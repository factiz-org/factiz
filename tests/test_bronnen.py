"""De lijst met betrouwbare bronnen (PLAN #32.3c): eerst wat voor bron het is, dan pas
hoe goed. Drie banden op het cijfer van Lin e.a. (PO 2026-10-28: "0,65 lijkt me dan de
grens"); platforms krijgen geen band, want wie het post bepaalt het. Versie 3 (#32.29):
de tekens die de PO aannam, alleen bij de redacties die de PO een voor een koos."""

import json

import pytest

from doublecheck import berichtcontrole as bc
from doublecheck import bronnen as br
from doublecheck import bronnenlijst as bl

LIN = ("domain,pc1\nnytimes.com,0.86\ncnn.com,0.66\nnypost.com,0.64\nfoxnews.com,0.53\ndailymail.co.uk,0.38\n"
       "wikipedia.org,0.83\nyoutube.com,0.38\nnasa.gov,0.95\nfacebook.com/iemand,0.25\neldiario.es,0.60\n")
WIKI = """{| class="wikitable"
|- class="s-gu" id="Wikipedia"
| Wikipedia
| {{WP:RSPSTATUS|gu}}
| {{WP:RSPUSES|wikipedia.org}}
|- class="s-gu" id="YouTube"
| YouTube
| {{WP:RSPSTATUS|gu}}
| {{WP:RSPUSES|youtube.com}}
|- class="s-gu" id="Fox News (politics)"
| Fox News (politics)
| {{WP:RSPSTATUS|gu}}
| {{WP:RSPUSES|foxnews.com}}
|- class="s-gr" id="Reuters"
| Reuters
| {{WP:RSPSTATUS|gr}}
| {{WP:RSPUSES|reuters.com}}
|}"""


def _lijst(tekens=None):
    return br.bouw(lin=LIN, wikipedia=[WIKI], ifcn=["https://www.factcheck.org/"],
                   ebu=[("nos.nl", "NLD"), ("pbs-voorbeeld.org", "USA")],
                   rsf=bl.rsf_scores("ISO;Score 2026\r\nNLD;88,92\r\nUSA;62,61\r\n"), datum="2026-10-28",
                   tekens=tekens)


def _b(url, lijst=None):
    return br.beoordeel(url, (lijst or _lijst())["sites"])


def test_lin_gives_three_bands_with_the_line_at_0_65_and_0_40():
    assert _b("https://www.nytimes.com/x")["band"] == "goed"
    assert _b("https://edition.cnn.com/x")["band"] == "goed"  # 0,66
    assert _b("https://nypost.com")["band"] == "wisselend"  # 0,64
    assert _b("https://www.dailymail.co.uk")["band"] == "laag"  # 0,38
    assert _b("https://onbekend.example")["band"] is None and _b("https://onbekend.example")["soort"] == "overig"


def test_wikipedia_is_reference_and_good_its_own_citation_rule_does_not_count():
    w = _b("https://en.wikipedia.org/wiki/X")
    assert w["soort"] == "naslag" and w["band"] == "goed" and w["site"] == "wikipedia.org"
    assert _b("https://www.wikiwand.com/en/X") == {**w, "spiegel van": "wikipedia.org"}


def test_a_platform_never_gets_a_band_whatever_the_raters_say():
    for url in ("https://www.youtube.com/watch", "https://x.com/iemand", "https://www.facebook.com/iemand",
                "https://grokipedia.com/page/X"):
        uit = _b(url)
        assert uit["soort"] == "platform" and uit["band"] is None, url


def test_the_strictest_judgment_on_the_same_publisher_counts():
    assert _b("https://www.foxnews.com/politics")["band"] == "laag"  # Lin 0,53 wisselend, Wikipedia ongeschikt
    assert _b("https://reuters.com")["band"] == "goed"


def test_official_domains_keep_their_kind_and_get_the_band_of_the_raters():
    assert _b("https://www.nasa.gov/x") == {"site": "nasa.gov", "soort": "officieel", "band": "goed",
                                            "bronnen": [["goed", "Lin e.a. 0.95"]]}
    assert _b("https://pib.gov.in/x")["soort"] == "officieel" and _b("https://pib.gov.in/x")["band"] is None


def test_factcheckers_and_public_broadcasters_from_a_free_press_are_good():
    assert _b("https://www.factcheck.org/2026/x")["band"] == "goed"
    assert _b("https://nos.nl/artikel/1")["band"] == "goed"
    assert _b("https://pbs-voorbeeld.org")["band"] is None  # RSF 62,6: onder de 70


def test_the_list_carries_its_version_lines_and_fingerprint():
    lijst = _lijst()
    assert lijst["_meta"]["versie"] == "bronnen-v4"  # de bouw op de lijsten; versie 5 legt daar de keuze van de PO op
    assert lijst["_meta"]["grenzen"] == {"goed": 0.65, "laag": 0.40, "rsf": 70.0}
    assert bl.vastgelegd(lijst)


# --- versie 3: de tekens die de PO aannam (#32.29) ----------------------------------------------

def _voorstel():
    def r(domein, tekens, taal="es"):
        return {"domein": domein, "naam": domein, "taal": taal, "tekens": tekens}
    return {"al_goed": ["elpais.com"], "groepen": [
        {"id": "A", "regel": "nu", "redacties": [r("animalpolitico.com", ["IFCN actief"]), r("oud.es", ["IFCN actief"])]},
        {"id": "C", "regel": "jti", "redacties": [r("eldiario.es", ["JTI"]), r("larazon.es", ["JTI"])]},
        {"id": "D", "regel": "trust", "redacties": [r("folha.uol.com.br", ["Trust Project"], "pt")]},
        {"id": "E", "regel": "vernieuwing", "redacties": [r("publico.pt", ["IFCN vernieuwing"], "pt")]},
        {"id": "F", "regel": "eigen", "redacties": [r("lavanguardia.com", [])]}]}


def _keuzes(**regels):
    return {"datum": "2026-11-02",
            "regels": {"efcsn": "ja", "jti": "ja", "trust": "ja", "vernieuwing": "ja", "strengste": "ja", "eigen": "ja",
                       **regels},
            "redacties": {"animalpolitico.com": {"keuze": "twijfel"}, "oud.es": {"keuze": "goed"},
                          "eldiario.es": {"keuze": "goed"}, "larazon.es": {"keuze": "goed"},
                          "folha.uol.com.br": {"keuze": "goed"}, "publico.pt": {"keuze": "goed"},
                          "lavanguardia.com": {"keuze": "goed"}},
            "adressen": {"toelichting": "", "oud.es": {"adressen": ["nieuw.es"], "waarom": ""}}}


def test_a_mark_the_po_accepted_makes_a_chosen_newsroom_good():
    tekens = br.tekens_uit(_voorstel(), _keuzes())
    assert tekens["larazon.es"] == ["JTI, PO 2026-11-02"]
    assert tekens["folha.uol.com.br"] == ["Trust Project, PO 2026-11-02"]
    assert tekens["publico.pt"] == ["IFCN vernieuwing, PO 2026-11-02"]
    lijst = _lijst(tekens)
    assert _b("https://www.larazon.es/x", lijst)["band"] == "goed"
    assert _b("https://www1.folha.uol.com.br/x", lijst)["band"] == "goed"
    assert _b("https://www.uol.com.br/x", lijst)["band"] is None  # alleen het deel van de site met het teken


def test_a_newsroom_without_a_mark_or_with_doubt_gets_no_band():
    """PO 2026-11-02: alleen Lin e.a. en de tekens; groep F zonder band, ook als er een keuze staat."""
    tekens = br.tekens_uit(_voorstel(), _keuzes())
    assert "lavanguardia.com" not in tekens and "animalpolitico.com" not in tekens
    lijst = _lijst(tekens)
    assert _b("https://www.lavanguardia.com/x", lijst)["band"] is None
    assert _b("https://www.animalpolitico.com/x", lijst)["band"] is None


def test_a_mark_whose_rule_the_po_declined_does_not_count():
    tekens = br.tekens_uit(_voorstel(), _keuzes(vernieuwing="nee"))
    assert "publico.pt" not in tekens and "larazon.es" in tekens


def test_a_mark_never_beats_a_lower_judgment():
    """Twijfel versoepelt nooit: Lin e.a. 0,60 (wisselend) en een JTI-certificaat blijft wisselend."""
    lijst = _lijst(br.tekens_uit(_voorstel(), _keuzes()))
    uit = _b("https://www.eldiario.es/x", lijst)
    assert uit["band"] == "wisselend" and ["goed", "JTI, PO 2026-11-02"] in uit["bronnen"]


def test_a_corrected_address_replaces_the_one_in_the_proposal():
    tekens = br.tekens_uit(_voorstel(), _keuzes())
    assert "oud.es" not in tekens and tekens["nieuw.es"] == ["IFCN actief, PO 2026-11-02"]


def test_a_chosen_newsroom_without_an_accepted_mark_is_refused():
    voorstel = _voorstel()
    voorstel["groepen"][1]["redacties"][1]["tekens"] = []
    with pytest.raises(ValueError):
        br.tekens_uit(voorstel, _keuzes())


def test_the_po_choices_on_disk_give_40_newsrooms_and_none_from_group_f():
    voorstel = json.loads(br.VOORSTEL.read_text(encoding="utf-8"))
    keuzes = json.loads(br.KEUZES.read_text(encoding="utf-8"))
    tekens = br.tekens_uit(voorstel, keuzes)
    f = {r["domein"] for g in voorstel["groepen"] if g["id"] == "F" for r in g["redacties"]}
    assert not f & set(tekens)
    assert "animalpolitico.com" not in tekens and "eldiario.es" not in tekens
    assert "greenefact.sapo.pt" in tekens and "agencialupa.org" in tekens and "greenefact.pt" not in tekens
    assert len(tekens) == 42  # 40 redacties, twee met een tweede adres


def test_the_coverage_per_language_counts_sites_by_country_domain():
    sites = _lijst({"larazon.es": ["JTI, PO"], "folha.uol.com.br": ["Trust Project, PO"]})["sites"]
    tel = br.per_taal(sites)
    assert tel["es"]["goed"] == 1 and tel["pt"]["goed"] == 1 and tel["es"]["wisselend"] == 1  # eldiario.es
    assert tel["de"] == {"goed": 0, "wisselend": 0, "laag": 0}


def test_the_check_refuses_a_source_list_of_another_version(tmp_path, monkeypatch):
    oud = dict(_lijst())
    oud["_meta"] = {**oud["_meta"], "versie": "bronnen-v2"}
    pad = tmp_path / "bronnen.json"
    pad.write_text(json.dumps(oud), encoding="utf-8")
    monkeypatch.setattr(br, "BESTAND", pad)
    bc.herkomstlijst.cache_clear()
    try:
        with pytest.raises(bc.VersieFout):
            bc.herkomstlijst()
    finally:
        bc.herkomstlijst.cache_clear()


# --- versie 4: de tekens uit de volle lijsten, in alle talen (#32.29d) ----------------------------

IFCN_TSV = ("naam\twebsite\tstatus\tsinds\nPesaCheck\thttps://pesacheck.org\tvernieuwing\t2023-01-01\n"
            "Kenya Check\tWww.kenyacheck.co.ke\tactief\t2025-01-01\nOud\thttps://oud.example\tverlopen\t2019-01-01\n"
            "Leeg\t\tactief\t2025-01-01\n")
EFCSN_TSV = "profiel\twebsite\nfaktisk\thttps://www.faktisk.no/\n"
JTI_TSV = ("naam\tland\tsinds\tverloopt\tsites\tmet de hand\nLRT\tLithuania\t2025-01-01\t2027-01-01\tlrt.lt\t\n"
           "FMM\tFrance\t2025-01-01\t2027-01-01\trfi.fr france24.com\tja\nGeen\tTunisia\t2026-01-01\t2028-01-01\t\t\n")
TRUST_TSV = ("naam\tslug\twikidata\tsite\ttitel\tpast\nHeraldo\theraldo\tQ1\theraldo.es\tHeraldo de Aragón\tja\n"
             "WMTW\twmtw\tQ2\tmeta.wikimedia.org\tMain Page\tnee\n")


def _lijsten(twijfel=frozenset()):
    return br.tekens_lijsten(IFCN_TSV, EFCSN_TSV, JTI_TSV, TRUST_TSV, twijfel)


def test_every_accepted_mark_counts_in_every_language():
    tekens = _lijsten()
    assert tekens["pesacheck.org"] == ["IFCN vernieuwing"] and tekens["kenyacheck.co.ke"] == ["IFCN"]
    assert tekens["faktisk.no"] == ["EFCSN"] and tekens["lrt.lt"] == ["JTI"] and tekens["france24.com"] == ["JTI"]
    assert tekens["heraldo.es"] == ["Trust Project"]
    lijst = _lijst(tekens)
    assert _b("https://pesacheck.org/x", lijst)["band"] == "goed" and _b("https://www.lrt.lt/x", lijst)["band"] == "goed"


def test_an_expired_ifcn_member_and_a_trust_site_whose_title_does_not_fit_get_no_mark():
    tekens = _lijsten()
    assert "oud.example" not in tekens and "meta.wikimedia.org" not in tekens and "" not in tekens


def test_a_newsroom_the_po_doubted_gets_no_mark_from_a_list():
    """Twijfel versoepelt nooit: de keuze *twijfel* van de PO (#32.29) gaat voor een teken uit een lijst."""
    assert "lrt.lt" not in _lijsten(frozenset({"lrt.lt"}))


def test_a_mark_from_a_list_still_never_beats_a_lower_judgment():
    tekens = {**_lijsten(), "eldiario.es": ["JTI"]}
    assert _b("https://www.eldiario.es/x", _lijst(tekens))["band"] == "wisselend"  # Lin e.a. 0,60


# --- versie 5: Wikinews in alle talen van V1 zoals in het Engels (B58, #32.42) ---------------------

def test_wikinews_in_spanish_portuguese_and_german_is_reliable_as_in_english():
    v4 = {"_meta": {"versie": "bronnen-v4", "grenzen": {}}, "sites": {
        "wikinews.org": [["goed", "Lin e.a. 0.75"], ["laag", "Wikipedia"]], "en.wikinews.org": [["goed", "Lin e.a. 0.85"]]}}
    v5 = br.met_po_banden(v4, br.PO_BANDEN, "2026-11-05")
    assert v5["_meta"]["versie"] == "bronnen-v5" and bl.vastgelegd(v5)
    for taal in ("es", "pt", "de", "en"):
        assert br.beoordeel(f"https://{taal}.wikinews.org/wiki/X", v5["sites"])["band"] == "goed"
    assert br.beoordeel("https://fr.wikinews.org/wiki/X", v5["sites"])["band"] == "laag"  # alleen wat de PO koos
    assert "B58" in br.beoordeel("https://es.wikinews.org/wiki/X", v5["sites"])["bronnen"][0][1]


def test_version_five_names_only_wikinews_of_the_languages_of_v1_then():
    assert br.VERSIE_V5 == "bronnen-v5" and br.BESTAND_V5.name == "bronnen-v5.json"
    assert set(br.PO_BANDEN) == {"es.wikinews.org", "pt.wikinews.org", "de.wikinews.org"}


# --- versie 6: publieke omroepen (B64) en Wikinews in het Nederlands en Frans (B58, B63) ----------------

def _v5():
    return {"_meta": {"versie": "bronnen-v5", "grenzen": {}, "vingerafdruk": "abc"}, "sites": {
        "orf.at": [["goed", "EBU, RSF AUT 79.4"], ["wisselend", "Lin e.a. 0.60"]],
        "omroep.example": [["goed", "EBU, RSF XYZ 72.0"], ["wisselend", "Lin e.a. 0.55"]],
        "zwak.example": [["goed", "EBU, RSF XYZ 81.0"], ["laag", "Lin e.a. 0.35"]],
        "krant.example": [["wisselend", "Lin e.a. 0.64"]],
        "wikinews.org": [["goed", "Lin e.a. 0.75"], ["laag", "Wikipedia"]]}}


def test_a_public_broadcaster_of_the_ebu_in_a_free_country_is_reliable_even_if_lin_says_mixed():
    v6 = br.met_omroepen(_v5(), br.PO_BANDEN_V6, "2026-11-08")
    assert v6["_meta"]["versie"] == "bronnen-v6" and v6["_meta"]["basis"] == "abc" and bl.vastgelegd(v6)
    orf = br.beoordeel("https://orf.at/stories/1", v6["sites"])
    assert orf["band"] == "goed" and any("B64" in waarom and "0.60" in waarom for _, waarom in orf["bronnen"])


def test_the_broadcaster_rule_never_lifts_a_low_judgment_a_lower_press_freedom_or_a_site_without_the_ebu():
    v6 = br.met_omroepen(_v5(), br.PO_BANDEN_V6, "2026-11-08")
    assert br.beoordeel("https://omroep.example/x", v6["sites"])["band"] == "wisselend"  # RSF onder 75
    assert br.beoordeel("https://zwak.example/x", v6["sites"])["band"] == "laag"  # Lin zegt laag
    assert br.beoordeel("https://krant.example/x", v6["sites"])["band"] == "wisselend"  # de grens blijft 0,65


def test_wikinews_in_dutch_and_french_is_reliable_as_in_the_other_languages_of_v1():
    v6 = br.met_omroepen(_v5(), br.PO_BANDEN_V6, "2026-11-08")
    for taal in ("nl", "fr"):
        assert br.beoordeel(f"https://{taal}.wikinews.org/wiki/X", v6["sites"])["band"] == "goed"
    assert br.beoordeel("https://it.wikinews.org/wiki/X", v6["sites"])["band"] == "laag"
    assert set(br.PO_BANDEN_V6) == {"nl.wikinews.org", "fr.wikinews.org"}


def test_version_six_keeps_its_name_and_the_broadcaster_rule():
    assert br.VERSIE_V6 == "bronnen-v6" and br.BESTAND_V6.name == "bronnen-v6.json" and br.OMROEP_RSF == 75.0


def test_version_seven_is_the_version_the_check_uses():
    """B69, PO 2026-11-09: "Ja, release v7"."""
    assert br.VERSIE == br.VERSIE_V7 == "bronnen-v7" and br.BESTAND == br.BESTAND_V7
    assert br.BESTAND.name == "bronnen-v7.json"


# --- versie 7: media die verhuisden (#32.66, PO 2026-11-09: "Ja, bouw v7") -------------------------------------------

def _v6():
    sites = {"francetvinfo.fr": [["goed", "Lin e.a. 0.85"]], "cnn.com": [["goed", "Lin e.a. 0.66"]],
             "nepkrant.example": [["laag", "Lin e.a. 0.20"]], "bbc.co.uk": [["goed", "Lin e.a. 0.80"]]}
    return {"_meta": {"versie": "bronnen-v6", "vingerafdruk": bl.vingerafdruk(sites)}, "sites": sites}


def test_a_homepage_that_redirects_to_an_unlisted_domain_is_a_move_candidate():
    sites = _v6()["sites"]
    assert br.verhuizing("francetvinfo.fr", "https://www.franceinfo.fr/", sites) == "franceinfo.fr"
    assert br.verhuizing("nepkrant.example", "https://m.nieuwe-nepkrant.co.uk/home", sites) == "nieuwe-nepkrant.co.uk"


def test_a_redirect_within_the_site_to_a_listed_site_to_a_consent_page_or_a_platform_is_no_move():
    sites = _v6()["sites"]
    assert br.verhuizing("francetvinfo.fr", "https://www.francetvinfo.fr/", sites) is None
    assert br.verhuizing("cnn.com", "https://edition.cnn.com/", sites) is None
    assert br.verhuizing("bbc.co.uk", "https://www.cnn.com/", sites) is None  # al met een eigen oordeel
    assert br.verhuizing("cnn.com", "https://consent.yahoo.com/v2/collectConsent", sites) is None
    assert br.verhuizing("cnn.com", "https://www.facebook.com/cnn", sites) is None
    assert br.verhuizing("cnn.com", None, sites) is None


def test_version_seven_gives_a_moved_site_the_judgments_of_its_old_address_and_changes_nothing_else():
    v6 = _v6()
    v7 = br.met_verhuizingen(v6, {"franceinfo.fr": "francetvinfo.fr"}, "2026-11-09")
    assert v7["_meta"]["versie"] == "bronnen-v7" and v7["_meta"]["basis"] == v6["_meta"]["vingerafdruk"]
    assert bl.vastgelegd(v7)
    nieuw = br.beoordeel("https://www.franceinfo.fr/vrai-ou-fake/x", v7["sites"])
    assert nieuw["band"] == "goed" and nieuw["bronnen"] == [["goed", "verhuisd van francetvinfo.fr: Lin e.a. 0.85"]]
    assert {k: v for k, v in v7["sites"].items() if k != "franceinfo.fr"} == v6["sites"]


def test_a_low_site_that_moves_stays_low_at_its_new_address():
    v7 = br.met_verhuizingen(_v6(), {"nieuwe-nepkrant.example": "nepkrant.example"}, "2026-11-09")
    assert br.beoordeel("https://nieuwe-nepkrant.example/", v7["sites"])["band"] == "laag"


def test_a_move_never_overwrites_a_judgment_of_its_own_or_comes_from_an_unknown_address():
    with pytest.raises(ValueError):
        br.met_verhuizingen(_v6(), {"cnn.com": "francetvinfo.fr"}, "2026-11-09")
    with pytest.raises(ValueError):
        br.met_verhuizingen(_v6(), {"franceinfo.fr": "onbekend.example"}, "2026-11-09")


def test_a_good_domain_taken_over_by_someone_else_loses_its_band_and_a_low_one_stays_low():
    """Verlopen domeinen met *goed* die nu een casino of spam tonen (huffpostbrasil.com, dailyherald.news): een zoekuitslag
    daarvan telde als goede bron. Een overgenomen *laag* domein blijft laag: twijfel versoepelt nooit."""
    v7 = br.met_verhuizingen(_v6(), {}, "2026-11-09", overgenomen={"cnn.com": "nu een casino"})
    assert br.beoordeel("https://cnn.com/x", v7["sites"])["band"] is None and "cnn.com" not in v7["sites"]
    assert v7["_meta"]["overgenomen"] == {"cnn.com": "nu een casino"} and bl.vastgelegd(v7)
    with pytest.raises(ValueError):
        br.met_verhuizingen(_v6(), {}, "2026-11-09", overgenomen={"nepkrant.example": "te koop"})


def test_the_reason_of_a_judgment_reads_the_same_at_a_moved_address():
    """Versie 7 zet "verhuisd van ..." voor de reden; wie de reden leest (IFCN, Lin e.a.), leest erdoorheen."""
    assert br.reden("verhuisd van poligrafo.sapo.pt: IFCN") == "IFCN"
    assert br.reden("verhuisd van francetvinfo.fr: Lin e.a. 0.85") == "Lin e.a. 0.85"
    assert br.reden("Lin e.a. 0.85") == "Lin e.a. 0.85" and br.reden("IFCN") == "IFCN"


def test_a_factchecker_that_moved_is_still_a_factchecker_in_the_check_and_on_the_first_day():
    """Polígrafo verhuisde van poligrafo.sapo.pt naar poligrafo.iol.pt: de controle ziet er nog steeds een
    IFCN-ondertekenaar in, en een meting als op de eerste dag laat de site nog steeds weg (#32.43)."""
    from doublecheck import speuren as sp
    from doublecheck import zoekcontrole as zc

    sites = {"poligrafo.sapo.pt": [["goed", "EFCSN"], ["goed", "IFCN"]], "francetvinfo.fr": [["goed", "Lin e.a. 0.85"]]}
    v6 = {"_meta": {"versie": "bronnen-v6", "vingerafdruk": bl.vingerafdruk(sites)}, "sites": sites}
    v7 = br.met_verhuizingen(v6, {"poligrafo.iol.pt": "poligrafo.sapo.pt", "franceinfo.fr": "francetvinfo.fr"},
                             "2026-11-09")
    res = zc.resultaten_uit({"web": {"results": [{"url": "https://poligrafo.iol.pt/x", "title": "t"}]}}, v7["sites"],
                            staat={"domeinen": {}})
    assert res[0]["factcheck"] is True and res[0]["band"] == "goed"
    hosts = sp.eerste_dag_hosts({"franceinfo.fr"}, v7["sites"])
    assert "poligrafo.iol.pt" in hosts and "franceinfo.fr" not in hosts  # franceinfo is een nieuwsmedium met Lin e.a.
