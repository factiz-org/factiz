"""De lezer met alle uitkomsten op gewone tekst en de bewaking (PLAN #32.31): de sets zoals vooraf vastgelegd, één
bericht door dezelfde functies als `/check`, het antwoord uit de batch door `na_lezen`, en de eisen."""

import dataclasses
import json

import pytest

from doublecheck import uitkomsten as uk
from doublecheck import zoekcontrole as zc
from doublecheck.config import load_config

SITES = {"nytimes.com": [["goed", "Lin e.a. 0.86"]], "cnn.com": [["goed", "Lin e.a. 0.75"]],
         "factcheck.org": [["goed", "IFCN"]]}
CHECKS = [{"claim": "c1", "tekst": "Een bewering", "redactie": "BOOM", "oordeel": "onwaar", "datum": "2026-08-01",
           "url": "https://www.boomlive.in/x", "beeld": False}]


def _config():
    c = load_config()
    return dataclasses.replace(c, berichtcontrole=dataclasses.replace(c.berichtcontrole, lezer="lezer-v6", beeld=False))


def _rij(i, taal="en", bron="social media", label="No", tekst=None, stemmen=("No", "No", "No")):
    return {"nr": i, "text": tekst or f"bericht {i}", "language": taal, "source": bron, "majority_label": label,
            "annotator1": stemmen[0], "annotator2": stemmen[1], "annotator3": stemmen[2]}


def test_the_plain_text_set_takes_clear_majorities_in_english_from_social_media_without_round_6_or_duplicates():
    rijen = ([_rij(i, label="No") for i in range(60)] + [_rij(i, label="Yes") for i in range(60, 90)]
             + [_rij(90, taal="hi"), _rij(91, bron="fact-check"), _rij(92, label="No Majority"),
                _rij(93, tekst="bericht 5"), _rij(94, tekst="  BERICHT   6 ")])
    toets, ontwikkel = uk.kies_g(rijen, uitgesloten={7}, n_geen=20, n_wel=5, n_ontwikkel=3, zaad=1)
    assert [s["label"] for s in toets].count("geen bewering") == 20 and len(toets) == 25
    assert [s["label"] for s in ontwikkel].count("bewering") == 3 and len(ontwikkel) == 6
    nummers = [int(s["id"].split("-")[1]) for s in toets + ontwikkel]
    assert len(set(nummers)) == 31 and not {7, 90, 91, 92, 93, 94} & set(nummers)
    assert {s["set"] for s in toets} == {"G"} and {s["set"] for s in ontwikkel} == {"G-ontwikkel"}
    assert toets == uk.kies_g(list(reversed(rijen)), uitgesloten={7}, n_geen=20, n_wel=5, n_ontwikkel=3, zaad=1)[0]
    assert all(s["eenstemmig"] for s in toets)


class _Blok:
    def __init__(self, tekst):
        self.type, self.text = "text", tekst


class _Gebruik:
    input_tokens, output_tokens, cache_read_input_tokens, cache_creation_input_tokens = 3_000, 200, 0, 0
    server_tool_use = None


class _Bericht:
    def __init__(self, d):
        self.content, self.usage = [_Blok(json.dumps(d))], _Gebruik()


def _brave(*urls):
    return {"web": {"results": [{"url": u, "title": f"t{i}", "description": f"f{i}"} for i, u in enumerate(urls)]}}


def test_one_message_is_prepared_by_the_same_functions_as_the_check():
    gezocht, checks = [], []
    zoek = lambda q: gezocht.append(q) or _brave("https://www.nytimes.com/a")  # noqa: E731
    s = {"id": "G:t-00001", "set": "G", "tekst": "Good morning to all of you", "datum": "2019–2021"}
    voor = uk.voorbereiden(s, _config(), zoek, lambda t: None, SITES,
                           lambda tekst, verborgen: checks.append(verborgen) or CHECKS)
    assert voor["route"] == "zoeken" and gezocht == [zc.zoekvraag(s["tekst"])] and checks == [frozenset()]
    assert voor["verzoek"] == zc.leesverzoek(s["tekst"], voor["resultaten"], s["datum"], _config(), checks=CHECKS)
    assert "tools" not in voor["verzoek"]  # het model zoekt nooit zelf


def test_the_first_ring_answers_without_a_search_and_unknown_fake_news_skips_it_and_its_fact_checkers():
    snel = {"oordeel": "klopt niet", "kleur": "rood", "bronnen": []}
    gezocht = []
    db = uk.voorbereiden({"id": "W:1", "set": "W", "tekst": "x", "datum": None}, _config(),
                         lambda q: gezocht.append(q), lambda t: snel, SITES, lambda tekst, verborgen: [])
    assert db["route"] == "database" and db["rij"]["uitkomst"] == "klopt niet" and gezocht == []
    gevraagd, checks = [], []
    zoek = lambda q: _brave("https://www.factcheck.org/x", "https://www.nytimes.com/a")  # noqa: E731
    o = uk.voorbereiden({"id": "O:gfc-9", "set": "O'", "tekst": "Nep.", "datum": None, "verborgen": ["gfc-9", "gfc-10"]},
                        _config(), zoek, lambda t: gevraagd.append(t) or snel, SITES,
                        lambda tekst, verborgen: checks.append(verborgen) or [])
    assert gevraagd == [] and checks == [frozenset({"gfc-9", "gfc-10"})]
    assert [r["site"] for r in o["resultaten"]] == ["nytimes.com"]


def test_the_answer_from_the_batch_goes_through_the_same_reading_as_the_check_at_the_batch_price():
    s = {"id": "G:t-00001", "set": "G", "tekst": "Good morning to all of you", "datum": None}
    voor = uk.voorbereiden(s, _config(), lambda q: _brave("https://www.nytimes.com/a", "https://edition.cnn.com/b"),
                           lambda t: None, SITES, lambda tekst, verborgen: [])
    d = {"oordeel": "geen bewering", "steunt": [1, 2], "spreekt_tegen": [], "uitleg": "Een groet.", "over_beeld": False,
         "checks": [], "vorm": "zelf", "detail": {"woorden": "", "juist": "", "nr": 0}}
    rij = uk.afmaken(s, voor, _Bericht(d), _config())
    assert rij["uitkomst"] == "geen bewering" and rij["kleur"] is None and rij["route"] == "zoeken"
    assert rij["kosten"] == pytest.approx((3_000 * 2.0 + 200 * 10.0) / 2 / 1e6 + zc.ZOEKPRIJS)
    assert rij["vraag"] == uk.vingerafdruk("lezer-v6") and [b["site"] for b in rij["bronnen"]] == ["nytimes.com",
                                                                                                 "cnn.com"]
    assert "fragment" not in json.dumps(rij["bronnen"])  # van de zoekresultaten alleen adres, site, titel en band


def _r(id_, set_, kleur=None, uitkomst="onzeker", label=None, vraag="v"):
    return {"id": id_, "set": set_, "kleur": kleur, "uitkomst": uitkomst, "label": label, "kosten": 0.01,
            "vraag": vraag}


def _toets(geen_bewering=80, rood_g=0, vals_w=3, groen_w=210, maar_w=1, groen_o=1, alarm_o=33, groen_d=0):
    rijen, labels = [], {}
    for i in range(100):
        rijen.append(_r(f"G:{i}", "G", "rood" if i < rood_g else None,
                        "geen bewering" if i < geen_bewering else "onzeker", "geen bewering"))
        labels.update({f"G:{i}": "vals"} if i < rood_g else {})
    for i in range(300):
        kleur = "oranje" if i < vals_w else ("groen" if i < vals_w + groen_w else None)
        uitkomst = "klopt grotendeels" if vals_w + groen_w <= i < vals_w + groen_w + maar_w else "onzeker"
        rijen.append(_r(f"W:{i}", "W", kleur, uitkomst))
        if i < vals_w or uitkomst == "klopt grotendeels":
            labels[f"W:{i}"] = "vals"
    for i in range(100):
        kleur = "groen" if i < groen_o else ("rood" if i < groen_o + alarm_o else None)
        rijen.append(_r(f"O:{i}", "O'", kleur))
        labels.update({f"O:{i}": "vals"} if i < groen_o else {})
    for i in range(40):
        rijen.append(_r(f"D:{i}", "D", "groen" if i < groen_d else None))
        labels.update({f"D:{i}": "vals"} if i < groen_d else {})
    return rijen, labels


def test_the_requirements_are_those_set_in_advance():
    assert all(uk.telling(*_toets())["eisen"].values())
    for te_veel in ({"geen_bewering": 79}, {"rood_g": 1}, {"vals_w": 4}, {"groen_w": 209}, {"maar_w": 2},
                    {"groen_o": 2}, {"alarm_o": 32}, {"groen_d": 1}):
        eisen = uk.telling(*_toets(**te_veel))["eisen"]
        assert list(eisen.values()).count(False) == 1, te_veel


def test_a_red_plain_text_counts_against_the_requirement_whatever_its_label():
    rijen, labels = _toets(rood_g=1)
    labels["G:0"] = "terecht"
    assert not uk.telling(rijen, labels)["eisen"]["G: nooit rood of oranje"]


def test_the_count_refuses_while_something_that_counts_has_no_label_or_the_question_changed():
    rijen, labels = _toets(groen_d=1)
    del labels["D:0"]
    with pytest.raises(uk.Weigering):
        uk.telling(rijen, labels)
    rijen, labels = _toets()
    rijen[0]["vraag"] = "anders"
    with pytest.raises(uk.Weigering):
        uk.telling(rijen, labels)


def test_a_label_that_does_not_exist_is_refused():
    with pytest.raises(uk.Weigering):
        uk.lees_labels({"toelichting": "", "oordelen": [{"id": "W:1", "label": "misschien"}]})


def test_the_run_stops_before_the_cap():
    assert uk.mag_nog(5.0, 10) and not uk.mag_nog(5.9, 10)


def test_the_question_has_a_fingerprint_that_changes_with_the_question():
    assert uk.vingerafdruk("lezer-v6") != uk.vingerafdruk("lezer-v5") and len(uk.vingerafdruk("lezer-v6")) == 12


def test_the_measurement_borrows_the_reader_from_the_core():
    assert uk.zc is zc


# --- de tweede ronde: lezer-v7 (#32.32) ----------------------------------------------------------------------------

def test_the_second_round_takes_only_unanimous_plain_texts_that_were_not_used_before():
    rijen = ([_rij(i, label="No") for i in range(40)] + [_rij(40, label="No", stemmen=("No", "No", "Yes"))]
             + [_rij(i, label="Yes", stemmen=("Yes", "Yes", "Yes")) for i in range(41, 50)])
    toets, _ = uk.kies_g(rijen, uitgesloten={1, 2}, n_geen=30, n_wel=0, n_ontwikkel=0, zaad=3, eenstemmig=True)
    nummers = {int(s["id"].split("-")[1]) for s in toets}
    assert len(toets) == 30 and not {1, 2, 40} & nummers and all(s["eenstemmig"] for s in toets)


def _nieuws(i, jaar="2016", titel=None, tekst=None):
    return {"sleutel": f"wikinews:en:{i}", "titel": titel or f"Kop {i}", "datum": f"{jaar}-05-0{i % 9 + 1}",
            "url": f"https://en.wikinews.org/wiki/{i}",
            "tekst": tekst if tekst is not None else (f"Kop {i}\nMonday, May 2 Related articles Collaborate! Writing an "
                                                      f"article The council voted on Monday to close the bridge. It "
                                                      f"will reopen in June after repairs. A third sentence follows.")}


def test_true_news_is_the_headline_and_the_start_of_a_wikinews_article_from_2010_to_2024():
    rijen = ([_nieuws(i) for i in range(30)] + [_nieuws(30, jaar="2008"), _nieuws(31, jaar="2025"),
             _nieuws(32, titel="Wikinews interviews a candidate"), _nieuws(33, tekst="Kop 33\nzonder het begin")])
    w2 = uk.kies_w2(rijen, n=20, zaad=1)
    assert len(w2) == 20 and {s["set"] for s in w2} == {"W2"}
    assert not {"wikinews:en:30", "wikinews:en:31", "wikinews:en:32", "wikinews:en:33"} & {s["bron"] for s in w2}
    s = w2[0]
    assert s["tekst"].startswith(s["titel"] + "\n") and "Writing an article" not in s["tekst"]
    assert s["tekst"].endswith("after repairs.") and len(s["tekst"]) <= len(s["titel"]) + 1 + uk.LEAD
    assert s["datum"].startswith("2016") and w2 == uk.kies_w2(list(reversed(rijen)), n=20, zaad=1)


FEED = """<?xml version="1.0"?><rss><channel><title>The Beaverton</title>
<item><title>Local man &amp; his dog elected mayor</title><link>https://www.thebeaverton.com/a</link>
<pubDate>Mon, 02 Nov 2026 10:00:00 +0000</pubDate>
<description><![CDATA[<p>TORONTO &#8211; In a landslide, the dog won. Experts were stunned.</p>]]></description></item>
<item><title>Second story</title><link>https://www.thebeaverton.com/b</link>
<pubDate>Sun, 01 Nov 2026 10:00:00 +0000</pubDate><description>Short.</description></item>
</channel></rss>"""


def test_satire_with_its_source_is_the_headline_from_the_feed_with_the_site_name_in_front():
    koppen = uk.koppen_uit_feed(FEED, "The Beaverton")
    assert [k["id"] for k in koppen] == ["S-bron:https://www.thebeaverton.com/a", "S-bron:https://www.thebeaverton.com/b"]
    assert koppen[0]["tekst"] == "The Beaverton\nLocal man & his dog elected mayor\nTORONTO – In a landslide, the dog won."
    assert koppen[0]["datum"] == "2026-11-02" and koppen[0]["set"] == "S-bron"


def test_cut_out_satire_takes_claims_rated_satire_without_descriptions_of_a_post():
    rijen = [(f"gfc-{i}", f"Senator {i} wants to ban the NBA.", "2022-10-29") for i in range(10)] + [
        ("gfc-p", "post on Facebook claiming to show a plane", "2025-01-27"),
        ("gfc-t", "TikTok post claiming to reveal the change", "2025-05-28"),
        ("gfc-v", "Video shows the queen dancing", "2022-01-01")]
    s = uk.kies_s_los(rijen, n=8, zaad=1)
    assert len(s) == 8 and not {"S:gfc-p", "S:gfc-t", "S:gfc-v"} & {x["id"] for x in s}
    assert {x["set"] for x in s} == {"S-los"} and s[0]["claim"] == s[0]["id"][2:]


def test_cut_out_satire_like_unknown_fake_news_skips_the_first_ring_and_hides_its_own_check():
    gevraagd, checks = [], []
    uk.voorbereiden({"id": "S:gfc-1", "set": "S-los", "tekst": "x", "datum": None, "verborgen": ["gfc-1"]}, _config(),
                    lambda q: _brave("https://www.factcheck.org/x"), lambda t: gevraagd.append(t), SITES,
                    lambda tekst, verborgen: checks.append(verborgen) or [])
    assert gevraagd == [] and checks == [frozenset({"gfc-1"})]


def _toets7(rood_g=0, geen_g=80, vals_w=2, over_w=20, geen_w=10, maar_w=1, groen_o=1, alarm_o=33, groen_d=0,
            groen_s=0, satire_s=15):
    rijen, labels = [], {}
    for i in range(100):
        rijen.append(_r(f"G2:{i}", "G2", "rood" if i < rood_g else None, "geen bewering" if i < geen_g else "onzeker",
                        "geen bewering"))
        labels.update({f"G2:{i}": "terecht"} if i < rood_g else {})
    uitkomsten = ["oranje"] * vals_w + ["over een bewering"] * over_w + ["geen bewering"] * geen_w + [
        "klopt grotendeels"] * maar_w
    for i in range(200):
        u = uitkomsten[i] if i < len(uitkomsten) else "klopt"
        rijen.append(_r(f"W2:{i}", "W2", "oranje" if u == "oranje" else ("groen" if u == "klopt" else None),
                        "misleidend" if u == "oranje" else u))
        if u in ("oranje", "klopt grotendeels"):
            labels[f"W2:{i}"] = "vals"
    for i in range(100):
        rijen.append(_r(f"O:{i}", "O'", "groen" if i < groen_o else ("rood" if i < groen_o + alarm_o else None)))
        labels.update({f"O:{i}": "vals"} if i < groen_o else {})
    for i in range(40):
        rijen.append(_r(f"D:{i}", "D", "groen" if i < groen_d else None))
        labels.update({f"D:{i}": "vals"} if i < groen_d else {})
    for i in range(20):
        rijen.append(_r(f"SB:{i}", "S-bron", "groen" if i < groen_s else None, "satire" if i < satire_s else "onzeker"))
        labels.update({f"SB:{i}": "vals"} if i < groen_s else {})
    for i in range(25):
        rijen.append(_r(f"SL:{i}", "S-los", None, "klopt niet"))
    return rijen, labels


def test_the_requirements_of_the_second_round_are_those_set_in_advance():
    eisen = uk.telling(*_toets7(), ronde="lezer-v7")["eisen"]
    assert len(eisen) == 11 and all(eisen.values())
    for te_veel in ({"rood_g": 1}, {"geen_g": 79}, {"vals_w": 3}, {"over_w": 21}, {"geen_w": 11}, {"maar_w": 2},
                    {"groen_o": 2}, {"alarm_o": 32}, {"groen_d": 1}, {"satire_s": 14}):
        eisen = uk.telling(*_toets7(**te_veel), ronde="lezer-v7")["eisen"]
        assert list(eisen.values()).count(False) == 1, te_veel
    eisen = uk.telling(*_toets7(groen_s=1, satire_s=14), ronde="lezer-v7")["eisen"]
    assert not eisen["S: nooit groen"]


def test_each_round_has_its_own_files_and_labels():
    v6, v7 = uk.RONDES["lezer-v6"], uk.RONDES["lezer-v7"]
    assert v6["map"] == uk.UIT and v7["map"] != v6["map"] and v7["labels"] != v6["labels"]
    assert v7["sets"] == ("W2", "O'", "G2", "D", "S-los", "S-bron")


# --- de grens per batch (PO 2026-11-03: één vraag hield een batch van 30 1 uur 40 minuten open) --------------------

class _Klok:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t

    def slaap(self, s):
        self.t += s


def _bericht(i=1000, u=200):
    from types import SimpleNamespace as NS
    return NS(usage=NS(input_tokens=i, output_tokens=u, cache_read_input_tokens=0, cache_creation_input_tokens=0,
                       server_tool_use=None))


class _Batches:
    """Een nep-Batch API: een vraag uit `hangt` (per batch, op volgorde) komt nooit terug; annuleren sluit de batch
    en geeft de klare antwoorden, zoals Anthropic op 2026-11-03 deed."""

    def __init__(self, hangt: list[set[str]]):
        self.hangt, self.ingediend, self.geannuleerd, self.batches = list(hangt), [], [], {}

    def create(self, requests):
        from types import SimpleNamespace as NS
        bid = f"b{len(self.ingediend)}"
        ids = [r["custom_id"] for r in requests]
        self.ingediend.append(ids)
        self.batches[bid] = {"ids": ids, "hangt": self.hangt.pop(0) if self.hangt else set(), "weg": False}
        return NS(id=bid)

    def retrieve(self, bid):
        from types import SimpleNamespace as NS
        b = self.batches[bid]
        return NS(id=bid, processing_status="ended" if b["weg"] or not (b["hangt"] & set(b["ids"])) else "in_progress")

    def cancel(self, bid):
        self.geannuleerd.append(bid)
        self.batches[bid]["weg"] = True

    def results(self, bid):
        from types import SimpleNamespace as NS
        b = self.batches[bid]
        for cid in b["ids"]:
            klaar = cid not in b["hangt"]
            yield NS(custom_id=cid, result=NS(type="succeeded" if klaar else "canceled",
                                               message=_bericht() if klaar else None))


def _client(hangt):
    from types import SimpleNamespace as NS
    return NS(messages=NS(batches=_Batches(hangt)))


def _met_grens(client, verzoeken, **kw):
    klok, log = _Klok(), []
    gemist = uk.batch_met_grens(client, verzoeken, verwerk=lambda m: log.append(("verwerk", sorted(m))),
                                aangemeld=lambda b, ids: log.append(("aan", b, sorted(ids))),
                                afgemeld=lambda b: log.append(("af", b)), slaap=klok.slaap, klok=klok,
                                melding=lambda *_: None, **kw)
    return gemist, log, klok


def test_a_hanging_request_is_cancelled_after_the_limit_and_only_it_is_sent_again():
    client = _client([{"a"}])
    gemist, log, klok = _met_grens(client, {"a": {}, "b": {}, "c": {}}, grens=1200, poll=30)
    batches = client.messages.batches
    assert gemist == [] and batches.ingediend == [["a", "b", "c"], ["a"]] and batches.geannuleerd == ["b0"]
    assert 1200 <= klok.t < 1300
    assert log == [("aan", "b0", ["a", "b", "c"]), ("verwerk", ["b", "c"]), ("af", "b0"),
                   ("aan", "b1", ["a"]), ("verwerk", ["a"]), ("af", "b1")]


def test_a_batch_that_finishes_in_time_is_never_cancelled():
    client = _client([set()])
    gemist, log, klok = _met_grens(client, {"a": {}, "b": {}})
    assert gemist == [] and client.messages.batches.geannuleerd == [] and klok.t < 60
    assert log == [("aan", "b0", ["a", "b"]), ("verwerk", ["a", "b"]), ("af", "b0")]


def test_a_request_that_keeps_hanging_is_given_up_after_the_retries():
    client = _client([{"a"}, {"a"}, {"a"}, {"a"}])
    gemist, log, _ = _met_grens(client, {"a": {}, "b": {}}, herkansingen=2)
    assert gemist == ["a"] and client.messages.batches.ingediend == [["a", "b"], ["a"], ["a"]]
    assert ("verwerk", ["a"]) not in log and log.count(("verwerk", [])) == 0


def test_a_lost_batch_costs_its_answered_tokens_and_its_searches_and_is_closed_first():
    from doublecheck.betatoets import kosten_batch

    client = _client([{"c"}])
    client.messages.batches.create([{"custom_id": x, "params": {}} for x in ("a", "b", "c")])
    kosten = uk.kosten_van_batch(client, "b0", zoekkosten=0.015, slaap=lambda s: None)
    assert client.messages.batches.geannuleerd == ["b0"]
    assert kosten == pytest.approx(2 * kosten_batch({"in": 1000, "uit": 200}) + 0.015)


def test_what_was_lost_counts_towards_the_budget(tmp_path):
    ronde = {"map": tmp_path, "labels": tmp_path / "labels.json"}
    (tmp_path / "ontwikkel.jsonl").write_text('{"kosten": 0.2}\n')
    (tmp_path / "antwoorden.jsonl").write_text('{"kosten": 1.0}\n{"kosten": 0.5}\n')
    assert uk._uitgegeven(ronde) == pytest.approx(1.7)
    uk._voeg_toe(tmp_path / "verloren.jsonl", [{"kosten": 0.32, "reden": "proef onderbroken"}])
    assert uk._uitgegeven(ronde) == pytest.approx(2.02)


def test_an_open_batch_from_a_stopped_process_is_settled_into_the_lost_costs(tmp_path):
    ronde = {"map": tmp_path, "labels": tmp_path / "labels.json"}
    client = _client([{"c"}])
    client.messages.batches.create([{"custom_id": x, "params": {}} for x in ("a", "b", "c")])
    uk._meld_aan(ronde, "b0", 0.015)
    assert json.loads((tmp_path / "lopend.json").read_text()) == {"b0": {"zoekkosten": 0.015}}
    uk._vereffen(ronde, client, slaap=lambda s: None)
    assert json.loads((tmp_path / "lopend.json").read_text()) == {}
    verloren = [json.loads(r) for r in (tmp_path / "verloren.jsonl").read_text().splitlines()]
    assert [r["batch"] for r in verloren] == ["b0"] and uk._uitgegeven(ronde) == pytest.approx(verloren[0]["kosten"])
    assert verloren[0]["kosten"] > 0.015
