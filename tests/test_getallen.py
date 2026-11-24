"""Scherpere getalherkenning (PLAN.md #8.1, E3.S4).

Aanleiding: `30.000` viel uiteen in `30` en `000`, waardoor een gewisselde `30`
al aanwezig leek en de tegenspraak gemist werd (benchmarkrun #5).
"""

from doublecheck.relation import contradicts, extract_numbers


def test_thousand_separator_is_one_number():
    assert extract_numbers("bekommt 30.000 Euro") == frozenset({"30000"})
    assert extract_numbers("costs 30,000 euros") == frozenset({"30000"})
    assert extract_numbers("1.234.567 mensen") == frozenset({"1234567"})


def test_decimal_separator_is_kept_as_one_number():
    assert extract_numbers("3,5 procent") == frozenset({"3.5"})
    assert extract_numbers("3.5 percent") == frozenset({"3.5"})
    assert extract_numbers("1.234,56 euro") == frozenset({"1234.56"})


def test_plain_numbers_still_work():
    assert extract_numbers("1 op 3 vluchtelingen in 2020") == frozenset(
        {"1", "3", "2020"}
    )
    assert extract_numbers("geen cijfers") == frozenset()


def test_the_leak_from_run_five_is_closed():
    """Het concrete geval dat de benchmark liet lekken."""
    claim = (
        "Eine syrische Großfamilie mit vier Frauen und 23 Kindern bekommt"
        " 30.000 Euro staatliche Unterstützung im Monat."
    )
    artefact = claim.replace("23 Kindern", "30 Kindern")

    assert contradicts(extract_numbers(artefact), frozenset(), claim) is True


def test_truncation_still_is_not_a_contradiction():
    """Een afgekapte kop heeft mínder getallen — dat blijft geen tegenspraak."""
    claim = "In 2020 kregen 30.000 mensen een boete van 95 euro"
    afgekapt = "In 2020 kregen 30.000 mensen"

    assert contradicts(extract_numbers(afgekapt), frozenset(), claim) is False


def test_same_context_different_number_is_contradiction():
    """Het lek uit run #6: de gewisselde 15 stond al in '15-jarig'."""
    claim = "Vrijspraak voor 8 migranten die 15-jarig meisje verkrachtten in Duitsland"
    artefact = claim.replace("8 migranten", "15 migranten")

    # De deelverzameling-regel ziet niets: {15} zit al in {8, 15}.
    assert extract_numbers(artefact) <= extract_numbers(claim)
    # De contextregel wél: "migranten" hoort bij 8, niet bij 15.
    assert contradicts(extract_numbers(artefact), frozenset(), claim,
                       artefact_text=artefact) is True


def test_same_context_same_number_is_no_contradiction():
    claim = "Vrijspraak voor 8 migranten in Duitsland"
    artefact = "Vrijspraak voor 8 migranten"

    assert contradicts(extract_numbers(artefact), frozenset(), claim,
                       artefact_text=artefact) is False


def test_context_rule_needs_a_shared_context_word():
    """Zonder gedeeld contextwoord doet de regel geen uitspraak."""
    claim = "In 2020 kregen 30.000 mensen een boete"
    artefact = "Er waren 30.000 deelnemers"

    # Geen gedeelde context ("mensen" vs "deelnemers"), dus geen contextconflict;
    # de deelverzameling-regel beslist dan, en die ziet 30000 in beide.
    assert contradicts(extract_numbers(artefact), frozenset(), claim,
                       artefact_text=artefact) is False


def test_context_rule_is_optional_and_backwards_compatible():
    """Zonder artefacttekst blijft het gedrag exact als voorheen."""
    claim = "De heffing is 17 procent gestegen"

    assert contradicts(frozenset({"24"}), frozenset(), claim) is True
    assert contradicts(frozenset({"17"}), frozenset(), claim) is False


def test_space_thousand_separator():
    """Frans/Zweeds gebruiken een spatie: '40 000' is één getal (PLAN.md #9.1)."""
    assert extract_numbers("construit 40 000 logements") == frozenset({"40000"})
    assert extract_numbers("123 456 789 euro") == frozenset({"123456789"})
    assert extract_numbers("1 000 mensen") == frozenset({"1000"})


def test_space_separator_does_not_merge_unrelated_numbers():
    """De valkuil: twee losse getallen naast elkaar mogen niet samensmelten."""
    # 2020 heeft vier cijfers, dus het is geen duizendtal-voorloper.
    assert extract_numbers("In 2020 300 mensen") == frozenset({"2020", "300"})
    # Groepen die geen exact drietal zijn, smelten niet samen.
    assert extract_numbers("kamer 12 45 mensen") == frozenset({"12", "45"})
    # Woorden tussen de getallen: geen scheidingsteken.
    assert extract_numbers("1 op 3 mensen") == frozenset({"1", "3"})


def test_french_dutch_thousand_pair_is_no_contradiction():
    """Het concrete geval dat 13 clusterkandidaten blokkeerde."""
    nl = "Londens burgemeester Sadiq Khan bouwt 40.000 nieuwe huizen voor moslims"
    fr = ("Sadiq Khan, le maire de Londres, construit 40 000 nouveaux logements"
          " pour les musulmans")

    assert extract_numbers(nl) == extract_numbers(fr)
    assert contradicts(extract_numbers(fr), frozenset(), nl, artefact_text=fr) is False
