"""De beschermingsgrenzen staan vast en verjaren niet (PLAN.md #20.3).

Na 20.1 en 20.2 staan de grenzen verspreid: pixels en bytes in de code, de
OCR-timeout en de rate-limit in config. Dat is precies de vorm die dit project
overal bestrijdt — een grens die stil verdwijnt zonder dat iets het merkt. Deze
guard breekt zodra iemand er een weghaalt of op nul zet, en `BENCHMARK.md §55`
somt ze op één plek op voor een securityreview.
"""

from doublecheck.api import MAX_IMAGE_BYTES, MAX_TEXT_LENGTH
from doublecheck.config import load_config
from doublecheck.image_fingerprint import MAX_IMAGE_PIXELS


def test_the_input_size_limits_are_present_and_sane():
    # Pixels: dekt een 4K-schermafbeelding (8,3 MP), snijdt de bom af (§54).
    assert 0 < MAX_IMAGE_PIXELS <= 50_000_000
    assert 0 < MAX_IMAGE_BYTES <= 64 * 1024 * 1024
    assert 0 < MAX_TEXT_LENGTH <= 1_000_000


def test_the_ocr_timeout_is_configured_and_positive():
    assert load_config().ocr.timeout_seconds > 0


def test_rate_limiting_is_configured_even_if_a_deployment_disables_it():
    rl = load_config().ratelimit
    assert rl.requests_per_minute > 0 and rl.burst > 0
    assert isinstance(rl.enabled, bool)
