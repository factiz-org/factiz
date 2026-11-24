"""Import uit de CC BY-feed van Data Commons (PLAN.md #14.5, B13).

Waarom deze bron en niet de Fact Check Tools API: die verbiedt onder Google APIs
ToS §5 het bouwen van databases (§5.e.1), het herdistribueren én het maken van
afgeleide werken (§5.e.2), en zelfs het doorgeven aan derden (§5.c) — precies
wat wij doen. De Data Commons-feed draagt CC BY op de compilatie en mag dat
allemaal wel (PROTOCOL.md §11.5).

Twee dingen maken deze bron anders dan de API:

**Geen taalveld.** Nul van de 98.997 records draagt `inLanguage` (BENCHMARK.md
§33a). De taal komt daarom uit `taal.corpus_taal`, per claim.

Er stond hier eerst een meerderheidstelling per uitgever — een krukje voor een
detector die maar zes talen kende. Met py3langid is dat krukje niet alleen
overbodig maar schadelijk: per claim haalt 98% van de feed een taal tegen 67%
via de uitgever, en het splitst meertalige uitgevers netjes. Fact Crescendo valt
uiteen in en/hi/ml/km/bn/as/mr, waar een meerderheid alleen `und` kon zeggen
(§35).

**Herkomst moet mee.** Zonder vastgelegde bron kunnen we bij het vrijgeven niet
scheiden wat wél en niet in de repo mag (15.3). Dat is een mechanische eis: een
regel die niemand afdwingt, is bij het inpakken vergeten.
"""

from __future__ import annotations

import collections

from doublecheck.factchecktools import RawClaim, RawFactcheck

# Herkomstwaarden voor `factcheck.source`. Alleen de eerste mag mee in een
# publieke uitgave; de tweede is contractueel gebonden aan Googles voorwaarden.
HERDISTRIBUEERBAAR = "datacommons-ccby"
API_GEBONDEN = "factchecktools-api"

_TAAL_ONBEPAALD = "und"


def _reviews(feed: dict):
    for element in feed.get("dataFeedElement", []):
        inhoud = element.get("item")
        for review in (inhoud if isinstance(inhoud, list) else [inhoud]):
            if isinstance(review, dict):
                yield review


def _uitgever(review: dict) -> tuple[str | None, str | None]:
    auteur = review.get("author")
    if not isinstance(auteur, dict):
        return None, None
    site = (auteur.get("url") or "").removeprefix("https://").removeprefix("http://")
    return auteur.get("name"), (site.strip("/").removeprefix("www.") or None)


def _oordeel(review: dict) -> str | None:
    rating = review.get("reviewRating")
    if not isinstance(rating, dict):
        return None
    return rating.get("alternateName") or rating.get("name")


def parse_feed(feed: dict) -> list[RawClaim]:
    """Feedrecords naar dezelfde vorm als de API, zodat er één importpad blijft.

    De taal komt per claim uit `corpus_taal`; bij twijfel `und`. Records zonder
    claimtekst vallen af — dat zijn er 6.945 van de 98.997 (§33a).
    """
    from doublecheck.taal import corpus_taal

    claims: list[RawClaim] = []
    for review in _reviews(feed):
        tekst = review.get("claimReviewed")
        if not tekst:
            continue
        naam, site = _uitgever(review)
        claims.append(
            RawClaim(
                text=tekst,
                claimant=None,  # bewust weggelaten: meestal een genoemde persoon
                claim_date=None,
                factchecks=(
                    RawFactcheck(
                        publisher=naam,
                        publisher_site=site,
                        url=review.get("url"),
                        review_date=review.get("datePublished"),
                        verdict_original=_oordeel(review),
                        language=corpus_taal(tekst) or _TAAL_ONBEPAALD,
                    ),
                ),
            )
        )
    return claims


def redistribueerbare_claims(conn) -> list[str]:
    """Claims waarvan élke check uit een herdistribueerbare bron komt (15.3).

    Eén API-gebonden check is genoeg om de hele claim uit te sluiten: de
    claimtekst kan uit die bron komen, en dat is niet uit elkaar te trekken
    zonder te gokken. De veilige kant kost hier dekking en geen precisie.
    """
    return [
        rij[0]
        for rij in conn.execute(
            "SELECT c.claim_id FROM claim c JOIN factcheck f"
            " ON f.claim_id = c.claim_id"
            " GROUP BY c.claim_id"
            " HAVING sum(CASE WHEN f.source <> ? THEN 1 ELSE 0 END) = 0",
            (HERDISTRIBUEERBAAR,),
        )
    ]


def main() -> None:
    import argparse
    import collections
    import json
    from pathlib import Path

    from datetime import datetime, timezone

    from doublecheck.ingest import ConfigFingerprinter, import_claims
    from doublecheck.storage import connect, init_schema, registreer_importrun

    parser = argparse.ArgumentParser(
        description="Doublecheck import uit de CC BY-feed (#14.5)"
    )
    parser.add_argument("--bestand", required=True,
                        help="het gedownloade data.json van Data Commons")
    parser.add_argument("--db", default="doublecheck-ccby.db")
    parser.add_argument("--max", type=int, default=None,
                        help="alleen de eerste N claims importeren")
    parser.add_argument("--uitgesteld", action="store_true",
                        help="niet embedden; doe dat daarna met doublecheck.reindex")
    parser.add_argument("--alleen-talen", action="store_true",
                        help="alleen de taalanalyse, niets importeren")
    args = parser.parse_args()

    feed = json.loads(Path(args.bestand).read_text(encoding="utf-8"))
    claims = parse_feed(feed)
    print(f"feed: {len(claims)} ClaimReviews met claimtekst")

    per_taal: collections.Counter = collections.Counter()
    for claim in claims:
        for check in claim.factchecks:
            per_taal[check.language] += 1
    bepaald = len(claims) - per_taal[_TAAL_ONBEPAALD]
    print(f"taal bepaald: {bepaald}/{len(claims)} ({bepaald/max(1,len(claims)):.0%})"
          f" · {len(per_taal) - 1} talen")
    for taal, n in per_taal.most_common(15):
        print(f"   {taal:<6}{n:>7}")

    if args.alleen_talen:
        return

    if args.max:
        claims = claims[: args.max]
    gestart = datetime.now(timezone.utc).isoformat(timespec="seconds")
    conn = connect(args.db)
    init_schema(conn)
    rapport = import_claims(
        conn, claims,
        fingerprinter=None if args.uitgesteld else ConfigFingerprinter(),
        source=HERDISTRIBUEERBAAR,
        uitgesteld=args.uitgesteld,
    )
    registreer_importrun(
        conn, gestart_op=gestart, bron=str(args.bestand), rapport=rapport,
        nieuwe_fingerprints=rapport.new_fingerprints,
    )
    print()
    print(f"geïmporteerd in {args.db}: {rapport.accepted_claims} claims,"
          f" {rapport.accepted_factchecks} checks,"
          f" {rapport.existing_claims} al bekend,"
          f" {len(rapport.refusals)} geweigerd")
    print(f"herdistribueerbaar: {len(redistribueerbare_claims(conn))} claims")
    conn.close()


if __name__ == "__main__":
    main()
