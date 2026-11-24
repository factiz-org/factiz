// De vraag of we mogen meten (B88, SPECS E9.S36): onderaan elke pagina tot de bezoeker kiest, met ja en nee even groot en
// even makkelijk. Na ja laadt Google Analytics; na nee niets, en een eerdere ja wordt gewist. In de voet een knop om de
// keuze opnieuw te maken. De keuze blijft op het apparaat en geldt een jaar (`meten.js`). Subtiel (PO 2026-11-24): een
// kleine kaart, op een groter scherm in de hoek, zonder grijze laag; zolang ze er staat, krijgt de pagina onderaan zo veel
// ruimte als de kaart hoog is, zodat het einde van de pagina en wat de focus heeft er nooit onder verdwijnen (WCAG 2.4.11).
import { useEffect, useRef, useState } from 'react';
import { keuze, bewaar, laadAnalytics, wisAnalytics } from '../../lib/meten.js';

export default function Meten({ id, tekst }) {
  const [stand, zetStand] = useState('laden');
  const kaart = useRef(null);

  useEffect(() => {
    const k = keuze();
    zetStand(k ?? 'vraag');
    if (k === 'ja') laadAnalytics(id);
  }, [id]);

  useEffect(() => {
    const el = kaart.current;
    if (stand !== 'vraag' || !el) return undefined;
    const html = document.documentElement;
    const meet = () => {
      const onder = parseFloat(getComputedStyle(el).bottom) || 0;
      html.style.setProperty('--fz-meten-ruimte', `${Math.ceil(el.getBoundingClientRect().height + onder)}px`);
    };
    meet();
    html.classList.add('fz-meten-open');
    const kijker = typeof ResizeObserver === 'function' ? new ResizeObserver(meet) : null;
    kijker?.observe(el);
    return () => {
      kijker?.disconnect();
      html.classList.remove('fz-meten-open');
      html.style.removeProperty('--fz-meten-ruimte');
    };
  }, [stand]);

  function kies(k) {
    bewaar(k);
    zetStand(k);
    if (k === 'ja') laadAnalytics(id);
    else wisAnalytics(id);
  }

  return (
    <>
      <button type="button" className="link fz-meten-aanpassen text-[13px]" onClick={() => zetStand('vraag')}>{tekst.aanpassen}</button>
      {stand === 'vraag' && (
        <div ref={kaart} className="fz-meten" role="dialog" aria-modal="false" aria-labelledby="fz-meten-vraag">
          <p id="fz-meten-vraag">
            {tekst.vraag} <a className="link" href={tekst.meerHref}>{tekst.meer}</a>
          </p>
          <div className="flex gap-2">
            <button type="button" className="knop fz-meten-knop" onClick={() => kies('ja')}>{tekst.ja}</button>
            <button type="button" className="knop fz-meten-knop" onClick={() => kies('nee')}>{tekst.nee}</button>
          </div>
        </div>
      )}
    </>
  );
}
