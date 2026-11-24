// De site van Factiz (B76, PLAN #34.2f): Astro op de server, met React, Tailwind en Radix. De gegevens komen van het
// platform in TypeScript (`src/platform/`, B80), op de server zelf aangeroepen. Deze bouw draait in Node (toetsen, eigen
// computer); met `FACTIZ_DOEL=worker` (`npm run build:worker`) dezelfde site voor een Cloudflare Worker met D1 (B80).
import { defineConfig } from 'astro/config';
import cloudflare from '@astrojs/cloudflare';
import node from '@astrojs/node';
import react from '@astrojs/react';
import tailwindcss from '@tailwindcss/vite';
import { createHash } from 'node:crypto';
import { fileURLToPath } from 'node:url';
import { KOPSCRIPT } from './src/lib/weergave.js';

const hash = (s) => `sha256-${createHash('sha256').update(s).digest('base64')}`;
// Node (toetsen, eigen computer) of een Worker: de adapter, waar de uitgave staat (`#gegevens`) en de uitvoermap
const WORKER = process.env.FACTIZ_DOEL === 'worker';

export default defineConfig({
  output: 'server',
  adapter: WORKER ? cloudflare({ configPath: 'wrangler.jsonc', imageService: 'passthrough' }) : node({ mode: 'standalone' }),
  ...(WORKER ? { outDir: 'dist-worker', session: false } : {}),
  integrations: [react()],
  server: { host: '127.0.0.1', port: 8796 },
  // Geen bestanden in de pagina geplakt (data:): elk lettertype en beeld komt als bestand van de site (font-src 'self').
  vite: { plugins: [tailwindcss()], server: { fs: { allow: ['..'] } }, build: { assetsInlineLimit: 0 },
    // De schermvergrendeling van Radix zet haar opmaak in een stylesheet uit het script, niet in een <style>-element dat de
    // opmaakregel weigert (PLAN #34.2ad, src/lib/opmaakblad.js).
    resolve: { alias: { 'react-style-singleton': fileURLToPath(new URL('./src/lib/opmaakblad.js', import.meta.url)),
      // waar de uitgave staat (B80): in Node een SQLite-bestand, in de Worker D1 en de statische bestanden van de release
      '#gegevens': fileURLToPath(new URL(WORKER ? './src/lib/gegevens-worker.js' : './src/lib/gegevens-node.js', import.meta.url)) } } },
  // Script alleen van de eigen site (B75): Astro zet de hashes van zijn eigen stukjes script en opmaak in de kop.
  security: {
    // De adressen waarop de site zichzelf herkent (PLAN #34.2v). Zonder deze lijst neemt Astro aan dat elke bezoeker op
    // http://localhost zit, en weigert het zoeken (een gepost formulier) van factiz.org of 127.0.0.1 als kwam het van een
    // andere site: "Cross-site POST form submissions are forbidden".
    allowedDomains: [{ hostname: 'factiz.org', protocol: 'https' }, { hostname: 'localhost' }, { hostname: '127.0.0.1' }],
    csp: {
      // B88 (SPECS E9.S36 AC4): Google Analytics, pas na een ja van de bezoeker geladen (src/lib/meten.js); alleen de hosts
      // die het nodig heeft
      directives: ["default-src 'none'", "img-src 'self' https://*.google-analytics.com https://*.googletagmanager.com",
                   "font-src 'self'",
                   "connect-src 'self' https://*.google-analytics.com https://*.analytics.google.com https://*.googletagmanager.com",
                   "form-action 'self'", "base-uri 'none'", "frame-ancestors 'none'"],
      // en het ene stukje in de kop dat licht of donker zet vóór het tekenen (src/lib/weergave.js)
      scriptDirective: { resources: ["'self'", 'https://www.googletagmanager.com'], hashes: [hash(KOPSCRIPT)] },
      // Radix zet opmaak in attributen (een verborgen vinkje voor formulieren); dat mag hier, alleen opmaak, nooit script.
      // De keuzelijst van Radix voegt één vast blokje opmaak in (de schuifbalk van de lijst verbergen): dat met zijn hash.
      styleDirective: { resources: ["'self'", { resource: "'unsafe-inline'", kind: 'attribute' }],
                        hashes: [hash('[data-radix-select-viewport]{scrollbar-width:none;-ms-overflow-style:none;-webkit-overflow-scrolling:touch;}[data-radix-select-viewport]::-webkit-scrollbar{display:none}')] },
    },
  },
});
