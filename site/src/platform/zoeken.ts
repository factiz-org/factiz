// Zoeken en suggesties (`zoek`, `suggesties`, POST) in TypeScript (B80, PLAN #34.2bo stap 4): hetzelfde antwoord als
// `api_zoek` en `api_suggesties` in `factiz_site/app.py`. De vraag komt in het bericht en wordt nergens bewaard.
import { LABELS, TALEN, getal, label, opsomming, pad, stempel, tekst } from './i18n.ts';
import { MEER, type Bewering, type Filters, type Publicatie } from './publicatie.ts';
import { schoon, woorden } from './tekst.ts';
import { BIJNA_GEEN, FILTERS, GROTE_REDACTIES, type Ingang, filterdelen, landnaam, lijstUrl, rijGegevens, tel, themanaam,
  vertaald } from './gedeeld.ts';
import { MAX_PLAKTEKST, MAX_VRAAG, fragment, markeer, sleutel } from './zoeken-tekst.ts';
import { ZOEK_VOLGORDES, type Kenmerk, type Wat, type Zoekuitslag, zoeker } from './zoeken-motor.ts';
import { casefold, knip, lengte, lstrip, strip, vergelijk } from './zoeken-unicode.ts';

// Een vraag naar de site zelf: per vaste pagina haar naam in het menu en de woorden waarmee iemand haar zoekt
// (`app.VASTE_INGANGEN`). Alleen een ingang, nooit een doorsturing.
const VASTE_INGANGEN: [string, string, string[]][] = [
  ['about', 'nav_over', ['over', 'about', 'uber', 'acerca', 'a propos', 'propos', 'over factiz', 'about factiz', 'privacy',
    'privacidad', 'datenschutz', 'confidentialite', 'vie privee', 'contact', 'kontakt', 'contacto', 'impressum', 'factiz']],
  ['platform', 'nav_platform', ['platform', 'plattform', 'plataforma', 'plateforme', 'api', 'open data']],
  ['sources', 'nav_bronnen', ['bronnen', 'sources', 'quellen', 'fuentes', 'licentie', 'licenties', 'license', 'licenses',
    'licence', 'licences', 'lizenz', 'lizenzen', 'licencia', 'licencias', 'cc by']],
  ['newsrooms', 'nav_redacties', ['redacties', 'newsrooms', 'redaktionen', 'redacciones', 'redactions', 'factcheckers',
    'fact checkers', 'faktenchecker', 'verificadores', 'fact-checkers']],
];
let vasteSleutels: Set<string>[] | null = null;

export function vasteIngangen(vraag: string, taal: string): Wat[] {
  const s = sleutel(vraag);
  if (!s) return [];
  vasteSleutels ??= VASTE_INGANGEN.map(([, naamsleutel, w]) =>
    new Set([...TALEN.map((t) => sleutel(tekst(t, naamsleutel))), ...w.map(sleutel)]));
  return VASTE_INGANGEN.flatMap(([pagina, naamsleutel], i) => (vasteSleutels![i].has(s)
    ? [{ soort: 'pagina', pagina, naam: tekst(taal, naamsleutel), aantal: null, href: pad(taal, pagina) }] : []));
}

// Het adres van een ingang op de site (`app.ingang_href`).
export function ingangHref(taal: string, i: Wat): string {
  if (i.href) return i.href;
  if (i.soort === 'naam') return pad(taal, 'names', i.nummer);
  if (i.soort === 'thema') return pad(taal, 'themes', i.thema);
  if (i.soort === 'onderdeel') return pad(taal, 'themes', i.thema, i.onderdeel);
  if (i.soort === 'dossier') return pad(taal, 'dossiers', i.sleutel);
  if (i.soort === 'factcheck') return pad(taal, 'fact-checks', i.nummer);
  return lijstUrl(taal, { redactie: i.redactie });
}

// Wat erin zit en wie nog bijna ontbreekt, als er niets gevonden is (`app.dekking`).
async function dekking(pub: Publicatie, taal: string): Promise<string[]> {
  const redacties = await pub.redacties();
  const zinnen = [tekst(taal, 'dekking_zin', { n: getal(taal, await pub.paginas()), r: getal(taal, redacties.length),
                                              top: opsomming(taal, redacties.slice(0, 3).map(([n]) => n)) })];
  const weinig = GROTE_REDACTIES.filter(([, stuk]) =>
    redacties.filter(([n]) => casefold(n).includes(stuk)).reduce((s, [, a]) => s + a, 0) < BIJNA_GEEN).map(([naam]) => naam);
  if (weinig.length) zinnen.push(tekst(taal, 'dekking_ontbreekt', { namen: opsomming(taal, weinig) }));
  return zinnen;
}

// De eerste waarde van een veld, zoals `(velden.get(k) or [standaard])[0]`.
const eerste = (velden: Map<string, string[]>, k: string, standaard: string) => {
  const w = velden.get(k);
  return w && w.length ? w[0] : standaard;
};

// De vraag, het blad, de volgorde en de filters uit het bericht (`app.lees_zoekbericht`); een keuze die niet bestaat doet
// niets.
async function leesZoekbericht(pub: Publicatie, velden: Map<string, string[]>) {
  const gekozen: Filters = Object.fromEntries(FILTERS.map((s) => [s, null]));
  const vraag = knip(schoon(woorden(eerste(velden, 'q', '')).join(' ')), 0, MAX_PLAKTEKST);
  const ruw = eerste(velden, 'p', '1');
  const blad = /^[0-9]{1,4}$/.test(ruw) && parseInt(ruw, 10) >= 1 ? parseInt(ruw, 10) : 1;
  for (const soort of FILTERS) {
    if (MEER.includes(soort)) {
      const rij: string[] = [];
      for (const w of new Set(velden.get(soort) ?? [])) if (w && await pub.kent(soort, w)) rij.push(w);
      gekozen[soort] = rij.length ? rij.sort(vergelijk) : null;
      continue;
    }
    const waarde = eerste(velden, soort, '');
    if (waarde && soort !== 'onderdeel' && await pub.kent(soort, waarde)) gekozen[soort] = waarde;
  }
  const deel = eerste(velden, 'onderdeel', '');
  if (deel && gekozen.thema && await pub.deel(gekozen.thema as string, deel)) gekozen.onderdeel = deel;
  const volgorde = eerste(velden, 'sorteer', '');
  return { vraag, blad, sorteer: ZOEK_VOLGORDES.includes(volgorde) ? volgorde : null, gekozen };
}

export const ingangen: Record<string, Ingang> = {
  // Zoeken als gegevens (`app.api_zoek`): dezelfde zoekfunctie, filters en ingangen als de zoekpagina.
  zoek: { methode: 'POST', async f(pub, taal, _delen, _vraag, bericht) {
    const velden = bericht ?? new Map<string, string[]>();
    const { vraag, blad, sorteer, gekozen } = await leesZoekbericht(pub, velden);
    const letterlijk = eerste(velden, 'letterlijk', '') === '1';
    const z = await zoeker(pub);
    // het zoeken, de pagina om meteen heen te gaan en de ingangen tegelijk: hun vragen aan de database gaan samen (#37.16)
    const [uit, doel0, ingangenVan] = await Promise.all([z.zoekRuim(vraag, blad, taal, sorteer, letterlijk, true, gekozen),
      blad === 1 ? z.doorsturen(vraag, letterlijk) : Promise.resolve(null),
      blad === 1 ? z.ingangenVan(vraag, taal) : Promise.resolve([])]);
    const termen = uit.markeer;
    const { totaal, zonder_filters: zonder } = uit;
    // tellen (B78): een vraag op het eerste blad; zonder resultaat ook bij alleen zwakke treffers. Nooit de vraag zelf.
    if (blad === 1 && strip(vraag)) {
      tel('zoek', taal);
      if (!totaal || (uit.bericht && uit.deels)) tel('zoek-zonder', taal);
      if (uit.bericht) tel('zoek-bericht', taal);
    }
    // meteen naar een pagina: een geplakte link altijd, een persoon of dossier alleen zonder filters
    let doel = doel0;
    if (doel && doel.soort !== 'factcheck' && Object.values(gekozen).some((w) => w)) doel = null;
    const doorsturen = doel ? { href: ingangHref(taal, doel), soort: doel.soort,
                                naam: typeof doel.naam === 'object' ? doel.naam[taal] : doel.naam } : null;
    const gelezen = async (g: Kenmerk & { woord: string }) => {
      const naam = g.soort === 'land' ? await landnaam(pub, taal, g.waarde) : g.soort === 'redactie' ? g.waarde
        : g.soort === 'thema' ? await themanaam(pub, taal, g.waarde) : await themanaam(pub, taal, g.thema ?? '', g.waarde);
      return { ...g, naam, tekst: tekst(taal, `zoek_gelezen_${g.soort}`, { woord: g.woord, naam }) };
    };
    const rij = async (r: Bewering) => {
      const g = await rijGegevens(pub, taal, r) as Awaited<ReturnType<typeof rijGegevens>> & { stukken?: unknown };
      const v = vertaald(taal, r);
      g.stukken = markeer(fragment(v ? v.tekst : r.bewering as string, termen, 220), termen);
      if (g.origineel) (g.origineel as Record<string, unknown>).stukken = markeer(fragment(r.bewering as string, termen, 140), termen);
      return g;
    };
    const berichtKop = !totaal ? 'zoek_bericht_niets' : uit.deels ? 'zoek_bericht_zwak_kop'
      : totaal === 1 ? 'zoek_bericht_een' : 'zoek_bericht_meer';
    const rijen_ = [];
    for (const r of uit.rijen) rijen_.push(await rij(r));
    const vast = blad === 1 ? [...vasteIngangen(vraag, taal), ...ingangenVan] : [];
    const gelezenUit = [];
    for (const g of uit.gelezen) gelezenUit.push(await gelezen(g));
    return { status: 200, body: {
      totaal, deels: uit.deels, gezocht: uit.termen.length > 0, blad, verbeterd: uit.verbeterd,
      // een geplakt bericht: eerlijk zeggen dat het om gelijkenis in woorden gaat, en op welke woorden
      bericht: uit.bericht,
      bericht_kop: uit.bericht ? tekst(taal, berichtKop, { n: getal(taal, totaal) }) : '',
      bericht_uitleg: uit.bericht ? (uit.deels && totaal ? tekst(taal, 'zoek_bericht_zwak', { n: getal(taal, totaal) })
        : uit.termen.length && totaal ? tekst(taal, 'zoek_bericht_uitleg', { woorden: uit.termen.slice(0, 6).join(', ') }) : '') : '',
      aantal: tekst(taal, totaal === 1 ? 'zoek_een' : 'zoek_meer', { n: getal(taal, totaal) }),
      rijen: rijen_,
      filters: await filterdelen(pub, taal, gekozen, sorteer, true, uit.facetten),
      zonder_filters: zonder > totaal && !totaal
        ? tekst(taal, 'zoek_zonder', { aantal: tekst(taal, zonder === 1 ? 'zoek_een' : 'zoek_meer', { n: getal(taal, zonder) }) }) : '',
      ingangen: vast.map((i) => ({ ...i, href: ingangHref(taal, i) })),
      gelezen: gelezenUit, letterlijk, doorsturen,
      // niets gevonden: wat erin zit en wie nog ontbreekt
      dekking: !totaal ? await dekking(pub, taal) : [],
    } };
  } },

  // Suggesties tijdens het typen (`app.api_suggesties`): zoekvragen, ingangen en een paar factchecks, samen hoogstens 10.
  suggesties: { methode: 'POST', async f(pub, taal, _delen, _vraag, bericht) {
    const velden = bericht ?? new Map<string, string[]>();
    const ruw = knip(schoon(eerste(velden, 'q', '')), 0, MAX_VRAAG);
    const vraag = woorden(ruw).join(' ');
    const z = await zoeker(pub);
    const [gevonden, aanvulwoorden] = await z.suggesties(vraag, taal);
    let ingangen_ = [...vasteIngangen(vraag, taal), ...gevonden];
    // het woord dat je typt, afgemaakt (op de vraag zoals getypt, dus niets na een spatie), en de vraag zelf: tegelijk,
    // zodat hun vragen aan de database samen gaan (#37.16)
    type Uit = Pick<Zoekuitslag, 'rijen' | 'totaal' | 'deels' | 'facetten' | 'markeer'> & { verbeterd?: string | null };
    const [afgemaakt, uit] = await Promise.all([z.aanvulling(lstrip(ruw)),
      lengte(vraag) >= 2 ? z.zoekRuim(vraag, 1, taal)
        : Promise.resolve<Uit>({ rijen: [], totaal: 0, deels: false, facetten: {}, markeer: [] })]) as [
      Awaited<ReturnType<typeof z.aanvulling>>, Uit];
    const aanvulling = afgemaakt?.tekst ?? null;
    const totaal = uit.deels ? 0 : uit.totaal;
    const zoekvragen: Record<string, unknown>[] = [];
    if (totaal) {
      // bij een verbeterde spelfout is de verbeterde vraag de eerste suggestie
      zoekvragen.push({ tekst: uit.verbeterd || vraag, aantal: getal(taal, totaal), ...(uit.verbeterd ? { verbeterd: true } : {}) });
      const themas = Object.entries(uit.facetten.thema ?? {}).sort((a, b) => b[1] - a[1]);
      for (const [s, n] of themas.filter((x) => x[1] < totaal).slice(0, 2)) {
        zoekvragen.push({ tekst: uit.verbeterd || vraag, thema: s, thema_naam: await themanaam(pub, taal, s), aantal: getal(taal, n) });
      }
    }
    // de vraag met het woord afgemaakt bovenaan, met haar aantal
    if (afgemaakt && afgemaakt.aantal) zoekvragen.unshift({ tekst: afgemaakt.tekst, aantal: getal(taal, afgemaakt.aantal) });
    const gezien = new Set(zoekvragen.filter((x) => !x.thema).map((x) => casefold(x.tekst as string)));
    zoekvragen.push(...aanvulwoorden.filter((w) => w !== casefold(vraag) && !gezien.has(w)).map((w) => ({ tekst: w }))
      .slice(0, Math.max(0, 4 - zoekvragen.length)));
    const ruimte = 10 - zoekvragen.length;
    ingangen_ = ingangen_.slice(0, Math.min(4, ruimte));
    const soort: Record<string, (i: Wat) => string> = {
      naam: (i) => tekst(taal, `naam_soort_${i.naamsoort}`), pagina: () => tekst(taal, 'ingang_pagina'),
      dossier: () => tekst(taal, 'ingang_dossier'), thema: () => tekst(taal, 'filter_thema'),
      onderdeel: () => tekst(taal, 'filter_onderdeel'), redactie: () => tekst(taal, 'filter_redactie'),
    };
    const termen = uit.markeer;
    const factchecks = (totaal ? uit.rijen : []).slice(0, Math.max(0, ruimte - ingangen_.length)).slice(0, 3).map((r) => ({
      nummer: r.nummer, href: pad(taal, 'fact-checks', r.nummer as string),
      stukken: markeer(fragment(vertaald(taal, r)?.tekst || (r.bewering as string), termen, 110), termen),
      label: label(taal, r.label as string | null), stempel: stempel(taal, r.label as string | null),
      soort: LABELS.includes(r.label as string) ? r.label : 'geen',
    }));
    return { status: 200, body: {
      vraag, totaal, zoekvragen, aanvulling,
      ingangen: ingangen_.map((i) => ({ soort: i.soort, soort_tekst: soort[i.soort](i), naam: i.naam,
        aantal: i.aantal === null ? '' : tekst(taal, i.aantal === 1 ? 'lijst_een' : 'lijst_meer', { n: getal(taal, i.aantal) }),
        href: ingangHref(taal, i) })),
      factchecks,
    } };
  } },
};
