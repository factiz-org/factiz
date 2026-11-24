# Doublecheck — Design
> Owner: Designer · Status: **APPROVED** 2026-08-27
> Gebaseerd op: REQUIREMENTS.md (APPROVED), SPECS.md

**Reikwijdte.** v1 bouwt alleen een kale testinterface (B3). De richting in §4 en de
uitslagweergave in §2 zijn vooruitgeschreven voor de consumentenschil die later komt —
zodat het antwoordschema er nú op ontworpen wordt en niet achteraf verbogen hoeft.
Elke sectie vermeldt of hij voor v1 geldt of richting is.

## 1. Ontwerpprincipes

Vijf regels die toekomstige discussies beslechten. Elke regel moet een echte
ontwerpkeuze kunnen afwijzen. Een zesde staat op de roadmap, voor later.

1. **Het bewijs is het beeld.** Geen score, geen meter, geen stoplicht. De bronnen
   zijn het grootste element op het scherm. *(volgt uit B10)*
   → Verwerpt: percentagebalken, gauges, cijfers boven de 3rem.
2. **Tellingen, nooit schattingen.** "14 checks, 6 talen, oudste uit 2019" is
   feitelijk en aanklikbaar. Alles wat een berekende waarschijnlijkheid suggereert
   is verboden. *(B10, DR2)*
   → Verwerpt: "zeer waarschijnlijk onwaar", sterbeoordelingen, betrouwbaarheidsbalken.
   *(Sinds B30 één uitzondering: "waarschijnlijk onwaar" als eigen oordeel in
   laag 3, alleen in een klasse die de gemeten poort haalt, met het foutcijfer
   van die klasse erbij; zie §4b. Trappen daarboven blijven verworpen.)*
3. **Rust boven urgentie.** De lezer zit al in een conflict; het scherm voegt geen
   temperatuur toe. Geen waarschuwingsdriehoeken, geen alarmrood, geen uitroeptekens.
   → Verwerpt: rode banners, schudanimaties, "PAS OP"-koppen.
4. **Elke uitslag staat op zichzelf.** Hij wordt doorgestuurd naar iemand die de app
   nooit zag. Zonder context van het vorige scherm moet duidelijk zijn wát er
   gecontroleerd is en door wie.
   → Verwerpt: verwijzingen naar "je vorige check", afkortingen, interne labels.
5. **Onzekerheid krijgt evenveel ontwerpaandacht als zekerheid.** `related` en `none`
   zijn geldige, veelvoorkomende antwoorden — geen foutmeldingen. *(B5: liever vaak
   niets tonen dan één keer verkeerd)*
   → Verwerpt: "niet gevonden" als grijze foutregel; lege staten zonder uitleg.
6. **De bewering is het onderwerp, nooit de maker.** *(roadmap, voor later; PO
   2026-10-13: "voor nu nog te far fetched"; PLAN #26.5, #27.5)* Elke zin in een uitslag gaat over de
   bewering: "Dat 5G corona veroorzaakt: 14 redacties, onwaar." Over de post,
   de grap of de bedoeling van wie hem maakte zeggen we niets. Een meme, satire
   of sarcasme krijgt hetzelfde antwoord als de kale bewering eronder; lacht de
   meme die bewering uit, dan staat het antwoord aan de kant van de maker, en
   verspreidt hij haar, dan krijgt de lezer de bron. Een grap zonder toetsbare
   bewering krijgt stilte (`none`). Noemt een redactie iets zelf satire, dan
   staat er satire, op geen kant van de schaal. Over een afzender alleen wat
   een ander publiceerde, als bonnetje met bron en datum: "Dit account komt
   voor in onderzoek van [bron], [datum]", nooit "Russisch account" als onze
   eigen uitspraak. *(DR2, DR10)*
   → Verwerpt: "Deze meme is misleidend", "Let op: satire", een
   satiredetector, "verdacht account", een afzenderscore, een afzender
   afgeleid uit stijl of standpunt.

## 2. Gebruikersstromen

### Stroom A — Kernlus: artefact → uitslag *(v1: kaal; richting voor later)*
1. Gebruiker levert artefact aan (plakken, kiezen, of URL)
2. Systeem toont dat het bezig is, met welke stap — niet een anonieme spinner
3. Uitslag verschijnt in één van vier vormen:
   - **`matched`** — kop met de telling ("Weerlegd door 14 factcheckers"), daaronder
     de checks als lijst: uitgever, oordeel, datum, taal, link
   - **`related`** — expliciet benoemd wát overeenkomt ("Dezelfde foto, andere
     bewering"), met de gerelateerde check eronder
   - **`assessed`** — *(niet in v1)* visueel duidelijk andere behandeling dan
     `matched`; nooit dezelfde koptypografie *(DR5)*
   - **`none`** — uitleg dat er niets gevonden is, wat dat wél en niet betekent,
     en één vervolgactie

Randgevallen: onleesbaar artefact, te groot bestand, lege index, netwerkfout — elk
met eigen tekst, nooit teruggevallen op `none`.

### Stroom B — Delen *(richting)*
1. Gebruiker deelt de uitslag als link
2. Link toont in WhatsApp/X/Signal een leesbare previewkaart: de telling, het oordeel,
   en de naam van minstens één uitgever
3. Ontvanger opent de link en ziet dezelfde uitslag, altijd actueel

### Stroom C — Betwisten *(richting, hoort bij E6.S3)*
1. Gebruiker vindt de uitslag onjuist en start een betwisting
2. Systeem vraagt expliciet toestemming om het artefact te bewaren voor foutanalyse,
   met uitleg wat er bewaard wordt en hoe lang *(B11)*
3. Zonder toestemming gaat de betwisting door met alleen de fingerprint

## 3. Schermoverzicht

| # | Scherm | Doel | Epic | In v1? |
|---|--------|------|------|--------|
| S1 | Invoer | Artefact aanleveren (tekst, beeld, URL) | E5 | ja — kaal |
| S2 | Bezig | Tonen welke stap loopt | E5 | ja — kaal |
| S3 | Uitslag `matched` | Bewijstoestand tonen | E3, E5 | ja — ruwe respons |
| S4 | Uitslag `related` | Benoemen wát overeenkomt | E3, E5 | ja — ruwe respons |
| S5 | Uitslag `none` | Uitleggen wat "niet gevonden" betekent | E3, E5 | ja — ruwe respons |
| S6 | Foutstaten | Onleesbaar / te groot / netwerk | E5 | ja — kaal |
| S7 | Previewkaart (OG) | Losstaande leesbaarheid bij delen | — | nee — richting |
| S8 | Betwisting + toestemming | Foutanalyse met expliciete opt-in | E6 | nee — richting |

## 4. Look & feel — richting

- **Toon:** neutraal en zakelijk. Als een laboratoriumuitslag: hier is wat gevonden
  is, oordeel zelf. Geen bijvoeglijke naamwoorden die het oordeel kleuren.
- **Referentie:** Apple Health / Ōura — kalme datapresentatie, veel wit, hoogwaardig
  gemaakt. **Maar zonder de merkwarmte van die producten:** geen gradiënten, geen
  illustraties, geen persoonlijkheid. De verzorging moet lezen als *zorgvuldig
  gemaakt*, niet als *gemarket*. Een standaard mag geen agenda uitstralen.
- **Tegenpool:** alles wat op een dashboard met scores lijkt, en alles wat op
  campagnemateriaal lijkt.
- **Kleur:** terughoudend. **Rood/groen mag nooit de primaire drager van betekenis
  zijn** — het is een stoplicht en dus een verkapte score *(principe 1)*, en het
  faalt bij kleurenblindheid. Kleur alleen als rustig accent om categorieën te
  onderscheiden; de betekenis staat in de tekst.
- **Typografie:** precies en leesbaar op klein formaat — de previewkaart is soms de
  enige vorm waarin iemand de uitslag ziet. Eén tekstfamilie, duidelijke hiërarchie.
- **Dichtheid & beweging:** laag. Eén uitslag per scherm. Beweging alleen om een
  toestandsovergang te verduidelijken, nooit decoratief.
- **Licht/donker:** beide, vanaf het begin.
- **Conventies:** standaard webpatronen; geen eigen bedachte interactiemodellen.
- **De marketingsite** *(besloten door PO 2026-10-27, §4h)*: factiz.org krijgt een
  eigen look met beelden en filmkorrel. Die look is voor de schil, nooit voor
  de uitslag: wat hierboven staat blijft gelden voor elke uitslag, elk label,
  elke bonnetjeslijst en de meter.

### 4a. De marketingdemo *(PO 2026-10-04, bij etappe 22)*

De publieksdemo op try.factiz.org is sinds de launchvoorbereiding ook een
marketingoppervlak, en dat verdraagt zich met §4 door een scheiding in twee
lagen:

- **De schil mag uitnodigen.** Merkstijl (papier, serif-display, groen met
  oranje als actiekleur), een dropzone die slepen, kiezen én plakken
  accepteert, voorbeeldchips, en een statistiekregel met echte
  corpuscijfers uit het discovery-endpoint. Dit is de etalage.
  *(Besloten 2026-10-27, §4h: de schil krijgt de nieuwe look van de site:
  dunne schreefloze koppen, een smalle band met een veld bovenaan, knoppen
  in wit en donker; oranje wordt markeerkleur en de serif blijft alleen voor
  de bewering.)*
- **De uitslagkaart blijft §4.** Binnen de schil is het antwoord nog steeds
  de laboratoriumuitslag: tellingen, bronnen als grootste element, eigen
  tekst per staat, geen kleur als oordeelsdrager. Alle D-checks gelden
  onverkort; DR2/DR3 veranderen niet.
- **Chips zijn gemeten.** Een voorbeeldchip staat er alleen als de claim op
  het echte corpus `matched` oplevert, met de meting erbij in de code. Een
  demo die haar eigen voorbeelden niet waarmaakt is een anti-demo, en de
  marketingsite mag geen chip tonen die de demo niet kan inlossen.
- **Het artefact blijft lokaal.** Slepen of plakken toont een preview via
  een object-URL in de browser; het beeld gaat uitsluitend naar déze
  resolver, en de pagina zegt dat hardop.
- **Eén site, twee hosts** *(PO 2026-10-15)*. De bezoeker merkt de grens
  tussen factiz.org en try.factiz.org niet: elke pagina linkt naar de
  hoofdpagina's van beide kanten (kop en voet), de merknaam leidt naar
  factiz.org, en geen link wijst naar iets dat niet bestaat
  (`tests/test_sitelinks.py`). Navigatie naar de eigen site laadt niets;
  van buiten laden blijft verboden.

### 4b. Het labeltje *(B23, akte 2; PO 2026-10-10)*

De consumentenschil uit B12 wordt een badge in de tijdlijn, op de plek waar de
leugen staat. Drie regels, uit te werken in #24.1:

- **Het label zegt helder wat bekend is, en uit welke laag.** *(Aangepast door
  B25.)* Symmetrisch: "Bekend als onwaar · 3 redacties, 2 talen" en
  "Bevestigd · 2 redacties". Een schaal van bevestigd tot bekend als onwaar
  mag, met de laag erbij (bekend, signaal, eigen oordeel) en woorden die de
  positie benoemen; nooit "100%", nooit een kaal percentage, nooit een kleur
  als enige drager, kleuren kleurenblind-veilig (D1, DR2, §4). Een eigen
  oordeel verschijnt alleen waar de meting het draagt; elders "nog niet
  genoeg bekend".
  *De labels (B30, PO 2026-10-14):*

  | label | wie zegt het |
  |---|---|
  | Bekend als onwaar | redacties, met bonnetjes (laag 1) |
  | Omstreden | redacties die elkaar tegenspreken (laag 1) |
  | Bekend als waar | redacties, met bonnetjes (laag 1) |
  | Deels waar | redacties, met bonnetjes (laag 1; PO 2026-10-14) |
  | Lijkt op een bekende misleiding | signaal, met de bron (laag 2) |
  | Klopt met bron | signaal, met de bron (laag 2) |
  | Waarschijnlijk onwaar | Factiz, machinaal, alleen in een klasse die de poort van 1 op 10.000 haalt (laag 3) |
  | Wordt beoordeeld | stand: in de wachtrij bij redacties |
  | Onzeker | stand: er is iets, maar te weinig voor een oordeel |
  | Niets bekend | stand: geen treffer |

  Een machinaal label draagt het foutcijfer van zijn klasse, nooit een
  percentage voor dit ene bericht, en ziet er nooit uit als een check van
  een redactie (DR5). Het antwoord wijst aan welk deel van het artefact de
  treffer gaf.
- **Stilte bij `none`.** Het label verschijnt alleen als het geheugen iets
  weet. Geen "unverified"-badge op elke post: dan lijkt alles verdacht en
  betekent het label niets meer. Afwezigheid zegt niets, en dat staat
  uitgelegd waar de gebruiker het instelt.
- **De bonnetjes zijn altijd één klik weg.** Het label is de oppervlakte; de
  redacties, met datum, taal en link, zijn het oordeel (D2).

### 4c. Het label in de tijdlijn, uitgewerkt *(#24.1, 2026-10-14)*

De drie regels van §4b, uitgewerkt tot staten en stromen voor de extensie
(#24.3). Schermontwerp: `docs/ontwerp/label.html` (alle staten, beide
kleurmodi, toetsenbord). De naam van het label volgt uit de naamsessie vóór
#24.3; tot dan staat er het merk.

**Twee manieren waarop een label ontstaat.**

1. **Lokaal, zonder netwerk.** De claimfilter (#24.2) kent alleen hashes: geen
   telling en geen claimtekst. Een treffer op de **hele tekst** van een claim
   toont de kant al (*Known to be misleading · Show receipts*), want de filter
   draagt die kant voor zulke sleutels (PO 2026-10-14, #24.2c). Een treffer op
   een **losse zin** geeft een neutraal label, *Fact-checked before*, met
   *Show receipts*. Pas de klik
   stuurt de posttekst naar de resolver (DR3: niets verlaat het apparaat
   zonder klik), en pas als die `matched` zegt, wordt het label het oordeel
   met de telling. Zegt de resolver iets anders, dan verdwijnt het label en
   volgt de regel van stroom 2. Twijfel versoepelt nooit: de filter raakt ook
   op losse zinnen van 40 tekens of meer, en zo'n zin kan bij een andere
   bewering horen.
2. **Op verzoek.** Elke post krijgt in zijn menu *Check with Factiz*. Dat
   stuurt de tekst naar de resolver; het antwoord komt onder de post.

**De staten.**

| antwoord | wat de lezer ziet | blijft het staan? |
|---|---|---|
| geen lokale treffer, geen verzoek | niets | n.v.t. |
| lokale treffer op de hele tekst | de kant zonder telling: *Known to be misleading · Show receipts* | ja |
| lokale treffer op een losse zin | *Fact-checked before · Show receipts* (neutraal, geen kant) | ja |
| `matched` | het oordeel als label, met de telling: *Known to be false · 3 newsrooms, 2 languages* | ja |
| `related` | *A related claim was checked · See what matched*; de lade noemt wát overeenkomt en zegt dat het niet dezelfde bewering is; geen oordeel in het label (B8) | ja |
| `none`, op verzoek | geen label, een regel onder de post met de reden (#25.35) en *Dismiss*; weg bij herladen | nee |
| fout of te veel verzoeken | een regel: *Could not check right now*; nooit teruggevallen op `none` (D7) | nee |

**Van oordeel naar labeltekst (laag 1).** Het label noemt de kant, in woorden
die het oordeel van de redacties niet aanscherpen:

| oordelen van de redacties | label |
|---|---|
| alleen onwaar | *Known to be false* |
| alleen misleidend | *Known to be misleading* |
| onwaar en misleidend | *Known to be false or misleading* |
| alleen waar | *Known to be true* |
| alleen deels waar | *Partly true* |
| oordelen op verschillende kanten (waar en onwaar, onwaar en deels waar) | *Disputed by fact-checkers* |
| alleen satire | *Satire, according to fact-checkers* (op geen kant, principe 6) |
| alleen onbewezen | *Unproven, according to fact-checkers* |
| geen genormaliseerd oordeel | *Fact-checked* |

**Jongste oordeel voorop** *(PO 2026-10-15)*. Verschuift het oordeel over de
jaren, dan zegt het label het oordeel van het jongste jaar, en de regel eronder
wat er eerder gezegd werd: *Unproven, according to fact-checkers (2025)* met
*Earlier: known to be false (2020)*. Daar telt *onbewezen* als positie; in één
jaar tegenstrijdig blijft *Disputed by fact-checkers*. De bonnetjes staan van
nieuw naar oud.

Een oordeel zonder kant (onbekend, onbewezen, satire) telt verder niet mee zolang er
een check mét kant is: drie redacties met misleidend, misleidend en een
oordeel dat niet te normaliseren was, heten *Known to be misleading*. De demo
gebruikt dezelfde woorden (PO 2026-10-14). Daarachter altijd de telling: *3 newsrooms, 2 languages*. Nooit een
percentage, nooit "100%" (DR2).

**De lade (bonnetjes, D2).** Eén klik op het label opent haar; *Esc* sluit
haar en zet de focus terug op het label. Van boven naar beneden: de bewering
zoals ze gecheckt is; de labelregel; de checks als grootste blok (uitgever,
oordeel in hun eigen woorden, datum, taal, link, en bij een dode link *Source
offline since at least … · Archived copy*, #25.9); de geschiedenis
(attributies, *Went round on X, 15 March 2025*); onderaan *The sources are
the verdict*, *Wrong match? Tell us* (de betwistingsroute, B11) en *How labels
work*. Een lade staat op zichzelf (D4): wie haar doorstuurt, ziet wát er
gecheckt is en door wie.

**De drie lagen, ook in grijs te onderscheiden (D5).** Laag 1 (redacties): een
pil met een doorgetrokken rand. Laag 2 (signalen): een gestippelde rand en het
voorvoegsel *Signal:*, met de bron in de tekst (*Signal: looks like a known
hoax · AFP, 2019*). Laag 3 (eigen oordeel): rechte hoeken en het voorvoegsel
*Factiz estimate:*, met het foutcijfer van de klasse (*error rate at most 1 in
10,000 in this class*). Laag 2 en 3 zijn ontworpen maar niet in v1: er komt
nog geen signaal uit de motor, en geen klasse haalt de poort van B30. De vorm
staat nu vast zodat laag 3 nooit op een check van een redactie kan lijken
(DR5).

**Laag 3 wordt het hoofdspoor (B42, 2026-10-23).** De oordelaar (de leerling)
gaat per klasse aan zodra die de poort van B30 haalt; tot dan blijft de vorm
hierboven ongebruikt. *Voorstel, nog niet akkoord:* onder een eigen oordeel
staat altijd wat Factiz las, in één regel (*Factiz read: "Photo shows floods
in Chennai in 2015"*), zodat de lezer ziet waar het oordeel op rust (B25) en
een verkeerde lezing meteen opvalt. Geen tweede regel met een reden in eigen
woorden: een reden die overtuigend klinkt, kan een fout oordeel dragen; de
bonnetjes van laag 1 blijven het enige uitgebreide bewijs.

**Instellingen.** *Show labels* (aan), *Match on this device* (aan; alleen
hashes, niets verlaat het apparaat), en geen telemetrie. Bovenaan de uitleg
van de stilte: *No label means nothing. Most claims are never checked, so the
absence of a label says nothing about a post.*

**Toegankelijkheid.** Het label is een knop met de volledige tekst als naam;
de lade is een dialoog met een kop, focus erin, *Esc* eruit, focus terug.
Het raakvlak is minstens 44×44 px, ook als de pil kleiner oogt. Kleur draagt
nooit alleen: de kant staat in woorden, de laag in rand en voorvoegsel.

**Besloten door de PO (2026-10-14, "eens met alle drie").** (1) De filter
draagt de kant voor een treffer op de hele tekst; het label zegt die kant
zonder netwerk, de telling blijft een klik (#24.2c). (2) De demo zegt
dezelfde woorden als het label (*Known to be true*, *Disputed by
fact-checkers*). (3) *Partly true* is een eigen label in laag 1.

### 4d. De claimkaart: één object, drie oppervlakken *(B31, PO 2026-10-15)*

Eén kaart per bewering, overal dezelfde: op de claimpagina's (#24.9), in Ask
Factiz (#24.10) en als insteekkaart naast een artikel van een redactie
(#24.11). Van boven naar beneden:

1. **De bewering** zoals redacties haar checkten.
2. **Het label** met de telling (§4c): *Known to be false · 4 newsrooms, 3
   languages, 2018–2023*.
3. **Eén uitlegzin**, alleen als die de poort van B31 haalt, en met de
   herkomst erbij: de eigen woorden van een redactie (met naam), of
   *Summary of what fact-checkers found*. Geen zin, dan staat er niets en
   gaat de kaart door naar de bonnetjes.
4. **De bonnetjes**, de grootste blok (D2): redactie, oordeel in hun eigen
   woorden, datum, taal, link, en een archiefkopie als de bron verdween.
5. **Onderaan** *The sources are the verdict* en *Wrong? Tell us*.

De kaart staat op zichzelf (D4): wie haar los ziet, naast een artikel of
doorgestuurd, ziet wát er gecheckt is en door wie. Ze volgt geen lezers: de
insteekkaart is óf een stukje HTML dat de redactie zelf plakt, óf een kaart
zonder cookies en zonder logs. Nooit een kaal ja of nee: de zin geeft de
nuance zoals de redacties haar gaven ("het lab bestaat; dat er biowapens
worden gemaakt, is onwaar").

### 4e. Ask Factiz *(#24.10, PO 2026-10-15)*

Een vraag in gewone woorden, en terug de gecheckte beweringen die er het
dichtst bij liggen, elk als claimkaart (§4d). Op try.factiz.org/ask, in
dezelfde schil als de demo (§4a). Vier regels:

- **Het oordeel hoort bij de bewering, niet bij de vraag.** Elke kaart begint
  met de bewering zoals redacties haar checkten, dan het label. Nergens een
  ja of nee op de vraag: wie vraagt "Is corona uit een lab ontsnapt?" ziet
  welke beweringen daarover gecheckt zijn en wat redacties vonden.
- **Nabijheid in woorden, uit de categoriseringsfunctie.** Boven elke kaart
  *Close to your question* (`matched`) of *Related to your question*
  (`related`). Nooit een score.
- **Stilte boven gissen.** Ligt niets boven de verwantdrempel, dan zegt de
  pagina dat, met de reden, zoals bij `none` in de demo. Geen "dichtstbijzijnde
  toch maar" eronder.
- **Gemeten voorbeelden, gemeten cijfer.** Voorbeeldvragen alleen uit de
  testset en alleen als ze daar de juiste bewering tonen (§4a). Het cijfer van
  de testset staat op de pagina met de opzet erbij, ook hoeveel vragen niets
  kregen.

*Eén antwoord in plaats van losse kaarten (PO 2026-10-15, variant B van
`docs/ontwerp/ask.html`).* Losse kaarten werken niet bij meer dan een paar
treffers. Daarom:

- **Bovenaan een regel met tellingen**: hoeveel beweringen, redacties, talen
  en jaren. Geen oordeel.
- **Dan de samenvatting van de oordelen, alleen als die klopt.** Alle
  beoordeelde checks op dezelfde kant: *All 4 rated checks found these claims
  false or misleading*, met een check zonder oordeel in haar eigen woorden
  erbij. Spreken twee getoonde beweringen elkaar tegen ("vaccines cause
  autism" en "vaccines do not cause autism"), dan geen samenvatting maar de
  reden: *No summary: these claims do not all say the same thing*, met de
  tegengestelde bewering en haar oordeel. Bij één bewering geen samenvatting.
  De samenvatting gaat over de beweringen, nooit over de vraag.
- **Per bewering één compacte regel** (label, bewering, redacties, jaren)
  die openklapt naar de bonnetjes. Geen samenvoegen op gelijkenis: dat
  verstopt nuance ("Labs, yes. Weapons, no") en kan een ontkenning bij haar
  tegendeel schuiven.
- **Een check zonder oordeel** toont de eigen woorden van de redactie (route 1
  van B31) in plaats van een kaal *Fact-checked*.
- **Vertaald, met het origineel** (B32): de bewering in de taal van de
  pagina, *Machine translation from <taal>* en het origineel eronder; het
  oordeel van de redactie met zijn betekenis ernaast (*Yanlış (false)*).
- **Niets gevonden is geen doodlopend eind**: *Send it to a fact-checker*,
  met tiplijnen van redacties in de taal van de vraag, uit de registers van
  IFCN en EFCSN, met bron en datum.

### 4f. De waarheidsmeter *(B44, besloten door PO 2026-10-26; PLAN #31.9)*

De wens van de PO (2026-10-26): een screenshot inslepen en een stand zien op een
meter van groen naar rood, met woorden als *zeer waarschijnlijk onwaar*, net
als Pangram nooit 100%.

**De meter.** Een horizontale schaal met negen streepjes en twee uiteinden.
- *De streepjes 1 tot 9:* de naald staat in V1 op een van vijf standen (1, 3,
  5, 7, 9), na de ijkronde op elk streepje.
- *De uiteinden 0 en 10* zijn alleen voor de feitenbasis (B34): *In strijd met
  een vastgesteld feit* (helemaal rood) en *Vastgesteld feit* (helemaal
  groen), in woorden, nooit als "100%". Onder een uiteinde staan de bronnen
  van het feit (minstens vier, van minstens twee soorten) en een link naar de
  openbare regel. Een gemeten stand komt nooit op een uiteinde.
- *In V1 alleen het groene uiteinde* (PO 2026-10-26, BENCHMARK §154).
  - *Vastgesteld feit* (10) staat open voor de 40 kernfeiten.
  - *In strijd met een vastgesteld feit* (0) is dicht. De naald staat nooit
    helemaal rood; een bericht dat een vastgesteld feit tegenspreekt staat
    op de gemeten stand.

**Wat er in één oogopslag staat, van boven naar onder:**
1. *Wat Factiz las:* de bewering, zoals uit het beeld gehaald (DR5, D4).
2. *De meter* met de woorden van de stand eronder, groot.
3. *De laag*, even groot als de woorden. Bijvoorbeeld:
   - *Established fact: 4 independent sources* (de feitenbasis, alleen bij 0
     en 10);
   - *Checked by fact-checkers* (laag 1, met het aantal redacties);
   - *Found on the web, not checked by a fact-checker* (laag 2);
   - *No source found*.
4. *Waarom deze stand:* één regel met het gemeten aandeel. Voorbeeld: *Of
   messages with this result, 2 in 100 turned out to be true*.
5. *De bonnetjes* (D2): de check van de redactie of de geciteerde bronnen,
   met link. Bij laag 1 is dit het grootste blok.

**Kleur.** De schaal loopt van groen naar rood, met een groot verschil in
lichtheid tussen de uiteinden, zodat ze in grijs en bij kleurenblindheid te
onderscheiden blijven (D5). De woorden en de positie dragen de betekenis,
nooit de kleur alleen (§5). Geen rode banner, driehoek of uitroepteken (D6):
het rood zit alleen in de schaal.

**Standen zonder oordeel.** *Onzeker* staat in het midden, met de reden:
- *Nothing decisive found*;
- *Sources disagree*;
- *Not checked yet*.

*Geen bewering* (een groet, een mening) toont geen meter maar één regel.

**Wat de meter nooit doet:**
- een los percentage als waarheid ("73% waar");
- een stand voorbij 3 of 7 zonder check van een redactie, tenzij de ijkronde
  die soort bewering vrijgaf;
- een uiteinde (0 of 10) zonder feit uit de feitenbasis;
- tegen het oordeel in wijzen;
- een eigen oordeel van het model laten lijken op een check van een redactie
  (DR5).

### 4g. De controlepagina op try.factiz.org *(B45, ronde 3; PLAN #31.13)*

De vraag van de PO (2026-10-27): "op try.factiz.org de schaal van 0 tot 10,
het oordeel in woorden en de bronnen, en op factiz.org hoe we met privacy
omgaan."

**Waar.** `try.factiz.org/check`, naast Ask. Het menu ("Check a claim") wijst
nog naar de demo van de resolver, tot de beta opengaat (ronde 7). Tot dan
staat de controle uit (B43), en zegt de pagina dat eerlijk.

**Van boven naar onder:**
1. *Het invoerveld:* tekst plakken of een screenshot kiezen, en één knop
   *Check*. Ernaast de korte privacyversie: het screenshot wordt op onze
   server in de EU gelezen en niet bewaard; namen, nummers en adressen gaan
   eruit; alleen de rest van de tekst gaat voor deze ene controle naar het
   model van Anthropic in de VS, dat haar hoogstens 30 dagen bewaart en er
   niet op traint (B54, PO 2026-11-03; eerst stond hier "wordt daar niet
   bewaard", dat gold alleen onder zero data retention). Met een link naar
   de privacypagina. *Met het beeld aan (B55):* bij het kiezen van een
   screenshot één zin, geen knop: "Factiz sends your screenshot to
   Anthropic's model for this check; Anthropic keeps it for at most 30 days
   and does not train on it." Wat de tekstherkenning als persoonsgegeven
   vindt (nummers, e-mailadressen, handles, de naam van een groep of
   afzender), is dan al zwart.
2. *Wat Factiz las:* de tekst zoals die naar het model ging, dus gemaskeerd,
   ingeklapt. Daaronder *Claim checked:* de bewering die het model
   beoordeelde (DR5, D4).
3. *De meter* van §4f: een schaal van 0 tot 10, met de naald op de stand en
   de woorden groot eronder:
   - 0 *Contradicts an established fact* (dicht in V1);
   - 1 *Very likely false*;
   - 3 *Likely false*;
   - 5 *Uncertain*;
   - 7 *Likely true*;
   - 9 *Very likely true*;
   - 10 *Established fact*.
4. *De laag*, even groot als de woorden, met de teksten van §4f.
5. *Waarom deze stand:* één regel.
   - Bij een gemeten stand het aandeel uit de ijking: *Of messages with this
     result, 2 in 100 turned out to be true.*
   - Bij een klasse met te weinig metingen: *Too few measured messages with
     this result to say more.*
   - Bij *onzeker*: *Nothing decisive found.*
   - Bij 10: het feit zelf en zijn bronnen, met een link naar de lijst met
     vastgestelde feiten.
6. *De bonnetjes* (D2):
   - een check van een redactie met redactie, oordeel, datum en link;
   - een bron van het web met titel, de geciteerde passage en link.
   Bij laag 1 is dit het grootste blok.

**Geen meter** bij *geen bewering* en bij *satire* ("This looks like satire.").

**§4l *Niet bevestigd* (B57)** — de eerlijke middelste uitkomst voor wat
betrouwbare media zouden melden als het waar was, maar niemand betrouwbaars
meldt:
- kop: *Not confirmed*;
- zin: "No reliable source reports this." en daaronder "Factiz searched for:"
  met de zoekvragen, elk met wat ze vonden (de bonnetjes van wat er níét is);
- geen rood, oranje of groen; een neutrale markering, zodat het nooit leest als
  een oordeel;
- nooit bij *geen bewering*, *satire* of een bericht over een bewering van een
  ander.

*Geen bewering* zegt wat Factiz vond, niet wat het bericht is *(PO 2026-11-03,
na BENCHMARK §209: 13 van 58 screenshots van bekend nepnieuws met onleesbare
tekst kregen deze uitkomst)*:
- kop: *No checkable claim found*;
- bij tekst: "Factiz found no checkable claim in this message.";
- bij een screenshot: "Factiz found no checkable claim in the text it could
  read from this screenshot. The photo itself may still make one, and Factiz
  does not look at photos yet." *Wat Factiz las* staat dan open, zodat de
  gebruiker ziet hoe weinig er te lezen was.

Nooit "This message makes no checkable claim": bij een screenshot kan de
bewering in de foto zitten, of in tekst die de OCR niet las.

**De twee regels** *(ronde 5, PLAN #31.15, BENCHMARK §159)*:
- *Een bericht over een bewering van een ander* (een factcheck, een
  nieuwsbericht over wat iemand zegt of beschuldigt, een vraag "is dit
  waar?"): boven de meter "This message reports on a claim made by someone
  else. That claim is:", daaronder de meter, de woorden en de bronnen zoals
  altijd. De meter gaat over die bewering; het bericht zelf krijgt geen rood
  of groen.
- *Een bewering over wat een beeld toont* die anders *klopt* of groen zou
  zijn: *Uncertain* (5), met als regel bij *Waarom deze stand* "Factiz cannot
  see the image or video this claim is about." Rood blijft rood.

**Geen uitlegzin van het model.** De regel UITLEG van de machine is niet gemeten
op trouw aan de bonnetjes (B31), en is Nederlands. Hij staat alleen in het
ruwe antwoord voor ontwikkelaars.

**Foutstaten** (D7), elk met eigen tekst:
- *De controle staat uit:* "Checking messages opens with the beta. Nothing
  you enter here is sent anywhere yet."
- *Geen tekst in het beeld:* "Factiz found no text in this image. Version 1
  reads the text in screenshots; photos without text are not checked yet."
- *Te groot:* "This image is larger than 8 MB."
- *Het dagplafond:* "Today's checks are used up. Try again tomorrow."
- *Het model onbereikbaar:* "The check cannot reach its model right now. Try
  again in a minute."

**Zoals Ask:** de pagina bouwt nooit HTML uit een string, de invoer gaat met
POST in de body (DR3), en onder de uitslag staat *Wrong? Tell us* zodra de
betwistingsroute de controle kent (ronde 6).

### 4h. De nieuwe look van de site *(besloten door PO 2026-10-27: "Akkoord met het plan."; PLAN #23.14)*

De vraag van de PO (2026-10-27): "IK wil de marketing site iets meer als een
frontier lab laten uitzien. Moderner en subtieler en meer 'organisch
technologisch'." Voorbeelden: labelbox.com (warm papier, grote dunne koppen,
haarlijnen, kleine mono-labels), attio.com (raster, het product voorop),
wonderful.ai (kleurvelden die met beweging gefotografeerd lijken, met
filmkorrel; witte pilknoppen) en de voet van voicelabs.dental (een
halfdoorzichtige kaart op een wazig beeld). Daarbij de PO: "in de visual een
analoge, grainy look".

**Gekozen in de vraagronde (2026-10-27).** Uit een schets met drie richtingen
(A donker, B licht met velden, C raster; lokaal in `data/look/`, niet in git)
koos de PO B ("B is top!"). Verder, alle drie zoals aangeraden: de letter van
het apparaat, alleen abstracte beelden, knoppen in wit en donker.

**Richting B: licht, met velden als beelden.** Papier is de grond (in donker:
nacht). De velden zijn beelden, geen achtergrondkleur: ze zijn in licht en
donker gelijk. Ze staan op vier plekken en nergens anders:
1. bovenaan elke pagina: op de homepage op volle breedte, op de andere
   pagina's een lagere band met de kop erin;
2. de drie ingangen (*Check a claim*, *Ask a question*, *The numbers*) als
   kaarten met afgeronde hoeken, elk op een eigen veld;
3. de voet: een veld met daarop een afgeronde, halfdoorzichtige kaart met de
   links;
4. de afbeelding bovenaan een blogpost.
De tekstsecties ertussen zijn rustig: haarlijnen, kleine mono-labels in groen,
veel ruimte, de tabellen zoals nu.

**Letter.** De letter die al op het apparaat staat: SF Pro op Apple, Segoe UI
op Windows, Roboto op Android. Er wordt niets geladen, dus de beveiligings-
instellingen van de site blijven dicht. Koppen dun (300) en krap gespatieerd
(-0,035em), de grootste tot ~4rem; lopende tekst normaal (400); mono voor de
labels. **De serif alleen voor wat een ander zei**: de bewering en citaten.
Wat Factiz zelf zegt, staat in de schreefloze.

**Kleur** (contrast nagerekend 2026-10-27, WCAG):

| rol | licht | donker | contrast |
|---|---|---|---|
| papier (grond) | `#f3efe8` | `#141517` | |
| inkt (tekst) | `#1d1b18` | `#ecebe8` | 15,0 / 15,3 |
| zacht (bijtekst) | `#6b665e` | `#a5a199` | 5,0 / 7,1 |
| groen (merk, labels) | `#0b6b47` | `#7fd1ae` | 5,7 / 10,1 |
| haarlijn | `#ddd6ca` | `#2b2d31` | versiering |

- **Knoppen zijn pillen.** Op een veld wit met donkere tekst, of een witte
  rand; op papier donker met lichte tekst, of een rand. In donker omgekeerd.
- **Groen blijft het merk**: de labels, de links. De punt achter Factiz is sinds 2026-11-09 vervangen door het logo
  (hieronder).
- **Het logo** *(PO 2026-11-09: "Ik geef je ook het nieuwe logo en logo + text als svg, ook voor site icon, OG
  images, avatar, main menu etc.", PLAN #23.18)*. Het logo is een oranje vierkant (`#FF5900`) met afgeronde hoeken
  en drie witte ovalen. Het woordmerk is het logo met "factiz" erachter.
  - *De bron:* de bestanden van de PO in `web/public/merk/` (`logo.svg`, `woordmerk.svg`).
  - *Kop en voet:* het woordmerk, inline. Het oranje en wit van het logo staan vast; de letters volgen de tekst
    (`currentColor`): inkt op papier, wit op een veld en in donker. Er is één bron voor de site, de tijdelijke site
    en try.factiz.org: `web/src/data/woordmerk.svg`.
  - *Het icoon van de site* is het logo (`favicon.svg`). Er zijn ook `favicon.ico` en `apple-touch-icon.png`, op
    het volle vierkant, want iOS rondt de hoeken zelf af.
  - *De avatar* (`merk/avatar.png`, 1024×1024) heeft het volle oranje vierkant. De ovalen blijven binnen een
    cirkel, dus een ronde uitsnede snijdt niets af.
  - *Het beeld bij delen* (`merk/og.jpg`, 1200×630) is de uitsnede van corpus met het woordmerk erop, in wit.
  - Alle beelden komen uit één script, `python -m doublecheck.merkbeelden`, dat de vormen uit de SVG zelf tekent.
    Er is geen download nodig, en hetzelfde commando geeft hetzelfde beeld.
  - *Oranje* staat alleen in het logo. Of de groene labels en links oranje worden, beslist de PO.
- **Oranje is geen knopkleur meer.** Het blijft als markeerkleur waar iets
  verschilt (de bits in *How it works*), in de donkere tint `#d85a1f`, die
  3,4:1 haalt op papier (de huidige `#ee6a2a` haalt 2,7).
- **De focusrand** in groen op papier (3,8:1) en in wit op een veld.
- **Rood** alleen in de schaal van de meter (D6); nooit in een veld.

**De beelden (velden).** Gemaakt door een eigen script, `python -m
doublecheck.velden`, naar het voorbeeld van `motorkap`. Geen beeldmodel, geen
stock, geen download, geen licentie; geen gezichten, geen symbolen, geen rood.
- *Hoe:* lichtstrepen opgeteld als licht, lang vervaagd in de
  bewegingsrichting met een zachte gloed eromheen, licht vervormd zodat het
  organisch oogt. Dan het filmkarakter: zwart is nooit zwart, wit brandt zacht
  af, een warme gloed lekt rond het felste licht, de hoeken zakken weg, en de
  korrel zit het sterkst in de middentonen, in klonten van twee groottes.
- *Zes velden, elk met een vaste seed*, zodat hetzelfde commando hetzelfde
  beeld geeft: nacht (blauw en wit op bijna zwart), groen (mint op groen-zwart,
  het merk), hemel (hemelsblauw met wolkvegen), olijf (olijfgroen met goud),
  leisteen (grijze vegen als wind over water) en corpus.
- *Corpus is getekend uit de data:* elk lichtspoor is een taal van de index,
  van links naar rechts de maanden, en hoe feller, hoe meer checks die maand.
  Het komt uit dezelfde stand als de releasekaart, en het bijschrift ("Every
  streak is one language…") noemt het aantal talen en het beginjaar. Een
  test houdt beeld en bijschrift gelijk, zoals de tabel aan de releasekaart
  hangt. Dit beeld staat bovenaan de homepage.
- *Bestanden:* WebP. AVIF is met korrel niet kleiner (gemeten op de schets:
  WebP 85–125 KB, AVIF 84–120 KB, JPEG 140–200 KB per beeld van 1600×900 of
  900×1200). Elk beeld hooguit 200 KB.
- *Herkomst:* per beeld een regel in `web/public/beeld/HERKOMST.md`: commando,
  seed en versie van het script, en bij corpus de releasekaart en de datum.
- *De afbeelding bij delen* (Open Graph) wordt een uitsnede van corpus,
  1200×630, zonder tekst. Sinds het logo (2026-11-09) staat het woordmerk erop: `merk/og.jpg`, gemaakt uit
  `beeld/delen.jpg`.
- *De foto's:* krant-bril en lezer gaan van de site; de blog krijgt een veld.
  De typemachine blijft in *How it works*, want daar zijn zijn 256 bits uit
  die foto berekend (motorkap); zijn bron blijft in `BRONNEN.md`.
- *Stil:* de velden bewegen niet.

**Tekst op een veld moet leesbaar blijven.** Gemeten op de schets: wit haalt
in het midden van de velden maar 1,2:1 (corpus, hemel) tot 4,3:1 (nacht),
tegen de lichtste 5% van de pixels. Daarom:
- elk veld krijgt in het script een *tekstzone* waar het rustig en donker
  blijft (bij corpus linksonder, waar de kop staat);
- daaroverheen mag een zachte schaduwlaag;
- de test meet per veld, na de schaduwlaag, wit tegen de lichtste 5% in de
  tekstzone: koppen minstens 3:1, alle andere tekst minstens 4,5:1 (§5).
  Haalt een licht veld dat niet, dan gaat de tekst in inkt.

**Wat niet verandert.**
- De uitslag blijft de laboratoriumuitslag van §4: op papier, tellingen, de
  bronnen het grootste blok, eigen tekst per staat. Nooit een veld achter of
  in een uitslag, label, bonnetjeslijst of de meter (§4f). Op de
  marketingsite mag een voorbeelduitslag op een veld liggen, als lijst eromheen.
- De meter houdt zijn schaal van groen naar rood (D6).
- De site laadt niets van buiten: geen scripts, geen lettertypen. De beelden
  komen van de eigen site (`img-src 'self'`).
- Geen em-dash, titels en beschrijvingen binnen Google, elke link werkt,
  licht en donker compleet (D8), toegankelijkheid §5.

**Wat er verandert, per pagina.**
- *Gedeeld* (`global.css`, `Header.astro`, `Footer.astro`; `site.json` krijgt
  alleen de missie erbij, voor de voet):
  letters, kleuren, pillen, de focusrand. De kop is een smalle balk; ligt er
  een veld bovenaan, dan ligt de kop erop, in wit. De voet staat op een veld
  met de halfdoorzichtige kaart.
- *Homepage:* bovenaan corpus op volle breedte met de kop; de drie ingangen
  als kaarten; de donkergroene sectie en de mintsectie worden papier met
  haarlijnen; de tabel blijft. De waterverf (`herovlak`, `wasvlek`) en de
  korrellaag van de nachtsectie gaan weg.
- *How it works:* een lage band bovenaan; de tekeningen van de motorkap
  blijven, met oranje als markeerkleur.
- *Use cases, de twee toepassingen en de drie doelgroepen* (`LandingLayout`):
  een lage band met de kop; de blokken worden panelen met een haarlijn.
- *Blog:* een veld als afbeelding bovenaan de post en in het overzicht.
- *Privacy en 404:* de band, verder alleen de gedeelde opmaak (zo staat er
  bovenaan elke pagina een veld, stap 4 van #23.14).

**try.factiz.org.** Leest `global.css`, dus kop, voet, letter, kleuren en
knoppen gaan vanzelf mee. De demo, Ask, de cijfers en `/check` krijgen bovenaan
een smalle band met een veld achter de titel. De invoer, de uitslag, de
bonnetjes en de meter staan daaronder op papier, met dezelfde opbouw als nu;
de knop *Check* wordt een donkere pil. De voet staat op hetzelfde veld als op
factiz.org; de API serveert de velden zelf (`/beeld/<naam>.webp`), zoals het
favicon, dus ook hier komt niets van elders.

**Hoe het getest wordt.**
- Alle bewakers die er zijn blijven: zelfstandig, de dichte
  beveiligingsinstellingen, elke link, titels, geen em-dash, licht en donker,
  focus, `prefers-reduced-motion`, geen alarmkleur.
- Aangepast: de merkregel in `test_site` en `test_webui` (nu: oranje is de
  klik, `herovlak`, `wasvlek`) wordt de nieuwe (pillen in wit en inkt, groen
  het merk, oranje alleen als markeerkleur, de serif alleen voor de bewering);
  de fototest gaat over de foto's die blijven.
- Nieuw:
  - elk beeld in `web/public/beeld/` heeft een herkomstregel, en het script
    maakt met dezelfde seed hetzelfde beeld, op een kleine marge na;
  - corpus en zijn bijschrift komen uit de stand van de releasekaart;
  - tekst op een veld haalt het contrast hierboven;
  - gewicht: elk beeld hooguit 200 KB, de homepage samen hooguit 700 KB bij
    het eerste bezoek;
  - op try.factiz.org geen veld binnen de uitslag, de bonnetjes of de meter;
  - elke pagina nagekeken in licht, donker en op telefoonbreedte (375 px).
- De stijlgids `docs/ontwerp/stijl.html` wordt herschreven naar dit systeem.

**Wat het kost.** Geen geld: geen lettertypen, geen stockbeelden, geen
beeldmodel, geen dienst. Het script draait ~10 seconden op de Mac.

**De velden bewegen** *(PO 2026-10-28: "Kun je al onze gemaakt abstracte
achtergrond heel subtiel laten bewegen?")*. Elk veld schuift heel langzaam
heen en weer, als licht dat voorbijgaat: alleen opzij, nooit omhoog of omlaag,
want de strepen lopen opzij en de tekstzones liggen in banden van boven naar
beneden. Het beeld staat daarvoor een fractie ingezoomd (`--veld-zoom`, 1,04),
zodat er nooit een rand zichtbaar wordt, en schuift hooguit `--veld-drift`
(1,5%) naar elke kant, in 40 tot 70 seconden heen en net zo lang terug; elk
veld in zijn eigen tempo, zodat ze nooit samen bewegen. Alleen CSS
(`transform` op een laag achter de inhoud, geen script), dus de dichte
beveiligingsinstellingen blijven. Bij `prefers-reduced-motion: reduce` staat
alles stil. Het geldt voor elk veld op de pagina: de homepage bovenaan, de drie
ingangen, de band, de voet, het uitgelichte stuk in het menu en de velden van
de blog; niet voor de beelden in de persmap, want die zijn om te downloaden.
Getest: in elke stand van de beweging haalt elke tekstzone nog zijn contrast
(`tests/test_velden.py` meet de uiterste standen), en de beweging staat alleen
aan buiten `reduce`.

### 4i. Het hoofdmenu *(besloten door PO 2026-10-27: "Akkoord met het plan voor het menu."; PLAN #23.15)*

De vraag van de PO (2026-10-27): "main menu en mega menu's maken: Solutions/Use
cases [...] Platform [...] Resources [...] About [...]". Gekozen in twee
vraagrondes (schets in `data/look/menu-schets.html`, niet in git):
- *Platform* is alles wat onder Factiz uitkomt: de releases, de tools, de API,
  en later een plug-in, MCP en producten voor teams. Wat er nog niet is, staat
  op een overzichtspagina met zijn stand, niet als link in het menu.
- Nieuw bij het menu: *What we believe*, *Releases*, *Documentation*, het
  overzicht *Platform*, en *Newsroom* nu al, als persmap zonder persbericht.
- *Education* wordt lesmateriaal voor scholen, later (roadmap). De MCP-server
  komt eerst op het plan, pas daarna op de site.
- Zonder script.

**Het menu.** Vier groepen en de knop: *Solutions · Platform · Resources ·
About · Try it free*. Elke groep opent een megamenu: per link de naam en één
regel uitleg, en rechts één uitgelicht stuk op een veld.

| groep | links (waarheen) | uitgelicht |
|---|---|---|
| Solutions | For fact-checkers, For developers, For researchers (de drie `/for/`-pagina's); For AI teams (`/use-cases/#ai-teams`, *in development*); All use cases | Check a claim, op hemel |
| Platform | Check a claim, Ask a question, Check a message (*in development*; was *beta* tot B46), The numbers (try.factiz.org); How it works; Releases; API and protocol (`/docs/`); Open source (GitHub); All products (`/platform/`) | The numbers, op leisteen |
| Resources | Blog; Documentation (`/docs/`) | de nieuwste blogpost, op leisteen |
| About | What we believe; Newsroom; Privacy; Code and licences (GitHub) | de missie, op leisteen (een uitgelicht stuk staat op een staand veld; nacht ligt) |

**Nooit een link naar iets dat er niet is** (`tests/test_sitelinks.py`): het
menu groeit mee met de pagina's. Nog niet in het menu: *Product tour*, *Case
studies* (er gebruikt nog geen redactie Factiz, #23.13), *Education* en MCP.

**De nieuwe pagina's**, elk op de band, in de stem van VOICE, met de tekst
langs de PO vóór de commit:
- `/platform/`: elk product met zijn stand (*available*, *beta*, *in
  development*, *planned*), zoals Use cases dat doet. Wat beschikbaar is,
  linkt naar zijn pagina; de rest linkt nergens heen of naar zijn kaart.
  Alleen wat op het plan of in een besluit staat, elk met zijn taak of
  besluit erbij (`data-plan`); MCP en producten voor teams komen er pas op
  als ze op het plan staan. De controle per bericht staat sinds B46 op *in
  development*: de gesloten beta komt pas na stap 9 van de route naar V1, en
  het menu zegt hetzelfde.
- `/releases/`: de huidige releasekaart (Factiz 1) en de eerdere, uit
  `docs/RELEASES.md`, met wat slechter werd; de cijfers hangen aan de kaart.
- `/docs/`: de API (`POST /resolve`, de discovery, de grenzen), het protocol,
  zelf draaien en de conformantiesuite, nu verspreid over *For developers*, de
  README en PROTOCOL.md. Met een vaste inhoudsopgave opzij die meeschuift
  (PO 2026-10-27: "Bij resources graag wel een sticky inhoudsopgave in plaats
  van die labels aan de bovenkant"): een kolom links met een link per deel,
  elk 44 px hoog, en het laatst gekozen deel gemarkeerd (`:target`, zonder
  script). Op een telefoon past geen kolom: daar een uitklapper *On this page*
  bovenaan, die niet meeschuift, want open zou hij de halve pagina bedekken.
- `/what-we-believe/`: de missie (B27) en de principes, uit teksten die er al
  staan (homepage, How it works, privacy).
- `/newsroom/`: de persmap: wat Factiz is in drie zinnen, de kerncijfers van de
  releasekaart, het beeld (het merk, de velden, schermen) en het perscontact
  (#23.3, van de PO). Het persbericht komt erbij bij het verzenden (#23.5).
  Perscontact *info@factiz.org*, zonder naam van een persoon (PO 2026-10-27:
  "een 'good old' algemeen info@ adres", "Nee, alleen Factiz"); de mailbox
  bestaat vóór de lancering (#23.3). Schermafbeeldingen van het product
  komen op aanvraag: de demo toont een uitslag pas na een klik, en een
  gereedschap dat dat vastlegt is een download (PO).

**Zonder script.** Elke groep is een uitklapper (`details`, allemaal met
dezelfde `name`): een klik, een tik of het toetsenbord opent hem, en een
tweede sluit de eerste. Klikken ernaast sluit hem niet; dat is de prijs van
geen script (PO). Op een telefoon één knop *Menu* met de vier groepen onder
elkaar, elk weer uitklapbaar. Elke link minstens 44 px hoog (§5); dat lost ook
de te kleine menulinks van nu op. Op beide hosts gelijk, uit `site.json`, dat
groepen, een regel uitleg per link en het uitgelichte stuk krijgt.

**De voet** toont dezelfde vier groepen als kolommen in de glazen kaart.

**Hoe het getest wordt.** Elke link in menu en voet bestaat; hetzelfde menu op
elke pagina van beide hosts; geen script; elke link minstens 44 px hoog en op
375 px niets opzij (gemeten in de preview); op `/platform/` linkt alleen een
beschikbaar product naar een pagina; de cijfers op `/releases/` en
`/newsroom/` hangen aan de releasekaart; geen em-dash; titels en
beschrijvingen binnen Google.

**Wat het kost.** Geen geld; wel de tekst van vijf pagina's.

### 4j. Een vals detail, gemarkeerd *(B48, besloten door PO 2026-10-27; PLAN #32.3a)*

De PO (2026-10-27): "De tweede, het allemooiste is al we deze zin ook visual
kunnen markeren of highlighten".

**Wat het is.** Een echt verhaal met één vals detail: de hoofdbewering klopt,
maar één datum, getal, plaats of naam niet. Factiz zegt *Mostly true, but …*
en wijst het detail aan in het bericht zelf.

**Van boven naar onder, op de controlepagina (§4g):**
1. *Het bericht*, zoals de gebruiker het stuurde:
   - *tekst:* de foute woorden met een markering in de kleur van *let op*
     (niet rood: het verhaal klopt grotendeels), en een cijfer ervoor als er
     meer dan één markering is;
   - *screenshot:* het beeld zoals de gebruiker het koos, in de browser, met
     een kader over de woorden die de OCR daar las. De server stuurt alleen
     de kaders terug, nooit het beeld (B43, DR3).
2. *De uitkomst in woorden:* "Mostly true, but **2003** should be **2006**."
   Daaronder de bron die 2006 noemt, met het citaat en de link (een bonnetje,
   zoals overal).
3. *De meter* (§4f) op de stand die bij *klopt grotendeels* gemeten is. Nooit
   in het groen.

**Regels:**
- Niet alleen met kleur: elke markering heeft de verbetering in woorden
  ernaast, en voor een schermlezer de tekst "marked: 2003, should be 2006".
- De markering valt precies op de foute woorden, niet op de hele zin. Kan de
  pagina de woorden niet terugvinden (de OCR las ze anders), dan geen kader,
  wel de verbetering in woorden.
- Hoogstens één *maar*. Meer dan één vals detail is *klopt niet* (B48).
- Op een telefoon staat de verbetering onder het bericht, niet in een
  zwevend venster.

### 4k. Rood op algemene kennis *(B50, besloten door PO 2026-10-28; PLAN #32.0m)*

De PO (2026-10-28): "rood op algemene kennis mag als eigen laag, hoogstens stand
3, met een eigen tekst op de pagina".

**Wat het is.** Duidelijke onzin waar geen bron het met zoveel woorden tegenspreekt
("Barack Obama weighed 50 pounds at birth"). Factiz zegt *Likely false* en zegt erbij
waarop dat rust.

**Op de controlepagina (§4g):**
1. *De meter* op 3, *Likely false*. Nooit 1: dat vraagt een check van een redactie.
2. *De laag*, in plaats van de bronnen: "Contradicts well-established knowledge.
   No fact-check or source found."
3. *Waarom deze stand*: het gemeten aandeel, zoals overal ("Of messages with this
   result, fewer than 1 in 100 turned out to be true.").
4. Geen bonnetjes, en geen uitlegzin van het model (B31). Onder *Sources* staat:
   "Factiz found no source that says this in so many words. This result rests on
   general knowledge, which is right far more often than not, but not always."

**Regels:**
- Alleen in een taal waar de laag gemeten is (eerst Engels); anders blijft het
  oordeel van de machine staan.
- De woorden zeggen eerlijk dat er geen bron is. Nooit "proven false".
- Een bericht over een bewering van een ander krijgt ook hier geen kleur (§4g).

### 4l. Het antwoord in twee lagen *(PLAN #32.13; concept, de PO beslist na de meting)*

De PO (2026-10-29, bij het nakijken van §181 en §182): "Onderliggend feit: klopt!
Bewering: niet", met een klein inzetje van wat er echt gebeurde, zoals een
factchecker dat doet. Een kaal *misleidend* doet denken dat het oorspronkelijke
artikel niet klopt.

**Op de controlepagina (§4g), van boven naar onder:**
1. *The claim:* het oordeel over de bewering, groot, met de kleur. De kleur hoort
   alleen bij de bewering; de regels veranderen niet (B51, #32.11, #32.12).
2. *What is confirmed:* het onderliggende feit in één zin, met de uitgevers die het
   bevestigen. Alleen als de bewering niet *klopt* en twee bronnen het dragen, zoals
   bij groen. Geen kleur: het feit is geen oordeel over het bericht.
3. *What really happened:* een kader naast de bewering, niet in haar kleur, met de
   bron erbij. Alleen bij rood of oranje.
4. De herkomstregel en de bronnen, zoals altijd; een bron die alleen het feit
   bevestigt, heet *Confirms the fact*.

**Voorbeeld** (Rasuwa, zonder het beeld): *The claim: Not settled.* "This is about
what a photo or video shows. Factiz cannot see it here …" *What is confirmed:*
"Floods hit Rasuwa on 26 August." *Confirmed by kathmandupost.com, bbc.com.*

**Regels:** de twee zinnen schrijft het model; ze staan er alleen na een meting op
trouw aan de bronnen (B31, #32.13). De uitlegzin blijft in het ruwe antwoord. Een
antwoord uit de database verandert niet.

### 4m. De foto bij de bron, in twee lagen *(PLAN #32.54; voorstel, de PO beslist bij de release; PO 2026-11-08: A in twee lagen)*

Bij een bericht met een foto zegt Factiz alleen groen als een betrouwbare bron die het nieuws bevestigt, ook die foto
toont (`fotobron-v2`, BENCHMARK §248, §249). Klopt het nieuws, maar vinden we de foto daar niet, dan is de uitkomst
`photo_not_at_source`, en krijgt het bericht als geheel geen groen.

**Op de controlepagina (§4g), van boven naar onder:**
1. kop: *News confirmed, photo not found*, zonder kleur, met de neutrale markering van *Not confirmed* (§4l);
2. *The news:* *True*, met een klein groen bolletje: het nieuws zelf klopt;
3. *The photo:* "None of the reliable sources that confirm this news shows this photo. It may come from somewhere else."
   Geen kleur: we zeggen niet dat de foto nep is, alleen dat we haar niet bij het nieuws vonden;
4. de herkomstregel en de bronnen, zoals altijd; de uitlegzin van het model staat niet op de pagina (B31, §4l).

**Wel gevonden:** gewoon groen, zoals nu, met onder het oordeel één regel *The photo appears at* met de uitgever en een
link naar de pagina.

**In `POST /check`:** `outcome` `photo_not_at_source`, `colour` leeg, `news_colour` `green` (de laag van het nieuws), en
`photo` met `found`, `page` en `checked` (hoeveel pagina's geopend). Geen foto of geen groen: `photo` leeg.

**Tijdens het wachten** (§251, PO 2026-11-09): de pagina zegt wat Factiz doet ("looks for fact-checks, searches reliable
sources and reads them"; bij een screenshot ook het lezen van het beeld en de foto bij de bron), dat het 10 tot 15 seconden
duurt, en telt de seconden. Geen nagebootste stappen die niet echt gebeuren.

**Regels:** de stap kijkt alleen op de pagina's die het bericht al bevestigen. Opent geen pagina, dan is de foto niet
gevonden en is er geen groen; twijfel versoepelt nooit. Rood en oranje veranderen nooit.

### 4n. De tijdelijke site *(PO 2026-11-09, PLAN #23.17)*

**Waarvoor.** Partijen benaderen vóór de echte site er is: factcheckers, onderzoekers naar beïnvloeding (CheckFirst,
Alliance4Europe) en organisaties. Wie onze mail krijgt, moet op factiz.org zien wat we bouwen, waarom, en hoe ver
we zijn.

**Eén pagina, in het Engels**, in de look van §4h:
- bovenaan een veld met de kop van de pagina erop;
- daaronder rustige secties op papier;
- onderaan de voet op het veld nacht.

De kop heeft geen menu, alleen het merk en de knop *Get in touch* (een mail aan info@factiz.org). De secties, in deze
volgorde:
1. **Bovenaan, boven de vouw, ook op een telefoon:**
   - wat Factiz als geheel is, in de kop: "Independent fact-checking for what people share online";
   - waarom, in de zin eronder: de check bestaat vaak al, en wij brengen haar naar het moment van twijfel;
   - voor wie, als drie kleine labels: mensen in appgroepen, factcheckers en redacties, onderzoekers en platforms;
   - dat het nog in ontwikkeling is.

   *(PO 2026-11-09: "de kop moet direct zeggen, wat is factiz, dus de overall header. Wervend, wat is het, voor wie,
   waarom allemaal above the fold".)* De screenshots zijn één functie en staan als kop bij *What it does*.
2. **Why we do this**, het manifest *(PO 2026-11-09: "Wil je de missie en de visie en onze grotere idee, waarom we
   dit doen, en onze passie voor de waarheid, democratie etc met passie omschrijven. [...] je moet er in kunnen
   geloven als je met ons mee wilt werken.")*. Dit staat op niveau 2 van VOICE (eigen stem, één beeldspraak), maar
   elke zin rust op een besluit:
   - een scène in een appgroep, en de check die al bestond (REQUIREMENTS §2);
   - waarom het ertoe doet: een democratie heeft gedeelde feiten nodig, nep maken kost bijna niets, en Meta stopte
     in januari 2025 met factchecken in de VS;
   - de belofte van REQUIREMENTS §1: liegen duurder maken, kopieën herkennen;
   - de onafhankelijkheid van B12.
3. **Who it is for:** de gebruiker in de appgroep, factcheckers en redacties, onderzoekers, platforms en instellingen
   (REQUIREMENTS §3, B40).
4. **What it does:** de kop "A fact-check machine for forwarded screenshots", en de uitkomsten van de controle in gewone woorden. De kleur komt van de bronnen. Elke zin van de
   uitleg heeft zijn bron.
5. **How it works:** vijf stappen: lezen en zwartmaken, de factchecks, zoeken zoals een factchecker, de bronnenlijst
   beslist de kleur, het antwoord.
6. **Where we are** (het plan):
   - de zes talen van V1 (B63);
   - de lat van B68, die per taal gehaald moet zijn voor die taal openbaar wordt;
   - waar we nu aan werken: de aanvoer per taal, en de herkomst (B62, met Operation Overload als voorbeeld, K31);
   - de volgorde van B65;
   - waar het naartoe gaat: de open kaart van B23, met bij elke pijl zijn bonnetje.
7. **What we hold to:** de missers en elke release met zijn meting (B22), en geen waarheidspercentage (DR2).
8. **Talk to us:** wie we zoeken, en het adres.

De voet eindigt in één balk *(PO 2026-11-09: "Footer kan een balk zijn onderin denk ik, layout is nu rommelig")*:
links het woordmerk, rechts de vlag van de EU met "Factiz is built in the Netherlands." *(PO 2026-11-09: "EU vlag +
'Factiz is built in the Netherlands' in de footer?")*, het adres en "No cookies, no scripts.". Breed staat dat op één
regel, op een telefoon onder elkaar. Onderin wordt het veld donkerder, zodat de kleine tekst leesbaar blijft. De vlag is getekend naar de vaste maten
(3 bij 2, twaalf sterren op een cirkel). Ze zegt waar Factiz gemaakt wordt, niet dat de EU het steunt; daarom staat
ze klein naast de zin en nergens anders.

**Regels:**
- Geen eigen meetcijfer zonder de PO. De lat van B68 is een doel, geen meting, en mag erop.
- Geen link naar een pagina die er niet is, en geen link naar try.factiz.org zolang de controle uit staat.
- Geen script en geen beeld van elders, net als de site.
- De stem van VOICE.md: koppen op niveau 0, "we", geen uitroeptekens, geen em-dashes en geen strijdtaal.

**Wat de PO beslist:** de kop en de tekst, en wanneer de pagina live gaat.

### 4o. Het platform: de soorten pagina's *(B72–B74, PO 2026-11-10; PLAN etappe 33; eerste opzet, de PO stelt bij op de eerste schermen)*

Het platform is een leeszaal, geen campagnesite. Dezelfde ondergrond als §4h
(papier, dunne koppen, haarlijnen, mono labels, knoppen als pil), maar zonder
velden: een pagina met inhoud uit de database draagt geen beeld (D11). Geen
script, dus alles is een link of een gewone pagina. *Sinds #33.6d (§4w, PO
2026-11-12) staan de velden er wel: bovenaan elke pagina en als kaart bij thema's
en dossiers, nooit achter een bewering of oordeel.*

| pagina | wat erop staat | wie vult het |
|---|---|---|
| factcheck | één bewering met haar checks (§4p) | de database |
| lijst | factchecks met filters: thema, taal, jaar, oordeel, redactie | de database |
| thema | de dossiers eronder, de nieuwste factchecks, de rapporten | de database |
| dossier | een verhaal of een netwerk, met een tijdlijn (§4r) | een mens |
| truc | uitleg van één truc, met voorbeelden | een mens en de database |
| rapport | eigen werk over een land, een verkiezing of een netwerk | een mens |
| zoeken | één veld, de uitkomst als lijst | de database |
| vaste pagina's | over ons, werkwijze, correcties, licenties en naamsvermelding, privacy | een mens |

De eerste pagina is geen etalage van cijfers maar een ingang: zoeken, de
thema's, de dossiers, het nieuwste.

**Het logo op het platform** *(PO 2026-11-11: "Factiz logo staat in de map van de placeholder site. Handig voor menu,
footer, OG images, favicon etc.")*. Dezelfde bestanden als §4h, geen nieuwe: het woordmerk inline in de kop en in de
voet (het logo houdt zijn oranje, de letters nemen de tekstkleur, dus het werkt licht en donker), als link naar de
start in de taal van de pagina, met de naam *Factiz* voor wie niet kijkt; het icoon (`logo.svg`, met `favicon.ico` en
`apple-touch-icon.png` voor oudere browsers); en bij delen het vaste beeld `og.jpg` met de titel en de omschrijving
van de pagina. Een eigen deelbeeld per factcheck of dossier is er nog niet.

### 4p. De factcheckpagina *(B72; de claimkaart van §4d, uitgegroeid tot een pagina)*

Van boven naar beneden:

1. **De bewering**, in haar eigen taal en schrijfrichting, in de schreef (wat
   een ander zei, §4h). Is de taal van de site een andere en is er een
   vertaling die mag (B32), dan staat die erboven en het origineel eronder, met
   *Machine translation from Spanish. Original:*.
2. **Het label met de telling** uit de woordenlijst van §4c: *Known to be false ·
   4 newsrooms, 3 languages, 2018–2023*. Bij één check: het oordeel van die
   redactie, met haar naam.
3. **De bronnen**, het grootste blok (D2), de nieuwste eerst: redactie, het
   oordeel in haar eigen woorden, datum, taal, link; bij een dode link *Archived
   copy* met de datum. Onder het blok de naamsvermelding en de licentie.
4. **Waar het opdook**, alleen als een bron dat vastlegde: het domein als platte
   tekst (nooit een link), met *seen at* of *attributed to*, de bron en de
   datum.
5. **De velden als rustige regels**: thema, dossier (*Part of dossier …*), truc
   en vorm, namen. Elk is een link naar zijn lijst.
6. **Komt ook voor als** *(#33.6, PO 2026-11-11)*: hetzelfde bericht in andere
   woorden en andere talen. Eerst één regel met de telling (*The same message
   was checked 9 times, in 5 languages*), dan de lijst: de andere factchecks
   van dezelfde versie uit het dossier, elk een rij zoals in een lijst (de
   bewering in haar eigen taal, met de vertaling volgens §4p, het label en de
   datum), en daaronder de andere woorden waarin deze zelfde pagina is
   nagetrokken. Geen alarm en geen oordeel: een telling laat zien dat het
   bericht vaker opdook. Twee factchecks staan hier alleen samen als een mens
   dat goedkeurde, of als het lab ze al als één bewering samenvoegde.
7. **Verwante factchecks**: hoogstens vijf *(nog niet gebouwd)*.
8. **Onderaan**: *The sources are the verdict*, *Wrong? Tell us*, en de datum
   van de release.

Wat er nooit staat: een eigen oordeel van Factiz op een check van een redactie
(DR5), een percentage (D1), een beeld van het nepnieuws (dat komt pas met eigen
factchecks, B70, met een stempel).

**Een vertaling in een lijst** *(#33.5, B32)*: dezelfde volgorde als op de pagina. De vertaling is de regel waarop je
klikt; eronder, kleiner, *Machine translation from Hindi. Original:* en het origineel in zijn eigen taal en richting.
Op de vier andere talen van de site staat tot hun eigen vertaalronde de Engelse vertaling, en de regel zegt dat ze
Engels is (*Machinevertaling in het Engels, uit het Hindi*). Een bewering in de taal van de site staat zoals ze is.
Heeft een doeltaal haar leesproef gehaald, dan gaat de vertaling in de taal van de site voor de Engelse, ook bij een
bewering die Engels is (*Machinevertaling uit het Engels*, met het Engels eronder); waar ze ontbreekt, blijft het de
Engelse.

### 4q. Lijsten, thema's en zoeken

- **Een rij in een lijst** is de bewering (twee regels, afgekapt op een woord),
  het label, de redactie en het jaar. Geen kaartjes met beeld.
- **Filters** staan boven de lijst als rijen links; het gekozen filter is te
  zien zonder kleur (D5). Elk filter is een eigen adres.
- **Bladeren** met *Previous* en *Next* en het aantal.
- **Zoeken** is één veld in de kop van elke pagina. De uitkomst is dezelfde
  lijst. Niets gevonden is een eigen tekst met één vervolgstap (D3), geen lege
  pagina.
- **Een themapagina** opent met de naam en één zin, dan de dossiers, dan de
  nieuwste factchecks, dan de rapporten.

### 4r. Het dossier

Naar de dossiers die de PO voor de Sportraad Amsterdam bouwde. Van boven naar
beneden:

1. **De soort als label** (*Story* of *Network*), de naam, en één alinea.
2. **Where do we stand now?** met kerngetallen uit de database: voor het eerst
   gezien, het aantal factchecks, de talen, de redacties, de laatste
   aanvulling.
3. **De tijdlijn**, per jaar, de nieuwste boven. Elk item draagt zijn soort als
   label: *Fact-check*, *In the press*, *Research*, *Decision*, *Report*. Een
   factcheck linkt naar zijn pagina; de rest naar de bron.
4. **Verwijzingen**: het thema, verwante dossiers.
5. **Verkennen** *(PO 2026-11-19, PLAN #34.2ca)*: onder de verwijzingen de begrippen van het dossier
   (de Taurus, Kursk, Boetsja), als een rij knoppen die elk een zoekvraag naar het archief sturen. Een
   knop zegt het begrip en niets meer; geen telling, want het getal zegt een lezer niets en verschuift
   met elke uitgave. Hoogstens twaalf, het meest kenmerkende eerst.

Bij een netwerkdossier staat boven de tijdlijn wie het netwerk vaststelde, met
de bron. Een item staat er alleen in met die bron erbij (B62).

*Bij de bouw (#33.6):* het eerste kerngetal heet *First fact-check*, niet *first
seen*: we kennen de datum van de eerste check, niet de dag waarop het verhaal
begon. Een factcheck op de tijdlijn is de bewering (met de vertaling volgens
§4p), het label, de redactie en de datum van de eerste check. Een factcheck
zonder datum staat onderaan, onder *Date unknown*. Een dossier dat de PO nog
niet goedkeurde, draagt op de eigen computer het label *Draft* en staat in geen
uitgave.

### 4s. Talen en schrijfrichting *(B74)*

- **De taalkeuze** staat in de kop, als de namen van de talen in hun eigen
  taal (*Nederlands*, *English*, *Deutsch*, *Español*, *Français*). Alleen de
  talen waarin déze pagina bestaat. Geen vlaggen.
- **Een bewering in een andere taal** houdt haar eigen taal en richting. Een
  Arabische bewering staat rechts uitgelijnd in een verder Nederlandse pagina.
- **De opmaak gaat niet uit van links naar rechts**: marges en uitlijning volgen
  de leesrichting, zodat een taal van rechts naar links er later bij kan.
- **Lettertypen van het systeem**, ook voor schriften buiten het Latijn; geen
  lettertype van buiten.
- **Data en getallen** in de vorm van de taal van de site.

### 4t. De schil van het platform: kop, menu's, filters, voet *(PO 2026-11-11, de interfaceronde; PLAN #33.6b)*

Het onderzoek en de bronnen staan in `docs/voorstellen/2026-11-11-interface-ronde.md`. Het menu volgt §4i (groepen
die uitklappen, een regel uitleg per link, nooit een link naar iets dat er niet is), nu voor het platform.

**De maten.** Eén breedte voor kop, voet en lijsten (74 rem) en een leeskolom van 46 rem die links begint, onder het
merk. Twee omslagpunten: onder 48 rem is het een telefoon (lades), vanaf 62 rem staat het menu in de kop.

**De kop.** Breed: het merk, de drie menugroepen, het zoekveld en de taal, op één rij. Telefoon: het merk en de knop
*Menu* op de eerste rij, het zoekveld op de tweede; hoogstens 120 punten samen. Het zoekveld is op elke pagina een
invulveld, nooit een link of een icoon.

**De menugroepen.** *Factchecks* (alle factchecks, zoeken, redacties; de thema's; de dossiers), *Platform*
(producten, voor ontwikkelaars, onder de motorkap, documentatie) en *Over Factiz* (over ons, bronnen en licenties, een
fout melden). Elke groep is een uitklapper; een tweede sluit de eerste, en een klik ernaast sluit hem ook. Per link de
naam en, waar het helpt, één regel uitleg. Op een telefoon staat dezelfde lijst in een lade, met de taalkeuze erin.
Het is één lijst in de pagina, niet twee.

**De filters.** Eén formulier met keuzelijsten (thema, onderdeel, oordeel, taal, jaar, land, redactie, sorteren) en
één knop *Show results*. Breed: een kolom links van de lijst. Telefoon: een knop *Filters* boven de lijst opent het
formulier als lade van onderen, met een knop *Close*. Boven de lijst staat wat er gefilterd is, elk stukje weg te
halen, en *Clear filters*. Een lege uitkomst krijgt een eigen tekst met één vervolgstap (D3).

**Sorteren.** *Newest first*, *Oldest first*, *Most newsrooms*; bij zoeken staat *Best match* voorop.

**De voet.** Kolommen: het archief, de thema's, het platform, over Factiz. Daaronder één rij: de uitgave, geen
cookies en geen scripts, de licenties, het contactadres als tekst, en de talen.

**Elk doel 44 punten** in kop, menu, lade, werkbalk, bladeren en voet (§5); links in lopende tekst niet.

**Zonder script (D13).** De lades en de laag van het menu gebruiken `popover`, de groepen `details` met één `name`.
Kent een browser dat niet, dan staan menu en filters open in de pagina: alles blijft bereikbaar.

**Vindbaarheid.** Elke pagina een eigen titel en omschrijving; bij een factcheck de bewering, het label en de
telling. Kruimelpaden met opmaak voor zoekmachines in de HTML zelf. Elk blad van een lijst noemt zijn eigen adres als
voorkeursadres; een zoekuitslag nooit. Eén vast deelbeeld. De site blijft dicht voor zoekmachines tot 33.9.

### 4u. Namen *(B72; PLAN #33.7; eerste opzet, de PO stelt bij op de eerste schermen)*

Een naam is een ingang, geen onderwerp van een oordeel.

- **Op de factcheck:** bij de velden (§4p, 5) één regel *Names*, met de namen
  als links, in de taal van de site. Hoogstens vijf, in de volgorde waarin het
  model ze noemde. Geen pictogram, geen foto.
- **De pagina van een naam** (`/names/Q…/`): de naam als kop; eronder klein de
  soort (*Person*, *Organisation*, *Place*) en *Wikidata Q…* als link naar
  buiten (zonder iets over de bezoeker mee te geven). Dan één vaste zin:
  *Fact-checks in which this name appears. A name here says nothing about who
  made a claim.* Daaronder de gewone lijst met het filterformulier van §4t, met
  de naam als vast stukje dat weg kan.
- **Het overzicht** (`/names/`): drie groepen (personen, organisaties,
  plaatsen), elk op alfabet in de taal van de site, per letter te bladeren. Geen
  tellingen naast de namen: het is een register, geen ranglijst.
- **Wat er nooit staat:** een omschrijving ("politicus", "complotdenker"), een
  foto, een telling die als score leest, of een woord dat zegt dat de genoemde
  iets beweerde. De bewering is van wie haar deed; de naam zegt alleen over wie
  of wat zij gaat.
- **Leeg:** een naam die uit een latere uitgave valt, geeft de gewone
  *niet gevonden*, geen doorverwijzing.

### 4v. Zoeken voorop *(PO 2026-11-12, met een eigen ontwerp; PLAN #33.6c; de regels van Baymard, nagelezen)*

**De startpagina** begint met een band over de hele breedte in het ontwerp van de PO: donker groenblauw, een
raster van fijne stippen, rechtsboven en linksonder een veld waar de stippen feller zijn. De kop met het logo
hoort bij de band. In het midden, op leesbreedte: het label *Search 106,988 fact-checks* (het getal komt uit de
uitgave) boven een groot licht veld met een korte plaatshouder (*Name, place or words*, zodat zij ook op een telefoon
past) en de knop
*Search* erin. Daaronder één regel: zoveel checks, van zoveel redacties, in zoveel talen, en dat de vraag niet
bewaard wordt. Onder de band staat het archief: links de filters, rechts de volgorde, een paar thema's met hun
aantal, en de nieuwste factchecks; daarna de dossiers. Geen losse rijen links meer.

**Het formulier.** Thema en onderdeel als keuzelijst bovenaan, dan oordeel, taal en jaar als vinkjes, dan land
en redactie als keuzelijst. Bij elke waarde het aantal, rechts uitgelijnd, in de zachte kleur. Wat niets
oplevert staat er niet. Na zes tot acht waarden *Nog 22 tonen* met een plusteken. Onderaan één knop *Toon
resultaten*. Op een telefoon is het formulier een lade van onderen, met bovenin de volgorde als rondjes; de knop
ernaartoe heet *Filteren en sorteren* en telt wat gekozen is.

**De volgorde** staat op een breed scherm rechts van het aantal: *Sorteren op* en dan de keuzes als korte
knoppen; de gekozen heeft een lichte vulling. Bij zoeken komt *Beste treffer* vooraan.

**De zoekpagina.** Bovenaan hetzelfde grote veld, nu op de lichte pagina, met de vraag erin. Daaronder, als de
vraag een ingang is, een lichtgroen vak met de pagina's die zo heten (*Persoon · Donald Trump · 2.356
factchecks*). Dan de kop *3 resultaten voor "Zelensky bought"*, de volgorde, de gekozen stukjes, en de
treffers: de woorden van de vraag gemarkeerd met een zachte gele achtergrond, bij een lange bewering het stuk
rond het woord. Geen treffer: de kop *Niets gevonden*, een tip (minder of andere woorden; een bewering in een
andere taal vind je ook via haar vertaling) en de wegen verder.

**Bronnen** (gelezen op 2026-11-12; alleen openbare pagina's, de rest staat in PLAN #33.6c als niet geopend):
baymard.com/blog/search-field-design, /search-bar-ui, /mobile-search-submit-button, /persist-search-queries,
/search-scope, /search-snippets, /allow-applying-of-multiple-filter-values, /ecommerce-filter-ui,
/how-to-design-applied-filters, /promoting-product-filters, /essential-sort-types, /back-button-expectations,
/number-of-items-loaded-by-default; baymard.com/research-articles/no-results-page en /truncation-design.

### 4w. De look van de site op het platform, met de velden *(PO 2026-11-12; PLAN #33.6d; een tussenstap tot het designsysteem van etappe 34)*

De PO: "Voor nu, gebruik voor de stijl het design system wat er al lag voor de oude site. (niet de placeholder) En
kijk of je de abstracte visuals kunt gebruiken voor achtergronden, en visuals bij cases, checks en dossiers." Dit
vervangt voor het platform de regel van §4o dat een pagina met inhoud uit de database geen beeld draagt, en de
stippenband van §4v. De rest van §4o tot §4v blijft.

**De opmaak van §4h.** Papier en nacht als grond, de letter van het apparaat, koppen dun en krap, mono-labels in
groen met ruime spatiëring, knoppen als pil (inkt op papier, wit op een veld), haarlijnen. Het menu klapt uit als een
paneel van papier met afgeronde hoeken en een schaduw; de kolomkoppen zijn mono-labels.

**Waar de velden staan.**
1. *Bovenaan elke pagina*, met de kop erop in wit:
   - de start op corpus (het beeld dat uit de checks zelf getekend is), met het label, het grote zoekveld als witte
     pil met een donkere knop, en de regel eronder;
   - de zoekpagina op groen, met hetzelfde zoekveld en de vraag erin;
   - de andere pagina's op een band: het kruimelpad, een mono-label en de kop, dun en groot. Groen, behalve bij een
     thema (zijn eigen band) en een dossier (zijn eigen band);
   - de factcheck op een lage band in het veld van haar thema, met alleen het kruimelpad en het label. De bewering, het
     label met de telling en de bronnen staan daaronder samen op papier: de claimkaart blijft één ding (§4d), en een
     valse bewering krijgt geen affiche.
2. *De kaarten*: elk dossier en elk thema in een overzicht als kaart (4:5) op zijn eigen veld, met de naam in het
   midden en de telling eronder, zoals de drie ingangen van §4h. Bij een thema staan de onderdelen eronder op papier.
   Een case is een verhaaldossier; een rapport of truc krijgt later dezelfde behandeling.
3. *De voet* op nacht, met de missie, een witte knop en de links op een halfdoorzichtige kaart.

**Een veld per thema en per dossier.** Uit hetzelfde script en dezelfde vijf families (nacht, groen, hemel, olijf,
leisteen), met een eigen seed, zodat elk thema en elk dossier een eigen beeld heeft in dezelfde stijl. Een dossier
neemt de familie van zijn thema. Elk veld bestaat als band (2000×600, de tekst links) en als kaart (900×1125, de
tekst in het midden en onderaan). De familie zegt niets over waar of onwaar en volgt geen oordeel; zij maakt een plek
herkenbaar, en de naam staat er altijd in tekst bij.

**Wat niet verandert.** Geen veld achter of in de bewering, het label, de telling, de bronnen of de meter (D11). Eén
uitzondering, sinds 2026-11-19: op het beeld van een dossierkaart staat linksonder een dicht label *Dossier* (bij een netwerk
*Netwerk*), met een eigen achtergrond zodat de korrel er niet doorheen komt; het label *Verhaal* naast de naam is weg, want
elke kaart was een verhaal (PO: "Overal een storylabel: voeg niet zoveel toe. Ik denk dat we gewoon over de visual, het
label, dossier moeten plakken"). De laatste aanvulling staat niet meer op de kaart ("'latest addition' kan weg"). Een rij
in een lijst draagt geen beeld (§4q): een lijst is om te lezen, en een abstract beeld zegt niets over de bewering. Geen
script, de beelden van de eigen site (`img-src 'self'`), en het platform draagt zijn eigen kopie van de beelden.

**Hoe het getest wordt.** Per veld de herkomstregel en de seed, opnieuw getekend op een steekproef; wit in elke
tekstzone na de sluier van de pagina, ook als het veld schuift; geen rood; hooguit 200 KB; elk thema en dossier heeft
zijn band en kaart; een factcheck draagt nooit een veld achter haar bewering, label of bronnen; geen inline opmaak.

### 4y. Het oordeel als stempel, met wie het zegt *(PO 2026-11-19; PLAN #34.2cc)*

*PO 2026-11-19: "Wat je nu doet met onze eigen onwaar- of waar-labeltjes, vind ik veel cooler dan we hadden en veel meer
des fact checks. Ik snap dat we dit hebben gedaan omdat we niet een definitieve mening wilden geven, maar volgens mij
kunnen we dat slim oplossen. [...] in plaats van 'bekend als onwaar', zeggen we gewoon 'onwaar volgens'. Dan zetten we
daar de betreffende redactie neer. Als meerdere tot dezelfde conclusie zijn gekomen, staan die er ook achter", en: "de
stempel is dan gewoon 'Onwaar' en volgens VérifRadar erachter, klein, net zoals we factiz erachter zetten".*

- **Het stempel** draagt alleen het oordeel, in hoofdletters in een dubbel kader, licht schuin, zoals bij de eigen check
  (§4x): *ONWAAR*, *MISLEIDEND*, *ONWAAR OF MISLEIDEND*, *DEELS WAAR*, *KLOPT*, *ONBEWEZEN*, *SATIRE*, *OMSTREDEN*; zonder
  oordeel *GECHECKT*. Dezelfde woorden als de schaal van de eigen redactie waar die ze heeft.
- **Erachter, klein**, wie het zegt: *volgens VérifRadar*, *volgens DW en BR24 Faktenfuchs*; tot vier namen allemaal,
  daarboven drie en *en 2 andere*. Bij *Omstreden* staat er *tussen PolitiFact en FactCheck.org*, want dan zijn ze het
  oneens; zonder oordeel *door AFP*. De namen komen uit de uitgave (`pagina.volgens`, `publiceren.wie_het_zegt`): wie
  tot het getoonde oordeel kwam, wie het vaakst checkte eerst.
- **Waarom dit DR2 niet breekt**: het oordeel is nog steeds dat van de redacties, en wie het gaf staat er direct naast.
  *Bekend als* was er om geen eigen oordeel te geven; *volgens* doet hetzelfde met een naam erbij.
- **Wie het checkte en wat elk zegt** *(PO 2026-11-22; PLAN #34.2cd; SPECS E9.S31 AC7)*: checkten meer redacties dezelfde
  bewering (op deze pagina of onder *Ook gecheckt door*), dan staan onder het antwoord hun stempels onder elkaar, elk met de
  naam erachter, de namen in één kolom: **MISLEIDEND** Washington Post, **DEELS WAAR** PolitiFact, **KLOPT** El Detector.
  Geen kop: aan de verschillende stempels zie je dat meer redacties het checkten (PO 2026-11-22: "Dit kan weg. Dan komen ze
  netjes onder elkaar."); *Gecheckt door* staat er alleen voor een schermlezer. Elke redactie is een eigen link naar haar
  check eronder, die met het getoonde oordeel; bij aanwijzen licht alleen die naam op, en de check waar je landt is even
  gemarkeerd (PO: "1"). *N andere* springt naar de lijst.
  Geen telling en geen zin over verschil: of ze het eens zijn, zie je aan de stempels (PO: "That's it."). Onderzoek laat zien
  dat redacties het zelden oneens zijn (K37, K42), en dat het lezers helpt als ze dat zien.
- **De eigen check** houdt haar zegel en *Factiz* (D12): in grijs blijft het verschil het rondje met de F.
- **Waar**: in elke rij van een lijst (de naam van de redactie onder in de rij valt dan weg), op de factcheckpagina boven
  de checks, in de suggesties bij het zoeken (het stempel alleen, want daar is geen plek), op het deelplaatje (het stempel
  rechtop, want Pillow en resvg zetten een schuin kader te verschillend, met *volgens …* ernaast: alle namen als ze heel
  passen, anders *en N andere*, nooit een afgekapte naam) en in de titel en de
  omschrijving voor zoekmachines, met hoogstens één naam: *Onwaar volgens Vera Files: ‘…’*, *Onwaar volgens FactCheck.org
  en 3 andere: ‘…’* (PO 2026-11-19: "Ja, zet ze om").

### 4x. De eigen factcheck *(B82, PLAN #37.4; de stijl Stempel, gekozen door de PO op 2026-11-18: "Stempel")*

De opbouw, de schaal, het beeld en de toon staan in `docs/voorstellen/2026-11-18-eigen-factcheck.md`: de kop zegt wat we
vonden, dan het oordeel met één zin, de bewering zoals ze rondgaat, *In het kort*, *Wat we weten* met het nummer van de
bron achter elke zin, *Wat we niet weten*, de tijdlijn, de bronnen en wie schreef en wie nalas. Het beeld dat rondgaat
altijd met een stempel en verkleind, het origineel ernaast zonder stempel; een gezicht van een privépersoon of een kind
onherkenbaar.

Drie richtingen, op dezelfde tokens als de site en elk met de vier concepten van de proef, op
https://claude.ai/artifact/PkEWGHzyNDJw9JZy7yN334 (gemaakt met `docs/voorstellen/eigen-factcheck-stijlen/maak.py`):

- **Uitslag**: een formulier van een laboratorium, met een nummer, vaste velden en een register van bronnen;
- **Reportage**: een stuk met een naam erboven, de tekst in de schreef, het oordeel als één groot woord;
- **Stempel**: een eigen zegel en een donkere kaart met de bewering en het oordeel als stempel.

Alle drie halen D12: het verschil met een check van een andere redactie zit in de vorm, ook in grijstinten (de pagina
heeft een knop om dat te zien). **De PO koos Stempel:** het zegel van Factiz bovenaan, de kop in de schreefloze letter, de
donkere kaart (in donker licht) met de bewering in de schreef en het oordeel als stempel, en in een lijst het kleine zegel
met een stempeltje in plaats van de pil van het archief. Na de eerste pagina (PO 2026-11-18): *Wat we vonden* heet *Wat we weten*, naast *Wat we
niet weten*; dat tweede deel staat als gewone tekst, en de tijdlijn krijgt het vlak. In het archief staat een eigen check als redactie
*Factiz* tussen de andere; haar rij heeft links het kleine zegel, het oordeel als stempeltje en de naam Factiz, waar een
check van een andere redactie de pil heeft (D12). De kleuren van het oordeel zijn die van het archief, zonder rood; nooit een veld achter de
bewering, het oordeel of de bronnen (D11). **Sinds 2026-11-19 de opbouw van een factcheck** (PO: "Onze eigen factchecks mogen ook de sidebar
krijgen en meer in lijn komen met het pagina design van de andere checks, nu heeft deze alles anders terwijl wat er lag al
sterk was, alleen afwijken in design waar we duidelijk willen maken dat het een 'eigen' factcheck is"): het kruimelpad met
*Terug naar resultaten*, twee kolommen met de contextkaarten van haar pagina in het archief en *Op deze pagina*, de bewering
in de schreef en *Klopt dit?* op het zachte vlak, de koppen, de verbanden en het melden van een fout zoals bij elke factcheck.
Eigen blijven het zegel met de kop die zegt wat we vonden, het stempel van Factiz in het antwoord (*volgens Factiz*, in de
inkt van het oordeel), het beeld met het stempel en de bronnen met hun nummer. De donkere kaart is weg.
**Sinds B84 (2026-11-19) het begin van een gesprek** (PO: "De rest van de dingen die nog openstaan in jouw concept
opmerkingen mogen erbij als: 'nog uit te zoeken' en misschien wel een oproep, draag bij aan deze factcheck, dat we het
juist als een begin van een dialoog zien?"): na *Wat we niet weten* de lijst *Nog uit te zoeken*, in woorden voor de lezer
(wat we nog willen nagaan, en waar we twijfelden tussen twee oordelen), met daaronder het paneel *Draag bij aan deze
factcheck*: één zin, de knop die een mail opent met de kop van de check als onderwerp, en het adres als tekst om te kopiëren.
Een bron die een post van een privépersoon is zonder kopie, zegt waarom: *de post is niet meer te zien*, of de reden in
woorden. Een beeld dat rondgaat maar er niet is, laat bij een gepubliceerde check geen lege plek. Onderaan staat wie
schreef (*Claude (AI)*) en wie nalas (*De redactie van Factiz*).
**Het zegel** (PO 2026-11-19): in het midden de F van het logo, de drie bellen uit `logo.svg` (`site/src/lib/bellenf.js`), in
de kleur van het zegel; op de ring twee keer *CHECKED BY FACTIZ*, in elke taal hetzelfde, met de hoofdletters midden in de
ring en de ene keer precies bovenaan, de andere precies onderaan. Het kleine zegel in een rij heeft dezelfde F.
**Factiz Radar** (PO 2026-11-19: "Factiz Radar, met eronder Gecheckt met AI, nagelezen door de redactie"; "Ja, bouw het"):
zo heten de eigen checks op de site, met onder de naam *Gecheckt met AI, nagelezen door de redactie*; onderaan blijft wie
precies schreef en nalas. Niet *geautomatiseerd*: mensen vinden een kop met het label AI minder juist omdat ze aannemen
dat er geen mens meekeek (Altay en Gilardi, PNAS Nexus 2024), en hier keek er wel een mee. De lijst staat op `/nl/radar/`.
In het hoofdmenu een eigen punt *Radar* met een stip in het oranje van het logo, niet onder Verkennen (B83: de eigen checks
zijn de kern), en op de start drie ringen in de held met de naam en wat er deze week nieuw is, als link naar de lijst.
Alleen in een taal met gepubliceerde eigen checks. Een golf loopt alleen naar buiten als er in de zeven dagen tot de
uitgave een nieuwe check is: een cirkel die altijd pulseert, wordt behang en botst met principe 3; met
`prefers-reduced-motion` staat hij stil (§5).

## 5. Toegankelijkheid — ondergrens

Niet onderhandelbaar voor elke versie:

- Contrast minimaal WCAG AA (4,5:1 voor tekst, 3:1 voor grote tekst)
- Kleur is nooit de enige drager van betekenis — categorie staat altijd ook in tekst
- Volledig bedienbaar met toetsenbord; zichtbare focusindicatie
- Aanraakdoelen minimaal 44×44 px
- Uitslagen zijn leesbaar met een schermlezer: categorie en telling zijn tekst,
  geen afbeelding
- Respecteert `prefers-reduced-motion`

## 6. Ontwerpchecks

Te controleren bij elke etappepoort, met een screenshot in de hand.

- [ ] **D1** — Geen enkel scherm toont een percentage of balk die de waarschijnlijkheid
      van waarheid uitdrukt *(principe 1 & 2, DR2)*. *Sinds B25:* een
      waarheidsschaal mag alleen met de laag erbij zichtbaar (bekend, signaal,
      eigen oordeel), met woorden en positie als drager, kleurenblind-veilig, en
      nooit "100%"; een eigen oordeel alleen waar de gepubliceerde meting de
      poort haalt. *Sinds B44:* de waarheidsmeter van §4f is die schaal.
      - Een stand van 1 tot 9 uit het gemeten aandeel, met woorden, de laag en
        één regel met dat aandeel.
      - 10 alleen voor een vastgesteld feit, met de bronnen; 0 is dicht (§154).
      - Nooit het getal "100%" of een los percentage als waarheid.
- [ ] **D2** — Op een `matched`-uitslag is het bronnenblok het grootste element; de
      telling staat in de kop *(principe 1)*
- [ ] **D3** — `none` en `related` hebben een eigen tekst met uitleg en één
      vervolgactie — niet vormgegeven als fout of lege staat *(principe 5)*
- [ ] **D4** — Een uitslag los bekeken (zonder voorgaand scherm) maakt duidelijk wát
      gecontroleerd is en door wie *(principe 4)*
- [ ] **D5** — In grijstinten bekeken blijft elke categorie te onderscheiden
      *(toegankelijkheid, kleur niet als enige drager)*
- [ ] **D6** — Geen rode banners, waarschuwingsdriehoeken of uitroeptekens in een
      normale uitslag *(principe 3)*. *Sinds B44:* rood mag in de schaal van
      de waarheidsmeter, van groen naar rood met genoeg verschil in lichtheid
      (D5), nergens anders.
- [ ] **D7** — Elke foutstaat heeft eigen tekst; geen enkele fout valt terug op `none`
- [ ] **D8** — Licht en donker zijn beide compleet; geen enkel element is alleen in
      één modus leesbaar
- [ ] **D9** *(roadmap, voor later; hoort bij principe 6)* — Geen enkele zin in een uitslag
      heeft de post, de maker of het account als onderwerp, behalve een
      bonnetje dat zijn bron en datum noemt *(principe 6, DR10)*
- [ ] **D10** *(#24.1; gehaald op het schermontwerp, 2026-10-14)* — Stilte bij `none`: in de tijdlijn staat nergens een label
      zonder treffer, en een `none` op verzoek is een regel die weggaat, geen
      badge op de post *(§4b, principe 5)*
- [ ] **D11** *(#23.14)* — Een beeld draagt nooit betekenis: geen
      veld achter of in een uitslag, label, bonnetjeslijst of meter; tekst op
      een veld haalt het contrast van §4h; de velden staan stil *(§4h)*.
      *Sinds #33.6d (§4w):* op het platform mag een veld een plek herkenbaar
      maken (een thema, een dossier), met de naam in tekst erbij; nooit achter
      de bewering, het label, de telling of de bronnen, en nooit een oordeel
- [ ] **D12** *(B72, etappe 33)* — Op het platform is een check van een redactie
      in grijstinten te onderscheiden van een eigen oordeel van Factiz, en
      draagt elke pagina haar bronnen met naam *(DR5, §4p)*
- [ ] **D13** *(B73, B74; versoepeld door B75 op 2026-11-12: de beste gebruikerservaring gaat voor; script mag, van
      de eigen site of met een hash in de pagina, en opmaak in attributen; nooit gegevens van bezoekers bewaren, nooit
      volgen, nooit analytics van een andere partij, en tellen alleen anoniem en opgeteld (B78); de pagina blijft leesbaar als
      het script niet laadt)* — Elke pagina van het platform werkt zonder script, in
      licht en donker, en met een bewering van rechts naar links erin *(§4s)*
- [ ] **D14** *(B74)* — De taalkeuze toont alleen talen waarin de pagina
      bestaat, in hun eigen naam, zonder vlaggen *(§4s)*

## 7. Geparkeerd — voor de PO

Ontwerpideeën die scope raken en dus niet hier thuishoren:

- **Tijdlijnweergave** van een claim (eerste verschijning, herhaald opduiken) —
  visueel sterk, maar vereist herkomstdata die pas beschikbaar is als het corpus dik
  genoeg is. Kandidaat voor v2.
- **Consensussterkte als visuele gradatie** (1 check vs. 14) — nu een telling in
  tekst; of dat later een eigen visuele behandeling verdient is een PO-beslissing.
