// Roept een tekstfunctie van het platform aan op een lijst argumenten (PLAN #34.2bo stap 3), voor de toets die haar
// naast de Python-functie legt:  node scripts/platform-functie.ts <naam>  <  [[arg1, arg2], …]
import { lijstUrl } from '../src/platform/api.ts';
import { datum, getal, opsomming, pad } from '../src/platform/i18n.ts';
import { kort, link, schoon } from '../src/platform/tekst.ts';

const FUNCTIES: Record<string, (...a: never[]) => unknown> = { kort, link, schoon, datum, getal, opsomming, pad, lijstUrl };
const functie = FUNCTIES[process.argv[2]];
if (!functie) {
  console.error(`onbekende functie: ${process.argv[2]}`);
  process.exit(2);
}
let invoer = '';
for await (const stuk of process.stdin) invoer += stuk;
process.stdout.write(JSON.stringify((JSON.parse(invoer) as never[][]).map((args) => functie(...args))));
