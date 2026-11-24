"""'Beweringen eerst' voor screenshots meten (PLAN #32.6, B49).

In ronde 4 (§158) werd bekend nepnieuws als echt screenshot in 54 van de 100
gevallen rood met bewijs. Bij alle 46 missers stond de eigen check niet bij de
vijf beste uit het geheugen; stond hij er wel, dan werd het 34 van de 34 keer
rood. Deze meting zet "beweringen eerst" (`berichtcontrole.beweringen_vragen`,
de vraag van V2 in P4) voor het geheugen, met dezelfde functies als `/check`.

Eerst de voormeting: alleen het zoeken, op vier sets.
- E: de 100 echte screenshots van ronde 4;
- N: de 58 nieuwe screenshots van P4;
- W: de 150 ware chatberichten van ronde 4;
- Z: de 50 chatberichten zonder bewering van ronde 4.

De ronde volgt alleen als de verwachting op E 75 haalt (vooraf vastgelegd in
PLAN #32.6). Haiku krijgt de gemaskeerde tekst van openbare beelden via de
Batch API; dat is offline werk, niet het aanvraagpad. Geen beeld wordt
bewaard (B35).

    python -m doublecheck.hittewacht -- python -m doublecheck.beweringeneerst set
    python -m doublecheck.beweringeneerst indienen [--proef 5]|ophalen|wachttijd
    python -m doublecheck.hittewacht -- python -m doublecheck.beweringeneerst zoeken
    python -m doublecheck.beweringeneerst voormeting
"""

from __future__ import annotations

import dataclasses
import json
import time
from pathlib import Path

from doublecheck import berichtcontrole as bc
from doublecheck import betatoets as bt
from doublecheck import zoekherstel as zh

WORTEL = Path(__file__).resolve().parent.parent
UIT = WORTEL / "data" / "beweringen"
VERSIE = "beweringen-v1"
BUDGET = 5.0  # PLAN #32.6, voor alles samen
SCHATTING = 0.0003  # per vraag aan Haiku via de Batch API, ruim
DOEL_E = 75  # B49
N_WACHTTIJD = 10
ONWAAR = ("onwaar", "misleidend")


class Weigering(RuntimeError):
    pass


def _claims(geheugen: list[dict]) -> set[str]:
    return {k["claim"] for k in geheugen[:5]}


def veranderd(oud: list[dict], nieuw: list[dict]) -> bool:
    """Andere checks bij de vijf beste: alleen dan vraagt de ronde de machine opnieuw."""
    return _claims(oud) != _claims(nieuw)


def eigen_erbij(stuk: dict, geheugen: list[dict]) -> bool:
    return bool(_claims(geheugen) & set(stuk.get("eigen") or ()))


def onwaar_bovenaan_nieuw(oud: list[dict], nieuw: list[dict]) -> bool:
    """Bovenaan een onware check, waar eerst geen onware stond (de bewaking van P4, §162). Een wissel
    tussen twee onware checks bovenaan telt niet."""
    return bool(nieuw) and nieuw[0]["oordeel"] in ONWAAR and not (oud and oud[0]["oordeel"] in ONWAAR)


def bewezen_in_ronde4(stuk: dict, uitkomst: dict, labels: dict) -> bool:
    """Rood met bewijs zoals ronde 4 telde: met de eigen check, of met een andere bron die geen ander label
    kreeg (de steekproef van ronde 4 was veilig, §158)."""
    if not bt.rood(uitkomst["stand"], uitkomst["oordeel"]):
        return False
    return bt._eigen_bewijs(stuk, uitkomst) or (bool(uitkomst["bronnen"]) and labels.get(
        (stuk["id"], uitkomst["oordeel"])) in (None, "bewijst", "bewijst via factcheck"))


def voormeting(stukken: list[dict], nieuw: dict[str, list[dict]], bewezen: set[str]) -> dict:
    """Per set wat het nieuwe geheugen verandert. `bewezen`: de ids van E die in ronde 4 rood met bewijs
    waren. De verwachting op E: wat bewezen was en zijn eigen check houdt, plus de missers waar de eigen
    check er nu bij staat (34 van de 34 werd rood); wie zijn eigen check kwijtraakt, telt niet."""
    uit: dict = {}
    for s in stukken:
        if s["id"] not in nieuw:
            continue
        oud, nw = s["geheugen"], nieuw[s["id"]]
        d = uit.setdefault(s["set"], {"n": 0, "geheugen veranderd": 0, "eigen erbij, oud": 0, "eigen erbij, nieuw": 0,
                                      "eigen kwijt": 0, "eigen gevonden": 0, "onwaar bovenaan, nieuw": 0})
        d["n"] += 1
        d["geheugen veranderd"] += veranderd(oud, nw)
        voor, na = eigen_erbij(s, oud), eigen_erbij(s, nw)
        d["eigen erbij, oud"] += voor
        d["eigen erbij, nieuw"] += na
        d["eigen kwijt"] += voor and not na
        d["eigen gevonden"] += na and not voor
        d["onwaar bovenaan, nieuw"] += onwaar_bovenaan_nieuw(oud, nw)
        if s["set"] == "E":
            d.setdefault("verwachting", 0)
            d["verwachting"] += (s["id"] in bewezen and (na or not voor)) or (s["id"] not in bewezen and na and not voor)
    if "E" in uit:
        uit["door naar de ronde"] = uit["E"]["verwachting"] >= DOEL_E
    return uit


# --- de bestanden en de CLI ----------------------------------------------------------------

def _set() -> list[dict]:
    return bt._jsonl(UIT / "set.jsonl")


def maak_set() -> list[dict]:  # pragma: no cover - met de OCR, het model en de database
    """E, W en Z uit ronde 4, zoals ze daar gemeten zijn; N opnieuw gelezen en voorbereid zoals in het product."""
    from doublecheck import routemeting as rm
    from doublecheck.config import load_config
    from doublecheck.storage import connect

    config = load_config(None)
    conn = connect("doublecheck.db")
    ronde4 = bt._jsonl(bt.UIT / "set.jsonl")
    kies = {"E": ("bekend", "screenshot"), "W": ("waar", "chat"), "Z": ("zonder bewering", "chat")}
    uit = [{**s, "set": naam} for naam, (deel, vorm) in kies.items() for s in ronde4
           if (s["deel"], s["vorm"]) == (deel, vorm)]
    datums = {k["sleutel"]: k.get("datum") for k in rm.beeldkandidaten()}
    for i, n in enumerate(bt._jsonl(zh.UIT / "nieuw.jsonl")):
        bericht = bc.bericht_uit(None, Path(n["beeld"]).read_bytes(), config.ocr)
        v = bc.voorbereiden(conn, config, bericht)
        uit.append({"id": f"n-{n['id']}", "set": "N", "deel": "bekend", "vorm": "screenshot", "label": "onwaar",
                    "bron": "M4FC", "sleutel": n["sleutel"], "zaak": n.get("zaak"), "datum": datums.get(n["sleutel"]),
                    "beeld": n["beeld"], "helft": n["helft"], "tekst": v["tekst"], "geheugen": v["geheugen"],
                    "kandidaten": v["kandidaten"], "eigen": n["eigen"]})
        print(f"\rN {i + 1}", end="", flush=True)
    bt._schrijf(UIT / "set.jsonl", uit)
    print(f"\n{len(uit)} berichten")
    return uit


def _config_aan():  # pragma: no cover - op config.toml
    from doublecheck.config import load_config

    config = load_config(None)
    return dataclasses.replace(config, berichtcontrole=dataclasses.replace(config.berichtcontrole, beweringen=VERSIE))


def al_uitgegeven() -> float:
    return sum(b["schatting"] if b.get("werkelijk") is None else b["werkelijk"]
               for b in bt._jsonl(UIT / "batches.jsonl")) + sum(r["kosten"] for r in bt._jsonl(UIT / "wachttijd.jsonl"))


def main() -> None:  # pragma: no cover - CLI, met de Batch API
    import argparse

    import anthropic

    from doublecheck.leraar import MODELLEN
    from doublecheck.varianten import laad_sleutel

    parser = argparse.ArgumentParser(description="'Beweringen eerst' voor screenshots (PLAN #32.6)")
    parser.add_argument("stap", choices=("set", "indienen", "ophalen", "wachttijd", "zoeken", "voormeting"))
    parser.add_argument("--proef", type=int, default=0)
    args = parser.parse_args()
    UIT.mkdir(parents=True, exist_ok=True)
    if args.stap == "set":
        maak_set()
        return
    stukken = _set()
    config = _config_aan()
    if args.stap in ("indienen", "ophalen", "wachttijd"):
        laad_sleutel()
        client = anthropic.Anthropic()
    batches = bt._jsonl(UIT / "batches.jsonl")
    extracties = {r["id"]: r["beweringen"] for r in bt._jsonl(UIT / "extracties.jsonl")}
    if args.stap == "indienen":
        al = {i for b in batches for i in b["ids"]}
        nodig = [s for s in stukken if bt.batch_id(s["id"]) not in al and s["tekst"].strip()][: args.proef or None]
        geschat = len(nodig) * SCHATTING
        if not nodig or al_uitgegeven() + geschat > BUDGET:
            raise Weigering(f"{len(nodig)} vragen: ${al_uitgegeven():.2f} plus ${geschat:.2f} tegen ${BUDGET:.2f}")
        verzoeken = [{"custom_id": bt.batch_id(s["id"]), "params": bc.beweringenverzoek(s["tekst"], config)}
                     for s in nodig]
        batch = client.messages.batches.create(requests=verzoeken)
        batches.append({"id": batch.id, "schatting": round(geschat, 4), "ids": [v["custom_id"] for v in verzoeken]})
        bt._schrijf(UIT / "batches.jsonl", batches)
        print(f"batch {batch.id}: {len(verzoeken)} vragen, geschat ${geschat:.3f}; samen ${al_uitgegeven():.3f}")
        return
    if args.stap == "ophalen":
        per_batch_id = {bt.batch_id(s["id"]): s["id"] for s in stukken}
        rijen = bt._jsonl(UIT / "extracties.jsonl")
        prijs = MODELLEN[bc.BEWERINGEN[VERSIE]["model"]]
        for b in batches:
            if b.get("werkelijk") is not None:
                continue
            if client.messages.batches.retrieve(b["id"]).processing_status != "ended":
                print(f"{b['id']} loopt nog")
                continue
            kosten = 0.0
            for r in client.messages.batches.results(b["id"]):
                if r.result.type != "succeeded":
                    print(f"{r.custom_id}: {r.result.type}")
                    continue
                msg = r.result.message
                kosten += (msg.usage.input_tokens * prijs["in"] + msg.usage.output_tokens * prijs["uit"]) / 1e6
                tekst = "".join(getattr(blok, "text", "") or "" for blok in msg.content)
                rijen.append({"id": per_batch_id[r.custom_id], "beweringen": zh.lees_extractie(tekst)})
            b["werkelijk"] = round(kosten, 4)
        bt._schrijf(UIT / "extracties.jsonl", rijen)
        bt._schrijf(UIT / "batches.jsonl", batches)
        print(f"{len(rijen)} gelezen; samen ${al_uitgegeven():.3f}")
        return
    if args.stap == "wachttijd":
        gedaan = bt._jsonl(UIT / "wachttijd.jsonl")
        e = [s for s in stukken if s["set"] == "E" and s["tekst"].strip()][len(gedaan):N_WACHTTIJD]
        with (UIT / "wachttijd.jsonl").open("a", encoding="utf-8") as fh:
            for s in e:
                begin = time.perf_counter()
                _, kosten = bc.beweringen_vragen(s["tekst"], client, config, True)
                fh.write(json.dumps({"id": s["id"], "seconden": round(time.perf_counter() - begin, 3),
                                     "kosten": round(kosten, 6)}) + "\n")
                fh.flush()
        tijden = sorted(r["seconden"] for r in bt._jsonl(UIT / "wachttijd.jsonl"))
        print(f"{len(tijden)} keer; mediaan {tijden[len(tijden) // 2]:.2f}s, hoogste {tijden[-1]:.2f}s")
        return
    if args.stap == "zoeken":
        from doublecheck.embedding import fingerprint_texts
        from doublecheck.storage import connect

        conn = connect("doublecheck.db")
        pad = UIT / "geheugen.jsonl"
        klaar = {r["id"] for r in bt._jsonl(pad)}
        with pad.open("a", encoding="utf-8") as fh:
            for i, s in enumerate(stukken):
                if s["id"] in klaar or s["id"] not in extracties:
                    continue
                fp = fingerprint_texts([s["tekst"][:600]], config.model_versions.text_embedding)[0]
                oud = bc.geheugen_met(conn, config, s["tekst"], fp, [])
                nieuw = bc.geheugen_met(conn, config, s["tekst"], fp, extracties[s["id"]])
                fh.write(json.dumps({"id": s["id"], "oud nu": oud, "nieuw": nieuw}, ensure_ascii=False) + "\n")
                fh.flush()
                print(f"\r{i + 1}/{len(stukken)}", end="", flush=True)
        print()
        return
    from doublecheck.config import load_config

    gezocht = {r["id"]: r for r in bt._jsonl(UIT / "geheugen.jsonl")}
    afwijkend = sum(1 for s in stukken if s["id"] in gezocht and _claims(gezocht[s["id"]]["oud nu"]) != _claims(s["geheugen"]))
    e = [s for s in stukken if s["set"] == "E"]
    uitkomsten = bt.uitkomsten_van(e, bt._jsonl(bt.UIT / "antwoorden.jsonl"), bc.ijktabel(load_config(None)))
    labels, _ = bt.lees_labels()
    bewezen = {s["id"] for s in e if s["id"] in uitkomsten and bewezen_in_ronde4(s, uitkomsten[s["id"]], labels)}
    uit = voormeting(stukken, {i: r["nieuw"] for i, r in gezocht.items()}, bewezen)
    uit["oud geheugen nu anders dan in de set"] = afwijkend
    uit["bewezen in ronde 4 (E)"] = len(bewezen)
    uit["uitgegeven"] = round(al_uitgegeven(), 4)
    print(json.dumps(uit, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
