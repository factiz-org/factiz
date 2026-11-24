// Een zoekveld op de pagina zelf (PLAN #34.2ac, SPECS E9.S14 AC1, AC2): het grote veld op de start en het veld boven de
// lijst, met dezelfde suggesties en toetsen als het zoekvenster. De lijst hangt onder het veld, in een laag boven de
// pagina (de band van de start knipt wat eruit steekt). Zonder script is het een gewoon formulier dat de vraag post.
import { useEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { Loep, SuggestieLijst, Spook, regelsVan, restVan, useSamenstellen, useSuggesties, useToetsen, zoekNaar } from './zoeken.jsx';

export default function Zoekveld({ id, taal, tekst, lijst, actie, begin = '', groot = false, opZoek, label, hint, knop }) {
  const [waarde, zetWaarde] = useState(begin);
  const [open, zetOpen] = useState(false);
  const [plek, zetPlek] = useState(null);
  const invoer = useRef(null);
  const vak = useRef(null);
  const { s, stil } = useSuggesties(taal, open ? waarde : '');
  const { samenstellen, opties } = useSamenstellen();

  useEffect(() => { zetWaarde(begin); }, [begin]);

  const regels = useMemo(() => (open && s && waarde.trim().length >= 2 ? regelsVan(s, { lijst }) : []), [open, s, waarde, lijst]);
  const rest = open ? restVan(s, waarde, samenstellen) : '';
  const lijstId = `${id}-lijst`;

  // de lijst staat in een laag boven de pagina, onder het hele zoekvak (op een telefoon is het veld zelf te smal)
  useEffect(() => {
    if (!regels.length) return undefined;
    const zet = () => {
      const r = vak.current?.getBoundingClientRect();
      if (r) zetPlek({ left: r.left + scrollX, top: r.bottom + scrollY + 6, width: r.width });
    };
    zet();
    addEventListener('resize', zet);
    addEventListener('scroll', zet, { passive: true });
    return () => { removeEventListener('resize', zet); removeEventListener('scroll', zet); };
  }, [regels.length]);

  function zoek(q, thema) {
    if (!q) return;
    zetOpen(false);
    if (opZoek) opZoek(q, thema);
    else zoekNaar(lijst, q, { thema });
  }
  function kies(r) {
    if (!r) { zoek(waarde.trim()); return; }
    if (r.soort === 'zoek') { stil.current = true; zetWaarde(r.tekst); zoek(r.tekst, r.thema); }
    else location.href = r.href;
  }
  const { actief, zetActief, toets } = useToetsen({
    regels, waarde, zetWaarde, stil, kies, rest, sluit: () => { if (!open || !regels.length) return false; zetOpen(false); return true; },
  });

  const invoerKlasse = groot
    ? 'h-11 min-w-0 w-full bg-transparent text-[15px] pointer-coarse:text-[16px] text-[#171717] outline-none placeholder:text-[#8b908d]'
    : 'invoer';
  return (
    <form ref={vak} role="search" method="post" action={actie} onSubmit={(e) => { e.preventDefault(); if (!samenstellen) kies(regels[actief]); }}
          className={groot
            ? 'mt-7 flex max-w-[36rem] items-center gap-2 rounded-[10px] bg-white p-1.5 ps-3 text-[#171717] shadow-[0_10px_30px_-10px_rgb(0_0_0/.5)]'
            : 'flex w-full max-w-[26rem] gap-2'}>
      {groot && <Loep className="size-4 flex-none text-[#8b908d]" />}
      <label htmlFor={id} className="sr-only">{label}</label>
      <div className="relative min-w-0 flex-1">
        <input ref={invoer} id={id} name="q" type="search" dir="auto" {...opties} className={invoerKlasse} value={waarde} placeholder={hint}
               onChange={(e) => { zetWaarde(e.target.value); zetOpen(true); }} onFocus={() => zetOpen(true)}
               onBlur={() => zetOpen(false)} onKeyDown={toets}
               role="combobox" aria-expanded={regels.length > 0} aria-controls={lijstId} aria-autocomplete="both"
               aria-activedescendant={actief >= 0 ? `${lijstId}-${actief}` : undefined}
               autoComplete="off" spellCheck="false" enterKeyHint="search" maxLength={1000} />
        <Spook invoer={invoer} waarde={waarde} rest={rest} />
      </div>
      <button className={groot ? 'h-11 rounded-[7px] bg-[#171717] px-4 text-[14px] font-medium text-white' : 'knop'} type="submit">{knop}</button>
      {regels.length > 0 && plek && createPortal(
        <div className="fz-zoeklaag" style={{ left: plek.left, top: plek.top, width: plek.width }}>
          <SuggestieLijst id={lijstId} regels={regels} actief={actief} zetActief={zetActief} kies={kies} tekst={tekst} waarde={waarde} s={s} />
          <p className="fz-zoeklaag-voet"><span><kbd>↑</kbd> <kbd>↓</kbd> {tekst.kiezen}</span>
            {rest && <span><kbd>Tab</kbd> {tekst.aanvullen}</span>}<span><kbd>Enter</kbd> {tekst.openen}</span></p>
        </div>, document.body)}
    </form>
  );
}
