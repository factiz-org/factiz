"""De volle beeldindex bouwen voor de beeldstap (PLAN #32.35).

Uit de pool van #32.21 (`vindronde`) en de oogst (`beeldoogst`): alleen de beelden die `rol-v3` *viraal* noemt, met hun
PDQ, de punten (gekopieerd naar de index), de tekst die de OCR erop las (waar die er is) als vector van het tekstmodel,
en per artikel de checks uit de database in de vorm van `zoekcontrole.checks_uit`. Nooit een beeld (B35). De index
draagt zijn versies (`versies.json`); de beeldstap weigert een andere (DR6).

    python -m doublecheck.beeldindexbouw
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from doublecheck import beeldvraag as bv
from doublecheck.beeldstap import adres

WORTEL = Path(__file__).resolve().parent.parent
ROL = "rol-v3"


def virale(beelden: list[dict], rollen: list[dict]) -> list[dict]:
    """De beelden die `ROL` viraal noemt; een rol van een andere versie telt niet (DR6)."""
    rol = {(r["artikel"], b): x for r in rollen if r.get("versie") == ROL for b, x in zip(r["beelden"], r["rollen"])}
    uit, gezien = [], set()
    for b in beelden:  # na een herstart van de oogst kan een beeld twee keer staan
        sleutel = (b["artikel"], b["beeld"])
        if rol.get(sleutel) == "viraal" and sleutel not in gezien:
            gezien.add(sleutel)
            uit.append(b)
    return uit


def indexrij(b: dict, punten: str) -> dict:
    return {"adres": adres(b["artikel"]), "artikel": b["artikel"], "beeld": b["beeld"], "pdq": b["pdq"],
            "kwaliteit": b["kwaliteit"], "punten": punten}


def versies(config) -> dict:
    s = config.beeldstap
    return {"punten": s.punten, "vergelijking": s.vergelijking, "rol": ROL, "tekst": config.model_versions.text_embedding}


def _jsonl(pad: Path) -> list[dict]:  # pragma: no cover - een bestand
    return [json.loads(r) for r in pad.read_text(encoding="utf-8").splitlines() if r.strip()] if pad.exists() else []


def _bouw() -> None:  # pragma: no cover - op de bestanden, de database en het tekstmodel
    import sqlite3

    import numpy as np

    from doublecheck import beeldoogst as bo
    from doublecheck import vindronde as vr
    from doublecheck.config import load_config
    from doublecheck.embedding import fingerprint_texts

    config = load_config(None)
    if bv.PUNTVERSIE != config.beeldstap.punten or bv.VERGELIJKING != config.beeldstap.vergelijking:
        raise SystemExit("de code en de config noemen andere versies van de punten (DR6)")
    doel = WORTEL / config.beeldstap.index
    if doel.exists():
        raise SystemExit(f"{doel} bestaat al; eerst weg, dan opnieuw (een index wordt in één keer gebouwd)")
    (doel / "punten").mkdir(parents=True)
    bronnen = [
        (virale(_jsonl(vr.MAP / "pool-beelden.jsonl"), _jsonl(vr.MAP / "rolronde.jsonl")),
         lambda b: vr._puntpad("pool", b["artikel"], b["beeld"])),
        (virale(_jsonl(bo.MAP / "beelden.jsonl"), _jsonl(bo.MAP / "rollen.jsonl")),
         lambda b: bo._puntpad(b["artikel"], b["beeld"])),
    ]
    rijen, gemist = [], 0
    for lijst, puntpad in bronnen:
        for b in lijst:
            bron = puntpad(b)
            if not bron.exists():
                gemist += 1
                continue
            naam = f"punten/{bron.name}"
            shutil.copyfile(bron, doel / naam)
            rijen.append(indexrij(b, naam))
    (doel / "beelden.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rijen),
                                        encoding="utf-8")
    in_index = {(r["artikel"], r["beeld"]) for r in rijen}
    teksten = [(adres(t["artikel"]), t["tekst"]) for t in _jsonl(vr.MAP / "viraal-tekst.jsonl")
               if t.get("tekst") and (t["artikel"], t["beeld"]) in in_index]
    if teksten:
        versie = config.model_versions.text_embedding
        vecs = [fp.vector for i in range(0, len(teksten), 256)
                for fp in fingerprint_texts([t[:600] for _, t in teksten[i:i + 256]], versie)]
        np.save(doel / "teksten.npy", np.vstack(vecs).astype(np.float32))
        (doel / "teksten.jsonl").write_text("".join(json.dumps({"adres": a}) + "\n" for a, _ in teksten),
                                            encoding="utf-8")
    adressen = {r["adres"] for r in rijen}
    conn = sqlite3.connect(f"file:{WORTEL / 'doublecheck.db'}?mode=ro", uri=True)
    checks = []
    for url, claim, tekst, redactie, oordeel, datum in conn.execute(
            "SELECT f.url, c.claim_id, c.canonical_text, f.publisher, f.verdict_normalized, f.review_date "
            "FROM factcheck f JOIN claim c USING (claim_id)"):
        if adres(url) in adressen:
            checks.append({"adres": adres(url), "claim": claim, "tekst": tekst, "redactie": redactie,
                           "oordeel": oordeel, "datum": str(datum)[:10], "url": url})
    (doel / "checks.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in checks),
                                       encoding="utf-8")
    (doel / "versies.json").write_text(json.dumps(versies(config), indent=1), encoding="utf-8")
    print(f"{len(rijen)} virale beelden van {len(adressen)} artikelen, {len(teksten)} met tekst, {len(checks)} checks; "
          f"{gemist} zonder punten")


if __name__ == "__main__":  # pragma: no cover
    _bouw()
