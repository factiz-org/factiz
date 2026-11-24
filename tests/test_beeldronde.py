"""Het beeld bij screenshots, één ronde (PLAN #32.6b)."""

import base64

import pytest

from doublecheck import beeldronde as br

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 20


def test_the_image_goes_in_front_of_the_very_same_question():
    params = {"model": "claude-sonnet-5-5", "max_tokens": 3000, "system": "S",
              "messages": [{"role": "user", "content": "Message:\nThe Eiffel tower burned down."}],
              "tools": [{"type": "web_search_20250305", "name": "web_search"}]}
    met = br.met_beeld(params, PNG)
    beeld, tekst = met["messages"][0]["content"]
    assert beeld == {"type": "image", "source": {"type": "base64", "media_type": "image/png",
                                                 "data": base64.b64encode(PNG).decode()}}
    assert tekst == {"type": "text", "text": "Message:\nThe Eiffel tower burned down."}
    assert {k: v for k, v in met.items() if k != "messages"} == {k: v for k, v in params.items() if k != "messages"}
    assert params["messages"][0]["content"] == "Message:\nThe Eiffel tower burned down."  # het origineel blijft


def _u(oordeel, stand, bronnen=(), eigen=False):
    return {"oordeel": oordeel, "stand": stand, "bronnen": list(bronnen), "eigen_bewijs": eigen}


STUKKEN = [{"id": "n1", "set": "N"}, {"id": "n2", "set": "N"}, {"id": "w1", "set": "W"}, {"id": "w2", "set": "W"}]


def test_the_count_refuses_while_a_red_on_a_true_photo_or_a_green_on_fake_news_is_unread():
    per_arm = {"zonder": {"n1": _u("onzeker", 5), "n2": _u("klopt niet", 1, ["web"]), "w1": _u("klopt", 8),
                          "w2": _u("klopt", 8)},
               "met": {"n1": _u("klopt niet", 1, ["geheugen"], eigen=True), "n2": _u("klopt niet", 1, ["web"]),
                       "w1": _u("klopt niet", 2, ["web"]), "w2": _u("klopt", 8)}}
    with pytest.raises(br.Weigering):
        br.telling(STUKKEN, per_arm, {("n2", "zonder"): "bewijst", ("n2", "met"): "bewijst"})
    labels = {("n2", "zonder"): "bewijst", ("n2", "met"): "bewijst", ("w1", "met"): "vals"}
    uit = br.telling(STUKKEN, per_arm, labels)
    assert uit["zonder"]["N"]["rood met bewijs"] == 1 and uit["met"]["N"]["rood met bewijs"] == 2
    assert uit["met"]["W"]["onterecht rood"] == 1 and uit["zonder"]["W"].get("onterecht rood", 0) == 0
    assert uit["eisen"] == {"N: met beeld minstens 10 punten meer rood met bewijs": True,
                            "W: met beeld niet meer onterecht rood dan zonder": False,
                            "W: hoogstens 1 onterecht rood met beeld": True}


def test_a_green_on_fake_news_must_be_read_and_a_red_without_proof_does_not_count():
    per_arm = {"zonder": {"n1": _u("klopt", 8), "n2": _u("klopt niet", 1, ["web"])},
               "met": {"n1": _u("klopt", 8), "n2": _u("klopt niet", 1, ["web"])}}
    with pytest.raises(br.Weigering):
        br.telling(STUKKEN[:2], per_arm, {("n2", "zonder"): "bewijst niet", ("n2", "met"): "bewijst niet"})
    labels = {("n2", "zonder"): "bewijst niet", ("n2", "met"): "bewijst niet", ("n1", "zonder"): "vals groen",
              ("n1", "met"): "vals groen"}
    uit = br.telling(STUKKEN[:2], per_arm, labels)
    assert uit["met"]["N"]["rood met bewijs"] == 0 and uit["met"]["N"]["groen"] == 1
