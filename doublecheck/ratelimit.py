"""Per-IP rate-limiting als token-bucket *(PLAN.md #20.2, B12, PROTOCOL §11.3)*.

Waarom in-proces en niet op de reverse proxy: het besluit is één instantie
draaien (B13, PROTOCOL §11.3). Zolang dat zo is, is een token-bucket per IP in
het proces genoeg — en het beschermt de dienst vandaag, in de repo, met een
test. Twee grenzen die dat wél vragen staan op de roadmap:

- **Meerdere werkers of instanties.** Elke werker heeft zijn eigen emmer, dus de
  effectieve grens is N× de ingestelde. Voor een cross-instantie-grens is een
  gedeelde store nodig (Redis-token-bucket) of rate-limiting op de reverse proxy.
- **Achter een reverse proxy** ziet dit de proxy-IP, niet de echte client — dan
  telt iedereen als één. De proxy is dan óók de juiste plek, want die ziet de
  echte IP's (`X-Forwarded-For` met een vertrouwde-proxy-config).

Beide horen in de infrastructuur; deze module is de sufficient-now-oplossing voor
de directe, enkelvoudige instantie. De grens komt uit config (DR6).
"""

from __future__ import annotations

import math
import time
from collections import OrderedDict

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse


class RateLimiter:
    """Token-bucket per client.

    De emmer vat `burst` tokens en vult met `requests_per_minute / 60` tokens per
    seconde. Elk verzoek kost één token; is de emmer leeg, dan komt er een
    wachttijd terug. Een injecteerbare klok maakt het deterministisch toetsbaar.
    """

    def __init__(
        self,
        requests_per_minute: int,
        burst: int,
        *,
        enabled: bool = True,
        max_clients: int = 10_000,
        klok=time.monotonic,
    ) -> None:
        if requests_per_minute <= 0 or burst <= 0:
            raise ValueError("requests_per_minute en burst moeten positief zijn")
        self.enabled = enabled
        self._per_seconde = requests_per_minute / 60.0
        self._capaciteit = float(burst)
        self._max_clients = max_clients
        self._klok = klok
        # client -> (tokens, laatste_tijd). OrderedDict zodat de oudste eruit
        # valt als de tabel vol raakt — een emmer vergeten kost hooguit dat een
        # inactieve client vers begint (§54).
        self._emmers: "OrderedDict[str, tuple[float, float]]" = OrderedDict()

    def toestaan(self, client: str) -> tuple[bool, int]:
        """`(toegestaan, retry_after_seconden)`. Bij toestaan is de wachttijd 0."""
        if not self.enabled:
            return True, 0

        nu = self._klok()
        tokens, laatst = self._emmers.get(client, (self._capaciteit, nu))
        tokens = min(self._capaciteit, tokens + (nu - laatst) * self._per_seconde)

        if tokens >= 1.0:
            tokens -= 1.0
            toegestaan, retry = True, 0
        else:
            toegestaan = False
            retry = max(1, math.ceil((1.0 - tokens) / self._per_seconde))

        self._emmers[client] = (tokens, nu)
        self._emmers.move_to_end(client)
        if len(self._emmers) > self._max_clients:
            self._emmers.popitem(last=False)
        return toegestaan, retry

    def aantal_clients(self) -> int:
        return len(self._emmers)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Weigert boven de grens met 429 en een `Retry-After`-kop."""

    def __init__(self, app, limiter: RateLimiter) -> None:
        super().__init__(app)
        self._limiter = limiter

    async def dispatch(self, request, call_next):
        client = request.client.host if request.client else "onbekend"
        toegestaan, retry = self._limiter.toestaan(client)
        if not toegestaan:
            return JSONResponse(
                {"detail": f"too many requests; try again in {retry}s"},
                status_code=429,
                headers={"Retry-After": str(retry)},
            )
        return await call_next(request)
