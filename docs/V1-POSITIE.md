# Pangram voor nepnieuws — de positie van Factiz, 2026-10-27

> De PO (2026-10-27): "Wat ik ook nog zie als een gevaar, is dat we een droom
> hebben, maar dat frontier AI-labs al tegen hetzelfde probleem zijn aangelopen
> […] Iets waar wij bijna niet mee kunnen concurreren. Ik zoek naar een systeem
> dat eigenlijk één ding heel goed doet, heel erg vergelijkbaar met Pangram. […]
> wij gebruiken onderliggend grote AI-modellen, maar voor specifiek één taak,
> namelijk het herkennen van onzin, satire, nepnieuws en nieuws dat je probeert
> te nudgen. […] Pangram voor fake news."
>
> Bijgevoegd door de PO: het transparantieoverzicht en het dreigingsrapport
> (september 2026) van Anthropic, de pagina over hoe Claude AI-inhoud markeert,
> en een artikel over de nieuwe regels tegen nepbronnen. Bronnen onderaan.

## 1. Het gevaar: doen de grote labs dit al?

Wat de labs doen, volgens de stukken van de PO:
- **Ze bewaken hun eigen model en hun eigen gebruikers.** Het dreigingsrapport
  beschrijft negen beïnvloedingsoperaties die Anthropic op Claude zelf
  ontdekte, waaronder een netwerk van ~70 nepnieuwssites met 8.913 artikelen in
  ~20 talen. Anthropic zag ze omdat ze Claude gebruikten, en blokkeerde de
  accounts. Het rapport zegt zelf dat het zicht ophoudt zodra de inhoud live
  staat. Hoe misinformatie op X, Telegram of YouTube herkend moet worden,
  beschrijft het niet.
- **Ze stellen regels voor hun eigen gebruikers.** Vanaf 12 november 2026 mag
  niemand Claude gebruiken voor netwerken van sites die elkaar als
  "onafhankelijke" bronnen bevestigen. Dat raakt wie Claude gebruikt, niet wat
  er al op het web staat.
- **Ze markeren hun eigen inhoud.** Claude zet een onzichtbaar watermerk in
  tekst en Content Credentials (C2PA) in bestanden. Een merk zegt alleen dat
  Claude het maakte. Het ontbreken ervan bewijst niets.
- **Ze meten hun eigen gedrag:** weigeren bij verkiezingsmisbruik, politieke
  evenwichtigheid, hallucinaties.

**Wat geen lab doet:** een onafhankelijke detector verkopen die
misinformatie herkent, waar die ook vandaan komt, met een gepubliceerde
foutmarge per taal. Dat is dezelfde ruimte als die van Pangram:
- OpenAI stopte in juli 2023 met zijn eigen detector voor AI-tekst, wegens te
  weinig nauwkeurigheid. Een watermerk herkent alleen de inhoud van het eigen
  model.
- Pangram herkent tekst van élk model, en dat is precies waarom het bestaat.
- Labs vermijden bovendien de rol van scheidsrechter over waarheid. Meta stopte
  er in de VS mee, en Grok antwoordt wel, maar met bronnen die in 30–60% van de
  gevallen niet kloppen.

Het gevaar zit dus niet bij de detector. Het zit bij de gewone gebruiker: wie
in een app "is this true?" vraagt, gebruikt het lab zelf (Grok, ChatGPT). Die
markt winnen we niet. De markt van een onafhankelijke, meetbare detector voor
platforms, AI-labs, redacties en OSINT is open.

## 2. Wat Pangram precies doet, en wat we ervan leren

- **Eén taak:** is deze tekst door AI geschreven?
- **Een eigen, gespecialiseerd model**, getraind op miljoenen teksten van mensen,
  met AI-hulp en van AI. Pangram vraagt het niet aan een algemeen model; het
  bouwt er een voor deze ene taak.
- **Eén getal voorop: hoe vaak het onterecht alarm slaat.** Volgens Pangram zelf
  1 op ~24.000 documenten. Dat geldt voor Engelse lange teksten; onder 50
  woorden doet het geen uitspraak. Een onderzoek van de Universiteit van Chicago
  bevestigde bijna nul fouten op middellange en lange teksten.
- **Een vaste schaal:** vier niveaus (mens, licht geholpen, matig geholpen,
  volledig AI) met een score.
- **Gratis voor wie het eens wil proberen** (2.000 woorden per dag). Een API per
  woord voor organisaties ($0,05 per 100 woorden).
- **Eerlijk over de grenzen:** korte teksten, code en andere talen zijn zwakker,
  en dat staat erbij.

## 3. Waar de vergelijking niet opgaat, en hoe we dat oplossen

**AI-tekst zit in de tekst zelf; nepnieuws meestal niet.** "Het Europees
Parlement heeft een onderzoek naar Infantino geëist" leest precies als echt
nieuws. Of het waar is, staat in de wereld, niet in de zinnen. Het onderzoek is
daar duidelijk over:
- valse en ware teksten van een taalmodel lijken in stijl op elkaar
  (Schuster e.a., 2020);
- als een taalmodel nepnieuws herschrijft in de stijl van een betrouwbare krant,
  verliezen de beste detectors tot 38% van hun score (F1; Wu e.a., 2023);
- detectors leunen op toevallige kenmerken van hun trainingsdata, en houden het
  daarbuiten niet (2025).

Ons eigen lokale model herkende 28% van het nepnieuws (§144).

**Dus Pangram voor nepnieuws heeft twee lagen:**

| laag | wat het herkent | hoe | net als Pangram? |
|---|---|---|---|
| **in de tekst** | geen bewering, satire, onzin, sturing (angst, wij-tegen-zij, geladen woorden, valse keuze), een bewering over een beeld | een eigen, snel model per taak, getraind op gelabelde voorbeelden; een groot model labelt, een mens kijkt na (B34, B42) | ja: de vorm zit in de tekst |
| **in de wereld** | een bekende leugen (al ontkracht), een nieuwe onwaarheid, of het klopt | eerst de database met 110.000 factchecks in 47 talen (eigen zoekmodel; op 4.839 testparen hoogstens 0,22% fout); alleen wat daar niet in staat, gaat naar een groot model met webzoeken en bronnen | deels: het zoeken is ons eigen model, het oordeel over nieuwe beweringen niet |

Dat is dezelfde opbouw als in ARCHITECTUUR.md: eerst goedkoop en snel, alleen
de twijfel naar het grote model. Het is ook het doel van B42 (leraar en
leerling), nu voor de taak die in de tekst zit. Het eigen model hoeft niet te
weten wat waar is; het moet de vorm herkennen.

**Wat dat oplevert:**
- *Een eigen product, geen schil om Sonnet.* Het zoeken en de modellen voor de
  vorm zijn van ons. Het grote model is een onderdeel, zoals bij Pangram.
- *Goedkoop en snel.* De meeste berichten hoeven het grote model niet te zien:
  geen bewering, satire, of een bekende leugen. Een bericht kost dan een fractie
  van een cent in plaats van ~$0,03, en dat maakt platforms en AI-labs mogelijk.
- *Privacy.* Wat lokaal herkend wordt, verlaat de EU niet. Alleen de twijfel gaat
  naar het grote model.

## 4. Wat Factiz dan zegt

Per tekst of screenshot één label, met een score en de reden. Bij alles wat
uit de wereld komt, ook de bronnen:

| label | wat het betekent | uit welke laag |
|---|---|---|
| **bekende leugen** | al ontkracht door een redactie, met de check erbij | wereld (database) |
| **onwaar** | nieuw, maar betrouwbare bronnen spreken het tegen | wereld (groot model, met bronnen) |
| **misleidend** | deels waar, verkeerde context, oud beeld | wereld |
| **sturend** | stuurt met technieken (angst, wij-tegen-zij, geladen woorden), los van waar of onwaar | tekst |
| **satire** | bedoeld als grap | tekst |
| **onzin** | pseudowetenschap of kettingbrief, zonder controleerbare bron | tekst, en wereld als er een bewering in staat |
| **geen bewering** | een gewone tekst | tekst |
| **klopt** | betrouwbare bronnen bevestigen het | wereld |
| **onzeker** | niets beslissends gevonden | — |

Elk label krijgt per taal één getal voorop, zoals bij Pangram: **hoe vaak
Factiz dit label onterecht geeft.** Eis: hoogstens 1 op 100 bij elk label dat
iemand beschuldigt (bekende leugen, onwaar, misleidend, sturend, onzin), en
nooit bij een gewone tekst.

## 5. Wat er aan de route verandert

De volgorde van de PO blijft de kern: eerst bepalen wat een gewone tekst is, wat
een kloppende tekst is, en de verzamelingen. Voor een Pangram is dat zelfs nog
belangrijker, want het model leert van die verzamelingen. Wat erbij komt of
verschuift:

1. **De labels vastleggen** (§4): een omschrijving met voorbeelden per label en
   per taal, ook voor *sturend*, *satire* en *onzin*.
2. **Verzamelingen per label en per taal.** Bovenop de ware en valse teksten van
   etappe 32 komen satire, sturing en onzin erbij. Een groot model labelt via de
   Batch API, een mens kijkt een steekproef na. Bruikbare bestaande sets: de
   factchecks met oordeel *satire*, en een openbare meertalige set met
   sturingstechnieken (SemEval 2023, nog na te kijken).
3. **De eerste laag bouwen:** een eigen model voor de vorm (geen bewering,
   satire, sturing, bewering over een beeld), getraind op de Mac, achter de
   hittewacht. Het zoeken in de database in het wild verbeteren (nu 22% van het
   al ontkrachte).
4. **De tweede laag** is wat er nu staat: de controle met Sonnet, de bronnen en
   de regels van ronde 5. Alleen voor wat de eerste laag niet beslist. Citaten
   worden nagelopen.
5. **Per label en per taal meten**, met hoe vaak het label onterecht is als
   getal voorop.
6. **Daarna** een pagina met een gratis proef, en een API voor organisaties.

Kosten (schatting): labelen via de Batch API ~$10–20, trainen op de Mac $0, en
meten per taal ~$10–15. Voor Engels, Spaans en Duits samen ~$50–70; een
vierde taal ~$15 extra.

## 6. Wat de PO beslist

1. **De positie:** Pangram voor nepnieuws, met twee lagen: wat in de tekst zit
   herkent ons eigen model, wat in de wereld zit de database en daarna het grote
   model met bronnen. Akkoord?
2. **De labels van §4:** akkoord, of anders?
3. **Het getal voorop:** per label en per taal hoe vaak het onterecht is, met als
   eis hoogstens 1 op 100?
4. **Wat er met B46 gebeurt:** de acht uitkomsten van B46 worden deze labels,
   en etappe 32 krijgt de stappen van §5.

## Bronnen

- Anthropic, dreigingsrapport september 2026: https://www.anthropic.com/threat-intelligence-report-september-2026
- Regels tegen nepbronnen (Search Engine Journal): https://www.searchenginejournal.com/claude-rules-fake-sources-ai-answers/592456/
- Hoe Claude AI-inhoud markeert: https://support.claude.com/en/articles/16266773-how-claude-marks-ai-generated-content
- Anthropic, transparantie: https://www.anthropic.com/transparency
- Pangram, foutmarge en werking: https://the-decoder.com/pangram-says-its-new-ai-text-detector-makes-only-one-mistake-per-24000-documents/ en https://www.pcworld.com/article/3255226/pangram-review-a-polished-ai-detector-that-gets-the-basics-right.html
- Grenzen van Pangram (taal en lengte): https://www.eesel.ai/blog/pangram-4-alternatives
- Stijl herkent geen nepnieuws: Schuster e.a., https://arxiv.org/pdf/1908.09805; generaliseren van detectors, https://arxiv.org/html/2502.20299v1
- Grok, de markt en de audits: `docs/V1-MARKT.md`, `docs/RESEARCH.md`
