"""De netwerktoets: echte propaganda-artikelen tegen hun ontkrachting (#28.5).

EUvsDisinfo noemt per zaak de media die het verhaal verspreidden; de set van
Sheffield (Leite e.a., CIKM 2024) maakt daar artikel-URL's van, en datum plus
domein koppelt 3.599 zaken aan onze checks. De vraag is wat een lezer zou
plakken: de kop, of de kop met de inleiding. Wat een site bij elk artikel
zet (een slogan, de sitenaam in de titel) is geen artikeltekst.
"""

from doublecheck import netwerktoets as nt


def _artikel(host, titel, beschrijving="", tekst="", claim="gfc-1", report="/report/x", taal="Russian"):
    return {"article_url": f"https://{host}/a/{abs(hash(titel))}", "claim_id": claim, "report": report,
            "taal": taal, "bron": "wayback", "titel": titel, "beschrijving": beschrijving, "tekst": tekst}


def test_a_slogan_every_article_of_a_site_carries_is_not_the_lead():
    slogan = "Sputnik Беларусь говорит то, о чем другие молчат"
    artikelen = [_artikel("sputnik.by", f"Кop {i}", slogan, f"Первый абзац статьи номер {i}.") for i in range(3)]
    artikelen.append(_artikel("ria.ru", "Заголовок", "Своя, неповторимая аннотация к статье."))
    items = {i.host: i for i in nt.items(artikelen)}
    sputnik = [i for i in nt.items(artikelen) if i.host == "sputnik.by"]
    assert all(slogan not in i.kop_inleiding for i in sputnik)
    assert sputnik[0].kop_inleiding.startswith("Кop 0") and "Первый абзац статьи номер 0" in sputnik[0].kop_inleiding
    assert "неповторимая аннотация" in items["ria.ru"].kop_inleiding


def test_a_site_name_in_the_title_is_stripped_in_any_script():
    artikelen = [_artikel("nabd.com", f"اخبار لبنان | خبر رقم {i} عن البرلمان", taal="Arabic") for i in range(3)]
    assert [i.kop for i in nt.items(artikelen)] == [f"خبر رقم {i} عن البرلمان" for i in range(3)]


def test_two_articles_sharing_a_line_is_not_yet_boilerplate():
    """Twee artikelen met dezelfde lead kunnen hetzelfde verhaal zijn; pas
    vanaf drie is het de site."""
    artikelen = [_artikel("tsargrad.tv", f"Kop {i}", "Дело MH17 носит политический характер.") for i in range(2)]
    assert all("политический характер" in i.kop_inleiding for i in nt.items(artikelen))


def test_an_article_without_a_title_is_no_item_and_items_carry_their_check():
    artikelen = [_artikel("ria.ru", "", "", ""), _artikel("ria.ru", "Заголовок", claim="gfc-9", report="/report/y")]
    artikelen.append({**_artikel("ria.ru", "Мимо"), "bron": None})
    (item,) = nt.items(artikelen)
    assert (item.claim_id, item.bonnetje) == ("gfc-9", "https://euvsdisinfo.eu/report/y")


def test_the_report_splits_by_form_and_language():
    rijen = [nt.Uitslag("gfc-1", "ru", "ria.ru", "kop", "gevonden"),
             nt.Uitslag("gfc-1", "ru", "ria.ru", "kop+inleiding", "niets"),
             nt.Uitslag("gfc-2", "ar", "rt.com", "kop", "fout")]
    r = nt.rapport(rijen)
    assert r["per_vorm"]["kop"] == {"n": 2, "gevonden": 1, "verwant": 0, "fout": 1, "niets": 0}
    assert r["per_taal"]["ru"]["n"] == 2


def test_a_title_with_nothing_to_strip_stays_exactly_as_it_was():
    titel = "Главный вопрос года - роль США в крушении MH17"
    (item,) = nt.items([_artikel("tsargrad.tv", titel)])
    assert item.kop == titel
