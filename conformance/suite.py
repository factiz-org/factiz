"""Conformantiesuite voor het resolverprotocol v0.1 *(PROTOCOL.md §8)*.

Deze suite kent geen implementatie. Hij stuurt artefacten naar een resolver
en toetst de verplichtingen uit §2 op wát er terugkomt.

Twee dingen bepalen de vorm. **De test bestaat uit weigeringen, niet uit
uitkomsten**: nergens wordt een categorie voorgeschreven, alleen wat een
antwoord niet mag zijn. En **niet-waargenomen is geen geslaagd**: een regel
die tijdens de run nooit aan bod kwam wordt apart gerapporteerd, want een
groen vinkje op een ongeteste regel is precies de belofte die dit protocol
wil vervangen.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Iterator, Sequence

# Uitvoer naar buiten in het Engels (PO 2026-10-13: de voertaal van Factiz
# naar buiten is overal Engels); de code zelf blijft Nederlands.
GESLAAGD = "passed"
GEFAALD = "failed"
NIET_WAARGENOMEN = "not observed"

# Velden die waarheidswaarschijnlijkheid uitdrukken (§2.1). Matchzekerheid
# (`similarity`) en systeemprecisie zijn uitdrukkelijk toegestaan.
VERBODEN_TOKENS = (
    "truth",
    "waarheid",
    "veracity",
    "probability",
    "waarschijnlijk",
    "likelihood",
    "credibility",
    "geloofwaardig",
    "trustworthiness",
)

# Marge tegen afrondingsverschillen tussen server en JSON.
_TOLERANTIE = 1e-6

# Wat deze suite principieel niet over HTTP kan vaststellen. Hoort in elk
# rapport, want een lezer moet weten waar het bewijs ophoudt.
BEPERKINGEN = (
    "That nothing is stored cannot be proven from outside (§2.4). Obligation 4 "
    "tests one observable failure: a submitted artifact that comes back as a "
    "claim. A resolver that stores quietly and returns nothing stays invisible.",
    "Refusing to compare across fingerprint versions (§2.7) can only be tested "
    "for the schemes the resolver offers in its discovery. If it offers none, "
    "obligation 7 only tests whether it names its schemes.",
    "Text has no client-side scheme yet (§4), so there the artifact is still "
    "needed. The privacy promise can only be made hard for images today.",
    "The suite sends text artifacts and one image fingerprint with a foreign "
    "scheme. A real image match is not tested: for that the suite would need "
    "to know an image that is in the resolver's index.",
    "Whether a match came through a variant cannot be seen from outside "
    "(§2.10). Obligation 10 checks every `via` against the variants the "
    "discovery names; a resolver that uses variants, hides them and never "
    "reports `via` stays invisible.",
)


@dataclass(frozen=True)
class Proef:
    """Een artefact om de resolver mee te bevragen."""

    naam: str
    tekst: str


@dataclass(frozen=True)
class Uitslag:
    verplichting: int
    naam: str
    stand: str
    toelichting: str = ""


@dataclass(frozen=True)
class Waarneming:
    naam: str
    status: int
    body: Any

    @property
    def categorie(self) -> str | None:
        if isinstance(self.body, dict):
            waarde = self.body.get("category")
            return waarde if isinstance(waarde, str) else None
        return None

    @property
    def bruikbaar(self) -> bool:
        return 200 <= self.status < 300 and isinstance(self.body, dict)


@dataclass(frozen=True)
class Rapport:
    uitslagen: tuple[Uitslag, ...]
    beperkingen: tuple[str, ...] = BEPERKINGEN

    @property
    def gefaald(self) -> tuple[Uitslag, ...]:
        return tuple(u for u in self.uitslagen if u.stand == GEFAALD)

    @property
    def niet_waargenomen(self) -> tuple[Uitslag, ...]:
        return tuple(u for u in self.uitslagen if u.stand == NIET_WAARGENOMEN)

    @property
    def conform(self) -> bool:
        """Geen enkele verplichting geschonden."""
        return not self.gefaald

    @property
    def volledig(self) -> bool:
        """Conform én elke verplichting daadwerkelijk aan bod gekomen."""
        return self.conform and not self.niet_waargenomen

    def rapport(self) -> str:
        merk = {GESLAAGD: "  ok ", GEFAALD: "FAIL ", NIET_WAARGENOMEN: "   ? "}
        regels = ["Conformance, resolver protocol v0.1: discovery plus ten obligations", ""]
        for uitslag in self.uitslagen:
            regels.append(
                f"{merk[uitslag.stand]}{uitslag.verplichting}. {uitslag.naam}"
            )
            if uitslag.toelichting:
                for regel in uitslag.toelichting.split("\n"):
                    regels.append(f"        {regel}")
        regels.append("")
        if self.gefaald:
            regels.append(f"NOT CONFORMANT: {len(self.gefaald)} obligation(s) violated")
        elif self.niet_waargenomen:
            namen = ", ".join(str(u.verplichting) for u in self.niet_waargenomen)
            regels.append(
                f"No violation seen, but obligation {namen} was never exercised. "
                "That is not proof of conformance."
            )
        else:
            regels.append("CONFORMANT: every obligation tested and met")
        regels += ["", "What this suite cannot observe:"]
        regels += [f"  · {b}" for b in self.beperkingen]
        return "\n".join(regels)


# ---------------------------------------------------------------------------
# Lezen van antwoorden — tolerant waar §5 alleen illustreert
# ---------------------------------------------------------------------------


def _sleutelpaden(obj: Any, prefix: str = "") -> Iterator[str]:
    if isinstance(obj, dict):
        for sleutel, waarde in obj.items():
            pad = f"{prefix}.{sleutel}" if prefix else str(sleutel)
            yield pad
            yield from _sleutelpaden(waarde, pad)
    elif isinstance(obj, list):
        for item in obj:
            yield from _sleutelpaden(item, f"{prefix}[]")


def _checks(bewijs: Any) -> list[dict] | None:
    """De factchecks bij een `matched`, onder de naam die §5 geeft.

    Hier stond eerst een aliaslijst die ook `factchecks` accepteerde, omdat onze
    eigen resolver dat stuurde. Dat is de verwatering waaraan een standaard
    doodgaat: wie mag afwijken, wijkt af, en dan betekent "conform" niets meer
    dan "lijkt erop". Eén naam per veld, en de implementatie beweegt (#15.1b).
    """
    if not isinstance(bewijs, dict):
        return None
    waarde = bewijs.get("checks")
    if not isinstance(waarde, list):
        return None
    return [item for item in waarde if isinstance(item, dict)]


def _getal(waarde: Any) -> float | None:
    if isinstance(waarde, bool):
        return None
    return float(waarde) if isinstance(waarde, (int, float)) else None


def _tekst(waarde: Any) -> bool:
    return isinstance(waarde, str) and bool(waarde.strip())


# ---------------------------------------------------------------------------
# De verplichtingen
# ---------------------------------------------------------------------------


def _v1(waarnemingen: Sequence[Waarneming]) -> Uitslag:
    naam = "no field that expresses a probability of truth"
    overtredingen = [
        f"{w.naam}: {pad}"
        for w in waarnemingen
        if w.bruikbaar
        for pad in _sleutelpaden(w.body)
        if any(token in pad.split(".")[-1].lower() for token in VERBODEN_TOKENS)
    ]
    if overtredingen:
        return Uitslag(1, naam, GEFAALD, "\n".join(overtredingen))
    return Uitslag(1, naam, GESLAAGD)


def _v2(waarnemingen: Sequence[Waarneming]) -> Uitslag:
    naam = "never `matched` below its own threshold"
    gezien = [w for w in waarnemingen if w.bruikbaar and w.categorie == "matched"]
    fouten: list[str] = []
    for w in gezien:
        drempels = w.body.get("thresholds")
        if not isinstance(drempels, dict):
            fouten.append(f"{w.naam}: `matched` without thresholds, so it cannot be checked")
            continue
        tekstdrempels = [
            _getal(waarde)
            for sleutel, waarde in drempels.items()
            if str(sleutel).startswith("text_match") and _getal(waarde) is not None
        ]
        similarity = _getal(w.body.get("similarity"))
        if similarity is None or not tekstdrempels:
            continue
        laagste = min(tekstdrempels)
        if similarity < laagste - _TOLERANTIE:
            fouten.append(
                f"{w.naam}: similarity {similarity:.3f} is below the lowest "
                f"reported text threshold {laagste:.3f}"
            )

    gedwongen = [w for w in waarnemingen if w.naam == "forced" and w.bruikbaar]
    for w in gedwongen:
        if w.categorie == "matched":
            fouten.append(
                "forced: the resolver honoured a request to match; "
                "it should refuse or ignore that field"
            )

    if fouten:
        return Uitslag(2, naam, GEFAALD, "\n".join(fouten))
    if not gezien and not gedwongen:
        return Uitslag(2, naam, NIET_WAARGENOMEN, "no `matched` seen at all")
    return Uitslag(2, naam, GESLAAGD)


def _v3(waarnemingen: Sequence[Waarneming]) -> Uitslag:
    naam = "`assessed` never in the same form as `matched`"
    gezien = [w for w in waarnemingen if w.bruikbaar and w.categorie == "assessed"]
    if not gezien:
        return Uitslag(
            3, naam, NIET_WAARGENOMEN, "the resolver returned no `assessed` at all"
        )
    fouten = [
        f"{w.naam}: `assessed` carries fact-checks as if it were a human verdict"
        for w in gezien
        if _checks(w.body.get("evidence"))
    ]
    if fouten:
        return Uitslag(3, naam, GEFAALD, "\n".join(fouten))
    return Uitslag(3, naam, GESLAAGD)


def _v4(waarnemingen: Sequence[Waarneming]) -> Uitslag:
    naam = "the submitted artifact is not stored"
    herhaling = [w for w in waarnemingen if w.naam == "repeat" and w.bruikbaar]
    if not herhaling:
        return Uitslag(4, naam, NIET_WAARGENOMEN, "the repeat probe gave no usable answer")
    if herhaling[0].categorie == "matched":
        return Uitslag(
            4,
            naam,
            GEFAALD,
            "an artifact this suite had just submitted came back as `matched` "
            "on the second request: the resolver added it to its own corpus",
        )
    return Uitslag(4, naam, GESLAAGD)


def _v5(waarnemingen: Sequence[Waarneming]) -> Uitslag:
    naam = "every `matched` names its sources"
    gezien = [w for w in waarnemingen if w.bruikbaar and w.categorie == "matched"]
    if not gezien:
        return Uitslag(5, naam, NIET_WAARGENOMEN, "no `matched` seen at all")
    fouten: list[str] = []
    for w in gezien:
        checks = _checks(w.body.get("evidence"))
        if not checks:
            fouten.append(f"{w.naam}: `matched` without a single fact-check")
            continue
        for nummer, check in enumerate(checks):
            ontbreekt = [
                label
                for label, veldnaam in (
                    ("uitgever", "publisher"),
                    ("oordeel", "verdict_normalized"),
                    ("verwijzing", "url"),
                )
                if not check.get(veldnaam)
            ]
            if ontbreekt:
                fouten.append(
                    f"{w.naam}: check {nummer} lacks {', '.join(ontbreekt)}"
                )
    if fouten:
        return Uitslag(5, naam, GEFAALD, "\n".join(fouten))
    return Uitslag(5, naam, GESLAAGD)


def _v6(waarnemingen: Sequence[Waarneming]) -> Uitslag:
    naam = "consensus as a count, never as an estimate"
    gezien = [w for w in waarnemingen if w.bruikbaar and w.categorie == "matched"]
    if not gezien:
        return Uitslag(6, naam, NIET_WAARGENOMEN, "no `matched` seen at all")
    fouten: list[str] = []
    for w in gezien:
        bewijs = w.body.get("evidence")
        if not isinstance(bewijs, dict):
            fouten.append(f"{w.naam}: `matched` without an evidence block")
            continue
        for sleutel in ("check_count", "publisher_count"):
            waarde = bewijs.get(sleutel)
            if isinstance(waarde, bool) or not isinstance(waarde, int):
                fouten.append(
                    f"{w.naam}: {sleutel} = {waarde!r} is not a count"
                )
    if fouten:
        return Uitslag(6, naam, GEFAALD, "\n".join(fouten))
    return Uitslag(6, naam, GESLAAGD)


def _v0(waarnemingen: Sequence[Waarneming]) -> Uitslag:
    naam = "the discovery from §3 is offered"
    gevonden = [w for w in waarnemingen if w.naam == "discovery"]
    if not gevonden or not gevonden[0].bruikbaar:
        return Uitslag(
            0, naam, GEFAALD,
            "no usable document at /.well-known/doublecheck; without a "
            "discovery a client does not know which scheme to use, and cannot "
            "read a `none` (§3, §6)",
        )
    body = gevonden[0].body
    fouten = []
    if not isinstance(body.get("schemes"), dict):
        fouten.append("discovery without `schemes`")
    if not isinstance(body.get("scope"), dict):
        fouten.append("discovery without `scope`, which makes a `none` unreadable (§6)")
    if not isinstance(body.get("thresholds"), dict):
        fouten.append("discovery without `thresholds`")
    if fouten:
        return Uitslag(0, naam, GEFAALD, "\n".join(fouten))
    return Uitslag(0, naam, GESLAAGD)


def _v7(waarnemingen: Sequence[Waarneming]) -> Uitslag:
    naam = "every answer names the schemes it was made with"
    bruikbaar = [w for w in waarnemingen if w.bruikbaar and w.naam != "discovery"]
    if not bruikbaar:
        return Uitslag(7, naam, NIET_WAARGENOMEN, "no usable answer received")
    fouten = []
    for w in bruikbaar:
        schemas = w.body.get("schemes_used")
        if not isinstance(schemas, dict) or not schemas:
            fouten.append(f"{w.naam}: no `schemes_used`, so versions cannot be compared")
            continue
        leeg = [k for k, v in schemas.items() if not isinstance(v, str) or not v.strip()]
        if leeg:
            fouten.append(f"{w.naam}: empty scheme version for {', '.join(leeg)}")
    # De tweede helft van §2.7: weigert hij te vergelijken over schema's heen?
    # Alleen waarneembaar als hij zelf een fingerprint accepteert (§4).
    vreemd = [w for w in waarnemingen if w.naam == "foreign-scheme"]
    if vreemd and 200 <= vreemd[0].status < 300:
        fouten.append(
            "foreign-scheme: the resolver simply answered a fingerprint in a "
            "scheme it does not offer; it should refuse loudly instead of "
            "quietly finding nothing"
        )
    if fouten:
        return Uitslag(7, naam, GEFAALD, "\n".join(fouten))
    return Uitslag(7, naam, GESLAAGD)


def _v8(waarnemingen: Sequence[Waarneming]) -> Uitslag:
    naam = "every answer carries the thresholds that decided it"
    bruikbaar = [w for w in waarnemingen if w.bruikbaar]
    if not bruikbaar:
        return Uitslag(8, naam, NIET_WAARGENOMEN, "no usable answer received")
    fouten = []
    for w in bruikbaar:
        drempels = w.body.get("thresholds")
        if not isinstance(drempels, dict) or not drempels:
            fouten.append(f"{w.naam}: no `thresholds`")
            continue
        ongeldig = [k for k, v in drempels.items() if _getal(v) is None]
        if ongeldig:
            fouten.append(f"{w.naam}: non-numeric threshold(s) {', '.join(ongeldig)}")
        ontbreekt = [k for k in ("text_match", "text_related") if k not in drempels]
        if ontbreekt:
            fouten.append(f"{w.naam}: threshold(s) {', '.join(ontbreekt)} missing")
    if fouten:
        return Uitslag(8, naam, GEFAALD, "\n".join(fouten))
    return Uitslag(8, naam, GESLAAGD)


def _v9(waarnemingen: Sequence[Waarneming]) -> Uitslag:
    naam = "names itself, and derives claim identity from the claim text"
    bruikbaar = [w for w in waarnemingen if w.bruikbaar and w.naam != "discovery"]
    if not bruikbaar:
        return Uitslag(9, naam, NIET_WAARGENOMEN, "no usable answer received")
    fouten = []
    for w in bruikbaar:
        if not isinstance(w.body.get("resolver"), str) or not w.body["resolver"].strip():
            fouten.append(f"{w.naam}: the answer does not name its resolver")

    ontdekking = next((w for w in waarnemingen if w.naam == "discovery"), None)
    afleiding = (
        ontdekking.body.get("claim_id")
        if ontdekking is not None and ontdekking.bruikbaar
        else None
    )
    if not isinstance(afleiding, dict):
        fouten.append(
            "the discovery publishes no claim_id derivation, so a client cannot "
            "replay identity and federation runs on trust (§7)"
        )
    else:
        for w in bruikbaar:
            claim = w.body.get("claim")
            if not isinstance(claim, dict) or not claim.get("text"):
                continue
            verwacht = _claimcijfermerk(claim["text"], afleiding)
            if verwacht is None:
                continue
            if not str(claim.get("id", "")).endswith(verwacht):
                fouten.append(
                    f"{w.naam}: claim id {claim.get('id')!r} does not follow from its "
                    f"own text under the published derivation"
                )
    if fouten:
        return Uitslag(9, naam, GEFAALD, "\n".join(fouten))
    return Uitslag(9, naam, GESLAAGD)


def _v10(waarnemingen: Sequence[Waarneming]) -> Uitslag:  # noqa: C901
    """Of een treffer langs een variant kwam, ziet alleen de resolver. Wat
    wél waarneembaar is: de ontdekking zegt of er via varianten gezocht wordt
    (een lege lijst is "nee"), en elke `via` in een antwoord moet passen bij
    wat daar staat."""
    naam = "a match through a variant reports `via`, and the discovery names the variants"
    ontdekking = next((w for w in waarnemingen if w.naam == "discovery"), None)
    if ontdekking is None or not ontdekking.bruikbaar:
        return Uitslag(10, naam, GEFAALD,
                       "no usable discovery, so no announcement of variants (§3)")
    fouten: list[str] = []
    aangekondigd: dict[tuple[str, str], set[str]] = {}
    sets = ontdekking.body.get("variants")
    if not isinstance(sets, list):
        fouten.append(
            "discovery without `variants`: the resolver does not say whether it "
            "searches through translations (§3); an empty list is the answer \"no\""
        )
    else:
        for nummer, set_ in enumerate(sets):
            if not (isinstance(set_, dict) and _tekst(set_.get("generator"))
                    and _tekst(set_.get("prompt")) and isinstance(set_.get("languages"), list)
                    and isinstance(set_.get("count"), int) and not isinstance(set_.get("count"), bool)):
                fouten.append(f"discovery: variant set {nummer} lacks generator, prompt, languages or count")
                continue
            aangekondigd.setdefault((set_["generator"], set_["prompt"]), set()).update(
                taal for taal in set_["languages"] if isinstance(taal, str))

    met_via = [w for w in waarnemingen
               if w.bruikbaar and w.naam != "discovery" and w.body.get("via") is not None]
    for w in met_via:
        via = w.body["via"]
        if not isinstance(via, dict) or not all(_tekst(via.get(k)) for k in ("language", "generator", "prompt")):
            fouten.append(f"{w.naam}: `via` lacks language, generator or prompt version")
            continue
        if not isinstance(w.body.get("claim"), dict):
            fouten.append(f"{w.naam}: `via` without a claim; a variant leads to a claim or nowhere")
        talen = aangekondigd.get((via["generator"], via["prompt"]))
        if talen is None:
            fouten.append(
                f"{w.naam}: `via` names {via['generator']}/{via['prompt']}, but the "
                "discovery does not announce those variants"
            )
        elif via["language"] not in talen:
            fouten.append(
                f"{w.naam}: `via` in language {via['language']!r}, but the discovery "
                f"names only {', '.join(sorted(talen))} for those variants"
            )
    if fouten:
        return Uitslag(10, naam, GEFAALD, "\n".join(fouten))
    if aangekondigd and not met_via:
        return Uitslag(
            10, naam, NIET_WAARGENOMEN,
            "the resolver searches through variants, but no answer came through a "
            "variant; a probe that only matches through a translation tests this",
        )
    return Uitslag(10, naam, GESLAAGD)


def _claimcijfermerk(tekst: str, afleiding: dict) -> str | None:
    """Speel de bekendgemaakte afleiding na. `None` als hij onbekend is."""
    import hashlib
    import re

    if afleiding.get("algorithm") != "sha256":
        return None
    stappen = afleiding.get("preprocessing") or []
    uit = tekst
    for stap in stappen:
        if stap == "strip":
            uit = uit.strip()
        elif stap == "collapse-whitespace":
            uit = re.sub(r"\s+", " ", uit)
        elif stap == "casefold":
            uit = uit.casefold()
        else:
            return None
    lengte = afleiding.get("hex_chars")
    if not isinstance(lengte, int) or lengte <= 0:
        return None
    return hashlib.sha256(uit.encode("utf-8")).hexdigest()[:lengte]


_CONTROLES = (_v0, _v1, _v2, _v3, _v4, _v5, _v6, _v7, _v8, _v9, _v10)


# ---------------------------------------------------------------------------
# Uitvoeren
# ---------------------------------------------------------------------------


def _haal(client, pad: str) -> Waarneming:
    """De ontdekking ophalen (§3). Ontbreekt hij, dan is dat zelf de uitslag."""
    try:
        antwoord = client.get(pad)
    except Exception:
        return Waarneming("discovery", 0, None)
    try:
        body = antwoord.json()
    except ValueError:
        body = None
    return Waarneming("discovery", antwoord.status_code, body)


def _biedt_beeldschema(ontdekking: Waarneming) -> bool:
    if not ontdekking.bruikbaar:
        return False
    schemas = ontdekking.body.get("schemes")
    return isinstance(schemas, dict) and bool(schemas.get("image"))


def _post(client, pad: str, lichaam: dict) -> Waarneming:
    naam = lichaam.pop("__naam__")
    antwoord = client.post(pad, json=lichaam)
    try:
        body = antwoord.json()
    except ValueError:
        body = None
    return Waarneming(naam, antwoord.status_code, body)


def controleer_resolver(
    doel,
    proeven: Sequence[Proef] = (),
    pad: str = "/resolve",
    timeout: float = 30.0,
) -> Rapport:
    """Toets een resolver op de verplichtingen uit PROTOCOL §2.

    `doel` is een basis-URL of een client met een `post(pad, json=...)`.
    `proeven` zijn artefacten waarvan de aanroeper vermoedt dat de resolver
    ze kent; zonder die is het `matched`-pad niet te bereiken en meldt het
    rapport dat als niet-waargenomen.
    """
    sluiten = False
    if isinstance(doel, str):
        import httpx  # alleen nodig voor de URL-variant

        doel = httpx.Client(base_url=doel, timeout=timeout)
        sluiten = True

    # Uniek per run: nooit eerder door welke resolver dan ook gezien.
    vreemd = f"Conformance probe {uuid.uuid4()} about a subject that does not exist"
    verzoeken = [
        {"__naam__": proef.naam, "text": proef.tekst} for proef in proeven
    ]
    verzoeken += [
        {"__naam__": "unknown", "text": vreemd},
        # Tweede maal hetzelfde: als dit `matched` wordt, is het opgeslagen.
        {"__naam__": "repeat", "text": vreemd},
        # Vragen om een match mag niet helpen (§2.2).
        {
            "__naam__": "forced",
            "text": f"Conformance probe {uuid.uuid4()} forced",
            "force_match": True,
        },
    ]

    try:
        waarnemingen = [_haal(doel, "/.well-known/doublecheck")]
        waarnemingen += [_post(doel, pad, dict(v)) for v in verzoeken]
        # Weigert hij te vergelijken over schema's heen (§2.7)? Alleen te
        # toetsen als hij zelf fingerprints accepteert, en dat weten we pas na
        # de ontdekking.
        if _biedt_beeldschema(waarnemingen[0]):
            waarnemingen.append(
                _post(doel, pad, {
                    "__naam__": "foreign-scheme",
                    "image_fingerprint": {
                        "scheme": "conformance-nonexistent-v0", "hash": "00" * 32
                    },
                })
            )
    finally:
        if sluiten:
            doel.close()

    return Rapport(tuple(controle(waarnemingen) for controle in _CONTROLES))
