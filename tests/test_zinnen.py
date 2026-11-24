"""De bewering uit een artikel (#30.11): een tekst in eenheden."""

from doublecheck.zinnen import MAX_ZINNEN, eenheden, zinnen


def test_a_sentence_keeps_its_end_so_a_question_stays_a_question():
    assert zinnen("Is the earth flat? Scientists disagree with that.") == [
        "Is the earth flat?", "Scientists disagree with that."]


def test_a_decimal_point_or_an_abbreviation_inside_a_sentence_does_not_split_it():
    assert zinnen("The price rose 3.5 percent in a year.") == ["The price rose 3.5 percent in a year."]


def test_scripts_with_their_own_sentence_end_split_without_a_space():
    assert zinnen("地球是平的。疫苗导致自闭症。") == ["地球是平的。", "疫苗导致自闭症。"]
    assert zinnen("पृथ्वी चपटी है। टीके से ऑटिज़्म होता है।") == ["पृथ्वी चपटी है।", "टीके से ऑटिज़्म होता है।"]
    assert zinnen("هل الأرض مسطحة؟ لا يوجد دليل") == ["هل الأرض مسطحة؟", "لا يوجد دليل"]


def test_a_line_break_ends_a_headline():
    assert zinnen("Breaking: vaccines contain chips\nThe claim spread on Telegram.") == [
        "Breaking: vaccines contain chips", "The claim spread on Telegram."]


def test_one_sentence_is_searched_as_it_came_in():
    assert eenheden("Vaccines contain microchips.") == ["Vaccines contain microchips."]
    # Eén zin die meetelt, de rest te kort: het pad van nu.
    assert eenheden("Wow! Vaccines contain microchips.") == ["Wow! Vaccines contain microchips."]


def test_an_article_is_searched_whole_and_per_sentence():
    tekst = "Vaccines contain microchips\nThe chips track every citizen. Officials denied it."
    assert eenheden(tekst) == [tekst, "Vaccines contain microchips", "The chips track every citizen.",
                               "Officials denied it."]


def test_at_most_the_first_twelve_sentences_count():
    tekst = " ".join(f"This is sentence number {i} here." for i in range(20))
    uit = eenheden(tekst)
    assert uit[0] == tekst and len(uit) == 1 + MAX_ZINNEN
    assert uit[-1] == f"This is sentence number {MAX_ZINNEN - 1} here."


def test_a_short_chinese_sentence_counts_like_the_same_sentence_in_english():
    tekst = "疫苗导致自闭症。卫生部否认了这一说法。"
    assert eenheden(tekst) == [tekst, "疫苗导致自闭症。", "卫生部否认了这一说法。"]
