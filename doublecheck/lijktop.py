"""Lijkt op: andere factchecks over hetzelfde verhaal (PLAN #34.2p, DESIGNSYSTEEM §4).

Het lab voegt een bewering alleen samen met een andere als de meting het draagt; wat het niet samenvoegt, wordt een eigen
pagina. Zo staan de Singalese, de Perzische en de Telugu factcheck over de Palestijnse vlag op de Eiffeltoren elk apart.
Dit zoekt per pagina de dichtstbijzijnde andere pagina's met bge-m3 (de versie uit config, DR6), op de tekst zoals de
site haar toont: de Engelse vertaling, anders de Nederlandse, anders het origineel. Op de originelen vond dezelfde
betekenis in het Singalees, het Telugu en het Perzisch elkaar niet (geen buur boven 0,80); een vertaling haalt dat gat
weg. Deze vectoren blijven in `data/lijktop/`, buiten de index van het lab. Wat een bezoeker ziet, is een verwijzing ("lijkt op"), nooit een samenvoeging: elke pagina
houdt haar eigen bewering en haar eigen oordeel (DR2, DR5).

De drempel komt uit een leesproef met een regel die vóór het lezen vaststond: 50 paren in elk vak van de score, en de
drempel is de ondergrens van het laagste vak vanaf waar elk vak erboven minstens 95% *zelfde verhaal* heeft.

    python -m doublecheck.lijktop rekenen|lezen|tellen

Leest de nieuwste publicatiedatabase en de vectoren van het lab, alleen-lezen; uitvoer in `data/lijktop/`, mijn lezing
in `docs/steekproeven/34.2p-lijkt-op.json`. Op de Mac, twee kernen, $0.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import random
import sqlite3
from collections import Counter
from pathlib import Path

import numpy as np

WORTEL = Path(__file__).resolve().parent.parent
MAP = WORTEL / "data" / "lijktop"
PAREN = MAP / "paren.jsonl"
LABELS = WORTEL / "docs" / "steekproeven" / "34.2p-lijkt-op.json"
VERSIE = "lijktop-v2"          # v1 op de originelen vond geen buren over schriften heen
VAKKEN = (0.80, 0.85, 0.90, 0.95)       # de ondergrens van elk vak; het laatste loopt tot 1
PER_VAK = 50
AANDEEL = 0.95
K = 5                                   # hoogstens zoveel per pagina
MAX_TOKENS = 256                        # van een getoonde tekst
ZAAD = 34216


def buren(x: np.ndarray, namen: list[str], *, k: int = K, vloer: float = VAKKEN[0], blok: int = 512) -> dict[str, list]:
    """Per naam de `k` dichtstbijzijnde andere namen met hun cosinus, vanaf `vloer`, de hoogste eerst. In blokken, zodat
    het geheugen klein blijft; het blok verandert de uitkomst niet."""
    x = np.asarray(x, dtype=np.float32)
    x = x / np.clip(np.linalg.norm(x, axis=1, keepdims=True), 1e-12, None)
    uit: dict[str, list] = {}
    for begin in range(0, len(x), blok):
        s = x[begin:begin + blok] @ x.T
        for i in range(len(s)):
            s[i, begin + i] = -np.inf               # nooit zichzelf
        kk = min(k, x.shape[0] - 1)
        top = np.argpartition(-s, kk - 1, axis=1)[:, :kk] if kk > 0 else np.empty((len(s), 0), dtype=int)
        for i, rij in enumerate(top):
            gekozen = sorted(((float(s[i, j]), namen[j]) for j in rij if s[i, j] >= vloer), reverse=True)
            uit[namen[begin + i]] = [(naam, score) for score, naam in gekozen]
    return uit


def vak(score: float) -> float | None:
    """Het vak van een score: de hoogste ondergrens die ze haalt, of niets onder het laagste vak."""
    onder = [v for v in VAKKEN if score >= v]
    return max(onder) if onder else None


def _uniek(paren: list[dict]) -> dict[frozenset, tuple[tuple[str, str], float]]:
    """Elk paar één keer, in de volgorde waarin het eerst voorkomt, met de hoogste score."""
    uit: dict[frozenset, tuple[tuple[str, str], float]] = {}
    for p in paren:
        sleutel = frozenset((p["pagina"], p["ander"]))
        if sleutel not in uit or p["score"] > uit[sleutel][1]:
            uit[sleutel] = (uit[sleutel][0] if sleutel in uit else (p["pagina"], p["ander"]), p["score"])
    return uit


def leesproef(paren: list[dict], zaad: int = ZAAD) -> list[tuple[str, str]]:
    """De paren die ik lees: 50 per vak, elk paar één keer, bij dezelfde paren altijd dezelfde."""
    kies = random.Random(zaad)
    per_vak: dict[float, list] = {v: [] for v in VAKKEN}
    for paar, score in sorted(_uniek(paren).values()):
        if vak(score) is not None:
            per_vak[vak(score)].append(paar)
    return [paar for v in VAKKEN for paar in kies.sample(per_vak[v], min(PER_VAK, len(per_vak[v])))]


def poort(paren: list[dict], pad: str | Path = LABELS) -> tuple[float | None, str]:
    """De drempel volgens de regel, of niets: alle paren van de proef gelezen, en dan de ondergrens van het laagste vak
    vanaf waar elk vak erboven minstens 95% *zelfde verhaal* heeft. Twijfel telt als *ander*."""
    proef = leesproef(paren)
    score = {k: s for k, (_, s) in _uniek(paren).items()}
    try:
        labels = json.loads(Path(pad).read_text(encoding="utf-8"))["paren"]
    except (OSError, json.JSONDecodeError, KeyError, TypeError):
        return None, "nog niets gelezen"
    gelezen = [labels.get(f"{a}|{b}") for a, b in proef]
    if not proef or any(l not in ("zelfde", "ander", "twijfel") for l in gelezen):
        return None, f"{sum(l in ('zelfde', 'ander', 'twijfel') for l in gelezen)} van de {len(proef)} gelezen"
    per_vak: dict[float, list[bool]] = {v: [] for v in VAKKEN}
    for (a, b), l in zip(proef, gelezen):
        per_vak[vak(score[frozenset((a, b))])].append(l == "zelfde")
    drempel, regels = None, []
    for v in reversed(VAKKEN):
        goed, n = sum(per_vak[v]), len(per_vak[v])
        regels.append(f"{v:.2f}: {goed} van {n}")
        if n and goed >= math.ceil(AANDEEL * n):
            drempel = v
        else:
            break
    return drempel, "; ".join(regels)


def voor_uitgave(paren: list[dict], drempel: float | None) -> dict[str, list[str]]:
    """Per pagina de andere pagina's vanaf de drempel, de hoogste score eerst, hoogstens vijf."""
    if drempel is None:
        return {}
    per: dict[str, list[tuple[float, str]]] = {}
    for p in paren:
        if p["score"] >= drempel:
            per.setdefault(p["pagina"], []).append((p["score"], p["ander"]))
    return {pagina: [a for _, a in sorted(lijst, reverse=True)[:K]] for pagina, lijst in per.items()}


def geldige_paren() -> tuple[dict[str, list[str]], str]:  # pragma: no cover - bestanden
    paren = _jsonl(PAREN)
    drempel, reden = poort(paren)
    return voor_uitgave(paren, drempel), (f"drempel {drempel:.2f} ({reden})" if drempel else f"dicht ({reden})")


# --- bestanden ---------------------------------------------------------------------------------------------------------

def _jsonl(pad: Path) -> list[dict]:
    if not pad.exists():
        return []
    return [json.loads(regel) for regel in pad.read_text(encoding="utf-8").splitlines() if regel.strip()]


def _publicatie() -> sqlite3.Connection:  # pragma: no cover - een bestand
    paden = sorted((WORTEL / "data" / "publicatie").glob("*/publicatie.db"))
    if not paden:
        raise SystemExit("geen publicatiedatabase: bouw er een met `python -m doublecheck.publiceren bouwen`")
    return sqlite3.connect(f"{paden[-1].resolve().as_uri()}?mode=ro", uri=True)


def getoond(taal: str, bewering: str, vertalingen: dict[str, str]) -> str:
    """De tekst waarop vergeleken wordt: de Engelse vertaling, anders de Nederlandse, anders de bewering zelf."""
    if taal == "en":
        return bewering
    return vertalingen.get("en") or (bewering if taal == "nl" else vertalingen.get("nl")) or bewering


def _rekenen() -> None:  # pragma: no cover - bestanden en het model
    from doublecheck.config import load_config
    from doublecheck.embedding import _load_model, normaliseer_voor_embedding

    versie = load_config(None).model_versions.text_embedding
    pub = _publicatie()
    vert: dict[str, dict[str, str]] = {}
    for nr, taal, tekst in pub.execute("SELECT pagina, taal, tekst FROM vertaling WHERE taal IN ('en', 'nl')"):
        vert.setdefault(nr, {})[taal] = tekst
    namen, teksten = [], []
    for nr, bewering, taal in pub.execute("SELECT nummer, bewering, taal FROM pagina ORDER BY nummer"):
        namen.append(nr)
        teksten.append(getoond(taal, bewering, vert.get(nr, {})))
    MAP.mkdir(parents=True, exist_ok=True)
    cache, cache_namen = MAP / "vectoren.npy", MAP / "vectoren.json"
    if cache.exists() and json.loads(cache_namen.read_text()) == {"versie": VERSIE, "model": versie, "namen": namen}:
        x = np.load(cache)
    else:
        model = _load_model(versie, "mps")
        model.max_seq_length = MAX_TOKENS        # een bewering is kort; een lange tekst maakt elke portie traag
        volgorde = sorted(range(len(teksten)), key=lambda i: len(teksten[i]))   # gelijke lengtes in één portie
        x = np.zeros((len(teksten), model.get_sentence_embedding_dimension()), dtype=np.float32)
        for k in range(0, len(volgorde), 128):
            deel = volgorde[k:k + 128]
            x[deel] = model.encode([normaliseer_voor_embedding(teksten[i]) for i in deel], normalize_embeddings=True,
                                   show_progress_bar=False)
            if k % 12800 == 0:
                print(f"{k + len(deel)} van {len(teksten)} ingebed", flush=True)
        np.save(cache, x)
        cache_namen.write_text(json.dumps({"versie": VERSIE, "model": versie, "namen": namen}), encoding="utf-8")
    print(f"{len(namen)} pagina's ({versie}, {VERSIE}); rekenen ...", flush=True)
    uit = buren(x, namen)
    with PAREN.open("w", encoding="utf-8") as f:
        for pagina, lijst in uit.items():
            for ander, score in lijst:
                f.write(json.dumps({"pagina": pagina, "ander": ander, "score": round(score, 4)}) + "\n")
    (MAP / "versie.json").write_text(json.dumps({"versie": VERSIE, "model": versie, "k": K, "vloer": VAKKEN[0],
                                                 "paginas": len(namen)}, indent=1), encoding="utf-8")
    paren = _jsonl(PAREN)
    print(f"{len(paren)} paren vanaf {VAKKEN[0]}; per vak:", Counter(vak(p["score"]) for p in paren))


def _tekst(pub: sqlite3.Connection, nr: str) -> dict:  # pragma: no cover - een bestand
    bewering, taal, label = pub.execute("SELECT bewering, taal, label FROM pagina WHERE nummer = ?", (nr,)).fetchone()
    vert = dict(pub.execute("SELECT taal, tekst FROM vertaling WHERE pagina = ?", (nr,)))
    datum = pub.execute("SELECT max(datum) FROM check_ WHERE pagina = ?", (nr,)).fetchone()[0]
    getoond = bewering if taal in ("en", "nl") else vert.get("en") or vert.get("nl") or bewering
    return {"nummer": nr, "taal": taal, "label": label or "gecheckt", "datum": datum, "tekst": getoond[:400]}


def main() -> None:  # pragma: no cover - CLI
    os.environ.setdefault("VECLIB_MAXIMUM_THREADS", "2")
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("stap", choices=["rekenen", "lezen", "tellen"])
    a = p.parse_args()
    if a.stap == "rekenen":
        return _rekenen()
    paren = _jsonl(PAREN)
    if a.stap == "lezen":
        pub = _publicatie()
        score = {k: s for k, (_, s) in _uniek(paren).items()}
        uit = [{"sleutel": f"{x}|{y}", "score": score[frozenset((x, y))], "vak": vak(score[frozenset((x, y))]),
                "a": _tekst(pub, x), "b": _tekst(pub, y)} for x, y in leesproef(paren)]
        (MAP / "te-lezen.json").write_text(json.dumps(uit, ensure_ascii=False, indent=1), encoding="utf-8")
        print(MAP / "te-lezen.json", len(uit))
        return
    drempel, reden = poort(paren)
    per = voor_uitgave(paren, drempel)
    print(f"{len(paren)} paren; de poort: {drempel} ({reden}); pagina's met Lijkt op: {len(per)}, "
          f"verwijzingen: {sum(len(v) for v in per.values())}")


if __name__ == "__main__":  # pragma: no cover
    main()
