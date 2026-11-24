"""De schikking van het netwerk van namen (PLAN #34.2ai, SPECS E9.S18 AC4): waar elke cirkel staat. Eerst krachten
(ForceAtlas2: elke naam duwt elke andere weg, een lijn trekt twee namen naar elkaar toe, en zwaartekracht houdt losse
namen in beeld), met een vast zaad, zodat elke opvraag dezelfde plek geeft. Daarna
schuiven cirkels en labels uit elkaar tot niets meer overlapt. Het label staat onder de cirkel; de breedte komt van de
aanroeper (de breedste schrijfwijze over de vijf talen), dus elke taal krijgt dezelfde plek. Geen bibliotheek: numpy."""

from __future__ import annotations

import math

import numpy as np

BREED, HOOG = 900.0, 560.0
LABEL_HOOG = 15.0        # de hoogte van een label onder zijn cirkel
TUSSEN = 3.0             # de ruimte die tussen twee cirkels of labels overblijft
MARGE = 0.01
STAPPEN = 500
DUWKRACHT = 100.0       # hoe hard twee namen elkaar wegduwen
ZWAARTE = .03           # hoe hard elke naam naar het midden wordt getrokken
DUWEN = 600              # hoogstens zoveel rondes om overlap weg te schuiven
GROEI = 6                # zo vaak wordt het vlak groter als het niet past


def _dozen(plek: np.ndarray, r: np.ndarray, w: np.ndarray) -> tuple[np.ndarray, ...]:
    half = np.maximum(r, w / 2)
    onder = r + np.where(w > 0, LABEL_HOOG, 0.0)
    return plek[:, 0] - half, plek[:, 0] + half, plek[:, 1] - r, plek[:, 1] + onder


def _paar(plek: np.ndarray, r: np.ndarray, w: np.ndarray, i: int, j: int) -> tuple[tuple[float, float], ...]:
    """De dozen van twee namen: (links, boven) en (rechts, onder) van elk."""
    uit = []
    for k in (i, j):
        half = max(r[k], w[k] / 2)
        uit += [(plek[k, 0] - half, plek[k, 1] - r[k]),
                (plek[k, 0] + half, plek[k, 1] + r[k] + (LABEL_HOOG if w[k] > 0 else 0.0))]
    return tuple(uit)


def _krachten(n: int, randen: list[tuple[int, int, float]], breed: float, hoog: float, zaad: int) -> np.ndarray:
    """ForceAtlas2 (Jacomy e.a., 2014), in de lin-log-vorm met sterke zwaartekracht: namen met veel lijnen duwen harder
    (massa is het aantal lijnen plus één), een lijn trekt met de logaritme van de afstand (dat maakt groepen zichtbaar),
    en de zwaartekracht houdt namen zonder lijn dicht bij de rest. Gekozen op de echte uitgave uit zes varianten."""
    rng = np.random.default_rng(zaad)
    plek = np.column_stack([rng.uniform(-1, 1, n), rng.uniform(-1, 1, n)]) * 100
    if n == 1:
        return plek
    gewicht = np.zeros((n, n))
    for i, j, w in randen:
        gewicht[i, j] = gewicht[j, i] = math.log1p(w)
    massa = (gewicht > 0).sum(1) + 1.0
    warmte = 10.0
    for _ in range(STAPPEN):
        d = plek[:, None, :] - plek[None, :, :]
        afstand = np.sqrt((d ** 2).sum(-1)) + 1e-6
        duw = (DUWKRACHT * massa[:, None] * massa[None, :] / afstand ** 2)[:, :, None] * d
        trekt = -(gewicht * np.log1p(afstand) / afstand)[:, :, None] * d
        verschuif = duw.sum(1) + trekt.sum(1) - ZWAARTE * massa[:, None] * plek
        lengte = np.linalg.norm(verschuif, axis=1, keepdims=True) + 1e-9
        plek += verschuif / lengte * np.minimum(lengte, warmte)
        warmte = max(warmte * .995, .3)
    return plek


def _past(ruw: np.ndarray, r: np.ndarray, w: np.ndarray, breed: float, hoog: float) -> np.ndarray | None:
    """De plekken van de krachten in het vlak gezet, en dan uit elkaar geschoven; None als het niet past."""
    half = np.maximum(r, w / 2)
    boven, onder = r, r + np.where(w > 0, LABEL_HOOG, 0.0)
    laag, hoogst = ruw.min(0), ruw.max(0)
    spreid = np.where(hoogst - laag > 1e-9, hoogst - laag, 1.0)
    rand_x, rand_y = half.max() + .5, max(boven.max(), onder.max()) + .5
    plek = np.column_stack([rand_x + (ruw[:, 0] - laag[0]) / spreid[0] * (breed - 2 * rand_x),
                            rand_y + (ruw[:, 1] - laag[1]) / spreid[1] * (hoog - 2 * rand_y)])
    if len(plek) == 1:
        plek[:] = [breed / 2, hoog / 2]
    links, rechts = np.maximum(r, w / 2), np.maximum(r, w / 2)
    n = len(plek)
    for _ in range(DUWEN):
        x0, x1, y0, y1 = _dozen(plek, r, w)
        over_x = np.minimum(x1[:, None], x1[None, :]) - np.maximum(x0[:, None], x0[None, :]) + TUSSEN
        over_y = np.minimum(y1[:, None], y1[None, :]) - np.maximum(y0[:, None], y0[None, :]) + TUSSEN
        # een fractie van een punt telt niet: anders noemt de ene rekening het botsen en de andere niet
        botst = (over_x > MARGE) & (over_y > MARGE) & np.triu(np.ones((n, n), dtype=bool), 1)
        if not botst.any():
            return plek
        # per paar, één voor één (alles tegelijk schiet heen en weer): elk de helft van de overlap, langs de as waar
        # het minst overlapt; wie links (boven) staat, gaat naar links (boven), bij gelijke plek beslist de volgorde
        for i, j in zip(*np.nonzero(botst)):
            a0, a1, b0, b1 = _paar(plek, r, w, i, j)
            ox, oy = min(a1[0], b1[0]) - max(a0[0], b0[0]) + TUSSEN, min(a1[1], b1[1]) - max(a0[1], b0[1]) + TUSSEN
            if ox <= MARGE or oy <= MARGE:
                continue
            as_, over = (0, ox) if ox <= oy else (1, oy)
            kant = 1.0 if plek[i, as_] > plek[j, as_] or (plek[i, as_] == plek[j, as_] and i > j) else -1.0
            plek[i, as_] += kant * (over / 2 + MARGE)
            plek[j, as_] -= kant * (over / 2 + MARGE)
            for k in (i, j):          # een halve punt van de rand: na het afronden blijft alles binnen het vlak
                plek[k, 0] = min(max(plek[k, 0], links[k] + .5), breed - rechts[k] - .5)
                plek[k, 1] = min(max(plek[k, 1], boven[k] + .5), hoog - onder[k] - .5)
    return None


def schik(stralen: list[float], randen: list[tuple[int, int, float]], labels: list[float], *, breed: float = BREED,
          hoog: float = HOOG, zaad: int = 7) -> dict:
    """Per naam (x, y) in een vlak van `breed` bij `hoog`. `randen` zijn (i, j, hoe vaak samen), `labels` de breedte van
    het label onder elke cirkel (0: geen label). Past het niet, dan wordt het vlak een stuk hoger en breder."""
    n = len(stralen)
    if n == 0:
        return {"plek": [], "breed": breed, "hoog": hoog}
    r, w = np.asarray(stralen, dtype=float), np.asarray(labels, dtype=float)
    for _ in range(GROEI + 1):
        plek = _past(_krachten(n, randen, breed, hoog, zaad), r, w, breed, hoog)
        if plek is not None:
            break
        breed, hoog = breed * 1.05, hoog * 1.15
    else:
        raise ValueError("het netwerk past niet in het vlak")
    return {"plek": [(round(float(x), 1), round(float(y), 1)) for x, y in plek], "breed": round(breed, 1),
            "hoog": round(hoog, 1)}
