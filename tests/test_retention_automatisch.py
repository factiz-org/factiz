"""De bewaartermijn wordt automatisch afgedwongen (PLAN.md #6.9).

Zonder dit is de belofte van B11 niet meer waard dan een handmatige handeling
die niemand gepland heeft — de bevinding uit de AVG-toets van etappepoort 6.
"""

from datetime import datetime, timedelta, timezone

import numpy as np
import pytest
from fastapi.testclient import TestClient

import doublecheck.api as api
from doublecheck.config import load_config
from doublecheck.dispute import record_dispute
from doublecheck.embedding import TextFingerprint
from doublecheck.storage import connect, init_schema


def _verlopen_betwisting(pad):
    conn = connect(pad)
    init_schema(conn)
    vector = np.array([0.6, 0.8], dtype=np.float32)
    vector.setflags(write=False)
    record_dispute(
        conn,
        disputed_category="matched",
        dispute_text="verkeerde koppeling",
        text_fingerprint=TextFingerprint(vector=vector, model_version="testmodel-v1"),
        artifact=b"artefact dat allang verlopen is",
        artifact_mime="text/plain",
        consent=True,
        retention_days=90,
        now=datetime.now(timezone.utc) - timedelta(days=200),
    )
    conn.close()


def test_expired_artifact_is_swept_at_startup(tmp_path, monkeypatch):
    pad = str(tmp_path / "start.db")
    _verlopen_betwisting(pad)
    monkeypatch.setenv("DOUBLECHECK_DB", pad)

    conn = connect(pad)
    assert conn.execute(
        "SELECT artifact_bytes FROM dispute"
    ).fetchone()["artifact_bytes"] is not None
    conn.close()

    # De applicatie opstarten dwingt de bewaartermijn af.
    with TestClient(api.app):
        pass

    conn = connect(pad)
    rij = conn.execute("SELECT artifact_bytes, dispute_text FROM dispute").fetchone()
    conn.close()
    assert rij["artifact_bytes"] is None
    assert rij["dispute_text"] == "verkeerde koppeling"


def test_config_exposes_sweep_interval():
    """Ook het interval is configuratie, geen hardcoded waarde (DR6)."""
    config = load_config()

    assert config.retention.sweep_interval_hours > 0


def test_periodic_sweep_is_running_while_the_app_runs(tmp_path, monkeypatch):
    monkeypatch.setenv("DOUBLECHECK_DB", str(tmp_path / "loop.db"))

    with TestClient(api.app):
        taak = getattr(api.app.state, "sweep_taak", None)
        assert taak is not None, "geen periodieke opruimtaak gestart"
        assert not taak.done()

    # Na afsluiten hoort de taak netjes gestopt te zijn.
    assert taak.cancelled() or taak.done()


@pytest.mark.anyio
async def test_sweep_loop_repeats_until_cancelled(tmp_path):
    """De lus draait herhaaldelijk en stopt netjes op annulering."""
    import asyncio

    pad = str(tmp_path / "herhaal.db")
    conn = connect(pad)
    init_schema(conn)
    conn.close()

    rondes = []
    taak = asyncio.create_task(
        api._sweep_lus(pad, interval_seconden=0.01, na_ronde=rondes.append)
    )
    await asyncio.sleep(0.06)
    taak.cancel()
    try:
        await taak
    except asyncio.CancelledError:
        pass

    assert len(rondes) >= 2, rondes


@pytest.fixture
def anyio_backend():
    return "asyncio"
