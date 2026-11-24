"""Modelvergelijking op natuurlijke parafrasen (PLAN.md #25.14).

De toets van #25.13 liet zien waar laag 1 knelt: twee redacties die dezelfde
virale post checkten, schrijven de claim zo verschillend op dat het huidige
model ze mediaan 0,67 gelijk vindt (BENCHMARK §71). Deze module meet of een
sterker meertalig model dat beter doet, vóór er iets aan de index verandert.

Twee spelregels maken de vergelijking eerlijk:

- **Dezelfde pool voor elk model.** Alle claims uit de parafrasegroepen plus
  een vaste, willekeurige steekproef van het corpus als afleiders. Geen
  afleiders die het huidige model heeft uitgekozen: dan zou de pool juist de
  fouten van dat model bevatten en niet die van de kandidaten.
- **Geen gedeelde drempel.** Elk model heeft zijn eigen gelijkenisschaal. De
  vraag is daarom per model: hoeveel vind je terug bij hetzelfde foutniveau?
  Dat cijfer verandert niet als een model zijn hele schaal opschuift.

Dit is de voorronde. Wie hier wint, gaat door naar het volledige corpus en de
benchmark; pas bij duidelijke winst volgt een herindex, en die is een release
(B22).
"""

from __future__ import annotations

import os
import random
import re
import threading
import time
from dataclasses import dataclass

import numpy as np

from doublecheck.embedding import normaliseer_voor_embedding


@dataclass(frozen=True)
class Kandidaat:
    slug: str
    naam: str
    # Volledige commit-hash: een model op Hugging Face kan onder dezelfde naam
    # veranderen, en dan meet een herhaling iets anders (DR6).
    revisie: str
    # multilingual-e5 verwacht "query: " vóór beide kanten van een symmetrische
    # taak (modelkaart: paraphrase retrieval).
    voorvoegsel: str = ""
    # Modellen met benoemde prompts in hun eigen configuratie (voyage).
    prompt: str | None = None
    # Het model draagt eigen modelcode in zijn repository. Alleen op een
    # vastgezette, gelezen revisie (zie `controleer`).
    eigen_code: bool = False


KANDIDATEN: dict[str, Kandidaat] = {
    k.slug: k
    for k in (
        Kandidaat("minilm", "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
                  "e8f8c211226b894fcb81acc59f3b34ba3efd5f42"),
        Kandidaat("e5", "intfloat/multilingual-e5-base",
                  "d128750597153bb5987e10b1c3493a34e5a4502a", voorvoegsel="query: "),
        Kandidaat("labse", "sentence-transformers/LaBSE",
                  "836121a0533e5664b21c7aacc5d22951f2b8b25b"),
        Kandidaat("bgem3", "BAAI/bge-m3",
                  "5617a9f61b028005a4858fdac845db406aefb181"),
        # Symmetrisch: dezelfde "document"-prompt aan beide kanten. De code in
        # de repository (84 regels, gelezen op 2026-10-10) maakt de aandacht
        # bidirectioneel en zet er een projectie achter; geen netwerk of I/O.
        Kandidaat("voyage", "voyageai/voyage-4-nano",
                  "67fabc9bef010dabc5f6024aa1b1b6b93410426f", prompt="document", eigen_code=True),
    )
}


def controleer(kandidaat: Kandidaat) -> None:
    """Externe modelcode draait alleen op een vastgezette revisie.

    Op een tak als `main` kan de code na het lezen veranderen; op een
    commit-hash niet.
    """
    if kandidaat.eigen_code and not re.fullmatch(r"[0-9a-f]{40}", kandidaat.revisie):
        raise ValueError(
            f"{kandidaat.naam} draagt eigen modelcode; die draait alleen op een"
            f" volledige commit-hash, niet op {kandidaat.revisie!r}"
        )


def kies_pool(groepen: list[set[str]], alle_ids, n: int, seed: int) -> list[str]:
    """Alle groepsclaims plus `n` vaste afleiders, onafhankelijk van de volgorde."""
    in_groep = set().union(*groepen) if groepen else set()
    rest = sorted(set(alle_ids) - in_groep)
    afleiders = random.Random(seed).sample(rest, min(n, len(rest)))
    return sorted(in_groep) + sorted(afleiders)


@dataclass(frozen=True)
class Zoekvraag:
    claim_id: str
    soort: str
    beste_partner: float
    beste_afleider: float

    @property
    def gevonden_bovenaan(self) -> bool:
        # Strikt: bij gelijkstand weet het model het niet (twijfel versoepelt nooit).
        return self.beste_partner > self.beste_afleider

    @property
    def bovenaan(self) -> float:
        return max(self.beste_partner, self.beste_afleider)


def _soort(a: str, groep: set[str], taal: dict[str, str]) -> str:
    bekend = lambda t: t not in ("", "und", None)  # noqa: E731
    if not bekend(taal.get(a)):
        return "taal onbekend"
    partnertalen = [taal.get(b) for b in groep if b != a]
    if any(t == taal[a] for t in partnertalen):
        return "zelfde taal"
    if any(bekend(t) for t in partnertalen):
        return "cross-linguaal"
    return "taal onbekend"


def herkenning(matrix: np.ndarray, ids: list[str], groepen: list[set[str]],
               taal: dict[str, str]) -> list[Zoekvraag]:
    """Per groepsclaim: beste partner van dezelfde post tegen beste afleider."""
    index = {cid: i for i, cid in enumerate(ids)}
    vragen = []
    for groep in groepen:
        leden = [c for c in groep if c in index]
        for a in leden:
            sims = matrix @ matrix[index[a]]
            sims[index[a]] = -np.inf
            partners = [index[b] for b in leden if b != a]
            masker = np.ones(len(ids), dtype=bool)
            masker[partners] = False
            masker[index[a]] = False
            vragen.append(Zoekvraag(
                claim_id=a,
                soort=_soort(a, set(leden), taal),
                beste_partner=float(sims[partners].max()) if partners else float("-inf"),
                beste_afleider=float(sims[masker].max()) if masker.any() else float("-inf"),
            ))
    return vragen


def gevonden_bij_foutniveau(vragen: list[Zoekvraag], niveau: float) -> tuple[float, float, float]:
    """Laagste drempel waarbij hoogstens `niveau` van de zoekvragen een afleider
    als match krijgt; geeft (drempel, aandeel gevonden, aandeel fout).

    Zoals het productiepad: alleen de bovenste kandidaat telt, en die telt
    alleen boven de drempel.
    """
    n = len(vragen)
    if n == 0:
        return float("inf"), 0.0, 0.0
    boven = np.array([v.bovenaan for v in vragen])
    goed = np.array([v.gevonden_bovenaan for v in vragen])
    keuze = (float("inf"), 0.0, 0.0)
    for drempel in sorted(set(boven.tolist()), reverse=True):
        raak = boven >= drempel
        fout = float((raak & ~goed).sum()) / n
        if fout > niveau:
            break
        keuze = (drempel, float((raak & goed).sum()) / n, fout)
    return keuze


def embed(kandidaat: Kandidaat, teksten: list[str], *, model=None, portie: int = 512,
          pauze: float = 1.0) -> np.ndarray:
    """Vectoren in porties, met de casefold van productie plus de eigen
    voorbewerking van het model. Een pauze tussen porties houdt de machine koel."""
    if model is None:
        model = laad(kandidaat)
    blokken = []
    for start in range(0, len(teksten), portie):
        invoer = [kandidaat.voorvoegsel + normaliseer_voor_embedding(t)
                  for t in teksten[start:start + portie]]
        blokken.append(np.asarray(model.encode(
            invoer, prompt_name=kandidaat.prompt, normalize_embeddings=True,
            show_progress_bar=False, batch_size=32,
        ), dtype=np.float32))
        if pauze and start + portie < len(teksten):
            time.sleep(pauze)
    return np.vstack(blokken) if blokken else np.empty((0, 0), dtype=np.float32)


def _maak_voyage_bruikbaar(kandidaat: Kandidaat) -> None:
    """Twee aanpassingen voor transformers 5, zonder het bestand te wijzigen.

    De code van voyage-4-nano is geschreven voor transformers 4.51: de klasse
    mist `config_class`, en `create_causal_mask` heet daar `input_embeds` en
    kent nog `cache_position`. Wint dit model, dan worden deze 84 regels
    eigen, geteste code en vervalt het laden van externe code.
    """
    import sys

    from transformers import Qwen3Config
    from transformers.dynamic_module_utils import get_class_from_dynamic_module

    klasse = get_class_from_dynamic_module(
        "modeling_qwen3_bidirectional.Qwen3BidirectionalModel", kandidaat.naam,
        revision=kandidaat.revisie,
    )
    klasse.config_class = Qwen3Config
    module = sys.modules[klasse.__module__]
    if getattr(module.create_causal_mask, "_doublecheck", False):
        return
    origineel = module.create_causal_mask

    def compat(**kw):
        if "input_embeds" in kw:
            kw["inputs_embeds"] = kw.pop("input_embeds")
        kw.pop("cache_position", None)
        return origineel(**kw)

    compat._doublecheck = True
    module.create_causal_mask = compat


def laad(kandidaat: Kandidaat):
    import torch
    from sentence_transformers import SentenceTransformer

    controleer(kandidaat)
    if kandidaat.eigen_code:
        _maak_voyage_bruikbaar(kandidaat)
    # float32: voyage staat in bfloat16, en dat rekent op deze processor
    # dertien keer trager en normaliseert onnauwkeurig (gemeten: 1,0046).
    model = SentenceTransformer(
        kandidaat.naam, revision=kandidaat.revisie, device="cpu",
        trust_remote_code=kandidaat.eigen_code, model_kwargs={"dtype": torch.float32},
    )
    # Claims zijn kort; een lange transcriptie mag een groot model niet
    # minutenlang bezighouden. MiniLM houdt zijn eigen 128.
    model.max_seq_length = min(model.max_seq_length or 512, 512)
    return model


def herbouw_testset(conn, teksten: dict[int, str | None], versie: str, vectoren_voor) -> int:
    """Geeft elk herleid testpaar de vector van de kandidaat; dezelfde paren,
    dezelfde labels en afleidingen. Onherleidbare paren gaan eruit en worden
    geteld, nooit geraden. Alleen in een kopie van de database gebruiken."""
    ids = [tid for tid, t in teksten.items() if t is not None]
    weg = [tid for tid, t in teksten.items() if t is None]
    vectoren = vectoren_voor([teksten[tid] for tid in ids]) if ids else []
    for tid, v in zip(ids, vectoren):
        conn.execute("UPDATE testpair SET payload = ?, model_version = ? WHERE testpair_id = ?",
                     (np.ascontiguousarray(v, dtype=np.float32).tobytes(), versie, tid))
    for tid in weg:
        conn.execute("DELETE FROM testpair WHERE testpair_id = ?", (tid,))
    conn.commit()
    return len(weg)


def neem_vectoren_over(doel, bron, bronversie: str, doelversie: str) -> int:
    """Zet de vectoren uit een meetkopie in de index onder de productieversie.

    Alleen na bewijs dat het productiepad dezelfde vectoren geeft (#25.14c).
    Additief, zoals herindexeren: alleen claims die in de doeldatabase staan
    en de doelversie nog missen; een tweede keer voegt niets toe.
    """
    al = {r[0] for r in doel.execute(
        "SELECT claim_id FROM fingerprint WHERE kind = 'text' AND model_version = ?", (doelversie,))}
    claims = {r[0] for r in doel.execute("SELECT claim_id FROM claim")}
    n = 0
    for cid, payload in bron.execute(
            "SELECT claim_id, payload FROM fingerprint WHERE kind = 'text' AND model_version = ?", (bronversie,)):
        if cid in claims and cid not in al:
            doel.execute("INSERT INTO fingerprint (claim_id, kind, model_version, payload)"
                         " VALUES (?, 'text', ?, ?)", (cid, doelversie, payload))
            n += 1
    doel.commit()
    return n


_TESTPAAR = ("SELECT testpair_id, claim_id, is_same, provenance, language, numbers, negations,"
             " derivation_version FROM testpair WHERE kind = 'text' ORDER BY testpair_id")


def neem_testparen_over(doel, bron, doelversie: str) -> int:
    """Geeft de testparen de vectoren uit de meetkopie, maar alleen als het
    rij voor rij dezelfde paren zijn: zelfde claim, label, soort, taal en
    afleidingen. Anders gaat er niets over."""
    if [tuple(r) for r in doel.execute(_TESTPAAR)] != [tuple(r) for r in bron.execute(_TESTPAAR)]:
        raise ValueError("de testparen in bron en doel verschillen; niets overgezet")
    n = 0
    for tid, payload in bron.execute("SELECT testpair_id, payload FROM testpair WHERE kind = 'text'").fetchall():
        doel.execute("UPDATE testpair SET payload = ?, model_version = ? WHERE testpair_id = ?",
                     (payload, doelversie, tid))
        n += 1
    doel.commit()
    return n


@dataclass(frozen=True)
class Bovenste:
    """De bovenste kandidaat van één testpaar, eenmaal gezocht."""
    gelijkenis: float | None
    is_zelfde: bool
    # Mag de bovenste kandidaat matchen zonder fout? (zelfde regel als _is_fout)
    doel_goed: bool
    tegenspraak: bool
    crosslinguaal: bool


def bovenste_per_paar(conn, versie: str) -> list[Bovenste]:
    """Zoekt elk testpaar één keer, met precies de stappen van de benchmark."""
    from doublecheck.benchmark import _is_fout
    from doublecheck.categorize import Category
    from doublecheck.relation import contradicts
    from doublecheck.search import search_text
    from doublecheck.taal import zijn_verschillende_talen
    from doublecheck.testset import load_test_pairs

    uit = []
    for pair in load_test_pairs(conn):
        if pair.kind != "text":
            continue
        kandidaten = search_text(conn, pair.fingerprint)
        if not kandidaten:
            uit.append(Bovenste(None, pair.is_same, False, False, False))
            continue
        beste = kandidaten[0]
        kandidaat = conn.execute("SELECT canonical_text, language FROM claim WHERE claim_id = ?",
                                 (beste.claim_id,)).fetchone()
        uit.append(Bovenste(
            gelijkenis=beste.similarity,
            is_zelfde=pair.is_same,
            doel_goed=not _is_fout(pair, Category.MATCHED, beste.claim_id),
            tegenspraak=contradicts(
                pair.fingerprint.numbers, pair.fingerprint.negations, kandidaat["canonical_text"],
                artefact_negation_tokens=getattr(pair.fingerprint, "negation_tokens", None),
            ),
            crosslinguaal=zijn_verschillende_talen(getattr(pair.fingerprint, "language", None),
                                                   kandidaat["language"]),
        ))
    return uit


def tel(bovenste: list[Bovenste], t) -> tuple[int, int, int]:
    """(foute koppelingen, juiste matches, zelfde-paren), zoals de benchmark telt."""
    from doublecheck.categorize import Category, categorize

    fouten = goed = 0
    for b in bovenste:
        cat = categorize(b.gelijkenis, t, contradiction=b.tegenspraak, crosslinguaal=b.crosslinguaal)
        raak = cat.category is Category.MATCHED
        fouten += raak and not b.doel_goed
        goed += raak and b.is_zelfde and b.doel_goed
    return fouten, goed, sum(b.is_zelfde for b in bovenste)


def kalibreer(bovenste: list[Bovenste], *, budget: int, rooster) -> tuple:
    """De drempels met de meeste juiste matches bij hoogstens `budget` fouten.

    Gelijkspel gaat naar de strengere drempels (twijfel versoepelt nooit), en
    de cross-linguale drempel ligt nooit boven de gewone.
    """
    from doublecheck.config import Thresholds

    beste = None
    for match in sorted(rooster):
        for cross in sorted(rooster):
            if cross > match:
                continue
            t = Thresholds(text_match=match, text_related=0.0, image_same=31,
                           text_match_crosslingual=cross)
            fouten, goed, _ = tel(bovenste, t)
            if fouten > budget:
                continue
            sleutel = (goed, match, cross)
            if beste is None or sleutel >= beste[0]:
                beste = (sleutel, t, fouten, goed)
    if beste is None:
        raise ValueError("geen drempel in het rooster blijft binnen het foutbudget")
    return beste[1], beste[2], beste[3]


@dataclass(frozen=True)
class TaalRij:
    taal: str
    dekking_basis: float
    dekking_kandidaat: float
    fouten_basis: int
    fouten_kandidaat: int
    achteruit: bool

    @property
    def verschil(self) -> float:
        return self.dekking_kandidaat - self.dekking_basis


def per_taal(basis: dict, kandidaat: dict, *, marge: float) -> list:
    """Per taal dekking en fouten naast elkaar (B14). Achteruit is: meer dan
    `marge` minder dekking, of meer foute koppelingen in die taal."""
    if set(basis) != set(kandidaat):
        raise ValueError(f"talen verschillen: {sorted(set(basis) ^ set(kandidaat))}")
    rijen = []
    for taal in sorted(basis):
        b, k = basis[taal], kandidaat[taal]
        achteruit = k.dekking - b.dekking < -marge or k.wrong_links > b.wrong_links
        rijen.append(TaalRij(taal, b.dekking, k.dekking, b.wrong_links, k.wrong_links, achteruit))
    return rijen


class CpuMeter:
    """Meet het CPU-gebruik van dit proces, elke 2 s, als aandeel van de machine."""

    def __init__(self, interval: float = 2.0):
        self.interval = interval
        self.metingen: list[float] = []
        self._stop = threading.Event()

    def __enter__(self):
        def loop():
            vorig_t, vorig_c = time.time(), sum(os.times()[:2])
            while not self._stop.wait(self.interval):
                t, c = time.time(), sum(os.times()[:2])
                self.metingen.append(100 * (c - vorig_c) / (t - vorig_t))
                vorig_t, vorig_c = t, c

        self._draad = threading.Thread(target=loop, daemon=True)
        self._draad.start()
        return self

    def __exit__(self, *_):
        self._stop.set()
        self._draad.join()

    def samenvatting(self) -> str:
        if not self.metingen:
            return "CPU: te kort om te meten"
        kernen = os.cpu_count() or 1
        piek, gem = max(self.metingen), float(np.mean(self.metingen))
        return (f"CPU: piek {piek:.0f}% ({piek / kernen:.0f}% van de machine)"
                f" · gemiddeld {gem:.0f}% ({gem / kernen:.0f}% van de machine)")


def voorronde(args) -> None:
    import statistics
    from pathlib import Path

    from doublecheck.config import load_config
    from doublecheck.natuurlijk import groepen_uit_feed
    from doublecheck.storage import connect

    conn = connect(os.environ.get("DOUBLECHECK_DB", "doublecheck.db"))
    groepen = groepen_uit_feed(conn, args.feed)
    rijen = conn.execute("SELECT claim_id, canonical_text, language FROM claim").fetchall()
    tekst = {r[0]: r[1] for r in rijen}
    taal = {r[0]: r[2] for r in rijen}
    pool = kies_pool(groepen, tekst, args.pool, args.seed)
    print(f"groepen {len(groepen)} · groepsclaims {len(set().union(*groepen))} · pool {len(pool)}"
          f" (seed {args.seed})", flush=True)

    map_ = Path(args.map)
    map_.mkdir(parents=True, exist_ok=True)
    uitslagen = {}
    for slug in args.modellen.split(","):
        k = KANDIDATEN[slug]
        bestand = map_ / f"{slug}-{k.revisie[:10]}-pool{args.pool}-seed{args.seed}.npz"
        start = time.time()
        meter = CpuMeter()
        if bestand.exists() and list(np.load(bestand)["ids"]) == pool:
            matrix = np.load(bestand)["vectoren"]
            herkomst = "uit cache"
        else:
            with meter:
                matrix = embed(k, [tekst[c] for c in pool], portie=args.portie, pauze=args.pauze)
            np.savez(bestand, ids=np.array(pool), vectoren=matrix)
            herkomst = f"{time.time() - start:.0f}s · {meter.samenvatting()}"
        if slug == "minilm":
            # Dezelfde voorbewerking als productie? Dan liggen deze vectoren op
            # de opgeslagen index.
            versie = load_config().model_versions.text_embedding
            opgeslagen = dict(conn.execute(
                "SELECT claim_id, payload FROM fingerprint WHERE kind = 'text' AND model_version = ?",
                (versie,)))
            steek = [i for i, c in enumerate(pool) if c in opgeslagen][:500]
            cos = [float(matrix[i] @ np.frombuffer(opgeslagen[pool[i]], dtype=np.float32)) for i in steek]
            herkomst += f" · tegen de productie-index: min cos {min(cos):.5f}"
        vragen = herkenning(matrix, pool, groepen, taal)
        uitslagen[slug] = vragen
        print(f"{slug:7} dim {matrix.shape[1]:>4} · {herkomst}", flush=True)

    print()
    soorten = ("alle", "zelfde taal", "cross-linguaal")
    kop = "model    " + "".join(f"{s + ' bovenaan':>24}" for s in soorten)
    print(kop + f"{'gev. @2% fout':>15}{'gev. @5% fout':>15}{'cross @5%':>11}{'mediaan partner':>17}")
    for slug, vragen in uitslagen.items():
        def deel(soort):
            sel = [v for v in vragen if soort == "alle" or v.soort == soort]
            return sel
        cellen = []
        for soort in soorten:
            sel = deel(soort)
            cellen.append(f"{sum(v.gevonden_bovenaan for v in sel) / len(sel):>17.1%} (n={len(sel):>3})")
        _, g2, _ = gevonden_bij_foutniveau(vragen, 0.02)
        _, g5, _ = gevonden_bij_foutniveau(vragen, 0.05)
        _, c5, _ = gevonden_bij_foutniveau(deel("cross-linguaal"), 0.05)
        med = statistics.median(v.beste_partner for v in vragen)
        print(f"{slug:8} " + "".join(f"{c:>24}" for c in cellen) + f"{g2:>15.1%}{g5:>15.1%}{c5:>11.1%}{med:>17.3f}")


def meetversie(kandidaat: Kandidaat) -> str:
    """Het label van de kandidaat in de kopie: model, revisie en voorbewerking.

    Geen productieversie; die volgt pas bij een herindex (B22, DR6)."""
    stappen = ([f"prompt-{kandidaat.prompt}"] if kandidaat.prompt else []) + \
              (["query-voorvoegsel"] if kandidaat.voorvoegsel else []) + ["casefold"]
    return f"{kandidaat.naam}@{kandidaat.revisie[:10]}+" + "+".join(stappen)


def volledig(args) -> None:
    """Ronde twee: het hele corpus, de benchmark op dezelfde testparen, en de
    parafrasetoets met de eigen drempels van het model. Altijd in een kopie."""
    import json
    import sqlite3
    import statistics
    from pathlib import Path

    from doublecheck.benchmark import run_benchmark
    from doublecheck.config import load_config
    from doublecheck.embedding import TextFingerprint, fingerprint_texts
    from doublecheck.natuurlijk import groepen_uit_feed, meet_natuurlijk
    from doublecheck.reindex import reindex_text
    from doublecheck.storage import connect
    from doublecheck.testset import herleid_artefactteksten

    k = KANDIDATEN[args.volledig]
    config = load_config()
    productie = config.model_versions.text_embedding
    bron = os.environ.get("DOUBLECHECK_DB", "doublecheck.db")
    map_ = Path(args.map)
    map_.mkdir(parents=True, exist_ok=True)

    # Het foutbudget is het huidige cijfer: een kandidaat mag niet meer fout doen.
    prod = sqlite3.connect(f"file:{bron}?mode=ro", uri=True, check_same_thread=False)
    prod.row_factory = sqlite3.Row
    basis = bovenste_per_paar(prod, productie)
    budget, basis_goed, zelfde = tel(basis, config.thresholds)
    print(f"huidig model op de productiedrempels: {budget} fouten, {basis_goed}/{zelfde} gevonden", flush=True)

    meter = CpuMeter()
    if k.slug == "minilm":
        conn, versie, model = prod, productie, None
    else:
        doel = map_ / f"{k.slug}.db"
        if not doel.exists():
            kopie = sqlite3.connect(doel)
            prod.backup(kopie)
            kopie.close()
        conn = connect(doel)
        versie = meetversie(k)
        model = laad(k)
        start = time.time()

        def fingerprinter(teksten, v):
            vectoren = embed(k, teksten, model=model, portie=len(teksten), pauze=0)
            time.sleep(args.pauze)
            return [TextFingerprint(vector=x, model_version=v) for x in vectoren]

        def voortgang(gedaan, totaal):
            if gedaan % (args.portie * 20) < args.portie or gedaan == totaal:
                print(f"  corpus {gedaan}/{totaal} · {time.time() - start:.0f}s", flush=True)

        with meter:
            reindex_text(conn, versie, fingerprinter=fingerprinter, batch=args.portie, voortgang=voortgang)
            versies = {r[0] for r in conn.execute("SELECT DISTINCT model_version FROM testpair WHERE kind = 'text'")}
            if versies != {versie}:
                teksten = herleid_artefactteksten(
                    conn, None, batch=lambda ts: [f.vector for f in fingerprint_texts(ts, productie)])
                weg = herbouw_testset(conn, teksten, versie,
                                      lambda ts: embed(k, ts, model=model, portie=256, pauze=0))
                print(f"  testset herbouwd: {len(teksten) - weg} paren, {weg} niet herleid", flush=True)
        print(f"  {meter.samenvatting()}", flush=True)

    rooster = [round(x / 100, 2) for x in range(50, 100)]
    bovenste = bovenste_per_paar(conn, versie)
    t, fouten, goed = kalibreer(bovenste, budget=budget, rooster=rooster)
    echt = run_benchmark(conn, t, versie).totals
    assert (echt.wrong_links, echt.correct_matches) == (fouten, goed), "snelle telling wijkt af van de benchmark"
    print(f"{k.slug}: drempels {t.text_match:.2f} / cross-linguaal {t.text_match_crosslingual:.2f}"
          f" · {fouten} fouten · dekking {goed}/{echt.same_pairs} ({goed / echt.same_pairs:.1%})", flush=True)

    groepen = groepen_uit_feed(conn, args.feed)
    uitslag = {"model": k.naam, "revisie": k.revisie, "versie": versie, "budget": budget,
               "drempel": t.text_match, "drempel_crosslinguaal": t.text_match_crosslingual,
               "fouten": fouten, "gevonden": goed, "zelfde_paren": echt.same_pairs}
    for naam, drempels in (("eigen drempels", t),) + ((("productiedrempels", config.thresholds),)
                                                     if k.slug == "minilm" else ()):
        tel_, per_soort, partner = meet_natuurlijk(conn, groepen, versie, drempels)
        n = sum(tel_.values())
        regel = {s: c["gevonden"] / sum(c.values()) for s, c in per_soort.items()}
        print(f"  natuurlijke parafrasen ({naam}): gevonden {tel_['gevonden'] / n:.1%}"
              f" · ander record {tel_['fout'] / n:.1%} · tegenspraak {tel_['tegenspraak'] / n:.1%}"
              f" · zelfde taal {regel.get('zelfde taal', 0):.1%} · cross-linguaal {regel.get('cross-linguaal', 0):.1%}"
              f" · mediaan partner {statistics.median(partner):.3f}", flush=True)
        uitslag[f"natuurlijk_{naam}"] = {"n": n, **{k_: v / n for k_, v in tel_.items()},
                                         **{f"gevonden_{s}": v for s, v in regel.items()}}

    if model is not None:
        enkel = []
        for tekst in [r[0] for r in conn.execute("SELECT canonical_text FROM claim LIMIT 40")]:
            t0 = time.perf_counter()
            embed(k, [tekst], model=model, portie=1, pauze=0)
            enkel.append(1000 * (time.perf_counter() - t0))
        dim = len(np.frombuffer(conn.execute(
            "SELECT payload FROM fingerprint WHERE kind = 'text' AND model_version = ? LIMIT 1",
            (versie,)).fetchone()[0], dtype=np.float32))
        n_claims = conn.execute("SELECT count(*) FROM claim").fetchone()[0]
        uitslag |= {"ms_per_vraag_mediaan": statistics.median(enkel), "dimensies": dim,
                    "index_mb": n_claims * dim * 4 / 1e6, "cpu": meter.samenvatting()}
        print(f"  één vraag: mediaan {statistics.median(enkel):.0f} ms · index {n_claims * dim * 4 / 1e6:.0f} MB"
              f" in het geheugen", flush=True)
    (map_ / f"{k.slug}-uitslag.json").write_text(json.dumps(uitslag, indent=2, ensure_ascii=False))



def vergelijk_per_taal(args) -> None:
    """Elke kandidaat met een uitslag, per taal naast productie (B14)."""
    import collections
    import json
    import sqlite3
    from pathlib import Path

    from doublecheck.benchmark import run_benchmark
    from doublecheck.config import Thresholds, load_config
    from doublecheck.storage import connect

    config = load_config()
    bron = os.environ.get("DOUBLECHECK_DB", "doublecheck.db")
    prod = sqlite3.connect(f"file:{bron}?mode=ro", uri=True, check_same_thread=False)
    prod.row_factory = sqlite3.Row
    basis = run_benchmark(prod, config.thresholds, config.model_versions.text_embedding)
    for uitslag in sorted(Path(args.map).glob("*-uitslag.json")):
        u = json.loads(uitslag.read_text())
        slug = uitslag.name.removesuffix("-uitslag.json")
        if slug == "minilm":
            continue
        match, cross = u["drempel"], u["drempel_crosslinguaal"]
        for opgave in args.drempel:
            naam, _, paar = opgave.partition("=")
            if naam == slug:
                match, cross = (float(x) for x in paar.split("/"))
        t = Thresholds(text_match=match, text_related=0.0, image_same=31, text_match_crosslingual=cross)
        resultaat = run_benchmark(connect(Path(args.map) / f"{slug}.db"), t, u["versie"])
        fouten = collections.Counter(o.provenance.split(":")[0] for o in resultaat.outcomes if o.fout)
        basisfouten = collections.Counter(o.provenance.split(":")[0] for o in basis.outcomes if o.fout)
        print(f"\n{slug} ({match:.2f} / {cross:.2f}) tegen productie"
              f" · fouten per soort {dict(fouten)} (productie {dict(basisfouten)})")
        print(f"{'taal':6}{'dekking nu':>12}{'kandidaat':>11}{'verschil':>10}{'fouten':>9}")
        for r in per_taal(basis.per_language, resultaat.per_language, marge=args.marge):
            teken = "  ACHTERUIT" if r.achteruit else ""
            print(f"{r.taal:6}{r.dekking_basis:>12.1%}{r.dekking_kandidaat:>11.1%}{r.verschil:>+10.1%}"
                  f"{f'{r.fouten_basis}→{r.fouten_kandidaat}':>9}{teken}")


def main() -> None:
    import argparse

    import torch
    from threadpoolctl import threadpool_limits

    parser = argparse.ArgumentParser(description="Modelvergelijking op natuurlijke parafrasen (#25.14)")
    parser.add_argument("--volledig", choices=sorted(KANDIDATEN),
                        help="ronde twee voor één model: hele corpus, benchmark en parafrasetoets, in een kopie")
    parser.add_argument("--per-taal", action="store_true",
                        help="na ronde twee: elke kandidaat met een uitslag per taal naast productie (B14)")
    parser.add_argument("--marge", type=float, default=0.05, help="per taal: toegestane daling in dekking")
    parser.add_argument("--drempel", action="append", default=[], metavar="MODEL=MATCH/CROSS",
                        help="per taal: andere drempels dan de gekalibreerde, bv. bgem3=0.87/0.87")
    parser.add_argument("--modellen", default=",".join(KANDIDATEN), help="voorronde: welke modellen")
    parser.add_argument("--pool", type=int, default=15000, help="voorronde: aantal willekeurige afleiders")
    parser.add_argument("--seed", type=int, default=25014)
    parser.add_argument("--threads", type=int, default=2)
    parser.add_argument("--portie", type=int, default=512)
    parser.add_argument("--pauze", type=float, default=1.0)
    parser.add_argument("--feed", default="data/datacommons-claimreview.json")
    parser.add_argument("--map", default="data/modelmeting")
    args = parser.parse_args()
    threadpool_limits(limits=args.threads)
    torch.set_num_threads(args.threads)
    if args.per_taal:
        vergelijk_per_taal(args)
    elif args.volledig:
        volledig(args)
    else:
        voorronde(args)


if __name__ == "__main__":
    main()
