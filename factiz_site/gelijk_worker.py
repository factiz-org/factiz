"""De site als Worker naast de site in Node (B80, PLAN #34.2bo stap 7): dezelfde pagina's, zoekvragen, ingangen en
deelplaatjes van twee draaiende servers, op dezelfde uitgave. De Node-site rust op de vergelijking met Python
(`factiz_site.gelijk*`) en de site-toetsen; dit laat zien dat de Worker (workerd, D1, het geheugen, de statische
bestanden) hetzelfde doet. Alleen de namen van gebouwde bestanden (`/_astro/...`) mogen verschillen.

    python -m factiz_site.gelijk_worker [--node http://127.0.0.1:8796] [--worker http://127.0.0.1:8795] [--per-taal 40]
"""

from __future__ import annotations

import argparse
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser

from factiz_site import i18n

BEGIN = ["", "fact-checks/", "themes/", "dossiers/", "names/", "newsrooms/", "sources/", "explore/", "explore/network/",
         "about/", "platform/"]
ASTRO = re.compile(r"/_astro/[^\"' )>]+")
AFZENDER = "FactizGelijkBot/1.0 (de site naast de Worker leggen)"   # "Bot": telt als robot, nooit als bezoeker


class _Geen(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def haal(basis: str, pad: str, bericht: dict | None = None) -> tuple[int, str, bytes, float]:
    """(status, soort, inhoud, seconden), zonder een omleiding te volgen."""
    data = urllib.parse.urlencode(bericht).encode() if bericht is not None else None
    # een eigen naam: Cloudflare weigert die van urllib (fout 1010) op workers.dev
    kop = {"user-agent": AFZENDER}
    if data:
        kop |= {"content-type": "application/x-www-form-urlencoded", "origin": basis}
    verzoek = urllib.request.Request(basis + pad, data=data, method="POST" if data else "GET", headers=kop)
    begin = time.monotonic()
    try:
        with urllib.request.build_opener(_Geen).open(verzoek, timeout=60) as r:
            return r.status, r.headers.get("content-type", ""), r.read(), time.monotonic() - begin
    except urllib.error.HTTPError as fout:
        return fout.code, fout.headers.get("content-type", ""), fout.read(), time.monotonic() - begin


class _Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links: list[str] = []

    def handle_starttag(self, tag, attrs):
        href = dict(attrs).get("href") if tag == "a" else None
        if href and href.startswith("/") and not href.startswith("//"):
            self.links.append(href.split("#")[0])


def paden(node: str, per_taal: int) -> list[str]:
    """Per taal de vaste pagina's en wat ervandaan te bereiken is, tot `per_taal` pagina's, in vaste volgorde."""
    uit: list[str] = []
    for taal in i18n.TALEN:
        voor = "/" if taal == "en" else f"/{i18n.PAD[taal]}/"
        rij = [voor + b for b in BEGIN]
        gezien = set(rij)
        i = 0
        while i < len(rij) and len([p for p in uit if p.startswith(voor) or voor == "/"]) < 10**9 and i < per_taal:
            status, soort, inhoud, _ = haal(node, rij[i])
            if status == 200 and "html" in soort:
                lezer = _Links()
                lezer.feed(inhoud.decode("utf-8", "replace"))
                for link in lezer.links:
                    if link not in gezien and (taal == "en" or link.startswith(voor)) and "/deelbeeld/" not in link:
                        gezien.add(link)
                        rij.append(link)
            i += 1
        uit += rij[:per_taal]
    return uit


def normaal(inhoud: bytes, soort: str) -> bytes:
    if "html" in soort or "json" in soort or "javascript" in soort:
        return ASTRO.sub("/_astro/X", inhoud.decode("utf-8", "replace")).encode()
    return inhoud


def main() -> None:  # pragma: no cover - CLI tegen twee draaiende servers
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--node", default="http://127.0.0.1:8796")
    p.add_argument("--worker", default="http://127.0.0.1:8795")
    p.add_argument("--per-taal", type=int, default=40)
    a = p.parse_args()
    lijst = paden(a.node, a.per_taal)
    deelbeelden = sorted({m for pad in lijst if "/fact-checks/" in pad
                          for m in re.findall(r"/deelbeeld/[a-z-]+/[0-9a-f]{16}\.jpg", haal(a.node, pad)[2].decode("utf-8", "replace"))})[:40]
    zoekvragen = [("/", {"q": q}) for q in ("vaccine", "WHO", "Zelensky villa", "vacinne", "疫苗", "टीका")] + [
        (f"/{taal}/api/zoek", {"q": "vaccine"}) for taal in ("nl", "ar")] + [(f"/{taal}/api/suggesties", {"q": "zel"}) for taal in ("en", "ru")]
    verschillen, tijden = [], {"node": [], "worker": []}
    for pad, bericht in [(p_, None) for p_ in lijst + deelbeelden] + zoekvragen:
        n, w = haal(a.node, pad, bericht), haal(a.worker, pad, bericht)
        tijden["node"].append(n[3])
        tijden["worker"].append(w[3])
        if n[0] != w[0]:
            verschillen.append(f"{pad} {bericht or ''}: status Node {n[0]}, Worker {w[0]}")
        elif normaal(n[2], n[1]) != normaal(w[2], w[1]):
            verschillen.append(f"{pad} {bericht or ''}: andere inhoud ({len(n[2])} tegen {len(w[2])} bytes)")
    for v in verschillen[:40]:
        print(v)
    totaal = len(lijst) + len(deelbeelden) + len(zoekvragen)
    mediaan = lambda x: sorted(x)[len(x) // 2]
    print(f"{totaal - len(verschillen)} van {totaal} gelijk; mediaan Node {mediaan(tijden['node']) * 1000:.0f} ms, "
          f"Worker {mediaan(tijden['worker']) * 1000:.0f} ms")
    raise SystemExit(1 if verschillen else 0)


if __name__ == "__main__":  # pragma: no cover
    main()
