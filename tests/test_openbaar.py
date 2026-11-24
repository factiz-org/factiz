"""Het openbare repo als stand van het lab (PLAN #34.2bl, PO 2026-11-24: "Ja, schone start met een nieuw openbaar repo").

Wat intern is, komt nooit in de boom van de branch `openbaar`; een thuismap, het eigen e-mailadres of een regel uit de
weigerlijst houdt de hele stand tegen; de commit heeft Factiz als auteur en geen co-auteurregel."""
import json
import subprocess

import pytest

from doublecheck import openbaar


def _git(wortel, *args, **kw):
    return subprocess.run(["git", "-C", str(wortel), *args], check=True, capture_output=True, text=True, **kw).stdout


def _schrijf(wortel, pad, tekst):
    p = wortel / pad
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(tekst) if isinstance(tekst, str) else p.write_bytes(tekst)


@pytest.fixture
def lab(tmp_path):
    w = tmp_path / "lab"
    w.mkdir()
    _git(w, "init", "-q", "-b", "werk")
    _git(w, "config", "user.email", "iemand@voorbeeld.nl")
    _git(w, "config", "user.name", "Iemand")
    _schrijf(w, "docs/PLAN.md", "# Plan\n")
    _schrijf(w, "docs/HANDOFF.md", "intern\n")
    _schrijf(w, "docs/voorstellen/mail.md", "Beste partner\n")
    _schrijf(w, "docs/pers/persbericht.md", "Embargo\n")
    _schrijf(w, "content/redactie/af/check.toml", 'status = "gepubliceerd"\n')
    _schrijf(w, "content/redactie/af/vertalingen/en.json", "{}\n")
    _schrijf(w, "content/redactie/bezig/check.toml", 'status = "concept"\n')
    _schrijf(w, "content/redactie/bezig/vertalingen/en.json", "{}\n")
    _schrijf(w, "content/redactie/gelezen/check.toml", 'status = "nagelezen"\n')
    _schrijf(w, "factiz_site/static/redactie/af/post.jpg", b"\xff\xd8beeld")
    _schrijf(w, "factiz_site/static/redactie/bezig/post.jpg", b"\xff\xd8beeld")
    duel = {"toelichting": "De keuzes van de PO.", "labels": [{"id": "a", "klopt": "factiz", "opmerking": "mijn gedachte"}]}
    _schrijf(w, "docs/steekproeven/duel-2026-11-07.json", json.dumps(duel, ensure_ascii=False, indent=1) + "\n")
    kaart = {"toelichting": "Kaartenbak.", "keuzes": {"O:1": {"keuze": "goed", "opmerking": "twijfel"}}}
    _schrijf(w, "docs/steekproeven/poproef-2026-11-07.json", json.dumps(kaart, ensure_ascii=False, indent=1) + "\n")
    oordelen = {"toelichting": "Oordelen.", "labels": {"ab12": {"categorie": "onwaar", "reden": "'Still Illegal': niets"}}}
    _schrijf(w, "docs/steekproeven/32.38-oordelen.json", json.dumps(oordelen, ensure_ascii=False, indent=1) + "\n")
    afp = {"toelichting": "AFP.", "checks": [{"id": "afp-01", "titel": "Kop van AFP", "url": "https://afp.example/1"}]}
    _schrijf(w, "docs/steekproeven/37.0-maatstaf.json", json.dumps(afp, ensure_ascii=False, indent=1) + "\n")
    _schrijf(w, "docs/steekproeven/andere.json", json.dumps({"labels": [{"opmerking": "blijft"}]}) + "\n")
    _git(w, "add", "-A")
    _git(w, "commit", "-q", "-m", "begin")
    return w


def _boom(wortel):
    return set(_git(wortel, "ls-tree", "-r", "--name-only", "openbaar").split())


def _blob(wortel, pad):
    return _git(wortel, "show", f"openbaar:{pad}")


def test_internal_documents_and_unpublished_checks_never_reach_the_public_tree(lab):
    openbaar.maken(lab, van="werk")
    boom = _boom(lab)
    assert "docs/PLAN.md" in boom
    assert "content/redactie/af/check.toml" in boom and "content/redactie/af/vertalingen/en.json" in boom
    for pad in boom:
        assert not pad.startswith(("docs/voorstellen/", "docs/pers/", "content/redactie/bezig/",
                                   "content/redactie/gelezen/", "factiz_site/static/redactie/")), pad
    assert "docs/HANDOFF.md" not in boom


def test_po_remarks_are_stripped_but_the_choices_stay(lab):
    openbaar.maken(lab, van="werk")
    duel = json.loads(_blob(lab, "docs/steekproeven/duel-2026-11-07.json"))
    assert duel["labels"] == [{"id": "a", "klopt": "factiz"}]
    assert "zonder de opmerkingen van de PO" in duel["toelichting"]
    kaart = json.loads(_blob(lab, "docs/steekproeven/poproef-2026-11-07.json"))
    assert kaart["keuzes"] == {"O:1": {"keuze": "goed"}}
    assert json.loads(_blob(lab, "docs/steekproeven/andere.json")) == {"labels": [{"opmerking": "blijft"}]}


def test_self_read_fact_checks_keep_only_their_id_or_link(lab):
    openbaar.maken(lab, van="werk")
    oordelen = json.loads(_blob(lab, "docs/steekproeven/32.38-oordelen.json"))
    assert oordelen["labels"] == {"ab12": {"categorie": "onwaar"}}
    afp = json.loads(_blob(lab, "docs/steekproeven/37.0-maatstaf.json"))
    assert afp["checks"] == [{"id": "afp-01", "url": "https://afp.example/1"}]
    assert "zelf van de sites van redacties las" in afp["toelichting"]


def test_a_home_path_stops_the_whole_version(lab):
    _schrijf(lab, "docs/notitie.md", "zie /Users/" + "iemand/dev/factiz\n")  # in delen, anders weigert het zichzelf
    _git(lab, "add", "-A")
    _git(lab, "commit", "-q", "-m", "pad")
    with pytest.raises(openbaar.Geweigerd, match="docs/notitie.md"):
        openbaar.maken(lab, van="werk")
    assert subprocess.run(["git", "-C", str(lab), "rev-parse", "--verify", "-q", "openbaar"]).returncode != 0


def test_the_own_address_or_a_refused_line_stops_the_whole_version(lab):
    _schrijf(lab, "README.md", "Mail iemand@voorbeeld.nl\n")
    _git(lab, "add", "-A")
    _git(lab, "commit", "-q", "-m", "adres")
    with pytest.raises(openbaar.Geweigerd, match="README.md"):
        openbaar.maken(lab, van="werk")
    _schrijf(lab, "README.md", "Gemaakt door Volle Naam\n")
    _schrijf(lab, "data/openbaar/weiger.txt", "# niet openbaar\nVolle Naam\n")
    _git(lab, "add", "README.md")
    _git(lab, "commit", "-q", "-m", "naam")
    with pytest.raises(openbaar.Geweigerd, match="README.md"):
        openbaar.maken(lab, van="werk")


def test_a_value_from_env_stops_the_whole_version_without_showing_it(lab):
    geheim = "abcdefghijklmnopqrstuvwx123456"
    _schrijf(lab, ".env", f"SLEUTEL={geheim}\n")
    _schrijf(lab, "config.py", f"S = '{geheim}'\n")
    _git(lab, "add", "config.py")
    _git(lab, "commit", "-q", "-m", "sleutel")
    with pytest.raises(openbaar.Geweigerd) as fout:
        openbaar.maken(lab, van="werk")
    assert "config.py" in str(fout.value) and geheim not in str(fout.value)


def test_factiz_is_the_author_the_first_commit_has_no_parent_and_nothing_new_makes_no_commit(lab):
    eerste = openbaar.maken(lab, van="werk")
    assert _git(lab, "log", "-1", "--format=%an <%ae>|%cn <%ce>|%P", "openbaar").strip() == \
        "Factiz <info@factiz.org>|Factiz <info@factiz.org>|"
    bericht = _git(lab, "log", "-1", "--format=%B", "openbaar")
    assert "Co-Authored-By" not in bericht and "Claude" not in bericht
    assert openbaar.maken(lab, van="werk") is None
    _schrijf(lab, "docs/PLAN.md", "# Plan\nmeer\n")
    _git(lab, "commit", "-q", "-am", "meer")
    tweede = openbaar.maken(lab, van="werk")
    assert _git(lab, "log", "-1", "--format=%P", "openbaar").strip() == eerste
    assert tweede != eerste
    assert _git(lab, "rev-parse", "werk").strip() != _git(lab, "rev-parse", "openbaar").strip()
