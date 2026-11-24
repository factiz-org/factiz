# Doublecheck v1 — Eindbalans

> Opsteller: Lead Developer · **herzien 2026-08-31**, na etappe 19, de vijf
> besluiten uit het besluitenplan en het afronden van 15.3.
> De vorige versie dateerde van 28 augustus, na etappepoort 5; die is vervangen
> omdat vrijwel elk cijfer erin achterhaald was.
>
> **Alle cijfers zijn gemeten, niet geschat**, en op de dag van schrijven
> opnieuw gedraaid. Elk is na te rekenen met de commando's uit `CLAUDE.md`.

## 1. Wat er staat

| | |
|---|---|
| Testsuite | **1.576 geslaagd**, 8 xfail *(bewuste bevindingen, §6)* |
| Code | 8.037 regels productie, 9.305 regels test — meer test dan code |
| Modules | 33, plus `conformance/` als los pakket |
| Commits | 144, elke taak apart |
| Corpus | **79.676 claims · 80.555 factchecks · 38 talen · 1.596 uitgevers** |
| Etappes | 21 |
| Benchmarkdocument | 53 secties, inclusief de ingetrokken metingen |

De vorige balans stond op 142 tests en 4.631 claims. Het corpus is zeventienmaal
zo groot geworden **en van bron gewisseld**: alles komt nu uit de CC BY-feed van
Data Commons, niets meer uit de Fact Check Tools API. Dat was geen optimalisatie
maar een licentienoodzaak — zie B13.

## 2. De doelen afgerekend

### G1 — "De resolver zit er vrijwel nooit naast"

| route | fouten | bovengrens95 |
|---|---|---|
| tekst, strikt | **5 op 1.550** | **0,68%** |
| tekst, clusterbewust | **2 op 1.550** | **0,41%** |
| beeld | **0 op 4.000** | **0,07%** |
| gemengd (beeld + tekst) | 0 misleidend op 60 | — |

**De norm is nul, dus G1 is formeel niet gehaald** — maar de vijf resterende
fouten zijn gediagnosticeerd en structureel: twee `inkorting`, twee
`vervorming`, één `ontkenning`. Geen enkele drempel neemt ze weg; dat is
uitgesweept en vastgelegd (§11, §36).

Ter ijking van hoe ver het gekomen is: dezelfde meting gaf ooit **264 op 1.000**.

### G2 — "Vindt een substantieel deel terug"
Dekking **64,8%** (518 van 800 zelfde-claim-paren). Bewust niet
gemaximaliseerd: de drempels staan op precisie, en de sweep laat zien dat
verlagen fouten kost zonder dekking te winnen.

### G3 — "Door derden na te rekenen"
Gehaald, en sinds etappe 15 in een sterkere vorm dan bedoeld. Naast het
benchmarkdocument staat er nu een **conformantietest die tegen elke
resolver-URL draait** — `python -m conformance <url>` — en die tien
verplichtingen toetst. Niet "wij zeggen dat het klopt", maar "draai het zelf".

### G4 — "Werkt buiten het Engels"
Gehaald en verbreed. Nederlands: **0 fouten op 525 paren**. Maar het punt is
groter geworden dan G4 vroeg: de index draagt 38 talen, en sinds B14 mag een
taal er alleen in als het model haar **aantoonbaar kan representeren**, gemeten
vóór opname. Die regel bestaat omdat drie talen 71% valse matches gaven op een
manier die per constructie buiten elke benchmark viel (§39).

### Prestatie-eis E3.S1-AC3 — *dit is wat het eerst gaat breken*

| | vorige balans | **nu** |
|---|---|---|
| index | 4.631 claims | 79.676 |
| mediaan | 28 ms | **190 ms** |
| p95 | 44 ms | **316 ms** |
| max | 129 ms | **479 ms** |

De eis is < 500 ms en wordt gehaald, maar **de marge is nog 1,6× en de maximale
waargenomen tijd zit op 479 ms**. Brute force over numpy heeft dit gedragen tot
tachtigduizend claims; bij ongeveer het dubbele is het op. De vectorindex uit de
parking lot is daarmee van "ooit" naar "eerstvolgende" verschoven.

## 3. Wat er sinds de vorige balans bij is gekomen

- **Een corpus dat weggegeven mag worden.** De Fact Check Tools API verbiedt
  databases, herdistributie én afgeleide werken; de Data Commons-feed staat
  onder CC BY. Volledig omgezet, met herkomst per record en een commando dat
  weigert bij één gebonden regel.
- **Open source in drie stukken** (B13): specificatie CC BY, code AGPL-3.0,
  en conformantie op een genummerde draaibare test. Dat derde been heette eerst
  "het merk"; dat bleek de verkeerde naam voor het bezit.
- **Een protocol** (`docs/PROTOCOL.md`) met negen normatieve verplichtingen, een
  ontdekkingsdocument, en clientzijdige beeldfingerprints — het artefact hoeft
  het apparaat niet meer te verlaten.
- **Clustering en DR7.** Van 3 claims met twee onafhankelijke uitgevers naar
  **616 clusters** met er twee of meer.
- **PDQ in plaats van pHash**, waarmee de beeldroute van 261 fouten op 1.000
  naar nul ging en de v1-inperking kon vervallen (B15).

## 4. Domeinregels: hoe ze worden afgedwongen

Geen van deze regels leunt op discipline; elk heeft een mechanisme dat breekt
zodra iemand hem schendt.

| Regel | Afdwinging |
|---|---|
| **DR1** bron verplicht | `NOT NULL` plus weigering bij import; een bronloze factcheck kán er niet in |
| **DR2** geen waarheidspercentage | Walker over élk dataclass en pydantic-model in het pakket |
| **DR3** geen artefactopslag | Kritieke test over vier kanalen ná een echte beeldresolve, plus een test dat die controle een écht lek nog betrapt |
| **DR4** nooit `matched` onder de drempel | Veegtest tot de laatste float onder de grens; alleen `categorize.py` mag een uitkomst construeren |
| **DR5** `assessed` ≠ `matched` | `category` is verplicht enum; een respons zonder is niet construeerbaar |
| **DR6** config, geen hardcoding | Elke fingerprint draagt zijn versie; de resolver weigert bij een niet-herbouwde index; ook de taallijst en de beeldrenderer dragen nu hun versie |
| **DR7** één claim, meerdere checks | Foreign key, `UNIQUE(claim_id, url)`, plus een uitgeversregister zodat één redactie niet als twee telt |
| **DR8** tegenspraak nooit `matched` | Degradatie in de categorisering, aangetoond met mutatiecheck |
| **DR9** bewaartermijn | `CHECK` in het schema plus een sweep bij opstart én periodiek |

**Nieuw sinds de vorige balans**, en even belangrijk als de DR-regels zelf:

| Guard | Wat hij tegenhoudt |
|---|---|
| `test_schriftpaneel.py` | Code die stilzwijgend Latijn aanneemt — 24 schriften, en elke tekstfunctie moet een schriftcontract hebben |
| `test_afhankelijkheden.py` | Imports die niet in `requirements.txt` staan; ongeldige ontsnappingen; definities ná het `__main__`-blok |
| `test_licenties.py` | Herdistributie van CC BY-materiaal zonder naamsvermelding |
| `test_conformantie.py` | De suite zelf: negen kapotte resolvers worden alle negen betrapt |
| `relation._PROEVEN` | Testsetdata die niet meer bij zijn afleidingscode past |

## 5. Het patroon — zes keer dezelfde fout

Dit is het waardevolste dat dit project heeft opgeleverd, en het staat hier
apart omdat een opvolger het anders opnieuw maakt.

**Een hulpmiddel neemt stilzwijgend Latijn aan, en niets merkt het** — omdat de
tests op Latijnse invoer draaien en het cijfer er béter van wordt:

| | wat er misging |
|---|---|
| §17a | `.upper()` is een no-op in het Arabisch: het artefact wás de claim, gelijkenis 1,000 |
| §39 | onderscheid gemeten op twaalf handgekozen talen; zes ineengeklapte talen gemist |
| §45 | de oordeeltabel kende Nederlands en Engels; 53% van het corpus kwam terug als `onbekend` |
| §46 | de entiteitsmaat leunde op hoofdletters en vuurde nul keer op 61% van de blokkades |
| §48c | `[a-z0-9]` smolt 107 Cyrillische uitgevers tot één identiteit |
| §51d | het lettertype miste CJK-glieven: 23 van 435 paren kregen dezelfde beeldhash |

Twee daarvan zaten in de reparatie van de vorige. De guard uit §51 vond de zesde
binnen een uur na oplevering, en betrapte de opsteller sindsdien drie keer op
nieuwe overtredingen.

De tweede vorm is verwant: **afgeleide staat veroudert zonder dat iets het
merkt** — modelversies (DR6), testsetdata (11.5), clusters (12.3), marktdekking
(B14), de beeldrenderer (18.3), en zelfs een *bevinding*: het cijfer waarop 17.4
zijn besluit baseerde was berekend met een uitgeversidentiteit die daarna
gerepareerd werd (§47b2).

## 6. Wat bewezen kapot is

Dit staat er niet ter verontschuldiging maar omdat een cijfer zonder zijn
beperkingen misleidt.

- **Vijf structurele benchmarkfouten** die geen enkele drempel wegneemt.
- **Ongeveer zeventig van de 227 vetoblokkades splitsen dezelfde bewering.**
  Kosten: ~25 DR7-koppelingen, 4,1%. Er is geen bruikbaar onderscheid tussen
  parafrase en entiteitswissel in schrift zonder hoofdletters, en dat is 61% van
  de blokkades (§46).
- **Bijsnijden wordt niet herkend.** Geen van beide beeldhashes overleeft
  10% randafsnijding; wie bijsnijdt valt terug op OCR.
- **23% van de oordelen blijft `onbekend`.** Duits staat op 94% — niet omdat de
  tabel te klein is, maar omdat ClaimReview vrije tekst als oordeel toestaat.
  Dat is B16's derde zwakte, en hij is met een tabel niet op te lossen.
- **`assessed` bestaat niet.** Dat is een besluit (B3, bevestigd 11.2), geen
  gebrek — maar het betekent dat verplichting 3 tegen onze eigen resolver
  onwaarneembaar blijft, en de conformantiesuite zegt dat hardop.
- **Acht xfails**, waaronder het ontkenningsprobleem op modelniveau.

## 7. Wat er níét in zit, en waarom

De Won't-lijst is niet stilzwijgend aangevuld. Geen accounts, geen
consumentenschil, geen platform-integraties, geen externe AI-aanroepen, geen
eigen oordeel. Elke uitbreiding die er wél kwam ging eerst door
`REQUIREMENTS.md` met een expliciet besluit — zestien inmiddels, B1 tot en met
B16, waarvan er drie later zijn aangescherpt op grond van een meting die het
oorspronkelijke besluit weersprak.

## 8. Aanbeveling

**De kern is bewezen en het huis is opgeruimd.** Er staat geen open taak in
`PLAN.md` en geen open besluit in `REQUIREMENTS.md` of `PROTOCOL.md`. Dat is een
goed moment om te stoppen met bouwen en te beginnen met uitgeven.

Drie dingen, in deze volgorde:

1. **Beslis over de naam.** Dat is het enige wat een publieke lancering nu nog
   tegenhoudt. `TRADEMARK.md` beweert bewust geen registratie, en B13(c) is zo
   geformuleerd dat een naamswissel het fundament niet raakt — maar iemand moet
   hem kiezen.
2. **Zet de vectorindex op de rol.** Niet omdat het nu knelt, maar omdat de
   marge op de prestatie-eis nog 1,6× is en corpusgroei het eerste is wat een
   uitgave oplevert.
3. **Laat het corpus zijn werk doen.** De betwistingsroute staat er, de
   conformantietest staat er, het protocol staat er. Wat ontbreekt is
   praktijkdata: echte artefacten uit het wild, waarop de NLI-drempel en de
   sjabloonvraag pas eerlijk te beoordelen zijn. Dat is niet te bouwen, alleen
   te verzamelen.

Voor B12 geldt tot slot wat er ook in de vorige balans stond, nu met meer
gewicht: het cijfer dat het onafhankelijke "Klopt dit?"-icoon moet dragen
bestaat, is publiek narekenbaar, **en is door een derde te controleren zonder
ons te geloven**. Dat laatste is er sinds etappe 15 bij gekomen, en het is het
verschil tussen een belofte en een standaard.
