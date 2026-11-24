# De opdracht voor een onderzoeker van Factiz Radar (PLAN #37.10)

*Elke onderzoeker van de weekronde leest dit eerst; de prompt noemt alleen de sleutel, de taal en wat bijzonder is.*

You are writing one own fact-check for Factiz (factiz.org) as a draft for its editors. The key, the language of the check
and anything specific are in your prompt. Working directory: the root of the Factiz repository (the folder with `config.toml`).

## Read first

1. docs/voorstellen/2026-11-18-eigen-factcheck.md (structure, verdict scale, rules) and docs/VOICE.md (tone).
2. Finished checks as examples: content/redactie/vliegstop-vs-iran/check.toml (English) and
   content/redactie/rij-vrouwen-kinderopvang/check.toml (Dutch), and data/redactie/vliegstop-vs-iran/dossier.md for what a
   dossier holds.
3. Your candidate in data/radar/keuze/2026-11-19.md (the block with your key, or the reserve line with your key). It was
   written from X Community Notes: treat it as a lead, never as a source. The topic in data/radar/lijst/2026-11-15-<taal>.md
   (or 2026-11-15.md for Dutch) has more post links.
4. The validator: doublecheck/redactie.py.

## Do

- Research on the open web with WebSearch and WebFetch only. Read the actual posts through X's public embed data:
  https://cdn.syndication.twimg.com/tweet-result?id=<id>&token=<token>&lang=<taal>, where the token is computed with node as
  ((Number(id) / 1e15) * Math.PI).toString(36).replace(/(0+|\.)/g, ''). Compare each post's real text with the claim; the
  radar can describe a post wrongly.
- Prefer primary sources and reputable sources, in the language of the check where they exist. At least two independent
  sources for the core finding (another fact-checker does not count as one of the two). Every sentence in kort, tekst,
  niet_weten and the timeline carries its source numbers [n].
- Keep it short: about 400 words in `tekst` (at most 450), `kort` in three sentences, and only the sources the text
  needs. Every word is translated into up to fourteen languages and read by the editors, so cut what does not carry the
  finding.
- Factiz speaks as one newsroom, and the editors check what a person can check: they watch the videos, read the posts and
  open the pages. So never write what your tools could not do ("we could not open", "we did not watch", "the page refused
  us", "we only saw the first frames") in the check. Put every such item in `nog_doen` instead, as a short task for the
  editors in English with the source number, for example "Watch the video in post [1]: does the right half show the same
  scene as the video by Louis Errington [11]?" or "Open the Kremlin transcript [4] and look for these words." When the
  editors approve the check, those tasks count as done and are removed.
- `niet_weten` and `nog_uitzoeken` are only for what nobody can settle yet, editors included: who made an image, which
  meeting a clip comes from, what a final investigation will find, whether a doubtful verdict should be another one.
- Write the check in the language of your prompt. The editors read a check in a language other than Dutch or English in an
  English machine translation, so write plainly, avoid idioms, and keep names, numbers, dates and quotes exact. A quote in
  another language than the check: give the original and a translation.
- Write data/redactie/<key>/dossier.md (findings, every source with URL and an existing web.archive.org copy if there is
  one, what refused you, time spent by the clock), content/redactie/<key>/check.toml, and data/redactie/<key>/beeld.json as
  {"post": "<id>"} for the post that circulates and should be shown stamped (prefer one without a Community Note in its
  embed).
- In check.toml: status = "concept", taal = "<taal>", auteur = "Claude (AI)", nalezer = "", gepubliceerd = "", reikwijdte
  "internationaal" or "lokaal", a verdict from the scale, soort and vorm from the allowed values, nog_uitzoeken with what
  stays open. A post by a private person: no url, prive = true (the editors make the archive copy). A post by a public
  figure or organisation: its url. If the circulating image shows minors or gore, say so in the dossier.
- From the repository root, run `.venv/bin/python -m doublecheck.redactie controleren` and
  fix until your key reads "goed".

## Never

Open a browser, log in, create accounts, download files, contact anyone, use the Brave API or any paid API; put the text of
a Community Note in a search query, the check or the dossier; name a private person or a victim; use an em dash or an
exclamation mark in Factiz's own text; touch files of other keys; commit. If the claim turns out not to be checkable, or a
verdict would rest only on the poster, stop and say so instead of forcing a check.

## Report

In under 200 words: the verdict you propose and why, number of sources, open questions, what refused you, time spent.
