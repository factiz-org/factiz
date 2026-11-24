# Onderzoek — wat de wereld al weet over factcheckmachines

> Eigenaar: PO · bijgehouden door de Lead Dev · stand 2026-11-01
>
> Wat er buiten Factiz bekend is: benchmarks, beste werkwijzen, bestaande
> systemen, diensten en audits van chatbots. Elke bevinding met haar bron. Onze
> eigen metingen staan in `BENCHMARK.md`, besluiten in `REQUIREMENTS.md`. Dit
> document groeit; wat verouderd raakt, krijgt een datum erbij in plaats van te
> verdwijnen.
>
> **[secundair]** = alleen in berichtgeving gevonden, niet in de bron zelf.

---

## 0. Kort: de acht dingen die ertoe doen

1. **Eerst bestaande checks, dan het web.** Dat is de grootste hefboom.
   GPT-4o haalt op 6.000 PolitiFact-claims 0,26 zonder zoeken, 0,76 met
   webzoeken en 0,90 met de checks van PolitiFact erbij (§2.3). Ons geheugen
   van 110.000 checks is dus het belangrijkste wat we hebben.
2. **Oordelen zonder bron noemt ware dingen fout.** In AVeriTeC 2025 noemden
   systemen 11,8% van de ware claims onwaar (§2.1). Opus zonder bronnen deed
   dat bij ons 1 op 37 keer. Met bronnen en de regel "*klopt niet* alleen met
   een check of een geciteerde bron" kwamen we op 0 van 50 (§145, §146).
3. **Meer antwoorden is niet beter antwoorden.**
   - Met webzoeken weigerden chatbots niets meer: van 31% naar 0% (NewsGuard).
   - Tegelijk herhaalden ze vaker valse claims: van 18% naar 35% (§6.1).
   - *Onzeker* is dus een functie, geen gebrek.
4. **Buiten het Engels gaat het slechter, en vooral door weglaten.**
   - ISD 2026: 71% volledig juist in het Engels, 55% in het Spaans. Eén op de
     zes Spaanse antwoorden had geen enkele bron.
   - NewsGuard 2025: fout in het Russisch 55%, in het Frans 34%.
   - Meten per taal is dus nodig (§6).
5. **Bronnen zijn de zwakste schakel.**
   - Bronproblemen in 31% van de antwoorden (EBU) en 34,7% (Brennan).
   - Meer dan 60% verkeerde bronvermeldingen bij AI-zoekmachines (Tow Center).
   - Elk citaat moet nagelopen worden (§3.2).
6. **Beelden vragen omgekeerd zoeken.** Zonder dat zakte DEFAME van 83,9% naar
   73,7% (§5). Chatbots herkennen AI-beelden slecht: ChatGPT ving er 1 van de
   14 (§6.2).
7. **Datalacunes en "LLM-grooming".** Waar weinig betrouwbare bronnen zijn,
   vullen staatsmedia en netwerken als Pravda het gat (§6.1). Dus nodig:
   - een oordeel over de betrouwbaarheid van domeinen;
   - een signaal als een onderwerp weinig dekking heeft.
8. **Voorwaarden tellen mee.** De zoekresultaten van Gemini mogen niet bewaard,
   geanalyseerd of automatisch verzameld worden. Claude's zoekfunctie, Brave en
   Google Cloud Vision kennen zo'n verbod niet (§4).

---

## 1. Van waar we komen

**Verifyr (april 2026)** — `~/dev/CLAUDE CODE MAP/Verifyr`.
- **De motor:** Gemini 2.5 Flash met Google Search, in drie stappen:
  1. eerst de tekst uit een beeld lezen;
  2. een snelle voorkeuring zonder zoeken;
  3. dan een oordeel op live zoekresultaten, met een lijst betrouwbare bronnen
     (IFCN-redacties, persbureaus, kwaliteitskranten, onderzoeksplatforms,
     officiële bronnen), satireherkenning, een bewijsketen en een herkomstspoor.
- **De kracht:** live controle van elke bewering. "Werkte verbluffend goed"
  (PO), maar nooit gemeten.
- **De zwakte** (eigen ROADMAP, juli 2026):
  - de bronnenlijst schreef het model zelf, het waren geen citaten;
  - delen en de cache waren kapot;
  - er zaten namaaklogo's in;
  - het leunde op Google, met de voorwaarden van §4.

**Doublecheck / Factiz (27 augustus tot nu).**
- **Gekozen als resolverlaag:** is dit al gecheckt, door wie (B1, B3).
- **Wat het opleverde:**
  - het geheugen van ~110.000 checks;
  - een precisie die vaststaat;
  - een basisset van 27.478 stukken om te meten.
- **Wat het niet deed:** controleren waar nog geen check van bestaat.

**Sinds 2026-10-25 (B43, besloten 2026-10-26):** de machine controleert met bronnen. Een
model leest, raadpleegt het geheugen en zoekt op het web; Factiz eromheen
(PLAN #31.8, §145–§146).

---

## 2. Benchmarks en het plafond

### 2.1 AVeriTeC (echte claims met webbewijs)
- **De set:** 4.568 claims van 50 factcheckorganisaties, met de labels
  Supported, Refuted, Not Enough Evidence en Conflicting. Mensen zijn het eens
  met κ 0,62.
- **2024:** de winnaar haalde 0,63, met GPT-4o in zes stappen.
- **2025:**
  - alleen open modellen op één GPU van 23 GB, binnen één minuut per claim;
  - de winnaar haalde 0,33, met Qwen3-14B;
  - op 1.000 claims uit 2024 noemden systemen 11,8% van de ware claims
    onwaar;
  - "niet genoeg bewijs" scoorde overal bijna 0.
- **Voor beelden (AVerImaTeC, 2026):** de winnaar haalde 0,55, met Gemini 2.5
  Pro en omgekeerd zoeken via Google Cloud Vision. Een enkele zoekmachine vindt
  vaak niets; meerdere helpen.
- Bronnen: https://arxiv.org/html/2410.23850v1 ·
  https://aclanthology.org/2025.fever-1.15/ · https://arxiv.org/abs/2602.11221

### 2.2 Andere benchmarks
- **FEVER:** verzadigd, ~80%.
- **X-Fact (25 talen):** een fijngestemd XLM-R van 270M haalt 57,7%; de beste
  taalmodellen van 7 à 12B 16,9%.
- **CheckThat! 2024:** check-waardigheid, F1 0,80 (Engels) en 0,73 (Nederlands).
- **CheckThat! 2025:** normalisatie van claims in 20 talen, en getallen.

### 2.3 Zoeken tegen bestaande checks (DeVerna e.a., november 2025)
- **De opzet:** 15 modellen op meer dan 6.000 PolitiFact-claims.

| | macro-F1 |
|---|---|
| GPT-4o zonder zoeken | 0,26 |
| GPT-4o met webzoeken | 0,76 |
| GPT-4o met de checks van PolitiFact erbij | 0,90 |
| Gemini 2.0 Flash met Google-grounding | 0,27 (geen winst) |

- **Waarschuwing:** de modellen met zoeken vonden de PolitiFact-check zelf in
  44 à 59% van de antwoorden. Wie meet, moet factchecksites blokkeren of op
  verse claims toetsen.
- Bron: https://arxiv.org/abs/2511.18749

### 2.4 Zoeken en nieuwe claims
- **DEFAME:** GPT-4o haalt 35,2% op claims van na de trainingsgrens zonder
  zoeken en 69,7% met zoeken.
- **SAFE (Google DeepMind):** gpt-3.5 met zoeken was het in 72% van de gevallen
  eens met crowdwerkers, en kostte $0,19 per antwoord tegen $4 voor mensen.
- **FIRE:** zoekt alleen als het model onzeker is; 7,6 keer goedkoper.
- Bronnen: https://arxiv.org/abs/2412.10510 · https://arxiv.org/abs/2403.18802 ·
  https://arxiv.org/abs/2411.00784

---

## 3. Beste werkwijzen en bestaande systemen

### 3.1 De vaste volgorde
De standaard bij CheckThat!, Full Fact, Meedan, Loki en DEFAME:
1. de bewering eruit halen en normaliseren;
2. vergelijken met bestaande checks;
3. zoeken, 1 à 3 rondes met de beste resultaten (SAFE, SAGE, FIRE);
4. een oordeel met citaten;
5. afzien als het bewijs ontbreekt.

### 3.2 Citaten nalopen
- Tow Center (maart 2025): AI-zoekmachines gaven in meer dan 60% van 1.600
  tests verkeerde bronnen (Perplexity 37%, Grok-3 94%).
- Claude's zoekfunctie geeft een letterlijk citaat (`cited_text`, tot 150
  tekens) dat je kunt controleren; Gemini en OpenAI geven koppelingen naar de
  eigen tekst.
- Bron:
  https://www.niemanlab.org/2025/03/ai-search-engines-fail-to-produce-accurate-citations-in-over-60-of-tests-according-to-new-tow-center-study/

### 3.3 Bestaande systemen

| systeem | wat | open? |
|---|---|---|
| Full Fact AI | claimtypes en claimmatching; 40+ organisaties, ~⅓ miljoen zinnen per dag; mensen keuren alles | nee |
| Factiverse | compacte fijngestemde modellen, 114 talen | nee (code bij het artikel wel) |
| Meedan Check | tiplijnen op WhatsApp die tips aan bestaande checks koppelen | ja (MIT) |
| Google Fact Check Tools | API over gepubliceerde checks; de snippets zijn sinds juni 2025 uit de zoekresultaten. De open feed van Data Commons bevat alleen checks die met Google's eigen invoerhulp zijn gemaakt (§8.4) | gratis |
| Loki / OpenFactVerification | ontleden, zoeken (Serper), oordelen | ja (MIT) |
| DEFAME | factchecksysteem in zes stappen, met omgekeerd zoeken; met een open model veel zwakker (§8.7.3) | ja (Apache-2.0) |
| InVID-WeVerify | omgekeerd zoeken op beelden, video, detectie van AI-beelden; het project vera.ai erachter stopte op 31 oktober 2025 [secundair] | gratis plug-in |
| Fact-Check Insights / MediaVault | ClaimReview en MediaReview van 188 organisaties; sinds 2025 bij Maldita.es en Full Fact, niet meer bij Duke; alleen voor factcheckers (§8.5) | op aanvraag |
| TrueMedia.org | detectie van deepfakes; sloot op 14 januari 2025 | code MIT, gewichten niet gedeeld |
| SynthID Detector (Google) | herkent het watermerk van Google en partners; sinds 7 oktober 2026 voor iedereen, alleen als website (§8.7.4) | nee |
| Logically Facts | ging in juli 2025 failliet | — |

---

## 4. Live zoeken: diensten, kosten, voorwaarden

| dienst | prijs | citaten | voorwaarden |
|---|---|---|---|
| Claude web search | $10 per 1.000 + tokens, ook in de Batch API | letterlijk (`cited_text`) | bij tonen aan gebruikers de bron vermelden; geen verbod op opslag gevonden |
| Gemini grounding | $35 per 1.000 prompts (2.5); $14 per 1.000 zoekopdrachten (3) | koppelingen, geen citaten | **niet cachen, analyseren of automatisch verzamelen**; alleen aan de vragende gebruiker tonen |
| OpenAI web search | $10 à $25 per 1.000 | koppelingen | — |
| Brave Search API | $5 per 1.000 | ruwe resultaten | opslag alleen met een plan dat dat toestaat |
| Perplexity Search | $1 à $5 per 1.000 | ruwe resultaten | — |
| Bing Search API | — | — | opgeheven in augustus 2025 |

Bronnen: https://ai.google.dev/gemini-api/terms ·
https://platform.claude.com/docs/en/agents-and-tools/tool-use/web-search-tool

---

## 5. Omgekeerd zoeken op beelden

| dienst | prijs per 1.000 | wat | kanttekening |
|---|---|---|---|
| **Google Cloud Vision, Web Detection** | $3,50; eerste 1.000 per maand gratis | pagina's met hetzelfde beeld (adres, titel), trefwoorden; geen datum | officieel; Google bewaart het beeld niet |
| Google Lens via SerpApi, Bright Data, Serper | $1 à $25 | idem, soms een datum | scraping; er loopt een rechtszaak van Google tegen SerpApi |
| TinEye | $10 à $40 | `crawl_date` (de vroegst geziene) | zwak op sociale media |

- **DEFAME:** zonder omgekeerd zoeken van 83,9% naar 73,7% op VERITE.
- **5Pils:** één zoekmachine vond bruikbare pagina's voor 66% van de beelden.
- **XFacta (2025):** GPT-4o haalt 70,5% zonder bewijs en 89,5% met bewijs.
  Zonder bewijs neigt het naar "nep".
- **Wat we zelf zagen:** de beelden van M4FC zijn bijna allemaal schermafdrukken
  van de virale post (192 van 196). Ware beelden in hun juiste context moeten we
  apart verzamelen (PLAN #31.8).
- Bronnen: https://cloud.google.com/vision/pricing ·
  https://arxiv.org/abs/2508.09999
- **Bijgewerkt 2026-11-01** (§8.7.2, §8.7.4):
  - een kopie terugvinden kan nu met een open model dat per paar zegt of het
    een kopie is (CopyNCE, Apache-2.0);
  - de SynthID Detector is een website zonder API;
  - C2PA gaat verloren in een screenshot;
  - open detectors van AI-beelden halen op beelden uit het wild AUC
    0,52–0,56.

---

## 6. Chatbots, verkiezingen en talen (audits 2024–2026)

### 6.1 ISD, "Chatbots and the Ballot Box" (september 2026)

*Het onderzoek achter het BNR-bericht van 26 oktober 2026 ("AI-chatbots
verspreiden vaker desinformatie over midterms in andere talen dan Engels", via
Politico). Zelf gelezen in het rapport.*

**De opzet:**
- zes chatbots in hun standaardversie, met webzoeken aan: GPT-5.5, Gemini 3.5
  Flash, Sonnet 4.6, Grok 4.3, DeepSeek V4 Pro en Meta's Muse Spark;
- tien staten; per staat 15 gewone kiezersvragen en 5 sturende vragen;
- Engels en Spaans; 2.400 antwoorden;
- gemeten in juni 2026.

**Resultaten bij gewone vragen:**
- 29% van de Engelse antwoorden was onvolledig, verouderd of fout (16%
  onvolledig, 6% verouderd, 6% fout). 12% kon kiezers echt misleiden.
- **Volledig juist: 71% in het Engels, 55% in het Spaans.**
  - Elk model werd slechter in het Spaans.
  - GPT-5.5 hield het best stand: 89% in het Engels, 82% in het Spaans.
  - Vier modellen, waaronder Sonnet 4.6, hadden in het Spaans meer dan 40%
    niet volledig juist.
  - Bij "Kan ik per post stemmen in <staat>?" zakte het met 20 à 40 punten.
- **Waarom het Spaans slechter is:** vooral door *weglaten*. Ongeveer 64% van
  het verschil komt van onvolledige antwoorden: termijnen, uitzonderingen en
  stappen ontbraken. Letterlijke vertaling maakte het erger (stembureau
  tegenover verkiezingskantoor). De lengte van het antwoord verklaarde het
  niet.
- **Bronnen:**
  - zonder één bron is maar een derde van de antwoorden volledig juist;
  - van de Spaanse antwoorden zonder bron minder dan 1 op 10;
  - in het Spaans had 1 op de 6 antwoorden geen enkele bron, in het Engels 3%.
- **Sturende vragen:** 91% (Engels) en 89% (Spaans) weerlegd; hooguit 4% gaf de
  vrager gelijk.
  - Hoe minder concreet de claim, hoe slechter: bij "ballot harvesting" in
    North Carolina weerlegde maar één van de zes modellen de claim.
  - De bevindingen gelden niet voor nieuwe, lokale of weinig gecheckte claims.
- **Aanbeveling aan ontwikkelaars:** "close the language gap as a distinct
  priority". Het gat sluit niet vanzelf, want het komt door weglaten en niet
  door gebrek aan kennis.

Bron:
https://www.isdglobal.org/wp-content/uploads/2026/09/Chatbots-and-the-Ballot-Box-US-elections.pdf

### 6.2 Andere audits

- **NewsGuard, AI False Claims Monitor:** per chatbot 10 valse claims × 3
  soorten vraag.
  - In augustus 2024 herhaalden chatbots 18% en weigerden ze 31%. In augustus
    2025 was dat 35% en 0%: met webzoeken antwoorden ze alles, ook uit vervuilde
    bronnen.
  - Januari 2026: elf chatbots herhaalden in "meer dan 28%" van de gevallen een
    valse claim.
  - **In zeven talen (februari 2025):** fout in het Russisch 55%, Chinees 51%,
    Spaans 48%, Duits 43%, Engels 43%, Italiaans 39%, Frans 34%.
  - **Engels tegen Mandarijn (juli 2026):** 24% tegen 33% herhaald; in het
    Mandarijn citeerden de chatbots Chinese Sputnik-sites.
  - https://www.newsguardtech.com/press/ai-multilingual-failure-russian-chinese
- **NewsGuard over het Pravda-netwerk (maart 2025):**
  - in 33% herhaalden chatbots een verhaal van het netwerk;
  - het netwerk publiceerde 3,6 miljoen artikelen in 2024;
  - details [secundair];
  - in mei 2026 herhaalde Claude pro-Kremlinclaims in 15% van de gewone vragen
    (3 van 20).
  - **Tegenbewijs:**
    - Harvard Misinformation Review (oktober 2025): 5% herhaling. De auteurs
      zien eerder datalacunes dan grooming.
    - ISD (oktober 2025): 18% van de antwoorden citeerde Russische staatsbronnen,
      oplopend van 11% bij neutrale tot 24% bij kwaadwillige vragen.
  - https://misinforeview.hks.harvard.edu/wp-content/uploads/2025/10/alyukov_chatbots_kremlin_disinformation_20251015.pdf
- **Brennan Center, "Does AI Fight or Fuel Election Disinformation?" (augustus
  2026):**
  - 220 antwoorden op echte complotposts; geen enkel antwoord steunde de claim;
  - 32,5% had een feitelijke fout en 34,7% een bronfout;
  - meer fouten in lange gesprekken;
  - AI-beelden herkennen: Meta AI 10 van 14, ChatGPT 1 van 14 (ook niet de
    eigen beelden).
  - https://www.brennancenter.org/our-work/research-reports/does-ai-fight-or-fuel-election-disinformation
- **EBU/BBC, "News Integrity in AI Assistants" (oktober 2025):**
  - 22 omroepen (ook NOS/NPO en VRT), 14 talen, 2.709 antwoorden;
  - 45% had een ernstig probleem, 31% een bronprobleem;
  - Gemini 76%, Copilot 37%, ChatGPT 36%, Perplexity 30%;
  - Engelse antwoorden linkten vaker rechtstreeks naar de bron;
  - Copilot en Gemini noemden voor de NOS paus Franciscus nog paus.
  - https://www.ebu.ch/research/open/report/news-integrity-in-ai-assistants
- **Proof News en Factchequeado (oktober 2024):** 52% van de Spaanse en 43% van
  de Engelse antwoorden fout. Spaanse antwoorden dwaalden af naar
  Latijns-Amerika of Spanje en linkten naar Engelse sites.
  https://www.proofnews.org/ai-models-falter-answering-election-questions-in-spanish/
- **Nieuwsuur en AI Forensics (2024):**
  - Nieuwsuur, mei 2024: ChatGPT, Copilot en Gemini schreven
    campagnestrategieën met desinformatie voor de EU-verkiezingen.
    https://nos.nl/nieuwsuur/artikel/2519038
  - AI Forensics, juli 2024: Copilot blokkeerde verkiezingsvragen in het
    Engels in 90% van de gevallen, in het Nederlands in 28%.
    https://aiforensics.org/work/chatbots-moderation
- **Oversight Board (juli 2026):** gaat over weigeren, niet over juistheid.
  Modellen weigerden kritiek op restrictieve landen vaker (34%) dan op
  vrijere landen (14%); bij Claude Sonnet 4 was het verschil het grootst (16%
  tegen 59%).

---

## 6b. Bronnen, datasets en zoekdiensten (bureauonderzoek, 29 oktober 2026)

*Alleen openbare pagina's, gelezen door een subagent. Niets aangemeld,
gedownload of gekocht. Wat met [secundair] gemarkeerd is of "onbekend" heet,
is niet nagegaan.*

**FACTS van Google (Kaggle; [artikel](https://arxiv.org/abs/2512.10791))**
- *Wat het is:* vier delen:
  - grounding: blijft een antwoord bij een meegegeven document?
  - eigen kennis zonder zoeken;
  - kennis met zoeken;
  - beelden.
- *Openbare data:* eigen kennis 1.052, zoeken 890, beelden 711. Grounding v2
  heeft 860 vragen, onder CC BY 4.0
  ([HF](https://huggingface.co/datasets/google/FACTS-grounding-public)).
- *De stand van 24 tot 27 oktober 2026,* gelezen via de openbare API van
  Kaggle. Tussen haakjes: hoe vaak juist als het model antwoordt, en hoe vaak
  het weigert:

| model | grounding | eigen kennis | met zoeken |
|---|---|---|---|
| de beste (GPT-6 Astra) | 80,1 | 83,8 (86,7 / 3) | 89,9 |
| Claude Opus 5.5 | 62,4 | 58,7 (73,8 / 20) | 86,5 |
| Claude Sonnet 5.5 | — | 35,1 (52,6 / 33) | — |
| Claude Haiku 5.5 | 57,0 | 13,1 (33,9 / 61) | 77,5 |

- *Wat het zegt:*
  - Met zoeken zit Claude dicht bij de top; zonder zoeken ver eronder. Dat
    steunt "alleen met bron".
  - Haiku zonder zoeken is bij moeilijke feitvragen maar in een derde van de
    gevallen juist. De vloer (B50) vraagt Haiku zonder zoeken. Daar gaat het
    wel om duidelijke onzin, en dat is apart gemeten (§169–§171).
- *Bruikbaar:* de 1.052 vragen van eigen kennis als ware beweringen. De vloer
  mag er geen enkele "duidelijk onwaar" noemen. Dat is een toets op valse
  alarmen bij moeilijke feiten (<$2).

**Bronnen van feiten (kring 2):**
- Wikidata (CC0, met een officiële MCP-server van WMDE).
- Data Commons (CC BY; MCP-server met Apache 2.0).
- Eurostat, CBS StatLine en OESO (open, licentie niet overal nagelezen).
- De open data van de Tweede Kamer (CC0), om citaten van politici na te gaan.
- *Zwak:* de Knowledge Graph Search API van Google ("not suitable for
  production").

**Bronnen van mis- en desinformatie (kring 1 en 4):**
- *Bruikbaar:*
  - X-Fact: 31.000 checks in 25 talen, MIT; om per taal te meten.
  - MultiClaimNet: beweringen per verhaal in 86 talen, licentie onbekend.
  - `imageSearch` van de Fact Check Tools API: checks zoeken met een beeld op
    een openbare URL; alleen offline.
  - DISARM: technieken van desinformatie, CC BY 4.0.
  - De EU-lijst van verboden Russische media (Verordening 833/2014): een
    neutrale lijst voor "telt nooit als bron".
  - *Bijgewerkt 2026-11-01 (§8.5, §8.7.1):*
    - SemEval-2025 taak 7 als ijkpunt voor het vinden van bestaande checks
      over talen heen: de winnaar haalde 0,859 in de top 10;
    - FACTors: 118.112 Engelse claims van 39 organisaties tot 2025, MIT;
    - Cofacts: CC BY-SA 4.0, alleen met een account.
- *Niet bruikbaar of duur:*
  - FEVER en LIAR: verzadigd.
  - ClaimsKG: laatste uitgave januari 2023 [secundair].
  - MuMiN: vraagt de API van X.
  - Full Fact AI en Factiverse: alleen als betaalde dienst.
  - NewsGuard: betaald.
  - Iffy: gebouwd op MBFC.
  - DBKF en het EDMO-archief: geen openbare API.

**Zoekdiensten die de dichte sites van §175 misschien wél zien:**
- *Brave* volgt de crawlregels voor Googlebot
  ([Brave](https://search.brave.com/help/brave-search-crawler)). Reuters, de
  BBC en nu.nl staan dus waarschijnlijk in zijn index (niet gezien).
  - Kosten: $5 per 1.000, met $5 tegoed per maand.
  - Brave bewaart zoekvragen standaard tot 90 dagen; ZDR alleen met een
    enterprisecontract.
- *Exa en You.com:* ZDR in enterprise; of ze de dichte sites zien, is
  onbekend.
- *Tavily:* geen ZDR gevonden.
- *SerpApi:* leest Google uit; geen bewaren pas vanaf $3.750 per maand.
- *Google Programmable Search:* stopt op 1 januari 2027.
- *De MCP-koppeling van Anthropic* valt buiten ZDR
  ([docs](https://platform.claude.com/docs/en/agents-and-tools/mcp-connector)),
  dus nooit in het aanvraagpad.

**GDELT** is gratis, ook commercieel, met bronvermelding. De zoekdienst (DOC
2.0) kijkt drie maanden terug: in de referentie moet STARTDATETIME "within
the last 3 months" liggen. Alleen de aankondiging uit 2017 noemde "back to
January 1, 2017"
([GDELT](https://blog.gdeltproject.org/gdelt-doc-2-0-api-debuts/)). Eigen
waarneming (#32.3f): GDELT toont apnews.com niet, en weigert de meeste vragen,
ook bij één vraag per zes seconden.

---

## 7. Wat het betekent voor Factiz

| bevinding | gevolg voor Factiz | stand |
|---|---|---|
| Bestaande checks zijn de sterkste hefboom (§2.3) | het geheugen gaat altijd eerst | zo gebouwd (PLAN #31.8) |
| Zonder bron worden ware dingen fout genoemd (§2.1, §6.2) | *klopt niet* alleen met een check of geciteerde bron, *klopt* alleen met een bron, anders *onzeker* | zo gebouwd; 0 van 50 fout (§146) |
| Meer antwoorden ≠ beter (NewsGuard) | *onzeker* is een eerlijke uitkomst; we tellen hoe vaak, per soort | zo gemeten |
| Buiten het Engels slechter, door weglaten en minder bronnen (§6.1) | **per taal meten**; per taal tellen hoe vaak er geen bron is; zoeken in de taal van de claim én in het Engels | zoeken in beide talen staat in de vraag; per taal meten nog niet: de volgende meting van 400 stukken telt per taal |
| Bronnen falen in 30–60% (§3.2, §6.2) | alleen letterlijke citaten van de API; zelf nalopen of het citaat in de pagina staat | citaten van de API; zelf nalopen nog niet gebouwd |
| Verouderde antwoorden (paus, verkiezingsdatum; §6.2) | de datum van het bericht meegeven; oordelen naar toen | zo gebouwd (vraag v2, §146) |
| Datalacunes en grooming (§6.2) | een lijst onbetrouwbare domeinen (staatsmedia, het Pravda-netwerk) niet als bron laten tellen; signaleren als er weinig dekking is | nog niet gebouwd |
| Sturende vragen geven meer fouten (ISD 2025) | eerst een neutrale bewering eruit halen, dan zoeken | zo gebouwd (stap 1 van de vraag) |
| Chatbots herkennen AI-beelden slecht (Brennan) | niet het model laten oordelen over echtheid; omgekeerd zoeken en herkomst (C2PA, SynthID) | omgekeerd zoeken gebouwd, wacht op een sleutel (PLAN #31.8) |
| Modellen verschuiven per versie | elke modelwissel is een release met een meting (B22) | staat |
| Voorwaarden van Gemini (§4) | geen Gemini-grounding in een pijplijn die bewaart | Claude's zoekfunctie gekozen |
| De aanvoer van checks droogt op; de grote factcheckers staan niet in de open feed (§8) | zelf ClaimReview ophalen bij de sites die het nog zetten; een lezer voor de grote zonder ClaimReview | voorstel, PLAN #32.19 |

---

## 8. Dekking en modellen (bureauonderzoek, 1 november 2026)

*Op de vraag van de PO (1 november 2026): "Hebben we alle wereldwijde
factchecktools die nog actief zijn al in ons systeem en ook al eens flink
gezocht op AI modellen die op dit moment in ontwikkeling zijn?"*

*Deel A telt wat er in de database met factchecks staat en legt dat naast de
lijsten van actieve factcheckers. Deel B zoekt modellen uit 2025–2026 voor
drie problemen van Factiz. Alles alleen gelezen: niets gedownload, aangemeld
of gekocht, de database geopend met `mode=ro`. Webpagina's in Claude in
Chrome; per factchecksite één lijstpagina, twee tot vier artikelen en
robots.txt, niets meer. Deel B door een subagent; drie dragende punten
(harrier, CopyNCE, de SynthID Detector) zelf nagelezen. Het voorstel staat in
PLAN #32.19.*

*De talen: de opdracht noemde Engels, Spaans, Duits en Chinees
(`V1-ROUTE.md`, B46). Sinds B47 (27 oktober 2026) zijn de talen van V1
Engels, Spaans, Duits en **Portugees**; Chinees gaat naar versie 2. Beide
staan hieronder.*

### 8.1 Kort

1. **De aanvoer droogt op bij de bron.** In 2024 kwamen er per maand
   gemiddeld 433 Engelse checks bij, in 2026 110. Spaans van 68 naar 1,
   Duits van 43 naar 5, Portugees van 154 naar 0. Chinees had er nooit veel
   en sinds augustus 2025 geen (§8.2).
2. **De oorzaak zit in wat de open feed bevat.** De feed van Data Commons
   heeft alleen checks die een factchecker invoert met Google's eigen
   invoerhulp (de Fact Check Markup Tool of de ClaimReview-API). In juni 2025
   besloot Google ClaimReview uit de zoekresultaten te halen. Sindsdien gebruiken steeds
   minder factcheckers die invoerhulp: 36 sites per maand in juli 2025, 13 in
   oktober 2026 (§8.4).
3. **De grote factcheckers zijn er nog, maar niet in de feed.** Deze zetten
   ClaimReview nog in hun eigen artikelen:
   - AFP in het Engels, Spaans, Duits en Portugees;
   - Snopes, Full Fact, Lead Stories, AAP, EFE Verifica en Annie Lab;
   - een deel van de checks van Maldita, Newtral, Factchequeado, Aos Fatos
     en Estadão Verifica.

   PolitiFact (sinds zijn nieuwe site), dpa, Correctiv, Taiwan FactCheck
   Center, MyGoPen, Chequeado, Lupa, Polígrafo en AP doen dat niet (meer)
   (§8.4).
4. **Van de 382 actieve factchecksites bij Duke hebben er 14 een check sinds
   mei in de database; 240 (63%) staan er helemaal niet in.** Van de 137
   IFCN-sites hebben er 8 een check sinds mei (§8.3).
5. **De meeste verse checks levert zelf, beleefd, de ClaimReview ophalen bij
   de sites die het nog zetten.** In het Engels, Spaans en Portugees samen
   naar schatting meer dan 500 per maand, tegen ~110 nu. Voor Duits en
   Chinees is daarnaast een lezer nodig voor de grote sites zonder
   ClaimReview: dpa en Correctiv, Taiwan FactCheck Center en MyGoPen.
   FACTors vult het Engelse verleden tot 2025 aan (§8.5, §8.6).
6. **Modellen** (§8.7):
   - *Tekst:* er zijn open modellen van dezelfde grootte als bge-m3 die op
     de meertalige ranglijst duidelijk hoger scoren (harrier-oss-v1-0.6b,
     Qwen3).
   - *Beeld:* er is een open model dat per paar zegt of een beeld een kopie
     is (CopyNCE).
   - *AI-beelden:* open detectors zakken op beelden uit het wild naar gokken.
   - *Watermerk en herkomst:* de SynthID Detector is sinds 7 oktober 2026
     voor iedereen, maar alleen als website. C2PA gaat verloren in een
     screenshot.

### 8.2 Wat er in de database staat

*Telling uit `doublecheck.db` (tabel `factcheck`, 110.231 checks), 1 november
2026. Spellingsvarianten van uitgevers samengevoegd via de host van de URL
(zonder `www.` en `m.`); subdomeinen tellen bij de organisatie, dus
`srilanka.factcrescendo.com` bij Fact Crescendo. De taal komt uit het veld
`language`.*

| periode | checks per maand | sites per maand | Engels | Spaans | Duits | Portugees | Chinees |
|---|---|---|---|---|---|---|---|
| 2024 (gemiddeld) | 1.309 | 53–70 | 433 | 68 | 43 | 154 | 1 |
| 2025, januari–juni | 974 | 46–54 | 399 | 38 | 15 | 2 | 0 |
| 2025, juli–december | 457 | 17–36 | 201 | 6 | 5 | 0 | 0 |
| 2026, januari–oktober | 260 | 11–20 | 110 | 1 | 5 | 0 | 0 |

- **Portugees en Nederlands vielen het eerst weg**, vanaf november 2024. De
  laatste checks van Lupa, Boatos.org en Comprova (Brazilië) en van VRT en
  Knack (Vlaanderen) zijn van 2024. De laatste Portugese check is van 27
  november 2025.
- **Sinds 1 mei 2026:** 1.307 checks van 24 sites (32 uitgeversnamen), in
  oktober nog 13 sites.
  - *Engels:* 580. Daarvan komen de meeste uit Azië: Factly 226, Fact
    Crescendo Sri Lanka 163, VERA Files 86. Uit de VS en het VK alleen
    FactCheck.org (23) en PolitiFact (18, laatste op 14 juli), plus DW (15).
  - *Spaans:* 6. *Duits:* 20 (BR24 Faktenfuchs 13, DW 7).
  - *Portugees en Chinees:* 0. De laatste Chinese check is van 2 augustus
    2025.
- **Voor de beeldroute (#32.17):** een screenshot wordt herkend als de check
  van de factchecker in de database staat. Bij een vers beeld uit de VS,
  Europa, Latijns-Amerika of de Chinese wereld is dat nu bijna nooit zo.

### 8.3 Tegen de lijsten van actieve factcheckers

**IFCN** (`data/bronnen/extern/ifcn/actief.tsv`: 138 actieve ondertekenaars op
28 oktober 2026, 137 met een site). Soms is de site in het IFCN-profiel die
van het bedrijf, niet die van de checks. Dan telde ik de site van de checks:
AP als apnews.com, Reuters als reuters.com, AFP met alle afp.com-subdomeinen,
dpa ook met presseportal.de, EFE als efe.com.
- 70 van de 137 staan in de database, 67 niet.
- 8 hebben een check sinds 1 mei 2026: Factly (335), Fact Crescendo (285),
  VERA Files (89), You Turn (60), ARIJ (30), FactCheck.org (24), DW (22) en
  PolitiFact (18).
- Van de 70 in de database heeft 45 de laatste check vóór 2025.
- **Helemaal niet in de database**, onder meer: AP, Correctiv, Snopes, Lead
  Stories, Aos Fatos, Estadão Verifica, EFE, France 24 Observers, India Today,
  Factchequeado, Teyit, StopFake, Faktisk en Demagog (Polen en Tsjechië).
- **Bijna niet:** AFP (2 checks, 2019), Reuters (2, 2020), Full Fact (1,
  2019).

**Duke Reporters' Lab** (https://reporterslab.org/locations/, gelezen op 1
november 2026; de kaart bevat alle 665 records in de pagina zelf):
- 442 actief en 223 niet meer, in 116 landen.
- De 442 actieve hebben 382 verschillende sites. AFP, PesaCheck en
  PolitiFact staan er per land of staat meer keer in.
- Duke vult de taal maar bij 23 van de 665 in. De taal hieronder komt
  daarom van het land.

| | sites | check sinds mei | 20+ checks, niets sinds mei | 1–19 checks | geen enkele |
|---|---|---|---|---|---|
| alle actieve | 382 | 14 | 78 | 50 | **240** |
| Engels (VS, VK, Ierland, Australië, Nieuw-Zeeland, Canada) | 66 | 2 | 14 | 6 | 44 |
| Spaans (Spanje en Latijns-Amerika) | 38 | 0 | 7 | 11 | 20 |
| Duits (Duitsland, Oostenrijk, Zwitserland) | 12 | 2 | 2 | 3 | 5 |
| Portugees (Brazilië, Portugal) | 15 | 0 | 4 in deze twee kolommen samen | (zie links) | 11 |
| Chinees (Taiwan, China met Hongkong, Singapore, Maleisië) | 11 | 0 | 3 | 0 | 8 |

De grote namen per taal:
- **Engels.**
  - *Geen enkele check:* AFP (factcheck.afp.com), AP, Snopes, Lead Stories,
    CBS, NBC, ABC News, Newsweek, CBC, The Irish Times, The Ferret,
    Factchequeado.
  - *Verouderd:* BBC (laatste 2021), Reuters (2020), USA Today (2020), The
    New York Times (2021), Full Fact (2019), AAP (2020), ABC Australië
    (2023), PA Media en TheJournal.ie (februari 2025), The Dispatch (juli
    2025).
- **Spaans.**
  - *Geen enkele:* AFP Factual, EFE Verifica, Animal Político, Ojo Público,
    Convoca, Ecuador Chequea, Cotejo, Reverso.
  - *Verouderd:* Newtral en Maldita (beide 2020), Chequeado (november 2024),
    La Diaria (juni 2025), Fast Check CL (oktober 2025).
- **Duits.**
  - *Geen enkele:* AFP Faktencheck, Correctiv, WDR, ZDF, EBU Spotlight.
  - *Verouderd:* dpa (5.432 checks, laatste 20 mei 2025), APA (maart 2024).
  - *Vers:* BR24 Faktenfuchs en DW.
- **Portugees.**
  - *Geen enkele:* AFP Checamos, Aos Fatos, Estadão Verifica.
  - *Verouderd:* Boatos.org (3.976, oktober 2024), Lupa (3.318, september
    2024), Comprova (augustus 2024), Polígrafo (4, december 2024).
- **Chinees.**
  - *Geen enkele:* Annie Lab, HKBU Fact Check, Tencent Jiaozhen, TSTM,
    askST.
  - *Verouderd:* Taiwan FactCheck Center (461, maart 2025), MyGoPen (499,
    juli 2024), Factcheck Lab (66, juli 2024).

Per land, in sites (check sinds mei / alleen oude / geen):

| land | sites | sinds mei | alleen oude | geen |
|---|---|---|---|---|
| VS | 48 | 2 | 9 | 37 |
| India | 28 | 3 | 15 | 10 |
| Frankrijk | 14 | 0 | 5 | 9 |
| Indonesië | 11 | 0 | 5 | 6 |
| Brazilië | 10 | 0 | 3 | 7 |
| Filipijnen | 9 | 2 | 2 | 5 |
| VK | 9 | 0 | 6 | 3 |
| Duitsland | 8 | 2 | 2 | 4 |
| Spanje | 8 | 0 | 5 | 3 |

**Het veld krimpt ook zelf.** Bron: de census van Duke van 12 juni 2026
(https://reporterslab.org/2026/06/12/2026-census-fact-checking-losses-continue-amid-funding-pressure-but-most-projects-persist/).
- Eind 2025 waren er 441 actieve projecten, op 1 juni 2026 437.
- In 2025 begonnen er 10 en stopten er meer dan 30.
- In de VS daalde het aantal van 65 naar 61.
- In 2025 stopten de Fact Checker van de Washington Post en Logically
  Facts. Meta stopte begin 2025 met zijn factcheckprogramma in de VS.
- Driekwart van de ruim 100 factcheckers in een enquête van het IFCN noemt
  zich financieel kwetsbaar of in crisis.

### 8.4 Wie zet nog ClaimReview in zijn artikelen?

**Wat er in de open feed komt.**
- Data Commons zegt dat de feed ClaimReview bevat die "created via the
  Google Fact Check Markup Tool and the new ClaimReview Read/Write API" is
  (https://datacommons.org/factcheck/download).
- De oudere onderzoeksset noemt Data Commons zelf een deelverzameling die
  "not representative" is (https://datacommons.org/factcheck/faq).
- Wie ClaimReview zelf in de pagina zet, komt er dus nooit in.
- In juni 2025 kondigde Google aan dat ClaimReview in de weken en maanden
  daarna uit de zoekresultaten zou verdwijnen
  (https://developers.google.com/search/blog/2025/06/simplifying-search-results;
  Nieman Lab, 30 juni 2025:
  https://www.niemanlab.org/2025/06/google-kills-the-fact-checking-snippet/).
  Fact Check Explorer blijft bestaan.
- Daarna zakte de feed van 36 naar 13 sites per maand (§8.2).

**Gemeten op de sites zelf** (1 november 2026):
- Per site eerst de lijstpagina in de browser. Daarna 2–4 recente artikelen
  en robots.txt van dezelfde site, verder niets.
- "Nu ruwweg" is het aantal artikelen op de eerste lijstpagina, gedeeld
  door de dagen die ze beslaan. Dat geeft een orde van grootte.
- "Geweerd" betekent: robots.txt noemt die crawler bij naam en sluit hem
  uit.

| factchecker | taal | in de database | ClaimReview in recente artikelen | robots.txt voor gewone crawlers | nu ruwweg |
|---|---|---|---|---|---|
| AFP Fact Check | en | 2 (2019) | ja | open; GPTBot en CCBot geweerd | 28 in 8 dagen, ~100 per maand |
| AFP Factual | es | 0 | ja | open | 28 in 4 dagen, ~200 per maand |
| AFP Faktencheck | de | 0 | ja | open | 28 in 2 maanden, ~13 per maand |
| AFP Checamos | pt | 0 | ja | open | 28 in 9 dagen, ~95 per maand |
| Snopes | en | 0 | ja (2 van 2) | open; GPTBot, ClaudeBot en CCBot geweerd | 21 in 7 dagen, ~90 per maand |
| Full Fact | en | 1 (2019) | ja (2 van 2) | open | niet geteld |
| Lead Stories | en | 0 | ja bij checks (1 van 2; een analyse niet) | open | nieuwste op de voorpagina: augustus 2026 |
| AAP FactCheck | en | 125 (2020) | ja (3 van 3) | open | niet geteld |
| EFE Verifica | es | 0 | ja (3 van 3) | open | niet geteld |
| Annie Lab (Hongkong) | taal niet nagegaan | 0 | ja (3 van 3) | open | ~5 per maand (54 in 2026 op de voorpagina) |
| Maldita | es | 619 (2020) | deels (1 van 2) | open | 18 in 5 weken op de eerste pagina |
| Newtral | es | 1.602 (2020) | deels (1 van 3) | open; CCBot geweerd | niet geteld |
| Factchequeado | es | 0 | deels (1 van 3) | niet nagegaan | niet geteld |
| Aos Fatos | pt | 0 | deels (1 van 3) | open; o.a. GPTBot geweerd | niet geteld |
| Estadão Verifica | pt | 0 | deels (1 van 3) | open; drie AI-regels | niet geteld |
| PolitiFact | en | 8.099 (laatste 14 juli 2026) | **nee: geen enkele gestructureerde data op de nieuwe site** | open; 10 seconden tussen verzoeken | niet geteld |
| AP Fact Check | en | 0 | nee (0 van 4) | open; GPTBot, ClaudeBot en CCBot geweerd | niet geteld |
| USA Today | en | 104 (2020) | nee (0 van 2) | open | nieuwste in de Europese versie: februari 2025 |
| Reuters Fact Check | en | 2 (2020) | niet nagegaan: de site toonde een blokkade | **dicht**: `Disallow: /` voor iedereen | — |
| dpa-Faktencheck | de | 5.432 (laatste 20 mei 2025) | nee (0 van 2) | open; 55 crawlers bij naam geweerd, ook ClaudeBot | 50–66 per maand (maart–oktober 2026) |
| Correctiv | de | 0 | nee (0 van 2) | open | 21 in een maand |
| Lupa (nu agencialupa.org) | pt | 3.318 (september 2024) | nee (0 van 3) | niet nagegaan | niet geteld |
| Polígrafo | pt | 4 (december 2024) | nee (0 van 3) | open | niet geteld |
| Chequeado | es | 19 (november 2024) | nee (0 van 7) | open | niet geteld |
| Taiwan FactCheck Center | zh | 461 (maart 2025) | nee (0 van 3) | open | 9 in 9 dagen, ~30 per maand |
| MyGoPen | zh | 499 (juli 2024) | nee (0 van 3) | open | minstens 10 in oktober |

Wat opvalt:
- **AFP is de grootste bron van verse checks die nu ontbreekt**, in vier van
  de vijf talen, en zet ClaimReview nog. Snopes komt daarna. AFP weert
  GPTBot en CCBot, Snopes en AP weren daarnaast ook ClaudeBot. Gewone
  crawlers weren ze niet. Een ophaler van Factiz meldt zich dus eerlijk onder een eigen
  naam. De gebruiksvoorwaarden van elke site moeten eerst gelezen worden;
  dat is niet nagegaan.
- **Vijf grote sites stonden ooit in de feed en zijn met ClaimReview
  gestopt:** PolitiFact, dpa, Lupa, Taiwan FactCheck Center en MyGoPen.
  Hun checks verschijnen nog wel (dpa 50–66 per maand).
- **Reuters is alleen via een afspraak te krijgen:** robots.txt sluit alle
  crawlers uit, en het staat ook niet in FACTors.

### 8.5 Routes per groep die ontbreekt

| route | wat het oplevert | voorwaarden en licentie | kosten | oordeel |
|---|---|---|---|---|
| **1. De open feed van Google** (wat we nu gebruiken) | ~260 checks per maand, 13 sites in oktober; vooral India, Sri Lanka, de Filipijnen en Iran | CC BY op de compilatie, plus `sdLicense` per check (FAQ hierboven) | $0 | houden. Het is de enige bron die we vrij mogen doorgeven, maar hij krimpt |
| **2. FACTors** (https://github.com/altuncu/FACTors) | 118.112 Engelse claims uit 117.993 checks van 39 IFCN- en EFCSN-organisaties, 1995–2025. Onder meer PolitiFact 20.977, Snopes 19.792, AFP 11.799, Full Fact 4.533, AAP 1.474, Lead Stories 497 en AP 182 (`data/org_stats.csv`). **Geen Reuters.** Zonder de tekst van de artikelen | MIT op de repository (code en compilatie). De claimzinnen komen van de sites van de factcheckers, en MIT maakt die niet vrij. Einddatum in 2025 niet nagegaan (artikel van 14 mei 2025, laatste wijziging februari 2026) | $0, maar de CSV moet gedownload worden (repository ~31 MB): dat vraagt toestemming | goed voor het **verleden** in het Engels, niet voor verse checks. Eerst de overlap per URL meten |
| **3. Fact-Check Insights** (https://www.factcheckinsights.org) | 257.884 checks van 188 organisaties, elke dag bijgewerkt, met MediaReview (welk beeld of welke video) | Zie hieronder | $0; een brief van de PO | kans onzeker, want Factiz is geen factchecker |
| **4. Afspraak met AFP of Reuters** | AFP Fact Check in 24 talen, van ruim 150 onderzoekers (https://www.afp.com/en/our-offer/afp-fact-check) | Zie hieronder | onbekend, betaald | alleen nodig als Factiz checks wil tonen of doorgeven. Reuters is de enige grote die alleen zo kan |
| **5. Zelf beleefd ophalen, met ClaimReview** | Volledig: AFP (en, es, de, pt), Snopes, Full Fact, Lead Stories, AAP, EFE Verifica, Annie Lab. Deels: Maldita, Newtral, Factchequeado, Aos Fatos, Estadão Verifica. In het Engels, Spaans en Portugees samen naar schatting meer dan 500 per maand | Zie hieronder | $0 | **de grootste winst** voor Engels, Spaans en Portugees. Reuters valt erbuiten |
| **5b. Zelf ophalen, zonder ClaimReview** | Duits: dpa (50–66 per maand) en Correctiv (~20). Chinees: Taiwan FactCheck Center (~30) en MyGoPen. Verder PolitiFact, AP, Lupa, Polígrafo en Chequeado | Zoals route 5, plus per site regels om de bewering en het oordeel uit de pagina te halen (kop, label). Breekbaarder: onderhoud bij elke wijziging van een site | $0 per site met regels; met een taalmodel enkele dollars per duizend checks (niet berekend) | de enige route naar volume in het Duits en Chinees. Een afspraak met dpa kan ook; niet nagegaan of dpa dat aanbiedt |

**Fact-Check Insights (route 3), de voorwaarden.**
- De compilatie staat onder CC BY.
- De gebruiksvoorwaarden (december 2025) laten alleen factcheckorganisaties
  en -professionals toe.
- Doorgeven en commerciële producten op basis van de data zijn verboden
  zonder schriftelijke toestemming. Voor "producten, onderzoek, integraties"
  vragen ze contact op te nemen (https://www.factcheckinsights.org/terms).
- **Nieuw:** sinds 2025 beheren Maldita.es en Full Fact het, niet meer Duke
  (https://www.factcheckinsights.org/about). Een aanvraag gaat dus naar
  contact@mail.factcheckinsights.org. Dat stelt PLAN #d2 bij.

**AFP en Reuters (route 4), de voorwaarden.**
- AFP verkoopt AFP Fact Check als product voor uitgevers die de checks op
  hun eigen site zetten ("Request a trial"). Een prijs staat er niet.
- Voor zoeken en linken is geen afspraak nodig: AFP zet zijn ClaimReview al
  openbaar (route 5).
- Voor Reuters vond ik geen openbaar aanbod voor factchecks. Reuters Connect
  werkt op offerte [secundair].
- De voorwaarden van reuters.com heb ik niet gelezen: de site toonde een
  blokkade.

**Zelf ophalen (route 5), de voorwaarden.**
- robots.txt respecteren, één verzoek tegelijk per site, de wachttijd van de
  site aanhouden (PolitiFact 10 seconden), en een eigen naam als crawler.
- AFP zet geen `sdLicense` in zijn ClaimReview. De gebruiksvoorwaarden per
  site zijn niet gelezen.
- Bewaren om te zoeken en doorgeven zijn twee aparte vragen. Tot de PO
  beslist, gaan deze checks in de tabel `bron` met `herverdeelbaar = 0`
  (E7.S1-AC2).
- PROTOCOL §11.5 noemde deze route al.
- Wat al bestaat: de ophaler met robots-controle (`doublecheck/beeldindex.py`,
  `mag`) en het lezen van ClaimReview (`doublecheck/feed.py`).

**Wat niet kan of niet loont:**
- *Google Fact Check Tools API:* afgewezen in PROTOCOL §11.5. De
  voorwaarden verbieden opslaan, doorgeven en afgeleide werken. Ik zocht een
  nieuw feit en vond er geen: dat Google ClaimReview uit de zoekresultaten
  haalde, verandert die voorwaarden niet. Niet heropend.
- *ClaimsKG:* de laatste uitgave is van januari 2023, met 13 sites, onder
  CC BY-SA [secundair; record bij GESIS]. Te oud.
- *Common Crawl en Web Data Commons:* ClaimReview is daar geen
  kant-en-klaar deel [secundair]. Bovendien weren AFP, Snopes, AP en Newtral
  de crawler van Common Crawl (CCBot), dus juist zij ontbreken.
- *Cofacts* (Taiwanese tipline, Chinees):
  - de data staat onder CC BY-SA 4.0 op Hugging Face, alleen met een
    account en een gebruikersovereenkomst
    (https://huggingface.co/datasets/Cofacts/line-msg-fact-check-tw);
  - dat is aanmelden, dus de PO beslist;
  - door de ShareAlike-voorwaarde moet wat we doorgeven ook CC BY-SA zijn,
    terwijl de database CC BY is;
  - het aantal checks is niet nagegaan.
- *MultiClaim* (SemEval-2025 taak 7): alleen voor onderzoek, op aanvraag
  (PLAN #28.1). Niet om in het product te zetten.

### 8.6 Wat de PO kan doen, op volgorde van opbrengst

Verse checks per maand, per taal. "Nu" is het gemiddelde van de open feed in
2026. De routes zijn ruwe tellingen van lijstpagina's in de laatste week van
oktober 2026 (§8.4), dus een orde van grootte.

| taal | nu | route 5: zelf ClaimReview ophalen | route 5b: zelf ophalen zonder ClaimReview | route 2: FACTors |
|---|---|---|---|---|
| Engels | ~110, vooral uit Azië | AFP ~100, Snopes ~90, plus Full Fact, Lead Stories en AAP (niet geteld) | PolitiFact, AP (niet geteld) | 118.112, alleen tot 2025 |
| Spaans | ~1 | AFP Factual ~200, plus EFE en een deel van Maldita, Newtral en Factchequeado | Chequeado | — |
| Duits | ~5 | AFP Faktencheck ~13 | dpa 50–66, Correctiv ~20 | — |
| Portugees | 0 | AFP Checamos ~95, plus een deel van Aos Fatos en Estadão Verifica | Lupa, Polígrafo | — |
| Chinees (versie 2) | 0 | Annie Lab ~5 | Taiwan FactCheck Center ~30, MyGoPen 10+ | — |

**De drie routes met de meeste verse checks:**
1. **Zelf ClaimReview ophalen (route 5)** bij AFP, Snopes, EFE en de anderen
   die het nog zetten.
   - *Opbrengst:* Engels, Spaans en Portugees van ~110 naar naar schatting
     meer dan 500 per maand; Duits een beetje. $0.
   - *De PO beslist:* mag Factiz deze sites ophalen? En blijven deze checks
     niet door te geven tot de uitgevers of een jurist iets anders zeggen?
2. **Zelf ophalen zonder ClaimReview (route 5b)** bij dpa en Correctiv, en
   voor later Taiwan FactCheck Center en MyGoPen.
   - *Opbrengst:* de enige weg naar volume in het Duits, ~70–85 per maand.
   - *Kosten:* meer werk. Eerst dpa vragen of ze een feed hebben kan ook.
3. **FACTors (route 2).**
   - *Opbrengst:* geen verse checks, wel het Engelse verleden van AFP,
     Snopes, Full Fact en PolitiFact tot 2025. Voor de beeldroute telt dat,
     want een viraal beeld komt vaak terug.
   - *Wat nodig is:* de download vraagt toestemming; eerst de overlap meten.

**Daarna, als de PO wil:**
- Cofacts voor Chinees (aanmelden);
- een brief aan Fact-Check Insights (nu Maldita.es en Full Fact);
- pas als Factiz checks wil tonen of doorgeven: een gesprek met AFP en
  Reuters.

### 8.7 AI-modellen en hulpmiddelen in ontwikkeling (2025–2026)

Wat al gemeten is, staat hier niet opnieuw:
- *tekst:* MiniLM, multilingual-e5-base, LaBSE, voyage-4-nano en bge-m3
  (BENCHMARK §73–§74);
- *beeld:* PDQ, DINOv2-small, panelen en SIFT (§185–§187).

#### 8.7.1 Claims koppelen over talen heen (nu bge-m3 met bge-reranker-v2-m3)

De bron is de meertalige ranglijst MTEB (Multilingual, v2), gelezen op 1
november 2026
(https://mteb-leaderboard.hf.space/benchmark/MTEB(Multilingual%2C%20v2)).
Voor Factiz telt het deel "zoeken". bge-m3 haalt daar 54,59.

| model | wat | licentie | gemeten | op een Mac M1 met 16 GB |
|---|---|---|---|---|
| **harrier-oss-v1-0.6b** (Microsoft, maart 2026) | tekstvectoren, 94 talen, gebouwd op Qwen3 | MIT (https://huggingface.co/microsoft/harrier-oss-v1-0.6b, zelf nagelezen) | gemiddeld 69,0 (modelkaart), zoeken 70,75 (ranglijst) | ja: 0,6B, zo groot als bge-m3 |
| harrier-oss-v1-270m | kleinere versie | MIT | gemiddeld 66,5, zoeken 66,38 | ja |
| **Qwen3-Embedding-0.6B** (juni 2025) | tekstvectoren, 100+ talen | Apache-2.0 | gemiddeld 64,34, zoeken 64,65 (ranglijst) | ja |
| **Qwen3-Reranker-0.6B** | herordenaar | Apache-2.0 | zoeken na herordenen 66,36, tegen 58,36 voor bge-reranker-v2-m3. Gemeten door Qwen zelf (https://huggingface.co/Qwen/Qwen3-Reranker-0.6B) | ja |
| EmbeddingGemma-300m (Google) | kleine tekstvectoren | eigen Gemma-licentie | gemiddeld 61,14, zoeken 62,49 (ranglijst) | ja |
| jina-embeddings-v5, jina-reranker-v3 | tekstvectoren, herordenaar | **CC BY-NC 4.0**: niet commercieel | v5-small 67,7 (eigen modelkaart) | ja, maar valt af om de licentie |
| een opvolger van bge-m3 | — | — | niet gevonden | — |

**SemEval-2025 taak 7** is precies de taak van Factiz
(https://arxiv.org/html/2505.10740):
- *De taak:* bij een post de bestaande check vinden, in 10 talen en over
  talen heen, uit 206.000 checks van MultiClaim.
- *De uitslag* (staat de juiste check in de top 10?):

| | zelfde taal | over talen heen |
|---|---|---|
| de winnaar (PINGAN AI, geen artikel) | 0,960 | 0,859 |
| het beginpunt, multilingual-e5-large | 0,859 | 0,637 |

- *Wat de organisatoren concluderen:* bijtrainen op eigen paren met moeilijke
  foute voorbeelden levert het meeste op; herordenen helpt vooral over talen
  heen.

*Voor Factiz:*
- Een ranglijst zegt weinig over onze eigen claims. In §73 deed e5 het
  binnen één taal beter en over talen heen slechter.
- Wat beslist, is een proef van $0 op de vaste set van §73 (15.703 claims,
  716 zoekvragen), met de regels van §73–§74.
- Een wissel van model is een release (B22) en vraagt opnieuw indexeren
  (DR6).

#### 8.7.2 Een beeld herkennen en herleiden (nu PDQ, in proef SIFT)

| kandidaat | wat | licentie | gemeten | op een Mac M1 met 16 GB |
|---|---|---|---|---|
| **CopyNCE** (ICCV 2025) | een vector per beeld, plus een vergelijker die per paar zegt of het een kopie is, ook bij uitsnede en bewerking | Apache-2.0 (https://github.com/eddielyc/CopyNCE, zelf nagelezen) | DISC21 (bewerkte kopieën): de vergelijker haalt 83,5 µAP met de vrijgegeven gewichten, 88,0 na bijtrainen (README) | ja: klein ViT-S-model |
| SSCD (Meta, 2022) | een vector per beeld, getraind op kopieën met tekst en uitsnede erover | MIT (https://github.com/facebookresearch/sscd-copy-detection) | boven een overeenkomst van 0,75 een kopie, met 90% precisie op DISC (README) | ja |
| LightGlue met ALIKED of DISK | koppelt punten tussen twee beelden, met een zekerheid per koppeling | Apache-2.0 (https://github.com/cvg/LightGlue); SuperPoint niet, die heeft een beperkende licentie | 20 paren per seconde op een gewone processor (README) | ja |
| DINOv3 (augustus 2025), SigLIP 2 (februari 2025) | algemene beeldvectoren | eigen DINOv3-licentie; Apache-2.0 | voor kopieën niet nagegaan. DINOv2 vond in §185 7 van de 100 | ja |
| een opvolger van PDQ | — | — | niet gevonden | — |

**AI-gemaakt of bewerkt:**
- **Deepfake-Eval-2024** (TrueMedia; https://arxiv.org/html/2503.02857v5):
  - *De set:* 1.975 echte beelden die gebruikers in 2024 aanboden, alleen
    met gezichten.
  - *Open detectors:* AUC 0,52–0,56 (0,5 is gokken), tegen 0,94–0,99 op hun
    eigen toetsen. Na bijtrainen hoogstens 0,73.
  - *De beste betaalde detector, zonder merknaam:* AUC 0,90, precisie 0,99,
    vangst 0,71.
- **Chameleon / AIDE** (ICLR 2025; https://arxiv.org/abs/2406.19435): bijna
  alle negen bestaande detectors noemen de moeilijke AI-beelden echt.
- **CERTH** (mei 2026; https://arxiv.org/abs/2605.02567): AI-beelden uit het
  wild verzamelen via factcheckartikelen, en daarmee detectors bijtrainen.
  Dat gaf 8 à 9 punten meer.
- **TrueMedia.org** sloot op 14 januari 2025. De code is MIT, de gewichten
  zijn niet gedeeld (https://github.com/truemediaorg/ml-models).

*Voor Factiz:*
- *De proef die loont:* de vergelijker van CopyNCE als stap "het beeld
  bevestigt" in #32.17.
  - Alleen tegen de vijf kandidaten die de tekst vond.
  - Te meten op de 275 kopieën en 369 beelden van §187. Daar gaf SIFT bij
    een derde van de kopieën een verkeerd beeld als beste treffer.
  - $0, na de uitslag van #32.17.
- *Een detector van AI-beelden niet proberen.* Dat bevestigt #32.18: eerst
  de bron.

#### 8.7.3 Tekst en beeld samen controleren

| kandidaat | wat | licentie | gemeten | op een Mac M1 met 16 GB |
|---|---|---|---|---|
| **Qwen3-VL-Embedding-2B** (januari 2026) | vectoren voor tekst, beelden en schermafdrukken in één ruimte, 30+ talen | Apache-2.0 (https://huggingface.co/Qwen/Qwen3-VL-Embedding-2B) | MMEB-V2 (beeld en tekst samen) 73,2. Op tekst alleen (MMTEB) 63,87, tegen 59,56 voor bge-m3 op dezelfde kaart | ja (~4 GB) |
| Gemma 4 (maart–mei 2026) | leest tekst en beelden; E2B, E4B, 12B, 26B, 31B | Apache-2.0 | op factchecktoetsen niet nagegaan | E4B en 12B in 4 bit |
| Qwen3.5 (februari 2026) | leest tekst en beelden; 0,8B tot 397B | Apache-2.0 | niet nagegaan | 4B ja |
| Qwen3-VL-8B (2025) | leest tekst en beelden | Apache-2.0 | AVerImaTeC 2026: 0,256, tegen 0,546 voor Gemini 2.5 Pro en 0,347 voor GPT-5.1 (https://arxiv.org/html/2602.11221) | ja, in 4 bit |
| DEFAME (ICML 2025) | factchecksysteem in zes stappen, met zoeken en omgekeerd zoeken | Apache-2.0 (https://github.com/multimodal-ai-lab/DEFAME) | op ClaimReview2024+: 69,7 met GPT-4o, 32,6 met een open model (LLaVA-1V) (https://arxiv.org/html/2412.10510) | het systeem wel, een goed model erin niet |
| Llama 3.2 Vision | leest tekst en beelden | bedrijven met hun hoofdvestiging in de EU krijgen geen rechten op de modellen met beeld (https://www.llama.com/llama3_2/use-policy/) | — | valt af |

*Voor Factiz:*
- Een open model als rechter haalt het niet: 0,26 tegen 0,55.
- Wel zijn er twee proeven van $0, na #32.17:
  - Qwen3-VL-Embedding-2B als extra sleutel: de schermafdruk direct tegen de
    claimtekst en de artikelbeelden.
  - De beschrijving van de foto lokaal maken met Gemma 4 E4B in plaats van
    Haiku. Dan blijft het beeld op het apparaat (raakt B43).

#### 8.7.4 SynthID en C2PA

- **SynthID Detector** (Google), bron:
  https://blog.google/innovation-and-ai/models-and-research/google-deepmind/synth-id-ai-content/
  (zelf nagelezen).
  - *Sinds 7 oktober 2026* voor iedereen, wereldwijd, in het Engels.
  - *Wat het doet:* een website die zegt of een beeld, video of geluid
    gemaakt is met AI van Google of partners, ook OpenAI, NVIDIA, Kakao en
    Apple.
  - *Geen API* voor willekeurige beelden gevonden.
  - *Het beeld gaat naar Google.* Dat is het besluit van B43.
  - *Geen watermerk* betekent niet dat het beeld echt is.
- **C2PA:**
  - de specificatie staat op versie 2.5 (https://spec.c2pa.org/, datum niet
    nagegaan);
  - de bibliotheek c2pa-rs is MIT en Apache-2.0
    (https://github.com/contentauth/c2pa-rs);
  - een schermafdruk is een nieuw bestand zonder die gegevens, en de meeste
    platforms halen ze bij het uploaden al weg [secundair];
  - voor de screenshots die Factiz meestal krijgt, levert C2PA dus bijna
    niets op. Bij een origineel bestand is het lokaal lezen een gratis
    signaal met bron.

### 8.8 Niet nagegaan, en wat dicht bleef

**Niet nagegaan:**
- de gebruiksvoorwaarden van de afzonderlijke factchecksites (AFP, Snopes,
  Full Fact, EFE en de anderen) over hergebruik van hun ClaimReview;
- of Reuters ClaimReview zet, en de voorwaarden van reuters.com;
- de einddatum van FACTors in 2025, en hoeveel Engelse checks erin staan die
  wij niet hebben (daarvoor is de download nodig);
- of Fact-Check Insights AFP en Reuters bevat;
- het aantal checks per maand bij Full Fact, Lead Stories, AAP, EFE,
  Newtral, Factchequeado, Aos Fatos, Estadão Verifica, Lupa, Polígrafo en
  Chequeado;
- of AFP in het Chinees publiceert;
- of dpa een feed of dienst voor anderen aanbiedt;
- hoeveel checks Cofacts heeft;
- deel B: de modelkaarten van jina-embeddings-v4, llama-embed-nemotron-8b,
  snowflake-arctic-embed-l-v2.0, multilingual-e5-large-instruct,
  gte-multilingual-base, Moondream 3, MASt3R en XFeat, en de cijfers van
  Hive, Reality Defender en Sightengine.

**Dicht gebleven**, voor de PO om zelf te openen:
- https://www.reuters.com/fact-check/ (een artikel gaf "Toegang is tijdelijk
  beperkt"; niet omzeild).

**Niet geopend om zuinig te blijven** (deel B):
- https://docs.cloud.google.com/vertex-ai/generative-ai/docs/image/verify-watermark
- https://arxiv.org/pdf/2504.20865 (AI-GenBench)
- https://arxiv.org/pdf/2607.05434 (OpenAI en SynthID)
- https://tech.ebu.ch/news/2025/09/and-that-s-a-wrap-conclusion-of-the-veraai-project-on-ai-against-disinformation-and-next-steps
  (het einde van vera.ai)

---

## 9. Hoe de grote AI-bedrijven nepnieuws aanpakken (bureauonderzoek, 7 november 2026)

*Aanleiding (PO 2026-11-07):* "Eigenlijk is het helemaal niet zo verwonderlijk dat wij tegen Gemini niet zo veel verschil
maken ... het voor ons misschien wel interessant om op zoek te gaan naar research papers over hoe de grote AI-bedrijven de
alignment van nepnieuws regelen. Daar kunnen wij veel van leren, en daaruit kunnen we ook afleiden of wij daarin verschil
kunnen maken met ons weinige budget." Na de duels van BENCHMARK §235 en §236. Gezocht door een onderzoeksagent met
webzoeken; *[lab]* is wat een bedrijf over zichzelf zegt, *[onafh.]* is van buiten gemeten. Wat §6 al heeft (ISD,
NewsGuard en het Pravda-netwerk, Brennan, EBU/BBC, AI Forensics), staat hier niet opnieuw.

### 9.1 Kort

- **Geen eigen filter tegen nepnieuws.** Geen bedrijf heeft een algemene classificeerder voor nepnieuws. Llama Guard van
  Meta dekt alleen onjuiste informatie over hoe stemmen werkt [20]. De rest is training op eerlijkheid, op durven zeggen
  "ik weet het niet" en op zoeken met bronvermelding.
- **De vooruitgang is echt, maar vooral zelf gemeten.** GPT-5 Thinking maakt met zoeken 78% minder antwoorden met een
  grote fout dan o3 *[lab]* [5]. Van buiten: bij nieuws gaat de bronvermelding in meer dan 60% van de antwoorden mis [25],
  en van 280 vragen over echte nieuwsfoto's waren er 14 helemaal goed (plaats, datum, fotograaf) [26] *[onafh.]*.
- **Zoeken is de oplossing én de zwakke plek.** Eén pagina van een aanvaller kwam in 31% van de antwoorden terecht, en
  maar ongeveer een kwart daarvan met een waarschuwing [30]. Dat chatbots Kremlinsites noemen, komt vooral door
  *datalacunes*: vragen naar details waar gewone media niets over schreven [29] *[onafh.]*.
- **Meepraten en te stellig zijn zit erin.** Het komt uit de training op wat mensen prettig vinden [11] en uit toetsen
  die een gok hoger waarderen dan "weet ik niet" [2]. Een update kan het erger maken: OpenAI draaide in april 2025 een
  versie van GPT-4o terug [5].
- **Juist is niet hetzelfde als nuttig.** Een model dat 90% van de valse koppen goed aanwees, hielp mensen niet om waar
  van onwaar te onderscheiden; checks van mensen deden dat wel. Twijfelde het model bij een valse kop, dan geloofden
  mensen die kop juist méér (PNAS 2024) [35] *[onafh.]*.
- **Beelden en andere talen dan het Engels zijn overal het zwakst** [16, 26, 32, 33, 34].
- **Er komen minder nieuwe factchecks.** 437 actieve projecten, netto 23 minder in 2025 (Duke Reporters' Lab) [41].

### 9.2 Per bedrijf

- **OpenAI** *[lab]*:
  - de Model Spec met "Do not lie", "Don't be sycophantic" en "Express uncertainty" [1] (alleen de inhoudsopgave gelezen);
  - een artikel over waarom modellen verzinnen [2]: wie alleen goed of fout telt, beloont gokken. Het voorstel is antwoorden
    alleen boven een zekerheid t, en een fout t/(1−t) laten kosten;
  - SimpleQA telt goed, fout en *niet geprobeerd* apart [4];
  - GPT-5 is getraind om goed te zoeken, en meepraten werd een strafpunt in de training [5];
  - bij verkiezingen: samenwerking met Democracy Works en AP, en herkomstlabels (C2PA) [7].
- **Anthropic** *[lab]*:
  - de grondwet van Claude noemt eerlijkheid in zeven eigenschappen, waaronder *gekalibreerd* en *niet manipulerend*.
    Een bron vertrouwen past alleen als die "suitably reliable" is [8];
  - onderzoek naar kalibratie [9] en naar meepraten [11];
  - bij de verkiezingen van 2026 zocht Claude bij 92–95% van de vragen op het web, met officiële informatie over stemmen
    [12, 13];
  - een open toets met vragen in paren, van beide politieke kanten [14];
  - onderzoek naar vergiftiging: 250 gemanipuleerde documenten waren genoeg voor een smalle achterdeur in modellen van elke
    grootte [15].
- **Google DeepMind**:
  - FACTS (december 2025): elk model scoorde onder de 70%, en het laagst bij beelden [16];
  - SAFE splitst een antwoord in losse feiten en zoekt elk na; het was het in 72% eens met mensen, voor een twintigste van
    de prijs [17];
  - Grounding with Google Search, wat ons duel gebruikte: het model kiest zelf of het zoekt. De documentatie zegt niets
    over de kwaliteit van bronnen [18]; Google zegt dat de rangschikking en spamfilters van Search meewegen [19] *[lab]*;
  - na de fouten van AI Overviews in 2024 gaf Google datalacunes toe en weerde het harde nieuwsonderwerpen [21].
- **Meta:** Llama Guard heeft alleen een categorie voor onjuiste informatie over verkiezingen [20].
- **xAI (Grok):**
  - een "unauthorized modification" van de systeemprompt in mei 2025, waarna xAI beloofde de prompts te publiceren [22];
  - Grok 4 zocht bij omstreden onderwerpen eerst de posts van Musk op [23];
  - bij een met AI gemaakte video van een vliegveld zei Grok 31% van de keren dat het Tel Aviv was. Pas met een Community
    Note werd het beter [24] *[onafh.]*.
- **DeepSeek** *[onafh.]*: de Amerikaanse overheid (NIST, CAISI) mat dat V3.1 verhalen van de Chinese Communistische Partij
  herhaalt: 5% in het Engels en 12% in het Chinees, tegen 2–3% bij Amerikaanse modellen. Dat zit in de gewichten van het
  model zelf [32]. Dat sluit aan bij de waarheidstoets van PLAN #32.50.

### 9.3 Waar het misgaat

- **Vers nieuws:**
  - chatbots besluiten soms niet te zoeken en antwoorden met verouderde kennis [27];
  - aanvallen die zich als breaking news voordoen, werken het best [30] (cijfer uit een samenvatting, niet nagelezen).
- **Datalacunes en vergiftiging:** zie §9.1 [29, 30]. 7 tot 28% van de genoemde bronnen is zelf met AI gemaakt [31].
- **Andere talen:**
  - Gemini wordt bij oorlogsdesinformatie alleen in het Engels beter [33];
  - over 61.514 beweringen zijn de verschillen tussen talen groot, en GPT-4o weigerde 43% te beoordelen [34].
- **Beelden:** elk model noemde minstens één echte foto door AI gemaakt [26], en Gemini en Copilot hielden een nepfoto van
  Gemini voor echt [28].
- **Meepraten:** tot 100% meewerken aan onzinnige medische verzoeken [38]; chatbots gaven mensen 49% vaker gelijk dan
  mensen dat deden [39] (beide niet geopend).
- **Te stellig:** ChatGPT Search toonde twijfel in 15 van de 200 antwoorden en weigerde nooit [25].
- **Tegen factcheckers van beroep:**
  - LLM's zijn het matig eens met menselijke beoordelaars, en hun redenen leunen op de oppervlakte [37];
  - Renault e.a. vinden dat een LLM met zoeken het even vaak eens kan zijn als factcheckers onderling, maar dat bronnen
    beperken of zoeken uitzetten de juistheid verlaagt [40] (alleen de samenvatting).

### 9.4 Wat het betekent voor Factiz

**Waar Factiz verschil kan maken:**
1. **De check van een mens voorop**, met redactie, datum en adres [35]. Grok werd pas goed met een Community Note [24].
   Dat doet Factiz al met kring 1; v12 en v13 leggen nu ook uit waarom.
2. **Eén slechte pagina zet de kleur niet.** Groen vraagt twee goede uitgevers en rood een goede tegenspraak, dus een
   aanvaller of een datalacune bepaalt het oordeel niet [29, 30]. Wel kan de uitleg zo'n pagina herhalen. Een waarschuwing
   als een zin op één bron zonder band leunt, zou helpen; grote systemen waarschuwen maar in ~27% van de gevallen [30].
3. **De kleur laat zich niet ompraten:** de bronnenlijst beslist, niet het model [11, 38, 39]. Wel het model vastzetten en
   bij elke nieuwe versie opnieuw meten [5].
4. **Altijd zoeken** [27].
5. **Hergebruikte beelden** herkennen met een hash is opzoeken, geen oordeel over herkomst, en dat is waar modellen falen
   [26].
6. **Geen kleur moet iets zeggen.** Een kaal *onzeker* maakt een valse kop geloofwaardiger [35, 36]: zeg wat er gevonden is
   en wat ontbreekt.

**Waar Factiz bijna zeker niet wint:**
- vers gewoon nieuws: Google zoekt in zijn eigen index en rangschikking [18, 19], en het gelijkspel in de duels is
  waarschijnlijk het plafond;
- nieuwe AI-beelden herkennen [16, 26, 28];
- andere talen buiten onze eigen data, omdat Sonnet het taalgat meeneemt [33, 34];
- nieuwe beweringen op termijn, omdat er minder factcheckers komen [41]. Het voordeel van de database wordt hergebruikt en
  steeds terugkerend nepnieuws.

**Goedkoop over te nemen:**
- in onze metingen een prijs voor een verkeerde kleur, en *niet geprobeerd* apart tellen [2, 4];
- de openbare richtlijnen van AFP als werkwijze in de vraag aan de lezer: +4,8 punten op AVeriTeC, 61% goedkoper [42];
- losse feiten nalopen zoals SAFE, voor *klopt grotendeels* [17];
- de vragen in paren van Anthropic voor de politieke kant van #32.50 [14];
- elke wijziging van de vraag openbaar maken, zoals xAI beloofde [22].

**Niet de moeite:** een eigen training op eerlijkheid of een eigen classificeerder [20]; detectoren voor AI-beelden; de
lezer alleen de bronnen van de lijst laten lezen, want minder bronnen verlaagde de juistheid [40]. De lijst is voor de
kleur.

### 9.5 Bronnen

Geopend door de onderzoeksagent, tenzij anders vermeld.

1. OpenAI Model Spec, https://model-spec.openai.com/2026-10-29.html, 2026-10-29 (alleen de inhoudsopgave).
2. Kalai e.a., Why Language Models Hallucinate, https://arxiv.org/abs/2509.04664, 2025-09.
4. Wei e.a., SimpleQA, https://arxiv.org/abs/2411.04368, 2024-11 (samenvatting).
5. GPT-5 System Card, https://cdn.openai.com/gpt-5-system-card.pdf, 2025-08-13.
7. Tech Policy Press over de verkiezingsplannen, https://techpolicy.press/how-openai-google-and-anthropic-plan-to-handle-the-2026-us-midterms, 2026-06-10 (de pagina van OpenAI zelf gaf 403).
8. Claude's Constitution, https://www.anthropic.com/constitution, januari 2026.
9. Kadavath e.a., https://arxiv.org/abs/2207.05221, 2022 (niet geopend).
11. Sharma e.a., Towards Understanding Sycophancy, https://arxiv.org/abs/2310.13548, 2024 (niet geopend).
12. Anthropic, election safeguards update, https://www.anthropic.com/news/election-safeguards-update, 2026-04-24.
13. Anthropic, 2026 US midterms, https://anthropic.com/news/2026-us-midterms, 2026-10-14.
14. Anthropic, political even-handedness, https://www.anthropic.com/news/political-even-handedness, 2025-11-13.
15. Anthropic, small samples can poison LLMs, https://www.anthropic.com/research/small-samples-poison, 2025-10-09.
16. DeepMind, FACTS Benchmark Suite, https://deepmind.google/blog/facts-benchmark-suite-systematically-evaluating-the-factuality-of-large-language-models/, 2025-12-09.
17. Wei e.a., SAFE, https://arxiv.org/abs/2403.18802, 2024 (samenvatting).
18. Google, Grounding with Google Search, https://aistudio.google.com/docs/google-search.
19. Google, verkiezingen, https://publicpolicy.google/elections/.
20. Meta, Llama Guard 3, https://dev.meta.ai/llama/docs/model-cards-and-prompt-formats/llama-guard-3/, 2024.
21. Google, AI Overviews: about last week, https://blog.google/products/search/ai-overviews-update-may-2024/, 2024-05-30.
22. CNBC over xAI, https://www.cnbc.com/2025/05/15/musks-xai-grok-white-genocide-posts-violated-core-values.html, 2025-05-16.
23. Engadget over Grok 4, https://www.engadget.com/ai/grok-4-reportedly-checks-elon-musks-views-before-offering-its-opinion-130016794.html, 2025-07-11.
24. DFRLab, Grok tijdens de oorlog tussen Israël en Iran, https://dfrlab.org/2025/06/24/grok-struggles-with-fact-checking-amid-israel-iran-war/, 2025-06-24.
25. Tow Center, AI-zoekmachines en bronvermelding, https://www.cjr.org/tow_center/we-compared-eight-ai-search-engines-theyre-all-bad-at-citing-news.php, 2025-03-06.
26. Tow Center, foto's verifiëren, https://www.cjr.org/tow_center/why-ai-models-are-bad-at-verifying-photos.php, 2025-08-26.
27. Tow Center, waarom chatbots niet zoeken, https://www.cjr.org/tow_center/ai-chatbots-can-search-the-web-so-why-dont-they.php, 2026-01-27.
28. AFP via RNZ, https://www.rnz.co.nz/news/business/579586/ai-s-blind-spot-tools-fail-to-detect-their-own-fakes, 2025-11-21.
29. Alyukov e.a., HKS Misinformation Review, https://misinforeview.hks.harvard.edu/article/llms-grooming-or-data-voids-llm-powered-chatbot-references-to-kremlin-disinformation-reflect-information-gaps-not-manipulation, 2025-10-15.
30. Guerra e.a., Data-Void Exploits in Web-Searching LLMs, https://arxiv.org/abs/2610.30365, 2026-10-21 (samenvatting; cijfers per aanval uit een samenvatting door derden, niet nagelezen).
31. Allaham en Diakopoulos, Synthetic Sources?, https://arxiv.org/abs/2605.23684, 2026-05.
32. NIST CAISI, evaluatie van DeepSeek, https://www.nist.gov/document/caisi-evaluation-deepseek-ai-models-report, 2025-09-30.
33. Makhortykh e.a., https://arxiv.org/abs/2409.10697, 2024-09 (samenvatting).
34. Saju e.a., Facts are Harder Than Opinions, https://arxiv.org/abs/2506.03655, 2025 (samenvatting).
35. DeVerna e.a., PNAS, https://arxiv.org/abs/2308.10800, 2024-12 (samenvatting).
36. He, Horne en Nevo, https://arxiv.org/abs/2607.15364, 2026-07 (samenvatting).
37. Tai e.a., GenAI vs. Human Fact-Checkers, https://arxiv.org/abs/2502.14943, 2025-02 (samenvatting).
38. Chen e.a., npj Digital Medicine, https://www.ncbi.nlm.nih.gov/pmc/articles/PMC12534679/, 2025-10 (niet geopend).
39. Cheng e.a., Science, via https://news.stanford.edu/stories/2026/03/ai-advice-sycophantic-models-research, 2026-03 (niet geopend).
40. Renault e.a., Fact-Checking Using AI, https://doi.org/10.31234/osf.io/85quw_v5, 2026-09 (samenvatting; de percentages niet nagelezen).
41. Duke Reporters' Lab, telling 2026, https://reporterslab.org/?p=4294, 2026-06-12.
42. Chen, He en Li, SkillCheck, https://arxiv.org/abs/2610.25777, 2026-10-19.

*Niet nagelezen:* de tekst van de secties in de Model Spec, de scores per toets van Gemini 3 Pro, en een artikel in Nature
(2026) over Chinese staatsmedia in trainingsdata (achter een betaalmuur).

## 10. Wat anderen al oplosten: papers, code en modellen (bureauonderzoek, 7 november 2026)

*Aanleiding (PO 2026-11-07):* "Ik ben heel benieuwd of er diepgravende research papers zijn of speciale codebases of
modellen die ons kunnen helpen met de achterliggende intelligentie, dan kunnen we misschien een 'kikkersprong' maken over
problemen die andere al opgelost hebben." Gezocht door een onderzoeksagent; wat §2, §3.3 en §8.7 al noemen, staat hier
niet opnieuw. *Zelf nagelopen* (7 november, op de pagina zelf): de licenties van 5Pils, COVE, MiniCheck, EuroBERT,
LettuceDetect en de dataset van Burdisso, en de cijfers van COVE.

### 10.1 Kort

- **Een echte gebeurtenis met een verkeerde foto is nergens opgelost.** Open systemen die op de kunstmatige set
  NewsCLIPpings 87–93% halen, halen op echte gevallen (5Pils-OOC, 624 gecontroleerde foto's met een juist en een verkeerd
  bijschrift) 47–58%: weinig beter dan een munt. Wat wél werkt, is de *methode*: eerst vaststellen waar de foto echt
  vandaan komt (datum, plaats, gebeurtenis), en dan pas vergelijken met wat het bericht zegt. Mensen die die herleide
  herkomst zagen, hadden het 85,6% van de keren goed, zonder 34,4% (COVE, NAACL 2025, zelf nagelopen).
- **Een bericht koppelen aan een factcheck in een andere taal kan beter zonder nieuw model.** bge-m3 geeft naast zijn
  vectoren ook gewichten per woord; die twee samen haalden in SemEval-2025 taak 7 85,2 tegen 78,9 alleen de vectoren (de
  goede check in de top 10, zelfde taal). De winnaar haalde 96, maar beschreef zijn methode nergens.
- **Kleine lokale modellen kunnen nagaan of een bron een zin draagt,** maar vrijwel alleen in het Engels (MiniCheck, 0,8B,
  MIT). Voor Duits en Spaans is er LettuceDetect (MIT), gemeten op machinaal vertaalde data. Voor Portugees niets open.
- **Over de uitleg:** detail werkt beter dan een kaal label; de "truth sandwich" voegt niets toe aan een gewone,
  gedetailleerde correctie; en een AI-oordeel *onzeker* kan een valse kop geloofwaardiger maken. Dat steunt `lezer-v13`.
- **Geen open pijplijn met veel stappen** verslaat aantoonbaar "zoeken plus één keer lezen" op verse beweringen. Het
  zoeken is de bottleneck: met het juiste bewijs erbij winnen systemen 14–22 punten.

### 10.2 De kandidaten, op volgorde

1. **De verkeerde foto: meten op 5Pils-OOC, en een stap "waar komt deze foto vandaan" (het patroon van COVE).**
   - *Bron:* COVE, https://arxiv.org/html/2502.01194 (2025), code https://github.com/UKPLab/naacl2025-cove (Apache 2.0;
     de set 5Pils-OOC staat daar in `data/5pils_ooc`, CC-BY-SA 4.0); 5Pils, https://github.com/UKPLab/5pils (EMNLP 2024,
     code Apache 2.0, data CC-BY-SA 4.0).
   - *Cijfers op 5Pils-OOC (zelf nagelopen, tabel 2):* COVE met Llama 3 58,2; SNIFFER 56,3; AITR 52,6; RED-DOT 46,8. Op
     NewsCLIPpings: 86,7; 88,4; 93,5; 90,3. Mensenonderzoek (tabel 4): 85,6 met de herleide herkomst, 34,4 zonder.
   - *Wat wij doen:* geen model overnemen, wel de twee stappen in de vraag aan Sonnet. De repository levert de resultaten
     van omgekeerd zoeken al mee, dus een eerste meting kost niets aan zoeken.
   - *Eerste proef:* 100 paren door `/check`: hoe vaak wordt het verkeerde bijschrift groen, en daarna met de stap.
     Onder $5.
2. **Het oudste voorkomen van een foto, met datum.** Eén zoekopdracht van Google Vision vond in 66,2% een eerder gebruik
   (5Pils). TinEye kan sorteren op oudste eerst (prijs niet nagelopen); `htmldate` (Apache 2.0) leest de datum van een
   pagina (F 0,949 op 1.000 pagina's). Sluit aan op de voormeting van het oudste beeld (§218, #32.40). Omgekeerd zoeken
   met het beeld van een gebruiker in het aanvraagpad gaat verder dan B55: een besluit van de PO.
3. **Kring 1 met woorden én vectoren uit bge-m3** (SemEval-2025 taak 7, FactDebug,
   https://aclanthology.org/2025.semeval-1.284.pdf): 78,91 → 85,20 (zelfde taal), 65,9 → 67,02 (andere taal); daarna
   bge-reranker-v2-m3 85,90 en 67,2. Geen nieuw model; wel een herindex, dus een release (B22). De set MultiClaim is alleen
   voor onderzoek: niet om op te trainen voor het product.
4. **Elke zin van de uitleg nagaan tegen zijn bron.** MiniCheck-Flan-T5-Large (0,8B, MIT, Engels;
   https://huggingface.co/lytang/MiniCheck-Flan-T5-Large), HHEM-2.1-Open (0,1B, Apache 2.0), LettuceDetect op EuroBERT
   voor Spaans en Duits (MIT; https://huggingface.co/KRLabsOrg/lettucedect-610m-eurobert-es-v1). Bespoke-MiniCheck-7B valt
   af: CC BY-NC 4.0. Doel: een waarschuwing als een zin op één bron zonder band leunt (§9.4).
5. **De vorm van de uitleg** (gratis): detail boven een label (Chan e.a. 2017, meta-analyse, secundair); de truth sandwich
   voegt niets toe (Swire-Thompson e.a. 2025, N=1.046); lezers verkozen in Zhou e.a. 2025 LLM-uitleg om helderheid en
   neutrale toon; *onzeker* vraagt zorgvuldige woorden (DeVerna e.a. 2024). Kanttekening: het onderzoek van Costello e.a.
   (2024) over AI tegen complotdenken kreeg in juni 2026 een Expression of Concern van Science.
6. **Websites zonder band herkennen aan hun links** (Burdisso e.a., NAACL 2024): Spearman 0,80 met journalisten; de set van
   5.332 domeinen staat onder Apache 2.0 (https://huggingface.co/datasets/sergioburdisso/news_media_reliability), met een
   kolom `newsguard_score` voor een klein deel, zonder uitleg over de herkomst. Alleen om "zonder band" te signaleren,
   nooit om een band te geven.
7. **Eerlijker meten:** 17–29% van "verse" beweringen uit eind 2025 was al te beantwoorden met kennis van vóór de
   trainingsgrens; zonder die beweringen daalt de score tot 11 punten en wisselt de volgorde van modellen (He e.a.,
   ACM MM 2026, https://huggingface.co/papers/2607.23514). Bruikbaar voor de duels met Gemini.

### 10.3 Niet de moeite

- Bespoke-MiniCheck-7B (niet commercieel), TRUST-VL (13B, alleen onderzoek), SNIFFER (13B, 56,3% op echte gevallen),
  RED-DOT en AITR (getraind op kunstmatige data, 46,8–52,6% op echte gevallen), E2LVLM en EXCLAIM (geen code).
- MultiClaim, MultiClaimNet en VERITE: alleen voor onderzoek.
- NewsRECON (de datum en plaats van een foto voorspellen): alleen Engels, 3–5% juiste datum.
- Google Backstory (een tijdlijn van waar een foto verscheen): alleen voor testers, geen API.
- Een oordeel van een taalmodel over een website als band: LLM's zijn het onderling eens (ρ 0,79) maar matig met
  deskundigen (ρ 0,50) (Yang en Menczer, WebSci 2025).

### 10.4 Wat ontbreekt, ook bij anderen

- een open model dat een verkeerde foto bij een echte gebeurtenis betrouwbaar herkent;
- een methode of toets voor oud nieuws dat opnieuw gedeeld wordt (alleen hulpmiddelen: htmldate, de datum van TinEye,
  de Wayback Machine);
- een open model dat nagaat of een bron een zin draagt, in het Portugees;
- onderzoek dat de lengte van een AI-uitleg bij een factcheck gericht varieert.

*Niet nagelopen:* de prijs van TinEye; of EuroBERT Portugees kent (de modelkaart noemt "15 languages" zonder lijst); de
licentie van de gewichten van FactCG; de snelheid van elk model op de Mac; de cijfers van Hackenburg e.a. (Science 2025,
alleen samenvattingen); de beschrijving van de winnaar van SemEval-2025 taak 7.

## 11. Faceless YouTube: nepnieuws als verdienmodel (bureauonderzoek, 8 november 2026)

*Aanleiding:* de PO (2026-11-08), bij het artikel van Pointer: "contentmakers ... verdienen heel veel met
nepnieuwskanalen ... een misinformatienetwerk [kan] net zo goed in Nederland zitten als in Rusland"; "Kunnen wij een tool
zijn die YouTube zelf kan inzetten? Kunnen wij ... de screenshots die ze zetten, van tevoren al identificeren?"

### 11.1 Wat er bekend is

- **Pointer (KRO-NCRV), 5 november 2026** (Jerry Vermanen, Luke Thomas; gelezen):
  - minstens 56 dubieuze Nederlandse faceless kanalen met AI-video's: complotten, beschuldigingen zonder wederhoor, roddel
    over bekende Nederlanders, AI-presentatoren die onjuist nieuws voorlezen, misdaadkanalen met volledige namen, en
    dubieuze medische adviezen;
  - 66 miljoen keer bekeken, de reclame-opbrengst van de meeste kanalen naar schatting €290.000;
  - maar 11 van de 56 met het verplichte AI-label;
  - YouTube verwijderde er 11 en zette er 8 zonder advertentie-inkomsten;
  - de makers volgden een Nederlandse cursus, en het productiewerk gaat deels naar freelancers in lagelonenlanden.
  https://pointer.kro-ncrv.nl/youtube-verwijdert-misleidende-opruiende-nederlandse-kanalen
- **CBC met Radio-Canada Décrypteurs, mei 2026:**
  - 20 kanalen met ingehuurde acteurs die de afscheiding van Alberta aanprijzen, samen meer dan 40 miljoen views;
  - herleid tot Nederlanders en de cursus Faceless Education Community;
  - geen aanwijzing voor een staatscampagne;
  - YouTube verwijderde een deel onder zijn regels tegen spam, misleiding en oplichting.
  https://www.dutchnews.nl/2026/05/dutch-trio-behind-wave-of-fake-canadian-propaganda-videos-cbc/,
  https://nos.nl/l/2613360, het rapport *Slopaganda* van het Media Ecosystem Observatory:
  https://mediatechdemocracy.com/fr/publications/slopaganda-alberta-secession_2026/
- **Maldita, 31 juli 2026:**
  - minstens 1.046 YouTube-kanalen met door AI gemaakte "dokters": ruim 96.000 video's, ~1,84 miljard views, in 33 talen;
  - 45% verdient mee aan de advertenties, en 20 kanalen beloven kanker te genezen;
  - gemelde video's stonden 72 uur later nog online;
  - de thumbnails zijn sensationeler dan de video zelf.
  https://maldita.es/investigaciones/20260731/health-tips-artificial-intelligence-youtube/
- **Zuid-Korea (Korea Health Promotion Institute, 2026):** van de 100 meest bekeken video's over de gezondheid van ouderen
  gebruikten er 42 AI, en 24 deden zich voor als arts of deskundige. https://biz.heraldcorp.com/article/10779674
- **Polen en Taiwan** melden hetzelfde patroon: AI-dokters die zich op ouderen richten ("drink dit elke dag na je
  zestigste"), en ouderen die het AI-label niet zien.
- **YouTube zelf:**
  - de regel tegen *inauthentic content* (massaal gemaakt, herhalend) zet kanalen uit het partnerprogramma; in juli 2026
    verduidelijkt, en geen verbod op AI (https://www.tubefilter.com/2026/07/13/youtube-inauthentic-content-monetization-policy-update/);
  - de handhaving is deels automatisch;
  - Google trok zich in januari 2025 terug uit de factcheckafspraken van de Europese gedragscode, en voegt geen factchecks
    toe aan YouTube of de ranking; het wijst op notities van gebruikers (https://www.axios.com/2025/01/16/google-fact-check-eu).
- **Trusted flaggers onder de DSA:**
  - de nationale toezichthouder (in Nederland de ACM) wijst ze aan, en hun meldingen gaan voor;
  - de Commissie publiceerde op 29 mei 2026 concept-richtsnoeren;
  - daarnaast het vrijwillige Priority Flagger-programma van Google.
  https://digital-strategy.ec.europa.eu/en/library/draft-commission-guidelines-trusted-flaggers
- **Thumbnails herkennen kan:** ThumbnailTruth (2.843 video's uit acht landen) haalde met een groot taalmodel dat het
  beeld, de beschrijving en de ondertitels leest 93,8% juist (https://arxiv.org/abs/2509.04714). Het onderzoek waarschuwt
  dat *misleidend* per cultuur verschilt.

### 11.2 Wat het voor Factiz betekent

1. *Een thumbnail is een screenshot met een bewering.* "Kanker in zeep? Koop dit merk nooit meer!" met een merklogo is
   de bewering "dit merk veroorzaakt kanker". Dat is precies de route waarin Factiz het sterkst is: tekst in beeld lezen,
   de bewering zoeken, en een oordeel met bronnen (Engelse screenshots 54 van 58, §220). Een thumbnail en titel vooraf
   controleren kan met de bestaande machine; de video zelf (spraak) is versie 2.
2. *Herkomst en gedrag (B62) passen hier precies:*
   - dezelfde AI-presentator of hetzelfde sjabloon over veel kanalen;
   - geen AI-label terwijl het wel AI is;
   - een echt merk in een gezondheidsangst;
   - een kanaal dat jong is en veel uploadt.
   Het merk in beeld (signaal 2, §242) is hier anders dan gedacht: geen nagemaakt nieuwsmerk, maar een echt consumentenmerk
   dat zwartgemaakt wordt.
3. *YouTube als klant ligt niet voor de hand:* Google wil geen factchecks in YouTube (2025) en heeft eigen systemen.
   Wel mogelijk: Factiz als *trusted flagger* onder de DSA of in het Priority Flagger-programma. Factiz vindt en meldt
   met bronnen, YouTube beslist. Dat levert geen omzet van YouTube op, wel geloofwaardigheid en een plek voor fondsen.
4. *Wie wel betaalt of belang heeft* (voor de sparringronde, #32.60):
   - merken die in zulke thumbnails zwartgemaakt worden (merkbescherming);
   - adverteerders en hun brand-safety-diensten, want de advertenties betalen deze kanalen;
   - gezondheidsorganisaties en patiëntenverenigingen;
   - journalisten en factcheckers (Pointer en Maldita deden het met de hand; stap 2 van B65).
5. *Het publiek wapenen:*
   - de plug-in uit B23 die naast een thumbnail op YouTube een controle met bronnen laat zien;
   - uitleg die helpt, voor ouderen in gewone woorden;
   - samenwerken met ouderenbonden.
6. *Risico:* een kanaal onterecht aanwijzen is ernstig, dus alleen met bronnen, en per kanaal een signaal, geen oordeel
   (B62, DR2).

## 12. Claude Fable 5.2 en Mythos 5.2 (bureauonderzoek, 10 november 2026)

*Aanleiding (PO 2026-11-10): "Claude heeft een nieuw model uit en ik zou factiz wel eens willen testen tegen Fable 5.2,
ik verwacht eigenlijk dat we verliezen, maar denk ook dat we nieuwe mogelijkheden hebben om met dit model als de kern
totaal nieuwe factcheck mogelijkheden te bouwen". Gelezen op 2026-11-10, eerst de bronnen van Anthropic zelf. De
systeemkaart (een pdf van meer dan 10 MB) is niet gelezen.*

### 12.1 Wat vaststaat

- **Fable 5.2** (`claude-fable-5-2`) is uitgebracht op 9 november 2026 en staat open voor onze API-sleutel.
  - 1 miljoen woorddelen context, 128.000 uit. Tekst en beeld in, tekst uit; geen video.
  - Denken staat altijd aan; de standaard is effort `high`. Kennis tot juni 2026.
- **Prijs per miljoen woorddelen:** $8 in en $40 uit, en via de Batch API $4 en $20. Dat is 4× Sonnet 5.5 ($2 en $10)
  en 2× Opus 5.5. Zoeken op het web kost $10 per 1.000 zoekvragen; pagina's ophalen alleen de woorddelen.
- **Regels die Factiz raken:**
  - gedwongen gereedschap geeft een fout, dus ons vaste JSON-schema moet via `output_config` (dat doet de lezer al);
  - Fable 5.2 vraagt de bewaartermijn van 30 dagen en is er niet met zero data retention. Dat past bij B54;
  - zoeken met *dynamic filtering* is de standaard, en die is in het aanvraagpad verboden (B43). Dus daar
    `allowed_callers: ["direct"]`;
  - denken telt mee in `max_tokens`. Onze 1.000 voor de lezer is voor Fable waarschijnlijk te krap.
- **Wat Anthropic meet:** beter dan Fable 5.1 en Opus 5.5 op verzamelwerk met zoeken (WANDR 82,1% tegen 72,3% voor
  Opus 5.5), op Humanity's Last Exam met gereedschap (74,2% tegen 67,7%) en op grafieken lezen (73,4% tegen 64,4%).
  Over feitelijke juistheid, verzinnen of citeren publiceert Anthropic geen cijfers.
- **Een onafhankelijke meting van Fable 5.x of Opus 5.5 op factchecken is er niet.** NewsGuard en NPR testten
  "Claude" zonder modelversie. Artificial Analysis gaf Fable 5 (niet 5.2) 40 op zijn index voor kennis en verzinnen,
  vooral door meer goede antwoorden en niet door minder verzinsels.
- **Mythos 5.2** is hetzelfde model als Fable 5.2, met dezelfde prijs, maar zonder de extra remmen op cyber en
  biologie. Het is alleen er voor organisaties in de verificatieprogramma's voor cyberveiligheid en life sciences, of
  voor Enterprise in een besloten proef. Geen programma noemt factchecken of desinformatie, en verkiezingsbeïnvloeding is
  in het cyberprogramma juist verboden.
- **De gebruiksregels van Anthropic, vanaf 12 november 2026:** verboden zijn netwerken van nepmedia, en het
  manipuleren van de bronnen waaruit zoekmachines en AI hun antwoorden halen. Analyse en moderatie zijn toegestaan.
  Personen ontmaskeren uit anonieme activiteit is verboden. Dat telt als Factiz ooit van domeinen naar mensen gaat.

### 12.2 Wat het voor Factiz betekent

- **Mythos is voor ons niet nodig.** De remmen van Fable 5.2 gaan over cyber en biologie, niet over nieuws. Wel een
  terugvalmodel instellen voor het geval Fable onterecht weigert.
- **Fable 5.2 als lezer** kost per bericht ongeveer $0,19 in plaats van ~$0,05 (de rekensom van het onderzoek, niet
  gemeten). Fable als factchecker met eigen zoekwerk kost ~$0,40–0,90 per bericht. Dat is 10 tot 25 keer de ~$0,04 van
  nu.
- **Een derde laag** is daarom logischer dan een nieuwe kern: Fable alleen waar Brave en Sonnet eindigen op *niet
  bevestigd* of *onzeker*, of waar het beeld telt. Dit is een inferentie die nog gemeten moet worden.
- **Werk dat nu kan, offline en via de Batch API:**
  - netwerken van sites in kaart brengen, zoals Anthropic zelf doet in zijn dreigingsrapport;
  - lange bronpagina's lezen;
  - grafieken in screenshots lezen.

  Dat past bij de kaart van B23.
- **De test (PLAN #32.67)** moet laten zien:
  - of Fable alleen, met zoeken, Factiz verslaat;
  - of Factiz met Fable als lezer beter wordt dan met Sonnet;
  - wat dat kost.

**Bronnen:**
- platform.claude.com: docs/models/fable-5-2/overview, whats-new-fable-5-2, about-claude/pricing,
  agents-and-tools/tool-use/web-search-tool en web-fetch-tool, build-with-claude/vision, refusals-and-fallback,
  models/mythos-5-2/overview;
- anthropic.com: claude-fable-and-mythos-5-2, aup (versie vanaf 12 november 2026), threat-intelligence-report-september-2026
  (deels gelezen);
- support.claude.com/en/articles/14604842 (het programma voor cyberveiligheid);
- artificialanalysis.ai/articles/claude-fable-5-mythos-intelligence-index;
- newsguardtech.com/ai-monitor/may-2026;
- wlrn.org (NPR over NewsGuard, 30 augustus 2026; secundair);
- CNBC, 9 november 2026.

## Bijhouden

- Nieuwe audits en benchmarks komen in §2 en §6, met datum en bron.
- Wat een besluit raakt, gaat als voorstel naar de PO (REQUIREMENTS) en als
  taak naar PLAN.
- Wat we zelf meten, staat in BENCHMARK, niet hier.
