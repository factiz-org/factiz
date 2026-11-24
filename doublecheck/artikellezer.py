"""De artikellezer (PLAN #30.11b): of een tekst van meerdere eenheden een
bekende bewering doet, ook bij lage gelijkenis.

Bij een gemist artikel staat de juiste ontkrachting vaak bovenaan, maar onder
de vloer waar de rechter leest (BENCHMARK §134). De lezer leest de vijf
claims met de hoogste gelijkenis over de eenheden vanaf `artikel_vloer`.
Stap 0 is een voorproef met lezers die er al zijn; pas als die tekortschieten
komt er lesstof en een eigen lezer.

    python -m doublecheck.artikellezer voorproef
"""

from __future__ import annotations

import functools
import json
from pathlib import Path

WORTEL = Path(__file__).resolve().parent.parent
UIT = WORTEL / "data" / "artikellezer"
# Vastgelegd vóór de voorproef (PLAN #30.11b).
K = 5
VLOER_VOORPROEF = 0.50
WEB_VANAF = 0.60
WEB_N = 5000
ZAAD = 3011


def beste_claims(per_eenheid: list[list[tuple[str, float]]], k: int, vloer: float) -> list[tuple[str, float, int]]:
    """Per claim de hoogste gelijkenis over de eenheden en de eenheid die haar
    gaf (bij gelijkstand de eerste); de `k` beste vanaf `vloer`."""
    beste: dict[str, tuple[float, int]] = {}
    for i, rijen in enumerate(per_eenheid):
        for claim, gelijkenis in rijen:
            if claim not in beste or gelijkenis > beste[claim][0]:
                beste[claim] = (gelijkenis, i)
    gekozen = sorted(((c, s, i) for c, (s, i) in beste.items() if s >= vloer), key=lambda x: (-x[1], x[2]))
    return gekozen[:k]


MODEL = "claude-haiku-5-5"
PROMPTVERSIE = "lezerlabel-v1"
PRIJS_IN, PRIJS_UIT = 0.05, 0.25  # batch, dollar per miljoen tokens (2026-10-17)
LESSTOF = UIT / "lesstof.jsonl"
TE_LABELEN = UIT / "te-labelen.jsonl"
OORDELEN = ["beweert", "weerlegt", "niet"]
SYSTEEM = ("You label pairs for a system that matches what people share or publish to fact-checks that already "
           "exist. Never judge whether a claim is true; only say what the text claims.")
_VRAAG = """Claim (checked by fact-checkers):
{claim}

Text (what someone shared or published):
{tekst}

Does the text make this claim?
- beweert: the text asserts the claim, in other words, another language, or as part of a longer story.
- weerlegt: the text discusses the claim but rejects or debunks it.
- niet: the text does not make this claim (another claim, a related topic, or something else).
Set zeker to false if you are unsure."""
_SCHEMA = {"type": "object",
           "properties": {"oordeel": {"type": "string", "enum": OORDELEN}, "zeker": {"type": "boolean"}},
           "required": ["oordeel", "zeker"], "additionalProperties": False}


def mag_mee(cluster: set[str], helft_van) -> bool:
    """Lesstof alleen uit een zaak waarvan geen clustergenoot in de
    toetshelft staat (`helft_van(claim)`)."""
    return all(helft_van(c) == "ontwikkel" for c in cluster)


def paarsleutel(claim: str, tekst: str) -> str:
    import hashlib

    return hashlib.sha256(f"{claim}\x00{tekst}".encode("utf-8")).hexdigest()[:32]


def label_uit(antwoord: str) -> int | None:
    """Een zeker "beweert" is 1, een zeker "weerlegt" of "niet" is 0 (een
    weerlegging doet de bewering niet, DR8); twijfel is geen lesstof."""
    try:
        oordeel = json.loads(antwoord)
    except json.JSONDecodeError:
        return None
    if oordeel.get("oordeel") not in OORDELEN or not oordeel.get("zeker"):
        return None
    return 1 if oordeel["oordeel"] == "beweert" else 0


def verzoek(paar: dict) -> dict:
    return {"custom_id": paarsleutel(paar["claim"], paar["tekst"]),
            "params": {"model": MODEL, "max_tokens": 1_000, "system": SYSTEEM,
                       "messages": [{"role": "user", "content": _VRAAG.format(**paar)}],
                       "output_config": {"effort": "medium", "format": {"type": "json_schema", "schema": _SCHEMA}}}}


def lees(config, tekst: str, lijsten: list, claimtekst, scorer=None):
    """De artikellezer in het aanvraagpad: de `diepte` beste claims over de
    eenheden vanaf `artikel_vloer`, gelezen met de claim eerst en de hele
    tekst daarna. Geeft (kandidaat zoals gevonden, score, eenheid) van de
    hoogste score, of None als er niets te lezen is; de categorie zet
    `categorize` (DR4)."""
    per_eenheid = [[(k.claim_id, k.similarity) for k in lijst] for lijst in lijsten]
    gekozen = beste_claims(per_eenheid, config.artikellezer.diepte, config.thresholds.artikel_vloer)
    if not gekozen:
        return None
    paren = [(claimtekst(c), tekst) for c, _, _ in gekozen]
    scores = (scorer or (lambda p: scores_lezer(p, config.artikellezer.pad, config.artikellezer.model)))(paren)
    (claim, gelijkenis, eenheid), score = max(zip(gekozen, scores), key=lambda x: x[1])
    kandidaat = next(k for k in lijsten[eenheid] if k.claim_id == claim and k.similarity == gelijkenis)
    return kandidaat, score, eenheid


class Weigering(Exception):
    """De gewichten in `pad` zijn niet de versie uit de config (DR6)."""


@functools.lru_cache(maxsize=1)
def _laad_lezer(pad: str, model: str):  # pragma: no cover - met het model
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    # De naam (lezer-a, lezer-b) staat voor de @; de hash erachter is de identiteit (DR6).
    gevonden = lezerversie(Path(pad), model.split("@")[0])
    if gevonden != model:
        raise Weigering(f"de gewichten in {pad} zijn {gevonden}, de config verwacht {model} (DR6)")
    return AutoTokenizer.from_pretrained(pad), AutoModelForSequenceClassification.from_pretrained(pad).eval()


def scores_lezer(paren: list[tuple[str, str]], pad: str, model: str) -> list[float]:  # pragma: no cover - met het model
    """Op de processor, zoals de dienst rekent; tot 384 tokens, zoals hij leerde."""
    import torch

    tokenizer, net = _laad_lezer(pad, model)
    with torch.no_grad():
        invoer = tokenizer([c for c, _ in paren], [t for _, t in paren], return_tensors="pt", truncation=True,
                           max_length=384, padding=True)
        return torch.sigmoid(net(**invoer).logits.view(-1).float()).tolist()


def _apparaat():  # pragma: no cover - met torch
    import torch

    return "mps" if torch.backends.mps.is_available() else "cpu"


def _lees(naam: str, paren: list[tuple[str, str]], max_lengte: int, batch: int = 16) -> list[float]:  # pragma: no cover
    """Scores van één lezer op de grafische chip (B37; alleen meten, de
    resolver rekent op de processor). `naam` is een map met gewichten of een
    model op Hugging Face met `@revisie`."""
    import torch
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    pad, _, revisie = naam.partition("@")
    tokenizer = AutoTokenizer.from_pretrained(pad, revision=revisie or None)
    model = AutoModelForSequenceClassification.from_pretrained(pad, revision=revisie or None).to(_apparaat()).eval()
    uit: list[float] = []
    with torch.no_grad():
        for start in range(0, len(paren), batch):
            deel = paren[start:start + batch]
            invoer = tokenizer([a for a, _ in deel], [b for _, b in deel], return_tensors="pt", truncation=True,
                               max_length=max_lengte, padding=True).to(model.device)
            uit += torch.sigmoid(model(**invoer).logits.view(-1).float()).cpu().tolist()
    del model
    if _apparaat() == "mps":
        torch.mps.empty_cache()
    return uit


_MATRICES: dict[str, tuple] = {}


def _kandidaten(teksten: list[str], conn, versie: str, k: int = K,
                vloer: float = VLOER_VOORPROEF) -> list[list[tuple[str, float, int, list[str]]]]:
    """Per tekst de eenheden en de K beste claims over die eenheden vanaf de
    vloer, met per claim de eenheid die de hoogste gelijkenis gaf."""
    per_tekst, vectoren = _eenheidvectoren(teksten, versie)
    return _kandidaten_uit(per_tekst, vectoren, conn, versie, k, vloer)


def _eenheidvectoren(teksten: list[str], versie: str):
    """De eenheden per tekst en hun vectoren, in porties van 256, zonder de
    index: de zeef kan zo eerst alles embedden en pas daarna de index laden
    (2026-10-22, lezer B: bge-m3 en de index samen lieten de Mac swappen)."""
    import numpy as np

    from doublecheck.zeef import _vectoren_gpu
    from doublecheck.zinnen import eenheden

    per_tekst = [eenheden(t) for t in teksten]
    alle = [e for es in per_tekst for e in es]
    delen = [_vectoren_gpu(alle[start:start + 256], versie) for start in range(0, len(alle), 256)]
    if _apparaat() == "mps":  # pragma: no cover - met de grafische chip
        import torch

        # Elke lengte vraagt andere stukken; zonder vrijgeven groeide de cache
        # in de zeefrun van lezer B per blok van 4 naar 9 GB.
        torch.mps.empty_cache()
    return per_tekst, (np.concatenate(delen) if delen else np.empty((0, 0), dtype=np.float32))


def _index(conn, versie: str) -> tuple:
    """Claims en varianten als één matrix, één keer per proces."""
    import numpy as np

    from doublecheck.search import _tekstmatrix, _variantenmatrix

    # De index één keer per proces: per portie opnieuw laden kostte ~2,3 GB
    # per keer en liet het geheugen vollopen (PO 2026-10-22: eerst de zuinigste aanpak).
    # Op de grafische chip ook de vergelijking met de 570.000 claims en
    # varianten: op twee kernen kostte die 3,5 van de 5,8 minuten per 1.000
    # teksten (2026-10-22). Alleen voor metingen (B37); dezelfde kandidaten.
    if versie not in _MATRICES:
        ids, claims = _tekstmatrix(conn, versie)
        vids, _, varianten, _ = _variantenmatrix(conn, versie)
        alles = np.concatenate([claims, varianten]).astype(np.float32)
        del claims, varianten
        if _apparaat() == "mps":
            import torch

            alles = torch.from_numpy(alles).to("mps")
        _MATRICES[versie] = (list(ids) + list(vids), alles)
    return _MATRICES[versie]


def _kandidaten_uit(per_tekst: list[list[str]], vectoren, conn, versie: str, k: int = K,
                    vloer: float = VLOER_VOORPROEF) -> list[list[tuple[str, float, int, list[str]]]]:
    """De kandidaten bij vectoren van `_eenheidvectoren`."""
    import numpy as np

    rij_claim, alles = _index(conn, versie)
    rijen: list[list[tuple[str, float]]] = []
    for start in range(0, len(vectoren), 256):
        deel = vectoren[start:start + 256]
        if isinstance(alles, np.ndarray):
            sim = alles @ deel.T
            boven = np.argpartition(-sim, 50, axis=0)[:50]
            waarden = np.take_along_axis(sim, boven, axis=0)
        else:  # pragma: no cover - met de grafische chip
            import torch

            sim = alles @ torch.from_numpy(deel).to(alles.device).T
            waarden, boven = torch.topk(sim, 50, dim=0)
            waarden, boven = waarden.cpu().numpy(), boven.cpu().numpy()
            del sim
        for j in range(boven.shape[1]):
            beste: dict[str, float] = {}
            for r, s in zip(boven[:, j], waarden[:, j]):
                c = rij_claim[r]
                beste[c] = max(float(s), beste.get(c, -1.0))
            rijen.append(list(beste.items()))
    if not isinstance(alles, np.ndarray):  # pragma: no cover - met de grafische chip
        import torch

        # Elke portie van 256 eenheden vraagt ~580 MB op de grafische chip, en
        # bge-m3 per lengte weer andere stukken; zonder vrijgeven groeide de
        # cache in de zeefrun van lezer B naar 17 GB en liep de swap vol
        # (2026-10-22, gestopt door de bewaker). De index zelf blijft staan.
        torch.mps.empty_cache()
    uit, i = [], 0
    for es in per_tekst:
        uit.append([(c, s, u, es) for c, s, u in beste_claims(rijen[i:i + len(es)], k, vloer)])
        i += len(es)
    return uit


def voorproef() -> dict:  # pragma: no cover - op de productiedatabase
    """Stap 0 van #30.11b: drie lezers die er al zijn, op P2 (ontwikkel) en
    webtekst (N1, ontwikkel). Alleen sleutels, claims en scores op schijf."""
    import random
    import sqlite3

    import numpy as np

    from doublecheck.clustering import cluster_members
    from doublecheck.config import load_config
    from doublecheck.herordenaar import HERORDENAAR
    from doublecheck.netwerktoets import items
    from doublecheck.variantenbatch import lees_regels
    from doublecheck.zeef import P2_MAP, POOLS, helft

    config = load_config()
    versie = config.model_versions.text_embedding
    conn = sqlite3.connect(f"file:{WORTEL / 'doublecheck.db'}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    tekst = {r[0]: r[1] for r in conn.execute("SELECT claim_id, canonical_text FROM claim")}

    artikelen = [json.loads(r) for r in (P2_MAP / "artikelen.jsonl").read_text(encoding="utf-8").splitlines() if r.strip()]
    p2 = [i for i in items(artikelen) if helft(f"zaak:{i.claim_id}") == "ontwikkel"]
    web = []
    zeefmap = WORTEL / "data" / "zeef" / "factiz-artikel"
    for pool in POOLS:
        rijen = lees_regels(pool)
        best = np.maximum(np.load(zeefmap / f"N1-{pool.name}-hoogste.npy"),
                          np.load(zeefmap / f"N1-{pool.name}-hoogste-zinnen.npy"))
        meer = np.load(zeefmap / f"N1-{pool.name}-hoogste-zinnen.npy") > -1
        for i in np.nonzero(meer & (best >= WEB_VANAF))[0].tolist():
            sleutel = f"N1:{pool.name}:{rijen[i]['claim_id']}"
            if helft(sleutel) == "ontwikkel":
                web.append((sleutel, rijen[i]["varianten"][0]["tekst"]))
    web = sorted(random.Random(ZAAD).sample(web, min(WEB_N, len(web))))
    print(f"P2 ontwikkel {len(p2)}, webtekst {len(web)}", flush=True)

    stukken = [("P2", f"P2:{i.artikel}#{i.claim_id}", i.kop_inleiding,
                cluster_members(conn, i.claim_id) | {i.claim_id}) for i in p2]
    stukken += [("N1", s, t, set()) for s, t in web]
    kandidaten = _kandidaten([t for _, _, t, _ in stukken], conn, versie)
    paren = [(si, c, s, es[u]) for si, lijst in enumerate(kandidaten) for c, s, u, es in lijst]
    print(f"{len(paren)} paren", flush=True)
    lezers = {
        "a_rechter_eenheid": (config.rechter.pad, [(e, tekst[c]) for _, c, _, e in paren], 256),
        "b_rechter_tekst": (config.rechter.pad, [(stukken[si][2], tekst[c]) for si, c, _, _ in paren], 512),
        "c_herordenaar_tekst": (HERORDENAAR, [(stukken[si][2], tekst[c]) for si, c, _, _ in paren], 512),
    }
    scores = {}
    for naam, (model, invoer, lengte) in lezers.items():
        scores[naam] = _lees(model, invoer, lengte)
        print(f"  {naam} gelezen", flush=True)
    UIT.mkdir(parents=True, exist_ok=True)
    with (UIT / "voorproef.jsonl").open("w", encoding="utf-8") as f:
        for k, (si, c, s, _) in enumerate(paren):
            f.write(json.dumps({"set": stukken[si][0], "sleutel": stukken[si][1], "claim": c, "gelijkenis": round(s, 4),
                                "verwacht": c in stukken[si][3], **{n: round(v[k], 5) for n, v in scores.items()}},
                               ensure_ascii=False) + "\n")
    return uitslag_voorproef([json.loads(r) for r in (UIT / "voorproef.jsonl").read_text(encoding="utf-8").splitlines()],
                             n_p2=len(p2))


def uitslag_voorproef(regels: list[dict], n_p2: int) -> dict:
    """Per lezer: hoeveel P2-stukken hun verwachte claim boven de hoogste
    webtekst krijgen (en boven de 2e en 6e hoogste: 1 of 5 vals), en de AUC
    van verwacht tegen het hoogste van elke webtekst."""
    lezers = sorted({k for r in regels for k in r if k[:2] in ("a_", "b_", "c_")})
    uit = {}
    for lezer in lezers:
        pos: dict[str, float] = {}
        web: dict[str, float] = {}
        for r in regels:
            if r["set"] == "P2" and r["verwacht"]:
                pos[r["sleutel"]] = max(r[lezer], pos.get(r["sleutel"], 0.0))
            elif r["set"] == "N1":
                web[r["sleutel"]] = max(r[lezer], web.get(r["sleutel"], 0.0))
        w = sorted(web.values(), reverse=True)
        grens = {f"{n}_vals": (w[n] if len(w) > n else 0.0) for n in (0, 1, 5)}
        gevonden = {k: sum(1 for s in pos.values() if s > g) for k, g in grens.items()}
        paren = [(p, q) for p in pos.values() for q in web.values()]
        auc = (sum(1.0 if p > q else 0.5 if p == q else 0.0 for p, q in paren) / len(paren)) if paren else None
        uit[lezer] = {"p2_n": n_p2, "verwacht_in_kandidaten": len(pos), "webtekst_n": len(web),
                      "grens": grens, "gevonden": gevonden, "auc": auc}
    return uit


def lesstof() -> dict:  # pragma: no cover - op de productiedatabase
    """Stap 1 van #30.11b: de paren die zeker zijn naar `LESSTOF`, de harde
    gevallen naar `TE_LABELEN` voor Haiku. Alleen zaken van de
    ontwikkelhelft; les en keuze per zaak, webtekst per stuk."""
    import collections
    import csv
    import sqlite3
    import sys

    import numpy as np

    from doublecheck.clustering import cluster_members
    from doublecheck.netwerktoets import items
    from doublecheck.rechtermeting import deel
    from doublecheck.zeef import P2_MAP, helft

    csv.field_size_limit(sys.maxsize)
    conn = sqlite3.connect(f"file:{WORTEL / 'doublecheck.db'}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    tekst = {r[0]: r[1] for r in conn.execute("SELECT claim_id, canonical_text FROM claim")}
    helft_van = lambda c: helft(f"zaak:{c}")  # noqa: E731
    cluster = {}

    def leden(c):
        if c not in cluster:
            cluster[c] = cluster_members(conn, c) | {c}
        return cluster[c]

    def regel(claim, tekst_, label, bron, zaak, deel_):
        return {"claim": claim, "tekst": tekst_, "label": label, "bron": bron, "zaak": zaak, "deel": deel_}

    zeker, harde = [], []
    # EUvsDisinfo: de titel naast de samenvatting (beweert) en de ontkrachting (weerlegt).
    slug_claim = {u.rstrip("/").split("/report/")[-1]: c for u, c in
                  conn.execute("SELECT url, claim_id FROM factcheck WHERE url LIKE '%euvsdisinfo.eu/report/%'")}
    zaken = []
    with open(WORTEL / "data" / "euvsdisinfo_all_texts_rename.csv", newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            c = slug_claim.get(r["Links"].rstrip("/").split("/report/")[-1])
            if not c or not mag_mee(leden(c), helft_van) or not r["Title"].strip():
                continue
            d = deel(c)
            zeker.append(regel(r["Title"], r["Disinformation"], 1, "eu-samenvatting", c, d))
            if r["Information"].strip():
                zeker.append(regel(r["Title"], r["Information"], 0, "eu-ontkrachting", c, d))
            zaken.append((c, r["Title"], d))
    # Harde gevallen: een titel naast de samenvatting van de meest gelijkende andere zaak.
    versie = load_config_versie()
    vector = {c: np.frombuffer(p, dtype=np.float32) for c, p in conn.execute(
        "SELECT claim_id, payload FROM fingerprint WHERE kind = 'text' AND model_version = ?", (versie,))}
    zaken = [z for z in zaken if z[0] in vector]
    X = np.stack([vector[c] for c, _, _ in zaken])
    for start in range(0, len(zaken), 1024):
        sim = X[start:start + 1024] @ X.T
        for i, rij in enumerate(sim):
            c, titel, d = zaken[start + i]
            for j in np.argsort(-rij)[:10]:
                cj = zaken[j][0]
                if cj in leden(c) or deel(cj) != d:
                    continue
                harde.append(regel(titel, tekst[cj], None, "eu-buur", c, d))
                break
    # P2: het artikel naast zijn claim (beweert), en naast zijn andere kandidaten (Haiku).
    artikelen = [json.loads(r) for r in (P2_MAP / "artikelen.jsonl").read_text(encoding="utf-8").splitlines() if r.strip()]
    per_sleutel = {f"P2:{i.artikel}#{i.claim_id}": i for i in items(artikelen)}
    for item in per_sleutel.values():
        if helft_van(item.claim_id) == "ontwikkel" and mag_mee(leden(item.claim_id), helft_van):
            zeker.append(regel(tekst[item.claim_id], item.kop_inleiding, 1, "p2-artikel", item.claim_id,
                               deel(item.claim_id)))
    voorproef = [json.loads(r) for r in (UIT / "voorproef.jsonl").read_text(encoding="utf-8").splitlines() if r.strip()]
    from doublecheck.variantenbatch import lees_regels
    from doublecheck.zeef import POOLS

    webtekst = {f"N1:{p.name}:{r['claim_id']}": r["varianten"][0]["tekst"] for p in POOLS for r in lees_regels(p)}
    for r in voorproef:
        if r["set"] == "P2" and not r["verwacht"]:
            item = per_sleutel[r["sleutel"]]
            harde.append(regel(tekst[r["claim"]], item.kop_inleiding, None, "p2-ander", item.claim_id,
                               deel(item.claim_id)))
        elif r["set"] == "N1":
            # Webtekst doet zelden een gecheckte bewering; wat de herordenaar
            # toch hoog geeft, leest Haiku (er zitten terechte koppen tussen).
            nieuw = regel(tekst[r["claim"]], webtekst[r["sleutel"]], 0, "webtekst", r["sleutel"], deel(r["sleutel"]))
            (harde if r["c_herordenaar_tekst"] >= 0.9 else zeker).append(nieuw | ({"label": None}
                                                                              if r["c_herordenaar_tekst"] >= 0.9 else {}))
    UIT.mkdir(parents=True, exist_ok=True)
    LESSTOF.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in zeker), encoding="utf-8")
    TE_LABELEN.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in harde), encoding="utf-8")
    return {"zeker": dict(collections.Counter((r["bron"], r["deel"], r["label"]) for r in zeker)),
            "te_labelen": dict(collections.Counter((r["bron"], r["deel"]) for r in harde))}


def webtekst_in_lesstof(pad: Path = UIT / "voorproef.jsonl") -> set[str]:
    """De webteksten (N1-sleutels) uit het lesdeel van de voorproef: alles
    waar de lezer van kon leren. Ze tellen niet mee in het vals alarm van de
    beslisregel (#30.11b). Leeg zonder voorproef."""
    from doublecheck.rechtermeting import deel

    return {r["sleutel"] for r in _lees_jsonl(pad) if r["set"] == "N1" and deel(r["sleutel"]) == "les"}


LEZER = UIT / "lezer-a"
WEB_LES = 10_000  # webtekst in de lesstof, willekeurig (zaad ZAAD), zodat die de positieven niet overstemt


def lezerversie(map_: Path, naam: str = "lezer-a") -> str:  # pragma: no cover - leest de gewichten
    import hashlib

    h = hashlib.sha256()
    for pad in sorted(Path(map_).glob("*.safetensors")):
        with pad.open("rb") as f:
            while stuk := f.read(1 << 24):
                h.update(stuk)
    return f"{naam}@{h.hexdigest()[:12]}"


def lesparen(regels: list[dict], web_n: int = WEB_LES, zaad: int = ZAAD) -> list[dict]:
    """De lesstof voor de training: alleen het lesdeel en alleen paren met een
    label; van de webtekst hoogstens `web_n`, willekeurig maar vast."""
    import random

    les = [r for r in regels if r["deel"] == "les" and r["label"] is not None]
    web = [r for r in les if r["bron"] == "webtekst"]
    rest = [r for r in les if r["bron"] != "webtekst"]
    return rest + (random.Random(zaad).sample(web, web_n) if len(web) > web_n else web)


def trainen(lagen: int = 6, rondes: int = 1, batch: int = 8, lr: float = 2e-5, lengte: int = 384,
            extra: list[dict] = (), naam: str = "lezer-a") -> dict:  # pragma: no cover
    """De lezer bijtrainen vanaf de herordenaar, zoals D (#30.3), met de claim
    eerst. Elke training in een eigen map met haar versie; `lezer-a` wijst naar
    de nieuwste."""
    import collections
    import random

    import torch
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    from doublecheck.herordenaar import HERORDENAAR

    torch.manual_seed(ZAAD)
    basis, _, revisie = HERORDENAAR.partition("@")
    tokenizer = AutoTokenizer.from_pretrained(basis, revision=revisie)
    # Zonder dropout, zodat de snelle aandacht op de grafische chip kan: met
    # "eager" en 512 tekens duurde één ronde ~5,5 uur (2026-10-18).
    model = AutoModelForSequenceClassification.from_pretrained(basis, revision=revisie, attn_implementation="sdpa",
                                                               hidden_dropout_prob=0.0,
                                                               attention_probs_dropout_prob=0.0)
    for n, param in model.named_parameters():
        bovenin = any(f"encoder.layer.{i}." in n for i in range(model.config.num_hidden_layers - lagen,
                                                                  model.config.num_hidden_layers))
        param.requires_grad = bovenin or n.startswith("classifier")
    apparaat = _apparaat()
    model.to(apparaat).train()
    # Lezer B (#30.11c) krijgt de lesstof van A plus zijn eigen (`extra`).
    les = lesparen(_lees_jsonl(LESSTOF) + _lees_jsonl(UIT / "lesstof-haiku.jsonl") + list(extra))
    optim = torch.optim.AdamW([p for p in model.parameters() if p.requires_grad], lr=lr)
    verlies_fn = torch.nn.BCEWithLogitsLoss()
    rnd = random.Random(ZAAD)
    stappen = 0
    for ronde in range(rondes):
        rnd.shuffle(les)
        totaal = 0.0
        for start in range(0, len(les), batch):
            deel_ = les[start:start + batch]
            invoer = tokenizer([p["claim"] for p in deel_], [p["tekst"] for p in deel_], return_tensors="pt",
                               truncation=True, max_length=lengte, padding=True).to(apparaat)
            doelen = torch.tensor([float(p["label"]) for p in deel_], device=apparaat)
            verlies = verlies_fn(model(**invoer).logits.view(-1).float(), doelen)
            optim.zero_grad()
            verlies.backward()
            optim.step()
            totaal += float(verlies.detach()) * len(deel_)
            stappen += 1
            if stappen % 100 == 0:
                print(f"  ronde {ronde + 1}, stap {stappen} van {rondes * ((len(les) + batch - 1) // batch)}:"
                      f" verlies {float(verlies):.4f}", flush=True)
        print(f"ronde {ronde + 1}: gemiddeld verlies {totaal / len(les):.4f}", flush=True)
    model.eval().to("cpu")
    nieuw = UIT / f"{naam}-nieuw"
    model.save_pretrained(nieuw)
    tokenizer.save_pretrained(nieuw)
    v = lezerversie(nieuw, naam)
    meta = {"basis": HERORDENAAR, "lagen": lagen, "rondes": rondes, "batch": batch, "lr": lr, "lengte": lengte,
            "aandacht": "sdpa, zonder dropout",
            "zaad": ZAAD, "volgorde": "claim, tekst", "paren": len(les), "positief": sum(p["label"] for p in les),
            "bronnen": {f"{b}/{l}": n for (b, l), n in collections.Counter((p["bron"], p["label"]) for p in les).items()},
            "versie": v}
    (nieuw / "meta.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
    nieuw.rename(UIT / v)
    link = UIT / naam
    if link.is_symlink() or link.exists():
        link.unlink()
    link.symlink_to(v)
    return meta


VLOEREN = (0.50, 0.55, 0.60, 0.65, 0.70)
DREMPELS = (0.5, 0.7, 0.8, 0.9, 0.95, 0.97, 0.98, 0.99, 0.995, 0.999)


def kies_drempels(rijen: list[dict], vloeren=VLOEREN, drempels=DREMPELS) -> dict:
    """De regel van #30.11b, vastgelegd vóór het kiezen: per vloer de laagste
    drempel waarbij geen webtekst een kandidaat vanaf de vloer met een score
    vanaf de drempel heeft; dan de vloer met de meeste artikelen waarvan de
    best scorende kandidaat de verwachte is (bij gelijkstand de hoogste
    vloer). `rijen`: per kandidaat set, sleutel, verwacht, gelijkenis, score."""
    import collections

    per_stuk = collections.defaultdict(list)
    for r in rijen:
        per_stuk[(r["set"], r["sleutel"])].append(r)

    def tel(vloer, drempel):
        gevonden = ander = web = 0
        for (set_, _), kandidaten in per_stuk.items():
            boven = [k for k in kandidaten if k["gelijkenis"] >= vloer and k["score"] >= drempel]
            if not boven:
                continue
            if set_ == "N1":
                web += 1
            elif max(boven, key=lambda k: k["score"])["verwacht"]:
                gevonden += 1
            else:
                ander += 1
        return {"gevonden": gevonden, "ander": ander, "webtekst": web}

    per_vloer = {}
    for vloer in vloeren:
        for drempel in drempels:
            t = tel(vloer, drempel)
            if t["webtekst"] == 0:
                per_vloer[str(vloer)] = {"drempel": drempel, **t}
                break
    beste = max(per_vloer.items(), key=lambda kv: (kv[1]["gevonden"], float(kv[0])), default=None)
    return {"per_vloer": per_vloer,
            "gekozen": {"vloer": float(beste[0]), "drempel": beste[1]["drempel"]} if beste else None}


def kiezen() -> dict:  # pragma: no cover - met het model
    """De drempels op het keuzedeel: de kandidaten van de voorproef (P2 en
    webtekst van de ontwikkelhelft, alleen het keuzedeel), gelezen door de
    bijgetrainde lezer met de claim eerst, en dan `kies_drempels`."""
    import sqlite3

    from doublecheck.netwerktoets import items
    from doublecheck.rechtermeting import deel
    from doublecheck.variantenbatch import lees_regels
    from doublecheck.zeef import P2_MAP, POOLS

    conn = sqlite3.connect(f"file:{WORTEL / 'doublecheck.db'}?mode=ro", uri=True)
    tekst = {r[0]: r[1] for r in conn.execute("SELECT claim_id, canonical_text FROM claim")}
    artikelen = [json.loads(r) for r in (P2_MAP / "artikelen.jsonl").read_text(encoding="utf-8").splitlines() if r.strip()]
    stuk = {f"P2:{i.artikel}#{i.claim_id}": (i.kop_inleiding, i.claim_id) for i in items(artikelen)}
    stuk |= {f"N1:{p.name}:{r['claim_id']}": (r["varianten"][0]["tekst"], f"N1:{p.name}:{r['claim_id']}")
             for p in POOLS for r in lees_regels(p)}
    rijen = [r for r in _lees_jsonl(UIT / "voorproef.jsonl") if deel(stuk[r["sleutel"]][1]) == "keuze"]
    scores = _lees(str(LEZER.resolve()), [(tekst[r["claim"]], stuk[r["sleutel"]][0]) for r in rijen], 512)
    rijen = [r | {"score": s} for r, s in zip(rijen, scores)]
    (UIT / "keuze-scores.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rijen), encoding="utf-8")
    uit = kies_drempels(rijen) | {"lezer": LEZER.resolve().name,
                                  "artikelen": len({r["sleutel"] for r in rijen if r["set"] == "P2"}),
                                  "webteksten": len({r["sleutel"] for r in rijen if r["set"] == "N1"})}
    (UIT / "keuze.json").write_text(json.dumps(uit, indent=1), encoding="utf-8")
    return uit


def load_config_versie() -> str:  # pragma: no cover
    from doublecheck.config import load_config

    return load_config().model_versions.text_embedding


def main() -> None:  # pragma: no cover - CLI
    import argparse

    parser = argparse.ArgumentParser(description="De artikellezer (#30.11b)")
    parser.add_argument("stap", choices=("voorproef", "lesstof", "plan", "indienen", "ophalen", "uitschrijven",
                                         "trainen", "kiezen"))
    parser.add_argument("--rondes", type=int, default=1)
    parser.add_argument("--proef", type=int)
    args = parser.parse_args()
    if args.stap == "voorproef":
        print(json.dumps(voorproef(), ensure_ascii=False, indent=1))
    elif args.stap == "kiezen":
        print(json.dumps(kiezen(), ensure_ascii=False, indent=1))
    elif args.stap == "trainen":
        print(json.dumps(trainen(rondes=args.rondes), ensure_ascii=False, indent=1))
    elif args.stap == "lesstof":
        print(json.dumps({k: {str(a): b for a, b in v.items()} for k, v in lesstof().items()}, ensure_ascii=False,
                         indent=1))
    else:
        _haiku(args.stap, args.proef)


def _lees_jsonl(pad: Path) -> list[dict]:
    # Op `\n`, niet met splitlines(): artikeltekst bevat U+2028 en U+2029 (sheffield.regels).
    return [json.loads(r) for r in pad.read_text(encoding="utf-8").split("\n") if r.strip()] if pad.exists() else []


def _haiku(stap: str, proef: int | None, map_: Path = UIT) -> None:  # pragma: no cover - met de Batch API
    """Haiku-labels op de harde gevallen (`TE_LABELEN`), zoals de rechterlabels:
    plan, indienen (eerst `--proef N`), ophalen, uitschrijven naar de lesstof."""
    logboek, antwoorden = map_ / "batches.jsonl", map_ / "antwoorden.jsonl"
    paren = _lees_jsonl(map_ / TE_LABELEN.name)
    if stap == "plan":
        tokens_in = sum((len(p["claim"]) + len(p["tekst"])) // 3 + 300 for p in paren)
        print(f"{len(paren)} paren, naar schatting ${(tokens_in * PRIJS_IN + len(paren) * 250 * PRIJS_UIT) / 1e6:.2f}")
        return
    import anthropic

    from doublecheck.varianten import laad_sleutel

    laad_sleutel()
    client = anthropic.Anthropic()
    if stap == "indienen":
        ingediend = {i for r in _lees_jsonl(logboek) for i in r["ids"]}
        uniek = {paarsleutel(p["claim"], p["tekst"]): p for p in paren}
        verzoeken = [verzoek(p) for k, p in uniek.items() if k not in ingediend][:proef]
        if not verzoeken:
            print("alles is al ingediend")
            return
        batch = client.messages.batches.create(requests=verzoeken)
        with logboek.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"id": batch.id, "prompt": PROMPTVERSIE, "ids": [v["custom_id"] for v in verzoeken]})
                    + "\n")
        print(f"batch {batch.id}: {len(verzoeken)} paren")
    elif stap == "ophalen":
        klaar = {r["id"] for r in _lees_jsonl(antwoorden)}
        with antwoorden.open("a", encoding="utf-8") as uit:
            for b in _lees_jsonl(logboek):
                if client.messages.batches.retrieve(b["id"]).processing_status != "ended":
                    print(f"batch {b['id']} loopt nog")
                    continue
                for r in client.messages.batches.results(b["id"]):
                    if r.result.type != "succeeded" or r.custom_id in klaar:
                        continue
                    t = next((c.text for c in r.result.message.content if c.type == "text"), "")
                    uit.write(json.dumps({"id": r.custom_id, "tekst": t}) + "\n")
                    klaar.add(r.custom_id)
        print(f"{len(klaar)} antwoorden")
    elif stap == "uitschrijven":
        import collections

        label = {r["id"]: label_uit(r["tekst"]) for r in _lees_jsonl(antwoorden)}
        gelabeld = [p | {"label": label[paarsleutel(p["claim"], p["tekst"])]} for p in paren
                    if label.get(paarsleutel(p["claim"], p["tekst"])) is not None]
        with (map_ / "lesstof-haiku.jsonl").open("w", encoding="utf-8") as f:
            f.writelines(json.dumps(p, ensure_ascii=False) + "\n" for p in gelabeld)
        print(f"{len(gelabeld)} van {len(paren)} gelabeld; {dict(collections.Counter((p['bron'], p['label']) for p in gelabeld))}")


if __name__ == "__main__":
    main()
