// De factcheckpagina als gegevens (`app.api_factcheck`, PLAN #34.2) in TypeScript (B80, PLAN #34.2bo stap 3): dezelfde
// velden, met de teksten al in de taal van de site, en hetzelfde antwoord voor een nummer dat er niet is (404) of dat
// een andere formulering is (301 naar de bewering). Een voorkant zegt zo nooit iets anders dan het platform.
import { BASIS, LABELS, datum, eigenTalen, getal, label, oordeelKop, opsomming, pad, richting, stempel, taalnaam, taalnaamIn, tekst,
  telregel, volgens, xDefault, plat, WEGGELATEN } from './i18n.ts';
import type { Bewering, Dossier, Publicatie } from './publicatie.ts';
import { NIET_GEVONDEN, type Antwoord, type Ingang, kenmerken, landnaam, lijstUrl, rijGegevens, themanaam, vertaald,
  vertaalregel, eigenCheck, volgensNamen } from './gedeeld.ts';
import { kort, link, vergelijk } from './tekst.ts';
import { strip } from './zoeken-unicode.ts';
import { type Check, type Pagina, type Samenvatting, type Samenvattingen, type Toeschrijving, begin, dossiersVan, lijktOp, namenVan, pagina, samenvatting,
  toeschrijvingen, varianten,
  verwijzing, waarom, zelfde } from './factcheck-gegevens.ts';
import { context } from './factcheck-context.ts';
import { eigenIn } from './eigentaal.ts';

export const CONTACT = 'info@factiz.org';
const VERTAALTAAL = 'en';

// Een omleiding: de status en waar heen; de site zet `adres` in de kop Location.
export type Omleiding = Antwoord & { adres: string };

// `urllib.parse.quote`: elke byte van UTF-8 als %XX, behalve letters, cijfers, `_.-~` en wat `veilig` noemt.
export function quote(tekst_: string, veilig = '/'): string {
  let uit = '';
  for (const b of new TextEncoder().encode(tekst_)) {
    const c = String.fromCharCode(b);
    uit += /[A-Za-z0-9_.~-]/.test(c) || (b < 128 && veilig.includes(c)) ? c : `%${b.toString(16).toUpperCase().padStart(2, '0')}`;
  }
  return uit;
}

// Witruimte zoals Python haar ziet (`str.strip()`).
const RAND = /^[\t\n\x0b\x0c\r\x1c-\x1f \x85\xa0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000]+|[\t\n\x0b\x0c\r\x1c-\x1f \x85\xa0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000]+$/gu;

// Python `str()` van een waarde uit JSON, voor een blanco in een vaste tekst.
function alsTekst(w: unknown): string {
  return w === null || w === undefined ? 'None' : w === true ? 'True' : w === false ? 'False' : String(w);
}

// Python `int()` op het jaar van een datum; iets anders is een fout, zoals in Python.
function jaartal(stuk: string): number {
  if (!/^\s*[+-]?\d+\s*$/u.test(stuk)) throw new Error(`geen jaar: ${stuk}`);
  return parseInt(stuk, 10);
}

const opDatum = <T extends { datum?: unknown }>(a: T, b: T) => vergelijk(a.datum as string, b.datum as string);

type Ookals = { tekst: string; taal: unknown; richting: unknown };

// Het omveld van een bewering (`app.omveld`, PLAN #34.2h): per jaar wanneer redacties haar checkten, waar een bron haar
// het eerst zag, aan welk netwerk een dossier haar toeschrijft en hoe ze nog meer luidt; niets als er niets te zeggen is.
function omveld(taal: string, p: Pagina, ookAls: Ookals[], toe: Toeschrijving[], dossiers: Map<string, Dossier>) {
  const data = p.checks_lijst.filter((k) => k.datum).map((k) => begin(k.datum as string, 10)).sort(vergelijk);
  const perJaar = new Map<number, number>();
  for (const d of data) perJaar.set(jaartal(begin(d, 4)), (perJaar.get(jaartal(begin(d, 4))) ?? 0) + 1);
  const jaren = [];
  if (perJaar.size) {
    for (let j = Math.min(...perJaar.keys()); j <= Math.max(...perJaar.keys()); j++) jaren.push({ jaar: j, aantal: perJaar.get(j) ?? 0 });
  }
  const gezien = p.opgedoken.filter((o) => o.datum).sort(opDatum);
  const eerstGezien = gezien.length ? { naam: gezien[0].naam, datum: datum(taal, gezien[0].datum),
                                        volgens: tekst(taal, 'opgedoken_volgens', { bron: gezien[0].bron_naam }) } : null;
  const toegeschreven = toe.map((t) => {
    const d = dossiers.get(t.sleutel)!;
    return { naam: d.naam[taal], href: pad(taal, 'dossiers', t.sleutel), door: t.bron, url: link(t.url),
             netwerk_door: d.vastgesteld?.door ?? '' };
  });
  if (jaren.length < 2 && !eerstGezien && !toegeschreven.length && !ookAls.length) return null;
  return { jaren, eerst: data.length ? datum(taal, data[0]) : '', laatst: data.length ? datum(taal, data[data.length - 1]) : '',
           eerst_gezien: eerstGezien, toegeschreven,
           ook_als: ookAls.length ? { aantal: ookAls.length, voorbeelden: ookAls.slice(0, 2) } : null };
}

// Wat een zoekmachine en een AI-zoeker lezen (`app.kopgegevens`, PLAN #34.2m, #34.2bw): het oordeel en dan de bewering in de titel, het
// antwoord van de redacties eerst, en de bewering als `Claim` in JSON-LD met de artikelen van de redacties als `citation`.
const TITEL_BEWERING = 45;

function kopgegevens(taal: string, nummer: string, p: Pagina, g: { vertaling: { tekst: string } | null; bewering: string; label: string }) {
  const t = (s: string, w: Record<string, unknown> = {}) => tekst(taal, s, w);
  // een weggelaten naam (#34.2bw) in een titel en omschrijving als [naam weggelaten]; boven het antwoord de sticker
  const getoond = plat(taal, g.vertaling ? g.vertaling.tekst : g.bewering);
  // eerst het oordeel, dan de bewering tot 45 tekens tussen de aanhalingstekens van de taal (#34.2bq, #34.2bw): een titel
  // die Google afkapt of herbouwt, toont zo nooit een kale bewering over iemand (`app.kopgegevens`)
  // sinds 2026-11-19 het stempel met wie het zegt (PLAN #34.2cc, `app.kopgegevens`): *Onwaar volgens Vera Files: ‘…’*
  const kop = oordeelKop(taal, p.label as string | null, volgensNamen(p.volgens));
  // de vraag zoals een zoeker haar typt (#34.2cf, B87), alleen in haar eigen taal (`app.kopgegevens`)
  const vraagKop = p.zoekvraag && p.zoekvraag.taal === taal ? p.zoekvraag.vraag : '';
  const vraag = plat(taal, vraagKop);
  const titel = vraag ? t('factcheck_titel_vraag', { oordeel: kop, vraag })
    : t('factcheck_titel', { oordeel: kop, bewering: kort(getoond, TITEL_BEWERING) });
  const labelTekst = LABELS.includes(p.label as string) ? kop : '';
  const checks = p.checks_lijst;
  const gedateerd = checks.filter((k) => datum(taal, begin((k.datum as string) || '', 10))).sort(opDatum);
  const nieuwste = gedateerd.length ? gedateerd[gedateerd.length - 1] : checks[0] ?? null;
  const wanneer = gedateerd.length ? datum(taal, begin(nieuwste!.datum as string, 10)) : '';
  const n = (p.redacties as number) || new Set(checks.map((k) => k.redactie)).size;
  let zin = '';
  if (n > 1) {
    zin = wanneer ? t('antwoord_meer', { n: getal(taal, n), redactie: nieuwste!.redactie, datum: wanneer })
      : t('antwoord_meer_zonder_datum', { n: getal(taal, n) });
  } else if (nieuwste) {
    zin = wanneer ? t('antwoord_een', { redactie: nieuwste.redactie, datum: wanneer })
      : t('antwoord_een_zonder_datum', { redactie: nieuwste.redactie });
  }
  const antwoord = [labelTekst ? `${labelTekst}.` : '', zin].filter(Boolean).join(' ');
  const metVoet = `${antwoord} ${t('omschrijving_voet')}`.replace(RAND, '');
  let omschrijving = Array.from(metVoet).length <= 160 ? metVoet : kort(antwoord, 158);
  if (vraag) {   // het oordeel, de vraag, en wie het wanneer checkte; past dat niet, dan zonder wie en wanneer
    const voorop = labelTekst ? `${labelTekst}.` : '';
    const opties = [[voorop, vraag, zin], [voorop, vraag]].map((x) => x.filter(Boolean).join(' '));
    omschrijving = opties.find((x) => Array.from(x).length <= 160) ?? omschrijving;
  }

  const adres = BASIS + pad(taal, 'fact-checks', nummer);
  const claim: Record<string, unknown> = { '@type': 'Claim', text: plat(taal, strip(p.bewering as string)), inLanguage: p.taal };
  const gezien = (p.opgedoken ?? []).filter((o) => o.datum).sort(opDatum);
  if (gezien.length) {   // de plek en de datum, nooit een link naar de bron van het nepnieuws
    claim.firstAppearance = { '@type': 'CreativeWork', name: gezien[0].naam, datePublished: begin(gezien[0].datum, 10) };
  }
  // ook de checks van dezelfde bewering bij een andere redactie (*Ook gecheckt door*, #34.2bp, #34.2bq)
  const bronnen = [...checks, ...lokaalEerst(p.ook_checks ?? [], taal, p.taal as string)];
  const citaties = bronnen.filter((k) => k.link !== 'offline' && link(k.url as string)).map((k) => ({
    '@type': 'CreativeWork', url: link(k.url as string), inLanguage: k.taal, author: { '@type': 'Organization', name: k.redactie },
    ...(datum(taal, begin((k.datum as string) || '', 10)) ? { datePublished: begin(k.datum as string, 10) } : {}),
  }));
  if (citaties.length) claim.citation = citaties;
  const kruimel: [string, string][] = [[t('nav_start'), BASIS + pad(taal)], [t('nav_lijst'), BASIS + pad(taal, 'fact-checks')],
                                       [titel, adres]];
  // wanneer de pagina het laatst veranderde: de dag van haar nieuwste check, zoals `lastmod` in de sitemap (PLAN #34.2bz)
  const gewijzigd = begin((p.laatste_datum as string) || '', 10);
  const ld = {
    '@context': 'https://schema.org', '@type': 'WebPage', '@id': adres, url: adres, name: titel, description: omschrijving,
    inLanguage: taal, ...(datum(taal, gewijzigd) ? { dateModified: gewijzigd } : {}), isPartOf: { '@type': 'WebSite', name: 'Factiz', url: `${BASIS}/` }, mainEntity: claim,
    breadcrumb: { '@type': 'BreadcrumbList', itemListElement: kruimel.map(([naam, url], i) =>
      ({ '@type': 'ListItem', position: i + 1, name: naam, item: url })) },
  };
  // een `<` wordt <: geen bewering kan het blok openbreken met </script>
  return { titel, omschrijving, antwoord: { kop: vraagKop || t('antwoord_kop'), label: labelTekst, zin },
           ld: JSON.stringify(ld).replaceAll('<', '\\u003c') };
}

// De link om een fout te melden (`app.melden`, PLAN #34.2at): een mail met het nummer en de taal in het onderwerp, en
// alleen wat de machine op deze pagina deed, om aan te kruisen.
function melden(taal: string, nummer: string, gedaan: [string, boolean][]) {
  const t = (s: string, w: Record<string, unknown> = {}) => tekst(taal, s, w);
  const regels = [t('melden_kop'), '', ...gedaan.filter(([, ja]) => ja).map(([s]) => `[ ] ${t(s)}`), `[ ] ${t('melden_anders')}`,
                  '', t('melden_pagina', { adres: BASIS + pad(taal, 'fact-checks', nummer) })];
  const onderwerp = t('melden_onderwerp', { nummer, code: taal });
  const href = `mailto:${CONTACT}?subject=${quote(onderwerp, '')}&body=${regels.map((r) => quote(r, '')).join(quote('\r\n'))}`;
  return { vraag: t('melden_vraag'), tekst: t('melden_tekst'), href, adres: CONTACT, redactie: t('melden_redactie') };
}

// Bij een overzicht van de wereldlijst (`app.samenvatting_gegevens`, #37.12, B91): wat de redacties vonden en waar het
// rondging, in het Engels, elke zin met de redacties die haar dragen en het anker van hun check in de volgorde van de pagina.
function samenvattingGegevens(taal: string, checks: Record<string, unknown>[], gevonden: Samenvattingen | null) {
  if (!gevonden) return null;
  const rijen = gevonden.rijen;
  const t = (s: string, w: Record<string, unknown> = {}) => tekst(taal, s, w);
  const plek = new Map<string, { naam: string; anker: string }>();
  checks.forEach((k, i) => { if (!plek.has(k.url as string)) plek.set(k.url as string, { naam: k.redactie as string, anker: `check-${i}` }); });
  const zin = (r: Samenvatting) => ({ zin: r.zin, bronnen: r.bronnen.filter((u) => plek.has(u)).map((u) => plek.get(u)!) });
  return {
    kop: t('samenvatting_kop'), vond: rijen.filter((r) => r.soort === 'vond').map(zin), rondgang_kop: t('rondgang_kop'),
    rondgang: rijen.filter((r) => r.soort === 'rondgang').map(zin), door: t('samenvatting_door'), taal: gevonden.taal,
    engels: gevonden.taal !== taal ? t('samenvatting_engels') : '',
    vertaald: gevonden.taal === taal && taal !== gevonden.brontaal
      ? t('eigen_vertaling', { bron: taalnaamIn(taal, gevonden.brontaal) }) : '',
  };
}

// *Waarom het niet klopt* (`app.waarom_gegevens`, B77): de punten van EUvsDisinfo in het Engels, met de link, de
// herkomst en een mailto om een fout te melden; de gemeten foutmarge niet meer (PO 2026-11-22). Nooit als eigen oordeel.
function waaromGegevens(taal: string, nummer: string, punten: { punten: string[]; url: string } | null) {
  if (!punten) return null;
  const t = (s: string, w: Record<string, unknown> = {}) => tekst(taal, s, w);
  const onderwerp = `${t('waarom_onderwerp')}: ${nummer}`;
  return {
    kop: t('waarom_kop'), bron: 'EUvsDisinfo', punten: punten.punten, taal: 'en', url: link(punten.url), lees: t('waarom_lees'),
    herkomst: t('waarom_herkomst'), engels: taal !== 'en' ? t('waarom_engels') : '',
    meld: `mailto:${CONTACT}?subject=${quote(onderwerp)}`, meld_tekst: t('waarom_meld'),
  };
}

// De checks zo dicht mogelijk bij de lezer (#34.2bp, SPECS E9.S31 AC5, `app.lokaal_eerst`): eerst in de taal van de site,
// dan in de taal van de bewering, dan de nieuwste; bij gelijk de volgorde van de uitgave.
export function lokaalEerst<T extends Record<string, unknown>>(checks: T[], taal: string, claimtaal: string): T[] {
  const rang = (k: T) => (k.taal !== taal ? 2 : 0) + (k.taal !== claimtaal ? 1 : 0);
  const opDatum = [...checks].sort((a, b) => {
    const x = (a.datum as string) || '';
    const y = (b.datum as string) || '';
    return x < y ? 1 : x > y ? -1 : 0;
  });
  return opDatum.sort((a, b) => rang(a) - rang(b));
}

// Wie het checkte en wat elk zegt (`app.eens`, PLAN #34.2cd): elke redactie één keer met haar nieuwste oordeel, in de
// volgorde van de pagina; tot vier allemaal, daarboven drie en *N andere*. Hun oordelen, nooit een eigen (DR2).
type Check = Record<string, unknown>;
// Elke redactie linkt naar haar eigen check eronder: `check-<n>` op deze pagina, `ook-<n>` onder Ook gecheckt door.
function eens(taal: string, eigen: Check[], ook: Check[]) {
  const per = new Map<string, [string, string]>();
  const anker = new Map<string, string>();
  const alle: [Check, string][] = [...eigen.map((k, i): [Check, string] => [k, `check-${i}`]), ...ook.map((k, i): [Check, string] => [k, `ook-${i}`])];
  for (const [k, a] of alle) {
    const oordeel = k.oordeel as string;
    if (!LABELS.includes(oordeel)) continue;
    const nu: [string, string] = [(k.datum as string) || '', oordeel];
    const was = per.get(k.redactie as string);
    if (!was || nu[0] > was[0] || (nu[0] === was[0] && nu[1] > was[1])) {
      per.set(k.redactie as string, nu);
      anker.set(k.redactie as string, a);
    }
  }
  if (per.size < 2) return null;
  const namen = [...per.keys()];
  const heel = namen.length <= 4;
  const toon = heel ? namen : namen.slice(0, 3);
  return {
    tekst: tekst(taal, 'eens_kop'),
    redacties: toon.map((n) => ({ naam: n, soort: (per.get(n) as [string, string])[1], woord: stempel(taal, (per.get(n) as [string, string])[1]), anker: anker.get(n) as string })),
    meer: heel ? '' : tekst(taal, 'stempel_andere', { n: getal(taal, namen.length - 3) }),
    anker: ook.length ? 'ook-gecheckt' : 'bronnen',
  };
}

// Eén check als gegevens (`app.check_gegevens`): de redactie, haar eigen woorden, de datum en de taal, en de link naar het
// artikel of het archief; de woorden in een andere taal dan de site letterlijk vertaald (#34.2o).
function checkGegevens(taal: string, k: Check) {
  const t = (s: string, w: Record<string, unknown> = {}) => tekst(taal, s, w);
  const offline = k.link === 'offline';
  const ktaal = k.taal as string;
  const archief = datum(taal, k.archief_datum as string | null);
  return {
    redactie: k.redactie, oordeel: kort((k.oordeel_eigen as string) || '', 300), oordeel_taal: ktaal,
    oordeel_richting: richting(ktaal), datum: datum(taal, k.datum as string) || t('geen_datum'), taal: taalnaam(ktaal),
    taal_code: ktaal, offline, url: offline ? '' : link(k.url as string), archief: offline ? link(k.archief_url as string | null) : '',
    archief_tekst: archief ? t('check_archief_van', { datum: archief }) : t('check_archief'),
    glos: ktaal !== taal ? k.glossen.get(taal) ?? null : null,
    glos_regel: ktaal !== taal && k.glossen.get(taal) ? t('oordeel_glos', { bron: taalnaamIn(taal, ktaal) }) : '',
  };
}

async function factcheck(pub: Publicatie, taal: string, nummer: string): Promise<Antwoord> {
  const p = await pagina(pub, nummer);
  if (!p) {
    // het nummer van een andere formulering wijst blijvend naar de bewering
    const doel = await verwijzing(pub, nummer);
    if (!doel) return NIET_GEVONDEN;
    const omleiding: Omleiding = { status: 301, adres: `/api/${taal}/factcheck/${doel}` };
    return omleiding;
  }
  const [variant, dossiers, toe, namen, lijkt, punten, meta, gelijk, zinnen] = await Promise.all([
    varianten(pub, nummer, taal), dossiersVan(pub, nummer), toeschrijvingen(pub, nummer), namenVan(pub, nummer),
    lijktOp(pub, nummer, taal), waarom(pub, nummer), pub.meta(), zelfde(pub, nummer, taal), samenvatting(pub, nummer, taal, p.taal as string)]);
  // de check die het dichtst bij de lezer staat eerst (#34.2bp): ook in het antwoord, de bronnen en de context
  p.checks_lijst = lokaalEerst(p.checks_lijst, taal, p.taal as string);
  p.redactie_ruw = p.checks_lijst.length ? p.checks_lijst[0].redactie_ruw : null;
  p.vertaling = p.vertalingen.get(taal) ?? null;
  p.vertaling_en = p.vertalingen.get(VERTAALTAAL) ?? null;
  const t = (s: string, w: Record<string, unknown> = {}) => tekst(taal, s, w);
  const v = vertaald(taal, p as unknown as Bewering);
  // een voorlopige vertaling (B93) is geen eigen tekst: zoekmachines zien de pagina in die taal niet
  const eigen = eigenTalen(p.taal as string, [...p.vertalingen.keys()].filter((x) => !p.voorlopig.has(x)));
  const thema = p.thema as string | null;
  const deel = p.onderdeel as string;
  const tweede = p.tweede as string;
  const ding = async (sleutel: string, ...pad_: string[]) =>
    ({ sleutel, naam: await themanaam(pub, taal, pad_[0], pad_[1] ?? ''), href: pad(taal, 'themes', ...pad_) });
  const themaNaam = thema ? await themanaam(pub, taal, thema) : '';
  const landNaam = p.land ? await landnaam(pub, taal, p.land as string) : '';

  const gegevens: Record<string, unknown> = {
    nummer, href: pad(taal, 'fact-checks', nummer),
    // `kern`: de eerste stap naar zoekmachines (B73 punt 5, PLAN #34.2bt), dezelfde regel als `sitemapWaar`
    vindbaar: { index: eigen.includes(taal), talen: eigen, x_default: xDefault(eigen),
                kern: (p.redacties as number) > 1 || gelijk.length > 0 || dossiers.length > 0,
                // maatregel 2 (#34.2bw): in geen stand naar een zoekmachine; lezen kan iedereen
                afgeschermd: p.afgeschermd },
    bewering: p.bewering, taal: p.taal, richting: p.richting,
    // de tekst boven het citaat: een vertaling, of het normale schrift van een bewering in hoofdletters
    vertaling: v ? { tekst: v.tekst, taal: v.taal, regel: vertaalregel(taal, p.taal as string, v.taal, v.normaal ?? false) } : null,
    // de banner boven een voorlopige vertaling (B93)
    voorlopig: v && p.voorlopig.has(v.taal) ? t('vertaling_voorlopig') : '',
    label: label(taal, p.label as string | null), label_klasse: p.label,
    stempel: stempel(taal, p.label as string | null), volgens: volgens(taal, p.label as string | null, volgensNamen(p.volgens)),
    // het deelplaatje (PLAN #34.2aq): getekend als iemand het vraagt, met de versie van de uitgave in het adres
    deelbeeld: { src: `/deelbeeld/${taal}/${nummer}.jpg?v=${meta.release ?? ''}`,
                 alt: `${kort(plat(taal, v ? v.tekst : p.bewering as string), 200)} · ${label(taal, p.label as string | null)}` },
    // een naam die Factiz bewust weglaat (#34.2bw, SPECS E9.S8 AC13): de site zet de voetnoot onder de bewering
    weggelaten: (p.bewering as string).includes(WEGGELATEN),
    telregel: telregel(taal, p.redacties as number, (JSON.parse((p.talen as string) || '[]') as unknown[]).length,
                       p.eerste_datum as string, p.laatste_datum as string),
    eerder: (JSON.parse((p.eerder as string) || '[]') as [string, unknown][])
      .map(([k, j]) => t('eerder', { label: label(taal, k), jaar: alsTekst(j) })),
    checks: p.checks_lijst.map((k) => checkGegevens(taal, k)),
    herkomst: p.bronnen.map((b) => t('record_bron', { naamsvermelding: b.naamsvermelding, licentie: b.licentie })),
    opgedoken: p.opgedoken.map((o) => ({
      niveau: o.niveau === 'waargenomen' || o.niveau === 'toegeschreven' ? t(`niveau_${o.niveau}`) : '', naam: o.naam,
      volgens: t('opgedoken_volgens', { bron: o.bron_naam }), datum: datum(taal, o.datum), url: link(o.url) })),
    // per rij ook wie het natrok, in welke taal en wanneer voor het eerst: zo is te zien dat hetzelfde bericht rondging
    varianten: variant ? {
      telling: t('ook_als_telling', { n: getal(taal, variant.checks), talen: t(variant.talen === 1 ? 'talen_een' : 'talen_meer',
                                                                                { n: getal(taal, variant.talen) }) }),
      rijen: await Promise.all(variant.rijen.map(async (r) => ({
        ...(await rijGegevens(pub, taal, r)), redactienamen: r.redactienamen, taal_eigen: taalnaam(r.taal as string),
        eerste: datum(taal, r.eerste_datum as string) }))),
    } : null,
    formuleringen: p.formuleringen.map((f) => ({ tekst: kort(f.tekst as string, 400), taal: f.taal, richting: f.richting })),
    // de contextkaarten naast de factcheck (PLAN #34.2an, SPECS E9.S21)
    context: await context(pub, taal, p, dossiers, namen),
    dossiers: dossiers.map((d) => ({ sleutel: d.sleutel, naam: d.naam[taal], href: pad(taal, 'dossiers', d.sleutel) })),
    thema: thema && themaNaam ? await ding(thema, thema) : null,
    onderdeel: thema && deel && await themanaam(pub, taal, thema, deel) ? await ding(deel, thema, deel) : null,
    // het tweede thema, zoals de pagina het noemt (alleen naast een eerste)
    tweede: thema && themaNaam && tweede && await themanaam(pub, taal, tweede) ? await ding(tweede, tweede) : null,
    land: p.land && landNaam ? { code: p.land, naam: landNaam, href: lijstUrl(taal, { land: p.land as string }) } : null,
    kenmerken: kenmerken(taal, p.kenmerk),
    namen: namen.map((n) => ({ nummer: n.nummer, naam: n.naam[taal], soort: n.soort, href: pad(taal, 'names', n.nummer) })),
  };
  // hoe de bewering nog meer luidt: de andere formuleringen uit dezelfde groep, dan de versies uit een dossier
  const ookAls: Ookals[] = (gegevens.formuleringen as Ookals[]).map((f) => ({ tekst: f.tekst, taal: f.taal, richting: f.richting }));
  const rijen = (gegevens.varianten as { rijen: Ookals[] } | null)?.rijen ?? [];
  ookAls.push(...rijen.map((r) => ({ tekst: r.tekst, taal: r.taal, richting: r.richting })));
  gegevens.omveld = omveld(taal, p, ookAls, toe, new Map(dossiers.map((d) => [d.sleutel, d])));
  // de checks van dezelfde bewering elders: voor de bronnen in de kop en voor Ook gecheckt door (#34.2bp)
  p.ook_checks = gelijk.flatMap((r) => r.checks_lijst);
  gegevens.kop = kopgegevens(taal, nummer, p, gegevens as Parameters<typeof kopgegevens>[3]);
  // een fout melden (PLAN #34.2at, SPECS E9.S24): een mail met alleen wat de machine op deze pagina deed
  gegevens.melden = melden(taal, nummer, [
    ['melden_vertaling', Boolean(v && !v.normaal)], ['melden_thema', Boolean(gegevens.thema)],
    ['melden_land', Boolean(gegevens.land)], ['melden_namen', namen.length > 0],
    ['melden_kenmerk', (gegevens.kenmerken as unknown[]).length > 0]]);
  // Ook gecheckt door (#34.2bp, SPECS E9.S31): de checks van de pagina's met dezelfde bewering bij een andere redactie, elk
  // met haar eigen oordeel en de bewering zoals die pagina haar toont; de dichtstbijzijnde eerst
  const metRij = await Promise.all(gelijk.map(async (r) => {
    const rij = await rijGegevens(pub, taal, r);
    return r.checks_lijst.map((k) => ({ k, rij, taal: k.taal, datum: k.datum }));
  }));
  const ook = lokaalEerst(metRij.flat(), taal, p.taal as string);
  const ookNamen = [...new Set(ook.map((x) => x.k.redactie as string))];
  gegevens.ook_gecheckt = ook.length ? {
    regel: t('ook_gecheckt_regel', { namen: opsomming(taal, ookNamen) }),
    telling: t(ookNamen.length === 1 ? 'redacties_een' : 'redacties_meer', { n: getal(taal, ookNamen.length) }),
    checks: ook.map((x) => ({ ...checkGegevens(taal, x.k), bewering: x.rij })),
  } : null;
  // wat alle redacties zeggen (PLAN #34.2cd, SPECS E9.S31 AC7): op deze pagina en onder Ook gecheckt door samen (`app.eens`)
  gegevens.eens = eens(taal, p.checks_lijst, ook.map((x) => x.k));
  // Lijkt op (#34.2p): wat al bij Komt ook voor als of bij Ook gecheckt door staat, niet nog eens
  const al = new Set([...(variant?.rijen ?? []).map((r) => r.nummer), ...gelijk.map((r) => r.nummer)]);
  const lijktRijen = await Promise.all(lijkt.filter((r) => !al.has(r.nummer)).map((r) => rijGegevens(pub, taal, r)));
  const perLabel = new Map<string, { label: string; soort: unknown; n: number }>();
  for (const r of lijktRijen) {
    const sleutel = JSON.stringify([r.label, r.soort]);
    if (!perLabel.has(sleutel)) perLabel.set(sleutel, { label: r.label, soort: r.soort, n: 0 });
    perLabel.get(sleutel)!.n++;
  }
  gegevens.lijkt_op = lijktRijen.length ? {
    telling: t(lijktRijen.length === 1 ? 'lijkt_op_een' : 'lijkt_op_meer', { n: getal(taal, lijktRijen.length) }),
    per_label: [...perLabel.values()].sort((a, b) => b.n - a.n), rijen: lijktRijen,
  } : null;
  gegevens.waarom = waaromGegevens(taal, nummer, punten);
  gegevens.samenvatting = samenvattingGegevens(taal, p.checks_lijst as unknown as Record<string, unknown>[], zinnen);
  // een eigen factcheck (#37.4): de site gaat meteen naar de check zelf
  const ec = await eigenCheck(pub, nummer);
  if (ec) gegevens.eigen_href = ec.paden[eigenIn(ec, taal) ? taal : ec.taal];
  return { status: 200, body: gegevens };
}

export const ingangen: Record<string, Ingang> = {
  factcheck: { delen: [1], f: (pub, taal, delen) => factcheck(pub, taal, delen[0]) },
};
