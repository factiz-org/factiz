// De gegevens van de site (B76, B80): het platform in TypeScript (`src/platform/`), rechtstreeks aangeroepen op de server,
// zonder netwerk ertussen. Waar de uitgave staat zet de bouw (`#gegevens`): in de Worker D1, in Node een SQLite-bestand.
// Nooit vanuit de browser van een ander.
import { antwoord } from '../platform/api.ts';
import { tel as telBezoek, telVraag } from '../platform/gedeeld.ts';
import { zoekvraagVoorTellen } from './zoekvragen.js';
import { gegevens } from '#gegevens';
import { PAD, TALEN } from './talen.js';

// Het adres van de site, als tekst op Over Factiz; gelijk aan CONTACT in factiz_site/app.py (een test bewaakt dat).
export const CONTACT = 'info@factiz.org';

// Eén ingang van het platform als antwoord: status, en JSON of bytes. Een omleiding (het nummer van een andere formulering)
// volgt het zelf, zoals `fetch` dat deed toen het platform een eigen server was: de pagina toont de bewering, met haar
// eigen nummer in de canonical.
export async function vraag(pad, { methode = 'GET', bericht = null } = {}, sprongen = 3) {
  const url = new URL(pad, 'http://platform');
  const a = await antwoord(gegevens(), decodeURIComponent(url.pathname), url.searchParams, { methode, bericht });
  if (a.adres && a.status >= 300 && a.status < 400 && sprongen > 0) return vraag(a.adres, {}, sprongen - 1);
  return a;
}

// De gegevens van een ingang, of niets als die er niet is.
export async function haal(pad) {
  const a = await vraag(pad);
  return a.status === 200 ? a.body : null;
}

// Een antwoord van het platform als antwoord van de site, met de bewaartijd erbij.
export function alsAntwoord(a, bewaar) {
  if (a.bytes) return new Response(a.bytes, { status: a.status, headers: { 'content-type': a.type, 'cache-control': bewaar } });
  if (a.status !== 200) return new Response(a.tekst ?? null, { status: a.status });
  return new Response(JSON.stringify(a.body), { status: 200, headers: { 'content-type': 'application/json', 'cache-control': bewaar } });
}

// Anoniem tellen (PLAN #34.2ba, SPECS E9.S26, B78): welke soort pagina, in welke taal, en of de user-agent een robot is.
// Die wordt alleen hier gelezen en gaat niet mee. Een teller breekt nooit een pagina.
const ROBOT = /bot|crawl|spider|slurp|preview|fetch|curl|wget|python|httpclient|headless|lighthouse|monitor/i;

// Een storing (PLAN #34.2bv): een antwoord van 500 of hoger, geteld per dag en taal (uit het pad), van wie ook; geen adres.
export function telStoring(adres) {
  gegevens();
  const eerste = adres.pathname.split('/')[1] ?? '';
  const taal = TALEN.find((t) => PAD[t] && PAD[t] === eerste) ?? 'en';
  try { telBezoek('storing', taal); } catch { /* een teller breekt nooit een pagina */ }
}

export function tel(soort, taal, request) {
  // de teller hangt `gegevens()` op (in de Worker de D1 `TELLINGEN`): eerst dat, want een pagina zonder gegevens (Over)
  // of uit de paginacache vraagt het platform niets, en op een nieuwe server of Worker telde zo'n eerste bezoek niet
  gegevens();
  const robot = ROBOT.test(request.headers.get('user-agent') ?? '');
  try { telBezoek(robot ? 'robot' : soort, taal); } catch { /* onbekend: niet tellen */ }
}

// Wat mensen zoeken (B94, PLAN #37.17): na het antwoord van het platform, alleen een gewone getypte vraag van een mens
// (`zoekvraagVoorTellen`); de user-agent alleen om een robot over te slaan, en die gaat niet mee. Nooit wachten, nooit
// een pagina breken.
export function telZoekvraag(taal, bericht, antwoord, request) {
  gegevens();
  const robot = ROBOT.test(request.headers.get('user-agent') ?? '');
  try {
    const vraag = zoekvraagVoorTellen(bericht, antwoord?.status === 200 ? antwoord.body : null, robot);
    if (vraag) telVraag(taal, vraag);
  } catch { /* een teller breekt nooit een pagina */ }
}
