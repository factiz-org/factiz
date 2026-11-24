# Merk en conformantie

De code is vrij (AGPL-3.0), de specificatie is vrij (CC BY 4.0). Wat níét vrij
is, is de bewering **"conform aan het resolverprotocol"** onder onze naam.

Dat is met opzet het enige voorbehoud. De code kun je forken, de spec kun je
kopiëren, een concurrent kun je bouwen — allemaal prima, en allemaal de reden
dat dit project bestaat. Maar wie zegt dat zijn resolver de verplichtingen
uit §2 nakomt terwijl hij dat niet doet, verkoopt precies de belofte die dit
project wil vervangen.

## Wat mag zonder toestemming

- De code gebruiken, wijzigen, draaien en doorgeven onder AGPL-3.0.
- Het protocol implementeren, ook commercieel. Onbeperkt (`LICENSE-PROTOCOL.md`).
- Verwijzen naar dit project: "gebouwd op Factiz", "gebouwd op Doublecheck",
  "spreekt het resolverprotocol", "fork van Doublecheck". Beschrijvend
  gebruik is vrij.
- Je fork een eigen naam geven. Graag zelfs.

## Wat een voorwaarde heeft

Jezelf **conform** noemen. Die claim mag, en is gratis, mits:

1. `python -m conformance <jouw-url>` slaagt, en
2. je het rapport op verzoek kunt laten zien.

Er is geen aanvraag, geen keurmerkbureau en geen factuur. De handhaving is
sociaal en dat is expres: iemand zegt "conform", een ander draait de suite.
Dat mechanisme kost niemand personeel en schaalt zonder ons.

Slaagt de suite niet, gebruik dan een andere formulering — "spreekt het
protocol", "gedeeltelijk conform, zie rapport". Een rapport met een eerlijk
vraagteken is meer waard dan een vinkje dat niemand kan narekenen.

## Wat wij hier níét beweren

**Er is geen merkregistratie.** Niet aangevraagd, niet verleend. De dienst
heet sinds 2026-10-04 **Factiz** (factiz.org — besluit B19 in
`docs/REQUIREMENTS.md`): een werknaam voor de eerste lancering, gekozen na een
vrijbaancheck (domein vrij, geen bestaand merk gevonden) en met de
Factly-nabijheid bewust gewogen. "Doublecheck" blijft de technische naam van
de codebase en het protocoloppervlak (`/.well-known/doublecheck`). Dit bestand
legt vast wat wij voorbehouden en waarom; het beweert niet dat wij dat vandaag
juridisch kunnen afdwingen.

Dat is minder erg dan het klinkt, en sinds **B13(c)** *(PO 2026-08-31)* is het
ook zo vastgelegd: het dragende been van dit project is niet het merk maar de
**publiek genummerde, draaibare test**. "Conform aan resolverprotocol v0.1" is
door iedereen te weerleggen, ongeacht wie de naam bezit — de suite betrapte bij
haar eerste run onze eigen dienst op verplichting 7.

De naam is de drager, niet het been. Verandert hij, dan verhuist dit voorbehoud
mee en blijft de test staan.
