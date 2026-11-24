// Welk stuk van het geheugen een antwoord verandert (PLAN #34.2bo stap 3c): per stuk alleen dat stuk uit het geheugen, en
// het antwoord naast dat zonder geheugen.   node scripts/geheugen-zoek.ts <publicatie.db> <geheugenmap> <pad> [bericht]
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { antwoord, zetGeheugen } from '../src/platform/api.ts';
import { openDb } from './platform-node.ts';

const [, , bestand, map, pad, bericht] = process.argv;
const index = JSON.parse(readFileSync(join(map, 'index.json'), 'utf8')) as { stukken: { naam: string; bestand: string }[] };
async function vraag(alleen: string | null) {
  zetGeheugen(alleen === null ? null : async (naam) => {
    const s = index.stukken.find((x) => x.naam === naam && naam === alleen);
    return s ? readFileSync(join(map, s.bestand), 'utf8') : null;
  });
  const url = new URL(pad, 'http://platform');
  const a = await antwoord(openDb(bestand), url.pathname, url.searchParams, bericht ? { methode: 'POST', bericht } : {});
  return JSON.stringify(a.body);
}
const zonder = await vraag(null);
for (const s of index.stukken) {
  if (await vraag(s.naam) !== zonder) console.log('anders met:', s.naam);
}
console.log('klaar');
