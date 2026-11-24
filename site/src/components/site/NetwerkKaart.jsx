// Het netwerk van namen (PLAN #34.2ai, SPECS E9.S18): de cirkels en lijnen als SVG, op de server getekend op de plekken
// die het platform berekent (`factiz_site/netwerk.py`). Zonder script is elke cirkel een link die de naam kiest (?naam=);
// met script lichten bij aanwijzen de buren op, en vindt een zoekveld een naam in het netwerk. Wat je typt, blijft in de
// browser. Het plaatje is voor een schermlezer verborgen en heeft geen tabstop: de lijst naast het netwerk is de weg in
// woorden (AC5).
import { useEffect, useMemo, useRef, useState } from 'react';
import { THEMA } from './ThemaTegel.jsx';

const LABEL_ONDER = 12;
const plat = (s) => s.normalize('NFKD').replace(/\p{M}/gu, '').toLocaleLowerCase();

export default function NetwerkKaart({ knopen, randen, breed, hoog, gekozen, tekst }) {
  const [wijs, zetWijs] = useState(null);
  const [vraag, zetVraag] = useState('');
  const [klaar, zetKlaar] = useState(false);
  const vlak = useRef(null);
  useEffect(() => zetKlaar(true), []);
  // op een smal scherm schuift het vlak naar de gekozen naam
  useEffect(() => {
    const v = vlak.current, k = knopen.find((x) => x.id === gekozen);
    if (v && k && v.scrollWidth > v.clientWidth) v.scrollLeft = (k.x / breed) * v.scrollWidth - v.clientWidth / 2;
  }, [gekozen]);
  const plek = useMemo(() => Object.fromEntries(knopen.map((k) => [k.id, k])), [knopen]);
  const buren = useMemo(() => {
    const uit = {};
    for (const r of randen) {
      (uit[r.a] ??= new Set()).add(r.b);
      (uit[r.b] ??= new Set()).add(r.a);
    }
    return uit;
  }, [randen]);
  // wat oplicht: de aangewezen naam, anders de gekozen, met hun buren
  const midden = wijs ?? gekozen;
  const licht = midden ? new Set([midden, ...(buren[midden] ?? [])]) : null;
  const gevonden = vraag.trim()
    ? knopen.filter((k) => plat(k.naam).includes(plat(vraag.trim()))).sort((a, b) => a.naam.localeCompare(b.naam)).slice(0, 8)
    : [];
  const treffer = new Set(gevonden.map((k) => k.id));

  return (
    <div className="nw">
      {klaar && (
        <div className="nw-zoek">
          <label className="text-[12px] font-semibold" htmlFor="nw-vraag">{tekst.zoek}</label>
          <input id="nw-vraag" className="invoer" type="search" dir="auto" autoComplete="off" value={vraag}
                 onChange={(e) => zetVraag(e.target.value)} onKeyDown={(e) => e.key === 'Escape' && zetVraag('')} />
          {vraag.trim() && (gevonden.length
            ? <ul className="nw-treffers">{gevonden.map((k) => <li key={k.id}><a href={k.href}>{k.naam}</a></li>)}</ul>
            : <p className="zacht text-[12.5px]">{tekst.geen}</p>)}
        </div>
      )}
      <p className="nw-schuif zacht text-[12px]">{tekst.schuif}</p>
      <div className="nw-vlak" ref={vlak}>
        <svg data-netwerk viewBox={`0 0 ${breed} ${hoog}`} aria-hidden="true" focusable="false"
             onMouseLeave={() => zetWijs(null)}>
          <g className="nw-randen">
            {randen.map((r) => {
              const a = plek[r.a], b = plek[r.b];
              const aan = licht && licht.has(r.a) && licht.has(r.b) && (r.a === midden || r.b === midden);
              return <line key={`${r.a}-${r.b}`} x1={a.x} y1={a.y} x2={b.x} y2={b.y} strokeWidth={r.dikte}
                           className={aan ? 'nw-rand nw-aan' : licht ? 'nw-rand nw-stil' : 'nw-rand'} />;
            })}
          </g>
          {knopen.map((k) => {
            const stand = treffer.has(k.id) ? 'nw-gevonden' : licht ? (licht.has(k.id) ? '' : 'nw-stil') : '';
            // een label staat er altijd bij de grote namen; bij een andere alleen als hij zelf gekozen, aangewezen of gevonden
            // is (de buren staan in de lijst ernaast; al hun labels samen zouden elkaar overlappen)
            const toon = k.label || k.id === midden || treffer.has(k.id);
            return (
              <a key={k.id} href={k.href} tabIndex={-1} className={`nw-knoop ${stand} ${k.id === midden ? 'nw-midden' : ''}`}
                 onMouseEnter={() => zetWijs(k.id)}>
                <title>{`${k.naam}: ${k.aantal_tekst}`}</title>
                <circle cx={k.x} cy={k.y} r={k.r} data-familie={THEMA[k.thema]?.familie ?? ''} />
                {toon && <text x={k.x} y={k.y + k.r + LABEL_ONDER} textAnchor="middle">{k.kort}</text>}
              </a>
            );
          })}
        </svg>
      </div>
    </div>
  );
}
