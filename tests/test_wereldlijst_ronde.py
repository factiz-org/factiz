"""De wereldlijst als vaste wekelijkse ronde (PLAN #37.12, B90; PO 2026-11-23: "Ja, de wereldlijst"): elke week dezelfde
opdracht voor vier onderzoekers, met wat Factiz al heeft; een keuzepagina voor de PO; en haar keuzes in één stap naar het
weekbestand dat de uitgave leest."""

import json

import pytest

from doublecheck import wereldlijst as wl


def _voorstel(sleutel, regio="europa", **anders):
    return {"sleutel": sleutel, "regio": regio, "landen": ["UA"], "talen": ["en"], "soort": "image",
            "bewering": "Pictures show the Crimea bridge broken apart.",
            "rondgang": "From 18 November the pictures spread on X. [1]",
            "kern": ["The pictures do not show the damage. [1]"],
            "checks": [{"nr": 1, "redactie": "AFP Fact Check", "land": "FR", "taal": "en", "oordeel": "False",
                        "oordeel_en": "False", "datum": "2026-11-27", "titel": "AI image", "url": "https://factcheck.afp.com/x"}],
            "post": None, "waarom": "A war claim in several languages.", **anders}


def test_the_week_runs_from_a_week_ago_to_the_day_itself():
    assert wl.venster("2026-11-30") == ("2026-11-23", "2026-11-30")


def test_the_brief_is_the_first_round_with_the_week_region_and_what_factiz_already_has(tmp_path):
    tekst = wl.opdracht("europa", "2026-11-30", ["crimea bridge ai visuals", "greta thunberg laughs"], tmp_path / "europa.json")
    assert "between 2026-11-23 and 2026-11-30" in tekst and "Today is 2026-11-30" in tekst
    assert "Russia–Ukraine war" in tekst and "dpa-Faktencheck" in tekst
    assert "Skip these topics, which Factiz already covers: crimea bridge ai visuals, greta thunberg laughs." in tekst
    assert str(tmp_path / "europa.json") in tekst and '"regio": "europa"' in tekst
    assert "Do not use the Google Fact Check Tools API" in tekst and "$" not in tekst
    azie = wl.opdracht("azie", "2026-11-30", [], tmp_path / "azie.json")
    assert '"regio": "zuid-azie" or "oost-azie"' in azie and "BOOM" in azie and "nothing yet" in azie
    assert sum(d["aantal"] for d in wl.DELEN.values()) == 20


def test_what_factiz_already_has_comes_from_its_own_checks_and_every_earlier_world_list(tmp_path):
    redactie, wereld = tmp_path / "redactie", tmp_path / "wereld"
    (redactie / "greta").mkdir(parents=True)
    (redactie / "greta" / "check.toml").write_text('sleutel = "greta"\nadres_en = "greta-thunberg-laughs-climate-protest"\n',
                                                   encoding="utf-8")
    wereld.mkdir()
    (wereld / "2026-11-23.json").write_text(json.dumps({"week": "2026-11-23", "overzichten": [_voorstel("crimea-bridge-ai-visuals")]}),
                                             encoding="utf-8")
    assert wl.al_gedaan(redactie, wereld) == ["crimea bridge ai visuals", "greta thunberg laughs climate protest"]


def test_a_round_writes_four_briefs_in_the_folder_of_its_week(tmp_path, monkeypatch):
    monkeypatch.setattr(wl, "al_gedaan", lambda *a: ["iets"])
    paden = wl.ronde("2026-11-30", tmp_path)
    assert sorted(p.name for p in paden) == ["opdracht-amerikas.md", "opdracht-azie.md", "opdracht-europa.md",
                                             "opdracht-midden-oosten-afrika.md"]
    assert all(p.parent == tmp_path / "2026-11-30" for p in paden)
    assert str(tmp_path / "2026-11-30" / "amerikas.json") in (tmp_path / "2026-11-30" / "opdracht-amerikas.md").read_text(encoding="utf-8")


def test_the_page_shows_every_proposal_of_the_week_in_region_order(tmp_path):
    week = tmp_path / "2026-11-30"
    week.mkdir()
    (week / "azie.json").write_text(json.dumps([_voorstel("china-x", "oost-azie")]), encoding="utf-8")
    (week / "europa.json").write_text(json.dumps([_voorstel("crimea-x")]), encoding="utf-8")
    pad = wl.pagina("2026-11-30", tmp_path)
    html = pad.read_text(encoding="utf-8")
    assert pad == week / "overzichten.html"
    assert "crimea-x" in html and "china-x" in html and html.index("crimea-x") < html.index("china-x")
    assert "<title>Wereldlijst week 48</title>" in html and "23 en 30 november 2026" in html
    assert "__" not in html.replace("__proto__", "")


def test_the_choices_of_the_po_become_the_week_file_that_the_edition_reads(tmp_path):
    week = tmp_path / "overzicht" / "2026-11-30"
    week.mkdir(parents=True)
    (week / "europa.json").write_text(json.dumps([_voorstel("goed-een"), _voorstel("twijfel-een"), _voorstel("weg-een")]),
                                      encoding="utf-8")
    uit = tmp_path / "wereldlijst"
    keuzes = {"goed-een": "goed", "twijfel-een": "twijfel", "weg-een": "weg"}
    akkoord = '2026-12-01, PO: "Gekozen"'
    pad = wl.akkoord("2026-11-30", keuzes, akkoord, tmp_path / "overzicht", uit, register={})
    blad = json.loads(pad.read_text(encoding="utf-8"))
    assert pad == uit / "2026-11-30.json" and blad["week"] == "2026-11-30" and blad["akkoord"] == akkoord
    assert {o["sleutel"]: o["status"] for o in blad["overzichten"]} == {"goed-een": "gepubliceerd", "twijfel-een": "concept"}
    assert all(o["taal"] == "en" for o in blad["overzichten"])
    # niet nog eens over een week heen, niet zonder akkoord in de vaste vorm, niet zonder keuze voor elk voorstel
    with pytest.raises(wl.Weigering, match="bestaat al"):
        wl.akkoord("2026-11-30", keuzes, akkoord, tmp_path / "overzicht", uit, register={})
    with pytest.raises(wl.Weigering, match="akkoord"):
        wl.akkoord("2026-11-30", keuzes, "ja", tmp_path / "overzicht", tmp_path / "ander", register={})
    with pytest.raises(wl.Weigering, match="geen keuze"):
        wl.akkoord("2026-11-30", {"goed-een": "goed"}, akkoord, tmp_path / "overzicht", tmp_path / "ander2", register={})


def test_a_choice_that_breaks_the_rules_stops_the_week_file(tmp_path):
    week = tmp_path / "overzicht" / "2026-11-30"
    week.mkdir(parents=True)
    fout = _voorstel("zonder-bron", kern=["A sentence without its source."])
    (week / "europa.json").write_text(json.dumps([fout]), encoding="utf-8")
    with pytest.raises(wl.Weigering, match="zin zonder bron"):
        wl.akkoord("2026-11-30", {"zonder-bron": "goed"}, '2026-12-01, PO: "Gekozen"', tmp_path / "overzicht",
                   tmp_path / "wereldlijst", register={})
    assert not (tmp_path / "wereldlijst").exists()


def test_a_verdict_word_gets_the_scale_of_the_archive_when_the_table_knows_it_and_never_by_guessing(tmp_path):
    week = tmp_path / "2026-11-30"
    week.mkdir()
    bekend = _voorstel("bekend")
    vreemd = _voorstel("vreemd")
    vreemd["checks"][0].update(oordeel="przerobione zdjęcie", oordeel_en="Doctored photo", url="https://demagog.org.pl/x")
    (week / "europa.json").write_text(json.dumps([bekend, vreemd]), encoding="utf-8")
    assert wl.vul_schalen("2026-11-30", tmp_path) == ["vreemd [1]: przerobione zdjęcie / Doctored photo"]
    terug = {o["sleutel"]: o["checks"][0].get("schaal") for o in json.loads((week / "europa.json").read_text(encoding="utf-8"))}
    assert terug == {"bekend": "onwaar", "vreemd": None}
    # zonder schaal gaat het niet mee; met de hand gezet wel
    with pytest.raises(wl.Weigering, match="schaal"):
        wl.akkoord("2026-11-30", {"bekend": "goed", "vreemd": "goed"}, '2026-12-01, PO: "Gekozen"', tmp_path,
                   tmp_path / "uit", register={})
    items = json.loads((week / "europa.json").read_text(encoding="utf-8"))
    items[1]["checks"][0]["schaal"] = "misleidend"
    (week / "europa.json").write_text(json.dumps(items), encoding="utf-8")
    pad = wl.akkoord("2026-11-30", {"bekend": "goed", "vreemd": "goed"}, '2026-12-01, PO: "Gekozen"', tmp_path,
                     tmp_path / "uit", register={})
    assert [k["schaal"] for o in json.loads(pad.read_text(encoding="utf-8"))["overzichten"] for k in o["checks"]] == \
        ["onwaar", "misleidend"]


def test_checking_the_proposals_finds_what_breaks_the_rules_before_the_page_goes_to_the_po(tmp_path):
    week = tmp_path / "2026-11-30"
    week.mkdir()
    oud = _voorstel("te-oud")
    oud["checks"][0]["datum"] = "2026-11-10"
    (week / "europa.json").write_text(json.dumps([_voorstel("goed"), oud, _voorstel("goed"),
                                                  _voorstel("zonder-bron", kern=["No source."])]), encoding="utf-8")
    fouten = wl.nakijken("2026-11-30", tmp_path, register={})
    assert "te-oud: check [1] van 2026-11-10, buiten 2026-11-23 tot 2026-11-30" in fouten
    assert "goed: twee voorstellen met deze sleutel" in fouten
    assert any(f.startswith("zonder-bron: zin zonder bron") for f in fouten)
    assert not [f for f in fouten if f.startswith("goed:") and "twee" not in f]
