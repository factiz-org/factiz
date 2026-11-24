// De sticker op de plek van een weggelaten naam (maatregel 2, PLAN #34.2bw); de stukken in `weggelaten.js`.
import { stukken } from './weggelaten.js';

// Een tekst met een sticker op de plek van een weggelaten naam; `ster` waar de voetnoot eronder staat (de factcheck).
export function MetWeg({ tekst, ster = false }) {
  const s = stukken(tekst);
  if (!s.some(([, weg]) => weg)) return tekst ?? '';
  return s.map(([stuk, weg], i) => (weg
    ? <span key={i} className="fz-weg">{stuk}{ster && <sup aria-hidden="true">*</sup>}</span>
    : <span key={i}>{stuk}</span>));
}
