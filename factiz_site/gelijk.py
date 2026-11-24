"""De TypeScript-kant van het platform naast deze Python-kant (B80, PLAN #34.2bo stap 3): dezelfde adressen naar beide,
op dezelfde uitgave, en elk verschil in woorden. Een ingang is af als er geen verschil meer is.

    python -m factiz_site.gelijk [<publicatie.db>]

TypeScript draait in Node (`site/scripts/platform-vraag.ts`, op `node:sqlite`); in de Worker is het D1, dat in stap 1 en
2 dezelfde rijen en zoekaantallen gaf.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from factiz_site import i18n

SITE = Path(__file__).resolve().parent.parent / "site"
# de ingangen die TypeScript al beantwoordt, in de volgorde van PLAN 34.2bo stap 3
KLAAR = ("bronnen", "redacties", "themas", "dossiers", "archief", "namen", "naam", "thema", "dossier", "sitemap", "eigen")


def lijstvragen(pub) -> list[str]:
    """Vragen aan de lijst die elk filter, de combinaties, de volgordes, de bladen en de weigeringen raken, met waarden
    uit deze uitgave."""
    from urllib.parse import urlencode

    eerste = {s: [w for w, _ in pub.facetten.get(s, [])][:2] for s in ("taal", "jaar", "oordeel", "redactie", "land", "soort", "vorm")}
    thema = pub.themas[0] if pub.themas else None
    uit = ["", "?sorteer=oud", "?sorteer=redacties", "?p=2", "?p=99999", "?p=0", "?p=x", "?onbekend=1", "?sorteer=nieuw",
           "?redactie=a&redactie=b", "?taal=zz", "?taal=", "?onderdeel=covid", "?jaar=1800"]
    for soort, waarden in eerste.items():
        for w in waarden:
            uit.append("?" + urlencode({soort: w}))
        if soort in ("taal", "jaar", "oordeel", "soort", "vorm") and len(waarden) == 2:
            uit.append("?" + urlencode([(soort, waarden[1]), (soort, waarden[0]), (soort, waarden[0])]))
    if thema:
        uit.append("?" + urlencode({"thema": thema["sleutel"]}))
        uit.append("?" + urlencode({"thema": thema["sleutel"], "sorteer": "oud", "p": "2"}))
        for o in thema["onderdelen"][:2]:
            uit.append("?" + urlencode({"thema": thema["sleutel"], "onderdeel": o["sleutel"]}))
        if eerste["taal"]:
            uit.append("?" + urlencode([("thema", thema["sleutel"]), ("taal", eerste["taal"][0]), ("sorteer", "redacties")]))
    if eerste["redactie"] and eerste["jaar"]:
        uit.append("?" + urlencode([("redactie", eerste["redactie"][0]), ("jaar", eerste["jaar"][0]), ("p", "2")]))
    namen = list(getattr(pub, "_naam", {}))[:2]
    for q in namen:
        uit.append("?" + urlencode({"naam": q}))
    return uit


def ts_antwoorden(bestand: str | Path, adressen: list[str]) -> list[dict]:
    uit = subprocess.run(["node", "scripts/platform-vraag.ts", str(bestand)], input=json.dumps(adressen, ensure_ascii=False),
                         capture_output=True, text=True, cwd=SITE, timeout=600)
    if uit.returncode:
        raise RuntimeError(uit.stderr[-3000:])
    return json.loads(uit.stdout)


def eerste_verschil(a, b, plek: str = "$") -> str | None:
    """Waar twee antwoorden voor het eerst uit elkaar lopen; de volgorde van sleutels telt niet, die van lijsten wel."""
    if type(a) is not type(b) and not (isinstance(a, (int, float)) and isinstance(b, (int, float))
                                       and not isinstance(a, bool) and not isinstance(b, bool)):
        return f"{plek}: {a!r} tegen {b!r}"
    if isinstance(a, dict):
        if set(a) != set(b):
            return f"{plek}: sleutels {sorted(set(a) ^ set(b))}"
        return next((v for k in a if (v := eerste_verschil(a[k], b[k], f"{plek}.{k}"))), None)
    if isinstance(a, list):
        if len(a) != len(b):
            return f"{plek}: {len(a)} tegen {len(b)} items"
        return next((v for i, (x, y) in enumerate(zip(a, b)) if (v := eerste_verschil(x, y, f"{plek}[{i}]"))), None)
    return None if a == b else f"{plek}: {a!r} tegen {b!r}"


def verschillen(client, bestand: str | Path, adressen: list) -> list[str]:
    """Elk verzoek bij Python (een TestClient op `bestand`) en bij TypeScript; de verschillen in woorden. Een verzoek is
    een adres (GET) of `{"pad", "methode": "POST", "bericht"}` met een formulier als tekst. JSON wordt na inlezen
    vergeleken; bij een ander antwoord dan JSON alleen de status."""
    ts = ts_antwoorden(bestand, adressen)
    uit = []
    for verzoek, t in zip(adressen, ts):
        if isinstance(verzoek, str):
            r = client.get(verzoek)
            adres = verzoek
        else:
            adres = f"{verzoek.get('methode', 'GET')} {verzoek['pad']} {(verzoek.get('bericht') or '')[:80]}"
            r = client.request(verzoek.get("methode", "GET"), verzoek["pad"], content=(verzoek.get("bericht") or "").encode(),
                               headers={"content-type": "application/x-www-form-urlencoded"})
        if r.status_code != t["status"]:
            uit.append(f"{adres}: Python {r.status_code}, TypeScript {t['status']} {str(t.get('fout', ''))[:800]}")
        elif r.status_code == 200 and r.headers.get("content-type", "").startswith("application/json"):
            if v := eerste_verschil(r.json(), t.get("body")):
                uit.append(f"{adres}: {v}")
    return uit


def ingangsadressen(pub) -> list[str]:
    """Namen per letter, een naam, elk thema en onderdeel, elk dossier, en wat er niet is."""
    from urllib.parse import urlencode

    uit = ["naam/Q1", "naam/x", "thema/bestaat-niet", "dossier/bestaat-niet", "dossier/X", "namen?soort=persoon",
           "namen?letter=a", "namen?soort=persoon&letter=a&letter=b", "namen?soort=niets&letter=a", "namen?x=1"]
    for soort in ("persoon", "organisatie", "plaats"):
        for letter in pub.letters("en", soort)[:2] + pub.letters("en", soort)[-1:]:
            uit.append("namen?" + urlencode([("soort", soort), ("letter", letter)]))
    uit += [f"naam/{q}" for q in list(getattr(pub, "_naam", {}))[:5]]
    for th in pub.themas:
        uit.append(f"thema/{th['sleutel']}")
        uit += [f"thema/{th['sleutel']}/{o['sleutel']}" for o in th["onderdelen"][:3]]
        uit.append(f"thema/{th['sleutel']}/bestaat-niet")
    uit += [f"dossier/{d['sleutel']}" for d in pub.dossiers]
    # de sitemaps (PLAN #34.2bt): elke stand met haar eerste delen, de namen, en wat de ingang niet kent
    uit += [f"sitemap?stand={s}" for s in (1, 2, 3)] + [f"sitemap?stand={s}&deel={d}" for s in (1, 2, 3) for d in (0, 1)]
    uit += ["sitemap?soort=namen", "sitemap", "sitemap?stand=4", "sitemap?stand=1&deel=01", "sitemap?stand=1&x=1",
            "sitemap?stand=1&stand=2", "sitemap?soort=namen&stand=1"]
    return uit


def alle_adressen(pub) -> list[str]:
    """Elke ingang die TypeScript al beantwoordt: de vaste in alle talen, de lijst met al haar vragen in vijf talen."""
    vast = [f"/api/{taal}/{ingang}" for taal in i18n.TALEN for ingang in ("bronnen", "redacties", "themas", "dossiers", "namen")]
    vast += [f"/api/{taal}/{a}" for taal in i18n.TALEN for a in ingangsadressen(pub)]
    lijst = [f"/api/{taal}/archief{v}" for taal in ("en", "nl", "hi", "ar", "zh") for v in lijstvragen(pub)]
    return vast + lijst


def main() -> None:  # pragma: no cover - CLI
    from starlette.testclient import TestClient

    from factiz_site import app as fa

    bestand = Path(sys.argv[1]) if len(sys.argv) > 1 else fa._standaard_pad()
    client = TestClient(fa.maak_app(bestand), follow_redirects=False)
    adressen = alle_adressen(fa.db.Publicatie(bestand))
    fouten = verschillen(client, bestand, adressen)
    for f in fouten:
        print(f)
    print(f"{len(adressen) - len(fouten)} van {len(adressen)} adressen gelijk ({bestand})")
    raise SystemExit(1 if fouten else 0)


if __name__ == "__main__":  # pragma: no cover
    main()
