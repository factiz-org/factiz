"""Eén routine per week voor een nieuwe uitgave (PLAN #35.2; PO 2026-11-17: "Ok, nee dan is wekelijkse verversen prima",
"Yes, build it").

    python -m doublecheck.verversen [--toch] [--wacht M] [--grens D]
    python -m doublecheck.verversen stand

Begint als het lab bijgewerkt is uit een stand van de feed die nog geen uitgave heeft: de laatste regel
`database bijgewerkt uit <feed>: uitgang 0` in `data/vooruitblik/ophalen.log` (de dagelijkse taak van 4:17). Dan:

0. `euvsdisinfo`: de nieuwe gevallen van EUvsDisinfo (vanaf `euvsdisinfo.VANAF`) van hun server in het lab (PLAN #35.3);
1. `bouwen`: de nieuwe uitgave (`publiceren bouwen`), en wat er nieuw is tegenover de uitgave op factiz.org;
2. de verrijkingen, elk alleen voor wat er nog niet is en elk met haar eigen poort (zie `BATCHSTAPPEN`), met de punten van
   Waarom het niet klopt voor de nieuwe gevallen van EUvsDisinfo;
3. `herbouwen`: dezelfde uitgave opnieuw, nu met de verrijkingen;
4. `voorbereiden`: de SQL voor D1 en het geheugen van de Worker (`uitrol voorbereiden`);
5. een melding aan de PO, en `data/verversen/<uitgave>.md` met wat erin zit, wat het kostte en hoe het live gaat.

Live gaat alleen met een ja van de PO (`python -m doublecheck.uitrol live <uitgave> --akkoord '…'`); deze routine raakt
het account van Cloudflare nooit. Na elke stap staat de stand in `data/verversen/<uitgave>.json`; een nieuwe aanroep begint
bij de stap die misging, dus nooit twee keer betalen. De grens per week (`GRENS`) telt de kosten van alle stappen samen.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Callable

WORTEL = Path(__file__).resolve().parent.parent
MAP = WORTEL / "data" / "verversen"
OPHAALLOG = WORTEL / "data" / "vooruitblik" / "ophalen.log"
GRENS = 10.00           # dollar per uitgave, alle stappen samen; verwacht $1 tot $4 (PLAN #35.2)

_BIJGEWERKT = re.compile(r"database bijgewerkt uit (feed-[0-9T-]+\.json): uitgang (\d+)\s*$")


class Weigering(Exception):
    """Een stap mag zo niet, of ging mis; de stand blijft, een volgende aanroep begint daar."""


class NietsNieuw(Exception):
    """De nieuwe stand van de feed bracht niets wat factiz.org nog niet heeft: geen uitgave nodig."""


def laatste_bijwerking(log: str) -> str | None:
    """De stand van de feed waaruit het lab het laatst zonder fout bijgewerkt is, of niets."""
    laatste = None
    for regel in log.splitlines():
        m = _BIJGEWERKT.search(regel)
        if m and m.group(2) == "0":
            laatste = m.group(1)
    return laatste


def moet_verversen(feed: str | None, vorige: dict, toch: bool = False) -> bool:
    """Of er een nieuwe uitgave moet komen: het lab heeft een stand die de vorige uitgave van de routine nog niet had."""
    if feed is None:
        return False
    return toch or vorige.get("feed") != feed


def verschil(live: set[str], nieuw: set[str]) -> tuple[list[str], list[str]]:
    """De pagina's die de nieuwe uitgave heeft en die op factiz.org niet, en andersom (een check die verdween)."""
    return sorted(nieuw - live), sorted(live - nieuw)


def voer_uit(stappen: dict[str, Callable[[dict], dict]], stand_pad: Path, *, release: str, feed: str, grens: float,
             schattingen: dict[str, float] | None = None, tot: str | None = None) -> dict:
    """De stappen in hun volgorde; na elke stap de stand op schijf, en wat al klaar is gaat niet nog eens. Een stap krijgt
    de stand met wat de stappen ervoor vonden en geeft terug wat ze deed, met `kosten` in dollar als ze iets kostte. Vóór
    een stap met een schatting: past ze niet meer binnen de grens, dan stopt de routine (de stand blijft)."""
    stand = (json.loads(stand_pad.read_text(encoding="utf-8")) if stand_pad.exists()
             else {"release": release, "feed": feed, "stappen": {}, "kosten": 0.0})
    if stand.get("release") != release:
        raise Weigering(f"{stand_pad} hoort bij de uitgave {stand.get('release')}, niet bij {release}")
    stand_pad.parent.mkdir(parents=True, exist_ok=True)
    for naam, stap in stappen.items():
        if naam in stand["stappen"]:
            continue
        schatting = (schattingen or {}).get(naam, 0.0)
        if stand["kosten"] + schatting > grens:
            raise Weigering(f"{naam} past niet binnen de grens: al ${stand['kosten']:.2f}, geschat ${schatting:.2f}, "
                            f"grens ${grens:.2f}")
        uit = stap(stand) or {}
        stand["stappen"][naam] = uit
        stand["kosten"] = round(stand["kosten"] + float(uit.get("kosten") or 0.0), 4)
        stand_pad.write_text(json.dumps(stand, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        if naam == tot:             # tot en met deze stap, bijvoorbeeld eerst alleen bouwen ($0) om te zien wat nieuw is
            break
    return stand


def melding(stand: dict, *, live: str, grens: float, dekking: dict | None = None) -> str:
    """Wat de PO leest: wat er nieuw is tegenover factiz.org, per taal, wat de nieuwe pagina's kregen, wat elke stap
    kostte, wat op een mens wacht, en het commando om live te gaan."""
    bouwen = stand["stappen"].get("bouwen", {})
    per_taal = ", ".join(f"{t} {n}" for t, n in sorted((bouwen.get("per_taal") or {}).items(), key=lambda x: (-x[1], x[0])))
    regels = [f"# Uitgave {stand['release']}", "",
              f"Uit de feed {stand['feed']}. Tegenover {live} op factiz.org: {bouwen.get('nieuw', 0)} nieuwe factchecks"
              + (f" ({per_taal})" if per_taal else "") + f", {bouwen.get('weg', 0)} niet meer in de uitgave.", "",
              f"Kosten: ${stand['kosten']:.2f} van de grens van ${grens:.2f}.", ""]
    if dekking:
        n = dekking["paginas"]
        talen = ", ".join(f"{t} {k}" for t, k in sorted(dekking["vertalingen"].items(), key=lambda x: (-x[1], x[0])))
        regels += ["## Wat de nieuwe factchecks kregen", "",
                   f"- een thema: {dekking['thema']} van {n}; een land: {dekking['land']} van {n}",
                   f"- een of meer namen: {dekking['namen']} van {n}",
                   f"- vertalingen op de site: {talen or 'geen'} (een taal die haar leesproef niet haalde, blijft uit, "
                   "zoals op factiz.org)",
                   "- niet elke week: taallabels, hoofdletters, oordelen, Lijkt op en Ook gecheckt door (PLAN #35.2a)", ""]
    regels += ["## De stappen", ""]
    wacht = []
    for naam, uit in stand["stappen"].items():
        if naam == "bouwen":
            continue
        regels.append(f"- {naam}: " + (f"${uit['kosten']:.2f}" if uit.get("kosten") else "klaar"))
        if uit.get("wacht"):
            wacht.append(f"- {naam}: {uit['wacht']}")
    if wacht:
        regels += ["", "## Wacht op een mens", "", *wacht]
    regels += ["", "## Live", "", "Alleen met een ja van de PO:", "",
               f"    python -m doublecheck.uitrol live {stand['release']} --akkoord '<datum>, PO: \"<haar woorden>\"'"]
    return "\n".join(regels) + "\n"


def lab_bezig(log: str) -> bool:
    """Of het lab nu bijgewerkt wordt: de laatste regel over een stand is een nieuwe stand zonder `database bijgewerkt`
    erna. Dan niet bouwen uit een lab dat half geschreven is."""
    for regel in reversed([r for r in log.splitlines() if r.strip()]):
        if _BIJGEWERKT.search(regel):
            return False
        if " nieuwe stand feed-" in regel or " inhalen " in regel:
            return True
    return False


# --- de stappen zelf -------------------------------------------------------------------------------------------------

# De verrijkingen per week, elk alleen voor wat er nog niet is (PLAN #35.2). Bewust niet elke week: de taallabels, de
# hoofdletters, de oordelen, Lijkt op en Ook gecheckt door; hun leesproef wordt opnieuw getrokken uit alle antwoorden, dus
# één nieuw antwoord sluit hun poort en haalt de verrijking uit de hele uitgave. Dat vraagt eerst een vaste steekproef.
BATCHSTAPPEN = {                    # stap: (module, opdracht indienen, opdracht ophalen, batchbestand)
    "themas": ("doublecheck.themas", ["vol", "indienen"], ["vol", "ophalen"], WORTEL / "data" / "themas" / "vol-batches.jsonl"),
    "namen-lezen": ("doublecheck.namen", ["vol", "indienen"], ["vol", "ophalen"], WORTEL / "data" / "namen" / "vol-batches.jsonl"),
    "namen-kiezen": ("doublecheck.namen", ["kiezen", "indienen"], ["kiezen", "ophalen"],
                     WORTEL / "data" / "namen" / "keuze-batches.jsonl"),
    "vertalingen": ("doublecheck.weergave", ["indienen"], ["ophalen"], WORTEL / "data" / "vertalingen" / "batches.jsonl"),
    # #34.2bw, maatregel 2: een nieuwe bewering die niemand las, blijft buiten zoekmachines tot Haiku haar las
    "privepersonen": ("doublecheck.privepersonen", ["indienen"], ["ophalen"], WORTEL / "data" / "privepersonen" / "batches.jsonl"),
    # #34.2ch: wat particulier is, gaat uit de uitgave; een nieuwe bewering die niemand las, blijft erin tot Haiku haar las
    "relevantie": ("doublecheck.relevantie", ["indienen"], ["ophalen"], WORTEL / "data" / "relevantie" / "batches.jsonl"),
    # #35.3: de punten van Waarom het niet klopt voor de nieuwe gevallen van EUvsDisinfo, dan de tweede lezing ervan
    "waarom": ("doublecheck.waarom", ["indienen"], ["ophalen"], WORTEL / "data" / "waarom" / "batches.jsonl"),
    "waarom-lezing": ("doublecheck.waarom", ["lezing-indienen"], ["lezing-ophalen"],
                      WORTEL / "data" / "waarom" / "lezing-batches.jsonl"),
}


def _jsonl(pad: Path) -> list[dict]:
    if not pad.exists():
        return []
    return [json.loads(r) for r in pad.read_text(encoding="utf-8").splitlines() if r.strip()]


def _draai(args: list[str], omgeving: dict | None = None) -> str:  # pragma: no cover - roept een programma aan
    import os
    import subprocess
    import sys

    uit = subprocess.run([sys.executable, "-m", *args], capture_output=True, text=True, cwd=WORTEL,
                         env={**os.environ, **(omgeving or {})})
    tekst = uit.stdout + uit.stderr
    if uit.returncode:
        raise Weigering(f"{' '.join(args[:3])} mislukte: {tekst.strip()[-600:]}")
    return tekst


def _laatste_regel(tekst: str) -> str:
    regels = [r.strip() for r in tekst.splitlines() if r.strip()]
    return regels[-1][:300] if regels else ""


def _paginas(bestand: Path) -> dict[str, str]:  # pragma: no cover - een bestand
    import sqlite3

    with sqlite3.connect(f"file:{bestand}?mode=ro", uri=True) as c:
        return dict(c.execute("SELECT nummer, taal FROM pagina"))


def _live() -> str:  # pragma: no cover - een bestand
    from doublecheck import uitrol

    return uitrol.lees_database((WORTEL / "site" / "wrangler.jsonc").read_text(encoding="utf-8"))[0].removeprefix("factiz-")


def maak_stappen(release: str, grens: float, wacht: int) -> dict[str, Callable[[dict], dict]]:  # pragma: no cover
    """De stappen van de routine voor deze uitgave, in hun volgorde."""
    bestand = WORTEL / "data" / "publicatie" / release / "publicatie.db"

    def bouwen(stand: dict) -> dict:
        _draai(["doublecheck.publiceren", "bouwen", "--release", release])
        live = _live()
        oud, nieuw_ = _paginas(WORTEL / "data" / "publicatie" / live / "publicatie.db"), _paginas(bestand)
        erbij, weg = verschil(set(oud), set(nieuw_))
        per_taal: dict[str, int] = {}
        for nr in erbij:
            per_taal[nieuw_[nr]] = per_taal.get(nieuw_[nr], 0) + 1
        if not erbij and not weg:
            raise NietsNieuw(f"niets nieuw tegenover {live}")
        return {"live": live, "nieuw": len(erbij), "weg": len(weg), "per_taal": per_taal}

    def batchstap(naam: str) -> Callable[[dict], dict]:
        module, indienen, ophalen, pad = BATCHSTAPPEN[naam]

        def f(stand: dict) -> dict:
            from doublecheck import routinegrens as rg

            omgeving = {"FACTIZ_ROUTINE": release, "FACTIZ_ROUTINE_RUIMTE": f"{grens - stand['kosten']:.4f}"}
            tekst = ""
            if not rg.kosten(_jsonl(pad), release)[1]:      # niets van deze uitgave onderweg: indienen wat ontbreekt
                tekst = _draai([module, *indienen], omgeving)
            if rg.kosten(_jsonl(pad), release)[1]:          # wat onderweg is, ophalen (de stap zelf wacht)
                tekst = _draai([module, *ophalen, "--wacht", str(wacht)], omgeving)
            kosten, lopend = rg.kosten(_jsonl(pad), release)
            if lopend:
                raise Weigering(f"{naam}: {lopend} batch(es) lopen nog na {wacht} minuten; een volgende aanroep gaat verder")
            return {"kosten": kosten, "tekst": _laatste_regel(tekst)}
        return f

    def gewoon(naam: str, args: list[str]) -> Callable[[dict], dict]:
        def f(stand: dict) -> dict:
            return {"tekst": _laatste_regel(_draai(args))}
        return f

    def euvsdisinfo(stand: dict) -> dict:
        tekst = _draai(["doublecheck.euvsdisinfo", "--server"])
        # de samenvatting van de ophaler, niet de voortgangsbalk van het model die erna op stderr komt
        regel = next((r.strip() for r in reversed(tekst.splitlines()) if r.startswith("EUvsDisinfo:")), "")
        return {"tekst": regel[:300] or _laatste_regel(tekst)}

    def herbouwen(stand: dict) -> dict:
        return {"tekst": _laatste_regel(_draai(["doublecheck.publiceren", "bouwen", "--release", release]))}

    def voorbereiden(stand: dict) -> dict:
        uit = _draai(["doublecheck.uitrol", "voorbereiden", "--release", release])
        regel = next((r.strip() for r in uit.splitlines() if "nakijken:" in r), "")
        return {"nakijken": regel.removeprefix("nakijken:").strip() or "in orde"}

    return {
        "euvsdisinfo": euvsdisinfo,
        "bouwen": bouwen,
        "themas": batchstap("themas"),
        "namen-lezen": batchstap("namen-lezen"),
        "namen-zoeken": gewoon("namen-zoeken", ["doublecheck.namen", "zoeken"]),
        "namen-kiezen": batchstap("namen-kiezen"),
        "namen-kenmerken": gewoon("namen-kenmerken", ["doublecheck.namen", "kenmerken"]),
        "vertalingen": batchstap("vertalingen"),
        "privepersonen": batchstap("privepersonen"),
        "relevantie": batchstap("relevantie"),
        "relevantie-tweede": gewoon("relevantie-tweede", ["doublecheck.relevantie", "tweede"]),
        "waarom": batchstap("waarom"),
        "waarom-lezing": batchstap("waarom-lezing"),
        "herbouwen": herbouwen,
        "namen-samenstellen": gewoon("namen-samenstellen", ["doublecheck.namen", "samenstellen"]),
        "herbouwen-namen": herbouwen,
        "voorbereiden": voorbereiden,
    }


def _dekking(release: str, live: str) -> dict:  # pragma: no cover - bestanden
    """Wat de pagina's die factiz.org nog niet heeft in de nieuwe uitgave kregen: thema, land, namen, vertalingen."""
    import sqlite3

    pub = WORTEL / "data" / "publicatie"
    with sqlite3.connect(f"file:{pub / release / 'publicatie.db'}?mode=ro", uri=True) as c:
        c.execute("ATTACH DATABASE ? AS live", (f"file:{pub / live / 'publicatie.db'}?mode=ro",))
        nieuw = "SELECT nummer FROM main.pagina WHERE nummer NOT IN (SELECT nummer FROM live.pagina)"
        een = lambda sql: c.execute(sql).fetchone()[0]
        return {"paginas": een(f"SELECT COUNT(*) FROM ({nieuw})"),
                "thema": een(f"SELECT COUNT(*) FROM main.pagina WHERE nummer IN ({nieuw}) AND COALESCE(thema, '') <> ''"),
                "land": een(f"SELECT COUNT(*) FROM main.pagina WHERE nummer IN ({nieuw}) AND COALESCE(land, '') <> ''"),
                "namen": een(f"SELECT COUNT(DISTINCT pagina) FROM main.pagina_naam WHERE pagina IN ({nieuw})"),
                "vertalingen": dict(c.execute(f"SELECT taal, COUNT(*) FROM main.vertaling WHERE pagina IN ({nieuw}) "
                                              "GROUP BY taal"))}


def _rapport(stand: dict, grens: float) -> str:  # pragma: no cover - bestanden
    live = stand["stappen"]["bouwen"]["live"]
    tekst = melding(stand, live=live, grens=grens, dekking=_dekking(stand["release"], live))
    (MAP / f"{stand['release']}.md").write_text(tekst, encoding="utf-8")
    return tekst


def _melding_mac(tekst: str) -> None:  # pragma: no cover - alleen op een Mac
    import subprocess
    import sys

    if sys.platform == "darwin":
        subprocess.run(["osascript", "-e", f"display notification {json.dumps(tekst[:200])} with title \"Factiz\""],
                       check=False)


def main() -> None:  # pragma: no cover - CLI
    import argparse
    from datetime import date

    p = argparse.ArgumentParser(description="Eén routine per week voor een nieuwe uitgave (PLAN #35.2)")
    p.add_argument("stap", nargs="?", choices=["draaien", "stand", "rapport"], default="draaien")
    p.add_argument("release", nargs="?", help="rapport: de uitgave (standaard de laatste van de routine)")
    p.add_argument("--toch", action="store_true", help="ook als deze stand van de feed al een uitgave heeft")
    p.add_argument("--wacht", type=int, default=120, help="minuten wachten op een batch per stap")
    p.add_argument("--grens", type=float, default=GRENS, help="dollar voor deze uitgave, alle stappen samen")
    p.add_argument("--melding", action="store_true", help="een melding op de Mac, ook bij een fout")
    p.add_argument("--tot", help="tot en met deze stap, bijvoorbeeld `bouwen` om eerst te zien wat nieuw is ($0)")
    a = p.parse_args()
    vorige_pad = MAP / "laatste.json"
    vorige = json.loads(vorige_pad.read_text(encoding="utf-8")) if vorige_pad.exists() else {}
    if a.stap == "stand":
        print(json.dumps(vorige, ensure_ascii=False, indent=1) if vorige else "nog geen uitgave van de routine")
        return
    if a.stap == "rapport":
        release = a.release or vorige.get("release")
        if not release or not (MAP / f"{release}.json").exists():
            raise SystemExit(f"geen stand van de routine voor {release}")
        print(_rapport(json.loads((MAP / f"{release}.json").read_text(encoding="utf-8")), a.grens))
        return
    log = OPHAALLOG.read_text(encoding="utf-8") if OPHAALLOG.exists() else ""
    feed = laatste_bijwerking(log)
    try:
        if lab_bezig(log) and not a.toch:
            print("het lab wordt bijgewerkt; later opnieuw")
            return
        # een uitgave die nog niet klaar is, gaat eerst verder; anders alleen bij een nieuwe stand van de feed
        bezig = vorige.get("feed") == feed and not vorige.get("klaar")
        if not bezig and not moet_verversen(feed, vorige, a.toch):
            print(f"geen nieuwe stand van de feed sinds {vorige.get('release')} ({feed})")
            return
        from doublecheck import uitrol

        release = vorige["release"] if bezig else uitrol.volgende_naam(uitrol._bestaande(), date.today().isoformat())
        if not bezig:
            vorige = {"feed": feed, "release": release, "klaar": False}
            MAP.mkdir(parents=True, exist_ok=True)
            vorige_pad.write_text(json.dumps(vorige, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"uitgave {release} uit {feed}", flush=True)
        stappen = maak_stappen(release, a.grens, a.wacht)
        if a.tot and a.tot not in stappen:
            raise Weigering(f"geen stap {a.tot!r}; de stappen: {', '.join(stappen)}")
        stand = voer_uit(stappen, MAP / f"{release}.json", release=release, feed=feed, grens=a.grens, tot=a.tot)
        if a.tot and a.tot != list(stappen)[-1]:
            b = stand["stappen"].get("bouwen", {})
            print(f"gestopt na {a.tot}: {b.get('nieuw')} nieuw ({b.get('per_taal')}), {b.get('weg')} weg tegenover "
                  f"{b.get('live')}; ${stand['kosten']:.2f}")
            return
        tekst = _rapport(stand, a.grens)
        vorige_pad.write_text(json.dumps({**vorige, "klaar": True}, ensure_ascii=False) + "\n", encoding="utf-8")
        print(tekst)
        if a.melding:
            b = stand["stappen"]["bouwen"]
            _melding_mac(f"Uitgave {release} staat klaar: {b['nieuw']} nieuwe factchecks, ${stand['kosten']:.2f}. "
                         f"Live met een ja van de PO.")
    except NietsNieuw as e:
        import shutil

        # de gebouwde uitgave is gelijk aan die op factiz.org: weg ermee (nooit die van factiz.org), en deze stand is gedaan
        if vorige["release"] != _live():
            shutil.rmtree(WORTEL / "data" / "publicatie" / vorige["release"], ignore_errors=True)
        (MAP / f"{vorige['release']}.json").unlink(missing_ok=True)
        vorige_pad.write_text(json.dumps({**vorige, "klaar": True, "niets": str(e)}, ensure_ascii=False) + "\n",
                              encoding="utf-8")
        print(f"geen uitgave nodig: {e}")
    except Weigering as e:
        print(f"gestopt: {e}")
        if a.melding:
            _melding_mac(f"De routine stopte: {e}")
        raise SystemExit(1) from None


if __name__ == "__main__":  # pragma: no cover
    main()
