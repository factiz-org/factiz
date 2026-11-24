# Routekaart naar V1 — eerst bewijzen dat het kan, dan bouwen (2026-10-27)

> De PO (2026-10-27), bij de opbouw in lagen: "Als je dit stuk nu bekijkt, is
> dit volledig? Is dit een goed plan? Mee eens? haalbaar etc? Nu is denk ik de
> tijd om de routekaart uit te stippelen en er zo lang mogelijk over na te
> denken, zodat we niet later erachter komen dat het niet de goede route was. We
> moeten eerst exact weten wat de route naar succes is en vastleggen of het
> kan."
>
> Twee beoordelingen liggen hieronder samen. De eerste is van mij. De tweede
> komt van een onafhankelijke beoordelaar: een tweede Claude die alleen de
> documenten kreeg, niet mijn conclusies, met de opdracht te zoeken naar wat
> ontbreekt, wat niet kan en waar het misgaat. Zijn feiten heb ik in de stukken
> nagekeken. Bouwt voort op `docs/V1-POSITIE.md`, `docs/V1-MARKT.md`,
> `docs/V1-ROUTE.md` (B46) en RELEASES "Een nieuw model: de modelpoort".

## 0. Het overzicht (stand 2026-10-27, na het gesprek met de PO)

**Waar we staan.**
- *Gebouwd:*
  - de zoekfunctie: 110.000 factchecks in 47 talen, klaar maar niet
    gelanceerd;
  - de controle, die nog uit staat: Sonnet, de database, het web en de regels
    van ronde 5.
- *Gemeten, op Engelse tekst:*
  - rood klopt in 97–99% van de gevallen;
  - bekend nepnieuws 99%, maar in de woorden van de factchecker zelf;
  - echte screenshots 54%;
  - nieuw nepnieuws zelf herkend 21%;
  - bekende leugens met alleen het web 37 van 50;
  - ~$0,04 per bericht, 95% binnen 7 s.
- *Wat we leerden:*
  - onze testsets kwamen bijna allemaal uit de database, en alle labels las
    Claude, dus onze cijfers zijn scheef;
  - de database is de sterkste bron als ze raakt, maar geen dekking: in het
    wild 22–29%;
  - de aanvoer van nieuwe factchecks staat stil;
  - de site belooft dat Factiz nooit zelf oordeelt (#23.16);
  - de grote labs bewaken hun eigen model; een onafhankelijke, meetbare
    detector bestaat niet.

**Waar we naartoe gaan.**
- *De missie:* Pangram voor nepnieuws. Een onafhankelijk hulpmiddel dat van
  elke tekst of screenshot zegt wat het is, en waarom, met bronnen.
- *Vertrouwen:* wat het zegt, kun je vertrouwen. Bij wat echt niet te weten
  is, zegt het eerlijk "weet ik niet", maar nooit bij wat iedereen weet (de
  vloer).
- *V1:*
  - tekst en screenshots, in het Engels, Spaans, Duits en Portugees;
  - het antwoord in drie delen: inhoud, herkomst, en vorm en afzender;
  - de context uit drie of vier onafhankelijke algemene bronnen, met de
    database als één bron;
  - een bronnenlijst die zegt welke bronnen niet tellen;
  - het model is een onderdeel dat we wisselen als het via de modelpoort beter
    is.
- *Voor wie:* eerst factcheckers, redacties en OSINT-groepen. Later platforms
  en AI-labs (de controle in bulk, versie 2) en het in kaart brengen van
  netwerken.
- *Pas naar buiten* als we zelf tevreden zijn.

**De tussenstappen.**

| fase | wat | kosten |
|---|---|---|
| **0 Bewijzen dat het kan** | elf proeven (§5). Eerst die op data: de aanvoer (P3), de gemiste screenshots (P4), het plafond met beeld (P5), bekend nepnieuws in echte vorm (P6), een tegenspeler (P8), de modelpoort (P9), materiaal per taal (P10) en de gebruikerstoets van de PO (P11). Die met mensen wachten: een factchecker labelt blind (P1), drie redacties (P2), eensgezindheid over sturing (P7) | ~$25, plus mensen |
| **1 De keten in het Engels** | aanvoer, beweringen eruit halen, de herkomstcheck, de bronnenlijst met een werkwijze, drie of vier bronnen, citaten nalopen en draagt de bron het, waarom, screenshots, tegenspeler, de vaste toets met een vers en een geheim deel, evenwicht | ~$20–30, plus nalezen |
| **2 De talen** | Spaans, Duits, Portugees | ~$15 per taal, plus nalezen |
| **3 Zelf tevreden** | de hele toets op een geheime set, door een mens nagekeken | ~$10 |
| **4 Naar buiten** | de belofte herschrijven, klaarmaken, de redacties van P2 als eerste gebruikers | |
| **5 Versie 2** | de controle in bulk, beelden en video, netwerken, Chinees en Russisch | |

## 1. Het korte antwoord

- **Het principe klopt.** Het model is een onderdeel. Wat Factiz is, zijn de
  lagen eromheen en de meting. Daarmee bouwen we op de labs in plaats van met
  ze te concurreren.
- **De opbouw zoals hij in de tabel stond, is niet volledig.** Er ontbreken
  lagen, en twee daarvan kunnen het hele plan laten mislukken: de waarheid
  waartegen we meten, en de aanvoer van factchecks (§3).
- **We hebben het product vandaag vier keer anders omschreven:**
  1. de tussenbalans;
  2. de factcheckmachine van B46;
  3. het bewijsdossier;
  4. Pangram voor nepnieuws.

  Dat zegt dat de vraag "wie gebruikt dit, en waarvoor?" nog niet beantwoord
  is. Dat los je niet op door verder te denken, maar door het aan gebruikers
  voor te leggen.
- **Een deel van wat we beloofden, is niet te bewijzen.** "Hoogstens 1 op 100
  onterecht, per label, per taal, per vorm" vraagt ~12.000 door mensen
  nagekeken berichten. *Sturend* en *onzin* zijn oordelen waar zelfs mensen het
  niet over eens worden (§4).
- **Daarom eerst fase 0:** elf proeven die zeggen of het kan, de meeste
  goedkoop, met vooraf vastgelegd wat "door" en wat "anders" betekent. Pas
  daarna leggen we de route vast (§5, §6).

**De vloer** *(aantekening van de PO, 2026-10-27)*. Eerlijk *onzeker* zeggen
mag niet betekenen dat Factiz het laat afweten bij wat iedereen weet. De PO:
"Als hij bij overduidelijk niet-kloppende dingen zegt: 'Ik weet het niet', dan
zou iemand bij heel veel van zulke antwoorden concluderen dat ons systeem niet
werkt." En: "Tegenwoordig verwacht ik namelijk van een model dat het in ieder
geval voor de meeste dingen net zo goed presteert als een gewoon taalmodel,
Google of gewoon algemene kennis." Dus: op overduidelijke leugens en waarheden
is Factiz minstens zo goed als een gewoon taalmodel. Gemeten tot nu: van 50
leugens die al jaren rondgaan bewees Sonnet met alleen het web er 37 (§150);
van 180 valse zinnen over vastgestelde feiten 92%, en wat het miste, zocht het
niet op (§156). De strenge regel (*klopt niet* alleen met een bron) kan hier
te streng zijn. Proef P11 zoekt het uit.

## 2. Wat er in de vorige stukken niet klopte

- *V1-POSITIE liet twee uitkomsten van B46 weg:* **over een bewering** en
  **beeld nodig**. Juist die droegen de regels van ronde 5: ware artikelen van
  97% naar 99%, en beweringen over beelden van groen naar 0 van 50 (§159). Ze
  horen erin.
- *Eén label per bericht mengt twee dingen die los van elkaar staan:* of het
  waar is, en hoe het gebracht wordt. Een waar bericht kan bangmakend zijn, een
  onwaar bericht zakelijk.
- *"Een fractie van een cent per bericht" klopt niet voor V1.* Op echte
  tiplineberichten had maar 4 van de 250 een check met een gelijkenis van 0,80
  of meer. Het model was nodig om de rest te herkennen (§149). Goedkoop wordt
  het pas met de controle in bulk (versie 2).
- *De Pangram-vergelijking is een principe, geen techniek.* Pangram leest een
  eigenschap van lange Engelse tekst, en zegt niets onder de 50 woorden. Wij
  krijgen korte berichten, en hun waarheid staat buiten de tekst.

## 3. De volledige opbouw

Van een screenshot tot een antwoord dat een redactie vertrouwt. **Vet** staat
wat in de tabel van de PO ontbrak.

| | laag | stand |
|---|---|---|
| **aanvoer** | **verse factchecks**: de bron publiceert sinds 19 oktober niet. Ze mist per definitie AFP, Snopes en Correctiv, en sinds Google in juni 2025 stopte met de factcheckvermelding in de zoekresultaten, hebben redacties minder reden om hun checks op te maken. **Geen afspraak met één redactie** | **riskant** |
| **invoer** | lezen en opknippen | bestaat; 54% op echte screenshots (§158) |
| | **het beeld zien zonder dat het de EU verlaat**: in 29 van de 100 echte screenshots zat de bewering in het beeld. Tesseract leest dat niet; een lokaal beeldmodel misschien wel | ontbreekt |
| | **beweringen eruit halen vóór het zoeken**, en een bericht met meer beweringen splitsen; datum en afzender uit het screenshot lezen. Dat alleen vond 18 van de 79 gemiste checks terug (§155) | ontbreekt |
| | **taal herkennen**, met de poort dat een taal zonder gehaalde eis geen oordeel krijgt | herkenning bestaat, de poort niet |
| **kennis** | de database met 110.000 factchecks | bestaat; de juiste check staat maar bij 71 van de 150 echte screenshots bij de beste vijf (§155), in het wild bij 22% (§116) |
| | de lijst met vastgestelde feiten (40) | bestaat |
| | de bronnenlijst | ontbreekt; vulling: Wikipedia, de Sheffield-set (7.671 artikelen van desinformatiedomeinen), het Pravda-netwerk |
| | de database met hoe nepnieuws werkt | deels: 240 verhaalgroepen over drie jaar of langer (§111), EUvsDisinfo |
| | het draaiboek | ontbreekt; nu ~20 regels in de vraag |
| | **wie beslist over de lijsten**: een gepubliceerde werkwijze, en bezwaar voor wie erop staat. NewsGuard laat zien wat het kost om dit over te slaan | ontbreekt |
| | zoeken op het web | bestaat; of de zoekdienst iets bewaart, is nog niet bekend |
| **oordeel** | het model, vast per versie | bestaat; Sonnet 5.5 heeft geen vaste versie met datum, en geeft soms bij dezelfde vraag een ander oordeel (§153) |
| | de regels (over een bewering, beeld nodig) | bestaat (§159) |
| | de controle op het antwoord: bronnen langs de lijst, citaten nalopen | ontbreekt |
| | **draagt de bron de bewering echt?** Niet alleen of het citaat bestaat, maar of het bewijst wat het moet bewijzen. In ronde 1 stond een bron die het niet bewees (V270), en 14 die het alleen indirect deden (§156) | ontbreekt |
| **antwoord** | **drie delen** (PO 2026-10-27): *inhoud* (klopt, klopt niet, misleidend, onzeker of wordt onderzocht, geen bewering, over een bewering, beeld nodig, satire); *herkomst* (echt van de genoemde bron, niet gevonden bij die bron, of vervalst: bestaat de kop op de site van de krant, schrijft die schrijver daar, heeft dat account dit gepost?); *vorm en afzender* (neutrale signalen zoals "gebruikt angst", en of de afzender bekendstaat als dubieus) | nu één oordeel; herkomst ontbreekt helemaal: een vals screenshot met een ware zin erin krijgt nu groen |
| | waarom het nep is, uit de nagelopen bronnen, in de taal van de gebruiker | ontbreekt |
| | de schaal, per model en taal geijkt | alleen Sonnet in het Engels |
| **meting** | **een waarheid die niet van Claude komt.** Elk getal tot nu toe rust op labels die Claude las. In de set van §150 bleek 1,7% zelf fout, meer dan de 1% die we beloven | **riskant** |
| | de vaste toets, met een vers en een geheim deel, het kale model ernaast | voorstel (RELEASES) |
| | **evenwicht**: hoe vaak onterecht rood, per politieke kant en per onderwerp | ontbreekt |
| | **een tegenspeler**: opdrachten verstopt in een screenshot, Factiz als oracle gebruiken (een leugen bijschaven tot ze niet meer rood is), een screenshot van een groene Factiz als bewijs voor een leugen, verse domeinen die elkaar bevestigen | ontbreekt |
| **bedrijf** | bewaren bij het model: voor nu de standaard van Anthropic, hoogstens 30 dagen en geen training (B54); zero data retention opnieuw wegen bij de EU-server of een EU-regio (Amazon Bedrock met `data_retention_mode: none`) | besloten voor nu, opnieuw bij de EU-variant |
| | **toegang tot factcheckers die ons weren**: per bron een mail met de vraag om de ClaimReview te mogen lezen, of een feed of API (concepten: `docs/voorstellen/partnermails.md`). Pas als factiz.org live staat, want de mail verwijst ernaar (PO 2026-11-03). Nu bekend: AFP (elke automatische toegang, in vier talen), PesaCheck (1.383 van 1.383 artikelen geweigerd in de beeldoogst), Tempo Cekfakta en Investigate Bel. Nog te verkennen: Reuters en AP. De lijst wordt bijgewerkt uit de beeldoogst en route A | na de livegang van de site |
| | **juridisch**: smaad bij "onwaar" over iemand met naam; een DPIA, want politieke opvattingen zijn bijzondere persoonsgegevens (AVG art. 9); een termijn voor correcties; uitleggen dat een oordeel niet na te spelen is als we niets bewaren | ontbreekt |
| | **mensen**: nalezers met de taal als moedertaal voor Spaans, Duits en de vierde taal; toezicht zonder labels als het draait | ontbreekt |
| | kosten | ~$0,04 per bericht live (§157); voor redacties haalbaar, voor platforms niet |

## 4. Kan het? Per belofte

| belofte | bewijs | oordeel |
|---|---|---|
| rood klopt bij Engelse tekst | 0 van 99 met de regels (§159), 97% in ronde 4 (§158); maar gelabeld door Claude | **waarschijnlijk**; eerst door een mens bevestigen |
| bekend nepnieuws herkend | 99 van de 99 op de tekst van de check zelf; met de juiste check bij de beste vijf 99%, anders 19% (§155); in het wild 22% (§116) | **onzeker**: hangt af van de zoekfunctie |
| echte screenshots ≥90% | 54% (§158); ~69% met twee stappen, achteraf gemeten (§155) | **onzeker zonder het beeld te zien** |
| nieuw nepnieuws | 21% zelf herkend | **geen belofte**: *onzeker* is het eerlijke antwoord |
| *sturend*, *onzin* als oordeel | bij een internationale wedstrijd voor zulke technieken (SemEval 2023) waren menselijke beoordelaars het weinig eens (α 0,34), en haalden de beste systemen een F1 van 0,38–0,51 | **niet haalbaar als oordeel**; wel als neutraal signaal |
| "hoogstens 1 op 100 per label, taal en vorm" | vraagt ~12.000 nagekeken berichten | **niet haalbaar**; wel uitspraken met een marge, uit herhaalde metingen op een geheime set |
| "nooit rood bij een gewone tekst" | "nooit" is niet te bewijzen | **een bovengrens publiceren** |
| Spaans, Duits | Spaans 5.575 checks; Duits 4.139, waarvan 3.910 met het oordeel als zin (dpa, BR24), om te zetten voor < $1 | **haalbaar** |
| Chinees | 12 ware checks; welke bronnen betrouwbaar zijn (Taiwan of China) is een politieke keuze | **niet voor V1**; Portugees heeft 7.859 checks |
| de database vers houden | de bron staat stil | **riskant**; zonder dit veroudert de belangrijkste laag |

## 5. Fase 0: elf proeven

| | proef | door als | anders | kosten |
|---|---|---|---|---|
| **P1** | **een mens labelt blind**: een externe factchecker leest ~150 berichten uit ronde 4 en 5 (elk rood bij een waar bericht, elk groen bij nepnieuws, en 50 willekeurige) zonder ons oordeel te zien | hoogstens 2% verschil met onze labels | onze cijfers zijn niet te gebruiken; eerst de waarheid opnieuw opbouwen | €0–500, een dag (PO zoekt de factchecker) |
| **P2** | **drie redacties**: twee factcheckredacties en een OSINT-groep krijgen elk 20 dossiers, met de hand gemaakt uit wat er al is, over beweringen waar ze nu mee bezig zijn. Hoeveel minuten scheelt het, en wat mist? (#23.13) | twee van de drie zouden het wekelijks gebruiken | het product herzien vóór we bouwen | $0, twee weken |
| **P3** | **de aanvoer**: nieuwe records per maand in de feed over 24 maanden; gesprekken met EDMO, AFP en Correctiv over hun checks | een bron die elke week levert | de database veroudert: eerst oplossen, anders geen V1 | $0 |
| **P4** | **de 79 gemiste screenshots van §155**: beweringen eruit halen, meerdere zoekvragen per bewering, een betere tekstherkenning (Apple Vision of PaddleOCR) | de juiste check bij de beste vijf in ≥80% | de zoekfunctie eerst verbeteren | ~$2 |
| **P5** | **het plafond van screenshots**: Sonnet krijgt het beeld wel, offline, op de openbare M4FC-beelden | ≥85% | het doel of het privacyontwerp herzien, bijvoorbeeld een lokaal beeldmodel | ~$2 |
| **P6** | **bekend nepnieuws in echte vorm**: herformuleringen, posts en screenshots in plaats van de tekst van de check | ≥70% bewezen | de eis bijstellen | ~$4 |
| **P7** | **twee mensen labelen 100 berichten** op sturing, onzin, misleidend en satire, los van elkaar | eensgezindheid (κ) ≥0,7 | geen belofte op die labels; alleen neutrale signalen | $0, een halve dag |
| **P8** | **een tegenspelerset van 50**: opdrachten in screenshots, een echte gebeurtenis met een vals detail, bronnen van verse domeinen | geen enkele onterecht groen | eerst de tegenspelerlaag | ~$1 |
| **P9** | **de modelpoort**: Opus 5.5, Sonnet 5.5, Haiku 5.5 en het kale model op de 100 moeilijkste | we weten welk model het meest waard is | Sonnet blijft | ~$5–10 |
| **P10** | **wat niet de techniek is**: ZDR met zoeken (een mail van de PO), een uur met een mediajurist, en per taal tellen wat er bruikbaar is | ja op ZDR, geen juridische blokkade, genoeg materiaal | per punt een besluit | $0 en een uur juridisch advies |

| **P11** | **de gebruikerstoets**, zoals de PO zelf zou testen (2026-10-27), ~250 berichten: echte krantenartikelen en boeken als screenshot; dezelfde, gefotoshopt (nep-logo, een schrijver die niet bestaat, tekst veranderd); verzonnen leugens; TikTok-screenshots over gezondheid en wetenschap; politieke beweringen in het midden ("de EU haalt expres bootvluchtelingen binnen"); en overduidelijke leugens en waarheden. Door Factiz, het kale model met zoeken en een model zonder zoeken. De vervalste screenshots maken we zelf, alleen voor de toets, nooit gepubliceerd | op overduidelijke berichten minstens zo goed als het kale model (≥95% goed, nooit *onzeker* waar het kale model het goed heeft); een vervalst screenshot nooit als echt; bij politieke beweringen context met bronnen | de regel voor algemeen bekende kennis bijstellen, en de herkomstcheck eerst bouwen | ~$5–8 |

**Samen:** ~$15–20 aan vragen aan een model, ~€0–500 voor de factchecker, en
werk van de PO. Wat het oplevert: een route waarvan we weten dat ze kan, met
eisen die we kunnen bewijzen.

## 6. De routekaart na fase 0

| fase | wat | poort | kosten |
|---|---|---|---|
| **0 Bewijzen** | de elf proeven van §5 | per proef door of anders; daarna de route en de eisen vastleggen | ~$20 + factchecker |
| **1 De keten in het Engels** | aanvoer, beweringen eruit halen, de bronnenlijst met een werkwijze, citaten nalopen en draagt de bron het, waarom het nep is, de screenshots, de tegenspeler, de vaste toets | de eisen in het Engels, met een marge; door een mens nagekeken; evenwicht per politieke kant | ~$20–30 + nalezen |
| **2 De talen** | Spaans, Duits, Portugees: materiaal, nalezers met de taal als moedertaal, toets, ijking | per taal de eisen; anders geen oordeel in die taal | ~$15 + nalezen per taal |
| **3 Zelf tevreden** | de hele toets opnieuw, op een geheime set, meerdere keren | V1 klaar | ~$10 |
| **4 Naar buiten** | de belofte (#23.16), klaarmaken (#31.16), de redacties van P2 als eerste gebruikers, juridisch rond | | |
| **5 Versie 2** | platforms en AI-labs (de controle in bulk), beelden en video, netwerken in kaart, Chinees en Russisch | | |

**Tussendoor: de tijdelijke site en de partnermails** *(PO 2026-11-09: "zet de mails op de roadmap in 1 doc voor
partner mails")*. Dit loopt naast de fasen, niet erna:
1. de tijdelijke site live op factiz.org (PLAN #23.17), met een inbox die werkt op info@factiz.org;
2. de partnermails (`docs/voorstellen/partnermails.md`), in deze volgorde:
   - CheckFirst en Alliance4Europe;
   - een redactie per taal;
   - toegang bij AFP en de anderen die ons weren;
   - de licentie bij Le Monde.

De redacties per taal worden de eerste gebruikers van fase 4. De mail aan Brave over de zoekvragen hoort bij de DPIA
en kan nu al.

**Later** *(PO 2026-11-10: "Zet op de roadmap, doen we later, nu eerst verder waar we waren")*:
- de test van Factiz tegen Fable 5.2, en Fable 5.2 als kern of als derde laag (PLAN #32.67, RESEARCH §12). De opzet
  ligt klaar: drie armen op de 50 berichten van het duel met Gemini, ~$20–30, grens $35;
- de sparringronde over Mythos en het hele internet afspeuren naar nepnieuws, in kaart brengen en melden bij netwerken
  en overheden (B23, B40).

**Het nalezen door mensen is de grootste post**, niet de vragen aan een model.
Reken per taal op enkele dagen van iemand met die taal als moedertaal.

**Idee van de PO (2026-10-27, na P3): een eigen checkmotor als bron.** De
aanvoer van factchecks is ingestort (~1.000 per maand in 2024, ~200 nu; Spaans
en Portugees bijna nul). Op mensen kunnen we niet rekenen. Dus maakt Factiz
later zelf checks: wat waar is weten we uit vier betrouwbare bronnen van twee
soorten (B34), en de controle per bericht doet al bijna dit werk. Zo blijven we
zelf ons eigen materiaal leveren. Nog geen besluit. Wat er dan voor moet
gelden:
- *Een eigen check is nooit een check van een redactie.* Hij staat apart in
  de database, met zijn bronnen, en wordt nooit in de vorm van een redactie
  getoond (DR5). Alleen in een taal en soort bewering waar de gemeten precisie
  de poort haalt (B25).
- *Geen kringloop.* Een eigen check telt nooit als bewijs voor zichzelf of
  voor een volgende eigen check. Het bewijs blijft bij de bronnen.
- *Een mens leest een vaste steekproef na*, per taal, zoals bij P1.
- *Waar de beweringen vandaan komen:* wat rondgaat (tiplines, Community
  Notes, trending). Dat is de controle in bulk (versie 2), of eerder een
  kleine vaste stroom per taal.
- *Eerst als meetmateriaal.* Verse onware berichten per taal zijn precies wat
  P10 mist (0 tot 1 per taal in drie maanden). Pas daarna in het antwoord.

**Idee van de PO (2026-11-10): een vaste stroom pagina's over wat er rondgaat** (`docs/voorstellen/2026-11-10-wat-er-rondgaat.md`,
PLAN #32.68; nog geen besluit). Factiz publiceert zelf, op factiz.org, per bericht dat rondgaat een pagina met de
check van de redactie bovenaan, in het Nederlands en Engels, zodat Factiz zelf een bron wordt bij Google en in
antwoorden van AI. In drie stappen: eerst alleen wat een redactie al checkte; per taal na de eisen ook wat Factiz met
bronnen weerlegt; later zelf afspeuren (de sparringronde hierboven). Elke pagina eerst langs een mens, en factiz.org
nooit als bron in de eigen controle. Eerste proef: de valse Vogue-cover, lokaal.

## 7. Wat de PO besliste (2026-10-27, B47)

*Fase 0 eerst; het antwoord in twee delen; Portugees in plaats van Chinees. De proeven met mensen (P1, P2, P7, het juridische deel van P10) wachten: "Nog niet".*

1. **Fase 0 eerst**, met de elf proeven en hun uitkomsten van §5, en de route
   pas vastleggen daarna?
2. **Het antwoord in twee delen**: waarheid (de acht uitkomsten van B46, met
   *satire*) en vorm (neutrale signalen, geen oordeel). *Sturend* en *onzin*
   komen in V1 niet als oordeel.
3. **De vierde taal:** Portugees in plaats van Chinees; Chinees en Russisch in
   versie 2.
4. **Mensen en geld buiten de modellen:** een externe factchecker voor P1
   (€0–500), drie redacties voor P2, gesprekken over de aanvoer (P3), een uur
   met een mediajurist.

**Daarna, na de gebruikerstoets (B48):** een echt verhaal met één vals detail
wordt *klopt grotendeels, maar 2003 moet 2006 zijn*, met de bron, en de foute
woorden worden in het bericht gemarkeerd. Dat is de negende uitkomst, en nooit
groen. Te bouwen in fase 1 (PLAN #32.3a).

## Bronnen

- SemEval-2023 Task 3 (overtuigingstechnieken, meertalig): https://aclanthology.org/2023.semeval-1.317.pdf
- Google stopt de factcheckvermelding: https://www.niemanlab.org/2025/06/google-kills-the-fact-checking-snippet/ en https://www.poynter.org/ifcn/2025/google-claimreview-fact-checks-snippets-removed/
- Eigen metingen: BENCHMARK §111, §116, §144, §149–§159; de feed: PLAN, de onderzoeken naar het AFP-gat
