"""De eigen factcheck van Factiz (PLAN #37.4, B82, SPECS E10.S4).

Een check is een map `content/redactie/<sleutel>/` met `check.toml`: de kop, het oordeel uit de schaal, de soort en vorm
die het archief kent, de bewering zoals ze rondgaat, de tekst met de nummers van haar bronnen, de beelden, de tijdlijn,
de bronnen, wie schreef en wie nalas, en de correcties. Een mens schrijft en tekent; Claude mag een concept maken, dat
dan zo heet. Het dossier met het onderzoek staat in `data/redactie/<sleutel>/`, buiten git, en komt nooit op de site.

    python -m doublecheck.redactie controleren          # elke check in content/redactie/

`controleer` weigert wat de code van het EFCSN niet toelaat: minder dan twee bronnen voor de kern (een andere factchecker
telt niet mee), een nummer zonder bron of een bron zonder nummer, een oordeel buiten de schaal, een gepubliceerde check
zonder schrijver of zonder een nalezer die niet Claude en niet de schrijver is (B84), met iets in `nog_doen` (wat nog uit te
zoeken is, `nog_uitzoeken`, staat op de pagina), een directe link naar de post van een privépersoon (alleen een
archiefkopie, B70, of de vermelding dat de post weg is, B84, of de reden waarom er geen kopie is, `geen_kopie`), en een beeld dat rondgaat zonder stempel, bronregel of
alt-tekst. Het
voorstel: docs/voorstellen/2026-11-18-eigen-factcheck.md.
"""

from __future__ import annotations

import json
import re
import sys
import tomllib
from pathlib import Path

WORTEL = Path(__file__).resolve().parent.parent
MAP = WORTEL / "content" / "redactie"

# De schaal van oordelen (het voorstel van 2026-11-18); de soort en de vorm zijn die van het archief (`soortvorm`)
SCHAAL = {
    "onwaar": {"nl": "Onwaar", "en": "False"},
    "misleidend": {"nl": "Misleidend", "en": "Misleading"},
    "context": {"nl": "Ontbrekende context", "en": "Missing context"},
    "grotendeels": {"nl": "Klopt grotendeels", "en": "Mostly true"},
    "klopt": {"nl": "Klopt", "en": "True"},
    "onbewezen": {"nl": "Onbewezen", "en": "Unproven"},
}


def oordeel_tekst(oordeel: str, taal: str) -> str:
    """Het oordeel in de taal van de check: de schaal hierboven voor het Nederlands en het Engels, anders de woorden van de
    site (`eigen_oordeel_<oordeel>` in factiz_site/teksten), zodat een check in het Turks YANLIŞ zegt (#37.10)."""
    if taal in SCHAAL[oordeel]:
        return SCHAAL[oordeel][taal]
    teksten = Path(__file__).resolve().parent.parent / "factiz_site" / "teksten" / f"{taal}.json"
    try:
        return json.loads(teksten.read_text(encoding="utf-8"))["teksten"][f"eigen_oordeel_{oordeel}"]
    except (OSError, KeyError, ValueError):
        return SCHAAL[oordeel]["en"]


STATUS = ("concept", "nagelezen", "gepubliceerd")
# de talen waarin de redactie zelf leest (B85 punt 5)
LEZER_TALEN = ("nl", "en")
BRONSOORTEN = ("bron", "nieuws", "factcheck")   # de bron zelf, het nieuws, een andere factchecker
VERPLICHT = ("sleutel", "status", "taal", "adres", "kop", "oordeel", "oordeel_zin", "bewering", "platform", "eerst_gezien",
             "kort", "tekst", "auteur", "bron")
# het adres van een check (PLAN #37.11, SPECS E10.S4 AC6, PO 2026-11-21: "Jaar en maand"): /<taal>/radar/<jjjj>/<mm>/<naam>/,
# met een korte naam van de bewering: kleine letters zonder accenten, cijfers en streepjes, minstens twee woorden
ADRES = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)+")
ADRES_MAX = 60
# het eerste stuk van het pad per taal van de site (Engels op de hoofdmap, `factiz_site/teksten/sitetalen.json`)
_PADEN = {t["code"]: t["pad"] for t in json.loads(
    (WORTEL / "factiz_site" / "teksten" / "sitetalen.json").read_text(encoding="utf-8"))["talen"]}
_NUMMER = re.compile(r"\[(\d+)\]")
_STREEPJE = re.compile("[—–]| -- ")


class Weigering(Exception):
    pass


def lees(pad: Path) -> dict:
    try:
        return tomllib.loads(Path(pad).read_text(encoding="utf-8"))
    except (tomllib.TOMLDecodeError, UnicodeDecodeError) as fout:
        raise Weigering(f"{pad}: geen geldige TOML ({fout})") from fout


def lees_alle(map_: Path = MAP) -> list[dict]:
    """Elke check in `content/redactie/<sleutel>/check.toml`; de sleutel moet de naam van de map zijn."""
    uit = []
    for pad in sorted(Path(map_).glob("*/check.toml")):
        check = lees(pad)
        if check.get("sleutel") != pad.parent.name:
            raise Weigering(f"{pad}: de sleutel {check.get('sleutel')!r} is niet de naam van de map")
        uit.append(check)
    return uit


def maand(check: dict, dag: str) -> str:
    """De maand in het adres van een check (`2026-11`): die van publicatie; een concept heeft er nog geen en krijgt die van
    `dag` (de dag van de uitgave), zodat ze ook in een voorbeeld een adres heeft. In een uitgave staat de maand bij de
    check (`publiceren.eigen_adressen`); een datum van publicatie gaat daar altijd voor."""
    return (check.get("gepubliceerd") or check.get("maand") or dag)[:7]


def naam_in(check: dict, taal: str) -> str:
    """De naam in het adres in een taal: in de taal van de check haar eigen naam, in elke vertaling de Engelse."""
    return check["adres"] if taal == check["taal"] else check.get("adres_en") or check["adres"]


SITETALEN = tuple(_PADEN)


def pad_in(check: dict, taal: str, maand_: str) -> str:
    """Het adres van een check in een taal van de site (PLAN #37.11): `/nl/radar/2026/11/klaver-citaat-privebezit/`."""
    jaar, mm = maand_.split("-")
    voor = f"/{_PADEN[taal]}" if _PADEN.get(taal) else ""
    return f"{voor}/radar/{jaar}/{mm}/{naam_in(check, taal)}/"


def botsingen(checks: list[dict], dag: str) -> list[str]:
    """De namen die in dezelfde maand bij twee checks horen: dan zou één adres naar twee checks wijzen. De eigen naam en de
    Engelse naam van één check mogen gelijk zijn."""
    gezien: dict[tuple[str, str], str] = {}
    fouten = []
    for c in sorted(checks, key=lambda c: c.get("sleutel", "")):
        if not c.get("adres"):
            continue
        for naam in {c["adres"], c.get("adres_en") or c["adres"]}:
            sleutel = (maand(c, dag), naam)
            if sleutel in gezien and gezien[sleutel] != c["sleutel"]:
                fouten.append(f"{c['sleutel']}: het adres {naam!r} heeft {gezien[sleutel]} in {sleutel[0]} al")
            gezien.setdefault(sleutel, c["sleutel"])
    return fouten


def _mens(naam: str) -> bool:
    return bool(naam.strip()) and "claude" not in naam.lower()



def _alle_tekst(x) -> str:
    """Alle tekst in een check, ook in lijsten en tabellen, aan elkaar."""
    if isinstance(x, dict):
        return " ".join(_alle_tekst(v) for v in x.values())
    if isinstance(x, list):
        return " ".join(_alle_tekst(v) for v in x)
    return x if isinstance(x, str) else ""

def controleer(check: dict) -> list[str]:
    """De fouten in één check; een lege lijst is goed."""
    from doublecheck.soortvorm import SOORTEN, VORMEN

    fouten = [f"{v} ontbreekt" for v in VERPLICHT if not check.get(v)]
    if fouten:
        return fouten
    if check["status"] not in STATUS:
        fouten.append(f"status {check['status']!r} bestaat niet")
    if check["oordeel"] not in SCHAAL:
        fouten.append(f"oordeel {check['oordeel']!r} staat niet in de schaal")
    if check.get("soort") and check["soort"] not in SOORTEN:
        fouten.append(f"soort {check['soort']!r} kent het archief niet")
    if check.get("vorm") and check["vorm"] not in VORMEN:
        fouten.append(f"vorm {check['vorm']!r} kent het archief niet")
    # lokaal of internationaal (B85, PO 2026-11-19): bepaalt de volgorde op de Radar van een andere taal
    if check.get("reikwijdte") and check["reikwijdte"] not in ("lokaal", "internationaal"):
        fouten.append(f"reikwijdte {check['reikwijdte']!r}: lokaal of internationaal")
    # de naam in het adres (PLAN #37.11): in de taal van de check, en een Engelse voor de vertalingen
    for veld in ("adres", "adres_en"):
        naam = check.get(veld)
        if veld == "adres_en" and not naam:
            if check["taal"] != "en":
                fouten.append("adres_en ontbreekt: de naam in het adres van de vertalingen, in het Engels")
            continue
        if not isinstance(naam, str) or not ADRES.fullmatch(naam) or len(naam) > ADRES_MAX:
            fouten.append(f"{veld} {naam!r}: kleine letters zonder accenten, cijfers en streepjes, minstens twee woorden, "
                          f"hoogstens {ADRES_MAX} tekens")

    bronnen = check["bron"]
    nummers = [b.get("nr") for b in bronnen]
    for b in bronnen:
        if b.get("soort") not in BRONSOORTEN:
            fouten.append(f"bron {b.get('nr')}: soort {b.get('soort')!r} bestaat niet")
        for veld in ("uitgever", "titel", "datum"):
            if not b.get(veld):
                fouten.append(f"bron {b.get('nr')}: {veld} ontbreekt")
        if b.get("prive"):
            # een post van een privépersoon: alleen via een archiefkopie, nooit een directe link (B70)
            if b.get("url"):
                fouten.append(f"bron {b.get('nr')} is van een privépersoon: alleen een archiefkopie, geen link")
            # een post die niet meer te zien is en waarvan geen kopie bestaat, mag met die vermelding (B84), en een post
            # waarvan geen kopie te maken was, met de reden in woorden (geen_kopie)
            if check["status"] == "gepubliceerd" and not b.get("archief") and not b.get("weg") \
                    and not str(b.get("geen_kopie") or "").strip():
                fouten.append(f"bron {b.get('nr')}: de archiefkopie ontbreekt")
        elif not str(b.get("url", "")).startswith(("https://", "http://")):
            fouten.append(f"bron {b.get('nr')}: de link is geen webadres")
        if b.get("archief") and not str(b["archief"]).startswith(("https://", "http://")):
            fouten.append(f"bron {b.get('nr')}: de archiefkopie is geen webadres")
    if len(set(nummers)) != len(nummers):
        fouten.append("twee bronnen met hetzelfde nummer")
    kern = {b.get("uitgever") for b in bronnen if b.get("soort") in ("bron", "nieuws")}
    if len(kern) < 2 and not check.get("een_bron"):
        fouten.append("minder dan twee bronnen van verschillende uitgevers voor de kern (een andere factchecker telt niet "
                      "mee); schrijf anders bij een_bron waarom er maar één kan zijn")

    lopend = " ".join(str(check.get(v, "")) for v in ("kort", "tekst", "niet_weten", "oordeel_zin"))
    lopend += " " + " ".join(str(t.get("wat", "")) for t in check.get("tijdlijn", []))
    genoemd = {int(n) for n in _NUMMER.findall(lopend)}
    for n in sorted(genoemd - set(nummers)):
        fouten.append(f"[{n}] in de tekst heeft geen bron")
    for n in sorted(set(nummers) - genoemd):
        fouten.append(f"bron {n} wordt in de tekst nergens genoemd")
    # de bewering is een citaat van de post (PO 2026-11-18): haar leestekens zijn van de schrijver, dus alleen onze eigen tekst
    alles = lopend + " " + check["kop"]
    if _STREEPJE.search(alles):
        fouten.append("een streepje als pauze in de tekst; gebruik een komma, punt of dubbelepunt")
    if "!" in alles:
        fouten.append("een uitroepteken in de tekst")
    # een aanduiding voor wat nog ontbreekt, komt nooit op een gepubliceerde pagina (B84: dat wordt nog uit te zoeken)
    if check["status"] == "gepubliceerd" and "FEIT NODIG" in _alle_tekst({k: v for k, v in check.items() if k != "nog_doen"}):
        fouten.append("een aanduiding [FEIT NODIG] staat nog in de check; zet wat ontbreekt bij nog_uitzoeken")

    for i, beeld in enumerate(check.get("beeld", []), 1):
        if beeld.get("pad") and not str(beeld["pad"]).startswith(f"/static/redactie/{check.get('sleutel')}/"):
            fouten.append(f"beeld {i}: het pad wijst buiten de map van deze check")
        if beeld.get("rol") == "rondgaat":
            for veld, wat in (("stempel", "stempel"), ("bijschrift", "bronregel"), ("alt", "alt-tekst")):
                if not beeld.get(veld):
                    fouten.append(f"beeld {i} gaat rond en heeft geen {wat}")
            # vervagen is nooit de standaard (PO 2026-11-18), alleen bij een minderjarige of gruwelijk beeld, met reden
            vakken = beeld.get("vervaag") or []
            if vakken and not beeld.get("vervaag_reden"):
                fouten.append(f"beeld {i} wordt vervaagd zonder reden (vervaag_reden)")
            if any(len(v) != 4 or not all(isinstance(g, (int, float)) and 0 <= g <= 1 for g in v) for v in vakken):
                fouten.append(f"beeld {i}: een vak om te vervagen is vier getallen tussen 0 en 1 (x, y, breedte, hoogte)")
        elif beeld.get("rol") == "origineel":
            if beeld.get("stempel"):
                fouten.append(f"beeld {i} is het origineel en krijgt geen stempel")
            if not beeld.get("bijschrift"):
                fouten.append(f"beeld {i}: de maker en uitgever van het origineel ontbreken")
        else:
            fouten.append(f"beeld {i}: rol {beeld.get('rol')!r} bestaat niet (rondgaat of origineel)")

    # wat nog uit te zoeken is, staat op de pagina, ook bij een gepubliceerde check (B84): een lijst van zinnen
    if not isinstance(check.get("nog_uitzoeken", []), list) or not all(isinstance(n, str) and n.strip()
                                                                        for n in check.get("nog_uitzoeken", [])):
        fouten.append("nog uit te zoeken is een lijst van zinnen")
    if check["status"] == "gepubliceerd":
        # B84 (PO 2026-11-19): Claude mag schrijven, een mens of de redactie leest na; een concept draagt die naam niet
        auteur = check["auteur"].strip()
        if not auteur or "concept" in auteur.lower():
            fouten.append("een gepubliceerde check heeft een schrijver, zonder 'concept' in de naam (B84)")
        if not _mens(check.get("nalezer", "")) or check.get("nalezer", "").strip() == auteur:
            fouten.append("een gepubliceerde check heeft een nalezer die niet Claude en niet de schrijver is (B84)")
        if not check.get("gepubliceerd"):
            fouten.append("de datum van publicatie ontbreekt")
        # een check in een taal die de redactie niet leest, is in het Engels (of Nederlands) nagelezen, en de pagina zegt dat
        # (B85 punt 5, PO 2026-11-19: "nalezen doe ik dan zelf op vertaalde versie naar engels")
        if check["taal"] not in LEZER_TALEN and check.get("nagelezen_in") not in LEZER_TALEN:
            fouten.append(f"een gepubliceerde check in het {check['taal']} zegt in nagelezen_in in welke taal de redactie "
                          f"haar las ({' of '.join(LEZER_TALEN)})")
        if check.get("nog_doen"):
            fouten.append(f"er staat nog te doen: {len(check['nog_doen'])} punt(en)")
    return fouten


def main() -> None:  # pragma: no cover - CLI
    if sys.argv[1:] != ["controleren"]:
        raise SystemExit("gebruik: python -m doublecheck.redactie controleren")
    from datetime import date

    fout = False
    checks = []
    for pad in sorted(MAP.glob("*/check.toml")):
        check = lees(pad)
        checks.append(check)
        fouten = controleer(check)
        print(f"{pad.parent.name}: {'goed' if not fouten else '; '.join(fouten)}")
        fout |= bool(fouten)
    for f in botsingen(checks, date.today().isoformat()):
        print(f)
        fout = True
    raise SystemExit(1 if fout else 0)


if __name__ == "__main__":  # pragma: no cover
    main()
