"""De publieksdemo (E5.S2 → #22.4; Engelstalig sinds #22.7)."""

import re

import pytest
from fastapi.testclient import TestClient

import doublecheck.api as api
from doublecheck.storage import connect, init_schema


@pytest.fixture
def client():
    conn = connect(":memory:")
    init_schema(conn)
    api.app.dependency_overrides[api.get_conn] = lambda: conn
    yield TestClient(api.app)
    api.app.dependency_overrides.clear()
    conn.close()


def test_interface_offers_text_and_image_input(client):
    respons = client.get("/")

    assert respons.status_code == 200
    assert respons.headers["content-type"].startswith("text/html")
    pagina = respons.text
    assert "<textarea" in pagina
    assert 'type="file"' in pagina
    assert "accept=" in pagina


def test_interface_shows_raw_response_area(client):
    pagina = client.get("/").text

    # De ruwe respons komt in een <pre>; categorie en afstanden staan erin
    # doordat het hele JSON-antwoord getoond wordt (E5.S2-AC1).
    assert "<pre" in pagina
    assert "/resolve" in pagina


def test_interface_has_no_decoration_beyond_readability(client):
    pagina = client.get("/").text

    # AC2: geen vormgeving verder dan leesbaarheid — geen externe assets,
    # geen afbeeldingen, geen framework. Navigatie naar de eigen site en de
    # code mag (PO 2026-10-15: geen eilanden); laden van buiten nooit.
    pagina = re.sub(r'<a [^>]*href="https://(factiz\.org|github\.com/factiz-org)[^"]*"', "", pagina)
    for verboden in ("<img", "http://", "https://", "cdn", "bootstrap", "tailwind"):
        assert verboden not in pagina.lower(), verboden


def test_none_state_has_own_text_and_one_action(client):
    """D3: `none` is een geldig antwoord, geen lege staat."""
    pagina = client.get("/").text

    assert "Nothing found" in pagina
    # Uitleg van wat het wél en niet betekent (DESIGN stroom A).
    assert "does not mean" in pagina.lower()
    assert "actieKnop('none'" in pagina  # precies één vervolgactie


def test_related_state_names_what_matched(client):
    """D3 + E3.S2-AC2: `related` benoemt expliciet wát overeenkomt."""
    pagina = client.get("/").text

    assert "Related" in pagina
    assert "actieKnop('related'" in pagina  # precies één vervolgactie
    # De drie signalen die matched_on kan bevatten worden vertaald naar tekst.
    for signaal in ("tekst-gedeeltelijk", "beeld", "tegenspraak"):
        assert signaal in pagina


def test_states_are_not_presented_as_errors(client):
    """D3 + ontwerpprincipe 3: geen urgentie, geen foutvormgeving."""
    pagina = client.get("/")
    tekst = pagina.text

    for verboden in ("⚠", "❗", "🚫", "Fout:", "ERROR", "PAS OP"):
        assert verboden not in tekst, verboden

    # Geen alarmkleuren. Alleen het stijlblok bekijken: elders is "red" een
    # onschuldige lettergreep (zoals in "stored"), en mét woordgrens, want
    # `prefers-reduced-motion: reduce` (§5) bevat ": red" zonder rood te zijn.
    import re

    stijl = tekst[tekst.index("<style>"):tekst.index("</style>")].lower()
    assert not re.search(r"[:\s]red\b", stijl), "alarmrood in het stijlblok"
    for kleur in ("#f00", "#ff0000", "crimson", "tomato"):
        assert kleur not in stijl, kleur


def test_matched_state_shows_tally_not_score(client):
    """Principe 2: tellingen, nooit schattingen."""
    pagina = client.get("/").text

    assert "independent" in pagina or "check" in pagina
    # Geen percentage-opmaak in de uitslagweergave (DR2).
    assert "toFixed" not in pagina or "%" not in pagina.split("<pre")[0]


def test_each_error_state_has_its_own_text(client):
    """D7 + E5.S1-AC3: elke foutstaat eigen tekst."""
    pagina = client.get("/").text

    for kop in (
        "File too large",
        "Artifact cannot be read",
        "Index unavailable",
        "Server unreachable",
    ):
        assert kop in pagina, kop


def test_no_error_falls_back_to_none(client):
    """D7: een fout is een fout, nooit `none`."""
    pagina = client.get("/").text

    # De none-tekst bestaat precies één keer: in de none-tak, niet in een fouttak.
    assert pagina.count("Nothing found in the index") == 1
    # In de verzendlus wordt een niet-ok respons afgevangen én afgebroken
    # vóórdat de categorie-afhandeling aan bod komt.
    lus = pagina[pagina.index("formulier.addEventListener"):]
    assert lus.index("!antwoord.ok") < lus.index("toonUitslag(data)")
    assert "return;" in lus[lus.index("!antwoord.ok"):lus.index("toonUitslag(data)")]


def test_error_states_offer_a_way_forward(client):
    pagina = client.get("/").text

    assert "actieKnop('fout'" in pagina


def test_busy_state_names_the_step(client):
    """DESIGN stroom A stap 2: geen anonieme spinner."""
    pagina = client.get("/").text

    assert "Checking" in pagina
    # De fasen die de client écht kan waarnemen, met naam.
    assert "preparing the artifact" in pagina
    assert "waiting for the resolver" in pagina


def test_busy_state_names_the_work_per_artefact_type(client):
    pagina = client.get("/").text

    # Tekstroute en beeldroute doen aantoonbaar ander werk; dat wordt benoemd.
    assert "image hash" in pagina
    assert "OCR" in pagina
    assert "searching the index" in pagina


def test_busy_state_shows_elapsed_time_not_fake_progress(client):
    pagina = client.get("/").text

    assert "elapsed" in pagina
    # Geen voortgangsbalk of percentage: we weten de voortgang niet.
    assert "<progress" not in pagina
    assert "width: ' +" not in pagina


def test_dispute_is_offered_after_a_result(client):
    """DESIGN stroom C stap 1: je kunt een uitslag betwisten."""
    pagina = client.get("/").text

    assert "Dispute this result" in pagina
    assert "/dispute" in pagina


def test_consent_checkbox_is_never_pre_checked(client):
    """E6.S3-AC1: toestemming is expliciet, nooit vooraf aangevinkt."""
    pagina = client.get("/").text

    import re

    invoervelden = re.findall(r"<input[^>]*>", pagina)
    aanvinkvak = [veld for veld in invoervelden if 'id="toestemming"' in veld]
    assert len(aanvinkvak) == 1, invoervelden
    assert 'type="checkbox"' in aanvinkvak[0]
    assert "checked" not in aanvinkvak[0], aanvinkvak[0]


def test_consent_explains_what_is_stored_and_for_how_long(client):
    """DESIGN stroom C stap 2 (B11): uitleg wát er bewaard wordt en hoe lang."""
    from doublecheck.config import load_config

    pagina = client.get("/").text
    dagen = load_config().retention.artifact_days

    # De bewaartermijn komt uit config, niet uit de tekst (DR6).
    assert f"{dagen} days" in pagina
    # Beide gevallen worden uitgelegd, vóórdat je kiest.
    assert "fingerprint" in pagina
    assert "Without" in pagina and "With" in pagina
    # En het verwijderrecht wordt genoemd (B11).
    assert "delet" in pagina.lower()


def test_dispute_without_consent_is_the_default_path(client):
    """Stap 3: zonder toestemming gaat de betwisting gewoon door."""
    pagina = client.get("/").text

    assert "consent_to_store_artifact" in pagina
    # De uitslagtekst voor een betwisting is geen foutstaat (D3).
    assert "Dispute recorded" in pagina


# --- 22.4: van testinterface naar publieksdemo -------------------------------


def test_the_page_speaks_to_the_public_not_to_testers(client):
    """De demo is akte 1 (B18): hij legt in gewone woorden uit wát dit is —
    het geheugen van de factcheckers — zonder intern jargon in het zicht."""
    pagina = client.get("/").text
    assert "testinterface" not in pagina.lower()
    assert "memory" in pagina.lower()
    assert "fact-check" in pagina.lower()


def test_the_privacy_promise_is_on_the_page(client):
    """DR3 is een belofte aan de bezoeker, dus hij staat op de pagina zelf:
    tekst wordt niet bewaard, een beeld wordt na het rekenen weggegooid.
    De volledige verklaring leeft op de site; de demo noemt de plek
    (sinds 2026-10-15 als link: navigatie naar de eigen site laadt niets)."""
    pagina = client.get("/").text.lower()
    assert "not stored" in pagina
    assert "fingerprint" in pagina
    assert "factiz.org/privacy" in pagina


def test_matched_headline_carries_the_tally(client):
    """DESIGN §2: de kop dráágt de telling. Sinds B25 zegt hij helder wat
    bekend is, symmetrisch: bekend als onwaar en bekend als waar, met het
    aantal redacties; oordelen op verschillende kanten heten omstreden (B30)."""
    pagina = client.get("/").text
    assert "'Fact-checked · ' + telling" in pagina
    assert "newsroom" in pagina


def test_the_verdict_labels_are_symmetric_and_carry_the_count(client):
    """B25: wat klopt zeggen we net zo hard als wat niet klopt, ongeacht wie
    het deelt; en altijd met de bewijssterkte (de telling), nooit een
    percentage (DR2)."""
    pagina = client.get("/").text
    # De woorden van B30 en DESIGN §4c, dezelfde als het label in de tijdlijn
    # (#24.1); "Partly true" is een eigen label in laag 1 (PO 2026-10-14).
    for label in ("Known to be false", "Known to be misleading", "Known to be false or misleading",
                  "Known to be true", "Partly true", "Disputed by fact-checkers",
                  "Satire, according to fact-checkers", "Unproven, according to fact-checkers"):
        assert label in pagina, label
    for oud in ("Confirmed true", "Mixed verdicts"):
        assert oud not in pagina, oud
    # Rood en groen zijn kanten, de woorden dragen de betekenis (§5, D1).
    assert "'onwaar': 'rood'" in pagina and "'waar': 'groen'" in pagina


def test_sources_are_rendered_as_the_primary_block(client):
    """D2: het bronnenblok is het grootste element — structureel afdwingbaar:
    de checks renderen in een eigen bronnenlijst, niet als kale <ul>."""
    pagina = client.get("/").text
    assert 'class="bronnen"' in pagina
    assert ".bronnen" in pagina  # en de stylesheet kent hem


def test_raw_response_is_folded_away_for_developers(client):
    """De ruwe respons blijft (dat is de testinterface-erfenis en het
    PROTOCOL-venster), maar dichtgeklapt achter een ontwikkelaarsklepje."""
    pagina = client.get("/").text
    assert "<details" in pagina
    assert 'id="respons"' in pagina


def test_rate_limited_gets_its_own_calm_text(client):
    """429 is met #20.2 een echte uitkomst; hij krijgt een eigen rustige
    tekst (D7: nooit terugvallen op een generieke fout), zonder alarm."""
    pagina = client.get("/").text
    assert "429" in pagina
    assert "requests" in pagina.lower()


def test_both_colour_modes_and_reduced_motion_are_defined(client):
    """§5/D8: licht en donker zijn beide compleet en beweging respecteert
    de systeeminstelling."""
    pagina = client.get("/").text
    assert "prefers-color-scheme: dark" in pagina
    assert "prefers-reduced-motion" in pagina
    assert "focus-visible" in pagina


# --- 22.12: van publieksdemo naar marketingdemo (DESIGN §4a) -----------------


def test_the_shell_wears_the_brand_the_result_stays_lab(client):
    """§4a en §4h: de schil draagt het merk (papier, groen, de klik in inkt),
    maar de uitslagkaart blijft de laboratoriumuitslag met tellingen en
    bronnen."""
    pagina = client.get("/").text
    assert "#0e8a5b" in pagina          # merkgroen
    assert ".knop.primair { background: var(--inkt)" in pagina  # de klik is inkt, niet oranje
    assert "#ee6a2a" not in pagina
    assert "Factiz" in pagina
    # De uitslag blijft tellen, niet scoren; de bronnen blijven het blok.
    assert "'Fact-checked · ' + telling" in pagina
    assert 'class="bronnen"' in pagina


def test_the_dropzone_accepts_drag_choose_and_paste(client):
    """§4a: één groot doel — slepen over de pagina, klikken om te kiezen,
    en een screenshot plakken. De preview blijft lokaal (object-URL)."""
    pagina = client.get("/").text
    assert 'id="dropzone"' in pagina
    assert "'drop'" in pagina or '"drop"' in pagina
    assert "'dragover'" in pagina or '"dragover"' in pagina
    assert "'paste'" in pagina or '"paste"' in pagina
    assert "createObjectURL" in pagina
    # Kiezen via het bestandsveld blijft bestaan, met beeldfilter.
    assert 'type="file"' in pagina and 'accept="image/*"' in pagina


def test_the_preview_never_builds_html_from_file_data(client):
    """XSS-discipline (#17.5): een bestandsnaam is andermans data. De
    preview ontstaat via createElement en property-toewijzing, en de naam
    gaat door textContent, nooit door een HTML-string."""
    pagina = client.get("/").text
    assert "createElement('img')" in pagina
    assert ".textContent" in pagina
    script = pagina[pagina.index("<script>"):]
    for regel in script.splitlines():
        if "innerHTML" in regel:
            assert ".name" not in regel, regel


def test_sample_chips_fire_measured_matched_claims(client):
    """§4a: elke chip is vooraf op het echte corpus gemeten als `matched`
    (meting in PLAN #22.12). De chips staan op de pagina en vuren de
    check direct af."""
    from doublecheck.webui import CHIPS

    pagina = client.get("/").text
    assert len(CHIPS) >= 3
    for chip in CHIPS:
        assert chip in pagina, chip
    assert "data-claim" in pagina
    assert "requestSubmit" in pagina


def test_the_stats_line_comes_from_discovery_not_from_copy(client):
    """§4a: de statistiekregel haalt de echte cijfers uit het
    discovery-endpoint; er staat geen hardgecodeerde claimtelling in de
    pagina, en de waarden landen via textContent."""
    pagina = client.get("/").text
    assert "/.well-known/doublecheck" in pagina
    assert 'id="statistiek"' in pagina
    assert "80,902" not in pagina  # geen vastgebakken cijfer dat veroudert


def test_the_answer_time_is_measured_not_promised(client):
    """§4a: de demo toont de gemeten antwoordtijd van déze aanvraag
    (performance.now), geen belofte; en alleen bij een geslaagd antwoord."""
    pagina = client.get("/").text
    assert "performance.now" in pagina
    assert " ms" in pagina


def test_the_source_link_speaks_the_language_of_the_page(client):
    """De demo is Engelstalig (#22.7); de link naar de check heette nog "bron"."""
    pagina = client.get("/").text
    assert 'rel="noopener noreferrer">source</a>' in pagina
    assert ">bron</a>" not in pagina


def test_a_verdict_in_another_language_carries_its_meaning(client):
    """B32: "Yanlış (false)". Het oordeel blijft de woorden van de redactie;
    de betekenis komt uit het genormaliseerde oordeel, nooit uit een model.
    Demo en Ask delen dezelfde lijst (`webui.LABEL_JS`)."""
    from doublecheck.askui import ASK_PAGINA

    pagina = client.get("/").text
    for p in (pagina, ASK_PAGINA):
        assert "function betekenisVan(check)" in p and "'onwaar': 'false'" in p
    assert "const OORDEEL" not in pagina



def test_the_check_button_shows_that_it_is_checking_and_cannot_fire_twice(client):
    """Zoals in Ask (PO 2026-10-16): de knop zegt dat er gecontroleerd wordt,
    en een tweede klik start geen tweede verzoek."""
    pagina = client.get("/").text
    assert "knop.textContent = 'Checking...'" in pagina and "knop.textContent = 'Check'" in pagina
    assert "if (knop.disabled) return;" in pagina


def test_the_styles_of_every_app_page_are_balanced():
    """#23.11: een weggehaalde regel liet een `@media (prefers-color-scheme:
    dark) {` open staan, en toen gold de hele opmaak van demo en Ask alleen
    nog in donkere modus. Elke accolade in de opmaak heeft haar tegenhanger."""
    import re

    from doublecheck.askui import ASK_PAGINA
    from doublecheck.webui import PAGINA

    for naam, html in (("demo", PAGINA), ("ask", ASK_PAGINA)):
        for css in re.findall(r"<style[^>]*>(.*?)</style>", html, re.S):
            css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
            diepte = 0
            for teken in css:
                diepte += {"{": 1, "}": -1}.get(teken, 0)
                assert diepte >= 0, naam
            assert diepte == 0, naam
        assert "font-family: var(--serif)" in html, naam


# --- 23.14: de nieuwe look, de gedeelde voet (DESIGN §4h) ----------------------


def test_the_app_serves_the_site_fields_from_its_own_host(client):
    """De voet staat op een veld; ook op try.factiz.org komt dat beeld van
    de eigen host, zoals het favicon. Alleen de velden van het script."""
    antwoord = client.get("/beeld/nacht.webp")
    assert antwoord.status_code == 200
    assert antwoord.headers["content-type"] == "image/webp"
    assert antwoord.content[:4] == b"RIFF"
    assert client.get("/beeld/bestaat-niet.webp").status_code == 404
    assert client.get("/beeld/..%2Fbeeld%2Fnacht.webp").status_code == 404


# --- 23.14 stap 5: try.factiz.org op de band (DESIGN §4h, D11) ------------------


def _app_paginas(tmp_path) -> dict[str, str]:
    from doublecheck.askui import ASK_PAGINA
    from doublecheck.checkui import pagina as check_pagina
    from doublecheck.cijfers import bouw_pagina
    from doublecheck.config import load_config
    from doublecheck.webui import PAGINA

    conn = connect(":memory:")
    init_schema(conn)
    try:
        cijfers = bouw_pagina(conn, load_config(), str(tmp_path / "geen-conformantie.json"))
    finally:
        conn.close()
    return {"demo": PAGINA, "ask": ASK_PAGINA, "check": check_pagina(False), "cijfers": cijfers}


def _eigen_opmaak() -> dict[str, str]:
    """De opmaak die elke app-pagina zelf meebrengt, naast global.css."""
    from doublecheck import askui, checkui, cijfers, webui

    return {"demo en ask": webui.STIJL, "ask": askui._EXTRA_STIJL, "check": checkui._EXTRA_STIJL,
            "cijfers": "".join(re.findall(r"<style[^>]*>(.*?)</style>", cijfers._SKELET, re.S))}


def test_every_app_page_opens_on_the_band_with_the_result_below_it(tmp_path):
    """Elke pagina op try.factiz.org opent op dezelfde band als de site, met
    de kop erop in wit. De invoer, de uitslag, de bonnetjes en de meter staan
    eronder op papier, nooit op een veld (D11)."""
    for naam, html in _app_paginas(tmp_path).items():
        assert '<header class="kop op-veld">' in html, naam
        assert html.count('<section class="band op-veld">') == 1, naam
        begin = html.index('<section class="band op-veld">')
        einde = html.index("</section>", begin)
        assert "<h1>" in html[begin:einde] and html.index('<main id="main"') < begin, naam
        for daarna in ("<form", 'id="uitslag"', 'class="meter"', 'class="bonnetjes"', 'class="bronnen"'):
            if daarna in html:
                assert html.index(daarna) > einde, (naam, daarna)


def test_the_app_styles_put_no_field_behind_the_result():
    for naam, css in _eigen_opmaak().items():
        for verboden in ("url(", "op-veld", "/beeld/"):
            assert verboden not in css, (naam, verboden)


def test_the_check_button_is_an_ink_pill_and_orange_is_no_button_in_the_app():
    from doublecheck import webui

    knop = re.search(r'button\[type="submit"\] \{([^}]*)\}', webui.STIJL)
    assert knop and "background: var(--inkt)" in knop.group(1) and "color: var(--papier)" in knop.group(1)
    knoppen = re.search(r"(?m)^  button \{([^}]*)\}", webui.STIJL)
    assert knoppen and "border-radius: 999px" in knoppen.group(1)
    for naam, css in _eigen_opmaak().items():
        assert not re.search(r"background(-color)?:\s*var\(--oranje", css), naam


def test_in_the_app_the_serif_is_only_for_the_claim():
    """§4h: wat Factiz zelf zegt (de kop, de telling, de woorden van de
    meter) staat in de schreefloze; de serif alleen voor de bewering."""
    for naam, css in _eigen_opmaak().items():
        css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
        for selector, regel in re.findall(r"([^{}]+)\{([^{}]*)\}", css):
            if "var(--serif)" in regel:
                assert "bewering" in selector, (naam, selector.strip())


def test_example_chips_and_the_developer_details_are_44px_high():
    """Gevonden bij het nalopen (#23.15 stap 7): de voorbeeldknoppen van demo
    en Ask waren 35 px en de uitklapper voor ontwikkelaars 24 px; elk
    aanraakdoel buiten lopende tekst is minstens 44 px (DESIGN §5)."""
    from doublecheck.webui import STIJL

    for selector in (".chip", "details.dev summary"):
        regel = re.search(rf"(?:^|[}}\s]){re.escape(selector)}\s*\{{([^}}]*)\}}", STIJL, re.M)
        assert regel and re.search(r"min-height:\s*44px", regel.group(1)), selector
