// De gegevens van de site in Node (de toetsen, de eigen computer; B80, PLAN #34.2bo stap 7): de uitgave als SQLite-bestand,
// gelezen door dezelfde TypeScript-laag als in de Worker. `FACTIZ_PUBLICATIE` wijst het bestand aan; anders de nieuwste in
// data/publicatie/. Tellen alleen met `FACTIZ_TELLINGEN`, in dezelfde tabel als factiz_site/tellen.py (B78).
import { DatabaseSync } from 'node:sqlite';
import { existsSync, readdirSync } from 'node:fs';
import { readFile } from 'node:fs/promises';
import { createRequire } from 'node:module';
import { join, resolve } from 'node:path';
import { openDb } from '../../scripts/platform-node.ts';
import { zetTeller, zetVraagteller } from '../platform/api.ts';
import { ERBIJ as VRAAG_ERBIJ, OPRUIMEN, SCHEMA as VRAAG_SCHEMA, opruimdag } from './zoekvragen.js';
import { zetMiddelen } from '../platform/deelbeeld.ts';
import { TEKEN_WASM } from '../platform/deelbeeld-hb.ts';

const SCHEMA = 'CREATE TABLE IF NOT EXISTS telling (dag TEXT NOT NULL, wat TEXT NOT NULL, taal TEXT NOT NULL, '
  + 'n INTEGER NOT NULL, PRIMARY KEY (dag, wat, taal)) WITHOUT ROWID';
const ERBIJ = 'INSERT INTO telling (dag, wat, taal, n) VALUES (?, ?, ?, 1) ON CONFLICT (dag, wat, taal) DO UPDATE SET n = n + 1';

// Een map onder de werkmap of die erboven (de site draait uit `site/`, de toetsen uit de hoofdmap).
function zoekMap(...delen) {
  for (const wortel of [process.cwd(), resolve(process.cwd(), '..')]) {
    const map = join(wortel, ...delen);
    if (existsSync(map)) return map;
  }
  return null;
}

// De lettertypen en beelden van het deelplaatje (`node scripts/deelbeeld-voorraad.ts`) en de wasm uit node_modules.
function deelbeeldMiddelen() {
  const voorraad = process.env.FACTIZ_DEELBEELD || zoekMap('data', 'deelbeeld');
  const vind = createRequire(import.meta.url).resolve;
  const wasm = { harfbuzz: () => vind('harfbuzzjs/dist/harfbuzz.wasm'), resvg: () => vind('@resvg/resvg-wasm/index_bg.wasm') };
  zetMiddelen({
    lees: async (pad) => new Uint8Array(await readFile(join(voorraad ?? 'data/deelbeeld', pad))),
    wasm: async (naam) => (naam === 'teken' ? TEKEN_WASM : new Uint8Array(await readFile(wasm[naam]()))),
  });
}

function nieuwste() {
  for (const wortel of [process.cwd(), resolve(process.cwd(), '..')]) {
    const map = join(wortel, 'data', 'publicatie');
    if (!existsSync(map)) continue;
    const datums = readdirSync(map).filter((d) => existsSync(join(map, d, 'publicatie.db'))).sort();
    if (datums.length) return join(map, datums[datums.length - 1], 'publicatie.db');
  }
  throw new Error('geen publicatiedatabase: zet FACTIZ_PUBLICATIE of bouw er een met python -m doublecheck.publiceren bouwen');
}

let db = null;

// In Node mag werk tussen verzoeken gedeeld worden; alleen de Worker heeft een eigen context per verzoek nodig (#34.2bq).
export const perVerzoek = (fn) => fn();

export function gegevens() {
  if (!db) {
    db = openDb(process.env.FACTIZ_PUBLICATIE || nieuwste());
    deelbeeldMiddelen();
    if (process.env.FACTIZ_TELLINGEN) {
      const t = new DatabaseSync(process.env.FACTIZ_TELLINGEN);
      t.exec(SCHEMA);
      const erbij = t.prepare(ERBIJ);
      zetTeller((dag, wat, taal) => { try { erbij.run(dag, wat, taal); } catch { /* een teller breekt nooit een pagina */ } });
      // wat mensen zoeken (B94): opgeteld per dag, en één keer per dag opruimen wat zeldzaam bleef
      t.exec(VRAAG_SCHEMA);
      const vraagErbij = t.prepare(VRAAG_ERBIJ);
      let opgeruimd = null;
      zetVraagteller((dag, taal, vraag) => {
        try {
          if (opgeruimd !== dag) {
            for (const sql of OPRUIMEN) t.prepare(sql).run(opruimdag(dag));
            opgeruimd = dag;
          }
          vraagErbij.run(dag, taal, vraag);
        } catch { /* een teller breekt nooit een pagina */ }
      });
    }
  }
  return db;
}

// In Node geen paginacache (`paginacache.js`): elke pagina wordt gemaakt.
export const paginacache = () => null;
