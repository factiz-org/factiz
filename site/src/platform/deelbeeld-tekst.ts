// De tekst op het deelplaatje (B80, PLAN #34.2bo stap 5), regel voor regel gelijk aan `factiz_site/deelbeeld.py`: welk
// lettertype elk teken krijgt, de stukken per lettertype, afbreken en afkappen, en waar elk stuk komt. Zetten doet
// HarfBuzz (`deelbeeld-hb.ts`), zoals raqm dat onder Pillow doet; de richting binnen een stuk komt uit bidi-js, zoals
// raqm haar uit FriBidi haalt. Wat Pillow tekent, wordt hier een SVG-pad.
import bidiFactory from 'bidi-js';
import type { HarfBuzz } from './deelbeeld-hb.ts';
import { woorden } from './tekst.ts';
import { Voorraad } from './verzoek.ts';

const bidi = bidiFactory();

// De voorraad (`node scripts/deelbeeld-voorraad.ts`): per lettertype de tekens die het dekt, in de volgorde van
// `deelbeeld._bereik`; de vier pakketten voor Chinees, Japans en Koreaans in eigen bestanden, want hun lijst is groot en
// alleen nodig voor een teken dat geen ander lettertype heeft.
export type Voorraad = { lettertypen: [string, string][]; cjk: string[]; banden: string[] };
export type Lezer = (pad: string) => Promise<Uint8Array>;

type Reeksen = Int32Array;
const CJK_STANDAARD = 'noto-sans-sc';
const GEIST = 'geist-latin-wght-normal.ttf';
// tekens die alleen in traditioneel Chinees zo geschreven worden (`deelbeeld.TRADITIONEEL`)
const TRADITIONEEL = new Set(Array.from('這個們說國會灣為與經裡發時對學來無後電視嗎點關選舉實體開長門問間現認讓應過還運動語錢錄東車書買賣見親頭題麼樣'
  + '誤錯臺灣區華際總統黨權議論號網絡變顯聞報導戰爭軍隊將傳們'));
// schriften zonder spaties tussen de woorden (`deelbeeld._GEEN_SPATIES`), per teken
const GEEN_SPATIES = /^[\u0e00-\u0eff\u1000-\u109f\u1780-\u17ff\u3000-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\uff00-\uffef]$/u;
// wat Python witruimte noemt (`str.isspace`)
const WIT = /^[\t\n\x0b\x0c\r\x1c-\x1f \x85\xa0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000]$/u;
const CF = /^\p{Cf}$/u;
const MERK = /^\p{M}$/u;

export const isWit = (ch: string) => WIT.test(ch);
// een teken dat niets tekent maar het vormen stuurt (zero width joiner, richtingsteken): hoort bij zijn stuk
export const onzichtbaar = (ch: string) => CF.test(ch);

function leesReeksen(tekst: string): Reeksen {
  const delen = tekst.split(',');
  const uit = new Int32Array(delen.length * 2);
  delen.forEach((d, i) => {
    const [a, n] = d.split('+');
    uit[2 * i] = parseInt(a, 36);
    uit[2 * i + 1] = uit[2 * i] + (n ? parseInt(n, 36) : 0);
  });
  return uit;
}

function dekt(r: Reeksen, code: number): boolean {
  for (let i = 0; i < r.length; i += 2) if (r[i] <= code && code <= r[i + 1]) return true;
  return false;
}

// Japans bij kana, Koreaans bij hangul, traditioneel Chinees bij een traditioneel teken, anders vereenvoudigd.
export function cjkVariant(tekst: string): string {
  const tekens = Array.from(tekst);
  if (tekens.some((ch) => ch >= '\u3040' && ch <= '\u30ff')) return 'noto-sans-jp';
  if (tekens.some((ch) => (ch >= '\uac00' && ch <= '\ud7af') || (ch >= '\u1100' && ch <= '\u11ff') || (ch >= '\u3130' && ch <= '\u318f'))) {
    return 'noto-sans-kr';
  }
  if (tekens.some((ch) => TRADITIONEEL.has(ch))) return 'noto-sans-tc';
  return CJK_STANDAARD;
}

const richting = (ch: string) => bidi.getBidiCharTypeName(ch);
const isRtl = (tekst: string) => Array.from(tekst).some((ch) => { const r = richting(ch); return r === 'R' || r === 'AL'; });

// de richting van een regel: die van haar eerste sterke teken
function basisRtl(tekst: string): boolean {
  for (const ch of tekst) {
    const r = richting(ch);
    if (r === 'R' || r === 'AL') return true;
    if (r === 'L') return false;
  }
  return false;
}

// Pillow zet elk teken op een hele pixel: het begin van een stuk naar beneden afgerond, met een half naar boven in x en naar
// beneden in y (zo gemeten), en daarbinnen elk teken op zijn plek in 26.6, afgerond (`PIXEL` in `_imagingft.c`)
const pixel = (v: number) => Math.floor((v + 32) / 64);
function heel(v: number, x: boolean): number {
  const g = Math.trunc(v);
  const f = Math.round((v - g) * 64);
  return g + (x ? (f >= 32 ? 1 : 0) : (f > 32 ? 1 : 0));
}

type Glyphs = { font: number; glyph: number[]; x: number[]; dy: number[]; breedte: number };

export class Zetter {
  private hb: HarfBuzz;
  private lees: Lezer;
  private gewoon: [string, Reeksen][];
  private cjkPakketten: string[];
  // gedeeld tussen verzoeken via `Voorraad` (PLAN #34.2bq): een ander verzoek wacht nooit op een lettertype dat nog laadt
  private cjkBereik = new Voorraad<[string, Reeksen][]>();
  private keuze = new Map<string, string | null>();
  private faces = new Voorraad<number>();
  private fonts = new Voorraad<number>();
  private hoogtes = new Map<number, [number, number]>();
  private gezet = new Map<string, Glyphs>();
  readonly banden: Set<string>;
  // hoeveel bytes aan lettertypen deze HarfBuzz al vasthoudt (`deelbeeld.ts` begint boven een grens een nieuwe)
  geladen = 0;

  constructor(hb: HarfBuzz, voorraad: Voorraad, lees: Lezer) {
    this.hb = hb;
    this.lees = lees;
    this.gewoon = voorraad.lettertypen.map(([b, r]) => [b, leesReeksen(r)]);
    this.cjkPakketten = voorraad.cjk;
    this.banden = new Set(voorraad.banden);
  }

  // de tekens per lettertype van een pakket voor Chinees, Japans of Koreaans, pas als een teken erom vraagt
  private cjk(pakket: string): Promise<[string, Reeksen][]> {
    return this.cjkBereik.haal(pakket, () => this.lees(`bereik/${pakket}.json`).then((bytes) =>
      (JSON.parse(new TextDecoder().decode(bytes)) as [string, string][]).map(([f, r]): [string, Reeksen] => [f, leesReeksen(r)])));
  }

  // Het lettertype van een teken: eerst Geist en Noto Sans per schrift, dan de variant van Chinees, Japans of Koreaans
  // vóór de andere drie (`deelbeeld._bestand_voor`).
  async bestandVoor(ch: string, cjk = CJK_STANDAARD): Promise<string | null> {
    const sleutel = `${cjk}\u0000${ch}`;
    if (this.keuze.has(sleutel)) return this.keuze.get(sleutel)!;
    const code = ch.codePointAt(0)!;
    let uit: string | null = null;
    for (const [b, r] of this.gewoon) if (dekt(r, code)) { uit = b; break; }
    if (uit === null) {
      for (const p of [cjk, ...this.cjkPakketten.filter((q) => q !== cjk)]) {
        if (!this.cjkPakketten.includes(p)) continue;
        const hit = (await this.cjk(p)).find(([, r]) => dekt(r, code));
        if (hit) { uit = hit[0]; break; }
      }
    }
    if (this.keuze.size > 20000) this.keuze.clear();
    this.keuze.set(sleutel, uit);
    return uit;
  }

  // Heeft elk teken van deze tekst een lettertype? Anders geen bewering op het plaatje (`deelbeeld.kan_tonen`).
  async kanTonen(tekst: string): Promise<boolean> {
    if (!woorden(tekst).length) return false;
    const cjk = cjkVariant(tekst);
    for (const ch of tekst) if (!isWit(ch) && !onzichtbaar(ch) && !(await this.bestandVoor(ch, cjk))) return false;
    return true;
  }

  // De tekst in stukken per lettertypebestand; een spatie of een onzichtbaar teken blijft bij het stuk waar het in staat.
  async stukken(tekst: string): Promise<[string, string][]> {
    const stukken: [string, string][] = [];
    const cjk = cjkVariant(tekst);
    for (const ch of tekst) {
      const los = isWit(ch) || onzichtbaar(ch);
      const bestand = los ? GEIST : ((await this.bestandVoor(ch, cjk)) ?? GEIST);
      if (stukken.length && (los || stukken[stukken.length - 1][0] === bestand)) stukken[stukken.length - 1][1] += ch;
      else stukken.push([bestand, ch]);
    }
    return stukken;
  }

  private face(bestand: string): Promise<number> {
    return this.faces.haal(bestand, () => this.lees(`lettertypen/${bestand}`).then((bytes) => {
      this.geladen += bytes.byteLength;
      return this.hb.face(bytes);
    }));
  }

  private font(bestand: string, grootte: number, gewicht: number): Promise<number> {
    const sleutel = `${bestand}\u0000${grootte}\u0000${gewicht}`;
    return this.fonts.haal(sleutel, () => this.face(bestand).then((face) => this.hb.font(face, grootte, gewicht)));
  }

  // ascender en descender in hele pixels, zoals FreeType ze aan Pillow geeft (naar boven en naar beneden afgerond)
  private hoogte(font: number): [number, number] {
    let h = this.hoogtes.get(font);
    if (!h) {
      const [a, d] = this.hb.hoogte(font);
      h = [Math.ceil(a / 64), Math.floor(d / 64)];
      this.hoogtes.set(font, h);
    }
    return h;
  }

  // Eén stuk gezet zoals raqm dat doet: de richting per teken uit het bidi-algoritme met `rtl` als basis, elke reeks met
  // dezelfde richting apart gezet (met de rest van het stuk als context), en de reeksen in de volgorde op het scherm.
  private async zetStuk(bestand: string, grootte: number, gewicht: number, stuk: string, rtl: boolean): Promise<Glyphs> {
    const font = await this.font(bestand, grootte, gewicht);
    const sleutel = `${font}\u0000${rtl ? 1 : 0}\u0000${stuk}`;
    const klaar = this.gezet.get(sleutel);
    if (klaar) return klaar;
    const niveaus = bidi.getEmbeddingLevels(stuk, rtl ? 'rtl' : 'ltr').levels;
    const reeksen: [number, number, number][] = [];
    for (let i = 0; i < stuk.length; i++) {
      const laatste = reeksen[reeksen.length - 1];
      if (laatste && laatste[2] === niveaus[i]) laatste[1] = i + 1;
      else reeksen.push([i, i + 1, niveaus[i]]);
    }
    // L2: keer elke reeks van niveau k of hoger om, van het hoogste niveau tot het laagste oneven niveau
    const hoogste = Math.max(0, ...reeksen.map((r) => r[2]));
    const laagsteOneven = Math.min(...reeksen.map((r) => r[2]).filter((n) => n % 2 === 1), hoogste + 1);
    for (let k = hoogste; k >= laagsteOneven; k--) {
      for (let i = 0; i < reeksen.length;) {
        if (reeksen[i][2] < k) { i++; continue; }
        let j = i;
        while (j < reeksen.length && reeksen[j][2] >= k) j++;
        reeksen.splice(i, j - i, ...reeksen.slice(i, j).reverse());
        i = j;
      }
    }
    const uit: Glyphs = { font, glyph: [], x: [], dy: [], breedte: 0 };
    for (const [begin, eind, niveau] of reeksen) {
      const g = this.hb.zet(font, stuk, begin, eind - begin, niveau % 2 === 1);
      for (let i = 0; i < g.glyph.length; i++) {
        uit.glyph.push(g.glyph[i]);
        uit.x.push(uit.breedte + g.x[i]);
        uit.dy.push(g.dy[i]);
      }
      uit.breedte += g.breedte;
    }
    if (this.gezet.size > 4000) this.gezet.clear();
    this.gezet.set(sleutel, uit);
    return uit;
  }

  // de breedte van een stuk in 26.6, zoals `getlength` (zonder richting: raqm kiest haar uit het eerste sterke teken)
  private async lengte(bestand: string, stuk: string, grootte: number, gewicht: number): Promise<number> {
    return (await this.zetStuk(bestand, grootte, gewicht, stuk, basisRtl(stuk))).breedte;
  }

  async breedte(tekst: string, grootte: number, gewicht: number): Promise<number> {
    let som = 0;
    for (const [b, s] of await this.stukken(tekst)) som += await this.lengte(b, s, grootte, gewicht);
    return som / 64;
  }

  // Waar elk stuk komt: (x, bestand, stuk, richting); een regel van rechts naar links eindigt bij `rechts` en zet haar
  // stukken van rechts naar links, elk in zijn eigen richting (`deelbeeld._plaatsing`).
  async plaatsing(tekst: string, links: number, rechts: number | null, grootte: number, gewicht: number):
    Promise<[number, string, string, boolean][]> {
    const breed: [string, string, number][] = [];
    for (const [b, s] of await this.stukken(tekst)) breed.push([b, s, (await this.lengte(b, s, grootte, gewicht)) / 64]);
    const uit: [number, string, string, boolean][] = [];
    if (!basisRtl(tekst)) {
      let x = links;
      for (const [b, s, w] of breed) {
        uit.push([x, b, s, isRtl(s)]);
        x += w;
      }
      return uit;
    }
    let x = rechts !== null ? rechts : links + breed.reduce((n, [, , w]) => n + w, 0);
    for (const [b, s, w] of breed) {
      x -= w;
      uit.push([x, b, s, isRtl(s)]);
    }
    return uit;
  }

  // De tekst als SVG-pad (`deelbeeld._schrijf`): anker `la` zet de bovenkant van de ascender op y, `lm` het midden tussen
  // ascender en descender, zoals Pillow.
  async schrijf(x: number, y: number, tekst: string, grootte: number, gewicht: number, anker: 'la' | 'lm' = 'la',
                rechts: number | null = null): Promise<string> {
    const delen: string[] = [];
    for (const [plek, bestand, stuk, rtl] of await this.plaatsing(tekst, x, rechts, grootte, gewicht)) {
      const g = await this.zetStuk(bestand, grootte, gewicht, stuk, rtl);
      const [asc, desc] = this.hoogte(g.font);
      const basis = heel(y, false) + (anker === 'la' ? asc : pixel(Math.trunc((asc * 64 + desc * 64) / 2)));
      const begin = heel(plek, true);
      for (let i = 0; i < g.glyph.length; i++) {
        delen.push(this.hb.omtrek(g.font, g.glyph[i], begin + pixel(g.x[i]), basis - pixel(g.dy[i])));
      }
    }
    return delen.join('');
  }

  // De tekst in stukken om af te breken, elk met wat ervoor hoort (`deelbeeld._delen`).
  delen(tekst: string): [string, string][] {
    const delen: [string, string][] = [];
    for (const woord of woorden(tekst)) {
      let tussen = delen.length ? ' ' : '';
      let los = '';
      for (const ch of woord) {
        const vorige = delen.length ? Array.from(delen[delen.length - 1][0]).pop()! : '';
        if (MERK.test(ch) && !los && delen.length && GEEN_SPATIES.test(vorige)) {
          delen[delen.length - 1][0] += ch;
        } else if (GEEN_SPATIES.test(ch)) {
          if (los) {
            delen.push([los, tussen]);
            tussen = '';
            los = '';
          }
          delen.push([ch, tussen]);
          tussen = '';
        } else {
          los += ch;
        }
      }
      if (los) delen.push([los, tussen]);
    }
    return delen;
  }

  // De tekst in regels die passen; wat niet past wordt afgekapt met een beletselteken, na een heel woord, of in een
  // schrift zonder spaties na een heel teken (`deelbeeld._regels`).
  async regels(tekst: string, grootte: number, breedte: number, maxRegels: number, gewicht = 600): Promise<[string[], boolean]> {
    let regels: string[] = [];
    let huidig = '';
    let gebroken = false;
    for (const [stuk, tussen] of this.delen(tekst)) {
      const proef = huidig ? `${huidig}${tussen}${stuk}` : stuk;
      if ((await this.breedte(proef, grootte, gewicht)) <= breedte) {
        huidig = proef;
        continue;
      }
      if (huidig) regels.push(huidig);
      huidig = stuk;
      if (regels.length === maxRegels) {
        gebroken = true;
        break;
      }
    }
    if (!gebroken) {
      if (huidig) regels.push(huidig);
      if (regels.length <= maxRegels) return [regels, false];
    }
    regels = regels.slice(0, maxRegels);
    let laatste = regels[regels.length - 1];
    while (laatste && (await this.breedte(`${laatste}\u2026`, grootte, gewicht)) > breedte) {
      laatste = laatste.includes(' ') ? laatste.slice(0, laatste.lastIndexOf(' ')) : Array.from(laatste).slice(0, -1).join('');
    }
    regels[regels.length - 1] = `${laatste}\u2026`;
    return [regels, true];
  }
}
