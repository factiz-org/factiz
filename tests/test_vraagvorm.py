"""Vraag en bewering vinden elkaar (PLAN #25.36, stap c).

Een bewering gaat ook als vraag rond, en een vraag scoort lager tegen de
bewering die al gecheckt is ("Did Ukraine start the war versus Russia?" 0,781,
dezelfde inhoud als bewering 0,817). De regel leest een vraag daarom ook als
bewering, zonder taalmodel: het vraagteken en het vraagwoord of -partikel
eraf. Gezocht wordt met de tekst zoals hij binnenkomt én met de omgezette
tekst, per claim de hoogste gelijkenis. Twijfel versoepelt nooit: weet de regel
de taal niet zeker, dan valt alleen het vraagteken weg. De regel staat achter
`[vraagvorm] aan` en is uit tot een release (B22).
"""

import pytest

from doublecheck import vraagvorm
from doublecheck.vraagvorm import als_bewering


@pytest.mark.parametrize("vraag, bewering", [
    ("Did Ukraine start the war versus Russia?", "Ukraine start the war versus Russia"),
    ("Is the US testing biological weapons in labs in Ukraine?",
     "the US testing biological weapons in labs in Ukraine"),
    ("Is it true that vaccines cause autism in children?", "vaccines cause autism in children"),
    ("Did you know that 5G towers spread the coronavirus?", "5G towers spread the coronavirus"),
    ("Was the moon landing filmed in a studio?", "the moon landing filmed in a studio"),
    ("Does drinking hot water cure the coronavirus?", "drinking hot water cure the coronavirus"),
])
def test_a_yes_no_question_in_english_is_read_as_a_statement(vraag, bewering):
    assert als_bewering(vraag) == bewering


@pytest.mark.parametrize("vraag, bewering", [
    ("Aşılar çocuklarda otizme neden oluyor mu?", "Aşılar çocuklarda otizme neden oluyor"),
    ("क्या टीके से बच्चों में ऑटिज़्म होता है?", "टीके से बच्चों में ऑटिज़्म होता है"),
    ("هل تسبب اللقاحات التوحد عند الأطفال؟", "تسبب اللقاحات التوحد عند الأطفال"),
    ("日本は世界一の重税国ですか？", "日本は世界一の重税国です"),
    ("ワクチンで自閉症が増えるのでしょうか？", "ワクチンで自閉症が増えるの"),
    ("疫苗会导致儿童自闭症吗？", "疫苗会导致儿童自闭症"),
])
def test_the_question_word_or_particle_goes_in_the_languages_set_down_in_advance(vraag, bewering):
    """De talen uit de opzet van #25.36: Turks, Hindi, Arabisch, Japans en
    Chinees, naast het Engels."""
    assert als_bewering(vraag) == bewering


@pytest.mark.parametrize("tekst", [
    "Ukraine started the war with Russia.",
    "Vaccines cause autism",
    "日本は世界一の重税国",
    "Why is nobody talking about the vaccine injuries",
])
def test_a_statement_stays_exactly_as_it_is(tekst):
    assert als_bewering(tekst) == tekst


def test_a_question_about_what_or_why_only_loses_its_question_mark():
    """Een open vraag is geen bewering met een vraagteken; de regel herschrijft
    hem niet."""
    assert als_bewering("Why is nobody talking about the vaccine injuries?") == \
        "Why is nobody talking about the vaccine injuries"


def test_doubt_about_the_language_only_drops_the_question_mark():
    """Twijfel versoepelt nooit: zonder zekere taal blijft elk woord staan, ook
    een woord dat in een andere taal een vraagpartikel is."""
    assert als_bewering("Mi piace?") == "Mi piace"
    assert als_bewering("Does 5G cause covid?") == "Does 5G cause covid"
    assert als_bewering("¿Es verdad que mi vecino es espía?") == "Es verdad que mi vecino es espía"


def test_the_rule_never_leaves_nothing():
    """Blijft er na het weghalen niets over, dan blijft de tekst zoals hij was."""
    for tekst in ("?", "？", "  "):
        assert als_bewering(tekst) == tekst
    for tekst in ("Is?", "か？", "क्या?", "هل؟"):
        assert als_bewering(tekst).strip(), tekst


class _Kandidaat:
    def __init__(self, claim_id, similarity, via=None):
        self.claim_id, self.similarity, self.via = claim_id, similarity, via


def _zoeker(per_vector):
    def search_text(conn, fingerprint, limit=5, *, varianten=False):
        return per_vector[fingerprint.vector][:limit]
    return search_text


class _Fingerprint:
    def __init__(self, vector, model_version="m"):
        self.vector, self.model_version = vector, model_version


def test_both_searches_merge_with_the_best_similarity_per_claim(monkeypatch):
    from doublecheck.config import load_config

    config = load_config()
    config = type(config)(**{**config.__dict__, "vraagvorm": vraagvorm.VraagvormSettings(aan=True)})
    resultaten = {
        "vraag": [_Kandidaat("a", 0.78), _Kandidaat("b", 0.70)],
        "bewering": [_Kandidaat("b", 0.82), _Kandidaat("c", 0.75)],
    }
    monkeypatch.setattr(vraagvorm, "search_text", _zoeker(resultaten))
    monkeypatch.setattr(vraagvorm, "fingerprint_text", lambda tekst, versie: _Fingerprint("bewering", versie))
    uit = vraagvorm.zoek(None, config, "Did a happen?", _Fingerprint("vraag"))
    assert [(k.claim_id, k.similarity) for k in uit] == [("b", 0.82), ("a", 0.78), ("c", 0.75)]


def test_with_the_rule_off_the_search_is_exactly_the_old_one(monkeypatch):
    from doublecheck.config import load_config

    # Sinds de tussenrelease van 2026-10-16 staat de regel aan; de kaart moet
    # het dan zeggen (`test_releases`). Uit blijft hij precies de oude zoekvraag.
    config = load_config()
    config = type(config)(**{**config.__dict__, "vraagvorm": vraagvorm.VraagvormSettings(aan=False)})
    resultaten = {"vraag": [_Kandidaat("a", 0.78)]}
    monkeypatch.setattr(vraagvorm, "search_text", _zoeker(resultaten))

    def nooit(*_):
        raise AssertionError("met de regel uit wordt er niet twee keer gezocht")

    monkeypatch.setattr(vraagvorm, "fingerprint_text", nooit)
    uit = vraagvorm.zoek(None, config, "Did a happen?", _Fingerprint("vraag"))
    assert [k.claim_id for k in uit] == ["a"]


def test_a_statement_is_searched_once_even_with_the_rule_on(monkeypatch):
    from doublecheck.config import load_config

    config = load_config()
    config = type(config)(**{**config.__dict__, "vraagvorm": vraagvorm.VraagvormSettings(aan=True)})
    monkeypatch.setattr(vraagvorm, "search_text", _zoeker({"tekst": [_Kandidaat("a", 0.9)]}))

    def nooit(*_):
        raise AssertionError("een bewering hoeft geen tweede zoekvraag")

    monkeypatch.setattr(vraagvorm, "fingerprint_text", nooit)
    assert [k.claim_id for k in vraagvorm.zoek(None, config, "A happened.", _Fingerprint("tekst"))] == ["a"]


def test_resolve_and_ask_search_through_the_same_rule():
    """Eén plek: de resolver en Ask zoeken allebei via `vraagvorm.zoek`, dus de
    meting van Ask (`vraagtoets`) meet hetzelfde pad als de pagina."""
    from pathlib import Path

    wortel = Path(__file__).resolve().parent.parent / "doublecheck"
    for bestand in ("api.py", "ask.py", "terugkijk.py"):
        bron = (wortel / bestand).read_text(encoding="utf-8")
        assert "vraagvorm.zoek(" in bron, bestand
    assert "search_text(" not in (wortel / "ask.py").read_text(encoding="utf-8")


def test_all_units_of_an_article_search_through_the_rule_as_each_alone(monkeypatch):
    """#30.11: de eenheden van een artikel in één keer, met de vraagvorm per
    eenheid; per eenheid precies wat `zoek` alleen geeft."""
    from doublecheck.config import load_config

    config = load_config()
    config = type(config)(**{**config.__dict__, "vraagvorm": vraagvorm.VraagvormSettings(aan=True)})
    resultaten = {
        "kop": [_Kandidaat("k", 0.9)],
        "vraag": [_Kandidaat("a", 0.78), _Kandidaat("b", 0.70)],
        "bewering": [_Kandidaat("b", 0.82), _Kandidaat("c", 0.75)],
    }
    monkeypatch.setattr(vraagvorm, "search_text", _zoeker(resultaten))
    monkeypatch.setattr(vraagvorm, "search_texts", lambda conn, fps, limit=5, *, varianten=False: [
        resultaten[fp.vector][:limit] for fp in fps])
    monkeypatch.setattr(vraagvorm, "fingerprint_text", lambda tekst, versie: _Fingerprint("bewering", versie))
    teksten = ["Vaccines contain chips.", "Did a happen?"]
    vingers = [_Fingerprint("kop"), _Fingerprint("vraag")]
    gevraagd = []

    def vingerafdrukken(lijst, versie):
        gevraagd.append(list(lijst))
        return [_Fingerprint("bewering", versie) for _ in lijst]

    samen = vraagvorm.zoek_alle(None, config, teksten, vingers, vingerafdrukken=vingerafdrukken)
    los = [vraagvorm.zoek(None, config, t, v) for t, v in zip(teksten, vingers)]
    assert [[(k.claim_id, k.similarity) for k in lijst] for lijst in samen] == \
        [[(k.claim_id, k.similarity) for k in lijst] for lijst in los]
    assert gevraagd == [["a happen"]]
