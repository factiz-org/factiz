// Wat altijd in het geheugen van een uitgave moet (PLAN #34.2bo stap 3c): dit leest de Worker anders in D1 met de hele
// uitgave over het netwerk. Eén lijst voor `geheugen.ts`, dat het geheugen maakt, en `worker-voorraad.mjs`, dat een geheugen
// zonder deze stukken weigert; twee kopieën liepen uit elkaar bij #37.16. De woordenlijst staat sinds #37.16 als tabel
// `woord` in de uitgave, niet meer hier.
export const NODIG = ['zoeken:hoofdletters', 'zoeken:adresafdrukken', 'kolommen:kern', 'themas'];
