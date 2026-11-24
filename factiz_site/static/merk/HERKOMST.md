# Het logo en de beelden eruit (PLAN #23.18, DESIGN §4h)

Eén plek voor de site en het platform (PLAN #34.2f): `factiz_site/static/merk/`, gemaakt door
`python -m doublecheck.merkbeelden`; `tests/test_merkbeelden.py` eist dezelfde bytes.

- `logo.svg` en `woordmerk.svg`: van de PO, 2026-11-09. `logo.svg` is ook het icoon van de site.
- Getekend door het script, uit de vormen in die twee SVG's (geen download, geen beeldmodel):
  - `woordmerk-wit.svg`: de letters wit, voor een donkere grond.
  - `avatar.png`: 1024×1024, het logo op het volle oranje vierkant; de ovalen blijven binnen een cirkel.
  - `og.jpg`: 1200×630, het beeld bij delen: `../beeld/delen.jpg` (de uitsnede van corpus) met het woordmerk in wit.
  - `apple-touch-icon.png` (180×180, het volle vierkant) en `favicon.ico` (16, 32 en 48 pixels).
  - `woordmerk-deel.png`: 34 pixels hoog, de letters zwart, voor het deelplaatje per factcheck (PLAN #34.2aq).
- Voor het openbare repo (PLAN #34.2bl), in `.github/assets/`: `social-preview.jpg` (1280×640, in te stellen bij Settings,
  Social preview) en `banner.jpg` (boven de README), op het veld corpus met het woordmerk in wit, de pay-off en wat Factiz
  is, in Geist, de letter van de site.
- In kop en voet staat het woordmerk inline, uit `factiz_site/static/merk/woordmerk-inline.svg`: de letters in de tekstkleur.
