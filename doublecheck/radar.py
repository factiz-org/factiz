"""V3 van de radar (PLAN #32.69): wat er op Bluesky rondgaat met een beeld, tegen de nieuwsfoto's van dezelfde dagen.

De vraag: hoeveel beelden die rondgaan, zijn (gemaakt van) een echte nieuwsfoto, en vindt een index van nieuwsfoto's
ze terug? En gaan er bekende nepbeelden opnieuw rond (de beelden uit de factcheckartikelen van de beeldoogst)?

- *Luisteren:* Jetstream, de open stroom van Bluesky (geen account nodig). Bewaard per post met een beeld in een taal
  die we volgen: het adres, de beelden (als adres), de taal, de tijd en het aantal reposts. Nooit de tekst, nooit het
  beeld (B35). Engels voor een vaste tiende.
- *De nieuwsindex:* de beelden uit de RSS-feeds van de media per taal, alleen als vingerafdruk (PDQ, DINOv2).
- *Vergelijken:* de meest gedeelde posts, het beeld alleen in het geheugen, tegen de nieuwsindex en tegen de PDQ van de
  beeldoogst.

Geen privépersonen: de adressen dragen het id van een account; die blijven lokaal en gaan weg met `opruimen`.

    python -m doublecheck.radar luisteren --uren 1
    python -m doublecheck.hittewacht -- python -m doublecheck.radar nieuws
    python -m doublecheck.hittewacht -- python -m doublecheck.radar vergelijken [--top 300]
    python -m doublecheck.radar soort [--top 300]
    python -m doublecheck.radar controleren [--top 50] [--proef N]
    python -m doublecheck.radar lezen|tellen|opruimen

*V4, door de controle:* `soort` laat Haiku per post zeggen wat voor beeld het is en of er een bewering is (het beeld
zwartgemaakt, de tekst gemaskeerd); `controleren` haalt de meest gedeelde met een bewering door dezelfde functies als
`POST /check`; `lezen` zet elke post naast het antwoord, alleen op het scherm; `tellen` weigert zolang een gecontroleerde
post geen label heeft in `docs/steekproeven/32.69-radar.json`.
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from urllib.parse import urlsplit

import numpy as np

WORTEL = Path(__file__).resolve().parent.parent
MAP = WORTEL / "data" / "radar" / "v3"
JETSTREAM = ("wss://jetstream2.us-east.bsky.network/subscribe?wantedCollections=app.bsky.feed.post"
             "&wantedCollections=app.bsky.feed.repost")
TALEN = frozenset({"nl", "es"})
EN_DEEL = 0.10
MIN_REPOSTS = 10
TOP = 300
SNAPSHOT = 600   # seconden tussen twee keer wegschrijven


def beeldpost(ev: dict, talen: frozenset[str] | set[str], en_deel: float = EN_DEEL) -> dict | None:
    """Een nieuwe post met minstens één beeld in een taal die we volgen, of Engels voor een vaste `en_deel`. Zonder
    de tekst."""
    c = ev.get("commit") or {}
    if ev.get("kind") != "commit" or c.get("operation") != "create" or c.get("collection") != "app.bsky.feed.post":
        return None
    r = c.get("record") or {}
    embed = r.get("embed") or {}
    if embed.get("$type") == "app.bsky.embed.recordWithMedia":
        embed = embed.get("media") or {}
    if embed.get("$type") != "app.bsky.embed.images":
        return None
    cids = [((b.get("image") or {}).get("ref") or {}).get("$link") for b in embed.get("images") or []]
    cids = [x for x in cids if x]
    langs = [x for x in r.get("langs") or [] if isinstance(x, str)]
    uri = f"at://{ev['did']}/app.bsky.feed.post/{c.get('rkey')}"
    houden = bool(set(langs) & set(talen)) or (
        "en" in langs and int(hashlib.sha1(uri.encode()).hexdigest()[:8], 16) / 2 ** 32 < en_deel)
    if not cids or not houden:
        return None
    return {"uri": uri, "did": ev["did"], "cids": cids, "langs": langs, "tijd": r.get("createdAt")}


def repost_doel(ev: dict) -> str | None:
    """De post die een repost deelt."""
    c = ev.get("commit") or {}
    if ev.get("kind") != "commit" or c.get("operation") != "create" or c.get("collection") != "app.bsky.feed.repost":
        return None
    return ((c.get("record") or {}).get("subject") or {}).get("uri")


def cdn_url(did: str, cid: str) -> str:
    return f"https://cdn.bsky.app/img/feed_fullsize/plain/{did}/{cid}@jpeg"


def viraal(posts: dict[str, dict], min_reposts: int = MIN_REPOSTS, n: int = TOP) -> list[dict]:
    """De meest gedeelde posts, met een ondergrens."""
    return sorted((p for p in posts.values() if p["reposts"] >= min_reposts), key=lambda p: -p["reposts"])[:n]


def beelden_uit_rss(xml: bytes) -> list[dict]:
    """Per bericht in een RSS- of Atom-feed het beeld (media:content, enclosure of media:thumbnail), met titel, link en
    datum; een bericht zonder beeld valt weg."""
    import xml.etree.ElementTree as ET

    uit = []
    for item in ET.fromstring(xml).iter():
        if item.tag.split("}")[-1] not in ("item", "entry"):
            continue
        velden, beeld = {}, None
        for k in item:
            naam = k.tag.split("}")[-1]
            if naam in ("content", "enclosure", "thumbnail") and k.get("url") and beeld is None:
                soort = (k.get("type") or k.get("medium") or "image").lower()
                if "image" in soort or naam == "thumbnail":
                    beeld = k.get("url")
            elif naam == "link" and k.get("href"):
                velden["link"] = k.get("href")
            else:
                velden.setdefault(naam, (k.text or "").strip())
        if beeld:
            uit.append({"titel": velden.get("title", ""), "link": velden.get("link", ""),
                        "datum": velden.get("pubDate") or velden.get("published") or velden.get("updated") or "",
                        "beeld": beeld})
    return uit


def _bits(hexa: str) -> np.ndarray:
    return np.unpackbits(np.frombuffer(bytes.fromhex(hexa), dtype=np.uint8))


def dichtstbij(vector: np.ndarray, pdqs: list[str], index: list[dict]) -> dict:
    """De nieuwsfoto die het dichtst bij ligt: op de cosinus van de vector, en op de kleinste PDQ-afstand."""
    if not index:
        return {"dino": None, "pdq": None}
    m = np.stack([np.asarray(r["vector"], dtype=np.float32) for r in index])
    v = np.asarray(vector, dtype=np.float32)
    cos = m @ v / (np.linalg.norm(m, axis=1) * np.linalg.norm(v) + 1e-12)
    i = int(np.argmax(cos))
    beste_pdq = None
    if pdqs:
        vraag = [_bits(h) for h in pdqs]
        for r in index:
            afstand = min(int(np.count_nonzero(q != _bits(h))) for q in vraag for h in r["pdq"])
            if beste_pdq is None or afstand < beste_pdq["waarde"]:
                beste_pdq = {"url": r["url"], "waarde": afstand}
    return {"dino": {"url": index[i]["url"], "waarde": float(cos[i])}, "pdq": beste_pdq}


# --- V4: de radar door de controle ----------------------------------------------------------------------------------

SOORTEN = ("nieuwsfoto", "screenshot artikel", "screenshot post", "grafiek of kaart", "document", "strip of meme",
           "kunst of eigen foto", "anders")
SOORTVERSIE = "radarsoort-v1"
SOORT_TOP = 300
CONTROLE_TOP = 50
GRENS = 3.50          # dollar, de soort en de controle samen (PO 2026-11-10: "ja dat mag hoor", ~$2)
BRAVE_MAX = 300
LABELS = frozenset({"waar", "onwaar", "misleidend", "mening", "onbekend"})


class Weigering(Exception):
    """Tellen kan nog niet: een gecontroleerde post heeft geen label."""


def post_id(uri: str) -> str:
    """Een eigen id voor een post, zonder het account: `R:` en een hash van het adres."""
    return "R:" + hashlib.sha1(uri.encode()).hexdigest()[:10]


_SOORTVRAAG = """Below is a post that many people shared on a social network, with its image. Names, numbers and \
handles in the text are masked, and personal details in the image are blacked out.

1. "soort": what kind of image is it? Choose one:
- "nieuwsfoto": a photo of a news event, a person in the news or a place, as a news medium or agency would publish it
- "screenshot artikel": a screenshot of a news article, a headline or a news broadcast
- "screenshot post": a screenshot of a post or message on social media or in a messaging app
- "grafiek of kaart": a chart, a map or a table
- "document": a document, letter, form or official text
- "strip of meme": a comic, cartoon, meme or joke image
- "kunst of eigen foto": art, a drawing, or a personal photo (pets, food, selfies, landscapes)
- "anders": anything else
2. "bewering": does the post (text and image together) make a factual claim about news or current events that a \
fact-checker could check? Opinions, jokes and art are not claims. Answer true or false.
3. "onderwerp": the subject in at most ten English words, without names of private persons.

Post text:
{tekst}"""

_SOORTSCHEMA = {"type": "object", "additionalProperties": False, "required": ["soort", "bewering", "onderwerp"],
                "properties": {"soort": {"type": "string", "enum": list(SOORTEN)}, "bewering": {"type": "boolean"},
                               "onderwerp": {"type": "string"}}}


def soortverzoek(bericht: str, beeld: bytes, beeld_b64: str | None = None) -> dict:
    """De vraag naar de soort beeld en of er een bewering is: het zwartgemaakte beeld (verkleind, alleen in het
    geheugen) en de gemaskeerde tekst, met vaste woorden."""
    from doublecheck.modellen import MODELLEN

    if beeld_b64 is None:
        from doublecheck.beschrijvingvraag import _jpeg

        beeld_b64 = _jpeg(beeld)
    inhoud = [{"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": beeld_b64}},
              {"type": "text", "text": _SOORTVRAAG.format(tekst=" ".join(bericht.split())[:3000] or "(no text)")}]
    # Haiku 5.5 denkt eerst, en dat denken telt mee in `max_tokens`: met 300 bleef het antwoord soms leeg
    return {"params": {"model": MODELLEN["haiku"]["id"], "max_tokens": 3000,
                       "messages": [{"role": "user", "content": inhoud}],
                       "output_config": {"format": {"type": "json_schema", "schema": _SOORTSCHEMA}}}}


def lees_soort(tekst: str) -> dict:
    """Het antwoord in vaste woorden; een onbekende soort is *anders*, twijfel over de bewering is None (en gaat door de
    controle: twijfel versoepelt nooit)."""
    leeg = {"soort": "anders", "bewering": None, "onderwerp": ""}
    try:
        d = json.loads(tekst)
    except (json.JSONDecodeError, TypeError):
        return leeg
    if not isinstance(d, dict):
        return leeg
    return {"soort": d.get("soort") if d.get("soort") in SOORTEN else "anders",
            "bewering": d["bewering"] if isinstance(d.get("bewering"), bool) else None,
            "onderwerp": " ".join(str(d.get("onderwerp") or "").split())}


def te_controleren(posts: list[dict], soorten: dict[str, dict], n: int = CONTROLE_TOP) -> list[dict]:
    """De eerste `n` posts (al op volgorde van delen) met een bewering of twijfel; een post zonder soort gaat niet mee."""
    return [p for p in posts if p["uri"] in soorten and soorten[p["uri"]].get("bewering") is not False][:n]


def tekst_van(view: dict) -> str:
    """De tekst van een post uit de openbare API, zonder de beschrijving van het beeld (die ziet een gebruiker niet op
    een screenshot)."""
    return " ".join(str((view.get("record") or {}).get("text") or "").split())


def radartelling(antwoorden: list[dict], labels: dict[str, str]) -> dict:
    """Op de gecontroleerde posts, tegen wat de post echt is: gevonden (rood of oranje bij onwaar of misleidend), gemist,
    vals alarm (rood of oranje bij waar), groen bij onwaar, groen terecht. Weigert zolang er een geen label heeft."""
    import collections

    rijen = [a for a in antwoorden if "fout" not in a]
    open_ = [a["id"] for a in rijen if a["id"] not in labels]
    if open_:
        raise Weigering(f"{len(open_)} gecontroleerde posts zonder label, bijvoorbeeld {open_[:3]}")
    alarm = lambda a: a.get("kleur") in ("rood", "oranje")  # noqa: E731
    slecht = lambda a: labels[a["id"]] in ("onwaar", "misleidend")  # noqa: E731
    return {"gecontroleerd": len(rijen), "fout bij controleren": len(antwoorden) - len(rijen),
            "onwaar of misleidend": sum(slecht(a) for a in rijen),
            "gevonden": sum(slecht(a) and alarm(a) for a in rijen),
            "gemist": sum(slecht(a) and not alarm(a) for a in rijen),
            "vals alarm": sum(labels[a["id"]] == "waar" and alarm(a) for a in rijen),
            "alarm bij mening of onbekend": sum(labels[a["id"]] in ("mening", "onbekend") and alarm(a) for a in rijen),
            "groen bij onwaar": sum(slecht(a) and a.get("kleur") == "groen" for a in rijen),
            "groen terecht": sum(labels[a["id"]] == "waar" and a.get("kleur") == "groen" for a in rijen),
            "uitkomsten": dict(collections.Counter(a.get("uitkomst") for a in rijen))}


# --- het netwerk en de bestanden -----------------------------------------------------------------------------------

class _Ws:  # pragma: no cover - netwerk
    """Een kleine websocket-client met de standaardbibliotheek: alleen lezen, ping beantwoorden."""

    def __init__(self, url: str):
        import base64
        import os
        import socket
        import ssl

        u = urlsplit(url)
        self.sock = ssl.create_default_context().wrap_socket(socket.create_connection((u.hostname, 443), timeout=60),
                                                             server_hostname=u.hostname)
        sleutel = base64.b64encode(os.urandom(16)).decode()
        self.sock.sendall((f"GET {u.path}?{u.query} HTTP/1.1\r\nHost: {u.hostname}\r\nUpgrade: websocket\r\n"
                           f"Connection: Upgrade\r\nSec-WebSocket-Key: {sleutel}\r\nSec-WebSocket-Version: 13\r\n"
                           "User-Agent: FactizResearch\r\n\r\n").encode())
        self.buf = b""
        while b"\r\n\r\n" not in self.buf:
            deel = self.sock.recv(4096)
            if not deel:
                raise ConnectionError("geen antwoord op de handdruk")
            self.buf += deel
        kop, self.buf = self.buf.split(b"\r\n\r\n", 1)
        if b" 101 " not in kop.split(b"\r\n")[0]:
            raise ConnectionError(kop.split(b"\r\n")[0].decode(errors="replace"))

    def _lees(self, n: int) -> bytes:
        while len(self.buf) < n:
            deel = self.sock.recv(65536)
            if not deel:
                raise ConnectionError("verbinding dicht")
            self.buf += deel
        uit, self.buf = self.buf[:n], self.buf[n:]
        return uit

    def _pong(self, data: bytes) -> None:
        import os

        masker = os.urandom(4)
        self.sock.sendall(bytes([0x8A, 0x80 | len(data)]) + masker + bytes(b ^ masker[i % 4] for i, b in enumerate(data)))

    def berichten(self):
        stuk = b""
        while True:
            b0, b1 = self._lees(2)
            fin, opcode, lengte = b0 >> 7, b0 & 0x0F, b1 & 0x7F
            if lengte == 126:
                lengte = int.from_bytes(self._lees(2), "big")
            elif lengte == 127:
                lengte = int.from_bytes(self._lees(8), "big")
            masker = self._lees(4) if b1 >> 7 else None
            data = self._lees(lengte)
            if masker:
                data = bytes(b ^ masker[i % 4] for i, b in enumerate(data))
            if opcode == 0x9:
                self._pong(data[:125])
            elif opcode == 0x8:
                return
            elif opcode in (0x0, 0x1):
                stuk += data
                if fin:
                    yield stuk.decode("utf-8", errors="replace")
                    stuk = b""


def _jsonl(pad: Path) -> list[dict]:  # pragma: no cover - een bestand
    return [json.loads(r) for r in pad.read_text(encoding="utf-8").splitlines() if r.strip()] if pad.exists() else []


def _schrijf(pad: Path, rijen: list[dict], toevoegen: bool = False) -> None:  # pragma: no cover - een bestand
    pad.parent.mkdir(parents=True, exist_ok=True)
    with pad.open("a" if toevoegen else "w", encoding="utf-8") as f:
        f.writelines(json.dumps(r, ensure_ascii=False) + "\n" for r in rijen)


def _luisteren(uren: float) -> None:  # pragma: no cover - netwerk
    """Luisteren tot `uren` voorbij zijn; hervat met de cursor van Jetstream na een breuk, en schrijft elke tien minuten
    de stand weg (`posts.jsonl`, `stand.json`)."""
    import collections

    pad, stand = MAP / "posts.jsonl", MAP / "stand.json"
    posts = {p["uri"]: p for p in _jsonl(pad)}
    tel = collections.Counter(json.loads(stand.read_text())["tel"]) if stand.exists() else collections.Counter()
    einde, laatst, cursor = time.time() + uren * 3600, time.time(), None
    while time.time() < einde:
        try:
            ws = _Ws(JETSTREAM + (f"&cursor={cursor}" if cursor else ""))
            for tekst in ws.berichten():
                ev = json.loads(tekst)
                cursor = ev.get("time_us") or cursor
                tel["gebeurtenissen"] += 1
                p = beeldpost(ev, TALEN)
                if p:
                    posts[p["uri"]] = {**p, "reposts": 0}
                    for t in p["langs"]:
                        tel[f"beeldposts {t}"] += 1
                else:
                    doel = repost_doel(ev)
                    if doel in posts:
                        posts[doel]["reposts"] += 1
                        tel["reposts van gevolgde posts"] += 1
                if time.time() - laatst > SNAPSHOT or time.time() >= einde:
                    _schrijf(pad, list(posts.values()))
                    stand.write_text(json.dumps({"tel": tel, "cursor": cursor, "posts": len(posts),
                                                 "moment": time.strftime("%Y-%m-%d %H:%M:%S")}, indent=1))
                    laatst = time.time()
                    print(f"{time.strftime('%H:%M')} {len(posts)} beeldposts, {dict(tel)}", flush=True)
                    if time.time() >= einde:
                        break
        except (ConnectionError, OSError, ValueError) as e:   # alleen de soort fout (DR3)
            tel[f"breuk {type(e).__name__}"] += 1
            time.sleep(5)
    _schrijf(pad, list(posts.values()))


def _feeds() -> dict[str, tuple[str, str]]:  # pragma: no cover - configuratie
    from doublecheck import latset, speuren, talenset

    uit = {m: (u, "nl") for m, u in talenset.TALEN["nl"]["feeds"].items()}
    uit.update({m: (u, "es") for m, u in latset.FEEDS["es"].items()})
    uit.update({m: (u, "en") for m, u in speuren.FEEDS.items()})
    return uit


def _nieuws() -> None:  # pragma: no cover - netwerk en rekenen
    """De nieuwsindex: per feed de beelden, per beeld PDQ en DINOv2; hervatbaar."""
    from doublecheck import beeldvraag as bv
    from doublecheck.beeldindexmeting import Beleefd

    pad = MAP / "nieuws.jsonl"
    klaar = {r["url"] for r in _jsonl(pad)}
    web = Beleefd()
    for medium, (feed, taal) in _feeds().items():
        if not web.mag(feed):
            print(f"{medium}: robots.txt staat het niet toe")
            continue
        antwoord = web._vraag(feed)
        if antwoord is None or antwoord.status_code != 200:
            print(f"{medium}: {getattr(antwoord, 'status_code', 'fout')}")
            continue
        try:
            items = beelden_uit_rss(antwoord.content)
        except Exception as e:   # een feed die niet te lezen is
            print(f"{medium}: {type(e).__name__}")
            continue
        nieuw = 0
        for it in items:
            if it["beeld"] in klaar:
                continue
            data = web.beeld(it["beeld"])
            if data is None:
                continue
            try:
                k = bv.indexkenmerken(data)
            except Exception:   # kapot beeld
                continue
            del data
            _schrijf(pad, [{"url": it["beeld"], "medium": medium, "taal": taal, "titel": it["titel"],
                            "link": it["link"], "datum": it["datum"], "pdq": k["pdq"], "vector": k["vector"]}],
                     toevoegen=True)
            klaar.add(it["beeld"])
            nieuw += 1
        print(f"{medium} ({taal}): {len(items)} met beeld, {nieuw} nieuw in de index", flush=True)


def _factcheckhashes() -> tuple[np.ndarray, list[str]]:  # pragma: no cover - een bestand
    """De PDQ van elk beeld uit de beeldoogst, als bits, met het artikel erbij."""
    bits, artikelen = [], []
    for r in _jsonl(WORTEL / "data" / "beeldoogst" / "beelden.jsonl"):
        for h in r.get("pdq") or []:
            bits.append(np.frombuffer(bytes.fromhex(h), dtype=np.uint8))
            artikelen.append(r["artikel"])
    return np.stack(bits), artikelen


def _vergelijken(top: int) -> None:  # pragma: no cover - netwerk en rekenen
    from doublecheck import beeldvraag as bv
    from doublecheck.beeldindexmeting import Beleefd

    index = [{**r, "vector": bv.vector_uit_tekst(r["vector"])} for r in _jsonl(MAP / "nieuws.jsonl")]
    fc_bits, fc_artikelen = _factcheckhashes()
    posts = {p["uri"]: p for p in _jsonl(MAP / "posts.jsonl")}
    pad = MAP / "vergelijking.jsonl"
    klaar = {r["uri"] for r in _jsonl(pad)}
    web = Beleefd(pauze=0.5)
    for p in viraal(posts, n=top):
        if p["uri"] in klaar:
            continue
        data = web.beeld(cdn_url(p["did"], p["cids"][0]))
        if data is None:
            _schrijf(pad, [{"uri": p["uri"], "reposts": p["reposts"], "fout": "beeld niet te halen"}], toevoegen=True)
            continue
        try:
            k = bv.vraagkenmerken(data)
        except Exception as e:
            _schrijf(pad, [{"uri": p["uri"], "reposts": p["reposts"], "fout": type(e).__name__}], toevoegen=True)
            continue
        del data
        beste = dichtstbij(bv.vector_uit_tekst(k["vectoren"][0]), k["pdq"], index)
        vraag = np.stack([np.frombuffer(bytes.fromhex(h), dtype=np.uint8) for h in k["pdq"]])
        afstand = np.unpackbits(fc_bits[None, :, :] ^ vraag[:, None, :], axis=2).sum(axis=2).min(axis=0)
        j = int(np.argmin(afstand))
        _schrijf(pad, [{"uri": p["uri"], "reposts": p["reposts"], "langs": p["langs"], "nieuws": beste,
                        "factcheck": {"artikel": fc_artikelen[j], "waarde": int(afstand[j])}}], toevoegen=True)
    print(f"{len(_jsonl(pad))} vergeleken")


def _tellen() -> None:  # pragma: no cover - bestanden
    import collections

    posts = _jsonl(MAP / "posts.jsonl")
    stand = json.loads((MAP / "stand.json").read_text()) if (MAP / "stand.json").exists() else {}
    reposts = sorted((p["reposts"] for p in posts), reverse=True)
    print(f"{len(posts)} beeldposts; {stand.get('tel')}")
    print("reposts: " + ", ".join(f"≥{d}: {sum(r >= d for r in reposts)}" for d in (1, 5, 10, 50, 100, 500)))
    v = [r for r in _jsonl(MAP / "vergelijking.jsonl") if "fout" not in r]
    if v:
        # alleen PDQ telt: DINOv2 vanaf 0,80 zag in de stroom tekst op wit als hetzelfde beeld (PLAN #32.69, V3)
        nieuws = [r for r in v if (r["nieuws"]["pdq"] or {}).get("waarde", 256) <= 31]
        fc = [r for r in v if r["factcheck"]["waarde"] <= 31]
        print(f"vergeleken {len(v)}: bij een nieuwsfoto {len(nieuws)}, bij een beeld uit een factcheck {len(fc)}")
        print("talen: " + str(collections.Counter(t for r in v for t in r["langs"])))
    soort = [r for r in _jsonl(MAP / "soort.jsonl") if "fout" not in r]
    if soort:
        print(f"soort van {len(soort)}: {dict(collections.Counter(r['soort'] for r in soort))}; met een bewering "
              f"{sum(r['bewering'] is not False for r in soort)}")
    controle = _jsonl(MAP / "controle.jsonl")
    if controle:
        print("de controle:", radartelling(controle, _labels()))


def _views(uris: list[str]) -> dict[str, dict]:  # pragma: no cover - netwerk
    """De posts bij de openbare API van Bluesky, 25 per vraag; alleen in het geheugen."""
    import urllib.parse
    import urllib.request

    uit = {}
    for i in range(0, len(uris), 25):
        q = "&".join("uris=" + urllib.parse.quote(u) for u in uris[i:i + 25])
        verzoek = urllib.request.Request("https://public.api.bsky.app/xrpc/app.bsky.feed.getPosts?" + q,
                                         headers={"User-Agent": "FactizResearch"})
        with urllib.request.urlopen(verzoek, timeout=30) as antwoord:
            for v in json.load(antwoord)["posts"]:
                uit[v["uri"]] = v
        time.sleep(0.5)
    return uit


def _prijs(msg, model: str) -> float:  # pragma: no cover - een antwoord van de API
    from doublecheck.modellen import MODELLEN

    u, m = msg.usage, MODELLEN[model]
    # `MODELLEN` draagt batchprijzen; deze vragen gaan direct, dus zonder korting: twee keer zoveel
    return 2 * (u.input_tokens * m["in"] + u.output_tokens * m["uit"]) / 1e6


def _uitgegeven() -> float:  # pragma: no cover - bestanden
    return sum(r.get("kosten", 0.0) for naam in ("soort.jsonl", "controle.jsonl") for r in _jsonl(MAP / naam))


def _soort(top: int) -> None:  # pragma: no cover - netwerk en een model
    """De soort beeld en of er een bewering is, voor de `top` meest gedeelde posts; direct, vier tegelijk; hervatbaar."""
    import threading
    from concurrent.futures import ThreadPoolExecutor

    import anthropic

    from doublecheck import berichtcontrole as bc
    from doublecheck import opknippen
    from doublecheck.beeldindexmeting import Beleefd
    from doublecheck.config import load_config
    from doublecheck.varianten import laad_sleutel

    laad_sleutel()
    config, client, slot = load_config(None), anthropic.Anthropic(max_retries=6), threading.Lock()
    pad = MAP / "soort.jsonl"
    klaar = {r["uri"] for r in _jsonl(pad)}
    posts = [p for p in viraal({p["uri"]: p for p in _jsonl(MAP / "posts.jsonl")}, n=top) if p["uri"] not in klaar]
    views, web = _views([p["uri"] for p in posts]), Beleefd(pauze=0.5)

    def een(p: dict) -> None:
        basis = {"uri": p["uri"], "id": post_id(p["uri"]), "reposts": p["reposts"], "langs": p["langs"]}
        if _uitgegeven() > GRENS:
            return
        data = web.beeld(cdn_url(p["did"], p["cids"][0])) if p["uri"] in views else None
        if data is None:
            rij = {**basis, "fout": "post of beeld niet te halen"}
        else:
            try:
                bericht = bc.bericht_uit(tekst_van(views[p["uri"]]), data, config.ocr)
                zwart = opknippen.zwart_beeld(data, config.ocr)[0]
                msg = client.messages.create(**soortverzoek(bericht, zwart)["params"])
                if msg.stop_reason == "max_tokens":   # een afgebroken antwoord is geen soort *anders*
                    rij = {**basis, "fout": "max_tokens", "kosten": round(_prijs(msg, "haiku"), 6)}
                else:
                    rij = {**basis, **lees_soort("".join(getattr(b, "text", "") or "" for b in msg.content)),
                           "versie": SOORTVERSIE, "kosten": round(_prijs(msg, "haiku"), 6)}
            except Exception as e:  # noqa: BLE001 - alleen de soort fout (DR3)
                rij = {**basis, "fout": type(e).__name__}
            del data
        with slot:
            _schrijf(pad, [rij], toevoegen=True)

    with ThreadPoolExecutor(4) as pool:
        list(pool.map(een, posts))
    rijen = [r for r in _jsonl(pad) if "fout" not in r]
    import collections

    print(f"{len(rijen)} met een soort; uitgegeven ${_uitgegeven():.2f}")
    print(collections.Counter(r["soort"] for r in rijen))
    print("met een bewering:", sum(r["bewering"] is not False for r in rijen))


def _controleren(top: int, proef: int | None) -> None:  # pragma: no cover - live
    """De meest gedeelde posts met een bewering door `zoekcontrole.controleer`, zoals `POST /check`: kring 1, de checks
    uit de database, het beeld zwartgemaakt mee en de foto bij de bron; de tekst en het beeld alleen in het geheugen."""
    import sqlite3

    from doublecheck import berichtcontrole as bc
    from doublecheck import meting
    from doublecheck import zoekcontrole as zc
    from doublecheck.beeldindexmeting import Beleefd

    config, client, zoeker, snel, checks_voor, sites = meting._omgeving({"zoekvragen_max": BRAVE_MAX})
    beeldstap = None
    if config.beeldstap.aan:
        from doublecheck import api

        beeldstap = api._beeldstap(config)
    pad = MAP / "controle.jsonl"
    klaar = {r["uri"] for r in _jsonl(pad)}
    soorten = {r["uri"]: r for r in _jsonl(MAP / "soort.jsonl") if "fout" not in r}
    alle = viraal({p["uri"]: p for p in _jsonl(MAP / "posts.jsonl")}, n=SOORT_TOP)
    keuze = [p for p in te_controleren(alle, soorten, n=top) if p["uri"] not in klaar][:proef or top]
    views, web, kosten = _views([p["uri"] for p in keuze]), Beleefd(pauze=0.5), sqlite3.connect(":memory:")
    for p in keuze:
        if _uitgegeven() > GRENS:
            print(f"de grens van ${GRENS:.2f} is bereikt")
            break
        basis = {"uri": p["uri"], "id": post_id(p["uri"]), "reposts": p["reposts"], "langs": p["langs"],
                 "soort": soorten[p["uri"]]["soort"]}
        data = web.beeld(cdn_url(p["did"], p["cids"][0])) if p["uri"] in views else None
        if data is None:
            _schrijf(pad, [{**basis, "fout": "post of beeld niet te halen"}], toevoegen=True)
            continue
        begin = time.perf_counter()
        try:
            bericht = bc.bericht_uit(tekst_van(views[p["uri"]]), data, config.ocr)
            uit = zc.controleer(kosten, bericht, config, client, lambda q: zoeker(q, False), snel, sites, None,
                                datum=(p.get("tijd") or "")[:10] or None, beeld=data, zoek_checks=checks_voor,
                                beeldstap=beeldstap)
        except Exception as e:  # noqa: BLE001 - alleen de soort fout (DR3)
            _schrijf(pad, [{**basis, "fout": type(e).__name__}], toevoegen=True)
            continue
        finally:
            del data
        _schrijf(pad, [{**basis, "route": uit["route"], "uitkomst": uit.get("uitkomst"), "kleur": uit.get("kleur"),
                        "uitleg": uit.get("uitleg"), "over_beeld": uit.get("over_beeld", False),
                        "bronnen": [{k: b.get(k) for k in ("soort", "url", "site", "redactie", "band", "rol", "oordeel")}
                                    for b in uit.get("bronnen") or []],
                        "foto": uit.get("foto"), "versies": uit.get("versies"),
                        "kosten": round(uit.get("kosten", 0.0), 5), "seconden": round(time.perf_counter() - begin, 1)}],
                 toevoegen=True)
        print(f"{basis['id']} {p['reposts']} {uit.get('uitkomst')} {uit.get('kleur')}", flush=True)
    print(f"{len(_jsonl(pad))} gecontroleerd; uitgegeven ${_uitgegeven():.2f}")


def _labels() -> dict[str, str]:  # pragma: no cover - een bestand
    pad = WORTEL / "docs" / "steekproeven" / "32.69-radar.json"
    labels = json.loads(pad.read_text(encoding="utf-8")).get("labels", {}) if pad.exists() else {}
    fout = {k: v for k, v in labels.items() if v not in LABELS}
    if fout:
        raise Weigering(f"onbekende labels: {fout}")
    return labels


def _lezen() -> None:  # pragma: no cover - netwerk en bestanden
    """Elke gecontroleerde post zonder label naast het antwoord; de tekst opnieuw opgehaald, alleen op het scherm."""
    labels = _labels()
    rijen = [r for r in _jsonl(MAP / "controle.jsonl") if "fout" not in r and r["id"] not in labels]
    views = _views([r["uri"] for r in rijen]) if rijen else {}
    for r in rijen:
        did, rkey = r["uri"].split("/")[2], r["uri"].split("/")[-1]
        print(f"\n{r['id']} {r['reposts']} {r['langs']} {r['soort']} https://bsky.app/profile/{did}/post/{rkey}")
        print("  post:", tekst_van(views.get(r["uri"], {}))[:600])
        print(f"  Factiz: {r['uitkomst']} {r['kleur']} ({r['route']}), foto: {(r.get('foto') or {}).get('gevonden')}")
        print("  uitleg:", (r.get("uitleg") or "")[:900])
        for b in r["bronnen"][:5]:
            print(f"   - {b.get('rol')} {b.get('band')} {b.get('site') or b.get('redactie')} {b.get('url')}")
    print(f"\n{len(rijen)} zonder label")


def _opruimen() -> None:  # pragma: no cover - bestanden
    for naam in ("posts.jsonl", "vergelijking.jsonl"):
        (MAP / naam).unlink(missing_ok=True)
    for naam in ("soort.jsonl", "controle.jsonl"):   # de uitslag blijft, het adres met het account gaat weg
        rijen = _jsonl(MAP / naam)
        if rijen:
            _schrijf(MAP / naam, [{k: v for k, v in r.items() if k not in ("uri", "did")} for r in rijen])
    print("de adressen van de posts zijn weg; de nieuwsindex, de soorten, de antwoorden en de tellingen blijven")


def main() -> None:  # pragma: no cover - CLI
    import argparse

    parser = argparse.ArgumentParser(description="V3 van de radar: Bluesky tegen de nieuwsfoto's (PLAN #32.69)")
    parser.add_argument("stap", choices=("luisteren", "nieuws", "vergelijken", "soort", "controleren", "lezen",
                                         "tellen", "opruimen"))
    parser.add_argument("--uren", type=float, default=1.0)
    parser.add_argument("--top", type=int, default=None)
    parser.add_argument("--proef", type=int, default=None)
    args = parser.parse_args()
    {"luisteren": lambda: _luisteren(args.uren), "nieuws": _nieuws,
     "vergelijken": lambda: _vergelijken(args.top or TOP), "soort": lambda: _soort(args.top or SOORT_TOP),
     "controleren": lambda: _controleren(args.top or CONTROLE_TOP, args.proef), "lezen": _lezen,
     "tellen": _tellen, "opruimen": _opruimen}[args.stap]()


if __name__ == "__main__":
    main()
