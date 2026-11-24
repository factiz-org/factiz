// De site op factiz.org (B80, PLAN #34.2bo stap 8). Elk antwoord krijgt dezelfde beveiligingskoppen als het platform in
// Python (`factiz_site/app.py`, KOPPEN), behalve de CSP: die schrijft Astro zelf, met de hashes van zijn eigen stukjes
// script (astro.config.mjs). En de site heeft één adres: www.factiz.org stuurt blijvend door naar factiz.org, want het
// zoeken (een gepost formulier) werkt alleen op het adres dat Astro kent (`security.allowedDomains`).

export const KOPPEN = {
  'X-Content-Type-Options': 'nosniff',
  // een redactie ziet alleen dat de bezoeker van factiz.org kwam, nooit welke pagina (PLAN #34.2k)
  'Referrer-Policy': 'strict-origin-when-cross-origin',
  'X-Frame-Options': 'DENY',
  'Strict-Transport-Security': 'max-age=31536000; includeSubDomains',
  'Permissions-Policy': 'camera=(), microphone=(), geolocation=()',
  'Cross-Origin-Opener-Policy': 'same-origin',
};

export const HOOFDADRES = 'factiz.org';
const NEVENADRESSEN = new Set(['www.factiz.org']);

// Een bezoek aan www, of aan factiz.org over gewone http (#34.2bq): blijvend naar hetzelfde pad en dezelfde vraag op
// https://factiz.org. Gewone http alleen als Cloudflare het zegt (`protocol`: de kop x-forwarded-proto); `wrangler dev` geeft
// elk lokaal verzoek als http://factiz.org door, zonder die kop, en mag niet doorverwijzen. Anders null.
export function naarHoofdadres(adres, protocol = null) {
  if (NEVENADRESSEN.has(adres.hostname)) return doorNaar(adres);
  if (adres.hostname === HOOFDADRES && adres.protocol === 'http:' && protocol === 'http') return doorNaar(adres);
  return null;
}

function doorNaar(adres) {
  return new Response(null, { status: 301, headers: { location: `https://${HOOFDADRES}${adres.pathname}${adres.search}` } });
}

// Een kopie met de koppen erbij (een antwoord uit de cache of een doorverwijzing heeft koppen die niet veranderen); wat
// een pagina zelf zette, blijft.
export function metKoppen(antwoord) {
  const uit = new Response(antwoord.body, antwoord);
  for (const [naam, waarde] of Object.entries(KOPPEN)) if (!uit.headers.has(naam)) uit.headers.set(naam, waarde);
  // een pagina zegt haar tekenset ook in de kop, niet alleen in de HTML (#34.2bq)
  if ((uit.headers.get('content-type') ?? '').trim() === 'text/html') uit.headers.set('content-type', 'text/html; charset=utf-8');
  return uit;
}

// Alleen lezen en zoeken (#34.2bq): GET, HEAD en POST; elke andere methode krijgt 405, met wat wel mag.
export const METHODES = ['GET', 'HEAD', 'POST'];
export function weigerMethode(methode) {
  if (METHODES.includes(methode)) return null;
  return new Response(null, { status: 405, headers: { allow: METHODES.join(', ') } });
}

// Waar een onderzoeker een zwakke plek meldt (RFC 9116, #34.2bq). De vervaldatum vernieuwen vóór ze verloopt; een toets
// waarschuwt een maand vooraf.
export const SECURITY_VERLOOPT = '2027-11-01T00:00:00.000Z';
export function securityTxt() {
  return new Response([
    'Contact: mailto:info@factiz.org',
    `Expires: ${SECURITY_VERLOOPT}`,
    'Preferred-Languages: nl, en',
    'Canonical: https://factiz.org/.well-known/security.txt',
    '',
  ].join('\n'), { headers: { 'content-type': 'text/plain; charset=utf-8', 'cache-control': 'public, max-age=86400' } });
}

// De sleutel van IndexNow (PLAN #34.2bt, SPECS E9.S8 AC7): openbaar, want een zoekmachine leest hem op `/<sleutel>.txt` om
// te zien dat een melding van ons komt; alleen in een open stand. Gelijk aan `doublecheck/indexnow.py` (SLEUTEL).
export const INDEXNOW_SLEUTEL = '34e72c3d34148a19b8beeb1a44fad523';
export function indexnowSleutel() {
  return new Response(INDEXNOW_SLEUTEL, { headers: { 'content-type': 'text/plain; charset=utf-8', 'cache-control': 'public, max-age=86400' } });
}

// Dezelfde koppen voor de statische bestanden van de Worker, waar de Worker niet aan te pas komt (`_headers`, door
// scripts/worker-voorraad.mjs achter de regels van Astro gezet).
export function kopbestand() {
  return ['/*', ...Object.entries(KOPPEN).map(([naam, waarde]) => `  ${naam}: ${waarde}`)].join('\n') + '\n';
}
