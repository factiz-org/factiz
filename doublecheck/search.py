"""Similariteitszoek over de fingerprint-index, met in-proces matrixcache (#22.1).

Vergelijkt uitsluitend binnen de modelversie van de query-fingerprint:
opslag met een andere versie doet structureel niet mee (DR6). Geeft kale
kandidaten met cosinusgelijkenis terug — de uitkomstcategorie zetten is
exclusief aan de categoriseringsfunctie (DR4/DR5).

**Waarom een cache en geen vectordienst (§61):** de 316 ms p95 van §53 zat
niet in de wiskunde (80k×384 matmul is ~1 ms) maar in het per query opnieuw
laden en parsen van alle payload-blobs. Eén matrix per (bestand, soort,
modelversie) in het proces lost dat op zonder nieuwe afhankelijkheid, met
bit-identieke uitkomsten — zelfde rijvolgorde, zelfde stabiele argsort — en
SQLite blijft de enige bron van waarheid. Geheugenprijs onder bge-m3: ~450 MB
bij 110k tekstvectoren van 1024 dimensies.

**Per bestand, niet per verbinding (§77).** De API opent per vraag een verse
verbinding. Toen de cache per verbinding gold, laadde dus élke vraag de hele
index opnieuw; onder MiniLM viel dat weg in de ruis, onder bge-m3 werd het
4,1 s p50 in de belastingtest. Daarom deelt elke verbinding naar hetzelfde
bestand één slot.

**De verversingsregel** — dit is de "afgeleide staat die veroudert zonder dat
iets het merkt"-faalklasse (§17a, §39, §45, §46, §48c, §51d), dus hij is
bewust per aanroep en O(1). Het gedeelde slot geldt zolang de
**wachter**, een eigen verbinding per bestand die nooit schrijft, dezelfde
`PRAGMA data_version` ziet én het bestand dezelfde (apparaat, inode) heeft.
Voor de wachter is elke schrijver een ándere verbinding, dus `data_version`
verspringt bij elke commit, ook van een ander proces; de inode vangt een
database die op dezelfde plek is vervangen (een uitrol met `mv`), want de
wachter houdt het oude bestand open en ziet daar nooit meer iets veranderen.
Elke wijziging gooit de hele slot weg; herbouwen kost één koude laadbeurt,
en gelijktijdige koude vragen wachten op één bouwer in plaats van elk zelf
te bouwen (anders twee keer 450 MB tegelijk).

**Een ongecommitte eigen schrijfactie blijft privé.** Een verbinding met een
open transactie ziet haar eigen wijzigingen, de rest van de wereld niet. Zij
krijgt daarom haar eigen slot, op (id(verbinding), pad), dat geldig blijft
zolang (`data_version`, `total_changes`) van díé verbinding gelijk is — de
oude regel. Zo lekt niets wat nog terug kan rollen naar het gedeelde slot.
id-hergebruik na het sluiten van een verbinding is daar ongevaarlijk: een
treffer vereist óók een gelijk pad en een gelijke schrijfstand.

De cache geldt **alleen voor bestandsdatabases**. Voor `:memory:` staat
`data_version` stil en kunnen twee vérschillende geheugendatabases met een
hergebruikt id op dezelfde stand uitkomen (de suite betrapte dat);
geheugendatabases zoeken daarom brute force, zoals vóór #22.1. De productie
draait altijd op een bestand.
"""

from __future__ import annotations

import os
import sqlite3
import threading
from collections import Counter, OrderedDict
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from doublecheck.embedding import TextFingerprint

# Eén gedeeld slot per bestand is de praktijk (de server heeft er één); de
# grens houdt een proces dat veel bestanden of schrijvende verbindingen
# aanraakt (de testsuite, een import) begrensd, slots én wachters.
_MAX_SLOTS = 8

_slots: OrderedDict = OrderedDict()
_wachters: OrderedDict = OrderedDict()
_slotwissel = threading.Lock()

# Bits per bytewaarde, voor de gevectoriseerde hammingafstand.
_POPCOUNT = np.unpackbits(np.arange(256, dtype=np.uint8)[:, None], axis=1).sum(axis=1)


@dataclass(frozen=True)
class Candidate:
    claim_id: str
    similarity: float
    # Gevonden via een claimvariant (#25.17): taal, generator en promptversie.
    # `None` als de claim via zijn eigen vingerafdruk gevonden is.
    via: dict | None = None
    # De score van de rechter (#30.3), als hij deze kandidaat las.
    rechter: float | None = None


@dataclass(frozen=True)
class ImageCandidate:
    claim_id: str
    distance: int


class ModelVersionMismatchError(Exception):
    """De index is met een andere modelversie gebouwd en niet herbouwd (DR6)."""


def _hoofdpad(conn: sqlite3.Connection) -> str:
    for rij in conn.execute("PRAGMA database_list"):
        if rij[1] == "main":
            return rij[2] or ":memory:"
    return ":memory:"  # pragma: no cover - main bestaat altijd


def _stand(conn: sqlite3.Connection) -> tuple[int, int]:
    return (
        conn.execute("PRAGMA data_version").fetchone()[0],
        conn.total_changes,
    )


def _identiteit(pad: str) -> tuple[int, int] | None:
    try:
        info = os.stat(pad)
    except OSError:
        return None
    return (info.st_dev, info.st_ino)


def _wachterstand(pad: str) -> tuple | None:
    """(identiteit, data_version) zoals de wachter van dit bestand ze ziet.

    Draait onder `_slotwissel`: de wachter is één verbinding voor alle
    threads. `None` als het bestand of de wachter niet bruikbaar is; dan
    valt de aanroeper terug op een slot per verbinding."""
    identiteit = _identiteit(pad)
    if identiteit is None:
        return None
    bestaand = _wachters.get(pad)
    if bestaand is not None and bestaand[0] != identiteit:
        bestaand[1].close()
        del _wachters[pad]
        bestaand = None
    try:
        if bestaand is None:
            # mode=rw: nooit een leeg bestand aanmaken als het net weg is.
            wachter = sqlite3.connect(
                Path(pad).as_uri() + "?mode=rw", uri=True, check_same_thread=False)
            bestaand = (identiteit, wachter)
            _wachters[pad] = bestaand
        versie = bestaand[1].execute("PRAGMA data_version").fetchone()[0]
    except sqlite3.Error:
        weg = _wachters.pop(pad, None)
        if weg is not None:
            weg[1].close()
        return None
    _wachters.move_to_end(pad)
    while len(_wachters) > _MAX_SLOTS:
        _, (_, oudste) = _wachters.popitem(last=False)
        oudste.close()
    return (identiteit, versie)


def _neem_slot(sleutel, stand) -> dict:
    slot = _slots.get(sleutel)
    if slot is None or slot["stand"] != stand:
        # Herintreedbaar: een bouwer mag zelf iets uit hetzelfde slot vragen
        # (de matrix vraagt de claims buiten de index, toelating.py); een
        # andere thread wacht nog steeds op de ene bouwer.
        slot = {"stand": stand, "bouwslot": threading.RLock()}
        _slots[sleutel] = slot
    _slots.move_to_end(sleutel)
    while len(_slots) > _MAX_SLOTS:
        _slots.popitem(last=False)
    return slot


def _slot(conn: sqlite3.Connection) -> dict | None:
    """Het slot voor deze verbinding, geleegd zodra de schrijfstand wijzigt.

    Gedeeld per bestand, behalve bij een open transactie (zie
    moduledocstring). `None` voor een geheugendatabase: daar is geen veilige
    identiteit, en cachen heeft er ook niets te winnen."""
    pad = _hoofdpad(conn)
    if pad == ":memory:":
        return None
    with _slotwissel:
        if not conn.in_transaction:
            stand = _wachterstand(pad)
            if stand is not None:
                return _neem_slot(("bestand", pad), stand)
        return _neem_slot((id(conn), pad), _stand(conn))


def _gecachet(conn: sqlite3.Connection, sleutel, bouwer):
    slot = _slot(conn)
    if slot is None:
        return bouwer()
    entry = slot.get(sleutel)
    if entry is None:
        # Eén bouwer per slot; wie tegelijk koud binnenkomt, wacht en leest mee.
        with slot["bouwslot"]:
            entry = slot.get(sleutel)
            if entry is None:
                entry = bouwer()
                slot[sleutel] = entry
    return entry


def ensure_index_matches_version(conn: sqlite3.Connection, model_version: str) -> None:
    """Weigert luid bij een versiemismatch (E2.S3-AC2).

    Een lege index is géén mismatch — dat is de legitieme beginstand
    (E3.S1-AC2). Oude versies náást de huidige zijn ook geen mismatch; die
    ontstaan bewust bij migratie (herimport vult aan, taak 2.5).
    """
    aanwezig = _gecachet(conn, "tekstversies", lambda: {
        rij["model_version"]
        for rij in conn.execute(
            "SELECT DISTINCT model_version FROM fingerprint WHERE kind = 'text'"
        )
    })
    if aanwezig and model_version not in aanwezig:
        raise ModelVersionMismatchError(
            f"the index holds model version(s) {sorted(aanwezig)}, the resolver expects"
            f" {model_version!r}; rebuild the index by importing again"
        )


def _buiten_index(conn: sqlite3.Connection) -> frozenset[str]:
    """Claims die het zoeken overslaat (B28): weg uit elke matrix, dus uit
    resolver, batchcontrole, varianten en beeld tegelijk. Gelezen bij het
    bouwen van de matrix, niet uit een afgeleide tabel (toelating.py)."""
    from doublecheck.toelating import buiten_index

    return buiten_index(conn)


def _tekstmatrix(conn: sqlite3.Connection, model_version: str):
    # Geen ORDER BY: de natuurlijke rowid-volgorde is dezelfde als vóór de
    # cache, en de stabiele argsort maakt gelijkstanden daarmee bit-identiek.
    buiten = _buiten_index(conn)
    rows = [row for row in conn.execute(
        "SELECT claim_id, payload FROM fingerprint"
        " WHERE kind = 'text' AND model_version = ?",
        (model_version,),
    ) if row["claim_id"] not in buiten]
    ids = tuple(row["claim_id"] for row in rows)
    if rows:
        matrix = np.vstack(
            [np.frombuffer(row["payload"], dtype=np.float32) for row in rows]
        )
    else:
        matrix = np.empty((0, 0), dtype=np.float32)
    matrix.setflags(write=False)
    return ids, matrix


def search_text(
    conn: sqlite3.Connection, fingerprint: TextFingerprint, limit: int = 5,
    *, varianten: bool = False,
) -> list[Candidate]:
    """`varianten`: ook over de claimvarianten zoeken (#25.17). Uit is het
    pad van vóór de varianten, bit-identiek; aan alleen met de schakelaar uit
    de config, in resolver en benchmark gelijk."""
    if varianten:
        return _zoek_met_varianten(conn, fingerprint, limit)
    ids, matrix = _gecachet(
        conn, ("text", fingerprint.model_version),
        lambda: _tekstmatrix(conn, fingerprint.model_version),
    )
    if not ids:
        return []

    return _kies_claims(matrix @ fingerprint.vector, ids, limit)


def _kies_claims(similarities, ids, limit: int) -> list[Candidate]:
    volgorde = np.argsort(-similarities, kind="stable")[:limit]
    return [
        Candidate(claim_id=ids[i], similarity=float(similarities[i]))
        for i in volgorde
    ]


def search_texts(
    conn: sqlite3.Connection, fingerprints: list[TextFingerprint], limit: int = 5,
    *, varianten: bool = False,
) -> list[list[Candidate]]:
    """`search_text` voor elke vingerafdruk, met één matrixproduct (#30.11):
    de matrix van claims en varianten wordt één keer gelezen in plaats van per
    zin. Per vingerafdruk dezelfde keuze als `search_text`."""
    if not fingerprints:
        return []
    versie = fingerprints[0].model_version
    if any(fp.model_version != versie for fp in fingerprints):
        raise ModelVersionMismatchError("de eenheden van één vraag dragen verschillende modelversies (DR6)")
    vragen = np.stack([fp.vector for fp in fingerprints], axis=1)
    ids, matrix = _gecachet(conn, ("text", versie), lambda: _tekstmatrix(conn, versie))
    if not varianten:
        if not ids:
            return [[] for _ in fingerprints]
        uitkomst = matrix @ vragen
        return [_kies_claims(uitkomst[:, j], ids, limit) for j in range(len(fingerprints))]
    vids, via, vmatrix, _ = _gecachet(conn, ("variant", versie), lambda: _variantenmatrix(conn, versie))
    leeg = np.empty((0, len(fingerprints)), dtype=np.float32)
    alle = np.concatenate([matrix @ vragen if ids else leeg, vmatrix @ vragen if vids else leeg])
    return [_kies_varianten(np.ascontiguousarray(alle[:, j]), ids, vids, via, limit)
            for j in range(len(fingerprints))]


def ensure_variants_match_version(conn: sqlite3.Connection, model_version: str) -> None:
    """Met varianten in de resolver: staan er varianten, dan moeten die van
    dít model zijn (DR6), anders weigert de resolver in plaats van stil zonder
    te zoeken. Een lege tabel is, net als een lege claimindex, de legitieme
    beginstand van een schone kloon, geen mismatch; of de varianten van de
    release er staan, controleert de rooktest (#23.4) en toont `/numbers`."""
    aanwezig = _gecachet(conn, "variantversies", lambda: {
        rij[0] for rij in conn.execute("SELECT DISTINCT model_version FROM claim_variant")
    })
    if aanwezig and model_version not in aanwezig:
        raise ModelVersionMismatchError(
            f"variants are on in the resolver, but there are none for {model_version!r}"
            f" (present: {sorted(aanwezig) or 'none'}); import them again"
            " (`python -m doublecheck.variantenbatch importeren`)"
        )


def _variantenmatrix(conn: sqlite3.Connection, model_version: str):
    buiten = _buiten_index(conn)
    rows = [row for row in conn.execute(
        "SELECT claim_id, language, generator, prompt_version, payload FROM claim_variant"
        " WHERE model_version = ? ORDER BY variant_id",
        (model_version,),
    ) if row[0] not in buiten]
    ids = tuple(row[0] for row in rows)
    via = tuple({"language": row[1], "generator": row[2], "prompt": row[3]} for row in rows)
    if rows:
        matrix = np.vstack([np.frombuffer(row[4], dtype=np.float32) for row in rows])
    else:
        matrix = np.empty((0, 0), dtype=np.float32)
    matrix.setflags(write=False)
    # De samenvatting voor de ontdekking, in dezelfde bouw: zo noemt die
    # precies de rijen waarover gezocht wordt.
    per_set: dict[tuple[str, str], Counter] = {}
    for v in via:
        per_set.setdefault((v["generator"], v["prompt"]), Counter())[v["language"]] += 1
    sets = tuple((g, p, tuple(sorted(talen)), sum(talen.values())) for (g, p), talen in sorted(per_set.items()))
    return ids, via, matrix, sets


def variant_sets(conn: sqlite3.Connection, model_version: str) -> list[dict]:
    """De varianten waarover de resolver zoekt, per generator en
    promptversie: talen en aantal (PROTOCOL §3). Uit dezelfde cache als het
    zoeken, dus alleen varianten van dít model (DR6), en zonder de tabel per
    verzoek te tellen: dat kost seconden over 460.000 rijen."""
    *_, sets = _gecachet(conn, ("variant", model_version), lambda: _variantenmatrix(conn, model_version))
    return [{"generator": g, "prompt": p, "languages": list(talen), "count": n} for g, p, talen, n in sets]


def _zoek_met_varianten(conn: sqlite3.Connection, fingerprint: TextFingerprint, limit: int) -> list[Candidate]:
    """Over claims én varianten; per claim telt zijn beste rij, en een claim
    komt maar één keer terug. Bij gelijkstand gaat de eigen claimrij voor."""
    versie = fingerprint.model_version
    ids, matrix = _gecachet(conn, ("text", versie), lambda: _tekstmatrix(conn, versie))
    vids, via, vmatrix, _ = _gecachet(conn, ("variant", versie), lambda: _variantenmatrix(conn, versie))
    delen = [matrix @ fingerprint.vector if ids else np.empty(0, dtype=np.float32),
             vmatrix @ fingerprint.vector if vids else np.empty(0, dtype=np.float32)]
    return _kies_varianten(np.concatenate(delen), ids, vids, via, limit)


def _kies_varianten(alle, ids, vids, via, limit: int) -> list[Candidate]:
    if not len(alle):
        return []
    n = len(ids)

    def kies(rijen) -> list[Candidate]:
        # Hoogste gelijkenis eerst; bij gelijkstand de laagste rij (claims vóór varianten).
        volgorde = rijen[np.lexsort((rijen, -alle[rijen]))]
        gezien, uit = set(), []
        for r in volgorde:
            claim = ids[r] if r < n else vids[r - n]
            if claim in gezien:
                continue
            gezien.add(claim)
            uit.append(Candidate(claim, float(alle[r]), None if r < n else via[r - n]))
            if len(uit) == limit:
                break
        return uit

    # Eerst een ruime voorselectie; is die te klein voor `limit` verschillende
    # claims, dan alles. Zelfde uitkomst, maar zonder 571.000 rijen te sorteren.
    k = min(len(alle), max(limit * 20, 64))
    voor = np.argpartition(-alle, k - 1)[:k] if k < len(alle) else np.arange(len(alle))
    uit = kies(voor)
    if len(uit) < limit and k < len(alle):
        uit = kies(np.arange(len(alle)))
    return uit


def _beeldmatrix(conn: sqlite3.Connection, model_version: str):
    buiten = _buiten_index(conn)
    rows = [row for row in conn.execute(
        "SELECT claim_id, payload FROM fingerprint"
        " WHERE kind = 'image' AND model_version = ?",
        (model_version,),
    ) if row["claim_id"] not in buiten]
    ids = tuple(row["claim_id"] for row in rows)
    if rows:
        matrix = np.vstack([
            np.frombuffer(bytes.fromhex(row["payload"].decode("ascii")), dtype=np.uint8)
            for row in rows
        ])
    else:
        matrix = np.empty((0, 0), dtype=np.uint8)
    matrix.setflags(write=False)
    return ids, matrix


def search_image(conn: sqlite3.Connection, fingerprint, limit: int = 5):
    """Dichtstbijzijnde eerst (hammingafstand), binnen dezelfde hash-versie
    (DR6). Gevectoriseerd over de gecachte bytematrix; bij gelijkstand wint
    de opslagvolgorde, net als vóór de cache."""
    ids, matrix = _gecachet(
        conn, ("image", fingerprint.model_version),
        lambda: _beeldmatrix(conn, fingerprint.model_version),
    )
    if not ids:
        return []

    query = np.frombuffer(bytes.fromhex(fingerprint.hash_hex), dtype=np.uint8)
    afstanden = _POPCOUNT[matrix ^ query].sum(axis=1, dtype=np.int64)
    volgorde = np.argsort(afstanden, kind="stable")[:limit]
    return [
        ImageCandidate(claim_id=ids[i], distance=int(afstanden[i]))
        for i in volgorde
    ]
