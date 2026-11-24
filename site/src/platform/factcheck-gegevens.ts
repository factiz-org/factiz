// Wat de factcheckpagina uit de uitgave leest (`factiz_site/db.py`: `pagina`, `verwijzing`, `waarom`, `lijkt_op`,
// `varianten`, `namen_van`, `dossiers_van`, `toeschrijvingen`, `dossier_jaren`, en de tellingen achter de contextkaarten),
// in TypeScript (B80, PLAN #34.2bo stap 3). Per verzoek alleen vragen op een sleutel of index; wat voor de hele uitgave
// geldt, één keer per Worker achter `pub.eens`. Python houdt alle kenmerken in het geheugen; hier komen normaal schrift en
// kenmerk met dezelfde vraag mee, zodat een factcheckpagina nooit de hele tabel laadt.
import { eerste, rijen } from './db.ts';
import { MET_VERTALING, RIJ, SOORTEN, VORMEN, type Bewering, type Dossier, type NaamDing, type Publicatie } from './publicatie.ts';
import { TALEN } from './i18n.ts';
import { schoon, schoneRij, vergelijk, woorden } from './tekst.ts';

type Rij = Record<string, string | number | null>;

const NUMMER = /^[0-9a-f]{16}$/;

// De grenzen van Verkennen en het netwerk (`db.VERKEN_JAREN`, `NETWERK_NAMEN`, `NETWERK_SAMEN`, `VERHOUDING_LAND`,
// `VERHOUDING_THEMA`): een object, zodat een toets ze kan verzetten zoals Python met monkeypatch; elke voorraad hieronder
// draagt de waarden in haar naam.
export const GRENZEN = { VERKEN_JAREN: 11, NETWERK_NAMEN: 70, NETWERK_SAMEN: 25, VERHOUDING_LAND: 300, VERHOUDING_THEMA: 20 };

// Een stuk tekst in tekens (code points), zoals Python snijdt.
export function begin(tekst: string | null | undefined, n: number): string {
  return Array.from(tekst ?? '').slice(0, n).join('');
}

export type Check = Rij & { glossen: Map<string, string>; redactie_ruw: string };
export type Opgedoken = { naam: string; soort: string; niveau: string; datum: string; url: string; bron_naam: string };
export type Pagina = Rij & {
  vertalingen: Map<string, string>; voorlopig: Set<string>; normaal: string | null; kenmerk: [string, string] | null; checks_lijst: Check[];
  formuleringen: Rij[]; opgedoken: Opgedoken[]; bronnen: Record<string, string>[];
  redactie_ruw: string | null;     // de eerste redactie zoals ze in de tabel staat, voor haar telling
  ook_checks?: Check[];            // de checks van dezelfde bewering bij een andere redactie (#34.2bp), voor de kop
  zoekvraag: { taal: string; vraag: string; onderwerp: string } | null;   // de vraag zoals een zoeker haar typt (#34.2cf)
  afgeschermd: boolean;   // maatregel 2 (#34.2bw): nooit naar een zoekmachine
};

// Normaal schrift en kenmerk in dezelfde vraag als de bewering (`Publicatie._bewering_rij`).
const ERBIJ = ', bn.tekst AS _normaal, km.soort AS _soort, km.vorm AS _vorm';
const ERBIJ_JOIN = ' LEFT JOIN bewering_normaal bn ON bn.pagina = p.nummer LEFT JOIN kenmerk km ON km.pagina = p.nummer';

function alsBewering(ruw: Rij): Bewering {
  const { _normaal, _soort, _vorm, ...rest } = schoneRij(ruw);
  const rij = rest as Bewering;
  rij.normaal = (_normaal as string | null) ?? null;
  rij.kenmerk = _soort === null || _soort === undefined ? null : [_soort as string, _vorm as string];
  return rij;
}

export async function verwijzing(pub: Publicatie, nummer: string): Promise<string | null> {
  if (!NUMMER.test(nummer)) return null;
  return (await eerste<{ pagina: string }>(pub.db, 'SELECT pagina FROM verwijzing WHERE nummer = ?', nummer))?.pagina ?? null;
}

// Een check zoals de site haar leest, met de naam van de redactie zoals ze in de tabel staat (voor haar telling).
function alsCheck(r: Rij): Check {
  const k = schoneRij(r) as Check;
  k.redactie_ruw = r.redactie as string;
  return k;
}

// De woorden van de redactie, letterlijk vertaald (#34.2o); witruimte telt niet. Eén vraag voor alle checks.
async function metGlossen(pub: Publicatie, lijst: Check[]): Promise<void> {
  const sleutels = lijst.map((k) => woorden((k.oordeel_eigen as string) ?? '').join(' '));
  const glossen = new Map<string, Map<string, string>>();
  const uniek = [...new Set(sleutels)];
  for (let i = 0; i < uniek.length; i += 90) {
    const stuk = uniek.slice(i, i + 90);
    for (const r of await rijen<{ tekst: string; taal: string; glos: string }>(pub.db,
      `SELECT tekst, taal, glos FROM oordeel_glos WHERE tekst IN (${stuk.map(() => '?').join(', ')})`, ...stuk)) {
      if (!glossen.has(r.tekst)) glossen.set(r.tekst, new Map());
      glossen.get(r.tekst)!.set(r.taal, schoon(r.glos));
    }
  }
  lijst.forEach((k, i) => { k.glossen = glossen.get(sleutels[i]) ?? new Map(); });
}

// De pagina met haar vertalingen, checks (met de vertaalde woorden van de redactie), formuleringen, waar ze opdook en
// de bronnen van haar checks (`Publicatie.pagina`).
export async function pagina(pub: Publicatie, nummer: string): Promise<Pagina | null> {
  if (!NUMMER.test(nummer)) return null;
  const ruw = await eerste<Rij>(pub.db, `SELECT p.*${ERBIJ} FROM pagina p${ERBIJ_JOIN} WHERE p.nummer = ?`, nummer);
  if (!ruw) return null;
  const [vertalingen, checks, formuleringen, opgedoken, bronnen, zoekvraag, afgeschermd] = await Promise.all([
    rijen<{ taal: string; tekst: string; voorlopig: number }>(pub.db, 'SELECT taal, tekst, voorlopig FROM vertaling WHERE pagina = ?', nummer),
    rijen<Rij>(pub.db, 'SELECT * FROM check_ WHERE pagina = ? ORDER BY volg', nummer),
    rijen<Rij>(pub.db, 'SELECT nummer, tekst, taal, richting FROM formulering WHERE pagina = ? ORDER BY nummer', nummer),
    rijen<Rij>(pub.db, 'SELECT o.naam, o.soort, o.niveau, o.datum, o.url, b.naam AS bron_naam FROM opgedoken o '
      + 'JOIN bron b ON b.bron = o.bron WHERE o.pagina = ? ORDER BY o.datum DESC, o.naam LIMIT 200', nummer),
    pub.bronnen(),
    // de vraag zoals een zoeker haar typt (#34.2cf, B87): per pagina opgevraagd, niet in het geheugen (`Publicatie.pagina`)
    eerste<{ taal: string; vraag: string; onderwerp: string }>(pub.db,
      'SELECT taal, vraag, onderwerp FROM zoekvraag WHERE pagina = ?', nummer),
    // maatregel 2 (#34.2bw): een privépersoon in een gevoelige context, of nog niet gelezen
    eerste<{ a: number }>(pub.db, 'SELECT 1 AS a FROM afscherming WHERE pagina = ?', nummer),
  ]);
  const b = alsBewering(ruw);
  const p = b as unknown as Pagina;
  p.vertalingen = new Map(vertalingen.map((r): [string, string] => [r.taal, schoon(r.tekst)]));
  // een voorlopige vertaling (B93): op de pagina met een banner, nooit voor een zoekmachine (`db.pagina`)
  p.voorlopig = new Set(vertalingen.filter((r) => r.voorlopig).map((r) => r.taal));
  const lijst = checks.map(alsCheck);
  await metGlossen(pub, lijst);
  p.checks_lijst = lijst;
  p.redactie_ruw = checks.length ? checks[0].redactie as string : null;
  p.formuleringen = formuleringen.map(schoneRij);
  p.opgedoken = opgedoken.map((r) => schoneRij(r) as unknown as Opgedoken);
  const gebruikt = new Set(lijst.map((k) => k.bron));
  p.bronnen = (bronnen as unknown as Record<string, string>[]).filter((x) => gebruikt.has(x.bron));
  p.zoekvraag = zoekvraag ? { taal: zoekvraag.taal, vraag: zoekvraag.vraag, onderwerp: zoekvraag.onderwerp } : null;
  p.afgeschermd = !!afgeschermd;
  return p;
}

// *Waarom het niet klopt* (#34.2j): de punten zoals ze er staan, in volgorde, met de link naar de case.
export async function waarom(pub: Publicatie, nummer: string): Promise<{ punten: string[]; url: string } | null> {
  if (!NUMMER.test(nummer)) return null;
  const r = await rijen<{ punt: string; url: string }>(pub.db, 'SELECT punt, url FROM waarom WHERE pagina = ? ORDER BY volg', nummer);
  return r.length ? { punten: r.map((x) => x.punt), url: r[0].url } : null;
}

// Bij een overzicht van de wereldlijst (#37.12, B91): wat de redacties vonden en waar het rondging, in volgorde, elke zin
// met de links van de checks die haar dragen (`db.samenvatting`); leeg bij elke andere pagina.
// In `taal` als die vertaling er is (punt 5), anders in de taal van het overzicht (`db.samenvatting`).
export type Samenvatting = { soort: string; zin: string; bronnen: string[] };
export type Samenvattingen = { taal: string; brontaal: string; rijen: Samenvatting[] };
export async function samenvatting(pub: Publicatie, nummer: string, taal: string, brontaal: string): Promise<Samenvattingen | null> {
  if (!NUMMER.test(nummer)) return null;
  const r = await rijen<{ taal: string; soort: string; zin: string; bronnen: string }>(pub.db,
    'SELECT taal, soort, zin, bronnen FROM samenvatting WHERE pagina = ? AND taal IN (?, ?) ORDER BY volg', nummer, taal, brontaal);
  const gekozen = r.some((x) => x.taal === taal) ? taal : brontaal;
  const zinnen = r.filter((x) => x.taal === gekozen).map((x) => ({ soort: x.soort, zin: x.zin, bronnen: JSON.parse(x.bronnen) as string[] }));
  return zinnen.length ? { taal: gekozen, brontaal, rijen: zinnen } : null;
}

// *Lijkt op* (#34.2p): de andere pagina's over hetzelfde verhaal, in de volgorde van de uitgave.
export async function lijktOp(pub: Publicatie, nummer: string, vertaal: string): Promise<Bewering[]> {
  if (!NUMMER.test(nummer)) return [];
  return (await rijen<Rij>(pub.db, `SELECT ${RIJ}, p.eerste_datum${ERBIJ} FROM lijkt_op l JOIN pagina p ON p.nummer = l.ander`
    + `${MET_VERTALING}${ERBIJ_JOIN} WHERE l.pagina = ? ORDER BY l.volg`, vertaal, nummer)).map(alsBewering);
}

export type Zelfde = Bewering & { checks_lijst: Check[] };

// *Ook gecheckt door* (#34.2bp, SPECS E9.S31): de andere pagina's met dezelfde bewering bij een andere redactie, elk met
// haar checks (`Publicatie.zelfde`); de checks van alle pagina's in één vraag.
export async function zelfde(pub: Publicatie, nummer: string, vertaal: string): Promise<Zelfde[]> {
  if (!NUMMER.test(nummer)) return [];
  const paginas = (await rijen<Rij>(pub.db, `SELECT ${RIJ}, p.eerste_datum${ERBIJ} FROM zelfde z JOIN pagina p ON p.nummer = z.ander`
    + `${MET_VERTALING}${ERBIJ_JOIN} WHERE z.pagina = ? ORDER BY z.volg`, vertaal, nummer)).map(alsBewering) as Zelfde[];
  if (!paginas.length) return paginas;
  const nummers = paginas.map((r) => r.nummer as string);
  const checks = await rijen<Rij>(pub.db, `SELECT * FROM check_ WHERE pagina IN (${nummers.map(() => '?').join(', ')}) `
    + 'ORDER BY pagina, volg', ...nummers);
  const alle = checks.map(alsCheck);
  await metGlossen(pub, alle);
  const per = new Map<string, Check[]>(nummers.map((n) => [n, []]));
  checks.forEach((r, i) => per.get(r.pagina as string)?.push(alle[i]));
  for (const r of paginas) r.checks_lijst = per.get(r.nummer as string) ?? [];
  return paginas;
}

export type Varianten = { rijen: (Bewering & { redactienamen: string[] })[]; checks: number; talen: number };

// *Komt ook voor als*: de andere factchecks van dezelfde versie in het verhaaldossier, met de telling over de hele versie.
export async function varianten(pub: Publicatie, nummer: string, vertaal: string): Promise<Varianten | null> {
  if (!NUMMER.test(nummer)) return null;
  const eigen = await eerste<{ dossier: string; versie: string }>(pub.db,
    'SELECT i.dossier AS dossier, i.versie AS versie FROM dossier_item i JOIN dossier d ON d.sleutel = i.dossier '
    + "WHERE i.pagina = ? AND i.soort = 'factcheck' AND i.versie <> '' AND d.soort = 'verhaal'", nummer);
  if (!eigen) return null;
  const binnen = "(SELECT pagina FROM dossier_item WHERE dossier = ? AND versie = ? AND soort = 'factcheck')";
  const [ruw, paren, telling, talen] = await Promise.all([
    rijen<Rij>(pub.db, `SELECT ${RIJ}, p.eerste_datum${ERBIJ} FROM pagina p${MET_VERTALING}${ERBIJ_JOIN} WHERE p.nummer IN `
      + `${binnen} AND p.nummer <> ? ORDER BY p.eerste_datum = '', p.eerste_datum, p.nummer`,
      vertaal, eigen.dossier, eigen.versie, nummer),
    rijen<{ pagina: string; redactie: string }>(pub.db,
      `SELECT DISTINCT pagina, redactie FROM check_ WHERE pagina IN ${binnen} ORDER BY redactie`, eigen.dossier, eigen.versie),
    eerste<{ n: number }>(pub.db, `SELECT COUNT(*) AS n FROM check_ WHERE pagina IN ${binnen}`, eigen.dossier, eigen.versie),
    rijen<{ talen: string | null }>(pub.db, `SELECT talen FROM pagina WHERE nummer IN ${binnen}`, eigen.dossier, eigen.versie),
  ]);
  if (!ruw.length) return null;
  const redacties = new Map<string, string[]>();
  for (const r of paren) {
    if (!redacties.has(r.pagina)) redacties.set(r.pagina, []);
    redacties.get(r.pagina)!.push(schoon(r.redactie));
  }
  const alle = new Set<string>();
  for (const r of talen) for (const t of JSON.parse(r.talen || '[]') as string[]) alle.add(t);
  alle.delete('und');
  return {
    rijen: ruw.map(alsBewering).map((r) => Object.assign(r, { redactienamen: redacties.get(r.nummer as string) ?? [] })),
    checks: telling?.n ?? 0, talen: alle.size,
  };
}

function naamDing(r: Rij): NaamDing {
  return { nummer: r.nummer as string, soort: r.soort as string, paginas: r.paginas as number,
           naam: Object.fromEntries(TALEN.map((t) => [t, r[`naam_${t}`] as string])) };
}

// De namen bij een factcheck, in de volgorde waarin ze bij de bewering genoemd zijn.
export async function namenVan(pub: Publicatie, nummer: string): Promise<NaamDing[]> {
  if (!NUMMER.test(nummer)) return [];
  return (await rijen<Rij>(pub.db, 'SELECT n.* FROM pagina_naam pn JOIN naam n ON n.nummer = pn.naam WHERE pn.pagina = ? '
    + 'ORDER BY pn.volg', nummer)).map(schoneRij).map(naamDing);
}

// De dossiers waar deze factcheck in staat: het verhaal eerst, daarna de netwerken (`dossiers_van`).
export async function dossiersVan(pub: Publicatie, nummer: string): Promise<Dossier[]> {
  const sleutels = await rijen<{ dossier: string }>(pub.db, 'SELECT i.dossier AS dossier FROM dossier_item i JOIN dossier d '
    + "ON d.sleutel = i.dossier WHERE i.pagina = ? AND i.soort = 'factcheck' ORDER BY d.soort = 'netwerk', d.sleutel", nummer);
  if (!sleutels.length) return [];
  const per = new Map((await pub.dossiers()).map((d) => [d.sleutel, d]));
  return sleutels.map((r) => per.get(r.dossier)!).filter(Boolean);
}

export type Toeschrijving = { sleutel: string; bron: string; url: string; niveau: string };

// Aan welk netwerk een netwerkdossier deze factcheck toeschrijft, met de bron per factcheck (B62).
export async function toeschrijvingen(pub: Publicatie, nummer: string): Promise<Toeschrijving[]> {
  if (!NUMMER.test(nummer)) return [];
  return rijen<Toeschrijving>(pub.db, 'SELECT i.dossier AS sleutel, i.bron AS bron, i.url AS url, i.niveau AS niveau '
    + 'FROM dossier_item i JOIN dossier d ON d.sleutel = i.dossier '
    + "WHERE i.pagina = ? AND i.soort = 'factcheck' AND d.soort = 'netwerk' AND i.bron <> '' ORDER BY i.dossier", nummer);
}

// Per jaar hoeveel factchecks van een dossier er zijn (het jaar van de laatste check); zonder datum telt niet.
export function dossierJaren(pub: Publicatie, sleutel: string): Promise<[string, number][]> {
  return pub.eens(`factcheck:dossierjaren:${sleutel}`, async () => {
    const per = new Map<string, number>();
    for (const r of await rijen<{ d: string }>(pub.db, 'SELECT p.laatste_datum AS d FROM dossier_item i JOIN pagina p '
      + "ON p.nummer = i.pagina WHERE i.dossier = ? AND i.soort = 'factcheck'", sleutel)) {
      const j = begin(r.d, 4);
      if (/^\p{Nd}+$/u.test(j)) per.set(j, (per.get(j) ?? 0) + 1);
    }
    return [...per].sort((a, b) => vergelijk(a[0], b[0]));
  });
}

type Kenmerktelling = { soort: Map<string, number>; vorm: Map<string, number> };

function telKenmerk(r: { soort: string; vorm: string; n: number }[]): Kenmerktelling {
  const uit: Kenmerktelling = { soort: new Map(), vorm: new Map() };
  for (const { soort, vorm, n } of r) {
    if (SOORTEN.includes(soort)) uit.soort.set(soort, (uit.soort.get(soort) ?? 0) + n);
    if (VORMEN.includes(vorm)) uit.vorm.set(vorm, (uit.vorm.get(vorm) ?? 0) + n);
  }
  return uit;
}

// Factchecks per land in de hele uitgave, alleen landen met een naam (`Publicatie.facetten["land"]`).
export function landTelling(pub: Publicatie): Promise<Map<string, number>> {
  return pub.eens('factcheck:landen', async () => {
    const landen = await pub.landen();
    return new Map((await rijen<{ w: string; n: number }>(pub.db,
      "SELECT land AS w, COUNT(*) AS n FROM pagina WHERE land <> '' GROUP BY land"))
      .filter((r) => Object.hasOwn(landen, r.w)).map((r): [string, number] => [r.w, r.n]));
  });
}

// De soort en de vorm in de hele uitgave (`Publicatie.facetten["soort"]`, `["vorm"]`).
export function kenmerkTelling(pub: Publicatie): Promise<Kenmerktelling> {
  return pub.eens('factcheck:kenmerk', async () =>
    telKenmerk(await rijen(pub.db, 'SELECT soort, vorm, COUNT(*) AS n FROM kenmerk GROUP BY soort, vorm')));
}

export type Thematelling = Kenmerktelling & { land: Map<string, number>; jaar: Map<string, number> };

// Binnen een thema (een tweede thema telt mee) per land, jaar, soort en vorm: wat `facetten_van(thema=...)` daarvan
// geeft. Per thema één keer, met de index op thema en op tweede thema.
export function themaTelling(pub: Publicatie, thema: string): Promise<Thematelling> {
  return pub.eens(`factcheck:thema:${thema}`, async () => {
    const [verdeling, kenmerk] = await Promise.all([
      rijen<{ land: string; jaar: string; n: number }>(pub.db, 'SELECT land, substr(laatste_datum, 1, 4) AS jaar, COUNT(*) AS n '
        + 'FROM pagina WHERE thema = ? OR tweede = ? GROUP BY 1, 2', thema, thema),
      rijen<{ soort: string; vorm: string; n: number }>(pub.db, 'SELECT k.soort AS soort, k.vorm AS vorm, COUNT(*) AS n '
        + 'FROM kenmerk k JOIN pagina p ON p.nummer = k.pagina WHERE p.thema = ? OR p.tweede = ? GROUP BY 1, 2', thema, thema),
    ]);
    const uit: Thematelling = { ...telKenmerk(kenmerk), land: new Map(), jaar: new Map() };
    for (const { land, jaar, n } of verdeling) {
      if (land) uit.land.set(land, (uit.land.get(land) ?? 0) + n);
      if (jaar) uit.jaar.set(jaar, (uit.jaar.get(jaar) ?? 0) + n);
    }
    return uit;
  });
}

// Hoeveel factchecks een redactie in de uitgave heeft (`Publicatie.facetten["redactie"]`): per redactie één keer, met de
// index op redactie, in plaats van alle checks van de uitgave bij de eerste factcheck.
export function redactieTelling(pub: Publicatie, redactie: string): Promise<number> {
  return pub.eens(`factcheck:redactie:${redactie}`, async () => (await eerste<{ n: number }>(pub.db,
    'SELECT COUNT(DISTINCT pagina) AS n FROM check_ WHERE redactie = ?', redactie))?.n ?? 0);
}

// De nieuwste check in de uitgave: tot daar loopt het lopende jaar van Verkennen.
export function nieuwsteDatum(pub: Publicatie): Promise<string> {
  return pub.eens('factcheck:nieuwste', async () =>
    (await eerste<{ d: string }>(pub.db, "SELECT COALESCE(MAX(laatste_datum), '') AS d FROM pagina"))?.d ?? '');
}

// De namen van het netwerk: de `NETWERK_NAMEN` in de meeste factchecks, bij gelijke aantallen het laagste nummer van
// Wikidata eerst (`Publicatie.netwerk`).
export function netwerkNamen(pub: Publicatie): Promise<NaamDing[]> {
  const n = GRENZEN.NETWERK_NAMEN;
  return pub.eens(`factcheck:netwerk:${n}`, async () => (await rijen<Rij>(pub.db,
    'SELECT * FROM naam ORDER BY paginas DESC, CAST(substr(nummer, 2) AS INTEGER) LIMIT ?', n)).map(schoneRij).map(naamDing));
}

// De buren van een naam in het netwerk: elke andere naam van het netwerk waarmee hij in minstens `NETWERK_SAMEN`
// factchecks staat, op nummer, zoals de randen van `netwerk()` ze geven. Per naam één keer. De `+` houdt de index op naam
// buiten de tweede kant: zo leest de vraag de pagina's van deze naam (bij de grootste ~5.500) en niet die van alle namen
// van het netwerk (~64.000).
export function buren(pub: Publicatie, q: string, net: NaamDing[]): Promise<[string, number][]> {
  const samen = GRENZEN.NETWERK_SAMEN;
  return pub.eens(`factcheck:buren:${net.length}:${samen}:${q}`, async () => {
    const ids = net.map((x) => x.nummer);
    const r = await rijen<{ naam: string; k: number }>(pub.db, 'SELECT b.naam AS naam, COUNT(*) AS k FROM pagina_naam a '
      + `JOIN pagina_naam b ON b.pagina = a.pagina WHERE a.naam = ? AND +b.naam IN (${ids.map(() => '?').join(', ')}) `
      + 'AND b.naam <> ? GROUP BY b.naam HAVING COUNT(*) >= ?', q, ...ids, q, samen);
    return r.map((x): [string, number] => [x.naam, x.k]).sort((a, b) => vergelijk(a[0], b[0]));
  });
}
