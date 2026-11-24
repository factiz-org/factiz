# Is dit de slimste route? De route naar V1 tegen de markt — 2026-10-27

> De PO (2026-10-27): "Beoordeel dit plan en vergelijk het met andere dingen
> die op de markt zijn. Is dit een goede route die we nu nemen, en voegen we ook
> iets toe als we uitkomen?" En: "Ik wil bijvoorbeeld dat zo'n V1 al te gebruiken
> is door factcheckers en serieus kan worden genomen door een redactie of een
> OSINT-groep." Het einddoel: mensen laten weten wat echt of nep is; verkopen
> aan platforms (taggen) en AI-labs (corpus controleren); nepnieuwsnetwerken in
> kaart brengen.
>
> Beoordeeld: de route van B46 (`docs/V1-ROUTE.md`, PLAN etappe 32). De bronnen
> staan onderaan.

## 1. Het korte antwoord

- **Het fundament van de route klopt.** Eerst omschrijvingen en testsets, per
  taal meten, eerlijk *onzeker*, labels door een mens nagelezen. Zonder dat
  neemt geen redactie ons serieus.
- **De kern van V1 is niet de slimste keuze.** Zoals V1 nu omschreven is
  (screenshot erin, oordeel eruit), doet het wat Grok, ChatGPT en Perplexity al
  gratis doen, in elke taal en ook op beelden. Wat Factiz beter kan, zit niet in
  het oordeel zelf, maar in wat eromheen staat:
  - eerdere checks van dezelfde bewering, in alle talen;
  - bronnen die echt kloppen;
  - eerlijk *onzeker*;
  - een gepubliceerde foutmarge per taal.
- **Voorstel: hetzelfde fundament, een scherpere kern.** V1 wordt *het
  bewijsdossier* voor wie beroepsmatig controleert: factcheckers, redacties en
  OSINT-groepen. Het oordeel is één onderdeel ervan. Daarvoor komen er drie
  stappen bij (§4).

## 2. Wat elke doelgroep wil, en wie het nu levert

| doelgroep | wat ze willen | wie het nu levert | waar dat tekortschiet | wat Factiz kan toevoegen | betalen ze? |
|---|---|---|---|---|---|
| **iemand met een screenshot** | snel weten of het klopt | Grok (447.083 verzoeken "is this true" op X in een half jaar), ChatGPT, Perplexity; de WhatsApp-tiplines van factcheckers (Meedan Check) | bronnen in 30–60% van de gevallen fout; valse claims in 28–35% herhaald; slechter buiten het Engels; zelden "weet niet" (RESEARCH §0, §6) | bonnetjes die kloppen, eerlijk *onzeker* | nee; het bereik is het probleem |
| **factcheckers en redacties** | tijd winnen: is dit al ergens gecheckt, wat gaat er nu rond, klopt dit beeld, het bewijs bij elkaar; de mens beslist | Full Fact AI (betaald; 40+ organisaties, 3 talen, 30 landen); de CEDMO Fact-check Finder (gratis, in de plug-in van vera.ai/InVID, vooral Europese talen); Meedan Check (open); Google Fact Check Explorer; Factiverse (350.000 checks, betaald); InVID voor beelden | weinig talen (Full Fact), geen gepubliceerde foutmarges, citaten niet nagelopen | 47 talen, elk gemeten; foutmarges openbaar; open code; een dossier met nagelopen citaten | weinig: 76% van de factcheckers is kwetsbaar of in crisis, 53% gebruikt al AI (IFCN 2026) |
| **OSINT-groepen en onderzoekers** | een verhaal volgen over talen en jaren, het netwerk erachter zien | Graphika, Cyabra, Blackbird.AI, Alethea (gesloten, voor overheden en merken); DFRLab; EUvsDisinfo | "er is geen analytisch hulpmiddel dat de draden samenbrengt" (Disinformation Laundromat); duur en gesloten | dezelfde bewering over talen en jaren heen (316 keer opnieuw ontkracht in een andere taal), open en na te rekenen | overheden en onderzoeksfondsen |
| **AI-teams** | trainingsdata en antwoorden controleren op bekende valse verhalen | NewsGuard (een gesloten catalogus van valse verhalen, in licentie; politiek omstreden) | gesloten; wat erin staat is niet na te gaan | 110.000 checks in 47 talen onder CC BY, lokaal te matchen zonder model per stuk: de controle in bulk (versie 2) | ja |
| **overheden en gezondheidsdiensten** *(idee van de PO, 2026-10-27, na P11; nog niet uitgezocht)* | gezondheidsfabels die rondgaan vroeg zien en zelf taggen, met een bron, voordat ze schade doen | nog uit te zoeken | nog uit te zoeken | in P11 kreeg Factiz 40 van de 40 bekende gezondheidsfabels als onwaar, met de check van een redactie als bron; het gewone model 39 van 40, maar zonder die check. Maar: de 40 waren al gecheckt; nieuwe fabels zijn nog niet gemeten. Zelf taggen vraagt de controle in bulk (versie 2). Nederlands is nog geen taal van V1. En we taggen de bewering, nooit de mensen die haar delen: meekijken door een overheid is gevoelig | waarschijnlijk, via opdrachten of fondsen |
| **platforms** | taggen op grote schaal | eigen systemen en Community Notes; X laat sinds juli 2025 ook AI van derden notes voorstellen, die mensen beoordelen; Meta stopte in januari 2025 in de VS met factcheckers, buiten de VS (nog) niet | Logically, een leverancier aan platforms, ging in juli 2025 failliet; lange verkooptrajecten | later: een AI-schrijver voor Community Notes als kanaal, met een openbare toets (mensen beoordelen elke note) | moeilijk |

**Wat dat zegt:**
- Het oordeel per screenshot is voor gewone gebruikers al gratis te krijgen.
  Wij zijn eerlijker, maar dat ziet iemand in een appgroep niet meteen.
- Het terugvinden van eerdere checks doen er al meer (Full Fact, CEDMO, Meedan,
  Google), maar geen ervan in 47 talen met openbare foutmarges.
- Niemand levert een dossier dat een redactie kan overnemen: de bewering,
  eerdere checks in alle talen, nagelopen citaten van betrouwbare bronnen,
  waarom het nep is, en wat nog onbekend is.

## 3. Het plan beoordeeld

**Wat goed is, en blijft:**
- omschrijvingen en testsets vóór techniek (stap 32.2–32.5);
- per taal meten, elke taal haar eigen cijfer, een taal zonder gehaalde eis
  geen oordeel;
- de acht uitkomsten, met eerlijk *onzeker* en *beeld nodig*;
- labels door een mens nagelezen;
- eerst zelf tevreden.

**Wat niet het slimst is:**
1. **Het meeste geld gaat naar het deel dat iedereen al heeft.** Sonnet met
   webzoeken kan elke concurrent aanroepen. Moeilijk na te maken zijn drie
   andere dingen:
   - de database: 110.000 checks in 47 talen, gekoppeld en gemeten;
   - de meetdiscipline, met gepubliceerde fouten;
   - bonnetjes die kloppen.

   De route zet ~$48 op het meten van het oordeel in vier talen, en niets op
   die drie.
2. **De zoekfunctie vindt in het wild maar 22% van wat al ontkracht is**
   (§116). Dat is onze kern. Het oordeel steunt erop: van de terechte *klopt
   niet* op echte berichten kwamen er 15 van de 17 uit de database (§149).
   De route verbetert hem niet.
3. **Citaten worden niet nagelopen.** Chatbots falen daarop in 30–60% van de
   gevallen. Voor een redactie is één verzonnen citaat genoeg om af te haken.
   RESEARCH §7 noemt het al, "nog niet gebouwd".
4. **Bronnen krijgen geen betrouwbaarheidsoordeel.** Staatsmedia en het
   Pravda-netwerk kunnen als bewijs opduiken; in het Mandarijn citeerden
   chatbots Chinese Sputnik-sites (RESEARCH §6). Voor een OSINT-groep is dat
   onacceptabel. RESEARCH §7: "nog niet gebouwd".
5. **Chinees is duur voor wat we hebben:** 1.014 checks, waarvan 12 waar. De
   Chinese factcheckwereld zit vooral in Taiwan. Voor OSINT is Chinees wel
   belangrijk (beïnvloedingscampagnes). Twee andere kandidaten voor de vierde
   taal:
   - *Russisch*: voor OSINT in Europa het belangrijkst, met het Pravda-netwerk
     en Doppelganger. Maar 568 checks; het materiaal van EUvsDisinfo hebben we
     wel.
   - *Portugees*: het meeste materiaal, 7.859 checks, waarvan 6.074 onwaar en
     497 waar.
6. **Geen enkele gebruiker kijkt mee tot na V1.** Zo kunnen we een V1 bouwen die
   technisch goed is maar niet past in hoe een redactie werkt. PLAN #23.13 ("Drie
   redacties spreken, vóór we een redactietool bouwen") staat er al. Praten is
   geen lanceren.

## 4. Voorstel: dezelfde route, een scherpere kern

**V1 is het bewijsdossier.** Bij elke screenshot of tekst, in de talen van V1:
1. **wat het is:** de acht uitkomsten, met de stand op de schaal;
2. **eerdere checks** van dezelfde bewering, in elke taal, met datum: "in 2019
   ontkracht door X, in 2024 opnieuw door Y, in het Spaans";
3. **het bewijs:** citaten die letterlijk op de bronpagina staan, nagelopen,
   van bronnen met een betrouwbaarheidsoordeel;
4. **waarom het nep is**, in de taal van de gebruiker, uit dat bewijs;
5. **wat onbekend is:** wat er niet gevonden werd;
6. **een dossier om mee te nemen:** een export met de versies van de machine,
   die een factchecker kan citeren. De gebruiker bewaart het zelf; Factiz
   bewaart het bericht niet (DR3).

Een gewone gebruiker ziet daarvan het oordeel bovenaan; een redactie ziet het
hele dossier.

**Wat er aan etappe 32 verandert:**

| | wat | waarom | kosten |
|---|---|---|---|
| **nieuw, eerst** | **Drie gesprekken** (#23.13): twee factcheckredacties (één Spaanstalige, één Duitstalige) en één OSINT-groep. Welke van de zes onderdelen besparen hun tijd? Wat moet erin om het te gebruiken? | V1 omschrijven met gebruikers, niet ervoor | $0 |
| **nieuw** | **Citaten nalopen:** elke geciteerde zin moet letterlijk op de bronpagina staan. Eis: minstens 99% | de grootste zwakte van chatbots, en waar een redactie op afhaakt | ~$0, lokaal ophalen |
| **nieuw** | **Betrouwbaarheid van bronnen:** een lijst met domeinen die nooit als bewijs tellen (staatsmedia, het Pravda-netwerk), en een melding als een onderwerp weinig betrouwbare dekking heeft | nodig voor OSINT | $0 |
| **nieuw** | **De zoekfunctie in het wild verbeteren:** eerst meten waarom 78% van het al ontkrachte niet gevonden wordt, dan één verbetering | onze kern, en de bron van de meeste bewezen *klopt niet* | ~$5 |
| 32.7 | *Waarom het nep is* wordt onderdeel van het dossier, uit de nagelopen citaten | | gelijk |
| 32.8 | per taal meten, nu ook op de citaten (≥99%) en de eerdere checks | | gelijk |
| taal 4 | Chinees, Russisch of Portugees: opnieuw besluiten | §3.5 | |

Samen ~$75–85 in plaats van ~$65–75.

**Na V1, als kanaal:** een AI-schrijver voor Community Notes op X. Factiz stelt
notes voor met bronnen, en mensen van uiteenlopende kanten beoordelen ze in het
openbaar. Dat is een publieke toets van onze betrouwbaarheid, en bereik zonder
een platform iets te verkopen. Eerst nagaan of X dit nog voor derden openstelt,
en onder welke voorwaarden.

## 5. Voegen we iets toe als we uitkomen?

- **Als V1 alleen "screenshot erin, oordeel eruit" is: weinig.** Grok en ChatGPT
  doen dat gratis en overal. Wij zijn betrouwbaarder, maar dat valt een gewone
  gebruiker niet op, en een redactie gebruikt geen oordeel zonder dossier.
- **Als V1 het bewijsdossier is: ja.** Geen bestaand product combineert:
  - eerdere checks in 47 talen;
  - nagelopen citaten;
  - eerlijk *onzeker*;
  - foutmarges per taal, openbaar;
  - open code;
  - een screenshot dat de EU niet verlaat.

  Full Fact AI komt het dichtst bij, maar is gesloten, werkt in drie talen en
  geeft geen dossier. CEDMO koppelt alleen aan eerdere checks. NewsGuard is
  gesloten en omstreden.
- **De weg naar de grote doelen loopt erdoorheen:**
  - het taggen voor platforms en het controleren van corpora voor AI-labs
    vragen dezelfde database, plus de controle in bulk (versie 2);
  - het in kaart brengen van netwerken vraagt dezelfde koppeling van
    beweringen over talen en jaren.

  Elke verbetering aan de database en de koppeling in V1 telt dus ook voor
  later. Een beter oordeel alleen telt minder.

## 6. Wat de PO beslist

1. **De kern van V1:** het bewijsdossier voor professionals, met het oordeel
   als onderdeel, of het oordeel per screenshot (B46 zoals nu)?
2. **De vier nieuwe stappen:** de gesprekken, citaten nalopen, de
   betrouwbaarheid van bronnen, de zoekfunctie in het wild: erbij?
3. **Taal 4:** Chinees, Russisch of Portugees?

## Bronnen

- Full Fact AI, bereik in 2026: https://niemanlab.org/2026/06/full-fact-is-battling-ai-generated-elections-content-with-ai-tools-of-its-own en https://fullfact.org/ai/about
- CEDMO Fact-check Finder: https://cedmohub.eu/?p=135734
- Meedan Check: https://leadstories.com/analysis/2024/08/tipline.html
- Factiverse: https://techcrunch.com/2024/11/17/norwegian-startup-factiverse-wants-to-fight-disinformation-with-ai
- NewsGuard Misinformation Fingerprints: https://www.newsguardtech.com/insights/how-ai-companies-can-use-newsguard-trust-data-for-text-image-video-and-audio-generators/ en https://www.semafor.com/article/03/17/2024/newsguard-launches-suite-of-ai-anti-misinfo-tools
- Grok als factchecker op X: https://indicator.media/p/grok-is-this-true-how-x-s-chatbot-performs-as-a-fact-checking-tool
- AI-schrijvers voor Community Notes: https://betanews.com/2025/07/02/x-launches-ai-bot-pilot-to-write-community-notes-fact-checkers/
- IFCN, State of the Fact-Checkers 2026: https://www.poynter.org/wp-content/uploads/2026/03/2026-State-of-Fact-Checkers-4.pdf en https://www.niemanlab.org/?p=251187
- Meta buiten de VS: https://tech.co/news/meta-fact-checkers-outside-of-us
- Narrative intelligence (Cyabra, Graphika): https://cyabra.com/solutions/intelligence-osint-analysts/ en https://www.govconwire.com/articles/graphika-guyte-mccord-customized-osint-tools
- Disinformation Laundromat: https://gulbenkian.pt/emifund/projects/the-disinformation-laundromat-an-osint-tool-to-detect-disinformation-and-amplification-networks/
- Audits van chatbots en Logically: `docs/RESEARCH.md` §3.3, §6, §7
