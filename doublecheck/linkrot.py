"""Linkrot meten (#25.6): werken de bonnetjes nog?

Elke uitslag rust op een link naar de check van een redactie (DR1). Deze
meting neemt een reproduceerbare steekproef van check-URL's en kijkt of ze nog
bestaan. Streng in één richting: alleen wat aantoonbaar weg is telt als dood
(404/410, een verdwenen domein, of een doorverwijzing naar de voorpagina);
botbescherming, time-outs en serverfouten zijn "onduidelijk", nooit "levend".

Er wordt niets gedownload: een GET in streamstand, alleen de status en het
eindadres worden gelezen. De user-agent zegt wie er kijkt.
"""

from __future__ import annotations

import random
import re
from urllib.parse import urlsplit

USER_AGENT = "FactizLinkCheck/0.1 (+https://factiz.org; measures whether fact-check links still resolve)"
_ONDUIDELIJK = {401, 403, 405, 406, 408, 425, 429, 451, 500, 502, 503, 504, 520, 521, 522, 523, 524}
_TAALWORTEL = re.compile(r"^/(?:[a-z]{2}(?:-[a-z]{2})?/?)?$", re.IGNORECASE)
# Een tweede adres achter het eerste, een fout in de feed (BENCHMARK §110).
_TWEEDE_ADRES = re.compile(r"https?://", re.IGNORECASE)


def _segmenten(pad: str) -> list[str]:
    return [s for s in pad.split("/") if s]


def klasseer(status: int | None, eind_url: str | None, begin_url: str, fout: str | None = None) -> str:
    uitkomst = _klasseer(status, eind_url, begin_url, fout)
    # Een kapot adres dat niet werkt, zegt iets over de feed, niet over de
    # redactie: nooit dood, want "offline" zou een foute uitspraak over haar
    # werk zijn (#25.9). Werkt het toch, dan is het gewoon levend.
    if uitkomst in ("dood", "zacht-dood") and _TWEEDE_ADRES.search(begin_url, 1):
        return "onduidelijk"
    return uitkomst


def _klasseer(status: int | None, eind_url: str | None, begin_url: str, fout: str | None) -> str:
    if fout == "domein":
        return "dood"
    if fout is not None or status is None:
        return "onduidelijk"
    if status in (404, 410):
        return "dood"
    if status in _ONDUIDELIJK or status >= 500:
        return "onduidelijk"
    if 200 <= status < 300:
        eind_pad = urlsplit(eind_url or begin_url).path or "/"
        begin_pad = urlsplit(begin_url).path or "/"
        if _TAALWORTEL.match(eind_pad) and len(_segmenten(begin_pad)) > len(_segmenten(eind_pad)):
            return "zacht-dood"
        return "levend"
    return "onduidelijk"


def steekproef(urls: list[str], n: int, *, seed: int = 25) -> list[str]:
    uniek = sorted(set(urls))
    return random.Random(seed).sample(uniek, min(n, len(uniek)))


def rapport(uitkomsten: list[str]) -> dict:
    from doublecheck.benchmark import upper_bound_95

    n = len(uitkomsten)
    tel = {k: uitkomsten.count(k) for k in ("levend", "dood", "zacht-dood", "onduidelijk")}
    dood = tel["dood"] + tel["zacht-dood"]
    return {
        "n": n,
        **tel,
        "dood_totaal": dood,
        "aandeel_dood": dood / n if n else 0.0,
        "bovengrens95_dood": upper_bound_95(dood, n),
        "aandeel_onduidelijk": tel["onduidelijk"] / n if n else 0.0,
    }


def _controleer(client, url: str) -> tuple[str, str]:
    import httpx

    try:
        with client.stream("GET", url) as antwoord:
            return url, klasseer(antwoord.status_code, str(antwoord.url), url)
    except httpx.ConnectError as fout:
        tekst = str(fout).lower()
        domein = any(s in tekst for s in ("name or service not known", "nodename nor servname",
                                          "name resolution", "getaddrinfo"))
        return url, klasseer(None, None, url, fout="domein" if domein else "verbinding")
    except (httpx.TimeoutException, httpx.HTTPError, ValueError):
        return url, klasseer(None, None, url, fout="time-out")


def main() -> None:
    import argparse
    import collections
    import json
    import os
    from concurrent.futures import ThreadPoolExecutor
    from urllib.parse import urlsplit as _split

    import httpx

    from doublecheck.storage import connect

    parser = argparse.ArgumentParser(description="Linkrot op een steekproef van check-URL's (#25.6)")
    parser.add_argument("--n", type=int, default=400)
    parser.add_argument("--seed", type=int, default=25)
    parser.add_argument("--uit", help="schrijf de uitkomst per URL als JSON")
    args = parser.parse_args()

    conn = connect(os.environ.get("DOUBLECHECK_DB", "doublecheck.db"))
    urls = [r[0] for r in conn.execute("SELECT url FROM factcheck WHERE url LIKE 'http%'")]
    proef = steekproef(urls, args.n, seed=args.seed)
    with httpx.Client(follow_redirects=True, timeout=12.0, headers={"User-Agent": USER_AGENT}) as client:
        with ThreadPoolExecutor(max_workers=12) as pool:
            uitkomsten = dict(pool.map(lambda u: _controleer(client, u), proef))

    r = rapport(list(uitkomsten.values()))
    print(f"steekproef {r['n']} van {len(set(urls))} check-URL's (seed {args.seed})")
    print(f"  levend {r['levend']} · dood {r['dood']} · zacht-dood {r['zacht-dood']} · onduidelijk {r['onduidelijk']}")
    print(f"  dood totaal {r['aandeel_dood']:.1%} (bovengrens 95% {r['bovengrens95_dood']:.1%}) · "
          f"onduidelijk {r['aandeel_onduidelijk']:.1%}")
    per_host = collections.Counter(_split(u).hostname for u, k in uitkomsten.items() if k in ("dood", "zacht-dood"))
    if per_host:
        print("  dood per host (top 8):", ", ".join(f"{h} {n}" for h, n in per_host.most_common(8)))
    if args.uit:
        with open(args.uit, "w", encoding="utf-8") as f:
            json.dump(uitkomsten, f, indent=1)


if __name__ == "__main__":
    main()
