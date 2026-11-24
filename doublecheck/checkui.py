"""De controlepagina op try.factiz.org (PLAN #31.13 en #32.10, SPECS E5.S4, DESIGN §4g).

Een bericht of screenshot, en terug wat Factiz las, het oordeel met zijn kleur, waar het vandaan komt (de database
of het zoeken), en de bronnen met hun band uit de bronnenlijst (B51). Dezelfde schil als Ask (`webui.STIJL`).

Zo streng als Ask: deze pagina bouwt nooit HTML uit een string. Elk element ontstaat met `createElement`, elke
waarde gaat via `textContent`, en een href alleen na de schemacontrole in `link()`. Het bericht gaat met POST in de
body naar de dienst, nooit in een adres (DR3). Staat de controle uit (B43), dan is de knop uit en gaat er niets weg.

De uitlegzin van het model staat alleen in het ruwe antwoord: hij is niet gemeten op trouw aan de bronnen (B31).
"""

import html
import json

from doublecheck.webui import APP_HEAD, APP_KOP, APP_VOET, GEDEELDE_STIJL, STIJL, band

# Het oordeel in woorden (B51). Groen en rood alleen waar de bronnenlijst het draagt; anders de tweede regel.
UITKOMST = {"klopt": "True", "klopt niet": "False", "misleidend": "Misleading", "onzeker": "Not settled"}
ZONDER_KLEUR = {"klopt": "Probably true, but fewer than two reliable outlets confirm it.",
                "klopt niet": "Probably false, but no reliable outlet or fact-check contradicts it.",
                "misleidend": "Possibly misleading, but no reliable outlet or fact-check says so.",
                "onzeker": "The sources Factiz found do not settle it."}
OVER_BEELD = ("This is about what a photo or video shows. Factiz cannot see it here, and reports that the event "
              "happened do not confirm the image.")  # #32.12
# #32.32, DESIGN §4g: geen bewering en satire krijgen geen kleur en geen oordeel over waar of onwaar.
# Geen bewering zegt wat Factiz vond, niet wat het bericht is: bij een screenshot kan de bewering in de foto zitten
# (PO 2026-11-03, BENCHMARK §209).
ZONDER_BEWERING = {"no_claim": ("No checkable claim found", "Factiz found no checkable claim in this message."),
                   "satire": ("Satire", "This looks like satire. A source below says so.")}
GEEN_BEWERING_BEELD = ("Factiz found no checkable claim in the text it could read from this screenshot. The photo "
                       "itself may still make one, and Factiz does not look at photos yet.")
# B57, DESIGN §4l: *niet bevestigd* is een eigen uitkomst, nooit rood, oranje of groen, met de zoekvragen eronder.
NIET_BEVESTIGD = {"kop": "Not confirmed", "zin": "No reliable source reports this.", "gezocht": "Factiz searched for:"}
ZOEKSOORT = {"own_site": "On the website it names", "real_news": "The real news", "the_source": "The source it relies on"}
# B48, DESIGN §4i: de verbetering in woorden, naast de markering in het bericht.
MAAR = {"kop": "Mostly true, but", "moet": "should be", "bron": "According to "}
OVER_BEWERING = "This message reports on a claim made by someone else. That claim is:"
# #32.54, DESIGN §4m: de foto bij de bron in twee lagen; het nieuws mag groen zijn, de foto staat apart.
# §251: een controle duurt 10 tot 15 seconden; de pagina zegt wat Factiz doet en telt de seconden.
BEZIG = {"tekst": "Checking. Factiz looks for fact-checks, searches reliable sources and reads them. This takes 10 to 15 "
                  "seconds.",
         "beeld": "Checking. Factiz reads the screenshot, looks for fact-checks, searches reliable sources and reads "
                  "them; if they confirm the news, it looks for the photo at those sources. This takes 10 to 15 "
                  "seconds."}
FOTO = {"kop": "News confirmed, photo not found", "nieuws": "The news", "klopt": "True", "foto": "The photo",
        "niet": "None of the reliable sources that confirm this news shows this photo. It may come from somewhere else.",
        "wel": "The photo appears at "}
# #32.13: het antwoord in twee lagen; de kleur hoort bij de bewering, wat klopt en wat er echt gebeurde staan ernaast.
LAGEN = {"bewering": "The claim", "feit": "What is confirmed", "anders": "What really happened"}
ROUTE = {"database": "Checked by fact-checkers", "search": "Found on the web"}
BAND = {"goed": "reliable", "wisselend": "mixed", "laag": "low reliability"}
ROL = {"confirms": "Confirms", "contradicts": "Contradicts", "confirms_fact": "Confirms the fact",
       "same_claim": "Same claim, fact-check"}
# #32.11: een label bij een bron van een staat, geen oordeel (de PO: "zo tagged Google ook").
STAATSMEDIA = "state media"
# D7: elke foutstaat een eigen tekst, op de reden die `POST /check` meegeeft.
FOUTEN = {
    "off": "Checking messages opens with the beta. Until then, nothing you enter here is sent anywhere.",
    "no_text": "Factiz found no text in this image. Version 1 reads the text in screenshots; photos without "
               "text are not checked yet.",
    "image_unreadable": "Factiz could not open this image. Try a PNG or JPEG screenshot.",
    "too_large": "This image is larger than 8 MB.",
    "too_long": "This text is longer than 10,000 characters.",
    "cap": "Today's checks are used up. Try again tomorrow.",
    "model_unreachable": "The check cannot reach its model right now. Try again in a minute.",
    "search_unreachable": "The check cannot reach its search service right now. Try again in a minute.",
    "version": "The check is being updated. Try again later.",
    "other": "Something went wrong. Try again in a minute.",
}
# B55: één zin bij het uploaden, geen knop per controle; alleen met `[berichtcontrole] beeld` aan.
# B67 (§252): eerlijk over wat zwart wordt en wat kan blijven
BEELD_ZIN = ("Factiz sends your screenshot to Anthropic's model for this check; Anthropic keeps it for at most 30 days "
             "and does not train on it. Phone numbers, email addresses, handles and the names of a group or sender "
             "that Factiz reads in the image are blacked out first; the name of whoever published a post, and names "
             "in comments, can remain.")
PRIVACY_KORT = ("Your screenshot is read on our server in the EU and not kept. Phone numbers, email addresses, handles "
                "and names in chats are removed first; the name of whoever published a post, and names in comments, "
                "can remain. Only that text goes to a web search service (Brave Search) and to "
                "Anthropic's model in the United States, for this one check. Anthropic keeps it for at most 30 days "
                "and does not train on it; Brave says the search service does not share it or train on it.")
# B55: met het beeld aan gaat ook het screenshot naar het model; de korte tekst zegt dat (tussenrelease 2026-11-03).
PRIVACY_KORT_BEELD = ("Your screenshot is read on our server in the EU and not kept there. Phone numbers, email "
                      "addresses, handles and names in chats are removed from the text first; the name of whoever "
                      "published a post, and names in comments, can remain. Only that text goes to a web search "
                      "service (Brave Search). The text and the screenshot, with those details blacked out and without its "
                      "metadata, go to Anthropic's model in the United States, for this one check. Anthropic keeps them "
                      "for at most 30 days and does not train on them; Brave says the search service does not share "
                      "the text or train on it.")

_EXTRA_STIJL = """
  textarea#tekst { width: 100%; min-height: 7rem; font: inherit; padding: .7rem .8rem;
                   border: 1px solid var(--rand); border-radius: 10px; background: var(--kaart); color: inherit; }
  .invoer { display: grid; gap: .5rem; margin: 1rem 0 .4rem; }
  .privacykort { font-size: .9rem; color: var(--zacht); border-left: 3px solid var(--groen);
                 padding: .3rem .7rem; margin: .6rem 0 1rem; }
  #uitslag { border: 1px solid var(--rand); border-radius: 12px; background: var(--kaart);
             padding: 1rem 1.15rem .6rem; margin-top: .6rem; }
  .gelezen { white-space: pre-wrap; font-size: .9rem; color: var(--zacht); margin: .3rem 0 .6rem; }
  :root { --rood: #b3261e; }
  @media (prefers-color-scheme: dark) { :root { --rood: #f2857e; } }
  /* Het oordeel in de schreefloze; nooit alleen kleur: het woord en een streep dragen de betekenis. */
  .uitkomst { font-size: 1.6rem; font-weight: 600; letter-spacing: -.02em; line-height: 1.2; margin: .5rem 0 .2rem;
              padding-left: .7rem; border-left: .35rem solid var(--rand); }
  .uitkomst.rood { border-left-color: var(--rood); color: var(--rood); }
  .uitkomst.groen { border-left-color: var(--groen); color: var(--groen-donker); }
  .uitkomst.oranje { border-left-color: var(--oranje); color: var(--oranje-donker); }
  /* B48: klopt grotendeels in de kleur van let op, nooit groen; de markering valt alleen op de foute woorden. */
  .uitkomst.maar { border-left-color: var(--oranje); }
  .uitkomst.klein { font-size: 1.1rem; margin: .1rem 0; }
  mark.maar { background: color-mix(in srgb, var(--oranje) 30%, transparent); color: inherit; border-radius: 3px;
              padding: 0 .1rem; }
  .sr { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; }
  ul.bonnetjes .staat { font-family: var(--mono); font-size: .72rem; text-transform: uppercase; letter-spacing: .04em;
                        border: 1px solid var(--rand); border-radius: 4px; padding: 0 .3rem; margin-left: .3rem; }
  .zonder { margin: 0 0 .4rem; color: var(--zacht); }
  .laag { font-family: var(--mono); font-size: .78rem; text-transform: uppercase; letter-spacing: .04em;
          color: var(--zacht); margin: .6rem 0 0; }
  .feit p, .anders p { margin: .15rem 0 .3rem; }
  .feit .wie, .anders .wie { font-size: .9rem; color: var(--zacht); }
  /* Het inzetje, zoals een factchecker het zet: een kader naast de bewering, niet in haar kleur. */
  .anders { border: 1px solid var(--rand); border-left: .35rem solid var(--rand); border-radius: 8px;
            padding: .2rem .8rem .3rem; margin: .6rem 0; }
  .herkomst { font-size: 1.05rem; font-weight: 600; margin: .4rem 0 .3rem; }
  ul.bonnetjes { list-style: none; margin: .3rem 0 .6rem; padding: 0; }
  ul.bonnetjes li { border-top: 1px solid var(--rand); padding: .6rem 0; }
  ul.bonnetjes .wie { font-weight: 600; }
  ul.bonnetjes .rol { font-family: var(--mono); font-size: .78rem; text-transform: uppercase; letter-spacing: .04em;
                      color: var(--zacht); }
  ul.bonnetjes .rol.tegen { color: var(--rood); }
  .fout { margin: 0; }
  /* Uit (B43) is iets anders dan bezig: geen wachtcursor. */
  #knop:disabled { cursor: not-allowed; opacity: .45; }
"""

CHECK_PAGINA = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Check a message | Factiz</title>
__APP_HEAD__
<style>
__STIJL____EXTRA_STIJL__</style>
</head>
<body data-aan="__AAN__">
__APP_KOP__
<main id="main">
__BAND__
<div class="baan app">

<form id="formulier">
  <div class="invoer">
    <label for="tekst">The message</label>
    <textarea id="tekst" name="tekst" placeholder="Paste the message here"></textarea>
    <label for="beeld">Or a screenshot</label>
    <input id="beeld" name="beeld" type="file" accept="image/png,image/jpeg,image/webp">
    __BEELD_ZIN__
  </div>
  <p class="privacykort">__PRIVACY__ <a href="https://factiz.org/privacy/">How we handle privacy</a></p>
  __KNOP__
</form>

<h2>Result</h2>
<div id="uitslag" aria-live="polite"><p class="uitleg">__BEGIN__</p></div>

<details class="dev">
  <summary>For developers: the raw response of <code>POST /check</code></summary>
  <pre id="respons">Nothing checked yet.</pre>
</details>

</div>
</main>
__APP_VOET__

<script>
const AAN = document.body.dataset.aan === 'true';
const UITKOMST = __UITKOMST__;
const ZONDER_KLEUR = __ZONDER_KLEUR__;
const OVER_BEELD = __OVER_BEELD__;
const ZONDER_BEWERING = __ZONDER_BEWERING__;
const NIET_BEVESTIGD = __NIET_BEVESTIGD__;
const ZOEKSOORT = __ZOEKSOORT__;
const GEEN_BEWERING_BEELD = __GEEN_BEWERING_BEELD__;
const MAAR = __MAAR__;
const OVER_BEWERING = __OVER_BEWERING__;
const FOTO = __FOTO__;
const BEZIG = __BEZIG__;
const LAGEN = __LAGEN__;
const ROUTE = __ROUTE__;
const BAND = __BAND_NAMEN__;
const ROL = __ROL__;
const STAATSMEDIA = __STAATSMEDIA__;
const FOUTEN = __FOUTEN__;
const formulier = document.getElementById('formulier');
const tekstveld = document.getElementById('tekst');
const beeldveld = document.getElementById('beeld');
const knop = document.getElementById('knop');
const uitslag = document.getElementById('uitslag');
const uitvoer = document.getElementById('respons');

// Eén element, met tekst als tekst: nooit een HTML-string (zie de docstring).
function el(tag, klasse, tekst) {
  const e = document.createElement(tag);
  if (klasse) e.className = klasse;
  if (tekst !== undefined && tekst !== null) e.textContent = String(tekst);
  return e;
}

function link(href, tekst) {
  let adres;
  try { adres = new URL(href); } catch (fout) { return el('span', null, tekst); }
  if (adres.protocol !== 'https:' && adres.protocol !== 'http:') return el('span', null, tekst);
  const a = el('a', null, tekst);
  a.href = adres.href;
  a.rel = 'noopener noreferrer';
  return a;
}

function leeg(knoop) {
  while (knoop.firstChild) knoop.removeChild(knoop.firstChild);
}

function meldt(tekst) {
  leeg(uitslag);
  uitslag.appendChild(el('p', 'fout', tekst));
}

// Waar het antwoord vandaan komt, met de tellingen die de kleur droegen.
function herkomstregel(d) {
  if (d.route === 'database') {
    const redacties = new Set(d.sources.map(b => b.publisher));
    return ROUTE.database + ' (' + redacties.size + (redacties.size === 1 ? ' newsroom)' : ' newsrooms)');
  }
  const goed = d.sources.filter(b => b.band === 'goed');
  const voor = new Set(goed.filter(b => b.role === 'confirms').map(b => b.publisher)).size;
  const tegen = new Set(goed.filter(b => b.role === 'contradicts').map(b => b.publisher)).size;
  // #32.30: met lezer-v5 kan een check uit de database tegenspreken; die telt apart
  const factchecks_tegen = d.sources.filter(b => b.kind === 'check van een redactie' && b.role === 'contradicts').length;
  return ROUTE.search + ': ' + voor + ' reliable ' + (voor === 1 ? 'outlet confirms' : 'outlets confirm') +
         ' the claim' + (tegen ? ', ' + tegen + ' contradict' + (tegen === 1 ? 's' : '') + ' it' : '') +
         (factchecks_tegen ? ', ' + factchecks_tegen + ' fact-check' + (factchecks_tegen === 1 ? '' : 's') +
          ' from our database ' + (factchecks_tegen === 1 ? 'contradicts' : 'contradict') + ' it' : '');
}

function laag(klasse, kop, zin, voor, bronnen) {
  const blok = el('div', klasse);
  blok.appendChild(el('p', 'laag', kop));
  blok.appendChild(el('p', null, zin));
  const wie = [...new Set(bronnen.map(b => b.publisher).filter(Boolean))];
  if (wie.length) blok.appendChild(el('p', 'wie', voor + wie.join(', ')));
  return blok;
}

function bonnetjes(d) {
  const lijst = el('ul', 'bonnetjes');
  for (const b of d.sources) {
    const li = el('li');
    if (b.kind === 'check van een redactie') {
      li.appendChild(el('div', 'wie', 'Fact-check by ' + (b.publisher || 'a newsroom') + (b.date ? ', ' + b.date : '')));
      li.appendChild(el('div', null, 'Rated: ' + (b.rating || 'unrated')));
      li.appendChild(link(b.url, 'Read the fact-check'));
    } else {
      const rol = el('div', 'rol' + (b.role === 'contradicts' ? ' tegen' : ''), (ROL[b.role] || 'Source') +
                     ' · ' + (b.publisher || '') + ' · ' + (BAND[b.band] || 'not rated'));
      if (b.state_media) rol.appendChild(el('span', 'staat', STAATSMEDIA));
      li.appendChild(rol);
      li.appendChild(link(b.url, b.title || b.url));
    }
    lijst.appendChild(li);
  }
  return lijst;
}

const KLEUR = {red: 'rood', green: 'groen', orange: 'oranje'};

// B57, DESIGN §4l: de zoekvragen van de controle, elk met wat ze vonden: de bonnetjes van wat er níét is.
function zoekvragen(d) {
  const lijst = el('ul', 'bonnetjes');
  for (const z of d.searches) {
    const li = el('li');
    li.appendChild(el('div', 'wie', (ZOEKSOORT[z.kind] || 'Search') + (z.site ? ' · ' + z.site : '')));
    li.appendChild(el('div', null, '“' + z.query + '” — ' + z.found +
                      (z.found === 1 ? ' result' : ' results')));
    lijst.appendChild(li);
  }
  return lijst;
}

// Wat Factiz las; bij klopt grotendeels met de foute woorden gemarkeerd, en voor een schermlezer in woorden (B48).
function gelezenBlok(d) {
  const gelezen = el('details');
  gelezen.appendChild(el('summary', null, 'What Factiz read'));
  const p = el('p', 'gelezen');
  const c = d.correction;
  if (c && c.start >= 0 && c.end > c.start && c.end <= d.read.length) {
    p.appendChild(document.createTextNode(d.read.slice(0, c.start)));
    p.appendChild(el('mark', 'maar', d.read.slice(c.start, c.end)));
    p.appendChild(el('span', 'sr', ' (marked: ' + c.words + ', ' + MAAR.moet + ' ' + c.should_be + ')'));
    p.appendChild(document.createTextNode(d.read.slice(c.end)));
    gelezen.open = true;
  } else {
    p.textContent = d.read;
  }
  gelezen.appendChild(p);
  return gelezen;
}

// Het oordeel in woorden, met de kleur die de bronnenlijst draagt, of de tweede regel als er geen is.
function oordeel(verdict, kleur) {
  uitslag.appendChild(el('p', 'uitkomst ' + kleur, kleur ? UITKOMST[verdict] : UITKOMST.onzeker));
}

function maar(d) {
  const c = d.correction;
  const p = el('p', 'uitkomst maar', MAAR.kop + ' ');
  p.appendChild(el('strong', null, c.words));
  p.appendChild(document.createTextNode(' ' + MAAR.moet + ' '));
  p.appendChild(el('strong', null, c.should_be));
  p.appendChild(document.createTextNode('.'));
  uitslag.appendChild(p);
  const bron = el('p', 'zonder', MAAR.bron);
  bron.appendChild(link(c.url, c.publisher || c.url));
  uitslag.appendChild(bron);
}

function toon(d, vanBeeld) {
  leeg(uitslag);
  const gelezen = gelezenBlok(d);
  uitslag.appendChild(gelezen);
  const uit = d.outcome || 'uncertain';
  if (ZONDER_BEWERING[uit]) {
    // bij een screenshot zonder gelezen bewering: wat Factiz las staat open, en de foto kan nog iets beweren
    const beeld = uit === 'no_claim' && vanBeeld;
    if (beeld) gelezen.open = true;
    uitslag.appendChild(el('p', 'uitkomst', ZONDER_BEWERING[uit][0]));
    uitslag.appendChild(el('p', 'zonder', beeld ? GEEN_BEWERING_BEELD : ZONDER_BEWERING[uit][1]));
    if (uit === 'satire' && d.sources.length) {
      uitslag.appendChild(el('h3', null, 'Sources'));
      uitslag.appendChild(bonnetjes(d));
    }
    return;
  }
  if (uit === 'photo_not_at_source') {
    // DESIGN §4m: het nieuws klopt (een kleine groene laag), de foto vonden we niet bij dat nieuws; geen groen geheel
    uitslag.appendChild(el('p', 'uitkomst', FOTO.kop));
    const nieuws = el('div', 'feit');
    nieuws.appendChild(el('p', 'laag', FOTO.nieuws));
    nieuws.appendChild(el('p', 'uitkomst groen klein', FOTO.klopt));
    uitslag.appendChild(nieuws);
    const foto = el('div', 'anders');
    foto.appendChild(el('p', 'laag', FOTO.foto));
    foto.appendChild(el('p', null, FOTO.niet));
    uitslag.appendChild(foto);
    uitslag.appendChild(el('p', 'herkomst', herkomstregel(d)));
    if (d.sources.length) {
      uitslag.appendChild(el('h3', null, 'Sources'));
      uitslag.appendChild(bonnetjes(d));
    }
    return;
  }
  if (uit === 'unconfirmed') {
    // B57: geen kleur, geen oordeel over waar of onwaar; wel waar Factiz zocht en wat het vond
    uitslag.appendChild(el('p', 'uitkomst', NIET_BEVESTIGD.kop));
    uitslag.appendChild(el('p', 'zonder', NIET_BEVESTIGD.zin));
    if (d.searches && d.searches.length) {
      uitslag.appendChild(el('h3', null, NIET_BEVESTIGD.gezocht));
      uitslag.appendChild(zoekvragen(d));
    }
    if (d.sources.length) {
      uitslag.appendChild(el('h3', null, 'Sources'));
      uitslag.appendChild(bonnetjes(d));
    }
    return;
  }
  const kleur = KLEUR[d.colour] || '';
  if (uit === 'about_a_claim') {
    // DESIGN §4g: het bericht zelf krijgt geen kleur; de bewering waarover het gaat wel
    const bewering = KLEUR[d.claim_colour] || '';
    uitslag.appendChild(el('p', 'laag', OVER_BEWERING));
    oordeel(d.verdict, bewering);
    if (!bewering) uitslag.appendChild(el('p', 'zonder', ZONDER_KLEUR[d.verdict] || ZONDER_KLEUR.onzeker));
  } else if (uit === 'mostly_true' && d.correction) {
    uitslag.appendChild(el('p', 'laag', LAGEN.bewering));
    maar(d);
  } else {
    uitslag.appendChild(el('p', 'laag', LAGEN.bewering));
    oordeel(d.verdict, kleur);
    if (!kleur) uitslag.appendChild(el('p', 'zonder',
      d.about_image ? OVER_BEELD : (ZONDER_KLEUR[d.verdict] || ZONDER_KLEUR.onzeker)));
  }
  // #32.13: wat klopt en wat er echt gebeurde, elk alleen uit het eigen veld, met de uitgevers erbij
  if (d.fact) uitslag.appendChild(laag('feit', LAGEN.feit, d.fact, 'Confirmed by ',
                                       d.sources.filter(b => b.role === 'confirms_fact' || b.role === 'confirms')));
  if (d.what_happened) uitslag.appendChild(laag('anders', LAGEN.anders, d.what_happened, 'According to ',
                                                d.sources.filter(b => b.role === 'contradicts')));
  if (d.photo && d.photo.found && d.photo.page) {  // DESIGN §4m: de foto staat bij een bevestigende bron
    const p = el('p', 'wie', FOTO.wel);
    p.appendChild(link(d.photo.page, new URL(d.photo.page).hostname.replace(/^www\\./, '')));
    uitslag.appendChild(p);
  }
  uitslag.appendChild(el('p', 'herkomst', herkomstregel(d)));
  if (d.sources.length) {
    uitslag.appendChild(el('h3', null, 'Sources'));
    uitslag.appendChild(bonnetjes(d));
  }
}

async function controleer() {
  const tekst = tekstveld.value.trim();
  const bestand = beeldveld.files[0];
  if (!tekst && !bestand) return;
  meldt(bestand ? BEZIG.beeld : BEZIG.tekst);
  const teller = el('p', 'zonder', '0 s');
  uitslag.appendChild(teller);
  const begin = Date.now();
  const klok = setInterval(function () { teller.textContent = Math.round((Date.now() - begin) / 1000) + ' s'; }, 1000);
  let antwoord;
  try {
    if (bestand) {
      const formdata = new FormData();
      formdata.append('image', bestand);
      if (tekst) formdata.append('text', tekst);
      antwoord = await fetch('/check', { method: 'POST', body: formdata });
    } else {
      antwoord = await fetch('/check', { method: 'POST', headers: { 'content-type': 'application/json' },
                                         body: JSON.stringify({ text: tekst }) });
    }
  } catch (fout) {
    clearInterval(klok);
    meldt(FOUTEN.model_unreachable);
    return;
  }
  clearInterval(klok);
  let d = null;
  try { d = await antwoord.json(); } catch (fout) { d = null; }
  uitvoer.textContent = d ? JSON.stringify(d, null, 2) : String(antwoord.status);
  if (!antwoord.ok) {
    const reden = d && d.detail && d.detail.reason;
    meldt(FOUTEN[reden] || FOUTEN.other);
    return;
  }
  toon(d, !!bestand);
}

formulier.addEventListener('submit', function (gebeurtenis) {
  gebeurtenis.preventDefault();
  if (!AAN) return;
  controleer();
});
</script>
</body>
</html>
"""


def _js(waarde) -> str:
    """Een waarde als JavaScript, zonder dat een tekst het script kan sluiten."""
    return json.dumps(waarde, ensure_ascii=False).replace("<", "\\u003c")


_VAST = {
    "__STIJL__": GEDEELDE_STIJL + STIJL, "__EXTRA_STIJL__": _EXTRA_STIJL, "__APP_HEAD__": APP_HEAD,
    "__APP_KOP__": APP_KOP["/check"], "__APP_VOET__": APP_VOET,
    "__BAND__": band("Check a message", "Is this true?",
                     "Paste a message or choose a screenshot. Factiz first looks for fact-checks by newsrooms, then "
                     "searches the web and weighs what reliable outlets say, and shows where its answer comes from."),
    "__UITKOMST__": _js(UITKOMST), "__ZONDER_KLEUR__": _js(ZONDER_KLEUR), "__OVER_BEELD__": _js(OVER_BEELD),
    "__ZONDER_BEWERING__": _js(ZONDER_BEWERING), "__NIET_BEVESTIGD__": _js(NIET_BEVESTIGD),
    "__ZOEKSOORT__": _js(ZOEKSOORT),
    "__GEEN_BEWERING_BEELD__": _js(GEEN_BEWERING_BEELD), "__MAAR__": _js(MAAR), "__OVER_BEWERING__": _js(OVER_BEWERING), "__FOTO__": _js(FOTO), "__BEZIG__": _js(BEZIG), "__LAGEN__": _js(LAGEN), "__ROUTE__": _js(ROUTE),
    "__BAND_NAMEN__": _js(BAND), "__ROL__": _js(ROL), "__STAATSMEDIA__": _js(STAATSMEDIA), "__FOUTEN__": _js(FOUTEN),
}


def pagina(aan: bool, beeld: bool = False) -> str:
    """De pagina; met de controle uit is de knop uit en staat dat er eerlijk (B43). Gaat het beeld mee (B55), dan staat
    de zin daarover bij het kiezen van een screenshot."""
    uit = CHECK_PAGINA
    for plek, waarde in _VAST.items():
        uit = uit.replace(plek, waarde)
    knop = '<button type="submit" id="knop">Check</button>' if aan else '<button type="submit" id="knop" disabled>Check</button>'
    begin = "Nothing checked yet." if aan else html.escape(FOUTEN["off"], quote=False)
    zin = f'<p class="privacykort">{html.escape(BEELD_ZIN, quote=False)}</p>' if beeld else ""
    uit = uit.replace("__PRIVACY__", html.escape(PRIVACY_KORT_BEELD if beeld else PRIVACY_KORT, quote=False))
    return (uit.replace("__AAN__", "true" if aan else "false").replace("__KNOP__", knop).replace("__BEGIN__", begin)
            .replace("__BEELD_ZIN__", zin))
