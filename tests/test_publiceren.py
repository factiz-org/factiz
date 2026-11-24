"""De publicatiedatabase (PLAN #33.1, SPECS E9.S1): één bestand per release met alleen wat gepubliceerd mag worden."""

import json
import sqlite3

import pytest

from doublecheck import publiceren as pb
from doublecheck import storage

REGISTER = {"snopes.com": "Snopes", "maldita.es": "Maldita", "afp.com": "AFP", "factcheck.afp.com": "AFP",
            "euvsdisinfo.eu": "EUvsDisinfo"}
CCBY, EIGEN, EU = "datacommons-ccby", "route-a", "euvsdisinfo:mendeley-yhdtkszvgp-v3"


def _lab(tmp_path, naam="lab.db"):
    conn = storage.connect(tmp_path / naam)
    storage.init_schema(conn)
    conn.executemany(
        "INSERT INTO bron (bron_id, naam, soort, licentie, attributietekst, url, herverdeelbaar) VALUES (?,?,?,?,?,?,?)",
        [("euvsdisinfo", "EUvsDisinfo (EEAS East StratCom Task Force)", "overheid", "EEAS reuse; CC BY 4.0",
          "EUvsDisinfo, European External Action Service", "https://euvsdisinfo.eu/disinformation-cases/", 1),
         ("communitynotes", "Community Notes (X)", "platform", "X Developer Agreement; niet herverdeelbaar",
          "Community Notes", "https://communitynotes.x.com", 0),
         ("route-a", "Route A", "factchecker", "geen open licentie", "Factcheck van de redactie", "https://x.invalid", 0)])
    return conn


def _claim(conn, nummer, tekst, taal="en", cluster=None):
    claim_id = f"gfc-{nummer:016x}"
    conn.execute("INSERT INTO claim (claim_id, canonical_text, language, cluster_id) VALUES (?,?,?,?)",
                 (claim_id, tekst, taal, cluster))
    return claim_id


def _check(conn, claim_id, url, bron=CCBY, oordeel="onwaar", eigen="False", datum="2024-03-01", taal="en",
           uitgever="ruwe naam uit de feed"):
    conn.execute("INSERT INTO factcheck (claim_id, publisher, verdict_normalized, verdict_original, url, review_date, "
                 "language, source) VALUES (?,?,?,?,?,?,?,?)", (claim_id, uitgever, oordeel, eigen, url, datum, taal, bron))


def _bouw(conn, tmp_path, vaag=frozenset(), naam="uit", **extra):
    conn.commit()
    return pb.bouw(conn, tmp_path / naam, register=REGISTER, vaag=vaag, datum="2026-11-10", **extra)


def _vijf(nl, en):
    return {"nl": nl, "en": en, "de": en, "es": en, "fr": en}


THEMAS = [{"sleutel": "health", "naam": _vijf("Gezondheid", "Health"), "omschrijving": "x",
           "onderdelen": [{"sleutel": "vaccines", "naam": _vijf("Vaccins", "Vaccines")}]},
          {"sleutel": "war", "naam": _vijf("Oorlog en conflict", "War and conflict"), "omschrijving": "x",
           "onderdelen": [{"sleutel": "ukraine", "naam": _vijf("Rusland en Oekraïne", "Russia and Ukraine")}]}]
LANDEN = {"IN": _vijf("India", "India"), "UA": _vijf("Oekraïne", "Ukraine")}


def _pub(manifest):
    conn = sqlite3.connect(f"file:{manifest['bestand']}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def test_a_check_we_fetched_ourselves_stays_out_and_a_claim_with_only_such_checks_gets_no_page(tmp_path):
    lab = _lab(tmp_path)
    vrij = _claim(lab, 1, "The moon is made of cheese")
    gemengd = _claim(lab, 2, "Zelensky bought a villa")
    alleen_eigen = _claim(lab, 3, "Nespresso regala cafeteras")
    _check(lab, vrij, "https://snopes.com/a")
    _check(lab, gemengd, "https://snopes.com/b")
    _check(lab, gemengd, "https://maldita.es/b", bron=EIGEN)
    _check(lab, alleen_eigen, "https://maldita.es/c", bron=EIGEN, taal="es")
    pub = _pub(_bouw(lab, tmp_path))
    assert {r["nummer"] for r in pub.execute("SELECT nummer FROM pagina")} == {pb.nummer(vrij), pb.nummer(gemengd)}
    assert [r["url"] for r in pub.execute("SELECT url FROM check_ WHERE pagina = ?", (pb.nummer(gemengd),))] == [
        "https://snopes.com/b"]
    # de tekst van een bewering die alleen uit een eigen ophaalronde komt, staat nergens in het bestand
    assert "Nespresso" not in " ".join(str(v) for t in ("pagina", "formulering", "zoek")
                                       for r in pub.execute(f"SELECT * FROM {t}") for v in tuple(r))
    assert {r["bron"] for r in pub.execute("SELECT bron FROM bron")} == {"datacommons-ccby"}


def test_where_it_turned_up_comes_only_from_a_source_that_may_be_republished_with_its_level(tmp_path):
    lab = _lab(tmp_path)
    c = _claim(lab, 1, "Ukraine hosts secret biolabs")
    _check(lab, c, "https://euvsdisinfo.eu/report/x", bron=EU, eigen="Disinformation")
    lab.executemany("INSERT INTO actor (actor_id, naam, soort) VALUES (?,?,?)",
                    [("outlet:1", "tsargrad.tv", "outlet"), ("platform:x", "X", "platform")])
    lab.executemany("INSERT INTO attributie (claim_id, actor_id, bron_id, datum, url, niveau, grond) VALUES (?,?,?,?,?,?,?)",
                    [(c, "outlet:1", "euvsdisinfo", "2022-11-22", "https://euvsdisinfo.eu/report/x", "waargenomen", "g"),
                     (c, "platform:x", "communitynotes", "2024-01-01", "https://x.com/i/notes/1", "waargenomen", "g")])
    pub = _pub(_bouw(lab, tmp_path))
    rijen = [dict(r) for r in pub.execute("SELECT naam, soort, niveau, bron, datum, url FROM opgedoken")]
    assert rijen == [{"naam": "tsargrad.tv", "soort": "outlet", "niveau": "waargenomen", "bron": "euvsdisinfo",
                      "datum": "2022-11-22", "url": "https://euvsdisinfo.eu/report/x"}]
    bron = dict(pub.execute("SELECT * FROM bron WHERE bron = 'euvsdisinfo'").fetchone())
    assert bron["naamsvermelding"] == "EUvsDisinfo, European External Action Service" and "CC BY" in bron["licentie"]


def test_a_publisher_outside_the_register_and_a_vague_claim_stay_out(tmp_path):
    lab = _lab(tmp_path)
    goed = _claim(lab, 1, "Vaccines contain microchips")
    rommel = _claim(lab, 2, "Win a free phone")
    vaag = _claim(lab, 3, "Video")
    _check(lab, goed, "https://snopes.com/a")
    _check(lab, rommel, "https://casino.example/a")
    _check(lab, vaag, "https://snopes.com/v")
    pub = _pub(_bouw(lab, tmp_path, vaag=frozenset({vaag})))
    assert [r["nummer"] for r in pub.execute("SELECT nummer FROM pagina")] == [pb.nummer(goed)]


def test_a_cluster_is_one_page_with_every_check_the_newsroom_named_as_in_the_register_and_the_newest_first(tmp_path):
    lab = _lab(tmp_path)
    a = _claim(lab, 1, "The US runs biolabs in Ukraine", cluster="cl-1")
    b = _claim(lab, 2, "EEUU tiene biolaboratorios en Ucrania", taal="es", cluster="cl-1")
    _check(lab, a, "https://snopes.com/a", datum="2022-03-01")
    _check(lab, a, "https://factcheck.afp.com/a", datum="2022-03-05", eigen="Faux", taal="fr")
    _check(lab, b, "https://afp.com/b", datum="2023-01-02", eigen="Falso", taal="es")
    pub = _pub(_bouw(lab, tmp_path))
    pagina = dict(pub.execute("SELECT * FROM pagina").fetchone())
    assert pagina["nummer"] == pb.nummer(a) and pagina["bewering"] == "The US runs biolabs in Ukraine"
    assert (pagina["checks"], pagina["redacties"]) == (3, 2)          # AFP telt één keer, op twee adressen
    assert json.loads(pagina["talen"]) == ["en", "es", "fr"]
    assert (pagina["eerste_datum"], pagina["laatste_datum"]) == ("2022-03-01", "2023-01-02")
    checks = [(r["redactie"], r["datum"], r["oordeel_eigen"]) for r in pub.execute("SELECT * FROM check_ ORDER BY volg")]
    assert checks == [("AFP", "2023-01-02", "Falso"), ("AFP", "2022-03-05", "Faux"), ("Snopes", "2022-03-01", "False")]
    # de andere formulering staat erbij, en haar nummer verwijst naar de pagina
    assert [(r["tekst"], r["taal"]) for r in pub.execute("SELECT tekst, taal FROM formulering")] == [
        ("EEUU tiene biolaboratorios en Ucrania", "es")]
    assert dict(pub.execute("SELECT nummer, pagina FROM verwijzing").fetchone()) == {
        "nummer": pb.nummer(b), "pagina": pb.nummer(a)}


def test_every_check_carries_its_source_with_licence_and_credit(tmp_path):
    lab = _lab(tmp_path)
    _check(lab, _claim(lab, 1, "A"), "https://snopes.com/a")
    _check(lab, _claim(lab, 2, "B"), "https://euvsdisinfo.eu/report/b", bron=EU)
    pub = _pub(_bouw(lab, tmp_path))
    rijen = {r["url"]: dict(r) for r in pub.execute(
        "SELECT c.url, b.bron, b.licentie, b.naamsvermelding FROM check_ c JOIN bron b ON b.bron = c.bron")}
    assert rijen["https://snopes.com/a"]["bron"] == "datacommons-ccby" and "CC BY 4.0" in rijen["https://snopes.com/a"]["licentie"]
    assert rijen["https://euvsdisinfo.eu/report/b"]["naamsvermelding"].startswith("EUvsDisinfo")
    assert all(r["naamsvermelding"] and r["licentie"] for r in rijen.values())


def test_a_dead_link_carries_its_archive_copy_and_a_single_dead_sighting_is_not_dead(tmp_path):
    lab = _lab(tmp_path)
    c = _claim(lab, 1, "A")
    _check(lab, c, "https://snopes.com/dood")
    _check(lab, c, "https://maldita.es/een-keer", datum="2024-01-01")
    _check(lab, c, "https://afp.com/leeft", datum="2023-01-01")
    lab.executemany(
        "INSERT INTO linkstatus (url, uitkomst, gecontroleerd_op, laatst_levend, dood_sinds, laatst_dood, archief_url, "
        "archief_datum) VALUES (?,?,?,?,?,?,?,?)",
        [("https://snopes.com/dood", "dood", "2026-11-02T10:00:00", "2026-01-01T10:00:00", "2026-11-01T09:00:00",
          "2026-11-02T10:00:00", "https://web.archive.org/web/2025/https://snopes.com/dood", "2025-05-05"),
         ("https://maldita.es/een-keer", "dood", "2026-11-02T10:00:00", None, "2026-11-02T10:00:00",
          "2026-11-02T10:00:00", None, None),
         ("https://afp.com/leeft", "levend", "2026-11-02T10:00:00", "2026-11-02T10:00:00", None, None, None, None)])
    pub = _pub(_bouw(lab, tmp_path))
    link = {r["url"]: (r["link"], r["archief_url"], r["archief_datum"]) for r in pub.execute("SELECT * FROM check_")}
    assert link["https://snopes.com/dood"] == ("offline", "https://web.archive.org/web/2025/https://snopes.com/dood",
                                               "2025-05-05")
    assert link["https://maldita.es/een-keer"][0] == "unclear" and link["https://afp.com/leeft"][0] == "live"


@pytest.mark.parametrize("taal,richting", [("ar", "rtl"), ("fa", "rtl"), ("he", "rtl"), ("ur", "rtl"), ("en", "ltr"),
                                           ("hi", "ltr"), ("und", "ltr"), ("", "ltr")])
def test_a_language_written_right_to_left_gets_that_direction(taal, richting):
    assert pb.richting(taal) == richting


def test_the_newest_verdict_leads_and_an_earlier_position_is_kept(tmp_path):
    lab = _lab(tmp_path)
    c = _claim(lab, 1, "The virus escaped from a lab in Wuhan")
    _check(lab, c, "https://snopes.com/2020", oordeel="onwaar", datum="2020-04-01")
    _check(lab, c, "https://afp.com/2025", oordeel="onbewezen", eigen="Unproven", datum="2025-02-01")
    pub = _pub(_bouw(lab, tmp_path))
    pagina = pub.execute("SELECT label, eerder FROM pagina").fetchone()
    assert pagina["label"] == "onbewezen" and json.loads(pagina["eerder"]) == [["onwaar", "2020"]]


def test_a_date_that_cannot_be_trusted_is_left_empty_and_never_repaired(tmp_path):
    lab = _lab(tmp_path)
    _check(lab, _claim(lab, 1, "A"), "https://snopes.com/a", datum="2099-01-01")
    pub = _pub(_bouw(lab, tmp_path))
    assert pub.execute("SELECT datum FROM check_").fetchone()["datum"] == ""
    assert tuple(pub.execute("SELECT eerste_datum, laatste_datum FROM pagina").fetchone()) == ("", "")


def test_the_page_number_is_the_claims_own_and_stable_and_never_a_path_into_something_else():
    assert pb.nummer("gfc-fbc5c6fcc7cd7031") == "fbc5c6fcc7cd7031"
    vreemd = pb.nummer("../../etc/passwd")
    assert vreemd == pb.nummer("../../etc/passwd") and len(vreemd) == 16 and vreemd.isalnum()


def test_the_file_holds_no_fingerprints_disputes_article_text_or_anything_a_user_sent(tmp_path):
    lab = _lab(tmp_path)
    c = _claim(lab, 1, "A")
    _check(lab, c, "https://snopes.com/a")
    lab.execute("INSERT INTO fingerprint (claim_id, kind, model_version, payload) VALUES (?, 'text', 'm', x'00')", (c,))
    pub = _pub(_bouw(lab, tmp_path))
    tabellen = {r[0] for r in pub.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
                if not r[0].startswith(("zoek_", "zoek3_", "sqlite_"))}
    assert tabellen == {"meta", "bron", "pagina", "formulering", "check_", "verwijzing", "opgedoken", "vertaling",
                        "thema", "land", "dossier", "dossier_item", "dossier_verwant", "naam", "pagina_naam",
                        "oordeel_glos", "lijkt_op",     # #34.2o en #34.2p: vertaalde woorden en paginanummers, geen vectoren
                        "zelfde",     # #34.2bp: paginanummers met dezelfde bewering bij een andere redactie
                        "waarom",     # #34.2j, B77: korte punten uit de weerlegging van EUvsDisinfo (CC BY), met hun link
                        "naam_vorm",  # #34.2z: de andere schrijfwijzen van een naam volgens Wikidata (CC0), om te zoeken
                        "bewering_normaal",   # #34.2ae: een bewering in hoofdletters in normaal schrift, uit haar eigen tekst
                        "kenmerk",            # #34.2ak: de soort volgens de redactie en de vorm, uit haar eigen woorden
                        "zoekvraag",          # #34.2cf, B87: de vraag zoals een zoeker haar typt, uit de bewering zelf
                        "afscherming",        # #34.2bw: pagina's buiten zoekmachines, met een reden, nooit de naam zelf
                        "eigen_check",        # #37.4, B82: de eigen factchecks, door een mens geschreven, nooit iets van een gebruiker
                        "dossier_begrip",     # #34.2ca: de begrippen van een dossier, gerekend uit de beweringen zelf
                        "samenvatting",       # #37.12, B91: zinnen van Factiz bij de wereldlijst, met links, nooit artikeltekst
                        "woord",              # #37.16: de woorden van het zoekregister met hun telling, uit de uitgave zelf
                        "zoek", "zoek3"}
    kolommen = {k[1] for t in tabellen for k in pub.execute(f"PRAGMA table_info({t})")}
    assert not kolommen & {"payload", "artifact", "artefact", "fingerprint", "vector", "deletion_key", "dispute_text"}
    assert dict(pub.execute("SELECT sleutel, waarde FROM meta"))["schema"] == str(pb.SCHEMA_VERSIE)


def test_building_twice_gives_the_same_file_and_the_manifest_counts_per_source_and_language(tmp_path):
    lab = _lab(tmp_path)
    _check(lab, _claim(lab, 1, "A"), "https://snopes.com/a")
    _check(lab, _claim(lab, 2, "ب", taal="ar"), "https://euvsdisinfo.eu/report/b", bron=EU, taal="ar")
    een, twee = _bouw(lab, tmp_path, naam="een"), _bouw(lab, tmp_path, naam="twee")
    assert een["controlegetal"] == twee["controlegetal"] and len(een["controlegetal"]) == 64
    assert (een["paginas"], een["checks"]) == (2, 2)
    assert een["per_bron"] == {"datacommons-ccby": 1, "euvsdisinfo": 1} and een["per_taal"] == {"ar": 1, "en": 1}
    assert een["schema"] == pb.SCHEMA_VERSIE and een["release"] == "2026-11-10"
    op_schijf = json.loads((tmp_path / "een" / "manifest.json").read_text(encoding="utf-8"))
    assert op_schijf["controlegetal"] == een["controlegetal"]
    pb.controleer(een["bestand"])       # een schoon bestand komt erdoor


def test_the_check_refuses_a_file_with_a_source_that_may_not_be_published_or_another_schema(tmp_path):
    lab = _lab(tmp_path)
    _check(lab, _claim(lab, 1, "A"), "https://snopes.com/a")
    bestand = _bouw(lab, tmp_path)["bestand"]
    conn = sqlite3.connect(bestand)
    conn.execute("INSERT INTO bron (bron, naam, licentie, naamsvermelding, url) VALUES ('route-a', 'x', 'x', 'x', 'x')")
    conn.commit()
    with pytest.raises(pb.Weigering, match="route-a"):
        pb.controleer(bestand)
    conn.execute("DELETE FROM bron WHERE bron = 'route-a'")
    conn.execute("UPDATE pagina SET bewering = 'geknoeid'")
    conn.commit()
    with pytest.raises(pb.Weigering, match="controlegetal"):
        pb.controleer(bestand)
    conn.execute("UPDATE meta SET waarde = '99' WHERE sleutel = 'schema'")
    conn.commit()
    conn.close()
    with pytest.raises(pb.Weigering, match="schema"):
        pb.controleer(bestand)


def test_both_search_registers_are_filled_for_words_and_for_scripts_without_spaces(tmp_path):
    lab = _lab(tmp_path)
    en = _claim(lab, 1, "Zelensky bought a villa in Florida")
    ar = _claim(lab, 2, "زيلينسكي اشترى فيلا في فلوريدا", taal="ar")
    zh = _claim(lab, 3, "泽连斯基在佛罗里达州购买了别墅", taal="zh")
    es = _claim(lab, 4, "Zelenski compró una mansión", taal="es", cluster="cl-9")
    es2 = _claim(lab, 5, "Zelenski adquirió un palacete", taal="es", cluster="cl-9")
    for c in (en, ar, zh, es):
        _check(lab, c, f"https://snopes.com/{c}")
    _check(lab, es, "https://afp.com/extra")
    _check(lab, es2, "https://maldita.es/x", bron=CCBY)
    pub = _pub(_bouw(lab, tmp_path))

    def woorden(vraag):
        return [r[0] for r in pub.execute("SELECT nummer FROM zoek WHERE zoek MATCH ?", (vraag,))]

    def drietallen(vraag):
        return [r[0] for r in pub.execute("SELECT nummer FROM zoek3 WHERE zoek3 MATCH ?", (vraag,))]

    assert woorden('"villa"') == [pb.nummer(en)]
    assert woorden('"mansion"') == [pb.nummer(es)]             # zonder accent gezocht, met accent gevonden
    assert woorden('"فيلا"') == [pb.nummer(ar)]
    assert woorden('"palacete"') == [pb.nummer(es)]            # een andere formulering vindt dezelfde pagina
    assert drietallen('"佛罗里达"') == [pb.nummer(zh)]           # geen spaties tussen woorden: het register op drietallen
    assert pub.execute("SELECT COUNT(*) FROM zoek").fetchone()[0] == pub.execute("SELECT COUNT(*) FROM pagina").fetchone()[0]


# --- thema en land (PLAN #33.4) -------------------------------------------------------------------------------------

def test_without_a_sorting_a_page_has_no_theme_and_the_file_says_nothing_about_themes(tmp_path):
    lab = _lab(tmp_path)
    _check(lab, _claim(lab, 1, "Vaccines contain microchips"), "https://snopes.com/a")
    m = _bouw(lab, tmp_path)
    pub = _pub(m)
    assert tuple(pub.execute("SELECT thema, onderdeel, tweede, land FROM pagina").fetchone()) == (None, "", "", "")
    assert pub.execute("SELECT COUNT(*) FROM thema").fetchone()[0] == 0 and m["met_thema"] == 0
    pb.controleer(m["bestand"])


def test_a_page_gets_its_theme_part_second_theme_and_country_only_from_the_closed_lists(tmp_path):
    lab = _lab(tmp_path)
    a = _claim(lab, 1, "Vaccines contain microchips")
    b = _claim(lab, 2, "Ukraine hosts biolabs")
    c = _claim(lab, 3, "Something odd")
    d = _claim(lab, 4, "No answer for this one")
    for claim in (a, b, c, d):
        _check(lab, claim, f"https://snopes.com/{claim}")
    indeling = {pb.nummer(a): {"thema": "health", "onderdeel": "vaccines", "tweede": "", "land": "IN"},
                pb.nummer(b): {"thema": "war", "onderdeel": "vaccines", "tweede": "health", "land": "ZZ"},
                pb.nummer(c): {"thema": "astrology", "onderdeel": "x", "tweede": "war", "land": "UA"}}
    m = _bouw(lab, tmp_path, indeling=indeling, themas=THEMAS, landen=LANDEN)
    pub = _pub(m)
    rij = {r["nummer"]: tuple(r)[1:] for r in pub.execute("SELECT nummer, thema, onderdeel, tweede, land FROM pagina")}
    assert rij[pb.nummer(a)] == ("health", "vaccines", "", "IN")
    assert rij[pb.nummer(b)] == ("war", "", "health", "")           # een onderdeel van een ander thema, een land dat niet bestaat
    assert rij[pb.nummer(c)] == (None, "", "", "")                  # een thema buiten de lijst is geen thema
    assert rij[pb.nummer(d)] == (None, "", "", "")
    themas = [tuple(r) for r in pub.execute("SELECT sleutel, ouder, volg, naam_nl, naam_fr FROM thema ORDER BY volg")]
    assert themas == [("health", None, 0, "Gezondheid", "Health"), ("vaccines", "health", 1, "Vaccins", "Vaccines"),
                      ("war", None, 2, "Oorlog en conflict", "War and conflict"),
                      ("ukraine", "war", 3, "Rusland en Oekraïne", "Russia and Ukraine")]
    # alleen de landen die voorkomen, met hun naam in vijf talen
    assert [tuple(r) for r in pub.execute("SELECT code, naam_nl, naam_en FROM land")] == [("IN", "India", "India")]
    assert m["met_thema"] == 2 and m["per_thema"] == {"health": 1, "war": 1}
    pb.controleer(m["bestand"])


def test_the_check_refuses_a_newsroom_under_two_spellings(tmp_path):
    """Eén naam per redactie (PLAN #34.2ao): een naam die alleen in kast, spaties of leestekens verschilt, maakt van één
    redactie er twee, in de lijst, het filter en de telling per bewering."""
    lab = _lab(tmp_path)
    _check(lab, _claim(lab, 1, "A"), "https://youturn.in/a")
    _check(lab, _claim(lab, 2, "B"), "https://en.youturn.in/b")
    lab.commit()
    fout = pb.bouw(lab, tmp_path / "uit", register={"youturn.in": "youturn", "en.youturn.in": "Youturn"}, vaag=frozenset(),
                   datum="2026-11-15")
    with pytest.raises(pb.Weigering, match="Youturn / youturn"):
        pb.controleer(fout["bestand"])
    m = pb.bouw(lab, tmp_path / "goed", register={"youturn.in": "Youturn", "en.youturn.in": "Youturn"}, vaag=frozenset(),
                datum="2026-11-15")
    pb.controleer(m["bestand"])


def test_the_check_refuses_a_page_with_a_theme_or_country_the_file_does_not_know(tmp_path):
    lab = _lab(tmp_path)
    a = _claim(lab, 1, "Vaccines contain microchips")
    _check(lab, a, "https://snopes.com/a")
    m = _bouw(lab, tmp_path, indeling={pb.nummer(a): {"thema": "health", "onderdeel": "", "tweede": "", "land": "IN"}},
              themas=THEMAS, landen=LANDEN)
    conn = sqlite3.connect(m["bestand"])
    conn.execute("UPDATE pagina SET thema = 'astrology'")
    conn.commit()
    with pytest.raises(pb.Weigering, match="thema"):
        pb.controleer(m["bestand"])


# --- taalcorrecties en de Engelse vertaling (PLAN #33.5, B32) -----------------------------------------------------------

def _variant(conn, claim_id, tekst, taal="en"):
    conn.execute("INSERT INTO claim_variant (claim_id, language, text, generator, prompt_version, model_version, payload) "
                 "VALUES (?,?,?,?,?,?,?)", (claim_id, taal, tekst, "claude-haiku-5-5", "vertalingen-v1", "m", b"x"))


def test_a_corrected_language_goes_with_the_claim_everywhere_and_an_unknown_code_changes_nothing(tmp_path):
    lab = _lab(tmp_path)
    portugees = _claim(lab, 1, "Cacau Show está vendendo caixa branca", taal="es")
    arabisch = _claim(lab, 2, "هذا ادعاء", taal="und")
    gewoon = _claim(lab, 3, "The moon is made of cheese", taal="en")
    raar = _claim(lab, 4, "Something", taal="en")
    lid = _claim(lab, 5, "Zelensky comprou uma casa", taal="gl", cluster="c1")
    hoofd = _claim(lab, 6, "Zelensky bought a villa", taal="en", cluster="c1")
    for i, (c, taal) in enumerate([(portugees, "es"), (arabisch, "und"), (gewoon, "en"), (raar, "en"), (lid, "gl"),
                                   (hoofd, "en"), (hoofd, "en")]):
        _check(lab, c, f"https://snopes.com/{i}", taal=taal)
    talen = {pb.nummer(portugees): "pt", pb.nummer(arabisch): "ar", pb.nummer(lid): "pt", pb.nummer(raar): "Not A Code"}
    manifest = _bouw(lab, tmp_path, talen=talen)
    pub = _pub(manifest)
    rij = {r["nummer"]: r for r in pub.execute("SELECT * FROM pagina")}
    assert rij[pb.nummer(portugees)]["taal"] == "pt"
    assert (rij[pb.nummer(arabisch)]["taal"], rij[pb.nummer(arabisch)]["richting"]) == ("ar", "rtl")     # de richting volgt
    assert rij[pb.nummer(gewoon)]["taal"] == "en" and rij[pb.nummer(raar)]["taal"] == "en"
    assert pub.execute("SELECT taal FROM check_ WHERE pagina = ?", (pb.nummer(portugees),)).fetchone()[0] == "pt"
    assert pub.execute("SELECT taal FROM formulering WHERE nummer = ?", (pb.nummer(lid),)).fetchone()[0] == "pt"
    assert json.loads(rij[pb.nummer(hoofd)]["talen"]) == ["en", "pt"]                                   # geteld na de correctie
    assert manifest["taalcorrecties"] == 3
    zonder = _pub(_bouw(lab, tmp_path, naam="zonder"))
    assert zonder.execute("SELECT taal FROM pagina WHERE nummer = ?", (pb.nummer(portugees),)).fetchone()[0] == "es"


def test_the_english_translation_goes_with_a_claim_in_another_language_and_is_found_by_its_words(tmp_path):
    lab = _lab(tmp_path)
    spaans = _claim(lab, 1, "Nespresso regala cafeteras", taal="es")
    engels = _claim(lab, 2, "The moon is made of cheese", taal="en")
    galicisch = _claim(lab, 3, "Na Itália chove", taal="gl")              # de leesproef vond hier een fout (B32, §117)
    onbekend = _claim(lab, 4, "Blabla", taal="und")
    eigenlijk_engels = _claim(lab, 5, "Says Maria Corina Machado won", taal="es")
    zonder = _claim(lab, 6, "Sin traducción", taal="es")
    for i, (c, taal) in enumerate([(spaans, "es"), (engels, "en"), (galicisch, "gl"), (onbekend, "und"),
                                   (eigenlijk_engels, "es"), (zonder, "es")]):
        _check(lab, c, f"https://snopes.com/{i}", taal=taal)
    _variant(lab, spaans, "Nespresso gives away coffee machines")
    _variant(lab, spaans, "A second wording nobody shows")
    _variant(lab, spaans, "Nespresso verschenkt Kaffeemaschinen", taal="de")
    _variant(lab, engels, "The moon consists of cheese")
    _variant(lab, galicisch, "After Italy it rains")
    _variant(lab, onbekend, "Blah")
    _variant(lab, eigenlijk_engels, "Says Maria Corina Machado has won")
    talen = {pb.nummer(galicisch): "pt", pb.nummer(onbekend): "tr", pb.nummer(eigenlijk_engels): "en"}
    manifest = _bouw(lab, tmp_path, talen=talen)
    pub = _pub(manifest)
    rijen = [tuple(r) for r in pub.execute("SELECT pagina, taal, tekst, maker, nagelezen FROM vertaling")]
    # Alleen de Spaanse bewering: Engels heeft geen vertaling nodig, ook niet als het label eerst Spaans zei; bij het
    # label Galicisch of onbekend blijft de vertaling weg, ook nu de taal hersteld is: daar is ze niet op nagelezen.
    assert rijen == [(pb.nummer(spaans), "en", "Nespresso gives away coffee machines",
                      "claude-haiku-5-5, vertalingen-v1", 0)]
    assert manifest["vertalingen"] == 1
    assert [r[0] for r in pub.execute("SELECT nummer FROM zoek WHERE zoek MATCH '\"coffee\"'")] == [pb.nummer(spaans)]
    # het register op drietallen (voor schriften zonder spaties) houdt alleen de bewering zelf: het bestand blijft klein
    assert pub.execute("SELECT COUNT(*) FROM zoek3 WHERE zoek3 MATCH '\"machines\"'").fetchone()[0] == 0
    assert pb.controleer(manifest["bestand"])["paginas"] == 6


def test_the_check_refuses_a_translation_that_stands_alone_or_repeats_the_language_of_its_claim(tmp_path):
    lab = _lab(tmp_path)
    spaans = _claim(lab, 1, "Nespresso regala cafeteras", taal="es")
    _check(lab, spaans, "https://snopes.com/1", taal="es")
    _variant(lab, spaans, "Nespresso gives away coffee machines")
    manifest = _bouw(lab, tmp_path)
    conn = sqlite3.connect(manifest["bestand"])
    conn.execute("UPDATE vertaling SET taal = 'es'")
    conn.commit()
    conn.close()
    with pytest.raises(pb.Weigering):
        pb.controleer(manifest["bestand"])


def test_a_display_translation_that_only_repeats_the_claim_is_not_a_translation(tmp_path):
    lab = _lab(tmp_path)
    naam = _claim(lab, 1, "Claudia Sheinbaum", taal="es")
    citaat = _claim(lab, 2, "“Claim Floating Tree.”", taal="en")
    echt = _claim(lab, 3, "The moon is made of cheese", taal="en")
    for i, c in enumerate((naam, citaat, echt), 1):
        _check(lab, c, f"https://snopes.com/{i}", taal="es" if c == naam else "en")
    vertalingen = {"nl": {pb.nummer(naam): "Claudia Sheinbaum", pb.nummer(citaat): "claim  floating tree",
                          pb.nummer(echt): "De maan is van kaas"}}
    manifest = _bouw(lab, tmp_path, vertalingen=vertalingen, vertaalmaker="claude-haiku-5-5, weergave-v1")
    rijen = {r["pagina"] for r in _pub(manifest).execute("SELECT pagina FROM vertaling WHERE taal = 'nl'")}
    # dezelfde woorden als het origineel (hoofdletters, witruimte en aanhalingstekens tellen niet) zeggen de lezer niets
    assert rijen == {pb.nummer(echt)}


def test_an_english_display_translation_fills_only_a_page_without_an_english_version_from_the_lab(tmp_path):
    """PLAN #34.2x: Engels uit de vertaalstap alleen waar het lab geen Engelse versie schreef, nooit eroverheen."""
    lab = _lab(tmp_path)
    spaans = _claim(lab, 1, "Nespresso regala cafeteras", taal="es")
    portugees = _claim(lab, 2, "Lula vendeu a Amazônia", taal="pt")
    engels = _claim(lab, 3, "The moon is made of cheese", taal="en")
    for i, c in enumerate((spaans, portugees, engels), 1):
        _check(lab, c, f"https://snopes.com/{i}", taal={spaans: "es", portugees: "pt"}.get(c, "en"))
    _variant(lab, spaans, "Nespresso gives away coffee machines")
    vertalingen = {"en": {pb.nummer(spaans): "Nespresso is giving coffee makers", pb.nummer(portugees): "Lula sold the Amazon",
                          pb.nummer(engels): "The moon consists of cheese"}}
    makers = {"en": "claude-sonnet-5-5, weergave-v1", "nl": "claude-haiku-5-5, weergave-v1"}
    manifest = _bouw(lab, tmp_path, vertalingen=vertalingen, vertaalmaker=makers)
    rijen = {r["pagina"]: (r["tekst"], r["maker"]) for r in _pub(manifest).execute("SELECT * FROM vertaling")}
    # de maker per doeltaal: het Engels van de vertaalstap komt van Sonnet, nooit onder de naam van Haiku
    assert rijen == {pb.nummer(spaans): ("Nespresso gives away coffee machines", "claude-haiku-5-5, vertalingen-v1"),
                     pb.nummer(portugees): ("Lula sold the Amazon", "claude-sonnet-5-5, weergave-v1")}


def test_display_translations_that_passed_their_reading_go_in_per_language_and_into_the_word_search(tmp_path):
    lab = _lab(tmp_path)
    spaans = _claim(lab, 1, "Nespresso regala cafeteras", taal="es")
    engels = _claim(lab, 2, "The moon is made of cheese", taal="en")
    weg = _claim(lab, 3, "Only fetched by ourselves", taal="en")
    _check(lab, spaans, "https://snopes.com/1", taal="es")
    _check(lab, engels, "https://snopes.com/2")
    _check(lab, weg, "https://maldita.es/3", bron=EIGEN)
    _variant(lab, spaans, "Nespresso gives away coffee machines")
    vertalingen = {"nl": {pb.nummer(spaans): "Nespresso geeft koffiemachines weg", pb.nummer(engels): "De maan is van kaas",
                          pb.nummer(weg): "Heeft geen pagina", "0000000000000000": "Bestaat niet"},
                   "es": {pb.nummer(spaans): "Una traducción al idioma de la propia afirmación",
                          pb.nummer(engels): "La luna es de queso"},
                   "xx": {pb.nummer(engels): "Geen taal van de site"}}
    manifest = _bouw(lab, tmp_path, vertalingen=vertalingen, vertaalmaker="claude-haiku-5-5, weergave-v1")
    pub = _pub(manifest)
    rijen = {(r["pagina"], r["taal"]): (r["tekst"], r["maker"]) for r in pub.execute("SELECT * FROM vertaling")}
    assert rijen == {
        (pb.nummer(spaans), "en"): ("Nespresso gives away coffee machines", "claude-haiku-5-5, vertalingen-v1"),
        (pb.nummer(spaans), "nl"): ("Nespresso geeft koffiemachines weg", "claude-haiku-5-5, weergave-v1"),
        (pb.nummer(engels), "nl"): ("De maan is van kaas", "claude-haiku-5-5, weergave-v1"),
        (pb.nummer(engels), "es"): ("La luna es de queso", "claude-haiku-5-5, weergave-v1")}
    assert manifest["vertalingen"] == 4 and manifest["vertalingen_per_taal"] == {"en": 1, "es": 1, "nl": 2}
    # op woorden vindbaar in elke vertaling; het register op drietallen houdt alleen de bewering zelf
    assert [r[0] for r in pub.execute("SELECT nummer FROM zoek WHERE zoek MATCH '\"kaas\"'")] == [pb.nummer(engels)]
    assert [r[0] for r in pub.execute("SELECT nummer FROM zoek WHERE zoek MATCH '\"koffiemachines\"'")] == [pb.nummer(spaans)]
    assert pub.execute("SELECT COUNT(*) FROM zoek3 WHERE zoek3 MATCH '\"koffiemachines\"'").fetchone()[0] == 0
    assert pub.execute("SELECT COUNT(*) FROM zoek3 WHERE zoek3 MATCH '\"cafeteras\"'").fetchone()[0] == 1
    assert pb.controleer(manifest["bestand"])["paginas"] == 2


# --- de woorden van een redactie gelezen en vertaald, en lijkt op (PLAN #34.2o, #34.2p) -----------------------------------

def test_a_verdict_the_table_could_not_read_gets_the_reading_and_the_label_follows(tmp_path):
    lab = _lab(tmp_path)
    a = _claim(lab, 1, "Protesters raised a flag on the Eiffel Tower", taal="si")
    _check(lab, a, "https://snopes.com/a", oordeel="onbekend", eigen="අසත්‍යයි ", taal="si")
    b = _claim(lab, 2, "A tower turned red")
    _check(lab, b, "https://snopes.com/b", oordeel="onbekend", eigen="Explainer")
    c = _claim(lab, 3, "A scam is going round")
    _check(lab, c, "https://snopes.com/c", oordeel="onbekend", eigen="Scam")      # Snopes: geen oordeel
    m = _bouw(lab, tmp_path, oordelen={"අසත්‍යයි": "onwaar", "Scam": "onwaar"})
    pub = _pub(m)
    label = dict(pub.execute("SELECT nummer, label FROM pagina"))
    assert label[pb.nummer(a)] == "onwaar" and label[pb.nummer(b)] is None and label[pb.nummer(c)] is None
    assert m["oordelen_gelezen"] == 1
    # de woorden van de redactie blijven zoals ze waren
    assert pub.execute("SELECT oordeel_eigen FROM check_ WHERE pagina = ?", (pb.nummer(a),)).fetchone()[0] == "අසත්‍යයි "


def test_a_reading_never_overrides_the_table(tmp_path):
    lab = _lab(tmp_path)
    a = _claim(lab, 1, "x")
    _check(lab, a, "https://snopes.com/a", oordeel="waar", eigen="True")
    m = _bouw(lab, tmp_path, oordelen={"True": "onwaar"})
    assert _pub(m).execute("SELECT label FROM pagina").fetchone()[0] == "waar" and m["oordelen_gelezen"] == 0


def test_the_translation_of_a_newsrooms_words_goes_in_only_for_words_on_a_page_and_in_the_site_languages(tmp_path):
    lab = _lab(tmp_path)
    a = _claim(lab, 1, "x", taal="si")
    _check(lab, a, "https://snopes.com/a", oordeel="onwaar", eigen="අසත්‍යයි", taal="si")
    glos = {"en": "false", "nl": "onwaar", "de": "falsch", "es": "falso", "fr": "faux"}
    m = _bouw(lab, tmp_path, glossen={"අසත්‍යයි": glos, "Niet op een pagina": glos})
    rijen = sorted(tuple(r) for r in _pub(m).execute("SELECT tekst, taal, glos FROM oordeel_glos"))
    assert rijen == sorted(("අසත්‍යයි", t, g) for t, g in glos.items()) and m["glossen"] == 1
    pb.controleer(m["bestand"])


def test_lijkt_op_links_only_pages_that_exist_never_a_page_to_itself_in_their_order(tmp_path):
    lab = _lab(tmp_path)
    ids = [_claim(lab, i, f"claim {i}") for i in range(1, 5)]
    for i, cid in enumerate(ids):
        _check(lab, cid, f"https://snopes.com/{i}")
    nr = [pb.nummer(c) for c in ids]
    m = _bouw(lab, tmp_path, lijkt_op={nr[0]: [nr[2], nr[0], "0000000000000000", nr[1]], nr[3]: [nr[0]]})
    pub = _pub(m)
    assert [tuple(r) for r in pub.execute("SELECT pagina, volg, ander FROM lijkt_op ORDER BY pagina, volg")] == sorted(
        [(nr[0], 0, nr[2]), (nr[0], 1, nr[1]), (nr[3], 0, nr[0])])
    assert m["lijkt_op"] == {"paginas": 2, "verwijzingen": 3}
    pb.controleer(m["bestand"])


def test_the_same_claim_links_pages_both_ways_only_between_newsrooms_that_did_not_both_check_it(tmp_path):
    lab = _lab(tmp_path)
    ids = [_claim(lab, i, f"claim {i}") for i in range(1, 5)]
    for cid, url in zip(ids, ("https://snopes.com/a", "https://maldita.es/b", "https://factcheck.afp.com/c",
                              "https://snopes.com/d")):
        _check(lab, cid, url)
    nr = [pb.nummer(c) for c in ids]
    # nr[3] deelt Snopes met nr[0]: geen paar; een pagina die er niet is en een paar met zichzelf ook niet
    m = _bouw(lab, tmp_path, zelfde={nr[0]: [nr[1], nr[3], nr[0], "0000000000000000"], nr[2]: [nr[1]]})
    pub = _pub(m)
    assert sorted(tuple(r) for r in pub.execute("SELECT pagina, ander FROM zelfde")) == sorted(
        [(nr[0], nr[1]), (nr[1], nr[0]), (nr[1], nr[2]), (nr[2], nr[1])])
    assert [r[0] for r in pub.execute("SELECT ander FROM zelfde WHERE pagina = ? ORDER BY volg", (nr[1],))] == sorted(
        [nr[0], nr[2]])
    assert m["zelfde"] == {"paginas": 3, "verwijzingen": 4}
    pb.controleer(m["bestand"])


def test_the_check_refuses_the_same_claim_one_way_or_between_pages_of_one_newsroom(tmp_path):
    lab = _lab(tmp_path)
    a, b, c = (_claim(lab, i, f"claim {i}") for i in range(1, 4))
    for cid, url in ((a, "https://snopes.com/a"), (b, "https://maldita.es/b"), (c, "https://snopes.com/c")):
        _check(lab, cid, url)
    for i, vraag in enumerate(("INSERT INTO zelfde VALUES (?, 0, ?)",)):
        for x, y in ((a, b), (a, c)):
            m = _bouw(lab, tmp_path, naam=f"uit-{x[-1]}{y[-1]}")
            conn = sqlite3.connect(m["bestand"])
            conn.execute(vraag, (pb.nummer(x), pb.nummer(y)))
            if (x, y) == (a, c):     # beide kanten op, maar dezelfde redactie
                conn.execute(vraag.replace("0, ?", "1, ?"), (pb.nummer(y), pb.nummer(x)))
            conn.execute("UPDATE meta SET waarde = ? WHERE sleutel = 'controlegetal'", (pb.controlegetal(conn),))
            conn.commit()
            conn.close()
            with pytest.raises(pb.Weigering):
                pb.controleer(m["bestand"])


def test_the_check_refuses_a_translation_in_another_language_or_a_link_to_nothing(tmp_path):
    lab = _lab(tmp_path)
    a = _claim(lab, 1, "x")
    _check(lab, a, "https://snopes.com/a")
    m = _bouw(lab, tmp_path)
    for vraag in ("INSERT INTO oordeel_glos VALUES ('False', 'it', 'Falso')",
                  "INSERT INTO lijkt_op VALUES (?, 0, '0000000000000000')"):
        conn = sqlite3.connect(m["bestand"])
        conn.execute(vraag, (pb.nummer(a),)) if "?" in vraag else conn.execute(vraag)
        conn.execute("UPDATE meta SET waarde = ? WHERE sleutel = 'controlegetal'", (pb.controlegetal(conn),))
        conn.commit()
        conn.close()
        with pytest.raises(pb.Weigering):
            pb.controleer(m["bestand"])
        m = _bouw(lab, tmp_path, naam=f"uit-{len(vraag)}")


# Waarom het niet klopt (PLAN #34.2j, B77): de punten van EUvsDisinfo, alleen als de leesproef open is.
WAAROM_URL = "https://euvsdisinfo.eu/report/nazi-ukraine"
MEETING = {"punten": 292, "niet_gedragen": 3, "regels": "regels-v2", "lezer": "lezing-v2/haiku/medium"}


def test_why_it_is_false_holds_at_most_three_points_per_existing_page_with_the_link_to_the_case(tmp_path):
    lab = _lab(tmp_path)
    a = _claim(lab, 1, "Ukraine is a Nazi state")
    _check(lab, a, WAAROM_URL, bron=EU)
    b = _claim(lab, 2, "Garlic cures covid")
    _check(lab, b, "https://snopes.com/b")
    nr = pb.nummer(a)
    waarom = {"punten": {nr: {"punten": ["P1", "P2", "P3", "P4"], "url": WAAROM_URL},
                         "0000000000000000": {"punten": ["X"], "url": "https://euvsdisinfo.eu/report/x"}},
              "meting": MEETING}
    m = _bouw(lab, tmp_path, waarom=waarom)
    pub = _pub(m)
    assert [tuple(r) for r in pub.execute("SELECT pagina, volg, punt, url FROM waarom ORDER BY volg")] == [
        (nr, 0, "P1", WAAROM_URL), (nr, 1, "P2", WAAROM_URL), (nr, 2, "P3", WAAROM_URL)]
    assert json.loads(dict(pub.execute("SELECT sleutel, waarde FROM meta"))["waarom_meting"]) == MEETING
    assert m["waarom"] == {"paginas": 1, "punten": 3}
    pb.controleer(m["bestand"])


def test_without_an_open_reading_test_there_is_no_why_it_is_false(tmp_path):
    lab = _lab(tmp_path)
    _check(lab, _claim(lab, 1, "Ukraine is a Nazi state"), WAAROM_URL, bron=EU)
    m = _bouw(lab, tmp_path)
    pub = _pub(m)
    assert pub.execute("SELECT COUNT(*) FROM waarom").fetchone()[0] == 0
    assert "waarom_meting" not in dict(pub.execute("SELECT sleutel, waarde FROM meta"))
    assert m["waarom"] == {"paginas": 0, "punten": 0}


def test_the_check_refuses_a_why_point_that_a_person_removed(tmp_path):
    """B77: een gemelde fout is weg; staat ze toch in het bestand, dan mag het niet uit."""
    lab = _lab(tmp_path)
    a = _claim(lab, 1, "Ukraine is a Nazi state")
    _check(lab, a, WAAROM_URL, bron=EU)
    nr = pb.nummer(a)
    m = _bouw(lab, tmp_path, waarom={"punten": {nr: {"punten": ["P1", "P2"], "url": WAAROM_URL}}, "meting": MEETING})
    pb.controleer(m["bestand"], waarom_niet=[{"pagina": nr, "punt": "P3", "reden": "gemeld"}])
    for niet in ([{"pagina": nr, "punt": "P2", "reden": "gemeld"}], [{"pagina": nr, "reden": "gemeld"}]):
        with pytest.raises(pb.Weigering):
            pb.controleer(m["bestand"], waarom_niet=niet)


def test_the_check_refuses_a_why_point_without_a_page_beyond_three_or_with_a_link_elsewhere(tmp_path):
    lab = _lab(tmp_path)
    a = _claim(lab, 1, "x")
    _check(lab, a, WAAROM_URL, bron=EU)
    for i, vraag in enumerate(("INSERT INTO waarom VALUES ('0000000000000000', 0, 'x', 'https://euvsdisinfo.eu/report/x')",
                               "INSERT INTO waarom VALUES (?, 3, 'x', 'https://euvsdisinfo.eu/report/x')",
                               "INSERT INTO waarom VALUES (?, 0, 'x', 'https://elders.example/report/x')")):
        m = _bouw(lab, tmp_path, naam=f"uit-waarom-{i}")
        conn = sqlite3.connect(m["bestand"])
        conn.execute(vraag, (pb.nummer(a),)) if "?" in vraag else conn.execute(vraag)
        conn.execute("UPDATE meta SET waarde = ? WHERE sleutel = 'controlegetal'", (pb.controlegetal(conn),))
        conn.commit()
        conn.close()
        with pytest.raises(pb.Weigering):
            pb.controleer(m["bestand"])


def test_a_second_release_on_one_day_gets_a_letter_and_nothing_else_is_a_release_name():
    from datetime import date
    assert pb.releasenaam() == date.today().isoformat()
    assert pb.releasenaam("2026-11-16b") == "2026-11-16b"
    for fout in ("2026-11-16-b", "16-11-2026", "2026-11-16bb", "../2026-11-16", "2026-11-16B"):
        with pytest.raises(pb.Weigering):
            pb.releasenaam(fout)


# --- wie het oordeel draagt: het stempel "Onwaar volgens ..." (PLAN #34.2cc, DESIGN §4y) ---------------------------------

def _k(redactie, oordeel, datum="2025-01-01"):
    return {"redactie": redactie, "oordeel": oordeel, "datum": datum}


def test_the_newsrooms_behind_a_verdict_are_those_that_reached_it_most_checks_first():
    checks = [_k("DW", "onwaar"), _k("BR24", "onwaar"), _k("BR24", "onwaar", "2025-02-01"), _k("Snopes", "waar")]
    assert pb.wie_het_zegt("onwaar", checks) == ["BR24", "DW"]


def test_false_or_misleading_counts_both_and_disputed_names_everyone_with_a_verdict():
    checks = [_k("dpa", "misleidend"), _k("AFP", "onwaar"), _k("X", "onbekend")]
    assert pb.wie_het_zegt("onwaar-of-misleidend", checks) == ["AFP", "dpa"]
    assert pb.wie_het_zegt("omstreden", [_k("PolitiFact", "deels-waar"), _k("FactCheck.org", "misleidend"),
                                         _k("Y", "onbekend")]) == ["FactCheck.org", "PolitiFact"]


def test_without_a_verdict_or_a_match_every_newsroom_is_named():
    assert pb.wie_het_zegt(None, [_k("A", "onbekend"), _k("B", "onbekend")]) == ["A", "B"]
    assert pb.wie_het_zegt("waar", [_k("A", "onwaar")]) == ["A"]


def test_a_search_question_goes_in_only_with_the_exact_text_it_came_from(tmp_path):
    """PLAN #34.2cf, B87: de zoekvraag hoort bij een tekst; verandert de bewering of haar vertaling, dan blijft de oude
    vraag weg (de pagina houdt dan *Klopt dit?*)."""
    lab = _lab(tmp_path)
    a = _claim(lab, 1, "Garlic cures covid")
    _check(lab, a, "https://snopes.com/garlic")
    b = _claim(lab, 2, "Ginger cures covid")
    _check(lab, b, "https://snopes.com/ginger")
    lab.commit()
    na, nb = pb.nummer(a), pb.nummer(b)
    vragen = {na: {"taal": "en", "bron": "Garlic cures covid", "vraag": "Does garlic cure covid?", "onderwerp": "Garlic and covid"},
              nb: {"taal": "en", "bron": "Ginger cures the flu", "vraag": "Does ginger cure the flu?", "onderwerp": "Ginger"}}
    m = pb.bouw(lab, tmp_path / "uit", register=REGISTER, vaag=frozenset(), datum="2026-11-22", zoekvragen=vragen)
    assert m["zoekvragen"] == {"mee": 1, "verouderd": 1}
    pub = sqlite3.connect(m["bestand"])
    assert pub.execute("SELECT pagina, taal, vraag, onderwerp FROM zoekvraag").fetchall() == [
        (na, "en", "Does garlic cure covid?", "Garlic and covid")]
    pb.controleer(m["bestand"])


def test_a_page_with_a_private_person_in_a_sensitive_context_and_a_page_not_read_stay_out_of_search(tmp_path):
    """PLAN #34.2bw, maatregel 2: een pagina die een privépersoon noemt bij een misdaad, ziekte, dood of seksualiteit, of
    een minderjarige, staat in de tabel `afscherming`; een pagina waarvan de tekst nog niet gelezen is ook (twijfel
    versoepelt nooit). Zonder lezing van het lab (een test, een oude bouw) is er geen afscherming."""
    lab = _lab(tmp_path)
    a = _claim(lab, 1, "Jan de Vries uit Almere stak een agent neer", taal="nl")
    b = _claim(lab, 2, "Garlic cures covid")
    c = _claim(lab, 3, "Ginger cures covid")
    d = _claim(lab, 4, "Onions cure covid")
    for x, u in ((a, "a"), (b, "b"), (c, "c"), (d, "d")):
        _check(lab, x, f"https://snopes.com/{u}")
    lab.commit()
    na, nb, nc, nd = (pb.nummer(x) for x in (a, b, c, d))
    lezing = {na: {"bron": "Jan de Vries uit Almere stak een agent neer", "afschermen": True},
              nb: {"bron": "Garlic cures covid", "afschermen": False},
              nd: {"bron": "Onions cure the flu", "afschermen": False}}          # een lezing van een oude tekst
    m = pb.bouw(lab, tmp_path / "uit", register=REGISTER, vaag=frozenset(), datum="2026-11-22", afscherming=lezing)
    assert m["afscherming"] == {"privepersoon": 1, "niet_gelezen": 2, "weggelaten": 0}
    pub = sqlite3.connect(m["bestand"])
    assert sorted(pub.execute("SELECT pagina, reden FROM afscherming")) == sorted(
        [(na, "privepersoon"), (nc, "niet_gelezen"), (nd, "niet_gelezen")])
    pb.controleer(m["bestand"])
    zonder = pb.bouw(lab, tmp_path / "zonder", register=REGISTER, vaag=frozenset(), datum="2026-11-22")
    assert sqlite3.connect(zonder["bestand"]).execute("SELECT COUNT(*) FROM afscherming").fetchone() == (0,)


def test_a_minor_is_left_out_with_a_mark_in_every_text_and_a_translation_without_the_name_is_left_out(tmp_path):
    """Bij een minderjarige die twee lezingen zo noemden (`privepersonen.uitgave_invoer`) staat op de plek van de naam het
    merkteken dat het platform als sticker *naam weggelaten* toont (`i18n.WEGGELATEN`): in de bewering, de vertalingen en
    de zoekvraag; in de zoekregisters niets. Een vertaling waarin de naam niet letterlijk staat (het Hindi schrijft haar
    anders) blijft weg, want daar is niet te zien of de naam erin staat. De naam staat nergens in de uitgave."""
    from factiz_site.i18n import WEGGELATEN as W

    lab = _lab(tmp_path)
    a = _claim(lab, 1, "Jamna Kumari, 12, was attacked in Gujarat")
    _check(lab, a, "https://snopes.com/attack")
    lab.commit()
    na = pb.nummer(a)
    bron = "Jamna Kumari, 12, was attacked in Gujarat"
    m = pb.bouw(lab, tmp_path / "uit", register=REGISTER, vaag=frozenset(), datum="2026-11-22", vertaalmaker="proef",
                vertalingen={"nl": {na: "Jamna Kumari, 12, werd aangevallen in Gujarat"},
                             "hi": {na: "जमना कुमारी, 12, पर गुजरात में हमला हुआ"}},
                zoekvragen={na: {"taal": "en", "bron": bron, "vraag": "Was Jamna Kumari, 12, attacked in Gujarat?",
                                 "onderwerp": "Jamna Kumari in Gujarat"}},
                afscherming={na: {"bron": bron, "afschermen": True, "naam": "Jamna Kumari"}})
    assert m["afscherming"] == {"privepersoon": 1, "niet_gelezen": 0, "weggelaten": 1}
    pub = sqlite3.connect(m["bestand"])
    assert pub.execute("SELECT bewering FROM pagina").fetchone() == (f"{W}, 12, was attacked in Gujarat",)
    assert dict(pub.execute("SELECT taal, tekst FROM vertaling")) == {"nl": f"{W}, 12, werd aangevallen in Gujarat"}
    assert pub.execute("SELECT vraag, onderwerp FROM zoekvraag").fetchone() == (f"Was {W}, 12, attacked in Gujarat?",
                                                                               f"{W} in Gujarat")
    assert not [t for (t,) in pub.execute("SELECT tekst FROM zoek UNION ALL SELECT tekst FROM zoek3") if W in t or "redacted" in t]
    alles = "\n".join(pub.iterdump())
    assert "Jamna" not in alles and "Kumari" not in alles and "जमना" not in alles
    pb.controleer(m["bestand"])


def test_the_check_refuses_a_left_out_name_on_a_page_that_is_not_shielded(tmp_path):
    from factiz_site.i18n import WEGGELATEN as W

    lab = _lab(tmp_path)
    _check(lab, _claim(lab, 1, "Garlic cures covid"), "https://snopes.com/garlic")
    lab.commit()
    m = pb.bouw(lab, tmp_path / "uit", register=REGISTER, vaag=frozenset(), datum="2026-11-22")
    pub = sqlite3.connect(m["bestand"])
    pub.execute("UPDATE pagina SET bewering = ?", (f"{W} cures covid",))
    pub.execute("UPDATE meta SET waarde = ? WHERE sleutel = 'controlegetal'", (pb.controlegetal(pub),))
    pub.commit()
    with pytest.raises(pb.Weigering, match="weggelaten naam"):
        pb.controleer(m["bestand"])


def test_a_claim_about_the_private_life_of_one_person_is_left_out_but_not_from_a_dossier(tmp_path):
    """PLAN #34.2ch (PO 2026-11-22: "Te particuliere dingen moeten er wat mij betreft uit"): een pagina die Haiku
    particulier las, met precies haar tekst, komt niet in de uitgave, ook haar andere formuleringen niet; een pagina in een
    dossier (een mens keurde haar goed) blijft. Een lezing van een oude tekst telt niet."""
    lab = _lab(tmp_path)
    a = _claim(lab, 1, "Help little Ana, 5, who has cancer", cluster="ana")
    a2 = _claim(lab, 2, "Help little Ana who has cancer, share", cluster="ana")
    b = _claim(lab, 3, "Bill Gates puts chips in vaccines")
    c = _claim(lab, 4, "Missing girl Helena in Vargem Grande")
    for x, u in ((a, "a"), (a2, "a2"), (b, "b"), (c, "c")):
        _check(lab, x, f"https://snopes.com/{u}")
    lab.commit()
    na, na2, nb, nc = (pb.nummer(x) for x in (a, a2, b, c))
    m = pb.bouw(lab, tmp_path / "uit", register=REGISTER, vaag=frozenset(), datum="2026-11-22",
                particulier={na: {"bron": "Help little Ana, 5, who has cancer"},
                             nc: {"bron": "Missing girl Helena in Vargem Grande, SP"}})          # een oude tekst
    pub = sqlite3.connect(m["bestand"])
    nummers = {n for (n,) in pub.execute("SELECT nummer FROM pagina")}
    assert na not in nummers and nb in nummers and nc in nummers
    assert pub.execute("SELECT COUNT(*) FROM verwijzing WHERE nummer = ? OR pagina = ?", (na2, na)).fetchone() == (0,)
    assert m["weggelaten"]["particulier"] == 1
    pb.controleer(m["bestand"])


def test_a_private_claim_read_with_a_left_out_name_is_still_left_out(tmp_path):
    """Haiku las de uitgave waarin de naam van een minderjarige al het merkteken was; dezelfde pagina gaat er dan uit."""
    from factiz_site.i18n import WEGGELATEN as W

    lab = _lab(tmp_path)
    a = _claim(lab, 1, "Help little Ana, 5, who has cancer")
    _check(lab, a, "https://snopes.com/ana")
    _check(lab, _claim(lab, 2, "Garlic cures covid"), "https://snopes.com/garlic")
    lab.commit()
    na = pb.nummer(a)
    m = pb.bouw(lab, tmp_path / "uit", register=REGISTER, vaag=frozenset(), datum="2026-11-22",
                afscherming={na: {"bron": "Help little Ana, 5, who has cancer", "afschermen": True, "naam": "Ana"}},
                particulier={na: {"bron": f"Help little {W}, 5, who has cancer"}})
    assert m["weggelaten"]["particulier"] == 1
    assert na not in {n for (n,) in sqlite3.connect(m["bestand"]).execute("SELECT nummer FROM pagina")}
