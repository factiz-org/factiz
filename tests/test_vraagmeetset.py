"""De meetset van #25.36: vraag en bewering, beide kanten op.

Vooraf vastgelegd in PLAN #25.36: per taal en per richting 50 claims met een
toegelaten check (seed 2536), in twee helften (een ontwikkelhelft en een
toetshelft); de tegenvorm als post, met een eigen opdracht los van die van de
varianten; en de harde regels van de Batch API: eerst een proefbatch, binnen
het budget, nooit blind opnieuw.
"""

import json
from types import SimpleNamespace

import pytest

from doublecheck import vraagmeetset as vm
from doublecheck.storage import connect, init_schema


@pytest.fixture
def conn(tmp_path):
    conn = connect(tmp_path / "t.db")
    init_schema(conn)
    rijen = []
    for taal in ("en", "nl", "si"):
        for i in range(70):
            vraag = i % 2 == 0
            tekst = f"{taal} claim {i} about the harbour{'?' if vraag else '.'}"
            rijen.append((f"c-{taal}-{i:03d}", tekst, taal))
    for claim_id, tekst, taal in rijen:
        conn.execute("INSERT INTO claim (claim_id, canonical_text, language) VALUES (?, ?, ?)",
                     (claim_id, tekst, taal))
        conn.execute("INSERT INTO factcheck (claim_id, publisher, verdict_normalized, verdict_original, url,"
                     " review_date, language, source) VALUES (?, 'Krant', 'onwaar', 'False', ?, '2024-01-01', ?,"
                     " 'feed')", (claim_id, f"https://krant.example/{claim_id}", taal))
    conn.commit()
    return conn


def test_the_selection_is_reproducible_and_split_in_two_halves(conn):
    eerste = vm.kies(conn, talen=("en", "nl", "si"), per_taal=20)
    assert eerste == vm.kies(conn, talen=("en", "nl", "si"), per_taal=20)
    for taal in ("en", "nl", "si"):
        for richting in ("vraag", "bewering"):
            deel = [i for i in eerste if i["taal"] == taal and i["richting"] == richting]
            assert len(deel) == 20, (taal, richting)
            assert sorted(i["helft"] for i in deel) == ["ontwikkel"] * 10 + ["toets"] * 10
    # De richting volgt de claim: een bewering krijgt een vraag als tegenvorm,
    # een vraag een bewering.
    for item in eerste:
        assert item["richting"] == ("bewering" if item["claim"].endswith("?") else "vraag")
        assert item["publisher"] and item["url"], "CC BY: de bron reist mee"


def test_a_claim_outside_the_index_is_never_chosen(conn, monkeypatch):
    monkeypatch.setattr(vm, "buiten_index", lambda c: frozenset({"c-en-000", "c-en-001"}))
    gekozen = {i["claim_id"] for i in vm.kies(conn, talen=("en",), per_taal=35)}
    assert not gekozen & {"c-en-000", "c-en-001"}


def test_the_request_is_its_own_and_never_asks_for_a_verdict():
    from doublecheck.varianten import _SYSTEEM

    item = {"id": "vraag-c1", "claim": "The harbour closed in 2020.", "taal": "en", "richting": "vraag"}
    verzoek = vm.verzoek(item)
    assert verzoek["custom_id"] == "vraag-c1"
    assert verzoek["params"]["system"] != _SYSTEEM, "de meetset mag niet uit de opdracht van de varianten komen"
    tekst = verzoek["params"]["messages"][0]["content"]
    assert "yes-no question" in tekst and "The harbour closed in 2020." in tekst
    assert "never judge" in verzoek["params"]["system"]
    bewering = vm.verzoek({**item, "id": "bewering-c2", "richting": "bewering"})
    assert "not a question" in bewering["params"]["messages"][0]["content"]
    # v2: een claim die zelf een vraag is, wordt gesteld, nooit beantwoord of ontkend.
    assert "never answer it and never deny it" in bewering["params"]["messages"][0]["content"]


class _NepBatches:
    def __init__(self):
        self.ingediend, self.status, self.uitslagen = [], {}, {}

    def create(self, requests):
        batch_id = f"msgbatch_{len(self.ingediend):03d}"
        self.ingediend.append((batch_id, list(requests)))
        self.status[batch_id] = "in_progress"
        return SimpleNamespace(id=batch_id, processing_status="in_progress")

    def retrieve(self, batch_id):
        return SimpleNamespace(id=batch_id, processing_status=self.status[batch_id])

    def results(self, batch_id):
        return iter(self.uitslagen.get(batch_id, []))


def _uitslag(item_id, post, tokens=(300, 60), stop="end_turn"):
    inhoud = [SimpleNamespace(type="text", text=json.dumps({"post": post}))]
    bericht = SimpleNamespace(content=inhoud, stop_reason=stop,
                              usage=SimpleNamespace(input_tokens=tokens[0], output_tokens=tokens[1]))
    return SimpleNamespace(custom_id=item_id, result=SimpleNamespace(type="succeeded", message=bericht))


def test_first_a_trial_batch_then_only_within_the_budget(conn, tmp_path):
    items = vm.kies(conn, talen=("en", "nl", "si"), per_taal=20)
    batches = _NepBatches()
    client = SimpleNamespace(messages=SimpleNamespace(batches=batches))
    map_ = tmp_path / "meetset"
    eerste = vm.dien_volgende_in(client, map_, items, budget=1.0)
    assert len(batches.ingediend[0][1]) == vm.PROEFGROOTTE
    # De proef ziet elke taal en beide richtingen.
    proef = {v["custom_id"] for v in batches.ingediend[0][1]}
    gezien = {(i["taal"], i["richting"]) for i in items if i["id"] in proef}
    assert gezien == {(t, r) for t in ("en", "nl", "si") for r in ("vraag", "bewering")}
    with pytest.raises(vm.Weigering, match="proefbatch"):
        vm.dien_volgende_in(client, map_, items, budget=1.0)
    batches.status[eerste] = "ended"
    batches.uitslagen[eerste] = [_uitslag(v["custom_id"], "Is it true the harbour closed?")
                                 for v in batches.ingediend[0][1]]
    vm.haal_op(client, map_)
    with pytest.raises(vm.Weigering, match="budget"):
        vm.dien_volgende_in(client, map_, items, budget=0.0000001)
    tweede = vm.dien_volgende_in(client, map_, items, budget=1.0)
    assert tweede and len(batches.ingediend[1][1]) == len(items) - vm.PROEFGROOTTE


def test_a_refused_or_unreadable_answer_gets_no_post(conn, tmp_path):
    items = vm.kies(conn, talen=("en",), per_taal=2)
    batches = _NepBatches()
    client = SimpleNamespace(messages=SimpleNamespace(batches=batches))
    map_ = tmp_path / "meetset"
    batch = vm.dien_volgende_in(client, map_, items, budget=1.0)
    ids = [v["custom_id"] for v in batches.ingediend[0][1]]
    kapot = SimpleNamespace(content=[SimpleNamespace(type="text", text="geen json")], stop_reason="end_turn",
                            usage=SimpleNamespace(input_tokens=10, output_tokens=5))
    batches.status[batch] = "ended"
    batches.uitslagen[batch] = [_uitslag(ids[0], "", stop="refusal"),
                                SimpleNamespace(custom_id=ids[1],
                                                result=SimpleNamespace(type="succeeded", message=kapot))]
    vm.haal_op(client, map_)
    assert all(r["post"] is None for r in vm.lees_regels(map_))


def test_the_written_set_carries_its_provenance_and_room_for_the_read_test(conn, tmp_path):
    items = vm.kies(conn, talen=("en",), per_taal=2)
    regels = [{"id": i["id"], "post": f"post {n}", "geweigerd": False, "onleesbaar": False}
              for n, i in enumerate(items)]
    uit = vm.meetset(items, regels)
    assert "CC BY" in uit["_meta"] and "bewerk" in uit["_meta"].lower()
    assert all(p["publisher"] and p["url"] for p in uit["paren"])
    assert all(p["lezing"] is None for p in uit["paren"]), "de leesproef vult dit, niet de code"
