// De gegevens van een start (PLAN #34.2): de filters uit het adres, en een zoekvraag uit een gepost formulier (zo werkt
// zoeken ook zonder script, en staat de vraag nooit in het adres).
import { haal, telZoekvraag, vraag as vraagAan } from './platform.js';

export async function startgegevens(Astro, taal = 'nl') {
  if (Astro.request.method === 'POST') {
    const bericht = await Astro.request.text();
    if (bericht.length > 8192) return null;
    const velden = new URLSearchParams(bericht);
    const vraag = (velden.get('q') || '').trim().slice(0, 200);
    const letterlijk = velden.get('letterlijk') === '1';
    const paren = [...new URLSearchParams(Astro.url.search)];
    if (vraag) {
      const zoekbericht = new URLSearchParams([['q', vraag], ...paren, ...(letterlijk ? [['letterlijk', '1']] : [])]).toString();
      const antwoord = await vraagAan(`/api/${taal}/zoek`, { methode: 'POST', bericht: zoekbericht });
      telZoekvraag(taal, zoekbericht, antwoord, Astro.request);     // anoniem opgeteld, als ze gewoon en kort is (B94)
      if (antwoord.status === 200) {
        const g = antwoord.body;
        // de volledige naam van een persoon of dossier, of een geplakte link: meteen naar die pagina (PLAN #34.2ac)
        if (g.doorsturen) return { doorsturen: `${g.doorsturen.href}${g.doorsturen.soort === 'factcheck' ? '' : '#gezocht'}` };
        const basis = await haal(`/api/${taal}/archief`);
        return { ...g, tellingen: basis.tellingen, dossiers: basis.dossiers, vraag, paren, letterlijk };
      }
    }
  }
  const g = await haal(`/api/${taal}/archief${Astro.url.search}`);
  return g && { ...g, vraag: '', paren: g.paren };
}
