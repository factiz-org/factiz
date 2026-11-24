# Misbruikbeleid — voor wie een publieke instantie draait

*Hoort bij #22.4 (publieksdemo) en RUNBOOK.md. Uitgangspunt: deze dienst
bewaart geen artefacten en kent geen accounts (DR3), dus de meeste klassieke
misbruikdoelen bestaan hier simpelweg niet. Wat overblijft, staat hieronder.*

## Wat de software zelf al weert

- **Floods**: per-IP token-bucket (60/min, burst 30 — `[ratelimit]` in
  config); wie erdoorheen gaat krijgt een rustige 429 met uitleg. Achter een
  proxy of met meerdere werkers hoort de grens in de infra (RUNBOOK).
- **Oversized of vijandige invoer**: alle grenzen staan in BENCHMARK §55
  (tekst 10k tekens, beeld 8 MB en 12 MP vóór decodering, OCR-subprocess
  10 s) en worden met een eigen foutstaat geweigerd — niets wordt verwerkt,
  niets bewaard.
- **Indexvervuiling**: de demo heeft geen schrijfroute naar het corpus. De
  index groeit uitsluitend via de feedimport, achter de B14-taalpoort, de
  datumregel (#21.4) en de uitgeverweringen (#17.5).

## Wat we van gebruikers vragen

- **Schraap de demo niet.** De code is open source (AGPL) en het corpus is
  CC BY: wie volume nodig heeft draait in minuten een eigen instantie
  (`python -m doublecheck.bootstrap`) in plaats van andermans demo leeg te
  trekken. Structureel geautomatiseerd verkeer op een publieksinstantie kan
  op IP-niveau geweerd worden.
- **Inhoudelijk oneens met een uitslag?** Dat is geen misbruik maar een
  betwisting: de knop staat onder elke uitslag (B11), met expliciete
  toestemming vóór er iets bewaard wordt en een verwijdersleutel erbij.

## Wat de beheerder belooft

- Er wordt niets gelogd van wat bezoekers insturen (DR3: logging staat op
  bibliotheekniveau uit), dus er valt ook bij een incident niets te lekken.
- Blokkades zijn per adres en tijdelijk waar mogelijk; de dienst oordeelt
  niet over personen, alleen over verzoekvolume.

## Wat Factiz niet doet, ook niet op verzoek (B29)

- **Geen gegevens over personen of accounts.** De kaart en de open data
  tellen per claim, taal en periode. Wie een bewering deelde, weet Factiz niet
  en houdt het ook niet bij.
- **Geen apart product of exclusieve toegang voor een overheid.** Een
  overheid gebruikt de openbare kaart en de open data, zoals iedereen.
- **Geen hulp bij verwijderen of handhaven.** Factiz toont wat redacties
  vonden, met hun bonnetje; het zegt niet wat er van het internet af moet.
- **Financiering door een overheid alleen openbaar en los van de inhoud.**
  Geen voorwaarde over welke claims, talen of bronnen in het geheugen komen.

