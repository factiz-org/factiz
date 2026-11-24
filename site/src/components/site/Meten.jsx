// De vraag of we mogen meten (B88, SPECS E9.S36): onderaan elke pagina tot de bezoeker kiest, met ja en nee even groot en
// even makkelijk. Na ja laadt Google Analytics; na nee niets, en een eerdere ja wordt gewist. In de voet een knop om de
// keuze opnieuw te maken. De keuze blijft op het apparaat (`meten.js`).
import { useEffect, useState } from 'react';
import { keuze, bewaar, laadAnalytics, wisAnalytics } from '../../lib/meten.js';

export default function Meten({ id, tekst }) {
  const [stand, zetStand] = useState('laden');

  useEffect(() => {
    const k = keuze();
    zetStand(k ?? 'vraag');
    if (k === 'ja') laadAnalytics(id);
  }, [id]);

  function kies(k) {
    bewaar(k);
    zetStand(k);
    if (k === 'ja') laadAnalytics(id);
    else wisAnalytics(id);
  }

  return (
    <>
      <button type="button" className="link text-[13px]" onClick={() => zetStand('vraag')}>{tekst.aanpassen}</button>
      {stand === 'vraag' && (
        <div className="fz-meten" role="dialog" aria-modal="false" aria-labelledby="fz-meten-vraag">
          <p id="fz-meten-vraag" className="text-[14px] leading-relaxed">
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
