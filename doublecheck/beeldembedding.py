"""Een geleerde beeldembedding als vergelijking (PLAN.md #26.3).

PDQ is een hash over de pixels van het hele beeld: een kader, een band of 5%
bijsnijden verschuift hem te ver (BENCHMARK §89). Een beeldembedding
beschrijft wat er te zien is. DINOv2-small (Apache 2.0, 22 miljoen
parameters, open gewichten) draait lokaal, op een vastgezette revisie (DR6),
uitsluitend in het geheugen (DR3).

Voorbewerking vastgelegd vóór de meting: de verhouding blijft, de kortste
zijde wordt 224 pixels (bicubisch, zoals het model), beide zijden afgerond op
een veelvoud van 14 (de patchmaat), en er wordt níét in het midden
bijgesneden, want dat zou bij een hoog screenshot juist het kader wegknippen
en de meting vertekenen. Schalen en normaliseren met de waarden uit de
configuratie van het model; zelf gedaan, zodat er geen extra pakket nodig is
en de keuze zichtbaar blijft. Twee vectoren, allebei vóór de meting gekozen:
het CLS-token (wat er te zien is) en het gemiddelde over de beeldvlakjes (meer
van dít beeld); genormaliseerd. Nepbeelden lieten zien waarom: twee
verschillende lijken voor het CLS-token 0,98 op elkaar.

Offline meetgereedschap; in de resolver pas met een release (B22), en dan uit
de config.
"""

from __future__ import annotations

from functools import lru_cache

import numpy as np

BEELDMODEL = "facebook/dinov2-small@ed25f3a31f01632728cabb09d1542f84ab7b0056"
POOLINGS = ("cls", "vlakjes")
_KORTSTE_ZIJDE = 224


_GEMIDDELDE = np.array([0.485, 0.456, 0.406], dtype=np.float32)   # preprocessor_config.json
_SPREIDING = np.array([0.229, 0.224, 0.225], dtype=np.float32)
_PATCH = 14


@lru_cache(maxsize=1)
def _laad(versie: str):
    from transformers import AutoModel

    naam, _, revisie = versie.partition("@")
    model = AutoModel.from_pretrained(naam, revision=revisie or None)
    model.eval()
    return model


def _voorbewerk(beeld) -> np.ndarray:
    from PIL import Image

    b, h = beeld.size
    schaal = _KORTSTE_ZIJDE / min(b, h)
    nb = max(_PATCH, int(round(b * schaal)) // _PATCH * _PATCH)
    nh = max(_PATCH, int(round(h * schaal)) // _PATCH * _PATCH)
    pixels = np.asarray(beeld.resize((nb, nh), Image.BICUBIC), dtype=np.float32) / 255.0
    return ((pixels - _GEMIDDELDE) / _SPREIDING).transpose(2, 0, 1)[None]


def vectoren(beelden, versie: str = BEELDMODEL, *, pooling: str = "cls") -> np.ndarray:
    """Eén genormaliseerde vector per beeld, beeld voor beeld (de maten
    verschillen, want de verhouding blijft)."""
    return alle_vectoren(beelden, versie)[pooling]


def alle_vectoren(beelden, versie: str = BEELDMODEL) -> dict[str, np.ndarray]:
    """Beide vectoren uit één doorgang van het model."""
    import torch

    from doublecheck.image_fingerprint import as_image

    model = _laad(versie)
    uit: dict[str, list] = {p: [] for p in POOLINGS}
    with torch.no_grad():
        for beeld in beelden:
            invoer = torch.from_numpy(_voorbewerk(as_image(beeld).convert("RGB")))
            toestand = model(pixel_values=invoer).last_hidden_state[0]
            for pooling, v in (("cls", toestand[0]), ("vlakjes", toestand[1:].mean(dim=0))):
                v = v.float().numpy()
                uit[pooling].append(v / np.linalg.norm(v))
    return {p: (np.vstack(v) if v else np.empty((0, 384), dtype=np.float32)) for p, v in uit.items()}
