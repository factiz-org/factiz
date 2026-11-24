"""Het eerlijkheidsdashboard (#22.5; Engelstalig sinds #22.7): the numbers, misses first.

Dit is het merkverhaal van B18 in paginavorm: tegenover elk AI-waarheidsorakel
staat hier een dienst die zijn eigen metingen publiceert — fouten, dekking,
corpusstand, conformantie — per verzoek vers uit de database gerenderd, nooit
met de hand ingetypt. Een dashboard met getypte cijfers is precies het
vijgenblad dat B17 verbiedt.

Drie regels dragen de pagina:

- **Bronnen, geen beweringen**: benchmark uit `benchmark_run` en
  `benchmark_fout` (inclusief de missers zélf, met beide claimteksten),
  versheid uit `importrun`, corpusstand live geteld, conformantie uit de
  JSON-uitvoer van `python -m conformance <url> --json` (een bestand als
  interface, zodat de conformance-suite ontkoppeld blijft van deze code).
- **Lege staten zijn eerlijk**: "nog geen benchmarkrun" is een antwoord;
  een rij nullen die op een meting lijkt is dat niet.
- **DR2 blijft gelden**: percentages hier zijn systeemprecisie en dekking —
  de ene plek waar DR2 ze toestaat — nooit een waarheidsoordeel.
"""

from __future__ import annotations

import html
import json
import os
import sqlite3
from collections import namedtuple
from datetime import datetime, timezone

from doublecheck.evidence import onafhankelijke_uitgevers
from doublecheck.storage import importruns
from doublecheck.uitgevers import load_hosts

STANDAARD_CONFORMANTIE = "data/conformance-latest.json"

_Check = namedtuple("_Check", "publisher url")


def _inkorten(tekst: str, grens: int) -> str:
    """Kort alleen in wat echt te lang is, en laat zien dat het ingekort is.
    Bij 90 tekens viel het verschil van een getalwissel er vaak net buiten."""
    return tekst if len(tekst) <= grens else tekst[:grens - 3].rstrip() + "..."


def _moment(iso: str) -> str:
    """'2026-10-14T16:20:50+00:00' wordt '2026-10-14 16:20 UTC': de datum blijft
    ondubbelzinnig, de tijd leesbaar. Wat geen tijdstip is, blijft staan."""
    from datetime import datetime, timezone

    try:
        moment = datetime.fromisoformat(iso)
    except (TypeError, ValueError):
        return iso
    if moment.tzinfo is not None:
        moment = moment.astimezone(timezone.utc)
    return moment.strftime("%Y-%m-%d %H:%M UTC")


def _e(waarde) -> str:
    return html.escape(str(waarde))


def _getal(n: int) -> str:
    # EN-notatie sinds #22.7: de site is Engelstalig, dus 80,023 en 0.68%.
    return f"{n:,}"


def _pct(breuk: float, decimalen: int = 1) -> str:
    return f"{breuk * 100:.{decimalen}f}%"


def _bovengrens(k: int, n: int) -> float:
    """Eenzijdige 95%-bovengrens (Clopper-Pearson), zoals in BENCHMARK.md."""
    from scipy.stats import beta  # lazy: scipy hoort niet in de importtijd

    if n == 0:
        return 0.0
    if k == 0:
        return float(1 - 0.05 ** (1 / n))
    return float(beta.ppf(0.95, k + 1, n - k))


# De talen van de testset, met de naam die de Engelse pagina toont; een code
# die hier niet staat, verschijnt als code, zodat er nooit een rij verdwijnt.
TAALNAMEN = {
    "ar": "Arabic", "bn": "Bengali", "de": "German", "en": "English", "es": "Spanish",
    "fa": "Persian", "fr": "French", "hi": "Hindi", "id": "Indonesian", "it": "Italian",
    "ja": "Japanese", "kn": "Kannada", "ml": "Malayalam", "nl": "Dutch", "pt": "Portuguese",
    "ru": "Russian", "si": "Sinhala", "ta": "Tamil", "te": "Telugu", "tr": "Turkish",
    "zh": "Chinese", "crosslinguaal": "Cross-lingual",
}


# De soorten testparen, zoals de Engelse pagina ze noemt (PO 2026-10-13: wat
# buiten Factiz gelezen wordt, is Engels). Onbekend verschijnt als zichzelf.
_KOPIE = {
    "origineel": "the claim itself", "vervorming": "a distorted copy", "inkorting": "a truncated copy",
    "ontkenning": "a copy with a negation added", "cijferwissel": "a copy with its numbers changed",
    "hardste-buur": "its closest neighbouring claim", "vertaling": "a translation",
}
SOORTNAMEN = {
    "origineel": "original", "vervorming": "distorted copy", "inkorting": "truncation",
    "ontkenning": "negation", "cijferwissel": "number swap", "hardste-buur": "hardest neighbour",
    "vertaling": "translation",
}


def _taalvolgorde(taal: str) -> tuple[bool, str]:
    """Talen op alfabet van hun naam; cross-lingual is geen taal en komt
    apart, als laatste (PO 2026-10-13)."""
    return taal == "crosslinguaal", TAALNAMEN.get(taal, taal)


def _benchmarkblok(conn: sqlite3.Connection) -> str:
    run = conn.execute(
        "SELECT * FROM benchmark_run ORDER BY run_id DESC LIMIT 1"
    ).fetchone()
    if run is None:
        return ("<p class='leeg'>No benchmark run in this database yet. "
                "Run <code>python -m doublecheck.benchmark</code>; the run "
                "records itself here.</p>")

    dekking = (run["correct_matches"] / run["same_pairs"]) if run["same_pairs"] else 0.0
    grens = _bovengrens(run["wrong_links"], run["pairs"])
    per_taal = json.loads(run["results_per_language"])
    taalrijen = "".join(
        "<tr><td>{}</td><td>{}</td><td>{}</td><td>{}</td><td>{}</td></tr>".format(
            _e(TAALNAMEN.get(taal, taal)), _getal(s["pairs"]), _getal(s["wrong_links"]),
            _e(_pct(_bovengrens(s["wrong_links"], s["pairs"]), 2)),
            _e(_pct(s["correct_matches"] / s["same_pairs"], 1))
            if s.get("same_pairs") else "—",
        )
        for taal, s in sorted(per_taal.items(), key=lambda kv: _taalvolgorde(kv[0]))
    )

    missers = conn.execute(
        "SELECT f.*, doel.canonical_text AS doeltekst,"
        " fout.canonical_text AS fouttekst"
        " FROM benchmark_fout f"
        " LEFT JOIN claim doel ON doel.claim_id = f.target_claim_id"
        " LEFT JOIN claim fout ON fout.claim_id = f.matched_claim_id"
        " WHERE f.run_id = ? ORDER BY f.similarity DESC",
        (run["run_id"],),
    ).fetchall()
    if missers:
        def misser(m) -> str:
            # Wat de test met de bewering deed; de testtekst zelf bewaart de
            # benchmark bewust niet, dus de zin zegt het in woorden.
            soort = m["provenance"].split(":")[0]
            kopie = _KOPIE.get(soort, "a test version")
            # Een slotpunt van de bewering zelf botst met de dubbele punt erachter.
            doel = _e(_inkorten(m["doeltekst"] or m["target_claim_id"], 280).rstrip().removesuffix(".")
                      .removesuffix("।").removesuffix("。"))
            if m["matched_claim_id"] == m["target_claim_id"]:
                wat = "<em>{}</em>: {} was still linked to it.".format(doel, kopie)
            else:
                wat = "<em>{}</em>: {} was linked to <em>{}</em>".format(
                    doel, kopie, _e(_inkorten(m["fouttekst"] or m["matched_claim_id"], 280)))
            return "<li><span class='soort'>{}</span> ({}, similarity {}): {}</li>".format(
                _e(SOORTNAMEN.get(soort, soort)), _e(m["language"]), _e(f"{m['similarity']:.3f}"), wat)

        misserrijen = "".join(misser(m) for m in missers)
        missersblok = ("<h3>The misses of this run</h3><ul class='missers'>"
                       + misserrijen + "</ul>")
    else:
        missersblok = ("<h3>The misses of this run</h3>"
                       "<p>None. That number is as checkable as a bad one:"
                       " the test set and the measurement live in the"
                       " repository.</p>")

    return (
        "<p>Latest run: <strong>{}</strong> · model <code>{}</code> · "
        "thresholds match {} / related {}.</p>"
        "<dl><dt>pairs</dt><dd>{}</dd>"
        "<dt>errors</dt><dd>{}</dd>"
        "<dt>error upper bound (95%)</dt><dd>{}</dd>"
        "<dt>coverage</dt><dd>{}</dd></dl>"
        "<table><tr><th>language</th><th>pairs</th><th>errors</th>"
        "<th>upper bound</th><th>coverage</th></tr>{}</table>{}"
    ).format(
        _e(_moment(run["started_at"])), _e(run["model_version_text"]),
        _e(run["text_match"]), _e(run["text_related"]),
        _getal(run["pairs"]), _getal(run["wrong_links"]),
        _e(_pct(grens, 2)), _e(_pct(dekking, 1)), taalrijen, missersblok,
    )


def _corpusblok(conn: sqlite3.Connection, config) -> str:
    vandaag = datetime.now(timezone.utc).date().isoformat()
    claims = conn.execute("SELECT COUNT(*) FROM claim").fetchone()[0]
    checks = conn.execute("SELECT COUNT(*) FROM factcheck").fetchone()[0]
    talen = conn.execute(
        "SELECT COUNT(DISTINCT language) FROM claim"
    ).fetchone()[0]
    nieuwste, geldig = conn.execute(
        "SELECT MAX(review_date), COUNT(*) FROM factcheck"
        " WHERE review_date GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'"
        " AND review_date <= ?", (vandaag,),
    ).fetchone()

    register = load_hosts()
    groepen: dict[str, list] = {}
    for rij in conn.execute(
        "SELECT COALESCE(c.cluster_id, c.claim_id) AS groep, f.publisher, f.url"
        " FROM factcheck f JOIN claim c ON c.claim_id = f.claim_id"
    ):
        groepen.setdefault(rij["groep"], []).append(_Check(rij["publisher"], rij["url"]))
    consensus = sum(
        1 for leden in groepen.values()
        if onafhankelijke_uitgevers(
            leden, register, onbekend=config.consensus.onbekende_uitgever
        ) >= 2
    )

    # B28: buiten de index is niet weg, en het aantal is openbaar, per reden.
    from doublecheck.toelating import per_reden

    buiten = per_reden(conn)
    buitenregel = "{} claims: {} whose text says nothing checkable, {} without a check from a reviewed publisher".format(
        _getal(len(buiten["vaag"]) + len(buiten["onbekende_uitgever"])),
        _getal(len(buiten["vaag"])), _getal(len(buiten["onbekende_uitgever"])),
    )

    return (
        "<dl>"
        "<dt>claims</dt><dd>{}</dd>"
        "<dt>fact-checks</dt><dd>{}</dd>"
        "<dt>languages</dt><dd>{}</dd>"
        "<dt>claims checked by 2 or more independent newsrooms</dt><dd>{}</dd>"
        "<dt>latest fact-check</dt><dd>{}</dd>"
        "<dt>checks without a valid date</dt><dd>{}; counted, not hidden"
        " (the source feed lacks the field, and we do not invent dates)</dd>"
        "<dt>kept outside the index</dt><dd>{}; stored, never returned as a match</dd>"
        "</dl>"
    ).format(
        _getal(claims), _getal(checks), _getal(talen), _getal(consensus),
        _e(nieuwste) if nieuwste else "—", _getal(checks - geldig), buitenregel,
    )


def _versheidblok(conn: sqlite3.Connection) -> str:
    runs = importruns(conn, limit=5)
    if not runs:
        return ("<p class='leeg'>No refresh registered yet. The cadence runs "
                "with <code>python -m doublecheck.bootstrap "
                "--vernieuw --met-veto</code> (see the runbook).</p>")
    rijen = "".join(
        "<tr><td>{}</td><td>+{}</td><td>+{}</td><td>{}</td></tr>".format(
            _e(_moment(run["gestart_op"])), _getal(run["nieuwe_claims"]),
            _getal(run["nieuwe_factchecks"]), _getal(run["geweigerd"]),
        )
        for run in runs
    )
    return ("<table><tr><th>run</th><th>claims</th><th>checks</th>"
            "<th>not imported</th></tr>" + rijen + "</table>")


def _conformantieblok(pad: str) -> str:
    if not os.path.exists(pad):
        return ("<p class='leeg'>No conformance output found yet. "
                "Run <code>python -m conformance &lt;url&gt; --json</code> "
                "against the running instance and store the output as "
                "<code>{}</code>.</p>").format(_e(pad))
    try:
        rapport = json.loads(open(pad, encoding="utf-8").read())
        uitslagen = rapport["results"]
    except (json.JSONDecodeError, KeyError, OSError, UnicodeDecodeError):
        return ("<p class='leeg'>The conformance output at <code>{}</code> "
                "cannot be read (not valid JSON, or the wrong shape); this "
                "page would rather show nothing than half.</p>").format(_e(pad))

    if rapport.get("conformant") and rapport.get("complete"):
        kop = "Conformant, fully tested."
    elif rapport.get("conformant"):
        kop = ("Conformant on everything we could observe, but not fully "
               "tested (exit 2): some obligations can only be checked with "
               "probe claims, so we do not claim more.")
    else:
        kop = "Not conformant: the failed obligations are listed below."
    rijen = "".join(
        "<tr><td>{}</td><td>{}</td><td>{}</td><td>{}</td></tr>".format(
            _e(u.get("obligation", "—")), _e(u.get("name", "")),
            _e(u.get("status", "")), _e(u.get("note", "")),
        )
        for u in uitslagen
    )
    return ("<p>{}</p><table><tr><th>#</th><th>obligation</th>"
            "<th>status</th><th>note</th></tr>{}</table>").format(kop, rijen)


def bouw_pagina(conn: sqlite3.Connection, config, conformantie_pad: str) -> str:
    """De hele pagina, per verzoek vers — niets hierin is met de hand getypt
    behalve de uitleg eromheen."""
    blokken = (
        "<h2>Benchmark</h2>" + _benchmarkblok(conn)
        + "<h2>Corpus</h2>" + _corpusblok(conn, config)
        + "<h2>Freshness</h2>" + _versheidblok(conn)
        + "<h2>Conformance</h2>" + _conformantieblok(conformantie_pad)
    )
    from doublecheck.webui import APP_HEAD, APP_KOP, APP_VOET, GEDEELDE_STIJL, band

    return (_SKELET.replace("__GEDEELDE_STIJL__", GEDEELDE_STIJL).replace("__APP_HEAD__", APP_HEAD).replace("__INHOUD__", blokken)
            .replace("__APP_KOP__", APP_KOP["/numbers"]).replace("__APP_VOET__", APP_VOET)
            .replace("__BAND__", band("Accuracy you can audit", "The numbers",
                                      "We publish our misses. Everything on this page is rendered fresh from the "
                                      "measurements themselves (benchmark runs, the import log, live corpus counts, "
                                      "and the conformance output); nothing is filled in by hand. The percentages "
                                      "here are system precision and coverage. By design, no percentage on this page "
                                      "says anything about whether a claim is true.")))


_SKELET = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>The numbers | Factiz</title>
__APP_HEAD__
<meta name="description" content="The Factiz benchmark per language, the corpus, its freshness and the conformance test, rendered live from the measurements, including the misses.">
<style>
__GEDEELDE_STIJL__
  /* De cijferpagina in de kolom van de site (PLAN #23.11), onder de band (#23.14). */
  .cijfers { padding-top: 2.2rem; }
  .cijfers > * { max-width: 52rem; }
  .cijfers h2 { font-size: 1.1rem; font-weight: 600; letter-spacing: 0; margin: 2.2rem 0 .5rem; color: var(--zacht); }
  .cijfers h3 { font-size: 1rem; margin: 1.2rem 0 .4rem; }
  .cijfers p { margin: .5rem 0; }
  .uitleg, .leeg { color: var(--zacht); font-size: .92rem; }
  dl { display: grid; grid-template-columns: max-content 1fr; gap: .25rem 1rem; margin: .8rem 0; }
  dt { color: var(--zacht); }
  dd { margin: 0; font-weight: 600; }
  table { border-collapse: collapse; width: 100%; margin: .8rem 0; font-size: .92rem; }
  th, td { text-align: left; padding: .4rem .5rem; border-top: 1px solid var(--rand); }
  th { color: var(--zacht); font-weight: 600; border-top: none; }
  td { font-variant-numeric: tabular-nums; }
  .missers { margin: .4rem 0 0; padding-left: 1.2rem; }
  .missers li { margin: .35rem 0; }
  .soort { border: 1px solid var(--rand); border-radius: 999px; padding: .02rem .5rem; font-size: .85rem; }
  /* Een lange modelversie breekt, anders scrolt de pagina op een telefoon opzij. */
  code { background: var(--mint); padding: .1rem .35rem; border-radius: 5px; overflow-wrap: anywhere; }
  @media (max-width: 600px) { dl { grid-template-columns: 1fr; } dd { margin-bottom: .4rem; } }
</style>
</head>
<body>
__APP_KOP__
<main id="main">
__BAND__
<div class="baan cijfers">
__INHOUD__
<p class="uitleg">The full measurement history, methods and caveats live in
<code>docs/BENCHMARK.md</code> in the repository.</p>
</div>
</main>
__APP_VOET__
</body>
</html>
"""
