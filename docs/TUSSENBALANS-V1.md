# Tussenbalans op weg naar V1 — 2026-10-27

> Gevraagd door de PO (2026-10-27): "Eerst even een gate moment maken, waar staan
> we nu, wat is het doel, hoe behalen we dat, wat zijn de volgende stappen die we
> moeten doen om tot een v1 te komen die we durven te delen met de wereld en die
> aantoonbaar doet wat wij claimen? Een random stuk media beoordelen met feiten?"
>
> Elk getal hieronder komt uit een meting in `docs/BENCHMARK.md` (§-nummer erbij).

## 1. Het doel, zoals de PO het nu zegt

**Iemand stuurt een willekeurig stuk media. Factiz zegt met feiten en bronnen
of het klopt, en zegt eerlijk "onzeker" als het het niet weet.**

Om dat te mogen zeggen, moeten drie dingen aantoonbaar zijn:
1. *Als Factiz rood zegt, klopt dat*, met een bron die je kunt openen.
2. *Als Factiz groen zegt, klopt dat ook.*
3. *Het werkt op wat mensen echt sturen*, en niet alleen op onze eigen
   testsets.

## 2. Eerst een tegenstrijdigheid: wat we beloven en wat we bouwen

Er bestaan nu twee producten naast elkaar.

| | **De zoekfunctie** (Factiz 1, klaar, niet gelanceerd) | **De controle** (gebouwd, staat uit) |
|---|---|---|
| wat het doet | zoekt in ~110.000 factchecks van redacties of een bewering al gecontroleerd is, en door wie | Sonnet leest het bericht, krijgt de factchecks die erop lijken, zoekt op het web en geeft een oordeel met bron, op een schaal van 0 tot 10 |
| oordeel | nooit een eigen oordeel; de redactie oordeelt | wel een eigen oordeel |
| waar het draait | op onze server in de EU | het beeld blijft in de EU; de bewering zonder namen en nummers gaat naar Anthropic in de VS |
| talen | 47 talen, elke taal vooraf getoetst | alleen Engels gemeten |

**Wat de site nu belooft**, en wat met de controle niet meer klopt:
- "We never decide what is true ourselves." De controle beslist wel.
- "No scores, no truth percentages, ever." De controle toont een stand van 0
  tot 10, en "Of messages with this result, 2 in 100 turned out to be true".
- "Open source, runs locally, shows counts, never probabilities" (de voet van
  de site). De controle draait niet lokaal.
- De visie in REQUIREMENTS §1: "Het produceert niet zelf de waarheid."

Het doel "een random stuk media beoordelen met feiten" is de controle, niet de
zoekfunctie. **Wie V1 met de controle uitbrengt, moet eerst de belofte op de
site herschrijven.** Anders doet Factiz aantoonbaar níét wat het claimt. Dat
is het eerste besluit (§6, besluit 1).

## 3. Waar we staan

### Per soort media

| soort media | wat Factiz ermee doet | stand |
|---|---|---|
| tekst (Engels) | volledig gecontroleerd | sterk |
| screenshot met tekst (Engels) | de tekst wordt gelezen, het beeld niet | zwak bij echte screenshots |
| foto zonder tekst | niet gecontroleerd: "photos without text are not checked yet" | ontbreekt; omgekeerd zoeken haalde de eis niet (§148) |
| bewering over wat een foto of video toont | sinds ronde 5 eerlijk *onzeker* | niet herkend, wel eerlijk |
| video, spraakbericht | niet | versie 2 |
| andere talen | alleen de zoekfunctie, geen oordeel | niet gemeten |

### De metingen

| wat | uitslag | waarop gemeten | § |
|---|---|---|---|
| **rood klopt** (ware berichten onterecht rood) | 7 van 298 (97%) in ronde 4; 6 daarvan waren artikelen over een bewering. Na de regels van ronde 5: 0 van 99 nieuwe artikelen (99%) | ware checks en betrouwbare nieuwsartikelen, Engels | §158, §159 |
| **groen klopt** (nepnieuws onterecht groen) | 10 van 400 in ronde 4; 7 daarvan beweringen over een beeld, die regel 2 nu *onzeker* maakt; 0 van 100 in ronde 5 | onware checks, Engels | §158, §159 |
| bekend nepnieuws als tekst, rood met bewijs | 99 van 99 | onware checks die in de database staan | §158 |
| **bekend nepnieuws als echt screenshot** | **54 van 100** | screenshots uit factcheckartikelen (M4FC) | §158 |
| nepnieuws zonder factcheck in de database | 53% rood met bewijs, maar **zelf herkend 21%**; de rest via een factcheck die een andere site had overgenomen | verse onware checks, factchecksites geblokkeerd | §158 |
| een vastgesteld feit (stand 10) | nooit onterecht, op 945 | 40 feiten met minstens vier bronnen | §154 |
| **echte berichten uit tiplines** | van de berichten met een bewering krijgt **70% *onzeker***; 39 van de 41 oordelen met bron houden stand | 250 berichten uit Indiase tiplines, 2019–2021, zonder waarheidslabel | §149 |
| privacy | 0 nummers, adressen of handles gelekt in 375 chatberichten | getekende chatberichten | §158, §159 |
| wachttijd | 95% binnen 6,9 s (zonder de vormvraag van ronde 5) | 20 berichten live | §158 |

### Wat de getallen samen zeggen

- **Betrouwbaar is het al, op tekst in het Engels.** Rood klopt in 97 (ronde 4)
  tot 99 (ronde 5, met de regels) van de 100 gevallen. Groen klopt in ongeveer
  99 van de 100.
- **Het zwakke punt is hoe vaak Factiz iets zegt.** Bij echte berichten zegt
  het meestal *onzeker*. Bij echte screenshots bewijst het maar de helft van het
  bekende nepnieuws. En nepnieuws waarover nog geen factcheck bestaat, herkent
  het zelf zelden.
- **"Een willekeurig stuk media" is nog niet gemeten.** Elke meting gebruikte
  een samengestelde set: factchecks, nieuwsartikelen, screenshots uit
  factcheckartikelen en getekende chatberichten. De enige set uit het wild
  (§149) heeft geen labels voor waar of onwaar.
- **De labels zijn door Claude gelezen, niet door een mens.** Voor een
  publieke claim moet een mens een steekproef nalezen (B34: een taalmodel stelt
  voor, een mens kijkt na).

## 4. Wat "aantoonbaar" voor V1 betekent

Een V1 die we durven te delen, publiceert per belofte één zin, en elke zin
hoort bij een meting die iedereen kan nalezen. Voorstel voor die zinnen, met
de eis eronder:

| belofte | eis voor V1 | nu |
|---|---|---|
| "When Factiz says false, it is right at least 99 times in 100, and it shows the source." | ≤3 van 300 ware berichten rood, op een nieuwe set die op echte berichten lijkt | 99% op artikelen (§159); de hele set opnieuw met de regels: nog niet |
| "When Factiz says true, it is right at least 99 times in 100." | ≤1% van het nepnieuws groen | ~0–1% (§158, §159), nooit als eis vastgelegd |
| "It reads screenshots." | bekend nepnieuws op echte screenshots ≥90% rood met bewijs | **54%** |
| "When it does not know, it says so." | nooit een oordeel zonder bron | gehaald (§149, §158) |
| "Your screenshot never leaves the EU; the claim goes to a model provider that keeps nothing." | ZDR actief, 0 lekken | 0 lekken; ZDR nog niet actief |
| "Checked by people, not just by us." | een mens heeft een willekeurige steekproef van 50 labels nagelezen, met hoogstens 1 verschil | nog niet gedaan |
| "Run it yourself." | de testset, de labels en de code zijn openbaar; één commando draait de meting opnieuw | de code wel; testset en labels nog niet als pakket |

Wat V1 **niet** belooft: foto's zonder tekst, video, andere talen dan Engels,
en het zelf herkennen van nepnieuws waarover nog niets gepubliceerd is.

## 5. De route naar V1

In volgorde van wat het meest oplevert voor de belofte, met na elke stap een
moment om bij te sturen.

| stap | wat | waarom | kosten |
|---|---|---|---|
| 1 | **De belofte vastleggen:** de zinnen van §4 kiezen, en de site, REQUIREMENTS §1 en het voorstel voor V1 erop aanpassen | zonder dit doet Factiz niet wat de site zegt | $0 |
| 2 | **Echte screenshots** van 54% naar ≥90%. Eerst een goedkope voormeting die laat zien waar het misgaat (lezen, opknippen of zoeken), daarna één ronde | dit is het grootste gat, en de eerste gebruiker is iemand met een screenshot in een appgroep | ~$1, daarna ~$5 |
| 3 | **Een mens leest na:** de PO of een externe factchecker leest 50 willekeurige labels uit de rondes 4 en 5 | maakt de getallen aantoonbaar | $0, ~2 uur leeswerk |
| 4 | **De V1-proef:** één beslissende meting op een nieuwe set, met de regels en de screenshots erin, inclusief groen als eis. Testset en labels openbaar, met één commando opnieuw te draaien | het getal dat we publiceren | ~$15 |
| 5 | **Klaarmaken** (ronde 6, nu geparkeerd): ZDR, limieten, de knop om te betwisten, de wekelijkse controle, de releasekaart | nodig om open te gaan | ~$2 |
| 6 | **Beta en V1** (B45): V1 gaat uit als de eis drie weken op rij gehaald wordt bij echt gebruik | het bewijs uit de praktijk | ~$30–50 per maand |

Samen tot de beta ~$23, plus leeswerk. De PO bepaalt het tempo. Volgens
"eerst fijnslijpen" zijn stap 2 tot en met 4 dat fijnslijpen.

**Wat de route bewust overslaat voor V1:**
- *Nepnieuws zonder factcheck zelf herkennen* (21%). Factiz zegt dan eerlijk
  *onzeker*, en V1 belooft dit niet. Beter worden kan na V1.
- *Foto's zonder tekst en video.* Versie 2.
- *Andere talen.* Elke taal is een eigen meting van ~$10. Nederlands is de
  eerste kandidaat, zodra er testers zijn die het nodig hebben.

## 6. Besluiten voor de PO

1. **Wat is V1?**
   - (a) *De controle* (Engels, tekst en screenshots, met een eigen oordeel),
     met de zoekfunctie als basis. De belofte op de site wordt herschreven.
   - (b) *Alleen de zoekfunctie*, zoals de site nu belooft. De controle wordt
     versie 2.

   Het doel "een random stuk media beoordelen met feiten" vraagt (a).
2. **De beloftes van §4:** akkoord met deze zinnen en eisen, of andere?
3. **De volgorde van §5:** de screenshots als eerste stap van het fijnslijpen,
   of eerst iets anders?
4. **Wie leest na** (stap 3): de PO zelf, of een externe factchecker (en welke)?
