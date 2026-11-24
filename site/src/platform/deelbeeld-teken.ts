// De tekening van het deelplaatje (B80, PLAN #34.2bo stap 5), gelijk aan `factiz_site/deelbeeld.py`: dezelfde maten, kleuren
// en volgorde. Alles wordt één SVG (de band, de sluier, de tekening van het thema, het label, de tekst als paden en het
// woordmerk); resvg maakt er pixels van en jpeg-js een JPEG. Vlakken die Pillow zonder zachte rand tekent (het label, het
// vel achter de tekening) krijgen hier `crispEdges`.
import { Resvg } from '@resvg/resvg-wasm';
import encode from 'jpeg-js/lib/encoder.js';
import platenJson from '../../../factiz_site/static/platen.json' with { type: 'json' };
import type { Zetter } from './deelbeeld-tekst.ts';

export const BREED = 1200;
export const HOOG = 630;
const BAND = 228;                 // de hoogte van de band met het veld
const MARGE = 64;                 // de rand rond de tekst
const MAX_REGELS = 3;             // de bewering: hoogstens zoveel regels
const GROOTTES = [52, 46, 40];    // zo groot als past
const ZIN_GROOTTE = 24;
const LABEL_GROOTTE = 26;
const STEMPEL_HOOGTE = 52;
const OVERMAAT = 3;               // Pillow tekent de tekening zoveel groter: zo dik worden de lijnen
const INKT = '#171717';
const ZACHT = '#5f6461';
const PAPIER = '#fcfcfb';
const KWALITEIT = 86;             // zoals `deelbeeld._jpeg`
// resvg vraagt alleen een beeld met een webadres van buiten (`resolveImage`); dit adres bestaat niet en wordt nooit gehaald
const BEELD = 'https://deelbeeld.invalid/';

// de kleuren van het label zoals op de site (`deelbeeld.LABELKLEUREN`)
type Kleuren = { inkt: string; vlak: string; rand: string; stip: string };
const LABELKLEUREN: Record<string, Kleuren> = {
  onwaar: { inkt: '#7a3600', vlak: '#fbe0c2', rand: '#eeb27a', stip: '#c45f0a' },
  misleidend: { inkt: '#5c5000', vlak: '#fbf7dc', rand: '#e5d98f', stip: '#a38900' },
  deels: { inkt: '#5f5240', vlak: '#f3eee5', rand: '#ddd1bd', stip: '#9c8763' },
  waar: { inkt: '#1d4a8c', vlak: '#e8f0fc', rand: '#bdd1f1', stip: '#3a6fc6' },
  omstreden: { inkt: '#573a8e', vlak: '#f1ecfa', rand: '#d6caef', stip: '#7b58c2' },
  satire: { inkt: '#86306a', vlak: '#fbedf6', rand: '#edc6df', stip: '#b4468c' },
  onbewezen: { inkt: '#474d5c', vlak: '#f0f1f4', rand: '#d1d5dd', stip: '#868d9e' },
};
const GEEN_LABEL: Kleuren = { inkt: '#171717', vlak: '#ffffff', rand: '#d9dbd9', stip: '#8b908d' };
const KLASSE_KLEUR: Record<string, string> = {
  onwaar: 'onwaar', 'onwaar-of-misleidend': 'onwaar', misleidend: 'misleidend', 'deels-waar': 'deels', waar: 'waar',
  omstreden: 'omstreden', satire: 'satire', onbewezen: 'onbewezen',
};

type Vorm = { v: string; x?: number; y?: number; w?: number; h?: number; r?: number; o: number; open?: boolean; d?: string;
  streep?: string | null };
const PLATEN = platenJson as unknown as { familie: Record<string, string>; kleur: Record<string, string>;
  platen: Record<string, Vorm[]> };

// Wat een tekening nodig heeft naast de tekst: de band als JPEG en het woordmerk als PNG, uit de voorraad.
export type Beelden = { band: (naam: string) => Promise<Uint8Array>; merk: Uint8Array; merkMaat: [number, number] };

const g = (n: number) => String(Math.round(n * 1000) / 1000);
// Python rondt een half af naar het even getal (`round`); Pillow rondt de hoeken van een vlak zo af
const rond = (n: number) => { const f = Math.floor(n); const d = n - f; return d > 0.5 || (d === 0.5 && f % 2 === 1) ? f + 1 : f; };

// --- de tekening ---------------------------------------------------------------------------------------------------------

type Punt = [number, number];
const TEKENS = /[MLHVCSZ]|-?(?:\d+\.?\d*|\.\d+)/g;

// Een pad uit de tekeningen (alleen M, L, H, V, C, S en Z, absoluut) als lijnstukken; een kromme in 20 stappen, en Z
// sluit het stuk naar zijn begin (`_pad`).
function pad(d: string): Punt[][] {
  const stukken = d.match(TEKENS) ?? [];
  const lijnen: Punt[][] = [];
  let i = 0;
  let opdracht = '';
  let x = 0;
  let y = 0;
  let vorigeC: Punt | null = null;
  const getal = (k: number) => parseFloat(stukken[k]);
  while (i < stukken.length) {
    if (stukken[i] === 'Z') {
      const stuk = lijnen[lijnen.length - 1];
      [x, y] = stuk[0];
      stuk.push([x, y]); opdracht = ''; vorigeC = null;
      i += 1;
      continue;
    }
    if ('MLHVCS'.includes(stukken[i])) {
      opdracht = stukken[i];
      i += 1;
      continue;
    }
    if (opdracht === 'M') {
      x = getal(i); y = getal(i + 1); i += 2;
      lijnen.push([[x, y]]); opdracht = 'L'; vorigeC = null;
    } else if (opdracht === 'L') {
      x = getal(i); y = getal(i + 1); i += 2;
      lijnen[lijnen.length - 1].push([x, y]); vorigeC = null;
    } else if (opdracht === 'H') {
      x = getal(i); i += 1; lijnen[lijnen.length - 1].push([x, y]); vorigeC = null;
    } else if (opdracht === 'V') {
      y = getal(i); i += 1; lijnen[lijnen.length - 1].push([x, y]); vorigeC = null;
    } else if (opdracht === 'C' || opdracht === 'S') {
      let c1: Punt;
      if (opdracht === 'C') {
        c1 = [getal(i), getal(i + 1)]; i += 2;
      } else {
        c1 = vorigeC ? [2 * x - vorigeC[0], 2 * y - vorigeC[1]] : [x, y];
      }
      const c2: Punt = [getal(i), getal(i + 1)];
      const eind: Punt = [getal(i + 2), getal(i + 3)];
      i += 4;
      const p0: Punt = [x, y];
      for (let s = 1; s <= 20; s++) {
        const t = s / 20;
        lijnen[lijnen.length - 1].push([0, 1].map((k) => (1 - t) ** 3 * p0[k] + 3 * (1 - t) ** 2 * t * c1[k]
          + 3 * (1 - t) * t ** 2 * c2[k] + t ** 3 * eind[k]) as Punt);
      }
      [x, y] = eind;
      vorigeC = c2;
    } else {
      throw new Error(`onbekende opdracht in een pad: ${opdracht}`);
    }
  }
  return lijnen;
}

// Een lijn in stukjes volgens een streeppatroon (`3 3`): aan, uit, aan (`_streep`).
function streep(lijn: Punt[], patroonTekst: string | null | undefined): Punt[][] {
  if (!patroonTekst) return [lijn];
  const patroon = patroonTekst.split(/\s+/).filter(Boolean).map(parseFloat);
  const uit: Punt[][] = [];
  let stuk: Punt[] = [lijn[0]];
  let aan = true;
  let k = 0;
  let over = patroon[0];
  for (let j = 0; j + 1 < lijn.length; j++) {
    const [x0, y0] = lijn[j];
    const [x1, y1] = lijn[j + 1];
    const lengte = ((x1 - x0) ** 2 + (y1 - y0) ** 2) ** 0.5;
    let pos = 0;
    while (lengte - pos > over) {
      pos += over;
      const punt: Punt = [x0 + (x1 - x0) * pos / lengte, y0 + (y1 - y0) * pos / lengte];
      if (aan) uit.push([...stuk, punt]);
      stuk = [punt];
      aan = !aan;
      k = (k + 1) % patroon.length;
      over = patroon[k];
    }
    over -= lengte - pos;
    stuk.push([x1, y1]);
  }
  if (aan && stuk.length > 1) uit.push(stuk);
  return uit;
}

// De vormen van een tekening als SVG, in eenheden van het raster; `schaal` pixels per eenheid (`_vormen`). Pillow tekent op
// drie keer de maat en verkleint; hier de dikte van een lijn zoals die daar uitkomt.
function vormen(lijst: Vorm[], schaal: number, kleur: string): string {
  const s = schaal * OVERMAAT;
  const dik = (w: number) => Math.max(1, Math.round(w * s)) / s;
  const lijnstuk = (lijnen: Punt[][], w: number, o: number) => {
    const d = lijnen.map((l) => `M${l.map(([x, y]) => `${g(x)} ${g(y)}`).join('L')}`).join('');
    return `<path d="${d}" fill="none" stroke="${kleur}" stroke-opacity="${o}" stroke-width="${g(dik(w))}" `
      + 'stroke-linecap="round" stroke-linejoin="round"/>';
  };
  const uit: string[] = [];
  for (const v of lijst) {
    if (v.v === 'regel' || v.v === 'blok') {
      const r = v.v === 'regel' ? v.h! / 2 : v.r!;
      uit.push(`<rect x="${g(v.x!)}" y="${g(v.y!)}" width="${g(v.w!)}" height="${g(v.h!)}" rx="${g(r)}" fill="${kleur}" `
        + `fill-opacity="${v.o}"/>`);
    } else if (v.v === 'stip') {
      if (v.open) {
        const rand = Math.max(1, Math.round(0.9 * s)) / s;
        uit.push(`<circle cx="${g(v.x!)}" cy="${g(v.y!)}" r="${g(v.r!)}" fill="${PAPIER}" fill-opacity="0.8"/>`);
        uit.push(`<circle cx="${g(v.x!)}" cy="${g(v.y!)}" r="${g(v.r! - rand / 2)}" fill="none" stroke="${kleur}" `
          + `stroke-opacity="0.45" stroke-width="${g(rand)}"/>`);
      } else {
        uit.push(`<circle cx="${g(v.x!)}" cy="${g(v.y!)}" r="${g(v.r!)}" fill="${kleur}" fill-opacity="${v.o}"/>`);
      }
    } else if (v.v === 'lijn') {
      uit.push(lijnstuk(pad(v.d!).flatMap((l) => streep(l, v.streep)), v.w!, v.o));
    } else if (v.v === 'ring') {
      const cirkel: Punt[] = Array.from({ length: 121 }, (_, i) => {
        const t = (2 * Math.PI * i) / 120;
        return [v.x! + v.r! * Math.cos(t), v.y! + v.r! * Math.sin(t)];
      });
      uit.push(lijnstuk(streep(cirkel, v.streep), v.w!, v.o));
    } else if (v.v === 'vlak') {
      // een gevuld pad: een kaart of een voorwerp (2026-11-19, `_vormen`)
      const d = pad(v.d!).filter((l) => l.length > 2).map((l) => `M${l.map(([x, y]) => `${g(x)} ${g(y)}`).join('L')}Z`).join('');
      uit.push(`<path d="${d}" fill="${kleur}" fill-opacity="${v.o}"/>`);
    }
  }
  return uit.join('');
}

// Welk veld onder de band ligt: bij een dossier zijn eigen veld, anders dat van het thema, anders het algemene.
export function bandnaam(banden: Set<string>, thema: string | null, dossier: string | null): string {
  if (dossier && banden.has(`dossier-${dossier}`)) return `dossier-${dossier}`;
  if (thema && banden.has(`thema-${thema}`)) return `thema-${thema}`;
  return 'delen';
}

// Het veld met de tekening rechts, zoals in de kop van een thema of dossier (`_band`).
function band(thema: string | null, dossier: string | null): string {
  const uit = [
    `<clipPath id="bandvlak"><rect width="${BREED}" height="${BAND}"/></clipPath><g clip-path="url(#bandvlak)">`,
    `<image href="${BEELD}band" x="0" y="0" width="${BREED}" height="${BAND}" image-rendering="optimizeSpeed"/>`,
    // de sluier van `.kaartveld` op de site: van 0,1 in de bovenste rij naar 0,55 in de onderste
    '<linearGradient id="sluier" gradientUnits="userSpaceOnUse" x1="0" y1="0.5" x2="0" y2="227.5">'
      + '<stop offset="0" stop-color="rgb(12,13,16)" stop-opacity="0.1"/>'
      + '<stop offset="1" stop-color="rgb(12,13,16)" stop-opacity="0.55"/></linearGradient>',
    `<rect width="${BREED}" height="${BAND}" fill="url(#sluier)"/>`,
  ];
  const lijst = (dossier ? PLATEN.platen[`dossier:${dossier}`] : undefined) || (thema ? PLATEN.platen[`thema:${thema}`] : undefined);
  if (lijst && lijst.length) {
    const familie = PLATEN.familie[thema ?? ''];
    const kleur = familie ? PLATEN.kleur[familie] : ZACHT;
    const vakX = BREED / 2;
    const vakB = BREED / 2;
    const velSchaal = Math.max(vakB / 160, BAND / 68);
    const x0 = rond(vakX + 26 * velSchaal);
    const y0 = rond(13 * velSchaal);
    uit.push(`<rect x="${x0}" y="${y0}" width="${BREED + 40 - x0 + 1}" height="${BAND + 40 - y0 + 1}" `
      + `rx="${g(3 * velSchaal)}" fill="${PAPIER}" fill-opacity="${g(Math.round(0.72 * 255) / 255)}" shape-rendering="crispEdges"/>`);
    const vormSchaal = Math.min(vakB / 160, BAND / 68);
    // naar onderen vervaagt de tekening: helemaal tot 55% van de hoogte, dan lineair naar niets
    uit.push(`<mask id="vervaag" maskUnits="userSpaceOnUse" x="${vakX}" y="0" width="${vakB}" height="${BAND}">`
      + '<linearGradient id="vervaagkleur" gradientUnits="userSpaceOnUse" x1="0" y1="0.5" x2="0" y2="227.5">'
      + `<stop offset="0.55" stop-color="#fff" stop-opacity="1"/><stop offset="1" stop-color="#fff" stop-opacity="0"/>`
      + `</linearGradient><rect x="${vakX}" y="0" width="${vakB}" height="${BAND}" fill="url(#vervaagkleur)"/></mask>`);
    uit.push(`<g mask="url(#vervaag)"><g transform="translate(${vakX} 0) scale(${vormSchaal})">`
      + `${vormen(lijst, vormSchaal, kleur)}</g></g>`);
  }
  uit.push('</g>');
  return uit.join('');
}

// Het label zoals op de site: een pil met een stip en het woord (`_label`); Pillow rondt de hoeken af op hele pixels en
// tekent de rand van 2 binnen het vlak.
async function label(z: Zetter, x: number, y: number, tekst: string, klasse: string | null): Promise<string> {
  const k = LABELKLEUREN[KLASSE_KLEUR[klasse ?? ''] ?? ''] ?? GEEN_LABEL;
  const hoogte = 52;
  const binnen = 22;
  const stip = 12;
  const breedte = binnen * 2 + stip + 12 + (await z.breedte(tekst, LABEL_GROOTTE, 600));
  const [x0, y0, x1, y1] = [rond(x), rond(y), rond(x + breedte), rond(y + hoogte)];
  const [w, h] = [x1 - x0 + 1, y1 - y0 + 1];
  const tekstpad = await z.schrijf(x + binnen + stip + 12, y + hoogte / 2, tekst, LABEL_GROOTTE, 600, 'lm');
  return `<rect x="${x0}" y="${y0}" width="${w}" height="${h}" rx="${g(h / 2)}" fill="${k.rand}" shape-rendering="crispEdges"/>`
    + `<rect x="${x0 + 2}" y="${y0 + 2}" width="${w - 4}" height="${h - 4}" rx="${g(h / 2 - 2)}" fill="${k.vlak}" `
    + 'shape-rendering="crispEdges"/>'
    + `<circle cx="${g(rond(x + binnen) + 6.5)}" cy="${g(rond(y + (hoogte - stip) / 2) + 6.5)}" r="6.5" fill="${k.stip}" `
    + 'shape-rendering="crispEdges"/>'
    + `<path d="${tekstpad}" fill="${k.inkt}"/>`;
}

const tekst = (d: string, kleur: string) => (d ? `<path d="${d}" fill="${kleur}"/>` : '');

// Het oordeel als stempel (`deelbeeld._stempel`, PLAN #34.2cc): het woord in hoofdletters in een dubbel kader, zonder vlak,
// rechtop. Pillow tekent een rand van 3 en 2 binnen het vak; hier dezelfde vakken als lijnen in het midden van die rand.
async function stempel(z: Zetter, x: number, y: number, woord: string, klasse: string | null): Promise<[string, number]> {
  const k = LABELKLEUREN[KLASSE_KLEUR[klasse ?? ''] ?? ''] ?? GEEN_LABEL;
  const binnen = 20;
  const hoofd = woord.toUpperCase();
  const breedte = Math.round(binnen * 2 + (await z.breedte(hoofd, LABEL_GROOTTE, 700)));
  const [x0, y0] = [Math.round(x), Math.round(y)];
  const pad = await z.schrijf(x0 + binnen, y0 + STEMPEL_HOOGTE / 2, hoofd, LABEL_GROOTTE, 700, 'lm');
  const svg = `<rect x="${x0 + 1.5}" y="${y0 + 1.5}" width="${breedte - 2}" height="${STEMPEL_HOOGTE - 2}" fill="none" `
    + `stroke="${k.stip}" stroke-width="3" shape-rendering="crispEdges"/>`
    + `<rect x="${x0 + 7}" y="${y0 + 7}" width="${breedte - 13}" height="${STEMPEL_HOOGTE - 13}" fill="none" `
    + `stroke="${k.stip}" stroke-width="2" shape-rendering="crispEdges"/>`
    + `<path d="${pad}" fill="${k.inkt}"/>`;
  return [svg, breedte];
}

// Het wit met de band erboven en het woordmerk rechtsonder, en daarop wat `inhoud` tekent; als JPEG.
async function plaatje(b: Beelden, bandNaam: string, thema: string | null, dossier: string | null, inhoud: string):
  Promise<Uint8Array> {
  const [mw, mh] = b.merkMaat;
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${BREED}" height="${HOOG}" viewBox="0 0 ${BREED} ${HOOG}">`
    + `<rect width="${BREED}" height="${HOOG}" fill="#fff"/>${band(thema, dossier)}`
    + `<image href="${BEELD}merk" x="${BREED - MARGE - mw}" y="${HOOG - 52 - mh}" width="${mw}" height="${mh}" image-rendering="optimizeSpeed"/>`
    + `${inhoud}</svg>`;
  const r = new Resvg(svg, { font: { loadSystemFonts: false } });
  try {
    r.resolveImage(`${BEELD}band`, await b.band(bandNaam));
    r.resolveImage(`${BEELD}merk`, b.merk);
    const beeld = r.render();
    try {
      const pixels = beeld.pixels;
      const jpeg = encode({ data: pixels, width: beeld.width, height: beeld.height }, KWALITEIT).data as Uint8Array;
      return new Uint8Array(jpeg.buffer, jpeg.byteOffset, jpeg.byteLength);
    } finally {
      beeld.free();
    }
  } finally {
    r.free();
  }
}

// Het plaatje van een factcheck, 1200 bij 630 (`deelbeeld.teken`). `bewering` is leeg als geen lettertype haar kan tonen.
export async function teken(z: Zetter, b: Beelden, g_: { bewering: string; label: string; klasse: string | null; zin: string;
  thema: string | null; volgens?: string[] }): Promise<Uint8Array> {
  const [mw] = b.merkMaat;
  const delen: string[] = [];
  // van onder naar boven: de zin, het label, en de bewering in wat er overblijft; zonder bewering staan het label en de
  // zin midden in het vlak
  let zinY = HOOG - 52 - ZIN_GROOTTE * 1.2;
  if (!g_.bewering) zinY = BAND + (HOOG - BAND - (52 + 18 + ZIN_GROOTTE * 1.2)) / 2 + 52 + 18;
  const [zinRegels] = await z.regels(g_.zin, ZIN_GROOTTE, BREED - 2 * MARGE - mw - 32, 1, 400);
  if (zinRegels.length) delen.push(tekst(await z.schrijf(MARGE, zinY, zinRegels[0], ZIN_GROOTTE, 400), ZACHT));
  const labelY = zinY - 18 - 52;
  // het stempel met klein wie het zegt ernaast (PLAN #34.2cc, DESIGN §4y)
  const [stempelSvg, stempelBreed] = await stempel(z, MARGE, labelY, g_.label, g_.klasse);
  delen.push(stempelSvg);
  // de vormen van lang naar kort: de eerste die heel past, anders de kortste afgekapt (`deelbeeld.teken`)
  if (g_.volgens?.length) {
    let volgensRegels: string[] = [];
    for (const vorm of g_.volgens) {
      const [r, afgekapt] = await z.regels(vorm, ZIN_GROOTTE, BREED - MARGE - (MARGE + stempelBreed + 18), 1, 500);
      volgensRegels = r;
      if (!afgekapt) break;
    }
    if (volgensRegels.length) {
      delen.push(tekst(await z.schrijf(MARGE + stempelBreed + 18, labelY + STEMPEL_HOOGTE / 2, volgensRegels[0], ZIN_GROOTTE, 500, 'lm'), ZACHT));
    }
  }
  if (g_.bewering) {
    const boven = BAND + 36;
    const onder = labelY - 28;
    let regels: string[] = [];
    let grootte = GROOTTES[0];
    for (grootte of GROOTTES) {
      const [r, afgekapt] = await z.regels(g_.bewering, grootte, BREED - 2 * MARGE, MAX_REGELS);
      regels = r;
      const past = regels.length * grootte * 1.18 <= onder - boven;
      if (past && (!afgekapt || grootte === GROOTTES[GROOTTES.length - 1])) break;
    }
    while (regels.length * grootte * 1.18 > onder - boven && regels.length > 1) {
      regels = regels.slice(0, -1);
      const laatste = regels[regels.length - 1].replace(/\u2026+$/u, '');
      regels[regels.length - 1] = `${laatste.includes(' ') ? laatste.slice(0, laatste.lastIndexOf(' ')) : laatste}\u2026`;
    }
    for (const [i, regel] of regels.entries()) {
      delen.push(tekst(await z.schrijf(MARGE, boven + i * grootte * 1.18, regel, grootte, 600, 'la', BREED - MARGE), INKT));
    }
  }
  return plaatje(b, bandnaam(z.banden, g_.thema, null), g_.thema, null, delen.join(''));
}

// Het plaatje van een thema, onderdeel of dossier (`deelbeeld.teken_ingang`): de soort klein, de naam groot en het aantal
// eronder, onder de band met het veld en de tekening.
export async function tekenIngang(z: Zetter, b: Beelden, g_: { kicker: string; titel: string; regel: string;
  thema: string | null; dossier: string | null }): Promise<Uint8Array> {
  const [mw] = b.merkMaat;
  const delen: string[] = [];
  const boven = BAND + 44;
  if (g_.kicker && await z.kanTonen(g_.kicker)) delen.push(tekst(await z.schrijf(MARGE, boven, g_.kicker, ZIN_GROOTTE, 600), ZACHT));
  const regelY = HOOG - 52 - ZIN_GROOTTE * 1.2;
  const ruimte = regelY - 24 - (boven + ZIN_GROOTTE * 1.2 + 14);
  if (g_.titel && await z.kanTonen(g_.titel)) {
    let regels: string[] = [];
    let grootte = 64;
    for (grootte of [64, 56, 48]) {
      const [r, afgekapt] = await z.regels(g_.titel, grootte, BREED - 2 * MARGE, 2, 700);
      regels = r;
      if (!afgekapt && regels.length * grootte * 1.12 <= ruimte) break;
    }
    for (const [i, r] of regels.entries()) {
      delen.push(tekst(await z.schrijf(MARGE, boven + ZIN_GROOTTE * 1.2 + 14 + i * grootte * 1.12, r, grootte, 700, 'la',
        BREED - MARGE), INKT));
    }
  }
  const [regelRegels] = await z.regels(g_.regel, ZIN_GROOTTE, BREED - 2 * MARGE - mw - 32, 1, 400);
  if (regelRegels.length && await z.kanTonen(regelRegels[0])) {
    delen.push(tekst(await z.schrijf(MARGE, regelY, regelRegels[0], ZIN_GROOTTE, 400), ZACHT));
  }
  return plaatje(b, bandnaam(z.banden, g_.thema, g_.dossier), g_.thema, g_.dossier, delen.join(''));
}
