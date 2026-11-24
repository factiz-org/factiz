"""Lokale matching: een Bloom-filter van bekende claimteksten (#24.2, DR3).

De plug-in (#24.3) laadt deze filter één keer en toetst elke post op het
apparaat zelf. Een treffer zegt "het geheugen kent deze tekst"; het label
toont dan *Fact-checked before*, en de bonnetjes en de telling komen pas na een
klik van de gebruiker, via `POST /resolve`. Zonder klik verlaat niets het
apparaat. Sinds #24.2c draagt een treffer op de héle tekst ook de kant
(*Known to be false*), uit precies de checks die de resolver dan toont; een
losse zin nooit, want die kan bij een andere bewering horen.

De filter bevat uitsluitend hashes van publieke claimteksten, geen inhoud.

Sleutels per claim: de hele genormaliseerde tekst (vanaf 20 tekens) en elke
zin daarin vanaf 40 tekens, zodat een post die één zin uit een kettingbericht
citeert de filter ook raakt. Korte teksten komen er nooit in: het corpus
bevat rommelclaims als "Yes" en "google", en een post van drie letters mag
nooit een label krijgen.

Pariteit met JavaScript is het contract: `NORMALISATIE` en `posities` staan
in `claimfilter_vectoren.json`, en de plug-in moet die vectoren reproduceren.
Daarom alleen bewerkingen die beide talen identiek kennen: NFKC,
`lower`/`toLowerCase`, en de slot-sigma expliciet naar σ (Python en JS
lowercasen een slot-Σ verschillend).
"""

from __future__ import annotations

import base64
import hashlib
import math
import re
import sqlite3
import unicodedata
from dataclasses import dataclass
from typing import Iterable

VERSIE = "claimfilter-v2"
NORMALISATIE = "nfkc>lower>nfkc>final-sigma>ws-collapse>strip-quotes-and-final-punct@v1"
MIN_TEKST = 20
MIN_ZIN = 40
STANDAARD_VALS_POSITIEF = 1e-4
# De labelklassen die een sleutel op de hele tekst mag dragen (#24.2c, DESIGN
# §4c). Satire, onbewezen en "geen oordeel" krijgen geen kant: daar blijft het
# label neutraal tot de klik.
KLASSEN = ("onwaar", "misleidend", "onwaar-of-misleidend", "waar", "deels-waar", "omstreden")
# Elke sleutel in de filter draagt precies één kantsleutel, ook als hij geen
# kant heeft ("geen"): een losse zin, satire, geen oordeel, of een tekst die
# claims met een andere klasse delen. Dan geeft een toevallige botsing twee
# treffers, en het label blijft neutraal in plaats van een verkeerde kant te
# zeggen. Gemeten zonder deze regel: 50 van 80.612 zulke teksten kregen een
# kant (#24.2c).
KANTSLEUTELS = (*KLASSEN, "geen")

_RAND = " \t\r\n\"'“”‘’«»„‚‹›「」『』.!?…。！？؟।"
_ZINSEINDE = re.compile(r"(?<=[.!?…。！？؟।])\s+")


def normaliseer_voor_filter(tekst: str) -> str:
    """Wat een post onderweg verandert (kast, witruimte, aanhalingstekens,
    compatibiliteitsvormen) valt weg; letters en combinerende tekens blijven."""
    t = unicodedata.normalize("NFKC", tekst)
    t = unicodedata.normalize("NFKC", t.lower())
    t = t.replace("ς", "σ")
    t = re.sub(r"\s+", " ", t)
    return t.strip(_RAND)


def sleutels(tekst: str) -> list[str]:
    """De sleutels van één tekst: het geheel (≥ 20 tekens) en lange zinnen."""
    geheel = normaliseer_voor_filter(tekst)
    uit: list[str] = []
    if len(geheel) >= MIN_TEKST:
        uit.append(geheel)
    for zin in _ZINSEINDE.split(geheel):
        zin = zin.strip(_RAND)
        if len(zin) >= MIN_ZIN and zin not in uit:
            uit.append(zin)
    return uit


def posities(sleutel: str, m: int, k: int) -> list[int]:
    """Dubbel hashen over twee 32-bits woorden uit sha256: in JavaScript
    zonder BigInt na te rekenen (i * h2 blijft onder 2^53)."""
    digest = hashlib.sha256(sleutel.encode("utf-8")).digest()
    h1 = int.from_bytes(digest[0:4], "big")
    h2 = int.from_bytes(digest[4:8], "big") | 1
    return [(h1 + i * h2) % m for i in range(k)]


@dataclass
class Filter:
    m: int
    k: int
    n: int
    p: float
    bits: bytearray


def _parameters(n: int, p: float) -> tuple[int, int]:
    n = max(n, 1)
    m = max(8, math.ceil(-n * math.log(p) / (math.log(2) ** 2)))
    k = max(1, round(m / n * math.log(2)))
    return m, k


def kantsleutel(klasse: str, geheel: str) -> str:
    """De sleutel die zegt welke kant een hele (genormaliseerde) tekst heeft."""
    return f"kant:{klasse}|{geheel}"


def bouw_filter(teksten: Iterable[str], *, klassen: Iterable[tuple[str, str | None]] = (),
                vals_positief: float = STANDAARD_VALS_POSITIEF) -> Filter:
    """`klassen`: (claimtekst, labelklasse) voor de kant bij een treffer op de
    hele tekst (#24.2c)."""
    alle: list[str] = []
    gezien: set[str] = set()
    zinnen: set[str] = set()
    for tekst in teksten:
        geheel = normaliseer_voor_filter(tekst)
        for s in sleutels(tekst):
            if s != geheel:
                zinnen.add(s)
            if s not in gezien:
                gezien.add(s)
                alle.append(s)
    # De kant per hele tekst: alleen als alle claims met die tekst dezelfde
    # klasse uit `KLASSEN` hebben, en de tekst niet ook een losse zin van een
    # andere claim is.
    per_tekst: dict[str, set] = {}
    for tekst, klasse in klassen:
        per_tekst.setdefault(normaliseer_voor_filter(tekst), set()).add(klasse)
    for s in list(alle):
        eigen = per_tekst.get(s, set())
        klasse = next(iter(eigen)) if len(eigen) == 1 and s not in zinnen else None
        alle.append(kantsleutel(klasse if klasse in KLASSEN else "geen", s))
    m, k = _parameters(len(alle), vals_positief)
    bits = bytearray((m + 7) // 8)
    for s in alle:
        for pos in posities(s, m, k):
            bits[pos >> 3] |= 1 << (pos & 7)
    return Filter(m=m, k=k, n=len(alle), p=vals_positief, bits=bits)


def _bevat_sleutel(f: Filter, sleutel: str) -> bool:
    return all(f.bits[pos >> 3] & (1 << (pos & 7)) for pos in posities(sleutel, f.m, f.k))


def bevat(f: Filter, tekst: str) -> bool:
    """Wat de plug-in per post doet: het geheel en elke lange zin toetsen."""
    return any(_bevat_sleutel(f, s) for s in sleutels(tekst))


def kant(f: Filter, tekst: str) -> str | None:
    """De kant van een post, alleen bij een treffer op de hele tekst en alleen
    als precies één kantsleutel raakt en die een klasse is; anders `None`
    (neutraal tot de klik)."""
    geheel = normaliseer_voor_filter(tekst)
    if len(geheel) < MIN_TEKST or not _bevat_sleutel(f, geheel):
        return None
    geraakt = [klasse for klasse in KANTSLEUTELS if _bevat_sleutel(f, kantsleutel(klasse, geheel))]
    return geraakt[0] if len(geraakt) == 1 and geraakt[0] != "geen" else None


def naar_json(f: Filter, *, claims: int | None = None) -> dict:
    return {
        "versie": VERSIE,
        "normalisatie": NORMALISATIE,
        "min_tekst": MIN_TEKST,
        "min_zin": MIN_ZIN,
        # #24.2c: alleen de hele tekst, en alleen als precies één klasse raakt.
        "kanten": list(KANTSLEUTELS),
        "kantsleutel": "kant:<klasse>|<genormaliseerde hele tekst>",
        "hash": "sha256; h1=be32(d[0:4]), h2=be32(d[4:8])|1; pos_i=(h1+i*h2) mod m",
        "m": f.m,
        "k": f.k,
        "n": f.n,
        "p": f.p,
        "claims": claims,
        "bits": base64.b64encode(bytes(f.bits)).decode("ascii"),
    }


def van_json(draad: dict) -> Filter:
    if draad.get("versie") != VERSIE or draad.get("normalisatie") != NORMALISATIE:
        raise ValueError("onbekende filterversie of normalisatie; weiger liever dan stil fout te matchen (DR6)")
    return Filter(
        m=int(draad["m"]), k=int(draad["k"]), n=int(draad["n"]), p=float(draad["p"]),
        bits=bytearray(base64.b64decode(draad["bits"])),
    )


# Pariteitsinvoer voor de JavaScript-kant: zelfgeschreven, geen corpustekst.
# Elk geval raakt een andere valkuil (aanhalingstekens en witruimte, Grieks
# met slot-sigma, Cyrillisch, volle breedte en NBSP, Turks İ, Devanagari met
# klinkertekens, Frans met accenten en weglatingsteken, Chinees, ligatuur).
PARITEIT_M, PARITEIT_K = 1_000_003, 13
PARITEIT_INVOER = (
    '  "WhatsApp  will\ncharge users"  ',
    "«Vaccines have been proven to cause autism.»",
    "ΟΙ ΕΜΒΟΛΙΑΣΜΕΝΟΙ ΠΕΘΑΙΝΟΥΝ ΣΕ ΔΥΟ ΧΡΟΝΙΑΣ",
    "Россия не нападала на Украину!",
    "ＷｈａｔｓＡｐｐ\u00a0will charge users",
    "İstanbul’da seçim hilesi yapıldı",
    "क्विंट हिंदी की खबर फर्जी है।",
    "Le ministre aurait financé les manifestations d'élèves…",
    "疫苗会导致自闭症。",
    "ﬁngers ‘used’ to vote twice",
)


def pariteitsvectoren() -> dict:
    gevallen = []
    for invoer in PARITEIT_INVOER:
        n = normaliseer_voor_filter(invoer)
        gevallen.append({"invoer": invoer, "genormaliseerd": n,
                         "posities": posities(n, PARITEIT_M, PARITEIT_K)})
    # De kantsleutel (#24.2c): dezelfde hash over "kant:<klasse>|<tekst>".
    for invoer, klasse in ((PARITEIT_INVOER[0], "misleidend"), (PARITEIT_INVOER[2], "omstreden")):
        sleutel = kantsleutel(klasse, normaliseer_voor_filter(invoer))
        gevallen.append({"invoer": invoer, "klasse": klasse, "kantsleutel": sleutel,
                         "posities": posities(sleutel, PARITEIT_M, PARITEIT_K)})
    return {
        "_meta": "Pariteitsvectoren voor de JavaScript-implementatie van de claimfilter "
                 "(#24.2, #24.3). Zelfgeschreven testzinnen, geen corpustekst; "
                 "gegenereerd met `python -m doublecheck.claimfilter --vectoren`.",
        "normalisatie": NORMALISATIE,
        "m": PARITEIT_M,
        "k": PARITEIT_K,
        "gevallen": gevallen,
    }


def klassen_voor(conn: sqlite3.Connection) -> dict[str, str | None]:
    """De labelklasse per claim in de index, over precies de checks die de
    resolver toont als die claim matcht (`build_evidence`): alle clusterleden
    in de index, alleen checks van toegelaten uitgevers (B28). In één gang
    over de database in plaats van een bewijstoestand per claim."""
    from doublecheck.evidence import _host
    from doublecheck.toelating import buiten_index, register, staat_aan
    from doublecheck.verdicts import labelklasse_in_tijd

    buiten = buiten_index(conn)
    # Dezelfde regel als `toelating.toegelaten`, één keer opgehaald in plaats
    # van per check.
    aan, hosts = staat_aan(conn), register()
    groep_van = {claim_id: (cluster or claim_id) for claim_id, cluster in
                 conn.execute("SELECT claim_id, cluster_id FROM claim") if claim_id not in buiten}
    # Jongste oordeel voorop (B30 aangevuld): de klasse hangt ook aan de datum.
    oordelen: dict[str, list[tuple[str, str]]] = {}
    for claim_id, oordeel, datum, url in conn.execute(
            "SELECT claim_id, verdict_normalized, review_date, url FROM factcheck"):
        groep = groep_van.get(claim_id)
        if groep is not None and (not aan or (_host(url) or "") in hosts):
            oordelen.setdefault(groep, []).append((oordeel, datum))
    return {claim_id: labelklasse_in_tijd(oordelen.get(groep, ()))[0] for claim_id, groep in groep_van.items()}


def filter_voor(conn: sqlite3.Connection) -> dict:
    """De filter van de index, in de zoekcache: één bouw per stand van de
    database, ververst door elke schrijfactie, ook een gewijzigd oordeel
    (#24.2c: de kant hangt aan de oordelen). `:memory:` wordt nooit gecachet
    (§61c: id-hergebruik tussen verbindingen).

    Alleen claims in de index (B28): een vage tekst in de filter liet de
    plug-in elke post met "Something to think about." markeren."""
    from doublecheck.search import _gecachet
    from doublecheck.toelating import buiten_index

    def bouw() -> dict:
        buiten = buiten_index(conn)
        rijen = [(claim_id, tekst) for claim_id, tekst in conn.execute("SELECT claim_id, canonical_text FROM claim")
                 if claim_id not in buiten]
        klasse_van = klassen_voor(conn)
        return naar_json(bouw_filter([t for _, t in rijen],
                                     klassen=[(t, klasse_van.get(c)) for c, t in rijen]), claims=len(rijen))

    return _gecachet(conn, "claimfilter", bouw)


def main() -> None:
    import argparse
    import json
    import os
    import random
    import string
    import time

    from doublecheck.storage import connect

    parser = argparse.ArgumentParser(description="Claimfilter bouwen en meten (#24.2)")
    parser.add_argument("--uit", help="schrijf de filter als JSON naar dit pad")
    parser.add_argument("--vectoren", action="store_true",
                        help="schrijf alleen de pariteitsvectoren voor de JavaScript-kant")
    parser.add_argument("--steekproef", type=int, default=2000,
                        help="claims met een kant, tegen de bewijstoestand van de resolver (#24.2c)")
    parser.add_argument("--resolver", type=int, default=0,
                        help="zoveel daarvan door het hele /resolve (laadt het tekstmodel)")
    args = parser.parse_args()
    if args.vectoren:
        from pathlib import Path

        pad = Path(__file__).with_name("claimfilter_vectoren.json")
        pad.write_text(json.dumps(pariteitsvectoren(), ensure_ascii=False, indent=1) + "\n",
                       encoding="utf-8")
        print(f"geschreven: {pad}")
        return

    conn = connect(os.environ.get("DOUBLECHECK_DB", "doublecheck.db"))
    from doublecheck.toelating import buiten_index

    buiten = buiten_index(conn)
    rijen = [(c, tekst) for c, tekst in conn.execute("SELECT claim_id, canonical_text FROM claim") if c not in buiten]
    teksten = [tekst for _, tekst in rijen]
    # v1, zonder kantsleutels: alleen de tekstsleutels, zoals vóór #24.2c.
    tekstsleutels = {s for tekst in teksten for s in sleutels(tekst)}
    v1_m, v1_k = _parameters(len(tekstsleutels), STANDAARD_VALS_POSITIEF)
    begin = time.perf_counter()
    klasse_van = klassen_voor(conn)
    f = bouw_filter(teksten, klassen=[(tekst, klasse_van.get(c)) for c, tekst in rijen])
    duur = time.perf_counter() - begin
    draad = naar_json(f, claims=len(teksten))
    grootte = len(json.dumps(draad).encode("utf-8"))

    kort = sum(1 for t in teksten if not sleutels(t))
    random.seed(24)
    proef = ["".join(random.choices(string.ascii_lowercase + " ", k=random.randint(25, 120))) for _ in range(100_000)]
    vals = sum(bevat(f, t) for t in proef)
    vals_kant = sum(kant(f, t) is not None for t in proef)
    gemist = sum(1 for t in teksten if sleutels(t) and not bevat(f, t))

    print(f"claims in de index {len(teksten)} · zonder sleutel (te kort) {kort}")
    print(f"v1 zonder kant: sleutels {len(tekstsleutels)} · {v1_m / 8 / 1024:.0f} KiB · k {v1_k}")
    print(f"met kant:    sleutels {f.n} · {f.m / 8 / 1024:.0f} KiB · k {f.k} · JSON {grootte / 1024:.0f} KiB"
          f" · klassen en bouw {duur:.1f} s")
    verdeling = {}
    for c, _ in rijen:
        verdeling[klasse_van.get(c)] = verdeling.get(klasse_van.get(c), 0) + 1
    print("labelklasse per claim:", dict(sorted(verdeling.items(), key=lambda kv: -kv[1])))
    print(f"vals positief op 100.000 vreemde teksten: {vals} ({vals / len(proef):.4%}), met een kant: {vals_kant}")
    print(f"vals negatief op de eigen claims: {gemist}")

    # Op de eigen claims: geeft opzoeken precies de gebouwde klasse terug?
    uitkomst = {"gelijk": 0, "neutraal": 0, "anders": 0}
    for c, tekst in rijen:
        verwacht = klasse_van.get(c)
        if verwacht not in KLASSEN or len(normaliseer_voor_filter(tekst)) < MIN_TEKST:
            continue
        gevonden = kant(f, tekst)
        uitkomst["gelijk" if gevonden == verwacht else ("neutraal" if gevonden is None else "anders")] += 1
    print(f"eigen claims met een kant, opgezocht: {uitkomst}")

    # En de omgekeerde fout: een tekst zonder kant die toch een kant krijgt.
    per_geheel: dict[str, set] = {}
    for c, tekst in rijen:
        per_geheel.setdefault(normaliseer_voor_filter(tekst), set()).add(klasse_van.get(c))
    zonder_kant = toch = zinnen = toch_zin = 0
    for c, tekst in rijen:
        geheel = normaliseer_voor_filter(tekst)
        klassen_hier = per_geheel[geheel]
        if len(geheel) >= MIN_TEKST and not (len(klassen_hier) == 1 and next(iter(klassen_hier)) in KLASSEN):
            zonder_kant += 1
            toch += kant(f, tekst) is not None
        for zin in sleutels(tekst)[1:]:
            if zin not in per_geheel:
                zinnen += 1
                toch_zin += kant(f, zin) is not None
    print(f"teksten zonder kant: {zonder_kant}, toch een kant: {toch}; "
          f"losse zinnen als post: {zinnen}, toch een kant: {toch_zin}")

    # Tegen de resolver: de klasse uit de bewijstoestand die /resolve toont.
    from doublecheck.evidence import build_evidence
    from doublecheck.verdicts import labelklasse_in_tijd

    met_kant = sorted(c for c, tekst in rijen if klasse_van.get(c) in KLASSEN)
    steekproef = random.Random(242).sample(met_kant, min(args.steekproef, len(met_kant)))
    afwijkend = [c for c in steekproef
                 if labelklasse_in_tijd((x.verdict_normalized, x.review_date)
                                        for x in build_evidence(conn, c).factchecks)[0] != klasse_van[c]]
    print(f"tegen de bewijstoestand: {len(steekproef) - len(afwijkend)} van {len(steekproef)} gelijk"
          + (f"; afwijkend: {afwijkend[:10]}" if afwijkend else ""))

    if args.resolver:
        # Het hele pad: de letterlijke claimtekst door /resolve, zoals na de klik.
        from fastapi.testclient import TestClient

        import doublecheck.api as api

        tekst_van = dict(rijen)
        pad = random.Random(243).sample(steekproef, min(args.resolver, len(steekproef)))
        client = TestClient(api.app)
        telling = {"gelijk": 0, "neutraal": 0, "niet matched": 0, "andere kant": 0}
        voorbeelden = []
        for c in pad:
            # Onder de limiet van de resolver blijven (60 per minuut): een
            # 429 is geen antwoord over de claim.
            time.sleep(1.05)
            respons = client.post("/resolve", json={"text": tekst_van[c]})
            if respons.status_code != 200:
                raise SystemExit(f"de resolver antwoordde {respons.status_code}; de meting stopt")
            antwoord = respons.json()
            if antwoord.get("category") != "matched":
                telling["niet matched"] += 1
                voorbeelden.append((c, antwoord.get("category")))
                continue
            getoond = labelklasse_in_tijd((x["verdict_normalized"], x["review_date"])
                                          for x in antwoord["evidence"]["checks"])[0]
            lokaal = kant(f, tekst_van[c])
            if lokaal is None:
                telling["neutraal"] += 1
            elif getoond == lokaal:
                telling["gelijk"] += 1
            else:
                telling["andere kant"] += 1
                voorbeelden.append((c, getoond, kant(f, tekst_van[c])))
        print(f"het hele pad door /resolve: {telling}" + (f"; voorbeelden: {voorbeelden[:10]}" if voorbeelden else ""))

    if args.uit:
        with open(args.uit, "w", encoding="utf-8") as uit:
            json.dump(draad, uit)
        print(f"geschreven: {args.uit}")


if __name__ == "__main__":
    main()
