"""Namen voor het platform (PLAN #33.7, SPECS E9.S11): publieke personen, organisaties en plaatsen met een nummer van
Wikidata. Een naam is een ingang, geen oordeel; een privépersoon komt er nooit op."""

import json

import pytest

from doublecheck import namen as nm


# --- de vraag aan het model ------------------------------------------------------------------------------------------

def test_the_question_asks_for_names_in_the_claims_and_never_for_a_verdict():
    from doublecheck.modellen import MODELLEN

    p = nm.naamverzoek([("Zelensky compró una villa en Florida " * 40, "es"), ("WHO says masks do not work", "en")])
    assert p["model"] == MODELLEN["haiku"]["id"]
    tekst = p["messages"][0]["content"][0]["text"]
    assert tekst.startswith("1. (es) Zelensky compró") and "\n2. (en) WHO says" in tekst
    assert len(tekst) < 700                                           # een lange bewering wordt ingekort
    assert "do not judge" in p["system"].lower()
    item = p["output_config"]["format"]["schema"]["properties"]["antwoorden"]["items"]
    assert set(item["required"]) == {"nr", "namen"}
    assert set(item["properties"]["namen"]["items"]["properties"]["soort"]["enum"]) == set(nm.SOORTEN)


def test_the_question_tells_the_model_to_leave_private_persons_out():
    systeem = nm.naamverzoek([("x", "en")])["system"].lower()
    assert "private" in systeem and "leave" in systeem
    for woord in ("victim", "suspect", "child", "relative"):
        assert woord in systeem


def _antwoord(*rijen):
    return json.dumps({"antwoorden": [{"nr": nr, "namen": [{"naam": n, "soort": s} for n, s in namen]}
                                      for nr, namen in rijen]})


def test_names_are_read_per_claim_and_no_name_is_an_answer_too():
    uit = nm.lees_namen(_antwoord((1, [("Volodymyr Zelensky", "persoon"), ("Florida", "plaats")]), (2, [])), 2)
    assert uit == [[{"naam": "Volodymyr Zelensky", "soort": "persoon"}, {"naam": "Florida", "soort": "plaats"}], []]


def test_a_missing_or_a_double_number_counts_for_nothing():
    uit = nm.lees_namen(_antwoord((1, [("A B", "persoon")]), (1, [("C D", "persoon")]), (3, []), (9, [])), 4)
    assert uit == [None, None, [], None]
    for kapot in ("kapot", None, json.dumps({"antwoorden": "x"}), json.dumps([1])):
        assert nm.lees_namen(kapot, 2) == [None, None]


def test_an_unknown_kind_a_double_name_and_a_sixth_name_are_dropped():
    namen = [("World Health Organization", "organisatie"), ("world  health organization", "organisatie"),
             ("Masks", "ding"), ("A1", "plaats"), ("B2", "plaats"), ("C3", "plaats"), ("D4", "plaats"), ("E5", "plaats")]
    uit = nm.lees_namen(_antwoord((1, namen)), 1)[0]
    assert [n["naam"] for n in uit] == ["World Health Organization", "A1", "B2", "C3", "D4"]


def test_a_name_is_cleaned_of_hidden_direction_marks_and_an_empty_or_endless_name_is_dropped():
    vijandig = "‮Evil‬  Name‏"
    uit = nm.lees_namen(_antwoord((1, [(vijandig, "persoon"), ("  ", "persoon"), ("x" * 200, "plaats"),
                                       ("1234", "plaats"), ("<script>alert(1)</script>", "organisatie")])), 1)[0]
    assert [n["naam"] for n in uit] == ["Evil Name", "<script>alert(1)</script>"]    # tekst blijft tekst; de site ontsnapt


def test_the_key_of_a_name_ignores_case_and_spacing_and_keeps_every_script():
    assert nm.sleutel("  Narendra   MODI ") == nm.sleutel("narendra modi")
    assert nm.sleutel("नरेंद्र मोदी") != nm.sleutel("नरेंद्र मोद")
    assert nm.sleutel("São Paulo") != nm.sleutel("Sao Paulo")              # een accent is geen spelfout


# --- tellen ----------------------------------------------------------------------------------------------------------

def _rij(nummer, *namen):
    return {"nummer": nummer, "namen": [{"naam": n, "soort": s} for n, s in namen]}


def test_spellings_of_one_name_count_together_and_a_page_counts_once():
    rijen = [_rij("a", ("Donald Trump", "persoon")), _rij("b", ("donald trump", "persoon")),
             _rij("b", ("Donald Trump", "persoon")),                             # dezelfde pagina twee keer gelezen
             _rij("c", ("Donald Trump", "organisatie")), {"nummer": "d", "namen": None}]
    tel = nm.tel(rijen)
    t = tel[nm.sleutel("Donald Trump")]
    assert t["naam"] == "Donald Trump" and t["soort"] == "persoon" and t["paginas"] == ["a", "b", "c"]


# --- Wikidata --------------------------------------------------------------------------------------------------------

ZOEK = {"search": [
    {"id": "Q1428", "label": "Georgia", "description": "state of the United States of America"},
    {"id": "Q378694", "label": "Georgia", "description": "female given name"},
    {"id": "Q230", "label": "Georgia", "description": "country in the Caucasus region"},
    {"id": "P31", "label": "instance of"}, {"id": "Q5x", "label": "kapot"}, {"label": "zonder nummer"},
    {"id": "Q785035", "label": "Province of Georgia"},
    {"id": "Q1", "label": "een"}, {"id": "Q2", "label": "twee"}, {"id": "Q3", "label": "drie"}]}


def test_candidates_are_items_with_a_number_and_five_at_most():
    k = nm.kandidaten_uit(ZOEK)
    assert [x["nummer"] for x in k] == ["Q1428", "Q378694", "Q230", "Q785035", "Q1"]
    assert k[0] == {"nummer": "Q1428", "naam": "Georgia", "omschrijving": "state of the United States of America"}
    assert k[3]["omschrijving"] == ""
    assert nm.kandidaten_uit({"error": {"code": "maxlag"}}) == [] and nm.kandidaten_uit(None) == []


WIKI = {"query": {
    "normalized": [{"from": "georgia (country)", "to": "Georgia (country)"}, {"from": "stalin", "to": "Stalin"}],
    "redirects": [{"from": "Lula da Silva", "to": "Luiz Inácio Lula da Silva"}, {"from": "Stalin", "to": "Joseph Stalin"}],
    "pages": [{"title": "Bestaat Niet", "missing": True}, {"title": "X <y>", "invalid": True},
              {"title": "Joseph Stalin", "pageprops": {"wikibase_item": "Q855"}},
              {"title": "Georgia (country)", "pageprops": {"wikibase_item": "Q230"}},
              {"title": "Luiz Inácio Lula da Silva", "pageprops": {"wikibase_item": "Q37181"}},
              {"title": "Georgia", "pageprops": {"disambiguation": "", "wikibase_item": "Q4962"}},
              {"title": "Zonder Nummer"}, {"title": "Kapot Nummer", "pageprops": {"wikibase_item": "P31"}}]}}


def test_a_title_follows_its_redirect_to_a_number_and_a_disambiguation_page_is_no_answer():
    gevraagd = ["georgia (country)", "Lula da Silva", "stalin", "Georgia", "Bestaat Niet", "X <y>", "Zonder Nummer",
                "Joseph Stalin", "Kapot Nummer", "Niet In Het Antwoord"]
    assert nm.titels_uit(WIKI, gevraagd) == {"georgia (country)": "Q230", "Lula da Silva": "Q37181", "stalin": "Q855",
                                             "Joseph Stalin": "Q855"}
    assert nm.titels_uit(None, ["x"]) == {} and nm.titels_uit({"error": {"code": "maxlag"}}, ["x"]) == {}


def test_a_candidate_from_an_item_carries_its_english_name_and_description():
    item = {"id": "Q230", "labels": {"en": {"value": "Georgia"}, "nl": {"value": "Georgië"}},
            "descriptions": {"en": {"value": "country in the Caucasus"}}}
    assert nm.kandidaat_van(item) == {"nummer": "Q230", "naam": "Georgia", "omschrijving": "country in the Caucasus"}
    assert nm.kandidaat_van({"id": "Q1", "labels": {"mul": {"value": "Ada"}}}) == {"nummer": "Q1", "naam": "Ada", "omschrijving": ""}
    for kapot in ({"id": "Q1", "missing": ""}, {"id": "Q1", "labels": {}}, {"id": "P31", "labels": {"en": {"value": "x"}}}, None):
        assert nm.kandidaat_van(kapot) is None


def test_what_is_kept_of_an_item_is_enough_for_its_traits_and_nothing_more():
    item = {"id": "Q230", "labels": {"en": {"value": "Georgia"}}, "aliases": {"en": [{"value": "Sakartvelo"}]},
            "descriptions": {"en": {"value": "country"}, "nl": {"value": "land"}},
            "sitelinks": {"enwiki": {"title": "Georgia (country)", "badges": []}, "nlwiki": {"title": "Georgië"}, "kawiki": {}},
            "claims": {"P31": []}, "lastrevid": 1}
    klein = nm.compact(item)
    assert set(klein) == {"id", "labels", "aliases", "descriptions", "sitelinks"} and klein["sitelinks"] == {"enwiki": {}, "nlwiki": {}, "kawiki": {}}
    assert nm.kenmerken(klein, [])["wikis"] == 3 and nm.kandidaat_van(klein)["omschrijving"] == "country"


def test_only_wikipedias_count_as_languages():
    links = {"enwiki": {}, "nlwiki": {}, "be_x_oldwiki": {}, "simplewiki": {}, "zh_min_nanwiki": {},
             "commonswiki": {}, "specieswiki": {}, "metawiki": {}, "wikidatawiki": {}, "enwikiquote": {},
             "nlwikinews": {}, "enwikisource": {}, "mediawikiwiki": {}, "sourceswiki": {}}
    assert nm.wikis_van(links) == 5
    assert nm.wikis_van({}) == 0 and nm.wikis_van(None) == 0


def test_the_traits_of_an_item_are_its_names_its_wikipedias_and_whether_it_is_a_human():
    entiteit = {"labels": {"en": {"value": "Georgia"}, "nl": {"value": "Georgië"}, "de": {"value": "Georgien"}},
                "aliases": {"en": [{"value": "Republic of Georgia"}, {"value": "Sakartvelo"}], "nl": [{"value": "Georgië"}]},
                "sitelinks": {"enwiki": {}, "nlwiki": {}, "dewiki": {}, "commonswiki": {}}}
    k = nm.kenmerken(entiteit, ["Q6256", "Q3624078"])
    assert k == {"namen": {"en": "Georgia", "nl": "Georgië", "de": "Georgien", "es": "Georgia", "fr": "Georgia"},
                 "vormen": ["Georgia", "Georgien", "Georgië", "Republic of Georgia", "Sakartvelo"],
                 "wikis": 3, "mens": False, "weg": False, "zonder_soort": False}
    assert nm.kenmerken({"labels": {"en": {"value": "Ada"}}, "sitelinks": {}}, ["Q5"])["mens"] is True
    assert nm.kenmerken({"labels": {"en": {"value": "Georgia"}}, "sitelinks": {}}, ["Q11879590"])["weg"] is True
    assert nm.kenmerken({"labels": {"nl": {"value": "Alleen Nederlands"}}, "sitelinks": {}}, []) is None   # geen Engelse naam
    assert nm.kenmerken({"missing": ""}, []) is None


def test_a_thing_an_event_or_a_law_is_never_a_name_whatever_the_model_called_it():
    leeg = {"labels": {"en": {"value": "x"}}, "sitelinks": {}}
    # een gifstof, een verdrag, een wet, een aanslag, een godsdienst, een toernooi: geen organisatie en geen plaats
    for klasse in ("Q56256173", "Q131569", "Q476068", "Q2223653", "Q6957341", "Q34542827", "Q159535", "Q134808"):
        assert nm.kenmerken(leeg, [klasse])["weg"] is True, klasse
    assert nm.kenmerken(leeg, ["Q7278"])["weg"] is False                     # een politieke partij wel
    # een algemeen begrip ("verkiezingscommissie", "ministerie van defensie") heeft bij Wikidata geen soort
    zonder = nm.kenmerken(leeg, [])
    assert zonder["zonder_soort"] is True and not nm.soort_past("organisatie", zonder) and not nm.soort_past("plaats", zonder)


def test_a_person_must_be_a_human_and_anything_else_must_not_be():
    mens = {"mens": True, "weg": False}
    ding = {"mens": False, "weg": False}
    assert nm.soort_past("persoon", mens) and not nm.soort_past("persoon", ding)
    assert nm.soort_past("organisatie", ding) and nm.soort_past("plaats", ding)
    assert not nm.soort_past("organisatie", mens) and not nm.soort_past("plaats", mens)
    assert not nm.soort_past("plaats", {"mens": False, "weg": True})          # een doorverwijspagina of een voornaam


# --- staat de naam er ook ---------------------------------------------------------------------------------------------

def test_a_person_is_named_when_a_part_of_the_name_is_written():
    trump = ["Donald Trump", "Donald John Trump"]
    assert nm.genoemd(["Trump's lawyers said the vote was stolen"], trump, delen=["Donald Trump"])
    assert nm.genoemd(["won't speak, says #ArvindKejriwal"], ["Arvind Kejriwal"], delen=["Arvind Kejriwal"])   # in een hashtag
    assert nm.genoemd(["Xi says the West is finished"], ["Xi Jinping"], delen=["Xi Jinping"])                  # een korte naam
    assert nm.genoemd(["【錯誤】蔡當局當街燒死疫情患者", "the Tsai authorities burned patients"], ["Tsai Ing-wen"],
                      delen=["Tsai Ing-wen"])
    # een andere schrijfwijze die Wikidata kent, telt als zij er in haar geheel staat: een roepnaam, een bijnaam
    assert nm.genoemd(["E agora, Xandão?"], ["Alexandre de Moraes", "Xandão"], delen=["Alexandre de Moraes"])


def test_a_title_or_a_word_from_a_description_is_not_a_part_of_a_name():
    # Wikidata kent bij een persoon ook omschrijvingen als andere schrijfwijze ("Minister Barroso", "53rd President of
    # the Superior Electoral Court"). Een woord daaruit is geen naam: alleen de delen van de naam zelf tellen.
    barroso = ["Luís Roberto Barroso", "Minister Barroso", "53rd President of the Superior Electoral Court of Brazil"]
    assert not nm.genoemd(["The president of the court said so"], barroso, delen=["Luís Roberto Barroso"])
    assert nm.genoemd(["he ended up as an advisor to Barroso"], barroso, delen=["Luís Roberto Barroso"])
    # ook in de naam zelf is een titel geen naam: "the pope" is niet per se deze paus
    assert not nm.genoemd(["The pope visited Gaza"], ["Pope Francis"], delen=["Pope Francis"])
    assert nm.genoemd(["Francis visited Gaza"], ["Pope Francis"], delen=["Pope Francis"])
    assert not nm.genoemd(["The queen opened parliament"], ["Queen Camilla"], delen=["Queen Camilla"])
    assert not nm.genoemd(["Prince of darkness"], ["Prince Harry, Duke of Sussex"], delen=["Prince Harry, Duke of Sussex"])


def test_a_person_worked_out_from_a_role_is_not_named():
    bewering = "“ZÉ GATINHA”, governador da Bahia apresenta mascote Trans para incentivar vacinação"
    costa = ["Rui Costa", "Rui Costa dos Santos"]
    assert not nm.genoemd([bewering, "the governor of Bahia unveils a trans mascot"], costa, delen=costa)
    fuente = ["Luis de la Fuente"]
    assert not nm.genoemd(["La hija de la presidenta"], fuente, delen=fuente)          # een lidwoord telt nooit
    assert not nm.genoemd([], ["Donald Trump"], delen=["Donald Trump"]) and not nm.genoemd(["x"], [], delen=[])


def test_an_organisation_or_a_place_needs_its_name_or_another_known_form_in_full():
    bjp = ["Bharatiya Janata Party", "BJP"]
    assert nm.genoemd(["BJP MP visited a dargah"], bjp)
    assert not nm.genoemd(["Party workers beat a policeman"], bjp)        # "Party" alleen is niet de naam
    assert nm.genoemd(["A Ugandan businessman was arrested"], ["Uganda"])  # een lange vorm mag in een woord
    assert not nm.genoemd(["A French court ruled"], ["France"])
    assert not nm.genoemd(["The US army"], ["Russia", "RU"])               # een korte vorm alleen als los woord
    assert not nm.genoemd(["a hole ten metres in diameter"], ["India"])     # nooit over twee woorden heen


def test_pairs_whose_name_is_not_written_fall_away_before_the_counting():
    geteld = {nm.sleutel("Rui Costa"): {"naam": "Rui Costa", "soort": "persoon", "paginas": ["a", "b"]},
              nm.sleutel("Onbekend"): {"naam": "Onbekend", "soort": "persoon", "paginas": ["a"]}}
    keuzes = {nm.sleutel("Rui Costa"): "Q1", nm.sleutel("Onbekend"): ""}
    wikidata = {"Q1": {"vormen": ["Rui Costa", "Governor of Bahia"], "namen": {"en": "Rui Costa"}, "mens": True}}
    teksten = {"a": ["governador da Bahia"], "b": ["Rui Costa disse", "Rui Costa said"]}
    uit, weg = nm.houd_genoemd(geteld, keuzes, wikidata, teksten)
    assert uit[nm.sleutel("Rui Costa")]["paginas"] == ["b"] and weg == 1
    assert uit[nm.sleutel("Onbekend")]["paginas"] == ["a"]                 # zonder nummer valt hij later toch af


# --- de keuze tussen kandidaten --------------------------------------------------------------------------------------

def test_the_choice_shows_the_candidates_and_claims_and_offers_none():
    k = nm.kandidaten_uit(ZOEK)[:3]
    p = nm.keuzeverzoek("Georgia", "plaats", k, ["Georgia election officials found 5,000 fake ballots " * 20,
                                                 "Trump won Georgia", "Atlanta, Georgia", "een vierde"])
    tekst = p["messages"][0]["content"][0]["text"]
    assert "1. Q1428: Georgia (state of the United States of America)" in tekst and "3. Q230" in tekst
    assert "Trump won Georgia" in tekst and "een vierde" not in tekst and len(tekst) < 1500
    assert "private" in p["system"].lower()


def test_every_choice_uses_the_same_answer_form_whatever_the_candidates():
    # Een eigen schema per naam loopt bij de aanbieder tegen een grens aan (vijftig nieuwe schema's per minuut):
    # het antwoord is daarom de plek in de lijst, niet het nummer van Wikidata.
    een = nm.keuzeverzoek("Georgia", "plaats", nm.kandidaten_uit(ZOEK)[:1], ["x"])
    vijf = nm.keuzeverzoek("Florida", "plaats", nm.kandidaten_uit(ZOEK), ["y"])
    assert een["output_config"] == vijf["output_config"]
    assert een["output_config"]["format"]["schema"]["properties"]["keuze"]["enum"] == ["1", "2", "3", "4", "5", "geen"]


def test_a_choice_outside_the_candidates_counts_for_nothing():
    k = nm.kandidaten_uit(ZOEK)[:3]
    assert nm.lees_keuze(json.dumps({"keuze": "3"}), k) == "Q230" and nm.lees_keuze(json.dumps({"keuze": "1"}), k) == "Q1428"
    assert nm.lees_keuze(json.dumps({"keuze": "geen"}), k) == ""
    for kapot in (json.dumps({"keuze": "4"}), json.dumps({"keuze": "0"}), json.dumps({"keuze": "Q230"}), "kapot", None,
                  json.dumps(["3"])):
        assert nm.lees_keuze(kapot, k) is None                      # de vierde plek is leeg: er waren drie kandidaten


# --- welke namen op de site mogen ------------------------------------------------------------------------------------

def _wd(**extra):
    return {"namen": {t: "Naam" for t in ("en", "nl", "de", "es", "fr")}, "wikis": 40, "mens": True, "weg": False, **extra}


def _geteld(naam, soort, paginas):
    return {nm.sleutel(naam): {"naam": naam, "soort": soort, "paginas": paginas}}


def test_a_name_gets_on_the_site_with_a_number_enough_pages_and_enough_wikipedias():
    geteld = _geteld("Volodymyr Zelensky", "persoon", ["a", "b", "c", "d", "e"])
    uit = nm.stel_samen(geteld, {nm.sleutel("Volodymyr Zelensky"): "Q3874799"}, {"Q3874799": _wd()},
                        {p: {"r1", "r2"} for p in "abcde"})
    assert uit["namen"] == {"Q3874799": {"soort": "persoon", "namen": _wd()["namen"], "wikis": 40,
                                         "paginas": ["a", "b", "c", "d", "e"]}}
    assert uit["afgevallen"] == {}


def test_spellings_that_point_to_one_number_count_together():
    geteld = {**_geteld("Zelensky", "persoon", ["a", "b"]), **_geteld("Volodymyr Zelensky", "persoon", ["b", "c", "d", "e"])}
    keuzes = {nm.sleutel("Zelensky"): "Q3874799", nm.sleutel("Volodymyr Zelensky"): "Q3874799"}
    uit = nm.stel_samen(geteld, keuzes, {"Q3874799": _wd()}, {p: {"r1", "r2"} for p in "abcde"})
    assert uit["namen"]["Q3874799"]["paginas"] == ["a", "b", "c", "d", "e"]


@pytest.mark.parametrize("wat, reden", [
    ({"paginas": ["a", "b", "c", "d"]}, "paginas"),                           # vier pagina's: te weinig
    ({"wd": {"wikis": 2}}, "wikis"),                                          # twee talen van Wikipedia
    ({"redacties": {"r1"}}, "redacties"),                                     # een persoon bij één redactie
    ({"wd": {"mens": False}}, "soort"),                                       # het model zei persoon, Wikidata niet
    ({"wd": {"weg": True, "mens": False}, "soort": "plaats"}, "soort"),       # een doorverwijspagina
    ({"keuze": ""}, "geen-nummer"),                                           # het model koos geen kandidaat
    ({"keuze": None}, "geen-nummer"),                                         # niet opgezocht
    ({"niet": {"Q7"}}, "weggehaald"),                                         # een mens haalde de naam weg
])
def test_a_name_that_fails_one_rule_is_nowhere(wat, reden):
    paginas = wat.get("paginas", ["a", "b", "c", "d", "e"])
    geteld = _geteld("Iemand", wat.get("soort", "persoon"), paginas)
    keuzes = {nm.sleutel("Iemand"): wat.get("keuze", "Q7")}
    uit = nm.stel_samen(geteld, keuzes, {"Q7": _wd(**wat.get("wd", {}))},
                        {p: wat.get("redacties", {"r1", "r2"}) for p in paginas}, niet=wat.get("niet", frozenset()))
    assert uit["namen"] == {} and uit["afgevallen"] == {reden: 1}


def test_an_organisation_needs_no_second_newsroom_but_a_person_does():
    geteld = _geteld("Acme", "organisatie", ["a", "b", "c", "d", "e"])
    uit = nm.stel_samen(geteld, {nm.sleutel("Acme"): "Q9"}, {"Q9": _wd(mens=False)}, {p: {"r1"} for p in "abcde"})
    assert list(uit["namen"]) == ["Q9"]


def test_the_kind_of_a_number_is_what_most_pages_say():
    geteld = {**_geteld("Kremlin", "plaats", ["a", "b", "c"]), **_geteld("The Kremlin", "organisatie", ["d", "e", "f", "g"])}
    keuzes = {nm.sleutel("Kremlin"): "Q9", nm.sleutel("The Kremlin"): "Q9"}
    uit = nm.stel_samen(geteld, keuzes, {"Q9": _wd(mens=False)}, {p: {"r1"} for p in "abcdefg"})
    assert uit["namen"]["Q9"]["soort"] == "organisatie" and len(uit["namen"]["Q9"]["paginas"]) == 7


def test_the_list_of_removed_names_is_read_strictly(tmp_path):
    pad = tmp_path / "niet.json"
    assert nm.niet_lijst(pad) == frozenset()                                   # geen bestand: niemand weggehaald
    pad.write_text(json.dumps({"namen": [{"nummer": "Q42", "reden": "verzoek, 2026-11-12"}]}), encoding="utf-8")
    assert nm.niet_lijst(pad) == frozenset({"Q42"})
    for kapot in ({"namen": [{"nummer": "42", "reden": "x"}]}, {"namen": [{"nummer": "Q42"}]}, {"namen": "Q42"}, []):
        pad.write_text(json.dumps(kapot), encoding="utf-8")
        with pytest.raises(nm.Weigering):
            nm.niet_lijst(pad)


# --- de poort van de PO ----------------------------------------------------------------------------------------------

AKKOORD = '2026-11-12, PO: "computer is beter hier in vinden van namen, akkoord zoals het is"'


def _lezing(tmp_path, labels, door="PO", akkoord=None):
    pad = tmp_path / "po.json"
    pad.write_text(json.dumps({"gelezen_door": door, "labels": labels, **({"akkoord": akkoord} if akkoord else {})}),
                   encoding="utf-8")
    return pad


def test_the_gate_is_closed_until_the_po_has_read(tmp_path):
    assert nm.poort(tmp_path / "ontbreekt.json")[0] is False
    goed = {str(i): "goed" for i in range(60)}
    assert nm.poort(_lezing(tmp_path, goed, door="Claude"))[0] is False
    assert nm.poort(_lezing(tmp_path, goed))[0] is True                       # 60 zonder fout draagt 90%
    assert nm.poort(_lezing(tmp_path, {str(i): "goed" for i in range(20)}))[0] is False


def test_one_private_person_closes_the_gate_whatever_the_rest(tmp_path):
    labels = {str(i): "goed" for i in range(199)} | {"x": "prive"}
    open_, waarom = nm.poort(_lezing(tmp_path, labels))
    assert open_ is False and "privé" in waarom


def test_a_reading_by_claude_opens_the_gate_only_with_the_recorded_approval_of_the_po(tmp_path):
    # SPECS E9.S11 AC3, gewijzigd door de PO op 2026-11-12: Claude leest, haar akkoord staat erbij met haar woorden.
    labels = {str(i): "goed" for i in range(190)} | {f"f{i}": "fout" for i in range(10)}
    assert nm.poort(_lezing(tmp_path, labels, door="Claude"))[0] is False
    open_, waarom = nm.poort(_lezing(tmp_path, labels, door="Claude", akkoord=AKKOORD))
    assert open_ is True and "Claude" in waarom and "akkoord van de PO" in waarom
    for kapot in ("ja", 'PO: "akkoord"', '2026-13-40, PO: "akkoord"', '2026-11-12, Claude: "akkoord"', '2026-11-12, PO: ""'):
        assert nm.poort(_lezing(tmp_path, labels, door="Claude", akkoord=kapot))[0] is False, kapot


def test_an_approval_without_a_reading_opens_nothing_and_does_not_lower_the_bar(tmp_path):
    assert nm.poort(_lezing(tmp_path, {}, door="Claude", akkoord=AKKOORD))[0] is False
    te_weinig = {str(i): "goed" for i in range(170)} | {f"f{i}": "fout" for i in range(30)}
    assert nm.poort(_lezing(tmp_path, te_weinig, door="Claude", akkoord=AKKOORD))[0] is False
    prive = {str(i): "goed" for i in range(199)} | {"x": "prive"}
    open_, waarom = nm.poort(_lezing(tmp_path, prive, door="Claude", akkoord=AKKOORD))
    assert open_ is False and "privé" in waarom


def test_doubt_and_errors_count_as_read_and_not_good(tmp_path):
    labels = {str(i): "goed" for i in range(170)} | {f"f{i}": "fout" for i in range(15)} | {f"t{i}": "twijfel" for i in range(15)}
    assert nm.poort(_lezing(tmp_path, labels))[0] is False                    # 170 van 200
    labels = {str(i): "goed" for i in range(185)} | {f"f{i}": "fout" for i in range(15)}
    assert nm.poort(_lezing(tmp_path, labels))[0] is True                     # 185 van 200


# --- de leesronde van de PO ------------------------------------------------------------------------------------------

def _samen():
    namen = {"Q1": {"soort": "persoon", "namen": {"en": "Ada Lovelace", "nl": "Ada Lovelace"}, "wikis": 90,
                    "paginas": ["a", "b", "c", "d", "e"]},
             "Q2": {"soort": "plaats", "namen": {"en": "Georgia", "nl": "Georgië"}, "wikis": 200,
                    "paginas": ["a", "f", "g", "h", "i"]}}
    return {"namen": namen, "afgevallen": {}}


def test_cards_for_the_po_show_each_name_once_with_a_claim_she_can_read():
    paginas = {p: (f"claim {p}", "en") for p in "abcdefghi"} | {"e": ("دعوى", "ar"), "i": ("Behauptung", "de")}
    kaarten = nm.po_kaarten(_samen(), paginas, {"e": "a claim in Arabic"}, {"Q1": "English mathematician", "Q2": "country"}, n=10)
    assert sorted(k["nummer"] for k in kaarten) == ["Q1", "Q2"]              # elke naam hoogstens één keer
    for k in kaarten:
        assert k["id"] == f'{k["pagina"]}-{k["nummer"]}' and k["pagina"] != "i"   # Duits zonder vertaling leest zij niet
        assert k["soort"] in ("persoon", "organisatie", "plaats") and k["omschrijving"]
        if k["taal"] == "ar":
            assert k["richting"] == "rtl" and k["vertaling"] == "a claim in Arabic"
    assert nm.po_kaarten(_samen(), paginas, {}, {}, n=10) == nm.po_kaarten(_samen(), paginas, {}, {}, n=10)   # vast zaad


def test_a_later_choice_replaces_an_earlier_one_and_a_withdrawn_choice_is_no_choice():
    rijen = [{"sleutel": "china", "keuze": "Q29520"}, {"sleutel": "india", "keuze": "Q668"}, {"sleutel": "x", "keuze": None},
             {"sleutel": "china", "keuze": None},                              # opnieuw opgezocht: de oude keuze vervalt
             {"sleutel": "india", "keuze": "Q668"}, {"sleutel": "georgia", "keuze": ""}]
    assert nm.geldende_keuzes(rijen) == {"india": "Q668", "georgia": ""}
    assert nm.geldende_keuzes(rijen + [{"sleutel": "china", "keuze": "Q148"}])["china"] == "Q148"


def test_what_the_po_chose_becomes_labels_and_a_private_person_is_its_own_label():
    kaarten = [{"id": f"p{i}-Q{i}"} for i in range(6)]
    keuzes = {"p0-Q0": {"oordeel": "goed"}, "p1-Q1": {"oordeel": "fout", "mis": ["verkeerde"]},
              "p2-Q2": {"oordeel": "fout", "mis": ["prive", "verkeerde"], "opmerking": "een buurman"},
              "p3-Q3": {"opmerking": "weet ik niet"}, "p4-Q4": {"oordeel": "fout"}}
    uit = nm.po_uitslag(kaarten, keuzes)
    assert uit["labels"] == {"p0-Q0": "goed", "p1-Q1": "fout", "p2-Q2": "prive", "p3-Q3": "twijfel", "p4-Q4": "fout"}
    assert uit["opmerkingen"] == {"p2-Q2": "een buurman", "p3-Q3": "weet ik niet"}
    assert uit["mis"] == {"niet-genoemd": 0, "verkeerde": 2, "prive": 1}


def test_the_reading_page_carries_the_cards_and_cannot_be_broken_out_of():
    html = nm.po_pagina([{"id": "a-Q1", "bewering": "</script><script>alert(1)</script>", "naam": "Ada"}])
    assert "</script><script>alert(1)" not in html and "<\\/script>" in html and '"a-Q1"' in html


# --- geld ------------------------------------------------------------------------------------------------------------

def test_a_round_that_would_pass_the_limit_does_not_start():
    nm.binnen_grens(1.0, 4.9)
    with pytest.raises(nm.Weigering):
        nm.binnen_grens(1.2, 4.9)
