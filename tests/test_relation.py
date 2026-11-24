from doublecheck.relation import contradicts, extract_negations, extract_numbers


def test_extract_numbers_finds_digit_runs():
    assert extract_numbers("1 op 3 vluchtelingen in 2020") == frozenset({"1", "3", "2020"})
    assert extract_numbers("geen cijfers hier") == frozenset()


def test_extract_negations_respects_word_boundaries():
    assert extract_negations("Dit is niet waar") == frozenset({"niet"})
    assert extract_negations("This isn't true") == frozenset({"n't"})
    # "notitie" en "niets" bevatten negatietokens als substring, maar zijn er geen.
    assert extract_negations("een notitie over niets") == frozenset()
    assert extract_negations("De zeespiegel daalt") == frozenset()


def test_number_conflict_is_contradiction():
    claim = "De heffing is 17 procent gestegen sinds 2015"

    # Artefact beweert een getal dat de claim niet bevat → tegenspraak.
    assert contradicts(frozenset({"24", "2015"}), frozenset(), claim) is True
    # Zelfde getallen → geen tegenspraak.
    assert contradicts(frozenset({"17", "2015"}), frozenset(), claim) is False
    # Artefact-getallen zijn een deelverzameling (afgekapte kop) → geen tegenspraak.
    assert contradicts(frozenset({"17"}), frozenset(), claim) is False
    # Eén van beide kanten heeft geen getallen → v0 doet geen uitspraak.
    assert contradicts(frozenset(), frozenset(), claim) is False
    assert contradicts(frozenset({"24"}), frozenset(), "hier staan louter woorden") is False


def test_negation_flip_is_contradiction():
    # Artefact ontkent, claim niet → tegenspraak.
    assert contradicts(frozenset(), frozenset({"niet"}), "Minister Jansen is afgetreden") is True
    # Claim ontkent, artefact niet → ook tegenspraak.
    assert contradicts(frozenset(), frozenset(), "Minister Jansen is niet afgetreden") is True
    # Beide ontkennen → zelfde kant van de bewering, geen flip.
    assert contradicts(frozenset(), frozenset({"nooit"}), "Dat is niet gebeurd") is False
    # Geen van beide ontkent → geen tegenspraak.
    assert contradicts(frozenset(), frozenset(), "Minister Jansen is afgetreden") is False
