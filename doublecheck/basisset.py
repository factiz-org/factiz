"""De basisset van de leraarladder (PLAN #31.1, E8.S1, B42).

Eén set in plaats van losse meetsets, uit wat al in huis is: onwaar en waar
naast elkaar, als beeld, artikel, tekst en vastgesteld feit, plus gewone
webtekst. De basislijnval van §70 bepaalt de opbouw: bijna alles wat redacties
checkten is onwaar, dus wat telt is hoe vaak een model "onwaar" zegt bij iets
waars; daarom de betrouwbare artikelen van Sheffield over dezelfde onderwerpen,
de ware checks, de kern en de webtekst.

Per stuk: soort, bron, label, helft (de vaste hash van de zeef, per zaak waar
een claim bekend is), datum, taal, de vlag `vers` (na de trainingsgrens van de
5.5-modellen) en de tekst of het pad naar het beeld. Alleen openbare data; nooit
iets van een gebruiker (DR3), en van Sheffield alleen tekst, nooit HTML.

    python -m doublecheck.basisset bouwen
    python -m doublecheck.basisset tellen
"""

from __future__ import annotations

import json
import random
from collections import Counter, defaultdict
from pathlib import Path

WORTEL = Path(__file__).resolve().parent.parent
UIT = WORTEL / "data" / "basisset"
BESTAND = UIT / "basisset.jsonl"
VERS_VANAF = "2026-07-01"   # na de trainingsgrens van de 5.5-modellen (juni 2026)
MAX_TEKENS = 2_000
ZAAD = 3001
N_ONWARE_CLAIMS = 3_000
N_WEBTEKST, ZAAD_WEBTEKST = 5_000, 3003  # dezelfde steekproef als §124


def label_van_kant(kant: str | None) -> str | None:
    """Het oordeel van de redactie als label: rood is onwaar, groen is waar;
    midden en onbekend doen niet mee (zoals in §124)."""
    return {"rood": "onwaar", "groen": "waar"}.get(kant)


def stuk(sleutel: str, soort: str, bron: str, label: str, *, zaak: str | None = None, datum: str | None = None,
         taal: str | None = None, **inhoud) -> dict:
    """Eén stuk van de basisset. De helft hangt aan de zaak als die bekend is,
    zodat alles van dezelfde zaak in dezelfde helft valt (zoals de zeef)."""
    from doublecheck.zeef import helft

    return {"sleutel": sleutel, "soort": soort, "bron": bron, "label": label, "zaak": zaak,
            "helft": helft(f"zaak:{zaak}" if zaak else sleutel), "datum": datum, "taal": taal or "und",
            "vers": bool(datum) and datum >= VERS_VANAF, **inhoud}


def sheffield_tekst(rij: dict) -> str | None:
    """Titel, beschrijving en alineatekst van een Sheffield-artikel, witruimte
    samengevoegd, hooguit `MAX_TEKENS`; None als er niets is of het ophalen
    mislukte."""
    if rij.get("fout"):
        return None
    delen = [" ".join(str(rij.get(k) or "").split()) for k in ("titel", "beschrijving", "tekst")]
    tekst = "\n".join(d for d in delen if d)
    return tekst[:MAX_TEKENS] or None


def steekproef_per_taal(rijen: list[dict], n: int, zaad: int = ZAAD) -> list[dict]:
    """Een steekproef van `n` met elke taal naar verhouding, telkens dezelfde."""
    per_taal: dict[str, list] = defaultdict(list)
    for r in rijen:
        per_taal[r.get("taal") or "und"].append(r)
    rng = random.Random(zaad)
    uit = []
    for taal in sorted(per_taal):
        groep = per_taal[taal]
        k = round(n * len(groep) / len(rijen))
        uit += rng.sample(groep, min(k, len(groep)))
    return uit


def kies_claims(onwaar: list[dict], waar: list[dict], n: int = N_ONWARE_CLAIMS) -> list[tuple[dict, str]]:
    """De onware claims als steekproef naar taal, plus elke verse onware claim
    (het verse deel telt apart en is anders te klein); de ware allemaal."""
    gekozen = steekproef_per_taal(onwaar, n)
    al = {r["claim_id"] for r in gekozen}
    gekozen += [r for r in onwaar if (r.get("datum") or "") >= VERS_VANAF and r["claim_id"] not in al]
    return [(r, "onwaar") for r in gekozen] + [(r, "waar") for r in waar]


def telling(stukken: list[dict]) -> dict:
    return {
        "stukken": len(stukken),
        "per soort en label": dict(Counter(f"{s['soort']} {s['label']}" for s in stukken)),
        "per bron": dict(Counter(s["bron"] for s in stukken)),
        "per helft": dict(Counter(s["helft"] for s in stukken)),
        "vers": sum(s["vers"] for s in stukken),
        "per taal": dict(Counter(s["taal"] for s in stukken)),
    }


def nummer(stukken: list[dict]) -> None:
    """Een id die in een batch past (letters, cijfers, streepjes), in de vaste
    volgorde van de set."""
    for i, s in enumerate(stukken):
        s["id"] = f"b-{i:06d}"


def _gelijk(url: str) -> str:
    return url.strip().rstrip("/").lower()


def bouwen(db: str = "doublecheck.db") -> dict:  # pragma: no cover - op de productiedatabase en de bestanden
    import sqlite3

    from doublecheck import zeef
    from doublecheck.feitenbasis import lees_kern, lees_paren, n3_items
    from doublecheck.netwerktoets import items as artikel_items
    from doublecheck.ruwetest import m4fc_items
    from doublecheck.sheffield import regels
    from doublecheck.standaardmodel import _kant
    from doublecheck.variantenbatch import lees_regels

    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    datum = dict(conn.execute("SELECT claim_id, MIN(review_date) FROM factcheck GROUP BY claim_id"))
    uit: list[dict] = []
    # Beelden: de M4FC-beelden van P3, met het oordeel van de redactie.
    for b in m4fc_items(zeef.P3_MAP):
        label = label_van_kant(_kant(conn, b.claim_id))
        if label:
            uit.append(stuk(f"P3:{b.pad.stem}", "beeld", "m4fc", label, zaak=b.claim_id,
                            datum=(datum.get(b.claim_id) or "")[:10] or None, taal=b.taal, beeld=str(b.pad)))
    # Artikelen: P2 (kop en inleiding), dan Sheffield zonder wat P2 al heeft.
    artikelen = regels(zeef.P2_MAP / "artikelen.jsonl")
    p2_urls = set()
    for a in artikel_items(artikelen):
        label = label_van_kant(_kant(conn, a.claim_id))
        if label:
            p2_urls.add(_gelijk(a.artikel))
            uit.append(stuk(f"P2:{a.artikel}#{a.claim_id}", "artikel", "p2", label, zaak=a.claim_id,
                            datum=(datum.get(a.claim_id) or "")[:10] or None, taal=a.taal, tekst=a.kop_inleiding))
    for r in regels(zeef.P2_MAP / "lesstof-artikelen.jsonl"):
        tekst = sheffield_tekst(r)
        if not tekst or _gelijk(r["article_url"]) in p2_urls:
            continue
        label = {"disinformation": "onwaar", "trustworthy": "waar"}.get(r["klasse"])
        if label:
            uit.append(stuk(f"S:{r['article_url']}", "artikel", f"sheffield-{r['klasse']}", label,
                            zaak=r.get("claim_id"), datum=(r.get("datum") or "")[:10] or None, taal=r.get("taal"),
                            tekst=tekst))
    # Teksten: claims die redacties onwaar of waar noemden.
    claims = conn.execute("SELECT c.claim_id, c.canonical_text, c.language FROM claim c").fetchall()
    onwaar, waar = [], []
    for claim_id, tekst, taal in claims:
        label = label_van_kant(_kant(conn, claim_id))
        rij = {"claim_id": claim_id, "tekst": tekst, "taal": taal, "datum": (datum.get(claim_id) or "")[:10] or None}
        (onwaar if label == "onwaar" else waar if label == "waar" else []).append(rij)
    for r, label in kies_claims(onwaar, waar):
        uit.append(stuk(f"C:{r['claim_id']}", "tekst", "claimreview", label, zaak=r["claim_id"],
                        datum=r["datum"], taal=r["taal"], tekst=r["tekst"]))
    # Vastgestelde feiten: de kern en de ware kant van de beslissende paren; de vervalste kant als onwaar.
    paren = lees_paren()
    for n in n3_items(lees_kern(), paren):
        uit.append(stuk(n["sleutel"], "feit", f"n3-{n['bron']}", "waar", taal=n["taal"], tekst=n["tekst"],
                        feit=n["feit"]) | {"helft": n["helft"]})
    for p in paren:
        if p["label"] == "vervalsing":
            uit.append(stuk(f"NEP:paar:{p['revid']}", "feit", "minimale-paren", "onwaar", taal="en", tekst=p["nep"],
                            feit=p["feit"]) | {"helft": zeef.helft(f"feit:{p['feit']}")})
    # Webtekst: dezelfde steekproef van de stiltepools als §124.
    pools = [(pool.name, r) for pool in zeef.POOLS for r in lees_regels(pool)]
    random.Random(ZAAD_WEBTEKST).shuffle(pools)
    for pool, r in pools[:N_WEBTEKST]:
        uit.append(stuk(f"N1:{pool}:{r['claim_id']}", "webtekst", "stiltepool", "neutraal", taal=r["taal"],
                        tekst=r["varianten"][0]["tekst"]))
    nummer(uit)
    UIT.mkdir(parents=True, exist_ok=True)
    BESTAND.write_text("".join(json.dumps(s, ensure_ascii=False) + "\n" for s in uit), encoding="utf-8")
    return telling(uit)


def lees(pad: Path = BESTAND) -> list[dict]:
    from doublecheck.sheffield import regels

    return regels(pad)


def main() -> None:  # pragma: no cover - CLI
    import argparse

    parser = argparse.ArgumentParser(description="De basisset van de leraarladder (#31.1)")
    parser.add_argument("stap", choices=("bouwen", "tellen"))
    args = parser.parse_args()
    uitslag = bouwen() if args.stap == "bouwen" else telling(lees())
    print(json.dumps(uitslag, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
