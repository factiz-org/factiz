"""Ask Factiz (PLAN #24.10, SPECS E5.S3, DESIGN §4e): de pagina.

Een vraag in gewone woorden, en terug de gecheckte beweringen die er het
dichtst bij liggen, elk als claimkaart (DESIGN §4d): eerst de bewering zoals
redacties haar checkten, dan het label met de telling, dan de bonnetjes.
Het oordeel hoort bij de bewering, nooit bij de vraag. Dezelfde schil en
dezelfde labelregels als de demo (`webui.STIJL`, `webui.LABEL_JS`).

De vraag gaat met POST in de body naar déze resolver, nooit in een URL
(DR3). Strenger dan de demo: deze pagina bouwt nooit HTML uit een string.
Elk element ontstaat met `createElement`, elke waarde gaat via
`textContent`, en een href alleen na de schemacontrole in `link()`.
"""

import html

from doublecheck.ask import METING
from doublecheck.webui import APP_HEAD, APP_KOP, APP_VOET, GEDEELDE_STIJL, LABEL_JS, STIJL, band

# Uit de testset (`docs/steekproeven/24.10-vragen.json`), en alleen vragen
# die daar de juiste bewering als eerste getoonde regel kregen, gemeten over
# het pad van `ask.py` (BENCHMARK §115). Wie een voorbeeld wijzigt, meet eerst.
VOORBEELDEN = [
    "Did corona escape from a lab in Wuhan?",
    "Did the US promise Gorbachev that NATO would not expand east?",
    "Is the US testing biological weapons in labs in Ukraine?",
    "Do vaccines cause autism in children?",
]

_EXTRA_STIJL = """
  input#vraag {
    width: 100%; font: inherit; padding: .7rem .8rem; min-height: 2.9rem;
    border: 1px solid var(--rand); border-radius: 10px;
    background: var(--kaart); color: inherit;
  }
  #antwoord { border: 1px solid var(--rand); border-radius: 12px; background: var(--kaart);
              padding: 1rem 1.15rem .4rem; margin-top: .6rem; }
  #antwoord > .uitleg { margin: 0 0 .6rem; }
  .tellingen { font-family: var(--mono); font-size: .78rem; letter-spacing: .03em; color: var(--groen);
               font-weight: 700; margin: 0 0 .6rem; }
  .tally { margin: 0 0 .8rem; padding: .6rem .75rem; border-left: 3px solid var(--groen); background: var(--mint);
           border-radius: 0 8px 8px 0; }
  .groep { font-family: var(--mono); font-size: .75rem; letter-spacing: .06em; text-transform: uppercase;
           color: var(--zacht); margin: 1rem 0 .2rem; font-weight: 600; }
  ul.rijen { list-style: none; margin: 0; padding: 0; }
  .rij { border-top: 1px solid var(--rand); }
  .rij summary { list-style: none; cursor: pointer; display: grid; grid-template-columns: auto 1fr;
                 gap: .1rem .75rem; padding: .65rem 1.4rem .65rem .1rem; min-height: 2.75rem; position: relative; }
  .rij summary::-webkit-details-marker { display: none; }
  .rij summary::after { content: "+"; position: absolute; right: .2rem; top: .65rem; color: var(--zacht); }
  .rij details[open] summary::after { content: "-"; }
  .rij .bewering { grid-column: 2; grid-row: 1; font-family: var(--serif); font-size: 1.05rem; line-height: 1.35; }
  .rij .labelchip { grid-column: 1; grid-row: 1; align-self: start; font-size: .76rem; font-weight: 700;
               padding: .1rem .55rem; border-radius: 999px; border: 1.5px dashed var(--rand);
               color: var(--zacht); white-space: nowrap; }
  .rij .labelchip[data-kant="rood"] { border: 1.5px solid #9c3b2e; color: #9c3b2e; }
  .rij .labelchip[data-kant="groen"] { border: 1.5px solid var(--groen); color: var(--groen-donker); }
  .rij .labelchip[data-kant="midden"], .rij .labelchip[data-kant="omstreden"] { border: 1.5px solid #8a6d1f; color: #8a6d1f; }
  .rij .rijmeta, .rij .eigen, .rij .vertaling { grid-column: 2; margin: 0; font-size: .85rem; color: var(--zacht); }
  .rij .eigen { color: var(--inkt); }
  .rij details > .bronnen, .rij details > .voet { margin-left: .1rem; }
  .vert { color: var(--zacht); }
  .leeg h3 { margin: 0 0 .3rem; font-size: 1.2rem; }
  .tip { border: 1px solid var(--rand); border-radius: 10px; padding: .6rem .8rem; margin: .8rem 0; }
  .tip summary { cursor: pointer; font-weight: 650; min-height: 2.75rem; display: flex; align-items: center; }
  .tiplijst { margin: .3rem 0; padding-left: 1.1rem; }
  .tiplijst li { margin: .2rem 0; }
  .klein { font-size: .82rem; color: var(--zacht); }
  .voet { display: flex; flex-wrap: wrap; justify-content: space-between;
          align-items: center; gap: .5rem; margin: .4rem 0 .8rem;
          color: var(--zacht); font-size: .85rem; }
  .meting { color: var(--zacht); font-size: .9rem; }
  @media (prefers-color-scheme: dark) {
    .rij .labelchip[data-kant="rood"] { border-color: #f0a08f; color: #f0a08f; }
    .rij .labelchip[data-kant="midden"], .rij .labelchip[data-kant="omstreden"] { border-color: #e0c26a; color: #e0c26a; }
  }
  @media (max-width: 520px) {
    .rij summary { grid-template-columns: 1fr; }
    .rij .labelchip { grid-column: 1; grid-row: 2; justify-self: start; }
    .rij .bewering, .rij .rijmeta, .rij .eigen, .rij .vertaling { grid-column: 1; }
  }
"""

ASK_PAGINA = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Ask a question | Factiz</title>
__APP_HEAD__
<style>
__STIJL____EXTRA_STIJL__</style>
</head>
<body>
__APP_KOP__
<main id="main">
__BAND__
<div class="baan app">
<p class="uitleg">Your question is not stored. It is compared with the index
and forgotten.</p>
<p class="statregel" id="statistiek" hidden></p>

<form id="formulier">
  <label for="vraag">Your question</label>
  <input id="vraag" name="vraag" type="text" autocomplete="off"
         placeholder="Did corona escape from a lab in Wuhan?">
  <button type="submit">Ask</button>
</form>

<div class="chips" id="chips">
  <span>Try one:</span>
  __VOORBEELDEN__
</div>

<h2>Checked claims</h2>
<div id="antwoord"><p class="uitleg">Nothing asked yet.</p></div>

<div id="betwisting" hidden>
  <h3>Is this result wrong?</h3>
  <p class="uitleg" id="betwisting-over"></p>
  <label for="betwistingstekst">What is wrong?</label>
  <textarea id="betwistingstekst"
            placeholder="Describe what this result gets wrong, or which check is missing"></textarea>

  <div class="toestemming">
    <input type="checkbox" id="toestemming">
    <div>
      <label for="toestemming">Store my question, for error analysis</label>
      <p class="uitleg">
        <strong>Without</strong> this checkbox we store only a fingerprint (a
        row of numbers capturing the meaning of your question) plus your note
        and the disputed result. Your question cannot simply be read back from
        those numbers, but it is not irreversible encryption either.
        <strong>With</strong> the checkbox we additionally store the question
        itself, for __BEWAARTERMIJN__ days, solely to investigate this error.
        You receive a key to have it deleted earlier.
      </p>
    </div>
  </div>

  <p class="actie"><button type="button" id="verstuur-betwisting">Send</button></p>
</div>

<h2>How often it finds the right claim</h2>
<p class="meting">Measured on __VRAGEN__ test questions about claims that keep
coming back, written before we ran them: __GETOOND_JUIST__ show the claim we
expected as the first result, __ANDERE__ show a related check instead, and
__NIETS__ show nothing. On __STILLEVRAGEN__ questions about things nobody
fact-checks, it showed __STILTE_VALS__ results. On __WEBTEKST__ pieces of
ordinary web text, it showed __WEBTEKST_VALS__ wrong result.</p>

<details class="dev">
  <summary>For developers: the raw response of <code>POST /ask</code></summary>
  <pre id="respons">Nothing asked yet.</pre>
</details>

</div>
</main>
__APP_VOET__

<script>
const formulier = document.getElementById('formulier');
const vraagveld = document.getElementById('vraag');
const antwoord = document.getElementById('antwoord');
const uitvoer = document.getElementById('respons');
const betwisting = document.getElementById('betwisting');
const betwistingOver = document.getElementById('betwisting-over');
const betwistingstekst = document.getElementById('betwistingstekst');
const toestemming = document.getElementById('toestemming');

__LABEL_JS__
// Eén element, met tekst als tekst: nooit een HTML-string (zie de docstring).
function el(tag, klasse) {
  const knoop = document.createElement(tag);
  if (klasse) knoop.className = klasse;
  for (let i = 2; i < arguments.length; i++) {
    const kind = arguments[i];
    if (kind === null || kind === undefined || kind === '') continue;
    knoop.append(typeof kind === 'string' ? document.createTextNode(kind) : kind);
  }
  return knoop;
}

// Een href krijgt alleen een echt webadres (#17.5).
function link(url, tekst, alleen) {
  const adres = String(url === null || url === undefined ? '' : url).trim();
  if (!(alleen || /^https?:\\/\\//i).test(adres)) return el('span', 'bron-zonder-link', adres);
  const a = el('a', '', tekst);
  a.href = adres;
  a.rel = 'noopener noreferrer';
  return a;
}

// Bonnetjes die blijven (#25.9): alleen "offline" krijgt een regel.
function linkstand(stand) {
  if (!stand || stand.status !== 'offline') return null;
  const regel = el('span', 'linkstand', 'Source offline since at least '
    + String(stand.offline_since || '') + '. ');
  if (/^https:\\/\\/web\\.archive\\.org\\//i.test(String(stand.archive_url || ''))) {
    regel.append(link(stand.archive_url, 'Archived copy', /^https:\\/\\/web\\.archive\\.org\\//i));
    if (stand.archived_on) regel.append(' from ' + String(stand.archived_on));
  } else {
    regel.append('No archived copy found.');
  }
  return regel;
}

function taalnaam(code) {
  try {
    return new Intl.DisplayNames(['en'], { type: 'language' }).of(String(code)) || String(code);
  } catch (fout) {
    return String(code);
  }
}

function jarenVan(checks) {
  const jaren = checks.map(function (c) { return String(c.review_date || '').slice(0, 4); })
    .filter(function (j) { return /^\\d{4}$/.test(j); }).sort();
  if (!jaren.length) return '';
  return jaren[0] === jaren[jaren.length - 1] ? jaren[0] : jaren[0] + '-' + jaren[jaren.length - 1];
}

// De bonnetjes van nieuw naar oud, zonder datum achteraan (D2), zoals de demo.
function bonnetjesLijst(checks) {
  const lijst = el('ol', 'bronnen');
  checks.slice().sort(function (a, b) {
    return String(b.review_date || '').localeCompare(String(a.review_date || ''));
  }).forEach(function (check) {
    const oordeel = el('span', 'oordeel', String(check.verdict_original || '').trim());
    if (betekenisVan(check)) oordeel.append(el('span', 'vert', ' (' + betekenisVan(check) + ')'));
    lijst.append(el('li', '',
      el('span', 'uitgever', String(check.publisher || '')),
      oordeel,
      el('span', 'meta', (check.review_date ? String(check.review_date) : 'no date') + ' · '
        + String(check.language || '')),
      link(check.url, 'source'),
      linkstand(check.link)));
  });
  return lijst;
}

// Een check zonder oordeel spreekt in haar eigen woorden (route 1 van B31).
function eigenWoorden(checks) {
  const check = checks.find(function (c) {
    return c.verdict_normalized === 'onbekend' && String(c.verdict_original || '').trim().length > 12;
  });
  return check ? el('p', 'eigen', 'In their words, ' + String(check.publisher || '') + ': "'
    + String(check.verdict_original).trim() + '"') : null;
}

// Eén regel per bewering, die openklapt naar de bonnetjes (DESIGN §4e). In de
// leesvolgorde eerst de bewering, dan het label: het oordeel hoort bij de
// bewering, nooit bij de vraag (B25). De chip staat er alleen visueel voor.
function rijVoor(rij, index) {
  const claim = rij.claim || {};
  const bewijs = rij.evidence || {};
  const checks = bewijs.checks || [];
  const vertaling = rij.translation;
  const bewering = el('span', 'bewering', '"' + String(vertaling ? vertaling.text : claim.text || '') + '"');
  const inTijd = klasseInTijd(checks);
  const chip = el('span', 'labelchip', WOORDEN[inTijd.klasse] || 'Fact-checked');
  chip.dataset.kant = POSITIE[inTijd.klasse] || 'geen';
  const uitgevers = Number(bewijs.publisher_count) || checks.length;
  const jaren = jarenVan(checks);
  const kop = el('summary', '', bewering, chip,
    el('span', 'rijmeta', uitgevers + ' ' + enkelvoud(uitgevers, 'newsroom', 'newsrooms')
      + (jaren ? ' · ' + jaren : '') + eerderRegel(inTijd.eerder)),
    eigenWoorden(checks));
  if (vertaling) {
    const origineel = el('span', '', String(claim.text || ''));
    origineel.lang = String(vertaling.from_language);
    kop.append(el('p', 'vertaling', 'Machine translation from ' + taalnaam(vertaling.from_language)
      + '. Original: ', origineel));
  }
  const knop = el('button', '', 'Wrong? Tell us');
  knop.type = 'button';
  knop.dataset.betwist = String(index);
  const rijElement = el('li', 'rij', el('details', '', kop, bonnetjesLijst(checks),
    el('p', 'voet', el('span', '', 'The sources are the verdict.'), knop)));
  rijElement.dataset.cat = String(rij.category);
  return rijElement;
}

// De regel bovenaan: alleen tellingen, geen oordeel.
function tellingenVoor(t) {
  if (!t) return null;
  const jaren = t.first_year ? ' · ' + t.first_year + (t.last_year !== t.first_year ? '-' + t.last_year : '') : '';
  return el('p', 'tellingen', t.claims + ' checked ' + enkelvoud(t.claims, 'claim', 'claims')
    + ' close to your question · ' + t.newsrooms + ' ' + enkelvoud(t.newsrooms, 'newsroom', 'newsrooms')
    + ' · ' + t.languages + ' ' + enkelvoud(t.languages, 'language', 'languages') + jaren);
}

// Variant B (PO 2026-10-15): de oordelen samengevat, over de beweringen en
// nooit over de vraag; bij tegengestelde beweringen de reden waarom niet.
function samenvattingVoor(s, rijen) {
  if (!s) return null;
  if (s.kind === 'opposite') {
    const ander = rijen.find(function (r) { return r.claim && r.claim.id === s.claim_id; }) || {};
    const tekst = ander.translation ? ander.translation.text : (ander.claim || {}).text;
    return el('p', 'tally', 'No summary: these claims do not all say the same thing. "' + String(tekst || '')
      + '" says the opposite, and was rated ' + (BETEKENIS[s.verdict_class] || 'without a rating') + '.');
  }
  let tekst = s.kind === 'agree'
    ? (s.rated === 1 ? 'The one rated check found these claims ' : 'All ' + s.rated + ' rated checks found these claims ')
      + s.side + '.'
    : 'The rated checks do not agree: ' + Object.keys(s.counts).map(function (k) {
      return s.counts[k] + ' ' + k;
    }).join(', ') + '.';
  (s.other || []).forEach(function (o) {
    tekst += ' ' + o.count + ' ' + enkelvoud(o.count, 'check says', 'checks say') + ' ' + o.verdict + '.';
  });
  if (s.no_rating) {
    tekst += ' ' + s.no_rating.count + ' ' + enkelvoud(s.no_rating.count, 'check gives', 'checks give')
      + ' no rating; ' + s.no_rating.publisher + ': "' + s.no_rating.words + '"';
  }
  return el('p', 'tally', tekst);
}

function groepVoor(kop, rijen, alle) {
  if (!rijen.length) return [];
  return [el('h3', 'groep', kop), el('ul', 'rijen', ...rijen.map(function (r) { return rijVoor(r, alle.indexOf(r)); }))];
}

// Stilte boven gissen (DESIGN §4e): niets boven de verwantdrempel, dan zegt
// de pagina dat, met de reden, en een volgende stap: redacties die tips
// aannemen, in de taal van de vraag, uit de lijst van WhatsApp.
function leegVoor(reden, lijnen, bron) {
  const vreemd = reden === 'out_of_scope';
  const knop = el('button', '', 'Wrong? Tell us');
  knop.type = 'button';
  knop.dataset.betwist = 'leeg';
  const blok = el('div', 'leeg',
    el('h3', '', vreemd ? 'This language is not in the memory yet' : 'No checked claim close enough'),
    el('p', '', vreemd
      ? 'We searched across languages and found nothing close enough. We hold no '
        + 'checks in this language, so finding nothing says little here.'
      : 'Nothing in the memory is close enough to this question to show.'),
    el('p', '', 'That does not mean the answer is yes or no, only that no newsroom checked it, '
      + 'or not in a way we hold. Most new rumours are not checked yet.'));
  if (lijnen && lijnen.length) {
    const lijst = el('ul', 'tiplijst', ...lijnen.map(function (l) {
      const item = el('li', '', el('strong', '', String(l.organization)), ' (' + String(l.country) + ') ');
      (l.links || []).forEach(function (adres, i) {
        item.append(link(adres, String((l.numbers || [])[i] || adres), /^https:\\/\\/wa\\.me\\/\\d+$/), ' ');
      });
      return item;
    }));
    const herkomst = el('p', 'klein', 'From the ', link(bron && bron.url, 'WhatsApp list of IFCN fact-checkers'),
      ', as of ' + String((bron && bron.recorded) || '') + '. We do not know which newsroom will check it.');
    const open = el('details', 'tip', el('summary', '', 'Send it to a fact-checker: ' + lijnen.length + ' '
      + enkelvoud(lijnen.length, 'newsroom', 'newsrooms') + ' on WhatsApp in your language'), lijst, herkomst);
    if (lijnen.length <= 6) open.open = true;
    blok.append(open);
  }
  blok.append(el('p', 'voet', el('span', '', 'Know a fact-check we missed?'), knop));
  return blok;
}

function melding(kop) {
  const blok = el('div', 'leeg', el('h3', '', kop));
  for (let i = 1; i < arguments.length; i++) blok.append(el('p', '', arguments[i]));
  return blok;
}

// Elke foutstaat een eigen tekst, nooit terugvallen op "niets gevonden" (D7).
const FOUT = {
  413: 'This question is too long. Nothing was searched.',
  422: 'There is no question to search. Type one and try again.',
  429: 'Too many requests arrived from this address in a short time. Wait '
    + 'half a minute; nothing was searched and nothing was stored.',
  503: 'The index was built with a different model version than this '
    + 'resolver expects. It refuses to search rather than guess.',
};

let laatste = null;
let laatsteVraag = '';
let betwist = null;

function verbergBetwisting() {
  betwisting.hidden = true;
  betwist = null;
}

antwoord.addEventListener('click', function (gebeurtenis) {
  const knop = gebeurtenis.target.closest('button[data-betwist]');
  if (!knop || !laatste) return;
  const sleutel = knop.dataset.betwist;
  const rij = sleutel === 'leeg' ? null : (laatste.results || [])[Number(sleutel)];
  betwist = {
    category: rij ? rij.category : 'none',
    claim_id: rij && rij.claim ? rij.claim.id : null,
  };
  betwistingOver.textContent = rij
    ? 'About the claim: "' + String(rij.claim.text || '') + '"'
    : 'About the answer that nothing was found.';
  betwistingstekst.value = '';
  toestemming.checked = false;
  betwisting.hidden = false;
  betwistingstekst.focus();
});

document.getElementById('verstuur-betwisting').addEventListener('click', async () => {
  const toelichting = betwistingstekst.value.trim();
  if (!toelichting || !betwist) {
    betwistingstekst.focus();
    return;
  }
  try {
    const respons = await fetch('/dispute', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        text: laatsteVraag,
        disputed_category: betwist.category,
        dispute_text: toelichting,
        claim_id: betwist.claim_id,
        consent_to_store_artifact: toestemming.checked,
      }),
    });
    const data = await respons.json();
    if (!respons.ok) {
      betwistingOver.textContent = 'Not recorded. Server: ' + String((data && data.detail) || respons.status);
      return;
    }
    const bedankt = melding('Thank you, recorded (#' + String(data.dispute_id) + ')',
      'Stored: ' + data.stored_fields.map(String).join(', ') + '.');
    if (data.deletion_key) {
      bedankt.append(el('p', '', 'Your deletion key. Save it; it is shown only once. It lets you '
        + 'have your question deleted before ' + String(data.artifact_expires_at || '').slice(0, 10) + '.',
        el('code', 'sleutel', String(data.deletion_key))));
    } else {
      bedankt.append(el('p', '', 'Your question itself was not stored, so no key is needed.'));
    }
    antwoord.prepend(bedankt);
    verbergBetwisting();
  } catch (fout) {
    betwistingOver.textContent = 'The server was unreachable. Nothing was recorded.';
  }
});

async function laadStatistiek() {
  try {
    const respons = await fetch('/.well-known/doublecheck');
    if (!respons.ok) return;
    const scope = (await respons.json()).scope || {};
    if (!scope.claims) return;
    // `scope.claims` telt claims, geen checks: het woord moet kloppen.
    const regel = document.getElementById('statistiek');
    regel.textContent = 'Ready to search ' + scope.claims.toLocaleString('en-US')
      + ' checked claims in ' + (scope.languages || []).length + ' languages';
    regel.hidden = false;
  } catch (fout) {
    // Zonder statistiek werkt de pagina gewoon; de regel blijft verborgen.
  }
}

// Eén teller en één antwoord tegelijk (PO 2026-10-16: twee keer op Ask gaf
// twee tellers). Een nieuwe vraag stopt de oude teller, en een antwoord dat
// binnenkomt na een nieuwere vraag wordt weggelegd. De knop staat uit zolang
// er gezocht wordt; zonder werkende knop verstuurt Enter ook niets.
let klok = null;
let volgnummer = 0;
const knop = formulier.querySelector('button[type="submit"]');

function stopKlok() {
  if (klok !== null) {
    clearInterval(klok);
    klok = null;
  }
}

async function stel(vraag) {
  const mijn = ++volgnummer;
  laatsteVraag = vraag;
  laatste = null;
  verbergBetwisting();
  const start = Date.now();
  const teken = function () {
    antwoord.replaceChildren(melding('Searching',
      'Computing a fingerprint of the question and searching the index. '
      + Math.round((Date.now() - start) / 1000) + ' seconds elapsed. The first '
      + 'request after startup loads the language model and takes longer.'));
  };
  stopKlok();
  teken();
  klok = setInterval(teken, 1000);
  knop.disabled = true;
  knop.textContent = 'Searching...';
  antwoord.setAttribute('aria-busy', 'true');
  // Op een klein scherm staat het antwoord onder de vouw: breng het in beeld.
  if (antwoord.getBoundingClientRect().top > window.innerHeight * 0.75) {
    antwoord.scrollIntoView({ block: 'start',
      behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth' });
  }
  uitvoer.textContent = 'Working...';
  try {
    const respons = await fetch('/ask', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question: vraag }),
    });
    const data = await respons.json();
    if (mijn !== volgnummer) return;
    stopKlok();
    uitvoer.textContent = respons.status + ' ' + respons.statusText + '\\n\\n'
      + JSON.stringify(data, null, 2);
    if (!respons.ok) {
      antwoord.replaceChildren(melding('No answer this time',
        FOUT[respons.status] || 'The server returned status ' + respons.status + '. Nothing was searched.'));
      return;
    }
    laatste = data;
    const rijen = data.results || [];
    if (!rijen.length) {
      antwoord.replaceChildren(leegVoor(data.reason, data.tiplines, data.tiplines_source));
      return;
    }
    const dichtbij = rijen.filter(function (r) { return r.category === 'matched'; });
    const verwant = rijen.filter(function (r) { return r.category === 'related'; });
    antwoord.replaceChildren(...[tellingenVoor(data.totals), samenvattingVoor(data.summary, rijen)]
      .filter(Boolean)
      .concat(groepVoor('Close to your question', dichtbij, rijen))
      .concat(groepVoor('Related to your question', verwant, rijen)));
  } catch (fout) {
    if (mijn !== volgnummer) return;
    stopKlok();
    antwoord.replaceChildren(melding('Server unreachable',
      'The question did not arrive. This says nothing about any claim.'));
  } finally {
    if (mijn === volgnummer) {
      knop.disabled = false;
      knop.textContent = 'Ask';
      antwoord.removeAttribute('aria-busy');
    }
  }
}

formulier.addEventListener('submit', function (gebeurtenis) {
  gebeurtenis.preventDefault();
  const vraag = vraagveld.value.trim();
  if (!vraag) {
    vraagveld.focus();
    return;
  }
  stel(vraag);
});

document.getElementById('chips').addEventListener('click', function (gebeurtenis) {
  const chip = gebeurtenis.target.closest('button[data-vraag]');
  if (!chip) return;
  vraagveld.value = chip.dataset.vraag;
  stel(vraagveld.value);
});

laadStatistiek();
</script>
</body>
</html>
"""

# De voorbeelden landen één keer, bij import, en uitsluitend ge-escaped.
_VOORBEELD_KNOPPEN = "\n  ".join(
    '<button type="button" class="chip" data-vraag="{v}">{t}</button>'.format(
        v=html.escape(vraag, quote=True), t=html.escape(vraag)
    )
    for vraag in VOORBEELDEN
)
_METING = {f"__{sleutel.upper()}__": f"{waarde:,}" for sleutel, waarde in METING.items()}

ASK_PAGINA = (ASK_PAGINA.replace("__STIJL__", GEDEELDE_STIJL + STIJL).replace("__APP_HEAD__", APP_HEAD).replace("__EXTRA_STIJL__", _EXTRA_STIJL)
              .replace("__LABEL_JS__", LABEL_JS).replace("__VOORBEELDEN__", _VOORBEELD_KNOPPEN)
              .replace("__APP_KOP__", APP_KOP["/ask"]).replace("__APP_VOET__", APP_VOET)
              .replace("__BAND__", band("Ask a question", "Ask what fact-checkers found",
                                        "Type a question in your own words. Factiz shows the checked claims closest "
                                        "to it, what the newsrooms found, and their articles. It does not answer the "
                                        "question itself: each verdict belongs to the claim above it.")))
for _plek, _waarde in _METING.items():
    ASK_PAGINA = ASK_PAGINA.replace(_plek, _waarde)
