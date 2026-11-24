"""Zoeken voorop (PLAN #33.6c, SPECS E9.S12, DESIGN §4v): de startpagina is het zoekveld met het archief eronder; filters
met tellingen en meer keuzes tegelijk; sorteren boven de lijst; treffers die laten zien waarom ze er staan. De gegevens
daarvan komen uit het platform; het zoekveld en het formulier bouwt de site (B76)."""

from urllib.parse import urlencode

import pytest

from factiz_site import app as fa
from factiz_site import i18n
from tests.test_factiz_dossiers import _site
from tests.test_factiz_namen import _site as _site_namen


def _hrefs(r):
    return [rij["href"] for rij in r.json()["rijen"]]


def _groep(gegevens, soort):
    """De aangevinkte waarden van een filter met vinkjes, en alle waarden die het toont."""
    alle = next((g["boven"] + g["meer"] for g in gegevens["filters"]["groepen"] if g["soort"] == soort), [])
    return [k["waarde"] for k in alle if k["aan"]], [k["waarde"] for k in alle]


def _zoek(client, vraag, site="en", **velden):
    return client.post(f"/api/{site}/zoek", data={"q": vraag, **velden})


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    return _site(tmp_path_factory)


@pytest.fixture(scope="module")
def met_namen(tmp_path_factory):
    return _site_namen(tmp_path_factory)


# --- de startpagina: het archief zelf -----------------------------------------------------------------------------------

@pytest.mark.parametrize("taal, tekst", [("en", "Search 6 fact-checks"), ("nl", "Zoek in 6 factchecks"),
                                         ("de", "6 Faktenchecks durchsuchen")])
def test_the_first_page_counts_the_fact_checks_for_the_label_of_its_search_field(site, taal, tekst):
    client, _ = site
    tellingen = client.get(f"/api/{taal}/archief").json()["tellingen"]
    assert i18n.tekst(taal, "held_label", n=tellingen["paginas"]) == tekst


def test_the_first_page_is_the_archive_itself_with_its_filters_its_order_and_the_newest_fact_checks(site):
    client, n = site
    g = client.get("/api/nl/archief").json()
    assert _hrefs(client.get("/api/nl/archief"))[:2] == [f"/nl/fact-checks/{n['hindi']}/", f"/nl/fact-checks/{n['villa']}/"]
    assert ("Oudste eerst", "/nl/fact-checks/?sorteer=oud") in [(v["naam"], v["url"]) for v in g["filters"]["volgordes"]]
    assert "/nl/dossiers/zelensky-luxury/" in [d["href"] for d in g["dossiers"]]       # de dossiers staan er nog
    assert g["aantal"] == "6 factchecks"


# --- meer keuzes tegelijk ---------------------------------------------------------------------------------------------

def test_a_filter_with_boxes_takes_several_values_and_shows_either(site):
    client, n = site
    alle = {f"/fact-checks/{v}/" for v in n.values()}
    assert set(_hrefs(client.get("/api/en/archief?taal=hi"))) == {f"/fact-checks/{n['hindi']}/"}
    beide = client.get("/api/en/archief?taal=en&taal=hi")
    assert beide.status_code == 200 and set(_hrefs(beide)) == alle
    assert sorted(_groep(beide.json(), "taal")[0]) == ["en", "hi"]
    # elk gekozen stuk is los weg te halen
    stukjes = client.get("/api/nl/archief?taal=en&taal=hi").json()["filters"]["stukjes"]
    assert [(s["kop"], s["naam"], s["url"]) for s in stukjes] == [("Taal", "Engels", "/nl/fact-checks/?taal=hi"),
                                                                   ("Taal", "Hindi", "/nl/fact-checks/?taal=en")]
    # jaren en oordelen net zo, en samen met een ander filter is het "en"
    jaren = client.get("/api/en/archief?jaar=2021&jaar=2023")
    assert set(_hrefs(jaren)) == {f"/fact-checks/{n['los']}/", f"/fact-checks/{n['jacht']}/"}
    assert _hrefs(client.get("/api/en/archief?jaar=2021&jaar=2023&thema=health")) == [f"/fact-checks/{n['los']}/"]


def _een_adres(client, vraag):
    """Het ene adres van de lijst die de gegevens bij deze vraag beschrijven: hun filters op alfabet."""
    r = client.get(f"/api/en/archief?{vraag}")
    assert r.status_code == 200, vraag
    paren = [tuple(paar) for paar in r.json()["paren"]]
    return "/fact-checks/" + (f"?{urlencode(paren)}" if paren else "")


def test_the_address_of_several_values_is_one_address(site):
    client, _ = site
    # één vaste volgorde
    for vraag, doel in (("taal=hi&taal=en", "/fact-checks/?taal=en&taal=hi"), ("taal=en&taal=en", "/fact-checks/?taal=en"),
                        ("taal=en&taal=", "/fact-checks/?taal=en"),
                        ("jaar=2024&jaar=2024&jaar=2021", "/fact-checks/?jaar=2021&jaar=2024")):
        assert _een_adres(client, vraag) == doel, vraag
    assert fa.lijst_url("en", {"taal": ("en", "hi")}) == "/fact-checks/?taal=en&taal=hi"
    for fout in ("?taal=en&taal=xx", "?thema=war&thema=health", "?land=UA&land=IN"):
        assert client.get("/api/en/archief" + fout).status_code == 404, fout   # een waarde die niet bestaat; een filter met één keuze


# --- tellingen bij de filters -----------------------------------------------------------------------------------------

def test_every_filter_value_counts_what_it_would_show_and_a_value_that_shows_nothing_is_not_offered(site):
    client, _ = site
    g = client.get("/api/nl/archief?thema=war").json()                     # één factcheck: de villa (Engels, 2024, Oekraïne)
    aan, alle = _groep(g, "taal")
    assert aan == [] and alle == ["en"]                                     # Hindi zou hier niets tonen
    taal = next(gr for gr in g["filters"]["groepen"] if gr["soort"] == "taal")["boven"][0]
    assert (taal["naam"], taal["aantal"]) == ("Engels", "1")
    assert _groep(g, "jaar")[1] == ["2024"]
    assert [k["waarde"] for k in g["filters"]["lijsten"]["redactie"]] == ["AFP", "Snopes"]
    assert [k["waarde"] for k in g["filters"]["lijsten"]["land"]] == ["UA"]
    # zonder filter: alles, met de aantallen van het hele archief
    alles = client.get("/api/nl/archief").json()
    assert _groep(alles, "taal")[1] == ["en", "hi"]
    assert next(gr for gr in alles["filters"]["groepen"] if gr["soort"] == "taal")["boven"][0]["aantal"] == "5"


def test_a_filter_does_not_count_itself_so_a_second_value_can_be_added(site):
    client, _ = site
    g = client.get("/api/nl/archief?taal=hi").json()
    aan, alle = _groep(g, "taal")
    assert aan == ["hi"] and alle == ["en", "hi"]                           # Engels staat er nog, met wat het erbij zou geven
    assert _groep(g, "jaar")[1] == ["2024"]                                 # de andere filters tellen binnen het Hindi
    # een gekozen waarde blijft staan, ook als zij met de rest niets meer toont
    leeg = client.get("/api/nl/archief?jaar=2021&taal=hi").json()
    assert _groep(leeg, "taal")[0] == ["hi"] and _groep(leeg, "jaar")[0] == ["2021"]


def test_verdict_language_and_year_are_boxes_and_the_long_ones_are_lists_and_the_order_is_kept(site):
    client, _ = site
    f = client.get("/api/nl/archief?sorteer=oud&thema=war").json()["filters"]
    assert [g["soort"] for g in f["groepen"]] == ["oordeel", "taal", "jaar"]
    assert f["velden"] == ["thema", "onderdeel", "land", "redactie"]
    assert f["sorteer"] == "oud" and ["sorteer", "oud"] in f["alles"]       # het formulier houdt de volgorde vast


# --- sorteren boven de lijst ------------------------------------------------------------------------------------------

def test_the_order_stands_above_the_list_as_one_click_and_says_which_one_holds(site):
    client, n = site
    volgordes = client.get("/api/nl/archief?taal=en").json()["filters"]["volgordes"]
    assert [(v["naam"], v["url"], v["aan"]) for v in volgordes] == [
        ("Nieuwste eerst", "/nl/fact-checks/?taal=en", True), ("Oudste eerst", "/nl/fact-checks/?sorteer=oud&taal=en", False),
        ("Meeste redacties", "/nl/fact-checks/?sorteer=redacties&taal=en", False)]           # geen Beste treffer
    oud = client.get("/api/nl/archief?sorteer=oud").json()["filters"]["volgordes"]
    assert [(v["url"], v["aan"]) for v in oud if v["naam"] == "Oudste eerst"] == [("/nl/fact-checks/?sorteer=oud", True)]
    assert _hrefs(client.get("/api/en/archief?sorteer=oud"))[0] == f"/fact-checks/{n['los']}/"


def test_search_sorts_with_the_question_sent_again_and_starts_at_the_best_match(site):
    client, n = site
    f = _zoek(client, "Zelensky bought", "nl", taal="en").json()["filters"]
    # de knoppen sturen de vraag opnieuw met de keuzes die er al zijn
    assert f["alles"] == [["taal", "en"]]
    assert [(v["waarde"], v["naam"], v["aan"]) for v in f["volgordes"]][:1] == [("", "Beste treffer", True)]
    assert ("oud", "Oudste eerst", False) in [(v["waarde"], v["naam"], v["aan"]) for v in f["volgordes"]]
    assert _hrefs(_zoek(client, "Zelensky bought", sorteer="oud"))[0] == f"/fact-checks/{n['jacht']}/"


def _formulier(client, pad, paren):
    """Een formulier zoals de browser het stuurt, met een veld dat meer keer voorkomt."""
    return client.post(pad, content=urlencode(paren), headers={"content-type": "application/x-www-form-urlencoded"})


def test_search_takes_several_values_of_one_filter_too(site):
    client, n = site
    r = _formulier(client, "/api/en/zoek", [("q", "Zelensky bought"), ("taal", "hi"), ("taal", "en")])
    assert len(_hrefs(r)) == 3 and sorted(_groep(r.json(), "taal")[0]) == ["en", "hi"]
    assert _hrefs(_formulier(client, "/api/en/zoek", [("q", "Zelensky bought"), ("jaar", "2023"), ("jaar", "1999")])) == [
        f"/fact-checks/{n['jacht']}/"]                                      # een jaar dat niet bestaat doet niets


# --- zoeken: treffers laten zien waarom --------------------------------------------------------------------------------

def test_search_counts_the_hits_for_the_question(site):
    client, _ = site
    g = _zoek(client, "Zelensky bought", "nl").json()
    assert g["aantal"] == "3 resultaten" and g["totaal"] == 3 and g["gezocht"] and not g["deels"]
    leeg = _zoek(client, "", "nl").json()
    assert leeg["gezocht"] is False and leeg["rijen"] == []


def test_a_hit_marks_the_words_of_the_question(site):
    client, _ = site
    rij = _zoek(client, "villa zelensky").json()["rijen"][0]
    assert rij["stukken"] == [["Zelensky", True], [" bought a ", False], ["villa", True], [" in Florida", False]]
    assert not any("stukken" in r for r in client.get("/api/en/archief").json()["rijen"])   # een lijst zonder vraag markeert niets


def test_marking_ignores_case_and_accents_prefers_whole_words_and_never_changes_the_text():
    assert fa.markeer("Zelenski compró una villa", ["COMPRO"]) == [("Zelenski ", False), ("compró", True), (" una villa", False)]
    assert fa.markeer("Indiana and India", ["india"]) == [("Indiana and ", False), ("India", True)]
    assert fa.markeer("Indiana only", ["india"]) == [("India", True), ("na only", False)]      # geen heel woord: het stuk
    assert fa.markeer("ज़ेलेंस्की ने एक कैसीनो खरीदा", ["कैसीनो"]) == [("ज़ेलेंस्की ने एक ", False), ("कैसीनो", True), (" खरीदा", False)]
    assert fa.markeer("villa villa", ["villa", "vill"]) == [("villa", True), (" ", False), ("villa", True)]
    tekst = "<b>villa</b> & 'co'"
    assert "".join(stuk for stuk, _ in fa.markeer(tekst, ["villa", "co"])) == tekst
    assert fa.markeer("niets", []) == [("niets", False)] and fa.markeer("", ["x"]) == []


def test_a_long_claim_is_shown_around_the_word_that_was_found():
    lang = "Eerst een lange aanloop. " * 20 + "Daarna kocht hij een villa in Florida. " + "En nog veel meer tekst erna. " * 10
    stuk = fa.fragment(lang, ["villa"])
    assert stuk.startswith("… ") and "villa in Florida" in stuk and len(stuk) < 260
    kort = "Hij kocht een villa. " + "En nog veel meer tekst erna. " * 20
    assert fa.fragment(kort, ["villa"]).startswith("Hij kocht een villa.")   # staat het woord vooraan, dan gewoon het begin
    assert fa.fragment(lang, ["jacht"]) == fa.fragment(lang, [])             # niet gevonden: gewoon het begin


# --- geen treffer is geen doodlopende weg ------------------------------------------------------------------------------

# --- geen treffer is geen doodlopende weg ------------------------------------------------------------------------------

def test_when_no_fact_check_holds_every_word_the_ones_that_hold_some_are_shown_and_said_to_be_partial(site):
    client, n = site
    g = _zoek(client, "Zelensky eenhoorn", "nl").json()
    assert g["deels"] is True
    assert {r["href"] for r in g["rijen"]} == {f"/nl/fact-checks/{n[k]}/" for k in ("villa", "jacht", "hindi")}
    assert all(["Zelensky", True] in r["stukken"] for r in g["rijen"] if r["tekst"].startswith("Zelensky"))
    assert any(r["stukken"][0] == ["Zelensky", True] for r in g["rijen"])
    # met alle woorden erin gaat het gewoon
    assert _zoek(client, "Zelensky villa", "nl").json()["deels"] is False


def test_nothing_at_all_says_so_and_filters_in_the_way_are_named(site):
    client, _ = site
    niets = _zoek(client, "qqqqq zzzzz", "nl").json()
    assert niets["totaal"] == 0 and niets["rijen"] == [] and niets["zonder_filters"] == "" and niets["gezocht"]
    # de vraag heeft treffers, maar niet binnen het filter: zeg hoeveel het er zonder zijn
    filter_ = _zoek(client, "Zelensky bought", "nl", jaar="2021").json()
    assert filter_["totaal"] == 0 and filter_["zonder_filters"] == "3 resultaten zonder filters."


# --- ingangen: een naam, een thema, een dossier of een redactie die precies zo heet ------------------------------------

def test_a_question_that_is_a_theme_a_dossier_or_a_newsroom_offers_that_way_in(site):
    client, _ = site
    ingangen = lambda vraag: [{k: v for k, v in i.items() if k != "href"} for i in _zoek(client, vraag, "nl").json()["ingangen"]]
    assert ingangen("oorlog en conflict") == [{"soort": "thema", "thema": "war", "naam": "Oorlog en conflict", "aantal": 1}]
    # elke ingang draagt haar adres op de site (#34.2ac)
    assert [i["href"] for i in _zoek(client, "oorlog en conflict", "nl").json()["ingangen"]] == ["/nl/themes/war/"]
    assert ingangen("snopes") == [{"soort": "redactie", "redactie": "Snopes", "naam": "Snopes", "aantal": 4}]
    assert [(i["soort"], i["sleutel"]) for i in ingangen("Zelensky koopt luxe met westers geld")] == [("dossier", "zelensky-luxury")]
    assert ingangen("bought") == []


def test_a_question_that_is_a_name_offers_the_page_of_that_name(met_namen):
    client, _ = met_namen
    florida = _zoek(client, "florida", "nl").json()["ingangen"]
    assert [(i["soort"], i["nummer"], i["naamsoort"], i["naam"]) for i in florida] == [("naam", "Q812", "plaats", "Florida")]
    # een deel van de naam van een persoon is ook genoeg; in de taal van de site
    zelensky = _zoek(client, "Selenskyj", "de").json()["ingangen"]
    assert [(i["nummer"], i["naam"]) for i in zelensky] == [("Q3874799", "Wolodymyr Selenskyj")]
    wie = _zoek(client, "world health organization", "nl").json()["ingangen"]
    assert [(i["nummer"], i["naam"]) for i in wie] == [("Q7817", "Wereldgezondheidsorganisatie")]


def test_a_name_filter_takes_part_in_the_counts(met_namen):
    client, _ = met_namen
    g = client.get("/api/nl/archief?naam=Q812").json()                    # Florida: de villa en de WHO-bewering
    assert _groep(g, "jaar")[1] == ["2024", "2021"]


# --- spelfouten (PLAN #34.2i, Baymard #355, #1001) --------------------------------------------------------------------

def test_a_misspelled_word_without_results_is_corrected_and_the_data_says_so(site):
    client, _ = site
    gegevens = client.post("/api/nl/zoek", data={"q": "zelenksy"}).json()
    assert gegevens["verbeterd"] == "zelensky" and gegevens["totaal"] >= 2 and gegevens["rijen"]


def test_a_search_with_results_or_a_word_that_exists_is_never_corrected(site):
    client, _ = site
    for vraag in ("zelensky", "Zelenska", "bought"):
        assert client.post("/api/nl/zoek", data={"q": vraag}).json()["verbeterd"] is None, vraag


def test_numbers_and_scripts_without_spaces_are_left_alone(site):
    client, _ = site
    for vraag in ("751", "ゼレンスキ", "젤렌스키"):
        assert client.post("/api/nl/zoek", data={"q": vraag}).json()["verbeterd"] is None, vraag


def test_the_search_window_offers_the_corrected_search_first(site):
    client, _ = site
    s = client.post("/api/nl/suggesties", data={"q": "zelenksy"}).json()
    assert s["zoekvragen"][0]["tekst"] == "zelensky" and s["zoekvragen"][0].get("verbeterd") is True
