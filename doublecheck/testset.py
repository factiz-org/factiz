"""Testset voor de benchmark: formaat (3.1) en bouwer (3.2).

Een testpaar bestaat uit een verwijzing (claim_id), een label (zelfde claim of
niet), herkomst, taal en de fingerprint van de artefact-kant. De artefacttekst
zelf wordt bij het bouwen gefingerprint en weggegooid — hij bestaat nergens in
de opslag (E4.S1-AC3, DR3). Fingerprints dragen hun modelversie (DR6): na een
modelwissel is de testset herbouwen onderdeel van herindexeren.

De bouwer werkt met waarheid-door-constructie, zodat labels niet afhangen van
het model dat gemeten wordt:
- zelfde claim (is_same=1): `origineel`, `vervorming` (virale aankleding),
  `inkorting` (kop afgekapt; overgeslagen bij claims met een ontkenning, want
  afkappen mag de betekenis niet omdraaien);
- sterk lijkende niet-match (is_same=0): `ontkenning` (mechanisch ingevoegde
  negatie — de risicoklasse van taak 1.11), `cijferwissel` (zelfde bewering,
  ander getal), en `hardste-buur` (dichtstbijzijnde ándere claim van dezelfde
  uitgever — één uitgever checkt elke bewering één keer, dus dat is structureel
  een andere claim; selectie op nabijheid maakt de test zwaarder, niet lichter).
"""

from __future__ import annotations

import json
import random
import re
import sqlite3
import unicodedata
from dataclasses import dataclass

import numpy as np

from doublecheck.embedding import TextFingerprint
from doublecheck.relation import derivation_version, extract_negations


@dataclass(frozen=True)
class TestPair:
    # Geen pytest-testklasse, ondanks het naamvoorvoegsel.
    __test__ = False

    claim_id: str
    is_same: bool
    provenance: str
    language: str
    fingerprint: TextFingerprint  # of ImageFingerprint bij kind == "image"

    @property
    def kind(self) -> str:
        return "text" if hasattr(self.fingerprint, "vector") else "image"


def save_test_pair(conn: sqlite3.Connection, pair: TestPair) -> None:
    if pair.kind == "text":
        payload = pair.fingerprint.vector.tobytes()
        getallen = json.dumps(sorted(pair.fingerprint.numbers))
        # Mét herhalingen waar bekend (#25.1c); anders de verzameling.
        negaties = json.dumps(
            list(pair.fingerprint.negation_tokens)
            if pair.fingerprint.negation_tokens
            else sorted(pair.fingerprint.negations)
        )
    else:
        payload = pair.fingerprint.hash_hex.encode("ascii")
        getallen = negaties = "[]"
    conn.execute(
        "INSERT INTO testpair (claim_id, is_same, provenance, language,"
        " model_version, payload, numbers, negations, kind, derivation_version,"
        " artefact_language)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            pair.claim_id,
            1 if pair.is_same else 0,
            pair.provenance,
            pair.language,
            pair.fingerprint.model_version,
            payload,
            getallen,
            negaties,
            pair.kind,
            derivation_version(),
            getattr(pair.fingerprint, "language", None) or "",
        ),
    )


class DerivationVersionMismatchError(Exception):
    """De testset draagt afleidingen van een andere codeversie (#11.5, DR6-analoog)."""


def ensure_testset_matches_derivation(conn: sqlite3.Connection) -> None:
    """Weigert luid wanneer opgeslagen afleidingen niet van deze code komen.

    Analoog aan de modelversie-guard (DR6): liever hard stoppen dan stil een
    cijfer rapporteren over data die met andere extractiecode is gemaakt. Een
    lege testset is géén mismatch — dat is de legitieme beginstand. Een rij
    zónder vastgelegde versie wél: dat is onbekende herkomst, en precies het
    geval dat de runs #9 en #10 heeft aangetast (BENCHMARK.md §19c).
    """
    huidig = derivation_version()
    aanwezig = {
        rij["derivation_version"]
        for rij in conn.execute("SELECT DISTINCT derivation_version FROM testpair")
    }
    afwijkend = aanwezig - {huidig}
    if afwijkend:
        getoond = sorted(v or "(niet vastgelegd)" for v in afwijkend)
        raise DerivationVersionMismatchError(
            f"testset bevat afleidingsversie(s) {getoond}, deze code levert"
            f" {huidig!r}; herbouw de testset met python -m doublecheck.testset"
        )


def load_test_pairs(conn: sqlite3.Connection) -> list[TestPair]:
    from doublecheck.image_fingerprint import ImageFingerprint

    paren = []
    for rij in conn.execute(
        "SELECT claim_id, is_same, provenance, language, model_version, payload,"
        " numbers, negations, kind, artefact_language FROM testpair"
        " ORDER BY testpair_id"
    ):
        if rij["kind"] == "image":
            hash_hex = rij["payload"].decode("ascii")
            fingerprint = ImageFingerprint(
                hash_hex=hash_hex,
                model_version=rij["model_version"],
                bits=len(hash_hex) * 4,
            )
        else:
            vector = np.frombuffer(rij["payload"], dtype=np.float32)
            vector.setflags(write=False)
            fingerprint = TextFingerprint(
                vector=vector,
                model_version=rij["model_version"],
                numbers=frozenset(json.loads(rij["numbers"])),
                negations=frozenset(json.loads(rij["negations"])),
                negation_tokens=tuple(sorted(json.loads(rij["negations"]))),
                language=rij["artefact_language"] or None,
            )
        paren.append(
            TestPair(
                claim_id=rij["claim_id"],
                is_same=bool(rij["is_same"]),
                provenance=rij["provenance"],
                language=rij["language"],
                fingerprint=fingerprint,
            )
        )
    return paren


# Aandelen per markt. Bij de ES-uitrol (#11.4) verhoogd van 1.000 naar 1.500
# paren in plaats van de bestaande talen te verdunnen: zo houden nl/de/fr/en
# ongeveer hun absolute aantallen (520/280/120/80) en blijven hun cijfers
# vergelijkbaar met eerdere runs, terwijl Spaans eigen statistische kracht krijgt.
# Catalaans (922 claims) kwam mee met verificat.cat maar krijgt geen aandeel: een
# markt gaat live met een eigen benchmark, niet met een eigen corpus (B14).
DEFAULT_LANGUAGE_SHARES = {"nl": 0.35, "de": 0.19, "es": 0.33, "fr": 0.08, "en": 0.05}

# (patroon, vervanging) per taal; alleen de eerste toepasbare wordt gebruikt.
_NEGATIE_PATRONEN = {
    "nl": ((" is ", " is niet "), (" zijn ", " zijn niet "), (" heeft ", " heeft geen "),
           (" wordt ", " wordt niet "), (" kan ", " kan niet ")),
    "en": ((" is ", " is not "), (" are ", " are not "), (" has ", " has no "),
           (" can ", " cannot "), (" will ", " will not ")),
    "de": ((" ist ", " ist nicht "), (" sind ", " sind nicht "),
           (" hat ", " hat kein "), (" kann ", " kann nicht ")),
    "fr": ((" est ", " n'est pas "), (" sont ", " ne sont pas "),
           (" peut ", " ne peut pas "), (" a été ", " n'a pas été "),
           (" ont ", " n'ont pas ")),
    "es": ((" es ", " no es "), (" son ", " no son "), (" está ", " no está "),
           (" tiene ", " no tiene "), (" puede ", " no puede "),
           (" ha ", " no ha "), (" han ", " no han ")),
    # #25.1: talen die de productiewachter (relation._NEGATIE) nog niet kent.
    # Juist daarom in de testset: de meting moet het gat laten zien. Mechanisch
    # en soms onelegant, maar het label klopt per constructie: de variant is
    # een ándere bewering.
    "pt": ((" é ", " não é "), (" são ", " não são "), (" tem ", " não tem "),
           (" pode ", " não pode "), (" foi ", " não foi "), (" vai ", " não vai ")),
    "it": ((" è ", " non è "), (" sono ", " non sono "), (" ha ", " non ha "),
           (" può ", " non può "), (" sarà ", " non sarà ")),
    "ru": ((" является ", " не является "), (" был ", " не был "),
           (" была ", " не была "), (" были ", " не были "),
           (" может ", " не может "), (" будет ", " не будет ")),
    "id": ((" adalah ", " bukan "), (" akan ", " tidak akan "),
           (" bisa ", " tidak bisa "), (" dapat ", " tidak dapat "),
           (" sudah ", " belum ")),
    "hi": ((" हैं", " नहीं हैं"), (" है", " नहीं है"), (" थे", " नहीं थे"),
           (" था", " नहीं था")),
    # #25.20: de Zuid-Aziatische talen met testparen. In de Dravidische talen
    # hangt de ontkenning aan het werkwoord, dus de vervanging pakt het hele
    # werkwoord ("செய்யப்பட்டது" → "செய்யப்படவில்லை"). Het langste patroon
    # eerst; een patroon telt alleen op een woordeinde (`_WOORDEINDE_TALEN`).
    "ta": (("ப்பட்டுள்ளது", "ப்படவில்லை"), ("ப்பட்டது", "ப்படவில்லை"),
           (" உள்ளது", " இல்லை"), (" ஆகும்", " அல்ல")),
    "te": (("జరిగింది", "జరగలేదు"), ("చేశారు", "చేయలేదు"), ("ఇచ్చారు", "ఇవ్వలేదు"),
           ("అయింది", "కాలేదు"), (" ఉంది", " లేదు")),
    "ml": (("ചെയ്തു", "ചെയ്തില്ല"), (" ഉണ്ട്", " ഇല്ല"), (" ആണ്", " അല്ല")),
    "kn": (("ಮಾಡಿದ್ದಾರೆ", "ಮಾಡಿಲ್ಲ"), (" ಆಗಿದೆ", " ಆಗಿಲ್ಲ"), (" ಇದೆ", " ಇಲ್ಲ")),
    # Bengaals schrijft য় op twee manieren: samengesteld (U+09DF) en als য
    # plus nukta (U+09AF U+09BC); het corpus heeft ze allebei.
    "bn": (("\u09b9\u09af\u09bc\u09c7\u099b\u09c7", "\u09b9\u09af\u09bc\u09a8\u09bf"),
           ("\u09b9\u09df\u09c7\u099b\u09c7", "\u09b9\u09df\u09a8\u09bf"),
           ("করেছে", "করেনি"), (" আছে", " নেই"), (" হবে", " হবে না")),
    "si": ((" ඇත", " නැත"), (" වේ", " නොවේ")),
}
# In deze talen telt een patroon alleen als het op een woordeinde valt: anders
# wordt " වේ" (is) ook gevonden in "වේගය" (snelheid) en "ப்பட்டது" in
# "செய்யப்பட்டதும்" (en werd gedaan). Bewust niet voor de oudere talen: hun
# paren worden met `_negation_variant` herleid (#25.1b), en dat moet hetzelfde
# blijven geven.
_WOORDEINDE_TALEN = frozenset({"ta", "te", "ml", "kn", "bn", "si"})


def _op_woordeinde(text: str, eind: int) -> bool:
    return eind >= len(text) or unicodedata.category(text[eind])[0] not in "LM"
def _bevat_negatie(text: str) -> bool:
    """Eén definitie van "ontkenning", gedeeld met het productpad.

    Stond hier eerder als eigen tokenlijst met substring-matching, en dat liep
    uit elkaar én zat er naast: `"ne "` vlagde `"une "`, `"nie "` vlagde
    `"Unie "`. Daardoor werd 32% van de Franse en 10% van de Nederlandse claims
    ten onrechte overgeslagen bij het bouwen van ontkenningsparen — precies de
    is_same=0-klasse die G1 bewaakt (BENCHMARK.md §20).

    Een dubbele ontkenning zou hier alsnog kunnen ontstaan als het productpad er
    één mist, maar het label blijft dan correct: "niet niet X" is nog steeds een
    ándere bewering dan "niet X".
    """
    return bool(extract_negations(text))


def _negation_variant(text: str, language: str, *, controleer: bool = True) -> str | None:
    """Mechanische ontkenning: per constructie een andere, sterk lijkende claim.

    `controleer=False` slaat de bouwregel over (geen variant van een al ontkende
    zin) en past alleen de transformatie toe; dat is voor het herleiden van
    paren die met een oudere ontkenningsdetectie gebouwd zijn (#25.1b)."""
    if controleer and _bevat_negatie(text):
        return None
    for patroon, vervanging in _NEGATIE_PATRONEN.get(language, ()):
        if language in _WOORDEINDE_TALEN:
            start = text.find(patroon)
            while start != -1 and not _op_woordeinde(text, start + len(patroon)):
                start = text.find(patroon, start + 1)
            if start != -1:
                return text[:start] + vervanging + text[start + len(patroon):]
        elif patroon in text:
            return text.replace(patroon, vervanging, 1)
    return None


def _digit_swap_variant(text: str) -> str | None:
    """Zelfde bewering, ander getal: het eerste getal wordt deterministisch verhoogd."""
    treffer = re.search(r"\d+", text)
    if treffer is None:
        return None
    getal = int(treffer.group())
    return text[: treffer.start()] + str(getal + 7) + text[treffer.end():]


# Schriften die scriptio continua schrijven: geen spatie tussen woorden, dus
# `split()` levert er één lang "woord" op en het woordafkappen heeft niets te doen.
#
# Dit is bewust een schriftlijst en geen taallijst. Het schrift is een
# typografische eigenschap die je aan de tekens zelf kunt aflezen; de taal zou
# een aanname zijn. Een eerdere poging met een structurele maat (gemiddelde
# tokenlengte boven 12) sneuvelde op het corpus: "Q10-suppletie verbetert
# sportprestaties." haalt 13,3 en zou middenin een woord zijn afgekapt —
# Nederlandse en Duitse samenstellingen halen die drempel gewoon (PLAN.md #11.2).
_ZONDER_SPATIES_SCHRIFTEN = (
    "CJK",
    "HIRAGANA",
    "KATAKANA",
    "THAI",
    "KHMER",
    "LAO",
    "MYANMAR",
    "TIBETAN",
)
# Genoeg materiaal om 60% van af te kappen en nog een bewering over te houden;
# het spatiepad eist analoog acht woorden.
_MIN_TEKENS_INKORTING = 16


def _zonder_woordspaties(text: str) -> bool:
    letters = [teken for teken in text if teken.isalpha()]
    if not letters:
        return False
    continua = sum(
        unicodedata.name(teken, "").startswith(_ZONDER_SPATIES_SCHRIFTEN)
        for teken in letters
    )
    return continua > len(letters) / 2


def _dressing_variant(text: str, keuze: int) -> str:
    """Virale aankleding; verandert de bewering zelf niet.

    Vormen die de bron ongewijzigd teruggeven vallen af: `.upper()` is een no-op
    in schriften zonder hoofdletters (Arabisch, Han, Devanagari, Bengaals), en een
    artefact dat gelijk is aan zijn claim meet niets — het levert gelijkenis 1,000
    op zonder iets te bewijzen (BENCHMARK.md §17a). De omhullende vormen voegen
    altijd tekens toe, dus er blijft altijd minstens één vorm over.
    """
    vormen = tuple(
        vorm
        for vorm in (
            text.upper(),
            f'"{text}"',
            f">>> {text} <<<",
            f"{text}!!!",
        )
        if vorm != text
    )
    return vormen[keuze % len(vormen)]


def _truncation_variant(text: str, *, controleer: bool = True) -> str | None:
    """Kop afgekapt: een prefix die korter is maar nog steeds de bewering draagt.

    Afkappen gebeurt op woorden waar spaties bestaan (geen halve woorden), en op
    tekens in schriften die geen woordspaties kennen. Ontkenningen blokkeren de
    inkorting onverkort — afkappen mag de betekenis niet omdraaien.
    """
    if controleer and _bevat_negatie(text):
        return None
    if _zonder_woordspaties(text):
        if len(text) < _MIN_TEKENS_INKORTING:
            return None
        return text[: int(len(text) * 0.6)]
    woorden = text.split()
    if len(woorden) < 8:
        return None
    return " ".join(woorden[: max(6, int(len(woorden) * 0.6))])


@dataclass(frozen=True)
class TestsetReport:
    total: int
    per_language: dict[str, int]
    per_provenance: dict[str, int]
    same_pairs: int
    lookalike_pairs: int


def _language_targets(total, shares, beschikbaar):
    aanwezig = {taal: aandeel for taal, aandeel in shares.items() if beschikbaar.get(taal)}
    som = sum(aanwezig.values())
    doelen = {taal: int(round(total * aandeel / som)) for taal, aandeel in aanwezig.items()}
    # Afrondingsdrift corrigeren op de grootste taal.
    drift = total - sum(doelen.values())
    grootste = max(doelen, key=doelen.get)
    doelen[grootste] += drift
    return doelen


# Paarsoort → (fractie van het taaldoel, is_same).
_MIX = (
    ("origineel", 0.10, True),
    ("vervorming", 0.25, True),
    ("inkorting", 0.15, True),
    ("ontkenning", 0.15, False),
    ("cijferwissel", 0.20, False),
    ("hardste-buur", 0.15, False),
)
# Talen zonder ontkenningsregel: dat aandeel gaat naar de hardste buur, die het
# model zelf moet scheiden. Zwaarder, niet lichter (#25.1).
_MIX_ZONDER_ONTKENNING = (
    ("origineel", 0.10, True),
    ("vervorming", 0.25, True),
    ("inkorting", 0.15, True),
    ("cijferwissel", 0.20, False),
    ("hardste-buur", 0.30, False),
)


def build_testset(
    conn: sqlite3.Connection,
    fingerprinter,
    *,
    total: int = 1000,
    language_shares: dict[str, float] | None = None,
    rng_seed: int = 42,
) -> TestsetReport:
    conn.execute("DELETE FROM testpair")
    rng = random.Random(rng_seed)
    shares = language_shares or DEFAULT_LANGUAGE_SHARES
    return _bouw_talen(
        conn,
        fingerprinter,
        doelen_voor=lambda per_taal: _language_targets(total, shares, per_taal),
        rng=rng,
        mix_voor=lambda taal: _MIX,
    )


def ontbrekende_talen(conn: sqlite3.Connection, *, min_claims: int) -> list[str]:
    """Talen met minstens `min_claims` claims en nog geen enkel testpaar.
    `und` (onbepaald) is geen taal en telt nooit mee."""
    gemeten = {rij[0] for rij in conn.execute("SELECT DISTINCT language FROM testpair")}
    rijen = conn.execute(
        "SELECT language, count(*) FROM claim WHERE language NOT IN ('', 'und')"
        " GROUP BY language HAVING count(*) >= ? ORDER BY language",
        (min_claims,),
    ).fetchall()
    return [rij[0] for rij in rijen if rij[0] not in gemeten]


def voeg_talen_toe(
    conn: sqlite3.Connection,
    fingerprinter,
    talen,
    *,
    per_taal: int = 200,
    rng_seed: int = 42,
) -> TestsetReport:
    """Additief: bestaande paren blijven staan, zodat eerdere runs vergelijkbaar
    blijven (#25.1). Een taal die al paren heeft wordt geweigerd: twee
    bouwrondes door elkaar in één taal zijn niet meer te verantwoorden."""
    talen = list(dict.fromkeys(talen))
    al = {rij[0] for rij in conn.execute("SELECT DISTINCT language FROM testpair")}
    dubbel = sorted(set(talen) & al)
    if dubbel:
        raise ValueError(f"taal/talen {dubbel} hebben al testparen; bouw die opnieuw of laat ze staan")
    rapport = _bouw_talen(
        conn,
        fingerprinter,
        doelen_voor=lambda claims_per_taal: {
            taal: per_taal for taal in talen if claims_per_taal.get(taal)
        },
        rng=random.Random(rng_seed),
        mix_voor=lambda taal: _MIX if taal in _NEGATIE_PATRONEN else _MIX_ZONDER_ONTKENNING,
    )
    return rapport


def voeg_ontkenningsparen_toe(conn, fingerprinter, talen, *, per_taal: int = 30,
                              rng_seed: int = 2520) -> dict[str, int]:
    """Ontkenningsparen erbij in talen die al testparen hebben (#25.20),
    additief zoals #25.1: bestaande paren blijven onaangeraakt, en een claim
    die al paren heeft wordt geen anker. Een taal die al ontkenningsparen
    heeft wordt geweigerd: twee rondes door elkaar zijn niet te verantwoorden."""
    from doublecheck.toelating import buiten_index

    talen = list(dict.fromkeys(talen))
    al = [t for t in talen if conn.execute(
        "SELECT 1 FROM testpair WHERE language = ? AND provenance = 'ontkenning'", (t,)).fetchone()]
    if al:
        raise ValueError(f"taal/talen {al} hebben al ontkenningsparen; bouw die opnieuw of laat ze staan")
    bezet = {r[0] for r in conn.execute("SELECT claim_id FROM testpair")}
    buiten = buiten_index(conn)
    rng = random.Random(rng_seed)
    aantallen: dict[str, int] = {}
    for taal in talen:
        ankers = [r for r in conn.execute(
            "SELECT claim.claim_id, claim.canonical_text FROM claim JOIN fingerprint USING (claim_id)"
            " WHERE claim.language = ? AND fingerprint.kind = 'text' AND fingerprint.model_version = ?"
            " ORDER BY claim.claim_id", (taal, fingerprinter.model_version))
            if r[0] not in bezet and r[0] not in buiten]
        rng.shuffle(ankers)
        gemaakt = 0
        for claim_id, tekst in ankers:
            if gemaakt >= per_taal:
                break
            variant = _negation_variant(tekst, taal)
            if variant is None:
                continue
            save_test_pair(conn, TestPair(claim_id=claim_id, is_same=False, provenance="ontkenning",
                                          language=taal, fingerprint=fingerprinter(variant)))
            gemaakt += 1
        aantallen[taal] = gemaakt
    conn.commit()
    return aantallen


def _bouw_talen(conn, fingerprinter, *, doelen_voor, rng, mix_voor) -> TestsetReport:
    claims = conn.execute(
        "SELECT claim.claim_id, claim.canonical_text, claim.language"
        " FROM claim JOIN fingerprint ON fingerprint.claim_id = claim.claim_id"
        " WHERE fingerprint.kind = 'text' AND fingerprint.model_version = ?",
        (fingerprinter.model_version,),
    ).fetchall()
    per_taal: dict[str, list] = {}
    for rij in claims:
        per_taal.setdefault(rij["language"], []).append(rij)

    vectoren = {
        rij["claim_id"]: np.frombuffer(rij["payload"], dtype=np.float32)
        for rij in conn.execute(
            "SELECT claim_id, payload FROM fingerprint"
            " WHERE kind = 'text' AND model_version = ?",
            (fingerprinter.model_version,),
        )
    }
    uitgever_per_claim: dict[str, set] = {}
    for rij in conn.execute("SELECT claim_id, publisher FROM factcheck"):
        uitgever_per_claim.setdefault(rij["claim_id"], set()).add(rij["publisher"])
    claims_per_uitgever: dict[str, list] = {}
    for claim_id, uitgevers in uitgever_per_claim.items():
        for uitgever in uitgevers:
            claims_per_uitgever.setdefault(uitgever, []).append(claim_id)

    def _hardste_buur(anchor_id):
        kandidaten = {
            ander
            for uitgever in uitgever_per_claim.get(anchor_id, ())
            for ander in claims_per_uitgever[uitgever]
            if ander != anchor_id and ander in vectoren
        }
        if not kandidaten or anchor_id not in vectoren:
            return None
        eigen = vectoren[anchor_id]
        return max(kandidaten, key=lambda ander: float(eigen @ vectoren[ander]))

    per_language: dict[str, int] = {}
    per_provenance: dict[str, int] = {}
    same_pairs = 0
    lookalike_pairs = 0

    doelen = doelen_voor(per_taal)
    for taal, taaldoel in doelen.items():
        anchors = list(per_taal[taal])
        rng.shuffle(anchors)
        gemaakt_in_taal = 0

        def _bewaar(anchor, provenance, is_same, artefact_tekst=None, doel_claim=None):
            nonlocal gemaakt_in_taal, same_pairs, lookalike_pairs
            if artefact_tekst is not None:
                fp = fingerprinter(artefact_tekst)
            else:
                vector = vectoren[anchor["claim_id"]]
                fp = TextFingerprint(vector=vector, model_version=fingerprinter.model_version)
            save_test_pair(conn, TestPair(
                claim_id=doel_claim or anchor["claim_id"],
                is_same=is_same,
                provenance=provenance,
                language=taal,
                fingerprint=fp,
            ))
            per_language[taal] = per_language.get(taal, 0) + 1
            sleutel = provenance.split(":")[0]
            per_provenance[sleutel] = per_provenance.get(sleutel, 0) + 1
            gemaakt_in_taal += 1
            if is_same:
                same_pairs += 1
            else:
                lookalike_pairs += 1

        tekort = 0
        for soort, fractie, is_same in mix_voor(taal):
            soortdoel = int(round(taaldoel * fractie))
            gemaakt_voor_soort = 0
            for volgnr, anchor in enumerate(anchors):
                if gemaakt_voor_soort >= soortdoel or gemaakt_in_taal >= taaldoel:
                    break
                tekst = anchor["canonical_text"]
                if soort == "origineel":
                    _bewaar(anchor, "origineel", True, artefact_tekst=tekst)
                elif soort == "vervorming":
                    _bewaar(anchor, "vervorming", True,
                            artefact_tekst=_dressing_variant(tekst, volgnr))
                elif soort == "inkorting":
                    variant = _truncation_variant(tekst)
                    if variant is None:
                        continue
                    _bewaar(anchor, "inkorting", True, artefact_tekst=variant)
                elif soort == "ontkenning":
                    variant = _negation_variant(tekst, taal)
                    if variant is None:
                        continue
                    _bewaar(anchor, "ontkenning", False, artefact_tekst=variant)
                elif soort == "cijferwissel":
                    variant = _digit_swap_variant(tekst)
                    if variant is None:
                        continue
                    _bewaar(anchor, "cijferwissel", False, artefact_tekst=variant)
                elif soort == "hardste-buur":
                    buur = _hardste_buur(anchor["claim_id"])
                    if buur is None:
                        continue
                    _bewaar(anchor, f"hardste-buur:{anchor['claim_id']}", False,
                            doel_claim=buur)
                gemaakt_voor_soort += 1
            tekort += max(0, soortdoel - gemaakt_voor_soort)

        # Materiaaltekort aanvullen met vervorming: altijd toepasbaar,
        # label per constructie waar.
        volgnr = 0
        while gemaakt_in_taal < taaldoel and anchors:
            anchor = anchors[volgnr % len(anchors)]
            _bewaar(anchor, "vervorming", True,
                    artefact_tekst=_dressing_variant(anchor["canonical_text"], volgnr + 1))
            volgnr += 1

    conn.commit()
    return TestsetReport(
        total=sum(per_language.values()),
        per_language=per_language,
        per_provenance=per_provenance,
        same_pairs=same_pairs,
        lookalike_pairs=lookalike_pairs,
    )


@dataclass(frozen=True)
class HerberekenRapport:
    herberekend: int
    niet_herleid: int
    # Inkortingsparen van een zin die volgens de huidige code een ontkenning
    # bevat: de inkorting kan de ontkenning hebben afgeknipt terwijl het label
    # "zelfde claim" zegt. Verwijderd, nooit stil gehouden.
    verwijderd_label_twijfel: int = 0


def herleid_artefactteksten(conn: sqlite3.Connection, fingerprinter, *, batch=None) -> dict[int, str | None]:
    """Per tekstpaar de artefacttekst die de bouwer maakte, of None (§63).

    Elke kandidaat uit de bouwregels wordt gefingerprint en tegen de bewaarde
    vector gelegd; alleen bij cosinus ≥ 0,9999 is de tekst herleid. Nooit
    gegokt: wat niet herleidbaar is, komt terug als None. Voor
    hardste-buurparen is het artefact de tekst van het anker.

    De teksten blijven in het geheugen; ze gaan nooit naar schijf (DR3).
    """
    from doublecheck.clientschema import kandidaten
    from doublecheck.vertalingen import load_translations

    if batch is None:
        batch = lambda teksten: [fingerprinter(t).vector for t in teksten]  # noqa: E731
    paren = conn.execute(
        "SELECT p.testpair_id, p.claim_id, p.provenance, p.language, p.payload, c.canonical_text"
        " FROM testpair p JOIN claim c ON c.claim_id = p.claim_id WHERE p.kind = 'text'"
        " ORDER BY p.testpair_id"
    ).fetchall()
    buur_ids = [r["provenance"].split(":", 1)[1] for r in paren if r["provenance"].startswith("hardste-buur:")]
    teksten_per_id = {}
    for i in range(0, len(buur_ids), 500):
        blok = buur_ids[i:i + 500]
        teksten_per_id.update(dict(conn.execute(
            f"SELECT claim_id, canonical_text FROM claim WHERE claim_id IN ({','.join('?' * len(blok))})",
            blok,
        ).fetchall()))
    vertalingen: dict[str, list[str]] = {}
    for p in load_translations():
        vertalingen.setdefault(p["claim_id"], []).append(p["doel"])

    alle: list[str] = []
    per_paar: list[list[int]] = []
    for r in paren:
        ks = kandidaten(r["provenance"], r["claim_id"], r["canonical_text"], r["language"],
                        teksten_per_id, vertalingen)
        per_paar.append(list(range(len(alle), len(alle) + len(ks))))
        alle.extend(ks)
    vectoren = batch(alle) if alle else []

    uit: dict[int, str | None] = {}
    for r, idx in zip(paren, per_paar):
        bewaard = np.frombuffer(r["payload"], dtype=np.float32)
        beste = max(idx, key=lambda j: float(np.dot(vectoren[j], bewaard)), default=None)
        herleid = beste is not None and float(np.dot(vectoren[beste], bewaard)) >= 0.9999
        uit[r["testpair_id"]] = alle[beste] if herleid else None
    return uit


def herbereken_afleidingen(conn: sqlite3.Connection, fingerprinter, *, batch=None) -> HerberekenRapport:
    """Werkt `numbers`/`negations` van bestaande paren bij na een wijziging
    van de extractiecode, zonder de paren te veranderen (#25.1b).

    Het artefact is herleidbaar uit de claimtekst (§63, zie
    `herleid_artefactteksten`). Een paar dat niet herleidbaar is houdt zijn
    oude versie, zodat de benchmark blijft weigeren in plaats van stil op
    verouderde afleidingen te meten. Hardste-buurparen slaan per constructie
    lege afleidingen op en houden die.
    """
    from doublecheck.relation import derivation_version, extract_negation_tokens, extract_numbers

    versie = derivation_version()
    teksten = herleid_artefactteksten(conn, fingerprinter, batch=batch)
    paren = conn.execute(
        "SELECT p.testpair_id, p.provenance, c.canonical_text"
        " FROM testpair p JOIN claim c ON c.claim_id = p.claim_id WHERE p.kind = 'text'"
        " ORDER BY p.testpair_id"
    ).fetchall()

    herberekend = niet_herleid = verwijderd = 0
    for r in paren:
        if r["provenance"] == "inkorting" and _bevat_negatie(r["canonical_text"]):
            conn.execute("DELETE FROM testpair WHERE testpair_id = ?", (r["testpair_id"],))
            verwijderd += 1
            continue
        if r["provenance"].startswith("hardste-buur:"):
            conn.execute("UPDATE testpair SET derivation_version = ? WHERE testpair_id = ?",
                         (versie, r["testpair_id"]))
            herberekend += 1
            continue
        tekst = teksten.get(r["testpair_id"])
        if tekst is None:
            niet_herleid += 1
            continue
        conn.execute(
            "UPDATE testpair SET numbers = ?, negations = ?, derivation_version = ?"
            " WHERE testpair_id = ?",
            (json.dumps(sorted(extract_numbers(tekst))), json.dumps(list(extract_negation_tokens(tekst))),
             versie, r["testpair_id"]),
        )
        herberekend += 1
    conn.commit()
    return HerberekenRapport(herberekend=herberekend, niet_herleid=niet_herleid,
                             verwijderd_label_twijfel=verwijderd)


def main() -> None:
    import argparse

    from doublecheck.ingest import ConfigFingerprinter
    from doublecheck.storage import connect, init_schema

    parser = argparse.ArgumentParser(description="Doublecheck testset bouwen")
    parser.add_argument("--db", default="doublecheck.db")
    parser.add_argument("--total", type=int, default=1500)
    parser.add_argument("--voeg-talen-toe", default="",
                        help="kommalijst van talen om additief toe te voegen (#25.1)")
    parser.add_argument("--ontbrekende-talen", action="store_true",
                        help="voeg elke taal boven de configdrempel zonder testparen toe")
    parser.add_argument("--per-taal", type=int, default=200)
    parser.add_argument("--ontkenningen-erbij", default="",
                        help="kommalijst van talen met testparen: 30 ontkenningsparen erbij (#25.20)")
    parser.add_argument("--herbereken-afleidingen", action="store_true",
                        help="werk numbers/negations bij na een wijziging van de extractiecode (#25.1b)")
    args = parser.parse_args()

    conn = connect(args.db)
    init_schema(conn)
    fingerprinter = ConfigFingerprinter()
    if args.herbereken_afleidingen:
        from doublecheck.embedding import fingerprint_texts

        rapport = herbereken_afleidingen(
            conn, fingerprinter,
            batch=lambda teksten: [f.vector for f in fingerprint_texts(teksten, fingerprinter.model_version)],
        )
        print(f"afleidingen herberekend: {rapport.herberekend} · niet herleidbaar: {rapport.niet_herleid}"
              f" · inkortingen met labeltwijfel verwijderd: {rapport.verwijderd_label_twijfel}")
        conn.close()
        return
    if args.ontkenningen_erbij:
        talen = [t.strip() for t in args.ontkenningen_erbij.split(",") if t.strip()]
        print(f"ontkenningsparen erbij: {voeg_ontkenningsparen_toe(conn, fingerprinter, talen)}")
        conn.close()
        return
    if args.voeg_talen_toe or args.ontbrekende_talen:
        from doublecheck.config import load_config

        talen = [t.strip() for t in args.voeg_talen_toe.split(",") if t.strip()]
        if args.ontbrekende_talen:
            talen += ontbrekende_talen(
                conn, min_claims=load_config().benchmark.min_claims_voor_cijfer
            )
        rapport = voeg_talen_toe(conn, fingerprinter, talen, per_taal=args.per_taal)
        print(f"toegevoegd: {rapport.total} paren in {len(rapport.per_language)} talen "
              f"({rapport.same_pairs} zelfde, {rapport.lookalike_pairs} lijkend-maar-anders)")
        print(f"  per taal: {dict(sorted(rapport.per_language.items()))}")
        print(f"  per soort: {dict(sorted(rapport.per_provenance.items()))}")
        conn.close()
        return
    rapport = build_testset(conn, fingerprinter, total=args.total)
    vertalingen = add_translation_pairs(conn, fingerprinter)
    print(f"testset: {rapport.total} paren "
          f"({rapport.same_pairs} zelfde, {rapport.lookalike_pairs} lijkend-maar-anders)")
    print(f"  cross-linguaal: {vertalingen.total} vertaalparen"
          + (f" ({len(vertalingen.skipped)} overgeslagen: claim niet in corpus)"
             if vertalingen.skipped else ""))
    print(f"  per taal: {dict(sorted(rapport.per_language.items()))}")
    print(f"  per soort: {dict(sorted(rapport.per_provenance.items()))}")
    conn.close()



@dataclass(frozen=True)
class TranslationPairReport:
    total: int
    skipped: tuple[str, ...]


def add_translation_pairs(
    conn: sqlite3.Connection, fingerprinter, paren=None
) -> TranslationPairReport:
    """Voegt cross-linguale paren toe aan de testset (E4.S1-AC5).

    Het artefact is de vertaling, het doel is de brontaalclaim: een vertaling
    ís dezelfde bewering, dus `is_same=True`. De paren krijgen één gezamenlijk
    taallabel (`crosslinguaal`), zodat ze apart gerapporteerd worden en de
    eentalige cijfers niet vervuilen.

    Bewust één label en niet acht richtingen: met vijftig paren over acht
    richtingen zijn de bakjes twee tot tien groot, en zo'n bovengrens zegt
    niets. De richtingverdeling staat in de fixture zelf (#14.7).

    Deze functie *voegt toe* en wist niets — draai hem ná `build_testset`.
    """
    from doublecheck.vertalingen import load_translations

    if paren is None:
        paren = load_translations()

    aantal = 0
    overgeslagen: list[str] = []
    for paar in paren:
        bestaat = conn.execute(
            "SELECT 1 FROM claim WHERE claim_id = ?", (paar["claim_id"],)
        ).fetchone()
        if not bestaat:
            overgeslagen.append(paar["claim_id"])
            continue
        save_test_pair(
            conn,
            TestPair(
                claim_id=paar["claim_id"],
                is_same=True,
                provenance="vertaling",
                language="crosslinguaal",
                fingerprint=fingerprinter(paar["doel"]),
            ),
        )
        aantal += 1

    conn.commit()
    return TranslationPairReport(total=aantal, skipped=tuple(overgeslagen))

if __name__ == "__main__":
    main()
