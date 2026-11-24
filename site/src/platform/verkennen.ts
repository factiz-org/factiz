// Verkennen en het netwerk van namen (`verkennen`, `netwerk`) in TypeScript (B80, PLAN #34.2bo): hetzelfde antwoord als
// `api_verkennen` en `api_netwerk` in `factiz_site/app.py`, met `Publicatie.verkennen`, `verhoudingen` en `netwerk` uit
// `factiz_site/db.py`. De schikking van het netwerk staat in `verkennen-schikking.ts`.
import { rijen, type Rij } from './db.ts';
import { TALEN, getal, pad, tekst } from './i18n.ts';
import type { Publicatie } from './publicatie.ts';
import { alfabet, casefold, vergelijk } from './tekst.ts';
import { NIET_GEVONDEN, type Ingang, landnaam, lijstUrl, themanaam } from './gedeeld.ts';
import { ln, rond, rondEven, vast } from './verkennen-getal.ts';
import { schik } from './verkennen-schikking.ts';

// De drempels van `factiz_site/db.py`. Een object en geen losse waarden: de toets zet ze lager, zoals de Python-toetsen
// met monkeypatch doen, want een proefuitgave van acht beweringen haalt 300 factchecks per land nooit.
export const VERKEN = { jaren: 11, landen: 10, verhoudingLand: 300, verhoudingThema: 20, netwerkNamen: 70, netwerkSamen: 25 };

// Het netwerk (app.py): zoveel namen krijgen hun naam onder de cirkel, hoogstens zoveel tekens, en de breedte van een
// teken (Geist, 11 punten).
const NETWERK_LABELS = 30;
const LABEL_TEKENS = 22;
const LETTERBREEDTE = 6.3;
// De trappen van de wereldkaart (#34.2am): bij de verhouding vaste grenzen rond 1×.
const VERHOUDING_GRENZEN = [1.0, 1.5, 2.0, 3.0];

const tekens = (s: string) => Array.from(s);
// Python `len(j) == 4 and j.isdigit()`; een datum in de uitgave is ISO, dus alleen 0 tot 9
const isJaar = (j: string) => tekens(j).length === 4 && /^[0-9]+$/.test(j);
// Python `str.rstrip()`: witruimte zoals `str.split()` haar kent
const rstrip = (s: string) => s.replace(/[\t\n\x0b\x0c\r\x1c-\x1f \x85\xa0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000]+$/u, '');

// Een naam onder een cirkel: hoogstens `LABEL_TEKENS` tekens (`app.kort`).
function kort(naam: string): string {
  const t = tekens(naam);
  return t.length <= LABEL_TEKENS ? naam : rstrip(t.slice(0, LABEL_TEKENS - 1).join('')) + '…';
}

// --- de gegevens (db.py) ----------------------------------------------------------------------------------------------

function nieuwsteDatum(pub: Publicatie): Promise<string> {
  return pub.eens('verkennen:nieuwste', async () => (await rijen<{ d: string }>(pub.db,
    "SELECT COALESCE(MAX(laatste_datum), '') AS d FROM pagina"))[0]?.d ?? '');
}

// Hoeveel factchecks een thema hebben, elk één keer: het midden van de ring (`Publicatie.met_thema`, de kolom thema >= 0).
function metThema(pub: Publicatie): Promise<number> {
  return pub.eens('verkennen:met_thema', async () => (await rijen<{ n: number }>(pub.db,
    "SELECT COUNT(*) AS n FROM pagina WHERE COALESCE(thema, '') <> ''"))[0]?.n ?? 0);
}

// De jaren en de landen van de hele uitgave, met dezelfde vragen als `Publicatie.facetten` (een land alleen als de uitgave
// het kent). Apart, want `facetten` telt ook de redacties over alle checks, en dat heeft Verkennen niet nodig.
function jarenEnLanden(pub: Publicatie): Promise<{ jaar: [string, number][]; land: [string, number][] }> {
  return pub.eens('verkennen:jaren_landen', async () => {
    const paar = async (sql: string) => (await rijen<{ w: string; n: number }>(pub.db, sql)).map((r): [string, number] => [r.w, r.n]);
    const landen = await pub.landen();
    return {
      jaar: await paar("SELECT substr(laatste_datum, 1, 4) AS w, COUNT(*) AS n FROM pagina WHERE laatste_datum <> '' "
        + 'GROUP BY 1 ORDER BY 1 DESC'),
      land: (await paar("SELECT land AS w, COUNT(*) AS n FROM pagina WHERE land <> '' GROUP BY land ORDER BY COUNT(*) DESC, land"))
        .filter(([c]) => Object.hasOwn(landen, c)),
    };
  });
}

export type Verkenning = { totaal: number; jaren: [string, number][]; eerder: number; zonder_datum: number;
  landen: [string, number][]; met_land: number };

// Wat Verkennen toont (`Publicatie.verkennen`): per jaar tot het jaar van de nieuwste check, wat ervoor ligt en wat geen
// datum heeft, en de landen met hun aantal; met een thema alles binnen dat thema.
export async function verkennenVan(pub: Publicatie, thema: string | null = null): Promise<Verkenning> {
  let jaren: Record<string, number>;
  let landen: Record<string, number>;
  let totaal: number;
  if (thema) {
    const tel = await pub.facettenVan({ thema });
    jaren = tel.jaar;
    landen = tel.land;
    totaal = (await pub.thema(thema))!.aantal;
  } else {
    const f = await jarenEnLanden(pub);
    jaren = Object.fromEntries(f.jaar);
    landen = Object.fromEntries(f.land);
    totaal = await pub.paginas();
  }
  const bekend = await pub.landen();
  const jaar = Object.entries(jaren).filter(([j]) => isJaar(j));
  const land = Object.entries(landen).filter(([c]) => Object.hasOwn(bekend, c));
  const nieuwste = tekens(await nieuwsteDatum(pub)).slice(0, 4).join('');
  const laatste = /^[0-9]+$/.test(nieuwste) ? parseInt(nieuwste, 10) : null;
  const reeks: string[] = [];
  if (laatste !== null) for (let j = laatste - VERKEN.jaren + 1; j <= laatste; j++) reeks.push(String(j));
  const per = new Map(jaar);
  return {
    totaal, jaren: reeks.map((j): [string, number] => [j, per.get(j) ?? 0]),
    eerder: jaar.filter(([j]) => reeks.length && vergelijk(j, reeks[0]) < 0).reduce((s, [, n]) => s + n, 0),
    zonder_datum: totaal - jaar.reduce((s, [, n]) => s + n, 0),
    landen: land.sort((a, b) => (b[1] - a[1]) || vergelijk(a[0], b[0])),
    met_land: land.reduce((s, [, n]) => s + n, 0),
  };
}

// Per land hoe vaak het thema voorkomt bij de factchecks over dat land, gedeeld door hoe vaak het voorkomt bij alle
// factchecks met een land (`Publicatie.verhoudingen`): (land, verhouding, over het thema, over het land), de hoogste
// eerst. Zonder `hoeveel` de top van `VERKEN.landen`; met `null` allemaal, voor de kaart.
export async function verhoudingen(pub: Publicatie, thema: string, hoeveel: number | null = -1):
  Promise<[string, number, number, number][]> {
  const alle = new Map((await jarenEnLanden(pub)).land);
  const binnen = Object.entries((await pub.facettenVan({ thema })).land).filter(([c]) => alle.has(c));
  const t = binnen.reduce((s, [, n]) => s + n, 0);
  const n = [...alle.values()].reduce((s, v) => s + v, 0);
  if (!t) return [];
  const uit = binnen.filter(([c, a]) => alle.get(c)! >= VERKEN.verhoudingLand && a >= VERKEN.verhoudingThema)
    .map(([c, a]): [string, number, number, number] => [c, (a / alle.get(c)!) / (t / n), a, alle.get(c)!]);
  uit.sort((x, y) => (y[1] - x[1]) || (y[2] - x[2]) || vergelijk(x[0], y[0]));
  return hoeveel === null ? uit : uit.slice(0, hoeveel === -1 ? VERKEN.landen : hoeveel);
}

export type Netwerk = { namen: [string, number, string | null][]; randen: [string, string, number][] };

// Het netwerk van namen (`Publicatie.netwerk`): de namen in de meeste factchecks (bij gelijke aantallen het laagste
// nummer van Wikidata eerst), per naam het thema waarin hij het vaakst voorkomt (bij gelijkspel het eerste thema van de
// uitgave), en elk paar dat samen in minstens `VERKEN.netwerkSamen` factchecks staat. Eén keer per uitgave.
export function netwerkVan(pub: Publicatie): Promise<Netwerk> {
  const { netwerkNamen, netwerkSamen } = VERKEN;
  return pub.eens(`verkennen:netwerk:${netwerkNamen}:${netwerkSamen}`, async () => {
    const qGetal = (q: string) => parseInt(q.slice(1), 10);
    const top = [...(await pub.namen()).values()]
      .sort((a, b) => (b.paginas - a.paginas) || (qGetal(a.nummer) - qGetal(b.nummer))).slice(0, netwerkNamen);
    const ids = top.map((n) => n.nummer);
    const perPagina = new Map<string, string[]>();
    const perThema = new Map<string, Map<string, number>>(ids.map((q) => [q, new Map()]));
    if (ids.length) {
      const k = await pub.kolommen();
      const themas = new Set((await pub.themas()).map((t) => t.sleutel));
      for (let i = 0; i < ids.length; i += 90) {          // D1 neemt hoogstens 100 waarden per vraag
        const stuk = ids.slice(i, i + 90);
        for (const r of await rijen<Rij>(pub.db, `SELECT pagina, naam FROM pagina_naam WHERE naam IN (${stuk.map(() => '?').join(',')})`,
          ...stuk)) {
          const pagina = r.pagina as string;
          const naam = r.naam as string;
          if (!perPagina.has(pagina)) perPagina.set(pagina, []);
          perPagina.get(pagina)!.push(naam);
          const plek = k.plek.get(pagina);
          if (plek === undefined) continue;
          for (const code of new Set([k.kolom.thema[plek], k.kolom.tweede[plek]])) {
            if (code === -1) continue;
            const th = k.waarde.thema[code];
            if (!themas.has(th)) continue;
            const c = perThema.get(naam)!;
            c.set(th, (c.get(th) ?? 0) + 1);
          }
        }
      }
    }
    const samen = new Map<string, number>();
    for (const namen of perPagina.values()) {
      const s = [...namen].sort(vergelijk);
      for (let i = 0; i < s.length; i++) {
        for (let j = i + 1; j < s.length; j++) {
          const sleutel = `${s[i]}\u0000${s[j]}`;
          samen.set(sleutel, (samen.get(sleutel) ?? 0) + 1);
        }
      }
    }
    const volg = new Map((await pub.themas()).map((t, i) => [t.sleutel, i]));
    const thema = new Map<string, string | null>();
    for (const [q, c] of perThema) {
      let beste: string | null = null;
      for (const [t, n] of c) {
        if (beste === null || n > c.get(beste)! || (n === c.get(beste)! && volg.get(t)! < volg.get(beste)!)) beste = t;
      }
      thema.set(q, beste);
    }
    const randen = [...samen].filter(([, k]) => k >= netwerkSamen)
      .map(([s, k]): [string, string, number] => { const [a, b] = s.split('\u0000'); return [a, b, k]; })
      .sort((x, y) => vergelijk(x[0], y[0]) || vergelijk(x[1], y[1]) || (x[2] - y[2]));
    return { namen: top.map((n): [string, number, string | null] => [n.nummer, n.paginas, thema.get(n.nummer) ?? null]), randen };
  });
}

type NetwerkSchikking = { plek: [number, number][]; breed: number; hoog: number; stralen: number[]; labels: boolean[] };

// Waar elke naam van het netwerk staat (`app.schikking`): één keer per uitgave en drempel, met voor een label de
// breedste schrijfwijze over alle talen, dus in elke taal dezelfde plek.
function schikking(pub: Publicatie): Promise<NetwerkSchikking> {
  return pub.eens(`verkennen:schikking:${VERKEN.netwerkNamen}:${VERKEN.netwerkSamen}`, async () => {
    const net = await netwerkVan(pub);
    const namen = await pub.namen();
    const hoogste = net.namen.length ? Math.max(...net.namen.map(([, a]) => a)) : 1;
    const stralen = net.namen.map(([, a]) => 4 + 22 * Math.sqrt(a / hoogste));
    const labels = net.namen.map(([q], i) => (i < NETWERK_LABELS
      ? Math.max(...TALEN.map((t) => tekens(kort(namen.get(q)!.naam[t])).length)) * LETTERBREEDTE + 6 : 0.0));
    const volg = new Map(net.namen.map(([q], i) => [q, i]));
    const s = schik(stralen, net.randen.map(([a, b, k]): [number, number, number] => [volg.get(a)!, volg.get(b)!, k]), labels);
    return { ...s, stralen: stralen.map((r) => rond(r, 1)), labels: labels.map((w) => w > 0) };
  });
}

// --- de wereldkaart (app.py) ------------------------------------------------------------------------------------------

// Twee cijfers die tellen: 1473 wordt 1500, 237 wordt 240; onder de honderd blijft het getal (`app._rond`).
function rondTwee(n: number): number {
  if (n < 100) return rondEven(n);
  const stap = 10 ** (String(Math.trunc(n)).length - 2);
  return Math.trunc(rondEven(n / stap) * stap);
}

// Hoogstens vier grenzen tussen vijf even grote groepen van de landen met een factcheck (`app.grenzen_aantal`).
function grenzenAantal(waarden: number[]): number[] {
  const w = waarden.filter((v) => v > 0).sort((a, b) => a - b);
  const uit: number[] = [];
  for (const q of [0.2, 0.4, 0.6, 0.8]) {
    const g = w.length ? rondTwee(w[Math.min(w.length - 1, Math.trunc(q * w.length))]) : 0;
    if (g > Math.max(uit.length ? uit[uit.length - 1] : 1, w.length ? w[0] : 0)) uit.push(g);
  }
  return uit;
}

const trap = (waarde: number, grenzen: number[]) => 1 + grenzen.filter((g) => waarde >= g).length;

// Alleen voor de toets: de kleine functies naast die van `app.py`.
export const binnenkant = { rondTwee, grenzenAantal, trap, kort };

// --- de ingangen ------------------------------------------------------------------------------------------------------

// Alleen deze sleutels, elk één keer; anders bestaat het adres niet.
function alleen(vraag: URLSearchParams, mag: string[]): boolean {
  const sleutels = [...vraag.keys()];
  return sleutels.every((k) => mag.includes(k)) && sleutels.length === new Set(sleutels).size;
}

export const ingangen: Record<string, Ingang> = {
  // Verkennen (PLAN #34.2ah, SPECS E9.S17): de ring van thema's, de tijd en het waar, aan één keuze. Eén adres per
  // weergave: alleen `thema` en, bij een thema, `maat=verhouding`.
  verkennen: { async f(pub, taal, _delen, vraag) {
    if (!alleen(vraag, ['thema', 'maat'])) return NIET_GEVONDEN;
    const sleutel = vraag.get('thema');
    const maat = vraag.get('maat');
    const thema = sleutel !== null ? await pub.thema(sleutel) : null;
    if ((sleutel !== null && thema === null) || (maat !== null && (maat !== 'verhouding' || thema === null))) return NIET_GEVONDEN;
    const t = (s: string, w: Record<string, unknown> = {}) => tekst(taal, s, w);
    const basis = pad(taal, 'explore');
    const naam = thema ? thema.naam[taal] : '';
    const tal = (n: number) => t(n === 1 ? 'lijst_een' : 'lijst_meer', { n: getal(taal, n) });
    const filters = thema ? { thema: sleutel } : {};
    const g = await verkennenVan(pub, thema ? sleutel : null);
    const themas = await pub.themas();
    const midden = themas.length ? await metThema(pub) : 0;
    const land = async (c: string) => landnaam(pub, taal, c);

    const ring = {
      kop: t('verken_ring_kop'), kies: t('verken_kies'), alles: t('verken_alles'), totaal: midden,
      totaal_tekst: t('verken_met_thema', { n: getal(taal, midden) }),
      regel: thema ? t('verken_van_totaal', { n: getal(taal, thema.aantal), totaal: getal(taal, midden) }) : '',
      themas: themas.map((th) => ({ sleutel: th.sleutel, naam: th.naam[taal], aantal: th.aantal, aantal_tekst: tal(th.aantal),
                                    getal: getal(taal, th.aantal), href: `${basis}?thema=${th.sleutel}`, aan: th.sleutel === sleutel })),
    };
    const gekozen = thema ? {
      sleutel, naam, aantal: thema.aantal, aantal_tekst: tal(thema.aantal), lijst: lijstUrl(taal, filters),
      lijst_tekst: t('verken_naar_lijst', { thema: naam }), onderdelen_kop: t('thema_onderdelen'),
      onderdelen: thema.onderdelen.map((o) => ({ sleutel: o.sleutel, naam: o.naam[taal], aantal: o.aantal,
                                                 aantal_tekst: tal(o.aantal), getal: getal(taal, o.aantal),
                                                 href: pad(taal, 'themes', sleutel, o.sleutel) })),
    } : null;

    const nieuwste = await nieuwsteDatum(pub);
    const noot: string[] = [];
    if (g.eerder) noot.push(t('verken_eerder', { jaar: g.jaren[0][0], n: getal(taal, g.eerder) }));
    if (g.zonder_datum) noot.push(t('verken_zonder_datum', { n: getal(taal, g.zonder_datum) }));
    const lopend = tekens(nieuwste).slice(0, 4).join('');
    const tijd = {
      kop: t('verken_tijd_kop'), regel: thema ? t('verken_tijd_regel', { thema: naam }) : t('verken_tijd_regel_alles'),
      jaren: g.jaren.map(([j, n]) => ({ jaar: j, aantal: n, aantal_tekst: tal(n), getal: getal(taal, n), lopend: j === lopend,
                                        href: lijstUrl(taal, { ...filters, jaar: j }) })),
      eerder: g.eerder, zonder_datum: g.zonder_datum, noot: noot.join(' '),
    };

    const tiental = (x: number) => (taal === 'en' ? vast(x, 1) : vast(x, 1).replaceAll('.', ','));
    const verhouding = (f: number, a: number, van: number) =>
      t('verken_verhouding_waarde', { x: tiental(f), n: getal(taal, a), van: getal(taal, van) });
    let landen: Record<string, unknown>[];
    let waarNoot: string;
    if (maat === 'verhouding') {
      landen = [];
      for (const [c, f, a, van] of await verhoudingen(pub, sleutel!)) {
        landen.push({ code: c, naam: await land(c), aantal: a, van, waarde: f, tekst: verhouding(f, a, van),
                      href: lijstUrl(taal, { ...filters, land: c }) });
      }
      waarNoot = t('verken_noot_verhouding', { thema: naam, land: getal(taal, VERKEN.verhoudingLand),
                                               min: getal(taal, VERKEN.verhoudingThema) });
    } else {
      const namen = new Map<string, string>();
      for (const [c] of g.landen) namen.set(c, casefold(await land(c)));
      const top = [...g.landen].sort((x, y) => (y[1] - x[1]) || vergelijk(namen.get(x[0])!, namen.get(y[0])!)).slice(0, VERKEN.landen);
      landen = [];
      for (const [c, a] of top) {
        landen.push({ code: c, naam: await land(c), aantal: a, waarde: a, tekst: getal(taal, a),
                      href: lijstUrl(taal, { ...filters, land: c }) });
      }
      waarNoot = '';
    }
    // de wereldkaart: elk land met zijn maat en trap, op naam, en de legenda (E9.S20)
    type Vak = { code: string; naam: string; waarde: number; trap: number; tekst: string; href: string };
    const kaart: Vak[] = [];
    let grenzen: number[];
    let naamVan: (x: number) => string;
    if (maat === 'verhouding') {
      grenzen = VERHOUDING_GRENZEN;
      for (const [c, f, a, van] of await verhoudingen(pub, sleutel!, null)) {
        kaart.push({ code: c, naam: await land(c), waarde: f, trap: trap(f, grenzen), tekst: verhouding(f, a, van),
                     href: lijstUrl(taal, { ...filters, land: c }) });
      }
      naamVan = (x) => `${tiental(x)}×`;
    } else {
      grenzen = grenzenAantal(g.landen.map(([, a]) => a));
      for (const [c, a] of g.landen) {
        if (!a) continue;
        kaart.push({ code: c, naam: await land(c), waarde: a, trap: trap(a, grenzen), tekst: getal(taal, a),
                     href: lijstUrl(taal, { ...filters, land: c }) });
      }
      naamVan = (x) => getal(taal, Math.trunc(x));
    }
    const volg = new Map(kaart.map((r) => [r, alfabet(r.naam)]));
    kaart.sort((x, y) => vergelijk(volg.get(x)!, volg.get(y)!) || vergelijk(x.code, y.code));
    let legenda: { trap: number; tekst: string }[];
    if (maat === 'verhouding') {
      legenda = [{ trap: 1, tekst: t('verken_trap_onder', { x: naamVan(grenzen[0]) }) },
                 ...grenzen.slice(0, -1).map((van, i) => ({ trap: i + 2, tekst: `${tiental(van)}–${naamVan(grenzen[i + 1])}` })),
                 { trap: grenzen.length + 1, tekst: t('verken_trap_vanaf', { x: naamVan(grenzen[grenzen.length - 1]) }) }];
    } else if (kaart.length) {
      const randen = [kaart.reduce((m, r) => (r.waarde < m ? r.waarde : m), kaart[0].waarde), ...grenzen];
      legenda = randen.slice(0, -1).map((van, i) => {
        const tot = randen[i + 1];
        return { trap: i + 1, tekst: tot - 1 <= van ? naamVan(van) : `${naamVan(van)}–${naamVan(tot - 1)}` };
      });
      legenda.push({ trap: randen.length, tekst: t('verken_trap_vanaf', { x: naamVan(randen[randen.length - 1]) }) });
    } else legenda = [];
    const waar = {
      kop: t('verken_waar_kop'), kaart, legenda, alle_kop: t('verken_alle_landen', { n: getal(taal, kaart.length) }),
      te_klein: t('verken_te_klein'), kaart_bron: t('verken_kaart_bron'), kaart_leeg: t('verken_kaart_leeg'),
      kaart_geen: t('verken_kaart_geen'),
      regel: thema ? t('verken_waar_regel', { thema: naam }) : t('verken_waar_regel_alles'),
      maat: maat || 'aantal', landen, noot: waarNoot,
      gemiddeld: maat ? t('verken_gemiddeld') : '', leeg: maat && !landen.length ? t('verken_geen_land') : '',
      maten: thema ? ['aantal', 'verhouding'].map((w) => ({
        waarde: w, naam: t(`verken_maat_${w}`), aan: (maat || 'aantal') === w,
        href: w === 'verhouding' ? `${basis}?maat=verhouding&thema=${sleutel}` : `${basis}?thema=${sleutel}` })) : [],
    };
    // het netwerk van namen hoort bij Verkennen, en bestaat alleen als de uitgave namen heeft (E9.S18 AC7)
    const net = await pub.heeftNamen() ? { href: pad(taal, 'explore', 'network'), titel: t('netwerk_titel'),
                                           regel: t('netwerk_open_regel') } : null;
    return { status: 200, body: { titel: t('nav_verkennen'), inleiding: t('verken_inleiding'), alles_href: basis, gekozen,
                                  ring, tijd, waar, netwerk: net } };
  } },

  // Het netwerk van namen (PLAN #34.2ai, SPECS E9.S18): een naam kiezen licht hem en zijn buren op. Eén adres per
  // weergave: alleen `naam`, en alleen een naam die in het netwerk staat.
  netwerk: { async f(pub, taal, _delen, vraag) {
    if (!(await pub.heeftNamen())) return NIET_GEVONDEN;
    if (!alleen(vraag, ['naam'])) return NIET_GEVONDEN;
    const s = await schikking(pub);
    const net = await netwerkVan(pub);
    const keuze = vraag.get('naam');
    if (keuze !== null && !net.namen.some(([q]) => q === keuze)) return NIET_GEVONDEN;
    const t = (sl: string, w: Record<string, unknown> = {}) => tekst(taal, sl, w);
    const basis = pad(taal, 'explore', 'network');
    const alleNamen = await pub.namen();
    const naam = (q: string) => alleNamen.get(q)!.naam[taal];
    const tal = (n: number) => t(n === 1 ? 'lijst_een' : 'lijst_meer', { n: getal(taal, n) });
    const buren = new Map<string, number>();
    for (const [a, b, k] of net.randen) if (keuze === a || keuze === b) buren.set(a === keuze ? b : a, k);
    const knopen = net.namen.map(([q, a, th], i) => ({
      id: q, naam: naam(q), kort: kort(naam(q)), soort: alleNamen.get(q)!.soort, aantal: a, aantal_tekst: tal(a), thema: th,
      x: s.plek[i][0], y: s.plek[i][1], r: s.stralen[i], label: s.labels[i], href: `${basis}?naam=${q}`,
      pagina: pad(taal, 'names', q), aan: q === keuze, buur: buren.has(q),
    }));
    const veel = net.randen.length ? net.randen.map(([, , k]) => k) : [1];
    const laag = Math.min(...veel);
    const hoog = Math.max(...veel);
    const randen = net.randen.map(([a, b, k]) => ({
      a, b, samen: k, aan: keuze === a || keuze === b,
      dikte: rond(1 + 3 * (hoog > laag ? ln(k / laag) / ln(hoog / laag) : 0), 2),
    }));
    let gekozen = null;
    if (keuze) {
      const n = alleNamen.get(keuze)!;
      const [, aantal, thema] = net.namen.find(([q]) => q === keuze)!;
      const samen = (k: number) => t(k === 1 ? 'netwerk_samen_een' : 'netwerk_samen', { n: getal(taal, k) });
      const volg = new Map([...buren.keys()].map((q) => [q, alfabet(naam(q))]));
      const themaNaam = thema ? await themanaam(pub, taal, thema) : '';
      gekozen = {
        id: keuze, naam: naam(keuze), soort_naam: t(`naam_soort_${n.soort}`), aantal_tekst: tal(aantal),
        thema: thema ? { sleutel: thema, naam: themaNaam } : null,
        thema_regel: thema ? t('netwerk_thema', { thema: themaNaam }) : '',
        pagina: pad(taal, 'names', keuze), pagina_tekst: t('netwerk_naar_naam', { naam: naam(keuze) }),
        lijst: lijstUrl(taal, { naam: keuze }), lijst_tekst: t('netwerk_naar_lijst', { naam: naam(keuze) }),
        buren_kop: t('netwerk_buren'),
        buren: [...buren].sort((x, y) => (y[1] - x[1]) || vergelijk(volg.get(x[0])!, volg.get(y[0])!))
          .map(([q, k]) => ({ id: q, naam: naam(q), samen: k, samen_getal: getal(taal, k), samen_tekst: samen(k),
                              href: `${basis}?naam=${q}` })),
        geen_buren: buren.size ? '' : t('netwerk_geen_buren', { naam: naam(keuze), samen: getal(taal, VERKEN.netwerkSamen) }),
      };
    }
    const opNaam = new Map(knopen.map((k) => [k.id, alfabet(k.naam)]));
    return { status: 200, body: {
      titel: t('netwerk_titel'),
      inleiding: t('netwerk_inleiding', { n: getal(taal, knopen.length), samen: getal(taal, VERKEN.netwerkSamen) }),
      let_op: t('netwerk_let_op'), alles_href: basis, alles: t('netwerk_alles'),
      verkennen_href: pad(taal, 'explore'), verkennen: t('nav_verkennen'),
      breed: s.breed, hoog: s.hoog, knopen, randen, gekozen,
      // naast het netwerk staan de namen op alfabet, nooit op hun aantal (E9.S11 AC5, E9.S18 AC5)
      namen_kop: t('netwerk_namen_kop'), kies_regel: t('netwerk_kies_regel'),
      namen: [...knopen].sort((x, y) => vergelijk(opNaam.get(x.id)!, opNaam.get(y.id)!) || vergelijk(x.id, y.id))
        .map((k) => ({ id: k.id, naam: k.naam, href: k.href, aan: k.aan })),
      tekst: { zoek: t('netwerk_zoek'), geen: t('netwerk_zoek_geen'), schuif: t('netwerk_schuif') },
    } };
  } },
};
