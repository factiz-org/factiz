"""De voormeting voor de beeldmotor (PLAN #32.14)."""

import pytest

from doublecheck import beeldmotor as bm

HTML = """<html><head><meta property="og:image" content="https://x.org/deel.jpg"></head><body>
<nav><img src="/logo.png" alt="Logo"></nav>
<div class="entry-content"><p>A video is being shared claiming to show floods in Rasuwa.</p>
<figure><img src="/viral.jpg" alt="Screenshot of the viral post" width="800">
<figcaption>The viral video on Facebook</figcaption></figure>
<p>A reverse image search led us to a report from Arunachal Pradesh, June 2026.</p>
<img data-src="/origineel.jpg" alt=""><p>The original video, posted on 24 June.</p>
<img src="/klein.jpg" width="40"></div>
<aside><img src="/ander-artikel.jpg"></aside></body></html>"""


def test_each_content_image_comes_with_its_alt_text_caption_and_the_words_around_it():
    uit = bm.beelden_met_tekst(HTML, "https://x.org/a")
    assert [b["adres"] for b in uit] == ["https://x.org/viral.jpg", "https://x.org/origineel.jpg"]
    assert uit[0]["alt"] == "Screenshot of the viral post" and uit[0]["bijschrift"] == "The viral video on Facebook"
    assert uit[0]["voor"].endswith("claiming to show floods in Rasuwa.")
    assert uit[1]["voor"].endswith("Arunachal Pradesh, June 2026.") and uit[1]["na"].startswith("The original video")
    assert set(uit[0]) == {"adres", "alt", "bijschrift", "voor", "na"}  # tekst, nooit het beeld (DR3)


def test_counting_refuses_until_every_article_is_read_and_applies_the_bar_of_24():
    stukken = [{"id": f"c{i}", "redactie": "FACTLY" if i % 2 else "VERA Files"} for i in range(40)]
    labels = {f"c{i}": {"viraal": "ja", "origineel": "ja" if i < 10 else "nee", "bereikbaar": True}
              for i in range(24)}
    with pytest.raises(bm.Weigering, match="c24"):
        bm.telling(stukken, labels)
    labels |= {f"c{i}": {"viraal": "nee", "origineel": "nee", "bereikbaar": i != 39} for i in range(24, 40)}
    uit = bm.telling(stukken, labels)
    assert uit["viraal beeld in een bereikbaar artikel"] == 24 and uit["origineel"] == 10
    assert uit["beslisregel: minstens 24 van 40"] is True and uit["per redactie"]["FACTLY"]["viraal"] == 12
    labels["c0"] = {**labels["c0"], "bereikbaar": False}
    assert bm.telling(stukken, labels)["beslisregel: minstens 24 van 40"] is False
