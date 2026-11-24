"""Alleen wat publiek is: een check over het privéleven van één gewoon persoon gaat uit de uitgave (PLAN #34.2ch).

Factiz verzamelt desinformatie die ontwrichtend kan werken: over gezondheid, oorlog, politiek, migratie, publieke personen,
oplichting op grote schaal. Factcheckers checken ook kettingberichten over één persoon: een ziek kind, een inzameling, een
vermiste, een persoonlijk drama. Die helpen niemand om desinformatie te herkennen (PO 2026-11-22: "Te particuliere
dingen moeten er wat mij betreft uit"). Haiku leest elke bewering met één vraag: publiek of particulier
(`relevantie-v2`, tien per vraag); een misdaad die als verhaal over een groep wordt verteld en een bewering over een
publiek persoon zijn altijd publiek. Ik lees 200 die Haiku particulier noemde en 100 publieke na; de regel vooraf:
hoogstens 2 van de 200 toch publiek en hoogstens 5 twijfel (`poort`). Pas dan gaat wat particulier is uit de uitgave.

    python -m doublecheck.relevantie vragen [--proef N]|indienen|ophalen [--wacht M]|tweede|lezen|tellen

In de ontwikkelset (de eerste 100 van v2) waren 38 van de 100 toch publiek; daarom leest Sonnet daarna elke particuliere
opnieuw met zes voorwaarden (`tweede_verzoek`), en alleen wat beide particulier noemen kan weg.

Leest de nieuwste publicatiedatabase (openbare beweringen), alleen-lezen; de Batch API op openbare beweringen. Uitvoer in
`data/relevantie/`; mijn lezing in `docs/steekproeven/34.2ch-particulier.json`.
"""

from __future__ import annotations

import argparse
import json
import random
import sqlite3
from collections import Counter
from pathlib import Path

WORTEL = Path(__file__).resolve().parent.parent
MAP = WORTEL / "data" / "relevantie"
VOL = MAP / "vol.jsonl"
BATCHES = MAP / "batches.jsonl"
TWEEDE_ANTWOORDEN = MAP / "tweede.jsonl"
LABELS = WORTEL / "docs" / "steekproeven" / "34.2ch-particulier.json"
VERSIE = "relevantie-v2"          # v1 noemde in de proef een waarschuwing over zeep en een gekapseisde boot particulier
OORDELEN = ("publiek", "particulier", "twijfel")
LEESLABELS = ("publiek", "particulier", "twijfel")
ZAAD = 2217            # 2216 was de ontwikkelset van v2 (34.2ch-particulier-ontwikkel.json)
TWEEDE = "relevantie-tweede-v1"
TWEEDE_GRENS = 6.00
PARTICULIER_N = 200
PUBLIEK_N = 100
MAX_FOUT = 2           # van de 200 particuliere hoogstens zoveel die toch publiek zijn (de regel vooraf)
MAX_TWIJFEL = 5
PER_VRAAG = 10
DRADEN = 8
GRENS = 4.00           # dollar, alles samen; de volle ronde via de Batch API ~$2,40
SCHATTING_BATCH = 0.00003


class Weigering(Exception):
    pass


def verzoek(teksten: list[str]) -> dict:
    """Eén vraag over een rijtje beweringen, in welke taal ook."""
    from doublecheck.modellen import MODELLEN

    systeem = (
        "You read claims from a public archive of fact-checks, in many languages. For each numbered claim, decide whether "
        "it is about a public matter or about a private matter.\n"
        "\n"
        "- \"publiek\": the claim concerns something of public interest: health, medicine and vaccines; science and "
        "technology; politics, government, elections and laws; war, conflict and terrorism; migration; the economy, "
        "prices, money, companies and products; climate and the environment; religion, ethnic or social groups; public "
        "institutions and services; public figures (politicians, officials, celebrities, athletes, business leaders, "
        "journalists, influencers); scams, frauds or warnings that target many people; disasters and events that affect "
        "many people.\n"
        "- \"particulier\": only when the claim is about the private life of one ordinary person or one family and "
        "nothing in it concerns anyone else: an appeal for a sick or missing person, a donation or prayer chain for an "
        "individual, a personal tragedy, a private dispute, gossip about ordinary people. A warning about a product, "
        "food, place, health risk or scam that could affect anyone is \"publiek\". An accident, disaster or crime with "
        "several victims, in public transport or in a public place, is \"publiek\".\n"
        "- \"twijfel\": you cannot tell.\n"
        "\n"
        "A crime by or against a private person that is used to make a claim about a religious, ethnic, political or "
        "national group, or about the police, the state or a country, is \"publiek\". A claim about a public figure is "
        "always \"publiek\", also when you do not know the name: a person described by a public role (actor, actress, "
        "singer, presenter, politician, official, judge, athlete, journalist, influencer, a doctor or scientist speaking "
        "in public) is a public figure.")
    schema = {"type": "object", "additionalProperties": False, "required": ["antwoorden"], "properties": {
        "antwoorden": {"type": "array", "items": {
            "type": "object", "additionalProperties": False, "required": ["nr", "oordeel"],
            "properties": {"nr": {"type": "integer"}, "oordeel": {"type": "string", "enum": list(OORDELEN)}}}}}}
    vraag = "\n".join(f"{i}. {' '.join((t or '').split())}" for i, t in enumerate(teksten, 1))
    return {"model": MODELLEN["haiku"]["id"], "max_tokens": 1500, "system": systeem,
            "messages": [{"role": "user", "content": [{"type": "text", "text": vraag}]}],
            "output_config": {"effort": "low", "format": {"type": "json_schema", "schema": schema}}}


def lees_oordelen(tekst: str | None, teksten: list[str]) -> list[str | None]:
    """De oordelen op nummer; een nummer dat ontbreekt of twee keer voorkomt, of een onbekende waarde, telt niet."""
    uit: list[str | None] = [None] * len(teksten)
    try:
        antwoorden = json.loads(tekst or "")["antwoorden"]
        nummers = Counter(a["nr"] for a in antwoorden)
    except (json.JSONDecodeError, KeyError, TypeError):
        return uit
    for a in antwoorden:
        nr, oordeel = (a.get("nr"), a.get("oordeel")) if isinstance(a, dict) else (None, None)
        if isinstance(nr, int) and 1 <= nr <= len(teksten) and nummers[nr] == 1 and oordeel in OORDELEN:
            uit[nr - 1] = oordeel
    return uit


def tweede_verzoek(teksten: list[str]) -> dict:
    """De tweede lezing, door Sonnet, van wat Haiku particulier noemde. In de ontwikkelset van v2 waren 38 van de 100 toch
    publiek: een publiek persoon die het model niet kende (David Miller, Gabigol, Sonali Phogat), oplichting, een verhaal
    over een groep, corona, oorlog. Daarom alleen particulier als alle zes voorwaarden gelden."""
    from doublecheck.modellen import MODELLEN

    systeem = (
        "Each numbered item is a claim from a public archive of fact-checks. The archive keeps claims that matter to the "
        "public: disinformation about health, science, politics, war, migration, the economy, groups of people, public "
        "figures and institutions, and scams that target many people. Decide for each claim whether it may be left out "
        "because it is purely private.\n"
        "\n"
        "Answer \"particulier\" only if all of these hold:\n"
        "1. It is about one specific ordinary person, family or animal, or one private incident.\n"
        "2. No person in it is or may be a public figure: a politician, official, judge, police or army officer in that "
        "role, celebrity, actor, singer, athlete, footballer, cricketer, journalist, presenter, influencer, writer, "
        "religious leader, business leader, or a relative of one. If a named person could be a public figure in any "
        "country, it is not \"particulier\".\n"
        "3. It says nothing about a religion, caste, ethnic or national group, political party, protest, election, war, "
        "the police, the state, a country or a government.\n"
        "4. It is not a commercial offer, prize, giveaway, job vacancy or investment: those are scams that target many "
        "people. A prayer, sharing or donation appeal for one person, or one pet to adopt, can be \"particulier\".\n"
        "5. It is not a health, medical, covid, vaccine, science, nature or technology claim, or advice, that could apply "
        "to anyone. A story about one person's illness or accident can be \"particulier\".\n"
        "6. It is not about a disaster, an accident with several victims, or an event that affects many people.\n"
        "\n"
        "Otherwise answer \"publiek\". Answer \"twijfel\" if you cannot tell.")
    schema = {"type": "object", "additionalProperties": False, "required": ["antwoorden"], "properties": {
        "antwoorden": {"type": "array", "items": {
            "type": "object", "additionalProperties": False, "required": ["nr", "oordeel"],
            "properties": {"nr": {"type": "integer"}, "oordeel": {"type": "string", "enum": list(OORDELEN)}}}}}}
    vraag = "\n".join(f"{i}. {' '.join((t or '').split())}" for i, t in enumerate(teksten, 1))
    return {"model": MODELLEN["sonnet"]["id"], "max_tokens": 1500, "system": systeem,
            "messages": [{"role": "user", "content": [{"type": "text", "text": vraag}]}],
            "output_config": {"effort": "low", "format": {"type": "json_schema", "schema": schema}}}


def _laatste(vol: list[dict], versie: str = VERSIE) -> dict[str, dict]:
    return {r["pagina"]: r for r in vol if r.get("versie") == versie and r.get("oordeel")}


def particulier_volgens_beide(vol: list[dict], tweede: list[dict]) -> dict[str, str]:
    """De pagina's die Haiku en daarna Sonnet bij dezelfde tekst particulier noemden, met die tekst."""
    sonnet = _laatste(tweede, TWEEDE)
    return {p: r["bewering"] for p, r in _laatste(vol).items()
            if r["oordeel"] == "particulier" and p in sonnet and sonnet[p]["oordeel"] == "particulier"
            and sonnet[p]["bewering"] == r["bewering"]}


def te_lezen(vol: list[dict], tweede: list[dict]) -> tuple[list[str], list[str]]:
    """Wat ik nalees: een vaste greep van `PARTICULIER_N` uit wat beide particulier noemden en `PUBLIEK_N` uit wat Haiku
    publiek noemde."""
    laatste = _laatste(vol)
    part = sorted(particulier_volgens_beide(vol, tweede))
    publ = sorted(p for p, r in laatste.items() if r["oordeel"] == "publiek")
    return (random.Random(ZAAD).sample(part, min(PARTICULIER_N, len(part))),
            random.Random(ZAAD + 1).sample(publ, min(PUBLIEK_N, len(publ))))


def _labels(pad: str | Path) -> dict:
    try:
        return json.loads(Path(pad).read_text(encoding="utf-8"))["labels"]
    except (OSError, json.JSONDecodeError, KeyError, TypeError):
        return {}


def _greep(pad: str | Path) -> tuple[list[str], list[str]] | None:
    """De greep die gelezen is, vast in het labelbestand (2026-11-23): nieuwe antwoorden verschuiven een nieuwe trekking,
    en dan ging de poort dicht en kwam wat particulier is terug in de uitgave. Niets als er nog geen greep vastligt."""
    try:
        g = json.loads(Path(pad).read_text(encoding="utf-8"))["greep"]
        return list(g["particulier"]), list(g["publiek"])
    except (OSError, json.JSONDecodeError, KeyError, TypeError):
        return None


def poort(vol: list[dict], tweede: list[dict], pad: str | Path = LABELS) -> tuple[bool, str]:
    """Mag wat particulier is uit de uitgave? Alleen als alles wat getrokken is gelezen is, met van de particuliere
    hoogstens `MAX_FOUT` die toch publiek zijn en hoogstens `MAX_TWIJFEL` twijfel."""
    labels = _labels(pad)
    if not labels:
        return False, "nog niets gelezen"
    part, publ = _greep(pad) or te_lezen(vol, tweede)
    open_ = [p for p in part + publ if labels.get(p, {}).get("label") not in LEESLABELS]
    if open_:
        return False, f"{len(open_)} nog te lezen"
    telling = Counter(labels[p]["label"] for p in part)
    gemist = sum(labels[p]["label"] == "particulier" for p in publ)
    reden = (f"van {len(part)} particuliere {telling['particulier']} terecht, {telling['publiek']} toch publiek, "
             f"{telling['twijfel']} twijfel; van {len(publ)} publieke {gemist} toch particulier")
    if telling["publiek"] > MAX_FOUT or telling["twijfel"] > MAX_TWIJFEL:
        return False, reden
    return True, reden


def voor_uitgave(vol: list[dict], tweede: list[dict], pad: str | Path = LABELS) -> dict[str, dict]:
    """Per pagina die Haiku en Sonnet particulier lazen, de tekst die gelezen is (de uitgave laat haar alleen weg bij
    precies die tekst); niets als de poort dicht is. Wat ik als publiek of twijfel las, blijft."""
    if not poort(vol, tweede, pad)[0]:
        return {}
    labels = _labels(pad)
    return {p: {"bron": t} for p, t in particulier_volgens_beide(vol, tweede).items()
            if labels.get(p, {}).get("label") not in ("publiek", "twijfel")}


# --- bestanden en het model ------------------------------------------------------------------------------------------

def _jsonl(pad: Path) -> list[dict]:
    if not pad.exists():
        return []
    return [json.loads(regel) for regel in pad.read_text(encoding="utf-8").splitlines() if regel.strip()]


def voor_de_uitgave() -> tuple[dict[str, dict], str]:  # pragma: no cover - bestanden
    vol, tweede = _jsonl(VOL), _jsonl(TWEEDE_ANTWOORDEN)
    return voor_uitgave(vol, tweede), poort(vol, tweede)[1]


def _paginas() -> dict[str, str]:  # pragma: no cover - een bestand
    """Elke bewering van de nieuwste uitgave, op nummer, zonder de eigen checks (die schreef de redactie zelf)."""
    paden = sorted((WORTEL / "data" / "publicatie").glob("*/publicatie.db"))
    if not paden:
        raise Weigering("geen publicatiedatabase: bouw er een met `python -m doublecheck.publiceren bouwen`")
    pub = sqlite3.connect(f"{paden[-1].resolve().as_uri()}?mode=ro", uri=True)
    return dict(pub.execute("SELECT nummer, bewering FROM pagina WHERE nummer NOT IN "
                            "(SELECT pagina FROM check_ WHERE bron = 'factiz-redactie')"))


def _uitgegeven() -> float:  # pragma: no cover - bestanden
    return (sum(a.get("kosten", 0.0) for a in _jsonl(VOL))
            + sum(b["schatting"] for b in _jsonl(BATCHES) if b.get("werkelijk") is None))


def _vragen(proef: int) -> None:  # pragma: no cover - een model, op openbare beweringen
    """Een proef, direct: de eerste `proef` van een vaste greep, om de vraag te zien voor de volle ronde."""
    import anthropic

    from doublecheck.modellen import MODELLEN
    from doublecheck.varianten import laad_sleutel

    paginas = _paginas()
    gekozen = random.Random(ZAAD).sample(sorted(paginas), proef)
    laad_sleutel()
    client, prijs = anthropic.Anthropic(max_retries=6), MODELLEN["haiku"]
    MAP.mkdir(parents=True, exist_ok=True)
    for i in range(0, len(gekozen), PER_VRAAG):
        groep = gekozen[i:i + PER_VRAAG]
        msg = client.messages.create(**verzoek([paginas[p] for p in groep]))
        kosten = 2 * (msg.usage.input_tokens * prijs["in"] + msg.usage.output_tokens * prijs["uit"]) / 1e6
        tekst = "".join(getattr(b, "text", "") or "" for b in msg.content)
        for p, o in zip(groep, lees_oordelen(tekst, [paginas[p] for p in groep])):
            print(f"{o or '-':12} {' '.join(paginas[p].split())[:150]}")
        print(f"${kosten:.4f}")


def _indienen() -> None:  # pragma: no cover - de Batch API, op openbare beweringen
    from datetime import date

    import anthropic

    from doublecheck import routinegrens as rg
    from doublecheck.varianten import laad_sleutel

    klaar = {(r["pagina"], r["bewering"]) for r in _jsonl(VOL) if r.get("oordeel") and r.get("versie") == VERSIE}
    lopend = {p for b in _jsonl(BATCHES) if b.get("werkelijk") is None for p in b["paginas"]}
    werk = [(p, t) for p, t in sorted(_paginas().items()) if (p, t) not in klaar and p not in lopend]
    if not werk:
        print("niets te vragen")
        return
    schatting = SCHATTING_BATCH * len(werk)
    if rg.uitgave():            # onder de routine per week telt haar ruimte, niet de grens voor altijd (PLAN #35.2)
        if not rg.past(schatting):
            raise Weigering(f"geschat ${schatting:.2f} past niet in de ruimte van de routine (${rg.ruimte():.2f})")
    elif _uitgegeven() + schatting > GRENS:
        raise Weigering(f"geweigerd: ${_uitgegeven():.2f} uitgegeven plus ${schatting:.2f} is meer dan ${GRENS:.2f}")
    groepen = [werk[i:i + PER_VRAAG] for i in range(0, len(werk), PER_VRAAG)]
    laad_sleutel()
    client = anthropic.Anthropic(max_retries=6)
    batch = client.messages.batches.create(requests=[{"custom_id": f"g{i}", "params": verzoek([t for _, t in g])}
                                                     for i, g in enumerate(groepen)])
    MAP.mkdir(parents=True, exist_ok=True)
    (MAP / f"batch-{batch.id}.json").write_text(json.dumps({f"g{i}": g for i, g in enumerate(groepen)}, ensure_ascii=False),
                                                encoding="utf-8")
    with BATCHES.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rg.merk({"id": batch.id, "paginas": [p for p, _ in werk], "schatting": round(schatting, 4),
                                    "versie": VERSIE, "dag": date.today().isoformat(), "werkelijk": None})) + "\n")
    print(f"batch {batch.id}: {len(werk)} beweringen in {len(groepen)} vragen, schatting ${schatting:.2f}")


def _ophalen(wacht: int) -> None:  # pragma: no cover - de Batch API
    import time

    import anthropic

    from doublecheck import berichtcontrole as bc
    from doublecheck.modelpoort import kosten_batch
    from doublecheck.varianten import laad_sleutel

    laad_sleutel()
    client = anthropic.Anthropic()
    einde = time.time() + 60 * wacht
    while True:
        batches, open_ = _jsonl(BATCHES), 0
        for b in batches:
            if b.get("werkelijk") is not None:
                continue
            if client.messages.batches.retrieve(b["id"]).processing_status != "ended":
                open_ += 1
                continue
            groepen = json.loads((MAP / f"batch-{b['id']}.json").read_text(encoding="utf-8"))
            werkelijk, uitslag = 0.0, Counter()
            with VOL.open("a", encoding="utf-8") as f:
                for r in client.messages.batches.results(b["id"]):
                    groep = groepen.get(r.custom_id) or []
                    if not groep or r.result.type != "succeeded":
                        uitslag["zonder"] += len(groep)
                        continue
                    msg = r.result.message
                    kosten = kosten_batch(bc.gebruik_uit(msg), "haiku")
                    werkelijk += kosten
                    tekst = None if msg.stop_reason == "max_tokens" else "".join(getattr(x, "text", "") or "" for x in msg.content)
                    for (p, t), o in zip(groep, lees_oordelen(tekst, [t for _, t in groep])):
                        uitslag[o or "zonder"] += 1
                        f.write(json.dumps({"pagina": p, "bewering": t, "oordeel": o, "versie": b["versie"],
                                            "kosten": round(kosten / len(groep), 7)}, ensure_ascii=False) + "\n")
            b["werkelijk"] = round(werkelijk, 4)
            BATCHES.write_text("".join(json.dumps(x) + "\n" for x in batches), encoding="utf-8")
            print(f"batch {b['id']}: {dict(uitslag)}, ${werkelijk:.2f}")
        if not open_ or time.time() > einde:
            print(f"{open_} batches nog open; samen ${_uitgegeven():.2f} van ${GRENS:.2f}")
            return
        time.sleep(60)


def _tweede() -> None:  # pragma: no cover - een model, op openbare beweringen
    """Sonnet leest, direct, wat Haiku particulier noemde en nog geen tweede lezing van die tekst heeft."""
    import threading
    from concurrent.futures import ThreadPoolExecutor

    import anthropic

    from doublecheck.modellen import MODELLEN
    from doublecheck.varianten import laad_sleutel

    eerder = _jsonl(TWEEDE_ANTWOORDEN)
    klaar = {(r["pagina"], r["bewering"]) for r in eerder if r.get("versie") == TWEEDE and r.get("oordeel")}
    werk = [(p, r["bewering"]) for p, r in sorted(_laatste(_jsonl(VOL)).items())
            if r["oordeel"] == "particulier" and (p, r["bewering"]) not in klaar]
    if not werk:
        print("niets te vragen")
        return
    uitgegeven = sum(r.get("kosten", 0.0) for r in eerder)
    if uitgegeven + 0.002 * len(werk) > TWEEDE_GRENS:
        raise Weigering(f"geweigerd: ${uitgegeven:.2f} plus ${0.002 * len(werk):.2f} is meer dan ${TWEEDE_GRENS:.2f}")
    laad_sleutel()
    client, slot, prijs = anthropic.Anthropic(max_retries=6), threading.Lock(), MODELLEN["sonnet"]
    MAP.mkdir(parents=True, exist_ok=True)

    def een(groep: list[tuple[str, str]]) -> None:
        try:
            msg = client.messages.create(**tweede_verzoek([t for _, t in groep]))
            kosten = 2 * (msg.usage.input_tokens * prijs["in"] + msg.usage.output_tokens * prijs["uit"]) / 1e6
            tekst = None if msg.stop_reason == "max_tokens" else "".join(getattr(b, "text", "") or "" for b in msg.content)
        except Exception as fout:  # noqa: BLE001 - alleen de soort fout
            print("fout:", type(fout).__name__, flush=True)
            return
        with slot, TWEEDE_ANTWOORDEN.open("a", encoding="utf-8") as f:
            for (p, t), o in zip(groep, lees_oordelen(tekst, [t for _, t in groep])):
                f.write(json.dumps({"pagina": p, "bewering": t, "oordeel": o, "versie": TWEEDE,
                                    "kosten": round(kosten / len(groep), 7)}, ensure_ascii=False) + "\n")

    with ThreadPoolExecutor(DRADEN) as pool:
        list(pool.map(een, [werk[i:i + PER_VRAAG] for i in range(0, len(werk), PER_VRAAG)]))
    nu = _laatste(_jsonl(TWEEDE_ANTWOORDEN), TWEEDE)
    print(f"{len(nu)} gelezen:", Counter(r["oordeel"] for r in nu.values()),
          f"${sum(r.get('kosten', 0.0) for r in _jsonl(TWEEDE_ANTWOORDEN)):.2f}")


def main() -> None:  # pragma: no cover - CLI
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("stap", choices=["vragen", "indienen", "ophalen", "tweede", "lezen", "tellen"])
    p.add_argument("--proef", type=int, default=20)
    p.add_argument("--wacht", type=int, default=0, help="minuten wachten tot de batch klaar is")
    a = p.parse_args()
    try:
        if a.stap == "vragen":
            return _vragen(a.proef)
        if a.stap == "indienen":
            return _indienen()
        if a.stap == "ophalen":
            return _ophalen(a.wacht)
        if a.stap == "tweede":
            return _tweede()
        vol, tweede = _jsonl(VOL), _jsonl(TWEEDE_ANTWOORDEN)
        laatste = _laatste(vol)
        if a.stap == "lezen":
            # de greep ligt vast zodra ze getrokken is: een volgende `lezen` geeft dezelfde, nieuwe antwoorden ten spijt
            part, publ = _greep(LABELS) or te_lezen(vol, tweede)
            blad = json.loads(LABELS.read_text(encoding="utf-8")) if LABELS.exists() else {"labels": {}}
            if "greep" not in blad:
                LABELS.write_text(json.dumps({**blad, "greep": {"particulier": part, "publiek": publ}},
                                             ensure_ascii=False, indent=1), encoding="utf-8")
            uit = [{"pagina": p, "groep": "particulier" if p in part else "publiek", "bewering": laatste[p]["bewering"]}
                   for p in part + publ]
            (MAP / "te-lezen.json").write_text(json.dumps(uit, ensure_ascii=False, indent=1), encoding="utf-8")
            print(MAP / "te-lezen.json", len(uit))
            return
        print(f"{len(laatste)} gelezen:", Counter(r["oordeel"] for r in laatste.values()),
              f"${sum(r.get('kosten', 0.0) for r in vol):.2f}")
        print("beide particulier:", len(particulier_volgens_beide(vol, tweede)))
        print("de poort:", poort(vol, tweede))
    except Weigering as fout:
        raise SystemExit(str(fout)) from None


if __name__ == "__main__":  # pragma: no cover
    main()
