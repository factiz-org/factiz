// Het menu van de site (PLAN #34.2b): de thema's als eerste niveau met "Alle thema's" bovenaan (#287, #1006), de huidige
// plek gemarkeerd (#300), en de links over Factiz apart (#288). Het opent meteen, zonder wachttijd bij aanwijzen en zonder
// fade (PO 2026-11-15: "deze uitklap moet instant worden"; Baymard #289 raadt 300 tot 500 ms aan). Op een telefoon dezelfde
// lijst in een lade.
import { useState } from 'react';
import * as NavigationMenu from '@radix-ui/react-navigation-menu';
import { Lade } from './ui.jsx';
import ThemaTegel from './ThemaTegel.jsx';

const Pijl = () => (
  <svg viewBox="0 0 16 16" className="size-3 opacity-60" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true"><path d="M4 6l4 4 4-4" strokeLinecap="round" strokeLinejoin="round" /></svg>
);

export default function Menu({ tekst, themas, hier, links }) {
  const [lade, zetLade] = useState(false);
  const themaLinks = (
    <ul className="grid gap-0.5 sm:grid-cols-2">
      <li className="sm:col-span-2"><a className="fz-keuze font-medium" href={links.themas}>{tekst.alle_themas}</a></li>
      {themas.map((th) => (
        <li key={th.waarde}><a className="fz-keuze" href={`${links.themas}${th.waarde}/`}>
          <ThemaTegel thema={th.waarde} maat="midden" /><span className="min-w-0 flex-1 truncate">{th.naam}</span>
          <span className="getal text-[11.5px] text-[var(--zwak)]">{th.aantal}</span></a></li>
      ))}
    </ul>
  );
  return (
    <>
      <NavigationMenu.Root delayDuration={0} className="relative hidden md:block" aria-label={tekst.menu_naam}>
        <NavigationMenu.List className="flex items-center gap-0.5">
          <NavigationMenu.Item><NavigationMenu.Link className="navlink" href={links.lijst} aria-current={hier === 'lijst' ? 'page' : undefined}>{tekst.factchecks}</NavigationMenu.Link></NavigationMenu.Item>
          <NavigationMenu.Item>
            <NavigationMenu.Trigger className="navlink">{tekst.themas} <Pijl /></NavigationMenu.Trigger>
            <NavigationMenu.Content className="fz-keuzes fz-direct absolute top-[calc(100%+6px)] start-0 w-[34rem] p-2">{themaLinks}</NavigationMenu.Content>
          </NavigationMenu.Item>
          <NavigationMenu.Item><NavigationMenu.Link className="navlink" href={links.dossier} aria-current={hier === 'dossier' ? 'page' : undefined}>{tekst.dossiers}</NavigationMenu.Link></NavigationMenu.Item>
          <NavigationMenu.Item><NavigationMenu.Link className="navlink" href={links.verkennen} aria-current={hier === 'verkennen' ? 'page' : undefined}>{tekst.verkennen}</NavigationMenu.Link></NavigationMenu.Item>
          {/* Factiz Radar, de eigen checks, met een stip in de kleur van het logo (PO 2026-11-19) */}
          {links.radar && <NavigationMenu.Item><NavigationMenu.Link className="navlink" href={links.radar} aria-current={hier === 'eigen' ? 'page' : undefined}><span className="fz-radar-stip" aria-hidden="true" />{tekst.radar}</NavigationMenu.Link></NavigationMenu.Item>}
        </NavigationMenu.List>
      </NavigationMenu.Root>
      <button type="button" className="knop knop-stil md:hidden" onClick={() => zetLade(true)} aria-label={tekst.menu}>
        <svg viewBox="0 0 16 16" className="size-4" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true"><path d="M2.5 4.5h11M2.5 8h11M2.5 11.5h11" strokeLinecap="round" /></svg>
      </button>
      <Lade open={lade} zetOpen={zetLade} titel={tekst.menu} sluiten={tekst.sluiten}
            voet={<a className="knop w-full" href={links.over}>{tekst.over}</a>}>
        <nav aria-label={tekst.menu_naam} className="grid gap-4 pt-3">
          <ul className="grid gap-0.5">
            <li><a className="fz-keuze font-medium" href={links.start}>{tekst.start}</a></li>
            <li><a className="fz-keuze font-medium" href={links.lijst}>{tekst.factchecks}</a></li>
            <li><a className="fz-keuze font-medium" href={links.dossier}>{tekst.dossiers}</a></li>
            <li><a className="fz-keuze font-medium" href={links.verkennen}>{tekst.verkennen}</a></li>
            {links.radar && <li><a className="fz-keuze font-medium" href={links.radar}><span className="fz-radar-stip" aria-hidden="true" />{tekst.radar}</a></li>}
          </ul>
          <div><p className="px-2 pb-1 text-[12px] font-semibold text-[var(--zwak)]">{tekst.themas}</p>{themaLinks}</div>
        </nav>
      </Lade>
    </>
  );
}
