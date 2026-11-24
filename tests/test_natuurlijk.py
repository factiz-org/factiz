"""Natuurlijke parafrasen: twee redacties, dezelfde virale post (PLAN #25.13).

Factcheckers noemen in ClaimReview waar de claim verscheen. Checkten twee
verschillende redacties dezelfde post, dan zijn hun claimteksten twee
onafhankelijke formuleringen van dezelfde claim: gekozen op dezelfde post,
niet op gelijkenis, dus niet circulair. De toets zoekt met formulering A,
met A zelf uit de index, en kijkt of B terugkomt.
"""

import numpy as np

from doublecheck import natuurlijk as nt


def test_post_ids_are_kept_and_hosts_unified():
    assert nt.post_sleutel("https://x.com/user/status/123?s=20") == "twitter.com/user/status/123"
    assert nt.post_sleutel("https://www.facebook.com/photo.php?fbid=987&set=a.1&ref=share") == \
        "facebook.com/photo.php?fbid=987&set=a.1"
    assert nt.post_sleutel("https://m.facebook.com/story.php?story_fbid=55&id=66") == \
        "facebook.com/story.php?id=66&story_fbid=55"


def test_only_single_posts_on_social_platforms_count():
    assert nt.post_sleutel("https://www.facebook.com/search/top?q=x") is None
    assert nt.post_sleutel("https://www.facebook.com/photo") is None
    assert nt.post_sleutel("https://www.whitehouse.gov/briefings/remarks-14") is None
    assert nt.post_sleutel("https://www.foxnews.com/transcript/x") is None
    assert nt.post_sleutel("https://www.instagram.com/p/AbC123/") == "instagram.com/p/AbC123"
    assert nt.post_sleutel("https://www.tiktok.com/@a/video/42") == "tiktok.com/@a/video/42"


def _v(*xs):
    v = np.array(xs, dtype=np.float32)
    return v / np.linalg.norm(v)


def test_the_search_leaves_the_query_out_and_classifies_honestly():
    ids = ["A", "B", "C"]
    matrix = np.vstack([_v(1, 0, 0), _v(0.97, 0.24, 0), _v(0, 1, 0)])
    groep = {"A", "B"}
    # A zoekt; A zelf telt niet, B ligt op 0,97: gevonden.
    assert nt.zoek_zonder(0, matrix, ids, groep, match=0.92, verwant=0.80)[0] == "gevonden"
    # Met een strengere drempel: verwant.
    assert nt.zoek_zonder(0, matrix, ids, groep, match=0.98, verwant=0.80)[0] == "verwant"
    # C zoekt in een groep met A: de dichtste is B, buiten de groep, maar onder de drempel.
    assert nt.zoek_zonder(2, matrix, ids, {"C", "A"}, match=0.92, verwant=0.80)[0] == "niets"
    # Een ándere claim boven de drempel is een fout.
    matrix2 = np.vstack([_v(1, 0, 0), _v(0, 0, 1), _v(0.99, 0.14, 0)])
    assert nt.zoek_zonder(0, matrix2, ids, {"A", "B"}, match=0.92, verwant=0.80)[0] == "fout"
