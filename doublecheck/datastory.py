"""De datastory: desinformatie sterft niet, ze verhuist (PLAN.md #22.6, #25.14d c).

Rekent de cijfers van de blog en de cijferbijlage uit de clusters, met de
curatieregels uit `docs/pers/CIJFERBIJLAGE.md`:

- **basis**: clusters met minstens twee claims;
- **C1, junkfilter**: een cluster telt alleen als élke claimtekst na strip
  minstens 25 tekens is (ClaimReview-vervuiling als "Facebook");
- **meertalig**: minstens twee verschillende `claim.language` in het cluster;
- **zombie**: oudste en nieuwste géldige `review_date` (kale ISO-datum, niet
  in de toekomst, de §58-regel) minstens 365 dagen uit elkaar; de blog deelt
  ze in 1–2, 2–4 en 4+ jaar.

De clusters hangen aan het model (DR6). Na een modelwissel horen deze
cijfers dus opnieuw berekend te worden: `python -m doublecheck.datastory`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date

_MIN_TEKENS = 25
_DATUM = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_EEN_JAAR, _TWEE_JAAR, _VIER_JAAR = 365, 730, 1461


@dataclass
class Uitslag:
    clusters: int = 0
    geweerd_c1: int = 0
    meertalig: int = 0
    zombies: int = 0
    zombies_twee_jaar: int = 0
    per_kloof: dict[str, int] = field(default_factory=lambda: {"1-2 jaar": 0, "2-4 jaar": 0, "4+ jaar": 0})
    kloof_per_cluster: dict[str, int] = field(default_factory=dict)


def _geldige_datums(datums, vandaag: str) -> list[date]:
    return [date.fromisoformat(d) for d in datums
            if isinstance(d, str) and _DATUM.match(d) and d <= vandaag]


def _clusters(conn):
    leden: dict[str, list] = {}
    for cid, cluster, tekst, taal in conn.execute(
            "SELECT claim_id, cluster_id, canonical_text, language FROM claim WHERE cluster_id IS NOT NULL"):
        leden.setdefault(cluster, []).append((cid, tekst, taal))
    datums: dict[str, list[str]] = {}
    for cid, datum in conn.execute("SELECT claim_id, review_date FROM factcheck"):
        datums.setdefault(cid, []).append(datum)
    return {k: v for k, v in leden.items() if len(v) >= 2}, datums


def bereken(conn, *, vandaag: str | None = None) -> Uitslag:
    vandaag = vandaag or date.today().isoformat()
    clusters, datums = _clusters(conn)
    u = Uitslag()
    for naam, leden in clusters.items():
        if any(len((tekst or "").strip()) < _MIN_TEKENS for _, tekst, _ in leden):
            u.geweerd_c1 += 1
            continue
        u.clusters += 1
        if len({taal for _, _, taal in leden}) >= 2:
            u.meertalig += 1
        geldig = _geldige_datums([d for cid, _, _ in leden for d in datums.get(cid, [])], vandaag)
        if not geldig:
            continue
        kloof = (max(geldig) - min(geldig)).days
        u.kloof_per_cluster[naam] = kloof
        if kloof >= _EEN_JAAR:
            u.zombies += 1
            u.zombies_twee_jaar += kloof >= _TWEE_JAAR
            sleutel = "1-2 jaar" if kloof < _TWEE_JAAR else "2-4 jaar" if kloof < _VIER_JAAR else "4+ jaar"
            u.per_kloof[sleutel] += 1
    return u


def zoek_voorbeeld(conn, zoektermen: list[str], *, vandaag: str | None = None) -> dict | None:
    """Het eerste cluster met een claim die een van de zoektermen bevat."""
    vandaag = vandaag or date.today().isoformat()
    for term in zoektermen:
        rij = conn.execute(
            "SELECT cluster_id FROM claim WHERE cluster_id IS NOT NULL AND instr(lower(canonical_text), lower(?)) > 0",
            (term,)).fetchone()
        if rij is None:
            continue
        leden = conn.execute("SELECT claim_id, language, canonical_text FROM claim WHERE cluster_id = ?",
                             (rij[0],)).fetchall()
        ids = [r[0] for r in leden]
        alle = [d for (d,) in conn.execute(
            f"SELECT review_date FROM factcheck WHERE claim_id IN ({','.join('?' * len(ids))})", ids)]
        geldig = _geldige_datums(alle, vandaag)
        return {
            "cluster": rij[0],
            "claims": len(leden),
            "talen": sorted({r[1] for r in leden}),
            "kloof_dagen": (max(geldig) - min(geldig)).days if geldig else None,
            "van": min(geldig).isoformat() if geldig else None,
            "tot": max(geldig).isoformat() if geldig else None,
        }
    return None


# De redactionele voorbeelden uit de cijferbijlage en de blog, met zoektermen
# in de talen waarin ze in het corpus staan.
VOORBEELDEN = {
    "zonnebril en huidkanker": ["sunglasses cause skin cancer", "gafas de sol", "zonnebril"],
    "nepvingers bij de Lok Sabha": ["fake fingers", "fake finger", "नकली उंगली"],
    "volkslied door UNESCO": ["UNESCO declared", "national anthem", "जन गण मन"],
    "WhatsApp wordt betaald": ["WhatsApp will be paid", "WhatsApp will start charging", "WhatsApp to charge"],
    "condoleance Khaled Mashal": ["Mashal", "Meshaal", "مشعل"],
}


def main() -> None:
    import json
    import os

    from doublecheck.storage import connect

    conn = connect(os.environ.get("DOUBLECHECK_DB", "doublecheck.db"))
    u = bereken(conn)
    print(f"clusters na C1: {u.clusters} (geweerd door C1: {u.geweerd_c1})")
    print(f"meertalig: {u.meertalig} · zombies (1 jaar of meer): {u.zombies}"
          f" · waarvan 2 jaar of meer: {u.zombies_twee_jaar} · {u.per_kloof}")
    for naam, termen in VOORBEELDEN.items():
        print(f"  {naam}: {json.dumps(zoek_voorbeeld(conn, termen), ensure_ascii=False)}")


if __name__ == "__main__":
    main()
