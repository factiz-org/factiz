// De bibliotheek van de site (PLAN #34.2b, DESIGNSYSTEEM §4): zoeken, filteren en sorteren zoals in een goede
// webwinkel. Breed: de filters in een kolom en meteen toegepast. Telefoon: twee tekstknoppen (#1198) en een lade die pas
// na "Toon n resultaten" toepast (#1125). Meer laden (#501), terug op dezelfde plek (#1024), de filters in het adres (#492).
import { useEffect, useRef, useState } from 'react';
import { Checkbox } from '../ui/checkbox.jsx';
import { useArchief, Tekst } from '../../lib/archief.jsx';
import { meetZoekterm } from '../../lib/meten.js';
import { Sorteren, Lade } from './ui.jsx';
import ThemaTegel from './ThemaTegel.jsx';
import LijnIcoon from './LijnIcoon.jsx';
import Rij from './Rij.jsx';
import Zoekveld from './Zoekveld.jsx';
import { naarSite, pad, LOCALE } from '../../lib/talen.js';

// Het vinkje in de neutrale kleuren van deze richting: zwart bij een keuze, zoals de primaire knop (#730).
const VINK_B = 'size-4 rounded-[4px] border-[color:var(--lijn-sterk)] bg-[color:var(--paneel)] '
  + 'data-[state=checked]:border-[color:var(--primair)] data-[state=checked]:bg-[color:var(--primair)] data-[state=checked]:text-[color:var(--primair-inkt)] '
  + 'focus-visible:ring-[color:var(--accent)] focus-visible:ring-offset-[color:var(--paneel)]';

// De plek voor "terug" staat in de geschiedenis van het tabblad zelf (history.state): niets wordt opgeslagen, en het
// verdwijnt met het tabblad (B75).
function bewaarPlek() {
  history.replaceState({ ...(history.state ?? {}), plek: { rijen: document.querySelectorAll('.rijen > li').length, y: scrollY } }, '');
}

// Een filter met vinkjes, ingekort na zes waarden met "Nog n tonen" (#470), met het aantal bij elke waarde (#467). Wat
// één keuze is (thema, land, redactie), krijgt rondjes met "Alles" bovenaan: een vinkje belooft dat je er meer kunt
// kiezen (#479). `plek` houdt de kolom en de lade uit elkaar, die tegelijk in de pagina kunnen staan.
function Vinkjes({ soort, kop, uitleg, waarden, kies, meerTekst, metZoeken, een, alles, plek, zoekTekst, nietsTekst }) {
  const [open, zetOpen] = useState(false);
  const [zoek, zetZoek] = useState('');
  // Tijdens het zoeken houdt de groep de hoogte van vóór het zoeken (PO 2026-11-18: "als ik factiz intyp sluit het veld en
  // kan ik nergens meer bij"): anders krimpt de lade bij één treffer, schiet de inhoud omhoog en verdwijnt het veld met
  // zijn treffer achter het toetsenbord en de knoppen onderaan.
  const groep = useRef(null);
  const [hoogte, zetHoogte] = useState(0);
  const zoekNu = (w) => {
    if (w && !zoek && groep.current) zetHoogte(groep.current.offsetHeight);
    if (!w) zetHoogte(0);
    zetZoek(w);
  };
  const lijst = zoek ? waarden.filter((k) => k.naam.toLowerCase().includes(zoek.toLowerCase())) : waarden;
  const getoond = open || zoek ? lijst : [...lijst.filter((k) => k.aan), ...lijst.filter((k) => !k.aan)].slice(0, Math.max(6, lijst.filter((k) => k.aan).length));
  if (!waarden.length) return null;
  return (
    <fieldset className="filtergroep" ref={groep} style={zoek && hoogte ? { minHeight: `${hoogte}px` } : undefined}>
      <legend className="filterkop">{kop}</legend>
      {/* wat de soort en de vorm tellen (SPECS E9.S19 AC5) */}
      {uitleg && <p className="filteruitleg">{uitleg}</p>}
      {metZoeken && waarden.length > 12 && (
        <input className="invoer mb-1" type="search" dir="auto" value={zoek} onChange={(e) => zoekNu(e.target.value)} placeholder={zoekTekst} aria-label={`${kop}: ${zoekTekst}`}
               onKeyDown={(e) => { if (e.key === 'Enter') e.preventDefault(); }} />
      )}
      {een && !zoek && (
        <label htmlFor={`${plek}-${soort}-alles`} className="vink">
          <input type="radio" className="rondje" id={`${plek}-${soort}-alles`} name={`${plek}-${soort}`} checked={!waarden.some((k) => k.aan)}
                 onChange={() => kies(soort, '')} />
          <span className="min-w-0 flex-1 leading-tight">{alles}</span>
        </label>
      )}
      {getoond.map((k) => (
        <label key={k.waarde} htmlFor={`${plek}-${soort}-${k.waarde}`} className="vink">
          {een
            ? <input type="radio" className="rondje" id={`${plek}-${soort}-${k.waarde}`} name={`${plek}-${soort}`} checked={k.aan} onChange={() => kies(soort, k.waarde)} />
            : <Checkbox className={VINK_B} id={`${plek}-${soort}-${k.waarde}`} checked={k.aan} onCheckedChange={() => kies(soort, k.waarde)} />}
          {soort === 'thema' && <ThemaTegel thema={k.waarde} />}
          {/* dezelfde stip als op de kaart, zodat filter en lijst hetzelfde zeggen (PLAN #34.2l) */}
          {soort === 'oordeel' && <span className="stip" data-soort={k.waarde} aria-hidden="true" />}
          {(soort === 'soort' || soort === 'vorm') && <LijnIcoon wat={soort} waarde={k.waarde} />}
          <span className="min-w-0 flex-1 leading-tight">{'⁨'}{k.naam}{'⁩'}</span><span className="tel">{k.aantal}</span>
        </label>
      ))}
      {zoek && !lijst.length && <p className="filteruitleg" role="status">{nietsTekst}</p>}
      {!open && !zoek && lijst.length > getoond.length && (
        <button type="button" className="vink w-full text-[var(--accent)]" onClick={() => zetOpen(true)}>{meerTekst.replace('{n}', lijst.length - getoond.length)}</button>
      )}
    </fieldset>
  );
}

function Filters({ f, kies, tekst, plek, vastSoorten }) {
  const gedeeld = { kies, meerTekst: tekst.filter_meer_n, plek, zoekTekst: tekst.lijst_zoeken, nietsTekst: tekst.zoek_niets };
  const een = { ...gedeeld, een: true, alles: tekst.filter_alles };
  return (
    <div className="grid">
      {!vastSoorten.has('thema') && <Vinkjes soort="thema" kop={tekst.filter_thema} waarden={f.lijsten.thema} {...een} />}
      {/* op de pagina van een thema het onderdeel als filter (PLAN #34.2bb, SPECS E9.S27 AC2) */}
      {vastSoorten.has('thema') && !vastSoorten.has('onderdeel') && <Vinkjes soort="onderdeel" kop={tekst.filter_onderdeel} waarden={f.lijsten.onderdeel ?? []} {...een} />}
      {f.groepen.filter((g) => !vastSoorten.has(g.soort)).map((g) => <Vinkjes key={g.soort} soort={g.soort} kop={g.kop} uitleg={g.uitleg} waarden={[...g.boven, ...g.meer]} {...gedeeld} />)}
      <Vinkjes soort="land" kop={tekst.filter_land} waarden={f.lijsten.land} {...een} metZoeken />
      <Vinkjes soort="redactie" kop={tekst.filter_redactie} waarden={f.lijsten.redactie} {...een} metZoeken />
    </div>
  );
}

// Op een themapagina (PLAN #34.2bb, SPECS E9.S27): `vast` het thema (en het onderdeel), `basis` het adres van die pagina,
// `kop` de kop van de lijst; de pagina zelf heeft al een h1.
export default function Bibliotheek({ begin, tekst, beginVraag, beginParen, actie, taal, vast = [], basis, kop: lijstKop }) {
  const lijst = pad(taal, 'fact-checks');
  const a = useArchief(begin, { taal, basis: basis ?? lijst, beginVraag, beginParen, beginLetterlijk: !!begin.letterlijk, vast });
  const { gegevens, f, vastSoorten } = a;
  const stukjes = f.stukjes.filter((s) => !vastSoorten.has(s.soort));
  const Kop = vast.length ? 'h2' : 'h1';
  const [lade, zetLade] = useState(false);
  const lijstKolom = useRef(null);
  const filterPaneel = useRef(null);
  const [concept, zetConcept] = useState(null);
  const [laadt, zetLaadt] = useState(false);
  const rijen = gegevens.rijen;
  const totaal = gegevens.totaal ?? 0;

  // de zoekvraag naar Google Analytics (B88, SPECS E9.S36 AC3): alleen na een ja, nooit een geplakt bericht, kort en zonder
  // e-mailadres of nummer; zonder meet-ID of ja gebeurt er niets (`meten.js`)
  useEffect(() => { if (a.vraag) meetZoekterm(a.vraag, !!gegevens.bericht); }, [a.vraag, gegevens.bericht]);

  // terug van een factcheck: dezelfde vraag, dezelfde rijen en dezelfde plek (#1024, #348, SPECS E9.S14 AC8)
  useEffect(() => {
    const plek = history.state?.plek;
    if (!plek && !history.state?.vraag) return;
    if (plek) history.scrollRestoration = 'manual';   // de pagina zet de plek zelf, na het laden van de rijen
    (async () => {
      const g = await a.herstel();
      if (!plek) return;
      const perBlad = Math.max(1, g.rijen.length);
      const tot = Math.min(Math.ceil(plek.rijen / perBlad), Math.ceil((g.totaal ?? 0) / perBlad));
      for (let blad = (g.blad ?? 1) + 1; blad <= tot; blad += 1) await a.meer(blad);
      setTimeout(() => scrollTo({ top: plek.y, behavior: 'instant' }), 0);
    })();
  }, []);

  // een nieuwe lijst (filter, zoekvraag, volgorde; niet Meer laden): terug naar haar begin, als dat boven uit beeld is,
  // anders sta je midden in een lijst die net veranderde (PLAN #34.2bj)
  useEffect(() => {
    const naarBegin = () => {
      const kolom = lijstKolom.current;
      if (!kolom) return;
      const kop = document.querySelector('.kop')?.getBoundingClientRect().bottom ?? 0;
      const top = kolom.getBoundingClientRect().top;
      if (top < kop) scrollTo({ top: scrollY + top - kop - 12, behavior: 'instant' });
    };
    addEventListener('factiz:gefilterd', naarBegin);
    return () => removeEventListener('factiz:gefilterd', naarBegin);
  }, []);

  // het filterpaneel scrollt zelf als het langer is dan het scherm; `data-meer` zolang er onder de rand nog filters
  // zitten, voor de zachte vervaging onderaan (de balk zelf is onzichtbaar tot de muis erop staat, PLAN #34.2bj)
  useEffect(() => {
    const paneel = filterPaneel.current;
    if (!paneel) return undefined;
    const zet = () => paneel.toggleAttribute('data-meer', paneel.scrollTop + paneel.clientHeight < paneel.scrollHeight - 4);
    zet();
    paneel.addEventListener('scroll', zet, { passive: true });
    const kijker = new ResizeObserver(zet);
    kijker.observe(paneel);
    if (paneel.firstElementChild) kijker.observe(paneel.firstElementChild);
    return () => { paneel.removeEventListener('scroll', zet); kijker.disconnect(); };
  }, []);

  async function openLade() { zetConcept({ ...gegevens, paren: a.paren }); zetLade(true); }
  async function kiesInLade(soort, waarde) { const g = await a.proef(a.nieuweParen(concept.paren, soort, waarde)); if (g) zetConcept(g); }
  async function meer() { zetLaadt(true); await a.meer(); zetLaadt(false); }

  const kop = a.vraag
    ? (gegevens.bericht ? gegevens.bericht_kop
      : gegevens.deels ? tekst.zoek_deels : totaal ? <>{gegevens.aantal} {tekst.zoek_voor} <q>{gegevens.verbeterd || a.vraag}</q></> : tekst.zoek_niets)
    : lijstKop ?? tekst.lijst_titel;

  return (
    <div className={vast.length ? 'pb-10' : 'baan pb-10'}>
      <div className="flex flex-wrap items-end justify-between gap-3 pt-4 pb-4">
        <div className="min-w-0">
          <Kop className="text-[22px] font-semibold tracking-[-0.02em]">{kop}</Kop>
          {!a.vraag && <p className="mono mt-0.5" aria-live="polite">{gegevens.aantal}</p>}
          {/* een geplakt bericht (PLAN #34.2au): op welke woorden gezocht is, en dat het gelijkenis in woorden is */}
          {a.vraag && gegevens.bericht && gegevens.bericht_uitleg && (
            <p className="zacht mt-1 max-w-[var(--maat-tekst)] text-[13.5px]" data-bericht>{gegevens.bericht_uitleg}</p>
          )}
          {/* een verbeterde spelfout (PLAN #34.2i): de pagina zegt wat ze deed; de vraag in het veld blijft wat je typte */}
          {a.vraag && gegevens.verbeterd && (
            <p className="zacht mt-1 text-[13.5px]">{tekst.zoek_niets_voor} <q>{a.vraag}</q>. {tekst.zoek_resultaten_voor} <q>{gegevens.verbeterd}</q>.</p>
          )}
          {/* een land, redactie, thema of onderdeel in de vraag verruimde (SPECS E9.S14 AC3): zeggen wat we lazen */}
          {a.vraag && gegevens.gelezen?.length > 0 && (
            <p className="zacht mt-1 max-w-[var(--maat-tekst)] text-[13.5px]">{gegevens.gelezen.map((g) => g.tekst).join(' ')}{' '}
              <button type="button" className="text-[var(--accent)] underline-offset-2 hover:underline" onClick={() => a.zoek(a.vraag, undefined, true)}>{tekst.zoek_alleen_woorden}</button></p>
          )}
        </div>
      </div>

      <div className="grid gap-6 md:grid-cols-[16rem_minmax(0,1fr)]">
        <aside ref={filterPaneel} className="filterkolom max-md:hidden" aria-label={tekst.filters_kop}><Filters f={f} kies={a.kies} tekst={tekst} plek="kolom" vastSoorten={vastSoorten} /></aside>

        <section ref={lijstKolom} className="min-w-0" aria-busy={a.bezig}>
          {/* zoeken en sorteren op één rij boven de lijst, naast het filterpaneel (PLAN #34.2bg); op een telefoon het veld
              over de hele breedte, daaronder Filteren en Sorteren op */}
          <div className="flex flex-wrap items-center gap-2 pb-3" data-rij="zoeken">
            <div className="min-w-0 max-md:basis-full md:flex-1">
              <Zoekveld id="bieb-q" taal={taal} tekst={tekst.zoek} lijst={lijst} actie={actie} begin={a.vraag}
                        opZoek={(q, thema) => a.zoek(q, thema)} label={tekst.zoek_label} hint={tekst.held_hint} knop={tekst.zoek_knop} />
            </div>
            <button type="button" className="knop md:hidden" onClick={openLade}>{tekst.filteren}{stukjes.length ? ` (${stukjes.length})` : ''}</button>
            <div className="ms-auto"><Sorteren kop={tekst.sorteer_op} opties={f.volgordes} waarde={f.volgordes.find((v) => v.aan)?.waarde ?? ''} kies={a.sorteer} /></div>
          </div>
          {stukjes.length > 0 && (
            <div className="flex flex-wrap items-center gap-2 pb-3 max-md:hidden">
              {stukjes.map((s) => (
                <button key={`${s.soort}-${s.naam}`} type="button" className="knop" onClick={() => a.weg(s)}>
                  <span className="text-[var(--zacht)]">{s.kop}:</span> {s.naam} <span aria-hidden="true">×</span><span className="sr-only"> {tekst.chip_weg}</span></button>
              ))}
              <button type="button" className="knop knop-stil" onClick={a.wis}>{tekst.filter_wis}</button>
            </div>
          )}
          {/* een paar thema's als snelle keuze, alleen op een telefoon: breed staan ze al in de filterkolom links (#34.2bq) */}
          {stukjes.length === 0 && !vastSoorten.has('thema') && f.promotie.length > 0 && (
            <div className="-mx-1 flex gap-1.5 overflow-x-auto px-1 pb-3 md:hidden" aria-label={tekst.themas_kop} data-rij="themas">
              {f.promotie.map((p) => (
                <button key={p.waarde} type="button" className="knop" onClick={() => a.kies('thema', p.waarde)}>
                  <ThemaTegel thema={p.waarde} />{p.naam} <span className="getal text-[11.5px] text-[var(--zwak)]">{p.aantal}</span></button>
              ))}
            </div>
          )}
          {gegevens.ingangen?.length > 0 && (
            <div className="paneel mb-3 flex flex-wrap items-center gap-2 px-3 py-2">
              <span className="text-[12px] font-semibold text-[var(--zacht)]">{tekst.ingang_kop}</span>
              {gegevens.ingangen.map((i) => <a key={i.href} className="knop" href={naarSite(i.href)}>{i.naam}</a>)}
            </div>
          )}

          <ol className="rijen">{rijen.map((r) => <Rij key={r.nummer} r={r} bijKlik={() => bewaarPlek()} />)}</ol>
          {rijen.length === 0 && (
            <div className="paneel">
              <div className="grid gap-3 p-6">
                <p className="text-[15px] font-medium">{a.vraag ? tekst.zoek_niets : tekst.lijst_leeg}</p>
                {gegevens.zonder_filters && <button type="button" className="knop w-fit" onClick={a.wis}>{gegevens.zonder_filters}</button>}
                {/* niets vinden is geen oordeel (SPECS E9.S14 AC7) */}
                {a.vraag && <p>{tekst.zoek_niets_klopt}</p>}
                {/* wat erin zit en wie nog ontbreekt (PLAN #34.2az, E9.S25) */}
                {a.vraag && gegevens.dekking?.length > 0 && <p className="zacht">{gegevens.dekking.join(' ')}</p>}
                <p className="zacht">{tekst.zoek_tip}</p>
                <div className="flex flex-wrap gap-1.5">{f.lijsten.thema.slice(0, 6).map((k) => <a key={k.waarde} className="knop" href={`${lijst}?thema=${k.waarde}`}><ThemaTegel thema={k.waarde} />{k.naam}</a>)}</div>
                {/* wegen verder, ook als er niets te tellen valt (SPECS E9.S12 AC6, E9.S14 AC7) */}
                {a.vraag && (
                  <div className="flex flex-wrap gap-1.5">
                    <a className="knop" href={lijst}>{tekst.lijst_titel}</a><a className="knop" href={pad(taal, 'themes')}>{tekst.themas_kop}</a>
                    <a className="knop" href={pad(taal, 'dossiers')}>{tekst.nav_dossiers}</a><a className="knop" href={pad(taal, 'names')}>{tekst.nav_namen}</a>
                  </div>
                )}
              </div>
            </div>
          )}
          {rijen.length > 0 && (
            <div className="flex flex-col items-center gap-2 pt-4">
              <p className="mono">{tekst.getoond.replace('{n}', rijen.length.toLocaleString(LOCALE[taal])).replace('{totaal}', gegevens.aantal)}</p>
              {/* een gewone link naar het volgende blad, zodat ook een zoekmachine verder kan; met script komen de rijen erbij
                  (DESIGNSYSTEEM §6). Bij een zoekvraag een knop: die staat in geen adres. */}
              {rijen.length < totaal && (a.vraag
                ? <button type="button" className="knop knop-groot" onClick={meer} disabled={laadt}>{laadt ? tekst.laden : tekst.meer_laden}</button>
                : <a className="knop knop-groot" aria-disabled={laadt || undefined}
                     href={`${lijst}?${new URLSearchParams([...vast, ...a.paren.filter(([k]) => k !== 'p'), ['p', String((gegevens.blad ?? 1) + 1)]])}`}
                     onClick={(e) => { e.preventDefault(); if (!laadt) meer(); }}>{laadt ? tekst.laden : tekst.meer_laden}</a>)}
            </div>
          )}
        </section>
      </div>

      <Lade open={lade} zetOpen={zetLade} titel={tekst.filteren} sluiten={tekst.sluiten}
            voet={<>
              <button type="button" className="knop flex-1" onClick={async () => { const g = await a.proef([]); if (g) zetConcept(g); }}>{tekst.wis_alles}</button>
              <button type="button" className="knop knop-primair flex-[2]" onClick={() => { if (concept) a.toon(concept); zetLade(false); }}>
                {tekst.toon.replace('{n}', concept?.aantal ?? gegevens.aantal)}</button>
            </>}>
        {concept && <Filters f={concept.filters} kies={kiesInLade} tekst={tekst} plek="lade" vastSoorten={vastSoorten} />}
      </Lade>
    </div>
  );
}
