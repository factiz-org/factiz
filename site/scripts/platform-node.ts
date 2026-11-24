// Een SQLite-bestand in de vorm van D1 (PLAN #34.2bo stap 3), voor de toets en de vergelijking met Python in Node.
// Alleen lezen. In de Worker is het D1 zelf; daar komt dit bestand niet in.
import { DatabaseSync } from 'node:sqlite';
import type { Db, Opdracht, Waarde } from '../src/platform/db.ts';

// D1 geeft een BLOB als lijst getallen terug; hier net zo, zodat de code op beide hetzelfde ziet.
function zoalsD1(rij: Record<string, unknown>): Record<string, Waarde> {
  const uit: Record<string, Waarde> = {};
  for (const [k, v] of Object.entries(rij)) {
    uit[k] = v instanceof Uint8Array ? Array.from(v) : typeof v === 'bigint' ? Number(v) : (v as Waarde);
  }
  return uit;
}

export function openDb(pad: string): Db {
  const db = new DatabaseSync(pad, { readOnly: true });
  return {
    prepare(sql: string): Opdracht {
      const maak = (waarden: Waarde[]): Opdracht => ({
        bind: (...meer: Waarde[]) => maak(meer),
        async all<T>() {
          return { results: db.prepare(sql).all(...(waarden as never[])).map(zoalsD1) as T[] };
        },
        async first<T>() {
          const rij = db.prepare(sql).get(...(waarden as never[]));
          return (rij ? zoalsD1(rij as Record<string, unknown>) : null) as T | null;
        },
      });
      return maak([]);
    },
  };
}
