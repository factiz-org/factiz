// De paginacache van de Worker (B80, PLAN #34.2bo stap 8): een pagina die klaar is, gaat in de cache van Cloudflare, en een
// volgend bezoek komt daaruit, zonder platform en zonder D1. Alleen GET zonder vraagteken in het adres, met status 200 en
// een HTML-pagina of een deelplaatje: een lijst met filters, een zoekvraag (POST), een doorverwijzing of een 404 nooit, dus
// niets wat een bezoeker stuurt (B78). De sleutel draagt de versie van de uitrol: elke uitrol begint leeg. Een bezoek uit
// de cache telt met de soort en taal die de pagina zelf telde, uit een merk op de bewaarde kopie dat de bezoeker niet ziet.
// In Node is er geen cache (`omgeving` null) en gebeurt er niets anders dan de pagina maken.

const DUUR = 7 * 24 * 3600;                 // de sleutel wisselt bij elke uitrol, dus lang mag
// Wat de browser van de bezoeker bewaart (#34.2bq): een pagina kort, zodat een nieuwe uitgave binnen vijf minuten te zien is;
// de lange bewaartijd hierboven geldt alleen voor de cache van de Worker, waarvan de sleutel per uitrol wisselt.
const BROWSER = { 'text/html': 'public, max-age=300', 'image/jpeg': 'public, max-age=86400',
  'application/xml': 'public, max-age=3600', 'text/plain': 'public, max-age=3600' };
const MERK = 'x-factiz-tel';
// ook de sitemaps, robots.txt en llms.txt (#34.2bt): die vragen per taal tot ~100.000 rijen aan D1, en de stand wisselt
// alleen met een uitrol, dus met de sleutel
const SOORTEN = /^(text\/html|image\/jpeg|application\/xml|text\/plain)\b/;

// Een deelplaatje heeft bij delen `?v=<uitgave>` in zijn adres (zodat een app een nieuwe versie ophaalt); alleen die ene
// vraag, in de vorm van een uitgave, gaat mee in de sleutel (#34.2bq). Elke andere vraag in een adres: nooit in de cache.
const UITGAVE = /^\?v=\d{4}-\d{2}-\d{2}[a-z]?$/;

function bewaarbaar(adres) {
  return !adres.search || (adres.pathname.startsWith('/deelbeeld/') && UITGAVE.test(adres.search));
}

function sleutel(adres, versie) {
  return new Request(`${adres.origin}/__pagina/${encodeURIComponent(versie)}${adres.pathname}${adres.search}`);
}

// `maak` maakt de pagina (Astro); `locals.telling` is [soort, taal] als de pagina zichzelf telde. `omgeving`:
// { cache, versie, waitUntil, tel } in de Worker, null in Node.
export async function metCache(request, locals, maak, omgeving) {
  const adres = new URL(request.url);
  if (!omgeving || request.method !== 'GET' || !bewaarbaar(adres)) return maak();
  const k = sleutel(adres, omgeving.versie);
  const bewaard = await omgeving.cache.match(k);
  if (bewaard) {
    const telling = bewaard.headers.get(MERK);
    if (telling) {
      const [soort, taal] = telling.split(' ');
      omgeving.tel(soort, taal, request);
    }
    const uit = new Response(bewaard.body, bewaard);
    uit.headers.delete(MERK);
    uit.headers.set('x-factiz-cache', 'hit');
    return voorDeBrowser(uit);
  }
  const antwoord = await maak();
  const soort = antwoord.headers.get('content-type') ?? '';
  if (antwoord.status !== 200 || !SOORTEN.test(soort) || antwoord.headers.has('set-cookie')) return antwoord;
  const kopie = new Response(antwoord.clone().body, antwoord);
  kopie.headers.set('cache-control', `public, max-age=${DUUR}`);
  if (locals.telling) kopie.headers.set(MERK, locals.telling.join(' '));
  omgeving.waitUntil(omgeving.cache.put(k, kopie).catch(() => {}));
  const uit = new Response(antwoord.body, antwoord);
  uit.headers.set('x-factiz-cache', 'miss');
  return voorDeBrowser(uit);
}

function voorDeBrowser(antwoord) {
  const soort = (antwoord.headers.get('content-type') ?? '').split(';')[0].trim();
  if (BROWSER[soort]) antwoord.headers.set('cache-control', BROWSER[soort]);
  return antwoord;
}
