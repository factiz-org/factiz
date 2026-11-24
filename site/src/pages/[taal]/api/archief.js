// Dezelfde ingang als het platform, op dit adres, zodat de browser alleen met deze site praat (connect-src 'self').
import { alsAntwoord, vraag } from '../../../lib/platform.js';
import { TALEN } from '../../../lib/talen.js';

export async function GET({ params, url }) {
  if (!TALEN.includes(params.taal)) return new Response(null, { status: 404 });
  return alsAntwoord(await vraag(`/api/${params.taal}/archief${url.search}`), 'public, max-age=300');
}
