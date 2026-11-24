// Het zoekvenster van de site (PLAN #34.2b): overal te openen met Ctrl of Cmd+K of /, met dezelfde suggesties en
// dezelfde toetsen als elk zoekveld (`zoeken.jsx`, #34.2ac): groepen, pijltjes die rondlopen en een zoekvraag
// overnemen, en het woord dat je typt grijs afgemaakt, over te nemen met Tab. Zoeken gaat met een gepost formulier naar
// de bibliotheek: de vraag staat nooit in een adres. Zonder script werkt de knop als link naar de bibliotheek.
import { useEffect, useMemo, useRef, useState } from 'react';
import * as DialogPrimitive from '@radix-ui/react-dialog';
import { Loep, SuggestieLijst, Spook, regelsVan, restVan, useSamenstellen, useSuggesties, useToetsen, zoekNaar } from './zoeken.jsx';

export default function Zoekpalet({ tekst, themas, taal, lijst }) {
  const [open, zetOpen] = useState(false);
  const [vraag, zetVraag] = useState('');
  const invoer = useRef(null);
  const { s, stil } = useSuggesties(taal, vraag);
  const { samenstellen, opties } = useSamenstellen();

  useEffect(() => {
    const toets = (e) => {
      const typt = /^(input|textarea|select)$/i.test(e.target?.tagName ?? '') || e.target?.isContentEditable;
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); zetOpen((o) => !o); }
      else if (e.key === '/' && !typt) { e.preventDefault(); zetOpen(true); }
    };
    window.addEventListener('keydown', toets);
    return () => window.removeEventListener('keydown', toets);
  }, []);

  const regels = useMemo(() => regelsVan(vraag.trim().length >= 2 ? s : null, { themas, lijst }), [s, vraag, themas, lijst]);
  const rest = restVan(s, vraag, samenstellen);

  function kies(r) {
    if (!r) { if (vraag.trim()) zoekNaar(lijst, vraag.trim()); return; }
    if (r.soort === 'zoek') zoekNaar(lijst, r.tekst, { thema: r.thema });
    else location.href = r.href;
  }
  const { actief, zetActief, toets } = useToetsen({ regels, waarde: vraag, zetWaarde: zetVraag, stil, kies, rest });

  return (
    <DialogPrimitive.Root open={open} onOpenChange={(o) => { zetOpen(o); if (!o) zetVraag(''); }}>
      <DialogPrimitive.Trigger asChild>
        {/* op een telefoon het korte woord, en in een knop te smal voor een woord alleen de loep (2026-11-17: op 320 px stond er "S.") */}
        <a className="zoekknop @container" href={lijst} onClick={(e) => { e.preventDefault(); zetOpen(true); }} aria-label={tekst.knop}>
          {/* zonder woord staat de loep in het midden; met een woord neemt het woord de ruimte (PLAN #34.2ci) */}
          <Loep className="size-4 shrink-0 mx-auto" /><span className="min-w-0 flex-1 truncate text-start max-sm:hidden" aria-hidden="true">{tekst.knop}</span>
          <span className="min-w-0 flex-1 truncate text-start @max-[4.5rem]:hidden sm:hidden" aria-hidden="true">{tekst.kort ?? tekst.knop}</span><kbd className="max-sm:hidden" aria-hidden="true">⌘K</kbd>
        </a>
      </DialogPrimitive.Trigger>
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className="fz-overlay" />
        <DialogPrimitive.Content className="fz-venster" aria-describedby={undefined}>
          <DialogPrimitive.Title className="sr-only">{tekst.titel}</DialogPrimitive.Title>
          <form role="search" className="relative flex items-center gap-2 border-b border-[var(--lijn)] px-3" onSubmit={(e) => { e.preventDefault(); if (!samenstellen) kies(regels[actief]); }}>
            <Loep className="size-4 text-[var(--zwak)]" />
            <input ref={invoer} autoFocus dir="auto" {...opties} className="h-12 min-w-0 flex-1 bg-transparent text-[15px] pointer-coarse:text-[16px] outline-none placeholder:text-[var(--zwak)]" value={vraag}
                   onChange={(e) => zetVraag(e.target.value)} onKeyDown={toets} placeholder={tekst.hint} aria-label={tekst.titel}
                   role="combobox" aria-expanded={regels.length > 0} aria-controls="palet-lijst" aria-autocomplete="both"
                   aria-activedescendant={actief >= 0 ? `palet-lijst-${actief}` : undefined}
                   autoComplete="off" spellCheck="false" enterKeyHint="search" maxLength={1000} />
            <Spook invoer={invoer} waarde={vraag} rest={rest} />
            <kbd aria-hidden="true">Esc</kbd>
          </form>
          <SuggestieLijst id="palet-lijst" regels={regels} actief={actief} zetActief={zetActief} kies={kies} tekst={tekst} waarde={vraag} s={vraag.trim().length >= 2 ? s : null} />
          <div className="flex items-center gap-4 border-t border-[var(--lijn)] px-4 py-2 text-[12px] text-[var(--zwak)] pointer-coarse:hidden">
            <span><kbd>↑</kbd> <kbd>↓</kbd> {tekst.kiezen}</span><span className="max-sm:hidden"><kbd>Tab</kbd> {tekst.aanvullen}</span>
            <span><kbd>Enter</kbd> {tekst.openen}</span>
            <span className="ms-auto max-sm:hidden">{tekst.privacy}</span>
          </div>
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  );
}
