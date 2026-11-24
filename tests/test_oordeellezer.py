"""De oordelen die de tabel niet leest, gelezen voor het platform (PLAN #34.2o): een taalmodel stelt voor, een leesproef
beslist, en het lab houdt zijn oordelen."""

import json

from doublecheck import oordeellezer as ol

RIJEN = [
    # (eigen woorden, oordeel van de tabel, adres van de check, aantal checks, een bewering)
    ("අසත්‍යයි", "onbekend", "https://sinhala.factcrescendo.com/a", 14, "Een vlag op de Eiffeltoren"),
    ("අසත්‍යයි ", "onbekend", "https://sinhala.factcrescendo.com/b", 4, "Een vlag op de Eiffeltoren"),   # andere spaties
    ("Falso", "onwaar", "https://maldita.es/x", 900, "x"),                            # kort en bekend: alleen vertalen
    ("Non. Plusieurs éléments permettent d'établir que cette histoire ne tient pas la route. " * 2,
     "onbekend", "https://factuel.afp.com/x", 1, "Un berger  australien"),            # vrije tekst: met de bewering
    ("This claim is false, and here is a very long explanation of why it is false in every respect at all.",
     "onwaar", "https://example.org/x", 3, "y"),                                      # lang en bekend: niets te vragen
    ("Scam", "onbekend", "https://www.snopes.com/fact-check/x", 7, "z"),              # Snopes noemt dit geen oordeel
    ("", "onbekend", "https://example.org/y", 5, "z"),
]


def _werk():
    return {w["tekst"]: w for w in ol.werkset(RIJEN)}


def test_only_what_the_table_cannot_read_is_asked_for_a_verdict_and_only_short_words_are_translated():
    werk = _werk()
    # een vast label (meer dan drie checks) krijgt geen bewering mee: die van één check zou het model sturen
    assert werk["අසත්‍යයි"] == {"tekst": "අසත්‍යයි", "kort": True, "tabel": None, "checks": 18, "bewering": None}
    assert werk["Falso"]["tabel"] == "onwaar" and werk["Falso"]["kort"] is True
    lang = next(t for t in werk if t.startswith("Non."))
    assert werk[lang]["kort"] is False and werk[lang]["tabel"] is None and werk[lang]["bewering"] == "Un berger australien"
    assert not any(t.startswith("This claim is false") for t in werk)      # lang en al gelezen
    assert "Scam" not in werk and "" not in werk                           # geen oordeel volgens Snopes zelf; leeg


def test_an_answer_counts_only_with_a_known_verdict_and_a_full_translation_for_short_words():
    teksten = [("අසත්‍යයි", True), ("Non. Plusieurs éléments …", False), ("Falso", True)]
    antwoord = {"antwoorden": [
        {"nr": 1, "soort": "onwaar", "glos": {"en": "false", "nl": "onwaar", "de": "falsch", "es": "falso", "fr": "faux"}},
        {"nr": 2, "soort": "onwaar", "glos": {"en": "", "nl": "", "de": "", "es": "", "fr": ""}},
        {"nr": 3, "soort": "waarschijnlijk", "glos": {"en": "False", "nl": "", "de": "Falsch", "es": "Falso", "fr": "Faux"}}]}
    gelezen = ol.lees_antwoord(json.dumps(antwoord), teksten)
    assert gelezen[0] == {"soort": "onwaar", "glos": {"en": "false", "nl": "onwaar", "de": "falsch", "es": "falso", "fr": "faux"}}
    assert gelezen[1] == {"soort": "onwaar", "glos": None}                 # vrije tekst krijgt geen vertaling
    assert gelezen[2] == {"soort": None, "glos": None}                     # onbekende soort, onvolledige vertaling
    assert ol.lees_antwoord("geen json", teksten) == [None, None, None]
    dubbel = {"antwoorden": [{"nr": 1, "soort": "waar", "glos": {}}, {"nr": 1, "soort": "onwaar", "glos": {}}]}
    assert ol.lees_antwoord(json.dumps(dubbel), teksten)[0] is None


def _antwoorden(n=300):
    uit = [{"tekst": f"oordeel {i}", "soort": "onwaar" if i % 3 else "geen", "glos": None, "tabel": None,
            "checks": 1 + i % 7, "kort": False} for i in range(n)]
    uit += [{"tekst": f"kort {i}", "soort": "onwaar", "glos": {"en": "false", "nl": "onwaar", "de": "falsch",
             "es": "falso", "fr": "faux"}, "tabel": "onwaar", "checks": 10, "kort": True} for i in range(80)]
    return uit


def test_the_reading_sample_is_fixed_weighted_by_checks_and_never_takes_a_no_verdict_or_a_table_verdict():
    proef = ol.leesproef(_antwoorden())
    assert proef == ol.leesproef(_antwoorden())
    lezing = {a["tekst"]: a for a in _antwoorden()}
    assert len(proef["oordelen"]) == 200 and len(set(proef["oordelen"])) == 200
    assert all(lezing[t]["soort"] != "geen" and lezing[t]["tabel"] is None for t in proef["oordelen"])
    assert len(proef["glossen"]) == 50 and all(lezing[t]["kort"] and lezing[t]["glos"] for t in proef["glossen"])


def _labels(tmp_path, proef, oordelen=None, glossen=None):
    pad = tmp_path / "labels.json"
    pad.write_text(json.dumps({"versie": ol.VERSIE, "toelichting": "proef",
                               "oordelen": {t: (oordelen or {}).get(t, "goed") for t in proef["oordelen"]},
                               "glossen": {t: (glossen or {}).get(t, "goed") for t in proef["glossen"]}}), encoding="utf-8")
    return pad


def test_the_gate_closes_on_one_verdict_on_the_wrong_side_or_one_invented_verdict(tmp_path):
    antwoorden = _antwoorden()
    proef = ol.leesproef(antwoorden)
    assert ol.poort(antwoorden, _labels(tmp_path, proef))["oordelen"][0] is True
    eerste = proef["oordelen"][0]
    for fout in ("fout_kant", "fout_verzonnen"):
        assert ol.poort(antwoorden, _labels(tmp_path, proef, {eerste: fout}))["oordelen"][0] is False
    vijf = {t: "fout_buur" for t in proef["oordelen"][:4]} | {proef["oordelen"][4]: "twijfel"}
    assert ol.poort(antwoorden, _labels(tmp_path, proef, vijf))["oordelen"][0] is True
    zes = vijf | {proef["oordelen"][5]: "fout_buur"}
    assert ol.poort(antwoorden, _labels(tmp_path, proef, zes))["oordelen"][0] is False
    assert ol.poort(antwoorden, tmp_path / "bestaat-niet.json")["oordelen"][0] is False


def test_the_translations_have_their_own_gate_and_one_wrong_meaning_closes_it(tmp_path):
    antwoorden = _antwoorden()
    proef = ol.leesproef(antwoorden)
    assert ol.poort(antwoorden, _labels(tmp_path, proef))["glossen"][0] is True
    fout = _labels(tmp_path, proef, glossen={proef["glossen"][0]: "fout"})
    uit = ol.poort(antwoorden, fout)
    assert uit["glossen"][0] is False and uit["oordelen"][0] is True


def test_what_goes_into_the_publication_never_overrides_the_table_and_never_turns_no_verdict_into_one(tmp_path):
    antwoorden = _antwoorden()
    proef = ol.leesproef(antwoorden)
    oordelen, glossen = ol.voor_uitgave(antwoorden, ol.poort(antwoorden, _labels(tmp_path, proef)))
    assert all(s != "geen" for s in oordelen.values()) and not any(t.startswith("kort ") for t in oordelen)
    assert "oordeel 1" in oordelen and "oordeel 0" not in oordelen       # 0 % 3: geen oordeel
    assert glossen["kort 0"]["nl"] == "onwaar"
    dicht = {"oordelen": (False, "x"), "glossen": (False, "y")}
    assert ol.voor_uitgave(antwoorden, dicht) == ({}, {})


def test_whitespace_never_makes_two_wordings():
    assert ol.sleutel("  Falso \n / Manipulado ") == "Falso / Manipulado"


def test_a_rare_verdict_is_asked_with_its_claim_and_a_label_without():
    """v2 (#34.2o): "Found guilty by jury" zegt pas iets naast "Roger Stone was charged with alleged crimes"."""
    vraag = ol.verzoek([("Found guilty by jury", True, "Roger Stone was charged with alleged crimes"), ("Mix", True, None)])
    tekst = vraag["messages"][0]["content"][0]["text"]
    assert "1. [short] Verdict: Found guilty by jury\n   Claim: Roger Stone was charged with alleged crimes" in tekst
    assert "2. [short] Verdict: Mix" in tekst and tekst.count("Claim:") == 1
    assert "every sentence" in vraag["system"]


def test_only_answers_of_the_current_version_count():
    oud = {"tekst": "Falsi", "soort": "waar", "tabel": None, "checks": 1, "kort": True, "glos": None, "versie": "oordeel-lezer-v1"}
    assert ol.lezingen([oud]) == {}
    nieuw = {**oud, "soort": "onwaar", "versie": ol.VERSIE}
    assert ol.lezingen([oud, nieuw])["Falsi"]["soort"] == "onwaar"


def test_a_true_or_partly_true_reading_from_free_text_never_counts_but_from_a_label_it_does():
    """De kantregel (#34.2o): uit vrije tekst (hoogstens drie checks) alleen onwaar, misleidend of onbewezen."""
    vrij = {"tekst": "Gedoneerd bloed is even veilig", "soort": "waar", "tabel": None, "checks": 1, "kort": False}
    label = {"tekst": "Checks out", "soort": "waar", "tabel": None, "checks": 7, "kort": True}
    assert not ol.telt(vrij) and ol.telt(label) and ol.telt({**vrij, "soort": "onwaar"})
    assert not ol.telt({**vrij, "soort": "deels-waar"}) and not ol.telt({**label, "tabel": "waar"})
    open_ = {"oordelen": (True, ""), "glossen": (False, "")}
    oordelen, _ = ol.voor_uitgave([vrij, label], open_)
    assert oordelen == {"Checks out": "waar"}


def test_what_i_read_while_developing_never_enters_the_sample_that_opens_the_gate():
    antwoorden = _antwoorden()
    gezien = frozenset(ol.leesproef(antwoorden)["oordelen"][:30])
    proef = ol.leesproef(antwoorden, gezien=gezien)
    assert not gezien & set(proef["oordelen"]) and not gezien & set(proef["glossen"])
