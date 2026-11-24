"""De reikwijdte van het archief (B92, PLAN #37.14; PO 2026-11-23: "Ja, doe de scan zoals je voorstelt"): elke bewering
*internationaal*, *regionaal*, *lokaal*, *persoonlijk* of *twijfel*, met de maatstaf van de radar (B89), zodat de
vertaalronde van het archief alleen meeneemt wat buiten één land leesbaar moet zijn.

    python -m doublecheck.reikwijdte proef          # 200 uit een vaste greep, direct; schrijft data/reikwijdte/proef.jsonl
    python -m doublecheck.reikwijdte lezen          # de greep met het label van het model, om te lezen
    python -m doublecheck.reikwijdte indienen       # alle beweringen via de Batch API, tien per vraag, binnen `GRENS`
    python -m doublecheck.reikwijdte ophalen [--wacht M]
    python -m doublecheck.reikwijdte tellen         # per label en per taal, en de poort

Haiku leest de beweringen van de nieuwste uitgave, zonder de eigen checks en de wereldlijst (die zijn al internationaal).
De labels beslissen pas iets als `poort` open is: elke getrokken bewering gelezen in `docs/steekproeven/37.14-reikwijdte.json`
en hoogstens `MAX_FOUT` aan de verkeerde kant van vertalen of niet vertalen. Uit het archief gaat niets door deze scan: wat
persoonlijk is, loopt langs het filter van #34.2ch. De beweringen zijn openbaar (B54: de Batch API op openbare data).
"""

from __future__ import annotations

import argparse
import json
import random
import sqlite3
from collections import Counter
from pathlib import Path

WORTEL = Path(__file__).resolve().parent.parent
MAP = WORTEL / "data" / "reikwijdte"
VOL = MAP / "vol.jsonl"
PROEF = MAP / "proef.jsonl"
BATCHES = MAP / "batches.jsonl"
LABELS = WORTEL / "docs" / "steekproeven" / "37.14-reikwijdte.json"
VERSIE = "reikwijdte-v3"     # met de lat van de PO (B92): lokaal is alleen echt plaatselijk; v1 en v2 met een te strenge lat
OORDELEN = ("internationaal", "regionaal", "lokaal", "persoonlijk", "twijfel")
VERTALEN = frozenset({"internationaal", "regionaal", "twijfel"})     # twijfel vertaalt mee: liever een vertaling te veel
ZAAD = 2313                   # de greep voor de poort; 2311 en 2312 waren ontwikkelsets
ONTWIKKEL_ZAAD = 2312
ONTWIKKEL = WORTEL / "docs" / "steekproeven" / "37.14-reikwijdte-ontwikkel-3.json"
PROEF_N = 200
MAX_FOUT = 20
PER_VRAAG = 10
GRENS = 4.00                  # dollar voor de volle ronde; de scan op particuliere checks kostte $1,38
SCHATTING_BATCH = 0.000025    # dollar per bewering via de Batch API (de ronde van #34.2ch: $1,38 voor ~106.000)
_ANDERE_BRONNEN = ("factiz-redactie", "factiz-wereldlijst")


class Weigering(Exception):
    pass


def verzoek(teksten: list[str]) -> dict:
    """Eén vraag over een rijtje beweringen, in welke taal ook."""
    from doublecheck.modellen import MODELLEN

    systeem = (
        "You read claims from a public archive of fact-checks, in many languages. The archive is translated for readers "
        "around the world; only claims that matter to nobody beyond one local community stay untranslated. For each "
        "numbered claim, judge how far its subject reaches.\n"
        "\n"
        "- \"internationaal\": the subject matters beyond one country: war and conflict, international politics and "
        "diplomacy, people known around the world, health, medicine, food and wellness claims, pseudoscience and "
        "curiosities, climate and the environment, migration, science and technology, big international companies, a hoax "
        "that circulates in several countries, or a claim about another country than the one where it circulates.\n"
        "- \"regionaal\": the subject is national or state-wide: the politics, government, leaders, parties, elections, "
        "courts, laws, economy, institutions and well-known figures of one country or of one of its states or provinces "
        "(the United States, India, Brazil or any other country), national news and celebrities, large disasters, religious "
        "or ethnic tensions that make national news, and scams or warnings aimed at a whole country.\n"
        "- \"lokaal\": only something local with no reach beyond its own place: a matter of one town, city or district, a "
        "local official or candidate, a local incident, crime or accident, a local shop, school, hospital or service, a local "
        "event or festival, gossip about people known only locally, and sports results or fan talk.\n"
        "- \"persoonlijk\": only one identifiable private person or family.\n"
        "- \"twijfel\": you cannot tell.\n"
        "\n"
        "Judge the subject, not the language: a claim in Tamil about vaccines is \"internationaal\". When in doubt between "
        "\"regionaal\" and \"lokaal\", choose \"regionaal\".")
    schema = {"type": "object", "additionalProperties": False, "required": ["antwoorden"], "properties": {
        "antwoorden": {"type": "array", "items": {
            "type": "object", "additionalProperties": False, "required": ["nr", "oordeel"],
            "properties": {"nr": {"type": "integer"}, "oordeel": {"type": "string", "enum": list(OORDELEN)}}}}}}
    vraag = "\n".join(f"{i}. {' '.join((t or '').split())}" for i, t in enumerate(teksten, 1))
    return {"model": MODELLEN["haiku"]["id"], "max_tokens": 1500, "system": systeem,
            "messages": [{"role": "user", "content": [{"type": "text", "text": vraag}]}],
            "output_config": {"effort": "low", "format": {"type": "json_schema", "schema": schema}}}


def lees_oordelen(tekst: str | None, teksten: list[str]) -> list[str | None]:
    """De labels op nummer; een nummer dat ontbreekt of twee keer voorkomt, of een onbekende waarde, telt niet."""
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


def te_lezen(paginas: dict[str, str], zaad: int = ZAAD) -> list[str]:
    """De vaste greep die ik lees: `PROEF_N` paginanummers, altijd dezelfde bij dezelfde uitgave en hetzelfde zaad."""
    return sorted(random.Random(zaad).sample(sorted(paginas), min(PROEF_N, len(paginas))))


def _kant(label: str | None) -> bool | None:
    return None if label is None else label in VERTALEN


def poort(greep: list[str], model: dict[str, str], pad: str | Path = LABELS) -> tuple[bool, str]:
    """Mogen de labels beslissen? Alleen als elke getrokken bewering gelezen is en hoogstens `MAX_FOUT` aan de verkeerde kant
    van vertalen of niet vertalen staan (een fout binnen één kant, regionaal voor internationaal, telt niet)."""
    try:
        labels = json.loads(Path(pad).read_text(encoding="utf-8"))["labels"]
    except (OSError, json.JSONDecodeError, KeyError, TypeError):
        labels = {}
    if not labels:
        return False, "nog niets gelezen"
    open_ = [p for p in greep if (labels.get(p) or {}).get("label") not in OORDELEN]
    if open_:
        return False, f"{len(open_)} nog te lezen"
    fout = sum(_kant(model.get(p)) != _kant(labels[p]["label"]) for p in greep)
    reden = f"{len(greep) - fout} van de {len(greep)} aan de goede kant, {fout} fout (hoogstens {MAX_FOUT})"
    return fout <= MAX_FOUT, reden


def laatste(vol: list[dict]) -> dict[str, dict]:
    return {r["pagina"]: r for r in vol if r.get("versie") == VERSIE and r.get("oordeel")}


def voor_vertaling(vol: list[dict], paginas: dict[str, str]) -> set[str]:
    """De pagina's die de vertaalronde meeneemt: internationaal, regionaal of twijfel, voor precies de tekst die gelezen
    werd (een bewering die sindsdien veranderde, moet opnieuw gelezen)."""
    return {p for p, r in laatste(vol).items() if r["oordeel"] in VERTALEN and paginas.get(p) == r["bewering"]}


def te_vertalen(vol: list[dict], paginas: dict[str, str]) -> set[str]:
    """Wat de vertaalronde van het archief meeneemt (B92, punt 4): alles behalve wat bij zijn huidige tekst als lokaal of
    persoonlijk gelezen is. Een bewering die na de scan veranderde of nieuw is, gaat mee tot ze gelezen is."""
    gelezen = laatste(vol)
    return {p for p, t in paginas.items()
            if (gelezen.get(p) or {}).get("bewering") != t or gelezen[p]["oordeel"] in VERTALEN}


def poort_vast(model: dict[str, str], pad: str | Path = LABELS) -> tuple[bool, str]:
    """De poort op de greep die gelezen is, zoals die in het labelbestand staat: een nieuwe uitgave met andere pagina's
    verschuift de greep niet (de les van #34.2ch, 2026-11-23). Een getrokken bewering zonder antwoord telt als fout."""
    try:
        greep = sorted(json.loads(Path(pad).read_text(encoding="utf-8"))["labels"])
    except (OSError, json.JSONDecodeError, KeyError, TypeError):
        return False, "nog niets gelezen"
    if any(p not in model for p in greep):
        return False, f"{sum(p not in model for p in greep)} getrokken beweringen zonder antwoord van het model"
    return poort(greep, model, pad)


def filter_open() -> bool:  # pragma: no cover - bestanden
    """Mag de vertaalronde deze labels gebruiken? Alleen met de poort open op de gelezen greep."""
    return poort_vast({p: r["oordeel"] for p, r in laatste(_jsonl(PROEF)).items()})[0]


def _jsonl(p: Path) -> list[dict]:
    return [json.loads(r) for r in p.read_text(encoding="utf-8").splitlines() if r.strip()] if p.exists() else []


def _paginas() -> dict[str, str]:  # pragma: no cover - een bestand
    """Elke bewering van de nieuwste uitgave, op nummer, zonder de eigen checks en de wereldlijst."""
    paden = sorted((WORTEL / "data" / "publicatie").glob("*/publicatie.db"))
    if not paden:
        raise Weigering("geen publicatiedatabase: bouw er een met `python -m doublecheck.publiceren bouwen`")
    pub = sqlite3.connect(f"{paden[-1].resolve().as_uri()}?mode=ro", uri=True)
    return dict(pub.execute("SELECT nummer, bewering FROM pagina WHERE nummer NOT IN (SELECT pagina FROM check_ WHERE bron "
                            f"IN ({', '.join('?' * len(_ANDERE_BRONNEN))}))", _ANDERE_BRONNEN))


def _uitgegeven() -> float:  # pragma: no cover - bestanden
    return (sum(a.get("kosten", 0.0) for a in _jsonl(VOL) + _jsonl(PROEF))
            + sum(b["schatting"] for b in _jsonl(BATCHES) if b.get("werkelijk") is None))


def _proef(zaad: int = ZAAD) -> None:  # pragma: no cover - een model, op openbare beweringen
    """De vaste greep, direct, zodat ik haar kan lezen voor de volle ronde."""
    import anthropic

    from doublecheck.modellen import MODELLEN
    from doublecheck.varianten import laad_sleutel

    paginas = _paginas()
    greep = te_lezen(paginas, zaad)
    klaar = {r["pagina"] for r in _jsonl(PROEF) if r.get("versie") == VERSIE and r.get("oordeel")}
    werk = [p for p in greep if p not in klaar]
    laad_sleutel()
    client, prijs = anthropic.Anthropic(max_retries=6), MODELLEN["haiku"]
    MAP.mkdir(parents=True, exist_ok=True)
    with PROEF.open("a", encoding="utf-8") as f:
        for i in range(0, len(werk), PER_VRAAG):
            groep = werk[i:i + PER_VRAAG]
            msg = client.messages.create(**verzoek([paginas[p] for p in groep]))
            kosten = (msg.usage.input_tokens * prijs["in"] + msg.usage.output_tokens * prijs["uit"]) / 1e6
            tekst = "".join(getattr(b, "text", "") or "" for b in msg.content)
            for p, o in zip(groep, lees_oordelen(tekst, [paginas[p] for p in groep])):
                f.write(json.dumps({"pagina": p, "bewering": paginas[p], "oordeel": o, "versie": VERSIE,
                                    "kosten": round(kosten / len(groep), 7)}, ensure_ascii=False) + "\n")
    print(Counter(r["oordeel"] for r in laatste(_jsonl(PROEF)).values()), f"${_uitgegeven():.3f}")


def _indienen() -> None:  # pragma: no cover - de Batch API, op openbare beweringen
    from datetime import date

    import anthropic

    from doublecheck.varianten import laad_sleutel

    paginas = _paginas()
    greep = te_lezen(paginas)
    ok, reden = poort(greep, {p: r["oordeel"] for p, r in laatste(_jsonl(PROEF)).items()})
    if not ok:
        raise Weigering(f"de volle ronde wacht op de poort: {reden}")
    klaar = {(r["pagina"], r["bewering"]) for r in _jsonl(VOL) if r.get("oordeel") and r.get("versie") == VERSIE}
    lopend = {p for b in _jsonl(BATCHES) if b.get("werkelijk") is None for p in b["paginas"]}
    werk = [(p, t) for p, t in sorted(paginas.items()) if (p, t) not in klaar and p not in lopend]
    if not werk:
        print("niets te vragen")
        return
    schatting = SCHATTING_BATCH * len(werk)
    if _uitgegeven() + schatting > GRENS:
        raise Weigering(f"geweigerd: ${_uitgegeven():.2f} uitgegeven plus ${schatting:.2f} is meer dan ${GRENS:.2f}")
    groepen = [werk[i:i + PER_VRAAG] for i in range(0, len(werk), PER_VRAAG)]
    laad_sleutel()
    batch = anthropic.Anthropic(max_retries=6).messages.batches.create(
        requests=[{"custom_id": f"g{i}", "params": verzoek([t for _, t in g])} for i, g in enumerate(groepen)])
    MAP.mkdir(parents=True, exist_ok=True)
    (MAP / f"batch-{batch.id}.json").write_text(json.dumps({f"g{i}": g for i, g in enumerate(groepen)}, ensure_ascii=False),
                                                encoding="utf-8")
    with BATCHES.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"id": batch.id, "paginas": [p for p, _ in werk], "schatting": round(schatting, 4),
                            "versie": VERSIE, "dag": date.today().isoformat(), "werkelijk": None}) + "\n")
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


def main() -> None:  # pragma: no cover - CLI
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("stap", choices=["proef", "lezen", "indienen", "ophalen", "tellen"])
    p.add_argument("--wacht", type=int, default=0)
    p.add_argument("--ontwikkel", action="store_true", help="proef en lezen op de ontwikkelset (zaad 2312, de lat van de PO)")
    a = p.parse_args()
    zaad = ONTWIKKEL_ZAAD if a.ontwikkel else ZAAD
    try:
        if a.stap == "proef":
            return _proef(zaad)
        if a.stap == "indienen":
            return _indienen()
        if a.stap == "ophalen":
            return _ophalen(a.wacht)
        paginas = _paginas()
        greep = te_lezen(paginas, zaad)
        model = {p: r["oordeel"] for p, r in laatste(_jsonl(PROEF)).items()}
        if a.ontwikkel:
            print("de ontwikkelset:", poort(greep, model, ONTWIKKEL)[1])
        if a.stap == "lezen":
            uit = [{"pagina": p, "model": model.get(p), "bewering": paginas[p]} for p in greep]
            (MAP / "te-lezen.json").write_text(json.dumps(uit, ensure_ascii=False, indent=1), encoding="utf-8")
            print(MAP / "te-lezen.json", len(uit), Counter(model.get(p) for p in greep))
            return
        vol = laatste(_jsonl(VOL))
        print(f"{len(vol)} van {len(paginas)} gelezen:", dict(Counter(r["oordeel"] for r in vol.values())),
              f"${_uitgegeven():.2f}")
        print("voor de vertaalronde:", len(voor_vertaling(_jsonl(VOL), paginas)))
        print("de poort (op de gelezen greep):", poort_vast(model))
    except Weigering as fout:
        raise SystemExit(str(fout)) from None


if __name__ == "__main__":  # pragma: no cover
    main()
