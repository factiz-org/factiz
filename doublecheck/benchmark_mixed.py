"""Gemengde artefacten: beeld én tekst vuren tegelijk (PLAN.md #13, B15).

Onder de v1-inperking E1.S2-AC5 zweeg de beeldroute zodra er leesbare tekst was,
dus deze combinatie kón niet vuren en geen enkel harnas dekte hem — de
tekstbenchmark kent geen beelden, de beeldbenchmark gaat niet door de API. B15
heeft de route opengezet en daarmee een nieuwe klasse fouten mogelijk gemaakt.

Vier klassen, waarheid-door-constructie: het label volgt uit hoe het paar
gebouwd is, niet uit het model dat gemeten wordt.

De maat die er nieuw bij komt is **misleidend signaal**: `matched_on` noemt een
signaal dat naar een ándere claim wijst dan de teruggegeven `claim_id`. Wie dat
antwoord leest concludeert dat het beeld de claim staaft, terwijl het beeld
ergens anders op sloeg. Dat is geen verkeerde categorie maar een onwaar
bijschrift bij een goede categorie — en dus een eigen telling waard.

Zoals de beeldbenchmark is dit een **synthetische** meting: claimteksten
gerenderd als screenshot. Het meet het samenspel van de routes, niet de dekking
op wildbeelden.
"""

from __future__ import annotations

import io
import sqlite3
from dataclasses import dataclass, field

from doublecheck.benchmark_images import render_claim
from doublecheck.config import load_config
from doublecheck.image_fingerprint import fingerprint_image
from doublecheck.storage import save_image_fingerprint

KLASSEN = ("beide-zelfde", "beide-verschillend", "alleen-tekst", "alleen-beeld")


@dataclass(frozen=True)
class MixedPair:
    klasse: str
    afbeelding_png: bytes
    # Welke claim elke route hóórt te vinden; None = die route vindt niets.
    tekst_claim: str | None
    beeld_claim: str | None


@dataclass
class KlasseStats:
    paren: int = 0
    juiste_claim: int = 0
    # `matched_on` noemt een signaal dat naar een andere claim wijst.
    misleidend: int = 0
    categorieen: dict = field(default_factory=dict)


@dataclass(frozen=True)
class MixedResult:
    per_klasse: dict


def _png(afbeelding) -> bytes:
    buffer = io.BytesIO()
    afbeelding.save(buffer, format="PNG")
    return buffer.getvalue()


def _detailarm(seed: int):
    """Beeld zónder leesbare tekst, voor de klasse waar alleen beeld mag vuren."""
    from tests.beelden import vormen

    return vormen(seed)


def build_mixed_pairs(conn: sqlite3.Connection, limit: int = 40) -> list[MixedPair]:
    """Bouwt de vier klassen en indexeert de bijbehorende beeld-fingerprints."""
    config = load_config()
    versie = config.model_versions.image_hash
    claims = conn.execute(
        "SELECT claim_id, canonical_text FROM claim ORDER BY claim_id LIMIT ?",
        (limit,),
    ).fetchall()
    if len(claims) < 4:
        raise ValueError("te weinig claims voor een gemengde testset")

    paren: list[MixedPair] = []
    for nummer, rij in enumerate(claims):
        claim_id, tekst = rij["claim_id"], rij["canonical_text"]
        klasse = KLASSEN[nummer % len(KLASSEN)]
        beeld = render_claim(tekst)

        if klasse == "beide-zelfde":
            save_image_fingerprint(conn, claim_id, fingerprint_image(beeld, versie))
            paren.append(MixedPair(klasse, _png(beeld), claim_id, claim_id))

        elif klasse == "beide-verschillend":
            # Hetzelfde beeld, maar geïndexeerd onder een ándere claim: de tekst
            # wijst naar `claim_id`, het beeld naar `ander`.
            ander = claims[(nummer + 1) % len(claims)]["claim_id"]
            if ander == claim_id:
                continue
            save_image_fingerprint(conn, ander, fingerprint_image(beeld, versie))
            paren.append(MixedPair(klasse, _png(beeld), claim_id, ander))

        elif klasse == "alleen-tekst":
            # Beeld nergens geïndexeerd: alleen de tekstroute kan vuren.
            paren.append(MixedPair(klasse, _png(beeld), claim_id, None))

        else:  # alleen-beeld
            detailarm = _detailarm(nummer)
            save_image_fingerprint(conn, claim_id, fingerprint_image(detailarm, versie))
            paren.append(MixedPair(klasse, _png(detailarm), None, claim_id))

    conn.commit()
    return paren


def _signalen_wijzen_naar(matched_on, claim_id, paar) -> bool:
    """True wanneer een genoemd signaal een ándere claim aanwijst dan `claim_id`."""
    if "beeld" in matched_on and paar.beeld_claim not in (None, claim_id):
        return True
    tekst_signalen = {"tekst", "tekst-gedeeltelijk"} & set(matched_on)
    return bool(tekst_signalen) and paar.tekst_claim not in (None, claim_id)


def run_mixed_benchmark(conn: sqlite3.Connection, limit: int = 40, config=None) -> MixedResult:
    """`config`: een andere config voor deze meting, bijvoorbeeld met twee
    keer lezen bij twijfel aan (#25.22); zonder blijft het die van de machine."""
    from fastapi.testclient import TestClient

    import doublecheck.api as api
    from doublecheck.ruwetest import antwoord_of_fout, zonder_ipgrens

    paren = build_mixed_pairs(conn, limit=limit)
    # Een 429 telde hier als categorie None: een valse treffer kon zo
    # verdwijnen. Grens uit, en een fout stopt de run (#28.5).
    zonder_ipgrens()
    per_klasse = {klasse: KlasseStats() for klasse in KLASSEN}

    api.app.dependency_overrides[api.get_conn] = lambda: conn
    if config is not None:
        api.app.dependency_overrides[api.get_config] = lambda: config
    try:
        client = TestClient(api.app)
        for paar in paren:
            body = antwoord_of_fout(client.post(
                "/resolve",
                files={"image": ("artefact.png", paar.afbeelding_png, "image/png")},
            ))
            stats = per_klasse[paar.klasse]
            stats.paren += 1
            verwacht = paar.tekst_claim or paar.beeld_claim
            gevonden_claim = (body.get("claim") or {}).get("id")
            if gevonden_claim == verwacht:
                stats.juiste_claim += 1
            if _signalen_wijzen_naar(body.get("matched_on", []),
                                     gevonden_claim, paar):
                stats.misleidend += 1
            categorie = body.get("category")
            stats.categorieen[categorie] = stats.categorieen.get(categorie, 0) + 1
    finally:
        api.app.dependency_overrides.clear()

    return MixedResult(per_klasse=per_klasse)


def main() -> None:
    import argparse

    from doublecheck.storage import connect, init_schema

    parser = argparse.ArgumentParser(description="Doublecheck gemengde benchmark")
    parser.add_argument("--db", default="benchmark-gemengd.db")
    parser.add_argument("--from-corpus", default="doublecheck.db")
    parser.add_argument("--claims", type=int, default=40)
    parser.add_argument("--ocr-ondergrens", type=float,
                        help="meet met twee keer lezen bij twijfel vanaf deze OSD-zekerheid (#25.22); raakt config niet")
    args = parser.parse_args()

    config = load_config()
    conn = connect(args.db)
    init_schema(conn)

    # Claims, checks en tekstfingerprints overnemen — nooit een artefact (DR3).
    bron = connect(args.from_corpus)
    init_schema(bron)
    rijen = bron.execute(
        "SELECT c.claim_id, c.canonical_text, c.language, f.payload"
        " FROM claim c JOIN fingerprint f ON f.claim_id = c.claim_id"
        " AND f.kind = 'text' AND f.model_version = ?"
        " ORDER BY c.claim_id LIMIT ?",
        (config.model_versions.text_embedding, int(args.claims)),
    ).fetchall()
    for rij in rijen:
        conn.execute(
            "INSERT OR IGNORE INTO claim (claim_id, canonical_text, language)"
            " VALUES (?, ?, ?)",
            (rij["claim_id"], rij["canonical_text"], rij["language"]),
        )
        conn.execute(
            "INSERT INTO fingerprint (claim_id, kind, model_version, payload)"
            " VALUES (?, 'text', ?, ?)",
            (rij["claim_id"], config.model_versions.text_embedding, rij["payload"]),
        )
        for check in bron.execute(
            "SELECT publisher, verdict_normalized, verdict_original, url,"
            " review_date, language FROM factcheck WHERE claim_id = ?",
            (rij["claim_id"],),
        ):
            conn.execute(
                "INSERT INTO factcheck (claim_id, publisher, verdict_normalized,"
                " verdict_original, url, review_date, language)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (rij["claim_id"], *tuple(check)),
            )
    conn.commit()
    bron.close()
    print(f"gemengde index: {len(rijen)} claims overgenomen uit {args.from_corpus}")

    gemeten = None
    if args.ocr_ondergrens is not None:
        from doublecheck.ruwetest import config_met_ondergrens

        gemeten = config_met_ondergrens(args.ocr_ondergrens)
    resultaat = run_mixed_benchmark(conn, limit=args.claims, config=gemeten)

    print("gemengde benchmark · beeld én tekst door dezelfde resolver")
    print(f"{'klasse':<22}{'paren':>7}{'juiste claim':>14}{'misleidend':>12}"
          f"  categorieën")
    for klasse in KLASSEN:
        s = resultaat.per_klasse[klasse]
        if not s.paren:
            continue
        print(f"{klasse:<22}{s.paren:>7}{s.juiste_claim:>14}{s.misleidend:>12}"
              f"  {dict(sorted(s.categorieen.items()))}")
    print()
    print("misleidend = `matched_on` noemt een signaal dat naar een ándere claim")
    print("wijst dan de teruggegeven claim_id.")
    conn.close()


if __name__ == "__main__":
    main()
