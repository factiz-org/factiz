// De lettertypen van de site (PLAN #34.2bs, SPECS E9.S28 AC1, B78): uit de pakketten van Fontsource alleen de delen die de
// browser laadt, in één bestand, `src/styles/lettertypen.css`. Geist, Geist Mono, Newsreader, Noto Sans en Noto Serif
// voor het Latijn, Cyrillisch, Grieks en Vietnamees; Noto per schrift alleen voor de schriften van de sitetalen (Arabisch,
// Devanagari, Chinees, Japans), en daarvan alleen de delen van dat schrift. Een Latijns, wiskundig of symbooldeel van zo'n
// lettertype haalde de browser op voor een teken dat Geist mist: 0,39 MB op de start. Elk ander schrift staat in de
// letters van het toestel. Het deelplaatje tekent alles in Noto, uit dezelfde pakketten, die dus blijven.
//
//   npm --prefix site run lettertypen            na een nieuwe versie van een pakket
//   node scripts/lettertypen.mjs --toets         weigert als het bestand niet meer past (tests/test_site_lettertypes.py)
import { readFileSync, writeFileSync, existsSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const SITE = join(dirname(fileURLToPath(import.meta.url)), '..');
const UIT = join(SITE, 'src', 'styles', 'lettertypen.css');
const LATIJN = /^(latin|latin-ext|cyrillic|cyrillic-ext|greek|greek-ext|vietnamese)$/;
const GENUMMERD = /^\[\d+\]$/;      // Chinees en Japans: de tekens in honderd delen ([0] tot [119]), elk met zijn eigen unicode-range
const ALLES = /^.+$/;

// [pakket, stijlblad, delen die mee mogen]
const PAKKETTEN = [
  ['geist', 'index.css', ALLES],
  ['geist-mono', 'index.css', ALLES],
  ['noto-sans', 'index.css', LATIJN],              // niet zijn Devanagari: dat komt uit Noto Sans Devanagari, zoals op het deelplaatje
  ['noto-sans-arabic', 'index.css', /^arabic$/],
  ['noto-sans-devanagari', 'index.css', /^devanagari$/],
  ['noto-sans-sc', 'index.css', GENUMMERD],
  ['noto-sans-tc', 'index.css', GENUMMERD],
  ['noto-sans-jp', 'index.css', GENUMMERD],
  ['newsreader', 'opsz.css', ALLES],               // met de as voor optische grootte
  ['noto-serif', 'index.css', LATIJN],
  ['noto-naskh-arabic', 'index.css', /^arabic$/],
  ['noto-serif-devanagari', 'index.css', /^devanagari$/],
  ['noto-serif-sc', 'index.css', GENUMMERD],
  ['noto-serif-tc', 'index.css', GENUMMERD],
  ['noto-serif-jp', 'index.css', GENUMMERD],
];

function vlakken(pakket, blad, mag) {
  const pad = join(SITE, 'node_modules', '@fontsource-variable', pakket, blad);
  const css = readFileSync(pad, 'utf8');
  const uit = [];
  let gezien = 0;
  for (const m of css.matchAll(/\/\* ([a-z0-9[\]-]+) \*\/\n@font-face \{\n([\s\S]*?)\n\}/g)) {
    gezien++;
    const [, naam, lijf] = m;
    const deel = naam.match(new RegExp(`^${pakket}-(.+)-(?:wght|opsz)-normal$`))?.[1];
    if (!deel) throw new Error(`${pakket}: onbekende naam ${naam}`);
    if (!mag.test(deel)) continue;
    if (!lijf.includes('url(./files/')) throw new Error(`${pakket}: ${naam} zonder eigen bestand`);
    uit.push(`/* ${naam} */\n@font-face {\n${lijf.replaceAll('url(./files/', `url(../../node_modules/@fontsource-variable/${pakket}/files/`)}\n}`);
  }
  if (!gezien || !uit.length) throw new Error(`${pakket}: niets gelezen uit ${blad}`);
  return uit;
}

export function maak() {
  const kop = [
    '/* Gemaakt door site/scripts/lettertypen.mjs uit de pakketten van Fontsource (PLAN #34.2bs); niet met de hand bewerken.',
    '   Noto per schrift alleen voor de schriften van de sitetalen, en daarvan alleen de delen van dat schrift; elk ander',
    '   schrift in de letters van het toestel. */',
  ].join('\n');
  return [kop, ...PAKKETTEN.flatMap(([p, b, m]) => vlakken(p, b, m))].join('\n\n') + '\n';
}

const tekst = maak();
if (process.argv.includes('--toets')) {
  if (!existsSync(UIT) || readFileSync(UIT, 'utf8') !== tekst) {
    console.error('src/styles/lettertypen.css past niet meer bij de pakketten: npm --prefix site run lettertypen');
    process.exit(1);
  }
} else {
  writeFileSync(UIT, tekst);
  console.log(`src/styles/lettertypen.css: ${(tekst.match(/@font-face/g) ?? []).length} vlakken uit ${PAKKETTEN.length} pakketten`);
}
