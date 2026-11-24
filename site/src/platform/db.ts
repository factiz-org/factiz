// De database onder het platform (B80, PLAN #34.2bo stap 3): de vorm van D1, zodat dezelfde code in de Worker op D1 draait
// en in Node op een SQLite-bestand (`site/scripts/platform-node.ts`). Alleen lezen.

export type Waarde = string | number | null | ArrayBuffer | number[];
export type Rij = Record<string, Waarde>;

export interface Opdracht {
  bind(...waarden: Waarde[]): Opdracht;
  all<T = Rij>(): Promise<{ results: T[] }>;
  first<T = Rij>(): Promise<T | null>;
}

export interface Db {
  prepare(sql: string): Opdracht;
}

export async function rijen<T = Rij>(db: Db, sql: string, ...waarden: Waarde[]): Promise<T[]> {
  const opdracht = waarden.length ? db.prepare(sql).bind(...waarden) : db.prepare(sql);
  return (await opdracht.all<T>()).results;
}

export async function eerste<T = Rij>(db: Db, sql: string, ...waarden: Waarde[]): Promise<T | null> {
  const opdracht = waarden.length ? db.prepare(sql).bind(...waarden) : db.prepare(sql);
  return opdracht.first<T>();
}
