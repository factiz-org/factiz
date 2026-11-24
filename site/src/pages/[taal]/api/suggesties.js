// Suggesties tijdens het typen, op dit adres: de vraag gaat in het bericht door, nooit in een adres, en wordt nergens
// bewaard of gelogd.
import { alsAntwoord, vraag } from '../../../lib/platform.js';
import { TALEN } from '../../../lib/talen.js';

export async function POST({ params, request }) {
  if (!TALEN.includes(params.taal)) return new Response(null, { status: 404 });
  const bericht = await request.text();
  if (bericht.length > 2048) return new Response('Too large', { status: 413 });
  return alsAntwoord(await vraag(`/api/${params.taal}/suggesties`, { methode: 'POST', bericht }), 'no-store');
}
