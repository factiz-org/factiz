"""De minimale paren van Wikipedia (B34, PLAN #30.1b stap 3): een teruggedraaide
edit is een nepzin naast de ware zin, maar alleen de beslissing telt (de zin
die 90 dagen later nog staat), en nooit wie de edit deed.
"""

from doublecheck import minimaleparen as mp


def test_a_reverted_edit_that_changes_one_sentence_is_a_minimal_pair():
    oud = "Hiroshima was bombed on 6 August 1945 by the United States. The city was rebuilt after the war."
    nieuw = "Hiroshima was bombed on 6 August 1946 by the United States. The city was rebuilt after the war."
    assert mp.paar(oud, nieuw) == ("Hiroshima was bombed on 6 August 1945 by the United States.",
                                   "Hiroshima was bombed on 6 August 1946 by the United States.")


def test_vandalism_that_replaces_the_text_is_not_a_minimal_pair():
    oud = "Hiroshima was bombed on 6 August 1945 by the United States."
    assert mp.paar(oud, "this page is stupid lol") is None


def test_an_edit_that_changes_two_sentences_is_not_a_minimal_pair():
    oud = "Japan attacked Pearl Harbor on 7 December 1941. The attack killed 2,403 Americans."
    nieuw = "Japan attacked Pearl Harbor on 8 December 1941. The attack killed 3,000 Americans."
    assert mp.paar(oud, nieuw) is None


def test_wiki_markup_templates_and_references_are_cleaned():
    tekst = "'''Hiroshima''' was [[Atomic bombings of Hiroshima and Nagasaki|bombed]]<ref name=x>bron</ref> in {{citation needed|date=2020}} 1945."
    assert mp.schoon(tekst) == "Hiroshima was bombed in 1945."


def test_only_a_sentence_that_still_stands_after_ninety_days_counts():
    waar = "Japan attacked Pearl Harbor on 7 December 1941."
    nep = "The United States attacked Pearl Harbor on 7 December 1941."
    assert mp.beslist(waar, nep, f"Intro. {waar} More text.")
    assert not mp.beslist(waar, nep, f"Intro. {nep} More text.")
    assert not mp.beslist(waar, nep, "Intro. Something else entirely.")


def test_diff_rows_are_read_from_the_mediawiki_comparison():
    html = (
        '<tr><td class="diff-marker" data-marker="−"></td><td class="diff-deletedline diff-side-deleted"><div>'
        'Hiroshima was bombed on 6 August <del class="diffchange diffchange-inline">1945</del>.</div></td>'
        '<td class="diff-marker" data-marker="+"></td><td class="diff-addedline diff-side-added"><div>'
        'Hiroshima was bombed on 6 August <ins class="diffchange diffchange-inline">1946</ins>.</div></td></tr>'
        '<tr><td class="diff-context"><div>Unchanged line.</div></td></tr>'
    )
    assert mp.regels_uit_diff(html) == [("Hiroshima was bombed on 6 August 1945.",
                                        "Hiroshima was bombed on 6 August 1946.")]


def test_the_name_or_address_of_whoever_edited_is_never_requested():
    params = mp.revisie_params("Attack on Pearl Harbor", 50)
    velden = params["rvprop"].split("|")
    assert "user" not in velden and "userid" not in velden and "comment" not in velden
    assert params["rvtag"] == "mw-reverted"
