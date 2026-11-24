"""Kan het model deze taal representeren? (PLAN.md #16.1, DR6, B5)

Ontdekt tijdens het schaalonderzoek van etappe 16, en het bleek geen
schaalprobleem. Het embeddingmodel zet in Tamil, Telugu en Bengaals
**verschillende** claims op mediaan 0,73–0,78 gelijkenis, tegen 0,08–0,21 in de
andere corpustalen. Daardoor krijgt 71% van de artefacten in die talen een
dichtste buur boven de matchdrempel: een zelfverzekerde `matched` op een
willekeurige andere bewering (BENCHMARK.md §39).

**Waarom uitsluiten en niet alleen niet-beloven.** B14 zei dat een taal zonder
eigen benchmark in de index mag zitten "zonder precisiebelofte". Dat bleek niet
houdbaar: in de index zitten betekent kandidaat zijn, en een onbruikbare
kandidaat is schadelijker dan een afwezige. Bovendien vervuilt de blob de
kandidatenlijst van gezonde talen — 2,3% van de artefacten daar landt erin.

De maat is **modelgebonden**. Een ander embeddingmodel kan deze talen wél aan;
dan hoort deze lijst opnieuw gemeten te worden, net als elke andere afgeleide
waarde bij een modelwissel (DR6).
"""

from __future__ import annotations

import numpy as np

# Boven deze mediane gelijkenis tussen *verschillende* claims kan het model de
# taal niet uit elkaar houden. Ruim onder de laagste gemeten collapsed taal
# (0,728) en ruim boven de hoogste gezonde (0,206) — er zit een gat van een
# halve eenheid tussen, dus de grens is niet kritisch.
_MAX_ONDERSCHEID = 0.45
# Minder claims dan dit geeft geen oordeel: liever niets weten dan iets
# verzinnen op een handvol teksten.
_MIN_CLAIMS = 30

# Gemeten op 2026-08-30 met
# sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2+casefold, over
# **alle** corpustalen met minstens 30 claims — niet over een handmatig lijstje.
#
# Dat onderscheid kostte een extra ronde: de eerste meting toetste twaalf talen
# die ik had opgeschreven, en miste er zes. Ze doken pas op toen een cluster van
# 89 leden bleek te bestaan uit Malayalam, Kannada en Amhaars door elkaar
# (BENCHMARK.md §41).
#
#   ineengeklapt:  kn 0,955 · ml 0,847 · km 0,820 · as 0,802 · pa 0,791
#                  si 0,775 · te 0,775 · ta 0,740 · bn 0,728
#   bruikbaar:     en 0,077 … sw 0,382   (alles daaronder)
#
# Er zit een gat van bijna een halve eenheid tussen 0,382 en 0,728, dus de grens
# is niet kritisch. Hindi (0,212), Arabisch (0,206) en Amhaars (0,243) zijn
# prima: het ligt niet aan het schrift maar aan de talen waarop dit model is
# fijngesteld.
#
# Herzien met `python -m doublecheck.taalgeschiktheid`.
#
# **Onder bge-m3 (2026-10-11, #25.14c) klapt geen van deze talen nog ineen.**
# Gemeten op de feed (`--feed`), 150 claims per taal: te 0,332 · ta 0,346 ·
# si 0,346 · ml 0,335 · bn 0,339 · kn 0,373 · km 0,368 · as 0,388 · pa 0,333,
# binnen de band van de gezonde talen. Toegelaten door de PO (#25.18,
# 2026-10-11), met eigen testparen per taal vanaf 500 claims (B14). De lijst
# is daarmee leeg; het mechanisme blijft, voor een volgend model.
ONBRUIKBARE_TALEN: frozenset[str] = frozenset()

# Het model waaronder onderstaande lijst is gemeten. Vergelijken over
# modelversies heen is verboden (DR6): een andere embedder maakt deze meting
# waardeloos, en dan hoort de poort te weigeren in plaats van stil door te laten.
GEMETEN_MET = "BAAI/bge-m3@5617a9f61b028005a4858fdac845db406aefb181+casefold"

# Talen die het model aantoonbaar uit elkaar houdt — gemeten 2026-08-31 over het
# hele corpus, elke taal met minstens 30 claims (`python -m
# doublecheck.taalgeschiktheid`).
#
# **Dit is een witte lijst, en dat is de aanscherping van B14** *(PO 2026-08-31)*.
# Eerst gold: alles mag in de index, behalve wat gemeten en gezakt is. Nu geldt:
# alleen wat gemeten en geslaagd is. Het verschil is niet theoretisch — de
# faalvorm uit §39 valt per constructie buiten elke benchmark, dus "we merken het
# wel aan het cijfer" werkt hier niet.
#
#   ruimste marge: az 0,388 · sw 0,382 · ko 0,310 · tl 0,295
#   strakste:      en 0,070 · ro 0,075 · th 0,080 · vi 0,093
#   grens:         0,45, in een gat van een halve eenheid (§39b)
#
# Hermeten onder bge-m3 op 2026-10-11 (#25.14c), over het hele corpus: alle
# 38 talen en `und` bruikbaar, van he 0,305 en ar 0,295 tot tr 0,405 en
# sw 0,444. Dit model geeft elk paar een hogere basisgelijkenis, dus de band
# ligt hoger dan onder MiniLM. Er is onder bge-m3 geen ineengeklapte taal om
# de grens tegen te ijken; 0,45 blijft staan als de strenge kant (twijfel
# versoepelt nooit): een gezonde taal kan erop vastlopen, een ineengeklapte
# komt er niet door.
GEMETEN_BRUIKBAAR = frozenset({
    "af", "am", "ar", "az", "ca", "de",
    "en", "es", "fa", "fr", "ga", "gl",
    "gu", "he", "hi", "hr", "id", "it",
    "ja", "ko", "lo", "mn", "mr", "ms",
    "ne", "nl", "pl", "pt", "ro", "ru",
    "sw", "th", "tl", "tr", "und", "ur",
    "vi", "zh",
    # #25.18 (PO 2026-10-11): onder MiniLM ineengeklapt, onder bge-m3 gemeten
    # op de feed en bruikbaar (zie ONBRUIKBARE_TALEN hierboven).
    "as", "bn", "km", "kn", "ml", "pa", "si", "ta", "te",
})


class OngemetenModelError(RuntimeError):
    """De taallijst is onder een ander model gemeten dan er nu draait (DR6)."""


def is_bruikbaar(onderscheid: float | None) -> bool:
    """`None` (te weinig materiaal) telt als bruikbaar: geen oordeel, geen straf.

    Let op het verschil met `mag_in_de_index`: deze functie beoordeelt één
    méting, en een ontbrekende meting is geen bewijs van slechtheid. De poort
    hieronder beoordeelt een táál, en daar telt een ontbrekende meting wél
    tegen — bewijs van geschiktheid moet er zijn, niet ontbreken.
    """
    return onderscheid is None or onderscheid <= _MAX_ONDERSCHEID


def mag_in_de_index(taal: str, model_version: str) -> bool:
    """Mag deze taal het corpus in? *(B14, aangescherpt 2026-08-31)*

    Ongemeten is niet hetzelfde als goed. Een taal die nooit gemeten is kan het
    model even goed ineen laten klappen als Tamil deed, en dat merk je nergens
    aan: 71% valse matches, volledig buiten elke benchmark (§39).

    Een nieuwe taal komt binnen via `meet_teksten` op het feedmateriaal, vóór
    de import — zie die functie.
    """
    return taalgrond(taal, model_version) is None


def taalgrond(taal: str, model_version: str) -> str | None:
    """Waaróm een taal er niet in mag; `None` als ze er wél in mag.

    Twee weigeringen, twee berichten. `onbruikbare_taal` betekent: gemeten en
    gezakt — het model klapt deze taal ineen (§39). `ongemeten_taal` betekent:
    nooit gemeten, en dat is geen bewijs van geschiktheid. Voor de beheerder is
    dat verschil het verschil tussen "opgeven" en "meten".
    """
    if model_version != GEMETEN_MET:
        raise OngemetenModelError(
            f"taallijst is gemeten met {GEMETEN_MET!r}, niet met "
            f"{model_version!r}; hermeet met `python -m "
            f"doublecheck.taalgeschiktheid` voordat je importeert (DR6)"
        )
    if taal in GEMETEN_BRUIKBAAR:
        return None
    return "onbruikbare_taal" if taal in ONBRUIKBARE_TALEN else "ongemeten_taal"


def meet_teksten(teksten, model_version: str, embedder=None) -> float | None:
    """Onderscheid meten op ruwe teksten, vóór ze het corpus in gaan.

    Zonder deze uitweg is de witte lijst een muur: een taal mag er niet in
    voordat ze gemeten is, en ze is niet te meten uit een corpus waar ze niet in
    zit. Hiermee meet je op het feedmateriaal zelf.
    """
    if embedder is None:
        from doublecheck.embedding import fingerprint_texts

        def embedder(teksten, model_version):
            return [fp.vector for fp in fingerprint_texts(list(teksten), model_version)]

    teksten = list(teksten)
    if len(teksten) < _MIN_CLAIMS:
        return None
    return meet_onderscheid(embedder(teksten, model_version))


def meet_onderscheid(vectoren) -> float | None:
    """Mediane gelijkenis tussen *verschillende* claims; hoog = ineengeklapt."""
    matrix = np.asarray(vectoren, dtype=np.float32)
    if len(matrix) < _MIN_CLAIMS:
        return None
    gelijkenis = matrix @ matrix.T
    boven = gelijkenis[np.triu_indices(len(matrix), k=1)]
    return float(np.median(boven))


def vectoren_per_taal(conn, model_version: str) -> dict[str, np.ndarray]:
    """De corpusvectoren per taal, uitsluitend van `model_version` (DR6).

    Na een modelwissel staan oude en nieuwe vingerafdrukken naast elkaar; een
    meting over beide door elkaar zou niets betekenen (#25.14c).
    """
    per_taal: dict[str, list[np.ndarray]] = {}
    for taal, payload in conn.execute(
        "SELECT c.language, f.payload FROM claim c JOIN fingerprint f ON f.claim_id = c.claim_id"
        " WHERE f.kind = 'text' AND f.model_version = ?", (model_version,)
    ):
        per_taal.setdefault(taal, []).append(np.frombuffer(payload, dtype=np.float32))
    return {taal: np.vstack(v) for taal, v in per_taal.items()}


def main() -> None:
    """Meet het onderscheid voor élke corpustaal (#16.3).

    Bestaat omdat de lijst hierboven één keer met de hand is samengesteld en er
    toen zes talen misten. Een lijst die je kunt hermeten, blijft kloppen; een
    lijst die je moet onthouden, niet.
    """
    import argparse
    import random
    import sqlite3

    parser = argparse.ArgumentParser(
        description="Doublecheck: kan het model deze talen representeren?"
    )
    parser.add_argument("--db", default="doublecheck.db")
    parser.add_argument("--steekproef", type=int, default=150)
    parser.add_argument(
        "--feed",
        help="meet de talen ín een feedbestand, vóór de import — de manier om"
             " een nieuwe taal toe te laten zonder haar eerst te importeren",
    )
    args = parser.parse_args()

    if args.feed:
        _meet_feed(args.feed, args.steekproef)
        return

    from doublecheck.config import load_config

    conn = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    per_taal = vectoren_per_taal(conn, load_config().model_versions.text_embedding)

    rng = random.Random(7)
    print(f"{'taal':<7}{'claims':>8}{'onderscheid':>13}   oordeel")
    slecht = []
    for taal in sorted(per_taal):
        matrix = per_taal[taal]
        steek = rng.sample(range(len(matrix)), min(args.steekproef, len(matrix)))
        score = meet_onderscheid(matrix[steek])
        if score is None:
            print(f"{taal:<7}{len(matrix):>8}{'—':>13}   te weinig materiaal")
            continue
        bruikbaar = is_bruikbaar(score)
        if not bruikbaar:
            slecht.append(taal)
        print(f"{taal:<7}{len(matrix):>8}{score:>13.3f}"
              f"   {'ok' if bruikbaar else 'ONBRUIKBAAR'}")
    print()
    print(f"onbruikbaar volgens deze meting: {sorted(slecht)}")
    print(f"vastgelegd in de code          : {sorted(ONBRUIKBARE_TALEN)}")
    if set(slecht) - ONBRUIKBARE_TALEN:
        print(f"NIEUW en nog niet vastgelegd   : {sorted(set(slecht) - ONBRUIKBARE_TALEN)}")
    conn.close()


def _meet_feed(pad: str, steekproef: int) -> None:
    """Meet elke taal in een feedbestand, vóórdat er iets geïmporteerd is.

    De witte lijst uit `GEMETEN_BRUIKBAAR` is anders een muur: een taal mag het
    corpus niet in voordat ze gemeten is, en uit een corpus waar ze niet in zit
    valt niets te meten. Hiermee meet je op het ruwe materiaal.
    """
    import collections
    import json
    import random
    from pathlib import Path

    from doublecheck.config import load_config
    from doublecheck.feed import parse_feed

    feed = json.loads(Path(pad).read_text(encoding="utf-8"))
    claims = parse_feed(feed)
    per_taal: dict[str, list[str]] = collections.defaultdict(list)
    for claim in claims:
        taal = next((c.language for c in claim.factchecks if c.language), None)
        if taal:
            per_taal[taal].append(claim.text)

    model = load_config().model_versions.text_embedding
    rng = random.Random(7)
    print(f"{len(claims)} claims in {len(per_taal)} talen · model {model}")
    if model != GEMETEN_MET:
        print(f"LET OP: de vastgelegde lijst is gemeten met {GEMETEN_MET!r}")
    print()
    print(f"{'taal':<7}{'claims':>8}{'onderscheid':>13}   stand")
    nieuw_bruikbaar = []
    for taal in sorted(per_taal, key=lambda t: -len(per_taal[t])):
        teksten = per_taal[taal]
        if len(teksten) > steekproef:
            teksten = rng.sample(teksten, steekproef)
        score = meet_teksten(teksten, model)
        if score is None:
            print(f"{taal:<7}{len(per_taal[taal]):>8}{'—':>13}   te weinig materiaal")
            continue
        al_bekend = taal in GEMETEN_BRUIKBAAR
        goed = is_bruikbaar(score)
        stand = "al toegelaten" if al_bekend else ("KAN ERBIJ" if goed else "ONBRUIKBAAR")
        if goed and not al_bekend:
            nieuw_bruikbaar.append(taal)
        print(f"{taal:<7}{len(per_taal[taal]):>8}{score:>13.3f}   {stand}")
    print()
    if nieuw_bruikbaar:
        print(f"kan aan GEMETEN_BRUIKBAAR worden toegevoegd: {sorted(nieuw_bruikbaar)}")
        print("Zet ze er met de hand bij, mét de meting erboven — de lijst hoort")
        print("navolgbaar te zijn, niet automatisch te groeien.")
    else:
        print("geen nieuwe talen die de grens halen")


if __name__ == "__main__":
    main()
