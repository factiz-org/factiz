"""EUvsDisinfo bijhouden via hun server (PLAN #35.3; PO 2026-11-23: "Qua binnenhalen, doe voor nu alleen 2026, de rest
doen we later"): een geval van de server wordt hetzelfde geval als uit de momentopname, het ophalen stopt bij de eerste dag
die Factiz neemt of bij een bladzijde zonder iets nieuws, en alleen wat het lab nog niet heeft gaat de import in, met een
eigen herkomst."""

import json

import pytest

from doublecheck import euvsdisinfo as eu
from doublecheck.storage import connect, init_schema


def _rij(url="https://euvsdisinfo.eu/report/a/", ts=1794787200, **anders):
    """Een geval zoals de server het geeft."""
    return {"id": "x", "title": "European countries are facing insolvency",
            "claim": "<p>The war is ruining Europe.</p><p>Some countries &amp; banks face insolvency.</p>",
            "fact": "<p>This is a recurring narrative.</p><p>The EU forecast suggests <strong>1.4%</strong> growth.</p>",
            "date": ts, "keywords": [{"_id": "k", "title": "Economic difficulties"}],
            "countries": [{"_id": "c1", "title": "Europe"}, {"_id": "c2", "title": "Ukraine"}],
            "linksToDisinformation": [
                {"headLine": "Kop", "language": {"name": "Russian", "id": "rus"},
                 "url": "https://www.sputnik.by/2026/a.html", "snapShotURL": "https://archive.euvsd.info/snapshots/1"},
                {"headLine": "Post", "language": {"name": "Russian", "id": "rus"}, "url": "https://t.me/kanaal/5"},
                {"headLine": "Nog eens", "language": {"name": "Russian", "id": "rus"}, "url": "https://sputnik.by/b"}],
            "url": url, **anders}


def test_a_case_from_the_server_becomes_the_same_kind_of_case_as_from_the_snapshot():
    g = eu.uit_server(_rij())
    assert g.datum == "2026-11-16"                      # de dag van de tijdstempel, in UTC
    assert g.url == "https://euvsdisinfo.eu/report/a"   # zonder de schuine streep aan het eind, zoals de momentopname
    assert g.titel == "European countries are facing insolvency"
    # platte tekst: de alinea's met een spatie ertussen, de tekens van HTML terug naar wat ze zijn
    assert g.claim == "The war is ruining Europe. Some countries & banks face insolvency."
    assert g.weerlegging == "This is a recurring narrative. The EU forecast suggests 1.4% growth."
    # de outlets zijn de sites waar EUvsDisinfo de bewering zag, elk één keer, zonder www
    assert g.outlets == ("sputnik.by", "t.me") and g.landen == ("Europe", "Ukraine")
    assert eu._soort("t.me") == "platform" and eu._soort("sputnik.by") == "outlet"


def test_a_case_without_a_usable_date_gets_no_date_and_so_never_becomes_a_receipt():
    assert eu.uit_server(_rij(ts=None)).datum == ""
    assert eu.naar_rawclaims([eu.uit_server(_rij(ts=None))]) == []


def _bladzijden(*paginas):
    """Een nep-server: per offset de gevallen van die bladzijde (nieuwste eerst), en welke offsets gevraagd werden."""
    gevraagd = []

    def roep(offset, limit):
        gevraagd.append(offset)
        return paginas[offset // limit] if offset // limit < len(paginas) else []
    return roep, gevraagd


def _dag(d):
    import datetime
    return int(datetime.datetime.fromisoformat(d).replace(tzinfo=datetime.UTC).timestamp())


def test_fetching_goes_back_to_the_first_day_factiz_takes_and_no_further():
    roep, gevraagd = _bladzijden(
        [_rij(f"https://euvsdisinfo.eu/report/n{i}", _dag("2026-03-01")) for i in range(2)],
        [_rij("https://euvsdisinfo.eu/report/j", _dag("2026-01-02")),
         _rij("https://euvsdisinfo.eu/report/d", _dag("2025-12-30"))],
        [_rij("https://euvsdisinfo.eu/report/oud", _dag("2025-06-01"))])
    gevallen = eu.ophalen(roep, sinds="2026-01-01", bekend=set(), limit=2, pauze=0)
    assert [g.url.rsplit("/", 1)[1] for g in gevallen] == ["n0", "n1", "j"]
    assert gevraagd == [0, 2]                           # de bladzijde met 2025 is de laatste die gevraagd wordt


def test_fetching_stops_at_a_page_with_nothing_new_so_a_week_asks_little():
    roep, gevraagd = _bladzijden(
        [_rij("https://euvsdisinfo.eu/report/nieuw", _dag("2026-11-20")),
         _rij("https://euvsdisinfo.eu/report/oud1", _dag("2026-11-10"))],
        [_rij("https://euvsdisinfo.eu/report/oud2", _dag("2026-11-01")),
         _rij("https://euvsdisinfo.eu/report/oud3", _dag("2026-10-20"))],
        [_rij("https://euvsdisinfo.eu/report/oud4", _dag("2026-10-01"))])
    bekend = {f"https://euvsdisinfo.eu/report/oud{i}" for i in range(1, 5)}
    gevallen = eu.ophalen(roep, sinds="2026-01-01", bekend=bekend, limit=2, pauze=0)
    assert [g.url for g in gevallen] == ["https://euvsdisinfo.eu/report/nieuw"]
    assert gevraagd == [0, 2]


def test_the_store_keeps_each_case_once_with_everything_the_reasons_need(tmp_path):
    pad = tmp_path / "server.jsonl"
    a, b = eu.uit_server(_rij()), eu.uit_server(_rij("https://euvsdisinfo.eu/report/b"))
    eu.bewaar([a], pad)
    eu.bewaar([a, b], pad)
    terug = eu.bewaarde(pad)
    assert [g.url for g in terug] == ["https://euvsdisinfo.eu/report/a", "https://euvsdisinfo.eu/report/b"]
    assert terug[0] == a and json.loads(pad.read_text(encoding="utf-8").splitlines()[0])["weerlegging"]
    assert eu.bewaarde(tmp_path / "er-niet.jsonl") == []


@pytest.fixture
def conn():
    c = connect(":memory:")
    init_schema(c)
    yield c
    c.close()


def test_only_cases_the_lab_does_not_have_go_in_and_they_carry_the_server_as_their_origin(conn):
    oud = eu.Geval(datum="2022-11-01", url="https://euvsdisinfo.eu/report/oud", titel="Oud",
                   claim="An old claim that the snapshot already brought in.", weerlegging="Old disproof.",
                   outlets=("rt.com",), landen=("Russia",))
    eu.importeer(conn, [oud], uitgesteld=True)
    nieuw = eu.uit_server(_rij())
    zelfde = eu.uit_server(_rij("https://euvsdisinfo.eu/report/oud/"))
    assert eu.nieuw_voor_lab(conn, [nieuw, zelfde]) == [nieuw]
    eu.importeer(conn, [nieuw], uitgesteld=True, herkomst=eu.HERKOMST_SERVER)
    bronnen = dict(conn.execute("SELECT url, source FROM factcheck"))
    assert bronnen == {"https://euvsdisinfo.eu/report/oud": eu.HERKOMST,
                       "https://euvsdisinfo.eu/report/a": "euvsdisinfo:mcp"}
    # dezelfde bron in het register, dus de uitgave neemt hem mee zoals de gevallen uit de momentopname
    from doublecheck.publiceren import _prefix
    assert _prefix(eu.HERKOMST_SERVER) == _prefix(eu.HERKOMST) == eu.BRON_ID
