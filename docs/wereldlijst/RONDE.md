# De wekelijkse ronde van de wereldlijst

*PLAN #37.12, B90, B91. PO 2026-11-23: "Ja, de wereldlijst" (als vaste wekelijkse ronde).* Sinds de feed van Data Commons
stilstaat (B91), komen nieuwe factchecks uit de wereldlijst en de eigen checks. Elke maandagochtend zet een ingeplande taak
(`wereldlijst-ronde`, 6:00) de voorstellen van de week klaar; de PO kiest; daarna gaan ze mee in de volgende uitgave. Dezelfde
werkwijze als de eerste lijst van 2026-11-23, die de PO zonder opmerkingen goedkeurde.

`<dag>` is de maandag van de ronde (`--tot`, standaard vandaag); de week loopt van zeven dagen ervoor tot en met die dag.

## Deel 1: de ronde (de ingeplande taak)

1. **De opdrachten.** `python -m doublecheck.wereldlijst ronde` schrijft vier opdrachten in `data/overzicht/<dag>/`
   (`opdracht-europa.md`, `-amerikas`, `-midden-oosten-afrika`, `-azie`): de vaste opdracht van de eerste ronde
   (`doublecheck/wereldlijst_onderzoek.md`) met de week, het deel van de wereld, nuttige redacties en wat Factiz al heeft
   (de eigen checks en elke eerdere wereldlijst). Samen twintig voorstellen.
2. **De onderzoekers.** Vier onderzoekers tegelijk (Agent, `general-purpose`), elk met de tekst van één opdrachtbestand,
   letterlijk. Elk schrijft zijn voorstellen naar het bestand dat de opdracht noemt.
3. **De schaal.** `python -m doublecheck.wereldlijst schalen` zet bij elke check het woord van de schaal van het archief
   (onwaar, misleidend, deels-waar, waar, onbewezen, satire) dat de tabel van `verdicts` kent. Wat open blijft, zet de
   nakijker met de hand in het voorstel: het oordeel van de redactie op die schaal, nooit een eigen oordeel (DR2). Een
   bewerkt of uit zijn verband gehaald beeld is *misleidend*, een verzonnen bewering of citaat *onwaar*.
4. **Nalezen.** Open de pagina van elke check en bevestig het oordeelwoord, de datum, de titel en de link; klopt iets niet,
   verbeter het of laat de check weg (en zonder erkende check het voorstel). Geen zin van een redactie overgenomen; elke zin
   met het nummer van zijn check; geen link naar de post van een privépersoon; geen lange streep of uitroepteken.
5. **Nakijken.** `python -m doublecheck.wereldlijst nakijken` moet zonder fouten eindigen (de regels van het weekbestand,
   elke check in de week, geen dubbele sleutel). Haalt een deel van de wereld er minder dan vijf, dan is dat zo; nooit een
   voorstel dat de regels niet haalt.
6. **De pagina.** `python -m doublecheck.wereldlijst pagina` schrijft `data/overzicht/<dag>/overzichten.html`. Publiceer die
   als nieuwe Artifact met `capabilities: {"db": {}}` en icon `globe`; de PO kiest per overzicht goed, twijfel of weg (de
   collectie `keuzes` van de pagina). Zet de link in `data/overzicht/<dag>/pagina.txt`.
7. **Melden en stoppen.** Meld de PO de link en per deel van de wereld wat erin zit, en wat open of twijfelachtig bleef.
   Niet verder: geen weekbestand, geen vertaling, geen uitgave, niets op het Cloudflare-account.

## Deel 2: na de keuze van de PO (in een gewone sessie)

8. **De keuzes lezen.** Uit de collectie `keuzes` van de pagina in `pagina.txt` (ArtifactData, `list`), als
   `{sleutel: goed|twijfel|weg}` in `data/overzicht/<dag>/keuzes.json`. Een opmerking van de PO lees je mee.
9. **Het weekbestand.** `python -m doublecheck.wereldlijst akkoord --tot <dag> --keuzes data/overzicht/<dag>/keuzes.json
   --akkoord '<datum>, PO: "<haar woorden>"'` schrijft `content/wereldlijst/<dag>.json`: goed gepubliceerd, twijfel als
   concept, weg eruit. Dan `python -m doublecheck.wereldlijst controleren`.
10. **Vertalen.** `python -m doublecheck.wereldvertaling plan|indienen|ophalen` (alle talen van de site; samen met de eigen
    checks hoogstens $5 per week).
11. **Uitgeven.** Met de volgende uitgave: `python -m doublecheck.uitrol voorbereiden`, en live alleen met een ja van de PO.
