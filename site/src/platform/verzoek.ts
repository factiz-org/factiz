// Werk dat over verzoeken gedeeld wordt (PLAN #34.2bq). Een Worker breekt een verzoek af dat wacht op werk dat een ander
// verzoek nog doet ("the Workers runtime canceled this request because it detected that your Worker's code had hung"):
// zo'n verzoek heeft zelf niets meer lopen. Op factiz.org gaf dat 5 tot 8% fouten bij een paar bezoekers tegelijk.
// Daarom: wat af is, deelt elk verzoek; wat nog bezig is, deelt alleen het verzoek dat het begon. Een ander verzoek kijkt
// telkens even (met een eigen timer, dus het leeft nog) of het werk af is en neemt dan het resultaat; mislukt het werk of
// duurt het te lang, dan doet het het zelf. Wie het verzoek is, zegt de omgeving (`zetVerzoek`): in de Worker de context
// van het verzoek, in Node altijd hetzelfde, zodat daar alles gedeeld blijft zoals het was.

let huidig: () => unknown = () => null;

export function zetVerzoek(f: () => unknown): void {
  huidig = f;
}

type Bezig<V> = { wie: unknown; belofte: Promise<V> };
export type VoorraadOpties = { max?: number; wachtMs?: number; wachtrondes?: number };

export class Voorraad<V> {
  private af = new Map<string, V>();
  private bezig = new Map<string, Bezig<V>>();
  private orde = new Map<string, true>();       // wanneer elk stuk begon, voor `alle`
  private readonly max: number;
  private readonly wachtMs: number;
  private readonly wachtrondes: number;

  constructor(opties: VoorraadOpties = {}) {
    this.max = opties.max ?? Infinity;
    this.wachtMs = opties.wachtMs ?? 5;
    this.wachtrondes = opties.wachtrondes ?? 3000;      // ~15 s
  }

  // Het stuk onder `sleutel`: wat af is meteen, wat dit verzoek al begon dezelfde belofte, en anders zelf maken of wachten
  // op wat een ander verzoek doet.
  haal(sleutel: string, maak: () => Promise<V>): Promise<V> {
    if (this.af.has(sleutel)) return Promise.resolve(this.af.get(sleutel) as V);
    const wie = huidig();
    const b = this.bezig.get(sleutel);
    if (b && b.wie === wie) return b.belofte;
    if (b) return this.wacht(sleutel, b, maak);
    return this.begin(sleutel, wie, maak);
  }

  has(sleutel: string): boolean {
    return this.af.has(sleutel);
  }

  // Een stuk dat af is weer vergeten (zodat het volgende verzoek het opnieuw maakt).
  vergeet(sleutel: string, waarde?: V): void {
    if (waarde === undefined || this.af.get(sleutel) === waarde) this.af.delete(sleutel);
  }

  get size(): number {
    return this.af.size;
  }

  // Alles wat af is, op volgorde van beginnen; eerst wacht het op wat nog bezig is.
  async alle(): Promise<[string, V][]> {
    await Promise.all([...this.bezig.values()].map((b) => b.belofte.catch(() => undefined)));
    return [...this.orde.keys()].filter((k) => this.af.has(k)).map((k): [string, V] => [k, this.af.get(k) as V]);
  }

  private begin(sleutel: string, wie: unknown, maak: () => Promise<V>): Promise<V> {
    let gestart: Promise<V>;
    try {
      gestart = maak();
    } catch (fout) {
      gestart = Promise.reject(fout);
    }
    this.orde.delete(sleutel);
    this.orde.set(sleutel, true);
    const belofte: Promise<V> = gestart.then((w) => {
      if (this.bezig.get(sleutel)?.belofte === belofte) this.bezig.delete(sleutel);
      this.af.delete(sleutel);
      this.af.set(sleutel, w);
      while (this.af.size > this.max) {
        const oudste = this.af.keys().next().value as string;
        this.af.delete(oudste);
        this.orde.delete(oudste);
      }
      return w;
    }, (fout) => {
      if (this.bezig.get(sleutel)?.belofte === belofte) this.bezig.delete(sleutel);
      throw fout;
    });
    this.bezig.set(sleutel, { wie, belofte });
    return belofte;
  }

  private async wacht(sleutel: string, b: Bezig<V>, maak: () => Promise<V>): Promise<V> {
    for (let i = 0; i < this.wachtrondes; i++) {
      await new Promise((ok) => setTimeout(ok, this.wachtMs));
      if (this.af.has(sleutel)) return this.af.get(sleutel) as V;
      if (this.bezig.get(sleutel) !== b) break;          // mislukt, of een ander begon opnieuw
    }
    if (this.af.has(sleutel)) return this.af.get(sleutel) as V;
    const nu = this.bezig.get(sleutel);
    const wie = huidig();
    if (nu && nu !== b && nu.wie === wie) return nu.belofte;
    return this.begin(sleutel, wie, maak);
  }
}
