"""De eigen checks van Factiz Radar in de andere talen van de site (PLAN #37.8, B85; PO 2026-11-19: "Ja, alle veertien
talen"): een machinevertaling van elke gepubliceerde check, met het label *Machinevertaling uit het Nederlands* en het
origineel erbij.

    python -m doublecheck.eigenvertaling plan                      # wat nog vertaald moet worden, en de schatting
    python -m doublecheck.eigenvertaling indienen [--proef N]      # Sonnet via de Batch API, binnen `GRENS`
    python -m doublecheck.eigenvertaling ophalen [--wacht M]       # de antwoorden nakijken en wegschrijven
    python -m doublecheck.eigenvertaling nagelezen --sleutel a,b [--taal en]   # de redactie las deze vertalingen

Per check en taal één bestand `content/redactie/<sleutel>/vertalingen/<taal>.json`: de vertaalde velden, de maker en de
vingerafdruk van de tekst die vertaald werd. Verandert de check, dan geldt de vertaling niet meer (`geldig`) en vraagt
`plan` haar opnieuw. Een antwoord gaat alleen het bestand in als het dezelfde velden heeft, even lange lijsten, in elke zin
dezelfde bronnummers, geen lang streepje en elke tekst echt vertaald (`lees_antwoord`, `onvertaald`). De checks zijn openbaar (B54: de Batch API voor offline werk
op openbare data); de bewering is het citaat van een openbare post.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

from doublecheck.redactie import LEZER_TALEN as _LEZER, MAP, lees_alle

VERSIE = "eigenvertaling-v2"    # v2 (2026-11-23): de bewering nooit in de brontaal laten, nooit het origineel ernaast
MODEL = "sonnet"            # de vertaling staat zo op de site; Haiku maakte bij de beweringen meer fouten (#34.2x)
GRENS = 5.00                # dollar per week (maandag tot zondag), PO 2026-11-20: "een budget van 5"; wat niet past,
                            # schuift naar de week erna; tot 2026-11-20 was het $12 voor alle rondes samen ($10,73 op)
# de schatting hieronder is te laag: 42 vertalingen kostten $1,23 tegen $0,74 geschat, 11 kostten $0,26 tegen $0,17
KALIBRATIE = 1.7
BATCHES = Path(__file__).resolve().parent.parent / "data" / "eigenvertaling" / "batches.jsonl"
# de doeltalen bij naam, voor het model (de talen van de site, `factiz_site/teksten/sitetalen.json`)
TALEN = {"en": "English", "nl": "Dutch", "de": "German", "es": "Spanish", "fr": "French", "pt": "Portuguese (Brazil)",
         "ru": "Russian", "uk": "Ukrainian", "tr": "Turkish", "ar": "Arabic", "fa": "Persian", "hi": "Hindi",
         "id": "Indonesian", "ja": "Japanese", "zh": "Chinese (Traditional)"}
TEKSTEN = ("kop", "oordeel_zin", "bewering", "kort", "tekst", "niet_weten", "bereik")
_NUMMER = re.compile(r"\[(\d+)\]")
ONVERTAALD_MIN = 20          # een tekst van minstens zoveel tekens moet anders zijn dan het origineel (`onvertaald`)

_SYSTEEM = """You translate a fact-check by the Factiz newsroom into another language, for readers in that language.

Rules:
- Translate faithfully and completely. Do not add, explain, soften, sharpen or leave out anything.
- Keep every source number such as [3] exactly as it is, attached to the same statement.
- Keep names, numbers, dates, amounts and quoted titles as they are; write dates and numbers the way the target language
  writes them.
- The field "bewering" is a quote of a post as it circulated: translate it literally into the target language, keeping
  its tone and punctuation. Never leave it in the source language, and never put the original next to the translation.
- Keep the meaning of the verdict words exactly (false, misleading, missing context, mostly true, true, unproven).
- No em dashes and no exclamation marks of your own.
- Answer with one JSON object only: the same keys as the input "velden", lists with the same number of items, nothing else.
"""


def bron(c: dict) -> dict:
    """De velden van een check die een lezer leest, in een vaste vorm: de teksten, wat nog uit te zoeken is, de tijdlijn,
    de bijschriften en alt-teksten van de beelden en de rekensom."""
    uit = {k: c[k] for k in TEKSTEN if c.get(k)}
    uit["nog_uitzoeken"] = list(c.get("nog_uitzoeken") or [])
    uit["tijdlijn"] = [t.get("wat", "") for t in c.get("tijdlijn") or []]
    uit["beeld_bijschrift"] = [b.get("bijschrift", "") for b in c.get("beeld") or []]
    uit["beeld_alt"] = [b.get("alt", "") for b in c.get("beeld") or []]
    if c.get("rekensom"):
        uit["rekensom"] = [[r.get("geval", ""), r.get("som", ""), r.get("uitkomst", "")] for r in c["rekensom"]]
    return uit


def vingerafdruk(c: dict) -> str:
    """Van de tekst die vertaald wordt: verandert er iets aan, dan geldt de vertaling niet meer."""
    return hashlib.sha256(json.dumps(bron(c), ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()[:16]


def veldafdrukken(c: dict) -> dict[str, str]:
    """Per veld een vingerafdruk: verandert één veld, dan hoeft alleen dat opnieuw vertaald (PO 2026-11-20, zuinig)."""
    return {k: hashlib.sha256(json.dumps(v, ensure_ascii=False).encode("utf-8")).hexdigest()[:16] for k, v in bron(c).items()}


def gewijzigd(c: dict, vertaling: dict) -> list[str] | None:
    """De velden van de check die niet meer passen bij de vertaling, of None als de vertaling dat niet bijhield (dan
    alles)."""
    oud = vertaling.get("veldafdrukken")
    if not isinstance(oud, dict):
        return None
    return sorted(k for k, a in veldafdrukken(c).items() if oud.get(k) != a)


def samenvoegen(c: dict, taal: str, oud: dict, nieuw: dict, maker: str) -> dict:
    """De vertaling die er lag met de opnieuw vertaalde velden erin, en zonder velden die de check niet meer heeft."""
    velden = {k: (nieuw[k] if k in nieuw else oud["velden"].get(k)) for k in bron(c)}
    return bestand(c, taal, velden, maker)


def delen(checks: list[dict], te_doen: list[tuple[str, str]], map_: Path = MAP) -> dict[tuple[str, str], list[str]]:
    """Per vraag de velden die alleen nog vertaald moeten, als er een vertaling ligt die per veld is bijgehouden."""
    per = {c["sleutel"]: c for c in checks}
    uit = {}
    for s, t in te_doen:
        p = pad(s, t, map_)
        if s in per and p.exists():
            v = json.loads(p.read_text(encoding="utf-8"))
            velden = gewijzigd(per[s], v)
            if velden is None:
                continue
            # en wat niet vertaald was (`onvertaald`): alleen dat veld opnieuw, niet de hele check
            velden = sorted(set(velden) | set(onvertaald(bron(per[s]), v.get("velden") or {})))
            if velden and len(velden) < len(bron(per[s])):
                uit[(s, t)] = velden
    return uit


def vastleggen(checks: list[dict], map_: Path = MAP) -> int:
    """Geeft elke geldige vertaling die ze nog niet had haar vingerafdrukken per veld, zodat een latere wijziging alleen
    dat veld opnieuw vraagt. Raakt geen vertaling aan die niet meer bij haar check past."""
    n = 0
    for c in checks:
        for p in sorted((map_ / c["sleutel"] / "vertalingen").glob("*.json")):
            v = json.loads(p.read_text(encoding="utf-8"))
            if "veldafdrukken" not in v and geldig(c, v):
                schrijf(p, {**{k: x for k, x in v.items() if k != "velden"}, "veldafdrukken": veldafdrukken(c),
                            "velden": v["velden"]})
                n += 1
    return n


def doeltalen(c: dict) -> list[str]:
    """Elke taal van de site behalve die van de check zelf."""
    return [t for t in TALEN if t != c["taal"]]


def verzoek(c: dict, taal: str, velden: list[str] | None = None) -> dict:
    from doublecheck.modellen import MODELLEN

    alle = bron(c)
    vraag = {"doeltaal": TALEN[taal], "brontaal": TALEN[c["taal"]],
             "velden": {k: alle[k] for k in velden} if velden else alle}
    return {"model": MODELLEN[MODEL]["id"], "max_tokens": 16000, "system": _SYSTEEM,
            "messages": [{"role": "user", "content": json.dumps(vraag, ensure_ascii=False)}]}


def _strings(x) -> list[str]:
    if isinstance(x, str):
        return [x]
    if isinstance(x, list):
        return [s for y in x for s in _strings(y)]
    return []


def onvertaald(bron_: dict, velden: dict) -> list[str]:
    """De tekstvelden die niet vertaald zijn: gelijk aan het origineel, of met het hele origineel erin en meer erbij. Sonnet
    liet zo 41 beweringen van 22 checks in de brontaal, en zette één keer het origineel voor de Japanse vertaling
    (2026-11-23). Alleen een tekst van minstens `ONVERTAALD_MIN` tekens met een letter: een naam mag gelijk blijven."""
    uit = []
    for k, o in bron_.items():
        w = velden.get(k)
        if isinstance(o, str) and isinstance(w, str):
            o_ = o.strip()
            if len(o_) >= ONVERTAALD_MIN and any(t.isalpha() for t in o_) and o_ in w:
                uit.append(k)
    return sorted(uit)


def lees_antwoord(tekst: str | None, velden: dict) -> dict | None:
    """Het antwoord als de vertaling van `velden`, of None: dezelfde sleutels, lijsten even lang, in elke tekst dezelfde
    bronnummers als in het origineel (elk dat er stond, geen nieuw; een nummer twee keer mag, als de zin anders loopt), geen
    lang streepje, en elke tekst echt vertaald (`onvertaald`)."""
    if not tekst:
        return None
    t = tekst.strip()
    if t.startswith("```"):
        t = t.strip("`").removeprefix("json").strip()
    try:
        uit = json.loads(t)
    except ValueError:
        return None
    # soms komt de vraag terug met de vertaling onder "velden"; dan telt wat daaronder staat
    if isinstance(uit, dict) and isinstance(uit.get("velden"), dict) and set(uit) - {"velden", "doeltaal", "brontaal"} == set():
        uit = uit["velden"]
    if not isinstance(uit, dict) or set(uit) != set(velden):
        return None
    for k, v in velden.items():
        w = uit[k]
        if isinstance(v, str):
            if not isinstance(w, str) or not w.strip() or set(_NUMMER.findall(w)) != set(_NUMMER.findall(v)):
                return None
        elif isinstance(v, list):
            if not isinstance(w, list) or len(w) != len(v):
                return None
            for a, b in zip(v, w):
                if isinstance(a, list):
                    if not isinstance(b, list) or len(b) != len(a) or not all(isinstance(x, str) for x in b):
                        return None
                elif not isinstance(b, str) or set(_NUMMER.findall(b)) != set(_NUMMER.findall(a)):
                    return None
    if any("\u2014" in s for s in _strings(list(uit.values()))) or onvertaald(velden, uit):
        return None
    return uit


def pad(sleutel: str, taal: str, map_: Path = MAP) -> Path:
    return Path(map_) / sleutel / "vertalingen" / f"{taal}.json"


def bestand(c: dict, taal: str, velden: dict, maker: str) -> dict:
    """Het vertaalbestand van een check, met voorop waar het vandaan komt (`_meta`, zoals elk databestand dat de site
    verspreidt, tests/test_licenties.py)."""
    return {"_meta": (f"Machinevertaling ({c['taal']} naar {taal}) van de eigen factcheck {c['sleutel']} van Factiz, eigen werk "
                      f"van de redactie (B82, B84), door {maker}; doublecheck/eigenvertaling.py, PLAN #37.8."),
            "taal": taal, "brontaal": c["taal"], "vingerafdruk": vingerafdruk(c), "veldafdrukken": veldafdrukken(c),
            "maker": maker, "velden": velden}


def schrijf(p: Path, v: dict) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(v, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def geldig(c: dict, vertaling: dict | None) -> bool:
    """Een vertaling geldt zolang de tekst die vertaald werd niet veranderde, en als elke tekst echt vertaald is
    (`onvertaald`); anders komt ze in geen uitgave en vraagt `plan` het veld opnieuw."""
    return (bool(vertaling) and vertaling.get("vingerafdruk") == vingerafdruk(c) and isinstance(vertaling.get("velden"), dict)
            and not onvertaald(bron(c), vertaling["velden"]))


def tekstafdruk(velden: dict) -> str:
    """Van de vertaalde tekst zelf: wat de redactie las (PLAN #37.11)."""
    return hashlib.sha256(json.dumps(velden, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()[:16]


def is_nagelezen(taal: str, vertaling: dict) -> bool:
    """De redactie las deze vertaling (PLAN #37.11, SPECS E10.S4 AC7): in een taal die zij leest, en de tekst is sinds het
    lezen niet veranderd."""
    merk = vertaling.get("nagelezen")
    return (taal in LEZER_TALEN and isinstance(merk, dict) and isinstance(vertaling.get("velden"), dict)
            and merk.get("afdruk") == tekstafdruk(vertaling["velden"]))


def geldige(c: dict, map_: Path = MAP) -> dict[str, dict]:
    """De geldige vertalingen van een check per taal, als `{taal: {"velden": ..., "maker": ..., "nagelezen": ...}}`."""
    uit = {}
    for taal in doeltalen(c):
        p = pad(c["sleutel"], taal, map_)
        if p.exists():
            v = json.loads(p.read_text(encoding="utf-8"))
            if geldig(c, v):
                uit[taal] = {"velden": v["velden"], "maker": v["maker"], "nagelezen": is_nagelezen(taal, v)}
    return uit


def nagelezen(c: dict, taal: str, door: str, datum: str, map_: Path = MAP) -> None:
    """Legt vast dat de redactie de vertaling van een check in `taal` las (PLAN #37.11, PO 2026-11-21: "ja dat ook graag"),
    met de vingerafdruk van de tekst: wordt de vertaling daarna opnieuw gemaakt, dan telt het lezen niet meer. Alleen een
    geldige vertaling in een taal die de redactie leest."""
    if taal not in LEZER_TALEN:
        raise ValueError(f"{taal}: die taal leest de redactie niet ({', '.join(LEZER_TALEN)})")
    p = pad(c["sleutel"], taal, map_)
    v = json.loads(p.read_text(encoding="utf-8")) if p.exists() else None
    if not geldig(c, v):
        raise ValueError(f"{c['sleutel']}: geen geldige vertaling in het {taal}; eerst vertalen")
    merk = {"door": door, "datum": datum, "afdruk": tekstafdruk(v["velden"])}
    schrijf(p, {**{k: x for k, x in v.items() if k not in ("nagelezen", "velden")}, "nagelezen": merk, "velden": v["velden"]})


# de talen waarin de redactie zelf leest; een check in een andere taal leest zij na in het Engels (B85, punt 5)
LEZER_TALEN = _LEZER


def nog_te_doen(checks: list[dict], map_: Path = MAP) -> list[tuple[str, str]]:
    """Per check de talen zonder geldige vertaling, als (sleutel, taal): bij een gepubliceerde check elke andere taal van
    de site, bij een concept in een taal die de redactie niet leest alleen het Engels, om na te lezen."""
    uit = []
    for c in checks:
        if c.get("status") == "gepubliceerd":
            # een lokale check alleen naar het Engels, waar de redactie haar leest (PO 2026-11-20, "Yes, set it up")
            talen = ([] if c["taal"] == "en" else ["en"]) if c.get("reikwijdte") == "lokaal" else doeltalen(c)
        elif c.get("taal") not in LEZER_TALEN:
            talen = ["en"]
        else:
            continue
        klaar = geldige(c, map_)
        uit += [(c["sleutel"], t) for t in talen if t not in klaar]
    return uit


def schatting(checks: list[dict], te_doen: list[tuple[str, str]], deel: dict | None = None) -> float:
    """Wat de vragen ongeveer kosten: ~1,3 token per 4 tekens in, de vertaling ~1,2 keer zo lang uit; bij een vraag die
    alleen enkele velden vraagt (`deel`), alleen die."""
    from doublecheck.modellen import MODELLEN

    bronnen = {c["sleutel"]: bron(c) for c in checks}
    def lengte(s, t):
        b = bronnen[s]
        velden = (deel or {}).get((s, t))
        return len(json.dumps({k: b[k] for k in velden} if velden else b, ensure_ascii=False))
    tok_in = sum(lengte(s, t) / 3 + 600 for s, t in te_doen)
    tok_uit = sum(lengte(s, t) / 2.5 for s, t in te_doen)
    return KALIBRATIE * (tok_in * MODELLEN[MODEL]["in"] + tok_uit * MODELLEN[MODEL]["uit"]) / 1e6


def _jsonl(p: Path) -> list[dict]:
    return [json.loads(r) for r in p.read_text(encoding="utf-8").splitlines() if r.strip()] if p.exists() else []


def weekbedrag(batches: list[dict], dag: str) -> float:
    """Wat de batches in de week van `dag` kostten (de schatting zolang een batch open is); een batch van vóór de grens per
    week draagt geen dag en telt niet mee."""
    from datetime import date

    week = date.fromisoformat(dag).isocalendar()[:2]
    return sum(b.get("werkelijk") if b.get("werkelijk") is not None else b.get("schatting", 0)
               for b in batches if b.get("dag") and date.fromisoformat(b["dag"]).isocalendar()[:2] == week)


def binnen_grens(checks: list[dict], te_doen: list[tuple[str, str]], ruimte: float,
                 deel: dict | None = None) -> list[tuple[str, str]]:
    """Wat er deze week nog in past: eerst het Engels van een concept (om na te lezen), dan het Engels van de rest, dan de
    andere talen; wat niet past, wacht op de week erna."""
    status = {c["sleutel"]: c.get("status") for c in checks}
    volgorde = sorted(te_doen, key=lambda x: (status.get(x[0]) != "concept", x[1] != "en"))
    gekozen: list[tuple[str, str]] = []
    for vraag in volgorde:
        if schatting(checks, gekozen + [vraag], deel) <= ruimte:
            gekozen.append(vraag)
    return gekozen


def _uitgegeven() -> float:
    from datetime import date

    return weekbedrag(_jsonl(BATCHES), date.today().isoformat())


def _indienen(proef: int | None) -> None:  # pragma: no cover - de Batch API
    import anthropic

    from doublecheck.varianten import laad_sleutel

    from datetime import date

    checks = {c["sleutel"]: c for c in lees_alle()}
    open_ = {(s, t) for b in _jsonl(BATCHES) if b.get("werkelijk") is None for s, t in b["vragen"]}
    te_doen = [x for x in nog_te_doen(list(checks.values())) if x not in open_]
    if proef:
        te_doen = te_doen[:proef]
    if not te_doen:
        print("niets te vertalen")
        return
    alles = len(te_doen)
    deel = delen(list(checks.values()), te_doen)
    te_doen = binnen_grens(list(checks.values()), te_doen, GRENS - _uitgegeven(), deel)
    if not te_doen:
        raise SystemExit(f"de grens van deze week is bereikt: ${_uitgegeven():.2f} van ${GRENS:.2f}; {alles} wachten")
    if len(te_doen) < alles:
        print(f"{alles - len(te_doen)} vertalingen wachten op volgende week (grens ${GRENS:.2f} per week)")
    kost = schatting(list(checks.values()), te_doen, deel)
    laad_sleutel()
    client = anthropic.Anthropic(max_retries=6)
    batch = client.messages.batches.create(requests=[
        {"custom_id": f"{s}__{t}", "params": verzoek(checks[s], t, deel.get((s, t)))} for s, t in te_doen])
    BATCHES.parent.mkdir(parents=True, exist_ok=True)
    with BATCHES.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"id": batch.id, "vragen": te_doen, "schatting": round(kost, 4), "versie": VERSIE,
                            "dag": date.today().isoformat(), "werkelijk": None,
                            "delen": {f"{s}__{t}": v for (s, t), v in deel.items() if (s, t) in te_doen}}) + "\n")
    print(f"batch {batch.id}: {len(te_doen)} vertalingen, schatting ${kost:.2f}")


def _ophalen(wacht: int) -> None:  # pragma: no cover - de Batch API
    import time

    import anthropic

    from doublecheck import berichtcontrole as bc
    from doublecheck.modellen import MODELLEN
    from doublecheck.modelpoort import kosten_batch
    from doublecheck.varianten import laad_sleutel

    checks = {c["sleutel"]: c for c in lees_alle()}
    laad_sleutel()
    client = anthropic.Anthropic()
    einde = time.time() + 60 * wacht
    while True:
        batches = _jsonl(BATCHES)
        open_ = 0
        for b in batches:
            if b.get("werkelijk") is not None:
                continue
            if client.messages.batches.retrieve(b["id"]).processing_status != "ended":
                open_ += 1
                continue
            werkelijk, goed, fout = 0.0, 0, []
            for r in client.messages.batches.results(b["id"]):
                sleutel, taal = r.custom_id.split("__")
                c = checks.get(sleutel)
                if c is None or r.result.type != "succeeded":
                    fout.append(r.custom_id)
                    continue
                msg = r.result.message
                werkelijk += kosten_batch(bc.gebruik_uit(msg), MODEL)
                tekst = None if msg.stop_reason == "max_tokens" else "".join(getattr(x, "text", "") or "" for x in msg.content)
                gevraagd = (b.get("delen") or {}).get(r.custom_id)
                alle = bron(c)
                velden = lees_antwoord(tekst, {k: alle[k] for k in gevraagd} if gevraagd else alle)
                if velden is None:
                    fout.append(r.custom_id)
                    continue
                p = pad(sleutel, taal)
                maker = f"{MODELLEN[MODEL]['id']}, {b.get('versie', VERSIE)}"
                if gevraagd and p.exists():
                    schrijf(p, samenvoegen(c, taal, json.loads(p.read_text(encoding="utf-8")), velden, maker))
                else:
                    schrijf(p, bestand(c, taal, velden, maker))
                goed += 1
            b["werkelijk"] = round(werkelijk, 4)
            b["fout"] = fout
            BATCHES.write_text("".join(json.dumps(x) + "\n" for x in batches), encoding="utf-8")
            print(f"batch {b['id']}: {goed} goed, {len(fout)} niet bruikbaar {fout[:5]}, ${werkelijk:.2f}")
        if not open_ or time.time() > einde:
            print(f"{open_} batches nog open; deze week ${_uitgegeven():.2f} van ${GRENS:.2f}")
            return
        time.sleep(30)


def main() -> None:  # pragma: no cover - CLI
    p = argparse.ArgumentParser(description="De eigen checks vertaald (PLAN #37.8)")
    p.add_argument("stap", choices=["plan", "indienen", "ophalen", "vastleggen", "nagelezen"])
    p.add_argument("--proef", type=int)
    p.add_argument("--sleutel", help="nagelezen: de checks, met komma's")
    p.add_argument("--taal", default="en", help="nagelezen: de taal van de vertaling")
    p.add_argument("--door", default="De redactie van Factiz", help="nagelezen: wie las")
    p.add_argument("--wacht", type=int, default=0, help="ophalen: zoveel minuten wachten op open batches")
    a = p.parse_args()
    if a.stap == "plan":
        checks = lees_alle()
        te_doen = nog_te_doen(checks)
        print(f"{len(te_doen)} vertalingen te doen, schatting ${schatting(checks, te_doen, delen(checks, te_doen)):.2f}; "
              f"deze week uitgegeven ${_uitgegeven():.2f} van ${GRENS:.2f}")
    elif a.stap == "vastleggen":
        print(f"{vastleggen(lees_alle())} vertalingen per veld vastgelegd")
    elif a.stap == "nagelezen":
        from datetime import date

        per = {c["sleutel"]: c for c in lees_alle()}
        sleutels = [s for s in (a.sleutel or "").split(",") if s]
        if not sleutels or any(s not in per for s in sleutels):
            raise SystemExit(f"onbekende of geen sleutel: {[s for s in sleutels if s not in per] or '--sleutel ontbreekt'}")
        for s in sleutels:
            nagelezen(per[s], a.taal, a.door, date.today().isoformat())
            print(f"{s}: de vertaling in het {a.taal} is nagelezen door {a.door}")
    elif a.stap == "indienen":
        _indienen(a.proef)
    else:
        _ophalen(a.wacht)


if __name__ == "__main__":  # pragma: no cover
    main()
