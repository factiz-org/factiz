"""Het beeld bij een eigen factcheck (PLAN #37.5, B70, DESIGN §4x): zoals het rondging, verkleind, met het stempel erin,
zonder de bediening van X en nooit met een Community Note; vervaagd alleen waar de check het zegt."""

import io
import json

import pytest
from PIL import Image, ImageDraw

from doublecheck import redactie
from doublecheck import redactiebeeld as rb

META = {"nummer": "1", "x": 1, "y": 1, "w": 543, "h": 746, "kop": 66, "onder": 694, "media": [], "note": False,
        "onbeschikbaar": False, "tekst": "", "schaal": 2}


def _post(breed=1086, hoog=1492):
    """Een nagemaakte post zoals de pagina hem vastlegt: wit, met een geblokt vlak waar een foto zou staan."""
    beeld = Image.new("RGB", (breed, hoog), "white")
    teken = ImageDraw.Draw(beeld)
    for x in range(30, breed - 30, 12):
        for y in range(200, 1000, 12):
            if (x // 12 + y // 12) % 2:
                teken.rectangle((x, y, x + 11, y + 11), fill="black")
    uit = io.BytesIO()
    beeld.save(uit, format="PNG")
    return uit.getvalue()


def _open(bytes_):
    return Image.open(io.BytesIO(bytes_))


def test_the_image_is_at_most_640_wide_and_cut_above_the_replies_button():
    klaar = _open(rb.bewerk(_post(), META, "misleidend"))
    assert klaar.format == "JPEG"
    assert klaar.size == (640, round(694 * 2 * 640 / 1086))


def test_the_verdict_is_burned_in_as_a_stamp_over_the_middle():
    klaar = _open(rb.bewerk(_post(), META, "onwaar")).convert("RGB")
    b, h = klaar.size
    midden = klaar.crop((b // 4, h // 2 - 40, 3 * b // 4, h // 2 + 40))
    inkt = rb.INKT["onwaar"]
    gekleurd = sum(1 for p in midden.get_flattened_data() if abs(p[0] - inkt[0]) < 40 and abs(p[1] - inkt[1]) < 40
                   and abs(p[2] - inkt[2]) < 40 and p[0] - p[2] > 60)
    assert gekleurd > 300          # het stempel in de kleur van Onwaar, niet in zwart of wit van de post


def test_the_image_carries_no_metadata():
    klaar = _open(rb.bewerk(_post(), META, "onwaar"))
    assert not klaar.getexif() and "exif" not in klaar.info


def test_a_blur_box_makes_only_that_part_unreadable():
    def ruis(beeld, vak):
        stuk = beeld.convert("L").crop(vak)
        waarden = list(stuk.get_flattened_data())
        gem = sum(waarden) / len(waarden)
        return sum((w - gem) ** 2 for w in waarden) / len(waarden)

    gewoon = _open(rb.bewerk(_post(), META, "onwaar"))
    vervaagd = _open(rb.bewerk(_post(), META, "onwaar", vervaag=[[0.0, 0.1, 0.3, 0.3]]))
    links, rechts = (20, 150, 150, 250), (480, 150, 620, 250)
    assert ruis(vervaagd, links) < ruis(gewoon, links) / 10
    assert ruis(vervaagd, rechts) > ruis(gewoon, rechts) / 2


def test_without_a_blur_box_nothing_is_blurred():
    """Account en gezichten blijven in beeld (PO 2026-11-18): vervagen is nooit de standaard."""
    gewoon = _open(rb.bewerk(_post(), META, "onwaar")).convert("L")
    stuk = list(gewoon.crop((20, 150, 150, 250)).get_flattened_data())
    assert max(stuk) - min(stuk) > 150


def test_a_post_with_a_community_note_never_becomes_an_image():
    with pytest.raises(redactie.Weigering, match="Community Note"):
        rb.bewerk(_post(), {**META, "note": True}, "onwaar")


@pytest.mark.parametrize("anders", [{"tekst": "Niet gevonden", "h": 76}, {"onbeschikbaar": True}, {"fout": "geen post"}])
def test_a_removed_post_gives_no_image(anders):
    with pytest.raises(rb.Weg):
        rb.bewerk(_post(), {**META, **anders}, "onwaar")


def _check(**anders):
    return {"sleutel": "proef", "oordeel": "onwaar",
            "beeld": [{"rol": "rondgaat", "bestand": "beeld-1.jpg", "stempel": True},
                      {"rol": "origineel", "link": "https://nos.nl/x"}], **anders}


def _gemaakt(tmp_path, oordeel="onwaar"):
    statisch, inhoud = tmp_path / "static", tmp_path / "content"
    (statisch / "proef").mkdir(parents=True)
    (statisch / "proef" / "beeld-1.jpg").write_bytes(b"jpg")
    (inhoud / "proef").mkdir(parents=True)
    (inhoud / "proef" / "beelden.json").write_text(json.dumps(
        {"beeld-1.jpg": {"oordeel": oordeel, "breedte": 640, "hoogte": 818}}))
    return statisch, inhoud


def test_a_made_image_gets_its_path_and_size_in_the_edition(tmp_path):
    statisch, inhoud = _gemaakt(tmp_path)
    uit = rb.erbij(_check(), statisch, inhoud)
    assert uit["beeld"][0] | {} == {"rol": "rondgaat", "bestand": "beeld-1.jpg", "stempel": True,
                                    "pad": "/static/redactie/proef/beeld-1.jpg", "breedte": 640, "hoogte": 818}
    assert "pad" not in uit["beeld"][1]


def test_an_image_that_is_not_made_yet_keeps_the_placeholder(tmp_path):
    uit = rb.erbij(_check(), tmp_path / "static", tmp_path / "content")
    assert "pad" not in uit["beeld"][0]


def test_an_image_whose_stamp_says_another_verdict_stops_the_build(tmp_path):
    statisch, inhoud = _gemaakt(tmp_path, oordeel="misleidend")
    with pytest.raises(redactie.Weigering, match="opnieuw"):
        rb.erbij(_check(), statisch, inhoud)


def test_the_post_is_captured_in_the_language_of_the_check():
    # een Engelse check toont X in het Engels (Follow, Reply, Nov 14), niet met de knoppen in het Nederlands (#37.9)
    script = rb.SCRIPT.read_text(encoding="utf-8")
    assert "lang=nl&" not in script
    assert "lang=${talen.get(nummer)}" in script
    import subprocess
    regel = next(r for r in script.splitlines() if r.startswith("const talen"))
    vervolg = script.splitlines()[script.splitlines().index(regel) + 1]
    zone = script.splitlines()[script.splitlines().index(regel) + 3]
    js = (f"process.argv = ['node', 'x', '123456:en', '7654321', 'onzin'];\n{regel}\n{vervolg}\n"
          f"{script.splitlines()[script.splitlines().index(regel) + 2]}\n{zone}\n"
          "console.log(JSON.stringify([[...talen], zone('nl'), zone('en')]));")
    uit = subprocess.run(["node", "-e", js], capture_output=True, text=True, check=True).stdout
    # de tijd op het beeld zoals de tekst haar noemt: Amsterdam bij een Nederlandse check, anders UTC
    assert json.loads(uit) == [[["123456", "en"], ["7654321", "nl"]], "Europe/Amsterdam", "UTC"]
    assert "setTimezoneOverride" in script


@pytest.mark.parametrize("taal, woord", [("tr", "YANLIŞ"), ("uk", None), ("ar", None), ("hi", None), ("zh", None),
                                         ("ja", None), ("fa", None)])
def test_the_stamp_speaks_the_language_of_the_check_in_its_own_script(taal, woord):
    # een check in het Turks krijgt YANLIŞ, uit de woorden van de site (eigen_oordeel_onwaar), niet een stempel dat
    # weigert of lege vakjes tekent (#37.10); elk teken heeft een lettertype dat het kent
    label = rb.label("onwaar", taal)
    assert label and label != rb.label("onwaar", "en")
    if woord:
        assert label.upper() == woord
    assert all(ch.isspace() or rb._lettertype(ch, label) for ch in label)
    klaar = _open(rb.bewerk(_post(), META, "onwaar", taal)).convert("RGB")
    b, h = klaar.size
    inkt = rb.INKT["onwaar"]
    midden = klaar.crop((b // 4, h // 2 - 40, 3 * b // 4, h // 2 + 40))
    gekleurd = sum(1 for p in midden.get_flattened_data() if abs(p[0] - inkt[0]) < 40 and abs(p[1] - inkt[1]) < 40
                   and abs(p[2] - inkt[2]) < 40 and p[0] - p[2] > 60)
    assert gekleurd > 300


def test_dutch_and_english_stamps_stay_exactly_as_they_were():
    assert rb.label("onwaar", "nl") == "Onwaar" and rb.label("context", "en") == "Missing context"
    assert rb._lettertype("O", "ONWAAR") == rb.LETTER


def test_the_image_is_cut_above_the_replies_button_in_every_language_x_writes():
    # zoals X de knop om de link te kopiëren schreef in de beelden van de eerste weekronde (#37.10); daaronder staat alleen
    # bediening ("Lees 360 antwoorden"), die nooit op het beeld mag
    import subprocess
    script = rb.SCRIPT.read_text(encoding="utf-8")
    regel = next(r for r in script.splitlines() if r.startswith("const KOPIEER_BRON"))
    knoppen = ["Link naar post kopiëren", "Copy link to post", "Link zum Post kopieren", "Copier le lien du post",
               "Copiar enlace del post", "Copiar link para o post", "ポストへのリンクをコピー", "Gönderinin bağlantısını kopyala",
               "पोस्ट का लिंक कॉपी करें", "نسخ الرابط إلى المنشور", "کپی پیوند در پست", "Копіювати посилання на пост"]
    js = f"{regel}\nconst r = new RegExp(KOPIEER_BRON, 'i');\nconsole.log(JSON.stringify({json.dumps(knoppen)}.map((k) => r.test(k) && k.length < 45)));"
    uit = subprocess.run(["node", "-e", js], capture_output=True, text=True, check=True).stdout
    assert json.loads(uit) == [True] * len(knoppen)
    assert 'a[href*="birdwatch"]' in script     # een note ook herkend in een taal zonder woorden in de regel
