// De eigen factchecks van Factiz in TypeScript (PLAN #37.4, B82, DESIGN §4x): de lijst en een check, alleen in de taal van
// de check; hetzelfde antwoord als `api_eigen_lijst` en `api_eigen` in `factiz_site/app.py`.
import { LABELS, datum, getal, maandJaar, pad, richting, stempel, taalnaamIn, tekst } from './i18n.ts';
import { link } from './tekst.ts';
import { NIET_GEVONDEN, type Ingang, kenmerken, landnaam, lijstUrl, themanaam, vertaalregel } from './gedeeld.ts';
import { kort } from './tekst.ts';
import { dossiersVan } from './factcheck-gegevens.ts';
import { eigenIn } from './eigentaal.ts';
import type { Bewering, Dossier, EigenCheck, Publicatie } from './publicatie.ts';
import { CONTACT, quote } from './factcheck.ts';

const OORDELEN = ['onwaar', 'misleidend', 'context', 'grotendeels', 'klopt', 'onbewezen'];
const NODIG = '[FEIT NODIG: ';
const STUK = /(\[[0-9]+\]|\[FEIT NODIG: [^\]]*\])/;
const NUMMER = /^\[[0-9]+\]$/;
const HOST = /^https?:\/\/([^/:?#]+)/;

export type Stuk = { t: string } | { n: number } | { nodig: string };

const gewoon = (s: string) => s.split(/\s+/u).filter(Boolean).join(' ');

// Een zin in stukken (`app.stukken`): tekst, het nummer van een bron tegen het woord ervoor, en wat nog na te gaan is.
export function stukken(tekst_: string | null | undefined): Stuk[] {
  const uit: Stuk[] = [];
  for (const deel of gewoon(tekst_ ?? '').split(STUK)) {
    if (!deel) continue;
    if (deel.startsWith(NODIG)) uit.push({ nodig: deel.slice(NODIG.length, -1) });
    else if (NUMMER.test(deel)) {
      const vorige = uit[uit.length - 1];
      if (vorige && 't' in vorige) {
        vorige.t = vorige.t.trimEnd();
        if (!vorige.t) uit.pop();
      }
      uit.push({ n: parseInt(deel.slice(1, -1), 10) });
    } else uit.push({ t: deel });
  }
  return uit;
}

export function alineas(tekst_: string | null | undefined): Stuk[][] {
  return (tekst_ ?? '').trim().split('\n\n').filter((a) => a.trim()).map(stukken);
}

function host(url: string): string {
  const m = url.match(HOST);
  const h = m ? m[1].toLowerCase() : '';
  return h.startsWith('www.') ? h.slice(4) : h;
}

// Waar een eigen check op de Radar van een taal staat (`app.radargroep`): uit die taal zelf, internationaal of uit een
// ander land.
function radargroep(c: EigenCheck): string {
  if (!('brontaal' in c)) return 'hier';
  return c.reikwijdte === 'internationaal' ? 'internationaal' : 'elders';
}
const ORDE: Record<string, number> = { hier: 0, internationaal: 1, elders: 2 };

// Zoekmachines zien een eigen check in haar eigen taal en in een vertaling die de redactie las; een concept nooit
// (`app.eigen_vindbaar`, PLAN #37.11).
const vindbaar = (c: EigenCheck, taal: string) => !c.concept && (c.vindbaar_in ?? []).includes(taal);
// de Radar van een maand (`2026-11`): `/nl/radar/2026/11/` (`app.maandpad`)
const maandpad = (taal: string, maand: string) => pad(taal, 'radar', ...maand.split('-'));

// Een eigen factcheck als kaart, met dezelfde velden als een rij van het archief (`app.eigenrij`, `Rij.jsx`): het zegel met
// het oordeel, de datum, de kop, en het thema, het land, de soort en de vorm van haar pagina in het archief.
async function rij(pub: Publicatie, taal: string, c: EigenCheck, nummer: string, p: Bewering | undefined) {
  const t = (s: string) => tekst(taal, s);
  const thema = (p?.thema as string | null) ?? null, land = (p?.land as string | null) ?? null;
  const [themaNaam, landNaam] = await Promise.all([themanaam(pub, taal, thema), landnaam(pub, taal, land)]);
  const bron = c.brontaal ? (await pub.eigen()).find((x) => x.sleutel === c.sleutel) ?? c : null;
  return {
    nummer, href: c.paden[taal], eigen: t(`eigen_oordeel_${c.oordeel}`),
    soort: p && LABELS.includes(p.label as string) ? p.label : 'geen',
    datum: datum(taal, c.gepubliceerd ?? ''), tekst: c.kop, taal, richting: richting(taal),
    origineel: bron ? { regel: vertaalregel(taal, c.brontaal as string, taal), tekst: kort(bron.kop, 140), taal: c.brontaal,
                        richting: richting(c.brontaal as string) } : null,
    thema: thema && themaNaam ? { sleutel: thema, naam: themaNaam } : null,
    land: land && landNaam ? { code: land, naam: landNaam } : null,
    kenmerken: kenmerken(taal, p?.kenmerk ?? null),
    concept: c.concept ? t('eigen_concept') : '',
  };
}

// De kaarten van een lijst, met één vraag voor alle pagina's in het archief (een vraag aan D1 kost ~20 ms).
async function kaarten(pub: Publicatie, taal: string, checks: EigenCheck[]) {
  const paginas = await pub.eigenPaginas();
  const nummers = checks.map((c) => Object.keys(paginas).find((nr) => paginas[nr] === c.sleutel) ?? '');
  const rijen = await pub.beweringen(nummers.filter(Boolean), taal);
  return Promise.all(checks.map(async (c, i) => kaart(taal, c, await rij(pub, taal, c, nummers[i], rijen.get(nummers[i])))));
}

function kaart(taal: string, c: EigenCheck, r: Awaited<ReturnType<typeof rij>>) {
  return { sleutel: c.sleutel, kop: c.kop, oordeel: c.oordeel, rij: r, oordeel_tekst: tekst(taal, `eigen_oordeel_${c.oordeel}`),
           datum: datum(taal, c.gepubliceerd ?? ''), gepubliceerd_iso: c.gepubliceerd || '', href: c.paden[taal], concept: c.concept,
           vertaald: 'brontaal' in c, vindbaar: vindbaar(c, taal), groep: radargroep(c) };
}

function check(taal: string, c: EigenCheck, nummer: string) {
  const t = (s: string, w: Record<string, unknown> = {}) => tekst(taal, s, w);
  const oordeel = t(`eigen_oordeel_${c.oordeel}`);
  const kenmerken = [...(c.soort ? [t(`soort_${c.soort}`)] : []), ...(c.vorm ? [t(`vorm_${c.vorm}`)] : [])];
  const posts = Number(c.posts) || 0;
  return {
    sleutel: c.sleutel, taal, brontaal: (c.brontaal as string | undefined) ?? c.taal, concept: c.concept,
    // haar adres in deze taal en in elke taal waarin ze er is, en waar zoekmachines haar zien (`app.api_eigen`, PLAN #37.11)
    href: c.paden[taal], paden: c.paden, vindbaar_in: c.concept ? [] : [...(c.vindbaar_in ?? [])], vindbaar: vindbaar(c, taal),
    maand: { tekst: maandJaar(taal, c.maand), href: maandpad(taal, c.maand) },
    // een machinevertaling zegt dat ze er een is, en of de redactie haar las, met de link naar het origineel (#37.8)
    vertaling: c.brontaal ? { tekst: t(c.vertaling_nagelezen ? 'eigen_vertaling_nagelezen' : 'eigen_vertaling',
                                       { bron: taalnaamIn(taal, c.brontaal as string) }),
                              origineel: c.paden[c.brontaal as string], link: t('eigen_origineel'),
                              nagelezen: Boolean(c.vertaling_nagelezen) } : null,
    // haar pagina in het archief, voor de zijbalk, het thema en de verbanden van elke factcheck (`app.api_eigen`)
    nummer,
    kop: c.kop, oordeel: c.oordeel, oordeel_tekst: oordeel, oordeel_zin: stukken(c.oordeel_zin),
    kenmerken: kenmerken.join(' · '), bewering: c.bewering, platform: c.platform,
    eerst_gezien: datum(taal, c.eerst_gezien),
    posts_tekst: posts === 1 ? t('eigen_post') : posts ? t('eigen_posts', { n: getal(taal, posts) }) : '',
    bereik: c.bereik || '',
    kort: stukken(c.kort), tekst: alineas(c.tekst), niet_weten: alineas(c.niet_weten || ''),
    beelden: (c.beeld ?? []).map((b) => ({
      rol: b.rol, stempel: b.rol === 'rondgaat' && b.stempel ? oordeel : '', bijschrift: b.bijschrift || '', alt: b.alt || '',
      link: link(b.link), host: host(link(b.link)), pad: b.pad || '', breedte: b.breedte || 0, hoogte: b.hoogte || 0 })),
    rekensom: (c.rekensom ?? []).map((r) => ({ geval: r.geval, som: r.som, uitkomst: r.uitkomst })),
    tijdlijn: (c.tijdlijn ?? []).map((r) => ({ datum: datum(taal, r.datum), tijd: r.tijd || '',
                                               wat: gewoon(r.wat.replace(/\s*\[[0-9]+\]/gu, '')) })),
    bronnen: c.bron.map((b) => ({
      nr: b.nr, soort_tekst: t(`eigen_bron_${b.soort}`), uitgever: b.uitgever, titel: b.titel, datum: datum(taal, b.datum),
      url: b.prive ? '' : link(b.url), host: b.prive ? '' : host(link(b.url)), archief: link(b.archief), prive: Boolean(b.prive),
      // een post die niet meer te zien is, zonder kopie (B84), of waarvan geen kopie te maken was
      weg: Boolean(b.weg), geen_kopie: String(b.geen_kopie ?? '') })),
    auteur: c.auteur, nalezer: c.nalezer || '', nagelezen_in: c.nagelezen_in || '', gepubliceerd: datum(taal, c.gepubliceerd ?? ''),
    gepubliceerd_iso: c.gepubliceerd || '',
    nog_doen: c.concept ? (c.nog_doen ?? []).map((n) => stukken(n)) : [],
    // wat nog uit te zoeken is, ook bij een gepubliceerde check, met de oproep om bij te dragen (B84, `app.api_eigen`)
    nog_uitzoeken: [...(c.nog_uitzoeken ?? [])],
    bijdragen: { href: `mailto:${CONTACT}?subject=${quote(t('eigen_bijdragen_onderwerp', { kop: c.kop }), '')}`, adres: CONTACT },
  };
}

// de naam van de eigen redactie in het archief, zoals `publiceren.EIGEN_BRON` haar zet (`app.EIGEN_REDACTIE`)
export const EIGEN_REDACTIE = 'Factiz';

// De zijkolom van Factiz Radar (`app.radar_zijkolom`): hoe het werkt, wat we vonden (de tellingen van het archief voor de
// redactie Factiz), de dossiers met de checks, en een tip; meeste eerst, dan op naam of plek.
async function zijkolom(pub: Publicatie, taal: string, checks: EigenCheck[]) {
  const t = (s: string) => tekst(taal, s);
  const tel = await pub.facettenVan({ redactie: EIGEN_REDACTIE });
  const rij = (wat: string, naam: (w: string) => string) => Object.entries(tel[wat] ?? {})
    .sort((a, b) => b[1] - a[1] || (a[0] < b[0] ? -1 : a[0] > b[0] ? 1 : 0)).filter(([, n]) => n)
    .map(([w, n]) => ({ naam: naam(w), aantal: getal(taal, n), href: lijstUrl(taal, { redactie: EIGEN_REDACTIE, [wat]: [w] }) }));
  const alle = await pub.dossiers();
  const plek = new Map(alle.map((d, i) => [d.sleutel, i]));
  const paginas = await pub.eigenPaginas();
  const gepubliceerd = checks.filter((c) => !c.concept);
  const lijsten = await Promise.all(gepubliceerd.map((c) => {
    const nummer = Object.keys(paginas).find((nr) => paginas[nr] === c.sleutel) ?? '';
    return nummer ? dossiersVan(pub, nummer) : Promise.resolve([] as Dossier[]);
  }));
  const per = new Map<string, [Dossier, number]>();
  for (const ds of lijsten) for (const d of ds) { const x = per.get(d.sleutel); if (x) x[1]++; else per.set(d.sleutel, [d, 1]); }
  const dossiers = [...per.values()].sort((a, b) => b[1] - a[1] || (plek.get(a[0].sleutel) ?? 0) - (plek.get(b[0].sleutel) ?? 0));
  // de maanden met een check in deze taal, de nieuwste eerst (`app.radar_zijkolom`, PLAN #37.11)
  const perMaand = new Map<string, number>();
  for (const c of checks) perMaand.set(c.maand, (perMaand.get(c.maand) ?? 0) + 1);
  const maanden = [...perMaand].sort((a, b) => (a[0] < b[0] ? 1 : a[0] > b[0] ? -1 : 0))
    .map(([m, n]) => ({ naam: maandJaar(taal, m), href: maandpad(taal, m), aantal: getal(taal, n) }));
  return {
    maanden,
    oordelen: rij('oordeel', (w) => stempel(taal, w)),
    soorten: rij('soort', (w) => t(`soort_${w}`)),
    vormen: rij('vorm', (w) => t(`vorm_${w}`)),
    dossiers: dossiers.map(([d, n]) => ({ naam: d.naam[taal], href: pad(taal, 'dossiers', d.sleutel), aantal: getal(taal, n) })),
    archief: lijstUrl(taal, { redactie: EIGEN_REDACTIE }),
    tip: { href: `mailto:${CONTACT}?subject=${quote(t('radar_tip_onderwerp'), '')}`, adres: CONTACT },
  };
}

// een jaar van vier cijfers en een maand van twee, 01 tot 12; `00` als er geen maand is (`app._periode`)
const periodeGoed = (jaar: string, maand = '00') => /^[0-9]{4}$/u.test(jaar) && /^[0-9]{2}$/u.test(maand) && Number(maand) <= 12;

// De lijst, alle of van één jaar of maand (`app.eigen_lijst`, PLAN #37.11); de zijkolom telt altijd de hele Radar.
async function lijst(pub: Publicatie, taal: string, alle: EigenCheck[], jaar = '', maand = '') {
  const periode = maand ? `${jaar}-${maand}` : jaar;
  const checks = jaar ? alle.filter((c) => c.maand.startsWith(periode)) : alle;
  if (!checks.length) return NIET_GEVONDEN;
  return { status: 200, body: { titel: tekst(taal, 'eigen_titel'), inleiding: tekst(taal, 'eigen_inleiding'),
    periode: jaar ? { tekst: maand ? maandJaar(taal, periode) : jaar, jaar, jaar_href: pad(taal, 'radar', jaar), maand,
                      href: pad(taal, 'radar', jaar, maand) } : null,
    checks: await kaarten(pub, taal, checks), zijkolom: await zijkolom(pub, taal, alle) } };
}

// Eén check (`app.eigen_antwoord`), in de taal van de site of vertaald.
async function antwoordCheck(pub: Publicatie, taal: string, alle: EigenCheck[], sleutel: string) {
  const c = alle.find((x) => x.sleutel === sleutel);
  if (!c || !OORDELEN.includes(c.oordeel)) return NIET_GEVONDEN;
  const paginas = await pub.eigenPaginas();
  const nummer = Object.keys(paginas).find((nr) => paginas[nr] === c.sleutel) ?? '';
  return { status: 200, body: check(taal, c, nummer) };
}

export const ingangen: Record<string, Ingang> = {
  // de lijst; een check op haar werknaam (het oude adres) of de Radar van een jaar; de Radar van een maand; een check op
  // haar adres, of de naam van een andere taal als doorverwijzing (`app.api_eigen`, `app.api_eigen_periode`, PLAN #37.11)
  eigen: { delen: [0, 1, 2, 3], async f(pub, taal, delen) {
    const alle = (await pub.eigen()).map((c) => eigenIn(c, taal)).filter((c): c is EigenCheck => c !== null)
      .sort((a, b) => ORDE[radargroep(a)] - ORDE[radargroep(b)]);
    if (!delen.length) return lijst(pub, taal, alle);
    if (delen.length === 1) {
      if (/^[0-9]/u.test(delen[0])) return periodeGoed(delen[0]) ? lijst(pub, taal, alle, delen[0]) : NIET_GEVONDEN;
      return antwoordCheck(pub, taal, alle, delen[0]);
    }
    const [jaar, maand, naam] = delen;
    if (!periodeGoed(jaar, maand) || maand === '00') return NIET_GEVONDEN;
    if (naam === undefined) return lijst(pub, taal, alle, jaar, maand);
    const staart = `/radar/${jaar}/${maand}/${naam}/`;
    const c = (await pub.eigen()).find((x) => Object.values(x.paden ?? {}).some((p) => p.endsWith(staart)));
    if (!c || !(taal in c.paden)) return NIET_GEVONDEN;
    if (!c.paden[taal].endsWith(staart)) return { status: 200, body: { doorsturen: c.paden[taal] } };
    return antwoordCheck(pub, taal, alle, c.sleutel);
  } },
};
