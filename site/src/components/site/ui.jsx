// De bouwstenen van de site (PLAN #34.2b), naar shadcn/ui op Radix: de keuzelijst voor sorteren en de lade.
import * as SelectPrimitive from '@radix-ui/react-select';
import * as DialogPrimitive from '@radix-ui/react-dialog';

export const Pijl = () => (
  <svg viewBox="0 0 16 16" className="size-3.5 text-[var(--zwak)]" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true">
    <path d="M4 6l4 4 4-4" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);
export const Vink = () => (
  <svg viewBox="0 0 16 16" className="keuze-vink size-4" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
    <path d="M3.5 8.5l3 3 6-7" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);

// Sorteren als keuzelijst, met "Sorteren op:" ernaast en de keuze zichtbaar (#514, #521).
export function Sorteren({ kop, opties, waarde, kies }) {
  const gekozen = opties.find((o) => o.waarde === waarde) ?? opties[0];
  return (
    <div className="flex items-center gap-2">
      <span className="text-[13px] text-[var(--zacht)]" id="sorteer-kop">{kop}</span>
      <SelectPrimitive.Root value={gekozen?.waarde || '_'} onValueChange={(w) => kies(w === '_' ? '' : w)}>
        <SelectPrimitive.Trigger className="knop" aria-labelledby="sorteer-kop">
          <SelectPrimitive.Value>{gekozen?.naam}</SelectPrimitive.Value><Pijl />
        </SelectPrimitive.Trigger>
        <SelectPrimitive.Portal>
          <SelectPrimitive.Content className="fz-keuzes" position="popper" sideOffset={6} align="end">
            <SelectPrimitive.Viewport>
              {opties.map((o) => (
                <SelectPrimitive.Item key={o.waarde || '_'} value={o.waarde || '_'} className="fz-keuze">
                  <SelectPrimitive.ItemText>{o.naam}</SelectPrimitive.ItemText>
                  <SelectPrimitive.ItemIndicator className="keuze-vink"><Vink /></SelectPrimitive.ItemIndicator>
                </SelectPrimitive.Item>
              ))}
            </SelectPrimitive.Viewport>
          </SelectPrimitive.Content>
        </SelectPrimitive.Portal>
      </SelectPrimitive.Root>
    </div>
  );
}

// Een lade van onderen (telefoon): een kruisje, de inhoud, en onderaan vast wat de lade afsluit (#1125).
export function Lade({ open, zetOpen, titel, children, voet, sluiten = 'Sluiten' }) {
  return (
    <DialogPrimitive.Root open={open} onOpenChange={zetOpen}>
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className="fz-overlay" />
        <DialogPrimitive.Content className="fz-lade" aria-describedby={undefined}>
          <div className="flex items-center justify-between border-b border-[var(--lijn)] px-4 py-2">
            <DialogPrimitive.Title className="text-[15px] font-semibold">{titel}</DialogPrimitive.Title>
            <DialogPrimitive.Close className="knop knop-stil" aria-label={sluiten}>
              <svg viewBox="0 0 16 16" className="size-4" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true"><path d="M4 4l8 8M12 4l-8 8" strokeLinecap="round" /></svg>
            </DialogPrimitive.Close>
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto px-4 pb-4">{children}</div>
          <div className="flex gap-2 border-t border-[var(--lijn)] px-4 py-3">{voet}</div>
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  );
}
