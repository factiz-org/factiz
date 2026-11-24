"""De netwerktoets: echte propaganda-artikelen tegen hun ontkrachting (#28.5).

EUvsDisinfo noemt per zaak de media die het verhaal verspreidden. De set van
de Universiteit van Sheffield (Leite e.a., CIKM 2024; CC BY 4.0) maakt daar
artikel-URL's van, en datum plus verspreidend domein koppelt 3.599 zaken
eenduidig aan onze EUvsDisinfo-checks. Dit zijn de eerste echte artikelen van
de netwerken zelf met een verwacht antwoord: `matched`, met die check.

Twee vormen, zoals een lezer ze zou plakken: de **kop**, en de **kop met de
inleiding** (de beschrijving van het artikel, of anders het begin van de
tekst). Wat een site bij elk artikel zet, een slogan als beschrijving of de
sitenaam in de titel, is geen artikeltekst: een regel of titeldeel dat bij
dezelfde site in drie of meer artikelen terugkomt gaat eruit. Twee is nog geen
site; twee artikelen kunnen hetzelfde verhaal zijn.

De artikelen zijn geen artefacten van gebruikers, maar ook hier komt alleen
de uitkomst per zaak op schijf, nooit de tekst die door de resolver ging.

    python -m doublecheck.netwerktoets [--map data/extern/euvsdisinfo-sheffield]
"""

from __future__ import annotations

import collections
import re
from dataclasses import asdict, dataclass
from urllib.parse import urlsplit

# Vanaf hoeveel artikelen van één site een regel of titeldeel boilerplate is.
# Een schoonmaakregel voor de toets, geen drempel van de motor.
MIN_HERHALING = 3
INLEIDING = 300

_TITELSCHEIDING = re.compile(r"\s+[|–—-]\s+")


@dataclass(frozen=True)
class Item:
    claim_id: str
    bonnetje: str
    host: str
    taal: str
    kop: str
    kop_inleiding: str
    # Het artikel zelf, als sleutel voor de zeef (#30.1); geen tekst.
    artikel: str = ""


@dataclass(frozen=True)
class Uitslag:
    claim_id: str
    taal: str
    host: str
    vorm: str
    uitkomst: str


def _host(url: str) -> str:
    return urlsplit(url).netloc.lower().removeprefix("www.")


def items(artikelen: list[dict]) -> list[Item]:
    """Toetsitems uit de opgehaalde artikelen, met de boilerplate per site eruit."""
    bruikbaar = [a for a in artikelen if a.get("bron") and (a.get("titel") or "").strip()]
    per_site = collections.defaultdict(list)
    for a in bruikbaar:
        per_site[_host(a["article_url"])].append(a)

    uitkomst = []
    for host, eigen in per_site.items():
        delen = collections.Counter(
            deel.strip() for a in eigen for deel in set(_TITELSCHEIDING.split(a["titel"])))
        regels = collections.Counter(
            regel.strip() for a in eigen
            for regel in {*(a.get("beschrijving") or "").splitlines(), *(a.get("tekst") or "").splitlines()}
            if regel.strip())
        herhaald_deel = {d for d, n in delen.items() if n >= MIN_HERHALING}
        herhaald_regel = {r for r, n in regels.items() if n >= MIN_HERHALING}
        for a in eigen:
            eigen_delen = [d.strip() for d in _TITELSCHEIDING.split(a["titel"]) if d.strip()]
            over = [d for d in eigen_delen if d not in herhaald_deel]
            kop = a["titel"].strip() if over == eigen_delen else " | ".join(over).strip()
            if not kop:
                continue
            beschrijving = (a.get("beschrijving") or "").strip()
            if beschrijving in herhaald_regel:
                beschrijving = ""
            tekst = " ".join(r.strip() for r in (a.get("tekst") or "").splitlines()
                             if r.strip() and r.strip() not in herhaald_regel)
            inleiding = beschrijving or tekst[:INLEIDING]
            uitkomst.append(Item(a["claim_id"], "https://euvsdisinfo.eu" + a["report"], host, a.get("taal", ""),
                                 kop, f"{kop}\n{inleiding}".strip(), a["article_url"]))
    return uitkomst


def _tel(rijen) -> dict:
    c = collections.Counter(r.uitkomst for r in rijen)
    return {"n": len(rijen), **{k: c.get(k, 0) for k in ("gevonden", "verwant", "fout", "niets")}}


def rapport(uitslagen: list[Uitslag]) -> dict:
    def per(sleutel):
        groepen = collections.defaultdict(list)
        for u in uitslagen:
            groepen[getattr(u, sleutel)].append(u)
        return {k: _tel(v) for k, v in sorted(groepen.items(), key=lambda kv: -len(kv[1]))}

    return {"totaal": _tel(uitslagen), "per_vorm": per("vorm"), "per_taal": per("taal"), "per_host": per("host")}


def main() -> None:
    import argparse
    import json
    from datetime import datetime
    from pathlib import Path

    import torch
    from fastapi.testclient import TestClient

    from doublecheck.api import app
    from doublecheck.clustering import cluster_members
    from doublecheck.ruwetest import antwoord_of_fout, beoordeel, zonder_ipgrens
    from doublecheck.storage import connect

    parser = argparse.ArgumentParser(description="Propaganda-artikelen tegen hun ontkrachting (#28.5)")
    parser.add_argument("--map", default="data/extern/euvsdisinfo-sheffield")
    parser.add_argument("--threads", type=int, default=2)
    args = parser.parse_args()
    torch.set_num_threads(args.threads)

    artikelen = [json.loads(r) for r in (Path(args.map) / "artikelen.jsonl").read_text(encoding="utf-8").splitlines()
                 if r.strip()]
    toets = items(artikelen)
    print(f"artikelen {len(artikelen)} · toetsitems {len(toets)} bij {len({i.claim_id for i in toets})} zaken",
          flush=True)
    import os

    conn = connect(os.environ.get("DOUBLECHECK_DB", "doublecheck.db"))
    uitslagen: list[Uitslag] = []
    zonder_ipgrens()
    with TestClient(app) as api:
        for n, item in enumerate(toets, 1):
            verwacht = cluster_members(conn, item.claim_id) | {item.claim_id}
            for vorm, tekst in (("kop", item.kop), ("kop+inleiding", item.kop_inleiding)):
                antwoord = antwoord_of_fout(api.post("/resolve", json={"text": tekst}))
                oordeel = beoordeel(antwoord, item.bonnetje, verwacht)
                uitslagen.append(Uitslag(item.claim_id, item.taal, item.host, vorm, oordeel))
            if n % 100 == 0:
                print(f"  {n}/{len(toets)} · {_tel(uitslagen)}", flush=True)

    r = rapport(uitslagen)
    print(f"TOTAAL {r['totaal']}")
    for vorm, tel in r["per_vorm"].items():
        print(f"  {vorm:14} {tel}")
    print("per taal:")
    for taal, tel in list(r["per_taal"].items())[:12]:
        print(f"  {taal:14} {tel}")
    pad = Path("data") / f"netwerktoets-{datetime.now().strftime('%Y-%m-%dT%H%M%S')}.json"
    pad.write_text(json.dumps({"rapport": r, "uitslagen": [asdict(u) for u in uitslagen]},
                              ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"uitslagen (alleen zaak en uitkomst): {pad}")


if __name__ == "__main__":
    main()
