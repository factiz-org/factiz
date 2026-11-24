"""De lettertypen van het deelplaatje, uit de pakketten van de site (PLAN #34.2as, SPECS E9.S28 AC3).

    python -m factiz_site.lettertypen

Per pakket van `deelbeeld.NOTO`: het stijlblad `index.css`, de licentie en de bestanden die het stijlblad noemt,
ongewijzigd, naar `factiz_site/fonts/noto/<pakket>/`. Het platform leest er per bestand de tekens uit
(`deelbeeld._bereik`); het leent niets uit de site, alleen deze kopie. Opnieuw draaien na een nieuwe versie van een pakket.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

from factiz_site.deelbeeld import FONTS, NOTO

BRON = Path(__file__).resolve().parent.parent / "site" / "node_modules" / "@fontsource-variable"


def kopieer(bron: Path = BRON, doel: Path = FONTS / "noto") -> dict[str, int]:
    """Kopieert elk pakket; geeft per pakket het aantal lettertypebestanden."""
    uit = {}
    for pakket in NOTO:
        van, naar = bron / pakket, doel / pakket
        css = (van / "index.css").read_text(encoding="utf-8")
        bestanden = sorted(set(re.findall(r"url\(\./files/([^)]+\.woff2)\)", css)))
        if naar.exists():
            shutil.rmtree(naar)
        (naar / "files").mkdir(parents=True)
        shutil.copyfile(van / "index.css", naar / "index.css")
        shutil.copyfile(van / "LICENSE", naar / "LICENSE")
        for naam in bestanden:
            shutil.copyfile(van / "files" / naam, naar / "files" / naam)
        uit[pakket] = len(bestanden)
    return uit


if __name__ == "__main__":  # pragma: no cover
    for pakket, n in kopieer().items():
        print(f"{pakket}: {n} bestanden")
