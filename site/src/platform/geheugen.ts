// Het geheugen van een uitgave (B80, PLAN #34.2bo stap 3c): wat het platform één keer per uitgave rekent (de kolommen van
// de filters, de woordenlijst, de afkortingen, de adressen), vooraf berekend en bewaard, zodat een nieuwe Worker het leest
// in plaats van het opnieuw te rekenen uit D1. Dezelfde code rekent het; hier alleen bewaren en teruglezen, precies.

// Een waarde als tekst: JSON, met een merk voor wat JSON niet kent (Map, Set, getallenrijen, -0, NaN, oneindig).
// Een object dat op meer plekken staat, blijft één object: de code vergelijkt soms op het object zelf (een ingang die al in
// een lijst staat), en twee kopieën zouden dan dubbel tellen. De eerste keer krijgt het een nummer, daarna een verwijzing.
export function bewaar(waarde: unknown): string {
  const tellingen = new Map<object, number>();
  tel(waarde, tellingen);
  const gedeeld = new Map<object, number>();
  for (const [o, n] of tellingen) if (n > 1) gedeeld.set(o, -1);
  return JSON.stringify(inpakken(waarde, gedeeld, { volgende: 0 }));
}

export function lees(tekst: string): unknown {
  return uitpakken(JSON.parse(tekst), new Map());
}

function tel(w: unknown, tellingen: Map<object, number>): void {
  if (w === null || typeof w !== 'object') return;
  const n = tellingen.get(w) ?? 0;
  tellingen.set(w, n + 1);
  if (n) return;
  if (Array.isArray(w)) w.forEach((x) => tel(x, tellingen));
  else if (w instanceof Map) for (const [k, v] of w) { tel(k, tellingen); tel(v, tellingen); }
  else if (w instanceof Set) for (const x of w) tel(x, tellingen);
  else if (Object.getPrototypeOf(w) === Object.prototype) for (const x of Object.values(w)) tel(x, tellingen);
}

const RIJEN = { Int32Array, Uint8Array, Float64Array, Uint32Array, Int16Array, Uint16Array, Int8Array } as const;

// Een getallenrij wordt bewaard in het kleinste soort waar elke waarde precies in past (een code van 0 tot 254 in één byte
// in plaats van vier) en bij het lezen terug in haar eigen soort gezet: de kolommen van 106.073 pagina's werden zo een
// kwart zo groot (stap 8).
const KLEINER: Record<string, [string, number, number][]> = {
  Int32Array: [['Int8Array', -128, 127], ['Int16Array', -32768, 32767]],
  Uint32Array: [['Uint8Array', 0, 255], ['Uint16Array', 0, 65535]],
  Int16Array: [['Int8Array', -128, 127]],
  Uint16Array: [['Uint8Array', 0, 255]],
};

type MetBasis64 = { fromBase64?: (s: string) => Uint8Array };

function basis64(bytes: Uint8Array): string {
  let s = '';
  for (let i = 0; i < bytes.length; i += 0x8000) s += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  return btoa(s);
}

function uitBasis64(tekst: string): Uint8Array {
  // in een Worker kent Uint8Array dit zelf (veel sneller dan teken voor teken); in Node 22 nog niet
  const eigen = (Uint8Array as unknown as MetBasis64).fromBase64;
  if (eigen) return eigen(tekst);
  const s = atob(tekst);
  const uit = new Uint8Array(s.length);
  for (let i = 0; i < s.length; i++) uit[i] = s.charCodeAt(i);
  return uit;
}

function rij(w: ArrayBufferView & ArrayLike<number>, naam: string): unknown {
  for (const [klein, laag, hoog] of KLEINER[naam] ?? []) {
    let past = true;
    for (let i = 0; i < w.length && past; i++) past = w[i] >= laag && w[i] <= hoog;
    if (past) {
      const k = new RIJEN[klein as keyof typeof RIJEN](w as unknown as ArrayLike<number>);
      return { _r: naam, k: klein, b: basis64(new Uint8Array(k.buffer, k.byteOffset, k.byteLength)) };
    }
  }
  return { _r: naam, b: basis64(new Uint8Array(w.buffer, w.byteOffset, w.byteLength)) };
}

function inpakken(w: unknown, gedeeld: Map<object, number>, teller: { volgende: number }): unknown {
  if (w !== null && typeof w === 'object' && gedeeld.has(w)) {
    const nummer = gedeeld.get(w)!;
    if (nummer >= 0) return { _ref: nummer };
    const eigen = teller.volgende++;
    gedeeld.set(w, eigen);
    return { _id: eigen, _w: inpakkenZelf(w, gedeeld, teller) };
  }
  return inpakkenZelf(w, gedeeld, teller);
}

function inpakkenZelf(w: unknown, gedeeld: Map<object, number>, teller: { volgende: number }): unknown {
  const inp = (x: unknown) => inpakken(x, gedeeld, teller);
  if (w === null || typeof w === 'string' || typeof w === 'boolean') return w;
  if (typeof w === 'number') {
    if (Number.isNaN(w)) return { _g: 'NaN' };
    if (w === Infinity || w === -Infinity) return { _g: w > 0 ? 'inf' : '-inf' };
    if (Object.is(w, -0)) return { _g: '-0' };
    return w;
  }
  if (w === undefined) return { _o: 1 };
  if (Array.isArray(w)) return w.map(inp);
  if (w instanceof Map) return { _m: [...w].map(([k, v]) => [inp(k), inp(v)]) };
  if (w instanceof Set) return { _s: [...w].map(inp) };
  for (const [naam, soort] of Object.entries(RIJEN)) {
    if (w instanceof soort) return rij(w as unknown as ArrayBufferView & ArrayLike<number>, naam);
  }
  if (typeof w === 'object' && Object.getPrototypeOf(w) === Object.prototype) {
    // een gewoon object; een sleutel die met _ begint krijgt er een _ bij, zodat hij nooit een merk lijkt
    const uit: Record<string, unknown> = { _v: 1 };
    for (const [k, v] of Object.entries(w as Record<string, unknown>)) uit[k.startsWith('_') ? `_${k}` : k] = inp(v);
    return uit;
  }
  throw new TypeError(`niet te bewaren: ${Object.prototype.toString.call(w)}`);
}

function uitpakken(w: unknown, gezien: Map<number, unknown>): unknown {
  if (w === null || typeof w !== 'object') return w;
  const o = w as Record<string, unknown>;
  if ('_ref' in o) return gezien.get(o._ref as number);
  if ('_id' in o) {
    // eerst een lege houder onder het nummer, dan vullen: zo vindt een verwijzing naar zichzelf (een kring) het al
    const houder = leeg(o._w);
    if (houder === undefined) {
      const waarde = uitpakken(o._w, gezien);
      gezien.set(o._id as number, waarde);
      return waarde;
    }
    gezien.set(o._id as number, houder);
    vul(houder, o._w as Record<string, unknown> | unknown[], gezien);
    return houder;
  }
  const houder = leeg(w);
  if (houder !== undefined) {
    vul(houder, w as Record<string, unknown> | unknown[], gezien);
    return houder;
  }
  if ('_g' in o) return ({ NaN: NaN, inf: Infinity, '-inf': -Infinity, '-0': -0 } as Record<string, number>)[o._g as string];
  if ('_o' in o) return undefined;
  if ('_r' in o) {
    const bytes = uitBasis64(o.b as string);
    const soort = RIJEN[o._r as keyof typeof RIJEN];
    if (!('k' in o)) return new soort(bytes.buffer, bytes.byteOffset, bytes.byteLength / soort.BYTES_PER_ELEMENT);
    const klein = RIJEN[o.k as keyof typeof RIJEN];
    return new soort(new klein(bytes.buffer, bytes.byteOffset, bytes.byteLength / klein.BYTES_PER_ELEMENT));
  }
  throw new TypeError('onbekend merk in het geheugen');
}

// Een lege houder voor een lijst, Map, Set of gewoon object; niets voor de rest.
function leeg(w: unknown): unknown {
  if (Array.isArray(w)) return [];
  if (w === null || typeof w !== 'object') return undefined;
  const o = w as Record<string, unknown>;
  if ('_m' in o) return new Map();
  if ('_s' in o) return new Set();
  if ('_v' in o) return {};
  return undefined;
}

function vul(houder: unknown, w: Record<string, unknown> | unknown[], gezien: Map<number, unknown>): void {
  const uitp = (x: unknown) => uitpakken(x, gezien);
  if (Array.isArray(houder)) {
    for (const x of w as unknown[]) houder.push(uitp(x));
  } else if (houder instanceof Map) {
    for (const [k, v] of (w as Record<string, unknown>)._m as [unknown, unknown][]) houder.set(uitp(k), uitp(v));
  } else if (houder instanceof Set) {
    for (const x of (w as Record<string, unknown>)._s as unknown[]) houder.add(uitp(x));
  } else {
    const uit = houder as Record<string, unknown>;
    for (const [k, v] of Object.entries(w as Record<string, unknown>)) {
      if (k === '_v') continue;
      uit[k.startsWith('__') ? k.slice(1) : k] = uitp(v);
    }
  }
}
