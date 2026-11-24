"""De woorden zoeken, het beeld bevestigt (PLAN #32.17).

De tekst en een beschrijving van de foto zoeken elk de vijf beste checks; het beeld bevestigt alleen tegen de beelden in
de artikelen van die kandidaten: PDQ binnen 31 bits, of minstens 50 punten over minstens 10% van de vraag. Een vraag
die zelf in het artikel staat en huisstijl tellen niet. Gevonden is alleen een bevestiging in de eigen bewering die als
*zelfde beeld, zelfde bewering* gelezen is; tellen weigert zolang een bevestiging geen label heeft.
"""

import io
import json

import numpy as np
import pytest
from PIL import Image, ImageDraw

from doublecheck import beeldbevestiging as bb
from doublecheck import beeldvraag as bv
from doublecheck.beeldindexmeting import is_beeld


def _blokken(zaad, maat=(640, 480)) -> Image.Image:
    rng = np.random.default_rng(zaad)
    beeld = Image.new("RGB", maat, tuple(int(c) for c in rng.integers(0, 255, 3)))
    teken = ImageDraw.Draw(beeld)
    for _ in range(80):
        x, y = rng.integers(0, maat[0]), rng.integers(0, maat[1])
        teken.rectangle([x, y, x + rng.integers(6, 90), y + rng.integers(6, 90)],
                        fill=tuple(int(c) for c in rng.integers(0, 255, 3)))
    return beeld


def _bytes(beeld: Image.Image, soort="JPEG") -> bytes:
    buf = io.BytesIO()
    beeld.save(buf, soort)
    return buf.getvalue()


def _hash(bits_om: int) -> str:
    """Een PDQ-hash die `bits_om` bits van de nulhash verschilt."""
    getal = (1 << bits_om) - 1
    return f"{getal:064x}"


# --- de sets -------------------------------------------------------------------------------------

def test_the_fresh_claims_come_from_r2s_candidates_up_to_the_date_and_never_from_r2():
    rijen = [(f"c{i:03d}", None, f"https://factly.in/a{i}", "FACTLY", "en",
              "2026-05-01" if i < 150 else "2026-10-30", "Photo shows a flood") for i in range(200)]
    r2 = {"c000", "c001"}
    uit = bb.r3_claims(rijen, r2)
    assert len(uit) == 100 and not ({c["claim_id"] for c in uit} & r2)
    assert all(c["datum"] <= bb.R3_TOT for c in uit)
    assert uit == bb.r3_claims(rijen, r2)


def test_s3_draws_five_hundred_with_its_own_seed():
    werk = [str(i) for i in range(3663)]
    assert len(bb.s3_keuze(werk)) == 500 and bb.s3_keuze(werk) == bb.s3_keuze(list(reversed(werk)))


# --- de kandidaten --------------------------------------------------------------------------------

def test_the_candidates_of_both_keys_are_merged_with_where_they_came_from():
    tekst = [{"claim": "c1", "url": "u1", "gelijkenis": 0.8}, {"claim": "c2", "url": "u2", "gelijkenis": 0.7}]
    beschrijving = [{"claim": "c2", "url": "u2", "gelijkenis": 0.75}, {"claim": "c3", "url": "u3", "gelijkenis": 0.6}]
    uit = bb.kandidaten(tekst, beschrijving, {"c1": "g1", "c2": "g2", "c3": "g1"}.get)
    assert [(k["claim"], k["via"], k["groep"]) for k in uit] == [
        ("c1", ["tekst"], "g1"), ("c2", ["tekst", "beschrijving"], "g2"), ("c3", ["beschrijving"], "g1")]


def _vraag_maken(meta, beeld, tekst="Breaking: the photo shows the flood in the city today", **anders):
    gevraagd = {"beweer": [], "beschrijf": 0}

    def beweer(t):
        gevraagd["beweer"].append(t)
        return [{"bewering": "Photo shows a flood", "zoekvragen": ["flood city"]}], 0.0002

    def beschrijf(_b):
        gevraagd["beschrijf"] += 1
        return {"beschrijving": "Photo shows a flooded street.", "zoekvragen": ["flooded street"]}, 0.0003

    def zoek(t, gehaald):
        return [{"claim": "c-tekst" if "flood in" in t or t.startswith("Breaking") else "c-beeld", "url": "https://a/1",
                 "gelijkenis": 0.7}]
    deps = {"lees": lambda _b: tekst, "beweer": beweer, "beschrijf": beschrijf, "zoek": zoek, "groep": lambda c: c}
    return (*bb.vraag(meta, beeld, **(deps | anders)), gevraagd)


def test_a_short_text_asks_for_no_claims_and_only_the_description_searches():
    regel, _, gevraagd = _vraag_maken({"id": "s1-0", "set": "S1"}, _bytes(_blokken(1)), tekst="kort")
    assert gevraagd["beweer"] == [] and gevraagd["beschrijf"] == 1
    assert [k["via"] for k in regel["kandidaten"]] == [["beschrijving"]]


def test_the_stored_memory_of_n_and_w_is_used_without_reading_again():
    geheugen = [{"claim": "c-oud", "url": "https://b/2", "gelijkenis": 0.8}]
    regel, _, gevraagd = _vraag_maken({"id": "n-1", "set": "N", "geheugen": geheugen}, _bytes(_blokken(2)),
                                      lees=lambda _b: pytest.fail("N en W lezen niet opnieuw"))
    assert gevraagd["beweer"] == []
    assert [(k["claim"], k["via"]) for k in regel["kandidaten"]] == [("c-oud", ["tekst"]), ("c-beeld", ["beschrijving"])]


# --- uitsluiting en huisstijl -----------------------------------------------------------------

def test_a_question_that_sits_in_the_article_itself_never_counts():
    vraag = {"set": "N", "adressen": ["https://www.factly.in/wp-content/uploads//2021/11/x.jpg",
                                      "https://web.archive.org/web/20230525004101/https://factly.in/wp-content/uploads//2021/11/x.jpg"],
             "pdq": [_hash(0)]}
    ver = [_hash(120)] * 4
    assert bb.uitgesloten(vraag, {"beeld": "http://factly.in/wp-content/uploads/2021/11/x.jpg?w=800", "pdq": ver})
    assert bb.uitgesloten({**vraag, "adressen": vraag["adressen"][1:]},
                          {"beeld": "https://factly.in/wp-content/uploads/2021/11/x.jpg", "pdq": ver})
    assert bb.uitgesloten(vraag, {"beeld": "https://cdn.example/y.jpg", "pdq": [_hash(31)] + ver[1:]})
    assert not bb.uitgesloten(vraag, {"beeld": "https://cdn.example/z.jpg", "pdq": [_hash(32)] + ver[1:]})
    # een uitsnede van de vraag in het artikel is geen kopie van de vraag als geheel: die mag blijven
    assert not bb.uitgesloten(vraag, {"beeld": "https://cdn.example/z.jpg", "pdq": ver[:1] + [_hash(0)] * 3})
    # een kopie van het open web staat niet zelf in een factcheckartikel
    assert not bb.uitgesloten({**vraag, "set": "R3"}, {"beeld": vraag["adressen"][0], "pdq": [_hash(0)]})


def test_house_style_at_three_claims_never_counts():
    artikelen = [{"url": "a1", "groepen": ["g1"], "beelden": ["logo", "f1"]},
                 {"url": "a2", "groepen": ["g2"], "beelden": ["logo", "f2"]},
                 {"url": "a3", "groepen": ["g3"], "beelden": ["logo"]},
                 {"url": "a4", "groepen": ["g4"], "beelden": ["f5"]},
                 {"url": "a5", "groepen": ["g4"], "beelden": ["f5"]},
                 {"url": "a6", "groepen": ["g5"], "beelden": ["f5"]}]
    assert bb.huisstijl(artikelen) == {"logo"}


# --- vergelijken ----------------------------------------------------------------------------------

def test_a_copy_in_the_article_is_confirmed_and_another_photo_never():
    foto = _blokken(3)
    regel, punten, _ = _vraag_maken({"id": "r-1", "set": "R3"}, _bytes(foto))
    kandidaat = {"claim": "c1", "groep": "g1", "url": "https://a/1", "via": ["tekst"]}
    kopie = _bytes(foto.resize((560, 420)), "PNG")
    paar = bb.vergelijk(regel, punten, kandidaat, {"beeld": "https://a/1.jpg", **bb.artikelbeeld(kopie)})
    assert bb.bevestigd(paar) and not paar["uitgesloten"]
    ander = bb.vergelijk(regel, punten, kandidaat, {"beeld": "https://a/2.jpg", **bb.artikelbeeld(_bytes(_blokken(4)))})
    assert not bb.bevestigd(ander)


def test_no_image_file_ever_reaches_disk(tmp_path):
    regel, punten, _ = _vraag_maken({"id": "s1-0", "set": "S1"}, _bytes(_blokken(5)))
    bb.schrijf_vraag(tmp_path, regel, punten)
    kandidaat = {"claim": "c1", "groep": "g1", "url": "https://a/1", "via": ["tekst"]}
    paar = bb.vergelijk(regel, punten, kandidaat, {"beeld": "https://a/1.jpg", **bb.artikelbeeld(_bytes(_blokken(6)))})
    bb.schrijf(tmp_path / "paren.jsonl", [paar])
    json.dumps(regel), json.dumps(paar)
    assert "tekst" not in regel, "de gelezen tekst van een beeld blijft in het geheugen"
    bestanden = [p for p in tmp_path.rglob("*") if p.is_file()]
    assert bestanden and not any(is_beeld(p.read_bytes()) for p in bestanden)
    assert not any(p.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp", ".gif") for p in bestanden)
    assert bv.puntvergelijking(punten, bb.lees_punten(tmp_path, regel))[0] > 0


def test_cleaning_erases_the_points_of_the_questions_and_keeps_the_rows(tmp_path):
    regel, punten, _ = _vraag_maken({"id": "s1-0", "set": "S1"}, _bytes(_blokken(7)))
    bb.schrijf_vraag(tmp_path, regel, punten)
    bb.opruimen(tmp_path)
    assert not list(tmp_path.rglob("*.npz")) and (tmp_path / "vragen.jsonl").exists()


# --- tellen -------------------------------------------------------------------------------------

def _v(id_, set_, groepen=(), claim=None):
    return {"id": id_, "set": set_, "groepen": list(groepen), "claim_id": claim}


def _p(id_, set_, groep, beeld, *, pdq=None, punten=0, dekking=0.0, via=("tekst",), uitgesloten=False,
       punten500=None, dekking500=None):
    return {"vraag": id_, "set": set_, "groep": groep, "beeld": beeld, "artikel": "https://a/" + groep,
            "claim": groep, "via": list(via), "pdq": pdq, "uitgesloten": uitgesloten, "punten": punten,
            "dekking": dekking, "punten500": punten if punten500 is None else punten500,
            "dekking500": dekking if dekking500 is None else dekking500}


AANTALLEN = {"R3": 100, "R2": 100}


def test_counting_refuses_while_a_confirmation_has_no_label():
    vragen, paren = [_v("n1", "N", ["g1"])], [_p("n1", "N", "g1", "b1", punten=80, dekking=0.5)]
    with pytest.raises(bb.Weigering, match="N\\|n1\\|b1"):
        bb.telling(vragen, paren, {}, set(), AANTALLEN)
    assert bb.telling(vragen, paren, {"N|n1|b1": bb.GEVONDEN}, set(), AANTALLEN)["hoofd"]["N"]["gevonden"] == 1


def test_an_excluded_or_house_style_image_is_never_read_nor_counted():
    vragen = [_v("n1", "N", ["g1"])]
    paren = [_p("n1", "N", "g1", "b1", punten=80, dekking=0.5, uitgesloten=True), _p("n1", "N", "g1", "logo", pdq=3)]
    assert bb.te_lezen(vragen, paren, {}, {"logo"}) == []
    assert bb.telling(vragen, paren, {}, {"logo"}, AANTALLEN)["hoofd"]["N"]["gevonden"] == 0


def test_found_counts_only_in_the_own_claim_or_cluster_and_elsewhere_apart():
    vragen, paren = [_v("n1", "N", ["g1"])], [_p("n1", "N", "g9", "b1", punten=80, dekking=0.5)]
    d = bb.telling(vragen, paren, {"N|n1|b1": bb.GEVONDEN}, set(), AANTALLEN)["hoofd"]["N"]
    assert d["gevonden"] == 0 and d["gevonden elders"] == 1


def test_what_the_description_adds_is_counted_apart():
    vragen = [_v(f"n{i}", "N", [f"g{i}"]) for i in range(3)]
    paren = [_p("n0", "N", "g0", "b0", punten=80, dekking=0.5, via=["tekst"]),
             _p("n1", "N", "g1", "b1", punten=80, dekking=0.5, via=["beschrijving"]),
             _p("n2", "N", "g2", "b2", pdq=10, via=["tekst", "beschrijving"])]
    labels = {f"N|n{i}|b{i}": bb.GEVONDEN for i in range(3)}
    d = bb.telling(vragen, paren, labels, set(), AANTALLEN)["hoofd"]["N"]
    assert (d["gevonden"], d["via tekst"], d["via beschrijving"], d["beschrijving voegt toe"]) == (3, 2, 2, 1)


def test_a_fresh_claim_counts_once_and_a_claim_without_copies_counts_as_missed():
    vragen = [_v("r1#0", "R3", ["g1"], "c1"), _v("r1#1", "R3", ["g1"], "c1")]
    paren = [_p("r1#0", "R3", "g1", "b1", pdq=4), _p("r1#1", "R3", "g1", "b1", pdq=6)]
    labels = {"R3|r1#0|b1": bb.GEVONDEN, "R3|r1#1|b1": bb.GEVONDEN}
    d = bb.telling(vragen, paren, labels, set(), AANTALLEN)["hoofd"]["R3"]
    assert (d["claims"], d["vragen"], d["gevonden"]) == (100, 2, 1)


def _stand(n_gevonden=20, r3_gevonden=30, w_vals=0, s_vals=1):
    """58 screenshots, 100 verse claims met elk 2 kopieën tot 135 kopieën, 60 ware foto's en 1.450 stiltebeelden."""
    vragen = [_v(f"n{i}", "N", [f"gn{i}"]) for i in range(58)]
    vragen += [_v(f"r{c}#{k}", "R3", [f"gr{c}"], f"c{c}") for c in range(68) for k in range(2)][:135]
    vragen += [_v(f"w{i}", "W") for i in range(60)]
    vragen += [_v(f"s{i}", ("S1", "S2", "S3", "S4")[i % 4]) for i in range(1450)]
    paren, labels = [], {}

    def zet(id_, set_, groep, label):
        paren.append(_p(id_, set_, groep, "b-" + id_, punten=90, dekking=0.4))
        labels[f"{set_}|{id_}|b-{id_}"] = label
    for i in range(n_gevonden):
        zet(f"n{i}", "N", f"gn{i}", bb.GEVONDEN)
    for c in range(r3_gevonden):
        zet(f"r{c}#0", "R3", f"gr{c}", bb.GEVONDEN)
    for i in range(w_vals):
        zet(f"w{i}", "W", "gx", bb.VALS)
    zet("w59", "W", "gy", bb.ANDERE)
    for i in range(s_vals):
        zet(f"s{i}", ("S1", "S2", "S3", "S4")[i % 4], "gz", bb.VALS)
    return vragen, paren, labels


def test_the_requirements_count_as_registered():
    uit = bb.telling(*_stand(), set(), AANTALLEN)
    assert all(uit["eisen"].values()) and uit["gehaald"], uit["eisen"]
    assert uit["hoofd"]["samen"]["vragen"] == 58 + 135 + 60 + 1450
    assert not bb.telling(*_stand(n_gevonden=19), set(), AANTALLEN)["gehaald"]
    assert not bb.telling(*_stand(r3_gevonden=29), set(), AANTALLEN)["gehaald"]
    assert not bb.telling(*_stand(w_vals=1, s_vals=0), set(), AANTALLEN)["gehaald"]
    assert not bb.telling(*_stand(s_vals=2), set(), AANTALLEN)["gehaald"]
    # zelfde beeld met een andere bewering is geen vals, maar wordt apart gemeld
    assert uit["hoofd"]["W"]["andere bewering"] == 1 and uit["hoofd"]["W"]["vals"] == 0


def test_the_exploratory_variants_never_refuse_and_count_what_is_unread():
    vragen, paren = [_v("n1", "N", ["g1"])], [_p("n1", "N", "g1", "b1", punten=30, dekking=0.5)]
    uit = bb.telling(vragen, paren, {}, set(), AANTALLEN)
    assert uit["hoofd"]["N"]["gevonden"] == 0
    assert uit["verkennend"]["20 punten"]["N"]["ongelezen"] == 1
    assert uit["verkennend"]["100 punten"]["N"]["ongelezen"] == 0


def test_the_cost_guard_stops_before_the_limit():
    assert not bb.over_budget([{"kosten": 1.0}], 100)
    assert bb.over_budget([{"kosten": 2.6}], 300)


def test_an_address_in_another_script_finds_its_percent_encoded_wayback_copy():
    gewoon = "https://cdn4.fatabyyano.net/wp-content/uploads/2021/12/18213133/ادعاء-بيض-الأرانب.jpg"
    wayback = ("https://web.archive.org/web/20220404045630/https://cdn4.fatabyyano.net/wp-content/uploads/2021/12/"
               "18213133/%D8%A7%D8%AF%D8%B9%D8%A7%D8%A1-%D8%A8%D9%8A%D8%B6-%D8%A7%D9%84%D8%A3%D8%B1%D8%A7%D9%86%D8%A8.jpg")
    assert bb._adres(gewoon) == bb._adres(wayback)
    assert bb.uitgesloten({"set": "S3", "adressen": [wayback], "pdq": [_hash(0)]},
                          {"beeld": gewoon, "pdq": [_hash(200)] * 4})


def test_the_fixed_comparison_replaces_only_the_recomputed_pairs_and_never_the_decision():
    """§189, verkennend: de paren met minstens 20 punten opnieuw vergeleken zonder ingeklapte vorm. Het telt naast de
    regel zoals hij draaide, en de eisen blijven op die regel."""
    vragen = [_v("s1", "S1"), _v("n1", "N", ["g1"])]
    paren = [_p("s1", "S1", "gx", "klont", punten=70, dekking=0.5), _p("n1", "N", "g1", "echt", punten=200, dekking=0.4)]
    opnieuw = {"S1|s1|klont": {"punten": 0, "dekking": 0.0, "punten500": 0, "dekking500": 0.0}}
    na = bb.herberekend(paren, opnieuw)
    assert (na[0]["punten"], na[1]["punten"]) == (0, 200) and paren[0]["punten"] == 70
    labels = {"S1|s1|klont": bb.VALS, "N|n1|echt": bb.GEVONDEN}
    uit = bb.telling(vragen, paren, labels, set(), AANTALLEN, opnieuw)
    assert uit["hoofd"]["S1"]["vals"] == 1, "de eisen tellen op de regel zoals hij draaide"
    assert uit["na de reparatie"]["hoofd"]["S1"]["vals"] == 0 and uit["na de reparatie"]["hoofd"]["N"]["gevonden"] == 1
