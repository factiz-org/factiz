"""Vraag en bewering vinden elkaar (PLAN #25.36, stap c).

Een bewering gaat ook als vraag rond ("Is it true that...?"), en een vraag
scoort lager tegen de bewering die al gecheckt is: "Did Ukraine start the war
versus Russia?" haalt 0,781, net onder `related`; dezelfde inhoud als
bewering 0,817 (PO-proef 2026-10-16). Deze regel leest een vraag daarom ook
als bewering, zonder taalmodel: het vraagteken en het vraagwoord of
-partikel eraf, in de talen die de opzet van #25.36 vooraf noemde.

Gezocht wordt met de tekst zoals hij binnenkomt én met de omgezette tekst,
per claim de hoogste gelijkenis, zoals bij de claimvarianten. De categorie
komt daarna uit `categorize` (DR4), en de tegenspraakcontrole (DR8) draait
bij de aanroeper op de tekst zoals hij binnenkwam: "Is X not Y?" wordt zo
nooit `matched` op "X is Y".

Twijfel versoepelt nooit: een vraagwoord gaat er alleen af als de taal
zeker is, of als het woord zelf maar in één taal een vraag maakt (هل, क्या,
か na です of ます, 吗). Anders valt alleen het vraagteken weg. De regel staat
achter `[vraagvorm] aan` en is uit tot een release: aanzetten verschuift
cijfers (B22).
"""

from __future__ import annotations

import re
import sqlite3

from doublecheck.config import VraagvormSettings  # noqa: F401 (de schakelaar hoort bij de regel)
from doublecheck.embedding import TextFingerprint, fingerprint_text, fingerprint_texts
from doublecheck.search import Candidate, search_text, search_texts
from doublecheck.taal import corpus_taal


_VRAAGTEKENS = "?？؟"
_OPEN = "¿¡"
# Engels: eerst een inleiding die van de bewering een vraag maakt, dan een
# hulpwerkwoord vooraan (de inversie van een ja-neevraag). Open vragen (why,
# what, who) blijven staan: dat zijn geen beweringen met een vraagteken.
_ENGELSE_INLEIDING = re.compile(r"^(?:is it true(?: that)?|is this true(?: that)?|did you know(?: that)?)\s+",
                                re.IGNORECASE)
_ENGELS_HULPWERKWOORD = re.compile(
    r"^(?:did|does|do|is|are|was|were|has|have|had|can|could|will|would|should|may|might|must)\s+",
    re.IGNORECASE)
# Turks: het partikel mı/mi/mu/mü als los woord, met of zonder persoonsuitgang.
_TURKS_PARTIKEL = re.compile(
    r"\s+(?:mı|mi|mu|mü)(?:yım|yim|yum|yüm|sın|sin|sun|sün|yız|yiz|yuz|yüz|sınız|siniz|sunuz|sünüz|dır|dir|dur|dür"
    r"|lar|ler)?(?=\s|$)")


def is_vraag(tekst: str) -> bool:
    """Eindigt de tekst op een vraagteken, aanhalingstekens en haakjes niet
    meegerekend?"""
    kern = tekst.strip().rstrip("\"'”»“«)]. ").strip()
    return bool(kern) and kern[-1] in _VRAAGTEKENS


def als_bewering(tekst: str) -> str:
    """De tekst gelezen als bewering: zonder vraagteken en, waar de taal het
    zeker maakt, zonder het vraagwoord of -partikel. Een bewering blijft
    precies zoals ze is; blijft er niets over, dan ook."""
    kern = tekst.strip()
    if not kern or kern[-1] not in _VRAAGTEKENS:
        return tekst
    kern = kern.rstrip(_VRAAGTEKENS + " ").lstrip(_OPEN + " ")
    if not kern:
        return tekst
    kern = _zonder_vraagwoord(kern)
    return kern if kern.strip() else tekst


def _zonder_vraagwoord(kern: str) -> str:
    # Woorden die in één taal een vraag maken: geen taalherkenning nodig.
    if kern.startswith("هل "):
        return kern[len("هل "):]
    if kern.startswith("क्या "):
        return kern[len("क्या "):]
    if kern.endswith("でしょうか"):
        return kern[: -len("でしょうか")]
    if kern.endswith(("ですか", "ますか")):
        return kern[:-1]
    if kern.endswith(("吗", "嗎")):
        return kern[:-1]
    taal = corpus_taal(kern)
    if taal == "en":
        zonder = _ENGELSE_INLEIDING.sub("", kern, count=1)
        return zonder if zonder != kern else _ENGELS_HULPWERKWOORD.sub("", kern, count=1)
    if taal == "tr":
        return _TURKS_PARTIKEL.sub("", kern)
    return kern


def zoek(conn: sqlite3.Connection, config, tekst: str, fingerprint: TextFingerprint,
         limit: int = 5, *, vingerafdruk=None) -> list[Candidate]:
    """De kandidaten voor een tekst, zoals de resolver en Ask ze zoeken. Met de
    regel aan en een vraag als invoer ook met de tekst als bewering, per claim
    de hoogste gelijkenis; bij gelijkstand gaat de zoekvraag zoals hij
    binnenkwam voor. De tweede vingerafdruk komt van dezelfde functie als de
    eerste (`vingerafdruk`, standaard `fingerprint_text`), dus van hetzelfde
    model (DR6)."""
    eerste = search_text(conn, fingerprint, limit, varianten=config.varianten.in_resolver)
    if not config.vraagvorm.aan:
        return eerste
    omgezet = als_bewering(tekst)
    if omgezet == tekst:
        return eerste
    tweede = search_text(conn, (vingerafdruk or fingerprint_text)(omgezet, fingerprint.model_version), limit,
                         varianten=config.varianten.in_resolver)
    return _samen(eerste, tweede, limit)


def zoek_alle(conn: sqlite3.Connection, config, teksten: list[str], fingerprints: list[TextFingerprint],
              limit: int = 5, *, vingerafdrukken=None) -> list[list[Candidate]]:
    """`zoek` voor alle eenheden van een artikel (#30.11): één zoekvraag voor
    alle eenheden, één voor de vragen onder hen als bewering, en per eenheid
    dezelfde samenvoeging als `zoek`. `vingerafdrukken` (standaard
    `fingerprint_texts`) maakt de tweede ronde met hetzelfde model (DR6)."""
    eerste = search_texts(conn, fingerprints, limit, varianten=config.varianten.in_resolver)
    if not config.vraagvorm.aan:
        return eerste
    omgezet = [(i, als_bewering(t)) for i, t in enumerate(teksten)]
    omgezet = [(i, o) for i, o in omgezet if o != teksten[i]]
    if not omgezet:
        return eerste
    vingers = (vingerafdrukken or fingerprint_texts)([o for _, o in omgezet], fingerprints[0].model_version)
    tweede = search_texts(conn, vingers, limit, varianten=config.varianten.in_resolver)
    uit = list(eerste)
    for (i, _), lijst in zip(omgezet, tweede):
        uit[i] = _samen(eerste[i], lijst, limit)
    return uit


def _samen(eerste: list[Candidate], tweede: list[Candidate], limit: int) -> list[Candidate]:
    """Per claim de hoogste gelijkenis; bij gelijkstand gaat de zoekvraag
    zoals hij binnenkwam voor."""
    beste: dict[str, Candidate] = {}
    for kandidaat in [*eerste, *tweede]:
        if kandidaat.claim_id not in beste or kandidaat.similarity > beste[kandidaat.claim_id].similarity:
            beste[kandidaat.claim_id] = kandidaat
    volgorde: dict[str, int] = {}
    for i, kandidaat in enumerate([*eerste, *tweede]):
        volgorde.setdefault(kandidaat.claim_id, i)
    return sorted(beste.values(), key=lambda k: (-k.similarity, volgorde[k.claim_id]))[:limit]
