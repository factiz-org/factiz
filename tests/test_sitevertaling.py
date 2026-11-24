"""De site in tien talen erbij (PLAN #34.2be, B79): wat een vertaling van een vaste tekst laat vallen, de datumvorm uit
CLDR, en de nieuwe talen in een dossier zonder dat de tekst van de PO verandert."""

import tomllib

from doublecheck import sitevertaling as sv


def test_a_translation_is_refused_when_a_placeholder_changes_or_it_shouts():
    assert sv.fout("{n} newsrooms", "{n} redações") == ""
    assert sv.fout("{n} newsrooms", "{aantal} redações") == "plekhouders"
    assert sv.fout("{n} newsrooms", "redações") == "plekhouders"
    assert sv.fout("Search", "Pesquisar!") and sv.fout("Search", "検索！") and sv.fout("Back", "Voltar — já")
    assert sv.fout("Search", "  ") == "leeg" and sv.fout("Search", None) == "leeg"


def test_the_date_form_comes_from_the_cldr_example():
    assert sv.datumvorm("28 de outubro de 2026", "outubro") == "{dag} de {maand} de {jaar}"
    assert sv.datumvorm("2026年10月28日", "10月") == "{jaar}年{maand}{dag}日"
    assert sv.datumvorm("28 октября 2026\u202fг.", "октября") == "{dag} {maand} {jaar}\u202fг."
    assert sv.datumvorm("\u200f28 أكتوبر، 2026", "أكتوبر") == "{dag} {maand}، {jaar}"


TOML = '''soort = "verhaal"

[naam]
nl = "Naam"
en = "Name"
fr = "Nom"

[inleiding]
nl = """
Een alinea."""
fr = """
Un paragraphe
sur deux lignes."""

[nagelezen]
nl = false
fr = false

[[item]]
soort = "pers"
[item.titel]
nl = "Titel een"
fr = "Titre un"

[[item]]
soort = "pers"
[item.titel]
nl = "Titel twee"
fr = "Titre deux"
'''


def test_new_languages_go_after_french_and_the_rest_of_the_dossier_stays_the_same():
    vertalingen = {"naam": {"pt": 'Nome "x"', "ar": "اسم"}, "inleiding": {"pt": "Um parágrafo.", "ar": "فقرة."},
                   "item.0": {"pt": "Título um", "ar": "عنوان"}, "item.1": {"pt": "Título dois", "ar": "عنوان ٢"}}
    nieuw = sv.voeg_talen_toe(TOML, vertalingen, ["pt", "ar"])
    oud, gelezen = tomllib.loads(TOML), tomllib.loads(nieuw)
    assert gelezen["naam"] == {**oud["naam"], "pt": 'Nome "x"', "ar": "اسم"}
    assert gelezen["inleiding"]["fr"] == oud["inleiding"]["fr"] and gelezen["inleiding"]["pt"].strip() == "Um parágrafo."
    assert gelezen["nagelezen"] == {**oud["nagelezen"], "pt": False, "ar": False}
    assert [it["titel"]["pt"] for it in gelezen["item"]] == ["Título um", "Título dois"]
    assert [it["titel"]["fr"] for it in gelezen["item"]] == ["Titre un", "Titre deux"]


def test_filling_in_asks_only_for_the_missing_texts_and_keeps_the_rest_as_it_was(tmp_path, monkeypatch):
    import json

    en = {"_meta": {"taal": "en"}, "teksten": {"a": "One", "nieuw": "Also checked by {namen}", "b": "Two"}}
    pt = {"_meta": {"taal": "pt", "nagelezen": False}, "teksten": {"a": "Um", "b": "Dois"}}
    for taal, d in (("en", en), ("pt", pt)):
        (tmp_path / f"{taal}.json").write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    gevraagd = []

    def vertaal(client, taal, soort, bron, **_):
        gevraagd.append((taal, bron))
        return {k: "Também verificada por {namen}" for k in bron}

    monkeypatch.setattr(sv, "TEKSTEN", tmp_path)
    monkeypatch.setattr(sv, "vertaal", vertaal)
    sv.aanvullen(None, ["pt"])
    assert gevraagd == [("pt", {"nieuw": "Also checked by {namen}"})]
    uit = json.loads((tmp_path / "pt.json").read_text(encoding="utf-8"))
    assert list(uit["teksten"].items()) == [("a", "Um"), ("nieuw", "Também verificada por {namen}"), ("b", "Dois")]
    assert uit["_meta"] == pt["_meta"]
    sv.aanvullen(None, ["pt"])                                              # niets meer te doen
    assert len(gevraagd) == 1
