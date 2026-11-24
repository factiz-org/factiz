"""De interne ingang van het platform voor de proef in Astro (PLAN.md #34.0).

`/api/<taal>/archief` geeft dezelfde lijst, filters, tellingen en volgorde als de start en `/fact-checks/`, met dezelfde
functies, als gegevens. Een andere voorkant mag nooit iets anders tonen dan het platform zelf (M5), en de ingang neemt
geen zoekvraag aan: die gaat nooit in een adres (E9.S6 AC3).
"""

import json

import pytest

from factiz_site import i18n
from tests.test_factiz_dossiers import NAAM, _site
from tests.test_factiz_site import CSP

TALEN = ("en", "nl", "de", "es", "fr")


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    return _site(tmp_path_factory)


def _voor(taal):
    return "" if taal == "en" else f"/{taal}"


@pytest.mark.parametrize("taal", TALEN)
def test_the_archive_as_data_shows_the_newest_first_with_its_count_and_what_each_filter_value_would_show(site, taal):
    client, nr = site
    r = client.get(f"/api/{taal}/archief")
    assert r.status_code == 200 and r.headers["content-type"].startswith("application/json")
    gegevens = r.json()
    # 7 juni 2024, 5 maart 2024, december 2023, maart 2022, 2021; zonder datum achteraan
    volgorde = ("hindi", "villa", "jacht", "biolab", "los", "zonder_datum")
    assert [rij["href"] for rij in gegevens["rijen"]] == [f"{_voor(taal)}/fact-checks/{nr[k]}/" for k in volgorde]
    assert gegevens["aantal"] == i18n.tekst(taal, "lijst_meer", n="6") and gegevens["taal"] == taal
    # de tellingen bij de vinkjes, met de namen in de taal van de site
    groepen = {g["soort"]: [(k["waarde"], k["naam"], k["aantal"]) for k in g["boven"] + g["meer"]]
               for g in gegevens["filters"]["groepen"]}
    assert groepen == {
        "oordeel": [("onwaar", i18n.label(taal, "onwaar"), "6")],
        "taal": [("en", i18n.taalnaam_in(taal, "en"), "5"), ("hi", i18n.taalnaam_in(taal, "hi"), "1")],
        "jaar": [("2024", "2024", "2"), ("2023", "2023", "1"), ("2022", "2022", "1"), ("2021", "2021", "1")]}


def test_a_filter_gives_only_its_rows_in_the_chosen_order(site):
    client, nr = site
    gegevens = client.get("/api/nl/archief?taal=en&sorteer=oud").json()
    # alleen het Engels, de oudste eerst op de datum van de laatste check; zonder datum achteraan
    assert [rij["href"] for rij in gegevens["rijen"]] == [
        f"/nl/fact-checks/{nr[k]}/" for k in ("los", "biolab", "jacht", "villa", "zonder_datum")]
    assert gegevens["paren"] == [["sorteer", "oud"], ["taal", "en"]]
    gekozen = [k["waarde"] for g in gegevens["filters"]["groepen"] if g["soort"] == "taal" for k in g["boven"] if k["aan"]]
    assert gekozen == ["en"]


def test_a_translated_row_carries_its_original_and_a_row_in_the_language_of_the_site_does_not(site):
    """B32: een vertaling staat nooit alleen."""
    client, nr = site
    rijen = {rij["nummer"]: rij for rij in client.get("/api/nl/archief").json()["rijen"]}
    hindi = rijen[nr["hindi"]]
    assert hindi["tekst"] == "Zelensky kocht een casino" and hindi["taal"] == "nl"
    assert hindi["origineel"]["taal"] == "hi" and "Hindi" in hindi["origineel"]["regel"]
    engels = client.get("/api/en/archief").json()["rijen"]
    assert all(rij["origineel"] is None for rij in engels if rij["taal"] == "en" and rij["nummer"] != nr["hindi"])


def test_the_archive_as_data_refuses_what_the_list_refuses_and_never_takes_a_search_question(site):
    client, _ = site
    for vraag in ("q=zelensky", "taal=xx", "oordeel=verzonnen", "bestaat=1", "p=0", "sorteer=gok"):
        assert client.get(f"/api/nl/archief?{vraag}").status_code == 404, vraag
    assert client.get("/api/xx/archief").status_code == 404


def test_the_archive_as_data_carries_the_policy_and_no_cookie(site):
    client, _ = site
    r = client.get("/api/nl/archief")
    assert r.headers["content-security-policy"] == CSP and "set-cookie" not in r.headers
    tekst = json.dumps(r.json(), ensure_ascii=False)
    assert "<script" not in tekst.lower()


@pytest.mark.parametrize("taal", TALEN)
def test_a_fact_check_as_data_says_its_label_count_newsrooms_and_translation_in_the_language_of_the_site(site, taal):
    """PLAN #34.2: de bewering, het label, de telling en elke redactie; de vertaling nooit zonder het origineel (B32)."""
    from factiz_site import app as fa
    client, nr = site
    villa = client.get(f"/api/{taal}/factcheck/{nr['villa']}").json()
    assert villa["bewering"] == "Zelensky bought a villa in Florida" and villa["vertaling"] is None
    assert villa["label"] == i18n.label(taal, "onwaar")
    assert villa["telregel"] == i18n.telregel(taal, 2, 2, "2022-04-01", "2024-03-05")
    # de check in de taal van de site eerst, dan in de taal van de bewering, dan de nieuwste (#34.2bp, E9.S31 AC5): de
    # Franse check van AFP alleen op de Franse site vooraan
    assert [k["redactie"] for k in villa["checks"]] == (["AFP", "Snopes"] if taal == "fr" else ["Snopes", "AFP"])
    hindi = client.get(f"/api/{taal}/factcheck/{nr['hindi']}").json()
    assert hindi["bewering"] == "ज़ेलेंस्की ने एक कैसीनो खरीदा" and [k["redactie"] for k in hindi["checks"]] == ["Snopes"]
    doel = "nl" if taal == "nl" else "en"            # een vertaling in de taal van de site, anders de Engelse
    assert hindi["vertaling"] == {"tekst": "Zelensky kocht een casino" if doel == "nl" else "Zelensky bought a casino",
                                  "taal": doel, "regel": fa.vertaalregel(taal, "hi", doel)}
    assert client.get(f"/api/{taal}/factcheck/0000000000000000").status_code == 404


def test_the_label_and_count_of_a_fact_check_read_as_words():
    assert i18n.telregel("en", 2, 2, "2022-04-01", "2024-03-05") == "2 newsrooms, 2 languages, 2022–2024"
    assert i18n.telregel("nl", 2, 2, "2022-04-01", "2024-03-05") == "2 redacties, 2 talen, 2022–2024"


@pytest.mark.parametrize("taal", TALEN)
def test_a_dossier_as_data_has_its_timeline_per_year_the_newest_on_top_and_its_counts(site, taal):
    client, _ = site
    g = client.get(f"/api/{taal}/dossier/zelensky-luxury").json()
    assert g["naam"] == NAAM[taal]
    assert [j["kop"] for j in g["jaren"]] == ["2025", "2024", "2023", "2022", i18n.tekst(taal, "dossier_zonder_datum")]
    assert [len(j["regels"]) for j in g["jaren"]] == [1, 1, 2, 1, 1]       # vier factchecks, een onderzoek, een besluit
    assert g["stand"]["factchecks"] == "4"
    assert client.get(f"/api/{taal}/dossier/bestaat-niet").status_code == 404
    assert client.get(f"/api/{taal}/dossier/in-de-maak").status_code == 404          # een concept staat in geen uitgave


def test_search_as_data_finds_the_claims_with_every_word_and_takes_the_question_only_in_the_body(site):
    """De vraag in het bericht, nooit in het adres en nooit in een tussengeheugen (E9.S6 AC3)."""
    client, nr = site
    g = client.post("/api/nl/zoek", data={"q": "Zelensky bought"})
    assert g.status_code == 200 and g.headers["cache-control"] == "no-store"
    gegevens = g.json()
    # de Hindi bewering via haar vertaling
    assert [rij["href"] for rij in gegevens["rijen"]] == [f"/nl/fact-checks/{nr[k]}/" for k in ("villa", "jacht", "hindi")]
    assert gegevens["aantal"] == "3 resultaten" and gegevens["gezocht"] and not gegevens["deels"]
    # de woorden van de vraag zijn gemarkeerd
    assert any(raak for rij in gegevens["rijen"] for _, raak in rij["stukken"])
    assert client.get("/api/nl/zoek?q=zelensky").status_code == 405
    assert client.post("/api/nl/zoek", content=b"q=" + b"x" * 9000,
                       headers={"content-type": "application/x-www-form-urlencoded"}).status_code == 413


@pytest.fixture(scope="module")
def met_namen(tmp_path_factory):
    from tests.test_factiz_namen import _site as _site_namen
    return _site_namen(tmp_path_factory)


def test_suggestions_while_typing_are_at_most_ten_in_three_groups_and_take_the_question_only_in_the_body(site):
    """#404 hoogstens 10, #356 zoekvragen, ingangen en factchecks apart, #359 de zoekvraag eerst; de vraag nooit in een
    adres en nooit in een tussengeheugen (E9.S6 AC3)."""
    client, _ = site
    r = client.post("/api/nl/suggesties", data={"q": "zelensky"})
    assert r.status_code == 200 and r.headers["cache-control"] == "no-store"
    g = r.json()
    assert set(g) == {"vraag", "totaal", "zoekvragen", "ingangen", "factchecks", "aanvulling"}   # #34.2ac
    assert len(g["zoekvragen"]) + len(g["ingangen"]) + len(g["factchecks"]) <= 10
    assert g["zoekvragen"][0]["tekst"] == "zelensky" and g["totaal"] > 0
    assert all(f["href"].startswith("/nl/fact-checks/") for f in g["factchecks"])
    assert client.get("/api/nl/suggesties?q=zelensky").status_code == 405
    leeg = client.post("/api/nl/suggesties", data={"q": "z"}).json()                  # één teken: nog niets
    assert leeg["ingangen"] == [] and leeg["factchecks"] == []


def test_the_start_of_a_word_finds_the_dossier_and_the_person_with_the_most_fact_checks_first(site, met_namen):
    client, _ = site
    g = client.post("/api/en/suggesties", data={"q": "zelens"}).json()
    assert any(i["soort"] == "dossier" and i["href"] == "/dossiers/zelensky-luxury/" for i in g["ingangen"])
    client_namen = met_namen[0]
    g = client_namen.post("/api/nl/suggesties", data={"q": "zelen"}).json()
    personen = [i for i in g["ingangen"] if i["soort"] == "naam"]
    assert personen and personen[0]["href"].startswith("/nl/names/Q")
    # het woord afgemaakt als zoekvraag (#359), zonder leestekens aan de rand
    assert any(z["tekst"].startswith("zelensk") for z in g["zoekvragen"])
    assert all(not z["tekst"].endswith((",", ".")) for z in g["zoekvragen"])


# --- 34.2c: vindbaar alleen in een taal met eigen hoofdtekst (DESIGNSYSTEEM §6) ---------------------------------------

def test_a_claim_is_findable_in_its_own_language_and_in_every_language_with_a_translation():
    """Google telt een vertaalde pagina niet als kopie, wel een pagina waarvan alleen menu en knoppen vertaald zijn: de
    hoofdinhoud is de bewering. Ligt er geen enkele, dan alleen de hoofdmap, zodat er altijd één vindbare versie is."""
    from factiz_site import i18n
    assert i18n.eigen_talen("de", {"en", "fr"}) == ("en", "de", "fr")
    assert i18n.eigen_talen("nl", ()) == ("nl",)
    assert i18n.eigen_talen("te", ()) == ("en",)                     # Telugu is geen taal van de site: de hoofdmap
    assert i18n.eigen_talen("te", {"ml", "nl"}) == ("nl",)          # een vertaling in een taal die de site niet heeft telt niet
    assert i18n.eigen_talen("hi", ()) == ("hi",)                     # Hindi wel, sinds B79: daar is de bewering eigen tekst


def test_the_fact_check_data_says_where_the_page_is_findable(site):
    client, nr = site
    # Hindi met een Nederlandse en een Engelse vertaling: vindbaar in die twee en in het Hindi zelf (B79), in het Duits
    # alleen voor bezoekers
    assert client.get(f"/api/nl/factcheck/{nr['hindi']}").json()["vindbaar"] == {
        "index": True, "talen": ["en", "nl", "hi"], "x_default": "en", "kern": True,
        "afgeschermd": False}       # #34.2bw: een uitgave zonder lezing van privépersonen schermt niets af
    assert client.get(f"/api/de/factcheck/{nr['hindi']}").json()["vindbaar"]["index"] is False
    # Engels zonder vertaling: alleen op de hoofdmap
    assert client.get(f"/api/en/factcheck/{nr['villa']}").json()["vindbaar"] == {
        "index": True, "talen": ["en"], "x_default": "en", "kern": True, "afgeschermd": False}
    # de kern van de eerste stap (B73 punt 5): de villa bij twee redacties, de Hindi-bewering in het dossier, en 'los' met
    # Ook gecheckt door (dezelfde bewering als de jacht); een factcheck zonder een van de drie toetst test_factiz_sitemap
    assert client.get(f"/api/en/factcheck/{nr['los']}").json()["vindbaar"]["kern"] is True
    assert client.get(f"/api/fr/factcheck/{nr['villa']}").json()["vindbaar"]["index"] is False


def test_the_context_names_a_network_only_with_who_established_it(site):
    """B62: een toeschrijving aan een netwerk komt alleen uit een netwerkdossier, met wie het vaststelde (PLAN #34.2h)."""
    client, nr = site
    toegeschreven = client.get(f"/api/nl/factcheck/{nr['biolab']}").json()["omveld"]["toegeschreven"]
    assert len(toegeschreven) == 1
    assert toegeschreven[0]["href"] == "/nl/dossiers/doppelganger/"
    assert toegeschreven[0]["door"] == "EUvsDisinfo" and toegeschreven[0]["url"] == "https://euvsdisinfo.eu/report/biolab"


def test_a_row_says_its_verdict_kind_and_its_language_only_when_no_translation_bridges_it(site):
    """PLAN #34.2l: de kaart kleurt het oordeel naar zijn soort, en noemt de taal alleen als de bewering in een andere
    taal staat dan de site en er geen vertaling bij is (dan zegt de regel bij het origineel het al)."""
    client, nr = site
    gezien = set()
    for taal in TALEN:
        for rij in client.get(f"/api/{taal}/archief").json()["rijen"]:
            assert rij["soort"] in (*i18n.LABELS, "geen")
            if rij["taal"] == taal or rij["origineel"]:
                assert not rij["taalnaam"], (taal, rij["nummer"])
            else:    # een taal zonder naam (een losse code) noemt de kaart niet
                assert rij["taalnaam"] in ("", i18n.taalnaam_in(taal, rij["taal"])), (taal, rij["nummer"])
                gezien.add((taal, rij["taal"], rij["taalnaam"]))
    assert ("de", "en", "Englisch") in gezien    # een Engelse bewering zonder Duitse vertaling


# --- Gevonden op een vraag eromheen (PLAN #34.2m, DESIGNSYSTEEM §6) -------------------------------------------------------
def _zoekkop(client, taal, nummer):
    g = client.get(f"/api/{taal}/factcheck/{nummer}").json()
    return g, g["kop"]


@pytest.mark.parametrize("taal", TALEN)
def test_the_title_starts_with_the_verdict_and_quotes_the_claim_on_a_whole_word(site, taal):
    """De juridische verkenning (PLAN #34.2bw, SPECS E9.S8 AC8): een titel die Google afkapt of herbouwt, mag nooit een kale
    bewering over iemand tonen; dus eerst het oordeel, dan de bewering tussen de aanhalingstekens van de taal. Ook de naam in
    de gestructureerde gegevens en het laatste deel van het kruimelpad."""
    from factiz_site import app as fa
    client, nr = site
    for nummer in (nr["villa"], nr["hindi"], nr["los"]):
        g, kop = _zoekkop(client, taal, nummer)
        getoond = g["vertaling"]["tekst"] if g["vertaling"] else g["bewering"]
        # sinds 2026-11-19 het stempel met wie het zegt (PLAN #34.2cc): *False according to AFP and Snopes: “…”*; in deze
        # kleine uitgave hoogstens twee redacties, dus staan ze er allebei, net als op de pagina
        oordeel = f'{g["stempel"]} {g["volgens"]}'.strip()
        # met een zoekvraag in deze taal (#34.2cf, B87) het oordeel met de vraag, anders met de bewering
        vraag = kop["antwoord"]["kop"] if kop["antwoord"]["kop"] != i18n.tekst(taal, "antwoord_kop") else ""
        if vraag:
            assert kop["titel"] == i18n.tekst(taal, "factcheck_titel_vraag", oordeel=oordeel, vraag=vraag)
        else:
            assert kop["titel"] == i18n.tekst(taal, "factcheck_titel", oordeel=oordeel,
                                              bewering=fa._kort(getoond, fa.TITEL_BEWERING))
            assert getoond[:20] in kop["titel"]
        assert kop["titel"].startswith(g["stempel"])
        assert bool(vraag) == ((nummer, taal) in {(nr["villa"], "en"), (nr["hindi"], "hi"), (nr["los"], "en")})
        ld = json.loads(kop["ld"])
        assert ld["name"] == kop["titel"] and ld["breadcrumb"]["itemListElement"][-1]["name"] == kop["titel"]
    from factiz_site import app as fa
    lang = "Zelensky bought two yachts for seventy-five million dollars from a shipyard in the south of Italy"
    kort = fa._kort(lang, 58)
    assert len(kort) <= 60 and kort.endswith(" …") and lang.startswith(kort[:-2]) and lang[len(kort) - 2] == " "


def test_in_every_language_the_title_puts_the_verdict_before_the_quoted_claim():
    for taal in i18n.TALEN:
        sjabloon = i18n.teksten(taal)["factcheck_titel"]
        assert sjabloon.index("{oordeel}") < sjabloon.index("{bewering}"), taal
        assert sjabloon.count("{bewering}") == 1 and sjabloon.count("{oordeel}") == 1, taal


@pytest.mark.parametrize("taal", TALEN)
def test_the_answer_says_the_verdict_then_who_checked_and_when(site, taal):
    from factiz_site import i18n
    client, nr = site
    g, kop = _zoekkop(client, taal, nr["villa"])           # twee redacties, de nieuwste op 5 maart 2024
    a = kop["antwoord"]
    # het stempel met wie het zegt (PLAN #34.2cc): *Onwaar volgens AFP en Snopes*
    oordeel = f'{g["stempel"]} {g["volgens"]}'.strip()
    # boven het antwoord de zoekvraag in haar eigen taal (#34.2cf), anders *Klopt dit?*
    assert a["kop"] == ("Did Zelensky buy a villa in Florida?" if taal == "en" else i18n.tekst(taal, "antwoord_kop"))
    assert a["label"] == oordeel
    nieuwste = next(k for k in g["checks"] if k["datum"] == i18n.datum(taal, "2024-03-05"))
    assert a["zin"] == i18n.tekst(taal, "antwoord_meer", n="2", redactie=nieuwste["redactie"], datum=nieuwste["datum"])
    # de omschrijving: het oordeel, dan de vraag als die er in deze taal is (#34.2cf), dan wie het wanneer checkte
    vraag = f"{a['kop']} " if taal == "en" else ""
    assert kop["omschrijving"].startswith(f"{oordeel}. {vraag}{a['zin']}") and len(kop["omschrijving"]) <= 160
    _, zonder = _zoekkop(client, taal, nr["zonder_datum"])  # één redactie, geen datum
    redactie = client.get(f"/api/{taal}/factcheck/{nr['zonder_datum']}").json()["checks"][0]["redactie"]
    assert zonder["antwoord"]["zin"] == i18n.tekst(taal, "antwoord_een_zonder_datum", redactie=redactie)


def test_a_check_without_a_verdict_answers_only_who_checked():
    """DR2: zonder oordeel van een redactie geen label in het antwoord, alleen wie checkte."""
    from factiz_site import app as fa
    p = {"label": None, "redacties": 1, "bewering": "x", "taal": "en", "opgedoken": [],
         "checks_lijst": [{"redactie": "Snopes", "datum": "2024-03-05", "url": "https://snopes.com/x", "link": "ok", "taal": "en"}]}
    g = {"label": "Fact-checked", "vertaling": None, "bewering": "x"}
    kop = fa.kopgegevens("en", "0123456789abcdef", p, g)
    assert kop["antwoord"]["label"] == "" and kop["omschrijving"].startswith("Snopes checked this claim on 5 March 2024.")


@pytest.mark.parametrize("taal", TALEN)
def test_the_structured_data_cites_the_newsrooms_and_never_claims_a_review(site, taal):
    from factiz_site import i18n
    client, nr = site
    g, kop = _zoekkop(client, taal, nr["villa"])
    assert "<" not in kop["ld"] and "ClaimReview" not in kop["ld"]
    ld = json.loads(kop["ld"])
    assert ld["@type"] == "WebPage" and ld["url"] == i18n.BASIS + g["href"] and ld["inLanguage"] == taal
    claim = ld["mainEntity"]
    assert claim["@type"] == "Claim" and claim["text"] == g["bewering"] and claim["inLanguage"] == g["taal"]
    # de eigen checks eerst, dan die van dezelfde bewering bij een andere redactie (*Ook gecheckt door*, #34.2bq)
    ook = [k["url"] for k in (g["ook_gecheckt"] or {}).get("checks", []) if k["url"]]
    assert [c["url"] for c in claim["citation"]] == [k["url"] for k in g["checks"] if k["url"]] + ook and ook
    assert claim["text"] == claim["text"].strip()
    assert all(c["author"]["@type"] == "Organization" and c["author"]["name"] for c in claim["citation"])
    kruimel = ld["breadcrumb"]["itemListElement"]
    assert [k["position"] for k in kruimel] == [1, 2, 3] and kruimel[0]["item"] == i18n.BASIS + i18n.pad(taal)


def test_no_claim_can_break_out_of_the_structured_data_and_the_first_sighting_has_no_link():
    """Een bewering met `</script>` blijft tekst; de eerste keer gezien noemt de plek en de datum, nooit een link naar de
    bron van het nepnieuws."""
    from factiz_site import app as fa
    p = {"label": "onwaar", "redacties": 1, "bewering": 'x</script><script>alert(1)</script>', "taal": "en",
         "opgedoken": [{"naam": "rt.com", "datum": "2022-03-01", "url": "https://rt.com/x", "bron_naam": "EUvsDisinfo"}],
         "checks_lijst": [{"redactie": "EUvsDisinfo", "datum": "2022-03-10", "url": "https://euvsdisinfo.eu/report/x",
                           "link": "ok", "taal": "en"}]}
    g = {"label": "Known to be false", "vertaling": None, "bewering": p["bewering"]}
    kop = fa.kopgegevens("en", "0123456789abcdef", p, g)
    assert "</script" not in kop["ld"] and "<" not in kop["ld"]
    claim = json.loads(kop["ld"])["mainEntity"]
    assert claim["text"] == p["bewering"]
    assert claim["firstAppearance"] == {"@type": "CreativeWork", "name": "rt.com", "datePublished": "2022-03-01"}


# --- de woorden van een redactie vertaald, en lijkt op (PLAN #34.2o, #34.2p) --------------------------------------------
@pytest.mark.parametrize("taal", TALEN)
def test_a_newsrooms_words_in_another_language_than_the_site_get_their_translation(site, taal):
    from factiz_site import i18n
    client, nr = site
    g = client.get(f"/api/{taal}/factcheck/{nr['villa']}").json()
    glos = {"en": "False", "nl": "Onwaar", "de": "Falsch", "es": "Falso", "fr": "Faux"}
    for k in g["checks"]:
        if k["taal_code"] == taal:
            assert k["glos"] is None and k["glos_regel"] == ""
        else:
            assert k["glos"] == glos[taal]
            assert k["glos_regel"] == i18n.tekst(taal, "oordeel_glos", bron=i18n.taalnaam_in(taal, k["taal_code"]))


@pytest.mark.parametrize("taal", TALEN)
def test_lijkt_op_shows_other_pages_with_their_own_verdict_never_a_version_already_shown(site, taal):
    from factiz_site import i18n
    client, nr = site
    g = client.get(f"/api/{taal}/factcheck/{nr['villa']}").json()
    l = g["lijkt_op"]
    assert [r["nummer"] for r in l["rijen"]] == [nr["biolab"]]            # de jacht staat al bij Komt ook voor als
    assert l["telling"] == i18n.tekst(taal, "lijkt_op_een", n="1")
    biolab = client.get(f"/api/{taal}/factcheck/{nr['biolab']}").json()
    assert l["per_label"] == [{"label": biolab["label"], "soort": l["rijen"][0]["soort"], "n": 1}]
    assert g["label"] != "" and client.get(f"/api/{taal}/factcheck/{nr['los']}").json()["lijkt_op"] is None


@pytest.mark.parametrize("taal", TALEN)
def test_also_checked_by_shows_each_check_of_the_same_claim_elsewhere_the_closest_to_the_reader_first(site, taal):
    """PLAN #34.2bp, SPECS E9.S31: elke check met haar eigen oordeel en de bewering zoals die pagina haar toont; eerst in
    de taal van de site, dan in de taal van de bewering, dan de nieuwste. Het oordeel bovenaan blijft van de eigen checks."""
    client, nr = site
    villa = client.get(f"/api/{taal}/factcheck/{nr['villa']}").json()
    o = villa["ook_gecheckt"]
    assert o["regel"] == i18n.tekst(taal, "ook_gecheckt_regel", namen="Maldita")
    assert o["telling"] == i18n.tekst(taal, "redacties_een", n="1")
    assert [(k["redactie"], k["taal_code"]) for k in o["checks"]] == [("Maldita", "es")]
    assert o["checks"][0]["bewering"]["nummer"] == nr["jacht"]
    assert o["checks"][0]["bewering"]["href"] == i18n.pad(taal, "fact-checks", nr["jacht"])
    assert [k["redactie"] for k in villa["checks"]] != ["Maldita"]             # de eigen checks blijven de eigen
    jacht = client.get(f"/api/{taal}/factcheck/{nr['jacht']}").json()["ook_gecheckt"]
    volgorde = {"fr": [("AFP", "fr"), ("Snopes", "en"), ("Snopes", "en")]}.get(
        taal, [("Snopes", "en"), ("Snopes", "en"), ("AFP", "fr")])
    assert [(k["redactie"], k["taal_code"]) for k in jacht["checks"]] == volgorde
    namen = ["AFP", "Snopes"] if taal == "fr" else ["Snopes", "AFP"]
    assert jacht["regel"] == i18n.tekst(taal, "ook_gecheckt_regel", namen=i18n.opsomming(taal, namen))
    # een pagina zonder dezelfde bewering elders heeft het blok niet
    assert client.get(f"/api/{taal}/factcheck/{nr['biolab']}").json()["ook_gecheckt"] is None


# Waarom het niet klopt (PLAN #34.2j, B77): de punten van EUvsDisinfo in de gegevens van een factcheck.
@pytest.fixture(scope="module")
def met_waarom(tmp_path_factory):
    from doublecheck import publiceren as pb
    from factiz_site import app as fa
    from starlette.testclient import TestClient
    from tests.test_publiceren import EU, REGISTER, _check, _claim, _lab
    map_ = tmp_path_factory.mktemp("waarom")
    lab = _lab(map_)
    a = _claim(lab, 1, "Ukraine is a Nazi state")
    _check(lab, a, "https://euvsdisinfo.eu/report/nazi-ukraine/", bron=EU, eigen="Disinformation")
    b = _claim(lab, 2, "Garlic water cures covid")
    _check(lab, b, "https://snopes.com/garlic")
    lab.commit()
    nr = {"met": pb.nummer(a), "zonder": pb.nummer(b)}
    waarom = {"punten": {nr["met"]: {"punten": ["The far-right won 2.15% of the vote.", "Zelenskyy is Jewish."],
                                     "url": "https://euvsdisinfo.eu/report/nazi-ukraine/"}},
              "meting": {"punten": 292, "niet_gedragen": 3, "regels": "regels-v2", "lezer": "lezing-v2/haiku/medium",
                         "paginas": 200, "datum": "2026-11-12"}}
    m = pb.bouw(lab, map_ / "uit", register=REGISTER, vaag=frozenset(), datum="2026-11-12", waarom=waarom)
    return TestClient(fa.maak_app(m["bestand"]), follow_redirects=False), nr


@pytest.mark.parametrize("taal", TALEN)
def test_a_fact_check_carries_why_it_is_false_from_euvsdisinfo_with_the_link_the_measurement_and_a_way_to_report(met_waarom, taal):
    client, nr = met_waarom
    g = client.get(f"/api/{taal}/factcheck/{nr['met']}").json()["waarom"]
    assert g["punten"] == ["The far-right won 2.15% of the vote.", "Zelenskyy is Jewish."] and g["taal"] == "en"
    assert g["url"] == "https://euvsdisinfo.eu/report/nazi-ukraine/" and g["bron"] == "EUvsDisinfo"
    assert "meting" not in g                            # geen steekproefregel (PO 2026-11-22: "Ja, alle drie weg")
    # de gemeten foutmarge staat op de pagina over de bronnen, bij EUvsDisinfo (B77: "bij het blok of op de pagina over
    # de methode")
    b = client.get(f"/api/{taal}/bronnen").json()
    eu = [x for x in b["bronnen"] if x["meting"]]
    assert len(eu) == 1 and "EUvsDisinfo" in eu[0]["naam"] and "292" in eu[0]["meting"] and b["meting_kop"]
    assert g["meld"].startswith("mailto:info@factiz.org?subject=") and nr["met"] in g["meld"]
    # op een andere taalsite zegt een regel dat de punten Engels zijn, zoals de weerlegging
    assert bool(g["engels"]) == (taal != "en")
    assert client.get(f"/api/{taal}/factcheck/{nr['zonder']}").json()["waarom"] is None


@pytest.mark.parametrize("taal", TALEN)
def test_the_archive_says_the_day_of_the_edition_and_of_its_latest_fact_check(site, taal):
    """Tot wanneer de site bij is (PLAN #34.2bz, PO 2026-11-17: "versienummer met datum in de footer"): de dag van de uitgave
    uit haar naam en de dag van de nieuwste check erin, als datum en in de vorm van de taal."""
    client, _ = site
    assert client.get(f"/api/{taal}/archief").json()["actueel"] == {
        "uitgave": "2026-11-11", "uitgave_tekst": i18n.datum(taal, "2026-11-11"),
        "factcheck": "2024-06-07", "factcheck_tekst": i18n.datum(taal, "2024-06-07")}


def test_the_day_of_an_edition_is_its_name_without_the_letter_of_a_second_one_that_day():
    from factiz_site import db
    assert db.uitgave_dag("2026-11-16b") == "2026-11-16" and db.uitgave_dag("2026-11-16") == "2026-11-16"
    assert db.uitgave_dag("") == "" and db.uitgave_dag(None) == "" and db.uitgave_dag("proef") == ""


def _eens_site(tmp_path, checks):
    """Een uitgave met één bewering en een check per (adres, oordeel, datum)."""
    from doublecheck import publiceren as pb
    from factiz_site import app as fa
    from starlette.testclient import TestClient
    from tests.test_publiceren import REGISTER, _check, _claim, _lab

    tmp_path.mkdir(parents=True, exist_ok=True)
    lab = _lab(tmp_path)
    n = _claim(lab, 1, "Zelensky bought a villa in Florida")
    for url, oordeel, datum in checks:
        _check(lab, n, url, oordeel=oordeel, eigen=oordeel, datum=datum)
    lab.commit()
    register = {**REGISTER, "politifact.com": "PolitiFact"}
    m = pb.bouw(lab, tmp_path / "uit", register=register, vaag=frozenset(), datum="2026-11-22")
    client = TestClient(fa.maak_app(m["bestand"]))
    return client.get(f"/api/nl/factcheck/{pb.nummer(n)}").json()


def test_the_answer_shows_each_newsroom_once_with_its_latest_verdict_as_a_stamp(tmp_path):
    """PLAN #34.2cd, SPECS E9.S31 AC7 (PO 2026-11-22: "Dus je ziet de drie stempels met daarachter de betreffende redactie.
    That's it."): hun oordelen, nooit een eigen; elke redactie één keer, met haar nieuwste oordeel; pas vanaf twee."""
    d = _eens_site(tmp_path / "a", [("https://snopes.com/a", "onwaar", "2024-03-01"),
                                    ("https://snopes.com/b", "misleidend", "2024-05-01"),     # het nieuwste van Snopes
                                    ("https://factcheck.afp.com/a", "onwaar", "2024-03-02"),
                                    ("https://politifact.com/a", "waar", "2024-03-03")])
    e = d["eens"]
    assert e["tekst"] == "Gecheckt door:" and e["meer"] == "" and e["anker"] == "bronnen"
    assert sorted((r["naam"], r["soort"], r["woord"]) for r in e["redacties"]) == [
        ("AFP", "onwaar", "Onwaar"), ("PolitiFact", "waar", "Klopt"), ("Snopes", "misleidend", "Misleidend")]
    # elke redactie linkt naar haar eigen check op de pagina, die met het getoonde oordeel (PO 2026-11-22: "1")
    for r in e["redacties"]:
        soort, n = r["anker"].split("-")
        assert soort == "check" and d["checks"][int(n)]["redactie"] == r["naam"] and d["checks"][int(n)]["oordeel"] == r["soort"]
    # meer dan vier: drie, en de rest als aantal
    d = _eens_site(tmp_path / "b", [(f"https://{h}/a", "onwaar", "2024-03-01") for h in
                                    ("snopes.com", "factcheck.afp.com", "maldita.es", "politifact.com", "euvsdisinfo.eu")])
    assert len(d["eens"]["redacties"]) == 3 and d["eens"]["meer"] == "2 andere"
    # één redactie: geen regel
    assert _eens_site(tmp_path / "c", [("https://snopes.com/a", "onwaar", "2024-03-01")])["eens"] is None


def test_the_agreement_line_counts_the_newsrooms_on_the_page_and_under_also_checked_by(site):
    client, nr = site
    d = client.get(f"/api/nl/factcheck/{nr['villa']}").json()
    e = d["eens"]
    assert e["tekst"] == "Gecheckt door:" and e["anker"] == "ook-gecheckt" and e["meer"] == ""
    assert [(r["naam"], r["woord"]) for r in e["redacties"]] == [("Snopes", "Onwaar"), ("AFP", "Onwaar"), ("Maldita", "Onwaar")]
    # een redactie van deze pagina springt naar haar check hier, een andere naar haar check onder Ook gecheckt door
    lijsten = {"check": d["checks"], "ook": d["ook_gecheckt"]["checks"]}
    assert [r["anker"].split("-")[0] for r in e["redacties"]] == ["check", "check", "ook"]
    for r in e["redacties"]:
        soort, n = r["anker"].split("-")
        assert lijsten[soort][int(n)]["redactie"] == r["naam"]
    assert client.get(f"/api/nl/factcheck/{nr['biolab']}").json()["eens"] is None


def test_a_search_question_becomes_the_heading_title_and_description_in_its_own_language(tmp_path):
    """PLAN #34.2cf, SPECS E9.S8 AC11, B87: in de taal van de vraag is de kop boven het antwoord de vraag, de titel het
    oordeel met de vraag (nooit een kale bewering) en de omschrijving het oordeel, de vraag en wie het wanneer checkte. In
    een andere taal blijft het zoals het was."""
    from doublecheck import publiceren as pb
    from factiz_site import app as fa
    from starlette.testclient import TestClient
    from tests.test_publiceren import REGISTER, _check, _claim, _lab

    lab = _lab(tmp_path)
    n = _claim(lab, 1, "This photo shows Greta Thunberg holding up the book On The Jews and Their Lies")
    _check(lab, n, "https://snopes.com/greta", oordeel="onwaar", eigen="Fake", datum="2023-11-30")
    lab.commit()
    nr = pb.nummer(n)
    vraag = "Does this photo show Greta Thunberg holding up the book On The Jews and Their Lies?"
    m = pb.bouw(lab, tmp_path / "uit", register=REGISTER, vaag=frozenset(), datum="2026-11-22", zoekvragen={nr: {
        "taal": "en", "bron": "This photo shows Greta Thunberg holding up the book On The Jews and Their Lies",
        "vraag": vraag, "onderwerp": "Greta Thunberg and the book"}})
    client = TestClient(fa.maak_app(m["bestand"]))
    en = client.get(f"/api/en/factcheck/{nr}").json()["kop"]
    assert en["antwoord"]["kop"] == vraag
    assert en["titel"] == f"False according to Snopes: {vraag}"
    assert en["omschrijving"].startswith(f"False according to Snopes. {vraag}") and len(en["omschrijving"]) <= 160
    nl = client.get(f"/api/nl/factcheck/{nr}").json()["kop"]
    assert nl["antwoord"]["kop"] == "Klopt dit?" and vraag not in nl["titel"] and vraag not in nl["omschrijving"]


def test_a_left_out_name_is_a_sticker_in_the_data_and_plain_words_in_titles_in_python_and_typescript(tmp_path):
    """Maatregel 2 (PLAN #34.2bw, SPECS E9.S8 AC13): het merkteken van een weggelaten naam gaat nooit zo naar buiten. In de
    gegevens wordt het ⟦naam weggelaten⟧ in de taal van de site (de site maakt er een sticker van, met een voetnoot), in
    de titel, de omschrijving, de gestructureerde gegevens en de alt-tekst van het deelplaatje [naam weggelaten]."""
    import json as json_
    from doublecheck import publiceren as pb
    from factiz_site import app as fa
    from factiz_site import gelijk, i18n
    from starlette.testclient import TestClient
    from tests.test_publiceren import REGISTER, _check, _claim, _lab

    lab = _lab(tmp_path)
    n = _claim(lab, 1, "Jamna Kumari, 12, was attacked in Gujarat")
    _check(lab, n, "https://snopes.com/attack", oordeel="onwaar", eigen="Fake", datum="2023-11-30")
    lab.commit()
    nr = pb.nummer(n)
    bron = "Jamna Kumari, 12, was attacked in Gujarat"
    m = pb.bouw(lab, tmp_path / "uit", register=REGISTER, vaag=frozenset(), datum="2026-11-22", vertaalmaker="proef",
                vertalingen={"nl": {nr: "Jamna Kumari, 12, werd aangevallen in Gujarat"}},
                zoekvragen={nr: {"taal": "en", "bron": bron, "vraag": "Was Jamna Kumari, 12, attacked in Gujarat?",
                                 "onderwerp": "Jamna Kumari in Gujarat"}},
                afscherming={nr: {"bron": bron, "afschermen": True, "naam": "Jamna Kumari"}})
    client = TestClient(fa.maak_app(m["bestand"]))
    nl = client.get(f"/api/nl/factcheck/{nr}").json()
    assert i18n.WEGGELATEN not in json_.dumps(nl, ensure_ascii=False)
    assert nl["bewering"] == "⟦naam weggelaten⟧, 12, was attacked in Gujarat"
    assert nl["vertaling"]["tekst"] == "⟦naam weggelaten⟧, 12, werd aangevallen in Gujarat"
    assert nl["weggelaten"] is True and nl["vindbaar"]["afgeschermd"] is True
    assert "[naam weggelaten]" in nl["kop"]["titel"] and "⟦" not in nl["kop"]["titel"] + nl["kop"]["omschrijving"]
    assert "[naam weggelaten], 12" in nl["deelbeeld"]["alt"]
    en = client.get(f"/api/en/factcheck/{nr}").json()
    assert en["kop"]["antwoord"]["kop"] == "Was ⟦name withheld⟧, 12, attacked in Gujarat?"
    assert en["kop"]["titel"] == "False according to Snopes: Was [name withheld], 12, attacked in Gujarat?"
    assert json_.loads(en["kop"]["ld"])["mainEntity"]["text"] == "[name withheld], 12, was attacked in Gujarat"
    # ook in een lijst, en een pagina zonder weggelaten naam zegt het niet
    lijst = client.get("/api/de/archief").json()
    assert "⟦Name weggelassen⟧" in json_.dumps(lijst, ensure_ascii=False)
    adressen = [f"/api/{taal}/factcheck/{nr}" for taal in ("en", "nl", "de", "hi")] + ["/api/de/archief", "/api/en/archief"]
    assert gelijk.verschillen(client, m["bestand"], adressen) == []
