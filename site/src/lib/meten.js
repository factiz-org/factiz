// Meten met Google Analytics, alleen na een ja (B88, SPECS E9.S36, PLAN #34.2cg). De keuze blijft op het apparaat van de
// bezoeker, onder één sleutel; zonder ja laadt de site niets van Google en plaatst ze geen cookie. Na ja komt het script van
// Google zelf, nooit omgeleid via factiz.org: een adblocker die het tegenhoudt, respecteren we. Wat iemand instuurt (een
// geplakt bericht, een screenshot) gaat nooit naar Google; een zoekvraag alleen als ze getypt en kort is.
export const SLEUTEL = 'factiz-meten';

export function keuze() {
  try {
    const k = localStorage.getItem(SLEUTEL);
    return k === 'ja' || k === 'nee' ? k : null;
  } catch { return null; }
}

export function bewaar(k) {
  try { localStorage.setItem(SLEUTEL, k); } catch { /* de keuze geldt dan alleen voor deze pagina */ }
}

export function vergeet() {
  try { localStorage.removeItem(SLEUTEL); } catch { /* niets te vergeten */ }
}

// Een zoekvraag die naar Analytics mag (AC3): getypt, hoogstens acht woorden en honderd tekens, zonder e-mailadres,
// telefoonnummer of reeks van zes of meer cijfers (een jaartal mag). Google verbiedt persoonsgegevens in Analytics.
const MAIL = /\S+@\S+/;
const CIJFERS = /\d[\d\s().+-]{4,}\d/;
export function zoektermVoorMeten(vraag) {
  const q = (vraag ?? '').split(/\s+/).filter(Boolean).join(' ');
  if (!q || q.length > 100 || q.split(' ').length > 8) return null;
  if (MAIL.test(q) || CIJFERS.test(q)) return null;
  return q;
}

// Na ja: het script van Google, met Google signals en advertenties uit. Eén keer per pagina.
export function laadAnalytics(id) {
  if (window.gtag || !/^G-[A-Z0-9]{4,12}$/.test(id)) return;
  window.dataLayer = window.dataLayer || [];
  window.gtag = function gtag() { window.dataLayer.push(arguments); };
  window[`ga-disable-${id}`] = false;
  window.gtag('consent', 'default', { ad_storage: 'denied', ad_user_data: 'denied', ad_personalization: 'denied',
                                      analytics_storage: 'granted' });
  window.gtag('js', new Date());
  window.gtag('config', id, { allow_google_signals: false, allow_ad_personalization_signals: false });
  const s = document.createElement('script');
  s.async = true;
  s.src = `https://www.googletagmanager.com/gtag/js?id=${id}`;
  document.head.appendChild(s);
  for (const term of window.factizMeten || []) window.gtag('event', 'search', { search_term: term });
}

// Na nee (ook na een eerdere ja): niets meer meten en de cookies van Analytics wissen, op dit adres en het hoofddomein.
export function wisAnalytics(id) {
  window[`ga-disable-${id}`] = true;
  if (window.gtag) window.gtag('consent', 'update', { analytics_storage: 'denied' });
  const domeinen = ['', location.hostname, `.${location.hostname.split('.').slice(-2).join('.')}`];
  for (const naam of document.cookie.split(';').map((c) => c.split('=')[0].trim()).filter((n) => n.startsWith('_ga'))) {
    for (const d of domeinen) {
      document.cookie = `${naam}=; Max-Age=0; path=/${d ? `; domain=${d}` : ''}`;
    }
  }
}

// Een zoekvraag op de site (AC3): alleen na ja, nooit een geplakt bericht, en dezelfde vraag twee keer na elkaar één keer.
// Laadt Analytics nog, dan wacht de vraag in `window.factizMeten`.
export function meetZoekterm(vraag, bericht) {
  if (bericht || keuze() !== 'ja') return;
  const term = zoektermVoorMeten(vraag);
  if (!term) return;
  const wachtrij = (window.factizMeten = window.factizMeten || []);
  if (wachtrij[wachtrij.length - 1] === term) return;
  wachtrij.push(term);
  if (window.gtag) window.gtag('event', 'search', { search_term: term });
}
