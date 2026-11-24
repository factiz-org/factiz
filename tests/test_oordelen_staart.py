"""De staart van onbekende oordelen (PLAN #25.3).

17.996 checks over 12.366 verschillende labels. Binnen de grenzen van #18.1:
alleen ondubbelzinnige oordeelwoorden, elke niet-Engelse regel met taal en
glos, geen nieuwe categorie, en geen regel die het oordeel uit de kop van een
vrije tekst plukt. Twijfelgevallen blijven onbekend tot een schaallegenda van
de uitgever zelf ze beslist.
"""

import pytest

from doublecheck.verdicts import VERTAALDE_LABELS, normalize_verdict


@pytest.mark.parametrize("label, verwacht", [
    ("خاطئ", "onwaar"), ("زائف", "onwaar"), ("كاذب", "onwaar"), ("مفبرك", "onwaar"),
    ("غير مثبت", "onbewezen"), ("صحيح جزئياً", "deels-waar"), ("غير صحيح جزئيا", "deels-waar"),
    ("Худал", "onwaar"), ("Төөрөгдүүлсэн", "misleidend"),
    ("yalan", "onwaar"), ("əsasən yanlış", "deels-waar"), ("মিছা", "onwaar"),
    ("Netočno, dezinformacija", "onwaar"), ("Verdad a medias", "deels-waar"),
    ("Fuera de contexto", "misleidend"), ("Insustentável", "onbewezen"),
    ("ஃபேக்ட் கிரஸண்டோ ரேட்டிங்: False", "onwaar"),
    ("The claim is false.", "onwaar"), ("This is false claim.", "onwaar"),
    ("This is misleading.", "misleidend"), ("False headline", "onwaar"),
    ("Wrong", "onwaar"), ("Inaccurate", "onwaar"), ("Not legit", "onwaar"),
    ("Unsupported", "onbewezen"), ("No basis", "onbewezen"),
    ("Lacks context", "misleidend"), ("Not the whole story", "misleidend"),
    ("Spins the facts", "misleidend"), ("Old video", "misleidend"),
])
def test_unambiguous_tail_labels_are_recognised(label, verwacht):
    assert normalize_verdict(label) == verwacht


@pytest.mark.parametrize("label", [
    "شاخ‌دار", "Nì", "Exagerado", "Subestimado", "Impreciso", "5", "1",
    "Three Pinocchios", "Pinocchio andante", "Flip-flop", "Explainer",
    "Contextualizando", "事實釐清", "Exaggerated",
])
def test_labels_that_need_a_judgement_stay_unknown(label):
    """Een verkeerd label geeft het oordeel van een uitgever verkeerd weer, en
    dat is erger dan géén label (DR1, #18.1)."""
    assert normalize_verdict(label) == "onbekend"


def test_every_translated_label_carries_language_and_gloss():
    for label, (categorie, taal, glos) in VERTAALDE_LABELS.items():
        assert taal and glos, label
