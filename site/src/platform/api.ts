// De ingangen van het platform onder `/api/<taal>/` in TypeScript (B80, PLAN #34.2bo): hetzelfde pad, na inlezen dezelfde
// JSON en dezelfde 404 als `factiz_site/app.py`. Elke groep ingangen staat in een eigen bestand; hier alleen de weg ernaartoe.
// `tests/test_platform_ts*.py` en `python -m factiz_site.gelijk` leggen het naast Python.
import type { Db } from './db.ts';
import { TALEN, gemerkt, merkDiep } from './i18n.ts';
import { Fout404, MAX_BERICHT, NIET_GEVONDEN, SOORTEN, type Antwoord, type Ingang, leesBericht, publicatie, tel } from './gedeeld.ts';
import { ingangen as lijsten } from './lijsten.ts';
import { ingangen as factcheck } from './factcheck.ts';
import { ingangen as verkennen } from './verkennen.ts';
import { ingangen as zoeken } from './zoeken.ts';
import { ingangen as deelbeeld } from './deelbeeld.ts';
import { ingangen as kaart } from './kaart.ts';
import { ingangen as eigen } from './eigen.ts';

export type { Antwoord } from './gedeeld.ts';
export { lijstUrl, publicatie, zetGeheugen, zetTeller, zetVraagteller } from './gedeeld.ts';

const INGANGEN: Record<string, Ingang> = { ...lijsten, ...factcheck, ...verkennen, ...zoeken, ...deelbeeld, ...kaart, ...eigen };

// E\u00e9n verzoek: het pad zonder vraag, de vraag apart, en bij een POST het bericht (een formulier, hoogstens 8 KB).
export async function antwoord(db: Db, pad_: string, vraag = new URLSearchParams(),
                               { methode = 'GET', bericht = null }: { methode?: string; bericht?: string | null } = {}):
  Promise<Antwoord> {
  const delen = pad_.split('/');
  // een bezoek, gemeld door de site (#34.2ba): soort pagina, taal en of het een robot was; alleen opgeteld
  if (pad_ === '/api/tel') {
    if (methode !== 'POST') return { status: 405, tekst: 'Method Not Allowed' };
    if (new TextEncoder().encode(bericht ?? '').length > MAX_BERICHT) return { status: 400, tekst: 'Bad request' };
    const velden = leesBericht(bericht ?? '');
    const veld = (naam: string) => velden.get(naam)?.[0] ?? '';
    if (!SOORTEN.has(veld('soort')) || !TALEN.includes(veld('taal'))) return { status: 400, tekst: 'Bad request' };
    tel(veld('robot') === '1' ? 'robot' : veld('soort'), veld('taal'));
    return { status: 204 };
  }
  if (delen[0] !== '' || delen[1] !== 'api' || !TALEN.includes(delen[2]) || !Object.hasOwn(INGANGEN, delen[3])) return NIET_GEVONDEN;
  const ingang = INGANGEN[delen[3]];
  if (!(ingang.delen ?? [0]).includes(delen.length - 4) || delen.slice(4).some((d) => d === '')) return NIET_GEVONDEN;
  if (methode !== (ingang.methode ?? 'GET')) return { status: 405, tekst: 'Method Not Allowed' };
  let velden: Map<string, string[]> | null = null;
  if (methode === 'POST') {
    if (new TextEncoder().encode(bericht ?? '').length > MAX_BERICHT) return { status: 413, tekst: 'Too large' };
    velden = leesBericht(bericht ?? '');
  }
  const pub = publicatie(db);
  await pub.meta();
  try {
    const a = await ingang.f(pub, delen[2], delen.slice(4), vraag, velden);
    // een weggelaten naam (#34.2bw) nooit als merkteken naar buiten (`app.Weggelaten`)
    return a.body === undefined ? a : { ...a, body: merkDiep(a.body, gemerkt(delen[2])) };
  } catch (fout) {
    if (fout instanceof Fout404) return NIET_GEVONDEN;
    throw fout;
  }
}
