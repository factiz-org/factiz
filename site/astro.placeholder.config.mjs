// De placeholder van factiz.org (PLAN #34.2f, stap 3b): één stille pagina uit de site, statisch gebouwd, ook voor als de
// site in onderhoud is. Een eigen bouw naast de site: de bron in placeholder/, de uitvoer in dist-placeholder/, met de
// teksten, het woordmerk en het veld van de site zelf. Geen script; een adres dat er niet is, krijgt bij Cloudflare Pages
// deze pagina, want er is geen 404.
import { defineConfig } from 'astro/config';

export default defineConfig({
  site: 'https://factiz.org',
  output: 'static',
  srcDir: './placeholder',
  publicDir: './placeholder/public',
  outDir: './dist-placeholder',
  cacheDir: './node_modules/.astro-placeholder',
  trailingSlash: 'always',
  build: { format: 'directory', inlineStylesheets: 'always' },
  vite: { server: { fs: { allow: ['..'] } }, build: { assetsInlineLimit: 0 } },
  devToolbar: { enabled: false },
});
