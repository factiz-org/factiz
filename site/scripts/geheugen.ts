// Het geheugen van een uitgave vooraf berekenen (B80, PLAN #34.2bo stap 3c):
//   node scripts/geheugen.ts <publicatie.db> <uitmap> [--alles]
// Warmt het platform op met echte verzoeken (elke soort ingang, zoeken met een afkorting, een link en een geplakt bericht),
// en schrijft elk stuk dat het daarbij één keer rekende als bestand weg, met `index.json` erbij. De Worker leest die
// bestanden in plaats van ze opnieuw te rekenen; het antwoord blijft hetzelfde (`factiz_site.gelijk` met FACTIZ_GEHEUGEN).
import { mkdirSync, rmSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { antwoord, publicatie } from '../src/platform/api.ts';
import { bewaar, lees } from '../src/platform/geheugen.ts';
import { zoeker } from '../src/platform/zoeken-motor.ts';
import { ZONDER_SPATIES } from '../src/platform/zoeken-tekst.ts';
import { openDb } from './platform-node.ts';
import { buren, netwerkNamen, redactieTelling, themaTelling } from '../src/platform/factcheck-gegevens.ts';
import { rijen } from '../src/platform/db.ts';

const [, , bestand, uit, vlag] = process.argv;
const ALLES = vlag === '--alles';       // elk stuk bewaren, ook een groot stuk dat bijna even snel te rekenen is (de toets)
// Wat altijd mee moet, hoe snel het hier ook rekent: één lijst met `worker-voorraad.mjs` (`geheugen-nodig.mjs`).
import { NODIG } from './geheugen-nodig.mjs';
// Wat een nieuwe Worker zelf maakt uit wat wel bewaard is, goedkoper dan het lezen: de kolommen uit hun kern.
const AFGELEID = ['kolommen'];
// Een bestandsnaam met alleen veilige tekens: de bestandsserver van de Worker leest %3A als een dubbele punt.
const veilig = (naam: string) => naam.replace(/[^A-Za-z0-9-]/g, (c) => `_${c.codePointAt(0)!.toString(16)}_`);
if (!bestand || !uit) {
  console.error('gebruik: node scripts/geheugen.ts <publicatie.db> <uitmap>');
  process.exit(2);
}
const db = openDb(bestand);
const pub = publicatie(db);
// elk stuk vastleggen zodra het af is, voordat een volgende vraag het aanvult
const vastgelegd = new Map<string, string | null>();
pub.opnemen = (naam, waarde) => {
  try { vastgelegd.set(naam, bewaar(waarde)); } catch { vastgelegd.set(naam, null); }
};
const begin = Date.now();
const vraag = (pad: string, bericht: string | null = null) => {
  const url = new URL(pad, 'http://platform');
  return antwoord(db, url.pathname, url.searchParams, bericht === null ? {} : { methode: 'POST', bericht });
};

// een nummer, een thema, een dossier en een naam uit deze uitgave
const lijst = (await vraag('/api/en/archief')).body as { rijen: { nummer: string }[] };
const themas = await pub.themas();
const dossiers = await pub.dossiers();
const namen = [...(await pub.namen()).keys()];
const nummer = lijst.rijen[0]?.nummer;
const adres = (await db.prepare('SELECT url FROM check_ LIMIT 1').first<{ url: string }>())?.url ?? '';
const verzoeken: [string, string | null][] = [
  ['/api/en/archief?sorteer=oud', null], ['/api/en/archief?sorteer=redacties', null], ['/api/en/themas', null],
  ['/api/en/dossiers', null], ['/api/en/redacties', null], ['/api/en/bronnen', null], ['/api/en/namen', null],
  ['/api/en/verkennen', null], ['/api/en/netwerk', null],
  ...(nummer ? [[`/api/en/factcheck/${nummer}`, null] as [string, null]] : []),
  ...(themas[0] ? [[`/api/en/thema/${themas[0].sleutel}`, null], [`/api/en/verkennen?thema=${themas[0].sleutel}`, null]] as [string, null][] : []),
  ...(dossiers[0] ? [[`/api/en/dossier/${dossiers[0].sleutel}`, null] as [string, null]] : []),
  ...(namen[0] ? [[`/api/en/naam/${namen[0]}`, null] as [string, null]] : []),
  ['/api/en/zoek', 'q=vaccine'], ['/api/en/zoek', 'q=WHO+vaccine'], ['/api/en/zoek', 'q=vacinne'],
  ['/api/en/zoek', `q=${encodeURIComponent(adres)}`],
  ['/api/en/zoek', `q=${encodeURIComponent('Forwarded many times: the government has confirmed that the new vaccine contains a microchip that tracks every citizen')}`],
  ['/api/en/suggesties', 'q=zel'], ['/api/en/suggesties', 'q=vacc'],
];
for (const [pad, bericht] of verzoeken) {
  const a = await vraag(pad, bericht);
  if (a.status >= 500) throw new Error(`${pad}: ${a.status}`);
}
// elk thema, onderdeel en dossier, en de tellingen die een factcheckpagina per thema, redactie en naam vraagt: hier is elk
// een vraag van 0,1 ms, in de Worker een vraag na de andere van ~20 ms, en een thema telt 33.000 tot 53.000 rijen
for (const t of themas) {
  for (const pad of [`/api/en/thema/${t.sleutel}`, `/api/en/verkennen?thema=${t.sleutel}`]) await vraag(pad);
  for (const o of t.onderdelen) await vraag(`/api/en/thema/${t.sleutel}/${o.sleutel}`);
  await themaTelling(pub, t.sleutel);
}
for (const d of dossiers) await vraag(`/api/en/dossier/${d.sleutel}`);
for (const { r } of await rijen<{ r: string }>(db, 'SELECT DISTINCT redactie AS r FROM check_')) await redactieTelling(pub, r);
const net = await netwerkNamen(pub);
for (const n of net) await buren(pub, n.nummer, net);
// en wat de Worker nooit zelf mag rekenen, hoe deze uitgave ook is (een uitgave zonder afkortingen vraagt er geen op)
const z = await zoeker(pub);
await Promise.all([z.hoofdletters(), (z as unknown as { adressen(): Promise<unknown> }).adressen(),
  pub.kolommen(), pub.themas()]);
// de kandidaten voor een tikfout, per beginletter (#37.16): anders haalt de Worker bij een tikfout duizenden woorden uit D1;
// niet voor de schriften zonder spaties, daar verbetert de site geen tikfouten
for (const { b } of await rijen<{ b: string }>(db, 'SELECT DISTINCT substr(term, 1, 1) AS b FROM woord WHERE kandidaat = 1')) {
  if (!ZONDER_SPATIES.test(b)) await z.tikfoutKandidaten(b);
}

rmSync(uit, { recursive: true, force: true });
mkdirSync(uit, { recursive: true });
const index: { naam: string; bestand: string; bytes: number; rekentijd: number; leestijd: number }[] = [];
for (const [naam, tekst] of vastgelegd) {
  if (tekst === null) continue;     // iets met eigen gedrag (de zoeker zelf): dat maakt de Worker opnieuw, goedkoop
  if (AFGELEID.includes(naam)) continue;
  // alles bewaren: hier kost een vraag aan de uitgave 0,1 ms, in de Worker kost elke vraag aan D1 ~25 ms (gemeten op het
  // testadres, stap 8), dus wat hier snel rekent, kost daar een nieuwe Worker tientallen vragen na elkaar
  const lezen = Date.now();
  lees(tekst);
  const leestijd = Date.now() - lezen;
  const rekentijd = pub.rekentijd.get(naam) ?? 0;
  const nodig = NODIG.includes(naam);
  // een groot stuk dat bijna even snel te rekenen is (het namenregister herhaalt elke naam per taal): niet bewaren
  if (!ALLES && !nodig && tekst.length > 5e6 && rekentijd < 3 * leestijd) continue;
  const naamBestand = `${veilig(naam)}.json`;
  writeFileSync(join(uit, naamBestand), tekst);
  index.push({ naam, bestand: naamBestand, bytes: Buffer.byteLength(tekst), rekentijd, leestijd });
}
const ontbreekt = NODIG.filter((n) => !index.some((i) => i.naam === n));
if (ontbreekt.length) throw new Error(`het opwarmen rekende niet: ${ontbreekt.join(', ')}`);
const meta = await pub.meta();
writeFileSync(join(uit, 'index.json'), JSON.stringify({ release: meta.release, controlegetal: meta.controlegetal, stukken: index }, null, 1));
const totaal = index.reduce((s, i) => s + i.bytes, 0);
console.log(`${index.length} stukken, ${(totaal / 1e6).toFixed(1)} MB, in ${((Date.now() - begin) / 1000).toFixed(1)} s`);
for (const i of index.sort((a, b) => b.bytes - a.bytes)) console.log(`  ${(i.bytes / 1e6).toFixed(2)} MB  rekenen ${i.rekentijd} ms, lezen ${i.leestijd} ms  ${i.naam}`);
