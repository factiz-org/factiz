// robots.txt (PLAN #34.2bt, SPECS E9.S8 AC5). Dicht tot de PO de site per stap openzet (#33.9, B73), zoals het platform in
// Python (`factiz_site/app.py`, robots); elke pagina zegt daarnaast zelf noindex. Open: elke crawler mag alles, ook voor AI
// (PO 2026-11-16: "Everything, training too"), behalve de interne paden en de lijsten met filters, die eindeloos te
// combineren zijn en zelf noindex zeggen. Een volgend blad, de letters van de namen, de deelplaatjes en de opmaak (met een
// versie in het adres) blijven open; de langste regel wint (RFC 9309).
import { HOOFDADRES } from '../lib/koppen.js';
import { stand } from '../lib/vindbaar.js';

export const DICHT = 'User-agent: *\nDisallow: /\n';
export const OPEN = ['User-agent: *', 'Allow: /', 'Disallow: /api/', 'Disallow: /_geheugen/', 'Disallow: /_deelbeeld/',
  'Disallow: /*?', 'Allow: /*?p=', 'Allow: /*names/?letter=', 'Allow: /deelbeeld/', 'Allow: /static/', 'Allow: /_astro/', '',
  `Sitemap: https://${HOOFDADRES}/sitemap.xml`, ''].join('\n');

export function GET() {
  return new Response(stand() ? OPEN : DICHT, {
    headers: { 'content-type': 'text/plain; charset=utf-8', 'cache-control': 'public, max-age=3600' },
  });
}
