"""Drempels en modelversies uit `config.toml` (DR6).

Bewust zonder defaults in code: ontbreekt of rammelt een waarde, dan weigert
het laden met `ConfigError` in plaats van stil met een ingebakken waarde door
te rekenen.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

_DEFAULT_PATH = Path(__file__).resolve().parent.parent / "config.toml"


class ConfigError(Exception):
    """Configbestand ontbreekt, is onvolledig of inconsistent."""


@dataclass(frozen=True)
class Thresholds:
    text_match: float
    text_related: float
    image_same: int
    # Lagere drempel voor paren waarvan vaststaat dat ze cross-linguaal zijn
    # (#12.4). Cross-linguale gelijkenis ligt structureel lager, dus één drempel
    # mist óf vertalingen óf laat gelijkende ándere claims door.
    text_match_crosslingual: float = 0.85
    # Samenvoegen is ingrijpender dan matchen, dus strenger (E2.S5-AC4).
    cluster_same: float = 0.95
    # Vanaf welke NLI-score een samenvoeging geblokkeerd wordt (PLAN.md #10.4).
    nli_contradiction: float = 0.5
    # Vanaf welke entailment-score de batchcontrole (#21.2) een zin als
    # "beweert deze weerlegde claim" vlagt. Gemeten (BENCHMARK.md §56):
    # beweert min 0,79, weerlegt/bespreekt max 0,66 — 0,7 ligt in het gat.
    # Uitsluitend offline/batch (B17), nooit in het aanvraagpad.
    stance_entailment: float = 0.7
    # De kandidaatpoort van de batchcontrole (#21.5): vanaf welke gelijkenis een
    # zin claim-kandidaat is voor de stance-laag. Bewust lager dan text_match —
    # de resolverdrempel beantwoordt "is dit dezelfde claim?" op bijna-verbatim
    # materiaal; de screeningvraag is "schrijft dit een weerlegde claim na, in
    # eigen woorden?" en parafrase landt op 0,63–0,87 (§59d). Gemeten: §60.
    screening_poort: float = 0.75
    # De rechter (#30.3, B36): vanaf welke score hij *zelfde bewering* zegt,
    # en vanaf welke gelijkenis een kandidaat hem voorgelegd wordt. Zonder
    # deze twee kan de rechter niet aan; ze horen bij zijn modelversie.
    rechter_zelfde: float | None = None
    rechter_vloer: float | None = None
    # Boven de matchdrempel is de rechter een veto: `matched` tenzij hij
    # onder deze (mildere) score blijft. Zonder: overal rechter_zelfde.
    rechter_veto: float | None = None
    # De feitenlaag (#30.3b): vanaf welke gelijkenis een vastgesteld feit de
    # rechter voorgelegd wordt, en vanaf welke score hij *zelfde* zegt.
    feit_vloer: float | None = None
    feit_zelfde: float | None = None
    # De artikellezer (#30.11b): bij een tekst van meerdere eenheden `matched`
    # vanaf `artikel_vloer` als de lezer `artikel_zelfde` haalt.
    artikel_vloer: float | None = None
    artikel_zelfde: float | None = None


@dataclass(frozen=True)
class ModelVersions:
    text_embedding: str
    image_hash: str
    # Relatiemodel voor de clustering-veto (E3.S4-AC3). Alleen offline gebruikt.
    nli: str = ""


@dataclass(frozen=True)
class OcrSettings:
    languages: str
    min_chars: int
    # Harde grens op tesseract-tijd per beeld (#20.1). `pytesseract` SIGKILL't de
    # subprocess bij overschrijding, dus de CPU komt écht vrij. Ná de pixelgrens
    # uit §54 kost de zwaarste legale plaat 4,8s; deze grens ligt daar ruim boven
    # en snijdt het pathologische geval af.
    timeout_seconds: int
    # Schrift (zoals Tesseract-OSD het noemt) → pakketten voor dat schrift
    # (#25.21). Leeg of `per_schrift` uit: alleen `languages`.
    schriften: dict[str, str] = field(default_factory=dict)
    # Aanzetten verandert wat de resolver op beelden antwoordt: een release (B22).
    per_schrift: bool = False
    # Onder deze OSD-zekerheid blijft het `languages`: nooit slechter dan zonder.
    schrift_zekerheid: float = 0.0
    # Tesseract-OSD geeft standaard op onder 50 tekens; een kop of meme heeft
    # er vaak minder (#25.21).
    schrift_min_tekens: int = 50
    # Twee keer lezen bij twijfel (#25.22): tussen deze ondergrens en
    # `schrift_zekerheid` leest de OCR met `languages` én met het schrift, en
    # houdt de zekerste lezing. `None` is gelijk aan `schrift_zekerheid`: geen
    # twijfelband. Aanzetten verandert wat de resolver op beelden antwoordt: een
    # release (B22).
    schrift_ondergrens: float | None = None
    # Een tweede lezing telt alleen als minstens dit deel van haar letters in het
    # herkende schrift staat; anders was de herkenning fout (§107).
    schrift_min_aandeel: float = 0.5


@dataclass(frozen=True)
class RetentionSettings:
    """Bewaartermijn voor artefacten op de betwistingsroute (E6.S3-AC5, DR9)."""

    artifact_days: int
    sweep_interval_hours: int


@dataclass(frozen=True)
class RateLimitSettings:
    """Per-IP token-bucket (#20.2). Beschermt de enkelvoudige instantie tegen
    een verzoekstroom; de cross-instantie-variant staat op de roadmap."""

    enabled: bool
    requests_per_minute: int
    burst: int


@dataclass(frozen=True)
class ResolverIdentity:
    """Wie geeft dit antwoord? (PROTOCOL §7, #11.3)

    §7 schrijft voor dat een client antwoorden van meerdere resolvers naast
    elkaar toont *met de bron erbij*. Zonder een veld dat de resolver noemt kan
    dat alleen zolang niemand een antwoord doorgeeft of bewaart — en juist dan
    is federatie aan de orde.
    """

    id: str
    name: str


@dataclass(frozen=True)
class ConsensusSettings:
    """Wat telt als onafhankelijke bevestiging (DR7, B12, #17.7).

    `onbekende_uitgever` bepaalt wat er gebeurt met een factcheck op een host
    die niet in `uitgevers.json` staat. `telt-niet-mee` is de strenge stand en
    volgt de conventie "twijfel versoepelt nooit": een uitgever die we niet
    kennen mag geen consensus dragen. `telt-mee` valt terug op de naamregel uit
    #17.6. Het verschil is groot — 578 tegen 637 clusters — en het zit vooral in
    de onvolledigheid van het register, niet in echte afhankelijkheid (§50).
    """

    onbekende_uitgever: str


@dataclass(frozen=True)
class BenchmarkSettings:
    """Vanaf hoeveel claims een taal een eigen benchmarkcijfer móét hebben
    (#25.1, B14 aangescherpt). Daaronder staat een taal in de index zonder
    precisiebelofte; daarboven weigert de benchmark zonder testparen."""

    min_claims_voor_cijfer: int


@dataclass(frozen=True)
class VariantSettings:
    """Claimvarianten in de resolver (#25.17). Aanzetten verandert wat de
    resolver antwoordt: een release (B22).

    `stance_in_zinstaal` (#25.31): bij een cross-linguaal paar beslist de
    stance-laag van de batchcontrole óók op de variant van de claim in de taal
    van de zin; "beweert" alleen als beide de drempel halen."""
    in_resolver: bool = False
    stance_in_zinstaal: bool = False


@dataclass(frozen=True)
class RechterSettings:
    """De rechter (#30.3, B36): een bijgetrainde cross-encoder tussen breed
    zoeken en `categorize`. `model` is de versie uit de hash van de gewichten
    (DR6), `pad` de map met die gewichten, `diepte` hoeveel kandidaten boven
    de vloer hij hoogstens leest. Aanzetten is een release (B22)."""
    aan: bool = False
    model: str = ""
    pad: str = ""
    diepte: int = 5


@dataclass(frozen=True)
class FeitenSettings:
    """De feitenlaag (#30.3b): een vraag die een vastgesteld feit uit de kern
    is, krijgt geen rood of omstreden oordeel als `matched`. Herkennen gaat
    met de rechter, dus zonder rechter geen laag. Aanzetten is een release (B22)."""
    aan: bool = False


@dataclass(frozen=True)
class ArtikellezerSettings:
    """De artikellezer (#30.11b): een bijgetrainde lezer die zegt of een tekst
    van meerdere eenheden een bekende bewering doet, ook bij lage gelijkenis.
    `model` is de versie uit de hash van de gewichten (DR6), `pad` de map,
    `diepte` hoeveel kandidaten hij leest. Aanzetten is een release (B22)."""
    aan: bool = False
    model: str = ""
    pad: str = ""
    diepte: int = 5


@dataclass(frozen=True)
class ArtikelSettings:
    """De bewering uit een artikel (#30.11): een tekst met twee of meer zinnen
    wordt gezocht als de hele tekst plus elke zin (`doublecheck.zinnen`).
    Aanzetten verandert wat de resolver antwoordt: een release (B22)."""
    per_zin: bool = False


@dataclass(frozen=True)
class VraagvormSettings:
    """Vraag en bewering vinden elkaar (#25.36): een vraag wordt ook als
    bewering gezocht. Aanzetten verandert wat de resolver en Ask antwoorden:
    een release (B22)."""
    aan: bool = False


@dataclass(frozen=True)
class BonnetjesSettings:
    """Wanneer een check-link offline heet, en wanneer een uitgever een
    waarschuwing krijgt (#25.9). Streng in één richting: ten onrechte
    "offline" is een foute uitspraak over een redactie."""

    offline_na_uren: int = 24
    waarschuwing_min_dood: int = 10
    waarschuwing_aandeel: float = 0.2


@dataclass(frozen=True)
class BerichtcontroleSettings:
    """De controle per bericht, `POST /check` (B43, B45; PLAN #31.12). Uit tot
    zero data retention bij Anthropic actief is (B43). Model, vraag,
    herkansing, feitenstap en de ijking van de meter zijn de versies waarmee
    gemeten is (DR6); wijkt de code af, dan weigert de controle. Aanzetten is
    een release (B22)."""

    aan: bool = False
    model_id: str = ""
    vraag: str = ""
    herkansing: str = ""
    feitenstap: str = ""
    ijking: str = ""
    vorm: str = ""  # de vormvraag van de twee regels (#31.15); leeg = geen regels
    detail: str = ""  # de detailvraag van B48 (#32.3a); leeg = geen *klopt grotendeels*
    beweringen: str = ""  # "beweringen eerst" bij een screenshot (#32.6); leeg = alleen de tekst zoeken
    beweringen_model: str = ""
    vloer: str = ""  # de vloerstap van B50 (#32.0m): rood op algemene kennis; leeg = uit
    vloer_model: str = ""
    lezer: str = "lezer-v1"  # B51: de vraag aan Sonnet, die de top 10 van de zoekdienst leest
    zoeker: str = "brave-v1"  # B51: de zoekdienst die de grote media ziet (Brave)
    beeld: bool = False  # het beeld mee naar het model: een besluit van de PO (REQUIREMENTS §9)
    kring1: bool = True  # de eerste kring van #32.7a: een check uit de database die één kant op wijst, zonder model
    herkomst: str = ""  # de herkomstcontrole van #32.3e: één zoekvraag op de site die het screenshot noemt; leeg = uit
    speuren: bool = False  # de speurstap van #32.40: bij *onzeker* zoekt de lezer zelf verder (alleen lezer-v8)
    fotobron: str = ""  # #32.54: de foto bij de bron na het oordeel (`fotobron.VERSIES`); leeg = uit
    speurvraag_model: str = ""  # het kleine model dat bij lezer-v9 vooraf de zoekvragen bedenkt (#32.41); leeg = geen v9
    dagplafond_dollar: float = 0.0
    cache: bool = False
    kosten_db: str = ""


@dataclass(frozen=True)
class BeeldstapSettings:
    """De beeldstap (PLAN #32.35, deel 2 van het releasevoorstel): het beeld van een screenshot bevestigt checks via de
    punten van de virale beelden in de factcheckartikelen. De index draagt zijn versies; wijkt er een af, dan weigert de
    stap (DR6). Uit tot een meting en een release (B22)."""

    aan: bool = False
    index: str = ""  # de map van de volle beeldindex (`beeldindexbouw`)
    punten: str = ""  # de versie van de punten, `beeldvraag.PUNTVERSIE`
    vergelijking: str = ""  # `beeldvraag.VERGELIJKING`
    rol: str = ""  # de rolvraag die *viraal* zei
    drempel_pdq: int = 31
    min_punten: int = 50
    min_dekking: float = 0.10
    top_beeldtekst: int = 5  # zoveel artikelen via de tekst op hun virale beelden, naast de checks


@dataclass(frozen=True)
class Config:
    thresholds: Thresholds
    model_versions: ModelVersions
    ocr: OcrSettings
    retention: RetentionSettings
    consensus: ConsensusSettings
    resolver: ResolverIdentity
    ratelimit: RateLimitSettings
    benchmark: BenchmarkSettings
    varianten: VariantSettings = field(default_factory=VariantSettings)
    vraagvorm: VraagvormSettings = field(default_factory=VraagvormSettings)
    bonnetjes: BonnetjesSettings = field(default_factory=BonnetjesSettings)
    rechter: RechterSettings = field(default_factory=RechterSettings)
    feiten: FeitenSettings = field(default_factory=FeitenSettings)
    artikel: ArtikelSettings = field(default_factory=ArtikelSettings)
    artikellezer: ArtikellezerSettings = field(default_factory=ArtikellezerSettings)
    berichtcontrole: BerichtcontroleSettings = field(default_factory=BerichtcontroleSettings)
    beeldstap: BeeldstapSettings = field(default_factory=BeeldstapSettings)


def _require(raw: dict, section: str, key: str):
    if section not in raw:
        raise ConfigError(f"config mist sectie [{section}]")
    if key not in raw[section]:
        raise ConfigError(f"config mist [{section}] {key!r}")
    return raw[section][key]


def _optioneel_getal(raw: dict, sleutel: str) -> float | None:
    waarde = raw.get("thresholds", {}).get(sleutel)
    return None if waarde is None else float(waarde)


def load_config(path: str | Path | None = None) -> Config:
    config_path = Path(path) if path is not None else _DEFAULT_PATH
    try:
        raw = tomllib.loads(config_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ConfigError(f"configbestand niet gevonden: {config_path}") from None
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"configbestand ongeldig: {config_path}: {exc}") from None

    thresholds = Thresholds(
        text_match=float(_require(raw, "thresholds", "text_match")),
        text_related=float(_require(raw, "thresholds", "text_related")),
        image_same=int(_require(raw, "thresholds", "image_same")),
        cluster_same=float(_require(raw, "thresholds", "cluster_same")),
        nli_contradiction=float(_require(raw, "thresholds", "nli_contradiction")),
        stance_entailment=float(_require(raw, "thresholds", "stance_entailment")),
        screening_poort=float(_require(raw, "thresholds", "screening_poort")),
        text_match_crosslingual=float(
            _require(raw, "thresholds", "text_match_crosslingual")
        ),
        rechter_zelfde=_optioneel_getal(raw, "rechter_zelfde"),
        rechter_vloer=_optioneel_getal(raw, "rechter_vloer"),
        rechter_veto=_optioneel_getal(raw, "rechter_veto"),
        feit_vloer=_optioneel_getal(raw, "feit_vloer"),
        feit_zelfde=_optioneel_getal(raw, "feit_zelfde"),
        artikel_vloer=_optioneel_getal(raw, "artikel_vloer"),
        artikel_zelfde=_optioneel_getal(raw, "artikel_zelfde"),
    )
    versions = ModelVersions(
        text_embedding=str(_require(raw, "model_versions", "text_embedding")),
        image_hash=str(_require(raw, "model_versions", "image_hash")),
        nli=str(_require(raw, "model_versions", "nli")),
    )
    ocr = OcrSettings(
        languages=str(_require(raw, "ocr", "languages")),
        min_chars=int(_require(raw, "ocr", "min_chars")),
        timeout_seconds=int(_require(raw, "ocr", "timeout_seconds")),
        schriften={str(k): str(v) for k, v in raw.get("ocr", {}).get("schriften", {}).items()},
        schrift_zekerheid=float(raw.get("ocr", {}).get("schrift_zekerheid", 0.0)),
        schrift_min_tekens=int(raw.get("ocr", {}).get("schrift_min_tekens", 50)),
        per_schrift=bool(raw.get("ocr", {}).get("per_schrift", False)),
        schrift_ondergrens=float(raw.get("ocr", {}).get(
            "schrift_ondergrens", raw.get("ocr", {}).get("schrift_zekerheid", 0.0))),
        schrift_min_aandeel=float(raw.get("ocr", {}).get("schrift_min_aandeel", 0.5)),
    )
    if ocr.timeout_seconds <= 0:
        raise ConfigError(
            f"[ocr] timeout_seconds moet positief zijn, kreeg {ocr.timeout_seconds}"
        )
    retention = RetentionSettings(
        artifact_days=int(_require(raw, "retention", "artifact_days")),
        sweep_interval_hours=int(_require(raw, "retention", "sweep_interval_hours")),
    )
    resolver = ResolverIdentity(
        id=str(_require(raw, "resolver", "id")),
        name=str(_require(raw, "resolver", "name")),
    )
    ratelimit = RateLimitSettings(
        enabled=bool(_require(raw, "ratelimit", "enabled")),
        requests_per_minute=int(_require(raw, "ratelimit", "requests_per_minute")),
        burst=int(_require(raw, "ratelimit", "burst")),
    )
    if ratelimit.requests_per_minute <= 0 or ratelimit.burst <= 0:
        raise ConfigError(
            "[ratelimit] requests_per_minute en burst moeten positief zijn, kreeg "
            f"{ratelimit.requests_per_minute} en {ratelimit.burst}"
        )
    consensus = ConsensusSettings(
        onbekende_uitgever=str(_require(raw, "consensus", "onbekende_uitgever")),
    )
    benchmark = BenchmarkSettings(
        min_claims_voor_cijfer=int(_require(raw, "benchmark", "min_claims_voor_cijfer")),
    )
    if benchmark.min_claims_voor_cijfer < 1:
        raise ConfigError(
            "[benchmark] min_claims_voor_cijfer moet minstens 1 zijn, kreeg "
            f"{benchmark.min_claims_voor_cijfer}"
        )
    if consensus.onbekende_uitgever not in {"telt-mee", "telt-niet-mee"}:
        raise ConfigError(
            "[consensus] onbekende_uitgever moet 'telt-mee' of 'telt-niet-mee' "
            f"zijn, kreeg {consensus.onbekende_uitgever!r}"
        )

    if not 0.0 < thresholds.text_related < thresholds.text_match <= 1.0:
        raise ConfigError(
            "drempels inconsistent: vereist 0 < text_related < text_match <= 1, "
            f"kreeg text_related={thresholds.text_related} text_match={thresholds.text_match}"
        )
    if not thresholds.text_match <= thresholds.cluster_same <= 1.0:
        raise ConfigError(
            "clusterdrempel moet minstens de matchdrempel zijn, kreeg "
            f"cluster_same={thresholds.cluster_same} text_match={thresholds.text_match}"
        )
    if not (
        thresholds.text_related
        <= thresholds.text_match_crosslingual
        <= thresholds.text_match
    ):
        raise ConfigError(
            "cross-linguale drempel moet tussen text_related en text_match liggen,"
            f" kreeg {thresholds.text_match_crosslingual} bij"
            f" related={thresholds.text_related} match={thresholds.text_match}"
        )
    if not 0.0 < thresholds.stance_entailment <= 1.0:
        raise ConfigError(
            "stance-drempel moet in (0, 1] liggen, kreeg"
            f" {thresholds.stance_entailment}"
        )
    if not 0.0 < thresholds.screening_poort <= thresholds.text_match:
        raise ConfigError(
            "screening-poort moet in (0, text_match] liggen — hoger dan de"
            " resolverdrempel zou de batchcontrole strenger maken dan de"
            f" resolver zelf; kreeg {thresholds.screening_poort} bij"
            f" text_match={thresholds.text_match}"
        )
    if thresholds.image_same < 0:
        raise ConfigError(f"image_same moet >= 0 zijn, kreeg {thresholds.image_same}")
    if not versions.text_embedding or not versions.image_hash or not versions.nli:
        raise ConfigError("modelversies mogen niet leeg zijn")
    if not 0.0 < thresholds.nli_contradiction < 1.0:
        raise ConfigError(
            f"nli_contradiction moet tussen 0 en 1 liggen, kreeg "
            f"{thresholds.nli_contradiction}"
        )
    if ocr.min_chars < 1 or not ocr.languages:
        raise ConfigError("ocr-instellingen ongeldig")
    if retention.artifact_days < 1:
        raise ConfigError("bewaartermijn moet minstens één dag zijn")
    if retention.sweep_interval_hours < 1:
        raise ConfigError("opruiminterval moet minstens één uur zijn")
    ruw_bonnetjes = raw.get("bonnetjes", {})
    bonnetjes = BonnetjesSettings(
        offline_na_uren=int(ruw_bonnetjes.get("offline_na_uren", 24)),
        waarschuwing_min_dood=int(ruw_bonnetjes.get("waarschuwing_min_dood", 10)),
        waarschuwing_aandeel=float(ruw_bonnetjes.get("waarschuwing_aandeel", 0.2)),
    )
    if bonnetjes.offline_na_uren < 1 or not 0.0 < bonnetjes.waarschuwing_aandeel <= 1.0:
        raise ConfigError("bonnetjes-instellingen ongeldig")

    ruw_rechter = raw.get("rechter", {})
    rechter = RechterSettings(aan=bool(ruw_rechter.get("aan", False)), model=str(ruw_rechter.get("model", "")),
                              pad=str(ruw_rechter.get("pad", "")), diepte=int(ruw_rechter.get("diepte", 5)))
    if rechter.aan and (not rechter.model or not rechter.pad or thresholds.rechter_zelfde is None
                        or thresholds.rechter_vloer is None or rechter.diepte < 1):
        raise ConfigError("de rechter staat aan zonder model, pad, diepte of drempels (DR6)")

    feiten = FeitenSettings(aan=bool(raw.get("feiten", {}).get("aan", False)))
    ruw_lezer = raw.get("artikellezer", {})
    lezer = ArtikellezerSettings(aan=bool(ruw_lezer.get("aan", False)), model=str(ruw_lezer.get("model", "")),
                                 pad=str(ruw_lezer.get("pad", "")), diepte=int(ruw_lezer.get("diepte", 5)))
    if lezer.aan and (not lezer.model or not lezer.pad or lezer.diepte < 1 or thresholds.artikel_vloer is None
                      or thresholds.artikel_zelfde is None):
        raise ConfigError("de artikellezer staat aan zonder model, pad, diepte of drempels (DR6)")
    if feiten.aan and (not rechter.aan or thresholds.feit_vloer is None or thresholds.feit_zelfde is None):
        raise ConfigError("de feitenlaag staat aan zonder rechter of zonder feit_vloer en feit_zelfde")
    ruw_controle = raw.get("berichtcontrole", {})
    berichtcontrole = BerichtcontroleSettings(
        aan=bool(ruw_controle.get("aan", False)),
        **{k: str(ruw_controle.get(k, "")) for k in ("model_id", "vraag", "herkansing", "feitenstap", "ijking",
                                                     "vorm", "detail", "beweringen", "beweringen_model",
                                                     "vloer", "vloer_model", "herkomst", "kosten_db", "lezer", "zoeker",
                                                     "speurvraag_model", "fotobron")},
        dagplafond_dollar=float(ruw_controle.get("dagplafond_dollar", 0.0)),
        cache=bool(ruw_controle.get("cache", False)),
        kring1=bool(ruw_controle.get("kring1", True)),
        beeld=bool(ruw_controle.get("beeld", False)),
        speuren=bool(ruw_controle.get("speuren", False)),
    )
    from doublecheck.fotobron import VERSIES as FOTOVERSIES

    if berichtcontrole.fotobron and berichtcontrole.fotobron not in FOTOVERSIES:
        raise ConfigError(f"[berichtcontrole] fotobron {berichtcontrole.fotobron!r} bestaat niet in de code (DR6)")
    if berichtcontrole.aan and (not all((berichtcontrole.model_id, berichtcontrole.vraag, berichtcontrole.herkansing,
                                         berichtcontrole.feitenstap, berichtcontrole.ijking,
                                         berichtcontrole.kosten_db))
                                or berichtcontrole.dagplafond_dollar <= 0):
        raise ConfigError("de berichtcontrole staat aan zonder versies, ijking of dagplafond (DR6)")
    ruw_stap = raw.get("beeldstap", {})
    beeldstap = BeeldstapSettings(
        aan=bool(ruw_stap.get("aan", False)),
        **{k: str(ruw_stap.get(k, "")) for k in ("index", "punten", "vergelijking", "rol")},
        drempel_pdq=int(ruw_stap.get("drempel_pdq", 31)), min_punten=int(ruw_stap.get("min_punten", 50)),
        min_dekking=float(ruw_stap.get("min_dekking", 0.10)), top_beeldtekst=int(ruw_stap.get("top_beeldtekst", 5)),
    )
    if beeldstap.aan and not all((beeldstap.index, beeldstap.punten, beeldstap.vergelijking, beeldstap.rol)):
        raise ConfigError("de beeldstap staat aan zonder index of versies (DR6)")

    return Config(
        thresholds=thresholds,
        model_versions=versions,
        ocr=ocr,
        retention=retention,
        consensus=consensus,
        resolver=resolver,
        ratelimit=ratelimit,
        benchmark=benchmark,
        varianten=VariantSettings(
            in_resolver=bool(raw.get("varianten", {}).get("in_resolver", False)),
            stance_in_zinstaal=bool(raw.get("varianten", {}).get("stance_in_zinstaal", False)),
        ),
        vraagvorm=VraagvormSettings(aan=bool(raw.get("vraagvorm", {}).get("aan", False))),
        bonnetjes=bonnetjes,
        rechter=rechter,
        feiten=feiten,
        artikel=ArtikelSettings(per_zin=bool(raw.get("artikel", {}).get("per_zin", False))),
        artikellezer=lezer,
        berichtcontrole=berichtcontrole,
        beeldstap=beeldstap,
    )
