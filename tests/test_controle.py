"""Batchcontrole van teksten tegen bekend-weerlegde beweringen (#21.2, #21.5).

De bestaande primitief in een batch-jas (B17): geen nieuw resolverhart, wel een
nieuw product­oppervlak — N documenten erin, per document de treffers eruit,
mét stance (§56) en mét de bronnen. Lokaal, geen accountlaag, niets bewaard.

Na §59 is de jas hersneden, en deze tests bewaken de drie snedes:

- **De premise is een venster, geen losse zin** (§59c): op echte
  weerlegpagina's isoleert de splitser het claimcitaat ("Claim: …", "Says …",
  kopregels), en een losse herformulering entailt de claim. Met de buurzinnen
  in de premise leest de stance het oordeel mee — precies de conditie waarin
  §56 de motor mat.
- **De poort is de screening-drempel, niet de resolver-0,92** (§59d):
  modelparafrase landt op 0,63–0,87. De resolverdrempel hoort bij "is dit
  dezelfde claim?"; de screeningvraag heeft een eigen, gemeten poort
  (`screening_poort`), met de DR8-tegenspraakcheck als veto.
- **Weerlegt wint** (§56-val als productgedrag): een document dat de claim
  érgens ontkracht, vlagt hem nérgens — anders strippen we de journalistiek
  samen met de leugen. Twijfel versoepelt nooit.

Het rapport blijft een logboek (B17: auditspoor): modelversies, drempels,
corpusstand en tijdstip reizen mee. Fingerprinter en stance zijn injecteerbaar
zodat dit deterministisch toetst; de echte modellen zitten achter dezelfde
interface (§56 en §60 maten ze).
"""

from __future__ import annotations

import dataclasses
from datetime import datetime

import numpy as np
import pytest

from doublecheck.config import load_config
from doublecheck.controle import _zinnen, controleer_teksten
from doublecheck.embedding import TextFingerprint
from doublecheck.ingest import claim_id_for_text
from doublecheck.storage import connect, init_schema, save_text_fingerprint

CLAIM = "De zeespiegel daalt al tien jaar wereldwijd"


def _eenheid(richting):
    vector = np.asarray(richting, dtype=np.float32)
    vector = vector / np.linalg.norm(vector)
    vector.setflags(write=False)
    return vector


@pytest.fixture
def conn():
    config = load_config()
    conn = connect(":memory:")
    init_schema(conn)
    claim_id = claim_id_for_text(CLAIM)
    conn.execute(
        "INSERT INTO claim (claim_id, canonical_text, language) VALUES (?, ?, 'nl')",
        (claim_id, CLAIM),
    )
    conn.execute(
        "INSERT INTO factcheck (claim_id, publisher, verdict_normalized,"
        " verdict_original, url, review_date, language, source) VALUES"
        " (?, 'Nieuwscheckers', 'onwaar', 'Onjuist',"
        " 'https://nieuwscheckers.nl/zeespiegel', '2024-03-14', 'nl',"
        " 'datacommons-ccby')",
        (claim_id,),
    )
    save_text_fingerprint(
        conn, claim_id,
        TextFingerprint(_eenheid([1.0, 0.0, 0.0]), config.model_versions.text_embedding),
    )
    conn.commit()
    yield conn
    conn.close()


def _nep_fingerprinter(teksten, model_version):
    """Letterlijke zinnen landen op de claimvector (gelijkenis 1,0); een
    parafrase ("zeewater") midden tussen de screening-poort en de
    resolverdrempel, uit de config; al het andere staat haaks.

    Eerst stond de parafrase vast op 0,8. Toen de poort onder bge-m3 naar
    0,82 ging (§77) viel ze eronder, terwijl het mechanisme klopte. Het
    midden van het venster volgt de config; valt het venster ooit dicht
    (poort op of boven de resolverdrempel), dan faalt de test alsnog."""
    drempels = load_config().thresholds
    midden = (drempels.screening_poort + drempels.text_match) / 2
    uit = []
    for tekst in teksten:
        laag = tekst.lower()
        if "zeespiegel" in laag:
            richting = [1.0, 0.0, 0.0]
        elif "zeewater" in laag:
            richting = [midden, (1 - midden**2) ** 0.5, 0.0]
        else:
            richting = [0.0, 0.0, 1.0]
        uit.append(TextFingerprint(_eenheid(richting), model_version))
    return uit


def _nep_stance(premise, hypothese):
    """Deterministische stand-in voor §56: een oordeel in de premise maakt het
    weerleggen; anders beweert claimtaal, en zwijgt de rest."""
    laag = premise.lower()
    if "onjuist" in laag or "niet waar" in laag:
        return 0.01, 0.98
    if "zeespiegel" in laag or "zeewater" in laag:
        return 0.95, 0.01
    return 0.1, 0.1


def _controleer(conn, documenten, **overschrijf):
    return controleer_teksten(
        conn,
        documenten,
        fingerprinter=_nep_fingerprinter,
        stance=_nep_stance,
        **overschrijf,
    )


def test_a_sentence_asserting_a_known_claim_is_flagged(conn):
    rapport = _controleer(conn, [
        ("doc-1", f"Het weer was mooi vandaag. {CLAIM}, dat is inmiddels bekend."),
    ])
    (uitslag,) = rapport.documenten
    (treffer,) = uitslag.treffers
    assert treffer.stance == "beweert"
    assert treffer.claim_id == claim_id_for_text(CLAIM)
    assert treffer.claim_tekst == CLAIM
    assert treffer.similarity >= load_config().thresholds.screening_poort
    assert uitslag.beweert == (treffer,)
    # DR1: de bonnetjes reizen mee.
    (bron,) = treffer.bronnen
    assert bron.publisher == "Nieuwscheckers"
    assert bron.url.startswith("https://")
    assert bron.verdict_original == "Onjuist"


def test_a_debunking_sentence_is_reported_but_never_flagged(conn):
    """De §56-val als productgedrag: de weerlegger citeert de claim en wordt
    herkend — maar niet gevlagd. Anders strippen we de journalistiek."""
    rapport = _controleer(conn, [
        ("doc-2", "Het is niet waar dat de zeespiegel al tien jaar daalt."),
    ])
    (uitslag,) = rapport.documenten
    (treffer,) = uitslag.treffers
    assert treffer.stance == "weerlegt"
    assert uitslag.beweert == (), "een weerlegger mag nooit als 'beweert' gevlagd"


def test_a_quoted_claim_next_to_its_verdict_is_not_flagged(conn):
    """§59c, het mechanisme dat de precisie op nul zette: elk factcheckformat
    zet de claim-herformulering los vooraan ("Claim: …", "Says …"), en een
    losse herformulering entailt de claim. Het venster leest het oordeel mee
    — ook als dat oordeel als zin te kort is voor de kandidaatselectie."""
    rapport = _controleer(conn, [
        ("doc-7", f"De bewering: {CLAIM}. Onjuist."),
    ])
    (uitslag,) = rapport.documenten
    (treffer,) = uitslag.treffers
    assert treffer.stance == "weerlegt", "het venster moet het oordeel meelezen"
    assert uitslag.beweert == ()


def test_a_paraphrase_below_the_resolver_threshold_is_flagged(conn):
    """§59d, het mechanisme dat de recall op nul zette: modelparafrase landt
    onder de resolver-0,92. De screening-poort vangt haar wél, en de stance
    beslist."""
    config = load_config()
    rapport = _controleer(conn, [
        ("doc-8", "Het zeewater zakt al jaren overal ter wereld, dat ziet iedereen."),
    ])
    (uitslag,) = rapport.documenten
    (treffer,) = uitslag.treffers
    assert treffer.stance == "beweert"
    assert uitslag.beweert == (treffer,)
    # Precies het venster dat §59 miste: boven de poort, onder de resolverdrempel.
    assert treffer.similarity >= config.thresholds.screening_poort
    assert treffer.similarity < config.thresholds.text_match


def test_a_debunk_anywhere_in_the_document_wins(conn):
    """Weerlegt wint: een document dat de claim érgens ontkracht, vlagt hem
    nérgens — ook als een eerdere zin hem buiten het venster van het oordeel
    beweert. Twijfel versoepelt nooit."""
    doc = (
        f"{CLAIM}, dat is bekend. "
        "De zon scheen gisteren volop in de stad. "
        "De markt op het plein was druk vanmiddag. "
        "Verder gebeurde er vandaag bijzonder weinig. "
        "De redactie dook daarna het archief in. "
        "De redactie keek naar de zeespiegel en noemde de bewering onjuist. "
        "Tot zover dit korte overzicht."
    )
    rapport = _controleer(conn, [("doc-9", doc)])
    (uitslag,) = rapport.documenten
    stances = sorted(t.stance for t in uitslag.treffers)
    assert stances == ["beweert", "weerlegt"], "beide zinnen blijven zichtbaar in het logboek"
    assert uitslag.beweert == (), "de weerlegging elders in het document wint"


def test_mechanical_contradiction_blocks_candidacy(conn):
    """DR8 blijft het veto vóór de stance: een zin die de claim mechanisch
    tegenspreekt (negatieflip) is een ándere bewering, geen kandidaat."""
    def fp_met_negatie(teksten, model_version):
        uit = []
        for tekst in teksten:
            laag = tekst.lower()
            negaties = frozenset({"niet"}) if "niet" in laag else frozenset()
            richting = [1.0, 0.0, 0.0] if "zeespiegel" in laag else [0.0, 0.0, 1.0]
            uit.append(TextFingerprint(
                _eenheid(richting), model_version, negations=negaties))
        return uit

    rapport = controleer_teksten(
        conn,
        [("doc-10", "De zeespiegel daalt helemaal niet al tien jaar.")],
        fingerprinter=fp_met_negatie,
        stance=_nep_stance,
    )
    (uitslag,) = rapport.documenten
    assert uitslag.treffers == ()


def test_an_unrelated_document_yields_no_hits(conn):
    rapport = _controleer(conn, [
        ("doc-3", "Bananen bevatten vitamine C. De trein had vertraging."),
    ])
    (uitslag,) = rapport.documenten
    assert uitslag.treffers == ()
    assert uitslag.zinnen == 2


def test_the_report_is_an_audit_trail(conn):
    """B17: navolgbaar zonder ons te geloven — versies, drempels, corpusstand
    en tijdstip staan in het rapport zelf."""
    config = load_config()
    # Vervuiling zoals die écht in de feed zit (12,3% lege datums, en één
    # check uit "2923"): het logboek verzwijgt haar niet en herhaalt haar niet.
    for nummer, datum in enumerate(("", "2923-01-02")):
        conn.execute(
            "INSERT INTO factcheck (claim_id, publisher, verdict_normalized,"
            " verdict_original, url, review_date, language, source) VALUES"
            " (?, 'dpa', 'onwaar', 'Onjuist', ?, ?, 'nl', 'datacommons-ccby')",
            (claim_id_for_text(CLAIM), f"https://dpa.example/{nummer}", datum),
        )
    conn.commit()
    rapport = _controleer(conn, [("doc-4", CLAIM + ".")])
    assert rapport.model_versions["text"] == config.model_versions.text_embedding
    assert rapport.model_versions["nli"] == config.model_versions.nli
    assert rapport.thresholds["screening_poort"] == config.thresholds.screening_poort
    assert rapport.thresholds["stance_entailment"] == config.thresholds.stance_entailment
    assert rapport.corpus["claims"] == 1
    assert rapport.corpus["factchecks"] == 3
    # De corrupte datum wint de MAX niet, en de rommel wordt geteld — niet
    # weggemoffeld: een auditlogboek dat "2923" als nieuwste check meldt is
    # zelf niet te vertrouwen.
    assert rapport.corpus["nieuwste_check"] == "2024-03-14"
    assert rapport.corpus["zonder_geldige_datum"] == 2
    datetime.fromisoformat(rapport.gestart_op)  # geldig tijdstip of dit knalt
    # En het is serialiseerbaar tot het logboek dat de CLI wegschrijft.
    assert dataclasses.asdict(rapport)["documenten"][0]["treffers"]


def test_the_flag_threshold_comes_from_config(conn):
    """DR6: drempels uit config, nooit uit code. Boven de nep-entailment van
    0,95 geklemd wordt dezelfde zin 'overig' in plaats van 'beweert'."""
    config = load_config()
    streng = dataclasses.replace(
        config, thresholds=dataclasses.replace(config.thresholds, stance_entailment=0.99)
    )
    rapport = _controleer(conn, [("doc-5", CLAIM + ".")], config=streng)
    (uitslag,) = rapport.documenten
    assert uitslag.treffers[0].stance == "overig"
    assert uitslag.beweert == ()


def test_the_screening_gate_comes_from_config(conn):
    """DR6 voor de poort zelf: wie strenger screent, zet dat in config — de
    parafrase op 0,8 valt dan weer buiten de kandidaten."""
    config = load_config()
    streng = dataclasses.replace(
        config, thresholds=dataclasses.replace(config.thresholds, screening_poort=0.9)
    )
    rapport = _controleer(
        conn,
        [("doc-11", "Het zeewater zakt al jaren overal ter wereld, dat ziet iedereen.")],
        config=streng,
    )
    (uitslag,) = rapport.documenten
    assert uitslag.treffers == ()


def test_sentences_split_across_scripts():
    """Zinnen eindigen niet overal op een punt (schriftguard, §51)."""
    assert len(_zinnen("Eerste zin hier. Tweede zin daar!")) == 2
    assert len(_zinnen("中文的第一句话在这里。第二句话在这里！")) == 2
    assert len(_zinnen("هل هذا سؤال طويل بما يكفي؟ نعم هذا جواب كامل.")) == 2
    assert len(_zinnen("यह पहला पूरा वाक्य है। यह दूसरा पूरा वाक्य है।")) == 2
    # Geen zinseinde: de hele tekst is één zin, niet nul.
    assert _zinnen("een tekst zonder zinseinde") == ["een tekst zonder zinseinde"]


def test_a_mismatched_index_is_refused_loudly(conn):
    """DR6, zelfde regel als de resolver: nooit stil over modelversies heen."""
    from doublecheck.search import ModelVersionMismatchError

    conn.execute("DELETE FROM fingerprint")
    save_text_fingerprint(
        conn, claim_id_for_text(CLAIM),
        TextFingerprint(_eenheid([1.0, 0.0, 0.0]), "een-ander-model-v9"),
    )
    conn.commit()
    with pytest.raises(ModelVersionMismatchError):
        _controleer(conn, [("doc-6", CLAIM + ".")])


def test_a_claim_with_mixed_verdicts_is_never_flagged(conn):
    """B17 zegt "bekend-wéérlegde beweringen": de vlag vereist unaniem
    'onwaar'. Een claim die ook 'waar' of 'deels waar' kreeg is geen
    weerlegde claim, hoe hard een zin hem ook beweert (§60b). De treffer
    blijft wel in het logboek staan."""
    conn.execute(
        "INSERT INTO factcheck (claim_id, publisher, verdict_normalized,"
        " verdict_original, url, review_date, language, source) VALUES"
        " (?, 'AndereChecker', 'waar', 'Klopt',"
        " 'https://anderechecker.example/zee', '2024-05-01', 'nl',"
        " 'datacommons-ccby')",
        (claim_id_for_text(CLAIM),),
    )
    conn.commit()
    rapport = _controleer(conn, [("doc-12", CLAIM + ", dat is bekend.")])
    (uitslag,) = rapport.documenten
    (treffer,) = uitslag.treffers
    assert treffer.stance == "beweert"
    assert treffer.vlagbaar is False
    assert uitslag.beweert == ()


def test_a_question_shaped_claim_is_never_flagged(conn):
    """§60b: het corpus draagt vraagvormige claims ("Le niveau de la mer
    augmente-t-il … ?"). Een vraag is geen bewering, dus nooit een vlag."""
    config = load_config()
    vraag = "Daalt de zeespiegel al tien jaar wereldwijd overal?"
    vraag_id = claim_id_for_text(vraag)
    conn.execute(
        "INSERT INTO claim (claim_id, canonical_text, language) VALUES (?, ?, 'nl')",
        (vraag_id, vraag),
    )
    conn.execute(
        "INSERT INTO factcheck (claim_id, publisher, verdict_normalized,"
        " verdict_original, url, review_date, language, source) VALUES"
        " (?, 'Nieuwscheckers', 'onwaar', 'Onjuist',"
        " 'https://nieuwscheckers.nl/zeevraag', '2024-03-15', 'nl',"
        " 'datacommons-ccby')",
        (vraag_id,),
    )
    # De vraagclaim wint de zoek: eigen richting, dichter bij de testzin.
    save_text_fingerprint(
        conn, vraag_id,
        TextFingerprint(_eenheid([0.0, 1.0, 0.0]), config.model_versions.text_embedding),
    )
    conn.commit()

    def fp_naar_vraag(teksten, model_version):
        return [TextFingerprint(_eenheid([0.0, 1.0, 0.0]), model_version)
                for _ in teksten]

    rapport = controleer_teksten(
        conn, [("doc-13", "De zeespiegel zakt al tien jaar, overal.")],
        fingerprinter=fp_naar_vraag, stance=_nep_stance,
    )
    (uitslag,) = rapport.documenten
    (treffer,) = uitslag.treffers
    assert treffer.claim_id == vraag_id
    assert treffer.vlagbaar is False
    assert uitslag.beweert == ()


def test_a_known_factcheck_url_is_its_own_receipt(conn):
    """De bonnetjesregel (§60b): een document dat zélf de vastgelegde
    factcheck-URL van de gematchte claim is, wéérlegt die claim per
    definitie — geen NLI-oordeel nodig, het bonnetje is de grond."""
    rapport = _controleer(conn, [
        ("https://www.nieuwscheckers.nl/zeespiegel",
         f"De bewering: {CLAIM}, dat is bekend. Wij zochten het uit."),
    ])
    (uitslag,) = rapport.documenten
    (treffer,) = uitslag.treffers
    assert treffer.stance == "weerlegt"
    assert treffer.grond == "bron-url"
    assert uitslag.beweert == ()


def test_the_batch_check_searches_like_the_resolver_does(conn, monkeypatch):
    """#21.8: de controle zoekt met de claimvarianten precies wanneer de
    resolver dat doet (de schakelaar `[varianten] in_resolver`)."""
    import dataclasses

    import doublecheck.controle as controle
    from doublecheck.config import VariantSettings

    gezien = []
    monkeypatch.setattr(controle, "search_text", lambda c, fp, **kw: gezien.append(kw.get("varianten")) or [])
    for aan in (True, False):
        config = dataclasses.replace(load_config(), varianten=VariantSettings(in_resolver=aan))
        _controleer(conn, [("d", "Een zin die lang genoeg is om als kandidaat te tellen.")], config=config)
        assert gezien and set(gezien) == {aan}
        gezien.clear()


# --- De stance in de taal van de zin (#25.31) --------------------------------

ENGELS = "The sea level has been falling all over the world for ten years now"
VARIANT_EN = "Sea levels have been falling worldwide for a decade"


def _met_variant(conn, taal="en", tekst=VARIANT_EN):
    from doublecheck.storage import save_variant

    versie = load_config().model_versions.text_embedding
    save_variant(conn, claim_id_for_text(CLAIM), taal, tekst, "claude-haiku-5-5", "vertalingen-v1",
                 TextFingerprint(_eenheid([0.0, 1.0, 0.0]), versie))
    conn.commit()


def _engels_fingerprinter(teksten, model_version):
    """De Engelse zin landt op de Nederlandse claim, en is als Engels herkend."""
    return [TextFingerprint(_eenheid([1.0, 0.0, 0.0] if "sea level" in t.lower() else [0.0, 0.0, 1.0]),
                            model_version, language="en") for t in teksten]


def _stance_met(variant_oordeel):
    """Over twee talen heen ziet het model de claim (0,95); op de Engelse
    variant zegt het `variant_oordeel`."""
    gevraagd = []

    def stance(premise, hypothese):
        gevraagd.append(hypothese)
        if hypothese == VARIANT_EN:
            return variant_oordeel
        laag = premise.lower()
        return (0.95, 0.01) if "sea level" in laag or "zeespiegel" in laag else (0.1, 0.1)

    stance.gevraagd = gevraagd
    return stance


def _aan(aan=True):
    config = load_config()
    return dataclasses.replace(config, varianten=dataclasses.replace(config.varianten, stance_in_zinstaal=aan))


def test_a_cross_lingual_flag_must_also_hold_in_the_language_of_the_sentence(conn):
    _met_variant(conn)
    rapport = controleer_teksten(conn, [("doc-v1", ENGELS + ".")], config=_aan(),
                                 fingerprinter=_engels_fingerprinter, stance=_stance_met((0.2, 0.1)))
    (uitslag,) = rapport.documenten
    (treffer,) = uitslag.treffers
    assert treffer.crosslinguaal
    assert treffer.stance == "overig" and uitslag.beweert == ()
    assert treffer.entailment_zinstaal == 0.2
    assert rapport.regels == {"varianten": True, "stance_in_zinstaal": True}


def test_when_the_variant_agrees_the_flag_stays(conn):
    _met_variant(conn)
    rapport = controleer_teksten(conn, [("doc-v2", ENGELS + ".")], config=_aan(),
                                 fingerprinter=_engels_fingerprinter, stance=_stance_met((0.96, 0.01)))
    (uitslag,) = rapport.documenten
    assert uitslag.treffers[0].stance == "beweert" and len(uitslag.beweert) == 1


def test_without_a_variant_in_that_language_nothing_changes(conn):
    _met_variant(conn, taal="es", tekst="El nivel del mar baja en todo el mundo desde hace diez años")
    stance = _stance_met((0.2, 0.1))
    rapport = controleer_teksten(conn, [("doc-v3", ENGELS + ".")], config=_aan(),
                                 fingerprinter=_engels_fingerprinter, stance=stance)
    (uitslag,) = rapport.documenten
    assert uitslag.treffers[0].stance == "beweert"
    assert uitslag.treffers[0].entailment_zinstaal is None


def test_the_rule_is_off_unless_config_turns_it_on(conn):
    """Een andere stance-regel verandert wat de batchcontrole vlagt: dat
    besluit staat in config, niet in code (DR6)."""
    assert load_config().varianten.stance_in_zinstaal is False
    _met_variant(conn)
    rapport = controleer_teksten(conn, [("doc-v4", ENGELS + ".")], config=_aan(False),
                                 fingerprinter=_engels_fingerprinter, stance=_stance_met((0.2, 0.1)))
    assert rapport.documenten[0].treffers[0].stance == "beweert"


def test_a_same_language_pair_never_asks_a_variant(conn):
    _met_variant(conn, taal="nl", tekst="Overal ter wereld daalt de zeespiegel al tien jaar")
    stance = _stance_met((0.2, 0.1))
    rapport = controleer_teksten(conn, [("doc-v5", f"Iedereen weet het: {CLAIM}.")], config=_aan(),
                                 fingerprinter=_nep_fingerprinter, stance=stance)
    assert rapport.documenten[0].treffers[0].stance == "beweert"
    assert stance.gevraagd == [CLAIM]


# --- #21.7: bredere zoekopties voor de meting, standaard uit ----------------------

TWEEDE = "Het poolijs groeit sinds 2015 elk jaar"


def _met_tweede_claim(conn, richting):
    claim_id = claim_id_for_text(TWEEDE)
    conn.execute("INSERT INTO claim (claim_id, canonical_text, language) VALUES (?, ?, 'nl')", (claim_id, TWEEDE))
    conn.execute(
        "INSERT INTO factcheck (claim_id, publisher, verdict_normalized, verdict_original, url, review_date,"
        " language, source) VALUES (?, 'Nieuwscheckers', 'onwaar', 'Onjuist',"
        " 'https://nieuwscheckers.nl/poolijs', '2024-05-01', 'nl', 'datacommons-ccby')", (claim_id,))
    save_text_fingerprint(conn, claim_id, TextFingerprint(_eenheid(richting), load_config().model_versions.text_embedding))
    conn.commit()
    return claim_id


def _stance_alles_beweert(premise, hypothese):
    return 0.95, 0.01


def test_a_window_of_two_sentences_catches_a_claim_split_over_both(conn):
    """Een herschreven bewering staat vaak over twee zinnen; elk alleen lijkt
    niet op de claim, samen wel."""
    def fingerprinter(teksten, versie):
        return [TextFingerprint(_eenheid([1.0, 0.0, 0.0] if ("zeepeil" in t and "zakt" in t) else [0.0, 0.0, 1.0]),
                                versie) for t in teksten]

    document = [("doc", "Het zeepeil verandert opvallend. Het zakt al tien jaar overal.")]
    per_zin = controleer_teksten(conn, document, fingerprinter=fingerprinter, stance=_stance_alles_beweert)
    per_venster = controleer_teksten(conn, document, fingerprinter=fingerprinter, stance=_stance_alles_beweert,
                                     eenheid="venster2")
    assert per_zin.documenten[0].beweert == ()
    (vlag,) = per_venster.documenten[0].beweert
    assert vlag.claim_id == claim_id_for_text(CLAIM)
    assert per_venster.regels["eenheid"] == "venster2"


def test_more_candidates_per_unit_each_get_the_gate_and_the_stance(conn):
    tweede = _met_tweede_claim(conn, [0.97, 0.243, 0.0])
    document = [("doc", f"{CLAIM}, zegt men.")]
    een = controleer_teksten(conn, document, fingerprinter=_nep_fingerprinter, stance=_stance_alles_beweert)
    twee = controleer_teksten(conn, document, fingerprinter=_nep_fingerprinter, stance=_stance_alles_beweert, top=2)
    assert {t.claim_id for t in een.documenten[0].treffers} == {claim_id_for_text(CLAIM)}
    assert {t.claim_id for t in twee.documenten[0].treffers} == {claim_id_for_text(CLAIM), tweede}


def test_an_extra_candidate_source_still_has_to_pass_the_gate(conn):
    """Zoeken op woorden mag kandidaten aandragen; de poort en de stance
    beslissen nog steeds, op de gelijkenis van de eenheid met die claim."""
    dichtbij = _met_tweede_claim(conn, [0.97, 0.243, 0.0])
    document = [("doc", f"{CLAIM}, zegt men.")]
    rapport = controleer_teksten(conn, document, fingerprinter=_nep_fingerprinter, stance=_stance_alles_beweert,
                                 extra_kandidaten=lambda tekst: [dichtbij])
    assert dichtbij in {t.claim_id for t in rapport.documenten[0].treffers}

    ver = claim_id_for_text("Iets heel anders over vulkanen")
    conn.execute("INSERT INTO claim (claim_id, canonical_text, language) VALUES (?, 'Iets heel anders over vulkanen', 'nl')", (ver,))
    save_text_fingerprint(conn, ver, TextFingerprint(_eenheid([0.0, 1.0, 0.0]), load_config().model_versions.text_embedding))
    rapport = controleer_teksten(conn, document, fingerprinter=_nep_fingerprinter, stance=_stance_alles_beweert,
                                 extra_kandidaten=lambda tekst: [ver])
    assert ver not in {t.claim_id for t in rapport.documenten[0].treffers}


def test_the_default_check_leaves_the_measurement_options_off(conn):
    rapport = _controleer(conn, [("doc", f"{CLAIM}.")])
    assert "eenheid" not in rapport.regels and "top" not in rapport.regels


def test_a_reranker_gate_replaces_the_similarity_gate(conn):
    """#21.7 stap 3: de herordenaar leest zin en claim samen; zijn score is de
    poort. Een claim met een lage gelijkenis maar een hoge score komt door,
    een claim met een hoge gelijkenis maar een lage score niet."""
    laag = _met_tweede_claim(conn, [0.5, 0.866, 0.0])   # gelijkenis 0,5: onder elke gelijkenispoort
    document = [("doc", f"{CLAIM}, zegt men.")]

    def herordenaar(paren):
        return [0.95 if "poolijs" in claim.lower() else 0.01 for _, claim in paren]

    rapport = controleer_teksten(conn, document, fingerprinter=_nep_fingerprinter, stance=_stance_alles_beweert,
                                 top=2, herordenaar=herordenaar, herordenaar_poort=0.5)
    assert {t.claim_id for t in rapport.documenten[0].treffers} == {laag}
    assert rapport.regels["herordenaar_poort"] == 0.5
