# Architectuur voor de zeef: toets en voorstel

> Opsteller: Lead Developer · 2026-10-17 · **besloten door de PO op
> 2026-10-17 (B35–B38)**: "eens, leg alle besluiten vast".
> Aanleiding: de PO vroeg of de huidige architectuur en stack opgewassen zijn
> tegen wat er nu ligt (B33 met de lat in twee lagen, B34 de feitenbasis,
> etappe 30). Alle cijfers komen uit BENCHMARK of uit metingen van deze week.

## Het oordeel

De principes houden: lokaal in het aanvraagpad (B26, DR3), een modelversie
bij elke vector (DR6), één plek die de categorie zet (DR4), bonnetjes bij
elk antwoord, en geen release zonder verschoven cijfer (B22). Die blijven.

De vorm houdt niet. Factiz is gebouwd als **één zoekstap met een drempel, op
één CPU-server, voor één vraag tegelijk**. De nieuwe taken vragen drie dingen
die daar niet in passen:

1. **Een tweede stap die beoordeelt** of een kandidaat hetzelfde beweert. Met
   één drempel komt de precisie niet op 99,5%, en de vindkans niet op 95%.
2. **Meerdere indexen naast elkaar** (claims, beelden, verhalen, feiten), die
   samen niet meer in het werkgeheugen passen.
3. **Een batchpad** voor een miljoen stukken met beeld, video en geluid, dat
   dezelfde beslisregels gebruikt als de resolver.

Geen herbouw dus, maar een verbouwing in vijf stappen, elk een release met een
cijfer.

## Wat er nu staat

Een artefact gaat zo door Factiz:

1. Een beeld krijgt een PDQ-hash en gaat door Tesseract. De productie-index
   draagt geen enkele beeldhash, dus alleen de gelezen tekst telt.
2. De tekst gaat door bge-m3 en, als het een vraag is, ook als bewering
   (#25.36).
3. Zoeken gebeurt brute-force in het werkgeheugen, over ruim 108.000 claims
   en 462.000 varianten.
4. Alleen de beste kandidaat telt. De regels van DR8 kijken naar getallen en
   ontkenningen.
5. `categorize` zet de categorie op drempels (0,87 / 0,79), en daarna komen
   de bonnetjes.

| onderdeel | nu | wat de metingen zeggen |
|---|---|---|
| tekst | bge-m3 op CPU | rangorde meestal goed, gelijkenis niet: de juiste check staat vaak bovenaan, maar onder de drempel (§108, mediaan 0,69) |
| beslissen | één drempel plus DR8 | 6 van 359 keer `matched` fout (98,3%, §120); 3 van 16 ware feiten kregen een rood oordeel (B34): een omgedraaide rol, een andere lading, een datum |
| beeld | PDQ, geen index in productie | PDQ én DINOv2 samen vinden bijna twee keer zoveel kaders (§92); in de zeef 8 van 1.103 beelden gevonden |
| OCR | Tesseract, per schrift | nooit los gemeten op de beelden die rondgaan |
| relatiemodel | mDeBERTa NLI, alleen offline | scheidt "zelfde bewering" goed via entailment in twee richtingen, maar 525 ms per paar op CPU (§15) |
| opslag | SQLite, vectoren als blobs, zoeken in RAM | één werker gebruikt ongeveer 4,4 GB |
| batch | losse meetscripts via de API | de zeef deed 1.103 beelden in 45 minuten en de webtekst in ruim twee uur |
| hosting | de site en het zoeken bij Cloudflare, in TypeScript op Workers met D1 (B80); de controle per bericht en het lab later op Hetzner, CPX31: 4 vCPU, 8 GB, geen GPU (B21) | de proef van PLAN 34.2bo: zoeken in D1 gelijk aan Python, de tellingen per filter in het geheugen van de Worker; de CPX31 past voor wat er nu draait, niet voor modellen erbij |

## De nieuwe taken, en of het huidige ontwerp ze draagt

| taak | wat die vraagt | draagt het huidige ontwerp het? |
|---|---|---|
| precisie 99,5% (B33) | per kandidaat beoordelen of hij hetzelfde beweert, ook bij een omgedraaide rol | **nee**: DR8 ziet getallen en ontkenningen, niet wie wat deed |
| vindkans naar 95% (B33) | breed zoeken, dan beoordelen; een artikel per zin lezen | **nee**: de drempel laat de juiste kandidaat liggen (§108); artikelen 3 van 835 |
| nultolerantie op de kern (B33) | elke release alle kernfeiten erdoor | **ja**, met de zeef; maar zonder rechter zakt hij nu al (B34) |
| verhalen (#30.2) | een verhaallaag naast de claims | **nee**: bestaat niet |
| feitenbasis (B34) | zoeken en toetsen over miljoenen passages | **nee**: tien miljoen passages zijn 41 GB aan vectoren, en alles staat in RAM |
| beeld zonder tekst (#30.4) | een beeldindex | **half**: PDQ en DINOv2 zijn gemeten, maar niet in productie |
| video en stem (#30.4) | frames, ondertitels, spraak | **nee**: bestaat niet; voorstel: V2 |
| een miljoen stukken (B33, #30.6) | een batchpad met dezelfde beslisregels | **nee**: alleen per vraag |

## Het voorstel: vijf lagen, één beslisplek

1. **Binnenkomst.** Tekst, URL, beeld, video of geluid, alleen in het
   geheugen (DR3).
2. **Uitlezen: wat wordt er beweerd?** OCR op beelden, een artikel per zin,
   de vraagvorm; in V2 ook spraak naar tekst en frames bij scènewissels. Het
   resultaat is een lijst beweringen, met waar ze vandaan komen.
3. **Breed zoeken, gericht op de vindkans.** Per bewering de beste vijftig
   kandidaten uit vier indexen: claims en varianten (betekenis plus woorden,
   §108), beelden (eerst PDQ, dan DINOv2), verhalen (#30.2) en feiten (B34).
   De indexen staan op schijf, met een modelversie per index (DR6).
4. **Beoordelen, gericht op de precisie.** Een lokale rechter kijkt per
   kandidaat: *zelfde bewering*, *verwant* of *iets anders*, en of hij haar
   tegenspreekt. Alleen de kandidaten die ertoe doen, niet alle vijftig.
5. **Beslissen.** `categorize` blijft de enige plek die de categorie zet
   (DR4) en krijgt het oordeel van de rechter als invoer. Signalen van laag 2
   (*lijkt op een bekende misleiding*, *klopt met bron*) komen ernaast, nooit
   in de vorm van een check (DR5). Laag 3 komt pas na de poort van B30.

Daarna, zoals nu, de bonnetjes.

**Het batchpad** gebruikt dezelfde functies voor stap 2 tot 5, in porties,
met een wachtrij die hervat waar hij stopte. Dat is geen tweede beslispad: het
roept dezelfde code aan. Erop draaien de zeef, de trending-route (#30.6) en
grote controles voor redacties.

**De meetlaag** zit eromheen: de zeef per versie (P1 tot P3, N1, N3, later
video), de kern als releasecheck, en een standaardmodel ernaast (#30.1c).

## De stack

| onderdeel | nu | voorstel | licentie |
|---|---|---|---|
| API | FastAPI | blijft | MIT |
| metadata en bonnetjes | SQLite | blijft: claims, checks, herkomst, labels | publiek domein |
| vectoren | numpy in RAM, blobs in SQLite | een ANN-index op schijf per corpus en modelversie, gekwantiseerd; FAISS of usearch, te kiezen op een meting die de benchmark gelijk houdt | MIT / Apache-2.0 |
| tekst | bge-m3 | blijft voorlopig de eerste stap; opnieuw gemeten op de zeef tegen nieuwere meertalige modellen (`modelmeting`); woorden (BM25) erbij (§108) | MIT |
| rechter | geen (DR8-regels) | **nieuw**: een cross-encoder die we bijtrainen op onze eigen gelabelde paren (zelfde/anders, vetolabels, testparen, minimale paren van Wikipedia, rolwissels), of een klein open taalmodel als rechter; kiezen op de ontwikkelhelft | open gewichten, per model na te gaan |
| NLI | mDeBERTa, alleen offline | blijft offline; voor de feitenbasis eventueel dezelfde rechter | MIT |
| OCR | Tesseract | meten tegen PaddleOCR en een klein open visietaalmodel, op P3 en de meting per schrift (§80) | Apache-2.0 / per model |
| beeld | PDQ, geen index | PDQ plus DINOv2-small (§92), en een beeldindex uit factcheckartikelen (de pilot van #25.11 opgeschaald, alleen de hash en de vector, nooit het beeld) | BSD / Apache-2.0 |
| spraak | geen | **V2**: faster-whisper, lokaal | MIT |
| video | geen | **V2**: ffmpeg plus PySceneDetect voor de frames; in V1 een screenshot van het frame met de bewering | LGPL / BSD-3 |
| taal | py3langid plus `taal.py` | blijft | BSD |
| batch | losse meetscripts | één batchloper met hervatbare porties; uitkomsten in Parquet | Apache-2.0 |
| werkplaats | Claude via de Batch API | blijft, offline op openbare data (B26) | — |
| rekenkracht | de Mac | in fases, zie hieronder: eerst de Mac, de cloud alleen per run; de EU-server van B21 pas bij de livegang | — |

## De zeven engines *(B39)*

*De PO (2026-10-17): om feit van fictie te onderscheiden zijn meerdere engines
nodig, over elkaar gelegd; zo leer je ook hoe nepnieuws iets onwaars
verstopt in iets echts, en zie je steeds subtielere vormen. Aan het ene eind
van het spectrum staat wat vaststaat (encyclopedie, krant van naam, contract,
rechter), aan het andere eind een subtiele duw die geen nepclaim is.*

| engine | wat hij doet | waar in het ontwerp | stand |
|---|---|---|---|
| 1. uitlezen | herkent wat er in een beeld, opmerking of tekst beweerd wordt | laag 2 (OCR, per zin, de vraagvorm); #30.4a | deels gebouwd |
| 2. de bouw van nepnieuws | herkent hoe een bericht vervalst is: een jaartal veranderd, een ontkenning omgedraaid, een feit erbij verzonnen | de minimale paren (§122) als leerstof; de rechter (#30.3) | eerste data |
| 3. sjablonen | herkent terugkerende opmaak van operaties | #27.3, alleen opmaak die een tracker al vastlegde | gepland |
| 4. echt nieuws | herkent wat vaststaat | de feitenbasis (B34); *klopt met bron* | kern van 40 feiten |
| 5. bronnen van echt nieuws | weet welke bronnen een bewering dragen | het register (B34): 111 bronnen, 44 kranten | staat |
| 6. bronnen van nepnieuws | weet welke domeinen en accounts in gepubliceerd onderzoek voorkomen | #27.5, opzoeken met bonnetje (DR10) | gepland |
| 7. de duw | herkent een verhaal dat niet onwaar is maar mensen een richting op duwt | de verschuivingen van standpunt in de minimale paren; #30.10 | eerste data |

Daarbij hoort de **logo- en publicatiecheck** (#30.9): een screenshot met het
logo van een nieuwsorganisatie, nagegaan of die organisatie het bericht echt
publiceerde. Dat is opzoeken, met een bonnetje.

**Elke engine geeft een signaal met zijn bron** (laag 2 van B30), of een
gemeten eigen oordeel onder de poort van B30 (laag 3). `categorize` blijft de
enige plek die de categorie zet (DR4).

**De stijlregel** (DR10, aangevuld): schrijfstijl mag een hulpsignaal zijn
binnen de rechter of een gemeten eigen oordeel, alleen onder de poort van B30
(hoogstens 1 op 10.000 ware stukken met een vals label, per klasse gemeten).
Nooit als losse "dit klinkt als nep"-sticker en nooit om een afzender aan te
wijzen: een operatie die de standpunten van een groep nabootst, klinkt als de
echte aanhang, en wie de operatie op stijl leert herkennen, markeert echte
mensen. Het slimste nepnieuws schrijft bovendien als een krant van naam.

## Rekenkracht: trapsgewijs

*PO 2026-10-17: geen overkill, een solo developer, opschalen in fases en alleen
voor de onderdelen die het nodig hebben.*

**Wat de Mac kan.** Een Apple M1 met 8 kernen en 16 GB. Gemeten op 512 claims:
bge-m3 embedt op de processor (twee kernen, de afspraak tegen oververhitting)
25 teksten per seconde, op de grafische chip (MPS) 54,5, met dezelfde vectoren
(grootste verschil per waarde 0,0000005, laagste cosinus 1,000000). Embedden
mag dus op de grafische chip, zonder gevolgen voor DR6.

**De regel.** Alles op de Mac, behalve een run die langer duurt dan een nacht
of niet in 16 GB past. Die ene run gaat naar de cloud, met een budget dat de
PO vooraf goedkeurt.

| fase | wat | waar | kosten |
|---|---|---|---|
| 0, nu | #30.1b, #30.1c, de zeef met precisie en drukte, #30.2, de vectoren op schijf, de beeldindex, de OCR-vergelijking, de rechter beoordelen | de Mac; #30.1c rekent bij Anthropic | €0, plus het budget voor #30.1c |
| 1, per run | de rechter bijtrainen, als een lichte manier (LoRA) niet op de Mac past | Google Colab: in de browser, GPU per klik, betalen per gebruik | een paar dollar |
| 2, als het loont | heel Wikipedia embedden (ongeveer 40 miljoen passages, 8 à 9 dagen op de Mac); eerst een deelset op de Mac | één dag een spotmachine met GPU bij Google Cloud of AWS; de runs hervatten al waar ze stopten | tientallen dollars |
| 3, later | een miljoen stukken per ronde (OCR op schaal), V2 met video; de livegang | per run een machine met veel kernen; productie op de EU-server (B21) | per run te begroten |

**Opslag.** Cloudflare R2 voor de back-ups van de database en de ijkset; de
eerste 10 GB zijn voor zover bekend gratis, en daar passen we in.

**Geen overkill.** Geen container en geen eigen server zolang we bouwen: een
lijst met vaste pakketversies en vastgezette modelrevisies volstaat, ook in
Colab. Een container komt bij de livegang.

## Snelheid

SPECS E3.S1-AC3 eist minder dan 500 ms. Een rechter op CPU haalt dat niet: NLI
kostte 525 ms per paar (§15), en het voorstel beoordeelt meerdere kandidaten.
Op een GPU kost een rechter voor twintig paren naar verwachting tientallen
milliseconden; dat is nog te meten. Beeld duurt sowieso langer, door de OCR.
Voorstel: de eis per soort artefact. Tekst onder 1 seconde, beeld onder 3
seconden; video in V2, op de achtergrond met een melding als hij klaar is.
*Aangevuld (B41, PO 2026-10-21):* een artikel, een tekst van twee of meer
zinnen waarop de artikellezer leest, krijgt ook 3 seconden. Gemeten op de Mac
p95 2,00 s op 150 artikelen; de server meet het opnieuw (#23.4).

## De volgorde

Geen alles-in-één-keer: elke stap is een release met een verschoven cijfer
(B22).

1. **De rechter (#30.3).** De grootste hefboom voor allebei de lagen van de
   lat. Breed zoeken met een lage drempel, en de rechter beslist. Gemeten op
   de zeef, met precisie en vindkans per emmer van drukte (#30.1c).
2. **De vectoren op schijf.** Een voorwaarde voor de feitenbasis en de
   beeldindex. Bewijs: de benchmark blijft gelijk.
3. **De beeldindex en een betere OCR** (#30.4, eerste deel).
4. **De verhaallaag (#30.2) en de feitenbasis (#30.1b)**, als indexen in
   dezelfde opbouw.
5. **Het batchpad** voor een miljoen stukken (#30.6). Spraak en video
   (#30.4, tweede deel) volgen in V2.

#30.1b (de kern van 300 feiten) en #30.1c (de lat meetbaar, het
standaardmodel) vragen nog niets van deze verbouwing en kunnen eerst.

## De besluiten *(PO 2026-10-17, B35–B38)*

1. **De richting**: vijf lagen, een rechter als tweede stap, indexen op
   schijf, een batchpad dat dezelfde functies gebruikt.
2. **De rekenkracht in fases**: eerst de Mac, de cloud alleen per run die
   langer duurt dan een nacht of niet in 16 GB past, met een budget vooraf;
   de EU-server van B21 pas bij de livegang.
3. **De snelheidseis per soort artefact** (SPECS E3.S1-AC3 herzien).
4. **De volgorde**: de rechter (#30.3) vóór de verhalen (#30.2), want ook "is
   dit hetzelfde verhaal?" is een vraag voor de rechter.
5. **Video en spraak naar V2** (voorstel van de PO, 2026-10-17). In V1 een
   screenshot van het frame met de bewering: op TikTok en Instagram staat die
   meestal als tekst in beeld. Een video-URL krijgt een eerlijk antwoord
   ("Videos aren't supported yet. Upload a screenshot of the frame that shows
   the claim."). Hoe dringend V2 is, zegt later een kleine meting: bevat één
   screenshot de bewering bij vijftig gecheckte video's?

De besloten stack staat in `CLAUDE.md`, met wat nog gebouwd moet worden apart.

## Het platform: de publicatielaag en de site *(B71–B74, PO 2026-11-10)*

Naast de vijf lagen van het aanvraagpad komt er een tweede uitgang: publiceren.
Drie delen, gescheiden door één bestand.

```
  het lab (privé)                      de repo                     de site (openbaar)
  doublecheck.db, metingen,            content/: dossiers,         factiz_site/: een kleine
  modellen, .env                       thema's, trucs,             web-app in Python
        │                              rapporten, per taal         leest alleen, schrijft niets
        │ python -m doublecheck.publiceren        │                        ▲
        ▼                                         │                        │
  publicatie.db  ◄──────────────────────────────┘                        │
  (één bestand per release, alleen lezen) ────────────────────────────────┘
```

- **De inhoud van mensen** staat in `content/`. Een dossier is een map met
  `dossier.toml` (een mens) en `factchecks.json` (de goedkeurstap); het lab
  leest en keurt ze (`doublecheck/dossiers.py`) en zet ze in de
  publicatiedatabase. De site leest `content/` nooit zelf *(#33.6)*.
- **Namen** *(#33.7)* komen niet van een mens maar worden door een mens
  bewaakt: het lab leest ze met een taalmodel, koppelt ze aan een nummer van
  Wikidata en laat alleen door wat vier regels haalt
  (`doublecheck/namen.py`); zonder een nagelezen steekproef en het akkoord
  van de PO komt geen naam in een uitgave, en
  `content/namen-niet.json` is de lijst van wat een mens weghaalde. De site
  kent van een naam alleen het nummer, de soort en de naam in vijf talen.
- **De publicatiedatabase** is het contract. Het lab schrijft haar, de site
  leest haar; geen van beide leent code van de ander. Ze bevat alleen wat
  gepubliceerd mag worden (SPECS E9.S1) en draagt een schemaversie; de site
  weigert een bestand met een ander schema (naar DR6).
- **De site** (`factiz_site/`): Starlette en Jinja2 (beide stonden er al, onder
  FastAPI), pagina's van de server; script mag sinds B75 (van de eigen site, nooit om
  bezoekers te volgen), de pagina blijft leesbaar zonder. Eén module
  spreekt SQL, met vaste vragen en ingevulde waarden. De database gaat
  alleen-lezen en onveranderlijk open. Geen inlog, geen sessie, geen cookie.
- **Zoeken** is de woordzoeker van SQLite (FTS5) in hetzelfde bestand: één
  register op woorden, en één op drietallen van tekens voor schriften zonder
  spaties. Geen Elasticsearch, geen dienst van een derde. Zoeken op betekenis
  over talen heen blijft bij Ask.
- **Talen:** vijf, met Engels op de hoofdmap. Vaste teksten in een woordenlijst
  per taal; labels uit vaste lijsten; de taal en richting van een bewering
  komen uit de database.
- **Beveiliging:** wat er niet is, kan niet gekraakt worden (geen schrijfpad).
  Daarbovenop: een beleid in de kop van elk antwoord dat niets van buiten
  toestaat, tekst uit de database altijd als platte tekst, twee handen vol
  pakketten die er al waren, en op de machine geen sleutels en geen
  privégegevens.
- **Uitrollen** (stap 8, nog te beslissen): de server in de EU van B21. De
  pagina's zonder invoer mogen achter een tussenlaag met voorraad; de zoekroute
  niet achter een Amerikaanse (B21, B73).
- **Niet in dit deel:** de controle per bericht en de resolver. Die blijven de
  dienst van de eerste hoofdstukken; het platform linkt ernaar.
