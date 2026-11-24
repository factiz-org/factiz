"""Notes voor beweringen die nog geen redactie checkte: de offline meting
(PLAN #25.16 d, PO 2026-10-12: eerst meten).

De vraag: vindt een bewering de behulpzame Community Note die erover gaat?
De bruggen (notes die naar onze check verwijzen) zijn de vragen met een
bekend antwoord; de notes blijven in een aparte map die nooit wordt
uitgegeven.
"""

import json
import zipfile

import numpy as np

from doublecheck import notesmeting as nm
from doublecheck.embedding import TextFingerprint
from doublecheck.storage import connect, init_schema, save_text_fingerprint

VERSIE = "testmodel-v1"


def _zip(pad, naam, kop, rijen):
    with zipfile.ZipFile(pad / f"{naam}.zip", "w") as z:
        z.writestr(f"{naam}.tsv", "\t".join(kop) + "\n" + "\n".join("\t".join(r) for r in rijen) + "\n")


def _v(*xs):
    v = np.array(xs, dtype=np.float32)
    return v / np.linalg.norm(v)


def test_a_note_is_read_without_its_links():
    assert nm.schoon("This photo is from 2016. https://factly.in/a-b/  See\nhttps://x.co/1") == \
        "This photo is from 2016. See"


def test_the_selection_takes_every_bridge_and_a_fixed_sample_of_other_helpful_notes(tmp_path):
    _zip(tmp_path, "noteStatusHistory-00000", ["noteId", "currentStatus", "timestampMillisOfCurrentStatus"],
         [[str(i), "CURRENTLY_RATED_HELPFUL" if i != 9 else "NEEDS_MORE_RATINGS", "1760000000000"]
          for i in range(1, 10)])
    _zip(tmp_path, "notes-00000", ["noteId", "tweetId", "classification", "createdAtMillis", "summary"],
         [["1", "11", "MISINFORMED_OR_POTENTIALLY_MISLEADING", "1700000000000",
           "Old video. https://factly.in/old-video-claim/"]]
         + [[str(i), str(i * 11), "MISINFORMED_OR_POTENTIALLY_MISLEADING", "1700000000000", f"Een note nummer {i}"]
            for i in range(2, 10)])
    conn = connect(":memory:")
    init_schema(conn)
    conn.execute("INSERT INTO claim (claim_id, canonical_text, language) VALUES ('c1', 'x', 'en')")
    conn.execute("INSERT INTO factcheck (claim_id, publisher, verdict_normalized, verdict_original, url,"
                 " review_date, language) VALUES ('c1', 'FACTLY', 'onwaar', 'False',"
                 " 'https://factly.in/old-video-claim', '2024-01-01', 'en')")
    regels = nm.selecteer(conn, tmp_path, factcheck_hosts={"factly.in"}, afleiders=3, zaad=1)
    assert len(regels) == 4                                   # de brug plus drie afleiders
    brug = [r for r in regels if r["brug"]]
    assert brug == [{"claim_id": "1", "post": "11", "brug": "c1",
                     "varianten": [{"taal": "", "tekst": "Old video."}]}]
    assert "9" not in {r["claim_id"] for r in regels}          # niet behulpzaam
    assert nm.selecteer(conn, tmp_path, factcheck_hosts={"factly.in"}, afleiders=3, zaad=1) == regels


def test_a_bridged_claim_finds_its_own_note_or_one_from_its_cluster():
    """Goed als de dichtstbijzijnde note verwijst naar de claim zelf of naar
    een claim in hetzelfde cluster; de rang telt over alle notes."""
    conn = connect(":memory:")
    init_schema(conn)
    for cid, cluster, richting in (("c1", "cl-1", (1, 0, 0)), ("c2", "cl-1", (0.9, 0.44, 0)), ("c3", None, (0, 0, 1))):
        conn.execute("INSERT INTO claim (claim_id, canonical_text, language, cluster_id) VALUES (?, ?, 'en', ?)",
                     (cid, cid, cluster))
        save_text_fingerprint(conn, cid, TextFingerprint(_v(*richting), VERSIE))
    rijen = [{"claim_id": "n1", "brug": "c2"}, {"claim_id": "n2", "brug": None}, {"claim_id": "n3", "brug": "c3"}]
    matrix = np.vstack([_v(0.98, 0.2, 0), _v(0, 0.3, 0.95), _v(0.1, 0.9, 0.42)])
    uit = nm.meet_bruggen(conn, rijen, matrix, VERSIE)
    assert uit["vragen"] == 2                                  # c2 en c3 hebben een brug
    assert uit["rang"] == {"c2": 1, "c3": 2}
    assert uit["bovenaan_goed"] == 1


def test_the_reranker_chooses_among_the_nearest_notes_not_the_embedding():
    """De embedding levert de kandidaten; de herordenaar kiest welke over de
    vraag gaat. Een algemene note die dichter ligt verliest het dan."""
    rijen = [{"claim_id": "n1", "brug": None, "varianten": [{"taal": "", "tekst": "This statement is fake."}]},
             {"claim_id": "n2", "brug": "c1", "varianten": [{"taal": "", "tekst": "Angola never banned Islam."}]},
             {"claim_id": "n3", "brug": None, "varianten": [{"taal": "", "tekst": "Iets heel anders."}]}]
    matrix = np.vstack([_v(1, 0.1, 0), _v(0.9, 0.4, 0), _v(0, 0, 1)])

    def score(paren):
        return [0.9 if "Angola" in note else 0.01 for _, note in paren]

    uit = nm.herorden_vragen([("c1", _v(1, 0, 0), "Angola has banned Islam")], rijen, matrix, score, k=2)
    assert uit == [{"vraag": "c1", "note": "n2", "brug": "c1", "score": 0.9, "plek": 2,
                    "gelijkenis": round(float(_v(1, 0, 0) @ _v(0.9, 0.4, 0)), 4)}]


def test_the_meedan_pairs_judge_the_reranker_against_human_labels():
    """Wat annotatoren "Very Similar" noemden, hoort de herordenaar boven de
    drempel te zetten; "N/A" (geen bewering, verkeerde taal) telt niet mee."""
    paren = [{"text1": "a", "text2": "a2", "majority_label": "Very Similar"},
             {"text1": "b", "text2": "b2", "majority_label": "Very Similar"},
             {"text1": "c", "text2": "c2", "majority_label": "Very Dissimilar"},
             {"text1": "d", "text2": "d2", "majority_label": "Somewhat Similar"},
             {"text1": "e", "text2": "e2", "majority_label": "N/A: One or both messages does not have a claim"},
             {"text1": "f", "text2": "f2", "majority_label": "No Majority"}]
    waarde = {"a": 0.95, "b": 0.4, "c": 0.8, "d": 0.6, "e": 0.99, "f": 0.99}

    def score(lijst):
        return [waarde[x[0]] if x[0] in waarde else waarde[x[1]] for x in lijst]

    uit = nm.meedan_toets(paren, score, drempels=(0.5,))
    assert uit["paren"] == 4
    assert uit["per_drempel"][0.5] == {"zeer_gelijk": 2, "gevonden": 1, "boven_drempel": 3,
                                       "waarvan_zeer_gelijk": 1, "waarvan_ongelijk": 1}
