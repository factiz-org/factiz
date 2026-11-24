"""Ask Factiz: een vraag aan het corpus (PLAN #24.10, SPECS E5.S3, DESIGN §4e).

Een vraag in gewone woorden, en terug de gecheckte beweringen die er het
dichtst bij liggen. De categorie per bewering komt uit de
categoriseringsfunctie, met de drempels van de resolver: de herordenaar als
eigen poort haalde de stiltemeting niet (BENCHMARK §114). Het oordeel hoort
bij de bewering, nooit bij de vraag.
"""

import json
import re
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

import doublecheck.api as api
from doublecheck.config import load_config
from doublecheck.embedding import TextFingerprint
from doublecheck.storage import connect, init_schema, save_text_fingerprint

WORTEL = Path(__file__).resolve().parent.parent

LAB = "Did corona escape from a lab?"
BIOLAB = "Are there biolabs in Georgia?"
MAAN = "When is the next full moon?"
SWAHILI = "Ndizi zina vitamini C zaidi kuliko machungwa yote duniani"
LABS = "Are there US labs in Georgia?"
ALIEN = "Is the alien interrogation video real?"
GALICISCH = "Was the cure for corona found in Italy?"
VACCINS = "Do vaccines cause autism?"

# Zeven richtingen: 0 lab, 1 biolab, 2 bananen, 3 leeg, 4 alien, 5 Italië, 6 vaccins.
VRAGEN = {
    LAB: [0.9, 0.0, 0.0, 0.43589],  # 0,90 tot de labclaim: matched
    BIOLAB: [0.0, 0.80, 0.0, 0.6],  # 0,80 tot de biolabclaim: related
    MAAN: [0.0, 0.0, 0.0, 1.0],  # nergens in de buurt
    SWAHILI: [0.0, 0.0, 0.0, 1.0],
    LABS: [0, 1, 0, 0],  # beide biolabclaims: matched
    ALIEN: [0, 0, 0, 0, 1],
    GALICISCH: [0, 0, 0, 0, 0, 1],
    VACCINS: [0, 0, 0, 0, 0, 0, 1],  # de claim en haar ontkenning: matched
}
DIM = 7


def _eenheid(richting):
    vector = np.zeros(DIM, dtype=np.float32)
    vector[:len(richting)] = richting
    vector = vector / np.linalg.norm(vector)
    vector.setflags(write=False)
    return vector


def _claim(conn, versie, claim_id, tekst, richting, checks, cluster=None, taal="en", vertaling=None):
    conn.execute("INSERT INTO claim (claim_id, canonical_text, language, cluster_id) VALUES (?, ?, ?, ?)",
                 (claim_id, tekst, taal, cluster))
    for check in checks:
        uitgever, oordeel, datum = check[:3]
        woorden = check[3] if len(check) > 3 else oordeel.capitalize()
        conn.execute("INSERT INTO factcheck (claim_id, publisher, verdict_normalized, verdict_original, url,"
                     " review_date, language) VALUES (?, ?, ?, ?, ?, ?, ?)",
                     (claim_id, uitgever, oordeel, woorden,
                      f"https://{uitgever.lower()}.example/{claim_id}", datum, taal))
    save_text_fingerprint(conn, claim_id, TextFingerprint(_eenheid(richting), versie))
    if vertaling:
        conn.execute("INSERT INTO claim_variant (claim_id, language, text, generator, prompt_version, model_version,"
                     " payload) VALUES (?, 'en', ?, 'claude-haiku-5-5', 'vertalingen-v1', ?, ?)",
                     (claim_id, vertaling, versie, _eenheid(richting).tobytes()))


@pytest.fixture
def opzet(monkeypatch):
    config = load_config()
    versie = config.model_versions.text_embedding
    conn = connect(":memory:")
    init_schema(conn)
    _claim(conn, versie, "lab", "COVID-19 escaped from the lab in Wuhan", [1, 0, 0, 0],
           [("Alpha", "onwaar", "2020-02-01"), ("Beta", "onbewezen", "2025-03-01")], cluster="c-lab")
    _claim(conn, versie, "lab2", "The coronavirus was leaked from the Wuhan Institute of Virology",
           [0.98, 0.2, 0, 0], [("Gamma", "onbewezen", "2024-06-01")], cluster="c-lab")
    _claim(conn, versie, "biolab", "The US runs bioweapons labs in Georgia", [0, 1, 0, 0],
           [("Delta", "onwaar", "2022-03-10")])
    _claim(conn, versie, "ver", "Bananas are radioactive", [0, 0, 1, 0], [("Epsilon", "misleidend", "2019-01-01")])
    _claim(conn, versie, "biolab2", "The US tests bioweapons in Georgian labs", [0, 0.97, 0.243],
           [("Zeta", "onwaar", "2023-04-01"), ("Eta", "onbekend", "2023-05-01", "Labs, yes. Weapons, no")])
    _claim(conn, versie, "alien", "Videodakinin gerçek bir uzaylı olduğu iddiası", [0, 0, 0, 0, 1],
           [("Dogrula", "onwaar", "2023-09-18", "Yanlış")], taal="tr",
           vertaling="The claim that the person in the video is a real alien.")
    _claim(conn, versie, "italie", "Na Itália, o remédio contra o coronavírus foi encontrado", [0, 0, 0, 0, 0, 1],
           [("Theta", "onwaar", "2020-03-20", "Falso")], taal="gl",
           vertaling="After Italy, the cure for the coronavirus has been found")
    _claim(conn, versie, "vac", "Vaccines cause autism", [0, 0, 0, 0, 0, 0, 1], [("Iota", "onwaar", "2019-01-01")])
    _claim(conn, versie, "vacniet", "Vaccines do not cause autism", [0, 0, 0.312, 0, 0, 0, 0.95],
           [("Kappa", "waar", "2019-04-11")])
    conn.commit()
    # Met de vraagvorm aan (#25.36) zoekt Ask ook met de vraag als bewering;
    # die krijgt hier dezelfde vector, zodat deze tests Ask zelf toetsen.
    from doublecheck.vraagvorm import als_bewering

    vectoren = {**{als_bewering(v): x for v, x in VRAGEN.items()}, **VRAGEN}
    monkeypatch.setattr(api, "fingerprint_text",
                        lambda tekst, v: TextFingerprint(_eenheid(vectoren[tekst]), v))
    api.app.dependency_overrides[api.get_conn] = lambda: conn
    yield TestClient(api.app), conn
    api.app.dependency_overrides.clear()
    conn.close()


@pytest.fixture
def client(opzet):
    return opzet[0]


def _vraag(client, vraag):
    respons = client.post("/ask", json={"question": vraag})
    assert respons.status_code == 200, respons.text
    return respons.json()


def test_a_claim_below_the_related_threshold_is_never_in_the_answer(client):
    """DR4: wat onder de verwantdrempel ligt, komt niet in het antwoord, ook
    niet als "dichtstbijzijnde toch maar"."""
    antwoord = _vraag(client, MAAN)
    assert antwoord["results"] == []
    gerelateerd = _vraag(client, BIOLAB)
    assert [r["claim"]["id"] for r in gerelateerd["results"]] == ["biolab"]


def test_every_row_carries_its_category_from_the_categorize_function(client):
    drempels = load_config().thresholds
    dichtbij = _vraag(client, LAB)["results"][0]
    assert dichtbij["category"] == "matched" and dichtbij["similarity"] >= drempels.text_match
    verwant = _vraag(client, BIOLAB)["results"][0]
    assert verwant["category"] == "related"
    assert drempels.text_related <= verwant["similarity"] < drempels.text_match


def test_a_cluster_is_shown_once_with_the_claim_closest_to_the_question(client):
    """Twee leden van één cluster dragen dezelfde bonnetjes; twee kaarten met
    dezelfde checks zouden dubbel tellen wat één keer gecheckt is."""
    resultaten = _vraag(client, LAB)["results"]
    assert [r["claim"]["id"] for r in resultaten] == ["lab"]
    assert resultaten[0]["claim"]["text"] == "COVID-19 escaped from the lab in Wuhan"


def test_each_row_carries_the_receipts_of_its_whole_cluster(client):
    rij = _vraag(client, LAB)["results"][0]
    bewijs = rij["evidence"]
    assert bewijs["check_count"] == 3
    assert {c["publisher"] for c in bewijs["checks"]} == {"Alpha", "Beta", "Gamma"}
    assert all(c["url"].startswith("https://") and c["review_date"] for c in bewijs["checks"])
    assert rij["claim"]["cluster_size"] == 2


def test_the_answer_never_judges_the_question_itself(client):
    """Geen ja of nee en geen percentage op de vraag (DR2, B25): het oordeel
    staat alleen in de checks van de getoonde bewering."""
    antwoord = _vraag(client, LAB)
    assert set(antwoord) == {"resolver", "results", "reason", "thresholds", "schemes_used", "totals", "summary",
                             "tiplines", "tiplines_source"}
    rij = antwoord["results"][0]
    assert set(rij) == {"category", "similarity", "claim", "via", "evidence", "translation"}


def test_nothing_shown_says_why(client):
    assert _vraag(client, MAAN)["reason"] == "not_found"
    assert _vraag(client, SWAHILI)["reason"] == "out_of_scope"
    assert _vraag(client, LAB)["reason"] is None


def test_asking_stores_nothing(opzet):
    """DR3: de vraag wordt vergeleken en vergeten; geen enkele tabel groeit."""
    client, conn = opzet
    tabellen = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")]
    voor = {t: conn.execute(f"SELECT count(*) FROM {t}").fetchone()[0] for t in tabellen}
    _vraag(client, LAB)
    _vraag(client, MAAN)
    na = {t: conn.execute(f"SELECT count(*) FROM {t}").fetchone()[0] for t in tabellen}
    assert voor == na


def test_an_empty_or_oversized_question_gets_its_own_error(client):
    assert client.post("/ask", json={"question": "   "}).status_code == 422
    assert client.post("/ask", json={"question": "x" * (api.MAX_TEXT_LENGTH + 1)}).status_code == 413


def test_a_caller_cannot_ask_for_a_lower_threshold(client):
    """Zoals bij /resolve (DR4): een onbekend veld wordt geweigerd."""
    assert client.post("/ask", json={"question": LAB, "threshold": 0.1}).status_code == 422


def test_an_index_of_another_model_version_is_refused(opzet):
    client, conn = opzet
    conn.execute("DELETE FROM fingerprint")
    save_text_fingerprint(conn, "lab", TextFingerprint(_eenheid([1, 0, 0, 0]), "ander-model@1"))
    conn.commit()
    assert client.post("/ask", json={"question": LAB}).status_code == 503


# --- De pagina -----------------------------------------------------------

@pytest.fixture
def pagina(client):
    respons = client.get("/ask")
    assert respons.status_code == 200
    return respons.text


def test_the_question_never_goes_into_a_url(pagina):
    """Een vraag in een URL belandt in logboeken en geschiedenis (DR3)."""
    assert "fetch('/ask'" in pagina and "method: 'POST'" in pagina
    for lek in ("location.search", "URLSearchParams", "?q=", "history.pushState"):
        assert lek not in pagina


def test_the_card_puts_the_claim_before_the_verdict(pagina):
    """DESIGN §4e: het oordeel hoort bij de bewering. Eerst de bewering zoals
    redacties haar checkten, dan het label."""
    kaart = re.search(r"function rijVoor\(.*?\n}\n", pagina, re.S).group(0)
    assert kaart.index("claim.text") < kaart.index("WOORDEN[")
    assert kaart.index("el('summary', '', bewering, chip") > 0
    assert "Close to your question" in pagina and "Related to your question" in pagina


def test_the_page_never_shows_a_score(pagina):
    kaart = re.search(r"function rijVoor\(.*?\n}\n", pagina, re.S).group(0)
    assert "similarity" not in kaart and "%" not in kaart


def test_every_answer_offers_wrong_tell_us(pagina):
    assert pagina.count("Wrong? Tell us") >= 1
    assert "fetch('/dispute'" in pagina
    for veld in ("disputed_category", "dispute_text", "claim_id", "consent_to_store_artifact"):
        assert veld in pagina


def test_the_consent_checkbox_is_never_pre_checked(pagina):
    assert re.search(r'<input type="checkbox" id="toestemming"(?![^>]*checked)', pagina)


def test_the_page_states_the_measured_figure_with_its_setup(pagina):
    from doublecheck.ask import METING

    assert f"{METING['vragen']} test questions" in pagina
    assert f"{METING['getoond_juist']} show the claim we" in pagina
    assert f"{METING['andere']} show a related check" in pagina and f"{METING['niets']} show nothing" in pagina
    assert "5,000" in pagina


def test_example_questions_come_from_the_test_set(pagina):
    """DESIGN §4a en §4e: een voorbeeld dat de pagina niet waarmaakt is een
    anti-demo. Alleen vragen uit de testset, waar ze de juiste bewering toonden."""
    from doublecheck.askui import VOORBEELDEN

    testset = {v["vraag"] for v in json.loads(
        (WORTEL / "docs" / "steekproeven" / "24.10-vragen.json").read_text(encoding="utf-8"))["vragen"]}
    assert VOORBEELDEN and set(VOORBEELDEN) <= testset
    for vraag in VOORBEELDEN:
        assert vraag.replace('"', "&quot;") in pagina or vraag in pagina


def test_the_measurement_and_the_endpoint_share_one_path():
    """Kritiek AC van E5.S3: het cijfer op de pagina is het cijfer van dit pad."""
    for module in ("api.py", "vraagtoets.py"):
        bron = (WORTEL / "doublecheck" / module).read_text(encoding="utf-8")
        assert "ask.kandidaten(" in bron and "ask.getoond(" in bron, module


def test_no_frontier_model_in_the_request_path():
    """B26: geen taalmodel dat schrijft, en geen herordenaar als poort (§114)."""
    bron = (WORTEL / "doublecheck" / "ask.py").read_text(encoding="utf-8")
    for verboden in ("anthropic", "herordenaar", "openai"):
        assert f"import {verboden}" not in bron and f"from doublecheck.{verboden}" not in bron



# --- Eén antwoord: tellingen, samenvatting, vertaling, tiplijnen (DESIGN §4e) ---

def test_the_answer_counts_claims_newsrooms_languages_and_years(client):
    totaal = _vraag(client, LABS)["totals"]
    assert totaal["claims"] == 2 and totaal["first_year"] == "2022" and totaal["last_year"] == "2023"
    # De redacties in de testdata zijn verzonnen namen; DR7 telt die niet als onafhankelijk.
    assert totaal["languages"] == 1 and isinstance(totaal["newsrooms"], int)


def test_the_summary_counts_rated_checks_and_quotes_a_check_without_rating(client):
    samen = _vraag(client, LABS)["summary"]
    assert samen["kind"] == "agree" and samen["side"] == "false or misleading" and samen["rated"] == 2
    assert samen["no_rating"] == {"count": 1, "publisher": "Eta", "words": "Labs, yes. Weapons, no"}


def test_no_summary_when_two_shown_claims_say_opposite_things(client):
    """"Vaccines cause autism" en "Vaccines do not cause autism": een telling
    zou hier misleiden, dus het antwoord zegt waarom er geen is."""
    samen = _vraag(client, VACCINS)["summary"]
    assert samen["kind"] == "opposite" and samen["claim_id"] == "vacniet" and samen["verdict_class"] == "waar"


def test_no_summary_for_a_single_claim(client):
    assert _vraag(client, ALIEN)["summary"] is None


def test_rated_checks_that_disagree_are_named_as_such():
    from doublecheck.ask import Kandidaat, samenvatting
    from doublecheck.categorize import Category
    from doublecheck.evidence import EvidenceState, FactcheckEvidence

    def rij(claim, tekst, oordeel):
        check = FactcheckEvidence("X", oordeel, oordeel, f"https://x.example/{claim}", "2020-01-01", "en")
        return (Kandidaat(claim, tekst, 0.9, Category.MATCHED),
                EvidenceState(claim, tekst, (check,), 1, 1, ("en",), "2020-01-01", 1, (claim,)))

    samen = samenvatting([rij("a", "The old bridge collapsed last week", "onwaar"),
                          rij("b", "The new bridge was paid for by the EU", "waar")])
    assert samen["kind"] == "disagree" and samen["counts"] == {"false or misleading": 1, "true": 1}


def test_a_translation_comes_with_its_original_and_provenance(client):
    rij = _vraag(client, ALIEN)["results"][0]
    assert rij["claim"]["text"] == "Videodakinin gerçek bir uzaylı olduğu iddiası"
    assert rij["translation"] == {"language": "en", "from_language": "tr",
                                  "text": "The claim that the person in the video is a real alien.",
                                  "generator": "claude-haiku-5-5", "prompt": "vertalingen-v1"}


def test_no_translation_where_the_read_test_found_an_error_or_none_is_needed(client):
    """B32, BENCHMARK §117: het label Galicisch gaf de enige betekenisfout."""
    assert _vraag(client, GALICISCH)["results"][0]["translation"] is None
    assert _vraag(client, LAB)["results"][0]["translation"] is None


def test_tiplines_only_when_nothing_is_shown_and_in_the_language_of_the_question(client):
    from doublecheck.ask import TIPLIJNEN

    data = json.loads(TIPLIJNEN.read_text(encoding="utf-8"))
    assert _vraag(client, LAB)["tiplines"] == []
    swahili = _vraag(client, SWAHILI)
    assert swahili["tiplines"] and swahili["tiplines_source"]["recorded"] == "2026-10-15"
    for lijn in swahili["tiplines"]:
        assert "sw" in data["talen_per_land"][lijn["country"]]


def test_the_tipline_list_is_copied_with_its_source_and_never_carries_the_question():
    from doublecheck.ask import TIPLIJNEN

    data = json.loads(TIPLIJNEN.read_text(encoding="utf-8"))
    assert data["_bron"]["url"].startswith("https://faq.whatsapp.com/") and data["_bron"]["vastgelegd"]
    for lijn in data["lijnen"]:
        assert lijn["land"] in data["talen_per_land"]
        for link in lijn["links"]:
            assert re.fullmatch(r"https://wa\.me/\d+", link), link


def test_the_page_shows_one_answer_with_rows_that_open(pagina):
    assert "function rijVoor" in pagina and "details" in pagina
    for woorden in ("Machine translation from", "In their words", "Send it to a fact-checker",
                    "No summary: these claims do not all say the same thing"):
        assert woorden in pagina, woorden


def test_asking_twice_never_runs_two_counters_or_shows_an_older_answer(pagina):
    """PO 2026-10-16: twee keer op Ask gaf twee tellers tegelijk. Er loopt
    altijd één teller, alleen de laatste vraag krijgt haar antwoord, en de
    knop staat uit zolang er gezocht wordt."""
    stel = re.search(r"async function stel\(.*?\n}\n", pagina, re.S).group(0)
    assert stel.index("stopKlok();") < stel.index("klok = setInterval(")
    assert "const klok" not in stel
    assert stel.count("if (mijn !== volgnummer) return;") >= 2
    assert "knop.disabled = true" in stel and "knop.disabled = false" in stel



def test_the_ask_button_shows_that_it_is_searching(pagina):
    """PO 2026-10-16: zonder feedback op de knop zie je niet dat er gezocht
    wordt. De knop zegt het zelf, en het antwoordvak meldt dat het bezig is."""
    stel = re.search(r"async function stel\(.*?\n}\n", pagina, re.S).group(0)
    assert "knop.textContent = 'Searching...'" in stel and "knop.textContent = 'Ask'" in stel
    assert "aria-busy" in stel
    assert 'button[type="submit"]:disabled' in pagina
