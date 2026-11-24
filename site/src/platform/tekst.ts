// Kleine tekstfuncties van het platform, gelijk aan die in `factiz_site/app.py` en `factiz_site/db.py` (PLAN #34.2bo stap 3).
// Python telt in tekens (code points) en sorteert op code points; JavaScript telt in UTF-16, dus hier expliciet.

// Stuurtekens uit het wild gaan eruit voordat iets de pagina bereikt (`db.schoon`).
const STUUR = /[\u202a-\u202e\u2066-\u2069\ufeff\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]/gu;

export function schoon<T>(waarde: T): T {
  return (typeof waarde === 'string' ? waarde.replace(STUUR, '') : waarde) as T;
}

export function schoneRij<T extends Record<string, unknown>>(rij: T): T {
  const uit: Record<string, unknown> = {};
  for (const [k, v] of Object.entries(rij)) uit[k] = schoon(v);
  return uit as T;
}

// Wat Python witruimte noemt (`str.split()` zonder argument).
const WIT = /[\t\n\x0b\x0c\r\x1c-\x1f \x85\xa0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000]+/u;

export function woorden(tekst: string): string[] {
  return tekst.split(WIT).filter(Boolean);
}

// Code points vergelijken, zoals Python twee teksten vergelijkt.
export function vergelijk(a: string, b: string): number {
  const x = Array.from(a);
  const y = Array.from(b);
  for (let i = 0; i < Math.min(x.length, y.length); i++) {
    const d = x[i].codePointAt(0)! - y[i].codePointAt(0)!;
    if (d) return d;
  }
  return x.length - y.length;
}

// Een bewering in een lijst: afgekapt op een woord (`app._kort`).
export function kort(tekst: string | null | undefined, n = 220): string {
  const heel = woorden(tekst ?? '').join(' ');
  const tekens = Array.from(heel);
  if (tekens.length <= n) return heel;
  const begin = tekens.slice(0, n).join('');
  const knip = begin.includes(' ') ? begin.slice(0, begin.lastIndexOf(' ')) : begin;
  return knip.replace(/[,.;:]+$/u, '') + ' \u2026';
}

// Alleen een gewoon webadres wordt een link (`app._link`); een adres op factiz.org zelf wordt een pad op deze site.
export function link(url: string | null | undefined): string {
  const schoon_ = (url ?? '').replace(/^\s+|\s+$/gu, '');
  if (schoon_.startsWith('https://factiz.org/')) return schoon_.slice('https://factiz.org'.length);
  return schoon_.startsWith('https://') || schoon_.startsWith('http://') ? schoon_ : '';
}

// `urllib.parse.urlencode`: spatie wordt +, alleen letters, cijfers en _.-~ blijven staan.
function quotePlus(s: string): string {
  return encodeURIComponent(s).replace(/[!'()*]/g, (c) => `%${c.charCodeAt(0).toString(16).toUpperCase()}`)
    .replace(/%20/g, '+');
}

export function urlencode(paren: [string, string][]): string {
  return paren.map(([k, v]) => `${quotePlus(k)}=${quotePlus(v)}`).join('&');
}

export type Filters = Record<string, string | string[] | null | undefined>;

// De filters als paren van sleutel en waarde, op alfabet (`app.paren`).
export function paren(filters: Filters): [string, string][] {
  const uit: [string, string][] = [];
  for (const [sleutel, waarde] of Object.entries(filters)) {
    if (Array.isArray(waarde)) uit.push(...waarde.map((w): [string, string] => [sleutel, w]));
    else if (waarde) uit.push([sleutel, waarde]);
  }
  return uit.sort((a, b) => vergelijk(a[0], b[0]) || vergelijk(a[1], b[1]));
}

// `casefold` en `alfabet` zoals Python 3.12 ze rekent (volledig vouwen, Unicode 15.0): uit de tabellen van het zoeken.
// zoeken-unicode.ts leent zelf niets, dus hier geen kring.
import { casefold, normaliseer, strip, zonderMn } from './zoeken-unicode.ts';

export { casefold };

// Waarop een naam in het register gesorteerd wordt: zonder hoofdletters en zonder accenten (`db._alfabet`).
export const alfabet = (naam: string): string => strip(zonderMn(normaliseer(casefold(naam), 'NFKD')));
