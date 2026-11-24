"""Ask Factiz: een vraag aan het corpus (PLAN #24.10, SPECS E5.S3, DESIGN §4e).

Een vraag in gewone woorden, en terug de gecheckte beweringen die er het
dichtst bij liggen. De categorie per bewering komt uit de
categoriseringsfunctie (DR4), met de drempels van de resolver: de herordenaar
als eigen poort haalde de stiltemeting niet (BENCHMARK §114). Getoond wordt
alleen `matched` en `related`, en elk cluster één keer, met de bewering die
het dichtst bij de vraag ligt. Geen taalmodel dat schrijft en geen geschreven
antwoord (B26, B31): het antwoord is de beweringen met hun bonnetjes.

De vraag wordt nergens bewaard of gelogd (DR3). De meting (`vraagtoets`) en
het endpoint gebruiken dezelfde twee functies, dus het cijfer op de pagina
is het cijfer van dit pad (kritiek AC van E5.S3).
"""

from __future__ import annotations

import json
import sqlite3
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from doublecheck.categorize import Category, categorize
from doublecheck.config import Config
from doublecheck.embedding import TextFingerprint
from doublecheck.evidence import EvidenceState, build_evidence
from doublecheck.relation import contradicts
from doublecheck import feitenlaag, rechter, vraagvorm
from doublecheck.taal import zijn_verschillende_talen

DIEPTE = 5
GETOOND = (Category.MATCHED, Category.RELATED)
TIPLIJNEN = Path(__file__).with_name("tiplijnen.json")
# Geen vertaling bij deze taallabels: Engels hoeft niet, onbekend kan niet, en
# bij het label Galicisch vond de leesproef een betekenisfout (B32, §117).
GEEN_VERTALING = frozenset({"en", "und", "", "gl"})
# De kant van een check, in de woorden van de samenvatting (DESIGN §4e).
_KANT = {"onwaar": "false or misleading", "misleidend": "false or misleading", "waar": "true",
         "deels-waar": "partly true"}
_ANDER_OORDEEL = {"onbewezen": "unproven", "satire": "satire"}

# Gemeten door `python -m doublecheck.vraagtoets` over dit pad (BENCHMARK
# §115, en sinds de vraagvorm §118): de 53 testvragen van §112 en de 50
# stillevragen van §113, en de 5.000 stukken webtekst van §114 met de drempel
# van de resolver (de vraagvorm raakte daar geen tekst, §118). Wie het pad
# wijzigt, meet opnieuw en zet de cijfers hier en in BENCHMARK gelijk.
METING = {
    "vragen": 53,
    "getoond_juist": 40,  # de verwachte bewering, telkens als eerste kaart
    "andere": 2,  # een check van hetzelfde verhaal uit een andere groep
    "niets": 9,
    "stillevragen": 50,
    "stilte_vals": 0,
    "webtekst": 5000,
    "webtekst_vals": 1,
}


@dataclass(frozen=True)
class Kandidaat:
    claim_id: str
    tekst: str
    gelijkenis: float
    categorie: Category
    via: dict[str, str] | None = None


def kandidaten(conn: sqlite3.Connection, config: Config, vraag: str,
               fingerprint: TextFingerprint, *, vingerafdruk=None) -> list[Kandidaat]:
    """De vijf beweringen die het dichtst bij de vraag liggen, elk met haar
    categorie. Zoals de resolver: tegenspraak in getallen of ontkenning maakt
    nooit `matched` (DR8), en de lagere drempel over talen heen geldt alleen
    als beide talen herkend zijn en verschillen (#12.4)."""
    uit = []
    gevonden = vraagvorm.zoek(conn, config, vraag, fingerprint, max(DIEPTE, config.rechter.diepte),
                              vingerafdruk=vingerafdruk)
    feit = []  # de feitenlaag (#30.3b), hoogstens één keer per vraag gevraagd

    def is_feit() -> bool:
        if not feit:
            feit.append(feitenlaag.herken(vraag, fingerprint, config) is not None)
        return feit[0]

    for kandidaat in rechter.herorden(conn, config, vraag, gevonden)[:DIEPTE]:
        tekst, taal = conn.execute("SELECT canonical_text, language FROM claim WHERE claim_id = ?",
                                   (kandidaat.claim_id,)).fetchone()
        uitkomst = categorize(
            kandidaat.similarity, config.thresholds,
            contradiction=contradicts(fingerprint.numbers, fingerprint.negations, tekst, artefact_text=vraag,
                                      artefact_negation_tokens=fingerprint.negation_tokens),
            crosslinguaal=zijn_verschillende_talen(fingerprint.language, taal),
            rechter=rechter.oordeel(kandidaat, config),
            feit_rood=config.feiten.aan and feitenlaag.rood(conn, kandidaat.claim_id) and is_feit())
        uit.append(Kandidaat(kandidaat.claim_id, tekst, float(kandidaat.similarity), uitkomst.category,
                             kandidaat.via))
    return uit


def getoond(conn: sqlite3.Connection, rijen: list[Kandidaat]) -> list[tuple[Kandidaat, EvidenceState]]:
    """Wat Ask Factiz toont: alleen `matched` en `related`, in volgorde, en
    elk cluster één keer. Twee leden van één cluster dragen dezelfde
    bonnetjes; twee kaarten zouden dubbel tellen wat één keer gecheckt is."""
    uit, gezien = [], set()
    for rij in rijen:
        if rij.categorie not in GETOOND or rij.claim_id in gezien:
            continue
        staat = build_evidence(conn, rij.claim_id)
        gezien.update(staat.leden or (rij.claim_id,))
        if staat.check_count:
            uit.append((rij, staat))
    return uit


def samenvatting(rijen: list[tuple[Kandidaat, EvidenceState]]) -> dict | None:
    """Variant B van DESIGN §4e: een samenvatting van de oordelen over de
    getoonde beweringen, nooit over de vraag. Bij één bewering niets; spreken
    twee getoonde beweringen elkaar tegen ("vaccines cause autism" en
    "vaccines do not cause autism"), dan geen telling maar de tegengestelde
    bewering, want een telling zou daar misleiden."""
    from doublecheck.relation import contradicts, extract_negation_tokens, extract_negations, extract_numbers
    from doublecheck.verdicts import labelklasse_in_tijd

    if len(rijen) < 2:
        return None

    def spreekt_tegen(a: str, b: str) -> bool:
        return contradicts(extract_numbers(a), extract_negations(a), b, artefact_text=a,
                           artefact_negation_tokens=extract_negation_tokens(a))

    for i, (a, _) in enumerate(rijen):
        for b, staat in rijen[i + 1:]:
            if spreekt_tegen(a.tekst, b.tekst) or spreekt_tegen(b.tekst, a.tekst):
                klasse, _ = labelklasse_in_tijd((c.verdict_normalized, c.review_date) for c in staat.factchecks)
                return {"kind": "opposite", "claim_id": b.claim_id, "verdict_class": klasse}
    checks = [c for _, staat in rijen for c in staat.factchecks]
    kanten = Counter(_KANT[c.verdict_normalized] for c in checks if c.verdict_normalized in _KANT)
    if not kanten:
        return None
    anders = Counter(_ANDER_OORDEEL[c.verdict_normalized] for c in checks if c.verdict_normalized in _ANDER_OORDEEL)
    zonder = [c for c in checks if c.verdict_normalized not in _KANT and c.verdict_normalized not in _ANDER_OORDEEL]
    uit = {"other": [{"verdict": v, "count": n} for v, n in sorted(anders.items())],
           "no_rating": {"count": len(zonder), "publisher": zonder[0].publisher,
                         "words": zonder[0].verdict_original.strip()} if zonder else None}
    if len(kanten) == 1:
        (kant, aantal), = kanten.items()
        return {"kind": "agree", "side": kant, "rated": aantal, **uit}
    return {"kind": "disagree", "counts": dict(kanten), **uit}


def vertaling(conn: sqlite3.Connection, claim_id: str, taal: str) -> dict | None:
    """De bewering in de taal van de pagina, uit de varianten die offline
    geschreven zijn (#25.17), met de herkomst erbij; alleen samen met het
    origineel te tonen (B32)."""
    if taal in GEEN_VERTALING:
        return None
    rij = conn.execute("SELECT text, generator, prompt_version FROM claim_variant WHERE claim_id = ?"
                       " AND language = 'en' ORDER BY variant_id LIMIT 1", (claim_id,)).fetchone()
    if rij is None:
        return None
    return {"language": "en", "from_language": taal, "text": rij[0], "generator": rij[1], "prompt": rij[2]}


def tellingen(rijen: list[tuple[Kandidaat, EvidenceState]], onbekend: str) -> dict:
    """De regel bovenaan: beweringen, redacties (DR7), talen en jaren."""
    from doublecheck.datums import geldige_review_datum
    from doublecheck.evidence import onafhankelijke_uitgevers
    from doublecheck.uitgevers import load_hosts

    checks = [c for _, staat in rijen for c in staat.factchecks]
    jaren = sorted({d[:4] for d in (geldige_review_datum(c.review_date or "") for c in checks) if d})
    return {"claims": len(rijen),
            "newsrooms": onafhankelijke_uitgevers(checks, register=load_hosts(), onbekend=onbekend) if checks else 0,
            "languages": len({c.language for c in checks if c.language not in ("", "und")}),
            "first_year": jaren[0] if jaren else None, "last_year": jaren[-1] if jaren else None}


def tiplijnen(taal: str | None, pad: Path = TIPLIJNEN) -> tuple[list[dict], dict]:
    """Redacties met een WhatsApp-tiplijn in de taal van de vraag, letterlijk
    uit de lijst van WhatsApp, met de bron en de dag van vastlegging."""
    data = json.loads(pad.read_text(encoding="utf-8"))
    bron = {"name": data["_bron"]["naam"], "url": data["_bron"]["url"], "recorded": data["_bron"]["vastgelegd"]}
    if not taal:
        return [], bron
    lijnen = [{"organization": lijn["redactie"], "country": lijn["land"], "numbers": lijn["nummers"],
               "links": lijn["links"]}
              for lijn in data["lijnen"] if taal in data["talen_per_land"].get(lijn["land"], ())]
    return lijnen, bron
