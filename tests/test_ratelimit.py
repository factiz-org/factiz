"""Per-IP rate-limiting (PLAN.md #20.2, BENCHMARK §54).

De pixelgrens (§54) en de OCR-timeout (#20.1) begrenzen wat één verzoek kost;
niets begrensde nog hoevéél verzoeken één bron doet. Een stroom legale
schermafbeeldingen van één IP verzadigt de werkers net zo goed.

PO-besluit 2026-09-01: het Chrome-plugin-scenario (dat een API-sleutel per
afnemer zou vergen — en een sleutel is een account, tegen B12) is van tafel. Dus
**per-IP volstaat**, en voor de "één instantie"-keuze uit B13/PROTOCOL §11.3 is
een in-proces token-bucket genoeg. De cross-instantie-variant (gedeelde store /
reverse proxy) staat op de roadmap.

De limiter is pure logica met een injecteerbare klok — deterministisch te toetsen
zonder te slapen. De grens komt uit config (DR6).
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from doublecheck.ratelimit import RateLimiter, RateLimitMiddleware


class _Klok:
    def __init__(self):
        self.nu = 1000.0

    def __call__(self):
        return self.nu

    def verder(self, seconden):
        self.nu += seconden


def test_a_burst_is_allowed_then_the_stream_is_throttled():
    klok = _Klok()
    limiter = RateLimiter(requests_per_minute=60, burst=3, klok=klok)
    # Drie direct achter elkaar mogen (de emmer is vol).
    for i in range(3):
        toegestaan, _ = limiter.toestaan("1.2.3.4")
        assert toegestaan, f"verzoek {i} zou binnen de burst moeten passen"
    # De vierde niet, en hij krijgt een wachttijd mee.
    toegestaan, retry = limiter.toestaan("1.2.3.4")
    assert not toegestaan
    assert retry >= 1


def test_the_bucket_refills_at_the_sustained_rate():
    klok = _Klok()
    limiter = RateLimiter(requests_per_minute=60, burst=1, klok=klok)
    assert limiter.toestaan("ip")[0] is True
    assert limiter.toestaan("ip")[0] is False        # emmer leeg
    klok.verder(1.0)                                  # 60/min = 1 token/sec
    assert limiter.toestaan("ip")[0] is True


def test_each_client_has_its_own_bucket():
    limiter = RateLimiter(requests_per_minute=60, burst=1, klok=_Klok())
    assert limiter.toestaan("a")[0] is True
    assert limiter.toestaan("a")[0] is False
    assert limiter.toestaan("b")[0] is True, "b deelt geen emmer met a"


def test_retry_after_reflects_the_refill_rate():
    limiter = RateLimiter(requests_per_minute=30, burst=1, klok=_Klok())
    limiter.toestaan("ip")
    _, retry = limiter.toestaan("ip")
    # 30/min = 1 token per 2s; een geweigerd verzoek wacht ~2s.
    assert retry == 2


def test_a_disabled_limiter_never_throttles():
    limiter = RateLimiter(requests_per_minute=1, burst=1, enabled=False, klok=_Klok())
    for _ in range(50):
        assert limiter.toestaan("ip") == (True, 0)


def test_memory_stays_bounded_under_many_clients():
    limiter = RateLimiter(requests_per_minute=60, burst=1, max_clients=100, klok=_Klok())
    for n in range(1000):
        limiter.toestaan(f"10.0.0.{n}")
    assert limiter.aantal_clients() <= 100


def test_the_middleware_answers_429_with_a_retry_after_header():
    app = FastAPI()

    @app.get("/ping")
    def ping():
        return {"ok": True}

    app.add_middleware(
        RateLimitMiddleware,
        limiter=RateLimiter(requests_per_minute=60, burst=2),
    )
    client = TestClient(app)
    assert client.get("/ping").status_code == 200
    assert client.get("/ping").status_code == 200
    derde = client.get("/ping")
    assert derde.status_code == 429
    assert int(derde.headers["Retry-After"]) >= 1
    assert "too many requests" in derde.json()["detail"].lower()


def test_a_disabled_middleware_lets_everything_through():
    app = FastAPI()

    @app.get("/ping")
    def ping():
        return {"ok": True}

    app.add_middleware(
        RateLimitMiddleware,
        limiter=RateLimiter(requests_per_minute=1, burst=1, enabled=False),
    )
    client = TestClient(app)
    for _ in range(10):
        assert client.get("/ping").status_code == 200
