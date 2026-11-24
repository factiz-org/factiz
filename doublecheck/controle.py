"""Batchcontrole: documenten langs bekend-weerlegde beweringen (PLAN.md #21.2).

Dit is B17 als product­oppervlak: geen nieuw resolverhart, maar de bestaande
primitief in een batch-jas. N documenten erin — modeluitvoer, een scrape, een
trainingsset — en per document de zinnen eruit die een weerlegde claim als waar
brengen, mét de bronnen erbij (DR1).

Twee lagen nemen de beslissing, hersneden na de echte-datameting (§59, #21.5):

1. **Is de zin kandidaat voor een bekende claim?** Gelijkenis boven de eigen
   `screening_poort` (DR6, config), met de DR8-tegenspraakcheck als veto: een
   zin met een ander getal of een negatieflip is een ándere bewering. De
   resolverdrempel (0,92) is hier bewust niet het instrument — die beantwoordt
   "is dit dezelfde claim?" op bijna-verbatim materiaal, terwijl parafrase op
   0,63–0,87 landt (§59d). Dit oppervlak kent géén resolvercategorieën toe
   (geen `matched`/`related`-woordenschat), dus "één plek zet de categorie"
   (DR4) blijft onaangetast.
2. **Brengt het document hem als waar?** Dat beslist de stance-laag (§56) op
   een **venster**: de zin plus haar buurzinnen als premise. Op echte
   weerlegpagina's isoleert de splitser het claimcitaat ("Claim: …",
   "Says …", kopregels) en een losse herformulering entailt de claim (§59c);
   met het oordeel in de premise gaat de val niet af — precies de conditie
   waarin §56 de motor mat. En **weerlegt wint**: een document dat de claim
   érgens ontkracht, vlagt hem nérgens. Twijfel versoepelt nooit.

De stance-scores zeggen *of het document de claim brengt*, nooit of de claim
waar is — het oordeel blijft van de factchecker (DR2, B10).

Lokaal en zonder spoor (DR3): niets wordt bewaard of gelogd; het rapport is de
eigen data van de aanroeper, terug aan de aanroeper. Wél reist de hele
meetopstelling mee — modelversies, drempels, corpusstand, tijdstip — zodat een
uitkomst navolgbaar is zonder ons te geloven (B17: auditspoor).

Bekende beperkingen, bewust gelaten: de zinsplitser oversplitst op afkortingen
("bijv. de") — een fragment wordt dan los gezocht, wat dekking kost maar geen
valse vlag geeft; en de retrieval zelf blijft het recall-plafond: wat niet
boven de poort komt, bereikt de stance nooit (§59d, §60).
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable
from urllib.parse import urlparse

from doublecheck.config import load_config
from doublecheck.embedding import TextFingerprint, fingerprint_texts
from doublecheck.relation import contradicts
from doublecheck.search import ensure_index_matches_version, ensure_variants_match_version, search_text
from doublecheck.storage import connect
from doublecheck.taal import zijn_verschillende_talen

# Korter dan dit draagt geen claim ("Ja.", "Echt?") en vervuilt alleen de zoek.
_MIN_ZINLENGTE = 10

# De stance-premise is de zin plus zoveel buurzinnen aan weerszijden (#21.5):
# het oordeel staat op weerlegpagina's náást het citaat, niet erin. Te korte
# buurzinnen ("Onjuist.") doen hier wél mee — ze dragen juist het oordeel.
_VENSTER = 2
# Boven dit aantal tekens krimpt het venster, zodat de NLI-truncatie niet
# stilletjes het oordeel aan het eind afsnijdt.
_VENSTER_MAX_TEKENS = 700

_ZINSEINDE = re.compile(
    # Latijnse einders alleen vóór wit of tekstslot, zodat "3.5 mm" heel
    # blijft; schriften met een eigen zinseinde (CJK 。, Arabisch ؟,
    # Devanagari ।) zetten geen spatie na het teken en splitsen altijd.
    r"(?:[.!?…]+(?=\s|$))|(?:[。！？؟।॥։።။]+)"
)


def _zinnen(tekst: str) -> list[str]:
    """Zinnen uit een document, over schriftgrenzen heen (schriftpaneel)."""
    delen = _ZINSEINDE.split(tekst)
    return [zin for zin in (deel.strip() for deel in delen) if zin]


def _venster(zinnen: list[str], index: int) -> str:
    """De stance-premise rond zin `index`: zin plus buurzinnen (§59c)."""
    for breedte in (_VENSTER, 1):
        stuk = " ".join(zinnen[max(0, index - breedte): index + breedte + 1])
        if len(stuk) <= _VENSTER_MAX_TEKENS:
            return stuk
    return zinnen[index]


# Vraagtekens over schriften heen; ASCII-';' hoort hier bewust niet bij, ook
# al schrijft het Grieks er vragen mee — elke puntkomma als vraag lezen zou
# overbreed zijn, en een gemiste vraagvorm kost hoogstens een vlag te veel
# op een claim die dan alsnog unaniem onwaar moet zijn.
_VRAAGTEKENS = ("?", "؟", "？", "՞", "⁇", "⁈", "⁉", ";")


def _is_vraagvorm(tekst: str) -> bool:
    """Een claim die een vraag is, is geen bewering — en kan dus nooit
    "nageschreven als waar" worden (§60b: "Le niveau de la mer
    augmente-t-il … ?" stond als claim in het corpus)."""
    return tekst.rstrip().endswith(_VRAAGTEKENS)


def _url_sleutel(url: str) -> str:
    """Host-plus-pad als vergelijkingssleutel voor de bonnetjesregel; een
    tekst die geen URL is levert de lege sleutel en matcht nooit."""
    try:
        delen = urlparse(url.strip())
    except ValueError:
        return ""
    if not delen.netloc:
        return ""
    return delen.netloc.lower().removeprefix("www.") + delen.path.rstrip("/")


@dataclass(frozen=True)
class Bron:
    """Eén bonnetje (DR1): wie heeft dit gecheckt, wat kwam eruit, waar."""

    publisher: str
    verdict_normalized: str
    verdict_original: str
    url: str
    review_date: str


@dataclass(frozen=True)
class Treffer:
    # `zin` is het anker; de stance-scores zijn gemeten op het vénster rond
    # deze zin (#21.5), zodat het oordeel naast een citaat meetelt.
    zin: str
    claim_id: str
    claim_tekst: str
    similarity: float
    crosslinguaal: bool
    # "beweert": het venster brengt de weerlegde claim als waar — kandidaat-
    # vlag (de dóórslag valt op documentniveau: weerlegt wint).
    # "weerlegt": het venster ontkracht hem — herkend, nooit gevlagd (§56).
    # "overig": bevat de claim wel, maar neemt geen duidelijke positie in.
    stance: str
    # None wanneer de stance niet uit de NLI komt maar uit een bonnetje
    # (`grond == "bron-url"`): dan is er geen gemeten score om te tonen.
    entailment: float | None
    contradiction: float | None
    # "nli": het venster-oordeel van §56/§60. "bron-url": het document ís de
    # vastgelegde factcheck-URL van deze claim — het bonnetje is de grond.
    grond: str
    # Alleen een unaniem-onwaar, niet-vraagvormige claim is vlagbaar (§60b);
    # B17 belooft "bekend-wéérlegde beweringen", niet "gecheckte".
    vlagbaar: bool
    bronnen: tuple[Bron, ...]
    # De laagste entailment op de varianten van de claim in de taal van de zin
    # (#25.31), of None als die regel niet meedeed: uitgeschakeld, hetzelfde
    # taalpaar, of geen variant in die taal.
    entailment_zinstaal: float | None = None


@dataclass(frozen=True)
class DocumentUitslag:
    document_id: str
    zinnen: int
    treffers: tuple[Treffer, ...]

    @property
    def beweert(self) -> tuple[Treffer, ...]:
        """De vlaggen, met **weerlegt wint** op documentniveau (#21.5): een
        claim die dit document érgens ontkracht, wordt nérgens gevlagd — ook
        niet als een andere zin hem buiten het venster van het oordeel
        beweert. Twijfel versoepelt nooit; beide zinnen blijven als treffer
        zichtbaar in het logboek."""
        weerlegd = {t.claim_id for t in self.treffers if t.stance == "weerlegt"}
        return tuple(
            t for t in self.treffers
            if t.stance == "beweert" and t.vlagbaar and t.claim_id not in weerlegd
        )


@dataclass(frozen=True)
class Controlerapport:
    """Het logboek: uitkomsten mét de volledige meetopstelling erbij."""

    gestart_op: str
    model_versions: dict[str, str]
    thresholds: dict[str, float]
    corpus: dict[str, object]
    documenten: tuple[DocumentUitslag, ...]
    # De schakelaars die meebeslissen: zoeken over varianten (#21.8) en de
    # stance in de taal van de zin (#25.31). Ook die horen bij de opstelling.
    regels: dict[str, bool] = field(default_factory=dict)

    @property
    def gevlagd(self) -> int:
        return sum(len(uitslag.beweert) for uitslag in self.documenten)


def _stance_uit_config(config) -> Callable[[str, str], tuple[float, float]]:
    from doublecheck import nli  # torch/transformers pas laden bij echt gebruik

    versie = config.model_versions.nli

    def stance(premise: str, hypothese: str) -> tuple[float, float]:
        return nli.stance_scores(premise, hypothese, versie)

    return stance


def _bronnen(conn: sqlite3.Connection, claim_id: str) -> tuple[Bron, ...]:
    rijen = conn.execute(
        "SELECT publisher, verdict_normalized, verdict_original, url, review_date"
        " FROM factcheck WHERE claim_id = ? ORDER BY review_date DESC, url",
        (claim_id,),
    ).fetchall()
    return tuple(Bron(*rij) for rij in rijen)


_ISO_DATUM = "[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]"


def _corpusstand(conn: sqlite3.Connection) -> dict[str, object]:
    """Corpusstand voor het logboek — mét de rommel geteld, niet weggemoffeld.

    De feed draagt corrupte datums (12,3% leeg, en losse uitschieters als
    "2923-01-02"); een auditlogboek dat zo'n datum als "nieuwste check" meldt
    is zelf niet te vertrouwen. Dus: de nieuwste *geldige* datum (ISO-vorm,
    niet in de toekomst), plus de telling van wat daarbuiten valt. De echte
    schoonmaak hoort in de feedimport (#21.4), niet in deze query.
    """
    vandaag = datetime.now(timezone.utc).date().isoformat()
    claims = conn.execute("SELECT COUNT(*) FROM claim").fetchone()[0]
    checks = conn.execute("SELECT COUNT(*) FROM factcheck").fetchone()[0]
    nieuwste, geldig = conn.execute(
        "SELECT MAX(review_date), COUNT(*) FROM factcheck"
        " WHERE review_date GLOB ? AND review_date <= ?",
        (_ISO_DATUM, vandaag),
    ).fetchone()
    return {
        "claims": claims,
        "factchecks": checks,
        "nieuwste_check": nieuwste,
        "zonder_geldige_datum": checks - geldig,
    }


def _beoordeel_zin(
    conn: sqlite3.Connection,
    document_id: str,
    zinnen: list[str],
    index: int,
    fingerprint: TextFingerprint,
    drempels,
    stance: Callable[[str, str], tuple[float, float]],
    varianten: bool = False,
    stance_in_zinstaal: bool = False,
) -> Treffer | None:
    # Zoeken zoals de resolver: met de claimvarianten als de schakelaar aan
    # staat (#21.8), anders bit-identiek aan het pad van vóór de varianten.
    kandidaten = search_text(conn, fingerprint, varianten=varianten)
    if not kandidaten:
        return None
    beste = kandidaten[0]
    return _beoordeel_kandidaat(
        conn, document_id, zinnen[index], lambda: _venster(zinnen, index), fingerprint,
        beste.claim_id, beste.similarity, drempels, stance, stance_in_zinstaal)


def _beoordeel_kandidaat(
    conn: sqlite3.Connection,
    document_id: str,
    zin: str,
    premisse: Callable[[], str],
    fingerprint: TextFingerprint,
    claim_id: str,
    similarity: float,
    drempels,
    stance: Callable[[str, str], tuple[float, float]],
    stance_in_zinstaal: bool = False,
) -> Treffer | None:
    """Eén kandidaat-claim voor één eenheid: de poort, het DR8-veto, de
    bonnetjesregel en de stance op het venster. `premisse` geeft het venster
    pas als de stance het nodig heeft."""
    # De eigen poort van de screeningtaak (§59d), niet de resolver-0,92.
    if similarity < drempels.screening_poort:
        return None
    rij = conn.execute(
        "SELECT canonical_text, language FROM claim WHERE claim_id = ?",
        (claim_id,),
    ).fetchone()
    if rij is None:  # pragma: no cover - fingerprint zonder claim is corrupt
        return None
    claim_tekst, claim_taal = rij

    # DR8 blijft het veto vóór de stance: een ander getal of een negatieflip
    # is een ándere bewering, geen kandidaat.
    if contradicts(
        fingerprint.numbers, fingerprint.negations, claim_tekst,
        artefact_text=zin, artefact_negation_tokens=fingerprint.negation_tokens,
    ):
        return None
    crosslinguaal = zijn_verschillende_talen(fingerprint.language, claim_taal)
    bronnen = _bronnen(conn, claim_id)

    # De bonnetjesregel (§60b): is dit document zélf een vastgelegde
    # factcheck van deze claim, dan weerlegt het hem per definitie — het
    # bonnetje is de grond, geen NLI-oordeel nodig. Geef gescrapete
    # documenten dus hun bron-URL als document_id.
    entailment_zinstaal = None
    eigen_sleutel = _url_sleutel(document_id)
    if eigen_sleutel and eigen_sleutel in {_url_sleutel(b.url) for b in bronnen}:
        label, grond = "weerlegt", "bron-url"
        entailment = contradiction = None
    else:
        grond = "nli"
        venster = premisse()
        entailment, contradiction = stance(venster, claim_tekst)
        if entailment >= drempels.stance_entailment:
            label = "beweert"
        elif contradiction >= drempels.stance_entailment:
            label = "weerlegt"
        else:
            label = "overig"
        # Over twee talen heen ziet het NLI-model te snel dezelfde bewering
        # (§100, #25.31). Staat de claim ook in de taal van de zin, dan moet
        # het daar óók "beweert" zeggen; twijfel versoepelt nooit, dus elke
        # variant in die taal telt, en de laagste beslist.
        if stance_in_zinstaal and crosslinguaal and label == "beweert":
            teksten = [r[0] for r in conn.execute(
                "SELECT DISTINCT text FROM claim_variant WHERE claim_id = ? AND language = ?"
                " ORDER BY text", (claim_id, fingerprint.language))]
            if teksten:
                entailment_zinstaal = min(stance(venster, t)[0] for t in teksten)
                if entailment_zinstaal < drempels.stance_entailment:
                    label = "overig"
    vlagbaar = (
        not _is_vraagvorm(claim_tekst)
        and bool(bronnen)
        and all(b.verdict_normalized == "onwaar" for b in bronnen)
    )
    return Treffer(
        zin=zin,
        claim_id=claim_id,
        claim_tekst=claim_tekst,
        similarity=round(float(similarity), 4),
        crosslinguaal=crosslinguaal,
        stance=label,
        entailment=None if entailment is None else round(float(entailment), 4),
        contradiction=None if contradiction is None else round(float(contradiction), 4),
        grond=grond,
        vlagbaar=vlagbaar,
        bronnen=bronnen,
        entailment_zinstaal=None if entailment_zinstaal is None else round(float(entailment_zinstaal), 4),
    )


# Meetopties van #21.7, standaard uit: de eenheid waarop gezocht wordt, hoeveel
# kandidaten per eenheid de poort en de stance krijgen, en een extra
# kandidatenbron (zoeken op woorden). Zolang ze uit staan, is het pad precies
# dat van vóór #21.7.
_EENHEDEN = {"zin": 1, "venster2": 2, "venster3": 3}


def _spannen(zinnen: list[str], eenheid: str) -> list[tuple[int, int]]:
    """De eenheden als (begin, eind) over de zinnen. Zinnen zoals altijd;
    vensters schuiven één zin per stap over álle zinnen."""
    breedte = _EENHEDEN[eenheid]
    if breedte == 1:
        return [(i, i + 1) for i, zin in enumerate(zinnen) if len(zin) >= _MIN_ZINLENGTE]
    if len(zinnen) <= breedte:
        return [(0, len(zinnen))] if zinnen else []
    return [(i, i + breedte) for i in range(len(zinnen) - breedte + 1)]


def _premisse(zinnen: list[str], begin: int, eind: int) -> str:
    """Het stance-venster rond een eenheid, zoals `_venster` rond een zin."""
    for breedte in (_VENSTER, 1):
        stuk = " ".join(zinnen[max(0, begin - breedte): eind + breedte])
        if len(stuk) <= _VENSTER_MAX_TEKENS:
            return stuk
    return " ".join(zinnen[begin:eind])


def _claimvector(conn: sqlite3.Connection, claim_id: str, versie: str, cache: dict):
    if claim_id not in cache:
        import numpy as np

        rij = conn.execute(
            "SELECT payload FROM fingerprint WHERE claim_id = ? AND kind = 'text' AND model_version = ?",
            (claim_id, versie)).fetchone()
        cache[claim_id] = None if rij is None else np.frombuffer(rij[0], dtype=np.float32)
    return cache[claim_id]


def controleer_teksten(
    conn: sqlite3.Connection,
    documenten: Iterable[tuple[str, str]],
    *,
    config=None,
    fingerprinter=None,
    stance=None,
    eenheid: str = "zin",
    top: int = 1,
    extra_kandidaten: Callable[[str], list[str]] | None = None,
    herordenaar: Callable[[list[tuple[str, str]]], list[float]] | None = None,
    herordenaar_poort: float | None = None,
) -> Controlerapport:
    """Controleert (document_id, tekst)-paren en levert het logboek.

    `fingerprinter` en `stance` zijn injecteerbaar voor deterministische tests;
    zonder injectie draaien de echte, lokale modellen uit config (DR3, DR6).
    `eenheid`, `top`, `extra_kandidaten` en `herordenaar` zijn meetopties
    van #21.7; de standaard is het pad van de batchcontrole zoals ze is. Met
    een herordenaar is zijn score (0 tot 1, per paar zin en claimtekst) de
    poort, vanaf `herordenaar_poort`, in plaats van de gelijkenis.
    """
    if herordenaar is not None and herordenaar_poort is None:
        raise ValueError("een herordenaar zonder poort laat alles door")
    config = config if config is not None else load_config()
    fingerprinter = fingerprinter if fingerprinter is not None else fingerprint_texts
    stance = stance if stance is not None else _stance_uit_config(config)
    versie = config.model_versions.text_embedding
    drempels = config.thresholds
    # Zelfde regel als de resolver: nooit stil over een modelversie heen (DR6).
    ensure_index_matches_version(conn, versie)
    varianten = config.varianten.in_resolver
    if varianten:
        ensure_variants_match_version(conn, versie)
    gestart = datetime.now(timezone.utc).isoformat(timespec="seconds")

    breed = eenheid != "zin" or top != 1 or extra_kandidaten is not None or herordenaar is not None
    # Met een herordenaar is zijn score de poort (#21.7 stap 3); de gelijkenis
    # telt dan niet meer als poort.
    poortdrempels = drempels
    if herordenaar is not None:
        import dataclasses

        poortdrempels = dataclasses.replace(drempels, screening_poort=-1.0)
    vectoren: dict = {}
    uitslagen = []
    for document_id, tekst in documenten:
        alle = _zinnen(tekst)
        if breed:
            treffers = []
            spannen = _spannen(alle, eenheid)
            teksten = [" ".join(alle[b:e]) for b, e in spannen]
            prints = fingerprinter(teksten, versie) if teksten else []
            for (begin, eind), stuk, fingerprint in zip(spannen, teksten, prints):
                kandidaten = [(k.claim_id, k.similarity) for k in
                              search_text(conn, fingerprint, max(top, 1), varianten=varianten)][:top]
                gezien = {claim_id for claim_id, _ in kandidaten}
                for claim_id in (extra_kandidaten(stuk) if extra_kandidaten else []):
                    vector = _claimvector(conn, claim_id, versie, vectoren)
                    if claim_id not in gezien and vector is not None:
                        kandidaten.append((claim_id, float(vector @ fingerprint.vector)))
                        gezien.add(claim_id)
                if herordenaar is not None and kandidaten:
                    claimteksten = [conn.execute("SELECT canonical_text FROM claim WHERE claim_id = ?",
                                                 (claim_id,)).fetchone()[0] for claim_id, _ in kandidaten]
                    scores = herordenaar([(stuk, tekst) for tekst in claimteksten])
                    kandidaten = [k for k, score in zip(kandidaten, scores) if score >= herordenaar_poort]
                for claim_id, similarity in kandidaten:
                    treffer = _beoordeel_kandidaat(
                        conn, document_id, stuk, lambda b=begin, e=eind: _premisse(alle, b, e), fingerprint,
                        claim_id, similarity, poortdrempels, stance, config.varianten.stance_in_zinstaal)
                    if treffer is not None:
                        treffers.append(treffer)
            uitslagen.append(DocumentUitslag(document_id, len(alle), tuple(treffers)))
            continue
        # Kandidaten komen uit de lange zinnen; de vénsters (stance-premise)
        # lopen over álle zinnen — korte buurzinnen dragen juist het oordeel.
        indices = [i for i, zin in enumerate(alle) if len(zin) >= _MIN_ZINLENGTE]
        treffers = []
        if indices:
            prints = fingerprinter([alle[i] for i in indices], versie)
            for index, fingerprint in zip(indices, prints):
                treffer = _beoordeel_zin(
                    conn, document_id, alle, index, fingerprint, drempels, stance, varianten,
                    config.varianten.stance_in_zinstaal)
                if treffer is not None:
                    treffers.append(treffer)
        uitslagen.append(DocumentUitslag(document_id, len(alle), tuple(treffers)))

    return Controlerapport(
        gestart_op=gestart,
        model_versions={
            "text": versie,
            "nli": config.model_versions.nli,
        },
        thresholds={
            "screening_poort": drempels.screening_poort,
            "stance_entailment": drempels.stance_entailment,
        },
        corpus=_corpusstand(conn),
        documenten=tuple(uitslagen),
        regels={"varianten": varianten, "stance_in_zinstaal": config.varianten.stance_in_zinstaal,
                **({"eenheid": eenheid, "top": top, "extra_kandidaten": extra_kandidaten is not None,
                    "herordenaar_poort": herordenaar_poort}
                   if breed else {})},
    )


def _lees_documenten(paden: list[str], jsonl: str | None) -> list[tuple[str, str]]:
    documenten = [
        (Path(pad).name, Path(pad).read_text(encoding="utf-8")) for pad in paden
    ]
    if jsonl:
        with open(jsonl, encoding="utf-8") as bestand:
            for nummer, regel in enumerate(bestand, start=1):
                regel = regel.strip()
                if not regel:
                    continue
                record = json.loads(regel)
                documenten.append(
                    (str(record.get("id", f"regel-{nummer}")), str(record["tekst"]))
                )
    return documenten


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Controleer documenten tegen bekend-weerlegde beweringen (B17)."
            " Uitgang 1 als er iets gevlagd is, zodat dit als poort in een"
            " pijplijn kan staan."
        )
    )
    parser.add_argument(
        "paden", nargs="*", help="tekstbestanden, één document per bestand"
    )
    parser.add_argument(
        "--jsonl",
        help='JSONL met per regel {"id": ..., "tekst": ...}; geef gescrapete'
             " documenten hun bron-URL als id, dan werkt de bonnetjesregel",
    )
    parser.add_argument("--db", default="doublecheck.db")
    parser.add_argument("--uit", help="schrijf het rapport hierheen i.p.v. stdout")
    args = parser.parse_args(argv)

    documenten = _lees_documenten(args.paden, args.jsonl)
    if not documenten:
        parser.error("geen documenten: geef bestandspaden of --jsonl")

    conn = connect(args.db)
    try:
        rapport = controleer_teksten(conn, documenten)
    finally:
        conn.close()

    uitvoer = json.dumps(asdict(rapport), ensure_ascii=False, indent=2)
    if args.uit:
        Path(args.uit).write_text(uitvoer + "\n", encoding="utf-8")
    else:
        print(uitvoer)
    print(
        f"{len(rapport.documenten)} document(en), {rapport.gevlagd} gevlagd",
        file=sys.stderr,
    )
    return 1 if rapport.gevlagd else 0


if __name__ == "__main__":
    raise SystemExit(main())
