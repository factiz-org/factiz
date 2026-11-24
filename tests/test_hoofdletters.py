"""Hoofdletters in normaal schrift (PLAN #34.2ae, SPECS E9.S15): een tekst in hoofdletters krijgt één keer normaal schrift
van een taalmodel, alleen als er niets anders verandert dan hoofd- en kleine letters; de bewering blijft het citaat, een
vertaling staat in normaal schrift; en pas na een leesproef van 100 in de uitgave."""

import json
import sqlite3

import pytest
from starlette.testclient import TestClient

from doublecheck import hoofdletters as hl
from doublecheck import publiceren as pb
from factiz_site import app as fa
from tests.test_publiceren import REGISTER, _check, _claim, _lab

WHO = "WHO CONDEMNS LOCKDOWN: IT DOESN'T SAVE LIVES AND MAKES THE POOR MUCH POORER"
WHO_NORMAAL = "WHO condemns lockdown: it doesn't save lives and makes the poor much poorer"


# --- wat in hoofdletters is (AC1) ------------------------------------------------------------------------------------

@pytest.mark.parametrize("tekst,ja", [
    (WHO, True), ("OMS CONDENA O LOCKDOWN: NÃO SALVA VIDAS", True), (WHO_NORMAAL, False),
    ("WHO UN EU", False),                                  # te kort om iets te zeggen
    ("यूक्रेन में गुप्त जैविक प्रयोगशालाएं हैं", False),        # een schrift zonder hoofdletters
    ("O ATOR MARCELO MADUREIRA PUBLICOU O QUE SEGUE SOBRE O LULA. Muita gente", True),
    ("The WHO and the UN say the US and the EU agree", False), ("", False),
])
def test_a_text_is_in_capitals_when_four_in_five_of_its_cased_letters_are(tekst, ja):
    assert hl.in_hoofdletters(tekst) is ja


# --- alleen hoofd- en kleine letters veranderen (AC2) ----------------------------------------------------------------

@pytest.mark.parametrize("nieuw,mag", [
    (WHO_NORMAAL, True), ("WHO  condemns lockdown: it doesn't save lives and makes the poor much poorer ", True),
    ("WHO condemns the lockdown: it doesn't save lives and makes the poor much poorer", False),    # een woord erbij
    ("WHO condemns lockdown; it doesn't save lives and makes the poor much poorer", False),       # een leesteken anders
    ("WHO condemns lockdown: it doesnt save lives and makes the poor much poorer", False),        # een teken weg
    ("Who condemns lockdown: it doesn't save lives and makes the poor much poorer", True),        # alleen letters: de leesproef ziet dit
    ("", False),
])
def test_only_upper_and_lower_case_may_change(nieuw, mag):
    assert hl.alleen_hoofdletters(WHO, nieuw) is mag


def test_an_answer_counts_only_if_it_changes_case_and_nothing_else():
    originelen = [WHO, "STF CRIA CAMPOS DE CONCENTRAÇÃO", "GARIMPEIROS FOGEM DE TERRAS INDÍGENAS"]
    antwoord = json.dumps({"antwoorden": [
        {"nr": 1, "tekst": WHO_NORMAAL},
        {"nr": 2, "tekst": "O STF cria campos de concentração"},              # een woord erbij: weg
        {"nr": 3, "tekst": "GARIMPEIROS FOGEM DE TERRAS INDÍGENAS"},           # nog steeds hoofdletters: weg
    ]})
    assert hl.lees_letters(antwoord, originelen) == [WHO_NORMAAL, None, None]
    dubbel = json.dumps({"antwoorden": [{"nr": 1, "tekst": WHO_NORMAAL}, {"nr": 1, "tekst": WHO_NORMAAL}]})
    assert hl.lees_letters(dubbel, originelen) == [None, None, None]
    assert hl.lees_letters("geen json", originelen) == [None, None, None]


def test_the_question_sends_each_text_once_with_its_number_and_no_other_data():
    verzoek = hl.letterverzoek([WHO, "STF CRIA CAMPOS"])
    tekst = verzoek["messages"][0]["content"][0]["text"]
    assert tekst == f"1. {WHO}\n2. STF CRIA CAMPOS"
    assert "acronym" in verzoek["system"].lower() and "nothing else" in verzoek["system"].lower()
    assert verzoek["output_config"]["format"]["type"] == "json_schema"


# --- de leesproef en de poort (AC5) ----------------------------------------------------------------------------------

def _antwoorden(n=150):
    return [{"pagina": f"{i:016x}", "taal": "", "was": WHO, "tekst": WHO_NORMAAL, "versie": hl.VERSIE} for i in range(n)]


def _labels(tmp_path, proef, waarden):
    pad = tmp_path / "labels.json"
    pad.write_text(json.dumps({"labels": dict(zip(proef, waarden))}), encoding="utf-8")
    return pad


def test_the_reading_sample_is_a_hundred_and_always_the_same():
    a = _antwoorden()
    assert hl.leesproef(a) == hl.leesproef(list(reversed(a))) and len(hl.leesproef(a)) == 100


@pytest.mark.parametrize("waarden,open_", [
    (["goed"] * 100, True), (["goed"] * 95 + ["klein"] * 5, True), (["goed"] * 94 + ["klein"] * 6, False),
    (["goed"] * 99 + ["fout"], False), (["goed"] * 99 + ["twijfel"], False), (["goed"] * 99, False),
])
def test_the_gate_opens_only_without_a_reading_error_and_at_most_five_small_ones(tmp_path, waarden, open_):
    a = _antwoorden()
    proef = [hl.sleutel(x) for x in hl.leesproef(a)]
    assert hl.poort(a, _labels(tmp_path, proef, waarden))[0] is open_


def test_without_an_open_gate_nothing_goes_into_the_release(tmp_path):
    a = _antwoorden()
    assert hl.geldig(a, tmp_path / "bestaat-niet.json") == ({}, "nog niets gelezen")
    proef = [hl.sleutel(x) for x in hl.leesproef(a)]
    geldig, _ = hl.geldig(a, _labels(tmp_path, proef, ["goed"] * 100))
    assert len(geldig) == 150 and geldig[(f"{0:016x}", "")] == {"was": WHO, "tekst": WHO_NORMAAL}


# --- in de uitgave en op de site (AC3, AC4) --------------------------------------------------------------------------

@pytest.fixture(scope="module")
def uitgave(tmp_path_factory):
    map_ = tmp_path_factory.mktemp("hoofdletters")
    lab = _lab(map_)
    nummers = {}
    for i, (k, tekst, taal) in enumerate([("who", WHO, "en"), ("oms", "OMS CONDENA O LOCKDOWN: NÃO SALVA VIDAS", "pt"),
                                          ("gewoon", "The vaccine causes autism", "en")], start=1):
        c = _claim(lab, i, tekst, taal=taal)
        _check(lab, c, f"https://snopes.com/{k}/", taal=taal)
        nummers[k] = pb.nummer(c)
    lab.commit()
    vertalingen = {"nl": {nummers["oms"]: "WHO VEROORDEELT DE LOCKDOWN: HET REDT GEEN LEVENS"},
                   "en": {nummers["oms"]: "WHO CONDEMNS THE LOCKDOWN: IT DOES NOT SAVE LIVES"}}
    letters = {(nummers["who"], ""): {"was": WHO, "tekst": WHO_NORMAAL},
               (nummers["oms"], "nl"): {"was": "WHO VEROORDEELT DE LOCKDOWN: HET REDT GEEN LEVENS",
                                        "tekst": "WHO veroordeelt de lockdown: het redt geen levens"},
               (nummers["oms"], "en"): {"was": "WHO CONDEMNS THE LOCKDOWN: IT DOES NOT SAVE LIVES",
                                        "tekst": "WHO condemns the lockdown: it does not save lives, says Bolsonaro"},  # meer dan letters
               (nummers["gewoon"], ""): {"was": "THE VACCINE CAUSES AUTISM", "tekst": "The vaccine causes autism"}}  # oud
    m = pb.bouw(lab, map_ / "uit", register=REGISTER, vaag=frozenset(), datum="2026-11-13", vertalingen=vertalingen,
                vertaalmaker="proef", hoofdletters=letters)
    return m, nummers


def test_the_claim_stays_the_quote_and_its_normal_writing_stands_beside_it(uitgave):
    m, nr = uitgave
    db = sqlite3.connect(m["bestand"])
    assert db.execute("SELECT bewering FROM pagina WHERE nummer = ?", (nr["who"],)).fetchone()[0] == WHO
    assert dict(db.execute("SELECT pagina, tekst FROM bewering_normaal")) == {nr["who"]: WHO_NORMAAL}
    # een vertaling is tekst van Factiz: zelf in normaal schrift; wat meer dan letters verandert, blijft zoals het was
    vertaling = dict(db.execute("SELECT taal, tekst FROM vertaling WHERE pagina = ?", (nr["oms"],)))
    assert vertaling == {"nl": "WHO veroordeelt de lockdown: het redt geen levens",
                         "en": "WHO CONDEMNS THE LOCKDOWN: IT DOES NOT SAVE LIVES"}
    assert m["hoofdletters"] == {"versie": hl.VERSIE, "beweringen": 1, "vertalingen": 1}
    assert pb.controleer(m["bestand"])


def test_the_check_refuses_a_normal_writing_that_changes_more_than_case(uitgave, tmp_path):
    m, nr = uitgave
    kopie = tmp_path / "kopie.db"
    kopie.write_bytes(open(m["bestand"], "rb").read())
    db = sqlite3.connect(kopie)
    db.execute("UPDATE bewering_normaal SET tekst = ? WHERE pagina = ?", (WHO_NORMAAL + " Echt waar.", nr["who"]))
    db.commit()
    db.close()
    with pytest.raises(pb.Weigering, match="hoofdletters"):
        pb.controleer(kopie)


def test_the_site_shows_the_normal_writing_and_says_how_it_circulated(uitgave):
    m, nr = uitgave
    client = TestClient(fa.maak_app(m["bestand"]))
    p = client.get(f"/api/en/factcheck/{nr['who']}").json()
    assert p["vertaling"]["tekst"] == WHO_NORMAAL and p["vertaling"]["taal"] == "en"
    assert p["vertaling"]["regel"] == "As it circulated, in capitals:" and p["bewering"] == WHO
    assert p["kop"]["titel"].startswith(f"{p['stempel']} {p['volgens']}: “WHO condemns lockdown")     # oordeel eerst (#34.2bw), normaal schrift
    assert json.loads(p["kop"]["ld"])["mainEntity"]["text"] == WHO          # zoekmachines krijgen het citaat
    rij = next(r for r in client.get("/api/en/archief").json()["rijen"] if r["nummer"] == nr["who"])
    assert rij["tekst"] == WHO_NORMAAL and rij["origineel"]["tekst"] == WHO
    assert rij["origineel"]["regel"] == "As it circulated, in capitals:"
    zoek = client.post("/api/en/zoek", data={"q": "lockdown poorer"}).json()["rijen"]
    assert "".join(s for s, _ in zoek[0]["stukken"]).startswith("WHO condemns lockdown")
    # een vertaling in normaal schrift, met het origineel zoals het rondging
    oms = client.get(f"/api/nl/factcheck/{nr['oms']}").json()
    assert oms["vertaling"]["tekst"] == "WHO veroordeelt de lockdown: het redt geen levens"
    assert oms["bewering"] == "OMS CONDENA O LOCKDOWN: NÃO SALVA VIDAS"
    # een gewone bewering verandert niet
    gewoon = client.get(f"/api/en/factcheck/{nr['gewoon']}").json()
    assert gewoon["vertaling"] is None and gewoon["bewering"] == "The vaccine causes autism"
