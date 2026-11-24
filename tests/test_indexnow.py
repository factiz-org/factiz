"""IndexNow (PLAN #34.2bt, SPECS E9.S8 AC7): bij een uitgave in een open stand de nieuwe en gewijzigde factchecks melden,
alleen in de talen waar ze in die stand vindbaar zijn, in delen van hoogstens 10.000, met de openbare sleutel. In stand 0,
of zonder de vorige uitgave om mee te vergelijken, nooit."""

from pathlib import Path

import pytest

from doublecheck import indexnow as ix
from doublecheck import publiceren as pb
from tests.test_publiceren import REGISTER, _check, _claim, _lab

WORTEL = Path(__file__).resolve().parent.parent


def _uitgave(map_, naam, met_telugu, tweede_check, nl):
    (map_ / naam).mkdir()
    lab = _lab(map_ / naam)
    villa = _claim(lab, 1, "Zelensky bought a villa in Florida")
    jacht = _claim(lab, 2, "Zelenski compró un yate de lujo", taal="es")
    _check(lab, villa, "https://snopes.com/villa", datum="2024-03-05")
    if tweede_check:
        _check(lab, villa, "https://factcheck.afp.com/villa", datum="2025-01-02", taal="fr", eigen="Faux")
    _check(lab, jacht, "https://maldita.es/yate", datum="2023-12-01", taal="es", eigen="Bulo")
    vertalingen = {"nl": {pb.nummer(villa): "Zelensky kocht een villa in Florida"}} if nl else {}
    if met_telugu:
        telugu = _claim(lab, 3, "పచ్చి పాల వలన లాక్టోస్ అసహనం తగ్గుతుంది", taal="te")
        _check(lab, telugu, "https://snopes.com/milk", datum="2025-02-03")
        vertalingen["en"] = {pb.nummer(telugu): "Raw milk reduces lactose intolerance"}
    lab.commit()
    return pb.bouw(lab, map_ / naam / "uit", register=REGISTER, vaag=frozenset(), datum="2026-11-17",
                   vertaalmaker="proef", vertalingen=vertalingen)["bestand"], {
        "villa": pb.nummer(villa), "jacht": pb.nummer(jacht), "telugu": pb.nummer(_claim_id(3))}


def _claim_id(n):
    return f"gfc-{n:016x}"


@pytest.fixture(scope="module")
def twee(tmp_path_factory):
    map_ = tmp_path_factory.mktemp("indexnow")
    vorige, _ = _uitgave(map_, "vorige", met_telugu=False, tweede_check=False, nl=False)
    nieuwe, nr = _uitgave(map_, "nieuwe", met_telugu=True, tweede_check=True, nl=True)
    return vorige, nieuwe, nr


def test_only_new_and_changed_fact_checks_are_reported_where_they_are_findable(twee):
    vorige, nieuwe, nr = twee
    site = "https://factiz.org"
    # de villa kreeg een check en een Nederlandse vertaling, de Telugu-bewering is nieuw, de jacht bleef gelijk
    assert ix.nieuwe_adressen(vorige, nieuwe, 3) == sorted([
        f"{site}/fact-checks/{nr['villa']}/", f"{site}/nl/fact-checks/{nr['villa']}/", f"{site}/fact-checks/{nr['telugu']}/"])
    assert ix.nieuwe_adressen(vorige, nieuwe, 2) == sorted([
        f"{site}/fact-checks/{nr['villa']}/", f"{site}/fact-checks/{nr['telugu']}/"])
    # in stand 1 alleen de kern: de villa heeft nu twee redacties
    assert ix.nieuwe_adressen(vorige, nieuwe, 1) == [f"{site}/fact-checks/{nr['villa']}/"]


def test_a_report_goes_in_parts_of_at_most_10000_with_the_key_and_where_it_stands():
    gestuurd = []
    adressen = [f"https://factiz.org/fact-checks/{i:016x}/" for i in range(25001)]
    uit = ix.meld(adressen, stuur=lambda bericht: gestuurd.append(bericht) or 202)
    assert uit == {"gemeld": 25001, "antwoorden": [202, 202, 202]}
    assert [len(b["urlList"]) for b in gestuurd] == [10000, 10000, 5001]
    assert [a for b in gestuurd for a in b["urlList"]] == adressen
    assert gestuurd[0] == {"host": "factiz.org", "key": ix.SLEUTEL, "keyLocation": f"https://factiz.org/{ix.SLEUTEL}.txt",
                           "urlList": adressen[:10000]}


def test_nothing_but_pages_of_factiz_org_is_ever_reported():
    for adres in ("https://evil.example/x", "http://factiz.org/x", "https://factiz.org.evil.example/x"):
        with pytest.raises(ValueError):
            ix.meld([adres], stuur=lambda bericht: pytest.fail("verstuurd"))


def test_closed_or_without_the_previous_release_nothing_is_reported(twee):
    vorige, nieuwe, _ = twee
    nooit = lambda bericht: pytest.fail("verstuurd")
    assert ix.melden(0, vorige, nieuwe, stuur=nooit) == {"gemeld": 0, "reden": "dicht"}
    assert ix.melden(1, None, nieuwe, stuur=nooit) == {"gemeld": 0, "reden": "geen vorige uitgave om mee te vergelijken"}
    gestuurd = []
    assert ix.melden(3, vorige, nieuwe, stuur=lambda b: gestuurd.append(b) or 200)["gemeld"] == 3 and len(gestuurd) == 1


def test_the_step_comes_from_the_config_of_the_worker_and_only_the_po_changes_it():
    assert ix.stand_uit('"vars": { "FACTIZ_VINDBAAR": "1" }') == 1
    assert ix.stand_uit('"vars": {"FACTIZ_VINDBAAR":"2"}') == 2 and ix.stand_uit('"FACTIZ_VINDBAAR": "3"') == 3
    for tekst in ('"vars": { "FACTIZ_VINDBAAR": "0" }', '"vars": { "FACTIZ_VINDBAAR": "4" }', "{}", ""):
        assert ix.stand_uit(tekst) == 0, tekst
    # de stand van factiz.org zelf: 2 sinds 2026-11-22 (PO: "etappe 2 live", B73); een andere stand is een eigen besluit
    assert ix.stand_uit((WORTEL / "site" / "wrangler.jsonc").read_text(encoding="utf-8")) == 2


def test_a_new_or_changed_own_check_is_reported_where_search_engines_see_it_with_its_month_and_the_radar(tmp_path):
    """PLAN #37.11 (SPECS E10.S4 AC8): een uitrol meldt een eigen check die erbij kwam of veranderde, in elke taal waarin
    zoekmachines haar zien, met de Radar en haar maand; een ongelezen vertaling en een concept nooit."""
    from tests import test_factiz_eigen as fe
    from tests import test_redactie as tr

    gelezen = {"en": {**fe._engels(), "nagelezen": True}}
    vorige = fe._bouw(tmp_path / "vorige", [fe._gepubliceerd(sleutel="oud")])["bestand"]
    nieuwe = fe._bouw(tmp_path / "nieuwe", [fe._gepubliceerd(sleutel="oud"), fe._gepubliceerd(vertalingen=gelezen),
                                           tr._check(sleutel="proef")], concepten=True)["bestand"]
    site = "https://factiz.org"
    assert [a for a in ix.nieuwe_adressen(vorige, nieuwe, 1) if "/radar/" in a] == sorted([
        f"{site}/nl/radar/", f"{site}/nl/radar/2026/12/", f"{site}/nl/radar/2026/12/gepubliceerd-check-nl/",
        f"{site}/radar/", f"{site}/radar/2026/12/", f"{site}/radar/2026/12/gepubliceerd-check-en/"])
    # zonder veranderingen niets
    assert [a for a in ix.nieuwe_adressen(nieuwe, nieuwe, 1) if "/radar/" in a] == []


def test_an_older_previous_edition_is_read_with_the_rule_of_its_own_schema(twee, tmp_path):
    """De vorige uitgave kan een ouder schema hebben (2026-11-23: 23c, schema 19, zonder `vertaling.voorlopig` en met
    afscherming; een van voor schema 17 heeft ook geen afscherming): de regel van de sitemaps volgt haar schemanummer."""
    import shutil
    import sqlite3

    vorige, nieuwe, nr = twee
    for schema in (19, 16):
        oud = tmp_path / f"schema-{schema}.db"
        shutil.copy(vorige, oud)
        c = sqlite3.connect(oud)
        c.execute("ALTER TABLE vertaling DROP COLUMN voorlopig")
        if schema < 17:
            c.execute("DROP TABLE afscherming")
        c.execute("UPDATE meta SET waarde = ? WHERE sleutel = 'schema'", (str(schema),))
        c.commit()
        c.close()
        assert ix.nieuwe_adressen(oud, nieuwe, 2) == ix.nieuwe_adressen(vorige, nieuwe, 2), schema
