"""Verkennen en het netwerk van namen in TypeScript naast Python (B80, PLAN #34.2bo stap 3): elke taal, elk thema, elke
weergave en elk adres dat niet bestaat, voor `verkennen` en `netwerk`. Na inlezen gelijk, of het verschil in woorden.

    python -m factiz_site.gelijk_verkennen [<publicatie.db>]

De drempels van `db` (300 en 20 voor de verhouding, 70 namen en 25 keer samen) gaan mee naar TypeScript: een toets die
ze in Python lager zet, krijgt in TypeScript dezelfde.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlencode

from factiz_site import db, i18n
from factiz_site.gelijk import SITE, eerste_verschil

INGANG = SITE / "src" / "platform" / "verkennen.ts"


def drempels() -> dict[str, int]:
    """De drempels zoals Python ze nu heeft, met de namen van `VERKEN` in `verkennen.ts`."""
    return {"jaren": db.VERKEN_JAREN, "landen": db.VERKEN_LANDEN, "verhoudingLand": db.VERHOUDING_LAND,
            "verhoudingThema": db.VERHOUDING_THEMA, "netwerkNamen": db.NETWERK_NAMEN, "netwerkSamen": db.NETWERK_SAMEN}


def verkenvragen(pub) -> list[str]:
    """Elke weergave van Verkennen (alles, elk thema, elk thema met de verhouding) en wat geen weergave is."""
    uit = ["", "?", "?&", "?thema=bestaat-niet", "?thema=", "?thema", "?maat=verhouding", "?maat=aantal", "?land=IN",
           "?x=1", "?thema=%20", "?maat="]
    for th in pub.themas:
        s = th["sleutel"]
        uit += ["?" + urlencode({"thema": s}), "?" + urlencode({"thema": s, "maat": "verhouding"}),
                "?" + urlencode({"maat": "verhouding", "thema": s}), "?thema=" + "".join(f"%{ord(c):02X}" for c in s)]
    if pub.themas:
        s, t = pub.themas[0]["sleutel"], pub.themas[-1]["sleutel"]
        uit += [f"?thema={s.upper()}", f"?thema={s}&maat=aantal", f"?thema={s}&maat=procent", f"?thema={s}&maat=",
                f"?thema={s}&thema={t}", f"?thema={s}&thema={s}", f"?thema={s}&maat=verhouding&maat=verhouding",
                f"?thema={s}&x=1", f"?thema={s}&land=IN", f"?maat=verhouding&thema={s}&thema={s}"]
        uit += [f"?thema={o['sleutel']}" for o in pub.themas[0]["onderdelen"][:2]]
    return uit


def netwerkvragen(pub, alle_namen: bool = True) -> list[str]:
    """Het netwerk zonder keuze, elke naam erin (of de eerste en de laatste), en wat geen weergave is."""
    uit = ["", "?", "?naam=", "?naam", "?naam=x", "?naam=Q1", "?naam=q1", "?thema=war", "?x=1", "?naam=Q0"]
    if not pub.heeft_namen:
        return uit
    net = [q for q, _, _ in pub.netwerk()["namen"]]
    erin = net if alle_namen else net[:2] + net[-1:]
    uit += ["?" + urlencode({"naam": q}) for q in erin]
    buiten = [q for q in pub._naam if q not in set(net)]
    uit += ["?" + urlencode({"naam": q}) for q in buiten[:2]]
    if net:
        uit += [f"?naam={net[0]}&naam={net[-1]}", f"?naam={net[0]}&naam={net[0]}", f"?naam={net[0]}&x=1",
                f"?naam={net[0]}%20", f"?naam=%20{net[0]}"]
    return uit


def adressen(pub, alle_namen: bool | tuple[str, ...] = True) -> list[str]:
    """Elke vraag aan beide ingangen in elke taal van de site. `alle_namen`: elke naam van het netwerk in elke taal
    (True), of alleen in deze talen en anders de eerste en de laatste."""
    uit = []
    for taal in i18n.TALEN:
        uit += [f"/api/{taal}/verkennen{v}" for v in verkenvragen(pub)]
        alle = alle_namen is True or (isinstance(alle_namen, tuple) and taal in alle_namen)
        uit += [f"/api/{taal}/netwerk{v}" for v in netwerkvragen(pub, alle)]
    return uit


def ts_antwoorden(bestand: str | Path, adressen: list) -> list[dict]:
    """De antwoorden van TypeScript, met eerst de drempels van Python in `VERKEN` (een module die Node vooraf laadt)."""
    with tempfile.TemporaryDirectory() as map_:
        vooraf = Path(map_) / "drempels.mjs"
        vooraf.write_text(f"import {{ VERKEN }} from {json.dumps(INGANG.as_uri())};\n"
                          f"Object.assign(VERKEN, {json.dumps(drempels())});\n", encoding="utf-8")
        uit = subprocess.run(["node", "--import", vooraf.as_uri(), "scripts/platform-vraag.ts", str(Path(bestand).resolve())],
                             input=json.dumps(adressen, ensure_ascii=False), capture_output=True, text=True, cwd=SITE,
                             timeout=900)
    if uit.returncode:
        raise RuntimeError(uit.stderr[-3000:])
    return json.loads(uit.stdout)


def verschillen(client, bestand: str | Path, adressen: list[str]) -> list[str]:
    """Elk adres bij Python (een TestClient op `bestand`) en bij TypeScript; de verschillen in woorden."""
    ts = ts_antwoorden(bestand, adressen)
    uit = []
    for adres, t in zip(adressen, ts):
        r = client.get(adres)
        if r.status_code != t["status"]:
            uit.append(f"{adres}: Python {r.status_code}, TypeScript {t['status']} {str(t.get('fout', ''))[:800]}")
        elif r.status_code == 200 and (v := eerste_verschil(r.json(), t.get("body"))):
            uit.append(f"{adres}: {v}")
    return uit


def main() -> None:  # pragma: no cover - CLI
    from starlette.testclient import TestClient

    from factiz_site import app as fa

    bestand = Path(sys.argv[1]) if len(sys.argv) > 1 else fa._standaard_pad()
    client = TestClient(fa.maak_app(bestand), follow_redirects=False)
    lijst = adressen(db.Publicatie(bestand))
    fouten = verschillen(client, bestand, lijst)
    for f in fouten:
        print(f)
    print(f"{len(lijst) - len(fouten)} van {len(lijst)} adressen gelijk ({bestand})")
    raise SystemExit(1 if fouten else 0)


if __name__ == "__main__":  # pragma: no cover
    main()
