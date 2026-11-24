// Het deelplaatje (`deelbeeld`) in TypeScript (B80, PLAN #34.2bo stap 5): dezelfde adressen, dezelfde 404 en hetzelfde
// plaatje als `factiz_site/app.py` en `factiz_site/deelbeeld.py`, op de pixel na: Pillow en resvg zetten een rand net anders.
// `python -m factiz_site.gelijk_deelbeeld` legt ze naast elkaar.
//   /api/<taal>/deelbeeld/<nummer>.jpg, .../deelbeeld/thema/<thema>[/<onderdeel>].jpg, .../deelbeeld/dossier/<sleutel>.jpg
// De lettertypen, de banden en de wasm komen van buiten (`zetMiddelen`): Node leest ze van schijf
// (`site/scripts/deelbeeld-node.ts`), een Worker uit zijn bestanden en zijn bundel. Niets wordt vooraf getekend; de laatste
// plaatjes blijven in het geheugen.
import { initWasm } from '@resvg/resvg-wasm';
import { rijen, eerste } from './db.ts';
import { HarfBuzz, type WasmBron } from './deelbeeld-hb.ts';
import { Zetter, type Voorraad } from './deelbeeld-tekst.ts';
import { teken, tekenIngang, type Beelden } from './deelbeeld-teken.ts';
import { NIET_GEVONDEN, vertaald, volgensNamen, type Antwoord, type Ingang } from './gedeeld.ts';
import { datum, getal, plat, stempel, tekst as vasteTekst, telregel, volgens } from './i18n.ts';
import type { Bewering, Publicatie } from './publicatie.ts';
import { schoon, schoneRij, vergelijk } from './tekst.ts';
import { Voorraad as Gedeeld } from './verzoek.ts';

// Wat het plaatje van buiten nodig heeft. `lees` geeft een bestand uit de voorraad van
// `node scripts/deelbeeld-voorraad.ts` (`voorraad.json`, `bereik/<pakket>.json`, `lettertypen/…ttf`, `beeld/<veld>.jpg`,
// `woordmerk-deel.png`); `wasm` de module van HarfBuzz, van resvg of het tekenblok (`teken.wasm`), als bytes of, in een
// Worker die geen wasm mag compileren, als module uit de bundel.
export type Middelen = {
  lees: (pad: string) => Promise<Uint8Array>;
  wasm: (naam: 'harfbuzz' | 'resvg' | 'teken') => Promise<WasmBron>;
};

const NUMMER = /^[0-9a-f]{16}$/;
const GEHEUGEN = 64;                // de laatste plaatjes per uitgave (~100 KB per stuk)
// HarfBuzz geeft geheugen nooit terug: elk lettertype dat een plaatje laadt, blijft erin staan, tot ~40 MB na honderden
// plaatjes in alle schriften. Boven deze grens begint het volgende plaatje met een nieuwe HarfBuzz; de oude verdwijnt zodra
// de plaatjes die hem nog gebruiken klaar zijn. Zo past het plaatje naast het platform in een Worker (128 MB, stap 8).
const LETTERTYPEN_MAX = 12 * 1024 * 1024;

let middelen: Middelen | null = null;
// gedeeld tussen verzoeken via `Voorraad` (PLAN #34.2bq): de HarfBuzz met zijn lettertypen en de beelden, en het begin van
// resvg (dat kent maar één begin per proces)
const opzet = new Gedeeld<{ z: Zetter; b: Beelden }>();
const resvgBegin = new Gedeeld<true>();

export function zetMiddelen(m: Middelen): void {
  middelen = m;
  opzet.vergeet('zetter');
}

const tekstUit = (bytes: Uint8Array) => new TextDecoder().decode(bytes);

// De wasm en de voorraad laden zonder iets te tekenen, bijvoorbeeld als een Worker begint; anders gebeurt het bij het eerste
// plaatje.
export async function bereidVoor(): Promise<void> {
  await laad();
}

function startResvg(m: Middelen): Promise<true> {
  return resvgBegin.haal('resvg', async () => {
    try {
      await initWasm(await m.wasm('resvg'));
    } catch (fout) {
      // twee keer beginnen kan alleen als een ander verzoek te lang deed: dan is het er al
      if (!/Already initialized/.test(String(fout))) throw fout;
    }
    return true;
  });
}

function laad(): Promise<{ z: Zetter; b: Beelden }> {
  if (!middelen) return Promise.reject(new Error('deelbeeld: geen middelen (zetMiddelen)'));
  const m = middelen;
  return opzet.haal('zetter', async () => {
    const [hbWasm, tekenWasm, voorraad, merk] = await Promise.all([m.wasm('harfbuzz'), m.wasm('teken'),
      m.lees('voorraad.json'), m.lees('woordmerk-deel.png'), startResvg(m)]);
    const hb = await HarfBuzz.laad(hbWasm, tekenWasm);
    const z = new Zetter(hb, JSON.parse(tekstUit(voorraad)) as Voorraad, m.lees);
    const banden = new Gedeeld<Uint8Array>();
    const band = (naam: string) => banden.haal(naam, () => m.lees(`beeld/${naam}.jpg`));
    // de maat van het woordmerk uit de kop van de PNG
    const kop = new DataView(merk.buffer, merk.byteOffset, merk.byteLength);
    return { z, b: { band, merk, merkMaat: [kop.getUint32(16), kop.getUint32(20)] as [number, number] } };
  });
}

// Eén plaatje met de HarfBuzz van nu; houdt die te veel lettertypen vast, dan krijgt het volgende plaatje een nieuwe.
async function metZetter<T>(f: (z: Zetter, b: Beelden) => Promise<T>): Promise<T> {
  const deze = await laad();
  try {
    return await f(deze.z, deze.b);
  } finally {
    if (deze.z.geladen > LETTERTYPEN_MAX) opzet.vergeet('zetter', deze);
  }
}

// De zin onder het label, zoals `app.kopgegevens` haar maakt: wie checkte en wanneer.
function antwoordzin(taal: string, redacties: number, checks: { redactie: string; datum: string | null }[]): string {
  const gedateerd = checks.filter((k) => datum(taal, (k.datum ?? '').slice(0, 10)))
    .sort((a, b) => vergelijk(a.datum as string, b.datum as string));
  const nieuwste = gedateerd.length ? gedateerd[gedateerd.length - 1] : (checks[0] ?? null);
  const d = gedateerd.length ? datum(taal, (nieuwste!.datum as string).slice(0, 10)) : '';
  const n = redacties || new Set(checks.map((k) => k.redactie)).size;
  if (n > 1) {
    return d ? vasteTekst(taal, 'antwoord_meer', { n: getal(taal, n), redactie: nieuwste!.redactie, datum: d })
      : vasteTekst(taal, 'antwoord_meer_zonder_datum', { n: getal(taal, n) });
  }
  if (nieuwste) {
    return d ? vasteTekst(taal, 'antwoord_een', { redactie: nieuwste.redactie, datum: d })
      : vasteTekst(taal, 'antwoord_een_zonder_datum', { redactie: nieuwste.redactie });
  }
  return '';
}

// Wat op het plaatje van een factcheck komt (`app.deelgegevens`): dezelfde kop, hetzelfde label en dezelfde zin als op de
// pagina. Eerst uit de uitgave; welke tekst het lettertype kan tonen, beslist `toon`.
async function deelgegevens(pub: Publicatie, taal: string, nummer: string) {
  if (!NUMMER.test(nummer)) return null;
  // de drie vragen tegelijk: in een Worker gaan ze dan in één keer naar D1 (`gegevens-worker.js`), niet na elkaar
  const [ruw, vertaalrijen, checkrijen] = await Promise.all([
    eerste<Record<string, string | number | null>>(pub.db, 'SELECT * FROM pagina WHERE nummer = ?', nummer),
    rijen<{ taal: string; tekst: string }>(pub.db, 'SELECT taal, tekst FROM vertaling WHERE pagina = ?', nummer),
    rijen<{ redactie: string; datum: string | null }>(pub.db, 'SELECT redactie, datum FROM check_ WHERE pagina = ? ORDER BY volg', nummer),
  ]);
  if (!ruw) return null;
  const p = schoneRij(ruw);
  const vertalingen = new Map(vertaalrijen.map((r) => [r.taal, schoon(r.tekst)]));
  const normaal = await pub.normaalVan();
  const rij = { ...p, vertaling: vertalingen.get(taal) ?? null, vertaling_en: vertalingen.get('en') ?? null,
                normaal: normaal.get(nummer) ?? null, kenmerk: null } as Bewering;
  const v = vertaald(taal, rij);
  const checks = checkrijen.map(schoneRij);
  return {
    getoond: plat(taal, v ? v.tekst : (p.bewering as string)),
    engels: plat(taal, (rij.vertaling_en as string | null) || (p.taal === 'en' ? (p.bewering as string) : '')),
    zin: antwoordzin(taal, (p.redacties as number) || 0, checks),
    telregel: telregel(taal, p.redacties as number, (JSON.parse((p.talen as string) || '[]') as string[]).length,
      p.eerste_datum as string, p.laatste_datum as string),
    // het stempel met wie het zegt (PLAN #34.2cc, `app.deelgegevens`)
    label: stempel(taal, p.label as string | null),
    // de vormen van lang naar kort, zonder dubbele (`app.deelgegevens`)
    volgens: [...new Set([4, 3, 2, 1].map((h) => volgens(taal, p.label as string | null, volgensNamen(p.volgens), h)))].filter(Boolean),
    klasse: p.label as string | null, thema: (p.thema as string | null) ?? null,
  };
}

// Kan geen lettertype het schrift van de kop tonen, dan de Engelse versie, en anders geen bewering; een zin met een naam in
// een schrift zonder lettertype wordt de telling van de pagina, geen blokjes.
async function toon(z: Zetter, g: NonNullable<Awaited<ReturnType<typeof deelgegevens>>>) {
  const bewering = (await z.kanTonen(g.getoond)) ? g.getoond : ((await z.kanTonen(g.engels || '')) ? g.engels : '');
  const zin = (await z.kanTonen(g.zin)) ? g.zin : g.telregel;
  const vormen: string[] = [];
  for (const v of g.volgens) if (await z.kanTonen(v)) vormen.push(v);
  return { bewering, label: g.label, volgens: vormen, klasse: g.klasse, zin, thema: g.thema };
}

const aantal = (taal: string, n: number) => vasteTekst(taal, n === 1 ? 'lijst_een' : 'lijst_meer', { n: getal(taal, n) });

// Wat op het plaatje van een thema, onderdeel of dossier komt (`app.ingangsgegevens`).
async function ingangsgegevens(pub: Publicatie, taal: string, soort: string, sleutel: string, deel: string | null) {
  if (soort === 'thema') {
    const thema = await pub.thema(sleutel);
    const onderdeel = thema && deel ? await pub.deel(sleutel, deel) : null;
    if (!thema || (deel !== null && !onderdeel)) return null;
    const masker = await pub.masker({ thema: sleutel, ...(onderdeel ? { onderdeel: deel } : {}) });
    const totaal = masker.reduce((n, m) => n + m, 0);
    return { kicker: onderdeel ? thema.naam[taal] : vasteTekst(taal, 'nav_themas'), titel: (onderdeel ?? thema).naam[taal],
             thema: sleutel, dossier: null, regel: aantal(taal, totaal) };
  }
  const d = await pub.dossier(sleutel);
  if (!d) return null;
  const st = d.stand;
  return { kicker: vasteTekst(taal, `dossier_soort_${d.soort}`), titel: d.naam[taal], thema: d.thema, dossier: sleutel,
           regel: `${aantal(taal, st.factchecks)}, ${telregel(taal, st.redacties, st.talen, st.eerste || '', st.laatste || '')}` };
}

const geheugen = new WeakMap<Publicatie, Gedeeld<Uint8Array | null>>();

// Eén keer tekenen per adres en uitgave; de laatste `GEHEUGEN` blijven bewaard (gedeeld via `Voorraad`, PLAN #34.2bq).
function onthoud(pub: Publicatie, sleutel: string, maak: () => Promise<Uint8Array | null>): Promise<Uint8Array | null> {
  let per = geheugen.get(pub);
  if (!per) {
    per = new Gedeeld<Uint8Array | null>({ max: GEHEUGEN });
    geheugen.set(pub, per);
  }
  return per.haal(sleutel, maak);
}

// Het adres in delen: wat er na `deelbeeld/` staat, met `.jpg` aan het eind; al het andere bestaat niet.
function lees(delen: string[]): [string, string, string | null] | null {
  const laatste = delen[delen.length - 1];
  if (!laatste.endsWith('.jpg') || laatste.length === 4) return null;
  const naam = laatste.slice(0, -4);
  if (delen.length === 1) return ['factcheck', naam, null];
  if (delen.length === 2 && (delen[0] === 'thema' || delen[0] === 'dossier')) return [delen[0], naam, null];
  if (delen.length === 3 && delen[0] === 'thema') return ['thema', delen[1], naam];
  return null;
}

async function deelbeeld(pub: Publicatie, taal: string, delen: string[]): Promise<Antwoord> {
  const adres = lees(delen);
  if (!adres) return NIET_GEVONDEN;
  const [soort, sleutel, deel] = adres;
  const bytes = await onthoud(pub, `${taal}\u0000${soort}\u0000${sleutel}\u0000${deel ?? ''}`, async () => {
    // eerst of het bestaat: een adres dat niet bestaat, laadt geen lettertype en geen wasm
    if (soort === 'factcheck') {
      const g = await deelgegevens(pub, taal, sleutel);
      if (!g) return null;
      return metZetter((z, b) => toon(z, g).then((t) => teken(z, b, t)));
    }
    const g = await ingangsgegevens(pub, taal, soort, sleutel, deel);
    if (!g) return null;
    return metZetter((z, b) => tekenIngang(z, b, g));
  });
  return bytes ? { status: 200, bytes, type: 'image/jpeg' } : NIET_GEVONDEN;
}

export const ingangen: Record<string, Ingang> = {
  deelbeeld: { delen: [1, 2, 3], f: (pub, taal, delen) => deelbeeld(pub, taal, delen) },
};
