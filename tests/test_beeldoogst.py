"""De volle beeldindex, de oogst (PLAN #32.35): wat er geoogst wordt, de proef, wat er van een beeld blijft, en de
schatting voor de rest met de regels vooraf."""

from doublecheck import beeldoogst as bo


def test_the_harvest_skips_the_pool_and_the_excluded_sites():
    urls = {"a.org/1": "https://a.org/1", "a.org/2": "https://a.org/2", "euvsdisinfo.eu/r": "https://euvsdisinfo.eu/r",
            "b.org/3": "https://www.b.org/3"}
    uit = bo.te_oogsten(urls, klaar={"a.org/2"}, uitgesloten=frozenset({"euvsdisinfo.eu"}))
    assert uit == ["https://a.org/1", "https://www.b.org/3"]


def test_the_trial_is_a_fixed_random_choice_and_never_depends_on_the_order():
    urls = [f"https://s{i % 7}.org/{i}" for i in range(500)]
    keuze = bo.proef_keuze(urls, 50, zaad=3235)
    assert len(keuze) == 50 == len(set(keuze)) and keuze == bo.proef_keuze(list(reversed(urls)), 50, zaad=3235)
    assert bo.proef_keuze(urls[:10], 50, zaad=3235) == sorted(urls[:10])


def test_only_the_points_of_viral_images_are_kept_and_an_unknown_image_is_never_viral():
    beelden = {"https://a.org/1": ["x.jpg", "y.jpg", "z.jpg"], "https://a.org/2": ["w.jpg"]}
    rollen = [{"artikel": "https://a.org/1", "beelden": ["x.jpg", "y.jpg", "z.jpg"],
               "rollen": ["viraal", "huisstijl", "onbekend"]}]
    assert bo.te_wissen(beelden, rollen) == [("https://a.org/1", "y.jpg"), ("https://a.org/1", "z.jpg"),
                                             ("https://a.org/2", "w.jpg")]  # 2 kreeg geen antwoord


def _artikel(host, status=200, seconden=10.0, beelden=2):
    return {"url": f"https://{host}/{seconden}", "host": host, "status": status, "seconden": seconden,
            "beelden": [f"b{i}" for i in range(beelden)]}


def test_the_estimate_takes_the_slowest_site_or_the_total_work_over_the_threads():
    artikelen = [_artikel("factly.in", seconden=s) for s in (10.0, 12.0, 11.0)] + [_artikel("b.org", seconden=2.0)]
    rollen = [{"artikel": a["url"], "beelden": a["beelden"], "rollen": ["viraal", "huisstijl"]} for a in artikelen]
    uit = bo.schatting(artikelen, rollen, kosten=0.0008, rest_per_host={"factly.in": 3600, "b.org": 100, "c.org": 50},
                       bytes_per_viraal=80_000, draden=12)
    assert uit["duur rest, uur"] == 11.0  # 3600 × 11 s; c.org krijgt de mediaan van alle artikelen
    assert uit["aandeel viraal"] == 0.5 and uit["kosten per artikel met beelden"] == 0.0002
    assert uit["opslag rest, GB"] == round(3750 * 2 * 0.5 * 80_000 / 1e9, 2)
    assert not any(uit["plan moet veranderen"].values())


def test_the_rules_fixed_beforehand_stop_the_full_harvest():
    artikelen = [_artikel("a.org", status=403, beelden=0)] * 3 + [_artikel("a.org", seconden=30.0)]
    rollen = [{"artikel": artikelen[-1]["url"], "beelden": ["b0", "b1"], "rollen": ["viraal", "viraal"]}]
    uit = bo.schatting(artikelen, rollen, kosten=0.001, rest_per_host={"a.org": 40_000}, bytes_per_viraal=600_000,
                       draden=12)
    regels = uit["plan moet veranderen"]
    assert regels["meer dan 25% geen 200"] and regels["kosten per artikel meer dan twee keer $0,0002"]
    assert regels["duur rest meer dan 3 dagen"] and regels["opslag rest meer dan 10 GB"]


def test_the_full_harvest_takes_every_article_and_the_trial_only_its_choice():
    urls = [f"https://s{i % 7}.org/{i}" for i in range(500)]
    assert bo.werk_voor(urls, 50, alles=True) == sorted(set(urls))
    assert bo.werk_voor(urls, 50, alles=False) == bo.proef_keuze(urls, 50)
    assert bo.GRENZEN["alles"] > bo.GRENZEN["proef"] == bo.GRENS_PROEF


def test_once_a_batch_is_answered_only_its_articles_lose_their_non_viral_points():
    kaart = [{"custom_id": "a", "artikel": "https://a.org/1", "batch": "b1"},
             {"custom_id": "b", "artikel": "https://a.org/2", "batch": "b2"}]
    beelden = {"https://a.org/1": ["x.jpg", "y.jpg"], "https://a.org/2": ["w.jpg"]}
    rollen = [{"artikel": "https://a.org/1", "beelden": ["x.jpg", "y.jpg"], "rollen": ["viraal", "huisstijl"]}]
    assert bo.te_wissen_voor_batch(kaart, "b1", beelden, rollen) == [("https://a.org/1", "y.jpg")]
    assert bo.te_wissen_voor_batch(kaart, "b2", beelden, rollen) == [("https://a.org/2", "w.jpg")]  # zonder antwoord


def test_factly_is_left_out_of_the_rest_of_the_harvest():
    """PO 2026-11-03: FACTLY trekt het corpus naar India; de eigen artikelen van N staan al in de pool."""
    urls = {"factly.in/1": "https://factly.in/1", "a.org/2": "https://a.org/2"}
    assert bo.te_oogsten(urls, klaar=set(), uitgesloten=bo.OVERGESLAGEN) == ["https://a.org/2"]
    assert "factly.in" in bo.OVERGESLAGEN and bo.OVERGESLAGEN >= __import__("doublecheck.beeldindexmeting",
                                                                            fromlist=["x"]).UITGESLOTEN


def test_a_restart_redoes_only_the_articles_whose_roles_were_never_asked():
    artikelen = [{"url": "https://a.org/1", "beelden": ["x.jpg"]}, {"url": "https://a.org/2", "beelden": []},
                 {"url": "https://a.org/3", "beelden": ["y.jpg"]}]
    kaart = [{"artikel": "https://a.org/1", "status": "gevraagd"}]
    assert bo.al_klaar(artikelen, kaart) == {"https://a.org/1", "https://a.org/2"}  # 3 zat nog in de wachtrij


def test_an_article_done_twice_counts_once_in_the_estimate():
    a = {"url": "https://a.org/1", "host": "a.org", "status": 200, "seconden": 10.0, "beelden": ["x"]}
    eens = bo.schatting([a], [], 0.0, {"a.org": 10}, 1.0)
    assert bo.schatting([a, {**a, "seconden": 20.0}], [], 0.0, {"a.org": 10}, 1.0)["artikelen"] == eens["artikelen"] == 1
