# Het lettertype van het deelplaatje (PLAN #34.2aq, SPECS E9.S23 AC4)

Geist, het lettertype van de site, versie 5.3.0 van `@fontsource-variable/geist` (de site laadt hetzelfde pakket), van
The Geist Project Authors (https://github.com/vercel/geist-font), onder de SIL Open Font License 1.1 (`OFL.txt`). Hier
alleen de rechte variant met de as voor de dikte, in vijf delen per schrift: Latijn, Latijn uitgebreid, Cyrillisch,
Cyrillisch uitgebreid en Vietnamees. `geist.css` is het stijlblad van het pakket; het platform leest er alleen de
`unicode-range` per deel uit, om per stukje tekst het bestand te kiezen dat het schrift dekt.

Gekopieerd uit `site/node_modules/@fontsource-variable/geist/` zonder wijziging; `tests/test_factiz_deelbeeld.py` eist
dezelfde bytes zolang het pakket er staat.

## Noto Sans per schrift (PLAN #34.2as, SPECS E9.S28)

Achter Geist, voor elk schrift dat Geist niet kent, Noto Sans van The Noto Project Authors (https://notofonts.github.io),
onder de SIL Open Font License 1.1 (`noto/<pakket>/LICENSE`). Dezelfde pakketten als de site laadt, op een vaste versie:
`@fontsource-variable/noto-sans`, `@fontsource-variable/noto-sans-arabic`, `@fontsource-variable/noto-sans-hebrew`,
`@fontsource-variable/noto-sans-devanagari`, `@fontsource-variable/noto-sans-bengali`, `@fontsource-variable/noto-sans-tamil`,
`@fontsource-variable/noto-sans-telugu`, `@fontsource-variable/noto-sans-malayalam`, `@fontsource-variable/noto-sans-kannada`,
`@fontsource-variable/noto-sans-gujarati`, `@fontsource-variable/noto-sans-gurmukhi`, `@fontsource-variable/noto-sans-sinhala`,
`@fontsource-variable/noto-sans-thai`, `@fontsource-variable/noto-sans-khmer` en `@fontsource-variable/noto-sans-ethiopic`
(5.3.0), en `@fontsource-variable/noto-sans-sc`, `@fontsource-variable/noto-sans-tc`, `@fontsource-variable/noto-sans-jp` en
`@fontsource-variable/noto-sans-kr` (5.3.1). Per pakket het stijlblad `index.css` (het platform leest er alleen de
`unicode-range` per bestand uit) en de bestanden die het noemt, ongewijzigd gekopieerd met
`python -m factiz_site.lettertypen`; `tests/test_factiz_deelbeeld.py` eist dezelfde bytes zolang het pakket er staat.
