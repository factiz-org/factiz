"""De corpusrun van de claimvarianten via de Batch API (PLAN #25.17).

Besluit van de PO (2026-10-11): alleen vertalingen, in vijf talen. Dit is
de eerste stap die echt geld van een persoonlijke sleutel uitgeeft, dus de
tests gaan vooral over wat er níét mag gebeuren: de rest indienen voordat
een proefbatch de echte kosten heeft laten zien, over het budget gaan, of
na een onderbreking dezelfde claims nog eens betalen.
"""

import json
from types import SimpleNamespace

import numpy as np
import pytest

from doublecheck import variantenbatch as vb


def _claims(n, taal="en"):
    return [(f"gfc-{i:016x}", f"Claim nummer {i} over iets", taal) for i in range(n)]


def test_the_corpus_run_translates_into_five_languages_never_the_claims_own():
    assert vb.TALEN == ("en", "pt", "es", "te", "ta")
    assert vb.doeltalen("pt") == ["en", "es", "te", "ta"]
    assert vb.doeltalen("nl") == list(vb.TALEN)
    assert vb.doeltalen(None) == list(vb.TALEN)


def test_a_request_asks_only_for_translations_with_the_chosen_model():
    verzoek = vb.verzoek("gfc-0000000000000001", "Het sneeuwt in Dubai.", "nl")
    assert verzoek["custom_id"] == "gfc-0000000000000001"
    params = verzoek["params"]
    assert params["model"] == "claude-haiku-5-5"
    assert params["output_config"]["effort"] == "low"
    schema = params["output_config"]["format"]["schema"]
    assert list(schema["properties"]) == ["vertalingen"]
    prompt = params["messages"][0]["content"]
    assert "en, pt, es, te, ta" in prompt and "Het sneeuwt in Dubai." in prompt
    assert "rewrite" not in prompt.lower()                 # geen formuleringen meer


class _NepBatches:
    def __init__(self):
        self.ingediend = []
        self.status = {}
        self.uitslagen = {}

    def create(self, requests):
        batch_id = f"msgbatch_{len(self.ingediend):03d}"
        self.ingediend.append((batch_id, list(requests)))
        self.status[batch_id] = "in_progress"
        return SimpleNamespace(id=batch_id, processing_status="in_progress")

    def retrieve(self, batch_id):
        return SimpleNamespace(id=batch_id, processing_status=self.status[batch_id])

    def results(self, batch_id):
        return iter(self.uitslagen.get(batch_id, []))


def _client():
    return SimpleNamespace(messages=SimpleNamespace(batches=_NepBatches()))


def _gelukt(claim_id, vertalingen, tokens=(200, 600), stop="end_turn"):
    inhoud = [SimpleNamespace(type="text", text=json.dumps({"vertalingen": vertalingen}))]
    bericht = SimpleNamespace(content=inhoud, stop_reason=stop,
                              usage=SimpleNamespace(input_tokens=tokens[0], output_tokens=tokens[1]))
    return SimpleNamespace(custom_id=claim_id, result=SimpleNamespace(type="succeeded", message=bericht))


def _mislukt(claim_id, soort):
    return SimpleNamespace(custom_id=claim_id, result=SimpleNamespace(type=soort))


def _lever(client, batch_id, uitslagen):
    client.messages.batches.status[batch_id] = "ended"
    client.messages.batches.uitslagen[batch_id] = uitslagen


def test_the_first_submission_is_a_small_pilot(tmp_path):
    client = _client()
    vb.dien_volgende_in(client, tmp_path, _claims(5000), budget=30.0, proefgrootte=100)
    ((_, verzoeken),) = client.messages.batches.ingediend
    assert len(verzoeken) == 100


def test_nothing_more_is_submitted_while_the_pilot_is_out(tmp_path):
    client = _client()
    claims = _claims(5000)
    vb.dien_volgende_in(client, tmp_path, claims, budget=30.0, proefgrootte=100)
    with pytest.raises(vb.Weigering, match="proefbatch"):
        vb.dien_volgende_in(client, tmp_path, claims, budget=30.0, proefgrootte=100)
    assert len(client.messages.batches.ingediend) == 1


def _proef_terug(client, tmp_path, claims, tokens):
    vb.dien_volgende_in(client, tmp_path, claims, budget=30.0, proefgrootte=100)
    batch_id, verzoeken = client.messages.batches.ingediend[0]
    _lever(client, batch_id, [
        _gelukt(v["custom_id"], [{"taal": "pt", "tekst": "Reivindicação"}], tokens=tokens)
        for v in verzoeken])
    vb.haal_op(client, tmp_path)


def test_the_rest_goes_only_if_the_measured_cost_fits_the_budget(tmp_path):
    client = _client()
    claims = _claims(5000)
    # Proefbatch: 400 in + 4.000 uit per claim kost met batchkorting
    # (0,05 + 4 x 0,25) / 1000 = $0,00102 per claim: 5.000 claims ~ $5,10.
    _proef_terug(client, tmp_path, claims, tokens=(400, 4000))
    with pytest.raises(vb.Weigering, match="budget"):
        vb.dien_volgende_in(client, tmp_path, claims, budget=5.0, proefgrootte=100)
    assert len(client.messages.batches.ingediend) == 1

    vb.dien_volgende_in(client, tmp_path, claims, budget=6.0, proefgrootte=100, portie=3000)
    _, verzoeken = client.messages.batches.ingediend[1]
    assert len(verzoeken) == 3000
    assert not {v["custom_id"] for v in verzoeken} & {c for c, _, _ in claims[:100]}


def test_an_interrupted_submission_is_never_repeated_blindly(tmp_path):
    """Viel het proces weg tussen indienen en het bewaren van het batch-id,
    dan weet niemand of die batch loopt. Opnieuw indienen zou mogelijk
    dubbel betalen; de run weigert en zegt waar te kijken."""
    client = _client()
    stand = vb.lees_stand(tmp_path)
    stand["bezig"] = {"claims": 100, "sinds": "2026-10-11T20:00:00"}
    vb.schrijf_stand(tmp_path, stand)
    with pytest.raises(vb.Weigering, match="batches.list"):
        vb.dien_volgende_in(client, tmp_path, _claims(500), budget=30.0, proefgrootte=100)
    assert client.messages.batches.ingediend == []


def test_fetched_results_become_one_line_per_claim_and_failures_return_to_the_queue(tmp_path):
    client = _client()
    claims = _claims(4, taal="nl")
    vb.dien_volgende_in(client, tmp_path, claims, budget=30.0, proefgrootte=4)
    batch_id, _ = client.messages.batches.ingediend[0]
    a, b, c, d = (cid for cid, _, _ in claims)
    _lever(client, batch_id, [
        _gelukt(a, [{"taal": "en", "tekst": "Claim number 0 about something"},
                    {"taal": "nl", "tekst": "Een claim in de eigen taal"},     # niet gevraagd
                    {"taal": "de", "tekst": "Behauptung Nummer 0"}]),          # niet gevraagd
        _gelukt(b, [], stop="refusal"),
        _mislukt(c, "errored"),
        _mislukt(d, "expired"),
    ])
    vb.haal_op(client, tmp_path)
    regels = vb.lees_regels(tmp_path)
    assert [r["claim_id"] for r in regels] == [a, b]
    assert [v["taal"] for v in regels[0]["varianten"]] == ["en"]
    assert regels[0]["model"] == "claude-haiku-5-5" and regels[0]["prompt"] == vb.PROMPTVERSIE
    assert regels[1]["geweigerd"] is True and regels[1]["varianten"] == []
    # Een tweede keer ophalen schrijft niets dubbel.
    vb.haal_op(client, tmp_path)
    assert len(vb.lees_regels(tmp_path)) == 2
    # Fout en verlopen gaan bij de volgende indiening mee, de rest niet.
    assert vb.nog_te_doen(tmp_path, claims) == [claims[2], claims[3]]


class _TellendeVingerafdruk:
    def __init__(self):
        self.aanroepen = []

    def __call__(self, teksten, versie):
        self.aanroepen.append(len(teksten))
        return [SimpleNamespace(vector=np.full(4, float(len(t)), dtype=np.float32)) for t in teksten]


def _schrijf_regels(map_, aantal, begin=0):
    with (map_ / "regels.jsonl").open("a", encoding="utf-8") as uit:
        for i in range(begin, begin + aantal):
            uit.write(json.dumps({"claim_id": f"gfc-{i:016x}", "geweigerd": False,
                                  "varianten": [{"soort": "vertaling", "taal": "en", "tekst": "x" * (i + 1)}]})
                      + "\n")


def test_embedding_resumes_where_it_stopped_and_redoes_a_short_tail(tmp_path):
    _schrijf_regels(tmp_path, 10)
    vinger = _TellendeVingerafdruk()
    vb.embed(tmp_path, "model-a", vinger, portie=4)
    assert vinger.aanroepen == [4, 4, 2]
    vb.embed(tmp_path, "model-a", vinger, portie=4)
    assert vinger.aanroepen == [4, 4, 2]                    # niets opnieuw
    _schrijf_regels(tmp_path, 3, begin=10)
    vb.embed(tmp_path, "model-a", vinger, portie=4)
    assert vinger.aanroepen == [4, 4, 2, 4, 1]              # de korte staart opnieuw, dan de rest
    ids, matrix = vb.lees_vectoren(tmp_path, "model-a")
    assert len(ids) == matrix.shape[0] == 13
    assert matrix[12, 0] == 13.0


def test_vectors_are_kept_per_model_version(tmp_path):
    """DR6: vingerafdrukken van een ander model zijn er voor deze versie niet."""
    _schrijf_regels(tmp_path, 3)
    vb.embed(tmp_path, "model-a", _TellendeVingerafdruk(), portie=4)
    ids, matrix = vb.lees_vectoren(tmp_path, "model-b")
    assert ids == [] and matrix.shape[0] == 0


def test_a_second_run_with_another_portion_size_is_refused(tmp_path):
    """Porties staan op vaste plaatsen; een andere grootte zou ze door elkaar
    halen en stil verkeerde vectoren bij verkeerde varianten zetten."""
    _schrijf_regels(tmp_path, 6)
    vb.embed(tmp_path, "model-a", _TellendeVingerafdruk(), portie=4)
    with pytest.raises(vb.Weigering):
        vb.embed(tmp_path, "model-a", _TellendeVingerafdruk(), portie=3)


def test_a_half_written_last_line_is_not_read_yet(tmp_path):
    """Ophalen schrijft terwijl embedden leest. Een regel die nog niet af is
    telt nog niet mee; anders schuift de volgorde van de varianten."""
    _schrijf_regels(tmp_path, 2)
    with (tmp_path / "regels.jsonl").open("a", encoding="utf-8") as uit:
        uit.write('{"claim_id": "gfc-half", "varianten": [{"taal": "en", "te')
    assert [r["claim_id"] for r in vb.lees_regels(tmp_path)] == [
        "gfc-0000000000000000", "gfc-0000000000000001"]


def test_variants_of_a_claim_that_left_the_index_never_count():
    """Na het opruimen (#25.19) zitten er claims in de batches die niet meer
    in de index staan. Hun varianten zouden een vraag naar een claim zonder
    bonnetje sturen."""
    varianten = [("gfc-a", "en", "x"), ("gfc-weg", "pt", "y"), ("gfc-a", "es", "z")]
    matrix = np.arange(12, dtype=np.float32).reshape(3, 4)
    over, rest = vb.alleen_bestaande(varianten, matrix, {"gfc-a", "gfc-b"})
    assert [c for c, _, _ in over] == ["gfc-a", "gfc-a"]
    assert rest.tolist() == [matrix[0].tolist(), matrix[2].tolist()]
