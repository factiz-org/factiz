/*
 * Een tekening per thema en per dossier (PLAN #34.2ap, SPECS E9.S22, DESIGNSYSTEEM §4). De tekentaal komt van de
 * routeplaatjes van Ideelab (`components/Routeplaatjes.tsx` in de repo van de Ideelab-site, PO 2026-11-15: "daar hebben
 * we al een SVG stijl, die moet alleen wat abstracter met wat grain erover"), hier in eigen code: een halfdoorzichtig
 * vel dat linksboven inspringt en rechts en onder uit het beeld loopt, met vormen zonder woorden in de kleur van de
 * familie (`currentColor`, E9.S16). Abstracter dan bij Ideelab: geen venster en geen formulier, hoogstens drie soorten
 * vormen, en alleen de vorm die de betekenis draagt op volle kleur. De vormen vervagen naar onder. De korrel komt van
 * het veld eronder; een eigen korrel gaf een dubbele korrel (PLAN #34.2bf).
 *
 * De vormen zelf staan als gegevens in `site/src/lib/platen.js`, één bron voor deze tekening en voor het deelplaatje
 * (PLAN #34.2aq). Een tekening toont het onderwerp, nooit de bewering die gecheckt is, en nooit een oordeel (AC3). Ze staat
 * op het veld en nooit achter een bewering, een label of een bron (D11). Voor een schermlezer verborgen.
 *
 * Eén raster van 160 bij 68; het vel staat op (26, 13). Het vel vult het beeld (`slice`, linksboven vast), de vormen
 * passen erin (`meet`), zodat ook een smallere kaart, zoals die van een dossier, de hele tekening toont. In de kop van
 * een thema of dossier staat ze rechts.
 */
import { THEMA } from './ThemaTegel.jsx';
import { UITSNEDE, vormen } from '../../lib/platen.js';

function Vorm({ v }) {
  switch (v.v) {
    case 'regel':
      return <rect x={v.x} y={v.y} width={v.w} height={v.h} rx={v.h / 2} fill="currentColor" fillOpacity={v.o} />;
    case 'blok':
      return <rect x={v.x} y={v.y} width={v.w} height={v.h} rx={v.r} fill="currentColor" fillOpacity={v.o} />;
    case 'stip':
      return v.open
        ? <circle className="plaat-open" cx={v.x} cy={v.y} r={v.r} stroke="currentColor" strokeOpacity="0.45" strokeWidth="0.9" />
        : <circle cx={v.x} cy={v.y} r={v.r} fill="currentColor" fillOpacity={v.o} />;
    case 'lijn':
      return <path d={v.d} fill="none" stroke="currentColor" strokeOpacity={v.o} strokeWidth={v.w} strokeLinecap="round"
                   strokeLinejoin="round" strokeDasharray={v.streep ?? undefined} />;
    case 'vlak':
      return <path d={v.d} fill="currentColor" fillOpacity={v.o} />;
    case 'ring':
      return <circle cx={v.x} cy={v.y} r={v.r} fill="none" stroke="currentColor" strokeOpacity={v.o} strokeWidth={v.w}
                     strokeDasharray={v.streep ?? undefined} />;
    default:
      return null;
  }
}

export default function Plaat({ soort = 'thema', sleutel, thema, plek = 'kaart' }) {
  const lijst = vormen(soort, sleutel, thema);
  if (!lijst) return null;
  const familie = THEMA[thema ?? sleutel]?.familie ?? '';
  const uitsnede = UITSNEDE[plek].join(' ');
  return (
    <span className={`plaat plaat-${plek}`} data-familie={familie} aria-hidden="true">
      <svg className="plaat-vel" viewBox={uitsnede} preserveAspectRatio="xMinYMin slice" focusable="false">
        <rect x="26" y="13" width="160" height="100" rx="3" />
      </svg>
      <svg className="plaat-vormen" viewBox={uitsnede} preserveAspectRatio="xMinYMin meet" focusable="false">
        {lijst.map((v, i) => <Vorm key={i} v={v} />)}
      </svg>
    </span>
  );
}
