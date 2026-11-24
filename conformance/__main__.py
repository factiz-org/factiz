"""`python -m conformance <url>` — toets een willekeurige resolver.

Uitgangen: 0 conform en volledig getoetst, 1 niet conform, 2 conform maar met
verplichtingen die niet aan bod kwamen. Dat derde geval is met opzet géén 0:
een suite die niets waarnam heeft niets bewezen.
"""

from __future__ import annotations

import argparse
import json
import sys

from conformance.suite import Proef, controleer_resolver


def lees_proeven(data) -> list[Proef]:
    """Een lijst `[{"name", "text"}]`, of een object met die lijst onder
    `probes` en een `_meta` ernaast: proeven uit een corpus onder CC BY
    dragen hun naamsvermelding mee. Engels, want dit is gereedschap voor
    andere resolvers (PO 2026-10-13)."""
    items = data["probes"] if isinstance(data, dict) else data
    return [Proef(item["name"], item["text"]) for item in items]


def als_json(rapport) -> dict:
    """Het rapport als JSON, met Engelse sleutels: wat buiten Factiz gelezen
    wordt, is Engels (PO 2026-10-13)."""
    return {
        "conformant": rapport.conform,
        "complete": rapport.volledig,
        "results": [{"obligation": u.verplichting, "name": u.naam, "status": u.stand, "note": u.toelichting}
                    for u in rapport.uitslagen],
        "limitations": list(rapport.beperkingen),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m conformance",
        description="Conformance test for the resolver protocol v0.1.",
    )
    parser.add_argument("url", help="base URL of the resolver, e.g. http://localhost:8000")
    parser.add_argument("--pad", default="/resolve", help="path of the resolve endpoint")
    parser.add_argument(
        "--proeven",
        help=(
            "JSON file with artifacts the resolver should match: "
            '[{"name": "...", "text": "..."}], or {"_meta": "...", "probes": [...]} '
            "with their provenance. Without it the matched obligations stay "
            "unobserved."
        ),
    )
    parser.add_argument("--json", action="store_true", help="report as JSON")
    argumenten = parser.parse_args(argv)

    proeven: list[Proef] = []
    if argumenten.proeven:
        with open(argumenten.proeven, encoding="utf-8") as bestand:
            proeven = lees_proeven(json.load(bestand))

    rapport = controleer_resolver(argumenten.url, proeven=proeven, pad=argumenten.pad)

    if argumenten.json:
        print(json.dumps(als_json(rapport), ensure_ascii=False, indent=2))
    else:
        print(rapport.rapport())

    if not rapport.conform:
        return 1
    return 0 if rapport.volledig else 2


if __name__ == "__main__":
    sys.exit(main())
