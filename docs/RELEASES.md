# Releases — wanneer iets een versie is, en wat erin moet staan

*Eigenaar: PO. Besluit: B22. De kaart onder "Huidige release" wordt door
`tests/test_releases.py` tegen `config.toml` gehouden: wie de engine wijzigt
zonder nieuwe kaart, krijgt een rode suite.*

## Waarom versies

Een versienummer is de verpakking van een verschoven cijfer. Technisch
bestond de release al: elke fingerprint draagt zijn modelversie en een
wissel dwingt een herindex af (DR6), en elke uitbreiding meet alle markten
opnieuw (B14). Wat ontbrak was het publieke moment. Dit document maakt van
dat technische feit een productrelease, zonder dat het nummer ooit meer
belooft dan de meting.

Wij versioneren de **resolver**, niet "ons model". We trainen geen model;
we stellen een resolver samen uit een embeddingmodel, drempels, een
beeldhash en clustering. Een aankondiging zegt dus "Factiz 2", nooit "ons
nieuwe model".

## Drie lagen, drie ritmes

| laag | versie | ritme | wie merkt het |
|---|---|---|---|
| **protocol** | v0.1, v0.2 | traag; alleen bij een wijziging op de draad | implementatoren |
| **resolver** | Factiz 1, 2, 3 (en 1.x) | alleen bij een verschoven poortcijfer of een nieuwe modaliteit | gebruikers en pers |
| **corpus** | gedateerde bouw (bouw 2026-10-04) | wekelijks (RUNBOOK), zonder releasemoment | iedereen, via `/numbers` |

De lagen bewegen onafhankelijk. Een protocolversie is een standaardbesluit
en volgt nooit de marketingkalender. Het corpus is geen release maar een
teller; datastory's uit het corpus (zoals de zombieclaims) houden het ritme
vast tussen de resolver-releases door.

## Wat een release is

- **Hoofdrelease (Factiz N).** Een nieuwe capaciteit of modaliteit, of een
  gewijzigde modelversie in `config.toml` (die een DR6-herindex afdwingt).
  Dit is het persmoment.
- **Tussenrelease (Factiz N.x).** Dezelfde engine, maar een poortcijfer is
  verschoven: door afstelling, door beter zoeken, of doordat een taal is
  toegelaten (B14). Blogpost en changelog, geen persronde.
- **Geen release.** Een corpusverversing, copy, de site, een bugfix zonder
  cijfereffect. Die krijgen een commit, geen nummer.

De launch heet in dit logboek Factiz 1. In perscopy verschijnt het nummer
pas vanaf de opvolger: een "1" zegt een lezer niets tot er een "2" is.

## De twee eerlijkheidsregels

1. **Geen release zonder verschoven cijfer.** De poortcijfers zijn de
   foutbovengrens en de dekking, totaal én per markt, gemeten met
   `python -m doublecheck.benchmark` op alle markten (B14), vóór en na, op
   dezelfde testset. Een nieuwe modaliteit telt als capaciteit zodra ze
   een eigen nulmeting heeft (zoals §29 voor beeld). Is er geen delta, dan
   is er geen release.
2. **Wat slechter werd en wat nog mist staat in de aankondiging zelf.** Het
   is een verplichte sectie en ze is nooit leeg: werd er niets slechter,
   dan staat er wat nog steeds niet werkt. Een verwijzing naar een los
   document volstaat niet.

## Het releaseproces

1. Wijzig de engine in `config.toml`; bij een modelversie:
   `python -m doublecheck.reindex`.
2. Draai `python -m doublecheck.benchmark` (alle markten) en noteer het
   run-id. Draai de poortwachters uit de RUNBOOK (uitgeversregister,
   taalgeschiktheid).
3. Schrijf de nieuwe kaart onder "Huidige release" en verplaats de vorige
   naar "Eerdere releases". De suite dwingt af dat kaart en config gelijk
   zijn. Werk de site bij op dezelfde run, ook `site/how-it-works.html`
   (de motorgeschiedenis en de cijfers); bij een modelwissel tekent
   `python -m doublecheck.motorkap` de vingerafdrukken opnieuw. Ook dat
   dwingt de suite af.
4. Draai `python -m doublecheck.feitenbasis kerncheck`: alle feiten van de
   kern in al hun formuleringen door het echte `/resolve`. Eén rood of
   *omstreden* oordeel naast een vastgesteld feit, en de release gaat niet
   door; het releaserapport weigert dan *(B33, nultolerantie op de kern,
   2026-10-17)*.
5. Draai `python -m conformance <url> --proeven deploy/conformantie-proeven.json`
   en ververs het dashboard. De proeven raken het `matched`-pad, en één
   matcht alleen via een vertaling (verplichting 10).
6. Tot de lancering is de aankondiging een gegenereerd rapport volgens het
   skelet hieronder *(PO 2026-10-12, #23.10)*:
   `python -m doublecheck.releaserapport --voor <run> --na <run> --uit
   docs/releases/<naam>-<datum>.md`. Bij de livegang schrijven we haar
   met de hand en halen we haar door de writer-lint.
7. Raakt de wissel iets dat clients zelf berekenen, dan geldt de
   uitfasering.
8. Bevries de release: `python -m doublecheck.vooruitblik bevriezen
   --release <naam>`. Wat de feed daarna brengt, kon niemand gebruiken om af
   te stellen; daarop wordt de release later gescoord (#28.6 d).

## Een nieuw model: de modelpoort *(voorstel, PO 2026-10-27: "yes" op vastleggen; nog geen besluit)*

**Wat een release is, en wat niet.** Een release is een nieuwe versie van de
Factiz-engine: de vraag, de regels, de databases, de bronnenlijst en het
model samen, met cijfers op de vaste toets. Een nieuw model, van welke
aanbieder ook, is alleen een kandidaat. Het wordt pas een release als het door
de poort komt en iets beter maakt. Blijft het huidige model het beste voor
zijn geld, dan blijft het. De PO: "Het zou dus prima kunnen dat wij op Sonnet
draaien, als het maar werkt."

**Wanneer we kijken:** niet bij elk nieuw model, maar bij een van vier
aanleidingen:
1. de aanbieder kondigt aan dat het huidige model stopt;
2. de wekelijkse controle slaat alarm (Sonnet 5.5 heeft geen vaste versie met
   datum, B43);
3. een nieuw model belooft winst op een bekende zwakte (screenshots, talen);
4. een goedkoper model is misschien even goed.

Eens per kwartaal kijken we welke modellen er zijn, van alle aanbieders,
ook de open modellen.

**De vaste toets** (de verzamelingen van PLAN etappe 32, per taal):

| deel | aantal | waarom |
|---|---|---|
| ware berichten (checks, nieuws, feiten) | 300 | rood moet kloppen |
| bekend nepnieuws | 100 | wat al ontkracht is |
| vers nepnieuws | 100 | factchecks van ná de kennisgrens van het nieuwste model, elke maand ververst |
| gewone teksten | 100 | nooit rood |
| satire, sturing, berichten over een bewering, beweringen over een beeld | elk 50 | de lastige randen |
| dezelfde berichten als screenshot | | de hoofdzaak van V1 |

- *Vers*, omdat een nieuw model een oude factcheck uit zijn trainingsdata kan
  kennen. Dan scoort het hoog op bekend nepnieuws zonder dat het iets kan.
- *Een geheim deel*, dat nooit gepubliceerd wordt. Wat openbaar is, kan in de
  trainingsdata van een volgend model belanden, en dan meet de toets niets
  meer.

**De poort, in twee rondes:**
1. *Voorronde (~$3–5):* de 100 moeilijkste berichten door de Factiz-engine
   met het nieuwe model erin. Wordt het vaker onterecht rood, dan stopt het
   hier.
2. *Hoofdronde (~$15–25 per taal):* de hele toets, met de eisen van V1 (B46).
   Het nieuwe model wint bij minder onterecht rood bij gelijke herkenning,
   meer herkenning bij gelijke betrouwbaarheid, of gelijke kwaliteit voor
   minder geld. Dan volgen het releaseproces hierboven en een nieuwe ijking
   van de schaal: die hoort bij het model (B44).

In beide rondes draait **het kale model** mee, zonder onze lagen, alleen met
"is this true?" en zoeken. Zo zien we elke keer wat Factiz toevoegt. Wordt het
kale model even goed als de engine, dan verschuift ons voordeel naar de
databases en de meting, en dat willen we vroeg weten.

**Wat een kandidaat verder moet kunnen:**
- zo kort mogelijk bewaren (zero data retention als het kan; sinds B54 de standaard van Anthropic, hoogstens 30
  dagen) en niet trainen op onze
  berichten (B43);
- zoeken met letterlijke citaten die we kunnen nalopen;
- een vaste versie met datum waar dat kan; anders hoort de wekelijkse controle
  erbij;
- bij modellen uit China ook per onderwerp meten, want in het Mandarijn
  citeerden chatbots Chinese staatsbronnen (RESEARCH §6);
- een open model dat we zelf in de EU draaien, is een sterke kandidaat: dan
  verlaat ook de bewering de EU niet.

**Kosten:** per aanleiding ~$5. Bij een kandidaat die de voorronde haalt, komt
daar ~$15–25 per taal bij. De eerste keer dat de poort draait, is de
vergelijking Opus 5.5 tegen Sonnet 5.5 (`docs/V1-POSITIE.md`).

## Uitfasering: de belofte en het gat

**De belofte.** Bij een wissel van een schema dat clients zelf berekenen
(vandaag alleen beeld, via `image_fingerprint`) blijft het vorige schema
**90 dagen** bediend naast het nieuwe. Discovery noemt beide schema's, het
nieuwste eerst, en de aankondiging noemt de einddatum.

**Het gat.** Vandaag bedient de resolver één beeldschema en weigert hij
elke fingerprint met een ander schema (DR6, zie `api.py`). Dubbele
bediening is dus bouwwerk, en een harde voorwaarde vóór de eerste release
die het beeldschema wisselt. Het is geen onderdeel van Factiz 1. Daarnaast
kent het discovery-document geen veld voor een einddatum; dat is een open
protocolvraag (PROTOCOL §11.6).

**Wat er niet onder valt.** Tekst heeft geen clientschema (`schemes.text`
is leeg, PROTOCOL §4), dus een embeddingwissel raakt geen clients: herindex
en benchmark volstaan. Drempels staan in discovery en zijn bij een release
direct van kracht; ze staan op de kaart.

## Skelet van de aankondiging (Engels)

De titel is de claim met het nummer erin, zonder dubbele punt:
*"Factiz 2 checks what language models say"*.

1. **The sentence.** One comparative number, the same condition on both
   sides: "coverage from 64.2% to X% at the same error bound".
2. **What is new.** At most three items, each with its measurement and
   the benchmark run id.
3. **What got worse, and what we still miss.** Mandatory, never empty.
4. **Check us.** The benchmark command, `/numbers`, the conformance run.
5. **For implementers.** Scheme, threshold and protocol changes, with the
   phase-out date where one applies.
6. **Release card.** The table from this document.

## Huidige release

### Factiz 1 (launch, akte 1, 2026-10)

De resolver als het collectieve geheugen van de factcheckers: tekst en
screenshot in, bronnen uit. Vóór de lancering gewisseld naar bge-m3 (#25.14c,
PO 2026-10-11, BENCHMARK §73–§75), en negen Zuid-Aziatische talen toegelaten
die het vorige model niet aankon (#25.18, §76); de vorige kandidaat staat
onder "Eerdere releases". Daarna, nog vóór de lancering (PO 2026-10-12): de
claimvarianten, vertalingen van elke claim in vijf talen waarlangs de
resolver ook zoekt (#25.17, §84), en OCR per schrift (#25.21, §80). En op
2026-10-14 (PO): twee keer lezen bij twijfel over het schrift (#25.22,
§107). De twijfelband raakt de tekstroute niet. Kaart en site staan sinds
2026-10-14 op run #61 (PO): na de witte lijst van uitgevers (B28,
§100–§102) en met ontkenningen in negen Zuid-Aziatische talen (#25.20,
§106). Claims, checks, DR7 en attributie tellen over de index; `/numbers`
telt alle opgeslagen claims mee (108.922 claims, 109.958 checks, 840 met
twee of meer redacties) en noemt de 364 erbuiten apart. En op 2026-10-16 (PO,
als tussenrelease): een vraag ook als bewering zoeken (#25.36, §118). De
benchmark ziet die regel niet, want hij zoekt op bewaarde vingerafdrukken
zonder tekst (DR3); zijn cijfers blijven per constructie gelijk (run
#63 met de regel aan is gelijk aan #61: 5 op 4.839, dekking 81,5%). Het cijfer dat verschuift, is dat van de meetset en van Ask; dat
staat hieronder als eigen regel. En op 2026-10-16 (PO, tussenrelease): de
claims die als vraag zijn opgeschreven, ook als bewering in de index
(#25.37, §119), 3.539 varianten van een regel. Kaart en site staan sindsdien
op run #64: dekking van 81,5% naar 81,6%, de fouten gelijk. En op 2026-10-17
(PO, tussenrelease; in de besluiten van #30.3b "Factiz 1.1"): de rechter, een
bijgetrainde cross-encoder die de bovenste kandidaten leest en meebeslist over
`matched` (#30.3, §125–§130), en de feitenlaag, die een rood of omstreden
oordeel naast een vastgesteld feit uit de kern nooit als `matched` geeft
(#30.3b, §131). Omdat Factiz 1 nog niet live is, staan ze op deze kaart, zoals
de vraagvorm. Ook deze twee ziet de benchmark niet, want de rechter leest
tekst en de benchmark heeft alleen vingerafdrukken (DR3); run #66 met beide
aan is gelijk aan #64. Het cijfer dat verschuift, is dat van de zeef (B33):
een eigen regel hieronder. Op 2026-10-18 gingen nog 25 vage claimteksten uit
de index ("Is this possible?", "What is happening?", "Can anyone tell?"):
een losse zin uit gewone webtekst raakte ze letterlijk (§133, #30.11b). Dat
is een corpuswijziging, geen release: 108.533 claims in de index, 71 als
vaag erbuiten, en run #67 is gelijk aan #66. Op 2026-10-22 gingen er nog 8
uit (#30.11c, §136): onderschriften zonder wie, wat of wanneer ("terreuraanval
in Jammu en Kasjmir", "Election date announced") die de artikellezer op
webtekst aantrok. Eén testpaar had er een als lastigste buur en ging bewust
weg (`data/testparen-weg-2026-10-22T113328.json`, B28): 108.525 claims in de
index, 79 als vaag erbuiten, en run #68 is gelijk aan #67 (4.838 paren, 5
fouten, dekking 81,6%).

En op 2026-10-29 (PO, tussenrelease): de controle per bericht (B51, `POST
/check`) met `lezer-v3` (#32.12). Ze staat nog uit (`[berichtcontrole] aan =
false`); sinds B54 is zero data retention daar geen voorwaarde meer voor. Ze raakt
`/resolve` en de benchmark niet, dus run #68 blijft het cijfer van de
resolver. Het cijfer dat verschuift, is dat van de controle zelf: twee eigen
regels hieronder (§181, §182).

En op 2026-11-02 (PO): de bronnenlijst `bronnen-v3` (#32.29, §202). Daarbij
tellen ook de tekens die de PO aannam: het EFCSN, de JTI, het Trust Project en
een IFCN-lidmaatschap in vernieuwing. Ze tellen alleen bij de 40 Spaanse en
Portugese redacties die de PO een voor een koos. Een redactie zonder teken
krijgt geen band (PO: "Maybe just use the LIN score and skip everything without
IFCN and other factcheck rating, better to be clear?"). De controle staat nog
uit, dus live verandert er niets. Het cijfer dat verschuift, is de dekking van
de lijst: een eigen regel hieronder. En op 2026-11-03 (PO: "Bronnen zo bouwen"):
`bronnen-v4` (#32.29d, §205). Dezelfde tekens gelden nu in alle talen, uit de
volle lijsten van het IFCN, het EFCSN, de JTI en het Trust Project. Een eigen
score zonder teken kwam niet door de ijking (§204) en zit er niet in.

En op 2026-11-03 (PO, tussenrelease): de lezer leest ook de checks uit de
database (`lezer-v5`, #32.28, #32.30). Raakt kring 1 niets, dan zoekt `/check`
de 5 checks die het meest op het bericht lijken, en Sonnet leest die naast de
top 10 van Brave. Brave is daarmee ook de zoekdienst in het product, met het
gewone plan (B52). De controle staat nog uit, tot de livegang (B54: zero data
retention is geen voorwaarde meer). De cijfers die verschuiven, zijn die van de controle
zelf: twee eigen regels hieronder (§201, §206).

En op 2026-11-03 (PO: "lezer mag jij kiezen", tussenrelease): de lezer met de
negen uitkomsten van besluit A en B48 (`lezer-v7`, #32.31, #32.32). `POST /check`
zegt welke uitkomst het is (`outcome`). Bij *klopt grotendeels* geeft het de
verbetering met de plaats van de foute woorden (`correction`); de
controlepagina markeert die woorden. Bij een bericht over een bewering van een
ander krijgt het bericht geen kleur, maar die bewering wel (`claim_colour`).
Gekozen boven `lezer-v5`, omdat besluit A en B48 deze uitkomsten vragen en
`lezer-v7` bij 200 ware nieuwsberichten geen vals alarm gaf. Wikinews blijft in
de bronnenlijst *goed* (PO). De controle staat nog uit (B43). Op echte
screenshots waarschuwt `lezer-v7` bij 39 van 58 met bewijs, tegen 37 met
`lezer-v5` (§209, §201).

En op 2026-11-03 (PO: "Ja: breng het beeld uit (beeld = true) als
tussenrelease", B55): het beeld van een screenshot gaat mee naar het model,
altijd en zonder goedkeuring per controle (`beeld = true`). Eerst maakt
Factiz zwart wat de tekstherkenning als persoonsgegeven vindt: nummers,
e-mailadressen, handles, links naar een persoon, de regels met de naam van
een groep of afzender (`opknippen.zwart_beeld`). Daarna slaat het het beeld
opnieuw op, zonder metadata. Bij het uploaden staat één zin, en de
privacytekst zegt het. Uitgebracht met één eis niet gehaald: bij de ware
foto's 3 valse alarmen in plaats van hoogstens 2 (§212, hieronder bij wat
slechter werd).

En op 2026-11-05 (PO: "ship the release of lezer-v9 today", tussenrelease,
B57): de controle zoekt zoals een factchecker, in één
lezing (`lezer-v9`, #32.41). Haiku 5.5 bedenkt vooraf tot drie zoekvragen: de
eigen site van wie het bericht noemt, het echte nieuws en de bron zelf. Die en
het bericht zelf gaan tegelijk naar Brave, en Sonnet leest één keer. Wat
betrouwbare media zouden melden als het waar was, maar geen betrouwbare bron
meldt, heet *niet bevestigd*, zonder kleur en met de zoekvragen erbij (DESIGN
§4l). Op echte screenshots waarschuwt `lezer-v9` bij 54 van 58 bekend nepnieuws
met bewijs: de eis van V1 (52) gehaald, tegen 39 met `lezer-v7` (§220).
Uitgebracht met twee eisen niet gehaald: één keer te vaak *niet bevestigd* bij
waar nieuws en gewone tekst, en de wachttijd p50 7,45 s in plaats van
hoogstens 7 s (§219, §220, hieronder bij wat slechter werd).

En op 2026-11-05 (PO: "es-, pt- and de.wikinews.org count as reliable, as in
English", B58): de bronnenlijst `bronnen-v5`. Wikinews in het Spaans, het
Portugees en het Duits telt als *goed*, zoals in het Engels; daarvoor viel het
terug op wikinews.org, waar het strengste oordeel *laag* is. Alleen die drie
adressen veranderen. Gemeten wordt het in #32.42, op berichten in die talen.

En op 2026-11-08 (PO: "ja eens, doen we het zo", B64): de bronnenlijst `bronnen-v6`. Een publieke omroep die lid is van de
EBU, in een land met 75 of meer bij Reporters zonder Grenzen, is *goed*, ook als Lin e.a. hem *wisselend* noemt; een
oordeel *laag* blijft *laag*, de grens van 0,65 blijft. Daarbij Wikinews in het Nederlands en Frans *goed*, zoals in de
andere talen van V1 (B58, B63). Precies 8 adressen veranderen: ORF, RTBF, WDR, NDR, SWR, STV, nl.wikinews.org en
fr.wikinews.org. In de 3.489 bewaarde antwoorden van de metingen noemen er 16 een van deze omroepen als bron, allemaal in
de Duitse sets en het duel (BENCHMARK §245); een nieuwe kleur is daar niet na te rekenen, want de zoekresultaten zijn niet
bewaard. Gemeten wordt het in de volgende Duitse meting en in de eerste Nederlandse en Franse (#32.59).

En op 2026-11-08 (PO: "dat mag", tussenrelease): de lezer `lezer-v17` (#32.43–#32.64, §223–§247). Wat er sinds
`lezer-v9` bij kwam:
- geen *niet bevestigd* bij oud nieuws (het nieuwste jaartal in het bericht drie kalenderjaren terug) of bij een
  onafhankelijke bevestiging zonder band (v10);
- een echte kop die woord voor woord op de eigen site van het genoemde medium staat, is *klopt* en groen (v11, v13,
  B60);
- één goede bron is genoeg voor groen, als de lezer *klopt* zegt, niets het tegenspreekt, het niet over een beeld gaat en
  die bron niet het bericht zelf is (v14, v15, B61);
- een uitleg van drie tot vijf feitelijke zinnen. Elke zin draagt het nummer van zijn bron; de code laat een zin weg
  zonder geldig nummer, met een medium dat niet in zijn bronnen staat, of met een getal dat niet in die bron of het
  bericht staat (v12, v15, v16). In het Engels rust de uitleg zo voor ~96% op wat Factiz las (§243);
- het vaste deel van de vraag staat vooraan in het systeembericht en wordt tussen vragen bewaard (prompt caching): bij
  Sonnet ~15–20% goedkoper, met dezelfde woorden als v16 (v17).
De bronnenlijst blijft `bronnen-v6` (B64). De controle staat nog uit, tot de livegang. Op echte screenshots waarschuwt
`lezer-v17` bij 55 van 58 bekend nepnieuws met bewijs, tegen 54 met `lezer-v9` (§247). Uitgebracht op een ingekorte
ronde (PO: "Proefmeting is voldoende voor mij nu"): in het Portugees en Duits alleen een proef van 12 per set, en de
wachttijd is niet gemeten (hieronder bij wat slechter werd).

En op 2026-11-09 (PO: "yes", tussenrelease, B66): de foto bij de bron, in twee lagen (`fotobron = "fotobron-v2"`,
#32.54, DESIGN §4m), en `lezer-v18`.
- *De foto bij de bron:* bij een groen antwoord met een foto kijkt Factiz op de goede (en officiële) pagina's die het
  bericht bevestigen, hoogstens vijf, of dezelfde foto er staat, ook als ze maar een deel van een screenshot vult.
  - Gevonden: groen, met *The photo appears at* en de pagina.
  - Niet gevonden: *News confirmed, photo not found*, met de laag *The news: True* en de laag *The photo*, zonder groen
    voor het bericht als geheel (`photo_not_at_source`, `news_colour`, `photo` in `POST /check`).
  - Het geldt ook voor een groen uit de database.
  - Een pagina die niet binnen 4 s opent, telt als niet gevonden.
  - Het beeld van de gebruiker blijft in het geheugen en wordt alleen lokaal vergeleken (DR3).
- *`lezer-v18`* = v17 met een eerste zin van de uitleg die bij de uitkomst past; dezelfde vraag aan het model.

Onterecht groen bij nepbeelden gaat in zes talen van 16 naar 0 (§248, §249). De controle staat nog uit, tot de livegang.

En op 2026-11-09 (PO: "Ja, release v7", tussenrelease, B69): de bronnenlijst `bronnen-v7` (#32.66, §255). Een medium dat
naar een nieuw adres verhuisde, houdt daar zijn oordeel: 152 media, onder andere franceinfo (van francetvinfo.fr naar
franceinfo.fr), MS NOW (msnbc.com), ICI (francebleu.fr) en Polígrafo (poligrafo.iol.pt). 14 domeinen met *goed* die
verlopen zijn en nu een gokwebsite, spam of te koop tonen, verliezen hun band (zoals huffpostbrasil.com en
dailyherald.news). Gevonden door van elke site in de lijst één keer de voorpagina op te vragen; elke kandidaat is met de
hand nagekeken, en alleen *zelfde medium* telt. Een kop van franceinfo op franceinfo.fr telt nu ook als echte kop op de
eigen site (B60). Op de 5.221 bewaarde antwoorden van de metingen: bij 2 ware Franse berichten kan groen nu, bij 3
nepberichten is er nu een goede tegenspraak, en er is geen groen dat wegvalt of bij nepnieuws bijkomt (§255). De controle
staat nog uit, tot de livegang.

| onderdeel | waarde |
|---|---|
| tekst-embedding | `BAAI/bge-m3@5617a9f61b028005a4858fdac845db406aefb181+casefold` |
| beeldhash | `pdq-256-v1` (256 bits) |
| relatiemodel (alleen offline, clustering-veto) | `MoritzLaurer/mDeBERTa-v3-base-xnli-multilingual-nli-2mil7` |
| poortdrempels | `text_match` 0.87 · `text_match_crosslingual` 0.87 · `text_related` 0.79 · `image_same` 31 · `cluster_same` 0.91 |
| claimvarianten | `[varianten] in_resolver = true`: 460.698 vertalingen in en, pt, es, te en ta, `claude-haiku-5-5/vertalingen-v1`, offline geschreven op openbare claimtekst; de resolver zoekt over claims en varianten, geeft elke claim één keer, en meldt een treffer via een vertaling in `via` (PROTOCOL §5). Daarnaast 3.539 varianten `regel/vraagvorm-v2`: elke claim die als vraag is opgeschreven ook als bewering, door een regel en zonder taalmodel (het vraagteken en het vraagwoord eraf, aan de claimkant ook het Singalese partikel ද, #25.37); een treffer daarlangs meldt `via` met generator `regel` |
| OCR | `[ocr] per_schrift = true`: eerst het schrift (Tesseract-OSD), dan het pakket voor dat schrift; `schrift_zekerheid` 3.0. Daaronder, vanaf `schrift_ondergrens` 1.5, twee keer lezen: met de Latijnse set en met het pakket van het herkende schrift, en de lezing met de hoogste woordzekerheid houden, maar de tweede alleen als minstens `schrift_min_aandeel` 0.5 van haar letters in dat schrift staat (#25.22); onder 1,5 de Latijnse set |
| vraagvorm | `[vraagvorm] aan = true`: een vraag wordt ook als bewering gezocht, per claim de hoogste gelijkenis. Het vraagteken gaat eraf; het vraagwoord of -partikel in het Engels en Turks als de taal zeker is, en هل, क्या, か na です/ます, でしょうか en 吗 altijd. Geen taalmodel; de tegenspraakcontrole draait op de tekst zoals hij binnenkwam (#25.36) |
| rechter | `[rechter] aan = true`: `rechter-d@0744e8eea8ce` (de hash van de gewichten, DR6), `BAAI/bge-reranker-v2-m3` met de bovenste zes lagen en de kop bijgetraind op de rechterset: door Haiku 5.5 geschreven varianten van openbare claimtekst en echte paren met labels van Haiku 5.5 of uit de gelezen steekproeven in `docs/steekproeven` (#30.3). Hij leest per vraag hoogstens diepte 5 kandidaten vanaf `rechter_vloer` 0.79 en moet tussen die vloer en `text_match` minstens `rechter_zelfde` 0.95 geven; vanaf `text_match` is hij een veto, onder `rechter_veto` 0.6 geen `matched`. Het antwoord noemt deze drempels als `text_match_judged`, `judge_same` en `judge_veto` (PROTOCOL verplichting 8). Gekozen met een vooraf vastgelegde regel op de ontwikkelhelft van de zeef (§128–§130). Draait lokaal op de processor; de vraag gaat naar geen taalmodel |
| feitenlaag | `[feiten] aan = true`: 40 vastgestelde feiten in `doublecheck/feiten/kern.json`, elk met bronnen die op de pagina zelf zijn nagelopen, en 280 formuleringen in de laag. Lijkt een vraag op een formulering vanaf `feit_vloer` 0.79 en zegt de rechter *zelfde* vanaf `feit_zelfde` 0.95, dan geeft `categorize` geen `matched` bij een rood of omstreden oordeel; de check blijft als `related` zichtbaar. Geen eigen oordeel: de laag houdt alleen een koppeling tegen (#30.3b) |
| controle per bericht | `[berichtcontrole] aan = false` tot de livegang; Anthropic bewaart de gemaskeerde tekst volgens zijn standaard hoogstens 30 dagen en traint er niet op (B54; zero data retention is geen voorwaarde meer). Eerst kring 1 (`kring1 = true`): een check uit de database die één kant op wijst, zonder model. Anders bedenkt Haiku 5.5 tot drie zoekvragen zoals een factchecker (`speurvraag_model = "claude-haiku-5-5"`, `speurvraag-v1`, met het zwartgemaakte beeld, nooit een oordeel): de eigen site van wie het bericht noemt (met `site:`), het echte nieuws, de bron zelf. Ondertussen zoekt Brave het bericht zelf (`zoeker = "brave-v1"`, het gewone plan, B52: de eerste 50 woorden van de gemaskeerde tekst); daarna de zoekvragen tegelijk, elk de top 10 met per resultaat de band uit de bronnenlijst, een pagina één keer, een mislukte zoekvraag als geen resultaat. Sonnet 5.5 leest één keer (`lezer = "lezer-v18"`, de eerste zin van de uitleg bij de uitkomst passend, het vaste deel van de vraag bewaard tussen vragen, vast JSON-schema, zoekt niet zelf): de resultaten per zoekvraag en de 5 checks uit de database die het meest op het bericht lijken (`api._checks_uit_database`), en zegt of betrouwbare media het zouden melden als het waar was (`zou_gemeld`). Het oordeel is *klopt*, *klopt niet*, *misleidend*, *onzeker*, *klopt grotendeels*, *geen bewering* of *satire*; per check zegt de lezer of die over dezelfde bewering gaat, of de bewering gaat over wat een beeld toont, en of het bericht zelf iets beweert of meldt wat een ander beweert (wie als feit meldt wat iemand zei, doet die bewering zelf). Eén functie zet daaruit een van de tien uitkomsten (`zoekcontrole.na_lezen`, `outcome` in het antwoord): *niet bevestigd* (B57) als het anders *onzeker* of *beeld nodig* was, `zou_gemeld` ja is, een eigen zoekvraag antwoord gaf, geen goede of officiële site het bevestigt en geen check over dezelfde bewering bestaat, nooit met kleur, met de zoekvragen in `searches`; *geen bewering* en *satire* (alleen met een bron die het zegt) nooit met kleur; *klopt grotendeels* alleen met de foute woorden letterlijk in het bericht en de juiste waarde in de titel of het fragment van een goede bron, en niet als een bevestigende bron dezelfde woorden heeft, nooit groen; *over een bewering*: het bericht geen kleur, de bewering zelf wel; *beeld nodig* bij een bewering over een beeld zonder het beeld. Een check over dezelfde bewering met *onwaar* of *misleidend* telt als goede tegenspraak, zoals kring 1; een check maakt nooit groen. *Niet bevestigd* niet bij oud nieuws of bij een bevestiging zonder band. De uitleg: drie tot vijf zinnen, elke zin met het nummer van zijn bron; een zin zonder geldig nummer, met een medium buiten zijn bronnen of met een getal dat niet in de bron of het bericht staat, valt weg. De bronnenlijst (`bronnen-v7`: `bronnen-v6` met 152 verhuisde media op hun nieuwe adres en 14 verlopen *goede* domeinen zonder band, B69; daarvoor de publieke omroepen van de EBU en nl- en fr.wikinews.org *goed*, B64, en es-, pt- en de.wikinews.org, B58) beslist: rood of oranje alleen met een goede tegenspraak (een factcheck van een IFCN-ondertekenaar telt ook bij een lagere band); groen met twee goede uitgevers, of één goede plus één andere die niet laag, geen platform en geen staatsmedia is, of één goede bron die niet het bericht zelf is als de lezer *klopt* zegt en niets het tegenspreekt (B61), of een echte kop woord voor woord op de eigen site van het genoemde medium (B60); een bewering over wat een beeld toont, zonder het beeld nooit groen. Het beeld gaat mee (`beeld = true`, B55), zwartgemaakt met `opknippen.zwart_beeld`: nummers, e-mailadressen, handles, links naar een persoon en de regels met een naam, opnieuw opgeslagen zonder metadata; naar Brave gaat alleen de tekst. Bronnen van staatsmedia krijgen een label (273 domeinen, `doublecheck/staatsmedia.json`). Bij een groen antwoord met een foto de foto bij de bron (`fotobron = "fotobron-v2"`, B66): staat de foto niet op een bevestigende goede of officiële pagina (hoogstens vijf, beleefd opgehaald, binnen 4 s), dan *foto niet bij de bron*, zonder groen voor het bericht als geheel, met de laag van het nieuws (`news_colour`); ook voor een groen uit de database. Alleen de gemaskeerde tekst gaat naar Brave en het model |
| protocol | protocol v0.1 (concept) |
| corpus bij release | bouw 2026-10-10 na de opruiming, plus negen talen en zonder webwinkelrommel op 2026-10-11, en na de witte lijst van uitgevers (B28, 2026-10-14): 108.558 claims, 109.592 checks in de index, 47 talen; 364 claims staan erbuiten (46 vaag, 318 zonder check van een toegelaten uitgever); bronnen: Data Commons ClaimReview-feed (CC BY) en EUvsDisinfo (EEAS, snapshot CC BY) |

| poortcijfer | waarde | bron |
|---|---|---|
| tekstroute, fouten | 5 op 4.839 paren in 21 talen, bovengrens 95%: 0,22%. Daarin 148 ontkenningsparen in zes Zuid-Aziatische talen; met de wachter van vóór #25.20 waren dat 115 fouten (run #60). Eén van de vijf is dezelfde bewering in een Assamese check buiten het cluster. Eerder: 6 op 4.728 met varianten (run #54), 5 zonder (run #53) | §106, §84, §119, run #64 (gelijk aan #61 en #63) |
| dekking | 81,6% (1.931 van 2.365), met de vraag-claims als bewering (#25.37); daarvoor 81,5% (1.927, run #61 en #63), 81,2% (run #54) en zonder varianten 80,9% (run #53); op de 3.528 paren van vóór de negen talen haalde bge-m3 zonder varianten 81,4%, de MiniLM-kandidaat 64,2% | run #64, #61, #54, #53, #47 |
| cross-linguaal | 0 fouten (bovengrens 5,82%), dekking 92,0%; zonder varianten 80,0% (run #53) | run #64 |
| clusterbewust | 5 op 4.839 paren, bovengrens 95%: 0,22%; dekking 1.931 van 2.365, gelijk aan het strikte cijfer (de Assamese check staat in een ander cluster); daarvoor 1.927 (run #62), eerder 6 op 4.728 (run #54) | run #65 (`--clusters`, strikt gelijk aan #64) |
| natuurlijke parafrasen | met varianten 29,2% gevonden en over taalgrenzen 33,3%, zonder 9,9% en 4,1% (toets van §84); de modelkeuze op de toets van §74: 16,5% (MiniLM 10,6%) | §84, §74 |
| beeldroute | 0 valse treffers in 4.000 proeven (1.000 claims × 4 soorten); 0 op 1.000 niet-geïndexeerde screenshots, bovengrens 0,30%. Met OCR per schrift op 1.103 echte M4FC-beelden van ongeveer 10 naar 13 herkend, geen Latijns beeld anders. Met twee keer lezen: M4FC 8 gevonden, 66 verwant, 9 fout (was 8, 65, 9), en in de gemengde benchmark "beeld en tekst wijzen elk naar een andere claim" 9 van 10 juist (was 7) | gemengde benchmark; §29, §80, §107 |
| vraag en bewering | op de toetshelft van de meetset (225 vraagposts in negen talen, door één model geschreven): de juiste claim als `matched` van 52% naar 60% (118 naar 136), niets van 13 naar 10, `matched` op iets anders 0 en 0, geen paar achteruit; Ask: de verwachte claim als eerste kaart 40 van 53 (was 39), niets 9 (was 11), stillevragen 0; gewone webtekst: 0 `matched` op de 15.376 teksten waar de regel iets doet, uit en aan. Met de vraag-claims als bewering in de index (#25.37), richting bewering zoekt vraag op de toetshelft (222): van 48% naar 58% (106 naar 128), niets van 27 naar 15, `matched` op iets anders van 1 naar 0; op 42 echte paren uit de terugkijktoets 16 gevonden voor en na; geen webtekst op 0,79 of hoger bij een nieuwe variant | §118, §119 |
| zeef (B33) | met rechter en feitenlaag, door het echte `/resolve`: hoofdgetal (gemiddelde vindkans op tekst, artikelen en beelden) van 7,1% naar 11,9% op de toetshelft, tekst 34,1%, artikelen 0,5%, beelden 1,1%; precisie van 96,3% naar 99,7% (296 van 297, bovengrens fout 1,6%); vals alarm op gewone webtekst 1 op 270.978. Op de ontwikkelhelft 12,7% bij precisie 329 van 329. De toetshelft was al eerder gezien en is daarom een controle, geen poort; de poort van V1 ligt op een verse set (#28.6 d, B33) | §131, zeefrun `factiz-rechter-d5-feiten` |
| kern (B33) | 0 keer rood of omstreden naast een vastgesteld feit op 317 formuleringen die de laag nooit zag (Factiz 1 zonder rechter: 5 op de vorige kernformuleringen, de rechter zonder laag: 1); de laag hield op 3.637 stukken van de zeef geen enkele terechte ontkrachting tegen | §131, `python -m doublecheck.feitenbasis kerncheck` op `config.toml` |
| bronnenlijst (`bronnen-v7`) | Versie 7 (B69, 2026-11-09): `bronnen-v6` met 152 verhuisde media op hun nieuwe adres (franceinfo.fr 55 keer genoemd in de bewaarde antwoorden) en 14 verlopen *goede* domeinen zonder band; op 5.221 bewaarde antwoorden kan groen nu bij 2 ware Franse berichten, een goede tegenspraak bij 3 nepberichten, 0 groen weg en 0 groen erbij bij nepnieuws (§255). Versie 6 (B64, 2026-11-08): `bronnen-v5` met 6 publieke omroepen van de EBU *goed* (ORF, RTBF, WDR, NDR, SWR, STV) en nl- en fr.wikinews.org *goed*; 16 van de 3.489 bewaarde antwoorden noemen een van die omroepen (§245). Versie 5 (B58, 2026-11-05): `bronnen-v4` met 3 adressen die de PO koos, es-, pt- en de.wikinews.org *goed*; nog niet gemeten op berichten in die talen (#32.42). Versie 4, met de tekens in alle talen (§205): van de 304 toegelaten factcheckers uit het register *goed* van 143 naar 168, en de checks in de database van een goede uitgever van 42.915 naar 51.522 (van 69.444). Op de 400 zoekresultaten van §203 (en, es, pt, de) verandert groen kan met hoogstens 1 per taal. Daarvoor, met `bronnen-v3` (§202): van de 96 grote Spaanse en Portugese redacties en factcheckers uit het voorstel van #32.29: *goed* in het Spaans van 23 naar 45 (van 63), in het Portugees van 5 naar 22 (van 33); op het landdomein .es en Latijns-Amerika van 17 naar 29 websites, .pt en .br van 5 naar 22, .de en .at gelijk (120); in de Engelse antwoorden van de rondes verandert 1 van de 3.287 genoemde websites (van geen band naar *goed*). Geteld op de lijst, niet op zoekresultaten | §202, §205, §255 |
| controle per bericht, de foto bij de bron (`fotobron-v2`, B66) | Op de bewaarde antwoorden van `lezer-v17` en `lezer-v18` (§248, §249): onterecht groen bij nepbeelden zonder de regel 16, met de regel 0 (N 1, Spaans 9, Duits 2, Frans 3, Nederlands 1, verse Engelse N2 1); groen bij echte foto's met de regel W 39 van 45, W-pt 11 van 11, verse W2 52 van 55; de stap mist 1 foto die er staat (een vlak, wazig beeld). De fotostap: p50 0,95 s, p95 2,0 s. Door de echte controle nagelopen op drie bekende berichten | §248, §249 |
| controle per bericht (`lezer-v18`) | Nagerekend op 572 bewaarde antwoorden van `lezer-v17`: de eerste zin past zich aan bij 41 (7%), kleur en uitkomst blijven gelijk. Wachttijd van de hele controle op 10 berichten: p50 10,4 s | §249 |
| controle per bericht (`lezer-v17`), echte screenshots | Op dezelfde 58 en 60 echte screenshots als §220, met het zwartgemaakte beeld: bekend nepnieuws met bewijs gewaarschuwd 55 (`lezer-v9`: 54; de eis van V1: 52), onterecht groen 1 (Malawi, zoals altijd); bij de 60 ware foto's vals alarm 1 (2) en *niet bevestigd* 1 (2). Via de Batch API, ~$0,028 per bericht met Brave | §247 |
| controle per bericht (`lezer-v17`), tekst in andere talen | Spaans, 100 verse onware berichten als op de eerste dag: 63 met bewijs en 22 *niet bevestigd* (samen 85; `lezer-v10`: 82), alarm zonder bewijs 1 (7), onterecht groen 1; bij 62 ware berichten 0 vals alarm en 0 *niet bevestigd*. Portugees en Duits een proef van 12 per set: onwaar 10 en 8 van 12 met bewijs of *niet bevestigd* (v10: 11 en 9); bij 48 ware 0 vals alarm, 1 *niet bevestigd*. Echt nieuws in es, pt en de (110): groen 75 (`lezer-v10`: 81) | §247 |
| controle per bericht, één lezing (`lezer-v9`, B57), echte screenshots | Op de 58 echte screenshots van bekend nepnieuws van §212, met het zwartgemaakte beeld voor Haiku en Sonnet: met bewijs gewaarschuwd 54 (`lezer-v7`: 39; de eis van V1: 52), waarvan 40 met de eigen check als bron; onterecht groen 1 (Malawi, zoals altijd). Op de 60 echte foto's met een ware bewering: groen 43 (`lezer-v7`: 38), vals alarm 2 (3), *niet bevestigd* 2 (beide onterecht: Polígrafo noemde de foto echt). Wachttijd door `controleer` op 12 berichten: p50 7,45 s, p95 11,2 s. Via de Batch API, $0,028 per bericht | §220 |
| controle per bericht, één lezing (`lezer-v9`, B57), tekst als op de eerste dag | Zonder kring 1, zonder checks uit de database, zonder factchecksites: op 100 verse onware berichten 35 rood of oranje met bewijs en 43 *niet bevestigd* (samen 78; de speurstap van `lezer-v8`: 33 met bewijs, 57 zonder kleur; `lezer-v7`, mét factchecksites: 32 gewaarschuwd), onterecht groen 1; op 59 nagemaakte merken 23 met bewijs en 19 *niet bevestigd*, onterecht groen 2; op 50 Wikinews-artikelen groen 46 (92%), vals alarm 0, 1 keer onterecht *niet bevestigd*; op 56 echte koppen van zeven media groen 47 (84%), vals alarm 0; op 40 gewone teksten 33 *geen bewering*, 2 keer *niet bevestigd* bij teksten die onware beweringen bleken | §219 |
| controle per bericht, het beeld mee (`beeld = true`, B55) | Op dezelfde 58 en 60 echte screenshots als §209, met `lezer-v7` en het zwartgemaakte beeld: bij de 60 ware foto's groen van 7 naar 38 (32 van de 45 *beeld nodig* werden groen), vals alarm van 2 naar 3. Bij de 58 screenshots van bekend nepnieuws dezelfde 39 met bewijs, onterecht groen 1 en 1 (Malawi); *geen bewering* van 13 naar 4. Zwart gemaakt bij 6 van de 116 beelden, mediaan 0,65 s. Op andere zoekresultaten dan §209, via de Batch API | §212 |
| controle per bericht, alle uitkomsten (`lezer-v7`) | Op 200 Engelse Wikinews-artikelen (2010–2024): vals alarm 0, *over een bewering* 0 (`lezer-v6`: 60 van 300 ware berichten), *geen bewering* 0, groen 162 (126 zonder Wikinews zelf als tweede goede uitgever), 1 onterechte *klopt grotendeels*. Op 100 gewone tiplineberichten zonder bewering: 87 *geen bewering*, 2 keer rood of oranje (beide terecht: echte weerlegde beweringen). Op 100 verse onware berichten, de eigen check verborgen: 32 gewaarschuwd, 1 onterecht groen. Op 40 verzonnen details: 25 *klopt grotendeels* (24 met de juiste verbetering) en 3 rood of oranje, 4 groen. Satire met de bron: 20 van 20 *satire*; losgeknipte satire: nooit groen (7 *satire*, 9 rood) | §208, §207 |
| controle per bericht, echte screenshots (`lezer-v7`) | Op de 58 echte screenshots van bekend nepnieuws van §201: met bewijs gewaarschuwd 39 (`lezer-v5`: 37), waarvan 24 met de eigen check als bron; geen screenshot die `lezer-v5` met bewijs waarschuwde, raakte `lezer-v7` kwijt; onterecht groen 1 en 1 (Malawi). Op de 60 echte foto's met een ware bewering: vals alarm 2 (`lezer-v5`: 3), groen 7 (3), *beeld nodig* 45. Op andere zoekresultaten dan §201, en via de Batch API. Wachttijd door het echte `POST /check` op de 20 berichten van §206: p50 6,9 s (`lezer-v5`: 4,3 s); zonder de eerste twee p50 6,5 s en p95 9,1 s (4,1 en 7,5 s) | §209 |
| controle per bericht, echte screenshots (`lezer-v5`) | Op 58 echte screenshots van bekend nepnieuws, met `lezer-v3` en `lezer-v5` op dezelfde zoekresultaten: met bewijs gewaarschuwd van 25 naar 37, waarvan met de eigen check als bron van 4 naar 26; onterecht groen 1 en 1; zonder kleur van 31 naar 20. Op 60 echte foto's met een ware bewering: vals alarm van 4 naar 3, groen van 4 naar 3. Geen screenshot die `lezer-v3` waarschuwde, raakte `lezer-v5` kwijt | §201 |
| controle per bericht, tekst (`lezer-v5`) | Op dezelfde zoekresultaten, `lezer-v3` → `lezer-v5`. Op 300 ware berichten van ronde 4: vals alarm van 2 naar 1 (B45: 99%), groen van 236 naar 232. Op 50 verse ware berichten: vals alarm 0 en 0, groen 47 en 47. Op 100 verse onware berichten, met de eigen check verborgen: gewaarschuwd van 22 naar 37 (14 van de 15 erbij met een tegensprekende check uit de database), onterecht groen 1 en 1. Wachttijd door het echte `POST /check`: p50 4,3 s, p95 7,5 s. Kosten per bericht dat zoekt ~$0,015 in plaats van ~$0,012; met het dagplafond van $2 ~130 berichten per dag in plaats van ~158 | §206, §201 |
| controle per bericht, verse berichten | op 100 Engelse claims met een onware of misleidende factcheck die nooit in een set zaten, met kring 1 uit en zonder de factchecksites: 1 onterecht groen (bovengrens 95%: 4,7%), 17 rood, 3 oranje en 78 zonder kleur; zonder de beeldregel was 5 groen geweest in plaats van 2. Op 50 ware berichten uit Portal:Current events: 44 groen (88%), 1 onterecht oranje (98%, B45; bovengrens 95%: 9%), 5 zonder kleur. Wachttijd p50 3,7 s, p95 4,9 s | §182 |
| controle per bericht, ronde 4 (met `lezer-v2`, de lezer zonder beeldregel) | op 300 ware berichten 3 onterecht rood of oranje (99%) en 230 groen (77%); bekend nepnieuws 0 van 100 groen (93 uit de database); onbekend nepnieuws 9 van 100 onterecht groen, 7 om een bewering over een beeld. Daarom kwam de beeldregel van `lezer-v3` | §181 |
| onafhankelijke bevestiging | 839 beweringen met 2 of meer onafhankelijke redacties, geteld over de index en alleen met checks van toegelaten uitgevers (bij de wissel 831, MiniLM 677) | DR7-telling 2026-10-14, §76 |
| zoeklatentie | met varianten zoeken p95 223,3 ms (p50 113,2 ms), gemeten over 109.515 claims plus 460.698 varianten, iets meer dan de index nu (108.558 claims, 456.724 varianten); zonder varianten 24,1 ms; op twee kernen, laptop onder geheugendruk; de rooktest op de server (#23.4) meet het opnieuw | §84 |
| doorvoer | één werker, twee tegelijk: 5,5 vragen/s, p50 365 ms, p95 389 ms, 4,4 GB; zonder varianten op dezelfde machine en dag 6,1/s, 312 en 411 ms, 2,5 GB (op een rustige machine eerder 7,3/s, §77i) | belastingtest, §84 |
| conformantie | conform, uitgang 2 (verplichting 3 onwaargenomen); de nieuwe verplichting 10 (`via` en de varianten in de ontdekking) geslaagd met een proef die alleen via een vertaling matcht | `/numbers`, 2026-10-12, `deploy/conformantie-proeven.json` |
| attributie (E7, sinds 2026-10-12 in het antwoord als `evidence.attributions`) | 14.669 van 108.558 claims in de index met minstens één bonnetje (13,5%): 27.557 van EUvsDisinfo bij 2.855 outlets en platforms en 1.725 van Community Notes (een behulpzame note op X die naar de check verwijst) bij 907 claims, niveau `waargenomen`; categorie en telling van redacties veranderen er niet door | `python -m doublecheck.attributie`, geteld over de index op 2026-10-14 |

**Wat slechter werd.** Van `bronnen-v7` (2026-11-09, B69): The National (thenationalnews.com) krijgt de band van zijn oude
adres thenational.ae, *laag*. In 8 bewaarde antwoorden genoemd; nergens kost het groen. Versie 7 is nagerekend op de
bronnen in de bewaarde antwoorden, niet op nieuwe zoekresultaten; wat Brave voor de verhuisde media echt teruggeeft,
blijkt pas in de volgende Franse meting.

Van de foto bij de bron (2026-11-09, B66): bij echte foto's verliest 5 tot 13% het groen
(W 6 van 45, W2 3 van 55). Het nieuws heet dan wel *klopt*, maar het bericht als geheel krijgt geen groen. Op één gemiste foto
na (een vlak, wazig beeld van Saturnus) was dat telkens terecht: een kapotte link bij de bron, een andere foto bij het
nieuws, of geen goede bevestigende bron. Een groen antwoord met een foto wacht ~1 s langer. De wachttijd van de hele
controle met `lezer-v18` is p50 10,4 s, boven de eis van 7 s (`lezer-v9`: 7,45 s). Dat komt door de langere uitleg sinds v12
en speelde al vóór deze release. Factiz haalt nu live tot vijf pagina's van de bevestigende bronnen op.

Van `lezer-v17` (2026-11-08): bij echt nieuws in het Spaans, Portugees en Duits minder groen,
75 van 110 in plaats van 81 (`lezer-v10`), vooral door de strengere regels voor groen en vaker *geen bewering*. Bij 4
berichten begint de uitleg met "Dit klopt grotendeels" terwijl de uitkomst *onzeker* is: de lezer zegt het, de regels
voor groen geven geen kleur. Bij Portugees nepnieuws vaker *niet bevestigd* in plaats van rood: 4 van 12 tegen 1 bij
`lezer-v10`, met bewijs 6 tegen 10. Een check van
Polígrafo met "Verdadeiro, mas..." werd één keer als tegenspraak gelezen (vals alarm bij een ware foto) en één keer niet
als bevestiging. Niet gemeten: de wachttijd, de uitleg op screenshots en in andere talen, en het Portugees en Duits
voluit (een proef van 12 per set, op verzoek van de PO).

Van de lezing in één keer (`lezer-v9`, B57): twee eisen van #32.41 niet gehaald. Bij waar nieuws
en gewone tekst kwam *niet bevestigd* 3 keer in plaats van hoogstens 2: één keer echt fout (de ontvoering van een
bisschop in Nigeria in 2010, die grote media wel meldden), twee keer bij gewone teksten die onware beweringen bleken. En
de wachttijd: p50 7,45 s in plaats van hoogstens 7 s (`lezer-v7`: 6,9 s), p95 11,2 s; de meting had een rem van 0,25 s
tussen zoekvragen die het product niet heeft. Bij de ware foto's 2 keer onterecht *niet bevestigd*: Polígrafo noemde
beide foto's echt, maar die check stond niet bij de bevestigende resultaten. De twee valse alarmen bij ware foto's (het
zwembad met schermen, de bikini in Rimini) en het onterechte groen bij Malawi blijven. Bij de nagemaakte merken
onterecht groen 2 in plaats van 1. Elk bericht kost vier zoekvragen bij Brave in plaats van één, en ~$0,037 per bericht
live (`lezer-v7`: ~$0,017): met het dagplafond van $2 ~50 berichten per dag in plaats van ~115.

Van het beeld mee (2026-11-03, B55): bij de 60 ware
foto's 3 valse alarmen in plaats van 2 (de eis was hoogstens 2). Het extra
geval is de bikini in Rimini, 1957: Snopes noemt het bijschrift onzeker, de
lezer zei *misleidend*. De andere twee bleven: de foto van Poetin met Fiona
Hill (Snopes noemt hem echt) en het wattenstaafje van 20 cm. Bij nepnieuws
hielp het beeld niet (dezelfde 39), en het onterechte groen bij Malawi blijft:
ook met de foto ziet de lezer niet dat het wrak van een andere crash is. Het
model vergelijkt de foto met de beschrijving van een factchecker, niet met
het beeld zelf. Elke screenshot kost ~$0,002 meer (de beeldtokens), en het
zwartmaken ~0,65 s (mediaan). De wachttijd met het beeld door het echte
`POST /check` is niet gemeten. De foto bevat ook wat de tekstherkenning niet
vindt, zoals gezichten en een naam in het beeld; die gaan mee. De DPIA komt
vóór de livegang.

Van de lezer met de negen uitkomsten (2026-11-03): bij de
verzonnen details 4 keer groen in plaats van 2 (§207); bij één zag de lezer het
foute detail en zei toch *klopt*. Bij de verse onware berichten 32 gewaarschuwd,
tegen 34 met `lezer-v6` en 37 met `lezer-v5` (§206, op andere zoekresultaten);
19 keer zei de lezer daar *klopt niet* zonder goede tegenspraak, dus zonder
kleur. De vraag is langer: Sonnet ~$0,0118 per bericht in plaats van ~$0,0103,
samen met Brave ~$0,017 per bericht dat zoekt, en ~119 berichten per dag binnen
het plafond van $2 in plaats van ~130 (gemeten: ~$0,0175 per bericht, §209). De
wachttijd door het echte `POST /check` is ~2,5 s langer: op dezelfde 20 berichten
p50 van 4,3 naar 6,9 s, en zonder de eerste twee vragen p50 van 4,1 naar 6,5 s en
p95 van 7,5 naar 9,1 s; de eerste vraag na het starten 56 s (§209). Op echte screenshots kregen 13 van de 58 met onleesbare tekst *geen
bewering* in plaats van *onzeker*; "This message makes no checkable claim" is daar
te stellig. In een screenshot zelf komt nog geen kader over de foute woorden
(DESIGN §4i): de pagina markeert ze in wat Factiz las.

Van de lezer met de database (2026-11-03): elk bericht
dat zoekt, kost ongeveer een vijfde meer, en de wachttijd gaat omhoog (p50 van
3,7 naar 4,3 s, p95 van 4,9 naar 7,5 s; de eerste vraag na het starten 33 s,
omdat het tekstmodel laadt). Bij ware berichten werd het 4 keer minder groen
(236 naar 232 van 300): twee keer zette de lezer een check van EUvsDisinfo bij
een bericht dat de bewering van een ander citeert ("Rogozin zei …"), en een
tegensprekende check houdt groen tegen. Op de ware foto's werd er één minder
groen (4 naar 3). De lezer koos soms een check over een verwante, andere
bewering (n-sn-033: "de grootste moskee ter wereld" naast de eigen check over de
oudste); de kleur kwam daar van de eigen check, maar het antwoord toont zo een
bron die er niet bij hoort.

Van de controle per bericht (2026-10-29): met de
beeldregel wordt ook een ware bewering over een foto of video nooit groen.
Hoe vaak dat gebeurt, is niet gemeten, want de verse ware berichten noemden
geen beeld. De ruime regel voor groen kostte op ronde 4 vier valse groenen
bij onbekend nepnieuws (9 tegen 5 met de strenge regel), maar maakte 21 ware
berichten groen. Een andere oorzaak ziet de lezer nog niet altijd (de
iPhone-tiener, §181 en §182), een scheve voorstelling ook niet. En soms is hij
te streng: een waar bericht werd oranje omdat een politicus een dader
beschuldigde (§182).

De rechter maakt een tekstvraag trager en een werker
zwaarder: `/resolve` op tekst van p50 0,21 naar 0,33 s en p95 van 0,26 naar
0,56 s, met één uitschieter van 6,2 s in de zeef (§126), gemeten op de
processor van een M1 en nog niet op de server (op dezelfde laptop met twee
rekenthreads na de release opnieuw: p50 0,30 tegen 0,17 s). De gewichten wegen
2,3 GB in float32 en een werker houdt ze in het geheugen: reken op ongeveer
6,7 GB per werker in plaats van 4,4, en dat is krap op de servermaat uit de
RUNBOOK (8 GB). Op de laptop mat de RSS maar 0,3 tot 0,5 GB meer, maar onder
geheugendruk telt macOS gecomprimeerde pagina's niet mee. De rechter is gekozen op de ontwikkelhelft van de zeef
en gecontroleerd op een toetshelft die we al eerder zagen; een verse meting
volgt met #28.6 d. Op gemaakte valkuilen (rollen omgedraaid, een andere
lading, iets toegevoegd) zegt hij in 63 van 3.521 gevallen toch *zelfde*
(1,8%, de lat was 2%, §130). Lange invoer wijst hij af: een artikel met kop
en inleiding vindt minder dan alleen de kop (§131). De feitenlaag kent 40
feiten en herkent alleen formuleringen die op de 280 in de laag lijken; een
vastgesteld feit buiten de kern beschermt ze niet.

Een vraag kost een tweede zoekvraag (#25.36): op
120 vraagposts verdubbelde de tijd van `/resolve`, p50 van 513 naar 1.007 ms
en p95 van 1.274 naar 3.098 ms. Die tijden zijn gemeten terwijl de benchmark
op dezelfde laptop draaide, dus absoluut te hoog; de verhouding klopt. Een
bewering kost niets extra. En twee keer op de 15.376 geraakte webteksten
wordt een vraag nu `related` op iets wat er niets mee te maken heeft
(vertrouwen in Facebook met betaalgegevens, een Google-account herstellen);
Ask zou die tonen als verwante check (§118).

Twee keer lezen kost tijd op de beelden in de
twijfelband: daar leest de OCR twee keer, binnen dezelfde grens van 10
seconden. De regel is gemeten op beelden die we al kenden; de schriftcontrole
werd bedacht na de eerste uitslag (§107). Een verse meting op onbekende
beelden kan pas als de beeldindex van #25.11 groeit.

Met de varianten één fout meer in de benchmark: 6
in plaats van 5, de bovengrens van 0,22% naar 0,25%. Die zesde is dezelfde
bewering (Salman Khan die Lawrence Bishnoi bedreigt) in een Assamese check
die niet in hetzelfde cluster zit; de benchmark kent alleen het eigen
cluster als goed (§84). Zoeken alleen wordt vijf tot negen keer trager (p95
van 24 naar 223 ms), en een werker draagt 1,9 GB meer (4,4 GB). De winst
zit uitsluitend in de vijf doeltalen: zoekvragen in Hindi, Malayalam,
Kannada en Arabisch vinden niets meer dan voorheen.

Van de wissel naar bge-m3: een vraag kost meer rekentijd en meer geheugen. Op
twee kernen duurt embedden en zoeken samen mediaan 121 ms en in het
langzaamste twintigste 188 ms, tegen 23 en 32 ms met MiniLM; zoeken alleen
gaat van 11,5 naar 21,2 ms (rustige laptop, 94.103 claims). Met de negen
talen erbij en de laptop in gebruik was dat 151 ms en 39,1 ms. Het model weegt 2,3 GB per werker in plaats van
0,5 GB (RUNBOOK). De batchcontrole vindt op de proefset één claim minder:
2 van de 28 bij 7 valse vlaggen op de gemeten poort 0,82, waar MiniLM er 3
vond bij 10 (§77e).

**Wat niet werkt.** Op de zeef, die meet wat er in het wild rondgaat,
vinden we met de rechter 11,9% van wat redacties al checkten; de lat van V1
is 70% (B33). Artikelen (0,5%) en beelden (1,1%) vinden we bijna nooit: daar
zit het grootste gat, en dat is #30.11 en #30.4a. Bijna een vijfde van de bekende claims herkennen we
nog niet (dekking 81,6%), en van twee formuleringen van dezelfde claim die
redacties onafhankelijk schreven, vinden we er met de varianten 29,2% (§84).
Een propaganda-artikel dat óver een ontkrachte bewering gaat, vinden we
bijna nooit: 6 van 835 koppen, hoewel de juiste ontkrachting in een kwart
van de gevallen bovenaan staat (§81). Een bijgesneden beeld verslaat
beide hashes. In de negen Zuid-Aziatische talen kent de
tegenspraakcontrole sinds #25.20 ook ontkenningen, maar die patronen komen
uit grammatica's en zag nog geen moedertaalspreker (#25.20b); in het
Arabisch, Perzisch, Turks, Chinees en Japans kent ze alleen getallen. Khmer,
Assamees en Punjabi zitten met minder dan 500 claims in de index zonder
eigen cijfer. Khmer herkent de schriftherkenning niet, dus twee keer lezen
helpt daar niet (§107). Een bewering die een claim zoekt die als vraag is
opgeschreven, wint met de varianten van #25.37 op de meetset (van 48% naar
58%), maar niet op echte paren: van 42 latere checks die alleen een eerdere
vraag-claim hadden, vond Factiz er 16, voor en na. Daar zit het gat niet in
de vraagvorm maar in andere woorden. De vraagvorm kent zes talen; in de andere valt alleen het
vraagteken weg, en Engelse posts met twee vragen achter elkaar winnen weinig
(van 10 naar 11 van 25).
Het NLI-veto in de clustering trekt onder bge-m3 vaker dezelfde bewering
uit elkaar: 53 van de 84 blokkades in het hele corpus, tegen 18 terecht en
13 twijfel (§86; onder MiniLM 38%, §44). Het blijft aan, omdat de
omgekeerde fout duurder is. De
batchcontrole van modeluitvoer en datasets is geen onderdeel van deze
release: op echte data haalt ze recall 2/28 bij precisie 2/9 (§77e).

De controle per bericht staat uit tot de livegang; zero data retention is sinds B54 geen voorwaarde meer.
Ze is alleen in het Engels gemeten, en op kleine sets. Het beeld gaat niet
mee naar het model, dus een screenshot wordt alleen als tekst gelezen; Brave
in het product en het beeld met toestemming wachten op een besluit van de PO
(REQUIREMENTS §9). Een factcheck als bericht en een oud artikel zijn alleen op
de 15 gelezen gevallen gezien, niet vers. En zonder de factchecksites wordt
nepnieuws meestal niet rood maar blijft het zonder kleur (78 van 100, §182).
Met de lezer met de database waarschuwt de controle bij 37 van de 58 echte
screenshots van bekend nepnieuws met bewijs; de eis van V1 is 52. Met `lezer-v7`
zijn het er 39 (§209), met `lezer-v9` 54 (§220). Een ware tekst
met een valse foto blijft groen (n-sn-034). De database helpt alleen bij wat er
al in staat, en de lezer is alleen in het Engels gemeten (118 screenshots, 450
tekstberichten). Het beeld als tweede stap zit er niet in (zie het voorstel
hieronder).
In het Spaans en het Portugees krijgen 27 grote redacties zonder teken geen band
(La Vanguardia, El Confidencial, g1, Clarín, Expresso en andere). Ze tellen dan
alleen als tweede bron naast een goede. Hoe vaak een Spaans of Portugees bericht
daardoor geen groen krijgt, is niet gemeten op zoekresultaten (§202).

## Voorstel: het beeld als tweede stap *(concept, nog geen release; de PO beslist; PLAN #32.30)*

*Opgesteld 2026-11-02 op verzoek van de PO, met de lezer met de database als deel 1. Dat deel is op 2026-11-03
uitgebracht als tussenrelease (de kaart hierboven, §201, §206). Wat daarvoor nog open stond, geldt voor de hele
controle: een steekproef met de hand op het maskeren
(B43). Brave is besloten (B52). Dit is geen kaart onder "Huidige release", dus de suite houdt haar niet tegen de
config.*

### Deel 2: het beeld als tweede stap

**Wat het deed (§201).** Van 37 naar 44 van de 58 screenshots, telkens met een check die niet in de beste 5 van de
woorden stond (6 keer de eigen check). Op de ware foto's kwam één vals alarm terug (w-04437, van 3 naar 4, evenveel als
`lezer-v3`). Het beeld bevestigt een check als de punten van de screenshot passen op een beeld dat `rol-v3` in dat
artikel *viraal* noemt (de vergelijking van #32.21).

**Waarom het nog niet in het product kan:**

1. **De index van de beelden is te klein, en gunstig samengesteld.** De vergelijking liep op 15.408 van de 104.392
   factcheckartikelen in de database, met de eigen artikelen van de sets eerst. In het product moet elk artikel erin:
   - ~89.000 artikelen beleefd ophalen: per site één verzoek met robots.txt. De grootste site, FACTLY, heeft er ~12.000:
     reken op enkele dagen.
   - Per beeld alleen PDQ, de punten en de tekst eromheen, nooit het beeld (B35).
   - De rol per artikel met `rol-v3`: Haiku via de Batch API op openbare artikelen, ~$12–15.
   - Van elk viraal beeld de tekst (OCR, lokaal) en een beschrijving (Haiku, ~$5).
   - Op schijf naar schatting 4–5 GB aan punten, alleen voor de virale beelden; eerst te meten op een proef.
2. **Vier van de zeven komen alleen via een beschrijving van de foto door een model** (n-sn-002, 017, 035, 041): de
   beschrijving van de screenshot tegen de beschrijvingen van de virale beelden. Dan gaat het beeld van de gebruiker
   naar Haiku, en B43 zegt "nooit het beeld". Dat vraagt een besluit over het voorstel "het beeld met toestemming naar
   het model" (REQUIREMENTS §9). Zonder dat besluit blijven twee lokale ingangen over: de woorden tegen de claims, en de
   woorden tegen de tekst op de virale beelden. Daarlangs liepen 3 van de 7 (n-sn-007, 008, 043). Dat is niet apart
   gemeten.
3. **De code zit in de metingen** (`vindronde`, `beeldbevestiging`). De vergelijking en het opzoeken moeten naar de kern
   (`tests/test_kern.py`). `beeldvraag` en `beeldrolvraag` staan er al.
4. **Opnieuw meten op de volle index.** Zeven keer zoveel artikelen geven meer kans op een beeld dat vals bevestigt.
   Daarom N en W opnieuw (~$2), met eisen vooraf, en het vals alarm bij W apart.

**Wat B43 en ZDR vragen (deel 2):**
- *Met de beschrijving:* het beeld gaat live naar Haiku (niet via de Batch API), onder de standaard van Anthropic
  (B54). Of dat met toestemming per controle moet, is een besluit van de PO. Het kost per screenshot naar schatting minder dan een tiende cent extra, en
  Haiku kan tegelijk met Brave lopen.
- *Zonder de beschrijving:* niets nieuws. De punten van de screenshot blijven in het geheugen en gaan daarna weg (DR3).
  Het vergelijken is lokaal, ~50 paren per screenshot, ~0,2 s op de M1 (§194: 113.281 paren in 513 s).
- *Versies voor de kaart:*
  - `sift-1000-v1`, `sift-ransac-v2` en `pdq-256-v1` voor de vergelijking;
  - `rol-v3` voor de rol;
  - `beschrijving-v1` als het beeld naar het model mag.

## Richting in releases (geen belofte)

Sinds B23 (2026-10-10) is de kaart het doel en loopt de volgorde langs de vier
lagen; elke release blijft gebonden aan een verschoven cijfer.

- **Factiz 2** is akte 2: de plug-in met het labeltje in de tijdlijn (B12 naar
  voren), het brede corpus met toegeschreven attributie, en de archieffunctie.
  Poortcijfers: dekking en fout op de bestaande benchmark, plus het aandeel
  claims met minstens één attributie.
- **Factiz 3** is de kaart: verspreiding uit publieke waarnemingen, netwerkpijlen
  uit attributies, STIX-export. Poortcijfer: het aandeel claims met minstens één
  waarneming en minstens één attributie, met bron en bewijsniveau per pijl.
- **Factiz 4** zijn bronketens, altijd toegeschreven, nooit door ons beweerd.
- **De AI-kop** (B17, controle van modeluitvoer en datasets) blijft een eigen
  lijn met zijn eigen poort: een geslaagde hermeting na #21.6 en #21.7.
- **Tussenreleases 1.x**: winst uit #21.7 als die de dekking verschuift zonder
  nieuwe capaciteit, en toegelaten talen.
- **De EU-variant**: Claude in een EU-regio (B43), samen met de EU-server van de
  livegang (B21). Dan weegt de PO zero data retention opnieuw (PO 2026-11-03,
  B54): Amazon Bedrock laat elk account `data_retention_mode: none` zetten, in
  een EU-regio, of een afspraak met Anthropic. Daarmee ook opnieuw: het beeld
  naar het model.

## Eerdere releases

### Factiz 1-kandidaat op MiniLM (nooit uitgebracht, vervangen op 2026-10-11)

*Vervangen vóór de lancering door bge-m3, dat op dezelfde 3.528 paren minder
fouten maakt en meer vindt (BENCHMARK §73–§75). Bewaard omdat de vergelijking
bij het logboek hoort.*

De resolver als het collectieve geheugen van de factcheckers: tekst en
screenshot in, bronnen uit.

| onderdeel | waarde |
|---|---|
| tekst-embedding | `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2+casefold` |
| beeldhash | `pdq-256-v1` (256 bits) |
| relatiemodel (alleen offline, clustering-veto) | `MoritzLaurer/mDeBERTa-v3-base-xnli-multilingual-nli-2mil7` |
| poortdrempels | `text_match` 0.92 · `text_match_crosslingual` 0.85 · `text_related` 0.80 · `image_same` 31 · `cluster_same` 0.93 |
| protocol | protocol v0.1 (concept) |
| corpus bij release | bouw 2026-10-10: 94.246 claims, 95.394 checks, 38 talen; bronnen: Data Commons ClaimReview-feed (CC BY) en EUvsDisinfo (EEAS, snapshot CC BY) |

| poortcijfer | waarde | bron |
|---|---|---|
| tekstroute, fouten | 12 op 3.528 paren in zestien talen, bovengrens 95%: 0,55% (vervangt 0,68% op vijf talen, run #40) | run #43 |
| dekking | 64,2% | run #43 |
| cross-linguaal | 0 fouten (bovengrens 5,82%), dekking 64,0% | run #43 |
| clusterbewust | 9 op 3.528 paren, bovengrens 95%: 0,44%; dekking 1.154 van 1.793 | run #45 (na incrementeel clusteren, #25.4) |
| beeldroute | 0 valse treffers in 4.000 proeven (1.000 claims × 4 soorten); 0 op 1.000 niet-geïndexeerde screenshots, bovengrens 0,30% | gemengde benchmark; §29 |
| onafhankelijke bevestiging | 678 beweringen met 2 of meer onafhankelijke redacties | DR7-telling |
| zoeklatentie | p95 11,3 ms op het volle corpus | §61 |
| conformantie | conform, uitgang 2 (verplichting 3 onwaargenomen) | `/numbers` |
| attributie (E7, nog niet op de draad) | 13.779 van 94.246 claims met minstens één bonnetje (14,6%), 27.613 bonnetjes bij 3.010 outlets, niveau `waargenomen` | `python -m doublecheck.attributie` |

**Wat niet werkt.** Ruim een derde van de bekende claims herkennen we
niet (dekking 64,2%). Een bijgesneden beeld verslaat beide hashes. Ongeveer
zeventig van de 226 clusterblokkades splitsen dezelfde bewering (§44). Drie
talen zitten in de index waarvan het model de claims niet uit elkaar houdt
(§39). De batchcontrole van modeluitvoer en datasets is geen onderdeel van
deze release: op echte data haalt ze recall 3/28 bij precisie 3/16 (§60).
