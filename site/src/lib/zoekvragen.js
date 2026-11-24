// Wat mensen zoeken, anoniem en opgeteld (B94, PLAN #37.17): per dag en sitetaal de getypte zoekvraag met haar aantal, in
// dezelfde database als de tellers van B78 (in de Worker de D1 `TELLINGEN`). Nooit een IP-adres, cookie, user-agent of
// tijdstip binnen de dag, een robot of een geplakt bericht. Wat in zeven dagen minder dan drie keer kwam, gaat weg, zodat
// een naam of iets persoonlijks dat één iemand typt niet blijft. Lezen: `python -m factiz_site.tellen --zoekvragen`.
import { zoektermVoorMeten } from './meten.js';

// Alleen een gewone eerste zoekvraag: een filter, een andere volgorde of een volgend blad is een klik verder, geen nieuwe
// vraag. Een leeg veld telt niet (een formulier stuurt lege keuzes mee); `letterlijk` (tussen aanhalingstekens) mag.
const GEWOON = new Set(['q', 'letterlijk']);

// De zoekvraag om te tellen, of niets: getypt door een mens, kort en zonder contactgegevens (dezelfde regel als voor
// Analytics, `zoektermVoorMeten`, B88), in kleine letters. `body` is het antwoord van het platform (met `bericht`).
export function zoekvraagVoorTellen(bericht, body, robot) {
  if (robot || !body || body.bericht) return null;
  const velden = new URLSearchParams(bericht ?? '');
  for (const [k, v] of velden) if (!GEWOON.has(k) && v !== '') return null;
  const term = zoektermVoorMeten(velden.get('q') ?? '');
  return term ? term.toLowerCase() : null;
}

export const SCHEMA = 'CREATE TABLE IF NOT EXISTS zoekvraag (dag TEXT NOT NULL, taal TEXT NOT NULL, vraag TEXT NOT NULL, '
  + 'n INTEGER NOT NULL, vast INTEGER NOT NULL DEFAULT 0, PRIMARY KEY (dag, taal, vraag)) WITHOUT ROWID';
export const ERBIJ = 'INSERT INTO zoekvraag (dag, taal, vraag, n) VALUES (?, ?, ?, 1) '
  + 'ON CONFLICT (dag, taal, vraag) DO UPDATE SET n = n + 1';

// Opruimen (B94 punt 4), met als enige waarde de dag van zeven dagen terug (`opruimdag`): een rij van die dag of eerder
// blijft alleen als er zeven dagen zijn waarin ze valt en waarin dezelfde vraag in die taal samen minstens drie keer kwam.
// Zo'n week mag beginnen op de dag van een rij van die vraag (`s`), tot zes dagen ervoor; elke week die een rij van die dag
// of eerder bevat, is dan al helemaal voorbij. Wat blijft, krijgt `vast`, zodat het niet elke dag opnieuw beoordeeld wordt.
export const OPRUIMEN = [
  'DELETE FROM zoekvraag WHERE vast = 0 AND dag <= ?1 AND NOT EXISTS (SELECT 1 FROM zoekvraag s WHERE s.taal = zoekvraag.taal '
    + "AND s.vraag = zoekvraag.vraag AND s.dag BETWEEN date(zoekvraag.dag, '-6 days') AND zoekvraag.dag "
    + 'AND (SELECT SUM(z.n) FROM zoekvraag z WHERE z.taal = s.taal AND z.vraag = s.vraag '
    + "AND z.dag BETWEEN s.dag AND date(s.dag, '+6 days')) >= 3)",
  'UPDATE zoekvraag SET vast = 1 WHERE vast = 0 AND dag <= ?1',
];

export const opruimdag = (vandaag) => new Date(Date.parse(`${vandaag}T00:00:00Z`) - 7 * 864e5).toISOString().slice(0, 10);
