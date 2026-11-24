"""Het oordeel van de redacties als stempel, met wie het zegt (PLAN #34.2cc, DESIGN §4y, PO 2026-11-19: "in plaats van
'bekend als onwaar', zeggen we gewoon 'onwaar volgens'. Dan zetten we daar de betreffende redactie neer")."""

from factiz_site import i18n


def test_the_stamp_says_the_verdict_alone_in_the_words_of_the_own_checks():
    assert i18n.stempel("nl", "onwaar") == "Onwaar" and i18n.stempel("en", "onwaar") == "False"
    assert i18n.stempel("nl", "waar") == "Klopt" and i18n.stempel("nl", "deels-waar") == "Deels waar"
    assert i18n.stempel("nl", None) == "Gecheckt"


def test_behind_the_stamp_stand_the_newsrooms_that_reached_that_verdict_up_to_four_by_name():
    assert i18n.volgens("nl", "onwaar", ["DW", "BR24 Faktenfuchs"]) == "volgens DW en BR24 Faktenfuchs"
    assert i18n.volgens("nl", "onwaar", ["A", "B", "C", "D"]) == "volgens A, B, C en D"
    assert i18n.volgens("nl", "onwaar", ["A", "B", "C", "D", "E"]) == "volgens A, B, C en 2 andere"
    assert i18n.volgens("en", "misleidend", ["VérifRadar"]) == "according to VérifRadar"


def test_a_disputed_verdict_names_who_disagree_and_no_verdict_says_who_checked():
    assert i18n.volgens("nl", "omstreden", ["PolitiFact", "FactCheck.org"]) == "tussen PolitiFact en FactCheck.org"
    assert i18n.volgens("nl", None, ["AFP"]) == "door AFP"
    assert i18n.volgens("nl", "onwaar", []) == ""


def test_every_language_of_the_site_has_the_words_of_the_stamp():
    for taal in i18n.TALEN:
        for klasse in (*i18n.LABELS, None):
            assert i18n.stempel(taal, klasse)
        assert "X" in i18n.volgens(taal, "onwaar", ["X"]) and "X" in i18n.volgens(taal, "omstreden", ["X", "Y"])


def test_a_title_carries_the_stamp_with_one_name_because_a_title_is_short():
    """PO 2026-11-19: "Ja, zet ze om": ook de titel en de omschrijving voor zoekmachines."""
    assert i18n.oordeel_kop("nl", "onwaar", ["Vera Files"]) == "Onwaar volgens Vera Files"
    assert i18n.oordeel_kop("nl", "onwaar", ["FactCheck.org", "PolitiFact", "NYT", "WaPo"]) == "Onwaar volgens FactCheck.org en 3 andere"
    assert i18n.oordeel_kop("en", "misleidend", ["Snopes"]) == "Misleading according to Snopes"
    assert i18n.oordeel_kop("nl", "onwaar", []) == "Onwaar"
    assert i18n.tekst("en", "factcheck_titel", oordeel=i18n.oordeel_kop("en", "onwaar", ["Snopes"]),
                      bewering="Zelensky bought a villa in Florida") == "False according to Snopes: “Zelensky bought a villa in Florida”"


def test_the_share_image_draws_the_stamp_and_who_says_it():
    import io

    from PIL import Image

    from factiz_site import deelbeeld as dl
    zonder = dl.teken(bewering="A claim", label="Onwaar", klasse="onwaar", zin="Een zin.", thema=None)
    met = dl.teken(bewering="A claim", label="Onwaar", klasse="onwaar", zin="Een zin.", thema=None, volgens=["volgens Vera Files"])
    assert Image.open(io.BytesIO(met)).size == (1200, 630) and met != zonder


def test_the_share_image_names_everyone_only_when_it_fits_and_otherwise_says_how_many_others():
    """Geen *The New York Times en…* naast het stempel: het plaatje neemt de langste vorm die heel past (2026-11-19)."""
    from factiz_site import deelbeeld as dl
    namen = ["FactCheck.org", "PolitiFact", "The New York Times", "Washington Post"]
    vormen = list(dict.fromkeys(i18n.volgens("nl", "onwaar", namen, hoogstens=h) for h in (4, 3, 2, 1)))
    ruimte = dl.BREED - dl.MARGE - (dl.MARGE + 380 + 18)
    gekozen = next(v for v in vormen if not dl._regels(v, dl.ZIN_GROOTTE, ruimte, 1, 500)[1])
    assert gekozen != vormen[0] and gekozen.endswith("andere")


def test_one_name_more_is_named_never_and_one_other():
    """*False according to AFP and 1 others* zei de titel (2026-11-19): één naam meer staat er gewoon."""
    assert i18n.oordeel_kop("en", "onwaar", ["AFP", "Snopes"]) == "False according to AFP and Snopes"
    assert i18n.oordeel_kop("nl", "onwaar", ["AFP", "Snopes", "DW"]) == "Onwaar volgens AFP en 2 andere"
    for h in (1, 2, 3, 4):
        for n in range(1, 8):
            assert " 1 " not in i18n.volgens("en", "onwaar", [f"R{i}" for i in range(n)], hoogstens=h)
