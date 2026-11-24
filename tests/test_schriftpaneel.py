"""Schriftguard: code mag niet stilzwijgend Latijn aannemen (PLAN.md #18.2).

Vijf keer ging dit mis — §17a, §39, §45, §46, §48c/§50c — en de reden dat het
vijf keer kon, is dat de fout **per constructie buiten elke meting viel**: de
tests draaiden op Latijnse invoer en de cijfers werden er beter van.

Deze guard bestaat uit twee delen, en het tweede is het belangrijkste.

**Het paneel.** `tests/schriften.py` draagt 31 echte teksten in 24 schriften.
Elke tekstfunctie wordt erop losgelaten, met het contract dat bij haar hoort.

**De volledigheidscontrole.** Elke functie in `doublecheck` die één `str`
aanneemt moet hieronder staan — mét contract, óf met een opgeschreven reden om
haar over te slaan. Wie een nieuwe tekstnormalisator bouwt, wordt gedwongen op
te schrijven hoe die zich tegenover schrift verhoudt. Een lijst die je moet
onthouden veroudert; een lijst die de test afdwingt niet.
"""

from __future__ import annotations

import importlib
import inspect
import pkgutil
import unicodedata

import pytest

import doublecheck
from tests.schriften import PANEEL

# --- contracten -------------------------------------------------------------
NOOIT_LEEG = "nooit_leeg"          # niet-lege invoer geeft nooit lege uitvoer
BEHOUDT_LETTERS = "behoudt_letters"  # geen letter of combinerend teken verdwijnt
ONDERSCHEIDT = "onderscheidt"      # verschillende teksten blijven verschillend
GELDIG = "geldig"                  # geeft antwoord zonder te struikelen
VERANDERT = "verandert"            # de uitvoer is nooit gelijk aan de invoer

CONTRACTEN: dict[str, set[str]] = {
    # Identiteitssleutels: hier ging het twee keer mis (§48c, §50c).
    "evidence:_uitgeversleutel": {NOOIT_LEEG, BEHOUDT_LETTERS, ONDERSCHEIDT},
    "verdicts:_normaliseer_label": {NOOIT_LEEG, BEHOUDT_LETTERS, ONDERSCHEIDT},
    "embedding:normaliseer_voor_embedding": {NOOIT_LEEG, BEHOUDT_LETTERS, ONDERSCHEIDT},
    "relation:_vouw_cijfers": {NOOIT_LEEG, BEHOUDT_LETTERS, ONDERSCHEIDT},
    "ingest:claim_id_for_text": {NOOIT_LEEG, ONDERSCHEIDT},
    "claimfilter:normaliseer_voor_filter": {NOOIT_LEEG, BEHOUDT_LETTERS, ONDERSCHEIDT},
    "claimfilter:sleutels": {GELDIG},
    "attributie:_sleutel": {NOOIT_LEEG, BEHOUDT_LETTERS, ONDERSCHEIDT},
    "dispute:hash_deletion_key": {NOOIT_LEEG, ONDERSCHEIDT},
    # De sleutel waarmee de uitgave ziet of een "vertaling" alleen het origineel herhaalt (#33.5): wie hier een
    # schrift leeg maakt, noemt elke vertaling in dat schrift een herhaling en gooit haar weg.
    "publiceren:_kaal": {NOOIT_LEEG, BEHOUDT_LETTERS, ONDERSCHEIDT},
    # Een naam van een persoon, organisatie of plaats (#33.7): het model geeft de Engelse vorm, maar niet elke naam
    # heeft er een. Wie hier een schrift leeg maakt of klinkertekens laat vallen, gooit twee namen op één hoop.
    "namen:schoon": {NOOIT_LEEG, BEHOUDT_LETTERS, ONDERSCHEIDT},
    "namen:sleutel": {NOOIT_LEEG, BEHOUDT_LETTERS, ONDERSCHEIDT},
    # De woorden waarin een naam gezocht wordt: letters, klinkertekens en cijfers blijven, in elk schrift.
    "namen:_woorden": {NOOIT_LEEG},
    # De sleutel waaronder de woorden van een redactie gelezen en vertaald worden (#34.2o): wie hier een schrift leeg
    # maakt of twee oordelen samenvoegt, geeft het ene oordeel het label van het andere.
    "oordeellezer:sleutel": {NOOIT_LEEG, BEHOUDT_LETTERS, ONDERSCHEIDT},
    # De bewering en de weerlegging van EUvsDisinfo uit de HTML van hun server (#35.3): alleen labels gaan eruit, nooit
    # een letter, in elk schrift.
    "euvsdisinfo:platte_tekst": {NOOIT_LEEG, BEHOUDT_LETTERS, ONDERSCHEIDT},
    # Een zin van de wereldlijst zoals de site haar toont (#37.12): alleen de nummers van de bronnen gaan eruit, elke letter
    # in elk schrift blijft.
    "wereldlijst:zonder_nummers": {NOOIT_LEEG, BEHOUDT_LETTERS},
    # Wat het model van een bewering ziet als het twee pagina's naast elkaar legt (#34.2bp): wie hier een schrift leeg
    # maakt of klinkertekens laat vallen, laat het model twee lege of verminkte beweringen vergelijken.
    "zelfdebewering:_kort": {NOOIT_LEEG, BEHOUDT_LETTERS, ONDERSCHEIDT},
    # Classificeerders en extractors: ze mogen samenvoegen, maar niet stikken.
    "verdicts:normalize_verdict": {GELDIG},
    # Hoofdletters in normaal schrift (#34.2ae): ja of nee voor elk schrift; een schrift zonder hoofdletters is het nooit.
    "hoofdletters:in_hoofdletters": {GELDIG},
    "zoekvragen:schriften": {GELDIG, NOOIT_LEEG},
    "publiceren:_naampatroon": {GELDIG},     # het patroon van een naam die initialen wordt, in elk schrift     # elk schrift heeft een naam, ook een dat de site niet kent
    # De vorm van een bewering (#34.2ak): video, beeld of niets, voor elk schrift; alleen Engelse woorden tellen.
    "soortvorm:vorm_van": {GELDIG},
    # Vergelijkingssleutel: in Arabisch schrift vallen spaties en halve spaties
    # weg (#25.3b), dus "onderscheidt" geldt bewust niet; letters blijven.
    "verdicts:_compact": {NOOIT_LEEG, BEHOUDT_LETTERS},
    "verdicts:_tabel": {GELDIG},
    # De vergelijking van B48: de woorden van een vals detail in het bericht en de passage, in elk schrift.
    "berichtcontrole:_gewoon": {NOOIT_LEEG, BEHOUDT_LETTERS},
    "detailmeting:_gewoon": {NOOIT_LEEG, BEHOUDT_LETTERS},
    "vloer:_gewoon": {NOOIT_LEEG, BEHOUDT_LETTERS},
    # De voormeting van de kruiscontrole (#32.3d) leest berichten en passages in elk schrift.
    "kruiscontrole:_woorden": {GELDIG},
    # Route A (#32.38): de bewering zonder HTML, in elk schrift; en of ze de conclusie van de redactie is.
    "terugaanvoer:zonder_html": {NOOIT_LEEG, BEHOUDT_LETTERS, ONDERSCHEIDT},
    "terugaanvoer:is_conclusie": {GELDIG},
    "beeldpaar:bron_van": {GELDIG},
    "kruiscontrole:_namen": {GELDIG},
    "kruiscontrole:_contexten": {GELDIG},
    # De koppen van de dichte sites (#32.3f): woorden van een kop, bronnen en links uit wikitekst, in elk schrift.
    "koppen:_woorden": {GELDIG},
    "koppen:citaten": {GELDIG},
    "koppen:portal_links": {GELDIG},
    # De eindtoets (#32.8): de gebeurtenissen van een dag uit Portal:Current events, in elk schrift.
    "eindtoets:portal_zinnen": {GELDIG},
    # De beeldindex (#32.15): de artikellinks van een dag van Portal:Current events en de sjablonen van imgflip.
    "beeldindexmeting:portal_artikelen": {GELDIG},
    # #32.17: een beschrijving in elk schrift gaat ongewijzigd naar het zoeken; een beeldadres in elk schrift
    # (Arabische paden in M4FC) moet zijn kopie in de Wayback Machine terugvinden (tests/test_beeldbevestiging.py)
    "beschrijvingvraag:lees_beschrijving": {GELDIG},
    "beeldbevestiging:_adres": {GELDIG},
    # #32.19: de proef van route A leest pagina's en adressen in elk schrift
    "eigenaanvoer:claimreviews": {GELDIG},
    "eigenaanvoer:adres": {GELDIG},
    "beeldstap:adres": {GELDIG},  # #32.35: hetzelfde adres als de database en de oogst, in elk schrift
    "beeldindexmeting:imgflip_sjablonen": {GELDIG},
    # Zoeken eerst (#32.9): de zoekvraag is het bericht zelf, in de eerste 50 woorden, in elk schrift.
    "zoekcontrole:zoekvraag": {GELDIG},
    # #32.29d: het citaat en de pagina worden in elk schrift op dezelfde manier vlak gemaakt
    "eigenscore:_vlak": {GELDIG, BEHOUDT_LETTERS},
    # #32.39: het citaat van Haiku en het artikel worden in elk schrift op dezelfde manier vlak gemaakt
    "werkwijze:_vlak": {GELDIG, BEHOUDT_LETTERS},
    # #32.41: de zoekvragen vooraf van Haiku, in elk schrift streng gelezen
    "speurvraag:lees": {GELDIG},
    # #32.42: de tekst van een bericht per taal ingekort, in elk schrift
    "talenset:_kort": {GELDIG},
    "talenset:artigo_wikinews": {GELDIG},
    "zoekcontrole:kop_gewoon": {BEHOUDT_LETTERS, GELDIG},
    "duel:_kaal": {NOOIT_LEEG, BEHOUDT_LETTERS, GELDIG},
    "duel:_zonder_koppen": {GELDIG},
    "zoekcontrole:zonder_database": {GELDIG},
    "zoekcontrole:zinnen": {GELDIG},
    "zoekcontrole:_kop_woorden": {GELDIG},
    "zoekcontrole:_nummer_voor_de_punt": {GELDIG, BEHOUDT_LETTERS},
    "zoekcontrole:_getallen": {GELDIG},
    "bronnen:_rsf": {GELDIG},
    "uitlegdekking:zinnen": {GELDIG},
    "netwerken:hosts_in": {GELDIG},
    "netwerken:host_van": {GELDIG},
    "merkinbeeld:medium": {GELDIG},
    "duel:gemini_verzoek": {GELDIG},
    # Haalt stempelregels uit OCR-tekst in elk schrift (#25.12).
    "artikelbeelden:schoon_ocr": {GELDIG},
    "notesmeting:schoon": {NOOIT_LEEG, BEHOUDT_LETTERS, ONDERSCHEIDT},
    # Sjablonen en markup uit Wikinews en Wikipedia, voor de leerstof (#31.3).
    "leerstof:schoon": {NOOIT_LEEG, BEHOUDT_LETTERS, ONDERSCHEIDT},
    # Een kop is een ware zin in claimstijl als hij geen vraag is, in elk schrift (#31.3).
    "leerstof:is_kop": {GELDIG},
    # De knipregel van de stiltetoets telt letters én combinerende tekens,
    # anders viel Hindi weg (#28.6 g); de eigen test toetst dat op Devanagari.
    "stiltetoets:knip": {GELDIG},
    # Wikitekst van de Engelse Wikipedia naar leesbare tekst, en in zinnen
    # (#30.1b); de zinsknip zoekt een hoofdletter, dus een tekst zonder
    # hoofdletters blijft één zin, wat de minimale paren alleen strenger maakt.
    "minimaleparen:schoon": {GELDIG},
    "minimaleparen:zinnen": {GELDIG},
    # Telt woorden voor het filter op toevoegingen in de rechterset (#30.3);
    # zonder spaties is de zin één woord, en dan valt er alleen niets weg.
    "rechterset:_woorden": {GELDIG},
    # Boven- en onderschrift van een meme: zonder spatie (Chinees, Japans)
    # gewoon in het midden; de eigen test toetst dat (#26.3).
    "beeldstilte:splits": {GELDIG},
    # Zet alleen twee URL's om; de tekst van de pagina blijft in elk schrift
    # letter voor letter staan (de previewserver van de site).
    "stiltetoets:_letteraandeel": {GELDIG},
    # Opknippen vóór de controlestap (B43): knippen mag regels laten vallen
    # (de chatomgeving), maskeren alleen telefoonnummers, adressen en handles;
    # de letters van de bewering blijven in elk schrift staan (#31.10).
    "opknippen:maskeer": {NOOIT_LEEG, BEHOUDT_LETTERS, ONDERSCHEIDT},
    "opknippen:knip": {GELDIG},
    "opknippen:opknippen": {GELDIG},
    "opknippen:_woorden": {GELDIG},
    "opknippen:_is_omgeving": {GELDIG},
    # De routemeting (#31.10): letters tellen met combinerende tekens, en de
    # stempelregel die alleen over de selectie van Engelse M4FC-beelden gaat.
    "routemeting:letters": {GELDIG},
    "routemeting:soort_van": {GELDIG},
    "routemeting:verraadt": {GELDIG},
    "routemeting:_cijfers": {GELDIG},
    # De toets voor de beta (#31.14): een artikel wordt kop en eerste zinnen, en
    # er blijft altijd iets over; `batch_id` maakt van onze eigen (ASCII-)ids een
    # sleutel voor de Batch API en hoeft andere schriften niet te onderscheiden.
    "betatoets:artikelbericht": {NOOIT_LEEG, GELDIG},
    "betatoets:batch_id": {NOOIT_LEEG, GELDIG},
    # Herkent de omschrijving door een factchecker ("Claim: ...", "Says ..."); stikt in geen schrift (#31.15).
    "herstel:omschrijving": {GELDIG},
    "taal:corpus_taal": {GELDIG},
    # Een vraag als bewering (#25.36): een bewering blijft zoals ze is, en er
    # blijft nooit niets over.
    "vraagvorm:als_bewering": {NOOIT_LEEG, ONDERSCHEIDT, GELDIG},
    # Een artikel in eenheden (#30.11): een breed teken telt voor drie, zodat
    # een korte Chinese zin meetelt; de eigen test toetst dat.
    "zinnen:zinnen": {NOOIT_LEEG, GELDIG},
    "zinnen:eenheden": {NOOIT_LEEG, GELDIG},
    "zinnen:_lengte": {GELDIG},
    "vraagvorm:_zonder_vraagwoord": {GELDIG},
    "vraagvorm:is_vraag": {GELDIG},
    "vraagvarianten:als_bewering_claim": {NOOIT_LEEG, ONDERSCHEIDT, GELDIG},
    "taal:detecteer_taal": {GELDIG},
    "relation:extract_numbers": {GELDIG},
    "relation:extract_negation_tokens": {GELDIG},
    "relation:extract_negations": {GELDIG},
    "relation:extract_number_contexts": {GELDIG},
    "relation:_canoniek_getal": {GELDIG},
    "source:observe_sources": {GELDIG},
    "ingest:_is_kale_url": {GELDIG},
    "ingest:is_geen_bewering": {GELDIG},
    # Leest paginatekst in elk schrift (de 21.3-proefset is nl/en/es, de
    # volgende kan Tamil zijn); mag niet struikelen (#25.14d).
    "screeningmeting:alineatekst": {GELDIG},
    "testset:_bevat_negatie": {GELDIG},
    "testset:_zonder_woordspaties": {GELDIG},
    "uitgeverkwaliteit:is_geweerd": {GELDIG},
    "ocr:_opschonen": {GELDIG, BEHOUDT_LETTERS},
    # De zinsplitser van de batchcontrole (#21.2): zinnen eindigen niet overal
    # op een punt, en geen schrift mag tot nul zinnen verdampen.
    "controle:_zinnen": {GELDIG, NOOIT_LEEG},
    # Vraagvorm-detectie (#21.5): vraagtekens verschillen per schrift, en een
    # gemiste vraagvorm mag hoogstens een vlag te veel kosten, nooit een crash.
    "controle:_is_vraagvorm": {GELDIG},
    # Lettertypedekking (#18.3). Deze drie beantwoorden juist de vraag "kan dit
    # schrift wel getekend worden", dus ze moeten voor élk schrift een antwoord
    # geven — ook voor de schriften waarvoor het antwoord nee is.
    "benchmark_images:kan_renderen": {GELDIG},
    "benchmark_images:_lettertype_voor": {GELDIG},
    "benchmark_images:_proeftekens": {GELDIG},
    # Testsettransformaties: dit is de §17a-klasse. Een vorm die de tekst
    # ongemoeid laat, levert een artefact dat gelijk is aan zijn claim.
    "testset:_truncation_variant": {GELDIG, VERANDERT},
    "testset:_digit_swap_variant": {GELDIG, VERANDERT},
}

BUITEN_BESCHOUWING: dict[str, str] = {
    "publiceren:_kolommen": "maakt kolomnamen uit een vaste veldnaam en de lijst van sitetalen (#34.2be), geen mensentekst",
    "bronnen:_tsv": "neemt de inhoud van een tsv-bestand uit data/bronnen/extern en geeft rijen; de schriftvraag zit bij wie de velden leest",
    "eigenscore:_site": "neemt een adres en geeft de host, geen mensentekst",
    "wereldlijst:_host": "neemt de link van een check en geeft de host, geen mensentekst",
    "wereldlijst:_datum_nl": "neemt een datum als JJJJ-MM-DD en geeft dag, maand en jaar, geen mensentekst",
    "wereldlijst:_woorden": "neemt een sleutel in kleine letters met streepjes (ASCII, `_SLEUTEL`) en geeft de woorden, geen mensentekst",
    "wereldlijst:venster": "neemt een datum als JJJJ-MM-DD en geeft de week, geen mensentekst",
    "wereldlijst:ronde": "neemt een datum en schrijft de opdrachten van de week, geen mensentekst",
    "wereldlijst:voorstellen": "neemt een datum en leest de voorstellen van de week, geen mensentekst",
    "wereldlijst:nakijken": "neemt een datum en legt de voorstellen langs `controleer`, geen mensentekst",
    "wereldlijst:pagina": "neemt een datum en schrijft de keuzepagina, geen mensentekst",
    "wereldlijst:vul_schalen": "neemt een datum en zet de schaal uit `verdicts`, geen mensentekst",
    "reikwijdte:_kant": "neemt een label uit een vaste lijst (internationaal, lokaal, ...) en zegt of het vertaald wordt, geen mensentekst",
    "zelfdebewering:versie_van": "neemt de naam van een model (haiku, sonnet) en geeft de naam van de vraag, geen mensentekst",
    "uitrol:_druk": "drukt de uitvoer van wrangler af zonder regels met het account, geen tekst uit het wild",
    "uitrol:_haal": "neemt een adres van factiz.org en haalt de pagina op, geen mensentekst",
    "uitrol:akkoord": "leest de vaste vorm van een akkoord van de PO (datum, PO, citaat), geen tekst uit het wild",
    "radarvoormeting:_datum": "zet milliseconden uit de export van X (cijfers) om in een datum, geen mensentekst",
    "redactie:_mens": "leest de naam van een auteur of nalezer die de redactie zelf invult, alleen om Claude te herkennen",
    "radarlijst:_datum": "zet milliseconden uit de export van X (cijfers) om in een datum, geen mensentekst",
    "radarlijst:_host": "neemt een adres uit een note en geeft de host, geen mensentekst",
    "radarlijst:bronnen": "geeft de hosts van de adressen in een note; de tekst eromheen telt niet",
    "radarlijst:in_het_nederlands": "beslist alleen of een note Nederlands is: een ander schrift is nooit Nederlands en valt af, zo bedoeld",
    "radarlijst:geen_bewering": "zoekt Nederlandse en Engelse woorden voor een kopie, bot of parodie; in een ander schrift vindt ze niets en blijft de note een bewering, zo bedoeld (B85)",
    "radarlijst:_sleutel": "zet een schrijfwijze uit het namenregister om in woorden met een spatie; een schrift zonder spaties gaat via bekende_namen als tekenreeks, zo bedoeld (B85)",
    "radarlijst:taal_van": "geeft alleen de taal van een note via py3langid; elk schrift mag, en een taal buiten de sitetalen of een te korte note geeft None, zo bedoeld (B85)",
    "radarlijst:_kort": "kort een note af op een spatie voor de lijst van de PO; zonder spaties (Chinees, Japans) op het aantal tekens, zo bedoeld (B85)",
    "verversen:laatste_bijwerking": "leest de eigen regels van data/vooruitblik/ophalen.log (tijd, stand van de feed, uitgang), geen mensentekst",
    "verversen:lab_bezig": "leest de eigen regels van data/vooruitblik/ophalen.log, geen mensentekst",
    "verversen:_laatste_regel": "neemt de laatste regel van de uitvoer van een eigen stap voor de stand, geen tekst uit het wild",
    "verversen:_melding_mac": "toont een eigen melding van de routine op de Mac, geen tekst uit het wild",
    "uitrol:lees_database": "leest de binding DB uit site/wrangler.jsonc, een eigen bestand",
    "uitrol:versie_uit": "leest de versie uit de uitvoer van wrangler",
    "uitrol:voorbereiden": "neemt de naam van een uitgave (2026-11-16b), geen mensentekst",
    "waarom:_lezing_proef": "neemt een modelnaam (haiku, sonnet), geen mensentekst",
    "waarom:leesproef_punten": "leest het eigen leesbestand van `lezen` op zijn vaste kopjes (=== en [n]); de punten gaan woord voor woord door",
    "eigenscore:_sites": "neemt de naam van een set (ijk), geen mensentekst",
    "eigenscore:_ophalen": "neemt de naam van een set en haalt pagina's op (netwerk)",
    "eigenscore:_indienen": "neemt de naam van een set en dient een batch in (netwerk)",
    "benchmark_images:renderversie": (
        "neemt een hashversie, geen mensentekst; de schriftvraag zit in"
        " kan_renderen"
    ),
    "api:_ruim_op": "neemt een bestandspad en opent er een database mee",
    "api:beeld": "neemt de naam van een veld van de site (uit het pad), geen mensentekst",
    "cijfers:_conformantieblok": "neemt een bestandspad en leest er JSON uit",
    "bootstrap:_feedgrootte": "neemt een URL en doet een netwerkverzoek",
    "embedding:_model_naam": "neemt een modelversie, geen mensentekst",
    "embedding:_modelspec": "neemt een modelversie, geen mensentekst",
    "search:_identiteit": "neemt een bestandspad en leest er de inode van",
    "search:_wachterstand": "neemt een bestandspad en opent er een database mee",
    "varianten:doeltalen": "neemt een taalcode, geen mensentekst",
    "velden:_rgb": "neemt een kleurcode (#rrggbb), geen mensentekst",
    "velden:teken": "neemt de naam van een veld van de site, geen mensentekst",
    "velden:dossier_seed": "neemt de sleutel van een dossier (de naam van zijn map, a-z en streepjes), geen mensentekst (#33.6d)",
    "zeef:helft": "neemt een sleutel (set en id), geen mensentekst",
    "zeef:uitkomst_p1": "neemt een uitkomstwoord van de terugkijktoets, geen mensentekst",
    "zeef:uitkomst_resolver": "neemt een uitkomstwoord van ruwetest.beoordeel, geen mensentekst",
    "zeef:tellen": "neemt een versienaam en leest er een uitvoermap mee",
    "minimaleparen:regels_uit_diff": "neemt de HTML van een vergelijking van MediaWiki, geen mensentekst",
    "minimaleparen:_cel": "neemt een HTML-cel uit een vergelijking van MediaWiki, geen mensentekst",
    "rechtermeting:scoren": "neemt de naam van een kandidaat-rechter, geen mensentekst",
    "rechtermeting:deel": "neemt een zaaksleutel (claim-id of feit), geen mensentekst",
    "rechtermeting:_motor": "neemt de naam van een kandidaat-rechter, geen mensentekst",
    "rechtermeting:_motor_van_zeef": "neemt de naam van een zeefversie, geen mensentekst",
    "artikellezer:label_uit": "leest het JSON-antwoord van Haiku, geen mensentekst",
    "rechtermeting:_kernachtig_lezen": "neemt de naam van een zeefversie, geen mensentekst",
    "rechtertraining:doel": "neemt een label uit een vaste lijst, geen mensentekst",
    "rechterlabels:mens_zelfde": "neemt een label uit een vaste lijst, geen mensentekst",
    "rechterlabels:uitkomst": "neemt het JSON-antwoord van Haiku; de teksten van het paar staan er niet in",
    "rechterlabels:verzamelen": "neemt een databasepad",
    "rechterset:label_veto": "neemt een leeslabel uit een vaste lijst, geen mensentekst",
    "rechterset:label_minimaal_paar": "neemt een leeslabel uit een vaste lijst, geen mensentekst",
    "variantenbatch:doeltalen": "neemt een taalcode, geen mensentekst",
    "uitgeverkwaliteit:is_geweerde_host": "neemt een URL; een host is per definitie ASCII-achtig",
    "netwerktoets:_host": "neemt een URL; een host is per definitie ASCII-achtig",
    "zoekcontrole:van_factiz": "neemt een URL; een host is per definitie ASCII-achtig",
    "artikelbeelden:_grootste_uit_srcset": "leest een srcset-attribuut: URL's met breedtes, geen mensentekst",
    "releaserapport:_conformantie": "neemt een bestandspad en leest er de conformantie-uitvoer uit",
    "beeldindex:_gelijk": "vergelijkt URL's van factcheckartikelen; een URL is per definitie ASCII-achtig",
    "beeldindexmeting:host": "neemt een URL; een host is per definitie ASCII-achtig",
    "eigenaanvoer:_datum": "neemt een datum uit een sitemap (ISO 8601), geen mensentekst",
    "eigenaanvoer:_kaal": "neemt een XML-tag met namespace, geen mensentekst",
    "eigenaanvoer:datum_uit_adres": "neemt een URL en leest er een datum uit; geen mensentekst",
    "eigenaanvoer:in_venster": "neemt een datum (ISO 8601), geen mensentekst",
    "eigenaanvoer:sitemap": "neemt een sitemap (XML met adressen en datums); de adressen gaan ongewijzigd door",
    "vindronde:_puntpad": "maakt een bestandsnaam uit een hash van een set en id's; geen mensentekst",
    "opmaakmeting:site": "neemt een URL; een host is per definitie ASCII-achtig",
    "opmaakmeting:_sha": "maakt een hash van een adres voor een vaste volgorde; geen mensentekst",
    "opmaakmeting:_beeldpad": "maakt een bestandsnaam uit een hash van een beeldadres; geen mensentekst",
    "opmaakmeting:_maskerpad": "maakt een bestandsnaam uit een hash van een beeldadres; geen mensentekst",
    "opmaakmeting:_kies": "kiest een van drie vaste meetsets op naam; geen mensentekst",
    "beeldindexmeting:sleutel_imgflip": "neemt het adres van een sjabloon van imgflip; geeft de bestandsnaam terug",
    "beeldindexmeting:_vragen": "neemt de naam van een meetset (R2, S1 tot S4), geen mensentekst",
    "beeldvraag:vector_uit_tekst": "neemt een vector in base64, geen mensentekst",
    "beeldcontrole:_adres": "vergelijkt URL's van factcheckartikelen; een URL is per definitie ASCII-achtig",
    "releaserapport:_huidige_kaart": (
        "knipt de releasekaart uit ons eigen RELEASES.md op een vaste kop; geen"
        " artefacttekst, en de inhoud gaat ongewijzigd door"
    ),
    "clientschema:int8_modellen": "neemt een modelversie en laadt er modellen mee, geen mensentekst",
    "datums:geldige_review_datum": (
        "neemt een datumveld uit ClaimReview, geen mensentekst; elk schrift"
        " levert terecht de lege string"
    ),
    "evidence:_host": "leest een URL; een URL is per definitie ASCII-achtig",
    "euvsdisinfo:_iso_datum": "neemt een datumveld, geen mensentekst",
    "euvsdisinfo:_volledige_url": "leest een URL; een URL is per definitie ASCII-achtig",
    "euvsdisinfo:_outlet": "leest een URL en geeft haar host; een host is per definitie ASCII-achtig",
    "euvsdisinfo:_splits_outlets": (
        "splitst een veldlijst op scheidingstekens en geeft een lijst terug;"
        " per element blijft het schrift onaangeroerd"
    ),
    "stiltetoets:_bestanden": "neemt een revisiehash van een dataset, geen mensentekst",
    "soortlezer:groep": "neemt een vaste Engelse sleutel van de soort uit het antwoordschema (#34.2aj), geen mensentekst",
    "cijfers:_taalvolgorde": "neemt een taalcode uit de benchmark (nl, crosslinguaal), geen mensentekst",
    "stancemeting:scorer": "neemt een modelnaam met revisie, geen mensentekst",
    "stancemeting:_snapshot": "neemt een modelnaam met revisie, geen mensentekst",
    "euvsdisinfo:_soort": (
        "vergelijkt een outletnaam met een vaste lijst platformnamen (#25.25);"
        " een naam in elk ander schrift is geen van die platforms en blijft terecht een outlet"
    ),
    "controle:_url_sleutel": "leest een URL; een URL is per definitie ASCII-achtig",
    "linkrot:_segmenten": "leest een URL-pad; een pad is per definitie ASCII-achtig",
    "bonnetjes:sleutel": "leest een URL van een factcheck; een URL is per definitie ASCII-achtig",
    "sheffield:dom": "leest een domeinnaam uit de Sheffield-set; een host is per definitie ASCII-achtig",
    "sheffield:ontproxy": "leest een URL; een URL is per definitie ASCII-achtig",
    "sheffield:_iso": "neemt een datumveld, geen mensentekst",
    "lezerb:_n1_stukken": "neemt een deelnaam (les of keuze), geen mensentekst",
    "lezerb:_client": "neemt een configpad, geen mensentekst",
    "bewering:_zinnen": "neemt een vraagversie (v1 of v2), geen mensentekst",
    "basisset:_gelijk": "vergelijkt URL's; een URL is per definitie ASCII-achtig",
    "basisset:label_van_kant": "neemt een kant (rood, midden, groen), geen mensentekst",
    "leraar:lees_oordeel": "leest het JSON-antwoord van het model; de reden gaat ongewijzigd door, alleen witruimte samengevoegd",
    "leraar:oordelen": "neemt een modelnaam (haiku, sonnet, opus), geen mensentekst",
    "echtnieuws:_inleiding": "pakt de eerste niet-lege regel; splitst alleen op regeleinden, in elk schrift gelijk",
    "leerstof:label_leerling": "neemt een label (onwaar, waar, neutraal), geen mensentekst",
    "leerstof:taalcode": "neemt een taalnaam of -code uit een bron, geen mensentekst",
    "leerstof:lees_paar": "leest het JSON-antwoord van het model; de zin gaat ongewijzigd door, alleen witruimte samengevoegd",
    "beeldzoeken:lees_kaal": "leest het JSON-antwoord van het model (waar of onwaar); geen tekst uit het wild",
    "beeldzoeken:_host": "een adres naar zijn host; het schrift van de pagina doet er niet toe",
    "beeldzoeken:lees_vorm": "leest het JSON-antwoord van het model (kaal en stempel); geen tekst uit het wild",
    "berichtcontrole:lees_vorm": "leest het JSON-antwoord van de vormvraag (vorm en beeld); geen tekst uit het wild",
    "herstel:_waarom": "leest de reden uit het JSON-antwoord van de vormvraag; de zin gaat ongewijzigd door",
    "gebruikerstoets:domein": "leest een URL; een URL is per definitie ASCII-achtig",
    "gebruikerstoets:lees_kaal": "leest de laatste regel VERDICT van het kale model, een vast Engels woord; geen tekst uit het wild",
    "beweringvraag:lees_extractie": "leest het JSON-antwoord van het model met vaste sleutels; de inhoud gaat ongewijzigd naar het zoeken",
    "vloervraag:lees_oordeel": "leest het JSON-antwoord van het model met een vaste keuze uit twee Engelse waarden; de tekst van het bericht komt er niet in",
    "bronnenlijst:host": "leest een URL naar zijn host; een host is ASCII of punycode, het schrift van de pagina doet er niet toe",
    "bronnenlijst:officieel": "leest de naam van een domein (ASCII of punycode) en kijkt alleen naar de laatste delen",
    "bronnen:_domein": "leest de naam van een website (ASCII of punycode) en kijkt alleen naar de laatste delen (#32.66)",
    "bronnen:reden": "haalt alleen ons eigen voorvoegsel \"verhuisd van ...: \" weg van een reden die wij schrijven (#32.66)",
    "merkbeelden:paden": "leest de vormen uit een SVG-pad van ons eigen logo (opdrachten en getallen), geen tekst in een schrift (#23.18)",
    "bronnenlijst:lin_oordelen": "leest het CSV-bestand van Lin e.a. met domeinnamen en een getal; geen tekst uit het wild",
    "bronnenlijst:lin_cijfers": "leest het CSV-bestand van Lin e.a. met domeinnamen en een getal; geen tekst uit het wild",    "bronnenlijst:wikipedia_oordelen": "leest de wikitekst van de lijst van Wikipedia met vaste sjablonen; geen tekst uit het wild",
    "bronnenlijst:rsf_scores": "leest het CSV-bestand van RSF met landcodes en scores; geen tekst uit het wild",
    "bronnenlijst:_bouw_uit_extern": "het argument is een datum; leest de gedownloade lijsten uit bestanden",
    "kruiscontrole:eigenaar": "het argument is de naam van een website (ASCII of punycode); kijkt alleen naar de laatste delen",
    "herkomst:antwoorden_van": "het argument is de naam van een versie van de vraag; leest de antwoorden uit een bestand",
    "herkomst:p11": "het argument is de naam van een helft (ontwikkel of toets); leest de set uit een bestand",
    "herkomst:stukken": "het argument is de naam van een set (ontwikkel of toets); leest de berichten uit bestanden",
    "koppen:_site": "het argument is een URL; geeft alleen de host terug",
    "uitkomsten:vingerafdruk": "neemt de naam van een lezer uit een vaste lijst in de code, nooit tekst van een bericht",
    "duelrechter:lees": "leest het JSON-antwoord van een beoordelaar met een vaste keuze (A, B, beide, geen, weet niet; A, B, gelijk); de zin waarom gaat ongewijzigd door; de tekst van het bericht komt er niet in",
    "zoekcontrole:lees_oordeel": "leest het JSON-antwoord van het model met een vaste keuze uit zeven oordelen en een ja of nee voor een beeld; de twee zinnen van v4 (het feit, wat er echt gebeurde) en de foute woorden en de juiste waarde van v6 gaan ongewijzigd door, alleen de witruimte aan de randen eraf; van v5 alleen de nummers van de checks met een gewoon ja; de vorm van v6 alleen bij precies *over een bewering*; de tekst van het bericht komt er niet in",
    "api:_warm_op": "het argument is het pad van de database; laadt alleen het model met een vaste zin en een claim uit de index",
    "staatsmedia:_host": "het argument is een URL of domein; geeft alleen de host terug",
    "vooruitblik:nieuwe_versie": "het argument is het versiekenmerk (ETag) van de feed; vergelijkt alleen gelijkheid",
    "vooruitblik:onthoud_versie": "het argument is het versiekenmerk (ETag) van de feed; schrijft het alleen weg",
    "koppen:_wikitekst": "het argument is de titel van een Wikipedia-pagina; haalt alleen de wikitekst op (netwerk)",
    "koppen:gdelt_woorden": "het argument is een URL; de woorden uit het pad zijn ASCII, en zonder streepjes geen zoekvraag",
    "vloerronde:rijen_van": "het argument is de naam van een set (O of R3), geen tekst; leest de antwoorden uit bestanden",
    "modelpoort:_bron_antwoorden": "het argument is de naam van een eerdere toets (een map), geen tekst; leest de feitenstap van toen uit een bestand",
    "echtevorm:lees_herschrijving": "leest het JSON-antwoord van Haiku met één vaste sleutel; de tekst gaat ongewijzigd door",
    "plafond:_beeld": "krijgt een bestandspad en leest een beeld; geen tekst",
    "berichtcontrole:lees_notitie": "leest het JSON-antwoord op de detailvraag met vaste sleutels; de woorden gaan ongewijzigd naar de zoekstap",
    "berichtcontrole:lees_detail": "leest het JSON-antwoord op de detailvraag met vaste sleutels; de woorden gaan ongewijzigd naar de controle",
    "talen:lees_omzetting": "leest het JSON-antwoord van Haiku met een vaste lijst Nederlandse categorieën; geen tekst uit het wild",
    "terugaanvoer:lees_oordeel": "leest het JSON-antwoord van Haiku met een vaste lijst Nederlandse categorieën; geen tekst uit het wild",
    "terugaanvoer:_host": "de naam van een site uit de eigen lijst (Snopes, Full Fact), geen tekst uit het wild",
    "terugaanvoer:artikel": "het adres van een factcheckartikel uit een sitemap of de database, een URL en geen tekst uit het wild",
    "omgedraaid:lees_soort": "leest het JSON-antwoord van Haiku met een vaste lijst van drie soorten; geen tekst uit het wild",
    "omgedraaid:_paden": "de naam van een ronde uit de vaste lijst (route-a, publicatie), geen tekst uit het wild",
    "beeldpaar:_host": "neemt een URL; een host is per definitie ASCII-achtig",
    "radar:_bits": "neemt een PDQ-hash in hexadecimale tekens, geen tekst uit het wild",
    "radar:post_id": "neemt het adres van een post (at://...), geen tekst uit het wild",
    "radar:lees_soort": "leest het JSON-antwoord van een model met vaste woorden; het onderwerp gaat alleen naar mij om te lezen",
    "beeldpaar:lees_paar": "leest het JSON-antwoord van een model met vaste woorden; de vrije zinnen gaan alleen naar mij om te lezen",
    "publiceren:nummer": "het nummer van een bewering uit de eigen database (gfc-…), geen tekst uit het wild; al het andere wordt een hash",
    "publiceren:richting": "een taalcode (ar, en), geen tekst uit het wild",
    "publiceren:_prefix": "de herkomst van een check uit de eigen database (datacommons-ccby, euvsdisinfo:…), geen tekst uit het wild",
    "d1uitgave:_naam": "zet een tabelnaam uit het schema van de uitgave tussen aanhalingstekens voor SQL, geen tekst uit het wild",
    "d1uitgave:d1_vraag": "de naam van een database in D1 (factiz-<release>), geen tekst uit het wild",
    "themas:lees_verkenning": "leest het JSON-antwoord van Haiku met een vaste lijst van velden; het onderwerp is een Engelse zin van het model en gaat alleen naar mij om te lezen",
    "dossier:lees_verhaal": "leest het JSON-antwoord van Haiku; de Engelse zin van het model gaat ongewijzigd door, alleen witruimte samengevoegd",
    "dossier:_kiezen": "een themanaam uit `dossier.THEMAS`, geen tekst uit het wild",
    "taallabels:_site": "een webadres van een check, geen tekst van een bewering: alleen de hostnaam in kleine letters",
    "weergave:doelen": "een taalcode uit de uitgave, geen tekst van een bewering",
    "weergave:maker": "een doeltaal van de site (`nl`, `en`), geen tekst van een bewering",
    "weergave:_controle_indienen": "de naam van een versie van de controlevraag (`controle-v1`), geen tekst uit het wild",
    "weergave:vraagt_tweede": "de naam van een versie van de controlevraag (`controle-v3`), geen tekst uit het wild",
    "dossier:_uitgegeven": "een themanaam uit `dossier.THEMAS`, geen tekst uit het wild",
    "dossiers:_lezing_pad": "de sleutel van een dossier (de naam van een map in `content/dossiers/`), geen tekst uit het wild",
    "dossiers:_lezing": "de sleutel van een dossier (de naam van een map in `content/dossiers/`), geen tekst uit het wild",
    "dossiers:_voorstellen": "de sleutel van een dossier (de naam van een map in `content/dossiers/`), geen tekst uit het wild",
    "latset:_kandidaten": "een taalcode uit `latset.REDACTIES` (es), geen tekst uit het wild",
    "latset:_lezen": "een taalcode uit `latset.REDACTIES` (es), geen tekst uit het wild",
    "latset:_oud": "een taalcode uit `latset.REDACTIES` (es), geen tekst uit het wild",
    "latset:_teksten": "een taalcode uit `latset.REDACTIES` (es), geen tekst uit het wild",
    "latset:_uitgegeven": "een taalcode uit `latset.REDACTIES` (es), geen tekst uit het wild",
    "latset:_vast": "een taalcode uit `latset.REDACTIES` (es), geen tekst uit het wild",
    "latset:map_voor": "een taalcode uit `latset.REDACTIES` (es), geen tekst uit het wild",
    "latset:lees_doorsturen": "leest het JSON-antwoord van Haiku: een ja of nee en een zin die alleen naar mij gaat om te lezen; geen tekst uit het wild",
    "terugaanvoer:custom_id": "een id van hexadecimale tekens, geen tekst uit het wild",
    "terugaanvoer:kant": "een categorie uit de vaste set van zeven, geen tekst uit het wild",
    "terugaanvoer:_nakijken": "de naam van een stap (sets, lezen, pagina, tellen), geen tekst uit het wild",
    "werkwijze:_host": "een adres naar zijn host; het schrift van de pagina doet er niet toe",
    "zoekvragen:kop_uit_adres": "een adres van EUvsDisinfo naar de kop in het pad; dat pad is altijd ASCII",
    "speuren:_feeds": "een datum (JJJJ-MM-DD), geen tekst uit het wild",
    "meting:lees_plan": "een pad naar een meetplan, geen tekst uit het wild",
    "talenset:_bouwen": "een taalcode uit de vaste lijst (es, pt, de), geen tekst uit het wild",
    "talenset:_checks": "een taalcode uit de vaste lijst (es, pt, de), geen tekst uit het wild",
    "talenset:_herstellen": "een taalcode uit de vaste lijst (es, pt, de), geen tekst uit het wild",
    "talenset:_vers": "een taalcode uit de vaste lijst (en, es, pt, de), geen tekst uit het wild",
    "talenset:_datum": "een taalcode uit de vaste lijst (en, es, pt, de), geen tekst uit het wild",
    "talenset:_beeld": "een taalcode uit de vaste lijst (es, pt, de, nl, fr), geen tekst uit het wild",
    "talenset:_waar": "een taalcode uit de vaste lijst (pt), geen tekst uit het wild",
    "talenset:_vers_beeld": "een taalcode uit de vaste lijst (en), geen tekst uit het wild",
    "meting:fotobestand": "een versienaam uit de vaste lijst, geen tekst uit het wild",
    "meting:beeld_bytes": "een pad of adres van een beeld, geen tekst uit het wild",
    "meting:_adres": "een adres van een webpagina, vergeleken op host en pad; geen tekst uit het wild",
    "poproef:_nieuws": "de naam van een ronde (een datum), geen tekst uit het wild",
    "duel:_set": "de naam van een ronde (een datum), geen tekst uit het wild",
    "consensus:venster": "een datum uit een meetset (ISO), geen tekst uit het wild",
    "netwerken:_naam": "een domeinnaam die `host_van` of de lijst al gaf, geen tekst uit het wild",
    "merkinbeeld:lees": "het JSON-antwoord van Haiku met een vast schema, geen tekst uit het wild",
    "talenset:gebruikte_paden": "een taalcode van V1 (en, es, pt, de), geen tekst uit het wild",
    "talenset:vers_pad": "een taalcode van V1 (en, es, pt, de), geen tekst uit het wild",
    "talen:omzetting_pad": "een taalcode (de, nl, fr), geen tekst uit het wild",
    "talen:batches_pad": "een taalcode (de, nl, fr), geen tekst uit het wild",
    "meting:model_naam": "een model-id uit de eigen lijst, geen tekst uit het wild",
    "uitlegdekking:_paden": "de naam van een meetplan, geen tekst uit het wild",
    "uitlegdekking:_lezen": "de naam van een meetplan, geen tekst uit het wild",
    "uitlegdekking:_tellen": "de naam van een meetplan, geen tekst uit het wild",
    "duel:_site": "een adres van een webpagina, alleen de host; geen tekst uit het wild",
    "zoekcontrole:_domein": "een adres of domein van het model naar de kale domeinnaam; het schrift van de pagina doet er niet toe",
    "werkwijze:m4fc_methoden": "de strategieën uit M4FC, een vaste Engelse lijst met puntkomma's, geen tekst uit het wild",
    "feitstap:stand_van": "een vaste richting van het model (bevestigt, spreekt tegen, geen), geen tekst uit het wild",
    "feitstap:uit_verzoek_id": "splitst een verzoek-id in stuk-id en sleutel (A of B), geen tekst uit het wild",
    "beeldzoeken:_vorm": "de naam van een stap (indienen, ophalen), geen tekst uit het wild",
    "verificatie:met_beeldzoeken": "de naam van een run (b, bR, aR), geen tekst uit het wild",
    "machinevraag:zonder_factchecks_aan": "de naam van een run (b, bR, aR), geen tekst uit het wild",
    "machinevraag:lees_antwoord": "leest de laatste regels OORDEEL, BEWERING en UITLEG van het model; de tekst gaat ongewijzigd door, alleen opmaaktekens aan de randen weg",
    "onderwerp:lees_antwoord": "leest het JSON-antwoord van het model; de zoekwoorden gaan ongewijzigd door, alleen witruimte en aanhalingstekens weg",
    "onderwerp:_helft": "een sleutel (taal en pagina-id) naar de vaste helft; de hash ziet alleen bytes",
    "leerstof:stijl_van": "neemt een soortnaam (artikel, nieuws, webtekst, ...), geen mensentekst",
    "echtnieuws:lees": "neemt een bronnaam (wikinews, wikipedia), geen mensentekst",
    "echtnieuws:wikinews_ophalen": "neemt een taalcode, geen mensentekst",
    "echtnieuws:wikipedia_ophalen": "neemt een taalcode, geen mensentekst",
    "bewering:kandidaten_zoeken": "neemt een vraagversie (v1 of v2), geen mensentekst",
    "bewering:lees_antwoord": (
        "leest het JSON-antwoord van het model (#30.12); de zin gaat ongewijzigd door, alleen witruimte"
        " wordt samengevoegd, en str.split kent de witruimte van elk schrift"
    ),
    "sheffield:lees": (
        "leest titel en beschrijving uit HTML-metatags en de alineatekst via"
        " screeningmeting.alineatekst (die zijn eigen contract heeft); de inhoud gaat"
        " ongewijzigd door, alleen witruimte en entiteiten worden opgeschoond"
    ),
    "bonnetjes:_stempel": "neemt een ISO-tijdstip, geen mensentekst",
    "bonnetjes:_dag": "neemt een ISO-tijdstip, geen mensentekst",
    "ask:tiplijnen": "neemt een taalcode, geen mensentekst",
    "cijfers:_moment": "neemt een ISO-tijdstip, geen mensentekst",
    "natuurlijk:post_sleutel": "leest een URL; een URL is per definitie ASCII-achtig",
    "communitynotes:host_en_pad": "leest een URL; een URL is per definitie ASCII-achtig",
    "ruwetest:lees_meta": "leest HTML-metatags uit een webpagina, geen claimtekst; de inhoud gaat ongewijzigd door",
    "benchmark_images:render_claim": (
        "tekent tekst in een afbeelding. Schriftgevoelig — een ontbrekende glief"
        " levert blokjes — maar dat is een lettertypevraag en geen tekenreeks;"
        " zie 18.3"
    ),
}


def _letters(tekst: str) -> set[str]:
    return {
        teken for teken in tekst
        if unicodedata.category(teken)[0] in {"L", "M"}
    }


def _tekstfuncties() -> dict[str, object]:
    """Elke functie in het pakket met precies één verplicht `str`-argument."""
    gevonden: dict[str, object] = {}
    for info in pkgutil.walk_packages(doublecheck.__path__, prefix="doublecheck."):
        try:
            module = importlib.import_module(info.name)
        except Exception:  # pragma: no cover - een kapotte module valt elders om
            continue
        for naam, fn in vars(module).items():
            if not inspect.isfunction(fn) or fn.__module__ != module.__name__:
                continue
            try:
                sig = inspect.signature(fn)
            except (ValueError, TypeError):  # pragma: no cover
                continue
            verplicht = [
                p for p in sig.parameters.values()
                if p.default is inspect.Parameter.empty
                and p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)
            ]
            if len(verplicht) != 1:
                continue
            if verplicht[0].annotation not in ("str", "str | None", str):
                continue
            sleutel = f"{info.name.removeprefix('doublecheck.')}:{naam}"
            gevonden[sleutel] = fn
    return gevonden


def _haal(sleutel: str):
    module, naam = sleutel.split(":")
    return getattr(importlib.import_module(f"doublecheck.{module}"), naam)


# --- de volledigheidscontrole ----------------------------------------------


def test_every_text_function_declares_how_it_treats_script():
    """Wie een tekstfunctie toevoegt, schrijft haar schriftcontract op.

    Dit is het deel dat de guard levend houdt. Zonder deze test is het paneel
    een momentopname die stilletjes achterloopt op de code.
    """
    gevonden = _tekstfuncties()
    assert len(gevonden) >= 20, "de zoeker vindt de bestaande functies niet meer"
    onbesproken = sorted(
        set(gevonden) - set(CONTRACTEN) - set(BUITEN_BESCHOUWING)
    )
    assert onbesproken == [], (
        "tekstfunctie(s) zonder schriftcontract: " + ", ".join(onbesproken)
        + " — zet ze in CONTRACTEN, of in BUITEN_BESCHOUWING mét reden"
    )


def test_nothing_is_excluded_without_a_reason():
    leeg = [k for k, v in BUITEN_BESCHOUWING.items() if not v.strip()]
    assert leeg == [], f"uitzondering zonder reden: {leeg}"
    verdwenen = sorted(
        set(CONTRACTEN) | set(BUITEN_BESCHOUWING) - set(_tekstfuncties())
    )
    bestaat = set(_tekstfuncties())
    weg = sorted(k for k in set(CONTRACTEN) | set(BUITEN_BESCHOUWING) if k not in bestaat)
    assert weg == [], f"staat in de lijst maar bestaat niet meer: {weg}"


# --- de contracten zelf -----------------------------------------------------


def _met(contract: str):
    return sorted(k for k, v in CONTRACTEN.items() if contract in v)


@pytest.mark.parametrize("sleutel", _met(NOOIT_LEEG))
@pytest.mark.parametrize("schrift", sorted(PANEEL))
def test_no_script_is_reduced_to_nothing(sleutel, schrift):
    """`[a-z0-9]` maakte van elke Cyrillische naam de lege string (§48c)."""
    uit = _haal(sleutel)(PANEEL[schrift])
    assert uit, f"{sleutel} maakt {schrift} leeg"


@pytest.mark.parametrize("sleutel", _met(BEHOUDT_LETTERS))
@pytest.mark.parametrize("schrift", sorted(PANEEL))
def test_no_letter_or_combining_mark_is_dropped(sleutel, schrift):
    """`\\w` liet combinerende tekens vallen: `क्विंट हिंदी` → `कवटहद` (§50c)."""
    tekst = PANEEL[schrift]
    uit = _haal(sleutel)(tekst)
    # Beide kanten vouwen: sommige normalisatoren doen dat zelf, andere niet,
    # en het contract gaat over verdwenen tekens — niet over kast.
    kwijt = _letters(tekst.casefold()) - _letters(uit.casefold())
    assert not kwijt, (
        f"{sleutel} laat {len(kwijt)} teken(s) vallen in {schrift}: "
        + " ".join(f"{c!r}({unicodedata.category(c)})" for c in sorted(kwijt))
    )


@pytest.mark.parametrize("sleutel", _met(ONDERSCHEIDT))
def test_different_texts_stay_different(sleutel):
    """Twee namen die alleen in klinkertekens verschillen, blijven twee namen."""
    fn = _haal(sleutel)
    uitkomsten: dict[str, str] = {}
    for schrift, tekst in PANEEL.items():
        uit = fn(tekst)
        eerder = uitkomsten.get(uit)
        assert eerder is None, f"{sleutel} gooit {schrift} en {eerder} op één hoop"
        uitkomsten[uit] = schrift


@pytest.mark.parametrize("sleutel", _met(GELDIG))
@pytest.mark.parametrize("schrift", sorted(PANEEL))
def test_every_script_gets_an_answer(sleutel, schrift):
    _haal(sleutel)(PANEEL[schrift])


@pytest.mark.parametrize("sleutel", _met(VERANDERT))
@pytest.mark.parametrize("schrift", sorted(PANEEL))
def test_a_testset_transformation_never_returns_its_input(sleutel, schrift):
    """`.upper()` deed niets in het Arabisch, en dan meet het paar niets (§17a)."""
    tekst = PANEEL[schrift]
    uit = _haal(sleutel)(tekst)
    assert uit is None or uit != tekst, f"{sleutel} laat {schrift} ongemoeid"


def test_the_dressing_variant_changes_every_script():
    """`_dressing_variant` heeft twee argumenten en valt buiten de zoeker, maar
    hij ís de §17a-fout. Hier apart getoetst, in alle vier zijn vormen."""
    from doublecheck.testset import _dressing_variant

    for schrift, tekst in PANEEL.items():
        for keuze in range(4):
            assert _dressing_variant(tekst, keuze) != tekst, f"{schrift}/{keuze}"
