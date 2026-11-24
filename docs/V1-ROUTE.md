# V1: wat het is, en de technische weg ernaartoe — besloten 2026-10-27 (B46)

> De PO (2026-10-27), na de tussenbalans: "Qua V1 denk ik dat we nu iets te
> snel denken dat we al een product hebben. […] Wij willen nepnieuws herkennen
> en bij dat nepnieuws vermelden waarom het nep is, met de bronnen. […] V1
> beschouw ik als een factcheckmachine die werkt in zoveel mogelijk talen. […]
> En die moet bij elke screenshot kunnen zeggen wat het is." Talen: "Engels,
> Spaans, Chinees en Duits." De stappen: "1. Wat is een gewone tekst? 2. Wat is
> een kloppende tekst? 3. Wat is een corpus van kloppende teksten? 4. Wat is een
> corpus van nepteksten?" En: "Pas veel later gaan we denken aan het lanceren
> […]. Eerst moeten we zelf tevreden zijn over ons product."
>
> Dit voorstel vervangt de route van `docs/TUSSENBALANS-V1.md` §5 (die ging
> naar een beta). Lanceren, de beta en de belofte op de site (#23.16, #31.16)
> komen pas na stap 9.

## 1. Wat V1 is

*Besloten door de PO (2026-10-27, B46): akkoord met besluit A tot en met D, met de talen in deze volgorde, en eerst de hele keten in het Engels.*

**In één zin:** je stuurt een screenshot of een tekst in een van de talen van
V1, en Factiz zegt wat het is. Bij nepnieuws zegt het ook waarom het nep is,
met de bronnen.

### Besluit A: wat Factiz over elk bericht zegt

Altijd één van deze acht uitkomsten, met de stand op de schaal van 0 tot 10:

| uitkomst | wanneer | wat erbij staat |
|---|---|---|
| **Geen bewering** | een gewone tekst: groet, mening, grap, reclame, een vraag zonder bewering | niets te controleren |
| **Satire** | bedoeld als grap, en herkenbaar zo | de bron die het als satire aanmerkt |
| **Klopt** | de hoofdbewering wordt door betrouwbare bronnen bevestigd | de bronnen |
| **Klopt niet** (nep) | betrouwbare bronnen spreken de hoofdbewering tegen | **waarom het nep is**, en de bronnen |
| **Misleidend** | deels waar, oud nieuws als nieuw, een echt beeld in een verkeerde context | wat er klopt, wat niet, en de bronnen |
| **Over een bewering** | het bericht bericht over een bewering van een ander (een factcheck, een nieuwsbericht, een vraag "is dit waar?") | het oordeel over díé bewering |
| **Beeld nodig** | de bewering gaat over wat een foto of video toont, en Factiz ziet het beeld niet | wat er wel bekend is over de gebeurtenis |
| **Onzeker** | niets beslissends gevonden | wat er wel gevonden is |

Bijna alles hiervan bestaat al in de controle (B43, ronde 5). Nieuw zijn
"waarom het nep is" als eigen onderdeel (stap 7) en *misleidend* als eigen
uitkomst; nu heet dat *let op*.

### Besluit B: welke media

| media | in V1 | waarom |
|---|---|---|
| tekst | ja | |
| screenshot met tekst | **ja, de hoofdzaak** | de eerste gebruiker krijgt een screenshot in een appgroep |
| foto zonder tekst | nee; Factiz zegt eerlijk dat het de foto niet kan beoordelen | omgekeerd zoeken haalde de eis niet (§148) |
| video, spraakbericht | nee, versie 2 | zo besloten in de stack (faster-whisper, ffmpeg) |

### Besluit C: welke talen

> **Gewijzigd door B47 (27 oktober 2026):** de talen van V1 zijn Engels, Spaans, Duits en **Portugees**; Chinees gaat
> naar versie 2. De tabel hieronder is de stand van 27 oktober; voor de aanvoer per taal nu, zie RESEARCH §8.2.
>
> **Uitgebreid door B63 (8 november 2026):** ook **Nederlands** (Nederland en Vlaanderen) en **Frans** (Frankrijk,
> Wallonië en Brussel), vanaf de start. Wat er per taal is: BENCHMARK §244; de route: PLAN #32.59.

De PO stelt Engels, Spaans, Duits en Chinees voor. Wat we per taal al hebben:

| taal | factchecks in de database | waarvan onwaar / waar | ware teksten in de basisset | tekstherkenning | wat er ontbreekt |
|---|---|---|---|---|---|
| Engels | 52.342 | 39.398 / 712 | 703 checks, 5.118 artikelen | ja | echte screenshots die werken (54%, §158) |
| Spaans | 5.575 | 4.186 / 279 | 297 checks, 39 artikelen | ja | betrouwbare Spaanse artikelen |
| Duits | 4.139 | 171 / 6 | 6 checks, 88 artikelen | ja | **bij 3.910 checks herkennen we het oordeel niet**; dat eerst oplossen |
| Chinees | 1.014 | 803 / 12 | 12 checks | ja, vereenvoudigd en traditioneel | weinig checks, bijna geen ware; welke bronnen betrouwbaar zijn, moet bewust gekozen worden |
| *ter vergelijking:* Portugees | 7.859 | — | 460 checks | ja | |
| *ter vergelijking:* Nederlands | 2.637 | — | 82 checks | ja | |

Voorstel: Engels, Spaans, Duits en Chinees, in die volgorde. Chinees als
laatste, omdat daar het minste materiaal is. Portugees heeft meer materiaal
dan Duits en Chinees samen; dat is een optie als de PO "zoveel mogelijk
talen" breder wil. Elke taal krijgt haar eigen cijfer (B14), en een taal
zonder gehaalde eis krijgt geen oordeel (B25).

### Besluit D: wanneer we zelf tevreden zijn

Per taal, en voor tekst en screenshots apart:

| | eis |
|---|---|
| rood klopt | op 300 ware berichten hoogstens 3 onterecht rood (99%) |
| groen klopt | op 200 nepberichten hoogstens 2 onterecht groen (99%) |
| bekend nepnieuws herkend | minstens 90% rood met bewijs, ook op echte screenshots |
| gewone tekst | nooit rood; minstens 80% herkend als *geen bewering* (zoals mensen het zien) |
| waarom het nep is | minstens 95% van de zinnen gedekt door een geciteerde bron |
| nagelezen door een mens | 50 willekeurige labels per taal, hoogstens 1 verschil |
| nepnieuws zonder factcheck | gemeten en gemeld, geen eis: Factiz zegt eerlijk *onzeker* |

### Besluit E: wat V1 niet doet

Foto's zonder tekst, video, spraak, andere talen dan die van besluit C, en een
oordeel in een taal die de eis niet haalt. Ook geen controle in bulk: dat is
versie 2.

## 2. Hoe een screenshot door de machine gaat

| stap | wat er gebeurt | wat er is | wat er ontbreekt |
|---|---|---|---|
| 1 lezen | de tekst uit het screenshot halen, per schrift | tekstherkenning in alle vier de schriften | bij echte screenshots ziet Sonnet in 29 van de 100 geen bewering: ligt dat aan het lezen, het opknippen of de bewering zelf? |
| 2 opknippen | wat het bericht is, en wat de omgeving (namen, tijden, knoppen); namen en nummers eruit | gemeten in het Engels, 0 lekken | de regels voor namen en nummers in het Spaans, Duits en Chinees |
| 3 wat voor tekst | gewone tekst, bewering, bericht over een bewering, bewering over een beeld; de hoofdbewering | Sonnet en de vormvraag, gemeten in het Engels | gemeten in de andere talen |
| 4 bewijs zoeken | de database met factchecks (47 talen), de lijst met vastgestelde feiten, het web in de taal van het bericht | alles bestaat | |
| 5 oordelen | een van de acht uitkomsten | gemeten in het Engels | gemeten in de andere talen |
| 6 waarom | waarom het nep of misleidend is, in de taal van de gebruiker, uit de bronnen | een korte uitleg in het Nederlands, niet gemeten en niet getoond (B31) | **moet gebouwd en gemeten worden** |
| 7 de stand | de plek op de schaal, uit het gemeten aandeel waar | geijkt op Engelse berichten (§151) | geijkt per taal |

## 3. De stappen, in volgorde

Eerst de hele keten in het Engels af, daarna taal voor taal. Zo hoeven we de
andere talen niet opnieuw te meten als er in de keten nog iets verandert.

| stap | wat | kosten |
|---|---|---|
| **1** | **Besluiten A tot en met E.** | $0 |
| **2** | **Wat is een gewone tekst?** Een vaste omschrijving met voorbeelden per taal: groet, mening, grap, reclame, vraag, oproep, en waar de grens met een bewering ligt ("mening met een feit erin"). Een verzameling gewone teksten per taal, uit echte tiplineberichten (Engels) en gewone webtekst (mC4, per taal al aanwezig). Gemeten: wordt er nooit één rood, en hoe vaak herkent Factiz *geen bewering*? | ~$1 per taal |
| **3** | **Wat is een kloppende tekst?** Een vaste omschrijving: de hoofdbewering wordt bevestigd door een betrouwbare bron (een factcheck die *waar* zegt, een vastgesteld feit, of betrouwbaar nieuws over dezelfde gebeurtenis). Met de grensgevallen erbij: deels waar, waar maar oud, waar met een fout detail. Per taal een lijst met betrouwbare bronnen; voor Chinees bewust gekozen. | $0 |
| **4** | **Een verzameling kloppende teksten**, per taal 300: ware checks, de kop en het begin van betrouwbaar nieuws (Wikinews en Wikipedia per taal, waarvoor de ophalers er al zijn; de Sheffield-artikelen voor het Engels), vastgestelde feiten. Als tekst, als chatbericht en als screenshot van een nieuwsbericht of post. Een taalmodel stelt de labels voor, een mens leest er 50 na. | ~$1–2 per taal |
| **5** | **Een verzameling nepteksten**, per taal 200: 100 die in de database staan en 100 verse. Daarvoor eerst: de Duitse oordelen herkennen (3.910), en de wekelijkse download van nieuwe factchecks weer laten lopen (sinds 19 oktober niets nieuws). Voor het Chinees: de Taiwanese tipline Cofacts onderzoeken (open data; licentie nakijken). | ~$1 per taal |
| **6** | **Echte screenshots.** Eerst een goedkope voormeting die laat zien waar de 46% misgaat (lezen, opknippen of de bewering). Dan één ronde om ≥90% te halen. Daarna screenshots per taal: echte screenshots uit factcheckartikelen in die taal, en screenshots die we zelf tekenen van ware berichten. | ~$1, daarna ~$5 |
| **7** | **Waarom het nep is.** Een aparte, korte stap na het oordeel, zoals de vormvraag: uit de geciteerde bronnen, in de taal van de gebruiker, elke zin terug te voeren op een bron. Gemeten op die dekking, en door een mens nagelezen. Sonnet zelf (vraag v4) blijft gelijk, dus de ijking van de schaal blijft gelden. | ~$3 |
| **8** | **De machine per taal meten**, op de verzamelingen van stap 2, 4 en 5, als tekst en als screenshot, met de eisen van besluit D. De schaal per taal ijken. Engels als eerste, met alles erin; daarna Spaans, Duits, Chinees. | ~$12 per taal, ~$48 voor vier |
| **9** | **Zelf tevreden?** Alle eisen per taal gehaald, en de labels nagelezen. Pas dan: de belofte herschrijven (#23.16), klaarmaken (#31.16), en daarna lanceren. | $0 |

**Samen ~$65–75**, verspreid over de stappen. Na elke stap kan de PO bijsturen.
Per taal gaan stap 2, 4, 5 en 8 opnieuw; stap 3, 6 en 7 doen we één keer, voor
de hele keten.

## 4. Wat de PO besliste (2026-10-27)

1. **Besluit A**, de acht uitkomsten: akkoord, of anders?
2. **Besluit B**, de media: screenshots en tekst in V1, foto's zonder tekst en
   video niet?
3. **Besluit C**, de talen: Engels, Spaans, Duits en Chinees, in die volgorde?
   Of breder, met Portugees of Nederlands?
4. **Besluit D**, de eisen: akkoord?
5. **De volgorde**: eerst de hele keten in het Engels, dan taal voor taal?
