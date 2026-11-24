"""V3 van de radar (PLAN #32.69): wat er op Bluesky rondgaat met een beeld, tegen de nieuwsfoto's van dezelfde dagen."""

import numpy as np

from doublecheck import radar as rd


def _post(did="did:plc:abc", rkey="3k1", langs=("nl",), embed=None, tekst="Kijk dit"):
    record = {"$type": "app.bsky.feed.post", "text": tekst, "langs": list(langs), "createdAt": "2026-11-10T12:00:00Z"}
    if embed is not None:
        record["embed"] = embed
    return {"did": did, "time_us": 1, "kind": "commit",
            "commit": {"operation": "create", "collection": "app.bsky.feed.post", "rkey": rkey, "record": record}}


def _beelden(*cids):
    return {"$type": "app.bsky.embed.images", "images": [{"image": {"ref": {"$link": c}}} for c in cids]}


def test_a_post_counts_only_with_an_image_in_a_language_we_follow_and_keeps_no_text():
    p = rd.beeldpost(_post(embed=_beelden("bafy1", "bafy2")), {"nl", "es"})
    assert p == {"uri": "at://did:plc:abc/app.bsky.feed.post/3k1", "did": "did:plc:abc", "cids": ["bafy1", "bafy2"],
                 "langs": ["nl"], "tijd": "2026-11-10T12:00:00Z"}
    assert "text" not in p and "tekst" not in p
    assert rd.beeldpost(_post(), {"nl"}) is None                                   # zonder beeld
    assert rd.beeldpost(_post(langs=("de",), embed=_beelden("b")), {"nl"}) is None  # andere taal
    media = {"$type": "app.bsky.embed.recordWithMedia", "media": _beelden("bafy3")}
    assert rd.beeldpost(_post(embed=media), {"nl"})["cids"] == ["bafy3"]


def test_only_a_share_of_the_english_posts_is_kept_and_always_the_same_share():
    posts = [_post(rkey=f"r{i}", langs=("en",), embed=_beelden("b")) for i in range(1000)]
    gehouden = [p for p in posts if rd.beeldpost(p, {"nl"}, en_deel=0.1)]
    assert 60 <= len(gehouden) <= 140
    assert gehouden == [p for p in posts if rd.beeldpost(p, {"nl"}, en_deel=0.1)]


def test_a_repost_names_the_post_it_shares_and_anything_else_is_ignored():
    ev = {"did": "x", "kind": "commit", "commit": {"operation": "create", "collection": "app.bsky.feed.repost",
                                                   "record": {"subject": {"uri": "at://did:plc:abc/app.bsky.feed.post/3k1"}}}}
    assert rd.repost_doel(ev) == "at://did:plc:abc/app.bsky.feed.post/3k1"
    assert rd.repost_doel(_post()) is None
    assert rd.repost_doel({"kind": "identity"}) is None


def test_the_image_address_is_the_public_cdn_of_bluesky():
    assert rd.cdn_url("did:plc:abc", "bafy1") == "https://cdn.bsky.app/img/feed_fullsize/plain/did:plc:abc/bafy1@jpeg"


def test_what_goes_round_is_the_most_shared_with_a_floor():
    posts = {f"u{i}": {"uri": f"u{i}", "reposts": i} for i in range(10)}
    assert [p["uri"] for p in rd.viraal(posts, min_reposts=5, n=3)] == ["u9", "u8", "u7"]
    assert rd.viraal(posts, min_reposts=50, n=3) == []


def test_images_are_read_from_rss_media_content_enclosure_and_thumbnail():
    xml = b"""<?xml version="1.0"?><rss xmlns:media="http://search.yahoo.com/mrss/"><channel>
    <item><title>Een</title><link>https://n.nl/1</link><pubDate>Tue, 10 Nov 2026 08:00:00 +0100</pubDate>
      <media:content url="https://n.nl/1.jpg" medium="image"/></item>
    <item><title>Twee</title><link>https://n.nl/2</link><enclosure url="https://n.nl/2.jpg" type="image/jpeg"/></item>
    <item><title>Drie</title><link>https://n.nl/3</link><media:thumbnail url="https://n.nl/3.jpg"/></item>
    <item><title>Vier</title><link>https://n.nl/4</link></item>
    </channel></rss>"""
    assert [(r["titel"], r["beeld"]) for r in rd.beelden_uit_rss(xml)] == [
        ("Een", "https://n.nl/1.jpg"), ("Twee", "https://n.nl/2.jpg"), ("Drie", "https://n.nl/3.jpg")]


def test_the_closest_news_photo_is_found_by_vector_and_by_hash():
    index = [{"url": "a", "vector": np.array([1.0, 0.0]), "pdq": ["0" * 64]},
             {"url": "b", "vector": np.array([0.0, 1.0]), "pdq": ["f" * 64]}]
    beste = rd.dichtstbij(np.array([0.9, 0.1]), ["f" * 63 + "e"], index)
    assert beste["dino"]["url"] == "a" and beste["dino"]["waarde"] > 0.9
    assert beste["pdq"]["url"] == "b" and beste["pdq"]["waarde"] == 1
    assert rd.dichtstbij(np.array([1.0, 0.0]), [], []) == {"dino": None, "pdq": None}


# --- V4: de radar door de controle ----------------------------------------------------------------------------------

def test_a_post_gets_an_own_id_without_the_account_and_always_the_same():
    uri = "at://did:plc:abc/app.bsky.feed.post/3k1"
    i = rd.post_id(uri)
    assert i.startswith("R:") and "did" not in i and "abc" not in i and i == rd.post_id(uri)
    assert rd.post_id("at://did:plc:abc/app.bsky.feed.post/3k2") != i


def test_the_kind_question_shows_the_masked_text_and_the_image_and_asks_for_fixed_words():
    from doublecheck.modellen import MODELLEN

    v = rd.soortverzoek("Kijk: de minister zegt [NAAM] ...", b"jpeg", beeld_b64="QUJD")
    p = v["params"]
    assert p["model"] == MODELLEN["haiku"]["id"]
    inhoud = p["messages"][0]["content"]
    assert inhoud[0]["type"] == "image" and inhoud[0]["source"]["data"] == "QUJD"
    assert "Kijk: de minister zegt [NAAM]" in inhoud[-1]["text"]
    schema = p["output_config"]["format"]["schema"]
    assert set(schema["required"]) == {"soort", "bewering", "onderwerp"}
    assert set(schema["properties"]["soort"]["enum"]) == set(rd.SOORTEN)
    # Haiku 5.5 denkt eerst, en dat telt mee in de grens van de uitvoer: met 300 tokens bleef het antwoord leeg
    assert p["max_tokens"] >= 2000


def test_an_unknown_kind_is_other_and_doubt_about_a_claim_counts_as_a_claim():
    import json

    assert rd.lees_soort(json.dumps({"soort": "nieuwsfoto", "bewering": False, "onderwerp": "x"})) == {
        "soort": "nieuwsfoto", "bewering": False, "onderwerp": "x"}
    assert rd.lees_soort(json.dumps({"soort": "hologram", "bewering": "misschien"}))["soort"] == "anders"
    # twijfel versoepelt nooit: wie niet zeker weet dat er geen bewering is, gaat door de controle
    assert rd.lees_soort(json.dumps({"soort": "nieuwsfoto", "bewering": "misschien"}))["bewering"] is None
    assert rd.lees_soort("kapot") == {"soort": "anders", "bewering": None, "onderwerp": ""}


def test_the_check_takes_the_most_shared_posts_with_a_claim_or_doubt_in_order():
    posts = [{"uri": f"u{i}", "reposts": 100 - i} for i in range(6)]
    soorten = {"u0": {"bewering": False}, "u1": {"bewering": True}, "u2": {"bewering": None},
               "u3": {"bewering": True}, "u5": {"bewering": True}}   # u4 nog zonder soort: niet mee
    assert [p["uri"] for p in rd.te_controleren(posts, soorten, n=2)] == ["u1", "u2"]
    assert [p["uri"] for p in rd.te_controleren(posts, soorten, n=10)] == ["u1", "u2", "u3", "u5"]


def test_the_text_of_a_post_comes_from_the_public_api_view_and_nothing_else():
    view = {"uri": "at://x/app.bsky.feed.post/1", "record": {"text": "  De  minister zei het\n"},
            "embed": {"images": [{"alt": "foto van een brug"}]}}
    assert rd.tekst_van(view) == "De minister zei het"
    assert rd.tekst_van({"record": {}}) == ""


def test_the_count_refuses_while_a_checked_post_has_no_label_and_counts_found_false_alarm_and_wrong_green():
    import pytest

    antw = [{"id": "R:1", "kleur": "rood", "uitkomst": "klopt niet"},
            {"id": "R:2", "kleur": "oranje", "uitkomst": "misleidend"},
            {"id": "R:3", "kleur": "groen", "uitkomst": "klopt"},
            {"id": "R:4", "kleur": None, "uitkomst": "onzeker"},
            {"id": "R:5", "kleur": "groen", "uitkomst": "klopt"},
            {"id": "R:6", "kleur": None, "uitkomst": "niet bevestigd"},
            {"id": "R:7", "fout": "beeld niet te halen"}]
    with pytest.raises(rd.Weigering):
        rd.radartelling(antw, {"R:1": "onwaar"})
    labels = {"R:1": "onwaar", "R:2": "waar", "R:3": "waar", "R:4": "onwaar", "R:5": "misleidend", "R:6": "mening"}
    t = rd.radartelling(antw, labels)
    assert t["gecontroleerd"] == 6 and t["fout bij controleren"] == 1
    assert t["onwaar of misleidend"] == 3 and t["gevonden"] == 1 and t["gemist"] == 2
    assert t["vals alarm"] == 1 and t["groen bij onwaar"] == 1 and t["groen terecht"] == 1
    assert t["uitkomsten"] == {"klopt niet": 1, "misleidend": 1, "klopt": 2, "onzeker": 1, "niet bevestigd": 1}
