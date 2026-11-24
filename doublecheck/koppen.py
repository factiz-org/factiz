"""De koppen van de dichte sites, een voormeting (PLAN #32.3f).

De zoekfunctie van Anthropic ziet 16 grote nieuwssites niet (BENCHMARK §175). Kunnen we zonder het artikel te
openen nagaan of zo'n site een stuk met deze kop had? Drie routes, alleen langs open pagina's:
- route 1: de kop letterlijk in Wikipedia zoeken en de bronvermeldingen lezen ($0);
- route 2: één zoekvraag van Haiku zonder beperking tot een site, naar overnames en verwijzingen (Batch API);
- route 3: GDELT, alleen voor vers nieuws, op links uit Portal:Current events ($0).
Overnames door goede redacties tellen los (PO 2026-10-28).

    python -m doublecheck.koppen set|wikipedia|indienen [--proef N]|ophalen|portal|gdelt|lezen|tellen
"""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from urllib.parse import urlsplit

from doublecheck import bronnen as br
from doublecheck.kruiscontrole import eigenaar

WORTEL = Path(__file__).resolve().parent.parent
UIT = WORTEL / "data" / "koppen"
LABELS = WORTEL / "docs" / "steekproeven" / "32.3f-koppen.json"
BUDGET = 3.0
DREMPEL = 0.8  # het deel van de woorden van de kop dat in de titel moet staan
SCHATTING = 0.02  # per vraag van Haiku met één zoekopdracht, in de batch
MAX_PAGINAS = 8
VRAAGVERSIE = 2  # v2: hoogstens één zin vóór de JSON en meer ruimte; in de proef van v1 werden 2 van de 5 afgekapt
PORTAL_PER_SITE, PORTAL_N = 10, 40
# Hoe een pagina een dichte site als bron noemt, naast de naam zonder achtervoegsel ("bbc", "theguardian").
_ALIASSEN = {"apnews": {"ap", "associatedpress"}, "nytimes": {"newyorktimes"}, "dw": {"deutschewelle"},
             "theguardian": {"guardian"}, "theatlantic": {"atlantic"}, "latimes": {"losangelestimes"},
             "economist": {"theeconomist"}, "independent": {"theindependent"}}
_WOORD = re.compile(r"\w+")
_CITE = re.compile(r"\{\{\s*cite[^{}]*\}\}", re.IGNORECASE)
_VELD = re.compile(r"\|\s*(url|title)\s*=\s*([^|}]*)", re.IGNORECASE)
_KALE_LINK = re.compile(r"\[(https?://[^\s\]]+)\s+([^\]]+)\]")
_LINK = re.compile(r"\[(https?://[^\s\]]+)")

VRAAG = """A screenshot presents this as a news article from {site}:
<article>
{tekst}
</article>

Search the web once for this article, with its headline or its most specific words. {site} itself cannot be searched: look for other pages, such as copies of the same article (a news agency story republished on another site), pages that cite or link to it, and other news reports of the same story.

List the relevant pages you found, at most {max}. For each page:
- "url": its address;
- "kop": its headline as shown;
- "zelfde_verhaal": true if it reports the same story;
- "overname": true if it carries the same article text (a copy or a republication);
- "bron": the website or news organisation the page names as the source of this story or article, as a domain if you can (for example "theguardian.com"), or "" if it names none;
- "verschillen": only for a copy, the facts in the screenshot text that differ from it, each with "woorden" (exactly as in the screenshot) and "juist" (exactly as on the page); otherwise [].

Write at most one short sentence before the JSON. End with one line of JSON and nothing after it:
{{"paginas": [{{"url": "...", "kop": "...", "zelfde_verhaal": true, "overname": false, "bron": "...", "verschillen": []}}]}}"""


class Weigering(Exception):
    """Tellen kan niet: een vondst bij een vervalsing zonder label, of indienen boven het budget."""


# --- vergelijken -----------------------------------------------------------------------------------

def _woorden(tekst: str) -> set[str]:
    return {w.casefold() for w in _WOORD.findall(tekst)}


def lijkt_op(kop: str, titel: str) -> bool:
    """Een titel hoort bij de kop als minstens vier vijfde van de woorden van de kop erin staat."""
    k = _woorden(kop)
    return bool(k) and len(k & _woorden(titel)) / len(k) >= DREMPEL


def _site(url: str) -> str:
    host = (urlsplit(url).hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


def zelfde_link(a: str, b: str) -> bool:
    """Dezelfde pagina: hetzelfde pad bij dezelfde uitgever, zonder schema, www, vraag of slotstreep."""
    pa, pb = urlsplit(a), urlsplit(b)
    return (eigenaar(_site(a)) == eigenaar(_site(b)) and bool(_site(a))
            and pa.path.rstrip("/").lower() == pb.path.rstrip("/").lower())


def _noemt(bron: str, site: str) -> bool:
    """Noemt deze bron de getoonde site? Een domein, een naam ("The Guardian") of een afkorting ("AP")."""
    b = re.sub(r"[^a-z0-9]", "", bron.casefold())
    naam = eigenaar(site)
    namen = {naam} | _ALIASSEN.get(naam, set())
    return bool(b) and any(n == b or (len(n) > 3 and n in b) for n in namen)


# --- route 1: Wikipedia -----------------------------------------------------------------------------

def citaten(wikitekst: str) -> list[dict]:
    """De bronnen in wikitekst: cite-sjablonen met url en titel, en kale links met een titel erachter."""
    uit = []
    for m in _CITE.finditer(wikitekst):
        velden = {n.lower(): w.strip() for n, w in _VELD.findall(m.group(0))}
        if velden.get("url"):
            uit.append({"url": velden["url"], "titel": velden.get("title", "")})
    for url, titel in _KALE_LINK.findall(_CITE.sub("", wikitekst)):
        uit.append({"url": url, "titel": titel.strip()})
    return uit


def wiki_vondst(kop: str, site: str, citaten_: list[dict]) -> dict | None:
    """De eerste bron bij dezelfde uitgever (bbc.co.uk telt voor bbc.com) met een titel die op de kop lijkt."""
    return next((c for c in citaten_ if eigenaar(_site(c["url"])) == eigenaar(site) and lijkt_op(kop, c["titel"])),
                None)


# --- route 2: overnames en verwijzingen -------------------------------------------------------------

def lees_overname(blokken: list[dict]) -> list[dict] | None:
    """De pagina's uit de laatste JSON-regel; wat niet te lezen is: None."""
    tekst = "".join(b.get("text") or "" for b in blokken if b.get("type") == "text")
    for begin in reversed([i for i, t in enumerate(tekst) if t == "{"]):
        try:
            d, _ = json.JSONDecoder().raw_decode(tekst[begin:])
        except json.JSONDecodeError:
            continue
        if isinstance(d, dict) and isinstance(d.get("paginas"), list):
            return [{"url": p.get("url") or "", "kop": p.get("kop") or "", "zelfde_verhaal": p.get("zelfde_verhaal") is True,
                     "overname": p.get("overname") is True, "bron": p.get("bron") or "",
                     "verschillen": [x for x in p.get("verschillen") or [] if isinstance(x, dict)
                                     and isinstance(x.get("woorden"), str) and isinstance(x.get("juist"), str)]}
                    for p in d["paginas"] if isinstance(p, dict) and isinstance(p.get("url"), str)]
    return None


def overname_vondst(kop: str, site: str, paginas: list[dict], sites: dict) -> dict:
    """Wat route 2 vond:
    - *bij site*: een pagina met deze kop die de getoonde site als bron noemt;
    - *andere site*: anders de eerste pagina met deze kop die een andere site als bron noemt;
    - *goede sites*: hoeveel redacties met band goed het verhaal brengen, elk los (PO), één per uitgever;
    - *verschillen*: wat een overname anders zegt dan het screenshot."""
    met_kop = [p for p in paginas if lijkt_op(kop, p["kop"])]
    bij = [p for p in met_kop if _noemt(p["bron"], site)]
    andere = next((p["bron"] for p in met_kop if p["bron"] and not _noemt(p["bron"], site)), None)
    goed = {eigenaar(_site(p["url"])) for p in paginas
            if p["zelfde_verhaal"] and br.beoordeel(p["url"], sites).get("band") == "goed"}
    return {"bij site": bool(bij), "andere site": None if bij else andere, "goede sites": len(goed),
            "verschillen": [d for p in paginas if p["overname"] for d in p["verschillen"]]}


# --- route 3: GDELT -----------------------------------------------------------------------------------

def portal_links(wikitekst: str) -> list[str]:
    """De links in een dag van Portal:Current events, in volgorde."""
    return _LINK.findall(wikitekst)


def gdelt_woorden(url: str) -> str:
    """Zoekwoorden uit de link zelf: de woorden van het laatste stuk van het pad, zonder cijfers en id's."""
    stukken = [s for s in urlsplit(url).path.split("/") if s]
    slug = max(stukken, key=lambda s: s.count("-"), default="")
    woorden = [w for w in slug.lower().split("-") if w.isalpha() and len(w) > 2]
    return " ".join(woorden[:6]) if slug.count("-") >= 2 else ""


# --- tellen ----------------------------------------------------------------------------------------------

def telling(stukken: list[dict], vondsten: dict[str, dict], labels: dict, gdelt: dict) -> dict:
    """De voormeting van PLAN #32.3f. `vondsten`: per bericht of route 1 en route 2 de kop bij de getoonde site
    vonden. Elke vondst bij een verzonnen kop of een andere krant moet gelezen zijn ('vals' of 'set fout'), en
    elke vondst van route 2 bij een echt artikel ('juist' of 'fout'; alleen 'juist' telt)."""
    routes = ("route 1", "route 2")
    dekking = {r: {"n": 0, "gevonden": 0} for r in (*routes, "samen")}
    per_set: dict[str, Counter] = {}
    vals = Counter()
    open_ = []
    for s in stukken:
        v = dict(vondsten.get(s["id"], {}))
        if s["sub"] == "A" and v.get("route 2"):
            label = labels.get((s["id"], "route 2"))
            if label is None:
                open_.append(f"{s['id']} route 2")
            v["route 2"] = label == "juist"
        if s["sub"] == "A":
            for r in routes:
                dekking[r]["n"] += 1
                dekking[r]["gevonden"] += bool(v.get(r))
            dekking["samen"]["n"] += 1
            dekking["samen"]["gevonden"] += any(v.get(r) for r in routes)
            per_set.setdefault(s.get("set", "?"), Counter()).update(
                {"n": 1, "gevonden": any(v.get(r) for r in routes)})
        elif s["sub"] in ("B-kop", "B-krant"):
            for r in routes:
                if v.get(r):
                    label = labels.get((s["id"], r))
                    if label is None:
                        open_.append(f"{s['id']} {r}")
                    vals[r] += label == "vals"
    if open_:
        raise Weigering(f"{len(open_)} zonder label in {LABELS.name}, bijvoorbeeld {open_[0]}")
    vals["samen"] = vals["route 1"] + vals["route 2"]
    veelbelovend = any(d["n"] and d["gevonden"] >= d["n"] / 2 and vals[r] == 0 for r, d in dekking.items())
    return {"dekking": dekking, "per set": {k: dict(c) for k, c in per_set.items()},
            "valse vondst": dict(vals), "route 3": gdelt, "veelbelovend": veelbelovend}


# --- de bestanden en de CLI ------------------------------------------------------------------------------

def _jsonl(pad: Path) -> list[dict]:
    return [json.loads(r) for r in pad.read_text(encoding="utf-8").splitlines() if r.strip()] if pad.exists() else []


def _voeg_toe(pad: Path, rij: dict) -> None:
    with pad.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rij, ensure_ascii=False) + "\n")


def lees_labels() -> dict:
    d = json.loads(LABELS.read_text(encoding="utf-8")) if LABELS.exists() else {}
    return {(r["id"], r["wat"]): r["label"] for r in d.get("oordelen", [])}


def al_uitgegeven() -> float:
    return sum(b["schatting"] if b.get("werkelijk") is None else b["werkelijk"] for b in _jsonl(UIT / "batches.jsonl"))


def _maak_set() -> list[dict]:  # pragma: no cover - op de bestanden van #32.0k en #32.3e
    from doublecheck import berichtcontrole as bc
    from doublecheck import gebruikerstoets as g
    from doublecheck import herkomst as h

    pool = {a["id"]: a for a in g.pools()["artikelen"]}
    keuze = {s["id"]: s for s in _jsonl(h.UIT / "keuze.jsonl")}
    gemaakt = {x["id"]: x for x in _jsonl(g.UIT / "gemaakt.jsonl") + _jsonl(h.UIT / "gemaakt.jsonl")}
    lijst = bc.herkomstlijst()
    uit = []
    for naam, rijen in (("ontwikkel", h.p11("ontwikkel")), ("toets", h.p11("toets")), ("nieuw", _jsonl(h.UIT / "set.jsonl"))):
        for s in rijen:
            site = bc.herkomst_site(s["tekst"], lijst["sites"], geblokkeerd=frozenset())
            if site not in bc.GEEN_TOEGANG:
                continue
            x = gemaakt.get(s["id"], {})
            echt = (keuze[s["id"]]["tekst"] if naam == "nieuw" else pool[s["id"].split(":", 1)[1]]["tekst"]).split("\n")[0]
            uit.append({"id": s["id"], "set": naam, "sub": s["sub"], "site": site, "tekst": s["tekst"],
                        "kop": x["kop"] if s["sub"] in ("B-feit", "B-kop") else echt, "echte kop": echt,
                        "detail": {k: x[k] for k in ("origineel", "nieuw", "veranderd") if k in x}})
    UIT.mkdir(parents=True, exist_ok=True)
    (UIT / "set.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in uit), encoding="utf-8")
    return uit


def _wiki(params: dict) -> dict:  # pragma: no cover - netwerk
    import time
    import urllib.parse
    import urllib.request

    import urllib.error

    url = "https://en.wikipedia.org/w/api.php?" + urllib.parse.urlencode({**params, "format": "json", "formatversion": 2,
                                                                         "maxlag": 5})
    req = urllib.request.Request(url, headers={"User-Agent": "FactizResearch/0.1 (https://factiz.org; research)"})
    for poging in range(6):
        time.sleep(2 + 30 * poging)  # één verzoek tegelijk; bij een weigering steeds langer wachten
        try:
            return json.load(urllib.request.urlopen(req, timeout=60))
        except urllib.error.HTTPError as fout:
            if fout.code != 429:
                raise
    raise RuntimeError("Wikipedia blijft weigeren")


def _wikitekst(titel: str) -> str:  # pragma: no cover - netwerk
    d = _wiki({"action": "query", "prop": "revisions", "rvprop": "content", "rvslots": "main", "titles": titel})
    pagina = d["query"]["pages"][0]
    return pagina["revisions"][0]["slots"]["main"]["content"] if "revisions" in pagina else ""


def _route1(s: dict) -> dict:  # pragma: no cover - netwerk
    kop = s["kop"].replace('"', "")
    titels = [x["title"] for x in _wiki({"action": "query", "list": "search", "srsearch": f'"{kop}"',
                                         "srlimit": 5})["query"]["search"]]
    vondst, andere = None, None
    for titel in titels:
        cit = citaten(_wikitekst(titel))
        vondst = wiki_vondst(s["kop"], s["site"], cit)
        andere = andere or next((c for c in cit if lijkt_op(s["kop"], c["titel"])
                                 and eigenaar(_site(c["url"])) != eigenaar(s["site"])), None)
        if vondst:
            break
    return {"id": s["id"], "paginas": titels, "gevonden": bool(vondst), "vondst": vondst,
            "andere": None if vondst else andere}


def _portal() -> list[dict]:  # pragma: no cover - netwerk
    from doublecheck import berichtcontrole as bc

    dicht = {eigenaar(x): x for x in bc.GEEN_TOEGANG}
    per_site: dict[str, list] = {}
    for dag in range(1, 29):
        for url in portal_links(_wikitekst(f"Portal:Current events/2026 October {dag}")):
            naam = eigenaar(_site(url))
            if naam in dicht and not any(zelfde_link(url, u["url"]) for u in per_site.get(naam, [])):
                per_site.setdefault(naam, []).append({"url": url, "site": _site(url), "dag": dag})
    gekozen, ronde = [], 0
    while len(gekozen) < PORTAL_N and any(len(v) > ronde for v in per_site.values()):
        for naam in sorted(per_site):
            if ronde < min(len(per_site[naam]), PORTAL_PER_SITE) and len(gekozen) < PORTAL_N:
                gekozen.append(per_site[naam][ronde])
        ronde += 1
    return gekozen


def _gdelt(rij: dict) -> dict:  # pragma: no cover - netwerk
    import time
    import urllib.parse
    import urllib.request

    woorden = gdelt_woorden(rij["url"])
    if not woorden:
        return {**rij, "woorden": "", "gevonden": None}
    import urllib.error

    from doublecheck import berichtcontrole as bc

    domein = next((d for d in sorted(bc.GEEN_TOEGANG) if rij["site"] == d or rij["site"].endswith("." + d)), rij["site"])
    q = urllib.parse.urlencode({"query": f"{woorden} domainis:{domein}", "mode": "artlist", "format": "json",
                                "maxrecords": 75, "timespan": "3months"})
    req = urllib.request.Request("https://api.gdeltproject.org/api/v2/doc/doc?" + q,
                                 headers={"User-Agent": "FactizResearch/0.1 (https://factiz.org; research)"})
    for poging in range(6):
        time.sleep(6 + 30 * poging)  # GDELT vraagt hoogstens één verzoek per vijf seconden; bij een weigering langer
        try:
            tekst = urllib.request.urlopen(req, timeout=60).read().decode("utf-8", "replace")
            break
        except urllib.error.HTTPError as fout:
            if fout.code != 429:
                raise
    else:
        return {**rij, "woorden": woorden, "gevonden": None, "fout": "GDELT bleef weigeren"}
    try:
        artikelen = json.loads(tekst).get("articles", [])
    except json.JSONDecodeError:
        return {**rij, "woorden": woorden, "gevonden": None, "fout": tekst[:200]}
    return {**rij, "woorden": woorden, "gevonden": any(zelfde_link(rij["url"], a.get("url", "")) for a in artikelen),
            "aantal": len(artikelen)}


def _vondsten(rijen: list[dict], sites: dict) -> tuple[dict, dict]:  # pragma: no cover - op de bestanden
    r1 = {r["id"]: r for r in _jsonl(UIT / "route1.jsonl")}
    r2 = {r["id"]: r for r in _jsonl(UIT / "route2.jsonl")}
    vondsten, route2 = {}, {}
    for s in rijen:
        if s["id"] in r2 and r2[s["id"]]["paginas"] is not None:
            route2[s["id"]] = overname_vondst(s["kop"], s["site"], r2[s["id"]]["paginas"], sites)
        vondsten[s["id"]] = {"route 1": bool(r1.get(s["id"], {}).get("gevonden")),
                             "route 2": bool(route2.get(s["id"], {}).get("bij site"))}
    return vondsten, route2


def main() -> None:  # pragma: no cover - CLI, netwerk en de Batch API
    import argparse

    from doublecheck import berichtcontrole as bc
    from doublecheck import betatoets as t
    from doublecheck.leraar import MODELLEN
    from doublecheck.modelpoort import kosten_batch

    parser = argparse.ArgumentParser(description="De koppen van de dichte sites, een voormeting (PLAN #32.3f)")
    parser.add_argument("stap", choices=("set", "wikipedia", "indienen", "ophalen", "portal", "gdelt", "lezen", "tellen"))
    parser.add_argument("--proef", type=int, default=0)
    args = parser.parse_args()
    UIT.mkdir(parents=True, exist_ok=True)
    if args.stap == "set":
        uit = _maak_set()
        print(len(uit), Counter(r["sub"] for r in uit), Counter(r["set"] for r in uit))
        return
    rijen = _jsonl(UIT / "set.jsonl")
    sites = bc.herkomstlijst()["sites"]
    if args.stap == "wikipedia":
        klaar = {r["id"] for r in _jsonl(UIT / "route1.jsonl")}
        for i, s in enumerate(r for r in rijen if r["id"] not in klaar):
            rij = _route1(s)
            _voeg_toe(UIT / "route1.jsonl", rij)
            print(f"{i + 1}: {s['id']} {s['site']} {'GEVONDEN' if rij['gevonden'] else '-'} {rij['paginas'][:2]}")
        return
    if args.stap == "portal":
        gekozen = _portal()
        (UIT / "portal.jsonl").write_text("".join(json.dumps(r) + "\n" for r in gekozen), encoding="utf-8")
        print(len(gekozen), Counter(r["site"] for r in gekozen))
        return
    if args.stap == "gdelt":
        klaar = {r["url"] for r in _jsonl(UIT / "gdelt.jsonl")}
        for r in _jsonl(UIT / "portal.jsonl"):
            if r["url"] not in klaar:
                uit = _gdelt(r)
                _voeg_toe(UIT / "gdelt.jsonl", uit)
                print(r["site"], uit["woorden"] or "(geen woorden)", uit["gevonden"], uit.get("aantal", ""))
        return
    import anthropic

    from doublecheck.varianten import laad_sleutel

    laad_sleutel()
    client = anthropic.Anthropic()
    per_cid = {f"k{VRAAGVERSIE}-{t.batch_id(s['id'])}": s for s in rijen}
    if args.stap == "indienen":
        ingediend = {i for b in _jsonl(UIT / "batches.jsonl") for i in b["ids"]}
        verzoeken = [{"custom_id": cid, "params": {
            "model": MODELLEN["haiku"]["id"], "max_tokens": 4_000,
            "messages": [{"role": "user", "content": VRAAG.format(site=s["site"], tekst=s["tekst"], max=MAX_PAGINAS)}],
            "tools": [{"type": "web_search_20250305", "name": "web_search", "max_uses": 1}]}}
            for cid, s in per_cid.items() if cid not in ingediend]
        verzoeken = verzoeken[: args.proef] if args.proef else verzoeken
        geschat = len(verzoeken) * SCHATTING
        if not verzoeken:
            raise SystemExit("niets in te dienen")
        if al_uitgegeven() + geschat > BUDGET:
            raise Weigering(f"geweigerd: ${al_uitgegeven():.2f} plus ${geschat:.2f} is meer dan ${BUDGET:.2f}")
        batch = client.messages.batches.create(requests=verzoeken)
        _voeg_toe(UIT / "batches.jsonl", {"id": batch.id, "schatting": round(geschat, 3),
                                          "ids": [r["custom_id"] for r in verzoeken]})
        print(f"batch {batch.id}: {len(verzoeken)} verzoeken; samen ${al_uitgegeven():.2f} van ${BUDGET:.2f}")
        return
    if args.stap == "ophalen":
        alle = _jsonl(UIT / "batches.jsonl")
        for b in alle:
            if b.get("werkelijk") is not None:
                continue
            if client.messages.batches.retrieve(b["id"]).processing_status != "ended":
                print(f"batch {b['id']} loopt nog")
                continue
            werkelijk = 0.0
            for r in client.messages.batches.results(b["id"]):
                if r.result.type != "succeeded":
                    print(f"{r.custom_id}: {r.result.type}")
                    continue
                blokken = [x.model_dump() for x in r.result.message.content]
                kosten = kosten_batch(bc.gebruik_uit(r.result.message), "haiku")
                werkelijk += kosten
                tekst = "".join(x.get("text") or "" for x in blokken if x.get("type") == "text")
                _voeg_toe(UIT / "route2.jsonl", {"id": per_cid[r.custom_id]["id"], "paginas": lees_overname(blokken),
                                                 "antwoord": tekst[-2500:], "kosten": round(kosten, 5)})
            b["werkelijk"] = round(werkelijk, 4)
        (UIT / "batches.jsonl").write_text("".join(json.dumps(b) + "\n" for b in alle), encoding="utf-8")
        print(f"uitgegeven ${al_uitgegeven():.2f} van ${BUDGET:.2f}")
        return
    vondsten, route2 = _vondsten(rijen, sites)
    labels = lees_labels()
    if args.stap == "lezen":
        r1 = {r["id"]: r for r in _jsonl(UIT / "route1.jsonl")}
        for s in rijen:
            v = vondsten[s["id"]]
            for r in ("route 1", "route 2"):
                lezen = (s["sub"] in ("B-kop", "B-krant") and v[r]) or (s["sub"] == "A" and r == "route 2" and v[r])
                if lezen and (s["id"], r) not in labels:
                    bewijs = r1[s["id"]]["vondst"] if r == "route 1" else \
                        [p for p in _jsonl(UIT / "route2.jsonl") if p["id"] == s["id"]][-1]["paginas"]
                    print(f"\n=== {s['id']} [{s['sub']}] {r} bij {s['site']}\nKOP: {s['kop']}\nECHT: {s['echte kop']}\n"
                          f"BEWIJS: {json.dumps(bewijs, ensure_ascii=False)[:900]}")
            if s["sub"] == "B-feit" and route2.get(s["id"], {}).get("verschillen") and (s["id"], "feit") not in labels:
                print(f"\n=== {s['id']} [B-feit] feit\nVERVALST: {s['detail']}\nROUTE 2: {route2[s['id']]['verschillen']}")
        return
    gdelt = _jsonl(UIT / "gdelt.jsonl")
    g3 = {"n": len(gdelt), "met woorden": sum(r["gevonden"] is not None for r in gdelt),
          "gevonden": sum(r["gevonden"] is True for r in gdelt),
          "per site": {s: [sum(r["gevonden"] is True for r in gdelt if r["site"] == s),
                           sum(r["site"] == s for r in gdelt)] for s in sorted({r["site"] for r in gdelt})}}
    uit = telling(rijen, vondsten, labels, g3)
    andere = Counter(s["sub"] for s in rijen if route2.get(s["id"], {}).get("andere site"))
    feit = Counter(labels.get((s["id"], "feit")) for s in rijen if s["sub"] == "B-feit" and route2.get(s["id"], {}).get("verschillen"))
    goed = Counter(route2[s["id"]]["goede sites"] for s in rijen if s["sub"] == "A" and s["id"] in route2)
    uit |= {"andere site gevonden (route 2)": dict(andere), "veranderd feit (route 2)": dict(feit),
            "goede sites per echt artikel": dict(sorted(goed.items())), "kosten": round(al_uitgegeven(), 2)}
    print(json.dumps(uit, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
