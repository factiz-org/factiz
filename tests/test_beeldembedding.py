"""Een geleerde beeldembedding als vergelijking (PLAN #26.3, BENCHMARK §89).

PDQ vindt een kopie in een kader, met een band erover of 5% bijgesneden niet
terug. Een beeldembedding beschrijft wat er te zien is in plaats van de
pixels. Eerst gemeten, offline; in de resolver pas met een release (B22).
"""

import numpy as np
import pytest
from PIL import Image, ImageDraw

from doublecheck import beeldembedding as be
from doublecheck.beeldindex import _jpeg


def _in_cache() -> bool:
    try:
        from huggingface_hub import try_to_load_from_cache
        naam, _, revisie = be.BEELDMODEL.partition("@")
        return isinstance(try_to_load_from_cache(naam, "config.json", revision=revisie), str)
    except Exception:
        return False


def _foto(zaad):
    rng = np.random.default_rng(zaad)
    beeld = Image.fromarray(np.clip(rng.normal(120, 30, (300, 400, 3)), 0, 255).astype(np.uint8))
    teken = ImageDraw.Draw(beeld)
    for _ in range(25):
        x, y = rng.integers(0, 400), rng.integers(0, 300)
        teken.rectangle([x, y, x + rng.integers(20, 120), y + rng.integers(20, 120)],
                        fill=tuple(int(c) for c in rng.integers(0, 255, 3)))
    return beeld


def test_the_image_model_is_pinned_to_a_commit():
    naam, _, revisie = be.BEELDMODEL.partition("@")
    assert naam == "facebook/dinov2-small" and len(revisie) == 40


@pytest.mark.skipif(not _in_cache(), reason="beeldmodel niet gedownload op deze machine")
@pytest.mark.parametrize("pooling", be.POOLINGS)
def test_a_recompressed_copy_lands_next_to_its_original(pooling):
    """Of het model een kopie in een kader herkent, meet de kadermeting op
    echte beelden; nepbeelden zijn voor dit model allemaal "ruis met
    rechthoeken" (twee verschillende lijken 0,98 op elkaar)."""
    origineel = _foto(1)
    v = be.vectoren([origineel, _jpeg(origineel, 60)], pooling=pooling)
    assert v.shape == (2, 384)
    assert np.allclose(np.linalg.norm(v, axis=1), 1, atol=1e-4)
    assert float(v[0] @ v[1]) > 0.95
