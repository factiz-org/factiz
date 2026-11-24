"""Het eerlijkheidsdashboard (PLAN.md #22.5; Engelstalig en op `/numbers` sinds #22.7).

Dit is het merkverhaal in paginavorm (B18): wij publiceren onze missers. De
tests bewaken daarom twee dingen scherper dan gewoon "de route werkt":

- **Niets met de hand**: elk cijfer komt per verzoek uit de database
  (`benchmark_run`, `benchmark_fout`, `importrun`, de corpustellingen) of uit
  de conformantie-uitvoer. Een dashboard met ingetypte cijfers is precies het
  vijgenblad dat B17 verbiedt.
- **Lege staten zijn eerlijk**: geen benchmarkrun betekent "nog niet
  gedraaid", nooit een rij nullen die op een meting lijkt.

Zelfde paginadiscipline als de demo (geen externe assets, geen alarmkleuren);
percentages zijn hier systeemprecisie en dekking — dat is de ene plek waar
DR2 ze toestaat.
"""

import json
import re

import pytest
from fastapi.testclient import TestClient

import doublecheck.api as api
from doublecheck.storage import connect, init_schema, registreer_importrun


@pytest.fixture
def conn():
    conn = connect(":memory:")
    init_schema(conn)
    yield conn
    conn.close()


@pytest.fixture(autouse=True)
def _geen_conformantiebestand(tmp_path, monkeypatch):
    """De echte instantie laat `data/conformance-latest.json` achter; deze
    tests mogen niet van de schijfstand van de repo afhangen. Tests die wél
    een bestand willen, zetten de variabele daarna zelf opnieuw."""
    monkeypatch.setenv("DOUBLECHECK_CONFORMANTIE", str(tmp_path / "afwezig.json"))


@pytest.fixture
def client(conn):
    api.app.dependency_overrides[api.get_conn] = lambda: conn
    yield TestClient(api.app)
    api.app.dependency_overrides.clear()


def _zaai_corpus(conn):
    for nummer, (taal, datum) in enumerate(
        [("nl", "2024-03-14"), ("nl", "2025-01-02"), ("en", "")]
    ):
        conn.execute(
            "INSERT INTO claim (claim_id, canonical_text, language)"
            " VALUES (?, ?, ?)",
            (f"c{nummer}", f"claim nummer {nummer} over iets", taal),
        )
        conn.execute(
            "INSERT INTO factcheck (claim_id, publisher, verdict_normalized,"
            " verdict_original, url, review_date, language, source) VALUES"
            " (?, 'Nieuwscheckers', 'onwaar', 'Onjuist', ?, ?, ?,"
            " 'datacommons-ccby')",
            (f"c{nummer}", f"https://nieuwscheckers.nl/{nummer}", datum, taal),
        )
    conn.commit()


def _zaai_benchmark(conn, *, fouten=1):
    cursor = conn.execute(
        "INSERT INTO benchmark_run (started_at, text_match, text_related,"
        " image_same, model_version_text, model_version_image, pairs,"
        " same_pairs, wrong_links, correct_matches, results_per_language)"
        " VALUES ('2026-10-04T12:00:00+00:00', 0.92, 0.8, 31, 'model-x',"
        " 'pdq', 1531, 800, ?, 520, ?)",
        (fouten, json.dumps({"nl": {
            "pairs": 1531, "same_pairs": 800,
            "wrong_links": fouten, "correct_matches": 520,
        }})),
    )
    run_id = cursor.lastrowid
    for _ in range(fouten):
        conn.execute(
            "INSERT INTO benchmark_fout (run_id, language, provenance,"
            " is_same, target_claim_id, matched_claim_id, similarity)"
            " VALUES (?, 'nl', 'inkorting', 0, 'c0', 'c1', 0.934)",
            (run_id,),
        )
    conn.commit()
    return run_id


def test_the_dashboard_keeps_the_page_discipline(client):
    respons = client.get("/numbers")
    assert respons.status_code == 200
    assert respons.headers["content-type"].startswith("text/html")
    # Navigatie naar de eigen site en de code mag (PO 2026-10-15: geen
    # eilanden); laden van buiten nooit.
    pagina = re.sub(r'<a [^>]*href="https://(factiz\.org|github\.com/factiz-org)[^"]*"', "", respons.text).lower()
    for verboden in ("<img", "http://", "https://", "cdn"):
        assert verboden not in pagina, verboden
    assert "misses" in pagina  # het principe staat op de pagina zelf


def test_numbers_come_from_the_database_not_from_hand(client, conn):
    _zaai_corpus(conn)
    _zaai_benchmark(conn, fouten=7)
    pagina = client.get("/numbers").text
    assert "1,531" in pagina          # paren, EN-geformatteerd (#22.7)
    assert "2026-10-04" in pagina     # de rundatum reist mee
    assert "model-x" in pagina        # modelversie uit de run, niet uit config
    # Dekking 520/800 = 65.0% — berekend, niet getypt.
    assert "65.0%" in pagina


def test_the_misses_themselves_are_published(client, conn):
    """Niet alleen het foutcijfer maar de fouten: soort, gelijkenis, en de
    twee claimteksten zodat een lezer de misser kan navoelen."""
    _zaai_corpus(conn)
    _zaai_benchmark(conn, fouten=1)
    pagina = client.get("/numbers").text
    # De soort komt uit de data (NL), de pagina noemt hem in het Engels.
    assert "truncation" in pagina and "inkorting" not in pagina
    assert "0.934" in pagina
    assert "claim nummer 0" in pagina
    assert "claim nummer 1" in pagina


def test_empty_states_are_honest(client):
    pagina = client.get("/numbers").text.lower()
    assert "no benchmark run" in pagina
    assert "no refresh registered" in pagina
    assert "conformance" in pagina
    assert "python -m conformance" in pagina  # hoe je hem wél krijgt


def test_corpus_counts_are_live(client, conn):
    _zaai_corpus(conn)
    pagina = client.get("/numbers").text
    assert ">3<" in pagina
    assert "2025-01-02" in pagina          # nieuwste geldige datum
    assert "without a valid date" in pagina  # de rommel wordt geteld (§58)


def test_what_stays_outside_the_index_is_counted_in_public(client, conn):
    """B28: buiten de index is niet weg, en hoeveel er buiten staat is een
    openbaar cijfer, per reden."""
    from doublecheck.ingest import claim_id_for_text
    from doublecheck.toelating import zet_aan

    _zaai_corpus(conn)
    for claim_id, tekst, url in ((claim_id_for_text("Something to think about."), "Something to think about.",
                                  "https://nieuwscheckers.nl/vaag"),
                                 ("winkel", "This shop is the best in town", "https://webwinkel.example/r")):
        conn.execute("INSERT INTO claim (claim_id, canonical_text, language) VALUES (?, ?, 'en')", (claim_id, tekst))
        conn.execute("INSERT INTO factcheck (claim_id, publisher, verdict_normalized, verdict_original, url,"
                     " review_date, language) VALUES (?, 'X', 'onwaar', 'False', ?, '2024-01-01', 'en')",
                     (claim_id, url))
    conn.commit()
    zet_aan(conn)
    pagina = client.get("/numbers").text
    assert "kept outside the index</dt><dd>2 claims" in pagina
    assert "1 whose text says nothing checkable" in pagina
    assert "1 without a check from a reviewed publisher" in pagina


def test_dr7_counts_clusters_with_independent_publishers(client, conn):
    """Twee bekende, verschillende redacties op één bewering telt; één
    redactie telt niet — via het echte register en de echte configstand."""
    conn.execute(
        "INSERT INTO claim (claim_id, canonical_text, language, cluster_id)"
        " VALUES ('d1', 'bewering met consensus', 'nl', 'k1')")
    for uitgever, url in (
        ("Nieuwscheckers", "https://nieuwscheckers.nl/a"),
        ("Snopes", "https://www.snopes.com/b"),
    ):
        conn.execute(
            "INSERT INTO factcheck (claim_id, publisher, verdict_normalized,"
            " verdict_original, url, review_date, language, source) VALUES"
            " ('d1', ?, 'onwaar', 'x', ?, '2024-01-01', 'nl',"
            " 'datacommons-ccby')", (uitgever, url))
    conn.execute(
        "INSERT INTO claim (claim_id, canonical_text, language, cluster_id)"
        " VALUES ('d2', 'bewering zonder consensus', 'nl', 'k2')")
    conn.execute(
        "INSERT INTO factcheck (claim_id, publisher, verdict_normalized,"
        " verdict_original, url, review_date, language, source) VALUES"
        " ('d2', 'Nieuwscheckers', 'onwaar', 'x',"
        " 'https://nieuwscheckers.nl/c', '2024-01-01', 'nl',"
        " 'datacommons-ccby')")
    conn.commit()
    pagina = client.get("/numbers").text
    assert "independent" in pagina
    assert ">1<" in pagina


def test_conformance_output_is_rendered_from_file(client, tmp_path, monkeypatch):
    rapport = {
        "conformant": True,
        "complete": False,
        "results": [
            {"obligation": 7, "name": "thresholds in discovery",
             "status": "passed", "note": ""},
            {"obligation": 3, "name": "assessed never as matched",
             "status": "not observed", "note": "nothing produces assessed"},
        ],
        "limitations": ["runs without probes"],
    }
    pad = tmp_path / "conformance.json"
    pad.write_text(json.dumps(rapport), encoding="utf-8")
    monkeypatch.setenv("DOUBLECHECK_CONFORMANTIE", str(pad))
    pagina = client.get("/numbers").text
    assert "thresholds in discovery" in pagina  # uitslagnamen komen uit het bestand
    assert "not observed" in pagina
    assert "not fully tested" in pagina.lower()  # complete=False eerlijk benoemd


def test_a_broken_conformance_file_is_an_honest_error(client, tmp_path, monkeypatch):
    pad = tmp_path / "kapot.json"
    pad.write_text("{dit is geen json", encoding="utf-8")
    monkeypatch.setenv("DOUBLECHECK_CONFORMANTIE", str(pad))
    respons = client.get("/numbers")
    assert respons.status_code == 200
    assert "cannot be read" in respons.text.lower()


def test_the_old_dutch_path_still_serves_the_page(client):
    """`/cijfers` blijft als alias bestaan (#22.7): runbook, docs en oude
    links mogen niet stil breken."""
    assert "We publish our misses" in client.get("/cijfers").text


def test_languages_have_names_in_alphabetical_order_with_cross_lingual_last(client, conn):
    """Op een Engelse pagina geen taalcodes en geen "crosslinguaal": de naam
    van de taal, op alfabet, en cross-lingual apart onderaan (PO 2026-10-13)."""
    rij = {"pairs": 100, "same_pairs": 50, "wrong_links": 0, "correct_matches": 40}
    conn.execute(
        "INSERT INTO benchmark_run (started_at, text_match, text_related,"
        " image_same, model_version_text, model_version_image, pairs,"
        " same_pairs, wrong_links, correct_matches, results_per_language)"
        " VALUES ('2026-10-04T12:00:00+00:00', 0.92, 0.8, 31, 'model-x', 'pdq', 300, 150, 0, 120, ?)",
        (json.dumps({"nl": rij, "crosslinguaal": rij, "en": rij, "ar": rij}),),
    )
    conn.commit()
    pagina = client.get("/numbers").text
    assert "crosslinguaal" not in pagina
    volgorde = [pagina.index(f"<td>{naam}</td>") for naam in ("Arabic", "Dutch", "English", "Cross-lingual")]
    assert volgorde == sorted(volgorde)


def test_the_public_page_is_english_through_and_through(client, conn):
    """PO 2026-10-13: de voertaal van Factiz naar buiten is overal Engels.
    De pagina zegt dat ook tegen schermlezers en zoekmachines, en laat geen
    interne code als "DR7" zien."""
    _zaai_corpus(conn)
    _zaai_benchmark(conn, fouten=1)
    pagina = client.get("/numbers").text
    assert '<html lang="en">' in pagina
    assert "DR7" not in pagina


def test_a_miss_shows_where_the_two_texts_differ(client, conn):
    """PO 2026-10-16: een getalwissel werd onleesbaar, omdat beide teksten na
    90 tekens werden afgebroken, vóór het getal dat verschilde. Nu tot 280
    tekens, en een inkorting is als inkorting te zien."""
    begin = "Video yang diklaim sebagai video pesan terakhir Bupati Situbondo Dadang Wigiarto sebelum "
    conn.execute("INSERT INTO claim (claim_id, canonical_text, language) VALUES ('c0', ?, 'id')",
                 (begin + "meninggal pada 2021",))
    conn.execute("INSERT INTO claim (claim_id, canonical_text, language) VALUES ('c1', ?, 'id')",
                 (begin + "meninggal pada 2022",))
    conn.execute("INSERT INTO claim (claim_id, canonical_text, language) VALUES ('c2', ?, 'en')", ("x" * 400,))
    _zaai_benchmark(conn)
    pagina = client.get("/numbers").text
    assert "meninggal pada 2021" in pagina and "meninggal pada 2022" in pagina


def test_times_are_written_for_people(client, conn):
    _zaai_benchmark(conn)
    pagina = client.get("/numbers").text
    assert "2026-10-04 12:00 UTC" in pagina and "T12:00:00+00:00" not in pagina


def test_the_dashboard_speaks_plain_english(client, conn):
    """Geen stroeve zinnen: 'newsrooms' zoals overal op de site, 'not
    imported' in plaats van 'refused', en geen 'question mark belongs here'."""
    _zaai_corpus(conn)
    pagina = client.get("/numbers").text
    assert "independent newsrooms" in pagina and "independent publishers" not in pagina
    assert "question mark belongs" not in pagina and "<th>refused</th>" not in pagina


def test_a_miss_on_its_own_claim_says_what_the_test_changed(client, conn):
    """Bij een getalwissel is de fout dat een kopie met andere getallen toch aan
    het origineel gekoppeld werd. "X was linked to X" zei dat niet; de testtekst
    zelf bewaart de benchmark bewust niet."""
    conn.execute("INSERT INTO claim (claim_id, canonical_text, language) VALUES ('c9', ?, 'hi')",
                 ("2014 में दाल और शक्कर की कीमतें 2021 से ज्यादा थीं",))
    run_id = _zaai_benchmark(conn, fouten=0)
    conn.execute("INSERT INTO benchmark_fout (run_id, language, provenance, is_same, target_claim_id,"
                 " matched_claim_id, similarity) VALUES (?, 'hi', 'cijferwissel', 0, 'c9', 'c9', 0.897)", (run_id,))
    conn.commit()
    pagina = client.get("/numbers").text
    assert "a copy with its numbers changed was still linked to it" in pagina
    assert pagina.count("2014 में दाल") == 1
