"""Ronde 1 van de koers naar de beta (B45, PLAN #31.11 stap 2): het fundament.

Weet de controle wat waar is, en herkent ze wat ertegenin gaat? De machine
zoals in het product (B43: vraag v4, de database met factchecks en webzoeken),
op platte Engelse tekst, zonder beeld. De stand op de schaal van 0 tot 10 komt
uit de meter (B44), met de twee sleutels van `feitstap-v3`: die antwoorden
bestaan al (§154, dezelfde vraag, hetzelfde model, dezelfde kandidaten), dus
alleen de machine kost geld.

De set, vooraf vastgelegd (PLAN #31.11), alleen zinnen die al gelezen en
goedgekeurd zijn bij de feitenstap, en die de machine nooit zag:
- waar, 350: de Engelse formuleringen van de vastgestelde feiten (K, K2, K3)
  en de ware verwante zinnen (W, W3);
- onwaar, 451: de Engelse valse varianten (V, V2, V3): een andere datum,
  plaats, dader of getal, het tegendeel, of "het is een mythe".

Een *klopt niet* met een bron bij een valse zin telt als herkend (vaste regel):
de zinnen zijn al gelezen, en een steekproef van 12 kijkt of de bron past. Past
er een niet, dan wordt elke *klopt niet* gelezen. Elke *klopt niet* en *let op*
bij een ware zin, elke *klopt* en *let op* bij een valse zin, en elke 10 buiten
het eigen feit van een kernzin wordt gelezen voordat hij telt.

    python -m doublecheck.hittewacht -- python -m doublecheck.fundament set
    python -m doublecheck.fundament indienen [--proef 10 | --willekeurig]|ophalen|lezen|tellen
"""

from __future__ import annotations

import json
import random
from collections import Counter
from pathlib import Path

WORTEL = Path(__file__).resolve().parent.parent
UIT = WORTEL / "data" / "fundament"
LABELS = WORTEL / "docs" / "steekproeven" / "31.11-fundament.json"
BUDGET = 10.0  # PO 2026-10-27, B45: ronde 1 "~$7, grens $10"
ZAAD = 3111
WAAR_DELEN = ("K", "K2", "K3", "W", "W3")
ONWAAR_DELEN = ("V", "V2", "V3")
KERNDELEN = ("K", "K2", "K3")
N_STEEKPROEF = 12
SCHATTING = {"waar": 0.030, "onwaar": 0.023}  # per bericht via de Batch API, ruim (de proef: $0,029 en $0,021)
WILLEKEURIG = (130, 150)  # PO 2026-10-27: "meet een willekeurige keuze van 130 ware en 150 valse zinnen erbij"
LAT_HERKEND = 0.90
MAX_KLOPT_VALS = 4


class Weigering(Exception):
    """Tellen of indienen kan niet: iets dat telt zonder label, of boven het budget."""


def kies(rijen: list[dict]) -> list[dict]:
    """De Engelse zinnen van de delen van ronde 1, met hun label, in de volgorde van de set."""
    uit = []
    for r in rijen:
        if r.get("taal") != "en" or r["deel"] not in WAAR_DELEN + ONWAAR_DELEN:
            continue
        uit.append({**r, "soort": "tekst", "label": "waar" if r["deel"] in WAAR_DELEN else "onwaar",
                    "datum": None, "eigen": []})
    return uit


def kies_willekeurig(stukken: list[dict], ingediend: set[str], n_waar: int, n_onwaar: int) -> list[dict]:
    """Een willekeurige keuze met een vast zaad uit wat nog niet gevraagd is, per label."""
    uit = []
    for label, n in (("waar", n_waar), ("onwaar", n_onwaar)):
        groep = sorted((s for s in stukken if s["label"] == label and s["id"] not in ingediend), key=lambda s: s["id"])
        uit += random.Random(f"{ZAAD}-{label}").sample(groep, min(n, len(groep)))
    return sorted(uit, key=lambda s: s["id"])


def eis_b45(fout: int, n: int) -> str:
    """Welke eis van B45 gehaald is: hoogstens 1, 2 of 3 op de 100 ware berichten onterecht rood."""
    for procent, eis in ((1, "99%"), (2, "98%"), (3, "97%")):
        if fout <= n * procent // 100:
            return eis
    return "onder 97%"


def steekproef(stukken: list[dict], antwoorden: dict[str, dict]) -> list[str]:
    """De valse zinnen met *klopt niet* en een bron waarvan een mens leest of de bron past."""
    ids = sorted(s["id"] for s in stukken if s["label"] == "onwaar" and s["id"] in antwoorden
                 and antwoorden[s["id"]]["oordeel"] == "klopt niet" and antwoorden[s["id"]]["bronnen"])
    return sorted(random.Random(ZAAD).sample(ids, min(N_STEEKPROEF, len(ids))))


def _label(labels: dict, sleutel: tuple) -> str:
    if sleutel not in labels:
        raise Weigering(f"{sleutel} heeft geen label in {LABELS.name}; eerst lezen")
    return labels[sleutel]


def telling(stukken: list[dict], antwoorden: dict[str, dict], standen: dict[str, dict], labels: dict,
            proeflabels: dict[str, str]) -> dict:
    """Per label en per deel de oordelen en wat ze waard zijn, de latten van PLAN
    #31.11 en de eis van B45. Weigert zolang iets dat telt geen label heeft."""
    from doublecheck.meter import wilson

    proef = steekproef(stukken, antwoorden)
    onveilig = any(proeflabels.get(i) == "past niet" for i in proef)
    if not onveilig:
        for i in proef:
            if i not in proeflabels:
                raise Weigering(f"{i} uit de steekproef van de bronnen heeft geen label in {LABELS.name}")
    leeg = {"n": 0, "oordelen": Counter(), "herkend": 0, "met check uit de database": 0, "let op terecht": 0,
            "let op andere reden": 0, "klopt niet zonder bewijs": 0, "klopt niet zonder bron": 0, "klopt vals": 0,
            "klopt niet vals": 0, "let op vals": 0, "onterecht rood": 0, "set fout": 0, "op 10": 0,
            "rood op de schaal": 0, "bron indirect": 0}
    uit: dict = {}
    verkeerde_10 = 0
    for s in stukken:
        a = antwoorden.get(s["id"])
        if a is None:
            continue
        o = a["oordeel"]
        groepen = (s["label"], f"deel {s['deel']}") + ((f"{s['label']} {s['groep']}",) if s.get("groep") else ())
        for groep in groepen:
            d = uit.setdefault(groep, {k: (Counter() if isinstance(v, Counter) else v) for k, v in leeg.items()})
            d["n"] += 1
            d["oordelen"][o] += 1
        st = standen.get(s["id"]) or {}
        uitkomst = ["rood op de schaal"] if st.get("stand") is not None and st["stand"] <= 3 else []
        if st.get("stand") == 10:
            uitkomst.append("op 10")
            if not (s["deel"] in KERNDELEN and st.get("feit") == s["feit"]):
                verkeerde_10 += _label(labels, (s["id"], 10, st.get("feit"))) == "fout"
        if s["label"] == "onwaar":
            if o == "klopt niet" and a["bronnen"]:
                eigen = labels.get((s["id"], o))
                if eigen is None and onveilig:
                    eigen = _label(labels, (s["id"], o))
                if eigen in (None, "bewijst", "bewijst indirect"):
                    uitkomst += ["herkend"] + (["bron indirect"] if eigen == "bewijst indirect" else [])
                    if any(b.get("soort") == "geheugen" for b in a["bronnen"]):
                        uitkomst.append("met check uit de database")
                else:
                    uitkomst.append("set fout" if eigen == "set fout" else "klopt niet zonder bewijs")
            elif o == "klopt niet":
                uitkomst.append("klopt niet zonder bron")
            elif o == "let op":
                label = _label(labels, (s["id"], o))
                uitkomst += {"terecht": ["herkend", "let op terecht"], "set fout": ["set fout"]}.get(
                    label, ["let op andere reden"])
            elif o == "klopt":
                uitkomst.append({"vals": "klopt vals", "set fout": "set fout"}[_label(labels, (s["id"], o))])
        elif o in ("klopt niet", "let op"):
            label = _label(labels, (s["id"], o))
            if label == "vals":
                uitkomst += [f"{o} vals", "onterecht rood"]
            elif label == "set fout":
                uitkomst.append("set fout")
        for groep in groepen:
            for k in uitkomst:
                uit[groep][k] += 1
    waar, onwaar = uit.get("waar"), uit.get("onwaar")
    latten = {"geen verkeerde 10": verkeerde_10 == 0}
    if waar:
        latten["ware zinnen nooit klopt niet"] = waar["klopt niet vals"] == 0
        n = waar["n"] - waar["set fout"]
        uit["eis B45"] = {"onterecht rood": waar["onterecht rood"], "van": n,
                          "gehaald": eis_b45(waar["onterecht rood"], n),
                          "bovengrens (95%)": round(wilson(waar["onterecht rood"], n)[1], 4)}
    if onwaar:
        n = onwaar["n"] - onwaar["set fout"]
        onwaar["aandeel herkend"] = round(onwaar["herkend"] / n, 4) if n else None
        latten["valse zinnen ≥ 90% herkend"] = bool(n) and onwaar["herkend"] / n >= LAT_HERKEND
        latten["hoogstens 4 keer klopt bij een valse zin"] = onwaar["klopt vals"] <= MAX_KLOPT_VALS
    for d in uit.values():
        if "oordelen" in d:
            d["oordelen"] = dict(d["oordelen"])
    uit["latten"] = latten
    return uit


# --- de set, de vragen, de labels --------------------------------------------------------

def _jsonl(pad: Path) -> list[dict]:
    return [json.loads(x) for x in Path(pad).read_text(encoding="utf-8").splitlines() if x.strip()] \
        if Path(pad).exists() else []


def maak_set() -> list[dict]:  # pragma: no cover - met het model en de database
    """De zinnen van ronde 1 met wat de database met factchecks bij elk vindt,
    zoals in de dienst (vingerafdruk, de beste 8 met varianten, de vloer)."""
    import sqlite3

    from doublecheck import feitstap
    from doublecheck import verificatie as v
    from doublecheck.config import load_config
    from doublecheck.embedding import fingerprint_texts
    from doublecheck.routemeting import _schrijf
    from doublecheck.search import search_texts
    from doublecheck.storage import connect

    config = load_config(None)
    stukken = kies(feitstap.lees_set(feitstap.VERSIES["v3"]["uit"]))
    vingers = fingerprint_texts([s["tekst"][:600] for s in stukken], config.model_versions.text_embedding)
    lijsten = search_texts(connect("doublecheck.db"), vingers, 8, varianten=True)
    lees = sqlite3.connect("file:doublecheck.db?mode=ro", uri=True)
    lees.row_factory = sqlite3.Row
    for s, lijst in zip(stukken, lijsten):
        s["geheugen"] = v.kandidaten_uit(lees, lijst)
    _schrijf(UIT / "set.jsonl", stukken)
    return stukken


def feitantwoorden(stukken: list[dict]) -> list[dict]:
    """De antwoorden van de twee sleutels uit de meting van `feitstap-v3` (A ook uit v2)."""
    from doublecheck import feitstap as f

    v3 = f.VERSIES["v3"]["uit"]
    per = {"A": f.antwoorden_sleutel(stukken, v3, "A", f.VERSIES["v2"]["uit"]),
           "B": f.antwoorden_sleutel(stukken, v3, "B")}
    return [{"id": i, "sleutel": k, "richting": x["richting"], "feit": x.get("feit")}
            for k, d in per.items() for i, x in d.items()]


def al_uitgegeven() -> float:
    """Van een afgeronde batch het werkelijke bedrag, van een lopende de schatting."""
    return sum(b["schatting"] if b.get("werkelijk") is None else b["werkelijk"] for b in _jsonl(UIT / "batches.jsonl"))


def lees_labels() -> tuple[dict, dict[str, str]]:
    """(labels per uitkomst, de steekproef van de bronnen). Een 10 die bij de
    feitenstap al gelezen is, houdt dat label: zelfde zin, zelfde twee sleutels."""
    from doublecheck import feitstap as f

    labels: dict = {}
    for pad in (f.LABELS_V3, f.LABELS_V2, f.LABELS):
        if Path(pad).exists():
            for r in json.loads(Path(pad).read_text(encoding="utf-8"))["labels"]:
                if r["stand"] == 10:
                    labels.setdefault((r["id"], 10, r["feit"]), {"terecht": "goed"}.get(r["label"], r["label"]))
    if not LABELS.exists():
        return labels, {}
    d = json.loads(LABELS.read_text(encoding="utf-8"))
    for r in d.get("oordelen", []):
        labels[(r["id"], r["oordeel"]) if r["oordeel"] != 10 else (r["id"], 10, r.get("feit"))] = r["label"]
    return labels, {r["id"]: r["label"] for r in d.get("steekproef", [])}


def main() -> None:  # pragma: no cover - CLI, met de Batch API
    import argparse

    from doublecheck import routemeting as rm

    parser = argparse.ArgumentParser(description="Ronde 1: het fundament (B45, PLAN #31.11)")
    parser.add_argument("stap", choices=("set", "indienen", "ophalen", "lezen", "tellen"))
    parser.add_argument("--proef", type=int, default=0, help="indienen: per deel de eerste N")
    parser.add_argument("--willekeurig", action="store_true",
                        help="indienen: 130 ware en 150 valse zinnen, willekeurig met een vast zaad")
    args = parser.parse_args()
    if args.stap == "set":
        stukken = maak_set()
        print(Counter(s["deel"] for s in stukken), Counter(bool(s["geheugen"]) for s in stukken))
        return
    stukken = _jsonl(UIT / "set.jsonl")
    keuze = {i.removeprefix("a-"): b.get("keuze", "proef") for b in _jsonl(UIT / "batches.jsonl") for i in b["ids"]}
    stukken = [{**s, "groep": keuze[s["id"]]} if s["id"] in keuze else s for s in stukken]
    per_id = {s["id"]: s for s in stukken}
    machine = {r["id"]: r for r in _jsonl(UIT / "antwoorden.jsonl")}
    if args.stap in ("lezen", "tellen"):
        labels, proeflabels = lees_labels()
        standen = rm.standen_van(stukken, machine, feitantwoorden(stukken))
        if args.stap == "tellen":
            print(json.dumps(telling(stukken, machine, standen, labels, proeflabels), ensure_ascii=False, indent=1))
            print(f"uitgegeven ${al_uitgegeven():.2f} van ${BUDGET:.2f}")
            return
        from doublecheck.feitstap import zinnen_van_feiten

        zin = zinnen_van_feiten()
        proef = set(steekproef(stukken, machine))
        onveilig = "past niet" in proeflabels.values()
        for s in stukken:
            a, st = machine.get(s["id"]), standen.get(s["id"], {})
            if a is None:
                continue
            o, te_lezen = a["oordeel"], []
            if st.get("stand") == 10 and not (s["deel"] in KERNDELEN and st.get("feit") == s["feit"]) \
                    and (s["id"], 10, st.get("feit")) not in labels:
                te_lezen.append(f"STAND 10 bij {st.get('feit')}: {zin.get(st.get('feit'))}")
            if s["label"] == "onwaar":
                if o in ("let op", "klopt") and (s["id"], o) not in labels:
                    te_lezen.append(f"OORDEEL {o}")
                if o == "klopt niet" and a["bronnen"] and (s["id"], o) not in labels and (
                        onveilig or (s["id"] in proef and s["id"] not in proeflabels)):
                    te_lezen.append("STEEKPROEF: past de bron?" if not onveilig else "OORDEEL klopt niet")
            elif o in ("klopt niet", "let op") and (s["id"], o) not in labels:
                te_lezen.append(f"OORDEEL {o}")
            if te_lezen:
                print(f"\n[{s['id']} · {s['deel']} · {s['label']} · feit {s['feit']}] {' | '.join(te_lezen)}\n"
                      f"  ZIN: {s['tekst']}\n  FEIT: {zin.get(s['feit'])}\n  STAND: {st.get('stand')} "
                      f"({st.get('woorden')})\n  UITLEG: {a.get('uitleg')}")
                for b in a["bronnen"][:4]:
                    print(f"  BRON ({b['soort']}): {b.get('url')} — {(b.get('citaat') or b.get('claim') or '')[:300]}")
        return
    import anthropic

    from doublecheck.leraar import MODELLEN
    from doublecheck.varianten import laad_sleutel

    laad_sleutel()
    client = anthropic.Anthropic()
    batches = UIT / "batches.jsonl"
    if args.stap == "indienen":
        ingediend = {i for b in _jsonl(batches) for i in b["ids"]}
        nog = [s for s in stukken if f"a-{s['id']}" not in ingediend]
        if args.proef:
            nog = [s for d in WAAR_DELEN + ONWAAR_DELEN for s in [x for x in nog if x["deel"] == d][: args.proef]]
        elif args.willekeurig:
            nog = kies_willekeurig(stukken, {i.removeprefix("a-") for i in ingediend}, *WILLEKEURIG)
        if not nog:
            raise SystemExit("niets in te dienen")
        geschat = sum(SCHATTING[s["label"]] for s in nog)
        if al_uitgegeven() + geschat > BUDGET:
            raise Weigering(f"geweigerd: ${al_uitgegeven():.2f} plus ${geschat:.2f} is meer dan ${BUDGET:.2f}")
        verzoeken = [{**rm._machineverzoek(s), "custom_id": f"a-{s['id']}"} for s in nog]
        batch = client.messages.batches.create(requests=verzoeken)
        with batches.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"id": batch.id, "schatting": round(geschat, 3),
                                 "keuze": "willekeurig" if args.willekeurig else "proef" if args.proef else "alles",
                                 "ids": [r["custom_id"] for r in verzoeken]}) + "\n")
        print(f"batch {batch.id}: {len(verzoeken)} berichten; samen ${al_uitgegeven():.2f} van ${BUDGET:.2f}")
        return
    prijs = (MODELLEN["sonnet"]["in"], MODELLEN["sonnet"]["uit"])  # met batchkorting
    alle = _jsonl(batches)
    with (UIT / "antwoorden.jsonl").open("a", encoding="utf-8") as fm:
        for b in alle:
            if b.get("werkelijk") is not None:
                continue
            if client.messages.batches.retrieve(b["id"]).processing_status != "ended":
                print(f"batch {b['id']} loopt nog")
                continue
            werkelijk = 0.0
            for r in client.messages.batches.results(b["id"]):
                if r.result.type != "succeeded":
                    continue
                s = per_id[r.custom_id.removeprefix("a-")]
                rij = rm._machineantwoord(s, r.result.message, prijs)
                werkelijk += rij["kosten"]
                if s["id"] not in machine:
                    fm.write(json.dumps(rij, ensure_ascii=False) + "\n")
            b["werkelijk"] = round(werkelijk, 4)
    rm._schrijf(batches, alle)
    machine = {r["id"]: r for r in _jsonl(UIT / "antwoorden.jsonl")}
    print(Counter((per_id[i]["label"], a["oordeel"]) for i, a in machine.items()),
          f"\nuitgegeven ${al_uitgegeven():.2f} van ${BUDGET:.2f}")


if __name__ == "__main__":
    main()
