"""De stiltetoets voor beelden (PLAN.md #26.3)."""

import numpy as np
import pytest
from PIL import Image

from doublecheck import beeldstilte as bs


def _sjabloon(maat=(600, 500)):
    rng = np.random.default_rng(3)
    vlak = np.linspace(40, 200, maat[0] * maat[1] * 3).reshape(maat[1], maat[0], 3)
    return Image.fromarray((vlak + rng.normal(0, 8, vlak.shape)).clip(0, 255).astype(np.uint8))


def test_a_caption_splits_near_the_middle_on_a_word_boundary():
    assert bs.splits("when the meeting could have been an email after all") == (
        "when the meeting could have", "been an email after all")
    assert bs.splits("没有空格的句子也能分开") == ("没有空格的", "句子也能分开")


def test_two_memes_on_one_template_share_the_picture_but_not_the_text():
    sjabloon = _sjabloon()
    a = bs.maak_meme(sjabloon, "first top text here", "first bottom text here")
    b = bs.maak_meme(sjabloon, "another caption on top", "and a different ending")
    assert a.size == b.size == sjabloon.size
    verschil = np.abs(np.asarray(a, dtype=int) - np.asarray(b, dtype=int)).sum(axis=2)
    h = sjabloon.height
    assert verschil[: h // 5].mean() > 5 and verschil[-h // 5:].mean() > 5   # andere tekst
    assert verschil[2 * h // 5: 3 * h // 5].mean() < 1                     # zelfde beeld


def test_captions_are_the_english_pieces_of_post_length_in_order():
    rijen = [{"taal": t, "varianten": [{"tekst": x}]} for t, x in [
        ("en", "x" * 59), ("nl", "y" * 80), ("en", "a" * 60), ("en", "b" * 121), ("en", "c" * 120)]]
    assert bs.onderschriften(rijen, 5) == ["a" * 60, "c" * 120]


def test_an_event_needs_ten_large_photos_and_keeps_their_licence():
    def bestand(titel, mime="image/jpeg", breedte=1600):
        return {"title": f"File:{titel}", "imageinfo": [{
            "mime": mime, "width": breedte, "thumburl": f"https://upload.example/{titel}",
            "descriptionurl": f"https://commons.example/{titel}",
            "extmetadata": {"LicenseShortName": {"value": "CC BY-SA 4.0"}}}]}

    paginas = {str(i): bestand(f"{i:02d}.jpg") for i in range(10)}
    paginas["x"] = bestand("logo.svg", mime="image/svg+xml")
    paginas["y"] = bestand("klein.jpg", breedte=400)
    gekozen = bs.kies_bestanden({"query": {"pages": paginas}}, 10)
    assert [g["titel"] for g in gekozen] == [f"File:{i:02d}.jpg" for i in range(10)]
    assert gekozen[0]["licentie"] == "CC BY-SA 4.0"
    del paginas["9"]
    assert bs.kies_bestanden({"query": {"pages": paginas}}, 10) == []


def test_the_rest_of_m4fc_is_everything_outside_the_linked_items():
    assert bs.rest_indices(6, {"1", "4"}) == [0, 2, 3, 5]


def _treffer(vraag, groep="m4fc_rest", vorm="origineel", variant="pdq_of_dino", index_id="m4fc:00001.jpg"):
    return {"groep": groep, "vraag": vraag, "vorm": vorm, "variant": variant, "index_id": index_id}


def test_counting_refuses_a_hit_without_a_label():
    with pytest.raises(bs.Weigering):
        bs.uitslag([_treffer("rest:1")], {}, {"m4fc_rest": 100})


def test_a_hit_on_the_same_picture_is_not_a_false_alarm():
    treffers = [
        _treffer("rest:1"),                                  # twee redacties, één viraal beeld
        _treffer("rest:2"),
        _treffer("rest:2", variant="dino"),
        _treffer("meme:3-4", groep="memes", index_id="meme:3-0"),
    ]
    labels = {"rest:1|origineel|m4fc:00001.jpg": "terecht", "rest:2|origineel|m4fc:00001.jpg": "vals",
              "meme:3-4|origineel|meme:3-0": "vals"}
    uit = bs.uitslag(treffers, labels, {"m4fc_rest": 1000, "memes": 900})
    rest = uit["m4fc_rest"]["pdq_of_dino"]
    assert (rest["n"], rest["treffers"], rest["terecht"], rest["vals"]) == (1000, 2, 1, 1)
    assert uit["m4fc_rest"]["dino"]["vals"] == 1
    assert uit["memes"]["pdq_of_dino"]["vals"] == 1
    assert uit["memes"]["pdq"]["vals"] == 0
    assert uit["memes"]["pdq"]["bovengrens"] == pytest.approx(1 - 0.05 ** (1 / 900))


def test_queries_are_loaded_only_when_their_block_is_measured(tmp_path):
    """3.665 beelden van 1024 px tegelijk in het geheugen is ruim 10 GB; de
    vragen blijven paden tot hun blok aan de beurt is."""
    _sjabloon().save(tmp_path / "a.png")
    _sjabloon((300, 200)).save(tmp_path / "b.jpg")
    (tmp_path / "kapot.jpg").write_bytes(b"geen beeld")
    lijst = bs.lui(tmp_path)
    assert [naam for naam, _ in lijst] == ["a.png", "b.jpg", "kapot.jpg"]
    assert all(callable(laad) for _, laad in lijst)
    beelden = [laad() for _, laad in lijst]
    assert beelden[0].size == (600, 500) and beelden[2] is None
