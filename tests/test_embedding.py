import numpy as np

from doublecheck.config import load_config
from doublecheck.embedding import fingerprint_text


def test_embedding_records_model_version():
    config = load_config()

    fingerprint = fingerprint_text(
        "De zeespiegel daalt al tien jaar wereldwijd",
        model_version=config.model_versions.text_embedding,
    )

    assert fingerprint.model_version == config.model_versions.text_embedding
    assert fingerprint.vector.ndim == 1
    assert fingerprint.vector.size > 0
    assert np.isclose(np.linalg.norm(fingerprint.vector), 1.0, atol=1e-5)


def test_same_text_gives_same_fingerprint():
    config = load_config()
    versie = config.model_versions.text_embedding

    een = fingerprint_text("Goldfish have a memory span of only three seconds", versie)
    twee = fingerprint_text("Goldfish have a memory span of only three seconds", versie)

    assert np.array_equal(een.vector, twee.vector)


def test_fingerprint_vector_is_read_only():
    config = load_config()

    fingerprint = fingerprint_text("test", config.model_versions.text_embedding)

    assert not fingerprint.vector.flags.writeable


class _NepModel:
    def encode(self, teksten, **_):
        return np.ones((len(teksten), 4), dtype=np.float32) / 2


def test_bulk_embedding_runs_on_the_cpu_unless_the_graphics_chip_is_asked_for(monkeypatch):
    """B37: de grafische chip geeft dezelfde vectoren, en mag voor het bulkembedden (#32.38); de server en elk los
    bericht blijven op de processor, zoals de index gebouwd en gemeten is (§74)."""
    from doublecheck import embedding

    gevraagd = []
    monkeypatch.setattr(embedding, "_load_model", lambda versie, apparaat="cpu": gevraagd.append(apparaat) or _NepModel())
    embedding.fingerprint_texts(["Een bewering."], "nep@1")
    embedding.fingerprint_texts(["Een bewering."], "nep@1", apparaat="mps")
    embedding.fingerprint_text("Een bewering.", "nep@1")
    assert gevraagd == ["cpu", "mps", "cpu"]


def test_the_reindex_asks_the_graphics_chip_only_when_it_is_there():
    import pytest

    from doublecheck import reindex

    f = reindex.bulkfingerprinter(grafische_chip=True, beschikbaar=lambda: True)
    assert f.keywords == {"apparaat": "mps"}
    assert reindex.bulkfingerprinter(grafische_chip=False, beschikbaar=lambda: True).keywords == {"apparaat": "cpu"}
    with pytest.raises(SystemExit):
        reindex.bulkfingerprinter(grafische_chip=True, beschikbaar=lambda: False)
