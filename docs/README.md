# A way into the documents

The team behind Factiz writes in Dutch, so most documents here are Dutch, and so are the names in the code. This page
is the English way in: what each document is for, how the numbering works, and the words you will keep meeting.
Machine translation reads these documents well enough to follow them; when something matters, ask in an issue.

The protocol is the exception. `PROTOCOL.md` is written in English, and the English text is the normative one.

## The documents

| document | what it answers |
|---|---|
| `REQUIREMENTS.md` | why: goals, users, scope, and the decision log, B1 to B94 |
| `SPECS.md` | what: epics, stories, acceptance criteria, and the domain rules DR1 to DR10 |
| `DESIGN.md` | how it should feel: principles, flows, design checks |
| `DESIGNSYSTEEM.md` | how it looks, and where each part of the look lives in the code; start here to build a page |
| `ARCHITECTUUR.md` | the layers of the lab, the stack, and where the computing happens |
| `PLAN.md` | the work, in stages and numbered tasks, one at a time |
| `PROTOCOL.md` | the resolver protocol, a draft standard, in English |
| `BENCHMARK.md` | every measurement, with date and configuration, including the ones that turned out wrong |
| `RELEASES.md` | when a change counts as a release, and the card of each one |
| `RUNBOOK.md` | how factiz.org is built, deployed and watched |
| `VOICE.md` | how Factiz writes: tone, words, and what we never say |
| `KENNISBANK.md` | facts with a source, for anyone writing about online fact-checking |
| `RESEARCH.md` | what others already know about fact-checking machines |
| `steekproeven/` | the labelled samples behind the measurements: every count in `BENCHMARK.md` that needed a human or a second reader has its labels here |
| `meetplannen/` | the set-up of each measurement round, written before the round ran |

## How the numbering works

- **B42** is a decision in the log of `REQUIREMENTS.md`. Decisions are numbered once and never renumbered; a later
  decision can replace an earlier one, and says so.
- **#34.2bl** is a task in `PLAN.md`: stage 34, task 2bl. Commit messages end with the task they belong to, as
  `(PLAN.md #34.2bl)`.
- **§160** is a section of `BENCHMARK.md`, one measurement per section.
- **DR4** is a domain rule in `SPECS.md`; **E9.S1** an epic and story there.
- **PO** is the product owner, who makes the decisions. Where a document quotes the PO with a date, that quote is
  the reason for what follows.

## Words you will meet

| Dutch | English | what it means here |
|---|---|---|
| bewering | claim | what is going around, in the words of the fact-check |
| oordeel | verdict | what the newsroom concluded, in its own words (`oordeel_eigen`) and mapped to our scale |
| redactie | newsroom | the fact-checking organisation |
| uitgever | publisher | the site a fact-check comes from, in the lab |
| factcheck, check | fact-check | one newsroom's article about one claim |
| pagina | page | one claim on factiz.org, with every check of it |
| uitgave | edition | one build of the archive: a SQLite file with only what may be published |
| lab | lab | `doublecheck/`: everything that builds, measures and decides what goes into an edition |
| platform | platform | the layer that reads an edition and answers `/api/` |
| eigen check | own fact-check | a check by Factiz itself, shown as Factiz Radar |
| wereldlijst | world list | our weekly overview of claims going around worldwide and what newsrooms found |
| dossier, thema, onderdeel | dossier, theme, sub-theme | ways to group pages, chosen by people |
| naam | name | a public person, organisation or place with a Wikidata number |
| bron | source | where a check or a fact comes from |
| herkomst | provenance | where a record came from, and whether it may be given away |
| vingerafdruk | fingerprint | what the resolver keeps of an artifact: a vector or a hash |
| drempel | threshold | always from `config.toml` |
| vertaling, weergave | translation, display translation | a translation for reading on the site, not for matching |
| nagelezen | reviewed | read by a person or a second model before it counts |
| leesproef | reading test | a sample read by hand; the gate for anything a model wrote |
| poort | gate | the condition that has to hold before something goes into an edition |
| steekproef | sample | a set of cases with labels, usually in `docs/steekproeven/` |
| meting, meetplan | measurement, measurement plan | a run with a fixed set-up, written down before it ran |
| lezer | reader | a model that reads a message and its sources (`lezer-v18` is a version) |
| schrift | script | a writing system: Latin, Devanagari, Arabic and 21 more in the test panel |
| afscherming | shielding | a page kept from search engines, for example because it names a private person |
| vindbaar | findable | how far the site is open to search engines, a setting from 0 to 3 |
| uitrol | deployment | putting an edition and the site on factiz.org |
| verversen | refresh | the weekly run that builds a new edition |
| hittewacht | heat guard | a wrapper that pauses heavy jobs when the Mac runs hot |

Commands follow the same pattern: `python -m doublecheck.<module> <step>`, with steps like `bouwen` (build),
`ophalen` (fetch), `indienen` (submit a batch), `lezen` (print for reading), `tellen` (count, which refuses while a
case has no label) and `controleren` (check). `CLAUDE.md` in the root lists all of them.
