"""Betwistingen vastleggen (E6.S3).

De enige route waar een artefact bewaard mág blijven — en alleen onder DR9:
expliciete toestemming, een vervaldatum en een intrekbare verwijdersleutel,
alle drie tegelijk. Het schema dwingt dat af; deze module levert de
toestemming aan of laat het artefact weg.

Zonder toestemming wordt uitsluitend vastgelegd wat geen artefact ís: de
fingerprints met hun modelversie, de betwiste categorie, de betwistingstekst
van de gebruiker en het tijdstip. Bij een tekstartefact betekent dat expliciet
dat de tekst zelf níét wordt opgeslagen — alleen zijn vector (DR3).
"""

from __future__ import annotations

import hashlib
import secrets
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone


@dataclass(frozen=True)
class DisputeRecord:
    dispute_id: int
    stored_artifact: bool
    artifact_expires_at: str | None
    deletion_key: str | None


def hash_deletion_key(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def record_dispute(
    conn: sqlite3.Connection,
    *,
    disputed_category: str,
    dispute_text: str,
    claim_id: str | None = None,
    text_fingerprint=None,
    image_fingerprint=None,
    artifact: bytes | None = None,
    artifact_mime: str | None = None,
    consent: bool = False,
    retention_days: int | None = None,
    now: datetime | None = None,
) -> DisputeRecord:
    """Legt een betwisting vast; het artefact alleen onder DR9.

    Bewaren gebeurt uitsluitend wanneer toestemming, een artefact én een
    bewaartermijn alle drie zijn meegegeven. Ontbreekt er één, dan wordt de
    betwisting gewoon vastgelegd zónder artefact — de veilige richting.
    """
    tijdstip = now or datetime.now(timezone.utc)
    moment = tijdstip.isoformat(timespec="seconds")

    bewaren = bool(consent and artifact is not None)
    if bewaren and not retention_days:
        # Zonder bewaartermijn kan DR9 niet worden nageleefd; dan liever
        # luidruchtig weigeren dan stilzwijgend zonder vervaldatum bewaren.
        raise ValueError("bewaren zonder bewaartermijn is niet toegestaan (DR9)")

    verwijdersleutel = secrets.token_urlsafe(32) if bewaren else None
    vervalt = (
        (tijdstip + timedelta(days=retention_days)).isoformat(timespec="seconds")
        if bewaren
        else None
    )

    cursor = conn.execute(
        "INSERT INTO dispute (created_at, disputed_category, dispute_text,"
        " claim_id, text_model_version, text_payload, image_model_version,"
        " image_hash, artifact_bytes, artifact_mime, consent_at,"
        " artifact_expires_at, deletion_key_hash)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            moment,
            disputed_category,
            dispute_text,
            claim_id,
            text_fingerprint.model_version if text_fingerprint else None,
            text_fingerprint.vector.tobytes() if text_fingerprint else None,
            image_fingerprint.model_version if image_fingerprint else None,
            image_fingerprint.hash_hex if image_fingerprint else None,
            artifact if bewaren else None,
            artifact_mime if bewaren else None,
            moment if bewaren else None,
            vervalt,
            hash_deletion_key(verwijdersleutel) if bewaren else None,
        ),
    )
    conn.commit()
    return DisputeRecord(
        dispute_id=cursor.lastrowid,
        stored_artifact=bewaren,
        artifact_expires_at=vervalt,
        deletion_key=verwijdersleutel,
    )


class DisputeNotFound(Exception):
    """Er bestaat geen betwisting met dit nummer."""


class DeletionKeyRejected(Exception):
    """De aangeboden verwijdersleutel hoort niet bij deze betwisting."""


def delete_artifact(conn: sqlite3.Connection, dispute_id: int, key: str) -> None:
    """Wist het artefact op vertoon van de verwijdersleutel (B11, AC4).

    De fingerprint, de betwiste categorie en de betwistingstekst blijven staan:
    het privacyrisico verdwijnt, de analysewaarde niet. Herhalen mag — is het
    artefact al weg, dan verandert er niets meer.
    """
    rij = conn.execute(
        "SELECT deletion_key_hash FROM dispute WHERE dispute_id = ?", (dispute_id,)
    ).fetchone()
    if rij is None:
        raise DisputeNotFound(f"betwisting {dispute_id} bestaat niet")

    opgeslagen = rij["deletion_key_hash"]
    # Vergelijking in constante tijd; een lege sleutel kan nooit kloppen.
    if not opgeslagen or not secrets.compare_digest(
        opgeslagen, hash_deletion_key(key)
    ):
        raise DeletionKeyRejected("verwijdersleutel klopt niet")

    conn.execute(
        "UPDATE dispute SET artifact_bytes = NULL, artifact_mime = NULL"
        " WHERE dispute_id = ?",
        (dispute_id,),
    )
    conn.commit()


@dataclass(frozen=True)
class DisputeCase:
    """Een betwisting zoals een bouwer hem leest (E6.S3-AC6).

    Bevat nooit artefactinhoud — alleen of er nog een artefact bestaat en tot
    wanneer. De betwistingstekst is de eigen tekst van de indiener en dus geen
    artefact.
    """

    dispute_id: int
    created_at: str
    disputed_category: str
    dispute_text: str
    claim_id: str | None
    has_text_fingerprint: bool
    has_image_fingerprint: bool
    has_artifact: bool
    artifact_expires_at: str | None


def list_disputes(
    conn: sqlite3.Connection,
    *,
    only_with_artifact: bool = False,
    limit: int | None = None,
) -> list[DisputeCase]:
    """Betwistingen als kandidaat-foutgevallen.

    Let op: een betwisting is een *gemelde* fout, geen gelabelde waarheid. Wie
    beoordeelt of de melder gelijk heeft, is redactioneel werk en valt buiten
    v1 (zie E6.S3). Deze lijst is het materiaal om dat oordeel op te vormen.
    """
    query = (
        "SELECT dispute_id, created_at, disputed_category, dispute_text, claim_id,"
        " text_payload IS NOT NULL AS heeft_tekst,"
        " image_hash IS NOT NULL AS heeft_beeld,"
        " artifact_bytes IS NOT NULL AS heeft_artefact,"
        " artifact_expires_at FROM dispute"
    )
    if only_with_artifact:
        query += " WHERE artifact_bytes IS NOT NULL"
    query += " ORDER BY dispute_id"
    if limit is not None:
        query += f" LIMIT {int(limit)}"

    return [
        DisputeCase(
            dispute_id=rij["dispute_id"],
            created_at=rij["created_at"],
            disputed_category=rij["disputed_category"],
            dispute_text=rij["dispute_text"],
            claim_id=rij["claim_id"],
            has_text_fingerprint=bool(rij["heeft_tekst"]),
            has_image_fingerprint=bool(rij["heeft_beeld"]),
            has_artifact=bool(rij["heeft_artefact"]),
            artifact_expires_at=(
                rij["artifact_expires_at"] if rij["heeft_artefact"] else None
            ),
        )
        for rij in conn.execute(query)
    ]


def main() -> None:
    import argparse

    from doublecheck.storage import connect, init_schema

    parser = argparse.ArgumentParser(description="Betwistingen als foutgevallen tonen")
    parser.add_argument("--db", default="doublecheck.db")
    parser.add_argument("--met-artefact", action="store_true",
                        help="alleen betwistingen waarvan het artefact nog bewaard is")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    conn = connect(args.db)
    init_schema(conn)
    gevallen = list_disputes(
        conn, only_with_artifact=args.met_artefact, limit=args.limit
    )

    print(f"{len(gevallen)} betwisting(en)"
          f"{' met bewaard artefact' if args.met_artefact else ''}")
    for geval in gevallen:
        sporen = []
        if geval.has_text_fingerprint:
            sporen.append("tekst-fp")
        if geval.has_image_fingerprint:
            sporen.append("beeld-fp")
        if geval.has_artifact:
            sporen.append(f"artefact tot {geval.artifact_expires_at[:10]}")
        print(f"\n#{geval.dispute_id}  {geval.created_at[:10]}"
              f"  betwist: {geval.disputed_category}"
              f"  claim: {geval.claim_id or '—'}")
        print(f"   {' · '.join(sporen) or 'geen fingerprint'}")
        print(f"   \"{geval.dispute_text}\"")
    conn.close()


if __name__ == "__main__":
    main()
