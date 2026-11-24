"""De feitenbasis, eerst als meetlat (B34, PLAN #30.1b).

Een feit krijgt het oormerk *vastgesteld feit* niet op ons gezag, maar met een
openbare regel over bronnen: minstens vier onafhankelijke bronnen, van
minstens twee soorten. Onafhankelijk telt per uitgever, niet per editie: tien
taalversies van Wikipedia zijn één bron. En per overheid: instanties onder de
politieke leiding van dezelfde regering tellen samen als één stem; rechtbanken,
onafhankelijke onderzoeksraden, academies en musea op afstand tellen apart.
Alleen bronnen uit het register tellen, en het register zegt per bron de
soort, de uitgever, eventueel de overheid, en waarom hij betrouwbaar is
(redactieproces, correctiebeleid, onafhankelijkheid, wetenschappelijke
status).

Een feit is open zolang een bron uit het register het tegenspreekt. Een bron
die op een onderwerp van standpunt wisselde zonder nieuw bewijs te noemen,
terwijl de andere bronnen bij hun oordeel bleven, telt op dat onderwerp niet
mee, niet voor en niet tegen; het register noemt dat met datum en reden
(B34, aangevuld 2026-10-17).

Kwaliteitskranten van naam, niet onder staatstoezicht, zijn een eigen soort:
*journalistiek*. Omdat elk feit twee soorten nodig heeft, krijgt geen feit een
oormerk op kranten alleen; kranten van dezelfde mediagroep zijn één stem.

    doublecheck/feiten/bronnen.json   het register van basisbronnen
    doublecheck/feiten/kern.json      de kern: feiten met hun bronnen en oormerk

De eerste toepassing is de meetlat (B33): elk feit gaat in meerdere
formuleringen en talen door het echte `/resolve`, als set N3 van de zeef. Een
`matched` met een rood oordeel of *omstreden* naast een vastgesteld feit is
vals alarm; *deels waar* en *onbewezen* staan er apart bij. Op de kern geldt
nultolerantie: `python -m doublecheck.feitenbasis kerncheck` noemt elk feit
dat rood kreeg, en zakt er één, dan gaat een release niet door.

    python -m doublecheck.feitenbasis controleren
    python -m doublecheck.feitenbasis kerncheck
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

WORTEL = Path(__file__).resolve().parent
REGISTER = WORTEL / "feiten" / "bronnen.json"
KERN = WORTEL / "feiten" / "kern.json"
PAREN = WORTEL.parent / "docs" / "steekproeven" / "30.1b-minimale-paren.json"
KERNCHECK = WORTEL.parent / "data" / "feitenbasis" / "kerncheck.json"

SOORTEN = ("naslagwerk", "wetenschap", "onderzoek", "statistiek", "journalistiek")
MIN_BRONNEN = 4
MIN_SOORTEN = 2
MIN_FORMULERINGEN = 3
MIN_TALEN = 2

# Wat naast een vastgesteld feit vals alarm is, en wat twijfel zaait maar apart
# staat (PLAN #30.1b, vooraf vastgelegd).
VALS_N3 = frozenset({"rood", "omstreden"})
TWIJFEL_N3 = frozenset({"deels-waar", "onbewezen"})
_KLASSE = {"onwaar": "rood", "misleidend": "rood", "onwaar-of-misleidend": "rood", "omstreden": "omstreden",
           "deels-waar": "deels-waar", "onbewezen": "onbewezen", "waar": "waar"}


def lees_register(pad: Path = REGISTER) -> dict[str, dict]:
    return {b["id"]: b for b in json.loads(Path(pad).read_text(encoding="utf-8"))["bronnen"]}


def lees_kern(pad: Path = KERN) -> list[dict]:
    return json.loads(Path(pad).read_text(encoding="utf-8"))["feiten"]


def stem(bron: dict) -> str:
    """Wie er spreekt: de overheid als de bron onder een regering valt, de
    mediagroep als een krant een eigenaar deelt met een andere, anders de
    uitgever."""
    return bron.get("overheid") or bron.get("groep") or bron["uitgever"]


def telt_niet_mee(bron: dict, onderwerpen) -> bool:
    return any(n.get("onderwerp") in set(onderwerpen or ()) for n in bron.get("niet_meegeteld") or [])


def problemen_register(register: dict[str, dict]) -> list[str]:
    uit = []
    for bron_id, bron in register.items():
        if bron.get("soort") not in SOORTEN:
            uit.append(f"{bron_id}: soort {bron.get('soort')!r} is geen van {', '.join(SOORTEN)}")
        for veld in ("naam", "uitgever", "url", "waarom"):
            if not (bron.get(veld) or "").strip():
                uit.append(f"{bron_id}: {veld} ontbreekt")
        if "overheid" in bron and not (bron["overheid"] or "").strip():
            uit.append(f"{bron_id}: overheid is leeg")
        for n in bron.get("niet_meegeteld") or []:
            if not all((n.get(v) or "").strip() for v in ("onderwerp", "sinds", "reden")):
                uit.append(f"{bron_id}: niet_meegeteld zonder onderwerp, datum of reden")
    return uit


def problemen_kern(kern: list[dict], register: dict[str, dict]) -> list[str]:
    """Wat een feit van zijn oormerk afhoudt, volgens de regel van B34."""
    uit = []
    gezien = Counter(f.get("id") for f in kern)
    for feit in kern:
        naam = feit.get("id") or "?"
        if gezien[naam] > 1:
            uit.append(f"{naam}: id komt {gezien[naam]} keer voor")
        if not (feit.get("zin") or "").strip():
            uit.append(f"{naam}: zin ontbreekt")
        onderwerpen = feit.get("onderwerpen") or []
        geldig = []
        for b in feit.get("bronnen") or []:
            if b.get("bron") not in register:
                uit.append(f"{naam}: bron {b.get('bron')!r} staat niet in het register")
            elif not (b.get("vindplaats") or "").strip() or not (b.get("nagelopen") or "").strip():
                uit.append(f"{naam}: bron {b['bron']} zonder vindplaats of datum van nalopen")
            elif not telt_niet_mee(register[b["bron"]], onderwerpen):
                geldig.append(register[b["bron"]])
        stemmen = {stem(b) for b in geldig}
        soorten = {b["soort"] for b in geldig}
        if len(stemmen) < MIN_BRONNEN:
            uit.append(f"{naam}: {len(stemmen)} onafhankelijke bronnen, minstens {MIN_BRONNEN} nodig")
        for t in feit.get("tegenspraak") or []:
            bron = register.get(t.get("bron"))
            if bron is not None and not telt_niet_mee(bron, onderwerpen):
                uit.append(f"{naam}: open, {t['bron']} spreekt het tegen")
        if len(soorten) < MIN_SOORTEN:
            uit.append(f"{naam}: {len(soorten)} soorten bronnen, minstens {MIN_SOORTEN} nodig")
        oormerk = feit.get("oormerk") or {}
        if not (oormerk.get("door") and oormerk.get("datum")):
            uit.append(f"{naam}: oormerk zonder naam of datum")
        formuleringen = [f for f in feit.get("formuleringen") or [] if (f.get("tekst") or "").strip()]
        talen = {f.get("taal") for f in formuleringen}
        if len(formuleringen) < MIN_FORMULERINGEN or len(talen) < MIN_TALEN:
            uit.append(f"{naam}: {len(formuleringen)} formuleringen in {len(talen)} talen, minstens"
                       f" {MIN_FORMULERINGEN} in {MIN_TALEN}")
    return uit


def lees_paren(pad: Path = PAREN) -> list[dict]:
    """De beslissende minimale paren van Wikipedia, met hun leesproef."""
    if not Path(pad).exists():
        return []
    return json.loads(Path(pad).read_text(encoding="utf-8"))["paren"]


def n3_items(kern: list[dict], paren: list[dict] | None = None) -> list[dict]:
    """Elke formulering als stuk van N3, en de ware zin van elk beslist
    minimaal paar; alles van een feit in dezelfde helft, met de hash van de
    zeef. Alleen de formuleringen zijn de kern (nultolerantie, B33)."""
    from doublecheck.zeef import helft

    # Zodra er poortformuleringen zijn (#30.3b), meet de kern alleen die: de
    # andere voeden de feitenlaag, en wat de laag kent, zegt niets over de poort.
    poort = any(f.get("rol") == "poort" for feit in kern for f in feit["formuleringen"])
    uit = [{"sleutel": f"N3:{feit['id']}#{i}", "feit": feit["id"], "taal": f["taal"], "tekst": f["tekst"],
            "helft": helft(f"feit:{feit['id']}"), "bron": "kern"}
           for feit in kern for i, f in enumerate(feit["formuleringen"])
           if not poort or f.get("rol") == "poort"]
    uit += [{"sleutel": f"N3:paar:{p['revid']}", "feit": p["feit"], "taal": "en", "tekst": p["waar"],
             "helft": helft(f"feit:{p['feit']}"), "bron": "paar"} for p in paren or []]
    return uit


def laagformuleringen(kern: list[dict]) -> list[tuple[str, str]]:
    """(feit, tekst) van de formuleringen die de feitenlaag voeden (#30.3b)."""
    return [(feit["id"], f["tekst"]) for feit in kern for f in feit["formuleringen"]
            if f.get("rol", "laag") == "laag"]


def n3_uitkomst(antwoord: dict) -> str:
    """Wat een lezer naast het feit zou zien: bij `matched` de labelklasse van
    de checks, met het jongste oordeel voorop (B30), zoals Ask hem toont."""
    from doublecheck.verdicts import labelklasse_in_tijd

    categorie = antwoord.get("category")
    if categorie == "related":
        return "verwant"
    if categorie != "matched":
        return "niets"
    checks = (antwoord.get("evidence") or {}).get("checks") or []
    klasse, _ = labelklasse_in_tijd((c.get("verdict_normalized"), c.get("review_date")) for c in checks)
    return _KLASSE.get(klasse, "zonder-oordeel")


def kern_vingerafdruk(pad: Path = KERN) -> str:
    """Een hash van de kern: een kerncheck geldt alleen voor deze versie ervan."""
    import hashlib

    return hashlib.sha256(Path(pad).read_bytes()).hexdigest()


def motor_van(config) -> dict:
    """De motor waar een meting bij hoort: model, drempels, vraagvorm, en de
    rechter alleen als hij aan staat (dan blijven oudere metingen bij hun motor)."""
    import dataclasses

    motor = {"text_embedding": config.model_versions.text_embedding,
             "drempels": dataclasses.asdict(config.thresholds), "vraagvorm": config.vraagvorm.aan}
    if config.rechter.aan:
        motor["rechter"] = {"model": config.rechter.model, "diepte": config.rechter.diepte}
    if config.feiten.aan:  # de laag hangt aan de kern: een andere kern is een andere motor
        motor["feiten"] = {"kern": kern_vingerafdruk()}
    if config.artikel.per_zin:  # een artikel per zin (#30.11)
        motor["artikel"] = {"per_zin": True}
    if config.artikellezer.aan:  # de artikellezer (#30.11b)
        motor["artikellezer"] = {"model": config.artikellezer.model, "diepte": config.artikellezer.diepte}
    return motor


def kernpoort(uitslag: dict | None, motor: dict, kern: str) -> list[str]:
    """Waarom een release niet door mag (B33: nultolerantie op de kern); leeg
    als de kerncheck van deze motor en deze kern geen rood gaf."""
    if uitslag is None:
        return ["geen kerncheck; draai `python -m doublecheck.feitenbasis kerncheck`"]
    redenen = []
    if uitslag.get("motor") != motor:
        redenen.append("de kerncheck is met een andere motor gedaan dan die in config.toml")
    if uitslag.get("kern") != kern:
        redenen.append("de kern is veranderd sinds de kerncheck")
    if uitslag.get("rood"):
        redenen.append(f"{len(uitslag['rood'])} keer rood of omstreden naast een vastgesteld feit: "
                       + ", ".join(sorted({r['feit'] for r in uitslag['rood']})))
    return redenen


def lees_kerncheck(pad: Path = KERNCHECK) -> dict | None:
    return json.loads(Path(pad).read_text(encoding="utf-8")) if Path(pad).exists() else None


def door_resolver(items: list[dict]) -> list[dict]:  # pragma: no cover - het echte pad, met het model
    from fastapi.testclient import TestClient

    from doublecheck import api
    from doublecheck.ruwetest import antwoord_of_fout

    api.limiter.enabled = False
    client = TestClient(api.app)
    uit = []
    for item in items:
        antwoord = antwoord_of_fout(client.post("/resolve", json={"text": item["tekst"]}))
        uit.append({"set": "N3", "sleutel": item["sleutel"], "feit": item["feit"], "helft": item["helft"],
                    "taal": item["taal"], "bron": item.get("bron", "kern"), "uitkomst": n3_uitkomst(antwoord),
                    "kandidaat": (antwoord.get("claim") or {}).get("id"), "gelijkenis": antwoord.get("similarity")})
    return uit


def main() -> None:  # pragma: no cover
    import argparse

    parser = argparse.ArgumentParser(description="De feitenbasis (B34, PLAN #30.1b)")
    parser.add_argument("stap", choices=("controleren", "kerncheck"))
    parser.add_argument("--threads", type=int, default=2)
    parser.add_argument("--config", help="kerncheck: een andere config dan config.toml (de rechter aan, #30.3)")
    parser.add_argument("--uit", help="kerncheck met --config: waarheen; nooit het bestand van de releasepoort")
    args = parser.parse_args()
    if args.config and (not args.uit or Path(args.uit).resolve() == KERNCHECK.resolve()):
        raise SystemExit("een kerncheck met een andere config schrijft naar een eigen --uit, niet naar de releasepoort")
    register, kern = lees_register(), lees_kern()
    problemen = problemen_register(register) + problemen_kern(kern, register)
    if args.stap == "controleren":
        print(f"{len(register)} bronnen in het register, {len(kern)} feiten in de kern")
        for p in problemen:
            print("  ", p)
        raise SystemExit(1 if problemen else 0)
    if problemen:
        raise SystemExit(f"de kern volgt de regel van B34 niet ({len(problemen)} problemen); eerst `controleren`")
    import torch

    torch.set_num_threads(args.threads)
    from datetime import date

    from doublecheck.config import load_config

    config = load_config(args.config)
    if args.config:
        from doublecheck import api

        api.app.dependency_overrides[api.get_config] = lambda: config
    uitpad = Path(args.uit) if args.uit else KERNCHECK
    regels = door_resolver(n3_items(kern))
    rood = [r for r in regels if r["uitkomst"] in VALS_N3]
    uitpad.parent.mkdir(parents=True, exist_ok=True)
    uitpad.write_text(json.dumps({"motor": motor_van(config), "kern": kern_vingerafdruk(),
                                     "datum": date.today().isoformat(), "formuleringen": len(regels),
                                     "rood": [{k: r[k] for k in ("feit", "taal", "kandidaat", "gelijkenis", "uitkomst")}
                                              for r in rood]}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"kern: {len(kern)} feiten, {len(regels)} formuleringen; rood of omstreden {len(rood)},"
          f" twijfel {sum(r['uitkomst'] in TWIJFEL_N3 for r in regels)}")
    for r in rood:
        print(f"  {r['feit']} [{r['taal']}] -> {r['kandidaat']} ({r['gelijkenis']}): {r['uitkomst']}")
    raise SystemExit(1 if rood else 0)


if __name__ == "__main__":
    main()
