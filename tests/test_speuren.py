"""De speurstap gemeten als op de eerste dag (PLAN #32.40): zonder kring 1, zonder checks uit de database en zonder
factchecksites in de resultaten, één zoekvraag (A) tegen één zoekvraag met de speurstap (B)."""

import pytest

from doublecheck import speuren as sp


def test_on_the_first_day_fact_checkers_and_their_pages_are_gone_but_news_media_stay():
    domeinen = {"snopes.com", "afp.com"}
    assert sp.van_factchecker("https://www.snopes.com/fact-check/x/", domeinen)
    assert sp.van_factchecker("https://factuel.afp.com/doc.afp.com.123", domeinen)
    assert sp.van_factchecker("https://www.reuters.com/fact-check/abc", domeinen)
    assert sp.van_factchecker("https://theins.press/en/news/299171", domeinen)
    assert not sp.van_factchecker("https://www.reuters.com/world/europe/abc", domeinen)
    assert not sp.van_factchecker("https://www.euronews.com/2026/11/03/ukraine", domeinen)
    antwoord = {"web": {"results": [{"url": "https://www.snopes.com/a"}, {"url": "https://www.bbc.com/b"}]}}
    assert [r["url"] for r in sp.zonder(antwoord, domeinen)["web"]["results"]] == ["https://www.bbc.com/b"]


SITES = {"snopes.com": [["goed", "IFCN"], ["goed", "Lin e.a. 0.90"]], "fullfact.org": [["goed", "EFCSN"],
                                                                         ["goed", "Lin e.a. 0.88"]],
         "aosfatos.org": [["goed", "IFCN"]], "agencialupa.org": [["goed", "IFCN"]],
         "factcheck.afp.com": [["goed", "IFCN"]], "afp.com": [["goed", "EFCSN"], ["goed", "Lin e.a. 0.95"]],
         "noticias.uol.com.br": [["goed", "IFCN"]], "estadao.com.br": [["goed", "IFCN"]],
         "reuters.com": [["goed", "Lin e.a. 1.00"]], "boatos.org": [], "bbc.com": [["goed", "Lin e.a. 0.90"]]}


def test_every_member_of_the_ifcn_or_efcsn_is_gone_on_the_first_day_unless_it_also_makes_the_news():
    hosts = sp.eerste_dag_hosts({"snopes.com", "reuters.com", "boatos.org"}, SITES)
    assert {"snopes.com", "fullfact.org", "aosfatos.org", "agencialupa.org", "factcheck.afp.com", "boatos.org"} <= hosts
    assert not {"reuters.com", "afp.com", "noticias.uol.com.br", "estadao.com.br", "bbc.com"} & hosts
    assert {"afp.com", "noticias.uol.com.br", "estadao.com.br"} <= sp.NIEUWSMEDIA


def test_the_fact_check_section_of_a_news_medium_is_gone_but_its_news_stays():
    hosts = sp.eerste_dag_hosts({"snopes.com"}, SITES)
    for url in ("https://fullfact.org/conflict/ai-image-uss-lincoln-fire/", "https://www.snopes.com/tag/islam/",
                "https://www.agencialupa.org/checagem/2024/05/x/", "https://www.aosfatos.org/noticias/x/",
                "https://noticias.uol.com.br/confere/ultimas-noticias/2024/05/10/x.htm",
                "https://noticias.uol.com.br/comprova/ultimas-noticias/2024/x.htm",
                "https://www.estadao.com.br/estadao-verifica/casas-de-bombas-porto-alegre/",
                "https://g1.globo.com/fato-ou-fake/noticia/2024/x.ghtml", "https://factual.afp.com/doc.afp.com.A6EL49E",
                "https://www.ptinews.com/fact-detail/old-video/3750448", "https://www.efe.com/efe/espana/efeverifica/1"):
        assert sp.van_factchecker(url, hosts), url
    for url in ("https://noticias.uol.com.br/eleicoes/2024/10/06/x.htm", "https://www.estadao.com.br/politica/x/",
                "https://www.reuters.com/world/asia-pacific/icc-judges-2026-04-22/",
                "https://observador.pt/2026/11/06/pan-com-90-propostas/", "https://www.afp.com/en/news/x"):
        assert not sp.van_factchecker(url, hosts), url


def test_w2_is_a_fixed_half_of_the_wikinews_set():
    rijen = [{"id": f"w{i}", "set": "W2"} for i in range(200)] + [{"id": "o", "set": "O'"}]
    a, b = sp.kies(rijen, "W2", 100), sp.kies(list(reversed(rijen)), "W2", 100)
    assert len(a) == 100 and [r["id"] for r in a] == [r["id"] for r in b] and all(r["set"] == "W2" for r in a)


def _gelezen(i, truc="nagemaakt", nagedaan="medium", wie="Euronews"):
    return {"id": f"g{i}", "leesbaar": True, "factcheck": True, "truc": truc, "nagedaan": nagedaan, "wie": wie,
            "url": f"https://fc.org/{i}"}


def test_m_takes_only_checks_of_a_post_that_imitated_an_outlet_an_institution_or_a_company():
    gelezen = [_gelezen(1), _gelezen(2, nagedaan="persoon"), _gelezen(3, truc="valse context"),
               _gelezen(4, nagedaan="overheid of instelling"), {"id": "g5", "leesbaar": False}]
    claims = {f"g{i}": {"claim": f"claim {i}", "jaar": 2025, "url": f"https://fc.org/{i}"} for i in range(1, 6)}
    uit = sp.kies_m(gelezen, claims, n=10)
    assert [r["id"] for r in uit] == ["M:g1", "M:g4"]
    assert uit[0]["tekst"] == "Euronews\nclaim 1" and uit[0]["set"] == "M" and uit[0]["merk"] == "Euronews"


def test_the_brand_goes_above_the_claim_as_a_logo_would_but_never_the_fact_checkers_words():
    assert sp.met_merk("Se confirma el primer caso en Andorra", "La Vanguardia") == \
        ("La Vanguardia", "La Vanguardia\nSe confirma el primer caso en Andorra")
    assert sp.met_merk("Win a car!", "Range Rover Club on Facebook, impersonating Range Rover")[0] == "Range Rover Club"
    assert sp.met_merk("x", "Iran International TV (logo used); quote attributed to Mehdi Taj")[0] == \
        "Iran International TV"
    assert sp.met_merk("Time magazine chose him as Person of the Year", "Time magazine")[1] == \
        "Time magazine chose him as Person of the Year"


def test_w_merk_is_the_headline_under_the_name_of_the_outlet_only_from_the_last_week():
    feeds = {"BBC News": [("Storm hits Spain", "2026-11-03"), ("Old story", "2026-10-01"), ("Vote in Chile", "2026-11-02")]}
    uit = sp.w_merk_uit(feeds, per_merk=10, sinds="2026-10-28")
    assert [r["tekst"] for r in uit] == ["BBC News\nStorm hits Spain", "BBC News\nVote in Chile"]
    assert all(r["set"] == "W-merk" and r["merk"] == "BBC News" for r in uit)


def _rij(i, set_, arm, kleur=None, uitkomst="onzeker", speur=()):
    return {"id": f"{set_}{i}", "set": set_, "arm": arm, "kleur": kleur, "uitkomst": uitkomst,
            "speurstap": [{"soort": s, "vraag": "q", "site": "x.com" if s == "eigen site" else "", "gevonden": g}
                          for s, g in speur], "kosten": 0.01}


def test_what_must_be_read_is_every_red_and_orange_and_every_green_on_a_false_message():
    assert sp.moet_lezen(_rij(1, "O'", "B", "rood", speur=[("echt nieuws", 3)]))
    assert sp.moet_lezen(_rij(1, "M", "A", "groen"))
    assert sp.moet_lezen(_rij(1, "W2", "A", "oranje"))
    assert not sp.moet_lezen(_rij(1, "W2", "A", "groen"))
    assert not sp.moet_lezen(_rij(1, "O'", "B", "rood"))  # zonder speurstap is B gelijk aan A, met het label van A


def test_counting_is_refused_while_a_red_has_no_label():
    rijen = [_rij(1, "O'", "A", "rood"), _rij(1, "O'", "B", "rood")]
    with pytest.raises(sp.Weigering):
        sp.telling(rijen, {})


def test_the_bars_compare_b_with_a_on_the_same_messages():
    rijen = []
    for i in range(12):  # O': B vindt bij 12 berichten een rood met bewijs dat A niet had
        rijen += [_rij(i, "O'", "A"), _rij(i, "O'", "B", "rood", "klopt niet", [("echt nieuws", 5)])]
    rijen += [_rij(0, "W2", "A", "groen", "klopt"), _rij(0, "W2", "B", "groen", "klopt")]
    rijen += [_rij(1, "W-merk", "A"), _rij(1, "W-merk", "B", "rood", "klopt niet", [("eigen site", 0)])]
    labels = {f"O'{i}#B": "bewijst" for i in range(12)} | {"W-merk1#B": "vals"}
    uit = sp.telling(rijen, labels)
    assert uit["eisen"]["O' en M: B minstens 10 meer rood of oranje met bewijs"] is True
    assert uit["eisen"]["W2 en W-merk: B niet meer vals alarm dan A"] is False
    assert uit["eisen"]["W2 en W-merk: B hoogstens 1 vals alarm"] is True
    assert uit["eigen site"]["W-merk"] == {"gezocht": 1, "niets gevonden": 1}
