// De factcheck als gegevens, op dit adres (connect-src 'self'): voor de site.
import { alsAntwoord, vraag } from '../../../../lib/platform.js';
import { TALEN } from '../../../../lib/talen.js';

export async function GET({ params }) {
  if (!TALEN.includes(params.taal)) return new Response(null, { status: 404 });
  if (!/^[0-9a-f]{16}$/.test(params.nummer)) return new Response(null, { status: 404 });
  return alsAntwoord(await vraag(`/api/${params.taal}/factcheck/${params.nummer}`), 'public, max-age=300');
}
