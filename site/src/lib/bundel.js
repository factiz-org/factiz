// Vragen die tegelijk gesteld worden (een factcheckpagina stelt er 12 in drie rondes) gaan samen in één batch naar D1: één
// keer heen en terug (~25 ms, stap 8) in plaats van één per vraag. Mislukt de batch (een zoekvraag die niet klopt, wat de
// code opvangt), dan gaat elke vraag apart, zodat alleen die ene faalt, zoals zonder batch. Alleen vragen van hetzelfde
// verzoek gaan samen (#34.2bq); buiten een verzoek gaat elke vraag apart. `rij()` geeft de rij van het lopende verzoek
// (`{ wachtrij: [] }`), of niets. Zonder imports van Cloudflare: de Worker gebruikt het (`gegevens-worker.js`), en de
// teller van de rondes (`scripts/rondes.ts`) meet er in Node mee wat de Worker doet.
export function gebundeld(db, rij) {
  const stuur = async (s) => {
    const nu = s.wachtrij;
    s.wachtrij = [];
    if (nu.length === 1) return nu[0].los();
    let uit;
    try {
      uit = await db.batch(nu.map((v) => v.opdracht));
    } catch {
      for (const v of nu) v.los();
      return;
    }
    nu.forEach((v, i) => v.klaar(uit[i]));
  };
  const vraag = (opdracht, eerste) => new Promise((ok, fout) => {
    const los = () => (eerste ? opdracht.first() : opdracht.all()).then(ok, fout);
    const s = rij();
    if (!s) return los();
    if (!s.wachtrij.length) setTimeout(() => stuur(s), 0);
    s.wachtrij.push({ opdracht, klaar: (r) => ok(eerste ? (r.results[0] ?? null) : r), los });
  });
  const maak = (o) => ({ bind: (...w) => maak(o.bind(...w)), all: () => vraag(o, false), first: () => vraag(o, true) });
  return { prepare: (sql) => maak(db.prepare(sql)) };
}
