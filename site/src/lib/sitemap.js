// De sitemaps (PLAN #34.2bt, SPECS E9.S8 AC4): `/sitemap.xml` is de index; per taal `/sitemaps/<taal>-vast.xml` met de vaste
// pagina's, thema's, dossiers en namen, en `/sitemaps/<taal>-factchecks-<n>.xml` met de factchecks die in deze stand in die
// taal vindbaar zijn, in delen van hoogstens 50.000 (`/api/<taal>/sitemap`). Alleen wat `index` zegt; een volgend blad van
// een lijst niet, want dat vindt een crawler zelf.
import { haal } from './platform.js';
import { BASIS, TALEN, pad } from './talen.js';
import { NAAMPAGINAS_VINDBAAR } from './vindbaar.js';

const XML = { 'content-type': 'application/xml; charset=utf-8', 'cache-control': 'public, max-age=3600' };
const NS = 'http://www.sitemaps.org/schemas/sitemap/0.9';
const vlucht = (s) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

export const xml = (tekst) => new Response(tekst, { headers: XML });

function urlset(regels) {
  const urls = regels.map((r) => `<url><loc>${vlucht(BASIS + r.href)}</loc>${r.lastmod ? `<lastmod>${r.lastmod}</lastmod>` : ''}</url>`);
  return `<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="${NS}">\n${urls.join('\n')}\n</urlset>\n`;
}

export async function index(stand) {
  const kaarten = [];
  for (const taal of TALEN) {
    kaarten.push(`${taal}-vast.xml`);
    const t = await haal(`/api/${taal}/sitemap?stand=${stand}`);
    for (let d = 1; d <= (t?.delen ?? 0); d++) kaarten.push(`${taal}-factchecks-${d}.xml`);
  }
  const regels = kaarten.map((k) => `<sitemap><loc>${BASIS}/sitemaps/${k}</loc></sitemap>`);
  return `<?xml version="1.0" encoding="UTF-8"?>\n<sitemapindex xmlns="${NS}">\n${regels.join('\n')}\n</sitemapindex>\n`;
}

// De vaste pagina's van een taal: de start, de overzichten, elk thema en onderdeel, elk dossier, de letters en de namen,
// en Factiz Radar (PLAN #37.11, SPECS E10.S4 AC8): het overzicht, elk jaar en elke maand met een check die zoekmachines in
// deze taal zien, en die checks zelf, met de dag van publicatie.
// `lastmod` alleen bij wat met elke uitgave verandert, de dag van de uitgave (PLAN #34.2bz): de start, de lijst, de thema's,
// de redacties, de bronnen en Verkennen tellen mee. Over, Platform, de dossiers en de namen niet: een datum die niet klopt,
// leert een zoekmachine de hele sitemap te negeren.
async function vast(taal) {
  const hrefs = ['', 'fact-checks', 'themes', 'dossiers', 'names', 'newsrooms', 'sources', 'about', 'global-fact-check-database', 'platform', 'explore']
    .map((d) => (d ? pad(taal, d) : pad(taal)));
  hrefs.push(pad(taal, 'explore', 'network'));
  const mee = new Set(['', 'fact-checks', 'themes', 'newsrooms', 'sources', 'explore'].map((d) => (d ? pad(taal, d) : pad(taal))));
  mee.add(pad(taal, 'explore', 'network'));
  for (const th of (await haal(`/api/${taal}/themas`))?.themas ?? []) {
    hrefs.push(th.href, ...(th.onderdelen ?? []).map((o) => o.href));
    mee.add(th.href);
    for (const o of th.onderdelen ?? []) mee.add(o.href);
  }
  for (const d of (await haal(`/api/${taal}/dossiers`))?.dossiers ?? []) hrefs.push(d.href);
  const namen = await haal(`/api/${taal}/namen`);
  if (namen && !namen.concept) {
    for (const g of namen.groepen) hrefs.push(...g.letters.map((l) => l.href));
    // de pagina per naam pas na een juridische toets (`NAAMPAGINAS_VINDBAAR`, PLAN #34.2bw)
    if (NAAMPAGINAS_VINDBAAR) hrefs.push(...((await haal(`/api/${taal}/sitemap?soort=namen`))?.regels ?? []).map((r) => r.href));
  } else {
    hrefs.splice(hrefs.indexOf(pad(taal, 'names')), 1);
  }
  const eigen = new Map();
  const zichtbaar = ((await haal(`/api/${taal}/eigen`))?.checks ?? []).filter((c) => c.vindbaar);
  if (zichtbaar.length) {
    const perioden = new Set();
    for (const c of zichtbaar) {
      const maand = c.href.replace(/[^/]+\/$/u, '');
      perioden.add(maand.replace(/[^/]+\/$/u, '')).add(maand);
      eigen.set(c.href, c.gepubliceerd_iso);
    }
    hrefs.push(pad(taal, 'radar'), ...[...perioden].sort(), ...eigen.keys());
  }
  const dag = (await haal(`/api/${taal}/archief`))?.actueel?.uitgave ?? '';
  return hrefs.map((href) => (eigen.get(href) ? { href, lastmod: eigen.get(href) }
    : dag && mee.has(href) ? { href, lastmod: dag } : { href }));
}

// Eén sitemap uit de index, of null als die er niet is.
export async function kaart(bestand, stand) {
  const m = /^([a-z]+)-(vast|factchecks-([1-9][0-9]*))\.xml$/.exec(bestand ?? '');
  if (!m || !TALEN.includes(m[1])) return null;
  if (m[2] === 'vast') return urlset(await vast(m[1]));
  const d = await haal(`/api/${m[1]}/sitemap?stand=${stand}&deel=${Number(m[3]) - 1}`);
  return d ? urlset(d.regels) : null;
}
