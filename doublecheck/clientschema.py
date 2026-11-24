"""Haalbaarheid van een clientschema voor tekst (#24.2b, PROTOCOL §4).

Vraag: kan de plug-in parafrases herkennen met een tekstmodel in de browser,
zodat ook een niet-letterlijke post een label krijgt zonder dat er tekst het
apparaat verlaat? Een browsermodel is gekwantiseerd (int8), dus de vraag wordt:
blijven de beslissingen van de resolver gelijk als beide kanten met het int8-
model worden gefingerprint?

Meting zonder het corpus opnieuw te embedden: de testset bewaart alleen
fingerprints (DR3), maar is met waarheid-door-constructie uit claimteksten
afgeleid. Elk artefact wordt opnieuw afgeleid en geverifieerd tegen de
bewaarde fp32-vector (cosinus ≥ 0,9999); daarna wordt per paar de gelijkenis
met fp32 en met int8 vergeleken en geteld welke beslissingen over een drempel
springen. Het is een paarmaat: de zoekstap over het hele corpus (de dichtste
buur) moet apart gemeten worden vóór een schema wordt aangeboden.

Twee int8-varianten, omdat een browserbuild (ONNX int8) meer kwantiseert dan
torch: A = alleen de Linear-lagen (torch dynamic int8), B = A plus de
woordembeddingtabel per rij naar int8 (de tabel is 250.002 × 384 en dus het
grootste deel van het model). B is de realistische benadering.

Dit wijzigt niets aan discovery: `schemes.text` blijft leeg tot een schema een
eigen drempel en een eigen benchmark heeft (§4).
"""

from __future__ import annotations

import copy
from dataclasses import dataclass

import numpy as np

from doublecheck.testset import (
    _digit_swap_variant,
    _dressing_variant,
    _negation_variant,
    _truncation_variant,
)


def band(sim: float, match: float, related: float) -> str:
    if sim >= match:
        return "matched"
    if sim >= related:
        return "related"
    return "none"


@dataclass(frozen=True)
class Meting:
    soort: str
    is_same: bool
    sim_fp32: float
    sim_int8: float
    match: float
    related: float


def wissels(rijen: list[Meting]) -> dict:
    per_soort: dict[str, int] = {}
    nieuwe_fouten = verloren_dekking = gewonnen_dekking = verdwenen_fouten = 0
    for r in rijen:
        a = band(r.sim_fp32, r.match, r.related)
        b = band(r.sim_int8, r.match, r.related)
        if a == b:
            continue
        per_soort[r.soort] = per_soort.get(r.soort, 0) + 1
        if not r.is_same and b == "matched":
            nieuwe_fouten += 1
        if not r.is_same and a == "matched":
            verdwenen_fouten += 1
        if r.is_same and a == "matched":
            verloren_dekking += 1
        if r.is_same and b == "matched":
            gewonnen_dekking += 1
    return {
        "totaal": sum(per_soort.values()),
        "per_soort": per_soort,
        "nieuwe_fouten": nieuwe_fouten,
        "verdwenen_fouten": verdwenen_fouten,
        "verloren_dekking": verloren_dekking,
        "gewonnen_dekking": gewonnen_dekking,
    }


def afruil(sims: np.ndarray, zelfde: np.ndarray, drempel: float) -> tuple[int, int]:
    """Paarmaat zonder de DR8-, cijfer- en ontkenningswachters: fouten zijn
    niet-zelfde paren boven de drempel, dekking zijn zelfde paren erboven.
    Alleen bruikbaar om schema's onder dezelfde regel te vergelijken."""
    boven = sims >= drempel
    return int(np.sum(boven & ~zelfde)), int(np.sum(boven & zelfde))


def beste_drempel(sims: np.ndarray, zelfde: np.ndarray, *, max_fouten: int) -> tuple[float, int, int]:
    """De drempel met de meeste dekking bij hooguit `max_fouten` fouten."""
    beste = (1.0001, 0, 0)
    for d in sorted(set(np.round(sims, 4).tolist()) | {1.0001}, reverse=True):
        f, dek = afruil(sims, zelfde, d)
        if f <= max_fouten and dek > beste[2]:
            beste = (float(d), f, dek)
    return beste


def kwantiseer_rijen(matrix: np.ndarray) -> np.ndarray:
    """Symmetrisch int8 per rij, teruggerekend naar float (nepkwantisering)."""
    schaal = np.abs(matrix).max(axis=1, keepdims=True) / 127.0
    veilig = np.where(schaal == 0, 1.0, schaal)
    q = np.clip(np.rint(matrix / veilig), -127, 127)
    return (q * veilig * (schaal != 0)).astype(matrix.dtype)


def kandidaten(
    soort: str,
    claim_id: str,
    claimtekst: str,
    taal: str,
    teksten_per_id: dict[str, str],
    vertalingen_per_claim: dict[str, list[str]],
) -> list[str]:
    """Welke artefacttekst kan de bouwer bij dit paar gemaakt hebben."""
    if soort == "origineel":
        return [claimtekst]
    if soort == "vervorming":
        return list(dict.fromkeys(_dressing_variant(claimtekst, k) for k in range(4)))
    if soort == "inkorting":
        v = _truncation_variant(claimtekst, controleer=False)
        return [v] if v else []
    if soort == "ontkenning":
        v = _negation_variant(claimtekst, taal, controleer=False)
        return [v] if v else []
    if soort == "cijferwissel":
        v = _digit_swap_variant(claimtekst)
        return [v] if v else []
    if soort.startswith("hardste-buur:"):
        buur = teksten_per_id.get(soort.split(":", 1)[1])
        return [buur] if buur else []
    if soort == "vertaling":
        return list(vertalingen_per_claim.get(claim_id, []))
    return []


def _encode(model, teksten: list[str]) -> np.ndarray:
    from doublecheck.embedding import normaliseer_voor_embedding

    return np.asarray(
        model.encode(
            [normaliseer_voor_embedding(t) for t in teksten],
            normalize_embeddings=True,
            show_progress_bar=False,
            batch_size=64,
        ),
        dtype=np.float32,
    )


def int8_modellen(model_version: str):
    """Twee verse kopieën (nooit het gecachete productiemodel muteren)."""
    import torch
    from sentence_transformers import SentenceTransformer

    from doublecheck.embedding import _modelspec

    if "qnnpack" in torch.backends.quantized.supported_engines:
        torch.backends.quantized.engine = "qnnpack"
    # CPU voor alle drie: kwantiseren kan niet op MPS, en fp32 en int8 moeten
    # op hetzelfde apparaat draaien om alleen het effect van int8 te meten.
    naam, revisie, _ = _modelspec(model_version)
    basis = SentenceTransformer(naam, revision=revisie, device="cpu")
    a = torch.ao.quantization.quantize_dynamic(copy.deepcopy(basis), {torch.nn.Linear}, dtype=torch.qint8)
    b = torch.ao.quantization.quantize_dynamic(copy.deepcopy(basis), {torch.nn.Linear}, dtype=torch.qint8)
    tabel = b[0].auto_model.embeddings.word_embeddings.weight
    tabel.data = torch.from_numpy(kwantiseer_rijen(tabel.data.numpy()))
    params = sum(p.numel() for p in basis.parameters())
    return basis, a, b, params


def main() -> None:
    import os
    import time

    import torch

    from doublecheck.config import load_config
    from doublecheck.storage import connect
    from doublecheck.vertalingen import load_translations

    torch.set_num_threads(4)  # laptop koel houden; dit is een paarmeting, geen herindex
    config = load_config()
    versie = config.model_versions.text_embedding
    t = config.thresholds
    conn = connect(os.environ.get("DOUBLECHECK_DB", "doublecheck.db"))

    paren = conn.execute(
        "SELECT p.claim_id, p.is_same, p.provenance, p.language, p.payload, c.canonical_text"
        " FROM testpair p JOIN claim c ON c.claim_id = p.claim_id"
        " WHERE p.kind = 'text' AND p.model_version = ? ORDER BY p.testpair_id",
        (versie,),
    ).fetchall()
    buur_ids = {r[2].split(":", 1)[1] for r in paren if r[2].startswith("hardste-buur:")}
    teksten_per_id = dict(
        conn.execute(
            f"SELECT claim_id, canonical_text FROM claim WHERE claim_id IN ({','.join('?' * len(buur_ids))})",
            list(buur_ids),
        ).fetchall()
    ) if buur_ids else {}
    vertalingen: dict[str, list[str]] = {}
    for p in load_translations():
        vertalingen.setdefault(p["claim_id"], []).append(p["doel"])

    begin = time.perf_counter()
    basis, model_a, model_b, params = int8_modellen(versie)

    # 1. Herleiden en verifiëren tegen de bewaarde fp32-vector.
    alle_kandidaten: list[str] = []
    per_paar: list[list[int]] = []
    for claim_id, _, soort, taal, _, tekst in paren:
        ks = kandidaten(soort, claim_id, tekst, taal, teksten_per_id, vertalingen)
        per_paar.append(list(range(len(alle_kandidaten), len(alle_kandidaten) + len(ks))))
        alle_kandidaten.extend(ks)
    kand32 = _encode(basis, alle_kandidaten)
    herleid: list[tuple[int, str]] = []
    for i, (rij, idx) in enumerate(zip(paren, per_paar)):
        bewaard = np.frombuffer(rij[4], dtype=np.float32)
        beste = max(idx, key=lambda j: float(kand32[j] @ bewaard), default=None)
        if beste is not None and float(kand32[beste] @ bewaard) >= 0.9999:
            herleid.append((i, alle_kandidaten[beste]))

    # 2. Gelijkenis per paar, fp32 tegenover int8 (A en B).
    artefacten = [a for _, a in herleid]
    claims = [paren[i][5] for i, _ in herleid]
    resultaten = {}
    for naam, model in (("fp32", basis), ("int8-A", model_a), ("int8-B", model_b)):
        resultaten[naam] = (_encode(model, artefacten), _encode(model, claims))
    sim = {n: np.einsum("ij,ij->i", a, c) for n, (a, c) in resultaten.items()}
    trouw = {n: np.einsum("ij,ij->i", resultaten["fp32"][0], resultaten[n][0]) for n in ("int8-A", "int8-B")}

    print(f"testparen {len(paren)} · herleid en geverifieerd {len(herleid)} "
          f"({len(herleid) / len(paren):.1%}) · duur {time.perf_counter() - begin:.0f} s")
    print(f"model: {params / 1e6:.0f} M parameters · fp32 {params * 4 / 2**20:.0f} MiB · "
          f"int8 (browser) ~{params / 2**20:.0f} MiB")
    for naam in ("int8-A", "int8-B"):
        rijen = []
        for (i, _), s32, s8 in zip(herleid, sim["fp32"], sim[naam]):
            _, is_same, soort, taal, _, _ = paren[i]
            match = t.text_match_crosslingual if taal == "crosslinguaal" else t.text_match
            rijen.append(Meting(soort.split(":")[0], bool(is_same), float(s32), float(s8), match, t.text_related))
        r = wissels(rijen)
        delta = np.abs(sim["fp32"] - sim[naam])
        print(f"\n{naam}: cosinus fp32↔int8 per artefact min {trouw[naam].min():.4f} · "
              f"mediaan {np.median(trouw[naam]):.4f}")
        print(f"  |Δ gelijkenis| mediaan {np.median(delta):.4f} · p99 {np.quantile(delta, 0.99):.4f} · max {delta.max():.4f}")
        print(f"  beslissingswissels {r['totaal']} van {len(rijen)} · per soort {r['per_soort']}")
        print(f"  nieuwe fouten {r['nieuwe_fouten']} · verdwenen fouten {r['verdwenen_fouten']} · "
              f"dekking verloren {r['verloren_dekking']} · gewonnen {r['gewonnen_dekking']}")

    # Eigen schema, eigen drempel (§4). Ontkennings- en cijferparen blokkeren
    # de deterministische wachters ongeacht het model; wat het model zelf moet
    # scheiden zijn de hardste buren. Dus: eentalige zelfde-paren tegen de
    # hardste buren.
    gekozen = [
        k for k, (i, _) in enumerate(herleid)
        if paren[i][3] != "crosslinguaal"
        and (paren[i][1] or paren[i][2].startswith("hardste-buur:"))
    ]
    zelfde = np.array([bool(paren[herleid[k][0]][1]) for k in gekozen])
    s32 = sim["fp32"][gekozen]
    ref_f, ref_d = afruil(s32, zelfde, t.text_match)
    print(f"\neigen drempel (eentalig: {int(zelfde.sum())} zelfde-paren tegen "
          f"{int((~zelfde).sum())} hardste buren):")
    print(f"  fp32 bij {t.text_match}: {ref_f} fouten · dekking {ref_d} van {int(zelfde.sum())}")
    for naam in ("int8-A", "int8-B"):
        d, f, dek = beste_drempel(sim[naam][gekozen], zelfde, max_fouten=ref_f)
        print(f"  {naam} bij zijn beste drempel {d:.4f}: {f} fouten · dekking {dek} "
              f"({dek - ref_d:+d} t.o.v. fp32)")


if __name__ == "__main__":
    main()
