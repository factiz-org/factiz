"""De beeldindex meten op echte screenshots (PLAN #32.15).

De sets liggen vast vóór het ophalen, een vraag van R1 vindt nooit de eigen redactie, een kopie van een factchecker telt
niet mee in R2, en de telling weigert zolang een treffer buiten de eigen bewering geen label heeft. De oogst zet geen
beeld op schijf (DR3, B35).
"""

import io
import json

import numpy as np
import pytest
from PIL import Image, ImageDraw

from doublecheck import beeldindex as bi
from doublecheck import beeldindexmeting as bm
from doublecheck import beeldvraag as bv
from doublecheck.kadermeting import _kader_b


def _nep(beelden):
    uit = []
    for b in beelden:
        klein = np.asarray(b.convert("RGB").resize((8, 16)), dtype=np.float32).ravel()
        v = klein - klein.mean()
        uit.append(v / (np.linalg.norm(v) or 1.0))
    return {"cls": np.vstack(uit), "vlakjes": np.vstack(uit)}


def _foto(zaad=1, maat=(640, 480)) -> Image.Image:
    rng = np.random.default_rng(zaad)
    beeld = Image.new("RGB", maat, tuple(int(c) for c in rng.integers(0, 255, 3)))
    teken = ImageDraw.Draw(beeld)
    for _ in range(40):
        x, y = rng.integers(0, maat[0]), rng.integers(0, maat[1])
        teken.ellipse([x, y, x + rng.integers(20, 160), y + rng.integers(20, 160)],
                      fill=tuple(int(c) for c in rng.integers(0, 255, 3)))
    return beeld


def _jpeg(beeld) -> bytes:
    buf = io.BytesIO()
    beeld.save(buf, "JPEG", quality=90)
    return buf.getvalue()


# --- de sets ---------------------------------------------------------------------------

def test_a_claim_counts_for_r1_only_with_two_newsrooms_we_can_fetch():
    rijen = [("c1", "g1", "https://factly.in/a"), ("c2", "g1", "https://www.politifact.com/b"),
             ("c3", "g2", "https://factly.in/c"), ("c4", "g2", "https://youturn.in/d"),
             ("c5", None, "https://factly.in/e"), ("c5", None, "https://www.factcheck.org/f")]
    assert bm.r1_groepen(rijen) == {"c5": ["factcheck.org", "factly.in"], "g1": ["factly.in", "politifact.com"]}


def test_the_fresh_image_claims_are_drawn_the_same_way_every_time():
    rijen = [(f"c{i:03d}", None, f"https://factly.in/{i}", "FACTLY", "en", "2026-05-01", f"Photo shows thing {i}")
             for i in range(150)]
    rijen += [("x1", None, "https://factly.in/x1", "FACTLY", "en", "2026-03-31", "Photo shows an old thing"),
              ("x2", None, "https://factly.in/x2", "FACTLY", "te", "2026-05-01", "Photo shows thing"),
              ("x3", None, "https://factly.in/x3", "FACTLY", "en", "2026-05-01", "The minister said so"),
              ("x4", None, "https://youturn.in/x4", "YouTurn", "en", "2026-05-01", "Video shows thing")]
    eerste, tweede = bm.r2_claims(rijen), bm.r2_claims(list(reversed(rijen)))
    assert len(eerste) == 100 and eerste == tweede
    assert not {c["claim_id"] for c in eerste} & {"x1", "x2", "x3", "x4"}


def test_each_article_is_fetched_once_and_excluded_hosts_never():
    rijen = [("c1", "g1", "https://factly.in/a"), ("c2", "g1", "https://factly.in/a"),
             ("c3", "g2", "https://euvsdisinfo.eu/b"), ("c4", None, "https://factly.in/oud")]
    lijst = bm.artikelen(rijen, {"https://factly.in/oud", "https://euvsdisinfo.eu/b"}, {"g1": ["x", "y"]}, [])
    assert lijst == [("c1", "https://factly.in/a"), ("c4", "https://factly.in/oud")]


# --- de index van de meting ------------------------------------------------------------------

def _regel(claim, url, *beelden, status=200):
    return {"claim_id": claim, "url": url, "status": status,
            "beelden": [{"beeld": f"{url}/{i}.jpg", **bv.indexkenmerken(b, vectoren=_nep)} for i, b in enumerate(beelden)]}


def test_a_collection_article_small_images_and_house_style_stay_out_of_the_index():
    logo = _foto(99)
    regels = [_regel("c1", "https://a.org/1", _foto(1), logo), _regel("c2", "https://a.org/2", _foto(2), logo),
              _regel("c3", "https://b.org/3", _foto(3), logo), _regel("c4", "https://b.org/4", _foto(4)),
              _regel("c5", "https://c.org/5", _foto(5, (150, 150))), _regel("c6", "https://c.org/6", _foto(6), status=404)]
    claims_van = {"https://b.org/4": ["c4", "c1"]}
    groep = {f"c{i}": f"g{i}" for i in range(1, 7)}
    index, info, tel = bm.index_uit_regels(regels, claims_van, groep)
    assert {b["claim_id"] for b in index.beelden} == {"c1", "c2", "c3"}
    assert tel["verzamelartikel"] == 1 and tel["te klein"] == 1 and tel["huisstijl"] == 3
    assert list(info["groep"]) == ["g1", "g2", "g3"]


def test_a_query_of_r1_never_finds_its_own_newsroom():
    foto = _foto(7)
    regels = [_regel("c1", "https://a.org/1", foto), _regel("c2", "https://b.org/2", _kader_b(foto)),
              _regel("c3", "https://a.org/3", _foto(8))]
    groep = {"c1": "g", "c2": "g", "c3": "h"}
    index, info, _ = bm.index_uit_regels(regels, {}, groep)

    def vraag(i):
        weg = (info["host"] == info["host"][i]) & (info["groep"] == "g")
        return bm.treffer(index, bv.vraag_uit_index(info["kenmerken"][i]),
                          {"set": "R1", "vraag": "q", "vorm": "origineel", "groep": "g"}, np.asarray(weg))

    eigen = vraag(0)
    assert eigen["pdq"][2] != "https://a.org/1" and eigen["dino_gebied"][2] != "https://a.org/1"
    # het screenshot van b.org vindt de foto van a.org via zijn beeldgebied; de kale foto het screenshot niet
    t = vraag(1)
    assert t["pdq"][2] == "https://a.org/1" and t["pdq"][3] <= bm.DREMPEL_PDQ
    assert bm.oordeel(t, bm.keuze(t, "combinatie"), {}) == bm.GEVONDEN


def test_each_variant_takes_its_own_route():
    t = {"pdq": ["p", "g1", "a", 20], "dino": ["d", "g2", "b", 0.99], "dino_gebied": ["d", "g2", "b", 0.99]}
    assert bm.keuze(t, "pdq")[0] == "p" and bm.keuze(t, "dino")[0] == "d" and bm.keuze(t, "combinatie")[0] == "p"
    t["pdq"][3] = 40
    assert bm.keuze(t, "pdq") is None and bm.keuze(t, "combinatie")[0] == "d"
    t["dino_gebied"][3] = 0.95
    assert bm.keuze(t, "combinatie") is None


# --- de kopieën van R2 ---------------------------------------------------------------------

def _vision(paginas=(), vol=(), deels=()):
    return {"responses": [{"webDetection": {"pagesWithMatchingImages": list(paginas),
                                            "fullMatchingImages": [{"url": u} for u in vol],
                                            "partialMatchingImages": [{"url": u} for u in deels]}}]}


def test_a_copy_from_a_fact_checker_or_the_own_article_never_counts():
    antwoord = _vision(
        paginas=[{"url": "https://www.facebook.com/post/1", "fullMatchingImages": [{"url": "https://scontent.fb/1.jpg"}]},
                 {"url": "https://www.boomlive.in/fact-check/x", "fullMatchingImages": [{"url": "https://cdn.x/2.jpg"}]}],
        vol=["https://i0.wp.com/factly.in/wp-content/3.jpg", "https://factly.in/4.jpg", "https://pbs.twimg.com/5.jpg"],
        deels=["https://pbs.twimg.com/5.jpg", "https://www.politifact.com/6.jpg", "https://news.example/7.jpg"])
    uit = bm.kopieen([antwoord], {"politifact.com", "factly.in"}, "factly.in")
    assert [(k["beeld"], k["soort"]) for k in uit] == [
        ("https://scontent.fb/1.jpg", "vol"), ("https://pbs.twimg.com/5.jpg", "vol"),
        ("https://news.example/7.jpg", "deels")]
    assert uit[0]["pagina"] == "https://www.facebook.com/post/1"


# --- S1, S2, S4 ------------------------------------------------------------------------------

def test_a_day_of_current_events_gives_its_articles_once_without_files_or_categories():
    tekst = ("* [[2026 Gaza war|Gaza]]: [[Israel Defense Forces|IDF]] strikes [[Gaza City#North]]. [[File:x.jpg]]\n"
             "* [[Category:2026]] [[Gaza City]] [[w:nl:Gaza]] [[Kamala_Harris]]")
    assert bm.portal_artikelen(tekst) == ["2026 Gaza war", "Israel Defense Forces", "Gaza City", "Kamala Harris"]


def test_only_a_jpeg_of_800_pixels_wide_counts_as_a_photo():
    assert bm.foto_van_commons({"mime": "image/jpeg", "width": 1200, "thumburl": "https://u/x.jpg"})
    assert not bm.foto_van_commons({"mime": "image/png", "width": 1200, "thumburl": "https://u/x.png"})
    assert not bm.foto_van_commons({"mime": "image/jpeg", "width": 640, "thumburl": "https://u/x.jpg"})


def test_an_imgflip_template_is_read_as_its_full_image():
    html = ('<img class="shadow" style="width:91px;height:150px" alt="say the line bart! simpsons Meme Template" '
            'src="//i.imgflip.com/4/176h0.jpg">')
    assert bm.imgflip_sjablonen(html) == [{"naam": "say the line bart! simpsons", "url": "https://i.imgflip.com/176h0.jpg"}]
    assert bm.sleutel_imgflip("https://i.imgflip.com/176h0.jpg") == "176h0"


# --- tellen ------------------------------------------------------------------------------------

def _t(set_, vraag, groep=None, pdq=None, dino=None, vorm="origineel", soort=None):
    return {"set": set_, "vraag": vraag, "vorm": vorm, "groep": groep, "soort": soort, "pdq": pdq, "dino": dino,
            "dino_gebied": dino}


TREFFERS = [
    _t("R1", "a1", "g1", pdq=["x1", "g1", "a", 10]),
    _t("R1", "a2", "g2", dino=["x2", "g2", "b", 0.97]),
    _t("R1", "a3", "g3", dino=["x9", "g9", "c", 0.96]),
    _t("R2", "k1", "g4", dino=["x4", "g4", "d", 0.99], soort="deels"),
    _t("R2", "k2", "g5", pdq=["x5", "g5", "e", 5], soort="vol"),
    _t("S1", "s1", dino=["x6", "g6", "f", 0.96]),
    _t("S1", "s2", pdq=["x7", "g7", "g", 50], dino=["x7", "g7", "g", 0.5]),
    _t("S4", "m1", dino=["x8", "g8", "h", 0.98]),
]


def test_counting_refuses_while_a_hit_outside_its_own_claim_has_no_label():
    with pytest.raises(bm.Weigering, match="R1\\|a3"):
        bm.telling(TREFFERS, {"S1|s1|origineel|x6": bm.VALS}, {"R1": 3, "R2": 2})
    assert {bm.labelsleutel(t, k) for t, k in bm.te_lezen(TREFFERS, {})} == {"R1|a3|origineel|x9", "S1|s1|origineel|x6"}


def test_a_same_claim_label_counts_as_found_and_a_meme_is_false_by_construction():
    labels = {"R1|a3|origineel|x9": bm.GEVONDEN, "S1|s1|origineel|x6": bm.VALS}
    uit = bm.telling(TREFFERS, labels, {"R1": 3, "R2": 2})
    assert uit["pdq"]["R1"]["gevonden"] == 1 and uit["combinatie"]["R1"]["gevonden"] == 3
    assert uit["combinatie"]["R2"]["gevonden"] == 2 and uit["combinatie"]["R2"]["via gedeeltelijke kopie"] == 1
    assert uit["combinatie"]["S1"] | {"bovengrens": 0} == {"vragen": 2, "vals": 1, "zelfde beeld": 0, "bovengrens": 0}
    assert uit["combinatie"]["S4"]["vals"] == 1 and uit["pdq"]["S4"]["vals"] == 0


def test_r1_finds_a_claim_only_at_another_newsroom_even_when_the_same_image_sits_in_another_cluster():
    eigen = {**_t("R1", "https://f.org/1 x", "g1", dino=["x1", "g2", "https://f.org/2", 0.97]), "host": "f.org"}
    ander = {**_t("R1", "https://f.org/3 x", "g3", dino=["x2", "g4", "https://h.org/4", 0.97]), "host": "f.org"}
    labels = {bm.labelsleutel(eigen, eigen["dino"]): bm.GEVONDEN, bm.labelsleutel(ander, ander["dino"]): bm.GEVONDEN}
    assert bm.telling([eigen, ander], labels, {"R1": 2})["combinatie"]["R1"]["gevonden"] == 1


def test_the_decision_rule_needs_all_three():
    def uitslag(r2, r1_comb, r1_pdq, vals, vragen, memes=0):
        d = lambda r1: {"R1": {"gevonden": r1}, "R2": {"gevonden": r2},  # noqa: E731
                        "S1-S3": {"vals": vals, "vragen": vragen}, "S4": {"vals": memes, "vragen": 900}}
        return {"combinatie": d(r1_comb), "pdq": d(r1_pdq)}
    assert bm.beslisregel(uitslag(50, 30, 10, 8, 8000))["gehaald"]
    assert not bm.beslisregel(uitslag(49, 30, 10, 0, 8000))["gehaald"]
    assert not bm.beslisregel(uitslag(60, 29, 10, 0, 8000))["gehaald"]
    assert not bm.beslisregel(uitslag(60, 30, 10, 9, 8000))["gehaald"]
    assert bm.beslisregel(uitslag(60, 30, 10, 0, 8000, memes=46))["S4 boven 5% (tekstregel mee in stap 5)"]


def test_an_unknown_label_is_refused(tmp_path, monkeypatch):
    pad = tmp_path / "labels.json"
    pad.write_text(json.dumps({"labels": {"S1|s|origineel|x": "misschien"}}), encoding="utf-8")
    monkeypatch.setattr(bm, "LABELS", pad)
    with pytest.raises(bm.Weigering, match="onbekende labels"):
        bm.lees_labels()


# --- de oogst --------------------------------------------------------------------------------------

class _Antwoord:
    def __init__(self, url, status, inhoud=b"", tekst=""):
        self.url, self.status_code, self.content, self.text = url, status, inhoud, tekst


def _nep_web(paginas: dict, beelden: dict, status: dict):
    class Web:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def get(self, url):
            if url.endswith("robots.txt"):
                return _Antwoord(url, 404)
            if url in paginas:
                return _Antwoord(url, status.get(url, 200), tekst=paginas[url])
            return _Antwoord(url, 200, inhoud=beelden[url])
    return Web


def _pagina(*beelden):
    return ('<html><head><meta property="og:image" content="%s"></head><body><div class="entry-content">%s</div>'
            '</body></html>' % (beelden[0], "".join(f'<img src="{b}">' for b in beelden[1:])))


def test_the_harvest_leaves_only_features_on_disk_never_an_image(tmp_path, monkeypatch):
    import httpx

    beelden = {f"https://f.org/{i}.jpg": _jpeg(_kader_b(_foto(i)) if i == 2 else _foto(i)) for i in range(1, 4)}
    paginas = {"https://f.org/artikel": _pagina(*beelden)}
    monkeypatch.setattr(httpx, "Client", _nep_web(paginas, beelden, {}))
    teller = bi.oogst(tmp_path, [("c1", "https://f.org/artikel")], "pdq-256-v1+dino", pauze=0,
                      verwerk=lambda inhoud: bv.indexkenmerken(inhoud, vectoren=_nep))
    assert teller["beelden"] == 3
    assert sorted(p.name for p in tmp_path.iterdir()) == ["regels.jsonl"]
    inhoud = (tmp_path / "regels.jsonl").read_bytes()
    assert b"\xff\xd8\xff" not in inhoud and b"/9j/" not in inhoud and len(inhoud) < 3 * 2_500
    regel = json.loads(inhoud)
    assert regel["beelden"][1]["gebied"] is not None and regel["beelden"][0]["gebied"] is None


def test_a_rate_limited_article_is_tried_again_when_the_harvest_resumes(tmp_path, monkeypatch):
    import httpx

    beelden = {"https://f.org/1.jpg": _jpeg(_foto(1))}
    paginas = {"https://f.org/artikel": _pagina(*beelden)}
    monkeypatch.setattr(httpx, "Client", _nep_web(paginas, beelden, {"https://f.org/artikel": 429}))
    bi.oogst(tmp_path, [("c1", "https://f.org/artikel")], "v", pauze=0, wacht_bij_limiet=0,
             verwerk=lambda inhoud: bv.indexkenmerken(inhoud, vectoren=_nep))
    monkeypatch.setattr(httpx, "Client", _nep_web(paginas, beelden, {}))
    bi.oogst(tmp_path, [("c1", "https://f.org/artikel")], "v", pauze=0,
             verwerk=lambda inhoud: bv.indexkenmerken(inhoud, vectoren=_nep))
    regels = bi._lees(tmp_path)
    assert [r["status"] for r in regels] == [429, 200]
    assert len(bi.laatste(regels)) == 1 and bi.laatste(regels)[0]["beelden"]


def test_the_original_and_the_framed_query_on_the_same_image_are_read_as_one_pair():
    t1 = _t("S1", "s1", dino=["x6", "g6", "f", 0.96])
    t2 = _t("S1", "s1", dino=["x6", "g6", "f", 0.97], vorm="kader_b")
    t3 = _t("S1", "s1", dino=["x7", "g7", "f", 0.97], vorm="kader_b")
    lijst = bm.paren(bm.te_lezen([t1, t2, t3], {}))
    assert [p["sleutels"] for p in lijst] == [["S1|s1|origineel|x6", "S1|s1|kader_b|x6"], ["S1|s1|kader_b|x7"]]


def test_a_panel_harvest_replaces_an_article_only_when_it_came_in():
    oud = [{"url": "u1", "status": 200, "beelden": ["oud1"]}, {"url": "u2", "status": 200, "beelden": ["oud2"]}]
    nieuw = [{"url": "u1", "status": 200, "beelden": ["nieuw1"]}, {"url": "u2", "status": "fout", "beelden": []}]
    from doublecheck.beeldindex import laatste
    uit = {r["url"]: r["beelden"] for r in laatste(bm.met_panelen(oud, nieuw))}
    assert uit == {"u1": ["nieuw1"], "u2": ["oud2"]}


def test_the_panel_trial_needs_fifty_fresh_claims():
    assert bm.beslisregel_panelen({"combinatie": {"R2": {"gevonden": 50}}})["gehaald"]
    assert not bm.beslisregel_panelen({"combinatie": {"R2": {"gevonden": 49}}})["gehaald"]


# --- de puntenproef (#32.15 stap 2d) ------------------------------------------------------------

def _foto_p(zaad, maat=(640, 480)):
    import numpy as np
    from PIL import Image, ImageDraw
    rng = np.random.default_rng(zaad)
    beeld = Image.new("RGB", maat, tuple(int(c) for c in rng.integers(0, 255, 3)))
    teken = ImageDraw.Draw(beeld)
    for _ in range(60):
        x, y = rng.integers(0, maat[0]), rng.integers(0, maat[1])
        teken.rectangle([x, y, x + rng.integers(10, 120), y + rng.integers(10, 120)],
                        fill=tuple(int(c) for c in rng.integers(0, 255, 3)))
    return beeld


def test_a_framed_and_stamped_copy_matches_its_photo_by_points():
    from PIL import ImageDraw
    from doublecheck.kadermeting import _kader_b
    foto = _foto_p(1)
    kopie = _kader_b(foto)
    ImageDraw.Draw(kopie).ellipse([40, 40, 200, 200], outline=(220, 0, 0), width=12)
    n, dekking = bm.puntvergelijking(bm.puntkenmerken(kopie), bm.puntkenmerken(foto))
    assert bm.punttreffer(n, dekking)


def test_a_photo_inside_a_collage_matches_by_points_and_an_unrelated_one_never():
    from PIL import Image
    foto = _foto_p(2)
    collage = Image.new("RGB", (1300, 520), (255, 255, 255))
    collage.paste(_foto_p(3), (10, 20))
    collage.paste(foto, (650, 20))
    index = bm.puntkenmerken(collage)
    assert bm.punttreffer(*bm.puntvergelijking(bm.puntkenmerken(foto), index))
    assert not bm.punttreffer(*bm.puntvergelijking(bm.puntkenmerken(_foto_p(4)), index))


def test_a_shared_app_bar_alone_is_never_a_match():
    from PIL import Image
    balk = _foto_p(5, (640, 30))

    def post(zaad):
        uit = Image.new("RGB", (640, 640), (255, 255, 255))
        uit.paste(balk, (0, 0))
        uit.paste(_foto_p(zaad, (640, 600)), (0, 40))
        return uit
    n, dekking = bm.puntvergelijking(bm.puntkenmerken(post(6)), bm.puntkenmerken(post(7)))
    assert n >= bm.PUNTEN_MIN and not bm.punttreffer(n, dekking), (n, dekking)


def _p(vraag, claim, groep, beste, soort="deels"):
    return {"set": "R2", "vraag": vraag, "vorm": "origineel", "claim_id": claim, "groep": groep, "soort": soort,
            "beste": beste}


PUNTREGELS = [
    _p("k1", "c1", "g1", ["x1", "g1", "a", 80, 0.5]),
    _p("k2", "c1", "g1", None),
    _p("k3", "c2", "g2", ["x9", "g9", "b", 40, 0.3]),
    _p("k4", "c3", "g3", None),
]


def test_the_point_trial_counts_a_claim_once_and_refuses_an_unread_hit_elsewhere():
    with pytest.raises(bm.Weigering, match="R2\\|k3"):
        bm.punt_telling(PUNTREGELS, {})
    uit = bm.punt_telling(PUNTREGELS, {"R2|k3|origineel|x9": bm.VALS})
    assert uit["gevonden"] == 1 and uit["vals"] == 1 and uit["n"] == 100 and not uit["gehaald"]
    uit = bm.punt_telling(PUNTREGELS, {"R2|k3|origineel|x9": bm.GEVONDEN})
    assert uit["gevonden"] == 2 and uit["via gedeeltelijke kopie"] == 2
