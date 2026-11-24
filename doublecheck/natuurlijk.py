"""Natuurlijke parafrasen: twee redacties, dezelfde virale post (#25.13).

Factcheckers noemen in ClaimReview waar de claim verscheen (`appearance`).
Checkten twee verschillende redacties (herkend aan het domein van hun artikel)
dezelfde post, dan zijn hun claimteksten twee onafhankelijke formuleringen van
dezelfde claim. Die paren zijn gekozen op dezelfde post, niet op gelijkenis, en
dus niet circulair: anders dan de clusters, die per constructie al ≥ 0,93
lijken.

De toets zoekt met formulering A, met A zelf uit de index, en kijkt of een
claim van dezelfde post terugkomt, met de regels van het productiepad
(matchdrempel, de cross-linguale drempel bij verschillende talen, DR8).

Alleen losse posts op sociale platforms tellen: een transcriptie of
persconferentie bevat veel verschillende claims onder één URL.
"""

from __future__ import annotations

import re
from urllib.parse import parse_qs, urlsplit

import numpy as np

_BEHOUD = {"fbid", "story_fbid", "id", "v", "set"}
_ALGEMEEN = {"/photo", "/photo.php", "/story.php", "/permalink.php", "/watch", "/search/top", ""}


def post_sleutel(url: str) -> str | None:
    """Een vaste sleutel per losse post op een sociaal platform, anders None."""
    try:
        s = urlsplit(url.strip())
    except ValueError:
        return None
    host = re.sub(r"^(www\.|m\.|mobile\.|web\.)", "", (s.hostname or "").lower())
    if host == "x.com":
        host = "twitter.com"
    pad = s.path.rstrip("/")
    query = parse_qs(s.query)
    behoud = "&".join(f"{k}={query[k][0]}" for k in sorted(query) if k in _BEHOUD)
    if host == "twitter.com" and "/status/" in pad:
        return f"{host}{pad}"
    if host == "facebook.com":
        if pad == "/search/top" or (pad in _ALGEMEEN and not behoud):
            return None
        return f"{host}{pad}" + (f"?{behoud}" if behoud else "")
    if host == "instagram.com" and re.match(r"^/(p|reel|tv)/", pad):
        return f"{host}{pad}"
    if host == "tiktok.com" and "/video/" in pad:
        return f"{host}{pad}"
    if host == "youtube.com" and (pad.startswith("/shorts/") or (pad == "/watch" and "v" in query)):
        return f"{host}{pad}" + (f"?v={query['v'][0]}" if pad == "/watch" else "")
    if host in {"t.me", "telegram.me"} and pad.count("/") >= 2:
        return f"t.me{pad}"
    return None


def zoek_zonder(i: int, matrix: np.ndarray, ids: list[str], groep: set[str], *,
                match: float, verwant: float) -> tuple[str, float, str]:
    """Zoekt met rij i, zonder rij i zelf; deelt in als gevonden, fout, verwant of niets."""
    sims = matrix @ matrix[i]
    sims[i] = -np.inf
    j = int(np.argmax(sims))
    s = float(sims[j])
    if s >= match:
        return ("gevonden" if ids[j] in groep else "fout"), s, ids[j]
    if s >= verwant:
        return "verwant", s, ids[j]
    return "niets", s, ids[j]


def groepen_uit_feed(conn, feed: str) -> list[set[str]]:
    """Per losse post die door ≥ 2 redacties is gecheckt: de claims in ons corpus.

    Alleen groepen met ≥ 2 verschillende claims; gedeeld met de
    modelvergelijking (#25.14), zodat elk model dezelfde paren krijgt.
    """
    import collections
    import json

    url_naar_claim = dict(conn.execute("SELECT url, claim_id FROM factcheck"))
    data = json.load(open(feed, encoding="utf-8"))
    items = data if isinstance(data, list) else data.get("dataFeedElement", [])
    per_post: dict[str, dict[str, str]] = collections.defaultdict(dict)
    for rec in items:
        if not isinstance(rec, dict):
            continue
        item = rec.get("item") or {}
        if isinstance(item, list):
            item = item[0] if item and isinstance(item[0], dict) else {}
        if not isinstance(item, dict) or item.get("url") not in url_naar_claim:
            continue
        domein = re.sub(r"^www\.", "", (urlsplit(item["url"]).hostname or "").lower())
        verschijningen = (item.get("itemReviewed") or {}).get("appearance") or []
        if isinstance(verschijningen, dict):
            verschijningen = [verschijningen]
        for v in verschijningen if isinstance(verschijningen, list) else []:
            u = v.get("url") if isinstance(v, dict) else (v if isinstance(v, str) else None)
            sleutel = post_sleutel(u) if u else None
            if sleutel:
                per_post[sleutel].setdefault(domein, url_naar_claim[item["url"]])
    groepen = [set(d.values()) for d in per_post.values() if len(d) >= 2 and len(set(d.values())) >= 2]
    return groepen


def meet_natuurlijk(conn, groepen: list[set[str]], versie: str, t):
    """De toets zelf, voor elke modelversie en elke drempelset (#25.14).

    Geeft (uitkomsten, uitkomsten per soort, gelijkenis met de beste partner).
    """
    import collections

    from doublecheck.relation import contradicts, extract_negation_tokens, extract_negations, extract_numbers

    rijen = conn.execute(
        "SELECT c.claim_id, c.canonical_text, c.language, f.payload FROM claim c JOIN fingerprint f"
        " ON f.claim_id = c.claim_id WHERE f.kind = 'text' AND f.model_version = ? ORDER BY c.claim_id",
        (versie,),
    ).fetchall()
    ids = [r[0] for r in rijen]
    tekst = {r[0]: r[1] for r in rijen}
    taal = {r[0]: r[2] for r in rijen}
    index = {cid: i for i, cid in enumerate(ids)}
    matrix = np.vstack([np.frombuffer(r[3], dtype=np.float32) for r in rijen])

    tel = collections.Counter()
    per_soort = collections.defaultdict(collections.Counter)
    partner_sims = []
    for groep in groepen:
        for a in groep:
            if a not in index:
                continue
            anderen = [b for b in groep if b != a and b in index]
            # Zoals het productiepad: de cross-linguale drempel geldt als de taal
            # van de zoekvraag en die van de gevonden claim beide bekend zijn en
            # verschillen (#12.4), niet als de groep toevallig een andere taal bevat.
            _, _, kandidaat = zoek_zonder(index[a], matrix, ids, groep, match=2.0, verwant=2.0)
            crossling = (taal[a] not in ("", "und") and taal[kandidaat] not in ("", "und")
                         and taal[a] != taal[kandidaat])
            match = t.text_match_crosslingual if crossling else t.text_match
            uitkomst, s, kandidaat = zoek_zonder(index[a], matrix, ids, groep, match=match, verwant=t.text_related)
            if uitkomst in ("gevonden", "fout") and contradicts(
                extract_numbers(tekst[a]), extract_negations(tekst[a]), tekst[kandidaat],
                artefact_text=tekst[a], artefact_negation_tokens=extract_negation_tokens(tekst[a]),
            ):
                uitkomst = "tegenspraak"
            tel[uitkomst] += 1
            per_soort["cross-linguaal" if crossling else "zelfde taal"][uitkomst] += 1
            partner_sims.append(max(float(matrix[index[a]] @ matrix[index[b]]) for b in anderen))

    return tel, per_soort, partner_sims


def main() -> None:
    import argparse
    import os
    import statistics

    from threadpoolctl import threadpool_limits

    from doublecheck.config import load_config
    from doublecheck.storage import connect

    parser = argparse.ArgumentParser(description="Natuurlijke parafrasen meten (#25.13)")
    parser.add_argument("--feed", default="data/datacommons-claimreview.json")
    parser.add_argument("--threads", type=int, default=2)
    args = parser.parse_args()
    threadpool_limits(limits=args.threads)

    config = load_config()
    t = config.thresholds
    conn = connect(os.environ.get("DOUBLECHECK_DB", "doublecheck.db"))
    groepen = groepen_uit_feed(conn, args.feed)

    tel, per_soort, partner_sims = meet_natuurlijk(conn, groepen, config.model_versions.text_embedding, t)

    n = sum(tel.values())
    print(f"posts door ≥2 redacties gecheckt, ≥2 claims in het corpus: {len(groepen)} · zoekvragen: {n}")
    for k in ("gevonden", "verwant", "tegenspraak", "fout", "niets"):
        label = "ander record" if k == "fout" else k
        print(f"  {label:12} {tel[k]:>5}  {tel[k] / n:6.1%}")
    print("  ('ander record' = een claim buiten deze post boven de drempel: vaak dezelfde claim,"
          " door een andere redactie onder een andere post gecheckt; steekproef nodig)")
    for soort, c in per_soort.items():
        m = sum(c.values())
        print(f"  {soort:15} n={m:>4} · gevonden {c['gevonden'] / m:.1%} · verwant {c['verwant'] / m:.1%}"
              f" · tegenspraak {c['tegenspraak'] / m:.1%} · fout {c['fout'] / m:.1%} · niets {c['niets'] / m:.1%}")
    print(f"  gelijkenis met de beste partner van dezelfde post: mediaan {statistics.median(partner_sims):.3f},"
          f" p25 {np.quantile(partner_sims, 0.25):.3f}, p75 {np.quantile(partner_sims, 0.75):.3f}")


if __name__ == "__main__":
    main()
