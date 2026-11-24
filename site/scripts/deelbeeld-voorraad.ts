// De voorraad van het deelplaatje in TypeScript (B80, PLAN #34.2bo stap 5): wat de tekening nodig heeft, eenmaal
// klaargezet, zodat een Worker per verzoek alleen bestanden leest en niets omzet.
//   node scripts/deelbeeld-voorraad.ts [<map>]        (standaard ../data/deelbeeld, buiten git)
// - de lettertypen van het platform (`factiz_site/fonts/`, dezelfde bestanden als Pillow) van WOFF2 naar TTF, ongewijzigd
//   van inhoud: HarfBuzz leest geen WOFF2. Elk deelbestand blijft apart, zodat een stuk tekst hetzelfde bestand krijgt als
//   in Python en een verzoek alleen de stukken laadt die het nodig heeft;
// - per veld (`static/beeld/*-band.webp` en `delen.jpg`) de band van 1200 bij 228, verkleind en uitgesneden zoals
//   `deelbeeld._band` dat doet, als JPEG: resvg leest geen WebP;
// - het woordmerk, en `voorraad.json` met per lettertype de tekens die het dekt, in de volgorde van `deelbeeld._bereik`;
//   die van Chinees, Japans en Koreaans apart in `bereik/<pakket>.json`: groot, en alleen nodig voor een teken dat geen
//   ander lettertype heeft. Een reeks staat er kort in: het begin in grondtal 36, en `+` met de lengte min één;
// - `teken.wasm`, het kleine wasm-blok waarmee HarfBuzz de omtrek van een teken teruggeeft (`deelbeeld-hb.ts`), voor een
//   Worker die het als module importeert.
// Opnieuw draaien na `python -m factiz_site.lettertypen` of `python -m doublecheck.velden platform`.
import { createHash } from 'node:crypto';
import { copyFileSync, existsSync, mkdirSync, readdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import sharp from 'sharp';
import decompress from 'wawoff2/decompress.js';
import { TEKEN_WASM } from '../src/platform/deelbeeld-hb.ts';

const HIER = dirname(fileURLToPath(import.meta.url));
const FACTIZ = join(HIER, '..', '..', 'factiz_site');
const FONTS = join(FACTIZ, 'fonts');
const BEELD = join(FACTIZ, 'static', 'beeld');
const UIT = process.argv[2] ?? join(HIER, '..', '..', 'data', 'deelbeeld');

// gelijk aan `deelbeeld.LETTERTYPES` en `deelbeeld.NOTO`
const GEIST = ['latin', 'latin-ext', 'cyrillic', 'cyrillic-ext', 'vietnamese'].map((d) => `geist-${d}-wght-normal.woff2`);
const NOTO = ['noto-sans', 'noto-sans-arabic', 'noto-sans-hebrew', 'noto-sans-devanagari', 'noto-sans-bengali',
  'noto-sans-tamil', 'noto-sans-telugu', 'noto-sans-malayalam', 'noto-sans-kannada', 'noto-sans-gujarati',
  'noto-sans-gurmukhi', 'noto-sans-sinhala', 'noto-sans-thai', 'noto-sans-khmer', 'noto-sans-ethiopic',
  'noto-sans-sc', 'noto-sans-tc', 'noto-sans-jp', 'noto-sans-kr'];
const CJK = ['noto-sans-sc', 'noto-sans-tc', 'noto-sans-jp', 'noto-sans-kr'];
const BREED = 1200;
const BAND = 228;

function reeksen(tekst: string): [number, number][] {
  return tekst.split(',').map((deel) => {
    const [a, b] = deel.trim().toUpperCase().replace('U+', '').split('-');
    return [parseInt(a, 16), parseInt(b || a, 16)];
  });
}

// per bestand de tekens uit het stijlblad, zoals `deelbeeld._bereik`
function bereik(): [string, [number, number][]][] {
  const uit: [string, [number, number][]][] = [];
  const css = readFileSync(join(FONTS, 'geist.css'), 'utf8');
  for (const bestand of GEIST) {
    const blok = css.match(new RegExp(`url\\(\\./files/${bestand.replace(/[.]/g, '\\.')}\\)[^}]*?unicode-range: ([^;]+);`, 's'));
    if (!blok) throw new Error(`geen reeks voor ${bestand}`);
    uit.push([bestand, reeksen(blok[1])]);
  }
  for (const pakket of NOTO) {
    const stijl = join(FONTS, 'noto', pakket, 'index.css');
    if (!existsSync(stijl)) continue;
    for (const m of readFileSync(stijl, 'utf8').matchAll(/url\(\.\/files\/([^)]+\.woff2)\)[^}]*?unicode-range: ([^;]+);/gs)) {
      uit.push([`noto/${pakket}/files/${m[1]}`, reeksen(m[2])]);
    }
  }
  return uit;
}

const ttf = (bestand: string) => bestand.replace(/\.woff2$/, '.ttf');
const kort = (r: [number, number][]) => r.map(([a, b]) => (a === b ? a.toString(36) : `${a.toString(36)}+${(b - a).toString(36)}`)).join(',');
const pakket = (bestand: string) => (bestand.startsWith('noto/') ? bestand.split('/')[1] : '');

if (existsSync(UIT)) rmSync(UIT, { recursive: true });
mkdirSync(join(UIT, 'beeld'), { recursive: true });
mkdirSync(join(UIT, 'bereik'), { recursive: true });
const vingerafdruk = createHash('sha256');
const lettertypen = bereik();
let bytes = 0;
for (const [bestand] of lettertypen) {
  const bron = readFileSync(join(FONTS, bestand));
  vingerafdruk.update(bestand).update(bron);
  const doel = join(UIT, 'lettertypen', ttf(bestand));
  mkdirSync(dirname(doel), { recursive: true });
  const inhoud = await decompress(bron);
  writeFileSync(doel, inhoud);
  bytes += inhoud.length;
}

// de band zoals `_band` haar uitsnijdt: zo groot dat ze 1200 bij 228 vult, dan het midden
const banden: string[] = [];
const velden = readdirSync(BEELD).filter((n) => n.endsWith('-band.webp')).map((n) => [n, n.slice(0, -'-band.webp'.length)]);
for (const [naam, sleutel] of [...velden, ['delen.jpg', 'delen']]) {
  const bron = readFileSync(join(BEELD, naam));
  vingerafdruk.update(naam).update(bron);
  const { width: w = 0, height: h = 0 } = await sharp(bron).metadata();
  const schaal = Math.max(BREED / w, BAND / h);
  const [nw, nh] = [Math.round(w * schaal), Math.round(h * schaal)];
  const links = Math.floor((nw - BREED) / 2);
  const boven = Math.floor((nh - BAND) / 2);
  let beeld = sharp(bron).removeAlpha();
  if (nw !== w || nh !== h) beeld = beeld.resize(nw, nh, { kernel: 'lanczos3', fit: 'fill' });
  // eerst verkleinen, dan uitsnijden: een tweede sharp, want sharp snijdt anders vóór het verkleinen
  const groot = await beeld.png().toBuffer();
  await sharp(groot).extract({ left: links, top: boven, width: BREED, height: BAND })
    .jpeg({ quality: 95, chromaSubsampling: '4:4:4' }).toFile(join(UIT, 'beeld', `${sleutel}.jpg`));
  banden.push(sleutel);
}
copyFileSync(join(FACTIZ, 'static', 'merk', 'woordmerk-deel.png'), join(UIT, 'woordmerk-deel.png'));
vingerafdruk.update(readFileSync(join(UIT, 'woordmerk-deel.png')));
writeFileSync(join(UIT, 'teken.wasm'), TEKEN_WASM);

for (const p of CJK) {
  writeFileSync(join(UIT, 'bereik', `${p}.json`),
    JSON.stringify(lettertypen.filter(([b]) => pakket(b) === p).map(([b, r]) => [ttf(b), kort(r)])));
}
writeFileSync(join(UIT, 'voorraad.json'), JSON.stringify({
  _meta: { toelichting: 'De voorraad van het deelplaatje (PLAN #34.2bo stap 5), gemaakt met `node scripts/deelbeeld-voorraad.ts`.',
           vingerafdruk: vingerafdruk.digest('hex') },
  lettertypen: lettertypen.filter(([b]) => !CJK.includes(pakket(b))).map(([b, r]) => [ttf(b), kort(r)]),
  cjk: CJK.filter((p) => lettertypen.some(([b]) => pakket(b) === p)),
  banden: banden.sort(),
}));
console.log(`${lettertypen.length} lettertypen (${(bytes / 1e6).toFixed(1)} MB), ${banden.length} banden in ${UIT}`);
