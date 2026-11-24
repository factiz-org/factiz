"""Patronen in herkomst: bekende netwerkdomeinen en hun klonen als signaal (PLAN #32.58, B62; PO 2026-11-07: "Ze quoten
mekaar, dan hoeven we het bericht niet eens door te lezen om toch al te weten dat het nep nieuws is").

Een signaal met zijn bron, nooit een oordeel (DR2, B25). De lijst (`netwerken.json`) komt uit openbare bronnen:
- het Pravda-netwerk: de sites in de data van CheckFirst en DFRLab (github.com/CheckFirstHQ/pravda-network: de map `json/`,
  gelezen 2026-11-07, en de steekproef in `data/extern/pravda-steekproef`);
- de verspreiders in de database van EUvsDisinfo (`data/euvsdisinfo_all_texts_rename.csv`), met minstens drie gevallen,
  zonder platforms en zonder sites met band *goed*;
- klonen: de naam van een goed medium op een extensie die Doppelgänger gebruikte (EU DisinfoLab, Doppelganger hub,
  gelezen 2026-11-07: ".ltd, .online, or .foo"; en diplomatie.gouv.fm in de zaak bij de WIPO).

    python -m doublecheck.netwerken bouwen|tellen
"""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

WORTEL = Path(__file__).resolve().parent.parent
LIJST = Path(__file__).resolve().parent / "netwerken.json"
MIN_GEVALLEN = 3
# De subdomeinen van news-pravda.com in github.com/CheckFirstHQ/pravda-network/tree/main/json, gelezen 2026-11-07
PRAVDA_SUBDOMEINEN = (
    "a.network abkhazia albania algeria armenia au austria balkan basque belgium bosnia-herzegovina bulgaria burkina-faso "
    "cameroon canada catalan chad croatia cyprus czechia denmark deutsch dprk dutch egypt eritrea estonia eu finland "
    "francais france galician gambia ge germany greece guinea-bissau guinea hungary iceland ireland italy japan korea "
    "latvia lt luxembourg mali malta maori mauritania md montenegro nato netherlands new-zealand niger nigeria "
    "north-macedonia norway ossetia poland portugal portuguese rca romania scotland senegal serbia singapore slovakia "
    "slovenia south-korea south-sudan spain spanish srpska sudan sweden switzerland syria taiwan trump turkey ua uk usa "
    "wales").split()
KLOON_EXTENSIES = ("ltd", "online", "foo", "fm")
PLATFORMS = frozenset({"youtube.com", "facebook.com", "twitter.com", "x.com", "t.me", "telegram.org", "vk.com", "ok.ru",
                       "instagram.com", "tiktok.com", "rumble.com", "bitchute.com", "odysee.com", "reddit.com",
                       "medium.com", "blogspot.com", "wordpress.com", "livejournal.com", "dzen.ru", "zen.yandex.ru",
                       "yandex.ru", "google.com", "archive.org", "archive.ph", "web.archive.org"})
_ACHTERVOEGSEL = frozenset({"co", "com", "org", "net", "gov", "ac", "edu", "gob", "or", "ne", "go", "nic", "gv"})
_HOST = re.compile(r"(?<![@\w.-])(?:https?://)?((?:[a-z0-9-]+\.)+[a-z]{2,})(?![\w@-])", re.IGNORECASE)


def host_van(tekst: str) -> str | None:
    """De host van een adres of een kaal domein, in kleine letters en zonder www; None als het geen domein is."""
    m = _HOST.search((tekst or "").strip())
    if not m or not re.fullmatch(r"(?:https?://)?(?:[a-z0-9-]+\.)+[a-z]{2,}(?:[/?#:].*)?", tekst.strip(), re.IGNORECASE):
        return None
    host = m.group(1).lower()
    return host[4:] if host.startswith("www.") else host


def hosts_in(tekst: str) -> list[str]:
    """De domeinen die in een bericht staan, met of zonder https, in volgorde, elk één keer; geen e-mailadres."""
    uit = []
    for m in _HOST.finditer(tekst or ""):
        host = m.group(1).lower()
        host = host[4:] if host.startswith("www.") else host
        if host not in uit:
            uit.append(host)
    return uit


def _naam(host: str) -> str:
    """De naam zonder het achtervoegsel: bbc.com en bbc.co.uk zijn allebei bbc."""
    delen = host.split(".")
    if len(delen) >= 3 and len(delen[-1]) == 2 and delen[-2] in _ACHTERVOEGSEL:
        return delen[-3]
    return delen[-2] if len(delen) >= 2 else host


def netwerk_van(host: str, lijst: dict) -> dict | None:
    """Het netwerk van een host: een domein uit de lijst (of een subdomein ervan), of een domein onder een achtervoegsel
    van een netwerk; anders None."""
    delen = host.split(".")
    for i in range(len(delen) - 1):
        kandidaat = ".".join(delen[i:])
        if kandidaat in lijst.get("domeinen", {}):
            return {"host": host, **lijst["domeinen"][kandidaat]}
        if kandidaat in lijst.get("achtervoegsels", {}):
            return {"host": host, **lijst["achtervoegsels"][kandidaat]}
    return None


def kloon_van(host: str, banden: dict, lijst: dict) -> str | None:
    """Het goede medium waarvan dit een kloon lijkt: dezelfde naam (minstens vier tekens) op een extensie die Doppelgänger
    gebruikte, terwijl de host zelf geen band heeft. Twijfel versoepelt nooit, dus alleen die extensies."""
    if host in banden or host.rsplit(".", 1)[-1] not in lijst.get("kloon_extensies", ()):
        return None
    naam = _naam(host)
    if len(naam) < 4:
        return None
    goed = sorted(s for s, b in banden.items() if any(x[0] == "goed" for x in b) and _naam(s) == naam)
    return goed[0] if goed else None


def signalen(tekst: str, urls, banden: dict, lijst: dict) -> list[dict]:
    """Wat het bericht of zijn bronnen verraden over hun herkomst: een netwerkdomein of een kloon, met de bron van dat
    signaal. Geen oordeel."""
    hosts = hosts_in(tekst)
    for u in urls:
        h = host_van(u)
        if h and h not in hosts:
            hosts.append(h)
    uit = []
    for h in hosts:
        n = netwerk_van(h, lijst)
        if n is not None:
            uit.append({"soort": "netwerk", **n})
            continue
        k = kloon_van(h, banden, lijst)
        if k is not None:
            uit.append({"soort": "kloon", "host": h, "lijkt_op": k,
                        "bron": "EU DisinfoLab: de extensies van Doppelgänger"})
    return uit


# --- de lijst bouwen en tellen -----------------------------------------------------------------------------------

def bouw_lijst(pravda_sites: list[str], euvs: Counter, banden: dict) -> dict:
    """De lijst uit de bronnen: Pravda (achtervoegsel en losse sites), EUvsDisinfo met minstens `MIN_GEVALLEN`, zonder
    platforms en zonder sites met band *goed*."""
    goed = {s for s, b in banden.items() if any(x[0] == "goed" for x in b)}
    bron_p = "CheckFirst/DFRLab, github.com/CheckFirstHQ/pravda-network (gelezen 2026-11-07)"
    domeinen = {s: {"netwerk": "Pravda", "bron": bron_p} for s in sorted(pravda_sites) if not s.endswith("news-pravda.com")}
    for host, n in sorted(euvs.items()):
        if n >= MIN_GEVALLEN and host not in PLATFORMS and host not in goed and host not in domeinen:
            domeinen[host] = {"netwerk": "EUvsDisinfo", "bron": "EUvsDisinfo, verspreider in de database", "gevallen": n}
    return {"_meta": ("Bekende netwerkdomeinen en de extensies van klonen (PLAN #32.58, B62): een signaal met zijn bron, "
                      "geen oordeel. Alleen domeinnamen. Herkomst per domein in 'bron'."),
            "achtervoegsels": {"news-pravda.com": {"netwerk": "Pravda", "bron": bron_p,
                                                   "subdomeinen": PRAVDA_SUBDOMEINEN}},
            "domeinen": domeinen, "kloon_extensies": list(KLOON_EXTENSIES)}


def _bouwen() -> None:  # pragma: no cover - op de bestanden
    import csv
    import gzip

    from doublecheck import bronnen as br

    banden = json.loads(br.BESTAND.read_text(encoding="utf-8"))
    banden = banden.get("sites", banden)
    pravda = {r["site"] for r in csv.DictReader(gzip.open(WORTEL / "data" / "extern" / "pravda-steekproef"
                                                          / "pravda-steekproef.csv.gz", "rt", encoding="utf-8"))}
    euvs = Counter()
    for r in csv.DictReader(open(WORTEL / "data" / "euvsdisinfo_all_texts_rename.csv", encoding="utf-8")):
        for o in (r.get("Outlets") or "").split(","):
            h = o.strip().lower()
            if re.fullmatch(r"(?:[a-z0-9-]+\.)+[a-z]{2,}", h):
                euvs[h.removeprefix("www.")] += 1
    lijst = bouw_lijst(sorted(pravda), euvs, banden)
    LIJST.write_text(json.dumps(lijst, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"{len(lijst['domeinen'])} domeinen, {Counter(v['netwerk'] for v in lijst['domeinen'].values())}")


NEP_SETS = frozenset({"O", "O'", "N", "M", "D", "V"})
WAAR_SETS = frozenset({"W", "W2", "W'", "W-merk", "K", "F", "G", "G2"})


def _tellen() -> None:  # pragma: no cover - op de bestanden
    """Hoe vaak een netwerkdomein of kloon voorkomt: in de berichten van elke meting en in de tiplineberichten van
    Meedan, en in de bronnen die de lezer noemde (met hun rol); per soort set (nep of waar). Schrijft
    `data/netwerken/telling.json`."""
    import csv

    from doublecheck import bronnen as br

    banden = json.loads(br.BESTAND.read_text(encoding="utf-8"))
    banden = banden.get("sites", banden)
    lijst = json.loads(LIJST.read_text(encoding="utf-8"))
    soort = lambda s: "nep" if s in NEP_SETS else ("waar" if s in WAAR_SETS else "anders")  # noqa: E731
    berichten, bronnen, voorbeelden = Counter(), Counter(), []
    for map_ in sorted((WORTEL / "data" / "meting").iterdir()):
        sets = {}
        if (map_ / "set.jsonl").exists():
            for regel in (map_ / "set.jsonl").read_text(encoding="utf-8").splitlines():
                r = json.loads(regel)
                sets[r["id"]] = r["set"]
                sig = signalen(r.get("tekst") or "", [], banden, lijst)
                berichten[(soort(r["set"]), "n")] += 1
                for x in sig:
                    berichten[(soort(r["set"]), x["soort"])] += 1
                    voorbeelden.append({"waar": "bericht", "meting": map_.name, "set": r["set"], **x})
        if (map_ / "antwoorden.jsonl").exists():
            for regel in (map_ / "antwoorden.jsonl").read_text(encoding="utf-8").splitlines():
                a = json.loads(regel)
                for b in a.get("bronnen", []):
                    for x in signalen("", [b.get("url") or ""], banden, lijst):
                        bronnen[(soort(a.get("set") or sets.get(a["id"], "")), x["soort"], b.get("rol") or "-")] += 1
                        voorbeelden.append({"waar": "bron", "meting": map_.name, "set": a.get("set"), "rol": b.get("rol"),
                                            **x})
    tipline = WORTEL / "data" / "extern" / "meedan-tiplines" / "claim_detection_dataset.csv"
    if tipline.exists():
        for r in csv.DictReader(open(tipline, encoding="utf-8")):
            berichten[("tipline", "n")] += 1
            for x in signalen(r.get("text") or "", [], banden, lijst):
                berichten[("tipline", x["soort"])] += 1
                voorbeelden.append({"waar": "tipline", **x})
    uit = {"berichten": {" ".join(k): v for k, v in sorted(berichten.items())},
           "bronnen": {" ".join(k): v for k, v in sorted(bronnen.items())}, "voorbeelden": voorbeelden[:200]}
    doel = WORTEL / "data" / "netwerken" / "telling.json"
    doel.parent.mkdir(parents=True, exist_ok=True)
    doel.write_text(json.dumps(uit, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: uit[k] for k in ("berichten", "bronnen")}, ensure_ascii=False, indent=1))


def main() -> None:  # pragma: no cover - CLI
    import argparse

    parser = argparse.ArgumentParser(description="Netwerkdomeinen en klonen als signaal (PLAN #32.58)")
    parser.add_argument("stap", choices=("bouwen", "tellen"))
    args = parser.parse_args()
    {"bouwen": _bouwen, "tellen": _tellen}[args.stap]()


if __name__ == "__main__":
    main()
