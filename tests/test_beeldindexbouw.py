"""De volle beeldindex bouwen (PLAN #32.35): alleen de virale beelden met hun punten, de tekst erop en de checks per
artikel, met de versies erbij (DR6)."""

from doublecheck import beeldindexbouw as bib


def test_only_images_that_rol_v3_calls_viral_go_into_the_index():
    beelden = [{"artikel": "https://a.org/1", "beeld": "x.jpg", "pdq": ["0" * 64], "kwaliteit": 90},
               {"artikel": "https://a.org/1", "beeld": "y.jpg", "pdq": ["f" * 64], "kwaliteit": 80},
               {"artikel": "https://b.org/2", "beeld": "z.jpg", "pdq": ["a" * 64], "kwaliteit": 70}]
    rollen = [{"artikel": "https://a.org/1", "beelden": ["x.jpg", "y.jpg"], "rollen": ["viraal", "huisstijl"],
               "versie": "rol-v3"},
              {"artikel": "https://b.org/2", "beelden": ["z.jpg"], "rollen": ["viraal"], "versie": "rol-v2"}]
    uit = bib.virale(beelden, rollen)
    assert [(r["artikel"], r["beeld"]) for r in uit] == [("https://a.org/1", "x.jpg")]


def test_an_index_row_carries_the_address_the_hashes_and_where_its_points_are():
    rij = bib.indexrij({"artikel": "https://www.a.org/1/", "beeld": "x.jpg", "pdq": ["0" * 64], "kwaliteit": 90},
                       "punten/abc.npz")
    assert rij == {"adres": "a.org/1", "artikel": "https://www.a.org/1/", "beeld": "x.jpg", "pdq": ["0" * 64],
                   "kwaliteit": 90, "punten": "punten/abc.npz"}


def test_the_versions_of_the_index_are_those_the_step_checks():
    from doublecheck.config import load_config

    config = load_config()
    v = bib.versies(config)
    assert v == {"punten": config.beeldstap.punten, "vergelijking": config.beeldstap.vergelijking,
                 "rol": "rol-v3", "tekst": config.model_versions.text_embedding}


def test_an_image_harvested_twice_goes_into_the_index_once():
    b = {"artikel": "https://a.org/1", "beeld": "x.jpg", "pdq": ["0" * 64], "kwaliteit": 90}
    rollen = [{"artikel": "https://a.org/1", "beelden": ["x.jpg"], "rollen": ["viraal"], "versie": "rol-v3"}]
    assert len(bib.virale([b, dict(b)], rollen)) == 1
