# VOICE — Factiz

> Status: **APPROVED** (PO 2026-10-13; geoogst uit de repo 2026-10-04, gekalibreerd met de PO 2026-10-13)
> Merk: Factiz (factiz.org) · codebase: doublecheck · voertaal publiek: Engels (PO 2026-10-04), NL-edities voor de Nederlandstalige ring

> **Sinds B74 (PO 2026-11-10):** het platform staat in vijf talen (Nederlands, Engels, Duits, Spaans, Frans), alle
> vijf open. De regels van dit document gelden per taal; de Engelse tekst is de bron, de andere talen volgen haar. Een
> vaste tekst die nog geen moedertaallezer zag, draagt dat als kenmerk in het bestand. De oude site en
> try.factiz.org blijven Engels.

## 1. Context

Open-source resolver-laag voor factchecks: het collectieve geheugen van de
factcheckers. Toont wie een bewering eerder controleerde en wat eruit kwam,
met de bron erbij. Oordeelt zelf nooit. Publiek: journalisten,
factcheckredacties, en later AI-teams; eerst NL/BE, meertalig van aard.
Afzender is een gebootstrapt project van één maker, geen bedrijf met een
marketingafdeling, en zo mag het klinken.

**Pay-off (B86, PO 2026-11-21):** "For a world that can't be fooled." Op elke
pagina onder het logo, in elke taal in het Engels ("Ja, overal Engels"): een merk
herken je alleen als het overal gelijk is. Nooit vertaald. Voor campagnes en social mag de tactische zin "Where the world
comes to double-check." De pay-off mag groot zijn; de checks zelf blijven nuchter.

*Daarvoor (B27, PO 2026-10-13):* "No lie should have to be debunked twice." en
"The internet's memory for fact-checks." Factiz is een geheugen, geen detector;
"lie detector" en "a world without fake news" zijn afgewezen (REQUIREMENTS B27).
Wat blijft: de pay-off belooft niet dat leugens verdwijnen, wel dat mensen er
niet meer in trappen.

## 2. Schrijffuncties

Uitleggen wat er gevonden is; nooit overtuigen dat iets waar is. De tekst
doet wat het product doet: tellen, tonen, doorverwijzen.

## 3. Toon

Als een laboratoriumuitslag (DESIGN §4): hier is wat gevonden is, oordeel
zelf. Nuchter, civiel, verzorgd zonder gemarket te zijn. Rust boven urgentie:
geen uitroeptekens, geen alarmtaal, geen waarschuwingsdriehoeken in woorden.
Zelfbewust over eerlijkheid: missers worden genoemd vóór iemand ernaar
vraagt. Eerder notaris dan campagneleider.

**De draaiknoppen per kanaal** *(kalibratie PO 2026-10-13)*:

- **Koppen op de site: niveau 0.** De kop zegt wat het doet, met het getal
  erin ("Search 110,579 fact-checks in 47 languages"). Geen verhaal en geen
  standpunt in de kop; dat mag in de tekst eronder.
- **Afzender: "we", het project.** Niet de maker in de ik-vorm, ook niet op
  de over-pagina. De maker mag bestaan (een citaat in een persbericht), maar
  de site spreekt als register.
- **Social mag naar niveau 2.** Een scène, een draai en één scherpe slotzin
  ("Our error rate is public. So are our misses."). Het verhaal van een
  claim die terugkomt is daar het vertrekpunt.
- **Missers in meetcijfers.** Het exacte cijfer met de meetopzet ("Coverage
  81.2%, error upper bound 0.25%, measured on 4,728 test pairs in 21
  languages"), niet afgerond tot een verhouding als "4 op de 5". Een
  verhouding verzacht; een cijfer met zijn opzet is na te rekenen.

## 4. Voorbeelden van goed (uit eigen productie)

- "De bronnen zijn het oordeel."
- "9.927 — geteld, niet verstopt."
- "Dekking 64,8%, en dat zeggen we hardop."
- "Dat betekent niet dat de bewering waar of onwaar is — alleen dat er nog
  geen factcheck van gevonden is."
- "Twijfel versoepelt nooit."

*Uit de kalibratie van 2026-10-13. Meer zoals dit:*

- Kop: "Search 110,579 fact-checks in 47 languages" / "Paste a claim or drop
  a screenshot. Factiz shows which newsrooms checked it and links to their
  article."
- Over-pagina: "Nobody did anything wrong. The checks just could not find
  each other." / "We never decide what is true. We show who checked, when,
  and what they found, and we publish our own misses."
- Social: "Nobody was wrong. They just couldn't see each other's work." /
  "We don't judge claims. We show you who already did." / "Our error rate is
  public. So are our misses."
- Missers: "Coverage 81.2%, error upper bound 0.25%, measured on 4,728 test
  pairs in 21 languages. Both are live on the numbers page."

*Minder zoals dit (niet gekozen):* een kop met verhaal ("A lie debunked in
2020 came back in 2024. So did the debunk.") of met een vraag aan de lezer
("See who already checked this claim"); de maker in de ik-vorm ("that
bothered me. So I built..."); "about 4 in 5 claims".

## 5. Input

Cijfers alleen uit de cijferbijlage, het dashboard of BENCHMARK.md; nooit
een getal uit het hoofd. Bij ontbrekend feit: [FEIT NODIG], nooit invullen.

## 6. Output

NL-getalsnotatie (80.902; 0,68%). "We", niet "wij" waar het kan. Factcheckers
heten redacties of factcheckers, nooit "waarheidsstrijders". Geen
waarheidspercentage over een bewering, ooit (DR2); percentages alleen over
eigen systeemprecisie en dekking.

## 7. Regels

Verboden: strijd/wapen/jacht-metaforen, "nepnieuws bestrijden" als frame,
revolutionair/innovatief/toonaangevend/baanbrekend, AI-hype, "verheugd aan
te kondigen", em-dashes, uitroeptekens. Concederen mag en moet: dekking is
64,8%, recall is geen belofte, en dat staat er gewoon.

### Woorden in de interface (PO 2026-11-17: "is het niet 'latest' ipv newest?", "Check even de gebruikelijke 'interface taal' overal")

De interface volgt de woorden die mensen van andere sites kennen; de merkstem zit in de zinnen, niet in de knoppen.

| waar | Engels | Nederlands | niet |
|---|---|---|---|
| sorteren | Newest first, Oldest first, Best match | Nieuwste eerst, Oudste eerst, Beste treffer | |
| een stand ("tot nu toe") | latest (Latest fact-checks, latest fact-check) | laatste, nieuwste | newest in een stand |
| de gegevens van één bouw | edition | uitgave | release, data release |
| zoeken zonder treffer | No results, No results for | Geen resultaten | Nothing found |
| de 404 | Page not found, Back to home | Pagina niet gevonden, Terug naar de start | This page does not exist |
| een filter op de soort | Type | Soort | Kind |
| een machinevertaling | Machine-translated from … | Machinevertaling uit het … | |
| in het zoekvenster | navigate, complete, open | navigeren, aanvullen, openen | choose |
| de naamsvermelding van een licentie | Attribution | Naamsvermelding | Credit |

## 8. Bewijsbank (peildatum 2026-10-14)

108.558 claims · 109.592 factchecks in de index, alleen van nagekeken
uitgevers (B28) · 47 talen (elk vooraf gemeten, B14) ·
839 beweringen met ≥2 onafhankelijke redacties · nieuwste check 2026-10-03 ·
316 meertalige clusters · 130 zombieclaims ≥1 jaar (57 ≥2 jaar), een
ondergrens (datastory van 2026-10-12, op 110.579 checks) · Google Maps/Palestina 2020→2024 in drie talen · nepvingers Lok
Sabha 2019→2024 · WhatsApp-betaald 2014→2019 · zonnebril in 3 talen ·
UNESCO-volkslied 2019→2024 · foutbovengrens 0,22% over 21 talen (run #64) · dekking
81,6% (over taalgrenzen 92,0%) · beeld 0 vals in 4.000 · 100% CC BY · AGPL-code, CC BY-protocol ·
missers live op /numbers. *Niet meer gebruiken:* Khaled Mashal (foute
samenvoeging, §77).

## 9. Changelog

- 2026-10-04 — eerste DRAFT, geoogst uit DESIGN §4, B18/B19, demo- en
  dashboardcopy; kalibratie met PO nog te doen.
- 2026-10-04 — kalibratie PO (persbericht v1→v2): een persbericht volgt de
  persconventies vóór de merkstem — kop is een krántenkop met het
  lanceerfeit, omgekeerde piramide, probleem eerst en dan de oplossing,
  oprichtersquote vroeg in de body. De datajournalistieke vondst is de
  subkop of het bewijs, nooit de kop. Stop-in power mag; waarheidsclaims en
  superlatieven blijven verboden.
- 2026-10-04 — kalibratie PO (persbericht v2→v3): perskoppen mogen het
  pregnante register in ("nieuw wapen tegen nepnieuws"), want de kop is
  voor de krant, niet voor het product; de PO beslist het kopregister per
  uiting. Onveranderd: de bodytekst oordeelt nooit zelf en claimt geen
  waarheidspercentages — de kop mag vonken, het bericht moet de factcheck
  overleven.
- 2026-10-04 — kalibratie PO (#22.7): Engels is de hoofdtaal van site,
  branding en pers; Nederlands blijft als editie voor de NL/BE-ring. Per
  kanaal een eigen register: pers pregnant, Hacker News en Product Hunt
  eerlijk-technisch — daar is het persregister een negatief signaal.
- 2026-10-11 — bewijsbank herrekend na de wissel naar bge-m3 en de negen
  nieuwe talen (#25.14c, #25.18, #25.14d c); het Mashal-voorbeeld geschrapt.
- 2026-10-13 — kalibratie PO (kop, afzender, social, missers): koppen op de
  site op niveau 0, afzender "we", social mag niveau 2, missers in
  meetcijfers met de opzet. De huidige homepage-kop ("Fake news doesn't
  die. Until now.") en de kop van de toepassingenpagina ("Six jobs behind
  one question") zijn van vóór deze kalibratie; de marketingsite (#23.11)
  volgt de nieuwe regel.
- 2026-10-13 — missie en tagline vastgelegd (B27).
- 2026-10-13 — PO: APPROVED. De twee koppen blijven staan tot de
  marketingsite (#23.11).
- 2026-10-14 — bewijsbank naar run #61 en de index na de witte lijst (B28);
  de datastorycijfers blijven die van 2026-10-12.
- 2026-10-16 — de twee oude koppen vervangen (PO: "eens, aanbevolen"):
  homepage "Search 109,592 fact-checks in 47 languages" met eronder "Paste a
  claim or drop a screenshot. Factiz shows which newsrooms checked it and
  links to their article. We never decide what is true ourselves.";
  toepassingen "Seven ways to use 109,592 fact-checks", met de missers
  ("Five of these jobs work today... For the other two, we publish what we
  measured so far.") in de tekst eronder, niet in de kop. De tagline blijft
  in de paginatitel en de OG-kaart; de kop zegt wat je er doet.
- 2026-10-16 — PO: de site start alleen in het Engels. De Nederlandse
  editie blijft voor pers en outreach (PERSBERICHT.md, de mails van ring 1);
  een sitetaal erbij pas met een publiek met een reden, met een
  taalschakelaar (PLAN #24.13).
- 2026-10-16 — bewijsbank naar run #64 na de twee tussenreleases van die
  dag (#25.36, #25.37): dekking 81,6%, de fouten gelijk; Ask 40 van 53.
- 2026-11-17 — de woorden in de interface vastgelegd (§7, na "is het niet 'latest' ipv newest?"): 25 Engelse en 8
  Nederlandse teksten gelijkgetrokken met wat mensen van andere sites kennen.
- 2026-11-21 — pay-off "For a world that can't be fooled." (B86, PO: "wordt onze globale pay-off"), in de voet in
  elke taal in het Engels (PO: "Ja, overal Engels"); "Where the world comes to double-check." als tactische zin. Afgewezen in de ronde: "Where lies come
  to die" ("misschien iets te militant"), en "a world without disinformation" letterlijk.
