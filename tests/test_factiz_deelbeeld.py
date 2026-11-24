"""Het deelplaatje per factcheck (PLAN #34.2aq, SPECS E9.S23): de bewering en het oordeel in woorden, met de band van het
thema erboven; getekend als iemand het vraagt, daarna bewaard, met de versie van de uitgave in het adres."""

import io
import re
from pathlib import Path

import pytest
from PIL import Image
from starlette.testclient import TestClient

from doublecheck import publiceren as pb
from factiz_site import app as fa
from factiz_site import deelbeeld as dl
from tests.test_factiz_dossiers import INLEIDING, NAAM, _dossier
from tests.test_factiz_themas import LANDEN, THEMAS
from tests.test_publiceren import REGISTER, _check, _claim, _lab

WORTEL = Path(__file__).resolve().parent.parent
HINDI = "ज़ेलेंस्की ने फ्लोरिडा में एक विला खरीदा"
PERZISCHE_REDACTIE = "فکت‌نامه"
# een schrift zonder lettertype op het plaatje (Birmaans; Noto Sans per schrift dekt het hier niet, #34.2as)
BIRMAANS = "ဇီလန်စကီး အိမ်ဝယ်ခဲ့သည်"
BIRMAANSE_REDACTIE = "မြန်မာ အချက်စစ်"


@pytest.fixture(scope="module")
def bestand(tmp_path_factory):
    map_ = tmp_path_factory.mktemp("deelbeeld")
    lab = _lab(map_)
    n = {"villa": _claim(lab, 1, "Zelensky bought a villa in Florida"),
         "hindi": _claim(lab, 2, HINDI, taal="hi"),
         "hindi_en": _claim(lab, 3, HINDI + " और एक नौका", taal="hi"),
         "lang": _claim(lab, 4, " ".join(["Een heel lange bewering over vaccins en chips die maar doorgaat"] * 6), taal="nl"),
         "perzisch": _claim(lab, 5, "زلنسکی ویلا خرید", taal="fa"),
         "birmaans": _claim(lab, 6, BIRMAANS, taal="my")}
    _check(lab, n["villa"], "https://snopes.com/villa", datum="2024-03-05")
    _check(lab, n["hindi"], "https://factcheck.afp.com/hindi", datum="2023-02-01", taal="hi")
    _check(lab, n["hindi_en"], "https://factcheck.afp.com/hindi-en", datum="2023-02-02", taal="hi")
    _check(lab, n["lang"], "https://maldita.es/lang", datum="2022-01-01", taal="nl", oordeel="misleidend", eigen="Misleidend")
    _check(lab, n["perzisch"], "https://factnameh.com/x", datum="2022-03-11", taal="fa")
    _check(lab, n["birmaans"], "https://myanmar-check.example/x", datum="2022-04-11", taal="my")
    lab.commit()
    nr = {k: pb.nummer(v) for k, v in n.items()}
    manifest = pb.bouw(lab, map_ / "uit", register={**REGISTER, "factnameh.com": PERZISCHE_REDACTIE, "myanmar-check.example": BIRMAANSE_REDACTIE}, vaag=frozenset(), datum="2026-11-15", themas=THEMAS,
                       landen=LANDEN, indeling={nr["villa"]: {"thema": "war", "onderdeel": "ukraine", "tweede": "", "land": "UA"}},
                       dossiers=[_dossier("zelensky-luxury", [nr["villa"]], naam=NAAM, inleiding=INLEIDING)],
                       vertaalmaker="proef", vertalingen={"nl": {nr["villa"]: "Zelensky kocht een villa in Florida"},
                                                          "en": {nr["hindi_en"]: "Zelensky bought a villa and a yacht"}})
    return manifest["bestand"], nr


@pytest.fixture
def client(bestand):
    pad, nr = bestand
    return TestClient(fa.maak_app(pad), follow_redirects=False), nr


def _beeld(client, taal, nummer):
    r = client.get(f"/api/{taal}/deelbeeld/{nummer}.jpg")
    assert r.status_code == 200, r.status_code
    return r, Image.open(io.BytesIO(r.content)).convert("RGB")


def test_the_image_is_1200_by_630_and_the_same_every_time(client):
    c, nr = client
    r, beeld = _beeld(c, "nl", nr["villa"])
    assert beeld.size == (1200, 630) and r.headers["content-type"] == "image/jpeg"
    gegevens = fa.deelgegevens(c.app.state.publicatie, "nl", nr["villa"])
    assert dl.teken(**gegevens) == dl.teken(**gegevens)


def test_the_claim_is_the_heading_of_the_page_with_english_or_nothing_as_fallback(client):
    c, nr = client
    pub = c.app.state.publicatie
    for taal, sleutel in (("nl", "villa"), ("en", "villa"), ("nl", "lang")):
        kop = c.get(f"/api/{taal}/factcheck/{nr[sleutel]}").json()
        verwacht = kop["vertaling"]["tekst"] if kop["vertaling"] else kop["bewering"]
        assert fa.deelgegevens(pub, taal, nr[sleutel])["bewering"] == verwacht, (taal, sleutel)
    # Hindi en Perzisch staan erop zoals in de kop (#34.2as); een schrift zonder lettertype: geen bewering
    assert fa.deelgegevens(pub, "nl", nr["hindi"])["bewering"] == HINDI
    # met een Engelse versie toont de kop op de Nederlandse site die, dus het plaatje ook
    assert fa.deelgegevens(pub, "nl", nr["hindi_en"])["bewering"] == "Zelensky bought a villa and a yacht"
    assert fa.deelgegevens(pub, "nl", nr["birmaans"])["bewering"] == ""
    assert dl.kan_tonen("Zelensky kocht een villa") and dl.kan_tonen("Зеленський") and dl.kan_tonen(HINDI)
    assert not dl.kan_tonen(BIRMAANS)


def test_a_newsroom_name_the_font_cannot_show_gives_way_to_the_count_of_the_page(client):
    """Geen blokjes op het plaatje: kan het lettertype de zin met de naam van de redactie niet tonen, dan de telling van
    de pagina (redacties, talen, jaren), zoals ze ook op de pagina staat."""
    c, nr = client
    g = fa.deelgegevens(c.app.state.publicatie, "nl", nr["birmaans"])
    assert g["bewering"] == "" and BIRMAANSE_REDACTIE not in g["zin"] and dl.kan_tonen(g["zin"])
    assert g["zin"] == c.get(f"/api/nl/factcheck/{nr['birmaans']}").json()["telregel"]
    # een Perzische naam kan nu wel (#34.2as)
    assert PERZISCHE_REDACTIE in fa.deelgegevens(c.app.state.publicatie, "nl", nr["perzisch"])["zin"]


def test_a_long_claim_is_cut_with_an_ellipsis_never_inside_a_word():
    regels = dl.regels(" ".join(["Een heel lange bewering over vaccins en chips die maar doorgaat"] * 6), 46)
    assert len(regels) <= dl.MAX_REGELS and regels[-1].endswith("…")
    woorden = set("Een heel lange bewering over vaccins en chips die maar doorgaat".split())
    assert all(w.rstrip("…") in woorden for regel in regels for w in regel.split())


def test_the_label_has_the_colours_of_the_site():
    css = (WORTEL / "site" / "src" / "styles" / "site.css").read_text(encoding="utf-8")
    licht = css[css.index(".fz {"):css.index("@media (prefers-color-scheme: dark)")]
    for klasse, kleuren in dl.LABELKLEUREN.items():
        for deel, kleur in kleuren.items():
            assert re.search(rf"--{klasse}-{deel}: {kleur};", licht, re.I), (klasse, deel, kleur)


def test_the_field_stays_in_the_band_and_the_claim_stands_on_a_plain_surface(client):
    c, nr = client
    _, beeld = _beeld(c, "nl", nr["villa"])
    band = [beeld.getpixel((x, 40)) for x in range(0, 1200, 40)]
    assert sum(1 for p in band if min(p) < 200) > len(band) / 2          # het veld, donker
    for x, y in ((24, dl.BAND + 24), (1180, 610), (24, 610)):
        assert min(beeld.getpixel((x, y))) > 245, (x, y)                    # het effen vlak
    _, zonder = _beeld(c, "nl", nr["birmaans"])
    vlak = zonder.crop((dl.MARGE, dl.BAND + 30, 1200 - dl.MARGE, dl.BAND + 150))
    assert min(laag for laag, _ in vlak.getextrema()) > 240                 # geen bewering, ook geen vierkantjes
    _, hindi = _beeld(c, "nl", nr["hindi"])
    vlak = hindi.crop((dl.MARGE, dl.BAND + 30, 1200 - dl.MARGE, dl.BAND + 150))
    assert min(laag for laag, _ in vlak.getextrema()) < 100                 # het Hindi staat erop (#34.2as)


def test_the_band_lays_only_the_veil_over_the_field_and_no_second_grain():
    """De korrel komt van het veld (PLAN #34.2bf, SPECS E9.S22 AC2): links in de band, waar geen tekening staat, is het
    plaatje het veld met de sluier van de site, zonder ruis erover."""
    import numpy as np

    veld = Image.open(dl.STATIC / "beeld" / "thema-war-band.webp").convert("RGB")
    schaal = max(dl.BREED / veld.width, dl.BAND / veld.height)
    veld = veld.resize((round(veld.width * schaal), round(veld.height * schaal)), Image.LANCZOS)
    links, boven = (veld.width - dl.BREED) // 2, (veld.height - dl.BAND) // 2
    veld = np.asarray(veld.crop((links, boven, links + dl.BREED, boven + dl.BAND)), dtype=np.float32)
    sluier = np.linspace(0.1, 0.55, dl.BAND, dtype=np.float32)[:, None, None]
    verwacht = veld * (1 - sluier) + np.array([12, 13, 16], dtype=np.float32) * sluier
    band = np.asarray(dl._band("war"), dtype=np.float32)
    helft = dl.BREED // 2
    assert np.abs(band[:, :helft] - verwacht[:, :helft]).max() <= 2


def test_a_second_request_is_not_drawn_again_and_a_cache_may_keep_it(client, monkeypatch):
    c, nr = client
    getekend = []
    echt = dl.teken
    monkeypatch.setattr(dl, "teken", lambda **k: getekend.append(1) or echt(**k))
    fa.deelbeeld_bytes.cache_clear()
    for _ in range(3):
        r = c.get(f"/api/en/deelbeeld/{nr['villa']}.jpg")
        assert r.status_code == 200
    assert len(getekend) == 1
    assert "immutable" in r.headers["cache-control"] and "max-age=31536000" in r.headers["cache-control"]


def test_an_unknown_page_or_language_gives_404(client):
    c, _ = client
    assert c.get("/api/nl/deelbeeld/0000000000000000.jpg").status_code == 404
    assert c.get("/api/nl/deelbeeld/..%2Fx.jpg").status_code == 404
    assert c.get("/api/xx/deelbeeld/0000000000000000.jpg").status_code == 404


def test_the_fact_check_data_names_its_image_with_the_release(client):
    c, nr = client
    g = c.get(f"/api/nl/factcheck/{nr['villa']}").json()
    assert g["deelbeeld"]["src"] == f"/deelbeeld/nl/{nr['villa']}.jpg?v=2026-11-15"
    assert "Bekend als onwaar" in g["deelbeeld"]["alt"] and "Zelensky kocht een villa" in g["deelbeeld"]["alt"]


def test_the_font_is_geist_from_the_site_with_its_licence():
    lettertypes = WORTEL / "factiz_site" / "fonts"
    assert (lettertypes / "OFL.txt").exists() and "SIL OPEN FONT LICENSE" in (lettertypes / "OFL.txt").read_text().upper()
    bron = WORTEL / "site" / "node_modules" / "@fontsource-variable" / "geist" / "files"
    for bestand_ in dl.LETTERTYPES:
        eigen = (lettertypes / bestand_).read_bytes()
        if bron.exists():
            assert eigen == (bron / bestand_).read_bytes(), bestand_


# --- een thema, een onderdeel en een dossier (PLAN #34.2ar, SPECS E9.S23 AC6) -----------------------------------------

@pytest.mark.parametrize("pad", ["thema/war", "thema/war/ukraine", "dossier/zelensky-luxury"])
def test_a_theme_a_part_and_a_dossier_have_their_own_image(client, pad):
    c, _ = client
    r = c.get(f"/api/nl/deelbeeld/{pad}.jpg")
    assert r.status_code == 200 and r.headers["content-type"] == "image/jpeg" and "immutable" in r.headers["cache-control"]
    assert Image.open(io.BytesIO(r.content)).size == (1200, 630)


def test_the_name_on_the_image_is_the_heading_of_the_page(client):
    c, _ = client
    pub = c.app.state.publicatie
    for soort, sleutel, deel, api in (("thema", "war", None, "thema/war"), ("thema", "war", "ukraine", "thema/war/ukraine"),
                                       ("dossier", "zelensky-luxury", None, "dossier/zelensky-luxury")):
        g = c.get(f"/api/nl/{api}").json()
        gegevens = fa.ingangsgegevens(pub, "nl", soort, sleutel, deel)
        assert gegevens["titel"] == (g["kop"] if soort == "thema" else g["naam"]), api
        assert g["deelbeeld"]["src"] == f"/deelbeeld/nl/{api}.jpg?v=2026-11-15", api
        assert gegevens["titel"] in g["deelbeeld"]["alt"], api
    assert fa.ingangsgegevens(pub, "nl", "thema", "war", None)["kicker"] == c.get("/api/nl/thema/war").json()["kicker"]
    assert fa.ingangsgegevens(pub, "nl", "thema", "war", "ukraine")["kicker"] == "Oorlog en conflict"
    assert "1 factcheck" in fa.ingangsgegevens(pub, "nl", "dossier", "zelensky-luxury", None)["regel"]


def test_an_unknown_theme_part_or_dossier_gives_404(client):
    c, _ = client
    for pad in ("thema/astrologie", "thema/war/mars", "thema/health/ukraine", "dossier/bestaat-niet", "dossier/..%2Fx"):
        assert c.get(f"/api/nl/deelbeeld/{pad}.jpg").status_code == 404, pad


# --- elk schrift (PLAN #34.2as, SPECS E9.S28) -----------------------------------------------------------------------------

SCHRIFTEN = {
    "hindi": "यह वीडियो चुनाव के बारे में झूठा दावा करता है", "telugu": "ఈ వీడియో ఎన్నికల గురించి తప్పుడు వాదన",
    "tamil": "இந்த வீடியோ தேர்தல் பற்றிய தவறான கூற்று", "bengaals": "এই ভিডিওটি নির্বাচন সম্পর্কে মিথ্যা দাবি",
    "malayalam": "ഈ വീഡിയോ തിരഞ്ഞെടുപ്പിനെക്കുറിച്ചുള്ള തെറ്റായ അവകാശവാദം", "kannada": "ಈ ವೀಡಿಯೊ ಚುನಾವಣೆಯ ಬಗ್ಗೆ ಸುಳ್ಳು ಹೇಳಿಕೆ",
    "gujarati": "આ વીડિયો ચૂંટણી વિશે ખોટો દાવો છે", "punjabi": "ਇਹ ਵੀਡੀਓ ਚੋਣਾਂ ਬਾਰੇ ਝੂਠਾ ਦਾਅਵਾ ਹੈ",
    "singalees": "මෙම වීඩියෝව මැතිවරණය ගැන බොරු ප්‍රකාශයකි", "arabisch": "هذا الفيديو يدعي ادعاءً كاذبًا عن الانتخابات",
    "perzisch": "این ویدیو ادعای نادرستی درباره انتخابات دارد", "urdu": "یہ ویڈیو انتخابات کے بارے میں جھوٹا دعویٰ ہے",
    "hebreeuws": "הסרטון הזה טוען טענה כוזבת על הבחירות", "thai": "วิดีโอนี้อ้างเท็จเกี่ยวกับการเลือกตั้ง",
    "khmer": "វីដេអូនេះអះអាងមិនពិតអំពីការបោះឆ្នោត", "amhaars": "ይህ ቪዲዮ ስለ ምርጫው ሐሰተኛ ነው",
    "traditioneel": "這段影片關於選舉的說法是錯誤的", "vereenvoudigd": "这段视频关于选举的说法是错误的",
    "japans": "この動画は選挙について誤った主張をしている", "koreaans": "이 영상은 선거에 대해 잘못된 주장을 한다",
    "grieks": "Αυτό το βίντεο κάνει ψευδή ισχυρισμό για τις εκλογές",
}


@pytest.mark.parametrize("schrift", SCHRIFTEN)
def test_every_script_has_a_font_and_no_empty_boxes(schrift):
    tekst = SCHRIFTEN[schrift]
    assert dl.kan_tonen(tekst), schrift
    for bestand_, stuk in dl._stukken(tekst):
        font = dl._font(bestand_, 40, 600)
        leeg = font.getmask("\U000FFFFD")
        for ch in stuk:
            if ch.isspace() or dl.onzichtbaar(ch):
                continue
            masker = font.getmask(ch)
            assert (masker.size, bytes(masker)) != (leeg.size, bytes(leeg)), (schrift, ch, bestand_)


def test_chinese_japanese_and_korean_each_get_their_own_variant():
    voor = lambda tekst, ch: dl._stukken(tekst)[[s for _, s in dl._stukken(tekst)].index(next(s for _, s in dl._stukken(tekst) if ch in s))][0]
    assert "noto-sans-tc" in voor(SCHRIFTEN["traditioneel"], "選")
    assert "noto-sans-sc" in voor(SCHRIFTEN["vereenvoudigd"], "选")
    assert "noto-sans-jp" in voor(SCHRIFTEN["japans"], "選")
    assert "noto-sans-kr" in voor(SCHRIFTEN["koreaans"], "영")


@pytest.mark.parametrize("schrift", ["traditioneel", "japans", "thai"])
def test_text_without_spaces_breaks_inside_the_line_and_never_runs_off_the_image(schrift):
    regels = dl.regels(SCHRIFTEN[schrift] * 8, 46)
    assert 1 < len(regels) <= dl.MAX_REGELS
    assert all(dl._breedte(r, 46, 600) <= dl.BREED - 2 * dl.MARGE for r in regels)


def test_a_right_to_left_line_ends_at_the_right_margin_and_a_left_to_right_line_starts_at_the_left():
    links, rechts = dl.MARGE, dl.BREED - dl.MARGE
    for tekst in (SCHRIFTEN["arabisch"], SCHRIFTEN["hebreeuws"], "زلنسکی در سال 2024 یک ویلا خرید"):
        plaatsen = dl._plaatsing(tekst, links, rechts, 46, 600)
        assert abs(max(x + dl._font(b, 46, 600).getlength(s) for x, b, s, _ in plaatsen) - rechts) < 1, tekst
        assert all(r == "rtl" for _, b, s, r in plaatsen if any("\u0590" <= ch <= "\u06ff" for ch in s))
    plaatsen = dl._plaatsing("Zelensky bought a villa", links, rechts, 46, 600)
    assert plaatsen[0][0] == links and all(r == "ltr" for *_, r in plaatsen)


def test_the_noto_fonts_are_the_packages_of_the_site_with_their_licence():
    noto = WORTEL / "factiz_site" / "fonts" / "noto"
    herkomst = (WORTEL / "factiz_site" / "fonts" / "HERKOMST.md").read_text(encoding="utf-8")
    for pakket in dl.NOTO:
        bron = WORTEL / "site" / "node_modules" / "@fontsource-variable" / pakket
        assert (noto / pakket / "index.css").exists() and f"@fontsource-variable/{pakket}" in herkomst, pakket
        for eigen in (noto / pakket / "files").glob("*.woff2"):
            if bron.exists():
                assert eigen.read_bytes() == (bron / "files" / eigen.name).read_bytes(), eigen.name


@pytest.mark.parametrize("sleutel", ["hindi", "perzisch"])
def test_a_page_in_another_script_draws_its_image(client, sleutel):
    _, nr = client
    _beeld(client[0], "nl", nr[sleutel])
