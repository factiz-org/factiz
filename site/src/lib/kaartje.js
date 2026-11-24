// Het kaartje op de contextkaart *Waar speelt dit?* (PLAN #34.2an, SPECS E9.S21): een uitsnede van dezelfde wereldkaart
// als Verkennen (`site/src/kaart/wereld.json`), rond één land, met de buren erbij. Op de server gerekend, geen script in de
// browser (B75). Een land dat op deze schaal geen vorm heeft, geeft `null`: de kaart toont dan alleen de zin.
import wereld from '../kaart/wereld.json';

const VERHOUDING = 1.6;   // breedte gedeeld door hoogte van de uitsnede
const MINSTE = 90;        // punten: een klein land krijgt zijn buren erbij
const RUIMTE = 2.2;       // de uitsnede is zoveel keer het land
const KLEIN = 9;          // punten: een land smaller en lager dan dit krijgt een ring, anders zie je het niet

// per land de rechthoek om zijn vorm, één keer gerekend
const randen = Object.fromEntries(Object.entries(wereld.landen).map(([code, d]) => {
  const getallen = d.match(/-?\d+(?:\.\d+)?/g).map(Number);
  let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
  for (let i = 0; i + 1 < getallen.length; i += 2) {
    const [x, y] = [getallen[i], getallen[i + 1]];
    x0 = Math.min(x0, x); x1 = Math.max(x1, x); y0 = Math.min(y0, y); y1 = Math.max(y1, y);
  }
  return [code, [x0, y0, x1, y1]];
}));

const rond = (x) => Math.round(x * 10) / 10;

export function kaartje(code) {
  const rand = randen[code];
  if (!rand) return null;
  const [x0, y0, x1, y1] = rand;
  const mx = (x0 + x1) / 2, my = (y0 + y1) / 2;
  let w = Math.max(MINSTE, (x1 - x0) * RUIMTE, (y1 - y0) * RUIMTE * VERHOUDING);
  w = Math.min(w, wereld.breed);
  let h = Math.min(w / VERHOUDING, wereld.hoog);
  w = h * VERHOUDING;
  const vx = Math.min(Math.max(mx - w / 2, 0), wereld.breed - w);
  const vy = Math.min(Math.max(my - h / 2, 0), wereld.hoog - h);
  const paden = Object.entries(wereld.landen)
    .filter(([c]) => { const [a, b, cc, dd] = randen[c]; return cc >= vx && a <= vx + w && dd >= vy && b <= vy + h; })
    .map(([c, d]) => ({ code: c, d, aan: c === code }));
  paden.sort((a, b) => a.aan - b.aan);          // het land zelf als laatste, bovenop zijn buren
  const klein = x1 - x0 < KLEIN && y1 - y0 < KLEIN;
  return {
    viewBox: `${rond(vx)} ${rond(vy)} ${rond(w)} ${rond(h)}`,
    paden,
    ring: klein ? { cx: rond(mx), cy: rond(my), r: rond(Math.max(x1 - x0, y1 - y0) / 2 + w / 40) } : null,
  };
}
