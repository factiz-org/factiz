// Eén sitemap per taal en soort (PLAN #34.2bt), alleen in een open stand.
import { kaart, xml } from '../../lib/sitemap.js';
import { stand } from '../../lib/vindbaar.js';

export async function GET({ params }) {
  const st = stand();
  const tekst = st ? await kaart(params.bestand, st) : null;
  return tekst ? xml(tekst) : new Response(null, { status: 404 });
}
