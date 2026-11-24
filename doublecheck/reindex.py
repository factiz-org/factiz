"""Herindexeren na een fingerprintversiewissel (PLAN.md #12.2, DR6).

Een versiewissel maakt de bestaande index onbruikbaar: de resolver weigert luid
in plaats van stil binnen een lege versie te zoeken (E2.S3-AC2). Tot etappe 12
was herimporteren via de API de enige weg terug — traag, quotavretend en
afhankelijk van wat de bron nú nog teruggeeft.

Herindexeren werkt op de claimtekst die al in de opslag staat. Additief: oude
fingerprints blijven staan, zodat een afgebroken run niets sloopt en een tweede
run verdergaat waar de eerste stopte.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from doublecheck.embedding import fingerprint_texts
from doublecheck.storage import save_text_fingerprint
from doublecheck.taal import detecteer_taal

_BATCH = 256


@dataclass(frozen=True)
class ReindexReport:
    nieuwe_fingerprints: int
    al_aanwezig: int


def bulkfingerprinter(grafische_chip: bool, beschikbaar=None):
    """De fingerprinter voor het herindexeren: op de grafische chip als daarom gevraagd is (B37, #32.38), en dan
    alleen als die er is; anders de processor."""
    import functools

    if grafische_chip:
        if beschikbaar is None:
            import torch

            beschikbaar = torch.backends.mps.is_available
        if not beschikbaar():
            raise SystemExit("geen grafische chip (mps) gevonden; draai zonder --grafische-chip")
    return functools.partial(fingerprint_texts, apparaat="mps" if grafische_chip else "cpu")


def reindex_text(
    conn: sqlite3.Connection,
    model_version: str,
    fingerprinter=fingerprint_texts,
    batch: int = _BATCH,
    voortgang=None,
) -> ReindexReport:
    """Geeft elke claim een tekstfingerprint onder `model_version`."""
    al_aanwezig = conn.execute(
        "SELECT count(*) FROM fingerprint WHERE kind = 'text' AND model_version = ?",
        (model_version,),
    ).fetchone()[0]

    ontbrekend = conn.execute(
        "SELECT c.claim_id, c.canonical_text FROM claim c"
        " WHERE NOT EXISTS ("
        "   SELECT 1 FROM fingerprint f"
        "   WHERE f.claim_id = c.claim_id AND f.kind = 'text'"
        "     AND f.model_version = ?)"
        " ORDER BY c.claim_id",
        (model_version,),
    ).fetchall()

    gemaakt = 0
    for start in range(0, len(ontbrekend), batch):
        blok = ontbrekend[start : start + batch]
        fingerprints = fingerprinter([rij[1] for rij in blok], model_version)
        for (claim_id, _), fingerprint in zip(blok, fingerprints):
            save_text_fingerprint(conn, claim_id, fingerprint)
        conn.commit()
        gemaakt += len(blok)
        if voortgang is not None:
            voortgang(gemaakt, len(ontbrekend))

    return ReindexReport(nieuwe_fingerprints=gemaakt, al_aanwezig=al_aanwezig)


@dataclass(frozen=True)
class HerlabelReport:
    # Aantal tegenspraken met de uitgeversbewering — gemeld, niet toegepast.
    gecorrigeerd: int
    bevestigd: int
    onbeslist: int


def reindex_languages(conn: sqlite3.Connection) -> HerlabelReport:
    """Zet `claim.language` op onze beste inschatting van de taal (#12.6).

    De uitgeversbewering is aantoonbaar onbetrouwbaar — van de 57 claims die als
    `en` binnenkwamen waren er 6 werkelijk Engels (BENCHMARK.md §26a) — en
    per-marktcijfers zijn de kern van B14.

    **Signaleert, corrigeert niet** — teruggedraaid na meting (BENCHMARK.md §32).
    De eerste versie overschreef het label met het oordeel van de detector. Van
    de 126 correcties gingen er 54 wég van `es`, en die waren aantoonbaar fout:
    "Esta imagen muestra a Von der Leyen con Jeffrey Epstein" werd Duits, omdat
    een Duitse naam Duitse functiewoorden bevat. Op de uitgeverspagina's stond
    `<html lang="es">` — de bron had gelijk en wij niet.

    De uitgeversbewering blijft dus leidend. De detector telt de tegenspraken en
    rapporteert ze, zodat een mens ernaar kan kijken. Dat is de enige rol waarin
    hij aantoonbaar beter is dan de bron: opvallen, niet beslissen.
    """
    # Eenmalig de oorspronkelijke bewering vastleggen, vóór de eerste correctie.
    conn.execute(
        "UPDATE claim SET language_reported = language WHERE language_reported = ''"
    )

    gecorrigeerd = bevestigd = onbeslist = 0
    for claim_id, tekst, huidig in conn.execute(
        "SELECT claim_id, canonical_text, language FROM claim ORDER BY claim_id"
    ).fetchall():
        gedetecteerd = detecteer_taal(tekst or "")
        if gedetecteerd is None:
            onbeslist += 1
        elif gedetecteerd == huidig:
            bevestigd += 1
        else:
            # Bewust géén UPDATE: signaleren, niet overschrijven (§32).
            gecorrigeerd += 1
    conn.commit()
    return HerlabelReport(gecorrigeerd, bevestigd, onbeslist)


@dataclass(frozen=True)
class OordeelReport:
    herzien: int
    ongewijzigd: int
    nog_onbekend: int


def reindex_verdicts(conn: sqlite3.Connection) -> OordeelReport:
    """Leidt `verdict_normalized` opnieuw af uit `verdict_original` (#18.1).

    Anders dan bij de taallabels (§32) is herzien hier wél juist, en het
    verschil zit in wiens bewering het is. `claim.language` overschrijven zou
    het oordeel van de uitgever vervangen door dat van onze detector — daar
    verloren we van de bron. `verdict_normalized` is óns afgeleide veld,
    gemaakt uit de onaangeroerde uitgeverstekst; die tekst blijft staan, en
    opnieuw afleiden herstelt alleen wat de tabel inmiddels beter weet.

    Nodig omdat de normalisatie bij import gebeurt: een corpus dat vóór #18.1
    binnenkwam draagt nog `onbekend` op 53% van zijn checks, en juist dat veld
    draagt DR7.
    """
    from doublecheck.evidence import _host
    from doublecheck.verdicts import normalize_verdict

    herzien = ongewijzigd = nog_onbekend = 0
    wijzigingen = []
    for factcheck_id, origineel, huidig, url in conn.execute(
        "SELECT factcheck_id, verdict_original, verdict_normalized, url FROM factcheck"
        " ORDER BY factcheck_id"
    ).fetchall():
        # Met de host: een schaallabel telt alleen op de host van zijn legenda (#25.3b).
        nieuw = normalize_verdict(origineel, host=_host(url))
        if nieuw == "onbekend":
            nog_onbekend += 1
        if nieuw == huidig:
            ongewijzigd += 1
        else:
            wijzigingen.append((nieuw, factcheck_id))
            herzien += 1

    conn.executemany(
        "UPDATE factcheck SET verdict_normalized = ? WHERE factcheck_id = ?",
        wijzigingen,
    )
    conn.commit()
    return OordeelReport(herzien, ongewijzigd, nog_onbekend)


def main() -> None:
    import argparse

    from doublecheck.config import load_config
    from doublecheck.storage import connect, init_schema

    parser = argparse.ArgumentParser(description="Doublecheck herindexeren (DR6)")
    parser.add_argument("--db", default="doublecheck.db")
    parser.add_argument("--alleen-talen", action="store_true",
                        help="alleen de taallabels herzien, niet herembedden")
    parser.add_argument("--alleen-oordelen", action="store_true",
                        help="alleen verdict_normalized opnieuw afleiden (#18.1)")
    parser.add_argument("--grafische-chip", action="store_true",
                        help="embedden op de grafische chip (mps): dezelfde vectoren, twee keer zo snel (B37, #32.38)")
    args = parser.parse_args()

    config = load_config()
    versie = config.model_versions.text_embedding
    conn = connect(args.db)
    init_schema(conn)
    print(f"herindexeren naar {versie!r}")

    def toon(gedaan, totaal):
        print(f"  {gedaan}/{totaal}", end="\r", flush=True)

    if args.alleen_oordelen:
        oordelen = reindex_verdicts(conn)
        print(f"oordelen: {oordelen.herzien} herzien, {oordelen.ongewijzigd}"
              f" ongewijzigd, {oordelen.nog_onbekend} nog onbekend")
        conn.close()
        return

    if not args.alleen_talen:
        rapport = reindex_text(conn, versie, fingerprinter=bulkfingerprinter(args.grafische_chip), voortgang=toon)
        print(f"\n{rapport.nieuwe_fingerprints} nieuwe fingerprints,"
              f" {rapport.al_aanwezig} al aanwezig")

    oordelen = reindex_verdicts(conn)
    print(f"oordelen: {oordelen.herzien} herzien, {oordelen.ongewijzigd}"
          f" ongewijzigd, {oordelen.nog_onbekend} nog onbekend")

    talen = reindex_languages(conn)
    print(f"taallabels: {talen.gecorrigeerd} gecorrigeerd,"
          f" {talen.bevestigd} bevestigd, {talen.onbeslist} onbeslist"
          " (uitgeversbewering bewaard in language_reported)")
    conn.close()


if __name__ == "__main__":
    main()
