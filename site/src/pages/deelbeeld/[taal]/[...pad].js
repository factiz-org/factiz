// Het deelplaatje (PLAN #34.2aq, #34.2ar; SPECS E9.S23), op het adres van de site: van een factcheck
// (`/deelbeeld/nl/<nummer>.jpg`), een thema of onderdeel (`.../thema/<thema>[/<onderdeel>].jpg`) en een dossier
// (`.../dossier/<sleutel>.jpg`). Het platform tekent het als iemand het vraagt en geeft het een jaar mee (`immutable`),
// want `og:image` zet de versie van de uitgave achter het adres (`?v=`). Niets wordt vooraf gemaakt.
import { alsAntwoord, vraag } from '../../../lib/platform.js';
import { TALEN } from '../../../lib/talen.js';

const VORM = /^(?:[0-9a-f]{16}|thema\/[a-z0-9-]+(?:\/[a-z0-9-]+)?|dossier\/[a-z0-9-]+)\.jpg$/;

export async function GET({ params }) {
  const pad = params.pad ?? '';
  if (!TALEN.includes(params.taal) || !VORM.test(pad)) return new Response(null, { status: 404 });
  const a = await vraag(`/api/${params.taal}/deelbeeld/${pad}`);
  if (a.status !== 200) return new Response(null, { status: a.status === 404 ? 404 : 502 });
  return alsAntwoord(a, 'public, max-age=31536000, immutable');
}
