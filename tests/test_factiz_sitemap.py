"""De ingang voor de sitemaps (PLAN #34.2bt, SPECS E9.S8 AC3, AC4): per taal en stand welke factchecks vindbaar zijn, in
delen van hoogstens 50.000, en de namen. Stand 1 alleen de kern (B73 punt 5: meer dan één redactie, Ook gecheckt door of in
een dossier), stand 2 elke factcheck één keer, in de taal van haar bewering of anders in de versie die `x_default` noemt;
stand 3 in elke taal met eigen tekst (`i18n.eigen_talen`, DESIGNSYSTEEM §6). In Python en TypeScript gelijk
(`factiz_site.gelijk.ingangsadressen`)."""

import pytest
from starlette.testclient import TestClient

from doublecheck import publiceren as pb
from factiz_site import app as fa
from factiz_site import db, i18n
from tests.test_publiceren import REGISTER, _check, _claim, _lab


@pytest.fixture(scope="module")
def uitgave(tmp_path_factory):
    map_ = tmp_path_factory.mktemp("kaart")
    lab = _lab(map_)
    n = {"villa": _claim(lab, 1, "Zelensky bought a villa in Florida"),
         "arabisch": _claim(lab, 2, "زيلينسكي اشترى فيلا في فلوريدا", taal="ar"),
         "spaans": _claim(lab, 3, "Zelenski compró un yate de lujo", taal="es"),
         "telugu_en": _claim(lab, 4, "పచ్చి పాల వలన లాక్టోస్ అసహనం తగ్గుతుంది", taal="te"),
         "telugu_nl": _claim(lab, 5, "జెలెన్స్కీ ఫ్లోరిడాలో విల్లా కొన్నాడు", taal="te"),
         "telugu_kaal": _claim(lab, 6, "చంద్రుడు జున్నుతో తయారైంది", taal="te"),
         "onbekend": _claim(lab, 7, "xq zv wr", taal="und")}
    for i, (sleutel, cid) in enumerate(n.items()):
        _check(lab, cid, f"https://snopes.com/{sleutel}", datum=f"2024-0{1 + i % 9}-1{i}")
    # de villa bij een tweede redactie: de kern van stand 1 (B73 punt 5)
    _check(lab, n["villa"], "https://factcheck.afp.com/villa", datum="2022-04-01", taal="fr", eigen="Faux")
    lab.commit()
    nr = {k: pb.nummer(v) for k, v in n.items()}
    manifest = pb.bouw(lab, map_ / "uit", register=REGISTER, vaag=frozenset(), datum="2026-11-16", vertaalmaker="proef",
                       vertalingen={"nl": {nr["villa"]: "Zelensky kocht een villa in Florida",
                                           nr["telugu_nl"]: "Zelensky kocht een villa in Florida, op zijn Telugu"},
                                    "en": {nr["spaans"]: "Zelensky bought a luxury yacht",
                                           nr["telugu_en"]: "Raw milk reduces lactose intolerance"}})
    client = TestClient(fa.maak_app(manifest["bestand"]))
    client.bestand = manifest["bestand"]
    return client, nr


def _alles(client, taal, stand):
    telling = client.get(f"/api/{taal}/sitemap?stand={stand}")
    assert telling.status_code == 200, (taal, stand)
    t = telling.json()
    assert t["stand"] == stand and t["per_deel"] == db.SITEMAP_DEEL
    regels = []
    for deel in range(t["delen"]):
        d = client.get(f"/api/{taal}/sitemap?stand={stand}&deel={deel}").json()
        assert d["stand"] == stand and d["deel"] == deel
        regels += d["regels"]
    assert len(regels) == t["totaal"]
    return regels


def _per_pagina(client, stand):
    """{nummer: de talen waarin de sitemaps de pagina aanbieden}."""
    uit: dict[str, list[str]] = {}
    for taal in i18n.TALEN:
        for r in _alles(client, taal, stand):
            nummer = r["href"].rstrip("/").rsplit("/", 1)[1]
            assert r["href"] == i18n.pad(taal, "fact-checks", nummer)
            uit.setdefault(nummer, []).append(taal)
    return uit


def test_step_three_offers_each_fact_check_in_every_language_with_its_own_text(uitgave):
    client, nr = uitgave
    per = _per_pagina(client, 3)
    assert per[nr["villa"]] == ["en", "nl"]
    assert per[nr["arabisch"]] == ["ar"]
    assert per[nr["spaans"]] == ["en", "es"]
    assert per[nr["telugu_en"]] == ["en"] and per[nr["telugu_nl"]] == ["nl"]
    assert per[nr["telugu_kaal"]] == ["en"] and per[nr["onbekend"]] == ["en"]
    # precies wat de pagina zelf vindbaar noemt
    for nummer, talen in per.items():
        assert client.get(f"/api/en/factcheck/{nummer}").json()["vindbaar"]["talen"] == talen, nummer


def test_step_two_offers_each_fact_check_once_in_its_own_language_or_else_where_x_default_points(uitgave):
    client, nr = uitgave
    per = _per_pagina(client, 2)
    assert per[nr["villa"]] == ["en"] and per[nr["arabisch"]] == ["ar"] and per[nr["spaans"]] == ["es"]
    assert per[nr["telugu_en"]] == ["en"] and per[nr["telugu_nl"]] == ["nl"] and per[nr["telugu_kaal"]] == ["en"]
    assert per[nr["onbekend"]] == ["en"]
    for nummer, talen in per.items():
        v = client.get(f"/api/en/factcheck/{nummer}").json()
        eigen = v["taal"] if v["taal"] in i18n.TALEN else v["vindbaar"]["x_default"]
        assert talen == [eigen], nummer
    assert sum(len(t) for t in per.values()) == len(per)          # elke factcheck één keer


def test_step_one_offers_only_the_core_once_and_the_page_says_the_same(uitgave):
    """B73 punt 5: eerst de pagina's met meer dan één redactie, Ook gecheckt door of in een dossier."""
    client, nr = uitgave
    per = _per_pagina(client, 1)
    assert per == {nr["villa"]: ["en"]}
    for nummer in nr.values():
        kern = client.get(f"/api/en/factcheck/{nummer}").json()["vindbaar"]["kern"]
        assert kern is (nummer in per), nummer


def test_the_parts_hold_at_most_the_part_size_and_list_everything_once_in_order(uitgave, monkeypatch):
    client, _ = uitgave
    heel = _alles(client, "en", 3)
    monkeypatch.setattr(db, "SITEMAP_DEEL", 2)
    t = client.get("/api/en/sitemap?stand=3").json()
    assert t["per_deel"] == 2 and t["delen"] == -(-t["totaal"] // 2) and t["totaal"] == len(heel)
    delen = [client.get(f"/api/en/sitemap?stand=3&deel={d}").json()["regels"] for d in range(t["delen"])]
    assert all(1 <= len(d) <= 2 for d in delen) and [r for d in delen for r in d] == heel
    assert [r["href"] for r in heel] == sorted(r["href"] for r in heel)
    assert all(r["lastmod"] and len(r["lastmod"]) == 10 for r in heel)


@pytest.mark.parametrize("vraag", ["", "?stand=0", "?stand=4", "?stand=x", "?stand=1&stand=2", "?stand=1&deel=99",
                                   "?stand=1&deel=-1", "?stand=1&deel=x", "?deel=0", "?stand=1&x=1", "?soort=x",
                                   "?soort=namen&stand=1"])
def test_a_question_the_sitemap_does_not_know_is_not_found(uitgave, vraag):
    client, _ = uitgave
    assert client.get(f"/api/en/sitemap{vraag}").status_code == 404


def test_without_names_the_names_are_not_found_and_with_them_every_name_in_every_language(uitgave, tmp_path_factory):
    client, _ = uitgave
    assert client.get("/api/en/sitemap?soort=namen").status_code == 404
    from tests.test_site_html import _uitgave
    bestand, _ = _uitgave(tmp_path_factory.mktemp("kaart-namen"))
    met = TestClient(fa.maak_app(bestand))
    for taal in i18n.TALEN:
        regels = met.get(f"/api/{taal}/sitemap?soort=namen").json()["regels"]
        assert [r["href"] for r in regels] == [i18n.pad(taal, "names", q) for q in ("Q3874799", "Q99")]


def test_typescript_answers_every_sitemap_question_the_same_as_python(uitgave):
    """B80: het platform in TypeScript (de site, de Worker) geeft per taal en stand dezelfde delen als Python."""
    from factiz_site import gelijk
    client, _ = uitgave
    adressen = [f"/api/{taal}/sitemap?stand={s}{d}" for taal in i18n.TALEN for s in (1, 2, 3) for d in ("", "&deel=0")]
    adressen += [f"/api/en/sitemap{v}" for v in ("", "?stand=4", "?soort=namen", "?stand=1&deel=1", "?stand=3&deel=٣")]
    adressen += [f"/api/{taal}/factcheck/{n}" for taal in ("en", "nl") for n in uitgave[1].values()]
    assert gelijk.verschillen(client, client.bestand, adressen) == []


@pytest.fixture(scope="module")
def afgeschermd(tmp_path_factory):
    """Een uitgave waarin de villa (de kern) een privépersoon noemt bij een misdaad, en de arabische nog niet gelezen is."""
    map_ = tmp_path_factory.mktemp("kaart-afscherming")
    lab = _lab(map_)
    n = {"villa": _claim(lab, 1, "Zelensky bought a villa in Florida"),
         "arabisch": _claim(lab, 2, "زيلينسكي اشترى فيلا في فلوريدا", taal="ar"),
         "spaans": _claim(lab, 3, "Zelenski compró un yate de lujo", taal="es")}
    for i, (sleutel, cid) in enumerate(n.items()):
        _check(lab, cid, f"https://snopes.com/{sleutel}", datum=f"2024-0{1 + i}-1{i}")
    _check(lab, n["villa"], "https://factcheck.afp.com/villa", datum="2022-04-01", taal="fr", eigen="Faux")
    lab.commit()
    nr = {k: pb.nummer(v) for k, v in n.items()}
    manifest = pb.bouw(lab, map_ / "uit", register=REGISTER, vaag=frozenset(), datum="2026-11-22", vertaalmaker="proef",
                       vertalingen={"nl": {nr["villa"]: "Zelensky kocht een villa in Florida"}},
                       afscherming={nr["villa"]: {"bron": "Zelensky bought a villa in Florida", "afschermen": True},
                                    nr["spaans"]: {"bron": "Zelenski compró un yate de lujo", "afschermen": False}})
    client = TestClient(fa.maak_app(manifest["bestand"]))
    client.bestand = manifest["bestand"]
    return client, nr


def test_a_shielded_fact_check_is_in_no_sitemap_and_says_so_itself_in_python_and_typescript(afgeschermd):
    """PLAN #34.2bw, maatregel 2: een afgeschermde pagina staat in geen enkele stand in de sitemaps, ook niet als ze tot
    de kern hoort, en de pagina zegt `afgeschermd` (de site zet dan noindex). Lezen kan iedereen ze nog."""
    from factiz_site import gelijk
    client, nr = afgeschermd
    for stand in (1, 2, 3):
        per = _per_pagina(client, stand)
        assert nr["villa"] not in per and nr["arabisch"] not in per, stand
    assert _per_pagina(client, 2) == {nr["spaans"]: ["es"]}
    for sleutel, nummer in nr.items():
        v = client.get(f"/api/en/factcheck/{nummer}").json()["vindbaar"]
        assert v["afgeschermd"] is (sleutel != "spaans"), sleutel
    adressen = [f"/api/{taal}/sitemap?stand={s}{d}" for taal in ("en", "nl", "ar", "es") for s in (1, 2, 3) for d in ("", "&deel=0")]
    adressen += [f"/api/{taal}/factcheck/{n}" for taal in ("en", "nl") for n in nr.values()]
    assert gelijk.verschillen(client, client.bestand, adressen) == []


def test_the_site_offers_a_shielded_fact_check_to_no_search_engine_in_an_open_step():
    """`aanbodFactcheck` in de site: afgeschermd is in stand 1, 2 en 3 geen enkele taal; stand 0 is toch helemaal dicht."""
    import json
    import subprocess
    from pathlib import Path

    wortel = Path(__file__).resolve().parent.parent
    script = ("import('./site/src/lib/vindbaar.js').then((m) => { const v = { talen: ['en', 'nl'], x_default: 'en', "
              "kern: true, afgeschermd: true }; const w = { ...v, afgeschermd: false }; console.log(JSON.stringify("
              "[0, 1, 2, 3].map((s) => [m.aanbodFactcheck('en', v, ['en', 'nl'], s), m.aanbodFactcheck('en', w, ['en', 'nl'], s)]))) })")
    uit = subprocess.run(["node", "--input-type=module", "-e", script], cwd=wortel, capture_output=True, text=True, check=True)
    assert json.loads(uit.stdout) == [[["en", "nl"], ["en", "nl"]], [[], ["en"]], [[], ["en"]], [[], ["en", "nl"]]]


def test_the_site_turns_a_left_out_name_into_a_sticker_piece_and_leaves_other_text_alone():
    """`weggelaten.js`: ⟦naam weggelaten⟧ uit het platform wordt een eigen stuk, de rest blijft zoals het is."""
    import json
    import subprocess
    from pathlib import Path

    wortel = Path(__file__).resolve().parent.parent
    script = ("import('./src/lib/weggelaten.js').then((m) => console.log(JSON.stringify(["
              "m.stukken('\u27e6naam weggelaten\u27e7, 12, werd aangevallen'), m.stukken('Zelensky kocht een villa'), "
              "m.stukken('Was \u27e6name withheld\u27e7 attacked?')])))")
    uit = subprocess.run(["node", "--input-type=module", "-e", script], cwd=wortel / "site", capture_output=True, text=True,
                         check=True)
    assert json.loads(uit.stdout) == [[["naam weggelaten", True], [", 12, werd aangevallen", False]],
                                      [["Zelensky kocht een villa", False]],
                                      [["Was ", False], ["name withheld", True], [" attacked?", False]]]
