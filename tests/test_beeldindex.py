"""De beelden die rondgingen indexeren (PLAN #25.11).

Per factcheckartikel de beelden lezen, alleen in het geheugen (DR3), en
alleen de PDQ-hash bewaren. Gemeten met echte kopieën (dezelfde virale foto
bij een andere redactie) en met kopieën die we bij het oogsten zelf maken;
een vraag vindt nooit de beelden van haar eigen claim.
"""

import io
import json
import urllib.robotparser

import numpy as np
from PIL import Image, ImageDraw

from doublecheck import beeldindex as bi
from doublecheck.storage import connect, init_schema

VERSIE = "pdq-256-v1"


def _foto(zaad=1, maat=(640, 480)):
    """Een beeld met structuur: PDQ geeft vlakken een lage kwaliteit."""
    rng = np.random.default_rng(zaad)
    beeld = Image.new("RGB", maat, "white")
    teken = ImageDraw.Draw(beeld)
    for _ in range(40):
        x, y = rng.integers(0, maat[0]), rng.integers(0, maat[1])
        teken.ellipse([x, y, x + rng.integers(20, 160), y + rng.integers(20, 160)],
                      fill=tuple(int(c) for c in rng.integers(0, 255, 3)))
    buf = io.BytesIO()
    beeld.save(buf, "JPEG", quality=90)
    return buf.getvalue()


def test_an_image_leaves_only_hashes_and_measurements_never_the_image():
    uit = bi.verwerk_beeld(_foto(), VERSIE)
    assert len(uit["pdq"]) == 64 and uit["kwaliteit"] >= 50
    assert (uit["breedte"], uit["hoogte"]) == (640, 480)
    assert set(uit["proeven"]) == {"jpeg50", "half", "stempel", "bijgesneden", "kader"}
    assert all(isinstance(h, str) and len(h) == 64 for h in uit["proeven"].values())
    tekst = json.dumps(uit)
    assert len(tekst) < 2_000, "er hoort geen beeld in de regel te zitten"


def test_a_recompressed_or_halved_copy_stays_within_the_threshold():
    uit = bi.verwerk_beeld(_foto(), VERSIE)
    origineel = bytes.fromhex(uit["pdq"])
    for soort in ("jpeg50", "half"):
        assert bi.afstand(origineel, bytes.fromhex(uit["proeven"][soort])) <= 31, soort


def _beeld(claim, artikel, url, hexa, kwaliteit=100, proeven=None):
    return bi.Beeld(claim, artikel, url, bytes.fromhex(hexa), kwaliteit, proeven or {})


H1 = "f" * 64
H1_KOPIE = "f" * 60 + "0000"          # 16 bits anders
H2 = "0" * 64
H3 = "0f" * 32
H4 = "f0" * 32


def test_the_cross_check_never_finds_the_own_claim_and_judges_by_cluster():
    """A en B zijn dezelfde claim bij twee redacties (één cluster); C staat in
    een ander cluster. A's beeld vindt B's kopie: goed. Het eigen tweede
    artikel van A telt niet mee."""
    beelden = [
        _beeld("A", "https://a.org/1", "https://a.org/1.jpg", H1),
        _beeld("A", "https://a.org/2", "https://a.org/2.jpg", H1),
        _beeld("B", "https://b.org/1", "https://b.org/1.jpg", H1_KOPIE),
        _beeld("C", "https://c.org/1", "https://c.org/1.jpg", H2),
    ]
    groep = {"A": "cl-1", "B": "cl-1", "C": "cl-2"}
    uit = bi.kruistoets(beelden, groep, 31)
    assert uit["goed"] == 3          # A/1 en A/2 vinden B, B vindt A
    assert uit["fout"] == 0 and uit["niets"] == 1    # C vindt niets
    assert uit["goed_andere_host"] == 3


def test_a_match_in_another_cluster_is_a_false_link_and_says_whose():
    """Bij een andere redactie kan het dezelfde foto bij een andere bewering
    zijn (B8: `related`); binnen één redactie is het huisstijl die de
    sjabloonregel miste. Het verslag houdt ze uit elkaar."""
    beelden = [_beeld("A", "https://a.org/1", "https://a.org/1.jpg", H1),
               _beeld("C", "https://c.org/1", "https://c.org/1.jpg", H1_KOPIE)]
    uit = bi.kruistoets(beelden, {"A": "cl-1", "C": "cl-2"}, 31)
    assert uit["fout"] == 2 and uit["goed"] == 0 and uit["fout_andere_host"] == 2


def test_templates_are_left_out_before_anything_is_measured():
    """Een logo of auteursfoto staat bij veel claims in verschillende
    clusters: dat is geen virale foto maar huisstijl."""
    logo = [_beeld(c, f"https://x.org/{c}", "https://x.org/logo.png", H3) for c in ("A", "B", "C")]
    bijna = [_beeld(c, f"https://y.org/{c}", f"https://y.org/{c}.jpg", H4) for c in ("D", "E", "F")]
    echt = [_beeld("G", "https://z.org/g", "https://z.org/g.jpg", H1),
            _beeld("H", "https://w.org/h", "https://w.org/h.jpg", H1_KOPIE)]
    groep = {c: f"cl-{c}" for c in "ABCDEF"} | {"G": "cl-gh", "H": "cl-gh"}
    weg = bi.sjablonen(logo + bijna + echt, groep, 31, min_groepen=3)
    assert weg == set(range(6))


def test_copies_made_while_harvesting_find_their_own_claim():
    """De kopietoets vraagt met een bewerkte versie van een geïndexeerd
    beeld; dan hoort de eigen claim gevonden te worden."""
    beelden = [_beeld("A", "https://a.org/1", "https://a.org/1.jpg", H1, proeven={"jpeg50": H1_KOPIE, "kader": H2}),
               _beeld("C", "https://c.org/1", "https://c.org/1.jpg", H3)]
    uit = bi.kopietoets(beelden, {"A": "cl-1", "C": "cl-2"}, 31)
    assert uit["jpeg50"] == {"goed": 1, "fout": 0, "niets": 0}
    assert uit["kader"] == {"goed": 0, "fout": 0, "niets": 1}


def test_an_image_outside_the_index_that_lands_on_a_claim_is_a_false_positive():
    beelden = [_beeld("A", "https://a.org/1", "https://a.org/1.jpg", H1)]
    assert bi.valse_treffers([bytes.fromhex(H1_KOPIE), bytes.fromhex(H2)], beelden, 31) == 1


def test_the_pilot_takes_clusters_with_two_hosts_and_the_m4fc_articles():
    conn = connect(":memory:")
    init_schema(conn)
    for cid, cluster, url in (("A", "cl-1", "https://a.org/1"), ("B", "cl-1", "https://b.org/1"),
                              ("C", "cl-2", "https://a.org/2"), ("D", "cl-2", "https://a.org/3"),
                              ("E", None, "https://e.org/1")):
        conn.execute("INSERT INTO claim (claim_id, canonical_text, language, cluster_id) VALUES (?, ?, 'en', ?)",
                     (cid, f"claim {cid}", cluster))
        conn.execute("INSERT INTO factcheck (claim_id, publisher, verdict_normalized, verdict_original, url,"
                     " review_date, language) VALUES (?, 'x', 'onwaar', 'False', ?, '2024-01-01', 'en')", (cid, url))
    artikelen = bi.pilotartikelen(conn, {"https://e.org/1"})
    assert sorted(artikelen) == [("A", "https://a.org/1"), ("B", "https://b.org/1"), ("E", "https://e.org/1")]


def test_a_path_that_robots_txt_forbids_is_not_fetched():
    robots = urllib.robotparser.RobotFileParser()
    robots.parse(["User-agent: *", "Disallow: /prive/"])
    assert bi.mag(robots, "https://a.org/artikel/1")
    assert not bi.mag(robots, "https://a.org/prive/1")
    assert bi.mag(None, "https://a.org/prive/1")       # geen robots.txt: geen verbod


def test_a_tiny_image_never_enters_the_index():
    """De HTML zegt niet altijd hoe groot een beeld is; een pictogram van 64
    pixels is geen virale foto, wat zijn hash ook zegt."""
    regels = [{"claim_id": "A", "url": "https://a.org/1", "beelden": [
        {"beeld": "https://a.org/klein.png", "pdq": H1, "kwaliteit": 100, "breedte": 64, "hoogte": 64},
        {"beeld": "https://a.org/groot.jpg", "pdq": H2, "kwaliteit": 100, "breedte": 800, "hoogte": 600},
    ]}]
    assert [b.url for b in bi.beelden_uit_regels(regels)] == ["https://a.org/groot.jpg"]


def test_an_m4fc_article_is_found_despite_a_trailing_slash():
    """M4FC schrijft `…/artikel`, het corpus `…/artikel/`: dat is hetzelfde
    artikel, en er wordt het adres uit het corpus geoogst."""
    conn = connect(":memory:")
    init_schema(conn)
    conn.execute("INSERT INTO claim (claim_id, canonical_text, language) VALUES ('K', 'claim K', 'nl')")
    conn.execute("INSERT INTO factcheck (claim_id, publisher, verdict_normalized, verdict_original, url,"
                 " review_date, language) VALUES ('K', 'Knack', 'onwaar', 'Onwaar',"
                 " 'https://www.knack.be/factcheck/een-artikel/', '2024-01-01', 'nl')")
    assert bi.pilotartikelen(conn, {"https://www.knack.be/factcheck/een-artikel"}) == [
        ("K", "https://www.knack.be/factcheck/een-artikel/")]


def test_a_half_written_line_is_cut_off_before_the_harvest_resumes(tmp_path):
    """Een onderbroken oogst laat hooguit één halve regel achter; zonder
    herstel plakt de volgende regel eraan vast en is het bestand onleesbaar."""
    pad = tmp_path / "regels.jsonl"
    pad.write_text('{"url": "https://a.org/1", "beelden": []}\n{"url": "https://a.o', encoding="utf-8")
    bi.herstel(pad)
    assert pad.read_text(encoding="utf-8") == '{"url": "https://a.org/1", "beelden": []}\n'


def test_house_style_at_one_outlet_is_a_template_from_two_clusters_on():
    """Een auteursfoto of oordeelsmeter staat bij twee claims van dezelfde
    redactie al in twee clusters; een echte virale foto bij twee redacties
    blijft staan."""
    huisstijl = [_beeld("A", "https://p.org/a", "https://p.org/meter.jpg", H3),
                 _beeld("B", "https://p.org/b", "https://p.org/meter.jpg", H3)]
    bijna = [_beeld("C", "https://q.org/c", "https://q.org/c.jpg", H4),
             _beeld("D", "https://q.org/d", "https://q.org/d.jpg", H4)]
    viraal = [_beeld("E", "https://e.org/e", "https://e.org/e.jpg", H1),
              _beeld("F", "https://f.org/f", "https://f.org/f.jpg", H1_KOPIE)]
    groep = {c: f"cl-{c}" for c in "ABCDEF"}
    assert bi.sjablonen(huisstijl + bijna + viraal, groep, 31, min_groepen=3) == {0, 1, 2, 3}


def test_an_article_that_checks_several_claims_gives_its_images_to_none():
    """Een verzamelartikel (een speech, tien beweringen) toont een foto van de
    spreker, niet het virale beeld van één bewering."""
    regels = [{"claim_id": "A", "url": "https://w.org/speech", "beelden": [
                  {"beeld": "https://w.org/1.jpg", "pdq": H1, "kwaliteit": 100, "breedte": 800, "hoogte": 600}]},
              {"claim_id": "B", "url": "https://w.org/speech", "beelden": [
                  {"beeld": "https://w.org/1.jpg", "pdq": H1, "kwaliteit": 100, "breedte": 800, "hoogte": 600}]},
              {"claim_id": "C", "url": "https://c.org/1", "beelden": [
                  {"beeld": "https://c.org/1.jpg", "pdq": H2, "kwaliteit": 100, "breedte": 800, "hoogte": 600}]}]
    groep = {"A": "cl-1", "B": "cl-2", "C": "cl-3"}
    assert bi.verzamelartikelen(regels, groep) == {"https://w.org/speech"}


def test_an_m4fc_image_is_found_under_its_zero_padded_name(tmp_path):
    (tmp_path / "00703.png").write_bytes(b"x")
    assert bi._m4fc_beeld(tmp_path, "703") == tmp_path / "00703.png"
    assert bi._m4fc_beeld(tmp_path, "999") is None
