// Schrijft de tekeningen per thema en per dossier uit voor het platform (PLAN #34.2aq, SPECS E9.S23 AC4): dezelfde
// gegevens als de site (`src/lib/platen.js`), als JSON naast de beelden in `factiz_site/static/`, met de herkomst erbij.
// `--controleer` schrijft niets en eindigt met 1 als het bestand niet meer bij de bron past.
import { readFileSync, writeFileSync } from 'node:fs';
import { PLATEN, UITSNEDE } from '../src/lib/platen.js';

// de familie per thema uit de tegel en de kleur per familie uit de lichte tokens van de site: geen tweede lijst
// (`tests/test_site_themakleur.py` houdt de vorm van beide vast)
const tegel = readFileSync(new URL('../src/components/site/ThemaTegel.jsx', import.meta.url), 'utf8');
const css = readFileSync(new URL('../src/styles/site.css', import.meta.url), 'utf8');
const FAMILIE = Object.fromEntries([...tegel.matchAll(/^\s+([a-z]+): \{ familie: '([a-z]+)', icoon: '[a-z-]+' \}/gm)].map((m) => [m[1], m[2]]));
const licht = css.slice(css.indexOf('.fz {'), css.indexOf('@media (prefers-color-scheme: dark)'));
const KLEUR = Object.fromEntries([...licht.matchAll(/--f-([a-z]+): (#[0-9A-Fa-f]{6});/g)].filter((m) => m[1] !== 'icoon').map((m) => [m[1], m[2]]));

const UIT = new URL('../../factiz_site/static/platen.json', import.meta.url);
const inhoud = JSON.stringify({
  _meta: {
    toelichting: 'De tekeningen per thema en per dossier (PLAN #34.2ap, #34.2aq), uitgeschreven uit site/src/lib/platen.js met '
      + '`npm --prefix site run platen`; eigen werk van Factiz. Het platform tekent ze met Pillow op het deelplaatje.',
  },
  uitsnede: UITSNEDE,
  familie: FAMILIE,
  kleur: KLEUR,
  platen: PLATEN,
}, null, 1) + '\n';

if (process.argv.includes('--controleer')) {
  let nu = '';
  try { nu = readFileSync(UIT, 'utf8'); } catch { /* ontbreekt */ }
  if (nu !== inhoud) {
    console.error('factiz_site/static/platen.json past niet bij site/src/lib/platen.js: draai npm --prefix site run platen');
    process.exit(1);
  }
} else {
  writeFileSync(UIT, inhoud);
  console.log(`${Object.keys(PLATEN).length} tekeningen naar factiz_site/static/platen.json`);
}
