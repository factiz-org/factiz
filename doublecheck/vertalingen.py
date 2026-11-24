"""Handgemaakte vertalingen van corpusclaims (E4.S1-AC5, #14.7).

Waarom met de hand en niet machinaal: een vertaling moet *per constructie*
dezelfde bewering zijn, net als de andere transformaties in de testset. Bij
machinevertaling wordt de vertaalkwaliteit een storende factor — een gemiste
match zou dan aan de vertaler kunnen liggen in plaats van aan de resolver.
Bovendien heeft `transformers` 5.x de vertaalpipeline laten vallen, dus het
zou ook een stackwijziging vragen.

De **bronkant** is létterlijk de canonieke corpustekst; een test bewaakt dat,
zodat de fixture niet stilletjes uit de pas gaat lopen met het corpus. Dat is
geen theorie: bij de omzetting naar het CC BY-corpus verdween de helft van de
oude fixture, en het cross-linguale cijfer droeg daarna niets meer
(BENCHMARK.md §36d).

Elk paar draagt zijn eigen richting (`bron_taal` → `doel_taal`). De talen zijn
beperkt tot Germaans en Romaans, want alleen daar kan de opsteller de vertaling
verifiëren — een onopgemerkte vertaalfout corrumpeert de meting stil, en dat is
in deze etappe al twee keer duur betaald.
"""

from __future__ import annotations

import json
from pathlib import Path

VERTALINGEN_PATH = Path(__file__).parent / "vertalingen.json"


def load_translations(path: str | Path = VERTALINGEN_PATH) -> list[dict]:
    return json.loads(Path(path).read_text(encoding="utf-8"))["paren"]
