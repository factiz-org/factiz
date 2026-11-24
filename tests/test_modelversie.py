"""De modelversie draagt een vastgezette revisie (PLAN.md #25.14c, DR6).

Een model op Hugging Face kan onder dezelfde naam veranderen. Dan rekent de
resolver stil met andere vectoren dan de index, en dat is precies wat DR6
verbiedt. De versie wordt daarom `naam@commit+voorbewerking`, en het laden
gebruikt die commit.
"""

import pytest

from doublecheck import embedding
from doublecheck.embedding import _model_naam, _modelspec

COMMIT = "5617a9f61b028005a4858fdac845db406aefb181"


def test_a_pinned_revision_is_read_from_the_version():
    assert _modelspec(f"BAAI/bge-m3@{COMMIT}+casefold") == ("BAAI/bge-m3", COMMIT, ("casefold",))
    assert _model_naam(f"BAAI/bge-m3@{COMMIT}+casefold") == "BAAI/bge-m3"


def test_a_version_without_revision_still_reads():
    versie = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2+casefold"
    assert _modelspec(versie) == (
        "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2", None, ("casefold",))
    assert _modelspec("kaal-model-v1") == ("kaal-model-v1", None, ())


def test_an_unknown_preprocessing_step_is_refused_not_ignored():
    with pytest.raises(ValueError, match="voorbewerking"):
        _modelspec(f"BAAI/bge-m3@{COMMIT}+casefold+query-voorvoegsel")


def test_a_revision_must_be_a_full_commit_hash():
    with pytest.raises(ValueError, match="commit"):
        _modelspec("BAAI/bge-m3@main+casefold")
    with pytest.raises(ValueError, match="commit"):
        _modelspec("BAAI/bge-m3@5617a9f61b+casefold")


def test_the_loader_pins_the_revision_runs_in_float32_and_caps_the_input(monkeypatch):
    import sentence_transformers
    import torch

    gezien = {}

    class Nep:
        def __init__(self, naam, **kw):
            gezien.update(naam=naam, **kw)
            self.max_seq_length = 8192

    monkeypatch.setattr(sentence_transformers, "SentenceTransformer", Nep)
    embedding._load_model.cache_clear()
    try:
        model = embedding._load_model(f"BAAI/bge-m3@{COMMIT}+casefold")
    finally:
        embedding._load_model.cache_clear()
    assert gezien["naam"] == "BAAI/bge-m3"
    assert gezien["revision"] == COMMIT
    assert gezien["device"] == "cpu"
    assert gezien["model_kwargs"] == {"dtype": torch.float32}
    assert model.max_seq_length == 512
