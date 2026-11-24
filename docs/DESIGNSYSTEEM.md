# Het designsysteem van Factiz

> Eigenaar: Designer · Status: IN AANBOUW (etappe 34) · Begonnen 2026-11-12

Dit document koppelt alles wat met het uiterlijk van Factiz te maken heeft: de oppervlakken, de bouwstenen, de tokens,
de onderdelen, de velden en waar dat in de code staat. Het is geschreven voor mensen en voor wie met Claude bouwt: wie
een pagina maakt of verandert, begint hier. `docs/DESIGN.md` blijft het logboek van de besluiten per pagina, met de
principes en de ontwerpchecks (D1 tot D14); dit document verwijst ernaar en herhaalt ze niet.

De ronde staat in `docs/PLAN.md`, etappe 34. Wat er nu staat is stap 34.1, de inventaris. De tokens (34.3), de onderdelen
(34.4) en de regels per oppervlak (34.5) komen erbij als die stappen klaar zijn.

## 1. De oppervlakken

| oppervlak | wat het is | pagina's nu | opmaak nu | straks (B76) |
|---|---|---|---|---|
| factiz.org, de oude site | wat Factiz is, voor wie, hoe het werkt | weg sinds 34.2f; de inventaris hieronder beschrijft haar zoals ze was | | |
| de placeholder | één stille pagina op factiz.org, ook voor onderhoud (34.2f) | Astro 7, statisch (`site/placeholder/`) | een eigen `<style>`, met Geist en het veld corpus van de site | het ene Astro-project |
| try.factiz.org | de demo, Ask, de cijfers, de controle per bericht | Python, HTML in een tekenreeks (`doublecheck/webui.py`) | `global.css` ingelezen, en `webui.STIJL` | het ene Astro-project |
| het platform | factchecks, thema's, dossiers, namen, zoeken | Python met Jinja (`factiz_site/templates/`) | `factiz_site/static/platform.css` en `velden.css` | het ene Astro-project, met Python eronder als dienst |
| de site | de nieuwe site, in vijf talen (34.2b, 34.2c, 34.2f) | Astro 7 op de server (`site/`) | Tailwind 4 en `site/src/styles/site.css` | het ene Astro-project |

## 2. De bouwstenen *(besloten: B75, B76)*

- **Astro 7** maakt elke pagina op de server; een pagina staat er dus ook als het script niet laadt.
- **React 19** alleen waar iets gebeurt: de filters, straks suggesties tijdens het typen en de menu's.
- **Tailwind 4**: de tokens als CSS-variabelen in één `@theme`, de opmaak als klassen.
- **Radix** voor wat met het toetsenbord en de schermlezer goed moet werken (vinkjes, menu's, lades, dialogen).
- **Onderdelen naar shadcn/ui**: de vorm en de namen van shadcn, met de kleuren en letters van factiz.org.
- **De velden** van `doublecheck.velden` als beeld: het eigen karakter van Factiz.
- **De regel voor script** (B75, bijgesteld 2026-11-12): de beste gebruikerservaring gaat voor. Script van de eigen site,
  of in de pagina met zijn hash in de beveiligingsregel; opmaak in attributen mag. Nooit gegevens van bezoekers bewaren,
  nooit bezoekers volgen, nooit analytics of script van een andere partij. Tellen mag anoniem en opgeteld, per dag en
  soort pagina, zonder IP, cookie of zoektekst (B78, E9.S26).
- **Van rechts naar links** (34.2bd, E9.S29): de richting komt uit de taal (`talen.js`); onderdelen en stijlen gebruiken
  begin en eind, nooit links of rechts (een test bewaakt dat); een pijl opzij staat in `<span class="pijl">` en draait mee;
  een tijdlijn blijft van links naar rechts.
- **Lettertypen van de eigen site** (B78, 34.2aw, 34.2as, 34.2bs): Geist en Geist Mono voor alles, met Noto Sans erachter
  voor de schriften van de sitetalen (Arabisch, Devanagari, Chinees, Japans), Newsreader alleen voor de kop van een
  factcheck, met Noto Serif voor dezelfde schriften erachter; elk ander schrift in de letters van het toestel. Het
  deelplaatje tekent elk schrift in Noto. Pakketten van Fontsource met een vaste versie, bij het bouwen gebundeld; de lijst
  in `site/src/styles/lettertypen.css`, gemaakt door `npm --prefix site run lettertypen`, elk deel met de tekens waarvoor
  het is, en van een lettertype per schrift alleen de delen van dat schrift. Niets van een lettertypedienst.

## 3. De inventaris *(34.1, 2026-11-12)*

Uitgelezen uit de code van alle oppervlakken; de cijfers zijn tellingen in de stylesheets, geen schatting.

### 3.1 Kleuren en tokens

De kleuren van §4h staan op drie plekken met dezelfde waarden: `global.css`, `platform.css` en de `@theme` van de proef.
De namen verschillen (`--papier` tegenover Tailwind's `--color-papier`, `--sans` tegenover `--font-sans`), en elk
oppervlak heeft tokens die de andere niet kennen.

| token | factiz.org | platform | proef | waarvoor |
|---|---|---|---|---|
| papier | `#f3efe8` | `#f3efe8` | `#f3efe8` | de grond |
| kaart | `#fbf9f5` | `#fbf9f5` | `#fbf9f5` | een vlak op papier |
| inkt | `#1d1b18` | `#1d1b18` | `#1d1b18` | de tekst |
| zacht | `#6b665e` | `#6b665e` | `#6b665e` | bijtekst |
| rand | `#ddd6ca` | `#ddd6ca` | `#ddd6ca` | haarlijnen |
| groen | `#0e8a5b` | `#0e8a5b` | `#0e8a5b` | de focusrand |
| groen-donker | `#0b6b47` | `#0b6b47` | `#0b6b47` | labels en links |
| mint | `#e9f0ea` | `#e9f0ea` | `#e9f0ea` | een gekozen knop |
| groen-nacht, groen-nacht-kaart, mint-inkt | ja | nee | nee | oude secties van de site |
| oranje, oranje-donker, oranje-inkt | ja | nee | nee | markeren wat verschilt (de bits) |
| accent-related | ja | nee | nee | de uitslag *related* op try.factiz.org |
| markeer | nee | `#fbe7a1` | `#fbe7a1` | de woorden van een zoekvraag |
| op-veld, groen-licht | nee | ja | ja | tekst en labels op een veld |
| invoer, invoer-inkt | nee | ja | nee | het witte zoekveld |
| breed, lees, doel, kop-h | nee | ja | nee | de maten van de schil |

Telling van losse kleurwaarden in de opmaak (ook die niet als token): factiz.org 37 gedeeld en 17 in de pagina's,
platform 29, de proef 27, try.factiz.org 0 (alles uit `global.css`), de tijdelijke site 4. Donker is overal alleen de
instelling van het apparaat (`prefers-color-scheme`); er is geen knop om te kiezen.

### 3.2 Letters

Overal de letter van het apparaat, in drie stapels (schreefloos, schreef, mono), op elke plek gelijk. De koppen dun (300)
en krap (-0,035em), de schreef alleen voor wat een ander zei (§4h). Een vaste schaal is er niet: in de opmaak staan 14
verschillende lettermaten in `global.css`, 40 in de pagina's van factiz.org, 24 in het platform, 11 in de tijdelijke site,
6 in try.factiz.org en 16 losse in de proef.

### 3.3 Maten

**De maat van een regel** *(2026-11-20, PO: "de ideale breedte van een stuk tekst ... zo rond de 60 characters")*. Lopende tekst
staat op `--maat-tekst` (48ch), een kop in een lijst op `--maat-kop` (52ch), en een bewering in een rij op 44ch
(`.rij-bewering`, PO 2026-11-15: "55-64 characters"). In de browser gemeten is dat ongeveer 70, 75 en 62 tekens per volle
regel. Reken nooit in ch als in tekens: in Geist is een ch (de breedte van een 0) zo'n 1,45 gemiddelde letter, dus 62ch
was 90 tekens. Een nieuwe alinea krijgt `max-w-[var(--maat-tekst)]` of valt in een `header` of `article` onder de regel in
`site.css`; `tests/test_site_themakleur.py` weigert een alinea op 60ch of breder. Alinea's hebben `text-wrap: pretty`.

| | factiz.org | platform | proef (Tailwind) |
|---|---|---|---|
| breedte van de inhoud | 66 rem (`.baan`) | 74 rem (`--breed`) | 74 rem |
| leeskolom | 46 rem in de band | 46 rem (`--lees`) | 46 rem |
| omslagpunten | 540 px, 760 px, 900 px, 40 rem | 22,5 rem, 48 rem, 56 rem, 62 rem | 40 rem, 48 rem, 64 rem (Tailwind) |
| hoeken | 8, 10, 12, 14, 16, 18, 22 px, rond | 2, 8, 10, 14, 16, 18, 22 px, rond | 2, 5, 10, 16, 22 px, rond |
| doel om aan te tikken | 44 px | 44 punten (`--doel`) | 44 px (`min-h-11`) |

Elf verschillende hoeken, en acht omslagpunten in factiz.org en het platform samen; geen ervan is een keuze die
ergens staat.

*De site in Astro (sinds 2026-11-17, PO: "check even of alle pagina netjes uitlijnen met de navigatie en dezelfde breedte
hebben"):* één baan, `.baan` in `site/src/styles/site.css` (80 rem, met de marge van de rand), voor de kop, de voet en elke
pagina; de smallere `.leesbaan` (72 rem) is weg. Lopende tekst houdt binnen die baan haar eigen leesbreedte (`max-w-[62ch]`).
`tests/test_site_html.py` (`..._lines_up_with_the_navigation_...`) weigert een tweede baan.

*Op een telefoon (2026-11-17, PLAN #34.2by, PO: "volledige sweep op mobiel view doen, overflow, weergave op 320px"):* de
site moet op 320 px passen zonder dat de pagina opzij schuift. Drie regels die daar misgingen:
- *Wat naast elkaar staat, mag onder elkaar.* Een rij in een raster krijgt `minmax(0, 1fr)`, een regel met een label en een
  datum `flex-wrap: wrap`, een knop met een lange tekst in een andere taal `whitespace-normal`.
- *Een veld is op een aanraakscherm 16 px* (`pointer-coarse:text-[16px]`, of de klasse `invoer`): onder 16 px zoomt Safari op
  iOS in zodra je erin tikt.
- *Een tikdoel is 44 px*, ook een kort woord in een lijst (`min-w-11`). Bewust kleiner: de wereldkaart, de ring van thema's en
  het netwerk van namen, met telkens een lijst of zoekveld ernaast.

*De tweede ronde (2026-11-24, PLAN #34.2ci, PO: "een grote responsive sweep voor mobiel, op alle punten"):* dezelfde meting,
nu ook op de Radar, de wereldlijst, de uitslag van een zoekvraag en de vraag om te meten. Wat daaruit als regel volgt:
- *Een knop en een stempel breken, ze lopen nooit door.* `.knop` is nooit breder dan zijn plek en krijgt op een aanraakscherm
  een tweede regel als het woord niet past (minstens 44 px hoog); `.fz-stempel` ook, gecentreerd in het kader. Alleen waar een
  rij knoppen opzij schuift (de thema's boven de lijst), houdt `shrink-0` ze op één regel.
- *Een stip staat tussen twee stukken, nooit vooraan een regel* (`.rij-voet`): elk stuk heeft zijn stip, de regel schuift één
  stip naar het begin en knipt die strook af.
- *Een woord met wie het zegt is één zin naast zijn icoon* (`.kenmerk-tekst`), geen twee smalle kolommen.
- *Een vaste kaart (de vraag om te meten) volgt de pagina:* is de pagina te breed, dan schuift de kaart mee buiten het scherm.
  Wie een kaart onderaan ziet weglopen, zoekt de oorzaak in de pagina.
Nagaan met `node site/scripts/mobiel.mjs` (zie CLAUDE.md); `tests/test_site_mobiel.py` houdt het vast.

### 3.4 Onderdelen

| onderdeel | factiz.org | try.factiz.org | platform | proef |
|---|---|---|---|---|
| kop | `Header.astro`: balk, op een veld in wit | dezelfde, in `webui.py` | `basis.html`, op een veld in wit | eigen, zonder uitklappers |
| menu | megamenu met kolommen en een uitgelicht stuk op een veld; telefoon: een verborgen vinkje opent het | hetzelfde | uitklappers (`details` met één naam), telefoon: een lade (`popover`) | geen |
| band bovenaan | `Band.astro`, veld groen | dezelfde, smal | `_band.html`, groen of het veld van een thema of dossier | het zoekveld op corpus |
| kaart op een veld | de drie ingangen (`.ingang`), het uitgelichte stuk | nee | thema's en dossiers (`.kaart-veld`) | dossiers |
| knop | `.knop`, `.primair`, `.omlijnd`, `.wit` | dezelfde | `button` zonder klasse, en losse klassen per plek (`.pil-wit`, `.knop-menu`, `.knop-filters`, `.knop-sluit`, `.stukje`) | `Button` met vijf soorten (shadcn) |
| klein label in mono | `.label` | `.label` | `.kicker`, `.soort`, `.kolom-kop` | losse klassen |
| oordeel van een redactie | nee | het labeltje van §4b | `.label` (een pil met een rand) | een pil in losse klassen |
| zoekveld | een strook die naar try.factiz.org wijst | het invulveld van de demo | `_zoekveld.html` en het veld in de kop | eigen, in de pagina |
| filters | nee | nee | `_filters.html`: vinkjes, keuzelijsten, lade | `Archief.jsx`: vinkjes van Radix |
| rij in een lijst | nee | de bonnetjes | `_rijen.html` | `Rij` in `Archief.jsx` |
| voet | `Footer.astro`: veld nacht, de missie, een kaart van glas | dezelfde | `basis.html`: dezelfde opbouw | korter, dezelfde opbouw |

**De vaste onderdelen en klassen van de site** *(2026-11-21, PO: "wil je kijken wat we nog meer gelijk kunnen trekken, met
dezelfde classes op kunnen lossen")*. Wie een pagina maakt, gebruikt deze en bouwt ze niet opnieuw met losse maten:

| wat | onderdeel of klasse | waar |
|---|---|---|
| kruimelpad | `Kruimel.astro` (`stappen`, `telefoon={false}` op een factcheck) | elke pagina |
| kop van een pagina | `.paginakop` met `.groot-kop` en een inleiding | elke overzichtspagina; de Radar met het zegel klein ervoor |
| kop van een sectie | `.sectiekop` met een `h2` (15 px) | pagina's met gegevens |
| kop in een lange tekst | `.leeskop` (18 px) | Over, Platform, de database |
| titel van een kaart of vak | `.kaartkop` (16 px) | bronnen, het netwerk, bijdragen |
| label in een vak | `.vakkop` (13 px, zacht) | het antwoord, waarom het niet klopt, het omveld |
| kop van een groep in een lijst | `.lijstkop` | de jaren van een dossier, de groepen van de Radar |
| vak op een paneel | `.paneel .vak` (1 rem binnen, .75 rem tussen) | elk paneel met inhoud |
| zijkolom | contextkaarten `.ck`, met `.ck-vraag`; een kaart die een link is `.ck-klik` | factcheck, eigen check, Radar, dossier |
| factcheck in een lijst | `Rij.jsx` | archief, dossier, Radar, verbanden |
| oordeel | `.fz-stempel`, groot `.fz-stempel-groot`; een eigen check met het zegel ervoor (D12) | overal |

### 3.5 De velden

Eén script, `python -m doublecheck.velden`, met vijf families (nacht, groen, hemel, olijf, leisteen) en corpus, dat uit
de checks zelf getekend is. Op factiz.org zes beelden in `web/public/beeld/`, met de sluier per plek in `global.css`. Op
het platform 31 beelden in `factiz_site/static/beeld/` (drie kopieën, en per thema en dossier een band en een kaart), met
`velden.css` uit het script. De regels: wit haalt zijn contrast in elke tekstzone na de sluier, ook als het veld schuift;
geen rood; hooguit 200 KB per beeld; nooit een veld achter een bewering, label of bron (D11). De tests:
`tests/test_velden.py` en `tests/test_velden_platform.py`.

### 3.6 Wat afwijkt, en waarom

- **De kleuren staan drie keer in de code**, omdat elk oppervlak apart gebouwd is; de waarden zijn gelijk gebleven, de
  namen niet. Daar komt 34.3 voor: één bron.
- **`.label` betekent twee dingen**: op factiz.org een klein label in mono, op het platform het oordeel van een redactie.
  Een naam per betekenis voorkomt dat een oordeel er ooit uitziet als een kopje.
- **Het menu is twee keer anders gebouwd**: op factiz.org met een verborgen vinkje, op het platform met uitklappers en een
  lade, omdat het platform later kwam en geen script mocht. Met Radix (B76) wordt het één menu.
- **Knoppen in drie systemen**: de pillen van factiz.org, de knoppen van het platform zonder klasse, en die van de proef
  naar shadcn. Ze lijken op elkaar, maar hun maten en staten (hover, focus, gekozen, uit) verschillen.
- **Geen schaal voor letters, hoeken en omslagpunten**: maten zijn per pagina gekozen. Elf hoeken, acht omslagpunten en tientallen
  lettermaten zijn de grootste bron van onrust in het beeld.
- **De velden staan twee keer op schijf**, omdat het platform geen code van het lab leent; met één voorkant (B76) wordt dat
  één map.
- **Donker volgt alleen het apparaat**; een eigen keuze ontbreekt. Of die er komt, hoort bij 34.2.
- **De tijdelijke site en try.factiz.org** lezen de opmaak van factiz.org in; ze lopen dus vanzelf mee, maar ook vanzelf
  achter als factiz.org verandert.

## 4. Richting B en de regels voor vinden *(34.2b, PO 2026-11-12)*

De PO koos B, de werkbank: "praktisch, bijna als een cloudflare of vercel", met de UX van een webwinkel om snel te vinden.
De bibliotheek is gereedschap; de voorpagina, de blog en de factcheck zelf zijn vriendelijk en inzichtelijk. De regels
hieronder komen uit haar studie naar e-commerce-UX (de aantekeningen bij Baymard, `#nummer` is de richtlijn), vertaald
naar een bibliotheek van factchecks. Wat niet past, staat onderaan, met de reden.

**De vertaling.** Een product is een factcheck; een categorie is een thema (met onderdelen); een collectie is een dossier;
een merk is een redactie; de prijs is het oordeel van de redactie; een beoordeling is het aantal redacties dat de
bewering natrok (een telling, nooit een score); varianten zijn dezelfde bewering in andere woorden en talen. De lijst is
een lijst om te lezen, met tekst als kern (#2269, *spec driven*).

**Het uiterlijk.** Klein en strak, zoals Vercel: Geist en Geist Mono (OFL, van de eigen site), met Newsreader alleen voor de
kop van een factcheck (34.2aw; Noto Serif per schrift erachter), neutrale grijzen met een
lichte zweem van groen, haarlijnen van 1 punt, hoeken van 6 tot 8 punten, knoppen klein maar op een aanraakscherm 44
punten. Zwart (in donker wit) is alleen de primaire knop (#730, #791). Groen is de focusrand en het merk. De velden: een
dunne strook in de kop, een kaart bij elk thema en dossier, en ruimer op de vriendelijke pagina's.

**Kleur bij het oordeel** *(34.2l, PO 2026-11-12: "onduidelijke labels door gebrek aan kleur")*. Het oordeel van een
redactie is een van de twee plekken waar kleur iets zegt (de andere is het onderwerp, hieronder), en dan altijd samen
met het woord en een stip (`.label[data-soort]`,
`.stip[data-soort]`). Eén as, kleurenblind-veilig: amber voor onwaar (ook *onwaar of misleidend*), geel voor misleidend,
zand voor deels waar, blauw voor waar; violet voor omstreden, roze voor satire, grijs voor onbewezen en voor *gecheckt*
zonder oordeel. Geen rood, oranje of groen, want dat is een stoplicht (DESIGN principe 1 en 3), oranje is het logo en
groen het merk. De waarden staan in `site.css` als `--l-inkt`, `--l-vlak`, `--l-rand`, `--l-stip` per soort, licht en
donker; `tests/test_site_oordelen.py` eist elke soort uit `i18n.LABELS` met tekst van minstens 4,5:1 op het vlak en een
stip van minstens 3:1 op het paneel.

**Kleur en icoon bij het onderwerp** *(34.2ag, SPECS E9.S16, PO 2026-11-15: "Ja, begin daarmee")*. Elk thema heeft een
tegel: een vierkantje in de kleur van zijn familie met een eigen icoon erin (`ThemaTegel.jsx`, `.tegel[data-familie]`),
altijd naast de naam en voor een schermlezer verborgen. Vierkant, zodat het nooit lijkt op het rondje van een oordeel.
Vijf families, met de namen van de velden: macht in leisteen (politiek, verkiezingen, wereld), conflict en veiligheid in
nacht (oorlog, misdaad, rampen), gezondheid en wetenschap in groen, geld en aarde in olijf (economie, klimaat), mensen in
hemel (samenleving, migratie, personen). De familie van een thema is ook die van zijn veld (`velden.THEMA_VELDEN`). De
kleuren (`--f-leisteen` tot `--f-hemel`, met `--f-icoon`) zijn gezocht en gemeten: onder gewoon zien en de drie vormen
van kleurenblindheid (Machado e.a. 2009) minstens ΔE 20 uit elkaar (licht 21,6, donker 25,9), het icoon minstens 3:1 op
de tegel en de tegel 3:1 op het paneel, en minstens ΔE 18 van elke kleur van het oordeel; `tests/test_site_themakleur.py`
meet het opnieuw bij elke wijziging. De iconen zijn van Lucide (ISC), als gegevens in eigen code, zonder pakket. Drie
maten: klein in een regel tekst (16 punten), midden in een menu, de zoeksuggesties, een kop en de kaarten op de start (20), groot op het
overzicht van de thema's (30). Een land krijgt nooit een kleur.

**Verkennen** *(34.2ah, SPECS E9.S17, PO 2026-11-15: "Ja, bouw Verkennen")*. Eén pagina, `/explore/`, met drie delen aan
één keuze, in de volgorde van Shneiderman: eerst het geheel, dan inzoomen, dan één pagina. De ring van thema's (elk zo
groot als zijn aantal, per familie bij elkaar, met de legenda per familie ernaast), *Wanneer* (staven per jaar, de laatste
elf jaar, het lopende jaar lichter) en *Waar ter wereld* (de tien landen, met *Aantal* en bij een thema *Verhouding*, met
een stippellijn op gemiddeld). Een keuze is een link (`?thema=`, `?maat=verhouding`), dus de pagina werkt zonder script;
een jaar of land opent de lijst met dat filter. De kleur is die van de familie van het gekozen thema, zonder keuze grijs.
Alles is SVG of tekst, op de server getekend, zonder bibliotheek (`lib/verkennen.js` rekent de bogen). De ring is voor een
schermlezer verborgen en heeft geen tabstop; de legenda, de jaren en de landen zijn gewone links met hun aantal. De
landen staan op één raster (subgrid), zodat elke staaf dezelfde schaal heeft; op een telefoon staat de staaf onder de
naam. Elk deel zegt wat het telt, en nergens een percentage.

**Het netwerk van namen** *(34.2ai, SPECS E9.S18, PO 2026-11-15: "Ja, bouw het netwerk")*. `/explore/network/`: de 70
namen in de meeste factchecks, een lijn bij minstens 25 factchecks samen (dikker naarmate het er meer zijn), een cirkel zo
groot als het aantal factchecks met die naam in de kleur van de familie van zijn meest voorkomende thema. De plekken
rekent het platform (`factiz_site/netwerk.py`): ForceAtlas2 (Jacomy e.a., 2014) in de lin-log-vorm met sterke
zwaartekracht, gekozen uit zes varianten op de echte uitgave omdat de groepen dan zichtbaar worden (India met zijn
partijen en deelstaten, Rusland en Oekraïne met Europa, het Midden-Oosten), daarna schuiven cirkels en labels uit elkaar
tot niets overlapt. Een label staat onder de 30 grootste namen; de breedte ervan is de breedste schrijfwijze over de vijf
talen, dus elke taal heeft dezelfde plek. Boven het netwerk staat dat een naam niets zegt over wie iets beweerde of
verspreidde (E9.S11 AC4). Een naam kiezen (`?naam=`) zet hem met zijn buren ernaast, op een telefoon erboven; het
eiland (`NetwerkKaart.jsx`) laat bij aanwijzen de buren oplichten, vindt een naam met een zoekveld dat alleen in de
browser werkt, en schuift op een smal scherm het vlak naar de gekozen naam. Op een telefoon schuift alleen het vlak
opzij. De lijst eronder staat op alfabet, nooit op aantal (E9.S11 AC5, aangescherpt op 2026-11-15).

**Soort en vorm, alleen waar het zeker is** *(34.2ak, SPECS E9.S19, PO 2026-11-15: "Ja, begin met route 1")*. De derde
drager van E9.S16: een lijnicoon zonder kleur met het woord (`LijnIcoon.jsx`, Lucide 0.460.0 als gegevens, ISC). De
soort volgens de redactie: *Bewerkt of nagemaakt* (schaar), *Zonder of uit zijn context* (oog in een kader),
*Verzonnen* (pen), *Satire* (maskers), *Gemaakt met AI* (sterretjes), met *volgens de redactie* erachter; de vorm:
*Video* (camera) en *Beeld* (foto). Op de kaart in de regel onder de bewering, op de factcheckpagina als knopje naar de
lijst met dat filter, en als filter direct onder het oordeel, met de uitleg wat het telt. Geen model: de soort komt
uit de nagelezen woorden van de redacties (`docs/steekproeven/34.2ak-soortwoorden.json`), de vorm uit de Engelse woorden
van de bewering.

**De wereldkaart** *(34.2am, SPECS E9.S20, PO 2026-11-15: "Ga verder met stap 5, de wereldkaart")*. In *waar ter
wereld* op Verkennen, boven de staven. Vijf trappen van dezelfde kleur, donkerder bij een hogere maat (bij een thema de
kleur van zijn familie, anders grijs); een land zonder maat is een licht vlak met een rand, met een eigen vakje in de
legenda. Bij het aantal zijn de grenzen die van vijf even grote groepen landen, afgerond tot een leesbaar getal; bij de
verhouding vaste grenzen rond 1×. De grenzen van Natural Earth (publiek domein, 1:110 miljoen) in Equal Earth, zodat elk
land zijn echte oppervlakte houdt; de PO stuurde simplemaps.com, maar die licentie verbiedt verder verspreiden en die
kaart is Robinson. 19 kleine gebieden en Antarctica staan onder de kaart als *niet op de kaart*. De kaart is een plaatje
voor een schermlezer; alle landen staan als lijst eronder (*alle landen als lijst*). Een land onder de muis krijgt de
kleur van een link, zonder rand (bij de groene familie de kleur van de tekst, want de linkkleur ligt daar te dichtbij; PO
2026-11-15: "Wereldkaart hover met border is niet zo mooi, beter een kleur veranderen op hover denk ik").

**Het icoon in een tegel** *(PO 2026-11-15: "iconen lopen tot de rand van de box, die moeten in hun eigen 24px grid zitten
en niet uitvullen")*. Een icoon van Lucide is getekend in een raster van 24 en houdt in de tegel zijn eigen maat: 11 in 16,
13 in 20, 18 in 30. Een regel die een beeld over de hele breedte van zijn vak zet, schrijft `> svg`, zodat hij nooit een
icoon in een tegel erbinnen raakt (de ring van Verkennen deed dat); `tests/test_site_themakleur.py` eist het.

**Contextkaarten naast een factcheck** *(34.2an, SPECS E9.S21, PO 2026-11-15: "Ja, bouw ze")*. Hoogstens vier, in deze
volgorde: dossier, waar, namen, wanneer, soort en vorm, redactie; een kaart zonder gegevens valt weg en de volgende schuift
op. Elke kaart één vraag als kop, één klein beeld in de kleur van het thema (de jaren van het dossier als staafjes, een
uitsnede van de wereldkaart, een lijn over de jaren met een stip op deze factcheck, een lijnicoon), één zin met het getal,
wat de telling níet zegt eronder, en één link naar Verkennen, het netwerk, het dossier of de lijst met hetzelfde filter.
De beelden zijn voor een schermlezer verborgen; de zin zegt het. Naast het artikel op een breed scherm, boven de inhoud,
die blijft staan zodra de kaarten voorbij zijn; op een telefoon onder het artikel, naast elkaar zolang er plaats is. Het dossier staat in de kolom als kaart met zijn
jaren; het veld van het dossier staat alleen onder *Verbanden*.

**Een tekening per thema en per dossier** *(34.2ap, SPECS E9.S22, PO 2026-11-15: "Op het veld")*. De tekentaal van de
routeplaatjes van Ideelab, abstracter, op de korrel van het veld: een halfdoorzichtig vel dat linksboven inspringt en rechts en onder
uit het beeld loopt, met hoogstens drie soorten vormen zonder woorden in de kleur van de familie, en alleen de vorm die de
betekenis draagt op volle kleur. De vormen vervagen naar onder. Het veld blijft eronder en brengt de enige korrel mee:
een tweede korrel over de tekening gaf een dubbele korrel en een lichte rand waar de tekening begon (PO 2026-11-15). Elk thema en elk dossier een eigen tekening, een onderdeel die van zijn thema. Op de
themakaart vult het vel het beeld en passen de vormen erin; de dossierkaart heeft een hogere uitsnede van hetzelfde
raster; in de kop van een thema of dossier staat de tekening rechts naast de naam, en op een telefoon niet. Een tekening
toont het onderwerp, nooit de bewering die gecheckt is, en nooit een oordeel: geen vinkje, geen kruis. In donker een
donker vel met de lichte kleuren van de families.

**Het deelplaatje per factcheck** *(34.2aq, SPECS E9.S23, PO 2026-11-15: "Maak nu het deelplaatje per factcheck")*.
1200 bij 630: bovenaan de band met het veld en de tekening van het thema, rechts zoals in de kop; daaronder op wit de
bewering in Geist (de kop van de pagina, tot drie regels, kleiner als het moet en anders afgekapt na een heel woord), het
label met zijn stip in de kleuren van de site, de zin wie het checkte en wanneer, en het woordmerk rechtsonder. Kan het
lettertype het schrift niet tonen, dan de Engelse versie, en anders geen bewering: het label en de zin staan dan midden
in het vlak, en een naam die het lettertype niet kent maakt plaats voor de telling van de pagina. Zuinig: getekend als
iemand het vraagt, bewaard in het geheugen van het platform en, met de versie van de uitgave in het adres, een jaar in
een cache; niets vooraf. Een thema, een onderdeel en een dossier hebben er ook een *(34.2ar, PO: "Ja, maak ze")*: dezelfde
band (bij een dossier zijn eigen veld en tekening), daaronder de soort klein, de naam groot en het aantal factchecks
(bij een dossier met redacties, talen en jaren). De overzichten en de vaste pagina's houden het vaste beeld.

**Het vlak onder de bewering** *(PO 2026-11-15: "zullen we de main factcheck wat meer vrijzetten door een subtiele
background te maken?")*. Het thema, de bewering en het blok *Klopt dit?* staan op een eigen vlak in de tint `--vlak`,
een effen kleur en nooit een veld (D11); op een breed scherm loopt het vlak iets buiten de tekstlijn.

| waar | regel | nummer |
|---|---|---|
| overal | het logo naar de voorpagina; zoeken altijd in de kop, met een knop | #257, #351b, #944 |
| overal | de thema's als eerste niveau in het menu, *Bekijk alles* bovenaan elk niveau, de huidige plek gemarkeerd; het menu opent meteen, zonder wachttijd bij aanwijzen en zonder fade (PO 2026-11-15: "deze uitklap moet instant worden"; Baymard #289 raadt 300 tot 500 ms aan) | #287, #1006, #300 |
| overal | de links over Factiz (over, bronnen, platform) apart van de hoofdnavigatie: in de voet en onderaan de menulade, niet in de kop; rechts in de kop staat alleen gereedschap (zoeken, taal). *PO 2026-11-12: "Ja, haal hem uit de kop"* | #288 |
| overal | de terugknop doet wat je verwacht: een filter terug, een lade dicht, de lijst op dezelfde plek (die plek staat in de geschiedenis van het tabblad, `history.state`, niet in opslag) | #1057, #492, #1024 |
| overal | nooit iets dat ongevraagd opengaat; meteen zichtbaar dat een tik iets doet | #284, #928, #1509 |
| zoeken | suggesties tijdens het typen op elk zoekveld (het venster, het grote veld op de start, het veld boven de lijst; `zoeken.jsx`, `Zoekveld.jsx`): hoogstens 10, eerst zoekvragen en ingangen, factchecks apart gegroepeerd, wat je typte gewoon en wat erbij komt vet, pijltjes nemen de suggestie over en lopen rond, het woord grijs afgemaakt in het veld en Tab of → neemt het over; terug geeft dezelfde vraag uit de geschiedenis van het tabblad (PLAN #34.2ac) | #359, #404, #356, #369, #361, #348, #1024 |
| zoeken | de vraag blijft in het veld; het aantal boven de treffers; waarom een treffer er staat (gemarkeerd) | #346, #377, #382 |
| zoeken | geen doodlopende weg: andere zoekvragen, ingangen, thema's, de hele lijst | #362, #358 |
| zoeken | een vraag die precies een thema, dossier of naam is, leidt daarheen | #370 |
| zoeken | een spelfout zonder treffers wordt verbeterd naar het dichtstbijzijnde woord uit de uitgave, en de pagina zegt het; de vraag in het veld blijft (34.2i) | #355, #1001 |
| lijst | het kruimelpad; het aantal boven en onder; dezelfde gegevens in elke rij in dezelfde volgorde | #537, #531, #443 |
| lijst | de bewering in een kaart in Geist, 16px medium, hoogstens 44ch breed: 50 tot 66 tekens op een volle regel, mediaan 60, in het Engels en het Nederlands (PO 2026-11-15: "Leesbaarheid werkt volgens mij tot 55-64 characters"; Newsreader las in de lijst lastig, 34.2aw) | |
| lijst | elke factcheck een kaart in drie lagen: het oordeel met de datum, de bewering (hoogstens drie regels), de context (thema, redacties, de taal als er geen vertaling is); op de start, in de lijst en bij *Komt ook voor als* hetzelfde onderdeel (`Rij.jsx`, 34.2l) | #443, #2269 |
| lijst | *Meer laden*, 20 tot 30 per keer; terug naar dezelfde plek | #501, #502, #1024 |
| lijst | een bewering met haar varianten is één rij | #421 |
| filters | vinkjes, meer waarden tegelijk, het aantal bij elke waarde, ingekort na 6 tot 8 met *Nog n tonen*; wat één keuze is (thema, land, redactie) krijgt rondjes met *Alles* bovenaan, want een vinkje belooft meer tegelijk | #479, #427, #467, #470 |
| filters | de gekozen filters als stukjes boven de lijst, elk los weg te halen; een paar thema's boven de lijst alleen op een telefoon, waar de filters in een lade zitten: breed staan de thema's al in de kolom links (34.2bq, PO 2026-11-16: "deze kan wel weg volgens mij, staat al links") | #488, #474 |
| filters | lange lijsten (redacties, landen) met een zoekveld | #1126 |
| filters | breed staan ze links in één paneel met dezelfde dunne rand, hoek en achtergrond als de kaarten van de lijst en de kaarten naast een factcheck (`.filterkolom`); de groepen erin gescheiden door een lijn; de kop van een groep klein, in hoofdletters en in de zachte kleur, met de lucht boven de kop en niet eronder (34.2bh); het paneel is zo hoog als de filters, niet als de lijst (PO 2026-11-15: "is het mooier dat de linker sidebar ook subtiele border heeft, net als de rest?") | |
| filters | op een telefoon twee tekstknoppen; een lade met een vaste knop *Toon n resultaten*, *Wis alles* en een kruisje | #1198, #1125 |
| sorteren | een keuzelijst met *Sorteren op:* ernaast; bij zoeken eerst de beste treffer; geen alfabet | #514, #521, #510, #539 |
| lijst | zoeken en sorteren op één rij boven de lijst, naast het filterpaneel: het zoekveld links, *Sorteren op* rechts; de gekozen filters eronder; op een telefoon het veld over de hele breedte, daaronder *Filteren* en *Sorteren op* (34.2bg) | #514 |
| lijst | op een breed scherm blijven de rij met zoeken en sorteren en het filterpaneel staan terwijl de berichten eronder door schuiven; het paneel scrollt zelf als het langer is dan het scherm, zonder zichtbare balk tot de muis erop staat en met een zachte vervaging onderaan zolang er meer is; na een nieuw filter, zoekvraag of volgorde terug naar het begin van de lijst; op een telefoon niets vast (34.2bj) | |
| keuzelijst | één stijl voor elke keuzelijst (taal, volgorde, *Thema's* in het menu, licht of donker; `fz-keuzes`, `fz-keuze`): een paneel met hoeken van 12 px en de hoge schaduw, regels van 36 px (44 bij aanraken) met hoeken van 8 px, dezelfde zachte achtergrond onder de muis en bij het toetsenbord, de gekozen waarde met een vinkje rechts in de accentkleur, zacht openen behalve bij `prefers-reduced-motion` (34.2af) | #404, WCAG 2.4.7 |
| zoeken | een geplakt bericht zoekt op zijn opvallendste woorden: *N factchecks lijken op je bericht* met de woorden die telden, of zonder treffer *Deze factchecks hebben woorden gemeen met je bericht*, de tien met de meeste van dezelfde woorden en gezegd dat het geen treffers zijn; nooit tienduizenden (34.2au) | #362, #358 |
| factcheck | het kruimelpad én *Terug naar resultaten* met de filters | #828 |
| factcheck | het oordeel en de telling bovenaan, in één oogopslag; de telling springt naar de bronnen | #792, #786 |
| factcheck | één primaire knop: *Lees de factcheck bij de redactie* | #730, #791 |
| thema's | het overzicht als kaarten met veld, naam, aantal en de onderdelen; een thema of onderdeel opent met zijn veld en naam, dan de lijst met filter, de onderdelen, de dossiers en de nieuwste factchecks; navigatie wijst naar de pagina, de knoppen in de lijst blijven filters (34.2u) | #307, #308, DESIGN §4w |
| redacties, over, bronnen, platform | *Platform* de vaste tekst in vier delen met hun stand en ankers; redacties met het aantal beweringen en elk de lijst met dat filter; *Over* de vaste tekst met het adres als tekst en de ankers `#corrections` en `#privacy`; *Bronnen* elke bron met licentie, naamsvermelding en link (34.2t) | E9.S10 |
| dossiers | het overzicht: elk dossier als dezelfde kaart als op de start (veld, soort, naam, begin van de inleiding, aantal, laatste aanvulling), de nieuwste boven; *Dossiers* in de kop gaat hierheen (34.2s) | DESIGN §4w |
| kaart | onder de bewering het thema, het land waar ze over gaat (zonder voorzetsel), het aantal redacties en de taal zonder vertaling (34.2w) | #443, #2281 |
| namen | niet in de kop, wel in de voet (een naam vind je via zoeken, een factcheck of het filter); het register per soort op alfabet, zonder tellingen; de pagina van een naam met de soort, de zin dat een naam niets zegt over wie een bewering deed, Wikidata, de nieuwste factchecks met de ene kaart en de lijst met het filter (34.2r) | DESIGN §4u |
| factcheck | het antwoord voorop: onder *Klopt dit?* één vlak in de kleur van het oordeel (`.uitspraak`, de tokens `--l-…`), het woord groot (22 tot 28px, halfvet) met de stip, dan wie checkte en wanneer, en bij één check de eigen woorden van de redactie erin; de taal van de check naast de knop (34.2ax, PO 2026-11-15: "Onze conclusie hebben wij wel heel subtiel vormgegeven") | #730 |
| factcheck | op een telefoon het antwoord in het eerste scherm: geen kruimelpad (het thema staat in het vlak, *Terug naar resultaten* blijft), het thema en de kenmerken op één regel, de kop vanaf 22px, het origineel onder het antwoord (34.2ay) | #957 |
| factcheck | het antwoord en de checks in één kaart *Klopt dit?*: bij één check alleen hun eigen woorden en de ene knop, bij meer elke check als regel in die kaart (de eerste knop primair); geen losse kaart *Wie het checkte* (34.2q) | #791 |
| factcheck | direct onder het oordeel *Waarom het niet klopt, volgens EUvsDisinfo*: hoogstens drie punten uit hun weerlegging, samengevat door Factiz met de bron en de link, en *Meld een fout* (de gemeten foutmarge staat sinds PO 2026-11-22 op *Bronnen en licenties* bij EUvsDisinfo, zoals B77 toestaat); geen label of kleur, zodat het nooit leest als een eigen oordeel (34.2j, B77) | #792 |
| factcheck | het omveld direct onder het oordeel: gecheckt (eerst, laatst, de jaren), eerst gezien, toegeschreven aan en ook bekend als, elk alleen met een bron en alleen als er iets te zeggen is; geen zoekvolume (34.2h) | OpenSanctions *first seen*, Discogs |
| factcheck | één lange pagina met een inhoud die blijft staan op een breed scherm, vloeiend scrollen | #758, #784 |
| factcheck | de woorden van een redactie in een andere taal dan de site krijgen een machinevertaling eronder; een oordeel dat de tabel niet kende, leest een taalmodel, pas na een leesproef (34.2o) | #786 |
| factcheck | *Lijkt op*: in het blok *Klopt dit?* hoeveel andere factchecks over hetzelfde verhaal er zijn, per oordeel, met een link naar hun kaarten in *Lijkt hierop*; nooit samengevoegd tot één oordeel (34.2p) | #738, #810 |
| factcheck | boven de inhoud hoogstens vier contextkaarten: het dossier met zijn jaren, waar, namen, wanneer, soort en vorm, redactie; op een telefoon onder het artikel; het veld van het dossier alleen onder *Verbanden* (34.2n, sinds 34.2an) | #810, #738 |
| factcheck | onderaan *Klopt hier iets niet?*: een mail aan info@factiz.org met het nummer en de taal in het onderwerp en een lijstje van wat de machine op die pagina deed om aan te kruisen; het adres ook als tekst; een fout in het oordeel hoort bij de redactie, via hun artikel; geen formulier, niets bewaard (34.2at, B75) | #1706 |
| factcheck | de verbanden als laatste: hetzelfde bericht elders (alternatieven) en wat erbij hoort (dossier, namen, thema), elk met *Bekijk alles* | #738, #810, #811, #812 |
| voorpagina | veel thema's in beeld, ingangen in de inhoud, begeleide routes (de dossiers), geen carrousel, geen reclame | #237, #236, #249, #242, #240 |
| thema | een overzicht met de onderdelen bovenaan, dan de dossiers, dan dezelfde lijst als *Factchecks* met het thema vast: filters links, zoeken binnen het thema, op een telefoon de lade (34.2bb) | #307, #308, #253 |

**Bewust niet.** Prijs, kleur en maat als filter, beelden van het product, reviews en sterren, een vergelijkfunctie, een
winkelwagen en afrekenen, en accounts (#1167, #740, #739, #495, thema 05 en 06): een factcheck heeft ze niet, of het
platform heeft geen inlog. Geen beeld van het nepnieuws (§4p). Spelfouten verbeteren (#355, #1001) is gebouwd in 34.2i.

## 5. Waar het in de code staat

| wat | waar |
|---|---|
| de opmaak en het menu van de demo (try.factiz.org) | `doublecheck/demo/global.css` en `site.json` (de oude site is weg sinds 34.2f) |
| opmaak van try.factiz.org | `doublecheck/webui.py` (`STIJL`, en `global.css` ingelezen) |
| opmaak van het platform | `factiz_site/static/platform.css`, `factiz_site/static/velden.css` |
| sjablonen van het platform | `factiz_site/templates/` |
| de site in Astro | `site/` (Tailwind in `src/styles/global.css`, de tokens en onderdelen in `src/styles/site.css`, Radix in `src/components/ui/` en `src/components/site/`) |
| de velden en hun herkomst | `doublecheck/velden.py`, `factiz_site/static/beeld/` (`HERKOMST-basis.md` en `HERKOMST.md`) |
| de tegel per thema: kleur, icoon en de licentie van Lucide (34.2ag) | `site/src/components/site/ThemaTegel.jsx`, de tokens `--f-*` in `site/src/styles/site.css` |
| Verkennen: de pagina, de bogen en de ingang (34.2ah) | `site/src/components/site/paginas/Verkennen.astro`, `site/src/lib/verkennen.js`, `/api/<taal>/verkennen` in `factiz_site/app.py` (`db.verkennen`, `db.verhoudingen`) |
| het netwerk van namen (34.2ai) | `site/src/components/site/paginas/Netwerk.astro`, `site/src/components/site/NetwerkKaart.jsx`, `factiz_site/netwerk.py` (de schikking), `/api/<taal>/netwerk` in `factiz_site/app.py` (`db.netwerk`) |
| soort en vorm (34.2ak) | `doublecheck/soortvorm.py` (de regels), de tabel `kenmerk` in de uitgave, `site/src/components/site/LijnIcoon.jsx`, de filters `soort` en `vorm` in `factiz_site/db.py` |
| de tekening per thema en per dossier (34.2ap) | de vormen als gegevens in `site/src/lib/platen.js` (uitgeschreven naar `factiz_site/static/platen.json`), getekend door `site/src/components/site/Plaat.jsx`, de stijl `.plaat` in `site/src/styles/site.css` |
| het deelplaatje per factcheck (34.2aq) | `factiz_site/deelbeeld.py` (Pillow), `deelgegevens` en `deelbeeld_bytes` in `factiz_site/app.py`, het lettertype in `factiz_site/fonts/`, het adres `site/src/pages/deelbeeld/[taal]/[bestand].js`, `og:image` in `site/src/layouts/Site.astro` |
| de contextkaarten naast een factcheck (34.2an) | `context` in `/api/<taal>/factcheck/…` (`app.context`, `db.dossier_jaren`), `site/src/components/site/ContextKaarten.astro`, het kaartje in `site/src/lib/kaartje.js` |
| de wereldkaart (34.2am) | `doublecheck/wereldkaart.py` (projectie en vereenvoudiging), `site/src/kaart/wereld.json`, de kaart in `site/src/components/site/paginas/Verkennen.astro`, `waar.kaart` en `waar.legenda` in `/api/<taal>/verkennen` |
| het logo en zijn beelden | `doublecheck/merkbeelden.py`, `factiz_site/static/merk/`, `factiz_site/static/merk/woordmerk-inline.svg` |
| besluiten per pagina, principes, ontwerpchecks | `docs/DESIGN.md` |
| de pagina's en de talen (34.2c, 34.2f) | `site/src/pages/[...pad].astro` (de router voor vijf talen), `site/src/components/site/paginas/` (de pagina's), `site/src/lib/talen.js` (adressen per taal), `site/src/lib/weergave.js` (licht en donker) |
| welke talen een pagina eigen tekst geeft | `factiz_site/i18n.py` (`eigen_talen`), in de gegevens van `/api/<taal>/factcheck/…` als `vindbaar` |

## 6. Talen, adressen en vindbaarheid *(34.2c, PO 2026-11-12)*

Er komen veel talen bij, en veel factchecks gaan over hetzelfde bericht in een ander jasje, of zijn een vertaling. Hier ligt
vast hoe een adres eruitziet en welke pagina een zoekmachine te zien krijgt. De bronnen staan onderaan, nagelezen op
2026-11-12.

**Het adres.**
- Eén adres per pagina per taal. De taal is de eerste map: Engels op de hoofdmap (`/fact-checks/7726…/`), elke andere
  taal onder haar code (`/nl/fact-checks/7726…/`, B74). Google raadt een eigen adres per taal aan; mappen zijn daarvoor
  goed, een taal in een parameter (`?taal=nl`) niet [2].
- Het pad na de taal is in elke taal hetzelfde: Engelse woorden en het nummer van de bewering. De taalkiezer verwisselt dus
  alleen het voorvoegsel, en een link blijft heel als er een taal bijkomt.
- Codes volgens BCP 47: in het pad in kleine letters (`pt-br`, `zh-hant`), in `lang` en `hreflang` zoals de standaard ze
  schrijft (`pt-BR`, `zh-Hant`).
- `/en/…` is geen tweede adres: het stuurt blijvend door naar de hoofdmap.
- Nooit een andere taal op hetzelfde adres door een cookie, het IP-adres of de taal van de browser, en nooit vanzelf
  doorsturen naar een andere taal [2]. Wie binnenkomt, kiest zelf.

**In stappen open** *(34.2bt, PO 2026-11-16: "In two steps", 2026-11-17: de eerste stap volgens B73)*. `FACTIZ_VINDBAAR`
heeft vier standen: 0 dicht; 1 alleen de kern (meer dan één redactie, *Ook gecheckt door* of in een dossier, B73 punt 5);
2 elke factcheck; 3 alles wat hieronder vindbaar heet. In stand 1 en 2 is een factcheck één keer vindbaar: in de taal van
haar bewering, of waar `x_default` heen wijst als dat geen sitetaal is (`site/src/lib/vindbaar.js`, `aanbodFactcheck`);
haar `hreflang` noemt dan alleen die versie, en elke andere versie zegt `noindex` tot stand 3. De vaste pagina's,
overzichten, thema's, dossiers en het register van namen zijn in elke open stand in elke taal vindbaar.

**Wat een zoekmachine van een bewering ziet** *(34.2bw, de juridische verkenning van 2026-11-17)*. De titel begint met het
oordeel en zet de bewering, hoogstens 45 tekens, tussen de aanhalingstekens van de taal (`factcheck_titel`: "False
according to Snopes: “Zelensky bought a villa in Florida”", het stempel met hoogstens één naam, DESIGN §4y); de
omschrijving begint met het oordeel en noemt de bewering niet; de kale
bewering (de kop, het origineel, de bewering in een rij) draagt `data-nosnippet`. Een pagina per naam (`/names/Q…/`) zegt
`noindex` en staat niet in de sitemap tot een jurist haar bekeek (`NAAMPAGINAS_VINDBAAR`). Een afgeschermde factcheck
(`vindbaar.afgeschermd`, de tabel `afscherming` van de uitgave: een privépersoon in een gevoelige context, of nog niet
gelezen, SPECS E9.S8 AC13) gaat in geen open stand naar een zoekmachine. Een naam die Factiz bewust weglaat, is op de pagina een sticker
*naam weggelaten** (`.fz-weg`, `--markeer`, nooit een zwarte balk) met de reden als voetnoot onder de bewering. De sitemap per taal (`/sitemap.xml`) volgt dezelfde regel, uit de ingang
`/api/<taal>/sitemap`; robots.txt sluit in een open stand alleen de interne paden en de lijsten met filters.

**Wanneer een pagina in een taal vindbaar is.** Google telt vertaalde pagina's niet als kopie, behalve als de hoofdinhoud
onvertaald blijft ("the main content of the page remains untranslated" [1]). Bij ons is de hoofdinhoud de bewering. Dus:
- Een factcheck is vindbaar in de taal van de bewering zelf en in elke taal van de site waarin er een vertaling van ligt
  (`i18n.eigen_talen`). Ligt er geen, dan alleen op de hoofdmap.
- Alleen die talen staan in `hreflang`, elk met zichzelf en alle andere erin, plus `x-default`: wederkerig, anders negeert
  Google ze [1].
- In de andere talen bestaat de pagina voor bezoekers (menu en knoppen in hun taal, de bewering in het origineel of in het
  Engels), met `noindex` en zonder canonical. Een canonical naar een andere taal hoort niet [4], en een kopie aanbieden ook
  niet.
- Zijn het er meer dan tien talen, dan gaan de `hreflang`-regels naar de sitemap in plaats van de kop van elke pagina;
  Google ziet de kop, een HTTP-header en de sitemap als gelijk [1], en de pagina blijft licht.

**Hetzelfde bericht in een ander jasje.**
- Dezelfde bewering van meer redacties is al één pagina: het lab voegt ze samen (één pagina per bewering of cluster,
  E9.S1), met alle redacties erbij.
- Een andere versie van hetzelfde bericht (andere woorden, een andere taal, een andere redactie of datum) is een eigen
  pagina met zichzelf als canonical, en de versies wijzen naar elkaar (*Komt ook voor als*, E9.S7). Een canonical naar een
  hoofdversie zou zeggen dat het dezelfde pagina is, en dat is het niet: een andere tekst, een ander oordeel, een andere
  bron.
- Twee vindbare pagina's met dezelfde bewering in dezelfde taal zijn een fout van het samenvoegen, geen zaak voor een
  canonical.

**Factiz Radar, de eigen checks** *(PLAN #37.11, SPECS E10.S4 AC6 tot AC8, PO 2026-11-21)*.
- Het adres draagt het jaar en de maand van publicatie en een korte naam van de bewering: `/nl/radar/2026/11/klaver-citaat-privebezit/`.
  De naam staat in de check (`adres`, in de taal van de check, in Latijnse letters); elke vertaling draagt de Engelse
  naam (`adres_en`): `/radar/2026/11/klaver-quote-abolish-private-property/`. `/radar/2026/` en `/radar/2026/11/` zijn de
  Radar van dat jaar en die maand, met de maanden in de zijkolom. Een werknaam of de naam van een andere taal stuurt
  blijvend door (301).
- Vindbaar: het origineel, en een vertaling die de redactie las (`eigenvertaling nagelezen`); die zegt *Machine translation
  from Dutch, reviewed by our editors*. Canonical naar zichzelf, `hreflang` naar elke vindbare taal, `x-default` naar het
  Engels als dat vindbaar is. Een ongelezen vertaling zegt `noindex` en heeft geen canonical; een concept nooit iets.
- Elke vindbare check en de Radar met haar jaren en maanden staan in de sitemap van hun taal (`<taal>-vast.xml`), met de dag
  van publicatie; `uitrol live` meldt nieuwe en gewijzigde checks bij IndexNow.

**Lijsten, filters en bladeren.**
- Vindbaar: de hele lijst en de lijsten met een eigen pad, één per ingang (een thema, een dossier, een redactie, een naam).
  Bladeren gaat met gewone links (`?p=2`), elk blad met zichzelf als canonical; `rel=next` en `prev` gebruikt Google niet
  meer [5].
- Niet vindbaar: een lijst met filters (`?taal=`, `?oordeel=`, `?jaar=`, `?land=`) of een andere volgorde (`?sorteer=`).
  Google raadt daarvoor eerst `robots.txt` aan [3]: bij de livegang (#33.9) een `Disallow` op die parameters, en de pagina
  zelf zegt `noindex`. Zoeken gaat met een gepost formulier en heeft dus geen adres.
- *Meer laden* is in de pagina een gewone link naar het volgende blad; met script haalt dezelfde link de rijen erbij.
  Google volgt links, geen knoppen [5].
- Richting B gebruikt voor een thema nog `?thema=` op de bibliotheek. In het platform in Astro krijgen thema, onderdeel,
  land, redactie en naam elk een eigen pad, zoals het platform nu al heeft (`/themes/health/`).

**Wat een zoekmachine en een taalmodel lezen.**
- De server levert de hele pagina af; alles staat er ook zonder script.
- Bovenaan elke factcheck in gewone tekst: de bewering, het oordeel met de naam van de redactie, de telling en de link naar
  haar factcheck; daarna de bronnen met hun datum. Zo is de kern te citeren zonder er iets bij te bedenken.
- *Gevonden op een vraag eromheen (34.2m).* Wie zoekt op "is it true that…", "did … really" of "is … a hoax", krijgt van de
  zoekmachine treffers op de bewering zelf; de vraagvorm valt weg. Dus per factcheck: een titel met de bewering (op een
  heel woord, hoogstens 60 tekens) en het label; een omschrijving met het antwoord eerst, wie en wanneer; en direct onder de
  bewering de kop *Is it true?* met het label en één zin over wie checkte en wanneer. Dat stuk citeren AI-zoekers. Geen
  lijsten met vraagvormen of trefwoorden als *hoax*.
- Gestructureerde gegevens alleen voor wat we zelf zijn: de pagina als `WebPage` met de bewering als `Claim` en de artikelen
  van de redacties als `citation` (met hun naam als auteur), en het kruimelpad. Geen `ClaimReview`: die hoort bij de
  redactie die de check deed, en Google toont haar sinds juni 2025 niet meer in de zoekresultaten [6].
- `lang` op de pagina en op elk stuk tekst in een andere taal: de bewering, het origineel, het oordeel van een redactie.

**De taalkiezer.**
- In de kop op elke breedte: een wereldbol met de code van de huidige taal. In de voet dezelfde lijst als gewone links,
  ook voor wie geen script heeft.
- De namen in hun eigen taal (*Deutsch*, *Español*), geen vlaggen: een vlag is een land, geen taal [7]. Vooraan in een
  vaste kolom de code (*DE*, *ES*), zoals op de knop; de naam in de taal van de pagina staat er niet meer onder (34.2af).
  De huidige taal aangevinkt. Vanaf negen talen een zoekveld, dat ook zoekt op de code en op de naam in de taal van de
  pagina. De knop: wereldbol, code en een pijltje.
- *De volgorde (34.2bi):* in elke taal van de site dezelfde, zodat je je taal op dezelfde plek terugvindt: op de code
  (AR, DE, EN, ES, FA, FR, HI, ID, JA, NL, PT, RU, TR, UK, ZH), zoals de taalkiezer van het W3C. De code staat vooraan op
  elke regel en op de knop, dus die kolom loopt van A tot Z; geen taal of schrift gaat voor, en *Bahasa Indonesia* staat
  niet bovenaan omdat haar naam met een B begint (PO 2026-11-15: "Op code"). In de kiezer en in de voet dezelfde. Bovenaan, onder
  *Voorgesteld*, hoogstens drie talen die de browser van de bezoeker zelf noemt en die niet de huidige zijn, met daaronder
  *Alle talen*; gelezen in de browser (`navigator.languages`), niets naar de server en niets bewaard (B78). Elke variant
  van een taal telt (`pt-PT` wijst naar het Portugees van Brazilië, elke `zh` naar traditioneel Chinees). Tijdens het
  zoeken alleen de treffers.
- Elke keuze is een gewone link naar dezelfde pagina in die taal, met `hreflang` en `lang`, niet naar de voorpagina. De
  filters gaan mee; een zoekvraag niet, want die staat nergens in een adres.

**Licht, donker, systeem.**
- In de voet een keuzelijst: *Systeem*, *Licht*, *Donker*; standaard *Systeem*, dat de instelling van het apparaat volgt.
- Een keuze voor licht of donker onthoudt de browser van de bezoeker zelf (`localStorage`, één sleutel:
  `factiz-weergave`); ze gaat nooit naar de server, en *Systeem* wist haar weer. Een klein stukje script in de kop zet de
  keuze vóór het tekenen, zodat de pagina niet eerst in de verkeerde kleur verschijnt.
- Bij de knop staat *Alleen op dit apparaat onthouden*, en de privacypagina zegt het in vijf talen
  (`over_privacy_weergave`); `tests/test_site_opslag.py` weigert elke andere opslag in de browser.
- *Besloten (34.2g, B75 aangevuld op 2026-11-12):* een instelling die de bezoeker zelf kiest, is geen gegeven over de
  bezoeker, met de voorwaarden uit de Europese en Nederlandse regels; bronnen in
  `docs/voorstellen/2026-11-12-b75-instellingen.md`. Recent bekeken en een zoekgeschiedenis blijven verboden, ook in de
  browser.

**Bronnen.**
1. Google Search Central, *Tell Google about localized versions of your page*,
   https://developers.google.com/search/docs/specialty/international/localized-versions
2. Google Search Central, *Managing multi-regional and multilingual sites*,
   https://developers.google.com/search/docs/specialty/international/managing-multi-regional-sites
3. Google Search Central, *Managing crawling of faceted navigation URLs*,
   https://developers.google.com/search/docs/crawling-indexing/crawling-managing-faceted-navigation
4. Google Search Central, *How to specify a canonical URL*,
   https://developers.google.com/search/docs/crawling-indexing/consolidate-duplicate-urls
5. Google Search Central, *Pagination, incremental page loading, and their impact on Google Search*,
   https://developers.google.com/search/docs/specialty/ecommerce/pagination-and-incremental-page-loading
6. Google Search Central Blog, *Simplifying the search results page*, 12 juni 2025,
   https://developers.google.com/search/blog/2025/06/simplifying-search-results
7. W3C Internationalization, *Language negotiation and links*, https://www.w3.org/International/questions/qa-site-conneg
