// De lijsten en ingangen van het platform in TypeScript (B80, PLAN #34.2bo stap 3): archief, bronnen, redacties, thema's,
// dossiers, namen, een naam, een thema en een dossier; hetzelfde antwoord als `factiz_site/app.py`.
import { getal, opsomming, pad, tekst, datum } from './i18n.ts';
import { NAAMSOORTEN, PER_BLAD, type Filters, type Publicatie } from './publicatie.ts';
import { begin, nieuwsteDatum } from './factcheck-gegevens.ts';
import { casefold, link, paren, urlencode } from './tekst.ts';
import { eigenIn } from './eigentaal.ts';
import { BIJNA_GEEN, GROTE_REDACTIES, NIET_GEVONDEN, type Ingang, aantal, actiefVan, dossierkaart, filterdelen, landnaam,
  leesLijstvraag, lijstUrl, rijGegevens, themakaart, themanaam } from './gedeeld.ts';

// De dag van een uitgave uit haar naam (`db.uitgave_dag`): `2026-11-16b` is van 16 november; anders leeg.
export function uitgaveDag(release: string | null | undefined): string {
  return /^([0-9]{4}-[0-9]{2}-[0-9]{2})[a-z]?$/.exec(release ?? '')?.[1] ?? '';
}

// De dag van de uitgave en van de nieuwste check erin (`app.actueel`, PLAN #34.2bz).
async function actueel(pub: Publicatie, taal: string) {
  const uitgave = uitgaveDag(await pub.release());
  const factcheck = begin(await nieuwsteDatum(pub), 10);
  return { uitgave, uitgave_tekst: datum(taal, uitgave), factcheck, factcheck_tekst: datum(taal, factcheck) };
}

// Het verschil in dagen tussen twee data als JJJJ-MM-DD (a min b), of null als er een geen datum is.
function dagenTussen(a: string, b: string): number | null {
  const d = (x: string) => (/^[0-9]{4}-[0-9]{2}-[0-9]{2}$/.test(x) ? Date.UTC(+x.slice(0, 4), +x.slice(5, 7) - 1, +x.slice(8, 10)) : NaN);
  const v = (d(a) - d(b)) / 86400000;
  return Number.isFinite(v) ? v : null;
}

// Factiz Radar in het menu en op de start (`app.radar`, PO 2026-11-19): de gepubliceerde eigen checks in deze taal, hoeveel
// van de zeven dagen tot en met de dag van de uitgave, en de nieuwste; zonder gepubliceerde check null.
async function radar(pub: Publicatie, taal: string) {
  const checks = (await pub.eigen()).filter((c) => !c.concept).map((c) => eigenIn(c, taal)).filter((c) => c !== null);
  if (!checks.length) return null;
  const dag = uitgaveDag(await pub.release());
  const nNieuw = checks.filter((c) => { const v = dagenTussen(dag, (c.gepubliceerd ?? '').slice(0, 10)); return v !== null && v >= 0 && v < 7; }).length;
  const eerste = [...checks].sort((a, b) => ((b.gepubliceerd ?? '') > (a.gepubliceerd ?? '') ? 1 : (b.gepubliceerd ?? '') < (a.gepubliceerd ?? '') ? -1 : 0))[0];
  return { href: pad(taal, 'radar'), aantal: checks.length, nieuw: nNieuw,
           aantal_tekst: tekst(taal, checks.length === 1 ? 'radar_aantal_een' : 'radar_aantal', { n: getal(taal, checks.length) }),
           nieuw_tekst: nNieuw ? tekst(taal, nNieuw === 1 ? 'radar_nieuw_een' : 'radar_nieuw', { n: getal(taal, nNieuw) }) : '',
           nieuwste: { kop: eerste.kop, href: eerste.paden[taal] } };
}

export const ingangen: Record<string, Ingang> = {
  // De lijst met filters, tellingen en volgorde (`app.api_archief`); geen zoekvraag, die gaat nooit in een adres.
  archief: { async f(pub, taal, _delen, vraag) {
    const { gekozen, sorteer, blad } = await leesLijstvraag(pub, vraag);
    const { rijen, totaal } = await pub.lijst(gekozen, { blad, vertaal: taal, sorteer });
    const bladen = Math.max(1, Math.ceil(totaal / PER_BLAD));
    if (blad > bladen && totaal) return NIET_GEVONDEN;
    const actief = actiefVan(gekozen);
    const tellingen = await pub.tellingen();
    return { status: 200, body: {
      taal, totaal, blad, bladen, aantal: aantal(taal, totaal),
      paren: paren({ ...actief, ...(sorteer ? { sorteer } : {}) }),
      rijen: await Promise.all(rijen.map((r) => rijGegevens(pub, taal, r))),
      filters: await filterdelen(pub, taal, gekozen, sorteer, false, await pub.facettenVan(gekozen)),
      tellingen: Object.fromEntries(Object.entries(tellingen).map(([k, v]) => [k, getal(taal, v)])),
      // tot wanneer de site bij is, voor de voet en de sitemap (`app.actueel`, PLAN #34.2bz)
      actueel: await actueel(pub, taal),
      // Factiz Radar, de eigen checks in deze taal, voor het menu en de ringen op de start (`app.radar`)
      radar: await radar(pub, taal),
      dossiers: (await pub.dossiers()).slice(0, 4).map((d) => dossierkaart(taal, d)),
      // hoeveel dossiers er zijn, voor de link naar alle dossiers op de start (`app.api_archief`)
      dossiers_aantal: getal(taal, (await pub.dossiers()).length),
      namen: await pub.heeftNamen(),
    } };
  } },

  // Het register van namen (PLAN #34.2r): letters per soort, en bij een gekozen letter de namen; nooit een telling.
  namen: { async f(pub, taal, _delen, vraag) {
    if (!(await pub.heeftNamen())) return NIET_GEVONDEN;
    const sleutels = [...vraag.keys()];
    if (sleutels.some((k) => k !== 'soort' && k !== 'letter') || sleutels.length !== new Set(sleutels).size) return NIET_GEVONDEN;
    const soort = vraag.get('soort');
    const letter = vraag.get('letter');
    if ((soort === null) !== (letter === null)) return NIET_GEVONDEN;
    if (soort !== null && (!NAAMSOORTEN.includes(soort) || !(await pub.letters(taal, soort)).includes(letter!))) return NIET_GEVONDEN;
    const teken = (x: string) => (x === '0' ? '#' : x.toUpperCase());
    const groepen = [];
    for (const s of NAAMSOORTEN) {
      groepen.push({ soort: s, kop: tekst(taal, `namen_soort_${s}`), letters: (await pub.letters(taal, s)).map((x) => ({
        letter: x, teken: teken(x), label: x === '0' ? tekst(taal, 'namen_andere') : '',
        href: `${pad(taal, 'names')}?${urlencode([['letter', x], ['soort', s]])}` })) });
    }
    return { status: 200, body: {
      groepen: groepen.filter((g) => g.letters.length), concept: Boolean((await pub.meta()).namen_concept),
      gekozen: soort ? { soort, letter, teken: teken(letter!) } : null,
      namen: soort ? (await pub.registerVan(taal, soort, letter!)).map((n) => ({ nummer: n.nummer, naam: n.naam[taal],
                                                                             href: pad(taal, 'names', n.nummer) })) : [],
    } };
  } },

  // Een naam (PLAN #34.2r): een ingang, geen oordeel; de factchecks waarin ze voorkomt.
  naam: { delen: [1], async f(pub, taal, delen) {
    const n = await pub.naam(delen[0]);
    if (!n) return NIET_GEVONDEN;
    const { rijen, totaal } = await pub.lijst({ naam: n.nummer }, { vertaal: taal });
    return { status: 200, body: {
      nummer: n.nummer, naam: n.naam[taal], soort: n.soort, soort_tekst: tekst(taal, `naam_soort_${n.soort}`),
      concept: Boolean((await pub.meta()).namen_concept), zin: tekst(taal, 'naam_zin'), bedoeld: tekst(taal, 'naam_bedoeld'),
      omschrijving: tekst(taal, 'naam_omschrijving', { naam: n.naam[taal] }), wikidata: `https://www.wikidata.org/wiki/${n.nummer}`,
      aantal: aantal(taal, totaal), rijen: await Promise.all(rijen.map((r) => rijGegevens(pub, taal, r))),
      alle: lijstUrl(taal, { naam: n.nummer }), alle_tekst: tekst(taal, 'naam_alle'),
    } };
  } },

  // Een thema of onderdeel (PLAN #34.2u): dezelfde rijen en dossiers als de pagina van het thema.
  thema: { delen: [1, 2], async f(pub, taal, delen) {
    const [sleutel, deelSleutel] = delen;
    const thema = await pub.thema(sleutel);
    const deel = thema && deelSleutel !== undefined ? await pub.deel(sleutel, deelSleutel) : null;
    if (!thema || (deelSleutel !== undefined && !deel)) return NIET_GEVONDEN;
    const filters: Filters = { thema: sleutel, ...(deel ? { onderdeel: deelSleutel } : {}) };
    const { rijen, totaal } = await pub.lijst(filters, { vertaal: taal });
    const kop = deel ? deel.naam[taal] : thema.naam[taal];
    const kaart = themakaart(taal, thema);
    const release = await pub.release();
    return { status: 200, body: {
      sleutel, kop, thema_naam: thema.naam[taal], thema_href: kaart.href, deel: deel ? { sleutel: deelSleutel, naam: deel.naam[taal] } : null,
      kicker: tekst(taal, 'nav_themas'), omschrijving: tekst(taal, 'thema_omschrijving', { naam: kop }),
      deelbeeld: { src: `/deelbeeld/${taal}/thema/${sleutel}${deel ? `/${deelSleutel}` : ''}.jpg?v=${release}`,
                   alt: `${deel ? thema.naam[taal] : tekst(taal, 'nav_themas')} · ${kop}` },
      aantal: aantal(taal, totaal), alle: lijstUrl(taal, filters), alle_tekst: tekst(taal, 'thema_alle'),
      onderdelen_kop: tekst(taal, 'thema_onderdelen'), onderdelen: deel ? [] : kaart.onderdelen,
      dossiers: (await pub.dossiersBij(sleutel, deel ? deelSleutel : null)).map((d) => dossierkaart(taal, d)),
      rijen: await Promise.all(rijen.map((r) => rijGegevens(pub, taal, r))),
    } };
  } },

  // Een dossier (PLAN #34.2): de tijdlijn per jaar, de nieuwste boven.
  dossier: { delen: [1], async f(pub, taal, delen) {
    const sleutel = delen[0];
    const d = await pub.dossier(sleutel);
    if (!d) return NIET_GEVONDEN;
    const t = (s: string, w: Record<string, unknown> = {}) => tekst(taal, s, w);
    const jaren: { jaar: string; kop: string; regels: Record<string, unknown>[] }[] = [];
    for (const it of await pub.tijdlijn(sleutel, taal)) {
      const jaar = (it.datum ?? '').slice(0, 4);
      if (!jaren.length || jaren[jaren.length - 1].jaar !== jaar) jaren.push({ jaar, kop: jaar || t('dossier_zonder_datum'), regels: [] });
      const regel: Record<string, unknown> = { soort: it.soort, soort_tekst: t(`item_${it.soort}`), datum: datum(taal, it.datum) };
      if (it.rij) {
        regel.rij = { ...(await rijGegevens(pub, taal, it.rij)), redacties: it.redacties ?? [] };
        if ((it.niveau === 'waargenomen' || it.niveau === 'toegeschreven') && it.bron) {
          regel.niveau = t(`dossier_niveau_${it.niveau}`, { bron: it.bron });
          regel.url = link(it.url);
        }
      } else Object.assign(regel, { titel: it.titel[taal], bron: it.bron, url: link(it.url) });
      jaren[jaren.length - 1].regels.push(regel);
    }
    const s = d.stand;
    const themaNaam = await themanaam(pub, taal, d.thema);
    const deelNaam = d.thema && d.onderdeel ? await themanaam(pub, taal, d.thema, d.onderdeel) : '';
    return { status: 200, body: {
      sleutel, naam: d.naam[taal], soort: d.soort, soort_tekst: t(`dossier_soort_${d.soort}`),
      deelbeeld: { src: `/deelbeeld/${taal}/dossier/${sleutel}.jpg?v=${await pub.release()}`,
                   alt: `${t(`dossier_soort_${d.soort}`)} · ${d.naam[taal]}` },
      concept: d.concept, inleiding: d.inleiding[taal], thema_sleutel: d.thema,
      stand: { eerste: datum(taal, s.eerste) || t('geen_datum'), factchecks: getal(taal, s.factchecks), redacties: getal(taal, s.redacties),
               talen: getal(taal, s.talen), laatste: datum(taal, s.laatste) || t('geen_datum') },
      vastgesteld: d.vastgesteld ? { door: d.vastgesteld.door, datum: datum(taal, d.vastgesteld.datum), url: link(d.vastgesteld.url) } : null,
      jaren,
      thema: d.thema && themaNaam ? { naam: themaNaam, href: pad(taal, 'themes', d.thema) } : null,
      onderdeel: d.thema && themaNaam && d.onderdeel && deelNaam ? { naam: deelNaam, href: pad(taal, 'themes', d.thema, d.onderdeel) } : null,
      verwant: d.verwant.map((w) => ({ sleutel: w.sleutel, naam: w.naam[taal], href: pad(taal, 'dossiers', w.sleutel) })),
      // begrippen om verder te zoeken (#34.2ca, SPECS E9.S7 AC9): elk een zoekvraag naar het archief
      begrippen: d.begrippen[taal] ?? d.begrippen.en ?? [],
    } };
  } },

  bronnen: { async f(pub, taal) {
    // bij EUvsDisinfo de gemeten foutmarge van *Waarom het niet klopt* (`app.api_bronnen`, B77)
    const meta = await pub.meta();
    const m = meta.waarom_meting ? JSON.parse(meta.waarom_meting as string) as Record<string, number> : null;
    const meting = m && Object.keys(m).length
      ? tekst(taal, 'waarom_meting', { punten: getal(taal, m.punten), fout: getal(taal, m.niet_gedragen) }) : '';
    return { status: 200, body: {
      titel: tekst(taal, 'bronnen_titel'), inleiding: tekst(taal, 'bronnen_inleiding'),
      licentie_kop: tekst(taal, 'bronnen_licentie'), vermelding_kop: tekst(taal, 'bronnen_vermelding'),
      meting_kop: tekst(taal, 'waarom_kop'),
      bronnen: (await pub.bronnen()).map((b) => ({ naam: b.naam, licentie: b.licentie,
                                                   naamsvermelding: b.naamsvermelding, url: link(b.url),
                                                   meting: b.bron === 'euvsdisinfo' ? meting : '' })),
    } };
  } },

  redacties: { async f(pub, taal) {
    const redacties = await pub.redacties();
    // Wat erin zit en wat nog niet (#34.2az): hoeveel factchecks van hoeveel redacties, wie de meeste leverde, en welke
    // grote redacties nog bijna ontbreken
    const dekking = [tekst(taal, 'dekking_zin', { n: getal(taal, await pub.paginas()), r: getal(taal, redacties.length),
                                                  top: opsomming(taal, redacties.slice(0, 3).map(([n]) => n)) })];
    const weinig = GROTE_REDACTIES.filter(([, stuk]) =>
      redacties.filter(([n]) => casefold(n).includes(stuk)).reduce((s, [, a]) => s + a, 0) < BIJNA_GEEN)
      .map(([naam]) => naam);
    if (weinig.length) dekking.push(tekst(taal, 'dekking_ontbreekt', { namen: opsomming(taal, weinig) }));
    return { status: 200, body: {
      titel: tekst(taal, 'nav_redacties'), inleiding: tekst(taal, 'redacties_inleiding'), dekking,
      redacties: redacties.map(([n, a]) => ({ naam: n, aantal: getal(taal, a), href: lijstUrl(taal, { redactie: n }) })),
    } };
  } },

  themas: { async f(pub, taal) {
    const themas = await pub.themas();
    if (!themas.length) return NIET_GEVONDEN;
    return { status: 200, body: { titel: tekst(taal, 'nav_themas'), inleiding: tekst(taal, 'themas_inleiding'),
                                  themas: themas.map((th) => themakaart(taal, th)) } };
  } },

  dossiers: { async f(pub, taal) {
    const dossiers = await pub.dossiers();
    if (!dossiers.length) return NIET_GEVONDEN;
    return { status: 200, body: { titel: tekst(taal, 'nav_dossiers'), inleiding: tekst(taal, 'dossiers_inleiding'),
                                  laatste_kop: tekst(taal, 'dossier_laatste'),
                                  dossiers: dossiers.map((d) => dossierkaart(taal, d)) } };
  } },
};
