# Doublecheck

De resolver-laag voor factchecks: geef een artefact uit het wild (screenshot, tekst,
URL) en krijg terug of die claim al gecontroleerd is, door wie, en wat eruit kwam.
Volledige context: `docs/REQUIREMENTS.md`.

## Projectdocumenten
- `docs/REQUIREMENTS.md` — waarom (doelen, gebruikers, scope, besluitlogboek B1–B76) · eigenaar: PO
- `docs/V1-ROUTE.md` — wat V1 is (de factcheckmachine, B46) en de technische stappen ernaartoe · eigenaar: PO
- `docs/SPECS.md` — wat (epics, stories, acceptatiecriteria, domeinregels DR1–DR10) · eigenaar: PO
- `docs/DESIGN.md` — hoe het voelt (principes, stromen, ontwerpchecks D1–D8) · eigenaar: Designer
- `docs/DESIGNSYSTEEM.md` — het ene document dat het uiterlijk koppelt: de oppervlakken, de bouwstenen (Astro,
  React, Tailwind, Radix, shadcn/ui; B75, B76), de tokens, de onderdelen, de velden en waar dat in de code staat; begint
  hier wie een pagina maakt · eigenaar: Designer
- `docs/PLAN.md` — etappes & taken; werk één taak per keer, in volgorde · eigenaar: Lead Dev
- `docs/PROTOCOL.md` — het resolverprotocol dat een standaard moet worden;
  *concept, nog geen besluit*; **in het Engels, en de Engelse tekst is
  normatief** (#23.12): wie het protocol wijzigt, schrijft Engels en houdt
  de §-nummers vast · eigenaar: PO
- `docs/KENNISBANK.md` — feiten en cijfers met bron voor blogs over online factchecken; alleen uit een
  nagelezen bron of een eigen meting, en eigen metingen pas naar buiten met de PO · eigenaar: PO
- `docs/ARCHITECTUUR.md` — de architectuur van de zeef: vijf lagen, de
  stack, de rekenkracht in fases en de volgorde; *besloten 2026-10-17
  (B35–B38)* · eigenaar: Lead Dev
- `docs/RELEASES.md` — wanneer iets een versie is, het releaseproces en de
  kaart van de huidige release *(B22)* · eigenaar: PO
- `docs/voorstellen/2026-11-10-platform-bouwplan.md` — het bouwplan van het platform (factchecks, dossiers, thema's,
  rapporten; B71–B74); de stappen staan in PLAN, etappe 33 · eigenaar: PO
- `docs/RESEARCH.md` — wat de wereld al weet over factcheckmachines:
  benchmarks, beste werkwijzen, diensten en audits van chatbots, elk met bron,
  en wat het voor Factiz betekent · eigenaar: PO

## Tech stack
- Python 3.12 (**niet** de systeem-3.9 van macOS)
- FastAPI + uvicorn
- `sentence-transformers` — meertalige tekst-embeddings, lokaal
- `transformers` + een meertalig NLI-model — relatie-oordeel, **uitsluitend offline
  in clustering**; te traag en te grof voor het aanvraagpad (BENCHMARK.md §15)
- `pdqhash` + Pillow — perceptuele beeldhashes (PDQ, 256 bits). `imagehash`
  blijft voor de pHash-versies: die zijn gemeten en gedocumenteerd, niet dood
  gewicht. **Drempel en hashversie wisselen altijd samen** — 31 van 256 hoort
  bij PDQ, 10 van 64 hoorde bij pHash *(#4P.3)*
- `pytesseract` + Tesseract — OCR (**ook `brew install tesseract-lang`**: de
  basisformule levert alleen Engels, geen `nld`)
- `py3langid` — taalherkenning over 97 talen, offline in de corpusroute. Onze
  eigen `taal.py` blijft voor de cross-linguale paarbeslissing: die is op díé
  taak gemeten *(#12.4)*, en 97 talen zijn daar niet nodig *(#14.6)*
- SQLite + numpy — opslag en brute-force vectorzoek (geen aparte vectordienst in v1)
- **Het platform (B71–B74, PLAN etappe 33), in aanbouw:** het lab maakt per release een publicatiedatabase met alleen
  wat gepubliceerd mag worden (`python -m doublecheck.publiceren`, SPECS E9.S1); een kleine web-app in Python
  (`factiz_site/`: Starlette, sinds #34.2f stap 4 alleen ingangen onder `/api/<taal>/`, geen inlog) leest alleen dat
  bestand, in vijftien talen (B79; Engels op de hoofdmap). Zoeken met de woordzoeker van SQLite (FTS5). `factiz_site`
  leent niets uit `doublecheck`; de database is het contract. De voorkant is de site in `site/` (Astro, B76); de oude
  `web/` is weg sinds #34.2f. **Sinds B80 (PLAN 34.2bo) leest de site de uitgave zelf**, met het platform in TypeScript
  (`site/src/platform/`, aangeroepen in `site/src/lib/platform.js`): in Node op het SQLite-bestand (`FACTIZ_PUBLICATIE`,
  anders de nieuwste uitgave), als Cloudflare Worker op D1. Elke ingang geeft hetzelfde als de Python-app, die blijft als
  maatstaf (`python -m factiz_site.gelijk*`); het lab en `publiceren` blijven Python. B21 geldt alleen nog voor wat mensen
  insturen. Geen handeling op het Cloudflare-account zonder een ja van de PO
- **Besloten, nog niet gebouwd (B36–B38):** een lokale rechter als tweede stap
  (#30.3), ANN-indexen op schijf per index en modelversie (#30.7), PDQ én
  DINOv2 in productie (#30.4a), een batchpad met dezelfde functies (#30.8);
  video en spraak (faster-whisper, ffmpeg) in V2
- **De controle per bericht, gebouwd, staat uit (B51, #32.10):** `POST /check`
  is de simpele versie (`doublecheck/zoekcontrole.py`, gemeten in BENCHMARK §179).
  1. Eerst kring 1: een check uit de database die één kant op wijst, geeft het
     antwoord meteen, zonder model (`api.los_op`, dezelfde categorie als `/resolve`).
  2. Anders één zoekvraag bij Brave (`zoeker = "brave-v1"`, sleutel in `.env` als
     `BRAVE_API_KEY`), top 10, met per resultaat de band uit de bronnenlijst
     (`bronnen.py`). Een pagina van factiz.org telt nooit als bron (`zoekcontrole.van_factiz`, #32.68: geen
     kringloop zodra Factiz zelf publiceert).
  3. Sonnet 5.5 leest het bericht, de resultaten en de 5 checks uit de database die
     het meest op het bericht lijken (`lezer = "lezer-v18"` sinds 2026-11-09, vast JSON-schema, zoekt
     niet zelf; `api._checks_uit_database`). Bij `lezer-v9` (B57, #32.41) bedenkt Haiku 5.5 vooraf tot
     drie zoekvragen (`speurvraag_model`, `speurvraag.py`: eigen site, echt nieuws, bron zelf), die met het
     bericht tegelijk naar Brave gaan, en leest Sonnet één keer; *niet bevestigd* is de tiende uitkomst. Hij zegt *klopt*, *klopt niet*,
     *misleidend*, *onzeker*, *klopt grotendeels*, *geen bewering* of *satire*, per check
     of die over dezelfde bewering gaat, met `over_beeld` of de bewering gaat over wat
     een beeld toont, en met `vorm` of het bericht meldt wat een ander beweert (#32.31,
     #32.32, BENCHMARK §207, §208; een tussenrelease op 2026-11-03, B53). Een check over
     dezelfde bewering met onwaar of misleidend telt als goede tegenspraak.
     `zoekcontrole.na_lezen` zet daaruit een van de negen uitkomsten (`outcome` in
     `POST /check`, met `correction` bij *klopt grotendeels* en `claim_colour` bij een
     bericht over een bewering van een ander).
  4. De bronnenlijst beslist:
     - rood of oranje alleen met een goede tegenspraak;
     - groen met twee verschillende goede uitgevers, of één goede plus één
       andere die niet laag, geen platform en geen staatsmedia is;
     - een bewering over wat een beeld toont, zonder het beeld nooit groen;
     - anders geen kleur. Bronnen van staatsmedia krijgen een label
       (`staatsmedia.json`).

  `lezer-v1` (§179), `lezer-v2` (§181), `lezer-v3` (§182), `lezer-v5` (§201, §206), `lezer-v6` (§207) en `lezer-v7` (§208, §209) blijven in
  de code voor de metingen. `lezer-v8` (#32.40, §217) zoekt zelf verder zoals een factchecker (de speurstap,
  `zoekcontrole.speur`, achter `[berichtcontrole] speuren`, standaard uit); gemeten, nog niet in config. `lezer-v9` (#32.41, B57, §219, §220) leest één keer: Haiku bedenkt vooraf de
  zoekvragen (`speurvraag.py`, `[berichtcontrole] speurvraag_model`), alles tegelijk naar Brave, en *niet bevestigd*
  als tiende uitkomst; in config van de tussenrelease van 2026-11-05 tot die van 2026-11-08. `lezer-v4` (#32.13, §183) geeft het antwoord in twee lagen (`feit_van`, `anders_van`: wat
  klopt en wat er echt gebeurde, `fact` en `what_happened` in `POST /check`); gemeten, nog niet in config.
  `lezer-v10` (#32.43) stelt de vraag van v9 en zegt daarna geen *niet bevestigd* bij oud nieuws (het nieuwste jaartal
  in het bericht drie kalenderjaren terug, `oud_jaartal`) of bij een onafhankelijke bevestiging zonder band
  (`bevestigd_zonder_band`), §223, §224; `onbevestigd_weg` zegt welke regel het deed. Gebouwd, niet in config; gemeten
  met `docs/meetplannen/32.43-<taal>.json`.
  `lezer-v11` (#32.46) is v10 plus: een echte kop die woord voor woord op de eigen site van het genoemde medium staat
  (`zoekcontrole.eigen_kop`, `MEDIA`), met band *goed*, mag groen worden (§232). Gebouwd, niet in config.

  `lezer-v12` (#32.49) is v11 met een uitleg die helpt: drie tot vijf feitelijke zinnen in plaats van één, en ook bij een
  check uit de database leest de lezer mee voor de uitleg (`zoekcontrole.met_uitleg`; de kleur blijft van de check, en
  is de lezer het oneens, dan blijft de zin van de redactie). Gebouwd na het duel met Gemini (BENCHMARK §235), niet in
  config.
  `lezer-v13` (#32.51) is v12 met de uitleg die meteen met het oordeel en de kern begint, en B60: een echte kop die woord
  voor woord op de eigen site van het genoemde medium staat, is *klopt* en groen in plaats van *geen bewering*
  (`zoekcontrole.echte_kop_klopt`, `kop_treffers`); "de database" gaat uit de uitleg (`zonder_database`). Gebouwd, niet in
  config.
  `lezer-v14` (#32.56, B61) is v13 met één goede bron genoeg voor groen (regel `een` in `zoekcontrole._gedragen`), als
  de lezer *klopt* zegt, niets het tegenspreekt en het niet over een beeld gaat. Gebouwd, niet in config.
  `lezer-v15` (#32.56, §240) is v14 met elke zin van de uitleg aan het nummer van zijn bron ([n], [Dk]); `met_bronnen`
  laat een zin zonder geldig nummer, of met een medium dat niet in zijn bronnen staat, weg (een nummer ná de punt hoort bij de zin ervoor, §241); en bij B61 telt het bericht
  zelf niet als de ene goede bron (`zelfde_artikel`). Gebouwd, niet in config.
  `lezer-v18` (#32.54, §249) is v17 met een eerste zin van de uitleg die bij de uitkomst past (`zoekcontrole.eerste_zin`);
  dezelfde vraag aan het model. **In config sinds de tussenrelease van 2026-11-09** (PO: "yes"), samen met de foto bij de
  bron (`fotobron.py`, `[berichtcontrole] fotobron = "fotobron-v2"`, B66, DESIGN §4m, §248, §249): groen bij een foto alleen
  als een bevestigende goede of officiële bron haar toont, anders *foto niet bij de bron* in twee lagen
  (`zoekcontrole.foto_bij_bron`, ook voor een groen uit de database). Sinds een tweede tussenrelease die dag de bronnenlijst
  `bronnen-v7` (B69, PO: "Ja, release v7"): verhuisde media houden hun oordeel (`bronnen.reden` leest door "verhuisd van" heen).
  `lezer-v16` (#32.56, §243) is v15 met de getallenregel: een getal in een zin van de uitleg moet in de aangewezen bron of het
  bericht staan (`zoekcontrole._getallen_kloppen`); de uitleg rust voor ~96% op wat Factiz las. Gebouwd, niet in config.
  `lezer-v17` (#32.64, §247) is v16 met het vaste deel van de vraag vooraan in het systeembericht, bewaard tussen vragen
  (prompt caching, ~15–20% goedkoper bij Sonnet), en zinnen die niet breken na een initiaal. **In config sinds de
  tussenrelease van 2026-11-08** (PO: "dat mag"), met `bronnen-v6`, tot die van 2026-11-09 (`lezer-v18`).
  De gemaskeerde tekst gaat naar Brave en het model (`berichtcontrole.bericht_uit`); het beeld gaat alleen mee met
  `[berichtcontrole] beeld = true`: besloten in B55 (altijd mee, zonder goedkeuring per controle, eerst zwart wat de
  tekstherkenning vindt), aan sinds de tussenrelease van 2026-11-03 (#32.36, BENCHMARK §212). Naar Brave gaat alleen de
  tekst.
  Brave is de zoekdienst in het product, met het gewone plan (B52). De oude keten (vraag v4 met
  webzoeken, vormvraag, detailvraag, vloer, herkomst, feitenstap, meter) staat
  nog in `berichtcontrole.beoordeel`, alleen voor de metingen.
  Zero data retention is geen voorwaarde meer voor `[berichtcontrole] aan` (B54): de standaard van Anthropic,
  hoogstens 30 dagen en geen training. Nog nodig voor aanzetten: de steekproef op het maskeren (B43) en de livegang.
- Rekenkracht *(B37)*: eerst de Mac (M1, 16 GB); embedden mag op de grafische
  chip (`device="mps"`, dezelfde vectoren); de cloud alleen per run die langer
  duurt dan een nacht of niet in 16 GB past, met een budget vooraf
- pytest

## Commando's
- Eén lokale preview (PO 2026-11-23: "zullen we al deze lokale servers even versimpelen tot 1 lokale preview"): `factiz` in
  `.claude/launch.json`, poort 8796: de site op wat het laatst gebouwd is (`data/voorbeeld/publicatie.db` of de nieuwste
  uitgave in `data/publicatie/`); na `npm --prefix site run build` of een nieuwe bouw opnieuw starten. De Worker lokaal:
  `npm --prefix site run worker:lokaal` (poort 8795).
*(alles geverifieerd t/m taak 2.8, behalve `benchmark` — die module bestaat pas na
taak 3.3. `ingest` vereist `GOOGLE_FACTCHECK_API_KEY` in `.env`)*
- Omgeving: `source .venv/bin/activate`
- Server: `uvicorn doublecheck.api:app --reload`
  *(`GET /.well-known/doublecheck` geeft schema's, drempels en scope;
  `POST /resolve` accepteert `image_fingerprint` zodat het beeld op het
  apparaat van de gebruiker blijft — PROTOCOL §3 en §4; `GET /ask` is Ask
  Factiz, `POST /ask` de vraag in de body, geen PROTOCOL-onderdeel, #24.10; `GET /check` is de controlepagina, `POST /check` de controle per bericht, standaard uit, #31.12–#31.13)*
- Tests: `pytest`
- Eén test: `pytest -k <naam> -v`
- Benchmark: `python -m doublecheck.benchmark` *(`--sweep` voor de matchdrempel,
  `--related-sweep` voor de afruil achter `text_related`; geen van beide wijzigt
  config)*
- Gemengde benchmark (beeld én tekst): `python -m doublecheck.benchmark_mixed`
  *(synthetisch; meet het samenspel van de routes, niet de dekking op wildbeelden)*
- Corpus bouwen vanaf nul: `python -m doublecheck.bootstrap` *(`--plan` zegt eerst
  wat het kost, `--max N` voor een snelle proef, `--herkomst` meldt of de
  database uitgegeven mag worden; haalt de feed zelf op, dus dit is het
  commando voor een schone kloon)*
- CC BY-corpus importeren uit een reeds gedownloade feed:
  `python -m doublecheck.feed --bestand data.json`
  *(`--alleen-talen` doet alleen de taalanalyse; herkomst wordt per record vastgelegd)*
- Corpus importeren: `python -m doublecheck.ingest --markt nl|es`
- Herindexeren na een fingerprintwissel: `python -m doublecheck.reindex [--grafische-chip]`
  *(additief en hervatbaar; werkt op de opgeslagen claimtekst, niet via de API. `--grafische-chip` embedt op mps,
  dezelfde vectoren en twee keer zo snel (B37, #32.38); de server blijft op de processor.
  Herziet ook de taallabels én de oordelen; `--alleen-talen` en
  `--alleen-oordelen` slaan het herembedden over)*
- Verlopen artefacten wissen: `python -m doublecheck.retention`
  *(de draaiende server doet dit zelf bij opstart en elke `sweep_interval_hours`;
  dit commando is de vangnet-variant voor cron of een handmatige controle)*
- Taalgeschiktheid meten: `python -m doublecheck.taalgeschiktheid`
  *(meldt talen die het model niet kan onderscheiden en nog niet vastliggen;
  `--feed <bestand>` meet op ruw feedmateriaal, vóór de import — de enige manier
  om een nieuwe taal toe te laten, want de index is een gemeten witte lijst)*
- Uitgeverkwaliteit meten: `python -m doublecheck.uitgeverkwaliteit`
  *(meldt uitgevers waarvan de eigen claims op elkaar lijken; lees de claims
  vóór je iets weert — de maat vindt rommel én sjabloonmatige huisstijl)*
- Modellen vergelijken: `python -m doublecheck.modelmeting` *(voorronde op de
  natuurlijke parafrasen, alle kandidaten in één vaste pool, vergeleken bij
  gelijk foutniveau; `--volledig <model>` meet één kandidaat op het hele corpus
  in een kopie van de database, met eigen drempels binnen het huidige
  foutbudget. Raakt config en productie-index niet; een herindex blijft een
  release, B22)*
- De velden van de site: `python -m doublecheck.velden [tellen]` *(#23.14, DESIGN
  §4h: tekent de wazige kleurvelden met filmkorrel en `delen.jpg` in
  `factiz_site/static/beeld/`, met `HERKOMST-basis.md`; vaste seed per veld, dus hetzelfde
  commando geeft hetzelfde beeld; `tellen` zet de checks per taal en maand voor
  het veld corpus in `doublecheck/velden_corpus.json`, alleen lezen;
  `tests/test_velden.py` tekent elk veld opnieuw en meet wit in de tekstzones)*
- Claimvarianten voor het hele corpus: `python -m doublecheck.variantenbatch
  plan|indienen|ophalen|embedden|meten` *(offline, Batch API met de sleutel uit
  `.env`; eerst een proefbatch, dan alleen binnen `--budget`; vectoren blijven
  buiten de productie-index tot de meting en een release, #25.17)*
- De screenshots in factcheckartikelen lezen: `python -m doublecheck.artikelbeelden
  proef|embedden|meten` *(OCR per schrift; zelfde meting als de varianten, #25.12)*
- Ruwe beeldtest: `python -m doublecheck.ruwetest --m4fc data/extern/m4fc`
  *(`--herbekijk <uitkomsten>` zet elke fout naast de verwachte claim, #25.10)*
- Netwerktoets: `python -m doublecheck.netwerktoets` *(propaganda-artikelen uit
  EUvsDisinfo tegen hun ontkrachting, #28.5; een toets stopt bij elke fout van de
  resolver in plaats van hem als "niets" te tellen)*
- Beelden uit factcheckartikelen: `python -m doublecheck.beeldindex oogsten|meten`
  *(alleen de PDQ-hash, nooit het beeld; per host één verzoek, robots.txt;
  hervatbaar; pilot #25.11, niet opgeschaald, BENCHMARK §88)*
- Kaders, stempels, uitsneden: `python -m doublecheck.kadermeting` *(de knipregel
  en de indexuitsneden van #26.3 op de M4FC-beelden; kader B en C zag de regel
  nooit, niet bijstellen na een uitslag)*
- Stiltetoets voor beelden: `python -m doublecheck.beeldstilte ophalen|meten|tellen`
  *(de rest van M4FC, memes op gedeelde sjablonen en foto's van één
  gebeurtenis door de vier beeldroutes van de kadermeting; tellen weigert
  zolang een treffer geen label heeft, #26.3, BENCHMARK §93)*
- Tekstregel voor beeldtreffers: `python -m doublecheck.beeldtekstmeting ophalen|meten`
  *(een beeldtreffer telt alleen als de gelezen tekst klopt; gemeten op de
  sjablonen 51 tot 100 en op de kopieën van §92, #26.3)*
- De radar van de eigen redactie (#37.1, B82; per taal sinds B85, #37.7; alleen de Engelse lijst sinds B89): `python -m doublecheck.radarlijst ophalen|lijst [--taal alle|nl,en] [--lijsten en] [--melding] [--tot JJJJ-MM-DD]|tip
  "<wat er rondgaat>" [--link <adres>]|weg <nummers> [--taal en] [--tot JJJJ-MM-DD]` *(sinds B89 komt alleen de Engelse lijst op schijf, waaruit Claude de 20 beste overhoudt en de PO kiest; de andere talen leest de radar voor *ook in*; `weg` haalt onderwerpen uit de lijst van
  een week, nummert de rest opnieuw en onthoudt hun posts en notes in `data/radar/weg.jsonl`, zodat ze niet terugkomen)* *(de nieuwste export van de Community Notes van X (~730 MB, hoogstens twee blijven staan),
  dan per taal van de site de notes van de laatste zeven dagen per bewering en per onderwerp (de taal als benadering van de
  regio: X geeft geen land), met posts, bronnen, een link naar een factchecker, of het ook in een andere taal rondgaat, of de
  note over beeld of video gaat, en de dichtste check in het archief, in `data/radar/lijst/<dag>.md` (Nederlands) en
  `<dag>-<taal>.md`, hoogstens 40 onderwerpen, met voorop wat nog niemand checkte, in meer talen rondgaat en beeld heeft
  (`rangorde_radar`), en `<dag>-talen.md` met wat in de meeste talen tegelijk rondgaat; lokaal met bge-m3, een
  notetekst nooit naar een externe dienst of de site; een tip zonder wie hem stuurde; elke zondag om 22:00 met
  `deploy/org.factiz.radar.plist`; `--tot` maakt de lijst van een eerdere week uit dezelfde export; $0)*
- De eigen checks vertaald (#37.8, B85): `python -m doublecheck.eigenvertaling plan|indienen [--proef N]|ophalen [--wacht M]`
  *(Sonnet via de Batch API, per check en taal één bestand `content/redactie/<sleutel>/vertalingen/<taal>.json` met de
  vingerafdruk van de tekst; een antwoord telt alleen met dezelfde velden, lijsten en bronnummers, zonder lang streepje en
  met elke tekst echt vertaald (`onvertaald`: niet gelijk aan het origineel en zonder het origineel erin);
  verandert de check, dan vraagt `plan` haar opnieuw; een lokale check alleen naar het Engels, een concept in een taal
  die de redactie niet leest alleen naar het Engels om na te lezen; grens $5 per week. `publiceren` neemt de geldige mee, de bewering ook in de
  tabel `vertaling`; de site toont ze onder `/<taal>/radar/` met *Machinevertaling uit het Nederlands* en de link naar het
  origineel, en zoekmachines zien alleen het origineel (`app.eigen_in`, `eigentaal.ts`); behalve een vertaling die de
  redactie las: `eigenvertaling nagelezen --sleutel a,b [--taal en]` legt dat vast met de vingerafdruk van de tekst, en die
  vertaling is vindbaar met *nagelezen door de redactie* (PLAN #37.11; een nieuwe vertaling moet opnieuw gelezen))*
- De eigen factcheck (#37.4, B82): `python -m doublecheck.redactie controleren` *(elke `content/redactie/<sleutel>/check.toml`,
  met haar adres (#37.11, PO 2026-11-21: "Jaar en maand"): `adres`, een korte naam van de bewering in de taal van de check,
  en `adres_en` voor de vertalingen; op de site `/nl/radar/<jjjj>/<mm>/<adres>/` met de maand van publicatie, en een werknaam
  stuurt blijvend door; twee checks met dezelfde naam in één maand weigert het;
  het oordeel uit de schaal, de soort en vorm van het archief, minstens twee bronnen voor de kern (een andere factchecker
  telt niet mee), elk nummer met zijn bron, een post van een privépersoon alleen als archiefkopie, het beeld dat rondgaat
  met stempel, bronregel en alt-tekst, en bij publicatie een schrijver (Claude mag, als *Claude (AI)*, B84), een menselijke
  nalezer die niet de schrijver is, niets meer in `nog_doen` en geen *[FEIT NODIG]*; wat openstaat staat als `nog_uitzoeken`
  op de pagina, met een oproep om bij te dragen; een post die weg is met `weg`, zonder kopie met de reden in `geen_kopie`; het dossier met het onderzoek in `data/redactie/<sleutel>/`, buiten git, nooit op de site; het voorstel in
  `docs/voorstellen/2026-11-18-eigen-factcheck.md`). In de uitgave (schema 13) de tabel `eigen_check`: een gepubliceerde
  check altijd, een concept alleen met `publiceren bouwen --concepten` (naar `data/voorbeeld/`); `controleren` legt elke
  check opnieuw langs de regels. Op de site als **Factiz Radar** (PO 2026-11-19), in de stijl Stempel (DESIGN §4x), onder
  `/nl/radar/`, `/nl/radar/<jjjj>[/<mm>]/` en `/nl/radar/<jjjj>/<mm>/<adres>/` (het oude `/nl/factiz-checks/` en
  `/nl/radar/<sleutel>/` sturen door), in de taal van de check en haar vertalingen, uit
  `/api/<taal>/eigen[/<sleutel>|/<jjjj>[/<mm>[/<adres>]]]` (Python en TypeScript gelijk); in het menu met een stip en op de start als ringen zodra
  een taal een gepubliceerde check heeft (`radar` in `/api/<taal>/archief`: aantal, nieuw in de zeven dagen tot de dag van
  de uitgave, de nieuwste); de ringen pulseren alleen bij iets nieuws. In het archief staat elke check ook als pagina met de redactie *Factiz*
  (bron `factiz-redactie`, `publiceren.eigen_paginas`), met het zegel in een rij; een link naar factiz.org wordt een pad op
  de site (`app._link`, `tekst.link`). Lokaal bekijken: `publiceren bouwen --concepten`, `npm --prefix site run build`,
  dan de preview `factiz` (poort 8796))*
- Het beeld bij een eigen check (#37.5): `python -m doublecheck.redactiebeeld maken [--sleutel a,b]` *(legt de post uit `data/redactie/<sleutel>/beeld.json` vast via de openbare insluitpagina van X in headless Chrome (`site/scripts/postbeeld.mjs`), zonder inloggen; het ruwe beeld alleen in het geheugen; zoals het rondging, met account en gezichten, vervaagd alleen met `vervaag` en `vervaag_reden` in de check (een minderjarige, gruwelijk beeld); zonder de knop om antwoorden te lezen, nooit met een Community Note (dan weigert het); hoogstens 640 breed met het oordeel als stempel, als JPEG in `factiz_site/static/redactie/<sleutel>/`, maat en oordeel in `content/redactie/<sleutel>/beelden.json`; `publiceren` zet pad en maat erbij (`redactiebeeld.erbij`) en weigert een stempel met een ander oordeel dan de check)*
- De voormeting voor de radar (#37.0): `python -m doublecheck.radarvoormeting notes|koppelen|lezen [--vooruit]|tellen`
  *(de Nederlandse notes uit de export van X in `data/communitynotes/<dag>/`, van een note alleen nummer, datum, status en
  vector bewaard, de tekst alleen in het geheugen; gekoppeld met bge-m3 aan de factchecks van AFP Factcheck Nederland
  (`docs/steekproeven/37.0-maatstaf.json`) en aan het archief; `tellen` weigert zolang iets geen label heeft in
  `docs/steekproeven/37.0-radar.json`; $0; BENCHMARK §261)*
- Een nieuwe uitgave per week (#35.2): `python -m doublecheck.verversen [--tot bouwen] [--melding]|stand` *(na een nieuwe
  stand van de feed in het lab: eerst de nieuwe gevallen van EUvsDisinfo (#35.3), dan bouwen, voor de nieuwe pagina's thema's, namen, vertalingen en de punten van Waarom (Batch API, hoogstens $10 per
  uitgave, `doublecheck/routinegrens.py`), opnieuw bouwen, `uitrol voorbereiden`, en `data/verversen/<dag>.md` met wat er
  nieuw is en wat het kostte; hervatbaar per stap in `data/verversen/<dag>.json`; elke dag om 7:30 met
  `deploy/org.factiz.verversen.plist`; live alleen met een ja van de PO, `uitrol live`; RUNBOOK, *Een nieuwe uitgave per
  week*)*
- EUvsDisinfo bijhouden (#35.3): `python -m doublecheck.euvsdisinfo --server` *(de nieuwe gevallen van hun MCP-server
  vanaf `euvsdisinfo.VANAF`, 2026-01-01 (PO 2026-11-23: "doe voor nu alleen 2026, de rest doen we later"), in het lab, met
  embedden; de sleutel `EUVSDISINFO_API_KEY` in `.env`; 100 per vraag, 2 s ertussen, tot de eerste dag of een bladzijde
  zonder iets nieuws; bewering en weerlegging in `data/euvsdisinfo/server.jsonl` (openbaar, buiten git), waar *Waarom het
  niet klopt* ze leest; herkomst `euvsdisinfo:mcp`, dezelfde bron in het register. De eerste stap van `verversen`; daarna
  `waarom` en `waarom-lezing` voor de nieuwe pagina's, binnen de grens van de routine)*
- De placeholder van factiz.org, ook voor onderhoud (#34.2f, stap 3b): `npm --prefix site run build:placeholder` *(één
  stille pagina uit de site, statisch: bron in `site/placeholder/`, uitvoer in `site/dist-placeholder/`, zo te uploaden naar
  Cloudflare Pages; de tekst uit de woordenlijsten (`wacht_kop`, `wacht_tekst`) in de vijf talen, het woordmerk en het veld
  corpus van de site, geen script, `noindex`; lokaal bekijken met `npm --prefix site run dev:placeholder` (poort 8798);
  `tests/test_placeholder.py` houdt haar op één pagina met alleen een mailto-link)*
- Het deelplaatje per factcheck (#34.2aq, SPECS E9.S23): het platform tekent het op verzoek (`factiz_site/deelbeeld.py`,
  `/api/<taal>/deelbeeld/<nummer>.jpg`, de site op `/deelbeeld/<taal>/<nummer>.jpg`; voor een thema, onderdeel en
  dossier `.../thema/<thema>[/<onderdeel>].jpg` en `.../dossier/<sleutel>.jpg`, #34.2ar), niets vooraf. Na een wijziging
  van de tekeningen in `site/src/lib/platen.js`: `npm --prefix site run platen` *(schrijft `factiz_site/static/platen.json`;
  `tests/test_site_platen.py` weigert als het niet meer past)*
- Tien sitetalen erbij (#34.2be, B79): de talen staan in `factiz_site/teksten/sitetalen.json`; namen van landen en talen,
  maanden en datumvorm uit CLDR met `doublecheck/cldr.swift`; de vaste teksten, thema's en dossiers met `python -m
  doublecheck.sitevertaling teksten|themas|dossiers|korter [--taal pt,ru]` *(Sonnet 5.5, direct, grens $5 per keer;
  `nagelezen: false`; een nieuwe taal mag ontbreken en valt dan terug op het Engels)*; een nieuwe vaste tekst in de tien
  talen met `aanvullen` *(alleen de sleutels die een taal mist, de rest blijft zoals het is; de vijf van B74 met de hand)*
- Bewaking van factiz.org (#34.2bv): `python -m factiz_site.bewaking [--n 12] [--zonder-d1] [--melding]` *(de vaste
  pagina's, robots.txt bij de stand en nieuwe factchecks en deelplaatjes, niet uit de cache, als robot; de storingen die de
  Worker telt (500 of hoger, `telStoring`) uit `factiz-tellingen`, alleen lezen; één regel in `data/bewaking/log.jsonl`;
  elke dag om 9:07 met `deploy/org.factiz.bewaking.plist`)*
- Open voor zoekmachines (#34.2bt, SPECS E9.S8): de stand in `site/wrangler.jsonc`, `"vars": { "FACTIZ_VINDBAAR": "0" }`
  *(0 dicht, 1 de kern van B73: meer dan één redactie, Ook gecheckt door of in een dossier, 2 elke factcheck één keer in de
  taal van haar bewering, 3 alles wat vindbaar is; `site/src/lib/vindbaar.js`, `vindbaar.kern` in de factcheck;
  elke stap een eigen ja van de PO, dan uitrollen; lokaal met `FACTIZ_VINDBAAR=1`). In een open
  stand: `/sitemap.xml` uit `/api/<taal>/sitemap` (Python en TypeScript gelijk), een open robots.txt, `/llms.txt` en het
  sleutelbestand van IndexNow; `uitrol live` meldt dan de nieuwe adressen (`doublecheck/indexnow.py`). Hoe het gaat:
  `docs/RUNBOOK.md`, *Open voor zoekmachines*.
- De site op een telefoon (#34.2by, #34.2ci): `node site/scripts/mobiel.mjs http://localhost:8796 320,414 / /fact-checks/ /#palet ...`
  *(headless Chrome als telefoon, elke pagina in een lege context: wat de pagina breder maakt dan het scherm, een veld
  onder 16 px (iOS zoomt dan in), een tikdoel onder 44 px en afgekapte tekst; `#palet`, `#menu`, `#taal` en `#filter`
  openen eerst dat venster, `#zoek=<vraag>` verstuurt het zoekformulier en meet de uitslag; een pagina zonder opmaak is een
  fout, dus meet een lange ronde op een eigen bouw (`npx astro build --outDir node_modules/.mobiel` in `site/`, met
  `FACTIZ_GA` om de vraag om te meten te zien), want een andere bouw in `site/dist` geeft de opmaak een nieuwe naam;
  `BEELD=<map>` maakt per pagina een schermafdruk; `tests/test_site_mobiel.py` houdt de
  uitkomst vast zonder browser)*
- De lettertypen van de site (#34.2bs): `npm --prefix site run lettertypen` *(schrijft `site/src/styles/lettertypen.css` uit
  de pakketten: Noto alleen voor de schriften van de sitetalen, per lettertype alleen de delen van zijn schrift; na een
  nieuwe versie van een pakket opnieuw; `tests/test_site_lettertypes.py` weigert als het niet meer past)*
- De lettertypen van het deelplaatje: `python -m factiz_site.lettertypen` *(#34.2as: Noto Sans per schrift uit
  `site/node_modules/@fontsource-variable/` naar `factiz_site/fonts/noto/`, ongewijzigd; na een nieuwe versie van een pakket
  opnieuw; `tests/test_factiz_deelbeeld.py` eist dezelfde bytes)*
- Het logo als beelden: `python -m doublecheck.merkbeelden` *(#23.18, DESIGN §4h: uit `logo.svg` en `woordmerk.svg` van
  de PO in `factiz_site/static/merk/` het icoon, `favicon.ico`, `apple-touch-icon.png`, de avatar, het beeld bij delen
  (`og.jpg`) en het witte woordmerk, in dezelfde map, en het woordmerk voor kop en voet in
  `factiz_site/static/merk/woordmerk-inline.svg`, met Pillow uit de vormen in de SVG; één plek voor de site en het platform
  (#34.2f); `tests/test_merkbeelden.py` tekent ze opnieuw en eist dezelfde bytes)*
- Community Notes: `python -m doublecheck.communitynotes` *(meten;
  `--importeer` zet de bruggen als regels in de geschiedenis, #25.16; de bron
  maakt de database niet uitgeefbaar)*
- Notes voor ongecheckte beweringen: `python -m doublecheck.notesmeting
  selecteren|embedden|meten|herordenen` *(offline, `--map` kiest de pool; de
  herordenaar `bge-reranker-v2-m3` staat vast in `herordenaar.py`, #25.23;
  noteteksten nooit naar een externe dienst. Uitkomst: niet in het antwoord,
  BENCHMARK §91)*
- Stiltetoets: `python -m doublecheck.stiltetoets ophalen|embedden|meten|tellen`
  *(gewone webtekst op postlengte uit mC4 die nooit `matched` mag geven;
  embedden is hervatbaar met `--deel`, meten haalt alles boven de laagste
  drempel door het echte `/resolve`, tellen weigert zolang een `matched`
  geen label heeft in `docs/steekproeven/28.6g-stiltetoets.json`, #28.6 g)*
- Vage claimteksten: `python -m doublecheck.vaagmeting meten|tellen|toepassen`
  *(claims die veel gewone webtekst uit de stiltetoets aantrekken; tellen
  weigert zolang een trekker geen label heeft in
  `docs/steekproeven/25.26-vage-claims.json`, toepassen zet de vage in
  `doublecheck/vage_claims.json`, #25.26, #25.28)*
- Wat de index toelaat: `python -m doublecheck.toelating [aan]` *(meldt hoeveel
  claims buiten de index vallen, per reden, en welke testparen erop wijzen;
  `aan` zet de witte lijst van uitgevers aan voor deze database (`bootstrap`
  doet dat zelf); `--testparen-weg` haalt die paren bewust weg, met een
  rapport, B28. Toelaten van een uitgever: een regel in `uitgevers.json` én
  een label *redactie* in `docs/steekproeven/25.29-uitgevers.json`)*
- Vetoblokkades: `python -m doublecheck.vetoblokkades tellen|scoren|meten`
  *(alle paren die het NLI-veto uit elkaar houdt; scoren is hervatbaar, meten
  leest de labels in `docs/steekproeven/25.14d-vetolabels.json`, #25.14d)*
- Batchcontrole meten: `python -m doublecheck.screeningmeting` *(de
  screeningpoort op de 21.3-proefset; `--eenheid`, `--top`, `--bm25` en
  `--herordenaar-poorten` zijn de varianten van #21.7. Waar het plafond zit:
  `python -m doublecheck.retrievalmeting`. Paginateksten blijven lokaal)*
- Claimfilter: `python -m doublecheck.claimfilter` *(bouwt en meet de filter
  met kant, #24.2c; `--uit <pad>` schrijft hem weg, `--resolver N` loopt N
  claims door het echte `/resolve`, één per seconde)*
- Evergreens: `python -m doublecheck.evergreen` *(verhaalgroepen over de jaren,
  #27.2a, BENCHMARK §111; schrijft naar `data/evergreen/`)*
- Ask Factiz toetsen: `python -m doublecheck.vraagtoets` *(de 53 vragen van
  `docs/steekproeven/24.10-vragen.json`; `--poort` meet de herordenaar als
  poort, `--stilte-web N` haalt gewone webtekst door die poort en is
  hervatbaar, `--stilte-tel` telt de labels in
  `docs/steekproeven/24.10-stilte-web.json` en weigert zolang een regel er
  geen heeft; #24.10, BENCHMARK §112–§114; met `HF_HUB_OFFLINE=1`)*
- Vraag en bewering (#25.36): `python -m doublecheck.vraagmeetset
  plan|indienen|ophalen|uitschrijven` *(de meetset: Batch API met de sleutel
  uit `.env`, eerst een proefbatch, binnen `--budget`)* en `python -m
  doublecheck.vraagmeting meten [--aan] [--helft ontwikkel]|stilte --pool
  <map>` *(door het echte `/resolve` en Ask, met `[vraagvorm] aan` uit of
  aan; de toetshelft alleen met `--stap-e`; `stilte` is hervatbaar)*
- Vraag-claims als bewering (#25.37): `python -m doublecheck.vraagvarianten
  plan|kopie|importeren` *(varianten van de regel, geen taalmodel; alleen in
  een kopie van de database, de import weigert die van de resolver, B22)*
- Clusters bouwen: `python -m doublecheck.clustering` *(`--zonder-veto` slaat het
  NLI-veto over; het clusterbewuste benchmarkcijfer weigert op clusters die met
  een andere drempel of modelversie zijn gebouwd)*
- Uitgeversregister bijwerken: `python -m doublecheck.uitgevers`
  *(`--voorstel` schrijft een nieuw voorstel weg en behoudt handmatige regels;
  wat de meting niet zeker weet komt in `te_beoordelen` en wordt niet toegepast)*
- Bonnetjes die blijven: `python -m doublecheck.bonnetjes
  controleren|toepassen|archief|rapport` *(per check-link of de bron nog
  bereikbaar is; per host één verzoek tegelijk, robots.txt, hervatbaar;
  `toepassen --ronde <log>` zet een ronde in één keer in de database;
  offline pas na twee dode waarnemingen met een dag ertussen, dus
  `controleren --alleen-dood` minstens 24 uur later; `archief` stelt alleen
  leesvragen aan de Wayback Machine, nooit opslagverzoeken, #25.9)*
- Betwistingen bekijken: `python -m doublecheck.dispute`
- Terugkijktoets: `python -m doublecheck.terugkijk meten|tellen` *(het
  geheugen per vraag terug in de tijd; goed is alleen wat mensen koppelden,
  via dezelfde post of een Community Note; tellen weigert zolang een
  ander-record geen label heeft in `docs/steekproeven/28.6c-*.json`, #28.6 c,
  BENCHMARK §116)*
- Vooruitblik: `python -m doublecheck.vooruitblik bevriezen|ophalen|tellen`
  *(#28.6 d: `bevriezen --release <naam>` hoort bij elke release en schrijft
  `docs/releases/bevroren.json`; `ophalen` draait wekelijks via launchd en
  raakt de database niet; `tellen` geeft alleen totalen)*
- De zeef: `python -m doublecheck.zeef meten|lezen|tellen --versie <naam>`
  *(de meetmachine per versie, #30.1, B33: P1 tekst, P2 artikelen, P3
  beelden en N1 webtekst door het echte pad; hervatbaar per set, `--sets`
  om twee processen naast elkaar te laten meten; `lezen` drukt de
  ongelabelde treffers af, `tellen` weigert zolang er een geen label heeft
  in `docs/steekproeven/30.1-zeef.json`; van de toetshelft alleen totalen;
  uitvoer in `data/zeef/<versie>/`, BENCHMARK §120)*
- De tweede artikellezer: `python -m doublecheck.lezerb lesstof|plan|indienen|ophalen|uitschrijven|trainen|kiezen`
  *(#30.11c: de lesstof van A plus Sheffield-artikelen en harde webtekst met
  Haiku-labels (eerst `indienen --proef 50`), opnieuw getraind vanaf de
  herordenaar; `kiezen` legt de drempels op het keuzedeel vast in
  `data/artikellezer/b/keuze.json`; trainen en kiezen achter de hittewacht)*
- De rest van de Sheffield-set: `python -m doublecheck.sheffield ophalen|tellen`
  *(lesstof voor een volgende artikellezer, #30.11b, PO 2026-10-21: alleen
  titel, beschrijving en alineatekst, nooit HTML; per host één verzoek met
  robots.txt, anders de Wayback-kopie; hervatbaar; schrijft naar
  `lesstof-artikelen.jsonl`, nooit naar `artikelen.jsonl`, dus P2 blijft gelijk)*
- Hittewacht: `python -m doublecheck.hittewacht [--log <pad>] -- <commando>`
  *(voor elke zware run op de Mac: pauzeert de hele procesgroep zodra macOS
  de Mac warmer dan nominaal meldt en laat haar na twee koele metingen verder
  gaan; elke tien minuten CPU, grafische chip en swap in het log; PO
  2026-10-21: "zorg erin dat de GPU en CPU niet overhitten")*
- De leerling: `python -m doublecheck.leerling trainen|scoren|lezen|meten
  [--naam leerling-2 --leerstof v3]` *(#31.4, B42: een eigen classificeerder
  vanaf de herordenaar; trainen en scoren achter de hittewacht; de drempel
  kiest de keuzerol, de toetshelft alleen totalen; `scoren` is hervatbaar;
  `lezen` drukt gevlagde webtekst zonder label af, `meten` weigert zolang er
  een open is in `docs/steekproeven/31.2-leraar.json`; BENCHMARK §141–§142)*
- Wikipedia per onderwerp: `python -m doublecheck.onderwerp
  plan|indienen|ophalen|zoeken|bewaken|tellen` *(#31.5: Haiku leest per onwaar
  stuk zoekwoorden, zonder oordeel; Wikipedia één verzoek tegelijk,
  hervatbaar, alleen de inleiding; `bewaken` haalt met bge-m3 uit de leerstof
  wat op een gemeten stuk lijkt; uitvoer in `data/echtnieuws/onderwerp/`)*
- Controleren met bronnen: `python -m doublecheck.verificatie
  geheugen|indienen --omstandigheid a|b|k [--proef N]|ophalen|lezen|tellen
  [--ronde N --model haiku|sonnet]` *(#31.8: een model leest het bericht,
  krijgt de checks uit het geheugen en zoekt op het web; *klopt niet* alleen
  met een check of een geciteerde bron, *let op* (vanaf v4, ronde 4) alleen
  met een van drie redenen; (b) zonder geheugen en met de factchecksites
  geblokkeerd, (k) kaal, zonder zoeken; `tellen` weigert zolang een oordeel
  dat telt geen label heeft in `docs/steekproeven/31.8-verificatie*.json`;
  budget per ronde; ronde 6 telt de echte tiplineberichten met `telling_wild`,
  ronde 7 is de bewijsronde (`w` = alleen web, op de evergreens),
  BENCHMARK §145–§150)*
- De waarheidsmeter: `python -m doublecheck.meter` *(B44, PLAN #31.9: herleest de
  antwoorden van de vastgezette machine en ijkt per oordeel en bron de stand van 1 tot 9 uit het
  gemeten aandeel waar, met interval; geen nieuwe vragen aan een model; uitvoer in
  `data/meter/`, BENCHMARK §151)*
- De route op echte screenshots: `python -m doublecheck.hittewacht -- python -m doublecheck.routemeting set`,
  daarna `python -m doublecheck.routemeting indienen [--proef 10]|ophalen|live|lezen [--masker]|tellen|opruimen`
  *(B43, PLAN #31.10: OCR, opknippen en maskeren (`opknippen.py`) lokaal, de machine zonder beeld, de
  feitenstap en de meter; `live` meet de wachttijd met de drie vragen tegelijk; `tellen` weigert zolang een
  oordeel dat telt geen label heeft in `docs/steekproeven/31.10-route.json`; `opruimen` wist de ruwe OCR van
  de handsteekproef; BENCHMARK §155)*
- Beweringen eerst voor screenshots: `python -m doublecheck.hittewacht -- python -m doublecheck.beweringeneerst set`,
  daarna `python -m doublecheck.beweringeneerst indienen [--proef 5]|ophalen|wachttijd|zoeken|voormeting`
  *(#32.6: Haiku haalt de beweringen met zoekvragen uit de gemaskeerde tekst, het geheugen zoekt met alles
  samen, met dezelfde functies als `/check`; `zoeken` achter de hittewacht; de ronde alleen als de verwachting
  op de 100 screenshots van ronde 4 75 haalt; grens $5; BENCHMARK §167)*
- De feitenstap: `python -m doublecheck.feitstap varianten indienen|ophalen|lezen|set|laag|indienen
  [--proef 10]|ophalen|lezen|tellen [--route sonnet|laag|beide] [--versie v1|v2]` *(B44, PLAN #31.9:
  koppelt een bericht aan een feit uit de feitenbasis voor stand 0 en 10; lokaal ophalen, één oordeel
  van Sonnet; tellen weigert zolang een 0, 10 of gemiste kernformulering geen label heeft in
  `docs/steekproeven/31.9-feitstap[-v2]-labels.json`; v2 (de standaard) heeft vloer 0,55 en geeft
  geen 10 als het bericht een eigen detail toevoegt, en meet de delen van v1 nog eens; BENCHMARK
  §152–§153)*
- De toets voor de beta: `python -m doublecheck.hittewacht -- python -m doublecheck.betatoets set`, daarna
  `python -m doublecheck.betatoets indienen [--proef 5]|herkansing|ophalen|live|lezen|tellen` *(ronde 4, B45,
  PLAN #31.14: 800 Engelse berichten door dezelfde functies als `/check`, via de Batch API; onbekend nepnieuws
  zonder database en met de factchecksites geblokkeerd; `live` meet de wachttijd door `beoordeel`; `tellen`
  weigert zolang iets dat telt geen label heeft in `docs/steekproeven/31.14-betatoets.json`; grens $20)*
- De herstelronde: `python -m doublecheck.herstel ontwikkel [--vraag vorm-v2]`, `python -m doublecheck.hittewacht --
  python -m doublecheck.herstel set`, daarna `python -m doublecheck.herstel indienen [--proef 3]|herkansing|vorm|ophalen|lezen|tellen`
  *(ronde 5, B45, PLAN #31.15: de vormvraag en de twee regels op 200 nieuwe berichten, met en zonder de regels uit één
  meting; `vorm` stelt de vormvraag na het oordeel, alleen bij rood of groen; `tellen` weigert zolang iets dat telt geen
  label heeft in `docs/steekproeven/31.15-herstel.json`; grens $6; BENCHMARK §159)*
- De gebruikerstoets: `python -m doublecheck.gebruikerstoets kanten indienen|ophalen`, `kiezen`, `genereren
  indienen|ophalen|lezen`, `python -m doublecheck.hittewacht -- python -m doublecheck.gebruikerstoets set`, daarna
  `indienen [--proef 3]|herkansing|vorm|ophalen|lezen|tellen` *(P11 van fase 0, PLAN #32.0k, B47: 250 Engelse
  berichten in zes delen (echte artikelen, vervalste, verzonnen details, gezondheid als TikTok, politiek, overduidelijk)
  door Factiz, het kale model met zoeken en een model zonder zoeken; de screenshots alleen in het geheugen; `tellen`
  weigert zolang iets dat telt geen label heeft in `docs/steekproeven/32.0k-gebruikerstoets.json`; grens $12;
  BENCHMARK §160)*
- Materiaal per taal en de aanvoer: `python -m doublecheck.talen aanvoer|tellen|duits indienen|ophalen|lezen|tellen`
  *(P3 en P10 van fase 0, PLAN #32.0a en #32.0g: checks per maand in de database en de feed, per taal wat er is
  (Wikinews, bekende en verse onware checks, M4FC); de Duitse oordelen in zinsvorm door Haiku omgezet naar
  `data/talen/duits.jsonl`, nooit in de database; labels in `docs/steekproeven/32.0g-duitse-oordelen.json`; BENCHMARK §161)*
- Het zoeken voor screenshots: `python -m doublecheck.zoekherstel nieuw|apple|google|indienen|ophalen|zoeken|tellen
  [--set route|nieuw|waar]` *(P4 van fase 0, PLAN #32.0b: Tesseract, Apple Vision (`appletekst.swift`, met swiftc) of
  Google Vision (`GOOGLE_VISION_API_KEY`, alleen openbare M4FC-beelden), met of zonder beweringen van Haiku of Sonnet;
  `zoeken` achter de hittewacht; BENCHMARK §162)*
- Bekend nepnieuws in echte vorm: `python -m doublecheck.echtevorm kiezen`, `herschrijven indienen|ophalen|lezen`,
  `python -m doublecheck.hittewacht -- python -m doublecheck.echtevorm set`, daarna `indienen [--proef N]|herkansing|vorm|
  ophalen|lezen|tellen` *(P6 van fase 0, PLAN #32.0d: 50 claims in de woorden van een andere redactie met de eigen check
  verborgen (`berichtcontrole.voorbereiden(..., verborgen=...)`, alleen voor metingen) en 50 als doorgestuurd appbericht
  van Haiku, getekend als chat; `tellen` weigert zolang een rood met een andere bron geen label heeft in
  `docs/steekproeven/32.0d-echte-vorm.json`; grens $4; BENCHMARK §163)*
- Het plafond van screenshots: `python -m doublecheck.plafond indienen [--proef N]|herkansing|ophalen|lezen|tellen`
  *(P5 van fase 0, PLAN #32.0c: de 100 echte screenshots van ronde 4 met het beeld erbij voor Sonnet, via de Batch API op
  openbare beelden, het beeld alleen in het geheugen; `tellen` weigert zolang een rood met een andere bron geen label
  heeft in `docs/steekproeven/32.0c-plafond.json`; grens $3,50; BENCHMARK §164)*
- De tegenspeler: `python -m doublecheck.tegenspeler kiezen`, `genereren indienen|ophalen|lezen`, `python -m
  doublecheck.hittewacht -- python -m doublecheck.tegenspeler set`, daarna `indienen|herkansing|vorm|ophalen|lezen|tellen`
  *(P8 van fase 0, PLAN #32.0e: verstopte opdrachten met tweeling, een vals detail, verzonnen instituten, een nep-uitslag
  van Factiz en satire als nieuws; `tellen` weigert zolang een groen geen label heeft in
  `docs/steekproeven/32.0e-tegenspeler.json`; grens $2; BENCHMARK §165)*
- Klopt grotendeels (B48): `python -m doublecheck.detailmeting kiezen`, `genereren indienen|ophalen|lezen`, `set`,
  `indienen|herkansing|vorm|ophalen`, `vragen [--helft ontwikkel|toets]`, `zoeken`, `lezen|tellen` *(PLAN #32.3a: de
  detailvraag (`berichtcontrole.detailverzoek`, `detail-v3`, in config `detail`, standaard uit) op de bestaande antwoorden
  van P11, P8 en W5 en op 40 nieuwe verzonnen details; `tellen` weigert zolang een groen, een markering of een maar geen
  label heeft in `docs/steekproeven/32.3a-vals-detail.json`; grens $3; BENCHMARK §166)*
- De modelpoort: `python -m doublecheck.modelpoort set|indienen [--proef]|vervolg|ophalen|lezen|tellen|wachttijd`
  en voor de drie strengere meetregels `r-volgorde|r-kanten|r-lezen|r-set` *(P9, PLAN #32.0f: Opus, Sonnet en
  Haiku als machine op de 100 moeilijkste uit de toetshelften van P11, P6 en P8; `vervolg` stelt per model de
  volgende vraag zoals `beoordeel` (herkansing, feitenstap, vorm, detail, zoekstap); `tellen` weigert zolang iets
  dat telt geen label heeft in `docs/steekproeven/32.0f-modelpoort.json`; grens $13; BENCHMARK §168)*
- De vloer, een voormeting: `python -m doublecheck.vloer pool|indienen [--proef 10]|ophalen|lezen|tellen` *(#32.0l:
  een vraag zonder zoeken (Haiku, twee sleutels) op de eerdere berichten waar de machine zonder bron onzeker of
  let op zei; `tellen` weigert zolang een vals alarm geen label heeft in `docs/steekproeven/32.0f-vloer.json`;
  grens $2; BENCHMARK §169)*
- De ronde van de vloerstap: `python -m doublecheck.hittewacht -- python -m doublecheck.vloerronde set`, daarna
  `python -m doublecheck.vloerronde vloer indienen|ophalen`, `o indienen|vervolg|ophalen`, `wachttijd|lezen|tellen`,
  en voor `vloer-v2` (#32.0n) `o2 set|indienen|vervolg|vergelijk|ophalen|tellen`
  *(#32.0m, B50: de twee vragen van `vloer-v1` op alle berichten van de rondes met vraag v4 voor de ijking van de laag
  algemene kennis en de bewaking op de ware berichten; set O, 100 nieuwe zinnen over de vastgestelde feiten, door de
  controle met de vloerstap aan en door het kale model; R3 opnieuw geteld op de antwoorden van P9; `tellen` weigert
  zolang een vals alarm of een markering geen label heeft in `docs/steekproeven/32.0m-vloerronde.json`; grens $7)*
- Het snelle antwoord: `python -m doublecheck.hittewacht -- python -m doublecheck.snelantwoord meten|tipline|ocr`,
  daarna `python -m doublecheck.snelantwoord lezen|tellen` *(#32.0o: het echte `/resolve` zonder taalmodel op de
  berichten van de rondes, de tiplineberichten en de echte screenshots; goed, fout of door naar de verdieping, en de
  tijd; `tellen` weigert zolang een snelle fout bij een waar bericht geen label heeft in
  `docs/steekproeven/32.0o-snelantwoord.json`; $0; BENCHMARK §172)*
- Betrouwbare bronnen: `python -m doublecheck.bronnenlijst bouwen|tellen` *(#32.3b: per website een soort
  (A betrouwbaar, O officieel, U door gebruikers, C onbetrouwbaar, B de rest) uit Lin e.a., Wikipedia, het
  IFCN en de EBU met RSF, gelezen uit `data/bronnen/extern/`; het strengste oordeel telt; `bouwen` weigert als
  de lijst al vastligt, `tellen` weigert als de vingerafdruk niet klopt; $0; BENCHMARK §173)*. Versie 3, voor
  gebruik: `python -m doublecheck.bronnen bouwen|dekking` *(#32.3c: eerst de soort (platform, naslag, officieel,
  overig), dan de band uit oordelen over een uitgever: goed vanaf Lin e.a. 0,65 (PO), laag tot en met 0,40; een
  platform krijgt nooit een band. #32.29: daarbij het EFCSN, de JTI, het Trust Project en het IFCN in vernieuwing,
  alleen bij de 40 Spaanse en Portugese redacties die de PO koos (`docs/steekproeven/32.29-keuzes-po.json`); zonder
  teken geen band; #32.29d, versie 4: dezelfde tekens in alle talen uit de volle lijsten in `data/bronnen/extern/` (het
  IFCN actief en in vernieuwing, het EFCSN, de JTI, het Trust Project waar de titel past); *twijfel* van de PO gaat voor;
  `bouwen` weigert als de lijst al vastligt; `dekking` vergelijkt met versie 3, per taal;
  `data/bronnen/bronnen-v4.json`, buiten git; BENCHMARK §202, §205; versie 5 (B58, #32.42): versie 4 met es-, pt- en de.wikinews.org *goed* zoals en.wikinews.org (`bronnen.PO_BANDEN`), `bouwen` maakt `bronnen-v5.json` uit de vaste versie 4; versie 6 (B64, #32.59): versie 5 met de publieke omroepen van de EBU in een land met 75 of meer bij RSF *goed* ook als Lin *wisselend* zegt, en nl- en fr.wikinews.org *goed*; `bouwen` maakt `bronnen-v6.json` uit de vaste versie 5; versie 7 (#32.66, B69, in gebruik sinds de tussenrelease van 2026-11-09): `doorverwijzingen` vraagt de voorpagina van elke site één keer op (robots.txt, hervatbaar), `verhuizingen` zet de kandidaten in `docs/steekproeven/32.66-verhuizingen.json`, en `bouwen` weigert zolang er een geen label heeft; verhuisde media houden hun oordeel, verlopen *goede* domeinen verliezen het, BENCHMARK §255)*. De dekking op echte zoekresultaten: `python -m
  doublecheck.bronnendekking set|draaien [--proef 5]|tellen` *(#32.29c: 100 claims per taal (en, es, pt, de) door de top
  10 van Brave, zoals het product; per vraag 1 en 2 goede uitgevers, met en zonder factcheckers, en of groen kan, met
  elke versie van de lijst op dezelfde resultaten; alleen de adressen bewaard; grens $2,50)*. Een eigen
  beoordeling voor sites zonder Lin en zonder teken: `python -m doublecheck.eigenscore ijkset|ophalen [--set ijk]|indienen
  [--set ijk] [--opnieuw a,b]|ophalen-antwoorden|ijktellen` *(#32.29d: Haiku leest de eigen pagina's van een site, een
  punt alleen met een citaat dat er letterlijk staat; de ijking haalde de eisen niet, dus niet in de lijst; de lijsten
  van het IFCN, het EFCSN, Duke, de JTI en het Trust Project in `data/bronnen/extern/`; grens $3; BENCHMARK §204)*. Kruiscontrole per detail, de
  voormeting: `python -m doublecheck.kruiscontrole voormeting` *(#32.3d: onafhankelijke goede bronnen en de
  getallen uit het bericht in de geciteerde passages, vijf regels; $0; BENCHMARK §174)*
- De herkomstcontrole: `python -m doublecheck.herkomst kiezen|toegang|genereren indienen|ophalen|lezen`, `python -m
  doublecheck.hittewacht -- python -m doublecheck.herkomst set`, daarna `indienen --set ontwikkel|toets [--proef N]|ophalen|
  live|lezen|tellen` *(#32.3e: één zoekvraag van Sonnet alleen op de site die het screenshot noemt, in config `herkomst`,
  standaard uit; `toegang` meet welke sites de zoekfunctie niet toelaat (`berichtcontrole.GEEN_TOEGANG`); `tellen`
  weigert zolang iets dat telt geen label heeft in `docs/steekproeven/32.3e-herkomst.json`; grens $8; BENCHMARK §175)*
- De proef van de controle per bericht: `python -m doublecheck.hittewacht -- python -m doublecheck.controleproef
  [--n 20]` *(#31.12: vragen zonder batchkorting door `berichtcontrole.voorbereiden` en `beoordeel`, op
  openbare zinnen uit ronde 1; meet de cache, de kosten en de wachttijd; grens $1,50; uitvoer in
  `data/berichtcontrole/`)*
- Ronde 1, het fundament: `python -m doublecheck.hittewacht -- python -m doublecheck.fundament set`,
  daarna `python -m doublecheck.fundament indienen [--proef 10 | --willekeurig]|ophalen|lezen|tellen` *(B45, PLAN #31.11:
  de machine op 801 Engelse zinnen over de vastgestelde feiten, 350 waar en 451 vals; de feitenstap uit
  §154 hergebruikt; `tellen` weigert zolang een oordeel dat telt geen label heeft in
  `docs/steekproeven/31.11-fundament.json`; meldt de eis van B45; BENCHMARK §156)*
- Omgekeerd zoeken op beelden: `python -m doublecheck.beeldzoeken
  [zoeken] --ronde 5|waar|vorm indienen|ophalen` *(#31.8: Google Cloud Vision
  met `GOOGLE_VISION_API_KEY` uit `.env`; alleen pagina's en titels bewaard,
  nooit het beeld; `waar` haalt de ware beelden uit M4FC beleefd op met
  robots.txt; `vorm` laat Haiku kale foto's en stempels aanwijzen. Haalde
  de lat niet en stopt, BENCHMARK §148)*
- Releaserapport: `python -m doublecheck.releaserapport --voor <run> --na <run>
  --uit docs/releases/<naam>-<datum>.md` *(de aankondiging tot de lancering,
  #23.10; weigert runs op verschillende testparen en een run die niet met de
  motor uit `config.toml` gemaakt is)*
- Conformantie toetsen: `python -m conformance <url>` *(`--proeven
  deploy/conformantie-proeven.json` met bekende claims, anders blijven de
  matched-verplichtingen en `via` onwaargenomen; uitgang 2 = conform maar niet
  volledig getoetst)*

- De koppen van de dichte sites: `python -m doublecheck.koppen set|wikipedia|indienen [--proef N]|ophalen|portal|gdelt|lezen|tellen`
  *(#32.3f: route 1 de bronnen van Wikipedia, route 2 overnames en verwijzingen met Haiku, route 3 GDELT op verse
  links uit Portal:Current events; Wikipedia en GDELT één verzoek tegelijk met oplopende wachttijd; `tellen` weigert
  zolang een vondst geen label heeft in `docs/steekproeven/32.3f-koppen.json`; grens $3)*
- Het beeld bij screenshots: `python -m doublecheck.hittewacht -- python -m doublecheck.beeldronde set`, daarna
  `python -m doublecheck.beeldronde indienen [--proef N]|herkansing|ophalen|lezen|tellen` *(#32.6b: vraag v4 zonder en
  met het beeld op N, 58 echte screenshots van bekend nepnieuws, en W, 61 echte foto's met een ware bewering; `tellen`
  weigert zolang een rood of groen dat telt geen label heeft in `docs/steekproeven/32.6b-beeld.json`; grens $7)*
- De eindtoets: `python -m doublecheck.eindtoets set|lezen`, `python -m doublecheck.hittewacht -- python -m
  doublecheck.eindtoets draaien`, daarna `tellen` *(#32.8: 60 Engelse berichten (K bekend, V verborgen, W waar uit
  Portal:Current events) live door de hele keten; de PO zet de labels op een eigen pagina, Claude haalt ze op naar
  `docs/steekproeven/32.8-eindtoets.json`; `tellen` weigert zolang een bericht geen label heeft; grens $3,50)*
- Zoeken eerst: `python -m doublecheck.hittewacht -- python -m doublecheck.zoekeerst draaien`, daarna `tellen`
  *(#32.9: de simpele versie tegen de oude keten op de 60 berichten van de eindtoets; Brave met de sleutel uit `.env`;
  grens $2; BENCHMARK §179)*
- De controle op 500 berichten: `python -m doublecheck.hittewacht -- python -m doublecheck.controle500 draaien`,
  daarna `lezen|tellen` *(#32.11: `lezer-v2` op 300 ware en 200 nepberichten uit ronde 4; hervatbaar; `tellen`
  weigert zolang een alarm bij een waar of een groen bij een nepbericht geen label heeft in
  `docs/steekproeven/32.11-controle500.json`; grens $4; BENCHMARK §181)*
- De lezer op verse berichten: `python -m doublecheck.versetoets set`, `python -m doublecheck.hittewacht -- python -m
  doublecheck.versetoets ontwikkel [--alleen <ids>]|draaien`, daarna `lezen|tellen` *(#32.12: `lezer-v3` op de 15
  gelezen gevallen van §181 en op 100 verse onware en 50 verse ware berichten; de onware eerst; `tellen` weigert
  zolang iets dat telt geen label heeft in `docs/steekproeven/32.12-versetoets.json`; grens $2; BENCHMARK §182)*
- Het antwoord in twee lagen: `python -m doublecheck.tweelagen set`, `python -m doublecheck.hittewacht -- python -m
  doublecheck.tweelagen ontwikkel [--alleen <ids>]|draaien`, daarna `lezen|tellen` *(#32.13: `lezer-v4` op de 18
  nagekeken gevallen en op 100 verse onware en 40 verse ware berichten; `tellen` weigert zolang een groen, een alarm of
  een getoonde zin (`<id>#feit`, `<id>#anders`) geen label heeft in `docs/steekproeven/32.13-tweelagen.json`; grens
  $2; BENCHMARK §183)*
- De voormeting voor de beeldmotor: `python -m doublecheck.beeldmotor set|ophalen|lezen|tellen` *(#32.14: per
  factcheckartikel van de 40 beeldclaims van O' alleen tekst uit de HTML, per host één verzoek met robots.txt; labels
  in `docs/steekproeven/32.14-beeldmotor.json`; $0; BENCHMARK §184)*
- De beeldindex op echte screenshots: `python -m doublecheck.beeldindexmeting set`, `python -m doublecheck.hittewacht --
  python -m doublecheck.beeldindexmeting oogsten [--max 50]`, `vision`, `vragen --set R2|S1|S2|S3|S4` (achter de
  hittewacht), daarna `zoeken|lezen|tellen` *(#32.15: per beeld alleen de PDQ-hashes en de DINOv2-vector
  (`beeldvraag.py`, de kern), nooit het beeld; oogst en vragen per host één verzoek met robots.txt, hervatbaar; uitvoer
  in `data/beeldindex/pdq-256-v1+dinov2-small-ed25f3a3/`; `tellen` weigert zolang een treffer buiten de eigen bewering
  geen label heeft in `docs/steekproeven/32.15-beeldindex.json`; Google Vision alleen voor de kopieën van R2;
  `--panelen` is stap 2b: de artikelen van R2 opnieuw met panelen uit collages en posts, `beelduitsnede.panelen`;
  `punten|punten-lezen|punten-tellen` is stap 2d, SIFT met OpenCV, alleen in het geheugen; BENCHMARK §185–§187)*
- Het beeld in de nieuwe controle: `python -m doublecheck.hittewacht -- python -m doublecheck.beeldcontrole draaien
  [--proef N]`, daarna `lezen|tellen` *(#32.16: `zoekcontrole.controleer` met en zonder beeld op de sets van §178,
  één zoekvraag en één keer de database per bericht voor beide armen; `tellen` weigert zolang iets dat telt geen label
  heeft in `docs/steekproeven/32.16-beeldcontrole.json`; grens $3; BENCHMARK §188)*
- De lezer met de checks uit de database: `python -m doublecheck.hittewacht -- python -m doublecheck.databaselezer
  draaien [--proef 5]`, daarna `lezen|tellen` *(#32.28: drie armen op dezelfde zoekresultaten van Brave en dezelfde
  kring 1: `lezer-v3` (het product nu), `lezer-v5` met de beste 5 checks van de woorden (sleutel 1 van de vindronde),
  en daarbij de checks waarvan het beeld de screenshot bevestigt (`rol-v3`, `zoekcontrole.BEELDZIN`); op N en W van
  §188, zonder beeld naar het model; `tellen` weigert zolang een rood, oranje of groen dat telt geen label heeft in
  `docs/steekproeven/32.28-database-lezer.json`; grens $6; BENCHMARK §201)*
- De lezer met de database op tekst: `python -m doublecheck.hittewacht -- python -m doublecheck.tekstlezer draaien
  [--proef 5]`, daarna `lezen|tellen`, en `wachttijd` *(#32.30: `lezer-v3` en `lezer-v5` op dezelfde zoekresultaten op W
  (300 ware van ronde 4), W' en O' (de verse van §182, bij O' de eigen check verborgen); `tellen` weigert zolang een alarm
  bij een waar of een groen bij een onwaar bericht geen label heeft in `docs/steekproeven/32.30-tekst.json`; `wachttijd`
  stuurt 20 berichten door het echte `POST /check` met de controle aan in een kopie van de config; grens $12; BENCHMARK
  §206)*
- De lezer met alle uitkomsten: `python -m doublecheck.uitkomsten set`, `python -m doublecheck.hittewacht -- python -m
  doublecheck.uitkomsten ontwikkel|draaien [--proef 5]`, daarna `lezen|tellen` *(#32.31: `lezer-v6` met geen bewering,
  satire, klopt grotendeels, over een bewering en beeld nodig (`zoekcontrole.na_lezen`, de kern) op 100 gewone teksten
  en 25 met een bewering (echte tiplineberichten), W en O' van §206 en de verzonnen details van §166; Sonnet via de
  Batch API op openbare data, de zoekresultaten alleen in het geheugen; `tellen` weigert zolang een rood of oranje bij
  G of W, een groen bij O' of D of een *klopt grotendeels* bij W geen label heeft in
  `docs/steekproeven/32.31-uitkomsten.json`; grens $6. Met `--lezer lezer-v7` is het #32.32: de zin uit `vorm-v2`
  terug en een strengere *klopt grotendeels*, op W2 (200 Wikinews-artikelen), G2, O', D, S-los en S-bron (satire), labels
  in `docs/steekproeven/32.32-uitkomsten-v7.json`; een batch die na 20 minuten niet dicht is, wordt geannuleerd en alleen
  wat hangt gaat opnieuw (`batch_met_grens`), verloren kosten staan in `verloren.jsonl` en tellen mee; BENCHMARK §207,
  §208)*
- `lezer-v7` op echte screenshots: `python -m doublecheck.screenshotlezer set`, `python -m doublecheck.hittewacht --
  python -m doublecheck.screenshotlezer draaien [--proef 5]`, daarna `lezen|tellen` *(#32.33: N en W van §201 door de
  batchronde van #32.32, zoals het product; gewaarschuwd met bewijs met de eigen check als bron of gelezen als
  *bewijst*; `tellen` weigert zolang een groen bij N, een rood of oranje bij N zonder de eigen check of een rood of
  oranje bij W geen label heeft in `docs/steekproeven/32.33-screenshots-v7.json`; de wachttijd met `python -m
  doublecheck.tekstlezer wachttijd --lezer lezer-v7`; grens $2. Met `--ronde beeld` is het #32.36 (B55): het beeld gaat
  mee, zwartgemaakt met `opknippen.zwart_beeld`, labels in `docs/steekproeven/32.36-screenshots-beeld.json`, vier eisen;
  grens $2,80; BENCHMARK §209, §212)*
- Screenshots beter lezen, lokaal: `python -m doublecheck.hittewacht -- python -m doublecheck.ocrvoormeting lezen`, daarna
  `teksten|tellen` *(#32.34: op de 58 screenshots van N de tekstherkenning van het product, Tesseract met alle Indiase
  pakketten en EasyOCR (eerst `pip install easyocr "torch==2.13.0" "torchvision<0.29"`, daarna weer verwijderd); de eigen
  check in de top 5 en de leesbaarheid, gelabeld in `docs/steekproeven/32.34-ocr-leesbaar.json`; $0; BENCHMARK §210)*
- De volle beeldindex bouwen, voor de beeldstap: `python -m doublecheck.beeldindexbouw` *(#32.35: alleen de beelden die
  `rol-v3` viraal noemt, uit de pool en de oogst, met hun punten, de tekst erop als vector en per artikel de checks;
  `data/beeldindex-vol/` met `versies.json`; de beeldstap (`beeldstap`, de kern, `[beeldstap]` in config, standaard uit)
  weigert een andere versie)*
- De volle beeldindex, de oogst: `python -m doublecheck.hittewacht -- python -m doublecheck.beeldoogst oogsten --proef
  1000` (of `--alles`), daarna `ophalen|tellen` *(#32.35: de factcheckartikelen die niet in de pool van #32.21 staan, zonder
  `beeldindexmeting.UITGESLOTEN`; per site één verzoek met robots.txt; per beeld PDQ en de punten, en in hetzelfde
  geheugen `rol-v3` voor de Batch API op openbare artikelen; `ophalen` annuleert een batch die na 20 minuten niet dicht
  is en gooit daarna de punten weg van elk beeld dat niet *viraal* heet; `tellen` schat de rest met de regels uit PLAN;
  uitvoer in `data/beeldoogst/`; grens $0,50 voor de proef; BENCHMARK §211)*
- De woorden zoeken, het beeld bevestigt: `python -m doublecheck.beeldbevestiging set|vision`, `python -m
  doublecheck.hittewacht -- python -m doublecheck.beeldbevestiging vragen [--set N] [--proef 5]|vergelijken [--max
  20]|herbereken`, daarna `lezen|tellen|opruimen` *(#32.17, BENCHMARK §189: de tekst en een beschrijving van de foto
  (`beschrijvingvraag.py`,
  `beschrijving-v1`, Haiku met het beeld) zoeken elk vijf checks; de punten (`beeldvraag.puntkenmerken`, de kern) en
  PDQ bevestigen alleen tegen de beelden in de artikelen van die kandidaten; artikelbeelden alleen in het geheugen, per
  host één verzoek met robots.txt, hervatbaar; `tellen` weigert zolang een bevestiging geen label heeft in
  `docs/steekproeven/32.17-beeldbevestiging.json`; `herbereken` vergelijkt de paren opnieuw met de herstelde
  vergelijking (`sift-ransac-v2`, verkennend); `opruimen` wist daarna de punten van de vragen; grens $3)*
- Drie voormetingen voor de volgende beeldronde: `python -m doublecheck.hittewacht -- python -m
  doublecheck.beeldvoormeting r2|paren|kandidaten [--proef N]`, daarna `lezen|tellen` *(#32.20: V1 §187 opnieuw met
  `sift-ransac-v2`, V2 de eigen check bij 5, 10 en 20 kandidaten per sleutel, V3 de matcher van CopyNCE
  (`copynce.py`, in eigen code nagebouwd; de gewichten van de makers in `data/extern/copynce/`, alleen als getallen
  geladen en op vingerafdruk) naast SIFT; beelden alleen in het geheugen, per host één verzoek met robots.txt;
  `tellen` weigert zolang een paar dat telt geen label heeft in `docs/steekproeven/32.20-voormetingen.json`, en leest
  ook de labels van #32.15 en #32.17; $0)*
- De vindronde: `python -m doublecheck.vindronde set|kopie|vision`, `python -m doublecheck.hittewacht -- python -m
  doublecheck.vindronde vragen|pool`, `rollen indienen|ophalen`, `viraal indienen|ophalen`, `zoeken|vergelijken`,
  daarna `lezen|po|tellen|opruimen` *(#32.21: vier sleutels (de tekst en de beschrijving tegen de claims, en tegen de
  tekst en de beschrijving van de virale beelden in de factcheckartikelen), de rol van elk beeld (`beeldrolvraag.py`,
  de kern; alleen viraal bevestigt) en een meetkopie `data/vindronde/kopie.db` met FACTors en route A (weigert de
  productie, B22); beelden alleen in het geheugen, per host één verzoek met robots.txt; `tellen` weigert zolang een
  bevestiging die telt geen label heeft in `docs/steekproeven/32.21-vindronde.json`; `po` schrijft de nakijkpagina
  voor de PO, 30 bevestigingen en 30 rollen zonder de labels van Claude, keuzes alleen in de browser; grens $5;
  BENCHMARK §194; `rolvoormeting lezen|tellen` is #32.25: de beelden die bij N en R3 de eigen check bevestigen maar
  geen viraal heten, gelezen in `docs/steekproeven/32.25-rol.json`; `tellen` weigert zolang een beeld geen gelezen rol
  heeft; $0; `rolronde set|indienen [--proef 10]|ophalen|lezen|tellen` is #32.26: `rol-v3` (`beeldrolvraag.py`, de kern)
  laat Haiku elk beeld van het artikel zien, op 539 artikelen, via de Batch API op openbare artikelen, de beelden
  alleen in het geheugen; `tellen` weigert zolang een bevestiging die door `rol-v3` telt geen label heeft in
  `docs/steekproeven/32.26-rolronde.json`; grens $2)*
- De opmaak eruit: `python -m doublecheck.hittewacht -- python -m doublecheck.opmaakmeting referentie|ophalen|vergelijken`,
  daarna `lezen|tellen|opruimen` *(#32.22: een punt van een artikelbeeld met een tegenhanger in een beeld van minstens 4
  andere artikelen van dezelfde site is opmaak (stempel, balk, logo; `beeldvraag.opmaakmasker`, `opmaak-v1`, de kern)
  en gaat eruit vóór dezelfde vergelijking; op de 875 bevestigingen van #32.21 en 500 paren zonder bevestiging; beelden
  alleen in het geheugen, per host één verzoek met robots.txt, hervatbaar; de punten in `data/opmaak/` tot `opruimen`;
  `tellen` weigert zolang een bevestiging die de regel erbij geeft geen label heeft in
  `docs/steekproeven/32.22-opmaak.json`; $0; `voormeting ophalen|vergelijken|tellen|opruimen` is #32.23: `opmaak-v2`
  telt een tegenhanger alleen op dezelfde plek in een beeld van bijna dezelfde vorm, op de 163 paren die in #32.22
  veranderden of vals waren, met opnieuw `opmaak-v1` ter controle; uitvoer in `data/opmaakplek/`; `rest
  ophalen|vergelijken|lezen|tellen|opruimen` is #32.24: na `opmaak-v2` legt `beeldvraag.restcontrole` (`rest-v1`) het
  artikelbeeld met de gevonden vorm op de vraag en vergelijkt 8 bij 8 vakken, op 863 paren; de beelden bij het
  vergelijken opnieuw beleefd opgehaald, alleen in het geheugen; uitvoer in `data/opmaakrest/`)*
- Eigen aanvoer, route A: `python -m doublecheck.eigenaanvoer verken|proef|lezen|tellen` *(#32.19: de ClaimReview
  die factcheckers zelf in hun artikelen zetten, via de sitemap uit robots.txt, per site één verzoek met minstens 2
  seconden ertussen, als FactizResearch; bewaard alleen adres, bewering, oordeel en datum, buiten de database in
  `data/aanvoer/proef/`; `tellen` weigert zolang een check uit de steekproef geen label heeft in
  `docs/steekproeven/32.19-eigenaanvoer.json`; $0; BENCHMARK §190)*
- Route A terug in de tijd: `python -m doublecheck.terugaanvoer verken|ophalen [--ronde eerste|tweede]|tellen`, en
  voor de oordelen `oordelen set|kopregel|indienen [--versie] [--set ontwikkel|toets|alles] [--proef N]|ophalen
  [--annuleer]|lezen [--blind]|tellen`, het nakijken `nakijken sets|lezen|pagina|toets2|tellen` en de import
  `importeren --in-kopie` *(#32.38: elk artikel uit de
  sitemap van Snopes, Full Fact, Lead Stories en EFE Verifica (tweede ronde: Maldita, Newtral), per site één verzoek met
  minstens 2 seconden ertussen en robots.txt, hervatbaar; alleen de ClaimReview, buiten de database in
  `data/aanvoer/terug/`; de oordelen eerst met de regels van `verdicts.py`, wat de redactie zelf geen oordeel noemt
  (`verdicts.geen_oordeel`) nooit naar Haiku; Full Fact alleen met de kopregel op hun host, de rest van Full Fact
  houdt onbekend (`ZONDER_LEZER`); Lead Stories en EFE met `oordeel-terug-v1` binnen $2 (`v2` maakte meer fouten);
  `tellen` weigert zolang een gelezen antwoord geen label heeft in `docs/steekproeven/32.38-oordelen.json`;
  BENCHMARK §213; `nakijken` telt mijn blinde labels en die van de PO samen (§214); `importeren --in-kopie` doet de
  import in een kopie van de database en gooit die daarna weg; herkomst `route-a`, niet herverdeelbaar; Lead Stories
  niet (B56); een artikel dat er al is uit een andere bron komt er niet nog eens in, en `dubbel [--uitvoeren]` haalt
  wat de import van 2026-11-10 er toch bij zette weg, rapport eerst (#32.66))*
- De conclusie in het veld van de bewering: `python -m doublecheck.omgedraaid set`, daarna `indienen [--ontwikkel]
  [--versie] [--proef N]|ophalen|lezen|tellen` en `toepassen [--uitvoeren]` *(#32.66: Maldita, Newtral en EFE Verifica
  zetten soms hun eigen bevinding in `claimReviewed` ("No, Nespresso no ha regalado ...", *Bulo*); Haiku leest elke
  negatieve check van die drie via de Batch API, ik lees elke *conclusie* en *twijfel* na in
  `docs/steekproeven/32.66-omgedraaid.json`; `tellen` weigert zolang een gemarkeerde check geen label heeft; wat gelezen
  conclusie of twijfel is gaat uit de database en blijft bij een nieuwe import weg; grens $2. Met `--ronde publicatie`
  de hele publicatiedatabase (2026-11-12, na El Detector van Univision): eerst `voormeting` (per redactie de negatieve
  checks met een ontkenning in hun eigen taal, zonder model), dan `set` (ronde 1, elke vorm) en `set --tweede` (ronde 2,
  de hele redacties waar ronde 1 een conclusie gaf) en `set --derde` (ronde 3, de redacties die in ronde 2 niet meer
  pasten), niet EUvsDisinfo; labels in `docs/steekproeven/32.66-omgedraaid-publicatie.json`, uitvoer in
  `data/omgedraaid/publicatie/`, grens $9 voor alle rondes samen; een tweede weghaalronde op een dag krijgt een eigen
  rapport (`weg-<datum>-2.json`); `toepassen
  --uitvoeren` schrijft ook `doublecheck/omgedraaid_weg.json`, die `ingest.import_claims` bij elke import weigert, en
  haalt een factcheck waarvan de pagina verdwijnt uit `content/dossiers/*/factchecks.json`; een bewering in de testset van
  de benchmark blijft staan, onder `wacht op de testset` in het labelbestand, tot de PO beslist)*
- Wat de factchecks ons leren: `python -m doublecheck.werkwijze set|ophalen|indienen [--proef N]|antwoorden|lezen|tellen|opruimen`
  *(#32.39, PO 2026-11-04: 2.000 factcheckartikelen uit de database (onwaar, misleidend of deels waar, de helft Engels,
  de helft uit 2023–2026, hoogstens 40 per redactie) en 200 uit M4FC; per host één verzoek met robots.txt, alleen titel
  en alineatekst, tijdelijk in `data/werkwijze/teksten.jsonl` tot `opruimen`; Haiku via de Batch API (`truc-v1`): de
  vorm, de truc, wie er werd nagedaan en hoe de factchecker het ontdekte, een methode alleen met een letterlijk citaat;
  `tellen` weigert zolang een van de 100 nagekeken artikelen geen label heeft in
  `docs/steekproeven/32.39-werkwijze.json`; grens $1)*
- Eén vaste meetopzet: `python -m doublecheck.meting <meetplan> set|draaien [--proef N] [--direct]|foto [--foto fotobron-v1|fotobron-v2] [--snel --max N]|wachttijd|lezen|tellen [--foto ...]`
  *(#32.41: een ronde is een meetplan in `docs/meetplannen/<taak>.json` met de sets (bron, aantal, als op de eerste dag
  of zoals het product, met of zonder beeld), de armen (de lezer en de schakelaars), wat gelabeld wordt en de eisen als
  tellingen; dezelfde functies als `/check`, de modellen via de Batch API op openbare data, Brave met een rem; `lezen`
  schrijft `te-labelen.jsonl`, `tellen` weigert zolang iets dat telt geen label heeft. Een nieuwe ronde is een nieuw
  meetplan, geen nieuwe module. #32.54: `--direct` stelt dezelfde vragen los en tegelijk in plaats van via de Batch API
  (PO: "hoe sneller hoe beter"); `foto` draait de foto bij de bron (`fotobron.py`, de kern) op de bewaarde antwoorden,
  per versie een eigen bestand, en `--snel` meet de tijd zoals het product; `overnemen` in het plan neemt antwoorden en
  labels van dezelfde arm over; een eis kan een aandeel van een andere telling zijn (`aandeel`, `van`))*
- De duelbeoordelaar: `python -m doublecheck.duelrechter ijken [--proef N]|tellen` *(#32.48a: de 100 kaarten van de twee
  duels blind in beide volgordes naar Claude Opus 5.5 en Gemini, geijkt op de keuzes van de PO; haalde de lat niet,
  BENCHMARK §250; grens $4)*
- *Niet bevestigd* nagerekend: `python -m doublecheck.narekening [<meetplan> ...]` *(#32.42: op de bewaarde antwoorden
  van #32.41 en #32.42, zonder nieuwe vragen; niet bij oud nieuws (de datum, of het jaartal in het bericht) en niet als
  een bron zonder band het bevestigt, met de eisen voor en na; ook de Portugese artikelen met de balk van recente koppen;
  $0; schrijft `data/meting/narekening.json`; BENCHMARK §223, §224; `lek` telt wat de waarschuwingen houden als de
  factcheckpagina's weg zijn, het dichte filter van #32.43, en schrijft `data/meting/lek.json`, §227; `koppen` telt
  welke koppen groen worden als de kop letterlijk op de eigen site van het genoemde medium staat, §232)*
- De Portugese W hersteld: `python -m doublecheck.talenset herstel --taal pt` *(#32.42: dezelfde steekproef W, per
  artikel één keer de pagina van pt.wikinews.org, één verzoek per 2 seconden met robots.txt en de User-Agent die
  Wikimedia vraagt; alleen de kop, de eigen datum en de alineatekst (`talenset.artigo_wikinews`), zonder de balk met
  de laatste koppen die in de dump het artikel verdringt; schrijft `data/talen/meting/pt-w.jsonl`, gemeten met
  `docs/meetplannen/32.42-pt-w.json`; BENCHMARK §224)*
- Verse sets voor `lezer-v10`: `python -m doublecheck.talenset vers --taal en|es|pt|de [--ronde 2]` *(#32.43, ronde 2 voor #32.56 zonder de eerste verse set en het duel: O, W en W-merk met
  een nieuw zaad, zonder iets uit de sets waarop de regels van §223 gebouwd zijn (`talenset.GEBRUIKT`); Wikinews zonder
  de balk met koppen, het Portugees van de pagina zelf; schrijft `data/talen/vers/<taal>.jsonl`, gemeten met
  `docs/meetplannen/32.43-<taal>.json`; weigert als de set al vastligt; `beeld --taal es|pt|de` kiest 60 bekende
  nepbeelden uit M4FC, alleen adressen, gemeten met `docs/meetplannen/32.46-beeld-<taal>.json`, §234; `datum --taal pt` haalt de artikelen van W
  zonder jaartal opnieuw op, met de datumcategorie van de pagina, naar `data/talen/vers/pt-w-datum.jsonl`, #32.44,
  §229)*
- De kaartenbak voor de PO, uit het nieuws zelf (zo voortaan): `python -m doublecheck.poproef nieuws --zaad <ronde>`
  *(20 koppen en 5 nieuwsfoto's van de afgelopen 2 dagen uit `poproef.FEEDS`, elk medium even zwaar; schrijft ook
  `docs/meetplannen/poproef-<ronde>.json` met de lezer uit config)*, dan `meting ... set|draaien --proef 1|draaien`,
  `trekken --meting poproef-<ronde> --zaad <ronde> --titel <tekst>` en `pagina`; de foto's alleen in het geheugen
  (`meting.beeld_bytes`). De oudere vorm, uit de meetsets:
  `python -m doublecheck.poproef berichten --zaad <ronde>`, een meetplan zoals het product
  (`docs/meetplannen/poproef-<ronde>.json`, zonder *eerste dag*) door `meting`, dan `trekken --meting <meetplan> --zaad
  <ronde> --titel <tekst> --voorraad <n>` en `pagina --zaad <ronde>` *(#32.45: alleen Engelse berichten uit westerse
  media, die de PO nog niet zag; zoals het product, PO 2026-11-07; de pagina https://claude.ai/artifact/Lu1jGzsqfcjdNgSL1115yW opnieuw publiceren vanuit
  `data/poproef/kaartenbak.html`; de keuzes van de PO per ronde in de database van die pagina; $0)*
- Factiz tegen gewoon zoeken: `python -m doublecheck.duel set --zaad <ronde>`, dan `meting docs/meetplannen/<ronde>.json
  set|draaien`, `duel gemini --zaad <ronde> [--proef N]` en `duel kaarten --zaad <ronde> --titel <tekst> [--bron <ronde>]`, daarna `poproef
  pagina --zaad <ronde>` *(#32.47, PO 2026-11-07: "Alleen Gemini": 25 nieuwsberichten en 25 verse nepberichten naar Factiz
  zoals het product en naar Gemini met Google Search (`gemini-4-argon`, `GEMINI_API_KEY` in `.env`), met de Nederlandse
  vraag van een gebruiker; de PO ziet per bericht A en B blind, kiest welk klopt en welk het meest helpt; de foto alleen in
  het geheugen; hervatbaar, grens $2; uitvoer in `data/duel/`)*
- Consensus naast de factchecks: `python -m doublecheck.consensus set|ophalen|kiezen`, daarna `vragen [--proef N]|lezen|tellen`
  *(#32.55, PO 2026-11-07: het nieuwsoverzicht van Wikipedia (Portal:Current events) tegen 300 Engelse berichten die er niet
  uit komen; per bericht de drie regels die er met bge-m3 het meest op lijken, Haiku zegt per regel bevestigt, spreekt tegen
  of niets (Batch API, openbare berichten); Wikipedia één verzoek tegelijk; `tellen` weigert zolang een bevestiging of
  tegenspraak geen label heeft in `docs/steekproeven/32.55-portaal.json`; grens $2; uitvoer in `data/consensus/`)*
- Waarom het nep is, de uitleg nagekeken: `python -m doublecheck.uitlegdekking <meetplan> vragen [--proef N]|lezen|tellen`
  *(#32.56, stap 7 van V1: per zin van de uitleg of die gedekt is door een bron die de lezer noemde, met wat de lezer ervan
  zag (`meting.wat_de_lezer_zag`, het veld `gezien` in de antwoorden); Haiku via de Batch API op openbare antwoorden;
  `tellen` weigert zolang een *niet gedekt* niet gelezen is in `docs/steekproeven/<meetplan>-uitleg.json`; eis 95%)*
- Netwerkdomeinen en klonen: `python -m doublecheck.netwerken bouwen|tellen` *(#32.58, B62: de lijst `netwerken.json` uit
  CheckFirst/DFRLab (Pravda), EUvsDisinfo (verspreiders met minstens 3 gevallen) en de extensies van Doppelgänger (EU
  DisinfoLab); een signaal met zijn bron, geen oordeel; `tellen` telt op alle metingen en de tiplineberichten, $0)*
- De speurstap als op de eerste dag: `python -m doublecheck.speuren set|draaien [--proef N]|wachttijd|lezen|tellen`
  *(#32.40: `lezer-v8` zonder (A) en met (B) de speurstap op O', M (nagemaakte merken), W2 en W-merk (echte koppen uit
  RSS), zonder kring 1, zonder checks uit de database en zonder factchecksites (`speuren.van_factchecker`; sinds #32.43
  elk lid van het IFCN en het EFCSN behalve `speuren.NIEUWSMEDIA`, en hun rubriek op het adres, §227); Sonnet via
  de Batch API op openbare data, de zoekresultaten alleen in het geheugen; `tellen` weigert zolang een rood, oranje of
  groen dat telt geen label heeft in `docs/steekproeven/32.40-speuren.json`; grens $8; BENCHMARK §217)*
- Het oudste beeld, een voormeting: `python -m doublecheck.oudstebeeld set|vision|paginas|lezen|tellen` *(#32.40: 100
  beelden uit de ijkset van M4FC door Google Vision, zonder factchecksites, van elke pagina beleefd de datum; `tellen`
  weigert zolang een oudste pagina van ruim vóór de factcheck geen label heeft in
  `docs/steekproeven/32.40-oudstebeeld.json`; grens $0,50; BENCHMARK §218)*
- De lijst met staatsmedia: `python -m doublecheck.staatsmedia bouwen` *(#32.11: Wikidata met RSF onder 55, de
  EU-sanctielijst, de aanwijzing van de VS in 2020 en een lijst die de PO nakijkt; een label, geen oordeel)*
- De aanvoer: `python -m doublecheck.vooruitblik ophalen --bijwerken` *(#32.7b: eerst alleen het versiekenmerk van de
  feed; bij een nieuwe stand de database bijwerken met `bootstrap --met-veto` achter de hittewacht op twee kernen; de
  dagelijkse taak staat in `deploy/org.factiz.vooruitblik.plist`)*
- De eigen radar (#32.69): `python -m doublecheck.beeldpaar set|teksten|lezen|lokaal|indienen [--proef]|ophalen|tellen|bronnen|opruimen`
  *(V1 en V2: het virale beeld naast het origineel uit hetzelfde factcheckartikel, lokaal en bij Sonnet, Opus en Fable
  5.2; labels in `docs/steekproeven/32.69-beeldparen.json`; BENCHMARK §257)* en `python -m doublecheck.radar
  luisteren --uren N|nieuws|vergelijken [--top 300]|soort [--top 300]|controleren [--top 50] [--proef N]|lezen|tellen|opruimen`
  *(V3 en V4: Bluesky via Jetstream, zonder tekst en zonder beeld op schijf; een index van nieuwsfoto's uit RSS; alleen
  PDQ telt als treffer; `soort` laat Haiku de soort beeld en de bewering zeggen, `controleren` haalt de meest gedeelde met
  een bewering door dezelfde functies als `POST /check`; `tellen` weigert zolang een gecontroleerde post geen label heeft
  in `docs/steekproeven/32.69-radar.json`; `opruimen` haalt de adressen met het account weg; grens $3,50)*

- Het proefdossier (#32.70): `python -m doublecheck.dossier kiezen|benoemen [--proef N | --toets] [--direct]|ophalen
  [--wacht M]|groeperen [--drempel 0.80]|terug [--grens 2025]` *(wat er ligt ordenen in een dossier (thema), verhaallijnen en cases: de
  beweringen van een thema op trefwoorden uit de database (alleen lezen), Haiku geeft per bewering de verhaallijn in één
  Engelse zin (`verhaallijn-v1`, Batch API op openbare beweringen), en de zinnen worden met bge-m3 gegroepeerd; de twee
  toetsverhalen van §111 erbij; `terug` telt hoeveel nieuwe beweringen horen bij een verhaallijn die er al was; uitvoer in
  `data/dossier/<thema>/`; grens $3)*

- Waarom het niet klopt (#34.2j, B77): `python -m doublecheck.waarom proef [--n] [--model]|indienen|ophalen [--wacht M]|lezen [--n 200]|regels|tellen|lezing-proef [--model] [--versie]|lezing-tellen|lezing-indienen|lezing-ophalen [--wacht M]|bekend`
  *(hoogstens drie korte punten uit de weerlegging van EUvsDisinfo, elk met een letterlijk citaat; Sonnet via de Batch API op
  openbare gevallen, grens $40; de regels (`herlees`, `REGELS`) werken op de bewaarde punten; `regels` legt ze naast de eerste
  leesproef; de tweede lezing (`lezing-…`, `LEZER`: `lezing-v2`, Haiku) zegt per punt of het iets toegeeft, een voorbehoud
  weglaat of iets toevoegt, en een ja telt alleen met woorden die er staan; `lezen` trekt 200 nieuwe pagina's voor de
  leesproef van de regels en de lezer van nu; de poort (`poort`) gaat open bij hoogstens 1 op de 100 punten niet gedragen
  (B77), in `docs/steekproeven/34.2j-waarom-v2.json`; `bekend` zet elk punt dat bij een leesproef niet gedragen bleek in
  `content/waarom-niet.json`, waar ook een gemelde fout komt: wat daar staat, komt in geen uitgave en `publiceren
  controleren` weigert het; uitvoer in `data/waarom/`. Op de site onder het oordeel, met de meting en *Meld een fout*)*
- Privépersonen in een bewering (#34.2bw, maatregel 2): `python -m doublecheck.privepersonen vragen [--proef N]|lezen|tellen|indienen|ophalen [--wacht M]|tweede`
  *(Haiku noemt per bewering een privépersoon bij naam, met de context (misdaad, ziekte, dood, seksualiteit) en of het een
  minderjarige is (`privepersoon-v1`, tien per vraag); een ja telt alleen met een naam die letterlijk in de bewering staat;
  `vragen`, `lezen` en `tellen` zijn de meting op 500 (`tellen` weigert zolang een ja, twijfel of een van de 100 getrokken nee
  geen label heeft in `docs/steekproeven/34.2bw-privepersonen.json`); `indienen` en `ophalen` lezen de hele uitgave via de
  Batch API (ook als stap van `verversen`, voor nieuwe beweringen); `tweede` laat Sonnet elke minderjarige in een gevoelige
  context nog eens lezen. `publiceren` zet in de tabel `afscherming` (schema 17) elke pagina met een privépersoon in een
  gevoelige context of een minderjarige, en elke pagina waarvan de tekst nog niet gelezen is; die gaat in geen stand naar
  een zoekmachine (`vindbaar.afgeschermd`, niet in de sitemap). Bij een minderjarige die beide lezingen bevestigden staat
  op de plek van de naam het merkteken `i18n.WEGGELATEN` in elke tekst van de pagina (`privepersonen.uitgave_invoer`);
  het platform maakt er ⟦naam weggelaten⟧ van in de taal van de site (`app.Weggelaten`, `merkDiep`), de site een sticker
  (`site/src/lib/weggelaten.jsx`, `.fz-weg`) met een voetnoot, en in een titel, omschrijving en het deelplaatje
  [naam weggelaten] (`i18n.plat`); grens $5; uitvoer in `data/privepersonen/`)*
- Alleen wat publiek is (#34.2ch, SPECS E9.S1 AC8): `python -m doublecheck.relevantie vragen [--proef N]|indienen|ophalen [--wacht M]|tweede|lezen|tellen`
  *(Haiku leest elke bewering: publiek of particulier (`relevantie-v2`, Batch API); Sonnet leest elke particuliere opnieuw
  met zes voorwaarden (`relevantie-tweede-v1`, direct); `publiceren` laat weg wat beide particulier noemden, alleen als
  `poort` open is (200 gelezen in `docs/steekproeven/34.2ch-particulier.json`, hoogstens 2 toch publiek en 5 twijfel; de gelezen greep ligt daar vast als `greep`, zodat nieuwe antwoorden de poort niet dichtzetten), en
  nooit wat ik als publiek of twijfel las of wat in een dossier staat; `verversen` leest nieuwe beweringen mee; grens $4 en
  $6; uitvoer in `data/relevantie/`)*
- De reikwijdte van het archief (B92, PLAN #37.14): `python -m doublecheck.reikwijdte proef [--ontwikkel]|lezen|indienen|ophalen
  [--wacht M]|tellen` *(Haiku labelt elke bewering internationaal, regionaal, lokaal, persoonlijk of twijfel, met de lat van
  de PO: lokaal is alleen echt plaatselijk; de poort op de gelezen greep in `docs/steekproeven/37.14-reikwijdte.json`,
  hoogstens 20 van de 200 fout; `weergave` vertaalt dan alleen `te_vertalen`; uit het archief gaat niets door deze scan)*
- De wereldlijst vertaald (PLAN #37.12 punt 5): `python -m doublecheck.wereldvertaling plan|indienen|ophalen` *(Sonnet,
  per overzicht en taal `content/wereldlijst/vertalingen/<sleutel>/<taal>.json`; één grens van $5 per week met de eigen checks)*
- De wereldlijst (B90, B91, PLAN #37.12): `python -m doublecheck.wereldlijst controleren|ronde|schalen|nakijken|pagina|akkoord`
  *(elke maandag om 6:00 de ingeplande taak `wereldlijst-ronde` volgens `docs/wereldlijst/RONDE.md`: vier opdrachten in
  `data/overzicht/<dag>/`, vier onderzoekers, de schaal, nakijken en de keuzepagina voor de PO; na haar keuze `akkoord
  --tot <dag> --keuzes <json> --akkoord '<datum>, PO: "…"'` naar `content/wereldlijst/<dag>.json`)* *(elke week een bestand
  `content/wereldlijst/<dag>.json` met de overzichten en het akkoord van de PO: de bewering in eigen woorden, waar ze
  rondging, wat de redacties vonden met [n] per zin, en per redactie haar oordeel, `schaal`, datum, titel en link;
  minstens één check uit het register of `wereldlijst.ERKEND`; `publiceren` maakt er gewone factchecks van (bron
  `factiz-wereldlijst`, tabel `samenvatting`, schema 18))*
- De feed gestopt (B91, PLAN #37.12): `python -m doublecheck.feedstop tellen` *(een check van Data Commons komt alleen nog in
  een uitgave als hij in de uitgave van 2026-11-23 stond, als paar van bewering en link in `doublecheck/feed_bevroren.txt.gz`
  (94.226); `publiceren bouwen` weigert zonder dat bestand; het lab blijft de feed lezen, voor de radar en de wereldlijst;
  nieuwe factchecks komen uit de wereldlijst (B90) en de eigen redactie; `vastleggen` weigert als het bestand er al is)*
- De publicatiedatabase (#33.1, SPECS E9.S1): `python -m doublecheck.publiceren bouwen [--uit <map>] [--concepten] [--release 2026-11-16b]|controleren <bestand> [--concepten]`
  *(de naam van een uitgave is haar dag; een tweede op dezelfde dag krijgt een letter, want haar D1 heet factiz-<naam> en
  een draaiende database wordt nooit overschreven, #34.2bp)*
  *(één bestand per release met alleen wat gepubliceerd mag worden: checks met een vrije herkomst (Data Commons, en een
  bron met `herverdeelbaar = 1`) van een toegelaten uitgever, één pagina per bewering of cluster, met naamsvermelding,
  linkstatus en waar het opdook; nooit zelf opgehaalde checks, Community Notes, vingerafdrukken of iets van een gebruiker;
  `controleren` weigert een ander schema, een bron die niet mag of een inhoud die niet bij het controlegetal past; leest
  de database van het lab alleen; uitvoer in `data/publicatie/<datum>/`. Sinds #33.5 gaan mee: de nagelezen correcties
  op de taal van een bewering (`taallabels.geldige_correcties`) en de Engelse vertaling die er ligt (tabel `vertaling`,
  ook in het zoekregister), behalve waar het lab de taal onbekend of Galicisch noemde (B32, §117). Sinds #34.2ak (schema
  10) per pagina de soort volgens de redactie en de vorm in de tabel `kenmerk` (`soortvorm.py`, zonder model: de nagelezen
  woorden in `docs/steekproeven/34.2ak-soortwoorden.json` en de Engelse woorden van de bewering))*
- De site als Worker (#34.2bo stap 7, B80): `node site/scripts/geheugen.ts <publicatie.db> data/d1/<release>/geheugen`
  *(het geheugen van een uitgave: alles wat het platform één keer rekent, want elke vraag aan D1 kost een Worker ~25 ms
  (stap 8), behalve een groot stuk dat bijna even snel te rekenen is; `NODIG` moet er altijd in (de afkortingen, de
  adressen, de kolommen, de thema's; de woordenlijst niet meer, die staat sinds #37.16 als tabel `woord` in de uitgave); gedeelde objecten en kringen
  komen precies terug; de kolommen alleen als kern (`kolommen:kern`, de rest maakt de Worker zelf); elk thema, dossier en de
  tellingen per thema, redactie en naam opgewarmd; `build:worker` weigert een geheugen van een andere uitgave dan de
  database in `wrangler.jsonc`)*, `node site/scripts/deelbeeld-voorraad.ts`
  *(de lettertypen en banden van het deelplaatje naar `data/deelbeeld/`, buiten git)*, dan `npm --prefix site run build:worker`
  *(`FACTIZ_DOEL=worker`: de Cloudflare-adapter, `#gegevens` wordt D1, uitvoer in `site/dist-worker/` met het geheugen onder
  `/_geheugen/` en het deelplaatje onder `/_deelbeeld/`, die alleen de Worker leest)*. Lokaal: de uitgave in een lokale D1
  (`npx wrangler d1 execute factiz-<release> --local --persist-to .wrangler/lokaal --file ../data/d1/<release>/deel-00N.sql`,
  vanuit `site/`), dan `npm --prefix site run worker:lokaal` (poort 8795). `python -m factiz_site.gelijk_worker
  [--node ... --worker ...]` legt de pagina's, zoekvragen en deelplaatjes van de Node-site en de Worker naast elkaar (met een
  eigen User-Agent: Cloudflare weigert die van urllib met fout 1010). Naar het account, alleen met een ja van de PO:
  `npx wrangler deploy --config dist-worker/server/wrangler.json` vanuit `site/` *(sinds 2026-11-16 op factiz.org en
  www.factiz.org als Custom Domains (`routes` in `site/wrangler.jsonc`), nog `noindex` met een robots.txt die alles dicht
  zet; www stuurt door en elk antwoord krijgt de koppen van het platform (`site/src/lib/koppen.js`); geen testadres meer;
  de Worker draait bij de database in Londen, `placement`; terug naar de tijdelijke pagina: `docs/RUNBOOK.md`)*. Een Worker
  heeft 128 MB: de woordenlijst staat daarom als tabel `woord` in de uitgave (#37.16: met elke vertaling 1,4 miljoen woorden,
  ~47 MB in het geheugen; `fts5vocab` geeft in D1 SQLITE_AUTH, dus `publiceren` maakt de tabel), en de adressen van links
  zijn vingerafdrukken (`tests/test_platform_ts.py` houdt die vorm vast), en het deelplaatje begint boven 12 MB aan lettertypen een nieuwe HarfBuzz.
  Een vraag aan D1 kost ~20 ms heen en terug (de SQL zelf 0 tot 1 ms): vragen die tegelijk gaan, bundelt de Worker in één
  batch (`site/src/lib/gegevens-worker.js`), dus stel onafhankelijke vragen met `Promise.all`, nooit na elkaar.
  Een pagina die klaar is, gaat in de cache van Cloudflare (`site/src/lib/paginacache.js`, via `site/src/middleware.js`):
  alleen GET zonder vraagteken, status 200, HTML of een deelplaatje, met de versie van de uitrol in de sleutel; een bezoek
  uit de cache telt via `Astro.locals.telling`. Kijk met de kop `x-factiz-cache` (`hit` of `miss`).
- Het platform in TypeScript naast Python (#34.2bo stap 3, B80): `python -m factiz_site.gelijk [<publicatie.db>]` *(stuurt
  dezelfde adressen naar de Python-app (TestClient) en naar `site/src/platform/api.ts` (in Node via
  `site/scripts/platform-vraag.ts` op `node:sqlite`) en noemt elk verschil; `factiz_site.gelijk.KLAAR` zijn de ingangen die
  TypeScript al beantwoordt; `tests/test_platform_ts.py` doet hetzelfde op een kleine uitgave. Bijzondere tekens in de
  TypeScript als escape (`\u2028`), nooit letterlijk)*
- Een uitgave naar factiz.org, in één commando (#34.2bo stap 9): `python -m doublecheck.uitrol voorbereiden [--release
  <naam>]`, dan met een ja van de PO `python -m doublecheck.uitrol live <release> --akkoord '<datum>, PO: "…"'` *(voorbereiden:
  bouwen, SQL en geheugen op de Mac, zonder het account, zonder naam de eerste vrije (vandaag, anders met een letter); live:
  de database aanmaken, importeren en nakijken, de binding `DB` in `site/wrangler.jsonc`, de Worker bouwen, uitrollen en
  factiz.org nakijken; de stand in `data/d1/<release>/uitrol.json`, na een fout verder bij de stap die misging; weigert een
  uitgave die al draait. Daarna `site/wrangler.jsonc` committen. Wat eronder zit, staat hieronder per stap)*
- De uitgave naar D1 (#34.2bo stap 2, B80): `python -m doublecheck.d1uitgave sql [<publicatie.db>]|aanmaken <release>|importeren
  <release>|nakijken <release>` *(`sql` alleen na `publiceren.controleer`, naar `data/d1/<release>/` (delen van hoogstens
  200 MB, elke opdracht hoogstens 90.000 bytes, de zoekregisters uit hun tekst opgebouwd, `klaar.json` als laatste); `aanmaken`
  een database `factiz-<release>` in West-Europa; `importeren` weigert een database met tabellen, dus nooit over de
  draaiende heen; `nakijken` legt elke rij van elke tabel, de controle van FTS5 en 18 zoekvragen naast de uitgave. Via
  `site/node_modules/.bin/wrangler` (aangemeld op het Ideelab-account); elke handeling op het account met een ja van de PO)*
- Oordelen die de tabel niet leest (#34.2o): `python -m doublecheck.oordeellezer werk|vragen [--proef N]|lezen|tellen`
  *(Haiku leest elke formulering van een redactie die `verdicts.py` `onbekend` noemt, met de regels van die tabel, en
  vertaalt elke korte formulering letterlijk in de vijf talen van de site (`oordeel-lezer-v1`, rechtstreeks, grens $1);
  niet wat de eigen lijst van een redactie geen oordeel noemt. Alleen in de publicatiedatabase, het lab houdt zijn
  oordelen; pas na mijn leesproef van 200 (geen fout naar de andere kant, geen verzonnen oordeel, hoogstens 5 buren) in
  `docs/steekproeven/34.2o-oordelen.json`, de vertalingen met een eigen poort. Uitvoer in `data/oordelen/`)*
- Lijkt op (#34.2p): `python -m doublecheck.hittewacht -- python -m doublecheck.lijktop rekenen`, daarna `lezen|tellen`
  *(per pagina de vijf dichtstbijzijnde andere pagina's met bge-m3 (de versie uit config) op de getoonde tekst: Engels,
  anders Nederlands, anders het origineel; op de grafische chip, vectoren in `data/lijktop/`, buiten de index van het lab.
  De drempel uit een leesproef van 50 paren per vak van de score, met een regel die vooraf vaststond, in
  `docs/steekproeven/34.2p-lijkt-op.json`; $0)*
- Eén bewering, meer redacties (#34.2bp, SPECS E9.S31): `python -m doublecheck.zelfdebewering
  kandidaten|proef|vragen|tweede|lezen|tellen` *(de paren van Lijkt op zonder gedeelde redactie; Haiku zegt per paar of
  het dezelfde bewering is (`zelfde-bewering-v2`, tien per vraag, direct), alleen vanaf een score van 0,84 (`VLOER`); een
  bewering over een foto of video telt alleen met dezelfde persoon op beide pagina's (`beeldregel`); `tweede` laat Sonnet
  elk *ja* opnieuw lezen; alleen *ja* van beide telt. De poort: 100 nieuwe paren gelezen in
  `docs/steekproeven/34.2bp-zelfde-bewering.json` (`gekozen`, `leesproef`), minstens 98 dezelfde bewering; dan neemt
  `publiceren` ze mee in de tabel `zelfde` (schema 12). Op de site *Ook gecheckt door*, een verwijzing, nooit een
  samenvoeging; elke lijst van checks met de dichtstbijzijnde eerst (`app.lokaal_eerst`, `lokaalEerst`). Grens $5;
  uitvoer in `data/zelfde/`. Na een nieuwe uitgave: eerst `lijktop rekenen`, dan `kandidaten`, `vragen` en `tweede` voor wat
  er bij kwam)*
- Taallabels nalopen voor het platform (#33.5): `python -m doublecheck.taallabels kandidaten|vragen [--proef N]|lezen|tellen`
  *(een bewering met een label dat onbekend, Galicisch of bij haar eigen site zeldzaam is, krijgt een tweede lezing van
  Haiku zonder het oude label (`taal-v1`, tien per vraag, direct, grens $0,50); `lezen` trekt 100 wijzigingen en 50
  ongewijzigde voor de leesproef in `docs/steekproeven/33.5-taallabels.json`; de correcties gelden alleen in de
  publicatiedatabase en alleen als 95 van de 100 kloppen. Het lab houdt zijn labels: een taalwissel daar raakt de
  cijfers per markt, B14)*
- Vertalingen voor weergave (#33.5, B32): `python -m doublecheck.weergave proef [--n 40] [--nieuw]|plan|indienen|ophalen [--wacht M]|lezen --taal <doeltaal> [--import]|tellen`
  *(een trouwe vertaling van elke bewering in de uitgave naar het Nederlands, Duits, Spaans en Frans (`weergave-v1`), en
  naar het Engels waar het lab geen Engelse versie schreef (nooit eroverheen, met Sonnet: Haiku had 3 van de 100
  fout, #34.2x; een methode is de vraag met het model, `weergave.METHODE`), en sinds #34.2be naar de tien nieuwe
  sitetalen (`weergave.NIEUW`, methode `weergave-v2/haiku`: zonder denkwerk, eigen grens `GRENS_NIEUW` van $39, eerst
  `proef --nieuw` in een eigen bestand): één vraag per bewering, Haiku (voor het
  Engels Sonnet) via de Batch API op openbare beweringen, grens $20; uitvoer in `data/vertalingen/`, buiten
  de database van het lab (de varianten daar zijn zoekvarianten met een vingerafdruk). Een doeltaal gaat pas in de
  uitgave na een leesproef van 100 in `docs/steekproeven/33.5-vertalingen.json`: geen betekenisfout en geen twijfel;
  bij één of twee blijft de brontaal van de fout uit, bij drie of meer de hele doeltaal (`weergave.poort`). Op de site
  gaat een vertaling in de taal van de site voor de Engelse; het origineel staat er altijd onder. Een paar dat ik fout
  las, in de greep of daarbuiten, staat nooit op de site (`weergave.bekend_fout`). Tot de ronde van 3 december (B93,
  PLAN #37.15) gaat wat alleen door de poort wegbleef voorlopig mee (`weergave.voorlopige`, in de uitgave `voorlopig = 1`,
  schema 20): op de site met de banner *Machinevertaling, wacht op een nieuwe vertaling*, nooit voor zoekmachines; zoeken op
  de site vindt haar wel, zoals elke vertaling (PLAN #37.16, schema 21). De controlestap:
  `python -m doublecheck.weergave controle proef [--versie controle-v2] [--model sonnet --wacht M]|tellen|indienen|ophalen`
  legt elke vertaling naast het origineel (`controle-v2` ook naast de Engelse versie die er al lag, `controle-v3` alleen
  naast die Engelse versie) en meldt een verschil in wie, wat, waar, wanneer of hoeveel; gemeten op de 400 gelezen paren:
  Haiku meldt 1 tot 2 van de 6 fouten en is niet op alles gedraaid, Sonnet alle 6 maar kost op alles $186; de PO beslist
  daarover bij de livegang (PLAN 33.9; minstens de Indiase talen, $35). Na een volle ronde geldt
  `weergave.poort_na`: alleen wat de controle doorliet, en een nieuwe leesproef (`lezen --taal nl --ronde 2`). Sinds
  #34.2x meet de leesproef de methode: ze ligt vast op de eerste ronde waarin een doeltaal gevraagd werd; elke
  `indienen` is een nieuwe ronde, die met dezelfde vraag zonder eigen leesproef op de site gaat (`weergave.toelating`). Na elke 5.000 nieuwe per doeltaal lees ik er 50 (`lezen --taal nl --import`, labels
  onder `na_import`); tot dan wacht wat erna komt, één fout zet haar brontaal uit, twee de doeltaal. Na een import:
  `publiceren bouwen`, `weergave indienen` en `ophalen`, en opnieuw `publiceren bouwen`)*

- De vormen van de wereldkaart (#34.2am): `python -m doublecheck.wereldkaart` *(uit Natural Earth 1:110m, versie 5.1.2,
  publiek domein, in `data/extern/naturalearth/` buiten git; projecteert met Equal Earth, vereenvoudigt, laat Antarctica
  weg en schrijft `site/src/kaart/wereld.json` met de herkomst; daarna de site opnieuw bouwen)*
- De soort nepnieuws, de voormeting (#34.2aj): `python -m doublecheck.soortlezer set|vragen [--proef N]|tellen|lezen`
  *(kan Haiku de soort (`truc-v1`-schaal) uit de bewering alleen halen? Op de 1.658 factchecks van #32.39 die in de
  uitgave staan, tegen de soort uit het artikel; tien per vraag, direct, grens $1; uitvoer in `data/soort/`. Uitkomst:
  nee, 43% bij de bevestigde, BENCHMARK §260)*

- Hoofdletters in normaal schrift (#34.2ae, SPECS E9.S15): `python -m doublecheck.hoofdletters kandidaten|vragen [--proef N]|lezen|tellen`
  *(een bewering of vertaling in hoofdletters (80% van de letters met een hoofd- en kleine vorm, minstens 12) krijgt één
  keer normaal schrift van Haiku (`hoofdletters-v1`, tien per vraag, direct, grens $1), alleen als er niets anders
  verandert dan hoofd- en kleine letters (`alleen_hoofdletters`); een vertaling staat in de uitgave in normaal schrift, de
  bewering blijft het citaat met `bewering_normaal` ernaast (schema 9), en `publiceren controleren` weigert een rij die
  meer verandert. Pas na mijn leesproef van 100 in `docs/steekproeven/34.2ae-hoofdletters.json` (geen fout, geen twijfel,
  hoogstens 5 klein); anders alleen met `bouwen --concepten`. Uitvoer in `data/hoofdletters/`. Na een nieuwe uitgave:
  `vragen` voor wat erbij kwam, dan opnieuw `publiceren bouwen`)*

- Dossiers voor het platform (#33.6, SPECS E9.S7, B72): een map per dossier in `content/dossiers/<sleutel>/` met
  `dossier.toml` (een mens: soort `verhaal` of `netwerk`, status `concept` of `akkoord`, thema, naam en één alinea in vijf
  talen, en de items uit pers, onderzoek, besluit of rapport, elk met datum, bron en link) en `factchecks.json` (wat een
  mens goedkeurde). `python -m doublecheck.dossiers kandidaten|voorstellen [--proef N]|toets|pagina|goedkeuren --keuzes
  <json> --dossier <sleutel>` *(kandidaten zijn alle pagina's van de uitgave met een van de woorden van het dossier; Haiku
  zegt per bewering ja, nee of twijfel (`dossiervoorstel-v1`, tien per vraag, direct, grens $0,50); `pagina` schrijft de
  leespagina voor de PO (`dossiers_pagina.html`, gepubliceerd als Artifact), `goedkeuren` zet haar keuzes in
  `factchecks.json` en haar hele lezing in `docs/steekproeven/33.6-dossier-<sleutel>.json`. Leest Claude eerst (AC3, PO
  2026-11-12), dan staat zijn lezing in `data/dossiers/<sleutel>/claude-lezing.json` met zijn twijfel in `groepen`;
  `twijfel --dossier a,b,…` schrijft één pagina met alleen die groepen (`dossiers_twijfel.html`, keuzes onder
  `dossiers/<sleutel>/groepen` en `…/keuzes`), en `goedkeuren --claude --akkoord '<datum>, PO: "…"' --keuzes <json>`
  (`{groepen: …, kaarten: …}`) zet zijn ja en nee en haar keuzes samen, met in de lezing wat van wie komt. `publiceren` weigert een
  dossier met een ontbrekend veld, een netwerk zonder bron per factcheck (B62) en een factcheck in twee verhaaldossiers;
  een concept gaat alleen mee met `bouwen --concepten`, naar `data/voorbeeld/`, en `controleren` weigert dat bestand als
  uitgave. De kerngetallen op de pagina rekent de site zelf uit de tabellen. Lokaal bekijken: het platform op de concepten,
  `FACTIZ_PUBLICATIE=data/voorbeeld/publicatie.db uvicorn --factory factiz_site.app:maak_app --port 8797 --no-access-log`
  met de site op hetzelfde bestand in de preview `factiz` (poort 8796). Niet te verwarren met `dossier.py`, de proef van #32.70. **Versies** (AC8): binnen
  een verhaaldossier is een versie hetzelfde bericht in andere woorden of een andere taal; `versies` vraagt Haiku in één
  vraag welke goedgekeurde factchecks hetzelfde bericht zijn (`dossierversie-v1`; boven de 80 in stukken die op elkaar
  lijken, `delen`, met de vectoren van *Lijkt op*), `versiepagina` schrijft de leespagina per groep
  (`dossiers_versies.html`) en `versiegroepen.json`, `versies-goedkeuren --keuzes <json>` zet in `factchecks.json` een
  `versie` bij wat de PO goedkeurde (met `--claude --akkoord '<datum>, PO: "…"'` wat Claude las, op haar akkoord). Op de site staat ze op de factcheckpagina onder *Komt ook voor als*, met een telling uit de
  tabellen; een factcheck buiten een dossier toont daar alleen wat het lab zelf samenvoegde)*

- Namen voor het platform (#33.7, SPECS E9.S11, DESIGN §4u): `python -m doublecheck.namen proef [--n 300]|vol
  indienen|ophalen [--wacht M]|tellen|zoeken [--max N]|kiezen indienen|ophalen [--wacht M]|kenmerken|samenstellen|staart
  [--n 100]|nakijken set|pagina|tellen --keuzes <json> [--door Claude --akkoord '<datum>, PO: "…"']` *(publieke personen, organisaties en plaatsen met hun nummer bij
  Wikidata: Haiku leest elke bewering van de uitgave, tien per vraag, en noemt hoogstens vijf namen (`namen-v1`, Batch
  API op openbare beweringen); elke schrijfwijze op minstens twee pagina's wordt opgezocht: eerst als titel bij de
  Engelse Wikipedia, vijftig per vraag, en wat daar geen artikel is bij de zoekfunctie van Wikidata; één verzoek
  tegelijk met een seconde ertussen (sneller remt Wikimedia af), als FactizResearch, hervatbaar. Haiku kiest uit de
  kandidaten of *geen* (`naamkeuze-v1`, met één vast antwoordschema voor elke vraag: een eigen schema per vraag loopt
  bij de aanbieder tegen vijftig nieuwe schema's per minuut aan); grens $6 samen.
  Een naam mag alleen op de site met een artikel in minstens 3 talen van Wikipedia, op minstens 5 pagina's, bij een
  persoon een mens volgens Wikidata en minstens 2 redacties, en zonder tegenspraak in de soort (een ding, wet, werk of
  gebeurtenis en een algemeen begrip zijn nooit een naam, `namen.WEG`); een paar telt alleen als
  de naam (of een vorm die Wikidata kent) letterlijk in de bewering of een vertaling staat; bij een persoon is een deel
  van de naam zelf genoeg, maar nooit een titel of een woord uit een omschrijving (`namen.genoemd`). Wat een
  mens weghaalt, staat in `content/namen-niet.json` en komt in geen uitgave. Namen gaan pas in de publicatiedatabase als
  `namen.poort()` open is: de steekproef is nagelezen (180 van 200, of wat met 95% zekerheid 90% draagt) **zonder één
  privépersoon**, door de PO of door Claude met een akkoord van de PO dat met haar woorden en de datum is vastgelegd
  (PO 2026-11-12; een lezing zonder akkoord opent niets, een akkoord zonder lezing ook niet); de lezing staat in
  `docs/steekproeven/33.7-namen-po.json`. Open sinds 2026-11-12: 195 van de 200 goed. Is de poort dicht, dan gaan namen
  alleen mee met `publiceren bouwen --concepten`, naar `data/voorbeeld/`. De site toont een naam als ingang, nooit als
  oordeel: `/names/` is een register op alfabet zonder tellingen, `/names/Q…/` de factchecks waarin de naam voorkomt, en
  `naam=Q…` een filter op de lijst. Sinds #34.2z gaan de andere schrijfwijzen die Wikidata kent mee in `naam_vorm`
  (schema 8, uit `data/namen/wikidata.jsonl`, `namen.bijnamen`), alleen om te zoeken: geen pagina toont een bijnaam,
  en welke helpen beslist `db._bouw_schrijfwijzen`. Uitvoer in `data/namen/`)*

- Het platform lokaal (#33.2):
  `uvicorn --factory factiz_site.app:maak_app --port 8799` *(leest de nieuwste `data/publicatie/<datum>/publicatie.db`,
  of het bestand in `FACTIZ_PUBLICATIE`; na een nieuwe bouw de server opnieuw starten. Het pakket `factiz_site/` leent
  niets uit `doublecheck`: `db.py` is de enige module die SQL spreekt (alleen-lezen), `i18n.py` de talen, de vaste teksten
  staan in `factiz_site/teksten/<taal>.json` (elke sleutel in alle vijf talen, `tests/test_factiz_site.py` weigert
  anders). Sinds #34.2f stap 4 heeft het geen eigen pagina's meer: een adres buiten `/api/` en `/robots.txt` is een kale
  404, en `/static` serveert de site)*
- De schil van het platform (#33.6b, SPECS E9.S10, DESIGN §4t; de Jinja-pagina's hieronder zijn weg sinds #34.2f
  stap 4, de site in `site/` doet dit nu): de kop met drie menugroepen en de taalkeuze als
  uitklappers (`details` met één `name`), op een telefoon in een lade (`popover`); één filterformulier met keuzelijsten
  en sorteren (`templates/_filters.html`), op een telefoon een lade van onderen; de voet in vier kolommen; kruimelpaden
  met microdata (`_kruimel.html`). Zonder script gebouwd. Het formulier stuurt lege keuzes mee: de app laat ze vallen en leidt
  door naar het ene adres van die lijst (`sorteer=oud|redacties`); bij zoeken gaan dezelfde filters in het bericht
  (`sorteer=nieuw|oud|redacties`, standaard de beste treffer). De vaste pagina's *Platform* en *Over Factiz*
  (`platform.html`, `over.html`) bestaan in alle vijf talen, met hun tekst in de woordenlijsten; bestaat een vaste
  pagina ooit in minder talen (`app.VASTE_TALEN`), dan wijst het menu van een andere taal naar de Engelse. Het onderzoek en de bronnen: `docs/voorstellen/2026-11-11-interface-ronde.md`

- Zoeken voorop (#33.6c, SPECS E9.S12, DESIGN §4v): de startpagina is het grote zoekveld in de band met het archief
  eronder; één zoekveld per pagina (in de kop, behalve op de start- en zoekpagina). Oordeel, taal en jaar zijn vinkjes
  (`db.MEER`, `?taal=en&taal=hi`); de aantallen bij elke filterwaarde rekent de site in het geheugen met numpy
  (`db._bouw_kenmerken`, `_masker`, `_tel_facetten`; een filter telt zichzelf niet mee), 3 tot 10 ms op de hele uitgave.
  Zoeken: `db.zoek_ruim` (treffers, aantallen, het aantal zonder filters, en een terugval op een deel van de woorden met
  `deels`), `db.ingangen` (een thema, dossier, redactie of naam die zo heet), `app.markeer` en `app.fragment` (de
  woorden van de vraag gemarkeerd, het stuk rond het gevonden woord)

- De look van de site op het platform (#33.6d, SPECS E9.S13, DESIGN §4w): `python -m doublecheck.velden platform`
  *(tekent per thema en per dossier een veld als band en als kaart, in de vijf families van factiz.org (familie en seed
  in `velden.THEMA_VELDEN`, een dossier uit zijn sleutel), naast de basisvelden in dezelfde map, en schrijft
  `factiz_site/static/velden.css` en `static/beeld/HERKOMST.md`; na een nieuw thema of dossier opnieuw draaien, ~2,5 s
  per veld. Bovenaan elke pagina een veld met de kop erop (in de site: `.kaartveld` in `site.css`), nooit achter een bewering,
  label of bron (D11); `tests/test_velden_platform.py` meet het contrast en eist de kopieën gelijk)*

- De site in Astro (B76, #34.2b, #34.2c, #34.2f): `npm ci --prefix site && npm --prefix site run build`, dan de preview `factiz`
  in `.claude/launch.json` (poort 8796) *(Astro 7 op de server met React, Tailwind 4 en Radix;
  de gegevens van het platform via `/api/<taal>/…`, dezelfde functies als het platform; `public/static` wijst naar
  `factiz_site/static`. Vijf talen, Engels op de hoofdmap en de andere onder hun code (`/nl/`), via één router
  `site/src/pages/[...pad].astro`; de pagina's in `src/components/site/paginas/`, de opmaak in `src/styles/site.css`
  (klassen `fz-…`, in `@layer components`). Canonical en hreflang volgen DESIGNSYSTEEM §6: een factcheck alleen in de talen
  met eigen tekst (`vindbaar` in `/api/<taal>/factcheck/…`, uit `factiz_site.i18n.eigen_talen`); het omveld van een
  bewering komt als `omveld` uit dezelfde ingang (`app.omveld`, #34.2h), en is `null` als er niets te zeggen is; een lijst met filters
  nooit. De site zegt `noindex, nofollow` tot `FACTIZ_VINDBAAR=1`. Sinds #34.2r tot #34.2u heeft ze elke pagina
  zelf (namen, thema's, dossiers, redacties, over, bronnen, platform, en sinds #34.2ah Verkennen op `/explore/`, met sinds #34.2ai het netwerk van namen op `/explore/network/`) en linkt ze nergens meer naar het platform; de
  Jinja-pagina's zijn weg (34.2f, stap 4), het platform is de gegevenslaag. De oude site is weg sinds #34.2f; het logo en de velden staan in
  `factiz_site/static/`, de opmaak en het menu van de demo van de API in `doublecheck/demo/`)*

- Anoniem tellen (#34.2ba, SPECS E9.S26, B78): op factiz.org telt de Worker in de D1 `factiz-tellingen` (binding
  `TELLINGEN`), te lezen met `python -m factiz_site.tellen --d1 factiz-tellingen [--dagen 14]`; lokaal telt de site alleen met `FACTIZ_TELLINGEN=<bestand>`;
  `python -m factiz_site.tellen [<bestand>] [--dagen 14]` toont per dag de bezoeken per soort pagina, de zoekvragen, die
  zonder resultaat (met het aandeel) en de robots *(`factiz_site/tellen.py`; per dag, soort en taal één getal, nooit een
  IP-adres, cookie of user-agent; de site meldt een bezoek via `tel` in `site/src/lib/platform.js` en stuurt
  `/api/tel` niet door)*; `--zoekvragen [--dagen 7]` toont per taal wat mensen zochten, alleen wat minstens drie keer kwam
  *(B94, PLAN #37.17: de site bewaart een gewone getypte zoekvraag van een mens, opgeteld per dag, in de tabel `zoekvraag`
  van dezelfde database (`site/src/lib/zoekvragen.js`, `telZoekvraag`); wat in zeven dagen minder dan drie keer kwam, ruimt
  de Worker één keer per dag op; nooit letterlijk op de site)*

- De zoekproef van het platform (#33.3): `python -m factiz_site.zoekproef [<publicatie.db>]` *(50 zoekvragen uit de
  beweringen zelf, tien per groep van schriften, vast zaad; eis 45 van 50 en 8 van 10 per groep; zoeken staat in
  `factiz_site/db.py` (`zoek`): eerst het register op woorden, dan dat op drietallen van tekens, dan doorlezen bij twee
  tekens. Een zoekvraag wordt op witruimte gesplitst, nooit op "woordtekens" (dat breekt Hindi en Tamil), gaat in het
  bericht en niet in het adres, en wordt nergens bewaard: de server draait met `--no-access-log`)*

- Zoeken op een geplakt bericht (#34.2au): `python -m factiz_site.berichtproef [<publicatie.db>] [--toets]` *(200
  beweringen als doorgestuurd bericht en 20 gewone berichten, zoals het zoeken nu is en zoals het wordt; `--toets` is
  het oordeel op zaad 2027 en 20 nieuwe berichten; de eisen in PLAN)*
- De randproef van het zoeken (#34.2y): `python -m factiz_site.randproef [<publicatie.db>]` *(48 gevallen in de vijf
  talen: enkelvoud en meervoud, samenstellingen, bijzondere letters, schrijfwijzen van namen, streepjes, hoofdletters,
  aanhalingstekens, kort, lang, filters, snelheid; vóór 10, na 44; sinds #34.2ab 62 gevallen met 14 afkortingen in
  hoofdletters, die een naam zijn als ze in de uitgave vooral die naam zijn (`Publicatie.afkorting`, de index in een eigen
  draad, `afkortingen_klaar`). De andere vormen van een zoekwoord komen uit het
  register zelf, aan de kant van de vraag (`db.vormen`, `Publicatie._groep`); wat precies zo staat, komt bovenaan;
  tussen aanhalingstekens niets anders dan wat er staat. Sinds #34.2ac 92 gevallen: een land, redactie, thema of
  onderdeel in de vraag verruimt en versmalt nooit (`_lees_kenmerken`, `_kenmerk_voorwaarde`, `gelezen`; `letterlijk`
  zet het uit), meteen naar de pagina alleen bij de volledige naam van een persoon of een dossier en bij een geplakte
  link (`Publicatie.doorsturen`, `adresvorm`), het woord afmaken (`Publicatie.aanvulling`, grijs in het veld, Tab
  neemt het over), een vraag naar de site zelf (`app.vaste_ingangen`), en suggesties binnen 100 ms)*

- Thema's voor het platform (#33.4): `python -m doublecheck.themas verkennen [--n 800]|tellen|toetsen --lijst <json>
  [--n 400]|uitslag --lijst <json>` *(Haiku benoemt van een steekproef uit de publicatiedatabase het onderwerp, een breed
  veld en het land (`themaverkenning-v1`); daarna zet het een andere steekproef bij een thema van een lijst of bij
  *anders* (`thema-v1`); de lijst is een bestand van 8 tot 15 thema's met hoogstens 8 onderdelen en nooit een derde
  niveau, anders weigert `lees_lijst`; direct, grens $1,50; uitvoer in `data/themas/`. De vastgestelde lijst staat in
  `content/themas.json` (namen in vijf talen). `hertoets|vergelijk` vraagt 400 nieuwe beweringen twee keer één per vraag
  en één keer tien per vraag (`thema-v2`, met het land als ISO-code); `vol indienen|ophalen [--wacht M]` is de volle
  ronde via de Batch API, grens $8; `nakijken set|pagina|tellen --keuzes <json>` trekt de 200 kaarten voor de PO,
  schrijft de nakijkpagina (`themas_pagina.html`, gepubliceerd als Artifact) en zet haar keuzes om in
  `docs/steekproeven/33.4-themas-po.json`. Thema's en landen gaan pas in de publicatiedatabase als `themas.poort()`
  open is (E9.S5 AC3): de PO las zelf 200 met minstens 180 goed, of uit wat zij las volgt met 95% zekerheid dat
  minstens 90% klopt (`themas.draagt`: 29 zonder fout, 46 met één); twijfel zonder keuze telt als niet goed. Open
  sinds 2026-11-11: 162 van de 163 goed)*

- Het openbare repo (#34.2bl, PO 2026-11-24: "Ja, schone start met een nieuw openbaar repo"): `python -m
  doublecheck.openbaar bouwen|maken [--van <ref>]` *(het lab blijft het repo waarin gewerkt wordt; `maken` zet een stand
  ervan als commit op de branch `openbaar`, met Factiz <info@factiz.org> als auteur en zonder co-auteurregel, zonder de
  werkmap te raken. Niet mee: `docs/voorstellen/`, `docs/pers/`, `docs/HANDOFF.md`, elke eigen check die niet
  gepubliceerd is, de beelden van posts (`factiz_site/static/redactie/`), de opmerkingen van de PO in de duels en de
  kaartenbak, en de tekst van zelf gelezen factchecks (`openbaar.VELDEN_WEG`, alleen id of link blijft). Weigert een
  thuismap, het eigen adres uit `git config`, een waarde uit `.env` en een regel uit `data/openbaar/weiger.txt`. Pushen
  naar het openbare repo alleen met een ja van de PO)*

## De kern en de metingen
- De dienst (`api`, `berichtcontrole`) leent alleen uit de kern: `machinevraag`, `feitvraag`, `vloervraag`,
  `beweringvraag`, `modellen`. Een meting leent uit de kern, nooit andersom; `tests/test_kern.py` bewaakt dat
  *(#32.7c)*. Een nieuwe vraag aan een model voor het product komt in de kern, de meting erbij in een eigen module.

## Werkafspraak
- Eén taak uit `docs/PLAN.md` per keer. Eerst de test, dan de implementatie, dan de
  suite draaien en de output tonen als bewijs.
- Commit na elke afgeronde taak: `[type]: [taak] (PLAN.md #N)`
- Geen regel `Co-Authored-By: Claude …` onder een commit of pull request, ook niet als het hulpmiddel er een voorstelt
  (PO 2026-11-24: "claude verwijderen eruit als co-author"; PLAN #34.2bl). Dit bestand gaat voor die standaard.
- Scope-wijzigingen gaan eerst naar `SPECS.md` / `DESIGN.md` / `PLAN.md`, pas daarna code.

## Conventies
Alleen wat afwijkt van wat je standaard zou doen:

- **Eén plek zet de categorie.** `matched` / `related` / `assessed` / `none` wordt
  uitsluitend bepaald door de categoriseringsfunctie. Geen tweede codepad mag een
  categorie toekennen. *(DR4, DR5)*
- **Elke fingerprint draagt zijn modelversie.** Vergelijken over versies heen is
  verboden; bij een mismatch weigert de resolver te draaien in plaats van stil door
  te rekenen. *(DR6)*
- **Drempels en modelversies komen uit config**, nooit uit code. Elke benchmarkrun
  legt de gebruikte waarden vast. *(DR6)*
- **Een engine-wijziging is een release.** Wie een modelversie of een
  poortdrempel in `config.toml` wijzigt, schrijft een nieuwe releasekaart in
  `docs/RELEASES.md` (mét de benchmarkrun erbij); de suite weigert anders. Geen
  release zonder verschoven cijfer, en wat slechter werd staat in de
  aankondiging zelf. *(B22)*
- **Elke markt draagt zijn eigen cijfer.** De benchmark weigert te draaien als een
  markt mét corpus geen testparen heeft. Een uitbreiding meet álle markten
  opnieuw; de poort ligt op het totaalcijfer, niet op de nieuwe markt. *(B14)*
- **Twijfel versoepelt nooit.** Waar een signaal onzeker kan zijn (taalherkenning,
  #12.4), valt de onbekende uitkomst terug op de strengste drempel. Nooit andersom.
- **Afgeleide testsetdata draagt zijn gedragsversie.** `numbers` en `negations` in
  de testset komen uit de extractiecode; verandert die, dan weigert de benchmark
  tot de testset herbouwd is. Wie een extractiemechanisme bijbouwt, zet er een
  proeftekst bij in `relation._PROEVEN`. *(#11.5, DR6-analoog)*
- **Elke tekstfunctie draagt een schriftcontract.** Een functie met één
  `str`-argument staat in `tests/test_schriftpaneel.py` — mét contract, of met
  een opgeschreven reden om haar over te slaan. Vijf keer ging dezelfde fout mis
  omdat niets hem merkte: de tests draaiden op Latijn en het cijfer werd beter
  *(§17a, §39, §45, §46, §48c)*. Het paneel draagt 24 schriften.
- **Artefactinhoud wordt nooit gelogd.** Logging staat uit op bibliotheekniveau, niet
  per aanroepsite. *(DR3)*
- **Een waarheidsoordeel alleen waar de meting het draagt.** Percentages mogen
  alleen voor match-zekerheid en systeemprecisie. Een positie op de
  waarheidsschaal komt uit één van drie lagen, altijd zichtbaar welke: checks van
  redacties (met bewijssterkte), signalen (met hun bron), of een eigen oordeel,
  en dat laatste uitsluitend per taal en soort claim waar de gepubliceerde
  precisie op ongeziene checks de poort haalt. Nooit "100%". *(DR2, B25)*
- **De waarheidsmeter is een meting**, en sinds B51 niet meer in het antwoord van `/check`; de
  regels hieronder gelden voor de metingen en voor een terugkeer na een nieuwe meting. Een stand van 1 tot 9 komt uit het
  gemeten aandeel ware berichten per oordeel en bron (`doublecheck/meter.py`,
  met interval, nooit tegen het oordeel in). 10 alleen voor een vastgesteld
  feit uit de feitenbasis dat twee sleutels bevestigen (`feitstap-v3`), in
  woorden. 0 is dicht (`meter.OPEN_UITEINDEN`, §154). Zonder check van een
  redactie of vrijgegeven soort bewering niet verder dan 3 en 7. *(B44)*
  Rood op algemene kennis (`vloer-v1`, zonder bron) is een eigen laag:
  hoogstens 3, alleen in een gemeten taal en alleen met een ijking van
  minstens 30 berichten. *(B50)*
- **Bouwen is vrij, bekijken alleen via het eigen domein (B78).** Een pakket met een open licentie (lettertype, iconen,
  bibliotheek) ophalen en bundelen bij het bouwen mag gewoon, met een vaste versie van minstens twee weken oud. De browser
  van een bezoeker laadt alleen van factiz.org. Wat een bezoeker stuurt, mag de server verwerken in het geheugen, nooit
  bewaren. Tellen mag alleen anoniem en opgeteld (geen IP, geen cookie); sinds B94 ook de getypte zoekvraag, opgeteld per dag
  en zonder iets dat een bezoeker herkent (PLAN #37.17). Wees niet strenger dan dit.
- Testnamen beschrijven het gedrag, niet de functie:
  `test_below_threshold_never_matched`, niet `test_categorize`.

## Do not
- Nooit `.env` committen.
- Nooit een artefact naar schijf, cache of externe dienst schrijven — alleen de
  fingerprint. Enige uitzondering: de betwistingsroute met expliciete toestemming *(B11)*.
  Sinds B55 gaat met `[berichtcontrole] beeld = true` ook het beeld van een screenshot mee naar het model, live, met
  eerst zwart wat de tekstherkenning als persoonsgegeven vindt (`opknippen.zwart_beeld`); bij Factiz nooit bewaard.
  De gemaskeerde bewering, nooit het artefact, mag voor één controle naar de
  modelaanbieder van B43, onder de standaard van Anthropic (hoogstens 30 dagen, geen training, B54); nooit naar schijf, log of
  cache *(B43, DR3)*.
- Nooit de Batch API, de Files API of webzoeken met *dynamic filtering* in het
  aanvraagpad gebruiken: die bewaren langer of anders (de Batch API 29 dagen, de Files API tot je wist), en zo
  blijft de route klaar voor zero data retention later *(B43, B54)*. De Batch
  API blijft voor offline werk op openbare data.
- Nooit beeld, video of geluid uit de batch, de zeef of trending op schijf
  bewaren; alleen wat eruit is afgeleid. Enige uitzondering: de ijkset *(B35)*.
- Nooit `matched` teruggeven onder de matchdrempel, ook niet als het de enige
  kandidaat is of de aanroeper erom vraagt *(B5, DR4)*.
- Nooit `assessed` presenteren in dezelfde vorm als `matched` *(DR5)*.
- Nooit een waarheidsoordeel of -percentage tonen of retourneren dat niet uit een
  van de drie lagen of de gemeten meter van B44 komt, en nooit een eigen oordeel in een taal of soort claim
  waar de poort niet gehaald is *(B10, DR2, B25)*.
- Niet de systeem-Python (3.9) gebruiken — die haalt `sentence-transformers` niet.
