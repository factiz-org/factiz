"""Het model leest, Factiz zoekt het bonnetje (PLAN #30.12).

§124 liet zien dat een taalmodel de bewering in een beeld of artikel wel ziet,
en Factiz niet: Haiku vond 43% van de beelden, Factiz 1%, maar Haiku zonder
bonnetje en met vals alarm. Deze meting zet de twee achter elkaar: Haiku 5.5
schrijft alleen de bewering op (één zin, geen oordeel), en die zin gaat door
het echte `/resolve` met `config.toml`. Alleen een `matched` met bonnetje telt.

Openbare data, offline (B26): de artikelen van de netwerktoets, de
M4FC-beelden (de ijkset), een steekproef van de stiltepools en N3. Nooit iets
van een gebruiker (DR3); in productie zou een lokaal model de zin schrijven
(stap 3 van #30.12).

    python -m doublecheck.bewering basiswaarde
    python -m doublecheck.bewering plan
    python -m doublecheck.bewering indienen [--proef 50] [--budget 1.0] [--opnieuw]
    python -m doublecheck.bewering ophalen
    python -m doublecheck.bewering meten [--alleen-ids-met-antwoord]
    python -m doublecheck.bewering lezen
    python -m doublecheck.bewering tellen

Stap 2b (Haiku kiest uit de vijf kandidaten van Factiz; de tweede vraag voor de
beelden zonder zin):

    python -m doublecheck.bewering indienen-v2|ophalen-v2 [--proef 50]
    python -m doublecheck.bewering kandidaten --vraag v1|v2
    python -m doublecheck.bewering beslis-indienen|beslis-ophalen --vraag v1|v2 [--proef 50]
    python -m doublecheck.bewering lezen-2b|tellen-2b [--ongelezen-als-fout]
"""

from __future__ import annotations

import base64
import json
import random
from collections import Counter
from pathlib import Path

PROMPTVERSIE = "bewering-v1"
MODEL = "claude-haiku-5-5"
PRIJS = {"in": 0.05, "uit": 0.25}  # batchprijs, dollar per miljoen tokens (zoals standaardmodel, 2026-10-17)
SYSTEEM = ("You extract the claim from social media posts, images and articles for a search engine that looks "
           "up existing fact-checks. You never assess whether a claim is accurate.")
VRAAG = ("Write down the main factual claim that this image or text makes, as one plain sentence in English, the "
         "way a fact-checker would summarise it before checking it (who or what, where and when, if stated). Use "
         "only what the image or text itself says or shows; add nothing from your own knowledge. Do not judge "
         "whether the claim is accurate. If it makes no checkable factual claim (for example an advertisement, a "
         "personal message, or a photo that does not present anything as fact), set doet_bewering to false and "
         "leave bewering empty.")
_SCHEMA = {"type": "object",
           "properties": {"doet_bewering": {"type": "boolean"}, "bewering": {"type": "string"}},
           "required": ["doet_bewering", "bewering"], "additionalProperties": False}
WORTEL = Path(__file__).resolve().parent.parent
UIT = WORTEL / "data" / "bewering"
LABELS = WORTEL / "docs" / "steekproeven" / "30.12-bewering.json"
RELEASERUN = "factiz-rechter-d5-feiten"  # de zeefrun van de releasemotor (§131), dezelfde motor als config.toml
RUWETEST = WORTEL / "data" / "ruwetest-2026-10-14T174458.json"  # per M4FC-beeld: leest de OCR >= 20 tekens?
N1_STEEKPROEF, ZAAD = 5_000, 3003  # dezelfde steekproef als §124
DELEN = ("screenshot met tekst", "foto zonder tekst", "artikel", "tekst")
_MATCH = ("gevonden", "ander")
_ROOD = ("rood", "omstreden")


class Weigering(Exception):
    """Tellen kan niet: er is een treffer zonder label."""


def lees_antwoord(tekst: str) -> tuple[str, str | None]:
    """Het antwoord van het model: ("bewering", zin), ("geen", None) als het
    stuk geen toetsbare bewering doet, of ("onleesbaar", None) als het
    antwoord is afgekapt (opnieuw indienen met meer ruimte)."""
    try:
        antwoord = json.loads(tekst)
    except json.JSONDecodeError:
        return "onleesbaar", None
    zin = " ".join(str(antwoord.get("bewering") or "").split())
    if not antwoord.get("doet_bewering") or not zin:
        return "geen", None
    return "bewering", zin


def verzoek(item: dict, max_tokens: int = 200, vraag: str = VRAAG) -> dict:
    if item.get("beeld"):
        pad = Path(item["beeld"])
        soort = {".png": "image/png", ".gif": "image/gif", ".webp": "image/webp"}.get(pad.suffix.lower(), "image/jpeg")
        inhoud = [{"type": "image", "source": {"type": "base64", "media_type": soort,
                                               "data": base64.b64encode(pad.read_bytes()).decode()}},
                  {"type": "text", "text": vraag}]
    else:
        inhoud = [{"type": "text", "text": f"Text:\n{item['tekst']}\n\n{vraag}"}]
    return {"custom_id": item["id"],
            "params": {"model": MODEL, "max_tokens": max_tokens, "system": SYSTEEM,
                       "messages": [{"role": "user", "content": inhoud}],
                       "output_config": {"effort": "low", "format": {"type": "json_schema", "schema": _SCHEMA}}}}


def kosten(items: list[dict], uit_per_stuk: int = 60) -> float:
    vast = (len(SYSTEEM) + len(VRAAG)) // 4 + 20
    tokens = sum(vast + (1_600 if i.get("beeld") else len(i.get("tekst", "")) // 4 + 5) for i in items)
    return (tokens * PRIJS["in"] + len(items) * uit_per_stuk * PRIJS["uit"]) / 1e6


def deel_van(set_: str, sleutel: str, met_tekst: dict[str, bool]) -> str | None:
    """Wat de gebruiker stuurt (PLAN #30.12, stap 1)."""
    if set_ == "P3":
        return "screenshot met tekst" if met_tekst.get(sleutel) else "foto zonder tekst"
    return {"P2": "artikel", "P1": "tekst"}.get(set_)


def combinatie(*uitkomsten: str) -> str:
    """Zoals productie de routes zou gebruiken: eerst de huidige; geeft die
    geen `matched`, dan de volgende. Zonder `matched` blijft het beste staan
    (verwant boven niets)."""
    for u in uitkomsten:
        if u in _MATCH:
            return u
    return "verwant" if "verwant" in uitkomsten else "niets"


def paar(sleutel: str, kandidaat: str | None) -> str:
    """Een label hoort bij een stuk én zijn treffer, zodat een label van een
    andere treffer van hetzelfde stuk niet meekomt."""
    return f"{sleutel}|{kandidaat}"


def _label(rij: dict, labels: dict[str, str], van_huidig: bool) -> str:
    if van_huidig:
        label = rij.get("huidig_label")
        if label is None:
            raise Weigering(f"geen label in de zeef voor {rij['sleutel']} (huidige route)")
        return label
    label = labels.get(paar(rij["sleutel"], rij.get("kandidaat")))
    if label is None:
        raise Weigering(f"geen label voor {paar(rij['sleutel'], rij.get('kandidaat'))}; eerst `lezen`")
    return label


def telling(rijen: list[dict], labels: dict[str, str]) -> dict:
    """Per helft: per deel de huidige route, de bewering en de combinatie;
    vals alarm op webtekst; rood naast ware zinnen (de kern apart); en de
    precisie van de combinatie. Weigert zolang een treffer op een andere
    claim of op webtekst geen label heeft."""
    uit: dict = {}
    for r in rijen:
        h = uit.setdefault(r["helft"], {"delen": {}, "N1": {"n": 0, "matched": 0, "terecht": 0, "vals": 0},
                                        "N3": {"n": 0, "rood": 0, "kern_rood": 0},
                                        "precisie": {"juist": 0, "fout": 0}})
        if r["set"] in ("P2", "P3"):
            d = h["delen"].setdefault(r["deel"], {k: {"n": 0, "gevonden": 0, "zelfde": 0, "anders": 0,
                                                      "verwant": 0, "niets": 0}
                                                  for k in ("huidig", "bewering", "combinatie")})
            samen = combinatie(r["huidig"], r["uitkomst"])
            for route, uitkomst, van_huidig in (("huidig", r["huidig"], True), ("bewering", r["uitkomst"], False),
                                                ("combinatie", samen, r["huidig"] in _MATCH)):
                d[route]["n"] += 1
                if uitkomst == "ander":
                    uitkomst = "zelfde" if _label(r, labels, van_huidig) == "zelfde" else "anders"
                d[route][uitkomst] += 1
                if route == "combinatie":
                    h["precisie"]["juist"] += uitkomst in ("gevonden", "zelfde")
                    h["precisie"]["fout"] += uitkomst == "anders"
        elif r["set"] == "N1":
            h["N1"]["n"] += 1
            van_huidig = r["huidig"] == "matched"
            if van_huidig or r["uitkomst"] == "matched":
                h["N1"]["matched"] += 1
                soort = "terecht" if _label(r, labels, van_huidig) == "terecht" else "vals"
                h["N1"][soort] += 1
                h["precisie"]["juist" if soort == "terecht" else "fout"] += 1
        elif r["set"] == "N3":
            h["N3"]["n"] += 1
            uitkomst = r["huidig"] if r["huidig"] in _ROOD else r["uitkomst"]
            if uitkomst in _ROOD:
                h["N3"]["rood"] += 1
                h["N3"]["kern_rood"] += r.get("bron") == "kern"
                h["precisie"]["fout"] += 1
    return uit


# --- stap 2b: Haiku kiest uit de kandidaten van Factiz ------------------------------

BESLIS_VERSIE = "beslisser-v1"
VLOER_KANDIDATEN = 0.50
BESLIS_SYSTEEM = ("You compare a claim with claims that fact-checkers have checked, for a search engine that "
                  "returns existing fact-checks. You never assess whether a claim is accurate.")
BESLIS_VRAAG = ("Which checked claim makes the same assertion as the claim above: the same subject, the same "
                "event or moment, the same core statement? A checked claim that is broader, narrower in a way "
                "that changes what is asserted, about another event, another time or place, or that says the "
                "opposite, is not the same. Answer with its number in keuze, or 0 if none is the same or if "
                "you are not sure.")
_BESLIS_SCHEMA = {"type": "object", "properties": {"keuze": {"type": "integer"}}, "required": ["keuze"],
                  "additionalProperties": False}
VRAAG_V2 = ("Write down the main factual claim that this image makes, as one plain sentence in English, the way a "
            "fact-checker would summarise it before checking it (who or what, where and when, if stated). If the "
            "image is a screenshot of a social media post, a message or a news item, always write the claim the "
            "post makes, also when it is phrased as a question, an opinion or a suggestion. Use only what the "
            "image itself says or shows; add nothing from your own knowledge. Do not judge whether the claim is "
            "accurate. Only if the image makes no claim at all (for example a plain photo without any caption, "
            "or an advertisement), set doet_bewering to false and leave bewering empty.")
ROUTES = ("huidig", "bewering", "beslisser", "tweede vraag")


def beslis_vraag(zin: str, kandidaten: list[dict]) -> str:
    """De vraag aan de beslisser: de zin en de genummerde kandidaten, elk met
    de datum van de check, nooit het oordeel (PLAN #30.12, stap 2b)."""
    regels = "\n".join(f"{n}. {' '.join(k['tekst'].split())[:500]} (checked {k['datum']})"
                       for n, k in enumerate(kandidaten, 1))
    return (f"Claim from a post, image or text:\n{zin}\n\nClaims that fact-checkers have checked:\n{regels}"
            f"\n\n{BESLIS_VRAAG}")


def lees_keuze(tekst: str, aantal: int) -> int | None:
    """Het nummer dat de beslisser koos (0 is geen), of None als het antwoord
    onleesbaar is of buiten de kandidaten valt."""
    try:
        keuze = json.loads(tekst).get("keuze")
    except (json.JSONDecodeError, AttributeError):
        return None
    return keuze if isinstance(keuze, int) and 0 <= keuze <= aantal else None


def uitkomst_keuze(set_: str, claim: str | None, verwacht: set[str], tegenspraak: bool, klasse: str | None) -> str:
    """Een keuze van de beslisser als uitkomst, zoals `categorize` haar zou
    geven: de tegenspraakregel (DR8) maakt er hoogstens verwant van; naast een
    ware zin telt een rode of omstreden check als fout (zonder feitenlaag)."""
    if claim is None:
        return {"N1": "none"}.get(set_, "niets")
    if tegenspraak:
        return {"N1": "related"}.get(set_, "verwant")
    if set_ in ("P2", "P3"):
        return "gevonden" if claim in verwacht else "ander"
    if set_ == "N3":
        return klasse if klasse in _ROOD else "matched"
    return "matched"


def _winnaar(set_: str, routes: list[dict]) -> dict | None:
    for r in routes:
        u = r["uitkomst"]
        if (set_ in ("P2", "P3") and u in _MATCH) or (set_ == "N1" and u == "matched") \
                or (set_ == "N3" and u not in ("niets", "verwant", "related", "none")):
            return r
    return None


def _label_route(sleutel: str, route: dict, labels: dict[str, str]) -> str:
    label = route.get("label") or labels.get(paar(sleutel, route.get("kandidaat")))
    if label is None:
        raise Weigering(f"geen label voor {paar(sleutel, route.get('kandidaat'))} ({route['route']}); eerst lezen")
    return label


def telling_routes(rijen: list[dict], labels: dict[str, str]) -> dict:
    """Per helft en per stap (de routes opgeteld in de volgorde van
    productie, de eerste `matched` telt): per deel, vals alarm op webtekst,
    rood naast ware zinnen en de precisie. Weigert zolang een keuze op een
    andere claim of op webtekst geen label heeft."""
    namen = [n for n in ROUTES if any(r["route"] == n for x in rijen for r in x["routes"])]
    uit: dict = {}
    for x in rijen:
        h = uit.setdefault(x["helft"], {"stappen": [
            {"route": n, "delen": {}, "N1": {"n": 0, "matched": 0, "terecht": 0, "vals": 0},
             "N3": {"n": 0, "rood": 0, "kern_rood": 0}, "precisie": {"juist": 0, "fout": 0}} for n in namen]})
        for k, stap in enumerate(h["stappen"]):
            tot = [r for r in x["routes"] if r["route"] in namen[:k + 1]]
            w = _winnaar(x["set"], tot)
            if x["set"] in ("P2", "P3"):
                d = stap["delen"].setdefault(x["deel"], {"n": 0, "gevonden": 0, "zelfde": 0, "anders": 0,
                                                         "verwant": 0, "niets": 0})
                if w is None:
                    u = "verwant" if any(r["uitkomst"] == "verwant" for r in tot) else "niets"
                elif w["uitkomst"] == "ander":
                    u = "zelfde" if _label_route(x["sleutel"], w, labels) == "zelfde" else "anders"
                else:
                    u = "gevonden"
                d["n"] += 1
                d[u] += 1
                stap["precisie"]["juist"] += u in ("gevonden", "zelfde")
                stap["precisie"]["fout"] += u == "anders"
            elif x["set"] == "N1":
                stap["N1"]["n"] += 1
                if w is not None:
                    soort = "terecht" if _label_route(x["sleutel"], w, labels) == "terecht" else "vals"
                    stap["N1"]["matched"] += 1
                    stap["N1"][soort] += 1
                    stap["precisie"]["juist" if soort == "terecht" else "fout"] += 1
            elif x["set"] == "N3":
                stap["N3"]["n"] += 1
                if w is not None and w["uitkomst"] in _ROOD:
                    stap["N3"]["rood"] += 1
                    stap["N3"]["kern_rood"] += x.get("bron") == "kern"
                    stap["precisie"]["fout"] += 1
    return uit


def hoofdgetal(p1: float, p2: float, p3: float) -> float:
    """Het ongewogen gemiddelde van tekst, artikelen en beelden (B33)."""
    return (p1 + p2 + p3) / 3


# --- de berg -------------------------------------------------------------------

def met_tekst_per_sleutel() -> dict[str, bool]:  # pragma: no cover - leest de ijkset
    from doublecheck.ruwetest import m4fc_items
    from doublecheck.zeef import P3_MAP

    beelden = m4fc_items(P3_MAP)
    ruw = json.loads(RUWETEST.read_text(encoding="utf-8"))
    if len(ruw) != len(beelden) or any(b.url != r["url"] for b, r in zip(beelden, ruw)):
        raise Weigering(f"{RUWETEST.name} loopt niet gelijk met de M4FC-beelden")
    return {f"P3:{b.pad.stem}": r["tekst"] for b, r in zip(beelden, ruw)}


def items() -> list[dict]:  # pragma: no cover - op de berg van de zeef
    """P2, P3, de steekproef van N1 en N3, in een vaste volgorde. Eén keer
    opgebouwd en bewaard in `items.jsonl` (de stiltepools lezen kost minuten)."""
    pad = UIT / "items.jsonl"
    if pad.exists():
        return [json.loads(r) for r in pad.read_text(encoding="utf-8").split("\n") if r]
    from doublecheck import zeef
    from doublecheck.feitenbasis import lees_kern, lees_paren, n3_items
    from doublecheck.netwerktoets import items as artikel_items
    from doublecheck.ruwetest import m4fc_items
    from doublecheck.variantenbatch import lees_regels

    met_tekst = met_tekst_per_sleutel()
    uit = []
    artikelen = [json.loads(x) for x in (zeef.P2_MAP / "artikelen.jsonl").read_text(encoding="utf-8").split("\n")
                 if x.strip()]
    for i, a in enumerate(artikel_items(artikelen)):
        sleutel = f"P2:{a.artikel}#{a.claim_id}"
        uit.append({"id": f"P2-{i:05d}", "set": "P2", "sleutel": sleutel, "helft": zeef.helft(f"zaak:{a.claim_id}"),
                    "deel": "artikel", "tekst": a.kop_inleiding, "claim": a.claim_id, "bonnetje": a.bonnetje})
    for i, b in enumerate(m4fc_items(zeef.P3_MAP)):
        sleutel = f"P3:{b.pad.stem}"
        uit.append({"id": f"P3-{i:05d}", "set": "P3", "sleutel": sleutel, "helft": zeef.helft(f"zaak:{b.claim_id}"),
                    "deel": deel_van("P3", sleutel, met_tekst), "beeld": str(b.pad), "claim": b.claim_id,
                    "bonnetje": b.url})
    stukken = [(pool.name, r) for pool in zeef.POOLS for r in lees_regels(pool)]
    random.Random(ZAAD).shuffle(stukken)
    for i, (pool, r) in enumerate(stukken[:N1_STEEKPROEF]):
        sleutel = f"N1:{pool}:{r['claim_id']}"
        uit.append({"id": f"N1-{i:05d}", "set": "N1", "sleutel": sleutel, "helft": zeef.helft(sleutel),
                    "tekst": r["varianten"][0]["tekst"]})
    for i, n in enumerate(n3_items(lees_kern(), lees_paren())):
        uit.append({"id": f"N3-{i:05d}", "set": "N3", "sleutel": n["sleutel"], "helft": n["helft"],
                    "tekst": n["tekst"], "bron": n["bron"]})
    UIT.mkdir(parents=True, exist_ok=True)
    pad.write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in uit), encoding="utf-8")
    return uit


def _jsonl(pad: Path) -> list[dict]:
    if not pad.exists():
        return []
    inhoud = pad.read_text(encoding="utf-8")
    return [json.loads(r) for r in inhoud[:inhoud.rfind("\n") + 1].split("\n") if r]


def antwoorden(naam: str = "antwoorden.jsonl") -> dict[str, tuple[str, str | None]]:
    """Per stuk de laatste leesbare uitkomst van het model (`antwoorden-v2.jsonl`
    voor de tweede vraag)."""
    uit: dict[str, tuple[str, str | None]] = {}
    for r in _jsonl(UIT / naam):
        if r["status"] != "onleesbaar" or r["id"] not in uit:
            uit[r["id"]] = (r["status"], r.get("bewering"))
    return uit


def _huidig() -> dict[str, dict]:  # pragma: no cover - leest de zeefrun van de releasemotor
    """Per sleutel de uitkomst van de huidige route in de zeef (§131), met het
    label van de zeef als die een andere claim of webtekst `matched` gaf."""
    from doublecheck import zeef

    map_ = zeef.UIT / RELEASERUN
    labels = {r["sleutel"]: r["label"] for r in json.loads(zeef.LABELS.read_text(encoding="utf-8"))["labels"]}
    uit = {}
    for s in ("P1", "P2", "P3", "N1", "N3"):
        for r in zeef._lees(map_ / f"{s}.jsonl"):
            uit[r["sleutel"]] = {"uitkomst": r["uitkomst"], "kandidaat": r.get("kandidaat"),
                                 "label": labels.get(r["sleutel"]), "helft": r.get("helft")}
    return uit


# --- het echte pad ---------------------------------------------------------------

def meten() -> None:  # pragma: no cover - het echte pad, met de modellen
    import sqlite3

    from fastapi.testclient import TestClient

    from doublecheck import api
    from doublecheck.clustering import cluster_members
    from doublecheck.config import load_config
    from doublecheck.feitenbasis import n3_uitkomst
    from doublecheck.ruwetest import antwoord_of_fout, beoordeel
    from doublecheck.zeef import uitkomst_resolver

    config = load_config(None)
    api.app.dependency_overrides[api.get_config] = lambda: config
    api.limiter.enabled = False
    client = TestClient(api.app)
    conn = sqlite3.connect("file:doublecheck.db?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    zinnen = antwoorden()
    pad = UIT / "meten.jsonl"
    # Een afgekapt antwoord is nog geen uitkomst: het wacht op `indienen
    # --opnieuw`. Een regel die met zo'n antwoord gemeten werd, gaat eruit zodra
    # er een leesbaar antwoord is (de eerste run telde 189 afgekapte als niets).
    oud = _jsonl(pad)
    vervangen = [r for r in oud if r["status"] == "onleesbaar" and zinnen.get(r["id"], ("onleesbaar",))[0] != "onleesbaar"]
    if vervangen:
        houden = [r for r in oud if r not in vervangen]
        pad.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in houden), encoding="utf-8")
        print(f"meten: {len(vervangen)} regels van afgekapte antwoorden opnieuw", flush=True)
    gedaan = {r["id"] for r in _jsonl(pad)}
    volgorde = {"P3": 0, "P2": 1, "N3": 2, "N1": 3}
    te_doen = sorted((i for i in items() if zinnen.get(i["id"], ("onleesbaar",))[0] != "onleesbaar"
                      and i["id"] not in gedaan), key=lambda i: volgorde[i["set"]])
    print(f"meten: {len(te_doen)} stukken", flush=True)
    with pad.open("a", encoding="utf-8") as uit:
        for n, item in enumerate(te_doen, 1):
            status, zin = zinnen[item["id"]]
            kandidaat = gelijkenis = None
            if zin is None:
                uitkomst = {"N1": "none"}.get(item["set"], "niets")
            else:
                antwoord = antwoord_of_fout(client.post("/resolve", json={"text": zin}))
                kandidaat, gelijkenis = (antwoord.get("claim") or {}).get("id"), antwoord.get("similarity")
                if item["set"] in ("P2", "P3"):
                    verwacht = cluster_members(conn, item["claim"]) | {item["claim"]}
                    uitkomst = uitkomst_resolver(beoordeel(antwoord, item["bonnetje"], verwacht))
                elif item["set"] == "N1":
                    uitkomst = antwoord.get("category")
                else:
                    uitkomst = n3_uitkomst(antwoord)
            uit.write(json.dumps({"id": item["id"], "set": item["set"], "sleutel": item["sleutel"],
                                  "helft": item["helft"], "deel": item.get("deel"), "bron": item.get("bron"),
                                  "status": status, "uitkomst": uitkomst, "kandidaat": kandidaat,
                                  "gelijkenis": gelijkenis}, ensure_ascii=False) + "\n")
            if n % 100 == 0:
                uit.flush()
                print(f"  {n}/{len(te_doen)}", flush=True)


def _lees_labels() -> dict[str, str]:
    if not LABELS.exists():
        return {}
    return {paar(r["sleutel"], r["kandidaat"]): r["label"]
            for r in json.loads(LABELS.read_text(encoding="utf-8"))["labels"]}


def rijen_om_te_tellen() -> list[dict]:  # pragma: no cover - leest de zeefrun en de meting
    huidig = _huidig()
    uit = []
    for r in _jsonl(UIT / "meten.jsonl"):
        h = huidig.get(r["sleutel"], {})
        standaard = "none" if r["set"] == "N1" else "niets"
        uit.append({**r, "huidig": h.get("uitkomst", standaard), "huidig_kandidaat": h.get("kandidaat"),
                    "huidig_label": h.get("label")})
    return uit


def lezen() -> None:  # pragma: no cover - drukt teksten af om te labelen, schrijft niets
    import sqlite3

    conn = sqlite3.connect("file:doublecheck.db?mode=ro", uri=True)
    tekst = dict(conn.execute("SELECT claim_id, canonical_text FROM claim"))
    labels, zinnen = _lees_labels(), antwoorden()
    stukken = {i["id"]: i for i in items()}
    open_ = [r for r in _jsonl(UIT / "meten.jsonl")
             if r["uitkomst"] in ("ander", "matched") and paar(r["sleutel"], r["kandidaat"]) not in labels]
    for r in open_:
        item = stukken[r["id"]]
        print(f"\n[{r['set']} · {r['helft']} · {r.get('deel') or ''}] {paar(r['sleutel'], r['kandidaat'])}"
              f" ({r['gelijkenis']})")
        print(f"  ZIN VAN HET MODEL: {zinnen[r['id']][1]}")
        if item.get("beeld"):
            print(f"  BEELD: {item['beeld']}")
        else:
            print(f"  STUK: {item['tekst'][:500]}")
        if item.get("claim"):
            print(f"  VERWACHT: {tekst.get(item['claim'], '?')[:300]}")
        print(f"  GEVONDEN: {tekst.get(r['kandidaat'], '?')[:300]}")
    print(f"\n{len(open_)} te labelen in {LABELS}")


def _p1_per_helft() -> dict[str, tuple[int, int]]:  # pragma: no cover
    from doublecheck import zeef

    tel: dict[str, list[int]] = {}
    for r in zeef._lees(zeef.UIT / RELEASERUN / "P1.jsonl"):
        t = tel.setdefault(r["helft"], [0, 0])
        t[0] += r["uitkomst"] == "gevonden"
        t[1] += 1
    return {h: (g, n) for h, (g, n) in tel.items()}


def tellen() -> dict:  # pragma: no cover - CLI
    from doublecheck.benchmark import upper_bound_95

    uitslag = telling(rijen_om_te_tellen(), _lees_labels())
    p1 = _p1_per_helft()
    for helft in ("ontwikkel", "toets"):
        h = uitslag.get(helft)
        if not h:
            continue
        print(f"\n{helft}:")
        delen = h["delen"]
        for d in DELEN[:3]:
            if d not in delen:
                continue
            regel = " · ".join(f"{route} {delen[d][route]['gevonden']} ({delen[d][route]['gevonden'] / delen[d][route]['n']:.1%})"
                               for route in ("huidig", "bewering", "combinatie"))
            print(f"  {d} (n {delen[d]['combinatie']['n']}): {regel}; anders in de combinatie {delen[d]['combinatie']['anders']}")

        def kans(namen, route):
            g = sum(delen[d][route]["gevonden"] for d in namen if d in delen)
            n = sum(delen[d][route]["n"] for d in namen if d in delen)
            return g / n if n else 0.0

        g1, n1 = p1.get(helft, (0, 1))
        for route in ("huidig", "combinatie"):
            p2, p3 = kans(["artikel"], route), kans(["screenshot met tekst", "foto zonder tekst"], route)
            h[f"hoofdgetal_{route}"] = hoofdgetal(g1 / n1, p2, p3)
            print(f"  hoofdgetal {route}: {h[f'hoofdgetal_{route}']:.1%} (P1 {g1 / n1:.1%}, P2 {p2:.1%}, P3 {p3:.1%})")
        pr = h["precisie"]
        totaal = pr["juist"] + pr["fout"]
        if totaal:
            print(f"  precisie: {pr['juist']} van {totaal} juist ({pr['juist'] / totaal:.1%}),"
                  f" bovengrens fout {upper_bound_95(pr['fout'], totaal):.1%}")
        print(f"  N1: {h['N1']}; N3: {h['N3']}")
    (UIT / "uitslag.json").write_text(json.dumps(uitslag, ensure_ascii=False, indent=1), encoding="utf-8")
    return uitslag


def basiswaarde() -> dict:  # pragma: no cover - leest de zeefrun en §124
    """Stap 1 van #30.12: per helft en per soort invoer de huidige motor
    (§131) en Haiku als standaardmodel (§124, dezelfde kant, zonder bonnetje)."""
    import os

    from doublecheck import standaardmodel, zeef

    met_tekst = met_tekst_per_sleutel()
    uit: dict = {}
    for s in ("P1", "P2", "P3"):
        for r in zeef._lees(zeef.UIT / RELEASERUN / f"{s}.jsonl"):
            d = uit.setdefault(r["helft"], {}).setdefault(deel_van(s, r["sleutel"], met_tekst),
                                                          {"factiz": [0, 0], "haiku": [0, 0]})
            d["factiz"][0] += r["uitkomst"] == "gevonden"
            d["factiz"][1] += 1
    oordeel = {}
    for r in (standaardmodel.UIT / "haiku" / "antwoorden.jsonl").read_text(encoding="utf-8").splitlines():
        r = json.loads(r)
        if r["oordeel"] != "onleesbaar" or r["id"] not in oordeel:
            oordeel[r["id"]] = r["oordeel"]
    for i in standaardmodel.items("factiz-1", os.environ.get("DOUBLECHECK_DB", "doublecheck.db")):
        if i["set"] not in ("P1", "P2", "P3") or i["id"] not in oordeel:
            continue
        if i.get("verwacht") not in ("rood", "midden", "groen"):
            continue
        d = uit.setdefault(i["helft"], {}).setdefault(deel_van(i["set"], i["sleutel"], met_tekst),
                                                      {"factiz": [0, 0], "haiku": [0, 0]})
        d["haiku"][0] += standaardmodel.uitkomst(i["set"], i["verwacht"], oordeel[i["id"]]) == "gevonden"
        d["haiku"][1] += 1
    for helft, delen in uit.items():
        print(f"\n{helft}:")
        for d in DELEN:
            if d in delen:
                f, h = delen[d]["factiz"], delen[d]["haiku"]
                print(f"  {d:22} Factiz {f[0]:4} van {f[1]:4} ({f[0] / max(f[1], 1):6.1%})"
                      f" · Haiku {h[0]:4} van {h[1]:4} ({h[0] / max(h[1], 1):6.1%})")
    UIT.mkdir(parents=True, exist_ok=True)
    (UIT / "basiswaarde.json").write_text(json.dumps(uit, ensure_ascii=False, indent=1), encoding="utf-8")
    return uit


# --- stap 2b: de pijplijn -------------------------------------------------------------

def _zinnen(vraag: str) -> dict[str, str]:
    """De zinnen per stuk: van de eerste vraag, of van de tweede."""
    naam = "antwoorden.jsonl" if vraag == "v1" else "antwoorden-v2.jsonl"
    return {k: z for k, (status, z) in antwoorden(naam).items() if status == "bewering" and z}


def kandidaten_zoeken(vraag: str) -> None:  # pragma: no cover - met bge-m3 en de index
    """De vijf beste verschillende claims vanaf de vloer, per zin, over claims
    en varianten met de toelating van de resolver."""
    from doublecheck.config import load_config
    from doublecheck.embedding import fingerprint_texts
    from doublecheck.search import search_texts
    from doublecheck.storage import connect

    config = load_config(None)
    conn = connect("doublecheck.db")
    zinnen = _zinnen(vraag)
    pad = UIT / f"kandidaten-{vraag}.jsonl"
    klaar = {r["id"] for r in _jsonl(pad)}
    ids = [k for k in zinnen if k not in klaar]
    with pad.open("a", encoding="utf-8") as uit:
        for start in range(0, len(ids), 256):
            deel = ids[start:start + 256]
            lijsten = search_texts(conn, fingerprint_texts([zinnen[k] for k in deel], config.model_versions.text_embedding),
                                   5, varianten=True)
            for k, lijst in zip(deel, lijsten):
                uit.write(json.dumps({"id": k, "kandidaten": [[c.claim_id, round(c.similarity, 4)] for c in lijst
                                                              if c.similarity >= VLOER_KANDIDATEN]}) + "\n")
            uit.flush()
            print(f"  kandidaten {vraag}: {min(start + 256, len(ids))} van {len(ids)}", flush=True)


def _claiminfo(conn, claims: set[str]) -> dict[str, dict]:  # pragma: no cover - op de productiedatabase
    uit = {}
    for c in claims:
        tekst = conn.execute("SELECT canonical_text FROM claim WHERE claim_id = ?", (c,)).fetchone()[0]
        datum = conn.execute("SELECT MIN(review_date) FROM factcheck WHERE claim_id = ?", (c,)).fetchone()[0] or "?"
        uit[c] = {"tekst": tekst, "datum": str(datum)[:10]}
    return uit


def beslis_verzoek(id_: str, zin: str, kandidaten: list[dict]) -> dict:
    return {"custom_id": id_,
            # Ruim: het model denkt eerst, en dat telt mee (met 50 was de helft van de proef afgekapt).
            "params": {"model": MODEL, "max_tokens": 1_000, "system": BESLIS_SYSTEEM,
                       "messages": [{"role": "user", "content": [{"type": "text", "text": beslis_vraag(zin, kandidaten)}]}],
                       "output_config": {"effort": "low", "format": {"type": "json_schema", "schema": _BESLIS_SCHEMA}}}}


def _klasse(conn, claim: str) -> str | None:  # pragma: no cover - op de productiedatabase
    from doublecheck.feitenbasis import _KLASSE
    from doublecheck.verdicts import labelklasse_in_tijd

    klasse, _ = labelklasse_in_tijd(conn.execute("SELECT verdict_normalized, review_date FROM factcheck WHERE claim_id = ?",
                                                 (claim,)).fetchall())
    return _KLASSE.get(klasse, "zonder-oordeel")


def _tegenspraak(zin: str, claimtekst: str) -> bool:  # pragma: no cover - dunne laag over relation
    from doublecheck.relation import contradicts, extract_negation_tokens, extract_negations, extract_numbers

    return contradicts(extract_numbers(zin), extract_negations(zin), claimtekst, artefact_text=zin,
                       artefact_negation_tokens=extract_negation_tokens(zin))


def _routes_om_te_tellen() -> list[dict]:  # pragma: no cover - leest de zeefrun en alle stappen
    import sqlite3

    from doublecheck.clustering import cluster_members

    conn = sqlite3.connect("file:doublecheck.db?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    huidig, stukken = _huidig(), {i["id"]: i for i in items()}
    meting = {r["id"]: r for r in _jsonl(UIT / "meten.jsonl")}
    keuzes = {v: {r["id"]: r for r in _jsonl(UIT / f"beslissingen-{v}.jsonl")} for v in ("v1", "v2")}
    zinnen = {"v1": _zinnen("v1"), "v2": _zinnen("v2")}
    tekst: dict[str, str] = {}
    uit = []
    for id_, m in meting.items():
        i = stukken[id_]
        h = huidig.get(i["sleutel"], {})
        standaard = "none" if i["set"] == "N1" else "niets"
        routes = [{"route": "huidig", "uitkomst": h.get("uitkomst", standaard), "kandidaat": h.get("kandidaat"),
                   "label": h.get("label")},
                  {"route": "bewering", "uitkomst": m["uitkomst"], "kandidaat": m["kandidaat"]}]
        verwacht = cluster_members(conn, i["claim"]) | {i["claim"]} if i.get("claim") else set()
        for v, naam in (("v1", "beslisser"), ("v2", "tweede vraag")):
            k = keuzes[v].get(id_)
            if k is None:
                continue
            claim = k.get("claim")
            if claim is not None and claim not in tekst:
                tekst[claim] = conn.execute("SELECT canonical_text FROM claim WHERE claim_id = ?", (claim,)).fetchone()[0]
            tegen = claim is not None and _tegenspraak(zinnen[v][id_], tekst[claim])
            klasse = _klasse(conn, claim) if claim is not None and i["set"] == "N3" else None
            routes.append({"route": naam, "uitkomst": uitkomst_keuze(i["set"], claim, verwacht, tegen, klasse),
                           "kandidaat": claim, "tegenspraak": tegen})
        uit.append({"set": i["set"], "sleutel": i["sleutel"], "helft": i["helft"], "deel": i.get("deel"),
                    "bron": i.get("bron"), "routes": routes})
    return uit


def _dien_in(client, verzoeken: list[dict], batches: Path, bedrag: float, budget: float, versie: str) -> None:  # pragma: no cover
    if not verzoeken:
        raise SystemExit("niets in te dienen")
    if bedrag > budget:
        raise SystemExit(f"geweigerd: naar schatting ${bedrag:.2f}, boven het budget van ${budget:.2f}")
    batch = client.messages.batches.create(requests=verzoeken)
    with batches.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"id": batch.id, "prompt": versie, "schatting": round(bedrag, 3),
                            "ids": [v["custom_id"] for v in verzoeken]}) + "\n")
    print(f"batch {batch.id}: {len(verzoeken)} stukken, naar schatting ${bedrag:.2f}")


def _haal_op(client, batches: Path, pad: Path, lees, klaar: set[str]) -> int:  # pragma: no cover
    nieuw = 0
    with pad.open("a", encoding="utf-8") as uit:
        for b in reversed(_jsonl(batches)):
            if client.messages.batches.retrieve(b["id"]).processing_status != "ended":
                print(f"batch {b['id']} loopt nog")
                continue
            for r in client.messages.batches.results(b["id"]):
                if r.custom_id in klaar:
                    continue
                tekst = None
                if r.result.type == "succeeded":
                    tekst = next((c.text for c in r.result.message.content if c.type == "text"), "{}")
                regel = lees(r.custom_id, tekst)
                uit.write(json.dumps(regel, ensure_ascii=False) + "\n")
                if regel["status"] != "onleesbaar":
                    klaar.add(r.custom_id)
                nieuw += 1
    return nieuw


def stap_2b(stap: str, vraag: str, proef: int, budget: float, ongelezen: bool = False) -> None:  # pragma: no cover - CLI
    import sqlite3

    if stap == "kandidaten":
        kandidaten_zoeken(vraag)
        return
    if stap == "lezen-2b":
        lezen_2b()
        return
    if stap == "tellen-2b":
        tellen_2b(ongelezen)
        return
    import anthropic

    from doublecheck.varianten import laad_sleutel

    laad_sleutel()
    client = anthropic.Anthropic()
    if stap == "beslis-indienen":
        conn = sqlite3.connect("file:doublecheck.db?mode=ro", uri=True)
        batches = UIT / f"beslis-batches-{vraag}.jsonl"
        ingediend = {i for r in _jsonl(batches) for i in r["ids"]}
        laatste = {}
        for r in _jsonl(UIT / f"beslissingen-{vraag}.jsonl"):
            if r["status"] != "onleesbaar" or r["id"] not in laatste:
                laatste[r["id"]] = r["status"]
        zinnen = _zinnen(vraag)
        lijsten = [r for r in _jsonl(UIT / f"kandidaten-{vraag}.jsonl") if r["kandidaten"]
                   and (r["id"] not in ingediend or laatste.get(r["id"]) == "onleesbaar")]
        if proef:
            per_set: dict[str, list] = {}
            for r in lijsten:
                per_set.setdefault(r["id"][:2], []).append(r)
            lijsten = [r for rs in per_set.values() for r in rs[: max(1, proef // len(per_set))]]
        info = _claiminfo(conn, {c for r in lijsten for c, _ in r["kandidaten"]})
        verzoeken = [beslis_verzoek(r["id"], zinnen[r["id"]], [info[c] for c, _ in r["kandidaten"]]) for r in lijsten]
        tokens = sum(len(v["params"]["messages"][0]["content"][0]["text"]) // 4 + 80 for v in verzoeken)
        _dien_in(client, verzoeken, batches, (tokens * PRIJS["in"] + len(verzoeken) * 20 * PRIJS["uit"]) / 1e6,
                 budget, BESLIS_VERSIE)
        return
    if stap == "beslis-ophalen":
        pad = UIT / f"beslissingen-{vraag}.jsonl"
        lijst = {r["id"]: [c for c, _ in r["kandidaten"]] for r in _jsonl(UIT / f"kandidaten-{vraag}.jsonl")}
        klaar = {r["id"] for r in _jsonl(pad) if r["status"] != "onleesbaar"}

        def lees(id_, tekst):
            keuze = lees_keuze(tekst, len(lijst[id_])) if tekst is not None else None
            if keuze is None:
                return {"id": id_, "status": "onleesbaar", "claim": None, "prompt": BESLIS_VERSIE}
            return {"id": id_, "status": "gekozen" if keuze else "geen", "nummer": keuze,
                    "claim": lijst[id_][keuze - 1] if keuze else None, "prompt": BESLIS_VERSIE}

        print(f"{_haal_op(client, UIT / f'beslis-batches-{vraag}.jsonl', pad, lees, klaar)} nieuw; "
              f"{Counter(r['status'] for r in _jsonl(pad))}")
        # Wie geen kandidaat boven de vloer had, kiest niets, zonder verzoek.
        zonder = [r["id"] for r in _jsonl(UIT / f"kandidaten-{vraag}.jsonl") if not r["kandidaten"]]
        al = {r["id"] for r in _jsonl(pad)}
        with pad.open("a", encoding="utf-8") as uit:
            for id_ in zonder:
                if id_ not in al:
                    uit.write(json.dumps({"id": id_, "status": "geen kandidaat", "claim": None}) + "\n")
        return
    if stap == "indienen-v2":
        al, v2 = antwoorden(), antwoorden("antwoorden-v2.jsonl")
        batches = UIT / "batches-v2.jsonl"
        ingediend = {i for r in _jsonl(batches) for i in r["ids"]}
        # Nieuw, of eerder afgekapt: de tweede vraag geeft lange zinnen (datum en hashtags van de post).
        kies = [i for i in items() if i["set"] == "P3" and al.get(i["id"], ("",))[0] == "geen"
                and (i["id"] not in ingediend or v2.get(i["id"], ("",))[0] == "onleesbaar")]
        if proef:
            kies = kies[:proef]
        _dien_in(client, [verzoek(i, 2_000, VRAAG_V2) for i in kies], batches, kosten(kies), budget, "bewering-v2")
        return
    if stap == "ophalen-v2":
        pad = UIT / "antwoorden-v2.jsonl"
        klaar = {k for k, (status, _) in antwoorden("antwoorden-v2.jsonl").items() if status != "onleesbaar"}

        def lees(id_, tekst):
            status, zin = lees_antwoord(tekst) if tekst is not None else ("fout", None)
            return {"id": id_, "status": status, "bewering": zin, "model": MODEL, "prompt": "bewering-v2"}

        print(f"{_haal_op(client, UIT / 'batches-v2.jsonl', pad, lees, klaar)} nieuw; "
              f"{Counter(s for s, _ in antwoorden('antwoorden-v2.jsonl').values())}")


def lezen_2b() -> None:  # pragma: no cover - drukt teksten af om te labelen, schrijft niets
    import sqlite3

    conn = sqlite3.connect("file:doublecheck.db?mode=ro", uri=True)
    tekst = dict(conn.execute("SELECT claim_id, canonical_text FROM claim"))
    labels = _lees_labels()
    stukken = {i["sleutel"]: i for i in items()}
    zinnen = {"beslisser": _zinnen("v1"), "tweede vraag": _zinnen("v2")}
    open_ = []
    for x in _routes_om_te_tellen():
        for r in x["routes"][2:]:
            if r["uitkomst"] in ("ander", "matched") and paar(x["sleutel"], r["kandidaat"]) not in labels:
                open_.append((x, r))
    gezien = set()
    for x, r in open_:
        if paar(x["sleutel"], r["kandidaat"]) in gezien:
            continue
        gezien.add(paar(x["sleutel"], r["kandidaat"]))
        item = stukken[x["sleutel"]]
        print(f"\n[{x['set']} · {x['helft']} · {x.get('deel') or ''} · {r['route']}] {paar(x['sleutel'], r['kandidaat'])}")
        print(f"  ZIN VAN HET MODEL: {zinnen[r['route']].get(item['id'])}")
        print(f"  BEELD: {item['beeld']}" if item.get("beeld") else f"  STUK: {item['tekst'][:500]}")
        if item.get("claim"):
            print(f"  VERWACHT: {tekst.get(item['claim'], '?')[:300]}")
        print(f"  GEKOZEN: {tekst.get(r['kandidaat'], '?')[:300]}")
    print(f"\n{len(gezien)} te labelen in {LABELS}")


def tellen_2b(ongelezen: bool = False) -> dict:  # pragma: no cover - CLI
    """`ongelezen`: een keuze op een andere claim zonder label telt als fout
    (de precisie wordt een ondergrens, de vindkans verandert niet). Alleen als
    de regel al op webtekst viel en lezen de uitslag niet meer verandert."""
    from doublecheck.benchmark import upper_bound_95

    rijen = _routes_om_te_tellen()
    labels = _lees_labels()
    if ongelezen:
        extra = {paar(x["sleutel"], r["kandidaat"]): "ongelezen" for x in rijen if x["set"] in ("P2", "P3")
                 for r in x["routes"] if r["uitkomst"] == "ander" and paar(x["sleutel"], r["kandidaat"]) not in labels}
        print(f"{len(extra)} keuzes op een andere claim ongelezen, geteld als fout")
        labels = {**extra, **labels}
    uitslag = telling_routes(rijen, labels)
    p1 = _p1_per_helft()
    tegen = Counter((x["helft"], r["route"]) for x in rijen for r in x["routes"] if r.get("tegenspraak"))
    for helft in ("ontwikkel", "toets"):
        if helft not in uitslag:
            continue
        g1, n1 = p1.get(helft, (0, 1))
        print(f"\n{helft}:")
        for stap in uitslag[helft]["stappen"]:
            delen = stap["delen"]

            def kans(namen):
                n = sum(delen[d]["n"] for d in namen if d in delen)
                return sum(delen[d]["gevonden"] for d in namen if d in delen) / n if n else 0.0

            p2, p3 = kans(["artikel"]), kans(["screenshot met tekst", "foto zonder tekst"])
            stap["hoofdgetal"] = hoofdgetal(g1 / n1, p2, p3)
            pr = stap["precisie"]
            totaal = pr["juist"] + pr["fout"]
            print(f"  t/m {stap['route']:13} hoofdgetal {stap['hoofdgetal']:.1%} · P2 {p2:.1%} · P3 {p3:.1%}"
                  f" (screenshots {kans(['screenshot met tekst']):.1%}, foto's {kans(['foto zonder tekst']):.1%})"
                  f" · precisie {pr['juist']}/{totaal}"
                  f" (bovengrens fout {upper_bound_95(pr['fout'], totaal) if totaal else 0:.1%})"
                  f" · N1 {stap['N1']} · N3 {stap['N3']}")
        print(f"  door DR8 tegengehouden: { {r: n for (h, r), n in tegen.items() if h == helft} }")
    (UIT / "uitslag-2b.json").write_text(json.dumps(uitslag, ensure_ascii=False, indent=1), encoding="utf-8")
    return uitslag


def main() -> None:  # pragma: no cover - CLI
    import argparse

    parser = argparse.ArgumentParser(description="Het model leest, Factiz zoekt het bonnetje (#30.12)")
    parser.add_argument("stap", choices=("basiswaarde", "plan", "indienen", "ophalen", "meten", "lezen", "tellen",
                                         "indienen-v2", "ophalen-v2", "kandidaten", "beslis-indienen",
                                         "beslis-ophalen", "lezen-2b", "tellen-2b"))
    parser.add_argument("--vraag", choices=("v1", "v2"), default="v1", help="stap 2b: de zinnen van de eerste of de tweede vraag")
    parser.add_argument("--ongelezen-als-fout", action="store_true",
                        help="tellen-2b: een ongelezen keuze op een andere claim telt als fout (precisie als ondergrens)")
    parser.add_argument("--proef", type=int, default=0, help="indienen: alleen de eerste N stukken die nog niet ingediend zijn")
    parser.add_argument("--budget", type=float, default=1.0, help="indienen: weigert boven dit bedrag in dollar")
    parser.add_argument("--opnieuw", action="store_true", help="indienen: alleen de afgekapte antwoorden, met meer ruimte")
    args = parser.parse_args()
    if args.stap in ("indienen-v2", "ophalen-v2", "kandidaten", "beslis-indienen", "beslis-ophalen", "lezen-2b",
                     "tellen-2b"):
        stap_2b(args.stap, args.vraag, args.proef, args.budget, args.ongelezen_als_fout)
        return
    if args.stap == "basiswaarde":
        basiswaarde()
        return
    if args.stap == "meten":
        meten()
        return
    if args.stap == "lezen":
        lezen()
        return
    if args.stap == "tellen":
        tellen()
        return
    alle = items()
    if args.stap == "plan":
        print(f"{len(alle)} stukken: {dict(Counter(i['set'] for i in alle))}")
        print(f"  proef van 50 ${kosten(alle[:50]):.2f}; alles ${kosten(alle):.2f}")
        return
    import anthropic

    from doublecheck.varianten import laad_sleutel

    laad_sleutel()
    client = anthropic.Anthropic()
    UIT.mkdir(parents=True, exist_ok=True)
    if args.stap == "indienen":
        ingediend = set()
        for r in _jsonl(UIT / "batches.jsonl"):
            ingediend |= set(r["ids"])
        if args.opnieuw:
            gekozen = [i for i in alle if antwoorden().get(i["id"], ("",))[0] == "onleesbaar"]
        else:
            nog = [i for i in alle if i["id"] not in ingediend]
            if args.proef:
                # Een proef uit elke set, zodat beelden, artikelen en webtekst er alle drie in zitten.
                per_set: dict[str, list] = {}
                for i in nog:
                    per_set.setdefault(i["set"], []).append(i)
                gekozen = [i for lijst in per_set.values() for i in lijst[: max(1, args.proef // len(per_set))]]
            else:
                gekozen = nog
        if not gekozen:
            raise SystemExit("niets in te dienen")
        bedrag = kosten(gekozen)
        if bedrag > args.budget:
            raise SystemExit(f"geweigerd: naar schatting ${bedrag:.2f}, boven het budget van ${args.budget:.2f}")
        ruimte = 600 if args.opnieuw else 200
        batch = client.messages.batches.create(requests=[verzoek(i, ruimte) for i in gekozen])
        with (UIT / "batches.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps({"id": batch.id, "prompt": PROMPTVERSIE, "schatting": round(bedrag, 3),
                                "ids": [i["id"] for i in gekozen]}) + "\n")
        print(f"batch {batch.id}: {len(gekozen)} stukken, naar schatting ${bedrag:.2f}")
        return
    # ophalen
    klaar = {k for k, (status, _) in antwoorden().items() if status != "onleesbaar"}
    nieuw = 0
    with (UIT / "antwoorden.jsonl").open("a", encoding="utf-8") as uit:
        for b in reversed(_jsonl(UIT / "batches.jsonl")):
            if client.messages.batches.retrieve(b["id"]).processing_status != "ended":
                print(f"batch {b['id']} loopt nog")
                continue
            for r in client.messages.batches.results(b["id"]):
                if r.custom_id in klaar:
                    continue
                if r.result.type != "succeeded":
                    status, zin = "fout", None
                else:
                    tekst = next((c.text for c in r.result.message.content if c.type == "text"), "{}")
                    status, zin = lees_antwoord(tekst)
                uit.write(json.dumps({"id": r.custom_id, "status": status, "bewering": zin, "model": MODEL,
                                      "prompt": PROMPTVERSIE}, ensure_ascii=False) + "\n")
                if status != "onleesbaar":
                    klaar.add(r.custom_id)
                nieuw += 1
    print(f"{nieuw} nieuwe antwoorden, {len(klaar)} klaar; {Counter(s for s, _ in antwoorden().values())}")


if __name__ == "__main__":
    main()
