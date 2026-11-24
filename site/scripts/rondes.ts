// Hoe vaak het platform voor één verzoek heen en terug gaat naar de database, zoals de Worker (na B93: de woordenlijst in
// de database mocht een zoekvraag of suggestie niet vaker laten heen en weer gaan dan ervoor):
//   node scripts/rondes.ts <publicatie.db> <geheugenmap> '{"pad": "/api/en/zoek", "methode": "POST", "bericht": "q=vaccin"}'
// Met dezelfde bundeling als de Worker (`src/lib/bundel.js`): wat tegelijk gevraagd wordt, gaat samen, en elke batch of losse
// vraag is één keer heen en terug. Het verzoek gaat twee keer: `koud` zoals een Worker die net begint (alleen het vooraf
// berekende geheugen), `warm` zoals een Worker die het al eens deed. Schrijft {"koud": n, "warm": n, "rijenKoud": n,
// "rijenWarm": n}: keer heen en weer, en hoeveel rijen er uit de database terugkwamen.
import { AsyncLocalStorage } from 'node:async_hooks';
import { antwoord, zetGeheugen } from '../src/platform/api.ts';
import type { Db, Opdracht } from '../src/platform/db.ts';
import { zetVerzoek } from '../src/platform/verzoek.ts';
import { gebundeld } from '../src/lib/bundel.js';
import { geheugenUitMap } from './geheugen-node.ts';
import { openDb } from './platform-node.ts';

const [, , bestand, geheugen, verzoekTekst] = process.argv;
if (!bestand || !geheugen || !verzoekTekst) {
  console.error('gebruik: node scripts/rondes.ts <publicatie.db> <geheugenmap> <verzoek als JSON>');
  process.exit(2);
}
zetGeheugen(geheugenUitMap(geheugen));
let rondes = 0;
let rijenTerug = 0;           // hoeveel rijen er uit de database terugkwamen: wat over het netwerk moet
// met RONDES_TOON=1 per keer heen en weer de vragen die meegingen, op stderr (om te zien wat na elkaar gaat)
const toon = (sqls: string[]) => {
  if (process.env.RONDES_TOON) console.error(`ronde ${rondes}: ${sqls.map((q) => q.replace(/\s+/g, ' ').slice(0, 110)).join(' | ')}`);
};
const basis = openDb(bestand);
type Geteld = Opdracht & { kaal: Opdracht; sql: string };
// de tijd van een vraag in SQLite hier (zonder het netwerk van D1): wat hier zwaar is, is daar zwaarder
const getimed = async <T>(sql: string, f: () => Promise<T>): Promise<[T, string]> => {
  const t = performance.now();
  const uit = await f();
  const r = uit as { results?: unknown[] } | null;
  rijenTerug += r && Array.isArray(r.results) ? r.results.length : r ? 1 : 0;
  return [uit, `${(performance.now() - t).toFixed(1)} ms ${sql}`];
};
const tel = (o: Opdracht, sql: string): Geteld => ({
  kaal: o,
  sql,
  bind: (...w) => tel(o.bind(...w), sql),
  all: async <T>() => { rondes++; const [r, t] = await getimed(sql, () => o.all<T>()); toon([t]); return r; },
  first: async <T>() => { rondes++; const [r, t] = await getimed(sql, () => o.first<T>()); toon([t]); return r; },
});
const d1 = {
  prepare: (sql: string) => tel(basis.prepare(sql), sql),
  batch: async (opdrachten: Geteld[]) => {
    rondes++;
    const uit = [];
    const tijden = [];
    for (const o of opdrachten) {
      const [r, t] = await getimed(o.sql, () => o.kaal.all());
      uit.push(r);
      tijden.push(t);
    }
    toon(tijden);
    return uit;
  },
};
const verzoek = new AsyncLocalStorage<{ wachtrij: unknown[] }>();
zetVerzoek(() => verzoek.getStore() ?? Symbol('buiten een verzoek'));
const db = gebundeld(d1, () => verzoek.getStore()) as Db;
const { pad, methode = 'GET', bericht = null } = JSON.parse(verzoekTekst) as { pad: string; methode?: string; bericht?: string };
const url = new URL(pad, 'http://platform');
const keer = async () => {
  rondes = 0;
  rijenTerug = 0;
  const a = await verzoek.run({ wachtrij: [] }, () => antwoord(db, decodeURIComponent(url.pathname), url.searchParams,
    { methode, bericht }));
  if (a.status !== 200) throw new Error(`${pad}: status ${a.status}`);
  return [rondes, rijenTerug];
};
const [koud, rijenKoud] = await keer();
const [warm, rijenWarm] = await keer();
process.stdout.write(JSON.stringify({ koud, warm, rijenKoud, rijenWarm }));
