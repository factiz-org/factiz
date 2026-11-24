// De ring van Verkennen (PLAN #34.2ah): een stuk van een ring als SVG-pad, van hoek `van` tot `tot` (in radialen, 0 is
// rechts, met de klok mee), tussen straal `binnen` en `buiten` rond (midden, midden). Op de server gerekend: geen script
// en geen bibliotheek in de browser (B75).
const punt = (midden, straal, hoek) => [midden + straal * Math.cos(hoek), midden + straal * Math.sin(hoek)]
  .map((x) => Math.round(x * 100) / 100).join(' ');

export function boog(midden, binnen, buiten, van, tot) {
  if (!(tot > van)) return '';
  // een stuk van de hele ring tekent als twee halve bogen: één boog van 360 graden tekent SVG niet
  if (tot - van >= 2 * Math.PI - 1e-6) {
    const half = van + Math.PI;
    return `${boog(midden, binnen, buiten, van, half)} ${boog(midden, binnen, buiten, half, van + 2 * Math.PI - 1e-6)}`;
  }
  const groot = tot - van > Math.PI ? 1 : 0;
  return `M${punt(midden, buiten, van)} A${buiten} ${buiten} 0 ${groot} 1 ${punt(midden, buiten, tot)} `
    + `L${punt(midden, binnen, tot)} A${binnen} ${binnen} 0 ${groot} 0 ${punt(midden, binnen, van)} Z`;
}
