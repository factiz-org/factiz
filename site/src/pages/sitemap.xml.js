// De index van de sitemaps (PLAN #34.2bt), alleen in een open stand (`lib/vindbaar.js`).
import { index, xml } from '../lib/sitemap.js';
import { stand } from '../lib/vindbaar.js';

export async function GET() {
  const st = stand();
  return st ? xml(await index(st)) : new Response(null, { status: 404 });
}
