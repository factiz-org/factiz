// De zoekmotor van het platform in TypeScript (B80, PLAN #34.2bo stap 4): dezelfde volgorde en dezelfde vragen aan de
// registers als `factiz_site/db.py` (`zoek_ruim`, `_keuze`, `_groep`, `_zoekbron`, `_berichtbron`, `suggesties`,
// `ingangen`, `doorsturen`, `aanvulling`, `verbeter`, de kenmerken en afkortingen in de vraag). Python rekent bij het
// openen; een Worker begint vaak opnieuw, dus hier wordt elk stuk pas gerekend als een vraag het nodig heeft, één keer per
// uitgave (`pub.eens`), en de schrijfwijzen van een naam alleen voor het woord dat gevraagd wordt.
import { type Db, type Waarde, eerste, rijen } from './db.ts';
import { TALEN } from './i18n.ts';
import { MET_VERTALING, PER_BLAD, RIJ, type Bewering, type Filters, type Publicatie, type Telling } from './publicatie.ts';
import { schoon, schoneRij, woorden } from './tekst.ts';
import { Voorraad } from './verzoek.ts';
import { AANHALINGSTEKENS, AANVUL_MIN, AFKORTING_ZEKER, BERICHT_DEEL, BERICHT_DEKKING, BERICHT_GEWOON, BERICHT_MAX, BERICHT_TERMEN,
  BERICHT_WOORDEN, BERICHT_ZWAK, type Deel, FAMILIE, GELEED, GEWOON, LEESTEKENS, LETTERS, MAX_KENMERK, MAX_TERMEN,
  MAX_VORMEN, RANDTEKENS, ZONDER_GRENS, ZONDER_SPATIES, adresvorm, af, afstand, alfabet, ascii, bijnaamTelt, indexvorm, isAfkorting,
  lijkt, losInHoofdletters, op, sleutel, toetsenbordvormen, zin, zoekdelen, zoektermen } from './zoeken-tekst.ts';
import { casefold, heeftWit, isalnum, isalpha, isascii, knip, lengte, rstrip, strip, stripTekens, vergelijk } from './zoeken-unicode.ts';

export const ZOEK_VOLGORDES = ['nieuw', 'oud', 'redacties'];
const VOLGORDES: Record<string, string> = {
  nieuw: 'p.laatste_datum DESC, p.nummer',
  oud: "p.laatste_datum = '', p.laatste_datum, p.nummer",
  redacties: 'p.redacties DESC, p.laatste_datum DESC, p.nummer',
};
const VERTAALTAAL = 'en';
const FACTIZ_LINK = /^factiz\.org\/(?:(?:nl|en|de|es|fr)\/)?fact-checks\/([0-9a-f]{16})$/;
const ZOEK_VAN = 'zoek JOIN pagina p ON p.nummer = zoek.nummer';
const ZOEK3_VAN = 'zoek3 JOIN pagina p ON p.nummer = zoek3.nummer';

// Een ingang: een thema, onderdeel, dossier, redactie of naam die een vraag kan zijn.
export type Wat = {
  soort: string; naam: Record<string, string> | string; aantal: number | null;
  thema?: string; onderdeel?: string; sleutel?: string; redactie?: string; nummer?: string; naamsoort?: string;
  pagina?: string; href?: string;
};
// Een land, redactie, thema of onderdeel in de vraag (#34.2ac).
export type Kenmerk = { soort: string; waarde: string; thema?: string };
type Afkorting = { nummer: string; tekst: string[]; hoofdletters: string[] };
// Eén stuk van de vraag voor het register: de voorwaarde met de andere vormen, die voor precies dit stuk, wat de tekst
// markeert, en bij een afkorting of kenmerk wat het is (in Python het vierde veld van het tupel).
type Groep = { match: string; exact: string; markeer: string[]; afkorting?: Afkorting; kenmerk?: { wat: Kenmerk; woord: string } };
// Waar de treffers vandaan komen: register, voorwaarden, waarden, volgorde van de beste treffer, waarden daarvan.
type Bron = [string, string[], Waarde[], string | null, Waarde[]];
type Keuze = { bron: Bron | null; deels: boolean; verbeterd: string | null; delen: Deel[]; markeer: string[];
  gelezen: (Kenmerk & { woord: string })[]; bericht: boolean };
export type Zoekuitslag = { rijen: Bewering[]; totaal: number; deels: boolean; facetten: Telling; zonder_filters: number;
  termen: string[]; markeer: string[]; verbeterd: string | null; gelezen: (Kenmerk & { woord: string })[]; bericht: boolean };

// --- de natuurlijke logaritme zoals Python hem geeft --------------------------------------------------------------------
// `Math.log` zit soms één bit naast de juiste afronding; de libm van macOS (Python) niet. Het gewicht van een woord in een
// geplakt bericht telt op tot een volgorde, dus hier de juist afgeronde waarde: de buren van `Math.log` naast een berekening
// in 200 bits.
const BITS = 200n;
const EEN = 1n << BITS;

function atanhVast(z: bigint): bigint {
  const z2 = (z * z) >> BITS;
  let t = z;
  let som = 0n;
  for (let k = 1n; t !== 0n; k += 2n) {
    som += t / k;
    t = (t * z2) >> BITS;
  }
  return som;
}
const LN2 = 2n * atanhVast(EEN / 3n);

function bitsVan(x: number): [bigint, number] {
  const d = new DataView(new ArrayBuffer(8));
  d.setFloat64(0, x);
  const hoog = d.getUint32(0);
  const exp = (hoog >>> 20) & 0x7ff;
  const mant = (BigInt(hoog & 0xfffff) << 32n) | BigInt(d.getUint32(4));
  return exp === 0 ? [mant, -1074] : [mant | (1n << 52n), exp - 1075];
}

function naast(x: number, richting: 1 | -1): number {
  const d = new DataView(new ArrayBuffer(8));
  d.setFloat64(0, x);
  const b = d.getBigUint64(0);
  d.setBigUint64(0, x === 0 ? 1n : (x > 0) === (richting > 0) ? b + 1n : b - 1n);
  return x === 0 && richting < 0 ? -d.getFloat64(0) : d.getFloat64(0);
}

function vast(x: number): bigint {
  const [m, e] = bitsVan(Math.abs(x));
  const verschuif = e + Number(BITS);
  const waarde = verschuif >= 0 ? m << BigInt(verschuif) : m >> BigInt(-verschuif);
  return x < 0 ? -waarde : waarde;
}

export function logPython(x: number): number {
  const y = Math.log(x);
  if (!(x > 0) || !Number.isFinite(x)) return y;
  const [m, e] = bitsVan(x);
  // x = m * 2^e met m een geheel getal: ln x = (e + 52) ln 2 + ln(m / 2^52), en ln(r) = 2 atanh((r-1)/(r+1))
  const r = 1n << 52n;
  const z = ((m - r) << BITS) / (m + r);
  const ln = BigInt(e + 52) * LN2 + 2n * atanhVast(z);
  const afwijking = (k: number) => { const a = vast(k) - ln; return a < 0n ? -a : a; };
  let beste = y;
  let kleinste = afwijking(y);
  for (const kandidaat of [naast(y, 1), naast(y, -1)]) {
    const a = afwijking(kandidaat);
    if (a < kleinste) {
      beste = kandidaat;
      kleinste = a;
    }
  }
  return beste;
}

// --- de filters als SQL (`Publicatie._waar`) ---------------------------------------------------------------------------
function waar(filters: Filters): [string[], Waarde[]] | null {
  const f = Object.fromEntries(Object.entries(filters).filter(([, v]) =>
    !(v === null || v === undefined || v === '' || (Array.isArray(v) && !v.length))));
  const rij = (w: unknown): string[] => (Array.isArray(w) ? w : [w as string]);
  const plekken = (n: number) => new Array(n).fill('?').join(', ');
  const delen: string[] = [];
  const waarden: Waarde[] = [];
  if ('taal' in f) {
    const talen = rij(f.taal);
    delen.push(`p.taal IN (${plekken(talen.length)})`);
    waarden.push(...talen);
  }
  if ('jaar' in f) {
    const jaren = rij(f.jaar);
    delen.push(`substr(p.laatste_datum, 1, 4) IN (${plekken(jaren.length)})`);
    waarden.push(...jaren);
  }
  if ('oordeel' in f) {
    const oordelen = rij(f.oordeel);
    const echte = oordelen.filter((o) => o !== 'geen');
    const stukken = [...(echte.length ? [`p.label IN (${plekken(echte.length)})`] : []),
      ...(oordelen.includes('geen') ? ['p.label IS NULL'] : [])];
    delen.push(`(${stukken.join(' OR ')})`);
    waarden.push(...echte);
  }
  if ('redactie' in f) {
    delen.push('p.nummer IN (SELECT pagina FROM check_ WHERE redactie = ?)');
    waarden.push(f.redactie as string);
  }
  for (const wat of ['soort', 'vorm']) {
    if (wat in f) {
      const keuze = rij(f[wat]);
      delen.push(`p.nummer IN (SELECT pagina FROM kenmerk WHERE ${wat} IN (${plekken(keuze.length)}))`);
      waarden.push(...keuze);
    }
  }
  if ('onderdeel' in f) {
    if (!('thema' in f)) return null;
    delen.push('p.thema = ? AND p.onderdeel = ?');
    waarden.push(f.thema as string, f.onderdeel as string);
  } else if ('thema' in f) {
    delen.push('(p.thema = ? OR p.tweede = ?)');
    waarden.push(f.thema as string, f.thema as string);
  }
  if ('land' in f) {
    delen.push('p.land = ?');
    waarden.push(f.land as string);
  }
  if ('naam' in f) {
    delen.push('p.nummer IN (SELECT pagina FROM pagina_naam WHERE naam = ?)');
    waarden.push(f.naam as string);
  }
  return [delen, waarden];
}

// Een vraag aan een register die mag mislukken (Python vangt daar `OperationalError`): dan niets.
async function probeer<T>(f: () => Promise<T>): Promise<T | null> {
  try {
    return await f();
  } catch {
    return null;
  }
}

// De volgende tekst na alles wat met `c` begint, in de volgorde van de database (BINARY, op codepunt): de grens van een
// reeks woorden met dezelfde beginletter. Een codepunt in de reeks voor UTF-16 bestaat niet als teken; dan het eerste erna.
function naBegin(c: string): string {
  const n = c.codePointAt(0)! + 1;
  return String.fromCodePoint(n >= 0xd800 && n <= 0xdfff ? 0xe000 : n);
}

// De adressen van de factcheckartikelen als vingerafdrukken van 64 bits, op volgorde, met de plek van hun pagina in de
// kolommen: de 103.427 adressen zelf kostten in een Worker 19 MB, dit 1,2 MB. Twee adressen met dezelfde afdruk weigert
// het bij het maken; dat een onbekend adres toevallig de afdruk van een bekend heeft, is zo'n 1 op 10^14 per link.
type Adressen = { hoog: Uint32Array; laag: Uint32Array; pagina: Uint32Array };

// cyrb53 (publiek domein), zonder de inkorting tot 53 bits aan het eind: twee keer 32 bits, over de UTF-16-eenheden.
function afdruk(s: string): [number, number] {
  let h1 = 0xdeadbeef;
  let h2 = 0x41c6ce57;
  for (let i = 0; i < s.length; i++) {
    const c = s.charCodeAt(i);
    h1 = Math.imul(h1 ^ c, 2654435761);
    h2 = Math.imul(h2 ^ c, 1597334677);
  }
  h1 = Math.imul(h1 ^ (h1 >>> 16), 2246822507) ^ Math.imul(h2 ^ (h2 >>> 13), 3266489909);
  h2 = Math.imul(h2 ^ (h2 >>> 16), 2246822507) ^ Math.imul(h1 ^ (h1 >>> 13), 3266489909);
  return [h2 >>> 0, h1 >>> 0];
}

// De plek in de kolommen van de pagina bij dit adres, of -1.
function paginaVan(a: Adressen, adres: string): number {
  const [h, l] = afdruk(adres);
  let lo = 0;
  let hi = a.hoog.length;
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    if (a.hoog[mid] < h || (a.hoog[mid] === h && a.laag[mid] < l)) lo = mid + 1;
    else hi = mid;
  }
  return lo < a.hoog.length && a.hoog[lo] === h && a.laag[lo] === l ? a.pagina[lo] : -1;
}
type Ingangen = { ingang: Map<string, Wat[]>; naamIngang: Map<string, Wat>; deel: Map<string, Wat[]>;
  suggestie: [string[], Wat][] };
type Schrijfgroepen = { groepen: string[][]; perVorm: Map<string, number[]> };

export class Zoeker {
  readonly pub: Publicatie;
  readonly db: Db;
  private hoeVaak = new Map<string, number>();                      // `tel` van de schrijfwijzen, op indexvorm
  // gedeeld tussen verzoeken via `Voorraad` (PLAN #34.2bq)
  private schrijf = new Voorraad<string[]>({ max: 4096 });
  private afkortingskeuze = new Voorraad<Afkorting | null>();
  private kenmerksets = new Map<string, string>();
  // wat de tabel `woord` zei (#37.16), per stuk van een vraag, per begin dat iemand typt en per tikfout: af is af, gedeeld
  // tussen verzoeken, zodat een Worker die een woord al eens opzocht niet opnieuw naar de database gaat
  private vormkennis = new Voorraad<{ bestaat: Set<string>; bijzonder: Map<string, string[]> }>({ max: 4096 });
  private begins = new Voorraad<{ bekend: boolean; top: string[] }>({ max: 4096 });
  private tikfouten = new Voorraad<string | null>({ max: 4096 });

  constructor(pub: Publicatie) {
    this.pub = pub;
    this.db = pub.db;
  }

  // --- wat de uitgave één keer levert ----------------------------------------------------------------------------------

  private naamvormen(): Promise<Map<string, string[]>> {
    return this.pub.eens('zoeken:naamvormen', async () => {
      const uit = new Map<string, string[]>();
      for (const r of await rijen<{ naam: string; vorm: string }>(this.db, 'SELECT naam, vorm FROM naam_vorm ORDER BY naam, vorm')) {
        if (!uit.has(r.naam)) uit.set(r.naam, []);
        uit.get(r.naam)!.push(r.vorm);
      }
      return uit;
    });
  }

  // Ingangen en suggesties (`Publicatie.__init__`): een zoekvraag die precies een thema, dossier, redactie of naam is.
  ingangen(): Promise<Ingangen> {
    return this.pub.eens('zoeken:ingangen', async () => {
      const ingang = new Map<string, Wat[]>();
      const naamIngang = new Map<string, Wat>();
      const zet = (tekst: string, wat: Wat) => {
        const s = sleutel(tekst);
        if (!s) return;
        if (!ingang.has(s)) ingang.set(s, []);
        if (!ingang.get(s)!.includes(wat)) ingang.get(s)!.push(wat);
      };
      for (const th of await this.pub.themas()) {
        const wat: Wat = { soort: 'thema', thema: th.sleutel, naam: th.naam, aantal: th.aantal };
        for (const taal of TALEN) zet(th.naam[taal], wat);
        for (const o of th.onderdelen) {
          const deel: Wat = { soort: 'onderdeel', thema: th.sleutel, onderdeel: o.sleutel, naam: o.naam, aantal: o.aantal };
          for (const taal of TALEN) zet(o.naam[taal], deel);
        }
      }
      for (const d of await this.pub.dossiers()) {
        const wat: Wat = { soort: 'dossier', sleutel: d.sleutel, naam: d.naam, aantal: d.stand.factchecks };
        for (const taal of TALEN) zet(d.naam[taal], wat);
      }
      for (const [redactie, n] of await this.pub.redacties()) {
        zet(redactie, { soort: 'redactie', redactie, naam: redactie, aantal: n });
      }
      const delen = new Map<string, Wat[]>();
      for (const n of (await this.pub.namen()).values()) {
        const wat: Wat = { soort: 'naam', nummer: n.nummer, naamsoort: n.soort, naam: n.naam, aantal: n.paginas };
        naamIngang.set(n.nummer, wat);
        for (const taal of TALEN) {
          zet(n.naam[taal], wat);
          if (n.soort === 'persoon') {
            for (const stuk of zoektermen(n.naam[taal])) {
              const s = alfabet(stuk);
              if (lengte(s) < 4) continue;
              if (!delen.has(s)) delen.set(s, []);
              if (!delen.get(s)!.includes(wat)) delen.get(s)!.push(wat);
            }
          }
        }
      }
      // een deel van de naam van een persoon: de vaakst genoemde eerst
      const deel = new Map([...delen].map(([s, lijst]) => [s, [...lijst].sort((a, b) => (b.aantal ?? 0) - (a.aantal ?? 0))]));
      // per ingang de woorden van haar naam in elke taal, zonder accenten, één keer
      const suggestie: [string[], Wat][] = [];
      const gezien = new Set<Wat>();
      for (const lijst of ingang.values()) {
        for (const wat of lijst) {
          if (gezien.has(wat)) continue;
          gezien.add(wat);
          const namen = typeof wat.naam === 'object' ? Object.values(wat.naam) : [wat.naam];
          const set = new Set<string>();
          for (const naam of namen) {
            for (const w of zoektermen(naam)) {
              const s = stripTekens(alfabet(w), LEESTEKENS);
              if (s) set.add(s);
            }
          }
          suggestie.push([[...set], wat]);
        }
      }
      return { ingang, naamIngang, deel, suggestie };
    });
  }

  // De namen die een stuk van de vraag verruimen: land, redactie, thema, onderdeel (`_bouw_kenmerknamen`).
  kenmerknamen(): Promise<Map<string, Kenmerk>> {
    return this.pub.eens('zoeken:kenmerken', async () => {
      const uit = new Map<string, Kenmerk>();
      const dubbel = new Set<string>();
      const gelijk = (a: Kenmerk, b: Kenmerk) => a.soort === b.soort && a.waarde === b.waarde && a.thema === b.thema;
      const zet = (naam: string, wat: Kenmerk) => {
        const stukken = zoektermen(naam).map((w) => stripTekens(alfabet(w), LEESTEKENS)).filter(Boolean);
        if (!stukken.length || stukken.length > MAX_KENMERK) return;
        const s = stukken.join('\u0000');
        if (uit.has(s) && !gelijk(uit.get(s)!, wat)) dubbel.add(s);
        if (!uit.has(s)) uit.set(s, wat);
      };
      const landen = await this.pub.landen();
      for (const [code] of (await this.pub.facetten()).land) {
        for (const taal of TALEN) zet(landen[code][taal], { soort: 'land', waarde: code });
      }
      for (const [redactie] of await this.pub.redacties()) zet(redactie, { soort: 'redactie', waarde: redactie });
      for (const th of await this.pub.themas()) {
        for (const taal of TALEN) {
          zet(th.naam[taal], { soort: 'thema', waarde: th.sleutel });
          for (const o of th.onderdelen) zet(o.naam[taal], { soort: 'onderdeel', waarde: o.sleutel, thema: th.sleutel });
        }
      }
      for (const s of dubbel) uit.delete(s);
      return uit;
    });
  }

  // De groepen schrijfwijzen van één naam (`_bouw_schrijfwijzen`, zonder te tellen): per groep de woorden, op volgorde.
  private schrijfgroepen(): Promise<Schrijfgroepen> {
    return this.pub.eens('zoeken:schrijfgroepen', async () => {
      const ruw: string[][] = [];
      const vormen = await this.naamvormen();
      for (const [nummer, n] of await this.pub.namen()) {
        const stukken = TALEN.map((taal) => zoektermen(n.naam[taal]));
        const bijnamen = vormen.get(nummer) ?? [];
        if (n.soort === 'persoon') {
          const laatste = stukken.filter((s) => s.length).map((s) => stripTekens(s[s.length - 1], LEESTEKENS));
          if (!laatste.length) continue;
          // de meest gebruikte achternaam; bij gelijk aantal de eerste (`Counter.most_common(1)`)
          const tel = new Map<string, number>();
          for (const w of laatste) tel.set(ascii(w), (tel.get(ascii(w)) ?? 0) + 1);
          let vaakst = '';
          let hoogst = 0;
          for (const [w, k] of tel) {
            if (k > hoogst) {
              vaakst = w;
              hoogst = k;
            }
          }
          const grens = Math.max(2, Math.floor(lengte(vaakst) / 3));
          const kern = laatste.filter((w) => afstand(ascii(w), vaakst, grens) <= grens);
          const verder = laatste.filter((w) => !kern.includes(w));
          for (const s of bijnamen.map(zoektermen)) {
            if (s.length && !s[s.length - 1].endsWith('.')) verder.push(stripTekens(s[s.length - 1], LEESTEKENS));
          }
          ruw.push([...kern, ...verder.filter((w) => lijkt(w, kern))]);
        } else {
          const enkel = stukken.filter((s) => s.length === 1).map((s) => s[0]);
          ruw.push([...enkel, ...bijnamen.filter((v) => bijnaamTelt(v, enkel)).map((v) => stripTekens(strip(v), LEESTEKENS))]);
        }
      }
      for (const namen of Object.values(await this.pub.landen())) {
        ruw.push(TALEN.map((taal) => zoektermen(namen[taal])).filter((s) => s.length === 1).map((s) => s[0]));
      }
      const groepen: string[][] = [];
      const perVorm = new Map<string, number[]>();
      for (const groep0 of ruw) {
        const groep = [...new Set(groep0.map((w) => stripTekens(w, LEESTEKENS)))].sort(vergelijk)
          .filter((w) => lengte(ascii(w)) >= 4 && Array.from(w).some((t) => isalpha(t)));
        if (new Set(groep.map(indexvorm)).size < 2) continue;
        const i = groepen.length;
        groepen.push(groep);
        for (const a of new Set(groep.map(ascii))) {
          if (!perVorm.has(a)) perVorm.set(a, []);
          perVorm.get(a)!.push(i);
        }
      }
      return { groepen, perVorm };
    });
  }

  private async telVorm(w: string): Promise<number> {
    const vorm = indexvorm(w);
    if (!this.hoeVaak.has(vorm)) {
      const r = await probeer(() => eerste<{ n: number }>(this.db, 'SELECT COUNT(*) AS n FROM zoek WHERE zoek MATCH ?', zin(w)));
      this.hoeVaak.set(vorm, r?.n ?? 0);
    }
    return this.hoeVaak.get(vorm)!;
  }

  // De schrijfwijzen die een stuk (zonder bijzondere letters) erbij krijgt: alleen voor dit stuk gerekend, met dezelfde
  // regels en in dezelfde volgorde als `_bouw_schrijfwijzen` voor de hele uitgave.
  schrijfwijzen(a: string): Promise<string[]> {
    return this.schrijf.haal(a, async () => {
      const { groepen, perVorm } = await this.schrijfgroepen();
      const andere: string[] = [];
      for (const i of perVorm.get(a) ?? []) {
        const groep = groepen[i];
        const tellen = new Map<string, number>(await Promise.all(groep.map(async (w) => [w, await this.telVorm(w)] as const)));
        const gewoon = new Set(groep.filter((w) => tellen.get(w)! > GEWOON * Math.max(1,
          ...groep.filter((o) => indexvorm(o) !== indexvorm(w)).map((o) => tellen.get(o)!))));
        for (const w of groep) {
          if (ascii(w) !== a) continue;
          const eigen = Math.max(...groep.filter((o) => ascii(o) === ascii(w)).map((o) => tellen.get(o)!));
          for (const o of groep) {
            if (ascii(o) !== a && !gewoon.has(o) && tellen.get(o)! >= eigen && !andere.includes(o)) andere.push(o);
          }
        }
      }
      return andere;
    });
  }

  // De afkortingen van 2 of 3 letters van de namen, met de namen die haar dragen (`_bouw_afkortingen`).
  private afkortingen(): Promise<Map<string, Set<string>>> {
    return this.pub.eens('zoeken:afkortingen', async () => {
      const uit = new Map<string, Set<string>>();
      const vormen = await this.naamvormen();
      for (const [nummer, n] of await this.pub.namen()) {
        for (const v of new Set([...Object.values(n.naam), ...(vormen.get(nummer) ?? [])])) {
          if (!isAfkorting(v, 3)) continue;
          const a = strip(v);
          if (!uit.has(a)) uit.set(a, new Set());
          uit.get(a)!.add(nummer);
        }
      }
      return uit;
    });
  }

  // Per afkorting de pagina's waar ze los in hoofdletters staat (`_bouw_hoofdletters`): de hele tekst van het register
  // één keer gelezen, in stukken. Lukt dat niet, dan is de index leeg en geldt geen afkorting als naam.
  hoofdletters(): Promise<Map<string, Set<string>>> {
    return this.pub.eens('zoeken:hoofdletters', async () => {
      const index = new Map<string, Set<string>>();
      try {
        const gezocht = new Set((await this.afkortingen()).keys());
        let na = -1;
        for (;;) {
          const stuk = await rijen<{ id: number; c0: string; c1: string | null }>(this.db,
            'SELECT id, c0, c1 FROM zoek_content WHERE id > ? ORDER BY id LIMIT 4000', na);
          if (!stuk.length) break;
          for (const r of stuk) {
            for (const w of losInHoofdletters(r.c1 || '', gezocht)) {
              if (!index.has(w)) index.set(w, new Set());
              index.get(w)!.add(r.c0);
            }
          }
          na = stuk[stuk.length - 1].id;
        }
        return index;
      } catch {
        return new Map();
      }
    });
  }

  // Welke van deze vormen als woord in het zoekregister staan, en per vorm de woorden met een bijzondere letter die iemand
  // zo typt (straße onder strasse): uit de tabel `woord` (#37.16), in één vraag, op de volgorde van de woorden.
  private async woorden(vormen: string[]): Promise<{ bestaat: Set<string>; bijzonder: Map<string, string[]> }> {
    const bestaat = new Set<string>();
    const bijzonder = new Map<string, string[]>();
    if (!vormen.length) return { bestaat, bijzonder };
    const gevraagd = new Set(vormen);
    const lijst = JSON.stringify([...gevraagd]);
    for (const r of await rijen<{ term: string; gewoon: string | null }>(this.db,
      'SELECT term, gewoon FROM woord WHERE term IN (SELECT value FROM json_each(?)) OR gewoon IN (SELECT value FROM json_each(?)) '
      + 'ORDER BY term', lijst, lijst)) {
      if (gevraagd.has(r.term)) bestaat.add(r.term);
      if (r.gewoon !== null && gevraagd.has(r.gewoon)) {
        if (!bijzonder.has(r.gewoon)) bijzonder.set(r.gewoon, []);
        bijzonder.get(r.gewoon)!.push(r.term);
      }
    }
    return { bestaat, bijzonder };
  }

  // De adressen van de factcheckartikelen, voor een geplakte link (`_adressen`): het eerste adres wint, in de volgorde van
  // de pagina's en hun checks, zoals in Python.
  private adressen(): Promise<Adressen> {
    return this.pub.eens('zoeken:adresafdrukken', async () => {
      const { plek } = await this.pub.kolommen();
      const eerst = new Map<string, number>();
      for (const { pagina, url } of await rijen<{ pagina: string; url: string }>(this.db,
        'SELECT pagina, url FROM check_ ORDER BY pagina, volg')) {
        const v = adresvorm(url);
        if (!v) continue;
        const p = plek.get(pagina);
        if (p === undefined) throw new Error(`een check van pagina ${pagina}, die niet in de kolommen staat`);
        for (const k of v) if (!eerst.has(k)) eerst.set(k, p);
      }
      const rij = [...eerst].map(([k, p]): [number, number, number] => [...afdruk(k), p])
        .sort((a, b) => a[0] - b[0] || a[1] - b[1]);
      for (let i = 1; i < rij.length; i++) {
        if (rij[i][0] === rij[i - 1][0] && rij[i][1] === rij[i - 1][1]) throw new Error('twee adressen met dezelfde afdruk');
      }
      return { hoog: Uint32Array.from(rij, (r) => r[0]), laag: Uint32Array.from(rij, (r) => r[1]),
        pagina: Uint32Array.from(rij, (r) => r[2]) };
    });
  }

  // --- een vraag -------------------------------------------------------------------------------------------------------

  // Is dit stuk, zo getypt, de afkorting van een naam (`afkorting`)? Eén keer gerekend per afkorting.
  afkorting(stuk: string): Promise<Afkorting | null> {
    const a = stripTekens(stuk || '', LEESTEKENS);
    if (!isAfkorting(a, 3)) return Promise.resolve(null);
    return this.afkortingskeuze.haal(a, () => this.rekenAfkorting(a));
  }

  private async rekenAfkorting(a: string): Promise<Afkorting | null> {
    const afk = await this.afkortingen();
    const namen = afk.get(a) ?? new Set<string>();
    if (namen.size !== 1) return null;
    const nummer = [...namen][0];
    const gekoppeld = new Set((await rijen<{ pagina: string }>(this.db, 'SELECT pagina FROM pagina_naam WHERE naam = ?', nummer))
      .map((r) => r.pagina));
    const zeker = (paginas: Set<string>) => [...paginas].filter((p) => gekoppeld.has(p)).length >= AFKORTING_ZEKER * paginas.size;
    const index = await this.hoofdletters();
    const hoofd = index.get(a) ?? new Set<string>();
    if (!gekoppeld.size || !(!hoofd.size || zeker(hoofd))) return null;
    const n = (await this.pub.namen()).get(nummer)!;
    const namen_ = Object.values(n.naam).filter((v) => !isAfkorting(v, 3));
    const hoofdletters = new Set(hoofd);
    const tekst = [...new Set(namen_)].sort(vergelijk);
    const enkel = namen_.map(zoektermen).filter((st) => st.length === 1).map((st) => st[0]);
    for (const v0 of [...new Set((await this.naamvormen()).get(nummer) ?? [])].sort(vergelijk)) {
      const v = strip(v0);
      if (isAfkorting(v, 3)) {
        if (v !== a && (afk.get(v)?.size ?? 0) === 1) {
          const hb = index.get(v) ?? new Set<string>();
          if (hb.size && zeker(hb)) for (const p of hb) hoofdletters.add(p);
        }
        continue;
      }
      if (tekst.includes(v) || (zoektermen(v).length < 2 && !bijnaamTelt(v, enkel))) continue;
      const paginas = await probeer(async () => new Set((await rijen<{ nummer: string }>(this.db,
        'SELECT nummer FROM zoek WHERE zoek MATCH ?', zin(v))).map((r) => r.nummer)));
      if (paginas === null) continue;
      if (paginas.size && zeker(paginas)) tekst.push(v);
    }
    return { nummer, tekst, hoofdletters: [...hoofdletters].sort(vergelijk) };
  }

  // Eén stuk van de vraag voor het register op woorden, met de andere vormen erbij (`_groep`).
  async groep(stuk: string, precies: boolean): Promise<Groep> {
    const exact = zin(stuk);
    if (precies) return { match: exact, exact, markeer: [stuk] };
    const afk = await this.afkorting(stuk);
    if (afk) {
      const match = afk.tekst.length ? `(${afk.tekst.map(zin).join(' OR ')})` : exact;
      return { match, exact: match, markeer: [stuk, ...afk.tekst], afkorting: afk };
    }
    const a = stripTekens(ascii(stuk), LEESTEKENS);
    // elke vorm die hieronder wordt nagevraagd, in één keer naar de database (#37.16), tegelijk met de schrijfwijzen
    const geleed = GELEED.test(a) ? a.match(/[a-z0-9]+/g)!.join('') : null;
    const vormen: string[] = geleed === null ? [] : [geleed];
    if (LETTERS.test(a)) {
      for (const b of [a, ...af(a)]) vormen.push(b, ...op(b));
      if (a.length >= 8) for (let i = 4; i < a.length - 3; i++) vormen.push(a.slice(0, i), a.slice(i));
    }
    const [bekend, namen] = await Promise.all([this.vormkennis.haal(a, () => this.woorden(vormen)), this.schrijfwijzen(a)]);
    const bestaand = (w: string) => [...(bekend.bestaat.has(w) ? [w] : []), ...(bekend.bijzonder.get(w) ?? [])];
    const woorden_: string[] = [];
    const zinnen: string[] = [];
    let begin: string | null = null;
    if (geleed !== null) woorden_.push(...bestaand(geleed));
    else if (/^[a-z0-9]+$/.test(a) && !/^[a-z]+$/.test(a) && !/^[0-9]+$/.test(a)) zinnen.push(a.match(/[a-z]+|[0-9]+/g)!.join(' '));
    if (LETTERS.test(a)) {
      woorden_.push(...bestaand(a));
      const basis = [a, ...[...af(a)].filter((k) => bestaand(k).length).sort(vergelijk)];
      for (const b of basis) for (const v of [...new Set([b, ...op(b)])].sort(vergelijk)) woorden_.push(...bestaand(v));
      const kortste = basis.reduce((x, y) => (y.length < x.length ? y : x));
      if (kortste.length >= 6 && await this.familie(kortste) <= FAMILIE) begin = kortste;
      if (a.length >= 8) {
        for (let i = 4; i < a.length - 3; i++) {
          const links = bestaand(a.slice(0, i));
          const rechts = bestaand(a.slice(i));
          if (links.length && rechts.length) zinnen.push(`${links[0]} ${rechts[0]}`);
        }
      }
    }
    zinnen.push(...namen, ...toetsenbordvormen(stuk));
    const eigen = indexvorm(stuk);
    let andere: string[] = [];
    for (const x of [...woorden_, ...zinnen]) if (indexvorm(x) !== eigen && !andere.includes(x)) andere.push(x);
    andere = andere.slice(0, MAX_VORMEN);
    if (!andere.length && !begin) return { match: exact, exact, markeer: [stuk] };
    const match = `(${[exact, ...andere.map(zin), ...(begin ? [`${zin(begin)}*`] : [])].join(' OR ')})`;
    return { match, exact, markeer: [stuk, ...andere, ...(begin ? [`${begin}*`] : [])] };
  }

  // In hoeveel beweringen een woord staat dat met `begin` begint, tot één boven `FAMILIE` (`_familie`).
  private async familie(begin: string): Promise<number> {
    return (await eerste<{ n: number }>(this.db, 'SELECT COUNT(*) AS n FROM (SELECT 1 FROM zoek WHERE zoek MATCH ? LIMIT ?)',
      `${zin(begin)}*`, FAMILIE + 1))!.n;
  }

  // De stukken met een land, redactie, thema of onderdeel samengenomen tot één stuk (`_lees_kenmerken`).
  private async leesKenmerken(delen: Deel[]): Promise<[Deel[], Map<number, Kenmerk>]> {
    const namen = await this.kenmerknamen();
    const uit: Deel[] = [];
    const kenmerken = new Map<number, Kenmerk>();
    let i = 0;
    while (i < delen.length) {
      let gevonden: [number, Kenmerk] | null = null;
      if (!delen[i][1]) {
        for (let n = Math.min(MAX_KENMERK, delen.length - i); n > 0; n--) {
          const stuk = delen.slice(i, i + n);
          if (stuk.some(([, p]) => p)) continue;
          const s = stuk.map(([t]) => stripTekens(alfabet(t), LEESTEKENS)).join('\u0000');
          if (namen.has(s) && !(n === 1 && await this.afkorting(stuk[0][0]) !== null)) {
            gevonden = [n, namen.get(s)!];
            break;
          }
        }
      }
      if (gevonden) {
        const [n, wat] = gevonden;
        kenmerken.set(uit.length, wat);
        uit.push([delen.slice(i, i + n).map(([t]) => t).join(' '), false]);
        i += n;
      } else {
        uit.push(delen[i]);
        i++;
      }
    }
    return [uit, kenmerken];
  }

  // Het stuk verruimd: wat het woord vindt, of het kenmerk (`_kenmerk_voorwaarde`).
  private async kenmerkVoorwaarde(wat: Kenmerk, match: string): Promise<[string, Waarde[]]> {
    const sleutel_ = JSON.stringify([wat.soort, wat.waarde, wat.thema ?? '', match]);
    let lijst = this.kenmerksets.get(sleutel_);
    if (lijst === undefined) {
      const filters: Filters = { land: { land: wat.waarde }, redactie: { redactie: wat.waarde }, thema: { thema: wat.waarde },
        onderdeel: { thema: wat.thema ?? null, onderdeel: wat.waarde } }[wat.soort]!;
      const m = await this.pub.masker(filters);
      const k = await this.pub.kolommen();
      for (const { nummer } of await rijen<{ nummer: string }>(this.db, 'SELECT nummer FROM zoek WHERE zoek MATCH ?', match)) {
        const p = k.plek.get(nummer);
        if (p !== undefined) m[p] = 1;
      }
      const nummers: string[] = [];
      for (let i = 0; i < k.n; i++) if (m[i]) nummers.push(k.nummer[i]);
      lijst = JSON.stringify(nummers);
      if (this.kenmerksets.size >= 64) this.kenmerksets.delete(this.kenmerksets.keys().next().value!);
      this.kenmerksets.set(sleutel_, lijst);
    }
    return ['p.nummer IN (SELECT value FROM json_each(?))', [lijst]];
  }

  // De stukken en hun groepen; een kenmerk als één verruimd stuk, behalve `letterlijk` (`_groepen`).
  private async groepen(delen0: Deel[], letterlijk: boolean): Promise<[Deel[], Groep[]]> {
    let delen = delen0;
    let kenmerken = new Map<number, Kenmerk>();
    if (!letterlijk) [delen, kenmerken] = await this.leesKenmerken(delen);
    // tegelijk: hun vragen aan de database gaan samen (`bundel.js`), niet een keer heen en terug per stuk
    const groepen: Groep[] = await Promise.all(delen.map(([t, p]) => this.groep(t, p)));
    for (const [i, wat] of kenmerken) {
      const g = groepen[i];
      groepen[i] = { match: g.match, exact: g.exact, markeer: g.markeer, kenmerk: { wat, woord: delen[i][0] } };
    }
    return [delen, groepen];
  }

  // Waar de treffers van een vraag vandaan komen (`_zoekbron`).
  async zoekbron(delen: Deel[], groepen0: Groep[] | null = null, ruim = false): Promise<Bron | null> {
    const termen = delen.map(([t]) => t);
    let groepen = groepen0;
    if (groepen === null) {
      groepen = [];
      for (const [t, p] of delen) groepen.push(await this.groep(t, p));
    }
    const woordbron = async (match: string, exact: string): Promise<Bron | null> => {
      const er = await probeer(() => eerste(this.db, 'SELECT 1 AS n FROM zoek WHERE zoek MATCH ? LIMIT 1', match));
      if (!er) return null;
      if (match === exact) return [ZOEK_VAN, ['zoek MATCH ?'], [match], 'zoek.rank, p.nummer', []];
      return [ZOEK_VAN, ['zoek MATCH ?'], [match], 'p.nummer NOT IN (SELECT nummer FROM zoek WHERE zoek MATCH ?), zoek.rank, p.nummer',
        [exact]];
    };
    if (ruim) {
      if (termen.length < 2) return null;
      return woordbron(groepen.map((g) => g.match).join(' OR '), groepen.map((g) => g.exact).join(' OR '));
    }
    const namen = groepen.filter((g) => g.afkorting || g.kenmerk);
    if (namen.length) {
      const voorwaarden: string[] = [];
      const waarden: Waarde[] = [];
      for (const g of namen) {
        if (g.kenmerk) {
          const [voorwaarde, w] = await this.kenmerkVoorwaarde(g.kenmerk.wat, g.match);
          voorwaarden.push(voorwaarde);
          waarden.push(...w);
          continue;
        }
        voorwaarden.push('(p.nummer IN (SELECT pagina FROM pagina_naam WHERE naam = ?) OR p.nummer IN '
          + '(SELECT nummer FROM zoek WHERE zoek MATCH ?) OR p.nummer IN (SELECT value FROM json_each(?)))');
        waarden.push(g.afkorting!.nummer, g.match, JSON.stringify(g.afkorting!.hoofdletters));
      }
      const rest = groepen.filter((g) => !(g.afkorting || g.kenmerk));
      let bron: Bron;
      if (!rest.length) {
        bron = ['pagina p', voorwaarden, waarden, null, []];
        if (namen.some((g) => g.kenmerk)) {
          // alleen kenmerken: wat het woord vond eerst, daarna de rest van het land, thema of de redactie
          bron = ['pagina p', voorwaarden, waarden,
            `p.nummer NOT IN (SELECT nummer FROM zoek WHERE zoek MATCH ?), ${VOLGORDES.nieuw}`,
            [namen.map((g) => g.match).join(' AND ')]];
        }
      } else {
        const b = await woordbron(rest.map((g) => g.match).join(' AND '), rest.map((g) => g.exact).join(' AND '));
        if (!b) return null;
        bron = [b[0], [...b[1], ...voorwaarden], [...b[2], ...waarden], b[3], b[4]];
      }
      // samen niets: dan geen bron, zodat een spelfout of een deel van de woorden nog kan
      if (!(await eerste(this.db, `SELECT 1 AS n FROM ${bron[0]} WHERE ${bron[1].join(' AND ')} LIMIT 1`, ...bron[2]))) return null;
      return bron;
    }
    // het register op woorden en dat op drietallen tegelijk: twee kleine vragen in één keer heen en terug (#37.16); de
    // eerste die iets vindt telt, zoals na elkaar
    const drie = termen.filter((t) => lengte(t) >= 3);
    const match3 = drie.map(zin).join(' ');
    const [b, er3] = await Promise.all([
      termen.every((t) => ZONDER_GRENS.test(t)) ? Promise.resolve(null)
        : woordbron(groepen.map((g) => g.match).join(' AND '), groepen.map((g) => g.exact).join(' AND ')),
      drie.length ? probeer(() => eerste(this.db, 'SELECT 1 AS n FROM zoek3 WHERE zoek3 MATCH ? LIMIT 1', match3))
        : Promise.resolve(null)]);
    if (b) return b;
    if (er3) return [ZOEK3_VAN, ['zoek3 MATCH ?'], [match3], 'zoek3.rank, p.nummer', []];
    const kort = termen.filter((t) => lengte(t) >= 2 || ZONDER_GRENS.test(t));
    if (kort.length && kort.some((t) => lengte(t) <= 2)) {
      const lijkt_ = kort.map(() => "zoek3.tekst LIKE ? ESCAPE '\\'");
      const patronen = kort.map((t) => `%${t.replaceAll('\\', '\\\\').replaceAll('%', '\\%').replaceAll('_', '\\_')}%`);
      if (await eerste(this.db, `SELECT 1 AS n FROM zoek3 WHERE ${lijkt_.join(' AND ')} LIMIT 1`, ...patronen)) {
        return [ZOEK3_VAN, lijkt_, patronen, null, []];
      }
    }
    return null;
  }

  // De rijen van één blad en het totaal, met de filters erbij (`_uit_bron`).
  private async uitBron(bron: Bron, blad: number, vertaal: string, sorteer: string | null, filters: Filters):
    Promise<{ rijen: Bewering[]; totaal: number }> {
    const [van, basis, basiswaarden, rang, rangwaarden0] = bron;
    const stukken = waar(filters);
    if (!stukken) return { rijen: [], totaal: 0 };
    const voorwaarde = [...basis, ...stukken[0]].join(' AND ');
    const waarden = [...basiswaarden, ...stukken[1]];
    const gekozen = sorteer !== null && ZOEK_VOLGORDES.includes(sorteer);
    const volgorde = gekozen || !rang ? VOLGORDES[gekozen ? sorteer! : 'nieuw'] : rang;
    const rangwaarden = gekozen || !rang ? [] : rangwaarden0;
    // het totaal en de rijen tegelijk: in één keer heen en terug (#37.16)
    const [telling, normaal, kenmerk, ruw] = await Promise.all([
      eerste<{ n: number }>(this.db, `SELECT COUNT(*) AS n FROM ${van} WHERE ${voorwaarde}`, ...waarden),
      this.pub.normaalVan(), this.pub.kenmerkVan(),
      rijen<Record<string, string | number | null>>(this.db,
        `SELECT ${RIJ} FROM ${van}${MET_VERTALING} WHERE ${voorwaarde} ORDER BY ${volgorde} LIMIT ? OFFSET ?`,
        vertaal, ...waarden, ...rangwaarden, PER_BLAD, (Math.max(1, blad) - 1) * PER_BLAD)]);
    const totaal = telling!.n;
    const uit = ruw.map((r) => {
      const rij = schoneRij(r) as Bewering;
      rij.normaal = normaal.get(rij.nummer as string) ?? null;
      rij.kenmerk = kenmerk.get(rij.nummer as string) ?? null;
      return rij;
    });
    return { rijen: uit, totaal };
  }

  // Een spelfout verbeterd: het dichtstbijzijnde woord met dezelfde beginletter in minstens twee beweringen (`verbeter`).
  async verbeter(termen: string[]): Promise<string[] | null> {
    // elk woord tegelijk: hun vragen aan de database gaan samen (`bundel.js`)
    const beter = await Promise.all(termen.map((term) => this.verbeterWoord(term)));
    return beter.some((b) => b !== null) ? beter.map((b, i) => b ?? termen[i]) : null;
  }

  // Eén woord verbeterd, of niets: de kandidaten met dezelfde beginletter en bijna dezelfde lengte uit de tabel `woord`,
  // op lengte en dan op de volgorde van de woorden, zoals Python ze langsloopt (#37.16).
  private async verbeterWoord(term: string): Promise<string | null> {
    const w = isascii(term) ? alfabet(term) : casefold(term);
    const tekens = Array.from(w);
    if (tekens.length < 4 || !isalpha(w) || ZONDER_SPATIES.test(w)) return null;
    return this.tikfouten.haal(`${w}\n${casefold(term)}`, () => this.verbeterNieuw(term, w, tekens));
  }

  private async verbeterNieuw(term: string, w: string, tekens: string[]): Promise<string | null> {
    const grens = tekens.length <= 5 ? 1 : 2;
    const [bekend, emmer] = await Promise.all([
      eerste(this.db, 'SELECT 1 AS n FROM woord WHERE term IN (?, ?)', w, casefold(term)),
      this.tikfoutKandidaten(tekens[0])]);
    if (bekend) return null;
    let beste: [number, number, string] | null = null;
    const [van, tot] = [tekens.length - grens, tekens.length + grens];
    for (let i = 0; i < emmer.term.length; i++) {
      const l = emmer.lengte[i];
      if (l < van) continue;
      if (l > tot) break;                       // op lengte gesorteerd: verder komt niets meer
      const kandidaat = emmer.term[i];
      const doc = emmer.doc[i];
      const d = afstand(tekens, kandidaat, grens);
      if (d <= grens && (beste === null || d < beste[0] || (d === beste[0] && -doc < beste[1]))) beste = [d, -doc, kandidaat];
    }
    return beste ? beste[2] : null;
  }

  // De kandidaten voor een tikfout met deze beginletter (`verbeter`): de woorden in minstens twee beweringen, alleen letters,
  // op lengte en dan op de volgorde van de woorden, zoals Python ze per beginletter en lengte langsloopt. Eén stuk per
  // beginletter, vooraf in het geheugen (`scripts/geheugen.ts`): anders haalt een tikfout duizenden woorden uit D1 (#37.16).
  tikfoutKandidaten(begin: string): Promise<{ term: string[]; doc: Uint32Array; lengte: Uint16Array }> {
    return this.pub.eens(`zoeken:tikfout:${begin}`, async () => {
      const r = await rijen<{ term: string; doc: number; lengte: number }>(this.db,
        'SELECT term, doc, lengte FROM woord WHERE term >= ? AND term < ? AND kandidaat = 1 ORDER BY lengte, term',
        begin, naBegin(begin));
      return { term: r.map((x) => x.term), doc: Uint32Array.from(r, (x) => x.doc), lengte: Uint16Array.from(r, (x) => x.lengte) };
    });
  }

  // Een geplakt bericht: de tien zeldzaamste woorden die in de uitgave staan (`_berichtbron`).
  private async berichtbron(delen: Deel[]): Promise<Omit<Keuze, 'gelezen' | 'bericht'>> {
    const k = await this.pub.kolommen();
    const n = k.n;
    const grens = Math.max(BERICHT_GEWOON * n, 3);
    const kandidaten: [number, number, string, Groep][] = [];
    const gezien = new Set<string>();
    let opvallend = 0;
    for (let plek = 0; plek < delen.length; plek++) {
      const term = delen[plek][0];
      const kern = Array.from(indexvorm(term)).filter((t) => isalnum(t)).join('');
      if (lengte(kern) < 3 || gezien.has(kern)) continue;
      gezien.add(kern);
      const groep = await this.groep(term, false);
      const r = await probeer(() => eerste<{ n: number }>(this.db, 'SELECT count(*) AS n FROM zoek WHERE zoek MATCH ?', groep.match));
      if (r === null) continue;
      const df = r.n;
      if (df <= grens) opvallend++;
      if (df > 0 && df <= grens) kandidaten.push([df, plek, term, groep]);
    }
    const gekozen = [...kandidaten].sort((a, b) => a[0] - b[0] || a[1] - b[1]).slice(0, BERICHT_TERMEN).sort((a, b) => a[1] - b[1]);
    const delenUit: Deel[] = gekozen.map(([, , term]) => [stripTekens(term, RANDTEKENS) || term, false]);
    const markeer = gekozen.flatMap(([, , , groep]) => groep.markeer);
    const niets = { bron: null, deels: false, verbeterd: null, delen: delenUit, markeer };
    if (gekozen.length < 2) return niets;
    const gewicht = new Map<string, number>();
    const aantal = new Map<string, number>();
    for (const [df, , , groep] of gekozen) {
      const w = logPython(n / df);
      for (const { nummer } of await rijen<{ nummer: string }>(this.db, 'SELECT nummer FROM zoek WHERE zoek MATCH ?', groep.match)) {
        gewicht.set(nummer, (gewicht.get(nummer) ?? 0) + w);
        aantal.set(nummer, (aantal.get(nummer) ?? 0) + 1);
      }
    }
    const nodig = Math.max(2, Math.ceil(Math.min(opvallend, BERICHT_TERMEN) * BERICHT_DEKKING));
    let beste = 0;
    let eerst = true;
    for (const [nr, g] of gewicht) {
      if (aantal.get(nr)! >= nodig && (eerst || g > beste)) {
        beste = g;
        eerst = false;
      }
    }
    let treffers = [...gewicht].filter(([nr, g]) => aantal.get(nr)! >= nodig && g >= BERICHT_DEEL * beste)
      .sort((a, b) => (b[1] - a[1]) || (aantal.get(b[0])! - aantal.get(a[0])!) || vergelijk(a[0], b[0]))
      .slice(0, BERICHT_MAX).map(([nr]) => nr);
    const zwak = !treffers.length;
    if (zwak) {
      // geen factcheck lijkt duidelijk op het bericht: de tien met de meeste van dezelfde woorden, geen treffers
      const ruim = await this.zoekbron(delen, null, true);
      if (!ruim) return niets;
      const [van, basis, waarden, rang, rangwaarden] = ruim;
      treffers = (await rijen<{ nummer: string }>(this.db,
        `SELECT p.nummer AS nummer FROM ${van} WHERE ${basis.join(' AND ')} ORDER BY ${rang} LIMIT ?`,
        ...waarden, ...rangwaarden, BERICHT_ZWAK)).map((r) => r.nummer);
      if (!treffers.length) return niets;
    }
    const lijst = JSON.stringify(treffers);
    return { bron: ['pagina p', ['p.nummer IN (SELECT value FROM json_each(?))'], [lijst],
      '(SELECT key FROM json_each(?) WHERE value = p.nummer)', [lijst]], deels: zwak, verbeterd: null, delen: delenUit, markeer };
  }

  // Welke bron een vraag krijgt: elk stuk; anders een verbeterde spelfout; dan een deel van de vraag (`_keuze`).
  async keuze(vraag: string | null, letterlijk = false, bericht = false): Promise<Keuze> {
    const ruw = zoekdelen(vraag);
    if (!ruw.length) return { bron: null, deels: false, verbeterd: null, delen: ruw, markeer: [], gelezen: [], bericht: false };
    const lang = bericht ? zoekdelen(vraag, true) : ruw;
    const berichtwoorden = lang.filter(([, p]) => !p);
    if (bericht && berichtwoorden.length > MAX_TERMEN) return { ...(await this.berichtbron(lang)), gelezen: [], bericht: true };
    let [delen, groepen] = await this.groepen(ruw, letterlijk);
    let bron = await this.zoekbron(delen, groepen);
    let deels = false;
    let verbeterd: string | null = null;
    if (!bron) {
      const beter = await this.verbeter(ruw.filter(([, p]) => !p).map(([t]) => t));
      if (beter) {
        let j = 0;
        const nieuwRuw: Deel[] = ruw.map(([t, p]) => [p ? t : beter[j++], p]);
        const [nieuw, nieuweGroepen] = await this.groepen(nieuwRuw, letterlijk);
        bron = await this.zoekbron(nieuw, nieuweGroepen);
        if (bron) {
          delen = nieuw;
          groepen = nieuweGroepen;
          verbeterd = nieuwRuw.map(([t, p]) => (p ? `"${t}"` : t)).join(' ');
        }
      }
    }
    if (!bron && bericht && berichtwoorden.length >= BERICHT_WOORDEN) {
      return { ...(await this.berichtbron(lang)), gelezen: [], bericht: true };
    }
    if (!bron) {
      bron = await this.zoekbron(delen, groepen, true);
      deels = true;
    }
    const gelezen = deels || !bron ? [] : groepen.filter((g) => g.kenmerk).map((g) => ({ ...g.kenmerk!.wat, woord: g.kenmerk!.woord }));
    return { bron, deels, verbeterd, delen, markeer: groepen.flatMap((g) => g.markeer), gelezen, bericht: false };
  }

  private async nummers(bron: Bron): Promise<string[]> {
    return (await rijen<{ nummer: string }>(this.db, `SELECT p.nummer AS nummer FROM ${bron[0]} WHERE ${bron[1].join(' AND ')}`,
      ...bron[2])).map((r) => r.nummer);
  }

  // Wat de zoekpagina nodig heeft (`zoek_ruim`).
  async zoekRuim(vraag: string | null, blad = 1, vertaal = VERTAALTAAL, sorteer: string | null = null, letterlijk = false,
                 bericht = false, filters: Filters = {}): Promise<Zoekuitslag> {
    const k = await this.keuze(vraag, letterlijk, bericht);
    const termen = k.delen.map(([t]) => t);
    if (!k.bron) {
      return { rijen: [], totaal: 0, deels: false, facetten: {}, zonder_filters: 0, termen, markeer: [], verbeterd: null,
               gelezen: [], bericht: k.bericht };
    }
    // het blad, de kolommen en de nummers voor de filters tegelijk: ze wachten niet op elkaar (#37.16)
    const [{ rijen: r, totaal }, kol, nummers] = await Promise.all([this.uitBron(k.bron, blad, vertaal, sorteer, filters),
      this.pub.kolommen(), this.nummers(k.bron)]);
    const treffers = new Uint8Array(kol.n);
    for (const nr of nummers) treffers[kol.plek.get(nr)!] = 1;
    let zonder = 0;
    for (let i = 0; i < kol.n; i++) zonder += treffers[i];
    return { rijen: r, totaal, deels: k.deels, termen, markeer: k.markeer, zonder_filters: zonder,
             facetten: await this.pub.telFacetten(treffers, filters), verbeterd: k.verbeterd, gelezen: k.gelezen, bericht: k.bericht };
  }

  // Hoeveel factchecks een vraag vindt, zonder filters en zonder een deel van de woorden (`tel`).
  async tel(vraag: string): Promise<number> {
    const { bron, deels } = await this.keuze(vraag);
    if (!bron || deels) return 0;
    return (await eerste<{ n: number }>(this.db, `SELECT COUNT(*) AS n FROM ${bron[0]} WHERE ${bron[1].join(' AND ')}`, ...bron[2]))!.n;
  }

  // De nummers achter het aantal zonder filters (`treffers`).
  async treffers(vraag: string, letterlijk = false): Promise<string[]> {
    const { bron } = await this.keuze(vraag, letterlijk);
    return bron ? this.nummers(bron) : [];
  }

  // Ingangen tijdens het typen, en de woorden die het laatste stuk afmaken (`suggesties`). Python haalt die woorden uit
  // een frozenset, en zet woorden met hetzelfde gewicht dus per proces in een andere volgorde; hier in de volgorde van de
  // namen.
  async suggesties(vraag: string, taal: string, n = 4): Promise<[Wat[], string[]]> {
    const stukken = zoektermen(vraag).map(alfabet).filter(Boolean);
    if (!stukken.length || lengte(stukken.join('')) < 2) return [[], []];
    const heel = stukken.join(' ');
    const laatste = stukken[stukken.length - 1];
    const treffers: [number, number, Wat][] = [];
    const aanvullingen = new Map<string, number>();
    for (const [woordenSet, wat] of (await this.ingangen()).suggestie) {
      if (!stukken.every((s) => woordenSet.some((w) => w.startsWith(s)))) continue;
      const namen = typeof wat.naam === 'object' ? Object.values(wat.naam) : [wat.naam];
      const precies = namen.some((naam) => alfabet(zoektermen(naam).join(' ')) === heel);
      treffers.push([precies ? 0 : 1, -(wat.aantal ?? 0), wat]);
      for (const w of woordenSet) {
        if (w.startsWith(laatste) && w !== laatste) aanvullingen.set(w, (aanvullingen.get(w) ?? 0) + (wat.aantal ?? 0));
      }
    }
    treffers.sort((a, b) => a[0] - b[0] || a[1] - b[1]);
    const ingangen = treffers.slice(0, n).map(([, , w]) => ({ ...w, naam: typeof w.naam === 'object' ? w.naam[taal] : w.naam }));
    const voor = stukken.slice(0, -1).join(' ');
    const woorden_ = [...aanvullingen].sort((a, b) => b[1] - a[1]).slice(0, 3).map(([w]) => strip(`${voor} ${w}`));
    return [ingangen, woorden_];
  }

  // Is de vraag precies een naam, thema, dossier of redactie, dan is dat een ingang; hoogstens drie (`ingangen`).
  async ingangenVan(vraag: string, taal: string): Promise<Wat[]> {
    const s = sleutel(vraag);
    if (!s) return [];
    const { ingang, naamIngang, deel } = await this.ingangen();
    const uit: Wat[] = [];
    const stukken = zoektermen(vraag);
    if (stukken.length === 1) {
      const afk = await this.afkorting(stukken[0]);
      if (afk) uit.push(naamIngang.get(afk.nummer)!);
    }
    for (const i of [...(ingang.get(s) ?? []), ...(deel.get(s) ?? [])]) if (!uit.includes(i)) uit.push(i);
    return uit.slice(0, 3).map((i) => ({ ...i, naam: typeof i.naam === 'object' ? i.naam[taal] : i.naam }));
  }

  // Waar een vraag meteen heen gaat: een geplakte link, of de volledige naam van één persoon of dossier (`doorsturen`).
  async doorsturen(vraag0: string, letterlijk = false): Promise<Wat | null> {
    if (letterlijk || !vraag0) return null;
    const vraag = strip(schoon(vraag0));
    const nummer = await this.factcheckVanLink(vraag);
    if (nummer !== null) {
      const r = await eerste<{ bewering: string }>(this.db, 'SELECT bewering FROM pagina WHERE nummer = ?', nummer);
      return { soort: 'factcheck', nummer, naam: r ? schoon(r.bewering) : '', aantal: null };
    }
    if (zoekdelen(vraag).some(([, p]) => p)) return null;
    const lijst = (await this.ingangen()).ingang.get(sleutel(vraag)) ?? [];
    if (lijst.length === 1 && (lijst[0].soort === 'dossier' || (lijst[0].soort === 'naam' && lijst[0].naamsoort === 'persoon'))) {
      return { ...lijst[0] };
    }
    return null;
  }

  private async factcheckVanLink(vraag: string): Promise<string | null> {
    const i = vraag.indexOf('://');
    const naSchema = i >= 0 ? vraag.slice(i + 3) : vraag;
    if (heeftWit(vraag) || !vraag.includes('.') || !stripTekens(naSchema, '/').includes('/')) return null;
    const vorm = adresvorm(vraag);
    if (!vorm) return null;
    const m = vorm[vorm.length - 1].match(FACTIZ_LINK);
    if (m) return (await this.pub.kolommen()).plek.has(m[1]) ? m[1] : null;
    const adressen = await this.adressen();
    for (const k of vorm) {
      const p = paginaVan(adressen, k);
      if (p >= 0) return (await this.pub.kolommen()).nummer[p];
    }
    return null;
  }

  // De vraag met het woord dat je typt afgemaakt, of niets (`aanvulling`).
  // Met haar aantal: hoeveel factchecks de afgemaakte vraag vindt (`tel`), uit dezelfde zoektocht die haar koos, zodat de
  // route haar niet nog eens helemaal hoeft te zoeken (#37.16).
  async aanvulling(vraag: string): Promise<{ tekst: string; aantal: number } | null> {
    if (!vraag || vraag !== rstrip(vraag) || Array.from(AANHALINGSTEKENS).some((t) => vraag.includes(t))) return null;
    const stukken = woorden(vraag);
    const laatste = stukken[stukken.length - 1];
    const w = indexvorm(laatste);
    if (lengte(w) < AANVUL_MIN || lengte(w) !== lengte(laatste) || !isalpha(w) || ZONDER_SPATIES.test(w)) return null;
    // of het woord al bestaat, en de drie kandidaten die met `w` beginnen, de grootste (aantal, woord) eerst
    // (`_voorvoegsels`, `heapq.nlargest`): samen in één vraag aan de database (#37.16)
    const { bekend, top } = await this.begins.haal(w, async () => {
      const [r, t] = await Promise.all([
        eerste(this.db, 'SELECT 1 AS n FROM woord WHERE term = ?', w),
        rijen<{ term: string }>(this.db, 'SELECT term FROM woord WHERE term >= ? AND term < ? AND kandidaat = 1 '
          + 'ORDER BY doc DESC, term DESC LIMIT 3', w, `${w}\u{10ffff}`)]);
      return { bekend: r !== null, top: t.map((x) => x.term) };
    });
    if (bekend) return null;
    const n = lengte(w);
    const hele = top.map((term) => vraag + knip(term, n));
    // de drie tegelijk, en de eerste die iets vindt (zoals na elkaar, maar in één keer heen en terug per stap)
    const bronnen = await Promise.all(hele.map(async (heel) => {
      const [delen, groepen] = await this.groepen(zoekdelen(heel), false);
      return this.zoekbron(delen, groepen);
    }));
    const i = bronnen.findIndex((b) => b !== null);
    if (i < 0) return null;
    const b = bronnen[i]!;
    const aantal = (await eerste<{ n: number }>(this.db, `SELECT COUNT(*) AS n FROM ${b[0]} WHERE ${b[1].join(' AND ')}`, ...b[2]))!.n;
    return { tekst: hele[i], aantal };
  }
}

export function zoeker(pub: Publicatie): Promise<Zoeker> {
  return pub.eens('zoeken:zoeker', async () => new Zoeker(pub));
}
