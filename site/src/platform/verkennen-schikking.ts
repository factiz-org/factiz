// De schikking van het netwerk van namen (PLAN #34.2ai, SPECS E9.S18 AC4), gelijk aan `factiz_site/netwerk.py`: eerst
// krachten (ForceAtlas2, met hetzelfde zaad als numpy), dan cirkels en labels uit elkaar tot niets overlapt. Elke
// bewerking in dezelfde volgorde als numpy, want 500 stappen vergroten één bit verschil tot een andere plek.
import { ln1p, rond } from './verkennen-getal.ts';

export const BREED = 900.0;
export const HOOG = 560.0;
const LABEL_HOOG = 15.0;
const TUSSEN = 3.0;
const MARGE = 0.01;
const STAPPEN = 500;
const DUWKRACHT = 100.0;
const ZWAARTE = 0.03;
const DUWEN = 600;
const GROEI = 6;

// --- het zaad: numpy `default_rng(zaad)`, dus SeedSequence en PCG64 (XSL-RR), en `uniform` ---------------------------

const M64 = (1n << 64n) - 1n;
const M128 = (1n << 128n) - 1n;
const VERMENIGVULDIGER = (0x2360ed051fc65da4n << 64n) + 0x4385df649fccf645n;

// SeedSequence met één woord entropie (een zaad onder 2^32) en een pool van vier woorden; dan vier woorden van 64 bits.
function zaadwoorden(zaad: number): bigint[] {
  const hash = [0x43b0d7e5];
  const meng = (waarde: number): number => {
    let v = (waarde ^ hash[0]) >>> 0;
    hash[0] = Math.imul(hash[0], 0x931e8875) >>> 0;
    v = Math.imul(v, hash[0]) >>> 0;
    return (v ^ (v >>> 16)) >>> 0;
  };
  const mix = (x: number, y: number): number => {
    const r = (Math.imul(0xca01f9dd, x) - Math.imul(0x4973f715, y)) >>> 0;
    return (r ^ (r >>> 16)) >>> 0;
  };
  const entropie = [zaad >>> 0];
  const pool = [0, 0, 0, 0].map((_, i) => meng(i < entropie.length ? entropie[i] : 0));
  for (let bron = 0; bron < 4; bron++) {
    for (let doel = 0; doel < 4; doel++) if (bron !== doel) pool[doel] = mix(pool[doel], meng(pool[bron]));
  }
  let h = 0x8b51f9dd;
  const woorden: number[] = [];
  for (let i = 0; i < 8; i++) {
    let v = (pool[i % 4] ^ h) >>> 0;
    h = Math.imul(h, 0x58f38ded) >>> 0;
    v = Math.imul(v, h) >>> 0;
    woorden.push((v ^ (v >>> 16)) >>> 0);
  }
  return [0, 1, 2, 3].map((i) => BigInt(woorden[2 * i]) | (BigInt(woorden[2 * i + 1]) << 32n));
}

class Pcg64 {
  private toestand = 0n;
  private stap: bigint;

  constructor(zaad: number) {
    const [a, b, c, d] = zaadwoorden(zaad);
    this.stap = (((c << 64n) | d) << 1n | 1n) & M128;
    this.volgende();
    this.toestand = (this.toestand + ((a << 64n) | b)) & M128;
    this.volgende();
  }

  private volgende(): void {
    this.toestand = (this.toestand * VERMENIGVULDIGER + this.stap) & M128;
  }

  getal64(): bigint {
    this.volgende();
    const s = this.toestand;
    const x = ((s >> 64n) ^ s) & M64;
    const draai = s >> 122n;
    return ((x >> draai) | (x << ((64n - draai) & 63n))) & M64;
  }

  // `uniform(laag, hoog)`: laag + (hoog − laag) · (getal >> 11) · 2^-53
  uniform(laag: number, hoog: number): number {
    return laag + (hoog - laag) * (Number(this.getal64() >> 11n) * (1.0 / 9007199254740992.0));
  }
}

// --- de krachten ------------------------------------------------------------------------------------------------------

// `math.log1p` van macOS op een geheel getal (hoe vaak twee namen samen staan) wijkt tot 200.000 op deze plekken één
// bit af van de juiste afronding; gemeten tegen Python op deze Mac, elk geheel getal van 1 tot 1.000.000.
const LOG1P_MACOS: Record<number, number> = { 9169: 1, 19142: -1, 37280: -1, 76020: 1, 115989: 1, 134808: 1, 136836: 1,
  141613: 1, 147673: 1, 160602: -1, 164412: 1, 166306: -1, 177419: 1, 189713: -1 };

function buur(x: number, richting: number): number {
  const beeld = new Float64Array([x]);
  const bits = new BigUint64Array(beeld.buffer);
  bits[0] += richting > 0 ? 1n : -1n;          // x > 0: één stap omhoog of omlaag in de bits is één ulp
  return beeld[0];
}

function log1pGewicht(w: number): number {
  const y = ln1p(w);
  return Number.isInteger(w) && Object.hasOwn(LOG1P_MACOS, w) ? buur(y, LOG1P_MACOS[w]) : y;
}

function krachten(n: number, randen: [number, number, number][], zaad: number): Float64Array[] {
  const rng = new Pcg64(zaad);
  const xs = Array.from({ length: n }, () => rng.uniform(-1, 1));
  const ys = Array.from({ length: n }, () => rng.uniform(-1, 1));
  const px = Float64Array.from(xs, (v) => v * 100);
  const py = Float64Array.from(ys, (v) => v * 100);
  if (n === 1) return [px, py];
  const gewicht = new Float64Array(n * n);
  for (const [i, j, w] of randen) gewicht[i * n + j] = gewicht[j * n + i] = log1pGewicht(w);
  const massa = new Float64Array(n);
  const buren: number[][] = Array.from({ length: n }, () => []);
  for (let i = 0; i < n; i++) {
    let tel = 0;
    for (let j = 0; j < n; j++) {
      if (gewicht[i * n + j] > 0) tel++;
      if (gewicht[i * n + j] !== 0) buren[i].push(j);
    }
    massa[i] = tel + 1.0;
  }
  const afstand = new Float64Array(n * n);
  const logaf = new Float64Array(n * n);
  const vx = new Float64Array(n);
  const vy = new Float64Array(n);
  let warmte = 10.0;
  for (let stap = 0; stap < STAPPEN; stap++) {
    // d[i, j] = plek[i] − plek[j]; de afstand is symmetrisch, tot op de bit
    for (let i = 0; i < n; i++) {
      afstand[i * n + i] = Math.sqrt(0) + 1e-6;
      for (let j = i + 1; j < n; j++) {
        const dx = px[i] - px[j];
        const dy = py[i] - py[j];
        afstand[i * n + j] = afstand[j * n + i] = Math.sqrt(dx * dx + dy * dy) + 1e-6;
      }
    }
    for (let i = 0; i < n; i++) {
      for (const j of buren[i]) if (j > i) logaf[i * n + j] = logaf[j * n + i] = ln1p(afstand[i * n + j]);
    }
    for (let i = 0; i < n; i++) {
      // de som over j zoals numpy hem langs de tweede as neemt: gewoon van voor naar achter
      let duwX = 0, duwY = 0, trekX = 0, trekY = 0;
      const mi = DUWKRACHT * massa[i];
      for (let j = 0; j < n; j++) {
        const dx = px[i] - px[j];
        const dy = py[i] - py[j];
        const a = afstand[i * n + j];
        const f = mi * massa[j] / (a * a);
        duwX += f * dx;
        duwY += f * dy;
      }
      for (const j of buren[i]) {
        const dx = px[i] - px[j];
        const dy = py[i] - py[j];
        const a = afstand[i * n + j];
        const f = -(gewicht[i * n + j] * logaf[i * n + j] / a);
        trekX += f * dx;
        trekY += f * dy;
      }
      const z = ZWAARTE * massa[i];
      vx[i] = (duwX + trekX) - z * px[i];
      vy[i] = (duwY + trekY) - z * py[i];
    }
    for (let i = 0; i < n; i++) {
      const lengte = Math.sqrt(vx[i] * vx[i] + vy[i] * vy[i]) + 1e-9;
      const stapje = Math.min(lengte, warmte);
      px[i] += vx[i] / lengte * stapje;
      py[i] += vy[i] / lengte * stapje;
    }
    warmte = Math.max(warmte * 0.995, 0.3);
  }
  return [px, py];
}

// --- uit elkaar schuiven ----------------------------------------------------------------------------------------------

function past(ruw: Float64Array[], r: Float64Array, w: Float64Array, breed: number, hoog: number): Float64Array[] | null {
  const n = r.length;
  const half = r.map((ri, i) => Math.max(ri, w[i] / 2));
  const onder = r.map((ri, i) => ri + (w[i] > 0 ? LABEL_HOOG : 0.0));
  const [rx, ry] = ruw;
  const minMax = (a: Float64Array) => [a.reduce((m, v) => (v < m ? v : m)), a.reduce((m, v) => (v > m ? v : m))];
  const [laagX, hoogX] = minMax(rx);
  const [laagY, hoogY] = minMax(ry);
  const spreidX = hoogX - laagX > 1e-9 ? hoogX - laagX : 1.0;
  const spreidY = hoogY - laagY > 1e-9 ? hoogY - laagY : 1.0;
  const randX = half.reduce((m, v) => (v > m ? v : m)) + 0.5;
  const randY = Math.max(r.reduce((m, v) => (v > m ? v : m)), onder.reduce((m, v) => (v > m ? v : m))) + 0.5;
  const px = rx.map((v) => randX + (v - laagX) / spreidX * (breed - 2 * randX));
  const py = ry.map((v) => randY + (v - laagY) / spreidY * (hoog - 2 * randY));
  if (n === 1) {
    px[0] = breed / 2;
    py[0] = hoog / 2;
  }
  // Python `min(max(p, laag), hoog)`: bij gelijke waarden de eerste
  const klem = (p: number, laag: number, hoogst: number) => {
    const m = laag > p ? laag : p;
    return hoogst < m ? hoogst : m;
  };
  for (let ronde = 0; ronde < DUWEN; ronde++) {
    // de dozen zoals `_dozen`: onder is y + (r + 15)
    const x0 = px.map((v, i) => v - half[i]);
    const x1 = px.map((v, i) => v + half[i]);
    const y0 = py.map((v, i) => v - r[i]);
    const y1 = py.map((v, i) => v + onder[i]);
    const paren: [number, number][] = [];
    for (let i = 0; i < n; i++) {
      for (let j = i + 1; j < n; j++) {
        const overX = Math.min(x1[i], x1[j]) - Math.max(x0[i], x0[j]) + TUSSEN;
        const overY = Math.min(y1[i], y1[j]) - Math.max(y0[i], y0[j]) + TUSSEN;
        if (overX > MARGE && overY > MARGE) paren.push([i, j]);
      }
    }
    if (!paren.length) return [px, py];
    for (const [i, j] of paren) {
      // de dozen zoals `_paar`: onder is (y + r) + 15
      const doos = (k: number) => {
        const h = Math.max(r[k], w[k] / 2);
        return [px[k] - h, py[k] - r[k], px[k] + h, py[k] + r[k] + (w[k] > 0 ? LABEL_HOOG : 0.0)];
      };
      const [a0x, a0y, a1x, a1y] = doos(i);
      const [b0x, b0y, b1x, b1y] = doos(j);
      const ox = Math.min(a1x, b1x) - Math.max(a0x, b0x) + TUSSEN;
      const oy = Math.min(a1y, b1y) - Math.max(a0y, b0y) + TUSSEN;
      if (ox <= MARGE || oy <= MARGE) continue;
      const opX = ox <= oy;
      const p = opX ? px : py;
      const over = opX ? ox : oy;
      const kant = p[i] > p[j] || (p[i] === p[j] && i > j) ? 1.0 : -1.0;
      p[i] += kant * (over / 2 + MARGE);
      p[j] -= kant * (over / 2 + MARGE);
      for (const k of [i, j]) {
        px[k] = klem(px[k], half[k] + 0.5, breed - half[k] - 0.5);
        py[k] = klem(py[k], r[k] + 0.5, hoog - onder[k] - 0.5);
      }
    }
  }
  return null;
}

export type Schikking = { plek: [number, number][]; breed: number; hoog: number };

// Per naam (x, y) in een vlak van `breed` bij `hoog` (`netwerk.schik`). De krachten hangen niet van het vlak af, dus
// die één keer; past het niet, dan wordt het vlak een stuk hoger en breder.
export function schik(stralen: number[], randen: [number, number, number][], labels: number[],
                      { breed = BREED, hoog = HOOG, zaad = 7 } = {}): Schikking {
  const n = stralen.length;
  if (n === 0) return { plek: [], breed, hoog };
  const r = Float64Array.from(stralen);
  const w = Float64Array.from(labels);
  const ruw = krachten(n, randen, zaad);
  for (let poging = 0; poging <= GROEI; poging++) {
    const plek = past(ruw, r, w, breed, hoog);
    if (plek) {
      return { plek: Array.from({ length: n }, (_, i): [number, number] => [rond(plek[0][i], 1), rond(plek[1][i], 1)]),
               breed: rond(breed, 1), hoog: rond(hoog, 1) };
    }
    breed *= 1.05;
    hoog *= 1.15;
  }
  throw new Error('het netwerk past niet in het vlak');
}

// Alleen voor de toets: de krachten, het uit elkaar schuiven en het gewicht van een lijn, elk apart.
export const binnenkant = { krachten, past, gewicht: log1pGewicht };
