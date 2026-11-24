// Hoe ver de site open staat voor zoekmachines (PLAN #34.2bt, SPECS E9.S8 AC3, DESIGNSYSTEEM §6). `FACTIZ_VINDBAAR`: 0 (of
// niets) dicht, 1 de kern (B73 punt 5: meer dan één redactie, Ook gecheckt door of in een dossier), 2 elke factcheck één
// keer, 3 alles wat vindbaar is. In de Worker staat het in `vars` van wrangler.jsonc; aanzetten,
// en de tweede stap, is elk een eigen ja van de PO. Zonder imports: robots.txt en de middleware lezen het ook buiten Vite.

export function stand() {
  const s = process.env.FACTIZ_VINDBAAR;
  return ['1', '2', '3'].includes(s) ? Number(s) : 0;
}

// De talen waarin een factcheck naar zoekmachines gaat. `vindbaar` is wat het platform zegt (`talen`, `x_default`, `kern`):
// elke taal met eigen tekst. In stand 2 één keer: de taal van de bewering, of, als dat geen sitetaal is, waar `x_default`
// heen wijst (het Engels, anders de eerste vertaling); in stand 1 zo, alleen voor de kern, anders nergens; in stand 0 de kop
// zoals hij in stand 3 wordt, met noindex.
// Een afgeschermde factcheck (maatregel 2, PLAN #34.2bw: een privépersoon bij een misdaad, ziekte, dood of seksualiteit, of
// nog niet gelezen) gaat in geen open stand naar een zoekmachine; lezen kan iedereen.
export function aanbodFactcheck(taalBewering, vindbaar, sitetalen, st = stand()) {
  if (st !== 0 && vindbaar.afgeschermd) return [];
  if (st === 0 || st === 3) return vindbaar.talen;
  if (st === 1 && !vindbaar.kern) return [];
  return sitetalen.includes(taalBewering) ? [taalBewering] : [vindbaar.x_default];
}

// Een pagina per naam (`/names/Q…/`) blijft buiten zoekmachines tot een jurist haar bekeek (PLAN #34.2bw, SPECS E9.S8 AC9):
// een automatische lijst van alles wat over iemand gezegd is, is het zwakste punt van de journalistieke uitzondering (art.
// 43 UAVG). `noindex` en niet in de sitemap; robots.txt laat haar open, anders ziet een crawler de noindex niet. Na een
// akkoord van de jurist en de PO: true.
export const NAAMPAGINAS_VINDBAAR = false;
