// De talen en hun adressen (PLAN #34.2c, DESIGNSYSTEEM §6, B79). Engels op de hoofdmap, elke andere taal onder haar pad
// (/nl/, /pt-br/, /zh-hant/); het pad na de taal is in elke taal gelijk, dus de taalkiezer verwisselt alleen het
// voorvoegsel. De ene lijst van het platform (`factiz_site/teksten/sitetalen.json`), in dezelfde volgorde.
import lijst from '../../../factiz_site/teksten/sitetalen.json';

export const TALEN = lijst.talen.map((t) => t.code);
export const STANDAARD = 'en';
// de vijf talen van B74, waarvan een mens de teksten zag; de placeholder blijft daarbij tot de PO anders beslist
export const BASIS_TALEN = lijst._meta.basis;
// de code naar buiten (lang, hreflang) en het pad: pt-BR en /pt-br/, zh-Hant en /zh-hant/
export const BCP47 = Object.fromEntries(lijst.talen.map((t) => [t.code, t.bcp47]));
export const PAD = Object.fromEntries(lijst.talen.map((t) => [t.code, t.pad]));
export const VAN_PAD = Object.fromEntries(lijst.talen.filter((t) => t.pad).map((t) => [t.pad, t.code]));
// og:locale in de vorm taal_LAND (pt_BR, zh_TW)
export const OG_LOCALE = Object.fromEntries(lijst.talen.map((t) => {
  const delen = t.locale.split('-u-')[0].split('-');
  return [t.code, delen.length > 1 ? `${delen[0]}_${delen.at(-1)}` : delen[0]];
}));
// talen van rechts naar links (PLAN #34.2bd, SPECS E9.S29): de pagina krijgt dir="rtl" en de opmaak spiegelt
export const RTL = new Set(['ar', 'fa', 'he', 'ur']);
export const richting = (taal) => (RTL.has(taal) ? 'rtl' : 'ltr');
export const EIGEN_NAAM = Object.fromEntries(lijst.talen.map((t) => [t.code, t.naam]));
export const LOCALE = Object.fromEntries(lijst.talen.map((t) => [t.code, t.locale]));
// De volgorde in de taalkiezer en de voet (PLAN #34.2bi): op elke pagina dezelfde, op de code (AR tot ZH), zoals de
// taalkiezer van het W3C; de code staat vooraan op elke regel, dus die kolom loopt van A tot Z (PO: "Op code").
export const KIESVOLGORDE = [...TALEN].sort();
// Het echte adres van de site, voor canonical en hreflang.
export const BASIS = 'https://factiz.org';

const stukken = (taal, delen) => [...(taal === STANDAARD ? [] : [PAD[taal]]), ...delen.filter(Boolean)];

// Een adres binnen de site: /fact-checks/7726…/ in het Engels, /nl/fact-checks/7726…/ in het Nederlands.
export const pad = (taal, ...delen) => `/${stukken(taal, delen).map((s) => `${s}/`).join('')}`;

// Hetzelfde adres, volledig, voor canonical en hreflang.
export const adresSite = (taal, ...delen) => `${BASIS}${pad(taal, ...delen)}`;

// De naam van een taal in de taal van de pagina (Duits, Allemand), voor wie zoekt in de taalkiezer.
export function naamIn(taal, code) {
  try { return new Intl.DisplayNames([LOCALE[taal]], { type: 'language' }).of(code) ?? code; } catch { return code; }
}

// Een adres zoals het platform het noemt, op de site. Sinds #34.2r tot #34.2u heeft de site elke pagina zelf (namen,
// thema's, dossiers), dus het is hetzelfde adres; de functie blijft de ene plek als dat ooit weer anders wordt.
export function naarSite(href) {
  return href;
}

