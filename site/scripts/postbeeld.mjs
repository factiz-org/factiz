// Een post op X als beeld, voor een eigen factcheck (PLAN #37.4, B70, DESIGN §4x): via de openbare insluitpagina van X,
// zonder inloggen, in headless Chrome. Het ruwe beeld gaat als base64 naar stdout en komt nooit op schijf; de bewerking
// (onherkenbaar maken, verkleinen, stempel) doet `doublecheck/redactiebeeld.py` in het geheugen.
//   node site/scripts/postbeeld.mjs <postnummer>[:<taal>] ...      één regel JSON per post; de taal van de check (de
//   knoppen en de datum van X in die taal), anders Nederlands. De tijd op het beeld staat bij een Nederlandse check in de
//   tijd van Amsterdam, anders in UTC, zoals de tekst van een check in een andere taal haar tijden noemt
import { spawn } from 'node:child_process';
import { mkdtempSync, readFileSync, existsSync } from 'node:fs';
import { join } from 'node:path';
import { tmpdir } from 'node:os';

const talen = new Map(process.argv.slice(2).map((a) => a.match(/^([0-9]{5,25})(?::([a-z]{2}))?$/)).filter(Boolean)
  .map(([, n, t]) => [n, t ?? 'nl']));
const nummers = [...talen.keys()];
const zone = (taal) => (taal === 'nl' ? 'Europe/Amsterdam' : 'UTC');
const profiel = mkdtempSync(join(tmpdir(), 'factiz-post-'));
const chrome = spawn(process.env.CHROME ?? '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
  ['--headless=new', '--remote-debugging-port=0', `--user-data-dir=${profiel}`, '--no-first-run', '--disable-extensions',
   '--window-size=600,1200', 'about:blank'], { stdio: 'ignore' });
const poortbestand = join(profiel, 'DevToolsActivePort');
for (let i = 0; i < 200 && !existsSync(poortbestand); i++) await new Promise((ok) => setTimeout(ok, 50));
const [poort, wspad] = readFileSync(poortbestand, 'utf8').trim().split('\n');
const ws = new WebSocket(`ws://127.0.0.1:${poort}${wspad}`);
await new Promise((ok) => ws.addEventListener('open', ok));
let volg = 0;
const wacht = new Map();
const luister = new Set();
ws.addEventListener('message', (e) => {
  const m = JSON.parse(e.data);
  if (m.id && wacht.has(m.id)) { wacht.get(m.id)(m); wacht.delete(m.id); } else for (const f of luister) f(m);
});
const stuur = (method, params = {}, sessionId) => new Promise((ok) => {
  const id = ++volg; wacht.set(id, ok); ws.send(JSON.stringify({ id, method, params, sessionId }));
});
const slaap = (ms) => new Promise((ok) => setTimeout(ok, ms));

// De knop om de link te kopiëren, in de talen van de site zoals X ze schrijft (#37.10: daaronder staat alleen nog bediening);
// als tekst in de bladzijde, dus met dubbele backslashes
const KOPIEER_BRON = String.raw`link (naar post )?kopi|copy link|link zum post kopieren|copier le lien|copiar (enlace|link)|ポストへのリンクをコピー|gönderinin bağlantısını kopyala|पोस्ट का लिंक कॉपी|نسخ الرابط|کپی پیوند|копіювати посилання|копировать ссылку|salin tautan|複製貼文連結|复制帖子链接`;
// Waar de post staat, en waar de kop (profielfoto, naam, handle) en de media zitten, in CSS-pixels.
const METEN = `(() => {
  const KOPIEER = new RegExp(${JSON.stringify(KOPIEER_BRON)}, 'i');
  const art = document.querySelector('article') || document.querySelector('[data-testid="tweet"]') || document.body.firstElementChild;
  if (!art) return { fout: 'geen post' };
  const r = art.getBoundingClientRect();
  const tekst = (art.innerText || '').trim();
  const media = [...art.querySelectorAll('img, video')].map((m) => m.getBoundingClientRect())
    .filter((b) => b.width > 120 && b.height > 80).map((b) => ({ x: b.x - r.x, y: b.y - r.y, w: b.width, h: b.height }));
  const avatar = [...art.querySelectorAll('img')].map((m) => m.getBoundingClientRect()).find((b) => b.width > 20 && b.width < 80);
  const kop = avatar ? avatar.bottom - r.y + 6 : 64;
  // De knop "N antwoorden lezen" onderaan is bediening, geen deel van de post: daarboven knippen.
  // Onder de rij met "Link kopiëren" staat alleen nog bediening (antwoorden lezen, lees meer op X): daar knippen.
  const rij = [...art.querySelectorAll('*')]
    .filter((a) => KOPIEER.test(a.innerText || '') && (a.innerText || '').length < 45)
    .map((a) => a.getBoundingClientRect());
  const onder = rij.length ? Math.max(...rij.map((b) => b.bottom)) - r.y + 3 : r.height;
  // Een Community Note mag nooit op de site (DR3, #37.1): staat er een in de post, dan meldt het beeld dat.
  const note = /context toegevoegd|added context|lezers voegden|readers added/i.test(tekst)
    || !!art.querySelector('a[href*="birdwatch"], a[href*="communitynotes"]');
  return { x: r.x, y: r.y, w: r.width, h: r.height, kop, onder, media, note, tekst: tekst.length < 400 ? tekst : '',
           // alleen de korte melding van X zelf; een post die "niet meer" zegt, is gewoon een post
           onbeschikbaar: tekst.length < 120 && /^(niet gevonden|not found)$|unavailable|niet beschikbaar|doesn.t exist|bestaat niet/i.test(tekst) };
})()`;

for (const nummer of nummers) {
  const { result: { browserContextId } } = await stuur('Target.createBrowserContext', { disposeOnDetach: true });
  const { result: { targetId } } = await stuur('Target.createTarget', { url: 'about:blank', browserContextId });
  const { result: { sessionId } } = await stuur('Target.attachToTarget', { targetId, flatten: true });
  let geladen = false;
  const f = (m) => { if (m.sessionId === sessionId && m.method === 'Page.loadEventFired') geladen = true; };
  luister.add(f);
  await stuur('Page.enable', {}, sessionId);
  await stuur('Emulation.setTimezoneOverride', { timezoneId: zone(talen.get(nummer)) }, sessionId);
  await stuur('Emulation.setDeviceMetricsOverride', { width: 560, height: 2600, deviceScaleFactor: 2, mobile: false }, sessionId);
  await stuur('Page.navigate', { url: `https://platform.twitter.com/embed/Tweet.html?id=${nummer}&theme=light&dnt=true&lang=${talen.get(nummer)}&conversation=none&hideThread=true` }, sessionId);
  for (let i = 0; i < 200 && !geladen; i++) await slaap(100);
  await slaap(4000);
  const { result } = await stuur('Runtime.evaluate', { expression: METEN, returnByValue: true }, sessionId);
  const m = result?.result?.value ?? { fout: 'meten mislukt' };
  let beeld = null;
  if (!m.fout && m.w > 50 && m.h > 50) {
    const { result: shot } = await stuur('Page.captureScreenshot', {
      format: 'png', clip: { x: m.x, y: m.y, width: m.w, height: m.h, scale: 1 }, captureBeyondViewport: false }, sessionId);
    beeld = shot?.data ?? null;
  }
  luister.delete(f);
  console.log(JSON.stringify({ nummer, ...m, schaal: 2, beeld }));
  await stuur('Target.disposeBrowserContext', { browserContextId });
}
chrome.kill();
