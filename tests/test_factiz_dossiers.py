"""Dossiers op het platform (PLAN #33.6, SPECS E9.S7, DESIGN §4r): een verhaal of een netwerk, met een tijdlijn."""

import pytest
from starlette.testclient import TestClient

from doublecheck import dossiers as ds
from doublecheck import publiceren as pb
from factiz_site import app as fa
from tests.test_factiz_themas import LANDEN, THEMAS
from tests.test_publiceren import EU, REGISTER, _check, _claim, _lab

TALEN = ("en", "nl", "de", "es", "fr")
NAAM = {"nl": "Zelensky koopt luxe met westers geld", "en": "Zelensky buys luxury with Western money",
        "de": "Selenskyj kauft Luxus mit westlichem Geld", "es": "Zelenski compra lujo con dinero occidental",
        "fr": "Zelensky achète du luxe avec l’argent occidental"}
INLEIDING = {"nl": "Een verhaal dat sinds 2022 terugkomt.", "en": "A story that has kept coming back since 2022.",
             "de": "Eine Geschichte, die seit 2022 wiederkehrt.", "es": "Una historia que vuelve desde 2022.",
             "fr": "Une histoire qui revient depuis 2022."}
ONDERZOEK = {"nl": "Hoe het jachtverhaal het debat over steun bereikte", "en": "How the yacht story reached the aid debate",
             "de": "Wie die Jacht-Geschichte die Debatte erreichte", "es": "Cómo la historia del yate llegó al debate",
             "fr": "Comment l’histoire du yacht a atteint le débat"}
BESLUIT = {taal: f"Sancties <b>tegen</b> een zender ({taal})" for taal in TALEN}


def _pad(taal, pad):
    return pad if taal == "en" else f"/{taal}{pad}"


def _vijf(tekst):
    return {taal: f"{tekst} ({taal})" for taal in TALEN}


def _dossier(sleutel, nummers, *, soort="verhaal", status="akkoord", naam=None, inleiding=None, items=(), verwant=(),
             thema="war", onderdeel="ukraine", bron=None):
    ruw = {"soort": soort, "status": status, "thema": thema, "onderdeel": onderdeel, "verwant": list(verwant),
           "naam": naam or _vijf(sleutel), "inleiding": inleiding or _vijf("Alinea"),
           "nagelezen": {taal: False for taal in TALEN}, "item": [dict(i) for i in items]}
    if status == "akkoord":
        ruw["akkoord"] = '2026-11-12, PO: "ja, zo mag het"'
    if soort == "netwerk":
        ruw["vastgesteld"] = {"door": "EU DisinfoLab", "url": "https://www.disinfo.eu/doppelganger", "datum": "2022-09-27"}
    return ds.keur(sleutel, ruw, {"goedgekeurd_door": "PO", "datum": "2026-11-12",
                                  "factchecks": [{"nummer": n, **(bron or {})} for n in nummers]})


def _site(tmp_path_factory, met_dossiers=True, concepten=False):
    map_ = tmp_path_factory.mktemp("dossiers")
    lab = _lab(map_)
    n = {"villa": _claim(lab, 1, "Zelensky bought a villa in Florida"),
         "jacht": _claim(lab, 2, "Zelensky bought two yachts for 75 million dollars"),
         "hindi": _claim(lab, 3, "ज़ेलेंस्की ने एक कैसीनो खरीदा", taal="hi"),
         "zonder_datum": _claim(lab, 4, "Zelenska bought a Bugatti"),
         "biolab": _claim(lab, 5, "Ukraine hosts secret biolabs"),
         "los": _claim(lab, 6, "Garlic water cures covid")}
    _check(lab, n["villa"], "https://snopes.com/villa", datum="2024-03-05")
    _check(lab, n["villa"], "https://factcheck.afp.com/villa", datum="2022-04-01", taal="fr")
    _check(lab, n["jacht"], "https://maldita.es/jacht", datum="2023-12-01", taal="es")
    _check(lab, n["hindi"], "https://snopes.com/casino", datum="2024-06-07", taal="hi")
    _check(lab, n["zonder_datum"], "https://snopes.com/bugatti", datum="")
    _check(lab, n["biolab"], "https://euvsdisinfo.eu/report/biolab", bron=EU, datum="2022-03-10", eigen="Disinformation")
    _check(lab, n["los"], "https://snopes.com/garlic", datum="2021-01-01")
    lab.commit()
    nr = {k: pb.nummer(v) for k, v in n.items()}
    items = [{"soort": "onderzoek", "datum": "2023-12-20", "bron": "BBC Verify", "url": "https://www.bbc.com/news/x",
              "titel": ONDERZOEK},
             {"soort": "besluit", "datum": "2025-02-01", "bron": "Council of the EU", "url": "https://europa.eu/sancties",
              "titel": BESLUIT}]
    toeschrijving = {"niveau": "toegeschreven", "bron": "EUvsDisinfo", "url": "https://euvsdisinfo.eu/report/biolab"}
    verhaal = _dossier("zelensky-luxury", [nr["villa"], nr["jacht"], nr["hindi"], nr["zonder_datum"]], naam=NAAM,
                       inleiding=INLEIDING, items=items, verwant=["doppelganger"])
    for f in verhaal["factchecks"]:
        if f["nummer"] in (nr["villa"], nr["jacht"], nr["hindi"]):
            f["versie"] = "een-aankoop"
    dossiers = [
        verhaal,
        _dossier("doppelganger", [nr["biolab"], nr["jacht"]], soort="netwerk", bron=toeschrijving, thema="health",
                 onderdeel="", verwant=["zelensky-luxury"]),
        _dossier("in-de-maak", [nr["los"]], status="concept", thema="health", onderdeel="covid")]
    indeling = {nr["villa"]: {"thema": "war", "onderdeel": "ukraine", "tweede": "", "land": "UA"},
                nr["los"]: {"thema": "health", "onderdeel": "covid", "tweede": "", "land": ""}}
    manifest = pb.bouw(lab, map_ / "uit", register=REGISTER, vaag=frozenset(), datum="2026-11-11",
                       indeling=indeling, themas=THEMAS, landen=LANDEN,
                       vertalingen={"nl": {nr["hindi"]: "Zelensky kocht een casino"},
                                    "en": {nr["hindi"]: "Zelensky bought a casino"}}, vertaalmaker="proef",
                       dossiers=dossiers if met_dossiers else None, concepten=concepten,
                       # #34.2o en #34.2p: de vertaalde woorden van een redactie, en lijkt op (de jacht is al een versie
                       # van de villa in het dossier en hoort dus niet bij Lijkt op)
                       glossen={"False": {"en": "False", "nl": "Onwaar", "de": "Falsch", "es": "Falso", "fr": "Faux"}},
                       lijkt_op={nr["villa"]: [nr["biolab"], nr["jacht"]]},
                       # #34.2bp: dezelfde bewering bij een andere redactie (de villa en de jacht delen geen redactie)
                       zelfde={nr["villa"]: [nr["jacht"]], nr["jacht"]: [nr["villa"], nr["los"]], nr["los"]: [nr["jacht"]]},
                       # #34.2cf: de zoekvraag, ook in het Hindi, een lange (de omschrijving valt terug) en een zonder datum
                       zoekvragen={
                           nr["villa"]: {"taal": "en", "bron": "Zelensky bought a villa in Florida",
                                         "vraag": "Did Zelensky buy a villa in Florida?", "onderwerp": "Zelensky's villa"},
                           nr["hindi"]: {"taal": "hi", "bron": "ज़ेलेंस्की ने एक कैसीनो खरीदा",
                                         "vraag": "क्या ज़ेलेंस्की ने एक कैसीनो खरीदा?", "onderwerp": "ज़ेलेंस्की और कैसीनो"},
                           nr["los"]: {"taal": "en", "bron": "Garlic water cures covid",
                                       "vraag": "Is it true that garlic water cures covid, as a long message that keeps going round "
                                                "in family chats claims, with recipes and a list of doctors?",
                                       "onderwerp": "Garlic water and covid"},
                           nr["zonder_datum"]: {"taal": "en", "bron": "Zelenska bought a Bugatti",
                                                "vraag": "Did Zelenska buy a Bugatti?", "onderwerp": "Zelenska and a Bugatti"}})
    client = TestClient(fa.maak_app(manifest["bestand"]), follow_redirects=False)
    client.bestand = manifest["bestand"]        # voor de vergelijking met de TypeScript-kant (#34.2bo)
    return client, nr


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    return _site(tmp_path_factory)


@pytest.fixture(scope="module")
def kaal(tmp_path_factory):
    return _site(tmp_path_factory, met_dossiers=False)


@pytest.fixture(scope="module")
def voorbeeld(tmp_path_factory):
    return _site(tmp_path_factory, concepten=True)


@pytest.mark.parametrize("taal", TALEN)
def test_the_overview_names_every_dossier_with_its_kind_in_the_language_of_the_site(site, taal):
    client, _ = site
    r = client.get(f"/api/{taal}/dossiers")
    assert r.status_code == 200
    kaarten = {d["sleutel"]: d for d in r.json()["dossiers"]}
    assert set(kaarten) == {"zelensky-luxury", "doppelganger"} and "in-de-maak" not in r.text   # een concept: in geen uitgave
    assert kaarten["zelensky-luxury"]["naam"] == NAAM[taal]
    assert kaarten["zelensky-luxury"]["href"] == _pad(taal, "/dossiers/zelensky-luxury/")
    assert kaarten["doppelganger"]["href"] == _pad(taal, "/dossiers/doppelganger/")
    soort = {"en": ("Story", "Network"), "nl": ("Verhaal", "Netwerk"), "de": ("Erzählung", "Netzwerk"),
             "es": ("Relato", "Red"), "fr": ("Récit", "Réseau")}[taal]
    assert (kaarten["zelensky-luxury"]["soort_tekst"], kaarten["doppelganger"]["soort_tekst"]) == soort


@pytest.mark.parametrize("taal", TALEN)
def test_a_dossier_opens_with_its_kind_its_name_and_one_paragraph_in_the_language_of_the_site(site, taal):
    client, _ = site
    d = client.get(f"/api/{taal}/dossier/zelensky-luxury").json()
    assert d["naam"] == NAAM[taal] and d["inleiding"] == INLEIDING[taal]
    assert d["soort"] == "verhaal" and d["soort_tekst"] == {"en": "Story", "nl": "Verhaal", "de": "Erzählung",
                                                             "es": "Relato", "fr": "Récit"}[taal]
    # hetzelfde dossier bestaat in de andere talen
    for ander in TALEN:
        assert client.get(f"/api/{ander}/dossier/zelensky-luxury").json()["sleutel"] == "zelensky-luxury"


def test_where_we_stand_is_counted_from_the_database(site):
    client, _ = site
    # vier factchecks; de eerste check is van AFP op 1 april 2022; drie redacties (Snopes, AFP, Maldita); talen en,
    # fr, es en hi; de laatste aanvulling is het besluit van 1 februari 2025
    assert client.get("/api/en/dossier/zelensky-luxury").json()["stand"] == {
        "eerste": "1 April 2022", "factchecks": "4", "redacties": "3", "talen": "4", "laatste": "1 February 2025"}
    nl = client.get("/api/nl/dossier/zelensky-luxury").json()["stand"]
    assert nl["eerste"] == "1 april 2022" and nl["laatste"] == "1 februari 2025"


def _regels(d):
    return [r for j in d["jaren"] for r in j["regels"]]


def test_the_timeline_runs_per_year_with_the_newest_on_top_and_every_item_names_its_kind(site):
    client, n = site
    d = client.get("/api/en/dossier/zelensky-luxury").json()
    assert [j["kop"] for j in d["jaren"]] == ["2025", "2024", "2023", "2022", "Date unknown"]
    regels = _regels(d)
    tekst = [r["rij"]["tekst"] if r.get("rij") else r["titel"] for r in regels]
    for i, stuk in enumerate(("Sancties", "casino", "How the yacht story reached", "two yachts", "villa in Florida", "Bugatti")):
        assert stuk in tekst[i], (i, stuk, tekst)
    assert [r["soort_tekst"] for r in regels] == ["Decision", "Fact-check", "Research", "Fact-check", "Fact-check", "Fact-check"]
    # een factcheck linkt naar zijn pagina, met het label en de redactie; de villa staat op de dag van haar eerste check
    villa = regels[4]
    assert villa["rij"]["href"] == f"/fact-checks/{n['villa']}/" and villa["rij"]["tekst"] == "Zelensky bought a villa in Florida"
    assert villa["datum"] == "1 April 2022" and villa["rij"]["label"] == "Known to be false"
    assert villa["rij"]["redacties"] == ["AFP", "Snopes"] and villa["soort"] == "factcheck"
    # een item van buiten linkt naar zijn bron
    onderzoek = regels[2]
    assert onderzoek["url"] == "https://www.bbc.com/news/x" and onderzoek["bron"] == "BBC Verify"
    assert onderzoek["datum"] == "20 December 2023"


def test_text_in_a_dossier_stays_plain_text_and_a_claim_keeps_its_translation_and_its_original(site):
    client, n = site
    regels = _regels(client.get("/api/nl/dossier/zelensky-luxury").json())
    # de tekst zoals de redactie haar schreef, als tekst: het ontsnappen doet de voorkant
    assert next(r for r in regels if r["soort"] == "besluit")["titel"] == "Sancties <b>tegen</b> een zender (nl)"
    # de Hindi bewering staat er met de Nederlandse vertaling voorop en het origineel eronder (B32)
    hindi = next(r["rij"] for r in regels if r.get("rij") and r["rij"]["nummer"] == n["hindi"])
    assert hindi["href"] == f"/nl/fact-checks/{n['hindi']}/" and hindi["tekst"] == "Zelensky kocht een casino"
    assert hindi["taal"] == "nl" and hindi["origineel"]["taal"] == "hi"
    assert hindi["origineel"]["tekst"] == "ज़ेलेंस्की ने एक कैसीनो खरीदा"
    assert hindi["origineel"]["regel"].startswith("Machinevertaling uit het Hindi")


def test_a_network_dossier_names_who_identified_it_and_every_fact_check_names_its_source_and_level(site):
    client, _ = site
    d = client.get("/api/en/dossier/doppelganger").json()
    assert d["soort_tekst"] == "Network"
    assert d["vastgesteld"] == {"door": "EU DisinfoLab", "datum": "27 September 2022", "url": "https://www.disinfo.eu/doppelganger"}
    regels = _regels(d)
    assert [r.get("niveau") for r in regels] == ["Attributed to this network by EUvsDisinfo"] * 2
    assert [r.get("url") for r in regels] == ["https://euvsdisinfo.eu/report/biolab"] * 2
    # een verhaaldossier noemt geen vaststeller en geen toeschrijving
    verhaal = client.get("/api/en/dossier/zelensky-luxury").json()
    assert verhaal["vastgesteld"] is None and not any("niveau" in r for r in _regels(verhaal))


def test_a_dossier_refers_to_its_theme_and_to_related_dossiers(site):
    client, _ = site
    d = client.get("/api/nl/dossier/zelensky-luxury").json()
    assert d["thema"] == {"naam": "Oorlog en conflict", "href": "/nl/themes/war/"}
    assert d["onderdeel"] == {"naam": "Rusland en Oekraïne", "href": "/nl/themes/war/ukraine/"}
    assert d["verwant"] == [{"sleutel": "doppelganger", "naam": "doppelganger (nl)", "href": "/nl/dossiers/doppelganger/"}]
    assert client.get("/api/nl/dossier/doppelganger").json()["onderdeel"] is None        # het netwerk heeft geen onderdeel


def test_an_unknown_or_malformed_dossier_is_not_found(site):
    client, _ = site
    for fout in ("/api/en/dossier/bestaat-niet", "/api/en/dossier/Zelensky-Luxury", "/api/en/dossier/in-de-maak",
                 "/api/en/dossier/zelensky-luxury/x", "/api/en/dossier/..%2Fthemes", "/api/nl/dossier/" + "a" * 80):
        assert client.get(fout).status_code == 404, fout


def test_a_fact_check_says_which_dossier_it_is_part_of_and_one_outside_a_dossier_says_nothing(site):
    client, n = site
    # het verhaal én het netwerk, het verhaal eerst
    assert client.get(f"/api/en/factcheck/{n['jacht']}").json()["dossiers"] == [
        {"sleutel": "zelensky-luxury", "naam": NAAM["en"], "href": "/dossiers/zelensky-luxury/"},
        {"sleutel": "doppelganger", "naam": "doppelganger (en)", "href": "/dossiers/doppelganger/"}]
    nl = client.get(f"/api/nl/factcheck/{n['villa']}").json()["dossiers"]
    assert nl == [{"sleutel": "zelensky-luxury", "naam": NAAM["nl"], "href": "/nl/dossiers/zelensky-luxury/"}]
    los = client.get(f"/api/en/factcheck/{n['los']}")
    assert los.json()["dossiers"] == [] and "/dossiers/" not in los.text           # het concept telt niet


def test_a_theme_lists_its_dossiers_and_a_part_only_those_of_that_part(site):
    client, _ = site
    for pad, sleutels in (("war", ["zelensky-luxury"]), ("war/ukraine", ["zelensky-luxury"]),
                          ("health", ["doppelganger"]), ("health/covid", [])):     # het netwerk heeft geen onderdeel
        assert [d["sleutel"] for d in client.get(f"/api/en/thema/{pad}").json()["dossiers"]] == sleutels, pad
    assert client.get("/api/en/thema/war").json()["dossiers"][0]["href"] == "/dossiers/zelensky-luxury/"


def test_the_first_page_leads_to_the_dossiers(site):
    client, _ = site
    kaarten = client.get("/api/nl/archief").json()["dossiers"]
    zelensky = next(d for d in kaarten if d["sleutel"] == "zelensky-luxury")
    assert zelensky["href"] == "/nl/dossiers/zelensky-luxury/" and zelensky["naam"].startswith("Zelensky koopt luxe")


def test_a_file_without_dossiers_gives_a_site_without_dossiers_that_still_works(kaal):
    client, n = kaal
    assert client.get("/api/en/dossiers").status_code == 404
    assert client.get("/api/en/dossier/zelensky-luxury").status_code == 404
    for pad in ("/api/en/archief", f"/api/en/factcheck/{n['villa']}", "/api/en/thema/war", "/api/en/themas"):
        r = client.get(pad)
        assert r.status_code == 200 and "/dossiers/" not in r.text, pad
    assert client.get("/api/en/archief").json()["dossiers"] == []


def test_a_draft_is_only_in_a_preview_and_says_so(voorbeeld, site):
    client, n = voorbeeld
    r = client.get("/api/nl/dossier/in-de-maak")
    assert r.status_code == 200 and r.json()["concept"] is True
    nl = {d["sleutel"]: d for d in client.get("/api/nl/dossiers").json()["dossiers"]}
    assert nl["in-de-maak"]["concept"] is True and nl["in-de-maak"]["concept_tekst"] == "Concept, niet gepubliceerd"
    en = {d["sleutel"]: d for d in client.get("/api/en/dossiers").json()["dossiers"]}
    assert en["in-de-maak"]["concept_tekst"] == "Draft, not published"
    assert en["zelensky-luxury"]["concept"] is False and en["zelensky-luxury"]["concept_tekst"] == ""
    assert client.get("/api/en/dossier/zelensky-luxury").json()["concept"] is False
    assert "/dossiers/in-de-maak/" in [d["href"] for d in client.get(f"/api/en/factcheck/{n['los']}").json()["dossiers"]]
    echt, _ = site
    assert "Draft, not published" not in echt.get("/api/en/dossiers").text
    assert not any(d["concept"] for d in echt.get("/api/en/dossiers").json()["dossiers"])


def test_every_dossier_answer_carries_the_policy_and_never_a_cookie(site):
    client, _ = site
    for pad in ("/api/en/dossiers", "/api/de/dossier/zelensky-luxury", "/api/en/dossier/bestaat-niet"):
        h = client.get(pad).headers
        assert "default-src 'none'" in h["content-security-policy"] and "set-cookie" not in h, pad
        assert h["x-content-type-options"] == "nosniff" and h["referrer-policy"] == "strict-origin-when-cross-origin", pad


def test_a_fact_check_shows_the_other_fact_checks_of_its_version_under_also_appears_as_with_a_count(site):
    client, n = site
    v = client.get(f"/api/en/factcheck/{n['villa']}").json()["varianten"]
    # de versie telt vier checks (de villa twee, het jacht en het casino elk één) in vier talen: en, fr, es en hi
    assert v["telling"] == "The same message was checked 4 times, in 4 languages."
    assert [r["href"] for r in v["rijen"]] == [f"/fact-checks/{n['jacht']}/", f"/fact-checks/{n['hindi']}/"]  # op datum, zonder zichzelf
    jacht, hindi = v["rijen"]
    assert jacht["tekst"].startswith("Zelensky bought two yachts") and jacht["label"] == "Known to be false"
    # elke rij zegt wie het natrok, in welke taal en wanneer voor het eerst: zo is te zien dat het bericht rondging
    assert (jacht["redactienamen"], jacht["taal_eigen"], jacht["eerste"]) == (["Maldita"], "English", "1 December 2023")
    assert (hindi["redactienamen"], hindi["taal_eigen"], hindi["eerste"]) == (["Snopes"], "हिन्दी", "7 June 2024")
    # een bewering in een andere taal staat er met haar vertaling en haar origineel (B32)
    assert hindi["tekst"] == "Zelensky bought a casino" and hindi["origineel"]["taal"] == "hi"
    assert hindi["origineel"]["tekst"] == "ज़ेलेंस्की ने एक कैसीनो खरीदा"
    nl = client.get(f"/api/nl/factcheck/{n['hindi']}").json()["varianten"]
    assert nl["telling"] == "Hetzelfde bericht is 4 keer nagetrokken, in 4 talen."


def test_a_fact_check_without_a_version_shows_no_such_block(site):
    client, n = site
    for sleutel in ("zonder_datum", "los", "biolab"):       # in het dossier zonder versie, buiten elk dossier, in een netwerk
        assert client.get(f"/api/en/factcheck/{n[sleutel]}").json()["varianten"] is None, sleutel
