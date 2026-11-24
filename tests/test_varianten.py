"""Claimvarianten aan de kant van de index (PLAN #25.17, B26).

Een frontiermodel schrijft offline, op openbare claimtekst, extra
formuleringen van een gecheckte claim: vertalingen en de vormen waarin een
post haar zou brengen. Het lokale model maakt er vingerafdrukken van. Een
gebruikersvraag gaat nooit naar een externe dienst (DR3).
"""

import json
from types import SimpleNamespace

import numpy as np
import pytest

from doublecheck import varianten as va


def _v(*xs):
    v = np.array(xs, dtype=np.float32)
    return v / np.linalg.norm(v)


def test_a_variant_that_changes_a_number_is_dropped():
    antwoord = json.dumps({
        "vertalingen": [{"taal": "en", "tekst": "20,000 corona patients to be killed"},
                        {"taal": "es", "tekst": "Matarán a 30.000 pacientes"},
                        {"taal": "fr", "tekst": ""}],
        "formuleringen": ["China wil 20.000 coronapatiënten doden", "China wil coronapatiënten doden"],
    })
    gehouden = va.lees_antwoord(antwoord, "China vraagt de rechter 20.000 coronapatiënten te doden", "nl")
    teksten = [v.tekst for v in gehouden]
    assert "20,000 corona patients to be killed" in teksten
    assert "Matarán a 30.000 pacientes" not in teksten          # ander getal
    assert "China wil coronapatiënten doden" not in teksten      # getal verdwenen
    assert "" not in teksten
    assert {v.soort for v in gehouden} == {"vertaling", "formulering"}


def test_a_variant_identical_to_the_claim_adds_nothing():
    antwoord = json.dumps({"vertalingen": [], "formuleringen": ["Het sneeuwt in Dubai.", "Het sneeuwt in Dubai"]})
    assert va.lees_antwoord(antwoord, "Het sneeuwt in Dubai.", "nl") == []


def test_the_target_languages_never_include_the_claims_own_language():
    assert "nl" not in va.doeltalen("nl")
    assert "en" in va.doeltalen("nl")
    assert len(va.doeltalen("und")) == len(va.DOELTALEN)


class _NepClient:
    def __init__(self, tekst=None, stop="end_turn"):
        self.tekst, self.stop = tekst, stop
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kw):
        self.kw = kw
        inhoud = [SimpleNamespace(type="text", text=self.tekst)] if self.tekst else []
        return SimpleNamespace(content=inhoud, stop_reason=self.stop,
                               usage=SimpleNamespace(input_tokens=100, output_tokens=50))


def test_the_request_uses_the_chosen_model_a_schema_and_low_effort():
    client = _NepClient(json.dumps({"vertalingen": [{"taal": "en", "tekst": "It is snowing in Dubai."}],
                                    "formuleringen": []}))
    uitslag = va.genereer(client, "Het sneeuwt in Dubai.", "nl")
    assert client.kw["model"] == "claude-haiku-5-5"
    assert client.kw["output_config"]["effort"] == "low"
    assert client.kw["output_config"]["format"]["type"] == "json_schema"
    assert [v.tekst for v in uitslag.varianten] == ["It is snowing in Dubai."]
    assert uitslag.geweigerd is False


def test_a_refusal_is_counted_not_hidden():
    uitslag = va.genereer(_NepClient(None, stop="refusal"), "Een claim", "nl")
    assert uitslag.geweigerd is True and uitslag.varianten == []


def test_the_query_never_finds_its_own_variants():
    # Rijen: claim A, variant van A, claim B, variant van B.
    matrix = np.vstack([_v(1, 0, 0), _v(0.99, 0.1, 0), _v(0, 1, 0), _v(0.95, 0.3, 0)])
    rij_claim = ["A", "A", "B", "B"]
    beste, sim, rij = va.beste_zonder(0, ["A"], matrix, rij_claim)
    assert beste == "B" and rij == 3                         # niet A's eigen variant op 0,99
    assert sim == pytest.approx(float(matrix[0] @ matrix[3]))


def test_the_request_path_never_loads_the_external_client():
    """DR3, B26: de resolver zelf praat nooit met een taalmodel. Wie de API
    laadt, laadt de Anthropic-client niet, ook niet indirect."""
    import subprocess
    import sys

    uit = subprocess.run(
        [sys.executable, "-c",
         "import sys, doublecheck.api; print('anthropic' in sys.modules)"],
        capture_output=True, text=True, check=True)
    assert uit.stdout.strip().splitlines()[-1] == "False"


def test_the_paraphrase_test_also_counts_per_language_of_the_query():
    """#25.17: de vijf doeltalen bevatten Telugu en Tamil, en de taalgrensparen
    van de toets zijn vooral Indiaas. Per taal van de zoekvraag zie je of de
    winst daar alleen zit."""
    from types import SimpleNamespace

    # Twee groepen: (A nl, B en) en (C te, D en). A vindt B via B's variant.
    matrix = np.vstack([_v(1, 0, 0, 0), _v(0, 1, 0, 0), _v(0, 0, 1, 0), _v(0, 0, 0, 1),
                        _v(1, 0.05, 0, 0)])                       # variant van B, dicht bij A
    rij_claim = ["A", "B", "C", "D", "B"]
    rij_tekst = ["a", "b", "c", "d", "b nl"]
    rij_taal = ["nl", "en", "te", "en", "nl"]
    claimrij = {"A": 0, "B": 1, "C": 2, "D": 3}
    drempels = SimpleNamespace(text_match=0.87, text_related=0.79)
    tel, per_soort, per_taal = va._meet_parafrasen(matrix, rij_claim, rij_tekst, rij_taal,
                                                    [{"A", "B"}, {"C", "D"}], claimrij, drempels)
    assert per_taal["nl"]["gevonden"] == 1
    assert per_taal["te"]["niets"] == 1
