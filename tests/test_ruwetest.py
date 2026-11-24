"""Ruwe test met de beelden van factcheckers (PLAN #25.10).

De netwerkkant draait alleen live; hier staan de stukken waar de uitslag op
rust: het beeld uit een artikel halen, herkennen of een beeld nog een stempel
draagt, en een antwoord van de resolver eerlijk indelen.
"""

import pytest

from doublecheck import ruwetest as rt

HTML = """<html><head>
<meta property="og:title" content="Fact Check: Viral photo of flooded airport is from 2019">
<meta content="https://cdn.example.org/beeld.jpg" property="og:image" />
<meta name="twitter:image" content="https://cdn.example.org/twitter.jpg">
</head><body></body></html>"""


def test_the_shared_image_and_title_are_read_from_the_page():
    meta = rt.lees_meta(HTML)
    assert meta["beeld"] == "https://cdn.example.org/beeld.jpg"
    assert meta["titel"].startswith("Fact Check: Viral photo")


def test_twitter_image_is_the_fallback():
    meta = rt.lees_meta('<meta name="twitter:image" content="https://x.org/t.png">')
    assert meta["beeld"] == "https://x.org/t.png"


def test_a_verdict_stamp_or_publisher_name_counts_as_a_leak():
    assert rt.lekt("FALSE  This photo is old", "FACTLY")
    assert rt.lekt("Misleading claim", "VERA Files")
    assert rt.lekt("factly.in", "FACTLY")
    assert rt.lekt("Cr, ANG TOTOO RAñed", "VERA Files")  # Tagalog-stempel
    assert rt.lekt("ಸುಳ್ಳು ... Fact Crescendo", "Fact Crescendo Sri Lanka")
    assert not rt.lekt("Airport flooded after heavy rains in Dubai today", "FACTLY")


def _antwoord(categorie, claim_id=None, urls=()):
    a = {"category": categorie}
    if claim_id:
        a["claim"] = {"id": claim_id}
        a["evidence"] = {"checks": [{"url": u} for u in urls]}
    return a


def test_outcomes_are_classified_honestly():
    verwacht = {"gfc-a", "gfc-b"}  # de claim en zijn clustergenoten
    assert rt.beoordeel(_antwoord("matched", "gfc-a", ["https://x/1"]), "https://x/1", verwacht) == "gevonden"
    assert rt.beoordeel(_antwoord("matched", "gfc-b", ["https://y/2"]), "https://x/1", verwacht) == "gevonden"
    assert rt.beoordeel(_antwoord("matched", "gfc-z", ["https://x/1"]), "https://x/1", verwacht) == "gevonden"
    assert rt.beoordeel(_antwoord("matched", "gfc-z", ["https://z/9"]), "https://x/1", verwacht) == "fout"
    assert rt.beoordeel(_antwoord("related"), "https://x/1", verwacht) == "verwant"
    assert rt.beoordeel(_antwoord("none"), "https://x/1", verwacht) == "niets"


def test_the_report_splits_stamped_and_clean_images():
    uitkomsten = [
        rt.Uitkomst("FACTLY", "en", "https://x/1", "gevonden", lekt=False),
        rt.Uitkomst("FACTLY", "en", "https://x/2", "niets", lekt=True),
        rt.Uitkomst("VERA Files", "en", "https://x/3", "verwant", lekt=False),
    ]
    r = rt.rapport(uitkomsten)
    assert r["totaal"]["gevonden"] == 1 and r["totaal"]["n"] == 3
    assert r["zonder_stempel"]["n"] == 2 and r["met_stempel"]["n"] == 1
    assert r["per_uitgever"]["FACTLY"]["n"] == 2


def test_m4fc_items_are_the_linked_images_on_disk_with_their_check(tmp_path):
    """#25.10 opnieuw, op de M4FC-beelden die bij een check in onze index
    horen (#28.5). Een beeld dat niet binnenkwam doet niet mee; de URL van
    het artikel is het bonnetje dat terug moet komen."""
    import json

    from doublecheck.ruwetest import m4fc_items

    (tmp_path / "beelden").mkdir()
    (tmp_path / "beelden" / "00000.jpg").write_bytes(b"\xff\xd8\xff beeld")
    (tmp_path / "M4FC.json").write_text(json.dumps([
        {"article_url": "https://factly.in/a/", "fc_org": "factly.in", "fc_language": "telugu"},
        {"article_url": "https://snopes.com/b/", "fc_org": "snopes.com", "fc_language": "english"},
        {"article_url": "https://correctiv.org/c/", "fc_org": "correctiv.org", "fc_language": "german"},
    ]), encoding="utf-8")
    (tmp_path / "gekoppeld.json").write_text(json.dumps({
        "0": {"claim_id": "gfc-1", "article_url": "https://factly.in/a/"},
        "2": {"claim_id": "gfc-3", "article_url": "https://correctiv.org/c/"},   # beeld ontbreekt
    }), encoding="utf-8")
    items = m4fc_items(tmp_path)
    assert [(i.claim_id, i.url, i.uitgever, i.taal, i.pad.name) for i in items] == [
        ("gfc-1", "https://factly.in/a/", "factly.in", "telugu", "00000.jpg")]


def test_the_report_splits_images_with_and_without_readable_text():
    """Zonder beeldindex (#25.11) kan een beeld zonder tekst alleen `none`
    geven; dat hoort apart in het rapport, anders lijkt het een fout van de
    tekstroute."""
    from doublecheck.ruwetest import Uitkomst, rapport

    rijen = [Uitkomst("u", "en", "a", "gevonden", False, tekst=True),
             Uitkomst("u", "en", "b", "niets", False, tekst=False),
             Uitkomst("u", "en", "c", "niets", True, tekst=True)]
    r = rapport(rijen)
    assert r["met_tekst"]["n"] == 2 and r["met_tekst"]["gevonden"] == 1
    assert r["zonder_tekst"] == {"n": 1, "gevonden": 0, "verwant": 0, "fout": 0, "niets": 1}


def test_only_the_wrong_answers_are_picked_for_review(tmp_path):
    """Een `fout` is een andere claim als `matched`: een echte valse treffer,
    of dezelfde claim bij een andere redactie buiten het cluster. Dat beslist
    een mens; de hulp zet alleen die gevallen klaar."""
    from pathlib import Path

    from doublecheck.ruwetest import M4FCItem, te_herbekijken

    items = [M4FCItem("gfc-1", "https://a/", "x", "en", Path("0.jpg")),
             M4FCItem("gfc-2", "https://b/", "x", "en", Path("1.jpg")),
             M4FCItem("gfc-3", "https://c/", "x", "en", Path("2.jpg"))]
    uitslagen = [{"url": "https://a/", "uitkomst": "niets"}, {"url": "https://b/", "uitkomst": "fout"},
                 {"url": "https://c/", "uitkomst": "gevonden"}]
    assert [i.claim_id for i in te_herbekijken(uitslagen, items)] == ["gfc-2"]


def test_an_error_from_the_resolver_stops_the_run_instead_of_counting_as_none():
    """De netwerktoets telde 1.670 keer "niets": het waren 429's van de
    per-IP-grens. Een toets die een fout als uitkomst telt, meet iets anders
    dan hij zegt."""
    from types import SimpleNamespace

    from doublecheck.ruwetest import antwoord_of_fout

    assert antwoord_of_fout(SimpleNamespace(status_code=200, json=lambda: {"category": "none"})) == {"category": "none"}
    with pytest.raises(RuntimeError, match="429"):
        antwoord_of_fout(SimpleNamespace(status_code=429, json=lambda: {}))
