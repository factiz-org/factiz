"""De beeldstap: het beeld van een screenshot bevestigt checks (PLAN #32.35, deel 2 van het releasevoorstel, §201).

Zoals arm 2 van §201, lokaal en zonder model. De kandidaten zijn de artikelen van de checks die `/check` uit de
database haalt, en de artikelen waarvan de tekst op een viraal beeld het best op de tekst van de screenshot lijkt. Van
elk kandidaatartikel vergelijkt de stap de virale beelden met de screenshot: binnen 31 bits PDQ, of genoeg punten met
één gelijkvormigheid die samen genoeg van de screenshot beslaan (`beeldvraag.bevestigd`). Een bevestigde check krijgt de
zin `zoekcontrole.BEELDZIN` voor de lezer. Een bevestigd artikel buiten de vijf checks komt er met zijn check bij.

De index (`beeldindexbouw`) houdt per viraal beeld alleen PDQ en de punten, nooit het beeld (B35). Elke index draagt
zijn versies (punten, vergelijking, rol, tekstmodel); bij een andere versie weigert de stap (DR6). Het beeld van de
gebruiker blijft in het geheugen (DR3).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from urllib.parse import unquote, urlsplit

import numpy as np

from doublecheck import beeldvraag as bv


class Versiefout(Exception):
    """De index is met andere versies gemaakt dan de config vraagt (DR6)."""


def adres(url: str) -> str:
    """Een adres zonder schema, www, zoekdeel en slotstreep, zoals de database en de oogst vergelijken."""
    deel = urlsplit(url or "")
    return (deel.hostname or "").lower().removeprefix("www.") + re.sub(r"/{2,}", "/", unquote(deel.path)).rstrip("/")


def beeldkenmerken(inhoud: bytes) -> dict:
    """Van een beeld, in het geheugen: de maat, de PDQ-hashes van het geheel en de drie vaste uitsneden (zoals de
    index), de kwaliteit, en de punten."""
    from doublecheck.beelduitsnede import UITSNEDEN
    from doublecheck.image_fingerprint import as_image, pdq_met_kwaliteit

    origineel = as_image(inhoud)
    breedte, hoogte = origineel.size
    b = bv._open(origineel)
    w, h = b.size
    hexa, kwaliteit = pdq_met_kwaliteit(b)
    pdq = [hexa] + [pdq_met_kwaliteit(b.crop((int(w * l), int(h * t), int(w * r), int(h * o))))[0]
                    for _, (l, t, r, o) in UITSNEDEN]
    return {"breedte": breedte, "hoogte": hoogte, "pdq": pdq, "kwaliteit": kwaliteit, "punten": bv.puntkenmerken(b)}


def controleer_versies(index: dict, verwacht: dict) -> None:
    for sleutel, waarde in verwacht.items():
        if index.get(sleutel) != waarde:
            raise Versiefout(f"de beeldindex heeft {sleutel} {index.get(sleutel)!r}, de config vraagt {waarde!r}")


@dataclass
class Index:
    map: Path
    versies: dict
    per_adres: dict[str, list[dict]]
    tekst_adressen: list[str] = field(default_factory=list)
    teksten: np.ndarray = field(default_factory=lambda: np.zeros((0, 1), dtype=np.float32))
    checks: dict[str, list[dict]] = field(default_factory=dict)  # per adres de checks, in de vorm van `checks_uit`


def laad(map_: str | Path, verwacht: dict) -> Index:
    """De index uit zijn map: `versies.json`, `beelden.jsonl` (per viraal beeld adres, PDQ, kwaliteit en het pad naar
    de punten), en als ze er zijn de vectoren van de tekst op de virale beelden (`teksten.npy`, `teksten.jsonl`) en per
    adres de checks (`checks.jsonl`)."""
    map_ = Path(map_)
    versies = json.loads((map_ / "versies.json").read_text(encoding="utf-8"))
    controleer_versies(versies, verwacht)
    per_adres: dict[str, list[dict]] = {}
    for regel in (map_ / "beelden.jsonl").read_text(encoding="utf-8").splitlines():
        if regel.strip():
            r = json.loads(regel)
            per_adres.setdefault(r["adres"], []).append(r)
    index = Index(map_, versies, per_adres)
    if (map_ / "teksten.npy").exists():
        index.teksten = np.load(map_ / "teksten.npy").astype(np.float32)
        index.tekst_adressen = [json.loads(r)["adres"] for r in
                                (map_ / "teksten.jsonl").read_text(encoding="utf-8").splitlines() if r.strip()]
    if (map_ / "checks.jsonl").exists():
        for regel in (map_ / "checks.jsonl").read_text(encoding="utf-8").splitlines():
            if regel.strip():
                r = json.loads(regel)
                index.checks.setdefault(r["adres"], []).append({k: v for k, v in r.items() if k != "adres"})
    return index


@lru_cache(maxsize=2)
def index_uit(map_: str, versies: tuple) -> Index:  # pragma: no cover - één keer per proces, op schijf
    return laad(map_, dict(versies))


def kandidaten(checks: list[dict], tekst_vector: np.ndarray | None, index: Index, top: int) -> dict[str, set[str]]:
    """De artikelen om te vergelijken, in volgorde: eerst die van de checks uit de database, dan de `top` artikelen
    waarvan de tekst op een viraal beeld het meest op de tekst van de screenshot lijkt (elk artikel één keer)."""
    uit: dict[str, set[str]] = {}
    for k in checks:
        uit.setdefault(adres(k["url"]), set()).add("check")
    if tekst_vector is not None and len(index.tekst_adressen):
        scores = index.teksten @ np.asarray(tekst_vector, dtype=np.float32)
        gezien = 0
        for i in np.argsort(-scores, kind="stable"):
            a = index.tekst_adressen[i]
            if a in uit and "beeldtekst" in uit[a]:
                continue
            uit.setdefault(a, set()).add("beeldtekst")
            gezien += 1
            if gezien >= top:
                break
    return uit


def _afstand(een: str, twee: str) -> int:
    return (int(een, 16) ^ int(twee, 16)).bit_count()


def bevestigde_artikelen(vraag: dict, adressen: list[str], index: Index, *, drempel_pdq: int, min_punten: int,
                         min_dekking: float) -> list[str]:
    """De artikelen waarvan een viraal beeld de screenshot bevestigt, in de volgorde van `adressen`."""
    hashes = vraag["pdq"] if vraag["kwaliteit"] >= bv.MIN_KWALITEIT else []
    uit = []
    for a in adressen:
        for b in index.per_adres.get(a, []):
            pdq = (min(_afstand(x, y) for x in hashes for y in b["pdq"])
                   if hashes and b["kwaliteit"] >= bv.MIN_KWALITEIT else None)
            punten = bv.punten_uit_bytes((index.map / b["punten"]).read_bytes())
            n, dekking = bv.puntvergelijking(vraag["punten"], punten)
            if bv.bevestigd(pdq, n, dekking, drempel_pdq=drempel_pdq, min_punten=min_punten, min_dekking=min_dekking):
                uit.append(a)
                break
    return uit


def met_beeld(checks: list[dict], bevestigd: list[str], checks_voor_adres) -> list[dict]:
    """De checks voor de lezer: een check van een bevestigd artikel krijgt `beeld`; een bevestigd artikel dat er nog
    niet bij staat, komt er met zijn check(s) achter (`checks_voor_adres(adres)`), ook met `beeld`."""
    uit = [{**k, "beeld": adres(k["url"]) in bevestigd} for k in checks]
    hier = {adres(k["url"]) for k in checks}
    for a in bevestigd:
        if a not in hier:
            uit += [{**k, "beeld": True} for k in checks_voor_adres(a)]
            hier.add(a)
    return uit


def bevestig_checks(beeld: bytes, tekst_vector: np.ndarray | None, checks: list[dict], index: Index,
                    instellingen) -> list[dict]:
    """De hele stap voor één screenshot: kenmerken in het geheugen, de kandidaten, de vergelijking en de checks met
    `beeld` (`instellingen`: `config.beeldstap`)."""
    vraag = beeldkenmerken(beeld)
    adressen = list(kandidaten(checks, tekst_vector, index, instellingen.top_beeldtekst))
    bevestigd = bevestigde_artikelen(vraag, adressen, index, drempel_pdq=instellingen.drempel_pdq,
                                     min_punten=instellingen.min_punten, min_dekking=instellingen.min_dekking)
    return met_beeld(checks, bevestigd, lambda a: index.checks.get(a, []))
