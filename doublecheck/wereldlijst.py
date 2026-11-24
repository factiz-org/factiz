"""De wereldlijst (B90, B91, PLAN #37.12, SPECS E10.S6): wat er deze week in de wereld rondging, verdeeld over de regio's,
als gewone factcheckpagina's van het archief.

    python -m doublecheck.wereldlijst controleren
    python -m doublecheck.wereldlijst ronde [--tot JJJJ-MM-DD]        # de vier opdrachten van de week
    python -m doublecheck.wereldlijst schalen [--tot JJJJ-MM-DD]      # de schaal van het archief bij elk oordeel
    python -m doublecheck.wereldlijst nakijken [--tot JJJJ-MM-DD]     # de regels, vóór de pagina naar de PO gaat
    python -m doublecheck.wereldlijst pagina [--tot JJJJ-MM-DD]       # de keuzepagina voor de PO
    python -m doublecheck.wereldlijst akkoord --tot JJJJ-MM-DD --keuzes <json> --akkoord '<datum>, PO: "…"'

Elke week dezelfde ronde (PLAN #37.12, `docs/wereldlijst/RONDE.md`): vier onderzoekers op het web met de vaste opdracht
(`wereldlijst_onderzoek.md`, de eerste ronde van 2026-11-23), elk voor een deel van de wereld (`DELEN`), met wat Factiz al
heeft; hun voorstellen in `data/overzicht/<dag>/`; een keuzepagina; en de keuzes van de PO in één stap naar
`content/wereldlijst/<dag>.json`.

Een overzicht staat in `content/wereldlijst/<dag>.json` (één bestand per week, met het akkoord van de PO): de bewering in
de woorden van Factiz, waar ze rondging, wat de redacties vonden (elke zin met het nummer van zijn check) en per redactie
haar eigen oordeel, de datum, de titel en de link. Factiz geeft geen eigen oordeel (DR2): `schaal` is het woord van de
redactie op de schaal van het archief, zoals `verdicts` dat doet. In de uitgave wordt elk overzicht een pagina met de checks
van de redacties (bron `factiz-wereldlijst`) en de tabel `samenvatting`; de site toont het als elke andere factcheck.
"""

from __future__ import annotations

import argparse
import json
import re
import tomllib
from datetime import date, timedelta
from pathlib import Path
from string import Template

WORTEL = Path(__file__).resolve().parent.parent
MAP = WORTEL / "content" / "wereldlijst"
BRON = {"bron": "factiz-wereldlijst", "naam": "Factiz",
        "licentie": "Compiled by Factiz; each verdict is the newsroom's own, with a link to its fact-check",
        "naamsvermelding": "Factiz, overview of the newsrooms' fact-checks", "url": "https://factiz.org/"}
SCHALEN = ("onwaar", "misleidend", "deels-waar", "waar", "onbewezen", "satire")
REGIO = ("europa", "amerikas", "midden-oosten", "afrika", "zuid-azie", "oost-azie")
# naast het register van uitgevers erkend als de check die een overzicht draagt: de persbureaus en hun factcheckdesks, en
# redacties die actief lid zijn van het IFCN (`data/bronnen/extern/ifcn/actief.tsv`, #32.29d; Facta en Demagog ook van het
# EFCSN), nagekeken op 2026-11-23; een nieuwe erbij alleen na dezelfde controle
ERKEND = frozenset({"factcheck.afp.com", "factual.afp.com", "factuel.afp.com", "checamos.afp.com", "faktencheck.afp.com",
                    "factcheckarabic.afp.com", "reuters.com", "apnews.com", "dpa-factchecking.com", "verifica.efe.com",
                    "facta.news", "demagog.org.pl", "aosfatos.org", "boomlive.in", "thequint.com", "verafiles.org",
                    "france24.com", "open.online"})
_SLEUTEL = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
_DATUM = re.compile(r"\d{4}-\d{2}-\d{2}")
_NR = re.compile(r"\[(\d+)\]")
_MERK = re.compile(r"\s*\[\d+\]")
OVERZICHT = WORTEL / "data" / "overzicht"
REDACTIE = WORTEL / "content" / "redactie"
OPDRACHT = Path(__file__).with_name("wereldlijst_onderzoek.md")
PAGINA = Path(__file__).with_name("wereldlijst_pagina.html")
# de vier delen van de wereld van de eerste ronde (2026-11-23, door de PO goedgekeurd), elk met een eigen onderzoeker
DELEN = {
    "europa": {
        "aantal": 5, "regio": '"europa"', "titel": "Europe, including the Russia–Ukraine war",
        "gebied": "Find 5 claims about Europe (UK, Germany, France, Spain, Italy, Poland, the Baltics, the Nordics, the "
                  "Balkans, the EU itself) and the Russia–Ukraine war (Russian or pro-Kremlin disinformation, claims about "
                  "Ukraine, NATO). Spread them across countries; at most 2 about the war.",
        "redacties": "AFP Fact Check (and AFP Factuel, AFP Faktencheck, AFP Factual), Reuters Fact Check, AP, dpa-Faktencheck, "
                     "Correctiv, BR24 Faktenfuchs, Tagesschau Faktenfinder, Full Fact, BBC Verify, Les Décodeurs, Libération "
                     "CheckNews, France 24 Observers, Maldita, Newtral, EFE Verifica, Pagella Politica / Facta, Demagog (PL), "
                     "Re:Baltica, Faktabaari, StopFake, VoxCheck, EUvsDisinfo, Nieuwscheckers, Knack, VRT.",
        "voorbeeld": '"redactie": "AFP Fact Check", "land": "FR", "taal": "en"'},
    "amerikas": {
        "aantal": 5, "regio": '"amerikas"', "titel": "the Americas",
        "gebied": "Find 5 claims: at most 2 about the United States (only with international scope: foreign policy, world "
                  "leaders, health, climate, big companies; nothing purely domestic-partisan), and at least 3 about Latin "
                  "America and the Caribbean (Brazil, Mexico, Argentina, Colombia, Venezuela, Chile, Peru, Central America, "
                  "Haiti). Spread them across countries.",
        "redacties": "AFP Fact Check and AFP Factual (Spanish) and AFP Checamos (Portuguese), Reuters Fact Check, AP, "
                     "PolitiFact, FactCheck.org, Snopes, Lead Stories, USA Today, Chequeado, Aos Fatos, Agência Lupa, Estadão "
                     "Verifica, Comprova, Colombiacheck, La Silla Vacía Detector, Animal Político El Sabueso, Verificado, "
                     "Cotejo.info, Efecto Cocuyo, Bolivia Verifica, Ecuador Chequea, Fast Check CL, EFE Verifica.",
        "voorbeeld": '"redactie": "AFP Factual", "land": "FR", "taal": "es"'},
    "midden-oosten-afrika": {
        "aantal": 5, "regio": '"midden-oosten" or "afrika"', "titel": "the Middle East and Africa",
        "gebied": "Find 5 claims: about 3 from the Middle East (Israel and Gaza, Lebanon, Iran, Syria, Iraq, the Gulf "
                  "states, Yemen, Turkey, Egypt) and about 2 from sub-Saharan Africa (Nigeria, Kenya, South Africa, "
                  "Ethiopia, the Sahel, Sudan, DR Congo). Spread them across countries.",
        "redacties": "AFP Fact Check (English, Arabic, French Africa desks), Reuters Fact Check, AP, Misbar, Fatabyyano, "
                     "Teyit (Turkey), Doğruluk Payı, Factnameh (Iran), Akhbar Meter, Matsda2sh, Kashif, Annahar Fact Check, "
                     "Africa Check, PesaCheck, Dubawa, FactCheckHub, TheCable Fact Check, Code for Africa, Les Observateurs "
                     "de France 24, BBC Verify, Full Fact, Logically Facts, Snopes.",
        "voorbeeld": '"redactie": "Misbar", "land": "QA", "taal": "ar"'},
    "azie": {
        "aantal": 5, "regio": '"zuid-azie" or "oost-azie"', "titel": "South, East and Southeast Asia",
        "gebied": "Find 5 claims: about 2 from South Asia (India, Pakistan, Bangladesh, Sri Lanka, Nepal; prefer "
                  "India–Pakistan, regional conflict, health or claims that cross borders, not domestic party politics) "
                  "and about 3 from East and Southeast Asia (China, Taiwan, Hong Kong, Japan, the Koreas, the Philippines, "
                  "Indonesia, Malaysia, Thailand, Vietnam, Myanmar). At least one should be about China or Chinese state "
                  "narratives. Spread them across countries.",
        "redacties": "AFP Fact Check (English, Chinese, Hindi, Bengali, Tamil, Indonesian, Thai, Korean, Japanese desks), "
                     "Reuters Fact Check, AP, BOOM, Alt News, Factly, India Today Fact Check, NewsMobile, Vishvas News, The "
                     "Quint WebQoof, Soch Fact Check, Rumor Scanner, Dismislab, Taiwan FactCheck Center, MyGoPen, Cofacts, "
                     "Annie Lab, Vera Files, Rappler, Tsek.ph, Mafindo / Turn Back Hoax, Tempo Cek Fakta, Kompas Cek Fakta, "
                     "Sure And Share, Cofact Thailand, JFC Japan, SNU FactCheck, Myanmar Now.",
        "voorbeeld": '"redactie": "BOOM", "land": "IN", "taal": "en"'},
}
REGIO_EN = {"europa": "Europe", "amerikas": "Americas", "midden-oosten": "Middle East", "afrika": "Africa",
            "zuid-azie": "South Asia", "oost-azie": "East Asia"}
MAANDEN = ("januari", "februari", "maart", "april", "mei", "juni", "juli", "augustus", "september", "oktober", "november",
           "december")
AKKOORD = re.compile(r'\d{4}-\d{2}-\d{2}, PO: ".+"')
KEUZES = ("goed", "twijfel", "weg")


class Weigering(Exception):
    pass


def _host(url: str) -> str:
    from doublecheck.evidence import _host as host

    return host(url) or ""


def zonder_nummers(zin: str) -> str:
    """De zin zoals de site haar toont: zonder de nummers van de bronnen, die als link naar de check komen."""
    return " ".join(_MERK.sub("", zin).split())


def controleer(o: dict, register: dict[str, str]) -> list[str]:
    """Wat een overzicht mist of verkeerd doet; leeg is goed."""
    fouten = []
    if not _SLEUTEL.fullmatch(o.get("sleutel") or ""):
        fouten.append("sleutel: kleine letters, cijfers en streepjes")
    if o.get("status") not in ("concept", "gepubliceerd"):
        fouten.append("status: concept of gepubliceerd")
    if o.get("regio") not in REGIO:
        fouten.append(f"regio: een van {', '.join(REGIO)}")
    if not (o.get("bewering") or "").strip() or len(o["bewering"]) > 400:
        fouten.append("bewering: één zin, hoogstens 400 tekens")
    checks = o.get("checks") or []
    nummers = {k.get("nr") for k in checks}
    if not checks:
        fouten.append("geen check van een redactie")
    if len(nummers) != len(checks):
        fouten.append("twee checks met hetzelfde nummer")
    kern = o.get("kern") or []
    if not 1 <= len(kern) <= 5:
        fouten.append("kern: een tot vijf zinnen")
    zinnen = [*kern, *([o["rondgang"]] if o.get("rondgang") else [])]
    genoemd = set()
    for zin in zinnen:
        nrs = {int(n) for n in _NR.findall(zin)}
        if not nrs:
            fouten.append(f"zin zonder bron: {zin[:60]}")
        for n in sorted(nrs - nummers):
            fouten.append(f"[{n}] bestaat niet: {zin[:60]}")
        genoemd |= nrs
    for n in sorted(nummers - genoemd, key=str):
        fouten.append(f"check [{n}] wordt niet genoemd")
    for veld, tekst in [("bewering", o.get("bewering") or ""), *(("zin", z) for z in zinnen)]:
        if "—" in tekst or "!" in tekst:
            fouten.append(f"{veld}: geen lange streep of uitroepteken")
    for k in checks:
        wie = f"check [{k.get('nr')}]"
        if k.get("schaal") not in SCHALEN:
            fouten.append(f"{wie}: schaal {k.get('schaal')!r}, een van {', '.join(SCHALEN)}")
        if not (k.get("redactie") or "").strip() or not (k.get("oordeel") or "").strip():
            fouten.append(f"{wie}: redactie en haar oordeel")
        if not _DATUM.fullmatch(k.get("datum") or ""):
            fouten.append(f"{wie}: datum als JJJJ-MM-DD")
        if not (k.get("url") or "").startswith("https://"):
            fouten.append(f"{wie}: een link met https")
    if checks and not any(_host(k.get("url") or "") in register or _host(k.get("url") or "") in ERKEND for k in checks):
        fouten.append("geen check van een erkende redactie of een persbureau")
    post = o.get("post") or None
    if post and post.get("prive") and post.get("url") and not post.get("archief"):
        fouten.append("post van een privépersoon: alleen als archiefkopie, nooit een directe link")
    return fouten


def lees_alle(map_: Path = MAP) -> list[dict]:
    """Elk overzicht uit `content/wereldlijst/*.json`, in de volgorde van de bestanden."""
    uit = []
    for pad in sorted(Path(map_).glob("*.json")):
        blad = json.loads(pad.read_text(encoding="utf-8"))
        uit += [{**o, "_week": blad.get("week", pad.stem)} for o in blad.get("overzichten", [])]
    return uit


def paginas(overzichten: list[dict], register: dict[str, str], concepten: bool) -> tuple[list[dict], dict]:
    """De overzichten als pagina's van het archief, en per pagina de zinnen van de samenvatting met de links van hun
    checks. Een overzicht dat de regels breekt, houdt de uitgave tegen; een concept gaat alleen mee met `concepten`."""
    from doublecheck.publiceren import nummer, richting
    from doublecheck.verdicts import labelklasse_in_tijd

    uit, samen, telling = [], {}, {"gepubliceerd": 0, "concept": 0}
    for o in sorted(overzichten, key=lambda o: o.get("sleutel", "")):
        fouten = controleer(o, register)
        if fouten:
            raise Weigering(f"wereldlijst {o.get('sleutel')}: {'; '.join(fouten)}")
        if o["status"] != "gepubliceerd" and not concepten:
            continue
        telling[o["status"]] += 1
        taal = o.get("taal") or "en"
        url_van = {k["nr"]: k["url"] for k in o["checks"]}
        checks = sorted(({
            "redactie": register.get(_host(k["url"])) or k["redactie"], "oordeel": k["schaal"], "oordeel_eigen": k["oordeel"],
            "datum": k["datum"], "taal": k.get("taal") or "und", "url": k["url"], "link": "unchecked",
            "archief_url": None, "archief_datum": None, "bron": BRON["bron"]} for k in o["checks"]),
            key=lambda k: (k["datum"], k["redactie"], k["url"]), reverse=True)
        label, eerder = labelklasse_in_tijd((k["oordeel"], k["datum"]) for k in checks)
        datums = sorted(k["datum"] for k in checks)
        nr = nummer(f"wereldlijst-{o['sleutel']}")
        uit.append({
            "nummer": nr, "bewering": o["bewering"].strip(), "taal": taal, "richting": richting(taal), "label": label,
            "eerder": [list(e) for e in eerder], "checks": checks, "redacties": len({k["redactie"] for k in checks}),
            "talen": sorted({taal, *(k["taal"] for k in checks)} - {"und"}), "eerste_datum": datums[0],
            "laatste_datum": datums[-1], "formuleringen": [], "leden": [], "kenmerk": ("", ""),
            # de machinevertaling van het overzicht (#37.12 punt 5): gaat voor die van `weergave`
            "vertaald": {t: (v["velden"]["bewering"], v["maker"]) for t, v in sorted((o.get("vertalingen") or {}).items())
                         if v.get("velden", {}).get("bewering")}})
        # de zinnen per taal: het origineel en elke vertaling, elk met de links van de checks achter haar nummers
        samen[nr] = []
        for t, velden in [(taal, o), *((t, v["velden"]) for t, v in sorted((o.get("vertalingen") or {}).items()))]:
            zinnen = [("vond", z) for z in velden.get("kern") or []] + (
                [("rondgang", velden["rondgang"])] if velden.get("rondgang") else [])
            samen[nr] += [(t, soort, zonder_nummers(z), list(dict.fromkeys(url_van[int(n)] for n in _NR.findall(z)
                                                                          if int(n) in url_van)))
                          for soort, z in zinnen]
    return sorted(uit, key=lambda p: p["nummer"]), {"zinnen": samen, "telling": telling}


# --- de wekelijkse ronde (PLAN #37.12) ----------------------------------------------------------------------------------
def venster(tot: str) -> tuple[str, str]:
    """De week van een ronde: van zeven dagen terug tot en met de dag zelf (een dag overlap met de vorige ronde; wat al
    gedekt is, slaat de opdracht over)."""
    return (date.fromisoformat(tot) - timedelta(days=7)).isoformat(), tot


def _woorden(sleutel: str) -> str:
    return " ".join(sleutel.split("-"))


def al_gedaan(redactie: Path = REDACTIE, wereld: Path = MAP) -> list[str]:
    """Wat Factiz al heeft, als korte onderwerpen voor de opdracht: elke eigen check (haar Engelse adres, anders haar adres
    of sleutel) en elk overzicht van een eerdere wereldlijst."""
    uit = set()
    for pad in sorted(Path(redactie).glob("*/check.toml")):
        c = tomllib.loads(pad.read_text(encoding="utf-8"))
        uit.add(_woorden(c.get("adres_en") or c.get("adres") or c.get("sleutel") or pad.parent.name))
    for o in lees_alle(wereld):
        uit.add(_woorden(o["sleutel"]))
    return sorted(uit)


def opdracht(deel: str, tot: str, gedaan: list[str], uitvoer: Path) -> str:
    """De opdracht voor de onderzoeker van één deel van de wereld, zoals in de eerste ronde."""
    d = DELEN[deel]
    van, tot = venster(tot)
    return Template(OPDRACHT.read_text(encoding="utf-8")).substitute(
        aantal=d["aantal"], vandaag=tot, titel=d["titel"], gebied=d["gebied"], van=van, tot=tot, redacties=d["redacties"],
        al_gedaan=(", ".join(gedaan) + ".") if gedaan else "nothing yet.", uitvoer=str(uitvoer), regio=d["regio"],
        voorbeeld=d["voorbeeld"])


def ronde(tot: str, map_: Path = OVERZICHT) -> list[Path]:
    """Schrijft de vier opdrachten van de week in `data/overzicht/<tot>/`; elk noemt het bestand voor haar voorstellen."""
    week = Path(map_) / tot
    week.mkdir(parents=True, exist_ok=True)
    gedaan = al_gedaan()
    paden = []
    for deel in DELEN:
        pad = week / f"opdracht-{deel}.md"
        pad.write_text(opdracht(deel, tot, gedaan, week / f"{deel}.json"), encoding="utf-8")
        paden.append(pad)
    return paden


def voorstellen(tot: str, map_: Path = OVERZICHT) -> list[dict]:
    """De voorstellen van de onderzoekers van een week, op volgorde van de regio's."""
    uit = []
    for deel in DELEN:
        pad = Path(map_) / tot / f"{deel}.json"
        if pad.exists():
            uit += json.loads(pad.read_text(encoding="utf-8"))
    return sorted(uit, key=lambda o: REGIO.index(o["regio"]) if o.get("regio") in REGIO else len(REGIO))


def _datum_nl(dag: str) -> tuple[int, str, int]:
    d = date.fromisoformat(dag)
    return d.day, MAANDEN[d.month - 1], d.year


def schaal_van(check: dict) -> str | None:
    """Het woord van de redactie op de schaal van het archief (`verdicts`): eerst haar eigen oordeelwoord met haar schaal,
    dan de Engelse weergave. Nooit geraden: wat de tabel niet kent, blijft open."""
    from doublecheck.verdicts import normalize_verdict

    for label, host in ((check.get("oordeel"), _host(check.get("url") or "")), (check.get("oordeel_en"), None)):
        schaal = normalize_verdict(label, host)
        if schaal in SCHALEN:
            return schaal
    return None


def vul_schalen(tot: str, map_: Path = OVERZICHT) -> list[str]:
    """Zet in de voorstellen van de week bij elke check zonder `schaal` het woord dat de tabel kent, en geeft de checks die
    open blijven: die zet wie de ronde nakijkt met de hand, op de schaal van het archief (de eerste ronde deed dat zo)."""
    open_ = []
    for deel in DELEN:
        pad = Path(map_) / tot / f"{deel}.json"
        if not pad.exists():
            continue
        items = json.loads(pad.read_text(encoding="utf-8"))
        for o in items:
            for k in o.get("checks") or []:
                if k.get("schaal") not in SCHALEN:
                    k["schaal"] = schaal_van(k) or k.get("schaal")
                    if k["schaal"] not in SCHALEN:
                        open_.append(f"{o.get('sleutel')} [{k.get('nr')}]: {k.get('oordeel')} / {k.get('oordeel_en')}")
        pad.write_text(json.dumps(items, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return open_


def _als_overzicht(o: dict, status: str) -> dict:
    """Een voorstel zoals het in het weekbestand komt: met status en taal, en elke check met haar schaal."""
    return {"sleutel": o.get("sleutel"), "status": status, "taal": "en",
            **{k: v for k, v in o.items() if k not in ("sleutel", "checks")},
            "checks": [{**k, "schaal": k.get("schaal") if k.get("schaal") in SCHALEN else schaal_van(k)}
                       for k in o.get("checks") or []]}


def nakijken(tot: str, map_: Path = OVERZICHT, register: dict[str, str] | None = None) -> list[str]:
    """Wat de voorstellen van een week missen, vóór de pagina naar de PO gaat: de regels van het weekbestand (`controleer`),
    een check buiten de week, en twee voorstellen met dezelfde sleutel."""
    if register is None:
        from doublecheck import toelating

        register = toelating.register()
    van, tot_ = venster(tot)
    fouten, gezien = [], set()
    for o in voorstellen(tot, map_):
        if o.get("sleutel") in gezien:
            fouten.append(f"{o.get('sleutel')}: twee voorstellen met deze sleutel")
        gezien.add(o.get("sleutel"))
        fouten += [f"{o.get('sleutel')}: {f}" for f in controleer(_als_overzicht(o, "concept"), register)]
        fouten += [f"{o.get('sleutel')}: check [{k.get('nr')}] van {k.get('datum')}, buiten {van} tot {tot_}"
                   for k in o.get("checks") or [] if not van <= (k.get("datum") or "") <= tot_]
    return fouten


def pagina(tot: str, map_: Path = OVERZICHT) -> Path:
    """De keuzepagina voor de PO (goed, twijfel of weg per overzicht, in de database van de pagina): de overzichten in het
    Engels zoals op de site, de omlijsting in het Nederlands. Weeknummer: de week die net voorbij is."""
    items = voorstellen(tot, map_)
    if not items:
        raise Weigering(f"geen voorstellen in {Path(map_) / tot}")
    van, tot_ = venster(tot)
    (d1, m1, j1), (d2, m2, j2) = _datum_nl(van), _datum_nl(tot_)
    tussen = f"{d1} en {d2} {m2} {j2}" if (m1, j1) == (m2, j2) else f"{d1} {m1} en {d2} {m2} {j2}"
    weeknr = (date.fromisoformat(tot) - timedelta(days=1)).isocalendar()[1]
    data = json.dumps(items, ensure_ascii=False).replace("<", "\\u003c")
    html = (PAGINA.read_text(encoding="utf-8").replace("__DATA__", data).replace("__REGIO__", json.dumps(REGIO_EN))
            .replace("__N__", str(len(items))).replace("__TITEL__", f"Wereldlijst week {weeknr}")
            .replace("__KOP__", f"{len(items)} overzichten van wat wereldwijd rondging, week {weeknr}")
            .replace("__VENSTER__", f"{tussen}"))
    pad = Path(map_) / tot / "overzichten.html"
    pad.write_text(html, encoding="utf-8")
    return pad


def akkoord(tot: str, keuzes: dict[str, str], akkoord_tekst: str, map_: Path = OVERZICHT, uit: Path = MAP,
            register: dict[str, str] | None = None) -> Path:
    """De keuzes van de PO naar het weekbestand: goed wordt gepubliceerd, twijfel een concept (gaat niet mee), weg valt
    eruit. Weigert zonder akkoord in de vaste vorm, zonder keuze voor elk voorstel, over een week die er al is, en als een
    overzicht dat meegaat de regels breekt (`controleer`); dan wordt er niets geschreven."""
    if not AKKOORD.fullmatch(akkoord_tekst or ""):
        raise Weigering("akkoord: '<datum>, PO: \"<haar woorden>\"'")
    pad = Path(uit) / f"{tot}.json"
    if pad.exists():
        raise Weigering(f"{pad} bestaat al")
    items = voorstellen(tot, map_)
    open_ = [o["sleutel"] for o in items if keuzes.get(o["sleutel"]) not in KEUZES]
    if open_:
        raise Weigering(f"geen keuze voor {', '.join(open_)}")
    if register is None:
        from doublecheck import toelating

        register = toelating.register()
    overzichten = []
    for o in items:
        keuze = keuzes[o["sleutel"]]
        if keuze == "weg":
            continue
        o = _als_overzicht(o, "gepubliceerd" if keuze == "goed" else "concept")
        fouten = controleer(o, register)
        if fouten:
            raise Weigering(f"{o['sleutel']}: {'; '.join(fouten)}")
        overzichten.append(o)
    van, _ = venster(tot)
    blad = {"week": tot, "toelichting": f"De wereldlijst van {van} tot en met {tot}: wat in die week wereldwijd rondging, "
                                         "gecheckt door de redacties; goed is gepubliceerd, twijfel staat als concept.",
            "akkoord": akkoord_tekst, "overzichten": overzichten}
    Path(uit).mkdir(parents=True, exist_ok=True)
    pad.write_text(json.dumps(blad, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return pad


def main() -> None:  # pragma: no cover - CLI
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("stap", choices=["controleren", "ronde", "schalen", "nakijken", "pagina", "akkoord"])
    p.add_argument("--tot", default=date.today().isoformat(), help="de laatste dag van de week (standaard vandaag)")
    p.add_argument("--keuzes", help="akkoord: een JSON-bestand {sleutel: goed|twijfel|weg}")
    p.add_argument("--akkoord", help="akkoord: '<datum>, PO: \"<haar woorden>\"'")
    a = p.parse_args()
    try:
        if a.stap == "ronde":
            for pad in ronde(a.tot):
                print(pad)
            return
        if a.stap == "schalen":
            open_ = vul_schalen(a.tot)
            print("\n".join(open_) if open_ else "elke check heeft een schaal")
            return
        if a.stap == "nakijken":
            fouten = nakijken(a.tot)
            print("\n".join(fouten) if fouten else f"{len(voorstellen(a.tot))} voorstellen, geen fouten")
            if fouten:
                raise SystemExit(1)
            return
        if a.stap == "pagina":
            print(pagina(a.tot))
            return
        if a.stap == "akkoord":
            keuzes = json.loads(Path(a.keuzes).read_text(encoding="utf-8"))
            print(akkoord(a.tot, keuzes, a.akkoord or ""))
            return
    except Weigering as fout:
        raise SystemExit(f"geweigerd: {fout}")
    from doublecheck import toelating

    register, fout = toelating.register(), 0
    alle = lees_alle()
    for o in alle:
        for f in controleer(o, register):
            print(f"{o.get('sleutel')}: {f}")
            fout += 1
    per = {}
    for o in alle:
        per[o["regio"]] = per.get(o["regio"], 0) + 1
    print(f"{len(alle)} overzichten, {fout} fouten; per regio: {per}")
    if fout:
        raise SystemExit(1)


if __name__ == "__main__":  # pragma: no cover
    main()
