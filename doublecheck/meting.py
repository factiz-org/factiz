"""Eén vaste meetopzet voor de controle (PLAN #32.41, PO 2026-11-05: "deze kun je allebei ook doorvoeren").

Een ronde is een meetplan in `docs/meetplannen/<taak>.json`, geen nieuwe module:
- *de sets:* per set de bron, het aantal (een vaste steekproef), en of het als op de eerste dag is (geen kring 1, geen
  checks uit de database, geen factchecksites in de resultaten, `speuren.van_factchecker`) of zoals het product (kring
  1 en de database), met of zonder het beeld (zwartgemaakt, B55);
- *de armen:* per arm de lezer en de schakelaars van `[berichtcontrole]`;
- *wat gelabeld wordt:* elk rood en oranje, elk groen bij onwaar nieuws (`onwaar`), elke *niet bevestigd* bij waar
  nieuws (`waar`). Een alarm dat de eigen check van het bericht als bron noemt, bewijst zichzelf;
- *de eisen:* tellingen met een grens.

Elke arm draait door dezelfde functies als `/check` (`zoekcontrole`, `speurvraag`). De vragen aan de modellen gaan via
de Batch API (openbare data); de zoekresultaten blijven in het geheugen, bewaard worden alleen de adressen.

Bij #32.54 kan een plan antwoorden van dezelfde arm uit een eerdere meting overnemen (`overnemen`), en draait de regel
van de foto bij de bron (`fotobron`) ná de lezer op de bewaarde antwoorden (`foto`): zo tellen met en zonder de regel op
dezelfde lezing.

Met `--direct` (PO 2026-11-08: "doe maar direct dan, hoe sneller hoe beter") gaan dezelfde vragen los en tegelijk naar
het model in plaats van via de Batch API: minuten in plaats van uren, tegen de prijs zonder batchkorting.

    python -m doublecheck.meting <meetplan> set|draaien [--proef N] [--direct]|foto|wachttijd|lezen|tellen
"""

from __future__ import annotations

import collections
import hashlib
import json
import random
import threading
import time
from pathlib import Path

from doublecheck import zoekcontrole as zc

WORTEL = Path(__file__).resolve().parent.parent
STUK = 50
SCHATTING = 0.027  # per bericht en arm: Haiku, vier zoekvragen en één lezing van Sonnet in de batch
ALARM = ("rood", "oranje")
LABELWAARDEN = ("bewijst", "bewijst niet", "vals", "terecht", "set fout")
OPS = {">=": lambda a, b: a >= b, "<=": lambda a, b: a <= b}
MIN_TUSSEN = 0.25  # seconden tussen twee zoekvragen, over alle draden samen


class Weigering(Exception):
    """Het plan klopt niet, het budget is op, of iets dat telt heeft geen label."""


# --- het plan en de set ------------------------------------------------------------------------------------------

def controleer_plan(plan: dict) -> None:
    """Het plan noemt alleen lezers die bestaan, een model voor de zoekvragen vooraf waar de lezer dat vraagt, en eisen
    op armen en sets die in het plan staan."""
    for naam, arm in plan["armen"].items():
        lezer = zc.LEZERS.get(arm.get("lezer"))
        if lezer is None:
            raise Weigering(f"arm {naam}: lezer {arm.get('lezer')!r} bestaat niet in de code")
        if lezer.get("vooraf") and not arm.get("speurvraag_model"):
            raise Weigering(f"arm {naam}: {arm['lezer']} vraagt een `speurvraag_model`")
    for eis in plan.get("eisen", []):
        for t in (eis["tel"] if isinstance(eis["tel"], list) else [eis["tel"]]) + ([eis["van"]] if "van" in eis else []):
            if t["arm"] not in plan["armen"] or not set(t["sets"]) <= set(plan["sets"]):
                raise Weigering(f"eis {eis['naam']!r} noemt een arm of set die niet in het plan staat")
        if eis["op"] not in OPS:
            raise Weigering(f"eis {eis['naam']!r}: onbekende vergelijking {eis['op']!r}")
        if ("van" in eis) != ("aandeel" in eis) or ("van" in eis) == ("waarde" in eis):
            raise Weigering(f"eis {eis['naam']!r}: een grens is een getal (`waarde`) of een aandeel van een telling "
                            "(`aandeel` en `van`)")
    if "zoekvragen_max" in plan and not (isinstance(plan["zoekvragen_max"], int) and plan["zoekvragen_max"] > 0):
        raise Weigering("zoekvragen_max is een positief getal: de grens van de meting bij de zoekdienst")


def zoekvragen_geschat(aantallen: dict[str, int], gewoon: set[str] = frozenset()) -> int:
    """Hoeveel zoekvragen een meting met zoekvragen vooraf hoogstens nodig heeft: per bericht het bericht zelf en drie
    eigen zoekvragen; een gewone tekst zoekt meestal alleen zichzelf."""
    return sum(n * (1 if naam in gewoon else 1 + zc.MAX_SPEURVRAGEN) for naam, n in aantallen.items())


def kies_set(plan: dict, bronnen: dict[str, list[dict]]) -> list[dict]:
    """De berichten van het plan: per set alles, of een vaste steekproef van `n`; de volgorde van de bron telt niet."""
    uit = []
    for naam, s in plan["sets"].items():
        rijen = sorted((r for r in bronnen[s["bron"]] if r["set"] == s["set"]), key=lambda r: r["id"])
        if s.get("n"):
            rijen = sorted(random.Random(plan.get("zaad", 0)).sample(rijen, min(s["n"], len(rijen))),
                           key=lambda r: r["id"])
        for r in rijen:
            item = {"id": r["id"], "set": naam, "tekst": r["tekst"], "datum": r.get("datum"),
                    "eerste_dag": bool(s.get("eerste_dag"))}
            if s.get("beeld") and r.get("beeld"):
                item["beeld"] = r["beeld"]
                if r.get("beeld_reserve"):
                    item["beeld_reserve"] = r["beeld_reserve"]
            if r.get("eigen_urls"):
                item["eigen_urls"] = r["eigen_urls"]
            uit.append(item)
    return uit


# --- labelen en tellen ---------------------------------------------------------------------------------------------

def moet_lezen(r: dict, plan: dict) -> bool:
    """Elk rood en oranje, elk groen bij onwaar nieuws en elke *niet bevestigd* bij waar nieuws; en elk groen dat de
    regel van de foto bij de bron wegnam (#32.54), bij onwaar en bij waar nieuws."""
    weg = (r.get("zonder_foto") or {}).get("kleur") == "groen" and r["kleur"] != "groen"
    return (r["kleur"] in ALARM or (r["kleur"] == "groen" and r["set"] in plan["onwaar"])
            or (r["uitkomst"] == "niet bevestigd" and r["set"] in plan["waar"])
            or (weg and (r["set"] in plan["onwaar"] or r["set"] in plan["waar"])))


def _adres(url: str | None) -> tuple[str, str]:
    """Een adres zonder "www." en zonder slash aan het eind: zo schrijft M4FC het, zo geeft de zoekdienst het (#32.46)."""
    from urllib.parse import urlsplit

    s = urlsplit(url or "")
    return (s.hostname or "").removeprefix("www."), s.path.rstrip("/")


def auto_label(r: dict, item: dict) -> str | None:
    """Een alarm dat de eigen check van het bericht als bron noemt, bewijst zichzelf (zoals §209)."""
    eigen = {_adres(u) for u in item.get("eigen_urls") or ()}
    return "bewijst" if r["kleur"] in ALARM and any(_adres(b.get("url")) in eigen for b in r["bronnen"]) else None


def _label(r: dict, labels: dict[str, str], items: dict[str, dict]) -> str | None:
    return labels.get(f"{r['id']}#{r['arm']}") or auto_label(r, items.get(r["id"], {}))


def _tel(rijen: list[dict], labels: dict[str, str], items: dict[str, dict], f: dict) -> int:
    """Telt de rijen die op het filter passen. `variant` (#32.54): `zonder_foto` telt de kleur en uitkomst zonder de
    regel van de foto bij de bron, `zonder_eigen` met de regel maar zonder de eigen check als vindplaats."""
    def v(r: dict) -> dict:
        return r.get(f["variant"]) or r if f.get("variant") else r

    return sum(1 for r in rijen if r["arm"] == f["arm"] and r["set"] in f["sets"]
               and ("kleuren" not in f or v(r)["kleur"] in f["kleuren"])
               and ("uitkomsten" not in f or v(r)["uitkomst"] in f["uitkomsten"])
               and ("labels" not in f or _label(r, labels, items) in f["labels"])
               and ("weg" not in f or bool(r.get("onbevestigd_weg")) == f["weg"]))


def telling(rijen: list[dict], labels: dict[str, str], plan: dict, items: dict[str, dict]) -> dict:
    """Per set en arm de kleuren, de uitkomsten en de labels, en de eisen van het plan. Weigert zolang iets dat telt
    geen label heeft."""
    open_ = sorted(f"{r['id']}#{r['arm']}" for r in rijen if moet_lezen(r, plan) and _label(r, labels, items) is None)
    if open_:
        raise Weigering(f"{len(open_)} zonder label, bijvoorbeeld {open_[0]}")
    per_set: dict = {}
    for r in rijen:
        d = per_set.setdefault(f"{r['set']} {r['arm']}", collections.Counter())
        d["n"] += 1
        d["kleur " + (r["kleur"] or "geen")] += 1
        d[r["uitkomst"]] += 1
        if r.get("onbevestigd_weg"):  # v10: wat v9 *niet bevestigd* had genoemd, en welke regel het wegnam
            d[f"niet bevestigd weg: {r['onbevestigd_weg']}"] += 1
        d["kosten"] += r["kosten"]
        if r.get("zonder_foto"):  # #32.54: wat de regel van de foto bij de bron deed
            d["zonder regel: kleur " + (r["zonder_foto"]["kleur"] or "geen")] += 1
            d["foto gevonden" if r["foto"].get("gevonden") else "foto niet gevonden"] += 1
            if not r["foto"].get("geopend"):
                d["foto: geen pagina open"] += 1
            if (r.get("zonder_eigen") or {}).get("kleur") != r["kleur"]:
                d["foto alleen bij de eigen check"] += 1
        if moet_lezen(r, plan):
            d[f"label {_label(r, labels, items)}"] += 1
    eisen = {}
    for eis in plan.get("eisen", []):
        waarde = sum(_tel(rijen, labels, items, t) for t in (eis["tel"] if isinstance(eis["tel"], list)
                                                              else [eis["tel"]]))
        if "van" in eis:  # #32.54: een aandeel van een andere telling op dezelfde antwoorden
            van = _tel(rijen, labels, items, eis["van"])
            eisen[eis["naam"]] = {"waarde": waarde, "van": van, "gehaald": OPS[eis["op"]](waarde, eis["aandeel"] * van)}
        else:
            eisen[eis["naam"]] = {"waarde": waarde, "gehaald": OPS[eis["op"]](waarde, eis["waarde"])}
    return {"per set": {k: dict(v) for k, v in sorted(per_set.items())}, "eisen": eisen}


# --- de foto bij de bron (#32.54) ----------------------------------------------------------------------------------

def overgenomen(rijen: list[dict], plan: dict, ids: set[str]) -> list[dict]:
    """De antwoorden van een eerdere meting die dit plan overneemt: dezelfde arm, de genoemde sets, de berichten van deze
    set. Een antwoord op een andere vraag dan de arm van dit plan nu stelt, weigert (DR6)."""
    o = plan["overnemen"]
    naar = o.get("naar", next(iter(plan["armen"])))
    verwacht = vingerafdruk(plan["armen"][naar])
    uit = []
    for r in rijen:
        if r["arm"] != o["arm"] or r["set"] not in o["sets"] or r["id"] not in ids:
            continue
        if r["vraag"] != verwacht:
            raise Weigering(f"{r['id']}: het antwoord rust op vraag {r['vraag']}, arm {naar} stelt {verwacht}")
        uit.append({**r, "arm": naar, "overgenomen": o["map"], "kosten": 0.0, "kosten_oud": r["kosten"]})
    return uit


def met_foto(rijen: list[dict], fotos: dict[tuple[str, str], dict]) -> list[dict]:
    """De regel van de foto bij de bron op de bewaarde antwoorden: per antwoord met een vondst de kleur en uitkomst met
    de regel, en daarnaast `zonder_foto` (de lezing zonder regel) en `zonder_eigen` (de regel zonder de eigen check als
    vindplaats)."""
    from doublecheck import fotobron as fb

    uit = []
    for r in rijen:
        f = fotos.get((r["id"], r["arm"]))
        if f is None:
            uit.append(r)
            continue
        nieuw = fb.toepassen(r, f["vondst"])
        zonder_eigen = fb.toepassen(r, f.get("zonder_eigen") or f["vondst"])
        uit.append({**nieuw, "zonder_foto": {"kleur": r["kleur"], "uitkomst": r["uitkomst"]},
                    "zonder_eigen": {"kleur": zonder_eigen["kleur"], "uitkomst": zonder_eigen["uitkomst"]}})
    return uit


def eigen_urls(item: dict) -> list[str]:  # pragma: no cover - leest M4FC voor de Engelse W
    """De eigen check van een bericht; bij de Engelse W (id `w-<rij>`) het artikel van die rij in M4FC."""
    if item.get("eigen_urls"):
        return item["eigen_urls"]
    if item["id"].startswith("w-") and item["id"][2:].isdigit():
        return [_m4fc()[int(item["id"][2:])]["article_url"]]
    return []


_M4FC: list = []


def _m4fc() -> list[dict]:  # pragma: no cover - een bestand
    if not _M4FC:
        _M4FC.extend(json.loads((WORTEL / "data" / "extern" / "m4fc" / "M4FC.json").read_text(encoding="utf-8")))
    return _M4FC


def vingerafdruk(arm: dict) -> str:
    """De vraag van de lezer, bij een lezer met zoekvragen vooraf ook die vraag, en bij v10 de regels na het lezen;
    verandert er iets, dan dit ook."""
    from doublecheck import speurvraag as sv

    d = zc.LEZERS[arm["lezer"]]
    inhoud = d["systeem"] + d["vraag"] + json.dumps(d["schema"], sort_keys=True)
    if d.get("vooraf"):
        inhoud += sv.SYSTEEM + sv.VRAAG + json.dumps(sv.SCHEMA, sort_keys=True) + arm["speurvraag_model"]
    if d.get("uitzonderingen"):  # de regels na het lezen (v10): verandert een regel, dan dit ook
        inhoud += json.dumps([d["uitzonderingen"], zc.OUD_JAREN, zc.JAARTAL.pattern])
    if d.get("eigen_kop"):  # de regel voor koppen (v11), met de lijst van media
        inhoud += json.dumps([sorted(zc.MEDIA.items()), zc.MIN_KOPWOORDEN])
    if d.get("uitleg_database"):  # een uitleg bij een check uit de database (v12), met wanneer de lezer het eens is
        inhoud += json.dumps([sorted(zc.EENS_MET_CHECK.items()), d.get("max_tokens")])
    if d.get("regel") == "een":  # één goede bron genoeg voor groen (v14, B61)
        inhoud += "regel:een"
    if d.get("getallen"):  # v16: een getal alleen als de aangewezen bron of het bericht het noemt
        inhoud += "getallen:" + zc._GETAL.pattern
    if d.get("met_bronnen") or d.get("eigen_niet"):  # v15: de zinnen met hun bron, en B61 zonder het bericht zelf
        inhoud += json.dumps([zc._NUMMER.pattern, zc._ALLEEN_OORDEEL.pattern, zc._EINDE_ZIN.pattern, zc._NA_DE_PUNT.pattern,
                              bool(d.get("eigen_niet"))])
    if d.get("kop_klopt") or d.get("zonder_database"):  # B60 en de database uit de uitleg (v13)
        inhoud += json.dumps([bool(d.get("kop_klopt")), zc._ONZE_DATABASE.pattern if d.get("zonder_database") else None])
    if d.get("regels"):  # v17: het vaste deel in het systeembericht
        inhoud += d["regels"]
    if d.get("initialen"):  # v17: geen breuk na een initiaal
        inhoud += "initialen:" + zc._EINDE_ZIN_INIT.pattern
    if d.get("eerste_zin"):  # v18: de eerste zin past bij de uitkomst
        inhoud += json.dumps([zc._OORDEEL_VOORAAN.pattern, sorted(zc._ZONDER_KLEUR.items())])
    if arm.get("model_id"):  # een arm met een eigen lezer (#32.64)
        inhoud += "model:" + arm["model_id"]
    return hashlib.sha256(inhoud.encode("utf-8")).hexdigest()[:12]


def model_naam(model_id: str) -> str:
    """De naam in `modellen.MODELLEN` bij een model-id, voor de prijs van een arm (#32.64)."""
    from doublecheck.modellen import MODELLEN

    return next(naam for naam, m in MODELLEN.items() if m["id"] == model_id)


def zoekkosten(nieuw: list[bool]) -> float:
    """Wat de zoekvragen van één bericht kosten: alleen wat deze meting nog niet vroeg (#32.64, de armen delen)."""
    return zc.ZOEKPRIJS * sum(nieuw)


# --- de bestanden en het netwerk -------------------------------------------------------------------------------

def _jsonl(pad: Path) -> list[dict]:
    from doublecheck.sheffield import regels

    return regels(pad)


def _schrijf(pad: Path, rijen: list[dict]) -> None:
    pad.parent.mkdir(parents=True, exist_ok=True)
    with pad.open("a", encoding="utf-8") as f:
        for r in rijen:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def lees_plan(pad: str) -> dict:  # pragma: no cover - een bestand
    plan = json.loads(Path(pad).read_text(encoding="utf-8"))
    controleer_plan(plan)
    return {**plan, "_map": WORTEL / plan["map"], "_labels": WORTEL / plan["labels"]}


def _ronde(plan: dict) -> dict:
    return {"map": plan["_map"], "labels": plan["_labels"]}


def _set(plan: dict) -> None:  # pragma: no cover - op de bestanden
    if (plan["_map"] / "set.jsonl").exists():
        raise Weigering("de set ligt al vast")
    bronnen = {s["bron"]: _jsonl(WORTEL / s["bron"]) for s in plan["sets"].values()}
    items = kies_set(plan, bronnen)
    _schrijf(plan["_map"] / "set.jsonl", items)
    print(collections.Counter(r["set"] for r in items))
    if plan.get("overnemen"):  # #32.54: de antwoorden en hun labels uit een eerdere meting, zonder nieuwe vraag
        o = plan["overnemen"]
        rijen = overgenomen(_jsonl(WORTEL / o["map"] / "antwoorden.jsonl"), plan, {s["id"] for s in items})
        _schrijf(plan["_map"] / "antwoorden.jsonl", rijen)
        oud = json.loads((WORTEL / o["labels"]).read_text(encoding="utf-8")).get("labels", {})
        naar = o.get("naar", next(iter(plan["armen"])))
        labels = {f"{r['id']}#{naar}": {**oud[f"{r['id']}#{o['arm']}"], "uit": o["labels"]} for r in rijen
                  if f"{r['id']}#{o['arm']}" in oud}
        if plan["_labels"].exists():
            raise Weigering("het labelbestand bestaat al; de overgenomen labels niet over iets heen schrijven")
        plan["_labels"].write_text(json.dumps({"toelichting": plan.get("toelichting_labels", ""), "labels": labels},
                                              ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"{len(rijen)} antwoorden en {len(labels)} labels overgenomen uit {o['map']}")


def tegoed_op(fout: BaseException) -> bool:
    """De zoekdienst weigert omdat het tegoed op is (402): dan stopt de meting, want elke volgende lezing zou zonder
    zoekresultaten betalen (#32.41 en #32.42, twee keer gebeurd)."""
    import urllib.error

    return isinstance(fout, urllib.error.HTTPError) and fout.code == 402


class _Zoeker:  # pragma: no cover - netwerk
    """Brave voor de meting: hoogstens één zoekvraag per `MIN_TUSSEN` seconden over alle draden, één keer opnieuw bij
    een weigering, en als op de eerste dag zonder de pagina's van factcheckers."""

    def __init__(self, sleutel: str, domeinen: set[str], max_aantal: int | None = None):
        self.sleutel, self.domeinen, self.slot, self.laatst = sleutel, domeinen, threading.Lock(), 0.0
        self.aantal, self.leeg, self.max_aantal, self.gezien = 0, False, max_aantal, {}

    def nieuw(self, q: str) -> bool:
        """Of deze zoekvraag in deze meting nog niet gesteld is (dan kost hij geld)."""
        return q not in self.gezien

    def __call__(self, q: str, eerste_dag: bool) -> dict:
        from doublecheck.speuren import zonder

        if q in self.gezien:  # dezelfde zoekvraag in deze meting één keer; alleen in het geheugen
            antwoord = self.gezien[q]
            return zonder(antwoord, self.domeinen) if eerste_dag else antwoord
        for poging in range(2):
            with self.slot:
                if self.max_aantal is not None and self.aantal >= self.max_aantal:
                    self.leeg = True  # de grens van het meetplan: stoppen zoals bij een leeg tegoed
                    raise RuntimeError("de grens van zoekvragen_max is bereikt")
                wacht = self.laatst + MIN_TUSSEN - time.monotonic()
                if wacht > 0:
                    time.sleep(wacht)
                self.laatst = time.monotonic()
                self.aantal += 1
            try:
                antwoord = zc.brave(q, self.sleutel)
                self.gezien[q] = antwoord
                return zonder(antwoord, self.domeinen) if eerste_dag else antwoord
            except Exception as fout:  # noqa: BLE001 - de zoekdienst weigerde; één keer opnieuw, nooit bij een leeg tegoed
                if tegoed_op(fout):
                    self.leeg = True
                    raise
                if poging:
                    raise
                time.sleep(2)
        raise RuntimeError("onbereikbaar")


def _omgeving(plan: dict):  # pragma: no cover - live
    import os

    import anthropic

    from doublecheck import api
    from doublecheck import berichtcontrole as bc
    from doublecheck.config import load_config
    from doublecheck.embedding import fingerprint_texts
    from doublecheck.speuren import eerste_dag_domeinen
    from doublecheck.storage import connect
    from doublecheck.varianten import laad_sleutel

    laad_sleutel()
    config = load_config(None)
    sites = bc.herkomstlijst()["sites"]
    conn, tabel = connect(str(WORTEL / "doublecheck.db")), bc.ijktabel(config)

    def snel(tekst: str) -> dict | None:
        return bc.snel_antwoord(api.los_op(conn, config, tekst, None, None).model_dump(), tabel, tekst,
                                config.model_versions.text_embedding)

    def checks_voor(tekst: str) -> list[dict]:
        fp = fingerprint_texts([tekst[:600]], config.model_versions.text_embedding)[0]
        return zc.checks_uit(bc.geheugen_met(conn, config, tekst, fp, []))

    zoeker = _Zoeker(os.environ["BRAVE_API_KEY"], eerste_dag_domeinen(sites), plan.get("zoekvragen_max"))
    return config, anthropic.Anthropic(max_retries=6), zoeker, snel, checks_voor, sites


GEDULD = (5, 20, 60)  # seconden wachten na "te veel verzoeken" of "even niet" (429, 503), daarna opgeven


def met_geduld(vraag, slaap=time.sleep):
    """Doet `vraag()` (geeft een statuscode of een antwoord met `status_code`); bij 429 of 503 wachten en opnieuw,
    hoogstens drie keer. Het webarchief antwoordt zo als de meting snel na elkaar vraagt (#32.54)."""
    antwoord = vraag()
    for pauze in GEDULD:
        if getattr(antwoord, "status_code", antwoord) not in (429, 503):
            break
        slaap(pauze)
        antwoord = vraag()
    return antwoord


def beeld_bytes(bron: str) -> bytes:  # pragma: no cover - een bestand of het netwerk
    """Het beeld van een bericht: een bestand (de ijkset), of een adres (#32.45, nieuwsfoto's). Een adres wordt één keer
    opgehaald, met robots.txt, en blijft alleen in het geheugen; nooit naar schijf."""
    if not bron.startswith(("http://", "https://")):
        return Path(bron).read_bytes()
    import urllib.robotparser
    from urllib.parse import urlsplit

    import httpx

    from doublecheck.poproef import AGENT

    with httpx.Client(headers=AGENT, follow_redirects=True, timeout=30) as web:
        robots = urllib.robotparser.RobotFileParser()
        r = met_geduld(lambda: web.get(f"https://{urlsplit(bron).hostname}/robots.txt"))
        robots.parse(r.text.splitlines() if r.status_code == 200 else [])
        if not robots.can_fetch("FactizResearch", bron):
            raise Weigering(f"robots.txt staat het beeld niet toe: {urlsplit(bron).hostname}")
        antwoord = met_geduld(lambda: web.get(bron))
        antwoord.raise_for_status()
        return antwoord.content


def beeld_of_reserve(item: dict, halen=None) -> bytes | None:
    """Het beeld van een bericht, en als dat niet meer bereikbaar is de reserve (een kopie in de Wayback Machine);
    None als beide weg zijn."""
    halen = halen or beeld_bytes
    for bron in (item.get("beeld"), item.get("beeld_reserve")):
        if bron:
            try:
                return halen(bron)
            except Exception:  # noqa: BLE001 - een beeld dat niet opent, telt niet; de reserve of overslaan
                continue
    return None


def _arm_config(config, arm: dict, beeld: bool):
    import dataclasses

    velden = {k: v for k, v in arm.items() if k in {f.name for f in dataclasses.fields(config.berichtcontrole)}}
    return dataclasses.replace(config, berichtcontrole=dataclasses.replace(config.berichtcontrole, **velden,
                                                                           beeld=beeld))


def wat_de_lezer_zag(bronnen: list[dict], resultaten: list[dict], checks: list[dict] | None,
                     uitleg: str | None = None) -> dict[str, str]:
    """Per bron die het antwoord noemt wat de lezer ervan zag: de titel en het fragment (zoals `zoekcontrole._regels`,
    400 tekens), of bij een check uit de database de bewering. Ook elk resultaat en elke check die de uitleg met een
    nummer aanwijst ([n], [Dk]; §241). Voor de meting van de uitleg (#32.56); de rest niet."""
    from doublecheck.zoekcontrole import _NUMMER

    def _check(k: dict) -> str:
        return " ".join(str(k.get("tekst") or "").split())[:400]

    per_url = {r["url"]: f"{r.get('titel') or ''} — {(r.get('fragment') or '')[:400]}" for r in resultaten if r.get("url")}
    per_url.update({k["url"]: _check(k) for k in checks or [] if k.get("url")})
    uit = {b["url"]: per_url[b["url"]] for b in bronnen if b.get("url") in per_url}
    per_nr = {str(r.get("nr")): r for r in resultaten if r.get("url")}
    for n in _NUMMER.findall(uitleg or ""):
        if n.startswith("D") and checks and 1 <= int(n[1:]) <= len(checks) and checks[int(n[1:]) - 1].get("url"):
            uit.setdefault(checks[int(n[1:]) - 1]["url"], _check(checks[int(n[1:]) - 1]))
        elif n in per_nr:
            uit.setdefault(per_nr[n]["url"], per_url[per_nr[n]["url"]])
    return uit


def _rij(item: dict, arm_naam: str, uit: dict, kosten: float, groepen: list[dict], vraag: str,
         gezien: dict[str, str] | None = None, ruw: str | None = None) -> dict:
    bronnen = [{k: b.get(k) for k in ("url", "site", "titel", "band", "soort", "rol", "redactie", "oordeel")
                if b.get(k) is not None} for b in uit["bronnen"]]
    return {"id": item["id"], "set": item["set"], "arm": arm_naam, "route": uit.get("route", "zoeken"),
            "oordeel": uit["oordeel"], "kleur": uit["kleur"], "uitkomst": uit["uitkomst"], "vorm": uit.get("vorm"),
            "over_beeld": uit.get("over_beeld"), "uitleg": uit.get("uitleg"), "bronnen": bronnen,
            "speurstap": [{k: g.get(k) for k in ("soort", "vraag", "site", "gevonden", "fout")} for g in groepen],
            "onbevestigd_weg": uit.get("onbevestigd_weg"), "kosten": round(kosten, 5), "vraag": vraag,
            **({"gezien": gezien} if gezien is not None else {}),
            **({"uitleg_ruw": ruw} if ruw is not None else {}),
            **({"kleur_bewering": uit["kleur_bewering"]} if uit.get("kleur_bewering") else {})}


def prijsfactor(direct: bool) -> int:
    """De prijzen in `leraar.MODELLEN` zijn die van de Batch API; direct kost het dubbele."""
    return 2 if direct else 1


def vraag_alles(client, verzoeken: dict, verwerk, aangemeld, afgemeld, *, direct: bool, draden: int = 8) -> list[str]:
    """De vragen van een stuk: via de Batch API (`batch_met_grens`), of direct: elke vraag los, tegelijk. Geeft de ids
    zonder antwoord."""
    if not direct:
        from doublecheck import uitkomsten as uk

        return uk.batch_met_grens(client, verzoeken, verwerk, aangemeld=aangemeld, afgemeld=afgemeld)
    from concurrent.futures import ThreadPoolExecutor

    def een(item):
        c, p = item
        try:
            return c, client.messages.create(**p)
        except Exception as fout:  # noqa: BLE001 - een vraag zonder antwoord telt als gemist, zoals in de batch
            print(f"{c}: geen antwoord ({type(fout).__name__})", flush=True)
            return c, None

    with ThreadPoolExecutor(draden) as pool:
        klaar = {c: m for c, m in pool.map(een, verzoeken.items()) if m is not None}
    if klaar:
        verwerk(klaar)
    return [c for c in verzoeken if c not in klaar]


def _tekst(msg) -> str:
    return "".join(getattr(b, "text", "") or "" for b in msg.content)


def _draai(plan: dict, proef: int | None, direct: bool = False) -> None:  # pragma: no cover - live
    """Per stuk en per arm: kring 1 (niet op de eerste dag); de zoekvragen vooraf in een batch van Haiku terwijl het
    bericht zelf gezocht wordt; de zoekvragen tegelijk; één batch van de lezer; dan `na_lezen`, zoals `/check`.
    Hervatbaar per bericht en arm, binnen het budget."""
    import datetime
    from concurrent.futures import ThreadPoolExecutor

    from doublecheck import berichtcontrole as bc
    from doublecheck import opknippen
    from doublecheck import speurvraag as sv
    from doublecheck import uitkomsten as uk
    from doublecheck.modelpoort import kosten_batch as kosten_model

    ronde = _ronde(plan)
    config, client, zoeker, snel, checks_voor, sites = _omgeving(plan)
    uk._vereffen(ronde, client)
    antwoorden = plan["_map"] / "antwoorden.jsonl"
    gedaan = {(r["id"], r["arm"]) for r in _jsonl(antwoorden)}
    alle = _jsonl(plan["_map"] / "set.jsonl")
    volgorde = list(plan["sets"])
    vooraf_gedeeld: dict = {}  # #32.64: de zoekvragen van Haiku per bericht, gedeeld door de armen; alleen in het geheugen
    for arm_naam, arm in plan["armen"].items():
        vraag = vingerafdruk(arm)
        werk = sorted((s for s in alle if (s["id"], arm_naam) not in gedaan), key=lambda s: volgorde.index(s["set"]))
        if proef:
            werk = [s for naam in volgorde for s in [x for x in werk if x["set"] == naam][:proef]]
        nodig = zoekvragen_geschat(collections.Counter(s["set"] for s in werk), gewoon=set(plan.get("gewoon", ())))
        print(f"arm {arm_naam} ({arm['lezer']}, vraag {vraag}): {len(werk)} berichten, hoogstens ~{nodig} zoekvragen "
              f"(~${nodig * zc.ZOEKPRIJS:.2f} bij de zoekdienst; grens {plan.get('zoekvragen_max', 'geen')})", flush=True)
        vooraf = zc.LEZERS[arm["lezer"]].get("vooraf")
        for begin in range(0, len(werk), STUK):
            stuk = werk[begin:begin + STUK]
            if zoeker.leeg:
                print("het tegoed bij de zoekdienst is op: gestopt", flush=True)
                return
            if uk._uitgegeven(ronde) + SCHATTING * len(stuk) > plan["budget"]:
                print(f"gestopt vóór de grens: ${uk._uitgegeven(ronde):.2f}", flush=True)
                return
            rijen, voor = [], {}
            for i, s in enumerate(stuk):
                cfg = _arm_config(config, arm, beeld=bool(s.get("beeld")))
                eerst = None
                if not s["eerste_dag"] and cfg.berichtcontrole.kring1:
                    hit = snel(s["tekst"])
                    if hit is not None:
                        eerst = zc.uit_kring1(hit, s["tekst"], {})
                        if not zc.LEZERS[arm["lezer"]].get("uitleg_database"):
                            rijen.append(_rij(s, arm_naam, eerst, 0.0, [], vraag))
                            continue
                        # v12: de lezer leest toch, voor de uitleg; de kleur blijft van de check (`zc.met_uitleg`)
                beeld = None
                if s.get("beeld"):
                    ruw = beeld_of_reserve(s)
                    if ruw is None:  # het beeld en de reserve zijn weg: niet meten, en melden
                        print(f"beeld niet bereikbaar, overgeslagen: {s['id']}", flush=True)
                        continue
                    beeld = opknippen.zwart_beeld(ruw, config.ocr)[0]
                checks = [] if s["eerste_dag"] else checks_voor(s["tekst"])
                voor[f"m{begin + i:04d}"] = {"s": s, "cfg": cfg, "beeld": beeld, "checks": checks, "kring1": eerst}
            # de zoekvragen vooraf (Haiku) en ondertussen de zoekvraag van het bericht zelf
            plannen: dict = {}
            sleutel = {c: (v["s"]["id"], arm["speurvraag_model"], v["beeld"] is not None) for c, v in voor.items()}
            gedeeld = {c for c in voor if sleutel[c] in vooraf_gedeeld}
            for c in gedeeld:
                plannen[f"p{c}"] = vooraf_gedeeld[sleutel[c]]
            for c, v in voor.items():
                v["nieuw"] = [zoeker.nieuw(zc.zoekvraag(v["s"]["tekst"]))]
            with ThreadPoolExecutor(4) as pool:
                eerste = {c: pool.submit(zc._veilig, lambda q, d=v["s"]["eerste_dag"]: zoeker(q, d),
                                         zc.zoekvraag(v["s"]["tekst"])) for c, v in voor.items()}
                if vooraf and set(voor) - gedeeld:
                    vraag_alles(client, {f"p{c}": sv.verzoek(v["s"]["tekst"], v["s"].get("datum"),
                                                             arm["speurvraag_model"], v["beeld"])
                                         for c, v in voor.items() if c not in gedeeld}, plannen.update,
                                lambda b, ids: uk._meld_aan(ronde, b, 0.0), lambda b: uk._meld_af(ronde, b),
                                direct=direct)
                for c in set(voor) - gedeeld:
                    if f"p{c}" in plannen:
                        vooraf_gedeeld[sleutel[c]] = plannen[f"p{c}"]
                for c, v in voor.items():
                    antwoord = eerste[c].result()
                    v["res"] = zc.resultaten_uit(antwoord, sites) if antwoord is not None else []
            for c, v in voor.items():
                p = plannen.get(f"p{c}")
                v["kosten"] = (kosten_model(bc.gebruik_uit(p), "haiku") * prijsfactor(direct)
                               if p is not None and c not in gedeeld else 0.0)
                verder = sv.lees(_tekst(p)) if p is not None else []

                def zoek(q, d=v["s"]["eerste_dag"], n=v["nieuw"]):
                    n.append(zoeker.nieuw(q))
                    return zoeker(q, d)

                v["res"], v["groepen"] = zc.speur(verder, v["res"], zoek, sites)
                v["kosten"] += zoekkosten(v["nieuw"])
                v["verzoek"] = zc.leesverzoek(v["s"]["tekst"], v["res"], v["s"].get("datum"), v["cfg"], v["beeld"],
                                              v["checks"], v["groepen"] if vooraf else None)
            if zoeker.leeg:  # de zoekresultaten van dit stuk zijn onvolledig: niet laten lezen
                _schrijf(uk._boek(ronde)[1], [{"kosten": round(sum(v["kosten"] for v in voor.values())
                                                              - zc.ZOEKPRIJS * sum(g["fout"] for v in voor.values()
                                                                                    for g in v["groepen"]), 5),
                                                "reden": "het tegoed bij de zoekdienst raakte op; niet gelezen",
                                                "ids": [v["s"]["id"] for v in voor.values()]}])
                print("het tegoed of de grens bij de zoekdienst is op: dit stuk niet gelezen, gestopt", flush=True)
                return
            lezingen: dict = {}
            if voor:
                gemist = vraag_alles(client, {c: v["verzoek"] for c, v in voor.items()}, lezingen.update,
                                     lambda b, ids: uk._meld_aan(ronde, b, sum(voor[i]["kosten"] for i in ids)),
                                     lambda b: uk._meld_af(ronde, b), direct=direct)
                if gemist:
                    _schrijf(uk._boek(ronde)[1], [{"kosten": round(sum(voor[c]["kosten"] for c in gemist), 5),
                                                    "reden": "gezocht, maar geen lezing", "ids": gemist}])
                    for c in gemist:  # een antwoord uit de database blijft, met de zin van de redactie
                        if voor[c]["kring1"] is not None:
                            rijen.append(_rij(voor[c]["s"], arm_naam, zc.met_uitleg(voor[c]["kring1"], None), 0.0, [],
                                              vraag))
            for c, msg in lezingen.items():
                v = voor[c]
                antwoord = zc.lees_oordeel(_tekst(msg))
                uit = zc.na_lezen(antwoord, v["s"]["tekst"], v["res"], v["checks"], arm["lezer"],
                                  v["beeld"] is not None, gezocht=zc.zelf_gezocht(v["groepen"]),
                                  jaar=datetime.date.today().year)
                if v["kring1"] is not None:
                    uit = zc.met_uitleg(v["kring1"], uit)
                rijen.append(_rij(v["s"], arm_naam, uit,
                                  v["kosten"] + kosten_model(bc.gebruik_uit(msg), model_naam(
                                      v["cfg"].berichtcontrole.model_id)) * prijsfactor(direct),
                                  v["groepen"], vraag,
                                  wat_de_lezer_zag(uit["bronnen"], v["res"], v["checks"], uit.get("uitleg")),
                                  antwoord.get("uitleg") or ""))
            _schrijf(antwoorden, rijen)
            teller = collections.Counter((r["set"], r["uitkomst"]) for r in rijen)
            print(f"{len(rijen)} bewaard: {dict(teller)}; {zoeker.aantal} zoekvragen; samen "
                  f"${uk._uitgegeven(ronde):.2f} van ${plan['budget']:.2f}", flush=True)


def _wachttijd(plan: dict) -> None:  # pragma: no cover - live
    """De wachttijd door `zoekcontrole.controleer` zelf, zonder batch, met de eerste arm van het plan."""
    import sqlite3

    from doublecheck.snelantwoord import percentiel

    w = plan["wachttijd"]
    config, client, zoeker, snel, checks_voor, sites = _omgeving(plan)
    arm = plan["armen"][w["arm"]]
    berichten = [s for s in _jsonl(plan["_map"] / "set.jsonl") if s["set"] in w["sets"]]
    berichten = random.Random(plan.get("zaad", 0)).sample(berichten, min(w["n"], len(berichten)))
    tijden, totaal, kosten = [], 0.0, sqlite3.connect(":memory:")
    for s in berichten:
        cfg = _arm_config(config, arm, beeld=False)
        begin = time.perf_counter()
        uit = zc.controleer(kosten, s["tekst"], cfg, client, lambda q, d=s["eerste_dag"]: zoeker(q, d),
                            (lambda t: None) if s["eerste_dag"] else snel, sites, None, s.get("datum"),
                            zoek_checks=(lambda t: []) if s["eerste_dag"] else checks_voor)
        tijden.append(round(time.perf_counter() - begin, 2))
        totaal += uit["kosten"]
    _schrijf(plan["_map"] / "ontwikkel.jsonl", [{"kosten": round(totaal, 5), "reden": "wachttijd"}])
    uit = {"n": len(tijden), "p50": percentiel(tijden, .5), "p95": percentiel(tijden, .95), "tijden": tijden,
           "eis p50": w.get("eis_p50"), "kosten": round(totaal, 4)}
    (plan["_map"] / "wachttijd.json").write_text(json.dumps(uit, indent=1), encoding="utf-8")
    print(uit)


def fotobestand(versie: str, snel: bool = False) -> str:
    """Waar de fotostap haar vondsten schrijft: per versie een bestand, en de wachttijd apart."""
    if snel:
        return f"wachttijd-{versie}.jsonl"
    return "foto.jsonl" if versie == "fotobron-v1" else f"foto-{versie.removeprefix('fotobron-')}.jsonl"


def _fotos(plan: dict, versie: str = "fotobron-v1") -> dict[tuple[str, str], dict]:  # pragma: no cover - een bestand
    pad = plan["_map"] / fotobestand(versie)
    return {(r["id"], r["arm"]): r for r in _jsonl(pad)} if pad.exists() else {}


def _antwoorden(plan: dict, versie: str = "fotobron-v1") -> list[dict]:  # pragma: no cover - een bestand
    return met_foto(_jsonl(plan["_map"] / "antwoorden.jsonl"), _fotos(plan, versie))


def _foto(plan: dict, versie: str = "fotobron-v1", snel: bool = False, hoogstens: int | None = None) -> None:  # pragma: no cover - netwerk
    """De regel van de foto bij de bron (#32.54) op de bewaarde antwoorden: bij elk groen met een beeld de bevestigende
    goede pagina's, beleefd (robots.txt, één verzoek per host), en of de foto daar staat. Eerst zonder de eigen check
    van het bericht, dan pas met. In `foto.jsonl` alleen adressen en getallen; elk beeld alleen in het geheugen (B35).
    Hervatbaar per antwoord. Met `snel` zoals het product: geen pauze tussen verzoeken (wel robots.txt), en de tijd per
    antwoord in `wachttijd-<versie>.jsonl`, hoogstens `hoogstens` antwoorden."""
    from concurrent.futures import ThreadPoolExecutor

    from doublecheck import beeldindexmeting as bm
    from doublecheck import fotobron as fb
    from doublecheck.artikelbeelden import beelden_uit_artikel
    from doublecheck.config import load_config

    stap = load_config(None).beeldstap
    kw = {"drempel_pdq": stap.drempel_pdq, "min_punten": stap.min_punten, "min_dekking": stap.min_dekking}
    pad = plan["_map"] / fotobestand(versie, snel)
    gedaan = {(r["id"], r["arm"]) for r in _jsonl(pad)} if pad.exists() else set()
    items = {s["id"]: s for s in _jsonl(plan["_map"] / "set.jsonl")}
    werk = [r for r in _jsonl(plan["_map"] / "antwoorden.jsonl") if (r["id"], r["arm"]) not in gedaan
            and fb.moet_zoeken(r, bool(items.get(r["id"], {}).get("beeld")))]
    werk = werk[:hoogstens] if hoogstens else werk
    print(f"{len(werk)} groene antwoorden met een beeld ({versie}{', snel' if snel else ''})", flush=True)
    web, slot, teller = bm.Beleefd(pauze=0.0 if snel else 2.0), threading.Lock(), collections.Counter()

    def beelden_van(url: str) -> list[str] | None:
        if bm.host(url) in bm.UITGESLOTEN or not web.mag(url):
            return None
        antwoord = web._vraag(url)
        if antwoord is None or antwoord.status_code != 200:
            return None
        try:
            return beelden_uit_artikel(antwoord.text, str(antwoord.url))
        except Exception:  # noqa: BLE001 - een pagina die niet te lezen is, opent niet
            return None

    def een(r: dict) -> None:
        item = items[r["id"]]
        beeld = beeld_of_reserve(item)
        if beeld is None:
            print(f"beeld niet bereikbaar, overgeslagen: {r['id']}", flush=True)
            return
        eigen = {_adres(u) for u in eigen_urls(item)}
        paginas = fb.paginas(r["bronnen"], versie)
        begin = time.perf_counter()
        if snel:  # zoals het product: alle pagina's in hun volgorde, de eigen check niet apart
            rij = {"id": r["id"], "arm": r["arm"], "vondst": fb.zoek(beeld, paginas, beelden_van, web.beeld, **kw,
                                                                       versie=versie),
                   "seconden": round(time.perf_counter() - begin, 2)}
            with slot:
                _schrijf(pad, [rij])
                teller["gevonden" if rij["vondst"]["gevonden"] else "niet gevonden"] += 1
            return
        anders = [p for p in paginas if _adres(p) not in eigen]
        zonder = fb.zoek(beeld, anders, beelden_van, web.beeld, **kw, versie=versie)
        rij = {"id": r["id"], "arm": r["arm"], "vondst": {**zonder, "paginas": len(paginas)}}
        if len(anders) < len(paginas):
            rij["zonder_eigen"] = zonder
            if not zonder["gevonden"]:
                bij = fb.zoek(beeld, [p for p in paginas if _adres(p) in eigen], beelden_van, web.beeld, **kw,
                              versie=versie)
                rij["vondst"] = {**bij, "paginas": len(paginas), "geopend": zonder["geopend"] + bij["geopend"],
                                 "beelden": zonder["beelden"] + bij["beelden"], "beste": bij["beste"] or zonder["beste"]}
        with slot:
            _schrijf(pad, [rij])
            teller["gevonden" if rij["vondst"]["gevonden"] else "niet gevonden"] += 1
            teller[r["set"]] += 1

    with ThreadPoolExecutor(6) as pool:
        for i, _ in enumerate(pool.map(een, werk), 1):
            if i % 10 == 0 or i == len(werk):
                print(f"{i} van {len(werk)}: {dict(teller)}", flush=True)


def _labels(plan: dict) -> dict[str, str]:  # pragma: no cover - een bestand
    pad = plan["_labels"]
    if not pad.exists():
        return {}
    labels = {k: v["label"] for k, v in json.loads(pad.read_text(encoding="utf-8")).get("labels", {}).items()}
    fout = [k for k, v in labels.items() if v not in LABELWAARDEN]
    if fout:
        raise Weigering(f"onbekende labels: {fout[:3]}")
    return labels


def _lezen(plan: dict, versie: str = "fotobron-v1") -> None:  # pragma: no cover - op de bestanden
    """Wat nog een label nodig heeft, in een bestand voor wie labelt, en kort op het scherm."""
    labels, items = _labels(plan), {s["id"]: s for s in _jsonl(plan["_map"] / "set.jsonl")}
    open_ = [r for r in _antwoorden(plan, versie) if moet_lezen(r, plan) and _label(r, labels, items) is None]
    uit = plan["_map"] / "te-labelen.jsonl"
    uit.write_text("".join(json.dumps({"sleutel": f"{r['id']}#{r['arm']}", "set": r["set"],
                                       "onwaar": r["set"] in plan["onwaar"], "bericht": items[r["id"]]["tekst"],
                                       "datum": items[r["id"]].get("datum"), **{k: r[k] for k in (
                                           "kleur", "uitkomst", "uitleg", "bronnen", "speurstap")},
                                       **{k: r[k] for k in ("zonder_foto", "foto") if k in r}},
                                      ensure_ascii=False) + "\n" for r in open_), encoding="utf-8")
    print(f"{len(open_)} te labelen in {uit}")
    print(collections.Counter((r["set"], r["kleur"], r["uitkomst"]) for r in open_))


def _tellen(plan: dict, versie: str = "fotobron-v1") -> None:  # pragma: no cover - op de bestanden
    from doublecheck import uitkomsten as uk

    rijen = _antwoorden(plan, versie)
    for naam, arm in plan["armen"].items():
        if {r["vraag"] for r in rijen if r["arm"] == naam} - {vingerafdruk(arm)}:
            raise Weigering(f"arm {naam}: de antwoorden rusten op een andere vraag dan de code nu stelt")
    items = {s["id"]: s for s in _jsonl(plan["_map"] / "set.jsonl")}
    tel = {**telling(rijen, _labels(plan), plan, items), "kosten": round(uk._uitgegeven(_ronde(plan)), 4)}
    (plan["_map"] / ("telling.json" if versie == "fotobron-v1" else f"telling-{versie}.json")).write_text(json.dumps(tel, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(tel, ensure_ascii=False, indent=1))


def main() -> None:  # pragma: no cover - CLI
    import argparse

    parser = argparse.ArgumentParser(description="Eén vaste meetopzet voor de controle (PLAN #32.41)")
    parser.add_argument("plan")
    parser.add_argument("stap", choices=("set", "draaien", "foto", "wachttijd", "lezen", "tellen"))
    parser.add_argument("--proef", type=int)
    parser.add_argument("--direct", action="store_true", help="de vragen los en tegelijk, niet via de Batch API")
    parser.add_argument("--foto", default="fotobron-v1", help="de versie van de foto bij de bron (#32.54)")
    parser.add_argument("--snel", action="store_true", help="foto: zoals het product, met de tijd per antwoord")
    parser.add_argument("--max", type=int, help="foto --snel: hoogstens zoveel antwoorden")
    args = parser.parse_args()
    plan = lees_plan(args.plan)
    {"set": _set, "draaien": lambda p: _draai(p, args.proef, args.direct), "foto": lambda p: _foto(p, args.foto, args.snel, args.max), "wachttijd": _wachttijd, "lezen": lambda p: _lezen(p, args.foto),
     "tellen": lambda p: _tellen(p, args.foto)}[args.stap](plan)


if __name__ == "__main__":
    main()
