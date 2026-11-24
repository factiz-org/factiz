// Wat het zoekvenster en de zoekvelden van de site delen (PLAN #34.2b, #34.2ac, SPECS E9.S14): suggesties tijdens het
// typen in groepen (zoekvragen, pagina's, factchecks; hoogstens 10, #359, #356), wat je typte gewoon en wat erbij komt vet
// (#404), pijltjes die rondlopen en een zoekvraag in het veld overnemen (#369), en het woord dat je typt grijs afgemaakt,
// over te nemen met Tab of het pijltje naar rechts (AC2). De vraag gaat in het bericht naar het platform en wordt
// nergens bewaard; zoeken gaat met een gepost formulier, nooit met de vraag in een adres.
import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { Tekst } from '../../lib/archief.jsx';
import { naarSite } from '../../lib/talen.js';
import ThemaTegel from './ThemaTegel.jsx';

export function zoekNaar(lijst, vraag, { thema, letterlijk } = {}) {
  const form = document.createElement('form');
  form.method = 'post';
  form.action = `${lijst}${thema ? `?thema=${encodeURIComponent(thema)}` : ''}`;
  for (const [naam, waarde] of [['q', vraag], ...(letterlijk ? [['letterlijk', '1']] : [])]) {
    form.append(Object.assign(document.createElement('input'), { type: 'hidden', name: naam, value: waarde }));
  }
  document.body.append(form);
  form.submit();
}

export const Loep = ({ className = 'size-4' }) => (
  <svg viewBox="0 0 16 16" className={className} fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true"><circle cx="7" cy="7" r="4.5" /><path d="M10.5 10.5 14 14" strokeLinecap="round" /></svg>
);

// De suggesties bij wat er nu in het veld staat, met een korte pauze na het typen; een ouder antwoord telt niet meer.
// `stil` slaat één keer ophalen over: na een overgenomen suggestie (#369) blijft de lijst staan.
export function useSuggesties(taal, vraag) {
  const [s, zetS] = useState(null);
  const volg = useRef(0);
  const stil = useRef(false);
  useEffect(() => {
    if (stil.current) { stil.current = false; return undefined; }
    if (vraag.trim().length < 2) { volg.current += 1; zetS(null); return undefined; }
    const nummer = ++volg.current;
    const wacht = setTimeout(async () => {
      try {
        const r = await fetch(`/${taal}/api/suggesties`, { method: 'POST', body: new URLSearchParams([['q', vraag]]) });
        if (r.ok && nummer === volg.current) zetS({ ...(await r.json()), voor: vraag });
      } catch { /* geen suggesties: het veld werkt gewoon als formulier */ }
    }, 110);
    return () => clearTimeout(wacht);
  }, [vraag, taal]);
  return { s, stil };
}

export function regelsVan(s, { themas = [], lijst }) {
  if (!s) return themas.map((th) => ({ soort: 'thema', naam: th.naam, rechts: th.aantal, thema: th.waarde, href: `${lijst}?thema=${th.waarde}` }));
  return [
    ...s.zoekvragen.map((z) => ({ soort: 'zoek', tekst: z.tekst, thema: z.thema, themaNaam: z.thema_naam, rechts: z.aantal, verbeterd: z.verbeterd })),
    ...s.ingangen.map((i) => ({ soort: 'ingang', naam: i.naam, label: i.soort_tekst, rechts: i.aantal, href: naarSite(i.href) })),
    ...s.factchecks.map((f) => ({ soort: 'factcheck', stukken: f.stukken, label: f.label, stempel: f.stempel, labelSoort: f.soort,
                                  href: naarSite(f.href) })),
  ].slice(0, 10);
}

// Wat de grijze aanvulling erbij zet: alleen als het antwoord bij precies deze invoer hoort.
// tekst van rechts naar links (Hebreeuws, Arabisch, Perzisch): de grijze aanvulling past daar niet achter de cursor
const RTL_TEKEN = /[\u0590-\u08ff\ufb1d-\ufdff\ufe70-\ufefc]/;

export function restVan(s, waarde, samenstellen = false) {
  if (samenstellen || RTL_TEKEN.test(waarde)) return '';
  if (!s?.aanvulling || s.voor !== waarde || !s.aanvulling.startsWith(waarde)) return '';
  return s.aanvulling.slice(waarde.length);
}

// De toetsen van een zoekveld met suggesties. Tab en → aan het eind nemen de grijze aanvulling over; zonder aanvulling
// doet Tab wat het altijd doet (niemand zit vast in het veld). ↑ en ↓ lopen rond en nemen een zoekvraag over (#369).
// Een invoermethode (Chinees, Japans, Koreaans, ook Vietnamees) stelt een teken samen met Enter, de pijltjes en Tab:
// zolang dat duurt, zijn die toetsen van haar, en zoekt Enter niet (PO 2026-11-15: "ondersteunen elk toetsenbord").
export function useSamenstellen() {
  const [samenstellen, zet] = useState(false);
  return { samenstellen, opties: { onCompositionStart: () => zet(true), onCompositionEnd: () => zet(false) } };
}

export function useToetsen({ regels, waarde, zetWaarde, stil, kies, rest, sluit }) {
  const [actief, zetActief] = useState(-1);
  useEffect(() => { zetActief(-1); }, [regels]);
  function toets(e) {
    if (e.nativeEvent?.isComposing || e.keyCode === 229) return;     // een teken in samenstelling
    const aanEind = e.currentTarget.selectionStart === waarde.length && e.currentTarget.selectionEnd === waarde.length;
    if ((e.key === 'Tab' && !e.shiftKey && !e.altKey && !e.ctrlKey && !e.metaKey) || (e.key === 'ArrowRight' && aanEind)) {
      if (rest) { e.preventDefault(); zetWaarde(waarde + rest); }
      return;
    }
    if (e.key === 'Escape' && sluit?.()) { e.preventDefault(); return; }
    if (!regels.length) return;
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault();
      const n = regels.length;
      const volgend = e.key === 'ArrowDown' ? (actief + 1) % n : (actief <= 0 ? n - 1 : actief - 1);
      zetActief(volgend);
      const r = regels[volgend];
      if (r.soort === 'zoek' && !r.thema) { stil.current = true; zetWaarde(r.tekst); }
    } else if (e.key === 'Enter' && actief >= 0) { e.preventDefault(); kies(regels[actief]); }
  }
  return { actief, zetActief, toets };
}

// Een zoekvraag in de lijst: wat je typte gewoon, wat erbij komt vet (#404). Een verbeterde spelfout helemaal vet.
function Aangevuld({ tekst, getypt, verbeterd }) {
  const voor = getypt.trim().toLocaleLowerCase();
  if (verbeterd || !voor || !tekst.toLocaleLowerCase().startsWith(voor)) return <b className="font-semibold">{tekst}</b>;
  return <><span>{tekst.slice(0, voor.length)}</span><b className="font-semibold">{tekst.slice(voor.length)}</b></>;
}

export function SuggestieLijst({ id, regels, actief, zetActief, kies, tekst, waarde, s }) {
  const groepen = [
    ['zoek', tekst.groep_zoeken], ['ingang', tekst.groep_ingangen], ['factcheck', tekst.groep_factchecks], ['thema', tekst.groep_themas],
  ];
  let i = -1;
  return (
    <div id={id} role="listbox" aria-label={tekst.titel} className="max-h-[min(70vh,34rem)] overflow-y-auto">
      {groepen.map(([soort, kop]) => {
        const deze = regels.filter((r) => r.soort === soort);
        if (!deze.length) return null;
        return (
          <div key={soort} className="fz-palet-groep" role="group" aria-label={kop}>
            <p className="fz-palet-kop">{kop}</p>
            {deze.map((r) => {
              i += 1;
              const plek = i;
              return (
                <div key={plek} id={`${id}-${plek}`} role="option" aria-selected={plek === actief} className="fz-palet-regel"
                     onMouseEnter={() => zetActief(plek)} onMouseDown={(e) => e.preventDefault()} onClick={() => kies(r)}>
                  {r.soort === 'zoek' && <><Loep className="size-3.5 flex-none text-[var(--zwak)]" />
                    <span className="min-w-0 truncate"><Aangevuld tekst={r.tekst} getypt={waarde} verbeterd={r.verbeterd} />
                      {r.themaNaam && <span className="aanvulling"> {tekst.in} {r.themaNaam}</span>}</span></>}
                  {r.soort === 'ingang' && <><span className="label">{r.label}</span><span className="min-w-0 truncate font-medium">{r.naam}</span></>}
                  {r.soort === 'factcheck' && <span className="min-w-0 truncate"><Tekst stukken={r.stukken} /></span>}
                  {r.soort === 'thema' && <><ThemaTegel thema={r.thema} maat="midden" /><span className="truncate">{r.naam}</span></>}
                  {r.rechts && <span className="rechts">{r.rechts}</span>}
                  {/* het oordeel als stempel (PLAN #34.2cc, DESIGN §4y); wie het zegt past hier niet */}
                  {r.soort === 'factcheck' && <span className="rechts"><span className="fz-stempel" data-soort={r.labelSoort ?? 'geen'}>{r.stempel ?? r.label}</span></span>}
                </div>
              );
            })}
          </div>
        );
      })}
      {s && regels.length === 0 && <p className="px-4 py-6 text-[var(--zacht)]">{tekst.niets}</p>}
    </div>
  );
}

// De grijze aanvulling in het veld zelf: dezelfde letters en dezelfde plek als de invoer, het getypte onzichtbaar en de
// rest erachter. Alleen als de tekst in het veld past; anders zou de rest ergens anders staan dan het woord.
export function Spook({ invoer, waarde, rest }) {
  const [stijl, zetStijl] = useState(null);
  useLayoutEffect(() => {
    const el = invoer.current;
    if (!el || !rest || el.scrollWidth > el.clientWidth + 1) { zetStijl(null); return; }
    const cs = getComputedStyle(el);
    zetStijl({
      left: el.offsetLeft, top: el.offsetTop, width: el.offsetWidth, height: el.offsetHeight,
      paddingLeft: cs.paddingLeft, paddingRight: cs.paddingRight, borderStyle: 'solid', borderColor: 'transparent',
      borderLeftWidth: cs.borderLeftWidth, borderRightWidth: cs.borderRightWidth, borderTopWidth: cs.borderTopWidth,
      borderBottomWidth: cs.borderBottomWidth, fontFamily: cs.fontFamily, fontSize: cs.fontSize, fontWeight: cs.fontWeight,
      letterSpacing: cs.letterSpacing,
    });
  }, [invoer, waarde, rest]);
  if (!stijl) return null;
  return <div aria-hidden="true" className="fz-spook" style={stijl}><span className="invisible">{waarde}</span><span className="fz-spook-rest">{rest}</span></div>;
}
