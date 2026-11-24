# Runbook — een instantie draaien en vers houden

*Voor wie een Doublecheck-instantie beheert. Eigenaar: Lead Dev. De besluiten
erachter: B13 (één instantie, forkbaar), B18 (launch), #22.2 (versheid).*

## Wat er draait

- `uvicorn doublecheck.api:app` (of gunicorn met uvicorn-workers).
- Eén werker. Die draagt het embeddingmodel (~2,3 GB in float32 sinds de
  wissel naar bge-m3, #25.14c) en één zoekcache voor alle vragen: ~450 MB
  voor 110k claims en, sinds de claimvarianten aanstaan (#25.17), ~1,9 GB
  voor 460.698 vertalingen; gemeten 4,4 GB RSS. Met de rechter aan (#30.3)
  draagt hij ook diens gewichten, ~2,3 GB in float32, en kost een tekstvraag
  ~0,13 s meer (BENCHMARK §126; RELEASES, de kaart van 2026-10-17). Op een M1 met twee
  rekenthreads 5,5 vragen per seconde bij twee tegelijk, p95 389 ms
  (BENCHMARK §85). De varianten zitten in de database (`claim_variant`); wie
  de database kopieert, kopieert ze mee. Een schone kloon zonder varianten
  draait gewoon, maar zonder de vertalingen: `python -m
  doublecheck.variantenbatch importeren` zet ze erin vanuit
  `data/varianten/corpus/`. Een tweede werker is een
  tweede kopie van alles, leverde 22% op bij twee tegelijk en werd
  slechter bij vier; schaal liever met een tweede instantie.
- De eerste vraag na een herstart laadt model en index: ~9 s. Daarna
  130 tot 150 ms.
- De retentie-sweep draait in de applicatie zelf (elke
  `sweep_interval_hours`); `python -m doublecheck.retention` is het
  cron-vangnet.

## De versheidscadans (#22.2)

Het corpus is een geheugen, en een geheugen dat stilstaat veroudert. De
afspraak: **wekelijks verversen**, vaker rond verkiezingen of een grote
nieuwsgebeurtenis.

```bash
python -m doublecheck.bootstrap --vernieuw --met-veto
```

Dit haalt de feed opnieuw op (`--vernieuw`; zonder die vlag wint de cache en
ververst er níéts), vult idempotent bij (claims dedupliceren op claim_id,
checks op claim_id+url), embedt alleen het nieuwe, herclustert mét NLI-veto,
en legt de run vast. Controle achteraf:

```bash
python -m doublecheck.bootstrap --runs
```

Een tweede run zonder `--vernieuw` hoort `+0 claims` te melden — dat is de
idempotentiecheck uit de suite, live.

**De vooruitblik haalt de feed apart binnen (#28.6 d).** Elke maandag om
04:17 haalt een launchd-taak op de Mac van de Lead Dev de feed naar
`data/vooruitblik/feed/` (de twee jongste standen; de stand is het jongste
element, want `dateModified` is het moment van ophalen). Dat raakt de
database niet: de verversing hierboven blijft een eigen stap. De taak staat
in `~/Library/LaunchAgents/org.factiz.vooruitblik.plist` (uit `deploy/`, met `sed "s|/path/to/factiz|$PWD|"` op de plek
van het repo), het logboek in
`data/vooruitblik/ophalen.log`. Hoeveel verse positieven er per bevroren
release zijn: `python -m doublecheck.vooruitblik tellen`. Een release
bevriezen hoort bij de release zelf: `python -m doublecheck.vooruitblik
bevriezen --release <naam>` (`docs/releases/bevroren.json`, in git).
Uitzetten:

```bash
launchctl bootout gui/$(id -u)/org.factiz.vooruitblik && rm ~/Library/LaunchAgents/org.factiz.vooruitblik.plist
```

**Clusteren zonder de machine heet te laten lopen (#25.4).** Na een import
of een nieuwe bron hoeft niet alles opnieuw: alleen de claims die het
clusteren nog niet zag.

```bash
python -m doublecheck.clustering --incrementeel --threads 2 --pauze 3
```

Porties van 256 claims, elk apart opgeslagen (hervatbaar; `--max-porties N`
om te knippen), hooguit 2 rekenthreads voor numpy én het NLI-model, en rust
tussen porties. Gemeten op een M1 (8 kernen): piek 21% van de machine,
gemiddeld 7%. Een volledige herbouw (`python -m doublecheck.clustering`)
blijft nodig na een wissel van model, drempel of vetomodel; de
incrementele route weigert dan zelf.

**Poortwachters ná elke verversing, vóór er iets gepubliceerd wordt:**

1. `python -m doublecheck.benchmark` — dekking en fouten verschuiven met
   corpusgroei (meer buren = meer kans op een verkeerde); de run legt de
   cijfers vast. Publiceer geen corpuscijfer zonder deze run.
2. `python -m doublecheck.uitgevers --voorstel` — een nieuwe host komt in
   `te_beoordelen` en is niet vindbaar tot iemand hem toelaat (B28, de witte
   lijst): lees drie claims met hun oordeel, en is het een redactie, zet hem
   dan in `uitgevers.json` én met label *redactie* in
   `docs/steekproeven/25.29-uitgevers.json` (de suite eist dat die twee gelijk
   zijn). Rommel krijgt het label *rommel* en komt niet terug in het voorstel;
   verwijderen uit het corpus is een apart besluit. `python -m
   doublecheck.toelating` meldt daarna hoeveel claims buiten de index staan.
3. Een nieuwe **taal** gaat nooit vanzelf mee: B14 eist eerst
   `python -m doublecheck.taalgeschiktheid --feed <bestand>` en een eigen
   benchmark vóór een taal de index in mag.
4. Bij een nieuwe export van Community Notes (handmatig gedownload naar
   `data/communitynotes/`): `python -m doublecheck.communitynotes --importeer`
   voegt de nieuwe bruggen toe als regels in de geschiedenis (#25.16). De
   bron mag niet herverdeeld worden, dus `--herkomst` meldt de database dan
   als niet uitgeefbaar; dat is juist (E7.S6).
5. `python -m doublecheck.vetoblokkades scoren`, dan `meten`: scoort alleen
   de nieuwe paren en meldt de vetoblokkades zonder label. Label die in
   `docs/steekproeven/25.14d-vetolabels.json` met de datum van de ronde in
   `ronde`. Zo groeit de achtergehouden toets voor de vraag uit §86 (zwijgt
   het veto bij bijna-dubbelingen?), zonder dat de grens op de eigen labels
   wordt afgelezen.
6. `python -m doublecheck.vaagmeting meten`, dan `tellen` (#25.28, B28):
   de claims die veel gewone webtekst aantrekken. De vage van vorige keer
   zitten niet meer in de matrix, dus wat bovenkomt is nieuw. `tellen`
   weigert zolang een trekker geen label heeft; label in
   `docs/steekproeven/25.26-vage-claims.json` (*vaag* of *bewering*), dan
   `vaagmeting toepassen`. Wijst er een testpaar naar een nieuwe vage
   claim, dan weigert de benchmark tot `python -m doublecheck.toelating
   --testparen-weg` hem met een rapport heeft weggehaald.

De importregels gelden bij elke verversing vanzelf: B14-taalpoort,
datumhygiëne (#21.4, ongeldige datums worden leeg), uitgeverwering (#17.5)
en herkomst per record (15.3; `--herkomst` zegt of de database uitgegeven
mag worden).

## Een nieuwe uitgave per week (PLAN #35.2)

*PO 2026-11-17: "Ok, nee dan is wekelijkse verversen prima"; elke uitgave live met een ja van de PO.* Twee taken op de Mac:
om 4:17 haalt `org.factiz.vooruitblik` de feed op en werkt het lab bij als er een nieuwe stand is (de regel
`database bijgewerkt uit <feed>: uitgang 0` in `data/vooruitblik/ophalen.log`); om 7:30 kijkt `org.factiz.verversen` of
die stand al een uitgave heeft, en zo niet, dan:

```bash
python -m doublecheck.verversen --melding
```

Dat bouwt de uitgave van vandaag (`data/publicatie/<dag>/`), vraagt alleen voor de nieuwe pagina's thema's, namen en
vertalingen (via de Batch API, hoogstens $10 per uitgave samen, `verversen.GRENS`; onder de routine telt die grens in
plaats van de grens voor altijd van elke stap, `doublecheck/routinegrens.py`), bouwt opnieuw, zet de SQL en het geheugen
klaar (`uitrol voorbereiden`) en schrijft `data/verversen/<dag>.md`: wat er nieuw is per taal, wat elke stap kostte, en
het commando om live te gaan. Live alleen met een ja van de PO:

```bash
python -m doublecheck.uitrol live <dag> --akkoord '<datum>, PO: "<haar woorden>"'
```

- *Wat de stand is:* `python -m doublecheck.verversen stand`; per uitgave `data/verversen/<dag>.json` met elke stap.
- *Eerst zien wat nieuw is, voor $0:* `python -m doublecheck.verversen --tot bouwen`.
- *Een batch die na twee uur nog loopt, of een stap die misging:* de routine stopt met een melding, en de volgende
  aanroep (de volgende ochtend, of met de hand) gaat verder bij die stap; wat al betaald is, wordt niet opnieuw gevraagd.
- *Niets nieuw:* bracht de stand van de feed niets wat factiz.org nog niet heeft, dan gooit de routine haar bouwsel weg.
- *Bewust niet elke week:* de taallabels, de hoofdletters, de oordelen, *Lijkt op* en *Ook gecheckt door*. Hun leesproef
  wordt opnieuw getrokken uit alle antwoorden, dus één nieuw antwoord zou hun poort sluiten en de verrijking uit de hele
  uitgave halen; dat vraagt eerst een vaste steekproef (PLAN #35.2a).
- *Aanzetten:* `sed "s|/path/to/factiz|$PWD|" deploy/org.factiz.verversen.plist > ~/Library/LaunchAgents/org.factiz.verversen.plist && launchctl load
  ~/Library/LaunchAgents/org.factiz.verversen.plist`.
- *Opruimen:* elke uitgave is ~0,8 GB op de Mac (de database, de SQL, het geheugen) en ~0,5 GB in D1. Houd in D1
  hoogstens de draaiende en de vorige; een oude database weghalen is een handeling op het account, met een ja.

## De radar van de eigen redactie (PLAN #37.1, B82)

*PO 2026-11-18: "Ja, bouw de radar maar".* Elke zondag om 22:00 (sinds 2026-11-19; eerder maandag 8:00, toen stond de Mac vaak uit) haalt `org.factiz.radar` de nieuwste export van de
Community Notes van X op en maakt de lijst van de week:

```bash
python -m doublecheck.radarlijst ophalen
python -m doublecheck.radarlijst lijst --melding
```

- *De lijst:* `data/radar/lijst/<dag van de laatste note>.md`, buiten git. Per onderwerp de bewering die op de meeste posts
  rondgaat, met de andere eronder; wat waarschijnlijk geen bewering is (parodie, een bot, een gestolen post) apart onderaan.
  Werkmateriaal voor de PO: zij kiest er een of twee voor een eigen factcheck.
- *Een tip:* `python -m doublecheck.radarlijst tip "<wat er rondgaat>" --link <adres>`; bewaard in `data/radar/tips.jsonl`
  met de datum, nooit wie hem stuurde (B78). De volgende lijst zet de tips van die week onder de onderwerpen.
- *Wat nooit gebeurt:* een notetekst naar een externe dienst of op de site. Alles draait lokaal (bge-m3 op de grafische
  chip, achter de hittewacht).
- *De export loopt achter:* X zet de export van een dag er een of twee dagen later neer; `ophalen` kijkt zes dagen terug en
  laat er hoogstens twee staan (~730 MB elk).
- *Aanzetten:* `sed "s|/path/to/factiz|$PWD|" deploy/org.factiz.radar.plist > ~/Library/LaunchAgents/org.factiz.radar.plist && launchctl load
  ~/Library/LaunchAgents/org.factiz.radar.plist`. Het log staat in `data/radar/launchd.log`.

## Grenzen die in de infra horen (§55)

- **gunicorn `--timeout 30`** als backstop op een hangende werker; de
  applicatiegrenzen (§55: tekst 10k, beeld 8 MB/12 MP, OCR 10 s) vangen het
  normale geval.
- **Rate limiting bij meerdere werkers of achter een proxy**: de ingebouwde
  token-bucket is per proces en ziet achter een proxy alleen het
  proxy-adres. Zet de grens dan in de proxy (`limit_req` met een vertrouwde
  `X-Forwarded-For`) of in een gedeelde store — zie #22.4.

## De site op factiz.org (B80, #34.2bo stap 8)

**Sinds 2026-11-16** (PO: "Yes, factiz.org") staat de site zelf op factiz.org, als de Worker `factiz-site` op het
Ideelab-account, nog met `noindex` en een robots.txt die alles dicht zet (#33.9, B73). De tijdelijke pagina hieronder
staat nog in het Pages-project `factiz-placeholder`, zonder domein.

| wat | instelling |
|---|---|
| Worker | `factiz-site`, uit `site/` met `npm run build:worker`, uitgerold met `npx wrangler deploy --config dist-worker/server/wrangler.json` (elke uitrol met een ja van de PO) |
| domeinen | `factiz.org` en `www.factiz.org` als *Custom Domain* van de Worker (`routes` in `site/wrangler.jsonc`); Cloudflare zet de records zelf. www stuurt blijvend door naar factiz.org (`site/src/lib/koppen.js`) |
| database | D1 `factiz-<release>`, de binding `DB` in `site/wrangler.jsonc`; een nieuwe uitgave is een nieuwe database (`python -m doublecheck.d1uitgave`), nooit over de draaiende heen |
| testadres | geen: `workers_dev` en voorbeeldadressen staan uit |
| koppen | dezelfde als het platform in Python (`KOPPEN` in `factiz_site/app.py`) op elke pagina en elk statisch bestand (`_headers`, gezet door `scripts/worker-voorraad.mjs`); de CSP schrijft Astro |
| tellen | in de D1 `factiz-tellingen` (binding `TELLINGEN`, PO 2026-11-16: "Yes, counting D1"), dezelfde tabel als hieronder; blijft over releases heen. Lezen: `python -m factiz_site.tellen --d1 factiz-tellingen [--dagen 14]` |
| mail | ongewijzigd: Email Routing, MX, DKIM en SPF hieronder |

**Een nieuwe uitgave naar factiz.org:**
1. `python -m doublecheck.uitrol voorbereiden` (op de Mac: de uitgave, de SQL voor D1 en het geheugen; noemt de naam).
2. Met een ja van de PO: `python -m doublecheck.uitrol live <naam> --akkoord '<datum>, PO: "<haar woorden>"'`. Gaat een
   stap mis, dan stopt het; hetzelfde commando gaat verder waar het stopte.
3. `site/wrangler.jsonc` committen. De vorige database blijft op het account tot de PO zegt dat ze weg mag.
4. Opslag (PO 2026-11-23: "Ja, ruim op"): D1 rekent opslag over alle databases samen, 5 GB inbegrepen, daarboven $0,75 per
   GB per maand, en een uitgave is sinds #37.16 ~1,5 GB. Houd alleen de live uitgave en de vorige (en `factiz-tellingen`);
   vraag na een uitrol of de oudste weg mag (`wrangler d1 delete <naam>`, op exacte naam, nooit een database die niet met
   `factiz-` begint). Een eerdere versie van de Worker die een verwijderde database leest, kan niet meer terug: `wrangler
   rollback` alleen naar de versie van de vorige uitgave.

**Open voor zoekmachines, in twee stappen** (PLAN #34.2bt, SPECS E9.S8, PO 2026-11-16: "In two steps", "Everything,
training too"; de eerste stap volgens B73 punt 5, PO 2026-11-17). De schakelaar is `"vars": { "FACTIZ_VINDBAAR": "0" }`
in `site/wrangler.jsonc`: "0" dicht (`noindex`, robots.txt dicht, geen sitemap, geen `llms.txt`); "1" de kern, de
factchecks met meer dan één redactie, *Ook gecheckt door* of in een dossier (5.571 in de uitgave van 2026-11-16b), elk één
keer; "2" elke factcheck één keer, in de taal van haar bewering, anders in het Engels (106.073); "3" alles wat vindbaar is
(525.823 versies). In elke open stand ook de vaste pagina's, thema's, dossiers en 2.649 namen in vijftien talen. Elke stap
is een eigen ja van de PO.
1. Vooraf, door de PO met haar eigen accounts: in Google Search Console het eigendom *Domein* `factiz.org`, bevestigd met
   het TXT-record dat Google geeft (dashboard, factiz.org, DNS, Records, *Add record*, type TXT, naam `@`); in Bing
   Webmaster Tools de site overnemen uit Search Console.
2. Met een ja: de stand op "1" in `site/wrangler.jsonc`, dan `npm --prefix site run build:worker` en de uitrol zoals
   hierboven. Nakijken: `https://factiz.org/robots.txt` noemt de sitemap, `https://factiz.org/sitemap.xml` geeft de index,
   `https://factiz.org/llms.txt` en `https://factiz.org/34e72c3d34148a19b8beeb1a44fad523.txt` bestaan, en een pagina zegt
   `index, follow`. Dan de sitemap (`https://factiz.org/sitemap.xml`) indienen in Search Console en Bing.
3. Vanaf dan meldt `uitrol live` bij elke nieuwe uitgave de nieuwe en gewijzigde adressen aan IndexNow (stap `melden`).
4. Na een week of twee met Search Console (geïndexeerd, uitgesloten en waarom) en een ja: de stand op "2" en uitrollen,
   en zo later naar "3".
5. Terug: de stand op "0" en uitrollen; robots.txt gaat weer dicht en elke pagina zegt weer `noindex`.

**Bewaking** (PLAN #34.2bv): `python -m factiz_site.bewaking` vraagt de vaste pagina's, robots.txt en een stel nieuwe
factchecks en deelplaatjes op (niet uit de cache) en leest de storingen die de Worker telde uit `factiz-tellingen`; één
regel per ronde in `data/bewaking/log.jsonl`. Elke dag om 9:07, met een melding op de Mac bij een probleem: `sed "s|/path/to/factiz|$PWD|"
deploy/org.factiz.bewaking.plist > ~/Library/LaunchAgents/org.factiz.bewaking.plist && launchctl load ~/Library/LaunchAgents/org.factiz.bewaking.plist`
(met een ja van de PO). De storingen per dag staan ook in `python -m factiz_site.tellen --d1 factiz-tellingen`.

**Hoe de overstap ging, en wat daarbij in de weg zit:** Cloudflare koppelt een Custom Domain niet zolang er nog een
DNS-record voor die naam staat (code 100117, *externally managed DNS records*), ook niet nadat Pages het domein heeft
losgelaten, en de login van wrangler (OAuth) mag geen DNS-records lezen of wijzigen. Dus: eerst haalt de PO in het
dashboard (factiz.org, DNS, Records) de CNAME's weg, dan de uitrol. Op 2026-11-16 wachtte een klein script tot de
naamserver van Cloudflare beide namen leeg gaf en rolde toen uit: 24 seconden tussen weg en live. Daarna gingen de twee
domeinen via de API uit het Pages-project (dat mag de login van wrangler wel). MX, DKIM en SPF bleven staan.

**Terug naar de tijdelijke pagina** (onderhoud of een fout die niet snel op te lossen is):
1. In het dashboard bij de Worker `factiz-site`, *Settings*, *Domains & Routes*: de twee domeinen weghalen, en daarna de
   `routes` uit `site/wrangler.jsonc`, anders zet de volgende uitrol ze terug.
2. In het Pages-project `factiz-placeholder`, *Custom domains*: `factiz.org` en `www.factiz.org` weer toevoegen.
   Cloudflare zet de CNAME's zelf.
3. Nakijken met `curl -sI https://factiz.org/`: de pagina zonder de kop `x-factiz-cache`.

## De tijdelijke site live (#23.17)

Eén pagina op factiz.org, tot de echte site het verhaal van V1 vertelt (DESIGN §4n). **Live van 2026-11-10 tot
2026-11-16**; sindsdien staat de site zelf op factiz.org (hierboven).

### Hoe het nu staat (2026-11-10)

*Aantekening voor later (PO: "zet in de aantekeningen dat we nu handmatig hebben geupload onder 'placeholder' naam en
de settings zodat we dat later nog weten").*

| wat | instelling |
|---|---|
| account | Cloudflare-account *Ideelab* |
| domein | factiz.org: registrar en naamservers bij Cloudflare, DNS-instelling *Full* |
| Pages-project | `factiz-placeholder`, **met de hand geüpload** (*Upload assets*), zonder Git. Testadres: `factiz-placeholder.pages.dev`. Kan bij Cloudflare later niet naar Git; voor Git komt er een nieuw project en verhuist het domein |
| wat er geüpload is | de map `web/dist-placeholder` uit `npm run build:placeholder`, de stand van commit `ce7eb1e` en later |
| eigen domeinen | `factiz.org` en `www.factiz.org`, allebei *Active* met SSL. Elk is een CNAME naar `factiz-placeholder.pages.dev`, via Cloudflare (proxied). factiz.org is het hoofdadres (de canonieke URL van de pagina); www stuurt nog niet door |
| Email Routing | aan. Drie MX-records (`route1`, `route2`, `route3.mx.cloudflare.net`), DKIM `cf2024-1._domainkey`, SPF `v=spf1 include:_spf.mx.cloudflare.net ~all`. Regel: `info@factiz.org` stuurt door naar het adres van de PO. De catch-all staat uit, dus andere adressen op factiz.org ontvangen niets. Versturen vanaf info@ kan niet |
| Email Address Obfuscation | **uit** (Security, Settings), zie stap 4 hieronder |
| beveiligingsheaders | uit `web/public/_headers`, meegeüpload: een dichte CSP, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, HSTS |
| try.factiz.org | bestaat nog niet; de controle staat uit (B54) |

**Een nieuwe versie zetten:**
1. `npm run build:placeholder` in `web/`; de tests in `tests/test_placeholder.py` moeten slagen.
2. In het project `factiz-placeholder`: *Create deployment*, en de map `web/dist-placeholder` slepen.
3. Nakijken zoals in stap 5 hieronder.

Elke upload is een eigen versie onder *Deployments*. Een oude versie zet je terug met *Rollback*.

### De stappen van de livegang

Stand vóór de livegang, op 2026-11-09:
- het domein stond bij Cloudflare (registrar en naamservers);
- er was nog geen record voor de site en geen record voor mail.

Wat de PO doet, in het dashboard van Cloudflare:

1. **Bouwen.**
   - Kies **met Git**: Workers & Pages, Create, Pages, en koppel de repo `factiz-org/factiz` (privé mag). Vul in:
     - root directory `web`;
     - build command `npm ci && npm run build:placeholder`;
     - output directory `dist-placeholder`;
     - de variabele `NODE_VERSION` = `22`.

     Elke push bouwt opnieuw.
   - Of **met de hand**: lokaal `npm run build:placeholder` in `web/`, en de map `web/dist-placeholder` slepen naar
     *Upload assets* van een nieuw Pages-project. *Gekozen door de PO, 2026-11-10: "route 1 doen we dan idd".* Een
     project dat zo begint, kan bij Cloudflare later niet naar Git. Komt de repo later toch, dan maak je een nieuw
     project en verhuis je het domein.
2. **Het domein:** in het project, Custom domains, eerst `factiz.org`, dan `www.factiz.org`. Cloudflare zet de records
   zelf, want het domein staat er al.
3. **De mail:**
   - Email Routing voor factiz.org aanzetten, met het adres `info@factiz.org` dat doorstuurt naar je eigen inbox.
     Cloudflare zet de MX- en TXT-records zelf. Gratis.
   - Antwoorden vanaf info@ vraagt een verzendroute, zoals "Send mail as" in Gmail met een SMTP-dienst. Tot die er is,
     antwoord je vanaf je eigen adres.
4. **Email Address Obfuscation uit** (Security, Settings). Die instelling van Cloudflare staat standaard aan.
   - *Wat ze doet:* ze vervangt elk e-mailadres in de pagina door `/cdn-cgi/l/email-protection` en "[email protected]",
     en voegt een eigen script toe om het terug te zetten.
   - *Waarom uit:* onze pagina laat geen scripts toe. De knoppen kwamen daardoor op een pagina van Cloudflare uit, en
     "No cookies, no scripts." klopte niet meer.
   - *Uitgezet op 2026-11-10* door Claude, PO: "graag".
5. **Controleren:**
   - `https://factiz.org` laat de pagina zien;
   - `curl -s https://factiz.org/ | grep -c email-protection` geeft 0, en de enige `<script>` is de gestructureerde
     data;
   - `curl -sI https://factiz.org/` toont de beveiligingsheaders uit `web/public/_headers`, waaronder
     `Content-Security-Policy`;
   - een testmail aan info@factiz.org komt aan;
   - een link naar factiz.org in een chat toont het beeld bij delen (`merk/og.jpg`).

try.factiz.org blijft uit: de controle staat uit tot de livegang van het product (B54). Daarna gaan de partnermails
(`docs/voorstellen/partnermails.md`).

## Deploy: try.factiz.org op Hetzner (B21)

Het artefactpad is volledig EU: de app draait direct op een Hetzner-VPS,
TLS op de machine zelf, geen Amerikaanse proxy ervoor. De brochure
(factiz.org) staat los hiervan op Cloudflare Pages; daar stroomt geen
gebruikersdata.

**Als code.** Alles hieronder staat uitvoerbaar in `deploy/`:
`provision.sh` (idempotent, als root), `factiz.service` en `Caddyfile`.
Eén keer kopiëren en draaien; het script stopt met instructie als de
deploy key nog niet in GitHub staat en gaat bij de tweede run verder.
`tests/test_deploy.py` houdt die bestanden gelijk aan dit draaiboek
(OCR-talen uit config, §55-timeout, poort, accesslogs uit).

```bash
scp -r deploy root@<ip>:/root/ && ssh root@<ip> bash /root/deploy/provision.sh
scp doublecheck.db factiz@<ip>:/home/factiz/app/doublecheck.db
scp -r data/rechterset/rechter-d@0744e8eea8ce factiz@<ip>:/home/factiz/app/data/rechterset/
```

De gewichten van de rechter (#30.3, 2,3 GB) zitten niet in git, net als de
database. `provision.sh` maakt de map aan en start de dienst pas als ze er
staan: met de rechter aan en zonder gewichten weigert elke tekstvraag (DR6,
de versie is de hash van de gewichten). Na een nieuwe rechter in
`config.toml` kopieer je de nieuwe map en herstart je de dienst.

De site op Cloudflare Pages is sinds #23.11 een Astro-project in `web/`.
Instellingen in Pages: hoofdmap `web`, buildopdracht `npm ci && npm run
build`, uitvoermap `dist`, Node 22. `web/public/_headers` zet een dichte
Content-Security-Policy (geen scripts, geen verbindingen, geen referrer),
zodat de privacybelofte ook technisch vastligt, en `web/public/_redirects`
laat de oude `.html`-adressen permanent naar de nieuwe mappen wijzen. Lokaal:
`python -m doublecheck.sitevoorbeeld` bouwt de site als de bron nieuwer is
en zet hem samen met demo, Ask en cijfers op één poort.

**Maat.** CPX31-klasse (4 vCPU x86, 8 GB) paste voor één werker (~4,4 GB
met de claimvarianten), met ruimte voor het systeem en Caddy. Met de rechter
aan (#30.3) komt daar ~2,3 GB bij: ~6,7 GB voor één werker, krap op 8 GB.
Kies daarom de klasse met 16 GB (CPX41), of meet op een CPX31 eerst de RSS
onder de rooktest (#23.4) voordat de pers komt. Zie "Wat er draait" voor de geheugenposten en waarom het
één werker is. Ubuntu 24.04 LTS levert Python 3.12.

**Provisionering** (eenmalig, als root):

```bash
apt update && apt install -y python3.12-venv git caddy ufw \
  tesseract-ocr tesseract-ocr-nld tesseract-ocr-deu tesseract-ocr-fra tesseract-ocr-spa \
  tesseract-ocr-osd tesseract-ocr-ara tesseract-ocr-fas tesseract-ocr-urd tesseract-ocr-ben tesseract-ocr-asm tesseract-ocr-rus tesseract-ocr-mon tesseract-ocr-hin tesseract-ocr-mar tesseract-ocr-nep tesseract-ocr-amh tesseract-ocr-guj tesseract-ocr-pan tesseract-ocr-chi-sim tesseract-ocr-chi-tra tesseract-ocr-kor tesseract-ocr-heb tesseract-ocr-jpn tesseract-ocr-kan tesseract-ocr-khm tesseract-ocr-lao tesseract-ocr-mal tesseract-ocr-sin tesseract-ocr-tam tesseract-ocr-tel tesseract-ocr-tha
ufw allow 22/tcp && ufw allow 80/tcp && ufw allow 443/tcp && ufw enable
adduser --system --group --home /home/factiz factiz
```

De tesseract-pakketten volgen `config.toml [ocr] languages`
(`nld+eng+deu+fra+spa`; `eng` zit in het basispakket). Wie daar een taal
bij zet, zet hier het apt-pakket bij.

**App en corpus** (als `factiz`):

```bash
git clone https://github.com/factiz-org/factiz.git /home/factiz/app && cd /home/factiz/app
```

Zolang de repository privé is (tot de launch, #23.5) clonet de server met
een read-only deploy key (repo-instellingen → Deploy keys) of een
fine-grained token; daarna kan het anoniem.

```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt gunicorn
```

Corpus: óf ter plekke bouwen (`python -m doublecheck.bootstrap`, het
embedden kost op 4 vCPU uren), óf de eigen `doublecheck.db` kopiëren
(scp; zelfde modelversies, dus geen reindex — DR6 weigert anders
vanzelf) en `--runs` als controle draaien. De eerste start downloadt het
embeddingmodel van Hugging Face; dat is eenmalig en hoort bij de
provisionering, niet bij het eerste bezoek.

**systemd** (`/etc/systemd/system/factiz.service`):

```ini
[Unit]
Description=Factiz resolver
After=network-online.target

[Service]
User=factiz
WorkingDirectory=/home/factiz/app
Environment=DOUBLECHECK_DB=/home/factiz/app/doublecheck.db
ExecStart=/home/factiz/app/.venv/bin/gunicorn doublecheck.api:app \
  -k uvicorn.workers.UvicornWorker -w 1 -b 127.0.0.1:8787 --timeout 30
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

Eén werker (§77i): elke extra werker draagt een eigen model en
zoekcache en vecht om dezelfde kernen. Meet vóór je verhoogt.

**Caddy** (`/etc/caddy/Caddyfile`) regelt TLS via Let's Encrypt:

```
try.factiz.org {
    reverse_proxy 127.0.0.1:8787
}
```

Achter de proxy ziet de ingebouwde token-bucket alleen 127.0.0.1 en
degradeert hij tot één gedeelde emmer: veilig voor de machine, oneerlijk
bij één veelvrager. Dat is de in B21 geaccepteerde trade-off; 429's
tijdens een piek zijn het schild dat werkt, geen storing. Per-IP-grenzen
vergen `X-Forwarded-For`-vertrouwen in de applicatie — zie #22.4 en
`docs/MISBRUIK.md`.

**Accesslogs blijven uit.** De privacyverklaring op factiz.org belooft
dat geen log een IP-adres koppelt aan wat er gecheckt werd. Gunicorn
(zonder `--access-logfile`) en Caddy (zonder `log`-directief) staan
standaard goed: laat dat zo, en zet bij debuggen hoogstens tijdelijk een
log aan zónder request-pad.

**DNS** (Cloudflare, alleen DNS): A-record `try` → VPS-IP met proxystatus
**DNS only** (grijze wolk). De oranje wolk gaat nooit aan voor `try` —
dat is precies de VS-tussenlaag die B21 uitsluit.

**Backups en de verwijderbelofte (B11).** De corpus-db is herbouwbaar;
het unieke op de machine zijn betwistingsartefacten mét bewaartermijn en
verwijdersleutel. Een snapshotreeks die langer leeft dan die termijn
breekt de belofte stilletjes: zet Hetzner-backups op de kortste cyclus
(7 dagen) en laat de dagelijkse retention-cron
(`python -m doublecheck.retention`) het vangnet zijn.

**Cron** (als `factiz`):

```
17 4 * * *  cd /home/factiz/app && .venv/bin/python -m doublecheck.retention
```

De wekelijkse verversing draait bewust niet uit cron: de poortwachters
erna (zie "De versheidscadans") zijn mensenwerk.

**Rooktest ná elke deploy** (#23.4): `curl https://try.factiz.org/.well-known/doublecheck`,
de demochips en de voorbeeldvragen op `/ask` naklikken, en `python -m conformance https://try.factiz.org
--proeven deploy/conformantie-proeven.json` met uitgang 2 en alleen
verplichting 3 onwaargenomen (zie hieronder); de JSON-uitvoer gaat naar het
dashboard (zie "Het eerlijkheidsdashboard").

## Tellen op het platform (#34.2ba, B78)

- **Aan:** start het platform met `FACTIZ_TELLINGEN=/var/lib/factiz/tellingen.db` (een map die het proces mag schrijven).
  Zonder die variabele telt de site niets.
- **Wat erin staat:** per dag (UTC), soort pagina of zoektelling, en taal één getal. Geen IP-adres, cookie, zoektekst,
  adres of user-agent (SPECS E9.S26).
- **Lezen:** `python -m factiz_site.tellen /var/lib/factiz/tellingen.db [--dagen 14]`.
- **Niet van buiten:** `/api/tel` is alleen voor de site. Het platform staat niet open naar het internet, en de site
  stuurt die ingang niet door.
- **Stoppen:** een gewone stop (SIGTERM) schrijft weg wat nog in het geheugen staat; een crash verliest hoogstens de
  laatste minuut.
- **Cache:** een pagina die Cloudflare uit zijn cache geeft, komt niet bij de server en telt dus niet.
- **Op factiz.org (de Worker, sinds 2026-11-16):** elk bezoek is één upsert in de D1 `factiz-tellingen`, na het antwoord
  (`waitUntil`), ook een bezoek uit de paginacache (de soort en taal staan op de bewaarde kopie). Een user-agent die op een
  robot lijkt (ook curl) telt als `robot`. Lezen: `python -m factiz_site.tellen --d1 factiz-tellingen [--dagen 14]`, één
  leesvraag via wrangler. De tabel maakte `python -c 'from factiz_site.tellen import SCHEMA; print(SCHEMA)'` met
  `wrangler d1 execute factiz-tellingen --remote --command`; een nieuwe uitgave raakt haar niet.

## Herstel

- Schone kloon → werkend corpus: `python -m doublecheck.bootstrap` (#15.3;
  `--plan` zegt eerst wat het kost).
- Modelwissel: nooit stil doorrekenen (DR6) — `python -m doublecheck.reindex`
  en daarna de benchmark.

## De Anthropic-sleutel (#25.17, #23.9)

Alleen offline gebruikt: de claimvarianten (`doublecheck.varianten`,
`doublecheck.variantenbatch`). Het aanvraagpad praat nooit met een
taalmodel (DR3, B26); een test bewaakt dat de API de client niet laadt.

- **Waar:** `ANTHROPIC_API_KEY` in `.env`, buiten git. Nooit in de chat,
  in code of in een log; `laad_sleutel()` leest het bestand zonder iets te
  tonen.
- **Wie:** voorlopig de persoonlijke sleutel van de PO. Vóór de lancering
  (#23.9): in de Console (`platform.claude.com`) een eigen werkruimte voor
  Factiz, daar een nieuwe sleutel, die in `.env` op de machine die de
  varianten draait, een proefrun (`python -m doublecheck.variantenbatch
  plan`), en dan de persoonlijke sleutel intrekken.
- **Bestedingslimiet:** onder Settings → Limits
  (`platform.claude.com/settings/limits`). Zet hem dicht boven wat een
  run kost, niet ruim: de limiet is het enige vangnet voor alles op die
  sleutel. Let op het verschil in tellen: de Console rekent een batch af
  terwijl hij verwerkt wordt, `variantenbatch` telt pas wat is opgehaald.
  Op 11 oktober 2026 ging de limiet van $20 daardoor over terwijl `plan`
  nog $11,37 zei: twee batches waren al verwerkt maar niet opgehaald.
  Reken dus met het verwachte totaal uit `plan`, niet met "uitgegeven".
- **Wat een run kost:** de corpusrun van 109.600 claims in vijf talen
  kostte $17,82 met de batchkorting ($0,00016 per claim), de proef op
  1.308 claims in vijftien talen $1,41. `variantenbatch` dient eerst een
  proefbatch van 2.000 claims in en de rest pas als de doorrekening onder
  `--budget` blijft.

## Voetnoten uit de praktijk

- **Draai de suite niet middenin een verversing**: de herclusterstap houdt
  de database kort vast; een test die het echte corpus leest kan dan één
  keer `database is locked` zien (waargenomen bij #22.2; groen na afloop).
- **Ook een +0-run herclustert**: dat is de vaste prijs van de routine, geen
  bug — de clusterstand hoort bij de corpusstand.
- **Misbruik op een publieksinstantie**: zie `docs/MISBRUIK.md`.

## De hardeningsronde (B24)

Elke twee weken, na de wekelijkse verversing. Een ronde is af als elk
gevonden mechanisme een reparatie mét test én meting heeft, of een
opgeschreven reden waarom het blijft.

1. **Nieuw materiaal erin.** Verversing (zie de cadans hierboven), nieuwe
   bronnen via het bronregister (licentie vóór import, DR10), en de
   wildset aanvullen met wat trackers de afgelopen twee weken meldden.
2. **Meten.** `python -m doublecheck.benchmark` op alle talen (de benchmark
   weigert een ongemeten taal boven `[benchmark] min_claims_voor_cijfer`),
   de wildset zodra die bestaat (de systeemtest, #28), de linkronde van
   de bonnetjes (#25.9, hieronder), de ruwe beeldtest
   (`python -m doublecheck.ruwetest --m4fc data/extern/m4fc`, #25.10) en de
   netwerktoets (`python -m doublecheck.netwerktoets`, #28.5). Een fout in
   die twee is meestal dezelfde claim bij een andere redactie buiten het
   cluster: kijk ze na met `--herbekijk` voordat je ze telt. Kijk per uitgever: een
   oplopend aandeel dode links is het vroegsignaal voor een gerichte
   archiefronde (#25.9c); Logically Facts verdween zonder dat iemand het
   zag aankomen. De 53 vragen van Ask Factiz
   (`python -m doublecheck.vraagtoets`, #24.10) horen er ook bij: zakt het
   aantal goede antwoorden op de eerste regel of tussen de getoonde regels
   (§112–§113), dan zoekt stap 3 de oorzaak. En de terugkijktoets
   (`python -m doublecheck.terugkijk meten`, dan `tellen` na het labelen van
   nieuwe ander-records, #28.6 c): het eerste punt onder het kopgetal, of
   Factiz een eerder gecheckte post met het geheugen van die dag terugvond
   (§116, 22,4% bij de eerste meting).

   **De linkronde (#25.9).** Elke check-link één keer, per host één
   verzoek tegelijk met twee seconden pauze en robots.txt; alleen status
   en eindadres, nooit de inhoud. Een volle ronde duurt ongeveer acht uur
   (factly.in bepaalt de duur) en is hervatbaar, ook na een herstart:

   ```bash
   python -m doublecheck.bonnetjes controleren
   python -m doublecheck.bonnetjes toepassen --ronde data/bonnetjes/ronde-<datum>.jsonl
   python -m doublecheck.bonnetjes rapport --ronde data/bonnetjes/ronde-<datum>.jsonl
   ```

   Onderbroken? `controleren --ronde data/bonnetjes/ronde-<datum>.jsonl`
   gaat verder in dezelfde log. Een link heet pas offline na twee dode
   waarnemingen met minstens een dag ertussen, dus minstens 24 uur na het
   einde van de ronde: `controleren --alleen-dood`, `toepassen` op die
   log, en dan `archief` (alleen leesvragen aan de Wayback Machine, nooit
   opslagverzoeken). Toepassen schrijft in één transactie; een draaiende
   resolver verliest zijn zoekcache dus één keer per ronde, niet per link.
   Het rapport geeft per uitgever het aandeel dood en een waarschuwing
   vanaf 10 dode links en 20% (`[bonnetjes]` in config).
3. **Analyseren per mechanisme.** Fouten groeperen naar oorzaak, niet naar
   taal: in run #41–#43 had 100 van de 110 fouten één oorzaak (een
   ontkenningswachter die vijf talen niet kende), en daarna 24 van de 38
   een tweede (ontkenning zien in plaats van tellen).
4. **Eén reparatie per mechanisme**, test eerst, hermeting op alle talen.
   Wat verslechtert staat in BENCHMARK.md, ook als het totaal beter wordt.
5. **De techniekcatalogus bijwerken** met de vormen die deze ronde
   opdoken (#27). `python -m doublecheck.evergreen` zegt welke verhalen
   opnieuw gecheckt zijn (§111); een evergreen met een verschuivende kant
   is een kandidaat om na te lezen, geen vaststelling.
6. **Publiceren.** Het rondecijfer op `/numbers` en een regel in de
   changelog; een verschoven poortcijfer is per B22 een tussenrelease.

## Het eerlijkheidsdashboard (#22.5)

`GET /numbers` (alias `/cijfers`) rendert per verzoek vers uit de metingen: benchmarkruns (mét
de missers), corpusstand, importlogboek en de conformantie-uitvoer. Twee
beheerafspraken:

- Ná elke verversing of deploy: `python -m conformance <url> --proeven
  deploy/conformantie-proeven.json --json > data/conformance-latest.json`
  (pad instelbaar via
  `DOUBLECHECK_CONFORMANTIE`). Zonder dat bestand toont de pagina eerlijk
  "nog geen uitvoer" — hij verzint geen vinkje.
- Uitgang 2 (conform, niet volledig getoetst) is voor v1 de verwáchte stand:
  verplichting 3 vergt een `assessed`-antwoord en niets in v1 produceert
  dat. Het dashboard legt dat vraagteken uit in plaats van het te verbergen.
  Staat er ook een vraagteken bij verplichting 10, dan matchte de proef
  `variant-en` niet via een vertaling: kijk of de varianten in de database
  staan (de ontdekking noemt ze onder `variants`).
