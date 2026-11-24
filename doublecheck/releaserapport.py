"""Het releaserapport uit de metingen (PLAN.md #23.10).

Tot de lancering komen er nog releases bij, en de aankondiging mag dan een
gegenereerd rapport zijn (PO 2026-10-12); de geschreven aankondiging volgt
bij de livegang. Dit vult het skelet uit `docs/RELEASES.md` met wat gemeten
is: twee benchmarkruns, `config.toml`, de conformantie-uitvoer en de
releasekaart. Niets in het rapport komt ergens anders vandaan.

Het weigert waar een vergelijking oneerlijk zou zijn: twee runs op
verschillende testparen (regel 1: vóór en na op dezelfde testset), of een
run `--na` die niet met de motor uit `config.toml` gemaakt is.

    python -m doublecheck.releaserapport --voor 53 --na 54 \\
        --uit docs/releases/factiz-1-2026-10-12.md
"""

from __future__ import annotations

import datetime
import json
import os
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from doublecheck.benchmark import upper_bound_95

RELEASES = Path(__file__).resolve().parent.parent / "docs" / "RELEASES.md"
CROSSLINGUAAL = "crosslinguaal"
_VELDEN = ("pairs", "same_pairs", "wrong_links", "correct_matches")


class OnvergelijkbareRuns(ValueError):
    """Twee runs die niet op dezelfde testparen maten."""


class AndereMotor(ValueError):
    """De run `--na` is niet gemaakt met de motor uit `config.toml`."""


@dataclass(frozen=True)
class Stand:
    pairs: int
    same_pairs: int
    wrong_links: int
    correct_matches: int

    @property
    def dekking(self) -> float:
        return self.correct_matches / self.same_pairs if self.same_pairs else 0.0

    @property
    def grens(self) -> float:
        return upper_bound_95(self.wrong_links, self.pairs)


@dataclass(frozen=True)
class Run:
    run_id: int
    datum: str
    motor: dict[str, object]
    per_taal: dict[str, Stand]


def lees_run(conn: sqlite3.Connection, run_id: int) -> Run:
    rij = conn.execute(
        "SELECT started_at, model_version_text, model_version_image, text_match, text_related,"
        " image_same, variant_set, results_per_language FROM benchmark_run WHERE run_id = ?",
        (run_id,),
    ).fetchone()
    if rij is None:
        raise SystemExit(f"benchmarkrun #{run_id} bestaat niet")
    per_taal = {taal: Stand(*(int(v[k]) for k in _VELDEN)) for taal, v in json.loads(rij[7]).items()}
    motor = {"text model": rij[1], "image hash": rij[2], "text_match": rij[3],
             "text_related": rij[4], "image_same": rij[5], "claim variants": rij[6]}
    return Run(run_id, rij[0][:10], motor, per_taal)


def _optellen(standen) -> Stand:
    standen = list(standen)
    return Stand(*(sum(getattr(s, k) for s in standen) for k in _VELDEN))


def _gedeeld(voor: Run, na: Run) -> list[str]:
    """De talen die beide runs maten, op dezelfde paren; anders weigeren."""
    gedeeld = [t for t in na.per_taal if t in voor.per_taal]
    anders = [t for t in gedeeld
              if (voor.per_taal[t].pairs, voor.per_taal[t].same_pairs)
              != (na.per_taal[t].pairs, na.per_taal[t].same_pairs)]
    if anders:
        t = anders[0]
        raise OnvergelijkbareRuns(
            f"run #{voor.run_id} en #{na.run_id} maten {', '.join(anders)} op verschillende"
            f" testparen ({t}: {voor.per_taal[t].pairs} tegen {na.per_taal[t].pairs});"
            " vergelijk runs op dezelfde testset (RELEASES, regel 1)"
        )
    return gedeeld


def controleer_motor(na: Run, config) -> None:
    verwacht = {"text model": config.model_versions.text_embedding,
                "image hash": config.model_versions.image_hash,
                "text_match": config.thresholds.text_match,
                "text_related": config.thresholds.text_related,
                "image_same": config.thresholds.image_same}
    anders = [f"{k}: run {na.motor[k]!r}, config {v!r}" for k, v in verwacht.items() if na.motor[k] != v]
    if bool(na.motor["claim variants"]) != config.varianten.in_resolver:
        anders.append(f"claim variants: run {na.motor['claim variants'] or 'zonder'!r},"
                      f" config in_resolver = {str(config.varianten.in_resolver).lower()}")
    if anders:
        raise AndereMotor(f"run #{na.run_id} is niet gemaakt met de motor uit config.toml: "
                          + "; ".join(anders))


# --- de kaart -------------------------------------------------------------------

def _huidige_kaart(kaart: str) -> str:
    start = kaart.index("## Huidige release")
    einde = kaart.find("\n## ", start + 1)
    return kaart[start:einde if einde != -1 else None]


def _blok(kaart: str, kop: str, volgende: str | None) -> str:
    """De alinea's vanaf `**kop**` tot `**volgende**` of het einde van de kaart."""
    start = kaart.find(f"**{kop}**")
    if start == -1:
        return ""
    einde = kaart.find(f"**{volgende}**", start) if volgende else -1
    return kaart[start:einde if einde != -1 else None].strip()


# --- opmaak ---------------------------------------------------------------------

def _pct(x: float) -> str:
    return f"{x:.1%}"


def _van_naar(a, b, opmaak=str) -> str:
    return opmaak(a) if a == b else f"{opmaak(a)} to {opmaak(b)}"


def _conformantie(pad: str) -> str:
    if not os.path.exists(pad):
        return (f"No conformance output found at `{pad}`; run `python -m conformance <url>"
                " --proeven deploy/conformantie-proeven.json --json` first.")
    try:
        uitvoer = json.loads(Path(pad).read_text(encoding="utf-8"))
        uitslagen = uitvoer["results"]
    except (OSError, ValueError, KeyError):
        return f"The conformance output at `{pad}` is unreadable."
    datum = datetime.date.fromtimestamp(os.path.getmtime(pad)).isoformat()
    gefaald = [str(u["obligation"]) for u in uitslagen if u.get("status") == "failed"]
    open_ = [str(u["obligation"]) for u in uitslagen if u.get("status") == "not observed"]
    if gefaald:
        stand = f"NOT conformant: obligation {', '.join(gefaald)} broken"
    elif open_:
        stand = f"conformant, not fully tested: obligation {', '.join(open_)} unobserved"
    else:
        stand = "conformant, every obligation tested"
    return f"{stand} ({len(uitslagen)} checks, output of {datum})."


def rapport(conn: sqlite3.Connection, config, voor_id: int, na_id: int, *,
            kaart: str, conformantie_pad: str, vandaag: str | None = None) -> str:
    voor, na = lees_run(conn, voor_id), lees_run(conn, na_id)
    controleer_motor(na, config)
    gedeeld = _gedeeld(voor, na)
    kaart = _huidige_kaart(kaart)
    naam = re.search(r"^### (.+?)(?: \(|$)", kaart, re.MULTILINE)
    naam = naam.group(1).strip() if naam else "Factiz"
    protocol = re.search(r"protocol v(\d+(?:\.\d+)*)", kaart)
    talen = [t for t in gedeeld if t != CROSSLINGUAAL]
    tv, tn = _optellen(voor.per_taal[t] for t in gedeeld), _optellen(na.per_taal[t] for t in gedeeld)
    vandaag = vandaag or datetime.date.today().isoformat()

    r = [f"# {naam} release report", "",
         f"Generated on {vandaag} from benchmark runs #{voor.run_id} ({voor.datum}) and"
         f" #{na.run_id} ({na.datum}) by `python -m doublecheck.releaserapport`. A measurement"
         " report, not an announcement: every number comes from a recorded run, `config.toml`,"
         " the conformance output or the release card.", "",
         "## The sentence", "",
         f"Coverage from {_pct(tv.dekking)} to {_pct(tn.dekking)} on the same {tn.pairs:,} test pairs"
         f" in {len(talen)} languages, with the error bound from {tv.grens:.2%} to {tn.grens:.2%}."]
    if CROSSLINGUAAL in gedeeld:
        cv, cn = voor.per_taal[CROSSLINGUAAL], na.per_taal[CROSSLINGUAAL]
        r += ["", f"Across languages: coverage from {_pct(cv.dekking)} to {_pct(cn.dekking)} on"
                  f" {cn.pairs:,} pairs, errors {_van_naar(cv.wrong_links, cn.wrong_links)}."]

    r += ["", "## What changed in the engine", ""]
    veranderd = [f"- {k}: {_van_naar(voor.motor[k] or 'none', na.motor[k] or 'none', lambda v: v if v == 'none' else f'`{v}`')}"
                 for k in na.motor if voor.motor[k] != na.motor[k]]
    r += veranderd or ["Nothing the runs record changed: text model, image hash, thresholds and claim"
                       " variants are the same. A change outside those, such as OCR, shows only on the"
                       " release card."]

    r += ["", "## What got worse, and what we still miss", ""]
    slechter = []
    for t in gedeeld:
        a, b = voor.per_taal[t], na.per_taal[t]
        if b.wrong_links > a.wrong_links:
            slechter.append(f"- {t}: errors from {a.wrong_links} to {b.wrong_links},"
                            f" bound from {a.grens:.2%} to {b.grens:.2%}")
        if b.correct_matches < a.correct_matches:
            slechter.append(f"- {t}: coverage from {_pct(a.dekking)} to {_pct(b.dekking)}")
    weg = [t for t in voor.per_taal if t not in na.per_taal]
    slechter += [f"- {t}: measured in run #{voor.run_id}, not in run #{na.run_id}" for t in weg]
    r += slechter or [f"Nothing got worse between run #{voor.run_id} and run #{na.run_id}."]
    laagste = sorted(talen, key=lambda t: (na.per_taal[t].dekking, t))[:3]
    hoogste = max(talen, key=lambda t: (na.per_taal[t].grens, t))
    h = na.per_taal[hoogste]
    r += ["", "Still missing:", "",
          f"- We do not find {tn.same_pairs - tn.correct_matches:,} of the {tn.same_pairs:,} test pairs"
          f" whose claim is known ({_pct(1 - tn.dekking)}).",
          "- Lowest coverage: " + ", ".join(f"{t} {_pct(na.per_taal[t].dekking)}" for t in laagste) + ".",
          f"- Highest error bound: {hoogste}, {h.wrong_links} errors in {h.pairs:,} pairs"
          f" (bound {h.grens:.2%})."]
    nieuw = [t for t in na.per_taal if t not in voor.per_taal]
    if nieuw:
        r += ["", f"New in run #{na.run_id}: " + "; ".join(
            f"{t} ({na.per_taal[t].pairs:,} pairs, coverage {_pct(na.per_taal[t].dekking)},"
            f" bound {na.per_taal[t].grens:.2%})" for t in nieuw) + ". No earlier figure to compare."]
    blokken = [b for b in (_blok(kaart, "Wat slechter werd.", "Wat niet werkt."),
                           _blok(kaart, "Wat niet werkt.", None)) if b]
    if blokken:
        r += ["", "From the release card (in Dutch; this covers what the runs do not measure, such"
                  " as speed and memory):", ""]
        for b in blokken:
            r += ["> " + regel if regel else ">" for regel in b.splitlines()] + [""]
        r.pop()

    r += ["", "## Per language", "",
          f"| language | pairs | errors | error bound | coverage #{voor.run_id} | coverage #{na.run_id} | change |",
          "|---|---:|---:|---:|---:|---:|---:|"]
    for t, a, b in [("total", tv, tn)] + [(t, voor.per_taal[t], na.per_taal[t]) for t in gedeeld]:
        r.append(f"| {t} | {b.pairs:,} | {_van_naar(a.wrong_links, b.wrong_links)} | {b.grens:.2%} |"
                 f" {_pct(a.dekking)} | {_pct(b.dekking)} | {(b.dekking - a.dekking) * 100:+.1f} pt |")
    for t in nieuw:
        b = na.per_taal[t]
        r.append(f"| {t} | {b.pairs:,} | {b.wrong_links} | {b.grens:.2%} | new | {_pct(b.dekking)} | |")

    drempels = " · ".join(f"`{k}` {v}" for k, v in config.thresholds.__dict__.items())
    r += ["", "## For implementers", "",
          f"- Protocol: v{protocol.group(1)}" if protocol else "- Protocol: not on the release card",
          f"- Thresholds in force: {drempels}",
          f"- Schemes: text `{config.model_versions.text_embedding}` (no client scheme), image"
          f" `{config.model_versions.image_hash}`",
          f"- Claim variants: `{na.motor['claim variants']}`; a match through one says so in `via`"
          if na.motor["claim variants"] else "- Claim variants: none",
          f"- Conformance: {_conformantie(conformantie_pad)}",
          "", "## Check us", "",
          f"- `python -m doublecheck.benchmark` measures again what run #{na.run_id} measured.",
          "- `/numbers` lists every run with its misses.",
          "- `python -m conformance <url> --proeven deploy/conformantie-proeven.json` checks the"
          " protocol obligations.",
          "- The release card: `docs/RELEASES.md`, under \"Huidige release\".", ""]
    return "\n".join(r)


def main() -> None:
    import argparse

    from doublecheck.cijfers import STANDAARD_CONFORMANTIE
    from doublecheck.config import load_config

    parser = argparse.ArgumentParser(description="Het releaserapport uit de metingen (#23.10)")
    parser.add_argument("--voor", type=int, required=True, help="de run van vóór de wijziging")
    parser.add_argument("--na", type=int, required=True, help="de run van de release")
    parser.add_argument("--uit", help="schrijf hierheen in plaats van naar het scherm")
    args = parser.parse_args()
    from doublecheck.feitenbasis import kern_vingerafdruk, kernpoort, lees_kerncheck, motor_van

    # Nultolerantie op de kern (B33): geen release zolang een vastgesteld feit rood krijgt.
    redenen = kernpoort(lees_kerncheck(), motor_van(load_config()), kern_vingerafdruk())
    if redenen:
        raise SystemExit("release geweigerd (B33, nultolerantie op de kern): " + "; ".join(redenen))
    bron = os.environ.get("DOUBLECHECK_DB", "doublecheck.db")
    conn = sqlite3.connect(f"file:{bron}?mode=ro", uri=True)
    try:
        tekst = rapport(conn, load_config(), args.voor, args.na,
                        kaart=RELEASES.read_text(encoding="utf-8"),
                        conformantie_pad=os.environ.get("DOUBLECHECK_CONFORMANTIE", STANDAARD_CONFORMANTIE))
    except (OnvergelijkbareRuns, AndereMotor) as fout:
        raise SystemExit(str(fout)) from None
    if args.uit:
        Path(args.uit).parent.mkdir(parents=True, exist_ok=True)
        Path(args.uit).write_text(tekst, encoding="utf-8")
        print(f"geschreven: {args.uit}")
    else:
        print(tekst)


if __name__ == "__main__":
    main()
