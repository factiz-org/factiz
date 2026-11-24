# Voorstellen 2026-08-27 — ter goedkeuring door de PO

> Opsteller: Lead Dev · Besluitstatus per 2026-08-27:
> **Voorstel 1 (B12): GOEDGEKEURD en doorgevoerd** in REQUIREMENTS.md (§1 + §8).
> **Voorstel 2 (DR8/E3.S4): VOLLEDIG GEACTIVEERD 2026-08-29.** De deterministische
> v0 kwam in etappe 3R (264 → 4 fouten op 1.000). Het NLI-deel was aangehouden tot
> er bewijs lag dat de semantische restklasse bestaat. **Dat bewijs is er nu** — niet
> uit de betwistingsroute maar uit de benchmark zelf: na etappe 8 (getallen) en 9
> (clustering) blijven vijf `inkorting`-fouten over, waarvan **twee standomkeringen**
> op echte corpusclaims: *solidariteit vóór boeren* tegenover *protest tegen boeren*,
> en *aanval van Israël* tegenover *Iraanse aanval op Israël*. Geen negatiewoord,
> geen getalconflict — onzichtbaar voor v0 en per constructie niet door v0 te vangen.
> Ingepland als etappe 10, met een modelspike als eerste taak.
> **Voorstel 3 (B13): TER BESLUITVORMING** — vastgelegd op verzoek PO; nog geen
> besluit nodig vóór het eerste externe pitchmoment (§9).

---

## Voorstel 1 — Onafhankelijkheid als kern-differentiator (REQUIREMENTS.md)

Aanleiding: gesprek 2026-08-27 over platform-eigen AI (Grok's "explain this
post"). De consumentenschil moet het *onafhankelijke* "Klopt dit?"-icoon worden;
platforms en AI's zijn afnemers van de resolver, nooit de motor erin.

### 1a. Toevoeging aan §1 Visie (nieuwe alinea, na de bestaande)

> Doublecheck is daarbij nadrukkelijk **platform-onafhankelijk**: het hoort bij
> geen platform, geen mediahuis en geen AI-leverancier. Waar een check-knop van
> het platform zelf het wantrouwen van zijn eigenaar erft, is Doublecheck de
> onafhankelijke check-laag die op elk platform aangeroepen kan worden. Die
> onafhankelijkheid is geen slogan maar een bewijslast — zie B12.

### 1b. Nieuwe rij in het besluitlogboek (§8)

| # | Beslissing | Reden |
|---|---|---|
| B12 | **Onafhankelijkheid is de kern-differentiator.** Doublecheck positioneert zich als platform-onafhankelijke check-laag, tegenover platform-eigen AI (Grok e.d.) en Big-Tech-tools (Google Fact Checked Claim Search). Platforms en AI's zijn afnemers van de resolver, nooit de motor erin; de consumentenschil (het onafhankelijke "Klopt dit?"-icoon) draagt deze positionering zodra de kern bewezen is (B3). Operationeel gedekt door: geen eigen waarheidsoordeel (B10), bronnen zichtbaar (DR1), consensus-telling (DR7), narekenbare cijfers (G3), geen artefact-opslag (B6), geldstroom niet van platforms (B2) | Vertrouwen is het enige actief van een check-laag; een platformknop erft het wantrouwen van zijn eigenaar. Geeft het aantoonbare antwoord op het differentiatierisico uit §9 (Google) |

Gevolg elders: geen. Scope v1 verandert niet; extensie/app blijven buiten scope
(§6) en komen uit het Verifyr-magazijn zodra de kern bewezen is.

---

## Voorstel 2 — Claim-relatie bepalen (SPECS.md + PLAN.md)

Aanleiding: bevinding taak 1.11. Het embeddingmodel plaatst het ontkenningspaar
dichterbíj́ elkaar (0.866) dan parafrases (0.843/0.858); de banden overlappen,
dus geen drempel scheidt ze. E1.S1-AC3 is daarmee op modelniveau niet haalbaar
(test staat op xfail). Retrieval vindt het juiste buurtje wél — wat ontbreekt is
een expliciet oordeel over de *relatie*: dezelfde bewering, het tegendeel, of
alleen verwant. Zonder mitigatie resolven tegengestelde beweringen elkaar als
`matched` — het incident uit B5, door de voordeur.

### 2a. Nieuwe domeinregel DR8 (SPECS.md, DR-lijst)

> **DR8** — Een vastgestelde tegenspraak-relatie resulteert nooit in `matched`,
> ongeacht de similariteit. Het relatie-oordeel is een uitspraak over
> claim-identiteit ("beweert dit hetzelfde?"), nooit over waarheid; B10/DR2
> gelden onverkort. Het relatiemodel draait lokaal (DR3) en zijn versie en
> drempels zijn configuratie (DR6).

### 2b. Nieuwe story E3.S4: Claim-relatie bepalen (SPECS.md, onder E3)

Als gebruiker wil ik dat een bewering die het tegendeel is van een gecheckte
claim nooit als "dezelfde claim" wordt gepresenteerd, zodat ik niet het oordeel
van de tegengestelde bewering opgeplakt krijg.

Werking: de bestaande zoeklaag levert top-N kandidaten (bi-encoder, goedkoop);
een lokaal meertalig NLI-model classificeert daarna alleen die paren als
`equivalent` / `tegenspraak` / `neutraal`. De relatie stuurt de categorie:
tegenspraak degradeert een kandidaat onvoorwaardelijk uit de `matched`-route.

**Acceptatiecriteria:**
- AC1 — Gegeven een artefact en een topkandidaat die elkaars tegengestelde
  zijn, wanneer geresolvet, dan is de relatie `tegenspraak` en de categorie
  nooit `matched`
- AC2 — Gegeven een tegenspraak, wanneer de respons wordt samengesteld, dan
  toont hij de relatie expliciet via het bestaande "wát komt overeen"-mechanisme
  van `related` (E3.S2-AC2), mét de bewijstoestand van de gecheckte claim —
  nooit in dezelfde vorm als `matched` (analoog DR5)
- AC3 — Relatiemodelversie en tegenspraak-drempel komen uit config en worden
  bij elke benchmarkrun vastgelegd (DR6); het model draait lokaal (DR3)
- AC4 — Gegeven de relatiecheck op de top-N, wanneer gemeten, dan blijft de
  p95-responstijd uit E3.S1-AC3 gehaald

> **Kritiek AC** *(DR8)*
> Gegeven het ontkenningspaar uit de seed ("Minister Jansen is afgetreden …" /
> "… is niet afgetreden …"), wanneer de ene helft wordt geresolvet tegen een
> index die de andere helft bevat, dan is de uitkomst nooit `matched`.
> Afgedwongen op: een test die faalt zodra dit wél gebeurt, plus mutatiecheck
> (zelfde regime als taak 1.6).

Verhouding tot E1.S1-AC3: dat AC blijft staan als gedocumenteerde
modelbeperking (xfail, strict). E3.S4 is de systeem-niveau ondervanging; het
systeemgedrag — niet de embeddingafstand — is voortaan de norm.

### 2c. Aanvulling E4.S1 (testset)

- AC4 (nieuw) — Gegeven de testset, wanneer samengesteld, dan bevat hij
  ontkenningsparen als aparte, gelabelde klasse binnen de niet-matches, en
  rapporteert de benchmark fouten op die klasse apart

### 2d. Redactioneel gevolg REQUIREMENTS §5 (kernlus)

`related`-omschrijving wordt: "gerelateerd (bv. zelfde beeld, andere bewering,
of: spreekt een gecheckte claim tegen), expliciet als zodanig".

### 2e. Inschuif in PLAN.md: Etappe 3R — Claim-relatie *(na etappe 3, vóór etappe 4)*

Ná de benchmark, zodat er een nulmeting bestaat waartegen het effect meetbaar is.

- [ ] **3R.1 Modelspike** — kandidaat-NLI-modellen (meertalig, lokaal) meten op
      de seed-ontkennings- en parafraseparen + latency op deze hardware; keuze
      en drempel vastleggen in config. Proof: meetrapport aan PO; configwaarden.
- [ ] **3R.2 Relatiemodule** — (artefacttekst, kandidaattekst) → relatie, met
      modelversie uit config. AC: E3.S4-AC3 · Proof:
      `test_negation_pair_classified_as_contradiction`.
- [ ] **3R.3 Integratie + kritieke afdwinging DR8** — relatiecheck vóór
      categorisering; tegenspraak kan nooit `matched` worden. AC: E3.S4-AC1 +
      kritiek AC · Proof: `test_contradiction_never_matched` + mutatiecheck.
- [ ] **3R.4 Respons** — relatie expliciet in de respons; DR2-walker dekt de
      nieuwe velden automatisch. AC: E3.S4-AC2 · Proof:
      `test_response_shows_contradiction_relation`.
- [ ] **3R.5 Benchmark herdraaien** — met ontkenningsklasse (2c) en
      p95-latencymeting. AC: E3.S4-AC4, E4.S1-AC4 · Proof: cijfers apart
      gerapporteerd, delta t.o.v. nulmeting.

**Etappepoort 3R:** 🔵 suite groen; kritiek AC DR8 aantoonbaar · 🟣 n.v.t. ·
🟠 benchmarkdelta en latency gezien; besluit of de ontkenningsfoutklasse
klein genoeg is voor de consumentenschil (B12)

### Wat expliciet níét verandert

- De vier categorieën van E5.S1 blijven; tegenspraak is een relatie bínnen
  `related`, geen vijfde categorie.
- Geen externe AI-diensten (DR3 onverkort; het NLI-model draait lokaal, zoals
  het embeddingmodel).
- B10: het relatiemodel spreekt zich nooit uit over waarheid — alleen over
  claim-identiteit.

### Open punten (horen bij de spike, niet bij dit besluit)

- Modelkeuze (kandidaten: meertalige NLI-cross-encoders, bv. mDeBERTa-XNLI-
  familie) en de tegenspraak-drempel.
- Gedrag bij `neutraal` op een hoge-similariteit-kandidaat (blijft `related`?).
- Of de relatiecheck ook `related`-kandidaten annoteert of alleen de
  `matched`-route bewaakt (kosten/baten in de spike meenemen).

---

## Voorstel 3 — Open source als verlengstuk van B12 (REQUIREMENTS.md)

Aanleiding: gesprek 2026-08-27, direct volgend op B12. Als onafhankelijkheid de
kern-differentiator is, is open code de diepste vorm van de bewijslast — en dan
moet het verdienmodel expliciet ergens anders liggen dan op de software.

### 3a. Nieuwe rij in het besluitlogboek (§8) — kandidaat-B13

| # | Beslissing | Reden |
|---|---|---|
| B13 | **Open source na bewezen kern; het verdienmodel ligt op de dienst, nooit op de software.** De resolver-code gaat open zodra (1) de G1-benchmark publiek gehaald is en (2) de naamkwestie uit §9 is opgelost. Betaald blijft, conform B2, de commerciële *inzet*: de geëxploiteerde dienst (verse, dagelijks bijgewerkte, continu gebenchmarkte index via de API), compliance-rapportage (DSA), en integratie/support. De claim-graph (B9), de NL-corpusdiepte (G4) en de operationele discipline (DR6: modelversies, herbouw, continue meting) zijn het bezit; de code is de bouwtekening. Open gaan: code, benchmarkmethode en testset (G3). Niet open: de geëxploiteerde index, infrastructuur, en betwiste artefacten (B11) | Open code maakt de B12-bewijslast controleerbaar op het laatste niveau — "audit me" in plaats van "geloof me" — en dient de standaard-ambitie uit B2 ("een standaard kan geen geld vragen aan wie hem legitimeert"). Er wordt weinig weggegeven: het bezit zit in data en discipline, niet in bewust saaie code. Een platform-fork erft bovendien per B12 het wantrouwen van zijn eigenaar — onafhankelijkheid is de slotgracht |

### 3b. Keuzepunten die bij activering beslist moeten worden (niet nu)

1. **Licentie** — AGPL (netwerk-copyleft: wie de dienst commercieel doorlevert
   deelt wijzigingen; beschermt tegen Big-Tech-freeriding) versus permissief
   (Apache/MIT: maximale adoptie, past bij het standaard-spoor; de slotgracht
   is dan uitsluitend index + merk). Afweging: standaard worden vs dienst
   beschermen.
2. **Corpusrechten** — de claims en oordelen zijn van de uitgevers
   (ClaimReview). Commercieel doorleveren vraagt afspraken; een omzetdeling
   mét factcheckers versterkt de B12-positionering (geldstroom naar de
   bronnen, niet van de platforms).
3. **Governance** — het publieke "Klopt dit?"-icoon mogelijk in
   stichtingsvorm, de commerciële API ernaast. Besluit ná bewezen kern.

### 3c. Aanvulling §9 risicotabel (twee nieuwe rijen)

| Risico / vraag | Impact | Nodig vóór |
|---|---|---|
| Corpusrechten: mag ClaimReview-afgeleide data commercieel doorgeleverd worden? | Raakt verdienmodel en uitgeversrelatie; omzetdeling als optie | eerste betaalde klant |
| Freeriding op open code door platforms/Big Tech | Raakt dienstomzet; mitigatie via licentiekeuze en indexbezit | open-sourcing (B13) |

### Wat expliciet níét verandert

- B7 (gebootstrapt) en B2 (gratis publiek/redactioneel, betaald commercieel)
  blijven staan; B13 preciseert alleen wát het betaalde ding is.
- Niets gaat open vóór G1 en de naamkeuze; tot die tijd blijft de repo privé.
