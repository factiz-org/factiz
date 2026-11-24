// Meet het deelplaatje in Node (B80, PLAN #34.2bo stap 5): per verzoek de tijd en wat het laadt, zoals een Worker het zou
// laden.  node scripts/deelbeeld-meting.ts <publicatie.db>  <  ["/api/en/deelbeeld/…", …]
// Eerst de wasm en de voorraad (`bereidVoor`), dan de verzoeken op volgorde; een lettertype dat een eerder verzoek al
// laadde, telt daarna niet meer, zoals in een Worker die blijft leven. Schrijft JSON: de tijd van het begin en per verzoek
// de status, de milliseconden, de bytes van het plaatje en de gelezen bestanden met hun grootte.
import { antwoord } from '../src/platform/api.ts';
import { bereidVoor, zetMiddelen } from '../src/platform/deelbeeld.ts';
import { middelen } from './deelbeeld-node.ts';
import { openDb } from './platform-node.ts';

const [, , bestand] = process.argv;
let invoer = '';
for await (const stuk of process.stdin) invoer += stuk;
let gelezen: [string, number][] = [];
zetMiddelen({
  lees: async (pad) => { const b = await middelen.lees(pad); gelezen.push([pad, b.byteLength]); return b; },
  wasm: async (naam) => { const w = await middelen.wasm(naam); gelezen.push([`wasm/${naam}`, (w as Uint8Array).byteLength]); return w; },
});
const db = openDb(bestand);
let t = performance.now();
await bereidVoor();
const begin = { ms: Math.round(performance.now() - t), gelezen };
const uit = [];
for (const pad of JSON.parse(invoer) as string[]) {
  gelezen = [];
  t = performance.now();
  const a = await antwoord(db, pad);
  uit.push({ pad, status: a.status, ms: Math.round((performance.now() - t) * 10) / 10, bytes: a.bytes?.byteLength ?? 0, gelezen });
}
process.stdout.write(JSON.stringify({ begin, verzoeken: uit }));
