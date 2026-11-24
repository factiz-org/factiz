"""De eigen factcheck op het platform (PLAN #37.4, B82, DESIGN §4x): een gepubliceerde check gaat mee in elke uitgave,
een concept alleen in een voorbeeld voor de eigen computer, en de site toont een check alleen in haar eigen taal."""

import json
import sqlite3

import pytest
from starlette.testclient import TestClient

from doublecheck import publiceren as pb
from factiz_site import app as fa
from tests import test_redactie as tr
from tests.test_publiceren import REGISTER, _check, _claim, _lab

KLAAR = dict(status="gepubliceerd", auteur="A. de Vries", nalezer="B. Jansen", gepubliceerd="2026-12-01")


def _gepubliceerd(sleutel="gepubliceerd", **anders):
    """Een gepubliceerde check met een gemaakt beeld (`redactiebeeld.erbij` zette pad en maat erbij, #37.5)."""
    beeld = [{**tr._check()["beeld"][0], "bestand": "beeld-1.jpg", "pad": f"/static/redactie/{sleutel}/beeld-1.jpg",
              "breedte": 640, "hoogte": 818}]
    return tr._check(sleutel=sleutel, **{**KLAAR, "beeld": beeld, "adres": f"{sleutel}-check-nl",
                                         "adres_en": f"{sleutel}-check-en", **anders})


def _engels():
    """Een geldige machinevertaling in het Engels van `_gepubliceerd` (#37.8), zoals `eigenvertaling.geldige` haar geeft."""
    from doublecheck import eigenvertaling as ev

    velden = {k: f"EN {v}" if isinstance(v, str) else v for k, v in ev.bron(_gepubliceerd()).items()}
    return {"velden": velden, "maker": "claude-sonnet-5-5, eigenvertaling-v1"}


def _bouw(map_, eigen, concepten=False):
    map_.mkdir(parents=True, exist_ok=True)
    lab = _lab(map_)
    n = _claim(lab, 1, "Garlic water cures covid")
    _check(lab, n, "https://snopes.com/garlic", datum="2021-01-01")
    lab.commit()
    return pb.bouw(lab, map_ / "uit", register=REGISTER, vaag=frozenset(), datum="2026-12-02", eigen=eigen,
                   concepten=concepten)


def _site(tmp_path_factory, concepten=True):
    """Een uitgave met een gepubliceerde eigen check en een concept met een post van een privépersoon erin."""
    map_ = tmp_path_factory.mktemp("eigen")
    post = {"nr": 3, "soort": "bron", "uitgever": "X", "titel": "De post", "datum": "2026-11-08", "prive": True}
    concept = tr._check(sleutel="proef", bron=tr._check()["bron"] + [post],
                        tekst=tr._check()["tekst"] + " De post stond er om 12:23 [3]. [FEIT NODIG: de tijd nakijken.]",
                        nog_doen=["De screenshot vervangen."],
                        tijdlijn=[{"datum": "2026-11-08", "tijd": "12:23", "wat": "De post [3]."}],
                        rekensom=[{"geval": "Nu", "som": "768 x 36%", "uitkomst": "3 euro"}])
    manifest = _bouw(map_, [_gepubliceerd(vertalingen={"en": _engels()}), concept], concepten=concepten)
    client = TestClient(fa.maak_app(manifest["bestand"]), follow_redirects=False)
    client.bestand = manifest["bestand"]        # voor de vergelijking met de TypeScript-kant (#34.2bo)
    return client, manifest


@pytest.fixture(scope="module")
def voorbeeld(tmp_path_factory):
    return _site(tmp_path_factory)


def test_a_published_own_check_goes_into_every_edition_and_a_draft_only_into_a_preview(tmp_path):
    uitgave = _bouw(tmp_path / "a", [_gepubliceerd(), tr._check()])
    conn = sqlite3.connect(uitgave["bestand"])
    assert conn.execute("SELECT sleutel, concept, taal, datum, oordeel FROM eigen_check").fetchall() == [
        ("gepubliceerd", 0, "nl", "2026-12-01", "onwaar")]
    assert uitgave["eigen"] == {"gepubliceerd": 1, "concept": 0, "vindbaar": 1}
    assert pb.controleer(uitgave["bestand"])["eigen"] == 1

    voorbeeld = _bouw(tmp_path / "b", [_gepubliceerd(), tr._check()], concepten=True)
    conn = sqlite3.connect(voorbeeld["bestand"])
    assert conn.execute("SELECT sleutel, concept FROM eigen_check ORDER BY sleutel").fetchall() == [
        ("gepubliceerd", 0), ("proef", 1)]
    with pytest.raises(pb.Weigering, match="eigen factcheck"):
        pb.controleer(voorbeeld["bestand"])
    assert pb.controleer(voorbeeld["bestand"], concepten=True)["eigen"] == 2


def test_an_own_check_that_breaks_the_rules_of_the_desk_stops_the_build(tmp_path):
    with pytest.raises(pb.Weigering, match="nalezer"):
        _bouw(tmp_path, [_gepubliceerd(nalezer="Claude")])


def test_checking_refuses_an_own_check_that_was_changed_afterwards_even_with_a_new_checksum(tmp_path):
    uitgave = _bouw(tmp_path, [_gepubliceerd()])
    conn = sqlite3.connect(uitgave["bestand"])
    gegevens = json.loads(conn.execute("SELECT gegevens FROM eigen_check").fetchone()[0])
    gegevens["bron"][1]["soort"] = "factcheck"      # dan rust de kern nog op één bron
    conn.execute("UPDATE eigen_check SET gegevens = ?", (json.dumps(gegevens),))
    conn.execute("UPDATE meta SET waarde = ? WHERE sleutel = 'controlegetal'", (pb.controlegetal(conn),))
    conn.commit()
    with pytest.raises(pb.Weigering, match="twee bronnen"):
        pb.controleer(uitgave["bestand"])


def test_the_own_check_page_gives_the_verdict_and_the_text_with_numbered_sources_only_in_its_own_language(voorbeeld):
    client, _ = voorbeeld
    d = client.get("/api/nl/eigen/proef").json()
    assert d["kop"] == tr._check()["kop"] and d["oordeel"] == "onwaar" and d["oordeel_tekst"] == "Onwaar"
    assert d["concept"] is True and d["href"] == "/nl/radar/2026/12/standbeeld-anne-frank-ai/"
    # het nummer van een bron staat tegen het woord ervoor, twee nummers naast elkaar zonder tekst ertussen
    assert d["kort"][:2] == [{"t": "Er gaat een beeld rond. Het is gemaakt met AI"}, {"n": 1}]
    assert any({"nodig": "de tijd nakijken."} in alinea for alinea in d["tekst"])
    assert d["kenmerken"] == "Gemaakt met AI · Beeld" and d["posts_tekst"] == "5 posts"
    assert d["eerst_gezien"] == "8 november 2026"
    assert d["tijdlijn"] == [{"datum": "8 november 2026", "tijd": "12:23", "wat": "De post."}]
    assert d["rekensom"] == [{"geval": "Nu", "som": "768 x 36%", "uitkomst": "3 euro"}]
    assert d["nog_doen"] == [[{"t": "De screenshot vervangen."}]]   # in stukken, zodat een [n] naar de bron linkt
    for pad in ("/api/en/eigen/proef", "/api/de/eigen/proef", "/api/nl/eigen/onbekend", "/api/nl/eigen/Proef"):
        assert client.get(pad).status_code == 404, pad


def test_the_own_check_names_its_page_in_the_archive_so_the_site_can_show_the_same_sidebar(voorbeeld):
    """PO 2026-11-19: "Onze eigen factchecks mogen ook de sidebar krijgen"; de kaarten, het thema en de verbanden komen van
    de pagina in het archief, zoals bij elke factcheck."""
    client, _ = voorbeeld
    d = client.get("/api/nl/eigen/proef").json()
    assert d["nummer"] == pb.nummer("factiz-proef")
    assert client.get(f"/api/nl/factcheck/{d['nummer']}").status_code == 200


def test_a_published_check_shows_what_is_still_to_find_out_with_a_call_to_contribute(tmp_path):
    """B84 (PO 2026-11-19): wat nog openstaat, staat op de pagina als nog uit te zoeken, met een mail naar de redactie; een
    post die weg is, staat er met die vermelding."""
    post = {"nr": 3, "soort": "bron", "uitgever": "X", "titel": "De post", "datum": "2026-11-08", "prive": True, "weg": True}
    check = _gepubliceerd(nog_uitzoeken=["Wie maakte het beeld?"], bron=tr._check()["bron"] + [post],
                          tekst=tr._check()["tekst"] + " De post stond er om 12:23 [3].", auteur="Claude (AI)",
                          nalezer="De redactie van Factiz")
    manifest = _bouw(tmp_path, [check])
    client = TestClient(fa.maak_app(manifest["bestand"]))
    d = client.get("/api/nl/eigen/gepubliceerd").json()
    assert d["nog_uitzoeken"] == ["Wie maakte het beeld?"] and d["nog_doen"] == []
    assert d["bijdragen"]["adres"] == fa.CONTACT and d["bijdragen"]["href"].startswith(f"mailto:{fa.CONTACT}?subject=")
    assert next(b for b in d["bronnen"] if b["nr"] == 3)["weg"] is True
    assert next(b for b in d["bronnen"] if b["nr"] == 3)["geen_kopie"] == ""
    assert d["auteur"] == "Claude (AI)" and d["nalezer"] == "De redactie van Factiz"


def test_a_post_by_a_private_person_is_listed_without_a_link_and_a_circulating_image_carries_its_stamp(voorbeeld):
    client, _ = voorbeeld
    d = client.get("/api/nl/eigen/proef").json()
    post = next(b for b in d["bronnen"] if b["nr"] == 3)
    assert post["prive"] is True and post["url"] == "" and post["host"] == ""
    nos = next(b for b in d["bronnen"] if b["nr"] == 2)
    assert nos["url"] == "https://www.parool.nl/" and nos["host"] == "parool.nl" and nos["soort_tekst"] == "nieuws"
    rondgaat = next(b for b in d["beelden"] if b["rol"] == "rondgaat")
    assert rondgaat["stempel"] == "Onwaar" and rondgaat["alt"]
    assert rondgaat["pad"] == "" and rondgaat["breedte"] == 0        # nog niet gemaakt: de site toont de plek


def test_a_made_image_reaches_the_api_with_its_path_and_size(voorbeeld):
    client, _ = voorbeeld
    d = client.get("/api/nl/eigen/gepubliceerd").json()
    rondgaat = next(b for b in d["beelden"] if b["rol"] == "rondgaat")
    assert rondgaat["pad"] == "/static/redactie/gepubliceerd/beeld-1.jpg"
    assert (rondgaat["breedte"], rondgaat["hoogte"]) == (640, 818)


def test_the_list_of_own_checks_puts_the_latest_first_marks_a_draft_and_exists_only_where_it_can_be_read(voorbeeld):
    client, _ = voorbeeld
    lijst = client.get("/api/nl/eigen").json()
    assert [c["sleutel"] for c in lijst["checks"]] == ["gepubliceerd", "proef"]
    assert [c["concept"] for c in lijst["checks"]] == [False, True]
    assert lijst["checks"][0]["datum"] == "1 december 2026" and lijst["checks"][0]["href"] == "/nl/radar/2026/12/gepubliceerd-check-nl/"
    # in een taal zonder eigen check en zonder vertaling is er geen lijst (#37.8: de Engelse heeft een vertaling)
    assert client.get("/api/de/eigen").status_code == 404


def test_a_text_becomes_pieces_with_the_source_numbers_against_the_word_before_them():
    assert fa.stukken("Het Huis  meldde het [1] [2]. Ook\nhet Parool [3].") == [
        {"t": "Het Huis meldde het"}, {"n": 1}, {"n": 2}, {"t": ". Ook het Parool"}, {"n": 3}, {"t": "."}]
    assert fa.stukken("Klopt. [FEIT NODIG: de datum.] Verder.") == [{"t": "Klopt. "}, {"nodig": "de datum."}, {"t": " Verder."}]
    assert fa.alineas("Een [1].\n\nTwee.") == [[{"t": "Een"}, {"n": 1}, {"t": "."}], [{"t": "Twee."}]]


def test_the_site_shows_an_own_check_in_the_stamp_style_without_raw_html_and_a_draft_is_never_findable():
    from pathlib import Path

    src = Path(__file__).resolve().parent.parent / "site" / "src"
    router = (src / "pages" / "[...pad].astro").read_text(encoding="utf-8")
    assert "soort === 'radar'" in router and "/api/${taal}/eigen/${sleutel}/${maand}/${naam}`" in router
    # het oude adres stuurt voorgoed door naar Factiz Radar (PO 2026-11-19), en een werknaam naar het adres met jaar en
    # maand (PLAN #37.11), net als de naam van een andere taal
    assert "soort === 'factiz-checks'" in router and "pad(taal, 'radar'" in router and ", 301)" in router
    assert "Astro.redirect(oud.href + Astro.url.search, 301)" in router and "Astro.redirect(e.doorsturen + Astro.url.search, 301)" in router
    pagina = (src / "components" / "site" / "paginas" / "EigenCheck.astro").read_text(encoding="utf-8")
    lijst = (src / "components" / "site" / "paginas" / "EigenChecks.astro").read_text(encoding="utf-8")
    eigen = [pagina, lijst, *(p.read_text(encoding="utf-8") for p in (src / "components" / "site" / "eigen").glob("*.astro"))]
    assert not any("set:html" in t for t in eigen)                     # de tekst komt in stukken, nooit als HTML
    assert "<Zegel" in pagina and "fz-stempel fz-stempel-groot" in pagina and "fz-eigen-afdruk" in pagina   # de stijl Stempel (DESIGN §4x)
    # de opbouw van een factcheck (PO 2026-11-19: "meer in lijn komen met het pagina design van de andere checks"): het
    # kruimelpad met terug, twee kolommen met de contextkaarten en de inhoud, de bewering en het antwoord op hun vlak, de
    # koppen van een factcheck; eigen blijven alleen het zegel, de kop en het stempel
    for stuk in ("lg:grid-cols-[minmax(0,1fr)_17rem]", "<ContextKaarten", "t('op_deze_pagina')", 'class="podium',
                 "t('antwoord_kop')", 'class="sectiekop"', "t('terug_resultaten')", "t('verbanden_kop')"):
        assert stuk in pagina, stuk
    assert "fz-eigen-kaart" not in pagina and "fz-eigen-h2" not in pagina
    # wat nog uit te zoeken is, met de oproep om bij te dragen, en een verdwenen post met die vermelding (B84); een
    # gepubliceerde check zonder gemaakt beeld toont geen lege plek
    for stuk in ("t('eigen_nog_uitzoeken')", "t('eigen_bijdragen_kop')", "e.bijdragen.href", "e.bijdragen.adres",
                 "t('eigen_bron_weg')", "b.geen_kopie", "b.pad || (e.concept && b.rol === 'rondgaat')"):
        assert stuk in pagina, stuk
    # het gemaakte beeld met zijn maat (geen verspringende pagina) en alt-tekst; anders de plek met het stempel
    assert 'class="fz-eigen-foto" src={b.pad} width={b.breedte} height={b.hoogte} alt={b.alt}' in pagina
    assert "b.pad ? (" in pagina and "eigen_beeld_volgt" in pagina
    # zoekmachines zien het origineel en een gelezen vertaling, een concept nooit (`vindbaar_in`, PLAN #37.11)
    assert "paden={e.paden} aangeboden={e.vindbaar_in}" in pagina
    assert "e.concept ? ''" in pagina                                    # en krijgt geen ClaimReview
    # in een lijst van het archief het zegel en een stempeltje in plaats van de pil (D12)
    rij = (src / "components" / "site" / "Rij.jsx").read_text(encoding="utf-8")
    assert "r.eigen ?" in rij and "fz-stempel" in rij and "fz-eigen-rijmerk" in rij
    # Radar in het menu en de voet alleen als de taal gepubliceerde eigen checks heeft (`radar` in het archief)
    layout = (src / "layouts" / "Site.astro").read_text(encoding="utf-8")
    assert "...(basis?.radar?.href ? { radar: basis.radar.href } : {})" in layout and "{links.radar && <li>" in layout and "factiz-checks" not in layout
    menu = (src / "components" / "site" / "Menu.jsx").read_text(encoding="utf-8")
    assert menu.count("{links.radar && ") == 2 and menu.count("fz-radar-stip") == 2
    # de ringen op de start: alleen met eigen checks, en ze pulseren alleen als er deze week een nieuwe is
    start = (src / "components" / "site" / "paginas" / "Start.astro").read_text(encoding="utf-8")
    assert "{g.radar && (" in start and "data-nieuw={g.radar.nieuw ? '' : undefined}" in start
    css = (src / "styles" / "site.css").read_text(encoding="utf-8")
    assert ".fz .fz-radar[data-nieuw] .fz-radar-golf { animation:" in css
    assert ".fz .fz-radar[data-nieuw] .fz-radar-midden { animation:" in css
    assert ("@media (prefers-reduced-motion: reduce) { .fz .fz-radar[data-nieuw] .fz-radar-golf, "
            ".fz .fz-radar[data-nieuw] .fz-radar-midden { animation: none; } }") in css


def test_an_own_check_is_a_page_of_the_archive_with_factiz_as_newsroom_and_only_published_in_an_edition(tmp_path):
    proef = pb.nummer("factiz-proef")
    voorbeeld = _bouw(tmp_path / "a", [_gepubliceerd(), tr._check()], concepten=True)
    conn = sqlite3.connect(voorbeeld["bestand"])
    assert conn.execute("SELECT bewering, taal, label, checks, redacties FROM pagina WHERE nummer = ?", (proef,)).fetchone() == (
        tr._check()["bewering"], "nl", "onwaar", 1, 1)
    assert conn.execute("SELECT redactie, oordeel, oordeel_eigen, url, bron FROM check_ WHERE pagina = ?", (proef,)).fetchone() == (
        "Factiz", "onwaar", "Onwaar", "https://factiz.org/nl/radar/2026/12/standbeeld-anne-frank-ai/", "factiz-redactie")
    assert conn.execute("SELECT soort, vorm FROM kenmerk WHERE pagina = ?", (proef,)).fetchone() == ("ai", "beeld")
    assert conn.execute("SELECT naam FROM bron WHERE bron = 'factiz-redactie'").fetchone() == ("Factiz",)
    assert conn.execute("SELECT COUNT(*) FROM zoek WHERE nummer = ?", (proef,)).fetchone() == (1,)
    pb.controleer(voorbeeld["bestand"], concepten=True)
    # in een uitgave alleen wat gepubliceerd is
    uitgave = _bouw(tmp_path / "b", [_gepubliceerd(), tr._check()])
    conn = sqlite3.connect(uitgave["bestand"])
    assert conn.execute("SELECT pagina FROM check_ WHERE redactie = 'Factiz'").fetchall() == [(pb.nummer("factiz-gepubliceerd"),)]


def test_the_archive_shows_an_own_check_as_newsroom_factiz_with_the_seal_and_a_link_to_its_own_page(voorbeeld):
    client, _ = voorbeeld
    proef = pb.nummer("factiz-proef")
    rijen = client.get("/api/nl/archief?redactie=Factiz").json()["rijen"]
    assert sorted(r["nummer"] for r in rijen) == sorted([proef, pb.nummer("factiz-gepubliceerd")])
    assert all(r["eigen"] == "Onwaar" for r in rijen)
    # een rij van een andere redactie krijgt geen zegel
    assert not any("eigen" in r for r in client.get("/api/nl/archief?redactie=Snopes").json()["rijen"])
    assert next(r for r in client.get("/api/en/archief").json()["rijen"] if r["nummer"] == proef)["eigen"] == "False"
    pagina = client.get(f"/api/nl/factcheck/{proef}")
    # de link van de check is een pad op deze site, zodat hij ook in een voorbeeld werkt
    assert pagina.status_code == 200 and '"/nl/radar/2026/12/standbeeld-anne-frank-ai/"' in pagina.text
    assert "https://factiz.org/nl/radar" not in pagina.text
    # en de site gaat meteen naar de check zelf, net als een rij in een lijst (PO 2026-11-18)
    assert pagina.json()["eigen_href"] == "/nl/radar/2026/12/standbeeld-anne-frank-ai/"
    assert next(r for r in rijen if r["nummer"] == proef)["href"] == "/nl/radar/2026/12/standbeeld-anne-frank-ai/"
    gewoon = client.get("/api/nl/archief?redactie=Snopes").json()["rijen"][0]
    assert "eigen_href" not in client.get(f"/api/nl/factcheck/{gewoon['nummer']}").json()
    assert "Factiz" in [r["naam"] for r in client.get("/api/nl/redacties").json()["redacties"]]


def test_radar_in_the_archive_counts_only_published_checks_in_that_language_and_what_is_new_that_week(tmp_path):
    """Factiz Radar (PO 2026-11-19): het archief zegt per taal hoeveel eigen checks er gepubliceerd zijn, hoeveel van de
    zeven dagen tot en met de dag van de uitgave (2 december), en welke de nieuwste is; een concept telt nooit mee, en in
    een taal zonder eigen check is er geen radar."""
    oud = _gepubliceerd(sleutel="oud", gepubliceerd="2026-11-20", kop="Een oudere check")
    nieuw = _gepubliceerd(sleutel="nieuw", gepubliceerd="2026-11-30", kop="De nieuwste check")
    manifest = _bouw(tmp_path, [oud, nieuw, tr._check(sleutel="proef")], concepten=True)
    client = TestClient(fa.maak_app(manifest["bestand"]))
    r = client.get("/api/nl/archief").json()["radar"]
    assert r["href"] == "/nl/radar/" and r["aantal"] == 2 and r["nieuw"] == 1
    assert r["aantal_tekst"] == "2 eigen checks" and r["nieuw_tekst"] == "1 nieuw deze week"
    assert r["nieuwste"] == {"kop": "De nieuwste check", "href": "/nl/radar/2026/11/nieuw-check-nl/"}
    assert client.get("/api/en/archief").json()["radar"] is None


def test_radar_does_not_pulse_when_nothing_is_new_that_week(tmp_path):
    manifest = _bouw(tmp_path, [_gepubliceerd(sleutel="oud", gepubliceerd="2026-11-01")])
    r = TestClient(fa.maak_app(manifest["bestand"])).get("/api/nl/archief").json()["radar"]
    assert r["aantal"] == 1 and r["nieuw"] == 0 and r["nieuw_tekst"] == "" and r["aantal_tekst"] == "1 eigen check"


def test_the_radar_sidebar_counts_the_archive_for_factiz_and_links_each_count_to_exactly_those_checks(voorbeeld):
    """De zijkolom van Factiz Radar (PO 2026-11-19): hoe het werkt, wat we vonden uit de tellingen van het archief voor de
    redactie Factiz (elke telling linkt naar precies die checks), de dossiers en een tip per mail."""
    client, _ = voorbeeld
    z = client.get("/api/nl/eigen").json()["zijkolom"]
    assert "werkwijze" not in z                         # geen uitleg van hoe het werkt (PO 2026-11-22: "Ja, alle drie weg")
    assert z["oordelen"] and all(r["href"].startswith("/nl/fact-checks/?") and "redactie=Factiz" in r["href"]
                                 for r in z["oordelen"] + z["soorten"] + z["vormen"])
    assert z["oordelen"][0]["naam"] == "Onwaar" and "oordeel=onwaar" in z["oordelen"][0]["href"]
    assert z["archief"] == "/nl/fact-checks/?redactie=Factiz"
    assert z["tip"]["adres"] == fa.CONTACT and z["tip"]["href"] == f"mailto:{fa.CONTACT}?subject=Tip%20voor%20Factiz%20Radar"
    assert fa.EIGEN_REDACTIE == pb.EIGEN_BRON["naam"]          # de naam waarmee publiceren de checks in het archief zet


def test_a_translated_own_check_reads_in_the_site_language_says_it_is_a_machine_translation_and_links_the_original(voorbeeld):
    """B85 (PO 2026-11-19: "Ja, alle veertien talen"): op de Engelse site staat de check in het Engels, met de regel dat het
    een machinevertaling is en de link naar het Nederlandse origineel; zoekmachines zien alleen het origineel."""
    client, _ = voorbeeld
    lijst = client.get("/api/en/eigen").json()
    assert [(c["sleutel"], c["vertaald"]) for c in lijst["checks"]] == [("gepubliceerd", True)]
    e = client.get("/api/en/eigen/gepubliceerd").json()
    assert e["kop"].startswith("EN ") and e["taal"] == "en" and e["brontaal"] == "nl"
    assert e["vertaling"]["origineel"] == "/nl/radar/2026/12/gepubliceerd-check-nl/" and e["vertaling"]["tekst"] == "Machine translation from Dutch."
    assert client.get("/api/nl/eigen/gepubliceerd").json()["vertaling"] is None
    assert client.get("/api/de/eigen/gepubliceerd").status_code == 404           # geen Duitse vertaling
    # het archief: de radar telt de vertaalde check, en de rij gaat naar de Engelse pagina met de vertaalde bewering
    assert client.get("/api/en/archief").json()["radar"]["aantal"] == 1
    rij = next(r for r in client.get("/api/en/archief").json()["rijen"] if r.get("eigen"))
    assert rij["href"] == "/radar/2026/12/gepubliceerd-check-en/" and rij["tekst"].startswith("EN ") and rij["origineel"]


def test_the_radar_of_another_language_puts_its_own_checks_first_then_international_ones_then_the_rest(tmp_path):
    """B85 (PO 2026-11-19): op de Engelse Radar eerst wat in het Engels rondging, dan wat internationaal speelt, dan
    "Uit andere landen"; op de Nederlandse alles uit het Nederlands."""
    eng = {"en": _engels()}
    checks = [_gepubliceerd(sleutel="lokaal", reikwijdte="lokaal", vertalingen=eng),
              _gepubliceerd(sleutel="wereld", reikwijdte="internationaal", vertalingen=eng),
              tr._check(sleutel="engels", taal="en", **KLAAR)]
    client = TestClient(fa.maak_app(_bouw(tmp_path, checks)["bestand"]))
    lijst = client.get("/api/en/eigen").json()["checks"]
    assert [(c["sleutel"], c["groep"]) for c in lijst] == [("engels", "hier"), ("wereld", "internationaal"), ("lokaal", "elders")]
    assert {c["groep"] for c in client.get("/api/nl/eigen").json()["checks"]} == {"hier"}



def test_a_check_has_one_address_per_language_with_year_month_and_a_short_name_and_old_addresses_point_to_it(voorbeeld):
    """PLAN #37.11 (PO 2026-11-21: "Jaar en maand"): het adres van een check draagt het jaar en de maand van publicatie en
    een korte naam van de bewering, in haar eigen taal; een vertaling draagt de Engelse naam. Het oude adres (de werknaam)
    geeft dezelfde check, zodat de site blijvend kan doorsturen."""
    client, _ = voorbeeld
    e = client.get("/api/nl/eigen/2026/12/gepubliceerd-check-nl").json()
    assert e["sleutel"] == "gepubliceerd" and e["href"] == "/nl/radar/2026/12/gepubliceerd-check-nl/"
    assert e["paden"] == {"nl": "/nl/radar/2026/12/gepubliceerd-check-nl/", "en": "/radar/2026/12/gepubliceerd-check-en/"}
    assert e["maand"] == {"tekst": "december 2026", "href": "/nl/radar/2026/12/"}
    assert client.get("/api/en/eigen/2026/12/gepubliceerd-check-en").json()["href"] == "/radar/2026/12/gepubliceerd-check-en/"
    # de naam van een andere taal stuurt door naar de naam van deze taal; een naam in een andere maand bestaat niet
    assert client.get("/api/en/eigen/2026/12/gepubliceerd-check-nl").json() == {"doorsturen": "/radar/2026/12/gepubliceerd-check-en/"}
    for pad in ("/api/nl/eigen/2026/11/gepubliceerd-check-nl", "/api/de/eigen/2026/12/gepubliceerd-check-en",
                "/api/nl/eigen/2026/12/onbekend-adres", "/api/nl/eigen/2026/13/gepubliceerd-check-nl",
                "/api/nl/eigen/26/12/gepubliceerd-check-nl", "/api/nl/eigen/2026/1/gepubliceerd-check-nl"):
        assert client.get(pad).status_code == 404, pad
    # het oude adres: dezelfde check, met haar nieuwe adres
    assert client.get("/api/nl/eigen/gepubliceerd").json()["href"] == "/nl/radar/2026/12/gepubliceerd-check-nl/"


def test_the_radar_has_a_page_per_year_and_per_month_with_only_the_checks_of_that_period(tmp_path):
    oud = _gepubliceerd(sleutel="oud", gepubliceerd="2026-11-20")
    nieuw = _gepubliceerd(sleutel="nieuw", gepubliceerd="2026-12-01")
    client = TestClient(fa.maak_app(_bouw(tmp_path, [oud, nieuw])["bestand"]))
    maand = client.get("/api/nl/eigen/2026/11").json()
    assert [c["sleutel"] for c in maand["checks"]] == ["oud"]
    assert maand["periode"] == {"tekst": "november 2026", "jaar": "2026", "jaar_href": "/nl/radar/2026/",
                                "maand": "11", "href": "/nl/radar/2026/11/"}
    jaar = client.get("/api/nl/eigen/2026").json()
    assert [c["sleutel"] for c in jaar["checks"]] == ["nieuw", "oud"]
    assert jaar["periode"] == {"tekst": "2026", "jaar": "2026", "jaar_href": "/nl/radar/2026/", "maand": "",
                               "href": "/nl/radar/2026/"}
    assert client.get("/api/nl/eigen").json()["periode"] is None
    # de maanden in de zijkolom, de nieuwste eerst, elk met haar aantal
    assert client.get("/api/nl/eigen").json()["zijkolom"]["maanden"] == [
        {"naam": "december 2026", "href": "/nl/radar/2026/12/", "aantal": "1"},
        {"naam": "november 2026", "href": "/nl/radar/2026/11/", "aantal": "1"}]
    for pad in ("/api/nl/eigen/2025", "/api/nl/eigen/2026/10", "/api/en/eigen/2026/11"):
        assert client.get(pad).status_code == 404, pad


def test_a_translation_the_editors_read_is_findable_and_says_so_and_an_unread_one_is_not(tmp_path):
    """PLAN #37.11 (PO 2026-11-21: "ja dat ook graag"): zoekmachines zien het origineel en een vertaling die de redactie
    las; de pagina zegt dan dat de redactie haar las. Een concept is nergens vindbaar."""
    gelezen = {"en": {**_engels(), "nagelezen": True}}
    client = TestClient(fa.maak_app(_bouw(tmp_path, [_gepubliceerd(vertalingen=gelezen)])["bestand"]))
    e = client.get("/api/en/eigen/gepubliceerd").json()
    assert e["vindbaar_in"] == ["nl", "en"] and e["vindbaar"] is True
    assert e["vertaling"]["nagelezen"] is True and e["vertaling"]["tekst"] == "Machine translation from Dutch, reviewed by our editors."
    assert client.get("/api/en/eigen").json()["checks"][0]["vindbaar"] is True
    assert client.get("/api/en/eigen").json()["checks"][0]["gepubliceerd_iso"] == "2026-12-01"     # voor de sitemap

    client, _ = _site_ongelezen(tmp_path)
    e = client.get("/api/en/eigen/gepubliceerd").json()
    assert e["vindbaar_in"] == ["nl"] and e["vindbaar"] is False and e["vertaling"]["nagelezen"] is False
    assert client.get("/api/nl/eigen/2026/12/standbeeld-anne-frank-ai").json()["vindbaar_in"] == []    # een concept


def _site_ongelezen(tmp_path):
    manifest = _bouw(tmp_path / "ongelezen", [_gepubliceerd(vertalingen={"en": _engels()}), tr._check(sleutel="proef")],
                     concepten=True)
    return TestClient(fa.maak_app(manifest["bestand"])), manifest


def test_two_checks_with_the_same_address_in_one_month_stop_the_build(tmp_path):
    a = _gepubliceerd(sleutel="a", adres="zelfde-naam")
    b = _gepubliceerd(sleutel="b", adres="zelfde-naam")
    with pytest.raises(pb.Weigering, match="zelfde-naam"):
        _bouw(tmp_path, [a, b])


def test_a_radar_list_gives_each_check_the_same_card_as_the_archive(tmp_path):
    """PO 2026-11-21: "radar hebben we anders gebouwd dan de rest, hier hebben we een lijst ipv cards? zullen we alles een
    beetje gelijk trekken": elke check in de Radar krijgt de gegevens van de kaart van het archief (`Rij.jsx`): het zegel
    met het oordeel, de datum, de kop van de check, en het thema, de soort, de vorm en het land van haar pagina in het
    archief; een vertaling met de regel en het origineel eronder, een concept met dat woord."""
    from tests import test_redactie as tr2

    gelezen = {"en": _engels()}
    client = TestClient(fa.maak_app(_bouw(tmp_path, [_gepubliceerd(vertalingen=gelezen), tr2._check(sleutel="proef")],
                                          concepten=True)["bestand"]))
    nl = {c["sleutel"]: c["rij"] for c in client.get("/api/nl/eigen").json()["checks"]}
    r = nl["gepubliceerd"]
    assert r["href"] == "/nl/radar/2026/12/gepubliceerd-check-nl/" and r["eigen"] == "Onwaar" and r["soort"] == "onwaar"
    assert r["tekst"] == tr2._check()["kop"] and r["taal"] == "nl" and r["datum"] == "1 december 2026"
    assert r["origineel"] is None and r["concept"] == "" and r["nummer"] == pb.nummer("factiz-gepubliceerd")
    assert [k["wat"] for k in r["kenmerken"]] == ["soort", "vorm"]
    assert nl["proef"]["concept"] == "Concept, niet gepubliceerd"
    en = client.get("/api/en/eigen").json()["checks"][0]["rij"]
    assert en["tekst"].startswith("EN ") and en["taal"] == "en"
    assert en["origineel"]["tekst"] == tr2._check()["kop"] and en["origineel"]["taal"] == "nl"
    assert en["origineel"]["regel"] == "Machine-translated from Dutch. Original:"
