"""De ronde van de vloerstap (PLAN #32.0m, B50; DESIGN §4k, SPECS AC13).

Vooraf vastgelegd in PLAN #32.0m. Drie delen:
- *de ijking en de bewaking:* de twee vragen van `vloer-v1` (Haiku, zonder zoeken) op
  alle berichten van de rondes met vraag v4, en op O en R3. De klasse (*klopt niet*,
  *algemene kennis*) is elk bericht waar beide "clearly false" zeggen; een vals alarm
  is een waar bericht in die klasse;
- *O:* 100 zinnen over de vastgestelde feiten die nog nooit gevraagd zijn, door de
  hele controle met de vloerstap aan, en door het kale model met zoeken;
- *R3 opnieuw geteld:* de vloerstap op de antwoorden van P9, zonder nieuwe vragen aan
  de machine.

Offline, op openbare data, via de Batch API; het product verandert niet.

    python -m doublecheck.hittewacht -- python -m doublecheck.vloerronde set
    python -m doublecheck.vloerronde vloer indienen [--proef 10]|ophalen
    python -m doublecheck.vloerronde o indienen|vervolg|ophalen
    python -m doublecheck.vloerronde wachttijd|lezen|tellen
"""

from __future__ import annotations

import dataclasses
import json
import random
from pathlib import Path

from doublecheck import betatoets as bt
from doublecheck import meter
from doublecheck import vloer as vl

WORTEL = Path(__file__).resolve().parent.parent
UIT = WORTEL / "data" / "vloerronde"
O_MAP = UIT / "o"
R3_MAP = UIT / "r3"
O2_MAP = UIT / "o2"
BUDGET_O2 = 4.0  # PO 2026-10-28: "grens $4"
KAAL_IN_O = 0.0054  # gemeten in O (#32.0m): $0,539 voor 100 vragen aan het kale model
LABELS = WORTEL / "docs" / "steekproeven" / "32.0m-vloerronde.json"
BUDGET = 7.0  # PO 2026-10-28: "grens $7"
ZAAD = 3220
ZAAD_O2 = 3221  # PLAN #32.0n: een nieuw vast zaad
N_O = 50  # per label
N_WACHTTIJD = 10
KLASSE = ("klopt niet", "algemene kennis")


class Weigering(RuntimeError):
    pass


def kies_o(fundament: list[dict], gevraagd: set[str], uitgesloten: set[str], zaad: int = ZAAD,
           voorvoegsel: str = "O") -> list[dict]:
    """50 ware en 50 onware zinnen over de vastgestelde feiten die nog nooit gevraagd zijn, met een vast zaad."""
    vrij = [s for s in fundament if s["id"] not in gevraagd and s["tekst"] not in uitgesloten and s.get("taal") == "en"]
    uit = []
    for label in ("waar", "onwaar"):
        groep = sorted((s for s in vrij if s["label"] == label), key=lambda s: s["id"])
        random.Random(f"{zaad}-{label}").shuffle(groep)
        uit += [{"id": f"{voorvoegsel}:{s['id']}", "oud_id": s["id"], "set": voorvoegsel, "deel": s["deel"], "label": label,
                 "tekst": s["tekst"], "modellen": ["sonnet"], "kaal": ["kaal"]} for s in groep[:N_O]]
    return uit


def _beide(antwoorden: dict[tuple[str, str], str], i: str) -> bool | None:
    if not all((i, k) in antwoorden for k in vl.SLEUTELS):
        return None
    return all(antwoorden[(i, k)] == vl.DUIDELIJK for k in vl.SLEUTELS)


def bewaking(alles: list[dict], antwoorden: dict, labels: dict[str, str], waar_in_rondes: int) -> dict:
    """De valse alarmen: ware berichten waar beide vragen "clearly false" zeggen. Elk moet gelezen zijn."""
    uit = {"ware berichten gevraagd": 0, "beide": 0, "vals alarm": 0, "set fout": 0}
    for s in alles:
        if s["label"] != "waar" or _beide(antwoorden, s["id"]) is None:
            continue
        uit["ware berichten gevraagd"] += 1
        if _beide(antwoorden, s["id"]):
            uit["beide"] += 1
            if s["id"] not in labels:
                raise Weigering(f"{s['id']} is een vals alarm zonder label in {LABELS.name}; eerst lezen")
            uit["vals alarm"] += labels[s["id"]] == "vals"
            uit["set fout"] += labels[s["id"]] == "set fout"
    uit["hoogstens"] = waar_in_rondes // vl.PER_VALS_ALARM
    uit["door"] = uit["vals alarm"] <= waar_in_rondes / vl.PER_VALS_ALARM
    return uit


def klasse(alles: list[dict], antwoorden: dict, labels: dict[str, str]) -> dict:
    """De ijking van (*klopt niet*, *algemene kennis*): elk waar of onwaar bericht waar beide vragen "clearly false"
    zeggen. Een waar bericht dat bij het lezen een fout in de set bleek, telt als onwaar."""
    waar = n = 0
    for s in alles:
        if s["label"] in ("waar", "onwaar") and _beide(antwoorden, s["id"]):
            n += 1
            waar += s["label"] == "waar" and labels.get(s["id"]) != "set fout"
    lo, hi = meter.wilson(waar, n)
    s = meter.stand(waar, n, KLASSE[1], KLASSE[0])
    return {"oordeel": KLASSE[0], "laag": KLASSE[1], "n": n, "waar": waar, "aandeel waar": round(waar / n, 4) if n else None,
            "interval": [round(lo, 4), round(hi, 4)], "stand": s, "woorden": meter.STANDEN[s]}


def vloerrood(stukken: list[dict], factiz: dict) -> dict:
    """Hoe vaak de vloerstap iets rood maakte, en of er een ware zin bij was (eis 4 van PLAN #32.0n)."""
    rood = [s for s in stukken if s["id"] in factiz and factiz[s["id"]]["kleur"] == "rood"
            and "algemene kennis" in (factiz[s["id"]].get("regels") or [])]
    waar = sum(s["label"] == "waar" for s in rood)
    return {"vloerstap rood": len(rood), "waar rood door de vloerstap": waar, "door": waar == 0}


def _goed(s: dict, u: dict, labels: dict, wie: str) -> bool:
    goed = "rood" if s["label"] == "onwaar" else "groen"
    if u["kleur"] == goed:
        return True
    if wie == "factiz" and s["label"] == "onwaar" and u["oordeel"] == "klopt grotendeels":
        sleutel = (s["id"], "markering")
        if sleutel not in labels:
            raise Weigering(f"{sleutel}: klopt grotendeels zonder label in {LABELS.name}; eerst lezen")
        return labels[sleutel] == "juist"
    return False


def tel_o(stukken: list[dict], factiz: dict, kaal: dict, labels: dict) -> dict:
    """O met de eisen van PLAN #32.0m: goed is rood bij onwaar en groen bij waar, en bij een onware zin ook *klopt
    grotendeels* met het juiste detail gemarkeerd."""
    from doublecheck.modelpoort import mcnemar

    uit = {"n": 0, "factiz goed": 0, "kaal goed": 0, "alleen kaal": 0, "alleen factiz": 0,
           "factiz onzeker of let op zonder bron waar kaal goed is met bron": 0, "vloerstap rood": 0}
    for s in stukken:
        f, k = factiz.get(s["id"]), kaal.get(s["id"])
        if f is None or k is None:
            continue
        gf, gk = _goed(s, f, labels, "factiz"), _goed(s, k, labels, "kaal")
        uit["n"] += 1
        uit["factiz goed"] += gf
        uit["kaal goed"] += gk
        uit["alleen kaal"] += gk and not gf
        uit["alleen factiz"] += gf and not gk
        uit["factiz onzeker of let op zonder bron waar kaal goed is met bron"] += (
            f["oordeel"] in ("onzeker", "let op") and not f["bronnen"] and gk and bool(k["bronnen"]))
        uit["vloerstap rood"] += "algemene kennis" in (f.get("regels") or [])
    p = mcnemar(uit["alleen kaal"], uit["alleen factiz"])
    uit["McNemar p"] = round(p, 4)
    uit["eisen"] = {
        "minstens 95% goed": uit["factiz goed"] >= 0.95 * uit["n"],
        "niet aantoonbaar slechter dan het kale model":
            uit["kaal goed"] - uit["factiz goed"] <= 2 and (uit["alleen kaal"] <= uit["alleen factiz"] or p >= 0.05),
        "nooit onzeker of let op zonder bron waar het kale model het goed heeft met bron":
            uit["factiz onzeker of let op zonder bron waar kaal goed is met bron"] == 0}
    return uit


# --- de bestanden en de CLI ---------------------------------------------------------------------

def lees_labels() -> dict:
    return json.loads(LABELS.read_text(encoding="utf-8")) if LABELS.exists() else {}


def _config_aan(versie: str = "vloer-v1"):  # pragma: no cover - op config.toml
    from doublecheck.config import load_config

    config = load_config(None)
    return dataclasses.replace(config, berichtcontrole=dataclasses.replace(config.berichtcontrole, vloer=versie))


def maak_o2() -> None:  # pragma: no cover - met het model en de database
    """O2 (PLAN #32.0n): 100 nieuwe zinnen, ook niet uit O, voorbereid zoals in het product."""
    from doublecheck import berichtcontrole as bc
    from doublecheck.config import load_config
    from doublecheck.storage import connect

    config = load_config(None)
    conn = connect("doublecheck.db")
    fundament = bt._jsonl(WORTEL / "data" / "fundament" / "set.jsonl")
    gevraagd = {r["id"] for r in bt._jsonl(WORTEL / "data" / "fundament" / "antwoorden.jsonl")}
    gevraagd |= {s["oud_id"] for s in bt._jsonl(O_MAP / "set.jsonl")}
    uitgesloten = {s["tekst"] for s in bt._jsonl(WORTEL / "data" / "gebruikerstoets" / "set.jsonl")}
    uitgesloten |= {s["tekst"] for s in bt._jsonl(WORTEL / "data" / "modelpoort" / "r.jsonl") if s.get("set") == "R3"}
    o2 = []
    for s in kies_o(fundament, gevraagd, uitgesloten, zaad=ZAAD_O2, voorvoegsel="O2"):
        v_ = bc.voorbereiden(conn, config, s["tekst"])
        o2.append({**s, "helft": "toets", "geheugen": v_["geheugen"], "kandidaten": v_["kandidaten"], "datum": None,
                   "eigen": []})
    O2_MAP.mkdir(parents=True, exist_ok=True)
    bt._schrijf(O2_MAP / "set.jsonl", o2)
    print(f"O2: {len(o2)} zinnen, {sum(s['label'] == 'waar' for s in o2)} waar")


def vloerantwoorden() -> dict[tuple[str, str], str]:
    return {(r["id"], r["sleutel"]): r["oordeel"] for r in bt._jsonl(UIT / "antwoorden.jsonl")}


def tabel_met_klasse(config, alles, antwoorden, labels) -> tuple[dict, dict]:  # pragma: no cover - met de ijking
    from doublecheck import berichtcontrole as bc

    k = klasse(alles, antwoorden, labels.get("valse alarmen", {}))
    return {**bc.ijktabel(config), KLASSE: k}, k


def vloerrijen(ids_per_set: dict[str, str], antwoorden: dict) -> list[dict]:
    """De vloervragen uit de ijkronde als rijen voor de stappen van de modelpoort (zonder model, zoals de
    feitenstap): `ids_per_set` van het id in O of P9 naar het id in de ijkronde."""
    rijen = []
    for eigen, ijk in ids_per_set.items():
        for k in vl.SLEUTELS:
            if (ijk, k) in antwoorden:
                rijen.append({"soort": f"vloer {k}", "model": None, "id": eigen, "oordeel": antwoorden[(ijk, k)],
                              "kosten": 0.0})
    return rijen


def maak_set() -> None:  # pragma: no cover - met het model en de database
    from doublecheck import berichtcontrole as bc
    from doublecheck.config import load_config
    from doublecheck.storage import connect

    config = load_config(None)
    conn = connect("doublecheck.db")
    rondes, ware = vl.rondes(alle=True)
    fundament = bt._jsonl(WORTEL / "data" / "fundament" / "set.jsonl")
    gevraagd = {r["id"] for r in bt._jsonl(WORTEL / "data" / "fundament" / "antwoorden.jsonl")}
    uitgesloten = {s["tekst"] for s in bt._jsonl(WORTEL / "data" / "gebruikerstoets" / "set.jsonl")}
    r3 = [s for s in bt._jsonl(WORTEL / "data" / "modelpoort" / "r.jsonl") if s.get("set") == "R3"]
    uitgesloten |= {s["tekst"] for s in r3}
    o = []
    for s in kies_o(fundament, gevraagd, uitgesloten):
        v_ = bc.voorbereiden(conn, config, s["tekst"])
        o.append({**s, "helft": "toets", "geheugen": v_["geheugen"], "kandidaten": v_["kandidaten"], "datum": None,
                  "eigen": []})
    O_MAP.mkdir(parents=True, exist_ok=True)
    bt._schrijf(O_MAP / "set.jsonl", o)
    alles = rondes + [{"bron": "O", "id": s["id"], "tekst": s["tekst"], "label": s["label"], "helft": "toets"} for s in o] \
        + [{"bron": "R3", "id": f"R3:{s['id']}", "tekst": s["tekst"], "label": s["label"], "helft": "toets"} for s in r3]
    bt._schrijf(UIT / "alles.jsonl", alles)
    (UIT / "meta.json").write_text(json.dumps({"ware berichten in de rondes": ware}), encoding="utf-8")
    print(f"alles: {len(alles)} berichten ({ware} ware in de rondes); O: {len(o)}; R3: {len(r3)}")


def uitgegeven() -> float:
    from doublecheck.modelpoort import uitgegeven_in

    return uitgegeven_in(UIT) + uitgegeven_in(O_MAP) + uitgegeven_in(R3_MAP) \
        + sum(r["kosten"] for r in bt._jsonl(UIT / "wachttijd.jsonl"))


def sets() -> dict[str, tuple[list[dict], Path, list[dict], dict[str, str]]]:  # pragma: no cover - op de bestanden
    """Per set de berichten, de map voor nieuwe vragen, de antwoorden van eerder, en hoe de ids naar de ijkronde
    wijzen. R3 hergebruikt de antwoorden van P9; alleen wat de vloerstap nieuw nodig maakt (een vormvraag) komt erbij."""
    o = bt._jsonl(O_MAP / "set.jsonl")
    r3 = [s for s in bt._jsonl(WORTEL / "data" / "modelpoort" / "r.jsonl") if s.get("set") == "R3"]
    p9 = [r for r in bt._jsonl(WORTEL / "data" / "modelpoort" / "antwoorden.jsonl") if r["id"].startswith("r3-")]
    o2 = bt._jsonl(O2_MAP / "set.jsonl")
    return {"O": (o, O_MAP, [], {s["id"]: s["id"] for s in o}),
            "R3": (r3, R3_MAP, p9, {s["id"]: f"R3:{s['id']}" for s in r3}),
            "O2": (o2, O2_MAP, [], {})}


def rijen_van(naam: str) -> list[dict]:  # pragma: no cover - op de bestanden
    stukken, map_, eerder, ids = sets()[naam]
    return eerder + bt._jsonl(map_ / "antwoorden.jsonl") + vloerrijen(ids, vloerantwoorden())


def main() -> None:  # pragma: no cover - CLI, met de Batch API
    import argparse

    parser = argparse.ArgumentParser(description="De ronde van de vloerstap (PLAN #32.0m)")
    parser.add_argument("deel", choices=("set", "vloer", "o", "o2", "wachttijd", "lezen", "tellen"))
    parser.add_argument("stap", nargs="?", default="")
    parser.add_argument("--proef", type=int, default=0)
    args = parser.parse_args()
    UIT.mkdir(parents=True, exist_ok=True)
    if args.deel == "set":
        maak_set()
        return
    if args.deel == "o2" and args.stap == "set":
        maak_o2()
        return
    import anthropic

    from doublecheck import modelpoort as mp
    from doublecheck.leraar import MODELLEN
    from doublecheck.varianten import laad_sleutel

    config = _config_aan()
    alles = bt._jsonl(UIT / "alles.jsonl")
    o = bt._jsonl(O_MAP / "set.jsonl")
    labels = lees_labels()
    antwoorden = vloerantwoorden()
    if args.deel in ("vloer", "o", "o2", "wachttijd"):
        laad_sleutel()
        client = anthropic.Anthropic()
    if args.deel == "vloer":
        batches = bt._jsonl(UIT / "batches.jsonl")
        per_bid = {f"{k}-{bt.batch_id(s['id'])}": (s, k) for s in alles for k in vl.SLEUTELS}
        if args.stap == "indienen":
            al = {i for b in batches for i in b["ids"]}
            keuze = alles[: args.proef] if args.proef else alles
            verzoeken = [{"custom_id": f"{k}-{bt.batch_id(s['id'])}", "params": vl.verzoek(s["tekst"], k, config)}
                         for s in keuze for k in vl.SLEUTELS if f"{k}-{bt.batch_id(s['id'])}" not in al]
            geschat = len(verzoeken) * vl.SCHATTING
            if not verzoeken or uitgegeven() + geschat > BUDGET:
                raise Weigering(f"{len(verzoeken)} vragen: ${uitgegeven():.2f} plus ${geschat:.2f} tegen ${BUDGET:.2f}")
            batch = client.messages.batches.create(requests=verzoeken)
            batches.append({"id": batch.id, "schatting": round(geschat, 4), "ids": [r["custom_id"] for r in verzoeken]})
            bt._schrijf(UIT / "batches.jsonl", batches)
            print(f"batch {batch.id}: {len(verzoeken)} vragen, geschat ${geschat:.2f}; samen ${uitgegeven():.2f}")
            return
        rijen = bt._jsonl(UIT / "antwoorden.jsonl")
        prijs = MODELLEN[vl.MODEL]
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
                s, k = per_bid[r.custom_id]
                tekst = "".join(getattr(x, "text", "") or "" for x in msg.content)
                rijen.append({"id": s["id"], "sleutel": k, "oordeel": vl.lees_oordeel(tekst), "tekst": tekst})
            b["werkelijk"] = round(kosten, 4)
        bt._schrijf(UIT / "antwoorden.jsonl", rijen)
        bt._schrijf(UIT / "batches.jsonl", batches)
        print(f"{len(rijen)} antwoorden; samen ${uitgegeven():.3f}")
        return
    tabel, k = tabel_met_klasse(config, alles, antwoorden, labels)
    if args.deel == "o2":
        v2 = _config_aan("vloer-v2")
        o2 = sets()["O2"][0]
        # Het kale model kostte in O $0,0054 per vraag; de schatting is het dubbele daarvan, niet de ruime $0,02.
        mp.SCHATTING_STAP = {**mp.SCHATTING_STAP, "kaal": 2 * KAAL_IN_O}
        if args.stap == "indienen":  # eerst de machine; het kale model na het ophalen, binnen de grens
            gedaan = {r["id"] for r in rijen_van("O2") if r["soort"] == "machine"}
            taken = [("machine", "sonnet", s) for s in o2] if not gedaan else [("kaal", None, s) for s in o2]
            mp.dien_in(client, taken, o2, rijen_van("O2"), v2, O2_MAP, BUDGET_O2)
        elif args.stap == "vervolg":
            mp.dien_in(client, mp.nodig(o2, rijen_van("O2"), tabel, v2), o2, rijen_van("O2"), v2, O2_MAP, BUDGET_O2)
        elif args.stap == "vergelijk":  # O en R3 met vloer-v2: alleen wat de ruimere regel nieuw nodig maakt
            for naam in ("O", "R3"):
                stukken, map_, _, _ = sets()[naam]
                mp.dien_in(client, mp.nodig(stukken, rijen_van(naam), tabel, v2), stukken, rijen_van(naam), v2, map_,
                           BUDGET - uitgegeven() + mp.uitgegeven_in(map_))
        elif args.stap == "ophalen":
            for naam, map_ in (("O2", O2_MAP), ("O", O_MAP), ("R3", R3_MAP)):
                mp.haal_op(client, sets()[naam][0], v2, map_)
        else:
            markeringen = {(i, "markering"): label for i, label in labels.get("markeringen", [])}
            uit = {}
            for naam in ("O2", "O", "R3"):
                stukken = sets()[naam][0]
                f = mp.uitkomsten("sonnet", stukken, rijen_van(naam), tabel, v2)
                kaal = {r["id"]: r for r in rijen_van(naam) if r["soort"] == "kaal"}
                uit[naam] = {**tel_o(stukken, f, kaal, markeringen), **vloerrood(stukken, f),
                             "uitkomsten": len(f)}
            uit["eisen"] = {f"{i} {naam}": w for i, (naam, w) in enumerate(uit["O2"]["eisen"].items(), 1)}
            uit["eisen"]["4 geen ware zin rood door de vloerstap"] = uit["O2"]["door"]
            uit["uitgegeven O2"] = round(mp.uitgegeven_in(O2_MAP), 3)
            print(json.dumps(uit, ensure_ascii=False, indent=1))
        return
    if args.deel == "o":
        if args.stap == "indienen":
            taken = [("machine", "sonnet", s) for s in o] + [("kaal", None, s) for s in o]
            mp.dien_in(client, taken, o, rijen_van("O"), config, O_MAP, BUDGET - uitgegeven() + mp.uitgegeven_in(O_MAP))
            return
        for naam, (stukken, map_, _, _) in sets().items():
            map_.mkdir(parents=True, exist_ok=True)
            if args.stap == "vervolg":
                mp.dien_in(client, mp.nodig(stukken, rijen_van(naam), tabel, config), stukken, rijen_van(naam), config,
                           map_, BUDGET - uitgegeven() + mp.uitgegeven_in(map_))
            else:
                mp.haal_op(client, stukken, config, map_)
        return
    if args.deel == "wachttijd":
        import time

        from doublecheck import berichtcontrole as bc

        if uitgegeven() + 0.02 > BUDGET:
            raise Weigering("boven de grens")
        with (UIT / "wachttijd.jsonl").open("a", encoding="utf-8") as fh:
            for s in o[:N_WACHTTIJD]:
                begin = time.perf_counter()
                ja, kosten = bc.vloer_vragen(s["tekst"], client, config)
                fh.write(json.dumps({"id": s["id"], "seconden": round(time.perf_counter() - begin, 2), "ja": ja,
                                     "kosten": round(kosten, 6)}) + "\n")
        tijden = sorted(r["seconden"] for r in bt._jsonl(UIT / "wachttijd.jsonl"))
        print(f"{len(tijden)} keer: mediaan {tijden[len(tijden) // 2]:.1f} s, hoogste {tijden[-1]:.1f} s")
        return
    factiz = mp.uitkomsten("sonnet", o, rijen_van("O"), tabel, config)
    kaal = {r["id"]: r for r in rijen_van("O") if r["soort"] == "kaal"}
    r3 = sets()["R3"][0]
    r3_factiz = mp.uitkomsten("sonnet", r3, rijen_van("R3"), tabel, config)
    r3_kaal = {r["id"]: r for r in rijen_van("R3") if r["soort"] == "kaal"}
    if args.deel == "lezen":
        vals = labels.get("valse alarmen", {})
        tekst = {s["id"]: s for s in alles}
        for s in alles:
            if s["label"] == "waar" and _beide(antwoorden, s["id"]) and s["id"] not in vals:
                print(f"=== vals alarm? {s['id']} [{s['bron']}]\n{s['tekst'][:500]}")
        for naam, stukken, uitkomst in (("O", o, factiz), ("R3", r3, r3_factiz)):
            for s in stukken:
                u = uitkomst.get(s["id"])
                if u and s["label"] == "onwaar" and u["oordeel"] == "klopt grotendeels" \
                        and (s["id"], "markering") not in {tuple(x) for x in labels.get("markeringen", [])}:
                    print(f"=== markering {naam} {s['id']}\n{s['tekst']}\n  -> {u.get('correcties')}")
        del tekst
        return
    meta = json.loads((UIT / "meta.json").read_text(encoding="utf-8"))
    markeringen = {(i, "markering"): label for i, label in labels.get("markeringen", [])}
    uit = {"bewaking": bewaking([s for s in alles if s["bron"] not in ("O", "R3")], antwoorden,
                                labels.get("valse alarmen", {}), meta["ware berichten in de rondes"]),
           "ijking": k, "O": tel_o(o, factiz, kaal, markeringen),
           "R3 opnieuw": tel_o(r3, r3_factiz, r3_kaal, markeringen),
           "wachttijd": sorted(r["seconden"] for r in bt._jsonl(UIT / "wachttijd.jsonl")),
           "uitgegeven": round(uitgegeven(), 3)}
    uit["eisen"] = {"1 hoogstens 1 vals alarm per 300 ware berichten": uit["bewaking"]["door"],
                    "2 de ijking draagt stand 3": k["stand"] == 3,
                    **{f"O {naam}": w for naam, w in uit["O"]["eisen"].items()}}
    print(json.dumps(uit, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
