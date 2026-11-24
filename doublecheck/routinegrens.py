"""De grens van de routine per week (PLAN #35.2).

Een verrijking (thema's, namen, vertalingen) heeft een eigen grens voor altijd, voor een ronde met de hand. Draait ze onder
`python -m doublecheck.verversen`, dan zet die twee variabelen: `FACTIZ_ROUTINE` (de uitgave) en `FACTIZ_ROUTINE_RUIMTE`
(wat er van de grens van die uitgave nog over is, in dollar). De stap toetst haar schatting dan aan die ruimte in plaats van
aan haar eigen grens, en merkt elke batch met de uitgave, zodat de routine weet wat hij kostte. Zonder de variabelen
verandert er niets.
"""

from __future__ import annotations

import os


def uitgave() -> str | None:
    """De uitgave waarvoor de routine deze stap draait, of niets bij een ronde met de hand."""
    return os.environ.get("FACTIZ_ROUTINE") or None


def ruimte() -> float:
    """Wat er van de grens van de routine nog over is; zonder getal niets, dan past er ook niets."""
    try:
        return max(0.0, float(os.environ.get("FACTIZ_ROUTINE_RUIMTE", "")))
    except ValueError:
        return 0.0


def past(schatting: float, marge: float = 1.0) -> bool:
    """Of een schatting (met de marge van de stap) nog binnen de ruimte van de routine valt."""
    return schatting * marge <= ruimte()


def merk(rij: dict) -> dict:
    """Een batch met de uitgave van de routine erbij, als die draait."""
    return {**rij, "routine": uitgave()} if uitgave() else rij


def kosten(batches: list[dict], release: str) -> tuple[float, int]:
    """Wat de batches van deze uitgave kostten (de schatting zolang een batch loopt), en hoeveel er nog lopen."""
    eigen = [b for b in batches if b.get("routine") == release]
    return (round(sum(b["werkelijk"] if b.get("werkelijk") is not None else b.get("schatting", 0.0) for b in eigen), 4),
            sum(b.get("werkelijk") is None for b in eigen))
