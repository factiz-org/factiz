"""Kritieke afdwinging DR9 (E6.S3, PLAN.md #6.3).

Na een betwisting zónder expliciete toestemming bestaat er nergens een kopie
van het artefact: niet in de database, niet op schijf, niet in een log, niet
bij een externe dienst. Dit is de enige route waar bewaren überhaupt mág, en
dus de plek waar de belofte uit B11 het makkelijkst kan breken.
"""

import io
import logging
import socket

import pytest
from fastapi.testclient import TestClient

import doublecheck.api as api
from doublecheck.config import load_config
from doublecheck.embedding import fingerprint_text
from doublecheck.storage import connect, init_schema
from tests.beelden import kop_screenshot
from tests.test_dr3 import _bestanden, _lekplekken, eigen_tmp, schendingen  # noqa: F401 (fixture)

# Uniek genoeg om overal op te kunnen zoeken — in tekst én via OCR in beeld.
KANARIE = "Kanarie Vlissingen ontsnapte uit Winterswijk"
BETWISTING = "De resolver koppelde dit aan een claim die er niets mee te maken heeft."


@pytest.fixture
def client_en_conn():
    conn = connect(":memory:")
    init_schema(conn)
    api.app.dependency_overrides[api.get_conn] = lambda: conn
    yield TestClient(api.app), conn
    api.app.dependency_overrides.clear()
    conn.close()


def _beeld_bytes():
    buffer = io.BytesIO()
    kop_screenshot([KANARIE]).save(buffer, format="PNG")
    return buffer.getvalue()


def _merkers():
    return (KANARIE.encode("utf-8"), _beeld_bytes())


def _controleer_alle_kanalen(conn, caplog, plekken, voor, eigen):
    # 1. Schijf: in de eigen mappen elk nieuw bestand, in de gedeelde alleen
    # een bestand met de kanarie of de beeldbytes (zie test_dr3).
    assert schendingen(plekken, voor, eigen, _merkers()) == []

    # 2. Logs.
    for record in caplog.records:
        bericht = record.getMessage()
        assert KANARIE not in bericht
        assert "Kanarie" not in bericht

    # 3. Database: geen artefactinhoud, en geen enkele rij mét artefact.
    dump = "\n".join(conn.iterdump())
    assert KANARIE not in dump
    assert "Kanarie" not in dump
    assert "Vlissingen" not in dump
    met_artefact = conn.execute(
        "SELECT COUNT(*) AS n FROM dispute WHERE artifact_bytes IS NOT NULL"
    ).fetchone()["n"]
    assert met_artefact == 0

    # 4. Externe dienst: afgedwongen door de socket-ban in de test zelf.


def test_no_artifact_anywhere_without_consent(client_en_conn, caplog, eigen_tmp):
    client, conn = client_en_conn
    plekken = _lekplekken(eigen_tmp)

    # Model vooraf laden: dat is infrastructuur, geen artefactverwerking. Het
    # koud laden legt één verbinding met de modelhub (zie de test hieronder);
    # daarna hoort er geen enkele uitgaande verbinding meer te zijn.
    fingerprint_text("opwarmen", load_config().model_versions.text_embedding)

    voor = {plek: _bestanden(plek) for plek in plekken}

    echte_connect = socket.socket.connect
    lokaal = {"127.0.0.1", "::1", "localhost", "testserver"}

    def alleen_lokaal(self, adres, *args, **kwargs):
        host = adres[0] if isinstance(adres, tuple) else adres
        if isinstance(host, str) and host not in lokaal:
            raise AssertionError(f"betwisting belde een externe dienst: {host} (DR9)")
        return echte_connect(self, adres, *args, **kwargs)

    socket.socket.connect = alleen_lokaal
    try:
        with caplog.at_level(logging.DEBUG):
            tekst = client.post("/dispute", json={
                "text": KANARIE,
                "disputed_category": "matched",
                "dispute_text": BETWISTING,
            })
            beeld = client.post(
                "/dispute",
                files={"image": ("kop.png", _beeld_bytes(), "image/png")},
                data={"disputed_category": "related", "dispute_text": BETWISTING},
            )
    finally:
        socket.socket.connect = echte_connect

    assert tekst.status_code == 200
    assert beeld.status_code == 200
    assert tekst.json()["stored_artifact"] is False
    assert beeld.json()["stored_artifact"] is False

    _controleer_alle_kanalen(conn, caplog, plekken, voor, eigen_tmp)


def test_with_consent_the_artifact_lives_only_in_the_database(client_en_conn, caplog, eigen_tmp):
    """E6.S3-AC7: bewaren mag, maar uitsluitend in de database.

    Met toestemming bestaat het artefact — dat is de uitzondering die B11
    toestaat. Maar het mag nergens ánders terechtkomen, zodat verwijderen één
    handeling blijft en er geen kopie kan achterblijven.
    """
    client, conn = client_en_conn
    plekken = _lekplekken(eigen_tmp)
    fingerprint_text("opwarmen", load_config().model_versions.text_embedding)
    voor = {plek: _bestanden(plek) for plek in plekken}

    with caplog.at_level(logging.DEBUG):
        respons = client.post("/dispute", json={
            "text": KANARIE,
            "disputed_category": "matched",
            "dispute_text": BETWISTING,
            "consent_to_store_artifact": True,
        })

    assert respons.status_code == 200
    assert respons.json()["stored_artifact"] is True

    # In de database: precies één artefact, met alle drie de DR9-voorwaarden.
    rij = conn.execute(
        "SELECT artifact_bytes, consent_at, artifact_expires_at, deletion_key_hash"
        " FROM dispute"
    ).fetchone()
    assert rij["artifact_bytes"].decode("utf-8") == KANARIE
    assert rij["consent_at"] and rij["artifact_expires_at"] and rij["deletion_key_hash"]

    # Maar nergens anders: niet op schijf, niet in logs.
    assert schendingen(plekken, voor, eigen_tmp, _merkers()) == []
    for record in caplog.records:
        assert "Kanarie" not in record.getMessage()


def test_dispute_text_is_kept_but_artefact_is_not(client_en_conn):
    """De analysewaarde blijft, het artefact niet — dat is de hele afspraak."""
    client, conn = client_en_conn

    client.post("/dispute", json={
        "text": KANARIE,
        "disputed_category": "matched",
        "dispute_text": BETWISTING,
    })

    rij = conn.execute("SELECT * FROM dispute").fetchone()
    assert rij["dispute_text"] == BETWISTING
    assert rij["text_payload"] is not None
    assert rij["artifact_bytes"] is None


def test_warm_model_makes_no_outbound_connection(client_en_conn):
    """Bevinding 2026-08-28, omgezet in een garantie.

    Het koud laden van het embeddingmodel legt één verbinding met de
    modelhub (Hugging Face via CloudFront). Er gaat geen artefactinhoud
    doorheen — het is een modelbestandscontrole — maar voor een
    privacy-eerst product hoort een draaiende dienst niet naar buiten te
    bellen. Deze test pint vast dat een wárm proces dat ook niet doet, zodat
    een toekomstige wijziging die per verzoek gaat bellen luid faalt.
    """
    client, _ = client_en_conn
    fingerprint_text("opwarmen", load_config().model_versions.text_embedding)

    naar_buiten = []
    echte_connect = socket.socket.connect
    lokaal = {"127.0.0.1", "::1", "localhost", "testserver"}

    def registreer(self, adres, *args, **kwargs):
        host = adres[0] if isinstance(adres, tuple) else adres
        if isinstance(host, str) and host not in lokaal:
            naar_buiten.append(host)
        return echte_connect(self, adres, *args, **kwargs)

    socket.socket.connect = registreer
    try:
        client.post("/dispute", json={
            "text": KANARIE,
            "disputed_category": "matched",
            "dispute_text": BETWISTING,
        })
        client.post("/resolve", json={"text": KANARIE})
    finally:
        socket.socket.connect = echte_connect

    assert naar_buiten == [], f"uitgaande verbindingen tijdens verzoek: {naar_buiten}"
