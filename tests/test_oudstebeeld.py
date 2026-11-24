"""De voormeting voor het beeld (PLAN #32.40): zoals een factchecker de oudste plek zoeken waar hetzelfde beeld stond,
met de datum uit de pagina zelf."""

from doublecheck import oudstebeeld as ob


def test_the_date_of_a_page_comes_from_its_own_publication_date_first():
    html = ('<html><head><meta property="article:published_time" content="2019-05-12T08:00:00Z">'
            '<script type="application/ld+json">{"datePublished": "2021-01-01"}</script></head>'
            '<body><time datetime="2023-03-03">x</time></body></html>')
    assert ob.paginadatum(html, "https://a.org/2024/02/02/x") == "2019-05-12"


def test_without_a_meta_tag_the_structured_data_then_a_time_tag_then_the_address():
    assert ob.paginadatum('<script>{"datePublished":"2020-07-04T10:00"}</script>', "https://a.org/x") == "2020-07-04"
    assert ob.paginadatum('<time datetime="2018-11-30">30 Nov</time>', "https://a.org/x") == "2018-11-30"
    assert ob.paginadatum("<p>niets</p>", "https://news.org/2017/06/21/flood") == "2017-06-21"
    assert ob.paginadatum("<p>niets</p>", "https://news.org/story") is None


def test_an_impossible_date_never_counts():
    assert ob.paginadatum('<meta name="date" content="1888-01-01">', "https://a.org/x") is None
    assert ob.paginadatum('<meta name="date" content="2099-01-01">', "https://a.org/x") is None


def test_the_oldest_page_is_the_one_with_the_earliest_date_and_a_page_without_a_date_never_wins():
    paginas = [{"url": "a", "datum": "2022-01-01"}, {"url": "b", "datum": None}, {"url": "c", "datum": "2015-03-01"}]
    assert ob.oudste(paginas)["url"] == "c"
    assert ob.oudste([{"url": "b", "datum": None}]) is None


def test_earlier_means_at_least_a_week_before_the_fact_check():
    assert ob.eerder("2019-01-01", "2021-05-05 10:00:00")
    assert not ob.eerder("2021-05-01", "2021-05-05 10:00:00")
    assert not ob.eerder(None, "2021-05-05")


def test_the_set_takes_only_images_found_by_reverse_search_that_are_on_disk():
    rijen = [{"verification_strategy": "reverse image search"}, {"verification_strategy": "keyword search"},
             {"verification_strategy": "reverse image search; keyword search"}, {"verification_strategy": "other"}]
    uit = ob.kies(rijen, op_schijf={0, 1, 2}, n=10)
    assert [r["index"] for r in uit] == [0, 2]


def test_a_long_video_page_still_gives_its_upload_date():
    html = "<html>" + "x" * 900_000 + '<meta itemprop="uploadDate" content="2021-11-30T09:00:20-08:00"></html>'
    assert ob.paginadatum(html, "https://www.youtube.com/watch?v=abc") == "2021-11-30"
