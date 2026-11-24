"""Linkrot meten (PLAN #25.6): werken de bonnetjes nog?

Elke uitslag rust op een link naar de check van een redactie. Hoeveel daarvan
dood zijn, bepaalt hoe urgent het archief is (#24.7). De indeling is streng in
één richting: alleen wat aantoonbaar weg is telt als dood; een blokkade door
botbescherming of een time-out is "onduidelijk", nooit "levend".
"""

from doublecheck import linkrot as lr


def test_alive_dead_and_unclear_are_kept_apart():
    assert lr.klasseer(200, "https://x.org/check/1", "https://x.org/check/1") == "levend"
    assert lr.klasseer(404, "https://x.org/check/1", "https://x.org/check/1") == "dood"
    assert lr.klasseer(410, "https://x.org/a", "https://x.org/a") == "dood"
    for status in (401, 403, 429, 451, 503):
        assert lr.klasseer(status, "https://x.org/a", "https://x.org/a") == "onduidelijk"
    assert lr.klasseer(None, None, "https://x.org/a", fout="time-out") == "onduidelijk"
    assert lr.klasseer(None, None, "https://weg.example/a", fout="domein") == "dood"


def test_a_redirect_to_the_front_page_is_a_soft_death():
    """Veel sites sturen een verdwenen artikel door naar de voorpagina, met 200."""
    assert lr.klasseer(200, "https://x.org/", "https://x.org/fact-check/vaccine-claim") == "zacht-dood"
    assert lr.klasseer(200, "https://x.org/nl/", "https://x.org/fact-check/vaccine-claim") == "zacht-dood"
    assert lr.klasseer(200, "https://www.x.org/fact-check/vaccine-claim/", "http://x.org/fact-check/vaccine-claim") == "levend"


def test_the_sample_is_reproducible():
    urls = [f"https://x.org/{i}" for i in range(1000)]
    assert lr.steekproef(urls, 50, seed=7) == lr.steekproef(urls, 50, seed=7)
    assert len(set(lr.steekproef(urls, 50, seed=7))) == 50


def test_the_report_gives_an_upper_bound_for_the_dead_share():
    uitkomsten = ["levend"] * 90 + ["dood"] * 6 + ["zacht-dood"] * 2 + ["onduidelijk"] * 2
    r = lr.rapport(uitkomsten)
    assert r["dood_totaal"] == 8 and r["n"] == 100
    assert 0.08 < r["bovengrens95_dood"] < 0.16
    assert r["onduidelijk"] == 2


def test_a_doubled_address_is_never_called_dead():
    """BENCHMARK §110: 16 adressen in de feed dragen een tweede adres achter
    het eerste ("https://factly.in/a/https://factly.in/a/"). Een 404 daarop
    zegt iets over de feed, niet over de redactie, en "offline" zou een
    foute uitspraak over haar werk zijn (#25.9). Dood wordt onduidelijk;
    werkt het adres toch, dan is het gewoon levend."""
    for kapot in ("https://factly.in/a-check/https://factly.in/a-check/",
                  "https://gujarati.factcrescendo.com/https://www.malayalam.factcrescendo.com/b/",
                  "http://x.org/c/http://x.org/c/"):
        assert lr.klasseer(404, kapot, kapot) == "onduidelijk", kapot
        assert lr.klasseer(None, None, kapot, fout="domein") == "onduidelijk", kapot
        assert lr.klasseer(200, "https://factly.in/", kapot) == "onduidelijk", kapot
        assert lr.klasseer(200, kapot, kapot) == "levend", kapot
