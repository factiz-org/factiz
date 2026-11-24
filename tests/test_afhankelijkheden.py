"""Wat de code importeert, moet de repo ook vragen (PLAN.md #15.3, B13).

Een schone kloon draait `pip install -r requirements.txt` en verwacht dan een
werkend project. Dat gold niet: `httpx`, `scipy`, `torch` en `transformers`
werden geïmporteerd maar nergens gevraagd — ze waren er alleen omdat andere
pakketten ze toevallig meebrachten.

Zulke afhankelijkheden breken niet vandaag maar bij de eerstvolgende
versiewissel van een ánder pakket, en dan bij iemand anders. Voor een project
dat open source gaat is dat de verkeerde kant om fouten te laten vallen.

Deze guard is dezelfde vorm als de schriftguard en de DR2-schemawalker: hij
loopt de code af in plaats van een lijst te vertrouwen die iemand moet
onthouden.
"""

from __future__ import annotations

import ast
import pathlib
import sys

WORTEL = pathlib.Path(__file__).resolve().parent.parent

# Importnaam → naam waaronder pip het kent, waar die verschillen.
PAKKETNAAM = {
    "PIL": "pillow",
    "sentence_transformers": "sentence-transformers",
    "py3langid": "py3langid",
    "cv2": "opencv-python-headless",
}

# Onze eigen pakketten, en wat de test zelf gebruikt.
EIGEN = {"doublecheck", "conformance", "factiz_site", "tests"}

# Bewust geen afhankelijkheid: alleen voor één meting, met de hand te installeren en daarna weer verwijderd. Elk met
# de reden; de import staat binnen de functie van de meting, zodat de rest van de module zonder het pakket werkt.
ALLEEN_HANDMATIG = {
    "easyocr": "PLAN #32.34: alleen V2 van de voormeting, geen kandidaat, daarna verwijderd (BENCHMARK §210)",
}


def _gevraagd() -> set[str]:
    regels = (WORTEL / "requirements.txt").read_text(encoding="utf-8").splitlines()
    namen = set()
    for regel in regels:
        schoon = regel.split("#")[0].strip()
        if not schoon:
            continue
        for scheiding in ("==", ">=", "<=", "~=", "[", ">", "<"):
            schoon = schoon.split(scheiding)[0]
        namen.add(schoon.strip().lower())
    return namen


def _geimporteerd() -> dict[str, str]:
    """Externe toppakketten die de code importeert, met een vindplaats."""
    stdlib = set(sys.stdlib_module_names)
    gevonden: dict[str, str] = {}
    for map_ in ("doublecheck", "conformance", "factiz_site"):
        for pad in sorted((WORTEL / map_).rglob("*.py")):
            boom = ast.parse(pad.read_text(encoding="utf-8"))
            for knoop in ast.walk(boom):
                namen: list[str] = []
                if isinstance(knoop, ast.Import):
                    namen = [alias.name for alias in knoop.names]
                elif isinstance(knoop, ast.ImportFrom) and knoop.level == 0:
                    namen = [knoop.module or ""]
                for naam in namen:
                    top = naam.split(".")[0]
                    if top and top not in stdlib and top not in EIGEN:
                        gevonden.setdefault(
                            top, f"{pad.relative_to(WORTEL)}:{knoop.lineno}"
                        )
    return gevonden


def test_every_import_is_declared_in_requirements():
    gevraagd = _gevraagd()
    ontbreekt = [
        f"{naam} ({vindplaats})"
        for naam, vindplaats in sorted(_geimporteerd().items())
        if PAKKETNAAM.get(naam, naam).lower() not in gevraagd and naam not in ALLEEN_HANDMATIG
    ]
    assert ontbreekt == [], (
        "wordt geïmporteerd maar niet gevraagd in requirements.txt: "
        + ", ".join(ontbreekt)
        + " — een schone kloon krijgt ze nu alleen als een ánder pakket ze "
        "toevallig meebrengt"
    )


def test_the_walker_still_finds_the_known_dependencies():
    """Als de zoeker stukgaat, slaagt de test hierboven om de verkeerde reden."""
    gevonden = set(_geimporteerd())
    for verwacht in ("fastapi", "numpy", "PIL", "sentence_transformers", "httpx"):
        assert verwacht in gevonden, verwacht


def test_requirements_asks_for_nothing_the_code_never_uses():
    """Andersom ook: een pakket dat nergens wordt gebruikt is ballast, en bij
    een AGPL-uitgave ook een licentievraag die niemand hoeft te stellen."""
    gebruikt = {PAKKETNAAM.get(n, n).lower() for n in _geimporteerd()}
    # pytest draait de tests en wordt daar geïmporteerd, niet in de bibliotheek.
    gebruikt |= {"pytest", "uvicorn", "python-multipart"}
    ongebruikt = sorted(_gevraagd() - gebruikt)
    assert ongebruikt == [], f"staat in requirements.txt maar wordt nergens gebruikt: {ongebruikt}"


def test_no_source_file_carries_an_invalid_escape():
    """Een ongeldige ontsnapping is vandaag een waarschuwing en in een latere
    Python een fout. Voor een pakket dat we weggeven is dat het verkeerde soort
    tijdbom: hij ontploft bij iemand anders, op een versie die wij niet draaien.

    Er stonden er twee: een JS-regex in de webinterface en `\\w` in een
    docstring die juist over `\\w` ging (#15.3).
    """
    import warnings

    klachten = []
    for map_ in ("doublecheck", "conformance", "tests"):
        for pad in sorted((WORTEL / map_).rglob("*.py")):
            with warnings.catch_warnings(record=True) as gevangen:
                warnings.simplefilter("always")
                compile(pad.read_text(encoding="utf-8"), str(pad), "exec")
            klachten += [
                f"{pad.relative_to(WORTEL)}:{w.lineno} {w.message}"
                for w in gevangen
                if issubclass(w.category, SyntaxWarning)
            ]
    assert klachten == [], "ongeldige ontsnapping(en): " + ", ".join(klachten)


def test_no_module_defines_anything_after_its_main_guard():
    """`if __name__ == "__main__": main()` hoort het laatste te zijn.

    Staat er nog een definitie ná dat blok, dan bestaat die naam nog niet als
    `main()` draait — en dat merk je alleen door het commando echt uit te
    voeren. `python -m doublecheck.clustering` clusterde daardoor keurig en
    viel dáárna om op `splits_op_veto`, ná de commit: de clusters stonden er,
    het veto was nooit toegepast (#15.3). Ik maakte dezelfde fout twee keer op
    één dag, in clustering.py en in taalgeschiktheid.py.
    """
    import ast

    klachten = []
    for map_ in ("doublecheck", "conformance", "factiz_site"):
        for pad in sorted((WORTEL / map_).rglob("*.py")):
            boom = ast.parse(pad.read_text(encoding="utf-8"))
            for nummer, knoop in enumerate(boom.body):
                is_main = (
                    isinstance(knoop, ast.If)
                    and isinstance(knoop.test, ast.Compare)
                    and getattr(knoop.test.left, "id", "") == "__name__"
                )
                if is_main and nummer != len(boom.body) - 1:
                    erna = [
                        getattr(k, "name", type(k).__name__)
                        for k in boom.body[nummer + 1 :]
                    ]
                    klachten.append(f"{pad.relative_to(WORTEL)}: {', '.join(erna)}")
    assert klachten == [], (
        "definitie(s) ná het __main__-blok, dus onbereikbaar voor main(): "
        + "; ".join(klachten)
    )


def test_a_manual_package_is_imported_only_inside_a_function_of_its_measurement():
    """Een pakket uit `ALLEEN_HANDMATIG` mag de import van een module nooit breken: alleen binnen een functie."""
    for naam in ALLEEN_HANDMATIG:
        for pad in sorted((WORTEL / "doublecheck").rglob("*.py")):
            boom = ast.parse(pad.read_text(encoding="utf-8"))
            for knoop in boom.body:
                if isinstance(knoop, (ast.Import, ast.ImportFrom)):
                    namen = [a.name for a in knoop.names] if isinstance(knoop, ast.Import) else [knoop.module or ""]
                    assert all(n.split(".")[0] != naam for n in namen), f"{naam} bovenaan {pad.name}"
