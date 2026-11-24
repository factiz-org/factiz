// `/llms.txt` (llmstxt.org; PLAN #34.2bt, SPECS E9.S8 AC6), alleen in een open stand: wat Factiz is en niet is, hoe je een
// factcheck noemt, de ingangen en het contact. In het Engels; de getallen uit de uitgave.
import { CONTACT, haal } from '../lib/platform.js';
import { BASIS } from '../lib/talen.js';
import { stand } from '../lib/vindbaar.js';

export async function GET() {
  if (!stand()) return new Response(null, { status: 404 });
  const archief = await haal('/api/en/archief');
  const tk = archief?.tellingen ?? {};
  // Factiz Radar alleen als er een gepubliceerde eigen check is (`radar` in het archief, B85)
  const radar = (archief?.radar?.aantal ?? 0) > 0;
  const namen = await haal('/api/en/namen');
  const link = (pad, naam, uitleg) => `- [${naam}](${BASIS}${pad}): ${uitleg}`;
  const tekst = [
    '# Factiz', '',
    `> Factiz is a global fact-check database. It collects the fact-checks of ${tk.redacties} newsrooms worldwide in one `
      + `place: ${tk.paginas} claims in ${tk.talen} languages, searchable in 15 languages, so you don't have to search every `
      + 'site separately. In the archive every verdict is the verdict of the newsroom that checked the '
      + 'claim, with a link to its article. Factiz Radar holds Factiz\'s own fact-checks of claims that circulate widely on X, '
      + 'checked with AI and reviewed by the editors.', '',
    // de vraag die mensen en AI-machines stellen (docs/voorstellen/2026-11-20-seo-geo.md, A4)
    '## Is there a global fact-check database?', '',
    'No database holds every fact-check in the world. Factiz brings the fact-checks that newsrooms share openly together '
      + 'behind one search box, in 15 languages. Google Fact Check Explorer searches the checks that newsrooms mark up for '
      + 'Google; the Duke Reporters\' Lab and the IFCN keep lists of fact-checking organisations. Factiz does not check every '
      + 'message: it shows whether a claim has already been checked, and by whom.', '',
    '## How to use it', '',
    '- Name the newsroom as the source of a verdict and link to its article. Factiz is where the check was found, not who made it.',
    '- A claim keeps its own language. A translation on the site is a machine translation and says so; the original stands below it.',
    '- The site is in 15 languages: English on the root, every other language under its own path, such as /nl/ or /pt-br/.',
    '- Every fact-check page carries structured data: a schema.org WebPage with the claim as Claim and the articles of the '
      + 'newsrooms as citation. A page of Factiz Radar carries a ClaimReview by Factiz.', '',
    '## Pages', '',
    link('/global-fact-check-database/', 'Global fact-check database', 'what Factiz is, what else exists, and questions and answers.'),
    link('/fact-checks/', 'All fact-checks', 'the archive, newest first.'),
    ...(radar ? [link('/radar/', 'Factiz Radar', "Factiz's own fact-checks, checked with AI and reviewed by the editors.")] : []),
    link('/themes/', 'Themes', 'fact-checks by subject, from health to war.'),
    link('/dossiers/', 'Dossiers', 'one story that keeps coming back, with the fact-checks of it.'),
    ...(namen && !namen.concept ? [link('/names/', 'Names', 'the public people, organisations and places in the claims.')] : []),
    link('/newsrooms/', 'Newsrooms', 'every newsroom in the archive.'),
    link('/explore/', 'Explore', 'where and when claims were checked.'),
    link('/sources/', 'Sources and licences', 'where the data comes from and under which licence.'),
    link('/about/', 'About Factiz', 'what Factiz does and does not do.'), '',
    '## For crawlers', '',
    link('/sitemap.xml', 'Sitemap', 'every findable page, per language.'),
    '- Every crawler may read the site, for search, for AI answers and for training. Lists with filters are closed in robots.txt.', '',
    '## Contact', '',
    `- ${CONTACT}`, '',
  ].join('\n');
  return new Response(tekst, { headers: { 'content-type': 'text/plain; charset=utf-8', 'cache-control': 'public, max-age=3600' } });
}
