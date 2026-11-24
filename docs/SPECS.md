# Doublecheck — Specifications
> Owner: Product Owner · Status: **APPROVED** 2026-08-27
> Gebaseerd op: REQUIREMENTS.md (APPROVED 2026-08-27)

## Prioriteitenoverzicht

| Epic | Prioriteit | Stories | Dient doel |
|------|-----------|---------|------------|
| E1: Fingerprinting | Must | 4 | G1, G4 |
| E2: Claim-index | Must | 5 | G2, G3 |
| E3: Resolver | Must | 3 | G1, kernlus |
| E4: Benchmark & bewijs | Must | 3 | G1, G3, G4 |
| E5: API & testinterface | Must | 2 | scope v1 |
| E6: Privacy & bewijsdiscipline | Doorlopend | 3 | B6, B10, B11 |
| E8: Eigen oordeel, leraar en leerling | Must *(B42, 2026-10-23)* | 7 | B30, B33, B42 |
| E9: Het platform | Must *(B71–B74, 2026-11-10)* | 9 | B71, B72 |

## Domeinregels

Invarianten die het systeem moet **afdwingen** — geen features, maar voorwaarden die
nooit geschonden mogen worden.

1. **DR1** — Een `matched`-respons bevat altijd minstens één externe factcheck met
   **bron-URL en uitgever**. Nooit `matched` zonder aanwijsbare bron. De datum
   wordt gerapporteerd wanneer hij bekend is, en anders expliciet als onbekend
   (`null`) — nooit verzonnen. *(B1)*
   > *Aangepast 2026-08-30.* De datum was eerst een eis. Bij de omzetting naar de
   > CC BY-bron bleek 10,3% van de records geen `datePublished` te dragen — 10.193
   > claims die we weigerden. Een factcheck zonder datum is nog steeds een
   > factcheck, met een aanwijsbare uitgever en URL (BENCHMARK.md §36a).
2. **DR2** — Geen enkele respons of weergave bevat een waarschijnlijkheidspercentage
   over de wáárheid van een claim. Percentages zijn uitsluitend toegestaan voor
   match-zekerheid en systeemprecisie. *(B10)* **Aangepast door B25:** een positie
   op de waarheidsschaal mag alleen (1) uit checks van redacties, met
   bewijssterkte; (2) als signaal met de bron van het signaal; of (3) als eigen
   oordeel, en dan uitsluitend in een taal en soort claim waar de gepubliceerde
   precisie op ongeziene checks de poort haalt (99%; strenger voor platforms).
   Altijd zichtbaar uit welke laag de positie komt; nooit "100%", nooit een kaal
   percentage als waarheid. Tot laag 3 per taal zijn poort haalt, bestaat er geen
   eigen oordeel en geldt de oorspronkelijke regel onverkort.
   **Aangepast door B44 (2026-10-26):** een positie op de waarheidsschaal is een
   stand op de waarheidsmeter.
   - *Van 1 tot 9:* gemeten, uit het aandeel ware berichten met hetzelfde
     oordeel en dezelfde soort bron, met interval, en met woorden en dat
     aandeel erbij.
   - *0 en 10:* alleen voor een feit met oormerk uit de feitenbasis (B34), als
     *in strijd met een vastgesteld feit* en *vastgesteld feit*.
     - Stand 10 alleen als de feitenstap met twee sleutels het feit bevestigt
       (`feitstap-v3`, BENCHMARK §154).
     - Stand 0 is dicht (PO 2026-10-26). Een bericht dat een vastgesteld feit
       tegenspreekt krijgt de gemeten stand.
   - *Laag en grenzen:* de laag staat er altijd bij. Zonder check van een
     redactie of vrijgegeven soort bewering niet verder dan 3 en 7. Nooit het
     getal "100%", nooit een los percentage als waarheid.
3. **DR3** — Ingestuurde artefacten worden niet gepersisteerd. Enige uitzondering:
   de betwistingsroute met expliciete toestemming. *(B6, B11)*
   **Sinds B43 (2026-10-26):** een artefact verlaat de server nooit. Alleen de
   gemaskeerde bewering mag, voor de duur van één controle, naar de
   modelaanbieder van B43, die haar volgens zijn standaard hoogstens 30 dagen
   bewaart en er niet op traint (B54; eerst: onder zero data retention); bij
   Factiz nooit naar schijf, log of cache. **Sinds B55 (2026-11-03):** met
   `[berichtcontrole] beeld = true` gaat ook het beeld van een screenshot
   mee, live en voor die ene controle, met eerst zwart wat de
   tekstherkenning als persoonsgegeven vindt (`opknippen.zwart_beeld`);
   nooit bewaard bij Factiz. De gemaskeerde bewering is de tekst van het bericht, zonder
   chatomgeving en met persoonsgegevens gemaskeerd.
4. **DR4** — Onder de matchdrempel is het antwoord `related` of `none`, nooit
   `matched`. Bij twijfel: minder tonen. *(B5)* Met de rechter aan (#30.3,
   B36) is de matchdrempel tweeledig: vanaf `text_match`, tenzij de rechter
   onder `rechter_veto` blijft, en vanaf `rechter_vloer` alleen als de rechter
   `rechter_zelfde` haalt. Onder `rechter_vloer` nooit. Het antwoord noemt
   beide (PROTOCOL §3, verplichting 8).
5. **DR5** — `assessed` wordt nooit als `matched` gepresenteerd, in geen enkele
   respons of weergave. *(B1)*
6. **DR6** — Drempels en modelversies zijn configuratie, geen hardcoded waarden.
   Elke benchmarkrun legt de gebruikte configuratie vast. *(B5, G3)*
7. **DR7** — De fingerprint is van de **claim**, niet van het artefact. Verschillende
   artefacten van dezelfde bewering resolven naar hetzelfde claim-ID. *(B9)*
8. **DR8** — Een vastgestelde tegenspraak-relatie resulteert nooit in `matched`,
   ongeacht de similariteit. Het relatie-oordeel gaat over claim-identiteit
   ("beweert dit hetzelfde?"), nooit over waarheid; B10/DR2 gelden onverkort en
   detectie draait lokaal (DR3). *(Toegevoegd 2026-08-28 n.a.v. benchmarkrun #2:
   261 van 264 fouten waren betekeniswissel onder hoge tekstgelijkenis.)*
9. **DR9** — Een bewaard artefact bestaat uitsluitend met alle drie tegelijk:
   vastgelegde expliciete toestemming, een vervaldatum, en een intrekbare
   verwijdersleutel. Ontbreekt er één, dan wordt het artefact niet bewaard.
   Dit is de enige uitzondering op DR3 en geldt alleen op de betwistingsroute.
   *(B11; toegevoegd 2026-08-28 bij de uitwerking van E6.S3)*
10. **DR10** — Attributie is een bonnetje. Een herkomsttoeschrijving ("deze
    claim verscheen bij outlet X", "tracker Y koppelde dit aan operatie Z")
    bestaat uitsluitend mét bron, datum, link en bewijsniveau, en wordt nooit
    door het systeem zelf afgeleid. De bronsoort (factchecker, overheid,
    tracker, onderzoek, platform) is zichtbaar. Een attributie beïnvloedt nooit
    de categorie (DR4) of de consensustelling (DR7); het is context naast het
    oordeel, geen oordeel. Een bron wordt pas geïmporteerd als zijn licentie en
    attributietekst in het bronregister staan. *(B23; toegevoegd 2026-10-10 bij
    #24.6)*
    **Schrijfstijl** *(aangevuld 2026-10-17, B39)*: geen afzender en geen
    "dit klinkt als nep" afleiden uit stijl, opbouw of woordkeus. Stijl mag
    alleen een hulpsignaal zijn binnen de rechter of een gemeten eigen oordeel,
    onder de poort van B30.

---

## E1: Fingerprinting — Must

Elk binnenkomend artefact omzetten naar een fingerprint die claim-niveau aankan:
bestand tegen hercompressie, bijsnijden, herformulering en vertaling. Dient G1 en G4.

### E1.S1: Tekst-fingerprint
Als resolver wil ik een taalonafhankelijke representatie van een bewering, zodat
dezelfde claim in het Nederlands en het Engels naar hetzelfde punt resolvet.

**Acceptatiecriteria:**
- [ ] AC1 — Gegeven twee vertalingen van dezelfde bewering, wanneer beide worden
      gefingerprint, dan is hun onderlinge similariteit hoger dan die met een
      willekeurige andere claim uit de index
- [ ] AC2 — Gegeven een herformulering van dezelfde bewering (andere woordvolgorde,
      synoniemen), wanneer gefingerprint, dan geldt hetzelfde
- [ ] AC3 — Gegeven twee beweringen die elkaars tegenovergestelde zijn ("X is
      afgetreden" / "X is níét afgetreden"), wanneer gefingerprint, dan liggen ze
      aantoonbaar verder uit elkaar dan twee parafrases
- [ ] AC4 — De gebruikte modelversie wordt bij elke fingerprint vastgelegd *(DR6)*

### E1.S2: Beeld-fingerprint
Als resolver wil ik een perceptuele hash van een afbeelding, zodat een screenshot
dat door WhatsApp is hercomprimeerd nog steeds herkend wordt.

**Acceptatiecriteria:**
- [ ] AC1 — Gegeven een afbeelding en dezelfde afbeelding na JPEG-hercompressie op
      kwaliteit 60, wanneer beide gehasht, dan is de afstand onder de gelijkheidsdrempel
- [ ] AC2 — Gegeven een afbeelding en dezelfde afbeelding met 10% randafsnijding,
      wanneer beide gehasht, dan geldt hetzelfde
- [ ] AC3 — Gegeven twee visueel verschillende afbeeldingen, wanneer beide gehasht,
      dan is de afstand boven de gelijkheidsdrempel
- [ ] AC4 — Gegeven een afbeelding met een ander bijschrift maar hetzelfde beeld,
      wanneer geresolved, dan komt de uitkomst als `related` terug, niet als `matched`
      *(B8, DR4)*
- [x] AC4 — *(gehaald sinds B15; was uitgesteld zolang AC5 gold)*
- ~~AC5 — v1-inperking: bij leesbare tekst levert de beeldhash géén matchsignaal~~
      **VERVALLEN** *(B15, PO 2026-08-30)*. De inperking bestond om één reden:
      pHash gaf 250 van 250 valse koppelingen op niet-geïndexeerde tekstscreenshots.
      Met PDQ is dat 0 van 250 en gaat de beeldbenchmark van 261 naar 0 fouten op
      1.000 (BENCHMARK.md §29c). Beide routes draaien nu naast elkaar; een
      beeldtreffer zónder claimtreffer blijft `related` en nooit `matched` (B8, DR4).

> **Waarom deze inperking bestond** *(beeldbenchmark 2026-08-28, BENCHMARK.md §9;
> vervallen 2026-08-30, zie B15)*
> pHash codeert bij 32×32 DCT vooral de lay-out van een beeld, niet de inhoud.
> Voor screenshots van tekst betekent dat: 250 van 250 niet-geïndexeerde
> screenshots kwamen tóch binnen de drempel (afstand 2–4 bij drempel 10). Op
> visueel gevarieerde beelden werkt de hash wél (0 botsingen op 406 paren).
> Het onderscheid "tekstdominant beeld" versus "foto met bijschrift" is nog
> niet te maken; tot dat kan, kiest v1 de veilige kant. AC4 blijft daarmee
> gehaald voor beeld zonder leesbare tekst en is voor foto's mét bijschrift
> uitgesteld tot E1.S4.
>
> **Achteraf:** het onderscheid "tekstdominant beeld" bleek niet nodig. PDQ
> scheidt verschillende tekstkoppen ruim genoeg (42–74 van 256, tegen 0–6 van 64
> bij pHash), dus de val verdween in plaats van dat we hem moesten omzeilen.
> Bijsnijden blijft wél onopgelost — door geen van beide hashes (§29a).

### E1.S3: Screenshot → tekst
Als resolver wil ik de tekst uit een screenshot halen, zodat de tekstroute ook werkt
voor beeld — de meest voorkomende vorm waarin desinformatie circuleert.

**Acceptatiecriteria:**
- [ ] AC1 — Gegeven een screenshot van een nieuwskop, wanneer verwerkt, dan wordt de
      kop als tekst geëxtraheerd en apart gefingerprint
- [ ] AC2 — Gegeven een screenshot zonder leesbare tekst, wanneer verwerkt, dan valt
      het systeem terug op alleen de beeld-fingerprint zonder te falen
- [ ] AC3 — Gegeven een screenshot met zichtbaar bronlogo of URL, wanneer verwerkt,
      dan wordt die bron vastgelegd als *waargenomen*, niet als *geverifieerd*

### E1.S4: Crop-bestendige beeldhash (PDQ) — Should *(toegevoegd 2026-08-28)*
Als resolver wil ik een beeldhash die bijsnijden overleeft en tekstdominante
beelden onderscheidt, zodat de beeldroute ook echt dekking oplevert.

Aanleiding: pHash haalt E1.S2-AC2 niet (10% randafsnijding geeft afstand 14–20
bij drempel 10; op schaal 249 van 250 gemist) en botst op tekstscreenshots.
PDQ is de industriestandaard voor dit probleem en is crop-toleranter.

**Acceptatiecriteria:**
- [ ] AC1 — **Niet gehaald; de aanname erachter is weerlegd** *(gemeten 2026-08-30,
      BENCHMARK.md §29a)*. PDQ is niet crop-toleranter dan pHash maar slechter:
      genormaliseerd 0,469 tegen 0,250 bij 10% randafsnijding — praktisch
      willekeurig. Gemeten over drie beeldsoorten, met een positieve controle op
      schalen die wél slaagt. PDQ is gebouwd voor hercompressie, schalen en
      spiegelen, niet voor bijsnijden. E1.S2-AC2 blijft dus open.
- [x] AC2 — Gegeven de beeldbenchmark uit BENCHMARK.md §9, wanneer opnieuw
      gedraaid met PDQ, dan zijn de cijfers voor bijsnijden én voor niet-geïndexeerde
      beelden apart gerapporteerd en vergeleken met de pHash-nulmeting
      *(§29c: 0 fouten op 1.000 tegen 261; niet-geïndexeerd 0/250 tegen 250/250;
      bijsnijden onveranderd gemist)*
- [ ] AC3 — De hashversie staat in config en reist mee met elke fingerprint; naast
      elkaar bestaan van `phash-*` en `pdq-*` in de index is toegestaan, vergelijken
      over versies heen niet *(DR6)*
- [ ] AC4 — Gegeven de PDQ-cijfers, wanneer besloten, dan is vastgelegd of AC5 van
      E1.S2 (de v1-inperking) kan vervallen

> Randvoorwaarde: PDQ vergt een nieuwe dependency (stackwijziging, CLAUDE.md).
> Uitvoering is door de PO ingepland ná etappe 5.

---

## E2: Claim-index — Must

Het corpus van al-gecheckte claims opbouwen en doorzoekbaar maken. Dient G2 en G3.

### E2.S1: Corpus inlezen
Als beheerder wil ik bestaande factchecks importeren, zodat de resolver iets heeft om
tegen te matchen.

**Acceptatiecriteria:**
- [ ] AC1 — Gegeven de Google Fact Check Tools API, wanneer de import draait, dan
      worden claims opgehaald met bewering, oordeel, uitgever, URL, datum en taal
- [ ] AC2 — Gegeven een claim zonder uitgever-URL of datum, wanneer geïmporteerd, dan
      wordt hij geweigerd en gelogd *(DR1)*
- [ ] AC3 — Gegeven een herhaalde import, wanneer dezelfde claim opnieuw langskomt,
      dan ontstaat geen duplicaat

### E2.S2: Normaliseren naar claim-object
Als resolver wil ik één intern claimformaat, zodat bronnen met verschillende
verdict-woordenschat vergelijkbaar worden.

**Acceptatiecriteria:**
- [ ] AC1 — Gegeven verdicts uit verschillende uitgevers ("False", "Pants on Fire",
      "Onwaar", "Misleading"), wanneer genormaliseerd, dan vallen ze in een vaste,
      gedocumenteerde set categorieën
- [ ] AC2 — Gegeven een normalisatie, wanneer opgeslagen, dan blijft het originele
      verdict-label van de uitgever bewaard en opvraagbaar
- [ ] AC3 — Gegeven een onbekend verdict-label, wanneer verwerkt, dan wordt het als
      `onbekend` gemarkeerd in plaats van geraden

### E2.S3: Claims fingerprinten
Als resolver wil ik dat elke geïndexeerde claim dezelfde fingerprint-behandeling krijgt
als binnenkomende artefacten, zodat ze vergelijkbaar zijn.

**Acceptatiecriteria:**
- [ ] AC1 — Gegeven een geïmporteerde claim, wanneer geïndexeerd, dan bestaat er een
      tekst-fingerprint met dezelfde modelversie als de resolver gebruikt *(DR6)*
- [ ] AC2 — Gegeven een modelversiewissel, wanneer de index niet is herbouwd, dan
      weigert de resolver te draaien in plaats van stil te vergelijken over versies heen

### E2.S4: Meerdere checks per claim
Als gebruiker wil ik zien hoe vaak een claim onafhankelijk is weerlegd, zodat
"veertien keer weerlegd" zichtbaar sterker is dan "eenmaal gecheckt".

**Acceptatiecriteria:**
- [ ] AC1 — Gegeven meerdere factchecks van verschillende uitgevers over dezelfde
      claim, wanneer geïndexeerd, dan hangen ze aan één claim-ID *(DR7)*
- [ ] AC2 — Gegeven zo'n claim, wanneer opgevraagd, dan bevat het antwoord het aantal
      onafhankelijke uitgevers, de talen en de oudste datum — als telling, niet als
      score *(DR2)*


### E2.S5: Claims clusteren *(toegevoegd 2026-08-29)*
Als gebruiker wil ik zien hoe vaak een bewering onafhankelijk is weerlegd, ook
wanneer uitgevers hem anders formuleren of in een andere taal publiceren.

Aanleiding: DR7 belooft dat verschillende artefacten van dezelfde bewering naar
hetzelfde claim-ID resolven, maar het corpus levert dat niet. Slechts **3 van de
4.614** claims hebben twee of meer onafhankelijke uitgevers op tekstidentiteit
(taak 2.8), en dezelfde claim staat er in meerdere talen onder verschillende ID's
(benchmarkruns #3, #5 en #6). Zonder clustering telt een terecht gevonden
anderstalige tweeling als fout, en blijft "veertien keer weerlegd" een belofte.

**Werking.** Claims worden geclusterd op fingerprint-nabijheid, met twee
veiligheidsregels die uit de verkenning van 2026-08-29 volgen:

1. **Tegenspraak blokkeert samenvoegen (DR8).** Een claim en zijn ontkenning
   liggen in de vectorruimte dicht bij elkaar (taak 1.11: 0,866); zonder deze
   regel zou clustering ze samenvoegen — het ergst denkbare resultaat, want dan
   krijgt een bewering het oordeel van zijn tegendeel.
2. **Volledige koppeling, geen ketens.** Een claim voegt zich alleen bij een
   cluster wanneer hij boven de drempel ligt ten opzichte van **elk** lid, niet
   slechts één. Enkelvoudige koppeling laat A~B~C samensmelten terwijl A en C
   niets met elkaar te maken hebben.

**Acceptatiecriteria:**
- [ ] AC1 — Gegeven twee claims die dezelfde bewering doen, wanneer geclusterd,
      dan delen zij één cluster-ID *(DR7)*
- [ ] AC2 — Gegeven een claim en zijn ontkenning, wanneer geclusterd, dan komen
      zij **nooit** in hetzelfde cluster, ongeacht hun similariteit *(DR8)*
- [ ] AC3 — Gegeven een cluster, wanneer de bewijstoestand wordt samengesteld,
      dan telt hij de factchecks van **alle** leden: aantal onafhankelijke
      uitgevers, talen en oudste datum over het cluster heen *(DR7, E2.S4-AC2)*
- [ ] AC4 — De clusterdrempel komt uit configuratie *(DR6)* en clustering
      gebruikt uitsluitend fingerprints van één modelversie
- [ ] AC5 — Gegeven een `matched`-respons, wanneer samengesteld, dan is zichtbaar
      dat het om een cluster gaat en hoeveel claims erin zitten; het gerapporteerde
      claim-ID blijft het dichtstbijzijnde lid, zodat het contract van E5.S1 niet
      breekt
- [ ] AC6 — Gegeven de benchmark, wanneer een artefact een ánder lid van het
      doelcluster matcht, dan telt dat als gevonden en niet als verkeerde
      koppeling — mits het cijfer óók strikt (op exact claim-ID) gerapporteerd
      blijft, zodat clustering geen fouten kan wegpoetsen

> **Kritiek AC** *(DR8 in clustering)*
> Gegeven het ontkenningspaar uit de seed, wanneer het corpus wordt geclusterd,
> dan zitten beide claims in verschillende clusters.
> Afgedwongen op: een test die faalt zodra zij samen in één cluster belanden,
> plus mutatiecheck — hetzelfde regime als taak 1.6.

> **Randvoorwaarde, gemeten 2026-08-29.** Clustering op 0,90 levert 117 clusters
> over 260 claims, grootste cluster 6 — geen explosie. Wel bleek de
> tegenspraak-detectie 13 van de 158 kandidaatparen te blokkeren op een **valse**
> grond: Frans gebruikt een spatie als duizendtalscheiding, waardoor "40 000"
> uiteenviel in twee getallen tegenover het Nederlandse "40.000". Dat moet eerst
> gerepareerd, anders blokkeert DR8 legitieme samenvoegingen.


---

### E2.S6: Toelating tot de index *(B28, toegevoegd 2026-10-13)*
Als gebruiker wil ik alleen bonnetjes van echte redacties zien, zodat een treffer
nooit op een winkelrecensie of een onderschrift rust.

**Acceptatiecriteria:**
- [ ] AC1 — Gegeven een claim die met de hand als vaag is gelabeld, wanneer iemand
      zoekt (resolver, batchcontrole, varianten, beeld), dan is hij niet vindbaar, en
      zijn checks tellen niet mee in het bewijs van een cluster *(#25.28)*
- [ ] AC2 — Gegeven een database die de toelating draagt, wanneer een claim geen
      check heeft van een host uit het register, dan is hij niet vindbaar *(#25.29)*
- [ ] AC3 — Gegeven zo'n database, wanneer het antwoord bonnetjes toont, dan alleen
      checks van hosts uit het register *(#25.29)*
- [ ] AC4 — Gegeven een nieuwe host in de feed, wanneer het register wordt
      voorgesteld, dan komt hij in `te_beoordelen` en nooit vanzelf in het register
- [ ] AC5 — Gegeven een claim buiten de index, dan blijven claim en checks in de
      database; buiten de index is niet weg

## E3: Resolver — Must

Van fingerprint naar claim, met een expliciete gelijkeniscategorie. Dit is de kernlus.

### E3.S1: Similariteitszoekopdracht
Als API wil ik de dichtstbijzijnde claims vinden bij een fingerprint, zodat er iets te
categoriseren valt.

**Acceptatiecriteria:**
- [ ] AC1 — Gegeven een fingerprint, wanneer gezocht, dan komen de N dichtstbijzijnde
      claims terug met hun afstand
- [ ] AC2 — Gegeven een lege index, wanneer gezocht, dan komt `none` terug zonder fout
- [ ] AC3 — Gegeven een tekstartefact, wanneer gezocht, dan is de p95-responstijd
      onder 1 seconde *(was 500 ms; B36, 2026-10-17: ruimte voor de rechter)*;
      voor een artikel, een tekst van twee of meer zinnen die meetellen waarop
      de artikellezer leest, onder 3 seconden *(B41, 2026-10-21)*

### E3.S2: Categoriseren
Als gebruiker wil ik weten wélke soort match dit is, zodat ik niet denk dat een
gerelateerd beeld hetzelfde is als een weerlegde bewering.

**Acceptatiecriteria:**
- [ ] AC1 — Gegeven een afstand boven de matchdrempel, wanneer gecategoriseerd, dan
      is de uitkomst `matched`
- [ ] AC2 — Gegeven een beeldovereenkomst zonder claimovereenkomst, wanneer
      gecategoriseerd, dan is de uitkomst `related` met vermelding van wát overeenkomt
- [ ] AC3 — Gegeven een afstand onder alle drempels, wanneer gecategoriseerd, dan is
      de uitkomst `none`
- [ ] AC4 — Drempels komen uit configuratie en worden in de respons meegegeven *(DR6)*
- [x] AC5 — Gegeven de uitkomst `none`, wanneer de resolver antwoordt, dan zegt
      `reason` wat dat `none` waard is *(#25.35, PROTOCOL §6)*: `out_of_scope`
      als de taal van de tekst, zoals het corpus talen benoemt, niet in de
      index staat; `low_confidence` als er alleen op beeld gezocht kon worden
      (geen leesbare tekst, of alleen een beeldvingerafdruk); anders
      `not_found`. Een onzekere taal is geen `out_of_scope`: we zeggen alleen
      wat we weten. `reason` zet geen categorie en verandert er geen (DR4).

> **Kritiek AC** *(DR4 — dit is het incident waar het product aan doodgaat)*
> Gegeven een artefact waarvan de dichtstbijzijnde claim onder de matchdrempel ligt,
> wanneer de resolver antwoordt, dan is de uitkomst nooit `matched` — ook niet wanneer
> het de enige kandidaat is of de aanroeper om een match vraagt.
> Afgedwongen op: de categoriseringsfunctie is de enige plek die de uitkomstcategorie
> mag zetten, met een test die faalt zodra een respons `matched` bevat bij een afstand
> onder de drempel.

### E3.S3: Bewijstoestand samenstellen
Als gebruiker wil ik zien wie het checkte en wanneer, in plaats van een percentage.

**Acceptatiecriteria:**
- [ ] AC1 — Gegeven een `matched`-uitkomst, wanneer samengesteld, dan bevat het
      antwoord per factcheck: uitgever, oordeel, URL, datum, taal *(DR1)*
- [ ] AC2 — Gegeven meerdere checks, wanneer samengesteld, dan is de telling en de
      oudste datum aanwezig
- [ ] AC3 — Gegeven welke uitkomst dan ook, wanneer samengesteld, dan bevat het
      antwoord géén waarheidspercentage *(DR2)*
- [x] AC4 — Gegeven een check waarvan de link gecontroleerd is, wanneer
      samengesteld, dan draagt die check een object `link` met status
      (`live`, `offline`, `unclear`), datum van controle en een archiefkopie
      als die er is; een nooit gecontroleerde link geeft `null`
      *(#25.9, PROTOCOL §5)*
- [x] AC5 — Gegeven een check met een dode link, wanneer samengesteld, dan
      blijft die check in het antwoord en verandert geen telling: het oordeel
      ís het bonnetje *(#25.9, DR1, DR7)*
- [x] AC6 — Gegeven één dode waarneming, of twee binnen een dag, wanneer
      samengesteld, dan heet de link niet `offline`; een robotcontrole of
      time-out is nooit `offline` *(#25.9, twijfel versoepelt nooit)*

### E3.S4: Claim-relatie bepalen — v0: deterministische tegenspraak *(toegevoegd 2026-08-28)*
Als gebruiker wil ik dat een bewering die een gecheckte claim tegenspreekt niet als
"dezelfde claim" wordt gepresenteerd, zodat ik nooit het oordeel van het tegendeel
of van een andere-getallen-variant opgeplakt krijg.

v0 is bewust deterministisch (geen extra model): een getalsignatuur en een
negatiesignatuur per tekst, vergeleken tussen artefact en topkandidaat. Het
NLI-deel van het oorspronkelijke voorstel (VOORSTELLEN-2026-08-27.md) blijft
aangehouden tot de v0-meting er is.

**Acceptatiecriteria:**
- [ ] AC1 — Gegeven een artefact met een getal dat niet in de kandidaatclaim
      voorkomt (beide bevatten getallen), wanneer geresolvet, dan is de relatie
      `tegenspraak` en de categorie nooit `matched`
- [ ] AC2 — Gegeven een artefact en kandidaat waarvan er precies één een negatie
      bevat, wanneer geresolvet, dan is de relatie `tegenspraak` en de categorie
      nooit `matched`
- [ ] AC3 — Gegeven een tegenspraak, wanneer de respons wordt samengesteld, dan is
      de relatie expliciet zichtbaar (mechanisme van E3.S2-AC2) en de uitkomst
      hoogstens `related`

> **Kritiek AC** *(DR8)*
> Gegeven het ontkenningspaar uit de seed ("Minister Jansen is afgetreden …" /
> "… is niet afgetreden …"), wanneer de ene helft wordt geresolvet tegen een index
> die de andere helft bevat, dan is de uitkomst nooit `matched`. Afgedwongen op:
> de categoriseringsfunctie is de enige plek die de categorie zet en krijgt het
> tegenspraak-signaal als invoer; test + mutatiecheck (regime van taak 1.6).

---

## E4: Benchmark & bewijs — Must

Het falsifieerbare cijfer waar het hele product op rust. Dient G1, G3 en G4.

### E4.S1: Testset samenstellen
Als bouwer wil ik 1.000 beoordeelde paren, zodat precisie meetbaar wordt.

**Acceptatiecriteria:**
- [ ] AC1 — Gegeven de testset, wanneer samengesteld, dan bevat hij zowel paren die
      wél dezelfde claim zijn als paren die dat níét zijn maar er sterk op lijken
- [ ] AC2 — Gegeven de testset, wanneer samengesteld, dan is minimaal een
      gedocumenteerd deel Nederlandstalig *(G4)*
- [ ] AC3 — Gegeven de testset, wanneer opgeslagen, dan bevat hij geen artefacten die
      onder DR3 vallen — alleen verwijzingen en fingerprints
- [ ] AC4 *(toegevoegd 2026-08-28)* — Gegeven de testset, wanneer samengesteld, dan
      bevat hij ontkenningsparen als aparte, gelabelde klasse binnen de niet-matches,
      en rapporteert de benchmark fouten op die klasse apart
- [ ] AC5 *(toegevoegd 2026-08-29)* — Gegeven de testset, wanneer samengesteld, dan
      bevat hij **cross-linguale paren**: een artefact in de ene taal tegen de
      brontaal-claim in de index, apart gerapporteerd. Zonder deze klasse blijft de
      kern van E1.S1 — "dezelfde claim in NL en EN resolvet naar hetzelfde punt" —
      ongemeten, terwijl G4 en de EU-positionering erop leunen

### E4.S2: Meetharnas
Als bouwer wil ik met één commando de precisie meten, zodat elke wijziging afrekenbaar is.

**Acceptatiecriteria:**
- [ ] AC1 — Gegeven de testset, wanneer de benchmark draait, dan rapporteert hij het
      aantal verkeerde koppelingen, de dekking, en beide apart per taal
- [ ] AC2 — Gegeven een benchmarkrun, wanneer klaar, dan legt hij de gebruikte
      drempels en modelversies vast *(DR6)*
- [ ] AC3 — Gegeven een run met verkeerde koppelingen, wanneer gerapporteerd, dan is
      elk foutgeval individueel terug te zien

### E4.S3: Publiceerbare methode
Als buitenstaander wil ik de meting kunnen narekenen, zodat het cijfer iets waard is.

**Acceptatiecriteria:**
- [ ] AC1 — Gegeven de methodebeschrijving, wanneer gelezen, dan staat erin hoe de
      testset is samengesteld, wat als fout telt, en welke drempels gebruikt zijn
- [ ] AC2 — Gegeven het resultaat, wanneer extern gecommuniceerd, dan is het
      geformuleerd als foutratio met bovengrens, niet als percentage *(G1, B10)*

---

## E5: API & testinterface — Must

### E5.S1: `POST /resolve`
Als afnemer wil ik één endpoint dat een artefact aanneemt en een categorie teruggeeft.

**Acceptatiecriteria:**
- [ ] AC1 — Gegeven tekst, een afbeelding of een URL, wanneer gepost, dan komt precies
      één van `matched` / `related` / `assessed` / `none` terug
- [ ] AC2 — Gegeven een respons, wanneer gelezen, dan bevat hij het claim-ID, de
      categorie, de match-zekerheid en (bij `matched`) de bewijstoestand
- [ ] AC3 — Gegeven een te groot of onleesbaar artefact, wanneer gepost, dan komt een
      duidelijke fout terug, geen `none`

> **Kritiek AC** *(DR5)*
> Gegeven dat `assessed` in een toekomstige versie wordt aangezet, wanneer een respons
> wordt samengesteld, dan is `assessed` nooit in hetzelfde veld of dezelfde vorm te
> verwarren met `matched`.
> Afgedwongen op: categorie is één verplicht enum-veld op het antwoordobject; er is
> geen respons mogelijk zonder dat veld.

### E5.S2: Kale testinterface
Als bouwer wil ik zonder curl kunnen testen, zodat ik snel kan proberen.

**Acceptatiecriteria:**
- [ ] AC1 — Gegeven de interface, wanneer ik tekst plak of een afbeelding kies, dan
      zie ik de ruwe respons inclusief categorie en afstanden
- [ ] AC2 — Geen vormgeving verder dan leesbaarheid *(scope v1)*

### E5.S3: Ask Factiz, een vraag aan het corpus *(#24.10, PO 2026-10-15)*
Als lezer wil ik een vraag in gewone woorden stellen ("Zijn er biolabs in
Georgië?") en de gecheckte beweringen zien die er het dichtst bij liggen, met
wat redacties vonden en hun bronnen.

**Acceptatiecriteria:**
- [x] AC1 — Gegeven een vraag, wanneer gesteld, dan komen hoogstens vijf
      beweringen terug, elk met de categorie uit de categoriseringsfunctie en
      de drempels van de resolver; alleen `matched` en `related` komen in het
      antwoord, nooit een bewering onder de verwantdrempel *(DR4; de
      herordenaar als poort haalde de stiltemeting niet, BENCHMARK §114)*
- [x] AC2 — Gegeven twee beweringen uit hetzelfde cluster, wanneer getoond,
      dan staat het cluster één keer in het antwoord, met de bewering die het
      dichtst bij de vraag ligt
- [x] AC3 — Gegeven een getoonde bewering, wanneer samengesteld, dan draagt
      ze de bewijstoestand van E3.S3, en het label staat bij de bewering, niet
      bij de vraag: nergens een ja of nee op de vraag zelf *(DR2, B25)*
- [x] AC4 — Gegeven geen getoonde bewering, wanneer samengesteld, dan zegt
      het antwoord waarom, met dezelfde `reason` als een `none` *(PROTOCOL §6)*
- [x] AC5 — Gegeven een vraag, wanneer verwerkt, dan wordt ze niet bewaard of
      gelogd en staat ze nooit in een URL *(DR3)*; alleen de betwistingsroute
      bewaart iets, en de vraag zelf alleen met toestemming *(B11, E6.S3)*
- [x] AC6 — Gegeven de pagina, wanneer getoond, dan staat het gemeten cijfer
      van de testvragen erop, met de opzet, en onder elke uitslag *Wrong? Tell
      us* *(E6.S3)*
- [x] AC7 — Geen frontiermodel in het aanvraagpad en geen geschreven antwoord
      *(B26, B31)*
- [x] AC8 — Gegeven meer dan één getoonde bewering, wanneer gesteld, dan
      geeft het antwoord een samenvatting van de oordelen alleen als alle
      beoordeelde checks op dezelfde kant staan en geen twee getoonde
      beweringen elkaar tegenspreken; anders de reden waarom niet *(DESIGN
      §4e, PO 2026-10-15)*
- [x] AC9 — Gegeven een bewering in een andere taal dan de pagina, wanneer
      getoond, dan staat de vertaling er alleen met het origineel en *Machine
      translation*, en alleen voor een soort die de leesproef haalde *(B32)*
- [x] AC10 — Gegeven geen getoonde bewering, wanneer getoond, dan staan er
      tiplijnen van redacties in de taal van de vraag, elk met bron en datum
      van vastlegging, en anders geen *(DESIGN §4e)*

> **Kritiek AC**
> Gegeven het cijfer op de pagina, wanneer gemeten, dan draaide de meting door
> dezelfde functies als het endpoint. Afgedwongen op: `vraagtoets` en
> `POST /ask` roepen allebei `ask.kandidaten` en `ask.getoond` aan.

---

### E5.S4: De controle per bericht, `POST /check` *(B43, B44, B45; PLAN #31.12)*
Als gebruiker wil ik een tekst of screenshot sturen en horen of het klopt, op
de schaal van 0 tot 10 met woorden, en waar dat oordeel vandaan komt.

**Acceptatiecriteria:**
- [x] AC1 — Gegeven een tekst of screenshot, wanneer gecontroleerd, dan geeft
      het antwoord het oordeel (*klopt*, *klopt niet*, *let op*, *onzeker*,
      *satire* of *geen bewering*), de stand met woorden en de soort bron
      (B44), de bronnen (een passage van het web met link, of een check van
      een redactie uit de database met redactie, oordeel en link) en de
      versies van model, vraag en meter
- [x] AC2 — Gegeven een screenshot, wanneer gecontroleerd, dan wordt de tekst
      op onze server gelezen en het beeld niet bewaard; naar het model gaat
      alleen de gemaskeerde tekst, nooit naar schijf, log of cache *(B43,
      DR3)*
- [x] AC3 — Gegeven de schakelaar uit (de standaard), wanneer gevraagd, dan
      antwoordt de dienst 503 en vraagt ze geen model iets *(B43)*
- [x] AC4 — Gegeven het dagplafond bereikt, wanneer gevraagd, dan 503, vóór
      elke vraag aan een model; de kosten per dag worden bewaard zonder inhoud
- [x] AC5 — Gegeven *onzeker* zonder zoekopdracht, wanneer beantwoord, dan
      wordt het model nog één keer gevraagd, met de opdracht eerst te zoeken;
      het tweede antwoord telt *(§156)*
- [x] AC6 — Gegeven een vraag aan het model, dan is het vaste deel gemarkeerd
      om onthouden te worden, en is de tekst gelijk aan die van de metingen
- [x] AC7 — Een check van een redactie staat als check van een redactie in het
      antwoord; het eigen oordeel van het model nooit in die vorm *(DR5)*. De
      categorie van `/resolve` wordt hier niet gezet *(DR4)*
- [x] AC8 — Stand 10 alleen als de twee sleutels van de feitenstap hetzelfde
      feit bevestigen; stand 0 is dicht *(B44)*
- [x] AC9 — Nooit de Batch API, de Files API of zoeken met dynamic filtering
      in dit pad *(B43)*
- [x] AC10 — Gegeven een rode of groene uitslag, dan stelt de controle de
      vormvraag met de beoordeelde bewering. Een bericht over een bewering
      van een ander krijgt geen kleur (`colour` leeg, `rules` noemt
      `about_a_claim`). Een bewering over wat een beeld toont is zonder het
      beeld *onzeker* (`image_not_seen`). Geen regel maakt iets rood of groen
      *(PLAN #31.15, BENCHMARK §159)*
- [x] AC11 — Gegeven een echt verhaal met één vals detail (datum, getal,
      plaats of naam), wanneer gecontroleerd, dan is het antwoord *klopt
      grotendeels*. Het noemt de foute woorden letterlijk zoals in het bericht,
      de juiste waarde en de bron die die waarde noemt, en het is nooit groen.
      Staan de foute woorden niet letterlijk in het bericht, of noemt geen
      bron de andere waarde, dan geen *maar* *(B48, PLAN #32.3a)*
- [ ] AC12 — Gegeven *klopt grotendeels*, dan geeft het antwoord de plaats
      van de foute woorden: in een tekst de tekens, in een screenshot de
      kaders van de OCR. Alleen coördinaten, nooit het beeld *(B48, B43, DR3)*.
      *Stand 2026-10-28:* de tekens staan in `corrections` (`start`, `end` in
      `read`), ook bij een screenshot; de kaders in het beeld nog niet (#32.6)
- [x] AC13 — Gegeven een Engels bericht waarbij de machine *onzeker* of *let
      op* zegt (sinds `vloer-v2` met of zonder bron), wanneer beide vragen
      "clearly false" zeggen en de ijking van de laag *algemene kennis* stand 3
      draagt, dan is het antwoord *klopt niet*, `scale.layer` is `algemene
      kennis`, de stand is hoogstens 3 en `rules` noemt `common_knowledge`. In
      een andere taal of zonder ijking verandert er niets *(B50, PLAN #32.0m en
      #32.0n, DESIGN §4k, BENCHMARK §170–§171)*
- [ ] AC14 — Gegeven een bewering die betrouwbare media of een officiële bron
      zouden melden als ze waar was, wanneer na de eigen zoekvragen geen
      betrouwbare bron (band *goed* of officieel) haar bevestigt of
      tegenspreekt, dan is de uitkomst *niet bevestigd* (`outcome:
      unconfirmed`), zonder kleur, met de zoekvragen die de controle deed.
      Nooit bij een bewering die zulke bronnen niet zouden melden, en nooit bij
      geen bewering, satire of een bericht over een bewering van een ander
      *(B57, PLAN #32.41)*. *Voorstel, nog niet in het product (`lezer-v10`,
      PLAN #32.43):* ook niet bij een bericht waarvan het nieuwste jaartal
      drie kalenderjaren terug ligt, en niet als een onafhankelijke bron
      zonder band het bevestigt; dan *onzeker*
- [ ] AC15 — Gegeven een bericht, wanneer gecontroleerd, dan bedenkt een klein
      model vooraf tot drie zoekvragen (eigen site, echt nieuws, bron zelf),
      gaan die en het bericht zelf tegelijk naar de zoekdienst, en leest de
      lezer één keer; een zoekvraag die mislukt, telt als geen resultaat en
      laat de controle nooit vallen *(B57, PLAN #32.41)*
- [ ] AC16 — *Voorstel, nog niet in het product (`lezer-v11`, PLAN #32.46):* gegeven een bericht dat een kop
      brengt onder de naam van een medium, wanneer de lezer *klopt* zegt, niets het tegenspreekt en de kop woord
      voor woord in de titel staat van een pagina op de eigen site van dat medium, met band *goed*, dan is het
      groen, ook zonder een tweede uitgever. Een nagemaakte kop onder een echte naam staat daar niet *(§232)*

> **Kritiek AC**
> Gegeven de toets voor de beta (ronde 4), wanneer gemeten, dan draaide de
> meting door dezelfde functies als het endpoint: `berichtcontrole.voorbereiden`
> en `berichtcontrole.beoordeel`.

---

## E6: Privacy & bewijsdiscipline — Doorlopend

Geen eigen etappe; deze criteria worden bij **elke** etappepoort gecontroleerd.

### E6.S1: Geen artefactopslag
**Kritiek AC** *(DR3, B6)*
> Gegeven een willekeurige resolve-aanroep met een afbeelding, wanneer de aanroep klaar
> is, dan bestaat er geen kopie van die afbeelding op schijf, in een log, in een cache
> of bij een externe dienst.
> Afgedwongen op: een test die na een resolve-aanroep de opslag en logs controleert;
> logging van artefactinhoud is uitgezet op bibliotheekniveau, niet per aanroepsite.

### E6.S2: Geen waarheidspercentages
- [ ] AC1 — Gegeven welk antwoord dan ook, wanneer geïnspecteerd, dan bevat het geen
      veld dat de waarschijnlijkheid van waarheid uitdrukt *(DR2)*
- [ ] AC2 — Een test faalt zodra zo'n veld in het antwoordschema verschijnt

### E6.S3: Betwisting met toestemming *(uitgewerkt 2026-08-28)*
Als gebruiker wil ik een uitslag kunnen betwisten, zodat een fout hersteld kan
worden. Als bouwer wil ik betwiste gevallen kunnen teruglezen, zodat precisie
verbeterd kan worden op echte fouten in plaats van op zelfbedachte testsets.

Dit is de **enige** route waar een artefact bewaard mag blijven (DR3, B11).
Daarom is de uitwerking streng: bewaren kan alleen met alle drie de
voorwaarden uit DR9 tegelijk.

**Werking.** De resolver is bewust toestandloos: er bestaat geen serverzijdig
resultaat om naar te verwijzen, en er wordt tussen resolve en betwisting niets
vastgehouden. Een betwisting draagt daarom zelf het artefact aan, samen met de
categorie die betwist wordt en de betwistingstekst. Dat is meteen het moment
waarop toestemming concreet gevraagd kan worden — precies de reden van B11.

**Wat er in beide gevallen wordt opgeslagen:** de fingerprint(s) met hun
modelversie, de betwiste categorie, de betwistingstekst, en het tijdstip.
Fingerprints zijn geen artefacten en vallen dus niet onder DR3.

**Wat er alléén met toestemming bij komt:** het artefact zelf, met een
vervaldatum en een verwijdersleutel.

**Acceptatiecriteria:**
- [ ] AC1 — Gegeven een betwisting, wanneer die wordt aangeboden, dan is
      toestemming een expliciet en apart veld; afwezigheid telt als weigering en
      er wordt nooit een impliciete of vooraf aangevinkte toestemming aangenomen
- [ ] AC2 — Gegeven geen toestemming, wanneer de betwisting wordt opgeslagen, dan
      bevat hij alleen de fingerprint, de betwiste categorie en de
      betwistingstekst *(B11)*
- [ ] AC3 — Gegeven een bewaard artefact, wanneer de bewaartermijn verstrijkt, dan
      wordt het artefact verwijderd terwijl de fingerprint en de betwistingstekst
      blijven bestaan — de analysewaarde overleeft de bewaartermijn, het artefact niet
- [ ] AC4 — Gegeven een betwisting mét toestemming, wanneer die is opgeslagen, dan
      krijgt de indiener een verwijdersleutel terug waarmee het artefact op elk
      moment vóór de vervaldatum verwijderd kan worden *(verwijderrecht, B11)*
- [ ] AC5 — De bewaartermijn komt uit configuratie, niet uit code *(DR6)*
- [ ] AC6 — Gegeven bewaarde betwistingen, wanneer een bouwer ze opvraagt, dan zijn
      ze als foutgevallen te lezen: betwiste categorie, betwistingstekst, en of er
      nog een artefact bij zit
- [ ] AC7 — Gegeven de betwistingsroute, wanneer een artefact wordt bewaard, dan
      staat het in de database en nooit als los bestand op schijf, zodat verwijderen
      één handeling is en er geen kopie kan achterblijven

> **Kritiek AC** *(DR9, DR3 — dit is de enige plek waar de privacybelofte kan breken)*
> Gegeven een betwisting zónder expliciete toestemming, wanneer de aanroep klaar is,
> dan bestaat er nergens een kopie van het artefact: niet in de database, niet op
> schijf, niet in een log, niet bij een externe dienst.
> Afgedwongen op: een test die na de betwisting alle vier de kanalen controleert,
> met mutatiecheck — hetzelfde regime als E6.S1.

> **Buiten scope voor v1.** Een redactionele afhandeling van betwistingen (wie
> beoordeelt, hoe wordt teruggekoppeld) hoort bij de consumentenschil; v1 levert de
> route en het analysemateriaal, niet het proces eromheen.

---

## Won't have (v1)

| Niet bouwen | Reden |
|---|---|
| `assessed` (eigen AI-oordeel) zonder poort | De motor bestaat in Verifyr; v1 moet eerst `matched` bewijzen *(B3)*. **Herzien 2026-10-23 (B42):** het eigen oordeel is nu epic E8, maar alleen per klasse die de poort van B30 haalt |
| Consumenten-webapp met vormgeving | UI op een onbewezen kern is verspilling *(B3)* |
| Browserextensie & iOS-app | Bestaan al in Verifyr, komen mee zodra de resolver staat |
| Accounts, betalingen, licentiebeheer | Geen betalende gebruiker in v1 |
| Platform-integraties, WhatsApp-tipline | Vereist bewezen dekking en cijfers |
| Eigen menselijke redactie, IFCN-traject | Maakt je concurrent van wie je indexeert *(B1)* |
| Audio- en videoforensiek | Buiten de kernlus |
| Meertalige UI | De tien talen uit Verifyr komen later mee |

## Niet-functionele eisen

- **Prestatie:** `/resolve` p95 onder 1 s voor tekst, onder 3 s voor een artikel (twee of meer zinnen, met de artikellezer) en voor beeld (inclusief OCR); video in V2 *(B36, B38, B41; was 500 ms en 2 s)*
- **Platform:** server-side API; geen browserafhankelijkheden in de kern
- **Data:** geen artefactpersistentie *(DR3)*; index en fingerprints wel
- **Reproduceerbaarheid:** elke benchmarkuitkomst herleidbaar tot drempels en modelversies *(DR6)*

---

## E7: Toegeschreven attributie — Should *(B23, #24.6)*

Het corpus verbreedt van de ClaimReview-feed naar alle debunk-bronnen, en elke
herkomsttoeschrijving is een bonnetje (DR10). De resolver blijft doorgever: de
kaart (B23) toont wie wat zei, nooit wat wij denken.

**E7.S1 — Bronregister.** Elke bron buiten de feed staat in het register met
soort, licentie, attributietekst, url en of zijn records herverdeelbaar zijn.
- AC1: een bron zonder licentie of attributietekst kan niet geregistreerd worden
  (schema-CHECK, geen applicatiecode).
- AC2: `--herkomst` (15.3) weegt bronnen met `herverdeelbaar = 0` mee als gebonden.

**E7.S2 — Attributie als bonnetje.** Een attributie koppelt een claim aan een
actor (operatie, outlet, netwerk of platform) met bron, datum, link en bewijsniveau
(`waargenomen`: de bron zag de claim daar verschijnen; `toegeschreven`: de bron
schrijft de claim toe aan een operatie).
- AC1: zonder bron, datum, link of bewijsniveau weigert de opslag.
- AC2: de categorisering en de DR7-telling lezen de attributietabel niet.

**E7.S5 — Attributies in het antwoord** *(PROTOCOL §11.7, PO 2026-10-12)*. Bij
de checks geeft het antwoord de attributies van dezelfde claims (het cluster),
op datum, als optioneel veld `evidence.attributions`.
- AC1: elk item heeft actor, actorsoort, bron, bronsoort, niveau, datum en link.
- AC2: de categorie en de telling van redacties zijn met en zonder attributies
  gelijk (DR7, DR4).
- AC3: een client die het veld niet kent, krijgt verder hetzelfde antwoord.

**E7.S6 — Tweede bron: Community Notes** *(#25.16, PO 2026-10-12)*. Een
behulpzame note die naar een check in ons corpus verwijst, wordt een
attributie van niveau `waargenomen`: actor X (soort `platform`), bron
Community Notes (soort `platform`, licentie X Developer Agreement, niet
herverdeelbaar), de datum van de note en een link naar de note.
- AC1: alleen notes die nu behulpzaam zijn, en alleen bij een check in het corpus.
- AC2: de notetekst wordt niet bewaard en niet getoond.
- AC3: met deze bron in de database meldt `--herkomst` de database als
  niet uitgeefbaar (E7.S1-AC2).

**E7.S3 — Actoren en aliassen.** Dezelfde operatie heet bij drie onderzoekers
anders (Matryoshka, Operation Overload, Storm-1679); aliassen reconciliëren naar
één actor, zoals claims clusteren.
- AC1: een alias-opzoeking is hoofdletter- en witruimte-ongevoelig en verzint
  nooit een actor: onbekend blijft onbekend.

**E7.S4 — Eerste bron: EUvsDisinfo.** De CC BY-snapshot (Mendeley yhdtkszvgp
v3, 2015–2022, 14.497 gevallen) van de EEAS-database, onder de EEAS-reuse-regel
("reuse is authorised, provided the source is acknowledged"). Elk geval wordt
een claim (Engelse samenvatting) met één check (uitgever EUvsDisinfo, oordeel
"disinformation") en per genoemde outlet een attributie van niveau
`waargenomen`.
- AC1: import zonder geregistreerde bron is onmogelijk (S1).
- AC2: na import draait de benchmark op alle markten opnieuw (B14) en de
  uitgeverkwaliteitsmeting op de nieuwe uitgever.
- AC3: poortcijfer: het aandeel claims met minstens één attributie, gemeten en
  op de releasekaart.

**E7.S5 — Weergave.** Attributies in het antwoord en in de demo zijn een
protocolvraag (PROTOCOL §11.7) en volgen pas na dat besluit.

## E8: Eigen oordeel, leraar en leerling — Must *(B42, 2026-10-23)*

Een eigen, lokaal model (de leerling) zegt bij een beeld of tekst
"waarschijnlijk onwaar" of "geen oordeel", ook als er geen check bestaat. Een
groot taalmodel (de leraar) doet eerst het zware werk, offline op openbare
data (B26). Het oordeel gaat alleen naar buiten per klasse die de poort van
B30 haalt.

**E8.S1 — De basisset.** Eén set in plaats van losse meetsets: per stuk de
soort (beeld, artikel, tekst, webtekst, vastgesteld feit), de bron, het label
(onwaar, waar, neutraal), de helft (ontwikkel of toets, vaste hash) en de
datum; een verse deel na de trainingsgrens van de modellen.
- AC1: geen stuk zit in beide helften; stukken van dezelfde zaak zitten in
  dezelfde helft.
- AC2: de set telt zichzelf per soort, bron, label, helft en taal.
- AC3: alleen openbare data die al in huis is; geen artefact van een gebruiker
  (DR3).

**E8.S2 — De leraarladder.** Haiku, Sonnet en Opus krijgen dezelfde vaste vraag
(`oordeel-v1`) op de basisset of een gelaagde steekproef ervan.
- AC1: eerst een proef van 50 per model; een batch boven het budget wordt
  geweigerd.
- AC2: per model, soort, taal en helft: herkend onwaar, "onwaar" bij waar
  (betrouwbaar nieuws, ware checks, de kern) met bovengrens, en "onwaar" bij
  webtekst.
- AC3: de telling weigert zolang een "onwaar" bij waar of neutraal geen label
  heeft; van de toetshelft alleen totalen.
- AC4: de leraar is het goedkoopste model zonder valse vlag op de kern en met
  de laagste valse vlaggen op waar nieuws, bij een bruikbare herkenning
  (vooraf vastgelegd in PLAN).

**E8.S3 — Leerstof.** Het oordeel van redacties is het label waar het bestaat;
de leraar vult aan (de bewering uit beelden en artikelen, betrouwbaar nieuws,
lastige paren).
- AC1: elk voorbeeld draagt zijn herkomst (redactie of leraar, model,
  promptversie).
- AC2: niets uit de toetshelft of de verse set wordt leerstof.

**E8.S4 — De leerling.** Een open meertalig model op een vastgezette revisie,
getraind op de leerstof (DR6, B26).
- AC1: gemeten op dezelfde basisset als de leraar, toetshelft en verse set
  apart.

**E8.S5 — Harden.** Valse vlaggen worden nieuwe leerstof, met lastige ware
voorbeelden over hetzelfde onderwerp.
- AC1: een ronde die de valse vlaggen niet verlaagt, is de laatste.

**E8.S6 — Echt nieuws op de schaal van de poort.**
- AC1: per klasse minstens zoveel ware stukken als de poort van B30 vraagt
  (zonder één fout bijna 30.000), uit een corpus dat de PO goedkeurt.

**E8.S7 — Weergave.**
- AC1: een eigen oordeel ziet er nooit uit als een check van een redactie
  (DR5), noemt de laag en het gemeten foutcijfer van de klasse, en draagt geen
  percentage per bericht (B30).
- AC2: het antwoord zegt wat Factiz in het beeld of de tekst las.
- AC3: zonder gehaalde poort geeft de dienst geen eigen oordeel (DR2); een
  test bewaakt dat.

## E9: Het platform — Must *(B71–B74, 2026-11-10)*

Factiz.org als platform van factchecks, dossiers, thema's en rapporten. Het lab
maakt per release een publicatiedatabase; de site leest alleen dat bestand.
Bouwplan: `docs/voorstellen/2026-11-10-platform-bouwplan.md`. Volgorde en
bewijs per taak: PLAN, etappe 33.

**E9.S1 — De publicatiedatabase.** Als uitgever wil ik per release één bestand
met alleen wat gepubliceerd mag worden, zodat de openbare server niets anders
kán tonen.
- AC1: een check komt er alleen in als de herkomst herverdeelbaar is (Data
  Commons CC BY, of een bron met `herverdeelbaar = 1`); een zelf opgehaalde
  check of een koppeling uit Community Notes in de uitvoer laat de bouw falen
  *(B13, B73)*.
- AC2: alleen checks van toegelaten uitgevers, en geen vage bewering *(B28)*.
- AC3: één pagina per bewering; dezelfde bewering bij meer redacties (een
  cluster) is één pagina met al haar checks *(DR7)*. De naam van de redactie
  komt uit het register, nooit ruw uit de feed.
- AC4: elke check draagt de naamsvermelding en de licentie van haar bron, of de
  link nog leeft, en de archiefkopie als die er is *(DR1, #25.9)*.
- AC5: het bestand bevat nooit iets wat een gebruiker instuurde, sleutels,
  meetgegevens, de tekst van artikelen, beelden of vingerafdrukken *(DR3, B35)*.
- AC6: een pagina heeft een vast openbaar nummer dat een nieuwe import
  overleeft.
- AC7: een manifest met de datum, de aantallen per bron en taal, de versies en
  een controlegetal; twee keer bouwen op dezelfde database geeft hetzelfde
  bestand. De site weigert een bestand met een ander schema dan ze kent
  *(naar DR6)*.
- AC8 *(PO 2026-11-22: "Te particuliere dingen moeter wat mij betreft uit", daarna "Ja, bouw het"; PLAN #34.2ch)*: een
  check over het privéleven van één gewoon persoon of gezin (een ziek kind, een inzameling, een vermiste, een persoonlijk
  drama), zonder publiek persoon, groep, politiek, oplichting, algemene gezondheidsclaim of ramp, komt niet in het
  bestand, ook haar andere formuleringen niet. Alleen als twee lezingen het zo noemen (Haiku, daarna Sonnet met zes
  voorwaarden) en na een leesproef van 200 met hoogstens 2 die toch publiek zijn; wat de lezer als publiek of twijfel
  las, blijft, en een check in een dossier ook.

**E9.S2 — De factcheckpagina.** Als lezer wil ik bij één bewering zien wie haar
checkte en wat eruit kwam.
- AC1: de bewering staat er in haar eigen taal, met die taal en schrijfrichting
  in de pagina.
- AC2: het label met de telling uit de vaste woordenlijst *(DESIGN §4c)*, en per
  check het oordeel in de eigen woorden van de redactie.
- AC3: de bronnen zijn het grootste blok *(D2)*, de nieuwste eerst, elk met
  redactie, datum, taal en link; bij een dode link de archiefkopie.
- AC4: op de pagina van een check van een redactie staat nooit een eigen
  oordeel van Factiz *(DR5)* en nergens een waarheidspercentage *(DR2, B10)*.
- AC5: de naamsvermelding en de licentie van elke bron zijn zichtbaar.
- AC6: de velden die er zijn: thema, dossier, waar het opdook (met bron en
  niveau), namen, en verwante factchecks.
- AC7: een weg om een fout te melden, en de datum van de release.

**E9.S3 — Talen.**
- AC1: vijf talen (nl, en, de, es, fr); Engels op de hoofdmap, de andere onder
  hun code, met dezelfde padwoorden *(B74)*.
- AC2: elke vaste tekst bestaat in alle vijf talen; een test weigert bij een
  ontbrekende tekst. Een tekst die nog geen moedertaallezer zag, draagt dat als
  kenmerk in het bestand.
- AC3: de taal en de richting van de pagina volgen de taal van de site; die van
  een bewering volgen de bewering. Een bewering in het Arabisch, Perzisch,
  Hebreeuws of Urdu staat van rechts naar links, ook op een Nederlandse pagina.
- AC4: de taalkeuze verschijnt alleen waar de pagina in die taal bestaat, met de
  taal in haar eigen naam, zonder vlaggen; niet doorsturen op de taal van de
  browser, geen cookie; de pagina's verwijzen naar elkaar per taal.
- AC5: oordelen, thema's, trucs, vormen en soorten items komen uit vaste, met de
  hand vertaalde lijsten; een model vertaalt nooit een oordeel *(B32)*.
- AC6: de vertaling van een bewering staat nooit zonder het origineel, altijd
  met "machinevertaling uit …", en alleen in een doeltaal waarvan honderd
  vertalingen zijn nagelezen *(B32)*. De leesproef meet de methode: een latere
  vertaling met dezelfde vraag en hetzelfde model mag zonder eigen leesproef
  op de site, met dezelfde brontalen uit. Na elke 5.000 nieuwe per doeltaal
  wordt een verse steekproef van 50 gelezen, en tot dan wacht wat erna komt.
  Een andere methode begint opnieuw bij honderd *(PO 2026-11-12: "Ja, zelfde
  methode"; PLAN #34.2x)*. Een brontaal die na een leesproef uit bleef, gaat weer aan
  na een nieuwe proef van 100 paren uit alleen die brontaal, nooit eerder
  gelezen, zonder één fout of twijfel *(PO 2026-11-13; PLAN #34.2aa)*.
- AC7 *(B93, tot de ronde van 3 december, PLAN #37.15)*: een vertaling met de methode van haar doeltaal die alleen
  wegbleef omdat de leesproef van haar doeltaal of brontaal 3 tot 9 fouten vond, staat voorlopig op de site, alleen waar
  geen geldige vertaling is en alleen bij een bewering die de scan van B92 doorlaat. Bovenaan de factcheck in die taal
  staat dan *Machinevertaling, wacht op een nieuwe vertaling*; de vertaling telt niet als eigen tekst van de pagina
  (geen hreflang, niet in de sitemap, `noindex` in die taal); zoeken op de site vindt haar wel, zoals elke vertaling
  (PLAN #37.16, schema 21). Nooit een vertaling die in een leesproef fout gelezen
  werd, een vertaling met een woord in een ander schrift, of een die gelijk is aan het origineel. In de uitgave
  (schema 20) draagt zo'n rij `voorlopig = 1` in de tabel `vertaling`.

**E9.S4 — Beveiliging en privacy.**
- AC1: de site heeft geen inlog, geen beheerpagina en geen route die schrijft;
  de database gaat alleen-lezen open.
- AC2: script, opmaak, lettertypen en beelden komen alleen van de eigen site,
  nooit van een andere partij, ook niet van een CDN. Een stukje script of
  opmaak in de pagina zelf mag alleen als het bij het bouwen ontstaat en met
  zijn hash in de beveiligingsregel staat; opmaak in een attribuut (zoals
  Radix doet) mag ook, script nooit. Geen element draagt script. Elk
  antwoord draagt een beveiligingsregel (CSP) die verder niets toestaat
  (`default-src 'none'`, `frame-ancestors 'none'`). De andere vaste
  beveiligingskoppen (`nosniff`, HSTS, `Permissions-Policy`) zet de proxy bij
  de livegang *(PLAN #33.9)*. Een factcheck, de lijst en zoeken blijven
  leesbaar als het script niet laadt. Een test loopt elke soort pagina na, in de
  vijf talen *(`tests/test_site_html.py`)*. *(B75; bijgewerkt op 2026-11-13, PO:
  "Werk de regel in SPECS E9.S4 AC2 bij")*
- AC3: tekst uit de database staat altijd als platte tekst in de pagina; een
  test met vijandige voorbeelden (script, omgekeerde schrijfrichting,
  onzichtbare tekens, extreme lengte) bewaakt dat.
- AC4: geen cookies, geen analytics van een andere partij, geen verzoek naar een derde. Tellen mag alleen anoniem en
  opgeteld, op de eigen server (B78, E9.S26).
- AC5: het domein van een verspreider is nooit een link; een link naar een
  redactie geeft niets door over de bezoeker.
- AC6: onbekende of ongeldige adressen geven een nette foutpagina zonder
  technische details.
- AC7: de site leent geen code uit het lab; een test bewaakt dat (zoals
  `tests/test_kern.py` voor de dienst).

**E9.S5 — Lijsten, filters en thema's.**
- AC1: lijsten filteren op thema, taal, jaar, oordeel en redactie, met gewone
  links; bladeren is stabiel. *Sinds E9.S10 (2026-11-11) kiest de bezoeker in
  een formulier met keuzelijsten; de adressen zijn dezelfde gebleven, en elk
  adres is nog steeds een gewone link.*
- AC2: thema's komen uit een vaste lijst van hoogstens twee niveaus; een
  factcheck mag er twee hebben *(B72)*.
- AC3: een thema dat een model toekende, wordt pas getoond als de PO een
  willekeurige steekproef nalas en (a) van 200 gelezen toekenningen er
  minstens 180 kloppen, of (b) uit wat gelezen is met 95% zekerheid volgt dat
  minstens 90% klopt: 29 zonder fout, 46 met één fout, 61 met twee, 76 met
  drie, enzovoort. Een kaart waar de PO twijfelde en niet koos, telt als niet
  goed. *(b) erbij op 2026-11-11: de PO stopte na 162 kaarten zonder fout,
  "dit moet genoeg zijn"; de lat van 90% blijft.*

**E9.S6 — Zoeken.**
- AC1: zoeken op woorden op de site zelf, met het zoekregister uit de
  publicatiedatabase; geen dienst van een derde *(B73)*.
- AC2: het werkt in elk schrift, ook waar woorden niet door spaties gescheiden
  zijn.
- AC3: een zoekvraag wordt niet bewaard en niet gelogd *(DR3)*, en gaat bij het
  uitrollen niet langs een Amerikaanse tussenpartij *(B21)*.
- AC4: geen treffer is een eigen tekst, geen gok.
- AC5 *(PO 2026-11-15: "Geplakt bericht", na de roast; PLAN #34.2au)*: een geplakt bericht (een doorgestuurde tekst van
  zes woorden of meer, waarin niet alle woorden samen voorkomen) zoekt op zijn opvallendste woorden: de tien zeldzaamste
  in de uitgave, en nooit een woord dat in meer dan 2% van de pagina's staat. Alleen een factcheck met genoeg van die
  woorden, gewogen naar hoe zeldzaam ze zijn, is een treffer; hoogstens honderd. De pagina zegt dat het om gelijkenis in
  woorden gaat (*Deze factchecks lijken op je bericht*), met het aantal, en markeert alleen de woorden die telden. Lijkt
  geen factcheck duidelijk op het bericht, dan de tien met de meeste van dezelfde woorden onder de kop *Deze factchecks
  hebben woorden gemeen met je bericht*, en de pagina zegt dat het geen treffers zijn (AC4). Een bericht met minder dan
  twee opvallende woorden krijgt niets. Een bericht mag tot 1.000 tekens lang zijn; de vraag wordt ook dan nergens
  bewaard (AC3).

**E9.S7 — Dossiers.**
- AC1: twee soorten, een verhaal en een netwerk; een mens maakt een dossier aan,
  als bestand *(B72)*.
- AC2: een tijdlijn per jaar met soorten items: factcheck, in de pers, onderzoek
  van anderen, besluit, eigen rapport.
- AC3: een model stelt voor welke factchecks erbij horen; alleen wat een mens
  goedkeurde, staat in het dossier. Wie leest: de PO, of Claude met de PO. Dan leest
  Claude elke kaart, met een reden bij elke twijfel, en zet zijn twijfel in groepen
  met één vraag per groep (de afbakening); de PO beslist over die groepen, en waar
  Claude een check niet kon openen, per kaart. Wat zij niet koos, blijft eruit. De
  lezing houdt bij wat van Claude komt en wat van haar, en draagt haar akkoord met
  haar woorden en de datum. *PO 2026-11-12, bij de zes nieuwe dossiers: "Ja, jij
  leest eerst, ik daarna de twijfelgevallen".*
- AC4: in een netwerkdossier staat alleen wat een bron met naam aan dat netwerk
  toeschreef, met het niveau erbij *(B62)*.
- AC5: de kerngetallen ("waar staan we nu") worden uit de database gerekend,
  nooit getypt.
- AC6: een factcheck staat in hoogstens één verhaaldossier *(B72)*.
- AC7: een dossier staat pas in een uitgave na een akkoord van de PO; een
  concept is alleen op de eigen computer te zien *(B73)*.
- AC8: binnen een verhaaldossier kunnen factchecks één **versie** delen:
  hetzelfde bericht in andere woorden of een andere taal (het landhuis van de
  Britse koning, in het Nederlands, Duits, Engels, Japans en Russisch). Een
  model stelt de versies voor, een mens keurt elke versie goed. De pagina van
  een factcheck toont de andere factchecks van haar versie onder *Komt ook voor
  als*, met een telling die de site zelf rekent. *(PO 2026-11-11: "als mensen
  een claim aanklikken wil ik ook dat ze de andere variaties van dit bericht
  zien: 'komt ook voor als'".)*
- AC9: in de zijbalk van een dossier staan onder *Verkennen* de begrippen die in zijn factchecks
  veel vaker voorkomen dan in het hele archief, elk als zoekvraag naar het archief, in de taal van de
  site. De site rekent ze uit de uitgave, nooit een model en nooit getypt; geen woord uit de naam van
  het dossier. *(PO 2026-11-19: "Door begrippen te tonen die in dossier voorkomen in de sidebar kun je
  onderwerpen verder verkennen.")*
- AC10: een dossier heeft per jaar hoogstens 25 beweringen (een instelling, `MAX_PER_JAAR`): die het
  vaakst rondgingen, gemeten aan hoe vaak en door hoeveel redacties ze in het archief gecheckt zijn, één
  factcheck per bewering. De eigen checks van Factiz staan er altijd in. Wat de lezing verder
  goedkeurde, blijft in de lezing staan. *(PO 2026-11-19: "een strenge selectie denk ik ook, alleen de
  grootste misinformatie die het vaakst voorbij komt", en daarna: "50 in totaal in misschien wat
  arbitrair, hoeft niet zo streng, een max aantal per jaar is beter, zodat we geen dossiers met
  duizenden krijgen".)*

**E9.S10 — De schil: navigatie, filters en sorteren.** *(PO 2026-11-11)*
- AC1: het hoofdmenu, de taalkeuze en de voet staan op elke pagina, uit één bron; elke link erin bestaat, in elke
  taal van de site.
- AC2: een lijst is te filteren op thema, onderdeel, oordeel, taal, jaar, land en redactie en te sorteren op nieuwste,
  oudste en meeste redacties, met één formulier; de keuze staat in het adres, en elk filter is los weg te halen.
- AC3: zoeken kan met dezelfde filters en volgorde; de zoekvraag staat ook dan in het bericht en nooit in het adres
  *(E9.S6 AC3)*.
- AC4: een adres met een lege of een niet passende keuze uit het formulier leidt door naar het ene adres van die
  lijst; een onbekende waarde of sleutel blijft niet gevonden.
- AC5: op een telefoon staan menu en filters in een lade, begint de eerste factcheck op het eerste scherm, en schuift
  niets opzij; alles werkt zonder script *(D13; sinds B75 mag script erbij, de pagina blijft leesbaar zonder)*.
- AC6: elke pagina heeft een eigen titel en omschrijving en, waar ze in een pad hangt, een kruimelpad.

**E9.S11 — Namen.** *(B72; PLAN #33.7, PO 2026-11-11)* Als onderzoeker wil ik alle
factchecks zien waarin een publieke persoon, een organisatie of een plaats
genoemd wordt, in elke taal.
- AC1: een naam op de site is een publieke persoon, een organisatie of een
  plaats met een nummer van Wikidata; dezelfde naam is in elke taal dezelfde.
  De naam staat er in de taal van de site, en anders in het Engels.
- AC2: een naam staat alleen op de site als (1) er een artikel is in minstens
  3 talen van Wikipedia, (2) hij op minstens 5 pagina's voorkomt, (3) bij een
  persoon Wikidata het een mens noemt en de pagina's van minstens 2 redacties
  komen, en (4) de soort van het model en die van Wikidata elkaar niet
  tegenspreken: een persoon is een mens; een organisatie of plaats is geen
  mens, geen ding, wet, werk of gebeurtenis, en geen algemeen begrip. Wat een
  van de vier niet haalt, staat nergens: niet als pagina en niet als veld.
  Een bewering telt alleen bij een naam als die naam, of een schrijfwijze die
  Wikidata kent, letterlijk in de bewering of in een vertaling ervan staat.
- AC3: namen gaan pas in een uitgave als een willekeurige steekproef van paren
  (bewering, naam) is nagelezen volgens de regel van E9.S5 AC3 (180 van 200, of
  wat met 95% zekerheid 90% draagt), **en daarin geen enkele privépersoon
  voorkwam**. Eén privépersoon sluit de poort. Wie leest: de PO, of Claude met
  een akkoord van de PO dat met haar woorden en de datum is vastgelegd. Een
  lezing van Claude zonder dat akkoord opent de poort niet, en een akkoord
  zonder lezing ook niet. *Gewijzigd door de PO op 2026-11-12, toen de kaarten
  klaarstonden: "Hier help mijn menselijke blik niet, computer is beter hier in
  vinden van namen, akkoord zoals het is". Tot dan las alleen de PO. Dit geldt
  voor namen; bij thema's (E9.S5 AC3) leest de PO zelf, bij dossiers (E9.S7 AC3)
  beslist zij over de twijfel en de afbakening.*
- AC4: de pagina van een naam zegt *factchecks waarin deze naam voorkomt*. Zij
  zegt nooit dat de genoemde iets beweerde of deed, en draagt geen
  omschrijving, geen foto en geen oordeel. Het nummer van Wikidata staat erbij
  als link, zodat te zien is wie of wat bedoeld is.
- AC5: er is geen ranglijst van wie het vaakst genoemd wordt; het overzicht van
  namen staat op alfabet. *Aangescherpt op 2026-11-15 (PO bij het netwerk van namen: "Check even of dit logisch is,
  of dat we weer te streng zijn"): het aantal factchecks per naam staat al op de pagina van die naam; wat deze regel
  verbiedt, is een lijst op volgorde van dat aantal. Het netwerk van namen (E9.S18) mag een naam zo groot tekenen als
  zijn aantal, met de uitleg dat een naam niets zegt over wie iets beweerde, en zijn lijst van namen staat op alfabet.*
- AC6: een mens kan een naam weghalen: een naam in `content/namen-niet.json`
  staat in geen enkele uitgave, wat de regels ook zeggen.
- AC7: wie een bewering deelde of verspreidde, krijgt nooit een naam of een
  pagina *(B29)*; een medium waar een bewering opdook blijft platte tekst op de
  factcheck *(E9.S4 AC5)*.
- AC8: de andere schrijfwijzen die Wikidata van een naam kent (bijnamen,
  afkortingen, andere transcripties), in de vijf talen van de site, gaan mee in
  de uitgave en dienen alleen om te zoeken: wie *Zelenskiy* of *NAVO* typt,
  vindt wat bij Zelensky en de NAVO hoort. Een bijnaam staat nooit op een
  pagina *(PLAN #34.2z)*. Een afkorting die in hoofdletters getypt is (WHO,
  OMS, EU), is de naam, als ze in de uitgave vooral die naam is; in kleine
  letters of tussen aanhalingstekens blijft ze het woord *(PLAN #34.2ab)*.

**E9.S12 — Zoeken voorop.** *(PO 2026-11-12; PLAN #33.6c, DESIGN §4v)* Als bezoeker wil ik op de eerste
pagina meteen kunnen zoeken, en daarna met filters en een volgorde snel vinden wat ik zoek.
- AC1: de startpagina opent met één groot zoekveld; het label noemt het aantal factchecks, een plaatshouder
  zegt wat je kunt typen, en de knop heeft een woord. Daaronder staat het archief zelf: de filters, de volgorde
  en de nieuwste factchecks. Op elke pagina is er één zoekveld.
- AC2: oordeel, taal en jaar zijn vinkjes: meer waarden tegelijk; binnen een filter is het *of*, tussen filters
  *en*. Elke waarde draagt het aantal factchecks dat zij binnen wat nu getoond wordt zou opleveren; een filter
  telt zichzelf niet mee; een waarde die niets oplevert staat er niet, behalve als zij gekozen is. Lange
  lijsten tonen zes tot acht waarden en de rest onder *meer*.
- AC3: elke keuze staat in het adres (`?taal=en&taal=hi`), en dezelfde keuze heeft één adres; elk gekozen stuk
  is los weg te halen.
- AC4: de volgorde staat op een breed scherm boven de lijst, als één klik, met zichtbaar welke geldt; op een
  telefoon in dezelfde lade als de filters, achter één knop *filteren en sorteren*. Bij zoeken is de beste
  treffer de standaard.
- AC5: de zoekpagina houdt de vraag in het veld en zegt boven de treffers hoeveel er zijn voor die vraag. Bij elke
  treffer staan de woorden van de vraag gemarkeerd, en bij een lange bewering het stuk rond het gevonden woord.
- AC6: staat geen enkele factcheck met al de woorden, dan de factchecks met een deel ervan, en dat staat erbij;
  levert de vraag binnen de filters niets op, dan het aantal zonder filters met een knop; levert zij niets op,
  dan wegen verder (thema's, dossiers, namen, de hele lijst, een fout melden). Een treffer wordt nooit verzonnen
  *(E9.S6 AC4)*.
- AC7: is de vraag precies een thema, een dossier, een redactie of een naam, of een deel van de naam van een
  persoon, dan staat die pagina bovenaan als ingang; hoogstens drie.
- AC8: zonder script *(D13; sinds B75 mogen suggesties en filters die meteen bijwerken er met script bij)*; de zoekvraag gaat in het bericht en wordt niet bewaard *(E9.S6 AC3)*; de tellingen
  zijn binnen 20 ms klaar op de hele uitgave.

**E9.S13 — De look van de site, met de velden.** *(PO 2026-11-12; PLAN #33.6d, DESIGN §4w; een tussenstap tot
etappe 34)* Als bezoeker wil ik dat het platform eruitziet als factiz.org, en dat ik een thema of dossier herken aan
zijn beeld.
- AC1: het platform draagt de opmaak van factiz.org (DESIGN §4h): papier, dunne koppen, kleine mono-labels in groen,
  knoppen als pil, haarlijnen. Bovenaan elke pagina staat een veld met de kop erop in wit: op de start corpus met het
  grote zoekveld, elders een band met het label en de kop van de pagina. De voet staat op het veld nacht, met de links
  op een halfdoorzichtige kaart.
- AC2: elk thema en elk dossier heeft een eigen veld uit `doublecheck.velden`, als band en als kaart, met een vaste
  seed en een herkomstregel. De themapagina en de dossierpagina dragen hun band; een factcheck draagt de band van haar
  thema, zonder thema het veld groen. Dossiers en thema's staan in een overzicht als kaart op hun veld. De naam staat
  er altijd in tekst bij: het beeld is nooit de enige drager.
- AC3: een veld draagt nooit een oordeel. Het staat nooit achter of in de bewering, het label, de telling, de bronnen of
  de meter; die staan samen op papier *(D11, §4d)*. Een rij in een lijst draagt geen beeld *(§4q)*.
- AC4: wit op een veld haalt in elke tekstzone 4,5:1 (koppen 3:1) na de sluier van de pagina, ook in de uiterste
  standen van de beweging; geen veld draagt rood; elk beeld weegt hooguit 200 KB.
- AC5: zonder script (gebouwd vóór B75; script mag sinds B75, van de eigen site), in licht en donker; op een telefoon
  begint de eerste factcheck nog op het eerste scherm en
  schuift niets opzij *(E9.S10 AC5)*; bij `prefers-reduced-motion` staan de velden stil.
- AC6: het platform leent geen code uit het lab: het draagt zijn eigen kopie van de beelden, en een test eist dat de
  gedeelde gelijk zijn aan die van factiz.org.

**E9.S14 — Zoeken dat meedenkt.** *(PO 2026-11-13: "Autocomplete met suggesties bouwen, kenmerken uit de zoekopdracht
als filter, typfouten en categorie-redirect, kijk even naar alle best practices"; PLAN #34.2ac; Baymard #340, #342,
#333, #348, #362, #370, #404, #1024)* Als bezoeker wil ik dat het zoeken mijn woorden afmaakt, begrijpt wat ik bedoel
en me terugbrengt waar ik was.
- AC1: elk zoekveld van de site (het grote veld op de start, het veld boven de lijst en het zoekvenster) toont tijdens
  het typen dezelfde suggesties: hoogstens tien, in groepen (zoekvragen, pagina's, factchecks). De pijltjes lopen rond
  en nemen een zoekvraag over in het veld, Esc sluit de lijst. In een zoekvraag staat wat je typte gewoon en wat erbij
  komt vet. Zonder script is elk veld een gewoon formulier.
- AC2: het woord dat je typt, wordt in het veld zelf grijs afgemaakt met het woord dat het vaakst in de uitgave staat
  en ermee begint, en alleen als de vraag dan treffers heeft. Tab, of het pijltje naar rechts aan het eind, neemt het
  over. Zonder grijze aanvulling doet Tab wat het altijd doet.
- AC3: de naam van een land, een redactie, een thema of een onderdeel in de vraag (in een van de vijf talen van de site)
  verruimt dat stuk: het vindt het woord, of de factchecks over dat land, van die redactie of in dat thema. Het
  versmalt nooit: wat het woord vond, blijft, en wie wil versmallen, kiest het filter. Boven de treffers staat wat we
  zo lazen, met één klik om alleen op de woorden te zoeken. Tussen aanhalingstekens geldt dit niet. Een jaartal en een
  oordeel blijven woorden.
- AC4: is de hele vraag precies de volledige naam van één persoon uit het namenregister of van één dossier, in een
  van de vijf talen, dan gaat het zoeken meteen naar die pagina. Daar staat dat je via zoeken kwam, met een knop om
  toch op de woorden te zoeken. Hebben meer pagina's die naam, is het een deel van een naam, staat de vraag tussen
  aanhalingstekens, of is het een plaats, organisatie, thema of onderdeel, dan blijft het een zoekvraag met de pagina
  bovenaan als ingang *(E9.S12 AC7)*: daar zou doorsturen laten vallen wat het woord vond.
- AC5: plakt iemand het adres van een factcheckartikel uit de uitgave, of van een factcheck op Factiz, dan gaat het
  zoeken naar die factcheck. Een adres dat er niet in staat, zoekt als een gewone vraag.
- AC6: een vraag naar de site zelf (over, privacy, bronnen, licenties, redacties, api, contact) wijst naar die pagina
  als ingang.
- AC7: vindt de vraag niets, dan zegt de pagina dat niets vinden niets zegt over of een bericht klopt, met de wegen
  van E9.S12 AC6.
- AC8: na een zoekvraag houdt de geschiedenis van het tabblad de vraag vast, nooit het adres. Terug van een factcheck
  geeft dezelfde vraag, dezelfde filters, dezelfde rijen en dezelfde plek. Een pagina die uit een formulier kwam,
  vraagt bij terug of herladen nooit om het formulier opnieuw te sturen.
- AC9: gemeten op de uitgave vóór en na: de randproef en de zoekproef blijven gelijk of worden beter, met nieuwe
  gevallen voor AC2 tot AC6; de suggesties zijn klaar binnen 100 ms; de zoekvraag wordt nergens bewaard *(E9.S6
  AC3)*.

**E9.S15 — Hoofdletters in normaal schrift.** *(PO 2026-11-13: "Zullen we dingen in capslock geschreven automatisch
normaal schrift maken?", daarna "Ja, bouw het"; PLAN #34.2ae)* Als lezer wil ik een bewering die in hoofdletters
rondging gewoon kunnen lezen, en toch zien hoe ze rondging.
- AC1: een tekst heet in hoofdletters als minstens 80% van zijn letters met een hoofd- en kleine vorm hoofdletters zijn,
  bij minstens 12 zulke letters. Op de uitgave van 13 november: 779 beweringen en 2.732 vertalingen.
- AC2: zo'n tekst krijgt één keer normaal schrift van een taalmodel (`hoofdletters-v1`), met een harde controle: het
  resultaat mag alleen in hoofd- en kleine letters verschillen van wat er stond (dezelfde tekens, dezelfde woorden,
  dezelfde leestekens; witruimte telt niet). Wat de controle niet haalt, blijft in hoofdletters.
- AC3: een vertaling is tekst van Factiz: in de uitgave staat ze in normaal schrift. De bewering zelf is het citaat:
  ze blijft in de uitgave zoals ze rondging, en het normale schrift staat ernaast.
- AC4: op de site staat in de kop, in de lijsten, bij zoeken en in de titel het normale schrift. Een vertaling houdt
  het origineel eronder zoals het rondging; een bewering in de taal van de site krijgt eronder een regel dat ze zo, in
  hoofdletters, rondging, met de tekst. De gegevens voor zoekmachines (`Claim`) houden de bewering zoals ze is.
- AC5: het normale schrift gaat pas in de uitgave na een leesproef van 100: geen fout die verandert wat je leest (een
  afkorting of naam die een gewoon woord wordt, zoals *Who* voor *WHO*), geen twijfel, en hoogstens 5 kleine (een
  hoofdletter te veel of te weinig die niets verandert). Is de poort dicht, dan alleen met `bouwen --concepten`.
- AC6: zoeken verandert niet (het register kent geen hoofdletters); het lab houdt zijn teksten.

**E9.S16 — Kleur en icoon per onderwerp.** *(PO 2026-11-15: "Ja, begin daarmee", op het voorstel
`docs/voorstellen/2026-11-15-kaart-van-de-factchecks.html`; PLAN #34.2ag)* Als bezoeker wil ik een onderwerp overal
herkennen aan dezelfde kleur en hetzelfde icoon, zonder het ooit voor een oordeel te houden.
- AC1: vier dragers, elk met één betekenis: een vierkante tegel met kleur en icoon is het onderwerp (thema); een rondje
  met een woord is het oordeel (zoals nu); een lijnicoon zonder kleur is later de soort nepnieuws; een land krijgt nooit
  een kleur.
- AC2: vijf families, met de namen van de velden: *Macht* (leisteen: Politiek en bestuur, Verkiezingen, Internationale
  politiek), *Conflict en veiligheid* (nacht: Oorlog en conflict, Misdaad en recht, Rampen en ongelukken), *Gezondheid en
  wetenschap* (groen), *Geld en aarde* (olijf: Economie en geld; Klimaat, energie en natuur), *Mensen* (hemel: Religie en
  samenleving, Migratie, Bekende mensen, sport en media). Het veld van een thema hoort bij zijn familie.
- AC3: de kleuren gemeten, licht en donker apart: tussen de families minstens ΔE 20 bij gewoon zicht en bij deuteranopie,
  protanopie en tritanopie (simulatie van Machado e.a., 2009); het icoon op een tegel minstens 3:1; in het donker de
  tegel op het paneel minstens 3:1; elke familie minstens ΔE 18 van elke oordeelkleur van dezelfde stand.
- AC4: per thema een icoon uit Lucide (ISC), in eigen code met de licentie erbij, zonder nieuw pakket; altijd met de
  naam ernaast, de tegel zelf is voor schermlezers verborgen.
- AC5: overal waar nu het staal van een thema staat (de kaart van een factcheck, de filters, het menu, het zoekvenster,
  de factcheckpagina, het dossier) staat de tegel; op de start en in het overzicht van de thema's staat hij bij de naam.

**E9.S17 — Verkennen.** *(PO 2026-11-15: "Ja, bouw Verkennen", stap 2 van het voorstel
`docs/voorstellen/2026-11-15-kaart-van-de-factchecks.html`; PLAN #34.2ah)* Als bezoeker wil ik in één beeld zien waar de
factchecks over gaan, wanneer ze gecheckt zijn en over welke landen, en van daaruit bij de factchecks zelf komen.
- AC1: één pagina, `/explore/`, in de vijf talen, met drie delen die aan één keuze hangen: de ring van onderwerpen (de
  thema's, elk zo groot als zijn aantal, in de kleur van zijn familie, met een legenda per familie: tegel, naam, aantal),
  *wanneer* (per jaar de laatste elf jaar tot het jaar van de nieuwste check, en wat ervoor ligt als één getal) en *waar*
  (de tien landen met de meeste factchecks). Zonder keuze tonen ze alles. Een keuze is een link (`?thema=`): de pagina werkt
  zonder script.
- AC2: elk deel eindigt bij de factchecks (overzicht eerst, dan inzoomen, dan één pagina): een jaar opent de lijst met dat
  thema en dat jaar, een land de lijst met dat thema en dat land, een onderdeel zijn eigen pagina, en er is een link naar
  alle factchecks van het gekozen thema.
- AC3: onder de jaren staat wat erbuiten valt (van vóór het eerste jaar, zonder datum), en bij de verhouding hoe die
  gerekend is. Geen uitleg over hoe er geteld is (welk jaar, welk land, een tweede thema), en bij het aantal geen zin dat
  tellen niet meten is hoeveel nepnieuws er is: PO 2026-11-22, "Dat soort uitlegzinnetjes ... zorgt alleen voor een
  drukkere interface. ... De teksten die op onze interface staan, moeten nuttig zijn voor de gebruiker.", en daarna "Ja,
  alle drie weg".
- AC4: bij een gekozen thema heeft *waar* twee maten: het aantal, en de verhouding (hoe vaak het thema voorkomt bij de
  factchecks over een land, gedeeld door hoe vaak het voorkomt bij alle factchecks met een land). De verhouding alleen
  voor landen met minstens 300 factchecks, waarvan minstens 20 over het thema. Geen percentages.
- AC5: één adres per weergave. Een onbekende sleutel, een onbekend thema, een `maat` anders dan `verhouding` of een `maat`
  zonder thema bestaat niet (404). Met een keuze is de pagina niet vindbaar; zonder keuze in alle vijf talen.
- AC6: toegankelijk zonder de ring: de ring is een plaatje dat een schermlezer overslaat, de legenda, de jaren en de
  landen zijn gewone links met hun aantal in woorden; op een telefoon schuift niets opzij; licht en donker.
- AC7: Verkennen staat in het menu (de kop en de lade) en in de voet.

**E9.S18 — Het netwerk van namen.** *(PO 2026-11-15: "Ja, bouw het netwerk", stap 3 van het voorstel
`docs/voorstellen/2026-11-15-kaart-van-de-factchecks.html`; PLAN #34.2ai)* Als onderzoeker wil ik zien welke namen samen
voorkomen in nagetrokken beweringen, en in welk thema, en van daaruit bij een naam en zijn factchecks komen.
- AC1: één pagina, `/explore/network/`, in de vijf talen, alleen als de uitgave namen heeft: de 70 namen die in de meeste
  factchecks staan, en een lijn tussen twee namen die samen in minstens 25 factchecks staan, dikker naarmate het er meer
  zijn. Een cirkel is zo groot als het aantal factchecks met die naam, in de kleur van de familie van het thema waarin de
  naam het vaakst voorkomt (E9.S16).
- AC2: boven het netwerk staat wat het telt en wat het niet zegt: een naam in een bewering zegt niets over wie die
  bewering deed of verspreidde, en samen genoemd worden zegt niet dat er een band is (E9.S11 AC4, AC5).
- AC3: een naam kiezen (`?naam=Q…`) licht hem en zijn buren op en zet ernaast: de soort, het aantal, het thema, de buren
  met hoe vaak ze samen voorkomen, en links naar de pagina van de naam en naar de lijst met die naam. De pagina werkt
  zonder script; met script lichten de buren op bij aanwijzen en vindt een zoekveld een naam in het netwerk, zonder dat
  er iets naar de server gaat.
- AC4: de schikking van de cirkels is in elke taal gelijk en bij elke opvraag hetzelfde, en geen naam of label ligt over
  een ander.
- AC5: toegankelijk zonder het netwerk: het plaatje is voor een schermlezer verborgen en heeft geen tabstop; de namen
  staan ernaast als gewone links op alfabet, nooit op volgorde van hun aantal. Op een telefoon schuift alleen het
  netwerk zelf opzij, de pagina niet.
- AC6: één adres per weergave: een andere sleutel, een naam die niet in het netwerk staat of een uitgave zonder namen
  geeft 404. Met een gekozen naam is de pagina niet vindbaar.
- AC7: Verkennen en het register van namen wijzen naar het netwerk.

**E9.S19 — Soort en vorm, alleen waar het zeker is.** *(PO 2026-11-15: "Ja, begin met route 1, route 2 op roadmap als
discussie topic voor een spar sessie tussen ons"; PLAN #34.2ak, na de voormeting #34.2aj, BENCHMARK §260)* Als
bezoeker wil ik zien hoe een bericht misleidde en of het een video of een beeld was, en daarop filteren, zonder dat
Factiz het raadt.
- AC1: twee kenmerken per factcheck, elk alleen waar het zeker is. De *soort volgens de redactie*: alleen als de
  woorden van een redactie haar noemen, in vijf soorten: *bewerkt of nagemaakt*, *zonder of uit zijn context*,
  *verzonnen*, *satire*, *gemaakt met AI*. De *vorm*: *video* of *beeld*, alleen als de bewering het zegt.
- AC2: de soort komt uit een nagelezen lijst van de woorden van redacties, na dezelfde normalisatie als de vertaalde
  woorden (`woordsleutel`), nooit uit een taalmodel. Een woord dat niet op de lijst staat, telt niet; een woord dat
  geen soort noemt, staat er met *geen*. De lijst staat in `docs/steekproeven/34.2ak-soortwoorden.json`. Heeft een
  factcheck meer soorten, dan telt de meest bijzondere: AI, bewerkt, satire, verzonnen, context.
- AC3: de vorm komt uit de woorden van de bewering, of haar Engelse versie: *video* bij video, clip of footage (184 van
  188 gelijk aan het artikel), *beeld* bij photo, picture, image of screenshot (139 van 154). Noemt een bewering beide,
  dan *video*.
- AC4: op de site een lijnicoon zonder kleur met het woord (E9.S16 AC1), op de kaart van een factcheck en op de
  factcheckpagina; bij de soort staat *volgens de redactie*. Beide zijn filters op de lijst, met hun aantal.
- AC5: de filters zeggen wat ze tellen: alleen de factchecks waar de redactie de soort noemde, of waar de bewering een
  video of beeld noemt. Wie geen vinkje ziet, mag niet denken dat de rest geen video was.

**E9.S20 — De wereldkaart.** *(PO 2026-11-15: "Ga verder met stap 5, de wereldkaart"; de download van Natural Earth met
een ja van de PO; PLAN #34.2am)* Als bezoeker wil ik op een kaart zien over welke landen de factchecks gaan, met
dezelfde twee maten als *waar ter wereld* (E9.S17), en vanaf een land bij zijn factchecks komen.
- AC1: op Verkennen, in *waar ter wereld*, een kaart van de wereld met per land een vlak dat donkerder is naarmate de maat
  hoger is: bij *aantal* het aantal factchecks over het land, bij *verhouding* de verhouding van E9.S17 AC4 (alleen landen
  boven de drempels; de rest zonder vlak). De kleur is die van de familie van het gekozen thema, zonder keuze grijs: een
  land krijgt geen eigen kleur (E9.S16 AC1), alleen een donkerte.
- AC2: een legenda met vijf trappen en hun grenzen in getallen; geen percentages.
- AC3: een land op de kaart opent de lijst met dat land (en het gekozen thema). De kaart is een plaatje dat een schermlezer
  overslaat; alle landen staan ook als gewone links in een lijst onder de kaart (*alle landen*), met hun waarde.
- AC4: de grenzen komen uit Natural Earth (publiek domein, 1:110 miljoen), in de projectie Equal Earth (gelijke
  oppervlakte, zodat een groot land niet zwaarder weegt dan het is), vereenvoudigd en zonder Antarctica; de herkomst staat
  bij het bestand. Een land dat op die schaal geen vorm heeft, en Antarctica, staat onder de kaart als *niet op de kaart*,
  met zijn waarde en link. Een land zonder factchecks heeft een licht vlak met een rand, en een eigen vakje in de legenda.
- AC5: op een telefoon past de kaart in de breedte; niets schuift opzij.

**E9.S21 — Contextkaarten naast een factcheck.** *(PO 2026-11-15: "Ja, bouw ze", op het voorstel
`docs/voorstellen/2026-11-15-zijbalk-contextkaarten.html`; PLAN #34.2an)* Als bezoeker wil ik naast een factcheck in één
blik zien in welk verband ze staat, en van daaruit verder kunnen kijken.
- AC1: hoogstens vier kaarten, in deze volgorde, alleen als er gegevens voor zijn: *dossier* (het verhaal, met de
  factchecks per jaar en deze gemarkeerd), *waar* (een stukje wereldkaart met het land, het aantal en bij een thema de
  verhouding), *namen* (de namen uit het netwerk met hun sterkste buren), *wanneer* (het thema per jaar, dit jaar als
  punt), *soort en vorm* (hoe vaak die in het thema voorkomt) en *redactie* (hoeveel ze in het archief heeft). Het
  patroon komt erbij met 33.11.
- AC2: elke kaart stelt één vraag, zegt in één zin wat ze telt en heeft één link naar de plek waar je verder kijkt
  (het dossier, Verkennen, het netwerk of de lijst met die filters). Geen percentages; de verhouding met ×.
- AC3: bij de namen staat dat samen genoemd worden geen band betekent (E9.S11). Bij het land geen zin dat een telling geen
  maat voor nepnieuws is: de zin zegt al dat het factchecks telt (PO 2026-11-22: "Hier kan het ook weg.").
- AC4: de kleur is die van het thema (E9.S16); elk beeld is voor een schermlezer verborgen en de zin draagt alles.
- AC5: de kaarten komen uit dezelfde functies als Verkennen, het netwerk en de dossiers (één veld `context` in
  `/api/<taal>/factcheck`), zonder model en zonder script. Op een breed scherm staan ze in de zijbalk boven *op deze
  pagina*, dat blijft staan zodra de kaarten voorbij zijn; op een smal scherm onder het artikel.

**E9.S22 — Een tekening per thema en per dossier.** *(PO 2026-11-15: "ik wil een SVG stijl toevoegen per check, topic en
dossier en thema die iets toegepaster is en minder abstract", daarna "Kijk even in de ideelab website repo hoe we daar de
visual bouwen, daar hebben we al een SVG stijl, die moet alleen wat abstracter met wat grain erover" en "Op het veld";
PLAN #34.2ap)* Als bezoeker wil ik aan het beeld van een thema of dossier zien waar het over gaat, niet alleen dat het
van Factiz is.
- AC1: elk thema en elk dossier krijgt één tekening in de tekentaal van de routeplaatjes van Ideelab, abstracter: een
  halfdoorzichtig vel dat linksboven inspringt en rechts en onder uit het beeld loopt, met hoogstens drie soorten vormen
  zonder woorden (regel, blok, stip, lijn, ring, en sinds 2026-11-19 een gevuld vlak voor een kaart of een voorwerp, PO:
  "Landkaartje van gaza") in de kleur van de familie (E9.S16); alleen de vorm die de betekenis draagt staat op volle kleur,
  en de tekening vervaagt naar onder. Een onderdeel krijgt de tekening van zijn thema; een dossier
  zonder eigen tekening die van zijn thema.
- AC2: de tekening staat op het veld, dat blijft (DESIGN §4h). De korrel komt van het veld: geen tweede korrel over
  het vel en de vormen (PO 2026-11-15: "ik zie nog een dubbele korrel met die svgs erover heen, was eerst mooier").
- AC3: een tekening toont het onderwerp, nooit de bewering die gecheckt is (bij het dossier over Gates geen chip), en
  nooit een oordeel: geen vinkje, geen kruis, geen rood (DESIGN principe 1 en 3).
- AC4: nooit achter een bewering, een label of een bron (D11). Op de kop van een thema of dossier staat de tekening rechts,
  naast de naam, en op een telefoon niet.
- AC5: voor een schermlezer verborgen, zonder script en zonder bestand van buiten (B75); geen eigen korrel (AC2).
- AC6: het deelplaatje per factcheck is E9.S23.

**E9.S23 — Het deelplaatje per factcheck.** *(PO 2026-11-15: "Maak nu het deelplaatje per factcheck (nadenken over
economisch gebruik denk ik, zodat je niet duizenden versie hoeft te maken?)"; PLAN #34.2aq)* Als iemand die een factcheck
deelt in een app wil ik dat de ontvanger de bewering en het oordeel al ziet voordat hij klikt.
- AC1: 1200 bij 630. Bovenaan een band met het veld en de tekening van het thema (E9.S22); daaronder op een effen vlak de
  bewering, het oordeel als label in woorden met zijn stip (zoals op de pagina, E9.S16) en de zin wie het checkte en
  wanneer, en het woordmerk. Nooit een veld of tekening achter de bewering of het label (D11); geen eigen oordeel, geen
  percentage.
- AC2: de bewering is dezelfde tekst als de kop van de pagina in die taal (de vertaling, anders het origineel); kan het
  lettertype dat schrift niet tonen, dan de Engelse versie, en anders geen bewering maar alleen het oordeel en de zin.
  Te lang wordt afgekapt met een beletselteken, nooit midden in een woord.
- AC3: zuinig: niets wordt vooraf gemaakt. Het plaatje wordt getekend als iemand het opvraagt, en daarna bewaard: het adres
  draagt de versie van de uitgave, zodat een cache het tot de volgende uitgave mag houden; het platform houdt de laatste
  in zijn geheugen.
- AC4: het lettertype is Geist (OFL), het lettertype van de site, als bestand bij het platform; geen pakket erbij. De
  tekeningen komen uit één bron voor de site en het plaatje (`site/src/lib/platen.js`, uitgeschreven naar
  `factiz_site/static/platen.json`).
- AC5: elke factcheckpagina wijst in `og:image` naar haar eigen plaatje, met een beschrijving in woorden
  (`og:image:alt`).
- AC6 *(PO 2026-11-15: "Ja, maak ze")*: een thema, een onderdeel en een dossier krijgen ook een eigen plaatje: dezelfde
  band (bij een dossier zijn eigen veld en tekening), daaronder de soort (de kicker van de pagina, de naam van het thema
  bij een onderdeel, de soort van een dossier), de naam groot, en het aantal factchecks (bij een dossier met redacties,
  talen en jaren). Op dezelfde zuinige manier (AC3). De overzichten en de vaste pagina's houden het algemene beeld.



**E9.S24 — Een fout melden op elke factcheck.** *(PO 2026-11-15: "Ja, bouw hem", na de roast; PLAN #34.2at)* Als bezoeker
wil ik een fout in wat Factiz aan een factcheck toevoegde kunnen melden, zonder account en zonder formulier.
- AC1: onder elke factcheck de vraag *Klopt hier iets niet?* met een link die een mail opent aan het adres van Factiz;
  het adres staat er ook als tekst, want een mailto werkt niet bij iedereen.
- AC2: het onderwerp draagt het nummer en de taal van de pagina; de mail somt op wat de machine op deze pagina deed (de
  vertaling, het thema, het land, de namen, de soort of vorm, alleen wat er staat), met het adres van de pagina, zodat de
  melder alleen hoeft aan te wijzen wat niet klopt.
- AC3: een fout in het oordeel zelf hoort bij de redactie: de pagina zegt dat, en hun artikel staat bovenaan.
- AC4: de site bewaart niets (B75): geen formulier, geen teller; de mail gaat naar de inbox. Een terechte melding wordt
  een regel in de lijsten die er al zijn (`content/namen-niet.json`, `content/waarom-niet.json`) of een correctie bij de
  volgende uitgave.

**E9.S25 — Wat erin zit en wat nog niet.** *(PO 2026-11-15: "Redacties en tellen", punt 2 van de roast; PLAN #34.2az)*
Als bezoeker die iets niet vindt, wil ik weten welke redacties in Factiz zitten en waarom grote redacties ontbreken, zodat
ik niet denk dat niemand het checkte.
- AC1: op de pagina met redacties en bij een zoekvraag zonder resultaat staat in de taal van de site hoeveel factchecks
  er zijn, van hoeveel redacties, en welke drie de meeste leverden; uit de uitgave geteld, nooit met de hand.
- AC2: een tweede zin noemt de grote redacties (AFP, Reuters, Snopes, Correctiv, Full Fact) die in de uitgave minder dan 50
  factchecks hebben, en zegt waarom: Factiz toont alleen wat het mag overnemen, en hun werk komt erbij als zij dat
  goedvinden. Haalt een van hen de 50, dan valt die naam vanzelf weg; halen ze het allemaal, dan valt de zin weg.
- AC3: geen belofte over wanneer; geen em-streepje en geen uitroepteken (VOICE).

**E9.S26 — Anoniem tellen.** *(PO 2026-11-15: "Redacties en tellen", uit de roast; B78; PLAN #34.2ba)* Als team wil ik na
de lancering zien welke soort pagina's gelezen worden en hoe vaak zoeken niets vindt, zonder iets over één bezoeker te
weten.
- AC1: per dag (UTC), per soort pagina (start, lijst, factcheck, thema, dossier, naam, redacties, verkennen, over, enz.) en
  per taal: het aantal keer dat de site die pagina toonde. Een doorverwijzing telt niet. Een robot, herkend aan zijn
  user-agent in het geheugen, telt alleen in één getal per dag en taal.
- AC2: per dag en taal: zoekvragen (het eerste blad; een ander filter op dezelfde vraag telt opnieuw), hoeveel daarvan
  niets vonden, en hoeveel een geplakt bericht waren.
- AC3: bewaard worden alleen die getallen, en sinds B94 de zoekvraag zelf (AC8). Geen IP-adres, geen cookie, geen adres of
  nummer van een pagina, geen user-agent, en geen tijd fijner dan een dag (B78).
- AC4: de site telt alleen als de server een bestand voor de tellingen krijgt (`FACTIZ_TELLINGEN`); zonder telt ze niets.
  Een bezoeker wacht nooit op de teller, en een kapotte teller breekt geen pagina.
- AC5: het platform neemt alleen bekende soorten en talen aan, en de site stuurt de ingang van de teller niet door.
  Meerdere serverprocessen tellen in hetzelfde bestand op.
- AC6: `python -m factiz_site.tellen` toont de getallen per dag, met het aandeel zoekvragen zonder resultaat.
- AC7: *Over Factiz* zegt onder *Wat we van je zien* wat we tellen, in de vijf talen.
- AC8 (B94, PLAN #37.17): wat mensen zoeken, per dag en taal de zoekvraag met haar aantal, in een eigen tabel
  (`zoekvraag`) naast de tellers. Alleen een gewone eerste zoekvraag (geen filter, sortering of volgend blad), getypt door
  een mens (geen robot, geen geplakt bericht), van hoogstens acht woorden en 100 tekens, zonder e-mailadres, telefoonnummer of
  reeks van zes cijfers (dezelfde regel als B88), in kleine letters. De suggesties tijdens het typen tellen niet.
- AC9: wat in zeven dagen minder dan drie keer gezocht werd, gaat weg zodra die zeven dagen voorbij zijn; wat blijft, blijft
  opgeteld per dag. `python -m factiz_site.tellen --zoekvragen [--dagen 7]` (ook met `--d1`) toont per taal alleen wat in die
  dagen minstens drie keer kwam. Nooit letterlijk op de site (B88 punt 5).
- AC10: de zin onder het zoekveld en *Wat we van je zien* zeggen het, in elke taal van de site.
- Wat het niet ziet: een pagina die Cloudflare uit zijn cache geeft, komt niet bij de server; zolang de site niet uit de
  cache komt, telt alles.

**E9.S36 — Meten met Google Analytics, na een ja.** *(PO 2026-11-22, B88; PLAN #34.2cg)* Als team wil ik zien hoeveel
echte mensen komen, hoe ze binnenkomen, wat ze op de site doen en wat ze zoeken, alleen van wie daar ja op zegt.
- AC1: met een meet-ID (`FACTIZ_GA`) toont elke pagina onderaan een banner met *ja* en *nee*, even groot; zonder meet-ID
  geen banner en niets van Google. Zonder keuze, of bij *nee*, laadt de site niets van Google en plaatst ze geen cookie.
- AC2: na *ja* laadt de site het script van Google (`googletagmanager.com`), met Google signals en
  advertentiekoppelingen uit; de keuze blijft op het apparaat, onder één sleutel (`factiz-meten`), en een knop in de voet
  opent de keuze opnieuw. Wie dan *nee* kiest, krijgt de cookies van Analytics (`_ga…`) gewist en wordt niet meer gemeten.
- AC3: op de zoekpagina gaat de zoekvraag als gebeurtenis `search` naar Analytics, alleen na *ja*, alleen een getypte
  vraag (geen geplakt bericht) van hoogstens acht woorden zonder e-mailadres, telefoonnummer of reeks van zes of meer
  cijfers (`site/src/lib/meten.js`, `zoektermVoorMeten`).
- AC4: de beveiligingsregel staat alleen de hosts van Google Analytics toe die het nodig heeft, voor script, verbinding en
  beeld; verder blijft alles van de site zelf.
- AC5: *Over Factiz* zegt onder *Wat we van je zien* wat Analytics meet, waarom, wat nooit naar Google gaat, hoe lang het
  blijft en hoe je nee zegt; de voet zegt dat er alleen met je ja gemeten wordt; in vijftien talen.
- AC6 *(later)*: een pagina *wat mensen willen weten* met onderwerpen uit Analytics en Search Console, nooit een
  letterlijke zoekvraag.

**E9.S27 — Zoeken en filteren binnen een thema.** *(PO 2026-11-15: "Moeten we op de overzicht pagina ook niet werken met
sidebar, immers je wilt hier ook kunnen zoeken filteren meerdere dossiers?"; keuze: "Links, als de lijst"; PLAN #34.2bb)*
Als bezoeker op een thema wil ik daar meteen kunnen zoeken en filteren, zonder eerst naar de lijst te gaan.
- AC1: de pagina van een thema of onderdeel toont onder de onderdelen en de dossiers dezelfde lijst als *Factchecks*,
  met het thema (en op een onderdeel ook het onderdeel) vast: de filters links, op een telefoon de knop en de lade,
  sorteren, meer laden, en een zoekveld dat binnen het thema zoekt.
- AC2: het vaste thema staat niet bij de filters en niet als wegklikbaar stukje; op de pagina van een thema is het
  onderdeel wel een filter. *Wis filters* laat het thema staan.
- AC3: de gekozen filters staan in het adres van de themapagina (terug en delen werken); de zoekvraag nooit (E9.S6 AC3).
- AC4: een themapagina zonder filters is vindbaar, met filters niet (DESIGNSYSTEEM §6, zoals de lijst).
- AC5: zonder script zoekt het formulier in de lijst met het thema als filter; *meer laden* is dan een gewone link naar
  het volgende blad van die lijst.
- AC6: de knop *Alle factchecks in dit thema, met filters* en het blok *Nieuwste factchecks* vervallen: de lijst staat
  er nu zelf, standaard het nieuwste eerst.

**E9.S28 — Elk schrift, in de menu's en op het deelplaatje.** *(PO 2026-11-15: "laten dit direct regelen zodat we ze
allemaal achter elkaar kunnen doen", over Chinees, Japans en Hindi die op een lettertype wachten; PLAN #34.2as)* Als bezoeker
in een taal met een ander schrift dan het Latijn wil ik de site en haar plaatjes in mijn schrift zien, niet in blokjes.
- AC1: alles wat Factiz schrijft staat in Geist, en daarachter Noto Sans voor de schriften van de sitetalen: Arabisch
  (ook Perzisch), Devanagari, vereenvoudigd en traditioneel Chinees en Japans, en Noto Sans zelf voor Grieks, Cyrillisch en
  wat Geist verder mist. Elk ander schrift, zoals een bewering in het origineel in het Telugu of Thai, staat in de letters
  van het toestel (PO 2026-11-16, PLAN #34.2bs: "Ja, bouw C"). Van de eigen site; een pagina laadt alleen de delen die
  haar tekens nodig hebben, en van een lettertype per schrift alleen de delen van dat schrift.
- AC2: het deelplaatje toont dezelfde schriften. Een bewering in zo'n schrift staat erop in plaats van de Engelse versie.
  Tekst zonder spaties (Chinees, Japans, Thai, Khmer) breekt binnen de regel per teken. Een regel van rechts naar links
  staat rechts uitgelijnd en in de leesvolgorde.
- AC3: elk lettertype heeft een open licentie (SIL OFL), met de herkomst in `factiz_site/fonts/HERKOMST.md`; de bestanden
  zijn dezelfde bytes als in het pakket, op een vaste versie van minstens twee weken oud (B78).

**E9.S29 — Een pagina van rechts naar links.** *(PO 2026-11-15: "laten dit direct regelen zodat we ze allemaal achter
elkaar kunnen doen", over Arabisch en Perzisch; PLAN #34.2bd)* Als bezoeker in het Arabisch, Perzisch, Hebreeuws of Urdu
wil ik een pagina die van rechts naar links leest, zonder dat iets verkeerd om staat.
- AC1: een taal van rechts naar links krijgt `dir="rtl"` op de pagina; de site heeft daar één lijst voor (`talen.js`).
- AC2: de opmaak spiegelt: onderdelen en stijlen gebruiken begin en eind, niet links en rechts. Een test weigert links of
  rechts, behalve op een plek met een opgeschreven reden.
- AC3: een pijl die opzij wijst (→, ←) draait mee; een pijl omhoog of omlaag en een toets niet.
- AC4: een bewering houdt haar eigen richting: een Arabische bewering staat rechts in haar kaart, ook op een Engelse
  pagina, en een Engelse bewering links, ook op een Arabische pagina.
- AC5: de balken van de landen op *Verkennen* groeien vanaf het begin van de regel; de wereldkaart en de jaren blijven
  zoals ze zijn, want een kaart en een tijdlijn draaien niet om.
- AC6: voordat een taal van rechts naar links opengaat, zijn de pagina's met `dir="rtl"` nagekeken in de browser, breed
  en op een telefoon.

**E9.S30 — De maker en open source in de voet.** *(PO 2026-11-15: "Een link naar ideelab als maker (voor de backlinks)
... Een link naar de Github repo ... en natuurlijk een zin onderaan met Open Source project, Licenties noemen etc."; PLAN
#34.2bk)* Als bezoeker wil ik zien wie Factiz maakt, dat de code open is en onder welke licenties alles valt.
- AC1: onder de kolommen van de voet één regel: *Open source*, de code onder AGPL-3.0 en het protocol onder CC BY 4.0, elk
  met een link naar de tekst van die licentie, en dat elk gegeven zijn bron en zijn licentie noemt, met een link naar
  *Bronnen en licenties*. Wat er in `LICENSE`, `LICENSE-PROTOCOL.md` en de README staat, is de bron; de voet zegt niets
  anders.
- AC2: in dezelfde regel *Gemaakt door Ideelab*, een gewone link naar https://ideelab.nl/ (een vermelding van de maker,
  zonder `nofollow`).
- AC3: in de kolom *Over* een link naar de broncode op GitHub (`github.com/factiz-org/factiz`). Het repo is nog privé: vóór
  de livegang openbaar, of de link gaat eruit (PLAN #34.2bl). *Sinds 2026-11-17 (PO: "Yes, start"):* zolang het repo privé
  is, staan de link en het woord *Open source* er niet (`BRONCODE_OPENBAAR` in `site/src/layouts/Site.astro`); de licenties
  wel, want die gelden.
- AC4: in de voet alleen deze vier adressen buiten de site; geen script, beeld of lettertype van daar (B78). In elke
  sitetaal.

**E9.S31 — Eén bewering, meer redacties.** *(PO 2026-11-16: "sommige claims kan ik me goed voorstellen dat er meerdere
factcheckers een uitspraak over hebben gedaan, toch noemen we er altijd maar 1. Zijn er checks waar meerdere checkers
uitspraak over hebben gedaan, en zo ja, kunnen we die bundelen?" en "Als dit lukt kun je zelf verder gaan: Zoekend in
Engels heeft een check buiten je eigen taalgebied minder waarde, en wil je eigenlijk zelfs de check zo lokaal mogelijk.";
PLAN #34.2bp)* Als bezoeker op een factcheck wil ik zien welke andere redacties dezelfde bewering checkten, ook in een
andere taal, met de check die het dichtst bij mij staat eerst.
- AC1: twee pagina's gaan over **dezelfde bewering** als ze hetzelfde beweren over hetzelfde: dezelfde gebeurtenis of
  hetzelfde onderwerp, en dezelfde wie, wat, waar, wanneer en getallen voor zover ze genoemd worden. Andere woorden, een
  andere taal, een kortere vorm en een ander jaar van opduiken mogen. Een eigen detail dat de bewering verandert, het
  tegendeel, of een andere bewering over hetzelfde verhaal niet; dat blijft *Lijkt op* (hetzelfde verhaal, E9.S1).
- AC2: kandidaten zijn de buren van *Lijkt op* (bge-m3 op de getoonde tekst, de vijf dichtstbij vanaf 0,80) waarbij de
  twee pagina's geen redactie delen. Een taalmodel zegt per paar *ja*, *nee* of *twijfel*, met beide beweringen zoals de
  site ze toont en in het origineel; alleen *ja* telt. Een paar dat het model niet zelf beoordeelde, telt niet: geen
  ketting van A via B naar C.
- AC3: de paren gaan pas in een uitgave als Claude van 100 willekeurige paren met *ja*, buiten de proef waarop de vraag
  werd bijgesteld, er minstens 98 dezelfde bewering vindt (twijfel telt als niet). De lezing staat in
  `docs/steekproeven/34.2bp-zelfde-bewering.json`; is de poort dicht, dan alleen met `publiceren bouwen --concepten`.
- AC4: een paar is een verwijzing, geen samenvoeging: elke pagina houdt haar nummer, haar bewering en het oordeel van haar
  eigen checks bovenaan (DR2, DR5). Onder *Ook gecheckt door* staan de checks van de andere pagina's, elk met de redactie,
  haar eigen oordeel, de datum, de taal, de bewering zoals die pagina haar toont en een link naar die pagina en naar het
  artikel. Bovenaan de pagina één regel met de namen van die redacties, die naar dat blok wijst.
- AC5: de volgorde van checks, de eigen bij meer dan één en die onder *Ook gecheckt door*: eerst in de taal van de site,
  dan in de taal van de bewering, dan de nieuwste. Het land van een redactie staat niet in de gegevens; dat komt later.
- AC6: hetzelfde antwoord van het platform in Python en in TypeScript (`factiz_site.gelijk`), en de telling die de site
  toont, rekent ze uit de tabellen.
- AC7: in het antwoord bovenaan **wie het checkte en wat elk zegt** (PO 2026-11-22: "Ja graag", na Lee e.a. 2023,
  KENNISBANK K37 en K42; en: "Dus je ziet de drie stempels met daarachter de betreffende redactie. That's it."): per
  redactie haar stempel en haar naam, onder elkaar en zonder zichtbare kop ("Dit kan weg. Dan komen ze netjes onder
  elkaar."; *Gecheckt door* alleen voor een schermlezer), die van deze pagina en die onder *Ook gecheckt door*, elke
  redactie één keer met haar nieuwste oordeel; tot vier allemaal, daarboven drie en *N andere*. Elke redactie linkt naar
  haar eigen check met dat oordeel, op deze pagina of onder *Ook gecheckt door* (PO: "1"); *N andere* naar de lijst. Dit
  neemt de plaats in van de regel met alleen de namen. Alleen bij minstens twee redacties met een oordeel.
  Hun oordelen, nooit een eigen oordeel (DR2).

**E9.S8 — Vindbaarheid in stappen.**
- AC1: het overzicht voor zoekmachines noemt alleen de pagina's van de huidige
  stap; de rest vraagt zoekmachines om hem nog niet op te nemen *(#24.9)*.
- AC2: geen factcheck-opmaak voor Google op de check van een redactie *(B70)*.
- AC3 *(PLAN #34.2bt, PO 2026-11-16: "In two steps", en op 2026-11-17 de eerste stap volgens B73 punt 5: "Yes, start")*:
  vier standen van `FACTIZ_VINDBAAR`. 0: niets vindbaar (`noindex, nofollow`, robots.txt dicht, geen sitemap, geen
  `llms.txt`). In elke open stand de vaste pagina's, overzichten, thema's, dossiers en namen in elke sitetaal, en daarbij:
  1 alleen de factchecks met meer dan één redactie, met *Ook gecheckt door* of in een dossier (B73 punt 5), elk één keer,
  in de taal van haar bewering, anders waar `x_default` heen wijst; 2 elke factcheck zo één keer; 3 elke factcheck in elke
  taal met eigen tekst (DESIGNSYSTEEM §6).
- AC4: `/sitemap.xml` is een index; per taal een sitemap met de vaste pagina's, thema's, dossiers en namen, en per taal
  de factchecks in delen van hoogstens 50.000 adressen, elk met `lastmod`. Er staat alleen in wat in die stand `index`
  zegt, en elke pagina die `index` zegt, staat erin (behalve een volgend blad van een lijst).
- AC5: robots.txt in een open stand laat elke crawler toe, ook voor AI *(PO 2026-11-16: "Everything, training too")*,
  behalve de interne paden en de lijsten met filters (die zeggen `noindex` en zijn eindeloos te combineren); een volgend
  blad, de letters van de namen, de deelplaatjes en de opmaak blijven open. Met de regel `Sitemap:`.
- AC6: `/llms.txt` in een open stand: wat Factiz is en dat het geen eigen oordeel geeft, hoe je een factcheck noemt (de
  redactie is de bron), de ingangen, de bronnen en het contact.
- AC7: IndexNow: een sleutelbestand op de site, en bij een uitgave in een open stand de nieuwe adressen gemeld door de
  uitrol; in stand 0 nooit.
- AC8 *(PLAN #34.2bw, de juridische verkenning van 2026-11-17)*: wat een zoekmachine van een factcheck toont, begint met
  het oordeel: de titel ("False according to Snopes: “Zelensky bought a villa in Florida”", met de aanhalingstekens van de
  taal; sinds 2026-11-19 het stempel met hoogstens één naam, DESIGN §4y), de
  omschrijving en de naam in de gestructureerde gegevens, ook in het kruimelpad. De kale bewering op de pagina en in een rij
  draagt `data-nosnippet`, zodat een fragment in de zoekresultaten haar niet zonder oordeel toont.
- AC9 *(idem)*: een pagina per naam (`/names/Q…/`) zegt `noindex` en staat niet in de sitemap, in elke stand, tot een
  jurist haar bekeek (`NAAMPAGINAS_VINDBAAR` in `site/src/lib/vindbaar.js`); robots.txt laat haar open, want anders ziet
  een zoekmachine de `noindex` niet. Het register met letters blijft vindbaar.
- AC10 *(PO 2026-11-17: "Zullen we een versienummer met datum in de footer zetten zodat we zien tot wanneer de pagina up
  to date is? Misschien ook handig voor google?", "Ja, bouw ze allebei")*: de voet van elke pagina zegt de dag van de
  uitgave en van de nieuwste factcheck erin, als platte tekst met `data-nosnippet`; een `lastmod` in de sitemap alleen waar
  hij klopt (een factcheck: de dag van haar nieuwste check; de start, de lijst, de thema's, de redacties, de bronnen en
  Verkennen: de dag van de uitgave; Over, Platform, de dossiers en de namen geen), en een factcheck zegt dezelfde dag als
  `dateModified` in haar gestructureerde gegevens.
- AC11 *(PO 2026-11-22: "Qua SEO en GEO is het belangrijk dat we vragen afdekken per check die gesteld worden als: 'klopt
  het dat...' 'is het waar dat' heeft...X gedaan? is ...een hoax, is ... waar?", en daarna over de drie oorzaken: "deze
  alledrie oplossen")*: elke factcheck heeft in de taal waarin ze vindbaar is (die van de bewering, anders `x_default`)
  één **zoekvraag** zoals een gewone zoeker haar typt (*Klopt het dat …?*, *Is it true that …?*, *Did X …?*, *Is … a
  hoax?*) en een kort **onderwerp** (een naamwoordgroep, nooit een bewering). De vraag staat als kop boven het antwoord, in
  plaats van *Klopt dit?*; de titel is het oordeel met de vraag (*False according to Snopes: Did Zelensky buy a villa in
  Florida?*) in plaats van de bewering afgekapt op 45 tekens, zodat de namen erin staan en het oordeel voorop blijft (niet
  het onderwerp: *Onwaar: het verlaten van het BRELL-net* leest alsof dat verlaten onwaar is); de omschrijving is het
  oordeel, de vraag en wie het wanneer checkte, en zonder wie en wanneer als dat niet in 160 tekens past. De vraag verraadt
  het antwoord nooit (geen *waarom is … nep*) en houdt de ontkenning van de bewering: het antwoord is het oordeel van de
  redacties, nooit een eigen oordeel (DR2). Een taalmodel schrijft ze (`zoekvraag-v5`); ze gaan in de uitgave na een
  leesproef van 200 nieuwe pagina's met hoogstens 1 fout op de 100 (B87), alleen bij de tekst waaruit ze kwamen. In een
  andere taal, en op een pagina zonder vraag, blijft *Klopt dit?*.
- AC12 *(idem)*: daarna stand 2: elke factcheck één keer vindbaar (B73).
- AC13 *(PO 2026-11-22: "Ja, zo", daarna "Ja, bouw het"; maatregel 2 van de juridische verkenning, PLAN #34.2bw)*: een
  factcheck waarvan de bewering een privépersoon bij naam noemt bij een misdaad, ziekte, dood of seksualiteit, of een
  minderjarige, gaat in geen stand naar een zoekmachine: `noindex` en niet in de sitemap; lezen kan iedereen. Zo ook een
  factcheck waarvan de tekst nog niet gelezen is. Bij een minderjarige in zo'n context, als een tweede lezing het
  bevestigt, staat op de plek van de naam een sticker *naam weggelaten** in de kleur van een markeerstift, geen zwarte
  balk (PO 2026-11-22: "een duidelijke manier om de laten zien, de info is er wel, maar wij kiezen er expres voor het niet
  te tonen"), met onder de bewering de reden: de privacy van een minderjarige. Zo in de bewering, de vertalingen, de
  zoekvraag en elke lijst; in een titel, de omschrijving, de gestructureerde gegevens en het deelplaatje *[naam
  weggelaten]*. De naam staat nergens in de uitgave of de pagina, ook niet verstopt onder de sticker, en het zoekregister
  kent haar niet; een vertaling waarin de naam niet letterlijk staat, blijft weg. De naampagina's blijven dicht (AC9).

**E9.S9 — Uitgeven.**
- AC1: elke publicatie is een release met een manifest en een kaart: wat erin
  staat, wat veranderde, wat slechter werd *(naar B22)*.
- AC2: terugdraaien is het vorige bestand terugzetten.
- AC3: niets gaat live zonder een ja van de PO, en de eerste keer niet zonder
  de juridische toets *(B73)*.

## E10: Een eigen factcheckredactie — Should *(B82, 2026-11-18)*

Factiz schrijft zelf een of twee factchecks per week, in het Nederlands, om na twaalf maanden lid te worden van het
EFCSN. De machine spot en bereidt voor; een mens schrijft, een ander mens leest na. Het archief zelf blijft zonder eigen
oordeel (DR2): de eigen checks staan erin als één redactie tussen de andere.

**E10.S1 — Een lijst per week met wat rondgaat.**
- AC1: elke week tien kandidaten, elk met de bron (een tip, een check in een andere taal, een note, een kanaal), waar het
  rondgaat, hoe vaak gedeeld en de checks die er al van zijn.
- AC2: van een tip of een bericht wordt niets bewaard dat de afzender herkenbaar maakt (B78); een note of post van een
  ander platform komt nooit op de site.
- AC3: een kandidaat die al door een redactie gecheckt is, staat zo in de lijst, zodat de PO geen dubbel werk kiest.

**E10.S2 — Een dossier per gekozen kandidaat.**
- AC1: de berichten met een archiefkopie, de eerdere checks, bronnen die het tegenspreken én die het steunen, wat het
  beeld laat zien, een tijdlijn en een voorstel van een oordeel met de zwakke plekken.
- AC2: elk feit in het dossier draagt zijn bron; wat de machine niet vond, staat er als *niet gevonden*.
- AC3: het dossier is werkmateriaal en verschijnt nooit op de site.

**E10.S3 — De pagina's die de code van het EFCSN vraagt.**
- AC1: de methode met de schaal van oordelen, het correctiebeleid met een logboek, het onpartijdigheidsbeleid, het kanaal
  voor tips, de redactie en wie wat doet, eigendom, rechtsvorm en geld, en het recht op reactie.
- AC2: in elke taal van de site, met de Nederlandse tekst als bron.

**E10.S4 — Een eigen factcheck op de site.**
- AC1: de tekst met minstens twee bronnen voor de kern (behalve als er maar één is), bij naam genoemd, de auteur en de
  nalezer, de datum, en elke correctie met een notitie.
- AC2: ClaimReview-gegevens erbij; in het archief staat de check als redactie *Factiz*, met hetzelfde soort oordeel als de
  andere redacties.
- AC3: niets gaat live zonder een menselijke nalezer die niet de schrijver is; Claude mag schrijven, met de naam *Claude
  (AI)* (B84). De juridische toets volgt (PLAN 37.6); de PO zette de eerste checks live zonder (2026-11-19: "Ja, toch live").
- AC4: wat nog openstaat, staat op de pagina als *Nog uit te zoeken*, met een oproep om bij te dragen en een mail naar de
  redactie (B84); een aanduiding *[FEIT NODIG]* staat nooit op een gepubliceerde pagina.
- AC5: een post van een privépersoon alleen via een archiefkopie (B70); is de post weg of was er geen kopie te maken, dan
  staat de bron er zonder link, met die vermelding.
- AC6: elke check heeft een adres met het jaar en de maand van publicatie en een korte naam van de bewering:
  `/nl/radar/2026/11/klaver-citaat-privebezit/` (PO 2026-11-21: "Jaar en maand"). De naam staat in de check (`adres`, in
  de taal van de check in Latijnse letters; in een ander schrift Engels), de vertalingen dragen een Engelse naam
  (`adres_en`). Binnen een maand botst geen naam. `/radar/2026/` en `/radar/2026/11/` zijn de Radar van dat jaar en die
  maand. Een oud adres (`/radar/<werknaam>/`, `/factiz-checks/<werknaam>/`) stuurt blijvend door.
- AC7: zoekmachines zien het origineel, en een vertaling die de redactie heeft gelezen (PO 2026-11-21: "ja dat ook
  graag"); de pagina zegt dan *machinevertaling, nagelezen door de redactie*. Wordt de vertaling daarna opnieuw gemaakt,
  dan geldt het lezen niet meer.
- AC8: elke vindbare check en elk Radar-overzicht met een gepubliceerde check staat in de sitemap, en een uitrol meldt
  nieuwe en gewijzigde checks bij IndexNow.

**E10.S5 — Het bewijs voor de aanvraag.**
- AC1: per maand het aantal gepubliceerde eigen factchecks, nagelezen, en het logboek van correcties; de etappepoort is
  twaalf maanden met gemiddeld vier per maand.

**E10.S6 — Een overzicht van wat wereldwijd rondgaat (B90, B91, PLAN #37.12).** *Als* lezer *wil ik* de belangrijkste
beweringen die deze week in de wereld rondgingen, uit elke regio, *zodat* Factiz niet alleen laat zien wat een handvol
redacties toevallig aanlevert.
- AC1: elke week een wereldlijst met een vaste verdeling over Europa, Rusland en Oekraïne, de VS, Latijns-Amerika, het
  Midden-Oosten, Afrika, Zuid-Azië en Oost-Azië; de maatstaf van B89 (internationaal, doet ertoe, geen roddel of
  plaatselijke politiek).
- AC2: een overzicht toont de bewering in de woorden van Factiz, waar en wanneer ze rondging, en per redactie die haar
  checkte haar eigen oordeel, de datum, de titel en de link; elke zin met het nummer van zijn bron.
- AC3: geen eigen oordeel van Factiz (DR2) en geen zin van een redactie overgenomen; minstens één check van een lid van
  het IFCN of het EFCSN of van een persbureau.
- AC4: een post van een privépersoon alleen als archiefkopie, nooit een directe link (zoals bij de eigen checks).
- AC5: de checks uit de feed blijven doorzoekbaar, maar de voorpagina toont eerst de eigen checks en de overzichten.
- AC6: een overzicht is een gewone factcheckpagina, geen eigen soort pagina; de herkomst zegt dat Factiz het
  samenstelde (B91).
- AC7: een check van Data Commons komt alleen in een uitgave als hij in de uitgave van 2026-11-23 stond
  (`doublecheck/feed_bevroren.txt.gz`); `publiceren bouwen` weigert zonder dat bestand (B91).
- AC8: in de uitgave (schema 18) is een overzicht een pagina met de checks van de redacties (bron
  `factiz-wereldlijst`) en de tabel `samenvatting`; de factcheckpagina toont *Wat de factcheckers vonden* en *Waar het
  rondging*, elke zin met de redacties die haar dragen en een link naar hun check op de pagina, in het Engels.
- AC9: elk gepubliceerd overzicht is machinevertaald in alle talen van de site (bewering, wat de redacties vonden,
  waar het rondging), met dezelfde bronnummers als het origineel en het label *Machine translation from English*;
  zonder geldige vertaling het Engels met die regel. Samen met de eigen checks hoogstens $5 per week.
