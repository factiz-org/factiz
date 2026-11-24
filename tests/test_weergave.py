"""Vertalingen voor weergave (PLAN #33.5, B32): de vraag, wat als antwoord telt, en wanneer een doeltaal op de site mag."""

import json

from doublecheck import weergave as wg


def test_the_request_asks_only_for_the_languages_the_claim_is_not_in_and_gives_the_text_as_it_is():
    v = wg.verzoek("Nespresso regala cafeteras", "es")
    assert v["model"] == "claude-haiku-5-5" and "json_schema" in json.dumps(v["output_config"])
    vraag = v["messages"][0]["content"]
    assert "Nespresso regala cafeteras" in vraag and "(language: es)" in vraag
    assert "Dutch (nl), German (de), French (fr)" in vraag and "Spanish" not in vraag
    assert wg.doelen("nl") == ["de", "es", "fr"] and wg.doelen("hi") == ["nl", "de", "es", "fr"]
    assert wg.doelen("und") == []                                         # zonder taal geen vertaling
    lang = wg.verzoek("x" * 5000, "en")["messages"][0]["content"]
    assert lang.count("x") == wg.MAX_TEKENS
    assert "add nothing" in v["system"].lower() and "leave nothing out" in v["system"]


def test_an_answer_counts_per_language_only_when_it_was_asked_for_and_says_something():
    tekst = json.dumps({"vertalingen": [{"taal": "nl", "tekst": " Nespresso geeft koffiemachines weg "},
                                        {"taal": "de", "tekst": ""}, {"taal": "es", "tekst": "No pedido"},
                                        {"taal": "fr", "tekst": "Nespresso offre des cafetières"},
                                        {"taal": "fr", "tekst": "Une deuxième"}]})
    # nl telt; de is leeg; es was niet gevraagd; fr staat er twee keer in, dus geen van beide
    assert wg.lees(tekst, ["nl", "de", "fr"]) == {"nl": "Nespresso geeft koffiemachines weg"}
    assert wg.lees(None, ["nl"]) == {} and wg.lees("kapot", ["nl"]) == {} and wg.lees('{"vertalingen": 3}', ["nl"]) == {}


def _antwoorden(n=300):
    return [{"nummer": f"{i:04d}", "bron": "pt" if i % 3 == 0 else "en", "vertalingen": {"nl": f"zin {i}", "de": f"Satz {i}"},
             "versie": wg.VERSIE} for i in range(n)]


def test_the_reading_sample_is_a_hundred_per_target_language_and_always_the_same():
    a = _antwoorden()
    nl, de = wg.leesproef(a, "nl"), wg.leesproef(a, "de")
    assert len(nl) == 100 and nl == wg.leesproef(a, "nl") and nl != de     # per taal een eigen greep
    assert wg.leesproef(a, "fr") == []                                      # geen Franse vertalingen in deze antwoorden


def test_a_target_language_goes_on_the_site_only_after_a_reading_without_a_meaning_error(tmp_path):
    a = _antwoorden()
    proef = wg.leesproef(a, "nl")
    bron = {x["nummer"]: x["bron"] for x in a}
    pad = tmp_path / "labels.json"
    assert wg.poort("nl", a, pad) == (False, "nog niets gelezen", frozenset())

    def schrijf(fouten=(), onzeker=(), gelezen=100):
        labels = {nr: "trouw" for nr in proef[:gelezen]}
        labels.update({nr: "betekenisfout" for nr in fouten})
        labels.update({nr: "onzeker" for nr in onzeker})
        labels[proef[5]] = labels.get(proef[5], "trouw") if proef[5] in fouten or proef[5] in onzeker else "klein"
        pad.write_text(json.dumps({"toelichting": "x", "gelezen_door": "Claude", "labels": {"nl": labels}}), encoding="utf-8")

    schrijf(gelezen=60)
    assert wg.poort("nl", a, pad)[:2] == (False, "60 van de 100 gelezen")
    schrijf()                                                               # alles trouw of klein
    assert wg.poort("nl", a, pad) == (True, "100 gelezen, geen betekenisfout", frozenset())
    pt = [nr for nr in proef if bron[nr] == "pt"]
    en = [nr for nr in proef if bron[nr] == "en"]
    schrijf(fouten=pt[:1], onzeker=pt[1:2])                                 # twee, beide in het Portugees
    assert wg.poort("nl", a, pad) == (True, "100 gelezen, 2 fout of onzeker; uit voor de brontaal pt", frozenset({"pt"}))
    schrijf(fouten=pt[:2] + en[:1])                                         # drie: de doeltaal blijft uit
    assert wg.poort("nl", a, pad)[0] is False and "3" in wg.poort("nl", a, pad)[1]
    assert wg.poort("de", a, pad)[0] is False                               # een andere taal heeft haar eigen lezing


def test_only_what_passed_its_reading_is_handed_to_the_release():
    a = _antwoorden(6)
    open_ = {"nl": (True, "x", frozenset({"pt"})), "de": (False, "y", frozenset())}
    uit = wg.vrijgegeven(a, lambda taal: open_.get(taal, (False, "", frozenset())))
    # Nederlands mag, behalve waar de bewering Portugees is; Duits mag niet
    assert uit == {"nl": {"0001": "zin 1", "0002": "zin 2", "0004": "zin 4", "0005": "zin 5"}}


# --- de controlestap (PLAN #33.5, stap 4) ---------------------------------------------------------------------------

def test_the_check_shows_the_original_and_every_translation_and_asks_a_verdict_per_language():
    v = wg.controleverzoek("Un cabo de la Legión niega el saludo", "es",
                           {"nl": "Een kapitein van het Legioen weigert de groet", "fr": "Un caporal de la Légion refuse le salut"})
    assert v["model"] == "claude-haiku-5-5"
    schema = v["output_config"]["format"]["schema"]["properties"]["checks"]["items"]["properties"]
    assert schema["lang"]["enum"] == ["nl", "fr"]                          # alleen de talen waarin een vertaling ligt
    assert schema["verdict"]["enum"] == ["same", "wording", "meaning"]
    vraag = v["messages"][0]["content"]
    assert vraag.startswith("Original (language: es):\nUn cabo de la Legión niega el saludo")
    assert "Dutch (nl):\nEen kapitein van het Legioen weigert de groet" in vraag and "French (fr):" in vraag
    assert "German" not in vraag
    # de vraag noemt soorten verschillen, geen voorbeelden uit de gelezen paren
    assert "negation" in v["system"] and "rank" in v["system"]
    assert not any(woord in v["system"] for woord in ("Legion", "Russia", "Donbas", "Kashi", "Atishi", "bond"))
    assert wg.controleverzoek("x" * 5000, "en", {"nl": "y"})["messages"][0]["content"].count("x") == wg.MAX_TEKENS
    assert wg.controleverzoek("a", "en", {"nl": "b"}, model="sonnet")["model"] == "claude-sonnet-5-5"


def test_the_second_version_of_the_check_adds_an_earlier_english_reading_when_there_is_one():
    met = wg.controleverzoek("Un cabo de la Legión", "es", {"nl": "Een kapitein van het Legioen"}, "controle-v2",
                             tweede="A Legion corporal")
    vraag = met["messages"][0]["content"]
    assert "Second reading (English, made separately):\nA Legion corporal" in vraag
    assert vraag.index("Original") < vraag.index("Second reading") < vraag.index("Dutch (nl)")
    assert "second reading" in met["system"].lower()
    zonder = wg.controleverzoek("The moon is made of cheese", "en", {"nl": "De maan is van kaas"}, "controle-v2")
    assert "Second reading" not in zonder["messages"][0]["content"]         # een Engelse bewering heeft er geen
    # de eerste versie krijgt de tweede lezing nooit te zien, ook niet als ze wordt meegegeven
    v1 = wg.controleverzoek("Un cabo", "es", {"nl": "Een kapitein"}, "controle-v1", tweede="A corporal")
    assert "Second reading" not in v1["messages"][0]["content"]
    assert not any(woord in met["system"] for woord in ("Legion", "Russia", "Donbas", "Kashi", "Atishi", "bond"))


def test_the_third_version_compares_only_with_the_english_reading_and_never_shows_the_original():
    v = wg.controleverzoek("Un cabo de la Legión", "es", {"nl": "Een kapitein van het Legioen"}, "controle-v3",
                           tweede="A Legion corporal")
    vraag = v["messages"][0]["content"]
    assert vraag.startswith("A (English):\nA Legion corporal") and "Dutch (nl):\nEen kapitein" in vraag
    assert "Un cabo" not in vraag and "Original" not in vraag              # het origineel leest dit model zelf verkeerd
    assert wg.vraagt_tweede("controle-v3") and not wg.vraagt_tweede("controle-v2")
    # zonder tweede lezing valt er niets te vergelijken
    import pytest
    with pytest.raises(wg.Weigering):
        wg.controleverzoek("The moon is made of cheese", "en", {"nl": "De maan is van kaas"}, "controle-v3")


def test_a_verdict_counts_only_for_a_language_that_was_asked_once_with_a_known_word():
    tekst = json.dumps({"checks": [{"lang": "nl", "note": " corporal  became captain ", "verdict": "meaning"},
                                   {"lang": "de", "note": "", "verdict": "same"},
                                   {"lang": "es", "note": "", "verdict": "wording"},
                                   {"lang": "fr", "note": "", "verdict": "perfect"},
                                   {"lang": "it", "note": "", "verdict": "same"}]})
    # fr: een woord dat geen oordeel is; it: niet gevraagd
    assert wg.lees_controle(tekst, ["nl", "de", "es", "fr"]) == {
        "nl": {"oordeel": "verschil", "wat": "corporal became captain"},
        "de": {"oordeel": "gelijk", "wat": ""}, "es": {"oordeel": "klein", "wat": ""}}
    dubbel = json.dumps({"checks": [{"lang": "nl", "note": "", "verdict": "same"},
                                    {"lang": "nl", "note": "x", "verdict": "meaning"}]})
    assert wg.lees_controle(dubbel, ["nl"]) == {}                           # twee keer genoemd, dus geen van beide
    for kapot in (None, "kapot", '{"checks": 3}', '{"checks": ["nl"]}', '{"anders": []}'):
        assert wg.lees_controle(kapot, ["nl"]) == {}


def _blad(tmp_path, eerst, na=None, opmerkingen=None):
    pad = tmp_path / "labels.json"
    blad = {"toelichting": "x", "gelezen_door": "Claude", "labels": eerst, "opmerkingen": opmerkingen or {}}
    if na is not None:
        blad["na_controle"] = {"labels": na}
    pad.write_text(json.dumps(blad), encoding="utf-8")
    return pad


def test_the_trial_counts_caught_errors_and_discarded_good_ones_apart_from_borderline_cases(tmp_path):
    eerst = {"nl": {f"g{i}": "trouw" for i in range(40)} | {"k1": "klein", "k2": "klein", "f1": "betekenisfout",
                                                           "f2": "betekenisfout", "f3": "onzeker"}}
    pad = _blad(tmp_path, eerst, opmerkingen={"nl": {"k2": "[en] grensgeval", "f1": "[es] een andere rang"}})
    oordelen = {f"g{i}": {"nl": "gelijk"} for i in range(40)}
    oordelen |= {"g0": {"nl": "verschil"}, "g1": {"nl": "klein"}, "g2": {}, "k1": {"nl": "klein"}, "k2": {"nl": "verschil"},
                 "f1": {"nl": "verschil"}, "f2": {"nl": "gelijk"}, "f3": {"nl": "verschil"}}
    u = wg.proefuitslag(pad, oordelen)
    # g0 is gemeld, g2 kreeg geen oordeel: beide zouden van de site verdwijnen; k2 is een grensgeval en telt nergens
    assert (u["fouten"], u["gevangen"], u["gemist"]) == (3, 2, [("nl", "f2")])
    assert (u["goed"], u["weg"], u["zonder_oordeel"]) == (41, 2, 1)
    assert (u["grens"], u["grens_gemeld"]) == (1, 1)
    assert u["haalt"] is False                                              # 2 van de 3 gevangen is geen 5
    ruim = {"nl": {f"g{i}": "trouw" for i in range(40)} | {f"f{i}": "betekenisfout" for i in range(6)}}
    pad = _blad(tmp_path, ruim)
    alles = {f"g{i}": {"nl": "gelijk"} for i in range(40)} | {f"f{i}": {"nl": "verschil"} for i in range(6)}
    assert wg.proefuitslag(pad, alles | {"f5": {"nl": "klein"}})["haalt"] is True         # 5 van de 6, niets weg
    assert wg.proefuitslag(pad, alles | {"f5": {"nl": "klein"}, "f4": {"nl": "gelijk"}})["haalt"] is False
    te_veel = alles | {f"g{i}": {"nl": "verschil"} for i in range(5)}                     # 5 van de 40 goede weg: 12,5%
    assert wg.proefuitslag(pad, te_veel)["haalt"] is False
    # een versie die alleen over een deel van de beweringen kan oordelen, wordt op dat deel geteld; de eis blijft de
    # eis op alle fouten, dus "haalt" zegt dan nee
    deel = wg.proefuitslag(pad, alles, alleen={"g0", "g1", "f0", "f1"})
    assert (deel["fouten"], deel["gevangen"], deel["goed"], deel["weg"], deel["haalt"]) == (2, 2, 2, 0, False)


def test_after_the_check_only_translations_it_let_through_reach_the_release():
    a = _antwoorden(6)
    controle = {"0000": {"nl": "gelijk"}, "0001": {"nl": "klein", "de": "gelijk"}, "0002": {"nl": "verschil"},
                "0003": {"nl": "gelijk"}, "0004": {}, "0005": {"nl": "gelijk"}}
    open_ = {"nl": (True, "x", frozenset({"pt"})), "de": (False, "y", frozenset())}
    uit = wg.vrijgegeven(a, lambda taal: open_.get(taal, (False, "", frozenset())), controle,
                         fout=frozenset({("nl", "0005")}))
    # 0000 en 0003 zijn Portugees (uit voor nl); 0002 is gemeld; 0004 kreeg geen oordeel; 0005 las ik zelf fout
    assert uit == {"nl": {"0001": "zin 1"}}
    assert wg.vrijgegeven(a, lambda taal: (True, "", frozenset()), {}) == {}             # zonder oordeel niets


def test_the_second_reading_draws_unread_pairs_the_check_let_through():
    a = _antwoorden()
    eerder = set(wg.leesproef(a, "nl"))
    controle = {x["nummer"]: {"nl": "verschil" if int(x["nummer"]) % 10 == 0 else "gelijk"} for x in a}
    na = wg.leesproef_na(a, controle, "nl")
    assert len(na) == 100 and na == wg.leesproef_na(a, controle, "nl")
    assert not set(na) & eerder                                              # niets dat ik al las
    assert not any(int(nr) % 10 == 0 for nr in na)                           # niets dat de controle meldde
    assert wg.leesproef_na(a, controle, "de") == []                          # geen oordeel over het Duits


def test_a_source_language_switched_off_comes_back_only_if_the_check_reported_the_error(tmp_path):
    a = _antwoorden()
    bron = {x["nummer"]: x["bron"] for x in a}
    eerste = wg.leesproef(a, "nl")
    fout_pt = next(nr for nr in eerste if bron[nr] == "pt")
    fout_en = next(nr for nr in eerste if bron[nr] == "en")
    eerst = {"nl": {nr: "trouw" for nr in eerste} | {fout_pt: "betekenisfout", fout_en: "betekenisfout"}}
    controle = {x["nummer"]: {"nl": "gelijk"} for x in a}
    controle[fout_pt] = {"nl": "verschil"}                                   # deze fout meldde de controle, de Engelse niet
    na = wg.leesproef_na(a, controle, "nl")
    assert wg.poort_na("nl", a, controle, _blad(tmp_path, eerst))[:2] == (False, "na de controle nog niets gelezen")
    half = _blad(tmp_path, eerst, {"nl": {nr: "trouw" for nr in na[:30]}})
    assert wg.poort_na("nl", a, controle, half)[:2] == (False, "na de controle 30 van de 100 gelezen")
    schoon = _blad(tmp_path, eerst, {"nl": {nr: "trouw" for nr in na}})
    open_, waarom, zonder = wg.poort_na("nl", a, controle, schoon)
    assert open_ is True and zonder == frozenset({"en"})                     # Portugees weer aan, Engels blijft uit
    assert "geen betekenisfout" in waarom and "en" in waarom
    nieuw_pt = [nr for nr in na if bron[nr] == "pt"]
    een = _blad(tmp_path, eerst, {"nl": {nr: "trouw" for nr in na} | {nieuw_pt[0]: "onzeker"}})
    assert wg.poort_na("nl", a, controle, een)[2] == frozenset({"en", "pt"})  # een nieuwe fout zet haar brontaal uit
    # wat ik in een van de twee leesproeven fout of onzeker noemde, staat nooit op de site
    assert wg.bekend_fout(een) == frozenset({("nl", fout_pt), ("nl", fout_en), ("nl", nieuw_pt[0])})
    drie = _blad(tmp_path, eerst, {"nl": {nr: "trouw" for nr in na} | {nr: "betekenisfout" for nr in nieuw_pt[:3]}})
    assert wg.poort_na("nl", a, controle, drie)[0] is False
    assert wg.bekend_fout(tmp_path / "bestaat-niet.json") == frozenset()
    # een fout die ik buiten de greep zag (dezelfde bewering in een andere taal) telt niet in de leesproef, maar staat
    # ook nooit op de site
    blad = json.loads(drie.read_text(encoding="utf-8"))
    blad["buiten_de_greep"] = {"labels": {"de": {fout_pt: "betekenisfout", "0001": "trouw"},
                                          "nl": {"0002": "betekenisfout"}}}
    drie.write_text(json.dumps(blad), encoding="utf-8")
    assert {("de", fout_pt), ("nl", "0002")} <= wg.bekend_fout(drie) and ("de", "0001") not in wg.bekend_fout(drie)
    met_laag = wg.poort("nl", a, drie)
    assert met_laag == wg.poort("nl", a, _blad(tmp_path, eerst))             # de telling van de greep blijft gelijk


# --- dezelfde methode na een import (PLAN #34.2x, PO 2026-11-12: "Ja, zelfde methode") --------------------------------

def _ronde(nummers, ronde, talen=("nl",), bron="pt", versie=None, model=None):
    rij = [{"nummer": nr, "bron": bron, "vertalingen": {t: f"{t} {nr}{' ' + model if model else ''}" for t in talen},
            "versie": versie or wg.VERSIE, "ronde": ronde, "gevraagd": list(talen)} for nr in nummers]
    for r in rij:
        if model:
            r["model"] = model
    return rij


def _lees(pad, labels=None, na_import=None):
    blad = {"toelichting": "x", "gelezen_door": "Claude", "labels": labels or {}}
    if na_import is not None:
        blad["na_import"] = {"labels": na_import}
    pad.write_text(json.dumps(blad), encoding="utf-8")


def test_the_reading_sample_stays_the_same_when_a_later_round_adds_answers():
    eerst = _antwoorden()
    proef = wg.leesproef(eerst, "nl")
    later = eerst + _ronde([f"9{i:04d}" for i in range(400)], 2)
    assert wg.leesproef(later, "nl") == proef                              # de greep schuift niet
    # een doeltaal die pas in ronde 2 gevraagd werd, trekt haar leesproef uit die ronde
    frans = later + _ronde([f"8{i:04d}" for i in range(150)], 2, talen=("fr",))
    assert len(wg.leesproef(frans, "fr")) == 100 and all(nr.startswith("8") for nr in wg.leesproef(frans, "fr"))


def test_a_later_round_with_the_same_method_goes_on_the_site_with_the_same_source_languages_off(tmp_path):
    eerst = _antwoorden()
    proef = wg.leesproef(eerst, "nl")
    pt = [nr for nr in proef if eerst[int(nr)]["bron"] == "pt"]
    pad = tmp_path / "labels.json"
    _lees(pad, {"nl": {**{nr: "trouw" for nr in proef}, pt[0]: "betekenisfout"}})
    later = eerst + _ronde(["90001", "90002"], 2, bron="en") + _ronde(["90003"], 2, bron="pt")
    t = wg.toelating("nl", later, pad)
    assert t[0] is True and t[2] == frozenset({"pt"}) and t[3] == frozenset()
    uit = wg.vrijgegeven(later, lambda taal: wg.toelating(taal, later, pad)[:3],
                         wacht={"nl": t[3]})
    assert {"90001", "90002"} <= set(uit["nl"]) and "90003" not in uit["nl"]   # Portugees bleef uit, ook in ronde 2


def test_a_translation_made_another_way_waits_for_its_own_first_reading(tmp_path):
    eerst = _antwoorden()
    pad = tmp_path / "labels.json"
    _lees(pad, {"nl": {nr: "trouw" for nr in wg.leesproef(eerst, "nl")}})
    later = eerst + _ronde(["90001"], 2, bron="en", versie="weergave-v2")
    assert "90001" in wg.toelating("nl", later, pad)[3]


def test_after_every_five_thousand_new_ones_fifty_are_read_before_more_go_on(tmp_path):
    eerst = _antwoorden()
    pad = tmp_path / "labels.json"
    ronde1 = {"nl": {nr: "trouw" for nr in wg.leesproef(eerst, "nl")}}
    nieuw = [f"9{i:05d}" for i in range(wg.BLOK + 300)]
    later = eerst + _ronde(nieuw[:wg.BLOK - 1], 2, bron="en") + _ronde(nieuw[wg.BLOK - 1:], 3, bron="en")
    eerste, tweede = nieuw[:wg.BLOK], nieuw[wg.BLOK:]
    proef = wg.blokproef(later, "nl", 0)
    assert len(proef) == wg.BLOK_N and set(proef) <= set(eerste) and proef == wg.blokproef(later, "nl", 0)

    _lees(pad, ronde1)
    open_, waarom, zonder, wacht = wg.toelating("nl", later, pad)
    # het volle blok blijft staan; wat erna kwam, wacht op de steekproef
    assert open_ and wacht == frozenset(tweede) and "0 van de 50" in waarom
    vol = later + _ronde([f"8{i:05d}" for i in range(10)], 4, bron="en")      # minder dan een blok erbij: geen eis
    assert wg.toelating("nl", eerst + _ronde(nieuw[:300], 2, bron="en"), pad)[3] == frozenset()
    assert set(wg.toelating("nl", vol, pad)[3]) == set(tweede) | {f"8{i:05d}" for i in range(10)}

    _lees(pad, ronde1, {"nl": {nr: "trouw" for nr in proef}})
    t = wg.toelating("nl", later, pad)
    assert t[0] is True and t[3] == frozenset()
    _lees(pad, ronde1, {"nl": {**{nr: "trouw" for nr in proef}, proef[0]: "onzeker"}})
    open_, _, zonder, wacht = wg.toelating("nl", later, pad)
    assert open_ and zonder == frozenset({"en"}) and wacht == frozenset()     # één: de brontaal van die fout uit
    _lees(pad, ronde1, {"nl": {**{nr: "trouw" for nr in proef}, proef[0]: "onzeker", proef[1]: "betekenisfout"}})
    assert wg.toelating("nl", later, pad)[0] is False                         # twee: de hele doeltaal dicht


def test_english_is_asked_only_for_a_claim_without_an_english_version_from_the_lab():
    assert wg.doelen("pt") == ["nl", "de", "es", "fr"]
    assert wg.doelen("pt", engels=True) == ["nl", "de", "es", "fr", "en"]
    assert wg.doelen("en", engels=True) == ["nl", "de", "es", "fr"] and wg.doelen("und", engels=True) == []
    v = wg.verzoek("Lula vendeu a Amazônia", "pt", ["en"])
    assert "Translate the claim into: English (en)." in v["messages"][0]["content"]
    assert json.dumps(v["output_config"]).count('"enum": ["en"]') == 1
    # wat al gevraagd is, wordt niet nog eens gevraagd
    a = [{"nummer": "1", "bron": "pt", "vertalingen": {"nl": "x"}, "versie": wg.VERSIE}]
    # (sinds #34.2be komen daar de tien nieuwe talen achter, behalve de eigen)
    tien = lambda eigen: [t for t in wg.NIEUW if t != eigen]  # noqa: E731
    assert wg.nog_te_vragen(a, {"1": ("t", "pt"), "2": ("t", "es")}, zonder_engels={"1", "2"}) == {
        "1": ["en", *tien("pt")], "2": ["nl", "de", "fr", "en", *tien("es")]}
    assert wg.samengevoegd(a + _ronde(["1"], 2, talen=("en",)))["1"]["vertalingen"] == {"nl": "x", "en": "en 1"}


# --- een methode is de vraag samen met het model (PLAN #34.2x, PO 2026-11-12: "Yes, with Sonnet") ----------------------

def test_a_method_is_the_question_together_with_the_model_and_each_target_language_has_one():
    assert wg.methode({"versie": wg.VERSIE}) == "weergave-v1/haiku"               # van vóór #34.2x: Haiku
    assert wg.methode({"versie": wg.VERSIE, "model": "sonnet"}) == "weergave-v1/sonnet"
    assert {t: wg.METHODE[t] for t in wg.VIER} == {t: "weergave-v1/haiku" for t in wg.VIER}
    assert wg.METHODE["en"] == "weergave-v1/sonnet"
    assert wg.verzoek("Lula vendeu a Amazônia", "pt", ["en"], model="sonnet")["model"] == "claude-sonnet-5-5"
    # de uitgave legt per doeltaal vast wie vertaalde
    assert wg.maker("en") == "claude-sonnet-5-5, weergave-v1" and wg.maker("nl") == "claude-haiku-5-5, weergave-v1"


def test_english_with_sonnet_reads_its_own_sample_without_the_pages_read_for_haiku_and_shows_only_sonnet(tmp_path):
    eerst = _antwoorden()
    paginas = [f"8{i:04d}" for i in range(300)]
    a = eerst + _ronde(paginas, 2, talen=("en",)) + _ronde(paginas, 3, talen=("en",), model="sonnet")
    haiku = wg.leesproef(a, "en", m="weergave-v1/haiku")
    sonnet = wg.leesproef(a, "en")                                              # de methode van nu: Sonnet
    assert len(haiku) == len(sonnet) == 100 and not set(haiku) & set(sonnet)
    assert sonnet == wg.leesproef(a + _ronde(["99999"], 4, talen=("en",), model="sonnet"), "en")
    pad = tmp_path / "labels.json"
    # de lezing van Haiku (drie fout) staat bovenaan; die van Sonnet onder `methoden`
    blad = {"toelichting": "x", "gelezen_door": "Claude",
            "labels": {"nl": {nr: "trouw" for nr in wg.leesproef(a, "nl")},
                       "en": {**{nr: "trouw" for nr in haiku}, **{nr: "betekenisfout" for nr in haiku[:3]}}}}
    pad.write_text(json.dumps(blad), encoding="utf-8")
    assert wg.poort("en", a, pad, m="weergave-v1/haiku")[0] is False
    assert wg.toelating("en", a, pad)[:2] == (False, "0 van de 100 gelezen")
    blad["methoden"] = {"weergave-v1/sonnet": {"labels": {"en": {nr: "trouw" for nr in sonnet}}}}
    pad.write_text(json.dumps(blad), encoding="utf-8")
    stand = {t: wg.toelating(t, a, pad) for t in wg.DOELTALEN}
    assert stand["en"][0] is True and stand["en"][3] == frozenset()
    uit = wg.vrijgegeven(a, lambda t: stand[t][:3], wacht={t: x[3] for t, x in stand.items()}, methode=wg.METHODE)
    assert uit["en"] == {nr: f"en {nr} sonnet" for nr in paginas}                 # nooit de vertaling van Haiku
    assert uit["nl"]["0001"] == "zin 1"                                         # nl blijft bij Haiku


def test_english_asked_with_haiku_is_asked_again_with_sonnet_and_not_after():
    a = [{"nummer": "1", "bron": "pt", "vertalingen": {"nl": "x"}, "versie": wg.VERSIE}] + _ronde(["1"], 2, talen=("en",))
    paginas = {"1": ("t", "pt")}
    tien = [t for t in wg.NIEUW if t != "pt"]                 # de tien nieuwe talen (#34.2be) staan er los van
    assert wg.nog_te_vragen(a, paginas, zonder_engels={"1"}) == {"1": ["en", *tien]}
    assert wg.nog_te_vragen(a + _ronde(["1"], 3, talen=("en",), model="sonnet"), paginas, zonder_engels={"1"}) == {"1": tien}


def test_the_cost_of_one_translation_comes_from_batches_that_recorded_what_they_asked():
    batches = [{"werkelijk": 13.0, "nummers": ["1"]},                                  # van vóór #34.2x: telt niet
               {"werkelijk": 0.15, "gevraagd": {str(i): ["en"] for i in range(3000)}},
               {"werkelijk": None, "gevraagd": {"9": ["en"]}},                         # loopt nog
               {"werkelijk": 9.0, "model": "sonnet", "gevraagd": {"8": ["en"]}}]        # een ander model
    assert wg.per_doeltaal(batches) == 0.15 / 3000 and wg.per_doeltaal(batches[:1]) is None


def test_a_pair_read_as_wrong_in_any_reading_never_goes_on_the_site(tmp_path):
    pad = tmp_path / "labels.json"
    pad.write_text(json.dumps({
        "labels": {"nl": {"1": "betekenisfout", "2": "trouw"}},
        "na_import": {"labels": {"nl": {"3": "onzeker"}}},
        "methoden": {"weergave-v1/sonnet": {"labels": {"en": {"4": "betekenisfout", "5": "klein"}},
                                            "na_import": {"labels": {"en": {"6": "onzeker"}}}}}}), encoding="utf-8")
    assert wg.bekend_fout(pad) == {("nl", "1"), ("nl", "3"), ("en", "4"), ("en", "6")}


# --- een brontaal weer aan na een nieuwe proef (PLAN #34.2aa, PO 2026-11-13: "Yes, read them") ------------------------

def _veel(n=900):
    """Antwoorden in de eerste ronde: een derde Portugees, de rest Engels, met Nederlands."""
    return [{"nummer": f"{i:04d}", "bron": "pt" if i % 3 == 0 else "en", "vertalingen": {"nl": f"zin {i}"},
             "versie": wg.VERSIE} for i in range(n)]


def test_the_new_trial_for_a_source_language_draws_only_that_language_and_never_a_pair_read_before(tmp_path):
    a = _veel()
    eerst = wg.leesproef(a, "nl")
    pad = tmp_path / "labels.json"
    pad.write_text(json.dumps({"labels": {"nl": {nr: "trouw" for nr in eerst}},
                               "buiten_de_greep": {"labels": {"nl": {"0002": "betekenisfout"}}}}), encoding="utf-8")
    proef = wg.bronproef(a, "nl", "en", pad)
    assert len(proef) == 100 and all(a[int(nr)]["bron"] == "en" for nr in proef)
    assert not set(proef) & set(eerst) and "0002" not in proef
    # vast: een latere ronde en een nieuw label veranderen haar niet
    later = a + [{"nummer": f"9{i:04d}", "bron": "en", "vertalingen": {"nl": "x"}, "versie": wg.VERSIE, "ronde": 2}
                 for i in range(300)]
    blad = json.loads(pad.read_text(encoding="utf-8"))
    blad["bronproeven"] = {"nl": {"en": {nr: "trouw" for nr in proef[:40]}}}
    pad.write_text(json.dumps(blad), encoding="utf-8")
    assert wg.bronproef(later, "nl", "en", pad) == proef


def test_a_source_language_switched_off_comes_back_only_after_a_hundred_new_pairs_without_an_error(tmp_path):
    a = _veel()
    eerst = wg.leesproef(a, "nl")
    en = [nr for nr in eerst if a[int(nr)]["bron"] == "en"]
    pad = tmp_path / "labels.json"
    blad = {"labels": {"nl": {**{nr: "trouw" for nr in eerst}, en[0]: "betekenisfout"}}}
    pad.write_text(json.dumps(blad), encoding="utf-8")
    assert wg.poort("nl", a, pad)[2] == frozenset({"en"})
    proef = wg.bronproef(a, "nl", "en", pad)

    def lees(labels):
        blad["bronproeven"] = {"nl": {"en": labels}}
        pad.write_text(json.dumps(blad), encoding="utf-8")
        return wg.poort("nl", a, pad)

    open_, waarom, zonder = lees({nr: "trouw" for nr in proef[:99]})          # nog niet alles gelezen: blijft uit
    assert open_ and zonder == frozenset({"en"}) and "99 van de 100" in waarom
    open_, waarom, zonder = lees({**{nr: "trouw" for nr in proef}, proef[7]: "klein"})
    assert open_ and zonder == frozenset() and "weer aan" in waarom               # geen fout: het Engels gaat weer aan
    open_, _, zonder = lees({**{nr: "trouw" for nr in proef}, proef[3]: "onzeker"})
    assert zonder == frozenset({"en"})                                          # één twijfel: het blijft uit
    assert ("nl", proef[3]) in wg.bekend_fout(pad) and ("nl", en[0]) in wg.bekend_fout(pad)
    # wat erna komt, laat het Engels ook op de site
    lees({nr: "trouw" for nr in proef})
    uit = wg.vrijgegeven(a, lambda t: wg.poort(t, a, pad) if t == "nl" else (False, "", frozenset()),
                         fout=wg.bekend_fout(pad))
    assert en[1] in uit["nl"] and en[0] not in uit["nl"]


def test_a_target_language_that_closed_never_opens_through_a_source_trial(tmp_path):
    a = _veel()
    eerst = wg.leesproef(a, "nl")
    en = [nr for nr in eerst if a[int(nr)]["bron"] == "en"]
    pad = tmp_path / "labels.json"
    blad = {"labels": {"nl": {**{nr: "trouw" for nr in eerst}, **{nr: "betekenisfout" for nr in en[:3]}}}}
    blad["bronproeven"] = {"nl": {"en": {nr: "trouw" for nr in wg.bronproef(a, "nl", "en", pad)}}}
    pad.write_text(json.dumps(blad), encoding="utf-8")
    assert wg.poort("nl", a, pad)[0] is False


# --- tien sitetalen erbij (PLAN #34.2be fase 2, B79; PO 2026-11-15: "Start fase 2", binnen $39,91 tegoed) ---------------

def test_the_ten_new_site_languages_are_the_site_list_without_the_five_and_each_has_a_name_for_the_question():
    from doublecheck.sitetalen import BASIS, SITETALEN
    assert wg.NIEUW == tuple(t for t in SITETALEN if t not in BASIS) and len(wg.NIEUW) == 10
    assert wg.DOELTALEN[:5] == ("nl", "de", "es", "fr", "en")              # de greep van de oude talen schuift niet
    assert set(wg.NIEUW) <= set(wg.NAAM) and "Traditional" in wg.NAAM["zh"] and "Brazil" in wg.NAAM["pt"]


def test_a_claim_gets_the_ten_new_languages_except_its_own_and_an_old_answer_counts_only_for_the_four():
    assert wg.doelen("pt", sitetalen=True) == ["nl", "de", "es", "fr", "ru", "uk", "id", "tr", "zh", "ja", "hi", "ar", "fa"]
    assert wg.doelen("pt") == ["nl", "de", "es", "fr"] and wg.doelen("und", sitetalen=True) == []
    oud = [{"nummer": "1", "bron": "en", "vertalingen": {"nl": "a", "de": "b", "es": "c", "fr": "d"}, "versie": wg.VERSIE}]
    nodig = wg.nog_te_vragen(oud, {"1": ("t", "en")}, zonder_engels=set())
    assert nodig == {"1": list(wg.NIEUW)}                                   # de vier waren er al; nu de tien
    klaar = oud + _ronde(["1"], 4, talen=wg.NIEUW, bron="en", versie=wg.VERSIE_NIEUW)
    # het Portugees kreeg een eigen methode (weergave-v6): na de ronde met v2 wordt het nog eens gevraagd, daarna niet
    assert wg.nog_te_vragen(klaar, {"1": ("t", "en")}, zonder_engels=set()) == {"1": ["pt"]}
    klaar += _ronde(["1"], 5, talen=("pt",), bron="en", versie=wg.VERSIE_V6)
    assert wg.nog_te_vragen(klaar, {"1": ("t", "en")}, zonder_engels=set()) == {}


def test_the_new_method_turns_thinking_off_and_leaves_room_for_ten_languages_while_the_old_question_stays():
    # het Portugees met weergave-v6 na de leesproef van fase 2 (PO 2026-11-16: "Kijk welke taal we nog bruikbaar kunnen
    # maken naast het Perzisch binnen tegoed"); de andere negen houden de methode van hun eerste ronde
    assert wg.METHODE["pt"] == "weergave-v6/haiku"
    assert {wg.METHODE[t] for t in wg.NIEUW if t != "pt"} == {"weergave-v2/haiku"}
    nieuw = wg.verzoek("Lula vendeu a Amazônia", "pt", list(wg.NIEUW[1:]), versie=wg.VERSIE_NIEUW)
    assert nieuw["thinking"] == {"type": "disabled"} and nieuw["output_config"]["effort"] == "low"
    assert nieuw["max_tokens"] >= 900 * 9 and nieuw["system"] == wg.verzoek("x", "pt")["system"]
    assert "Brazilian Portuguese" not in nieuw["messages"][0]["content"] and "Traditional Chinese" in nieuw["messages"][0]["content"]
    oud = wg.verzoek("Lula vendeu a Amazônia", "pt")
    assert "thinking" not in oud and oud["max_tokens"] == 4000              # de vraag van de vier blijft gelijk
    assert wg.maker("zh") == "claude-haiku-5-5, weergave-v2"


def test_an_answer_of_the_new_method_is_read_for_its_own_sample_and_never_mixes_with_the_four():
    eerst = _antwoorden()
    paginas = [f"7{i:04d}" for i in range(300)]
    a = eerst + _ronde(paginas, 4, talen=("ja", "hi"), bron="en", versie=wg.VERSIE_NIEUW)
    assert len(wg.leesproef(a, "ja")) == 100 and set(wg.leesproef(a, "ja")) <= set(paginas)
    assert wg.leesproef(a, "ja") != wg.leesproef(a, "hi")
    assert wg.leesproef(a, "nl") == wg.leesproef(eerst, "nl")


def test_the_new_languages_spend_from_their_own_cap_with_room_for_a_wrong_estimate():
    assert wg.GRENS_NIEUW <= 39.91
    assert wg.past(uitgegeven=1.0, schatting=30.0, grens=39.0)              # 1 + 30 x 1,15 = 35,5
    assert not wg.past(uitgegeven=1.0, schatting=34.0, grens=39.0)          # 1 + 39,1 is te veel
    # wat één vertaling in een nieuwe taal kost, komt alleen uit batches van die methode
    batches = [{"werkelijk": 1.0, "gevraagd": {str(i): ["nl"] for i in range(1000)}},
               {"werkelijk": 2.0, "versie": wg.VERSIE_NIEUW, "gevraagd": {str(i): ["ja", "hi"] for i in range(1000)}}]
    assert wg.per_doeltaal(batches, wg.VERSIE) == 1.0 / 1000
    assert wg.per_doeltaal(batches, wg.VERSIE_NIEUW) == 2.0 / 2000


def test_the_question_with_thinking_keeps_thinking_on_and_leaves_room_for_it():
    """De proef na de leesproef van fase 2 (PLAN #34.2be): dezelfde vraag mét denkwerk, zoals weergave-v1 dat had."""
    v = wg.verzoek("Lula vendeu a Amazônia", "pt", list(wg.NIEUW[1:]), versie=wg.VERSIE_DENKEN)
    assert "thinking" not in v and v["output_config"]["effort"] == "low" and v["max_tokens"] >= 3000 + 900 * 9


def test_a_word_half_in_another_script_is_found_unless_the_original_has_it_too():
    """Woorden half in een ander schrift ('documentируют', 'シriraj', 'پانDYA'): een teken van een vertaling die ontspoort."""
    assert wg.gemengd("Они documentируют нарушения", "ru", "They document violations")
    assert wg.gemengd("シriraj病院の水", "ja", "Siriraj hospital water")
    assert wg.gemengd("پانDYA بازیکن است", "fa", "Pandya is a player")
    assert not wg.gemengd("Они документируют нарушения", "ru", "They document violations")
    assert not wg.gemengd("GitHubのソースコード", "ja", "Source code on GitHub")
    assert not wg.gemengd("Они documentируют", "ru", "Они documentируют")      # stond zo in het origineel


def test_a_translation_with_a_word_half_in_another_script_never_goes_on_the_site():
    """Het Perzisch haalde de poort, maar 6% van zijn vertalingen heeft een woord half in Latijnse letters ('پانDYA'):
    die gaan niet mee (PLAN #34.2be); de bewering toont dan de Engelse versie of het origineel."""
    a = [{"nummer": "1", "bron": "en", "vertalingen": {"fa": "پاندیا بازیکن است"}, "versie": wg.VERSIE_NIEUW},
         {"nummer": "2", "bron": "en", "vertalingen": {"fa": "پانDYA بازیکن است"}, "versie": wg.VERSIE_NIEUW}]
    uit = wg.vrijgegeven(a, lambda t: (t == "fa", "", frozenset()),
                         originelen={"1": "Pandya is a player", "2": "Pandya is a player"})
    assert uit == {"fa": {"1": "پاندیا بازیکن است"}}


def test_the_fourth_question_adds_rules_for_numbers_labels_hedges_and_scripts_and_the_english_help():
    """weergave-v4 (PLAN #34.2be): gericht op wat de leesproef van fase 2 vond; de Engelse versie als hulp, het origineel
    beslist."""
    v = wg.verzoek("ឪពុក​យំ ... រាប់​ម៉ឺន​ដុល្លា", "km", ["pt", "hi"], versie=wg.VERSIE_V4,
                   engels="The father cried after his dragon fish worth tens of thousands of dollars died")
    assert v["thinking"] == {"type": "disabled"}
    for regel in ("exactly", "Claim", "allegedly", "script", "Traditional"):
        assert regel in v["system"], regel
    vraag = v["messages"][0]["content"]
    assert "tens of thousands" in vraag and "the original decides" in vraag
    assert "English rendering" not in wg.verzoek("x", "en", ["pt"], versie=wg.VERSIE_V4)["messages"][0]["content"]
    assert wg.verzoek("x", "km", ["pt"])["system"] == wg._SYSTEEM                 # de vraag van de vier blijft


def test_the_fifth_question_keeps_a_claim_label_only_when_the_original_has_one():
    """weergave-v4 zette 'Claim:' voor 21 tot 33% van de vertalingen zonder zo'n label in het origineel; v5 niet."""
    v5 = wg.verzoek("x", "km", ["pt"], versie=wg.VERSIE_V5, engels="y")
    assert "Never add a label" in v5["system"] and "Keep a label such as 'Claim:' at the start" not in v5["system"]
    assert v5["thinking"] == {"type": "disabled"} and "English rendering" in v5["messages"][0]["content"]
    assert "Never add a label" not in wg.verzoek("x", "km", ["pt"], versie=wg.VERSIE_V4)["system"]   # v4 blijft zoals gemeten


def test_the_cost_of_a_question_counts_the_input_once_per_question_and_the_output_per_language():
    """Een vraag met één taal kost veel meer per vertaling dan een met acht, want de invoer telt per vraag: de grens moet
    dat zien (PLAN #34.2be)."""
    rijen = [{"tokens": [1000, 800], "gevraagd": list("abcdefgh")}, {"tokens": [1200, 800], "gevraagd": list("abcdefgh")}]
    prijs = {"in": 0.05, "uit": 0.25}                                        # dollar per miljoen, via de batch
    een = wg.kosten_vraag(rijen, 1, prijs)
    assert abs(een - (1100 * 0.05 + 100 * 0.25) / 1e6) < 1e-12
    assert wg.kosten_vraag(rijen, 8, prijs) / 8 < een / 2                   # per vertaling veel goedkoper met acht


def test_the_sixth_question_puts_the_claim_between_tags_so_its_heading_never_leaks_into_the_translation():
    """v5 begon de vraag met 'Claim (language: en):' en nam dat 16 van de 100 keer over in de vertaling; v6 zet de bewering
    tussen markeringen en de regel over een label geldt alleen voor de tekst daarbinnen."""
    v6 = wg.verzoek("KKK officially endorses Trump 2020.", "en", ["pt"], versie=wg.VERSIE_V6)
    vraag = v6["messages"][0]["content"]
    assert vraag.startswith('<claim language="en">\nKKK officially endorses Trump 2020.\n</claim>')
    assert "Claim (language" not in vraag and "inside <claim>" in v6["system"] and "heading" in v6["system"]
    hulp = wg.verzoek("x", "km", ["pt"], versie=wg.VERSIE_V6, engels="y")["messages"][0]["content"]
    assert "<english_rendering>\ny\n</english_rendering>" in hulp
    assert wg.verzoek("x", "km", ["pt"], versie=wg.VERSIE_V5)["messages"][0]["content"].startswith("Claim (language")


def test_a_batch_request_of_a_question_with_the_english_help_carries_that_help():
    """De Engelse versie gaat mee in de vraag van v4 tot v6, ook in de batch (`batchverzoek`), niet alleen in de proef."""
    v = wg.batchverzoek("1", ("ឪពុក​យំ", "km"), ["pt"], "weergave-v6/haiku", {"1": "The father cried"})
    assert v["custom_id"] == "1" and "<english_rendering>\nThe father cried" in v["params"]["messages"][0]["content"]
    oud = wg.batchverzoek("1", ("x", "km"), ["nl"], "weergave-v1/haiku", {"1": "y"})
    assert "english" not in oud["params"]["messages"][0]["content"].lower()


def test_every_question_after_the_first_spends_from_the_budget_of_the_new_languages():
    """v2 tot v6 zijn de vragen van de tien nieuwe talen: hun proeven en batches tellen onder GRENS_NIEUW, v1 onder GRENS."""
    for v in (wg.VERSIE_NIEUW, wg.VERSIE_DENKEN, wg.VERSIE_V4, wg.VERSIE_V5, wg.VERSIE_V6):
        assert wg.van_nieuw({"versie": v}), v
    assert not wg.van_nieuw({"versie": wg.VERSIE}) and not wg.van_nieuw({})


def test_with_sonnet_the_sixth_question_turns_thinking_off_the_way_sonnet_accepts():
    """Sonnet 5.5 weigert thinking 'disabled'; 'between_tools' zet het uit bij effort low (PLAN #34.2bn, de proef)."""
    v = wg.verzoek("x", "km", ["hi"], model="sonnet", versie=wg.VERSIE_V6, engels="y")
    assert v["model"] == "claude-sonnet-5-5" and v["thinking"] == {"type": "between_tools"}
    assert v["output_config"]["effort"] == "low"
    assert wg.verzoek("x", "km", ["hi"], versie=wg.VERSIE_V6)["thinking"] == {"type": "disabled"}
