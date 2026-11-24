# Kennisbank: feiten over online factchecken, voor blogs

*Begonnen op 2026-11-07, op verzoek van de PO: "laten we een eigen kennisbank aanleggen die we later kunnen gebruiken voor
blogs over online factchecking". Eigenaar: PO.*

**Wat erin komt:** feiten en cijfers die een blog kan dragen, elk met de bron, de datum en hoe zeker we zijn. Dit is geen
onderzoeksverslag; het onderzoek zelf en de achtergrond staan in `docs/RESEARCH.md` en onze metingen in
`docs/BENCHMARK.md`.

**De regels:**
- Alleen uit een bron die wij zelf geopend hebben, of uit een eigen meting. Wat alleen uit een samenvatting of uit tweede
  hand komt, staat erbij als *samenvatting* of *secundair* en gaat niet ongecontroleerd in een blog.
- Het getal zoals de bron het geeft, met waar het op gemeten is. Geen afronding die het mooier maakt.
- Geen lange citaten: hoogstens een korte zin tussen aanhalingstekens, met de naam van de bron.
- Eigen metingen van Factiz gaan pas naar buiten als de PO dat zegt.
- Nieuw item: een volgend nummer, nooit een oud nummer hergebruiken. Wat achterhaald is, krijgt *vervangen door Kn*.

**Een item:** het feit in gewone woorden · de bron met datum en adres · *nagelezen:* ja, samenvatting of secundair ·
*voor een blog over:* de invalshoek · *waar:* de plek in RESEARCH of BENCHMARK.

---

## 1. Chatbots en nepnieuws

- **K1. Chatbots herhalen valse claims vaker sinds ze zoeken.** In augustus 2024 herhaalden chatbots in de test van
  NewsGuard 18% van de valse claims en weigerden ze 31%; in augustus 2025 was dat 35% en 0%. · NewsGuard, AI False Claims
  Monitor, 2024–2025, https://www.newsguardtech.com/press/ai-multilingual-failure-russian-chinese · *nagelezen:* in RESEARCH zonder aantekening dat de bron zelf geopend is; vóór een blog openen ·
  *voor een blog over:* waarom zoeken een chatbot niet vanzelf betrouwbaarder maakt · *waar:* RESEARCH §6.2.
- **K2. Bijna de helft van de AI-antwoorden over nieuws heeft een ernstig probleem.** 22 publieke omroepen (ook NOS/NPO en
  VRT) in 14 talen: 45% van 2.709 antwoorden had een ernstig probleem, 31% een probleem met de bron; bij Gemini 76%. ·
  EBU/BBC, News Integrity in AI Assistants, oktober 2025,
  https://www.ebu.ch/research/open/report/news-integrity-in-ai-assistants · *nagelezen:* in RESEARCH zonder aantekening dat de bron zelf geopend is; vóór een blog openen · *voor een blog over:* AI als
  nieuwsbron · *waar:* RESEARCH §6.2.
- **K3. AI-zoekmachines geven vaak de verkeerde bron.** In meer dan 60% van 1.600 tests (Perplexity 37%, Grok-3 94%). ·
  Tow Center, maart 2025,
  https://www.cjr.org/tow_center/we-compared-eight-ai-search-engines-theyre-all-bad-at-citing-news.php · *nagelezen:* ja ·
  *voor een blog over:* bronvermelding nalopen · *waar:* RESEARCH §3.2, §9.
- **K4. Te stellig.** ChatGPT Search toonde twijfel in 15 van de 200 antwoorden en weigerde nooit. · Tow Center, maart 2025
  (zie K3) · *nagelezen:* ja · *voor een blog over:* waarom "ik weet het niet" een goed antwoord is · *waar:* RESEARCH §9.3.
- **K5. Eén pagina van een aanvaller is genoeg.** Bij chatbots die zoeken kwam de inhoud van één pagina van een aanvaller
  in 31% van de antwoorden terecht, en maar in ongeveer een kwart daarvan met een waarschuwing. · Guerra e.a., Data-Void
  Exploits in Web-Searching LLMs, oktober 2026, https://arxiv.org/abs/2610.30365 · *nagelezen:* samenvatting (het cijfer van
  de waarschuwing secundair) · *voor een blog over:* datalacunes en hoe nepnieuws in AI-antwoorden komt · *waar:* RESEARCH
  §9.3.
- **K6. Kremlinbronnen in chatbots: vooral datalacunes.** 5% van de antwoorden herhaalde Kremlindesinformatie, en
  verwijzingen naar Kremlinsites kwamen vooral bij vragen naar details waar gewone media niets over schreven. · Alyukov
  e.a., HKS Misinformation Review, 15 oktober 2025,
  https://misinforeview.hks.harvard.edu/article/llms-grooming-or-data-voids-llm-powered-chatbot-references-to-kremlin-disinformation-reflect-information-gaps-not-manipulation
  · *nagelezen:* ja · *voor een blog over:* "LLM grooming" of gewoon gaten in het nieuws? · *waar:* RESEARCH §6.2, §9.3.
- **K7. Een juiste AI-factcheck helpt niet vanzelf.** Een model dat 90% van de valse koppen goed aanwees, hielp mensen niet
  beter waar van onwaar te onderscheiden; twijfelde het model bij een valse kop, dan geloofden mensen die kop méér. Checks
  van mensen hielpen wel. · DeVerna e.a., PNAS, december 2024, https://arxiv.org/abs/2308.10800 · *nagelezen:* samenvatting
  · *voor een blog over:* juist is niet hetzelfde als nuttig · *waar:* RESEARCH §9.1.
- **K8. Geen enkel groot AI-bedrijf heeft een algemeen filter tegen nepnieuws.** Meta's Llama Guard heeft alleen een
  categorie voor onjuiste informatie over hoe stemmen werkt; de rest is training op eerlijkheid en zoeken met bronnen. ·
  Meta, Llama Guard 3, 2024, https://dev.meta.ai/llama/docs/model-cards-and-prompt-formats/llama-guard-3/ · *nagelezen:* ja
  · *voor een blog over:* hoe AI-bedrijven nepnieuws aanpakken · *waar:* RESEARCH §9.2.
- **K9. Grok werd pas goed met een Community Note.** Bij een met AI gemaakte video van een vliegveld zei Grok 31% van de
  keren dat het Tel Aviv was, tot er een Community Note kwam. · DFRLab, 24 juni 2025,
  https://dfrlab.org/2025/06/24/grok-struggles-with-fact-checking-amid-israel-iran-war/ · *nagelezen:* ja · *voor een blog
  over:* waarom het werk van mensen voorop moet · *waar:* RESEARCH §9.2.

## 2. Talen

- **K10. Kiezersvragen: Spaans slechter dan Engels.** Zes chatbots met webzoeken, 2.400 antwoorden: 71% volledig juist in
  het Engels, 55% in het Spaans; het verschil kwam vooral door weglaten, niet door gebrek aan kennis. · ISD, Chatbots and
  the Ballot Box, september 2026,
  https://www.isdglobal.org/wp-content/uploads/2026/09/Chatbots-and-the-Ballot-Box-US-elections.pdf · *nagelezen:* ja ·
  *voor een blog over:* het taalgat · *waar:* RESEARCH §6.1.
- **K11. Hoe verder van het Engels, hoe meer fouten.** Valse claims herhaald: Russisch 55%, Chinees 51%, Spaans 48%, Duits
  43%, Engels 43%, Italiaans 39%, Frans 34%. · NewsGuard, februari 2025 (zie K1) · *nagelezen:* in RESEARCH zonder aantekening dat de bron zelf geopend is; vóór een blog openen · *voor een blog over:*
  het taalgat · *waar:* RESEARCH §6.2.
- **K12. Copilot weigerde verkiezingsvragen in het Engels veel vaker dan in het Nederlands** (90% tegen 28%). · AI
  Forensics, juli 2024, https://aiforensics.org/work/chatbots-moderation · *nagelezen:* in RESEARCH zonder aantekening dat de bron zelf geopend is; vóór een blog openen · *voor een blog over:* AI en de
  Nederlandse verkiezingen · *waar:* RESEARCH §6.2.

## 3. Beelden

- **K13. AI herkent de herkomst van nieuwsfoto's slecht.** Van 280 vragen over echte nieuwsfoto's waren er 14 helemaal goed
  (plaats, datum en fotograaf), en elk model noemde minstens één echte foto door AI gemaakt. · Tow Center, 26 augustus 2025,
  https://www.cjr.org/tow_center/why-ai-models-are-bad-at-verifying-photos.php · *nagelezen:* ja · *voor een blog over:* een
  echte foto bij het verkeerde verhaal · *waar:* RESEARCH §9.3.
- **K14. AI-hulpmiddelen herkennen hun eigen nepbeelden niet.** Gemini en Copilot noemden een nepfoto van een protest,
  gemaakt met Gemini, echt. · AFP via RNZ, 21 november 2025,
  https://www.rnz.co.nz/news/business/579586/ai-s-blind-spot-tools-fail-to-detect-their-own-fakes · *nagelezen:* ja · *voor
  een blog over:* waarom een AI-detector geen oplossing is · *waar:* RESEARCH §9.3.
- **K15. Elk model scoort onder de 70% op feitelijkheid, en het slechtst bij beelden.** · Google DeepMind, FACTS Benchmark
  Suite, 9 december 2025,
  https://deepmind.google/blog/facts-benchmark-suite-systematically-evaluating-the-factuality-of-large-language-models/ ·
  *nagelezen:* ja · *voor een blog over:* beelden als zwakste plek · *waar:* RESEARCH §9.2.

## 4. Staatsinvloed en propaganda

- **K16. DeepSeek herhaalt verhalen van de Chinese Communistische Partij, vaker in het Chinees.** DeepSeek V3.1: 5% in het
  Engels en 12% in het Chinees, tegen 2–3% bij Amerikaanse modellen; het zit in de gewichten van het model zelf. · NIST
  CAISI, 30 september 2025, https://www.nist.gov/document/caisi-evaluation-deepseek-ai-models-report · *nagelezen:* ja ·
  *voor een blog over:* hoe staatsinvloed in een taalmodel te meten is (PLAN #32.50) · *waar:* RESEARCH §9.2.
- **K17. Het Pravda-netwerk publiceerde 3,6 miljoen artikelen in 2024**, en chatbots herhaalden in 33% van de tests een
  verhaal van het netwerk. · NewsGuard, maart 2025 · *nagelezen:* in RESEARCH zonder aantekening dat de bron zelf geopend is; vóór een blog openen · *voor een blog over:* propaganda
  die op AI mikt · *waar:* RESEARCH §6.2. Zet het naast K6.
- **K18. Weigeren hangt af van het land.** Modellen weigerden kritiek op restrictieve landen vaker (34%) dan op vrijere
  landen (14%). · Oversight Board, juli 2026 · *nagelezen:* in RESEARCH zonder aantekening dat de bron zelf geopend is; vóór een blog openen · *voor een blog over:* wat een model niet wil zeggen ·
  *waar:* RESEARCH §6.2.
- **K31. Bij de rellen in Frankrijk (oktober 2026) deed een Russisch netwerk zich voor als westerse media.** De Russische
  operatie Overload verspreidde video's die deden alsof ze van westerse media kwamen. Ze beweerden ten onrechte dat migranten
  demonstranten hadden verkracht of dat er aanslagen op komst waren. Het netwerk heeft de rellen volgens het rapport niet
  veroorzaakt, maar wel uitgebuit. De periode is 7–21 oktober 2026. Het rapport is intern en komt van desinformatiespecialisten
  van de diplomatieke dienst van de EU, de EEAS. In een tweede, Frans intern rapport over 16–18 oktober haalden de 10 meest
  bekeken posts op X 2,8 miljoen weergaven (pro-Russisch), meer dan 49 miljoen (MAGA) en meer dan 35 miljoen (aan Israël
  gelinkt). · Reuters, 9 november 2026, https://www.internazionale.it/ultime-notizie-reuters/2026/11/09/exclusive-covert-russian-network-exploited-french-riots-on-social-media-eu-report-says ·
  *nagelezen:* ja, het Reuters-bericht. Reuters zegt zelf dat het de rapporten niet onafhankelijk kon controleren · *voor
  een blog over:* nagemaakte merken van media, en waarom een logo niets bewijst (B62) · *waar:* nog niet in RESEARCH.

## 5. Factcheckers en het aanbod

- **K19. Er komen minder factcheckers.** 437 actieve projecten, netto 23 minder in 2025. · Duke Reporters' Lab, telling
  2026, 12 juni 2026, https://reporterslab.org/?p=4294 · *nagelezen:* ja · *voor een blog over:* wie checkt er nog, en wat
  betekent dat voor AI · *waar:* RESEARCH §9.1.
- **K20. Met de checks erbij wordt een taalmodel veel beter.** GPT-4o op meer dan 6.000 claims van PolitiFact: macro-F1
  0,26 zonder zoeken, 0,76 met webzoeken en 0,90 met de checks van PolitiFact erbij. · DeVerna e.a., november 2025,
  https://arxiv.org/abs/2511.18749 · *nagelezen:* in RESEARCH zonder aantekening dat de bron zelf geopend is; vóór een blog openen · *voor een blog over:* waarom het werk van factcheckers de ruggengraat
  blijft · *waar:* RESEARCH §2.3.
- **K27. Frankrijk heeft de meeste factcheckers van Europa, Scandinavië de minste.** Actieve projecten per land: Frankrijk
  16, Verenigd Koninkrijk 9, Spanje en Duitsland 8, België en Polen 6, Nederland 3, Zweden 4, Noorwegen en Denemarken elk
  1. · Duke Reporters' Lab, kaart van factcheckers, gelezen 3 november 2026, https://reporterslab.org/fact-checking/ ·
  *nagelezen:* de kaartdata zelf opgehaald (`data/bronnen/extern/duke/`), de telling door ons; telt projecten, niet hun
  output · *voor een blog over:* waar in Europa wordt nepnieuws gecheckt, en waar niet · *waar:* BENCHMARK §244.
- **K28. Nederlandse faceless YouTube-kanalen verdienen aan nepnieuws.** Minstens 56 kanalen, 66 miljoen views, naar
  schatting €290.000 reclame-opbrengst; maar 11 met het verplichte AI-label; YouTube verwijderde er 11. · Pointer
  (KRO-NCRV), 5 november 2026, https://pointer.kro-ncrv.nl/youtube-verwijdert-misleidende-opruiende-nederlandse-kanalen ·
  *nagelezen:* ja · *voor een blog over:* nepnieuws als verdienmodel, ook vanuit Nederland · *waar:* RESEARCH §11.1.
- **K29. Meer dan 1.000 AI-dokters op YouTube, in 33 talen.** Ruim 96.000 video's en ~1,84 miljard views; 45% verdient
  mee aan advertenties. · Maldita, 31 juli 2026,
  https://maldita.es/investigaciones/20260731/health-tips-artificial-intelligence-youtube/ · *nagelezen:* nee, vóór een
  blog openen · *voor een blog over:* waarom ouderen het doelwit zijn · *waar:* RESEARCH §11.1.
- **K30. Nederlanders achter Canadese nepvideo's over de afscheiding van Alberta.** 20 kanalen, meer dan 40 miljoen
  views, herleid tot een Nederlandse cursus voor faceless kanalen; geen staatscampagne. · CBC en Radio-Canada, mei 2026, via
  https://www.dutchnews.nl/2026/05/dutch-trio-behind-wave-of-fake-canadian-propaganda-videos-cbc/ · *nagelezen:* nee,
  vóór een blog openen · *voor een blog over:* een desinformatienetwerk zit niet altijd in Rusland · *waar:* RESEARCH §11.1.
- **K34. Google toont factchecks niet meer apart in de zoekresultaten.** Sinds juni 2025 bouwt Google de steun voor zeven
  soorten gestructureerde gegevens af, waaronder ClaimReview, de opmaak waarmee factcheckers hun oordeel aan Google
  doorgaven; volgens Google verandert dat niets aan de rangorde. · Google Search Central Blog, *Simplifying the search
  results page*, 12 juni 2025, https://developers.google.com/search/blog/2025/06/simplifying-search-results ·
  *nagelezen:* ja, 12 november 2026 · *voor een blog over:* waarom een factcheck moeilijker te vinden is geworden, en wat
  een archief daaraan kan doen · *waar:* DESIGNSYSTEEM §6.
- **K36. Er is geen database van alle factchecks ter wereld.** De Duke Reporters' Lab houdt een lijst van factcheckers bij
  en maakte Fact-Check Insights, een doorzoekbare verzameling ClaimReview van meer dan 180.000 beweringen (stand van
  december 2023); de IFCN houdt een lijst van organisaties, geen database. · Duke Reporters' Lab, *Duke lab gives
  fact-checkers, researchers new tools to thwart misinformation*, 15 december 2023,
  https://reporterslab.org/2023/12/15/duke-lab-gives-fact-checkers-researchers-new-tools-to-thwart-misinformation/ ·
  *nagelezen:* nee, alleen via de zoekresultaten (20 november 2026); het getal is van 2023, vóór een blog opnieuw nagaan ·
  *voor een blog over:* waar je kunt opzoeken of iets al gecheckt is · *waar:* docs/voorstellen/2026-11-20-seo-geo.md.

- **K37. Snopes en PolitiFact checken zelden hetzelfde, maar zijn het dan bijna altijd eens.** Van 11.639 checks van
  Snopes hadden er 749 (6,4%) een tegenhanger bij PolitiFact (2016 tot augustus 2022). Daarvan had 69,6% precies hetzelfde
  oordeel en 74,2% dezelfde richting (waar of niet waar). Na correctie voor verschillen in de schaal, het accent, een detail
  in de bewering en het moment van checken bleef één geval over waarin ze elkaar echt tegenspraken. · Lee, Xiong, Seo en
  Lee, *"Fact-checking" fact checkers: A data-driven approach*, HKS Misinformation Review, 26 oktober 2023,
  https://misinforeview.hks.harvard.edu/article/fact-checking-fact-checkers-a-data-driven-approach/ (CC BY); de gegevens
  onder CC0 op https://doi.org/10.7910/DVN/FXYZDT · *nagelezen:* ja, 22 november 2026 · *voor een blog over:* waarom het
  helpt als meer redacties hetzelfde checken, en wat Factiz daarover over 256 redacties kan zeggen (K42).
- **K38. Bij twijfelgevallen zijn factcheckers het veel minder eens.** PolitiFact en The Washington Post Fact Checker
  maakten van september 2013 tot de verkiezingen van 2016 samen 1.503 checks van uitspraken van presidentskandidaten;
  77 uitspraken checkten ze allebei (6,5% van PolitiFact, 23,7% van Fact Checker). Ze gaven 49 van die 77 hetzelfde oordeel, nooit het ene
  uiterste tegenover het andere, maar bij "Half True" en "Mostly False" maar 14 van 23. Het verschil zat meestal niet in
  de feiten maar in hoe zwaar een redactie een onjuistheid weegt. · Chloe Lim, *Checking how fact-checkers check*,
  Research & Politics 5 (3), 19 juli 2018, https://doi.org/10.1177/2053168018786848 (CC BY-NC) · *nagelezen:* ja,
  22 november 2026 · *voor een blog over:* waarom een oordeel als "misleidend" minder hard is dan "onwaar".

## 7. Wat onderzoek zegt over beelden en uitleg

- **K23. Een echte foto bij het verkeerde verhaal herkent AI nauwelijks.** Open systemen die op een kunstmatige toets 87–93%
  halen, halen op 624 echte gevallen 47–58%, weinig beter dan een munt. · COVE (UKPLab, TU Darmstadt), NAACL 2025,
  https://arxiv.org/html/2502.01194, tabel 2 · *nagelezen:* ja (7 november 2026) · *voor een blog over:* waarom de oude
  foto bij nieuw nieuws het lastigste nepnieuws is · *waar:* RESEARCH §10.
- **K24. Laat zien waar een foto vandaan komt, en mensen zien het zelf.** Met de herleide herkomst van een foto had 85,6%
  het goed, zonder 34,4%. · COVE, tabel 4 (zie K23) · *nagelezen:* ja · *voor een blog over:* context geven werkt beter dan
  een oordeel · *waar:* RESEARCH §10.
- **K25. De "truth sandwich" voegt niets toe aan een gewone, gedetailleerde correctie.** Voorgeregistreerd, 1.046 mensen,
  ook na twee weken. · Swire-Thompson e.a., 2025, https://ifp.nyu.edu/2025/journal-article-abstracts/edu0000961/ ·
  *nagelezen:* samenvatting · *voor een blog over:* hoe je een factcheck schrijft · *waar:* RESEARCH §10.
- **K35. Het label 'door AI gemaakt' kost vertrouwen, omdat mensen aannemen dat er geen mens meekeek.** In twee
  voorgeregistreerde proeven met 4.976 mensen in de VS en het VK vonden ze koppen met dat label minder juist en deelden
  ze die minder, ook als de kop waar was of door een mens geschreven; het effect was een derde van dat van het label
  'onwaar'. · Altay en Gilardi, PNAS Nexus 3 (10), 2024, https://pmc.ncbi.nlm.nih.gov/articles/PMC11443540 ·
  *nagelezen:* samenvatting (19 november 2026, via de zoekresultaten en het persbericht; het artikel zelf vóór een blog
  openen) · *voor een blog over:* waarom Factiz Radar zegt 'gecheckt met AI, nagelezen door de redactie' en niet
  'geautomatiseerd' · *waar:* DESIGN §4x.

- **K40. Een andere verklaring werkt beter dan alleen zeggen dat het niet klopt.** Een meta-analyse van 65 studies:
  correcties hebben gemiddeld een matig effect (r = .35), bij politiek (r = .15) en bij echte, rondgaande desinformatie
  (r = .14) veel minder dan bij gezondheid of in het lab. Een weerlegging achteraf (r = .38) werkt beter dan een
  waarschuwing vooraf (r = .16), en een uitleg met een andere, samenhangende verklaring (r = .55) beter dan een kale
  factcheck (r = .25) of een beroep op de betrouwbaarheid van de bron (r = .14). · Walter en Murphy, *How to unring the
  bell*, Communication Monographs 85 (3), 2018, https://doi.org/10.1080/03637751.2018.1467564 · *nagelezen:* de samenvatting
  op de pagina van de uitgever, 22 november 2026 · *voor een blog over:* waarom een check van Factiz Radar zegt wat er echt
  gebeurde, niet alleen dat het niet klopt.
- **K41. Een check na het zien werkt beter dan een waarschuwing vooraf.** In twee proeven met 2.683 mensen die ware en
  valse koppen van sociale media lazen, hielp een label "waar" of "onwaar" ná het lezen een week later beter om waar van
  onwaar te scheiden dan hetzelfde label tijdens of vóór het lezen. · Brashier, Pennycook, Berinsky en Rand, *Timing
  matters when correcting fake news*, PNAS 118 (5), 2021, https://doi.org/10.1073/pnas.2020043118 · *nagelezen:* de
  samenvatting op de pagina van PNAS, 22 november 2026 · *voor een blog over:* waarom het zin heeft om iets na te checken
  dat je al zag ("Where the world comes to double-check").

## 8. Hoe nepnieuws zich verspreidt

- **K39. Onwaar gaat verder, sneller en dieper dan waar, en dat komt door mensen, niet door bots.** Alle door
  factcheckers beoordeelde verhalen op Twitter van 2006 tot 2017: ongeveer 126.000 verhalen, ruim 4,5 miljoen keer
  getweet door ongeveer 3 miljoen mensen. De 1% grootste onware verhalen bereikten 1.000 tot 100.000 mensen, ware zelden
  meer dan 1.000; het sterkst bij politiek. Bots verspreidden waar en onwaar even snel. De zes factcheckers waarop ze
  bouwden, waren het in 95 tot 98% eens. · Vosoughi, Roy en Aral, *The spread of true and false news online*, Science 359,
  9 maart 2018, https://doi.org/10.1126/science.aap9559 · *nagelezen:* de samenvatting op de pagina van Science,
  22 november 2026; het vaak genoemde "70% vaker gedeeld" staat alleen in het persbericht van MIT (secundair) ·
  *voor een blog over:* de leugen is snel.

## 6. Eigen metingen van Factiz (alleen naar buiten met de PO)

- **K21. Factiz tegen Gemini, eerste duel.** 50 Engelse berichten (25 vers nieuws, 25 bekende nepberichten), blind
  beoordeeld door de PO: juist Factiz 48, Gemini 45; geen van beide gaf groen bij nep of rood bij waar; het meest geholpen
  werd de lezer door Gemini (45 tegen 4), omdat Factiz kortaf was. · BENCHMARK §235, 7 november 2026 · *voor een blog over:*
  wat een factcheck nuttig maakt.
- **K22. Na een betere uitleg bijna gelijk.** Met drie tot vijf feitelijke zinnen in plaats van één: het meest geholpen
  Factiz 20, Gemini 21, 9 gelijk. · BENCHMARK §236, 7 november 2026 · *voor een blog over:* de uitleg is het product.
- **K26. Een nieuwsoverzicht is geen rechter.** Het dagelijkse nieuwsoverzicht van Wikipedia bevestigde 26 van 175 echte
  berichten (alleen groot nieuws), bevestigde bij twee nepvideo's de echte gebeurtenis erachter, en wees 12 keer onterecht
  een tegenspraak aan. · BENCHMARK §237, 7 november 2026 · *voor een blog over:* waarom consensus over een gebeurtenis
  niets zegt over een beeld.
- **K32. Een model ziet zijn eigen leesfout niet.** Van 400 nagelezen machinevertalingen van beweringen (naar het
  Nederlands, Duits, Spaans en Frans, uit 31 talen) hadden er 6 een betekenisfout. Vier daarvan waren leesfouten van het
  origineel en stonden in alle vier de talen tegelijk. Een controle door hetzelfde model meldde 1 van de 6, met een
  tweede lezing ernaast 2; een sterker model meldde alle 6 en keurde in totaal 4% van alle vertalingen af. · PLAN #33.5
  stap 4, eigen leesproef door Claude, 11 november 2026; zes fouten is weinig · *voor een blog over:* waarom een
  vertaling naast het origineel hoort te staan.
- **K33. Wat op Bluesky het meest gedeeld wordt, is zelden nepnieuws en zelden een nieuwsfoto.** Van de 300 meest gedeelde
  posts met een beeld in een etmaal (Nederlands, Spaans en een tiende van het Engels; 10 en 11 november 2026) was 34%
  kunst of een eigen foto, 24% een meme of strip en 11% een nieuwsfoto. Van de 50 meest gedeelde met een bewering over
  het nieuws waren er 3 onwaar of misleidend, en twee daarvan waren oud: een verzonnen citaat dat factcheckers maanden
  eerder weerlegden, en een plaatje uit 2025 dat als nieuws werd gedeeld. · BENCHMARK §259, eigen meting, labels van
  Claude; één etmaal op één platform, drie gevallen · *voor een blog over:* nepnieuws is vaak oud nieuws.

- **K42. Over taalgrenzen heen zijn redacties het bijna altijd eens.** In uitgave 2026-11-21c zijn er 2.109 paren
  *Ook gecheckt door* (dezelfde bewering bij twee redacties, gekozen zonder naar het oordeel te kijken, 69% in twee
  verschillende talen): 80,3% hetzelfde oordeel, 94,2% dezelfde richting, en 5 keer waar tegenover niet waar. Binnen een
  pagina die het lab samenvoegde (843 paren, 87 redacties): 76,6% hetzelfde oordeel, 86,6% dezelfde richting, 1 keer
  recht tegen elkaar in. Alle zes vallen in de soorten van K37: een andere schaal, een ander accent, een detail dat
  verschilt, of een ander moment. · Eigen meting, 22 november 2026, op de publicatiedatabase, zonder nieuwe vragen ($0);
  de oordelen zoals `verdicts.py` ze indeelt; het samenvoegen binnen een pagina scheidt beweringen met een andere strekking,
  dus dat cijfer valt eerder te hoog uit · *voor een blog over:* een wereldwijde versie van K37, in 50 talen.

---

## Bijhouden

- Nieuw onderzoek in RESEARCH met een citeerbaar feit: hier een item bij, met een verwijzing naar de plek in RESEARCH.
- Bij elk item dat in een blog komt: de bron nog één keer openen op de dag van publicatie.
