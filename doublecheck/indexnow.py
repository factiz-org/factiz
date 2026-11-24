"""IndexNow (PLAN #34.2bt, SPECS E9.S8 AC7): bij een uitgave in een open stand de nieuwe en gewijzigde adressen melden aan
de zoekmachines die IndexNow lezen (Bing en anderen), zodat ze niet op hun volgende ronde hoeven te wachten. De sleutel is
openbaar: de site toont hem op `/<sleutel>.txt` (`site/src/lib/koppen.js`), zodat een zoekmachine ziet dat een melding van
factiz.org komt. In stand 0 nooit."""

SLEUTEL = "34e72c3d34148a19b8beeb1a44fad523"

import hashlib
import json
import sqlite3
import urllib.error
import urllib.request

from factiz_site import db as fdb
from factiz_site import i18n
from factiz_site.bewaking import stand_uit  # noqa: F401  de stand uit site/wrangler.jsonc, één regel voor beide

HOST = "factiz.org"
SITE = f"https://{HOST}"
EINDPUNT = "https://api.indexnow.org/indexnow"
PER_MELDING = 10_000                # zoveel adressen neemt IndexNow per melding
AFZENDER = "FactizUitrolBot/1.0 (IndexNow na een uitgave)"


def _open(bestand) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{bestand}?mode=ro", uri=True)


def _vindbaar(c: sqlite3.Connection, stand: int) -> set[tuple[str, str]]:
    """(taal, nummer) van elke factcheck die in deze stand vindbaar is, met dezelfde regel als de sitemaps."""
    uit = set()
    # de vorige uitgave kan een ouder schema hebben: de regel volgt haar nummer (`_sitemap_waar`)
    schema = int(dict(c.execute("SELECT sleutel, waarde FROM meta"))["schema"])
    for taal in i18n.TALEN:
        waar, args = fdb.Publicatie._sitemap_waar(taal, stand, schema)
        uit |= {(taal, n) for (n,) in c.execute(f"SELECT p.nummer FROM pagina p WHERE {waar}", args)}
    return uit


def _radar(c: sqlite3.Connection) -> dict[str, str]:
    """Van elke gepubliceerde eigen check het adres in elke taal waarin zoekmachines haar zien, met een vingerafdruk van de
    check (PLAN #37.11); een uitgave zonder adressen (van voor schema 15) heeft er geen."""
    uit = {}
    for (g,) in c.execute("SELECT gegevens FROM eigen_check WHERE concept = 0 ORDER BY sleutel"):
        e = json.loads(g)
        afdruk = hashlib.sha256(g.encode("utf-8")).hexdigest()[:16]
        for taal in e.get("vindbaar_in") or []:
            if (e.get("paden") or {}).get(taal):
                uit[e["paden"][taal]] = afdruk
    return uit


def nieuwe_adressen(vorige, nieuwe, stand: int) -> list[str]:
    """De adressen die sinds de vorige uitgave nieuw of anders zijn: een factcheck die erbij kwam of een check, een datum
    erbij kreeg, of een taal waarin ze nu pas vindbaar is. Alleen waar ze in deze stand vindbaar is. En een eigen check van
    Factiz Radar die erbij kwam of veranderde, in elke taal waarin zoekmachines haar zien, met de Radar en haar maand in
    die taal (PLAN #37.11); de stand geldt voor het archief, niet voor de eigen checks."""
    oud_c, nieuw_c = _open(vorige), _open(nieuwe)
    try:
        staat = lambda c: {n: (d, k) for n, d, k in c.execute("SELECT nummer, laatste_datum, checks FROM pagina")}
        oud, nieuw = staat(oud_c), staat(nieuw_c)
        anders = {n for n, w in nieuw.items() if oud.get(n) != w}
        was, wordt = _vindbaar(oud_c, stand), _vindbaar(nieuw_c, stand)
        radar_was, radar_wordt = _radar(oud_c), _radar(nieuw_c)
    finally:
        oud_c.close()
        nieuw_c.close()
    uit = {SITE + i18n.pad(t, "fact-checks", n) for t, n in wordt if n in anders or (t, n) not in was}
    for pad, afdruk in radar_wordt.items():
        if radar_was.get(pad) != afdruk:
            maand = pad.rstrip("/").rsplit("/", 1)[0] + "/"
            uit |= {SITE + pad, SITE + maand, SITE + maand.rsplit("/", 3)[0] + "/"}
    return sorted(uit)


def _stuur(bericht: dict) -> int:  # pragma: no cover - het net
    verzoek = urllib.request.Request(EINDPUNT, data=json.dumps(bericht).encode("utf-8"), method="POST",
                                     headers={"Content-Type": "application/json; charset=utf-8", "User-Agent": AFZENDER})
    try:
        with urllib.request.urlopen(verzoek, timeout=60) as r:
            return r.status
    except urllib.error.HTTPError as fout:
        return fout.code


def meld(adressen: list[str], stuur=_stuur) -> dict:
    """Meldt de adressen in delen van hoogstens 10.000; alleen pagina's van factiz.org zelf."""
    for a in adressen:
        if not a.startswith(SITE + "/"):
            raise ValueError(f"geen pagina van {HOST}: {a}")
    antwoorden = [stuur({"host": HOST, "key": SLEUTEL, "keyLocation": f"{SITE}/{SLEUTEL}.txt",
                         "urlList": adressen[i:i + PER_MELDING]}) for i in range(0, len(adressen), PER_MELDING)]
    return {"gemeld": len(adressen), "antwoorden": antwoorden}


def melden(stand: int, vorige, nieuwe, stuur=_stuur) -> dict:
    """De stap van `uitrol live`: in stand 0 nooit, en zonder de vorige uitgave ook niet (dan zou alles nieuw lijken)."""
    if not stand:
        return {"gemeld": 0, "reden": "dicht"}
    if not vorige:
        return {"gemeld": 0, "reden": "geen vorige uitgave om mee te vergelijken"}
    adressen = nieuwe_adressen(vorige, nieuwe, stand)
    return meld(adressen, stuur) if adressen else {"gemeld": 0, "antwoorden": []}
