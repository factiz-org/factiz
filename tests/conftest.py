"""Gedeelde test-opzet.

De rate-limiter (#20.2) zit op de gedeelde app-singleton `doublecheck.api.app`.
Verschillende testlussen vuren tientallen verzoeken achter elkaar; die zouden
tegen de productiegrens aanlopen. Zet hem daarom uit voor de hele suite — de
limiter zelf wordt getoetst in `test_ratelimit.py`, op eigen app-instanties met
hun eigen grens.
"""

import pytest


@pytest.fixture(autouse=True)
def _rate_limit_uit():
    import doublecheck.api as api

    was = api.limiter.enabled
    api.limiter.enabled = False
    try:
        yield
    finally:
        api.limiter.enabled = was


# De rechter en de feitenlaag (#30.3, #30.3b) staan in productie aan, maar de
# gewichten van de rechter (2,1 GB) zitten niet in git en hun gedrag meten de
# zeef en de kerncheck, niet de suite. Zonder deze stand faalt een schone
# kloon op elke test die `/resolve` raakt, en meet een test met de echte
# rechter het model in plaats van de code. Dus toetst de suite het aanvraagpad
# standaard met beide uit, met verder precies `config.toml`; een test die de
# rechter nodig heeft, zet hem zelf aan met een nep-rechter
# (`tests/test_rechter_api.py`). Tests over de kaart en de site lezen de echte
# config met `@pytest.mark.echte_config`.
@pytest.fixture(scope="session")
def _config_zonder_rechter(tmp_path_factory):
    import re

    import doublecheck.config as config

    tekst = config._DEFAULT_PATH.read_text(encoding="utf-8")
    tekst = re.sub(r"(^\[(?:rechter|feiten)\]\n(?:(?!^\[).*\n)*?)^aan = true$", r"\1aan = false",
                   tekst, flags=re.M)
    pad = tmp_path_factory.mktemp("config") / "config.toml"
    pad.write_text(tekst, encoding="utf-8")
    geladen = config.load_config(pad)
    assert not geladen.rechter.aan and not geladen.feiten.aan
    return pad


@pytest.fixture(autouse=True)
def _rechter_uit(request, monkeypatch, _config_zonder_rechter):
    if request.node.get_closest_marker("echte_config"):
        return
    import doublecheck.config as config

    monkeypatch.setattr(config, "_DEFAULT_PATH", _config_zonder_rechter)
