"""De automatische beoordelaar voor het duel (PLAN #32.48a; PO 2026-11-09: "om te zien of we het eens zijn, als dat zo
is, kan het voortaan automatisch"): blind, in beide volgordes, door twee beoordelaars van verschillende makers, geijkt
op de keuzes van de PO."""

from doublecheck import duelrechter as dr

KAART = {"id": "K:1", "bericht": "Train derails in Germany",
         "onthulling": {"soort": "nieuws", "door": "BBC"},
         "antwoorden": [{"wie": "Gemini", "oordeel": "klopt", "kleur": "groen", "uitleg": "Het klopt, BBC meldt het.",
                         "bronnen": [{"site": "bbc.com", "titel": "Train derails"}]},
                        {"wie": "Factiz", "oordeel": "klopt", "kleur": "groen", "uitleg": "Dit klopt [1].",
                         "bronnen": [{"site": "dw.com", "titel": "Zug entgleist"}]}]}


def test_the_judge_sees_what_the_po_saw_and_never_the_reveal():
    tekst, wie = dr.paar(KAART, eerst="Factiz")
    assert wie == {"A": "Factiz", "B": "Gemini"} and "Train derails in Germany" in tekst
    assert tekst.index("Dit klopt [1].") < tekst.index("Het klopt, BBC meldt het.") and "dw.com" in tekst
    assert "onthulling" not in tekst and "nieuws" not in tekst.split("Het bericht")[0]
    _, om = dr.paar(KAART, eerst="Gemini")
    assert om == {"A": "Gemini", "B": "Factiz"}


def test_an_answer_that_is_not_valid_json_or_not_a_valid_choice_counts_as_unsure():
    assert dr.lees('{"klopt": "A", "helpt": "B", "waarom": "x"}') == {"klopt": "A", "helpt": "B", "waarom": "x"}
    assert dr.lees('```json\n{"klopt": "beide", "helpt": "gelijk"}\n```')["klopt"] == "beide"
    assert dr.lees("geen json") == {"klopt": "weet niet", "helpt": "gelijk", "waarom": ""}
    assert dr.lees('{"klopt": "C", "helpt": "misschien"}') == {"klopt": "weet niet", "helpt": "gelijk", "waarom": ""}


def test_choices_become_names_so_both_orders_can_be_compared():
    wie = {"A": "Factiz", "B": "Gemini"}
    assert dr.namen({"klopt": "A", "helpt": "B"}, wie) == (frozenset({"Factiz"}), "Gemini")
    assert dr.namen({"klopt": "beide", "helpt": "gelijk"}, wie) == (frozenset({"Factiz", "Gemini"}), "gelijk")
    assert dr.namen({"klopt": "geen", "helpt": "A"}, wie) == (frozenset(), "Factiz")
    assert dr.namen({"klopt": "weet niet", "helpt": "A"}, wie) == (None, "Factiz")


def test_a_choice_counts_only_when_both_orders_and_both_judges_agree_otherwise_a_flag():
    f, g, beide = frozenset({"Factiz"}), frozenset({"Gemini"}), frozenset({"Factiz", "Gemini"})
    eens = {("claude", "Factiz"): (beide, "Factiz"), ("claude", "Gemini"): (beide, "Factiz"),
            ("gemini", "Factiz"): (beide, "Factiz"), ("gemini", "Gemini"): (beide, "Factiz")}
    assert dr.samen(eens) == {"klopt": beide, "helpt": "Factiz", "vlag": False}
    volgorde = {**eens, ("claude", "Gemini"): (beide, "Gemini")}  # Claude kiest steeds de eerste: gelijk
    assert dr.samen(volgorde) == {"klopt": beide, "helpt": None, "vlag": True}
    oneens = {**eens, ("gemini", "Factiz"): (g, "Gemini"), ("gemini", "Gemini"): (g, "Gemini")}
    assert dr.samen(oneens) == {"klopt": None, "helpt": None, "vlag": True}
    assert dr.samen({**eens, ("gemini", "Factiz"): (f, "Factiz"), ("gemini", "Gemini"): (f, "Factiz")})["vlag"]


def test_the_po_label_is_read_with_who_was_a():
    label = {"id": "K:1", "a": "Gemini", "klopt": "A", "helpt": "Factiz"}
    assert dr.po(label) == (frozenset({"Gemini"}), "Factiz")
    assert dr.po({**label, "klopt": "beide"})[0] == frozenset({"Factiz", "Gemini"})
    assert dr.po({**label, "klopt": "weet niet"})[0] is None


def test_the_bar_is_counted_against_the_po_per_duel():
    f, beide = frozenset({"Factiz"}), frozenset({"Factiz", "Gemini"})
    rijen = ([{"duel": "1", "po": (beide, "Gemini"), "rechter": {"klopt": beide, "helpt": "Gemini", "vlag": False}}] * 8
             + [{"duel": "1", "po": (beide, "Factiz"), "rechter": {"klopt": f, "helpt": "Gemini", "vlag": False}}]
             + [{"duel": "1", "po": (None, "gelijk"), "rechter": {"klopt": None, "helpt": None, "vlag": True}}])
    uit = dr.ijking(rijen, verwacht={"1": {"Factiz": 1, "Gemini": 8}})
    assert uit["klopt"] == {"gelijk": 8, "van": 9, "aandeel": 0.889, "gehaald": False}
    assert uit["helpt"] == {"gelijk": 8, "van": 9, "aandeel": 0.889, "gehaald": True}
    assert uit["per duel"]["1"] == {"po": {"Factiz": 1, "Gemini": 8}, "rechter": {"Factiz": 0, "Gemini": 9},
                                    "gehaald": True}
    assert uit["vlaggen"] == {"aantal": 1, "gehaald": True}
