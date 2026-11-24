// De contextkaarten naast een factcheck (`app.context`, PLAN #34.2an, SPECS E9.S21) in TypeScript (B80, PLAN #34.2bo):
// het dossier, waar, de namen, wanneer, soort en vorm, de redactie; hoogstens vier, in die volgorde, elk alleen met
// gegevens. Dezelfde getallen als Verkennen, het netwerk en de lijst. Een kaart na de vierde wordt niet gerekend: ze valt
// toch weg.
import { datum, getal, pad, tekst } from './i18n.ts';
import type { Dossier, NaamDing, Publicatie } from './publicatie.ts';
import { landnaam, lijstUrl, themanaam } from './gedeeld.ts';
import { alfabet, vergelijk } from './tekst.ts';
import { GRENZEN, type Pagina, begin, buren, dossierJaren, kenmerkTelling, landTelling, netwerkNamen, nieuwsteDatum,
  redactieTelling, themaTelling } from './factcheck-gegevens.ts';

export const CONTEXT_MAX = 4;

// Python `f"{x:.1f}"`: afronden op de exacte waarde, en een gelijke afstand naar het even cijfer (`toFixed` kiest dan het
// grotere). Gelijk kan alleen bij een veelvoud van een kwart.
function eenDecimaal(x: number): string {
  if (Number.isInteger(x * 4) && !Number.isInteger(x * 2)) {
    const n = Math.floor(x * 10);
    return ((n % 2 === 0 ? n : n + 1) / 10).toFixed(1);
  }
  return x.toFixed(1);
}

// Hoe vaak het thema voorkomt bij de factchecks over dit land, gedeeld door hoe vaak bij alle factchecks met een land,
// alleen boven beide drempels (`Publicatie.verhoudingen`); anders niets.
async function verhouding(pub: Publicatie, thema: string, land: string): Promise<number | null> {
  const alle = await landTelling(pub);
  const binnen = [...(await themaTelling(pub, thema)).land].filter(([c]) => alle.has(c));
  const t = binnen.reduce((s, [, n]) => s + n, 0);
  const n = [...alle.values()].reduce((s, x) => s + x, 0);
  const a = binnen.find(([c]) => c === land)?.[1];
  if (!t || a === undefined) return null;
  const totaal = alle.get(land)!;
  return totaal >= GRENZEN.VERHOUDING_LAND && a >= GRENZEN.VERHOUDING_THEMA ? (a / totaal) / (t / n) : null;
}

// De jaren van Verkennen binnen een thema: de laatste `VERKEN_JAREN` tot het jaar van de nieuwste check.
async function themajaren(pub: Publicatie, thema: string): Promise<[string, number][]> {
  const laatste = begin(await nieuwsteDatum(pub), 4);
  if (!/^\p{Nd}+$/u.test(laatste)) return [];
  const jaren = new Map([...(await themaTelling(pub, thema)).jaar].filter(([j]) => /^\p{Nd}{4}$/u.test(j)));
  const tot = parseInt(laatste, 10);
  const uit: [string, number][] = [];
  for (let j = tot - GRENZEN.VERKEN_JAREN + 1; j <= tot; j++) uit.push([String(j), jaren.get(String(j)) ?? 0]);
  return uit;
}

export async function context(pub: Publicatie, taal: string, p: Pagina, dossiers: Dossier[], namen: NaamDing[]) {
  const tal = (n: number) => tekst(taal, n === 1 ? 'lijst_een' : 'lijst_meer', { n: getal(taal, n) });
  const thema = p.thema && await pub.thema(p.thema as string) ? p.thema as string : null;
  const themanaam_ = thema ? await themanaam(pub, taal, thema) : '';
  const jaar = begin(p.laatste_datum as string, 4);
  const verkennen = pad(taal, 'explore');
  const kaarten: Record<string, unknown>[] = [];
  const vol = () => kaarten.length >= CONTEXT_MAX;

  if (dossiers.length) {
    const d = dossiers[0];
    const st = d.stand;
    kaarten.push({
      soort: 'dossier', vraag: tekst(taal, 'context_dossier_vraag'), naam: d.naam[taal], thema: d.thema || '',
      jaren: (await dossierJaren(pub, d.sleutel)).map(([j, n]) => ({ jaar: j, aantal: n, aan: j === jaar })),
      zin: tekst(taal, 'context_dossier_zin', { n: getal(taal, st.factchecks), redacties: getal(taal, st.redacties),
                                                talen: getal(taal, st.talen), van: datum(taal, st.eerste), tot: datum(taal, st.laatste) }),
      href: pad(taal, 'dossiers', d.sleutel), link: tekst(taal, 'context_dossier_link'),
    });
  }

  const land = p.land && await landnaam(pub, taal, p.land as string) ? p.land as string : null;
  if (land && !vol()) {
    const naam = await landnaam(pub, taal, land);
    const alle = (await landTelling(pub)).get(land) ?? 0;
    let zin = tekst(taal, 'context_waar_zin', { land: naam, n: tal(alle) });
    let href = thema ? `${verkennen}?thema=${thema}` : verkennen;
    if (thema) {
      const binnen = (await themaTelling(pub, thema)).land.get(land) ?? 0;
      zin = tekst(taal, 'context_waar_thema', { land: naam, n: tal(alle), m: getal(taal, binnen), thema: themanaam_ });
      const v = await verhouding(pub, thema, land);
      if (v !== null) {
        const x = taal === 'en' ? eenDecimaal(v) : eenDecimaal(v).replace('.', ',');
        zin += ` ${tekst(taal, 'context_waar_verhouding', { x: `${x}×` })}`;
        href = `${verkennen}?maat=verhouding&thema=${thema}`;
      }
    }
    kaarten.push({ soort: 'waar', vraag: tekst(taal, 'context_waar_vraag'), code: land, thema: thema ?? '', zin,
                   href, link: tekst(taal, 'context_waar_link') });
  }

  // de namen in het netwerk: een naam buiten het netwerk krijgt geen regel; zonder namen geen netwerk
  if (namen.length && !vol()) {
    const net = await netwerkNamen(pub);
    const per = new Map(net.map((n) => [n.nummer, n]));
    const netwerkPad = pad(taal, 'explore', 'network');
    const regels = [];
    for (const n of namen) {
      if (!per.has(n.nummer)) continue;
      const rand = await buren(pub, n.nummer, net);
      const sleutel = new Map(rand.map(([q]) => [q, alfabet(per.get(q)!.naam[taal])]));
      const top = [...rand].sort((a, b) => (b[1] - a[1]) || vergelijk(sleutel.get(a[0])!, sleutel.get(b[0])!)).slice(0, 2);
      const regel = top.length
        ? tekst(taal, 'context_namen_samen', { namen: top.map(([q, k]) => `${per.get(q)!.naam[taal]} (${getal(taal, k)})`).join(', ') })
        : tekst(taal, 'context_namen_geen', { samen: getal(taal, GRENZEN.NETWERK_SAMEN) });
      regels.push({ naam: n.naam[taal], href: `${netwerkPad}?naam=${n.nummer}`, regel });
    }
    if (regels.length) {
      kaarten.push({ soort: 'namen', vraag: tekst(taal, 'context_namen_vraag'), namen: regels.slice(0, 3),
                     noot: tekst(taal, 'context_namen_noot'), href: netwerkPad, link: tekst(taal, 'context_namen_link') });
    }
  }

  if (thema && !vol()) {
    const jaren = await themajaren(pub, thema);
    if (jaren.some(([, n]) => n)) {
      // het eerste jaar met het hoogste aantal, bij gelijk aantal het latere jaar (`max` op (aantal, jaar))
      let [piekJaar, piek] = jaren[0];
      for (const [j, n] of jaren.slice(1)) if (n > piek || (n === piek && vergelijk(j, piekJaar) > 0)) [piekJaar, piek] = [j, n];
      let zin = tekst(taal, 'context_wanneer_zin', { thema: themanaam_, n: tal((await pub.thema(thema))!.aantal), jaar: piekJaar,
                                                     piek: getal(taal, piek) });
      if (jaar) zin += ` ${tekst(taal, 'context_wanneer_deze', { jaar })}`;
      kaarten.push({ soort: 'wanneer', vraag: tekst(taal, 'context_wanneer_vraag'), thema,
                     jaren: jaren.map(([j, n]) => ({ jaar: j, aantal: n, aan: j === jaar })), zin,
                     href: `${verkennen}?thema=${thema}`, link: tekst(taal, 'context_wanneer_link') });
    }
  }

  const [soort, vorm] = p.kenmerk ?? ['', ''];
  if ((soort || vorm) && !vol()) {
    const filters = thema ? { thema } : {};
    const tellen = thema ? await themaTelling(pub, thema) : await kenmerkTelling(pub);
    const rijen = [];
    for (const [wat, waarde] of [['soort', soort], ['vorm', vorm]] as const) {
      if (!waarde) continue;
      const n = tellen[wat].get(waarde) ?? 0;
      rijen.push({ wat, waarde, naam: tekst(taal, `${wat}_${waarde}`), regel: wat === 'soort' ? tekst(taal, 'soort_volgens') : '',
                   zin: tekst(taal, `context_${wat}_${thema ? 'thema' : 'alle'}`, { n: tal(n), thema: themanaam_ }),
                   href: lijstUrl(taal, { ...filters, [wat]: [waarde] }) });
    }
    kaarten.push({ soort: 'kenmerk', vraag: tekst(taal, 'context_kenmerk_vraag'), rijen });
  }

  if (p.checks_lijst.length && !vol()) {
    const redactie = p.checks_lijst[0].redactie as string;
    // een naam met stuurtekens telt Python onder haar schone vorm: dan de hele telling, zoals daar
    const ruw = p.redactie_ruw!;
    const n = ruw === redactie ? await redactieTelling(pub, ruw) : new Map(await pub.redacties()).get(redactie) ?? 0;
    kaarten.push({ soort: 'redactie', vraag: tekst(taal, 'context_redactie_vraag'), naam: redactie,
                   zin: tekst(taal, 'context_redactie_zin', { n: tal(n) }), href: lijstUrl(taal, { redactie }),
                   link: tekst(taal, 'context_redactie_link') });
  }
  return kaarten.slice(0, CONTEXT_MAX);
}
