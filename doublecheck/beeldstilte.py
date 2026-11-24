"""De stiltetoets voor beelden (PLAN.md #26.3).

§90 liet zien waarom die nodig is: een geleerde beeldembedding beschrijft wát
er te zien is, en dan liggen beelden van dezelfde soort dicht bij elkaar. Een
meme op hetzelfde sjabloon met een andere tekst, een andere foto van dezelfde
overstroming, een post in hetzelfde kader. M4FC had daar weinig van, dus de
valse treffers van §90 zeiden er niets over.

Alles hieronder is vastgelegd vóór het ophalen (PLAN #26.3):

- **bronnen**, alleen om te meten en buiten git: (1) de rest van M4FC, met
  dezelfde beleefdheid als de eerste keer; (2) de eerste 50 sjablonen van de
  openbare imgflip-API, met per sjabloon 10 memes die wij zelf maken; (3) de
  eerste 30 gebeurtenissen uit `GEBEURTENISSEN` met minstens 10 foto's op
  Wikimedia Commons, verkleind tot 1024 px;
- **index**: de 551 beelden van §90, plus per sjabloon de eerste meme en per
  gebeurtenis de eerste foto;
- **vragen**: de rest van M4FC, de andere memes en foto's, elk als origineel
  en in kader B;
- **routes**: de vier varianten van de combinatie, met haar drempels; niet
  opnieuw ijken op deze set;
- **tellen**: elke treffer met de hand, terecht (hetzelfde beeld) of vals.

    python -m doublecheck.beeldstilte ophalen|meten|tellen
"""

from __future__ import annotations

import collections
import json
import threading
import time
from pathlib import Path
from urllib.parse import urlsplit

M4FC_JSON = Path("data/extern/m4fc/M4FC.json")
GEKOPPELD = Path("data/extern/m4fc/gekoppeld.json")
M4FC_REST = Path("data/extern/m4fc/rest")
MAP = Path("data/extern/stilte-beelden")
UITSLAG = Path("data/kadermeting")
LABELS = Path("docs/steekproeven/26.3-stiltetoets-beelden.json")

KOP = {"User-Agent": "FactizResearch/0.1 (image silence test, measurement only; polite, 1 request per 2 s per host)"}
SJABLONEN, PER_SJABLOON = 50, 10
NODIG, PER_GEBEURTENIS = 30, 10
ONDERSCHRIFT = (60, 120)
VORMEN = ("origineel", "kader_b")

# Vastgelegd vóór het ophalen; de eerste 30 met genoeg foto's tellen.
GEBEURTENISSEN = (
    "2020 Beirut explosion", "Notre-Dame de Paris fire", "2023 Turkey–Syria earthquake",
    "2021 European floods", "January 6 United States Capitol attack", "2019–20 Australian bushfire season",
    "2022 Pakistan floods", "Hurricane Katrina", "2011 Tōhoku earthquake and tsunami", "2015 Nepal earthquake",
    "Grenfell Tower fire", "2010 Haiti earthquake", "Hurricane Maria", "Hurricane Harvey", "Camp Fire (2018)",
    "2023 Hawaii wildfires", "George Floyd protests", "Yellow vests movement", "2019–2020 Hong Kong protests",
    "Fridays for Future", "2024 Spanish floods", "North Sea flood of 1953", "Hurricane Sandy",
    "2016 Kaikōura earthquake", "2021 Suez Canal obstruction", "Funeral of Elizabeth II",
    "Ponte Morandi collapse", "Deepwater Horizon oil spill", "2017 Puebla earthquake", "2023 Libya floods",
    "2021 Cumbre Vieja volcanic eruption", "2010 eruptions of Eyjafjallajökull",
    "2022 Hunga Tonga–Hunga Haʻapai eruption and tsunami", "2019 Amazon rainforest wildfires",
    "2018 Kerala floods", "Cyclone Idai", "2023 Emilia-Romagna floods", "Coronation of Charles III and Camilla",
    "2014 Hong Kong protests", "2024 Noto earthquake", "Typhoon Haiyan", "2005 Kashmir earthquake",
    "2004 Indian Ocean earthquake and tsunami", "Women's March 2017",
)


class Weigering(Exception):
    pass


# --- de memes -----------------------------------------------------------------

def splits(tekst: str) -> tuple[str, str]:
    """Boven- en onderschrift: op de spatie die het dichtst bij het midden
    ligt, en zonder spatie (Chinees, Japans) gewoon in het midden."""
    spaties = [i for i, c in enumerate(tekst) if c == " "]
    if not spaties:
        return tekst[:len(tekst) // 2], tekst[len(tekst) // 2:]
    i = min(spaties, key=lambda i: (abs(i - len(tekst) / 2), i))
    return tekst[:i], tekst[i + 1:]


def onderschriften(rijen: list[dict], n: int) -> list[str]:
    """De Engelse stukken van de tekst-stiltetoets op memelengte, in volgorde."""
    lo, hi = ONDERSCHRIFT
    uit = [r["varianten"][0]["tekst"] for r in rijen
           if r["taal"] == "en" and lo <= len(r["varianten"][0]["tekst"]) <= hi]
    return uit[:n]


def maak_meme(sjabloon, boven: str, onder: str):
    """Wit met een zwarte rand, bovenaan en onderaan, zoals een meme eruitziet."""
    import textwrap

    from PIL import ImageDraw, ImageFont

    beeld = sjabloon.convert("RGB").copy()
    b, h = beeld.size
    maat = max(14, h // 12)
    lettertype = ImageFont.load_default(size=maat)
    teken = ImageDraw.Draw(beeld)
    breedte = max(8, int(b / (maat * 0.55)))
    rand = max(1, maat // 12)

    def blok(tekst: str, y: int, omhoog: bool) -> None:
        regels = textwrap.wrap(tekst.upper(), breedte)[:3]
        hoogte = maat + rand * 2
        if omhoog:
            y -= hoogte * len(regels)
        for regel in regels:
            lengte = teken.textlength(regel, font=lettertype)
            teken.text(((b - lengte) / 2, y), regel, font=lettertype, fill="white",
                       stroke_width=rand, stroke_fill="black")
            y += hoogte

    blok(boven, max(4, h // 40), omhoog=False)
    blok(onder, h - max(4, h // 40), omhoog=True)
    return beeld


# --- ophalen ------------------------------------------------------------------

def rest_indices(aantal: int, gekoppeld: set[str]) -> list[int]:
    return [i for i in range(aantal) if str(i) not in gekoppeld]


def kies_bestanden(antwoord: dict, n: int) -> list[dict]:
    """Uit een categorie op Commons de eerste `n` foto's (JPEG, minstens 800 px
    breed), op titel; met minder dan `n` telt de gebeurtenis niet mee."""
    paginas = sorted((antwoord.get("query") or {}).get("pages", {}).values(), key=lambda p: p["title"])
    uit = []
    for p in paginas:
        info = (p.get("imageinfo") or [{}])[0]
        if info.get("mime") != "image/jpeg" or info.get("width", 0) < 800 or not info.get("thumburl"):
            continue
        licentie = ((info.get("extmetadata") or {}).get("LicenseShortName") or {}).get("value", "")
        uit.append({"titel": p["title"], "url": info["thumburl"], "pagina": info.get("descriptionurl", ""),
                    "licentie": licentie})
    return uit[:n] if len(uit) >= n else []


def _haal(client, url: str):
    try:
        r = client.get(url, timeout=30, follow_redirects=True)
    except Exception as fout:  # netwerkfouten tellen als "niet gelukt"
        return None, type(fout).__name__
    if r.status_code != 200:
        return None, f"http {r.status_code}"
    handtekeningen = [(b"\xff\xd8\xff", "jpg"), (b"\x89PNG", "png"), (b"GIF8", "gif"), (b"RIFF", "webp")]
    for kop, ext in handtekeningen:
        if r.content.startswith(kop) and (ext != "webp" or r.content[8:12] == b"WEBP"):
            return r.content, ext
    return None, "geen beeld"


def ophalen_m4fc() -> collections.Counter:
    """De beelden buiten de gekoppelde, met de beleefdheid van de eerste keer:
    per host één verzoek tegelijk en 2 s ertussen, hosts naast elkaar; de
    Wayback-kopie samen één per 4 s. Hervatbaar via `rest-status.jsonl`."""
    import concurrent.futures as cf

    import httpx

    items = json.loads(M4FC_JSON.read_text(encoding="utf-8"))
    gekoppeld = set(json.loads(GEKOPPELD.read_text(encoding="utf-8")))
    status = M4FC_REST.parent / "rest-status.jsonl"
    M4FC_REST.mkdir(parents=True, exist_ok=True)
    klaar = set()
    if status.exists():
        klaar = {json.loads(r)["index"] for r in status.read_text(encoding="utf-8").splitlines() if r.strip()}
    per_host: dict[str, list[int]] = collections.defaultdict(list)
    for i in rest_indices(len(items), gekoppeld):
        if i not in klaar:
            per_host[urlsplit(items[i]["image_url"] or "").netloc].append(i)
    print(f"M4FC-rest: {sum(map(len, per_host.values()))} te doen over {len(per_host)} hosts", flush=True)
    slot, wayback = threading.Lock(), threading.Lock()
    laatst = [0.0]
    teller: collections.Counter = collections.Counter()

    def host_werk(indices: list[int]) -> None:
        with httpx.Client(headers=KOP) as client:
            for i in indices:
                item = items[i]
                data, uitkomst = _haal(client, item["image_url"]) if item.get("image_url") else (None, "geen url")
                if data is None and item.get("wayback_image_url"):
                    with wayback:
                        wacht = laatst[0] + 4 - time.monotonic()
                        if wacht > 0:
                            time.sleep(wacht)
                        data, uitkomst = _haal(client, item["wayback_image_url"])
                        laatst[0] = time.monotonic()
                bestand = f"{i:05d}.{uitkomst}" if data is not None else None
                if bestand:
                    (M4FC_REST / bestand).write_bytes(data)
                with slot:
                    with status.open("a", encoding="utf-8") as uit:
                        uit.write(json.dumps({"index": i, "bestand": bestand,
                                              "uitkomst": None if bestand else uitkomst}) + "\n")
                    teller["gelukt" if bestand else "mislukt"] += 1
                    if sum(teller.values()) % 250 == 0:
                        print(f"  {dict(teller)}", flush=True)
                time.sleep(2)

    with cf.ThreadPoolExecutor(8) as pool:
        list(pool.map(host_werk, sorted(per_host.values(), key=len, reverse=True)))
    return teller


def ophalen_sjablonen() -> int:
    import httpx

    doel = MAP / "sjablonen"
    doel.mkdir(parents=True, exist_ok=True)
    with httpx.Client(headers=KOP) as client:
        memes = client.get("https://api.imgflip.com/get_memes", timeout=30).json()["data"]["memes"][:SJABLONEN]
        meta = []
        for rang, m in enumerate(memes):
            data, ext = _haal(client, m["url"])
            if data is not None:
                naam = f"{rang:02d}.{ext}"
                (doel / naam).write_bytes(data)
                meta.append({"rang": rang, "bestand": naam, "naam": m["name"], "url": m["url"]})
            time.sleep(1)
    (MAP / "sjablonen.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    return len(meta)


def _categorie(client, categorie: str) -> list[dict]:
    antwoord = client.get("https://commons.wikimedia.org/w/api.php", timeout=30, params={
        "action": "query", "format": "json", "generator": "categorymembers",
        "gcmtitle": f"Category:{categorie}", "gcmtype": "file", "gcmlimit": 100,
        "prop": "imageinfo", "iiprop": "url|size|mime|extmetadata", "iiurlwidth": 1024,
        "iiextmetadatafilter": "LicenseShortName"}).json()
    time.sleep(1)
    return kies_bestanden(antwoord, PER_GEBEURTENIS)


def aanvullen_commons() -> int:
    """De foto's die bij het ophalen een limietfout kregen (429: de
    beeldserver maakt de verkleinde versie op aanvraag en vraagt dan 600 s
    geduld). Wacht één keer zo lang als gevraagd, en 3 s tussen verzoeken."""
    import httpx

    pad = MAP / "gebeurtenissen.json"
    meta = json.loads(pad.read_text(encoding="utf-8"))
    erbij = 0
    with httpx.Client(headers=KOP) as client:
        for e in meta:
            if len(e["fotos"]) >= PER_GEBEURTENIS:
                continue
            gekregen = {f["titel"] for f in e["fotos"]}
            for k, bestand in enumerate(_categorie(client, e["categorie"])):
                if bestand["titel"] in gekregen:
                    continue
                data, ext = _haal(client, bestand["url"])
                if data is None and ext == "http 429":
                    print("  limiet, 600 s wachten", flush=True)
                    time.sleep(600)
                    data, ext = _haal(client, bestand["url"])
                time.sleep(3)
                if data is not None:
                    naam = f"{e['nr']:02d}/{k:02d}.{ext}"
                    (MAP / "gebeurtenissen" / naam).write_bytes(data)
                    e["fotos"].append({**bestand, "bestand": naam})
                    erbij += 1
            e["fotos"].sort(key=lambda f: f["bestand"])
            print(f"  {e['nr']:02d} {e['categorie']}: {len(e['fotos'])} foto's", flush=True)
    pad.write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    return erbij


def ophalen_commons() -> int:
    """Eén verzoek per seconde naar de API en naar de beeldserver."""
    import httpx

    doel = MAP / "gebeurtenissen"
    meta = []
    with httpx.Client(headers=KOP) as client:
        for categorie in GEBEURTENISSEN:
            if len(meta) == NODIG:
                break
            bestanden = _categorie(client, categorie)
            if not bestanden:
                print(f"  {categorie}: te weinig foto's, overgeslagen", flush=True)
                continue
            nr = len(meta)
            (doel / f"{nr:02d}").mkdir(parents=True, exist_ok=True)
            gelukt = []
            for k, bestand in enumerate(bestanden):
                data, ext = _haal(client, bestand["url"])
                time.sleep(1)
                if data is not None:
                    (doel / f"{nr:02d}" / f"{k:02d}.{ext}").write_bytes(data)
                    gelukt.append({**bestand, "bestand": f"{nr:02d}/{k:02d}.{ext}"})
            meta.append({"nr": nr, "categorie": categorie, "fotos": gelukt})
            print(f"  {nr:02d} {categorie}: {len(gelukt)} foto's", flush=True)
    (MAP / "gebeurtenissen.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    return len(meta)


# --- meten en tellen ----------------------------------------------------------

def uitslag(treffers: list[dict], labels: dict[str, str], n_per_groep: dict[str, int]) -> dict:
    """Per groep en variant: treffers, terecht, vals en de bovengrens voor
    vals op n. Weigert zolang een treffer geen label heeft."""
    from doublecheck.cijfers import _bovengrens
    from doublecheck.kadermeting import VARIANTEN

    def sleutel(t: dict) -> str:
        return f"{t['vraag']}|{t['vorm']}|{t['index_id']}"

    ontbreekt = sorted({sleutel(t) for t in treffers if labels.get(sleutel(t)) not in ("terecht", "vals")})
    if ontbreekt:
        raise Weigering(f"{len(ontbreekt)} treffers zonder label (bijvoorbeeld {ontbreekt[:3]}); label in {LABELS}")
    uit = {g: {v: {"n": n, "treffers": 0, "terecht": 0, "vals": 0} for v in VARIANTEN}
           for g, n in n_per_groep.items()}
    for t in treffers:
        doel = uit[t["groep"]][t["variant"]]
        doel["treffers"] += 1
        doel[labels[sleutel(t)]] += 1
    for groep in uit.values():
        for doel in groep.values():
            doel["bovengrens"] = _bovengrens(doel["vals"], doel["n"])
    return uit


def lui(pad: Path) -> list[tuple[str, object]]:
    """(bestandsnaam, lader) per beeld: geladen pas als het blok aan de beurt
    is. Een lader geeft `None` voor wat geen bruikbaar beeld is."""
    from functools import partial

    from doublecheck.kadermeting import _laad

    return [(p.name, partial(_laad, p)) for p in sorted(pad.glob("*.*"))]


def _eerste(lijst: list[tuple[str, object]]) -> tuple[int, str, object] | None:
    """Het eerste bruikbare beeld: (plek, naam, beeld)."""
    for i, (naam, laad) in enumerate(lijst):
        if (beeld := laad()) is not None:
            return i, naam, beeld
    return None


def meten(*, max_vragen: int | None = None) -> dict:
    from functools import partial

    from doublecheck.beeldembedding import alle_vectoren
    from doublecheck.config import load_config
    from doublecheck.kadermeting import VARIANTEN, Routes, _kader_b, beslis, m4fc_helften, routes

    combinatie = UITSLAG / "uitslag-combinatie.json"
    if not combinatie.exists():
        raise Weigering("eerst de combinatie: python -m doublecheck.kadermeting --combinatie")
    drempels = {v: d["drempel_dino"] for v, d in json.loads(combinatie.read_text(encoding="utf-8")).items()}
    drempel_pdq = load_config().thresholds.image_same

    index_paren, _ = m4fc_helften()
    index_ids = [f"m4fc:{naam}" for naam, _ in index_paren]
    index = [b for _, b in index_paren]
    vragen: dict[str, list[tuple[str, object]]] = {"m4fc_rest": [(f"rest:{n}", laad) for n, laad in lui(M4FC_REST)]}

    rijen = [json.loads(r) for r in Path("data/stiltetoets/regels.jsonl").read_text(encoding="utf-8").splitlines() if r]
    teksten = iter(onderschriften(rijen, SJABLONEN * PER_SJABLOON))
    vragen["memes"] = []
    for naam, laad in lui(MAP / "sjablonen"):
        sjabloon = laad()
        if sjabloon is None:
            continue
        rang = naam.split(".")[0]
        onder = [splits(next(teksten)) for _ in range(PER_SJABLOON)]
        index.append(maak_meme(sjabloon, *onder[0]))
        index_ids.append(f"meme:{rang}-0")
        vragen["memes"] += [(f"meme:{rang}-{k}", partial(maak_meme, sjabloon, *tekst))
                            for k, tekst in enumerate(onder) if k]
    vragen["gebeurtenissen"] = []
    for map_ in sorted((MAP / "gebeurtenissen").iterdir()):
        fotos = lui(map_)
        if (eerste := _eerste(fotos)) is None:
            continue
        plek, naam, beeld = eerste
        index.append(beeld)
        index_ids.append(f"foto:{map_.name}-{naam}")
        vragen["gebeurtenissen"] += [(f"foto:{map_.name}-{n}", laad) for n, laad in fotos[plek + 1:]]

    r = Routes(index, alle_vectoren)
    treffers, n_per_groep = [], {}
    for groep, lijst in vragen.items():
        lijst = lijst[:max_vragen]
        n_per_groep[groep] = 0
        print(f"{groep}: {len(lijst)} vragen, {len(VORMEN)} vormen", flush=True)
        for start in range(0, len(lijst), 16):
            blok = [(vraag, b) for vraag, laad in lijst[start:start + 16] if (b := laad()) is not None]
            if not blok:
                continue
            n_per_groep[groep] += len(blok) * len(VORMEN)
            beelden = [b for _, b in blok] + [_kader_b(b) for _, b in blok]
            uitkomsten = r.vraag(beelden)
            for nr, x in enumerate(uitkomsten):
                vraag_id = blok[nr % len(blok)][0]
                vorm = VORMEN[nr // len(blok)]
                for variant in VARIANTEN:
                    gekozen = beslis(*routes(variant, x), drempel_pdq=drempel_pdq,
                                     drempel_dino=drempels[variant] if drempels[variant] is not None else float("inf"))
                    if gekozen is not None:
                        treffers.append({"groep": groep, "vraag": vraag_id, "vorm": vorm, "variant": variant,
                                         "index_id": index_ids[gekozen], "pdq": x[0][1], "dino": round(x[1][1], 4)})
    return {"treffers": treffers, "n_per_groep": n_per_groep, "index": len(index)}


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="De stiltetoets voor beelden (PLAN #26.3)")
    parser.add_argument("stap", choices=("ophalen", "meten", "tellen"))
    parser.add_argument("--bron", choices=("alle", "m4fc", "sjablonen", "commons", "commons-aanvullen"),
                        default="alle")
    parser.add_argument("--max", type=int, help="hooguit zoveel vragen per groep (proef)")
    args = parser.parse_args()
    if args.stap == "ophalen":
        if args.bron in ("alle", "sjablonen"):
            print(f"sjablonen: {ophalen_sjablonen()}", flush=True)
        if args.bron in ("alle", "commons"):
            print(f"gebeurtenissen: {ophalen_commons()}", flush=True)
        if args.bron == "commons-aanvullen":
            print(f"erbij: {aanvullen_commons()}", flush=True)
        if args.bron in ("alle", "m4fc"):
            print(f"M4FC-rest: {dict(ophalen_m4fc())}", flush=True)
    elif args.stap == "meten":
        uit = meten(max_vragen=args.max)
        MAP.mkdir(parents=True, exist_ok=True)
        (MAP / "treffers.json").write_text(json.dumps(uit, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"index {uit['index']} beelden; {len(uit['treffers'])} treffers over alle varianten;"
              f" te labelen in {LABELS}")
    else:
        uit = json.loads((MAP / "treffers.json").read_text(encoding="utf-8"))
        labels = json.loads(LABELS.read_text(encoding="utf-8"))["labels"] if LABELS.exists() else {}
        tel = uitslag(uit["treffers"], labels, uit["n_per_groep"])
        (UITSLAG / "uitslag-stilte-beelden.json").write_text(json.dumps(tel, indent=1), encoding="utf-8")
        for groep, varianten in tel.items():
            for variant, d in varianten.items():
                print(f"{groep:<15} {variant:<20} n {d['n']:>6}  treffers {d['treffers']:>4}  terecht"
                      f" {d['terecht']:>3}  vals {d['vals']:>3}  bovengrens {d['bovengrens']:.2%}")


if __name__ == "__main__":
    main()
