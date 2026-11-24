# Good first issues

Tasks that stand on their own: you can do them without the lab's database, without API keys and without knowing the
rest of the plan. Each one names where to start and when it is done. Say in an issue which one you pick up, so two
people do not do the same work. The plan item in brackets is where the task lives in `docs/PLAN.md`.

## Without code

### Read the site in your language

The site speaks 15 languages: English, Dutch, German, Spanish, French, Portuguese, Russian, Ukrainian, Indonesian,
Turkish, Chinese, Japanese, Hindi, Arabic and Persian. Every fixed text was written in English and translated by a
model, and not one language has been read by a native speaker yet: each file in `factiz_site/teksten/` still says
`"nagelezen": false`.

Read your language on [factiz.org](https://factiz.org) or in `factiz_site/teksten/<code>.json`. Note what is wrong in
meaning first (a negation, a number, who did what), then what reads unnatural. A pull request with the changes, or an
issue with the "A translation is wrong" form, both work. Done when the file says `"nagelezen": true` with your
changes in it.

### Check the negation rules for a South or Southeast Asian language

When two claims look alike but one says the opposite ("X did" against "X did not"), the resolver must not call them the
same. For Tamil, Telugu, Malayalam, Kannada, Bengali, Sinhala, Assamese, Punjabi and Khmer, those negation patterns
come from grammars, not from people who speak the language. `docs/BENCHMARK.md` §106 says per language which
patterns no speaker has seen; the patterns live in `doublecheck/relation.py`. Read them, say which are wrong or missing,
and give two or three example sentences. Done when a speaker of the language has signed off, in the issue or the pull
request. (PLAN #25.20, the native-speaker check that is still open.)

### Tell us about a newsroom we are missing

Use the "Add a newsroom" form. Most useful: newsrooms in languages where the archive is thin, and anyone who works at
a newsroom and can say yes to publishing its checks.

## Small code

### A sample edition, so the site runs anywhere

Today the site only runs against an edition built by the lab, which takes the full corpus. The tests already build
small editions from made-up data (see `_site` in `tests/test_factiz_dossiers.py`). Turn that into a command that writes
a sample edition of a few hundred pages to a path you choose, with only open-licensed or invented content. Done when
`FACTIZ_PUBLICATIE=<that file> npm --prefix site start` shows a working site, a test builds the sample and opens it,
and the README says how. (PLAN #34.2bl, step 5.)

### Checks on every pull request

Add a GitHub Actions workflow that, on every pull request, sets up Python 3.12 and Node 22, runs the part of the suite
that needs no lab data and no model downloads, and builds the site. Add a Dependabot configuration for `requirements.txt`
and `site/package.json` that waits two weeks before proposing a new version (Dependabot's `cooldown` setting): we only
take versions that are at least two weeks old. Done when the workflow is green on `main` and fails on a broken test.
(PLAN #34.2bl, step 6.)

### Plural forms in Russian, Ukrainian and Arabic

The site knows two forms for a count: one, and more than one (`redacties_een` and `redacties` in
`factiz_site/teksten/`). Russian, Ukrainian and Arabic have more. The Python platform (`factiz_site/`) and the TypeScript one (`site/src/platform/`) both fill in these texts and must
give the same result. Done when both use the plural rules of CLDR and a
test covers the numbers 1, 2, 5, 11, 21 and 101 in each language. (PLAN #34.2be, "later".)

### Mirror the share image for Arabic and Persian

Every fact-check has an image for sharing (`factiz_site/deelbeeld.py`, `site/src/lib/platen.js`). For Arabic and
Persian it is laid out left to right. Done when a right-to-left language gets a mirrored layout, in both the Python
and the TypeScript drawing, and `tests/test_site_platen.py` passes. (PLAN #34.2be, "later".)

## Bigger, for later

### One source for the design tokens

Colours, type, sizes, corners and shadows live in several places. Put them in one file that every surface gets its CSS
variables from, with a test that refuses a colour that does not come from it. Read `docs/DESIGNSYSTEEM.md` first.
(PLAN #34.3.)
