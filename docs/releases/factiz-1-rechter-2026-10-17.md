# Factiz 1 release report

Generated on 2026-10-17 from benchmark runs #64 (2026-10-16) and #66 (2026-10-17) by `python -m doublecheck.releaserapport`. A measurement report, not an announcement: every number comes from a recorded run, `config.toml`, the conformance output or the release card.

## The sentence

Coverage from 81.6% to 81.6% on the same 4,839 test pairs in 21 languages, with the error bound from 0.22% to 0.22%.

Across languages: coverage from 92.0% to 92.0% on 50 pairs, errors 0.

## What changed in the engine

Nothing the runs record changed: text model, image hash, thresholds and claim variants are the same. A change outside those, such as OCR, shows only on the release card.

## What got worse, and what we still miss

Nothing got worse between run #64 and run #66.

Still missing:

- We do not find 434 of the 2,365 test pairs whose claim is known (18.4%).
- Lowest coverage: en 76.3%, es 77.0%, nl 77.5%.
- Highest error bound: en, 1 errors in 75 pairs (bound 6.17%).

From the release card (in Dutch; this covers what the runs do not measure, such as speed and memory):

> **Wat slechter werd.** De rechter maakt een tekstvraag trager en een werker
> zwaarder: `/resolve` op tekst van p50 0,21 naar 0,33 s en p95 van 0,26 naar
> 0,56 s, met één uitschieter van 6,2 s in de zeef (§126), gemeten op de
> processor van een M1 en nog niet op de server (op dezelfde laptop met twee
> rekenthreads na de release opnieuw: p50 0,30 tegen 0,17 s). De gewichten wegen
> 2,3 GB in float32 en een werker houdt ze in het geheugen: reken op ongeveer
> 6,7 GB per werker in plaats van 4,4, en dat is krap op de servermaat uit de
> RUNBOOK (8 GB). Op de laptop mat de RSS maar 0,3 tot 0,5 GB meer, maar onder
> geheugendruk telt macOS gecomprimeerde pagina's niet mee. De rechter is gekozen op de ontwikkelhelft van de zeef
> en gecontroleerd op een toetshelft die we al eerder zagen; een verse meting
> volgt met #28.6 d. Op gemaakte valkuilen (rollen omgedraaid, een andere
> lading, iets toegevoegd) zegt hij in 63 van 3.521 gevallen toch *zelfde*
> (1,8%, de lat was 2%, §130). Lange invoer wijst hij af: een artikel met kop
> en inleiding vindt minder dan alleen de kop (§131). De feitenlaag kent 40
> feiten en herkent alleen formuleringen die op de 280 in de laag lijken; een
> vastgesteld feit buiten de kern beschermt ze niet.
>
> Een vraag kost een tweede zoekvraag (#25.36): op
> 120 vraagposts verdubbelde de tijd van `/resolve`, p50 van 513 naar 1.007 ms
> en p95 van 1.274 naar 3.098 ms. Die tijden zijn gemeten terwijl de benchmark
> op dezelfde laptop draaide, dus absoluut te hoog; de verhouding klopt. Een
> bewering kost niets extra. En twee keer op de 15.376 geraakte webteksten
> wordt een vraag nu `related` op iets wat er niets mee te maken heeft
> (vertrouwen in Facebook met betaalgegevens, een Google-account herstellen);
> Ask zou die tonen als verwante check (§118).
>
> Twee keer lezen kost tijd op de beelden in de
> twijfelband: daar leest de OCR twee keer, binnen dezelfde grens van 10
> seconden. De regel is gemeten op beelden die we al kenden; de schriftcontrole
> werd bedacht na de eerste uitslag (§107). Een verse meting op onbekende
> beelden kan pas als de beeldindex van #25.11 groeit.
>
> Met de varianten één fout meer in de benchmark: 6
> in plaats van 5, de bovengrens van 0,22% naar 0,25%. Die zesde is dezelfde
> bewering (Salman Khan die Lawrence Bishnoi bedreigt) in een Assamese check
> die niet in hetzelfde cluster zit; de benchmark kent alleen het eigen
> cluster als goed (§84). Zoeken alleen wordt vijf tot negen keer trager (p95
> van 24 naar 223 ms), en een werker draagt 1,9 GB meer (4,4 GB). De winst
> zit uitsluitend in de vijf doeltalen: zoekvragen in Hindi, Malayalam,
> Kannada en Arabisch vinden niets meer dan voorheen.
>
> Van de wissel naar bge-m3: een vraag kost meer rekentijd en meer geheugen. Op
> twee kernen duurt embedden en zoeken samen mediaan 121 ms en in het
> langzaamste twintigste 188 ms, tegen 23 en 32 ms met MiniLM; zoeken alleen
> gaat van 11,5 naar 21,2 ms (rustige laptop, 94.103 claims). Met de negen
> talen erbij en de laptop in gebruik was dat 151 ms en 39,1 ms. Het model weegt 2,3 GB per werker in plaats van
> 0,5 GB (RUNBOOK). De batchcontrole vindt op de proefset één claim minder:
> 2 van de 28 bij 7 valse vlaggen op de gemeten poort 0,82, waar MiniLM er 3
> vond bij 10 (§77e).

> **Wat niet werkt.** Op de zeef, die meet wat er in het wild rondgaat,
> vinden we met de rechter 11,9% van wat redacties al checkten; de lat van V1
> is 70% (B33). Artikelen (0,5%) en beelden (1,1%) vinden we bijna nooit: daar
> zit het grootste gat, en dat is #30.11 en #30.4a. Bijna een vijfde van de bekende claims herkennen we
> nog niet (dekking 81,6%), en van twee formuleringen van dezelfde claim die
> redacties onafhankelijk schreven, vinden we er met de varianten 29,2% (§84).
> Een propaganda-artikel dat óver een ontkrachte bewering gaat, vinden we
> bijna nooit: 6 van 835 koppen, hoewel de juiste ontkrachting in een kwart
> van de gevallen bovenaan staat (§81). Een bijgesneden beeld verslaat
> beide hashes. In de negen Zuid-Aziatische talen kent de
> tegenspraakcontrole sinds #25.20 ook ontkenningen, maar die patronen komen
> uit grammatica's en zag nog geen moedertaalspreker (#25.20b); in het
> Arabisch, Perzisch, Turks, Chinees en Japans kent ze alleen getallen. Khmer,
> Assamees en Punjabi zitten met minder dan 500 claims in de index zonder
> eigen cijfer. Khmer herkent de schriftherkenning niet, dus twee keer lezen
> helpt daar niet (§107). Een bewering die een claim zoekt die als vraag is
> opgeschreven, wint met de varianten van #25.37 op de meetset (van 48% naar
> 58%), maar niet op echte paren: van 42 latere checks die alleen een eerdere
> vraag-claim hadden, vond Factiz er 16, voor en na. Daar zit het gat niet in
> de vraagvorm maar in andere woorden. De vraagvorm kent zes talen; in de andere valt alleen het
> vraagteken weg, en Engelse posts met twee vragen achter elkaar winnen weinig
> (van 10 naar 11 van 25).
> Het NLI-veto in de clustering trekt onder bge-m3 vaker dezelfde bewering
> uit elkaar: 53 van de 84 blokkades in het hele corpus, tegen 18 terecht en
> 13 twijfel (§86; onder MiniLM 38%, §44). Het blijft aan, omdat de
> omgekeerde fout duurder is. De
> batchcontrole van modeluitvoer en datasets is geen onderdeel van deze
> release: op echte data haalt ze recall 2/28 bij precisie 2/9 (§77e).

## Per language

| language | pairs | errors | error bound | coverage #64 | coverage #66 | change |
|---|---:|---:|---:|---:|---:|---:|
| total | 4,839 | 5 | 0.22% | 81.6% | 81.6% | +0.0 pt |
| nl | 523 | 0 | 0.57% | 77.5% | 77.5% | +0.0 pt |
| de | 285 | 0 | 1.05% | 81.7% | 81.7% | +0.0 pt |
| es | 494 | 0 | 0.60% | 77.0% | 77.0% | +0.0 pt |
| fr | 120 | 0 | 2.47% | 78.3% | 78.3% | +0.0 pt |
| en | 75 | 1 | 6.17% | 76.3% | 76.3% | +0.0 pt |
| crosslinguaal | 50 | 0 | 5.82% | 92.0% | 92.0% | +0.0 pt |
| ar | 200 | 0 | 1.49% | 85.0% | 85.0% | +0.0 pt |
| fa | 200 | 1 | 2.35% | 81.0% | 81.0% | +0.0 pt |
| hi | 198 | 1 | 2.37% | 82.0% | 82.0% | +0.0 pt |
| id | 196 | 1 | 2.40% | 79.2% | 79.2% | +0.0 pt |
| it | 189 | 0 | 1.57% | 84.3% | 84.3% | +0.0 pt |
| ja | 200 | 0 | 1.49% | 78.0% | 78.0% | +0.0 pt |
| pt | 194 | 0 | 1.53% | 90.4% | 90.4% | +0.0 pt |
| ru | 188 | 0 | 1.58% | 86.0% | 86.0% | +0.0 pt |
| tr | 200 | 1 | 2.35% | 88.0% | 88.0% | +0.0 pt |
| zh | 200 | 0 | 1.49% | 89.0% | 89.0% | +0.0 pt |
| bn | 225 | 0 | 1.32% | 85.3% | 85.3% | +0.0 pt |
| kn | 212 | 0 | 1.40% | 79.6% | 79.6% | +0.0 pt |
| ml | 229 | 0 | 1.30% | 77.8% | 77.8% | +0.0 pt |
| si | 207 | 0 | 1.44% | 79.6% | 79.6% | +0.0 pt |
| ta | 225 | 0 | 1.32% | 83.2% | 83.2% | +0.0 pt |
| te | 229 | 0 | 1.30% | 79.8% | 79.8% | +0.0 pt |

## For implementers

- Protocol: v0.1
- Thresholds in force: `text_match` 0.87 · `text_related` 0.79 · `image_same` 31 · `text_match_crosslingual` 0.87 · `cluster_same` 0.91 · `nli_contradiction` 0.5 · `stance_entailment` 0.7 · `screening_poort` 0.82 · `rechter_zelfde` 0.95 · `rechter_vloer` 0.79 · `rechter_veto` 0.6 · `feit_vloer` 0.79 · `feit_zelfde` 0.95
- Schemes: text `BAAI/bge-m3@5617a9f61b028005a4858fdac845db406aefb181+casefold` (no client scheme), image `pdq-256-v1`
- Claim variants: `claude-haiku-5-5/vertalingen-v1 · 458266 varianten; regel/vraagvorm-v2 · 3539 varianten`; a match through one says so in `via`
- Conformance: conformant, not fully tested: obligation 3 unobserved (11 checks, output of 2026-10-17).

## Check us

- `python -m doublecheck.benchmark` measures again what run #66 measured.
- `/numbers` lists every run with its misses.
- `python -m conformance <url> --proeven deploy/conformantie-proeven.json` checks the protocol obligations.
- The release card: `docs/RELEASES.md`, under "Huidige release".
