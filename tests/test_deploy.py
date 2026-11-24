"""De deploy als code (PLAN #23.2, B21).

De bestanden in deploy/ zijn het draaiboek uit RUNBOOK §Deploy, uitvoerbaar.
Deze guards houden ze gelijk aan wat elders beloofd is: de OCR-talen uit
config, de werkergrenzen uit §55, de poort die Caddy en gunicorn delen, en
de privacybelofte dat accesslogs uitstaan.
"""

import pathlib
import re
import subprocess

import pytest

from doublecheck.config import load_config

WORTEL = pathlib.Path(__file__).resolve().parent.parent
DEPLOY = WORTEL / "deploy"
PROVISION = (DEPLOY / "provision.sh").read_text(encoding="utf-8")
UNIT = (DEPLOY / "factiz.service").read_text(encoding="utf-8")
CADDY = (DEPLOY / "Caddyfile").read_text(encoding="utf-8")


def test_the_provisioning_script_parses():
    uitkomst = subprocess.run(
        ["bash", "-n", str(DEPLOY / "provision.sh")], capture_output=True, text=True
    )
    assert uitkomst.returncode == 0, uitkomst.stderr


def test_tesseract_packages_follow_the_ocr_config():
    """RUNBOOK: wie een taal in config bijzet, zet hier het apt-pakket bij."""
    talen = load_config().ocr.languages.split("+")
    for taal in talen:
        if taal == "eng":
            continue  # zit in het basispakket tesseract-ocr
        assert f"tesseract-ocr-{taal}" in PROVISION, taal


def test_gunicorn_and_caddy_share_one_port_and_the_section_55_timeout():
    poort = re.search(r"-b 127\.0\.0\.1:(\d+)", UNIT)
    assert poort, "geen bind-adres in de unit"
    assert f"reverse_proxy 127.0.0.1:{poort.group(1)}" in CADDY
    assert "--timeout 30" in UNIT          # §55: backstop op een hangende werker
    assert "UvicornWorker" in UNIT
    assert "DOUBLECHECK_DB=" in UNIT


def test_access_logs_stay_off_as_the_privacy_page_promises():
    """De privacypagina (op het platform, `over.html`): geen log koppelt een IP-adres aan wat er gecheckt
    werd. Caddy logt alleen met een log-directief, gunicorn alleen met
    --access-logfile; beide ontbreken, en dat is geen vergeetachtigheid."""
    def zonder_commentaar(tekst: str) -> str:
        return "\n".join(r for r in tekst.splitlines() if not r.lstrip().startswith("#"))

    assert not re.search(r"^\s*log\b", zonder_commentaar(CADDY), flags=re.M)
    assert "--access-logfile" not in zonder_commentaar(UNIT)
    assert "--access-logfile" not in zonder_commentaar(PROVISION)


def test_the_script_serves_the_b21_line():
    """B21: TLS op de machine, geen VS-proxy, retention als cron, en de
    server clonet de (nog private) repo met een deploy key."""
    assert "try.factiz.org" in CADDY
    assert "doublecheck.retention" in PROVISION
    assert "ufw" in PROVISION
    assert "ssh-keygen" in PROVISION           # deploy key voor de private clone
    assert "github.com/factiz-org/factiz" in PROVISION


def test_every_pack_in_the_script_table_and_osd_are_provisioned():
    """#25.21: de OCR kiest per schrift een pakket. Een pakket dat op de server
    ontbreekt laat tesseract falen op precies de beelden waar het om ging."""
    ocr = load_config().ocr
    talen = {t for pakketten in ocr.schriften.values() for t in pakketten.split("+")}
    for taal in sorted(talen - {"eng"}):
        assert f"tesseract-ocr-{taal.replace('_', '-')}" in PROVISION, taal
    if ocr.schriften:
        assert "tesseract-ocr-osd" in PROVISION


@pytest.mark.echte_config
def test_the_judge_weights_reach_the_server_before_the_service_starts():
    """#30.3: de gewichten van de rechter zitten niet in git. Staat hij aan,
    dan noemt het draaiboek de kopie naar het pad uit config, en start
    provision.sh de dienst niet zonder die gewichten (anders weigert elke
    tekstvraag, DR6)."""
    rechter = load_config().rechter
    if not rechter.aan:
        return
    runbook = (WORTEL / "docs" / "RUNBOOK.md").read_text(encoding="utf-8")
    assert f"{rechter.pad} factiz@<ip>:/home/factiz/app/{rechter.pad.rsplit('/', 1)[0]}/" in runbook
    assert "model.safetensors" in PROVISION
    assert '"rechter"' in PROVISION
