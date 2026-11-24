"""De basisset van de leraarladder (PLAN #31.1, E8.S1): de regels die vóór het
bouwen vastlagen."""

from doublecheck import basisset


def test_a_red_check_is_false_a_green_one_true_and_the_rest_does_not_count():
    assert basisset.label_van_kant("rood") == "onwaar"
    assert basisset.label_van_kant("groen") == "waar"
    assert basisset.label_van_kant("midden") is None
    assert basisset.label_van_kant(None) is None


def test_pieces_of_the_same_case_always_land_in_the_same_half():
    a = basisset.stuk("S:https://a.example/1", "artikel", "sheffield", "onwaar", zaak="gfc-1")
    b = basisset.stuk("C:gfc-1", "tekst", "claimreview", "onwaar", zaak="gfc-1")
    assert a["helft"] == b["helft"]
    zonder = basisset.stuk("N1:pool:x", "webtekst", "stiltepool", "neutraal")
    assert zonder["helft"] in ("ontwikkel", "toets")


def test_a_piece_from_after_the_training_cutoff_is_fresh():
    assert basisset.stuk("C:gfc-2", "tekst", "claimreview", "onwaar", datum="2026-07-01")["vers"] is True
    assert basisset.stuk("C:gfc-3", "tekst", "claimreview", "onwaar", datum="2026-06-30")["vers"] is False
    assert basisset.stuk("C:gfc-4", "tekst", "claimreview", "onwaar")["vers"] is False


def test_sheffield_text_is_title_description_and_paragraphs_capped_without_markup():
    rij = {"titel": "  Kop  ", "beschrijving": "Een\nbeschrijving", "tekst": "x" * 3000}
    tekst = basisset.sheffield_tekst(rij)
    assert tekst.startswith("Kop\nEen beschrijving\n")
    assert len(tekst) == basisset.MAX_TEKENS
    assert basisset.sheffield_tekst({"titel": "", "beschrijving": "", "tekst": ""}) is None
    assert basisset.sheffield_tekst({"titel": "Kop", "fout": "403"}) is None


def test_the_sample_follows_the_languages_and_is_the_same_every_time():
    rijen = [{"taal": "en", "id": i} for i in range(80)] + [{"taal": "nl", "id": 100 + i} for i in range(20)]
    gekozen = basisset.steekproef_per_taal(rijen, 10, zaad=3001)
    assert sum(r["taal"] == "en" for r in gekozen) == 8 and sum(r["taal"] == "nl" for r in gekozen) == 2
    assert gekozen == basisset.steekproef_per_taal(rijen, 10, zaad=3001)


def test_the_set_counts_itself_by_kind_label_half_and_freshness():
    stukken = [basisset.stuk("C:gfc-1", "tekst", "claimreview", "onwaar", taal="en", datum="2026-08-01"),
               basisset.stuk("S:u", "artikel", "sheffield", "waar", taal="nl")]
    tel = basisset.telling(stukken)
    assert tel["per soort en label"] == {"tekst onwaar": 1, "artikel waar": 1}
    assert tel["vers"] == 1 and sum(tel["per helft"].values()) == 2
    assert tel["per taal"] == {"en": 1, "nl": 1}


def test_every_piece_gets_a_batch_safe_id_that_stays_the_same():
    stukken = [basisset.stuk("P2:https://x.example/a?b=c#gfc-1", "artikel", "p2", "onwaar")]
    basisset.nummer(stukken)
    assert stukken[0]["id"] == "b-000000"


def test_every_fresh_claim_is_in_and_the_sample_comes_on_top():
    onwaar = [{"claim_id": f"o{i}", "taal": "en", "datum": "2025-01-01"} for i in range(50)] + \
             [{"claim_id": "vers", "taal": "en", "datum": "2026-08-01"}]
    waar = [{"claim_id": "w1", "taal": "en", "datum": "2024-01-01"}]
    gekozen = basisset.kies_claims(onwaar, waar, n=5)
    ids = [r["claim_id"] for r, _ in gekozen]
    assert "vers" in ids and "w1" in ids and len(ids) == len(set(ids))
    assert dict((r["claim_id"], l) for r, l in gekozen)["w1"] == "waar"
