"""Beeldbenchmark: meetgereedschap voor de beeldroute (PLAN.md #4.9).

**Belangrijke beperking.** Het ClaimReview-corpus levert geen afbeeldingen, dus
er is geen echte beeldindex om tegen te meten (bevinding 4.6). Deze module
bouwt daarom een *synthetische* beeldindex: elke claimtekst wordt gerenderd als
screenshot en gehasht. Dat is een redelijke proxy voor het domein — mensen
sturen vooral screenshots van koppen door — maar het meet de robuustheid van
de beeldpijplijn, niet de dekking op echte wildbeelden. Zie docs/BENCHMARK.md.

De transformaties komen recht uit E1.S2: hercompressie (AC1), bijsnijden (AC2)
en een onbekend beeld dat niet mag matchen (AC3).
"""

from __future__ import annotations

import io
import sqlite3
from dataclasses import dataclass, replace
from pathlib import Path

import hashlib
import unicodedata
from functools import lru_cache

from PIL import Image, ImageDraw, ImageFont

from doublecheck.image_fingerprint import fingerprint_image
from doublecheck.storage import save_image_fingerprint
from doublecheck.testset import TestPair, save_test_pair

# Breed eerst, dan per schrift, dan de Linux-varianten. Er bestaat geen
# lettertype dat alles dekt: Arial Unicode mist Ethiopisch, en Amhaars zit in
# het corpus (§51d).
# Volgorde is opzet. Vooraan de lettertypen die er al stonden, zodat Latijnse
# claims **exact** blijven renderen als vóór #18.3 en de cijfers uit §29
# vergelijkbaar blijven. Daarachter de brede en schriftspecifieke, waar de tekst
# doorheen valt die vooraan alleen blokjes zou opleveren.
#
# Er bestaat geen lettertype dat alles dekt: Arial Unicode mist Ethiopisch, en
# Amhaars zit in het corpus (§51d). Vandaar een lijst en geen keuze.
_LETTERTYPEN = (
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    # Breed, voor wat hierboven niet lukt.
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    "/Library/Fonts/Arial Unicode.ttf",
    "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
    # Per schrift, voor wat zelfs Arial Unicode niet dekt.
    "/System/Library/Fonts/Supplemental/KefaIII.ttf",          # Ethiopisch
    "/System/Library/Fonts/Supplemental/NotoSansMyanmar.ttc",  # Birmaans
    "/System/Library/Fonts/Supplemental/Khmer MN.ttc",         # Khmer
    "/System/Library/Fonts/Supplemental/Sinhala MN.ttc",       # Singalees
)


class OngedekteTekst(ValueError):
    """Geen enkel beschikbaar lettertype kan deze tekst tekenen.

    Weigeren en niet tekenen, want blokjes zijn erger dan niets: twee
    verschillende CJK-claims kregen zo een exact identieke PDQ-hash — 23 van de
    435 paren in de eigen steekproef van de beeldbenchmark (§51d). Een gemiste
    meting is zichtbaar, een valse koppeling niet.
    """


@lru_cache(maxsize=None)
def _geladen(grootte: int) -> tuple:
    lettertypen = []
    for pad in _LETTERTYPEN:
        if not Path(pad).exists():
            continue
        try:
            lettertypen.append(ImageFont.truetype(pad, grootte))
        except OSError:
            continue
    return tuple(lettertypen) or (ImageFont.load_default(),)


def _proeftekens(tekst: str, *, alleen_letters: bool = True) -> list[str]:
    """Tekens waarop de gliefcontrole draait.

    Bij voorkeur letters en combinerende tekens: cijfers en leestekens tekent
    élk lettertype, dus die zouden een ontbrekend schrift maskeren. Pas als er
    geen twee letters zijn, kijkt de controle breder.
    """
    uit: list[str] = []
    for teken in tekst:
        if alleen_letters:
            geschikt = unicodedata.category(teken)[0] in {"L", "M"}
        else:
            geschikt = not teken.isspace() and unicodedata.category(teken)[0] != "P"
        if geschikt and teken not in uit:
            uit.append(teken)
        if len(uit) == 6:
            break
    return uit


def _tekent_verschillend(lettertype, tekst: str) -> bool:
    """Tekent dit lettertype de letters van `tekst` als verschillende beelden?

    Dít is de controle die de fout blootlegde. Een gliefcontrole op "levert dit
    teken iets op" wordt gefopt door blokjes — die zijn niet leeg. Maar twee
    verschillende letters die hetzelfde beeld geven, kúnnen geen glieven zijn.
    """
    letters = _proeftekens(tekst, alleen_letters=True)
    if len(letters) < 2:
        # Tekst zonder letters — bijvoorbeeld tekens uit het private
        # gebruiksgebied. Dan breder kijken, anders is de controle leeg en
        # glipt er alsnog een onrenderbare tekst door.
        letters = _proeftekens(tekst, alleen_letters=False)
    if len(letters) < 2:
        return True
    beelden = set()
    for teken in letters:
        proef = Image.new("L", (64, 64), 0)
        ImageDraw.Draw(proef).text((6, 6), teken, font=lettertype, fill=255)
        beelden.add(proef.tobytes())
    return len(beelden) == len(letters)


def _lettertype_voor(tekst: str, grootte: int = 30):
    """Het eerste lettertype dat deze tekst écht kan tekenen, of `None`."""
    for lettertype in _geladen(grootte):
        if _tekent_verschillend(lettertype, tekst):
            return lettertype
    return None


def renderversie(basis: str) -> str:
    """Beeldhashversie mét de renderer erin verwerkt (DR6-analoog, #18.3).

    De synthetische beeldindex slaat vingerafdrukken op van *gerenderde* tekst.
    Verandert het lettertype, dan veranderen die vingerafdrukken — terwijl
    `image_hash` hetzelfde blijft staan. Een oude benchmarkdatabase zou dan
    stilzwijgend beelden van het vorige lettertype vergelijken met nieuwe: exact
    de faalvorm die dit project overal elders afvangt.

    Door de gekozen lettertypen in de versiestring te verwerken, weigert de
    bestaande DR6-machinerie vanzelf over renderers heen te vergelijken.
    """
    aanwezig = [pad for pad in _LETTERTYPEN if Path(pad).exists()]
    merk = hashlib.sha256("|".join(aanwezig).encode("utf-8")).hexdigest()[:8]
    return f"{basis}+render-{merk}"


def _vingerafdruk(afbeelding, opslagversie: str):
    """Hashen met de échte hashversie, opslaan onder de renderversie.

    `fingerprint_image` kent alleen zijn eigen algoritmenamen, en terecht — de
    renderer is geen hashvariant. Maar de opgeslagen rij moet wél weten met welk
    lettertype hij gemaakt is, anders vergelijkt een volgende run stilzwijgend
    over renderers heen.
    """
    hashversie = opslagversie.split("+render-")[0]
    return replace(
        fingerprint_image(afbeelding, hashversie), model_version=opslagversie
    )


def kan_renderen(tekst: str) -> bool:
    """Kan enige beschikbare letter deze tekst tekenen? Zo niet: overslaan."""
    return _lettertype_voor(tekst) is not None


def render_claim(text: str, breedte: int = 760, hoogte: int = 240) -> Image.Image:
    """Rendert een claimtekst als screenshot-achtige afbeelding.

    Weigert wanneer geen enkel lettertype de tekst dekt; zie `OngedekteTekst`.
    """
    lettertype = _lettertype_voor(text)
    if lettertype is None:
        raise OngedekteTekst(
            "geen beschikbaar lettertype tekent deze tekst; renderen zou "
            f"blokjes opleveren: {text[:40]!r}"
        )
    afbeelding = Image.new("RGB", (breedte, hoogte), "white")
    tekenaar = ImageDraw.Draw(afbeelding)

    woorden = text.split()
    regels, huidig = [], ""
    for woord in woorden:
        kandidaat = f"{huidig} {woord}".strip()
        if len(kandidaat) > 42:
            regels.append(huidig)
            huidig = woord
        else:
            huidig = kandidaat
    if huidig:
        regels.append(huidig)

    for nummer, regel in enumerate(regels[:5]):
        tekenaar.text((24, 24 + nummer * 42), regel, font=lettertype, fill="black")
    return afbeelding


def _hercomprimeer(afbeelding: Image.Image, kwaliteit: int = 60) -> Image.Image:
    buffer = io.BytesIO()
    afbeelding.save(buffer, format="JPEG", quality=kwaliteit)
    buffer.seek(0)
    return Image.open(buffer).convert("RGB")


def _snij_bij(afbeelding: Image.Image, fractie: float = 0.10) -> Image.Image:
    breedte, hoogte = afbeelding.size
    dx, dy = int(breedte * fractie), int(hoogte * fractie)
    return afbeelding.crop((dx, dy, breedte - dx, hoogte - dy))


@dataclass(frozen=True)
class IndexReport:
    toegevoegd: int
    # Claims die geen enkel lettertype kan tekenen. Ze worden overgeslagen en
    # geteld, nooit als blokjes gerenderd (§51d, #18.3).
    overgeslagen: tuple[str, ...] = ()

    def __int__(self) -> int:  # blijft bruikbaar waar een aantal verwacht wordt
        return self.toegevoegd


def build_synthetic_image_index(
    conn: sqlite3.Connection, model_version: str, limit: int | None = None
) -> IndexReport:
    """Geeft elke claim een beeld-fingerprint van zijn gerenderde tekst.

    Een claim die geen beschikbaar lettertype kan tekenen gaat er **niet** in.
    Blokjes renderen leverde twee losstaande CJK-claims dezelfde PDQ-hash op —
    23 van de 435 paren (§51d). Een overgeslagen claim is zichtbaar in het
    rapport; een valse koppeling niet.
    """
    query = "SELECT claim_id, canonical_text FROM claim ORDER BY claim_id"
    if limit is not None:
        query += f" LIMIT {int(limit)}"
    aantal = 0
    overgeslagen: list[str] = []
    for rij in conn.execute(query).fetchall():
        bestaat = conn.execute(
            "SELECT 1 FROM fingerprint WHERE claim_id = ? AND kind = 'image'"
            " AND model_version = ?",
            (rij["claim_id"], model_version),
        ).fetchone()
        if bestaat:
            continue
        try:
            afbeelding = render_claim(rij["canonical_text"])
        except OngedekteTekst:
            overgeslagen.append(rij["claim_id"])
            continue
        save_image_fingerprint(
            conn, rij["claim_id"], _vingerafdruk(afbeelding, model_version)
        )
        aantal += 1
    conn.commit()
    return IndexReport(aantal, tuple(overgeslagen))


@dataclass(frozen=True)
class ImagePairReport:
    total: int
    per_provenance: dict[str, int]
    # Claims waarvoor geen lettertype glieven heeft; overgeslagen in plaats van
    # als blokjes gerenderd (#18.3).
    ongedekt: int = 0


def build_image_pairs(
    conn: sqlite3.Connection,
    model_version: str,
    per_claim_limit: int | None = None,
    total: int | None = None,
) -> ImagePairReport:
    """Bouwt beeldparen; wist eerst de bestaande testset (net als de tekstbouwer)."""
    conn.execute("DELETE FROM testpair")

    claims = conn.execute(
        "SELECT claim.claim_id, claim.canonical_text, claim.language FROM claim"
        " JOIN fingerprint ON fingerprint.claim_id = claim.claim_id"
        " WHERE fingerprint.kind = 'image' AND fingerprint.model_version = ?"
        " ORDER BY claim.claim_id",
        (model_version,),
    ).fetchall()
    if per_claim_limit is not None:
        claims = claims[: max(1, per_claim_limit // 4)]
    elif total is not None:
        claims = claims[: max(1, total // 4)]

    per_provenance: dict[str, int] = {}
    aantal = 0

    def _bewaar(claim, provenance, is_same, afbeelding):
        nonlocal aantal
        save_test_pair(
            conn,
            TestPair(
                claim_id=claim["claim_id"],
                is_same=is_same,
                provenance=provenance,
                language=claim["language"],
                fingerprint=_vingerafdruk(afbeelding, model_version),
            ),
        )
        per_provenance[provenance] = per_provenance.get(provenance, 0) + 1
        aantal += 1

    ongedekt = 0
    for volgnummer, claim in enumerate(claims):
        if not kan_renderen(claim["canonical_text"]):
            ongedekt += 1
            continue
        origineel = render_claim(claim["canonical_text"])
        _bewaar(claim, "beeld-origineel", True, origineel)
        _bewaar(claim, "beeld-hercompressie", True, _hercomprimeer(origineel))
        _bewaar(claim, "beeld-bijsnijden", True, _snij_bij(origineel))
        # Beeld dat niet in de index zit: elke match hierop is een fout (AC3).
        onbekend = render_claim(
            f"Niet-geindexeerde bewering {volgnummer} over een geheel ander onderwerp"
        )
        _bewaar(claim, "beeld-onbekend", False, onbekend)

    conn.commit()
    return ImagePairReport(
        total=aantal, per_provenance=per_provenance, ongedekt=ongedekt
    )


def main() -> None:
    import argparse

    from doublecheck.benchmark import record_run, run_benchmark, upper_bound_95
    from doublecheck.config import load_config
    from doublecheck.storage import connect, init_schema

    parser = argparse.ArgumentParser(
        description="Doublecheck beeldbenchmark (synthetische beeldindex)"
    )
    parser.add_argument("--db", default="benchmark-beeld.db")
    parser.add_argument("--from-corpus", default="doublecheck.db")
    parser.add_argument("--claims", type=int, default=250)
    parser.add_argument("--hash", dest="hash_versie", default=None,
                        help="beeldhash-versie i.p.v. die uit config (#4P.3);"
                             " een vergelijking wijzigt config niet (DR6)")
    parser.add_argument("--drempel", type=int, default=None,
                        help="gelijkheidsdrempel i.p.v. die uit config;"
                             " PDQ is 256 bits en heeft dus een ándere grootheid")
    args = parser.parse_args()

    config = load_config()
    versie = renderversie(args.hash_versie or config.model_versions.image_hash)
    if args.drempel is not None:
        from dataclasses import replace

        config = replace(
            config, thresholds=replace(config.thresholds, image_same=args.drempel)
        )

    conn = connect(args.db)
    init_schema(conn)
    # Claims uit het corpus overnemen (alleen tekst en verwijzingen, DR3).
    bron = connect(args.from_corpus)
    init_schema(bron)
    rijen = bron.execute(
        "SELECT claim_id, canonical_text, language FROM claim ORDER BY claim_id"
        f" LIMIT {int(args.claims)}"
    ).fetchall()
    for rij in rijen:
        conn.execute(
            "INSERT OR IGNORE INTO claim (claim_id, canonical_text, language)"
            " VALUES (?, ?, ?)",
            (rij["claim_id"], rij["canonical_text"], rij["language"]),
        )
    bron.close()
    conn.commit()

    nieuw = build_synthetic_image_index(conn, versie)
    rapport = build_image_pairs(conn, versie)
    print(f"synthetische beeldindex: {nieuw.toegevoegd} nieuwe fingerprints"
          f" over {len(rijen)} claims")
    if nieuw.overgeslagen:
        print(f"  {len(nieuw.overgeslagen)} claims overgeslagen: geen lettertype"
              " met glieven voor hun schrift (#18.3)")
    print(f"beeldparen: {rapport.total} {dict(sorted(rapport.per_provenance.items()))}"
          + (f" · {rapport.ongedekt} claims zonder lettertype overgeslagen"
             if rapport.ongedekt else ""))
    print()

    resultaat = run_benchmark(
        conn, config.thresholds, config.model_versions.text_embedding,
        image_model_version=versie,
    )
    beeld = resultaat.per_kind.get("image")
    print(f"beeldbenchmark · hash {versie} · drempel {config.thresholds.image_same}")
    print(f"  paren:                 {beeld.pairs}")
    print(f"  verkeerde koppelingen: {beeld.wrong_links} op {beeld.pairs}"
          f"  (bovengrens95 {upper_bound_95(beeld.wrong_links, beeld.pairs):.2%})")
    print(f"  dekking:               {beeld.correct_matches} van {beeld.same_pairs}")

    fouten: dict[str, int] = {}
    gemist: dict[str, int] = {}
    for uitkomst in resultaat.outcomes:
        if uitkomst.fout:
            fouten[uitkomst.provenance] = fouten.get(uitkomst.provenance, 0) + 1
        elif uitkomst.is_same and uitkomst.matched_claim_id is None:
            gemist[uitkomst.provenance] = gemist.get(uitkomst.provenance, 0) + 1
    print(f"  fouten per soort:  {dict(sorted(fouten.items())) or 'geen'}")
    print(f"  gemist per soort:  {dict(sorted(gemist.items())) or 'geen'}")

    run_id = record_run(conn, config.thresholds, config.model_versions, resultaat)
    print(f"\nrun #{run_id} vastgelegd in {args.db}")
    conn.close()


if __name__ == "__main__":
    main()
