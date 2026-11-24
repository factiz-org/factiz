"""Opknippen en maskeren vóór de controlestap (B43, PLAN #31.10): alleen de
bewering gaat naar het model, zonder de chatomgeving en zonder persoonsgegevens."""

from doublecheck import opknippen


def test_the_chat_surroundings_are_cut_and_the_message_stays():
    ocr = "\n".join([
        "9:41 LTE 87%",
        "Buurtapp Westwijk",
        "23 participants",
        "~ Marieke Hoogenboom +31 6 1234 5678",
        "Forwarded many times",
        "Drinking hot water every 15 minutes kills the coronavirus in your throat.",
        "Share this with everyone you love!",
        "14:32 ✓✓",
        "Type a message",
    ])
    uit = opknippen.knip(ocr)
    assert "Drinking hot water every 15 minutes kills the coronavirus in your throat." in uit
    assert "Share this with everyone you love!" in uit
    for weg in ("9:41", "Westwijk", "participants", "Marieke", "Forwarded", "14:32", "Type a message"):
        assert weg not in uit


def test_phone_numbers_emails_and_handles_are_masked_but_claim_numbers_stay():
    tekst = ("Call Anna on +44 7700 900412 or 06-12345678, (555) 123-4567, mail anna.peters@gmail.com, "
             "follow @truthnow and wa.me/31612345678. In 2021 about 6,000,000 people, 97 to 99 percent, 8,849 metres.")
    uit = opknippen.maskeer(tekst)
    for weg in ("7700", "12345678", "123-4567", "anna.peters", "@truthnow", "31612345678"):
        assert weg not in uit
    for blijft in ("Call Anna", "In 2021", "6,000,000", "97 to 99 percent", "8,849 metres"):
        assert blijft in uit
    assert "[telefoon]" in uit and "[e-mail]" in uit and "[handle]" in uit


def test_a_plain_claim_passes_unchanged():
    zin = "The Earth is flat and NASA hides it."
    assert opknippen.opknippen(zin) == zin


def test_a_social_post_keeps_its_author_name_but_loses_the_buttons():
    ocr = "Joe Biden\n@JoeBiden · 2h\nI will ban all cars by 2025.\n12.4K Retweets 40K Likes\nReply Retweet Like Share"
    uit = opknippen.opknippen(ocr)
    assert "Joe Biden" in uit and "I will ban all cars by 2025." in uit
    assert "@JoeBiden" not in uit and "Retweets" not in uit and "Reply" not in uit


def test_the_group_name_goes_even_when_the_ocr_puts_a_blank_line_under_it():
    uit = opknippen.knip("9:41 LTE 87%\nFootball Dads\n\n38 participants\n\nDrinking hot water kills the virus.")
    assert uit == "Drinking hot water kills the virus."


def test_an_email_address_is_masked_even_when_the_ocr_puts_a_space_around_the_at_sign():
    """§155: bij 3 van de ~67 adressen zette de OCR een spatie vóór de @, en
    bleef het deel vóór de @ staan."""
    for tekst in ("Mail jan.devries @gmail.com for the report", "Mail jan.devries@ gmail.com for the report",
                  "Mail jan.devries @ gmail.com for the report"):
        uit = opknippen.maskeer(tekst)
        assert "jan.devries" not in uit and "gmail" not in uit and "[e-mail]" in uit, uit
    assert opknippen.maskeer("Meet me @ the station at 9") == "Meet me @ the station at 9"


# --- B55: eerst zwart in het beeld wat het maskeren uit de tekst haalt (PLAN #32.36) -------------------------------

def _woord(tekst, links, boven=10, breedte=None, hoogte=20):
    return {"tekst": tekst, "links": links, "boven": boven, "breedte": breedte or 12 * len(tekst), "hoogte": hoogte}


def _regel(*woorden, boven=10):
    uit, x = [], 0
    for w in woorden:
        uit.append(_woord(w, x, boven))
        x += 12 * len(w) + 10
    return uit


def test_only_the_words_that_masking_would_label_are_blacked_and_a_sender_line_goes_whole():
    regels = [_regel("~", "Marieke", "Hoogenboom", boven=10),
              _regel("Hot", "water", "kills", "the", "virus", boven=50),
              _regel("call", "+31", "6", "1234", "5678", "or", "mail", "jan@voorbeeld.nl", boven=90),
              _regel("follow", "@jandevries", "for", "more", boven=130)]
    vakken = opknippen.zwarte_vakken(regels)
    zwart = {(v[0], v[1]) for v in vakken}
    assert all((w["links"], w["boven"]) in zwart for w in regels[0])            # de afzender, de hele regel
    assert not any((w["links"], w["boven"]) in zwart for w in regels[1])        # de bewering blijft
    assert [w["tekst"] for w in regels[2] if (w["links"], w["boven"]) in zwart] == ["+31", "6", "1234", "5678",
                                                                                  "jan@voorbeeld.nl"]
    assert [w["tekst"] for w in regels[3] if (w["links"], w["boven"]) in zwart] == ["@jandevries"]


def test_the_name_lines_are_the_ones_the_text_cutting_removes_too():
    regels = ["Buurtapp Westwijk", "23 participants", "~ Marieke Hoogenboom", "Hot water kills the virus"]
    namen = opknippen.namen_regels(regels)
    assert namen == {0, 1, 2}
    assert all(regels[i] not in opknippen.knip("\n".join(regels)).splitlines() for i in namen)


def test_the_image_for_the_model_loses_the_number_and_the_handle_and_keeps_the_claim():
    import io

    from doublecheck.config import load_config
    from doublecheck.ocr import extract_text
    from tests.beelden import kop_screenshot

    ocr = load_config().ocr
    beeld = kop_screenshot(["Hot water kills the virus", "call +31 6 1234 5678 now", "follow @jandevries"],
                           hoogte=220)
    bron = io.BytesIO()
    beeld.save(bron, format="PNG")
    uit, n = opknippen.zwart_beeld(bron.getvalue(), ocr)
    gelezen = extract_text(uit, ocr).text
    assert n >= 5 and "virus" in gelezen and "1234" not in gelezen and "jandevries" not in gelezen


def test_the_image_for_the_model_never_carries_its_metadata():
    import io

    from PIL import Image

    from doublecheck.config import load_config
    from tests.beelden import kop_screenshot

    beeld = kop_screenshot(["Hot water kills the virus"])
    exif = Image.Exif()
    exif[0x010E] = "geheime beschrijving"  # ImageDescription
    bron = io.BytesIO()
    beeld.save(bron, format="JPEG", exif=exif.tobytes())
    uit, _ = opknippen.zwart_beeld(bron.getvalue(), load_config().ocr)
    assert b"geheime beschrijving" in bron.getvalue() and b"geheime beschrijving" not in uit
    assert not Image.open(io.BytesIO(uit)).getexif()


def test_a_handle_is_masked_even_when_the_ocr_puts_an_underscore_right_before_the_at_sign():
    """§252: de tekstherkenning las "@Postcard_news" als "_@rosteard"; de regel moet dan nog steeds een handle zien."""
    assert opknippen.maskeer("Shared by _@rosteard yesterday") == "Shared by _[handle] yesterday"
    assert opknippen.maskeer("mail jan_b@voorbeeld.nl") == "mail [e-mail]"
