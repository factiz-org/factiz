"""Kritieke afdwinging DR3 / E6.S1 (PLAN.md #4.7).

Na een resolve met een afbeelding bestaat er geen kopie van dat artefact op
schijf, in een log, in een cache of bij een externe dienst. Deze test
controleert alle vier na afloop van een echte beeldresolve.
"""

import io
import logging
import socket
import tempfile
import uuid
from pathlib import Path

import pytest

from fastapi.testclient import TestClient

import doublecheck.api as api
from doublecheck.config import load_config
from doublecheck.embedding import fingerprint_text
from doublecheck.storage import connect, init_schema, save_text_fingerprint
from tests.beelden import kop_screenshot

# Uniek genoeg om overal in bestanden en logs op te kunnen zoeken.
GEHEIME_KOP = "Kanarie Zevenbergen ontsnapte uit Doetinchem"


def _artefact_bytes():
    buffer = io.BytesIO()
    kop_screenshot([GEHEIME_KOP]).save(buffer, format="PNG")
    return buffer.getvalue()


@pytest.fixture
def client_en_conn():
    conn = connect(":memory:")
    init_schema(conn)
    config = load_config()
    conn.execute(
        "INSERT INTO claim (claim_id, canonical_text, language)"
        " VALUES ('claim-x', 'Een geheel andere bewering over treinen', 'nl')"
    )
    conn.execute(
        "INSERT INTO factcheck (claim_id, publisher, verdict_normalized,"
        " verdict_original, url, review_date, language)"
        " VALUES ('claim-x', 'Nieuwscheckers', 'onwaar', 'Onjuist',"
        " 'https://nieuwscheckers.nl/treinen', '2024-01-01', 'nl')"
    )
    save_text_fingerprint(
        conn,
        "claim-x",
        fingerprint_text(
            "Een geheel andere bewering over treinen",
            config.model_versions.text_embedding,
        ),
    )
    conn.commit()

    api.app.dependency_overrides[api.get_conn] = lambda: conn
    yield TestClient(api.app), conn
    api.app.dependency_overrides.clear()
    conn.close()


_OVERSLAAN = {".venv", ".git", "__pycache__", ".pytest_cache"}


def _bestanden(directory: Path) -> set[Path]:
    """Bestanden tot één map diep — daar belandt een lek, en het blijft snel."""
    gevonden: set[Path] = set()
    try:
        for item in directory.iterdir():
            if item.name in _OVERSLAAN:
                continue
            if item.is_file():
                gevonden.add(item)
            elif item.is_dir():
                try:
                    gevonden.update(
                        kind for kind in item.iterdir() if kind.is_file()
                    )
                except OSError:
                    continue
    except OSError:
        return set()
    return gevonden


# De gedeelde tijdelijke map van deze machine, vastgelegd vóór een test zijn
# eigen map instelt. Op macOS een map onder /var/folders/…, níét /tmp.
_GEDEELD = Path(tempfile.gettempdir()).resolve()


@pytest.fixture
def eigen_tmp(monkeypatch, tmp_path) -> Path:
    """Een eigen tijdelijke map voor dit proces: wat pytesseract en andere
    bibliotheken via `tempfile` schrijven, landt hier. Daar is elk nieuw
    bestand een lek. De gedeelde mappen zijn van de hele machine; een andere
    OCR-job laat er `tess_*` achter, en daar telt dus alleen een bestand met
    de artefactinhoud."""
    map_ = tmp_path / "proces-tmp"
    map_.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(map_))
    monkeypatch.setenv("TMPDIR", str(map_))
    return map_.resolve()


def _lekplekken(eigen: Path | None = None) -> list[Path]:
    """Alle plausibele plekken waar een artefact zou kunnen belanden."""
    kandidaten = [
        _GEDEELD,
        Path("/tmp"),
        Path("/var/tmp"),
        Path.cwd(),
        Path(__file__).parent.parent,
    ] + ([eigen] if eigen is not None else [])
    unieke: list[Path] = []
    for pad in kandidaten:
        opgelost = pad.resolve()
        if opgelost.is_dir() and opgelost not in unieke:
            unieke.append(opgelost)
    return unieke


# Onze eigen mappen: hier is élk nieuw bestand verdacht, ook een lege.
_EIGEN_MAPPEN = {Path.cwd().resolve(), Path(__file__).parent.parent.resolve()}

# Een lek is nooit groot; alles daarboven openen kost meer dan het oplevert.
_MAX_INSPECTIE = 32 * 1024 * 1024


def _draagt(pad: Path, merkers: tuple[bytes, ...]) -> bool:
    """Bevat dit bestand een van de merkers (de artefactbytes, de kanarie)?"""
    try:
        if pad.stat().st_size > _MAX_INSPECTIE:
            return False
        inhoud = pad.read_bytes()
    except OSError:
        # Onleesbaar voor ons betekent: niet door ons geschreven.
        return False
    return any(m in inhoud for m in merkers)


def _draagt_artefact(pad: Path, artefact: bytes) -> bool:
    """Bevat dit bestand het artefact — als bytes of als leesbare kop?"""
    return _draagt(pad, (artefact, GEHEIME_KOP.encode("utf-8")))


def schendingen(plekken: list[Path], voor: dict, eigen: Path | None, merkers: tuple[bytes, ...]) -> list[str]:
    """Wat er sinds `voor` op schijf bijkwam en een lek is. In onze eigen
    mappen en de eigen tijdelijke map: elk nieuw bestand. In de gedeelde
    mappen: alleen een bestand dat een merker draagt."""
    streng = _EIGEN_MAPPEN | ({eigen} if eigen is not None else set())
    uit = []
    for plek in plekken:
        nieuw = sorted(pad for pad in _bestanden(plek) - voor[plek] if pad.is_file())
        if plek in streng:
            uit += [f"achtergelaten in {plek}: {pad.name}" for pad in nieuw]
        else:
            uit += [f"kopie van het artefact in {plek}: {pad.name}" for pad in nieuw if _draagt(pad, merkers)]
    return uit


def test_no_artifact_persisted_after_resolve(client_en_conn, caplog, eigen_tmp):
    client, conn = client_en_conn
    artefact = _artefact_bytes()
    plekken = _lekplekken(eigen_tmp)

    # Model vooraf laden: dat is infrastructuur, geen artefactverwerking.
    fingerprint_text("opwarmen", load_config().model_versions.text_embedding)

    voor = {plek: _bestanden(plek) for plek in plekken}

    # Alleen naar-buiten-verkeer is verboden; de testclient zelf gebruikt
    # lokale sockets en die moeten blijven werken.
    echte_connect = socket.socket.connect
    lokaal = {"127.0.0.1", "::1", "localhost", "testserver"}

    def alleen_lokaal(self, adres, *args, **kwargs):
        host = adres[0] if isinstance(adres, tuple) else adres
        if isinstance(host, str) and host not in lokaal:
            raise AssertionError(
                f"resolve legde een verbinding met een externe dienst: {host} (DR3)"
            )
        return echte_connect(self, adres, *args, **kwargs)

    socket.socket.connect = alleen_lokaal
    try:
        with caplog.at_level(logging.DEBUG):
            respons = client.post(
                "/resolve",
                files={"image": ("screenshot.png", artefact, "image/png")},
            )
    finally:
        socket.socket.connect = echte_connect

    assert respons.status_code == 200
    assert respons.json()["category"] in {"matched", "related", "assessed", "none"}

    # 1. Schijf: nergens een kopie van het artefact achtergelaten.
    #
    # In onze eigen mappen, en in de eigen tijdelijke map van dit proces, is
    # elk nieuw bestand verdacht; een `tess_*` van onze OCR landt in die
    # laatste. In de gedeelde tijdelijke mappen kan dat niet: /tmp en /var/tmp
    # zijn van de hele machine, en een ander proces dat daar in dit venster
    # iets schrijft (een andere OCR-job) zei niets over ons. Daar geldt een
    # inhoudelijke maat: een lek draagt per definitie de artefactinhoud.
    assert schendingen(plekken, voor, eigen_tmp, (artefact, GEHEIME_KOP.encode("utf-8"))) == []

    # 2. Logs: geen enkele regel die artefactinhoud bevat.
    for record in caplog.records:
        assert GEHEIME_KOP not in record.getMessage()
        assert "Kanarie" not in record.getMessage()

    # 3. Cache/opslag: de database bevat alleen fingerprints, geen artefact.
    dump = "\n".join(conn.iterdump())
    assert GEHEIME_KOP not in dump
    assert "Kanarie" not in dump
    assert "Zevenbergen" not in dump
    soorten = {rij["kind"] for rij in conn.execute("SELECT kind FROM fingerprint")}
    assert soorten <= {"text", "image"}

    # 4. Externe dienst: afgedwongen door de socket-ban hierboven.


def test_library_logging_is_off_at_package_level():
    """DR3-conventie: de kraan zit op bibliotheekniveau, niet per aanroepsite."""
    logger = logging.getLogger("doublecheck")

    assert logger.propagate is False
    assert any(
        isinstance(handler, logging.NullHandler) for handler in logger.handlers
    )


def test_the_disk_guard_actually_catches_a_leaking_resolver(client_en_conn, monkeypatch):
    """Een soepeler controle die niets meer betrapt is geen controle.

    De schijfcontrole werd inhoudelijk in plaats van tellend (zie hierboven),
    omdat /tmp van de hele machine is. Deze test laat de resolver met opzet
    lekken — een kopie van het artefact in de gedeelde tijdelijke map, onder een
    onschuldige naam — en eist dat de controle hem alsnog vindt.
    """
    client, _ = client_en_conn
    artefact = _artefact_bytes()
    gedeeld = _GEDEELD
    assert gedeeld not in _EIGEN_MAPPEN, "deze proef zegt niets in onze eigen map"

    echte_ocr = api.extract_text
    lek = gedeeld / "een-heel-gewone-naam.bin"

    def lekkende_ocr(inhoud, instellingen):
        lek.write_bytes(inhoud)
        return echte_ocr(inhoud, instellingen)

    monkeypatch.setattr(api, "extract_text", lekkende_ocr)
    voor = _bestanden(gedeeld)
    try:
        respons = client.post(
            "/resolve", files={"image": ("screenshot.png", artefact, "image/png")}
        )
        assert respons.status_code == 200

        nieuw = [pad for pad in _bestanden(gedeeld) - voor if pad.is_file()]
        betrapt = [pad for pad in nieuw if _draagt_artefact(pad, artefact)]
        assert betrapt == [lek], (
            "de schijfcontrole zag een weggeschreven artefact over het hoofd"
        )
    finally:
        lek.unlink(missing_ok=True)


def test_a_file_another_process_writes_to_shared_tmp_is_not_our_leak(eigen_tmp):
    """De gedeelde tijdelijke map is van de hele machine. Een andere OCR-job
    laat daar `tess_*` achter terwijl wij testen; dat zei niets over ons, en
    maakte DR3 en DR9 rood zodra er op de achtergrond OCR liep."""
    plekken = _lekplekken(eigen_tmp)
    voor = {plek: _bestanden(plek) for plek in plekken}
    vreemd = _GEDEELD / f"tess_vreemd_{uuid.uuid4().hex}_input.PNG"
    vreemd.write_bytes(b"een beeld van een ander proces")
    try:
        assert schendingen(plekken, voor, eigen_tmp, (_artefact_bytes(), GEHEIME_KOP.encode())) == []
    finally:
        vreemd.unlink(missing_ok=True)


def test_a_tesseract_leftover_of_our_own_process_is_still_caught(eigen_tmp):
    """Wat ons proces via `tempfile` schrijft (pytesseract doet dat), landt in
    de eigen map, en daar is elk achtergebleven bestand een lek."""
    plekken = _lekplekken(eigen_tmp)
    voor = {plek: _bestanden(plek) for plek in plekken}
    with tempfile.NamedTemporaryFile(prefix="tess_", suffix="_input.PNG", delete=False) as f:
        f.write(b"een opnieuw gecodeerde kopie")
    assert Path(f.name).resolve().parent == eigen_tmp
    gevonden = schendingen(plekken, voor, eigen_tmp, (_artefact_bytes(),))
    assert len(gevonden) == 1 and "tess_" in gevonden[0]
