"""Route A terug in de tijd (PLAN #32.38): de grote open factcheckers uit de VS en Europa in de database.

Zoals de proef van #32.19 (`eigenaanvoer`), maar zonder venster en zonder plafond per site: elk artikel uit de
sitemap die robots.txt noemt, per site één verzoek tegelijk en minstens 2 seconden ertussen (of de wachttijd die de
site vraagt), als FactizResearch, hervatbaar. Uit elk artikel alleen de ClaimReview; bewaard per check het adres, de
site, de taal, de bewering, het oordeel, de datum, de uitgever en of het adres al in de database staat. Nooit de pagina
of een beeld, en niets in de database: de import volgt pas na het nakijken en een besluit van de PO over de herkomst.

Eerst Snopes, Full Fact, Lead Stories en EFE Verifica; Maldita en Newtral pas na de beeldoogst van #32.35, die ook
hun artikelen ophaalt (per site één verzoek tegelijk).

    python -m doublecheck.terugaanvoer verken [--ronde eerste|tweede]
    python -m doublecheck.hittewacht -- python -m doublecheck.terugaanvoer ophalen [--ronde eerste|tweede]
    python -m doublecheck.terugaanvoer tellen
"""

from __future__ import annotations

import collections
import json
import re
from pathlib import Path
from urllib.parse import urlsplit

from doublecheck import eigenaanvoer as ea

WORTEL = Path(__file__).resolve().parent.parent
MAP = WORTEL / "data" / "aanvoer" / "terug"
EERSTE_RONDE = ("Snopes", "Full Fact", "Lead Stories", "EFE Verifica")   # PO 2026-11-03
NA_DE_BEELDOOGST = ("Maldita", "Newtral")
# B68 (PO 2026-11-09: "eens. start maar"): de factcheckers van de talen van V1
TALEN_V1 = ("Maldita", "Newtral", "AFP Factual", "AFP Faktencheck", "AFP Checamos", "AFP Factuel", "Correctiv",
            "dpa-Faktencheck", "Polígrafo", "Observador", "Knack")
# Verkend in #32.66: AFP Factuel (403), Le Monde (402, een licentie voor bots), Libération (403) en Les Surligneurs
# (geen ClaimReview) vallen af; franceinfo zet ClaimReview in ~40% van "vrai ou fake".
FRANS = ("franceinfo Vrai ou faux",)
RONDES = {"eerste": EERSTE_RONDE, "tweede": NA_DE_BEELDOOGST, "talen": TALEN_V1, "frans": FRANS}
MAX_SITEMAPS = 5000   # per site; een site met meer deelsitemaps wordt gemeld, niet stil afgekapt
MAX_DIEPTE = 3


def sites(namen: tuple[str, ...]) -> list[dict]:
    """De sites van `eigenaanvoer.SITES` met deze namen, in de volgorde daar."""
    return [s for s in ea.SITES if s["naam"] in namen]


def artikelen_uit(urls: list[tuple[str, str | None]], site: dict) -> list[tuple[str, str | None]]:
    """De artikelen van de site uit de adressen van een sitemap: alleen haar eigen host en het pad van de site, elk
    adres één keer (met de vroegste datum), de nieuwste eerst; de datum telt niet mee voor de keuze."""
    pad = re.compile(site["pad"]) if site.get("pad") else None
    host = site["host"].removeprefix("www.")
    uit: dict[str, str | None] = {}
    for loc, datum in urls:
        deel = urlsplit(loc)
        if (deel.hostname or "").removeprefix("www.") != host or (pad and not pad.search(deel.path)):
            continue
        datum = ea.datum_uit_adres(loc) or datum
        if loc not in uit or (datum and (uit[loc] is None or datum < uit[loc])):
            uit[loc] = datum
    return sorted(uit.items(), key=lambda x: x[1] or "", reverse=True)


def nog_te_doen(lijst: list[tuple[str, str | None]], gedaan: set[str]) -> list[str]:
    return [url for url, _ in lijst if url not in gedaan]


def uniek(checks: list[dict]) -> list[dict]:
    """Elke check één keer: een artikel van Full Fact draagt vaak meer beweringen onder hetzelfde adres."""
    return list({(c["adres"], c["bewering"]): c for c in checks}.values())


def check_van(review: dict, pagina: str, site: dict, bekend: set[str]) -> dict:
    """Wat we van één check bewaren (`eigenaanvoer.check_uit`), en of hij al in de database staat."""
    c = ea.check_uit(review, pagina, site)
    return {**c, "nieuw": ea.adres(c["adres"]) not in bekend and ea.adres(pagina) not in bekend}


# --- stap 3: de oordelen lezen -----------------------------------------------------------------------------------
#
# Eerst de regels van `verdicts` (hele labels, en de eigen lijst van de redactie); wat die onbekend laten, leest Haiku
# in één batch op openbare data. Wat de redactie zelf geen oordeel noemt (Snopes: "Scam", "Legend"), gaat nooit naar
# Haiku. Nalezen op een vaste steekproef; een fout is een andere kant, of een oordeel waar de redactie er geen gaf.

VERSIE = "oordeel-terug-v1"   # stap 3c: v1; v2 maakte meer fouten (stap 3b) en blijft voor de vergelijking
CATEGORIEEN = ("waar", "deels-waar", "misleidend", "onwaar", "onbewezen", "satire", "onbekend")
GRENS_OORDELEN = 2.00         # PO 2026-11-04
SCHATTING_OORDEEL = 0.00008   # Haiku per oordeel, de Duitse van §161 ($0,31 voor 3.907)
STEEKPROEF = {"Lead Stories": 50, "Full Fact": 40, "EFE Verifica": 10}
ZAAD = 3238
ZAAD_TOETS = 3239
ZAAD_KOP = 3240
N_KOPREGEL = 50
ZONDER_LEZER = frozenset({"Full Fact"})   # PO 2026-11-04: alleen de kopregel, de rest houdt onbekend
NIET_IMPORTEREN = frozenset({"Lead Stories"})   # B56: hun labels zeggen niet of iets klopt; blijft in de bestanden
LABELS = WORTEL / "docs" / "steekproeven" / "32.38-oordelen.json"
_KANTEN = {"onwaar": "rood", "misleidend": "rood", "waar": "groen", "deels-waar": "midden", "onbewezen": "onbewezen",
           "satire": "satire", "onbekend": "geen"}

_VRAAG_V1 = """The fact-checker {site} reviewed the claim below and gave the rating below. Which category does \
the rating express about the claim?
- onwaar: the claim is false (also made up, a fake, a hoax, a scam, an AI-generated or edited photo or video \
presented as real, a quote the person never said)
- misleidend: misleading, missing context, out of context, a real photo or video with a false caption or date
- deels-waar: partly true and partly false, mostly true, mostly false
- waar: true
- onbewezen: unproven, no evidence either way
- satire: the claim comes from satire or parody
- onbekend: the rating does not say which, or you are unsure between two categories
Judge only what the fact-checker wrote. Do not judge the claim yourself.

Claim: {claim}
Rating: {oordeel}"""

# v2 (#32.38, stap 3b): onze leesregels uit `verdicts.py` en de labels erbij, als regels op volgorde; geen "bij twijfel
# onbekend" meer, want de korte labels van Lead Stories noemen wat er mis is zonder een categorie.
_VRAAG_V2 = """The fact-checker {site} reviewed the claim below and gave the rating below. Which category does \
the rating express about the claim? Apply these rules in this order and take the first that fits:
1. satire: the claim comes from satire, parody or a joke.
2. onwaar: the rating says the claim is wrong: false, not true, incorrect, made up, fake, a hoax, a scam, \
AI-generated or edited media presented as real, a quote the person never said, wrong numbers. A short label that \
names what is wrong with the claim (such as "Bad Math", "Wrong Person", "Not Real") also means onwaar.
3. misleidend: the event, photo or video is real, but the claim gives it a wrong place, date, caption or meaning, \
or leaves out context that changes it.
4. deels-waar: one part of the claim is right and another part is wrong; mostly true; mostly false; true by one \
measure but not by another.
5. onbewezen: the rating only says there is no evidence, no record or no basis for the claim. If the rating also \
gives a fact that contradicts the claim, it is onwaar instead.
6. waar: the rating says the claim is correct, or gives the same fact or figure as the claim without correcting it.
7. onbekend: none of these; for example a warning, or a title that does not judge the claim.
Judge only what the fact-checker wrote. Do not judge the claim yourself.

Claim: {claim}
Rating: {oordeel}"""

VRAGEN = {"oordeel-terug-v1": _VRAAG_V1, "oordeel-terug-v2": _VRAAG_V2}

_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["waarom", "oordeel"],
           "properties": {"waarom": {"type": "string"}, "oordeel": {"type": "string", "enum": list(CATEGORIEEN)}}}


class Weigering(RuntimeError):
    pass


def _host(site_naam: str) -> str:
    return next(s["host"] for s in ea.SITES if s["naam"] == site_naam).removeprefix("www.")


def check_id(c: dict) -> str:
    """Eén check is één bewering onder één adres; het oordeel hoort niet bij de sleutel."""
    import hashlib

    return hashlib.sha1(f"{c['adres']}\n{c['bewering']}".encode()).hexdigest()[:16]


def custom_id(id_: str) -> str:
    return f"rt-{id_}"


def categorie_nu(c: dict) -> str:
    from doublecheck.verdicts import normalize_verdict

    return normalize_verdict(c["oordeel"], _host(c["site"]))


def naar_lezer(c: dict) -> bool:
    """Alleen wat de regels onbekend laten en waarvan de redactie niet zelf zegt dat het geen oordeel is."""
    from doublecheck.verdicts import geen_oordeel

    return c["site"] not in ZONDER_LEZER and bool((c["oordeel"] or "").strip()) and categorie_nu(c) == "onbekend" \
        and not geen_oordeel(c["oordeel"], _host(c["site"]))


def oordeelverzoek(c: dict, versie: str = VERSIE) -> dict:
    from doublecheck.modellen import MODELLEN

    inhoud = VRAGEN[versie].format(site=c["site"], claim=c["bewering"], oordeel=c["oordeel"])
    return {"custom_id": custom_id(check_id(c)), "params": {
        "model": MODELLEN["haiku"]["id"], "max_tokens": 1_000, "messages": [{"role": "user", "content": inhoud}],
        "output_config": {"effort": "low", "format": {"type": "json_schema", "schema": _SCHEMA}}}}


def lees_oordeel(tekst: str) -> str:
    """De categorie uit het antwoord; alles daarbuiten is onbekend, er wordt nooit geraden."""
    try:
        oordeel = json.loads(tekst).get("oordeel")
    except (json.JSONDecodeError, AttributeError):
        return "onbekend"
    return oordeel if oordeel in CATEGORIEEN else "onbekend"


def steekproef(rijen: list[dict], zaad: int = ZAAD) -> list[dict]:
    """Per site een vast aantal, onafhankelijk van de volgorde van binnenkomst, en daarna door elkaar."""
    import random

    uit = []
    for site, n in STEEKPROEF.items():
        van_site = sorted((r for r in rijen if r["site"] == site), key=lambda r: r["id"])
        random.Random(f"{zaad}-{site}").shuffle(van_site)
        uit += van_site[:n]
    random.Random(zaad).shuffle(uit)
    return uit


def toets(rijen: list[dict], ontwikkel: set[str]) -> list[dict]:
    """De toets van stap 3b: een vaste steekproef van dezelfde grootte, zonder wat al gelezen is om de vraag bij te
    stellen."""
    return steekproef([r for r in rijen if r["id"] not in ontwikkel], zaad=ZAAD_TOETS)


def kopregel_keuze(checks: list[dict], gelezen: set[str], n: int = N_KOPREGEL, zaad: int = ZAAD_KOP) -> list[dict]:
    """De checks van Full Fact die de kopregel een categorie geeft, zonder wat al gelezen is; een vaste keuze."""
    import random

    kandidaten = sorted(({**c, "id": check_id(c)} for c in checks
                         if c["site"] == "Full Fact" and categorie_nu(c) != "onbekend"), key=lambda c: c["id"])
    kandidaten = [c for c in kandidaten if c["id"] not in gelezen]
    random.Random(zaad).shuffle(kandidaten)
    return kandidaten[:n]


def eindcategorie(c: dict, v1: dict[str, dict]) -> tuple[str, str]:
    """De categorie die de import zou krijgen, en waar ze vandaan komt: de regels eerst, dan het antwoord van
    `oordeel-terug-v1` waar dat mag (stap 3c), anders geen."""
    nu = categorie_nu(c)
    if nu != "onbekend":
        return nu, "regel"
    antwoord = v1.get(check_id(c), {}).get("categorie", "onbekend") if naar_lezer(c) else "onbekend"
    if antwoord == "satire":   # B56: satire alleen als vaststaat dat het als grap bedoeld is
        antwoord = "onwaar"
    return (antwoord, "haiku") if antwoord != "onbekend" else ("onbekend", "geen")


N_NAKIJKEN, N_PO = 100, 50
ZAAD_NAKIJK = 3241
NAKIJK_LABELS = WORTEL / "docs" / "steekproeven" / "32.38-nakijken.json"
NAKIJK_PO = WORTEL / "docs" / "steekproeven" / "32.38-nakijken-po.json"


def nakijk_sets(checks: list[dict], gelezen: set[str], n: int = N_NAKIJKEN, zaad: int = ZAAD_NAKIJK) -> dict:
    """Stap 4: per taal een vaste keuze uit alle checks, zonder wat stap 3 al las; de PO leest de eerste helft van de
    Engelse, zodat twee mensen dezelfde checks zien."""
    import random

    uit = {}
    for taal in ("en", "es"):
        kandidaten = sorted({check_id(c) for c in checks if c.get("taal") == taal} - gelezen)
        random.Random(f"{zaad}-{taal}").shuffle(kandidaten)
        uit[f"nakijk-{taal}"] = kandidaten[:n]
    uit["nakijk-po"] = uit["nakijk-en"][:N_PO]
    return uit


ZAAD_NAKIJK2 = 3242


def tweede_toets(checks: list[dict], gelezen: set[str], n: int = N_NAKIJKEN) -> list[str]:
    """Stap 4b: 100 Engelse uit de sites die naar de import gaan (zonder `NIET_IMPORTEREN`), zonder alles wat al
    gelezen is; een vaste keuze, getrokken na de telling van B56."""
    return nakijk_sets([c for c in checks if c["site"] not in NIET_IMPORTEREN], gelezen, n, ZAAD_NAKIJK2)["nakijk-en"]


def po_keuzes_nu(po: dict[str, dict], getoond: dict[str, str], nu: dict[str, str]) -> dict[str, dict]:
    """De keuzes van de PO die nog gelden: een keuze over de categorie alleen als de pagina dezelfde categorie liet zien
    als die er nu is (na B56 veranderde de satire); de keuze over de bewering blijft altijd."""
    uit = {}
    for i, k in po.items():
        k = {**k}
        if getoond.get(i) != nu.get(i):
            k.pop("categorie", None)
        uit[i] = {a: b for a, b in k.items() if a in ("bewering", "categorie")}
    return uit


def telling_nakijken(ids: list[str], eind: dict[str, str], mijn: dict[str, dict], po: dict[str, dict]) -> dict:
    """Een check is fout als de bewering niet klopt of de categorie fout is, volgens mij of volgens de PO. Weigert
    zolang een check geen label van mij heeft."""
    open_ = [i for i in ids if i not in mijn]
    if open_:
        raise Weigering(f"{len(open_)} van de {len(ids)} nog zonder label in {NAKIJK_LABELS.name}; eerst lezen")
    tel = collections.Counter()
    for i in ids:
        e, m, p = eind[i], mijn[i]["categorie"], po.get(i, {})
        if e == m:
            soort = "gelijk"
        elif e == "onbekend":
            soort = "te voorzichtig"
        elif m != "onbekend" and kant(e) == kant(m):
            soort = "bijna"
        else:
            soort = "fout"
        if p.get("categorie") == "fout":
            soort = "fout"
        bewering_fout = mijn[i]["bewering"] == "fout" or p.get("bewering") == "fout"
        tel[soort] += 1
        tel["fout in de bewering"] += bewering_fout
        tel["fout in de categorie"] += soort == "fout"
        tel["fout samen"] += bewering_fout or soort == "fout"
        tel["door de PO gelezen"] += bool(p)
    n = len(ids)
    return {"gelezen": n, "gelijk": tel["gelijk"], "bijna": tel["bijna"], "te voorzichtig": tel["te voorzichtig"],
            "fout": tel["fout samen"], "fout in de bewering": tel["fout in de bewering"],
            "fout in de categorie": tel["fout in de categorie"], "door de PO gelezen": tel["door de PO gelezen"],
            "eis gehaald": tel["fout samen"] * 100 <= n}


# --- stap 5 en 6: de toelating en de import --------------------------------------------------------------------

# Maldita en Newtral sinds #32.66 (B68); franceinfo nog niet: drie labels zonder legenda, en vragen als bewering.
IMPORT_SITES = tuple(s for s in EERSTE_RONDE + NA_DE_BEELDOOGST if s not in NIET_IMPORTEREN)
BRON = "route-a"   # PO 2026-11-04: per check de herkomst route-a
BRONREGEL = dict(
    bron_id=BRON,
    naam="Route A: de ClaimReview op de sites van de redacties",
    soort="factchecker",
    licentie=("geen open licentie: alleen de feiten uit de ClaimReview die de redactie zelf publiceert (bewering, "
              "oordeel, datum, link); niet herverdeelbaar tot de PO over het uitgeven beslist (B13)"),
    attributietekst="Factcheck van de redactie, gelezen uit de ClaimReview op haar eigen site",
    url="https://schema.org/ClaimReview",
    herverdeelbaar=False,
)
_TAG = re.compile(r"</?[A-Za-z][^>]{0,40}>")
_CONCLUSIE = re.compile(r"(?i)^\s*(no es cierto que|es falso que|it is not true that|it's not true that)\b")
# Maldita zet soms de titel van het artikel in het veld van de bewering, met "[T]" ervoor (#32.66).
_TITEL = re.compile(r"^\s*\[T\]")


def zonder_html(tekst: str) -> str:
    """De bewering zonder de tags die oude artikelen van Snopes erin hebben ("<NOBR>War II</NOBR>")."""
    return " ".join(_TAG.sub("", tekst).split())


def is_conclusie(tekst: str) -> bool:
    """Staat in het veld van de bewering de conclusie van de redactie ("No es cierto que …")? Dan is het geen bewering."""
    return bool(_CONCLUSIE.match(tekst))


def artikel(url: str) -> str:
    """Eén sleutel per artikel: de host zonder www en het pad zonder slash aan het eind, in kleine letters; het schema
    en de query tellen niet mee."""
    deel = urlsplit(url.strip())
    return deel.netloc.lower().removeprefix("www.") + deel.path.rstrip("/").lower()


def _al_er(categorie: str, oordelen: list[str]) -> bool:
    """Staat het artikel er al (#32.66)? Ja, tenzij elke check die er is onbekend is en route A het oordeel weet."""
    return not (categorie != "onbekend" and all(o == "onbekend" for o in oordelen))


def aanwezige_artikelen(conn) -> dict[str, list[str]]:
    """Per artikel de oordelen van de checks die er al zijn uit een andere bron dan route A."""
    uit = collections.defaultdict(list)
    for url, oordeel in conn.execute("SELECT url, verdict_normalized FROM factcheck WHERE source <> ?", (BRON,)):
        uit[artikel(url)].append(oordeel)
    return dict(uit)


def naar_import(checks: list[dict], aanwezig: dict[str, list[str]] | None = None,
                weg_ids: set[str] | None = None) -> tuple[list, dict[str, int]]:
    """Elke check als één bewering met één check, zoals de feed; het oordeel gaat als label mee en de categorie volgt
    bij de import uit `verdicts.py`. Geeft ook wat wegbleef, per reden.

    Een artikel dat er al is uit een andere bron (`aanwezig`, van `aanwezige_artikelen`) komt er niet nog eens in
    (#32.66): bij Maldita en Newtral stond de bewering van route A in andere woorden, soms als de conclusie van de
    redactie, en dan beweerde de database het omgekeerde. Alleen als elke bestaande check onbekend is en route A het
    oordeel weet, gaat de check van route A mee. Ook een tweede bewering uit zo'n artikel blijft weg; dat kwam bij de
    660 dubbele niet voor.

    `weg_ids` zijn de checks die gelezen de conclusie van de redactie zijn, of twijfel (`omgedraaid.weg`)."""
    from doublecheck.factchecktools import RawClaim, RawFactcheck

    aanwezig, weg_ids = aanwezig or {}, weg_ids or set()
    claims, weg = [], collections.Counter()
    for c in checks:
        if c["site"] in NIET_IMPORTEREN:
            weg[f"{c['site']} (B56)"] += 1
        elif c["site"] not in IMPORT_SITES:
            weg["niet in deze ronde"] += 1
        elif is_conclusie(c["bewering"]):
            weg["de conclusie als bewering"] += 1
        elif _TITEL.match(c["bewering"]):
            weg["de titel van het artikel als bewering"] += 1
        elif check_id(c) in weg_ids:
            weg["de conclusie als bewering, gelezen"] += 1
        elif artikel(c["adres"]) in aanwezig and _al_er(c.get("categorie", "onbekend"), aanwezig[artikel(c["adres"])]):
            weg["het artikel stond er al"] += 1
        else:
            claims.append(RawClaim(text=zonder_html(c["bewering"]), claimant=None, claim_date=None, factchecks=(
                RawFactcheck(publisher=c["site"], publisher_site=_host(c["site"]), url=c["adres"],
                             review_date=c.get("datum"), verdict_original=c["oordeel"], language=c.get("taal")),)))
    return claims, dict(weg)


def dubbele_artikelen(conn) -> list[dict]:
    """De checks van route A bij een artikel dat er al was uit een andere bron, onder een andere bewering: wat
    `naar_import` nu weglaat, maar wat de import van 2026-11-10 er nog bij zette (#32.66). Twee beweringen uit één
    artikel die allebei van route A komen, blijven."""
    rijen = conn.execute("SELECT f.claim_id, f.url, f.source, f.verdict_normalized, f.publisher, c.canonical_text"
                         " FROM factcheck f JOIN claim c USING (claim_id)").fetchall()
    ander = collections.defaultdict(list)
    for cid, url, bron, oordeel, _, tekst in rijen:
        if bron != BRON:
            ander[artikel(url)].append({"claim_id": cid, "url": url, "oordeel": oordeel, "tekst": tekst})
    uit = []
    for cid, url, bron, oordeel, uitgever, tekst in rijen:
        er = [a for a in ander.get(artikel(url), []) if a["claim_id"] != cid] if bron == BRON else []
        if er and _al_er(oordeel, [a["oordeel"] for a in er]):
            uit.append({"claim_id": cid, "url": url, "uitgever": uitgever, "oordeel": oordeel, "tekst": tekst,
                        "al_er": er})
    return uit


_REGEL_DUBBEL = ("een check van route A bij een artikel dat er al was uit een andere bron, onder een andere bewering;"
                 " blijft als elke check die er was onbekend is en route A het oordeel weet (#32.66)")


def haal_dubbele_weg(conn, dubbel: list[dict], rapportpad, regel: str = _REGEL_DUBBEL) -> dict[str, int]:
    """Eerst het rapport met elke check die weggaat en wat er al stond, dan weg; een bewering die zo geen check meer
    heeft, gaat mee (met haar vingerafdrukken, via ON DELETE CASCADE). Weigert een bewering uit de testset, want dat
    zou de benchmark stil veranderen, en een rapport dat er al is."""
    from datetime import date

    ids = sorted({d["claim_id"] for d in dubbel})
    if ids:
        plekken = ",".join("?" * len(ids))
        n = conn.execute(f"SELECT count(*) FROM testpair WHERE claim_id IN ({plekken}) OR provenance IN ({plekken})",
                         ids + [f"hardste-buur:{i}" for i in ids]).fetchone()[0]
        if n:
            raise ValueError(f"{n} testpaar/paren verwijzen naar deze beweringen; eerst bewust uit de testset halen")
    rapportpad = Path(rapportpad)
    if rapportpad.exists():
        raise FileExistsError(f"{rapportpad} bestaat al; het rapport van een eerdere ronde blijft staan")
    rapportpad.parent.mkdir(parents=True, exist_ok=True)
    rapportpad.write_text(json.dumps({
        "datum": date.today().isoformat(),
        "regel": regel,
        "aantal": len(dubbel), "weg": dubbel}, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    with conn:
        conn.executemany("DELETE FROM factcheck WHERE claim_id = ? AND url = ?",
                         [(d["claim_id"], d["url"]) for d in dubbel])
        leeg = [i for i in ids if not conn.execute("SELECT 1 FROM factcheck WHERE claim_id = ?", (i,)).fetchone()]
        conn.executemany("DELETE FROM claim WHERE claim_id = ?", [(i,) for i in leeg])
    return {"checks": len(dubbel), "beweringen": len(leeg)}


def registreer_route_a(conn) -> None:
    """Vóór de eerste import staat route A in het bronregister (DR10)."""
    from doublecheck.attributie import registreer_bron

    registreer_bron(conn, **BRONREGEL)


def antwoorden(rijen: list[dict], versie: str) -> dict[str, dict]:
    """De antwoorden van één versie van de vraag; een andere versie telt nooit mee."""
    return {r["id"]: r for r in rijen if r.get("versie") == versie}


def kant(categorie: str) -> str:
    return _KANTEN[categorie]


def telling(rijen: list[dict], labels: dict[str, str], gelezen: list[dict] | None = None) -> dict:
    """Haiku tegen het nalezen. Weigert zolang een gelezen antwoord geen label heeft."""
    gelezen = steekproef(rijen) if gelezen is None else gelezen
    open_ = [r["id"] for r in gelezen if r["id"] not in labels]
    if open_:
        raise Weigering(f"{len(open_)} van de {len(gelezen)} nog zonder label in {LABELS.name}; eerst lezen")
    uit = collections.Counter()
    per_site = collections.defaultdict(collections.Counter)
    for r in gelezen:
        haiku, mens = r["categorie"], labels[r["id"]]
        if haiku == mens:
            soort = "gelijk"
        elif haiku == "onbekend":
            soort = "gemist"
        elif mens != "onbekend" and kant(haiku) == kant(mens):
            soort = "naburig"
        else:
            soort = "fout"
        uit[soort] += 1
        per_site[r["site"]][soort] += 1
    n = len(gelezen)
    return {"gelezen": n, **{k: uit[k] for k in ("gelijk", "naburig", "gemist", "fout")},
            "eis gehaald": uit["fout"] * 100 <= n, "per site": {s: dict(d) for s, d in per_site.items()}}


def binnen_grens(geschat: float, uitgegeven: float, grens: float = GRENS_OORDELEN) -> None:
    if uitgegeven + geschat > grens:
        raise Weigering(f"geweigerd: ${uitgegeven:.2f} al uitgegeven plus ${geschat:.2f} is meer dan ${grens:.2f}")


# --- het netwerk en de bestanden ---------------------------------------------------------------------------------

def _alle_artikelen(s) -> tuple[list[tuple[str, str | None]], dict]:  # pragma: no cover - netwerk
    """Elk artikel uit de sitemaps van de site, tot `MAX_DIEPTE` lagen diep."""
    gezien, urls, info = set(), [], {"sitemaps": 0, "afgekapt": False}
    rij = [(u, 0) for u in s.sitemaps]
    while rij:
        url, diepte = rij.pop(0)
        if url in gezien:
            continue
        if len(gezien) >= MAX_SITEMAPS:
            info["afgekapt"] = True
            break
        gezien.add(url)
        gevonden, kinderen = ea.sitemap(s.xml(url))
        urls += gevonden
        if diepte < MAX_DIEPTE:
            rij += [(k, diepte + 1) for k, _ in kinderen]
    info["sitemaps"] = len(gezien)
    return artikelen_uit(urls, s.site), info


def _lijstpad(site: dict) -> Path:
    """De hele naam, niet het eerste woord: Les Décodeurs en Les Surligneurs, of de vier AFP's, delen dat (#32.66)."""
    return MAP / f"lijst-{'-'.join(site['naam'].lower().split())}.json"


def _verken(namen: tuple[str, ...]) -> None:  # pragma: no cover - netwerk
    import concurrent.futures as cf

    def doe(site):
        s = ea._Site(site)
        s.lees_robots()
        lijst, info = _alle_artikelen(s)
        MAP.mkdir(parents=True, exist_ok=True)
        _lijstpad(site).write_text(json.dumps({"info": info, "artikelen": lijst}), encoding="utf-8")
        jaren = collections.Counter((d or "onbekend")[:4] for _, d in lijst)
        return {"site": site["naam"], "robots: sitemaps": s.sitemaps, "pauze": s.pauze, "artikelen": len(lijst),
                **info, "per jaar": dict(sorted(jaren.items())), "status": dict(collections.Counter(s.status))}

    with cf.ThreadPoolExecutor(len(namen)) as pool:
        uit = list(pool.map(doe, sites(namen)))
    MAP.mkdir(parents=True, exist_ok=True)
    (MAP / f"verken-{'-'.join(n.split()[0].lower() for n in namen)}.json").write_text(
        json.dumps(uit, ensure_ascii=False, indent=1), encoding="utf-8")
    for r in uit:
        uren = r["artikelen"] * (r["pauze"] + 0.5) / 3600
        print(f"{r['site']}: {r['artikelen']} artikelen uit {r['sitemaps']} sitemaps{' (afgekapt)' if r['afgekapt'] else ''}"
              f", pauze {r['pauze']} s, ~{uren:.1f} uur; status {r['status']}", flush=True)


def _ophalen(namen: tuple[str, ...]) -> None:  # pragma: no cover - netwerk
    import concurrent.futures as cf

    bekend = ea._bekend()
    gedaan = {r["pagina"] for r in ea._jsonl(MAP / "artikelen.jsonl")}

    def doe(site):
        s = ea._Site(site)
        s.lees_robots()
        if _lijstpad(site).exists():  # de lijst van het verkennen: de sitemaps niet nog eens opvragen
            d = json.loads(_lijstpad(site).read_text(encoding="utf-8"))
            lijst, info = [tuple(x) for x in d["artikelen"]], d["info"]
        else:
            lijst, info = _alle_artikelen(s)
        werk = nog_te_doen(lijst, gedaan)
        print(f"{site['naam']}: {len(lijst)} artikelen, {len(werk)} te doen", flush=True)
        tel = collections.Counter()
        for url in werk:
            if not s.mag(url):
                ea._schrijf(MAP / "artikelen.jsonl", [{"site": site["naam"], "pagina": url, "status": "robots"}])
                continue
            a = s.haal(url)
            status = a.status_code if a is not None else "fout"
            reviews = ea.claimreviews(a.text) if a is not None and a.status_code == 200 else []
            del a   # de pagina blijft in het geheugen en gaat nu weg
            checks = [c for c in (check_van(r, url, site, bekend) for r in reviews) if c["bewering"]]
            ea._schrijf(MAP / "checks.jsonl", checks)
            ea._schrijf(MAP / "artikelen.jsonl", [{"site": site["naam"], "pagina": url, "status": status,
                                                   "claimreviews": len(reviews), "checks": len(checks)}])
            tel["artikelen"] += 1
            tel["met ClaimReview"] += bool(reviews)
            tel["checks"] += len(checks)
            if tel["artikelen"] % 500 == 0:
                print(f"  {site['naam']}: {dict(tel)}", flush=True)
        samen = {"site": site["naam"], **info, "pauze": s.pauze, "status": dict(collections.Counter(s.status)), **tel}
        ea._schrijf(MAP / "sites.jsonl", [samen])
        print(f"{site['naam']} klaar: {dict(tel)}", flush=True)

    with cf.ThreadPoolExecutor(len(namen)) as pool:
        list(pool.map(doe, sites(namen)))


OORDELEN = MAP / "oordelen.jsonl"
OORDEELBATCHES = MAP / "oordeel-batches.jsonl"


def _te_lezen() -> list[dict]:  # pragma: no cover - een bestand
    return [{**c, "id": check_id(c)} for c in uniek(ea._jsonl(MAP / "checks.jsonl")) if naar_lezer(c)]


def _labelbestand() -> dict:  # pragma: no cover - een bestand
    return json.loads(LABELS.read_text(encoding="utf-8")) if LABELS.exists() else {"labels": {}}


def _labels() -> dict[str, str]:  # pragma: no cover - een bestand
    return {i: x["categorie"] for i, x in _labelbestand()["labels"].items()}


def _set(naam: str, rijen: list[dict]) -> list[str]:  # pragma: no cover - een bestand
    """De ids van een set: `ontwikkel` en `toets` staan vast in het labelbestand, `alles` is wat naar Haiku gaat."""
    if naam == "alles":
        return [r["id"] for r in rijen]
    sets = _labelbestand().get("sets", {})
    if naam not in sets:
        raise Weigering(f"de set {naam} ligt nog niet vast; eerst `oordelen set`")
    return sets[naam]


def _oordelen(sub: str, proef: int | None, annuleer: bool, versie: str = VERSIE, set_: str = "toets",
              blind: bool = False) -> None:  # pragma: no cover - de Batch API en bestanden
    import time

    rijen = _te_lezen()
    per_id = {r["id"]: r for r in rijen}
    gelezen = ea._jsonl(OORDELEN)
    batches = ea._jsonl(OORDEELBATCHES)
    if sub == "set":
        d = _labelbestand()
        if "toets" in d.get("sets", {}):
            raise Weigering("de toets ligt al vast")
        ontwikkel = sorted(d["labels"])     # de 50 van de proef met v1, gelezen vóór stap 3b
        d["sets"] = {"ontwikkel": ontwikkel, "toets": [r["id"] for r in toets(rijen, set(ontwikkel))]}
        LABELS.write_text(json.dumps(d, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"ontwikkel {len(d['sets']['ontwikkel'])}, toets {len(d['sets']['toets'])}")
        return
    if sub == "kopregel":     # stap 3c: 50 nieuwe van Full Fact die de kopregel beslist, vast getrokken, dan lezen
        d = _labelbestand()
        if "kopregel" not in d.get("sets", {}):
            keuze = kopregel_keuze(uniek(ea._jsonl(MAP / "checks.jsonl")), set(d["labels"]))
            d.setdefault("sets", {})["kopregel"] = [c["id"] for c in keuze]
            LABELS.write_text(json.dumps(d, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        ids = set(d["sets"]["kopregel"])
        for c in uniek(ea._jsonl(MAP / "checks.jsonl")):
            if check_id(c) in ids and check_id(c) not in d["labels"]:
                print(f"\n[{check_id(c)}] {c['site']}\n  BEWERING: {c['bewering'][:300]}\n  OORDEEL: {c['oordeel'][:500]}")
        return
    if sub in ("indienen", "ophalen"):
        import anthropic

        from doublecheck.modellen import MODELLEN
        from doublecheck.varianten import laad_sleutel

        laad_sleutel()
        client = anthropic.Anthropic()
    if sub == "indienen":
        klaar = set(antwoorden(gelezen, versie))
        open_ = {i for b in batches if b.get("werkelijk") is None and b.get("versie") == versie for i in b["ids"]}
        werk = [per_id[i] for i in _set(set_, rijen) if i in per_id and i not in klaar and i not in open_][:proef]
        geschat = len(werk) * SCHATTING_OORDEEL
        binnen_grens(geschat, sum(b["schatting"] if b.get("werkelijk") is None else b["werkelijk"] for b in batches))
        if not werk:
            raise Weigering("niets meer te lezen")
        batch = client.messages.batches.create(requests=[oordeelverzoek(r, versie) for r in werk])
        ea._schrijf(OORDEELBATCHES, [{"id": batch.id, "versie": versie, "set": set_, "schatting": round(geschat, 4),
                                      "ids": [r["id"] for r in werk]}])
        print(f"batch {batch.id}: {len(werk)} oordelen met {versie} op {set_}, geschat ${geschat:.3f}")
        return
    if sub == "ophalen":
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
                id_ = r.custom_id.removeprefix("rt-")
                nieuw.append({"id": id_, "site": per_id.get(id_, {}).get("site"), "categorie": lees_oordeel(tekst),
                              "waarom": waarom, "versie": b.get("versie", "oordeel-terug-v1")})
            ea._schrijf(OORDELEN, nieuw)
            b["werkelijk"] = round(kosten, 4)
            print(f"batch {b['id']}: {len(nieuw)} van {len(b['ids'])} gelezen met {b.get('versie')}, ${kosten:.3f}")
        OORDEELBATCHES.write_text("".join(json.dumps(b) + "\n" for b in batches), encoding="utf-8")
        print(f"samen ${sum(b.get('werkelijk') or 0 for b in batches):.3f} van ${GRENS_OORDELEN:.2f}")
        return
    labels = _labels()
    if sub == "lezen":
        antwoord = antwoorden(gelezen, versie)
        for i in _set(set_, rijen):
            c, r = per_id.get(i), antwoord.get(i)
            if c is None:
                continue
            if blind and i not in labels:     # om te labelen: alleen de bewering en het oordeel, niet wat Haiku zei
                print(f"\n[{i}] {c['site']}\n  BEWERING: {c['bewering'][:300]}\n  OORDEEL: {c['oordeel'][:500]}")
            elif not blind and r and r["categorie"] != labels.get(i):
                print(f"\n[{i}] {c['site']} · LABEL: {labels.get(i)} · HAIKU: {r['categorie']} — {r.get('waarom', '')}"
                      f"\n  BEWERING: {c['bewering'][:300]}\n  OORDEEL: {c['oordeel'][:500]}")
        return
    alle = uniek(ea._jsonl(MAP / "checks.jsonl"))
    per_site = collections.defaultdict(collections.Counter)
    from doublecheck.verdicts import geen_oordeel

    for c in alle:
        d = per_site[c["site"]]
        d["checks"] += 1
        if categorie_nu(c) != "onbekend":
            d["met de regels"] += 1
        elif geen_oordeel(c["oordeel"], _host(c["site"])):
            d["geen oordeel volgens de redactie"] += 1
        elif naar_lezer(c):
            d["naar Haiku"] += 1
    uit = {"per site": {s: dict(d) for s, d in sorted(per_site.items())},
           "kosten": round(sum(b.get("werkelijk") or 0 for b in batches), 3), "nalezen": {}}
    sets = _labelbestand().get("sets", {"ontwikkel": sorted(labels)})
    for v in VRAGEN:
        antwoord = antwoorden(gelezen, v)
        for naam, ids in sets.items():
            beantwoord = [antwoord[i] for i in ids if i in antwoord]
            if not beantwoord:
                continue
            try:
                t = telling(beantwoord, labels, gelezen=beantwoord)
                t["zonder antwoord"] = len(ids) - len(beantwoord)
            except Weigering as e:
                t = str(e)
            uit["nalezen"][f"{v} op {naam}"] = t
    if "kopregel" in sets:
        ids = set(sets["kopregel"])
        regel = [{"id": check_id(c), "site": c["site"], "categorie": categorie_nu(c)} for c in alle if check_id(c) in ids]
        try:
            uit["nalezen"]["de kopregel van Full Fact"] = telling(regel, labels, gelezen=regel)
        except Weigering as e:
            uit["nalezen"]["de kopregel van Full Fact"] = str(e)
    print(json.dumps(uit, ensure_ascii=False, indent=1))


_WOORD = {"onwaar": "Onwaar", "misleidend": "Misleidend", "deels-waar": "Deels waar", "waar": "Waar",
          "onbewezen": "Onbewezen", "satire": "Satire", "onbekend": "Geen categorie"}


def _nakijken(sub: str) -> None:  # pragma: no cover - op de bestanden
    """Stap 4: `sets` trekt de sets, `lezen` drukt mijn 200 blind af, `pagina` schrijft de 50 voor de PO, `tellen`
    telt per taal."""
    alle = uniek(ea._jsonl(MAP / "checks.jsonl"))
    per_id = {check_id(c): c for c in alle}
    d = json.loads(NAKIJK_LABELS.read_text(encoding="utf-8")) if NAKIJK_LABELS.exists() else None
    if sub == "sets":
        if d is not None:
            raise Weigering("de sets van stap 4 liggen al vast")
        gelezen = set(_labelbestand()["labels"])   # de 200 van stap 3
        d = {"toelichting": "", "sets": nakijk_sets(alle, gelezen), "labels": {}}
        NAKIJK_LABELS.write_text(json.dumps(d, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print({k: len(v) for k, v in d["sets"].items()})
        return
    if d is None:
        raise Weigering("eerst `nakijken sets`")
    if sub == "toets2":
        if "nakijk-en2" in d["sets"]:
            raise Weigering("de tweede toets ligt al vast")
        gelezen = set(_labelbestand()["labels"]) | set(d["labels"])   # stap 3 en de eerste 200 van stap 4
        d["sets"]["nakijk-en2"] = tweede_toets(alle, gelezen)
        NAKIJK_LABELS.write_text(json.dumps(d, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"nakijk-en2: {len(d['sets']['nakijk-en2'])}")
        return
    v1 = antwoorden(ea._jsonl(OORDELEN), "oordeel-terug-v1")
    if sub == "lezen":   # blind: de bewering en het oordeel, zonder onze categorie
        for i in d["sets"]["nakijk-en"] + d["sets"]["nakijk-es"] + d["sets"].get("nakijk-en2", []):
            if i not in d["labels"]:
                c = per_id[i]
                print(f"\n[{i}] {c['site']} · {c['adres']}\n  BEWERING: {c['bewering'][:400]}\n  OORDEEL: {c['oordeel'][:500]}")
        return
    if sub == "pagina":
        rijen = []
        for i in d["sets"]["nakijk-po"]:
            c = per_id[i]
            rijen.append({"id": i, "site": c["site"], "adres": c["adres"], "datum": c.get("datum"),
                          "bewering": c["bewering"], "oordeel": c["oordeel"],
                          "categorie": _WOORD[eindcategorie(c, v1)[0]]})
        uit = MAP / "nakijk-po.json"
        uit.write_text(json.dumps(rijen, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"{len(rijen)} checks in {uit}")
        return
    po = json.loads(NAKIJK_PO.read_text(encoding="utf-8"))["keuzes"] if NAKIJK_PO.exists() else {}
    eind = {i: eindcategorie(per_id[i], v1)[0]
            for i in d["sets"]["nakijk-en"] + d["sets"]["nakijk-es"] + d["sets"].get("nakijk-en2", [])}
    woord = {v: k for k, v in _WOORD.items()}
    getoond = {r["id"]: woord[r["categorie"]]   # wat de pagina van de PO liet zien
               for r in json.loads((MAP / "nakijk-po.json").read_text(encoding="utf-8"))}
    po = po_keuzes_nu(po, getoond, eind)   # B56: een keuze over een categorie die sindsdien veranderde, vervalt
    uit = {}
    sets = {"en": d["sets"]["nakijk-en"], "es": d["sets"]["nakijk-es"],
            "en zonder Lead Stories": [i for i in d["sets"]["nakijk-en"] if per_id[i]["site"] not in NIET_IMPORTEREN]}
    if "nakijk-en2" in d["sets"]:
        sets["en, de tweede toets"] = d["sets"]["nakijk-en2"]
    for taal, ids in sets.items():
        try:
            uit[taal] = telling_nakijken(ids, eind, d["labels"], po if taal.startswith("en") else {})
        except Weigering as e:
            uit[taal] = str(e)
    uit["PO gelezen"] = f"{len(po)} van {len(d['sets']['nakijk-po'])}"
    print(json.dumps(uit, ensure_ascii=False, indent=1))


def _importeren(in_kopie: bool) -> None:  # pragma: no cover - de database
    """Stap 6: de import van route A, zonder embedden (`reindex` doet dat daarna gebatcht). Met `in_kopie` in een kopie
    van de database die daarna weg is; zonder in de database zelf (PO 2026-11-04: "yes start maar"). Daarna nog
    `reindex` en `clustering --incrementeel`."""
    import shutil
    from datetime import datetime, timezone

    from doublecheck.bootstrap import herkomstrapport
    from doublecheck.ingest import import_claims
    from doublecheck.storage import connect, registreer_importrun

    gestart = datetime.now(timezone.utc).isoformat(timespec="seconds")
    doel = MAP / "proefimport.db" if in_kopie else WORTEL / "doublecheck.db"
    if in_kopie:
        shutil.copyfile(WORTEL / "doublecheck.db", doel)
    try:
        conn = connect(str(doel))
        from doublecheck import omgedraaid

        gelezen = json.loads(omgedraaid.LABELS.read_text(encoding="utf-8"))["labels"] if omgedraaid.LABELS.exists() else {}
        claims, weg = naar_import(uniek(ea._jsonl(MAP / "checks.jsonl")), aanwezige_artikelen(conn),
                                  omgedraaid.weg(gelezen))
        registreer_route_a(conn)
        r = import_claims(conn, claims, source=BRON, uitgesteld=True)
        if not in_kopie:
            registreer_importrun(conn, gestart_op=gestart, bron=f"{BRON}: data/aanvoer/terug/checks.jsonl", rapport=r,
                                 nieuwe_fingerprints=0)
        conn.commit()
        uit = {"waar": "kopie" if in_kopie else "doublecheck.db", "aangeboden": len(claims), "weggelaten": weg,
               "nieuwe beweringen": r.accepted_claims, "nieuwe checks": r.accepted_factchecks,
               "bewering bestond al": r.existing_claims, "check bestond al": r.duplicate_factchecks,
               "geweigerd": dict(collections.Counter(x.reason for x in r.refusals)),
               "per site en categorie": {f"{p} · {v}": n for p, v, n in conn.execute(
                   "SELECT publisher, verdict_normalized, count(*) FROM factcheck WHERE source = ? GROUP BY 1, 2",
                   (BRON,))}}
        print(json.dumps(uit, ensure_ascii=False, indent=1))
        print(herkomstrapport(conn).toelichting())
        if not in_kopie:
            (MAP / "import.json").write_text(json.dumps({**uit, "gestart": gestart}, ensure_ascii=False, indent=1) + "\n",
                                             encoding="utf-8")
        conn.close()
    finally:
        if in_kopie:
            for p in doel.parent.glob(doel.name + "*"):
                p.unlink()


def _dubbel(uitvoeren: bool) -> None:  # pragma: no cover - de database
    """De dubbele artikelen van de import van 2026-11-10 (#32.66): zonder `--uitvoeren` alleen tellen."""
    from datetime import date

    from doublecheck.storage import connect

    conn = connect(str(WORTEL / "doublecheck.db"))
    dubbel = dubbele_artikelen(conn)
    print(json.dumps({"dubbel": len(dubbel), "per uitgever": collections.Counter(d["uitgever"] for d in dubbel)},
                     ensure_ascii=False))
    if uitvoeren:
        print(haal_dubbele_weg(conn, dubbel, MAP / f"dubbel-{date.today().isoformat()}.json"))
    conn.close()


def _tellen() -> dict:  # pragma: no cover - op de bestanden
    checks = uniek(ea._jsonl(MAP / "checks.jsonl"))
    per_site = collections.defaultdict(collections.Counter)
    for c in checks:
        d = per_site[c["site"]]
        d["checks"] += 1
        d["nieuw"] += c["nieuw"]
        d["oordeel herkend"] += c["categorie"] not in (None, "", "onbekend")
    return {s: dict(d) for s, d in sorted(per_site.items())}


def main() -> None:  # pragma: no cover - CLI
    import argparse

    parser = argparse.ArgumentParser(description="Route A terug in de tijd (PLAN #32.38)")
    parser.add_argument("stap", choices=("verken", "ophalen", "tellen", "oordelen", "nakijken", "importeren", "dubbel"))
    parser.add_argument("sub", nargs="?", default="tellen",
                        choices=("set", "kopregel", "indienen", "ophalen", "lezen", "tellen", "sets", "pagina", "toets2"))
    parser.add_argument("--ronde", choices=tuple(RONDES), default="eerste")
    parser.add_argument("--proef", type=int, default=None)
    parser.add_argument("--annuleer", action="store_true", help="een batch die nog loopt annuleren en ophalen")
    parser.add_argument("--versie", choices=tuple(VRAGEN), default=VERSIE)
    parser.add_argument("--set", dest="set_", choices=("ontwikkel", "toets", "alles"), default="toets")
    parser.add_argument("--blind", action="store_true", help="lezen zonder het antwoord van Haiku, om te labelen")
    parser.add_argument("--in-kopie", dest="in_kopie", action="store_true", help="importeren in een kopie, die daarna weg is")
    parser.add_argument("--uitvoeren", action="store_true", help="dubbel: echt weghalen, na het rapport")
    args = parser.parse_args()
    if args.stap == "oordelen":
        _oordelen(args.sub, args.proef, args.annuleer, args.versie, args.set_, args.blind)
    elif args.stap == "nakijken":
        _nakijken(args.sub)
    elif args.stap == "importeren":
        _importeren(args.in_kopie)
    elif args.stap == "dubbel":
        _dubbel(args.uitvoeren)
    elif args.stap == "verken":
        _verken(RONDES[args.ronde])
    elif args.stap == "ophalen":
        _ophalen(RONDES[args.ronde])
    else:
        print(json.dumps(_tellen(), ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
