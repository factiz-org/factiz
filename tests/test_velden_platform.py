"""De velden van het platform (PLAN.md #33.6d, SPECS E9.S13, DESIGN §4w en D11).

De site draagt de look van factiz.org en zijn velden: bovenaan elke pagina, als kaart bij thema's en dossiers, en in de
voet. Elk thema en elk dossier heeft een eigen veld uit hetzelfde script. Deze tests houden de beelden eerlijk
(herkomst, opnieuw te tekenen, geen rood, licht genoeg om te laden) en leesbaar (wit haalt zijn contrast in elke
tekstzone, ook als het veld schuift). Waar de site de velden zet, bewaken de tests van de site (`tests/test_site_*.py`).
"""

import io
import json
import re

import numpy as np
import pytest
from PIL import Image

from doublecheck import velden
from tests.test_velden import _verschoven

HERKOMST = (velden.PLATFORM_UIT / "HERKOMST.md").read_text(encoding="utf-8")
# de velden van het platform en de drie gedeelde; de andere basisvelden staan in dezelfde map (test_velden)
BEELDEN = sorted(p for p in velden.PLATFORM_UIT.glob("*.webp") if p.stem not in set(velden.VELDEN) - set(velden.GEDEELD))
PLATFORM = velden.platform_velden()
# de opmaak van de site (B76); de eigen opmaak van het platform is weg sinds #34.2f, stap 4
OPMAAK = (velden.WORTEL / "site" / "src" / "styles" / "site.css").read_text(encoding="utf-8")


def _pixels(pad) -> np.ndarray:
    with Image.open(pad) as beeld:
        return np.asarray(beeld.convert("RGB"))


def test_every_theme_and_every_dossier_has_its_own_band_and_card():
    themas = [t["sleutel"] for t in json.loads(velden.THEMAS.read_text(encoding="utf-8"))["themas"]]
    dossiers = [p.name for p in velden.DOSSIERS.iterdir() if (p / "dossier.toml").exists()]
    assert set(velden.THEMA_VELDEN) == set(themas), "elk thema een familie en een seed"
    for soort, sleutels in (("thema", themas), ("dossier", dossiers)):
        for sleutel in sleutels:
            for vorm in ("band", "kaart"):
                assert f"{soort}-{sleutel}-{vorm}" in PLATFORM, (soort, sleutel, vorm)
    # elk thema een eigen seed: twee thema's in dezelfde familie lijken op elkaar, maar zijn niet hetzelfde beeld
    assert len({seed for _, seed in velden.THEMA_VELDEN.values()}) == len(velden.THEMA_VELDEN)
    assert {velden.dossier_seed(d) for d in dossiers}.isdisjoint({s for _, s in velden.THEMA_VELDEN.values()})


def test_every_image_of_the_platform_is_a_field_with_its_provenance():
    assert {p.stem for p in BEELDEN} == set(velden.GEDEELD) | set(PLATFORM) | set(velden.kleine_velden(PLATFORM))
    assert f"script {velden.VERSIE}" in HERKOMST
    for naam, (familie, veld) in PLATFORM.items():
        regel = re.search(rf"^- `{naam}\.webp`: (.*)$", HERKOMST, flags=re.M)
        assert regel, f"{naam}.webp ontbreekt in HERKOMST.md"
        assert f"familie {familie}, seed {veld.seed}, {veld.breedte}×{veld.hoogte}" in regel.group(1), naam


def test_the_shared_fields_are_the_base_fields_themselves():
    """Eén map voor de site en het platform (PLAN #34.2f): corpus, nacht en groen zijn de basisvelden zelf, geen kopie."""
    for naam in velden.GEDEELD:
        assert (velden.PLATFORM_UIT / f"{naam}.webp") == (velden.UIT / f"{naam}.webp"), naam   # hetzelfde bestand
        assert re.search(rf"^- `{naam}\.webp`: het basisveld \(seed ", HERKOMST, flags=re.M)


def test_the_field_stylesheet_is_what_the_script_writes_and_points_only_at_images_that_exist():
    css = velden.PLATFORM_CSS.read_text(encoding="utf-8")
    assert css == velden.platform_css(list(PLATFORM)), "draai `python -m doublecheck.velden platform`"
    adressen = re.findall(r"url\(([^)]+)\)", css)
    assert len(adressen) == len(velden.GEDEELD) + len(PLATFORM) + len(velden.kleine_velden(PLATFORM))
    for adres in adressen:
        assert adres.startswith("/static/beeld/") and (velden.PLATFORM_UIT / adres.rsplit("/", 1)[1]).exists(), adres
    # een dossier staat na de thema's: met beide klassen wint zijn eigen beeld, en anders dat van zijn thema
    assert css.index(".veld-band-dossier-") > css.rindex(".veld-band-thema-")


@pytest.mark.parametrize("naam", [velden.GEDEELD[0], *sorted(PLATFORM)[:1], *sorted(PLATFORM)[-1:]])
def test_the_script_redraws_a_sample_of_the_fields_from_their_seed(naam):
    """Hetzelfde commando geeft hetzelfde beeld. Een steekproef: elk veld van het platform kost ~2,5 seconden, en een
    wijziging in het script raakt ze allemaal; een andere seed vangt de herkomsttest."""
    nieuw = np.asarray(Image.open(io.BytesIO(velden.webp(velden.teken(naam)))).convert("RGB"))
    oud = _pixels(velden.PLATFORM_UIT / f"{naam}.webp")
    assert nieuw.shape == oud.shape
    assert np.abs(nieuw.astype(int) - oud.astype(int)).mean() <= 1.0, naam


def test_the_small_theme_bands_for_the_cards_are_the_bands_scaled_down_and_light():
    """PLAN #34.2bq: een kaart op de start en het overzicht krijgt de band verkleind tot 800×240, uit hetzelfde script."""
    klein = velden.kleine_velden(PLATFORM)
    assert len(klein) == len(velden.THEMA_VELDEN)
    for naam, band in klein.items():
        pad = velden.PLATFORM_UIT / f"{naam}.webp"
        assert re.search(rf"^- `{naam}\.webp`: verkleind uit `{band}\.webp` tot 800×240", HERKOMST, flags=re.M), naam
        assert _pixels(pad).shape == (240, 800, 3) and pad.stat().st_size <= 30 * 1024, (naam, pad.stat().st_size)
        opnieuw = np.asarray(Image.open(io.BytesIO(velden.klein_webp(velden.PLATFORM_UIT / f"{band}.webp"))).convert("RGB"))
        assert np.abs(opnieuw.astype(int) - _pixels(pad).astype(int)).mean() <= 1.0, naam


def test_no_image_of_the_platform_weighs_more_than_200_kb():
    for pad in BEELDEN:
        assert pad.stat().st_size <= 200 * 1024, (pad.name, pad.stat().st_size // 1024)


@pytest.mark.parametrize("naam", sorted(PLATFORM))
def test_white_text_stays_readable_in_every_text_zone_also_while_the_field_drifts(naam):
    """§4h: na de sluier van de pagina haalt wit in elke tekstzone 3:1 voor koppen en 4,5:1 voor de rest, tegen de
    lichtste 5% van de pixels, in beide uiterste standen van de beweging en in het midden."""
    # de beweging uit de opmaak van de site; beweegt het veld daar niet, dan in rust (zoom 1, geen verschuiving)
    zoom_m, drift_m = re.search(r"--veld-zoom:\s*([\d.]+);", OPMAAK), re.search(r"--veld-drift:\s*([\d.]+)%;", OPMAAK)
    zoom = float(zoom_m.group(1)) if zoom_m else 1.0
    drift = float(drift_m.group(1)) / 100 if drift_m else 0.0
    pixels = _pixels(velden.PLATFORM_UIT / f"{naam}.webp")
    for zone in PLATFORM[naam][1].zones:
        for t in (-drift, 0.0, drift):
            gemeten = velden.contrast_wit(pixels, _verschoven(zone, zoom, t))
            assert gemeten >= zone.minimum, (naam, zone.naam, t, round(gemeten, 2))


def test_the_band_lays_the_veil_the_zones_were_measured_with():
    """De sluier over het veld van een band en een kaart (`.kaartveld` in site.css) is onderaan, waar de kop staat,
    minstens zo dicht als de schaduw waarmee het script de tekstzones van een band mat; anders zegt de contrastmeting
    niets."""
    sluier = re.search(r"\.kaartveld::before \{[^}]*linear-gradient\(180deg, rgb\(12 13 16 / ([\d.]+)\), "
                       r"rgb\(12 13 16 / ([\d.]+)\)\)", OPMAAK)
    assert sluier and float(sluier.group(2)) >= max(z.schaduw for z in velden._BAND)


def test_the_start_lays_a_veil_nowhere_lighter_than_the_one_its_field_was_measured_with():
    """De start (`.held` in site.css) legt een sluier over *corpus* die van boven naar beneden verloopt. Waar de kop en de
    regel onder het zoekveld staan, mag hij nergens lichter zijn dan de schaduw waarmee de tekstzones van corpus gemeten
    zijn; halverwege was hij 0,05 tegen een gemeten 0,2 (PLAN #34.2f stap 4, hersteld in #34.2v)."""
    regel = re.search(r"\.held::before \{[^}]*linear-gradient\(180deg,([^;]*)\);", OPMAAK)
    assert regel, "de sluier van de start staat niet meer in site.css"
    dekkingen = [float(d) for d in re.findall(r"rgb\(\d+ \d+ \d+ / ([\d.]+)\)", regel.group(1))]
    assert len(dekkingen) >= 2 and min(dekkingen) >= max(z.schaduw for z in velden.VELDEN["corpus"].zones), dekkingen


@pytest.mark.parametrize("pad", BEELDEN, ids=lambda p: p.name)
def test_no_field_of_the_platform_carries_alarm_red(pad):
    rgb = _pixels(pad).astype(float) / 255
    hoog, laag = rgb.max(axis=2), rgb.min(axis=2)
    verzadiging = np.where(hoog > 0, (hoog - laag) / np.maximum(hoog, 1e-6), 0)
    rood = (rgb[..., 0] == hoog) & (rgb[..., 1] - rgb[..., 2] < (hoog - laag) * 0.25)
    assert (rood & (verzadiging > 0.5) & (hoog > 0.35)).mean() < 0.001, pad.name
