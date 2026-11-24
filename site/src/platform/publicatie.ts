// De uitgave zoals het platform haar leest (`factiz_site/db.py`, `Publicatie`), in TypeScript (PLAN #34.2bo stap 3).
// Python rekent alles bij het openen; een Worker begint vaak opnieuw, dus hier leest elk stuk pas als een ingang het
// vraagt, en daarna niet meer zolang de Worker leeft.
import { type Db, rijen, eerste } from './db.ts';
import { lees } from './geheugen.ts';
import { TALEN } from './i18n.ts';
import { alfabet, schoon, schoneRij, vergelijk } from './tekst.ts';
import { Voorraad } from './verzoek.ts';

export const SCHEMA = 21;            // 21: elke vertaling in het zoekregister en de woordenlijst als tabel `woord` (#37.16); 20: voorlopige vertalingen met een banner (B93); 19: de zinnen van de wereldlijst per taal (#37.12 punt 5); 18: de wereldlijst, wat de redacties vonden en waar het rondging (#37.12, B91); 17: pagina's buiten zoekmachines om een privépersoon (#34.2bw); 16: de zoekvraag per factcheck (#34.2cf, B87); 15: het adres van een eigen check met jaar en maand, en de gelezen vertalingen (#37.11); 14: de begrippen van een dossier (#34.2ca); 13: de eigen factchecks (#37.4, B82); 12: dezelfde bewering bij een andere redactie (#34.2bp)
export const PER_BLAD = 25;
// Een sitemap noemt hoogstens 50.000 adressen (sitemaps.org; `db.SITEMAP_DEEL`, PLAN #34.2bt).
export const SITEMAP_DEEL = 50000;
export const MEER = ['oordeel', 'soort', 'vorm', 'taal', 'jaar'];
export const FACETTEN = ['thema', 'onderdeel', 'oordeel', 'soort', 'vorm', 'taal', 'jaar', 'land', 'redactie'];
export const SOORTEN = ['bewerkt', 'context', 'verzonnen', 'satire', 'ai'];
export const VORMEN = ['video', 'beeld'];
export const LIJST_VOLGORDES = ['oud', 'redacties'];
export const NAAMSOORTEN = ['persoon', 'organisatie', 'plaats'];
export const ANDERE_LETTER = '0';
const VERTAALTAAL = 'en';
const NUMMER = /^[0-9a-f]{16}$/;
const SLEUTEL = /^[a-z][a-z0-9-]{1,39}$/;
const QNUMMER = /^Q[1-9][0-9]{0,11}$/;
export const RIJ = 'p.nummer, p.bewering, p.taal, p.richting, p.label, p.checks, p.redacties, p.laatste_datum, p.thema, p.land, p.volgens, '
  + 'v.tekst AS vertaling, e.tekst AS vertaling_en';
export const MET_VERTALING = ' LEFT JOIN vertaling v ON v.pagina = p.nummer AND v.taal = ?'
  + ` LEFT JOIN vertaling e ON e.pagina = p.nummer AND e.taal = '${VERTAALTAAL}'`;

export type Filterwaarde = string | string[] | null | undefined;
export type Filters = Record<string, Filterwaarde>;
export type Telling = Record<string, Record<string, number>>;
export type Bewering = Record<string, string | number | null> & { normaal: string | null; kenmerk: [string, string] | null };
export type Tijdlijnitem = { soort: string; datum: string; titel: Record<string, string>; bron: string; url: string;
  niveau: string; rij: Bewering | null; redacties: string[] };
export type NaamDing = { nummer: string; soort: string; naam: Record<string, string>; paginas: number };

// Per factcheck de kenmerken waarop gefilterd wordt, als getallen in het geheugen (`Publicatie._bouw_kenmerken`).
type Kolommen = {
  n: number; nummer: string[]; plek: Map<string, number>; redacties: Int32Array;
  kolom: Record<string, Int32Array>; code: Record<string, Map<string, number>>; waarde: Record<string, string[]>;
  redactiePlek: Int32Array; redactieCode: Int32Array; volgorde: Map<string, Int32Array>;
};
// Wat ervan bewaard wordt (`kolommen:kern`): de nummers als één tekst van 16 tekens per pagina, en de drie volgordes van de
// lijst al gesorteerd. Een nieuwe Worker las de kolommen als 13 MB JSON met 106.073 nummers, evenveel datums en een tabel
// van nummer naar plek (in Cloudflare ~250 ms CPU); de lijst en de tabel maken uit deze kern is veel goedkoper (stap 8).
type Kern = Omit<Kolommen, 'nummer' | 'plek'> & { nummers: string };
const NUMMERLENGTE = 16;

const rijVan = (w: Filterwaarde): string[] => (Array.isArray(w) ? w : w ? [w] : []);
const leeg = (w: Filterwaarde) => w === null || w === undefined || w === '' || (Array.isArray(w) && !w.length);

type Naam = Record<string, string>;
export type Onderdeel = { sleutel: string; ouder: string | null; naam: Naam; aantal: number };
export type Thema = Onderdeel & { onderdelen: Onderdeel[] };
export type Stand = { factchecks: number; eerste: string; talen: number; redacties: number; laatste: string };
export type Dossier = {
  sleutel: string; soort: string; concept: boolean; thema: string | null; onderdeel: string; naam: Naam; inleiding: Naam;
  vastgesteld: { door: string; url: string; datum: string } | null; stand: Stand; verwant: Dossier[];
  begrippen: Record<string, string[]>;
};
export type Bron = { bron: string; naam: string; licentie: string; naamsvermelding: string; url: string };
export type EigenCheck = Record<string, unknown> & {
  sleutel: string; taal: string; concept: boolean; kop: string; oordeel: string; oordeel_zin: string; bewering: string;
  platform: string; eerst_gezien: string; kort: string; tekst: string; auteur: string; soort?: string; vorm?: string;
  posts?: number; bereik?: string; reikwijdte?: string; niet_weten?: string; nalezer?: string; nagelezen_in?: string; gepubliceerd?: string; nog_doen?: string[]; nog_uitzoeken?: string[];
  // waar de check op de site staat, door `publiceren.eigen_adressen` erbij gezet (PLAN #37.11)
  maand: string; paden: Record<string, string>; vindbaar_in?: string[];
  beeld?: { rol: string; stempel?: boolean; bijschrift?: string; alt?: string; link?: string; pad?: string; breedte?: number;
             hoogte?: number }[];
  rekensom?: { geval: string; som: string; uitkomst: string }[];
  tijdlijn?: { datum: string; tijd?: string; wat: string }[];
  bron: { nr: number; soort: string; uitgever: string; titel: string; datum: string; url?: string; archief?: string; prive?: boolean; weg?: boolean; geen_kopie?: string }[];
};

export class Ongeldig extends Error {}

// Waar het vooraf berekende geheugen van een uitgave staat (`geheugen.ts`): per stuk de bewaarde tekst, of niets.
export type Geheugen = (naam: string) => Promise<string | null>;

export class Publicatie {
  readonly db: Db;
  private stukken = new Voorraad<unknown>();
  private geheugen: Geheugen | null;
  // hoe lang elk stuk rekende (met wat het zelf weer vroeg erbij): om te kiezen wat vooraf bewaard wordt
  readonly rekentijd = new Map<string, number>();
  // wie elk stuk wil vastleggen op het moment dat het af is (`site/scripts/geheugen.ts`)
  opnemen: ((naam: string, waarde: unknown) => void) | null = null;

  constructor(db: Db, geheugen: Geheugen | null = null) {
    this.db = db;
    this.geheugen = geheugen;
  }

  // Alles wat al gerekend is, om vooraf te bewaren (`site/scripts/geheugen.ts`).
  async alleStukken(): Promise<[string, unknown][]> {
    return this.stukken.alle();
  }

  // Eén keer per Worker: een stuk wordt gelezen bij de eerste vraag en daarna onthouden. Ook voor de modules van een
  // ingang (factcheck, zoeken): een eigen naam per stuk, met de module ervoor (`zoeken:hoofdletters`).
  // Gedeeld tussen verzoeken via `Voorraad` (PLAN #34.2bq): een ander verzoek wacht nooit op werk dat nog bezig is.
  eens<T>(naam: string, maak: () => Promise<T>): Promise<T> {
    return this.stukken.haal(naam, async () => {
      // eerst het vooraf berekende geheugen; ontbreekt het stuk daar, dan rekenen zoals altijd
      const bewaard = this.geheugen ? await this.geheugen(naam) : null;
      if (bewaard !== null) return lees(bewaard) as T;
      const begin = Date.now();
      const w = await maak();
      this.rekentijd.set(naam, Date.now() - begin);
      // vastleggen zoals het nu is: een stuk kan later nog groeien (een voorraad die zich vult), en dat hoort er niet bij
      this.opnemen?.(naam, w);
      return w;
    }) as Promise<T>;
  }

  meta(): Promise<Record<string, string>> {
    return this.eens('meta', async () => {
      const meta = Object.fromEntries((await rijen<{ sleutel: string; waarde: string }>(
        this.db, 'SELECT sleutel, waarde FROM meta')).map((r) => [r.sleutel, r.waarde]));
      if (meta.schema !== String(SCHEMA)) throw new Ongeldig(`schema ${meta.schema}, deze site kent schema ${SCHEMA}`);
      return meta;
    });
  }

  async release(): Promise<string> {
    return (await this.meta()).release ?? '';
  }

  paginas(): Promise<number> {
    return this.eens('paginas', async () =>
      (await eerste<{ n: number }>(this.db, 'SELECT COUNT(*) AS n FROM pagina'))?.n ?? 0);
  }

  // Waarop gefilterd kan worden, met de aantallen; hier alleen de redacties (de rest volgt met de lijst).
  redacties(): Promise<[string, number][]> {
    return this.eens('redacties', async () => (await rijen<{ r: string; n: number }>(this.db,
      'SELECT redactie AS r, COUNT(DISTINCT pagina) AS n FROM check_ GROUP BY redactie '
      + 'ORDER BY COUNT(DISTINCT pagina) DESC, redactie')).map((r): [string, number] => [schoon(r.r), r.n]));
  }

  bronnen(): Promise<Bron[]> {
    return this.eens('bronnen', async () =>
      (await rijen<Bron>(this.db, 'SELECT * FROM bron ORDER BY bron')).map(schoneRij));
  }

  // Thema's (PLAN #33.4): alleen wat een pagina heeft. Een bewering met een tweede thema telt bij beide thema's; een
  // onderdeel hoort bij het eerste thema.
  themas(): Promise<Thema[]> {
    return this.eens('themas', async () => {
      const perThema = new Map<string, number>();
      for (const r of await rijen<{ thema: string; tweede: string; n: number }>(this.db,
        'SELECT thema, tweede, COUNT(*) AS n FROM pagina WHERE thema IS NOT NULL GROUP BY thema, tweede')) {
        for (const s of new Set([r.thema, r.tweede])) {
          if (s === '') continue;
          perThema.set(s, (perThema.get(s) ?? 0) + r.n);
        }
      }
      const perDeel = new Map<string, number>();
      for (const r of await rijen<{ thema: string; onderdeel: string; n: number }>(this.db,
        "SELECT thema, onderdeel, COUNT(*) AS n FROM pagina WHERE onderdeel <> '' GROUP BY thema, onderdeel")) {
        perDeel.set(`${r.thema}\u0000${r.onderdeel}`, r.n);
      }
      const themas: Thema[] = [];
      const perSleutel = new Map<string, Thema>();
      for (const ruw of await rijen<Record<string, string | null>>(this.db, 'SELECT * FROM thema ORDER BY volg')) {
        const r = schoneRij(ruw);
        const naam = Object.fromEntries(TALEN.map((t) => [t, r[`naam_${t}`] as string]));
        const sleutel = r.sleutel as string;
        if (r.ouder === null && perThema.get(sleutel)) {
          const thema: Thema = { sleutel, ouder: null, naam, aantal: perThema.get(sleutel)!, onderdelen: [] };
          themas.push(thema);
          perSleutel.set(sleutel, thema);
        } else if (r.ouder !== null && perSleutel.has(r.ouder) && perDeel.get(`${r.ouder}\u0000${sleutel}`)) {
          perSleutel.get(r.ouder)!.onderdelen.push(
            { sleutel, ouder: r.ouder, naam, aantal: perDeel.get(`${r.ouder}\u0000${sleutel}`)! });
        }
      }
      return themas;
    });
  }

  async thema(sleutel: string): Promise<Thema | null> {
    return (await this.themas()).find((t) => t.sleutel === sleutel) ?? null;
  }

  async deel(thema: string, sleutel: string): Promise<Onderdeel | null> {
    return (await this.thema(thema))?.onderdelen.find((o) => o.sleutel === sleutel) ?? null;
  }

  landen(): Promise<Record<string, Record<string, string>>> {
    return this.eens('landen', async () => Object.fromEntries((await rijen<Record<string, string>>(this.db, 'SELECT * FROM land'))
      .map(schoneRij).map((r) => [r.code, Object.fromEntries(TALEN.map((t) => [t, r[`naam_${t}`]]))])));
  }

  // De soort volgens de redactie en de vorm (#34.2ak), en het normale schrift van een bewering in hoofdletters (#34.2ae).
  kenmerkVan(): Promise<Map<string, [string, string]>> {
    return this.eens('kenmerk', async () => new Map((await rijen<{ pagina: string; soort: string; vorm: string }>(this.db,
      'SELECT pagina, soort, vorm FROM kenmerk')).map((r): [string, [string, string]] => [r.pagina, [r.soort, r.vorm]])));
  }

  normaalVan(): Promise<Map<string, string>> {
    return this.eens('normaal', async () => new Map((await rijen<{ pagina: string; tekst: string }>(this.db,
      'SELECT pagina, tekst FROM bewering_normaal')).map((r): [string, string] => [r.pagina, schoon(r.tekst)])));
  }

  tellingen(): Promise<Record<string, number>> {
    return this.eens('tellingen', async () => {
      const een = async (sql: string) => (await eerste<{ n: number }>(this.db, sql))?.n ?? 0;
      return { paginas: await this.paginas(), checks: await een('SELECT COUNT(*) AS n FROM check_'),
               talen: await een('SELECT COUNT(DISTINCT taal) AS n FROM pagina'),
               redacties: await een('SELECT COUNT(DISTINCT redactie) AS n FROM check_') };
    });
  }

  // Waarop gefilterd kan worden, met de aantallen: één keer geteld, in de volgorde van `Publicatie.facetten`.
  facetten(): Promise<Record<string, [string, number][]>> {
    return this.eens('facetten', async () => {
      const paar = async (sql: string, f: (w: string | null) => string = (w) => w ?? '') =>
        (await rijen<{ w: string | null; n: number }>(this.db, sql)).map((r): [string, number] => [f(r.w), r.n]);
      const landen = await this.landen();
      const kenmerk = await this.kenmerkVan();
      const uit: Record<string, [string, number][]> = {
        taal: await paar('SELECT taal AS w, COUNT(*) AS n FROM pagina GROUP BY taal ORDER BY COUNT(*) DESC, taal'),
        jaar: await paar("SELECT substr(laatste_datum, 1, 4) AS w, COUNT(*) AS n FROM pagina WHERE laatste_datum <> '' "
          + 'GROUP BY 1 ORDER BY 1 DESC'),
        oordeel: await paar('SELECT label AS w, COUNT(*) AS n FROM pagina GROUP BY label ORDER BY COUNT(*) DESC', (w) => w || 'geen'),
        redactie: await this.redacties(),
        thema: (await this.themas()).map((t): [string, number] => [t.sleutel, t.aantal]),
        land: (await paar("SELECT land AS w, COUNT(*) AS n FROM pagina WHERE land <> '' GROUP BY land ORDER BY COUNT(*) DESC, land"))
          .filter(([c]) => Object.hasOwn(landen, c)),
      };
      for (const [wat, waarden, plek] of [['soort', SOORTEN, 0], ['vorm', VORMEN, 1]] as const) {
        const telling = new Map<string, number>();
        for (const k of kenmerk.values()) if (k[plek]) telling.set(k[plek], (telling.get(k[plek]) ?? 0) + 1);
        uit[wat] = waarden.filter((w) => telling.get(w)).map((w): [string, number] => [w, telling.get(w)!]);
      }
      return uit;
    });
  }

  // Namen (PLAN #33.7): publieke personen, organisaties en plaatsen met hun nummer bij Wikidata.
  namen(): Promise<Map<string, NaamDing>> {
    return this.eens('namen', async () => new Map((await rijen<Record<string, string | number>>(this.db, 'SELECT * FROM naam'))
      .map(schoneRij).map((r): [string, NaamDing] => [r.nummer as string, {
        nummer: r.nummer as string, soort: r.soort as string, paginas: r.paginas as number,
        naam: Object.fromEntries(TALEN.map((t) => [t, r[`naam_${t}`] as string])) }])));
  }

  async heeftNamen(): Promise<boolean> {
    return (await this.namen()).size > 0;
  }

  // Welke pagina's in deze taal en stand vindbaar zijn, als SQL (`db._sitemap_waar`, PLAN #34.2bt, DESIGNSYSTEEM §6).
  // Stand 3: de taal van de bewering of een vertaling erin, en in het Engels ook een pagina zonder eigen taal en zonder
  // vertaling in een sitetaal. Stand 2: elke pagina één keer, in de taal van haar bewering als dat een sitetaal is, anders
  // waar `x_default` heen wijst. Stand 1: zoals 2, alleen de kern.
  private sitemapWaar(taal: string, stand: number): [string, string[]] {
    const talen = [...TALEN];
    const vragen = (n: number) => Array.from({ length: n }, () => '?').join(',');
    // een voorlopige vertaling (B93) telt niet: zoekmachines zien haar niet (`db._sitemap_waar`)
    const heeft = 'EXISTS (SELECT 1 FROM vertaling v WHERE v.pagina = p.nummer AND v.taal = ? AND v.voorlopig = 0)';
    const geen = (deel: string[]) => (deel.length
      ? `NOT EXISTS (SELECT 1 FROM vertaling v WHERE v.pagina = p.nummer AND v.voorlopig = 0 AND v.taal IN (${vragen(deel.length)}))` : '1');
    const vreemd = `p.taal NOT IN (${vragen(talen.length)})`;
    let waar: string;
    let args: string[];
    if (stand === 3) {
      waar = `p.taal = ? OR ${heeft}`;
      args = [taal, taal];
    } else {
      const eerder = talen.slice(0, talen.indexOf(taal));
      waar = `p.taal = ? OR (${vreemd} AND ${heeft} AND ${geen(eerder)})`;
      args = [taal, ...talen, taal, ...eerder];
    }
    if (taal === 'en') {
      waar += ` OR (${vreemd} AND ${geen(talen)})`;
      args = [...args, ...talen, ...talen];
    }
    // stand 1, de kern (B73 punt 5): meer dan één redactie, Ook gecheckt door, of in een dossier
    if (stand === 1) {
      waar = `(${waar}) AND (p.redacties > 1 OR EXISTS (SELECT 1 FROM zelfde z WHERE z.pagina = p.nummer) `
        + "OR EXISTS (SELECT 1 FROM dossier_item d WHERE d.pagina = p.nummer AND d.soort = 'factcheck'))";
    }
    // in geen stand een afgeschermde pagina (maatregel 2, #34.2bw)
    waar = `(${waar}) AND NOT EXISTS (SELECT 1 FROM afscherming a WHERE a.pagina = p.nummer)`;
    return [waar, args];
  }

  async sitemapTelling(taal: string, stand: number): Promise<number> {
    const [waar, args] = this.sitemapWaar(taal, stand);
    return (await eerste<{ n: number }>(this.db, `SELECT COUNT(*) AS n FROM pagina p WHERE ${waar}`, ...args))?.n ?? 0;
  }

  // Het deel van de factchecks voor de sitemap, op nummer: [nummer, de datum van de nieuwste check].
  async sitemapDeel(taal: string, stand: number, deel: number): Promise<[string, string | null][]> {
    const [waar, args] = this.sitemapWaar(taal, stand);
    return (await rijen<{ nummer: string; laatste_datum: string | null }>(this.db,
      `SELECT p.nummer AS nummer, p.laatste_datum AS laatste_datum FROM pagina p WHERE ${waar} ORDER BY p.nummer LIMIT ? OFFSET ?`,
      ...args, SITEMAP_DEEL, deel * SITEMAP_DEEL)).map((r): [string, string | null] => [r.nummer, r.laatste_datum]);
  }

  // De namen met een eigen pagina, op nummer; in een uitgave met namen als concept geen.
  async sitemapNamen(): Promise<string[]> {
    if ((await this.meta()).namen_concept) return [];
    return [...(await this.namen()).keys()].sort();
  }

  async naam(nummer: string): Promise<NaamDing | null> {
    return QNUMMER.test(nummer ?? '') ? (await this.namen()).get(nummer) ?? null : null;
  }

  async kent(soort: string, waarde: string): Promise<boolean> {
    if (soort === 'naam') return (await this.namen()).has(waarde);
    return ((await this.facetten())[soort] ?? []).some(([w]) => w === waarde);
  }

  async dossier(sleutel: string): Promise<Dossier | null> {
    return SLEUTEL.test(sleutel ?? '') ? (await this.dossiers()).find((d) => d.sleutel === sleutel) ?? null : null;
  }

  async dossiersBij(thema: string, onderdeel: string | null = null): Promise<Dossier[]> {
    return (await this.dossiers()).filter((d) => d.thema === thema && (onderdeel === null || d.onderdeel === onderdeel));
  }

  kolommen(): Promise<Kolommen> {
    return this.eens('kolommen', async () => {
      const { nummers, ...rest } = await this.kolomkern();
      const nummer = Array.from({ length: rest.n }, (_, i) => nummers.slice(i * NUMMERLENGTE, (i + 1) * NUMMERLENGTE));
      return { ...rest, nummer, plek: new Map(nummer.map((nr, i) => [nr, i])) };
    });
  }

  private kolomkern(): Promise<Kern> {
    return this.eens('kolommen:kern', async () => {
      const ruw = await rijen<{ nummer: string; taal: string; jaar: string; oordeel: string; land: string; thema: string;
                                tweede: string; onderdeel: string; datum: string; redacties: number }>(this.db,
        "SELECT nummer, taal, substr(laatste_datum, 1, 4) AS jaar, COALESCE(label, 'geen') AS oordeel, land, "
        + "COALESCE(thema, '') AS thema, tweede, onderdeel, laatste_datum AS datum, redacties FROM pagina ORDER BY nummer");
      const n = ruw.length;
      const kenmerk = await this.kenmerkVan();
      const code: Record<string, Map<string, number>> = {};
      const waarde: Record<string, string[]> = {};
      const kolom: Record<string, Int32Array> = {};
      const sorteer = (s: Iterable<string>) => [...s].sort(vergelijk);
      for (const soort of ['taal', 'jaar', 'oordeel', 'land', 'thema', 'tweede'] as const) {
        const veld = soort as keyof (typeof ruw)[number];
        let c: Map<string, number>;
        if (soort === 'tweede') c = code.thema;
        else {
          const alle = sorteer(new Set(ruw.map((r) => r[veld] as string).filter((w) => w !== '')));
          c = new Map(alle.map((w, i) => [w, i]));
          code[soort] = c;
          waarde[soort] = alle;
        }
        kolom[soort] = Int32Array.from(ruw, (r) => c.get(r[veld] as string) ?? -1);
      }
      const delen = [...new Set(ruw.filter((r) => r.thema && r.onderdeel).map((r) => `${r.thema}\u0000${r.onderdeel}`))]
        .map((s) => s.split('\u0000') as [string, string])
        .sort((a, b) => vergelijk(a[0], b[0]) || vergelijk(a[1], b[1]));
      code.onderdeel = new Map(delen.map((d, i) => [`${d[0]}\u0000${d[1]}`, i]));
      waarde.onderdeel = delen.map((d) => d[1]);
      kolom.onderdeel = Int32Array.from(ruw, (r) => code.onderdeel.get(`${r.thema}\u0000${r.onderdeel}`) ?? -1);
      for (const [wat, waarden, plek] of [['soort', SOORTEN, 0], ['vorm', VORMEN, 1]] as const) {
        code[wat] = new Map(waarden.map((w, i) => [w, i]));
        waarde[wat] = [...waarden];
        kolom[wat] = Int32Array.from(ruw, (r) => code[wat].get((kenmerk.get(r.nummer) ?? ['', ''])[plek]) ?? -1);
      }
      const plek = new Map(ruw.map((r, i) => [r.nummer, i]));
      const paren_ = await rijen<{ pagina: string; redactie: string }>(this.db, 'SELECT DISTINCT pagina, redactie FROM check_');
      const redacties = sorteer(new Set(paren_.map((r) => schoon(r.redactie))));
      code.redactie = new Map(redacties.map((w, i) => [w, i]));
      waarde.redactie = redacties;
      const redactieAantal = Int32Array.from(ruw, (r) => r.redacties);
      // de volgordes van de lijst (`VOLGORDES`): nieuw, oud of redacties; bij gelijke waarden het nummer (de plekken staan
      // al op nummer en sorteren is stabiel)
      const d = ruw.map((r) => r.datum);
      const nieuw = (a: number, b: number) => (d[a] > d[b] ? -1 : d[a] < d[b] ? 1 : 0);
      const op = (f: (a: number, b: number) => number) => Int32Array.from(Array.from({ length: n }, (_, i) => i).sort(f));
      const volgorde = new Map<string, Int32Array>([
        ['nieuw', op(nieuw)],
        ['oud', op((a, b) => (Number(d[a] === '') - Number(d[b] === '')) || -nieuw(a, b))],
        ['redacties', op((a, b) => (redactieAantal[b] - redactieAantal[a]) || nieuw(a, b))],
      ]);
      if (ruw.some((r) => r.nummer.length !== NUMMERLENGTE)) throw new Ongeldig(`een nummer zonder ${NUMMERLENGTE} tekens`);
      return {
        n, nummers: ruw.map((r) => r.nummer).join(''), redacties: redactieAantal, kolom, code, waarde, volgorde,
        redactiePlek: Int32Array.from(paren_, (r) => plek.get(r.pagina)!),
        redactieCode: Int32Array.from(paren_, (r) => code.redactie.get(schoon(r.redactie))!),
      };
    });
  }

  // Welke factchecks door de filters komen; dezelfde regels als `_masker` en `_waar`.
  async masker(filters: Filters, zonder: string[] = []): Promise<Uint8Array> {
    const k = await this.kolommen();
    const f = Object.fromEntries(Object.entries(filters).filter(([s, w]) => !leeg(w) && !zonder.includes(s)));
    const m = new Uint8Array(k.n).fill(1);
    for (const soort of ['taal', 'jaar', 'oordeel', 'land', 'soort', 'vorm']) {
      if (!(soort in f)) continue;
      const codes = new Set(rijVan(f[soort]).filter((w) => k.code[soort].has(w)).map((w) => k.code[soort].get(w)!));
      const kol = k.kolom[soort];
      for (let i = 0; i < k.n; i++) if (m[i] && !codes.has(kol[i])) m[i] = 0;
    }
    if ('onderdeel' in f) {
      const c = k.code.onderdeel.get(`${f.thema ?? ''}\u0000${f.onderdeel}`) ?? -2;
      const zonderThema = !('thema' in f);
      for (let i = 0; i < k.n; i++) if (m[i] && (zonderThema || k.kolom.onderdeel[i] !== c)) m[i] = 0;
    } else if ('thema' in f) {
      const c = k.code.thema.get(f.thema as string) ?? -2;
      for (let i = 0; i < k.n; i++) if (m[i] && k.kolom.thema[i] !== c && k.kolom.tweede[i] !== c) m[i] = 0;
    }
    if ('redactie' in f) {
      const c = k.code.redactie.get(f.redactie as string) ?? -2;
      const r = new Uint8Array(k.n);
      for (let j = 0; j < k.redactieCode.length; j++) if (k.redactieCode[j] === c) r[k.redactiePlek[j]] = 1;
      for (let i = 0; i < k.n; i++) m[i] &= r[i];
    }
    if ('naam' in f) {
      const r = new Uint8Array(k.n);
      for (const p of await this.naamPlekken(f.naam as string)) r[p] = 1;
      for (let i = 0; i < k.n; i++) m[i] &= r[i];
    }
    return m;
  }

  // De plekken van de pagina's met een naam. Een factcheckpagina telt de filters van haar lijst *Meer over …* elk zonder
  // zichzelf, en vroeg zo negen keer dezelfde pagina's aan D1 (~20 ms per keer, stap 8); de laatste 256 namen blijven.
  private naamplekken = new Voorraad<Int32Array>({ max: 256 });
  private naamPlekken(naam: string): Promise<Int32Array> {
    return this.naamplekken.haal(naam, async () => {
      const k = await this.kolommen();
      const plekken: number[] = [];
      for (const { pagina } of await rijen<{ pagina: string }>(this.db, 'SELECT pagina FROM pagina_naam WHERE naam = ?', naam)) {
        const p = k.plek.get(pagina);
        if (p !== undefined) plekken.push(p);
      }
      return Int32Array.from(plekken);
    });
  }

  // Per filter hoeveel factchecks elke waarde heeft binnen alle andere filters (`_tel_facetten`); `basis` zijn de treffers
  // van een zoekvraag, of niets voor alles.
  async telFacetten(basis: Uint8Array | null, filters: Filters): Promise<Telling> {
    const k = await this.kolommen();
    const masker = async (...zonder: string[]) => {
      const m = await this.masker(filters, zonder);
      if (basis) for (let i = 0; i < k.n; i++) m[i] &= basis[i];
      return m;
    };
    const tel = (soort: string, m: Uint8Array): Record<string, number> => {
      const aantallen = new Array(k.waarde[soort].length).fill(0);
      const kol = k.kolom[soort];
      for (let i = 0; i < k.n; i++) if (m[i] && kol[i] >= 0) aantallen[kol[i]]++;
      return Object.fromEntries(aantallen.map((a, i) => [k.waarde[soort][i], a]).filter(([, a]) => a));
    };
    const uit: Telling = {};
    for (const soort of ['taal', 'jaar', 'oordeel', 'land', 'soort', 'vorm']) uit[soort] = tel(soort, await masker(soort));
    const m = await masker('thema', 'onderdeel');
    const aantallen = new Array(k.waarde.thema.length).fill(0);
    for (let i = 0; i < k.n; i++) {
      if (!m[i]) continue;
      const a = k.kolom.thema[i];
      const b = k.kolom.tweede[i];
      if (a >= 0) aantallen[a]++;
      if (b >= 0 && b !== a) aantallen[b]++;
    }
    uit.thema = Object.fromEntries(aantallen.map((a, i) => [k.waarde.thema[i], a]).filter(([, a]) => a));
    uit.onderdeel = {};
    if (filters.thema) {
      const mo = await masker('onderdeel');
      const c = k.code.thema.get(filters.thema as string) ?? -2;
      for (let i = 0; i < k.n; i++) if (k.kolom.thema[i] !== c) mo[i] = 0;
      uit.onderdeel = tel('onderdeel', mo);
    }
    const mr = await masker('redactie');
    const per = new Array(k.waarde.redactie.length).fill(0);
    for (let j = 0; j < k.redactieCode.length; j++) if (mr[k.redactiePlek[j]]) per[k.redactieCode[j]]++;
    uit.redactie = Object.fromEntries(per.map((a, i) => [k.waarde.redactie[i], a]).filter(([, a]) => a));
    return uit;
  }

  private facetvoorraad = new Voorraad<Telling>({ max: 2000 });

  facettenVan(filters: Filters): Promise<Telling> {
    const sleutel = JSON.stringify(Object.entries(filters).sort(([a], [b]) => vergelijk(a, b)));
    return this.facetvoorraad.haal(sleutel, () => this.telFacetten(null, filters));
  }

  // De plekken in de volgorde van een lijst (`VOLGORDES`): nieuw, oud of redacties, vooraf gesorteerd in de kolommen.
  private async orde(volgorde: string): Promise<Int32Array> {
    const uit = (await this.kolommen()).volgorde.get(volgorde);
    if (!uit) throw new Error(`geen volgorde ${volgorde}`);
    return uit;
  }

  // Rijen met een bewering, met haar vertalingen, haar normale schrift en haar kenmerken (`_bewering_rij`).
  async beweringen(nummers: string[], vertaal: string, extra = ''): Promise<Map<string, Bewering>> {
    const uit = new Map<string, Bewering>();
    if (!nummers.length) return uit;
    const normaal = await this.normaalVan();
    const kenmerk = await this.kenmerkVan();
    for (let i = 0; i < nummers.length; i += 90) {
      const stuk = nummers.slice(i, i + 90);
      for (const r of await rijen<Record<string, string | number | null>>(this.db,
        `SELECT ${RIJ}${extra} FROM pagina p${MET_VERTALING} WHERE p.nummer IN (${stuk.map(() => '?').join(', ')})`,
        vertaal, ...stuk)) {
        const rij = schoneRij(r) as Bewering;
        rij.normaal = normaal.get(rij.nummer as string) ?? null;
        rij.kenmerk = kenmerk.get(rij.nummer as string) ?? null;
        uit.set(rij.nummer as string, rij);
      }
    }
    return uit;
  }

  // De factchecks met de filters die gezet zijn, in de gekozen volgorde (`Publicatie.lijst`): geteld en geordend in het
  // geheugen, en alleen de rijen van dit blad uit de database.
  async lijst(filters: Filters, { blad = 1, vertaal = VERTAALTAAL, sorteer = null as string | null } = {}):
    Promise<{ rijen: Bewering[]; totaal: number }> {
    const m = await this.masker(filters);
    const k = await this.kolommen();
    const orde = await this.orde(sorteer && LIJST_VOLGORDES.includes(sorteer) ? sorteer : 'nieuw');
    let totaal = 0;
    const begin = (blad - 1) * PER_BLAD;
    const gekozen: string[] = [];
    for (let j = 0; j < orde.length; j++) {
      const i = orde[j];
      if (!m[i]) continue;
      if (totaal >= begin && gekozen.length < PER_BLAD) gekozen.push(k.nummer[i]);
      totaal++;
    }
    const rijen_ = await this.beweringen(gekozen, vertaal);
    return { rijen: gekozen.map((n) => rijen_.get(n)!), totaal };
  }

  // Het register per taal en soort, op alfabet, gegroepeerd per letter (`Publicatie._register`).
  register(): Promise<Map<string, Map<string, NaamDing[]>>> {
    return this.eens('register', async () => {
      const namen = [...(await this.namen()).values()];
      const uit = new Map<string, Map<string, NaamDing[]>>();
      for (const taal of TALEN) {
        for (const soort of NAAMSOORTEN) {
          const per = new Map<string, NaamDing[]>();
          const sleutels = new Map(namen.map((n) => [n.nummer, alfabet(n.naam[taal])]));
          const gesorteerd = namen.filter((n) => n.soort === soort).sort((a, b) =>
            vergelijk(sleutels.get(a.nummer)!, sleutels.get(b.nummer)!) || (parseInt(a.nummer.slice(1), 10) - parseInt(b.nummer.slice(1), 10)));
          for (const n of gesorteerd) {
            const eerste = Array.from(sleutels.get(n.nummer)!)[0] ?? '';
            const letter = eerste >= 'a' && eerste <= 'z' && eerste.length === 1 ? eerste : ANDERE_LETTER;
            if (!per.has(letter)) per.set(letter, []);
            per.get(letter)!.push(n);
          }
          const letters = [...per.keys()].sort((a, b) =>
            (Number(a === ANDERE_LETTER) - Number(b === ANDERE_LETTER)) || vergelijk(a, b));
          uit.set(`${taal}\u0000${soort}`, new Map(letters.map((l) => [l, per.get(l)!])));
        }
      }
      return uit;
    });
  }

  async letters(taal: string, soort: string): Promise<string[]> {
    return [...((await this.register()).get(`${taal}\u0000${soort}`)?.keys() ?? [])];
  }

  async registerVan(taal: string, soort: string, letter: string): Promise<NaamDing[]> {
    return (await this.register()).get(`${taal}\u0000${soort}`)?.get(letter) ?? [];
  }

  // De items van een dossier in de volgorde van het bestand; een factcheck draagt de rij van zijn pagina (`tijdlijn`).
  async tijdlijn(sleutel: string, vertaal: string): Promise<Tijdlijnitem[]> {
    const redacties = new Map<string, string[]>();
    for (const r of await rijen<{ pagina: string; redactie: string }>(this.db,
      'SELECT DISTINCT k.pagina AS pagina, k.redactie AS redactie FROM check_ k JOIN dossier_item i ON i.pagina = k.pagina '
      + 'WHERE i.dossier = ? ORDER BY k.redactie', sleutel)) {
      if (!redacties.has(r.pagina)) redacties.set(r.pagina, []);
      redacties.get(r.pagina)!.push(schoon(r.redactie));
    }
    const titels = TALEN.map((t) => `i.titel_${t}`).join(', ');
    const items: Tijdlijnitem[] = [];
    for (const ruw of await rijen<Record<string, string | number | null>>(this.db,
      `SELECT i.soort AS item_soort, i.datum AS item_datum, ${titels}, i.bron AS bron, i.url AS url, i.niveau AS niveau, ${RIJ} `
      + `FROM dossier_item i LEFT JOIN pagina p ON p.nummer = i.pagina${MET_VERTALING} WHERE i.dossier = ? ORDER BY i.volg`,
      vertaal, sleutel)) {
      const r = schoneRij(ruw);
      const factcheck = r.item_soort === 'factcheck' && r.nummer !== null;
      const rij = factcheck ? Object.fromEntries(['nummer', 'bewering', 'taal', 'richting', 'label', 'checks', 'redacties',
        'laatste_datum', 'vertaling', 'vertaling_en', 'volgens'].map((k) => [k, r[k]])) as Bewering : null;
      if (rij) { rij.normaal = null; rij.kenmerk = null; }
      items.push({ soort: r.item_soort as string, datum: r.item_datum as string,
                   titel: Object.fromEntries(TALEN.map((t) => [t, r[`titel_${t}`] as string])),
                   bron: r.bron as string, url: r.url as string, niveau: r.niveau as string, rij,
                   redacties: factcheck ? redacties.get(r.nummer as string) ?? [] : [] });
    }
    return items;
  }

  // *Waar staan we nu*: geteld uit de factchecks in het dossier en hun checks (`Publicatie._stand`).
  private async stand(sleutel: string): Promise<Stand> {
    const binnen = "(SELECT pagina FROM dossier_item WHERE dossier = ? AND soort = 'factcheck')";
    const c = await eerste<{ eerste: string | null; laatste: string | null; redacties: number | null }>(this.db,
      `SELECT MIN(NULLIF(datum, '')) AS eerste, MAX(datum) AS laatste, COUNT(DISTINCT redactie) AS redacties `
      + `FROM check_ WHERE pagina IN ${binnen}`, sleutel);
    const talen = new Set<string>();
    for (const r of await rijen<{ talen: string | null }>(this.db, `SELECT talen FROM pagina WHERE nummer IN ${binnen}`, sleutel)) {
      for (const t of JSON.parse(r.talen || '[]') as string[]) talen.add(t);
    }
    talen.delete('und');
    const i = await eerste<{ aantal: number | null; laatste: string | null }>(this.db,
      "SELECT SUM(soort = 'factcheck') AS aantal, MAX(datum) AS laatste FROM dossier_item WHERE dossier = ?", sleutel);
    const a = c?.laatste ?? '';
    const b = i?.laatste ?? '';
    return { factchecks: i?.aantal ?? 0, eerste: c?.eerste ?? '', talen: talen.size, redacties: c?.redacties ?? 0,
             laatste: a > b ? a : b };
  }

  // De eigen factchecks (#37.4, B82, `db.Publicatie.eigen`): een handvol, één keer gelezen; de gepubliceerde eerst, de
  // nieuwste boven. De check zelf staat als JSON in de uitgave, zoals de redactie haar schreef.
  // hun pagina's in het archief, met de eigen redactie als bron (`db.Publicatie.eigen_paginas`): pagina -> de sleutel
  // van de check, via haar adres (PLAN #37.11)
  eigenPaginas(): Promise<Record<string, string>> {
    return this.eens('eigen_paginas', async () => {
      const adressen = new Map<string, string>();
      for (const e of await this.eigen()) for (const p of Object.values(e.paden ?? {})) adressen.set(p, e.sleutel);
      const pad = (url: string) => { try { return new URL(url).pathname; } catch { return ''; } };
      return Object.fromEntries((await rijen<{ pagina: string; url: string }>(this.db,
        "SELECT pagina, url FROM check_ WHERE bron = 'factiz-redactie' ORDER BY pagina"))
        .filter((r) => adressen.has(pad(r.url))).map((r) => [r.pagina, adressen.get(pad(r.url)) as string]));
    });
  }

  eigen(): Promise<EigenCheck[]> {
    return this.eens('eigen', async () => (await rijen<{ concept: number; gegevens: string }>(this.db,
      'SELECT concept, gegevens FROM eigen_check ORDER BY concept, datum DESC, sleutel'))
      .map((r) => ({ ...(JSON.parse(r.gegevens) as EigenCheck), concept: Boolean(r.concept) })));
  }

  // Dossiers (PLAN #33.6): het zijn er weinig, dus één keer gelezen; wat het laatst is aangevuld, staat boven.
  dossiers(): Promise<Dossier[]> {
    return this.eens('dossiers', async () => {
      const perSleutel = new Map<string, Dossier>();
      for (const ruw of await rijen<Record<string, string | number | null>>(this.db, 'SELECT * FROM dossier ORDER BY sleutel')) {
        const r = schoneRij(ruw);
        const sleutel = r.sleutel as string;
        perSleutel.set(sleutel, {
          sleutel, soort: r.soort as string, concept: Boolean(r.concept), thema: r.thema as string | null,
          onderdeel: r.onderdeel as string,
          naam: Object.fromEntries(TALEN.map((t) => [t, r[`naam_${t}`] as string])),
          inleiding: Object.fromEntries(TALEN.map((t) => [t, r[`inleiding_${t}`] as string])),
          vastgesteld: r.vastgesteld_door ? { door: r.vastgesteld_door as string, url: r.vastgesteld_url as string,
                                              datum: r.vastgesteld_datum as string } : null,
          stand: await this.stand(sleutel), verwant: [], begrippen: {},
        });
      }
      // de begrippen per taal van de site (#34.2ca)
      for (const r of await rijen<{ dossier: string; taal: string; begrip: string }>(this.db,
        'SELECT dossier, taal, begrip FROM dossier_begrip ORDER BY dossier, taal, volg')) {
        const d = perSleutel.get(r.dossier);
        if (d) (d.begrippen[r.taal] ??= []).push(r.begrip);
      }
      for (const d of perSleutel.values()) {
        d.verwant = (await rijen<{ verwant: string }>(this.db,
          'SELECT verwant FROM dossier_verwant WHERE dossier = ? ORDER BY verwant', d.sleutel))
          .filter((v) => perSleutel.has(v.verwant)).map((v) => perSleutel.get(v.verwant)!);
      }
      return [...perSleutel.values()].sort((x, y) =>
        (y.stand.laatste > x.stand.laatste ? 1 : y.stand.laatste < x.stand.laatste ? -1 : 0));
    });
  }
}
