"""De feed van Data Commons stopt (B91, PLAN #37.12): een check van Data Commons komt alleen nog in een uitgave als hij in de
uitgave van 2026-11-23 stond; nieuwe factchecks komen uit de wereldlijst."""

import gzip
import sqlite3

import pytest

from doublecheck import feedstop as fs
from doublecheck import publiceren as pb
from tests.test_publiceren import CCBY, EU, _bouw, _check, _claim, _lab, _pub


def test_a_feed_check_that_was_not_live_on_23_november_never_enters_an_edition(tmp_path):
    lab = _lab(tmp_path)
    oud = _claim(lab, 1, "Old claim that was live")
    nieuw = _claim(lab, 2, "New claim from a later feed")
    zelfde = _claim(lab, 3, "Old claim with a new check from the feed")
    rus = _claim(lab, 4, "Claim checked by EUvsDisinfo")
    _check(lab, oud, "https://factcheck.afp.com/a")
    _check(lab, nieuw, "https://factcheck.afp.com/b")
    _check(lab, zelfde, "https://factcheck.afp.com/c")
    _check(lab, zelfde, "https://maldita.es/d")                 # dezelfde bewering, een nieuwe check uit de feed
    _check(lab, rus, "https://euvsdisinfo.eu/report/e", bron=EU)
    bevroren = frozenset({fs.sleutel(oud, "https://factcheck.afp.com/a"), fs.sleutel(zelfde, "https://factcheck.afp.com/c")})
    m = _bouw(lab, tmp_path, feed=bevroren)
    pub = _pub(m)
    paginas = {r["bewering"] for r in pub.execute("SELECT bewering FROM pagina")}
    assert paginas == {"Old claim that was live", "Old claim with a new check from the feed", "Claim checked by EUvsDisinfo"}
    assert {r["url"] for r in pub.execute("SELECT url FROM check_")} == {
        "https://factcheck.afp.com/a", "https://factcheck.afp.com/c", "https://euvsdisinfo.eu/report/e"}


def test_without_a_freeze_the_selection_still_takes_every_feed_check(tmp_path):
    """Alleen voor de proeven: `publiceren bouwen` geeft het bestand altijd mee (`feedstop.lees`)."""
    lab = _lab(tmp_path)
    _check(lab, _claim(lab, 1, "A claim"), "https://factcheck.afp.com/a")
    assert _pub(_bouw(lab, tmp_path)).execute("SELECT COUNT(*) FROM check_").fetchone()[0] == 1


def test_the_build_refuses_without_the_freeze_file(tmp_path):
    with pytest.raises(fs.Weigering):
        fs.lees(tmp_path / "geen.txt.gz")


def test_the_freeze_takes_exactly_the_pairs_that_were_live(tmp_path):
    lab = _lab(tmp_path)
    a, b, c = (_claim(lab, n, f"Claim {n}") for n in (1, 2, 3))
    _check(lab, a, "https://factcheck.afp.com/a")
    _check(lab, b, "https://factcheck.afp.com/b")                # bij b alleen deze check live
    _check(lab, b, "https://maldita.es/b2")
    _check(lab, c, "https://factcheck.afp.com/c")                # c stond niet live
    _check(lab, a, "https://euvsdisinfo.eu/report/x", bron=EU)  # geen check van de feed
    lab.commit()
    uitgave = sqlite3.connect(tmp_path / "uitgave.db")
    uitgave.executescript("CREATE TABLE pagina (nummer TEXT); CREATE TABLE formulering (pagina TEXT, nummer TEXT); "
                          "CREATE TABLE check_ (pagina TEXT, url TEXT, bron TEXT);")
    p1 = pb.nummer(a)                                            # de hoofdformulering is het nummer van de pagina
    uitgave.execute("INSERT INTO pagina VALUES (?)", (p1,))
    uitgave.execute("INSERT INTO formulering VALUES (?,?)", (p1, pb.nummer(b)))
    uitgave.executemany("INSERT INTO check_ VALUES (?,?,?)", [
        (p1, "https://factcheck.afp.com/a", CCBY), (p1, "https://factcheck.afp.com/b", CCBY),
        (p1, "https://euvsdisinfo.eu/report/x", "euvsdisinfo")])
    assert fs.uit_uitgave(lab, uitgave) == sorted({fs.sleutel(a, "https://factcheck.afp.com/a"),
                                                   fs.sleutel(b, "https://factcheck.afp.com/b")})


def test_the_frozen_file_is_read_back_whole(tmp_path):
    pad = tmp_path / "bevroren.txt.gz"
    fs.schrijf(["b" * 16, "a" * 16], pad, uitgave="2026-11-23")
    assert fs.lees(pad) == frozenset({"a" * 16, "b" * 16})
    regels = gzip.decompress(pad.read_bytes()).decode().splitlines()
    assert regels[0] == "# feed van Data Commons, bevroren op uitgave 2026-11-23: 2 checks" and regels[1:] == ["a" * 16, "b" * 16]


def test_the_freeze_of_23_november_holds_every_feed_check_that_was_live():
    """Het bestand in de repo: de checks van Data Commons in de uitgave van 2026-11-23 (94.202, PLAN #37.12)."""
    bevroren = fs.lees()
    kop = gzip.decompress(fs.BESTAND.read_bytes()).decode().splitlines()[0]
    assert kop.startswith("# feed van Data Commons, bevroren op uitgave 2026-11-23: ")
    assert len(bevroren) == int(kop.rsplit(": ", 1)[1].split()[0]) > 90_000
    assert all(len(s) == 16 for s in bevroren)
