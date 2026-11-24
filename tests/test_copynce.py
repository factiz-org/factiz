"""De matcher van CopyNCE, nagebouwd in eigen code (PLAN #32.20 V3). De gewichten staan niet in git; deze tests
draaien zonder."""

import hashlib
import io

import numpy as np
import pytest
import torch
from PIL import Image

from doublecheck import copynce as cn


def _beeld(kleur=(200, 30, 30), maat=(320, 180), modus="RGB") -> bytes:
    uit = io.BytesIO()
    Image.new(modus, maat, kleur if modus != "L" else 128).save(uit, format="PNG")
    return uit.getvalue()


def _bewaar(pad, inhoud) -> str:
    torch.save(inhoud, pad)
    return hashlib.sha256(pad.read_bytes()).hexdigest()


def _model(zaad: int) -> cn.Matcher:
    torch.manual_seed(zaad)
    return cn.Matcher().train(False)


def test_the_rebuilt_model_has_exactly_the_157_weights_of_the_released_matcher():
    sleutels = cn.Matcher().state_dict()
    assert len(sleutels) == 157
    assert tuple(sleutels["encoder.pos_embed"].shape) == (1, 197, 384)
    assert tuple(sleutels["encoder.patch_embed.proj.weight"].shape) == (384, 3, 16, 16)
    assert "encoder.blocks.7.mlp.fc2.weight" in sleutels and "encoder.blocks.8.norm1.weight" not in sleutels
    assert "fusion.blocks.3.attn.qkv.bias" in sleutels and "fusion.blocks.4.norm1.weight" not in sleutels
    assert tuple(sleutels["heads.cls_head.classifier.weight"].shape) == (1, 384)


def test_weights_with_another_fingerprint_are_never_loaded(tmp_path):
    pad = tmp_path / "w.pth.tar"
    _bewaar(pad, {"model": cn.Matcher().state_dict(), "epoch": 30})
    with pytest.raises(cn.Weigering):
        cn.laad(pad, vingerafdruk="0" * 64)


def test_weights_that_do_not_fit_exactly_are_refused(tmp_path):
    staat = cn.Matcher().state_dict()
    staat.pop("heads.cls_head.classifier.bias")
    pad = tmp_path / "w.pth.tar"
    with pytest.raises(RuntimeError):
        cn.laad(pad, vingerafdruk=_bewaar(pad, {"model": staat, "epoch": 30}))


class _Iets:
    pass


def test_a_weights_file_with_code_in_it_is_refused(tmp_path):
    pad = tmp_path / "w.pth.tar"
    with pytest.raises(cn.Weigering):
        cn.laad(pad, vingerafdruk=_bewaar(pad, {"model": cn.Matcher().state_dict(), "iets": _Iets()}))


def test_weights_saved_from_a_parallel_model_load(tmp_path):
    staat = {"module." + k: v for k, v in cn.Matcher().state_dict().items()}
    pad = tmp_path / "w.pth.tar"
    model = cn.laad(pad, vingerafdruk=_bewaar(pad, {"model": staat, "epoch": 30}))
    assert not model.training


def test_any_image_becomes_a_normalised_224_square():
    for inhoud in (_beeld(), _beeld(maat=(50, 900)), _beeld(modus="L"), _beeld(modus="RGBA", kleur=(0, 0, 0, 0))):
        x = cn.invoer(inhoud)
        assert tuple(x.shape) == (3, 224, 224) and x.dtype == torch.float32
    rood = cn.invoer(_beeld())
    assert torch.allclose(rood[:, 100, 100], torch.tensor([(200 / 255 - 0.485) / 0.229, (30 / 255 - 0.456) / 0.224,
                                                          (30 / 255 - 0.406) / 0.225]), atol=1e-4)


def test_the_score_is_between_zero_and_one_and_the_same_both_ways():
    model = _model(0)
    ta, tb = model.tokens(torch.stack([cn.invoer(_beeld()), cn.invoer(_beeld((10, 200, 90), (400, 400)))]))
    s1 = cn.scores(model, ta, tb[None])
    s2 = cn.scores(model, tb, ta[None])
    assert s1.shape == (1,) and 0.0 <= float(s1[0]) <= 1.0
    assert np.allclose(s1, s2, atol=1e-5)


def test_scores_in_batches_equal_scores_one_by_one():
    model = _model(1)
    tokens = model.tokens(torch.stack([cn.invoer(_beeld((i * 40, 90, 255 - i * 40))) for i in range(5)]))
    samen = cn.scores(model, tokens[0], tokens[1:], batch=3)
    los = np.concatenate([cn.scores(model, tokens[0], tokens[i:i + 1]) for i in range(1, 5)])
    assert np.allclose(samen, los, atol=1e-5)
