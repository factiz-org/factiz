"""Hermeting van de screeningpoort op de 21.3-proefset (PLAN #25.14d, §60).

De vorige hermeting (§60) draaide met een script in de kladmap dat daarna
verdween; alleen de uitkomsten stonden in de repository. Nu is de meting een
module: dezelfde herbouw van de proefset, dezelfde grondwaarheid, en een
poortkeuze die vooraf vastligt.
"""

from dataclasses import dataclass

from doublecheck import screeningmeting as sm


@dataclass(frozen=True)
class _T:
    claim_id: str


@dataclass(frozen=True)
class _Uitslag:
    document_id: str
    beweert: tuple


def test_a_flag_counts_only_for_the_expected_claim_or_its_cluster():
    uitslagen = [
        _Uitslag("beweert-1", (_T("c1"),)),            # terecht
        _Uitslag("beweert-2", (_T("c9"),)),            # andere claim, ander cluster
        _Uitslag("beweert-3", (_T("c3b"),)),           # ander lid van hetzelfde cluster
        _Uitslag("beweert-4", ()),                     # gemist
    ]
    verwacht = {"beweert-1": "c1", "beweert-2": "c2", "beweert-3": "c3", "beweert-4": "c4"}
    cluster = {"c3": "k3", "c3b": "k3"}
    u = sm.beoordeel(uitslagen, verwacht, cluster)
    assert u.terecht == {"beweert-1", "beweert-3"}
    assert u.gemist == {"beweert-2", "beweert-4"}
    assert u.vlag_op_andere_claim == 1
    assert u.vals == 0


def test_every_flag_outside_the_claiming_documents_is_false():
    uitslagen = [_Uitslag("check-nl-1", (_T("c1"), _T("c2"))), _Uitslag("wiki-en-1", (_T("c5"),))]
    u = sm.beoordeel(uitslagen, {}, {})
    assert u.vals == 3
    assert u.vlaggen == 3


def test_the_gate_with_most_true_flags_within_the_false_flag_budget_wins_and_ties_go_strict():
    rijen = {0.72: (5, 14), 0.75: (4, 9), 0.78: (4, 6), 0.80: (3, 4)}
    assert sm.kies_poort(rijen, budget=10) == 0.78
    assert sm.kies_poort(rijen, budget=3) is None


def test_paragraph_text_is_kept_and_navigation_and_scripts_are_not():
    html = ("<html><nav><p>Menu menu menu menu menu menu menu menu menu menu</p></nav>"
            "<script>var x = 'een script dat geen tekst is maar wel lang genoeg';</script>"
            "<p>Dit is een echte alinea van een factcheck, ruim langer dan veertig tekens.</p>"
            "<p>Kort.</p></html>")
    assert sm.alineatekst(html) == "Dit is een echte alinea van een factcheck, ruim langer dan veertig tekens."
