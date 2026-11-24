"""Zoeken bij randgevallen (PLAN #34.2y): wat een lezer als hetzelfde ziet, vindt hetzelfde, in de vijf talen van de
site; tussen aanhalingstekens precies wat er staat; en wat precies zo geschreven staat, komt bovenaan."""

import unicodedata

import pytest
from starlette.testclient import TestClient

from doublecheck import namen as nm
from doublecheck import publiceren as pb
from factiz_site import app as fa
from factiz_site import db
from factiz_site import randproef
from tests.schriften import PANEEL
from tests.test_publiceren import REGISTER, _check, _claim, _lab

TALEN = ("en", "nl", "de", "es", "fr")
LANG = ("Deze bewering is lang genoeg om voorbij de grens van tweehonderd tekens te lopen die de site van een zoekvraag "
        "leest, en het woord dat daar doorgesneden wordt heet onwaarschijnlijkheidsberekening, zodat de knip er midden in "
        "valt en de rest van de zin er nog achteraan komt.")


def _vijf(nl, en, de, es, fr):
    return {"nl": nl, "en": en, "de": de, "es": es, "fr": fr}


ZELENSKY = _vijf("Volodymyr Zelensky", "Volodymyr Zelenskyy", "Wolodymyr Selenskyj", "Volodímir Zelenski",
                 "Volodymyr Zelensky")
ZELENSKA = _vijf("Olena Zelenska", "Olena Zelenska", "Olena Selenska", "Olena Zelenska", "Olena Zelenska")
NAVO = _vijf("Noord-Atlantische Verdragsorganisatie", "NATO", "Nordatlantikvertragsorganisation", "OTAN",
             "Organisation du Traité de l'Atlantique Nord")
KYIV = _vijf("Kiev", "Kyiv", "Kiew", "Kiev", "Kiev")
MELINDA = _vijf("Melinda Gates", "Melinda Gates", "Melinda Gates", "Melinda French", "Melinda Gates")
SAIED = _vijf("Kais Said", "Kais Saied", "Kais Saied", "Kais Saied", "Kaïs Saïed")
WGO = _vijf("Wereldgezondheidsorganisatie", "World Health Organization", "Weltgesundheitsorganisation",
           "Organización Mundial de la Salud", "Organisation mondiale de la santé")
LEGER = _vijf("Strijdkrachten van de Filipijnen", "Armed Forces of the Philippines", "Streitkräfte der Philippinen",
             "Fuerzas Armadas de Filipinas", "Forces armées des Philippines")
LOEKASJENKO = _vijf("Aleksandr Loekasjenko", "Alexander Lukashenka", "Aljaksandr Lukaschenka", "Alejandro Lukashenka",
                    "Alexandre Loukachenko")
# De andere schrijfwijzen die Wikidata kent (PLAN #34.2z): wat helpt bij zoeken, en wat er niet bij mag
BIJNAMEN = {"Q3874799": ["President Zelenskiy", "Volodymyr Zelenskiy", "Wolodymyr Oleksandrowytsch Selenskyj"],
            "Q7184": ["NAVO", "O.T.A.N.", "North Atlantic Alliance", "Alianza Atlántica"],
            "Q1899": ["Kyjiw", "Capital", "Mother of Rus' cities"],
            "Q2866": ["Alexander Lukashenko", "Lukashenko Aleksandr Grigorevich", "Аляксандр Лукашэнка"],
            "Q7817": ["WHO", "OMS", "WGO", "World Health Organisation", "who.int", "Gesundheit"],
            "Q438061": ["AFP"]}
LANDEN = {"UA": _vijf("Oekraïne", "Ukraine", "Ukraine", "Ucrania", "Ukraine"),
          "IN": _vijf("India", "India", "Indien", "India", "Inde")}
THEMAS = [{"sleutel": "war", "naam": _vijf("Oorlog", "War", "Krieg", "Guerra", "Guerre"), "omschrijving": "x",
           "onderdelen": []}]

BEWERINGEN = {
    "biolab": ("A secret biolab was found near Kharkiv", "en"),
    "biolabs": ("The United States funds biolabs in Georgia", "en"),
    "biolabore": ("Amerikanische Biolabore stehen in Armenien", "de"),
    "biolaboratorios": ("Hay biolaboratorios estadounidenses en Ucrania", "es"),
    "impfstoff": ("Der Impfstoff verändert die DNA", "de"),
    "impfstoffe": ("Die Impfstoffe enthalten Graphen", "de"),
    "vaccine": ("The vaccine causes autism in children", "en"),
    "vaccines": ("Vaccines contain microchips", "en"),
    "election": ("L'élection présidentielle a été volée", "fr"),
    "elections": ("Les élections ont été truquées au Brésil", "fr"),
    "crime": ("The crime rate doubled last year", "en"),
    "crimea": ("Crimea voted to join Russia", "en"),
    "police": ("The police arrested a priest", "en"),
    "policy": ("The new policy bans cash", "en"),
    "kind": ("This kind of mask is useless", "en"),
    "kinder": ("Kinder bekommen kein Geld mehr", "de"),
    "coeur": ("Le cœur des vaccinés s'arrête", "fr"),
    "strasse": ("Die Straße wurde für Migranten gesperrt", "de"),
    "kilic": ("Kılıçdaroğlu seçimi kazandı", "tr"),
    "zelensky": ("Zelensky bought a villa in Florida", "en"),
    "selenskyj": ("Selenskyj kaufte eine Villa in Italien", "de"),
    "zelenski": ("Zelenski compró una mansión en Egipto", "es"),
    "zelenska": ("Olena Zelenska spent a million on jewellery", "en"),
    "kiew": ("Kiew wurde gestern bombardiert", "de"),
    "otan": ("La OTAN prepara la guerra", "es"),
    "ucrania": ("Ucrania vende armas a terroristas", "es"),
    "covid19": ("covid19 is a hoax", "en"),
    "covid-19": ("COVID-19 vaccines are poison", "en"),
    "coronavirus": ("Das Coronavirus ist erfunden", "de"),
    "corona-virus": ("Das Corona-Virus kommt aus dem Labor", "de"),
    "gates": ("Bill Gates wants to depopulate the world", "en"),
    "los": ("Gates signed the bill in secret", "en"),
    "yimiao": ("疫苗 含有芯片", "zh"),
    "yimiao2": ("新冠疫苗会改变基因", "zh"),
    "yiqing": ("新冠疫情是假的", "zh"),
    "lang": (LANG, "nl"),
    "hindi": ("यूक्रेन में गुप्त जैविक प्रयोगशालाएं हैं", "hi"),
    "frans": ("French farmers block the roads", "en"),
    "india1": ("India bans beef exports", "en"),
    "india2": ("India launched a rocket to the sun", "en"),
    "india3": ("Modi says India will ban cash", "en"),
    "indien_de": ("Indien verbietet Rindfleisch", "de"),
    "indien_nl": ("Indien je dit deelt, ben je medeplichtig", "nl"),
    "zelenskiy": ("Zelenskiy fled to London with his family", "en"),
    "navo": ("De NAVO bereidt een oorlog tegen Rusland voor", "nl"),
    "capital": ("The capital is empty tonight", "en"),
    "lukashenko": ("Lukashenko closed the border with Poland", "en"),
    "loukachenko": ("Loukachenko a fermé la frontière", "fr"),
    "loekasjenko": ("Loekasjenko sluit de grens met Litouwen", "nl"),
    "grigorevich": ("Grigorevich won the chess final", "en"),
    "who_caps": ("The WHO says masks do not work", "en"),
    "who_caps2": ("WHO admits the pandemic was planned", "en"),
    "oms": ("La OMS prohíbe la vacuna en los niños", "es"),
    "oms2": ("La OMS confirma cinco casos nuevos", "es"),
    "afp_leger1": ("The AFP killed rebels in Mindanao", "en"),
    "afp_leger2": ("The AFP bombed a school in Marawi", "en"),
    **{f"afp_bureau{i}": (f"AFP reported {i} fake videos this week", "en") for i in range(4)},
    "weltgesundheit": ("Die Weltgesundheitsorganisation verschweigt Todesfälle", "de"),
    "gesundheit": ("Gesundheit ist das Wichtigste im Leben", "de"),
    **{f"who_woord{i}": (f"The doctor who said {i} things was fired", "en") for i in range(6)},
    "saied1": ("Kais Saied dissolved parliament", "en"),
    "saied2": ("Kais Saied banned the opposition", "en"),
    **{f"said{i}": (f"The mayor said that number {i} was fine", "en") for i in range(25)},
}
# Vertalingen voor weergave: zo staat een bewering ook in andere talen in het register op woorden.
VERTALINGEN = {"nl": {"biolaboratorios": "Er zijn Amerikaanse biolaboratoria in Oekraïne"},
               "en": {"biolaboratorios": "There are US biolaboratories in Ukraine",
                      "ucrania": "Ukraine sells weapons to terrorists"}}


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    map_ = tmp_path_factory.mktemp("randgevallen")
    lab = _lab(map_)
    claims = {k: _claim(lab, i, tekst, taal=taal) for i, (k, (tekst, taal)) in enumerate(BEWERINGEN.items(), start=1)}
    for i, (k, c) in enumerate(claims.items(), start=1):
        redactie = {"selenskyj": "afp.com", "zelenska": "afp.com", "zelenski": "maldita.es", "frans": "afp.com",
                    "saied2": "afp.com", "loukachenko": "afp.com"}.get(k, "snopes.com")
        _check(lab, c, f"https://{redactie}/{k}", datum=f"2024-{1 + i % 12:02d}-{1 + i % 27:02d}", taal=BEWERINGEN[k][1])
    lab.commit()
    nr = {k: pb.nummer(v) for k, v in claims.items()}
    namen = {"namen": {
        "Q3874799": {"soort": "persoon", "namen": ZELENSKY, "wikis": 150,
                     "paginas": [nr["zelensky"], nr["selenskyj"], nr["zelenski"]]},
        "Q59321885": {"soort": "persoon", "namen": ZELENSKA, "wikis": 50, "paginas": [nr["zelenska"], nr["zelensky"]]},
        "Q7184": {"soort": "organisatie", "namen": NAVO, "wikis": 200, "paginas": [nr["otan"], nr["ucrania"]]},
        "Q1899": {"soort": "plaats", "namen": KYIV, "wikis": 200, "paginas": [nr["kiew"], nr["biolab"]]},
        "Q463877": {"soort": "persoon", "namen": MELINDA, "wikis": 70, "paginas": [nr["gates"], nr["frans"]]},
        "Q16120878": {"soort": "persoon", "namen": SAIED, "wikis": 50, "paginas": [nr["saied1"], nr["saied2"]]},
        "Q2866": {"soort": "persoon", "namen": LOEKASJENKO, "wikis": 150,
                  "paginas": [nr["lukashenko"], nr["loukachenko"], nr["loekasjenko"]]},
        "Q7817": {"soort": "organisatie", "namen": WGO, "wikis": 200, "paginas": [nr["who_caps"], nr["who_caps2"], nr["oms"]]},
        "Q438061": {"soort": "organisatie", "namen": LEGER, "wikis": 40, "paginas": [nr["afp_leger1"], nr["afp_leger2"]]}},
        "per_pagina": {nr["zelensky"]: ["Q3874799", "Q59321885"], nr["selenskyj"]: ["Q3874799"],
                       nr["zelenski"]: ["Q3874799"], nr["zelenska"]: ["Q59321885"], nr["otan"]: ["Q7184"],
                       nr["ucrania"]: ["Q7184"], nr["kiew"]: ["Q1899"], nr["biolab"]: ["Q1899"],
                       nr["gates"]: ["Q463877"], nr["frans"]: ["Q463877"], nr["saied1"]: ["Q16120878"],
                       nr["saied2"]: ["Q16120878"], nr["lukashenko"]: ["Q2866"], nr["loukachenko"]: ["Q2866"],
                       nr["loekasjenko"]: ["Q2866"], nr["who_caps"]: ["Q7817"], nr["who_caps2"]: ["Q7817"],
                       nr["oms"]: ["Q7817"], nr["afp_leger1"]: ["Q438061"], nr["afp_leger2"]: ["Q438061"]}}
    indeling = {nr["ucrania"]: {"thema": "war", "onderdeel": "", "tweede": "", "land": "UA"},
                nr["biolaboratorios"]: {"thema": "war", "onderdeel": "", "tweede": "", "land": "UA"},
                nr["india1"]: {"thema": "war", "onderdeel": "", "tweede": "", "land": "IN"}}
    vertalingen = {taal: {nr[k]: tekst for k, tekst in paren.items()} for taal, paren in VERTALINGEN.items()}
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(nm, "MIN_PAGINAS", 2)
        manifest = pb.bouw(lab, map_ / "uit", register=REGISTER, vaag=frozenset(), datum="2026-11-12", namen=namen,
                           indeling=indeling, themas=THEMAS, landen=LANDEN, vertalingen=vertalingen, vertaalmaker="proef",
                           naamvormen=BIJNAMEN)
    pub = db.Publicatie(manifest["bestand"])
    assert pub.afkortingen_klaar(30)
    return TestClient(fa.maak_app(manifest["bestand"]), follow_redirects=False), pub, nr, manifest["bestand"]


def _vind(pub, vraag):
    return set(pub.treffers(vraag))


def _rijen(client, vraag, taal="en", **extra):
    return [r["href"].rstrip("/").rsplit("/", 1)[-1] for r in client.post(f"/api/{taal}/zoek", data={"q": vraag, **extra}).json()["rijen"]]


# --- enkelvoud en meervoud ----------------------------------------------------------------------------------------

@pytest.mark.parametrize("vormen,doel", [
    (("biolab", "biolabs"), {"biolab", "biolabs"}),
    (("vaccine", "vaccines"), {"vaccine", "vaccines"}),
    (("Impfstoff", "Impfstoffe"), {"impfstoff", "impfstoffe"}),
    (("élection", "élections", "election"), {"election", "elections"}),
])
def test_the_singular_finds_what_the_plural_finds_and_back(site, vormen, doel):
    _, pub, nr, _ = site
    for vorm in vormen:
        assert {nr[k] for k in doel} <= _vind(pub, vorm), vorm


def test_what_is_written_exactly_so_comes_first(site):
    client, _, nr, _ = site
    assert _rijen(client, "biolab")[0] == nr["biolab"]
    assert _rijen(client, "biolabs")[0] == nr["biolabs"]
    assert _rijen(client, "vaccines")[0] == nr["vaccines"] and nr["vaccine"] in _rijen(client, "vaccines")
    # een andere volgorde blijft die volgorde
    assert _rijen(client, "biolab", sorteer="oud") == sorted(_rijen(client, "biolab", sorteer="oud"),
                                                              key=_rijen(client, "biolab", sorteer="oud").index)


@pytest.mark.parametrize("vraag,niet", [("crime", "crimea"), ("police", "policy"), ("kind", "kinder"),
                                        ("Zelensky", "zelenska"), ("Crimea", "crime"), ("policy", "police")])
def test_an_ending_never_joins_two_different_words(site, vraag, niet):
    _, pub, nr, _ = site
    assert nr[niet] not in _vind(pub, vraag)


def test_the_forms_of_a_word_are_plural_endings_only():
    assert {"vaccins", "vaccine", "vaccines"} <= db.vormen("vaccin")
    assert {"vaccin", "vaccine"} <= db.vormen("vaccines")
    assert {"laboratories"} <= db.vormen("laboratory") and "laboratory" in db.vormen("laboratories")
    assert "laboratoria" in db.vormen("laboratorium") and "reseaux" in db.vormen("reseau")
    assert "hopitaux" in db.vormen("hopital") and "hopital" in db.vormen("hopitaux")
    assert "impfstoffen" in db.vormen("impfstoff") and "wahlen" in db.vormen("wahl")
    for woord, vreemd in (("crime", "crimea"), ("crime", "crimee"), ("police", "policy"), ("late", "laten"),
                          ("pole", "polen"), ("kind", "kinder"), ("plan", "plane"), ("medium", "media"), ("datum", "data")):
        assert vreemd not in db.vormen(woord), (woord, vreemd)
    assert db.vormen("the") == set() and db.vormen("new") == set()      # te kort om te buigen


# --- samenstellingen ----------------------------------------------------------------------------------------------

def test_a_word_finds_the_longer_words_it_begins_while_they_are_few(site, monkeypatch):
    _, pub, nr, _ = site
    familie = {nr[k] for k in ("biolab", "biolabs", "biolabore", "biolaboratorios")}
    assert familie <= _vind(pub, "biolab") and familie <= _vind(pub, "biolabs")
    assert {nr["biolabore"], nr["biolaboratorios"]} <= _vind(pub, "Biolabor")
    # met veel langere woorden blijft het bij het woord en zijn vormen
    monkeypatch.setattr(db, "FAMILIE", 2)
    assert _vind(pub, "biolab") == {nr["biolab"], nr["biolabs"]}


def test_written_together_with_a_hyphen_or_apart_is_the_same(site):
    _, pub, nr, _ = site
    for vraag in ("Coronavirus", "Corona-Virus"):
        assert {nr["coronavirus"], nr["corona-virus"]} <= _vind(pub, vraag), vraag
    for vraag in ("COVID-19", "covid19", "covid-19"):
        assert {nr["covid19"], nr["covid-19"]} <= _vind(pub, vraag), vraag


# --- accenten en bijzondere letters -------------------------------------------------------------------------------

@pytest.mark.parametrize("vraag,k", [("coeur", "coeur"), ("cœur", "coeur"), ("Strasse", "strasse"), ("Straße", "strasse"),
                                     ("Kilicdaroglu", "kilic"), ("Kılıçdaroğlu", "kilic")])
def test_letters_people_type_otherwise_find_the_same_without_a_correction(site, vraag, k):
    client, pub, nr, _ = site
    assert _vind(pub, vraag) == {nr[k]}
    assert client.post("/api/fr/zoek", data={"q": vraag}).json()["verbeterd"] is None


# --- namen --------------------------------------------------------------------------------------------------------

def test_every_spelling_of_a_name_the_register_knows_finds_the_others(site):
    _, pub, nr, _ = site
    for vraag in ("Zelensky", "Zelenskyy", "Selenskyj", "Zelenski"):
        assert {nr["zelensky"], nr["selenskyj"], nr["zelenski"]} <= _vind(pub, vraag), vraag
    for vraag in ("Kyiv", "Kiev", "Kiew"):
        assert nr["kiew"] in _vind(pub, vraag), vraag
    assert nr["otan"] in _vind(pub, "NATO")
    # een land: wie Oekraïne typt, vindt ook de bewering zonder Nederlandse vertaling
    assert {nr["ucrania"], nr["biolaboratorios"]} <= _vind(pub, "Oekraïne")
    # de echtgenote is een ander mens
    assert nr["zelenska"] not in _vind(pub, "Selenskyj")


def test_a_spelling_that_is_also_an_ordinary_word_never_joins_a_name(site):
    _, pub, nr, _ = site
    # een achternaam die in een andere taal een ander woord is: Melinda Gates heet in het Spaanse register Melinda French
    assert nr["frans"] not in _vind(pub, "Gates") and nr["gates"] not in _vind(pub, "French")
    # een schrijfwijze die veel vaker voorkomt dan de naam zelf, is een gewoon woord: Said bij Saied
    assert _vind(pub, "Saied") == {nr["saied1"], nr["saied2"]}
    # alleen naar de schrijfwijze die vaker voorkomt: Indien vindt India, maar India niet het Nederlandse indien (als)
    assert {nr["india1"], nr["india2"], nr["india3"]} <= _vind(pub, "Indien")
    assert _vind(pub, "India") == {nr["india1"], nr["india2"], nr["india3"]}


def test_a_spelling_wikidata_knows_finds_the_name_although_the_register_writes_it_otherwise(site):
    """PLAN #34.2z: de bijnamen van een naam doen mee als de andere schrijfwijzen in het register."""
    _, pub, nr, _ = site
    zelensky = {nr["zelensky"], nr["selenskyj"], nr["zelenski"], nr["zelenskiy"]}
    assert zelensky <= _vind(pub, "Zelenskiy") and nr["zelenskiy"] in _vind(pub, "Zelensky")
    assert nr["zelenska"] not in _vind(pub, "Zelenskiy")                         # de echtgenote blijft een ander mens
    for vraag in ("Lukashenko", "Lukashenka", "Loukachenko"):
        assert {nr["lukashenko"], nr["loukachenko"], nr["loekasjenko"]} <= _vind(pub, vraag), vraag


def test_a_surname_far_from_the_most_common_joins_through_one_in_between(site):
    # Loekasjenko lijkt niet genoeg op Lukashenka, wel op Loukachenko, en dat lijkt op Lukashenka
    _, pub, nr, _ = site
    assert {nr["lukashenko"], nr["loukachenko"], nr["loekasjenko"]} <= _vind(pub, "Loekasjenko")


def test_an_acronym_in_capitals_joins_its_organisation(site):
    _, pub, nr, _ = site
    assert {nr["navo"], nr["otan"]} <= _vind(pub, "NAVO") and nr["navo"] in _vind(pub, "OTAN")


def test_a_nickname_that_is_another_word_never_joins_the_name(site):
    _, pub, nr, _ = site
    # Capital bij Kyiv lijkt op geen enkele naam van één woord en is geen afkorting
    assert nr["capital"] not in _vind(pub, "Kyiv") and nr["kiew"] not in _vind(pub, "capital")
    # bij een persoon telt alleen een achternaam die op de andere lijkt: niet de vadersnaam, niet een ander schrift
    assert nr["grigorevich"] not in _vind(pub, "Lukashenko") and nr["lukashenko"] not in _vind(pub, "Grigorevich")


@pytest.mark.parametrize("vorm, telt", [("NAVO", True), ("OTAN", True), ("Kyjiw", True), ("Capital", False),
                                        ("Géorg.", False), ("Brés.", False), ("O.T.A.N.", False), ("NATO Alliance", False),
                                        ("UN", False), ("", False)])
def test_a_nickname_of_an_organisation_or_place_counts_only_as_one_word_in_capitals_or_like_a_name(vorm, telt):
    # een afkorting met een punt lijkt zonder die punt op iets anders: Géorg. op de voornaam Georg, bij Georgië
    enkel = {"Géorg.": ["Georgia", "Georgië", "Géorgie"], "Brés.": ["Brazil", "Brésil", "Brasil"]}.get(
        vorm, ["NATO", "Kyiv", "Kiev", "Kiew"])
    assert db.bijnaam_telt(vorm, enkel) is telt


def test_a_nickname_is_for_searching_and_never_on_a_page(site):
    client, _, nr, _ = site
    for pad in ("/api/en/naam/Q3874799", f"/api/en/factcheck/{nr['selenskyj']}", "/api/en/namen"):
        assert "Zelenskiy" not in client.get(pad).text, pad
    assert "Volodymyr Zelenskyy" in client.get("/api/en/naam/Q3874799").text


# --- een afkorting in hoofdletters is een naam (PLAN #34.2ab) ----------------------------------------------------------

WHO_PAGINAS = ("who_caps", "who_caps2", "oms", "oms2", "weltgesundheit")


def test_an_acronym_typed_in_capitals_finds_the_organisation_in_every_language_and_not_the_word(site):
    _, pub, nr, _ = site
    gevonden = _vind(pub, "WHO")
    # de pagina's bij de naam, de volledige naam in een andere taal, en OMS in hoofdletters (die staat vooral bij de WHO)
    assert {nr[k] for k in WHO_PAGINAS} <= gevonden
    # niet het Engelse woord who, en geen bijnaam van één woord die op geen naam lijkt
    assert not {nr[f"who_woord{i}"] for i in range(6)} & gevonden and nr["gesundheit"] not in gevonden
    assert _vind(pub, "OMS") == gevonden and _vind(pub, "WGO") == gevonden


def test_an_acronym_that_in_capitals_mostly_means_something_else_stays_the_word(site):
    # AFP is ook het leger van de Filipijnen, maar in hoofdletters staat het hier vooral voor het persbureau
    _, pub, nr, _ = site
    assert {nr["afp_leger1"], nr["afp_leger2"], *(nr[f"afp_bureau{i}"] for i in range(4))} <= _vind(pub, "AFP")
    assert pub.afkorting("AFP") is None and all(i.get("nummer") != "Q438061" for i in pub.ingangen("AFP", "en"))


@pytest.mark.parametrize("tekst, gevonden", [
    ("The WHO says masks are useless", {"WHO"}), ("WHO's chief resigned", {"WHO"}), ("La ONU dice que no", {"ONU"}),
    ("THE WHO SAYS MASKS ARE USELESS", set()), ("UN HOMBRE MATA A SU VECINO", set()), ("OMSzorg en WHOOP", set()),
    ("Signed by the UN and the EU", {"UN", "EU"})])
def test_an_acronym_counts_in_capitals_only_on_its_own_and_not_in_a_headline_in_capitals(tekst, gevonden):
    assert db.los_in_hoofdletters(tekst, {"WHO", "ONU", "UN", "EU", "OMS"}) == gevonden


def test_in_small_letters_or_between_quotes_an_acronym_stays_the_word(site):
    _, pub, nr, _ = site
    woord = {nr[f"who_woord{i}"] for i in range(6)}
    assert woord <= _vind(pub, "who") and woord <= _vind(pub, '"WHO"')
    assert nr["oms"] not in _vind(pub, "who")


def test_an_acronym_together_with_a_word_needs_both(site):
    _, pub, nr, _ = site
    assert _vind(pub, "WHO masks") == {nr["who_caps"]}


def test_a_word_in_capitals_that_is_no_acronym_of_a_name_is_just_the_word(site):
    _, pub, nr, _ = site
    assert _vind(pub, "VACCINES") == _vind(pub, "vaccines") and nr["vaccines"] in _vind(pub, "VACCINES")


def test_an_acronym_that_is_the_whole_question_shows_the_name_as_entry(site):
    _, pub, _, _ = site
    eerste = pub.ingangen("WHO", "nl")[0]
    assert eerste["soort"] == "naam" and eerste["nummer"] == "Q7817" and eerste["naam"] == "Wereldgezondheidsorganisatie"
    assert all(i.get("nummer") != "Q7817" for i in pub.ingangen("who", "nl"))


# --- hoofdletters en aanhalingstekens -----------------------------------------------------------------------------

def test_capitals_never_matter(site):
    _, pub, _, _ = site
    assert _vind(pub, "BIOLAB") == _vind(pub, "biolab") == _vind(pub, "bIoLaB")


@pytest.mark.parametrize("vraag", ['"biolab"', "“biolab”", "«biolab»", "„biolab“", "« biolab »"])
def test_quotes_mean_exactly_this_word(site, vraag):
    client, pub, nr, _ = site
    assert _vind(pub, vraag) == {nr["biolab"]}
    r = client.post("/api/en/zoek", data={"q": vraag}).json()
    assert r["totaal"] == 1 and any(stuk == ["biolab", True] for stuk in r["rijen"][0]["stukken"])


def test_quotes_around_more_words_mean_these_words_in_a_row(site):
    _, pub, nr, _ = site
    assert _vind(pub, '"Bill Gates"') == {nr["gates"]}
    assert _vind(pub, "Bill Gates") == {nr["gates"], nr["los"]}
    assert _vind(pub, '"bill gates" depopulate') == {nr["gates"]}
    # een aanhalingsteken zonder zijn partner is een gewoon teken
    assert _vind(pub, 'Bill "Gates') == _vind(pub, "Bill Gates")
    assert db.zoekdelen('a "b c" d') == [("a", False), ("b c", True), ("d", False)]
    assert db.zoekdelen('"biolab"') == [("biolab", True)] and db.zoekdelen('x "y') == [("x", False), ("y", False)]


# --- kort en lang -------------------------------------------------------------------------------------------------

def test_one_or_two_characters_in_a_script_without_spaces_find_where_they_stand(site):
    _, pub, nr, _ = site
    assert _vind(pub, "疫苗") == {nr["yimiao"], nr["yimiao2"]}          # ook waar het als los woord staat
    assert _vind(pub, "疫") == {nr["yimiao"], nr["yimiao2"], nr["yiqing"]}


@pytest.mark.parametrize("vraag", ["a", "é", "EU", "5", "疫"])
def test_one_or_two_characters_get_an_answer_without_an_error(site, vraag):
    client, _, _, _ = site
    assert client.post("/api/en/zoek", data={"q": vraag}).status_code == 200


def test_a_long_pasted_claim_cut_inside_a_word_is_still_found_first(site):
    client, _, nr, _ = site
    assert LANG[db.MAX_VRAAG - 1].isalnum() and LANG[db.MAX_VRAAG].isalnum()      # de knip valt in een woord
    assert _rijen(client, LANG, taal="nl")[0] == nr["lang"]


# --- de filters en de markering -----------------------------------------------------------------------------------

@pytest.mark.parametrize("vraag", ["biolab", "Oekraïne", "Zelensky", "COVID-19", '"Bill Gates"'])
def test_the_count_at_each_filter_is_the_count_of_the_list_with_that_filter(site, vraag):
    _, pub, _, _ = site
    uit = pub.zoek_ruim(vraag)
    assert uit["zonder_filters"] == uit["totaal"] == len(pub.treffers(vraag))
    for soort, waarden in uit["facetten"].items():
        for waarde, aantal in waarden.items():
            assert pub.zoek_ruim(vraag, **{soort: waarde})["totaal"] == aantal, (vraag, soort, waarde)


def _gemarkeerd(client, vraag):
    rijen = client.post("/api/en/zoek", data={"q": vraag}).json()["rijen"]
    stukken = [s for rij in rijen for s in rij["stukken"] + ((rij.get("origineel") or {}).get("stukken") or [])]
    return {stuk for stuk, raak in stukken if raak}


def test_the_words_found_through_another_form_are_marked_whole(site):
    client, _, _, _ = site
    assert {"biolab", "biolabs", "Biolabore", "biolaboratorios", "biolaboratories"} <= _gemarkeerd(client, "biolab")
    assert {"Zelensky", "Selenskyj", "Zelenski"} <= _gemarkeerd(client, "Zelensky")
    assert {"Coronavirus", "Corona-Virus"} <= _gemarkeerd(client, "Coronavirus")
    assert fa.markeer("biolaboratorios en biolab", ["biolab*"]) == [("biolaboratorios", True), (" en ", False),
                                                                   ("biolab", True)]


# --- wat blijft ---------------------------------------------------------------------------------------------------

def test_a_word_with_vowel_signs_stays_whole_and_gets_no_latin_endings(site):
    _, pub, nr, _ = site
    assert _vind(pub, "जैविक") == {nr["hindi"]}
    for schrift, tekst in PANEEL.items():
        for stuk in tekst.split():
            vormen = db.vormen(stuk)
            assert all(v.isascii() and v.isalpha() for v in vormen), schrift
            if any(t.isalpha() and "LATIN" not in unicodedata.name(t, "") for t in stuk):
                assert vormen == set(), (schrift, stuk)
        pub.zoek_ruim(tekst)                                   # elk schrift krijgt een antwoord


def test_the_edge_case_trial_counts_its_cases_on_a_release(site):
    _, _, _, bestand = site
    uitslag = randproef.meet(bestand, lang=1)
    assert uitslag["totaal"] == len(uitslag["gevallen"]) and 0 <= uitslag["gehaald"] <= uitslag["totaal"]
    assert {g["groep"] for g in uitslag["gevallen"]} >= {"buiging", "samenstelling", "accent", "naam", "streepje",
                                                         "hoofdletters", "aanhalingstekens", "kort", "lang", "filters",
                                                         "snelheid"}
    filters = next(g for g in uitslag["gevallen"] if g["groep"] == "filters")
    assert filters["gehaald"], filters
