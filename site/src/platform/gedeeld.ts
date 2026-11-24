// Wat de ingangen van het platform delen (B80, PLAN #34.2bo stap 3): de uitgave per database, de lijstadressen, de kaarten,
// een rij van een lijst, het filterformulier en het lezen van een adres of een bericht. Gelijk aan `factiz_site/app.py`.
import type { Db } from './db.ts';
import { LABELS, TALEN, datum, getal, label, pad, stempel, taalnaamIn, tekst, volgens } from './i18n.ts';
import { FACETTEN, type Geheugen, LIJST_VOLGORDES, MEER, Publicatie, type Bewering, type Dossier, type Filters, type Telling,
  type Thema } from './publicatie.ts';
import { casefold, kort, paren, urlencode, vergelijk } from './tekst.ts';
import { eigenIn } from './eigentaal.ts';

// Een antwoord: JSON in `body`, of bytes met hun soort (het deelplaatje), of een kale tekst (413, 405).
// Een omleiding (301) zegt in `adres` waarheen, zoals de kop Location.
export type Antwoord = { status: number; body?: unknown; bytes?: Uint8Array; type?: string; tekst?: string; adres?: string };
// Een ingang: GET of POST, hoeveel delen na haar naam (`/naam/<nummer>` één), en wat ze doet. `bericht` is het
// formulier van een POST, al gelezen (`leesBericht`).
export type Ingang = {
  methode?: 'GET' | 'POST'; delen?: number[];
  f: (pub: Publicatie, taal: string, delen: string[], vraag: URLSearchParams, bericht: Map<string, string[]> | null)
    => Promise<Antwoord>;
};

export const NIET_GEVONDEN: Antwoord = { status: 404 };
export const MAX_BERICHT = 8192;       // bytes van een zoekformulier

// Het bericht van een formulier zoals `urllib.parse.parse_qs(..., keep_blank_values=True, max_num_fields=96)`: per
// sleutel de waarden; met meer dan 96 velden niets.
export function leesBericht(bericht: string): Map<string, string[]> {
  const uit = new Map<string, string[]>();
  if (bericht && 1 + (bericht.match(/&/g) ?? []).length > 96) return uit;
  for (const [k, v] of new URLSearchParams(bericht)) {
    if (!uit.has(k)) uit.set(k, []);
    uit.get(k)!.push(v);
  }
  return uit;
}

// Wat erin zit en wat nog niet (#34.2az, E9.S25): grote redacties die een bezoeker verwacht, met een stuk van hun naam
export const GROTE_REDACTIES: [string, string][] = [['AFP', 'afp'], ['Reuters', 'reuters'], ['Snopes', 'snopes'],
  ['Correctiv', 'correctiv'], ['Full Fact', 'full fact']];
export const BIJNA_GEEN = 50;

const uitgaven = new WeakMap<Db, Publicatie>();
let geheugen: Geheugen | null = null;

// Waar het vooraf berekende geheugen van de uitgave staat (stap 3c): in de Worker de statische bestanden van de release, in
// Node een map of niets. Zonder geheugen rekent het platform alles zelf, met hetzelfde antwoord.
export function zetGeheugen(nieuw: Geheugen | null): void {
  geheugen = nieuw;
}

export function publicatie(db: Db): Publicatie {
  let pub = uitgaven.get(db);
  if (!pub) {
    pub = new Publicatie(db, geheugen);
    uitgaven.set(db, pub);
  }
  return pub;
}

// Het adres van de lijst met deze filters: de sleutels op alfabet, het eerste blad zonder nummer (`app.lijst_url`).
export function lijstUrl(taal: string, filters: Filters, blad = 1): string {
  const delen = [...paren(filters), ...(blad > 1 ? [['p', String(blad)] as [string, string]] : [])]
    .sort((a, b) => vergelijk(a[0], b[0]) || vergelijk(a[1], b[1]));
  const vraag = urlencode(delen);
  return pad(taal, 'fact-checks') + (vraag ? `?${vraag}` : '');
}

export const aantal = (taal: string, n: number) => tekst(taal, n === 1 ? 'lijst_een' : 'lijst_meer', { n: getal(taal, n) });

export function dossierkaart(taal: string, d: Dossier) {
  return {
    sleutel: d.sleutel, naam: d.naam[taal], soort: d.soort, soort_tekst: tekst(taal, `dossier_soort_${d.soort}`),
    thema: d.thema, href: pad(taal, 'dossiers', d.sleutel), inleiding: kort(d.inleiding[taal], 200),
    aantal: aantal(taal, d.stand.factchecks), laatste: datum(taal, d.stand.laatste), concept: d.concept,
    concept_tekst: d.concept ? tekst(taal, 'dossier_concept') : '',
  };
}

export function themakaart(taal: string, th: Thema) {
  return {
    sleutel: th.sleutel, naam: th.naam[taal], href: pad(taal, 'themes', th.sleutel), aantal: aantal(taal, th.aantal),
    onderdelen: th.onderdelen.map((o) => ({ sleutel: o.sleutel, naam: o.naam[taal], aantal: getal(taal, o.aantal),
                                            href: pad(taal, 'themes', th.sleutel, o.sleutel) })),
  };
}

export const FILTERS = ['taal', 'jaar', 'oordeel', 'soort', 'vorm', 'redactie', 'thema', 'onderdeel', 'land', 'naam'];
// De volgorde waarin een filter in het formulier en boven de lijst staat: het algemeenste eerst (DESIGN §4t).
export const FILTERVOLGORDE = ['thema', 'onderdeel', 'oordeel', 'soort', 'vorm', 'taal', 'jaar', 'land', 'redactie'];
export const STUKVOLGORDE = [...FILTERVOLGORDE, 'naam'];
// Hoeveel waarden een filter met vinkjes meteen toont; de rest staat onder *Meer* (DESIGN §4v).
export const BOVEN: Record<string, number> = { oordeel: 8, taal: 8, jaar: 6, soort: 5, vorm: 2 };

export class Fout404 extends Error {}

export const rijVan = (w: unknown): string[] => (Array.isArray(w) ? w : w ? [w as string] : []);
export const actiefVan = (f: Filters): Filters =>
  Object.fromEntries(Object.entries(f).filter(([, v]) => !(v === null || v === undefined || v === '' || (Array.isArray(v) && !v.length))));

export async function themanaam(pub: Publicatie, taal: string, thema: string | null, onderdeel = ''): Promise<string> {
  if (!thema) return '';
  const ding = onderdeel ? await pub.deel(thema, onderdeel) : await pub.thema(thema);
  return ding ? ding.naam[taal] : '';
}

export async function landnaam(pub: Publicatie, taal: string, code: string | null): Promise<string> {
  const landen = await pub.landen();
  return code && Object.hasOwn(landen, code) ? landen[code][taal] ?? '' : '';
}

// De tekst boven het origineel, met haar taal, of niets (`app.vertaald`, B32).
export function vertaald(taal: string, r: Bewering): { tekst: string; taal: string; normaal?: boolean } | null {
  if (r.taal !== taal && r.vertaling) return { tekst: r.vertaling as string, taal };
  if (r.taal !== taal && r.taal !== 'en' && r.vertaling_en) return { tekst: r.vertaling_en as string, taal: 'en' };
  if (r.normaal) return { tekst: r.normaal, taal: r.taal as string, normaal: true };
  return null;
}

export function vertaalregel(taal: string, brontaal: string, vertaaltaal: string, normaal = false): string {
  if (normaal) return tekst(taal, 'zo_geschreven');
  return tekst(taal, vertaaltaal === taal ? 'vertaling_uit' : 'vertaling_engels_uit', { bron: taalnaamIn(taal, brontaal) });
}

// De soort volgens de redactie en de vorm, elk met hun woord en de lijst met dat filter (`app.kenmerken`).
export function kenmerken(taal: string, kenmerk: [string, string] | null) {
  const [soort, vorm] = kenmerk ?? ['', ''];
  const uit = [];
  if (soort) uit.push({ wat: 'soort', waarde: soort, naam: tekst(taal, `soort_${soort}`), regel: tekst(taal, 'soort_volgens'),
                        href: lijstUrl(taal, { soort: [soort] }) });
  if (vorm) uit.push({ wat: 'vorm', waarde: vorm, naam: tekst(taal, `vorm_${vorm}`), regel: '', href: lijstUrl(taal, { vorm: [vorm] }) });
  return uit;
}

// De eigen factcheck bij een pagina van het archief (#37.4, `app.eigen_href`), of niets.
export async function eigenCheck(pub: Publicatie, nummer: string) {
  const sleutel = (await pub.eigenPaginas())[nummer];
  return sleutel ? (await pub.eigen()).find((c) => c.sleutel === sleutel) : undefined;
}

// Een rij van een lijst als gegevens, zoals de kaart van de site haar toont (`app.rij_gegevens`).
// de redacties achter het oordeel van een pagina, uit de kolom `volgens` (JSON; `app._namen`)
export function volgensNamen(veld: unknown): string[] {
  try { const w = JSON.parse(typeof veld === 'string' && veld ? veld : '[]'); return Array.isArray(w) ? w.map(String) : []; }
  catch { return []; }
}

export async function rijGegevens(pub: Publicatie, taal: string, r: Bewering) {
  const v = vertaald(taal, r);
  const ec = await eigenCheck(pub, r.nummer as string);
  const eigen = ec?.oordeel ?? '';
  const thema = await themanaam(pub, taal, r.thema as string | null);
  const land = await landnaam(pub, taal, r.land as string | null);
  const rtaal = r.taal as string;
  return {
    nummer: r.nummer, href: ec ? ec.paden[eigenIn(ec, taal) ? taal : ec.taal] : pad(taal, 'fact-checks', r.nummer as string),
    tekst: kort(v ? v.tekst : (r.bewering as string)),
    taal: v ? v.taal : rtaal, richting: v && !v.normaal ? 'ltr' : r.richting,
    origineel: v ? { regel: vertaalregel(taal, rtaal, v.taal, v.normaal ?? false), tekst: kort(r.bewering as string, 140),
                     taal: rtaal, richting: r.richting } : null,
    label: label(taal, r.label as string | null), datum: datum(taal, r.laatste_datum as string),
    // het oordeel als stempel met wie het zegt (PLAN #34.2cc, DESIGN §4y)
    stempel: stempel(taal, r.label as string | null), volgens: volgens(taal, r.label as string | null, volgensNamen(r.volgens)),
    soort: LABELS.includes(r.label as string) ? r.label : 'geen',
    taalnaam: (v && !v.normaal) || rtaal === taal || taalnaamIn(taal, rtaal) === rtaal ? '' : taalnaamIn(taal, rtaal),
    thema: r.thema && thema ? { sleutel: r.thema, naam: thema } : null,
    land: r.land && land ? { code: r.land, naam: land } : null,
    kenmerken: kenmerken(taal, r.kenmerk),
    redacties: r.redacties ? tekst(taal, r.redacties === 1 ? 'redacties_een' : 'redacties_meer',
                                   { n: getal(taal, (r.redacties as number) || 0) }) : '',
    // een eigen factcheck van Factiz (#37.4): de rij krijgt het zegel en haar eigen oordeel (D12)
    ...(eigen ? { eigen: tekst(taal, `eigen_oordeel_${eigen}`) } : {}),
  };
}

// De filters, de volgorde en het blad uit het adres van een lijst (`app.lees_lijstvraag`): alleen bekende sleutels, elk
// één keer, en alleen waarden die in de database voorkomen; al het andere bestaat niet (404).
export async function leesLijstvraag(pub: Publicatie, vraag: URLSearchParams) {
  const sleutels = [...vraag.keys()];
  const enkel = sleutels.filter((k) => !MEER.includes(k));
  if (sleutels.some((k) => !FILTERS.includes(k) && k !== 'p' && k !== 'sorteer') || enkel.length !== new Set(enkel).size) {
    throw new Fout404();
  }
  const laatste = (k: string) => { const a = vraag.getAll(k); return a.length ? a[a.length - 1] : null; };
  const gekozen: Filters = {};
  for (const soort of FILTERS) if (!MEER.includes(soort)) gekozen[soort] = laatste(soort) || null;
  for (const soort of MEER) {
    const rij = [...new Set(vraag.getAll(soort).filter(Boolean))].sort(vergelijk);
    for (const w of rij) if (!(await pub.kent(soort, w))) throw new Fout404();
    gekozen[soort] = rij.length ? rij : null;
  }
  for (const [soort, waarde] of Object.entries(gekozen)) {
    if (waarde !== null && !MEER.includes(soort) && soort !== 'onderdeel' && !(await pub.kent(soort, waarde as string))) {
      throw new Fout404();
    }
  }
  const sorteer = laatste('sorteer') || null;
  if (sorteer !== null && !LIJST_VOLGORDES.includes(sorteer)) throw new Fout404();
  if (gekozen.onderdeel !== null && !(gekozen.thema && await pub.deel(gekozen.thema as string, gekozen.onderdeel as string))) {
    gekozen.onderdeel = null;
  }
  const ruw = laatste('p') || '1';
  if (!/^[0-9]+$/.test(ruw) || ruw.length > 6 || parseInt(ruw, 10) < 1) throw new Fout404();
  return { gekozen, sorteer, blad: parseInt(ruw, 10) };
}

// Wat het filterformulier, de stukjes erboven en de volgorde nodig hebben (`app.filterdelen`).
export async function filterdelen(pub: Publicatie, taal: string, gekozen: Filters, sorteer: string | null, zoeken: boolean,
                           tellingen: Telling) {
  const thema = gekozen.thema ? await pub.thema(gekozen.thema as string) : null;
  const facetten = await pub.facetten();
  const namen: Record<string, (w: string) => Promise<string> | string> = {
    thema: (w) => themanaam(pub, taal, w), onderdeel: (w) => themanaam(pub, taal, gekozen.thema as string, w),
    oordeel: (w) => label(taal, w), taal: (w) => taalnaamIn(taal, w), jaar: (w) => w, land: (w) => landnaam(pub, taal, w),
    redactie: (w) => w, soort: (w) => tekst(taal, `soort_${w}`), vorm: (w) => tekst(taal, `vorm_${w}`),
    naam: async (w) => (await pub.naam(w))!.naam[taal],
  };
  const vast: Record<string, string[]> = {
    thema: (await pub.themas()).map((th) => th.sleutel), onderdeel: (thema ? thema.onderdelen : []).map((o) => o.sleutel),
    ...Object.fromEntries(['oordeel', 'taal', 'jaar', 'land', 'redactie', 'soort', 'vorm'].map((s) => [s, facetten[s].map(([w]) => w)])),
  };
  type Keuze = { waarde: string; naam: string; aantal: string; aan: boolean };
  const lijsten: Record<string, Keuze[]> = {};
  for (const soort of FACETTEN) {
    const aan = rijVan(gekozen[soort]);
    const tel = tellingen[soort] ?? {};
    lijsten[soort] = [];
    for (const w of vast[soort]) {
      if (tel[w] || aan.includes(w)) {
        lijsten[soort].push({ waarde: w, naam: await namen[soort](w), aantal: getal(taal, tel[w] ?? 0), aan: aan.includes(w) });
      }
    }
  }
  for (const soort of ['land', 'redactie']) lijsten[soort].sort((a, b) => vergelijk(casefold(a.naam), casefold(b.naam)));
  const groepen = [];
  for (const soort of MEER) {
    const boven = lijsten[soort].filter((k) => k.aan);
    boven.push(...lijsten[soort].filter((k) => !k.aan).slice(0, Math.max(0, BOVEN[soort] - boven.length)));
    const orde = new Map(lijsten[soort].map((k, i) => [k.waarde, i]));
    boven.sort((a, b) => orde.get(a.waarde)! - orde.get(b.waarde)!);
    groepen.push({ soort, kop: tekst(taal, `filter_${soort}`), boven,
                   uitleg: soort === 'soort' || soort === 'vorm' ? tekst(taal, `filter_${soort}_uitleg`) : '',
                   meer: lijsten[soort].filter((k) => !boven.includes(k)) });
  }
  const actief = actiefVan(gekozen);
  const volgorde: Filters = sorteer ? { sorteer } : {};
  const stukjes = [];
  for (const soort of STUKVOLGORDE) {
    for (const waarde of rijVan(gekozen[soort])) {
      const rest: Filters = Object.fromEntries(Object.entries(actief).filter(([k]) => k !== soort && !(soort === 'thema' && k === 'onderdeel')));
      const over = rijVan(gekozen[soort]).filter((w) => w !== waarde);
      if (MEER.includes(soort) && over.length) rest[soort] = over;
      stukjes.push({ soort, kop: tekst(taal, `filter_${soort}`), naam: await namen[soort](waarde),
                     paren: paren({ ...rest, ...volgorde }), url: lijstUrl(taal, { ...rest, ...volgorde }) });
    }
  }
  const opties: [string, string][] = [...(zoeken ? [['', 'sorteer_relevantie'] as [string, string]] : []),
    [zoeken ? 'nieuw' : '', 'sorteer_nieuw'], ['oud', 'sorteer_oud'], ['redacties', 'sorteer_redacties']];
  const themaTel = tellingen.thema ?? {};
  const promotie = gekozen.thema || zoeken ? [] : [...lijsten.thema]
    .sort((a, b) => (themaTel[b.waarde] ?? 0) - (themaTel[a.waarde] ?? 0)).slice(0, 6)
    .map((k) => ({ waarde: k.waarde, naam: k.naam, aantal: k.aantal, url: lijstUrl(taal, { ...actief, thema: k.waarde, ...volgorde }) }));
  return {
    lijsten, groepen: groepen.filter((g) => g.boven.length), sorteer: sorteer ?? '', promotie,
    volgordes: opties.map(([w, k]) => ({ waarde: w, naam: tekst(taal, k), aan: w === (sorteer ?? ''),
                                         url: lijstUrl(taal, { ...actief, ...(w ? { sorteer: w } : {}) }) })),
    stukjes, velden: ['thema', 'onderdeel', 'land', 'redactie'].filter((s) => lijsten[s].length),
    gekozen: Object.fromEntries(FILTERS.map((k) => [k, gekozen[k] || ''])), paren: paren(actief),
    alles: paren({ ...actief, ...volgorde }),
  };
}

// Anoniem tellen (PLAN #34.2ba, SPECS E9.S26, B78): per dag, wat en taal één getal, en niets anders. Waar het heen gaat
// zet de omgeving: in de Worker een eigen D1-database met dezelfde tabel als `factiz_site/tellen.py`, in Node niets.
export const SOORTEN = new Set(['start', 'lijst', 'factcheck', 'dossiers', 'dossier', 'namen', 'naam', 'redacties', 'bronnen',
  'over', 'platform', 'themas', 'thema', 'verkennen', 'netwerk', 'fout', 'eigens', 'eigen']);
// `storing`: een antwoord van 500 of hoger (PLAN #34.2bv), geteld door de middleware van de site
const WAT = new Set([...SOORTEN, 'robot', 'zoek', 'zoek-zonder', 'zoek-bericht', 'storing']);
export type Teller = (dag: string, wat: string, taal: string) => void;
let teller: Teller = () => {};
const TALEN_SET = new Set(TALEN);

export function zetTeller(nieuw: Teller): void {
  teller = nieuw;
}

// Telt één keer `wat` in `taal`; wat het niet kent, weigert het (zoals `Teller.tel`).
export function tel(wat: string, taal: string): void {
  if (!WAT.has(wat) || !TALEN_SET.has(taal)) throw new Error('onbekend');
  teller(new Date().toISOString().slice(0, 10), wat, taal);
}

// Wat mensen zoeken (B94, PLAN #37.17): één keer de zoekvraag in `taal`, per dag opgeteld. Welke vraag mag, zegt de site
// (`zoekvraagVoorTellen` in `src/lib/zoekvragen.js`); hier alleen de dag en de taal erbij.
export type Vraagteller = (dag: string, taal: string, vraag: string) => void;
let vraagteller: Vraagteller = () => {};

export function zetVraagteller(nieuw: Vraagteller): void {
  vraagteller = nieuw;
}

export function telVraag(taal: string, vraag: string): void {
  if (!TALEN_SET.has(taal) || !vraag) throw new Error('onbekend');
  vraagteller(new Date().toISOString().slice(0, 10), taal, vraag);
}
