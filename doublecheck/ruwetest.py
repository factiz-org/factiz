"""Ruwe test met de beelden van factcheckers (#25.10).

Factcheckers hebben het nepnieuws al gevonden en geverifieerd. Deze test pakt
van hun artikelen het beeld dat rondging (og:image) en haalt het als
screenshot door de resolver: vindt het systeem vanaf het beeld de juiste check
terug? Twee delen:

- **herkenning**: checks die al in het geheugen staan;
- **versheid**: de nieuwste artikelen uit de RSS van een paar uitgevers die
  nog níét in het geheugen staan; die horen `none` te geven.

Beelden en pagina's worden alleen in het geheugen opgehaald en na de meting
weggegooid; er wordt niets op schijf bewaard behalve URL en uitkomst (DR3).
Anonimiseren is automatisch onbetrouwbaar (stempels als "FALSE", logo's), dus
de test meet het: per beeld of de OCR een oordeelwoord of uitgevernaam leest,
en het rapport splitst "met stempel" en "zonder stempel".
"""

from __future__ import annotations

import html as _html
import json
import re
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path

USER_AGENT = "FactizRoughTest/0.1 (+https://factiz.org; tests whether debunked images resolve to their fact-check)"

# Woorden die op een stempel of verdictlabel wijzen, in de talen van de
# geteste uitgevers. Alleen voor de lekmeting, nooit voor een oordeel.
OORDEELWOORDEN = (
    "false", "fake", "misleading", "fact check", "factcheck", "fact-check", "fact crescendo",
    "altered", "edited", "manipulated", "satire", "hoax", "no evidence",
    "faux", "falso", "falsch", "faktenfuchs", "onwaar", "nep", "misleidend", "engañoso", "enganoso",
    "ang totoo", "hindi totoo", "mali",  # Tagalog: VERA Files stempelt "ANG TOTOO"
    "زائف", "مضلل", "كاذب", "خاطئ", "فکت", "شاخ‌دار", "فرضی", "फर्जी", "गलत", "भ्रामक",
)

_META = re.compile(r"<meta\b[^>]*>", re.IGNORECASE)
_ATTR = re.compile(r'(\w[\w:-]*)\s*=\s*("([^"]*)"|\'([^\']*)\')', re.IGNORECASE)


def lees_meta(pagina: str) -> dict:
    """og:image (of twitter:image) en og:title uit de kop van een artikel."""
    gevonden: dict[str, str] = {}
    for tag in _META.findall(pagina):
        attrs = {m.group(1).lower(): (m.group(3) if m.group(3) is not None else m.group(4))
                 for m in _ATTR.finditer(tag)}
        sleutel = (attrs.get("property") or attrs.get("name") or "").lower()
        inhoud = _html.unescape(attrs.get("content") or "").strip()
        if sleutel and inhoud and sleutel not in gevonden:
            gevonden[sleutel] = inhoud
    return {
        "beeld": gevonden.get("og:image") or gevonden.get("og:image:url") or gevonden.get("twitter:image"),
        "titel": gevonden.get("og:title") or gevonden.get("twitter:title"),
    }


def lekt(ocr_tekst: str, uitgever: str) -> bool:
    tekst = ocr_tekst.casefold()
    if any(woord in tekst for woord in OORDEELWOORDEN):
        return True
    naam = uitgever.casefold().strip()
    varianten = {naam, " ".join(naam.split()[:2])}
    return any(v and len(v) >= 4 and v in tekst for v in varianten)


# Hoeveel tekens (zonder spaties) de OCR moet lezen voordat een beeld als
# "met tekst" telt. Een rapportsplitsing, geen drempel van de motor.
MIN_TEKST = 20


@dataclass(frozen=True)
class M4FCItem:
    claim_id: str
    url: str
    uitgever: str
    taal: str
    pad: Path


def config_met_ondergrens(ondergrens: float):
    """De config van deze machine, met alleen een andere ondergrens voor twee
    keer lezen (#25.22): om de regel te meten zonder `config.toml` te raken."""
    import dataclasses

    from doublecheck.config import load_config

    config = load_config()
    return dataclasses.replace(config, ocr=dataclasses.replace(config.ocr, schrift_ondergrens=ondergrens))


def m4fc_items(map_) -> list[M4FCItem]:
    """De M4FC-beelden met een check in onze index (#28.5) die binnenkwamen,
    met de URL van het artikel als het bonnetje dat terug moet komen."""
    map_ = Path(map_)
    dataset = json.loads((map_ / "M4FC.json").read_text(encoding="utf-8"))
    gekoppeld = json.loads((map_ / "gekoppeld.json").read_text(encoding="utf-8"))
    items = []
    for index, koppeling in sorted(gekoppeld.items(), key=lambda kv: int(kv[0])):
        bestanden = sorted((map_ / "beelden").glob(f"{int(index):05d}.*"))
        if not bestanden:
            continue
        rij = dataset[int(index)]
        items.append(M4FCItem(koppeling["claim_id"], koppeling["article_url"],
                              rij.get("fc_org", ""), rij.get("fc_language", ""), bestanden[0]))
    return items


def antwoord_of_fout(antwoord) -> dict:
    """Het antwoord van de resolver, of een harde stop. Een 429 of 500 als
    "niets" tellen meet de ratelimiter in plaats van de motor: zo telde de
    eerste netwerktoets 1.670 keer niets (#28.5)."""
    if antwoord.status_code != 200:
        raise RuntimeError(f"de resolver antwoordde {antwoord.status_code}; de run stopt in plaats van mee te tellen")
    return antwoord.json()


def zonder_ipgrens():
    """De per-IP-grens is er voor publiek verkeer; een meting in het proces
    vraagt sneller dan een mens en mag er niet tegenaan lopen."""
    from doublecheck.api import limiter

    limiter.enabled = False


def te_herbekijken(uitslagen: list[dict], items: list[M4FCItem]) -> list[M4FCItem]:
    """De items waar de resolver een ándere claim als `matched` gaf. Of dat
    een echte valse treffer is of dezelfde claim buiten het cluster, beslist
    een mens; deze hulp zet alleen die gevallen klaar."""
    fout = {u["url"] for u in uitslagen if u.get("uitkomst") == "fout"}
    return [i for i in items if i.url in fout]


def beoordeel(antwoord: dict, bron_url: str, verwacht: set[str]) -> str:
    """gevonden: de juiste check (of een clustergenoot) kwam terug; fout: een
    ándere claim als `matched`; verwant: `related`; niets: `none`."""
    categorie = antwoord.get("category")
    if categorie == "matched":
        claim = (antwoord.get("claim") or {}).get("id")
        urls = {c.get("url") for c in (antwoord.get("evidence") or {}).get("checks", [])}
        return "gevonden" if claim in verwacht or bron_url in urls else "fout"
    if categorie == "related":
        return "verwant"
    return "niets"


@dataclass(frozen=True)
class Uitkomst:
    uitgever: str
    taal: str
    url: str
    uitkomst: str
    lekt: bool
    deel: str = "herkenning"
    # Las de OCR genoeg tekst om de tekstroute een kans te geven? Zonder
    # beeldindex (#25.11) kan een beeld zonder tekst alleen `none` geven.
    tekst: bool = True


def _tel(rijen: list[Uitkomst]) -> dict:
    c = Counter(r.uitkomst for r in rijen)
    return {"n": len(rijen), **{k: c.get(k, 0) for k in ("gevonden", "verwant", "fout", "niets")}}


def rapport(uitkomsten: list[Uitkomst]) -> dict:
    per_uitgever: dict[str, list[Uitkomst]] = {}
    for u in uitkomsten:
        per_uitgever.setdefault(u.uitgever, []).append(u)
    return {
        "totaal": _tel(uitkomsten),
        "zonder_stempel": _tel([u for u in uitkomsten if not u.lekt]),
        "met_stempel": _tel([u for u in uitkomsten if u.lekt]),
        "met_tekst": _tel([u for u in uitkomsten if u.tekst]),
        "zonder_tekst": _tel([u for u in uitkomsten if not u.tekst]),
        "per_uitgever": {k: _tel(v) for k, v in sorted(per_uitgever.items())},
    }


def _kies(conn, *, per_uitgever: int, max_totaal: int, sinds: str):
    rijen = conn.execute(
        "SELECT f.claim_id, f.url, f.publisher, c.language, f.review_date FROM factcheck f"
        " JOIN claim c ON c.claim_id = f.claim_id"
        " WHERE f.review_date >= ? AND f.url LIKE 'http%' ORDER BY f.review_date DESC",
        (sinds,),
    ).fetchall()
    gekozen, per = [], Counter()
    for claim_id, url, uitgever, taal, _ in rijen:
        if per[uitgever] >= per_uitgever:
            continue
        per[uitgever] += 1
        gekozen.append((claim_id, url, uitgever, taal))
        if len(gekozen) >= max_totaal:
            break
    return gekozen


def main() -> None:
    import argparse
    import json
    import os
    import time
    from datetime import datetime

    import httpx
    from fastapi.testclient import TestClient

    from doublecheck.api import MAX_IMAGE_BYTES, app
    from doublecheck.clustering import cluster_members
    from doublecheck.config import load_config
    from doublecheck.ocr import extract_text
    from doublecheck.storage import connect

    parser = argparse.ArgumentParser(description="Ruwe test met de beelden van factcheckers (#25.10)")
    parser.add_argument("--per-uitgever", type=int, default=4)
    parser.add_argument("--max", type=int, default=40)
    parser.add_argument("--sinds", default="2026-08-01")
    parser.add_argument("--m4fc", help="map met M4FC.json, gekoppeld.json en beelden/ (#28.5); slaat het web over")
    parser.add_argument("--threads", type=int, default=2)
    parser.add_argument("--herbekijk", help="uitkomstenbestand van een M4FC-run: toon de fouten naast de verwachte claim")
    parser.add_argument("--ocr-ondergrens", type=float,
                        help="meet met twee keer lezen bij twijfel vanaf deze OSD-zekerheid (#25.22); raakt config niet")
    parser.add_argument("--rss", nargs="*", default=[
        "https://factly.in/feed/", "https://verafiles.org/feed", "https://www.br.de/nachrichten/faktenfuchs/rss",
    ], help="RSS-feeds voor het versheidsdeel")
    args = parser.parse_args()
    import torch

    torch.set_num_threads(args.threads)

    conn = connect(os.environ.get("DOUBLECHECK_DB", "doublecheck.db"))
    zonder_ipgrens()
    ocr = load_config().ocr
    if args.ocr_ondergrens is not None:
        from doublecheck.api import get_config

        gemeten = config_met_ondergrens(args.ocr_ondergrens)
        app.dependency_overrides[get_config] = lambda: gemeten
        ocr = gemeten.ocr
    bekend = {r[0] for r in conn.execute("SELECT url FROM factcheck")}
    uitkomsten: list[Uitkomst] = []
    overgeslagen = Counter()

    def _beeld_van(web, url):
        pagina = web.get(url)
        if pagina.status_code != 200:
            return None, "pagina " + str(pagina.status_code)
        beeldurl = lees_meta(pagina.text)["beeld"]
        if not beeldurl:
            return None, "geen beeld"
        beeld = web.get(beeldurl)
        soort = beeld.headers.get("content-type", "")
        if beeld.status_code != 200 or not soort.startswith("image/"):
            return None, "beeld onbereikbaar"
        if len(beeld.content) > MAX_IMAGE_BYTES:
            return None, "beeld te groot"
        return beeld.content, None

    def _toets(api, inhoud, uitgever):
        try:
            leesbaar = extract_text(inhoud, ocr).text
        except Exception:
            leesbaar = ""
        antwoord = api.post("/resolve", files={"image": ("beeld", inhoud, "application/octet-stream")})
        return (antwoord_of_fout(antwoord), lekt(leesbaar, uitgever), len("".join(leesbaar.split())) >= MIN_TEKST)

    if args.m4fc and args.herbekijk:
        uitslagen = json.loads(Path(args.herbekijk).read_text(encoding="utf-8"))
        tekst_van = dict(conn.execute("SELECT claim_id, canonical_text FROM claim"))
        with TestClient(app) as api:
            for item in te_herbekijken(uitslagen, m4fc_items(args.m4fc)):
                inhoud = item.pad.read_bytes()
                antwoord = antwoord_of_fout(
                    api.post("/resolve", files={"image": ("beeld", inhoud, "application/octet-stream")}))
                gekozen = antwoord.get("claim") or {}
                print(f"\n{item.uitgever} [{item.taal}] {item.url}")
                print(f"  verwacht: {tekst_van.get(item.claim_id, '?')[:160]}")
                print(f"  gekozen:  {(gekozen.get('text') or '')[:160]}")
                print(f"  gelijkenis {antwoord.get('similarity')} · via {antwoord.get('matched_on')}")
        return
    if args.m4fc:
        # Herkenning op de M4FC-beelden van schijf; geen versheidsdeel.
        with TestClient(app) as api:
            items = m4fc_items(args.m4fc)
            print(f"M4FC: {len(items)} beelden met een check in de index", flush=True)
            for n, item in enumerate(items, 1):
                inhoud = item.pad.read_bytes()
                if len(inhoud) > MAX_IMAGE_BYTES:
                    overgeslagen["beeld te groot"] += 1
                    continue
                antwoord, gelekt, tekst = _toets(api, inhoud, item.uitgever)
                verwacht = cluster_members(conn, item.claim_id) | {item.claim_id}
                uitkomsten.append(Uitkomst(item.uitgever, item.taal, item.url,
                                           beoordeel(antwoord, item.url, verwacht), gelekt, tekst=tekst))
                if n % 100 == 0:
                    print(f"  {n}/{len(items)} · {_tel(uitkomsten)}", flush=True)
        args.rss = []
    with httpx.Client(follow_redirects=True, timeout=20.0, headers={"User-Agent": USER_AGENT}) as web, \
            TestClient(app) as api:
        # (a) herkenning
        for claim_id, url, uitgever, taal in ([] if args.m4fc else _kies(
                conn, per_uitgever=args.per_uitgever, max_totaal=args.max, sinds=args.sinds)):
            try:
                inhoud, reden = _beeld_van(web, url)
            except httpx.HTTPError:
                inhoud, reden = None, "netwerk"
            if inhoud is None:
                overgeslagen[reden] += 1
                continue
            antwoord, gelekt, tekst = _toets(api, inhoud, uitgever)
            uitkomsten.append(Uitkomst(uitgever, taal, url,
                                       beoordeel(antwoord, url, cluster_members(conn, claim_id) | {claim_id}), gelekt,
                                       tekst=tekst))
            del inhoud
            time.sleep(0.5)
        # (b) versheid: nieuwste artikelen die nog niet in het geheugen staan
        for feed in args.rss:
            try:
                xml = web.get(feed).text
            except httpx.HTTPError:
                overgeslagen["rss onbereikbaar"] += 1
                continue
            links = [_html.unescape(l.strip()) for l in re.findall(r"<item>.*?<link>(.*?)</link>", xml, re.S)][:10]
            for url in links:
                if url in bekend:
                    continue
                try:
                    inhoud, reden = _beeld_van(web, url)
                except httpx.HTTPError:
                    inhoud, reden = None, "netwerk"
                if inhoud is None:
                    overgeslagen[reden] += 1
                    continue
                antwoord, gelekt, tekst = _toets(api, inhoud, feed)
                uitkomsten.append(Uitkomst(feed, "", url, beoordeel(antwoord, url, set()), gelekt,
                                           deel="versheid", tekst=tekst))
                del inhoud
                time.sleep(0.5)

    herkenning = [u for u in uitkomsten if u.deel == "herkenning"]
    versheid = [u for u in uitkomsten if u.deel == "versheid"]
    r = rapport(herkenning)
    print(f"HERKENNING (al in het geheugen): {r['totaal']}")
    print(f"  zonder stempel: {r['zonder_stempel']}")
    print(f"  met stempel:    {r['met_stempel']}")
    print(f"  met tekst:      {r['met_tekst']}")
    print(f"  zonder tekst:   {r['zonder_tekst']}")
    for uitgever, tel in r["per_uitgever"].items():
        print(f"  {uitgever[:28]:28} {tel}")
    print(f"VERSHEID (nog niet in het geheugen, verwacht: niets): {_tel(versheid)}")
    print(f"overgeslagen: {dict(overgeslagen)}")
    pad = f"data/ruwetest-{datetime.now().strftime('%Y-%m-%dT%H%M%S')}.json"
    with open(pad, "w", encoding="utf-8") as f:
        json.dump([asdict(u) for u in uitkomsten], f, ensure_ascii=False, indent=1)
    print(f"uitkomsten (alleen URL en uitkomst): {pad}")


if __name__ == "__main__":
    main()
