"""Elk toetsenbord (PO 2026-11-15: "en ook de zoekvelden nemen elke taal aan, ondersteunen elk toetsenbord vanuit de
browser etc?"; PLAN #34.2be): wat een toetsenbord anders typt dan de tekst schrijft, vindt toch hetzelfde. Brede letters
van een Chinees of Japans toetsenbord, en ک/ك en ی/ي van een Perzisch of Arabisch toetsenbord. In de zoekvelden: een
invoermethode die een teken samenstelt houdt haar toetsen, en getypte tekst neemt haar eigen richting."""

from pathlib import Path

import pytest

from doublecheck import publiceren as pb
from factiz_site import db
from tests.test_publiceren import REGISTER, _check, _claim, _lab

SITE = Path(__file__).resolve().parent.parent / "site" / "src" / "components" / "site"


@pytest.fixture(scope="module")
def pub(tmp_path_factory):
    map_ = tmp_path_factory.mktemp("toetsenbord")
    lab = _lab(map_)
    n = {"perzisch": _claim(lab, 1, "ویروس کرونا در ایران ساخته شد", taal="fa"),
         "arabisch": _claim(lab, 2, "فيروس كرونا صنع في مختبر", taal="ar"),
         "vaccin": _claim(lab, 3, "The vaccine contains a microchip")}
    for i, sleutel in enumerate(n):
        _check(lab, n[sleutel], f"https://snopes.com/t{i}", taal="en")
    lab.commit()
    m = pb.bouw(lab, map_ / "uit", register=REGISTER, vaag=frozenset(), datum="2026-11-15")
    return db.Publicatie(m["bestand"]), {k: pb.nummer(v) for k, v in n.items()}


def _nummers(pub, vraag):
    return {r["nummer"] for r in pub.zoek_ruim(vraag, 1, "en")["rijen"]}


def test_a_word_typed_on_a_persian_or_an_arabic_keyboard_finds_both_spellings(pub):
    p, nr = pub
    beide = {nr["perzisch"], nr["arabisch"]}
    assert _nummers(p, "کرونا") == beide          # Perzische kaf
    assert _nummers(p, "كرونا") == beide          # Arabische kaf
    assert db.toetsenbordvormen("كرونا") == ["کرونا"] and db.toetsenbordvormen("ایران") == ["ايران"]
    assert db.toetsenbordvormen("corona") == []


def test_wide_letters_from_a_chinese_or_japanese_keyboard_find_the_ordinary_word(pub):
    p, nr = pub
    assert _nummers(p, "ｖａｃｃｉｎｅ") == {nr["vaccin"]} == _nummers(p, "vaccine")


def test_the_search_fields_leave_an_input_method_its_keys_and_take_the_direction_of_what_is_typed():
    zoeken = (SITE / "zoeken.jsx").read_text(encoding="utf-8")
    assert "if (e.nativeEvent?.isComposing || e.keyCode === 229) return;" in zoeken
    assert "if (samenstellen || RTL_TEKEN.test(waarde)) return '';" in zoeken
    for naam in ("Zoekveld.jsx", "Zoekpalet.jsx"):
        bron = (SITE / naam).read_text(encoding="utf-8")
        assert "useSamenstellen()" in bron and "if (!samenstellen) kies(regels[actief])" in bron, naam
        assert 'dir="auto" {...opties}' in bron, naam
    for naam in ("Taalkiezer.jsx", "Bibliotheek.jsx", "NetwerkKaart.jsx"):
        assert 'type="search" dir="auto"' in (SITE / naam).read_text(encoding="utf-8"), naam
