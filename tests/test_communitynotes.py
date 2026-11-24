"""Community Notes als signaal en brug (PLAN #25.15).

Niet als corpus: de ruwe data valt onder X's voorwaarden en wordt niet
doorgegeven. Wel als meting: hoeveel notes worden behulpzaam, in welke talen,
en welke behulpzame notes linken naar een check in ons corpus (de brug tussen
een echte virale post en onze claim). Gelezen rechtstreeks uit de zips.
"""

import zipfile

from doublecheck import communitynotes as cn
from doublecheck.storage import connect, init_schema


def _zip(pad, naam, kop, rijen):
    with zipfile.ZipFile(pad / f"{naam}.zip", "w") as z:
        z.writestr(f"{naam}.tsv", "\t".join(kop) + "\n" + "\n".join("\t".join(r) for r in rijen) + "\n")


def test_helpful_notes_are_counted_and_bridged_to_our_checks(tmp_path):
    _zip(tmp_path, "noteStatusHistory-00000",
         ["noteId", "currentStatus", "timestampMillisOfCurrentStatus"],
         [["1", "CURRENTLY_RATED_HELPFUL", "1760000000000"],
          ["2", "NEEDS_MORE_RATINGS", "1760000000000"],
          ["3", "CURRENTLY_RATED_HELPFUL", "1760100000000"]])
    _zip(tmp_path, "notes-00000",
         ["noteId", "tweetId", "classification", "summary"],
         [["1", "111", "MISINFORMED_OR_POTENTIALLY_MISLEADING",
           "This video is from 2016. See https://www.factly.in/old-video-claim/ for details"],
          ["2", "222", "MISINFORMED_OR_POTENTIALLY_MISLEADING", "Not rated yet https://factly.in/x"],
          ["3", "333", "MISINFORMED_OR_POTENTIALLY_MISLEADING",
           "Contexto: el video es de Brasil. https://[broken"]])
    conn = connect(":memory:")
    init_schema(conn)
    conn.execute("INSERT INTO claim (claim_id, canonical_text, language) VALUES ('c1', 'x', 'en')")
    conn.execute("INSERT INTO factcheck (claim_id, publisher, verdict_normalized, verdict_original, url,"
                 " review_date, language) VALUES ('c1', 'FACTLY', 'onwaar', 'False',"
                 " 'https://factly.in/old-video-claim', '2024-01-01', 'en')")
    r = cn.meet(conn, tmp_path, factcheck_hosts={"factly.in"})
    assert r["behulpzaam"] == 2
    assert r["gelezen"] == 2
    assert r["met_factcheckdomein"] == 1
    assert r["bruggen"] == [("1", "111", "c1")]
    assert sum(r["per_week"].values()) == 2


def test_a_broken_url_in_a_note_never_stops_the_reading():
    assert cn.host_en_pad("https://[broken") == ("", "")
    assert cn.host_en_pad("https://www.Factly.in/Old-Video/).") == ("factly.in", "/old-video")


def test_a_bridge_becomes_a_dated_line_in_the_history_without_the_note_text(tmp_path):
    """#25.16, E7.S6: een behulpzame note die naar onze check verwijst, wordt
    "rondgegaan op X" met de datum van de note en een link naar de note. De
    notetekst blijft buiten de database (X Developer Agreement), en de bron
    maakt de database niet uitgeefbaar."""
    from datetime import datetime, timezone

    from doublecheck.attributie import attributies_voor
    from doublecheck.bootstrap import herkomstrapport

    geschreven = int(datetime(2025, 3, 15, 9, tzinfo=timezone.utc).timestamp() * 1000)
    _zip(tmp_path, "noteStatusHistory-00000", ["noteId", "currentStatus", "timestampMillisOfCurrentStatus"],
         [["1", "CURRENTLY_RATED_HELPFUL", "1760000000000"], ["2", "NEEDS_MORE_RATINGS", "1760000000000"]])
    _zip(tmp_path, "notes-00000", ["noteId", "tweetId", "classification", "createdAtMillis", "summary"],
         [["1", "111", "MISINFORMED_OR_POTENTIALLY_MISLEADING", str(geschreven),
           "This video is from 2016. See https://www.factly.in/old-video-claim/ for details"],
          ["2", "222", "MISINFORMED_OR_POTENTIALLY_MISLEADING", str(geschreven), "Not rated https://factly.in/old-video-claim"]])
    conn = connect(":memory:")
    init_schema(conn)
    conn.execute("INSERT INTO claim (claim_id, canonical_text, language) VALUES ('c1', 'x', 'en')")
    conn.execute("INSERT INTO factcheck (claim_id, publisher, verdict_normalized, verdict_original, url,"
                 " review_date, language, source) VALUES ('c1', 'FACTLY', 'onwaar', 'False',"
                 " 'https://factly.in/old-video-claim', '2024-01-01', 'en', 'datacommons-ccby')")
    assert cn.importeer(conn, tmp_path, factcheck_hosts={"factly.in"}) == 1
    regels = [(a.actor, a.actor_soort, a.bron, a.bron_soort, a.niveau, a.datum, a.url)
              for a in attributies_voor(conn, ["c1"])]
    assert regels == [("X", "platform", "Community Notes (X)", "platform", "waargenomen", "2025-03-15",
                       "https://x.com/i/birdwatch/n/1")]
    assert "This video is from 2016" not in "\n".join(conn.iterdump())
    assert cn.importeer(conn, tmp_path, factcheck_hosts={"factly.in"}) == 0     # nog eens: niets dubbel
    assert not herkomstrapport(conn).mag_uitgegeven_worden
