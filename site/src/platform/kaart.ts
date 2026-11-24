// De ingang voor de sitemaps onder `/api/<taal>/sitemap` (PLAN #34.2bt, SPECS E9.S8 AC4), gelijk aan `api_sitemap` in
// `factiz_site/app.py`: per taal en stand (1, 2 of 3) hoeveel factchecks vindbaar zijn en in hoeveel delen, een deel zelf
// (`deel`), of de namen (`soort=namen`). Welke stand geldt, weet alleen de site. Elke andere vraag: niet gevonden.
import { NIET_GEVONDEN, type Ingang } from './gedeeld.ts';
import { pad } from './i18n.ts';
import { SITEMAP_DEEL } from './publicatie.ts';

export const ingangen: Record<string, Ingang> = {
  sitemap: { async f(pub, taal, _delen, vraag) {
    const sleutels = [...vraag.keys()];
    const set = new Set(sleutels);
    if (sleutels.length !== set.size) return NIET_GEVONDEN;
    if (set.size === 1 && set.has('soort')) {
      if (vraag.get('soort') !== 'namen' || !(await pub.heeftNamen())) return NIET_GEVONDEN;
      return { status: 200, body: { regels: (await pub.sitemapNamen()).map((q) => ({ href: pad(taal, 'names', q) })) } };
    }
    const s = vraag.get('stand');
    if (!set.has('stand') || [...set].some((k) => k !== 'stand' && k !== 'deel') || !['1', '2', '3'].includes(s as string)) return NIET_GEVONDEN;
    const stand = Number(s);
    const totaal = await pub.sitemapTelling(taal, stand);
    const delen = Math.ceil(totaal / SITEMAP_DEEL);
    if (!set.has('deel')) return { status: 200, body: { stand, per_deel: SITEMAP_DEEL, totaal, delen } };
    const deel = vraag.get('deel') as string;
    if (!/^[0-9]+$/.test(deel) || String(Number(deel)) !== deel || Number(deel) >= delen) return NIET_GEVONDEN;
    return { status: 200, body: { stand, deel: Number(deel), regels: (await pub.sitemapDeel(taal, stand, Number(deel)))
      .map(([nummer, lastmod]) => ({ href: pad(taal, 'fact-checks', nummer), lastmod })) } };
  } },
};
