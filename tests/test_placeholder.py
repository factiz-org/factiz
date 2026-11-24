"""De placeholder van factiz.org (PLAN #34.2f, stap 3b): één stille pagina uit de site, die ook dient als
onderhoudspagina. PO 2026-11-12: "placeholder kan super simpel worden en gewoon iets zeggen als 'hier bouwen we aan
Factiz' [...] die we ook kunnen gebruiken voor als we onderhoud plegen aan de site".

Getoetst op de build, want dat is wat Cloudflare Pages serveert: één pagina, de tekst uit de woordenlijsten in de vijf
talen van de site, geen script, niets van elders, en niets wat er nog niet is.
"""

import html as html_lib
import json
import re
from pathlib import Path

import pytest

from tests.websitebouw import PLACEHOLDER, placeholder

ADRES = "info@factiz.org"
TALEN = ("en", "nl", "de", "es", "fr")
WOORDEN = Path(__file__).resolve().parent.parent / "factiz_site" / "teksten"


def _tekst(taal: str, sleutel: str) -> str:
    return json.loads((WOORDEN / f"{taal}.json").read_text(encoding="utf-8"))["teksten"][sleutel]


@pytest.fixture(scope="module")
def pagina() -> str:
    return placeholder()


def zichtbaar(html: str) -> str:
    tekst = re.sub(r"<(style|script)\b.*?</\1>", " ", html, flags=re.S)
    tekst = re.sub(r"<[^>]+>", " ", tekst)
    return " ".join(html_lib.unescape(tekst).split())


def test_the_placeholder_is_a_single_page():
    placeholder()
    paginas = sorted(p.relative_to(PLACEHOLDER).as_posix() for p in PLACEHOLDER.rglob("*.html"))
    assert paginas == ["index.html"], paginas


def test_it_says_in_each_language_of_the_site_that_we_are_building_factiz(pagina):
    tekst = zichtbaar(pagina)
    for taal in TALEN:
        assert _tekst(taal, "wacht_kop") in tekst and _tekst(taal, "wacht_tekst") in tekst, taal
        assert f'lang="{taal}"' in pagina, taal
    assert re.search(r'<html lang="en"', pagina)


def test_the_only_link_writes_to_us(pagina):
    assert re.findall(r'<a\b[^>]*\bhref="([^"]*)"', pagina) == [f"mailto:{ADRES}"]


def test_it_runs_no_script_and_loads_nothing_from_elsewhere(pagina):
    assert "<script" not in pagina.lower()
    for bron in re.findall(r'\b(?:src|href)="([^"]+)"', pagina):
        assert bron.startswith(("/", "mailto:")), bron
    assert not re.search(r"url\(\s*['\"]?https?:", pagina)
    kop = (PLACEHOLDER / "_headers").read_text(encoding="utf-8")
    assert "default-src 'none'" in kop and "font-src 'self'" in kop and "script-src" not in kop


def test_it_promises_nothing_that_is_not_there_yet(pagina):
    # geen link naar de controle of de site die nog niet open is, geen eigen meetcijfer
    assert "try.factiz.org" not in pagina
    assert not re.search(r"\d+(,\d+)?\s?%", zichtbaar(pagina))


def test_search_engines_do_not_keep_the_placeholder(pagina):
    # ook als onderhoudspagina: niet in de zoekresultaten, maar robots.txt laat de zoekmachine dat wel lezen
    assert '<meta name="robots" content="noindex">' in pagina
    assert "Disallow" not in (PLACEHOLDER / "robots.txt").read_text(encoding="utf-8")


def test_it_wears_the_logo_and_the_field_of_the_site(pagina):
    woordmerk = (Path(__file__).resolve().parent.parent / "factiz_site" / "static" / "merk" / "woordmerk-inline.svg").read_text(
        encoding="utf-8")
    assert woordmerk.strip()[:60] in pagina
    assert re.search(r'<img class="veld" src="/_astro/corpus\.[^"]+\.webp"[^>]*alt=""', pagina)
