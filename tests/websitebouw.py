"""De gebouwde site voor de tests: de placeholder (PLAN #34.2f, stap 3b), een eigen statische bouw in `site/` zoals
Cloudflare Pages haar serveert, en de site zelf (PLAN #34.2v), Astro op de server zoals ze straks draait. De oude site
ging weg in #34.2f.
"""

from functools import lru_cache
from pathlib import Path

WORTEL = Path(__file__).resolve().parent.parent
SITE = WORTEL / "site"


PLACEHOLDER = SITE / "dist-placeholder"
SERVER = SITE / "dist" / "server" / "entry.mjs"


def _bouw(uitvoer: Path, bronnen: list[Path], opdracht: str) -> None:
    """Bouw opnieuw als de uitvoer ontbreekt of een bron nieuwer is; de pakketten eerst als ze er niet zijn."""
    import subprocess

    if not uitvoer.exists() or max(f.stat().st_mtime for f in bronnen) > uitvoer.stat().st_mtime:
        if not (SITE / "node_modules").exists():
            subprocess.run(["npm", "ci", "--no-audit", "--no-fund"], cwd=SITE, check=True, capture_output=True)
        subprocess.run(["npm", "run", opdracht], cwd=SITE, check=True, capture_output=True)


def _woorden() -> list[Path]:
    return [*(WORTEL / "factiz_site" / "teksten").glob("*.json"), WORTEL / "factiz_site" / "static" / "merk" / "woordmerk-inline.svg"]


@lru_cache(maxsize=1)
def placeholder() -> str:
    """De placeholder, gebouwd als de uitvoer ontbreekt of een bron nieuwer is: haar pagina, de teksten, het woordmerk en het
    veld komen uit de site en het platform."""
    index = PLACEHOLDER / "index.html"
    bronnen = [f for map_ in ("placeholder", "src/lib") for f in (SITE / map_).rglob("*") if f.is_file()]
    _bouw(index, bronnen + [SITE / "astro.placeholder.config.mjs", SITE / "package.json", *_woorden()], "build:placeholder")
    return index.read_text(encoding="utf-8")


@lru_cache(maxsize=1)
def site() -> Path:
    """De site voor de server (`npm run build`), gebouwd als de uitvoer ontbreekt of een bron nieuwer is; geeft het
    startbestand voor node. De opmaak en de beelden van `static/` horen erbij, want de bouw kopieert ze."""
    bronnen = [f for f in (SITE / "src").rglob("*") if f.is_file()]
    bronnen += [f for f in (WORTEL / "factiz_site" / "static").rglob("*") if f.is_file()]
    _bouw(SERVER, bronnen + [SITE / "astro.config.mjs", SITE / "package.json", *_woorden()], "build")
    # de lettertypen en beelden van het deelplaatje (PLAN #34.2bo stap 5), buiten git: een keer klaarzetten
    if not (WORTEL / "data" / "deelbeeld" / "voorraad.json").exists():
        import subprocess

        subprocess.run(["node", "scripts/deelbeeld-voorraad.ts"], cwd=SITE, check=True, capture_output=True)
    return SERVER
