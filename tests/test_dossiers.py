"""De dossiers van het platform (PLAN #33.6, SPECS E9.S7): het bestand, het voorstellen en het goedkeuren."""

import copy
import json

import pytest

from doublecheck import dossiers as ds
from doublecheck import publiceren as pb
from tests.test_publiceren import REGISTER, _check, _claim, _lab

THEMAS = [{"sleutel": "war", "onderdelen": [{"sleutel": "ukraine"}]}, {"sleutel": "health", "onderdelen": []}]
EEN, TWEE, DRIE = "00000000000000a1", "00000000000000a2", "00000000000000a3"


def _vijf(tekst):
    return {taal: f"{tekst} ({taal})" for taal in ds.SITETALEN}


def _ruw(**anders):
    ruw = {"soort": "verhaal", "status": "concept", "thema": "war", "onderdeel": "ukraine",
           "naam": _vijf("Zelensky buys luxury"), "inleiding": _vijf("A recurring story about villas and yachts."),
           "nagelezen": {taal: False for taal in ds.SITETALEN},
           "item": [{"soort": "onderzoek", "datum": "2023-12-20", "bron": "BBC Verify",
                     "url": "https://www.bbc.com/news/world-us-canada-67766964", "titel": _vijf("How the yacht story travelled")}],
           "voorstel": {"woorden": ["zelensky", "zelenska"], "omschrijving": "Claims that Zelensky bought luxury goods."}}
    ruw.update(anders)
    return ruw


def _netwerk(**anders):
    return _ruw(soort="netwerk", vastgesteld={"door": "EU DisinfoLab", "url": "https://www.disinfo.eu/doppelganger",
                                              "datum": "2022-09-27"}, **anders)


def _goed(*nummers):
    return {"goedgekeurd_door": "PO", "datum": "2026-11-12", "factchecks": [{"nummer": n} for n in nummers]}


def test_a_complete_story_dossier_is_read_with_its_items_and_only_the_approved_fact_checks():
    d = ds.keur("zelensky-luxury", _ruw(), _goed(EEN, TWEE))
    assert d["sleutel"] == "zelensky-luxury" and d["soort"] == "verhaal" and d["status"] == "concept"
    assert d["thema"] == "war" and d["onderdeel"] == "ukraine" and d["verwant"] == [] and d["vastgesteld"] is None
    assert d["naam"]["nl"] == "Zelensky buys luxury (nl)" and set(d["inleiding"]) == set(ds.SITETALEN)
    assert d["items"] == [{"soort": "onderzoek", "datum": "2023-12-20", "bron": "BBC Verify",
                           "url": "https://www.bbc.com/news/world-us-canada-67766964",
                           "titel": _vijf("How the yacht story travelled")}]
    assert d["factchecks"] == [{"nummer": EEN}, {"nummer": TWEE}]
    # zonder goedkeuring staat er geen factcheck in: een voorstel van een model is geen plek in het dossier (AC3)
    assert ds.keur("zelensky-luxury", _ruw(), None)["factchecks"] == []


@pytest.mark.parametrize("breek, waarom", [
    (lambda r: r.pop("naam"), "naam"),
    (lambda r: r["naam"].pop("fr"), "naam"),
    (lambda r: r["inleiding"].update(de="  "), "inleiding"),
    (lambda r: r.update(tema="war"), "tema"),
    (lambda r: r.update(soort="thema"), "soort"),
    (lambda r: r.update(status="live"), "status"),
    (lambda r: r["item"][0].pop("bron"), "bron"),
    (lambda r: r["item"][0].update(soort="factcheck"), "soort"),
    (lambda r: r["item"][0]["titel"].pop("es"), "titel"),
    (lambda r: r["item"][0].update(kleur="rood"), "kleur"),
    (lambda r: r["nagelezen"].pop("nl"), "nagelezen"),
    (lambda r: r.update(naam={**r["naam"], "en": "regel een\nregel twee"}), "naam"),
])
def test_a_missing_empty_or_unknown_field_is_refused_with_its_name(breek, waarom):
    ruw = _ruw()
    breek(ruw)
    with pytest.raises(ds.Weigering, match=waarom):
        ds.keur("zelensky-luxury", ruw, None)


@pytest.mark.parametrize("veld, waarde", [
    ("datum", "2023-12"), ("datum", "2023-02-30"), ("datum", "20 December 2023"), ("datum", ""),
    ("url", "javascript:alert(1)"), ("url", "www.bbc.com/news"), ("url", "ftp://bbc.com/x"), ("url", ""),
])
def test_a_date_that_is_not_a_day_or_a_link_that_is_not_a_web_address_is_refused(veld, waarde):
    ruw = _ruw()
    ruw["item"][0][veld] = waarde
    with pytest.raises(ds.Weigering, match=veld):
        ds.keur("zelensky-luxury", ruw, None)


@pytest.mark.parametrize("sleutel", ["Zelensky", "a", "zelensky luxury", "../etc", "zelensky_luxury", "-start", "x" * 60])
def test_a_key_that_is_not_a_plain_lowercase_name_is_refused(sleutel):
    with pytest.raises(ds.Weigering, match="sleutel"):
        ds.keur(sleutel, _ruw(), None)


def test_an_approval_needs_the_date_and_the_words_of_the_po():
    with pytest.raises(ds.Weigering, match="akkoord"):
        ds.keur("zelensky-luxury", _ruw(status="akkoord"), None)
    with pytest.raises(ds.Weigering, match="akkoord"):
        ds.keur("zelensky-luxury", _ruw(status="akkoord", akkoord="ja"), None)
    d = ds.keur("zelensky-luxury", _ruw(status="akkoord", akkoord='2026-11-12, PO: "ja, zet maar live"'), None)
    assert d["status"] == "akkoord"
    # en een concept draagt geen akkoord: dat zou een half besluit zijn
    with pytest.raises(ds.Weigering, match="akkoord"):
        ds.keur("zelensky-luxury", _ruw(akkoord='2026-11-12, PO: "ja"'), None)


def test_a_network_dossier_names_who_identified_it_and_every_fact_check_carries_its_source_and_level():
    bron = {"niveau": "toegeschreven", "bron": "EUvsDisinfo", "url": "https://euvsdisinfo.eu/report/x"}
    d = ds.keur("doppelganger", _netwerk(), {**_goed(), "factchecks": [{"nummer": EEN, **bron}]})
    assert d["vastgesteld"] == {"door": "EU DisinfoLab", "url": "https://www.disinfo.eu/doppelganger", "datum": "2022-09-27"}
    assert d["factchecks"] == [{"nummer": EEN, **bron}]
    with pytest.raises(ds.Weigering, match="vastgesteld"):
        ds.keur("doppelganger", _ruw(soort="netwerk"), None)
    for mis in ("niveau", "bron", "url"):
        half = {"nummer": EEN, **{k: v for k, v in bron.items() if k != mis}}
        with pytest.raises(ds.Weigering, match=mis):
            ds.keur("doppelganger", _netwerk(), {**_goed(), "factchecks": [half]})
    with pytest.raises(ds.Weigering, match="niveau"):
        ds.keur("doppelganger", _netwerk(), {**_goed(), "factchecks": [{"nummer": EEN, **bron, "niveau": "lijkt erop"}]})
    # een verhaaldossier noemt geen vaststeller: een verhaal is van niemand
    with pytest.raises(ds.Weigering, match="vastgesteld"):
        ds.keur("zelensky-luxury", _ruw(vastgesteld={"door": "x", "url": "https://x.org/y", "datum": "2022-09-27"}), None)


@pytest.mark.parametrize("factchecks, waarom", [
    ([{"nummer": "gfc-00000000000000a1"}], "nummer"), ([{"nummer": "A" * 16}], "nummer"), ([{}], "nummer"),
    ([{"nummer": EEN}, {"nummer": EEN}], "twee keer"), ([{"nummer": EEN, "kleur": "rood"}], "kleur"),
])
def test_an_approved_fact_check_needs_a_real_number_once(factchecks, waarom):
    with pytest.raises(ds.Weigering, match=waarom):
        ds.keur("zelensky-luxury", _ruw(), {**_goed(), "factchecks": factchecks})


def test_an_approval_file_without_who_and_when_is_refused():
    for mis in ("goedgekeurd_door", "datum"):
        goed = _goed(EEN)
        goed.pop(mis)
        with pytest.raises(ds.Weigering, match=mis):
            ds.keur("zelensky-luxury", _ruw(), goed)


TOML = '''
soort = "verhaal"
status = "concept"
thema = "war"
onderdeel = "ukraine"
verwant = []

[naam]
nl = "Zelensky koopt luxe"
en = "Zelensky buys luxury"
de = "Selenskyj kauft Luxus"
es = "Zelenski compra lujo"
fr = "Zelensky achète du luxe"

[inleiding]
nl = "Een verhaal dat terugkomt."
en = "A story that keeps coming back."
de = "Eine Geschichte, die wiederkehrt."
es = "Una historia que vuelve."
fr = "Une histoire qui revient."

[nagelezen]
nl = true
en = false
de = false
es = false
fr = false

[[item]]
soort = "pers"
datum = "2023-12-20"
bron = "BBC"
url = "https://www.bbc.com/news/x"
titel = { nl = "Hoe het jachtverhaal reisde", en = "How the yacht story travelled", de = "d", es = "e", fr = "f" }

[voorstel]
woorden = ["zelensky"]
omschrijving = "Claims that Zelensky bought luxury goods."
'''


def _schrijf(map_, sleutel, toml=TOML, factchecks=None):
    (map_ / sleutel).mkdir(parents=True)
    (map_ / sleutel / "dossier.toml").write_text(toml, encoding="utf-8")
    if factchecks is not None:
        (map_ / sleutel / "factchecks.json").write_text(json.dumps(factchecks), encoding="utf-8")


def test_the_folder_name_is_the_key_and_both_files_are_read(tmp_path):
    _schrijf(tmp_path, "zelensky-luxury", factchecks=_goed(EEN))
    d = ds.lees_dossier(tmp_path / "zelensky-luxury")
    assert d["sleutel"] == "zelensky-luxury" and d["naam"]["de"] == "Selenskyj kauft Luxus"
    assert d["nagelezen"]["nl"] is True and d["items"][0]["titel"]["nl"] == "Hoe het jachtverhaal reisde"
    assert d["factchecks"] == [{"nummer": EEN}] and d["voorstel"]["woorden"] == ["zelensky"]
    # een map zonder dossier.toml is geen dossier, en een bestand dat geen TOML is, wordt geweigerd met zijn naam
    (tmp_path / "leeg").mkdir()
    with pytest.raises(ds.Weigering, match="leeg"):
        ds.lees_dossier(tmp_path / "leeg")
    _schrijf(tmp_path, "kapot", toml="soort = ")
    with pytest.raises(ds.Weigering, match="kapot"):
        ds.lees_dossier(tmp_path / "kapot")


def test_all_dossiers_are_read_in_a_fixed_order_and_a_missing_folder_means_there_are_none(tmp_path):
    assert ds.lees_alle(tmp_path / "bestaat-niet") == []
    _schrijf(tmp_path, "zelensky-luxury")
    _schrijf(tmp_path, "biolabs")
    assert [d["sleutel"] for d in ds.lees_alle(tmp_path, THEMAS)] == ["biolabs", "zelensky-luxury"]


def test_a_related_dossier_that_does_not_exist_and_a_theme_outside_the_list_are_refused(tmp_path):
    _schrijf(tmp_path, "zelensky-luxury", toml=TOML.replace("verwant = []", 'verwant = ["biolabs"]'))
    with pytest.raises(ds.Weigering, match="biolabs"):
        ds.lees_alle(tmp_path, THEMAS)
    _schrijf(tmp_path, "biolabs", toml=TOML.replace("verwant = []", 'verwant = ["biolabs"]'))
    with pytest.raises(ds.Weigering, match="zichzelf"):
        ds.lees_alle(tmp_path, THEMAS)
    (tmp_path / "biolabs" / "dossier.toml").write_text(TOML.replace('thema = "war"', 'thema = "astrology"'), "utf-8")
    with pytest.raises(ds.Weigering, match="astrology"):
        ds.lees_alle(tmp_path, THEMAS)
    (tmp_path / "biolabs" / "dossier.toml").write_text(TOML.replace('thema = "war"', 'thema = "health"'), "utf-8")
    with pytest.raises(ds.Weigering, match="ukraine"):          # een onderdeel van een ander thema
        ds.lees_alle(tmp_path, THEMAS)
    (tmp_path / "biolabs" / "dossier.toml").write_text(TOML, "utf-8")
    assert len(ds.lees_alle(tmp_path, THEMAS)) == 2
    # zonder lijst van thema's (een uitgave zonder thema's) wordt het thema niet getoetst
    (tmp_path / "biolabs" / "dossier.toml").write_text(TOML.replace('thema = "war"', 'thema = "astrology"'), "utf-8")
    assert len(ds.lees_alle(tmp_path)) == 2


def test_one_fact_check_sits_in_at_most_one_story_dossier_but_may_also_sit_in_a_network(tmp_path):
    _schrijf(tmp_path, "zelensky-luxury", factchecks=_goed(EEN, TWEE))
    _schrijf(tmp_path, "biolabs", factchecks=_goed(TWEE))
    with pytest.raises(ds.Weigering, match=TWEE):
        ds.lees_alle(tmp_path, THEMAS)
    netwerk = TOML.replace('soort = "verhaal"', 'soort = "netwerk"') + (
        '\n[vastgesteld]\ndoor = "EU DisinfoLab"\nurl = "https://www.disinfo.eu/x"\ndatum = "2022-09-27"\n')
    (tmp_path / "biolabs" / "dossier.toml").write_text(netwerk, "utf-8")
    (tmp_path / "biolabs" / "factchecks.json").write_text(json.dumps({**_goed(), "factchecks": [
        {"nummer": TWEE, "niveau": "waargenomen", "bron": "EUvsDisinfo", "url": "https://euvsdisinfo.eu/report/x"}]}), "utf-8")
    assert len(ds.lees_alle(tmp_path, THEMAS)) == 2


# --- voorstellen ---------------------------------------------------------------------------------------------------

def _uitgave(tmp_path):
    lab = _lab(tmp_path)
    n = {"villa": _claim(lab, 1, "Zelensky bought a villa in Florida"),
         "hindi": _claim(lab, 2, "ज़ेलेंस्की ने एक नौका खरीदी", taal="hi"),
         "japans": _claim(lab, 3, "ゼレンスキー大統領がチャールズ3世の邸宅を購入した", taal="ja"),
         "bezit": _claim(lab, 4, "Zelenskyy's wife owns a Bugatti"),
         "ander": _claim(lab, 5, "The moon is made of cheese")}
    for i, c in enumerate(n.values()):
        _check(lab, c, f"https://snopes.com/{i}", datum=f"2024-0{i + 1}-01")
    lab.commit()
    nummers = {k: pb.nummer(v) for k, v in n.items()}
    m = pb.bouw(lab, tmp_path / "uit", register=REGISTER, vaag=frozenset(), datum="2026-11-11",
                vertalingen={"nl": {nummers["hindi"]: "Zelensky kocht een jacht"}}, vertaalmaker="proef")
    return ds.open_uitgave(m["bestand"]), nummers


def test_candidates_are_every_page_with_one_of_the_words_in_the_claim_or_in_a_translation_in_any_script(tmp_path):
    pub, n = _uitgave(tmp_path)
    # het woord in de bewering, in een vertaling (Hindi), als deel van een woord (Zelenskyy's) en in een schrift
    # zonder spaties (Japans, met het eigen woord)
    assert set(ds.kandidaten(pub, ["zelensky"])) == {n["villa"], n["hindi"], n["bezit"]}
    assert set(ds.kandidaten(pub, ["zelensky", "ゼレンスキー"])) == {n["villa"], n["hindi"], n["bezit"], n["japans"]}
    assert ds.kandidaten(pub, ["zelensky"]) == sorted(ds.kandidaten(pub, ["zelensky"]))
    assert ds.kandidaten(pub, []) == [] and ds.kandidaten(pub, ['"', " ", "ab"]) == []
    # een woord is nooit een opdracht aan het zoekregister
    assert ds.kandidaten(pub, ['zelensky" OR "moon']) == []


def test_the_request_names_the_story_numbers_the_claims_and_asks_for_no_verdict_on_truth():
    d = ds.keur("zelensky-luxury", _ruw(), None)
    v = ds.voorstelverzoek(d, [("Zelensky bought a villa", "en"), ("Selenskyj kauft\neine Jacht " + "x" * 900, "de")])
    assert v["model"] == "claude-haiku-5-5" and "Zelensky buys luxury (en)" in v["system"]
    assert "Claims that Zelensky bought luxury goods." in v["system"] and "do not judge whether" in v["system"].lower()
    tekst = v["messages"][0]["content"][0]["text"]
    assert tekst.startswith("1. (en) Zelensky bought a villa\n2. (de) Selenskyj kauft eine Jacht x")
    assert len(tekst.splitlines()) == 2 and len(tekst) < 700           # één regel per bewering, afgekapt
    eigenschappen = v["output_config"]["format"]["schema"]["properties"]["antwoorden"]["items"]["properties"]
    assert eigenschappen["oordeel"]["enum"] == ["ja", "nee", "twijfel"]
    with pytest.raises(ds.Weigering, match="omschrijving"):
        ds.voorstelverzoek(ds.keur("x-y", {k: w for k, w in _ruw().items() if k != "voorstel"}, None), [("a", "en")])
    with pytest.raises(ds.Weigering, match="netwerk"):
        ds.voorstelverzoek(ds.keur("doppelganger", _netwerk(), None), [("a", "en")])


def test_an_answer_counts_only_with_a_known_verdict_and_a_number_that_occurs_once():
    antwoord = json.dumps({"antwoorden": [
        {"nr": 1, "oordeel": "ja", "reden": "villa bought\nwith aid"}, {"nr": 2, "oordeel": "misschien", "reden": "x"},
        {"nr": 3, "oordeel": "nee", "reden": "about the moon"}, {"nr": 3, "oordeel": "ja", "reden": "x"},
        {"nr": 9, "oordeel": "ja", "reden": "x"}, {"nr": 4, "oordeel": "twijfel", "reden": "r" * 500}, "rommel"]})
    gelezen = ds.lees_voorstel(antwoord, 5)
    assert gelezen[0] == {"oordeel": "ja", "reden": "villa bought with aid"}
    assert gelezen[1] is None and gelezen[2] is None and gelezen[4] is None      # onbekend, twee keer, niet beantwoord
    assert gelezen[3]["oordeel"] == "twijfel" and len(gelezen[3]["reden"]) <= 120
    for rommel in (None, "", "geen json", "[]", json.dumps({"antwoorden": "ja"})):
        assert ds.lees_voorstel(rommel, 3) == [None, None, None]


def _pagina(nummer, tekst, taal="en", datum="2024-03-01"):
    return {"nummer": nummer, "bewering": tekst, "taal": taal, "label": "onwaar", "eerste_datum": datum,
            "redacties": ["Snopes"], "url": f"https://snopes.com/{nummer}", "vertaling": ""}


def test_the_cards_for_the_po_are_the_yes_and_the_doubt_that_nobody_read_yet():
    paginas = {EEN: _pagina(EEN, "Zelensky bought a villa"), TWEE: _pagina(TWEE, "زيلينسكي اشترى يختا", taal="ar"),
               DRIE: _pagina(DRIE, "The moon is made of cheese")}
    paginas[TWEE]["vertaling"] = "Zelensky bought a yacht"
    voorstellen = {EEN: {"oordeel": "ja", "reden": "villa"}, TWEE: {"oordeel": "twijfel", "reden": "yacht, no money"},
                   DRIE: {"oordeel": "nee", "reden": "moon"}, "00000000000000ff": {"oordeel": "ja", "reden": "weg"}}
    kaarten = ds.kaarten(voorstellen, paginas, gelezen=set())
    assert [k["id"] for k in kaarten] == [EEN, TWEE]                    # ja eerst, dan twijfel; nee en wat weg is niet
    assert kaarten[0] == {"id": EEN, "bewering": "Zelensky bought a villa", "taal": "en", "richting": "ltr",
                          "vertaling": "", "label": "onwaar", "datum": "2024-03-01", "redacties": ["Snopes"],
                          "url": f"https://snopes.com/{EEN}", "voorstel": "ja", "reden": "villa"}
    assert kaarten[1]["richting"] == "rtl" and kaarten[1]["vertaling"] == "Zelensky bought a yacht"
    assert [k["id"] for k in ds.kaarten(voorstellen, paginas, gelezen={EEN})] == [TWEE]


def test_only_what_the_po_approved_ends_up_in_the_dossier_and_her_whole_reading_is_kept():
    d = ds.keur("zelensky-luxury", _ruw(), _goed(DRIE))
    kaarten = [{"id": EEN, "voorstel": "ja"}, {"id": TWEE, "voorstel": "ja"}, {"id": "00000000000000a4", "voorstel": "twijfel"},
               {"id": "00000000000000a5", "voorstel": "ja"}]
    keuzes = {EEN: {"oordeel": "ja", "opmerking": ""}, TWEE: {"oordeel": "nee", "opmerking": "gaat over haar moeder"},
              "00000000000000a4": {"oordeel": "", "opmerking": "grijs gebied"},
              "00000000000000ee": {"oordeel": "ja"}}                     # een nummer dat niet op de kaarten stond
    goed, lezing = ds.goedkeuring(d, kaarten, keuzes, datum="2026-11-12", eerder={DRIE: "ja"})
    # wat al goedgekeurd was blijft, wat nu ja kreeg komt erbij; nee, twijfel, ongelezen en onbekend niet
    assert goed == {"goedgekeurd_door": "PO", "datum": "2026-11-12", "factchecks": [{"nummer": DRIE}, {"nummer": EEN}]}
    assert lezing["labels"] == {DRIE: "ja", EEN: "ja", TWEE: "nee", "00000000000000a4": "twijfel"}
    assert lezing["opmerkingen"] == {TWEE: "gaat over haar moeder", "00000000000000a4": "grijs gebied"}
    assert lezing["gelezen_door"] == "PO" and lezing["datum"] == "2026-11-12"
    # een latere nee haalt een eerdere ja weer weg: de laatste lezing geldt
    goed2, lezing2 = ds.goedkeuring(ds.keur("zelensky-luxury", _ruw(), goed), [{"id": EEN, "voorstel": "ja"}],
                                    {EEN: {"oordeel": "nee"}}, datum="2026-11-13", eerder=lezing["labels"])
    assert goed2["factchecks"] == [{"nummer": DRIE}] and lezing2["labels"][EEN] == "nee"
    with pytest.raises(ds.Weigering, match="netwerk"):
        ds.goedkeuring(ds.keur("doppelganger", _netwerk(), None), kaarten, keuzes, datum="2026-11-12")


def test_the_reading_page_carries_the_cards_and_no_claim_can_close_its_script():
    d = ds.keur("zelensky-luxury", _ruw(), None)
    kaart = {"id": EEN, "bewering": 'x</script><script>alert(1)</script>', "taal": "en", "richting": "ltr", "vertaling": "",
             "label": "onwaar", "datum": "2024-03-01", "redacties": ["Snopes"], "url": "https://snopes.com/a",
             "voorstel": "ja", "reden": "villa"}
    html = ds.po_pagina(d, [kaart])
    assert "</script><script>alert(1)" not in html and "<\\/script>" in html
    data = json.loads(html.split('<script type="application/json" id="data">')[1].split("</script>")[0].replace("<\\/", "</"))
    assert data["dossier"] == "zelensky-luxury" and data["naam"] == "Zelensky buys luxury (nl)"
    assert data["kaarten"] == [kaart] and "/*KAARTEN*/" not in html
    assert "<title>Dossier zelensky-luxury nakijken</title>" in html


def test_every_dossier_in_the_repo_passes_the_checks_against_the_real_list_of_themes():
    themas = json.loads((ds.WORTEL / "content" / "themas.json").read_text(encoding="utf-8"))["themas"]
    dossiers = ds.lees_alle(ds.MAP, themas)
    assert dossiers, "content/dossiers/ hoort minstens het eerste dossier te dragen"
    for d in dossiers:
        # een akkoord draagt de woorden van de PO; een concept gaat in geen uitgave (B73)
        assert d["status"] == "concept" or d["akkoord"], d["sleutel"]


def test_the_spending_limit_stops_a_round_before_it_starts():
    ds.binnen_grens(0.10, 0.30)
    with pytest.raises(ds.Weigering, match="grens"):
        ds.binnen_grens(0.10, 0.45)


def test_reading_a_dossier_changes_nothing_in_what_it_was_given():
    ruw, goed = _ruw(), _goed(EEN)
    voor = copy.deepcopy((ruw, goed))
    ds.keur("zelensky-luxury", ruw, goed)
    assert (ruw, goed) == voor


# --- versies: hetzelfde bericht in andere woorden of een andere taal (E9.S7 AC8) -------------------------------------

def test_an_approved_fact_check_in_a_story_may_carry_a_version_and_one_in_a_network_may_not():
    goed = {**_goed(), "factchecks": [{"nummer": EEN, "versie": "highgrove-house"}, {"nummer": TWEE, "versie": "highgrove-house"},
                                      {"nummer": DRIE}]}
    d = ds.keur("zelensky-luxury", _ruw(), goed)
    assert d["factchecks"] == [{"nummer": EEN, "versie": "highgrove-house"}, {"nummer": TWEE, "versie": "highgrove-house"},
                               {"nummer": DRIE}]
    for fout in ("Highgrove House", "a", "x" * 60, "", 7):
        with pytest.raises(ds.Weigering, match="versie"):
            ds.keur("zelensky-luxury", _ruw(), {**_goed(), "factchecks": [{"nummer": EEN, "versie": fout}]})
    bron = {"niveau": "toegeschreven", "bron": "EUvsDisinfo", "url": "https://euvsdisinfo.eu/report/x"}
    with pytest.raises(ds.Weigering, match="versie"):
        ds.keur("doppelganger", _netwerk(), {**_goed(), "factchecks": [{"nummer": EEN, **bron, "versie": "highgrove-house"}]})


def test_the_version_request_numbers_the_claims_and_asks_which_are_the_same_message():
    d = ds.keur("zelensky-luxury", _ruw(), None)
    v = ds.versieverzoek(d, [("Zelensky bought Highgrove House", "en"), ("ゼレンスキー大統領がチャールズ3世の邸宅を購入した", "ja")])
    assert v["model"] == "claude-haiku-5-5" and "same message" in v["system"] and "Zelensky buys luxury (en)" in v["system"]
    assert "do not judge whether" in v["system"].lower()
    tekst = v["messages"][0]["content"][0]["text"]
    assert tekst.splitlines() == ["1. (en) Zelensky bought Highgrove House", "2. (ja) ゼレンスキー大統領がチャールズ3世の邸宅を購入した"]
    assert set(v["output_config"]["format"]["schema"]["properties"]["antwoorden"]["items"]["properties"]) == {"nr", "versie"}
    with pytest.raises(ds.Weigering, match="netwerk"):
        ds.versieverzoek(ds.keur("doppelganger", _netwerk(), None), [("a", "en")])


def test_version_answers_become_keys_and_a_version_of_one_is_no_version():
    antwoord = json.dumps({"antwoorden": [
        {"nr": 1, "versie": "Highgrove House"}, {"nr": 2, "versie": "highgrove  house!"}, {"nr": 3, "versie": "Two yachts"},
        {"nr": 4, "versie": ""}, {"nr": 5, "versie": "Вилла"}, {"nr": 6, "versie": "Cartier (New York)"},
        {"nr": 6, "versie": "x"}, {"nr": 9, "versie": "buiten"}, "rommel"]})
    # dezelfde naam in een andere schrijfwijze is dezelfde sleutel; alleen staan, geen naam, een naam zonder Latijnse
    # letters of een nummer dat twee keer voorkomt geeft geen versie
    assert ds.lees_versies(antwoord, 7) == ["highgrove-house", "highgrove-house", "", "", "", "", ""]
    for rommel in (None, "", "geen json", json.dumps({"antwoorden": "x"})):
        assert ds.lees_versies(rommel, 2) == ["", ""]


def test_the_groups_for_the_po_hold_only_approved_fact_checks_with_at_least_two_members():
    d = ds.keur("zelensky-luxury", _ruw(), _goed(EEN, TWEE, DRIE))
    paginas = {EEN: _pagina(EEN, "Zelensky bought Highgrove House", datum="2024-04-10"),
               TWEE: _pagina(TWEE, "Зеленский купил резиденцию английского короля", taal="ru", datum="2024-04-12"),
               DRIE: _pagina(DRIE, "Zelensky bought two yachts", datum="2023-12-01"),
               "00000000000000a4": _pagina("00000000000000a4", "Zelensky bought two yachts for 75 million")}
    paginas[TWEE]["vertaling"] = "Zelensky kocht de residentie van de Engelse koning"
    voorstel = {EEN: "highgrove-house", TWEE: "highgrove-house", DRIE: "two-yachts", "00000000000000a4": "two-yachts"}
    groepen = ds.versiegroepen(d, voorstel, paginas)
    # de jachten vallen af: de tweede factcheck is niet goedgekeurd, dus er blijft er één over
    assert [g["sleutel"] for g in groepen] == ["highgrove-house"]
    assert [k["id"] for k in groepen[0]["kaarten"]] == [EEN, TWEE]
    assert groepen[0]["kaarten"][1] == {"id": TWEE, "bewering": "Зеленский купил резиденцию английского короля", "taal": "ru",
                                        "richting": "ltr", "vertaling": "Zelensky kocht de residentie van de Engelse koning",
                                        "label": "onwaar", "datum": "2024-04-12", "redacties": ["Snopes"],
                                        "url": f"https://snopes.com/{TWEE}"}


def test_a_fact_check_gets_its_version_only_if_the_po_approved_the_group_and_left_the_card_in():
    vier, vijf = "00000000000000a4", "00000000000000a5"
    d = ds.keur("zelensky-luxury", _ruw(), _goed(EEN, TWEE, DRIE, vier, vijf))
    groepen = [{"sleutel": "highgrove-house", "kaarten": [{"id": EEN}, {"id": TWEE}, {"id": DRIE}]},
               {"sleutel": "two-yachts", "kaarten": [{"id": vier}, {"id": vijf}]},
               {"sleutel": "bugatti", "kaarten": [{"id": "00000000000000a6"}, {"id": "00000000000000a7"}]}]
    keuzes = {"highgrove-house": {"oordeel": "ja", "zonder": [DRIE, "00000000000000ff"], "opmerking": "de derde is een ander huis"},
              "two-yachts": {"oordeel": "nee", "opmerking": ""}}
    goed, lezing = ds.versies_goedkeuren(d, groepen, keuzes, datum="2026-11-12")
    assert goed["factchecks"] == [{"nummer": EEN, "versie": "highgrove-house"}, {"nummer": TWEE, "versie": "highgrove-house"},
                                  {"nummer": DRIE}, {"nummer": vier}, {"nummer": vijf}]
    assert goed["goedgekeurd_door"] == "PO" and goed["datum"] == "2026-11-12"
    assert lezing == {"highgrove-house": {"oordeel": "ja", "leden": [EEN, TWEE], "zonder": [DRIE],
                                          "opmerking": "de derde is een ander huis"},
                      "two-yachts": {"oordeel": "nee", "leden": [], "zonder": [], "opmerking": ""}}
    # een versie waar na het weghalen één kaart overblijft, is geen versie; een eerdere versie die nu nee krijgt, vervalt
    d2 = ds.keur("zelensky-luxury", _ruw(), goed)
    goed2, lezing2 = ds.versies_goedkeuren(d2, groepen[:1], {"highgrove-house": {"oordeel": "ja", "zonder": [TWEE, DRIE]}},
                                           datum="2026-11-13")
    assert all("versie" not in f for f in goed2["factchecks"]) and lezing2["highgrove-house"]["leden"] == []
    # een versie die deze ronde niet gelezen is, blijft zoals ze was
    goed3, _ = ds.versies_goedkeuren(d2, groepen[1:], {"two-yachts": {"oordeel": "ja"}}, datum="2026-11-13")
    assert goed3["factchecks"][:2] == [{"nummer": EEN, "versie": "highgrove-house"}, {"nummer": TWEE, "versie": "highgrove-house"}]
    assert goed3["factchecks"][3:] == [{"nummer": vier, "versie": "two-yachts"}, {"nummer": vijf, "versie": "two-yachts"}]
    with pytest.raises(ds.Weigering, match="netwerk"):
        ds.versies_goedkeuren(ds.keur("doppelganger", _netwerk(), None), groepen, keuzes, datum="2026-11-12")


def test_the_version_page_carries_the_groups_and_no_claim_can_close_its_script():
    d = ds.keur("zelensky-luxury", _ruw(), None)
    groepen = [{"sleutel": "highgrove-house", "kaarten": [{"id": EEN, "bewering": "x</script><script>alert(1)</script>"}]}]
    html = ds.versiepagina(d, groepen)
    assert "</script><script>alert(1)" not in html and "<title>Dossier zelensky-luxury versies</title>" in html
    data = json.loads(html.split('<script type="application/json" id="data">')[1].split("</script>")[0].replace("<\\/", "</"))
    assert data["dossier"] == "zelensky-luxury" and data["groepen"] == groepen


def test_a_later_reading_keeps_the_versions_of_what_stays_and_drops_a_version_left_with_one():
    vier = "00000000000000a4"
    goed = {**_goed(), "factchecks": [{"nummer": EEN, "versie": "highgrove-house"}, {"nummer": TWEE, "versie": "highgrove-house"},
                                      {"nummer": DRIE, "versie": "two-yachts"}, {"nummer": vier, "versie": "two-yachts"}]}
    d = ds.keur("zelensky-luxury", _ruw(), goed)
    eerder = {EEN: "ja", TWEE: "ja", DRIE: "ja", vier: "ja"}
    # de PO haalt later één jacht weg: Highgrove houdt zijn versie, het jacht dat alleen overblijft niet meer
    nieuw, lezing = ds.goedkeuring(d, [{"id": vier, "voorstel": "ja"}], {vier: {"oordeel": "nee", "opmerking": "toch niet"}},
                                   datum="2026-11-12", eerder=eerder)
    assert nieuw["factchecks"] == [{"nummer": EEN, "versie": "highgrove-house"}, {"nummer": TWEE, "versie": "highgrove-house"},
                                   {"nummer": DRIE}]
    assert lezing["labels"] == {EEN: "ja", TWEE: "ja", DRIE: "ja", vier: "nee"}


def test_a_new_reading_is_merged_into_the_old_one_without_losing_what_was_read_before():
    oud = {"toelichting": "x", "gelezen_door": "PO", "datum": "2026-11-11", "labels": {EEN: "ja", TWEE: "ja"},
           "opmerkingen": {EEN: "eerste notitie", TWEE: "blijft"}, "versies": {"highgrove-house": {"oordeel": "ja"}}}
    nieuw = {"gelezen_door": "PO", "datum": "2026-11-12", "labels": {EEN: "nee", TWEE: "ja"}, "opmerkingen": {EEN: "toch niet"}}
    samen = ds.voeg_lezing_samen(oud, nieuw)
    assert samen == {"toelichting": "x", "gelezen_door": "PO", "datum": "2026-11-12", "labels": {EEN: "nee", TWEE: "ja"},
                     "opmerkingen": {EEN: "toch niet", TWEE: "blijft"}, "versies": {"highgrove-house": {"oordeel": "ja"}}}
    assert ds.voeg_lezing_samen({}, nieuw)["labels"] == {EEN: "nee", TWEE: "ja"}


# --- Claude leest, de PO beslist over de twijfel (SPECS E9.S7 AC3, PO 2026-11-12) ---------------------------------------

VIER, VIJF = "00000000000000a4", "00000000000000a5"
AKKOORD = '2026-11-12, PO: "Ja, jij leest eerst, ik daarna de twijfelgevallen"'


def _kaart(nummer, tekst="Zelensky bought a villa"):
    return {"id": nummer, "bewering": tekst, "taal": "en", "richting": "ltr", "vertaling": "", "label": "onwaar",
            "datum": "2024-03-01", "redacties": ["Snopes"], "url": f"https://snopes.com/{nummer}", "voorstel": "ja",
            "reden": "villa"}


def _claude(**anders):
    lezing = {"dossier": "zelensky-luxury", "gelezen_door": "Claude", "datum": "2026-11-12",
              "labels": {EEN: "ja", TWEE: "nee", DRIE: "twijfel", VIER: "twijfel", VIJF: "twijfel"},
              "notities": {TWEE: "gaat over haar moeder", DRIE: "een jacht, geen villa"},
              "groepen": [{"sleutel": "jachten", "vraag": "Horen jachten erbij?", "uitleg": "Twee over een jacht.",
                           "per_kaart": False, "kaarten": [DRIE, VIER]},
                          {"sleutel": "niet-open", "vraag": "De check kon ik niet openen.", "uitleg": "Kies per kaart.",
                           "per_kaart": True, "kaarten": [VIJF]}]}
    lezing.update(anders)
    return lezing


def test_the_doubt_for_the_po_is_every_doubt_of_claude_each_in_exactly_one_group_and_nothing_else():
    kaarten = [_kaart(n) for n in (EEN, TWEE, DRIE, VIER, VIJF)]
    groepen = ds.twijfelgroepen(kaarten, _claude())
    assert [g["sleutel"] for g in groepen] == ["jachten", "niet-open"]
    assert [[k["id"] for k in g["kaarten"]] for g in groepen] == [[DRIE, VIER], [VIJF]]
    assert groepen[0]["vraag"] == "Horen jachten erbij?" and groepen[1]["per_kaart"] is True
    assert groepen[0]["kaarten"][0]["notitie"] == "een jacht, geen villa"      # de reden van Claude staat bij de kaart
    fout = {"een twijfel zonder groep": [[DRIE], [VIJF]], "een kaart in twee groepen": [[DRIE, VIER], [VIER, VIJF]],
            "een kaart die geen twijfel is": [[EEN, DRIE, VIER], [VIJF]]}
    for wat, indeling in fout.items():
        lezing = _claude()
        for g, nrs in zip(lezing["groepen"], indeling):
            g["kaarten"] = nrs
        with pytest.raises(ds.Weigering):
            ds.twijfelgroepen(kaarten, lezing)
    with pytest.raises(ds.Weigering, match="kaart"):                           # een nummer dat niet op de kaarten staat
        ds.twijfelgroepen(kaarten[:4], _claude())
    dubbel = _claude()
    dubbel["groepen"][1]["sleutel"] = "jachten"
    with pytest.raises(ds.Weigering, match="jachten"):
        ds.twijfelgroepen(kaarten, dubbel)


def test_a_group_choice_counts_for_each_card_in_it_unless_the_card_has_its_own_and_never_for_a_card_by_card_group():
    groepen = ds.twijfelgroepen([_kaart(n) for n in (EEN, TWEE, DRIE, VIER, VIJF)], _claude())
    keuzes = ds.keuzes_uit_groepen(groepen, {"jachten": {"oordeel": "ja", "opmerking": "jachten horen erbij"},
                                             "niet-open": {"oordeel": "ja"}},
                                   {VIER: {"oordeel": "nee", "opmerking": ""}, EEN: {"oordeel": "nee"}})
    assert keuzes == {DRIE: {"oordeel": "ja", "opmerking": "jachten horen erbij"},
                      VIER: {"oordeel": "nee", "opmerking": "jachten horen erbij"}}  # VIJF: per kaart, zonder eigen keuze
    assert ds.keuzes_uit_groepen(groepen, {}, {VIJF: {"oordeel": "ja"}}) == {VIJF: {"oordeel": "ja", "opmerking": ""}}


def test_claude_reads_the_rest_the_po_decides_the_doubt_and_the_reading_says_who_did_what_with_her_words():
    d = ds.keur("zelensky-luxury", _ruw(), None)
    kaarten = [_kaart(n) for n in (EEN, TWEE, DRIE, VIER, VIJF)]
    claude = _claude()
    groepen = ds.twijfelgroepen(kaarten, claude)
    groepkeuzes = {"jachten": {"oordeel": "ja", "opmerking": ""}}
    goed, lezing = ds.goedkeuring_met_claude(d, kaarten, claude, groepkeuzes, {}, datum="2026-11-12", akkoord=AKKOORD)
    # de ja van Claude en de groep die de PO goedkeurde; de kaart per kaart zonder keuze blijft eruit
    assert [f["nummer"] for f in goed["factchecks"]] == [EEN, DRIE, VIER]
    assert goed["goedgekeurd_door"] == "Claude en PO"
    assert lezing["labels"] == {EEN: "ja", TWEE: "nee", DRIE: "ja", VIER: "ja", VIJF: "twijfel"}
    assert lezing["door_po"] == [DRIE, VIER] and lezing["akkoord"] == AKKOORD
    assert lezing["notities_claude"] == claude["notities"]
    assert lezing["groepen"] == [{"sleutel": "jachten", "vraag": "Horen jachten erbij?", "kaarten": [DRIE, VIER],
                                  "keuze": "ja"},
                                 {"sleutel": "niet-open", "vraag": "De check kon ik niet openen.", "kaarten": [VIJF],
                                  "keuze": None}]
    for fout in ("", "PO zei ja", '2026-11-12, Claude: "ja"'):                 # zonder haar woorden en de datum niet
        with pytest.raises(ds.Weigering, match="akkoord"):
            ds.goedkeuring_met_claude(d, kaarten, claude, groepkeuzes, {}, datum="2026-11-12", akkoord=fout)


def test_the_doubt_page_carries_every_dossier_with_its_groups_and_no_claim_can_close_its_script():
    d = ds.keur("zelensky-luxury", _ruw(), None)
    kaarten = [_kaart(n) for n in (EEN, TWEE, DRIE, VIER)] + [_kaart(VIJF, 'x</script><script>alert(1)</script>')]
    claude = _claude()
    html = ds.twijfelpagina([(d, claude, ds.twijfelgroepen(kaarten, claude))])
    assert "</script><script>alert(1)" not in html and "<\\/script>" in html and "/*DOSSIERS*/" not in html
    data = json.loads(html.split('<script type="application/json" id="data">')[1].split("</script>")[0].replace("<\\/", "</"))
    [deel] = data["dossiers"]
    assert deel["dossier"] == "zelensky-luxury" and deel["naam"] == "Zelensky buys luxury (nl)"
    assert deel["telling"] == {"ja": 1, "nee": 1, "twijfel": 3}
    assert [g["sleutel"] for g in deel["groepen"]] == ["jachten", "niet-open"]
    assert '"dossiers/" + deel.dossier + "/groepen"' in html and '"dossiers/" + deel.dossier + "/keuzes"' in html


def test_a_large_dossier_is_cut_into_parts_of_at_most_the_maximum_and_what_is_alike_stays_together():
    import numpy as np
    rng = np.random.default_rng(7)
    # drie verhalen van elk 50 beweringen, elk rond een eigen richting: wat bij elkaar hoort, moet in één stuk blijven
    midden = rng.normal(size=(3, 32)) * 5
    x = np.vstack([midden[i] + rng.normal(size=(50, 32)) * 0.1 for i in range(3)]).astype(np.float32)
    nummers = [f"{i:016x}" for i in range(150)]
    stukken = ds.delen(x, nummers, maximum=80)
    assert sorted(nr for s in stukken for nr in s) == sorted(nummers)          # niets dubbel, niets weg
    assert all(len(s) <= 80 for s in stukken)
    verhaal = {nr: i // 50 for i, nr in enumerate(nummers)}
    for v in range(3):                                                          # elk verhaal heel in één stuk
        assert sum(any(verhaal[nr] == v for nr in s) for s in stukken) == 1
    assert ds.delen(x, nummers, maximum=80) == stukken                         # vast: dezelfde stukken
    assert ds.delen(x[:40], nummers[:40], maximum=80) == [nummers[:40]]        # klein genoeg: één stuk, zoals het was


def test_a_fact_check_already_approved_in_another_story_never_comes_back_as_a_card_but_one_in_a_network_does():
    verhaal = ds.keur("zelensky-luxury", _ruw(), _goed(EEN, TWEE))
    netwerk = ds.keur("doppelganger", _netwerk(), {"goedgekeurd_door": "PO", "datum": "2026-11-12", "factchecks": [
        {"nummer": DRIE, "niveau": "toegeschreven", "bron": "EU DisinfoLab", "url": "https://www.disinfo.eu/doppelganger"}]})
    nieuw = ds.keur("herkomst-coronavirus", _ruw(), _goed(VIER))
    assert ds.elders([verhaal, netwerk, nieuw], "herkomst-coronavirus") == {EEN: "zelensky-luxury", TWEE: "zelensky-luxury"}
    assert ds.elders([verhaal, netwerk, nieuw], "zelensky-luxury") == {VIER: "herkomst-coronavirus"}


# --- inkorten: hoogstens ~50, de beweringen die het vaakst rondgingen (SPECS E9.S7 AC10) ------------------------------

def _bewering(nummer, groep, redacties, checks=1, talen=1, eigen=False, jaar="2025"):
    return {"nummer": nummer, "groep": groep, "redacties": redacties, "checks": checks, "talen": talen, "eigen": eigen,
            "jaar": jaar}


def test_a_dossier_keeps_one_fact_check_per_claim_and_the_claims_checked_by_the_most_newsrooms_first():
    kandidaten = [_bewering("a1", "x", 9, 20, 6), _bewering("a2", "x", 9, 20, 6),       # dezelfde bewering, twee keer
                  _bewering("b1", "y", 2, 2), _bewering("c1", "z", 5, 7, 3), _bewering("d1", "w", 5, 9, 2)]
    assert ds.inkorten(kandidaten, per_jaar=3) == ["a1", "d1", "c1"]


def test_the_own_checks_of_factiz_always_stay_whatever_the_limit():
    kandidaten = [_bewering("e1", "e", 0, eigen=True), _bewering("e2", "f", 0, eigen=True), _bewering("a1", "x", 9, 20),
                  _bewering("b1", "y", 4, 4)]
    assert ds.inkorten(kandidaten, per_jaar=1) == ["e1", "e2", "a1"]


def test_the_limit_holds_per_year_so_every_year_keeps_its_strongest_claims():
    kandidaten = [_bewering("a1", "x", 9, jaar="2023"), _bewering("b1", "y", 8, jaar="2023"),
                  _bewering("c1", "z", 2, jaar="2025"), _bewering("d1", "w", 1, jaar="")]
    assert ds.inkorten(kandidaten, per_jaar=1) == ["a1", "c1", "d1"]


def test_within_one_claim_the_fact_check_with_its_own_most_newsrooms_represents_it():
    kandidaten = [{**_bewering("a1", "x", 9, 20), "eigen_redacties": 1}, {**_bewering("a2", "x", 9, 20), "eigen_redacties": 3}]
    assert ds.inkorten(kandidaten, per_jaar=5) == ["a2"]


def test_among_claims_checked_once_the_one_whose_story_the_archive_checked_most_goes_first():
    """Boetsja in 2025, maar sinds 2022 telkens weer gecheckt (`ruim_*`), gaat voor een bewering die alleen staat."""
    kandidaten = [{**_bewering("a1", "x", 1), "ruim_redacties": 1, "ruim_checks": 1},
                  {**_bewering("b1", "y", 1), "ruim_redacties": 6, "ruim_checks": 40}]
    assert ds.inkorten(kandidaten, per_jaar=1) == ["b1"]


# --- begrippen in een dossier (SPECS E9.S7 AC9, PLAN #34.2ca) --------------------------------------------------------

def _archief(*extra, n=1000):
    """De documentfrequenties van een nagemaakt archief van n teksten: gewone woorden staan in veel teksten."""
    from collections import Counter
    df = Counter({"video": 300, "shows": 400, "ukraine": 200, "russian": 150, "attack": 120, "german": 30})
    df.update(dict(extra))
    return df, n


def test_a_word_that_is_common_in_the_dossier_and_rare_in_the_archive_becomes_a_term_in_its_usual_spelling():
    teksten = ["Germany sends the Taurus to Ukraine", "Taurus needs German soldiers", "The Taurus plant in Schrobenhausen",
               "A video shows a Russian attack", "Video shows a Russian attack on Kyiv"]
    df, n = _archief(("taurus", 4))
    assert pb.begrippen(teksten, df, n, uit=set()) == ["Taurus"]


def test_the_words_of_the_dossier_name_numbers_and_months_are_never_terms():
    teksten = ["Gaza 2024 October bombing", "Gaza October bombing footage", "Gaza in October: bombing", "Old bombing in Gaza"]
    df, n = _archief(("gaza", 2), ("october", 3), ("bombing", 5))
    assert pb.begrippen(teksten, df, n, uit={"gaza"}) == ["bombing"]


def test_a_word_in_fewer_than_three_fact_checks_of_the_dossier_is_not_a_term():
    df, n = _archief(("kursk", 1))
    assert pb.begrippen(["Troops in Kursk", "Kursk again", "Something else"], df, n, uit=set()) == []
    assert pb.begrippen(["Troops in Kursk", "Kursk again", "Kursk once more"], df, n, uit=set()) == ["Kursk"]


def test_two_words_that_belong_together_are_one_term():
    teksten = ["Gazprom shut Nord Stream", "Nord Stream was blown up", "Who blew up Nord Stream", "Nord Stream leaks"]
    df, n = _archief(("nord", 5), ("stream", 6), ("nord stream", 4), ("blew", 20), ("blown", 20))
    assert pb.begrippen(teksten, df, n, uit=set()) == ["Nord Stream"]


def test_terms_are_read_in_any_alphabet():
    teksten = ["Таурус для Украины", "Немцы и Таурус", "Таурус снова"]
    df, n = _archief(("таурус", 2))
    assert pb.begrippen(teksten, df, n, uit=set()) == ["Таурус"]


def test_a_word_from_the_fixed_phrasing_of_one_newsroom_is_not_a_term_but_its_subject_is():
    """De vaste zin van één redactie ("purported") telt niet; een onderwerp dat één redactie drie keer checkte wel."""
    teksten = ["Post purported Kursk", "Image purported of Kursk", "Purported Kursk again", "Kursk by another desk"]
    wie = [{"PesaCheck"}, {"PesaCheck"}, {"PesaCheck"}, {"DW"}]
    df, n = _archief(("kursk", 1), ("purported", 1))
    assert pb.begrippen(teksten, df, n, uit=set(), redacties=wie, stijl={"purported": {"PesaCheck"}}) == ["Kursk"]


def test_singular_and_plural_are_one_term():
    teksten = ["A strike here", "A strike there", "One strike", "Strikes again", "Strikes once more", "Strikes too"]
    df, n = _archief(("strike", 2), ("strikes", 2))
    assert len(pb.begrippen(teksten, df, n, uit=set())) == 1
