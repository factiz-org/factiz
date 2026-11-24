"""De marketingdemo (E5.S2 → #22.4; Engels sinds #22.7; merkschil #22.12).

Begonnen als kale testinterface; sinds 22.4 de pagina die akte 1 van de
launch draagt (B18), en sinds 22.12 de marketingdemo volgens DESIGN §4a:
de schil draagt het merk en nodigt uit (dropzone, plakken, voorbeeldchips,
levende statistiekregel), maar de uitslagkaart blijft de laboratoriumuitslag
met de bronnen als grootste element (D2), tellingen in plaats van scores
(D1/DR2), en een eigen rustige tekst voor elke staat, fouten incluis (D3/D7).

De chips in `CHIPS` zijn op het echte corpus gemeten als `matched`
(PLAN #22.12); een voorbeeld dat `none` geeft is een anti-demo. De
marketingsite mag alleen chips tonen die hier letterlijk in staan.

Geen externe assets, geen framework, geen netwerk buiten déze resolver —
dat is DR3: het artefact verlaat de eigen machine alleen richting de
resolver, en de preview van een gesleept of geplakt beeld is een lokale
object-URL die de pagina zelf weer intrekt.

XSS-discipline (#17.5, hier bewust herhaald): elke dynamische waarde loopt
door `ontsnap()` (textContent-gebaseerd), en een href ontstaat uitsluitend
via `bronLink()`, dat eerst op een http(s)-schema filtert — ontsnappen alleen
maakt een `javascript:`-URL niet onschadelijk. Bestandsnamen en alles wat
uit een bestand komt gaan via `textContent` of property-toewijzing
(`createElement`), nooit door een HTML-string. Wie aan deze pagina bouwt,
voegt geen interpolatie toe buiten die poorten.
"""

import html
import json
from pathlib import Path

# Gemeten op het echte corpus (PLAN #22.12, 2026-10-04): elke chip geeft
# `matched`. WhatsApp-kosten: 1 check (en). Zonnebril: 3 checks, en/fr/nl.
# Vaccins-autisme: 3 checks, es/ru — Engelse invoer, geen Engelse check in
# het cluster, dus dit is de cross-linguale demonstratie. Baltimore-brug:
# 3 checks, en/es (het "video toont…"-genre). Wie een chip wijzigt, meet
# eerst opnieuw.
CHIPS = [
    "WhatsApp will charge users for sending messages",
    "Sunglasses cause skin cancer",
    "Vaccines have been proven to cause autism",
    "Video shows the collapse of the Francis Scott Key bridge in Baltimore",
]

# De opmaak en het menu van de demo (PLAN #23.11). Ze kwamen uit de oude site op factiz.org; die ging weg in #34.2f,
# en sindsdien staan ze bij de demo zelf, in `doublecheck/demo/`. Een pad uit site.json wordt hier een volledig adres;
# een adres op try.factiz.org een pad op deze host.
_DEMO = Path(__file__).resolve().parent / "demo"
_MERK = Path(__file__).resolve().parent.parent / "factiz_site"
SITE_DATA = json.loads((_DEMO / "site.json").read_text(encoding="utf-8"))
GEDEELDE_STIJL = (_DEMO / "global.css").read_text(encoding="utf-8")
FAVICON = (_MERK / "static" / "merk" / "logo.svg").read_text(encoding="utf-8")
# Het woordmerk van de PO in kop en voet, uit dezelfde bron als de site en het platform (#23.18, DESIGN §4h).
WOORDMERK = (_MERK / "static" / "merk" / "woordmerk-inline.svg").read_text(encoding="utf-8").strip()
# Wat elke pagina op try.factiz.org in de kop draagt, zoals de site (#23.11).
APP_HEAD = ('<link rel="icon" type="image/svg+xml" href="/favicon.svg">\n'
            '<meta name="theme-color" content="#f3efe8" media="(prefers-color-scheme: light)">\n'
            '<meta name="theme-color" content="#141517" media="(prefers-color-scheme: dark)">')
SITE_URL = SITE_DATA["site"]


def _adres(href: str, data: dict) -> str:
    """Een link uit site.json zoals hij op try.factiz.org werkt."""
    if href.startswith(data["app"]):
        return href[len(data["app"]):] or "/"
    if href.startswith("/"):
        return data["site"] + href
    return href


def _menu(huidig: str, data: dict) -> str:
    """Het hoofdmenu zoals de kop van de oude site (weg sinds PLAN #34.2f) (#23.15, DESIGN
    §4i): per groep een uitklapper met dezelfde naam, met kolommen links en
    één uitgelicht stuk op een veld; zonder script."""
    e = html.escape
    groepen = []
    for groep in data["menu"]:
        kolommen = []
        for kolom in groep["kolommen"]:
            links = "".join(
                '\n                <a class="menulink" href="{}"{}>\n                  <span class="titel">{}</span>{}'
                '\n                  <span class="uitleg">{}</span>\n                </a>'.format(
                    e(_adres(link["href"], data), quote=True),
                    ' aria-current="page"' if _adres(link["href"], data) == huidig else "",
                    e(link["label"]),
                    f'\n                  <span class="stand">{e(link["stand"])}</span>' if link.get("stand") else "",
                    e(link["tekst"]))
                for link in kolom["links"])
            kolommen.append(f'\n              <div class="kolom">\n                <p class="kolomkop">{e(kolom["kop"])}</p>'
                            f'{links}\n              </div>')
        uit = groep["uitgelicht"]
        groepen.append(
            f'\n        <details name="hoofdmenu" class="groep">\n          <summary>{e(groep["groep"])}</summary>'
            f'\n          <div class="paneel">{"".join(kolommen)}'
            f'\n            <a class="uitgelicht {e(uit["veld"], quote=True)}" href="{e(_adres(uit["href"], data), quote=True)}">'
            f'\n              <span class="titel">{e(uit["titel"])}</span>\n              <span class="uitleg">{e(uit["tekst"])}</span>'
            f'\n              <span class="knop wit">{e(uit["knop"])}</span>\n            </a>\n          </div>\n        </details>')
    return f'\n    <nav class="menu" aria-label="Main">{"".join(groepen)}\n    </nav>'


def _kop(huidig: str, data: dict, op_veld: bool = True) -> str:
    """De kop van de site; op_veld legt hem in wit op de band (#23.14, DESIGN §4h)."""
    klasse = "kop op-veld" if op_veld else "kop"
    return (f'<a class="skip" href="#main">Skip to content</a>\n<header class="{klasse}">\n  <div class="baan">\n'
            f'    <a class="merk" href="{data["site"]}/" aria-label="{html.escape(data["naam"], quote=True)}">{WOORDMERK}</a>\n'
            '    <input type="checkbox" id="menuknop" class="menuknop">\n'
            '    <label for="menuknop" class="menulabel">Menu</label>'
            f'{_menu(huidig, data)}\n'
            f'    <a class="knop primair" href="{html.escape(_adres(data["knop"]["href"], data), quote=True)}">'
            f'{html.escape(data["knop"]["label"])}</a>\n  </div>\n</header>')


APP_KOP = {huidig: _kop(huidig, SITE_DATA) for huidig in ("/", "/ask", "/numbers", "/check")}


def band(label: str, kop: str, inleiding: str) -> str:
    """De band bovenaan, zoals de band van de oude site (weg sinds PLAN #34.2f) (#23.14, DESIGN
    §4h): het veld groen met de kop erop. De opmaak staat in global.css. De
    invoer en de uitslag staan eronder op papier, nooit op het veld (D11)."""
    return (f'<section class="band op-veld">\n  <div class="baan">\n    <span class="label">{label}</span>\n'
            f'    <h1>{kop}</h1>\n    <p class="intro">{inleiding}</p>\n  </div>\n</section>')


# De voet zoals de voet van de oude site (weg sinds PLAN #34.2f) (#23.14, DESIGN §4h): de
# missie met de knop op het veld nacht, en de kaart met de groepen van het
# hoofdmenu als kolommen (#23.15, §4i).
APP_VOET = ('<footer class="voet">\n  <div class="baan">\n    <p class="missie">{missie}</p>\n'
            '    <a class="knop wit" href="{knop}">{knoplabel}</a>\n    <div class="glas">\n      <div>\n'
            '        <a class="merk" href="{site}/" aria-label="{naam}">{woordmerk}</a>\n        <p>{slogan}</p>\n'
            '      </div>\n      <nav aria-label="Footer">{links}</nav>\n    </div>\n  </div>\n</footer>').format(
    missie=html.escape(SITE_DATA["missie"]),
    knop=html.escape(_adres(SITE_DATA["knop"]["href"], SITE_DATA), quote=True),
    knoplabel=html.escape(SITE_DATA["knop"]["label"]),
    site=SITE_DATA["site"], naam=html.escape(SITE_DATA["naam"], quote=True), woordmerk=WOORDMERK,
    slogan=html.escape(SITE_DATA["slogan"]),
    links="".join('<div class="voetgroep"><p class="voetkop">{}</p>{}</div>'.format(
        html.escape(groep["groep"]),
        "".join('<a href="{}">{}</a>'.format(html.escape(_adres(link["href"], SITE_DATA), quote=True),
                                            html.escape(link["label"]))
                for kolom in groep["kolommen"] for link in kolom["links"]))
        for groep in SITE_DATA["menu"]))

# De stijl en de labelfuncties staan los, zodat Ask Factiz (#24.10, DESIGN
# §4e) dezelfde kaart toont als de demo: één label, één bonnetjeslijst.
STIJL = """  /* De app in de kolom van de site (PLAN #23.11): links uitgelijnd met het\n     merk, de gereedschapskolom smaller voor leesbaarheid. */\n  .app { padding-top: 2.2rem; padding-bottom: 1rem; }\n  .app > * { max-width: 44rem; }\n  .app p { margin: .4rem 0; }\n  /* Merkschil (DESIGN §4a, sinds #23.14 §4h) om een laboratoriumuitslag (§4)
     heen: de band met de kop bovenaan, de pillen in inkt; de uitslagkaart
     blijft tellen en kleur draagt nooit de betekenis — de tekst draagt. */
  h2 { font-size: 1.05rem; margin: 2rem 0 .6rem; color: var(--zacht);
       font-weight: 600; letter-spacing: 0; }
  .intro { margin: .2rem 0 .6rem; font-size: 1.05rem; }
  .uitleg { color: var(--zacht); font-size: .9rem; margin: .4rem 0; }
  .statregel {
    font-family: var(--mono); font-size: .78rem; letter-spacing: .08em;
    text-transform: uppercase; color: var(--groen-donker);
    margin: 1.1rem 0 0; font-weight: 600;
  }
  label { display: block; margin-top: 1.1rem; font-weight: 600; }
  textarea {
    width: 100%; min-height: 5.5rem; font: inherit; padding: .6rem .7rem;
    border: 1px solid var(--rand); border-radius: 10px;
    background: var(--kaart); color: inherit;
  }
  #dropzone {
    margin-top: 1rem; border: 2px dashed var(--rand); border-radius: 14px;
    background: var(--kaart); padding: 1.5rem 1.2rem; text-align: center;
    cursor: pointer; color: var(--zacht);
  }
  #dropzone strong { color: var(--inkt); }
  #dropzone.sleep { border-color: var(--groen); background: var(--mint);
                    color: var(--inkt); }
  #dropzone .wenk { font-size: .85rem; margin: .3rem 0 0; }
  #preview { display: flex; gap: .9rem; align-items: center;
             margin-top: 1rem; text-align: left; }
  #preview img { width: 72px; height: 72px; object-fit: cover;
                 border-radius: 10px; border: 1px solid var(--rand); }
  #preview .naam { flex: 1; font-size: .9rem; word-break: break-all;
                   color: var(--inkt); }
  button {
    font: inherit; min-height: 2.75rem; padding: .5rem 1.15rem;
    border: 1px solid var(--rand); border-radius: 999px;
    background: var(--kaart); color: inherit; cursor: pointer;
  }
  button[type="submit"] {
    margin-top: 1rem; background: var(--inkt); color: var(--papier);
    border-color: var(--inkt); font-weight: 500; padding: .5rem 1.6rem;
  }
  /* Bezig: de knop zegt het zelf, en de wachtcursor (PO 2026-10-16). */
  button[type="submit"]:disabled { opacity: .7; cursor: progress; }
  .chips { margin-top: 1rem; display: flex; flex-wrap: wrap; gap: .5rem;
           align-items: center; font-size: .85rem; color: var(--zacht); }
  .chip {
    min-height: 44px; padding: .15rem .8rem; border-radius: 999px;
    font-size: .85rem; color: var(--zacht);
  }
  .chip:hover { color: var(--inkt); border-color: var(--zacht); }
  :focus-visible { outline: 2px solid var(--groen); outline-offset: 2px; }
  #uitslag {
    border: 1px solid var(--rand); border-left: 4px solid var(--rand);
    border-radius: 12px; background: var(--kaart);
    padding: 1.1rem 1.25rem; margin-top: .6rem;
  }
  #uitslag[data-cat="matched"] { border-left-color: var(--groen); }
  #uitslag[data-cat="related"] { border-left-color: var(--accent-related); }
  #uitslag h3 { margin: 0 0 .3rem; font-size: 1.25rem; line-height: 1.3; }
  #uitslag p { margin: .4rem 0; }
  /* Het bewijs is het beeld (D2): de bronnen krijgen de meeste ruimte. */
  .bronnen { list-style: none; margin: .9rem 0 0; padding: 0; }
  .bronnen li {
    padding: .7rem 0; border-top: 1px solid var(--rand);
    display: flex; flex-wrap: wrap; gap: .25rem .6rem; align-items: baseline;
  }
  .bronnen .uitgever { font-weight: 650; }
  .bronnen .oordeel {
    border: 1px solid var(--rand); border-radius: 999px;
    padding: .02rem .55rem; font-size: .85rem;
  }
  .bronnen .meta { color: var(--zacht); font-size: .85rem; }
  .bronnen .vert { color: var(--zacht); }
  .bronnen a { color: var(--groen-donker); }
  .bron-zonder-link { color: var(--zacht); }
  .bronnen .linkstand { flex-basis: 100%; color: var(--zacht); font-size: .85rem; }
  #uitslag .actie { margin-top: .9rem; }
  details.dev { margin-top: 2rem; color: var(--zacht); }
  /* Een blok, geen flex: zo houdt de uitklapper zijn driehoekje. */
  details.dev summary { cursor: pointer; font-size: .9rem; min-height: 44px; padding: .7rem 0; box-sizing: border-box; }
  pre {
    background: var(--mint); padding: .75rem; overflow-x: auto;
    white-space: pre-wrap; word-break: break-word; border-radius: 8px;
  }
  #betwisting { border-top: 1px solid var(--rand); margin-top: 1.4rem;
                padding-top: 1rem; }
  #betwisting h3 { font-size: 1rem; margin: 0 0 .4rem; }
  #betwisting label { font-weight: 400; }
  #betwisting textarea { min-height: 4rem; }
  .toestemming { display: flex; gap: .6rem; align-items: flex-start;
                 margin-top: .9rem; }
  .toestemming input { margin-top: .35rem; width: 1.1rem; height: 1.1rem; }
  .toestemming .uitleg { margin: .3rem 0 0; }
  .sleutel { font-family: var(--mono); background: var(--mint);
             padding: .4rem .6rem; display: block; margin-top: .4rem;
             word-break: break-all; border-radius: 6px; }
  @media (prefers-reduced-motion: no-preference) {
    #uitslag { transition: border-color .2s ease; }
    #dropzone { transition: border-color .15s ease, background .15s ease; }
  }
  @media (prefers-reduced-motion: reduce) {
    #uitslag, #dropzone { transition: none; }
  }
"""

LABEL_JS = """function ontsnap(waarde) {
  const hulp = document.createElement('div');
  hulp.textContent = waarde === null || waarde === undefined ? '' : String(waarde);
  return hulp.innerHTML;
}

// Een href krijgt alleen een echt webadres. Ontsnappen maakt een
// `javascript:`-URL niet onschadelijk — die draait ook ge-escaped (#17.5).
function bronLink(url) {
  const adres = String(url === null || url === undefined ? '' : url).trim();
  if (!/^https?:\\/\\//i.test(adres)) {
    return '<span class="bron-zonder-link">' + ontsnap(adres) + '</span>';
  }
  return '<a href="' + ontsnap(adres) + '" rel="noopener noreferrer">source</a>';
}

// Bonnetjes die blijven (#25.9): het oordeel blijft staan als de bron
// verdwijnt. Alleen "offline" krijgt een regel, rustig en zonder rood (D3);
// een onduidelijke of levende link verandert niets aan het beeld.
function linkRegel(link) {
  if (!link || link.status !== 'offline') return '';
  const adres = String(link.archive_url || '');
  const kopie = /^https:\\/\\/web\\.archive\\.org\\//i.test(adres)
    ? ' <a href="' + ontsnap(adres) + '" rel="noopener noreferrer">Archived copy</a>'
      + (link.archived_on ? ' from ' + ontsnap(link.archived_on) : '')
    : ' No archived copy found.';
  return '<span class="linkstand">Source offline since at least '
    + ontsnap(link.offline_since || '') + '.' + kopie + '</span>';
}

function actieKnop(categorie, label) {
  return '<p class="actie"><button type="button" data-actie="' + categorie
    + '">' + label + '</button></p>';
}

function enkelvoud(aantal, een, meer) {
  return aantal === 1 ? een : meer;
}

// Kanten van de schaal (B25). Rood en groen zijn namen van kanten, geen
// kleuren als enige drager: de woorden in de kop dragen de betekenis (§5).
const KANT = {
  'onwaar': 'rood', 'misleidend': 'rood', 'waar': 'groen', 'deels-waar': 'midden',
  'onbewezen': 'geen', 'onbekend': 'geen', 'satire': 'geen',
};

// De woorden van B30 per labelklasse, dezelfde als het label in de tijdlijn
// (DESIGN §4c) en als `verdicts.labelklasse` in Python.
const WOORDEN = {
  'onwaar': 'Known to be false',
  'misleidend': 'Known to be misleading',
  'onwaar-of-misleidend': 'Known to be false or misleading',
  'waar': 'Known to be true',
  'deels-waar': 'Partly true',
  'omstreden': 'Disputed by fact-checkers',
  'satire': 'Satire, according to fact-checkers',
  'onbewezen': 'Unproven, according to fact-checkers',
};

// Een oordeel zonder kant (onbekend, onbewezen, satire) telt niet mee zolang
// er een check mét kant is; oordelen op verschillende kanten zijn omstreden.
function klasseVan(soorten) {
  const metKant = soorten.filter(function (s) { return (KANT[s] || 'geen') !== 'geen'; });
  const kanten = {};
  metKant.forEach(function (s) { kanten[KANT[s]] = true; });
  const alleen = function (s) { return metKant.length > 0 && metKant.every(function (x) { return x === s; }); };
  if (Object.keys(kanten).length > 1) return 'omstreden';
  if (alleen('onwaar')) return 'onwaar';
  if (alleen('misleidend')) return 'misleidend';
  if (kanten.rood) return 'onwaar-of-misleidend';
  if (kanten.groen) return 'waar';
  if (kanten.midden) return 'deels-waar';
  if (soorten.length > 0 && soorten.every(function (s) { return s === 'satire'; })) return 'satire';
  if (soorten.length > 0 && soorten.every(function (s) { return s === 'onbewezen'; })) return 'onbewezen';
  return null;
}

// Jongste oordeel voorop (PO 2026-10-15): verschuift de positie over de
// jaren, dan het oordeel van het jongste jaar en eronder wat er eerder
// gezegd werd. Hier telt "onbewezen" als positie. Dezelfde regel als
// `verdicts.labelklasse_in_tijd`.
const POSITIE = {
  'onwaar': 'rood', 'misleidend': 'rood', 'onwaar-of-misleidend': 'rood', 'waar': 'groen',
  'deels-waar': 'midden', 'omstreden': 'omstreden', 'onbewezen': 'onbewezen',
};

function klasseInTijd(checks) {
  const nu = new Date().getFullYear();
  const perJaar = {};
  checks.forEach(function (check) {
    const datum = String(check.review_date || '');
    const jaar = Number(datum.slice(0, 4));
    if (/^\\d{4}-\\d{2}-\\d{2}/.test(datum) && jaar >= 1995 && jaar <= nu
        && check.verdict_normalized !== 'onbekend') {
      (perJaar[datum.slice(0, 4)] = perJaar[datum.slice(0, 4)] || []).push(check.verdict_normalized);
    }
  });
  const klassen = {}, posities = {};
  Object.keys(perJaar).forEach(function (jaar) {
    klassen[jaar] = klasseVan(perJaar[jaar]);
    if (POSITIE[klassen[jaar]]) posities[jaar] = POSITIE[klassen[jaar]];
  });
  const jaren = Object.keys(posities).sort().reverse();
  const verschillend = {};
  jaren.forEach(function (jaar) { verschillend[posities[jaar]] = true; });
  if (Object.keys(verschillend).length <= 1) {
    return { klasse: klasseVan(checks.map(function (c) { return c.verdict_normalized; })), eerder: [] };
  }
  const eerder = [];
  const gezien = {};
  gezien[posities[jaren[0]]] = true;
  jaren.slice(1).forEach(function (jaar) {
    if (!gezien[posities[jaar]]) {
      eerder.push([klassen[jaar], jaar]);
      gezien[posities[jaar]] = true;
    }
  });
  return { klasse: klassen[jaren[0]], eerder: eerder };
}

function kopVoor(klasse, uitgevers) {
  const telling = uitgevers + ' ' + enkelvoud(uitgevers, 'newsroom', 'newsrooms');
  if (WOORDEN[klasse]) return WOORDEN[klasse] + ' · ' + telling;
  return 'Fact-checked · ' + telling;
}

// De telling als bewijssterkte (D1/DR2): checks, uitgevers, talen, jaar.
function bewijsRegel(bewijs, checks, uitgevers) {
  const talen = bewijs.languages || [];
  return checks.length + ' ' + enkelvoud(checks.length, 'check', 'checks')
    + ' from ' + uitgevers + ' independent '
    + enkelvoud(uitgevers, 'publisher', 'publishers')
    + (talen.length ? ', in ' + talen.length + ' '
       + enkelvoud(talen.length, 'language', 'languages') : '')
    + (bewijs.oldest_date ? ', oldest from '
       + ontsnap(String(bewijs.oldest_date).slice(0, 4)) : '');
}

// De betekenis van een genormaliseerd oordeel, naast de woorden van de
// redactie (B32, *Yanlış (false)*): het datavocabulaire blijft Nederlands op
// de draad, de pagina toont Engels, en het oordeel zelf wordt nooit door een
// model vertaald. Zegt de redactie het al in die woorden, dan niets erbij.
const BETEKENIS = {
  'onwaar': 'false', 'misleidend': 'misleading', 'onwaar-of-misleidend': 'false or misleading',
  'waar': 'true', 'deels-waar': 'partly true', 'omstreden': 'disputed', 'onbewezen': 'unproven',
  'satire': 'satire',
};

function betekenisVan(check) {
  const betekenis = BETEKENIS[check.verdict_normalized];
  return betekenis && String(check.verdict_original || '').trim().toLowerCase() !== betekenis ? betekenis : '';
}

// De bonnetjes van nieuw naar oud; zonder datum achteraan (D2).
function bonnetjes(checks) {
  const opDatum = checks.slice().sort(function (a, b) {
    return String(b.review_date || '').localeCompare(String(a.review_date || ''));
  });
  return opDatum.map(function (check) {
    return '<li>'
      + '<span class="uitgever">' + ontsnap(check.publisher) + '</span>'
      + '<span class="oordeel">' + ontsnap(check.verdict_original)
      + (betekenisVan(check) ? ' <span class="vert">(' + ontsnap(betekenisVan(check)) + ')</span>' : '')
      + '</span>'
      + '<span class="meta">' + ontsnap(check.review_date) + ' · '
      + ontsnap(check.language) + '</span>'
      + bronLink(check.url)
      + linkRegel(check.link)
      + '</li>';
  }).join('');
}

function eerderRegel(eerder) {
  if (!eerder.length) return '';
  return ' Earlier: ' + eerder.map(function (e) {
    const woorden = WOORDEN[e[0]];
    return woorden.charAt(0).toLowerCase() + woorden.slice(1) + ' (' + ontsnap(e[1]) + ')';
  }).join('; ') + '.';
}
"""

PAGINA = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Check a claim | Factiz</title>
__APP_HEAD__
<style>
__STIJL__</style>
</head>
<body>
__APP_KOP__
<main id="main">
__BAND__
<div class="baan app">
<p class="uitleg">Your input is not stored: text is only compared, and
nothing of an image is kept once its fingerprint is computed. The result
never judges a claim; the linked newsrooms do.</p>
<p class="statregel" id="statistiek" hidden></p>

<form id="formulier">
  <label for="tekst">Text</label>
  <textarea id="tekst" name="tekst" placeholder="Paste a claim here"></textarea>

  <div id="dropzone" tabindex="0" role="button"
       aria-label="Drop a screenshot, click to choose an image, or paste one">
    <strong>Drop a screenshot anywhere on this page</strong>
    <p class="wenk">or click to choose an image, or paste one with
    Ctrl+V (Cmd+V on a Mac)</p>
    <div id="preview" hidden></div>
  </div>
  <input id="bestand" name="bestand" type="file" accept="image/*" hidden>

  <button type="submit">Check</button>
</form>

<div class="chips" id="chips">
  <span>Try one:</span>
  __CHIPS__
</div>

<h2>Result</h2>
<div id="uitslag"><p class="uitleg">Nothing submitted yet.</p></div>

<div id="betwisting" hidden>
  <h3>Is this result wrong?</h3>
  <label for="betwistingstekst">What is wrong?</label>
  <textarea id="betwistingstekst"
            placeholder="Describe what this result gets wrong"></textarea>

  <div class="toestemming">
    <input type="checkbox" id="toestemming">
    <div>
      <label for="toestemming">Store what I submitted, for error analysis</label>
      <p class="uitleg">
        <strong>Without</strong> this checkbox we store only a fingerprint (a
        row of numbers capturing the meaning of your input) plus your note and
        the disputed category. Your text cannot simply be read back from those
        numbers, but it is not irreversible encryption either.
        <strong>With</strong> the checkbox we additionally store the submitted
        artifact itself, for __BEWAARTERMIJN__ days, solely to investigate this
        error. You receive a key to have it deleted earlier.
      </p>
    </div>
  </div>

  <p class="actie"><button type="button" id="verstuur-betwisting">Dispute this result</button></p>
</div>

<details class="dev">
  <summary>For developers: the raw response of <code>POST /resolve</code></summary>
  <pre id="respons">Nothing submitted yet.</pre>
</details>

</div>
</main>
__APP_VOET__

<script>
const formulier = document.getElementById('formulier');
const uitvoer = document.getElementById('respons');
const uitslag = document.getElementById('uitslag');
const tekstveld = document.getElementById('tekst');
const dropzone = document.getElementById('dropzone');
const bestandsveld = document.getElementById('bestand');
const voorbeeld = document.getElementById('preview');

// Wát er overeenkomt, in woorden (E3.S2-AC2).
const SIGNAAL = {
  'tekst': 'the claim itself',
  'tekst-gedeeltelijk': 'part of the claim',
  'beeld': 'the image, not the claim',
};

let bezigTimer = null;

function zetStaat(cat) {
  uitslag.dataset.cat = cat;
}

function toonBezig(fase, werk) {
  const start = Date.now();
  const teken = function () {
    const seconden = Math.round((Date.now() - start) / 1000);
    zetStaat('bezig');
    uitslag.innerHTML = '<h3>Checking</h3>'
      + '<p>Step: ' + fase + '.</p>'
      + '<p class="uitleg">What the resolver is doing: ' + werk + '.</p>'
      + '<p class="uitleg">' + seconden + ' seconds elapsed. The first '
      + 'request after startup loads the language model and takes longer.</p>';
  };
  teken();
  stopBezig();
  bezigTimer = setInterval(teken, 1000);
}

function stopBezig() {
  if (bezigTimer !== null) {
    clearInterval(bezigTimer);
    bezigTimer = null;
  }
}

// Elke foutstaat een eigen tekst — nooit terugvallen op `none` (D7).
const FOUT = {
  413: {
    kop: 'File too large',
    uitleg: 'The image exceeds the maximum size. Nothing was checked and '
      + 'nothing was stored.',
    actie: 'Pick a smaller file',
  },
  422: {
    kop: 'Artifact cannot be read',
    uitleg: 'The input could not be processed (empty, corrupted, or not a '
      + 'valid image), so nothing was searched.',
    actie: 'Try different input',
  },
  429: {
    kop: 'Too many requests for now',
    uitleg: 'Too many requests arrived from this address in a short time. '
      + 'Wait half a minute; nothing was checked and nothing was stored.',
    actie: 'Try again shortly',
  },
  503: {
    kop: 'Index unavailable',
    uitleg: 'The index was built with a different model version than this '
      + 'resolver expects. It refuses to search rather than guess.',
    actie: 'Try again later',
  },
};

function toonFout(status, detail) {
  const staat = FOUT[status] || {
    kop: 'Request refused',
    uitleg: 'The server returned status ' + status + '. Nothing was checked.',
    actie: 'Try again',
  };
  zetStaat('fout');
  uitslag.innerHTML = '<h3>' + staat.kop + '</h3>'
    + '<p>' + staat.uitleg + '</p>'
    + (detail ? '<p class="uitleg">Server: ' + ontsnap(detail) + '</p>' : '')
    + actieKnop('fout', staat.actie);
}

function toonNetwerkfout(fout) {
  zetStaat('fout');
  uitslag.innerHTML = '<h3>Server unreachable</h3>'
    + '<p>The request did not arrive. This says nothing about the claim; '
    + 'there was no answer to show.</p>'
    + '<p class="uitleg">Details: ' + ontsnap(fout) + '</p>'
    + actieKnop('fout', 'Try again');
}

__LABEL_JS__
function toonUitslag(data) {
  if (!data || !data.category) {
    zetStaat('fout');
    uitslag.innerHTML = '<h3>Request refused</h3>'
      + '<p>The answer carried no category. The raw response is at the bottom.</p>'
      + actieKnop('fout', 'Try again');
    return;
  }

  if (data.category === 'matched') {
    const bewijs = data.evidence || {};
    const checks = bewijs.checks || [];
    const uitgevers = Number(bewijs.publisher_count) || checks.length;

    // De kop zegt helder wat bekend is (B25), symmetrisch: bekend als onwaar
    // en bevestigd, met de telling als bewijssterkte. Nooit een percentage
    // (DR2): dit is laag 1, de checks van redacties zelf.
    const inTijd = klasseInTijd(checks);
    const kop = kopVoor(inTijd.klasse, uitgevers);

    zetStaat('matched');
    uitslag.innerHTML = '<h3>' + kop + '</h3>'
      + '<p class="uitleg">' + bewijsRegel(bewijs, checks, uitgevers) + '.'
      + eerderRegel(inTijd.eerder) + ' The sources below are the verdict.</p>'
      + '<ol class="bronnen">' + bonnetjes(checks) + '</ol>';
    return;
  }

  if (data.category === 'related') {
    const signalen = (data.matched_on || []).map(function (s) {
      return SIGNAAL[s] || s;
    });
    const wat = data.relation === 'tegenspraak'
      ? 'this claim contradicts a checked claim'
      : (signalen.length ? 'what matches is ' + signalen.join(' and ')
                         : 'there is a partial match');
    zetStaat('related');
    uitslag.innerHTML = '<h3>Related, not the same claim</h3>'
      + '<p>A related claim was found: ' + wat + '.</p>'
      + '<p>That is not enough to treat this as the same claim, so no '
      + 'fact-checker verdict is shown.</p>'
      + actieKnop('related', 'Submit a more precise claim');
    return;
  }

  if (data.category === 'none') {
    zetStaat('none');
    // Wat een `none` waard is (#25.35, PROTOCOL §6): niets gevonden, een taal
    // die de index niet kent, of alleen een beeld om op te zoeken.
    const nooitWaar = '<p>That does not mean the claim is true or false, only '
      + 'that no fact-check of it was found. Many claims are never checked.</p>';
    if (data.reason === 'out_of_scope') {
      uitslag.innerHTML = '<h3>This language is not in the memory yet</h3>'
        + '<p>We searched across languages and found no fact-check. We hold no '
        + 'checks in this language, so finding nothing says little here.</p>'
        + nooitWaar
        + actieKnop('none', 'Try the claim in another language');
      return;
    }
    if (data.reason === 'low_confidence') {
      uitslag.innerHTML = '<h3>Only the image to go on</h3>'
        + '<p>We could not read text in it, and the memory holds no images '
        + 'yet, so finding nothing says very little here.</p>'
        + nooitWaar
        + actieKnop('none', 'Paste the text of the post instead');
      return;
    }
    uitslag.innerHTML = '<h3>Nothing found in the index</h3>'
      + '<p>This claim does not appear in the memory of checked claims.</p>'
      + nooitWaar
      + actieKnop('none', 'Try the literal headline or the screenshot');
    return;
  }

  zetStaat('none');
  uitslag.innerHTML = '<h3>Category: ' + ontsnap(data.category) + '</h3>';
}

// --- De statistiekregel: echte cijfers uit discovery, nooit uit copy ------

let statBasis = null;

function zetStatistiek(ms) {
  if (!statBasis || !statBasis.claims) { return; }
  const el = document.getElementById('statistiek');
  // `scope.claims` telt claims, geen checks — het woord moet kloppen (DR2-geest).
  const basis = statBasis.claims.toLocaleString('en-US')
    + ' checked claims in ' + statBasis.talen + ' languages';
  // Alleen tekst, dus alleen textContent — hier komt nooit HTML in.
  el.textContent = ms === null
    ? 'Ready to search ' + basis
    : 'Searched ' + basis + ' in ' + ms + ' ms';
  el.hidden = false;
}

async function laadStatistiek() {
  try {
    const antwoord = await fetch('/.well-known/doublecheck');
    if (!antwoord.ok) { return; }
    const d = await antwoord.json();
    const talen = (d.scope && d.scope.languages) || [];
    statBasis = {
      claims: Number(d.scope && d.scope.claims) || 0,
      talen: talen.length,
    };
    zetStatistiek(null);
  } catch (fout) {
    // Stil: zonder discovery blijft de regel gewoon verborgen.
  }
}

laadStatistiek();

// --- Het gekozen beeld: één bron van waarheid voor kiezen/slepen/plakken --

let gekozen = null;
let voorbeeldUrl = null;

function wisBestand() {
  gekozen = null;
  bestandsveld.value = '';
  if (voorbeeldUrl !== null) {
    URL.revokeObjectURL(voorbeeldUrl);
    voorbeeldUrl = null;
  }
  voorbeeld.hidden = true;
  voorbeeld.replaceChildren();
}

// De preview ontstaat via createElement en property-toewijzing: een
// bestandsnaam is andermans data en komt nooit in een HTML-string.
function neemBestand(bestand) {
  if (!bestand || !bestand.type || bestand.type.indexOf('image/') !== 0) {
    return false;
  }
  wisBestand();
  gekozen = bestand;
  const beeld = document.createElement('img');
  if (voorbeeldUrl !== null) { URL.revokeObjectURL(voorbeeldUrl); }
  voorbeeldUrl = URL.createObjectURL(bestand);
  beeld.src = voorbeeldUrl;
  beeld.alt = 'preview of the chosen image, shown locally only';
  const naam = document.createElement('span');
  naam.className = 'naam';
  naam.textContent = bestand.name + ' (' + Math.round(bestand.size / 1024)
    + ' kB, stays on this page until you press Check)';
  const weg = document.createElement('button');
  weg.type = 'button';
  weg.textContent = 'Remove';
  weg.addEventListener('click', function (gebeurtenis) {
    gebeurtenis.stopPropagation();
    wisBestand();
  });
  voorbeeld.replaceChildren(beeld, naam, weg);
  voorbeeld.hidden = false;
  return true;
}

dropzone.addEventListener('click', function () { bestandsveld.click(); });
dropzone.addEventListener('keydown', function (gebeurtenis) {
  if (gebeurtenis.key === 'Enter' || gebeurtenis.key === ' ') {
    gebeurtenis.preventDefault();
    bestandsveld.click();
  }
});
bestandsveld.addEventListener('change', function () {
  neemBestand(bestandsveld.files[0]);
});

// Slepen werkt op de hele pagina: de dropzone licht op als doel, maar je
// hoeft niet te mikken.
window.addEventListener('dragover', function (gebeurtenis) {
  if (gebeurtenis.dataTransfer && gebeurtenis.dataTransfer.types
      && Array.prototype.indexOf.call(gebeurtenis.dataTransfer.types, 'Files') !== -1) {
    gebeurtenis.preventDefault();
    dropzone.classList.add('sleep');
  }
});
window.addEventListener('dragleave', function (gebeurtenis) {
  if (gebeurtenis.relatedTarget === null) {
    dropzone.classList.remove('sleep');
  }
});
window.addEventListener('drop', function (gebeurtenis) {
  gebeurtenis.preventDefault();
  dropzone.classList.remove('sleep');
  const bestanden = gebeurtenis.dataTransfer ? gebeurtenis.dataTransfer.files : null;
  if (bestanden && bestanden.length && neemBestand(bestanden[0])) {
    formulier.requestSubmit();
  }
});

// Een geplakt screenshot vuurt direct af; geplakte tekst volgt de normale
// weg naar het tekstveld.
document.addEventListener('paste', function (gebeurtenis) {
  const items = gebeurtenis.clipboardData ? gebeurtenis.clipboardData.items : null;
  if (!items) { return; }
  for (let i = 0; i < items.length; i++) {
    if (items[i].kind === 'file' && items[i].type.indexOf('image/') === 0) {
      const bestand = items[i].getAsFile();
      if (neemBestand(bestand)) {
        gebeurtenis.preventDefault();
        formulier.requestSubmit();
      }
      return;
    }
  }
});

// De chips: gemeten voorbeelden die direct afvuren.
document.getElementById('chips').addEventListener('click', function (gebeurtenis) {
  const knop = gebeurtenis.target.closest('button[data-claim]');
  if (!knop) { return; }
  wisBestand();
  tekstveld.value = knop.dataset.claim;
  formulier.requestSubmit();
});

const betwisting = document.getElementById('betwisting');
const betwistingstekst = document.getElementById('betwistingstekst');
const toestemming = document.getElementById('toestemming');
let laatsteUitslag = null;

function toonBetwisting(data) {
  laatsteUitslag = data;
  betwistingstekst.value = '';
  toestemming.checked = false;
  betwisting.hidden = false;
}

function verbergBetwisting() {
  betwisting.hidden = true;
  laatsteUitslag = null;
}

document.getElementById('verstuur-betwisting').addEventListener('click', async () => {
  const toelichting = betwistingstekst.value.trim();
  if (!toelichting) {
    betwistingstekst.focus();
    return;
  }
  const bestand = gekozen;
  const tekst = tekstveld.value.trim();

  let opties;
  if (bestand) {
    const formData = new FormData();
    formData.append('image', bestand);
    formData.append('disputed_category', laatsteUitslag.category);
    formData.append('dispute_text', toelichting);
    formData.append('consent_to_store_artifact', toestemming.checked ? 'true' : 'false');
    const geraakteClaim = laatsteUitslag.claim && laatsteUitslag.claim.id;
    if (geraakteClaim) formData.append('claim_id', geraakteClaim);
    opties = { method: 'POST', body: formData };
  } else {
    opties = {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        text: tekst,
        disputed_category: laatsteUitslag.category,
        dispute_text: toelichting,
        claim_id: (laatsteUitslag.claim && laatsteUitslag.claim.id) || null,
        consent_to_store_artifact: toestemming.checked,
      }),
    };
  }

  try {
    const antwoord = await fetch('/dispute', opties);
    const data = await antwoord.json();
    if (!antwoord.ok) {
      uitslag.innerHTML = '<h3>Dispute not recorded</h3>'
        + '<p class="uitleg">Server: ' + ontsnap(data && data.detail) + '</p>';
      verbergBetwisting();
      return;
    }
    const bewaard = '<p>Stored: ' + data.stored_fields.map(ontsnap).join(', ') + '.</p>';
    const sleutel = data.deletion_key
      ? '<p>Your deletion key. Save it; it is shown only once. It lets you '
        + 'have the artifact deleted before ' + ontsnap((data.artifact_expires_at || '').slice(0, 10))
        + '.<code class="sleutel">' + ontsnap(data.deletion_key) + '</code></p>'
      : '<p>No artifact was stored, so no key is needed.</p>';
    uitslag.innerHTML = '<h3>Dispute recorded (#' + ontsnap(data.dispute_id) + ')</h3>'
      + '<p>Thank you. This case will be used to improve the resolver.</p>'
      + bewaard + sleutel;
    verbergBetwisting();
  } catch (fout) {
    uitslag.innerHTML = '<h3>Dispute not sent</h3>'
      + '<p>The server was unreachable. Nothing was recorded.</p>';
    verbergBetwisting();
  }
});

uitslag.addEventListener('click', function (gebeurtenis) {
  if (gebeurtenis.target.matches('button[data-actie]')) {
    tekstveld.focus();
    tekstveld.select();
  }
});

formulier.addEventListener('submit', async (gebeurtenis) => {
  gebeurtenis.preventDefault();
  const tekst = tekstveld.value.trim();
  const bestand = gekozen;

  let opties;
  if (bestand) {
    const formData = new FormData();
    formData.append('image', bestand);
    if (tekst) { formData.append('text', tekst); }
    opties = { method: 'POST', body: formData };
  } else {
    opties = {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text: tekst }),
    };
  }

  const werk = bestand
    ? 'computing the image hash, running OCR, and searching the index'
    : 'computing a fingerprint and searching the index';
  // Eén verzoek tegelijk, en de knop zegt dat er gecontroleerd wordt
  // (PO 2026-10-16); ook een chip of Enter start geen tweede verzoek.
  const knop = formulier.querySelector('button[type="submit"]');
  if (knop.disabled) return;
  knop.disabled = true;
  knop.textContent = 'Checking...';
  uitvoer.textContent = 'Working...';
  verbergBetwisting();
  toonBezig('preparing the artifact', werk);
  const begonnen = performance.now();
  try {
    const verzoek = fetch('/resolve', opties);
    toonBezig('waiting for the resolver', werk);
    const antwoord = await verzoek;
    const data = await antwoord.json();
    stopBezig();
    uitvoer.textContent = antwoord.status + ' ' + antwoord.statusText + '\\n\\n'
      + JSON.stringify(data, null, 2);
    if (!antwoord.ok) {
      toonFout(antwoord.status, data && data.detail);
      verbergBetwisting();
      return;
    }
    // De gemeten antwoordtijd van déze aanvraag — systeemfeit, geen belofte.
    zetStatistiek(Math.round(performance.now() - begonnen));
    toonUitslag(data);
    toonBetwisting(data);
  } catch (fout) {
    stopBezig();
    uitvoer.textContent = 'Verzoek mislukt: ' + fout;
    verbergBetwisting();
    toonNetwerkfout(fout);
  } finally {
    knop.disabled = false;
    knop.textContent = 'Check';
  }
});
</script>
</body>
</html>
"""

# De chips landen één keer, bij import, en uitsluitend ge-escaped: de teksten
# zijn van ons, maar de poort blijft dezelfde als voor alle andere waarden.
_CHIP_KNOPPEN = "\n  ".join(
    '<button type="button" class="chip" data-claim="{v}">"{t}"</button>'.format(
        v=html.escape(chip, quote=True), t=html.escape(chip)
    )
    for chip in CHIPS
)
PAGINA = PAGINA.replace("__CHIPS__", _CHIP_KNOPPEN)
PAGINA = (PAGINA.replace("__STIJL__", GEDEELDE_STIJL + STIJL).replace("__APP_HEAD__", APP_HEAD).replace("__LABEL_JS__", LABEL_JS)
          .replace("__APP_KOP__", APP_KOP["/"]).replace("__APP_VOET__", APP_VOET)
          .replace("__BAND__", band("Check a claim", "Has this been checked?",
                                    "Paste a claim or drop a screenshot. Factiz is the fact-checkers' collective "
                                    "memory: see whether this claim was checked before, by whom, and what they "
                                    "found, with the source attached.")))
