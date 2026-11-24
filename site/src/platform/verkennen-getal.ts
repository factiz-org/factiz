// Rekenen zoals Python het doet, voor Verkennen en het netwerk van namen (B80, PLAN #34.2bo stap 3): `round()` en
// `f"{x:.1f}"` (half naar even op de exacte waarde), en de logaritme. `Math.log` en `Math.log1p` van V8 zitten in
// één op de twintig gevallen een bit naast die van macOS, en de schikking van het netwerk vergroot zo'n bit tot een
// andere plek; hier dus een logaritme die juist afrondt, in dubbele dubbele precisie (twee getallen per waarde).
// macOS rondt ook bijna altijd juist af: alleen vlak bij het midden tussen twee getallen (op 1 op de 10.000) niet.

type DD = [number, number];

const SPLITS = 134217729;            // 2^27 + 1: een getal in twee helften van 26 bits (Dekker)

function som(a: number, b: number): DD {
  const s = a + b;
  const v = s - a;
  return [s, (a - (s - v)) + (b - v)];
}

function snel(a: number, b: number): DD {          // |a| >= |b|
  const s = a + b;
  return [s, b - (s - a)];
}

function product(a: number, b: number): DD {
  const p = a * b;
  let t = SPLITS * a;
  const ah = t - (t - a);
  const al = a - ah;
  t = SPLITS * b;
  const bh = t - (t - b);
  const bl = b - bh;
  return [p, ((ah * bh - p) + ah * bl + al * bh) + al * bl];
}

function plus(a: DD, b: DD): DD {
  const [s, e] = som(a[0], b[0]);
  const [t, f] = som(a[1], b[1]);
  const [u, g] = snel(s, e + t);
  return snel(u, g + f);
}

function maal(a: DD, b: DD): DD {
  const [p, e] = product(a[0], b[0]);
  return snel(p, e + (a[0] * b[1] + a[1] * b[0]));
}

function gedeeld(a: DD, b: DD): DD {
  const q1 = a[0] / b[0];
  let r = plus(a, maal(b, [-q1, 0]));
  const q2 = r[0] / b[0];
  r = plus(r, maal(b, [-q2, 0]));
  const q3 = r[0] / b[0];
  return plus(snel(q1, q2), [q3, 0]);
}

// log(1 + j/64) voor j = 0..64, met de reeks van atanh: log(c) = 2·atanh(s), s = (c − 1)/(c + 1) = j/(128 + j).
// Pas gerekend bij het eerste gebruik; 40 termen halen ook bij s = 1/3 ruim 100 bits.
let tabel: DD[] | null = null;

function tafel(): DD[] {
  if (tabel) return tabel;
  tabel = [];
  for (let j = 0; j <= 64; j++) {
    const s = gedeeld([j, 0], [128 + j, 0]);
    const s2 = maal(s, s);
    let p = s;
    let totaal = s;
    for (let k = 1; k <= 40; k++) {
      p = maal(p, s2);
      totaal = plus(totaal, gedeeld(p, [2 * k + 1, 0]));
    }
    tabel.push([2 * totaal[0], 2 * totaal[1]]);
  }
  return tabel;
}

const BEELD = new Float64Array(1);
const BITS = new Uint32Array(BEELD.buffer);       // [laag, hoog]: little-endian, zoals elke Worker en elke Mac

function macht2(k: number): number {
  BITS[0] = 0;
  BITS[1] = (k + 1023) << 20;
  return BEELD[0];
}

// log(h + l) voor h > 0, juist afgerond: h = 2^k · m met 1 <= m < 2, m = c · (1 + r) met c = 1 + j/64 en |r| <= 1/128.
function logDD(h: number, l: number): number {
  if (!(h > 0) || !Number.isFinite(h)) return h === 0 ? -Infinity : h === Infinity ? Infinity : NaN;
  let k0 = 0;
  if (h < 2.2250738585072014e-308) {               // subnormaal: eerst normaal maken
    h *= 18014398509481984;                        // 2^54
    l *= 18014398509481984;
    k0 = -54;
  }
  BEELD[0] = h;
  const k = ((BITS[1] >>> 20) & 0x7ff) - 1023;
  BITS[1] = (BITS[1] & 0x800fffff) | (1023 << 20);
  const m = BEELD[0];
  const ml = l * macht2(-k);
  const t = tafel();
  const j = Math.round((m - 1) * 64);
  const c = 1 + j / 64;
  const r = gedeeld(som(m - c, ml), [c, 0]);
  const s = gedeeld(r, plus([2, 0], r));
  const s2 = maal(s, s);
  const s3 = maal(s2, s);
  const q = s2[0];
  // vanaf s^5 is het minder dan 2^-34 van het geheel: een gewoon getal is daar precies genoeg
  const staart = 2 * (s3[0] * q) * (1 / 5 + q * (1 / 7 + q * (1 / 9 + q * (1 / 11 + q * (1 / 13 + q / 15)))));
  const derde = gedeeld(s3, [3, 0]);
  const reeks = plus(plus([2 * s[0], 2 * s[1]], [2 * derde[0], 2 * derde[1]]), [staart, 0]);
  const kk = k + k0;
  const ln2 = t[64];
  const [p, e] = product(kk, ln2[0]);
  const kln2 = snel(p, e + kk * ln2[1]);
  return plus(plus(kln2, t[j]), reeks)[0];
}

// Python `math.log(x)` en `math.log1p(x)` (en `np.log1p`), juist afgerond.
export function ln(x: number): number {
  return logDD(x, 0);
}

export function ln1p(x: number): number {
  if (x === 0 || Number.isNaN(x)) return x;
  if (x < -1) return NaN;
  const [h, l] = som(1, x);
  return logDD(h, l);
}

// Ligt x precies midden tussen twee getallen met `n` decimalen? Dat kan alleen als x · 2^(n+1) oneven is.
function precieshalf(x: number, n: number): boolean {
  const y = x * 2 ** (n + 1);
  return Number.isInteger(y) && Math.abs(y % 2) === 1;
}

// Python `f"{x:.{n}f}"`: de exacte waarde afgerond, bij precies half naar het even cijfer (`toFixed` kiest dan omhoog).
export function vast(x: number, n: number): string {
  if (!Number.isFinite(x)) return x > 0 ? 'inf' : x < 0 ? '-inf' : 'nan';
  if (precieshalf(x, n)) {
    const v = x * 10 ** n;                       // precies: een oneven getal maal 5^n, gedeeld door 2
    const laag = Math.floor(v);
    const even = laag % 2 === 0 ? laag : laag + 1;
    const uit = (even / 10 ** n).toFixed(n);
    return even === 0 && x < 0 ? `-${uit}` : uit;
  }
  const uit = x.toFixed(n);
  return Object.is(x, -0) ? `-${uit}` : uit;
}

// Python `round(x, n)`: het getal dat het dichtst bij die decimale vorm ligt.
export function rond(x: number, n: number): number {
  if (!Number.isFinite(x)) return x;
  return Number(vast(x, n));
}

// Python `round(x)` op een getal zonder decimalen: half naar even.
export function rondEven(x: number): number {
  const laag = Math.floor(x);
  const rest = x - laag;
  if (rest > 0.5) return laag + 1;
  if (rest < 0.5) return laag;
  return laag % 2 === 0 ? laag : laag + 1;
}
