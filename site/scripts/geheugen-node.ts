// Het vooraf berekende geheugen uit een map lezen, in Node (PLAN #34.2bo stap 3c): voor de vergelijking met Python en de
// toetsen. In de Worker leest de site het uit haar statische bestanden.
import { existsSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import type { Geheugen } from '../src/platform/publicatie.ts';

export function geheugenUitMap(map: string): Geheugen {
  const index = JSON.parse(readFileSync(join(map, 'index.json'), 'utf8')) as { stukken: { naam: string; bestand: string }[] };
  const bestanden = new Map(index.stukken.map((s) => [s.naam, join(map, s.bestand)]));
  return async (naam) => {
    const pad = bestanden.get(naam);
    return pad && existsSync(pad) ? readFileSync(pad, 'utf8') : null;
  };
}
