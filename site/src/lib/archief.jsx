// Zoeken, filteren en sorteren op de start, voor alle drie de richtingen (PLAN #34.2). De gegevens komen van het
// platform; de filters gaan in het adres (terug en delen werken), de zoekvraag nooit.
import { useEffect, useRef, useState } from 'react';
import { MetWeg } from './weggelaten.jsx';

const MEER = new Set(['oordeel', 'taal', 'jaar']);
const zonderBlad = (paren) => paren.filter(([k]) => k !== 'p');
const adresVan = (paren) => new URLSearchParams(zonderBlad(paren)).toString();

// De zoekvraag staat in de geschiedenis van het tabblad (history.state), nooit in het adres (PLAN #34.2ac, SPECS E9.S14
// AC8): terug van een factcheck geeft dezelfde vraag, en een pagina die uit een formulier kwam, wordt een gewone pagina,
// zodat terug of herladen nooit vraagt het formulier opnieuw te sturen. Niets wordt opgeslagen: het verdwijnt met het
// tabblad (B75).
// `vast` (PLAN #34.2bb, SPECS E9.S27): filters die altijd meegaan naar het platform, zoals het thema op een themapagina,
// maar nooit in het adres staan en geen stukje zijn; `eigen` zijn de filters van de bezoeker.
export function useArchief(begin, { taal, basis, beginVraag = '', beginParen = null, beginLetterlijk = false, vast = [] }) {
  const vastSoorten = new Set(vast.map(([k]) => k));
  const eigen = (p) => p.filter(([k]) => !vastSoorten.has(k));
  const metVast = (p) => [...vast, ...eigen(p)];
  const [gegevens, zetGegevens] = useState(begin);
  const [paren, zetParen] = useState(beginParen ?? begin.paren ?? []);
  const [vraag, zetVraag] = useState(beginVraag);
  const [letterlijk, zetLetterlijk] = useState(beginLetterlijk);
  const [bezig, zetBezig] = useState(false);
  const volgnummer = useRef(0);
  const meting = useRef(null);
  // de stand van nu, ook voor wie verder laadt voordat React opnieuw getekend heeft
  const stand = useRef({ vraag: beginVraag, paren: beginParen ?? begin.paren ?? [], letterlijk: beginLetterlijk, blad: begin.blad ?? 1 });

  const adresMet = (schoon) => `${basis}${eigen(schoon).length ? `?${adresVan(eigen(schoon))}` : ''}`;
  const bericht = (q, schoon, ll, blad) => new URLSearchParams([['q', q], ...schoon, ...(ll ? [['letterlijk', '1']] : []),
    ...(blad ? [['p', String(blad)]] : [])]);

  async function haalOp(nieuw, metVraag, nieuwAdres = true, ll = false) {
    const schoon = eigen(zonderBlad(nieuw));
    const nummer = ++volgnummer.current;
    zetBezig(true);
    const antwoord = metVraag
      ? await fetch(`/${taal}/api/zoek`, { method: 'POST', body: bericht(metVraag, metVast(schoon), ll) })
      : await fetch(`/${taal}/api/archief${metVast(schoon).length ? `?${adresVan(metVast(schoon))}` : ''}`);
    if (nummer !== volgnummer.current) return null;
    if (!antwoord.ok) { zetBezig(false); return null; }
    const g = await antwoord.json();
    // de volledige naam van een persoon of dossier, of een geplakte link: meteen naar die pagina (AC4, AC5)
    if (g.doorsturen && nieuwAdres) {
      location.assign(`${g.doorsturen.href}${g.doorsturen.soort === 'factcheck' ? '' : '#gezocht'}`);
      return null;
    }
    stand.current = { vraag: metVraag, paren: schoon, letterlijk: ll, blad: g.blad ?? 1 };
    meting.current = { begin: performance.now(), adres: nieuwAdres ? adresMet(schoon) : null, staat: { vraag: metVraag, letterlijk: ll } };
    zetParen(schoon);
    zetVraag(metVraag);
    zetLetterlijk(ll);
    zetGegevens(g);
    zetBezig(false);
    return g;
  }

  // na het tekenen: de tijd van klik tot nieuwe lijst (M2), en een nieuwe plek in de geschiedenis met de vraag erbij
  useEffect(() => {
    if (!meting.current) return;
    const { begin: start, adres, staat } = meting.current;
    meting.current = null;
    (window.__filtertijden ??= []).push(performance.now() - start);
    window.dispatchEvent(new CustomEvent('factiz:gefilterd'));
    if (adres !== null) history.pushState(staat, '', adres);
  }, [gegevens]);

  useEffect(() => {
    // alleen terug, vooruit of herladen brengt een vraag en een plek terug; een nieuwe klik naar deze pagina (ook naar
    // hetzelfde adres) begint leeg
    const soort = performance.getEntriesByType?.('navigation')?.[0]?.type;
    if (!beginVraag && soort === 'navigate' && (history.state?.vraag || history.state?.plek)) {
      const { vraag: _v, letterlijk: _l, plek: _p, ...rest } = history.state;
      history.replaceState(rest, '');
    }
    // een pagina die uit een gepost formulier kwam: dezelfde plek in de geschiedenis, nu als gewone pagina met de vraag
    if (beginVraag) {
      history.replaceState({ ...(history.state ?? {}), vraag: beginVraag, letterlijk: beginLetterlijk },
                           '', adresMet(zonderBlad(beginParen ?? begin.paren ?? [])));
    }
    const terug = () => haalOp([...new URLSearchParams(location.search)], history.state?.vraag || '', false, !!history.state?.letterlijk);
    window.addEventListener('popstate', terug);
    return () => window.removeEventListener('popstate', terug);
  }, []);

  // Terug naar een plek met een zoekvraag die de pagina niet meer heeft (de browser haalde haar opnieuw op): eerst de
  // vraag opnieuw, dan pas de rijen en de plek. Geeft de gegevens die nu getoond worden.
  async function herstel() {
    const staat = history.state;
    if (beginVraag || !staat?.vraag) return gegevens;
    return (await haalOp([...new URLSearchParams(location.search)], staat.vraag, false, !!staat.letterlijk)) ?? gegevens;
  }

  // Meer laden (#501): het volgende blad erbij, zonder het adres te veranderen.
  // `blad` alleen bij het terugzetten van een plek: dan volgen de aanroepen elkaar op voordat de stand bijgewerkt is
  async function meer(blad) {
    const { vraag: q, paren: p, letterlijk: ll } = stand.current;
    const volgend = blad ?? stand.current.blad + 1;
    const antwoord = q
      ? await fetch(`/${taal}/api/zoek`, { method: 'POST', body: bericht(q, metVast(p), ll, volgend) })
      : await fetch(`/${taal}/api/archief?${new URLSearchParams([...metVast(p), ['p', String(volgend)]])}`);
    if (!antwoord.ok) return;
    const g = await antwoord.json();
    stand.current = { ...stand.current, blad: volgend };
    zetGegevens((oud) => ({ ...g, rijen: [...oud.rijen, ...g.rijen], blad: volgend }));
  }

  // Een lade op een telefoon (#1125): eerst klaarzetten en de aantallen zien, pas na "Toon n resultaten" toepassen.
  async function proef(nieuw) {
    const schoon = eigen(zonderBlad(nieuw));
    const { vraag: q, letterlijk: ll } = stand.current;
    const antwoord = q
      ? await fetch(`/${taal}/api/zoek`, { method: 'POST', body: bericht(q, metVast(schoon), ll) })
      : await fetch(`/${taal}/api/archief${metVast(schoon).length ? `?${adresVan(metVast(schoon))}` : ''}`);
    return antwoord.ok ? { ...(await antwoord.json()), paren: schoon } : null;
  }
  function toon(g) {
    const { vraag: q, letterlijk: ll } = stand.current;
    stand.current = { ...stand.current, paren: g.paren, blad: g.blad ?? 1 };
    meting.current = { begin: performance.now(), adres: adresMet(g.paren), staat: { vraag: q, letterlijk: ll } };
    zetParen(g.paren);
    zetGegevens(g);
  }

  function nieuweParen(huidig, soort, waarde) {
    let nieuw = zonderBlad(huidig);
    const heeft = nieuw.some(([k, w]) => k === soort && w === waarde);
    if (MEER.has(soort)) {
      nieuw = heeft ? nieuw.filter(([k, w]) => !(k === soort && w === waarde)) : [...nieuw, [soort, waarde]];
    } else {
      nieuw = nieuw.filter(([k]) => k !== soort && !(soort === 'thema' && k === 'onderdeel'));
      if (waarde && !heeft) nieuw.push([soort, waarde]);
    }
    return nieuw;
  }

  const kies = (soort, waarde) => haalOp(nieuweParen(paren, soort, waarde), vraag, true, letterlijk);

  const f = gegevens.filters;
  return {
    gegevens, f, vraag, bezig, paren, letterlijk, vastSoorten,
    kies, meer, proef, toon, nieuweParen, herstel,
    sorteer: (w) => haalOp([...paren.filter(([k]) => k !== 'sorteer'), ...(w ? [['sorteer', w]] : [])], vraag, true, letterlijk),
    // een nieuwe vraag: zonder de volgorde van de vorige, met het thema van een suggestie, en `ll` voor alleen de woorden
    zoek: (q, thema, ll = false) => haalOp([...paren.filter(([k]) => k !== 'sorteer' && !(thema && (k === 'thema' || k === 'onderdeel'))),
      ...(thema ? [['thema', thema]] : [])], (q || '').trim(), true, ll),
    wis: () => haalOp([], vraag, true, letterlijk),
    weg: (stukje) => haalOp(stukje.paren, vraag, true, letterlijk),
    gekozenThema: f.lijsten.thema.find((k) => k.aan)?.waarde ?? '',
  };
}

// De tekst van een rij: bij een zoekvraag de stukken met de gevonden woorden gemarkeerd; een weggelaten naam (#34.2bw)
// als sticker.
export function Tekst({ stukken, tekst }) {
  if (!stukken) return <MetWeg tekst={tekst} />;
  return stukken.map(([stuk, raak], i) => (raak ? <mark key={i}><MetWeg tekst={stuk} /></mark> : <span key={i}><MetWeg tekst={stuk} /></span>));
}
