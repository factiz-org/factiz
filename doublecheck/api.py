"""`POST /resolve` — één endpoint, één categorie per respons (E5.S1).

Het antwoordobject heeft `category` als verplicht enum-veld: er is geen
respons construeerbaar zonder (kritiek AC E5.S1, DR5). Het verzoekschema
weigert onbekende velden, dus een aanroeper kán niet eens om een match
vragen (DR4). Artefactinhoud wordt nergens gelogd of bewaard (DR3): alleen
de fingerprint raakt de database.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import sqlite3
from datetime import date
from typing import Iterator

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from PIL import UnidentifiedImageError
from PIL.Image import DecompressionBombError
from pydantic import BaseModel, ConfigDict, ValidationError, model_serializer

from doublecheck.attributie import attributies_voor
from doublecheck.bonnetjes import links_voor
from doublecheck.categorize import Category, categorize, reden_voor_none
from doublecheck.config import Config, load_config
from doublecheck.embedding import fingerprint_text, fingerprint_texts
from doublecheck.evidence import EvidenceState, build_evidence
from doublecheck.image_fingerprint import (
    TeGroteAfbeelding,
    fingerprint_image,
    fingerprint_van_hex,
)
from doublecheck.ocr import extract_text
from doublecheck.relation import contradicts
from doublecheck.taal import zijn_verschillende_talen
from doublecheck.retention import sweep_expired_artifacts
from doublecheck.search import (
    ModelVersionMismatchError,
    ensure_index_matches_version,
    ensure_variants_match_version,
    search_image,
    variant_sets,
)
from doublecheck import artikel, artikellezer, feitenlaag, rechter, vraagvorm, zinnen
from doublecheck.dispute import (
    DeletionKeyRejected,
    DisputeNotFound,
    delete_artifact,
    record_dispute,
)
from doublecheck.source import observe_sources
from doublecheck.ratelimit import RateLimiter, RateLimitMiddleware
from doublecheck.storage import connect, init_schema
from doublecheck.webui import PAGINA

# Bitbreedte per beeldschema, voor het ontdekkingsdocument (§3).
IMAGE_BITS = {"pdq-256-v1": 256, "phash-256-v1": 256, "phash-64-v1": 64}

# Technische invoerlimieten (geen matchdrempels; DR6 gaat hier niet over).
MAX_TEXT_LENGTH = 10_000
MAX_IMAGE_BYTES = 8 * 1024 * 1024

def _db_pad() -> str:
    return os.environ.get("DOUBLECHECK_DB", "doublecheck.db")


def _ruim_op(pad: str) -> int:
    """Dwingt de bewaartermijn af; telt alleen, logt nooit inhoud (DR3)."""
    conn = connect(pad)
    try:
        init_schema(conn)
        return sweep_expired_artifacts(conn)
    finally:
        conn.close()


async def _sweep_lus(pad: str, interval_seconden: float, na_ronde=None) -> None:
    """Blijft opruimen zolang de applicatie draait.

    Een server die maandenlang doorloopt zou met alleen een opstart-sweep de
    bewaartermijn uit B11 alsnog overschrijden.
    """
    while True:
        await asyncio.sleep(interval_seconden)
        aantal = await asyncio.to_thread(_ruim_op, pad)
        if na_ronde is not None:
            na_ronde(aantal)


WARMTEKST = "Factiz is warming up."


def _warm_op(pad: str) -> None:
    """Het tekstmodel, de index en de rechter van kring 1 vóór de eerste vraag laden (#32.10b): anders wacht de
    eerste controle ~45 s. Eerst een vaste zin (die niets vindt), dan de tekst van een claim uit de index (die het
    pad van een vondst neemt, met de rechter). Geen bericht van iemand."""
    from doublecheck.storage import connect

    conn = connect(pad)
    try:
        config = load_config()
        los_op(conn, config, WARMTEKST, None, None)
        rij = conn.execute("SELECT c.canonical_text FROM claim c JOIN fingerprint f ON f.claim_id = c.claim_id "
                           "LIMIT 1").fetchone()
        if rij and rij[0]:
            los_op(conn, config, rij[0], None, None)
    finally:
        conn.close()


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    """Bewaartermijn afdwingen bij opstart én periodiek (E6.S3-AC3, B11); met de controle aan ook het tekstmodel
    laden, zodat de eerste controle niet wacht (#32.10b)."""
    pad = _db_pad()
    config = load_config()
    interval = config.retention.sweep_interval_hours * 3600
    _ruim_op(pad)
    if config.berichtcontrole.aan:
        await asyncio.to_thread(_warm_op, pad)
    app.state.sweep_taak = asyncio.create_task(_sweep_lus(pad, interval))
    try:
        yield
    finally:
        app.state.sweep_taak.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await app.state.sweep_taak


app = FastAPI(title="Doublecheck", lifespan=lifespan)

# Rate-limiting bij het opbouwen van de app, niet per verzoek: de grens is
# statische config (DR6). In de test-suite zet `conftest.py` deze uit, zodat een
# testlus die veel verzoeken vuurt niet tript; productie draait hem aan (#20.2).
_ratelimit = load_config().ratelimit
limiter = RateLimiter(
    requests_per_minute=_ratelimit.requests_per_minute,
    burst=_ratelimit.burst,
    enabled=_ratelimit.enabled,
)
app.add_middleware(RateLimitMiddleware, limiter=limiter)


def get_conn() -> Iterator[sqlite3.Connection]:
    conn = connect(os.environ.get("DOUBLECHECK_DB", "doublecheck.db"))
    init_schema(conn)
    try:
        yield conn
    finally:
        conn.close()


def get_config() -> Config:
    return load_config()


@app.get("/", response_class=HTMLResponse)
def testinterface(config: Config = Depends(get_config)) -> str:
    """Publieksdemo (E5.S2 → #22.4); bewaartermijn komt uit config (DR6)."""
    return PAGINA.replace("__BEWAARTERMIJN__", str(config.retention.artifact_days))


@app.get("/numbers", response_class=HTMLResponse)
def numbers(
    conn: sqlite3.Connection = Depends(get_conn),
    config: Config = Depends(get_config),
) -> str:
    """Het eerlijkheidsdashboard (#22.5): per verzoek vers uit de metingen.
    Engelstalig en onder een Engels pad sinds #22.7."""
    from doublecheck.cijfers import STANDAARD_CONFORMANTIE, bouw_pagina

    pad = os.environ.get("DOUBLECHECK_CONFORMANTIE", STANDAARD_CONFORMANTIE)
    return bouw_pagina(conn, config, pad)


@app.get("/cijfers", response_class=HTMLResponse)
def cijfers(
    conn: sqlite3.Connection = Depends(get_conn),
    config: Config = Depends(get_config),
) -> str:
    """Alias van `/numbers`, zodat bestaande verwijzingen blijven werken."""
    return numbers(conn, config)


@app.get("/ask", response_class=HTMLResponse)
def ask_pagina(config: Config = Depends(get_config)) -> str:
    """Ask Factiz (#24.10, DESIGN §4e): de vraag gaat met POST in de body,
    nooit in de URL (DR3)."""
    from doublecheck.askui import ASK_PAGINA

    return ASK_PAGINA.replace("__BEWAARTERMIJN__", str(config.retention.artifact_days))


@app.get("/favicon.svg")
def favicon():
    """Hetzelfde merkteken als factiz.org (#23.11), van deze host: de pagina's
    hier laden niets van elders."""
    from fastapi.responses import Response

    from doublecheck.webui import FAVICON

    return Response(FAVICON, media_type="image/svg+xml", headers={"Cache-Control": "public, max-age=86400"})


@app.get("/beeld/{naam}.webp")
def beeld(naam: str):
    """De velden van de site (#23.14, DESIGN §4h), van deze host: de voet op
    try.factiz.org staat op hetzelfde beeld als op factiz.org. Alleen de
    velden die het script kent, dus geen pad van buiten."""
    from fastapi.responses import FileResponse

    from doublecheck.velden import UIT, VELDEN

    if naam not in VELDEN:
        raise HTTPException(status_code=404)
    return FileResponse(UIT / f"{naam}.webp", media_type="image/webp",
                        headers={"Cache-Control": "public, max-age=604800"})


@app.get("/claimfilter")
def claimfilter(conn: sqlite3.Connection = Depends(get_conn)) -> dict:
    """De Bloom-filter van bekende claimteksten voor lokale matching (#24.2).

    Alleen hashes van publieke claims: de plug-in toetst posts op het apparaat
    zelf en stuurt pas iets na een klik (DR3). Geen PROTOCOL-onderdeel; het
    formaat staat in `doublecheck/claimfilter.py` en de pariteitsvectoren.
    """
    from doublecheck.claimfilter import filter_voor

    return filter_voor(conn)


class ImageFingerprintIn(BaseModel):
    """Een door de client zelf berekende beeldfingerprint (PROTOCOL §4).

    PDQ is een DCT over een 64×64 verkleining en draait dus in een browser
    zonder model. Voor screenshots — de virale vorm — is de belofte "het
    artefact verlaat je apparaat niet" daarmee vandaag waar te maken.
    """

    model_config = ConfigDict(extra="forbid")

    scheme: str
    hash: str


class ResolveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str | None = None
    image_fingerprint: ImageFingerprintIn | None = None


class LinkOut(BaseModel):
    """Is de bron van deze check nog bereikbaar (PROTOCOL §5, #25.9)?

    Additief binnen v0.1, net als `attributions`: het oordeel van de check
    hangt er niet van af. `offline` pas na twee dode waarnemingen met minstens
    `[bonnetjes] offline_na_uren` ertussen; `offline_since` is de eerste dode
    waarneming, dus de link kan eerder gestorven zijn."""

    status: str
    checked_on: str
    offline_since: str | None = None
    last_seen_live: str | None = None
    archive_url: str | None = None
    archived_on: str | None = None


class FactcheckOut(BaseModel):
    publisher: str
    verdict_normalized: str
    verdict_original: str
    url: str
    review_date: str
    language: str
    # `null` zolang de link nooit gecontroleerd is (#25.9).
    link: LinkOut | None = None


class ClaimOut(BaseModel):
    """De bewering waar dit antwoord over gaat (PROTOCOL §5).

    Eén object, niet drie verspreide velden. `cluster_size` hoorde eerder in
    `evidence`, maar hoeveel claims samen deze bewering vormen is een
    eigenschap van de bewering, niet van wie haar checkte (#15.1b).
    """

    id: str
    # Leeg zolang er geen bewijs opgebouwd is — bij `related` kennen we de
    # buurclaim wel, maar presenteren we hem niet als gecontroleerde bewering.
    text: str | None = None
    cluster_size: int | None = None


class AttributionOut(BaseModel):
    """Eén regel in de geschiedenis van een bewering: waar en wanneer ze
    opdook, volgens welke bron (PROTOCOL §5 en §11.7, DR10)."""

    actor: str
    actor_kind: str
    source: str
    source_kind: str
    level: str
    date: str
    url: str


class EvidenceOut(BaseModel):
    checks: list[FactcheckOut]
    check_count: int
    publisher_count: int
    languages: list[str]
    # `None` wanneer geen enkele check een datum draagt (#14.3).
    oldest_date: str | None
    # Additief binnen v0.1 (§11.7): een client die het veld niet kent, mist
    # niets van het oordeel. Telt nooit mee bij `publisher_count` (DR7).
    attributions: list[AttributionOut] = []


class ThresholdsOut(BaseModel):
    """Elke drempel die dit antwoord bepaald kan hebben (PROTOCOL §2.8).

    Zonder de cross-linguale drempel is een `matched` op 0,87 van buitenaf niet
    te rijmen met een gemelde drempel van 0,92: de afnemer ziet een schending
    waar er geen is. `cluster_same` staat erbij omdat de clustering bepaalt
    hoeveel checks er in het bewijs terechtkomen.
    """

    text_match: float
    text_related: float
    image_same: int
    text_match_crosslingual: float
    cluster_same: float
    # Met de rechter aan (#30.3): `matched` kan vanaf `text_match_judged`
    # vallen, maar alleen als de rechter `judge_same` haalt; vanaf
    # `text_match` blokkeert een score onder `judge_veto`. Zonder deze drie
    # ziet een afnemer een `matched` op 0,83 als schending van verplichting 2.
    # Met de rechter uit staan ze er niet.
    text_match_judged: float | None = None
    judge_same: float | None = None
    judge_veto: float | None = None
    # Met de artikellezer aan (#30.11b): bij een tekst van meerdere eenheden
    # `matched` vanaf `text_match_read` als de lezer `reader_same` haalt.
    text_match_read: float | None = None
    reader_same: float | None = None

    @model_serializer(mode="wrap")
    def _zonder_lege(self, handler):
        return {k: v for k, v in handler(self).items() if v is not None}


def drempels_uit(thresholds, config: Config) -> ThresholdsOut:
    """De drempels die dit antwoord bepaald kunnen hebben (verplichting 8),
    de rechter alleen als hij aan staat."""
    basis = {veld: getattr(thresholds, veld) for veld in
             ("text_match", "text_related", "image_same", "text_match_crosslingual", "cluster_same")}
    if config.rechter.aan:
        basis |= {"text_match_judged": thresholds.rechter_vloer, "judge_same": thresholds.rechter_zelfde,
                  "judge_veto": thresholds.rechter_veto}
    if config.artikellezer.aan:
        basis |= {"text_match_read": thresholds.artikel_vloer, "reader_same": thresholds.artikel_zelfde}
    return ThresholdsOut(**basis)


class DisputeRequest(BaseModel):
    """Toestemming is een expliciet veld; afwezigheid telt als weigering (AC1)."""

    model_config = ConfigDict(extra="forbid")

    disputed_category: Category
    dispute_text: str
    text: str | None = None
    claim_id: str | None = None
    consent_to_store_artifact: bool = False


class DeletionRequest(BaseModel):
    """De sleutel gaat in de body, nooit in de URL — die belandt in logboeken."""

    model_config = ConfigDict(extra="forbid")

    deletion_key: str


class DeletionResponse(BaseModel):
    dispute_id: int
    artifact_present: bool


class DisputeResponse(BaseModel):
    dispute_id: int
    stored_artifact: bool
    artifact_expires_at: str | None
    deletion_key: str | None
    stored_fields: list[str]


class ObservedSourceOut(BaseModel):
    """Bron die zichtbaar is ín het artefact — waargenomen, nooit geverifieerd."""

    kind: str
    value: str
    status: str


class SchemeOut(BaseModel):
    id: str
    bits: int
    encoding: str


class ScopeOut(BaseModel):
    """Zonder dit veld kan een afnemer een `none` niet lezen (PROTOCOL §6)."""

    # Talen mét een eigen benchmark. B14: een markt is live als zijn cijfer
    # bestaat en slaagt, niet als zijn corpus bestaat.
    markets: list[str]
    # Talen die wél in de index zitten maar (nog) geen eigen cijfer dragen.
    languages: list[str]
    claims: int
    # Jongste factcheckdatum in de index — niet "wanneer wij draaiden", maar
    # tot hoever het materiaal reikt. Dat is wat een `none` leesbaar maakt.
    newest_check: str | None


class ResolverOut(BaseModel):
    id: str
    name: str


class ClaimIdOut(BaseModel):
    """Hoe een claim-id uit de claimtekst volgt (PROTOCOL §7, #11.3).

    Dit is wat federatie draagt: twee resolvers die dezelfde tekst kennen komen
    zonder overleg op hetzelfde id uit — geen register, geen autoriteit. Zonder
    dat dit ergens staat, zou een tweede implementatie met willekeurige id's
    federatie stilzwijgend breken.
    """

    algorithm: str
    preprocessing: list[str]
    hex_chars: int


class VariantSetOut(BaseModel):
    """Eén set claimvarianten waarover de resolver zoekt (PROTOCOL §3, #25.17).

    Zonder dit veld ziet een afnemer pas aan een `via` in een antwoord dat er
    machinevertalingen tussen kunnen zitten; hier ziet hij het vóór zijn eerste
    vraag, met de generator en promptversie die ook in `via` staan.
    """

    generator: str
    prompt: str
    languages: list[str]
    count: int


class DiscoveryOut(BaseModel):
    protocol: str
    resolver: ResolverOut
    schemes: dict[str, list[SchemeOut]]
    thresholds: ThresholdsOut
    scope: ScopeOut
    claim_id: ClaimIdOut
    # Leeg als de resolver alleen over de eigen claimteksten zoekt.
    variants: list[VariantSetOut]


class ResolveResponse(BaseModel):
    # Wie dit antwoord gaf (PROTOCOL §7). Nodig zodra een antwoord wordt
    # doorgegeven of bewaard — en juist dan is federatie aan de orde.
    resolver: str
    category: Category
    claim: ClaimOut | None
    similarity: float | None
    relation: str | None
    matched_on: list[str]
    # Alleen als de tekstmatch via een claimvariant kwam (#25.17): de taal van
    # de variant, het model dat haar schreef en de promptversie.
    via: dict[str, str] | None = None
    observed_sources: list[ObservedSourceOut]
    thresholds: ThresholdsOut
    # Welk schema elke gebruikte fingerprint maakte (PROTOCOL §2.7, §5). Alleen
    # de schema's die deze aanvraag écht raakten: een tekstaanvraag noemt geen
    # beeldversie. Zonder dit veld kan een afnemer twee antwoorden niet op
    # vergelijkbaarheid toetsen — precies wat DR6 intern al afdwingt.
    schemes_used: dict[str, str]
    evidence: EvidenceOut | None
    # Alleen bij `none` (PROTOCOL §6, #25.35): `not_found`, `out_of_scope` of
    # `low_confidence`. Zonder reden kan een afnemer "niets gevonden" niet
    # scheiden van "kon niet goed zoeken".
    reason: str | None = None


class AskRequest(BaseModel):
    """Alleen de vraag; een onbekend veld wordt geweigerd, dus ook hier kan
    een aanroeper niet om een lagere drempel vragen (DR4)."""

    model_config = ConfigDict(extra="forbid")

    question: str


class TranslationOut(BaseModel):
    """De bewering in de taal van de pagina, offline geschreven (#25.17);
    alleen samen met het origineel te tonen (B32)."""

    language: str
    from_language: str
    text: str
    generator: str
    prompt: str


class AskResultOut(BaseModel):
    """Eén gecheckte bewering dicht bij de vraag. Het oordeel staat in de
    checks van déze bewering, nooit op de vraag (DR2, B25)."""

    category: Category
    similarity: float
    claim: ClaimOut
    via: dict[str, str] | None = None
    evidence: EvidenceOut
    translation: TranslationOut | None = None


class AskTotalsOut(BaseModel):
    claims: int
    newsrooms: int
    languages: int
    first_year: str | None = None
    last_year: str | None = None


class TiplineOut(BaseModel):
    organization: str
    country: str
    numbers: list[str]
    links: list[str]


class TiplineSourceOut(BaseModel):
    name: str
    url: str
    recorded: str


class AskResponse(BaseModel):
    resolver: str
    # Alleen `matched` en `related`, elk cluster één keer (E5.S3-AC1, AC2).
    results: list[AskResultOut]
    # Alleen als er niets getoond wordt, met de woorden van een `none` (§6).
    reason: str | None = None
    thresholds: ThresholdsOut
    schemes_used: dict[str, str]
    # De regel bovenaan: beweringen, redacties, talen, jaren (DESIGN §4e).
    totals: AskTotalsOut | None = None
    # Een samenvatting van de oordelen over de getoonde beweringen, of de
    # reden waarom niet ("opposite"); nooit een oordeel over de vraag (AC8).
    summary: dict | None = None
    # Alleen als er niets getoond wordt: redacties die tips aannemen, in de
    # taal van de vraag, met de bron van de lijst (AC10).
    tiplines: list[TiplineOut] = []
    tiplines_source: TiplineSourceOut | None = None


def _evidence_out(bewijs: EvidenceState, conn: sqlite3.Connection, offline_na_uren: int) -> EvidenceOut:
    # De linkstatus komt ná de telling: een dode link haalt nooit een check
    # weg en verandert geen telling (#25.9, DR7).
    links = links_voor(conn, (check.url for check in bewijs.factchecks), offline_na_uren)
    return EvidenceOut(
        checks=[FactcheckOut(**check.__dict__, link=links.get(check.url)) for check in bewijs.factchecks],
        check_count=bewijs.check_count,
        publisher_count=bewijs.publisher_count,
        languages=list(bewijs.languages),
        oldest_date=bewijs.oldest_date,
        # Over dezelfde claims als de checks; opgehaald ná de telling, die
        # ze dus nooit ziet (DR7, E7.S2-AC2).
        attributions=[
            AttributionOut(actor=a.actor, actor_kind=a.actor_soort, source=a.bron, source_kind=a.bron_soort,
                           level=a.niveau, date=a.datum, url=a.url)
            for a in attributies_voor(conn, bewijs.leden)
        ],
    )


async def _lees_artefact(
    request: Request,
) -> tuple[str | None, bytes | None, "ImageFingerprintIn | None"]:
    """Eén endpoint, twee vormen: JSON met tekst, of multipart met een bestand."""
    content_type = request.headers.get("content-type", "")

    if content_type.startswith("multipart/form-data"):
        formulier = await request.form()
        bestand = formulier.get("image")
        if bestand is None or isinstance(bestand, str):
            raise HTTPException(status_code=422, detail="no file in field 'image'")
        inhoud = await bestand.read()
        if len(inhoud) > MAX_IMAGE_BYTES:
            raise HTTPException(
                status_code=413,
                detail=f"image larger than {MAX_IMAGE_BYTES} bytes",
            )
        meegestuurde_tekst = formulier.get("text")
        return (
            str(meegestuurde_tekst) if isinstance(meegestuurde_tekst, str) else None,
            inhoud,
            None,
        )

    try:
        data = await request.json()
        verzoek = ResolveRequest(**data)
    except (ValidationError, TypeError, ValueError) as fout:
        raise HTTPException(status_code=422, detail=f"unreadable request: {fout}") from None
    return verzoek.text, None, verzoek.image_fingerprint


def _in_index(conn: sqlite3.Connection) -> list:
    """(claim_id, taal) van wat de index kan vinden (B28): een claim buiten de
    index geeft nooit een treffer, dus hij hoort niet in de reikwijdte van een
    `none`. In de zoekcache, per stand van de database."""
    from doublecheck.search import _gecachet
    from doublecheck.toelating import buiten_index

    def bereken():
        buiten = buiten_index(conn)
        return [tuple(rij) for rij in conn.execute("SELECT claim_id, language FROM claim") if rij[0] not in buiten]

    return _gecachet(conn, "in_index", bereken)


@app.get("/.well-known/doublecheck", response_model=DiscoveryOut)
def ontdekking(
    conn: sqlite3.Connection = Depends(get_conn),
    config: Config = Depends(get_config),
) -> DiscoveryOut:
    """Welke schema's spreekt deze resolver, en hoe ver reikt hij? (§3)

    Een fingerprint is schemaspecifiek, dus een client die er zelf één maakt
    moet eerst wéten welke. Zonder deze stap kan "stuur de fingerprint, niet
    het artefact" niet werken — en tot #11.1 bestond dit document alleen op
    papier (§9).
    """
    in_index = _in_index(conn)
    talen = sorted({taal for _, taal in in_index if taal})
    markten = [
        rij[0]
        for rij in conn.execute(
            "SELECT DISTINCT language FROM testpair WHERE language <> ''"
            " ORDER BY language"
        )
    ]
    claims = len(in_index)
    jongste = conn.execute(
        "SELECT max(review_date) FROM factcheck WHERE review_date <> ''"
    ).fetchone()[0]
    return DiscoveryOut(
        protocol="0.1",
        resolver=ResolverOut(id=config.resolver.id, name=config.resolver.name),
        claim_id=ClaimIdOut(
            algorithm="sha256",
            preprocessing=["strip", "collapse-whitespace", "casefold"],
            hex_chars=16,
        ),
        schemes={
            "image": [
                SchemeOut(
                    id=config.model_versions.image_hash,
                    bits=IMAGE_BITS.get(config.model_versions.image_hash, 0),
                    encoding="hex",
                )
            ],
            # Tekst staat er bewust níét in: een clientzijdige tekstfingerprint
            # vergt een eigen schema met een eigen drempel en benchmark (§4).
            # Een schema aanbieden dat we niet kunnen waarmaken is erger dan
            # geen schema.
            "text": [],
        },
        thresholds=drempels_uit(config.thresholds, config),
        scope=ScopeOut(
            markets=[t for t in markten if t in talen],
            languages=talen,
            claims=claims,
            newest_check=jongste,
        ),
        variants=[
            VariantSetOut(**set_)
            for set_ in variant_sets(conn, config.model_versions.text_embedding)
        ] if config.varianten.in_resolver else [],
    )


def _claimtekst(conn, claim_id: str) -> str:
    return conn.execute("SELECT canonical_text FROM claim WHERE claim_id = ?", (claim_id,)).fetchone()[0]


def _tegenspraak_voor(vinger, eenheid: str):
    """DR8 voor de rechter, tegen de tekst van deze eenheid."""
    return lambda tekst: contradicts(vinger.numbers, vinger.negations, tekst, artefact_text=eenheid,
                                     artefact_negation_tokens=vinger.negation_tokens)


def _beoordeel(conn, config: Config, eenheid, vinger, kandidaten: list, beeld_afstand, beeld_claim,
               lezer: float | None = None):
    """Eén eenheid door `categorize` (DR4), met DR8 en de feitenlaag tegen haar
    eigen tekst. Geeft de uitkomst, de beste kandidaat, en de marge boven de
    rechterdrempel (0 zonder rechter) om bij gelijke categorie te kiezen."""
    beste = kandidaten[0] if kandidaten else None
    tegenspraak = False
    crosslinguaal = False
    if beste is not None:
        kandidaat = conn.execute(
            "SELECT canonical_text, language FROM claim WHERE claim_id = ?",
            (beste.claim_id,),
        ).fetchone()
        tegenspraak = contradicts(
            vinger.numbers,
            vinger.negations,
            kandidaat["canonical_text"],
            artefact_negation_tokens=vinger.negation_tokens,
            # De contextregel (PLAN.md #8.4) heeft de artefacttekst nodig.
            # In productie is die er; de benchmark bewaart hem bewust niet
            # (DR3), dus die meet alleen de deelverzameling-regel.
            artefact_text=eenheid,
        )
        # Alleen wanneer béíde talen herkend zijn én verschillen (#12.4);
        # twijfel valt terug op de strenge drempel.
        crosslinguaal = zijn_verschillende_talen(vinger.language, kandidaat["language"])
    uitkomst = categorize(
        beste.similarity if beste else None,
        config.thresholds,
        contradiction=tegenspraak,
        image_distance=beeld_afstand,
        crosslinguaal=crosslinguaal,
        # Wijst het beeld een ándere claim aan dan de tekst? Dan mag het niet
        # als bevestiging van die tekst gepresenteerd worden (#13.2).
        image_claim_differs=(
            beeld_claim is not None
            and beste is not None
            and beeld_claim != beste.claim_id
        ),
        rechter=rechter.oordeel(beste, config) if beste is not None else None,
        # De feitenlaag (#30.3b): eerst de goedkope vraag of de kandidaat rood
        # is, pas dan de rechter tegen de vastgestelde feiten.
        feit_rood=(config.feiten.aan and beste is not None and eenheid is not None
                   and feitenlaag.rood(conn, beste.claim_id)
                   and feitenlaag.herken(eenheid, vinger, config) is not None),
        lezer=lezer,
    )
    return uitkomst, beste, artikel.marge(beste, config, crosslinguaal)


@app.post("/resolve", response_model=ResolveResponse)
async def resolve(
    request: Request,
    conn: sqlite3.Connection = Depends(get_conn),
    config: Config = Depends(get_config),
) -> ResolveResponse:
    tekst, afbeelding, meegeleverd = await _lees_artefact(request)
    return los_op(conn, config, tekst, afbeelding, meegeleverd)


def los_op(conn: sqlite3.Connection, config: Config, tekst: str | None, afbeelding: bytes | None,
           meegeleverd: "ImageFingerprintIn | None") -> ResolveResponse:
    """De kern van `/resolve`, zonder het verzoek; ook de eerste kring van `/check` (PLAN #32.7a)."""
    observed_bronnen: tuple = ()
    beeld_afstand: int | None = None
    beeld_claim: str | None = None
    zoektekst: str | None = None
    beeld_schema: str | None = None

    if meegeleverd is not None:
        # De client rekende zelf; hier komt geen artefact langs (PROTOCOL §4).
        eigen = config.model_versions.image_hash
        if meegeleverd.scheme != eigen:
            # Luid weigeren, niet stil doorrekenen (§2.7). Zonder deze controle
            # filtert de beeldzoeker gewoon op modelversie, vindt nul rijen en
            # geeft een keurige `none` — een antwoord dat niets betekent.
            raise HTTPException(
                status_code=409,
                detail=(
                    f"this resolver speaks {eigen!r}, not {meegeleverd.scheme!r};"
                    " ask /.well-known/doublecheck which scheme applies"
                ),
            )
        try:
            beeld_fp = fingerprint_van_hex(meegeleverd.hash, eigen)
        except ValueError as fout:
            raise HTTPException(status_code=422, detail=str(fout)) from None
        beeld_schema = eigen
        beeld_kandidaten = search_image(conn, beeld_fp)
        if beeld_kandidaten:
            beeld_afstand = beeld_kandidaten[0].distance
            beeld_claim = beeld_kandidaten[0].claim_id

    if afbeelding is not None:
        try:
            beeld_fp = fingerprint_image(afbeelding, config.model_versions.image_hash)
            ocr = extract_text(afbeelding, config.ocr)
        except TeGroteAfbeelding:
            raise HTTPException(
                status_code=422,
                detail="image has too many pixels to process",
            ) from None
        except (UnidentifiedImageError, OSError, TypeError, DecompressionBombError):
            raise HTTPException(
                status_code=422, detail="unreadable image"
            ) from None
        observed_bronnen = observe_sources(ocr.text)
        if ocr.readable:
            zoektekst = ocr.text
        # Beide routes draaien, ook bij leesbare tekst (B15, PO 2026-08-30). De
        # v1-inperking E1.S2-AC5 bestond om één reden: pHash codeerde op
        # tekstscreenshots vooral lay-out en gaf 250 van 250 valse koppelingen
        # op niet-geïndexeerde beelden. Met PDQ is dat 0 van 250 (§29c).
        # Wat blijft: een beeldtreffer zónder claimtreffer wordt `related` en
        # nooit `matched` — dat regelt de categorisering (B8, DR4).
        beeld_kandidaten = search_image(conn, beeld_fp)
        if beeld_kandidaten:
            beeld_afstand = beeld_kandidaten[0].distance
            beeld_claim = beeld_kandidaten[0].claim_id

    if tekst is not None:
        schoon = tekst.strip()
        if not schoon:
            raise HTTPException(status_code=422, detail="empty text artifact")
        if len(schoon) > MAX_TEXT_LENGTH:
            raise HTTPException(
                status_code=413,
                detail=f"text artifact longer than {MAX_TEXT_LENGTH} characters",
            )
        zoektekst = schoon

    if zoektekst is None and afbeelding is None and meegeleverd is None:
        raise HTTPException(status_code=422, detail="no artifact submitted")

    beste = None
    if zoektekst is not None:
        # DR6-guard vóór het embedden: bij een niet-herbouwde index na een
        # modelwissel weigert de resolver, in plaats van stil `none` te geven.
        try:
            ensure_index_matches_version(conn, config.model_versions.text_embedding)
            if config.varianten.in_resolver:
                ensure_variants_match_version(conn, config.model_versions.text_embedding)
        except ModelVersionMismatchError as fout:
            raise HTTPException(status_code=503, detail=str(fout)) from None

        versie = config.model_versions.text_embedding
        # De bewering uit een artikel (#30.11): met de schakelaar aan een tekst
        # met twee of meer zinnen als geheel plus per zin; één zin blijft het
        # pad van daarvóór.
        eenheden = zinnen.eenheden(zoektekst) if config.artikel.per_zin else [zoektekst]
        if len(eenheden) == 1:
            vingers = [fingerprint_text(zoektekst, versie)]
            # Via de vraagvorm (#25.36): met de regel uit precies de oude zoekvraag.
            lijsten = [vraagvorm.zoek(conn, config, zoektekst, vingers[0], max(5, config.rechter.diepte),
                                      vingerafdruk=fingerprint_text)]
        else:
            vingers = fingerprint_texts(eenheden, versie)
            lijsten = vraagvorm.zoek_alle(conn, config, eenheden, vingers, max(5, config.rechter.diepte),
                                          vingerafdrukken=fingerprint_texts)
        # De rechter (#30.3): met de schakelaar uit ongewijzigd.
        for i in artikel.te_lezen(lijsten, config):
            lijsten[i] = rechter.herorden(conn, config, eenheden[i], lijsten[i],
                                          tegenspraak=_tegenspraak_voor(vingers[i], eenheden[i]))
        uitslagen = [_beoordeel(conn, config, eenheid, vinger, lijst, beeld_afstand, beeld_claim)
                     for eenheid, vinger, lijst in zip(eenheden, vingers, lijsten)]
        uitkomst, beste, _ = artikel.winnaar(uitslagen)
        # De artikellezer (#30.11b): een tekst van meerdere eenheden die zo geen
        # `matched` gaf, leest hij met de beste claims over de eenheden.
        if config.artikellezer.aan and uitkomst.category is not Category.MATCHED:
            if len(eenheden) == 1 and len(alle := zinnen.eenheden(zoektekst)) > 1:
                eenheden, vingers = alle, fingerprint_texts(alle, versie)
                lijsten = vraagvorm.zoek_alle(conn, config, eenheden, vingers,
                                              max(5, config.rechter.diepte, config.artikellezer.diepte),
                                              vingerafdrukken=fingerprint_texts)
            gelezen = artikellezer.lees(config, zoektekst, lijsten, lambda c: _claimtekst(conn, c)) \
                if len(eenheden) > 1 else None
            if gelezen is not None:
                kandidaat, score, i = gelezen
                gelezen_uitkomst, gelezen_beste, _ = _beoordeel(conn, config, eenheden[i], vingers[i], [kandidaat],
                                                                beeld_afstand, beeld_claim, lezer=score)
                if gelezen_uitkomst.category is Category.MATCHED:
                    uitkomst, beste = gelezen_uitkomst, gelezen_beste
    else:
        uitkomst, beste, _ = _beoordeel(conn, config, None, None, [], beeld_afstand, beeld_claim)

    via_tekst = {"tekst", "tekst-gedeeltelijk"} & set(uitkomst.matched_on)
    if uitkomst.category is Category.NONE:
        claim_id = None
    elif via_tekst and beste is not None:
        claim_id = beste.claim_id
    elif "beeld" in uitkomst.matched_on:
        claim_id = beeld_claim
    else:
        claim_id = None

    # Kwam de tekstmatch via een claimvariant, dan zegt het antwoord dat
    # (#25.17, B12): de afnemer moet kunnen zien dat er een vertaling door een
    # taalmodel tussen zat.
    via = beste.via if (via_tekst and beste is not None and claim_id == beste.claim_id) else None

    bewijs = None
    claim_uit = None
    if claim_id is not None:
        claim_uit = ClaimOut(id=claim_id)
    if uitkomst.category is Category.MATCHED and claim_id is not None:
        staat = build_evidence(conn, claim_id)
        bewijs = _evidence_out(staat, conn, config.bonnetjes.offline_na_uren)
        claim_uit = ClaimOut(
            id=claim_id,
            text=staat.canonical_text,
            cluster_size=staat.cluster_size,
        )

    reden = None
    if uitkomst.category is Category.NONE:
        # De taal zoals het corpus talen benoemt (97 talen), niet de detector
        # van het taalpaar: de vraag is hier of de index deze taal kent.
        from doublecheck.taal import corpus_taal

        reden = reden_voor_none(
            zoektekst=zoektekst,
            taal=corpus_taal(zoektekst) if zoektekst is not None else None,
            index_talen={taal for _, taal in _in_index(conn) if taal},
        )

    schemas: dict[str, str] = {}
    if zoektekst is not None:
        schemas["text"] = config.model_versions.text_embedding
    if afbeelding is not None or beeld_schema is not None:
        schemas["image"] = config.model_versions.image_hash

    return ResolveResponse(
        resolver=config.resolver.id,
        category=uitkomst.category,
        claim=claim_uit,
        similarity=uitkomst.similarity,
        relation="tegenspraak" if uitkomst.contradiction else None,
        matched_on=list(uitkomst.matched_on),
        via=via,
        observed_sources=[
            ObservedSourceOut(kind=bron.kind, value=bron.value, status=bron.status)
            for bron in observed_bronnen
        ],
        thresholds=drempels_uit(uitkomst.thresholds, config),
        schemes_used=schemas,
        evidence=bewijs,
        reason=reden,
    )


@app.post("/ask", response_model=AskResponse)
async def vraag_het_corpus(
    verzoek: AskRequest,
    conn: sqlite3.Connection = Depends(get_conn),
    config: Config = Depends(get_config),
) -> AskResponse:
    """Ask Factiz (#24.10, SPECS E5.S3): een vraag aan het corpus. Geen
    PROTOCOL-onderdeel, zoals `/claimfilter`. De vraag wordt vergeleken en
    vergeten (DR3); de categorie per bewering komt uit `categorize` (DR4)."""
    from doublecheck import ask
    from doublecheck.taal import corpus_taal

    vraag = verzoek.question.strip()
    if not vraag:
        raise HTTPException(status_code=422, detail="empty question")
    if len(vraag) > MAX_TEXT_LENGTH:
        raise HTTPException(status_code=413, detail=f"question longer than {MAX_TEXT_LENGTH} characters")
    try:
        ensure_index_matches_version(conn, config.model_versions.text_embedding)
        if config.varianten.in_resolver:
            ensure_variants_match_version(conn, config.model_versions.text_embedding)
    except ModelVersionMismatchError as fout:
        raise HTTPException(status_code=503, detail=str(fout)) from None

    fingerprint = fingerprint_text(vraag, config.model_versions.text_embedding)
    rijen = ask.getoond(conn, ask.kandidaten(conn, config, vraag, fingerprint, vingerafdruk=fingerprint_text))
    resultaten = []
    for rij, staat in rijen:
        taal = conn.execute("SELECT language FROM claim WHERE claim_id = ?", (rij.claim_id,)).fetchone()[0]
        vertaald = ask.vertaling(conn, rij.claim_id, taal)
        resultaten.append(AskResultOut(
            category=rij.categorie,
            similarity=rij.gelijkenis,
            claim=ClaimOut(id=rij.claim_id, text=rij.tekst, cluster_size=staat.cluster_size),
            via=rij.via,
            evidence=_evidence_out(staat, conn, config.bonnetjes.offline_na_uren),
            translation=TranslationOut(**vertaald) if vertaald else None,
        ))
    reden, lijnen, bron = None, [], None
    if not resultaten:
        vraagtaal = corpus_taal(vraag)
        reden = reden_voor_none(zoektekst=vraag, taal=vraagtaal,
                                index_talen={taal for _, taal in _in_index(conn) if taal})
        lijnen, bron = ask.tiplijnen(vraagtaal)
    return AskResponse(
        resolver=config.resolver.id,
        results=resultaten,
        reason=reden,
        thresholds=drempels_uit(config.thresholds, config),
        schemes_used={"text": config.model_versions.text_embedding},
        totals=AskTotalsOut(**ask.tellingen(rijen, config.consensus.onbekende_uitgever)) if rijen else None,
        summary=ask.samenvatting(rijen),
        tiplines=[TiplineOut(**lijn) for lijn in lijnen],
        tiplines_source=TiplineSourceOut(**bron) if lijnen else None,
    )


class _Anthropic:
    """De client van het model, pas gemaakt bij de eerste vraag: met de controle
    uit raakt niets de sleutel of het netwerk (B43)."""

    _client = None

    @property
    def messages(self):
        if _Anthropic._client is None:
            import anthropic

            from doublecheck.varianten import laad_sleutel

            laad_sleutel()
            _Anthropic._client = anthropic.Anthropic()
        return _Anthropic._client.messages


def get_anthropic() -> _Anthropic:
    return _Anthropic()


def get_zoeker():
    """De zoekdienst van de controle (B51), met de sleutel pas bij de eerste zoekvraag: met de controle uit raakt
    niets de sleutel of het netwerk."""

    def zoek(q: str) -> dict:
        import os

        from doublecheck import zoekcontrole as zc
        from doublecheck.varianten import laad_sleutel

        laad_sleutel()
        sleutel = os.environ.get("BRAVE_API_KEY")
        if not sleutel:
            raise _checkfout(503, "search_unreachable", "no key for the search service (BRAVE_API_KEY)")
        return zc.brave(q, sleutel)

    return zoek


def get_kostenconn(config: Config = Depends(get_config)) -> Iterator[sqlite3.Connection]:
    """De kosten per dag van de controle, in een eigen bestand: nooit in de index (#31.12)."""
    from doublecheck.berichtcontrole import kostenverbinding

    conn = kostenverbinding(config)
    try:
        yield conn
    finally:
        conn.close()


class CheckRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str


class CheckSourceOut(BaseModel):
    """Een bron bij het antwoord: een check van een redactie (route *database*), of een zoekresultaat met de band
    uit de bronnenlijst en of het bevestigt of tegenspreekt (route *search*, B51)."""
    kind: str
    url: str | None = None
    publisher: str | None = None
    rating: str | None = None
    date: str | None = None
    title: str | None = None
    band: str | None = None
    role: str | None = None
    state_media: str | None = None


# B45: rood en groen voor de gebruiker.
_KLEUR_EN = {"rood": "red", "groen": "green", "oranje": "orange"}
_ROUTE_EN = {"database": "database", "zoeken": "search"}
_ROL_EN = {"bevestigt": "confirms", "spreekt tegen": "contradicts", "bevestigt het feit": "confirms_fact",
           "zelfde bewering": "same_claim"}
# #32.32: de negen uitkomsten van besluit A en B48, zoals `zoekcontrole.na_lezen` ze zet.
_UITKOMST_EN = {"geen bewering": "no_claim", "satire": "satire", "klopt": "true", "klopt grotendeels": "mostly_true",
                "klopt niet": "false", "misleidend": "misleading", "over een bewering": "about_a_claim",
                "beeld nodig": "image_needed", "niet bevestigd": "unconfirmed", "onzeker": "uncertain",
                "foto niet bij de bron": "photo_not_at_source"}


def _checks_uit_database(conn: sqlite3.Connection, config: Config, tekst: str) -> list[dict]:  # pragma: no cover
    """De beste 5 checks uit de database voor `lezer-v5` (#32.30): dezelfde lokale zoektocht als in de meting van
    #32.28 (`berichtcontrole.geheugen_met`, zonder beweringen), op de gemaskeerde tekst."""
    from doublecheck import berichtcontrole as bc
    from doublecheck import zoekcontrole as zc
    from doublecheck.embedding import fingerprint_texts

    if not _heeft_index(conn):
        return []
    fp = fingerprint_texts([tekst[:600]], config.model_versions.text_embedding)[0]
    return zc.checks_uit(bc.geheugen_met(conn, config, tekst, fp, []))


class CheckSearchOut(BaseModel):
    """Een eigen zoekvraag van de controle (`lezer-v9`, B57): de soort, de vraag, de site en hoeveel resultaten er
    kwamen; bij *niet bevestigd* de bonnetjes van wat er níét is (DESIGN §4l)."""
    kind: str
    query: str
    site: str | None = None
    found: int


_ZOEKSOORT_EN = {"eigen site": "own_site", "echt nieuws": "real_news", "bron zelf": "the_source"}


class CheckCorrectionOut(BaseModel):
    """Het foute detail bij *klopt grotendeels* (B48): de woorden zoals ze in `read` staan, met hun plaats daarin, wat
    het moet zijn, en het resultaat dat die waarde noemt."""
    words: str
    should_be: str
    url: str | None = None
    publisher: str | None = None
    start: int
    end: int


def _beeldstap(config: Config):  # pragma: no cover - de index op schijf en het tekstmodel
    """De beeldstap van #32.35 voor `/check`: de index één keer per proces, met de versies uit config (DR6)."""
    from doublecheck import beeldstap as bs
    from doublecheck.embedding import fingerprint_texts

    s = config.beeldstap
    versies = {"punten": s.punten, "vergelijking": s.vergelijking, "rol": s.rol,
               "tekst": config.model_versions.text_embedding}
    index = bs.index_uit(s.index, tuple(sorted(versies.items())))

    def stap(beeld: bytes, bericht: str, checks: list[dict]) -> list[dict]:
        vector = fingerprint_texts([bericht[:600]], config.model_versions.text_embedding)[0].vector
        return bs.bevestig_checks(beeld, vector, checks, index, s)
    return stap


class CheckPhotoOut(BaseModel):
    """De foto bij de bron (#32.54, DESIGN §4m): of de foto op een bevestigende goede pagina staat, welke, en hoeveel
    pagina's Factiz kon openen."""

    found: bool
    page: str | None = None
    checked: int = 0


class CheckResponse(BaseModel):
    """Het antwoord van de controle (B51, SPECS E5.S4): het oordeel (*klopt*, *klopt niet*, *onzeker*), de kleur
    voor de gebruiker (rood, groen of niets), de uitleg in één zin, en de bronnen. Een check van een redactie staat
    als bron met `kind` *check van een redactie*; het oordeel van het model staat apart (DR5). Geen `category`: die
    zet alleen `/resolve` (DR4). `route` zegt waar het antwoord vandaan kwam: de database of het zoeken."""

    verdict: str
    colour: str | None = None
    read: str
    explanation: str | None = None
    route: str
    sources: list[CheckSourceOut]
    versions: dict[str, str]
    about_image: bool = False  # #32.12: een bewering over wat een beeld toont; zonder het beeld nooit groen
    # #32.13: het onderliggende feit (alleen als de bewering niet klopt en twee bronnen het dragen) en wat er echt
    # gebeurde (alleen bij rood of oranje)
    fact: str | None = None
    what_happened: str | None = None
    # #32.32: welke van de negen uitkomsten; bij *klopt grotendeels* de verbetering; bij een bericht over een
    # bewering van een ander de kleur van die bewering zelf (het bericht krijgt er geen)
    outcome: str = "uncertain"
    correction: CheckCorrectionOut | None = None
    claim_colour: str | None = None
    # #32.41, B57: de eigen zoekvragen van de controle; leeg bij een lezer zonder (tot `lezer-v9`)
    searches: list[CheckSearchOut] = []
    # #32.54, DESIGN §4m: de laag van het nieuws (groen als het nieuws klopt, ook als het bericht geen kleur krijgt) en de
    # foto bij de bron; leeg zonder foto of zonder groen
    news_colour: str | None = None
    photo: CheckPhotoOut | None = None


async def _lees_bericht(request: Request) -> tuple[str | None, bytes | None]:
    """JSON met tekst, of multipart met een screenshot en eventueel een bijschrift."""
    if request.headers.get("content-type", "").startswith("multipart/form-data"):
        formulier = await request.form()
        bestand = formulier.get("image")
        if bestand is None or isinstance(bestand, str):
            raise _checkfout(422, "image_unreadable", "no file in field 'image'")
        inhoud = await bestand.read()
        if len(inhoud) > MAX_IMAGE_BYTES:
            raise _checkfout(413, "too_large", f"image larger than {MAX_IMAGE_BYTES} bytes")
        tekst = formulier.get("text")
        return (tekst if isinstance(tekst, str) else None), inhoud
    try:
        return CheckRequest(**(await request.json())).text, None
    except (ValidationError, TypeError, ValueError) as fout:
        raise _checkfout(422, "other", f"unreadable request: {fout}") from None


def _checkfout(status: int, reden: str, bericht: str) -> HTTPException:
    """Een fout van de controle met een vaste reden, zodat de pagina haar eigen tekst toont (D7)."""
    return HTTPException(status_code=status, detail={"reason": reden, "message": bericht})


@app.get("/check", response_class=HTMLResponse)
def check_pagina(config: Config = Depends(get_config)) -> str:
    """De controlepagina (#31.13, DESIGN §4g): het bericht gaat met POST in de body,
    nooit in de URL (DR3); met de controle uit is de knop uit (B43)."""
    from doublecheck.checkui import pagina

    return pagina(config.berichtcontrole.aan, config.berichtcontrole.beeld)


def _heeft_index(conn: sqlite3.Connection) -> bool:
    """Zonder één vingerafdruk in de database is er geen eerste kring."""
    return conn.execute("SELECT 1 FROM fingerprint LIMIT 1").fetchone() is not None


@app.post("/check", response_model=CheckResponse)
async def controleer_bericht(
    request: Request,
    conn: sqlite3.Connection = Depends(get_conn),
    config: Config = Depends(get_config),
    client: _Anthropic = Depends(get_anthropic),
    zoek=Depends(get_zoeker),
    kosten: sqlite3.Connection = Depends(get_kostenconn),
) -> CheckResponse:
    """De controle per bericht, de simpele versie (B51; PLAN #32.10, SPECS E5.S4): eerst de database, anders één
    zoekvraag en Sonnet die de top 10 leest; de bronnenlijst beslist de kleur. Geen PROTOCOL-onderdeel, zoals
    `/ask`. Uit tot zero data retention actief is (B43)."""
    import urllib.error

    import anthropic
    from fastapi.concurrency import run_in_threadpool

    from doublecheck import berichtcontrole as bc
    from doublecheck import zoekcontrole as zc

    if not config.berichtcontrole.aan:
        raise _checkfout(503, "off", "the check is switched off (B43)")
    tekst, beeld = await _lees_bericht(request)
    if tekst is not None and len(tekst) > MAX_TEXT_LENGTH:
        raise _checkfout(413, "too_long", f"text longer than {MAX_TEXT_LENGTH} characters")
    try:
        ensure_index_matches_version(conn, config.model_versions.text_embedding)
    except ModelVersionMismatchError as fout:
        raise _checkfout(503, "version", str(fout)) from None

    def snel(bericht: str) -> dict | None:
        if not _heeft_index(conn):
            return None
        return bc.snel_antwoord(los_op(conn, config, bericht, None, None).model_dump(), bc.ijktabel(config),
                                bericht, config.model_versions.text_embedding)

    def controleer() -> dict:
        bericht = bc.bericht_uit(tekst, beeld, config.ocr)
        if not bericht.strip():
            raise _checkfout(422, "no_text", "no text found in the message")
        vandaag = date.today().isoformat()
        return zc.controleer(kosten, bericht, config, client, zoek, snel, bc.herkomstlijst()["sites"], vandaag,
                             datum=vandaag, beeld=beeld, bewaak=lambda: bc.bewaak_plafond(kosten, config, vandaag),
                             zoek_checks=lambda b: _checks_uit_database(conn, config, b),
                             beeldstap=_beeldstap(config) if config.beeldstap.aan else None)

    try:
        uit = await run_in_threadpool(controleer)
    except (UnidentifiedImageError, DecompressionBombError, TeGroteAfbeelding):
        raise _checkfout(422, "image_unreadable", "unreadable image") from None
    except bc.Plafond as fout:
        raise _checkfout(503, "cap", str(fout)) from None
    except bc.VersieFout as fout:
        raise _checkfout(503, "version", str(fout)) from None
    except anthropic.APIError:
        raise _checkfout(503, "model_unreachable", "the check cannot reach the model now") from None
    except (urllib.error.URLError, TimeoutError, ValueError):
        raise _checkfout(503, "search_unreachable", "the check cannot reach the search service now") from None
    from doublecheck.machinevraag import _OORDEEL_EN

    bronnen = []
    for b in uit["bronnen"]:
        if b.get("soort") == "check van een redactie":
            bronnen.append(CheckSourceOut(kind=b["soort"], url=b.get("url"), publisher=b.get("redactie"),
                                          rating=_OORDEEL_EN.get(b.get("oordeel"), b.get("oordeel")),
                                          date=b.get("datum"), role=_ROL_EN.get(b.get("rol"))))
        else:
            bronnen.append(CheckSourceOut(kind="web", url=b.get("url"), publisher=b.get("site"), title=b.get("titel"),
                                          band=b.get("band"), role=_ROL_EN.get(b.get("rol")),
                                          state_media=b.get("staatsmedia")))
    return CheckResponse(verdict=uit["oordeel"], colour=_KLEUR_EN.get(uit["kleur"]), read=uit["gelezen"],
                         explanation=uit["uitleg"], route=_ROUTE_EN[uit["route"]], sources=bronnen,
                         versions=uit["versies"], about_image=uit.get("over_beeld", False),
                         fact=uit.get("feit"), what_happened=uit.get("anders"),
                         outcome=_UITKOMST_EN.get(uit.get("uitkomst"), "uncertain"),
                         correction=_correctie_uit(uit.get("correctie")),
                         claim_colour=_KLEUR_EN.get(uit.get("kleur_bewering")),
                         searches=[CheckSearchOut(kind=_ZOEKSOORT_EN[g["soort"]], query=g["vraag"],
                                                  site=g.get("site") or None, found=g["gevonden"])
                                   for g in uit.get("speurstap") or [] if g.get("soort") in _ZOEKSOORT_EN],
                         news_colour=_KLEUR_EN.get(uit.get("kleur_nieuws")),
                         photo=CheckPhotoOut(found=bool(uit["foto"].get("gevonden")), page=uit["foto"].get("gevonden"),
                                             checked=uit["foto"].get("geopend", 0)) if uit.get("foto") else None)


def _correctie_uit(c: dict | None) -> CheckCorrectionOut | None:
    if not c:
        return None
    return CheckCorrectionOut(words=c["woorden"], should_be=c["juist"], url=c.get("url"), publisher=c.get("site"),
                              start=c["begin"], end=c["eind"])


@app.post("/dispute", response_model=DisputeResponse)
async def dispute(
    request: Request,
    conn: sqlite3.Connection = Depends(get_conn),
    config: Config = Depends(get_config),
) -> DisputeResponse:
    """Een uitslag betwisten (E6.S3).

    Zonder expliciete toestemming wordt het artefact nergens bewaard — alleen
    de fingerprint, de betwiste categorie en de betwistingstekst.
    """
    verzoek, afbeelding = await _lees_betwisting(request)

    betwistingstekst = verzoek.dispute_text.strip()
    if not betwistingstekst:
        raise HTTPException(status_code=422, detail="empty dispute text")

    tekst_fp = None
    beeld_fp = None
    artefact: bytes | None = None
    artefact_mime: str | None = None
    if afbeelding is not None:
        try:
            beeld_fp = fingerprint_image(afbeelding, config.model_versions.image_hash)
            ocr = extract_text(afbeelding, config.ocr)
        except TeGroteAfbeelding:
            raise HTTPException(
                status_code=422,
                detail="image has too many pixels to process",
            ) from None
        except (UnidentifiedImageError, OSError, TypeError, DecompressionBombError):
            raise HTTPException(
                status_code=422, detail="unreadable image"
            ) from None
        if ocr.readable:
            tekst_fp = fingerprint_text(
                ocr.text, config.model_versions.text_embedding
            )
        artefact, artefact_mime = afbeelding, "image/png"
    elif verzoek.text and verzoek.text.strip():
        schoon = verzoek.text.strip()
        tekst_fp = fingerprint_text(schoon, config.model_versions.text_embedding)
        # Bij een tekstbetwisting ís de tekst het artefact.
        artefact, artefact_mime = schoon.encode("utf-8"), "text/plain"
    else:
        raise HTTPException(
            status_code=422, detail="no artifact with the dispute"
        )

    vastgelegd = record_dispute(
        conn,
        disputed_category=str(verzoek.disputed_category),
        dispute_text=betwistingstekst,
        claim_id=verzoek.claim_id,
        text_fingerprint=tekst_fp,
        image_fingerprint=beeld_fp,
        artifact=artefact,
        artifact_mime=artefact_mime,
        consent=verzoek.consent_to_store_artifact,
        retention_days=config.retention.artifact_days,
    )

    velden = ["betwiste categorie", "betwistingstekst", "tijdstip"]
    if vastgelegd.stored_artifact:
        velden.append("het artefact zelf, tot de vervaldatum")
    if tekst_fp is not None:
        velden.append("tekst-fingerprint")
    if beeld_fp is not None:
        velden.append("beeld-fingerprint")

    return DisputeResponse(
        dispute_id=vastgelegd.dispute_id,
        stored_artifact=vastgelegd.stored_artifact,
        artifact_expires_at=vastgelegd.artifact_expires_at,
        deletion_key=vastgelegd.deletion_key,
        stored_fields=velden,
    )


async def _lees_betwisting(request: Request) -> tuple[DisputeRequest, bytes | None]:
    """Zelfde twee vormen als /resolve: JSON met tekst, of multipart met bestand."""
    content_type = request.headers.get("content-type", "")

    if content_type.startswith("multipart/form-data"):
        formulier = await request.form()
        bestand = formulier.get("image")
        inhoud = None
        if bestand is not None and not isinstance(bestand, str):
            inhoud = await bestand.read()
            if len(inhoud) > MAX_IMAGE_BYTES:
                raise HTTPException(
                    status_code=413,
                    detail=f"image larger than {MAX_IMAGE_BYTES} bytes",
                )
        velden = {
            sleutel: waarde
            for sleutel, waarde in formulier.items()
            if sleutel != "image" and isinstance(waarde, str)
        }
        toestemming = velden.pop("consent_to_store_artifact", "")
        try:
            verzoek = DisputeRequest(
                **velden,
                consent_to_store_artifact=str(toestemming).lower() in ("true", "1", "ja"),
            )
        except (ValidationError, TypeError, ValueError) as fout:
            raise HTTPException(status_code=422, detail=str(fout)) from None
        return verzoek, inhoud

    try:
        data = await request.json()
        return DisputeRequest(**data), None
    except (ValidationError, TypeError, ValueError) as fout:
        raise HTTPException(
            status_code=422, detail=f"unreadable request: {fout}"
        ) from None


@app.delete("/dispute/{dispute_id}", response_model=DeletionResponse)
def delete_dispute_artifact(
    dispute_id: int,
    request: DeletionRequest,
    conn: sqlite3.Connection = Depends(get_conn),
) -> DeletionResponse:
    """Het verwijderrecht uitoefenen (E6.S3-AC4, B11).

    Herhaalbaar: een tweede keer verwijderen slaagt en verandert niets.
    """
    try:
        delete_artifact(conn, dispute_id, request.deletion_key)
    except DisputeNotFound:
        raise HTTPException(
            status_code=404, detail="dispute not found"
        ) from None
    except DeletionKeyRejected:
        raise HTTPException(
            status_code=403, detail="deletion key does not match"
        ) from None
    return DeletionResponse(dispute_id=dispute_id, artifact_present=False)
