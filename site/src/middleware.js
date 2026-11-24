// Elke vraag aan de site (PLAN #34.2bo stap 8): www gaat blijvend naar factiz.org, de rest langs de paginacache
// (`lib/paginacache.js`, in Node is die er niet), en elk antwoord krijgt de beveiligingskoppen (`lib/koppen.js`).
import { defineMiddleware } from 'astro:middleware';
import { paginacache, perVerzoek } from '#gegevens';
import { metCache } from './lib/paginacache.js';
import { INDEXNOW_SLEUTEL, indexnowSleutel, metKoppen, naarHoofdadres, securityTxt, weigerMethode } from './lib/koppen.js';
import { stand } from './lib/vindbaar.js';
import { tel, telStoring } from './lib/platform.js';

// Elk verzoek in een eigen context (`perVerzoek`, #34.2bq): in de Worker deelt het zo nooit werk dat een ander verzoek nog doet.
export const onRequest = defineMiddleware((context, next) => perVerzoek(async () => {
  const www = naarHoofdadres(context.url, context.request.headers.get('x-forwarded-proto'));
  if (www) return metKoppen(www);
  const geweigerd = weigerMethode(context.request.method);
  if (geweigerd) return metKoppen(geweigerd);
  if (context.url.pathname === '/.well-known/security.txt') return metKoppen(securityTxt());
  if (context.url.pathname === `/${INDEXNOW_SLEUTEL}.txt` && stand()) return metKoppen(indexnowSleutel());
  const omgeving = paginacache();
  // een storing telt (PLAN #34.2bv): een antwoord van 500 of hoger, of een fout die de pagina niet afmaakt
  try {
    const antwoord = metKoppen(await metCache(context.request, context.locals, next, omgeving && { ...omgeving, tel }));
    if (antwoord.status >= 500) telStoring(context.url);
    return antwoord;
  } catch (fout) {
    telStoring(context.url);
    throw fout;
  }
}));
