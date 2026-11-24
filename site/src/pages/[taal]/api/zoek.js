// Zoeken, op dit adres: de vraag gaat in het bericht naar het platform, nooit in een adres, en wordt nergens gelogd
// (E9.S6 AC3); alleen anoniem opgeteld per dag, als ze gewoon en kort is (B94, `telZoekvraag`).
import { alsAntwoord, telZoekvraag, vraag } from '../../../lib/platform.js';
import { TALEN } from '../../../lib/talen.js';

export async function POST({ params, request }) {
  if (!TALEN.includes(params.taal)) return new Response(null, { status: 404 });
  const bericht = await request.text();
  if (bericht.length > 8192) return new Response('Too large', { status: 413 });
  const a = await vraag(`/api/${params.taal}/zoek`, { methode: 'POST', bericht });
  telZoekvraag(params.taal, bericht, a, request);
  return alsAntwoord(a, 'no-store');
}
