"""De velden van de site (PLAN.md #23.14, DESIGN §4h en D11).

De beelden op factiz.org zijn geen foto's en geen werk van een beeldmodel: een
eigen script tekent ze uit een vaste seed, en het beeld bovenaan de homepage
uit de checks zelf. Deze tests houden dat eerlijk: elk beeld heeft zijn
herkomst, het script tekent het opnieuw zoals het er staat, witte tekst blijft
leesbaar waar hij komt, en geen veld draagt alarmrood.
"""

import io
import re

import numpy as np
import pytest
from PIL import Image

from doublecheck import velden
import pathlib

RELEASES = (pathlib.Path(__file__).resolve().parent.parent / "docs" / "RELEASES.md").read_text(encoding="utf-8")


def _talen_bij_release() -> int:
    """Het aantal talen van de huidige releasekaart (voorheen via de motorkap, die met de oude site wegging, #34.2f)."""
    start = RELEASES.index("## Huidige release")
    kaart = RELEASES[start:RELEASES.find("\n## ", start + 1)]
    corpus = re.search(r"\| corpus bij release \|[^|\n]*?([\d.]+) claims, ([\d.]+) checks[^|\n]*?(\d+) talen", kaart)
    assert corpus
    return int(corpus.group(3))

# de basisvelden; in dezelfde map staan sinds PLAN #34.2f ook de velden per thema en dossier (test_velden_platform)
HERKOMST = velden.HERKOMST_BASIS.read_text(encoding="utf-8")
BESTANDEN = sorted([velden.UIT / f"{naam}.webp" for naam in velden.VELDEN] + [velden.DELEN])


def _pixels(pad) -> np.ndarray:
    with Image.open(pad) as beeld:
        return np.asarray(beeld.convert("RGB"))


def test_every_image_on_the_site_is_a_field_with_its_provenance():
    verwacht = {f"{naam}.webp" for naam in velden.VELDEN} | {velden.DELEN.name}
    assert {p.name for p in BESTANDEN} == verwacht and all(p.exists() for p in BESTANDEN)
    assert f"script {velden.VERSIE}" in HERKOMST
    for naam, veld in velden.VELDEN.items():
        regel = re.search(rf"^- `{naam}\.webp`: (.*)$", HERKOMST, flags=re.M)
        assert regel, f"{naam}.webp ontbreekt in HERKOMST.md"
        assert f"seed {veld.seed}," in regel.group(1), naam
        assert f"{veld.breedte}×{veld.hoogte}" in regel.group(1), naam
    assert re.search(rf"^- `{velden.DELEN.name}`: ", HERKOMST, flags=re.M)


@pytest.mark.parametrize("naam", sorted(velden.VELDEN))
def test_the_script_redraws_each_field_from_its_seed(naam):
    """Hetzelfde commando geeft hetzelfde beeld. Een marge van één tint per
    kanaal, voor een andere versie van de encoder; meer betekent dat het
    script of de seed veranderde zonder dat het beeld opnieuw gemaakt is."""
    nieuw = np.asarray(Image.open(io.BytesIO(velden.webp(velden.teken(naam)))).convert("RGB"))
    oud = _pixels(velden.UIT / f"{naam}.webp")
    assert nieuw.shape == oud.shape
    assert np.abs(nieuw.astype(int) - oud.astype(int)).mean() <= 1.0, naam


def test_no_image_weighs_more_than_200_kb():
    for pad in BESTANDEN:
        assert pad.stat().st_size <= 200 * 1024, (pad.name, pad.stat().st_size // 1024)


@pytest.mark.parametrize("naam", sorted(velden.VELDEN))
def test_white_text_stays_readable_in_every_text_zone(naam):
    """§4h: na de schaduwlaag van de pagina haalt wit in elke tekstzone 3:1
    voor koppen en 4,5:1 voor alle andere tekst, tegen de lichtste 5% van de
    pixels. Gemeten op het bestand dat bezoekers krijgen."""
    pixels = _pixels(velden.UIT / f"{naam}.webp")
    zones = velden.VELDEN[naam].zones
    for zone in zones:
        assert velden.contrast_wit(pixels, zone) >= zone.minimum, (naam, zone.naam)


def test_the_contrast_measure_catches_a_light_zone():
    """De meting zelf: wit op een lichtgrijs vlak zakt onder 4,5:1, op een
    donker vlak niet, en de schaduwlaag telt mee."""
    zone = velden.Zone("tekst", (0, 0, 1, 1), 4.5, 0.0)
    licht = np.full((40, 40, 3), 200, np.uint8)
    donker = np.full((40, 40, 3), 60, np.uint8)
    assert velden.contrast_wit(licht, zone) < 2
    assert velden.contrast_wit(donker, zone) > 9
    assert velden.contrast_wit(licht, velden.Zone("tekst", (0, 0, 1, 1), 4.5, 0.6)) > 4.5


@pytest.mark.parametrize("pad", BESTANDEN, ids=lambda p: p.name)
def test_no_field_carries_alarm_red(pad):
    """DESIGN §4h en D6: rood alleen in de schaal van de meter, nooit in een
    veld. De warme gloed rond het licht is amber, geen rood."""
    rgb = _pixels(pad).astype(float) / 255
    hoog, laag = rgb.max(axis=2), rgb.min(axis=2)
    verzadiging = np.where(hoog > 0, (hoog - laag) / np.maximum(hoog, 1e-6), 0)
    rood = (rgb[..., 0] == hoog) & (rgb[..., 1] - rgb[..., 2] < (hoog - laag) * 0.25)
    assert (rood & (verzadiging > 0.5) & (hoog > 0.35)).mean() < 0.001, pad.name


def test_the_corpus_field_draws_every_language_of_the_index_and_counts_the_rest():
    """Elke taal van de index tekent een spoor; de taalcodes zijn die van de
    releasekaart. Wat geen spoor tekent, is geteld: zonder datum, vóór het
    begin, of zonder vastgestelde taal (`und` is een code, geen taal)."""
    tellingen = velden.lees_tellingen()
    assert len(tellingen["talen_in_index"]) == _talen_bij_release()
    assert set(tellingen["talen"]) == set(tellingen["talen_in_index"]) - {velden.ONBEPAALD}
    maanden = len(tellingen["maanden"])
    assert all(len(reeks) == maanden for reeks in tellingen["talen"].values())
    getekend = sum(sum(reeks) for reeks in tellingen["talen"].values())
    assert getekend == tellingen["checks_getekend"]
    assert getekend + tellingen["zonder_datum"] + tellingen["voor_begin"] + tellingen["zonder_taal"] \
        == tellingen["checks_in_index"]
    # De herkomst noemt de stand waaruit getekend is.
    assert f"{tellingen['checks_in_index']:,}".replace(",", ".") in HERKOMST
    assert tellingen["datum"] in HERKOMST


def test_the_corpus_caption_says_only_what_the_image_draws():
    """Het bijschrift noemt de jaren van de tellingen en geen aantal: de kop
    van de site telt de talen al, en het totaal aan checks loopt na de
    releasekaart door."""
    tellingen = velden.lees_tellingen()
    tekst = velden.bijschrift_corpus(tellingen)
    assert tellingen["maanden"][0][:4] in tekst and tellingen["maanden"][-1][:4] in tekst
    zonder_jaren = tekst.replace(tellingen["maanden"][0][:4], "").replace(tellingen["maanden"][-1][:4], "")
    assert not re.search(r"\d", zonder_jaren)
    assert "—" not in tekst and f'"{tekst}"' in HERKOMST


def test_the_share_image_is_a_1200_by_630_jpeg():
    with Image.open(velden.DELEN) as beeld:
        assert beeld.format == "JPEG"
        assert beeld.size == (1200, 630)


# --- de velden bewegen (PO 2026-10-28, DESIGN §4h) ------------------------------


def _beweging() -> tuple[float, float]:
    """Hoe ver de velden inzoomen en opzij schuiven, uit de gedeelde opmaak."""
    css = (velden.WORTEL / "doublecheck" / "demo" / "global.css").read_text(encoding="utf-8")   # de demo laat ze bewegen
    zoom = re.search(r"--veld-zoom:\s*([\d.]+);", css)
    drift = re.search(r"--veld-drift:\s*([\d.]+)%;", css)
    assert zoom and drift
    return float(zoom.group(1)), float(drift.group(1)) / 100


def _verschoven(zone: velden.Zone, zoom: float, t: float) -> velden.Zone:
    """Het stuk van het beeld dat in de zone staat als de laag met
    `scale(zoom) translateX(t)` om het midden getransformeerd is."""
    x0, y0, x1, y1 = zone.vak

    def x(v: float) -> float:
        return min(1.0, max(0.0, 0.5 + (v - 0.5) / zoom - t))

    def y(v: float) -> float:
        return min(1.0, max(0.0, 0.5 + (v - 0.5) / zoom))

    return velden.Zone(zone.naam, (x(x0), y(y0), x(x1), y(y1)), zone.minimum, zone.schaduw)


def test_a_drifting_field_never_shows_its_edge():
    zoom, drift = _beweging()
    assert 1 < zoom <= 1.06, "heel subtiel (PO)"
    assert 0 < drift * zoom <= (zoom - 1) / 2


@pytest.mark.parametrize("naam", sorted(velden.VELDEN))
def test_every_text_zone_keeps_its_contrast_while_the_field_drifts(naam):
    """In elke stand van de beweging haalt wit in elke tekstzone nog zijn
    contrast: gemeten op het gepubliceerde beeld, in beide uiterste standen
    en in het midden (DESIGN §4h)."""
    zoom, drift = _beweging()
    pixels = np.asarray(Image.open(velden.UIT / f"{naam}.webp").convert("RGB"))
    for zone in velden.VELDEN[naam].zones:
        for t in (-drift, 0.0, drift):
            gemeten = velden.contrast_wit(pixels, _verschoven(zone, zoom, t))
            assert gemeten >= zone.minimum, (naam, zone.naam, t, round(gemeten, 2))
