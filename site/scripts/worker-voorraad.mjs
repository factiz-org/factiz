// Na `astro build` voor de Worker (PLAN #34.2bo stap 7): het geheugen van de release en de voorraad van het deelplaatje bij
// de statische bestanden, onder `/_geheugen/` en `/_deelbeeld/`. Alleen de Worker leest ze (`run_worker_first`).
//   node scripts/worker-voorraad.mjs [<release>]     (standaard de uitgave van de database in wrangler.jsonc)
import { appendFileSync, cpSync, existsSync, readFileSync, rmSync } from 'node:fs';
import { join } from 'node:path';
import { kopbestand } from '../src/lib/koppen.js';
import { NODIG } from './geheugen-nodig.mjs';

const WORTEL = join(import.meta.dirname, '..', '..');
const KLANT = join(import.meta.dirname, '..', 'dist-worker', 'client');
// het geheugen hoort bij dezelfde uitgave als de database van de Worker: anders zegt een pagina iets anders dan een andere.
// Dus niet het nieuwste op schijf: de routine kan intussen een volgende uitgave voorbereid hebben (2026-11-23)
const config = readFileSync(join(import.meta.dirname, '..', 'wrangler.jsonc'), 'utf8').replace(/^\s*\/\/.*$/gm, '');
const database = JSON.parse(config).d1_databases.find((d) => d.binding === 'DB')?.database_name ?? '';
const release = process.argv[2] ?? database.replace(/^factiz-/, '');
if (!existsSync(join(WORTEL, 'data', 'd1', release, 'geheugen', 'index.json'))) {
  throw new Error(`geen geheugen in data/d1/${release}/geheugen: eerst node scripts/geheugen.ts`);
}
if (database !== `factiz-${release}`) throw new Error(`het geheugen is van ${release}, de Worker leest ${database}`);
const deelbeeld = join(WORTEL, 'data', 'deelbeeld');
if (!existsSync(join(deelbeeld, 'voorraad.json'))) throw new Error('geen voorraad van het deelplaatje: eerst node scripts/deelbeeld-voorraad.ts');
// wat de Worker niet zelf kan rekenen, moet in het geheugen staan (`geheugen-nodig.mjs`)
const index = JSON.parse(readFileSync(join(WORTEL, 'data', 'd1', release, 'geheugen', 'index.json'), 'utf8'));
const ontbreekt = NODIG.filter((n) => !index.stukken.some((s) => s.naam === n));
if (ontbreekt.length) throw new Error(`het geheugen van ${release} mist ${ontbreekt.join(', ')}: opnieuw node scripts/geheugen.ts`);
for (const map of ['_geheugen', '_deelbeeld']) rmSync(join(KLANT, map), { recursive: true, force: true });
cpSync(join(WORTEL, 'data', 'd1', release, 'geheugen'), join(KLANT, '_geheugen'), { recursive: true });
cpSync(deelbeeld, join(KLANT, '_deelbeeld'), { recursive: true });
// de beveiligingskoppen ook op de statische bestanden, waar de Worker niet aan te pas komt; achter de regels die Astro
// in `_headers` zette (een bouw begint met een nieuw bestand)
appendFileSync(join(KLANT, '_headers'), `\n${kopbestand()}`);
console.log(`release ${release}: geheugen en deelplaatje bij de statische bestanden, en de koppen in _headers`);
