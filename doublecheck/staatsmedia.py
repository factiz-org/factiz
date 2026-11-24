"""Een label voor staatsmedia (PLAN #32.11). Een label bij de bron, geen oordeel.

De PO (2026-10-29): "Wel misschien aantekenen dat het een 'regeringsbron' is, zo tagged Google ook -> state owned
media." Vier delen, elk met zijn herkomst:
- (a) Wikidata (CC0): nieuwsmedia die eigendom zijn van of geleid worden door een overheid, of die Wikidata *state
  media* noemt, in een land met een RSF-score onder 55. Publieke omroepen in landen met persvrijheid (de BBC, de NOS,
  de ABC) vallen erbuiten;
- (b) de EU-sanctielijst voor Russische media (Verordening 833/2014, bijlage XV);
- (c) de Chinese media die het Amerikaanse ministerie van Buitenlandse Zaken in 2020 als *foreign mission* aanwees;
- (d) bekende staatsmedia die (a) mist, door Claude samengesteld met een reden per regel; door de PO aangenomen.
(b) en (c) zijn uit het hoofd van Claude overgenomen; de PO legt ze naast de officiële tekst.

    python -m doublecheck.staatsmedia bouwen
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from urllib.parse import urlsplit

WORTEL = Path(__file__).resolve().parent.parent
BESTAND = Path(__file__).resolve().parent / "staatsmedia.json"
RSF_GRENS = 55.0  # onder 55: "moeilijk" of "zeer ernstig" bij RSF
META = ("Label voor staatsmedia (PLAN #32.11), een label, geen oordeel. Herkomst per domein in 'bron': Wikidata (CC0, "
        "overheidseigendom of state media, in een land met een RSF-score onder 55; de scores van de World Press Freedom "
        "Index van RSF), de EU-Verordening 833/2014 (bijlage XV), de aanwijzing door het Amerikaanse ministerie van "
        "Buitenlandse Zaken (2020), en een lijst van Claude. Alleen domeinnamen en namen, geen tekst. De PO nam de lijst "
        "op 2026-10-29 aan ('ga er maar vanuit dat dit klopt'); de EU- en VS-delen, door Claude uit het hoofd overgenomen, "
        "zijn niet naast de officiële tekst gelegd.")

EU_833 = {
    "rt.com": "RT (Russia Today)", "sputniknews.com": "Sputnik", "sputnikglobe.com": "Sputnik", "ria.ru": "RIA Novosti",
    "iz.ru": "Izvestia", "rg.ru": "Rossiyskaya Gazeta", "vesti.ru": "Rossiya 24", "smotrim.ru": "VGTRK (Rossiya)",
    "1tv.ru": "Pervyi Kanal", "ntv.ru": "NTV", "ren.tv": "REN TV", "tvc.ru": "TV Centre",
    "tsargrad.tv": "Tsargrad", "journal-neo.su": "New Eastern Outlook", "katehon.com": "Katehon",
    "orientalreview.org": "Oriental Review", "voiceofeurope.com": "Voice of Europe", "redstar.ru": "Krasnaya Zvezda",
    "tvzvezda.ru": "TV Zvezda",
}
VS_2020 = {
    "news.cn": "Xinhua", "xinhuanet.com": "Xinhua", "cgtn.com": "CGTN", "cri.cn": "China Radio International",
    "chinadaily.com.cn": "China Daily", "people.com.cn": "People's Daily", "people.cn": "People's Daily",
    "cctv.com": "CCTV", "chinanews.com.cn": "China News Service", "ecns.cn": "China News Service",
    "globaltimes.cn": "Global Times", "yicaiglobal.com": "Yicai Global", "jfdaily.com": "Jiefang Daily",
    "xinmin.cn": "Xinmin Evening News", "bjreview.com": "Beijing Review", "ce.cn": "Economic Daily",
    "cssn.cn": "Social Sciences in China Press",
}
HANDMATIG = {
    "presstv.ir": ("Press TV", "Iran", "Engelstalige zender van de staatsomroep IRIB"),
    "irna.ir": ("IRNA", "Iran", "het staatspersbureau van Iran"),
    "kayhan.ir": ("Kayhan", "Iran", "uitgegeven onder een door de Opperste Leider benoemde directeur"),
    "farsnews.ir": ("Fars", "Iran", "persbureau gelieerd aan de Revolutionaire Garde"),
    "tasnimnews.com": ("Tasnim", "Iran", "persbureau gelieerd aan de Revolutionaire Garde"),
    "mehrnews.com": ("Mehr", "Iran", "persbureau van de Islamitische Propagandaorganisatie, een staatsorgaan"),
    "tass.com": ("TASS", "Rusland", "het staatspersbureau van Rusland"),
    "tass.ru": ("TASS", "Rusland", "het staatspersbureau van Rusland"),
    "rbth.com": ("Russia Beyond", "Rusland", "onderdeel van TV-Novosti, de uitgever van RT"),
    "aa.com.tr": ("Anadolu", "Turkije", "het staatspersbureau van Turkije"),
    "trtworld.com": ("TRT World", "Turkije", "de staatsomroep van Turkije"),
    "trt.net.tr": ("TRT", "Turkije", "de staatsomroep van Turkije"),
    "trthaber.com": ("TRT Haber", "Turkije", "de staatsomroep van Turkije"),
    "sana.sy": ("SANA", "Syrië", "het staatspersbureau van Syrië"),
    "kcna.kp": ("KCNA", "Noord-Korea", "het staatspersbureau van Noord-Korea"),
    "rodong.rep.kp": ("Rodong Sinmun", "Noord-Korea", "de krant van de regerende partij"),
    "ahram.org.eg": ("Al-Ahram", "Egypte", "staatskrant van Egypte"),
    "mena.org.eg": ("MENA", "Egypte", "het staatspersbureau van Egypte"),
    "suna-sd.net": ("SUNA", "Soedan", "het staatspersbureau van Soedan"),
    "telesurtv.net": ("teleSUR", "Venezuela", "gefinancierd door de staat Venezuela"),
    "granma.cu": ("Granma", "Cuba", "de krant van de regerende partij"),
    "prensa-latina.cu": ("Prensa Latina", "Cuba", "het staatspersbureau van Cuba"),
    "azertag.az": ("AZERTAC", "Azerbeidzjan", "het staatspersbureau van Azerbeidzjan"),
    "aljazeera.com": ("Al Jazeera", "Qatar", "gefinancierd door de staat Qatar; zo labelt YouTube het ook"),
    "almasirah.net": ("Al-Masirah", "Jemen", "de zender van de Houthi's"),
    "saba.ye": ("Saba", "Jemen", "persbureau onder het Houthi-bestuur in Sanaa"),
    "ypagency.net": ("Yemen Press Agency", "Jemen", "persbureau dicht bij het Houthi-bestuur"),
}


def _host(url: str) -> str:
    return (urlsplit(url if "://" in url else "https://" + url).hostname or "").lower().removeprefix("www.")


def bouw(wikidata: list[dict], rsf: dict[str, float], datum: str) -> dict:
    """De lijst: per domein de naam, het land en de bron. Uit Wikidata alleen media in een land onder de RSF-grens;
    een rij zonder land of score telt niet (een label zonder grond is geen label)."""
    domeinen: dict[str, dict] = {}
    for r in wikidata:
        iso3 = r.get("iso3", {}).get("value", "")
        if iso3 not in rsf or rsf[iso3] >= RSF_GRENS:
            continue
        host = _host(r["site"]["value"])
        if host and host not in domeinen:
            domeinen[host] = {"naam": r["itemLabel"]["value"], "land": iso3,
                              "bron": f"Wikidata, overheid of state media; RSF {rsf[iso3]:.0f}"}
    for host, naam in EU_833.items():
        domeinen[host] = {"naam": naam, "land": "RUS", "bron": "EU, Verordening 833/2014 (bijlage XV)"}
    for host, naam in VS_2020.items():
        domeinen[host] = {"naam": naam, "land": "CHN", "bron": "VS, ministerie van Buitenlandse Zaken, 2020"}
    for host, (naam, land, reden) in HANDMATIG.items():
        domeinen[host] = {"naam": naam, "land": land, "bron": "Claude, door de PO aangenomen", "reden": reden}
    vinger = hashlib.sha256(json.dumps(domeinen, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:12]
    return {"_meta": META, "datum": datum, "vingerafdruk": vinger, "domeinen": dict(sorted(domeinen.items()))}


def label(url: str, lijst: dict) -> dict | None:
    """Het label van een bron: het eigen domein of een domein waar het onder valt (actualidad.rt.com valt onder
    rt.com, art.com niet)."""
    host = _host(url)
    delen = host.split(".")
    for i in range(len(delen) - 1):
        kandidaat = ".".join(delen[i:])
        if kandidaat in lijst["domeinen"]:
            return lijst["domeinen"][kandidaat]
    return None


def lees() -> dict:
    return json.loads(BESTAND.read_text(encoding="utf-8")) if BESTAND.exists() else {"domeinen": {}}


def main() -> None:  # pragma: no cover - netwerk
    import argparse
    import time
    import urllib.parse
    import urllib.request

    from doublecheck.bronnenlijst import rsf_scores

    parser = argparse.ArgumentParser(description="Een label voor staatsmedia (PLAN #32.11)")
    parser.add_argument("stap", choices=("bouwen",))
    parser.parse_args()
    eigendom = """SELECT DISTINCT ?item ?itemLabel ?site ?land WHERE {
      VALUES ?soort { wd:Q11032 wd:Q192283 wd:Q1153191 wd:Q2001305 wd:Q15265344 wd:Q1616075 wd:Q14350 }
      ?item wdt:P31 ?soort .
      { ?item wdt:P127 ?eig . } UNION { ?item wdt:P749 ?eig . } UNION { ?item wdt:P137 ?eig . }
      ?eig wdt:P31/wdt:P279* ?ov . VALUES ?ov { wd:Q7188 wd:Q327333 wd:Q2659904 wd:Q1428357 }
      ?item wdt:P856 ?site .
      OPTIONAL { ?item wdt:P17 ?land . }
      SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }
    }"""
    staat = """SELECT DISTINCT ?item ?itemLabel ?site ?land WHERE {
      ?item wdt:P31/wdt:P279* wd:Q2324556 .
      ?item wdt:P856 ?site .
      OPTIONAL { ?item wdt:P17 ?land . }
      SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }
    }"""

    def vraag(sparql: str) -> list[dict]:
        url = "https://query.wikidata.org/sparql?" + urllib.parse.urlencode({"query": sparql})
        req = urllib.request.Request(url, headers={"User-Agent": "FactizResearch/0.1 (https://factiz.org; research)",
                                                   "Accept": "application/sparql-results+json"})
        uit = json.load(urllib.request.urlopen(req, timeout=300))["results"]["bindings"]
        time.sleep(2)
        return uit

    # in delen: met de landcode erbij liep de dienst van Wikidata vast (504)
    rijen = vraag(eigendom) + vraag(staat)
    landen = sorted({r["land"]["value"].rsplit("/", 1)[1] for r in rijen if "land" in r})
    codes = {r["land"]["value"].rsplit("/", 1)[1]: r["iso3"]["value"] for r in vraag(
        "SELECT ?land ?iso3 WHERE { VALUES ?land { " + " ".join("wd:" + q for q in landen) + " } ?land wdt:P298 ?iso3 . }")}
    for r in rijen:
        q = r.get("land", {}).get("value", "").rsplit("/", 1)[-1]
        if q in codes:
            r["iso3"] = {"value": codes[q]}
    rsf = rsf_scores((WORTEL / "data" / "bronnen" / "extern" / "rsf" / "2026.csv").read_text(encoding="cp1252"))
    lijst = bouw(rijen, rsf, time.strftime("%Y-%m-%d"))
    BESTAND.write_text(json.dumps(lijst, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    bronnen = {}
    for d in lijst["domeinen"].values():
        bronnen[d["bron"].split(",")[0]] = bronnen.get(d["bron"].split(",")[0], 0) + 1
    print(f"{len(rijen)} rijen uit Wikidata; {len(lijst['domeinen'])} domeinen: {bronnen}")


if __name__ == "__main__":
    main()
