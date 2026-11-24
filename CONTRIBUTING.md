# Contributing to Factiz

Thanks for looking. Factiz is a small project with a public archive behind it, so every change ends up in front of
people who use it to decide what to believe. That is why the habits below are firm. A pull request that follows them
merges quickly; one that fights them does not merge.

You do not need to know the whole lab to help. Some of the most useful work needs no code at all: reading the site in
your own language, telling us about a newsroom we are missing, or pointing out a page where two different claims
ended up together. `docs/GOOD-FIRST-ISSUES.md` lists tasks that stand on their own.

## Before you start

- **Small fixes** (a typo, a broken link, a test that fails on your machine): open a pull request straight away.
- **Anything larger**: open an issue first and say what you want to change and why. Work in this project follows
  `docs/PLAN.md`, one task at a time, and a change in scope is written down in `docs/SPECS.md`, `docs/DESIGN.md` or
  `docs/PLAN.md` before it becomes code. We will help you find the right place for it.
- **The words in the code are Dutch.** `docs/README.md` explains the documents in English and translates the terms
  you will meet (`bewering` is a claim, `oordeel` a verdict, `uitgave` an edition).

## How a change runs

1. **Test first.** Write the test that fails without your change. Test names describe behaviour, not the function:
   `test_below_threshold_never_matched`, not `test_categorize`.
2. **Then the change.**
3. **Run the suite and paste the output in the pull request.**

   ```bash
   pytest -m "not nli"          # the suite without the slow model tests
   pytest -k <name> -v          # one test
   npm --prefix site run build  # when you touched site/
   ```

4. **Measure a change in behaviour.** A change to matching, thresholds or models comes with a benchmark run
   (`python -m doublecheck.benchmark`) in the pull request, before and after. "It looks better" is not a measurement.
5. **Keep the two platforms equal.** The platform exists twice: in Python (`factiz_site/`, the reference) and in
   TypeScript (`site/src/platform/`, what runs on factiz.org). A change to one is a change to both, and
   `tests/test_platform_ts.py` checks that they give the same answer.

Commit messages follow `type: what changed (PLAN.md #N)`, or `(#issue)` when there is no plan item yet. Types we
use: `feat`, `fix`, `docs`, `test`, `perf`, `refactor`, `chore`, `release`.

## The rules a pull request never breaks

These are domain rules, not taste. The test suite guards most of them and a reviewer guards the rest.

- **No truth percentages.** No field in any answer says how likely a claim is to be true. Percentages are only for
  how sure a match is and how precise the system is.
- **One place sets the category.** `matched`, `related`, `assessed` and `none` come from the categorisation function
  alone. Nothing returns `matched` below the match threshold, not even when it is the only candidate.
- **Thresholds and model versions live in `config.toml`,** never in code. Every fingerprint carries its model version,
  and on a mismatch the resolver refuses to run instead of comparing anyway. Changing a model or a threshold is a
  release, with a card in `docs/RELEASES.md`.
- **Artifacts are never stored or logged.** What a user sends is compared and dropped; only its fingerprint may stay.
  Logging of artifact content is off at the library level, not per call.
- **Doubt never loosens.** Where a signal can be wrong (language detection, text recognition), the unknown outcome
  falls back to the strictest threshold.
- **Every text function has a script contract.** A function that takes one `str` is listed in
  `tests/test_schriftpaneel.py`, with a contract for 24 scripts or a written reason to skip it. Tests that only run on
  Latin script missed the same bug five times.
- **A visitor's browser loads only from factiz.org.** Packages with an open licence may be bundled at build time, at
  a fixed version at least two weeks old. The server may read what a visitor sends, never keep it. Counting is
  anonymous and added up.

## What never goes into the repository

- `.env` or any key. Use `.env.example` for the names.
- Anything under `data/`: the corpus, editions, measurement output. It is ignored on purpose.
- Fact-check text copied from a newsroom's site. We link to their article; we only publish what their licence or
  their written permission allows.
- Screenshots or names of private people, except where a published Factiz Radar check needs them and its rules
  allow it.

## Contributions made with AI tools

Welcome. You answer for what you send: it passes the same tests, the same measurements and the same review as
anything else.

## Licence of your contribution

Code and documentation land under AGPL-3.0, except inside `conformance/`, which is MIT, `docs/PROTOCOL.md`, which is
CC BY 4.0, and our own writing in `content/`, which is CC BY 4.0 (`content/LICENSE.md`). By sending a pull request you
agree that your work is released under the licence of the place it lands.

## Sign your commits (DCO)

Every commit carries a `Signed-off-by` line with your name and an address you use, which `git commit -s` adds for you:

```
Signed-off-by: Your Name <you@example.org>
```

With that line you certify the Developer Certificate of Origin 1.1 (https://developercertificate.org): you wrote the
change, or have the right to submit it under the licence of the place it lands. There is no separate agreement to sign.
Forgot it? `git commit --amend -s` for the last commit, or `git rebase --signoff main` for all of them.

## Talking to us

Issues and pull requests are welcome in English or Dutch. For a mistake on a page of factiz.org, the issue form
"A fact-check page is wrong" asks for what we need. Security problems go privately, as `SECURITY.md` describes.
Everyone here follows the `CODE_OF_CONDUCT.md`.
