"""Draaibare conformantietest voor het resolverprotocol *(PROTOCOL.md §8)*.

Los te gebruiken van welke implementatie dan ook: `python -m conformance <url>`.
Dit pakket importeert met opzet niets uit `doublecheck` — een suite die de
implementatie kent, toetst zichzelf.

Licentie: MIT (zie `conformance/LICENSE`), bewust losser dan de AGPL van de
rest van de repo *(B20)*: een conformantieclaim moet goedkoper te verifiëren
zijn dan te betwisten, dus elke implementatie — ook gesloten — mag deze suite
draaien, inbedden en porten.
"""

from conformance.suite import (
    BEPERKINGEN,
    GEFAALD,
    GESLAAGD,
    NIET_WAARGENOMEN,
    Proef,
    Rapport,
    Uitslag,
    controleer_resolver,
)

__all__ = [
    "BEPERKINGEN",
    "GEFAALD",
    "GESLAAGD",
    "NIET_WAARGENOMEN",
    "Proef",
    "Rapport",
    "Uitslag",
    "controleer_resolver",
]
