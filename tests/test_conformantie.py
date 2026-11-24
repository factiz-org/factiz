"""Conformantietest voor het resolverprotocol (PLAN.md #15.1, PROTOCOL §8).

De suite in `conformance/` moet lós van deze implementatie staan: hij praat
alleen HTTP en kent `doublecheck` niet. Deze tests bewijzen twee dingen — dat
hij onze eigen dienst goedkeurt, én dat hij opzettelijk kapotte resolvers
betrapt. Zonder dat tweede bewijs zegt een groene suite niets.
"""

import ast
import json
import pathlib

import numpy as np
import pytest
from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient

import dataclasses

import conformance
import doublecheck.api as api
from conformance import GESLAAGD, NIET_WAARGENOMEN, Proef, controleer_resolver
from doublecheck.config import VariantSettings, load_config
from doublecheck.embedding import TextFingerprint
from doublecheck.ingest import claim_id_for_text
from doublecheck.storage import connect, init_schema, save_text_fingerprint, save_variant

BEKENDE_TEKST = "De zeespiegel daalt al tien jaar wereldwijd"
VERTAALDE_TEKST = "Sea level has been falling worldwide for ten years"
ONBEKENDE_TEKST = "Bananen bevatten meer vitamine C dan sinaasappels"


# --------------------------------------------------------------------------
# Onze eigen dienst
# --------------------------------------------------------------------------


def _eenheid(richting):
    vector = np.asarray(richting, dtype=np.float32)
    vector = vector / np.linalg.norm(vector)
    vector.setflags(write=False)
    return vector


@pytest.fixture
def eigen_dienst(monkeypatch):
    """Onze resolver met één bekende claim, zodat het matched-pad geraakt wordt."""
    config = load_config()
    conn = connect(":memory:")
    init_schema(conn)
    zee_id = claim_id_for_text(BEKENDE_TEKST)
    conn.execute(
        "INSERT INTO claim (claim_id, canonical_text, language) VALUES (?, ?, 'nl')",
        (zee_id, BEKENDE_TEKST),
    )
    conn.execute(
        "INSERT INTO factcheck (claim_id, publisher, verdict_normalized,"
        " verdict_original, url, review_date, language) VALUES"
        " (?, 'Nieuwscheckers', 'onwaar', 'Onjuist',"
        " 'https://example.org/zee', '2024-03-14', 'nl')",
        (zee_id,),
    )
    conn.commit()

    zee = _eenheid([1.0, 0.0, 0.0])
    save_text_fingerprint(
        conn, zee_id, TextFingerprint(zee, config.model_versions.text_embedding)
    )
    richtingen = {BEKENDE_TEKST: zee, ONBEKENDE_TEKST: _eenheid([0.0, 0.0, 1.0])}

    def nep_fingerprint(text, model_version):
        return TextFingerprint(
            richtingen.get(text, _eenheid([0.0, 1.0, 0.0])), model_version
        )

    monkeypatch.setattr(api, "fingerprint_text", nep_fingerprint)
    api.app.dependency_overrides[api.get_conn] = lambda: conn
    yield TestClient(api.app)
    api.app.dependency_overrides.clear()
    conn.close()


def test_our_own_resolver_passes_every_obligation(eigen_dienst):
    rapport = controleer_resolver(
        eigen_dienst, proeven=[Proef("bekend", BEKENDE_TEKST)]
    )
    assert rapport.gefaald == (), rapport.rapport()
    assert rapport.conform


def test_our_own_resolver_leaves_nothing_unobserved(eigen_dienst):
    """Een groen rapport met blinde vlekken is geen bewijs (§8).

    Eén blinde vlek is echt: niets in v1 produceert `assessed` — eigen
    AI-oordeel staat op de Won't-lijst (B3). Verplichting 3 is tegen deze
    resolver dus niet te toetsen, en het rapport hoort dat te zeggen in
    plaats van een vinkje te geven. Al het andere moet aan bod komen.
    """
    rapport = controleer_resolver(
        eigen_dienst, proeven=[Proef("bekend", BEKENDE_TEKST)]
    )
    blind = {u.verplichting for u in rapport.niet_waargenomen}
    assert blind == {3}, rapport.rapport()
    assert not rapport.volledig


def test_our_own_resolver_says_when_a_translation_made_the_match(eigen_dienst, monkeypatch):
    """Verplichting 10 tegen onze eigen dienst: een proef die alleen via een
    vertaling van de claim matcht, en een ontdekking die die vertalingen noemt."""
    config = load_config()
    api.app.dependency_overrides[api.get_config] = lambda: dataclasses.replace(
        config, varianten=VariantSettings(in_resolver=True))
    conn = api.app.dependency_overrides[api.get_conn]()
    richting = _eenheid([0.0, 1.0, 1.0])
    save_variant(conn, claim_id_for_text(BEKENDE_TEKST), "en", VERTAALDE_TEKST, "claude-haiku-5-5",
                 "vertalingen-v1", TextFingerprint(richting, config.model_versions.text_embedding))
    conn.commit()
    vorige = api.fingerprint_text
    monkeypatch.setattr(api, "fingerprint_text", lambda tekst, versie: (
        TextFingerprint(richting, versie) if tekst == VERTAALDE_TEKST else vorige(tekst, versie)))

    rapport = controleer_resolver(
        eigen_dienst, proeven=[Proef("bekend", BEKENDE_TEKST), Proef("vertaling", VERTAALDE_TEKST)]
    )
    assert rapport.gefaald == (), rapport.rapport()
    standen = {u.verplichting: u.stand for u in rapport.uitslagen}
    assert standen[10] == GESLAAGD
    assert {u.verplichting for u in rapport.niet_waargenomen} == {3}


# --------------------------------------------------------------------------
# Opzettelijk niet-conforme resolvers
# --------------------------------------------------------------------------

DREMPELS = {
    "text_match": 0.92,
    "text_related": 0.80,
    "image_same": 31,
    "text_match_crosslingual": 0.85,
    "cluster_same": 0.93,
}
BEWIJS = {
    "checks": [
        {
            "publisher": "Stub Checkers",
            "verdict_normalized": "onwaar",
            "verdict_original": "Onjuist",
            "url": "https://example.org/stub",
            "review_date": "2024-03-14",
            "language": "nl",
        }
    ],
    "check_count": 1,
    "publisher_count": 1,
    "languages": ["nl"],
    "oldest_date": "2024-03-14",
}
CLAIM = {"id": claim_id_for_text(BEKENDE_TEKST), "text": BEKENDE_TEKST,
         "cluster_size": 1}
VARIANTENSET = {"generator": "stub-vertaler-1", "prompt": "stub-v1", "languages": ["en", "pt"],
                "count": 2}
VIA = {"language": "en", "generator": "stub-vertaler-1", "prompt": "stub-v1"}
# Gebreken die alleen te zien zijn bij een resolver die varianten aankondigt.
_MET_AANKONDIGING = {"onvolledige_via", "via_zonder_claim", "via_in_onaangekondigde_taal"}


def nepresolver(defect: str | None = None, varianten: bool = False) -> FastAPI:  # noqa: C901
    """Een geloofwaardige resolver met precies één gebrek. Met `varianten`
    zoekt hij ook via vertalingen, kondigt die aan en meldt `via` bij elke
    treffer."""
    app = FastAPI()
    eerder_gezien: set[str] = set()
    kondigt_aan = varianten or defect in _MET_AANKONDIGING

    @app.get("/.well-known/doublecheck")
    async def ontdekking():  # noqa: ANN202
        document = {
            "protocol": "0.1",
            "schemes": {"image": [{"id": "stub-beeld-v1", "bits": 256,
                                   "encoding": "hex"}], "text": []},
            "thresholds": dict(DREMPELS),
            "scope": {"markets": ["nl"], "languages": ["nl"], "claims": 1,
                      "newest_check": "2024-03-14"},
            "resolver": {"id": "stub.example", "name": "Stubresolver"},
            "claim_id": {"algorithm": "sha256",
                         "preprocessing": ["strip", "collapse-whitespace", "casefold"],
                         "hex_chars": 16},
            "variants": [dict(VARIANTENSET)] if kondigt_aan else [],
        }
        if defect == "ontdekking_zonder_varianten":
            del document["variants"]
        if defect == "geen_claimafleiding":
            del document["claim_id"]
        if defect == "ontdekking_zonder_scope":
            del document["scope"]
        return document

    @app.post("/resolve")
    async def resolve(request: Request):  # noqa: ANN202
        body = await request.json()
        if "image_fingerprint" in body:
            schema = (body["image_fingerprint"] or {}).get("scheme")
            if schema != "stub-beeld-v1" and defect != "vreemd_schema_geslikt":
                raise HTTPException(status_code=409, detail=f"onbekend schema {schema!r}")
            # Bij het defect: gewoon antwoorden alsof er niets aan de hand is.
            return {
                "resolver": "stub.example",
                "category": "none", "claim": None, "similarity": None,
                "relation": None, "matched_on": [], "observed_sources": [],
                "thresholds": dict(DREMPELS),
                "schemes_used": {"image": "stub-beeld-v1"}, "evidence": None,
            }
        tekst = str(body.get("text", ""))
        matcht = "bekend" in tekst
        if defect == "bewaart":
            if tekst in eerder_gezien:
                matcht = True
            eerder_gezien.add(tekst)
        if defect == "dwingbaar" and body.get("force_match"):
            matcht = True

        categorie = "matched" if matcht else "none"
        similarity = 0.97 if matcht else 0.11
        if defect == "onder_drempel" and matcht:
            similarity = 0.41
        if defect == "assessed_als_matched" and matcht:
            categorie = "assessed"

        antwoord = {
            "resolver": "stub.example",
            "category": categorie,
            "claim": dict(CLAIM) if matcht else None,
            "similarity": similarity,
            "relation": None,
            "matched_on": ["tekst"] if matcht else [],
            "observed_sources": [],
            "thresholds": dict(DREMPELS),
            "schemes_used": {"text": "stub-tekst-v1", "image": "stub-beeld-v1"},
            "evidence": dict(BEWIJS) if matcht else None,
        }
        if defect == "waarheidspercentage":
            antwoord["truth_probability"] = 0.83
        if defect == "geen_schema":
            del antwoord["schemes_used"]
        if defect == "geen_drempels":
            del antwoord["thresholds"]
        if defect == "naamloze_resolver":
            del antwoord["resolver"]
        if defect == "verzonnen_claim_id" and antwoord["claim"]:
            antwoord["claim"] = {**CLAIM, "id": "willekeurig-42"}
        if defect == "geen_bronnen" and antwoord["evidence"]:
            antwoord["evidence"] = {**BEWIJS, "checks": []}
        if defect == "consensus_schatting" and antwoord["evidence"]:
            antwoord["evidence"] = {**BEWIJS, "check_count": "veel"}
        if matcht and (varianten or defect == "verzwegen_variant"):
            antwoord["via"] = dict(VIA)
        if matcht and defect == "onvolledige_via":
            antwoord["via"] = {"language": "en"}
        if matcht and defect == "via_in_onaangekondigde_taal":
            antwoord["via"] = {**VIA, "language": "fr"}
        if not matcht and defect == "via_zonder_claim":
            antwoord["via"] = dict(VIA)
        return antwoord

    return app


def _stub_rapport(defect, varianten=False):
    with TestClient(nepresolver(defect, varianten)) as client:
        return controleer_resolver(client, proeven=[Proef("bekend", "iets bekends")])


def test_a_flawless_stub_is_accepted():
    """IJkpunt: zonder gebrek moet de stub erdoor, anders meet de suite ruis."""
    rapport = _stub_rapport(None)
    assert rapport.gefaald == (), rapport.rapport()


@pytest.mark.parametrize(
    "defect,verplichting",
    [
        ("waarheidspercentage", 1),
        ("onder_drempel", 2),
        ("dwingbaar", 2),
        ("assessed_als_matched", 3),
        ("bewaart", 4),
        ("geen_bronnen", 5),
        ("consensus_schatting", 6),
        ("geen_schema", 7),
        ("geen_drempels", 8),
        # Nieuw sinds #11.1: de ontdekking uit §3 en de tweede helft van §2.7.
        ("ontdekking_zonder_scope", 0),
        ("vreemd_schema_geslikt", 7),
        # Nieuw sinds #11.3: wat federatie draagt.
        ("naamloze_resolver", 9),
        ("verzonnen_claim_id", 9),
        ("geen_claimafleiding", 9),
        # Nieuw sinds #25.17: een treffer langs een vertaling zegt dat.
        ("ontdekking_zonder_varianten", 10),
        ("verzwegen_variant", 10),
        ("onvolledige_via", 10),
        ("via_zonder_claim", 10),
        ("via_in_onaangekondigde_taal", 10),
    ],
)
def test_suite_catches_each_broken_obligation(defect, verplichting):
    rapport = _stub_rapport(defect)
    assert not rapport.conform, f"gebrek '{defect}' bleef onopgemerkt"
    geraakt = {uitslag.verplichting for uitslag in rapport.gefaald}
    assert verplichting in geraakt, (
        f"gebrek '{defect}' moest verplichting {verplichting} raken, "
        f"maar raakte {sorted(geraakt)}\n{rapport.rapport()}"
    )


@pytest.mark.parametrize("varianten", [False, True])
def test_a_resolver_that_announces_its_variants_and_names_them_passes(varianten):
    """Zonder varianten: een lege lijst in de ontdekking en nooit `via`. Met
    varianten: aangekondigd, en elke treffer langs een variant zegt dat."""
    rapport = _stub_rapport(None, varianten=varianten)
    assert rapport.gefaald == (), rapport.rapport()
    assert {u.verplichting: u.stand for u in rapport.uitslagen}[10] == GESLAAGD


def test_announced_variants_without_a_probe_through_them_stay_unobserved():
    """Een resolver die varianten aankondigt maar in deze run nooit langs
    een variant matchte, heeft `via` niet laten zien: een vraagteken."""
    with TestClient(nepresolver(None, varianten=True)) as client:
        rapport = controleer_resolver(client, proeven=[Proef("vreemd", "hier matcht niets aan")])
    assert {u.verplichting: u.stand for u in rapport.uitslagen}[10] == NIET_WAARGENOMEN
    assert rapport.conform


def test_an_unobserved_check_never_counts_as_passed():
    """Nooit `matched` gezien betekent niet dat de matched-regels gelden."""
    with TestClient(nepresolver(None)) as client:
        rapport = controleer_resolver(
            client, proeven=[Proef("vreemd", "hier matcht niets aan")]
        )
    standen = {u.verplichting: u.stand for u in rapport.uitslagen}
    assert standen[5] == NIET_WAARGENOMEN
    assert standen[6] == NIET_WAARGENOMEN
    assert not rapport.volledig
    assert rapport.conform, "niet-waargenomen is geen overtreding"


def test_a_probe_file_may_carry_its_provenance():
    """Proeven uit een CC BY-corpus dragen hun naamsvermelding mee (#15.2):
    een object met `_meta` en `probes`. Een kale lijst blijft werken. De
    sleutels zijn Engels: dit gereedschap is voor andere resolvers."""
    from conformance.__main__ import lees_proeven

    kaal = [{"name": "a", "text": "a known claim"}]
    assert lees_proeven(kaal) == lees_proeven({"_meta": "provenance", "probes": kaal}) == [Proef("a", "a known claim")]
    eigen = json.loads((pathlib.Path(__file__).resolve().parent.parent / "deploy" / "conformantie-proeven.json")
                       .read_text(encoding="utf-8"))
    assert "CC BY" in eigen["_meta"]
    assert "variant-en" in [p.naam for p in lees_proeven(eigen)]
    # CC BY vraagt naamsvermelding per tekst: elke corpusproef noemt zijn bron.
    for proef in eigen["probes"]:
        if proef["name"].startswith("corpusclaim"):
            assert proef["source"]["publisher"] and proef["source"]["fact_check"].startswith("https://")


# --------------------------------------------------------------------------
# Losmaken van de implementatie
# --------------------------------------------------------------------------


def test_the_suite_does_not_import_the_implementation():
    """`conformance` mag `doublecheck` niet kennen, anders test hij zichzelf."""
    wortel = pathlib.Path(conformance.__file__).parent
    overtredingen = []
    for pad in sorted(wortel.rglob("*.py")):
        boom = ast.parse(pad.read_text(encoding="utf-8"))
        for knoop in ast.walk(boom):
            namen = []
            if isinstance(knoop, ast.Import):
                namen = [alias.name for alias in knoop.names]
            elif isinstance(knoop, ast.ImportFrom):
                namen = [knoop.module or ""]
            for naam in namen:
                if naam.split(".")[0] == "doublecheck":
                    overtredingen.append(f"{pad.name}:{knoop.lineno} {naam}")
    assert overtredingen == [], (
        "conformantiesuite importeert de implementatie: " + ", ".join(overtredingen)
    )


def test_the_report_and_its_json_are_english():
    """PO 2026-10-13: wat buiten Factiz gelezen wordt, is Engels; de suite is
    gereedschap voor andere resolvers."""
    from conformance.__main__ import als_json
    from conformance.suite import GEFAALD, Rapport, Uitslag

    rapport = Rapport((Uitslag(2, "never `matched` below its own threshold", GEFAALD, "x"),))
    assert set(als_json(rapport)) == {"conformant", "complete", "results", "limitations"}
    assert set(als_json(rapport)["results"][0]) == {"obligation", "name", "status", "note"}
    tekst = rapport.rapport()
    assert "NOT CONFORMANT" in tekst and "What this suite cannot observe" in tekst
    for nederlands in ("verplichting", "geschonden", "niet waargenomen", "geslaagd", "ontdekking"):
        assert nederlands not in tekst.lower(), nederlands
