"""Claims clusteren die dezelfde bewering doen (E2.S5, DR7).

Het corpus bevat dezelfde bewering meermaals: uitgevers formuleren anders, en
dpa publiceert dezelfde check in NL, DE en FR onder aparte ID's. Zonder
clustering blijft "veertien keer weerlegd" een belofte en telt een terecht
gevonden anderstalige tweeling als benchmarkfout.

Twee veiligheidsregels, allebei uit de verkenning van 2026-08-29:

1. **Tegenspraak blokkeert samenvoegen (DR8).** Een claim en zijn ontkenning
   liggen dicht bij elkaar in de vectorruimte (0,866 bij taak 1.11). Zonder
   deze regel zou clustering ze samenvoegen — en dan krijgt een bewering het
   oordeel van zijn tegendeel. Dat is het ergst denkbare resultaat.
2. **Volledige koppeling.** Een claim voegt zich alleen bij een cluster als hij
   boven de drempel ligt tegenover *elk* lid. Enkelvoudige koppeling laat
   A~B~C samensmelten terwijl A en C niets met elkaar te maken hebben.
"""

from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass

import numpy as np

from doublecheck.relation import (
    contradicts,
    extract_negation_tokens,
    extract_negations,
    extract_numbers,
)


@dataclass(frozen=True)
class ClusterReport:
    claims: int
    clusters: int
    clusters_with_multiple_members: int
    largest_cluster: int
    blocked_by_contradiction: int
    # Paren die op zichzelf dicht genoeg waren, maar afketsten op een ánder lid
    # van het cluster. Dat is volledige koppeling die zijn werk doet — en de
    # prijs ervan, zichtbaar gemaakt in plaats van weggemoffeld (PLAN.md #9.7).
    blocked_by_linkage: int = 0
    # Samenvoegingen die de mechanische regels doorlieten maar het relatiemodel
    # tegenhield (PLAN.md #10.4).
    blocked_by_veto: int = 0


def cluster_members(conn: sqlite3.Connection, claim_id: str) -> set[str]:
    """Alle claims die met deze claim één bewering vormen (inclusief zichzelf)."""
    rij = conn.execute(
        "SELECT cluster_id FROM claim WHERE claim_id = ?", (claim_id,)
    ).fetchone()
    if rij is None:
        return set()
    if rij["cluster_id"] is None:
        return {claim_id}
    return {
        r["claim_id"]
        for r in conn.execute(
            "SELECT claim_id FROM claim WHERE cluster_id = ?", (rij["cluster_id"],)
        )
    }


def _cluster_id(leden: list[str]) -> str:
    """Stabiel ID: dezelfde leden geven altijd hetzelfde cluster-ID."""
    kern = "|".join(sorted(leden))
    return "cl-" + hashlib.sha256(kern.encode("utf-8")).hexdigest()[:16]


# Rijen per blok bij het zoeken van kandidaatparen. 2.048 × 85.099 float32 is
# ~700 MB per blok — ruim binnen bereik, en de volle matrix zou 28,9 GB zijn.
_BLOK = 2048


def build_clusters(
    conn: sqlite3.Connection,
    model_version: str,
    threshold: float,
    veto=None,
) -> ClusterReport:
    """Clustert alle claims met een fingerprint van deze modelversie (AC4).

    `veto(tekst_a, tekst_b, taal_a, taal_b) -> bool` is een optionele extra rem. Hij mag een
    samenvoeging uitsluitend **tegenhouden**, nooit toestaan: het pad naar een
    merge blijft similariteit plus volledige koppeling plus DR8. Zo is een vals
    "niet hetzelfde" onschadelijk — de claims blijven apart, precies zoals
    zonder veto — terwijl een terecht oordeel een gevaarlijke merge voorkomt.
    Bedoeld voor het NLI-model, dat offline draait (BENCHMARK.md §15e).
    """
    rijen = conn.execute(
        "SELECT c.claim_id, c.canonical_text, c.language, f.payload FROM claim c"
        " JOIN fingerprint f ON f.claim_id = c.claim_id"
        " WHERE f.kind = 'text' AND f.model_version = ?"
        " ORDER BY c.claim_id",
        (model_version,),
    ).fetchall()

    conn.execute("UPDATE claim SET cluster_id = NULL")
    conn.execute("DELETE FROM cluster_state")
    conn.execute(
        "INSERT INTO cluster_state (id, model_version, threshold, veto_version)"
        " VALUES (1, ?, ?, ?)",
        (model_version, float(threshold), getattr(veto, "model_version", "") or ""),
    )
    if not rijen:
        conn.commit()
        return ClusterReport(0, 0, 0, 0, 0)

    ids = [rij["claim_id"] for rij in rijen]
    teksten = {rij["claim_id"]: rij["canonical_text"] for rij in rijen}
    talen = {rij["claim_id"]: rij["language"] for rij in rijen}
    matrix = np.vstack(
        [np.frombuffer(rij["payload"], dtype=np.float32) for rij in rijen]
    )
    # Blokgewijs in plaats van één matrix: `matrix @ matrix.T` is 28,9 GB bij
    # 85.099 claims (#16.3). De volle matrix is ook niet nodig — de
    # koppelingscontrole vraagt alleen óf een paar boven de drempel ligt, en dat
    # is precies de kandidatenlijst. Een paar dat er niet in staat, ligt eronder.
    scores: dict[tuple[int, int], float] = {}
    for start in range(0, len(matrix), _BLOK):
        blok = matrix[start : start + _BLOK] @ matrix.T
        rijen_idx, kolommen = np.nonzero(blok >= threshold)
        for rij_nr, kolom in zip(rijen_idx, kolommen):
            a = start + int(rij_nr)
            b = int(kolom)
            if a < b:
                scores[(a, b)] = float(blok[rij_nr, kolom])
        del blok

    geblokkeerd = 0
    afgeketst = 0
    veto_geblokkeerd = 0
    clusters: list[list[int]] = []
    van_index: dict[int, int] = {}

    # Sterkste paren eerst: die vormen de kern van een cluster.
    volgorde = sorted(scores, key=lambda paar: -scores[paar])

    def _mag_samen(kandidaat: int, cluster: list[int]) -> str | None:
        """Geeft de weigergrond terug, of None wanneer samenvoegen mag."""
        for lid in cluster:
            paar = (kandidaat, lid) if kandidaat < lid else (lid, kandidaat)
            if paar not in scores:
                return "koppeling"  # volledige koppeling
            tekst_a, tekst_b = teksten[ids[kandidaat]], teksten[ids[lid]]
            if contradicts(
                extract_numbers(tekst_a), extract_negations(tekst_a),
                tekst_b, artefact_text=tekst_a,
                artefact_negation_tokens=extract_negation_tokens(tekst_a),
            ):
                return "tegenspraak"  # DR8
            # Het veto draait als láátste: de goedkope, deterministische regels
            # hebben dan al gefilterd, en het dure model wordt alleen geraadpleegd
            # voor paren die anders daadwerkelijk zouden samensmelten.
            if veto is not None and veto(
                tekst_a, tekst_b, talen[ids[kandidaat]], talen[ids[lid]]
            ):
                return "veto"
        return None

    for a, b in volgorde:
        cluster_a, cluster_b = van_index.get(a), van_index.get(b)
        if cluster_a is not None and cluster_a == cluster_b:
            continue
        if cluster_a is None and cluster_b is None:
            grond = _mag_samen(a, [b])
            if grond is not None:
                geblokkeerd += grond == "tegenspraak"
                afgeketst += grond == "koppeling"
                veto_geblokkeerd += grond == "veto"
                continue
            clusters.append([a, b])
            van_index[a] = van_index[b] = len(clusters) - 1
        elif cluster_a is None or cluster_b is None:
            nieuw, bestaand = (a, cluster_b) if cluster_a is None else (b, cluster_a)
            grond = _mag_samen(nieuw, clusters[bestaand])
            if grond is not None:
                geblokkeerd += grond == "tegenspraak"
                afgeketst += grond == "koppeling"
                veto_geblokkeerd += grond == "veto"
                continue
            clusters[bestaand].append(nieuw)
            van_index[nieuw] = bestaand
        # Twee bestaande clusters samenvoegen doen we niet: dat is precies de
        # ketenvorming die volledige koppeling moet voorkomen.

    for leden in clusters:
        namen = [ids[i] for i in leden]
        cid = _cluster_id(namen)
        for naam in namen:
            conn.execute(
                "UPDATE claim SET cluster_id = ? WHERE claim_id = ?", (cid, naam)
            )
    # Alles wat hier meedeed is bekeken; incrementeel clusteren (#25.4) gaat
    # alleen nog over wat erna binnenkomt.
    conn.executemany(
        "UPDATE claim SET cluster_bekeken = 1 WHERE claim_id = ?", [(i,) for i in ids]
    )
    conn.commit()

    groottes = [len(leden) for leden in clusters]
    return ClusterReport(
        claims=len(ids),
        clusters=len(ids) - sum(groottes) + len(clusters),
        clusters_with_multiple_members=len(clusters),
        largest_cluster=max(groottes) if groottes else 1,
        blocked_by_contradiction=geblokkeerd,
        blocked_by_linkage=afgeketst,
        blocked_by_veto=veto_geblokkeerd,
    )


@dataclass(frozen=True)
class IncrementRapport:
    verwerkt: int
    aangesloten: int
    nieuwe_clusters: int
    geblokkeerd_tegenspraak: int
    geblokkeerd_koppeling: int
    geblokkeerd_veto: int
    resterend: int


def markeer_bekeken_volgens(conn: sqlite3.Connection, pad: str) -> int:
    """Eenmalig: claims die in een eerdere volledige bouw zaten zijn bekeken
    (#25.4). Alleen wat daarna binnenkwam moet nog incrementeel."""
    conn.execute("ATTACH DATABASE ? AS eerder", (pad,))
    try:
        cursor = conn.execute(
            "UPDATE claim SET cluster_bekeken = 1"
            " WHERE claim_id IN (SELECT claim_id FROM eerder.claim)"
        )
        conn.commit()
        return cursor.rowcount
    finally:
        conn.execute("DETACH DATABASE eerder")


def begin_opnieuw(conn: sqlite3.Connection, model_version: str, threshold: float, *,
                  veto_version: str) -> None:
    """Begint de clustering opnieuw voor een nieuw model of een nieuwe drempel (#25.14c).

    Clusters van een ander model zijn ongeldig (DR6): de gelijkenissen waarop
    ze rusten bestaan niet meer. Dit wist alle toewijzingen en markeringen en
    legt de nieuwe toestand vast, waarna `cluster_incrementeel` alles in
    porties opnieuw opbouwt, hervatbaar en met pauzes. Een volledige herbouw
    in één keer liep de laptop heet (#25.4).
    """
    conn.execute("UPDATE claim SET cluster_id = NULL, cluster_bekeken = 0")
    conn.execute("DELETE FROM cluster_state")
    conn.execute(
        "INSERT INTO cluster_state (id, model_version, threshold, veto_version) VALUES (1, ?, ?, ?)",
        (model_version, threshold, veto_version),
    )
    conn.commit()


def cluster_incrementeel(
    conn: sqlite3.Connection,
    model_version: str,
    threshold: float,
    veto=None,
    *,
    portie: int = 256,
    max_porties: int | None = None,
    pauze: float = 0.0,
    voortgang=None,
) -> IncrementRapport:
    """Clustert alleen nog niet bekeken claims, portie voor portie (#25.4).

    Dezelfde regels als `build_clusters`: een claim mag alleen bij een cluster
    als hij boven de drempel ligt met élk lid (volledige koppeling), DR8 vóór
    het veto, en twee bestaande clusters worden nooit samengevoegd. Het veto
    draait hier direct bij elke samenvoeging in plaats van achteraf: dat is
    even conservatief en raakt alleen de paren die echt samengaan. Elke portie
    wordt apart vastgelegd, zodat het hervatbaar is en tussendoor kan stoppen.

    Weigert op een clustertoestand met een andere modelversie, drempel of
    vetoversie: incrementeel bijbouwen op een anders gebouwde stand zou twee
    regels door elkaar mengen.
    """
    import time

    toestand = conn.execute(
        "SELECT model_version, threshold, veto_version FROM cluster_state WHERE id = 1"
    ).fetchone()
    vetoversie = getattr(veto, "model_version", "") or ""
    if toestand is None or (
        toestand["model_version"], float(toestand["threshold"]), toestand["veto_version"] or ""
    ) != (model_version, float(threshold), vetoversie):
        raise ClusterStateMismatchError(
            f"clustertoestand {tuple(toestand) if toestand else None} past niet bij"
            f" ({model_version!r}, {threshold}, {vetoversie!r}); bouw eerst volledig"
            " met python -m doublecheck.clustering"
        )

    rijen = conn.execute(
        "SELECT c.claim_id, c.canonical_text, c.language, c.cluster_id, c.cluster_bekeken,"
        " f.payload FROM claim c JOIN fingerprint f ON f.claim_id = c.claim_id"
        " WHERE f.kind = 'text' AND f.model_version = ? ORDER BY c.claim_id",
        (model_version,),
    ).fetchall()
    ids = [r["claim_id"] for r in rijen]
    teksten = [r["canonical_text"] for r in rijen]
    talen = [r["language"] for r in rijen]
    matrix = np.vstack([np.frombuffer(r["payload"], dtype=np.float32) for r in rijen]) if rijen else None
    nieuw = [i for i, r in enumerate(rijen) if not r["cluster_bekeken"]]

    leden: dict[str, list[int]] = {}
    van: dict[int, str] = {}
    for i, r in enumerate(rijen):
        if r["cluster_id"]:
            leden.setdefault(r["cluster_id"], []).append(i)
            van[i] = r["cluster_id"]

    tel = dict(aangesloten=0, nieuwe_clusters=0, tegenspraak=0, koppeling=0, veto=0)

    def _grond(kandidaat: int, groep: list[int]) -> str | None:
        for lid in groep:
            if float(matrix[kandidaat] @ matrix[lid]) < threshold:
                return "koppeling"
        for lid in groep:
            tekst_a, tekst_b = teksten[kandidaat], teksten[lid]
            if contradicts(
                extract_numbers(tekst_a), extract_negations(tekst_a), tekst_b,
                artefact_text=tekst_a,
                artefact_negation_tokens=extract_negation_tokens(tekst_a),
            ):
                return "tegenspraak"
        if veto is not None:
            for lid in groep:
                if veto(teksten[kandidaat], teksten[lid], talen[kandidaat], talen[lid]):
                    return "veto"
        return None

    verwerkt = 0
    volgnummer = 0
    for start in range(0, len(nieuw), portie):
        if max_porties is not None and volgnummer >= max_porties:
            break
        blok = nieuw[start:start + portie]
        sims = matrix[blok] @ matrix.T
        paren = []
        for rij_nr, n in enumerate(blok):
            for o in np.nonzero(sims[rij_nr] >= threshold)[0]:
                o = int(o)
                if o != n:
                    paren.append((float(sims[rij_nr, o]), n, o))
        del sims
        paren.sort(reverse=True)
        gewijzigd: set[str] = set()
        for _, n, o in paren:
            cn, co = van.get(n), van.get(o)
            if cn is not None and cn == co:
                continue
            if cn is None and co is None:
                grond = _grond(n, [o])
                if grond:
                    tel[grond] += 1
                    continue
                sleutel = f"nieuw-{n}"
                leden[sleutel] = [n, o]
                van[n] = van[o] = sleutel
                gewijzigd.add(sleutel)
                tel["nieuwe_clusters"] += 1
            elif cn is None or co is None:
                kandidaat, bestaand = (n, co) if cn is None else (o, cn)
                grond = _grond(kandidaat, leden[bestaand])
                if grond:
                    tel[grond] += 1
                    continue
                leden[bestaand].append(kandidaat)
                van[kandidaat] = bestaand
                gewijzigd.add(bestaand)
                if not bestaand.startswith("nieuw-"):
                    tel["aangesloten"] += 1
            # Twee clusters samenvoegen doen we niet (ketenvorming).

        # Vastleggen: gewijzigde clusters krijgen hun stabiele ID opnieuw.
        for sleutel in gewijzigd:
            groep = leden.pop(sleutel)
            cid = _cluster_id([ids[i] for i in groep])
            leden[cid] = groep
            for i in groep:
                van[i] = cid
                conn.execute("UPDATE claim SET cluster_id = ? WHERE claim_id = ?", (cid, ids[i]))
        conn.executemany(
            "UPDATE claim SET cluster_bekeken = 1 WHERE claim_id = ?", [(ids[i],) for i in blok]
        )
        conn.commit()
        verwerkt += len(blok)
        volgnummer += 1
        if voortgang is not None:
            voortgang(verwerkt, len(nieuw))
        if pauze and start + portie < len(nieuw):
            time.sleep(pauze)

    return IncrementRapport(
        verwerkt=verwerkt,
        aangesloten=tel["aangesloten"],
        nieuwe_clusters=tel["nieuwe_clusters"],
        geblokkeerd_tegenspraak=tel["tegenspraak"],
        geblokkeerd_koppeling=tel["koppeling"],
        geblokkeerd_veto=tel["veto"],
        resterend=len(nieuw) - verwerkt,
    )


class ClusterStateMismatchError(Exception):
    """De clustertoewijzing is met andere instellingen gebouwd (#12.3)."""


def ensure_clusters_match(
    conn: sqlite3.Connection, model_version: str, threshold: float
) -> None:
    """Weigert luid wanneer het clusterbewuste cijfer op oude clusters zou slaan.

    De benchmark *leest* `claim.cluster_id` en bouwt niet, dus zonder deze
    controle hangt dat cijfer af van wanneer er voor het laatst geclusterd is.
    Bij etappe 12 sloeg het daadwerkelijk even op clusters van een ándere drempel
    (BENCHMARK.md §23e).

    Een database zónder clustertoewijzing is géén mismatch: dat is de legitieme
    beginstand, net als een lege index (E3.S1-AC2) en een lege testset (#11.5).
    Een toewijzing zónder vastgelegde herkomst wél.
    """
    toegewezen = conn.execute(
        "SELECT count(*) FROM claim WHERE cluster_id IS NOT NULL"
    ).fetchone()[0]
    rij = conn.execute(
        "SELECT model_version, threshold FROM cluster_state WHERE id = 1"
    ).fetchone()

    if rij is None:
        if not toegewezen:
            return
        raise ClusterStateMismatchError(
            "clusters zijn toegewezen zonder vastgelegde herkomst; bouw ze"
            " opnieuw met python -m doublecheck.clustering"
        )
    if rij["model_version"] != model_version or abs(rij["threshold"] - threshold) > 1e-9:
        raise ClusterStateMismatchError(
            f"clusters gebouwd met model {rij['model_version']!r} op drempel"
            f" {rij['threshold']}, gevraagd is {model_version!r} op {threshold};"
            " bouw ze opnieuw met python -m doublecheck.clustering"
        )


def main() -> None:
    import argparse

    from doublecheck.config import load_config
    from doublecheck.storage import connect, init_schema

    parser = argparse.ArgumentParser(description="Doublecheck clusters bouwen (DR7)")
    parser.add_argument("--db", default="doublecheck.db")
    parser.add_argument("--zonder-veto", action="store_true",
                        help="sla het NLI-veto over (sneller, ruimer clusteren)")
    parser.add_argument("--incrementeel", action="store_true",
                        help="alleen nog niet bekeken claims, in porties (#25.4)")
    parser.add_argument("--portie", type=int, default=256)
    parser.add_argument("--max-porties", type=int, default=None)
    parser.add_argument("--pauze", type=float, default=3.0,
                        help="seconden rust tussen porties, zodat de machine afkoelt")
    parser.add_argument("--threads", type=int, default=2,
                        help="maximaal aantal rekenthreads (numpy én het NLI-model)")
    parser.add_argument("--opnieuw", action="store_true",
                        help="na een modelwissel: wis de clusters en leg de nieuwe toestand vast;"
                             " bouw daarna met --incrementeel (#25.14c)")
    parser.add_argument("--bekeken-volgens", metavar="DB",
                        help="eenmalig: markeer claims uit deze eerdere database als bekeken")
    args = parser.parse_args()

    # Begrenzen vóór er gerekend wordt: torch en de BLAS-bibliotheek pakken
    # anders elk alle kernen, en dat liep de laptop heet (#25.4).
    from threadpoolctl import threadpool_limits

    threadpool_limits(limits=args.threads)
    config = load_config()
    veto = None
    if not args.zonder_veto:
        import torch

        torch.set_num_threads(args.threads)
        from doublecheck.nli import same_language_veto

        veto = same_language_veto(
            config.model_versions.nli, config.thresholds.nli_contradiction
        )
    conn = connect(args.db)
    init_schema(conn)
    if args.opnieuw:
        begin_opnieuw(conn, config.model_versions.text_embedding, config.thresholds.cluster_same,
                      veto_version=getattr(veto, "model_version", "") or "")
        print(f"clusters gewist; toestand: {config.model_versions.text_embedding} op"
              f" {config.thresholds.cluster_same}. Bouw nu met --incrementeel.")
        conn.close()
        return
    if args.bekeken_volgens:
        n = markeer_bekeken_volgens(conn, args.bekeken_volgens)
        print(f"als bekeken gemarkeerd: {n} claims uit {args.bekeken_volgens}")
        conn.close()
        return
    if args.incrementeel:
        def _voortgang(gedaan, totaal):
            print(f"  {gedaan}/{totaal}", flush=True)

        rapport = cluster_incrementeel(
            conn, config.model_versions.text_embedding, config.thresholds.cluster_same,
            veto, portie=args.portie, max_porties=args.max_porties, pauze=args.pauze,
            voortgang=_voortgang,
        )
        print(f"incrementeel: {rapport.verwerkt} verwerkt, {rapport.resterend} resterend ·"
              f" {rapport.aangesloten} aangesloten bij een bestaand cluster ·"
              f" {rapport.nieuwe_clusters} nieuwe clusters · tegengehouden:"
              f" {rapport.geblokkeerd_tegenspraak} DR8, {rapport.geblokkeerd_koppeling}"
              f" koppeling, {rapport.geblokkeerd_veto} veto")
        conn.close()
        return
    print(f"clusteren op drempel {config.thresholds.cluster_same}"
          f" · model {config.model_versions.text_embedding}"
          + ("" if veto else " · zonder veto"))
    # Clusteren gebeurt zónder veto; dat draait er daarna overheen (#16.2).
    # Binnen de samenvoeglus vuurde het op elke poging — 394.221 kandidaatparen,
    # ~22 uur. Achteraf raakt het alleen de paren die daadwerkelijk samen in een
    # cluster zitten, en dat is de enige verzameling waar blokkeren iets doet.
    rapport = build_clusters(
        conn,
        config.model_versions.text_embedding,
        config.thresholds.cluster_same,
    )
    print(f"  {rapport.claims} claims → {rapport.clusters} clusters,"
          f" {rapport.clusters_with_multiple_members} met meer dan één lid"
          f" (grootste {rapport.largest_cluster})")
    print(f"  tegengehouden: {rapport.blocked_by_contradiction} door DR8,"
          f" {rapport.blocked_by_linkage} door volledige koppeling")

    if veto is not None:
        vetorapport = splits_op_veto(conn, veto)
        print(f"  veto: {vetorapport.beoordeelde_paren} paren beoordeeld,"
              f" {vetorapport.geblokkeerde_paren} geblokkeerd,"
              f" {vetorapport.gesplitste_clusters} clusters gesplitst")
    conn.close()

@dataclass(frozen=True)
class VetoReport:
    beoordeelde_paren: int
    geblokkeerde_paren: int
    gesplitste_clusters: int
    # De paren zelf, zodat een blokkade na te rekenen is. Een telling zonder de
    # paren is niet te beoordelen — de benchmark laat zijn fouten al inspecteren
    # (`--failures`), en het veto hoort dat ook te doen (#16.3).
    geblokkeerd: tuple[tuple[str, str], ...] = ()


def splits_op_veto(conn: sqlite3.Connection, veto) -> VetoReport:
    """Past het NLI-veto toe ná het clusteren in plaats van erbinnen (#16.2).

    Het veto zat in de samenvoeglus en vuurde dus op elke *poging* — ook op
    paren die uiteindelijk toch niet bij elkaar kwamen. Op het huidige corpus
    zijn dat 394.221 kandidaatparen, oftewel ~22 uur modelwerk (§39e).

    Maar het veto kan alleen **blokkeren**, en blokkeren heeft alleen zin voor
    paren die daadwerkelijk samen in een cluster zijn beland. Alle overige
    aanroepen zijn verspilling: die claims zitten al niet bij elkaar. Achteraf
    toetsen is daarmee niet alleen goedkoper maar raakt precies de juiste
    verzameling — de paren binnen gevormde clusters.

    **Niet bit-identiek aan de oude volgorde.** Een blokkade tijdens het
    samenvoegen kon een ánder cluster laten ontstaan; hier splitsen we een
    bestaand cluster. Het verschil is tweede-orde, en de uitkomst blijft even
    conservatief: er wordt nooit méér samengevoegd dan zonder veto.
    """
    groepen: dict[str, list[str]] = {}
    teksten: dict[str, str] = {}
    talen: dict[str, str] = {}
    for rij in conn.execute(
        "SELECT claim_id, canonical_text, language, cluster_id FROM claim"
        " WHERE cluster_id IS NOT NULL ORDER BY claim_id"
    ):
        groepen.setdefault(rij["cluster_id"], []).append(rij["claim_id"])
        teksten[rij["claim_id"]] = rij["canonical_text"]
        talen[rij["claim_id"]] = rij["language"]

    beoordeeld = gesplitst = 0
    geblokkeerde_paren: list[tuple[str, str]] = []
    for leden in groepen.values():
        if len(leden) < 2:
            continue
        verboden: set[tuple[str, str]] = set()
        for a_index, a in enumerate(leden):
            for b in leden[a_index + 1:]:
                beoordeeld += 1
                if veto(teksten[a], teksten[b], talen[a], talen[b]):
                    verboden.add((a, b))
                    geblokkeerde_paren.append((teksten[a], teksten[b]))
        if not verboden:
            continue
        gesplitst += 1
        for naam in leden:
            conn.execute(
                "UPDATE claim SET cluster_id = NULL WHERE claim_id = ?", (naam,)
            )
        # Opnieuw opbouwen met volledige koppeling over de toegestane paren:
        # een lid mag alleen bij een groep als het met élk lid daarin mag.
        nieuwe: list[list[str]] = []
        for naam in leden:
            for groep in nieuwe:
                if all(
                    (lid, naam) not in verboden and (naam, lid) not in verboden
                    for lid in groep
                ):
                    groep.append(naam)
                    break
            else:
                nieuwe.append([naam])
        for groep in nieuwe:
            if len(groep) < 2:
                continue  # een eenling is geen cluster
            cid = _cluster_id(groep)
            for naam in groep:
                conn.execute(
                    "UPDATE claim SET cluster_id = ? WHERE claim_id = ?", (cid, naam)
                )

    conn.execute(
        "UPDATE cluster_state SET veto_version = ? WHERE id = 1",
        (getattr(veto, "model_version", "") or "",),
    )
    conn.commit()
    return VetoReport(
        beoordeeld, len(geblokkeerde_paren), gesplitst,
        tuple(geblokkeerde_paren),
    )


if __name__ == "__main__":
    main()
