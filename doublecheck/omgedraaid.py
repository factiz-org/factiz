"""De conclusie in het veld van de bewering (PLAN #32.66, B68).

Bij route A zetten Maldita, Newtral en EFE Verifica soms hun eigen bevinding in het veld van de bewering
(`claimReviewed`), met hun oordeel erbij: "No, Nesspresso no ha regalado cafeteras ..." met *Bulo*, "El Banco de España
no ha recomendado tener dinero en efectivo ..." met *Falso*. Dan beweert de database het omgekeerde, en kan een waar
bericht rood worden. Een vaste vorm vangt maar een deel (`terugaanvoer.is_conclusie`, `_TITEL`), en een ontkenning
alleen zegt niets: "El COVID19 no es un virus" is een echte bewering. Haiku leest daarom elke negatieve check van die
drie (via de Batch API, openbare data), en ik lees elke *conclusie* en *twijfel* na (B34). Wat gelezen een conclusie of
twijfel is, gaat uit de database en komt bij een nieuwe import niet terug (`terugaanvoer.naar_import`). Twijfel gaat
ook weg: een check minder is strenger dan een omgedraaide.

    python -m doublecheck.omgedraaid set
    python -m doublecheck.omgedraaid indienen [--ontwikkel] [--proef N]|ophalen [--annuleer]|lezen|tellen
    python -m doublecheck.omgedraaid toepassen [--uitvoeren]

De hele publicatiedatabase (2026-11-12, `--ronde publicatie`): El Detector (Univision) zette via Data Commons "No se
descartaron votos en Arizona ..." met *onwaar* in het veld. Eerst een voormeting zonder model: per redactie de
negatieve checks met een ontkenning in de eigen taal (`vorm`). Ronde 1 leest elke negatieve check met zo'n vorm, ronde
2 alle andere negatieve checks van elke redactie waar ronde 1 een gelezen conclusie gaf (`tweede_ronde`), zolang de
grens het toeliet; ronde 3 de redacties die daar niet meer pasten (`derde_ronde`, PO 2026-11-12). Niet EUvsDisinfo: daar is het veld de desinformatie zelf. Wat gelezen weg moet, gaat uit de database van het lab en in
`doublecheck/omgedraaid_weg.json`, die elke import weigert (`ingest.import_claims`).

    python -m doublecheck.omgedraaid voormeting [--publicatie <db>]
    python -m doublecheck.omgedraaid set --ronde publicatie [--tweede | --derde]
    python -m doublecheck.omgedraaid indienen|ophalen|lezen|tellen|toepassen [--uitvoeren] --ronde publicatie
"""

from __future__ import annotations

import collections
import json
import re
from pathlib import Path

from doublecheck import eigenaanvoer as ea
from doublecheck import terugaanvoer as ta

MAP = ta.MAP / "omgedraaid"
SET = MAP / "set.jsonl"
ANTWOORDEN = MAP / "antwoorden.jsonl"
BATCHES = MAP / "batches.jsonl"
LABELS = ta.WORTEL / "docs" / "steekproeven" / "32.66-omgedraaid.json"
SITES = ("Maldita", "Newtral", "EFE Verifica")
NEGATIEF = frozenset({"onwaar", "misleidend", "deels-waar"})
VERSIE = "omgedraaid-v2"
# Samen gelezen: op de ontwikkelset vond v1 10 en v2 11 van de 13 omgedraaide, samen 12; een check is gemarkeerd als
# één versie hem markeert.
VERSIES = ("omgedraaid-v1", "omgedraaid-v2")
SOORTEN = ("bewering", "conclusie", "twijfel")
GRENS = 2.00          # Haiku, alle rondes samen
SCHATTING = 0.0001    # per check, iets boven de oordelen van #32.38 ($0,00008)
REGEL = ("een check van route A waarvan het veld van de bewering de conclusie van de redactie is, of twijfel, gelezen"
         " door Haiku en nagelezen (#32.66)")
REGEL_PUBLICATIE = ("een check uit de publicatiedatabase waarvan het veld van de bewering de conclusie van de redactie"
                    " is, of twijfel, gelezen door Haiku en nagelezen (#32.66, ronde publicatie)")

# Elke ronde haar eigen bestanden; route A is de ronde van 2026-11-10.
RONDES = {
    "route-a": {"map": MAP, "labels": LABELS, "grens": GRENS, "regel": REGEL},
    "publicatie": {"map": ta.WORTEL / "data" / "omgedraaid" / "publicatie",
                   "labels": ta.WORTEL / "docs" / "steekproeven" / "32.66-omgedraaid-publicatie.json",
                   "grens": 9.00, "regel": REGEL_PUBLICATIE},   # alle rondes samen; $3 tot ronde 3 erbij kwam
}
NIET_LEZEN = frozenset({"euvsdisinfo"})   # het veld is daar de desinformatie zelf (PLAN #32.66: 34 van 34 gelezen)

# Een ontkenning in de taal van de bewering: aan het begin, of achteraan waar het werkwoord achteraan staat. Een
# signaal voor de voormeting en de keuze van ronde 1, geen oordeel: "El COVID19 no es un virus" is een bewering.
_BEGIN = {
    "es": r"(no|ni|nunca|nadie|ning[uú]n[oa]?|nada|tampoco)\b|(es |resulta )?(falso|mentira|incierto) que"
          r"|no es (cierto|verdad) que",
    "pt": r"(n[ãa]o|nem|nunca|ningu[ée]m|nenhum[a]?|nada)\b|([ée] )?(falso|mentira) que|n[ãa]o [ée] verdade que",
    "gl": r"(non|nin)\b", "ca": r"(no|ni|cap)\b",
    "de": r"(nein|nicht|kein[e]?[nmrs]?|niemand|nie|nichts)\b|es (ist )?(falsch|stimmt nicht)",
    "fr": r"(non|ne|n'|n’|aucun[e]?|personne|jamais|rien|pas)\b|(il est |c'est |c’est )?faux (de dire )?que"
          r"|ce n.est pas",
    "it": r"(no|non|nessun[oa]?|mai|niente)\b|([èe] )?falso che",
    "nl": r"(nee|neen|geen|niet|niemand|nooit|niets)\b|het (is )?niet (waar|zo) dat|er (is|zijn) geen",
    "en": r"(no|not|never|nobody|none|nothing|neither)\b|(it is|it's|it’s) (false|not true|untrue) that"
          r"|there (is|are|was|were) no\b|false[:,]",
    "id": r"(tidak|bukan|tak|belum)\b", "ms": r"(tidak|bukan|tak|belum)\b", "tl": r"(hindi|walang)\b",
    "tr": r"(hay[ıi]r)\b", "pl": r"(nie|[żz]adn[aey]|nikt)\b", "ro": r"(nu|niciun|nicio)\b",
    "hr": r"(ne|nije|nema|nikad)\b", "bs": r"(ne|nije|nema)\b", "sr": r"(ne|nije|nema)\b", "sl": r"(ne|ni)\b",
    "ru": r"(нет|не|никто|ни|неправда)\b", "uk": r"(ні|не|ніхто)\b",
    "ar": r"(لا|لم|لن|ليس|ليست)\s", "fa": r"(نه|هیچ)\s", "he": r"(לא|אין)\s",
    "hi": r"(नहीं|ना)\s", "mr": r"(नाही)\s", "ne": r"(होइन|छैन)", "bn": r"(না|নয়)\s", "as": r"(নহয়|নাই)\s",
    "zh": r"(不|没有|沒有|并非|並非|无|無)",
}
_EIND = {
    "te": r"(కాదు|లేదు|లేవు)", "ta": r"(இல்லை|அல்ல)", "ml": r"(അല്ല|ഇല്ല)", "kn": r"(ಅಲ್ಲ|ಇಲ್ಲ)",
    "si": r"(නැත|නොවේ|නෑ)", "hi": r"(नहीं|नहीं है|नहीं हैं)", "mr": r"(नाही|नाहीत)", "bn": r"(নয়|না|নেই)",
    "as": r"(নহয়|নাই)", "ja": r"(ない|ません|ではない|なかった)", "ko": r"(않다|아니다|없다)", "gu": r"(નથી|નહીં)",
    "pa": r"(ਨਹੀਂ)", "ur": r"(نہیں)", "fa": r"(نیست|ندارد|نشد|نکرد)", "tr": r"(değil|değildir|yok|olmadı)",
}
_VORM_BEGIN = {t: re.compile(r"^\W*(" + p + ")", re.IGNORECASE) for t, p in _BEGIN.items()}
_VORM_EIND = {t: re.compile(p + r"[\s.!?।。۔]*$") for t, p in _EIND.items()}

_VRAAG_V1 = """The fact-checker {site} published a fact-check with the rating "{oordeel}". In the field for the \
claim they reviewed, they wrote the text below. Normally that field holds the claim as it circulated: what someone \
said, posted or shared, so that the rating applies to it. Sometimes the fact-checker put their own finding there \
instead, such as the headline of their article ("No, X did not say Y", "This photo does not show Z", "There is no \
evidence that ..."). Then the text says the opposite of the claim that was rated. Which is it?
- bewering: the claim as it circulated. Also when it contains a negation ("COVID-19 is not a virus", "Parliament held \
no minute of silence for the victims"), when it is a quote from a politician, or when it is a fake message or a scam.
- conclusie: the fact-checker's own finding or correction, which contradicts the claim they rated.
- twijfel: you cannot tell.
Do not judge whether the text is true. Judge only whose words these are.

Text: {claim}
Rating: {oordeel}"""

# v2: v1 miste op de ontwikkelset 3 van de 13 en markeerde 25 echte beweringen, omdat een ontkenning op een kop leek.
# Het oordeel zegt welke kant de redactie onwaar vond; met wat Haiku van het onderwerp weet, is te zien of de tekst die
# kant is of juist de correctie.
_VRAAG_V2 = """The fact-checker {site} gave the text below the rating "{oordeel}": they found it false or misleading. \
Normally the text is the claim that circulated. Sometimes, by mistake, the fact-checker put their own correction in \
that field instead: then the text states what the fact-checker found to be true, the opposite of the claim they \
debunked, and the rating contradicts the text.
- A mistake: "No, Nespresso has not given away coffee machines for Women's Day", rated False. The claim that \
circulated was that Nespresso gave them away; the text is the correction.
- Not a mistake: "COVID-19 is not a virus, it is an exosome", rated False. That is the claim that circulated, even \
though it contains a negation. The same holds for a quote from a politician, a fake message or a scam.
Use what you know about the topic and how the text is phrased. Answer:
- bewering: the text is what was debunked; the rating fits it.
- conclusie: the text is the correction; it says what the fact-checker found, so the rating contradicts it.
- twijfel: you cannot tell.

Text: {claim}
Rating: {oordeel}"""

VRAGEN = {"omgedraaid-v1": _VRAAG_V1, "omgedraaid-v2": _VRAAG_V2}

_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["waarom", "soort"],
           "properties": {"waarom": {"type": "string"}, "soort": {"type": "string", "enum": list(SOORTEN)}}}


class Weigering(RuntimeError):
    pass


def in_set(c: dict, oordeel_in_db: str | None) -> bool:
    """Alleen wat rood of oranje kan maken: een negatieve check van de drie Spaanse sites, zoals hij in de database staat.
    Bij *waar* zegt een conclusie hetzelfde als de bewering; *onbewezen* wordt nooit rood."""
    return c["site"] in SITES and oordeel_in_db in NEGATIEF


def verzoek(c: dict, versie: str = VERSIE) -> dict:
    from doublecheck.modellen import MODELLEN

    inhoud = VRAGEN[versie].format(site=c["site"], claim=c["bewering"], oordeel=c["oordeel"])
    return {"custom_id": f"om-{c.get('id') or ta.check_id(c)}", "params": {
        "model": MODELLEN["haiku"]["id"], "max_tokens": 1_000, "messages": [{"role": "user", "content": inhoud}],
        "output_config": {"effort": "low", "format": {"type": "json_schema", "schema": _SCHEMA}}}}


def lees_soort(tekst: str) -> str:
    """De soort uit het antwoord; wat niet te lezen is, is twijfel (dan lees ik het), nooit een bewering."""
    try:
        soort = json.loads(tekst).get("soort")
    except (json.JSONDecodeError, AttributeError):
        return "twijfel"
    return soort if soort in SOORTEN else "twijfel"


def samen(*per_versie: dict[str, str]) -> dict[str, str]:
    """Wat de versies samen zeggen: gemarkeerd als één versie markeert, een conclusie gaat voor twijfel; alleen wat
    elke versie las, telt."""
    ids = set.intersection(*(set(a) for a in per_versie)) if per_versie else set()
    uit = {}
    for i in ids:
        soorten = {a[i] for a in per_versie}
        uit[i] = "conclusie" if "conclusie" in soorten else "twijfel" if "twijfel" in soorten else "bewering"
    return uit


def weg(labels: dict[str, str]) -> set[str]:
    """Wat gelezen een conclusie of twijfel is."""
    return {i for i, label in labels.items() if label in ("conclusie", "twijfel")}


def te_lezen(antwoorden: dict[str, str], labels: dict[str, str]) -> list[str]:
    return sorted(i for i, s in antwoorden.items() if s != "bewering" and i not in labels)


def telling(antwoorden: dict[str, str], labels: dict[str, str], ontwikkel: list[str]) -> dict:
    """Weigert zolang een check die Haiku markeerde geen label heeft. Op de ontwikkelset (alles met de hand gelezen,
    vóór de eerste vraag) ook wat Haiku miste."""
    open_ = te_lezen(antwoorden, labels)
    if open_:
        raise Weigering(f"{len(open_)} gemarkeerde check(s) zonder label in het labelbestand")
    gemarkeerd = [i for i, s in antwoorden.items() if s != "bewering"]
    omgedraaid = [i for i in ontwikkel if labels.get(i) in ("conclusie", "twijfel")]
    gevonden = [i for i in omgedraaid if antwoorden.get(i, "bewering") != "bewering"]
    return {"gelezen": len(antwoorden), "door haiku gemarkeerd": len(gemarkeerd),
            "gemarkeerd en weg": sum(labels[i] in ("conclusie", "twijfel") for i in gemarkeerd),
            "gemarkeerd maar een bewering": sum(labels[i] == "bewering" for i in gemarkeerd),
            "ontwikkel": {"n": len(ontwikkel), "omgedraaid": len(omgedraaid), "gevonden": len(gevonden),
                          "gemist": sorted(set(omgedraaid) - set(gevonden))}}


def vorm(tekst: str, taal: str) -> str | None:
    """`begin` of `eind` als de bewering een ontkenning heeft in haar eigen taal, anders `None`."""
    t = (taal or "").split("-")[0].lower()
    if t in _VORM_BEGIN and _VORM_BEGIN[t].match(tekst or ""):
        return "begin"
    if t in _VORM_EIND and _VORM_EIND[t].search((tekst or "").strip()):
        return "eind"
    return None


def voormeting(rijen) -> dict[str, dict]:
    """Per redactie, alleen over de negatieve checks: hoeveel, hoeveel met een vorm (`begin`, `eind`), en de talen.
    `rijen`: dicts met redactie, oordeel (de klasse), tekst en taal."""
    uit: dict[str, dict] = {}
    for r in rijen:
        if r["oordeel"] not in NEGATIEF:
            continue
        d = uit.setdefault(r["redactie"], {"negatief": 0, "met vorm": 0, "begin": 0, "eind": 0, "talen": {}})
        v = vorm(r["tekst"], r["taal"])
        d["negatief"] += 1
        d["met vorm"] += v is not None
        if v:
            d[v] += 1
        d["talen"][r["taal"]] = d["talen"].get(r["taal"], 0) + 1
    return uit


def voor_lezer(check: dict) -> bool:
    """Een check uit de publicatiedatabase gaat naar Haiku als hij rood of oranje kan maken en niet van EUvsDisinfo is."""
    return check["oordeel"] in NEGATIEF and check["bron"] not in NIET_LEZEN


def tweede_ronde(labels: dict[str, str], redactie: dict[str, str], kosten: dict[str, float],
                 ruimte: float) -> tuple[list[str], list[str]]:
    """De redacties voor ronde 2: elke redactie met minstens één gelezen conclusie, de meeste eerst (bij gelijk op
    naam), zolang wat ze kost in de ruimte past; wat niet past, wordt overgeslagen en genoemd."""
    tel = collections.Counter(redactie[i] for i, label in labels.items() if label == "conclusie" and i in redactie)
    gekozen, overgeslagen, over = [], [], ruimte
    for naam, _ in sorted(tel.items(), key=lambda x: (-x[1], x[0])):
        if kosten.get(naam, 0.0) <= over:
            gekozen.append(naam)
            over -= kosten.get(naam, 0.0)
        else:
            overgeslagen.append(naam)
    return gekozen, overgeslagen


def derde_ronde(labels: dict[str, str], redactie: dict[str, str], heel: set[str], kosten: dict[str, float],
                ruimte: float) -> tuple[list[str], list[str]]:
    """Ronde 3: dezelfde regel als ronde 2, voor de redacties met een gelezen conclusie die ronde 2 niet heel las
    (`heel`). Een conclusie uit ronde 2 hoort bij een redactie die al heel gelezen is en telt dus niet."""
    return tweede_ronde({i: l for i, l in labels.items() if redactie.get(i) not in heel}, redactie, kosten, ruimte)


def rapportpad(map_: Path, datum: str) -> Path:
    """Het rapport van een weghaalronde; een tweede ronde op dezelfde dag krijgt een eigen bestand en het eerste blijft
    staan (`terugaanvoer.haal_dubbele_weg` weigert een rapport dat er al is)."""
    pad, n = Path(map_) / f"weg-{datum}.json", 1
    while pad.exists():
        n += 1
        pad = Path(map_) / f"weg-{datum}-{n}.json"
    return pad


WACHT = "wacht op de testset"   # gelezen weg, maar de bewering zit in de testset van de benchmark


def zonder_testset(rijen: list[dict], in_testset: set[str]) -> tuple[list[dict], list[dict]]:
    """Wat weg kan, en wat blijft omdat de bewering in de testset van de benchmark zit: die weghalen verandert de
    benchmark stil (`terugaanvoer.haal_dubbele_weg` weigert het), dus dat blijft staan en wordt genoemd."""
    return ([r for r in rijen if r["claim_id"] not in in_testset],
            [r for r in rijen if r["claim_id"] in in_testset])


def uit_dossier(doc: dict, verdwenen: set[str]) -> tuple[dict, list[dict]]:
    """Het dossier zonder de factchecks waarvan de pagina verdween; het origineel blijft onaangeroerd."""
    weg = [f for f in doc["factchecks"] if f["nummer"] in verdwenen]
    if not weg:
        return doc, []
    return dict(doc, factchecks=[f for f in doc["factchecks"] if f["nummer"] not in verdwenen]), weg


def _paden(ronde: str) -> dict:
    r = RONDES[ronde]
    return dict(r, set=r["map"] / "set.jsonl", antwoorden=r["map"] / "antwoorden.jsonl",
                batches=r["map"] / "batches.jsonl")


def _labelbestand(ronde: str = "route-a") -> dict:  # pragma: no cover - een bestand
    pad = RONDES[ronde]["labels"]
    return json.loads(pad.read_text(encoding="utf-8")) if pad.exists() else {"labels": {}, "sets": {}}


def _antwoorden(versie: str = "samen", ronde: str = "route-a") -> dict[str, str]:  # pragma: no cover - een bestand
    if versie == "samen":
        return samen(*(_antwoorden(v, ronde) for v in VERSIES))
    return {r["id"]: r["soort"] for r in ea._jsonl(_paden(ronde)["antwoorden"]) if r.get("versie") == versie}


def _set() -> None:  # pragma: no cover - de database en bestanden
    """De negatieve checks van de drie sites zoals ze in de database staan, met hun sleutel uit `checks.jsonl`."""
    from doublecheck.ingest import claim_id_for_text
    from doublecheck.storage import connect

    if SET.exists():
        raise Weigering(f"{SET} ligt al vast")
    conn = connect(str(ta.WORTEL / "doublecheck.db"))
    oordeel = {(c, u): v for c, u, v in conn.execute(
        "SELECT claim_id, url, verdict_normalized FROM factcheck WHERE source = ?", (ta.BRON,))}
    conn.close()
    rijen = []
    for c in ta.uniek(ea._jsonl(ta.MAP / "checks.jsonl")):
        cid = claim_id_for_text(ta.zonder_html(c["bewering"]))
        if in_set(c, oordeel.get((cid, c["adres"]))):
            rijen.append({"id": ta.check_id(c), "site": c["site"], "adres": c["adres"], "bewering": c["bewering"],
                          "oordeel": c["oordeel"], "categorie": oordeel[(cid, c["adres"])], "claim_id": cid})
    MAP.mkdir(parents=True, exist_ok=True)
    ea._schrijf(SET, rijen)
    print(f"{len(rijen)} checks: {dict(collections.Counter(r['site'] for r in rijen))}")


def _nieuwste_publicatie() -> Path:  # pragma: no cover - bestanden
    paden = sorted((ta.WORTEL / "data" / "publicatie").glob("*/publicatie.db"))
    if not paden:
        raise Weigering("geen publicatiedatabase in data/publicatie/")
    return paden[-1]


def _publicatie_rijen(pad: Path) -> list[dict]:  # pragma: no cover - de publicatiedatabase, alleen lezen
    import sqlite3

    conn = sqlite3.connect(f"file:{pad}?mode=ro", uri=True)
    kolommen = ("pagina", "redactie", "oordeel", "oordeel_eigen", "url", "bron", "tekst", "taal")
    rijen = [dict(zip(kolommen, r)) for r in conn.execute(
        "SELECT c.pagina, c.redactie, c.oordeel, c.oordeel_eigen, c.url, c.bron, p.bewering, p.taal"
        " FROM check_ c JOIN pagina p ON p.nummer = c.pagina")]
    leden = collections.defaultdict(set)
    for pagina, nummer in conn.execute("SELECT pagina, nummer FROM formulering"):
        leden[pagina].add(nummer)
    conn.close()
    for r in rijen:
        r["leden"] = leden[r["pagina"]] | {r["pagina"]}
    return rijen


def _voormeting(pad: Path | None) -> None:  # pragma: no cover - de publicatiedatabase, alleen lezen
    pad = pad or _nieuwste_publicatie()
    t = voormeting(_publicatie_rijen(pad))
    uit = _paden("publicatie")["map"] / "voormeting.json"
    uit.parent.mkdir(parents=True, exist_ok=True)
    uit.write_text(json.dumps({"publicatie": str(pad.relative_to(ta.WORTEL)), "per_redactie": t}, ensure_ascii=False,
                              indent=1) + "\n", encoding="utf-8")
    n = sum(d["negatief"] for d in t.values())
    v = sum(d["met vorm"] for d in t.values())
    print(f"{pad.parent.name}: {n} negatieve checks, {v} met een vorm ({v / n:.1%}), {len(t)} redacties")
    for naam, d in sorted(t.items(), key=lambda x: -x[1]["met vorm"])[:40]:
        talen = ", ".join(f"{k} {w}" for k, w in sorted(d["talen"].items(), key=lambda x: -x[1])[:2])
        print(f"  {d['met vorm']:5d} van {d['negatief']:6d} ({d['met vorm'] / d['negatief']:5.1%})"
              f"  begin {d['begin']:4d} eind {d['eind']:4d}  {naam}  [{talen}]")
    print(f"weggeschreven: {uit}")


def _set_publicatie(deel: int) -> None:  # pragma: no cover - de databases en bestanden
    """Ronde 1: elke negatieve check met een vorm. Ronde 2: alle andere negatieve checks van de redacties die
    `tweede_ronde` kiest; ronde 3 die van `derde_ronde`. Per check de bewering waar hij in het lab onder staat, met
    haar eigen taal."""
    import sqlite3

    from doublecheck.ingest import check_sleutel
    from doublecheck.publiceren import nummer

    paden = _paden("publicatie")
    bestaand = ea._jsonl(paden["set"])
    if any(r["deel"] == deel for r in bestaand):
        raise Weigering(f"ronde {deel} ligt al vast in {paden['set']}")
    pub = _nieuwste_publicatie()
    lab = sqlite3.connect(f"file:{ta.WORTEL / 'doublecheck.db'}?mode=ro", uri=True)
    claim = {cid: (tekst, taal) for cid, tekst, taal in lab.execute(
        "SELECT claim_id, canonical_text, language FROM claim")}
    per_url = collections.defaultdict(list)
    for cid, url in lab.execute("SELECT claim_id, url FROM factcheck"):
        per_url[url].append(cid)
    lab.close()
    kandidaten, gezien = [], {r["id"] for r in bestaand}
    for r in _publicatie_rijen(pub):
        if not voor_lezer(r):
            continue
        for cid in per_url.get(r["url"], []):
            if nummer(cid) not in r["leden"] or cid not in claim:
                continue
            tekst, taal = claim[cid]
            sleutel = check_sleutel(r["url"], tekst)
            if sleutel in gezien:
                continue
            gezien.add(sleutel)
            kandidaten.append({"id": sleutel, "site": r["redactie"], "adres": r["url"], "bewering": tekst,
                               "oordeel": r["oordeel_eigen"] or r["oordeel"], "categorie": r["oordeel"],
                               "claim_id": cid, "pagina": r["pagina"], "taal": taal or "und", "bron": r["bron"],
                               "vorm": vorm(tekst, taal or "")})
    if deel == 1:
        rijen = [dict(k, deel=1) for k in kandidaten if k["vorm"]]
    else:
        labels = _labelbestand("publicatie")["labels"]
        open_ = te_lezen(_antwoorden(ronde="publicatie"), labels)
        if open_:
            raise Weigering(f"{len(open_)} gemarkeerde check(s) van ronde 1 zonder label; eerst lezen")
        per_redactie = collections.defaultdict(list)
        for k in kandidaten:
            per_redactie[k["site"]].append(k)
        kosten = {naam: len(ks) * SCHATTING * len(VERSIES) for naam, ks in per_redactie.items()}
        uitgegeven = sum(b["schatting"] if b.get("werkelijk") is None else b["werkelijk"]
                         for b in ea._jsonl(paden["batches"]))
        redactie = {r["id"]: r["site"] for r in bestaand}
        if deel == 2:
            gekozen, overgeslagen = tweede_ronde(labels, redactie, kosten, paden["grens"] - uitgegeven)
        else:
            heel = {r["site"] for r in bestaand if r["deel"] == 2}
            gekozen, overgeslagen = derde_ronde(labels, redactie, heel, kosten, paden["grens"] - uitgegeven)
        rijen = [dict(k, deel=deel) for naam in gekozen for k in per_redactie[naam]]
        print(f"ronde {deel}: {gekozen}; past niet meer: {overgeslagen}")
    ea._schrijf(paden["set"], rijen)
    print(f"{pub.parent.name}: {len(rijen)} checks in ronde {deel}: "
          f"{dict(collections.Counter(r['site'] for r in rijen).most_common(15))}")


def _batch(sub: str, proef: int | None, annuleer: bool, ontwikkel: bool = False,
           versie: str = VERSIE, ronde: str = "route-a") -> None:  # pragma: no cover - de Batch API
    import time

    import anthropic

    from doublecheck.modellen import MODELLEN
    from doublecheck.varianten import laad_sleutel

    paden = _paden(ronde)
    laad_sleutel()
    client = anthropic.Anthropic()
    rijen = {r["id"]: r for r in ea._jsonl(paden["set"])}
    batches = ea._jsonl(paden["batches"])
    if sub == "indienen":
        klaar = set(_antwoorden(versie, ronde))
        open_ = {i for b in batches if b.get("werkelijk") is None and b["versie"] == versie for i in b["ids"]}
        alleen = set(_labelbestand(ronde)["sets"]["ontwikkel"]) if ontwikkel else set(rijen)
        werk = [r for i, r in rijen.items() if i in alleen and i not in klaar and i not in open_][:proef]
        geschat = len(werk) * SCHATTING
        uitgegeven = sum(b["schatting"] if b.get("werkelijk") is None else b["werkelijk"] for b in batches)
        if uitgegeven + geschat > paden["grens"]:
            raise Weigering(f"${uitgegeven + geschat:.2f} gaat over de grens van ${paden['grens']:.2f}")
        if not werk:
            raise Weigering("niets meer te lezen")
        batch = client.messages.batches.create(requests=[verzoek(r, versie) for r in werk])
        ea._schrijf(paden["batches"], [{"id": batch.id, "versie": versie, "schatting": round(geschat, 4),
                                        "ids": [r["id"] for r in werk]}])
        print(f"batch {batch.id}: {len(werk)} checks, geschat ${geschat:.3f}")
        return
    prijs = MODELLEN["haiku"]
    for b in batches:
        if b.get("werkelijk") is not None:
            continue
        status = client.messages.batches.retrieve(b["id"])
        if status.processing_status != "ended":
            if not annuleer:
                print(f"batch {b['id']}: {status.processing_status}, {status.request_counts}")
                continue
            client.messages.batches.cancel(b["id"])
            while client.messages.batches.retrieve(b["id"]).processing_status != "ended":
                time.sleep(5)
        kosten, nieuw = 0.0, []
        for r in client.messages.batches.results(b["id"]):
            if r.result.type != "succeeded":
                continue   # zonder antwoord: weer te doen bij het volgende indienen
            msg = r.result.message
            tekst = "".join(getattr(blok, "text", "") or "" for blok in msg.content)
            kosten += (msg.usage.input_tokens * prijs["in"] + msg.usage.output_tokens * prijs["uit"]) / 1e6
            try:
                waarom = json.loads(tekst).get("waarom", "")
            except (json.JSONDecodeError, AttributeError):
                waarom = ""
            nieuw.append({"id": r.custom_id.removeprefix("om-"), "soort": lees_soort(tekst), "waarom": waarom,
                          "versie": b["versie"]})
        ea._schrijf(paden["antwoorden"], nieuw)
        b["werkelijk"] = round(kosten, 4)
        print(f"batch {b['id']}: {len(nieuw)} van {len(b['ids'])} gelezen, ${kosten:.3f}")
    paden["batches"].write_text("".join(json.dumps(b) + "\n" for b in batches), encoding="utf-8")
    print(f"samen ${sum(b.get('werkelijk') or 0 for b in batches):.3f} van ${paden['grens']:.2f}")


def _lezen(versie: str = "samen", ronde: str = "route-a") -> None:  # pragma: no cover - bestanden
    paden = _paden(ronde)
    rijen = {r["id"]: r for r in ea._jsonl(paden["set"])}
    waarom = collections.defaultdict(str)
    for r in ea._jsonl(paden["antwoorden"]):
        if versie in ("samen", r.get("versie")) and r["soort"] != "bewering":
            waarom[r["id"]] += f"[{r['versie'][-2:]}] {r.get('waarom', '')[:150]} "
    antwoorden = _antwoorden(versie, ronde)
    for i in te_lezen(antwoorden, _labelbestand(ronde)["labels"]):
        r = rijen[i]
        print(f"[{i}] {r['site']} · {r.get('taal', '')} · {r['oordeel']} · HAIKU {antwoorden[i]}: {waarom[i][:320]}\n"
              f"  {r['bewering'][:300]}\n  {r['adres']}")


def _toepassen(uitvoeren: bool, ronde: str = "route-a") -> None:  # pragma: no cover - de database
    from datetime import date

    from doublecheck.storage import connect

    paden = _paden(ronde)
    labels = _labelbestand(ronde)["labels"]
    open_ = te_lezen(_antwoorden(ronde=ronde), labels)
    if open_:
        raise Weigering(f"{len(open_)} gemarkeerde check(s) zonder label; eerst lezen")
    rijen = [{"id": r["id"], "claim_id": r["claim_id"], "url": r["adres"], "site": r["site"], "oordeel": r["oordeel"],
              "tekst": r["bewering"], "label": labels[r["id"]]} for r in ea._jsonl(paden["set"]) if r["id"] in weg(labels)]
    conn = connect(str(ta.WORTEL / "doublecheck.db"))
    rijen = [r for r in rijen if conn.execute("SELECT 1 FROM factcheck WHERE claim_id = ? AND url = ?",
                                              (r["claim_id"], r["url"])).fetchone()]
    wacht: list[dict] = []
    if ronde == "publicatie":
        ids = sorted({r["claim_id"] for r in rijen})
        plekken = ",".join("?" * len(ids))
        in_testset = {i for (i,) in conn.execute(
            f"SELECT claim_id FROM testpair WHERE claim_id IN ({plekken})", ids)} | {
            p.removeprefix("hardste-buur:") for (p,) in conn.execute(
                f"SELECT provenance FROM testpair WHERE provenance IN ({plekken})",
                [f"hardste-buur:{i}" for i in ids])} if ids else set()
        rijen, wacht = zonder_testset(rijen, in_testset)
        print(f"blijft staan, de bewering zit in de testset van de benchmark: {len(wacht)} "
              f"{[(r['id'], r['site']) for r in wacht]}")
    print(f"weg: {len(rijen)} {dict(collections.Counter(r['label'] for r in rijen))} "
          f"{dict(collections.Counter(r['site'] for r in rijen).most_common(12))}")
    if not uitvoeren:
        conn.close()
        return
    print(ta.haal_dubbele_weg(conn, rijen, rapportpad(paden["map"], date.today().isoformat()), regel=paden["regel"]))
    if ronde == "publicatie":
        from doublecheck.ingest import WEGGEHAALD_PATH
        from doublecheck.publiceren import nummer

        WEGGEHAALD_PATH.write_text(json.dumps({
            "_meta": "Checks waarvan het veld van de bewering de conclusie van de redactie is, of twijfel, gelezen door"
                     " Haiku en nagelezen door Claude in docs/steekproeven/32.66-omgedraaid-publicatie.json (PLAN"
                     " #32.66). Sleutel: `ingest.check_sleutel` (adres en bewering). Elke import weigert ze."
                     " Geschreven door `python -m doublecheck.omgedraaid toepassen --ronde publicatie --uitvoeren`;"
                     " niet met de hand bewerken.",
            "checks": sorted(weg(labels) - {r["id"] for r in wacht})}, ensure_ascii=False, indent=1) + "\n",
            encoding="utf-8")
        d = _labelbestand(ronde)
        d["sets"][WACHT] = sorted(r["id"] for r in wacht)
        RONDES[ronde]["labels"].write_text(json.dumps(d, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        verdwenen = {nummer(r["claim_id"]) for r in rijen
                     if not conn.execute("SELECT 1 FROM claim WHERE claim_id = ?", (r["claim_id"],)).fetchone()}
        for pad in sorted((ta.WORTEL / "content" / "dossiers").glob("*/factchecks.json")):
            doc = json.loads(pad.read_text(encoding="utf-8"))
            nieuw, uit = uit_dossier(doc, verdwenen)
            if uit:
                pad.write_text(json.dumps(nieuw, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
                print(f"{pad.parent.name}: {len(uit)} factcheck(s) weg: {[f['nummer'] for f in uit]}")
        print(f"{len(verdwenen)} pagina's verdwijnen bij de volgende bouw; de uitgave is niet opnieuw gebouwd")
    conn.close()


def main() -> None:  # pragma: no cover - CLI
    import argparse

    parser = argparse.ArgumentParser(description="De conclusie in het veld van de bewering (PLAN #32.66)")
    parser.add_argument("stap", choices=("voormeting", "set", "indienen", "ophalen", "lezen", "tellen", "toepassen"))
    parser.add_argument("--ronde", choices=tuple(RONDES), default="route-a",
                        help="route-a (2026-11-10) of publicatie (2026-11-12)")
    parser.add_argument("--publicatie", type=Path, default=None, help="voormeting: standaard de nieuwste uitgave")
    parser.add_argument("--tweede", action="store_true", help="set --ronde publicatie: ronde 2, de hele redacties")
    parser.add_argument("--derde", action="store_true",
                        help="set --ronde publicatie: ronde 3, de redacties die in ronde 2 niet pasten")
    parser.add_argument("--proef", type=int, default=None)
    parser.add_argument("--annuleer", action="store_true")
    parser.add_argument("--ontwikkel", action="store_true", help="indienen: alleen de met de hand gelezen ontwikkelset")
    parser.add_argument("--versie", choices=tuple(VRAGEN) + ("samen",), default=None,
                        help="indienen: de vraag (standaard v2); lezen en tellen: standaard beide versies samen")
    parser.add_argument("--uitvoeren", action="store_true", help="toepassen: echt weghalen, na het rapport")
    args = parser.parse_args()
    if args.stap == "voormeting":
        _voormeting(args.publicatie)
    elif args.stap == "set":
        _set_publicatie(3 if args.derde else 2 if args.tweede else 1) if args.ronde == "publicatie" else _set()
    elif args.stap in ("indienen", "ophalen"):
        _batch(args.stap, args.proef, args.annuleer, args.ontwikkel, args.versie or VERSIE, args.ronde)
    elif args.stap == "lezen":
        _lezen(args.versie or "samen", args.ronde)
    elif args.stap == "toepassen":
        _toepassen(args.uitvoeren, args.ronde)
    else:
        d = _labelbestand(args.ronde)
        print(json.dumps(telling(_antwoorden(args.versie or "samen", args.ronde), d["labels"],
                                 d["sets"].get("ontwikkel", [])), ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
