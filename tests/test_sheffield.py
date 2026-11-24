"""De rest van de Sheffield-set: lesstof voor een volgende artikellezer
(PLAN #30.11b, PO 2026-10-21: "haal de rest van de Sheffield-set op, beleefd
per host en alleen de tekst")."""

from doublecheck import sheffield


def _rij(article_id, klasse, debunk="d1", domein="rt.com", url=None, datum="05-03-2022"):
    return {"debunk_id": debunk, "article_id": article_id, "article_domain": domein,
            "article_url": url or f"https://{domein}/{article_id}", "article_language": "Russian",
            "debunk_date": datum, "class": klasse}


def test_a_debunk_gets_our_claim_only_when_date_and_domain_point_to_one_report():
    rijen = [_rij("a1", "disinformation", "d1", "rt.com"), _rij("a2", "disinformation", "d2", "tass.ru"),
             _rij("a3", "disinformation", "d3", "ria.ru")]
    eigen = {"2022-03-05": [("/report/een", {"rt.com"}), ("/report/twee", {"tass.ru"}), ("/report/drie", {"tass.ru"})]}
    claims = sheffield.zaakclaims(rijen, eigen, {"/report/een": "gfc-1", "/report/twee": "gfc-2"})
    assert claims == {"d1": "gfc-1"}


def test_each_article_is_fetched_once_and_a_trustworthy_one_gets_the_claim_of_its_debunk():
    rijen = [_rij("a1", "disinformation", "d1"), _rij("a1", "disinformation", "d2"),
             _rij("b1", "trustworthy", "d1", "theguardian.com")]
    taken = sheffield.taken(rijen, {"d1": "gfc-1"}, klaar=set())
    assert [t["article_id"] for t in taken] == ["a1", "b1"]
    assert taken[0]["debunks"] == ["d1", "d2"] and taken[0]["claim_id"] == "gfc-1"
    assert taken[1]["klasse"] == "trustworthy" and taken[1]["claim_id"] == "gfc-1"


def test_articles_that_are_already_there_are_skipped_and_those_with_a_claim_go_first():
    rijen = [_rij("a1", "disinformation", "d9"), _rij("a2", "disinformation", "d1"), _rij("a3", "trustworthy", "d1")]
    taken = sheffield.taken(rijen, {"d1": "gfc-1"}, klaar={"a3"})
    assert [t["article_id"] for t in taken] == ["a2", "a1"]


def test_a_translate_proxy_link_points_back_to_the_site_itself():
    assert sheffield.ontproxy("https://rt-com.translate.goog/news/1?_x_tr_sl=ru") == "https://rt.com/news/1"
    assert sheffield.dom("www.ria-ru.translate.goog") == "ria.ru"


def test_only_text_is_kept_never_html():
    pagina = ("<html><head><meta property='og:title' content='Кремль &amp; НАТО'>"
              "<meta name='description' content='Короткое описание статьи'></head><body>"
              "<script>var x = 1;</script><p>Это первый абзац статьи, достаточно длинный, чтобы его сохранить.</p>"
              "<p>коротко</p></body></html>")
    titel, beschrijving, tekst = sheffield.lees(pagina)
    assert titel == "Кремль & НАТО"
    assert beschrijving == "Короткое описание статьи"
    assert tekst == "Это первый абзац статьи, достаточно длинный, чтобы его сохранить."
    assert "<" not in titel + beschrijving + tekst


def test_a_line_separator_inside_an_article_does_not_split_its_record(tmp_path):
    import json

    pad = tmp_path / "lesstof-artikelen.jsonl"
    regels = [{"article_id": "a1", "tekst": "eerste alinea tweede derde\x85vierde"}, {"article_id": "a2", "tekst": ""}]
    pad.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in regels), encoding="utf-8")
    assert sheffield.regels(pad) == regels
    assert sheffield.regels(tmp_path / "ontbreekt.jsonl") == []
