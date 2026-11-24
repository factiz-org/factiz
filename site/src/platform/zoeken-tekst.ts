// De tekstkant van het zoeken in TypeScript (B80, PLAN #34.2bo stap 4): de stukken van een vraag, de vormen van een woord,
// afkortingen, de afstand tussen twee woorden, een link als adres en het markeren van treffers. Gelijk aan
// `factiz_site/db.py` en `factiz_site/app.py`; Python telt in code points en kent Unicode 15.0 (`zoeken-unicode.ts`).
import { kort, schoon, urlencode, woorden } from './tekst.ts';
import { ALNUM_KLASSE, GEEN_ALNUM_KLASSE, casefold, heeftWit, isalnum, isalpha, isascii, isM, isMn, isupper, knip, lengte, lower,
  normaliseer, strip, stripTekens, vergelijk, zonderMn } from './zoeken-unicode.ts';

export const MAX_VRAAG = 200;          // tekens van een zoekvraag
export const MAX_TERMEN = 12;
export const MAX_PLAKTEKST = 1000;     // tekens van een geplakt bericht
export const RANDTEKENS = '.,;:!?¡¿…"\'“”‘’«»()[]';
export const MAX_PLAKWOORDEN = 80;
export const BERICHT_WOORDEN = 6;
export const BERICHT_TERMEN = 10;
export const BERICHT_GEWOON = 0.02;
export const BERICHT_DEEL = 0.3;
export const BERICHT_DEKKING = 0.4;
export const BERICHT_MAX = 100;
export const BERICHT_ZWAK = 10;
export const MAX_KENMERK = 6;
export const AANVUL_MIN = 3;
export const FAMILIE = 100;
export const MAX_VORMEN = 16;
export const GEWOON = 10;
export const AFKORTING_ZEKER = 0.5;
// Leestekens aan de rand van een woord tellen niet mee in een suggestie.
export const LEESTEKENS = '.,;:!?()[]{}"\'«»„“”‘’';

const ANDERS: Record<string, string> = { 'ß': 'ss', 'œ': 'oe', 'æ': 'ae', 'ø': 'o', 'ł': 'l',
  'đ': 'd', 'ð': 'd', 'ı': 'i', 'þ': 'th' };
export const BIJZONDER = /[ßœæøłđðıþ]/u;
export const LETTERS = /^[a-z]+$/;
const MEDEKLINKER = new Set('bcdfghjklmnpqrstvwxz');
// Een streepje binnen een stuk van Latijnse letters en cijfers (COVID-19, e-mail); geen punt.
export const GELEED = /^[a-z0-9]+(?:[-‐‑–—][a-z0-9]+)+$/;
// Schriften zonder grenzen tussen woorden: daar zoekt de site op tekens. Het Koreaans hoort er bij het verbeteren wel bij.
export const ZONDER_GRENS = /[฀-໿က-႟ក-៿぀-ヿ㐀-䶿一-鿿豈-﫿]/u;
export const ZONDER_SPATIES =
  /[฀-໿က-႟ក-៿぀-ヿ㐀-䶿一-鿿가-힯豈-﫿]/u;
const AANHALING = /["“”„«»]/u;
export const AANHALINGSTEKENS = '"“”„«»';
const HOOFD = 'A-ZÀ-ÖØ-Þ';
const LOS_IN_HOOFDLETTERS = new RegExp(`(?<!${ALNUM_KLASSE})[${HOOFD}]{2,3}(?!${ALNUM_KLASSE})`, 'gv');
const HOOFDWOORD = new RegExp(`^[${HOOFD}]{2}$`, 'u');

const heeftAlnum = (s: string): boolean => {
  for (const c of s) if (isalnum(c)) return true;
  return false;
};

// Brede letters van een Chinees of Japans toetsenbord en andere tekens voor dezelfde letter, met NFKC (`_toetsenbord`).
export const toetsenbord = (tekst: string): string => normaliseer(tekst, 'NFKC');

// Hetzelfde woord zoals een Perzisch of Arabisch toetsenbord het typt; alleen de andere vormen, op volgorde.
const NAAR_PERZISCH: Record<string, string> = { 'ي': 'ی', 'ك': 'ک', 'ى': 'ی' };
const NAAR_ARABISCH: Record<string, string> = { 'ی': 'ي', 'ک': 'ك' };
const vertaal = (s: string, tabel: Record<string, string>) => Array.from(s).map((c) => tabel[c] ?? c).join('');

export function toetsenbordvormen(stuk: string): string[] {
  return [...new Set([vertaal(stuk, NAAR_PERZISCH), vertaal(stuk, NAAR_ARABISCH)])].filter((v) => v !== stuk).sort(vergelijk);
}

// De stukken van een zoekvraag, gesplitst op witruimte; een stuk zonder letter of cijfer valt weg (`zoektermen`).
export function zoektermen(vraag: string | null | undefined): string[] {
  const schone = knip(toetsenbord(schoon(vraag || '')), 0, MAX_VRAAG);
  return woorden(schone).filter(heeftAlnum).slice(0, MAX_TERMEN);
}

// Eén stuk als letterlijke zin voor het zoekregister.
export const zin = (stuk: string): string => `"${stuk.replaceAll('"', ' ')}"`;

export type Deel = [string, boolean];

// De stukken van een vraag, met bij elk of het tussen aanhalingstekens stond (`zoekdelen`); `lang` is een geplakt bericht.
export function zoekdelen(vraag: string | null | undefined, lang = false): Deel[] {
  const schone = knip(toetsenbord(schoon(vraag || '')), 0, lang ? MAX_PLAKTEKST : MAX_VRAAG);
  const stukken = schone.split(AANHALING);
  if (stukken.length % 2 === 0) stukken.push(stukken.splice(-2).join(' '));
  const uit: Deel[] = [];
  stukken.forEach((stuk, i) => {
    const w = woorden(stuk).filter(heeftAlnum);
    if (i % 2 && w.length) uit.push([w.join(' '), true]);
    else uit.push(...w.map((x): Deel => [x, false]));
  });
  return uit.slice(0, lang ? MAX_PLAKWOORDEN : MAX_TERMEN);
}

// Een woord zoals het register op woorden het bewaart: kleine letters, zonder accenten (`_indexvorm`).
export const indexvorm = (tekst: string): string => zonderMn(normaliseer(lower(tekst), 'NFD'));

// Het woord zoals iemand het typt zonder bijzondere letters (`_ascii`).
export const ascii = (tekst: string): string => Array.from(indexvorm(tekst)).map((c) => ANDERS[c] ?? c).join('');

// Waarop een naam gesorteerd en vergeleken wordt: zonder hoofdletters en accenten (`db._alfabet`), met de volle
// `casefold` van Python.
export const alfabet = (naam: string): string => strip(zonderMn(normaliseer(casefold(naam), 'NFKD')));

// Een vraag of naam zoals het register van ingangen haar kent (`db.sleutel`).
export const sleutel = (tekst: string | null | undefined): string => alfabet(zoektermen(tekst).join(' '));

// Welke van deze afkortingen los in hoofdletters in de tekst staan, niet in een kop in hoofdletters (`los_in_hoofdletters`).
export function losInHoofdletters(tekst: string, gezocht: Set<string>): Set<string> {
  const uit = new Set<string>();
  for (const m of tekst.matchAll(LOS_IN_HOOFDLETTERS)) {
    const w = m[0];
    if (!gezocht.has(w) || uit.has(w)) continue;
    const begin = m.index;
    const eind = begin + w.length;
    const voor = Array.from(tekst.slice(Math.max(0, begin - 6), begin)).slice(-3);
    const na = Array.from(tekst.slice(eind, eind + 6)).slice(0, 3);
    if ((voor.length === 3 && /^[\t\n\x0b\x0c\r\x1c-\x1f \x85\xa0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000]$/u.test(voor[2])
         && HOOFDWOORD.test(voor[0] + voor[1]))
        || (na.length === 3 && /^[\t\n\x0b\x0c\r\x1c-\x1f \x85\xa0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000]$/u.test(na[0])
            && HOOFDWOORD.test(na[1] + na[2]))) continue;
    uit.add(w);
  }
  return uit;
}

// Een afkorting in hoofdletters: alleen letters, 2 tot `langst`, allemaal hoofdletters (`_is_afkorting`).
export function isAfkorting(vorm: string | null | undefined, langst: number): boolean {
  const v = strip(vorm || '');
  const n = lengte(v);
  return n >= 2 && n <= langst && isalpha(v) && isupper(v);
}

// Hoeveel letters a en b verschillen, met een grens; erboven heet het grens + 1 (`_afstand`).
export function afstand(a: string | string[], b: string | string[], grens: number): number {
  const x = typeof a === 'string' ? Array.from(a) : a;
  const y = typeof b === 'string' ? Array.from(b) : b;
  if (Math.abs(x.length - y.length) > grens) return grens + 1;
  let vorige2: number[] = [];
  let vorige = Array.from({ length: y.length + 1 }, (_, i) => i);
  for (let i = 1; i <= x.length; i++) {
    const rij = [i, ...new Array(y.length).fill(0)];
    let laagste = i;
    for (let j = 1; j <= y.length; j++) {
      rij[j] = Math.min(vorige[j] + 1, rij[j - 1] + 1, vorige[j - 1] + (x[i - 1] !== y[j - 1] ? 1 : 0));
      if (i > 1 && j > 1 && x[i - 1] === y[j - 2] && x[i - 2] === y[j - 1]) rij[j] = Math.min(rij[j], vorige2[j - 2] + 1);
      if (rij[j] < laagste) laagste = rij[j];
    }
    if (laagste > grens) return grens + 1;
    vorige2 = vorige;
    vorige = rij;
  }
  return vorige[vorige.length - 1];
}

// Lijkt w op een van de woorden in `op`, met de maat van de schrijfwijzen van een naam (`_lijkt`)?
export function lijkt(w: string, op: string[]): boolean {
  const a = ascii(w);
  return op.some((k) => {
    const b = ascii(k);
    const grens = Math.max(2, Math.floor(lengte(b) / 3));
    return afstand(a, b, grens) <= grens;
  });
}

// Telt een bijnaam van een organisatie of plaats mee voor het zoeken (`bijnaam_telt`)?
export function bijnaamTelt(vorm: string, enkel: string[]): boolean {
  const v = strip(vorm);
  if (!v || v.endsWith('.') || zoektermen(v).length !== 1) return false;
  const w = stripTekens(v, LEESTEKENS);
  return (isupper(w) && isalpha(w) && lengte(w) >= 4) || lijkt(w, enkel);
}

// De vormen met een meervoudsuitgang erbij en eraf (`_op`, `_af`); alleen voor woorden van a tot z.
export function op(w: string): Set<string> {
  const uit = new Set<string>();
  if (w.length >= 4) {
    if (!w.endsWith('s')) uit.add(`${w}s`);
    if (!w.endsWith('e')) uit.add(`${w}en`);
    if (MEDEKLINKER.has(w[w.length - 1])) uit.add(`${w}es`);
    if (w.endsWith('y')) uit.add(`${w.slice(0, -1)}ies`);
    if (w.endsWith('au') || w.endsWith('eu')) uit.add(`${w}x`);
  }
  if (w.length >= 5 && w.endsWith('al')) uit.add(`${w.slice(0, -2)}aux`);
  if (w.length >= 6) uit.add(w.endsWith('e') ? `${w}n` : `${w}e`);
  if (w.length >= 8 && w.endsWith('um')) uit.add(`${w.slice(0, -2)}a`);
  return uit;
}

export function af(w: string): Set<string> {
  const uit = new Set<string>();
  if (w.endsWith('s') && w.length >= 5 && !w.endsWith('ss') && !w.endsWith('us') && !w.endsWith('is')) uit.add(w.slice(0, -1));
  if (w.endsWith('es') && w.length >= 6 && MEDEKLINKER.has(w[w.length - 3])) uit.add(w.slice(0, -2));
  if (w.endsWith('en') && w.length >= 6) uit.add(w.slice(0, -2));
  if (w.endsWith('e') && w.length >= 7) uit.add(w.slice(0, -1));
  if (w.endsWith('en') && w.length >= 7) uit.add(w.slice(0, -1));
  if (w.endsWith('ies') && w.length >= 6) uit.add(`${w.slice(0, -3)}y`);
  if (w.endsWith('aux') && w.length >= 6 && !w.endsWith('eaux')) uit.add(`${w.slice(0, -3)}al`);
  if ((w.endsWith('aux') || w.endsWith('eux')) && w.length >= 5) uit.add(w.slice(0, -1));
  if (w.endsWith('a') && w.length >= 7) uit.add(`${w.slice(0, -1)}um`);
  return uit;
}

// Enkelvoud en meervoud van een woord in Latijnse letters (`vormen`).
export function vormen(woord: string): Set<string> {
  const w = ascii(woord);
  if (!LETTERS.test(w)) return new Set();
  const uit = new Set([...op(w), ...af(w)]);
  uit.delete(w);
  return uit;
}

// --- markeren (`app._vouw`, `_raak`, `markeer`, `fragment`) -----------------------------------------------------------

// De tekst zonder hoofdletters en accenten, met voor elk teken de plek in de tekst zelf (in code points).
function vouw(tekst: string): [string[], number[]] {
  const gevouwen: string[] = [];
  const plek: number[] = [];
  let i = 0;
  for (const teken of tekst) {
    for (const kaal of normaliseer(casefold(teken), 'NFKD')) {
      if (!isMn(kaal) || !gevouwen.length) {
        gevouwen.push(kaal);
        plek.push(i);
      }
    }
    i++;
  }
  return [gevouwen, plek];
}

const letterlijk = (s: string) => s.replace(/[\\^$.*+?()[\]{}|/]/g, '\\$&');

// Waar de stukken van de vraag in de tekst staan, als begin en eind in code points.
export function raak(tekst: string, termen: string[]): [number, number][] {
  const [gevouwen, plek] = vouw(tekst);
  const g = gevouwen.join('');
  // van een plek in UTF-16 naar een plek in code points
  const naarTeken = new Int32Array(g.length + 1);
  let n = 0;
  for (let i = 0; i < g.length; n++) {
    naarTeken[i] = n;
    if (g.codePointAt(i)! > 0xffff) naarTeken[++i] = n;
    i++;
  }
  naarTeken[g.length] = n;
  const vakken: [number, number][] = [];
  for (const term of termen) {
    const begin = lengte(term) > 1 && term.endsWith('*');
    const delen = woorden(vouw(begin ? term.slice(0, -1) : term)[0].join(''));
    if (!delen.length) continue;
    const patroon = new RegExp(delen.map(letterlijk).join(`${GEEN_ALNUM_KLASSE}+`) + (begin ? `${ALNUM_KLASSE}*` : ''), 'gv');
    const heel: [number, number][] = [];
    const deel: [number, number][] = [];
    for (const m of g.matchAll(patroon)) {
      const i = naarTeken[m.index];
      const eind = naarTeken[m.index + m[0].length];
      const vak: [number, number] = [plek[i], plek[eind - 1] + 1];
      const losVoor = i === 0 || !isalnum(gevouwen[i - 1]);
      const losNa = eind === gevouwen.length || !isalnum(gevouwen[eind]);
      if (losVoor && losNa) heel.push(vak);
      else if (!begin) deel.push(vak);
    }
    vakken.push(...(heel.length ? heel : deel));
  }
  const tekens = Array.from(tekst);
  const samen: [number, number][] = [];
  for (const [b, e] of vakken.sort((x, y) => x[0] - y[0] || x[1] - y[1])) {
    let eind = e;
    // een combinerend teken hoort bij het teken ervoor
    while (eind < tekens.length && isM(tekens[eind])) eind++;
    const laatste = samen[samen.length - 1];
    if (laatste && b <= laatste[1]) laatste[1] = Math.max(laatste[1], eind);
    else samen.push([b, eind]);
  }
  return samen;
}

// De tekst in stukken, met bij elk stuk of het een woord van de vraag is (`app.markeer`).
export function markeer(tekst: string, termen: string[]): [string, boolean][] {
  const tekens = Array.from(tekst);
  const uit: [string, boolean][] = [];
  let vorige = 0;
  for (const [b, e] of raak(tekst, termen)) {
    if (b > vorige) uit.push([tekens.slice(vorige, b).join(''), false]);
    uit.push([tekens.slice(b, e).join(''), true]);
    vorige = e;
  }
  if (vorige < tekens.length) uit.push([tekens.slice(vorige).join(''), false]);
  return uit;
}

// Het begin, of bij een lange bewering het stuk rond het eerste woord van de vraag (`app.fragment`).
export function fragment(tekst: string | null | undefined, termen: string[], n = 220): string {
  const heel = woorden(tekst || '').join(' ');
  const r = raak(heel, termen);
  if (!r.length || r[0][1] <= n - 40) return kort(heel, n);
  const tekens = Array.from(heel);
  let begin = Math.max(0, r[0][0] - 80);
  if (begin && tekens.slice(begin, r[0][0]).includes(' ')) begin = tekens.indexOf(' ', begin) + 1;
  return `… ${kort(tekens.slice(begin).join(''), n)}`;
}

// --- links (`db.adresvorm`, met `urllib.parse` van Python 3.12) --------------------------------------------------------

function partitie(s: string, teken: string, vanAchter = false): [string, string, string] {
  const i = vanAchter ? s.lastIndexOf(teken) : s.indexOf(teken);
  if (i < 0) return vanAchter ? ['', '', s] : [s, '', ''];
  return [s.slice(0, i), teken, s.slice(i + teken.length)];
}

function ipv4(s: string): boolean {
  if (s.includes('/') || !s) return false;
  const delen = s.split('.');
  return delen.length === 4 && delen.every((d) => /^[0-9]{1,3}$/.test(d) && (d === '0' || d[0] !== '0') && parseInt(d, 10) <= 255);
}

function ipv6(s: string): boolean {
  if (s.includes('/')) return false;
  const [adres, scheiding, zone] = partitie(s, '%');
  if (scheiding && (!zone || zone.includes('%'))) return false;
  if (!adres || lengte(adres) > 45) return false;
  // `split(':', maxsplit=9)`: hoogstens tien delen, het laatste met de rest
  const alle = adres.split(':');
  const delen = alle.length > 10 ? [...alle.slice(0, 9), alle.slice(9).join(':')] : alle;
  if (delen.length < 3) return false;
  if (delen[delen.length - 1].includes('.')) {
    if (!ipv4(delen.pop()!)) return false;
    delen.push('0', '0');
  }
  if (delen.length > 9) return false;
  let overslaan: number | null = null;
  for (let i = 1; i < delen.length - 1; i++) {
    if (!delen[i]) {
      if (overslaan !== null) return false;
      overslaan = i;
    }
  }
  let hoog: number;
  let laag: number;
  if (overslaan !== null) {
    hoog = overslaan;
    laag = delen.length - overslaan - 1;
    if (!delen[0] && --hoog) return false;
    if (!delen[delen.length - 1] && --laag) return false;
    if (8 - (hoog + laag) < 1) return false;
  } else {
    if (delen.length !== 8 || !delen[0] || !delen[delen.length - 1]) return false;
    hoog = delen.length;
    laag = 0;
  }
  const hextet = (h: string) => /^[0-9A-Fa-f]{1,4}$/.test(h);
  for (let i = 0; i < hoog; i++) if (!hextet(delen[i])) return false;
  for (let i = delen.length - laag; i < delen.length; i++) if (!hextet(delen[i])) return false;
  return true;
}

// `_check_bracketed_netloc`: een adres tussen haken moet IPv6 of IPvFuture zijn, anders een fout.
function hakenGoed(netloc: string): boolean {
  const hostEnPoort = partitie(netloc, '@', true)[2];
  const [voor, haak, binnen] = partitie(hostEnPoort, '[');
  let host: string;
  if (haak) {
    if (voor) return false;
    const [h, , poort] = partitie(binnen, ']');
    if (poort && !poort.startsWith(':')) return false;
    host = h;
  } else host = partitie(hostEnPoort, ':')[0];
  if (host.startsWith('v')) return /^v[a-fA-F0-9]+\.[^\n]+$/u.test(host);
  return !ipv4(host) && ipv6(host);
}

type Gesplitst = { netloc: string; path: string; query: string };

// `urllib.parse.urlsplit`; niets waar Python een ValueError geeft.
function urlsplit(adres: string): Gesplitst | null {
  let url = adres.replace(/^[\x00-\x20]+/, '').replace(/[\t\r\n]/g, '');
  const i = url.indexOf(':');
  if (i > 0 && /^[a-zA-Z]/.test(url) && /^[a-zA-Z0-9+\-.]*$/.test(url.slice(0, i))) url = url.slice(i + 1);
  let netloc = '';
  let query = '';
  if (url.slice(0, 2) === '//') {
    let eind = url.length;
    for (const c of '/?#') {
      const w = url.indexOf(c, 2);
      if (w >= 0) eind = Math.min(eind, w);
    }
    netloc = url.slice(2, eind);
    url = url.slice(eind);
    if (netloc.includes('[') !== netloc.includes(']')) return null;
    if (netloc.includes('[') && !hakenGoed(netloc)) return null;
  }
  if (url.includes('#')) url = partitie(url, '#')[0];
  if (url.includes('?')) [url, , query] = partitie(url, '?');
  if (netloc && !isascii(netloc)) {
    const n = netloc.replace(/[@:#?]/g, '');
    const n2 = normaliseer(n, 'NFKC');
    if (n !== n2 && /[/?#@:]/.test(n2)) return null;
  }
  return { netloc, path: url, query };
}

// `hostname`: zonder gebruiker en poort, in kleine letters (de zone van IPv6 niet).
function hostnaam(netloc: string): string {
  const info = partitie(netloc, '@', true)[2];
  const [, haak, binnen] = partitie(info, '[');
  const host = haak ? partitie(binnen, ']')[0] : partitie(info, ':')[0];
  if (!host) return '';
  const [h, procent, zone] = partitie(host, '%');
  return lower(h) + procent + zone;
}

const HEX = /^[0-9A-Fa-f]{2}/;

// `urllib.parse.unquote`: alleen de stukken in ASCII, als UTF-8 met U+FFFD voor wat niet klopt.
function unquote(s: string): string {
  if (!s.includes('%')) return s;
  return s.replace(/[\x00-\x7f]+/g, (stuk) => {
    const delen = stuk.split('%');
    if (delen.length === 1) return stuk;
    const bytes: number[] = [];
    const tekst = (t: string) => { for (let i = 0; i < t.length; i++) bytes.push(t.charCodeAt(i)); };
    tekst(delen[0]);
    for (const d of delen.slice(1)) {
      if (HEX.test(d)) {
        bytes.push(parseInt(d.slice(0, 2), 16));
        tekst(d.slice(2));
      } else tekst(`%${d}`);
    }
    return new TextDecoder('utf-8', { ignoreBOM: true }).decode(new Uint8Array(bytes));
  });
}

// `urllib.parse.parse_qsl(..., keep_blank_values=True)`.
function parseQsl(qs: string): [string, string][] {
  if (!qs) return [];
  const uit: [string, string][] = [];
  for (const nv of qs.split('&')) {
    if (!nv) continue;
    const [naam, , waarde] = partitie(nv, '=');
    uit.push([unquote(naam.replaceAll('+', ' ')), unquote(waarde.replaceAll('+', ' '))]);
  }
  return uit;
}

// Python `$` past ook vlak voor een regeleinde aan het eind.
const VOLGVRAAG = /^(utm_|fbclid(?=\n?$)|gclid(?=\n?$)|igshid(?=\n?$)|mc_|ref(?=\n?$)|amp(?=\n?$)|s(?=\n?$))/;

// Een link zoals het zoeken haar vergelijkt: zonder https, www of m., in kleine letters, zonder / aan het eind en zonder
// #; eerst met de vraag zonder volgvragen, dan zonder vraag (`db.adresvorm`).
export function adresvorm(adres: string): string[] | null {
  const deel = urlsplit(adres.includes('://') ? strip(adres) : `https://${strip(adres)}`);
  if (!deel) return null;
  let host = lower(hostnaam(deel.netloc));
  for (const voor of ['www.', 'm.', 'amp.']) if (host.startsWith(voor)) host = host.slice(voor.length);
  if (!host.includes('.') || !stripTekens(deel.path, '/')) return null;
  const pad = lower(stripTekens(deel.path, '/', 'rechts'));
  const vragen = parseQsl(deel.query).filter(([k]) => !VOLGVRAAG.test(lower(k)));
  const met = vragen.length ? lower(`${host}${pad}?${urlencode(vragen)}`) : null;
  return [met, `${host}${pad}`].filter((v): v is string => !!v);
}

export { casefold, heeftWit, isalpha, isascii, lengte, knip, strip, stripTekens, vergelijk };
