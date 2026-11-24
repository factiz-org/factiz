// Eén kaart voor een factcheck in elke lijst van de site (PLAN #34.2l, DESIGNSYSTEEM §4): boven het oordeel met de datum,
// in het midden de bewering (hoogstens drie regels), onder de context (thema, het land waar ze over gaat, redacties, en
// de taal als er geen vertaling is). Het label kleurt naar zijn soort, altijd met het woord en een stip (D5). Op de start en de factcheck zonder script.
import { BELLEN_F, bellenOp } from '../../lib/bellenf.js';
import { Tekst } from '../../lib/archief.jsx';
import ThemaTegel from './ThemaTegel.jsx';
import LijnIcoon from './LijnIcoon.jsx';
import { naarSite } from '../../lib/talen.js';

export default function Rij({ r, bijKlik }) {
  const voet = [
    r.thema && <span key="thema" className="thema"><ThemaTegel thema={r.thema.sleutel} />{r.thema.naam}</span>,
    // de soort volgens de redactie en de vorm (PLAN #34.2ak): een lijnicoon met het woord, de soort met wie het zegt
    // naam en regel in één tekstvak naast het icoon, dat breekt als een zin (PLAN #34.2ci: op 320 px stonden ze als twee
    // smalle kolommen naast elkaar)
    ...(r.kenmerken ?? []).map((k) => <span key={k.wat} className="kenmerk"><LijnIcoon wat={k.wat} waarde={k.waarde} />
      <span className="kenmerk-tekst">{k.naam}{k.regel && <>{' '}<span className="kenmerk-regel">{k.regel}</span></>}</span></span>),
    r.land && <span key="land">{r.land.naam}</span>,
    // wie het oordeel draagt staat al bij het stempel; anders hier hoeveel redacties het natrokken
    r.redacties && !r.volgens && <span key="redacties">{r.redacties}</span>,
    r.taalnaam && <span key="taal">{r.taalnaam}</span>,
    // een eigen check die nog concept is, op de Radar van een voorbeeld (PLAN #37.4)
    r.concept && <span key="concept" className="fz-eigen-conceptje">{r.concept}</span>,
  ].filter(Boolean);
  return (
    <li>
      <a className="rij" href={naarSite(r.href)} onClick={bijKlik}>
        <span className="rij-kop">
          {r.eigen ? (
            // een eigen factcheck van Factiz (PLAN #37.4, DESIGN §4x): het zegel voor hetzelfde stempel als bij een andere
            // redactie; het zegel is het verschil, ook in grijstinten (D12)
            <span className="fz-eigen-rijgroep">
              <span className="fz-eigen-rijmerk" aria-hidden="true">
                <svg viewBox="0 0 100 100"><circle cx="50" cy="50" r="45" fill="none" stroke="currentColor" strokeWidth="7" />
                  <g transform={bellenOp(50, 50, 0.95)} fill="currentColor">{BELLEN_F.map((d) => <path key={d} d={d} />)}</g></svg>
              </span>
              <span className="fz-stempel" data-soort={r.soort ?? 'geen'}>{r.eigen}</span>
              <span className="fz-eigen-wie">Factiz</span>
            </span>
          ) : r.stempel ? (
            // het oordeel van de redacties als stempel, met klein wie het zegt (PLAN #34.2cc, DESIGN §4y, PO 2026-11-19:
            // "in plaats van 'bekend als onwaar', zeggen we gewoon 'onwaar volgens'"); nooit een eigen oordeel (DR2)
            <span className="fz-stempelgroep">
              <span className="fz-stempel" data-soort={r.soort ?? 'geen'}>{r.stempel}</span>
              {r.volgens && <span className="fz-stempel-wie">{r.volgens}</span>}
            </span>
          ) : <span className="label" data-soort={r.soort ?? 'geen'}>{r.label}</span>}
          {r.datum && <span className="mono">{r.datum}</span>}
        </span>
        {/* de kale bewering nooit als fragment in een zoekresultaat (PLAN #34.2bw) */}
        <span className="rij-bewering" data-nosnippet="" lang={r.taal} dir={r.richting}><Tekst stukken={r.stukken} tekst={r.tekst} /></span>
        {r.origineel && (
          <span className="rij-origineel" data-nosnippet="">{r.origineel.regel} <span lang={r.origineel.taal} dir={r.origineel.richting}>
            <Tekst stukken={r.origineel.stukken} tekst={r.origineel.tekst} /></span></span>
        )}
        {voet.length > 0 && <span className="rij-voet">{voet}</span>}
      </a>
    </li>
  );
}

// Een stuk in de tijdlijn van een dossier dat geen factcheck is (pers, onderzoek, besluit, rapport): dezelfde kaart, met
// een neutraal label zonder soort, want het is geen oordeel van een redactie; de link gaat naar de bron zelf.
export function Bronrij({ soort, bron, datum, titel, url }) {
  return (
    <li>
      <a className="rij" href={url || '#'} rel="noopener">
        <span className="rij-kop">
          <span className="label">{soort}</span>
          {datum && <span className="mono">{datum}</span>}
        </span>
        <span className="rij-bewering">{titel}</span>
        {bron && <span className="rij-voet"><span>{bron}</span></span>}
      </a>
    </li>
  );
}
