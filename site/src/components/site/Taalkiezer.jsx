// De taalkiezer van de site (PLAN #34.2c, #34.2af, DESIGNSYSTEEM §6): in de hoofdnavigatie, op elke breedte. Een
// wereldbol met de code van de huidige taal en een pijltje; per regel de code en de naam in de eigen taal, geen vlaggen
// (W3C); elke keuze een gewone link naar
// dezelfde pagina in die taal, met hreflang en lang. Vanaf negen talen een zoekveld, dat ook zoekt op de code en op de
// naam in de taal van de pagina. Zonder script staat dezelfde lijst in de voet.
// De volgorde is op elke pagina dezelfde (`KIESVOLGORDE`, de server zet haar); bovenaan *Voorgesteld*, de talen die de
// browser zelf noemt, pas na het laden gelezen en nergens bewaard (PLAN #34.2bi, B78).
import { useEffect, useMemo, useRef, useState } from 'react';
import { Pijl, Vink } from './ui.jsx';
import { voorstel } from '../../lib/taalvoorstel.js';

const ZOEKEN_VANAF = 9;

const Bol = () => (
  <svg viewBox="0 0 16 16" className="size-4" fill="none" stroke="currentColor" strokeWidth="1.4" aria-hidden="true">
    <circle cx="8" cy="8" r="6.25" /><path d="M1.75 8h12.5M8 1.75c1.9 2 2.75 4 2.75 6.25S9.9 12.25 8 14.25C6.1 12.25 5.25 10.25 5.25 8S6.1 3.75 8 1.75Z" />
  </svg>
);

function Keuze({ l, taal }) {
  return (
    <li>
      <a className="fz-keuze" href={l.href} hrefLang={l.bcp47} lang={l.bcp47} aria-current={l.code === taal ? 'true' : undefined}>
        <span className="code" aria-hidden="true">{l.code.toUpperCase()}</span>
        <span className="taalnaam min-w-0 flex-1 truncate">{l.naam}</span>
        {l.code === taal && <Vink />}
      </a>
    </li>
  );
}

// talen: [{ code, naam (in de eigen taal), hier (in de taal van de pagina), href }], in de vaste volgorde
// Een knop die een lijst links uitklapt (het patroon "disclosure" van W3C): werkt met muis, tik en toetsenbord; Escape of
// ernaast klikken sluit hem, en de focus gaat terug naar de knop.
export default function Taalkiezer({ taal, talen, tekst }) {
  const [open, zetOpen] = useState(false);
  const [zoek, zetZoek] = useState('');
  const knop = useRef(null);
  const paneel = useRef(null);
  const [browser, zetBrowser] = useState([]);
  const huidig = talen.find((l) => l.code === taal);
  const q = zoek.trim().toLowerCase();
  const lijst = useMemo(
    () => (q ? talen.filter((l) => [l.naam, l.hier, l.code].some((w) => w.toLowerCase().includes(q))) : talen),
    [talen, q],
  );
  // de talen van de browser, na het laden: de pagina van de server blijft voor iedereen gelijk
  useEffect(() => {
    const codes = voorstel(navigator.languages ?? [navigator.language], talen.map((l) => l.code), taal);
    zetBrowser(codes.map((c) => talen.find((l) => l.code === c)).filter(Boolean));
  }, [talen, taal]);
  const voorgesteld = q ? [] : browser;
  useEffect(() => {
    if (!open) return undefined;
    const buiten = (e) => { if (!paneel.current?.contains(e.target) && !knop.current?.contains(e.target)) zetOpen(false); };
    const toets = (e) => { if (e.key === 'Escape') { zetOpen(false); knop.current?.focus(); } };
    document.addEventListener('pointerdown', buiten);
    document.addEventListener('keydown', toets);
    return () => { document.removeEventListener('pointerdown', buiten); document.removeEventListener('keydown', toets); };
  }, [open]);
  return (
    <div className="relative">
      <button ref={knop} type="button" className="navlink gap-1.5" aria-expanded={open} aria-controls="taalkiezer"
              aria-label={tekst.knop.replace('{taal}', huidig?.naam ?? taal)} onClick={() => zetOpen((o) => !o)}>
        <Bol /><span className="getal text-[12px] uppercase">{taal}</span><Pijl />
      </button>
      <nav ref={paneel} id="taalkiezer" hidden={!open} aria-label={tekst.taalkeuze}
           className="fz-keuzes absolute top-[calc(100%+6px)] end-0 z-40 w-[14rem] max-w-[calc(100vw-2rem)]">
        {talen.length >= ZOEKEN_VANAF && (
          <input className="invoer mb-1" type="search" dir="auto" value={zoek} onChange={(e) => zetZoek(e.target.value)}
                 placeholder={tekst.zoeken} aria-label={tekst.zoeken} autoComplete="off" />
        )}
        {voorgesteld.length > 0 && (
          <>
            <p className="fz-keuzes-kop" id="taal-voorgesteld">{tekst.voorgesteld}</p>
            <ul className="grid gap-0.5" aria-labelledby="taal-voorgesteld">{voorgesteld.map((l) => <Keuze key={l.code} l={l} taal={taal} />)}</ul>
            <p className="fz-keuzes-kop" id="taal-alle">{tekst.alle}</p>
          </>
        )}
        <ul className="grid gap-0.5" aria-labelledby={voorgesteld.length > 0 ? 'taal-alle' : undefined}>
          {lijst.map((l) => <Keuze key={l.code} l={l} taal={taal} />)}
        </ul>
        {lijst.length === 0 && <p className="px-2 py-3 text-[13px] text-[var(--zacht)]">{tekst.niets}</p>}
      </nav>
    </div>
  );
}
