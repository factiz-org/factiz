import pytest

from doublecheck.config import ConfigError, load_config


def test_config_exposes_thresholds_and_model_version():
    config = load_config()

    assert 0.0 < config.thresholds.text_related < config.thresholds.text_match <= 1.0
    assert config.thresholds.image_same >= 0
    assert config.model_versions.text_embedding
    assert config.model_versions.image_hash


def test_incomplete_config_refuses_to_load(tmp_path):
    zonder_matchdrempel = tmp_path / "config.toml"
    zonder_matchdrempel.write_text(
        "[thresholds]\n"
        "text_related = 0.70\n"
        "image_same = 10\n"
        "\n"
        "[model_versions]\n"
        'text_embedding = "x"\n'
        'image_hash = "y"\n',
        encoding="utf-8",
    )

    with pytest.raises(ConfigError):
        load_config(zonder_matchdrempel)


def test_config_exposes_ocr_settings():
    config = load_config()

    assert "nld" in config.ocr.languages
    assert config.ocr.min_chars > 0


def _zonder_rechter() -> str:
    """`config.toml` zonder rechter en feitenlaag: hun secties en drempels
    eruit, zodat een test ze zelf kan zetten (in productie staan ze aan)."""
    import re
    from pathlib import Path

    tekst = Path("config.toml").read_text(encoding="utf-8")
    tekst = re.sub(r"^\[(?:rechter|feiten)\]\n(?:(?!^\[).*\n)*", "", tekst, flags=re.M)
    return re.sub(r"^(?:rechter|feit)_\w+ = .*\n", "", tekst, flags=re.M)


def _met(tmp_path, extra: str):
    pad = tmp_path / "config.toml"
    pad.write_text(_zonder_rechter() + "\n" + extra, encoding="utf-8")
    return pad


def test_the_judge_is_off_unless_switched_on(tmp_path):
    assert load_config(_met(tmp_path, "")).rechter.aan is False


def test_the_judge_cannot_be_switched_on_without_its_thresholds(tmp_path):
    with pytest.raises(ConfigError):
        load_config(_met(tmp_path, '[rechter]\naan = true\nmodel = "rechter-d@abc"\npad = "x"\n'))


def test_the_judge_reads_its_model_depth_and_thresholds(tmp_path):
    pad = tmp_path / "config.toml"
    tekst = _zonder_rechter().replace(
        "[thresholds]\n", "[thresholds]\nrechter_zelfde = 0.996\nrechter_vloer = 0.79\n", 1)
    pad.write_text(tekst + '\n[rechter]\naan = true\nmodel = "rechter-d@abc"\npad = "data/x"\ndiepte = 5\n',
                   encoding="utf-8")
    config = load_config(pad)
    assert config.rechter.aan and config.rechter.model == "rechter-d@abc" and config.rechter.diepte == 5
    assert config.thresholds.rechter_zelfde == 0.996 and config.thresholds.rechter_vloer == 0.79


def test_the_fact_layer_is_off_unless_switched_on(tmp_path):
    assert load_config(_met(tmp_path, "")).feiten.aan is False


def test_the_fact_layer_cannot_be_switched_on_without_its_thresholds_or_without_the_judge(tmp_path):
    with pytest.raises(ConfigError):
        load_config(_met(tmp_path, "[feiten]\naan = true\n"))


def test_an_article_is_searched_whole_unless_switched_on(tmp_path):
    assert load_config(_met(tmp_path, "")).artikel.per_zin is False
    assert load_config(_met(tmp_path, "[artikel]\nper_zin = true\n")).artikel.per_zin is True


def test_the_search_step_and_the_model_that_plans_the_searches_are_read_from_the_file(tmp_path):
    """#32.40, #32.41: `speuren` en `speurvraag_model` staan in `[berichtcontrole]`; de lader las ze eerst niet, en dan
    weigert `lezer-v9` stil met een leeg model."""
    from pathlib import Path

    regels = [r for r in Path("config.toml").read_text(encoding="utf-8").split("\n")
              if not r.startswith(("speuren =", "speurvraag_model ="))]
    tekst = "\n".join(regels).replace(
        "[berichtcontrole]\n", '[berichtcontrole]\nspeuren = true\nspeurvraag_model = "claude-haiku-5-5"\n', 1)
    pad = tmp_path / "config.toml"
    pad.write_text(tekst, encoding="utf-8")
    controle = load_config(pad).berichtcontrole
    assert controle.speuren is True and controle.speurvraag_model == "claude-haiku-5-5"
