"""De formuleringen van de poort (PLAN #30.3b): per feit acht nieuwe, in woorden
en talen die de laag nooit zag; pas na lezen in de kern.
"""

from doublecheck import poortformuleringen as pf

FEIT = {"id": "apollo-11", "zin": "On 20 July 1969 Neil Armstrong walked on the Moon.",
        "formuleringen": [{"taal": "en", "tekst": "Neil Armstrong walked on the moon in 1969."},
                          {"taal": "es", "tekst": "Neil Armstrong caminó sobre la Luna en 1969."}]}


def test_the_request_shows_the_fact_and_the_wordings_to_avoid():
    v = pf.verzoek(FEIT)
    tekst = v["params"]["messages"][0]["content"]
    assert FEIT["zin"] in tekst and "Neil Armstrong caminó sobre la Luna en 1969." in tekst
    assert v["custom_id"] == "apollo-11"
    assert set(v["params"]["output_config"]["format"]["schema"]["required"]) == {s for s, _ in pf.VAKKEN}


def test_new_wordings_join_the_kern_as_gate_and_rejected_ones_stay_out():
    kern = [dict(FEIT, formuleringen=list(FEIT["formuleringen"]))]
    antwoord = {"en_1": "Neil Armstrong set foot on the Moon on 20 July 1969.", "en_2": "x", "es": "y", "pt": "z",
                "it": "a", "tr": "b", "id": "c", "ar": "d"}
    uit = pf.opnemen(kern, {"apollo-11": antwoord}, afgewezen={"apollo-11#en_2"})
    nieuw = [f for f in uit[0]["formuleringen"] if f.get("rol") == "poort"]
    assert len(nieuw) == 7 and {f["taal"] for f in nieuw} == {"en", "es", "pt", "it", "tr", "id", "ar"}
    assert not any(f["tekst"] == "x" for f in uit[0]["formuleringen"])
    assert all(f.get("rol", "laag") == "laag" for f in uit[0]["formuleringen"][:2])


def test_taking_the_same_answers_twice_adds_nothing():
    kern = [dict(FEIT, formuleringen=list(FEIT["formuleringen"]))]
    antwoord = {s: f"{s} tekst" for s, _ in pf.VAKKEN}
    eens = pf.opnemen(kern, {"apollo-11": antwoord}, afgewezen=set())
    twee = pf.opnemen(eens, {"apollo-11": antwoord}, afgewezen=set())
    assert len(twee[0]["formuleringen"]) == len(eens[0]["formuleringen"]) == 2 + len(pf.VAKKEN)
