"""Uitgevers waarvan de eigen claims op elkaar lijken (PLAN.md #17.1).

Ontdekt via de vetosteekproef: Koreaans en Amhaars leverden 44% van alle
vetoblokkades uit 0,3% van het corpus (BENCHMARK.md §42c). De oorzaak zit niet
in de taal — die halen de onderscheidingsmaat ruim — maar bij de uitgever.

De juiste maat is de **staart, niet de mediaan**: clustering wordt gedreven door
paren bóven de drempel, en een uitgever kan een prima mediaan hebben terwijl
enkele procenten van zijn paren tegen elkaar aan liggen. Gemeten over 149
uitgevers is de mediaan 0,0000% en p90 0,08%; de uitschieters zitten honderden
malen daarboven (§43).

De maat vindt twee verschillende dingen, en dat onderscheid is inhoudelijk:
- **rommel**: ClaimReview-markup die geen factcheck is. Iedereen mag die markup
  publiceren en niemand controleert het;
- **sjabloon**: echte factchecks met een huisstijl die de embedding overheerst.
"""

import numpy as np
import pytest

from doublecheck.uitgeverkwaliteit import (
    GEWEERDE_UITGEVERS,
    zelfgelijkenis,
)


def test_a_templated_publisher_scores_far_above_a_varied_one():
    rng = np.random.default_rng(0)

    gevarieerd = rng.normal(size=(40, 32)).astype(np.float32)
    gevarieerd /= np.linalg.norm(gevarieerd, axis=1, keepdims=True)

    # Sjabloon: elke claim is dezelfde kern plus een beetje eigen inhoud.
    kern = rng.normal(size=32).astype(np.float32)
    sjabloon = kern + 0.2 * rng.normal(size=(40, 32)).astype(np.float32)
    sjabloon /= np.linalg.norm(sjabloon, axis=1, keepdims=True)

    assert zelfgelijkenis(gevarieerd, 0.93) == 0.0
    assert zelfgelijkenis(sjabloon, 0.93) > 0.5


def test_the_measure_looks_at_the_tail_not_the_middle():
    """Een uitgever mag een prima mediaan hebben en tóch clusteren.

    JTBC haalt mediaan 0,337 — verhoogd maar niet extreem — terwijl 2,4% van
    zijn paren boven de clusterdrempel ligt. De mediaan zag dat niet (§43a).
    """
    rng = np.random.default_rng(1)
    gewoon = rng.normal(size=(60, 32)).astype(np.float32)
    gewoon /= np.linalg.norm(gewoon, axis=1, keepdims=True)
    # Vijf bijna-identieke claims tussen 55 gewone.
    gewoon[:5] = gewoon[0] + 0.01 * rng.normal(size=(5, 32)).astype(np.float32)
    gewoon[:5] /= np.linalg.norm(gewoon[:5], axis=1, keepdims=True)

    assert 0.0 < zelfgelijkenis(gewoon, 0.93) < 0.02
    assert float(np.median(gewoon @ gewoon.T)) < 0.3


def test_too_few_claims_gives_no_verdict():
    rng = np.random.default_rng(2)
    weinig = rng.normal(size=(3, 32)).astype(np.float32)
    weinig /= np.linalg.norm(weinig, axis=1, keepdims=True)

    assert zelfgelijkenis(weinig, 0.93) is None


def test_the_junk_publishers_are_recorded_with_their_measurement():
    """De lijst is een meetuitkomst, geen mening — en herbaar met het commando."""
    assert "Stancu Print" in GEWEERDE_UITGEVERS
    assert "FactStream" in GEWEERDE_UITGEVERS


def test_the_publisher_measurement_uses_only_the_configured_model(tmp_path):
    """Na een modelwissel staan twee versies naast elkaar; de meting mag ze
    nooit door elkaar halen (#25.14c, DR6)."""
    import numpy as np

    from doublecheck.storage import connect, init_schema
    from doublecheck.uitgeverkwaliteit import vectoren_per_uitgever

    conn = connect(tmp_path / "u.db")
    init_schema(conn)
    for i in range(3):
        conn.execute("INSERT INTO claim (claim_id, canonical_text, language) VALUES (?, ?, 'nl')", (f"c{i}", f"t{i}"))
        conn.execute("INSERT INTO factcheck (claim_id, publisher, verdict_normalized, verdict_original, url,"
                     " review_date, language) VALUES (?, 'Redactie', 'onwaar', 'Onjuist', ?, '2024-01-01', 'nl')",
                     (f"c{i}", f"https://x.nl/{i}"))
        for versie, dim in (("oud", 4), ("nieuw", 8)):
            conn.execute("INSERT INTO fingerprint (claim_id, kind, model_version, payload) VALUES (?, 'text', ?, ?)",
                         (f"c{i}", versie, np.ones(dim, dtype=np.float32).tobytes()))
    conn.commit()
    per, taal_van = vectoren_per_uitgever(conn, "nieuw")
    assert set(per) == {"Redactie"} and taal_van == {"Redactie": "nl"}
    assert len(per["Redactie"]) == 3 and all(v.shape == (8,) for v in per["Redactie"])


def test_the_web_shop_network_is_banned_by_name():
    """#25.19: zes namen van hetzelfde netwerk (halfrain.com, coreyz.com) die
    licentieverkoop en klantrecensies als ClaimReview publiceren. Op naam,
    zoals de eerdere twee: de maat vond ze, een mens las de claims."""
    from doublecheck.uitgeverkwaliteit import is_geweerd

    for naam in ("HalfRain eStore LLC", "HalfRain eStore", "HRC", "HRC: Attribution project",
                 "GarbageFile ORG", "CoreYZ Network"):
        assert is_geweerd(naam), naam
    assert not is_geweerd("PolitiFact")


def test_a_claimant_in_the_feed_never_becomes_a_publisher_in_the_measurement(tmp_path):
    """#25.19 b: "Donald Trump" stond met 40 claims als uitgever in de meting;
    het waren checks van PolitiFact. De meting telt op de redactie van de host."""
    import numpy as np

    from doublecheck.storage import connect, init_schema
    from doublecheck.uitgeverkwaliteit import vectoren_per_uitgever

    conn = connect(tmp_path / "u.db")
    init_schema(conn)
    for i, uitgever in enumerate(("Donald Trump", "PolitiFact", "Bernie Sanders")):
        conn.execute("INSERT INTO claim (claim_id, canonical_text, language) VALUES (?, ?, 'en')", (f"c{i}", f"t{i}"))
        conn.execute("INSERT INTO factcheck (claim_id, publisher, verdict_normalized, verdict_original, url,"
                     " review_date, language) VALUES (?, ?, 'onwaar', 'False', ?, '2024-01-01', 'en')",
                     (f"c{i}", uitgever, f"https://www.politifact.com/factchecks/{i}/"))
        conn.execute("INSERT INTO fingerprint (claim_id, kind, model_version, payload) VALUES (?, 'text', 'm', ?)",
                     (f"c{i}", np.ones(4, dtype=np.float32).tobytes()))
    conn.commit()
    per, _ = vectoren_per_uitgever(conn, "m", register={"politifact.com": "PolitiFact"})
    assert set(per) == {"PolitiFact"} and len(per["PolitiFact"]) == 3


def test_the_register_never_names_a_banned_host():
    """Het register leidde "Someone" af als redactie van factstream.co: de
    meest gebruikte naam op een host vol proefinvoer."""
    from doublecheck.uitgevers import load_hosts
    from doublecheck.uitgeverkwaliteit import is_geweerde_host

    assert not [h for h in load_hosts() if is_geweerde_host(f"https://{h}/")]


def test_shop_reviews_from_tripatourium_are_refused_under_every_name():
    """De stiltetoets vond een webwinkelrecensie als `matched` (BENCHMARK
    §95): de recensies van tripatourium.com staan in de feed onder "Etsy",
    "etsy" en "eBay". Op host weren, zoals factstream.co (#25.19 b)."""
    from doublecheck.uitgeverkwaliteit import is_geweerde_host

    for url in ("https://tripatourium.com/Cart", "https://tripatourium.com/blotterart/Ganesh"):
        assert is_geweerde_host(url), url


def test_shops_and_blogs_that_dress_up_as_fact_checks_are_refused():
    """Het nalopen na de stiltetoets (PO 2026-10-13: "haal ze er allemaal
    uit"): recensies, biografieën, eigen nieuws en blogbeweringen als
    ClaimReview, ook onder een andere spelling van de naam."""
    from doublecheck.uitgeverkwaliteit import is_geweerde_host

    for url in ("https://modelpeeps.com/jorden-van-foreest-net-worth", "https://www.emporiumdigital.online/x",
                "https://osochicragdolls.co.uk/", "https://www.dufranewatches.com/",
                "https://blog.nutricionyfarmacia.com/", "https://centresukha.com/x", "https://vegnsocial.com/vegan-facts",
                "https://pro100blogger.com/2019/07/x", "https://www.songkhlatoday.com/content/26410/",
                "https://www.tratonline.info/archives/6640"):
        assert is_geweerde_host(url), url


def test_a_casino_roofers_shops_personal_sites_and_a_test_site_are_refused():
    """Gevonden bij de trekkers van #25.26 (BENCHMARK §99; PO 2026-10-13):
    recensies van een casino-app, dakdekkers en winkels, persoonlijke sites,
    een blog dat zich "Pubmed" noemt, een stichting die de eigen artikelen
    "scientifically sound" noemt, en een proefsite met "This is the claim"."""
    from doublecheck.uitgeverkwaliteit import is_geweerde_host

    for url in ("https://app-live567.com/", "https://www.americanroofingsolutions.org/",
                "https://roofingrepairsmanchester.co.uk/", "https://www.metal2000.fr/rideaux-et-grilles/x",
                "https://dienmayminhphuong.com/dieu-hoa-casper-lc-24tl32-24000-btu/", "https://www.giatotqua.vn/",
                "http://shizenhouse.com/", "https://davidbsantos.com/", "http://www.worldchatlink.com/",
                "https://imstilljosh.com/undetectable_equals_untransmittable/", "https://samszo.univ-paris8.fr/",
                "https://biozdrowy.pl/blog/witamina-k", "https://fatherhoodchannel.com/2024/08/25/x",
                "http://fct.sens3.com/hurray"):
        assert is_geweerde_host(url), url


def test_banning_a_university_subdomain_leaves_the_university():
    """samszo.univ-paris8.fr is één persoonlijke server; de universiteit
    zelf en haar andere subdomeinen blijven toegestaan."""
    from doublecheck.uitgeverkwaliteit import is_geweerde_host

    assert not is_geweerde_host("https://www.univ-paris8.fr/actualites")
    assert not is_geweerde_host("https://ufr-culture.univ-paris8.fr/")
