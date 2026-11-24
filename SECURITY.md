# Security policy

## Reporting a vulnerability

Use **[Report a vulnerability](https://github.com/factiz-org/factiz/security/advisories/new)** on the Security tab of
this repository. Your report stays private between you and us until a fix is out. No GitHub account? Write to
**info@factiz.org**, the address that `factiz.org/.well-known/security.txt` also names.

Please do not open a public issue for a security problem, and do not test against factiz.org in a way that slows it
down for readers.

What you can expect:

- an answer within 72 hours;
- coordinated disclosure: we aim to fix within 90 days, and we name you in the release notes unless you would rather
  we did not;
- no bounty. The project has no budget for one, and we would rather say so than promise it.

## Scope

- factiz.org and its endpoints under `/api/` (the site in `site/`, running as a Cloudflare Worker);
- the platform in `factiz_site/` and `site/src/platform/`;
- the lab and the resolver API in `doublecheck/`;
- the conformance test in `conformance/`.

Out of scope: load tests and volumetric attacks on factiz.org, and problems in the fact-check articles we link to,
which belong to their publishers. A factual mistake on a page is not a security problem; use the issue form for it.

## What we promise the people who use Factiz

Judge the impact of a finding against these promises. Breaking one of them is the most serious kind of problem we
know.

- The resolver keeps fingerprints, never artifacts. Text is compared and dropped; of an image, only its perceptual
  hash may stay. Artifact content is never logged.
- The site keeps nothing that identifies a visitor. It counts visits and the words people type in the search box,
  added up per day and language; never an IP address, a cookie or a user agent.
- Until a visitor says yes to Google Analytics, their browser loads nothing from any domain but factiz.org.
- No key, token or private address belongs in this repository. If you find one, in the files or anywhere in the
  history, report it privately, as above.
