// De schakelaar in de voet: Systeem, Licht, Donker (PLAN #34.2c). Standaard Systeem, dat de instelling van het apparaat
// volgt. Een keuze geldt meteen, zonder de pagina opnieuw te laden.
import { useEffect, useState } from 'react';
import * as SelectPrimitive from '@radix-ui/react-select';
import { SLEUTEL } from '../../lib/weergave.js';
import { Vink } from './ui.jsx';

const ICOON = {
  systeem: <path d="M2.5 3.5h11v7h-11zM6 13.5h4M8 10.5v3" strokeLinecap="round" strokeLinejoin="round" />,
  licht: <><circle cx="8" cy="8" r="2.75" /><path d="M8 1.5v1.5M8 13v1.5M1.5 8H3M13 8h1.5M3.4 3.4l1.06 1.06M11.54 11.54l1.06 1.06M3.4 12.6l1.06-1.06M11.54 4.46l1.06-1.06" strokeLinecap="round" /></>,
  donker: <path d="M13 9.5A5.5 5.5 0 0 1 6.5 3a5.5 5.5 0 1 0 6.5 6.5Z" strokeLinejoin="round" />,
};
const Icoon = ({ soort }) => <svg viewBox="0 0 16 16" className="size-3.5 flex-none" fill="none" stroke="currentColor" strokeWidth="1.4" aria-hidden="true">{ICOON[soort]}</svg>;

export default function Weergave({ tekst }) {
  const [keuze, zetKeuze] = useState('systeem');
  useEffect(() => { zetKeuze(document.documentElement.dataset.weergave || 'systeem'); }, []);
  function kies(w) {
    zetKeuze(w);
    if (w === 'systeem') delete document.documentElement.dataset.weergave;
    else document.documentElement.dataset.weergave = w;
    try { if (w === 'systeem') localStorage.removeItem(SLEUTEL); else localStorage.setItem(SLEUTEL, w); } catch { /* geen opslag: dan alleen deze pagina */ }
  }
  const opties = ['systeem', 'licht', 'donker'];
  // De regel bij de knop zegt waar de keuze blijft (PLAN #34.2g, WP29-advies 04/2012 §3.6): alleen op dit apparaat.
  return (
    <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
      <span className="text-[12px] font-semibold" id="weergave-kop">{tekst.kop}</span>
      <SelectPrimitive.Root value={keuze} onValueChange={kies}>
        <SelectPrimitive.Trigger className="knop" aria-labelledby="weergave-kop" aria-describedby="weergave-hier">
          <Icoon soort={keuze} /><SelectPrimitive.Value>{tekst[keuze]}</SelectPrimitive.Value>
        </SelectPrimitive.Trigger>
        <SelectPrimitive.Portal>
          <SelectPrimitive.Content className="fz-keuzes" position="popper" side="top" sideOffset={6} align="start">
            <SelectPrimitive.Viewport>
              {opties.map((w) => (
                <SelectPrimitive.Item key={w} value={w} className="fz-keuze">
                  <Icoon soort={w} /><SelectPrimitive.ItemText>{tekst[w]}</SelectPrimitive.ItemText>
                  <SelectPrimitive.ItemIndicator className="keuze-vink"><Vink /></SelectPrimitive.ItemIndicator>
                </SelectPrimitive.Item>
              ))}
            </SelectPrimitive.Viewport>
          </SelectPrimitive.Content>
        </SelectPrimitive.Portal>
      </SelectPrimitive.Root>
      <span className="w-full text-[12px] text-[var(--zwak)]" id="weergave-hier">{tekst.hier}</span>
    </div>
  );
}
