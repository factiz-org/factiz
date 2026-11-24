"""De sets voor de lat van B68, per taal (PLAN #32.66, stap 2). Eerst het Spaans (PO 2026-11-10: "Ja, werk uit"; daarna
"alleen bouwen": de sets en het meetplan, nog niet draaien).

Vier sets, vastgelegd vóór de eerste vraag aan de controle:
- **B** bekende nepbeelden van Maldita en Newtral: 50 uit 2019–2020 (de virale beelden van de beeldoogst, #32.35) en 50
  uit 2025–2026 (een kleine oogst met `rol-v3`), één beeld per artikel, met een doorgestuurde tekst die Haiku schrijft
  (`doorsturen-v1`); een beeld met een stempel van de redactie valt af. Ik lees elke tekst (B34).
- **O** verse nepteksten: onwaar of misleidend van Maldita, Newtral en EFE Verifica uit 1 oktober tot 10 november 2026.
- **W-merk** en **W** echt nieuws: echte koppen uit tien Spaanse media van de week ervoor, en artikelen van Wikinews.
- **C** ware berichten die een ontkrachting herhalen: de koppen van Maldita in de vorm "No, ..." en de conclusies die
  #32.66 uit de database haalde (`omgedraaid`). Ik lees elke zin.

De beelden alleen in het geheugen (B35); bewaard worden adressen, teksten en antwoorden.

    python -m doublecheck.latset teksten --taal es
    python -m doublecheck.latset oud --taal es
    python -m doublecheck.latset oogst indienen|ophalen --taal es
    python -m doublecheck.latset doorsturen indienen|ophalen --taal es
    python -m doublecheck.latset lezen|vast --taal es
"""

from __future__ import annotations

import collections
import hashlib
import json
import random
import re
from pathlib import Path

from doublecheck import talenset as ts

WORTEL = Path(__file__).resolve().parent.parent
LABELS = WORTEL / "docs" / "steekproeven" / "32.66-es-set.json"
ZAAD = 3266
REDACTIES = {"es": ("Maldita", "Newtral", "EFE Verifica")}
BEELDREDACTIES = {"es": ("Maldita", "Newtral")}
VENSTER = {"es": ("2026-10-01", "2026-11-10")}      # de verse nepteksten
RECENT = {"es": ("2025-01-01", "2026-11-10")}       # de recente beelden
AANTAL = {"O": 100, "W-merk": 100, "W": 50, "C": 100, "B-deel": 50}
MAX_PER_REDACTIE = 34
PER_MERK = 12                                        # 9 media à 12, om de beurt gekozen tot 100
OOGST_PER_REDACTIE = 75
RESERVE_B = 20                                       # per deel, voor stempels, dode adressen en teksten die niet kloppen
GRENS = 1.00                                         # Haiku samen: de rollen en de doorgestuurde teksten
SCHATTING_ROL = 0.0004
SCHATTING_DOORSTUREN = 0.0004
# RTVE valt af: alle feeds van RTVE staan stil in 2022 (gelezen 2026-11-10); Cadena SER weigert (403), EFE en El Periódico
# gaven geen feed terug
FEEDS = {"es": {**{m: u for m, u in ts.TALEN["es"]["feeds"].items() if m != "RTVE"},
                "ABC": "https://www.abc.es/rss/2.0/portada/",
                "elDiario.es": "https://www.eldiario.es/rss/",
                "Europa Press": "https://www.europapress.es/rss/rss.aspx",
                "El Confidencial": "https://rss.elconfidencial.com/espana/",
                "Antena 3 Noticias": "https://www.antena3.com/noticias/rss/4013050.xml"}}

_TITEL = re.compile(r"^\s*\[T\]\s*")
_NO = re.compile(r"^No[,.]\s")


class Weigering(RuntimeError):
    pass


def _sha(*delen: str) -> str:
    return hashlib.sha1("|".join(delen).encode()).hexdigest()[:12]


def map_voor(taal: str) -> Path:
    return WORTEL / "data" / "talen" / "lat" / taal


def kies_o(rijen: list[dict], taal: str = "es", n: int = AANTAL["O"], max_per: int = MAX_PER_REDACTIE,
           uitgesloten: set[str] = frozenset(), zaad: int = ZAAD) -> list[dict]:
    """Verse nepteksten: alleen checks van de redacties van die taal, in het venster, onwaar of misleidend, hoogstens
    `max_per` per redactie (`talenset.kies_checks`)."""
    van, tot = VENSTER[taal]
    binnen = [r for r in rijen if r["publisher"] in REDACTIES[taal] and van <= r["datum"][:10] <= tot]
    jaren = tuple(sorted({van[:4], tot[:4]}))
    return ts.kies_checks(binnen, jaren, n, "O", max_per=max_per, eigen=True, uitgesloten=uitgesloten, zaad=zaad)


def correcties(titels: list[dict], conclusies: list[dict], n: int = AANTAL["C"], zaad: int = ZAAD) -> list[dict]:
    """Ware berichten die een ontkrachting herhalen: elke gevonden conclusie, aangevuld met koppen in de vorm "No, ...".
    Zonder `eigen_urls`: een rood dat het artikel van de redactie noemt, is bij een ware zin geen bewijs maar een vals
    alarm (`meting.auto_label`); het artikel staat apart in `artikel`."""
    def item(r: dict, tekst: str) -> dict:
        return {"id": "C:" + _sha(r["adres"], tekst), "set": "C", "tekst": tekst, "datum": (r.get("datum") or "")[:10],
                "redactie": r["site"], "artikel": r["adres"]}

    uit, gezien = [], set()
    for r in sorted(conclusies, key=lambda r: r["adres"]):
        tekst = " ".join(r["bewering"].split())
        if tekst.lower() not in gezien:
            gezien.add(tekst.lower())
            uit.append(item(r, tekst))
    rest = []
    for r in sorted(titels, key=lambda r: (r["adres"], r["bewering"])):
        tekst = " ".join(_TITEL.sub("", r["bewering"]).split())
        if _TITEL.match(r["bewering"]) and _NO.match(tekst) and tekst.lower() not in gezien:
            gezien.add(tekst.lower())
            rest.append(item(r, tekst))
    random.Random(zaad).shuffle(rest)
    return (uit + rest)[:n]


def om_de_beurt(rijen: list[dict], n: int) -> list[dict]:
    """De koppen om de beurt per medium, zodat geen medium tekortkomt als er na `n` wordt afgekapt."""
    per = collections.defaultdict(list)
    for r in rijen:
        per[r["merk"]].append(r)
    uit, i = [], 0
    while len(uit) < n and any(len(v) > i for v in per.values()):
        uit += [v[i] for v in per.values() if len(v) > i][: n - len(uit)]
        i += 1
    return uit


def wayback(url: str, jaar: str) -> str:
    """De kopie in de Wayback Machine die het dichtst bij dat jaar ligt, als het ruwe bestand (`id_`)."""
    return f"https://web.archive.org/web/{jaar}id_/{url}"


def jaar_van(datum: str, url: str, anders: str = "2020") -> str:
    """Het jaar voor de reservekopie: uit de datum van de check, anders uit het adres van het artikel."""
    if datum[:4].isdigit():
        return datum[:4]
    m = re.search(r"/(20\d\d)(?:\d{4})?/", url)
    return m.group(1) if m else anders


# Een bestandsnaam die zegt dat de redactie het beeld bewerkte: de gestempelde voorplaat (§256-vervolg, 2026-11-10: 61
# van de 70 virale beelden met precies één viraal beeld per artikel droegen een stempel; dat was meestal het deelbeeld)
_STEMPELWOORD = re.compile(r"(?i)bulo|fake|fals[oa]|enga[ñn]os[oa]|montaje|portada|timo|desinforma|verifica")


def kies_viraal(beelden: list[str], rollen: list[str], deelbeelden: frozenset[str] = frozenset()) -> str | None:
    """Het beeld dat iemand zou doorsturen: het eerste virale beeld dat niet het deelbeeld van het artikel is en geen
    stempelwoord in de bestandsnaam heeft. De stempelvraag aan Haiku blijft de laatste toets."""
    for b, rol in zip(beelden, rollen):
        naam = b.rsplit("/", 1)[-1]
        if rol == "viraal" and b not in deelbeelden and not _STEMPELWOORD.search(naam):
            return b
    return None


def virale_oud(rollen: list[dict], negatief: dict[str, dict], per_redactie: int, zaad: int = ZAAD,
               deelbeelden: frozenset[str] = frozenset()) -> list[dict]:
    """Uit de rollen van de beeldoogst (`rol-v3`): per artikel met een onware of misleidende check het beeld van
    `kies_viraal`, per redactie een vaste steekproef van `per_redactie`."""
    from doublecheck.terugaanvoer import artikel

    per = collections.defaultdict(list)
    for r in sorted(rollen, key=lambda r: r["artikel"]):
        beeld = kies_viraal(r["beelden"], r["rollen"], deelbeelden)
        c = negatief.get(artikel(r["artikel"]))
        if beeld and c:
            per[c["redactie"]].append({"id": "B:" + _sha(beeld), "set": "B", "deel": "oud", "bewering": c["tekst"],
                                       "datum": c["datum"], "beeld": beeld,
                                       "beeld_reserve": wayback(beeld, jaar_van(c["datum"], r["artikel"])),
                                       "eigen_urls": [r["artikel"]], "redactie": c["redactie"]})
    uit = []
    for redactie, lijst in sorted(per.items()):
        uit += random.Random(f"{zaad}:{redactie}").sample(lijst, min(per_redactie, len(lijst)))
    return uit


# --- de doorgestuurde tekst bij een beeld (`doorsturen-v1`) ----------------------------------------------------------

DOORSTUREN = "doorsturen-v1"
_VRAAG_DOORSTUREN = """This image circulated online. The fact-checker {redactie} reviewed this claim about it: \
"{bewering}"

1. stempel: does the image carry a mark that a fact-checker or newsroom added, such as a stamp or label (FALSO, BULO, \
FAKE, ENGAÑOSO, MONTAJE), a cross, a red frame, an arrow or circle that points something out, or the logo of Maldita, \
Newtral or another fact-checker? A logo or watermark that was part of the original (a TV channel, a newspaper, a social \
media handle) does not count.
2. tekst: write the message a person would send with this image to a WhatsApp group in Spain: one or two sentences in \
Spanish, in their own words, stating the claim as if it were true. No words of the fact-checker, no verdict, no doubt, \
no hashtags or emoji. Keep the names, places, dates and numbers of the claim."""

_SCHEMA_DOORSTUREN = {"type": "object", "additionalProperties": False, "required": ["waarom", "stempel", "tekst"],
                      "properties": {"waarom": {"type": "string"}, "stempel": {"type": "boolean"},
                                     "tekst": {"type": "string"}}}


def doorstuurverzoek(k: dict, beeld: bytes) -> dict:
    """De vraag aan Haiku: het beeld (verkleind, alleen in het geheugen) en de bewering van de redactie, met vast JSON."""
    from doublecheck.beschrijvingvraag import _jpeg
    from doublecheck.modellen import MODELLEN

    inhoud = [{"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": _jpeg(beeld)}},
              {"type": "text", "text": _VRAAG_DOORSTUREN.format(redactie=k["redactie"], bewering=k["bewering"])}]
    return {"custom_id": "ds-" + k["id"].split(":", 1)[1], "params": {
        "model": MODELLEN["haiku"]["id"], "max_tokens": 600, "messages": [{"role": "user", "content": inhoud}],
        "output_config": {"effort": "low", "format": {"type": "json_schema", "schema": _SCHEMA_DOORSTUREN}}}}


def lees_doorsturen(tekst: str) -> dict:
    """Of het beeld een stempel draagt en de tekst; zonder een duidelijk *nee* op de stempel telt het beeld niet als
    schoon (`None`)."""
    try:
        d = json.loads(tekst)
    except (json.JSONDecodeError, TypeError):
        return {"stempel": None, "tekst": ""}
    if not isinstance(d, dict):
        return {"stempel": None, "tekst": ""}
    stempel = d.get("stempel") if isinstance(d.get("stempel"), bool) else None
    return {"stempel": stempel, "tekst": " ".join(str(d.get("tekst") or "").split())}


def b_set(kandidaten: list[dict], antwoorden: dict[str, dict], labels: dict[str, str],
          per_deel: int = AANTAL["B-deel"]) -> list[dict]:
    """Per deel (oud, nieuw), in de volgorde van de kandidaten, de eerste `per_deel` met een schoon beeld, een tekst, en
    mijn label *goed* (de tekst is de bewering). Het bericht is de doorgestuurde tekst; de bewering blijft erbij."""
    uit, per = [], collections.Counter()
    for k in kandidaten:
        a = antwoorden.get(k["id"])
        if per[k["deel"]] >= per_deel or a is None or a["stempel"] is not False or not a["tekst"]:
            continue
        if labels.get(k["id"]) != "goed":
            continue
        per[k["deel"]] += 1
        uit.append({**k, "tekst": a["tekst"]})
    return uit


# --- de bestanden, de database en het netwerk ----------------------------------------------------------------------

def _jsonl(pad: Path) -> list[dict]:  # pragma: no cover - een bestand
    return [json.loads(r) for r in pad.read_text(encoding="utf-8").splitlines() if r.strip()] if pad.exists() else []


def _schrijf(pad: Path, rijen: list[dict], toevoegen: bool = False) -> None:  # pragma: no cover - een bestand
    pad.parent.mkdir(parents=True, exist_ok=True)
    with pad.open("a" if toevoegen else "w", encoding="utf-8") as f:
        f.writelines(json.dumps(r, ensure_ascii=False) + "\n" for r in rijen)


def _labels() -> dict[str, str]:  # pragma: no cover - een bestand
    return json.loads(LABELS.read_text(encoding="utf-8"))["labels"] if LABELS.exists() else {}


def _teksten(taal: str) -> None:  # pragma: no cover - de database, de bestanden en het netwerk
    """O, C, W-merk en W; weigert als ze al vastliggen."""
    import datetime

    from doublecheck import omgedraaid as om
    from doublecheck import terugaanvoer as ta
    from doublecheck.narekening import met_kopjesbalk
    from doublecheck.sheffield import regels
    from doublecheck.speuren import _feeds, w_merk_uit

    pad = map_voor(taal) / "teksten.jsonl"
    if pad.exists():
        raise Weigering(f"{pad} ligt al vast")
    weg = ts.gebruikt([r for p in ts.gebruikte_paden(taal, 2) for r in regels(WORTEL / p)])
    o = kies_o(ts._checks(taal), taal, uitgesloten=weg["claims"])
    checks = ta.uniek(_jsonl(ta.MAP / "checks.jsonl"))
    titels = [c for c in checks if c["site"] in REDACTIES[taal] and _TITEL.match(c["bewering"])]
    labels = json.loads(om.LABELS.read_text(encoding="utf-8"))["labels"]
    conclusies = [r for r in _jsonl(om.SET) if labels.get(r["id"]) == "conclusie"]
    c = correcties(titels, conclusies)
    sinds = (datetime.date.today() - datetime.timedelta(days=ts.DAGEN)).isoformat()
    wm = w_merk_uit(_feeds(sinds, FEEDS[taal]), per_merk=PER_MERK, sinds=sinds)
    wm = om_de_beurt([r for r in wm if r["id"] not in weg["ids"]], AANTAL["W-merk"])
    wikinews = regels(WORTEL / "data" / "echtnieuws" / f"wikinews-{taal}.jsonl")
    w = ts.kies_wikinews([r for r in wikinews if r["sleutel"] not in weg["sleutels"] and ts.wikinews_artikel(r)
                          and not met_kopjesbalk({"datum": r.get("datum"), "tekst": r.get("tekst") or ""})],
                         AANTAL["W"], ZAAD)
    _schrijf(pad, o + c + wm + w)
    print(f"O {len(o)} {dict(collections.Counter(r['publisher'] for r in o))}; C {len(c)}; "
          f"W-merk {len(wm)} {dict(collections.Counter(r['merk'] for r in wm))}; W {len(w)}")


def _negatief(redacties: tuple[str, ...]) -> dict[str, dict]:  # pragma: no cover - de database
    """Per artikel de bewering van een onware of misleidende check van die redacties, uit de database."""
    import sqlite3

    from doublecheck.terugaanvoer import artikel

    conn = sqlite3.connect(f"file:{WORTEL / 'doublecheck.db'}?mode=ro", uri=True)
    uit: dict[str, dict] = {}
    for url, pub, d, tekst in conn.execute(
            "SELECT f.url, f.publisher, f.review_date, c.canonical_text FROM factcheck f JOIN claim c USING (claim_id)"
            " WHERE f.verdict_normalized IN ('onwaar', 'misleidend') ORDER BY f.url, c.canonical_text"):
        redactie = next((r for r in redacties if r.lower().split()[0] in (url or "").lower()), None)
        if redactie and artikel(url) not in uit:
            uit[artikel(url)] = {"tekst": " ".join(tekst.split()), "datum": (d or "")[:10], "redactie": redactie,
                                 "url": url}
    conn.close()
    return uit


def _oud(taal: str) -> None:  # pragma: no cover - de bestanden en de database
    pad = map_voor(taal) / "b-oud.jsonl"
    if pad.exists():
        raise Weigering(f"{pad} ligt al vast")
    rollen = [r for r in _jsonl(WORTEL / "data" / "beeldoogst" / "rollen.jsonl")
              if any(h in r["artikel"] for h in ("maldita.es", "newtral.es"))]
    deel = frozenset(r["beeld"] for r in _jsonl(WORTEL / "data" / "beeldoogst" / "beelden.jsonl")
                     if r.get("deel") and any(h in r["artikel"] for h in ("maldita.es", "newtral.es")))
    b = virale_oud(rollen, _negatief(BEELDREDACTIES[taal]), AANTAL["B-deel"] // 2 + RESERVE_B, deelbeelden=deel)
    _schrijf(pad, b)
    print(f"oud {len(b)} {dict(collections.Counter(r['redactie'] for r in b))}")


def _uitgegeven(taal: str) -> float:  # pragma: no cover - een bestand
    return sum(b["schatting"] if b.get("werkelijk") is None else b["werkelijk"]
               for b in _jsonl(map_voor(taal) / "batches.jsonl"))


def _dien_in(client, taal: str, soort: str, verzoeken: list[dict], schatting: float) -> None:  # pragma: no cover
    if _uitgegeven(taal) + schatting > GRENS:
        raise Weigering(f"${_uitgegeven(taal) + schatting:.2f} gaat over de grens van ${GRENS:.2f}")
    batch = client.messages.batches.create(requests=verzoeken)
    _schrijf(map_voor(taal) / "batches.jsonl", [{"id": batch.id, "soort": soort, "schatting": round(schatting, 4),
                                                  "aantal": len(verzoeken),
                                                  "ids": [v["custom_id"] for v in verzoeken]}], toevoegen=True)
    print(f"batch {batch.id}: {len(verzoeken)} {soort}, geschat ${schatting:.3f}")


def _haal_op(client, taal: str, soort: str) -> list[tuple[str, str]]:  # pragma: no cover - de Batch API
    """De antwoorden van de dichte batches van die soort, als (custom_id, tekst); de kosten in `batches.jsonl`."""
    from doublecheck.modellen import MODELLEN

    pad, prijs = map_voor(taal) / "batches.jsonl", MODELLEN["haiku"]
    batches, uit = _jsonl(pad), []
    for b in batches:
        if b["soort"] != soort or b.get("werkelijk") is not None:
            continue
        status = client.messages.batches.retrieve(b["id"])
        if status.processing_status != "ended":
            print(f"batch {b['id']}: {status.processing_status}, {status.request_counts}")
            continue
        kosten = 0.0
        for r in client.messages.batches.results(b["id"]):
            if r.result.type != "succeeded":
                continue
            msg = r.result.message
            kosten += (msg.usage.input_tokens * prijs["in"] + msg.usage.output_tokens * prijs["uit"]) / 1e6
            uit.append((r.custom_id, "".join(getattr(blok, "text", "") or "" for blok in msg.content)))
        b["werkelijk"] = round(kosten, 4)
        print(f"batch {b['id']}: {b['aantal']} {soort}, ${kosten:.3f}")
    _schrijf(pad, batches)
    print(f"samen ${_uitgegeven(taal):.3f} van ${GRENS:.2f}")
    return uit


def _oogst(taal: str, sub: str) -> None:  # pragma: no cover - netwerk en de Batch API
    """De recente virale beelden: per artikel de pagina en de beelden, alleen in het geheugen, en `rol-v3`."""
    import io

    import anthropic
    from PIL import Image

    from doublecheck import beeldindexmeting as bm
    from doublecheck import beeldrolvraag as br
    from doublecheck import vindronde as vr
    from doublecheck.terugaanvoer import artikel
    from doublecheck.varianten import laad_sleutel

    laad_sleutel()
    client = anthropic.Anthropic()
    map_ = map_voor(taal)
    if sub == "indienen":
        if (map_ / "oogst.jsonl").exists():
            raise Weigering("de oogst ligt al vast")
        van, tot = RECENT[taal]
        o_artikelen = {artikel(u) for r in _jsonl(map_ / "teksten.jsonl") if r["set"] == "O"
                       for u in r.get("eigen_urls") or ()}
        per = collections.defaultdict(list)
        for a, c in sorted(_negatief(BEELDREDACTIES[taal]).items()):
            if van <= c["datum"] <= tot and a not in o_artikelen:
                per[c["redactie"]].append(c)
        werk = []
        for redactie, lijst in sorted(per.items()):
            werk += random.Random(f"{ZAAD}:oogst:{redactie}").sample(lijst, min(OOGST_PER_REDACTIE, len(lijst)))
        web, verzoeken, rijen = bm.Beleefd(), [], []
        for c in werk:
            if not web.mag(c["url"]):
                rijen.append({"artikel": c["url"], "status": "robots"})
                continue
            antwoord = web._vraag(c["url"])
            if antwoord is None or antwoord.status_code != 200:
                rijen.append({"artikel": c["url"], "status": getattr(antwoord, "status_code", "fout")})
                continue
            titel, beelden = vr.beelden_met_context(antwoord.text, str(antwoord.url))
            goed, inhoud = [], []
            for b in beelden[:br.MAX_BEELDEN]:
                data = web.beeld(b["beeld"])
                if data is None:
                    continue
                try:
                    with Image.open(io.BytesIO(data)) as im:
                        if min(im.size) < bm.MIN_ZIJDE:
                            continue
                except Exception:   # geen beeld: overslaan; alleen de soort (DR3)
                    continue
                goed.append(b)
                inhoud.append(data)
            if goed:
                cid = "rol-" + _sha(c["url"])
                verzoeken.append({"custom_id": cid, "params": br.verzoek(c["tekst"], titel, goed, versie="rol-v3",
                                                                        beelden_bytes=inhoud)})
            del inhoud
            rijen.append({"artikel": c["url"], "status": 200, "custom_id": "rol-" + _sha(c["url"]), **c,
                          "beelden": [b["beeld"] for b in goed]})
        _schrijf(map_ / "oogst.jsonl", rijen)
        print(f"{len(werk)} artikelen, {len(verzoeken)} met beelden")
        if verzoeken:
            _dien_in(client, taal, "rol", verzoeken, SCHATTING_ROL * len(verzoeken))
        return
    rijen = {r.get("custom_id"): r for r in _jsonl(map_ / "oogst.jsonl")}
    nieuw = []
    for cid, tekst in _haal_op(client, taal, "rol"):
        r = rijen.get(cid)
        if r is None:
            continue
        rollen = br.lees_rollen(tekst, len(r["beelden"]))
        # het eerste beeld is het deelbeeld; bij Newtral vaak het enige (de rest laadt later in), dan toch dat
        beeld = kies_viraal(r["beelden"], rollen, frozenset(r["beelden"][:1])) or kies_viraal(r["beelden"], rollen)
        if beeld:
            nieuw.append({"id": "B:" + _sha(beeld), "set": "B", "deel": "nieuw", "bewering": r["tekst"],
                          "datum": r["datum"], "beeld": beeld,
                          "beeld_reserve": wayback(beeld, jaar_van(r["datum"], r["artikel"], "2026")),
                          "eigen_urls": [r["artikel"]], "redactie": r["redactie"]})
    per = collections.defaultdict(list)
    for k in sorted(nieuw, key=lambda k: k["id"]):
        per[k["redactie"]].append(k)
    gekozen = []
    for redactie, lijst in sorted(per.items()):
        gekozen += random.Random(f"{ZAAD}:nieuw:{redactie}").sample(
            lijst, min(AANTAL["B-deel"] // 2 + RESERVE_B, len(lijst)))
    _schrijf(map_ / "b-nieuw.jsonl", gekozen)
    print(f"nieuw: {len(nieuw)} artikelen met een viraal beeld zonder stempelwoord, gekozen {len(gekozen)} "
          f"{dict(collections.Counter(k['redactie'] for k in gekozen))}")


def _kandidaten(taal: str) -> list[dict]:  # pragma: no cover - bestanden
    """Oud en nieuw, in een vaste volgorde: per deel eerst de steekproef, de reserve erachter."""
    return _jsonl(map_voor(taal) / "b-oud.jsonl") + _jsonl(map_voor(taal) / "b-nieuw.jsonl")


def _doorsturen(taal: str, sub: str) -> None:  # pragma: no cover - netwerk en de Batch API
    import anthropic

    from doublecheck import beeldindexmeting as bm
    from doublecheck.varianten import laad_sleutel

    laad_sleutel()
    client = anthropic.Anthropic()
    pad = map_voor(taal) / "doorsturen.jsonl"
    if sub == "indienen":
        klaar = {r["id"] for r in _jsonl(pad)}
        open_ = [b for b in _jsonl(map_voor(taal) / "batches.jsonl") if b["soort"] == DOORSTUREN
                 and b.get("werkelijk") is None]
        if any("ids" not in b for b in open_):
            raise Weigering("er staat een batch open zonder lijst van ids; eerst ophalen")
        bezig = {"B:" + i.removeprefix("ds-") for b in open_ for i in b["ids"]}
        web, verzoeken, dood = bm.Beleefd(), [], 0
        for k in _kandidaten(taal):
            if k["id"] in klaar or k["id"] in bezig:
                continue
            data = web.beeld(k["beeld"]) or (web.beeld(k["beeld_reserve"]) if k.get("beeld_reserve") else None)
            if data is None:
                dood += 1
                _schrijf(pad, [{"id": k["id"], "stempel": None, "tekst": "", "waarom": "beeld niet te halen"}],
                         toevoegen=True)
                continue
            verzoeken.append(doorstuurverzoek(k, data))
            del data
        print(f"{len(verzoeken)} beelden naar Haiku, {dood} niet te halen")
        if verzoeken:
            _dien_in(client, taal, DOORSTUREN, verzoeken, SCHATTING_DOORSTUREN * len(verzoeken))
        return
    nieuw = []
    for cid, tekst in _haal_op(client, taal, DOORSTUREN):
        try:
            waarom = json.loads(tekst).get("waarom", "")
        except (json.JSONDecodeError, AttributeError):
            waarom = ""
        nieuw.append({"id": "B:" + cid.removeprefix("ds-"), **lees_doorsturen(tekst), "waarom": waarom})
    _schrijf(pad, nieuw, toevoegen=True)
    print(f"{len(nieuw)} antwoorden: {dict(collections.Counter(str(r['stempel']) for r in nieuw))}")


def _lezen(taal: str) -> None:  # pragma: no cover - bestanden
    """Wat ik nog moet lezen: de teksten van B met een schoon beeld, en de zinnen van C."""
    labels = _labels()
    antwoorden = {r["id"]: r for r in _jsonl(map_voor(taal) / "doorsturen.jsonl")}
    for k in _kandidaten(taal):
        a = antwoorden.get(k["id"])
        if a and a["stempel"] is False and a["tekst"] and k["id"] not in labels:
            print(f"[{k['id']}] {k['deel']} {k['redactie']}\n  BEWERING: {k['bewering'][:220]}\n  TEKST: {a['tekst']}")
    for r in _jsonl(map_voor(taal) / "teksten.jsonl"):
        if r["set"] == "C" and r["id"] not in labels:
            print(f"[{r['id']}] C {r['redactie']}: {r['tekst']}")


def _vast(taal: str) -> None:  # pragma: no cover - bestanden
    """De set voor het meetplan: B (met mijn labels), O, W-merk, W en C (alleen wat ik als waar las)."""
    pad = map_voor(taal) / "set.jsonl"
    if pad.exists():
        raise Weigering(f"{pad} ligt al vast")
    labels = _labels()
    teksten = _jsonl(map_voor(taal) / "teksten.jsonl")
    open_c = [r["id"] for r in teksten if r["set"] == "C" and r["id"] not in labels]
    if open_c:
        raise Weigering(f"{len(open_c)} zin(nen) van C zonder label")
    antwoorden = {r["id"]: {"stempel": r["stempel"], "tekst": r["tekst"]}
                  for r in _jsonl(map_voor(taal) / "doorsturen.jsonl")}
    b = b_set(_kandidaten(taal), antwoorden, labels)
    per = collections.Counter(k["deel"] for k in b)
    if min(per.get("oud", 0), per.get("nieuw", 0)) < AANTAL["B-deel"]:
        raise Weigering(f"B is niet vol: {dict(per)}; lees eerst de rest of vraag de reserve")
    c = [r for r in teksten if r["set"] == "C" and labels.get(r["id"]) == "waar"]
    alle = b + [r for r in teksten if r["set"] in ("O", "W-merk", "W")] + c
    _schrijf(pad, alle)
    print(dict(collections.Counter(r["set"] for r in alle)))


def main() -> None:  # pragma: no cover - CLI
    import argparse

    parser = argparse.ArgumentParser(description="De sets voor de lat van B68 (PLAN #32.66, stap 2)")
    parser.add_argument("stap", choices=("teksten", "oud", "oogst", "doorsturen", "lezen", "vast"))
    parser.add_argument("sub", nargs="?", choices=("indienen", "ophalen"))
    parser.add_argument("--taal", choices=tuple(REDACTIES), required=True)
    args = parser.parse_args()
    if args.stap in ("oogst", "doorsturen") and not args.sub:
        raise SystemExit(f"{args.stap} vraagt indienen of ophalen")
    {"teksten": lambda: _teksten(args.taal), "oud": lambda: _oud(args.taal),
     "oogst": lambda: _oogst(args.taal, args.sub), "doorsturen": lambda: _doorsturen(args.taal, args.sub),
     "lezen": lambda: _lezen(args.taal), "vast": lambda: _vast(args.taal)}[args.stap]()


if __name__ == "__main__":
    main()
