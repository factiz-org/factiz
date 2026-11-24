// De talen van het platform (B74, B79), gelijk aan `factiz_site/i18n.py`: dezelfde woordenlijsten en de ene lijst van
// sitetalen. Een model vertaalt hier niets (PLAN #34.2bo stap 3).
import sitetalen from '../../../factiz_site/teksten/sitetalen.json' with { type: 'json' };
import talenlijst from '../../../factiz_site/teksten/talen.json' with { type: 'json' };
import en from '../../../factiz_site/teksten/en.json' with { type: 'json' };
import nl from '../../../factiz_site/teksten/nl.json' with { type: 'json' };
import de from '../../../factiz_site/teksten/de.json' with { type: 'json' };
import es from '../../../factiz_site/teksten/es.json' with { type: 'json' };
import fr from '../../../factiz_site/teksten/fr.json' with { type: 'json' };
import pt from '../../../factiz_site/teksten/pt.json' with { type: 'json' };
import ru from '../../../factiz_site/teksten/ru.json' with { type: 'json' };
import uk from '../../../factiz_site/teksten/uk.json' with { type: 'json' };
import id from '../../../factiz_site/teksten/id.json' with { type: 'json' };
import tr from '../../../factiz_site/teksten/tr.json' with { type: 'json' };
import zh from '../../../factiz_site/teksten/zh.json' with { type: 'json' };
import ja from '../../../factiz_site/teksten/ja.json' with { type: 'json' };
import hi from '../../../factiz_site/teksten/hi.json' with { type: 'json' };
import ar from '../../../factiz_site/teksten/ar.json' with { type: 'json' };
import fa from '../../../factiz_site/teksten/fa.json' with { type: 'json' };

type Lijst = Record<string, unknown> & { maanden: string[]; datum_vorm: string; maanden_jaar: string[]; maand_jaar_vorm: string };
const LIJSTEN: Record<string, Lijst> = Object.fromEntries(
  Object.entries({ en, nl, de, es, fr, pt, ru, uk, id, tr, zh, ja, hi, ar, fa })
    .map(([taal, bestand]) => [taal, (bestand as { teksten: Lijst }).teksten]));

type Sitetaal = { code: string; bcp47: string; pad: string; naam: string; locale: string; duizendtal: string };
const SITETALEN = (sitetalen as { talen: Sitetaal[] }).talen;

export const TALEN: string[] = SITETALEN.map((t) => t.code);
export const STANDAARD = 'en';
const PAD: Record<string, string> = Object.fromEntries(SITETALEN.map((t) => [t.code, t.pad]));
const DUIZENDTAL: Record<string, string> = Object.fromEntries(SITETALEN.map((t) => [t.code, t.duizendtal]));

function teksten(taal: string): Lijst {
  const lijst = LIJSTEN[taal];
  if (!lijst) throw new Error(`geen taal: ${taal}`);
  return lijst;
}

// `str.format`: {naam} wordt de waarde, {{ en }} worden { en }. Zonder waarden blijft de vorm zoals hij is.
function vul(vorm: string, waarden: Record<string, unknown>): string {
  return vorm.replace(/\{\{|\}\}|\{(\w+)\}/g, (heel, naam) => {
    if (heel === '{{') return '{';
    if (heel === '}}') return '}';
    if (!(naam in waarden)) throw new Error(`geen waarde voor {${naam}}`);
    return String(waarden[naam]);
  });
}

// Een vaste tekst, met de blanco's ingevuld; een sleutel die niet bestaat is een fout, geen lege plek.
export function tekst(taal: string, sleutel: string, waarden: Record<string, unknown> = {}): string {
  const vorm = teksten(taal)[sleutel];
  if (typeof vorm !== 'string') throw new Error(`geen tekst: ${sleutel}`);
  return Object.keys(waarden).length ? vul(vorm, waarden) : vorm;
}

// Een naam die Factiz bewust weglaat (maatregel 2, PLAN #34.2bw, `i18n.WEGGELATEN`): het merkteken in de uitgave. In de
// gegevens wordt het ⟦naam weggelaten⟧ (`gemerkt`, de site maakt er een sticker van), in een titel, omschrijving, de
// gestructureerde gegevens en het deelplaatje [naam weggelaten] (`plat`).
export const WEGGELATEN = '\u27e6redacted\u27e7';

export function plat(taal: string, tekst_: string): string {
  return tekst_ && tekst_.includes(WEGGELATEN) ? tekst_.split(WEGGELATEN).join(`[${tekst(taal, 'weggelaten')}]`) : tekst_;
}

export function gemerkt(taal: string): string {
  return `\u27e6${tekst(taal, 'weggelaten')}\u27e7`;
}

// In elk antwoord met gegevens het merkteken als ⟦naam weggelaten⟧ (zoals `app.Weggelaten`); een object dat niets bevat,
// blijft hetzelfde object (het geheugen van de Worker deelt ze).
export function merkDiep<T>(x: T, door: string): T {
  if (typeof x === 'string') return (x.includes(WEGGELATEN) ? x.split(WEGGELATEN).join(door) : x) as T;
  if (Array.isArray(x)) {
    let anders = false;
    const uit = x.map((y) => { const z = merkDiep(y, door); anders ||= z !== y; return z; });
    return (anders ? uit : x) as T;
  }
  if (x && typeof x === 'object' && Object.getPrototypeOf(x) === Object.prototype) {
    let anders = false;
    const uit: Record<string, unknown> = {};
    for (const [k, y] of Object.entries(x as Record<string, unknown>)) { const z = merkDiep(y, door); anders ||= z !== y; uit[k] = z; }
    return (anders ? uit : x) as T;
  }
  return x;
}

// Het adres binnen de site: Engels op de hoofdmap, de andere talen onder hun code.
export function pad(taal: string, ...delen: (string | null | undefined)[]): string {
  const stukken = [...(taal === STANDAARD ? [] : [PAD[taal]]), ...delen.filter((d): d is string => !!d)];
  return '/' + stukken.map((s) => `${s}/`).join('');
}

export function getal(taal: string, n: number): string {
  return String(n).replace(/\B(?=(\d{3})+(?!\d))/g, DUIZENDTAL[taal]);
}

// `Snopes, Maldita en AFP`.
export function opsomming(taal: string, namen: string[]): string {
  if (namen.length < 2) return namen.join('');
  return `${namen.slice(0, -1).join(', ')} ${tekst(taal, 'opsomming_en')} ${namen[namen.length - 1]}`;
}

// Python `int()` op een stuk van een datum: cijfers, met witruimte en een teken eromheen.
function geheel(stuk: string): number | null {
  return /^\s*[+-]?\d+\s*$/u.test(stuk) ? parseInt(stuk, 10) : null;
}

// `2024-03-05` in de vorm van de taal; een datum die er niet is of niet klopt, blijft leeg (`i18n.datum`).
export function datum(taal: string, iso: string | null | undefined): string {
  const delen = (iso ?? '').split('-');
  if (delen.length !== 3) return '';
  const [jaar, maand, dag] = delen.map(geheel);
  if (jaar === null || maand === null || dag === null) return '';
  const maanden = teksten(taal).maanden;
  let index = maand - 1;                              // Python: een negatieve plek telt van achteren
  if (index < -maanden.length || index >= maanden.length) return '';
  if (index < 0) index += maanden.length;
  if (dag < 1 || dag > 31) return '';
  const dagtekst = taal === 'fr' && dag === 1 ? '1er' : String(dag);
  return vul(teksten(taal).datum_vorm, { dag: dagtekst, maand: maanden[index], jaar });
}

// `2026-11` als maand met haar jaar in de vorm van de taal (`november 2026`), uit CLDR (`i18n.maand_jaar`, PLAN #37.11)
export function maandJaar(taal: string, maand: string | null | undefined): string {
  const delen = (maand ?? '').split('-');
  if (delen.length !== 2) return '';
  const [jaar, m] = delen.map(geheel);
  if (jaar === null || m === null || m < 1 || m > 12) return '';
  return vul(teksten(taal).maand_jaar_vorm, { maand: teksten(taal).maanden_jaar[m - 1], jaar });
}

export const LABELS = ['onwaar', 'misleidend', 'onwaar-of-misleidend', 'waar', 'deels-waar', 'omstreden', 'satire', 'onbewezen'];

// het oordeel van de redacties als stempel (PLAN #34.2cc, DESIGN §4y; `i18n.stempel` en `i18n.volgens`)
const STEMPEL_EIGEN: Record<string, string> = { onwaar: 'eigen_oordeel_onwaar', misleidend: 'eigen_oordeel_misleidend',
                                                onbewezen: 'eigen_oordeel_onbewezen', waar: 'eigen_oordeel_klopt' };

export function stempel(taal: string, klasse: string | null | undefined): string {
  if (klasse && STEMPEL_EIGEN[klasse]) return tekst(taal, STEMPEL_EIGEN[klasse]);
  return tekst(taal, klasse && LABELS.includes(klasse) ? `stempel_${klasse.replace(/-/g, '_')}` : 'stempel_geen');
}

export function volgens(taal: string, klasse: string | null | undefined, namen: string[] | null | undefined, hoogstens = 4): string {
  const alle = [...(namen ?? [])];
  if (!alle.length) return '';
  const vast = Math.max(1, hoogstens - 1);   // zoveel namen voor *en N andere*; in een titel één (`i18n.volgens`)
  // nooit *en 1 andere*: is er één naam meer, dan staat die er gewoon (`i18n.volgens`)
  const lijst = alle.length <= Math.max(hoogstens, vast + 1) ? alle
    : [...alle.slice(0, vast), tekst(taal, 'stempel_andere', { n: getal(taal, alle.length - vast) })];
  const soort = klasse === 'omstreden' ? 'stempel_tussen' : klasse && LABELS.includes(klasse) ? 'stempel_volgens' : 'stempel_door';
  return tekst(taal, soort, { wie: opsomming(taal, lijst) });
}

// het stempel met wie het zegt in één regel, voor een titel en een omschrijving (`i18n.oordeel_kop`)
export function oordeelKop(taal: string, klasse: string | null | undefined, namen: string[] | null | undefined): string {
  return `${stempel(taal, klasse)} ${volgens(taal, klasse, namen, 1)}`.trim();
}

export function label(taal: string, klasse: string | null | undefined): string {
  return tekst(taal, klasse && LABELS.includes(klasse) ? `label_${klasse.replace(/-/g, '_')}` : 'label_geen');
}

const TAALNAMEN = (talenlijst as { talen: Record<string, Record<string, string>> }).talen;

// De naam van een taal in de taal van de site (*Hindi*, *hindi*); een code zonder naam blijft de code (`taalnaam_in`).
export function taalnaamIn(taal: string, code: string | null | undefined): string {
  const kort_ = (code ?? '').split('-')[0].toLowerCase();
  return Object.hasOwn(TAALNAMEN, kort_) && Object.hasOwn(TAALNAMEN[kort_], taal) ? TAALNAMEN[kort_][taal] : (code ?? '');
}

export const BASIS = 'https://factiz.org';
export const BCP47: Record<string, string> = Object.fromEntries(SITETALEN.map((t) => [t.code, t.bcp47]));
export const EIGEN_NAAM: Record<string, string> = Object.fromEntries(SITETALEN.map((t) => [t.code, t.naam]));
const RTL = new Set(["ar", "ckb", "dv", "fa", "he", "ps", "sd", "ug", "ur", "yi"]);

export function richting(taal: string | null | undefined): string {
  return RTL.has((taal ?? '').split('-')[0].toLowerCase()) ? 'rtl' : 'ltr';
}

// De naam van een taal in die taal zelf, voor de taal van een bewering of een check (`i18n.TAALNAAM`).
export const TAALNAAM: Record<string, string> = {"af": "Afrikaans", "am": "አማርኛ", "ar": "العربية", "as": "অসমীয\u09bcা", "az": "Azərbaycanca", "bn": "বাংলা", "ca": "Català", "de": "Deutsch", "en": "English", "es": "Español", "fa": "فارسی", "fr": "Français", "ga": "Gaeilge", "gl": "Galego", "gu": "ગ\u0ac1જરાતી", "he": "עברית", "hi": "हिन\u094dदी", "hr": "Hrvatski", "id": "Bahasa Indonesia", "it": "Italiano", "ja": "日本語", "km": "ខ\u17d2មែរ", "kn": "ಕನ\u0ccdನಡ", "ko": "한국어", "lo": "ລາວ", "ml": "മലയാളം", "mn": "Монгол", "mr": "मराठी", "ms": "Bahasa Melayu", "ne": "न\u0947पाली", "nl": "Nederlands", "pa": "ਪ\u0a70ਜਾਬੀ", "pl": "Polski", "pt": "Português", "ro": "Română", "ru": "Русский", "si": "ස\u0dd2ංහල", "sw": "Kiswahili", "ta": "தமிழ\u0bcd", "te": "త\u0c46లుగు", "th": "ไทย", "tl": "Filipino", "tr": "Türkçe", "ur": "اردو", "vi": "Tiếng Việt", "zh": "中文", "bs": "Bosanski", "om": "Afaan Oromoo", "sl": "Slovenščina", "so": "Soomaali", "sr": "Српски", "ti": "ትግርኛ", "uk": "Українська"};

export function taalnaam(code: string | null | undefined): string {
  const k = (code ?? '').split('-')[0].toLowerCase();
  return Object.hasOwn(TAALNAAM, k) ? TAALNAAM[k] : (code ?? '');
}

// De talen van de site waarin een pagina eigen hoofdtekst heeft (`i18n.eigen_talen`); anders de hoofdmap.
export function eigenTalen(taalBewering: string, vertalingen: Iterable<string>): string[] {
  const v = new Set(vertalingen);
  const talen = TALEN.filter((t) => t === taalBewering || v.has(t));
  return talen.length ? talen : [STANDAARD];
}

export function xDefault(talen: string[]): string {
  return talen.includes(STANDAARD) ? STANDAARD : talen[0];
}

// `3 newsrooms, 3 languages, 2023\u20132024`: een telling, nooit een schatting (`i18n.telregel`).
export function telregel(taal: string, redacties: number, talen: number, eerste: string | null, laatste: string | null): string {
  const delen = [tekst(taal, redacties === 1 ? 'redacties_een' : 'redacties_meer', { n: getal(taal, redacties) }),
                 tekst(taal, talen === 1 ? 'talen_een' : 'talen_meer', { n: getal(taal, talen) })];
  const van = (eerste ?? '').slice(0, 4);
  const tot = (laatste ?? '').slice(0, 4);
  if (van && tot) delen.push(van === tot ? van : `${van}\u2013${tot}`);
  return delen.join(', ');
}
