"""De HTML van de site zelf (PLAN #34.2v): de site in `site/` gebouwd, met node gestart tegen de gegevenslaag op een
proefuitgave, en de echte pagina's gelezen. Met de Jinja-pagina's (weg sinds #34.2f stap 4) gingen de tests op de HTML
weg; deze lezen wat een bezoeker en een zoekmachine krijgen. DESIGNSYSTEEM §6, B75, DESIGN §4o, SPECS E9.S3 en E9.S4.
"""

import base64
import hashlib
import json
import os
import re
import socket
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser

import pytest
import uvicorn

from doublecheck import namen as nm
from doublecheck import publiceren as pb
from factiz_site import app as fa
from factiz_site import db, i18n
from tests import websitebouw
from tests.test_factiz_dossiers import NAAM, _dossier
from tests.test_factiz_namen import ZELENSKY
from tests.test_factiz_themas import LANDEN, THEMAS
from tests.test_publiceren import EU, REGISTER, _check, _claim, _lab

TALEN = ("en", "nl", "de", "es", "fr")
BASIS = "https://factiz.org"
ARABISCH = "زيلينسكي اشترى فيلا في فلوريدا"
# een script, een beeld dat script start, een teken dat de leesrichting van de rest omdraait (U+202E, gesloten met
# U+202C), een dat een onzichtbare richting opent (U+2066), een onzichtbaar teken (U+FEFF), en het verbindingsteken van
# het Perzisch (U+200C), dat moet blijven
VIJANDIG = ('<script>alert(1)</script> "><img src=x onerror=alert(1)> ‮omgekeerd‬ ⁦verstopt﻿ '
            "می‌خواهم")
WEG = ("‮", "‬", "⁦", "﻿")
VIJANDIGE_NAAM = "<img src=x onerror=alert(1)>"


def _pad(taal, pad):
    """Het adres in een taal: Engels op de hoofdmap, anders onder het pad van de taal (/nl/, /pt-br/, B79)."""
    return pad if taal == "en" else f"/{i18n.PAD[taal]}{pad}"


# --- de proefuitgave, de gegevenslaag en de site ------------------------------------------------------------------------

def _uitgave(map_, met_namen=True):
    """Een proefuitgave met wat de pagina's moeten kunnen: een bewering met een Nederlandse vertaling, een Arabische zonder,
    een Spaanse, een vijandige, een dossier met een link naar buiten, thema's, namen, en genoeg beweringen voor een
    tweede blad."""
    lab = _lab(map_)
    n = {"villa": _claim(lab, 1, "Zelensky bought a villa in Florida"),
         "arabisch": _claim(lab, 2, ARABISCH, taal="ar"),
         "spaans": _claim(lab, 3, "Zelenski compró un yate de lujo", taal="es"),
         "vijandig": _claim(lab, 4, VIJANDIG),
         "biolab": _claim(lab, 5, "Ukraine hosts secret biolabs")}
    _check(lab, n["villa"], "https://snopes.com/villa", datum="2024-03-05")
    _check(lab, n["villa"], "https://factcheck.afp.com/villa", datum="2022-04-01", taal="fr", eigen="Faux")
    _check(lab, n["arabisch"], "https://euvsdisinfo.eu/report/villa", bron=EU, datum="2022-11-22", eigen="Disinformation",
           taal="ar")
    _check(lab, n["spaans"], "https://maldita.es/yate", datum="2023-12-01", taal="es", eigen="Bulo")
    _check(lab, n["vijandig"], "https://snopes.com/x", eigen='<b>False</b> "><script>x</script>')
    _check(lab, n["biolab"], "https://euvsdisinfo.eu/report/biolab", bron=EU, datum="2022-03-10", eigen="Disinformation")
    for i in range(db.PER_BLAD):      # een tweede blad in de lijst
        vulsel = _claim(lab, 100 + i, f"A filler claim about the moon number {i}")
        _check(lab, vulsel, f"https://snopes.com/maan-{i}", datum="2020-01-01")
    lab.commit()
    nr = {k: pb.nummer(v) for k, v in n.items()}
    items = [{"soort": "onderzoek", "datum": "2023-12-20", "bron": "BBC Verify", "url": "https://www.bbc.com/news/x",
              "titel": {taal: f"Hoe het verhaal reisde ({taal})" for taal in TALEN}}]
    dossier = _dossier("zelensky-luxury", [nr["villa"], nr["spaans"]], naam=NAAM, items=items)
    indeling = {nr["villa"]: {"thema": "war", "onderdeel": "ukraine", "tweede": "", "land": "UA"},
                nr["biolab"]: {"thema": "health", "onderdeel": "", "tweede": "", "land": ""}}
    namen = {"namen": {
        "Q3874799": {"soort": "persoon", "namen": ZELENSKY, "wikis": 150, "paginas": [nr["villa"], nr["spaans"]]},
        "Q99": {"soort": "organisatie", "namen": {taal: VIJANDIGE_NAAM for taal in TALEN}, "wikis": 9,
                "paginas": [nr["villa"], nr["biolab"]]}},
        "per_pagina": {nr["villa"]: ["Q3874799", "Q99"], nr["spaans"]: ["Q3874799"], nr["biolab"]: ["Q99"]}}
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(nm, "MIN_PAGINAS", 2)
        manifest = pb.bouw(lab, map_ / "uit", register=REGISTER, vaag=frozenset(), datum="2026-11-13", indeling=indeling,
                           themas=THEMAS, landen=LANDEN, vertaalmaker="proef",
                           vertalingen={"nl": {nr["villa"]: "Zelensky kocht een villa in Florida"}},
                           dossiers=[dossier], namen=namen if met_namen else None)
    return manifest["bestand"], nr


def _vrije_poort() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wacht(url: str, tijd: float = 30) -> None:
    einde = time.monotonic() + tijd
    while time.monotonic() < einde:
        try:
            urllib.request.urlopen(url, timeout=2)
            return
        except urllib.error.HTTPError:
            return
        except OSError:
            time.sleep(0.1)
    raise RuntimeError(f"start niet: {url}")


class _Blijf(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


class Draaiend:
    """De site (node, met het platform in TypeScript op hetzelfde bestand) en de Python-app ernaast (uvicorn, in een draad),
    om de gegevens naast de pagina te leggen; elk op een vrije poort.
    `FACTIZ_VINDBAAR` gaat alleen mee als de proef de livegang nabootst."""

    def __init__(self, bestand, vindbaar: bool | str = False):
        self.api_poort, self.poort = _vrije_poort(), _vrije_poort()
        self.server = uvicorn.Server(uvicorn.Config(fa.maak_app(bestand), host="127.0.0.1", port=self.api_poort,
                                                    log_level="error", lifespan="off"))
        threading.Thread(target=self.server.run, daemon=True).start()
        omgeving = {k: v for k, v in os.environ.items() if k != "FACTIZ_VINDBAAR"}
        # de site leest de uitgave zelf, met het platform in TypeScript (B80); de Python-app ernaast blijft voor `api()`
        omgeving |= {"HOST": "127.0.0.1", "PORT": str(self.poort), "FACTIZ_PUBLICATIE": str(bestand)}
        if vindbaar:
            # True: alles wat vindbaar is (stand 3); een tekst: die stand (PLAN #34.2bt)
            omgeving["FACTIZ_VINDBAAR"] = "3" if vindbaar is True else vindbaar
        self.node = subprocess.Popen(["node", str(websitebouw.site())], env=omgeving, stdout=subprocess.DEVNULL,
                                     stderr=subprocess.DEVNULL)
        self._bewaard: dict = {}
        _wacht(f"http://127.0.0.1:{self.api_poort}/robots.txt")
        _wacht(f"http://127.0.0.1:{self.poort}/about/")

    def haal(self, pad: str, bericht: dict | None = None, koppen: dict | None = None):
        """(status, koppen, tekst) van de site, zonder een doorverwijzing te volgen; een GET één keer per test-run. Met een
        `bericht` een gepost formulier zoals de browser het stuurt (zoeken), van de site zelf tenzij `koppen` anders zegt."""
        if bericht is None and pad in self._bewaard:
            return self._bewaard[pad]
        adres = f"http://127.0.0.1:{self.poort}{pad}"
        verzoek = urllib.request.Request(adres)
        if bericht is not None:
            verzoek = urllib.request.Request(adres, data=urllib.parse.urlencode(bericht).encode(), method="POST",
                                             headers={"Origin": f"http://127.0.0.1:{self.poort}",
                                                      "Content-Type": "application/x-www-form-urlencoded", **(koppen or {})})
        try:
            with urllib.request.build_opener(_Blijf).open(verzoek, timeout=30) as r:
                antwoord = r.status, {k.lower(): v for k, v in r.headers.items()}, r.read().decode("utf-8")
        except urllib.error.HTTPError as fout:
            antwoord = fout.code, {k.lower(): v for k, v in fout.headers.items()}, fout.read().decode("utf-8", "replace")
        if bericht is None:
            self._bewaard[pad] = antwoord
        return antwoord

    def api(self, pad: str) -> dict:
        with urllib.request.urlopen(f"http://127.0.0.1:{self.api_poort}{pad}", timeout=30) as r:
            return json.loads(r.read())

    def stop(self):
        self.node.terminate()
        self.node.wait(timeout=10)
        self.server.should_exit = True


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    bestand, nr = _uitgave(tmp_path_factory.mktemp("sitehtml"))
    draaiend = Draaiend(bestand)
    yield draaiend, nr
    draaiend.stop()


@pytest.fixture(scope="module")
def stap_een(tmp_path_factory):
    """De site in de eerste stap (`FACTIZ_VINDBAAR=1`, PLAN #34.2bt)."""
    bestand, nr = _uitgave(tmp_path_factory.mktemp("sitehtml-stap1"))
    draaiend = Draaiend(bestand, vindbaar="1")
    yield draaiend, nr
    draaiend.stop()


@pytest.fixture(scope="module")
def stap_twee(tmp_path_factory):
    """De site in de tweede stap (`FACTIZ_VINDBAAR=2`): elke factcheck één keer."""
    bestand, nr = _uitgave(tmp_path_factory.mktemp("sitehtml-stap2"))
    draaiend = Draaiend(bestand, vindbaar="2")
    yield draaiend, nr
    draaiend.stop()


@pytest.fixture(scope="module")
def stap_drie(tmp_path_factory):
    """De site in de derde stap (`FACTIZ_VINDBAAR=3`): elke factcheck in elke taal met eigen tekst."""
    bestand, nr = _uitgave(tmp_path_factory.mktemp("sitehtml-stap3"))
    draaiend = Draaiend(bestand, vindbaar="3")
    yield draaiend, nr
    draaiend.stop()


@pytest.fixture(scope="module")
def open_zonder_namen(tmp_path_factory):
    """De site zoals na de livegang (`FACTIZ_VINDBAAR=1`), op een uitgave zonder namen."""
    bestand, nr = _uitgave(tmp_path_factory.mktemp("sitehtml-open"), met_namen=False)
    draaiend = Draaiend(bestand, vindbaar=True)
    yield draaiend, nr
    draaiend.stop()


# --- de HTML lezen ------------------------------------------------------------------------------------------------------

LEEG = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}


class Pagina(HTMLParser):
    """De elementen van een pagina, elk met zijn attributen, de elementen waar het in staat en zijn tekst."""

    def __init__(self, tekst: str):
        super().__init__(convert_charrefs=True)
        self.bron = tekst
        self.elementen: list[dict] = []
        self._open: list[dict] = []
        self.zichtbaar: list[str] = []      # de tekst buiten script en opmaak: wat de bezoeker leest
        self.feed(tekst)
        self.close()

    def handle_starttag(self, tag, attrs):
        el = {"tag": tag, "attrs": dict(attrs), "binnen": tuple(e["tag"] for e in self._open), "tekst": []}
        self.elementen.append(el)
        if tag not in LEEG:
            self._open.append(el)

    def handle_startendtag(self, tag, attrs):
        self.elementen.append({"tag": tag, "attrs": dict(attrs), "binnen": tuple(e["tag"] for e in self._open),
                               "tekst": []})

    def handle_endtag(self, tag):
        for i in range(len(self._open) - 1, -1, -1):
            if self._open[i]["tag"] == tag:
                del self._open[i:]
                return

    def handle_data(self, data):
        for el in self._open:
            el["tekst"].append(data)
        if not self._open or self._open[-1]["tag"] not in ("script", "style"):
            self.zichtbaar.append(data)

    def alle(self, tag: str, **attrs) -> list[dict]:
        return [e for e in self.elementen
                if e["tag"] == tag and all(e["attrs"].get(k.replace("_", "-")) == v for k, v in attrs.items())]

    def tekst(self, el: dict) -> str:
        return "".join(el["tekst"])

    def meta(self, sleutel: str) -> str | None:
        gevonden = [e["attrs"].get("content") for e in self.elementen
                    if e["tag"] == "meta" and sleutel in (e["attrs"].get("name"), e["attrs"].get("property"))]
        assert len(gevonden) <= 1, (sleutel, gevonden)
        return gevonden[0] if gevonden else None

    def links(self, rel: str) -> list[dict]:
        return [e["attrs"] for e in self.elementen if e["tag"] == "link" and e["attrs"].get("rel") == rel]

    def hreflang(self) -> dict[str, str]:
        return {a["hreflang"]: a["href"] for a in self.links("alternate") if "hreflang" in a}

    def eilanden(self, naam: str) -> list[dict]:
        """De gegevens die een onderdeel met script van de server meekrijgt (Astro: `[0, waarde]`, `[1, rij]`)."""
        def lees(w):
            soort, waarde = w
            if soort == 1:
                return [lees(x) for x in waarde]
            return {k: lees(v) for k, v in waarde.items()} if isinstance(waarde, dict) else waarde
        return [{k: lees(v) for k, v in json.loads(e["attrs"]["props"]).items()} for e in self.alle("astro-island")
                if f"/{naam}." in e["attrs"].get("component-url", "")]


def _lees(site, pad) -> Pagina:
    status, _, tekst = site.haal(pad)
    assert status == 200, (pad, status)
    return Pagina(tekst)


def _vaste_paden() -> list[str]:
    """De pagina's die in elke taal vindbaar zijn: de start, de vaste pagina's en de overzichten met een eigen pad."""
    # de letter van de vijandige naam: in elke taal dezelfde, onder de andere tekens
    return ["/", "/fact-checks/", "/fact-checks/?p=2", "/themes/", "/themes/war/", "/themes/war/ukraine/", "/dossiers/",
            "/dossiers/zelensky-luxury/", "/names/", "/names/?letter=0&soort=organisatie", "/names/Q3874799/", "/newsrooms/",
            "/sources/", "/about/", "/platform/", "/explore/", "/explore/network/"]


FILTERS = ("/fact-checks/?taal=en", "/fact-checks/?oordeel=onwaar", "/fact-checks/?jaar=2024", "/fact-checks/?land=UA",
           "/fact-checks/?sorteer=oud", "/fact-checks/?thema=war",
           "/explore/?thema=war", "/explore/?maat=verhouding&thema=war", "/explore/network/?naam=Q3874799")
NIET_GEVONDEN = ("/bestaat-niet/", "/fact-checks/zzz/", "/fact-checks/00000000000000ff/", "/dossiers/onbekend/",
                 "/themes/onbekend/", "/names/Q1/", "/fact-checks/?taal=xx",
                 "/explore/?thema=onbekend", "/explore/?maat=verhouding", "/explore/war/", "/explore/network/?naam=Q1",
                 "/explore/network/x/")


def _alle_paden(site, nr) -> list[str]:
    return _vaste_paden() + list(FILTERS) + [f"/fact-checks/{n}/" for n in nr.values()]


# --- 1. hreflang en canonical (DESIGNSYSTEEM §6) ------------------------------------------------------------------------

@pytest.mark.parametrize("taal", TALEN)
def test_a_fact_check_is_findable_only_in_the_languages_with_its_own_text(site, taal):
    s, nr = site
    for soort, nummer in nr.items():
        talen = s.api(f"/api/{taal}/factcheck/{nummer}")["vindbaar"]["talen"]
        p = _lees(s, _pad(taal, f"/fact-checks/{nummer}/"))
        canonical = p.links("canonical")
        if taal in talen:
            assert [c["href"] for c in canonical] == [BASIS + _pad(taal, f"/fact-checks/{nummer}/")], (soort, taal)
            verwacht = {code: BASIS + _pad(code, f"/fact-checks/{nummer}/") for code in talen}
            verwacht["x-default"] = verwacht["en" if "en" in talen else talen[0]]
            assert p.hreflang() == verwacht, (soort, taal)
        else:
            # een pagina waarvan alleen menu en knoppen vertaald zijn, is voor een zoekmachine een kopie
            assert canonical == [] and p.hreflang() == {}, (soort, taal)


def test_the_languages_of_a_fact_check_follow_its_own_text(site):
    s, nr = site
    talen = {soort: s.api(f"/api/en/factcheck/{nummer}")["vindbaar"]["talen"] for soort, nummer in nr.items()}
    assert talen["villa"] == ["en", "nl"]           # Engels, en een Nederlandse vertaling
    assert talen["arabisch"] == ["ar"]              # sinds B79 een taal van de site: daar is de bewering eigen tekst
    assert talen["spaans"] == ["es"]                # alleen Spaans, en dat is dan ook de x-default
    hreflang = _lees(s, f"/es/fact-checks/{nr['spaans']}/").hreflang()
    assert hreflang == {"es": f"{BASIS}/es/fact-checks/{nr['spaans']}/", "x-default": f"{BASIS}/es/fact-checks/{nr['spaans']}/"}


@pytest.mark.parametrize("taal", TALEN)
def test_the_fixed_pages_and_the_overviews_are_findable_in_every_language(site, taal):
    s, _ = site
    for pad in _vaste_paden():
        p = _lees(s, _pad(taal, pad))
        if re.fullmatch(r"/names/Q\d+/", pad):          # SPECS E9.S8 AC9: een pagina per naam pas na een juridische toets
            assert not p.links("canonical") and not p.hreflang(), (taal, pad)
            continue
        assert [c["href"] for c in p.links("canonical")] == [BASIS + _pad(taal, pad)], (taal, pad)
        verwacht = {i18n.BCP47[code]: BASIS + _pad(code, pad) for code in i18n.TALEN} | {"x-default": BASIS + pad}
        assert p.hreflang() == verwacht, (taal, pad)


@pytest.mark.parametrize("taal", TALEN)
def test_a_list_with_filters_or_another_order_is_never_findable(site, taal):
    s, _ = site
    for pad in FILTERS:
        p = _lees(s, _pad(taal, pad))
        assert p.links("canonical") == [] and p.hreflang() == {}, (taal, pad)
    # zoeken heeft geen adres, en het antwoord is dus ook niet vindbaar
    status, _, tekst = s.haal(_pad(taal, "/fact-checks/"), {"q": "villa"})
    assert status == 200 and Pagina(tekst).links("canonical") == [], taal


def test_a_missing_file_is_a_plain_not_found_and_never_a_lasting_redirect(site):
    """Een bestand dat er niet is (of even niet, tijdens een bouw) krijgt een 404, geen 301 naar een adres met een slash:
    een browser onthoudt een 301 voorgoed, en dan bleven de velden weg (PO 2026-11-15: "Ik zie dat de achtergrond weg
    is, nu alleen de ruis over"). Een pagina zonder slash stuurt wel blijvend door."""
    s, _ = site
    for pad in ("/static/bestaat-niet.css", "/static/beeld/bestaat-niet.webp", "/nl/iets.json"):
        status, koppen, _ = s.haal(pad)
        assert status == 404 and "location" not in koppen, (pad, status)
    status, koppen, _ = s.haal("/about")
    assert status == 301 and koppen["location"].endswith("/about/")
    # het stijlblad van de velden draagt de versie van zijn inhoud in het adres, en dat adres bestaat
    p = _lees(s, "/")
    [velden] = [a["href"] for a in p.links("stylesheet") if "velden.css" in a["href"]]
    assert re.fullmatch(r"/static/velden\.css\?v=[0-9a-f]{8}", velden) and s.haal(velden)[0] == 200


@pytest.mark.parametrize("taal", TALEN)
def test_a_theme_page_carries_the_list_with_its_theme_fixed(site, taal):
    """PLAN #34.2bb, SPECS E9.S27: de lijst met filters op de themapagina, het thema (en het onderdeel) vast; met filters
    in het adres niet vindbaar, zonder wel."""
    s, nr = site
    p = _lees(s, _pad(taal, "/themes/war/"))
    [bieb] = p.eilanden("Bibliotheek")
    assert bieb["vast"] == [["thema", "war"]] and bieb["basis"] == _pad(taal, "/themes/war/")
    assert [r["nummer"] for r in bieb["begin"]["rijen"]] == [nr["villa"]]
    assert p.links("canonical")
    [deel] = _lees(s, _pad(taal, "/themes/war/ukraine/")).eilanden("Bibliotheek")
    assert deel["vast"] == [["thema", "war"], ["onderdeel", "ukraine"]]
    gefilterd = _lees(s, _pad(taal, "/themes/war/?oordeel=onwaar"))
    assert gefilterd.links("canonical") == [] and gefilterd.hreflang() == {}
    [g] = gefilterd.eilanden("Bibliotheek")
    assert g["beginParen"] == [["oordeel", "onwaar"]]
    # op de pagina van een thema is het onderdeel een filter van de bezoeker, dus het blijft na herladen staan
    [o] = _lees(s, _pad(taal, "/themes/war/?onderdeel=ukraine")).eilanden("Bibliotheek")
    assert o["vast"] == [["thema", "war"]] and o["beginParen"] == [["onderdeel", "ukraine"]]


# --- 2. niets naar zoekmachines tot de livegang -------------------------------------------------------------------------

def test_nothing_goes_to_search_engines_until_the_launch(site):
    s, nr = site
    for taal in TALEN:
        for pad in _alle_paden(s, nr):
            assert _lees(s, _pad(taal, pad)).meta("robots") == "noindex, nofollow", (taal, pad)


def test_after_the_launch_a_page_is_indexed_only_where_it_is_findable(open_zonder_namen):
    s, nr = open_zonder_namen
    for pad in ("/", "/about/", "/fact-checks/", f"/fact-checks/{nr['villa']}/", f"/nl/fact-checks/{nr['villa']}/",
                f"/es/fact-checks/{nr['spaans']}/", "/nl/themes/war/"):
        assert _lees(s, pad).meta("robots") == "index, follow", pad
    for pad in (f"/de/fact-checks/{nr['villa']}/", f"/nl/fact-checks/{nr['arabisch']}/", f"/fact-checks/{nr['spaans']}/",
                "/fact-checks/?taal=en", "/nl/fact-checks/?sorteer=oud"):
        assert _lees(s, pad).meta("robots") == "noindex, follow", pad
    status, _, tekst = s.haal("/nl/bestaat-niet/")
    assert status == 404 and Pagina(tekst).meta("robots") == "noindex, follow"


# --- 3. taal en richting (E9.S3 AC3) ------------------------------------------------------------------------------------

def _html(p: Pagina) -> dict:
    return p.alle("html")[0]["attrs"]


@pytest.mark.parametrize("taal", TALEN)
def test_every_page_has_the_language_of_its_address(site, taal):
    s, nr = site
    for pad in _alle_paden(s, nr):
        assert _html(_lees(s, _pad(taal, pad))) == {"lang": taal, "dir": "ltr"}, (taal, pad)


def test_a_claim_keeps_its_own_language_and_direction_inside_a_page_in_another_language(site):
    s, nr = site
    arabisch = _lees(s, f"/nl/fact-checks/{nr['arabisch']}/")
    [kop] = arabisch.alle("h1")
    assert kop["attrs"]["lang"] == "ar" and kop["attrs"]["dir"] == "rtl" and arabisch.tekst(kop) == ARABISCH
    assert _html(arabisch) == {"lang": "nl", "dir": "ltr"}
    # de vertaling in de kop, het origineel eronder in zijn eigen taal en richting
    villa = _lees(s, f"/nl/fact-checks/{nr['villa']}/")
    [kop] = villa.alle("h1")
    assert kop["attrs"]["lang"] == "nl" and villa.tekst(kop) == "Zelensky kocht een villa in Florida"
    assert "Zelensky bought a villa in Florida" in [villa.tekst(e) for e in villa.alle("span", lang="en", dir="ltr")]
    [kop] = _lees(s, f"/fr/fact-checks/{nr['spaans']}/").alle("h1")
    assert (kop["attrs"]["lang"], kop["attrs"]["dir"]) == ("es", "ltr")
    # het oordeel van een redactie staat in haar eigen taal
    assert _lees(s, f"/fact-checks/{nr['arabisch']}/").alle("span", lang="ar", dir="rtl")


# --- 4. één kop ---------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("taal", TALEN)
def test_every_page_has_exactly_one_h1(site, taal):
    s, nr = site
    for pad in _alle_paden(s, nr) + list(NIET_GEVONDEN):
        _, _, tekst = s.haal(_pad(taal, pad))
        assert len(Pagina(tekst).alle("h1")) == 1, (taal, pad)


# --- 5. niets van een andere host, geen script buiten de regel (B75) ----------------------------------------------------

def _regel(koppen: dict) -> dict[str, list[str]]:
    return {d.split()[0]: d.split()[1:] for d in koppen["content-security-policy"].split(";") if d.strip()}


def _hash(tekst: str) -> str:
    return "'sha256-" + base64.b64encode(hashlib.sha256(tekst.encode("utf-8")).digest()).decode() + "'"


# B88, SPECS E9.S36 AC4: alleen de hosts die Google Analytics na een ja nodig heeft, en niets anders
GOOGLE = {"script-src": {"https://www.googletagmanager.com"},
          "connect-src": {"https://*.google-analytics.com", "https://*.analytics.google.com", "https://*.googletagmanager.com"},
          "img-src": {"https://*.google-analytics.com", "https://*.googletagmanager.com"}}


def _eigen(adres: str) -> bool:
    return adres.startswith("/") and not adres.startswith("//")


@pytest.mark.parametrize("taal", TALEN)
def test_every_script_style_icon_and_image_comes_from_the_site_itself(site, taal):
    s, nr = site
    for pad in _alle_paden(s, nr) + ["/bestaat-niet/"]:
        _, koppen, tekst = s.haal(_pad(taal, pad))
        p, regel = Pagina(tekst), _regel(koppen)
        # de regel noemt geen andere host en geen ander soort bron dan de site zelf en de hashes van haar eigen stukjes
        assert regel["default-src"] == ["'none'"] and regel["base-uri"] == ["'none'"], pad
        for naam, bronnen in regel.items():
            toegestaan = {"'self'", "'none'"} | ({"'unsafe-inline'"} if naam == "style-src-attr" else set())
            toegestaan |= GOOGLE.get(naam, set())       # B88: Google Analytics, pas na een ja geladen
            assert all(b in toegestaan or re.fullmatch(r"'sha256-[A-Za-z0-9+/=]+'", b) for b in bronnen), (pad, naam, bronnen)
        for el in p.elementen:
            a = el["attrs"]
            assert not any(k.startswith("on") for k in a), (pad, el["tag"], a)             # geen script in een element
            assert el["tag"] not in ("iframe", "object", "embed", "base"), (pad, el["tag"])
            for sleutel in ("src", "srcset", "component-url", "renderer-url", "before-hydration-url"):
                if sleutel in a:
                    assert _eigen(a[sleutel]), (pad, el["tag"], sleutel, a[sleutel])
            if el["tag"] == "link" and a.get("rel") in ("stylesheet", "icon", "apple-touch-icon", "modulepreload",
                                                        "preload"):
                assert _eigen(a["href"]), (pad, a)
            if el["tag"] == "script" and "src" not in a and a.get("type") != "application/ld+json":
                assert _hash(p.tekst(el)) in regel["script-src"], (pad, p.tekst(el)[:80])
            if el["tag"] == "style":
                assert _hash(p.tekst(el)) in regel["style-src"], (pad, p.tekst(el)[:80])
        assert "url(http" not in tekst and "url(//" not in tekst, pad
        assert "set-cookie" not in koppen, pad


# --- 6. het woordmerk, het icoon en de koppen voor delen (DESIGN §4o) ---------------------------------------------------

@pytest.mark.parametrize("taal", TALEN)
def test_every_page_carries_the_wordmark_the_icon_and_the_heads_for_sharing(site, taal):
    s, nr = site
    start = _pad(taal, "/")
    locale = {"en": "en_GB", "nl": "nl_NL", "de": "de_DE", "es": "es_ES", "fr": "fr_FR"}[taal]
    for pad in ["/", "/sources/", f"/fact-checks/{nr['villa']}/", f"/fact-checks/{nr['vijandig']}/",
                "/dossiers/zelensky-luxury/", "/fact-checks/?taal=en", "/bestaat-niet/"]:
        _, _, tekst = s.haal(_pad(taal, pad))
        p = Pagina(tekst)
        # het woordmerk in de kop en in de voet, als link naar de start in deze taal, met de naam voor wie niet kijkt
        merken = [e for e in p.alle("a", aria_label="Factiz") if "merk" in e["attrs"].get("class", "")]
        assert [(e["attrs"]["href"], "header" in e["binnen"], "footer" in e["binnen"]) for e in merken] == \
            [(start, True, False), (start, False, True)], (taal, pad)
        assert len(p.alle("svg", **{"class": "woordmerk", "aria_hidden": "true"})) == 2, (taal, pad)
        assert 'fill="#FF5900"' in tekst and 'fill="currentColor"' in tekst        # het logo oranje, de letters de tekst
        assert {(a.get("type"), a["href"]) for a in p.links("icon")} == {
            (None, "/static/merk/favicon.ico"), ("image/svg+xml", "/static/merk/logo.svg")}
        assert [a["href"] for a in p.links("apple-touch-icon")] == ["/static/merk/apple-touch-icon.png"]
        # delen: de titel en de omschrijving van de pagina, het vaste beeld als volledig adres
        titel = p.tekst(p.alle("title")[0])
        artikel = pad.startswith("/fact-checks/0") or pad.startswith("/dossiers/")
        assert p.meta("og:site_name") == "Factiz" and p.meta("og:locale") == locale, (taal, pad)
        assert p.meta("og:type") == ("article" if artikel else "website"), (taal, pad)
        assert p.meta("og:title") == titel and titel.endswith(" · Factiz"), (taal, pad)
        assert p.meta("og:description") == p.meta("description") and p.meta("description"), (taal, pad)
        assert p.meta("og:url") == (None if pad == "/bestaat-niet/" else BASIS + _pad(taal, pad)), (taal, pad)
        # een factcheck en een dossier delen hun eigen plaatje (PLAN #34.2aq, #34.2ar); de andere pagina's het vaste beeld
        eigen = re.fullmatch(r"/fact-checks/([0-9a-f]{16})/", pad) or re.fullmatch(r"/(dossier)s/([a-z0-9-]+)/", pad)
        beeld = (f"/deelbeeld/{taal}/{'/'.join(eigen.groups())}.jpg?v=2026-11-13" if eigen else "/static/merk/og.jpg")
        assert p.meta("og:image") == f"{BASIS}{beeld}", (taal, pad)
        assert (p.meta("og:image:width"), p.meta("og:image:height")) == ("1200", "630")
        assert p.meta("twitter:card") == "summary_large_image"


def test_the_brand_files_come_from_the_site_itself(site):
    s, _ = site
    for pad, soort in [("/favicon.ico", "image/"), ("/static/merk/favicon.ico", "image/"),
                       ("/static/merk/logo.svg", "image/svg+xml"), ("/static/merk/apple-touch-icon.png", "image/png"),
                       ("/static/merk/og.jpg", "image/jpeg"), ("/static/velden.css", "text/css")]:
        with urllib.request.urlopen(f"http://127.0.0.1:{s.poort}{pad}", timeout=30) as r:
            assert r.status == 200 and r.headers["content-type"].startswith(soort), pad
            assert r.read() and "set-cookie" not in {k.lower() for k in r.headers}, pad


# --- 7. elke link in menu en voet werkt ---------------------------------------------------------------------------------

# de enige adressen buiten de site in de voet (PLAN #34.2bk, SPECS E9.S30): de maker, de twee licenties en, zodra het repo
# openbaar is, de broncode (AC3: tot dan geen link en niet het woord Open source)
OPENBAAR = re.search(r"const BRONCODE_OPENBAAR = (true|false);",
                     (websitebouw.WORTEL / "site" / "src" / "layouts" / "Site.astro").read_text(encoding="utf-8")).group(1) == "true"
BUITEN_VOET = frozenset({"https://ideelab.nl/", "https://www.gnu.org/licenses/agpl-3.0.html",
                         "https://creativecommons.org/licenses/by/4.0/"} | ({"https://github.com/factiz-org/factiz"} if OPENBAAR else set()))


def _menu_en_voet(p: Pagina) -> set[str]:
    """Elke link in de kop en de voet, en die van het menu en de taalkiezer, ook wat pas met script in beeld komt."""
    hrefs = {e["attrs"]["href"] for e in p.alle("a") if "href" in e["attrs"] and {"header", "footer"} & set(e["binnen"])}
    [menu] = p.eilanden("Menu")
    hrefs |= set(menu["links"].values()) | {f"{menu['links']['themas']}{th['waarde']}/" for th in menu["themas"]}
    [kiezer] = p.eilanden("Taalkiezer")
    hrefs |= {l["href"] for l in kiezer["talen"]}
    [palet] = p.eilanden("Zoekpalet")
    hrefs |= {palet["lijst"]}
    return hrefs


@pytest.mark.parametrize("taal", TALEN)
def test_every_link_in_menu_and_footer_works(site, taal):
    s, nr = site
    for pad in ("/", f"/fact-checks/{nr['villa']}/", "/fact-checks/?taal=en", "/bestaat-niet/"):
        _, _, tekst = s.haal(_pad(taal, pad))
        hrefs = _menu_en_voet(Pagina(tekst))
        assert _pad(taal, "/names/") in hrefs and _pad(taal, "/themes/war/") in hrefs, (taal, pad)
        assert _pad(taal, "/explore/") in hrefs, (taal, pad)                     # Verkennen in kop en voet (E9.S17 AC7)
        for href in hrefs - BUITEN_VOET:                                         # vier adressen buiten de site (E9.S30)
            assert _eigen(href), (taal, pad, href)
            assert s.haal(href)[0] == 200, (taal, pad, href)


@pytest.mark.parametrize("taal", i18n.TALEN)
def test_the_footer_names_the_maker_the_source_code_and_the_licences(site, taal):
    """De maker en open source in de voet (PLAN #34.2bk, SPECS E9.S30): Ideelab als maker, de broncode op GitHub, de code
    onder AGPL-3.0 en het protocol onder CC BY 4.0 met hun licentietekst, en dat elk gegeven bron en licentie noemt, met
    een link naar Bronnen en licenties; geen ander adres buiten de site, en niets dat de browser van daar laadt."""
    s, _ = site
    _, _, html = s.haal(_pad(taal, "/"))
    voet = html[html.index("<footer"):html.index("</footer>")]
    buiten = {h for h in re.findall(r'href="([^"]+)"', voet) if h.startswith("http")}
    assert buiten == set(BUITEN_VOET), (taal, buiten ^ set(BUITEN_VOET))
    assert re.search(r'<a href="https://ideelab.nl/"[^>]*>Ideelab</a>', voet) and "nofollow" not in voet
    assert ">AGPL-3.0</a>" in voet and ">CC BY 4.0</a>" in voet
    from html import unescape
    tekst = unescape(re.sub(r"<[^>]+>", "", voet))
    for sleutel in ("voet_code", "voet_protocol", "voet_licentie"):
        assert i18n.tekst(taal, sleutel) in tekst, (taal, sleutel)
    for sleutel in ("voet_open_source", "voet_broncode"):          # alleen met een openbaar repo (E9.S30 AC3)
        assert (i18n.tekst(taal, sleutel) in tekst) is OPENBAAR, (taal, sleutel)
    maker = i18n.tekst(taal, "voet_maker", maker="Ideelab")
    assert maker in tekst and "{maker}" in json.loads((websitebouw.WORTEL / "factiz_site" / "teksten" / f"{taal}.json")
                                                      .read_text(encoding="utf-8"))["teksten"]["voet_maker"], taal
    assert f'href="{_pad(taal, "/sources/")}"' in voet
    assert not re.search(r'<(script|img|link|iframe)[^>]+(src|href)="https?://', voet)
    for regel in ("voet_open_source", "voet_code", "voet_protocol", "voet_broncode", "voet_maker"):
        woord = i18n.tekst(taal, regel, maker="Ideelab")
        assert "!" not in woord and "—" not in woord, (taal, regel)


@pytest.mark.parametrize("taal", TALEN)
def test_explore_draws_the_ring_as_a_picture_and_every_part_ends_at_the_fact_checks(site, taal):
    """Verkennen (PLAN #34.2ah, SPECS E9.S17 AC1, AC2, AC6): de ring een plaatje dat een schermlezer overslaat, en elk
    thema, jaar en land een gewone link met zijn aantal."""
    s, _ = site
    for vraag in ("", "?thema=war"):
        p = _lees(s, _pad(taal, f"/explore/{vraag}"))
        g = s.api(f"/api/{taal}/verkennen{vraag}")
        ringen = [e for e in p.alle("svg") if "data-ring" in e["attrs"]]
        assert len(ringen) == 1 and ringen[0]["attrs"].get("aria-hidden") == "true", (taal, vraag)
        # in de ring zelf geen tabstop: de legenda is de weg voor toetsenbord en schermlezer
        assert all(e["attrs"].get("tabindex") == "-1" for e in p.alle("a") if "svg" in e["binnen"]), (taal, vraag)
        gewoon: dict[str, str] = {}
        for e in p.alle("a"):
            if "svg" not in e["binnen"] and "href" in e["attrs"]:
                gewoon[e["attrs"]["href"]] = gewoon.get(e["attrs"]["href"], "") + " " + p.tekst(e)
        for t in g["ring"]["themas"]:
            assert t["href"] in gewoon and t["aantal_tekst"].split()[0] in gewoon[t["href"]], (taal, vraag, t)
        for j in g["tijd"]["jaren"]:
            if j["aantal"]:
                assert j["href"] in gewoon, (taal, vraag, j)
        for r in g["waar"]["landen"]:
            assert r["href"] in gewoon and r["naam"] in gewoon[r["href"]], (taal, vraag, r)
        # de wereldkaart (SPECS E9.S20 AC3): een plaatje dat een schermlezer overslaat, en elk land als gewone link eronder
        [kaart] = [e for e in p.alle("svg") if "data-wereld" in e["attrs"]]
        assert kaart["attrs"].get("aria-hidden") == "true", (taal, vraag)
        for r in g["waar"]["kaart"]:
            assert r["href"] in gewoon and r["naam"] in gewoon[r["href"]], (taal, vraag, r)
        gekozen = [e for e in p.alle("a") if e["attrs"].get("aria-current") == "true" and "svg" not in e["binnen"]
                   and "header" not in e["binnen"]]
        if vraag:
            assert g["gekozen"]["lijst"] in gewoon
            assert [e["attrs"]["href"] for e in gekozen] == [_pad(taal, "/explore/?thema=war")], (taal, gekozen)
        else:
            assert [e["attrs"]["href"] for e in gekozen] == [_pad(taal, "/explore/")], (taal, gekozen)


@pytest.mark.parametrize("taal", TALEN)
def test_every_fact_check_offers_a_way_to_report_an_error_and_shows_the_address(site, taal):
    """Een fout melden (PLAN #34.2at, SPECS E9.S24): de link van het platform op de pagina, en het adres als tekst."""
    s, nr = site
    for sleutel in ("villa", "biolab", "arabisch"):
        m = s.api(f"/api/{taal}/factcheck/{nr[sleutel]}")["melden"]
        p = _lees(s, _pad(taal, f"/fact-checks/{nr[sleutel]}/"))
        links = [e for e in p.alle("a") if e["attrs"].get("href", "").startswith("mailto:")]
        assert [e["attrs"]["href"] for e in links if p.tekst(e) == m["tekst"]] == [m["href"]], (taal, sleutel)
        leesbaar = "".join(p.zichtbaar)
        assert m["adres"] in leesbaar and m["vraag"] in leesbaar and m["redactie"] in leesbaar, (taal, sleutel)


@pytest.mark.parametrize("taal", TALEN)
def test_a_fact_check_shares_its_own_image_and_the_site_serves_it(site, taal):
    """Het deelplaatje per factcheck (PLAN #34.2aq, SPECS E9.S23 AC5): `og:image` wijst naar het plaatje van de pagina met de
    versie van de uitgave, met de bewering en het label als beschrijving; de site geeft het als JPEG die een cache mag
    houden. Een andere pagina houdt het vaste beeld."""
    s, nr = site
    g = s.api(f"/api/{taal}/factcheck/{nr['villa']}")
    p = _lees(s, _pad(taal, f"/fact-checks/{nr['villa']}/"))
    assert p.meta("og:image") == f"{BASIS}/deelbeeld/{taal}/{nr['villa']}.jpg?v=2026-11-13"
    assert p.meta("og:image:alt") == g["deelbeeld"]["alt"] and g["label"] in g["deelbeeld"]["alt"]
    with urllib.request.urlopen(f"http://127.0.0.1:{s.poort}/deelbeeld/{taal}/{nr['villa']}.jpg", timeout=30) as r:
        assert r.status == 200 and r.headers["content-type"] == "image/jpeg" and "immutable" in r.headers["cache-control"]
        assert r.read()[:3] == b"\xff\xd8\xff"     # het begin van een JPEG
    assert s.haal(f"/deelbeeld/{taal}/0000000000000000.jpg")[0] == 404
    assert s.haal(f"/deelbeeld/{taal}/{nr['villa']}.png")[0] == 404
    assert _lees(s, _pad(taal, "/themes/")).meta("og:image") == f"{BASIS}/static/merk/og.jpg"
    # een thema, een onderdeel en een dossier hebben er ook een (AC6); de overzichten het vaste beeld
    for pad, beeld in (("/themes/war/", "thema/war"), ("/themes/war/ukraine/", "thema/war/ukraine"),
                       ("/dossiers/zelensky-luxury/", "dossier/zelensky-luxury")):
        assert _lees(s, _pad(taal, pad)).meta("og:image") == f"{BASIS}/deelbeeld/{taal}/{beeld}.jpg?v=2026-11-13", pad
        with urllib.request.urlopen(f"http://127.0.0.1:{s.poort}/deelbeeld/{taal}/{beeld}.jpg", timeout=30) as r:
            assert r.status == 200 and r.headers["content-type"] == "image/jpeg", beeld
    assert s.haal(f"/deelbeeld/{taal}/thema/astrologie.jpg")[0] == 404
    assert _lees(s, _pad(taal, "/dossiers/")).meta("og:image") == f"{BASIS}/static/merk/og.jpg"


@pytest.mark.parametrize("taal", TALEN)
def test_themes_and_dossiers_carry_their_drawing_hidden_from_screen_readers(site, taal):
    """Een tekening per thema en per dossier (PLAN #34.2ap, SPECS E9.S22): op de themakaarten, de dossierkaart en in de
    kop; verborgen voor een schermlezer, zonder woorden; geen eigen korrel, want die komt van het veld (PLAN #34.2bf);
    nooit bij de bewering."""
    s, nr = site
    for pad, minstens in (("/", 2), ("/themes/", 2), ("/themes/war/", 1), ("/dossiers/", 1), ("/dossiers/zelensky-luxury/", 1)):
        status, _, html = s.haal(_pad(taal, pad))
        assert status == 200, pad
        platen = re.findall(r'<span class="plaat[ "][^>]*>(.*?)</span>', html, re.S)
        assert len(platen) >= minstens, (taal, pad, len(platen))
        assert all('aria-hidden="true"' in m.group(0) for m in re.finditer(r'<span class="plaat[ "][^>]*>', html))
        assert all("<text" not in p for p in platen), pad
        assert "fz-korrel" not in html and "plaat-korrel" not in html and "feTurbulence" not in html, pad
    status, _, html = s.haal(_pad(taal, f"/fact-checks/{nr['villa']}/"))
    podium = html[html.index('class="podium'):html.index('id="antwoord"')]
    assert 'class="plaat' not in podium and "fz-korrel" not in html


def test_search_and_sort_stand_on_one_row_above_the_list_beside_the_filters(site):
    """Zoeken en sorteren op één rij boven de lijst (PLAN #34.2bg): het zoekveld van de lijst staat na het filterpaneel, in
    dezelfde rij als Sorteren op, en niet meer in de kop naast de titel."""
    s, _ = site
    for pad in ("/fact-checks/", "/themes/war/"):
        status, _, html = s.haal(pad)
        assert status == 200, pad
        paneel, veld = html.index('class="filterkolom'), html.index('id="bieb-q"')
        rij = html[html.rindex('data-rij="zoeken"', 0, veld):]
        assert paneel < veld, pad
        assert rij.index('id="bieb-q"') < rij.index("sorteer"), pad
        assert html.rindex('data-rij="zoeken"', 0, veld) > paneel, pad


def test_a_filter_heading_stands_free_of_the_line_between_groups_in_small_capitals():
    """De volgorde van de filters (PLAN #34.2bh): de kop van een groep (een legend) staat los van de rand, anders zet de
    browser hem in de lijn en wist hij die weg, met de lucht van de groep pas onder de kop; klein en in hoofdletters."""
    css = (websitebouw.SITE / "src" / "styles" / "site.css").read_text(encoding="utf-8")
    kop = re.search(r"\.fz \.filterkop \{([^}]*)\}", css).group(1)
    groep = re.search(r"\.fz \.filtergroep \{([^}]*)\}", css).group(1)
    assert "float: inline-start" in kop and "width: 100%" in kop and "text-transform: uppercase" in kop
    assert "border-top: 1px solid var(--lijn-sterk)" in groep
    assert re.search(r"\.fz \.filterkop \+ \* \{[^}]*clear: both", css)


def test_on_a_wide_screen_search_sort_and_filters_stay_while_the_list_scrolls_under_them():
    """Zoeken, sorteren en filters blijven staan (PLAN #34.2bj): vanaf md onder de kop van de site, het paneel met een eigen
    scroll; op een telefoon niets vast. Na een nieuwe lijst terug naar haar begin, alleen als dat boven uit beeld is."""
    css = (websitebouw.SITE / "src" / "styles" / "site.css").read_text(encoding="utf-8")
    assert re.search(r"--kop-hoogte:", css)
    breed = re.search(r"@media \(min-width: 48rem\) \{\s*(\.fz \[data-rij=\"zoeken\"\][^}]*\}\s*\.fz \.filterkolom[^}]*\})", css)
    assert breed, "geen vaste rij en vast paneel vanaf md"
    rij, paneel = breed.group(1).split(".fz .filterkolom")
    assert "position: sticky" in rij and "top: var(--kop-hoogte)" in rij and "background: var(--grond)" in rij
    for deel in ("position: sticky", "top: calc(var(--kop-hoogte)", "overflow-y: auto", "max-height: calc(100dvh",
                 "overscroll-behavior: contain"):
        assert deel in paneel, deel
    bieb = (websitebouw.SITE / "src" / "components" / "site" / "Bibliotheek.jsx").read_text(encoding="utf-8")
    naar = bieb[bieb.index("factiz:gefilterd") - 600:bieb.index("factiz:gefilterd") + 200]
    assert "getBoundingClientRect().top" in naar and "scrollTo(" in naar


def test_the_filter_panel_shows_no_scrollbar_until_pointed_at_and_fades_while_there_is_more():
    """Geen balk in beeld (PLAN #34.2bj, bijgesteld): onzichtbaar tot de muis op het paneel staat of de focus erin; een
    zachte vervaging onderaan alleen zolang er meer onder de rand zit (`data-meer`)."""
    css = (websitebouw.SITE / "src" / "styles" / "site.css").read_text(encoding="utf-8")
    assert re.search(r"\.fz \.filterkolom \{[^}]*scrollbar-color: transparent transparent", css)
    assert re.search(r"\.fz \.filterkolom:hover, \.fz \.filterkolom:focus-within \{[^}]*scrollbar-color: var\(--lijn-sterk\)", css)
    assert re.search(r"\.fz \.filterkolom\[data-meer\]::after \{[^}]*position: sticky[^}]*bottom: 0", css)
    bieb = (websitebouw.SITE / "src" / "components" / "site" / "Bibliotheek.jsx").read_text(encoding="utf-8")
    assert "toggleAttribute('data-meer'" in bieb and "ResizeObserver" in bieb


def test_the_filters_beside_the_list_stand_in_one_panel_with_the_border_of_the_cards(site):
    """De filters links in één paneel met dezelfde rand, hoek en achtergrond als de kaarten van de lijst (PLAN #34.2bf,
    DESIGNSYSTEEM §5): op de lijst en op een thema, zo hoog als de filters; op een telefoon de lade."""
    s, _ = site
    for pad in ("/fact-checks/", "/themes/war/"):
        status, _, html = s.haal(pad)
        assert status == 200, pad
        kolom = re.search(r'<aside class="([^"]*)" aria-label="[^"]*">', html)
        assert kolom and "filterkolom" in kolom.group(1) and "max-md:hidden" in kolom.group(1), pad
    css = (websitebouw.SITE / "src" / "styles" / "site.css").read_text(encoding="utf-8")
    regel = re.search(r"\.fz \.filterkolom \{([^}]*)\}", css)
    assert regel, "geen stijl voor de kolom met filters"
    for deel in ("background: var(--paneel)", "border: 1px solid var(--lijn)", "border-radius: var(--r-groot)",
                 "align-self: start"):
        assert deel in regel.group(1), deel


@pytest.mark.parametrize("taal", TALEN)
def test_the_context_cards_beside_a_fact_check_show_what_the_platform_counted(site, taal):
    """Contextkaarten (PLAN #34.2an, SPECS E9.S21): hoogstens vier, in de volgorde van het platform; elke kaart een kop met
    de vraag, de zin en de noot van het platform, alleen de links die het platform gaf, en een beeld dat een schermlezer
    overslaat. De bewering en het oordeel staan op een eigen vlak, nooit op een veld (D11)."""
    s, nr = site
    for sleutel in ("villa", "biolab", "spaans", "arabisch"):
        g = s.api(f"/api/{taal}/factcheck/{nr[sleutel]}")
        status, _, html = s.haal(_pad(taal, f"/fact-checks/{nr[sleutel]}/"))
        assert status == 200
        kaarten = re.findall(r'<section class="ck"([^>]*)>(.*?)</section>', html, re.S)
        assert len(kaarten) == len(g["context"]) <= 4, (taal, sleutel)
        for (attrs, binnen), k in zip(kaarten, g["context"]):
            assert f'data-soort="{k["soort"]}"' in attrs, (taal, sleutel, k["soort"])
            p = Pagina(binnen)
            [kop] = p.alle("h2")
            assert p.tekst(kop) == k["vraag"]
            leesbaar = " ".join("".join(p.zichtbaar).split())
            for veld in ("zin", "noot", "naam"):
                if k.get(veld):
                    assert " ".join(k[veld].split()) in leesbaar, (taal, sleutel, veld)
            assert all(e["attrs"].get("aria-hidden") == "true" for e in p.alle("svg"))
            verwacht = ({k["href"]} if k.get("href") else set()) | {r["href"] for r in k.get("rijen", [])} \
                | {n["href"] for n in k.get("namen", [])}
            assert {e["attrs"]["href"] for e in p.alle("a")} == verwacht, (taal, sleutel, k["soort"])
            if k["soort"] == "waar":
                assert 'class="aan"' in binnen      # het land op het kaartje, in de kleur van het thema
        podium = html[html.index('class="podium'):html.index('id="antwoord"')]
        assert "<h1" in podium and "kaartveld" not in podium, (taal, sleutel)
    soorten = [k["soort"] for k in s.api(f"/api/{taal}/factcheck/{nr['villa']}")["context"]]
    assert soorten[:2] == ["dossier", "waar"], soorten


def test_the_years_of_a_dossier_stand_under_a_baseline_and_not_between_the_bars(site):
    """PO 2026-11-24, bij de dossierkaart naast een factcheck: "Ik denk dat hier een lijntje onder moet komen, heel subtiel,
    en daaronder de jaartallen." Alle staafjes staan op één lijn; de jaartallen staan in een eigen rij eronder, met één
    vak per jaar, ook als dat vak leeg blijft, zodat elk jaartal onder zijn staafje staat."""
    s, nr = site
    [dossier] = [k for k in s.api(f"/api/en/factcheck/{nr['villa']}")["context"] if k["soort"] == "dossier"]
    assert len(dossier["jaren"]) > 1
    _, _, html = s.haal(_pad("en", f"/fact-checks/{nr['villa']}/"))
    kaart = re.search(r'<section class="ck"[^>]*data-soort="dossier"[^>]*>(.*?)</section>', html, re.S).group(1)
    staafjes, jaren = kaart.index('class="ck-staafjes"'), kaart.index('class="ck-jaren"')
    assert staafjes < jaren
    assert kaart.count('class="ck-staaf') - kaart.count('class="ck-staafjes"') == len(dossier["jaren"])
    vak = r'class="ck-j( aan)?"'
    assert not re.search(vak, kaart[staafjes:jaren])                     # geen jaartal tussen de staafjes
    assert len(re.findall(vak, kaart)) == len(dossier["jaren"])          # één vak per jaar
    assert re.search(r'<span class="ck-jaren" dir="ltr" aria-hidden="true">', kaart)
    css = (websitebouw.SITE / "src" / "styles" / "site.css").read_text(encoding="utf-8")
    regel = lambda klasse: re.search(r"\.fz \." + klasse + r" \{([^}]*)\}", css).group(1)
    assert "border-bottom: 1px solid var(--lijn-sterk)" in regel("ck-staafjes") and "align-items: flex-end" in regel("ck-staafjes")
    # PO 2026-11-24: "afstand van cijfers tot bovenkant mag korter op de grafiek". Grafiek en jaartallen staan samen in één
    # blok, zodat de tussenruimte van de kaart er niet tussen komt; in de staafjes en in de lijn over de jaren
    assert re.search(r'<span class="ck-grafiek">\s*<span class="ck-staafjes".*?<span class="ck-jaren"', kaart, re.S)
    bron = (websitebouw.SITE / "src" / "components" / "site" / "ContextKaarten.astro").read_text(encoding="utf-8")
    assert re.search(r'<span class="ck-grafiek">\s*<span class="ck-reeks".*?<span class="ck-as"', bron, re.S)
    assert "display: block" in regel("ck-grafiek")
    for klasse in ("ck-jaren", "ck-as"):
        assert re.search(r"margin-top: [1-4]px", regel(klasse)), klasse
    assert "border-bottom: 1px solid var(--lijn-sterk)" in regel("ck-reeks")


@pytest.mark.parametrize("taal", TALEN)
def test_the_name_network_is_a_hidden_picture_next_to_plain_links_in_alphabetical_order(site, taal):
    """Het netwerk van namen (PLAN #34.2ai, SPECS E9.S18 AC3, AC5): het plaatje voor een schermlezer verborgen en zonder
    tabstop, de namen ernaast als gewone links op alfabet, en een gekozen naam met zijn pagina en zijn lijst."""
    s, _ = site
    p = _lees(s, _pad(taal, "/explore/network/"))
    g = s.api(f"/api/{taal}/netwerk")
    [plaatje] = [e for e in p.alle("svg") if "data-netwerk" in e["attrs"]]
    assert plaatje["attrs"].get("aria-hidden") == "true"
    assert all(e["attrs"].get("tabindex") == "-1" for e in p.alle("a") if "svg" in e["binnen"])
    # zonder keuze zijn de enige links naar een naam in het netwerk die van de lijst naast het plaatje
    lijst = [e["attrs"]["href"] for e in p.alle("a")
             if "svg" not in e["binnen"] and e["attrs"].get("href", "").startswith(_pad(taal, "/explore/network/?naam="))]
    assert lijst == [n["href"] for n in g["namen"]]
    gekozen = _lees(s, _pad(taal, "/explore/network/?naam=Q3874799"))
    hrefs = {e["attrs"].get("href") for e in gekozen.alle("a")}
    assert _pad(taal, "/names/Q3874799/") in hrefs and _pad(taal, "/fact-checks/?naam=Q3874799") in hrefs
    # Verkennen en het register wijzen naar het netwerk (AC7)
    for pad in ("/explore/", "/names/"):
        assert _pad(taal, "/explore/network/") in {e["attrs"].get("href") for e in _lees(s, _pad(taal, pad)).alle("a")}, pad


def test_a_release_without_names_has_no_link_to_names_and_every_link_still_works(open_zonder_namen):
    s, _ = open_zonder_namen
    assert s.api("/api/nl/archief")["namen"] is False
    for taal in TALEN:
        p = _lees(s, _pad(taal, "/"))
        voet = {e["attrs"]["href"] for e in p.alle("a") if "footer" in e["binnen"]}
        assert _pad(taal, "/names/") not in voet, taal
        for href in voet - BUITEN_VOET:
            assert s.haal(href)[0] == 200, (taal, href)


# --- 8. vijandige tekst uit de database (E9.S4 AC3) ---------------------------------------------------------------------

@pytest.mark.parametrize("taal", TALEN)
def test_hostile_text_from_the_database_stays_plain_text(site, taal):
    s, nr = site
    for pad in (f"/fact-checks/{nr['vijandig']}/", "/fact-checks/", "/fact-checks/?p=2", "/names/Q99/",
                "/names/?letter=0&soort=organisatie", f"/fact-checks/{nr['villa']}/"):
        _, _, tekst = s.haal(_pad(taal, pad))
        _geen_element_uit_de_database(Pagina(tekst), (taal, pad))
        assert not any(teken in tekst for teken in WEG), (taal, pad)
    _, _, tekst = s.haal(_pad(taal, f"/fact-checks/{nr['vijandig']}/"))
    p = Pagina(tekst)
    [kop] = p.alle("h1")
    # wat de bezoeker leest: het script als tekst, de omgekeerde richting en het onzichtbare weg, het Perzisch heel
    assert p.tekst(kop) == '<script>alert(1)</script> "><img src=x onerror=alert(1)> omgekeerd verstopt می‌خواهم'
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in tekst
    # het oordeel van de redactie, met opmaak en al, ook als tekst
    assert any(p.tekst(e) == '“<b>False</b> "><script>x</script>”' for e in p.alle("span", lang="en"))
    # het blok voor zoekmachines breekt niet open en zegt hetzelfde
    [ld] = p.alle("script", type="application/ld+json")
    assert json.loads(p.tekst(ld))["mainEntity"]["text"] == p.tekst(kop)
    assert "</script" not in p.tekst(ld).lower()
    # een naam met opmaak blijft tekst, op haar pagina en in de lijst van de factcheck
    naam = Pagina(s.haal(_pad(taal, "/names/Q99/"))[2])
    assert naam.tekst(naam.alle("h1")[0]).strip() == VIJANDIGE_NAAM


def _geen_element_uit_de_database(p: Pagina, waar) -> None:
    """Wat uit de database komt, wordt nooit een element: geen script, geen beeld, geen vet. (In een attribuut tussen
    aanhalingstekens is een `<` gewone tekst; het telt hier dus niet, wel wat de browser als element leest.)"""
    for el in p.elementen:
        a = el["attrs"]
        assert not (el["tag"] == "img" and a.get("src") == "x"), waar
        assert not any(k.startswith("on") for k in a), waar
        assert not (el["tag"] == "b" and "False" in p.tekst(el)), waar
        if el["tag"] == "script" and a.get("type") == "application/ld+json":
            assert "</script" not in p.tekst(el).lower(), waar
            json.loads(p.tekst(el))
        elif el["tag"] == "script":
            assert "alert(" not in p.tekst(el), waar


@pytest.mark.parametrize("taal", TALEN)
def test_a_pasted_message_says_the_fact_checks_look_like_it(site, taal):
    """Zoeken op een geplakt bericht (PLAN #34.2au, SPECS E9.S6 AC5): de kop zegt dat de factchecks op het bericht lijken,
    met het aantal, en de uitleg noemt de woorden die telden; een gewone vraag houdt haar eigen kop."""
    s, nr = site
    bericht = ("Forwarded as received. Zelensky secretly bought a luxury villa in Florida with our money. "
               "Share this before they delete it.")
    _, _, html = s.haal(_pad(taal, "/fact-checks/"), {"q": bericht})
    g = json.loads(s.haal(f"/{taal}/api/zoek", {"q": bericht})[2])
    assert g["bericht"] is True and g["totaal"] >= 1 and g["rijen"][0]["nummer"] == nr["villa"]
    kop = Pagina(html).tekst(Pagina(html).alle("h1")[0])
    assert kop == g["bericht_kop"] and "data-bericht" in html, taal
    gewoon = json.loads(s.haal(f"/{taal}/api/zoek", {"q": "villa"})[2])
    assert gewoon["bericht"] is False


def test_search_works_from_the_address_of_the_site_and_is_refused_from_another_site(site):
    """Zoeken is een gepost formulier. Astro weigert een formulier van een andere site; zonder de adressen van de site in
    `security.allowedDomains` hield het elke bezoeker voor een andere site behalve op http://localhost (PLAN #34.2v)."""
    s, _ = site
    lokaal = f"localhost:{s.poort}"
    for pad in ("/fact-checks/", "/nl/fact-checks/", "/nl/api/zoek", "/nl/api/suggesties"):
        assert s.haal(pad, {"q": "villa"})[0] == 200, pad                                             # 127.0.0.1
        assert s.haal(pad, {"q": "villa"}, {"Host": lokaal, "Origin": f"http://{lokaal}"})[0] == 200, pad
        # straks achter de proxy op factiz.org
        assert s.haal(pad, {"q": "villa"}, {"Host": "factiz.org", "X-Forwarded-Proto": "https",
                                            "Origin": "https://factiz.org"})[0] == 200, pad
        assert s.haal(pad, {"q": "villa"}, {"Origin": "https://elders.example"})[0] == 403, pad
        assert s.haal(pad, {"q": "villa"}, {"Host": "elders.example", "Origin": "http://elders.example"})[0] == 403, pad


def test_a_hostile_search_stays_plain_text_and_keeps_no_trace_in_the_address(site):
    s, _ = site
    vraag = '<script>alert(1)</script>‮villa'
    status, _, tekst = s.haal("/nl/fact-checks/", {"q": vraag})
    p = Pagina(tekst)
    assert status == 200 and "&lt;script&gt;alert(1)&lt;/script&gt;" in tekst
    _geen_element_uit_de_database(p, "zoeken")
    # in het zoekveld blijft staan wat de bezoeker typte (34.2i); in de tekst van de pagina draait niets de richting om
    assert [e["attrs"]["value"] for e in p.alle("input", name="q")] == [vraag]
    assert not any(teken in "".join(p.zichtbaar) for teken in WEG)
    # de vraag staat in geen adres: niet in de links, niet bij delen
    assert p.meta("og:url") == f"{BASIS}/nl/fact-checks/"
    assert not any("alert" in e["attrs"].get("href", "") for e in p.elementen)


# --- 9. een link naar buiten geeft niets door -------------------------------------------------------------------------

@pytest.mark.parametrize("taal", TALEN)
def test_every_link_to_another_host_carries_noopener(site, taal):
    s, nr = site
    gezien = 0
    for pad in _alle_paden(s, nr):
        for el in _lees(s, _pad(taal, pad)).alle("a"):
            href = el["attrs"].get("href", "")
            if href.startswith(("http:", "https:", "//")):
                gezien += 1
                assert "noopener" in el["attrs"].get("rel", "").split(), (taal, pad, href)
    assert gezien >= 5, taal       # snopes, afp, maldita, euvsdisinfo, de BBC en de bronnen


# --- 10. de 404 in de taal van het adres (E9.S4 AC6) --------------------------------------------------------------------

@pytest.mark.parametrize("taal", TALEN)
def test_an_unknown_address_gives_a_page_not_found_in_the_language_of_the_address(site, taal):
    s, _ = site
    for pad in NIET_GEVONDEN:
        status, koppen, tekst = s.haal(_pad(taal, pad))
        assert status == 404 and koppen["content-type"].startswith("text/html"), (taal, pad, status)
        p = Pagina(tekst)
        assert _html(p) == {"lang": taal, "dir": "ltr"}, (taal, pad)
        [kop] = p.alle("h1")
        assert p.tekst(kop) == i18n.tekst(taal, "fout_titel"), (taal, pad)
        terug = [e for e in p.alle("a", href=_pad(taal, "/")) if "main" in e["binnen"]]
        assert [p.tekst(e) for e in terug] == [i18n.tekst(taal, "fout_terug")], (taal, pad)
        assert p.meta("robots") == "noindex, nofollow" and p.links("canonical") == [] and p.hreflang() == {}, (taal, pad)
        # geen technische details: de pagina van de site, niet die van Astro, en niets over de server
        [hoofd] = p.alle("main")
        zichtbaar = "".join(p.tekst(hoofd).split())
        assert zichtbaar == "".join("".join(i18n.tekst(taal, f"fout_{k}") for k in ("titel", "tekst", "terug")).split()), \
            (taal, pad, p.tekst(hoofd))
        assert "404: Not Found" not in tekst and "127.0.0.1" not in tekst, (taal, pad)


def test_an_unknown_language_is_an_english_page_not_found(site):
    s, _ = site
    status, _, tekst = s.haal("/xx/fact-checks/")
    assert status == 404 and _html(Pagina(tekst))["lang"] == "en"


# --- 34.2ad: geen <style>-element uit een pakket; de schermvergrendeling via een stylesheet uit het eigen script ---------

def test_no_package_writes_a_style_element_that_the_policy_would_refuse():
    """Radix zet de pagina achter een venster vast met opmaak van `react-style-singleton`. Dat pakket maakt er een
    `<style>`-element voor, en dat weigert de opmaakregel (B75). De bouw wijst het pakket naar eigen code die een
    stylesheet uit het script bouwt (`adoptedStyleSheets`); de regel zelf blijft gelijk."""
    websitebouw.site()
    stukken = {f.name: f.read_text(encoding="utf-8") for f in (websitebouw.SITE / "dist" / "client" / "_astro").glob("*.js")}
    assert stukken
    # de code van het pakket: een element met type text/css
    assert not [naam for naam, code in stukken.items() if "text/css" in code], "een <style>-element uit een pakket"
    assert any("adoptedStyleSheets" in code for code in stukken.values())


# --- 34.2bi: de volgorde van de talen ------------------------------------------------------------------------------------

VASTE_VOLGORDE = ["ar", "de", "en", "es", "fa", "fr", "hi", "id", "ja", "nl", "pt-BR", "ru", "tr", "uk", "zh-Hant"]


def test_the_languages_stand_in_one_fixed_order_on_every_page_in_picker_and_footer(site):
    """De volgorde van de talen (PLAN #34.2bi): op de code, AR tot ZH, zoals het W3C (PO: "Op code"); op elke pagina
    dezelfde, in de kiezer en in de voet."""
    s, _ = site
    for pad in ("/nl/", "/ja/", "/ar/fact-checks/"):
        status, _, html = s.haal(pad)
        assert status == 200, pad
        kiezer = re.search(r'<nav[^>]*id="taalkiezer".*?</nav>', html, re.S).group(0)
        assert re.findall(r'hrefLang="([^"]+)"', kiezer) == VASTE_VOLGORDE, pad
        voet = re.search(r'<div id="talen">.*?</ul>', html, re.S).group(0)
        assert re.findall(r'(?<!href)lang="([^"]+)"', voet) == VASTE_VOLGORDE, pad


def _voorstel(tags, huidig, max_=3):
    code = ("import { voorstel } from './site/src/lib/taalvoorstel.js';"
            f"console.log(JSON.stringify(voorstel({json.dumps(tags)}, {json.dumps(list(i18n.TALEN))}, {json.dumps(huidig)}, {max_})));")
    uit = subprocess.run(["node", "--input-type=module", "-e", code], cwd=websitebouw.WORTEL, capture_output=True, text=True,
                         check=True)
    return json.loads(uit.stdout)


def test_the_suggested_languages_come_from_the_browser_mapped_to_the_site_without_the_current_one():
    """Voorgesteld (PLAN #34.2bi): de talen die de browser noemt, omgezet naar een taal van de site, zonder de huidige en
    zonder dubbele, hoogstens drie; een taal die de site niet heeft valt weg."""
    assert _voorstel(["de-AT", "de", "en-US", "pt-PT", "zh-CN"], "nl") == ["de", "en", "pt"]
    assert _voorstel(["nl-NL", "nl", "en"], "nl") == ["en"]
    assert _voorstel(["zh-CN", "sv", "ja"], "en") == ["zh", "ja"]
    assert _voorstel(["sv-SE", "pl"], "en") == []
    assert _voorstel(["fa-IR", "ar", "tr", "ru", "uk"], "en", 3) == ["fa", "ar", "tr"]
    assert _voorstel([], "en") == []


def test_the_picker_reads_the_browser_languages_after_loading_and_keeps_nothing():
    """Het voorstel komt uit de browser zelf, na het laden (zodat de pagina van de server gelijk blijft), en gaat nergens
    heen (B78): geen opslag, geen cookie, geen verzoek. De twee kopjes staan in elke woordenlijst."""
    bron = (websitebouw.SITE / "src" / "components" / "site" / "Taalkiezer.jsx").read_text(encoding="utf-8")
    effect = bron[bron.index("useEffect(() => {"):]
    assert "navigator.languages" in effect[:effect.index("}, [")]
    assert "voorstel(" in bron and ".sort(" not in bron
    for verboden in ("localStorage", "sessionStorage", "document.cookie", "fetch("):
        assert verboden not in bron, verboden
    for taal in i18n.TALEN:
        for sleutel in ("taal_voorgesteld", "taal_alle"):
            woord = i18n.tekst(taal, sleutel)
            assert woord and "!" not in woord and "—" not in woord, (taal, sleutel)


# --- 34.2af: de taalkeuze als in het voorbeeld van de PO ---------------------------------------------------------------

def test_the_language_picker_shows_the_code_then_the_name_in_its_own_language(site):
    s, _ = site
    _, _, tekst = s.haal("/nl/")
    eigen = {"en": "English", "nl": "Nederlands", "de": "Deutsch", "es": "Español", "fr": "Français"}
    for code, naam in eigen.items():
        m = re.search(r'<a[^>]*class="fz-keuze"[^>]*hrefLang="' + code + r'"[^>]*>(.*?)</a>', tekst, re.S | re.I)
        assert m, code
        binnen = m.group(1)
        assert re.search(r'<span[^>]*class="code"[^>]*aria-hidden="true"[^>]*>' + code.upper() + "</span>", binnen), binnen
        assert naam in binnen and binnen.index(code.upper()) < binnen.index(naam)
    # de naam in de taal van de pagina staat er niet meer onder: de code en het zoekveld dekken het
    assert "Duits" not in re.search(r'<nav[^>]*id="taalkiezer".*?</nav>', tekst, re.S).group(0)


# --- de ronde na de doorloop van factiz.org (PLAN #34.2bq, punten 1 tot 9) ------------------------------------------------

def _methode(s, pad: str, methode: str):
    verzoek = urllib.request.Request(f"http://127.0.0.1:{s.poort}{pad}", method=methode)
    try:
        with urllib.request.build_opener(_Blijf).open(verzoek, timeout=30) as r:
            return r.status, {k.lower(): v for k, v in r.headers.items()}, r.read().decode("utf-8")
    except urllib.error.HTTPError as fout:
        return fout.code, {k.lower(): v for k, v in fout.headers.items()}, fout.read().decode("utf-8", "replace")


def test_the_site_only_reads_and_searches_every_other_method_gets_405(site):
    s, nr = site
    for pad in ("/", f"/fact-checks/{nr['villa']}/", "/nl/dossiers/"):
        for methode in ("PUT", "DELETE", "PATCH", "OPTIONS"):
            status, koppen, _ = _methode(s, pad, methode)
            assert status == 405 and koppen["allow"] == "GET, HEAD, POST", (pad, methode, status)
            assert koppen["x-content-type-options"] == "nosniff"
    assert _methode(s, "/about/", "HEAD")[0] == 200


def test_every_page_says_utf8_in_its_header_and_security_txt_names_the_contact(site):
    s, _ = site
    for pad in ("/", "/nl/fact-checks/", "/de/themes/"):
        assert s.haal(pad)[1]["content-type"] == "text/html; charset=utf-8", pad
    status, koppen, tekst = s.haal("/.well-known/security.txt")
    assert status == 200 and koppen["content-type"] == "text/plain; charset=utf-8"
    assert "Contact: mailto:info@factiz.org" in tekst and "Expires: " in tekst


@pytest.mark.parametrize("taal", TALEN)
def test_the_first_thing_a_keyboard_reaches_is_the_link_to_the_content(site, taal):
    """WCAG 2.4.1: de eerste link van elke pagina springt naar de inhoud, in de taal van de pagina."""
    s, nr = site
    tekst = i18n.teksten(taal)["naar_inhoud"]
    for pad in ("/", "/fact-checks/", f"/fact-checks/{nr['villa']}/", "/dossiers/zelensky-luxury/"):
        p = _lees(s, _pad(taal, pad))
        eerste = next(e for e in p.elementen if e["tag"] == "a" and "body" in e["binnen"])
        assert eerste["attrs"].get("href") == "#main" and "naar-inhoud" in eerste["attrs"].get("class", ""), (taal, pad)
        assert p.tekst(eerste) == tekst
        assert [m["attrs"].get("id") for m in p.alle("main")] == ["main"], (taal, pad)


@pytest.mark.parametrize("taal", TALEN)
def test_every_description_fits_the_160_characters_a_search_engine_shows(site, taal):
    s, nr = site
    for pad in _alle_paden(s, nr):
        p = _lees(s, _pad(taal, pad))
        for sleutel in ("description", "og:description"):
            waarde = p.meta(sleutel)
            assert waarde and len(waarde) <= 160, (taal, pad, sleutel, waarde)


@pytest.mark.parametrize("taal", TALEN)
def test_the_start_tells_search_engines_the_site_and_who_makes_it(site, taal):
    s, _ = site
    p = _lees(s, _pad(taal, "/"))
    [ld] = [json.loads(p.tekst(e)) for e in p.alle("script", type="application/ld+json")]
    knopen = {k["@type"]: k for k in ld["@graph"]}
    site_, org = knopen["WebSite"], knopen["Organization"]
    assert site_["name"] == "Factiz" and site_["@id"] == f"{BASIS}/#site" and site_["url"] == BASIS + _pad(taal, "/")
    assert site_["publisher"]["@id"] == org["@id"] == f"{BASIS}/#factiz"
    assert org["logo"]["url"].startswith(f"{BASIS}/static/")
    # de kernzin (docs/voorstellen/2026-11-20-seo-geo.md): wat Factiz is, met de getallen, in de taal van de pagina
    assert org["description"] == site_["description"] and any(ch.isdigit() for ch in org["description"])
    assert "potentialAction" not in site_          # een zoekvraag staat nooit in een adres (B78)


@pytest.mark.parametrize("taal", TALEN)
def test_the_question_page_answers_whether_a_global_fact_check_database_exists(site, taal):
    # SEO en GEO (2026-11-20): de vraag die mensen en AI-machines stellen, met zes vragen en antwoorden als FAQPage en het
    # archief als Dataset; in de voet van elke pagina
    s, _ = site
    p = _lees(s, _pad(taal, "/global-fact-check-database/"))
    [ld] = [json.loads(p.tekst(e)) for e in p.alle("script", type="application/ld+json")]
    knopen = {k["@type"]: k for k in ld["@graph"]}
    assert len(knopen["FAQPage"]["mainEntity"]) == 6
    assert all(v["name"] and v["acceptedAnswer"]["text"] for v in knopen["FAQPage"]["mainEntity"])
    # de maker voluit, met soort en naam: Google volgt een kale verwijzing naar de startpagina niet ("Ongeldig objecttype voor
    # veld 'creator'", Search Console 2026-11-21)
    maker = knopen["Dataset"]["creator"]
    assert maker == {"@type": "Organization", "@id": f"{BASIS}/#factiz", "name": "Factiz", "url": f"{BASIS}/"}
    assert knopen["Dataset"]["isAccessibleForFree"]
    start = _lees(s, _pad(taal, "/"))
    assert any(a["attrs"].get("href") == _pad(taal, "/global-fact-check-database/") for a in start.alle("a"))


@pytest.mark.parametrize("taal", TALEN)
def test_a_dossier_tells_search_engines_which_fact_checks_it_collects(site, taal):
    s, _ = site
    pad = _pad(taal, "/dossiers/zelensky-luxury/")
    p = _lees(s, pad)
    [ld] = [json.loads(p.tekst(e)) for e in p.alle("script", type="application/ld+json")]
    assert ld["@type"] == "CollectionPage" and ld["url"] == BASIS + pad
    lijst = ld["mainEntity"]
    assert lijst["@type"] == "ItemList" and lijst["numberOfItems"] == len(lijst["itemListElement"]) >= 1
    for i, item in enumerate(lijst["itemListElement"], 1):
        assert item["position"] == i and item["url"].startswith(BASIS) and "/fact-checks/" in item["url"]
        # elke factcheck in de lijst staat ook op de pagina zelf
        assert any(a["attrs"].get("href") == item["url"][len(BASIS):] for a in p.alle("a")), item


@pytest.mark.parametrize("taal", TALEN)
def test_a_fact_check_title_starts_with_the_verdict_and_the_bare_claim_stays_out_of_snippets(site, taal):
    """PLAN #34.2bw, SPECS E9.S8 AC8: de titel en de deeltitel beginnen met het oordeel, de bewering hoogstens 45 tekens; de
    kale bewering (de kop, het origineel, de bewering in een rij) draagt data-nosnippet."""
    s, nr = site
    for n in nr.values():
        p = _lees(s, _pad(taal, f"/fact-checks/{n}/"))
        # sinds 2026-11-19 het stempel met wie het zegt (PLAN #34.2cc); hier hoogstens twee redacties, dus allebei
        g = s.api(f"/api/{taal}/factcheck/{n}")
        label = f'{g["stempel"]} {g["volgens"]}'.strip()
        [titel] = p.alle("title")
        assert p.tekst(titel).startswith(label) and p.meta("og:title").startswith(label), (taal, n)
        assert p.meta("description").startswith(label), (taal, n)
        bewering = p.tekst(titel)[len(label):].rsplit(" · Factiz", 1)[0]
        assert len(bewering) <= 47 + 4, (taal, n, bewering)          # 45, ' …' als ze afgekapt is, en de aanhalingstekens
        [kop] = p.alle("h1")
        assert "data-nosnippet" in kop["attrs"], (taal, n)
    lijst = _lees(s, _pad(taal, "/fact-checks/"))
    rijen = [e for e in lijst.elementen if "rij-bewering" in e["attrs"].get("class", "")]
    assert rijen and all("data-nosnippet" in e["attrs"] for e in rijen)


@pytest.mark.parametrize("taal", TALEN)
def test_the_start_counts_the_same_fact_checks_in_the_heading_and_under_the_search_field(site, taal):
    """PO 2026-11-19: "in de kop staat 106.332 factchecks en eronder 109.128 factchecks van 255 redacties. Hoe zit dat?"; de
    kop telde de pagina's en de regel eronder elke check van een redactie. Nu tellen beide de pagina's ("Ja, één getal")."""
    import re
    s, _ = site
    tekst = " ".join(" ".join(_lees(s, _pad(taal, "/")).zichtbaar).split()).replace("\u202f", " ").replace("\u00a0", " ")
    woorden = i18n.teksten(taal)
    getal = r"([0-9][0-9 .,'\u066c\u060c]*[0-9]|[0-9])"
    kop = re.search(re.escape(woorden["held_label"]).replace(re.escape("{n}"), getal), tekst)
    regel = re.search(re.escape(woorden["start_tellingen"]).replace(re.escape("{checks}"), getal)
                      .replace(re.escape("{redacties}"), getal), tekst)
    assert kop and regel, (taal, tekst[:300])
    assert kop.group(1) == regel.group(1), (taal, kop.group(0), regel.group(0))


@pytest.mark.parametrize("taal", TALEN)
def test_the_start_shows_the_dossiers_without_explaining_them_and_the_overview_explains_them(site, taal):
    """PO 2026-11-16: "teveel uitleg voor subkop, de uitleg moet dieper op de site, niet hier"; 2026-11-23 ook de korte regel
    onder Dossiers op de start doorgestreept."""
    s, _ = site
    tekst = lambda pad: " ".join(" ".join(_lees(s, _pad(taal, pad)).zichtbaar).split())
    uitleg = i18n.teksten(taal)["dossiers_inleiding"]
    assert uitleg not in tekst("/") and "start_dossiers" not in i18n.teksten(taal)
    assert uitleg in tekst("/dossiers/")



# --- de stappen naar zoekmachines (PLAN #34.2bt, SPECS E9.S8 AC3 tot AC7) ------------------------------------------------

INDEXNOW = "34e72c3d34148a19b8beeb1a44fad523"
SITEMAP_NS = "{http://www.sitemaps.org/schemas/sitemap/0.9}"


def test_while_closed_there_is_no_sitemap_no_llms_txt_and_no_key_file(site):
    s, _ = site
    for pad in ("/sitemap.xml", "/sitemaps/en-vast.xml", "/sitemaps/nl-factchecks-1.xml", "/llms.txt", f"/{INDEXNOW}.txt"):
        assert s.haal(pad)[0] == 404, pad


def test_in_step_one_only_the_core_is_findable_once_in_the_language_of_its_claim(stap_een):
    """B73 punt 5: de villa (twee redacties, in het dossier) en de jacht (in het dossier); de Arabische bewering en de
    biolabs (één redactie, geen dossier) nog niet."""
    s, nr = stap_een
    for pad in (f"/fact-checks/{nr['villa']}/", f"/es/fact-checks/{nr['spaans']}/",
                "/nl/", "/nl/about/", "/nl/themes/war/", "/nl/dossiers/zelensky-luxury/", "/nl/names/"):
        assert _lees(s, pad).meta("robots") == "index, follow", pad
    for pad in (f"/nl/fact-checks/{nr['villa']}/", f"/fact-checks/{nr['spaans']}/", f"/ar/fact-checks/{nr['arabisch']}/",
                f"/fact-checks/{nr['arabisch']}/", f"/fact-checks/{nr['biolab']}/"):
        p = _lees(s, pad)
        assert p.meta("robots") == "noindex, follow" and not p.links("canonical"), pad
    p = _lees(s, f"/fact-checks/{nr['villa']}/")
    assert p.hreflang() == {"en": f"{BASIS}/fact-checks/{nr['villa']}/", "x-default": f"{BASIS}/fact-checks/{nr['villa']}/"}


def test_in_step_two_every_fact_check_is_findable_once(stap_twee):
    s, nr = stap_twee
    for pad in (f"/fact-checks/{nr['villa']}/", f"/ar/fact-checks/{nr['arabisch']}/", f"/fact-checks/{nr['biolab']}/"):
        assert _lees(s, pad).meta("robots") == "index, follow", pad
    # de Nederlandse vertaling van de villa wacht op de derde stap (test_after_the_launch_...)
    for pad in (f"/nl/fact-checks/{nr['villa']}/", f"/fact-checks/{nr['arabisch']}/"):
        assert _lees(s, pad).meta("robots") == "noindex, follow", pad


def _sitemaps(s) -> dict[str, list[dict]]:
    """{adres van een sitemap: [{loc, lastmod}]}, via de index; elke sitemap geldig en binnen de grenzen."""
    import xml.etree.ElementTree as ET
    status, koppen, tekst = s.haal("/sitemap.xml")
    assert status == 200 and koppen["content-type"] == "application/xml; charset=utf-8"
    index = ET.fromstring(tekst)
    assert index.tag == f"{SITEMAP_NS}sitemapindex"
    uit = {}
    for kaart in index.findall(f"{SITEMAP_NS}sitemap"):
        loc = kaart.find(f"{SITEMAP_NS}loc").text
        assert loc.startswith(f"{BASIS}/sitemaps/") and loc.endswith(".xml"), loc
        status, koppen, tekst = s.haal(loc[len(BASIS):])
        assert status == 200 and koppen["content-type"] == "application/xml; charset=utf-8", loc
        assert len(tekst.encode()) < 50 * 1024 * 1024
        urls = ET.fromstring(tekst)
        assert urls.tag == f"{SITEMAP_NS}urlset"
        regels = [{"loc": u.find(f"{SITEMAP_NS}loc").text,
                   "lastmod": getattr(u.find(f"{SITEMAP_NS}lastmod"), "text", None)} for u in urls.findall(f"{SITEMAP_NS}url")]
        assert 1 <= len(regels) <= 50000, loc
        uit[loc] = regels
    return uit


@pytest.mark.parametrize("stand", ["stap_een", "stap_twee", "stap_drie"])
def test_every_address_in_the_sitemaps_is_findable_and_every_findable_page_is_in_them(request, stand):
    s, nr = request.getfixturevalue(stand)
    kaarten = _sitemaps(s)
    # per taal de vaste pagina's en de factchecks, elk in zijn eigen bestand
    for taal in i18n.TALEN:
        assert f"{BASIS}/sitemaps/{taal}-vast.xml" in kaarten, taal
    adressen = [r["loc"] for regels in kaarten.values() for r in regels]
    assert len(adressen) == len(set(adressen))
    for regels in kaarten.values():
        for r in regels:
            assert r["lastmod"] is None or re.fullmatch(r"\d{4}-\d\d-\d\d", r["lastmod"]), r
    for adres in adressen:
        p = _lees(s, adres[len(BASIS):])
        assert p.meta("robots") == "index, follow", adres
        assert [c["href"] for c in p.links("canonical")] == [adres], adres
    # en andersom: wat index zegt, staat erin (een volgend blad van een lijst niet)
    gezien = set(adressen)
    for taal in i18n.TALEN:
        for pad in _alle_paden(s, nr):
            adres = BASIS + _pad(taal, pad)
            if _lees(s, _pad(taal, pad)).meta("robots") == "index, follow" and "?p=" not in pad:
                assert adres in gezien, (stand, adres)
    # de factchecks staan met de datum van hun nieuwste check
    villa = next(r for regels in kaarten.values() for r in regels if r["loc"] == f"{BASIS}/fact-checks/{nr['villa']}/")
    assert villa["lastmod"] == "2024-03-05"
    assert (f"{BASIS}/nl/fact-checks/{nr['villa']}/" in gezien) is (stand == "stap_drie")
    assert (f"{BASIS}/fact-checks/{nr['biolab']}/" in gezien) is (stand != "stap_een")


def _mag(regels: str, pad: str) -> bool:
    """Zoals Google robots.txt leest (RFC 9309): de langste regel die past wint, bij gelijke lengte Allow."""
    beste = (-1, True)
    for regel in regels.splitlines():
        soort, _, patroon = regel.partition(":")
        patroon = patroon.strip()
        if soort.strip().lower() not in ("allow", "disallow") or not patroon:
            continue
        uitdr = "^" + re.escape(patroon).replace(r"\*", ".*").replace(r"\$", "$")
        if re.match(uitdr, pad):
            kandidaat = (len(patroon), soort.strip().lower() == "allow")
            if kandidaat > beste:
                beste = kandidaat
    return beste[1]


def test_robots_opens_for_every_crawler_and_closes_only_internal_paths_and_filtered_lists(stap_een):
    s, nr = stap_een
    status, koppen, tekst = s.haal("/robots.txt")
    assert status == 200 and koppen["content-type"] == "text/plain; charset=utf-8"
    assert tekst.splitlines()[0] == "User-agent: *" and tekst.count("User-agent:") == 1     # elke crawler, ook voor AI
    assert f"Sitemap: {BASIS}/sitemap.xml" in tekst.splitlines()
    open_ = ["/", "/nl/", f"/fact-checks/{nr['villa']}/", "/fact-checks/?p=2", "/nl/themes/war/?p=2",
             "/names/?letter=0&soort=organisatie", "/nl/names/?letter=a&soort=persoon", f"/deelbeeld/en/{nr['villa']}.jpg?v=x",
             "/static/velden.css?v=abc", "/_astro/site.css", "/sitemap.xml", "/sitemaps/en-vast.xml", "/llms.txt",
             f"/{INDEXNOW}.txt"]
    dicht = ["/api/en/archief", "/_geheugen/x", "/_deelbeeld/x", "/fact-checks/?taal=en", "/fact-checks/?taal=en&p=2",
             "/nl/fact-checks/?sorteer=oud", "/explore/?thema=war", "/names/?soort=persoon"]
    for pad in open_:
        assert _mag(tekst, pad), pad
    for pad in dicht:
        assert not _mag(tekst, pad), pad


def test_llms_txt_says_what_factiz_is_and_links_only_to_findable_pages(stap_een):
    s, _ = stap_een
    status, koppen, tekst = s.haal("/llms.txt")
    assert status == 200 and koppen["content-type"] == "text/plain; charset=utf-8"
    assert tekst.startswith("# Factiz\n\n> ")
    # sinds de eigen checks (B82, B84) niet meer "geen eigen oordeel": in het archief het oordeel van de redactie, en Factiz
    # Radar als eigen checks; de vraag of er een wereldwijde database is, beantwoord (2026-11-20)
    assert "no verdict of its own" not in tekst and "the verdict of the newsroom that checked the claim" in tekst
    assert "Factiz Radar" in tekst and "global fact-check database" in tekst and "info@factiz.org" in tekst
    links = re.findall(r"\]\((https://factiz\.org[^)]*)\)", tekst)
    assert len(links) >= 8
    for link in links:
        pad = link[len(BASIS):]
        if pad.endswith(".xml"):
            assert s.haal(pad)[0] == 200, link
        else:
            assert _lees(s, pad).meta("robots") == "index, follow", link


def test_the_indexnow_key_file_names_the_key(stap_een):
    s, _ = stap_een
    status, koppen, tekst = s.haal(f"/{INDEXNOW}.txt")
    assert status == 200 and tekst == INDEXNOW and koppen["content-type"] == "text/plain; charset=utf-8"
    assert s.haal("/0000000000000000000000000000000.txt")[0] == 404
    from doublecheck import indexnow
    assert indexnow.SLEUTEL == INDEXNOW


@pytest.mark.parametrize("taal", ("en", "ar"))
def test_every_page_lines_up_with_the_navigation_in_one_container(site, taal):
    """PO 2026-11-17: "check even of alle pagina netjes uitlijnen met de navigatie en dezelfde breedte hebben": één baan
    (`.baan`, 80rem) voor de kop, de voet en elke pagina; tekst houdt daarbinnen haar eigen leesbreedte."""
    css = (websitebouw.WORTEL / "site" / "src" / "styles" / "site.css").read_text(encoding="utf-8")
    assert re.findall(r"\.fz \.([a-z-]+) \{ max-width: \d+rem; margin-inline: auto;", css) == ["baan"]
    s, nr = site
    for pad in _vaste_paden() + [f"/fact-checks/{nr['villa']}/", "/bestaat-niet/"]:
        status, _, tekst = s.haal(_pad(taal, pad))
        p = Pagina(tekst)
        in_main = [e for e in p.elementen if "main" in e["binnen"] and "class" in e["attrs"]]
        assert in_main and "baan" in in_main[0]["attrs"]["class"].split(), (taal, pad)
        assert not any("leesbaan" in e["attrs"].get("class", "") for e in p.elementen), (taal, pad)



@pytest.mark.parametrize("stand", ["stap_een", "stap_drie"])
def test_a_name_page_stays_out_of_search_engines_until_a_lawyer_has_seen_it(request, stand):
    """PLAN #34.2bw, SPECS E9.S8 AC9: een pagina per naam is een profiel zoals bij een zoekmachine, het zwakste punt van de
    journalistieke uitzondering; noindex en niet in de sitemap, wel te lezen (anders ziet een crawler de noindex niet). Het
    register met letters blijft vindbaar."""
    s, _ = request.getfixturevalue(stand)
    for taal in ("en", "nl", "ar"):
        p = _lees(s, _pad(taal, "/names/Q3874799/"))
        assert p.meta("robots") == "noindex, follow" and not p.links("canonical"), taal
        assert _lees(s, _pad(taal, "/names/")).meta("robots") == "index, follow", taal
    robots = s.haal("/robots.txt")[2]
    assert _mag(robots, "/names/Q3874799/") and _mag(robots, "/nl/names/Q3874799/")
    adressen = [r["loc"] for regels in _sitemaps(s).values() for r in regels]
    assert not any(re.search(r"/names/Q\d+/$", a) for a in adressen)


@pytest.mark.parametrize("taal", ("en", "nl", "de", "ru", "ar", "zh"))
def test_the_footer_says_the_day_of_the_edition_and_of_the_latest_fact_check_out_of_search_snippets(site, taal):
    """PLAN #34.2bz (PO 2026-11-17: "Zullen we een versienummer met datum in de footer zetten zodat we zien tot wanneer de
    pagina up to date is?"): op elke pagina, in de regel onder de voet; `data-nosnippet`, want een datum die op elke pagina
    gelijk is, mag een zoekmachine niet voor de datum van een factcheck houden."""
    import html as htmllib
    s, nr = site
    verwacht = i18n.tekst(taal, "voet_actueel", uitgave=i18n.datum(taal, "2026-11-13"), factcheck=i18n.datum(taal, "2024-03-05"))
    assert s.api(f"/api/{taal}/archief")["actueel"]["factcheck"] == "2024-03-05"
    for pad in ("/", f"/fact-checks/{nr['villa']}/", "/about/"):
        _, _, tekst = s.haal(_pad(taal, pad))
        m = re.search(r'<p class="voet-actueel" data-nosnippet[^>]*>(.*?)</p>', tekst, re.S)
        assert m and htmllib.unescape(re.sub(r"<[^>]+>", "", m.group(1))).strip() == verwacht, (taal, pad)


def test_the_fixed_pages_carry_the_day_of_the_edition_only_where_an_edition_changes_them(stap_een):
    """`lastmod` alleen waar het klopt (PLAN #34.2bz): de start, de lijst, de thema's, de redacties, de bronnen en Verkennen
    tellen mee met elke uitgave; Over, Platform, de dossiers en het register van namen niet, die krijgen er geen."""
    s, _ = stap_een
    vast = {r["loc"][len(BASIS):]: r["lastmod"] for r in _sitemaps(s)[f"{BASIS}/sitemaps/en-vast.xml"]}
    for pad in ("/", "/fact-checks/", "/themes/", "/newsrooms/", "/sources/", "/explore/", "/explore/network/"):
        assert vast[pad] == "2026-11-13", pad
    assert any(p.startswith("/themes/") and p != "/themes/" and d == "2026-11-13" for p, d in vast.items())
    for pad, dag in vast.items():
        if pad in ("/about/", "/platform/") or pad.startswith(("/dossiers/", "/names/")):
            assert dag is None, pad


def test_a_fact_check_page_says_in_its_structured_data_when_it_last_changed(site):
    """`dateModified` van de pagina: de dag van haar nieuwste check, dezelfde als `lastmod` in de sitemap (PLAN #34.2bz)."""
    s, nr = site
    _, _, tekst = s.haal(f"/fact-checks/{nr['villa']}/")
    ld = json.loads(re.search(r'<script type="application/ld\+json">(.*?)</script>', tekst, re.S).group(1))
    assert ld["@type"] == "WebPage" and ld["dateModified"] == "2024-03-05"
