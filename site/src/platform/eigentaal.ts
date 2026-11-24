// Een eigen check zoals de site haar in een taal toont (`app.eigen_in`, PLAN #37.8, B85): zichzelf in haar eigen taal, met
// een geldige machinevertaling de vertaalde velden over het origineel heen (met `brontaal` en de maker), anders null.
// Zonder imports, zodat het archief, de factcheck en de lijst van eigen checks het allemaal kunnen gebruiken.

type Check = Record<string, unknown> & { taal: string; sleutel: string };
type Vertaling = { velden: Record<string, unknown>; maker: string; nagelezen?: boolean };

// de velden van een eigen check die een machinevertaling heeft (`app.EIGEN_TEKSTEN`)
const TEKSTEN = ['kop', 'oordeel_zin', 'bewering', 'kort', 'tekst', 'niet_weten', 'bereik'];

export function eigenIn<T extends Check>(c: T, taal: string): T | null {
  if (c.taal === taal) return c;
  const v = ((c.vertalingen ?? {}) as Record<string, Vertaling>)[taal];
  if (!v) return null;
  const f = v.velden;
  const uit: Record<string, unknown> = { ...c };
  for (const k of TEKSTEN) if (f[k]) uit[k] = f[k];
  uit.brontaal = c.taal;
  uit.vertaling_maker = v.maker;
  uit.vertaling_nagelezen = Boolean(v.nagelezen);
  if (Array.isArray(f.nog_uitzoeken)) uit.nog_uitzoeken = f.nog_uitzoeken;
  const tijdlijn = (c.tijdlijn ?? []) as Record<string, unknown>[];
  if (Array.isArray(f.tijdlijn)) uit.tijdlijn = tijdlijn.slice(0, f.tijdlijn.length).map((r, i) => ({ ...r, wat: (f.tijdlijn as string[])[i] }));
  const beelden = (c.beeld ?? []) as Record<string, unknown>[];
  if (beelden.length && Array.isArray(f.beeld_bijschrift) && Array.isArray(f.beeld_alt)) {
    const n = Math.min(beelden.length, f.beeld_bijschrift.length, f.beeld_alt.length);
    uit.beeld = beelden.slice(0, n).map((b, i) => ({ ...b, bijschrift: (f.beeld_bijschrift as string[])[i], alt: (f.beeld_alt as string[])[i] }));
  }
  const som = (c.rekensom ?? []) as Record<string, unknown>[];
  if (som.length && Array.isArray(f.rekensom)) {
    const rijen = f.rekensom as string[][];
    uit.rekensom = som.slice(0, rijen.length).map((r, i) => ({ ...r, geval: rijen[i][0], som: rijen[i][1], uitkomst: rijen[i][2] }));
  }
  return uit as T;
}
