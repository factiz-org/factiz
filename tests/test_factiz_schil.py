"""De schil van het platform (PLAN #33.6b, SPECS E9.S10, DESIGN §4t): filters met sorteren, de gegevens van het menu en
de vaste pagina's in vijf talen. De kop, het menu, de voet en het formulier zelf bouwt de site (B76)."""

import json
import re
from pathlib import Path
from urllib.parse import urlencode

import pytest

from factiz_site import app as fa
from factiz_site import i18n
from tests.test_factiz_dossiers import _site

TALEN = ("en", "nl", "de", "es", "fr")
PAKKET = Path(fa.__file__).resolve().parent
PAGINAS = PAKKET.parent / "site" / "src" / "components" / "site" / "paginas"


def _hrefs(client, adres):
    return [r["href"] for r in client.get(adres).json()["rijen"]]


def _een_adres(client, adres):
    """Het ene adres van de lijst die de gegevens bij dit adres beschrijven: hun filters en volgorde op alfabet, het
    blad erbij als het niet het eerste is (SPECS E9.S10 AC4)."""
    pad, _, vraag = adres.partition("?")
    taal = pad.split("/")[1] if pad.count("/") > 2 else "en"
    r = client.get(f"/api/{taal}/archief" + (f"?{vraag}" if vraag else ""))
    assert r.status_code == 200, adres
    g = r.json()
    delen = [tuple(p) for p in g["paren"]] + ([("p", str(g["blad"]))] if g["blad"] > 1 else [])
    return pad + (f"?{urlencode(sorted(delen))}" if delen else "")


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    return _site(tmp_path_factory)


# --- filters en sorteren ----------------------------------------------------------------------------------------------

def test_the_filters_show_what_is_chosen_and_offer_the_parts_of_the_chosen_theme(site):
    client, _ = site
    f = client.get("/api/nl/archief?taal=en&thema=war").json()["filters"]
    assert f["gekozen"]["thema"] == "war" and f["gekozen"]["taal"] == ["en"] and f["gekozen"]["jaar"] == ""
    # keuzelijsten voor thema, onderdeel, land en redactie; oordeel, taal en jaar zijn vinkjes (E9.S12)
    assert f["velden"] == ["thema", "onderdeel", "land", "redactie"]
    assert {g["soort"] for g in f["groepen"]} <= {"oordeel", "taal", "jaar"}
    assert [(k["waarde"], k["naam"]) for k in f["lijsten"]["onderdeel"]] == [("ukraine", "Rusland en Oekraïne")]
    # zonder thema is er geen keuzelijst voor het onderdeel
    zonder = client.get("/api/nl/archief?taal=en").json()["filters"]
    assert zonder["lijsten"]["onderdeel"] == [] and "onderdeel" not in zonder["velden"]


def test_what_is_filtered_is_named_and_each_piece_can_be_taken_away(site):
    client, _ = site

    def stukjes(adres):
        return [(s["kop"], s["naam"], s["url"]) for s in client.get(adres).json()["filters"]["stukjes"]]

    assert stukjes("/api/nl/archief?taal=en&thema=war") == [("Thema", "Oorlog en conflict", "/nl/fact-checks/?taal=en"),
                                                            ("Taal", "Engels", "/nl/fact-checks/?thema=war")]
    assert stukjes("/api/nl/archief") == []                                  # niets gekozen, niets te wissen
    # het onderdeel weghalen laat het thema staan; het thema weghalen neemt het onderdeel mee
    assert stukjes("/api/nl/archief?onderdeel=ukraine&thema=war") == [
        ("Thema", "Oorlog en conflict", "/nl/fact-checks/"), ("Onderdeel", "Rusland en Oekraïne", "/nl/fact-checks/?thema=war")]


def test_an_empty_or_unfitting_choice_from_the_form_leads_to_the_one_address_of_that_list(site):
    client, _ = site
    leeg = "thema=&oordeel=&jaar=&land=&redactie=&sorteer="
    for adres, doel in ((f"/fact-checks/?{leeg}&taal=en", "/fact-checks/?taal=en"), (f"/fact-checks/?{leeg}&taal=", "/fact-checks/"),
                        (f"/nl/fact-checks/?{leeg}&taal=hi", "/nl/fact-checks/?taal=hi"),
                        ("/fact-checks/?onderdeel=ukraine&thema=health", "/fact-checks/?thema=health"),
                        ("/fact-checks/?onderdeel=covid&thema=", "/fact-checks/"), ("/fact-checks/?onderdeel=covid", "/fact-checks/"),
                        ("/fact-checks/?sorteer=&p=1", "/fact-checks/")):
        assert _een_adres(client, adres) == doel, adres
    # een waarde of sleutel die niet bestaat, blijft niet gevonden
    for fout in ("?taal=xx&thema=", "?sorteer=willekeurig", "?kleur=", "?q=villa"):
        assert client.get("/api/en/archief" + fout).status_code == 404, fout


def test_the_list_sorts_on_newest_oldest_and_most_newsrooms_and_keeps_that_while_filtering(site):
    client, n = site
    nieuwste = _hrefs(client, "/api/en/archief")
    assert nieuwste[:2] == [f"/fact-checks/{n['hindi']}/", f"/fact-checks/{n['villa']}/"]      # 7 juni 2024, 5 maart 2024
    oudste = _hrefs(client, "/api/en/archief?sorteer=oud")
    # op de datum die de lijst toont (de laatste check): 2021 (knoflook), maart 2022 (biolab), december 2023 (het
    # jacht); de villa is in 2022 voor het eerst gecheckt maar in 2024 voor het laatst. Zonder datum achteraan.
    assert oudste[:3] == [f"/fact-checks/{n['los']}/", f"/fact-checks/{n['biolab']}/", f"/fact-checks/{n['jacht']}/"]
    assert oudste[-1] == f"/fact-checks/{n['zonder_datum']}/"
    assert _hrefs(client, "/api/en/archief?sorteer=redacties")[0] == f"/fact-checks/{n['villa']}/"   # twee redacties
    f = client.get("/api/nl/archief?sorteer=oud&taal=en").json()["filters"]
    assert f["sorteer"] == "oud"
    assert [(s["naam"], s["url"]) for s in f["stukjes"]] == [("Engels", "/nl/fact-checks/?sorteer=oud")]
    # Beste treffer is er alleen bij zoeken
    assert [v["naam"] for v in f["volgordes"]] == ["Nieuwste eerst", "Oudste eerst", "Meeste redacties"]


def test_an_empty_list_says_so_with_one_next_step(site):
    client, _ = site
    r = client.get("/api/nl/archief?taal=hi&jaar=2021")
    g = r.json()
    assert r.status_code == 200 and g["rijen"] == [] and g["totaal"] == 0 and g["aantal"] == "0 factchecks"
    # geen volgend of vorig blad; wel wat er gekozen is, om weg te halen
    assert g["blad"] == g["bladen"] == 1 and [s["naam"] for s in g["filters"]["stukjes"]] == ["Hindi", "2021"]


# --- zoeken met filters ---------------------------------------------------------------------------------------------

def _zoek(client, vraag, site="en", **velden):
    """Een zoekvraag in het bericht, op de site in taal `site`, met de filters als velden."""
    return client.post(f"/api/{site}/zoek", data={"q": vraag, **velden})


def test_search_takes_the_same_filters_and_order_and_the_question_never_enters_an_address(site):
    client, n = site
    treffers = lambda r: [rij["href"] for rij in r.json()["rijen"]]
    alles = _zoek(client, "Zelensky bought")
    assert set(treffers(alles)) == {f"/fact-checks/{n[k]}/" for k in ("villa", "jacht", "hindi")}     # de Hindi via de vertaling
    assert treffers(_zoek(client, "Zelensky bought", taal="hi")) == [f"/fact-checks/{n['hindi']}/"]
    assert treffers(_zoek(client, "Zelensky bought", thema="war")) == [f"/fact-checks/{n['villa']}/"]
    assert treffers(_zoek(client, "Zelensky bought", sorteer="oud"))[0] == f"/fact-checks/{n['jacht']}/"   # december 2023
    assert treffers(_zoek(client, "Zelensky bought", sorteer="nieuw"))[0] == f"/fact-checks/{n['hindi']}/"
    r = _zoek(client, "Zelensky bought", site="nl", thema="war")
    f = r.json()["filters"]
    # dezelfde filters, met de keuze gemarkeerd en de beste treffer als volgorde
    assert f["gekozen"]["thema"] == "war" and (f["volgordes"][0]["naam"], f["volgordes"][0]["aan"]) == ("Beste treffer", True)
    # wat gefilterd is, haal je weg met de rest van de keuzes, die opnieuw in het bericht gaan
    assert [(s["kop"], s["naam"], s["paren"]) for s in f["stukjes"]] == [("Thema", "Oorlog en conflict", [])]
    assert "Zelensky" not in " ".join(re.findall(r'"(?:href|url)":"([^"]*)"', r.text))
    assert alles.headers["cache-control"] == "no-store"
    # een keuze die niet bestaat, doet bij zoeken niets: de vraag blijft staan
    r = _zoek(client, "Zelensky bought", taal="xx", sorteer="willekeurig", kleur="rood")
    assert r.status_code == 200 and len(treffers(r)) == 3


# --- vindbaarheid -----------------------------------------------------------------------------------------------------

def test_a_fact_check_carries_a_description_of_its_own_and_its_theme_for_the_crumb_trail(site):
    client, n = site
    g = client.get(f"/api/nl/factcheck/{n['villa']}").json()
    kop = g["kop"]
    assert "Zelensky bought a villa in Florida" in kop["titel"]
    assert kop["omschrijving"].startswith("Onwaar volgens AFP en Snopes.") and "2 redacties" in kop["omschrijving"]
    ander = client.get(f"/api/nl/factcheck/{n['jacht']}").json()["kop"]["omschrijving"]
    assert ander != kop["omschrijving"] and len(kop["omschrijving"]) <= 160
    # het kruimelpad: de start, de lijst en de bewering; de site zet het thema ertussen
    kruimel = json.loads(kop["ld"])["breadcrumb"]["itemListElement"]
    assert [k["item"] for k in kruimel[:2]] == ["https://factiz.org/nl/", "https://factiz.org/nl/fact-checks/"]
    assert g["thema"]["href"] == "/nl/themes/war/"


def _vaste_sleutels():
    """De woorden van de vaste pagina's (Platform, Over Factiz), zoals de site ze gebruikt."""
    sleutels = set()
    for naam in ("Platform.astro", "Over.astro"):
        sleutels |= set(re.findall(r"t\('((?:platform|over)_[a-z0-9_]+)'", (PAGINAS / naam).read_text(encoding="utf-8")))
    return sleutels | {f"platform_motorkap_stap{i}" for i in range(1, 7)}


def test_the_fixed_pages_exist_in_all_five_languages_in_their_own_words_without_dashes_or_exclamations():
    koppen = {"en": ("What Factiz builds", "About Factiz"), "nl": ("Wat Factiz bouwt", "Over Factiz"),
              "de": ("Was Factiz baut", "Über Factiz"), "es": ("Lo que construye Factiz", "Sobre Factiz"),
              "fr": ("Ce que Factiz construit", "À propos de Factiz")}
    sleutels = _vaste_sleutels()
    assert len(sleutels) >= 20
    gezien = set()
    for taal, (platform, over) in koppen.items():
        assert i18n.tekst(taal, "platform_kop") == platform and i18n.tekst(taal, "nav_over") == over
        woorden = i18n.teksten(taal)
        teksten = [woorden[k] for k in sleutels]
        assert all(isinstance(w, str) and "—" not in w and "!" not in w for w in teksten), taal
        # de tekst is in elke taal een eigen tekst, geen Engelse met een andere kop
        alineas = {w for w in teksten if len(w) >= 60}
        assert len(alineas) >= 8 and not gezien & alineas, taal
        gezien |= alineas
