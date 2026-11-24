// Laat de TypeScript-kant van het platform antwoorden op een lijst verzoeken (PLAN #34.2bo):
//   node scripts/platform-vraag.ts <publicatie.db>  <  ["/api/en/bronnen", {"pad": "/api/en/zoek", "methode": "POST", "bericht": "q=vaccin"}, …]
// Schrijft per verzoek {status, body} als JSON (bytes als base64 in `bytes`), in dezelfde volgorde. `factiz_site.gelijk`
// en `tests/test_platform_ts*.py` leggen dat naast Python.
import { antwoord } from '../src/platform/api.ts';
import { openDb } from './platform-node.ts';
import { zetGeheugen } from '../src/platform/api.ts';
import { geheugenUitMap } from './geheugen-node.ts';
import './deelbeeld-node.ts';      // de lettertypen en wasm van het deelplaatje (stap 5)

const [, , bestand] = process.argv;
if (!bestand) {
  console.error('gebruik: node scripts/platform-vraag.ts <publicatie.db>');
  process.exit(2);
}
let invoer = '';
for await (const stuk of process.stdin) invoer += stuk;
// met FACTIZ_GEHEUGEN het vooraf berekende geheugen uit die map, zoals de Worker het leest (stap 3c)
if (process.env.FACTIZ_GEHEUGEN) zetGeheugen(geheugenUitMap(process.env.FACTIZ_GEHEUGEN));
const db = openDb(bestand);
const uit = [];
type Verzoek = string | { pad: string; methode?: string; bericht?: string };
for (const verzoek of JSON.parse(invoer) as Verzoek[]) {
  const { pad, methode = 'GET', bericht = null } = typeof verzoek === 'string' ? { pad: verzoek } : verzoek;
  const url = new URL(pad, 'http://platform');
  try {
    const a = await antwoord(db, decodeURIComponent(url.pathname), url.searchParams, { methode, bericht });
    uit.push(a.bytes ? { ...a, bytes: Buffer.from(a.bytes).toString('base64') } : a);
  } catch (fout) {
    uit.push({ status: 500, fout: String((fout as Error)?.stack ?? fout) });
  }
}
process.stdout.write(JSON.stringify(uit));
