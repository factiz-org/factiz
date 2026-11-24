"""De feitenlaag (PLAN #30.3b, B34, B36).

Een vraag die een vastgesteld feit uit de kern is, krijgt geen rood of
omstreden oordeel als `matched`: Factiz weet dat het feit vaststaat, in plaats
van het af te leiden uit de vergelijking met een claim. Aanleiding: "Rusia se
anexionó Crimea" naast "Crimea decided to join Russia" (BENCHMARK §128), een
eufemisme dat geen model als tegenspraak ziet.

De laag kent alleen de formuleringen met `rol: laag`; de poortformuleringen
meten of hij een feit ook in nieuwe woorden en talen herkent. Herkennen gaat
met de rechter: een valse bewering die op een feit lijkt, mag nooit als feit
gelden, want dan verdwijnt een terechte ontkrachting. De gevolgtrekking zit in
`categorize` (DR4).
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache


@dataclass(frozen=True)
class Herkend:
    feit: str
    formulering: str
    gelijkenis: float
    score: float


@lru_cache(maxsize=2)
def _index(model_version: str, kern_hash: str):  # pragma: no cover - met het model
    import numpy as np

    from doublecheck.embedding import fingerprint_texts
    from doublecheck.feitenbasis import laagformuleringen, lees_kern

    paren = laagformuleringen(lees_kern())
    vingers = fingerprint_texts([t for _, t in paren], model_version)
    return paren, np.stack([fp.vector for fp in vingers])


def herken(vraag: str, fingerprint, config, scorer=None, index=None) -> Herkend | None:
    """Het vastgestelde feit dat de vraag doet, of None."""
    if not config.feiten.aan:
        return None
    if index is None:  # pragma: no cover - met het model
        from doublecheck.feitenbasis import kern_vingerafdruk

        if fingerprint.model_version != config.model_versions.text_embedding:
            raise ValueError("de vingerafdruk past niet bij de modelversie van de feitenlaag (DR6)")
        index = _index(config.model_versions.text_embedding, kern_vingerafdruk())
    paren, matrix = index
    gelijkenis = matrix @ fingerprint.vector
    beste = [int(i) for i in (-gelijkenis).argsort()[:config.rechter.diepte]
             if gelijkenis[i] >= config.thresholds.feit_vloer]
    if not beste:
        return None
    if scorer is None:  # pragma: no cover - met het model
        from doublecheck.rechter import scores

        def scorer(v, teksten):
            return scores(v, teksten, config.rechter.pad, config.rechter.model)
    uitslag = scorer(vraag, [paren[i][1] for i in beste])
    score, i = max(zip(uitslag, beste))
    if score < config.thresholds.feit_zelfde:
        return None
    return Herkend(paren[i][0], paren[i][1], float(gelijkenis[i]), float(score))


def rood(conn, claim_id: str) -> bool:
    """Draagt deze claim een rood of omstreden oordeel, zoals een lezer het
    naast de vraag zou zien (B30)?"""
    from doublecheck.feitenbasis import _KLASSE, VALS_N3
    from doublecheck.verdicts import labelklasse_in_tijd

    rijen = [tuple(r) for r in conn.execute(
        "SELECT verdict_normalized, review_date FROM factcheck WHERE claim_id = ?", (claim_id,))]
    return bool(rijen) and _KLASSE.get(labelklasse_in_tijd(rijen)[0]) in VALS_N3
