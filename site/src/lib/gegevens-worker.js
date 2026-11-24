// De gegevens van de site in de Worker (B80, PLAN #34.2bo stap 7): de uitgave in D1 (`DB`), gelezen door dezelfde
// TypeScript-laag als in Node. Het vooraf berekende geheugen (`/_geheugen/`) en de lettertypen en beelden van het
// deelplaatje (`/_deelbeeld/`) staan bij de statische bestanden van deze bouw (`scripts/worker-voorraad.mjs`) en worden
// alleen hier gelezen. Tellen alleen met een eigen D1-database `TELLINGEN` (dezelfde tabel als factiz_site/tellen.py, B78),
// na het antwoord, zodat geen bezoeker op de teller wacht.
import { AsyncLocalStorage } from 'node:async_hooks';
import { env, waitUntil } from 'cloudflare:workers';
import hbWasm from 'harfbuzzjs/dist/harfbuzz.wasm';
import resvgWasm from '@resvg/resvg-wasm/index_bg.wasm';
import tekenWasm from '../platform/teken.wasm';
import { zetGeheugen, zetTeller, zetVraagteller } from '../platform/api.ts';
import { ERBIJ as VRAAG_ERBIJ, OPRUIMEN, SCHEMA as VRAAG_SCHEMA, opruimdag } from './zoekvragen.js';
import { zetMiddelen } from '../platform/deelbeeld.ts';
import { Voorraad, zetVerzoek } from '../platform/verzoek.ts';
import { gebundeld } from './bundel.js';

const ERBIJ = 'INSERT INTO telling (dag, wat, taal, n) VALUES (?, ?, ?, 1) ON CONFLICT (dag, wat, taal) DO UPDATE SET n = n + 1';
const BASIS = 'https://factiz.invalid';
let klaar = false;

// Elk verzoek een eigen context (PLAN #34.2bq): Workers breekt een verzoek af dat wacht op werk van een ander verzoek. De
// platformlaag vraagt via `zetVerzoek` wie het verzoek is, en deelt alleen wat af is (`Voorraad`); de bundeling van vragen
// aan D1 hieronder houdt per verzoek een eigen rij. Buiten een verzoek telt elke aanroep als een eigen verzoek.
const verzoek = new AsyncLocalStorage();
zetVerzoek(() => verzoek.getStore() ?? Symbol('buiten een verzoek'));

export function perVerzoek(fn) {
  return verzoek.run({ wachtrij: [] }, fn);
}

// Een eigen bestand van de bouw, via de binding (een bezoeker komt er niet bij, `run_worker_first` in wrangler.jsonc).
async function bestand(pad) {
  const antwoord = await env.ASSETS.fetch(new URL(pad, BASIS));
  return antwoord.ok ? antwoord : null;
}

let db = null;

// De cache van Cloudflare voor de pagina's (`paginacache.js`), met de versie van deze uitrol in de sleutel; zonder versie
// geen cache, want dan zou een nieuwe uitrol oude pagina's kunnen tonen. Op workers.dev doet de cache niets.
export function paginacache() {
  const versie = env.VERSIE?.id;
  return versie ? { cache: caches.default, versie, waitUntil } : null;
}

export function gegevens() {
  if (!klaar) {
    klaar = true;
    const index = new Voorraad();
    zetGeheugen(async (naam) => {
      const pad = (await index.haal('index', () => bestand('/_geheugen/index.json').then((a) => (a ? a.json() : { stukken: [] }))
        .then((i) => new Map(i.stukken.map((s) => [s.naam, s.bestand]))))).get(naam);
      const a = pad ? await bestand(`/_geheugen/${pad}`) : null;
      return a ? a.text() : null;
    });
    zetMiddelen({
      lees: async (pad) => {
        const a = await bestand(`/_deelbeeld/${pad}`);
        if (!a) throw new Error(`deelbeeld: ${pad}`);
        return new Uint8Array(await a.arrayBuffer());
      },
      wasm: async (naam) => ({ harfbuzz: hbWasm, resvg: resvgWasm, teken: tekenWasm })[naam],
    });
    if (env.TELLINGEN) {
      zetTeller((dag, wat, taal) => waitUntil(env.TELLINGEN.prepare(ERBIJ).bind(dag, wat, taal).run().catch(() => {})));
      // wat mensen zoeken (B94): na het antwoord, opgeteld per dag; de eerste keer op een dag maakt deze Worker de tabel
      // als die er nog niet is en ruimt hij op wat zeldzaam bleef, in dezelfde batch
      let opgeruimd = null;
      zetVraagteller((dag, taal, vraag) => {
        const d = env.TELLINGEN;
        const eerst = opgeruimd === dag ? [] : [d.prepare(VRAAG_SCHEMA), ...OPRUIMEN.map((sql) => d.prepare(sql).bind(opruimdag(dag)))];
        opgeruimd = dag;
        waitUntil(d.batch([...eerst, d.prepare(VRAAG_ERBIJ).bind(dag, taal, vraag)]).catch(() => { opgeruimd = null; }));
      });
    }
  }
  return (db ??= gebundeld(env.DB, () => verzoek.getStore()));
}
