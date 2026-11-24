"""De factcheckpagina (`/api/<taal>/factcheck/<nummer>`) van de TypeScript-kant naast deze Python-kant (B80, PLAN #34.2bo
stap 3): elke sitetaal, en per kenmerk dat de pagina anders maakt een paar nummers uit de uitgave, aangevuld tot een vaste
steekproef; daarbij de nummers van een andere formulering (301) en nummers die er niet zijn of niet kloppen (404).

    python -m factiz_site.gelijk_factcheck [<publicatie.db>] [--n 300]

Een omleiding telt alleen als gelijk als ook het adres gelijk is.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from factiz_site import gelijk, i18n

# nummers die er niet zijn of geen nummer zijn: een gewoon nummer zonder pagina, hoofdletters, te kort, te lang, geen
# hexadecimaal, en wat na het decoderen van het adres witruimte of een letter met accent is
FOUT = ("0000000000000000", "0123456789ABCDEF", "0123456789abcde", "0123456789abcdef0", "x", "g123456789abcdef", "%20",
        "0123456789abcdef%0A", "%C3%A9t%C3%A9")

_DOSSIER = "p.nummer IN (SELECT i.pagina FROM dossier_item i JOIN dossier d ON d.sleutel = i.dossier WHERE "
# wat een factcheckpagina anders maakt, als voorwaarde op `pagina p`
KENMERKEN = {
    "vertaald": "EXISTS (SELECT 1 FROM vertaling v WHERE v.pagina = p.nummer AND v.taal <> 'en')",
    "engels_vertaald": "EXISTS (SELECT 1 FROM vertaling v WHERE v.pagina = p.nummer AND v.taal = 'en')",
    "zonder_vertaling": "NOT EXISTS (SELECT 1 FROM vertaling v WHERE v.pagina = p.nummer)",
    "normaal": "p.nummer IN (SELECT pagina FROM bewering_normaal)",
    "normaal_vertaald": "p.nummer IN (SELECT pagina FROM bewering_normaal) AND p.nummer IN (SELECT pagina FROM vertaling)",
    "soort": "p.nummer IN (SELECT pagina FROM kenmerk WHERE soort <> '')",
    "vorm": "p.nummer IN (SELECT pagina FROM kenmerk WHERE vorm <> '')",
    "soort_en_vorm": "p.nummer IN (SELECT pagina FROM kenmerk WHERE soort <> '' AND vorm <> '')",
    "kenmerk_zonder_thema": "p.nummer IN (SELECT pagina FROM kenmerk) AND p.thema IS NULL",
    "verhaal": _DOSSIER + "d.soort = 'verhaal' AND i.soort = 'factcheck' AND i.versie = '')",
    "versie": _DOSSIER + "d.soort = 'verhaal' AND i.soort = 'factcheck' AND i.versie <> '')",
    "netwerk": _DOSSIER + "d.soort = 'netwerk' AND i.soort = 'factcheck')",
    "toegeschreven": _DOSSIER + "d.soort = 'netwerk' AND i.soort = 'factcheck' AND i.bron <> '')",
    "twee_dossiers": "p.nummer IN (SELECT pagina FROM dossier_item WHERE soort = 'factcheck' GROUP BY pagina "
                     "HAVING COUNT(DISTINCT dossier) > 1)",
    "namen": "p.nummer IN (SELECT pagina FROM pagina_naam)",
    # dezelfde bewering bij een andere redactie (#34.2bp): het blok Ook gecheckt door, en meer dan één eigen check in een
    # andere volgorde per taal
    "zelfde": "p.nummer IN (SELECT pagina FROM zelfde)",
    "zelfde_meer_checks": "p.nummer IN (SELECT pagina FROM zelfde) AND p.checks > 1",
    "meer_talen": "p.nummer IN (SELECT pagina FROM check_ GROUP BY pagina HAVING COUNT(DISTINCT taal) > 1)",
    "veel_namen": "p.nummer IN (SELECT pagina FROM pagina_naam GROUP BY pagina HAVING COUNT(*) >= 3)",
    "waarom": "p.nummer IN (SELECT pagina FROM waarom)",
    "lijkt_op": "p.nummer IN (SELECT pagina FROM lijkt_op)",
    "lijkt_op_en_versie": "p.nummer IN (SELECT pagina FROM lijkt_op) AND p.nummer IN (SELECT pagina FROM dossier_item "
                          "WHERE versie <> '')",
    "formuleringen": "p.nummer IN (SELECT pagina FROM formulering)",
    "opgedoken": "p.nummer IN (SELECT pagina FROM opgedoken)",
    "veel_opgedoken": "p.nummer IN (SELECT pagina FROM opgedoken GROUP BY pagina HAVING COUNT(*) >= 5)",
    "offline": "p.nummer IN (SELECT pagina FROM check_ WHERE link = 'offline')",
    "archief": "p.nummer IN (SELECT pagina FROM check_ WHERE archief_url IS NOT NULL AND archief_url <> '')",
    "glossen": "p.nummer IN (SELECT k.pagina FROM check_ k JOIN oordeel_glos g ON g.tekst = k.oordeel_eigen)",
    "meer_redacties": "p.redacties > 1",
    "veel_redacties": "p.redacties >= 4",
    "veel_checks": "p.checks >= 6",
    "zonder_datum": "p.laatste_datum = ''",
    "check_zonder_datum": "p.nummer IN (SELECT pagina FROM check_ WHERE datum = '') AND p.laatste_datum <> ''",
    "rtl": "p.richting = 'rtl'",
    "zonder_label": "p.label IS NULL",
    "eerder": "p.eerder NOT IN ('', '[]')",
    "thema_land": "p.thema IS NOT NULL AND p.land <> ''",
    "land_zonder_thema": "p.thema IS NULL AND p.land <> ''",
    "onderdeel": "p.onderdeel <> ''",
    "tweede": "p.tweede <> ''",
    "zonder_thema": "p.thema IS NULL",
    "lang": "length(p.bewering) > 400",
    "veel_talen": "length(p.talen) > 12",
}


def _nummers(c, waar: str, per: int, params=()) -> list[str]:
    """Een vaste keuze: de volgorde van een stuk uit het midden van het nummer (een hash), dan het nummer."""
    return [r[0] for r in c.execute(f"SELECT p.nummer FROM pagina p WHERE {waar} ORDER BY substr(p.nummer, 7), p.nummer "
                                    "LIMIT ?", (*params, per))]


def nummers(pub, n: int = 300, per: int = 3) -> list[str]:
    """Nummers met elk kenmerk, elk oordeel, elke taal van een bewering, met een naam uit het netwerk en met een land
    waarvan Verkennen een verhouding noemt; aangevuld tot `n`. Een kleine uitgave helemaal."""
    c = pub._conn()
    if c.execute("SELECT COUNT(*) FROM pagina").fetchone()[0] <= n:
        return [r[0] for r in c.execute("SELECT nummer FROM pagina ORDER BY nummer")]
    uit: list[str] = []
    for waar in KENMERKEN.values():
        uit += _nummers(c, waar, per)
    for (lab,) in c.execute("SELECT DISTINCT label FROM pagina WHERE label IS NOT NULL ORDER BY label").fetchall():
        uit += _nummers(c, "p.label = ?", per, (lab,))
    for (taal,) in c.execute("SELECT DISTINCT taal FROM pagina ORDER BY taal").fetchall():
        uit += _nummers(c, "p.taal = ?", 2, (taal,))
    if pub.heeft_namen:
        net = [q for q, _, _ in pub.netwerk()["namen"]]
        for q in net[:: max(1, len(net) // 12)]:
            uit += _nummers(c, "p.nummer IN (SELECT pagina FROM pagina_naam WHERE naam = ?)", 1, (q,))
    for th in pub.themas:
        uit += _nummers(c, "p.thema = ? AND p.land <> ''", 1, (th["sleutel"],))
        for land, *_ in pub.verhoudingen(th["sleutel"], hoeveel=None)[:3]:
            uit += _nummers(c, "(p.thema = ? OR p.tweede = ?) AND p.land = ?", 1, (th["sleutel"], th["sleutel"], land))
    uit = list(dict.fromkeys(uit))
    if len(uit) < n:
        al = set(uit)
        rest = [r[0] for r in c.execute("SELECT nummer FROM pagina ORDER BY substr(nummer, 3), nummer LIMIT ?", (2 * n,))]
        uit += [x for x in rest if x not in al][:n - len(uit)]
    return uit


def adressen(pub, n: int = 300, per: int = 3, talen=None) -> list[str]:
    """Elke sitetaal, met de steekproef van `nummers`, de nummers van een andere formulering en de nummers die niet bestaan."""
    c = pub._conn()
    andere = [r[0] for r in c.execute("SELECT nummer FROM verwijzing ORDER BY substr(nummer, 7), nummer LIMIT 8")]
    alle = nummers(pub, n, per) + andere + list(FOUT)
    return [f"/api/{taal}/factcheck/{nr}" for taal in (talen or i18n.TALEN) for nr in alle]


SITE = gelijk.SITE
# De TypeScript-kant met andere grenzen voor het netwerk en Verkennen, zoals een toets ze in Python met monkeypatch zet.
_MET_GRENZEN = """
import { antwoord } from './src/platform/api.ts';
import { GRENZEN } from './src/platform/factcheck-gegevens.ts';
import { openDb } from './scripts/platform-node.ts';
let invoer = '';
for await (const stuk of process.stdin) invoer += stuk;
const { bestand, grenzen, adressen } = JSON.parse(invoer);
Object.assign(GRENZEN, grenzen);
const db = openDb(bestand);
const uit = [];
for (const pad of adressen) {
  const url = new URL(pad, 'http://platform');
  try { uit.push(await antwoord(db, decodeURIComponent(url.pathname), url.searchParams)); }
  catch (fout) { uit.push({ status: 500, fout: String(fout?.stack ?? fout) }); }
}
process.stdout.write(JSON.stringify(uit));
"""


def ts_antwoorden(bestand, adressen: list[str], grenzen: dict | None = None) -> list[dict]:
    if not grenzen:
        return gelijk.ts_antwoorden(bestand, adressen)
    uit = subprocess.run(["node", "--input-type=module", "-e", _MET_GRENZEN],
                         input=json.dumps({"bestand": str(bestand), "grenzen": grenzen, "adressen": adressen}, ensure_ascii=False),
                         capture_output=True, text=True, cwd=SITE, timeout=600)
    if uit.returncode:
        raise RuntimeError(uit.stderr[-3000:])
    return json.loads(uit.stdout)


def verschillen(client, bestand, adressen: list[str], grenzen: dict | None = None) -> list[str]:
    """Zoals `gelijk.verschillen`, en bij een omleiding ook het adres. `client` volgt geen omleiding."""
    uit = []
    for adres, t in zip(adressen, ts_antwoorden(bestand, adressen, grenzen)):
        r = client.get(adres)
        if r.status_code != t["status"]:
            uit.append(f"{adres}: Python {r.status_code}, TypeScript {t['status']} {str(t.get('fout', ''))[:800]}")
        elif r.status_code == 200:
            if v := gelijk.eerste_verschil(r.json(), t.get("body")):
                uit.append(f"{adres}: {v}")
        elif 300 <= r.status_code < 400 and r.headers.get("location") != t.get("adres"):
            uit.append(f"{adres}: Python naar {r.headers.get('location')}, TypeScript naar {t.get('adres')}")
    return uit


def main() -> None:  # pragma: no cover - CLI
    import time

    from starlette.testclient import TestClient

    from factiz_site import app as fa

    argumenten = sys.argv[1:]
    n = 300
    if "--n" in argumenten:
        i = argumenten.index("--n")
        n = int(argumenten[i + 1])
        del argumenten[i:i + 2]
    bestand = (Path(argumenten[0]) if argumenten else fa._standaard_pad()).resolve()
    client = TestClient(fa.maak_app(bestand), follow_redirects=False)
    lijst = adressen(fa.db.Publicatie(bestand), n=n)
    begin = time.time()
    fouten = verschillen(client, bestand, lijst)
    for f in fouten:
        print(f)
    print(f"{len(lijst) - len(fouten)} van {len(lijst)} adressen gelijk ({bestand}, {time.time() - begin:.0f} s)")
    raise SystemExit(1 if fouten else 0)


if __name__ == "__main__":  # pragma: no cover
    main()
