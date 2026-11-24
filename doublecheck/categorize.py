"""Dé plek die de uitkomstcategorie zet — de enige (DR4, DR5).

Geen ander codepad mag een categorie toekennen of overschrijven. De functie
heeft bewust geen default-drempels: die komen altijd uit config (DR6), en de
gebruikte waarden reizen mee in het resultaat (E3.S2-AC4).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from doublecheck.config import Thresholds


class Category(StrEnum):
    MATCHED = "matched"
    RELATED = "related"
    # Gereserveerde contractwoordenschat (E5.S1); niets in v1 produceert dit —
    # eigen AI-oordeel staat op de Won't-lijst (B3) en valt onder DR5.
    ASSESSED = "assessed"
    NONE = "none"


@dataclass(frozen=True)
class Categorization:
    category: Category
    similarity: float | None
    thresholds: Thresholds
    contradiction: bool = False
    # Wát er overeenkomt: "tekst", "tekst-gedeeltelijk", "beeld" (E3.S2-AC2).
    matched_on: tuple[str, ...] = ()
    image_distance: int | None = None


def rechterdrempel(gelijkenis: float, thresholds: Thresholds, crosslinguaal: bool = False) -> float:
    """De score die de rechter voor deze kandidaat moet halen (#30.3): mild
    als veto vanaf de matchdrempel, streng daaronder."""
    drempel = thresholds.text_match_crosslingual if crosslinguaal else thresholds.text_match
    if gelijkenis >= drempel and thresholds.rechter_veto is not None:
        return thresholds.rechter_veto
    return thresholds.rechter_zelfde


def categorize(
    best_similarity: float | None,
    thresholds: Thresholds,
    contradiction: bool = False,
    image_distance: int | None = None,
    crosslinguaal: bool = False,
    image_claim_differs: bool = False,
    rechter: float | None = None,
    feit_rood: bool = False,
    lezer: float | None = None,
) -> Categorization:
    """`crosslinguaal` verlaagt alleen de matchdrempel, en alleen wanneer de
    aanroeper heeft vastgesteld dat béíde talen bekend zijn én verschillen
    (#12.4). Twijfel hoort hier nooit binnen te komen: die valt buiten deze
    functie al terug op de strenge drempel.

    `rechter` is de score van de rechter (#30.3, B36) voor deze kandidaat.
    Is hij er, dan is hij de matchdrempel voor tekst: tussen de vloer en de
    matchdrempel tilt hij een kandidaat alleen op als hij zeker is
    (`rechter_zelfde`); vanaf de matchdrempel is hij een veto met een
    mildere drempel (`rechter_veto`, anders dezelfde). Een nee houdt ook een
    dichte vector op `related`.

    `lezer` is de score van de artikellezer (#30.11b) voor een kandidaat van
    een tekst met meerdere eenheden: `matched` vanaf `artikel_vloer` als hij
    `artikel_zelfde` haalt. Tegenspraak en de feitenlaag houden hem tegen,
    zoals elke andere weg naar `matched`."""
    beeld_match = (
        image_distance is not None and image_distance <= thresholds.image_same
    )
    drempel = (
        thresholds.text_match_crosslingual if crosslinguaal else thresholds.text_match
    )
    if lezer is not None:
        if thresholds.artikel_vloer is None or thresholds.artikel_zelfde is None:
            raise ValueError("een lezerscore zonder lezerdrempels in de config (DR6)")
        tekst_match = (best_similarity is not None and best_similarity >= thresholds.artikel_vloer
                       and lezer >= thresholds.artikel_zelfde)
    elif rechter is not None:
        if thresholds.rechter_zelfde is None or thresholds.rechter_vloer is None:
            raise ValueError("een rechterscore zonder rechterdrempels in de config (DR6)")
        tekst_match = (best_similarity is not None and best_similarity >= thresholds.rechter_vloer
                       and rechter >= rechterdrempel(best_similarity, thresholds, crosslinguaal))
    else:
        tekst_match = best_similarity is not None and best_similarity >= drempel
    tekst_deels = (
        best_similarity is not None
        and not tekst_match
        and best_similarity >= thresholds.text_related
    )

    if tekst_match:
        category = Category.MATCHED
    elif tekst_deels or beeld_match:
        # B8/E1.S2-AC4: een beeldovereenkomst zonder claimovereenkomst is
        # `related` — "zelfde foto, nieuw bijschrift" is nooit een volle match.
        category = Category.RELATED
    else:
        category = Category.NONE

    if feit_rood and category is Category.MATCHED:
        # #30.3b: de vraag is een vastgesteld feit uit de kern en de kandidaat
        # draagt een rood of omstreden oordeel. Dat oordeel gaat over een
        # andere bewering, hoe dichtbij de vector ook ligt (B33, nultolerantie).
        category = Category.RELATED

    if contradiction and category is Category.MATCHED:
        # DR8: een vastgestelde tegenspraak is nooit `matched`, hoe dichtbij
        # de vector ook ligt — hoogstens `related`, mét relatievermelding.
        category = Category.RELATED

    signalen = []
    if tekst_match:
        signalen.append("tekst")
    elif tekst_deels:
        signalen.append("tekst-gedeeltelijk")
    if beeld_match and not (image_claim_differs and (tekst_match or tekst_deels)):
        # Wijst het beeld naar een ándere claim dan de tekst, dan staaft het de
        # teruggegeven claim niet en hoort het hier niet genoemd te worden.
        signalen.append("beeld")

    return Categorization(
        category=category,
        similarity=best_similarity,
        thresholds=thresholds,
        contradiction=contradiction,
        matched_on=tuple(signalen),
        image_distance=image_distance,
    )


def reden_voor_none(*, zoektekst: str | None, taal: str | None, index_talen: set[str]) -> str:
    """Wat een `none` waard is (PROTOCOL §6, #25.35). Zet geen categorie en
    verandert er geen (DR4): dit wordt alleen gevraagd ná `Category.NONE`.

    - `low_confidence`: er was geen tekst om op te zoeken, alleen de beeldroute
      draaide;
    - `out_of_scope`: de tekst staat in een taal die de index niet kent;
    - `not_found`: gezocht in een taal die we dekken, en niets gevonden.

    Een onzekere taal (`taal is None`) is nooit `out_of_scope`: we zeggen
    alleen wat we weten."""
    if zoektekst is None:
        return "low_confidence"
    if taal is not None and taal not in index_talen:
        return "out_of_scope"
    return "not_found"
