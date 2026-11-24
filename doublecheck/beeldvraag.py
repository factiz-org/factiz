"""Een beeld opzoeken in de beeldindex (PLAN #32.15, #30.4a).

De index bevat per beeld uit een factcheckartikel alleen kenmerken: de PDQ-hash van het hele beeld en van drie vaste
uitsneden (§89), en de CLS-vector van DINOv2-small. Een vraag brengt de hash en de vector van het hele beeld mee, en
die van het beeldgebied als het een screenshot is (`beelduitsnede.beeldgebied`). Alles wordt in het geheugen
uitgerekend; het beeld verlaat deze module niet (DR3, B35).

Eén beslispad (DR4), de variant "PDQ óf DINOv2 met gebied" van §92: PDQ eerst, want bijna gelijke pixels zijn sterker
bewijs dan een gelijkende beschrijving; anders DINOv2 boven de drempel, over het hele beeld en het beeldgebied. Elke
kenmerkenset draagt haar modelversies; zoeken over versies heen weigert (DR6).

Daarnaast de punten (SIFT) als bevestiging (#32.17): niet zoeken door alle beelden, maar bevestigen dat de vraag in
een van de paar artikelen staat die de woorden vinden. Ook de punten dragen hun versie (DR6).

Een kernmodule (#32.7c): de dienst mag haar lenen, de metingen lenen haar ook. In `/check` pas na stap 5 van #32.15 en
een release (B22).
"""

from __future__ import annotations

import base64
import io
from dataclasses import dataclass

import numpy as np

from doublecheck.beeldembedding import BEELDMODEL, alle_vectoren
from doublecheck.beelduitsnede import PANELEN, UITSNEDEN, beeldgebied, panelen as knip_panelen
from doublecheck.image_fingerprint import as_image, pdq_met_kwaliteit

PDQ = "pdq-256-v1"
VERSIES = {"pdq": PDQ, "dino": BEELDMODEL}
MIN_KWALITEIT = 50   # onder deze PDQ-kwaliteit zegt een hash weinig (vlakke beelden, §88)
MAX_ZIJDE = 1024     # zoals de beelden van §90 en §92, waar de drempel van DINOv2 vandaan komt
_POPCOUNT = np.unpackbits(np.arange(256, dtype=np.uint8)[:, None], axis=1).sum(axis=1).astype(np.uint16)


class Versiefout(ValueError):
    """Kenmerken van een andere modelversie dan de index: nooit vergelijken (DR6)."""


def _open(beeld):
    beeld = as_image(beeld).convert("RGB")
    beeld.thumbnail((MAX_ZIJDE, MAX_ZIJDE))
    return beeld


def vector_naar_tekst(v: np.ndarray) -> str:
    """Een vector als korte tekst voor een regel: float16, base64."""
    return base64.b64encode(np.asarray(v, dtype=np.float16).tobytes()).decode("ascii")


def vector_uit_tekst(tekst: str) -> np.ndarray:
    return np.frombuffer(base64.b64decode(tekst), dtype=np.float16).astype(np.float32)


def indexkenmerken(beeld, vectoren=alle_vectoren, panelen: bool = False) -> dict:
    """Wat de index van een beeld bewaart: de maat, de PDQ-hashes van het hele beeld en de drie uitsneden met de
    kwaliteit, de vector van het hele beeld; en, omdat elk indexbeeld ook een vraag kan zijn (R1), het beeldgebied
    met zijn hash en vector. Met `panelen` ook per paneel van een collage of post een hash en een vector
    (`beelduitsnede.panelen`, #32.15 stap 2b)."""
    beeld = _open(beeld)
    b, h = beeld.size
    hexa, kwaliteit = pdq_met_kwaliteit(beeld)
    pdq = [hexa] + [pdq_met_kwaliteit(beeld.crop((int(b * l), int(h * t), int(b * r), int(h * o))))[0]
                    for _, (l, t, r, o) in UITSNEDEN]
    gebied = beeldgebied(beeld)
    vakken = knip_panelen(beeld) if panelen else []
    delen = [beeld] + ([beeld.crop(gebied)] if gebied else []) + [beeld.crop(v) for v in vakken]
    v = vectoren(delen)["cls"]
    uit = {"versies": dict(VERSIES), "breedte": b, "hoogte": h, "pdq": pdq, "kwaliteit": kwaliteit,
           "vector": vector_naar_tekst(v[0]), "gebied": list(gebied) if gebied else None,
           "gebied_pdq": None, "gebied_vector": None, "panelen": None}
    if gebied:
        uit["gebied_pdq"] = pdq_met_kwaliteit(delen[1])[0]
        uit["gebied_vector"] = vector_naar_tekst(v[1])
    if panelen:
        eerste = 2 if gebied else 1
        stukken = [{"vak": list(vak), **dict(zip(("pdq", "kwaliteit"), pdq_met_kwaliteit(delen[eerste + i]))),
                    "vector": vector_naar_tekst(v[eerste + i])} for i, vak in enumerate(vakken)]
        # een vlak paneel (een zwarte zijkant, een leeg vak) zegt te weinig, net als een vlakke hash
        uit["panelen"] = {"versie": PANELEN, "delen": [d for d in stukken if d["kwaliteit"] >= MIN_KWALITEIT]}
    return uit


def vraagkenmerken(beeld, vectoren=alle_vectoren) -> dict:
    """Wat een vraag meebrengt: hash en vector van het hele beeld, en van het beeldgebied als er een is."""
    beeld = _open(beeld)
    gebied = beeldgebied(beeld)
    delen = [beeld] + ([beeld.crop(gebied)] if gebied else [])
    v = vectoren(delen)["cls"]
    return {"versies": dict(VERSIES), "pdq": [pdq_met_kwaliteit(d)[0] for d in delen],
            "vectoren": [vector_naar_tekst(x) for x in v], "gebied": list(gebied) if gebied else None}


def vraag_uit_index(kenmerken: dict) -> dict:
    """Een indexbeeld als vraag: dezelfde kenmerken als `vraagkenmerken` op dat beeld zou geven."""
    return {"versies": kenmerken["versies"], "gebied": kenmerken["gebied"],
            "pdq": [kenmerken["pdq"][0]] + ([kenmerken["gebied_pdq"]] if kenmerken["gebied_pdq"] else []),
            "vectoren": [kenmerken["vector"]] + ([kenmerken["gebied_vector"]] if kenmerken["gebied_vector"] else [])}


@dataclass
class Beeldindex:
    """De beelden met hun kenmerken; `beelden[i]` is wat de lezer over beeld i te zien krijgt (claim, artikel, adres)."""
    beelden: list[dict]
    pdq: np.ndarray          # (m, 32) uint8: de hashes met genoeg kwaliteit
    eigenaar: np.ndarray     # (m,) welk beeld bij elke hash hoort
    vectoren: np.ndarray     # (n + p, 384) float32: eerst één per beeld, dan de panelen
    versies: dict
    vector_eigenaar: np.ndarray | None = None   # (n + p,) welk beeld bij elke vector hoort

    def __post_init__(self):
        if self.vector_eigenaar is None:
            self.vector_eigenaar = np.arange(len(self.vectoren), dtype=np.int64)

    @classmethod
    def bouw(cls, beelden: list[dict], kenmerken: list[dict]) -> "Beeldindex":
        """Uit de beelden en hun `indexkenmerken`, in dezelfde volgorde; een hash met te weinig kwaliteit gaat niet
        mee op de PDQ-route. Panelen tellen mee waar ze er zijn, allemaal van één versie (DR6)."""
        for k in kenmerken:
            if k["versies"] != VERSIES:
                raise Versiefout(f"kenmerken van {k['versies']}, de index kent {VERSIES}")
        paneelversies = {k["panelen"]["versie"] for k in kenmerken if k.get("panelen")}
        if len(paneelversies) > 1:
            raise Versiefout(f"panelen van {sorted(paneelversies)} in één index")
        rijen, eigenaar, extra, extra_eigenaar = [], [], [], []
        for i, k in enumerate(kenmerken):
            hashes = [h for h in k["pdq"]] if k["kwaliteit"] >= MIN_KWALITEIT else []
            delen = (k.get("panelen") or {}).get("delen", [])
            hashes += [d["pdq"] for d in delen if d["kwaliteit"] >= MIN_KWALITEIT]
            rijen += [np.frombuffer(bytes.fromhex(h), dtype=np.uint8) for h in hashes]
            eigenaar += [i] * len(hashes)
            extra += [vector_uit_tekst(d["vector"]) for d in delen]
            extra_eigenaar += [i] * len(delen)
        pdq = np.vstack(rijen) if rijen else np.empty((0, 32), dtype=np.uint8)
        vectoren = (np.vstack([vector_uit_tekst(k["vector"]) for k in kenmerken] + extra) if kenmerken
                    else np.empty((0, 384), dtype=np.float32))
        versies = dict(VERSIES) | ({"panelen": paneelversies.pop()} if paneelversies else {})
        return cls(list(beelden), pdq, np.asarray(eigenaar, dtype=np.int64), vectoren, versies,
                   np.concatenate([np.arange(len(kenmerken)), extra_eigenaar]).astype(np.int64))

    def __len__(self) -> int:
        return len(self.beelden)


def routes(index: Beeldindex, vraag: dict, uitsluiten: np.ndarray | None = None) -> dict:
    """De beste kandidaat per route, voor `beslis` en voor de meting van de varianten: `pdq` als (beeld, afstand)
    over alle hashes van de vraag en de index, `dino` als (beeld, gelijkenis) op het hele beeld, en `dino_gebied` ook
    over het beeldgebied. `uitsluiten` (per beeld `True`) laat beelden weg, zoals de eigen redactie in R1."""
    if vraag["versies"] != {k: index.versies[k] for k in VERSIES}:
        raise Versiefout(f"een vraag met {vraag['versies']} tegen een index met {index.versies}")
    uit = {"pdq": None, "dino": None, "dino_gebied": None}
    if not len(index):
        return uit
    if len(index.pdq):
        q = np.vstack([np.frombuffer(bytes.fromhex(h), dtype=np.uint8) for h in vraag["pdq"]])
        d = _POPCOUNT[index.pdq[None, :, :] ^ q[:, None, :]].sum(axis=2).min(axis=0).astype(np.int64)
        if uitsluiten is not None:
            d[uitsluiten[index.eigenaar]] = 10_000
        j = int(np.argmin(d))
        if d[j] < 10_000:
            uit["pdq"] = (int(index.eigenaar[j]), int(d[j]))
    s = np.vstack([vector_uit_tekst(t) for t in vraag["vectoren"]]) @ index.vectoren.T
    if uitsluiten is not None:
        s[:, uitsluiten[index.vector_eigenaar]] = -np.inf
    j = int(np.argmax(s[0]))
    if np.isfinite(s[0, j]):
        uit["dino"] = (int(index.vector_eigenaar[j]), float(s[0, j]))
    rij, k = np.unravel_index(int(np.argmax(s)), s.shape)
    if np.isfinite(s[rij, k]):
        uit["dino_gebied"] = (int(index.vector_eigenaar[k]), float(s[rij, k]))
    return uit


def beslis(pdq, dino, *, drempel_pdq: int, drempel_dino: float) -> int | None:
    """PDQ eerst: bijna gelijke pixels zijn sterker bewijs dan een gelijkende beschrijving. `pdq` is (beeld,
    afstand), `dino` (beeld, gelijkenis), en `None` waar een variant die route niet heeft."""
    if pdq is not None and pdq[1] <= drempel_pdq:
        return pdq[0]
    if dino is not None and dino[1] >= drempel_dino:
        return dino[0]
    return None


def zoek(index: Beeldindex, vraag: dict, *, drempel_pdq: int, drempel_dino: float,
         uitsluiten: np.ndarray | None = None) -> dict | None:
    """Het beeld in de index dat hetzelfde is als de vraag, met de route die het vond; `None` als er geen is."""
    r = routes(index, vraag, uitsluiten)
    j = beslis(r["pdq"], r["dino_gebied"], drempel_pdq=drempel_pdq, drempel_dino=drempel_dino)
    if j is None:
        return None
    route = "pdq" if r["pdq"] is not None and r["pdq"][0] == j and r["pdq"][1] <= drempel_pdq else "dino"
    return {**index.beelden[j], "route": route, "afstand": r["pdq"][1] if route == "pdq" else None,
            "gelijkenis": r["dino_gebied"][1] if route == "dino" else None}


# --- punten, als bevestiging (#32.17) ---------------------------------------------------------------
#
# Lokale punten (SIFT) met een geometrische controle: twee beelden zijn hetzelfde als genoeg punten met één
# gelijkvormigheid (schaal, draaiing, verschuiving) op elkaar passen. Ongevoelig voor kader, stempel, uitsnede en
# collage (§187). Niet als zoeker door alle beelden, maar als bevestiger op de paar artikelen die de woorden vinden.

PUNTVERSIE = "sift-1000-v1"     # OpenCV-SIFT, hoogstens 1.000 punten op hoogstens 1.024 pixels
RATIO, RANSAC_PX, MAX_PUNTEN = 0.75, 5.0, 1000
# §189: zonder deze grens klapte de vorm soms in tot een punt (schaal 0), en 'pasten' 50 tot 90 punten van een vraag
# op één klont punten in een ander beeld. Tot 2026-11-01 (§187 en de regel van #32.17) zonder; "sift-ransac-v2" erna.
VERGELIJKING = "sift-ransac-v2"
MIN_SCHAAL, MAX_SCHAAL = 0.05, 20.0



def puntkenmerken(beeld) -> dict:
    """De SIFT-punten van een beeld (hoogstens 1.024 pixels, zoals de index): plaats, beschrijving en sterkte, de maat
    en de versie. De beschrijvingen zijn hele getallen van 0 tot 255."""
    import cv2

    grijs = as_image(beeld).convert("L")
    grijs.thumbnail((MAX_ZIJDE, MAX_ZIJDE))
    punten, beschrijving = cv2.SIFT_create(nfeatures=MAX_PUNTEN).detectAndCompute(np.asarray(grijs), None)
    return {"versie": PUNTVERSIE, "xy": np.array([k.pt for k in punten], dtype=np.float32).reshape(-1, 2),
            "des": beschrijving if beschrijving is not None else np.empty((0, 128), dtype=np.float32),
            "sterkte": np.array([k.response for k in punten], dtype=np.float32), "maat": grijs.size}


def sterkste(kenmerken: dict, n: int) -> dict:
    """Alleen de `n` sterkste punten, in hun oorspronkelijke volgorde; voor een index die de helft vraagt."""
    houden = np.sort(np.argsort(-kenmerken["sterkte"], kind="stable")[:n])
    return {**kenmerken, "xy": kenmerken["xy"][houden], "des": kenmerken["des"][houden],
            "sterkte": kenmerken["sterkte"][houden]}


# De opmaak eruit (#32.22): wat een redactie op veel van haar beelden zet (stempel, balk, logo) is geen foto. In §194
# waren alle valse paren zulke opmaak op een deelbeeld. Per site een vaste referentie: de beelden van hoogstens 80
# artikelen, per artikel hoogstens 3, het deelbeeld eerst.
OPMAAK = "opmaak-v1"
OPMAAK_ARTIKELEN, OPMAAK_BEELDEN, OPMAAK_K = 80, 3, 4
# #32.23: alleen wat op dezelfde plek terugkomt (de balk, het stempel), niet tekst of een foto die ergens anders staat
# (§195). De plek als deel van het beeld, alleen tegen een beeld van bijna dezelfde vorm.
OPMAAK_V2 = "opmaak-v2"
OPMAAK_PLEK, OPMAAK_VORM = 0.03, 0.05


def _deel_van_beeld(punten: dict) -> tuple[np.ndarray, float]:
    breedte, hoogte = punten["maat"]
    return np.asarray(punten["xy"], dtype=np.float32) / np.float32([breedte, hoogte]), breedte / hoogte


def opmaakmasker(punten: dict, andere: list[list[dict]], k: int = OPMAAK_K, plek: float | None = None,
                 vorm: float = OPMAAK_VORM) -> np.ndarray:
    """Welke punten van een artikelbeeld opmaak zijn: met de ratiotoets een tegenhanger in een beeld van minstens `k`
    andere artikelen van dezelfde site. `andere` geeft per ander artikel de punten van zijn beelden; per beeld getoetst,
    want een stempel dat twee keer in één artikel staat, faalt anders op de ratiotoets. Een foto staat zelden in vier
    artikelen van één redactie; een stempel wel. Met `plek` (`opmaak-v2`) telt de tegenhanger alleen op dezelfde plek,
    binnen `plek` van de breedte en de hoogte, in een beeld waarvan de vorm hoogstens `vorm` afwijkt; zo haalt de regel
    nooit meer weg dan zonder."""
    import cv2

    vraag = np.asarray(punten["des"], dtype=np.float32)
    teller = np.zeros(len(vraag), dtype=np.int32)
    zoeker = cv2.BFMatcher(cv2.NORM_L2)
    if plek is not None and len(vraag):
        eigen_xy, eigen_vorm = _deel_van_beeld(punten)
    for artikel in andere:
        raak = np.zeros(len(vraag), dtype=bool)
        for beeld in artikel:
            if beeld.get("versie", PUNTVERSIE) != punten.get("versie", PUNTVERSIE):
                raise Versiefout(f"punten van {punten.get('versie')} tegen opmaak van {beeld.get('versie')}")
            if len(vraag) == 0 or len(beeld["des"]) < 2:
                continue
            if plek is not None:
                ander_xy, ander_vorm = _deel_van_beeld(beeld)
                if abs(ander_vorm / eigen_vorm - 1) > vorm:
                    continue
            for p in zoeker.knnMatch(vraag, np.asarray(beeld["des"], dtype=np.float32), k=2):
                if len(p) == 2 and p[0].distance < RATIO * p[1].distance and (
                        plek is None or bool(np.all(np.abs(eigen_xy[p[0].queryIdx] - ander_xy[p[0].trainIdx]) <= plek))):
                    raak[p[0].queryIdx] = True
        teller += raak
    return teller >= k


def zonder_punten(punten: dict, masker: np.ndarray) -> dict:
    """De punten zonder de gemaskeerde; versie en maat blijven, zodat de dekking op dezelfde vraag rekent."""
    houden = ~np.asarray(masker, dtype=bool)
    return {**punten, "xy": punten["xy"][houden], "des": punten["des"][houden], "sterkte": punten["sterkte"][houden]}


def puntvergelijking(vraag: dict, index: dict) -> tuple[int, float]:
    """Hoeveel punten van de vraag met één gelijkvormigheid op het indexbeeld passen (ratiotoets van Lowe, RANSAC),
    en welk deel van de vraag hun omhullende beslaat. Punten van een andere versie: nooit vergelijken (DR6)."""
    return puntvorm(vraag, index)[:2]


def puntvorm(vraag: dict, index: dict) -> tuple[int, float, np.ndarray | None]:
    """Als `puntvergelijking`, en de gevonden vorm (schaal, draaiing, verschuiving; van de vraag naar het indexbeeld,
    2 bij 3), of `None` als er geen vorm is."""
    import cv2

    if vraag.get("versie", PUNTVERSIE) != index.get("versie", PUNTVERSIE):
        raise Versiefout(f"punten van {vraag.get('versie')} tegen punten van {index.get('versie')}")
    if len(vraag["des"]) < 2 or len(index["des"]) < 2:
        return 0, 0.0, None
    paren = cv2.BFMatcher(cv2.NORM_L2).knnMatch(np.asarray(vraag["des"], dtype=np.float32),
                                                np.asarray(index["des"], dtype=np.float32), k=2)
    goed = [p[0] for p in paren if len(p) == 2 and p[0].distance < RATIO * p[1].distance]
    a = vraag["xy"][[m.queryIdx for m in goed]]
    b = index["xy"][[m.trainIdx for m in goed]]
    for _ in range(3):
        if len(a) < 4:
            return 0, 0.0, None
        cv2.setRNGSeed(0)
        # schaal, draaiing en verschuiving: genoeg voor een kopie, en een volledige homografie past op een smalle
        # strook (een knoppenbalk) ook toevallige punten mee
        vorm, masker = cv2.estimateAffinePartial2D(a, b, method=cv2.RANSAC, ransacReprojThreshold=RANSAC_PX)
        if vorm is None:
            return 0, 0.0, None
        masker = masker.ravel().astype(bool)
        if MIN_SCHAAL <= float(np.hypot(vorm[0, 0], vorm[1, 0])) <= MAX_SCHAAL:
            break
        # een ingeklapte vorm (§189): zijn punten eruit, en opnieuw zoeken
        a, b = a[~masker], b[~masker]
    else:
        return 0, 0.0, None
    binnen = a[masker]
    if len(binnen) < 3:
        return len(binnen), 0.0, vorm
    breedte, hoogte = vraag["maat"]
    return len(binnen), float(cv2.contourArea(cv2.convexHull(binnen)) / (breedte * hoogte)), vorm


def bevestigd(pdq: int | None, punten: int, dekking: float, *, drempel_pdq: int, min_punten: int,
              min_dekking: float) -> bool:
    """Hetzelfde beeld: de PDQ-afstand binnen de drempel, of genoeg punten die samen genoeg van de vraag beslaan (niet
    alleen een gedeeld logo of de knoppenbalk van een app). `pdq` is `None` als geen hash genoeg kwaliteit heeft."""
    return (pdq is not None and pdq <= drempel_pdq) or (punten >= min_punten and dekking >= min_dekking)


# De rest van de foto moet ook passen (#32.24): na `opmaak-v2` blijven valse paren over die een afbeelding van het
# onderwerp delen (een partijlogo, een geplakte vlag); de punten passen op dat stukje, de rest van de beelden niet (§196).
REST = "rest-v1"
REST_RASTER, REST_GEDEKT, REST_OPMAAK, REST_SPREIDING = 8, 0.75, 1, 8.0
REST_MAAT, REST_CORRELATIE, REST_AANDEEL, REST_VAKKEN = 16, 0.5, 0.5, 4


def grijs_voor_punten(beeld) -> np.ndarray:
    """Het beeld in grijs op de maat waarop `puntkenmerken` zijn punten zet, zodat de vorm erop past."""
    grijs = as_image(beeld).convert("L")
    grijs.thumbnail((MAX_ZIJDE, MAX_ZIJDE))
    return np.asarray(grijs)


def restcontrole(vraag: np.ndarray, index: np.ndarray, vorm: np.ndarray, opmaak_xy: np.ndarray | None = None) -> dict:
    """Past de rest van de foto ook? Het indexbeeld gaat met de vorm van de vergelijking op de vraag; de vraag in 8 bij 8
    vakken. Een vak telt als het voor minstens 75% onder het indexbeeld valt, er hoogstens 1 opmaakpunt van het
    indexbeeld in ligt en het in beide beelden iets laat zien; het klopt bij een correlatie van minstens 0,5 op 16 bij
    16. Goed bij minstens de helft van minstens 4 vakken; te weinig vakken om te oordelen is nooit goed."""
    import cv2

    hoogte, breedte = vraag.shape
    terug = cv2.invertAffineTransform(np.asarray(vorm, dtype=np.float64))
    gelegd = cv2.warpAffine(index, terug, (breedte, hoogte), flags=cv2.INTER_LINEAR)
    gedekt = cv2.warpAffine(np.ones_like(index, dtype=np.uint8), terug, (breedte, hoogte), flags=cv2.INTER_NEAREST)
    opmaak = np.zeros((REST_RASTER, REST_RASTER), dtype=np.int32)
    if opmaak_xy is not None and len(opmaak_xy):
        xy = cv2.transform(np.asarray(opmaak_xy, dtype=np.float64).reshape(-1, 1, 2), terug).reshape(-1, 2)
        kol, rij = (xy[:, 0] * REST_RASTER // breedte).astype(int), (xy[:, 1] * REST_RASTER // hoogte).astype(int)
        binnen = (kol >= 0) & (kol < REST_RASTER) & (rij >= 0) & (rij < REST_RASTER)
        np.add.at(opmaak, (rij[binnen], kol[binnen]), 1)
    vakken, kloppen, kaart = 0, 0, []
    for r in range(REST_RASTER):
        for k in range(REST_RASTER):
            y0, y1 = r * hoogte // REST_RASTER, (r + 1) * hoogte // REST_RASTER
            x0, x1 = k * breedte // REST_RASTER, (k + 1) * breedte // REST_RASTER
            a, b = vraag[y0:y1, x0:x1], gelegd[y0:y1, x0:x1]
            if a.size == 0 or gedekt[y0:y1, x0:x1].mean() < REST_GEDEKT or opmaak[r, k] > REST_OPMAAK \
                    or a.std() < REST_SPREIDING or b.std() < REST_SPREIDING:
                kaart.append(".")
                continue
            a = cv2.resize(a, (REST_MAAT, REST_MAAT), interpolation=cv2.INTER_AREA).astype(np.float64).ravel()
            b = cv2.resize(b, (REST_MAAT, REST_MAAT), interpolation=cv2.INTER_AREA).astype(np.float64).ravel()
            a, b = a - a.mean(), b - b.mean()
            noemer = float(np.sqrt((a * a).sum() * (b * b).sum()))
            klopt = noemer > 0 and float((a * b).sum()) / noemer >= REST_CORRELATIE
            vakken += 1
            kloppen += klopt
            kaart.append("+" if klopt else "-")
    return {"vakken": vakken, "kloppen": kloppen, "kaart": "".join(kaart),
            "goed": vakken >= REST_VAKKEN and kloppen >= REST_AANDEEL * vakken}


def punten_naar_bytes(kenmerken: dict) -> bytes:
    """De punten zonder verlies op schijf: de beschrijvingen als bytes (ze zijn hele getallen), de rest als float32."""
    buf = io.BytesIO()
    np.savez_compressed(buf, xy=kenmerken["xy"], des=np.asarray(kenmerken["des"]).astype(np.uint8),
                        sterkte=kenmerken["sterkte"], maat=np.asarray(kenmerken["maat"], dtype=np.int32),
                        versie=np.array(kenmerken["versie"]))
    return buf.getvalue()


def punten_uit_bytes(inhoud: bytes) -> dict:
    with np.load(io.BytesIO(inhoud)) as d:
        return {"versie": str(d["versie"]), "xy": d["xy"], "des": d["des"].astype(np.float32),
                "sterkte": d["sterkte"], "maat": tuple(int(x) for x in d["maat"])}
