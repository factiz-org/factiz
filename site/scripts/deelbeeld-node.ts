// De middelen van het deelplaatje in Node (B80, PLAN #34.2bo stap 5): de voorraad van `node scripts/deelbeeld-voorraad.ts`
// van schijf (standaard `data/deelbeeld/`, anders `FACTIZ_DEELBEELD`) en de wasm uit `node_modules`. Eén import zet ze:
//   import './deelbeeld-node.ts';
// In een Worker doet een eigen module hetzelfde met zijn bestanden en zijn bundel.
import { readFile } from 'node:fs/promises';
import { createRequire } from 'node:module';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { type Middelen, zetMiddelen } from '../src/platform/deelbeeld.ts';
import { TEKEN_WASM } from '../src/platform/deelbeeld-hb.ts';

const VOORRAAD = process.env.FACTIZ_DEELBEELD ?? join(dirname(fileURLToPath(import.meta.url)), '..', '..', 'data', 'deelbeeld');
const vind = createRequire(import.meta.url).resolve;
const WASM = { harfbuzz: vind('harfbuzzjs/dist/harfbuzz.wasm'), resvg: vind('@resvg/resvg-wasm/index_bg.wasm') };

export const middelen: Middelen = {
  lees: async (pad) => new Uint8Array(await readFile(join(VOORRAAD, pad))),
  wasm: async (naam) => (naam === 'teken' ? TEKEN_WASM : new Uint8Array(await readFile(WASM[naam]))),
};
zetMiddelen(middelen);
