"""Het releasebeleid bijt (B22, PLAN #23.7).

Een engine-wijziging is een release. Wie een modelversie of een
poortdrempel in config wijzigt zonder een nieuwe releasekaart in
`docs/RELEASES.md`, krijgt een rode suite — zo kan de resolver niet stil
een andere engine draaien dan de kaart die het publiek leest.
"""

import pathlib
import re

import pytest
from fastapi.testclient import TestClient

import doublecheck.api as api
from doublecheck.config import load_config
from doublecheck.storage import connect, init_schema

WORTEL = pathlib.Path(__file__).resolve().parent.parent
pytestmark = pytest.mark.echte_config

RELEASES = (WORTEL / "docs" / "RELEASES.md").read_text(encoding="utf-8")

# De poortdrempels van wat er is uitgebracht: het aanvraagpad en de
# clustering waar de gepubliceerde cijfers op rusten. De drempels van de
# batchcontrole (stance, screening, NLI) horen bij akte 2 en komen pas op
# de kaart als die capaciteit een release is — tot dan mag dat onderzoek
# vrij afstellen zonder kaartwijziging.
POORTDREMPELS = (
    "text_match",
    "text_match_crosslingual",
    "text_related",
    "image_same",
    "cluster_same",
)


def _huidige_kaart() -> str:
    """De sectie onder '## Huidige release', tot de volgende '## '-kop."""
    start = RELEASES.index("## Huidige release")
    eind = RELEASES.find("\n## ", start + 1)
    return RELEASES[start:] if eind == -1 else RELEASES[start:eind]


def test_the_current_release_card_names_the_engine_in_config():
    """DR6 naar buiten: de modelversies op de kaart zíjn de configwaarden."""
    kaart = _huidige_kaart()
    versies = load_config().model_versions
    for veld in ("text_embedding", "image_hash", "nli"):
        assert getattr(versies, veld) in kaart, veld


def test_the_current_release_card_names_the_reader_and_the_search_of_the_check():
    """B51, #32.12: de lezer en de zoeker van de controle per bericht zijn een versie, net als een model; een andere
    lezer in config zonder kaart is een stille release."""
    kaart = _huidige_kaart()
    controle = load_config().berichtcontrole
    assert f"`lezer = \"{controle.lezer}\"`" in kaart and f"`zoeker = \"{controle.zoeker}\"`" in kaart


def test_the_current_release_card_names_the_model_that_plans_the_searches():
    """B57, #32.41: bij een lezer met zoekvragen vooraf is het kleine model een versie, net als de lezer; een ander
    model in config zonder kaart is een stille release (DR6)."""
    from doublecheck import zoekcontrole as zc

    controle = load_config().berichtcontrole
    if zc.LEZERS[controle.lezer].get("vooraf"):
        assert f"`speurvraag_model = \"{controle.speurvraag_model}\"`" in _huidige_kaart()


def test_the_current_release_card_names_the_source_list_of_the_check():
    """#32.29: de bronnenlijst beslist de kleur van de controle per bericht; een andere lijst zonder kaart is een
    stille release, net als een andere lezer."""
    from doublecheck import bronnen as br

    assert f"`{br.VERSIE}`" in _huidige_kaart()


def test_the_current_release_card_carries_the_gate_thresholds():
    """Een drempel verschuift een poortcijfer, dus een gewijzigde drempel
    zonder nieuwe kaart is een stille release."""
    kaart = _huidige_kaart()
    drempels = load_config().thresholds
    for naam in POORTDREMPELS:
        treffer = re.search(rf"`{naam}`\s+([0-9.]+)", kaart)
        assert treffer, f"{naam} ontbreekt op de releasekaart"
        assert float(treffer.group(1)) == float(getattr(drempels, naam)), naam


@pytest.fixture
def client():
    conn = connect(":memory:")
    init_schema(conn)
    api.app.dependency_overrides[api.get_conn] = lambda: conn
    yield TestClient(api.app)
    api.app.dependency_overrides.clear()
    conn.close()


def test_the_card_states_the_protocol_version_the_resolver_speaks(client):
    """De protocollaag heeft haar eigen versie; de kaart noemt de versie
    die discovery op de draad zet, niet een eigen verhaal."""
    protocol = client.get("/.well-known/doublecheck").json()["protocol"]
    assert f"protocol v{protocol}" in _huidige_kaart()


def test_the_policy_keeps_its_load_bearing_rules():
    """De regels die het beleid eerlijk houden staan er letterlijk: drie
    lagen, geen release zonder verschoven cijfer, de verplichte
    missersectie, en de uitfaseertermijn mét het benoemde gat."""
    vlak = " ".join(RELEASES.split()).lower()
    for laag in ("protocol", "resolver", "corpus"):
        assert laag in vlak, laag
    assert "geen release zonder verschoven cijfer" in vlak
    assert "wat slechter werd" in vlak
    assert "90 dagen" in vlak
    # Het gat is benoemd: vandaag bedient de resolver één beeldschema.
    assert "één beeldschema" in vlak


def test_the_card_names_the_variant_set_and_ocr_mode_the_resolver_uses():
    """#25.17, #25.21: claimvarianten en OCR per schrift veranderen wat de
    resolver antwoordt. Staan ze aan, dan noemt de kaart ze; staan ze uit,
    dan beweert de kaart ze niet."""
    kaart = _huidige_kaart()
    config = load_config()
    if config.varianten.in_resolver:
        assert "`[varianten] in_resolver = true`" in kaart
        assert "claude-haiku-5-5/vertalingen-v1" in kaart
    else:
        assert "`[varianten] in_resolver = true`" not in kaart
    # #25.36: een vraag ook als bewering zoeken verschuift cijfers.
    if config.vraagvorm.aan:
        assert "`[vraagvorm] aan = true`" in kaart
    else:
        assert "`[vraagvorm] aan = true`" not in kaart
    if config.ocr.per_schrift:
        assert "`[ocr] per_schrift = true`" in kaart
        assert f"schrift_zekerheid` {config.ocr.schrift_zekerheid}" in kaart
    else:
        assert "`[ocr] per_schrift = true`" not in kaart


def test_the_card_names_the_doubt_band_when_it_is_on():
    """#25.22: tussen `schrift_ondergrens` en `schrift_zekerheid` leest de
    OCR twee keer. Staat die band aan, dan noemt de kaart de ondergrens en de
    schriftcontrole; staat hij uit, dan beweert de kaart hem niet."""
    kaart = _huidige_kaart()
    ocr = load_config().ocr
    if ocr.per_schrift and ocr.schrift_ondergrens < ocr.schrift_zekerheid:
        assert f"`schrift_ondergrens` {ocr.schrift_ondergrens}" in kaart
        assert f"`schrift_min_aandeel` {ocr.schrift_min_aandeel}" in kaart
    else:
        assert "`schrift_ondergrens`" not in kaart


def test_the_card_names_the_judge_and_its_thresholds_when_it_is_on():
    """#30.3: de rechter beslist mee over `matched`. Staat hij aan, dan
    noemt de kaart de versie uit de gewichten en zijn drie drempels; staat
    hij uit, dan beweert de kaart hem niet."""
    kaart = _huidige_kaart()
    config = load_config()
    if config.rechter.aan:
        assert f"`{config.rechter.model}`" in kaart
        assert f"`[rechter] aan = true`" in kaart
        assert f"diepte {config.rechter.diepte}" in kaart
        for naam in ("rechter_vloer", "rechter_zelfde", "rechter_veto"):
            treffer = re.search(rf"`{naam}`\s+([0-9.]+)", kaart)
            assert treffer, f"{naam} ontbreekt op de releasekaart"
            assert float(treffer.group(1)) == float(getattr(config.thresholds, naam)), naam
    else:
        assert "`[rechter] aan = true`" not in kaart


def test_the_card_names_the_fact_layer_and_its_thresholds_when_it_is_on():
    """#30.3b: de feitenlaag houdt een rood oordeel naast een vastgesteld
    feit weg van `matched`. Aan: de kaart noemt de schakelaar en beide
    drempels. Uit: de kaart beweert haar niet."""
    kaart = _huidige_kaart()
    config = load_config()
    if config.feiten.aan:
        assert "`[feiten] aan = true`" in kaart
        for naam in ("feit_vloer", "feit_zelfde"):
            treffer = re.search(rf"`{naam}`\s+([0-9.]+)", kaart)
            assert treffer, f"{naam} ontbreekt op de releasekaart"
            assert float(treffer.group(1)) == float(getattr(config.thresholds, naam)), naam
    else:
        assert "`[feiten] aan = true`" not in kaart


def test_the_judge_weights_are_found_from_the_repo_root():
    """Het pad naar de gewichten is relatief, zodat dezelfde config op de
    server werkt (deploy/factiz.service draait vanuit de kloon)."""
    rechter = load_config().rechter
    if rechter.aan:
        assert not pathlib.Path(rechter.pad).is_absolute()


def test_the_card_names_the_check_and_its_versions_when_it_is_on():
    """#31.12: de controle per bericht. Aan: de kaart noemt de schakelaar, het
    model, de vraag, de herkansing, de feitenstap, de ijking van de meter en elke
    stap die aan staat (vorm, detail, beweringen eerst, de vloer).
    Uit: de kaart beweert haar niet."""
    kaart = _huidige_kaart()
    controle = load_config().berichtcontrole
    if controle.aan:
        assert "`[berichtcontrole] aan = true`" in kaart
        stappen = tuple(v for v in (controle.vorm, controle.detail, controle.beweringen, controle.vloer) if v)
        for waarde in (controle.model_id, controle.vraag, controle.herkansing, controle.feitenstap,
                       pathlib.Path(controle.ijking).stem) + stappen:
            assert f"`{waarde}`" in kaart, waarde
    else:
        assert "`[berichtcontrole] aan = true`" not in kaart
