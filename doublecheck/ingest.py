"""Import van ruwe claims naar de index, met DR1-weigering (E2.S1).

Een factcheck zonder uitgever of URL wordt geweigerd; een claim zonder
enige geldige factcheck komt er niet in. Weigeringen zijn data, geen logregels:
ze reizen als ImportReport terug naar de aanroeper, omdat logging op
bibliotheekniveau bewust uitstaat (DR3-conventie).

Het claim_id is deterministisch afgeleid van de genormaliseerde claimtekst,
zodat het stabiel is en een herimport overleeft (domeinmodel).
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from doublecheck.config import load_config
from doublecheck.datums import geldige_review_datum
from doublecheck.embedding import fingerprint_text
from doublecheck.feed import API_GEBONDEN
from doublecheck.taal import corpus_taal, detecteer_taal
from doublecheck.taalgeschiktheid import taalgrond
from doublecheck.evidence import _host
from doublecheck.uitgeverkwaliteit import is_geweerd, is_geweerde_host
from doublecheck.factchecktools import RawClaim, RawFactcheck, search_claims
from doublecheck.storage import save_text_fingerprint
from doublecheck.verdicts import normalize_verdict

# Corpus-sweep voor de NL-dekking (taak 2.8): bekende NL/BE-factcheckuitgevers
# volledig enumereren, plus brede NL-zoektermen voor checks van andere
# uitgevers. Dit zijn corpuskeuzes, geen drempels — DR6 gaat hier niet over.
@dataclass(frozen=True)
class Markt:
    """Eén taalgebied: waar we halen en waarmee we zoeken (B14).

    Een markt is data en geen code, zodat uitrol een regel is in plaats van een
    functie. De uitgeverslijsten zijn getoetst tegen de API, niet gegokt:
    `aosfatos.org` leverde 100% Portugees en viel daarom uit de Spaanse markt
    (BENCHMARK.md §22a).
    """

    language_code: str
    publisher_sites: tuple[str, ...]
    queries: tuple[str, ...]


MARKTEN = {
    "nl": Markt(
        language_code="nl",
        publisher_sites=(
            "nieuwscheckers.nl",
            "factchecknederland.afp.com",
            "factcheck.vlaanderen",
            "knack.be",
            "nu.nl",
            "dpa-factchecking.com",
            "vrt.be",
        ),
        queries=(
            "vaccin", "corona", "klimaat", "verkiezingen", "stikstof", "immigratie",
            "5G", "Europese Unie", "Oekraïne", "energie", "boeren", "belasting",
        ),
    ),
    # Tien uitgevers over zes landen — Spanje, Argentinië, Colombia, Mexico,
    # Ecuador en Venezuela. Spreiding is hier geen luxe: DR7 telt oordelen van
    # ónafhankelijke uitgevers, en één land levert te veel onderlinge overlap.
    "es": Markt(
        language_code="es",
        publisher_sites=(
            "maldita.es",
            "newtral.es",
            "chequeado.com",
            "colombiacheck.com",
            "ecuadorchequea.com",
            "verificado.com.mx",
            "cotejo.info",
            "verificat.cat",
            "animalpolitico.com",
            "lasillavacia.com",
        ),
        queries=(
            "vacuna", "covid", "clima", "elecciones", "inmigración", "migrantes",
            "energía", "Ucrania", "impuestos", "inteligencia artificial",
            "Israel", "aborto",
        ),
    ),
}

# BCP-47 voor "onbepaald", wanneer de bron geen taal meegeeft.
_TAAL_ONBEPAALD = "und"


class ConfigFingerprinter:
    """Standaard-fingerprinter: dezelfde modelversie als de resolver (DR6)."""

    def __init__(self):
        self.model_version = load_config().model_versions.text_embedding

    def __call__(self, text: str):
        return fingerprint_text(text, self.model_version)


@dataclass(frozen=True)
class Refusal:
    reason: str
    claim_text: str | None
    publisher: str | None
    url: str | None


@dataclass(frozen=True)
class ImportReport:
    accepted_claims: int
    accepted_factchecks: int
    existing_claims: int
    duplicate_factchecks: int
    new_fingerprints: int
    refusals: tuple[Refusal, ...]


def claim_id_for_text(text: str) -> str:
    genormaliseerd = re.sub(r"\s+", " ", text.strip().casefold())
    return "gfc-" + hashlib.sha256(genormaliseerd.encode("utf-8")).hexdigest()[:16]


def check_sleutel(url: str, tekst: str) -> str:
    """Eén check: één adres onder één bewering. Hoofdletters en witruimte tellen niet mee, zoals bij het nummer van de
    bewering, zodat de sleutel een nieuwe import overleeft (PLAN #32.66)."""
    genormaliseerd = re.sub(r"\s+", " ", (tekst or "").strip().casefold())
    return hashlib.sha1(f"{(url or '').strip()}\n{genormaliseerd}".encode("utf-8")).hexdigest()[:16]


# De checks die gelezen de conclusie van de redactie in het veld van de bewering hebben, of twijfel (PLAN #32.66).
# Geschreven door `python -m doublecheck.omgedraaid toepassen --ronde publicatie --uitvoeren`; niet met de hand.
WEGGEHAALD_PATH = Path(__file__).resolve().parent / "omgedraaid_weg.json"


def weggehaalde_checks(path: Path = WEGGEHAALD_PATH) -> frozenset[str]:
    if not Path(path).exists():
        return frozenset()
    return frozenset(json.loads(Path(path).read_text(encoding="utf-8"))["checks"])


def _is_kale_url(text: str) -> bool:
    """Een claimtekst die niets anders is dan een URL bevat geen bewering.

    Zulke records zaten in het corpus (17 van 4.631) en zijn schadelijk: ze
    matchen op cijfers uit de URL en vervuilen de benchmark (PLAN.md #8.2).
    """
    zonder_urls = re.sub(r"https?://\S+", " ", text).strip()
    return not re.search(r"[^\W\d_]", zonder_urls)


# Labelzinnen die uitgevers in het claimveld zetten in plaats van de claim (#25.2).
_LABELZINNEN = frozenset({
    "fact check", "factcheck", "claim reviewed", "fake news", "false claim",
    "misleading claim",
})


def is_geen_bewering(text: str) -> bool:
    """Een claimtekst van één woord, of een labelzin, is geen bewering (#25.2).

    In het corpus: "google" (55 checks), "Claim:", "Disinfo", "Yes", "true",
    toetsenbordgeklop. Twee woorden is al te streng: "Fauci arrested." en
    "Shakira R.I.P." zijn echte claims. Schriften zonder woordspaties
    (Chinees, Japans, Thai) hebben één "woord" per zin; daar telt een
    ondergrens van vijf letters.
    """
    from doublecheck.testset import _zonder_woordspaties

    schoon = text.strip()
    if not schoon:
        return True
    if _zonder_woordspaties(schoon):
        # Eén "woord" per zin, dus tekens tellen: "地球是平的" (de aarde is plat)
        # is vijf tekens en een claim; "谷歌" (Google, SEO-spam) is er twee.
        return sum(teken.isalpha() for teken in schoon) < 5
    if schoon.casefold().strip(" :.!?\"'“”") in _LABELZINNEN:
        return True
    return len(schoon.split()) < 2


# Alleen echte webadressen mogen door. HTML-ontsnappen redt een `href` niet:
# `javascript:` draait ook keurig ge-escaped (#17.5).
_WEBADRES = re.compile(r"https?://", re.IGNORECASE)


def _weigergrond(check: RawFactcheck) -> str | None:
    if not check.publisher:
        return "geen_uitgever"
    # Uitgeversnamen met opmaaktekens zijn geen uitgeversnamen. Het corpus
    # bevat zeven scriptpayloads die iemand met een scanner in andermans
    # ClaimReview-markup heeft gezet (§47). Wij ontsnappen ze wel, maar het
    # protocol vertelt derden deze velden te consumeren — dan hoort de rem bij
    # de import te zitten en niet bij elke afnemer.
    if "<" in check.publisher or ">" in check.publisher:
        return "onveilige_uitgeversnaam"
    # Markup die geen factcheck is. Iedereen mag ClaimReview publiceren en
    # niemand controleert het: `Stancu Print` levert claims als
    # "Google,Yandex,Bing", `FactStream` levert testdata (#17.1, §43b).
    if is_geweerd(check.publisher):
        return "geweerde_uitgever"
    if not check.url:
        return "geen_url"
    if not _WEBADRES.match(check.url.strip()):
        return "onveilige_url"
    # Een host vol proefinvoer, onder wisselende namen (#25.19 b).
    if is_geweerde_host(check.url):
        return "geweerde_host"
    # Géén datum-eis meer. Bij de omzetting naar de CC BY-bron bleek 10,3% van
    # de records geen `datePublished` te dragen — 10.193 claims (BENCHMARK.md
    # §36a). Een factcheck zonder datum is nog steeds een factcheck, met een
    # aanwijsbare uitgever en URL. De datum wordt gerapporteerd als hij bekend
    # is en anders expliciet als onbekend, wat eerlijker is dan weigeren én dan
    # er een verzinnen (DR1 aangepast, PO 2026-08-30).
    return None


def import_claims(
    conn: sqlite3.Connection,
    raw_claims: Iterable[RawClaim],
    *,
    source: str,
    fingerprinter=None,
    uitgesteld: bool = False,
    weg: frozenset[str] | None = None,
) -> ImportReport:
    """`source` is verplicht, niet uit strengheid maar omdat een herkomstloze
    import precies de fout is die bij het vrijgeven onopgemerkt blijft (#14.5,
    15.3). De Fact Check Tools API mag niet mee in een publieke uitgave, de
    CC BY-feed wel — en dat verschil moet in de opslag staan, niet in een hoofd.

    `weg` zijn de sleutels (`check_sleutel`) van checks die nooit meer binnenkomen; zonder de lijst die
    `omgedraaid` na het nalezen schreef (PLAN #32.66). Elk importpad komt hier langs, dus ook de feed en EUvsDisinfo."""
    weg = weggehaalde_checks() if weg is None else weg
    # `uitgesteld=True` slaat het embedden over: bij bulkimport kost stuk voor
    # stuk embedden 28 s per duizend claims, en `doublecheck.reindex` doet het
    # daarna gebatcht (#14.4). De index is dan tijdelijk onvolledig — de
    # DR6-guard weigert netjes tot het herindexeren gedaan is.
    if fingerprinter is None and not uitgesteld:
        fingerprinter = ConfigFingerprinter()

    # De taalpoort is modelgebonden; hem hier ophalen laat de DR6-guard in
    # `mag_in_de_index` één keer vuren in plaats van per claim.
    _taalmodel = load_config().model_versions.text_embedding

    refusals: list[Refusal] = []
    accepted_claims = 0
    accepted_factchecks = 0
    existing_claims = 0
    duplicate_factchecks = 0
    new_fingerprints = 0

    for raw in raw_claims:
        if not raw.text or not raw.text.strip():
            refusals.append(Refusal("geen_tekst", raw.text, None, None))
            continue
        if _is_kale_url(raw.text) or is_geen_bewering(raw.text):
            refusals.append(Refusal("geen_bewering", raw.text, None, None))
            continue

        # Talen die het model niet uit elkaar kan houden horen niet in de index:
        # daar is 71% van de artefacten een zelfverzekerde match op een
        # willekeurige andere claim (#16.1, BENCHMARK.md §39).
        #
        # Hier beslist `corpus_taal` en niet het uitgeverslabel: dit is een
        # corpuskeuze, en een verkeerd gelabelde claim mag er niet langs glippen.
        gemeld = next(
            (c.language for c in raw.factchecks if c.language), _TAAL_ONBEPAALD
        )
        # Witte lijst, geen zwarte (B14 aangescherpt 2026-08-31): een taal moet
        # gemeten en geslaagd zijn om binnen te komen. Ongemeten is niet
        # hetzelfde als goed — de faalvorm uit §39 valt per constructie buiten
        # elke benchmark, dus hem laten opvallen aan het cijfer werkt niet.
        grond_taal = taalgrond(corpus_taal(raw.text) or gemeld, _taalmodel)
        if grond_taal is not None:
            refusals.append(Refusal(grond_taal, raw.text, None, None))
            continue

        geldig: list[RawFactcheck] = []
        for check in raw.factchecks:
            grond = _weigergrond(check)
            if grond is None and weg and check_sleutel(check.url, raw.text) in weg:
                # de conclusie van de redactie in het veld van de bewering: dan beweert de database het omgekeerde
                grond = "conclusie_als_bewering"
            if grond is None:
                geldig.append(check)
            else:
                refusals.append(Refusal(grond, raw.text, check.publisher, check.url))
        if not geldig:
            refusals.append(Refusal("geen_geldige_factchecks", raw.text, None, None))
            continue

        # Herimport dupliceert niet maar vult aan: een bestaande claim krijgt
        # alleen factchecks erbij die hij nog niet had (zelfde claim + URL =
        # dezelfde check). Dit dekt ook dubbelen bínnen één batch.
        claim_id = claim_id_for_text(raw.text)
        bestaat = conn.execute(
            "SELECT 1 FROM claim WHERE claim_id = ?", (claim_id,)
        ).fetchone()
        if bestaat:
            existing_claims += 1
        else:
            taal = next((c.language for c in geldig if c.language), _TAAL_ONBEPAALD)
            conn.execute(
                # `language` is onze beste inschatting, `language_reported` de
                # bewering van de uitgever. Die twee lopen uiteen (#12.6): van de
                # 57 claims die als `en` binnenkwamen waren er 6 werkelijk Engels.
                "INSERT INTO claim (claim_id, canonical_text, language,"
                " language_reported) VALUES (?, ?, ?, ?)",
                (claim_id, raw.text, detecteer_taal(raw.text) or taal, taal),
            )
            accepted_claims += 1

        # E2.S3-AC1: elke geïndexeerde claim heeft een fingerprint met de
        # resolver-modelversie. Herimport embedt niet opnieuw; na een
        # modelwissel vult dit de index aan met de nieuwe versie (naast de
        # oude), zodat herindexeren gewoon "importeer opnieuw" is.
        heeft_fingerprint = uitgesteld or conn.execute(
            "SELECT 1 FROM fingerprint WHERE claim_id = ? AND kind = 'text'"
            " AND model_version = ?",
            (claim_id, fingerprinter.model_version),
        ).fetchone()
        if not heeft_fingerprint:
            canoniek = conn.execute(
                "SELECT canonical_text FROM claim WHERE claim_id = ?", (claim_id,)
            ).fetchone()["canonical_text"]
            save_text_fingerprint(conn, claim_id, fingerprinter(canoniek))
            new_fingerprints += 1

        for check in geldig:
            al_bekend = conn.execute(
                "SELECT 1 FROM factcheck WHERE claim_id = ? AND url = ?",
                (claim_id, check.url),
            ).fetchone()
            if al_bekend:
                duplicate_factchecks += 1
                continue
            conn.execute(
                "INSERT INTO factcheck (claim_id, publisher, verdict_normalized,"
                " verdict_original, url, review_date, language, source)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    claim_id,
                    # Spaties aan de rand horen niet bij een naam; 2.172
                    # factchecks droegen ze en telden daardoor als een aparte
                    # uitgever (#17.5).
                    re.sub(r"\s+", " ", check.publisher).strip(),
                    normalize_verdict(check.verdict_original, host=_host(check.url)),
                    check.verdict_original or "",
                    check.url,
                    # Ongeldig wordt leeg, nooit gerepareerd (#21.4, §58); dit
                    # is de enige INSERT, dus feed- én API-import dragen de
                    # regel zonder eigen kopie.
                    geldige_review_datum(check.review_date),
                    check.language or _TAAL_ONBEPAALD,
                    source,
                ),
            )
            accepted_factchecks += 1

    conn.commit()
    return ImportReport(
        accepted_claims=accepted_claims,
        accepted_factchecks=accepted_factchecks,
        existing_claims=existing_claims,
        duplicate_factchecks=duplicate_factchecks,
        new_fingerprints=new_fingerprints,
        refusals=tuple(refusals),
    )


def sweep(conn: sqlite3.Connection, api_key: str, markt: str = "nl") -> ImportReport:
    """Draait de corpussweep voor één markt: uitgeverssites volledig, termen breed."""
    definitie = MARKTEN[markt]
    fingerprinter = ConfigFingerprinter()
    totaal = ImportReport(0, 0, 0, 0, 0, ())

    def _voeg_toe(bron: str, claims) -> None:
        nonlocal totaal
        rapport = import_claims(conn, claims, fingerprinter=fingerprinter,
                                source=API_GEBONDEN)
        totaal = ImportReport(
            totaal.accepted_claims + rapport.accepted_claims,
            totaal.accepted_factchecks + rapport.accepted_factchecks,
            totaal.existing_claims + rapport.existing_claims,
            totaal.duplicate_factchecks + rapport.duplicate_factchecks,
            totaal.new_fingerprints + rapport.new_fingerprints,
            totaal.refusals + rapport.refusals,
        )
        print(f"  {bron}: {len(claims)} opgehaald, {rapport.accepted_claims} nieuw,"
              f" {len(rapport.refusals)} geweigerd")

    for site in definitie.publisher_sites:
        _voeg_toe(site, search_claims(
            api_key=api_key, review_publisher_site_filter=site, max_pages=30))
    for term in definitie.queries:
        _voeg_toe(f"query {term!r}", search_claims(
            term, api_key=api_key, language_code=definitie.language_code, max_pages=5))
    return totaal


def main() -> None:
    import argparse
    import os

    from doublecheck.storage import connect, init_schema

    parser = argparse.ArgumentParser(description="Doublecheck corpus-import")
    parser.add_argument("--db", default="doublecheck.db")
    parser.add_argument("--markt", default="nl", choices=sorted(MARKTEN),
                        help="taalgebied om te importeren (B14)")
    args = parser.parse_args()

    api_key = os.environ.get("GOOGLE_FACTCHECK_API_KEY", "")
    if not api_key:
        raise SystemExit("GOOGLE_FACTCHECK_API_KEY ontbreekt (zet hem in .env)")

    conn = connect(args.db)
    init_schema(conn)
    print(f"sweep {args.markt!r} naar {args.db}:")
    rapport = sweep(conn, api_key, markt=args.markt)
    print(f"\ntotaal: {rapport.accepted_claims} nieuwe claims,"
          f" {rapport.accepted_factchecks} nieuwe factchecks,"
          f" {rapport.new_fingerprints} nieuwe fingerprints,"
          f" {rapport.existing_claims} al bekend,"
          f" {rapport.duplicate_factchecks} dubbele checks,"
          f" {len(rapport.refusals)} weigeringen")
    conn.close()


if __name__ == "__main__":
    main()
