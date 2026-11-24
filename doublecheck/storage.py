"""SQLite-schema en verbinding voor claims, factchecks en fingerprints.

Het schema draagt de domeinregels die op opslagniveau afdwingbaar zijn:
url en datum van een factcheck zijn verplicht (DR1), elke fingerprint draagt
zijn modelversie (DR6), factchecks hangen via claim_id aan één claim (DR7),
en een bewaard artefact bestaat alleen mét toestemming, vervaldatum en
verwijdersleutel (DR9). Dat laatste is de enige uitzondering op DR3 en staat
daarom als CHECK in het schema, niet in applicatiecode.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS claim (
    claim_id       TEXT PRIMARY KEY,
    canonical_text TEXT NOT NULL,
    language       TEXT NOT NULL,
    -- Claims die dezelfde bewering doen delen één cluster (E2.S5, DR7).
    -- NULL = nog niet geclusterd; dan is de claim zijn eigen cluster.
    -- Wat de uitgever zei; `language` is onze beste inschatting (#12.6).
    language_reported TEXT NOT NULL DEFAULT '',
    cluster_id     TEXT,
    -- 1 = door het clusteren bekeken (#25.4). Nodig omdat `cluster_id IS NULL`
    -- twee dingen kan betekenen: nog niet bekeken, of bekeken en alleen gebleven.
    cluster_bekeken INTEGER NOT NULL DEFAULT 0 CHECK (cluster_bekeken IN (0, 1))
) STRICT;


CREATE TABLE IF NOT EXISTS factcheck (
    factcheck_id       INTEGER PRIMARY KEY,
    claim_id           TEXT NOT NULL REFERENCES claim(claim_id) ON DELETE CASCADE,
    publisher          TEXT NOT NULL,
    verdict_normalized TEXT NOT NULL,
    verdict_original   TEXT NOT NULL,
    url                TEXT NOT NULL,
    review_date        TEXT NOT NULL,
    language           TEXT NOT NULL,
    -- Waar dit record vandaan komt (#14.5). Bepaalt of het mee mag in
    -- een publieke uitgave: alleen CC BY-materiaal mag dat (15.3).
    source             TEXT NOT NULL DEFAULT '',
    UNIQUE (claim_id, url)
) STRICT;


CREATE TABLE IF NOT EXISTS fingerprint (
    fingerprint_id INTEGER PRIMARY KEY,
    claim_id       TEXT NOT NULL REFERENCES claim(claim_id) ON DELETE CASCADE,
    kind           TEXT NOT NULL CHECK (kind IN ('text', 'image')),
    model_version  TEXT NOT NULL,
    payload        BLOB NOT NULL,
    UNIQUE (claim_id, kind, model_version)
) STRICT;


-- Elke herimport legt zijn run vast (#22.2): het corpus is een geheugen, en
-- een geheugen dat stiekem groeit is net zo onbetrouwbaar als een dat
-- stilstaat. Wanneer, waarvandaan, hoeveel erbij, hoeveel geweigerd.
CREATE TABLE IF NOT EXISTS importrun (
    run_id               INTEGER PRIMARY KEY,
    gestart_op           TEXT NOT NULL,
    bron                 TEXT NOT NULL,
    nieuwe_claims        INTEGER NOT NULL,
    nieuwe_factchecks    INTEGER NOT NULL,
    bestaande_claims     INTEGER NOT NULL,
    duplicaat_factchecks INTEGER NOT NULL,
    nieuwe_fingerprints  INTEGER NOT NULL,
    geweigerd            INTEGER NOT NULL
) STRICT;


CREATE TABLE IF NOT EXISTS benchmark_run (
    run_id              INTEGER PRIMARY KEY,
    started_at          TEXT NOT NULL,
    text_match          REAL NOT NULL,
    text_related        REAL NOT NULL,
    image_same          INTEGER NOT NULL,
    model_version_text  TEXT NOT NULL,
    model_version_image TEXT NOT NULL,
    pairs               INTEGER NOT NULL,
    same_pairs          INTEGER NOT NULL,
    wrong_links         INTEGER NOT NULL,
    correct_matches     INTEGER NOT NULL,
    results_per_language TEXT NOT NULL
) STRICT;

CREATE TABLE IF NOT EXISTS benchmark_fout (
    fout_id          INTEGER PRIMARY KEY,
    run_id           INTEGER NOT NULL REFERENCES benchmark_run(run_id) ON DELETE CASCADE,
    language         TEXT NOT NULL,
    provenance       TEXT NOT NULL,
    is_same          INTEGER NOT NULL CHECK (is_same IN (0, 1)),
    target_claim_id  TEXT NOT NULL,
    matched_claim_id TEXT NOT NULL,
    similarity       REAL NOT NULL
) STRICT;


CREATE TABLE IF NOT EXISTS dispute (
    dispute_id          INTEGER PRIMARY KEY,
    created_at          TEXT NOT NULL,
    disputed_category   TEXT NOT NULL,
    dispute_text        TEXT NOT NULL,
    claim_id            TEXT,
    -- Fingerprints zijn geen artefacten en vallen niet onder DR3.
    text_model_version  TEXT,
    text_payload        BLOB,
    image_model_version TEXT,
    image_hash          TEXT,
    -- Het artefact: de enige uitzondering op DR3, en alleen onder DR9.
    consent_at          TEXT,
    artifact_expires_at TEXT,
    deletion_key_hash   TEXT,
    artifact_bytes      BLOB,
    artifact_mime       TEXT,
    -- DR9: een bewaard artefact bestaat alleen mét toestemming, vervaldatum
    -- én verwijdersleutel. Geen enkel codepad kan hier omheen.
    CHECK (
        artifact_bytes IS NULL
        OR (consent_at IS NOT NULL
            AND artifact_expires_at IS NOT NULL
            AND deletion_key_hash IS NOT NULL)
    )
) STRICT;


-- De toelating (B28, #25.29): staat deze rij er, dan is een claim alleen
-- vindbaar met een check van een host uit het uitgeversregister, en tonen
-- antwoorden alleen zulke checks. Een corpus uit `bootstrap` draagt haar; de
-- testdatabases van de suite niet, daar zijn de hosts verzonnen.
CREATE TABLE IF NOT EXISTS toelating (
    id    INTEGER PRIMARY KEY CHECK (id = 1),
    sinds TEXT NOT NULL
) STRICT;


-- Bonnetjes die blijven (#25.9): de laatste stand van elke check-link, per
-- adres (één link kan bij meer claims horen). Het oordeel staat in
-- `factcheck` en blijft, wat de link ook doet; deze tabel zegt alleen of de
-- bron nog bereikbaar is. Offline pas na twee dode waarnemingen met minstens
-- `[bonnetjes] offline_na_uren` ertussen (`bonnetjes.is_offline`).
CREATE TABLE IF NOT EXISTS linkstatus (
    url              TEXT PRIMARY KEY,
    uitkomst         TEXT NOT NULL CHECK (uitkomst IN ('levend', 'dood', 'zacht-dood', 'onduidelijk')),
    gecontroleerd_op TEXT NOT NULL,
    laatst_levend    TEXT,
    dood_sinds       TEXT,
    laatst_dood      TEXT,
    archief_url      TEXT,
    archief_datum    TEXT
) STRICT;


-- Waarmee de huidige clustertoewijzing gebouwd is (#12.3). Eén rij: clustering
-- is een toestand van de hele opslag, geen historie. Zonder deze rij is een
-- bestaande toewijzing van onbekende herkomst en dus onbruikbaar.
CREATE TABLE IF NOT EXISTS cluster_state (
    id            INTEGER PRIMARY KEY CHECK (id = 1),
    model_version TEXT NOT NULL,
    threshold     REAL NOT NULL,
    veto_version  TEXT NOT NULL DEFAULT ''
) STRICT;


CREATE TABLE IF NOT EXISTS testpair (
    testpair_id   INTEGER PRIMARY KEY,
    claim_id      TEXT NOT NULL REFERENCES claim(claim_id) ON DELETE CASCADE,
    is_same       INTEGER NOT NULL CHECK (is_same IN (0, 1)),
    provenance    TEXT NOT NULL,
    language      TEXT NOT NULL,
    model_version TEXT NOT NULL,
    payload       BLOB NOT NULL,
    numbers       TEXT NOT NULL DEFAULT '[]',
    negations     TEXT NOT NULL DEFAULT '[]',
    kind          TEXT NOT NULL DEFAULT 'text' CHECK (kind IN ('text', 'image')),
    -- Gedragsversie van de afleidingen in `numbers`/`negations` (#11.5).
    derivation_version TEXT NOT NULL DEFAULT '',
    -- Herkende taal van het artefact, leeg bij twijfel (#12.4).
    artefact_language TEXT NOT NULL DEFAULT ''
) STRICT;

-- Bronregister (#24.6, DR10): elke bron buiten de ClaimReview-feed draagt zijn
-- soort en licentie vóór de eerste import; `herverdeelbaar` zegt of zijn
-- records mee mogen in een publieke uitgave (15.3).
CREATE TABLE IF NOT EXISTS bron (
    bron_id         TEXT PRIMARY KEY,
    naam            TEXT NOT NULL CHECK (naam <> ''),
    soort           TEXT NOT NULL CHECK (soort IN
                      ('factchecker', 'overheid', 'tracker', 'onderzoek', 'platform')),
    licentie        TEXT NOT NULL CHECK (licentie <> ''),
    attributietekst TEXT NOT NULL CHECK (attributietekst <> ''),
    url             TEXT NOT NULL CHECK (url <> ''),
    herverdeelbaar  INTEGER NOT NULL CHECK (herverdeelbaar IN (0, 1))
) STRICT;

-- Actoren waaraan een claim wordt toegeschreven: een operatie, een outlet, een
-- netwerk, of het platform waarop ze verscheen (een post op X, #25.16).
-- Aliassen (Matryoshka = Operation Overload = Storm-1679) reconciliëren naar
-- één actor, zoals claims clusteren (E7.S3).
CREATE TABLE IF NOT EXISTS actor (
    actor_id TEXT PRIMARY KEY,
    naam     TEXT NOT NULL CHECK (naam <> ''),
    soort    TEXT NOT NULL CHECK (soort IN ('operatie', 'outlet', 'netwerk', 'platform'))
) STRICT;
CREATE TABLE IF NOT EXISTS actor_alias (
    sleutel  TEXT PRIMARY KEY,
    actor_id TEXT NOT NULL REFERENCES actor(actor_id) ON DELETE CASCADE
) STRICT;

-- Attributie als bonnetje (DR10): nooit zonder bron, datum, link en
-- bewijsniveau. De CHECKs staan hier zodat applicatiecode het niet kan
-- vergeten. Raakt categorie (DR4) noch consensustelling (DR7).
CREATE TABLE IF NOT EXISTS attributie (
    attributie_id INTEGER PRIMARY KEY,
    claim_id TEXT NOT NULL REFERENCES claim(claim_id) ON DELETE CASCADE,
    actor_id TEXT NOT NULL REFERENCES actor(actor_id),
    bron_id  TEXT NOT NULL REFERENCES bron(bron_id),
    datum    TEXT NOT NULL CHECK (datum <> ''),
    url      TEXT NOT NULL CHECK (url <> ''),
    niveau   TEXT NOT NULL CHECK (niveau IN ('waargenomen', 'toegeschreven')),
    grond    TEXT NOT NULL DEFAULT '',
    UNIQUE (claim_id, actor_id, bron_id, url)
) STRICT;
CREATE INDEX IF NOT EXISTS idx_attributie_claim ON attributie(claim_id);
"""


INDEXEN = """
CREATE INDEX IF NOT EXISTS idx_claim_cluster ON claim(cluster_id);
CREATE INDEX IF NOT EXISTS idx_factcheck_claim ON factcheck(claim_id);
-- Claimvarianten (#25.17): extra formuleringen van dezelfde claim, geschreven
-- door een taalmodel (vertalingen), elk met herkomst en de modelversie van
-- zijn vingerafdruk (DR6). Weg met de claim (CASCADE). De tekst blijft
-- bewaard, zodat een modelwissel opnieuw kan embedden zonder opnieuw te
-- genereren; de zoek gebruikt alleen de vingerafdruk.
CREATE TABLE IF NOT EXISTS claim_variant (
    variant_id     INTEGER PRIMARY KEY,
    claim_id       TEXT NOT NULL REFERENCES claim(claim_id) ON DELETE CASCADE,
    language       TEXT NOT NULL,
    text           TEXT NOT NULL,
    generator      TEXT NOT NULL,
    prompt_version TEXT NOT NULL,
    model_version  TEXT NOT NULL,
    payload        BLOB NOT NULL,
    UNIQUE (claim_id, language, text, model_version)
) STRICT;
CREATE INDEX IF NOT EXISTS idx_variant_claim ON claim_variant(claim_id);
CREATE INDEX IF NOT EXISTS idx_fingerprint_claim ON fingerprint(claim_id);
CREATE INDEX IF NOT EXISTS idx_benchmark_fout_run ON benchmark_fout(run_id);
CREATE INDEX IF NOT EXISTS idx_dispute_vervalt ON dispute(artifact_expires_at);
"""


def connect(path: str | Path) -> sqlite3.Connection:
    # check_same_thread=False: FastAPI draait sync-endpoints in een threadpool;
    # het sqlite3-module serialiseert statements zelf.
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


# Kolommen die ná de eerste versie van een tabel zijn toegevoegd. SQLite's
# `CREATE TABLE IF NOT EXISTS` raakt een bestaande tabel niet aan, dus zonder
# deze stap bereikt een schemawijziging een bestaande database nooit — en
# droppen is geen optie zodra er betwistingen in staan (DR9, B11).
_TOEGEVOEGDE_KOLOMMEN = (
    ("testpair", "numbers", "TEXT NOT NULL DEFAULT '[]'"),
    ("testpair", "negations", "TEXT NOT NULL DEFAULT '[]'"),
    ("testpair", "kind", "TEXT NOT NULL DEFAULT 'text'"),
    ("testpair", "derivation_version", "TEXT NOT NULL DEFAULT ''"),
    ("testpair", "artefact_language", "TEXT NOT NULL DEFAULT ''"),
    ("claim", "cluster_id", "TEXT"),
    # Met welke claimvarianten een run zocht (#25.17); leeg: zonder.
    ("benchmark_run", "variant_set", "TEXT NOT NULL DEFAULT ''"),
    ("claim", "language_reported", "TEXT NOT NULL DEFAULT ''"),
    ("factcheck", "source", "TEXT NOT NULL DEFAULT ''"),
    ("claim", "cluster_bekeken", "INTEGER NOT NULL DEFAULT 0"),
)


def _migreer(conn: sqlite3.Connection) -> None:
    """Voegt ontbrekende kolommen toe aan bestaande tabellen.

    Alleen additief: kolommen erbij, nooit data weg. Let op dat een zo
    gemigreerde kolom geen CHECK-constraint krijgt — SQLite kan die niet
    achteraf toevoegen. Verse databases krijgen het volledige schema.
    """
    bestaand = {
        rij["name"]
        for rij in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    for tabel, kolom, definitie in _TOEGEVOEGDE_KOLOMMEN:
        if tabel not in bestaand:
            continue
        aanwezig = {
            rij["name"] for rij in conn.execute(f"PRAGMA table_info({tabel})")
        }
        if kolom not in aanwezig:
            conn.execute(f"ALTER TABLE {tabel} ADD COLUMN {kolom} {definitie}")
    conn.commit()
    _verruim_actorsoorten(conn)


def _verruim_actorsoorten(conn: sqlite3.Connection) -> None:
    """De actorsoort `platform` (#25.16) in een database van daarvóór.

    Een CHECK verruimen kan SQLite niet ter plekke; de tabel wordt opnieuw
    opgebouwd volgens de procedure van SQLite zelf (verwijzingen even uit,
    nieuwe tabel, rijen over, hernoemen, verwijzingen controleren). Geen rij
    gaat verloren, en een tweede keer doet niets."""
    rij = conn.execute("SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'actor'").fetchone()
    if rij is None or "'platform'" in rij[0]:
        return
    conn.commit()
    conn.execute("PRAGMA foreign_keys = OFF")
    try:
        conn.execute("BEGIN")
        conn.execute(
            "CREATE TABLE actor_nieuw (actor_id TEXT PRIMARY KEY,"
            " naam TEXT NOT NULL CHECK (naam <> ''),"
            " soort TEXT NOT NULL CHECK (soort IN ('operatie', 'outlet', 'netwerk', 'platform'))) STRICT"
        )
        conn.execute("INSERT INTO actor_nieuw (actor_id, naam, soort) SELECT actor_id, naam, soort FROM actor")
        conn.execute("DROP TABLE actor")
        conn.execute("ALTER TABLE actor_nieuw RENAME TO actor")
        kapot = conn.execute("PRAGMA foreign_key_check").fetchall()
        if kapot:
            raise sqlite3.IntegrityError(f"verwijzingen kapot na het verruimen van actor: {kapot[:3]}")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.execute("PRAGMA foreign_keys = ON")


def init_schema(conn: sqlite3.Connection) -> None:
    # Volgorde is wezenlijk: tabellen, dan ontbrekende kolommen, dan pas de
    # indexen — een index op een kolom die de migratie nog moet toevoegen
    # laat `executescript` op een bestaande database stuklopen.
    conn.executescript(SCHEMA)
    _migreer(conn)
    conn.executescript(INDEXEN)


def save_text_fingerprint(conn: sqlite3.Connection, claim_id: str, fingerprint) -> None:
    """Slaat een TextFingerprint op; de modelversie reist verplicht mee (DR6)."""
    conn.execute(
        "INSERT INTO fingerprint (claim_id, kind, model_version, payload)"
        " VALUES (?, 'text', ?, ?)",
        (claim_id, fingerprint.model_version, fingerprint.vector.tobytes()),
    )


def save_variant(conn: sqlite3.Connection, claim_id: str, language: str, text: str,
                 generator: str, prompt_version: str, fingerprint) -> None:
    """Slaat een claimvariant op met herkomst; de modelversie reist mee (DR6)."""
    conn.execute(
        "INSERT OR REPLACE INTO claim_variant (claim_id, language, text, generator, prompt_version,"
        " model_version, payload) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (claim_id, language, text, generator, prompt_version, fingerprint.model_version,
         fingerprint.vector.tobytes()),
    )


def save_image_fingerprint(conn: sqlite3.Connection, claim_id: str, fingerprint) -> None:
    """Slaat een ImageFingerprint op; ook hier reist de modelversie mee (DR6)."""
    conn.execute(
        "INSERT INTO fingerprint (claim_id, kind, model_version, payload)"
        " VALUES (?, 'image', ?, ?)",
        (claim_id, fingerprint.model_version, fingerprint.hash_hex.encode("ascii")),
    )


def registreer_importrun(
    conn: sqlite3.Connection, *, gestart_op: str, bron: str, rapport,
    nieuwe_fingerprints: int,
) -> None:
    """Legt een herimportrun vast (#22.2). `rapport` is een ImportReport,
    duck-getypt zodat storage niet aan ingest hoeft te hangen."""
    conn.execute(
        "INSERT INTO importrun (gestart_op, bron, nieuwe_claims,"
        " nieuwe_factchecks, bestaande_claims, duplicaat_factchecks,"
        " nieuwe_fingerprints, geweigerd) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            gestart_op, bron, rapport.accepted_claims,
            rapport.accepted_factchecks, rapport.existing_claims,
            rapport.duplicate_factchecks, nieuwe_fingerprints,
            len(rapport.refusals),
        ),
    )
    conn.commit()


def importruns(conn: sqlite3.Connection, limit: int = 10) -> list[sqlite3.Row]:
    """De jongste herimportruns, nieuwste eerst."""
    return conn.execute(
        "SELECT * FROM importrun ORDER BY run_id DESC LIMIT ?", (limit,)
    ).fetchall()
