// De site op een telefoon (2026-11-17): per pagina en breedte wat de pagina breder maakt dan het scherm, een veld onder
// 16 px (iOS zoomt dan in), een tikdoel onder 44 px en tekst die wordt afgekapt. Headless Chrome via CDP, als telefoon
// (mobile, touch, pointer: coarse), elke pagina in een lege context. Eén regel JSON per pagina en breedte.
//   node site/scripts/mobiel.mjs <basis> <breedtes, bv 320,414> <pad>[#staat] ...     staat: palet | menu | taal | filter
// Met BEELD=<map> ook een schermafdruk per pagina. Chrome uit CHROME, anders de gewone plek op een Mac. De wereldkaart, de
// ring van thema's en het netwerk van namen hebben kleine vlakken met een lijst ernaast; die zijn bewust klein.
import { spawn } from 'node:child_process';
import { mkdtempSync, readFileSync, existsSync, rmSync } from 'node:fs';
import { join } from 'node:path';
import { tmpdir } from 'node:os';

const [basis, breedtesTekst, ...paden] = process.argv.slice(2);
const breedtes = breedtesTekst.split(',').map(Number);
const profiel = mkdtempSync(join(tmpdir(), 'factiz-mobiel-'));
const chrome = spawn(process.env.CHROME ?? '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
  ['--headless=new', '--remote-debugging-port=0', `--user-data-dir=${profiel}`, '--no-first-run', '--disable-extensions',
   '--window-size=414,900', 'about:blank'], { stdio: 'ignore' });
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

const OPEN = {
  palet: `document.querySelector('.zoekknop')?.click()`,
  menu: `[...document.querySelectorAll('header button')].find(b => b.offsetParent && b.className.includes('knop-stil'))?.click()`,
  taal: `document.querySelector('button[aria-controls="taalkiezer"]')?.click()`,
  filter: `[...document.querySelectorAll('button.knop')].find(b => b.offsetParent && /filter/i.test(b.textContent))?.click()`,
};

const METEN = `(() => {
  const vw = document.documentElement.clientWidth;
  const naam = (el) => {
    let s = el.tagName.toLowerCase();
    if (el.id) s += '#' + el.id;
    const k = (typeof el.className === 'string' ? el.className : el.className?.baseVal ?? '').trim().split(/\\s+/).filter(Boolean).slice(0, 4);
    if (k.length) s += '.' + k.join('.');
    return s;
  };
  const pad = (el) => { const d = []; for (let p = el; p && p !== document.body && d.length < 4; p = p.parentElement) d.unshift(naam(p)); return d.join(' > '); };
  const zichtbaar = (el) => { const s = getComputedStyle(el); return s.display !== 'none' && s.visibility !== 'hidden' && el.getClientRects().length; };
  const geknipt = (el) => {
    for (let p = el.parentElement; p && p !== document.documentElement; p = p.parentElement) {
      const s = getComputedStyle(p);
      if (/(auto|scroll|hidden|clip)/.test(s.overflowX)) { const r = p.getBoundingClientRect(); if (r.left >= -1 && r.right <= vw + 1) return true; }
    }
    return false;
  };
  const buiten = (el) => { const r = el.getBoundingClientRect(); return r.width > 0 && (r.right > vw + 1 || r.left < -1); };
  const breekt = [];
  for (const el of document.body.querySelectorAll('*')) {
    if (!zichtbaar(el) || !buiten(el) || geknipt(el)) continue;
    if (getComputedStyle(el).position === 'fixed' && el.closest('[aria-hidden="true"]')) continue;
    const kind = [...el.children].some((c) => zichtbaar(c) && buiten(c) && !geknipt(c));
    if (kind) continue;                                   // alleen de diepste: die duwt
    const r = el.getBoundingClientRect();
    breekt.push({ el: pad(el), links: Math.round(r.left), rechts: Math.round(r.right), tekst: (el.textContent || '').trim().slice(0, 50) });
  }
  const invoer = [...document.querySelectorAll('input, select, textarea')].filter((el) => zichtbaar(el) && el.type !== 'checkbox' && el.type !== 'radio' && el.type !== 'hidden')
    .map((el) => ({ el: pad(el), px: parseFloat(getComputedStyle(el).fontSize) })).filter((x) => x.px < 16);
  const klein = [];
  for (const el of document.querySelectorAll('a, button, input, select, summary, [role="button"], [role="option"], label')) {
    if (!zichtbaar(el)) continue;
    const r = el.getBoundingClientRect();
    if (!r.width) continue;
    if (el.tagName === 'A' && getComputedStyle(el).display === 'inline' && el.parentElement?.closest('p, li, dd, td, figcaption, .rij-bron')) continue;   // een link in lopende tekst
    if (el.tagName === 'LABEL' && !el.querySelector('input')) continue;
    const omvat = el.closest('label') || (el.id && document.querySelector('label[for="' + CSS.escape(el.id) + '"]'));
    if (omvat && omvat !== el) { const o = omvat.getBoundingClientRect(); if (o.height >= 44 && o.width >= 44) continue; }
    if (r.height < 44 && r.width < 44 || r.height < 24 || r.width < 24) klein.push({ el: pad(el), b: Math.round(r.width), h: Math.round(r.height), tekst: (el.textContent || el.getAttribute('aria-label') || '').trim().slice(0, 30) });
    else if (r.height < 44 || r.width < 44) klein.push({ el: pad(el), b: Math.round(r.width), h: Math.round(r.height), tekst: (el.textContent || el.getAttribute('aria-label') || '').trim().slice(0, 30), lichter: true });
  }
  const afgekapt = [];
  for (const el of document.body.querySelectorAll('*')) {
    if (!zichtbaar(el) || el.closest('.sr-only')) continue;
    const s = getComputedStyle(el);
    if (!/(hidden|clip)/.test(s.overflowX) || s.textOverflow === 'ellipsis' || s.webkitLineClamp !== 'none') continue;
    if (el.scrollWidth > el.clientWidth + 2 && (el.textContent || '').trim()) afgekapt.push({ el: pad(el), scroll: el.scrollWidth, client: el.clientWidth });
  }
  return { grof: matchMedia('(pointer: coarse)').matches, vw, sw: document.documentElement.scrollWidth, breekt: breekt.slice(0, 12), invoer, klein, afgekapt: afgekapt.slice(0, 8) };
})()`;

for (const regel of paden) {
  const [pad, staat] = regel.split('#');
  for (const b of breedtes) {
    const { result: { browserContextId } } = await stuur('Target.createBrowserContext', { disposeOnDetach: true });
    const { result: { targetId } } = await stuur('Target.createTarget', { url: 'about:blank', browserContextId });
    const { result: { sessionId } } = await stuur('Target.attachToTarget', { targetId, flatten: true });
    let geladen = false;
    const f = (m) => { if (m.sessionId === sessionId && m.method === 'Page.loadEventFired') geladen = true; };
    luister.add(f);
    await stuur('Page.enable', {}, sessionId);
    await stuur('Emulation.setDeviceMetricsOverride', { width: b, height: 780, deviceScaleFactor: 2, mobile: true }, sessionId);
    await stuur('Emulation.setTouchEmulationEnabled', { enabled: true, maxTouchPoints: 5 }, sessionId);
    await stuur('Emulation.setUserAgentOverride', { userAgent: 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1 FactizMeetBot/1.0' }, sessionId);
    await stuur('Page.navigate', { url: basis + pad }, sessionId);
    for (let i = 0; i < 300 && !geladen; i++) await slaap(100);
    await slaap(1500);
    if (staat) { await stuur('Runtime.evaluate', { expression: OPEN[staat] }, sessionId); await slaap(800); }
    const { result } = await stuur('Runtime.evaluate', { expression: METEN, returnByValue: true }, sessionId);
    if (process.env.BEELD) {
      const { result: shot } = await stuur('Page.captureScreenshot', { format: 'png', captureBeyondViewport: false }, sessionId);
      const { writeFileSync, mkdirSync } = await import('node:fs');
      mkdirSync(process.env.BEELD, { recursive: true });
      writeFileSync(join(process.env.BEELD, `${regel.replace(/[^a-z0-9]+/gi, '_')}-${b}.png`), Buffer.from(shot.data, 'base64'));
    }
    luister.delete(f);
    const m = result?.result?.value ?? { fout: JSON.stringify(result).slice(0, 300) };
    const klein = m.klein ?? [];
    console.log(JSON.stringify({ pad: regel, b, grof: m.grof, over: (m.sw ?? 0) - (m.vw ?? 0), breekt: m.breekt, invoer: m.invoer, klein_hard: klein.filter((k) => !k.lichter), klein_licht: klein.filter((k) => k.lichter).length, afgekapt: m.afgekapt, fout: m.fout }));
    await stuur('Target.disposeBrowserContext', { browserContextId });
  }
}
chrome.kill();
await slaap(300);
rmSync(profiel, { recursive: true, force: true });
process.exit(0);
