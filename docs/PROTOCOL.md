# Resolver protocol v0.1, *draft*

> **Status:** draft, not yet adopted. Owner: PO.
> This is the part that can become a standard. The icon cannot: that is a
> brand, and brands do not become standards.
>
> **Language:** this English text is normative. It replaces the Dutch text
> it was translated from on 14 October 2026; that version remains in the
> repository history and has no standing. Section and obligation numbers are
> unchanged, so every reference such as §2.7 or §11.5 still points to the
> same place.
>
> **Codes:** B13, DR2 and the like refer to the decision log and the domain
> rules of the reference implementation (`docs/REQUIREMENTS.md` and
> `docs/SPECS.md`, in Dutch); numbers such as 15.1 or #25.17 are tasks in
> `docs/PLAN.md`. Values on the wire keep their v0.1 spelling, some of it
> Dutch (`tekst`, `waargenomen`, `vertalingen-v1`): that is the format, and
> respelling it would be a protocol version decision.

## 1. What this is for

One question, one answer: **"has this claim already been checked, by whom,
and what was the outcome?"**

The question is asked with a *fingerprint* of an artifact, not with the
artifact itself. The answer is an **evidence state** with sources.

### What this is explicitly not

- **Not a truth oracle.** The protocol has no field that says whether a
  claim is true, and one MUST NOT ever be added. A percentage attached to an
  individual claim is always made up: nobody has measured that the earth is,
  with 96% certainty, not flat *(B10, DR2)*.
- **Not a moderation API.** The answer points to what others found. It is
  not an instruction to remove or label anything.
- **Not an identity layer.** The protocol carries no data about who asks the
  question, and there is no field that could hold it.

## 2. Normative obligations

This is the core. The primitives underneath, perceptual hashes and
multilingual embeddings, are widely available and nothing special. **What
this protocol adds are the constraints.** An implementation that drops them
is not a conforming implementation.

A resolver:

1. **MUST NOT** return a field that expresses a probability of truth.
   Percentages are allowed only for match confidence and system precision
   *(DR2)*.
2. **MUST NOT** return `matched` below its own match threshold, not even when
   it is the only candidate or the caller asks for it *(DR4)*.
3. **MUST NOT** present a judgement of its own (`assessed`) in the same form
   as a human fact-check (`matched`) *(DR5)*.
4. **MUST NOT** store, cache or forward the artifact it receives. Only the
   fingerprint may outlive the request *(DR3)*. The single exception is a
   dispute route with explicit consent given at that moment.
5. **MUST** name the sources for every `matched`: who checked, when, with
   which verdict, with a link *(DR1)*.
6. **MUST** express consensus as a **count**, never as an estimate.
   "Debunked by 14 fact-checkers in 6 languages" is factual and can be
   verified *(DR7, B10)*.
7. **MUST** state with every fingerprint the version that produced it, and
   **MUST** refuse to compare across versions, loudly rather than silently
   *(DR6)*.
8. **MUST** return the thresholds that determined this answer, so that a
   consumer can see under which regime it was produced.
9. **MUST** name itself in every answer, and **MUST derive claim identity
   from the claim text** following the derivation it publishes in its
   discovery document *(§7)*.
10. **MUST** report when a match came through a variant: a wording of the
    claim that does not come from a newsroom, such as a machine translation.
    The answer does this with `via` *(§5)*. It **MUST** also state in its
    discovery document which variants it searches, even when there are none
    *(§3)*.

Obligations 7 and 8 are what make this protocol verifiable rather than
reassuring. That distinction is the whole product.

Obligation 9 exists for the case this protocol is for: more than one
resolver. Added with 11.3.

Obligation 10 exists because a translation written by a language model can
connect a question to a newsroom's check. Without a notice, such a match
looks like any other. Added with #25.17 (PO, 12 October 2026).

## 2b. Relation to ClaimReview *(B16)*

This protocol **does not replace ClaimReview and does not compete with it.**
It sits next to it and supplies the two pieces that are missing.

ClaimReview has won: publishers already publish it, and it is the reason we
have a corpus at all. A competing standard yields two standards and no
adoption. An extension of two fields is something a publisher will take on.

### What ClaimReview does well, better than expected

Measured on eight publisher pages, raw JSON-LD next to the API response
(BENCHMARK.md §32a). A small sample, but an unambiguous one:

- **The language field is not in the markup.** Not a single page sets
  `inLanguage` on the ClaimReview node; Google infers the language, and does
  so better than our own detector, which went by proper names.
- The fields that are there (publisher, verdict, URL, date) are usable.
- ClaimReview even carries `claimant`, who made the claim. We **discard that
  field on purpose**: a claimant is usually a named person, and that does not
  fit where we stand. On that point ClaimReview is richer than our design
  allows.

### What is structurally missing

| missing | consequence |
|---|---|
| **an identifier for the claim itself** | two checks of the same claim, one in Dutch and one in Spanish, are separate records with no relation. The ecosystem cannot be tied together |
| **a representation of the artifact** | ClaimReview is text. A screenshot has no place in it, and that is the form in which disinformation circulates |
| **a controlled vocabulary for verdicts** | `alternateName` is free text: "Onjuist", "Mostly False", "Pants on Fire". Every consumer builds its own normalisation, and each does it differently |

There is also a quality problem that is not a schema problem: **we reject
31% of the records we retrieve** because the publisher, URL or date is
missing. That is a matter of enforcement at the index, not something a field
solves.

### What we add

Two things, nothing more, exactly §5 of this document:

1. **`claim_id`**, stable across languages and publishers. The missing
   hinge, and for us a by-product of clustering: 412 of the 516 clusters with
   more than one member are multilingual.
2. **`fingerprint`**, what the claim looked like, in a scheme named by the
   discovery document of §3.

The third (a vocabulary for verdicts) we in fact already have as
`verdict_normalized` next to `verdict_original`, but that is a proposal to
the ecosystem, not something to settle unilaterally.

> **Verify before you rely on it:** ClaimReview has been extended before, for
> images and video, when text alone fell short. If that holds, it is your
> evidence that the extension mechanism works and that this path has been
> walked before.

## 3. Discovery

A fingerprint is model-specific. A client that makes one itself must first
know *which* one. Without this step, "send the fingerprint, not the
artifact" cannot work.

```
GET /.well-known/doublecheck
```

```json
{
  "protocol": "0.1",
  "schemes": {
    "text": [
      {"id": "st-mmini-l12-v2+casefold",
       "model": "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
       "preprocessing": ["casefold"],
       "dims": 384, "dtype": "float32", "normalized": true}
    ],
    "image": [
      {"id": "pdq-256-v1", "bits": 256, "encoding": "hex"}
    ]
  },
  "thresholds": {
    "text_match": 0.90,
    "text_match_crosslingual": 0.85,
    "text_related": 0.80,
    "image_same": 31
  },
  "scope": {
    "markets": ["nl", "de", "fr", "en", "es"],
    "claims": 19590,
    "updated": "2026-08-30"
  },
  "variants": [
    {"generator": "claude-haiku-5-5", "prompt": "vertalingen-v1",
     "languages": ["en", "es", "pt", "ta", "te"], "count": 460698}
  ]
}
```

`scope` is not cosmetic. Without it a consumer cannot read a `none`; see §6.

`variants` names the claim variants the resolver searches, per generator and
prompt version: in which languages, and how many *(#25.17)*. The field is
required (obligation 10): an empty list means the resolver searches only its
own claim texts, and a missing field leaves that question open. The field
exists so that a consumer knows before its first question that machine
translations may be involved, rather than finding out from a `via` in an
answer (§5). The generator and prompt version are the same as in `via`.

**Thresholds with a second reader** *(#30.3, 17 October 2026)*. A resolver
may let a second model, a judge, read its closest candidates and decide
together with the similarity. A `matched` can then fall below `text_match`,
but only where the judge confirms it, and a judge can also block a
`matched` above it. Obligation 8 then requires three more keys in
`thresholds`, in discovery and in every answer: `text_match_judged`, the
lowest similarity at which a judged `matched` can occur; `judge_same`, the
score the judge must give between `text_match_judged` and `text_match`; and
`judge_veto`, the score below which the judge blocks a `matched` from
`text_match` upward. Obligation 2 then reads: no `matched` below
`text_match_judged`, and none below `text_match` without the judge's
confirmation. A resolver without a judge leaves the three keys out. The
judge's own score is not in the answer yet (§11.8).

## 4. Querying

```
POST /resolve
```

The client **preferably sends a fingerprint**, and sends the artifact only
when it cannot make one itself:

```json
{
  "text": {"scheme": "st-mmini-l12-v2+casefold",
           "vector": "<base64 float32[384]>",
           "numbers": ["30000"],
           "negations": ["geen"],
           "language": "nl"}
}
```

The derived fields (`numbers`, `negations`, `language`) travel along because
the source text is thrown away and they cannot be derived afterwards. They
carry no artifact content: numbers, negation tokens and one language code.

> **Images can do this today, text cannot yet.** This is one point that is
> really two.
>
> **Images**: PDQ is a DCT over a 64×64 downscale. It runs in WASM, with no
> model. And images are precisely the viral form. For screenshots, "the
> artifact never leaves your device" can therefore be made true now.
>
> **Text**: a quantised ONNX model is feasible in the browser (tens of MB,
> cached), but it does not yield bit-identical vectors. At a threshold of
> 0.90 that tips borderline cases. That is *not* an architecture problem: it
> is **a different scheme** in §3, with its own threshold and its own
> benchmark. It is, however, a stage of work.

## 5. Answers

```json
{
  "category": "matched",
  "claim": {
    "id": "gfc-…",
    "text": "De zeespiegel daalt al tien jaar wereldwijd",
    "cluster_size": 3
  },
  "evidence": {
    "checks": [
      {"publisher": "Nieuwscheckers", "verdict_normalized": "onwaar",
       "verdict_original": "Onjuist", "url": "https://…",
       "review_date": "2024-03-14", "language": "nl",
       "link": {"status": "offline", "checked_on": "2026-10-15",
                "offline_since": "2026-10-14", "last_seen_live": "2026-10-10",
                "archive_url": "https://web.archive.org/web/…",
                "archived_on": "2024-03-20"}}
    ],
    "check_count": 4,
    "publisher_count": 3,
    "languages": ["nl", "de", "fr"],
    "oldest_date": "2021-06-02",
    "attributions": [
      {"actor": "X", "actor_kind": "platform", "source": "Community Notes (X)",
       "source_kind": "platform", "level": "waargenomen",
       "date": "2025-03-15", "url": "https://x.com/i/birdwatch/n/…"}
    ]
  },
  "matched_on": ["tekst"],
  "similarity": 0.94,
  "relation": null,
  "observed_sources": [{"kind": "domain", "value": "nos.nl",
                        "status": "waargenomen"}],
  "thresholds": { "…as in discovery…" },
  "schemes_used": {"text": "st-mmini-l12-v2+casefold"}
}
```

`claim.text` and `claim.cluster_size` are empty when no evidence has been
built. With `related` the resolver does know the neighbouring claim, but it
does not present it as a checked claim; that would hollow out the
distinction in §6.

**One name per field** *(settled with task 15.1b)*. This example differed
from the reference implementation on six points, and the conformance suite
accepted both. That is the dilution a standard dies of: whoever may deviate
will deviate, and then "conforming" means nothing more than "looks like it".
The rule that settled it:

> Choose the name that cannot be confused, and where ClaimReview already has
> one, follow it: we extend ClaimReview, we do not replace it *(B16)*.

That went four times in favour of this specification and twice in favour of
the implementation:

| | was in §5 | was in the code | now | why |
|---|---|---|---|---|
| the claim | `claim {id, text, cluster_size}` | `claim_id`, plus `canonical_text` and `cluster_size` inside `evidence` | **`claim` object** | cluster size is a property of the claim, not of who checked it |
| the checks | `evidence.checks` | `evidence.factchecks` | **`checks`** | "factchecks" inside `evidence` repeats itself |
| the verdict | `verdict` | `verdict_normalized` | **`verdict_normalized`** | a bare `verdict` invites reading our normalisation as *their* verdict, exactly what DR5 forbids |
| the date | `date` | `review_date` | **`review_date`** | ClaimReview calls this `reviewDate`; and `date` of what? |

Two things that are easy to get wrong:

**`matched_on` is about the returned claim.** A signal that points to a
*different* claim does not belong in it. Sounds obvious; it was not. When
the image and text routes started running side by side, `beeld` was in
`matched_on` in 15 of 15 cases while that image hit a different claim: the
right category with an untrue caption *(BENCHMARK.md §30)*.

**`evidence.attributions` are receipts, not confirmation** *(§11.7, since
12 October 2026)*. A resolver MAY add a list of attributions to the checks:
where and when the claim turned up, or to which operation a source
attributed it. Each item carries `actor`, `actor_kind` (`outlet`,
`operatie`, `netwerk` or `platform`), `source`, `source_kind`, `level`
(`waargenomen` for observed or `toegeschreven` for attributed), `date` and
`url`, and no item comes without a source, a date and a link (DR10). An
attribution never changes the category, and a consumer that counts
confirmations never counts one: a claim that appeared on ten channels has
not thereby been debunked ten times. The scope is that of the checks; when
the checks of a cluster are in the answer, so are the attributions of that
cluster.

**`link` says whether the source can still be reached, not whether the
verdict is right** *(#25.9, proposal, additive within v0.1)*. A resolver MAY
give each check a `link` object: `status` (`live`, `offline` or `unclear`),
`checked_on`, `offline_since`, `last_seen_live`, `archive_url` and
`archived_on`; `null` as long as the link has never been checked. A dead
link never removes a check and never changes a count: the newsroom's verdict
*is* the receipt, even when its page disappears. `offline` is strict in one
direction, because a wrong "offline" is a statement about a newsroom's work:
in our implementation it takes two dead observations (404/410, domain gone,
redirected to the front page) at least a day apart. A robot check or a
time-out is `unclear`, never `offline`. `offline_since` is the first dead
observation, so the link may have died earlier. An archive copy is a capture
from before that observation.

**`observed_sources` are observed, never verified.** A logo or URL in a
screenshot says nothing about authenticity. The status field MUST carry that
distinction.

**`via` says that a translation sat in between** *(#25.17, since the Factiz 1
release of 12 October 2026)*. A resolver MAY also search claims through
variants: additional wordings of the same claim, such as translations
written by a language model. When the text match came through such a
variant, the answer MUST say so:
`"via": {"language": "ta", "generator": "claude-haiku-5-5", "prompt":
"vertalingen-v1"}`; otherwise the field is absent or `null`. The claim, the
checks and the verdict remain those of the newsrooms; `via` only says along
which wording the question reached them. Without this field a consumer could
not see that a machine translation made the connection, and that undermines
verification *(B12)*.

## 6. The four categories, and why `none` needs a reason

| category | meaning |
|---|---|
| `matched` | this claim has been checked; here is by whom, when, and what came out |
| `related` | related but not the same, for example the same image with a different claim *(B8)* |
| `assessed` | not yet checked by a human; this is a machine assessment, presented separately *(DR5)* |
| `none` | nothing found |

`matched` does **not mean "true"**. It means: this was looked at, and this
is what came out. That distinction is why a tick-or-cross icon cannot be
conforming.

**`none` is ambiguous, and that is a protocol flaw of our own.** It can mean
two things that have nothing to do with each other:

- *we searched and found nothing*: the claim has not been checked;
- *this market is not covered*: we did not even search.

A consumer that shows an icon has to separate the two. Hence:

```json
{"category": "none", "reason": "out_of_scope", "scope": {"markets": ["nl","de","fr","en","es"]}}
```

with `reason` one of `not_found` | `out_of_scope` | `low_confidence`, present
only with `none` and `null` otherwise. The scope itself is in the discovery
document (§3); a resolver MAY repeat it, as the example does. A reason never
sets or changes a category (§2.2); it says what a `none` is worth.

In the reference implementation *(#25.35, since 14 October 2026)*:

- `out_of_scope`: the text is in a language the index does not hold, as the
  corpus names languages (97 languages, certainty from 0.60). The text was
  still searched, across languages.
- `low_confidence`: there was no text to search on, only the image route
  ran (no readable text in the image, or only an image fingerprint was sent).
  The public index holds no image fingerprints yet, so this `none` says very
  little.
- `not_found`: everything else: searched in a language the index covers,
  and nothing reached the related threshold.

An uncertain language is never `out_of_scope`: a resolver says only what it
knows.

## 7. Comparability

Two resolvers are comparable only when their `schemes` match. They do **not**
need the same corpus, and that is the point: an Indian resolver knows Indian
publishers, and we do not.

A client that queries several resolvers:

- **MUST** make the fingerprint for each resolver in a scheme that resolver
  offers;
- **MUST NOT** compare or average similarities from different schemes;
- **SHOULD** show answers side by side with the source attached, instead of
  netting them out into one number.

That last point is not an implementation detail but the core of B12:
averaging verdicts makes you the arbiter, and that is exactly what a neutral
layer must not become.

### What a resolver must supply for this *(obligation 9, added with 11.3)*

**It names itself.** "Answers side by side with the source attached" works
only as long as the answer *says* where it comes from. As soon as one is
passed on, stored or merged, a `resolver` field is the difference between
attribution and guesswork.

**It derives claim identity from the text.** This is the part that carries
federation *without* a registry and *without* an authority:

```
claim_id = <prefix> "-" sha256(casefold(collapse_whitespace(strip(text))))[:16]
```

Two resolvers that know the same claim text thus arrive at the same digest
without ever having spoken to each other. The prefix is local; the digest
after it is what gets compared. The derivation is in the discovery document
(`claim_id`), so that a client can reproduce it instead of trusting it.

**What this is not.** It gives identity for the same *text*, not across
languages: a Dutch and an English wording of the same claim get different
ids. That bridge is clustering, and clustering differs per resolver. B16's
"stable claim ID across languages" is therefore half delivered, precisely
the half that needs no coordination.

## 8. Conformance

An implementation conforms when it meets the obligations of §2 and offers
the discovery document of §3. A conformance test should consist of
**refusals**, not of outcomes:

- returns `matched` below the threshold: does not conform;
- returns a truth percentage: does not conform;
- stores the artifact: does not conform;
- compares across fingerprint versions without refusing: does not conform;
- shows `assessed` in the same form as `matched`: does not conform;
- reports a `via` that the discovery document does not announce: does not
  conform.

That is why this protocol is worth standardising: it codifies what a
resolver **must not** do, and that is the part a platform or publisher
cannot credibly promise on its own.

**The test should be public and runnable, not described.** That is not a
detail but the entire enforcement mechanism: for a bootstrapped project a
trademark is barely enforceable in law, but a conformance test that anyone
can run lets the community check the claim instead of a lawyer. Someone
says "conforming", someone else runs the suite.

That suite exists *(task 15.1)*. It lives in `conformance/`, knows no
implementation (a test that imports what it tests, tests itself) and runs
against any resolver URL:

```
python -m conformance http://localhost:8000 --proeven known-claims.json
```

Three things that shape it, and that a successor should not rub out:

**Unobserved is not passed.** An obligation that did not come up during the
run gets a question mark instead of a tick, and the exit code is 2 instead
of 0. Otherwise a resolver that answers `none` to everything produces a
clean report.

**The report names its own blind spots.** The absence of storage cannot be
proven from outside; obligation 4 tests one observable failure mode: an
artifact the suite itself just supplied coming back as a claim. That is in
every report, not in a footnote.

**The probe is not an outcome.** Nowhere does the suite prescribe a
category. It sends artifacts and tests what an answer must *not* be.

## 9. What our own implementation does not meet yet

An honest list, because a specification that only describes what we already
do is no specification:

| | state |
|---|---|
| discovery document (§3) | met: `GET /.well-known/doublecheck` *(11.1)*; since #25.17 it also names the variants searched |
| `via` on a match through a variant (§5) | met: *(25.17)*; obligation 10, tested by the suite against the discovery document |
| attributions in the answer (§5, §11.7) | met: `evidence.attributions` *(25.16)*: EUvsDisinfo and Community Notes; a test guards that category and counts do not change because of them |
| link status per check (§5) | met: `link` *(25.9)*: offline only after two dead observations a day apart, archive copy from the Wayback Machine; a test guards that a dead link removes no check and changes no count |
| `none` with a reason (§6) | met: `reason` *(25.35)*: `not_found`, `out_of_scope` or `low_confidence`, only with `none`; a test per reason |
| model versions in the answer (§5) | met: `schemes_used`, only the schemes the request touched *(15.1)* |
| thresholds in the answer | met: complete since 15.1; the cross-lingual threshold was missing, which made a correct match at 0.87 look like a violation from outside. Since #30.3 also the judge's thresholds (§3), for the same reason: a judged match at 0.83 next to a reported `text_match` of 0.87 |
| client-side fingerprint, image (§4) | met: `image_fingerprint` in the request *(11.1)*; a WASM client is up to the consumer |
| client-side fingerprint, text (§4) | **not possible**; needs a scheme of its own |
| sources with `matched` | met |
| consensus as a count | met |
| resolver identity in the answer (§7) | met: *(11.3)* |
| claim identity derivable by the client (§7) | met: *(11.3)*; per text, not across languages |
| no truth field | met: guarded mechanically (DR2 test) |
| artifact not stored | met: guarded mechanically (DR3 test) |
| conformance test runnable on its own (§8) | met: `conformance/`, over HTTP against any URL |
| wire format equal to §5 | met: aligned with 15.1b; the suite knows one name per field |

## 10. What this means for B13

The protocol splits what there is to protect, and the three pieces are not
equally strong. Put under pressure:

### The specification: unrestricted

A standard you are not allowed to implement does not become a standard. No
discussion.

### The reference implementation: copyleft protects less than it seems

The AGPL requires that whoever runs it as a service publishes their changes.
A fork that strips out the constraints of §2 therefore has to show that.

But nobody is obliged to *look*, publication is not prevention, and whoever
really wants to rebuilds from the free specification and never touches the
licence. **Here copyleft is a transparency mechanism, not a lock.**

Whom does the AGPL actually hinder? Spelled out per consumer:

| consumer | affected by the AGPL? |
|---|---|
| AI lab checking model output | **no**: internal use, the network clause does not even fire |
| publisher running it internally | barely; it changes nothing anyway |
| fact-checker looking for duplicate work | no |
| **large platform** | **yes**, not through the terms but through company policy; large tech companies ban the AGPL outright |

**The party the AGPL blocks is exactly the party that does not need the
code.** A platform calls the API; it does not have to run the source code.
The parties that *do* have to run it (labs, publishers with privacy
constraints, other markets) are not hindered. That makes copyleft much
cheaper than it looked, and the bind between "protecting the brakes" and
"admitting partners" largely imaginary.

### The numbered test: this is the load-bearing leg

In law, a trademark is barely enforceable for a bootstrapped project. But
with a standard, enforcement works socially: when the test of §8 is public
and runnable, the community checks the claim. That is the cheapest
enforcement mechanism there is, and the only one that scales without staff.

**This heading was first called "the trademark on conformance".** That
turned out to be the wrong name for the asset *(revised 31 August 2026,
after 15.1 and 15.2)*. There is no trademark registration, the name is
descriptive and probably taken (REQUIREMENTS §9), and legal enforcement was
out of reach anyway. What makes a claim of conformance checkable is not the
name but the **version number plus the runnable test**: *"conforms to
resolver protocol v0.1"* can be refuted by anyone, whoever owns the name.
On its first run the suite caught our own service on obligation 7.

The name is the carrier, not the leg. If it changes (and it can; §9 of the
requirements calls it a launch risk), the caveat moves along and the test
stays.

*Since 4 October 2026 the carrier is **Factiz** (factiz.org, decision B19):
that is the name of the service and the public instance. The protocol
itself and its wire surface do not change because of it:
`/.well-known/doublecheck` remains the path and "resolver protocol v0.1"
remains the claim, because the path is format, not house style. Renaming
*that* would be a protocol version decision.*

**Order of importance: numbered test > free spec > code licence.** That is
the exact reverse of where the conversation started.

### Decision *(B13, PO, 30 August 2026)*

| piece | licence |
|---|---|
| this specification | **CC BY 4.0**; implementation permitted without restriction |
| reference implementation | **AGPL-3.0** |
| trademark | only on **conformance**, tested with the public test of §8 |
| corpus | **not** the current one (API terms); the CC BY base, yes; see §11.5 |

What this means for the order of work: turning the conformance test into
something that runs against any resolver comes first, not last. Without that
test the trademark is decoration and the three-way split has only two legs.

## 11. Open questions for the PO

With advice per question, because an open question without a preference is
no help.

### 11.1 Client-side fingerprint: *answered (31 August 2026)*

**Decision: split, and the image half is done.** PDQ runs in WASM without a
model, and images are the viral form: that is where the privacy promise can
be made firm today. Text becomes a scheme of its own, with its own threshold
and its own benchmark; that still stands.

What has been built since this decision:

- **§3 exists.** `GET /.well-known/doublecheck` returns the schemes, the
  thresholds and the scope. Until then that document existed only on paper,
  and without it a client cannot *know* which scheme to use.
- **§4 accepts an image fingerprint.** `{"image_fingerprint": {"scheme": …,
  "hash": …}}`: the artifact stays on the device. For text, `schemes`
  deliberately holds an empty list: offering a scheme we cannot honour is
  worse than offering none.
- **The second half of obligation 7 is now observable.** That was the silent
  failure: the image search filters on model version, so a fingerprint in a
  *different* scheme returned zero rows and therefore a tidy `none`, an
  answer that means nothing. Now it is a 409, with both scheme names in it.
  The conformance suite tests this, and catches a resolver that swallows it.

`scope` turned out to need to say two things. `markets` are the languages
with a figure of their own that passed (B14); `languages` are the languages
in the index. Treating those as equal would stretch the promise to where it
has not been measured.

### 11.2 Will `assessed` ever be offered? *answered (31 August 2026)*

**Advice: keep it reserved, and ask the question differently.** This is not
about our roadmap. It is about the fact that as soon as the code is open,
someone will build a language model on top of it. That is the fork you can
see coming.

So the reservation is not a promise about us but a **guard rail for the
ecosystem**: obligation 3 in §2 requires that whoever supplies `assessed`
does not present it as `matched`. That rule is worth more in someone else's
implementation than in ours.

Answer to the literal question: *probably not us, certainly others.*

**Decision *(PO, 31 August 2026)*: keep it reserved.** As a result,
obligation 3 is by definition untested against our own resolver: the
conformance suite reports it as a question mark and exits with 2 instead of
0. That is intended: a tick on a rule that never came up is exactly the
promise this protocol means to replace. The rule proves itself only in
someone else's implementation.

### 11.3 Federation: *answered (31 August 2026)*

**Decision: design for federation, run one instance.** This seemed to clash
with the wish for one well-known source; it does not.

One canonical resolver wins on coverage and reliability. The specification
covers the cases where that cannot work: privacy, sovereignty, a market we
do not serve. And the decisive argument runs the other way than expected:
**forkability is the precondition for dependence.** Nobody builds on
something they cannot leave.

"Cost: close to zero" was right, but not because there was nothing to do.
§7 described what a *client* must do and said nothing about what a resolver
must supply for it. Two things were missing, both small:

- **An answer did not say who gave it.** "Show side by side with the source
  attached" works only as long as nobody passes on or stores an answer, and
  that is exactly when federation matters. Now there is a `resolver` field in
  every answer and in the discovery document.
- **Claim identity was a happy accident.** Our ids were already derived from
  the claim text, so two resolvers arrive at the same digest without
  consulting each other. But that was written down nowhere, so a second
  implementation with arbitrary ids would quietly break federation. Now it is
  obligation 9, with the derivation in the discovery document so that a
  client can reproduce it.

What was *not* built, and did not need to be: a registry of resolvers, or
code that queries several of them. That is the client's job, and running one
instance remains the decision.

### 11.4 Trademark and conformance: *answered (31 August 2026)*

The advice was: settle this first, not last. That has happened. The test of
§8 lives in `conformance/`, runs against any resolver URL and catches nine
deliberately broken variants; the caveat is in `TRADEMARK.md`.

And the answer sharpened the question: the load-bearing leg is not the
trademark but the numbered test (§10). Recorded as B13(c).

### 11.5 What happens to the corpus? *answered (30 August 2026)*

> *Not legal advice; a reading of the published terms. Have it checked before
> you act on it.*

There turn out to be **two routes to the same data, with opposite
licences**, and we were on the wrong one.

| route | licence | redistribute? |
|---|---|---|
| **Fact Check Tools API** *(what we used then)* | Google APIs ToS §5 | **no** |
| **Data Commons dataset + markup feed** | **CC BY 4.0** on the compilation, plus `sdLicense` per record | **yes, with attribution** |

The prohibitions on the API route are literally what we ran into:

> **§5.e.1**: "Scrape, build databases, or otherwise create permanent copies
> of such content, or keep cached copies longer than permitted by the cache
> header"
>
> **§5.e.2**: "Copy, translate, modify, create a derivative work of, sell,
> lease, lend, convey, distribute, publicly display, or sublicense to any
> third party"
>
> **§5.c**: "you may not expose that content to other users or to third
> parties without explicit opt-in consent"

That hits three things at once, not only giving it away:

1. **Storing.** `doublecheck.db` was a permanent copy of 19,590 claims:
   precisely "build databases … permanent copies" (§5.e.1).
2. **Shipping it in the repository.** Prohibited under §5.e.2.
3. **Exposing it through our own `/resolve`.** We pass claim text and
   fact-check URLs on to callers (§5.c).

And note: §5.e.2 also prohibits "create a derivative work". That makes even
the elegant variant, **fingerprints without the source text**, doubtful on
this route.

### The way out

**Switch sources.** The Data Commons dataset carries CC BY on the
compilation: copying, modifying and redistributing are allowed, with
attribution. That removes all three objections above at once, including the
derivative-work point.

Two things to watch with that switch:

- **`sdLicense` per record.** CC BY covers the *compilation*; each
  ClaimReview record can carry a licence of its own. A careful
  implementation reads that field and respects it, instead of applying the
  compilation licence to everything.
- **Coverage.** The research dataset is historical, and the markup feed
  covers only what was made with Google's own tool. That is probably
  **less** than what the search API returns. Measure that before the switch,
  not after.

**A third route, as a fallback:** the ClaimReview markup is public on the
publishers' own sites. Crawling it ourselves bypasses Google's contract
entirely; then only `sdLicense` and the publisher's terms apply. More work,
but it makes you independent of a single gatekeeper, which fits B12.

### Consequence for B13

**The code licence was never the binding problem.** What you may give away
was determined by the source of your data, and until that day it was
unknown.

With the switch to CC BY, all three options from the earlier table become
possible, including shipping the full corpus. Without that switch, none of
the three is.

*Scheduled as 14.5.*

### 11.6 How does a resolver announce a scheme change? *open (5 October 2026)*

The release policy (B22, `docs/RELEASES.md`) promises that an image scheme
remains served for 90 days after a change. The wire format already allows
this: `schemes.image` in §3 is a list, so a resolver can name two schemes at
once. What the format *cannot* express is *until when* the old scheme stays.
A client reading the document sees two schemes and does not know which of
them is expiring.

Two directions, neither decided:

- **Order as convention**: the first scheme in the list is the preferred
  scheme; a client that handles all schemes picks that one. No new field,
  but also no end date on the wire.
- **An optional field per scheme** (for example `supported_until`): a client
  can plan its migration. That is an addition to §3 and therefore a protocol
  version decision (v0.2), not an implementation choice.

Until this is decided, the first direction is how the reference
implementation behaves, and the end date is in the release announcement.
This does not need to happen before Factiz 1: the first image scheme change
is the moment.

### 11.7 Do attributions belong in the answer? *answered (12 October 2026)*

Since B23/DR10 the reference implementation knows attributions: receipts
that say at which outlet a claim appeared or to which operation a tracker
attributed it, each with a source, a date, a link and a level of evidence.
The question is whether `evidence` (§5) may carry such a list.

For: it is exactly the kind of receipt §5 already carries for verdicts, and
the map (B23) needs it. Against: an attribution is politically more
sensitive than a verdict, and a client that counts `evidence.checks` must
never count attributions as confirmation (DR7). An additive, optional field
`evidence.attributions` with `actor`, `actor_kind`, `source`, `source_kind`,
`level`, `date` and `url` per item breaks no existing client and leaves the
conformance test untouched; whether that fits within v0.1 or is called v0.2
is up to the PO. Until this is decided, attribution stays within storage and
measurement.

**Decision (PO, 12 October 2026): yes, additive within v0.1.** The reason is
what an answer must be able to become: a screenshot in, the history of the
claim out. The checks say who debunked it and when; the attributions say
where and when it turned up. Together, by date, that is the history. The
field is in §5. A second source follows straight away: a helpful Community
Note on X that points to a check, as a line "went round on X", with the date
and a link to the note, without the note text (#25.16).

### 11.8 Does the judge's score belong in the answer? *open (17 October 2026)*

Since #30.3 the reference implementation has a judge (§3): a `matched`
between `text_match_judged` and `text_match` exists only because the judge
gave at least `judge_same`. The thresholds say that this regime exists. They
do not let a consumer check one answer: the judge's score for the returned
claim is not on the wire, so obligation 2 can only be checked against the
lowest threshold. An additive, optional field (for example `judge_score`
next to `similarity`) would close that, and the judge's version would then
belong in the discovery document, next to the schemes (obligation 7). Both
are additions within v0.1 or a v0.2, which is up to the PO. Until this is
decided, the thresholds are on the wire and the judge's version is on the
release card (`docs/RELEASES.md`).
