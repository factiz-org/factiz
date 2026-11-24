"""Het deelplaatje in TypeScript naast dat in Python (B80, PLAN #34.2bo stap 5): dezelfde adressen, dezelfde 404, dezelfde
maat, en een plaatje dat binnen de gemeten marge gelijk is, in elk schrift. Pillow en resvg zetten een rand net anders, dus
de bytes verschillen altijd; `factiz_site.gelijk_deelbeeld` meet hoeveel, en hier staat dat het een echte fout ziet."""

import io
import subprocess
from pathlib import Path

import pytest
from PIL import Image

from doublecheck import publiceren as pb
from factiz_site import deelbeeld as dl
from factiz_site import gelijk_deelbeeld as gd
from factiz_site import i18n
from tests.test_factiz_dossiers import INLEIDING, NAAM, _dossier
from tests.test_factiz_themas import LANDEN, THEMAS
from tests.schriften import NAMEN, PANEEL
from tests.test_publiceren import REGISTER, _check, _claim, _lab

SITE = Path(__file__).resolve().parent.parent / "site"
# de taal bij elk schrift van het paneel (`tests/schriften.py`); Georgisch, Birmaans en Oriya hebben geen lettertype
TAAL = {"arabisch": "ar", "bengaals": "bn", "han": "ja", "cyrillisch": "ru", "devanagari": "hi", "ethiopisch": "am",
        "georgisch": "ka", "grieks": "el", "gujarati": "gu", "hangul": "ko", "hebreeuws": "he", "hiragana": "ja",
        "katakana": "ja", "latijn": "en", "birmaans": "my", "oriya": "or", "thai": "th", "gurmukhi": "pa", "kannada": "kn",
        "khmer": "km", "malayalam": "ml", "singalees": "si", "tamil": "ta", "telugu": "te", "naam-devanagari": "hi",
        "naam-devanagari-variant": "hi", "naam-tamil": "ta", "naam-arabisch": "ar", "naam-cyrillisch": "ru",
        "naam-latijn-diakriet": "vi", "naam-latijn": "es"}
BEWERINGEN = {
    **{naam: (TAAL[naam], tekst) for naam, tekst in PANEEL.items()},
    "villa": ("en", "Zelensky bought a villa in Florida"),
    "lang": ("nl", " ".join(["Een heel lange bewering over vaccins en chips die maar doorgaat"] * 6)),
    "perzisch": ("fa", "زلنسکی در سال ۲۰۲۳ یک ویلا به ارزش ۸ میلیون دلار در Florida خرید"),
    "arabisch-latijn": ("ar", "قال بيل غيتس إن لقاح COVID-19 يحتوي على شريحة 5G منذ عام 2021"),
    "chinees": ("zh", "網傳「韓國今天確診1316例」"),
}
# redacties met een naam in een ander schrift, voor de zin onder het label
REDACTIES = {"tamil.example": NAMEN["naam-tamil"], "arabisch.example": NAMEN["naam-arabisch"],
             "cyrillisch.example": NAMEN["naam-cyrillisch"], "fa.example": "فکت\u200cنامه"}


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    """Een kleine uitgave met een bewering per schrift, een thema met onderdeel en een dossier, en de voorraad van de
    TypeScript-kant in een eigen map."""
    map_ = tmp_path_factory.mktemp("deelbeeld-ts")
    lab = _lab(map_)
    n = {k: _claim(lab, i + 1, tekst, taal=taal) for i, (k, (taal, tekst)) in enumerate(BEWERINGEN.items())}
    redacties = ["factcheck.afp.com", *REDACTIES]
    for i, (k, (taal, _)) in enumerate(BEWERINGEN.items()):
        _check(lab, n[k], f"https://{redacties[i % len(redacties)]}/{k}", datum=f"2024-{i % 12 + 1:02d}-{i % 28 + 1:02d}",
               taal=taal)
    lab.commit()
    nr = {k: pb.nummer(v) for k, v in n.items()}
    manifest = pb.bouw(lab, map_ / "uit", register={**REGISTER, **REDACTIES}, vaag=frozenset(), datum="2026-11-15", themas=THEMAS,
                       landen=LANDEN, indeling={nr["villa"]: {"thema": "war", "onderdeel": "ukraine", "tweede": "", "land": "UA"},
                                                nr["devanagari"]: {"thema": "health", "onderdeel": "vaccines", "tweede": "",
                                                                   "land": "IN"}},
                       # en een dossier met een gevuld vlak in zijn tekening (de kaart van de strook, 2026-11-19)
                       dossiers=[_dossier("zelensky-luxury", [nr["villa"]], naam=NAAM, inleiding=INLEIDING),
                                 _dossier("gaza-oorlog", [nr["perzisch"]], naam=NAAM, inleiding=INLEIDING)],
                       vertaalmaker="proef", vertalingen={"nl": {nr["villa"]: "Zelensky kocht een villa in Florida"}})
    voorraad = map_ / "voorraad"
    uit = subprocess.run(["node", "scripts/deelbeeld-voorraad.ts", str(voorraad)], capture_output=True, text=True, cwd=SITE,
                         timeout=600)
    assert uit.returncode == 0, uit.stderr[-3000:]
    return Path(manifest["bestand"]), nr, voorraad


def _vergelijk(site, adressen):
    bestand, _, voorraad = site
    return gd.vergelijk(bestand, [(a, "") for a in adressen], voorraad)


def test_every_address_shape_answers_like_python_and_the_rest_is_the_same_404(site):
    _, nr, _ = site
    goed = [f"/api/en/deelbeeld/{nr['villa']}.jpg", f"/api/nl/deelbeeld/{nr['villa']}.jpg",
            "/api/en/deelbeeld/thema/war.jpg", "/api/ar/deelbeeld/thema/war/ukraine.jpg",
            "/api/fa/deelbeeld/dossier/zelensky-luxury.jpg", "/api/en/deelbeeld/dossier/gaza-oorlog.jpg"]
    fout = [f"/api/en/deelbeeld/{nr['villa']}.png", f"/api/en/deelbeeld/{nr['villa'][:-1]}.jpg",
            f"/api/en/deelbeeld/{nr['villa'][:-1]}G.jpg", "/api/en/deelbeeld/0000000000000000.jpg",
            "/api/en/deelbeeld/thema/geen.jpg", "/api/en/deelbeeld/thema/war/geen.jpg", "/api/en/deelbeeld/thema/health/covid.jpg",
            "/api/en/deelbeeld/dossier/geen.jpg", "/api/en/deelbeeld/dossier/zelensky-luxury/x.jpg", "/api/en/deelbeeld/.jpg",
            "/api/en/deelbeeld/thema.jpg", "/api/en/deelbeeld/thema/war", "/api/xx/deelbeeld/thema/war.jpg",
            f"/api/en/deelbeeld/zelf/{nr['villa']}.jpg", "/api/en/deelbeeld/thema/war/ukraine/x.jpg"]
    uitslag = _vergelijk(site, goed + fout)
    assert [r["status"] for r in uitslag] == [[200, 200]] * len(goed) + [[404, 404]] * len(fout)
    for r in uitslag[:len(goed)]:
        assert Image.open(io.BytesIO(r["ts"])).format == "JPEG" and r["maat"] == [1200, 630], r["adres"]


def test_every_script_of_the_panel_matches_python_within_the_measured_margin_in_the_15_languages(site):
    """Elk schrift van het paneel in twee talen van de site, zodat alle vijftien voorkomen, met de label en de zin in die
    taal (ook van rechts naar links), en de thema's, een onderdeel en een dossier: pixels mogen schuiven, de volgorde en de
    vorm van de tekens niet (PLAN #34.2bo stap 5)."""
    _, nr, _ = site
    adressen = [f"/api/{i18n.TALEN[(i + d) % len(i18n.TALEN)]}/deelbeeld/{nr[k]}.jpg"
                for i, k in enumerate(BEWERINGEN) for d in (0, 7)]
    adressen += [f"/api/{taal}/deelbeeld/{a}.jpg" for taal in ("en", "nl", "fa", "hi", "ja", "zh", "ru")
                 for a in ("thema/war", "thema/health/vaccines", "dossier/zelensky-luxury", "dossier/gaza-oorlog")]
    assert set(i18n.TALEN) <= {a.split("/")[2] for a in adressen}
    uitslag = _vergelijk(site, adressen)
    assert gd.afwijkingen(uitslag) == []
    assert all(r["gemiddeld"] <= gd.GEMIDDELD and r["vak"] <= gd.VAK_GRENS for r in uitslag)


def test_a_script_without_a_font_leaves_the_surface_plain_as_in_python(site):
    _, nr, _ = site
    r, = _vergelijk(site, [f"/api/en/deelbeeld/{nr['birmaans']}.jpg"])
    for kant in ("py", "ts"):
        vlak = Image.open(io.BytesIO(r[kant])).convert("L").crop((dl.MARGE, dl.BAND + 30, 1200 - dl.MARGE, dl.BAND + 150))
        assert vlak.getextrema()[0] > 240, kant


def test_the_measure_sees_a_wrong_word_order_a_missing_word_and_another_label():
    """De grens van het vak ligt onder wat een echte fout geeft, met Pillow aan beide kanten: twee woorden om, een woord
    weg, een letter anders, een ander label. Een stip of klinkerteken ziet de maat niet; daarvoor zijn de vellen."""
    basis = {"label": "Known to be false", "klasse": "onwaar", "zin": "AFP checked this claim on 5 March 2024.", "thema": "war"}
    tekst = "Zelensky bought a villa in Florida for eight million dollars with money from the aid"
    goed = dl.teken(bewering=tekst, **basis)
    for ander in (tekst.replace("villa in", "in villa"), tekst.replace(" eight", ""), tekst.replace("villa", "vilma")):
        assert gd.verschil(goed, dl.teken(bewering=ander, **basis))["vak"] > gd.VAK_GRENS, ander
    arabisch = "زيلينسكي اشترى فيلا في فلوريدا"
    goed = dl.teken(bewering=arabisch, **basis)
    assert gd.verschil(goed, dl.teken(bewering="زيلينسكي فيلا اشترى في فلوريدا", **basis))["vak"] > gd.VAK_GRENS
    assert gd.verschil(goed, dl.teken(bewering=arabisch, **{**basis, "label": "Known to be misleading",
                                                              "klasse": "misleidend"}))["vak"] > gd.VAK_GRENS
    assert gd.verschil(goed, goed) == {"maat": [1200, 630], "gemiddeld": 0.0, "vak": 0.0}
