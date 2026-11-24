"""De leerstof van de eerste leerling (PLAN #31.3, E8.S3, B42).

Een tekst wordt "onwaar" (1) of "geen oordeel" (0). Labels komen alleen van
redacties of van de bron, nooit van de leraar: die verzint ontkrachtingen bij
verrassende waarheden (§140). Alleen het lesdeel van de ontwikkelhelft; het
keuzedeel van de basisset meet de leerling, de toetshelft geeft het
eindoordeel, en de kern en de minimale paren blijven de bewakers.

Per taal evenveel 0 als 1, zodat taal geen teken van nep wordt (van de
Russische stukken in de basisset is 90% onwaar): eerst de ware checks
(claimstijl), dan de betrouwbare Sheffield-artikelen, dan om en om Wikinews,
Wikipedia en webtekst; nooit aangevuld uit een andere taal.

    python -m doublecheck.leerstof bouwen
    python -m doublecheck.leerstof tellen
"""

from __future__ import annotations

import json
import random
import re
from collections import Counter
from pathlib import Path

WORTEL = Path(__file__).resolve().parent.parent
UIT = WORTEL / "data" / "leerstof"
BESTAND = UIT / "leerstof-v1.jsonl"
BESTAND_V2 = UIT / "leerstof-v2.jsonl"
BESTAND_V3 = UIT / "leerstof-v3.jsonl"
BESTAND_V4 = UIT / "leerstof-v4.jsonl"
MAX_TEKENS = 2_000
N_EEN = 10_000
ZAAD = 3001
BEWAKERS = {"n3-kern", "n3-paar", "minimale-paren"}
VOLGORDE_EERST = ("claimreview", "sheffield-trustworthy")
OM_EN_OM = ("wikinews", "wikipedia", "stiltepool")
_NAAM = {"english": "en", "russian": "ru", "german": "de", "french": "fr", "spanish": "es", "italian": "it",
         "polish": "pl", "czech": "cs", "slovak": "sk", "hungarian": "hu", "romanian": "ro", "bulgarian": "bg",
         "ukrainian": "uk", "serbian": "sr", "croatian": "hr", "lithuanian": "lt", "latvian": "lv", "estonian": "et",
         "finnish": "fi", "swedish": "sv", "norwegian": "no", "norwegian nynorsk": "nn", "danish": "da", "dutch": "nl",
         "greek": "el", "turkish": "tr", "arabic": "ar", "georgian": "ka", "armenian": "hy", "azerbaijani": "az",
         "portuguese": "pt", "chinese": "zh", "japanese": "ja", "korean": "ko", "belarusian": "be",
         "macedonian": "mk", "slovenian": "sl", "filipino": "tl", "telugu": "te", "tamil": "ta", "kannada": "kn",
         "hindi": "hi", "malayalam": "ml", "bengali": "bn", "sinhala": "si", "persian": "fa",
         "indonesian": "id", "afrikaans": "af"}


def taalcode(taal: str | None) -> str:
    """Eén code per taal: de bronnen schrijven "ru", "Russian" en "russian"."""
    t = (taal or "und").strip()
    return _NAAM.get(t.lower(), t.lower())


def deel_van(stuk: dict) -> str:
    """Les of keuze binnen de ontwikkelhelft, per zaak (of per artikel)."""
    from doublecheck.rechtermeting import deel

    return deel(stuk.get("zaak") or stuk["sleutel"])


def mag_leren(stuk: dict) -> bool:
    return (stuk["helft"] == "ontwikkel" and not stuk.get("vers") and stuk.get("bron") not in BEWAKERS
            and deel_van(stuk) == "les")


def label_leerling(label: str) -> int:
    return 1 if label == "onwaar" else 0


def schoon(tekst: str) -> str:
    """Sjablonen en markup weg, witruimte samengevoegd, hooguit `MAX_TEKENS`."""
    t = re.sub(r"<dynamicpagelist>.*?</dynamicpagelist>", " ", tekst, flags=re.S)
    for _ in range(3):  # geneste sjablonen
        t = re.sub(r"\{\{[^{}]*\}\}", " ", t)
    t = re.sub(r"<[^>]{0,200}>", " ", t)
    return " ".join(t.split())[:MAX_TEKENS]


def nullen_per_taal(een: list[dict], nul: dict[str, dict[str, list[dict]]], zaad: int = ZAAD) -> list[dict]:
    """Per taal zoveel 0 als er 1 zijn: eerst `VOLGORDE_EERST`, dan om en om
    `OM_EN_OM`, telkens willekeurig binnen een bron en telkens dezelfde."""
    rng = random.Random(zaad)
    uit: list[dict] = []
    for taal, nodig in sorted(Counter(s["taal"] for s in een).items()):
        bronnen = nul.get(taal, {})
        gekozen: list[dict] = []
        for bron in VOLGORDE_EERST:
            lijst = list(bronnen.get(bron, []))
            rng.shuffle(lijst)
            gekozen += lijst[: max(0, nodig - len(gekozen))]
        poelen = []
        for bron in OM_EN_OM:
            lijst = list(bronnen.get(bron, []))
            rng.shuffle(lijst)
            poelen.append(lijst)
        i = 0
        while len(gekozen) < nodig and any(poelen):
            if poelen[i % len(poelen)]:
                gekozen.append(poelen[i % len(poelen)].pop())
            i += 1
        uit += gekozen
    return uit


# --- v2: stijl tegen stijl (akkoord PO 2026-10-23) --------------------------------------

CLAIMSTIJL = ("claimreview", "wikinews-kop", "wikipedia")
ARTIKELSTIJL = ("sheffield-trustworthy", "wikinews")
WEBTEKST_DEEL = 0.2
# v3, onderwerp tegen onderwerp (#31.5, akkoord PO 2026-10-23): Wikipedia over
# hetzelfde onderwerp als de onware stukken komt vóór de algemene stukken.
CLAIMSTIJL_V3 = ("claimreview", "wikipedia-onderwerp", "wikinews-kop", "wikipedia")
ARTIKELSTIJL_V3 = ("sheffield-trustworthy", "wikipedia-onderwerp-inleiding", "wikinews")
# v4, stijl én onderwerp (#31.5 ronde 2, akkoord PO 2026-10-25): tegenover een
# onware claim om en om een ware zin over hetzelfde onderwerp en een ware zin
# in claimstijl; daarna algemene Wikipedia-zinnen als aanvulling.
CLAIMGROEPEN_V4 = (("wikipedia-onderwerp",), ("claimreview", "wikinews-kop"))
CLAIMAANVULLING_V4 = ("wikipedia",)


def is_kop(titel: str) -> bool:
    """Een Wikinews-kop als ware zin in claimstijl: 15 tot 200 tekens en geen
    vraag (een vraag beweert niets)."""
    t = " ".join((titel or "").split())
    # Vraagtekens per schrift: Latijn, Arabisch, CJK, Grieks (U+037E), Armeens, Ethiopisch.
    return 15 <= len(t) <= 200 and not t.endswith(("?", "؟", "？", "\u037e", "\u055e", "\u1367"))


def _uit_volgorde(bronnen: dict[str, list], volgorde: tuple, nodig: int, rng: random.Random) -> list:
    gekozen: list = []
    for bron in volgorde:
        lijst = list(bronnen.get(bron, []))
        rng.shuffle(lijst)
        gekozen += lijst[: max(0, nodig - len(gekozen))]
    return gekozen


def _om_en_om(bronnen: dict[str, list], groepen: tuple, nodig: int, rng: random.Random,
              aanvulling: tuple = ()) -> list:
    """Om en om uit elke groep (elk een volgorde van bronnen) tot `nodig`; een
    groep die opraakt laat de andere verder gaan, daarna `aanvulling`."""
    rijen = []
    for groep in groepen:
        rij: list = []
        for bron in groep:
            lijst = list(bronnen.get(bron, []))
            rng.shuffle(lijst)
            rij += lijst
        rijen.append(rij)
    gekozen, i = [], 0
    while len(gekozen) < nodig and any(rijen):
        rij = rijen[i % len(rijen)]
        if rij:
            gekozen.append(rij.pop(0))
        i += 1
    return gekozen + _uit_volgorde(bronnen, aanvulling, nodig - len(gekozen), rng)


def stijl_tegen_stijl(een: list[dict], nul: dict[str, dict[str, list[dict]]], zaad: int = ZAAD,
                      claimstijl: tuple = CLAIMSTIJL, artikelstijl: tuple = ARTIKELSTIJL,
                      claimgroepen: tuple | None = None) -> list[dict]:
    """Per taal: tegenover elke onware claimtekst of beeldzin een ware zin in
    claimstijl (`claimstijl`, op volgorde; of om en om uit `claimgroepen`),
    tegenover elk onwaar artikel een waar artikel (`artikelstijl`), en
    daarbovenop een vijfde webtekst."""
    rng = random.Random(zaad)
    uit: list[dict] = []
    for taal in sorted({s["taal"] for s in een}):
        eigen = [s for s in een if s["taal"] == taal]
        n_artikel = sum(s["soort"] == "artikel" for s in eigen)
        n_claim = len(eigen) - n_artikel
        bronnen = nul.get(taal, {})
        if claimgroepen:
            uit += _om_en_om(bronnen, claimgroepen, n_claim, rng, CLAIMAANVULLING_V4)
        else:
            uit += _uit_volgorde(bronnen, claimstijl, n_claim, rng)
        uit += _uit_volgorde(bronnen, artikelstijl, n_artikel, rng)
        uit += _uit_volgorde(bronnen, ("stiltepool",), round(WEBTEKST_DEEL * len(eigen)), rng)
    return uit


def _regel(stuk: dict, tekst: str) -> dict:
    return {"tekst": schoon(tekst), "label": label_leerling(stuk["label"]), "bron": stuk["bron"],
            "taal": stuk["taal"], "soort": stuk["soort"], "herkomst": stuk["sleutel"]}


def bouwen(db: str = "doublecheck.db", versie: str = "v1") -> dict:  # pragma: no cover - op de bestanden en de database
    import sqlite3

    from doublecheck import basisset, bewering, echtnieuws, zeef
    from doublecheck.standaardmodel import _kant
    from doublecheck.variantenbatch import lees_regels

    stukken = basisset.lees()
    for s in stukken:
        s["taal"] = taalcode(s["taal"])
    in_basisset = {s["sleutel"] for s in stukken}
    # Beelden: de bewering die Haiku las (eerste vraag, anders de tweede).
    id_van = {i["sleutel"]: i["id"] for i in bewering.items()}
    zin = {**bewering._zinnen("v2"), **bewering._zinnen("v1")}
    een, nul_basis = [], []
    for s in stukken:
        if not mag_leren(s):
            continue
        if s["soort"] == "beeld":
            tekst = zin.get(id_van.get(s["sleutel"], ""))
            if not tekst:
                continue
            s = {**s, "tekst": tekst}
        (een if s["label"] == "onwaar" else nul_basis).append(s)
    # Aanvullen met rode claims van buiten de basisset, per taal naar verhouding.
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    datum = dict(conn.execute("SELECT claim_id, MIN(review_date) FROM factcheck GROUP BY claim_id"))
    rest = []
    for claim_id, tekst, taal in conn.execute("SELECT claim_id, canonical_text, language FROM claim"):
        sleutel = f"C:{claim_id}"
        if sleutel in in_basisset:
            continue
        s = basisset.stuk(sleutel, "tekst", "claimreview", "onwaar", zaak=claim_id,
                          datum=(datum.get(claim_id) or "")[:10] or None, taal=taalcode(taal), tekst=tekst)
        if mag_leren(s) and _kant(conn, claim_id) == "rood":
            rest.append(s)
    if len(een) < N_EEN:
        een += basisset.steekproef_per_taal(rest, N_EEN - len(een), zaad=ZAAD)
    # Nullen per taal en bron.
    nul: dict[str, dict[str, list]] = {}
    for s in nul_basis:
        nul.setdefault(s["taal"], {}).setdefault(s["bron"], []).append(s)
    for bron in ("wikinews", "wikipedia"):
        for s in echtnieuws.lees(bron):
            s = {**s, "zaak": s["sleutel"].split("#")[0], "taal": taalcode(s["taal"])}
            if mag_leren(s):
                nul.setdefault(s["taal"], {}).setdefault(bron, []).append(s)
                if versie in ("v2", "v3", "v4") and bron == "wikinews" and is_kop(s.get("titel") or ""):
                    kop = {**s, "sleutel": f"{s['sleutel']}#kop", "bron": "wikinews-kop", "soort": "kop",
                           "tekst": " ".join(s["titel"].split())}
                    nul[s["taal"]].setdefault("wikinews-kop", []).append(kop)
    for pool in zeef.POOLS:
        for r in lees_regels(pool):
            sleutel = f"N1:{pool.name}:{r['claim_id']}"
            if sleutel in in_basisset:
                continue
            s = basisset.stuk(sleutel, "webtekst", "stiltepool", "neutraal", taal=taalcode(r["taal"]),
                              tekst=r["varianten"][0]["tekst"])
            if mag_leren(s):
                nul.setdefault(s["taal"], {}).setdefault("stiltepool", []).append(s)
    if versie in ("v3", "v4"):
        from doublecheck import onderwerp

        uitgesloten = set(onderwerp.uitgesloten())
        for s in onderwerp.lees_stukken():
            s = {**s, "taal": taalcode(s["taal"])}
            if mag_leren(s) and s["sleutel"] not in uitgesloten:
                nul.setdefault(s["taal"], {}).setdefault(s["bron"], []).append(s)
        nullen = (stijl_tegen_stijl(een, nul, artikelstijl=ARTIKELSTIJL_V3, claimgroepen=CLAIMGROEPEN_V4)
                  if versie == "v4" else
                  stijl_tegen_stijl(een, nul, claimstijl=CLAIMSTIJL_V3, artikelstijl=ARTIKELSTIJL_V3))
    elif versie == "v2":
        nullen = stijl_tegen_stijl(een, nul)
    else:
        nullen = nullen_per_taal(een, nul)
    regels = [_regel(s, s["tekst"]) for s in een + nullen]
    regels = [r for r in regels if r["tekst"]]
    random.Random(ZAAD).shuffle(regels)
    UIT.mkdir(parents=True, exist_ok=True)
    pad = {"v2": BESTAND_V2, "v3": BESTAND_V3, "v4": BESTAND_V4}.get(versie, BESTAND)
    pad.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in regels), encoding="utf-8")
    return telling(regels)


# --- lastige paren: de ware tegenhanger in claimstijl (Sonnet, eerst een proef) ---------

PAREN_VERSIE = "paren-v1"
PAREN_MODEL = "claude-sonnet-5-5"
PAREN_SYSTEEM = ("You help build training data for a model that must not call true statements false. You write "
                 "accurate, sourced statements.")
PAREN_VRAAG = ("Fact-checkers rated the claim above false or misleading. Write its accurate counterpart: one plain "
               "factual sentence in the same language as the claim, about the same subject and the same moment, "
               "stating what is actually true according to reliable sources (for example what the fact-check "
               "found). It must be a statement of fact, not a denial such as 'It is false that...', and not a "
               "judgement about the claim. Give one source URL you base it on (a reliable news outlet, an official "
               "page or Wikipedia). If you do not know what is actually true, set weet to false.")
_PAREN_SCHEMA = {"type": "object", "properties": {"weet": {"type": "boolean"}, "ware_zin": {"type": "string"},
                                                  "bron": {"type": "string"}},
                 "required": ["weet", "ware_zin", "bron"], "additionalProperties": False}
PAREN = UIT / "paren"


def paar_verzoek(id_: str, claim: str, taal: str, datum: str | None) -> dict:
    tekst = f"Claim ({taal}), checked {datum or 'on an unknown date'}:\n{claim}\n\n{PAREN_VRAAG}"
    return {"custom_id": id_,
            "params": {"model": PAREN_MODEL, "max_tokens": 1_500, "system": PAREN_SYSTEEM,
                       "messages": [{"role": "user", "content": [{"type": "text", "text": tekst}]}],
                       "output_config": {"effort": "low", "format": {"type": "json_schema", "schema": _PAREN_SCHEMA}}}}


def lees_paar(tekst: str) -> tuple[str, str | None, str | None]:
    """("bekend", zin, bron), ("onbekend", None, None) als het model het niet
    weet of geen bron geeft, of ("onleesbaar", None, None)."""
    try:
        a = json.loads(tekst)
    except json.JSONDecodeError:
        return "onleesbaar", None, None
    zin, bron = " ".join(str(a.get("ware_zin") or "").split()), str(a.get("bron") or "").strip()
    if not a.get("weet") or not zin or not bron:
        return "onbekend", None, None
    return "bekend", zin, bron


def stijl_van(soort: str) -> str:
    return {"artikel": "artikel", "nieuws": "artikel", "webtekst": "webtekst"}.get(soort, "claim")


def telling(regels: list[dict]) -> dict:
    return {"regels": len(regels), "per label": dict(Counter(r["label"] for r in regels)),
            "per label en stijl": dict(Counter(f"{r['label']} {stijl_van(r['soort'])}" for r in regels)),
            "per label en bron": dict(Counter(f"{r['label']} {r['bron']}" for r in regels)),
            "per taal (1/0)": {t: f"{n1}/{n0}" for t, (n1, n0) in sorted(
                {t: (sum(1 for r in regels if r["taal"] == t and r["label"] == 1),
                     sum(1 for r in regels if r["taal"] == t and r["label"] == 0))
                 for t in {r["taal"] for r in regels}}.items(), key=lambda kv: -kv[1][0])}}


def _jsonl(pad: Path) -> list[dict]:
    from doublecheck.sheffield import regels

    return regels(pad)


def paren(stap: str, proef: int) -> None:  # pragma: no cover - met de Batch API
    """De proef van de lastige paren: indienen, ophalen of lezen."""
    import sqlite3

    PAREN.mkdir(parents=True, exist_ok=True)
    keuze_pad, batches, antwoorden = PAREN / "keuze.jsonl", PAREN / "batches.jsonl", PAREN / "antwoorden.jsonl"
    if stap == "lezen":
        keuze = {r["id"]: r for r in _jsonl(keuze_pad)}
        for r in _jsonl(antwoorden):
            k = keuze[r["id"]]
            print(f"\n[{r['id']} · {k['taal']}] {r['status']}\n  ONWAAR: {k['tekst'][:250]}\n  WAAR:   {r.get('zin')}"
                  f"\n  BRON:   {r.get('bron')}")
        return
    import anthropic

    from doublecheck.basisset import steekproef_per_taal
    from doublecheck.varianten import laad_sleutel

    laad_sleutel()
    client = anthropic.Anthropic()
    if stap == "indienen":
        if keuze_pad.exists():
            raise SystemExit("de proef is al ingediend")
        conn = sqlite3.connect("file:doublecheck.db?mode=ro", uri=True)
        claims = [r for r in _jsonl(BESTAND) if r["label"] == 1 and r["bron"] == "claimreview"]
        gekozen = steekproef_per_taal(claims, proef, zaad=ZAAD)
        keuze = []
        for i, r in enumerate(gekozen):
            datum = conn.execute("SELECT MIN(review_date) FROM factcheck WHERE claim_id = ?",
                                 (r["herkomst"][2:],)).fetchone()[0]
            keuze.append({"id": f"p-{i:04d}", "herkomst": r["herkomst"], "taal": r["taal"], "tekst": r["tekst"],
                          "datum": (datum or "")[:10] or None})
        batch = client.messages.batches.create(
            requests=[paar_verzoek(k["id"], k["tekst"], k["taal"], k["datum"]) for k in keuze])
        keuze_pad.write_text("".join(json.dumps(k, ensure_ascii=False) + "\n" for k in keuze), encoding="utf-8")
        batches.write_text(json.dumps({"id": batch.id, "prompt": PAREN_VERSIE, "n": len(keuze)}) + "\n")
        print(f"batch {batch.id}: {len(keuze)} paren")
        return
    b = _jsonl(batches)[-1]
    if client.messages.batches.retrieve(b["id"]).processing_status != "ended":
        print(f"batch {b['id']} loopt nog")
        return
    uit = []
    for r in client.messages.batches.results(b["id"]):
        tekst = next((c.text for c in r.result.message.content if c.type == "text"), "{}") \
            if r.result.type == "succeeded" else "{"
        status, zin, bron = lees_paar(tekst)
        uit.append({"id": r.custom_id, "status": status, "zin": zin, "bron": bron, "prompt": PAREN_VERSIE})
    antwoorden.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in sorted(uit, key=lambda r: r["id"])),
                          encoding="utf-8")
    print(Counter(r["status"] for r in uit))


def main() -> None:  # pragma: no cover - CLI
    import argparse

    parser = argparse.ArgumentParser(description="De leerstof van de eerste leerling (#31.3)")
    parser.add_argument("stap", choices=("bouwen", "tellen", "paren-indienen", "paren-ophalen", "paren-lezen"))
    parser.add_argument("--proef", type=int, default=100)
    parser.add_argument("--versie", choices=("v1", "v2", "v3", "v4"), default="v2")
    args = parser.parse_args()
    if args.stap.startswith("paren-"):
        paren(args.stap.removeprefix("paren-"), args.proef)
        return
    pad = {"v2": BESTAND_V2, "v3": BESTAND_V3, "v4": BESTAND_V4}.get(args.versie, BESTAND)
    uitslag = bouwen(versie=args.versie) if args.stap == "bouwen" else telling(_jsonl(pad))
    print(json.dumps(uitslag, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
