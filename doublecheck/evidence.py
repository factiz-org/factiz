"""Bewijstoestand samenstellen: wie checkte het, wanneer, wat kwam eruit (E3.S3).

Het antwoord is opsombaar bewijs — uitgevers, oordelen, data, talen en een
telling. Geen enkel veld drukt waarheidswaarschijnlijkheid uit (DR2); de
schema-guard daarop is taak 1.8.
"""

from __future__ import annotations

import re
import unicodedata

import sqlite3
from dataclasses import dataclass


@dataclass(frozen=True)
class FactcheckEvidence:
    publisher: str
    verdict_normalized: str
    verdict_original: str
    url: str
    review_date: str
    language: str


@dataclass(frozen=True)
class EvidenceState:
    claim_id: str
    canonical_text: str
    factchecks: tuple[FactcheckEvidence, ...]
    check_count: int
    publisher_count: int
    languages: tuple[str, ...]
    oldest_date: str | None
    # Aantal claims dat deze bewering vormt (E2.S5-AC3); 1 = niet geclusterd.
    cluster_size: int = 1
    # De claims waarover dit bewijs gaat: de claim zelf, of zijn cluster.
    # Het antwoord haalt er de geschiedenis bij op (PROTOCOL §11.7); deze
    # module kent die bewust niet, zodat ze nooit kan meetellen (E7.S2-AC2).
    leden: tuple[str, ...] = ()


_URLNAAM = re.compile(r"https?://|^www\.", re.IGNORECASE)
_HOST = re.compile(r"^(?:https?://)?(?:www\.)?([^/\s?#]+)", re.IGNORECASE)


def _uitgeversleutel(naam: str) -> str:
    """Identiteit van een uitgever, los van schrijfwijze (#17.5, #17.6).

    Het corpus draagt 137 groepen namen die alleen in kast of spaties
    verschillen — `FACTLY`, `FACTLY  `, `Factly`, `factly` — en 2.172
    factchecks met spaties aan de rand. Die als aparte uitgevers tellen holt
    DR7 uit, want DR7 gaat juist over onafhankelijkheid: één redactie die
    zichzelf bevestigt is geen consensus (§47).

    Ook leestekens vallen weg: `El Detector / Univision Noticias` en
    `El Detector/ Univision Noticias` zijn één redactie, en een Arabische
    uitgever staat er met zeven soorten aanhalingstekens in.

    Wat er wég mag is leestekens, spaties en stuurtekens — niet meer. Twee
    eerdere versies sneden te diep:

    - `[a-z0-9]` liet elk niet-Latijns teken vallen en smolt `Вокс Чек`,
      `Вячеслав Вареня` en 107 andere namen tot één identiteit (§48);
    - ``\\w`` lijkt Unicode-breed maar laat combinerende tekens vallen (categorie
      Mn en Mc), waardoor `क्विंट हिंदी` verminkte tot `कवटहद`. Dat raakte 102
      namen en veroorzaakte twee echte botsingen.

    Daarom nu op Unicode-categorie: alles behalve leestekens (P), scheidings-
    tekens (Z) en stuurtekens (C) blijft staan.
    """
    kaal = "".join(
        teken
        for teken in naam.casefold()
        if unicodedata.category(teken)[0] not in {"P", "Z", "C"}
    )
    return kaal or re.sub(r"\s+", " ", naam).strip().casefold()


def _host(url: str) -> str | None:
    treffer = _HOST.match((url or "").strip())
    return treffer.group(1).lower() if treffer else None


def _identiteit(naam: str, url: str, bekende: set[str]) -> str:
    """Wie heeft dit gecheckt — voor de telling, niet voor de weergave.

    ClaimReview's `author` bevat soms de URL van het bericht dát gecheckt werd
    in plaats van de checker: 230 velden in dit corpus, waarvan het `url`-veld
    er 111 naar pesacheck.org wijst. Dat is PesaCheck, niet honderd uitgevers.
    Zo'n veld valt terug op het merk uit de check-URL — `pesacheck.org` wordt
    `pesacheck` — en telt mee als die naam elders in dit bewijs voorkomt.

    De terugval kijkt uitsluitend naar de namen ín dit bewijs. Een kaart over
    het hele corpus zou transitief samenvoegen, en dat loopt mis: `politifact`
    publiceert ook op `factstream.co`, en die schakel trok 230 namen over 32
    hosts tot één blok (§48).
    """
    if not _URLNAAM.match(naam.strip()):
        return _uitgeversleutel(naam)
    host = _host(url)
    if not host:
        return _uitgeversleutel(naam)
    delen = host.split(".")
    merk = delen[-2] if len(delen) >= 2 else delen[0]
    return merk if merk in bekende else host


def onafhankelijke_uitgevers(checks, register=None, onbekend: str = "telt-mee") -> int:
    """Hoeveel verschíllende redacties zitten hierachter? *(DR7, #17.7)*

    De identiteit hangt aan de host van de factcheck, niet aan de naam die
    iemand in het `author`-veld zette: daar staan claimanten en journalisten
    tussen. `register` is de host → naam-lijst uit `uitgevers.json`.

    `onbekend` bepaalt wat een host doet die niet in het register staat.
    `telt-niet-mee` is de strenge stand — een uitgever die we niet kennen mag
    geen consensus dragen — maar hij straft ook onvolledigheid van het register,
    en dat verschil is groot (§50). De keuze staat in config, niet hier.
    """
    if register is None:
        from doublecheck.uitgevers import load_hosts

        register = load_hosts()

    identiteiten = set()
    bekende_namen = {
        _uitgeversleutel(check.publisher)
        for check in checks
        if not _URLNAAM.match(check.publisher.strip())
    }
    for check in checks:
        host = _host(check.url)
        if host in register:
            identiteiten.add(_uitgeversleutel(register[host]))
        elif onbekend == "telt-niet-mee":
            continue
        else:
            identiteiten.add(_identiteit(check.publisher, check.url, bekende_namen))
    return len(identiteiten)


def build_evidence(
    conn: sqlite3.Connection,
    claim_id: str,
    register=None,
    onbekend: str | None = None,
) -> EvidenceState:
    """`register` en `onbekend` overschrijven het uitgeversregister en het
    beleid uit config — bedoeld om de telling te toetsen zonder de configuratie
    van de machine te veranderen."""
    claim = conn.execute(
        "SELECT canonical_text, cluster_id FROM claim WHERE claim_id = ?",
        (claim_id,),
    ).fetchone()
    if claim is None:
        raise LookupError(f"claim onbekend: {claim_id}")

    # DR7: de bewijstoestand hoort bij de bewéring, niet bij één formulering.
    # Zit de claim in een cluster, dan tellen de checks van alle leden mee —
    # dat is wat "veertien keer weerlegd" waarmaakt (E2.S5-AC3).
    if claim["cluster_id"] is None:
        leden = [claim_id]
    else:
        leden = [
            rij["claim_id"]
            for rij in conn.execute(
                "SELECT claim_id FROM claim WHERE cluster_id = ? ORDER BY claim_id",
                (claim["cluster_id"],),
            )
        ]

    # Een lid buiten de index (B28) draagt niets bij: een vage tekst trekt
    # ook bij het clusteren aan. De claim zelf blijft opvraagbaar, als
    # bonnetje (SPECS E2.S6-AC5).
    from doublecheck.toelating import buiten_index

    buiten = buiten_index(conn)
    leden = [lid for lid in leden if lid == claim_id or lid not in buiten]

    plaatshouders = ",".join("?" for _ in leden)
    rows = conn.execute(
        "SELECT publisher, verdict_normalized, verdict_original, url, review_date,"
        f" language FROM factcheck WHERE claim_id IN ({plaatshouders})"
        " ORDER BY review_date",
        leden,
    ).fetchall()
    if not rows:
        # Het domeinmodel eist 1..n factchecks per claim; een claim zonder is
        # een corrupte index, geen leeg-maar-geldig antwoord.
        raise LookupError(f"claim zonder factchecks in de index: {claim_id}")
    # Met de witte lijst (B28) is alleen een check van een nagekeken uitgever
    # een bonnetje; de rest blijft in de database (SPECS E2.S6-AC3).
    from doublecheck.toelating import toegelaten

    rows = [row for row in rows if toegelaten(conn, row["url"])]
    if not rows:
        raise LookupError(f"claim buiten de index, geen check van een nagekeken uitgever: {claim_id}")

    # Het bonnetje toont de redactie achter de link, niet wat de feed als
    # uitgever zette: daar staan claimanten en journalisten tussen ("Donald
    # Trump" op politifact.com, #25.19 b). Een host buiten het register
    # houdt de naam uit de feed.
    if register is None:
        from doublecheck.uitgevers import load_hosts

        register = load_hosts()
    checks = tuple(
        FactcheckEvidence(
            publisher=register.get(_host(row["url"]) or "", row["publisher"]),
            verdict_normalized=row["verdict_normalized"],
            verdict_original=row["verdict_original"],
            url=row["url"],
            review_date=row["review_date"],
            language=row["language"],
        )
        for row in rows
    )
    from doublecheck.config import load_config

    return EvidenceState(
        claim_id=claim_id,
        canonical_text=claim["canonical_text"],
        factchecks=checks,
        check_count=len(checks),
        publisher_count=onafhankelijke_uitgevers(
            checks,
            register=register,
            onbekend=onbekend or load_config().consensus.onbekende_uitgever,
        ),
        languages=tuple(sorted({check.language for check in checks})),
        # Alleen bekende datums tellen mee; `None` betekent "van geen enkele
        # check weten we wanneer" — niet verzinnen en niet leeg doen alsof
        # (DR1, #14.3).
        oldest_date=min(
            (check.review_date for check in checks if check.review_date),
            default=None,
        ),
        cluster_size=len(leden),
        leden=tuple(leden),
    )
