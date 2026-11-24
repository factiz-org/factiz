"""Een fout melden op elke factcheck (PLAN #34.2at, SPECS E9.S24): een mail met het nummer en de taal in het onderwerp
en alleen wat de machine op die pagina deed, zonder formulier en zonder dat de site iets bewaart."""

from urllib.parse import parse_qs, urlsplit

import pytest
from starlette.testclient import TestClient

from doublecheck import namen as nm
from doublecheck import publiceren as pb
from factiz_site import app as fa
from factiz_site import i18n
from tests.test_factiz_namen import ZELENSKY
from tests.test_factiz_themas import LANDEN, THEMAS
from tests.test_publiceren import REGISTER, _check, _claim, _lab

TALEN = ("en", "nl", "de", "es", "fr")
Z = "Q3874799"


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    map_ = tmp_path_factory.mktemp("melden")
    lab = _lab(map_)
    n = {"vol": _claim(lab, 1, "A video shows Zelensky buying a villa"),
         "zelensky": _claim(lab, 2, "Zelensky bought a yacht"),
         "kaal": _claim(lab, 3, "Something nobody could file")}
    _check(lab, n["vol"], "https://snopes.com/vol", datum="2024-03-05", eigen="Altered")
    _check(lab, n["zelensky"], "https://maldita.es/z", datum="2023-01-01")
    _check(lab, n["kaal"], "https://snopes.com/kaal", datum="")
    lab.commit()
    nr = {k: pb.nummer(v) for k, v in n.items()}
    namen = {"namen": {Z: {"soort": "persoon", "namen": ZELENSKY, "wikis": 150, "paginas": [nr["vol"], nr["zelensky"]]}},
             "per_pagina": {nr["vol"]: [Z], nr["zelensky"]: [Z]}}
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(nm, "MIN_PAGINAS", 2)
        manifest = pb.bouw(lab, map_ / "uit", register=REGISTER, vaag=frozenset(), datum="2026-11-15", themas=THEMAS,
                           landen=LANDEN, namen=namen, soortwoorden={"Altered": "bewerkt"},
                           indeling={nr["vol"]: {"thema": "war", "onderdeel": "", "tweede": "", "land": "UA"}},
                           vertaalmaker="proef", vertalingen={"nl": {nr["vol"]: "Een video toont Zelensky die een villa koopt"}})
    return TestClient(fa.maak_app(manifest["bestand"])), nr


def _mail(melden):
    deel = urlsplit(melden["href"])
    assert deel.scheme == "mailto" and deel.path == fa.CONTACT
    vraag = parse_qs(deel.query)
    return vraag["subject"][0], vraag["body"][0]


@pytest.mark.parametrize("taal", TALEN)
def test_every_fact_check_has_a_link_to_report_an_error_with_its_number_and_address(client, taal):
    c, nr = client
    for sleutel in nr:
        m = c.get(f"/api/{taal}/factcheck/{nr[sleutel]}").json()["melden"]
        onderwerp, tekst = _mail(m)
        assert nr[sleutel] in onderwerp and taal in onderwerp
        assert i18n.BASIS + i18n.pad(taal, "fact-checks", nr[sleutel]) in tekst
        assert m["adres"] == fa.CONTACT and m["vraag"] and m["tekst"] and m["redactie"]
        assert "!" not in m["vraag"] + m["tekst"] + m["redactie"] + tekst


def test_the_mail_lists_only_what_the_machine_did_on_this_page(client):
    c, nr = client
    t = lambda sleutel: i18n.tekst("nl", sleutel)
    _, vol = _mail(c.get(f"/api/nl/factcheck/{nr['vol']}").json()["melden"])
    for sleutel in ("melden_vertaling", "melden_thema", "melden_land", "melden_namen", "melden_kenmerk", "melden_anders"):
        assert t(sleutel) in vol, sleutel
    _, kaal = _mail(c.get(f"/api/nl/factcheck/{nr['kaal']}").json()["melden"])
    for sleutel in ("melden_vertaling", "melden_thema", "melden_land", "melden_namen", "melden_kenmerk"):
        assert t(sleutel) not in kaal, sleutel
    assert t("melden_anders") in kaal
    # in het Engels is de Engelse bewering geen vertaling
    _, engels = _mail(c.get(f"/api/en/factcheck/{nr['kaal']}").json()["melden"])
    assert i18n.tekst("en", "melden_vertaling") not in engels
