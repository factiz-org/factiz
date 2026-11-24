"""De kleur bij het oordeel van een redactie (PLAN #34.2l, DESIGNSYSTEEM §4): elke soort uit `i18n.LABELS` heeft een
kleur, altijd met het woord en een stip, licht en donker, met tekst van minstens 4,5:1 op haar vlak en een stip van
minstens 3:1 op het paneel (WCAG 1.4.3 en 1.4.11). En één kaart voor een factcheck in elke lijst van de site."""

import re
from pathlib import Path

import pytest

from factiz_site import i18n

SITE = Path(__file__).resolve().parent.parent / "site" / "src"
CSS = (SITE / "styles" / "site.css").read_text(encoding="utf-8")


def _blok(begin: str) -> str:
    """De tekst van het eerste blok na `begin`, tot de bijbehorende sluitaccolade."""
    i = CSS.index(begin)
    j = CSS.index("{", i) + 1
    diepte = 1
    while diepte:
        diepte += {"{": 1, "}": -1}.get(CSS[j], 0)
        j += 1
    return CSS[i:j]


BLOKKEN = {"licht": _blok(".fz {"), "donker-apparaat": _blok("@media (prefers-color-scheme: dark)"),
           "donker-gekozen": _blok(':root[data-weergave="donker"] .fz')}
PANEEL = {k: re.search(r"--paneel:\s*(#[0-9a-f]{6})", v).group(1) for k, v in BLOKKEN.items()}


def _familie(soort: str) -> str:
    regel = re.search(r'[^{}]*\[data-soort="' + re.escape(soort) + r'"\][^{}]*\{([^}]*)\}', CSS)
    assert regel, f"geen kleur voor {soort}"
    return re.search(r"--l-inkt:\s*var\(--([a-z-]+)-inkt\)", regel.group(1)).group(1)


def _lum(hexkleur: str) -> float:
    c = [int(hexkleur[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    c = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


def _contrast(a: str, b: str) -> float:
    la, lb = sorted((_lum(a), _lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


@pytest.mark.parametrize("soort", i18n.LABELS)
@pytest.mark.parametrize("weergave", BLOKKEN)
def test_every_verdict_kind_has_a_readable_colour_in_light_and_dark(soort, weergave):
    fam = _familie(soort)
    blok = BLOKKEN[weergave]
    kleur = {deel: re.search(rf"--{fam}-{deel}:\s*(#[0-9a-f]{{6}})", blok) for deel in ("inkt", "vlak", "rand", "stip")}
    assert all(kleur.values()), (soort, weergave, fam)
    kleur = {k: v.group(1) for k, v in kleur.items()}
    assert _contrast(kleur["inkt"], kleur["vlak"]) >= 4.5, (soort, weergave)
    assert _contrast(kleur["stip"], PANEEL[weergave]) >= 3, (soort, weergave)


def test_a_verdict_never_has_its_colour_without_its_word_and_dot():
    """D5: kleur is nooit de enige drager. Het label kleurt alleen met `data-soort` en houdt zijn tekst; de stip staat
    ervoor, ook in het filter."""
    assert re.search(r"\.fz \.label\[data-soort\]::before\s*\{[^}]*background:\s*var\(--l-stip", CSS)
    rij = (SITE / "components" / "site" / "Rij.jsx").read_text(encoding="utf-8")
    assert 'data-soort={r.soort' in rij and "{r.label}" in rij
    bieb = (SITE / "components" / "site" / "Bibliotheek.jsx").read_text(encoding="utf-8")
    assert "stip" in bieb and "data-soort" in bieb


def test_the_answer_puts_the_newsrooms_verdict_up_front_in_its_own_colour():
    """PO 2026-11-15: "Onze conclusie hebben wij wel heel subtiel vormgegeven". Onder Klopt dit? eerst één vlak in de kleur
    van het oordeel: het woord groot met de stip, dan wie checkte en wanneer, en bij één check de eigen woorden van de
    redactie (en hun vertaling) in dat vlak. De taal van de check staat naast de knop naar hun factcheck, niet achter hun
    woorden, waar ze leek te zeggen in welke taal die woorden zijn. Zonder soort is het vlak neutraal (DR2, D5). Sinds
    PO 2026-11-19 is het woord een stempel met erachter wie het zegt ("onwaar volgens")."""
    pagina = (SITE / "components" / "site" / "paginas" / "Factcheck.astro").read_text(encoding="utf-8")
    begin = pagina.index('aria-labelledby="antwoord"')
    blok = pagina[begin:pagina.index("{/* einde antwoord */}", begin)]
    assert "<div class=\"uitspraak\" data-soort={p.label_klasse || 'geen'}>" in blok
    vlak = blok[blok.index('class="uitspraak"'):blok.index("</div>", blok.index('class="uitspraak"'))]
    # sinds 2026-11-19 het oordeel als stempel met wie het zegt (PLAN #34.2cc, DESIGN §4y), nog steeds voor de zin
    assert vlak.index('<p class="uitspraak-label fz-stempelgroep">') < vlak.index("{p.kop.antwoord.zin}")
    assert "{p.stempel}" in vlak and "{p.volgens}" in vlak
    assert "{p.checks[0].oordeel}" in vlak and "{p.checks[0].glos}" in vlak and "enkel &&" in vlak
    assert blok.index("</div>", blok.index('class="uitspraak"')) < blok.index('id="bronnen"')
    assert "label-groot" not in blok and '<span class="mono ml-2">{k.taal}</span>' not in pagina
    assert '{enkel ? <p class="mono ms-auto">{k.taal}</p>' in blok
    uitspraak = _blok(".fz .uitspraak {")
    assert "var(--l-vlak, " in uitspraak and "var(--l-rand, " in uitspraak and "var(--l-inkt, " in uitspraak
    label = _blok(".fz .uitspraak-label {")
    assert float(re.search(r"font-size: clamp\(([\d.]+)rem", label).group(1)) >= 1.4 and "font-weight: 600" in label
    assert re.search(r"\.fz \.uitspraak-label::before\s*\{[^}]*background:\s*var\(--l-stip", CSS)


def test_on_a_phone_the_answer_starts_in_the_first_screen():
    """PLAN #34.2ay (PO 2026-11-15: "We verliezen ook wel hier veel screen real estate aan de bovenkant tot we bij de check
    komen"): op een telefoon geen kruimelpad (het thema staat al in het vlak, Terug naar resultaten blijft), het thema en
    de kenmerken op één regel, een iets kleinere kop, en het origineel onder het antwoord. Gemeten op 375 bij 812: de kop
    van 400 naar 203 punten, het antwoord van 654 naar 460, met de knop binnen het scherm."""
    pagina = (SITE / "components" / "site" / "paginas" / "Factcheck.astro").read_text(encoding="utf-8")
    # het kruimelpad is één onderdeel (`Kruimel.astro`); op deze pagina niet op een telefoon
    assert "<Kruimel taal={taal} telefoon={false}" in pagina
    onderdeel = (SITE / "components" / "site" / "Kruimel.astro").read_text(encoding="utf-8")
    assert "'max-md:hidden': !telefoon" in onderdeel
    terug = re.search(r'<a id="terug" class="([^"]*)"', pagina)
    assert terug and "hidden" not in terug.group(1)
    rij = pagina[pagina.index('<div class="flex flex-wrap items-center gap-x-3 gap-y-2">'):]
    rij = rij[:rij.index("</div>")]
    assert 'class="thema"' in rij and "kenmerk-knop" in rij
    assert pagina.count("text-[clamp(1.375rem,3vw,2.1rem)]") == 2
    origineel = re.search(r'<p (?:data-nosnippet )?class="([^"]*)">\{p\.vertaling\.regel\}', pagina)
    assert origineel and "max-md:order-last" in origineel.group(1)
    # in de broncode blijft het origineel direct onder de kop: breed en voor een schermlezer verandert de volgorde niet
    assert pagina.index("{p.vertaling.regel}") < pagina.index('aria-labelledby="antwoord"')


def test_every_list_of_fact_checks_on_the_site_uses_the_one_card():
    """DESIGNSYSTEEM §4: op de start, in de lijst en bij *Komt ook voor als* dezelfde kaart, uit één onderdeel."""
    for pad in (SITE / "components" / "site").rglob("*"):
        if pad.suffix in (".astro", ".jsx") and pad.name != "Rij.jsx":
            tekst = pad.read_text(encoding="utf-8")
            assert 'class="rij"' not in tekst and 'className="rij"' not in tekst, pad.name


def test_the_fact_check_page_shows_the_answer_and_gives_search_engines_the_title_description_and_data():
    """PLAN #34.2m: de site toont wat het platform uitrekent (`kop`), zonder eigen tekst te verzinnen."""
    pagina = (SITE / "components" / "site" / "paginas" / "Factcheck.astro").read_text(encoding="utf-8")
    assert "titel={p.kop.titel}" in pagina and "omschrijving={p.kop.omschrijving}" in pagina
    assert 'type="application/ld+json"' in pagina and "set:html={p.kop.ld}" in pagina
    assert "{p.kop.antwoord.kop}" in pagina and "{p.kop.antwoord.zin}" in pagina


def test_beside_the_contents_stand_the_context_cards_and_the_field_of_a_dossier_stays_under_connections():
    """PLAN #34.2n, sinds #34.2an (SPECS E9.S21): in de zijkolom de inhoud en de contextkaarten uit het platform, het dossier
    als eerste kaart met zijn jaren; het veld van het dossier staat alleen nog onder *Verbanden*, leeg, met de naam
    ernaast. De inhoud alleen op een breed scherm; de kaarten op een telefoon onder het artikel."""
    pagina = (SITE / "components" / "site" / "paginas" / "Factcheck.astro").read_text(encoding="utf-8")
    kolom = pagina[pagina.index("<aside"):pagina.index("</aside>")]
    assert "<ContextKaarten kaarten={p.context} />" in kolom and "kaartveld" not in kolom and "max-lg:hidden" in kolom
    assert '<aside class="max-lg:hidden"' not in pagina
    assert pagina.count("p.dossiers.map(") == 1             # onder Verbanden
    veld = re.search(r'<span class=\{`kaartveld[^`]*`\}[^>]*></span>', pagina)
    assert veld and 'aria-hidden="true"' in veld.group(0)    # het veld is leeg: de naam staat ernaast, nooit erop


def test_the_fact_check_page_says_how_many_similar_fact_checks_exist_and_translates_a_newsrooms_words():
    """PLAN #34.2o en #34.2p: in het blok Klopt dit? de telling van Lijkt op met per oordeel een stip en een link naar de
    kaarten; onder de woorden van een redactie in een andere taal de machinevertaling."""
    pagina = (SITE / "components" / "site" / "paginas" / "Factcheck.astro").read_text(encoding="utf-8")
    blok = pagina[pagina.index('aria-labelledby="antwoord"'):pagina.index("</section>", pagina.index('aria-labelledby="antwoord"'))]
    assert 'href="#lijkt-op"' in blok and "{p.lijkt_op.telling}" in blok and 'class="stip" data-soort={s.soort}' in blok
    assert 'id="lijkt-op"' in pagina and "p.lijkt_op.rijen.map((r) => <Rij r={r} />)" in pagina
    assert "['lijkt-op', t('lijkt_op_kop')]" in pagina
    assert "{k.glos_regel}" in pagina and "{k.glos}" in pagina


def test_the_checks_sit_in_the_answer_card_and_one_check_shows_no_second_name_date_or_button():
    """PLAN #34.2q: één kaart Klopt dit? met de checks erin; bij één check alleen hun woorden en de ene primaire knop,
    bij meer een regel per check met de eerste knop primair; geen losse kaart Wie het checkte."""
    pagina = (SITE / "components" / "site" / "paginas" / "Factcheck.astro").read_text(encoding="utf-8")
    begin = pagina.index('aria-labelledby="antwoord"')
    blok = pagina[begin:pagina.index("{/* einde antwoord */}", begin)]
    assert "p.checks.map(" in blok and "{k.oordeel}" in blok and "{k.glos}" in blok    # de checks in de kaart
    assert pagina.count("p.checks.map(") == 1                                           # en nergens anders
    assert pagina.count("knop-primair") == 1                                            # één primaire knop
    assert "enkel" in blok and "t('lees_bij', { redactie: k.redactie })" in blok        # bij één check de grote knop
    assert 'id="bronnen"' in blok                                                        # de inhoud springt hierheen
    assert "p.checks.length > 1 && ['bronnen', t('bronnen_kop')]" in pagina             # en noemt het alleen bij meer
    assert '<section id="bronnen"' not in pagina


def test_a_card_names_the_country_the_claim_is_about_right_after_its_theme(tmp_path_factory):
    """PLAN #34.2w: het land uit de themaronde staat op de kaart direct na het thema, in de taal van de site; een rij
    zonder land zegt niets."""
    from tests.test_factiz_dossiers import _site
    client, nr = _site(tmp_path_factory)
    rijen = {r["nummer"]: r for r in client.get("/api/nl/archief").json()["rijen"]}
    assert rijen[nr["villa"]]["land"] == {"code": "UA", "naam": "Oekraïne"}
    assert rijen[nr["villa"]]["thema"]["sleutel"] == "war"
    assert rijen[nr["los"]]["land"] is None                                       # de knoflook heeft geen land
    assert client.get("/api/en/archief").json()["rijen"][0].keys() >= {"land"}
    rij = (SITE / "components" / "site" / "Rij.jsx").read_text(encoding="utf-8")
    voet = rij[rij.index("const voet = ["):rij.index("].filter(Boolean);")]
    assert voet.index("r.thema &&") < voet.index("r.land &&") < voet.index("r.redacties &&")


def test_the_groups_under_connections_stand_further_apart_than_the_cards_in_them():
    """PO 2026-11-15: "hier iets meer padding", tussen *Meer over …* en *Meer in …* onder Verbanden."""
    pagina = (SITE / "components" / "site" / "paginas" / "Factcheck.astro").read_text(encoding="utf-8")
    verbanden = pagina[pagina.index('<section id="verbanden"'):pagina.index("</section>", pagina.index('<section id="verbanden"'))]
    assert verbanden.count('class="verband-groep grid gap-2.5"') == 2
    regel = re.search(r"\.fz \.verband-groep:not\(:first-child\) \{ margin-top: ([\d.]+)rem; \}", CSS)
    assert regel and float(regel.group(1)) >= 1.5


def test_a_fact_check_appears_only_once_under_connections():
    """PO 2026-11-15: "Eerst de dubbele". Een factcheck die bij de naam en bij het thema hoort, stond in beide groepen; de
    themagroep slaat nu over wat de naamgroep al toont en vult aan met de volgende."""
    pagina = (SITE / "components" / "site" / "paginas" / "Factcheck.astro").read_text(encoding="utf-8")
    assert "const themaRijen = anders(inThema, new Set(naamRijen.map((r) => r.nummer)));" in pagina
    verbanden = pagina[pagina.index('<section id="verbanden"'):pagina.index("</section>", pagina.index('<section id="verbanden"'))]
    assert "anders(" not in verbanden and "naamRijen.map((r) => <Rij r={r} />)" in verbanden
    assert "themaRijen.map((r) => <Rij r={r} />)" in verbanden


def test_the_fact_check_page_names_who_else_checked_the_same_claim_and_lists_their_checks():
    """PLAN #34.2bp, SPECS E9.S31 AC4: in het blok Klopt dit? één regel met de namen die naar Ook gecheckt door wijst; daar
    per check de redactie, haar eigen woorden, de datum en de taal, de bewering van die pagina met een link en de link naar
    het artikel. Geen primaire knop en geen kaart van een lijst: het is een verwijzing, het oordeel blijft van deze pagina."""
    pagina = (SITE / "components" / "site" / "paginas" / "Factcheck.astro").read_text(encoding="utf-8")
    blok = pagina[pagina.index('aria-labelledby="antwoord"'):pagina.index("</section>", pagina.index('aria-labelledby="antwoord"'))]
    assert 'href="#ook-gecheckt"' in blok and "{p.ook_gecheckt.regel}" in blok
    begin = pagina.index('<section id="ook-gecheckt"')
    sectie = pagina[begin:pagina.index("</section>", begin)]
    for stuk in ("{k.redactie}", "{k.oordeel}", "{k.datum}", "{k.taal}", "href={k.bewering.href}", "{k.bewering.tekst}",
                 "href={k.url}", "{p.ook_gecheckt.telling}"):
        assert stuk in sectie, stuk
    assert "knop-primair" not in sectie and "<Rij" not in sectie
    assert "ook_gecheckt_uitleg" not in pagina        # geen uitleg van hoe het werkt (PO 2026-11-22: "Is onnodig.")
    assert begin < pagina.index('<section id="lijkt-op"')                     # dezelfde bewering vóór hetzelfde verhaal
    assert "['ook-gecheckt', t('ook_gecheckt_kop')]" in pagina


def test_the_answer_shows_what_all_newsrooms_say_as_stamps_never_an_own_verdict():
    """PLAN #34.2cd (PO 2026-11-22: "Ja graag", en "1"): onder het antwoord de stempel en naam van elke redactie, elk een
    eigen link naar haar check eronder, op deze pagina of onder Ook gecheckt door."""
    pagina = (SITE / "components" / "site" / "paginas" / "Factcheck.astro").read_text(encoding="utf-8")
    assert "{p.eens && (" in pagina and 'class="fz-stempel" data-soort={r.soort}' in pagina and "{r.naam}" in pagina
    assert '<a class="fz-eens-soort" href={`#${r.anker}`}>' in pagina and "{!p.eens && p.ook_gecheckt &&" in pagina
    # zonder zichtbare kop, onder elkaar (PO 2026-11-22: "Dit kan weg. Dan komen ze netjes onder elkaar."); de kop alleen
    # voor een schermlezer
    assert '<ul class="fz-eens" aria-label={p.eens.tekst}>' in pagina and "{p.eens.tekst}</span>" not in pagina
    assert 'id={`check-${i}`}' in pagina and 'id={`ook-${i}`}' in pagina


def test_with_one_check_the_language_sits_against_the_button_also_for_an_archived_copy():
    """PO 2026-11-22: "De taal hoort tegen de knop aan te staan, maar ik zie hem ook een paar keer ineens in het midden
    opduiken." Bij één check duwt de taal (`ms-auto`) de knop naar rechts; een knop met een eigen `ms-auto` deelt de ruimte
    en zet de taal in het midden. Dat gold voor de knop naar het archief."""
    pagina = (SITE / "components" / "site" / "paginas" / "Factcheck.astro").read_text(encoding="utf-8")
    eigen = pagina[pagina.index('<ol id="bronnen"'):pagina.index("</ol>", pagina.index('<ol id="bronnen"'))]
    assert '<p class="mono ms-auto">{k.taal}</p>' in eigen
    for knop in re.findall(r"<a class=(\{`[^`]*`\}|\"[^\"]*\")", eigen):
        assert "ms-auto" not in knop or "enkel ? '' : 'ms-auto'" in knop, knop
