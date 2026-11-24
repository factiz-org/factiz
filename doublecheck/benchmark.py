"""Meetharnas: verkeerde koppelingen en dekking, apart per taal (E4.S2-AC1).

Elke meting loopt door exact hetzelfde codepad als productie — `search_text`
en `categorize` — zodat het cijfer over het product gaat en niet over een
benchmarkkopie ervan. De uitkomstcategorie wordt dus ook hier uitsluitend
door de categoriseringsfunctie gezet (DR4).

Scoringsregels:
- zelfde-paar: `matched` op de juiste claim = dekking; `matched` op een
  andere claim = verkeerde koppeling; `related`/`none` = gemist.
- lijkend-maar-anders-paar: elke `matched` is een verkeerde koppeling —
  behalve bij `hardste-buur`-paren, waar het artefact zelf in de index staat
  en zichzelf mag matchen; alleen een match op een ándere claim is daar fout.

Percentages hieronder zijn systeemprecisie-maten en daarmee expliciet
toegestaan (B10); de externe formulering als foutratio-met-bovengrens is de
taak van docs/BENCHMARK.md (3.6).
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone

import numpy as np
from scipy.stats import beta

from doublecheck.categorize import Category, categorize
from doublecheck.clustering import ensure_clusters_match
from doublecheck.config import ModelVersions, Thresholds
from doublecheck.relation import contradicts
from doublecheck.taal import zijn_verschillende_talen
from doublecheck.search import (
    ModelVersionMismatchError,
    ensure_index_matches_version,
    ensure_variants_match_version,
    search_image,
    search_text,
)
from doublecheck.testset import ensure_testset_matches_derivation, load_test_pairs


@dataclass(frozen=True)
class PairOutcome:
    language: str
    provenance: str
    is_same: bool
    target_claim_id: str
    category: str
    matched_claim_id: str | None
    similarity: float | None
    fout: bool
    kind: str = "text"


@dataclass(frozen=True)
class LanguageStats:
    pairs: int
    same_pairs: int
    lookalike_pairs: int
    wrong_links: int
    correct_matches: int

    @property
    def dekking(self) -> float:
        return self.correct_matches / self.same_pairs if self.same_pairs else 0.0


@dataclass(frozen=True)
class BenchmarkResult:
    per_language: dict[str, LanguageStats]
    outcomes: tuple[PairOutcome, ...]
    per_kind: dict[str, LanguageStats] = field(default_factory=dict)
    # Met welke claimvarianten deze run zocht; leeg als zonder (#25.17).
    variantenset: str = ""

    @property
    def totals(self) -> LanguageStats:
        stats = list(self.per_language.values())
        return LanguageStats(
            pairs=sum(s.pairs for s in stats),
            same_pairs=sum(s.same_pairs for s in stats),
            lookalike_pairs=sum(s.lookalike_pairs for s in stats),
            wrong_links=sum(s.wrong_links for s in stats),
            correct_matches=sum(s.correct_matches for s in stats),
        )


def upper_bound_95(fouten: int, n: int) -> float:
    """Eenzijdige 95%-bovengrens op de foutratio (Clopper-Pearson).

    Bij 0 fouten op 1.000 geeft dit de 'regel van drie': 0,3% (G1).
    """
    if n == 0:
        return 0.0
    if fouten >= n:
        return 1.0
    return float(beta.ppf(0.95, fouten + 1, n - fouten))


def _is_fout(
    pair, category: Category, matched_claim_id: str | None, cluster: set | None = None
) -> bool:
    """`cluster` bevat de claim-ID's die als hetzelfde doel gelden (E2.S5-AC6).

    Zonder cluster is dat alleen het doel zelf — dat is de strikte telling.
    """
    doelen = cluster if cluster else {pair.claim_id}
    if pair.kind == "image":
        # Beeld levert per definitie hoogstens `related` (B8); de vraag is of
        # het naar de júíste claim resolvet.
        if matched_claim_id is None:
            return False
        return matched_claim_id not in doelen if pair.is_same else True
    if category is not Category.MATCHED:
        return False
    if pair.is_same:
        return matched_claim_id not in doelen
    if pair.provenance.startswith("hardste-buur:"):
        anchor = pair.provenance.split(":", 1)[1]
        return matched_claim_id != anchor
    return True


class MarktZonderCijferError(Exception):
    """Een uitgerolde markt levert geen benchmarkrij op (B14, aangescherpt)."""


def ensure_every_market_is_measured(conn: sqlite3.Connection) -> None:
    """Elke markt mét corpus moet ook testparen hebben.

    B14 zei eerst: een markt gaat live wanneer zijn eigen benchmark slaagt. De
    ES-uitrol weerlegde dat — Frans ging van 0 naar 3 fouten en Nederlands van 5
    naar 8 zónder codewijziging, puur doordat de index verdrievoudigde
    (BENCHMARK.md §22d). G1 hoort bij de índex, niet bij een taal, dus wordt bij
    elke uitbreiding álles opnieuw gemeten en ligt de poort op het totaalcijfer.

    Hier mechanisch afgedwongen omdat de faalvorm stil is: een markt die wel
    corpus heeft maar geen testparen levert geen cijfer op, en niets zou dat
    zeggen. Een taal die géén markt is (Catalaans kwam mee met verificat.cat)
    hoeft geen rij — die zit in de index zonder precisiebelofte, precies wat B14
    toestaat.
    """
    from doublecheck.ingest import MARKTEN

    met_corpus = {
        rij["language"]
        for rij in conn.execute("SELECT DISTINCT language FROM claim")
    }
    gemeten = {
        rij["language"]
        for rij in conn.execute("SELECT DISTINCT language FROM testpair")
    }
    ontbreekt = sorted((set(MARKTEN) & met_corpus) - gemeten)
    if ontbreekt:
        raise MarktZonderCijferError(
            f"markt(en) {ontbreekt} hebben corpus maar geen testparen, dus geen"
            " eigen cijfer; bouw de testset opnieuw met python -m"
            " doublecheck.testset"
        )


def ensure_every_language_is_measured(conn: sqlite3.Connection, min_claims: int | None = None) -> None:
    """Elke taal vanaf `min_claims` claims heeft testparen (#25.1).

    Aanscherping van `ensure_every_market_is_measured`: niet alleen de
    invoermarkten, maar elke taal met genoeg corpus om ertoe te doen. Wat
    eronder blijft staat in de index zonder precisiebelofte (B14).
    """
    from doublecheck.testset import ontbrekende_talen

    if min_claims is None:
        from doublecheck.config import load_config

        min_claims = load_config().benchmark.min_claims_voor_cijfer
    ontbreekt = ontbrekende_talen(conn, min_claims=min_claims)
    if ontbreekt:
        raise MarktZonderCijferError(
            f"taal/talen {ontbreekt} hebben minstens {min_claims} claims maar geen"
            " testparen, dus geen eigen cijfer; breid de testset uit met python -m"
            " doublecheck.testset --ontbrekende-talen"
        )


def _variantenset(conn: sqlite3.Connection, model_version: str) -> str:
    """De claimvarianten voor dit model, zoals een run ze vastlegt."""
    rijen = conn.execute(
        "SELECT generator, prompt_version, count(*) FROM claim_variant WHERE model_version = ?"
        " GROUP BY 1, 2 ORDER BY 1, 2", (model_version,)).fetchall()
    return "; ".join(f"{g}/{p} · {n} varianten" for g, p, n in rijen)


def _met_varianten(config) -> bool:
    """Of de benchmark over de claimvarianten zoekt: precies wanneer de
    resolver dat doet (#25.17), zodat het cijfer over het product gaat."""
    return config.varianten.in_resolver


def ensure_testset_inside_index(conn: sqlite3.Connection) -> None:
    """Een testpaar op een claim buiten de index (B28) wordt stil een
    misser, en dan verschuift het cijfer zonder dat iemand het besloot.
    Weghalen is een eigen stap, met een rapport (`toelating --testparen-weg`)."""
    from doublecheck.toelating import testparen_buiten_index

    paren = testparen_buiten_index(conn)
    if paren:
        raise ValueError(
            f"{len(paren)} testpaar/paren verwijzen naar een claim buiten de index"
            f" (bijvoorbeeld {paren[0][1]}); haal ze bewust weg met"
            " python -m doublecheck.toelating --testparen-weg"
        )


def run_benchmark(
    conn: sqlite3.Connection,
    thresholds: Thresholds,
    model_version: str,
    image_model_version: str | None = None,
    cluster_aware: bool = False,
    varianten: bool | None = None,
) -> BenchmarkResult:
    """`cluster_aware`: een match op een ánder lid van het doelcluster telt als
    gevonden (E2.S5-AC6). Standaard uit, zodat het strikte cijfer het uitgangspunt
    blijft en clustering geen fouten kan wegpoetsen."""
    ensure_index_matches_version(conn, model_version)
    if varianten is None:
        from doublecheck.config import load_config

        varianten = _met_varianten(load_config())
    if varianten:
        ensure_variants_match_version(conn, model_version)
    ensure_testset_matches_derivation(conn)
    ensure_testset_inside_index(conn)
    ensure_every_market_is_measured(conn)
    ensure_every_language_is_measured(conn)
    if cluster_aware:
        # Alleen hier: het strikte cijfer raakt clusters niet en moet altijd
        # kunnen draaien, ook op een database zonder clustering (E2.S5-AC6).
        ensure_clusters_match(conn, model_version, thresholds.cluster_same)

    pairs = load_test_pairs(conn)
    if not pairs:
        raise ValueError("testset is leeg; bouw hem met python -m doublecheck.testset")
    verwacht = {
        "text": model_version,
        "image": image_model_version or model_version,
    }
    for soort in {pair.kind for pair in pairs}:
        versies = {
            pair.fingerprint.model_version for pair in pairs if pair.kind == soort
        }
        if versies != {verwacht[soort]}:
            raise ModelVersionMismatchError(
                f"testset ({soort}) draagt modelversie(s) {sorted(versies)}, verwacht"
                f" {verwacht[soort]!r}; herbouw de testset"
            )

    clusters: dict[str, set] = {}
    if cluster_aware:
        for rij in conn.execute(
            "SELECT claim_id, cluster_id FROM claim WHERE cluster_id IS NOT NULL"
        ):
            clusters.setdefault(rij["cluster_id"], set()).add(rij["claim_id"])
        van_claim = {
            rij["claim_id"]: rij["cluster_id"]
            for rij in conn.execute(
                "SELECT claim_id, cluster_id FROM claim WHERE cluster_id IS NOT NULL"
            )
        }
    else:
        van_claim = {}

    outcomes: list[PairOutcome] = []
    per_taal: dict[str, dict[str, int]] = {}
    per_soort: dict[str, dict[str, int]] = {}

    for pair in pairs:
        doelcluster = clusters.get(van_claim.get(pair.claim_id))
        if pair.kind == "image":
            kandidaten = search_image(conn, pair.fingerprint)
            beste = kandidaten[0] if kandidaten else None
            uitkomst = categorize(
                None, thresholds,
                image_distance=beste.distance if beste else None,
            )
            matched_id = (
                beste.claim_id
                if beste is not None and "beeld" in uitkomst.matched_on
                else None
            )
            maat = float(beste.distance) if beste else None
        else:
            kandidaten = search_text(conn, pair.fingerprint, varianten=varianten)
            beste = kandidaten[0] if kandidaten else None
            tegenspraak = False
            crosslinguaal = False
            if beste is not None:
                kandidaat = conn.execute(
                    "SELECT canonical_text, language FROM claim WHERE claim_id = ?",
                    (beste.claim_id,),
                ).fetchone()
                tegenspraak = contradicts(
                    pair.fingerprint.numbers,
                    pair.fingerprint.negations,
                    kandidaat["canonical_text"],
                    artefact_negation_tokens=getattr(pair.fingerprint, "negation_tokens", None),
                )
                crosslinguaal = zijn_verschillende_talen(
                    getattr(pair.fingerprint, "language", None),
                    kandidaat["language"],
                )
            uitkomst = categorize(
                beste.similarity if beste else None, thresholds,
                contradiction=tegenspraak,
                crosslinguaal=crosslinguaal,
            )
            matched_id = (
                beste.claim_id
                if beste and uitkomst.category is Category.MATCHED
                else None
            )
            maat = uitkomst.similarity

        fout = _is_fout(pair, uitkomst.category, matched_id, doelcluster)
        outcomes.append(
            PairOutcome(
                language=pair.language,
                provenance=pair.provenance,
                is_same=pair.is_same,
                target_claim_id=pair.claim_id,
                category=str(uitkomst.category),
                matched_claim_id=matched_id,
                similarity=maat,
                fout=fout,
                kind=pair.kind,
            )
        )

        doelen = doelcluster if doelcluster else {pair.claim_id}
        goed = pair.is_same and matched_id in doelen
        for register, sleutel in ((per_taal, pair.language), (per_soort, pair.kind)):
            stats = register.setdefault(
                sleutel,
                {"pairs": 0, "same": 0, "lookalike": 0, "wrong": 0, "correct": 0},
            )
            stats["pairs"] += 1
            if pair.is_same:
                stats["same"] += 1
                if goed:
                    stats["correct"] += 1
            else:
                stats["lookalike"] += 1
            if fout:
                stats["wrong"] += 1

    def _samenvatten(register):
        return {
            sleutel: LanguageStats(
                pairs=stats["pairs"],
                same_pairs=stats["same"],
                lookalike_pairs=stats["lookalike"],
                wrong_links=stats["wrong"],
                correct_matches=stats["correct"],
            )
            for sleutel, stats in register.items()
        }

    return BenchmarkResult(
        per_language=_samenvatten(per_taal),
        outcomes=tuple(outcomes),
        per_kind=_samenvatten(per_soort),
        variantenset=_variantenset(conn, model_version) if varianten else "",
    )


def record_run(
    conn: sqlite3.Connection,
    thresholds: Thresholds,
    model_versions: ModelVersions,
    result: BenchmarkResult,
) -> int:
    """Legt drempels, modelversies en uitkomsten van een run vast (E4.S2-AC2, DR6)."""
    totaal = result.totals
    per_taal = {
        taal: {
            "pairs": stats.pairs,
            "same_pairs": stats.same_pairs,
            "wrong_links": stats.wrong_links,
            "correct_matches": stats.correct_matches,
        }
        for taal, stats in result.per_language.items()
    }
    cursor = conn.execute(
        "INSERT INTO benchmark_run (started_at, text_match, text_related,"
        " image_same, model_version_text, model_version_image, pairs,"
        " same_pairs, wrong_links, correct_matches, results_per_language, variant_set)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            datetime.now(timezone.utc).isoformat(timespec="seconds"),
            thresholds.text_match,
            thresholds.text_related,
            thresholds.image_same,
            model_versions.text_embedding,
            model_versions.image_hash,
            totaal.pairs,
            totaal.same_pairs,
            totaal.wrong_links,
            totaal.correct_matches,
            json.dumps(per_taal),
            result.variantenset,
    ),
    )
    run_id = cursor.lastrowid
    # E4.S2-AC3: elk foutgeval individueel terug te zien — verwijzingen en
    # getallen, geen artefacten (DR3).
    for uitkomst in result.outcomes:
        if not uitkomst.fout:
            continue
        conn.execute(
            "INSERT INTO benchmark_fout (run_id, language, provenance, is_same,"
            " target_claim_id, matched_claim_id, similarity)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                run_id,
                uitkomst.language,
                uitkomst.provenance,
                1 if uitkomst.is_same else 0,
                uitkomst.target_claim_id,
                uitkomst.matched_claim_id,
                uitkomst.similarity,
            ),
        )
    conn.commit()
    return run_id


@dataclass(frozen=True)
class FailureCase:
    fout_id: int
    language: str
    provenance: str
    is_same: bool
    target_claim_id: str
    matched_claim_id: str
    similarity: float
    target_text: str | None
    matched_text: str | None


def list_failures(conn: sqlite3.Connection, run_id: int) -> list[FailureCase]:
    rijen = conn.execute(
        "SELECT fout.fout_id, fout.language, fout.provenance, fout.is_same,"
        " fout.target_claim_id, fout.matched_claim_id, fout.similarity,"
        " doel.canonical_text AS target_text, gematcht.canonical_text AS matched_text"
        " FROM benchmark_fout AS fout"
        " LEFT JOIN claim AS doel ON doel.claim_id = fout.target_claim_id"
        " LEFT JOIN claim AS gematcht ON gematcht.claim_id = fout.matched_claim_id"
        " WHERE fout.run_id = ? ORDER BY fout.fout_id",
        (run_id,),
    ).fetchall()
    return [
        FailureCase(
            fout_id=rij["fout_id"],
            language=rij["language"],
            provenance=rij["provenance"],
            is_same=bool(rij["is_same"]),
            target_claim_id=rij["target_claim_id"],
            matched_claim_id=rij["matched_claim_id"],
            similarity=rij["similarity"],
            target_text=rij["target_text"],
            matched_text=rij["matched_text"],
        )
        for rij in rijen
    ]


@dataclass(frozen=True)
class SweepRow:
    """Eén drempelstand met wat hij oplevert (PLAN.md #7.4)."""

    text_match: float
    text_related: float
    pairs: int
    same_pairs: int
    wrong_links: int
    correct_matches: int
    per_provenance_errors: dict[str, int]
    per_language_coverage: dict[str, tuple[int, int]]


@dataclass(frozen=True)
class RelatedSweepRow:
    related: float
    # Aandeel artefacten zónder tegenhanger in de index dat tóch een factcheck
    # voorgeschoteld zou krijgen.
    valse_related_aandeel: float
    # Zelfde-paren die de matchdrempel niet haalden en die `related` terugwint.
    teruggewonnen: int
    gemiste_paren: int


def sweep_related(
    conn: sqlite3.Connection,
    model_version: str,
    *,
    match: float,
    kandidaten=(0.70, 0.75, 0.80, 0.85),
    steekproef: int = 600,
    seed: int = 5,
) -> list[RelatedSweepRow]:
    """Meet de afruil achter `text_related`, van twee kanten tegelijk.

    De bestaande sweep varieert alleen de matchdrempel, waardoor `text_related`
    bij de fingerprintwissel van etappe 12 ongemerkt lósser werd (#12.5).

    *Valse related* — hoe vaak een artefact zónder tegenhanger tóch een
    factcheck voorgeschoteld krijgt. Gesimuleerd door per claim de eigen claim
    én zijn cluster uit te sluiten en te kijken hoe hoog de dichtstbijzijnde
    overgebleven buur nog komt. Dat is precies de situatie van een gebruiker die
    iets instuurt wat nog niemand gecheckt heeft.

    *Teruggewonnen* — zelfde-paren onder de matchdrempel die `related` alsnog
    zichtbaar maakt. Zonder deze kant zou de meting altijd "hoger is beter"
    zeggen, en dat is geen afweging.

    Experiment, geen configwijziging: `config.toml` blijft ongemoeid (DR6).
    """
    import random

    rijen = conn.execute(
        "SELECT c.claim_id, c.cluster_id, f.payload FROM claim c"
        " JOIN fingerprint f ON f.claim_id = c.claim_id"
        " WHERE f.kind = 'text' AND f.model_version = ?"
        " ORDER BY c.claim_id",
        (model_version,),
    ).fetchall()
    if not rijen:
        return []
    M = np.vstack([np.frombuffer(rij["payload"], dtype=np.float32) for rij in rijen])
    clusters = [rij["cluster_id"] for rij in rijen]

    keuze = list(range(len(rijen)))
    if len(keuze) > steekproef:
        keuze = random.Random(seed).sample(keuze, steekproef)

    maxima = []
    for i in keuze:
        scores = M @ M[i]
        scores[i] = -1.0
        if clusters[i] is not None:
            for j, cluster in enumerate(clusters):
                if cluster == clusters[i]:
                    scores[j] = -1.0
        maxima.append(float(scores.max()))
    maxima = np.asarray(maxima)

    bronnen = {
        rij["claim_id"]: np.frombuffer(rij["payload"], dtype=np.float32)
        for rij in rijen
    }
    gemist = []
    for paar in load_test_pairs(conn):
        if not paar.is_same or paar.kind != "text":
            continue
        bron = bronnen.get(paar.claim_id)
        if bron is None:
            continue
        gelijkenis = float(paar.fingerprint.vector @ bron)
        if gelijkenis < match:
            gemist.append(gelijkenis)
    gemist = np.asarray(gemist)

    return [
        RelatedSweepRow(
            related=drempel,
            valse_related_aandeel=float((maxima >= drempel).mean()) if len(maxima) else 0.0,
            teruggewonnen=int((gemist >= drempel).sum()) if len(gemist) else 0,
            gemiste_paren=len(gemist),
        )
        for drempel in kandidaten
    ]


def sweep_thresholds(
    conn: sqlite3.Connection,
    model_version: str,
    *,
    matches=(0.75, 0.80, 0.85, 0.90, 0.95),
    related: float = 0.70,
    image_same: int = 10,
    image_model_version: str | None = None,
) -> list[SweepRow]:
    """Meet dezelfde testset op meerdere matchdrempels.

    Dit is een experiment, geen configwijziging: `config.toml` blijft ongemoeid
    (DR6). Het levert de afruil tussen dekking en verkeerde koppelingen, zodat
    een drempelbesluit op cijfers rust in plaats van op gevoel.
    """
    rijen = []
    bruikbaar = [m for m in matches if 0.0 < related < m <= 1.0]
    overgeslagen = [m for m in matches if m not in bruikbaar]
    if not bruikbaar:
        # Alles ongeldig is iets anders dan iets ongeldig: dan is er niets te
        # meten en moet dat een fout zijn, geen lege tabel.
        raise ValueError(
            f"geen bruikbare drempel: {list(matches)} ligt niet boven"
            f" related={related}"
        )
    if overgeslagen:
        # Luid overslaan, niet stil afkappen: een combinatie onder de
        # related-drempel is betekenisloos, maar een ontbrekende rij in de tabel
        # leest als "gemeten en niet interessant" (#12.5 zette related op 0,80,
        # waarna de sweep op zijn eigen standaardwaarden omviel).
        print(f"overgeslagen: match {overgeslagen} ligt niet boven"
              f" related={related}")
    for match in matches:
        if not 0.0 < related < match <= 1.0:
            continue
        drempels = Thresholds(
            text_match=match, text_related=related, image_same=image_same
        )
        resultaat = run_benchmark(
            conn, drempels, model_version,
            image_model_version=image_model_version,
        )
        totaal = resultaat.totals
        fouten: dict[str, int] = {}
        for uitkomst in resultaat.outcomes:
            if uitkomst.fout:
                sleutel = uitkomst.provenance.split(":")[0]
                fouten[sleutel] = fouten.get(sleutel, 0) + 1
        rijen.append(
            SweepRow(
                text_match=match,
                text_related=related,
                pairs=totaal.pairs,
                same_pairs=totaal.same_pairs,
                wrong_links=totaal.wrong_links,
                correct_matches=totaal.correct_matches,
                per_provenance_errors=fouten,
                per_language_coverage={
                    taal: (stats.correct_matches, stats.same_pairs)
                    for taal, stats in resultaat.per_language.items()
                },
            )
        )
    return rijen


def main() -> None:
    import argparse

    from doublecheck.config import load_config
    from doublecheck.storage import connect, init_schema

    parser = argparse.ArgumentParser(description="Doublecheck benchmark")
    parser.add_argument("--db", default="doublecheck.db")
    parser.add_argument("--failures", type=int, metavar="RUN_ID",
                        help="toon de foutgevallen van een vastgelegde run en stop")
    parser.add_argument("--related-sweep", action="store_true",
                        dest="related_sweep",
                        help="afruil achter text_related meten (#12.5)")
    parser.add_argument("--sweep", action="store_true",
                        help="meet dezelfde testset op meerdere matchdrempels")
    parser.add_argument("--varianten", choices=("config", "aan", "uit"), default="config",
                        help="zoeken met de claimvarianten; standaard zoals de resolver (config)")
    parser.add_argument("--clusters", action="store_true",
                        help="rapporteer naast het strikte cijfer ook clusterbewust")
    args = parser.parse_args()

    config = load_config()
    conn = connect(args.db)
    init_schema(conn)

    if args.failures is not None:
        fouten = list_failures(conn, args.failures)
        print(f"run #{args.failures}: {len(fouten)} foutgevallen")
        for fout in fouten:
            label = "zelfde" if fout.is_same else "lijkend"
            print(f"#{fout.fout_id:<5} {fout.language} · {fout.provenance.split(':')[0]:<13}"
                  f" · {label} · sim {fout.similarity:.3f}")
            print(f"   doel:    {fout.target_claim_id}  {fout.target_text!r}"[:100])
            print(f"   matchte: {fout.matched_claim_id}  {fout.matched_text!r}"[:100])
        conn.close()
        return
    if args.related_sweep:
        rijen = sweep_related(
            conn, config.model_versions.text_embedding,
            match=config.thresholds.text_match,
        )
        huidig = config.thresholds.text_related
        print(f"related-sweep · match vast op {config.thresholds.text_match}"
              f" · config staat nu op related={huidig}")
        print()
        print(f"{'related':<9}{'valse related':>15}{'teruggewonnen paren':>22}")
        for rij in rijen:
            merk = " *" if rij.related == huidig else "  "
            terug = (f"{rij.teruggewonnen}/{rij.gemiste_paren}"
                     f" ({rij.teruggewonnen / rij.gemiste_paren:.1%})"
                     if rij.gemiste_paren else "—")
            print(f"{rij.related:<7.2f}{merk}{rij.valse_related_aandeel:>14.1%}{terug:>22}")
        print()
        print("valse related = artefact zonder tegenhanger in de index dat tóch een")
        print("factcheck voorgeschoteld krijgt (eigen cluster uitgesloten).")
        print("Een sweep wijzigt config.toml niet (DR6).")
        conn.close()
        return

    if args.sweep:
        rijen = sweep_thresholds(
            conn, config.model_versions.text_embedding,
            related=config.thresholds.text_related,
            image_same=config.thresholds.image_same,
        )
        huidig = config.thresholds.text_match
        print(f"drempelsweep · related vast op {config.thresholds.text_related}"
              f" · config staat nu op match={huidig}")
        print(f"\n{'match':<8}{'fouten':>8}{'bovengr95':>11}{'dekking':>10}"
              f"{'nl-en':>9}  fouten per soort")
        for rij in rijen:
            grens = upper_bound_95(rij.wrong_links, rij.pairs)
            nl_en = rij.per_language_coverage.get("nl-en")
            nl_en_tekst = f"{nl_en[0]}/{nl_en[1]}" if nl_en else "—"
            merk = " *" if rij.text_match == huidig else "  "
            print(f"{rij.text_match:<6.2f}{merk}{rij.wrong_links:>8}"
                  f"{grens:>10.2%}{rij.correct_matches:>6}/{rij.same_pairs:<4}"
                  f"{nl_en_tekst:>9}  {dict(sorted(rij.per_provenance_errors.items()))}")
        print("\n* = huidige configwaarde. Een sweep wijzigt config.toml niet (DR6).")
        conn.close()
        return

    met_varianten = {"aan": True, "uit": False}.get(args.varianten, _met_varianten(config))
    resultaat = run_benchmark(
        conn, config.thresholds, config.model_versions.text_embedding, varianten=met_varianten
    )

    totaal = resultaat.totals
    print(f"benchmark over {totaal.pairs} paren · model"
          f" {config.model_versions.text_embedding}")
    print(f"drempels: match={config.thresholds.text_match}"
          f" related={config.thresholds.text_related}")
    print(f"varianten: {resultaat.variantenset or 'geen'}")
    print()
    kop = f"{'taal':<8}{'paren':>7}{'zelfde':>8}{'fouten':>8}{'bovengrens95':>14}{'dekking':>9}"
    print(kop)
    rijen = sorted(resultaat.per_language.items()) + [("totaal", totaal)]
    for taal, stats in rijen:
        bovengrens = upper_bound_95(stats.wrong_links, stats.pairs)
        print(f"{taal:<8}{stats.pairs:>7}{stats.same_pairs:>8}"
              f"{stats.wrong_links:>8}{bovengrens:>13.2%}{stats.dekking:>9.1%}")

    if args.clusters:
        clusterbewust = run_benchmark(
            conn, config.thresholds, config.model_versions.text_embedding,
            cluster_aware=True, varianten=met_varianten,
        )
        ct = clusterbewust.totals
        print()
        print("clusterbewust (match op een ánder lid van het doelcluster telt mee):")
        # Zelfdocumenterend: de guard dwingt drempel en modelversie af, maar
        # `--zonder-veto` is een legitieme keuze en mag dus niet weigeren. Dan
        # moet wél zichtbaar zijn waarop dit cijfer slaat (#12.3).
        staat = conn.execute(
            "SELECT threshold, veto_version FROM cluster_state WHERE id = 1"
        ).fetchone()
        if staat is not None:
            print(f"  clusters gebouwd op drempel {staat['threshold']}"
                  f" · veto: {staat['veto_version'] or 'geen'}")
        print(f"  verkeerde koppelingen: {ct.wrong_links} op {ct.pairs}"
              f"  (bovengrens95 {upper_bound_95(ct.wrong_links, ct.pairs):.2%})")
        print(f"  dekking:               {ct.correct_matches} van {ct.same_pairs}")
        print("  het strikte cijfer hierboven blijft het uitgangspunt (E2.S5-AC6).")

    fouten_per_soort: dict[str, int] = {}
    for uitkomst in resultaat.outcomes:
        if uitkomst.fout:
            sleutel = uitkomst.provenance.split(":")[0]
            fouten_per_soort[sleutel] = fouten_per_soort.get(sleutel, 0) + 1
    print(f"\nfouten per soort: {dict(sorted(fouten_per_soort.items()))}")

    run_id = record_run(conn, config.thresholds, config.model_versions, resultaat)
    print(f"run #{run_id} vastgelegd (drempels + modelversies + uitkomsten)")
    conn.close()


if __name__ == "__main__":
    main()
