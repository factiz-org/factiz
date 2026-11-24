"""Schema-guard DR2 (E6.S2-AC2, PLAN.md #1.8).

Geen veld in enig antwoordschema mag waarheidswaarschijnlijkheid uitdrukken.
De walker vindt elk dataclass- en pydantic-schema in het pakket automatisch,
zodat ook schema's van latere taken (zoals het API-responsmodel) zonder
registry-onderhoud onder deze guard vallen. Match-zekerheid (`similarity`)
en systeemprecisie blijven toegestaan (B10).
"""

import dataclasses
import importlib
import inspect
import pkgutil

import doublecheck

VERBODEN_TOKENS = (
    "truth",
    "waarheid",
    "veracity",
    "probability",
    "waarschijnlijk",
    "likelihood",
    "credibility",
    "geloofwaardig",
)


def _alle_schemas():
    modules = [doublecheck]
    for info in pkgutil.walk_packages(doublecheck.__path__, prefix="doublecheck."):
        modules.append(importlib.import_module(info.name))
    for module in modules:
        for _, cls in inspect.getmembers(module, inspect.isclass):
            if cls.__module__ != module.__name__:
                continue
            if dataclasses.is_dataclass(cls):
                yield cls, [veld.name for veld in dataclasses.fields(cls)]
            elif hasattr(cls, "model_fields"):
                yield cls, list(cls.model_fields)


def test_response_schema_has_no_truth_probability():
    schemas = list(_alle_schemas())
    assert len(schemas) >= 8, "walker vindt de bestaande schema's niet meer"

    overtredingen = [
        f"{cls.__module__}.{cls.__name__}.{veldnaam}"
        for cls, veldnamen in schemas
        for veldnaam in veldnamen
        if any(token in veldnaam.lower() for token in VERBODEN_TOKENS)
    ]
    assert overtredingen == [], (
        "veld(en) drukken waarheidswaarschijnlijkheid uit (DR2): "
        f"{overtredingen}"
    )
