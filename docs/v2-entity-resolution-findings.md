# v2 Findings — Entity Resolution

Empirical results from testing the entity-resolution design against the real
corpus. The design itself is in
[`architecture.md`](architecture.md#resolution-layer); the literature behind it
is in [`research-notes.md`](research-notes.md). Data properties these results
rest on are in [`data-findings.md`](data-findings.md).

**Background.** Entity ambiguity, alias and nickname merging, and coreference are
three facets of one unsolved problem, not three separate small fixes. The
approach is a precision-first funnel: Stage 0 (pronoun and generic filter),
Stage A (mechanical surface-variant merge), then, deferred, Stage B (coreference
expansion) and Stage C (hard aliases and generic/collective entities).

Contents: [Coreference tooling](#coreference-tooling-experiments) ·
[Fragmentation scope](#entity-fragmentation-scope-module-a) ·
[Stage 0](#stage-0--pronoun-and-generic-filter) ·
[Full-corpus baseline](#full-corpus-baseline) · [Stage A](#stage-a--surface-variant-merge) ·
[Live wiring](#wiring-into-live-retrieval) · [Status](#status)

---

## Coreference tooling experiments

Run in `notebooks/explore_entity_resolution.ipynb` against real data, to test the
design's assumptions rather than read about them.

- **A script bug invalidated the first test.** `chunk_id` loads as a string
  (see [`data-findings.md`](data-findings.md#loading-and-cleaning)), so the
  first "contiguous" passage was two unrelated fragments stitched together by
  lexicographic order, and its good-looking coreference output validated
  nothing. Only the rebuilt passage counts: book 106, chunks 3–62, 6,613 words,
  no gaps in `chunk_id`, starting past the real Chapter I heading.
- **Dependency conflict.** `fastcoref` requires `transformers` 4.x. The project's
  stack uses `sentence-transformers` 6.0, which requires `transformers` 5.x and
  `huggingface-hub` 1.3 or later. In `transformers` 5, `PreTrainedModel` expects
  subclasses to call `post_init()`, and `fastcoref`'s `FCorefModel` does not, so
  loading failed with a missing `all_tied_weights_keys` attribute. Pinning
  `transformers==4.46.3` in the same environment broke `sentence-transformers`
  (pip warns but does not roll back), so the pin was undone and `fastcoref` moved
  to a **separate virtual environment (`.venv-coref`)**. This is the permanent
  answer, not a workaround: `resolution_map` is precomputed offline and only
  consumed by the live API, so the dependency never coexists with the serving
  environment.
- **`FCoref` (RoBERTa-backed) memory.** One call at about 60 chunks (about 6,600
  words) failed with a raw `RuntimeError: bad allocation` inside
  `torch.topk` (mention-span pruning), then succeeded on an identical rerun, and
  again on a fresh-kernel run, which ruled out PyTorch allocator warm-up. The
  conclusion is a soft ceiling that depends on concurrent system load, not a
  deterministic limit: a single success is not a safe threshold. Book 106 is 883
  chunks, about 15 times this size, so **whole-book single-call processing is
  infeasible on this hardware**.
- **`LingMessCoref` (Longformer-large backbone) fails differently, and worse.**
  At 60 chunks `predict()` silently returned an **empty list**, with no
  exception or warning (`preds[0]` raised `IndexError`). It works at 17 chunks.
  The ceiling lies between 17 and 60; the exact value was not found. It is also
  about 14 times slower than `FCoref` in the range it does handle, matching the
  model's published benchmark. Silent truncation is worse than a crash: an empty
  return looks like "nothing to resolve here" unless explicitly checked, and
  would silently produce an incomplete `resolution_map`. This is the mirror
  image of inventing facts: silently omitting real ones, and arguably harder to
  catch.
- **Conclusion.** Neither model is safe for a single full-book call, for two
  unrelated reasons (memory instability; silent length-based dropping). The model
  choice is secondary to building windowing first; comparing the models without
  windowing would compare both under conditions neither is meant to run in.
- **Real gap, still open.** Nothing in this exploration has verified a genuine
  cross-chunk resolution (a pronoun correctly linked to an antecedent introduced
  several chunks earlier). Every successful run may have needed only local,
  within-window context. This is the capability Stage B exists for, and it has
  not been tested.

---

## Entity-fragmentation scope (Module A)

Question: how much of the retrieval problem is entity fragmentation, and which
kind? Measured on **functional-step frontiers**: biological-parent lookups
(`parent_father_of` / `parent_mother_of`, entity1 role), the one relation family
where a single answer is structurally correct. A frontier is *contaminated* when
it resolves to more than one candidate node. Contaminated frontiers are
classified as `pronoun_generic`, `surface_variant`, or `unrelated`.

**Six-book pilot.** **19.4% (43 of 222)** of such lookups resolve to more than
one candidate. Of that 19.4%: 58% pronoun or generic node names (`"her son"`,
`"mother"`, bare pronouns), 9% surface-name variants (`"mr. harold transome"` vs
`"harold"`), 33% unclassified ("unrelated", 14 cases, not spot-checked). By
book the range was 2.6% (King Arthur, n=38) to 29.4% (Sons and Lovers, n=34);
the n is small and no per-book pattern is claimed. Contamination across
non-functional relations (36.5% raw) is **deliberately not used as a headline**,
because legitimate narrative multiplicity (several real companions, enemies or
siblings) cannot be separated from genuine fragmentation with this method.

**Sequencing decision.** On the pilot's numbers, the pronoun/generic filter
(Stage 0) was sequenced before mechanical alias merging (Stage A): surface
variants were only 9% of the confirmed problem, a smaller return than a single
anchor example (Harold) had suggested.

---

## Stage 0 — pronoun and generic filter

`resolution/pronoun_filter.py`: `is_pronoun_generic`, `build_resolution_map`,
`is_excluded_from_composition`. Non-destructive: it flags nodes without mutating
the graph. Unit tests include a regression check against the real Harold cluster.

**Real-corpus validation (not only unit tests).** Pilot contamination fell from
43 to 31 cases after the first pass (25.6% fully resolved, 2.3% went to
empty-but-honest). The gap from the predicted 58% was traced rather than
explained away: 58% was the share of contaminated *strings*, not the share of
*frontiers* fully cleared. Most contaminated frontiers carry more than one kind
of noise, so a single-mechanism filter can only fully clear frontiers where its
one target was the only problem.

**What the 31 residual cases showed.** The "unrelated" bucket is not one thing:
- **Genuine hard aliases** (`wotan` / `wanderer`, `the king` / `tancrede`), real
  corpus-wide evidence for the literature's zero-string-overlap alias problem.
- **ARF relation-semantics conflation** (`sir ector` as Arthur's foster father
  stored under the same slot as his biological father), the same category as
  the accepted `married_to` and `used_by` findings.

**Two real misses found and fixed:** `"daughter"` was missing despite `"son"`
being present (an inconsistency between `NOUN_SYNONYMS` and the role table); and
there was no plural handling at all (`"daughters"`, `"sonnes"`, `"children"`).
Fixed with an irregular-form set plus a conservative single-`-s`-strip rule.
After both fixes, contamination was 23 (from 43 originally); `"sonne"` (archaic
spelling) and `"thy"` (archaic possessive) cleared on a second real-data pass,
both symptoms of a hand list seeded from modern English against a corpus that
includes period and translated texts (Decameron, Rhinegold).

**Two sources of truth.** `is_nameable()` in the yardstick script duplicated the
pronoun/generic check through its own `_GENERIC` set, which had drifted out of
sync (also missing `"daughter"`). Fixed by delegating to `is_pronoun_generic`
rather than resyncing a second copy. The yardstick effect of that tightening is
in [`benchmarks.md`](benchmarks.md#is_nameable-ab).

---

## Full-corpus baseline

First run at full scale through the consolidated `resolution` package: 95 of 96
books (book 74763 skipped, independently reconfirming its 0 relations). **1,298
functional-step frontiers, 22.4% contaminated (291)**, close to the pilot's
19.4%, so the scope estimate held at scale.

The category mix shifted and corrected, without reversing, the sequencing
rationale:

| Category | Pilot | Full corpus |
|---|---|---|
| `pronoun_generic` | 58% | 47.1% |
| `surface_variant` | 9% | 19.6% |
| `unrelated` | 33% | 33.3% |

Stage 0 remains the larger share, so the ordering stands, but Stage A's expected
payoff at full scale is roughly double what the pilot suggested. Both stages
were built regardless of order, so only the record of why changed.

**Book 3322 (*East Lynne*) spot check** found two real vocabulary gaps by hand
inspection of contaminated frontiers:
1. `mamma` / `papa`: informal kinship terms in a different register (Victorian
   domestic fiction). Added to the pronoun/generic last-token list (`PRONOUN_GENERIC_LAST_TOKEN`), together with
   `mama`, `mom`, `dad`, `daddy`, which are unconfirmed elsewhere and included
   defensively for the same register. Extend further only on a real miss.
2. Standalone judicial and professional titles (`justice` for "Mr. Justice Hare"
   with no honorific prefix). Added `justice`, `judge`, `doctor`, `captain`,
   `reverend` (and abbreviated forms) to `HONORIFICS_AND_ARTICLES`.

**Before and after, measured directly.** 286 contaminated frontiers remain (from
291); the frontiers removed were anchored on pronoun/generic strings that were
masquerading as real anchors, not resolved contamination. Of those 286, **79.7%(This measure drops pronoun/generic and ambiguous-tier entries from each frontier, so "resolved to at most one answer" counts removing real names as success. That is the same removal that cost 395 of 470 correct nodes on the yardstick. Frontiers reduced to zero answers were not counted separately) resolve to at most one answer (up from 75.3%), 14.0% are unchanged (down from 15.8%)**, i.e. 40 cases.


The roughly 40 unchanged cases were deliberately not pursued. In book 3322,
`isabel -parent_father_of-> {papa, the earl, mount severn, earl, mr. carlyle,
he}` mixes Isabel's father's title variants with `mr. carlyle`, a different and
later significant character: the same narrative-context ceiling already accepted
for Stage A, not a new mechanical gap. Reopening it on one unconfirmed instance
would repeat the asymptote-chasing already named and stopped once.

---

## Stage A — surface-variant merge

Built and debugged across five rounds, each a distinct finding.

1. **Design flaw caught before running.** Union-find on raw token overlap would
   false-merge `"mrs. holt"` and `"mrs. transome"` on the shared honorific alone.
   Fixed with honorific and article stripping (`core_tokens`) first.
2. **707-member cluster on the first real run.** Union-find's transitivity: any
   chain of pairwise overlaps merges unrelated nodes connected only through
   intermediates. Fixed with direct pairwise matching, no transitive closure.
3. **Wrong canonical selection.** "Longest string wins" let `"young mr. morel"`
   claim `"mr. morel"` before `"walter morel"` got a turn. Fixed by flagging any
   node matching two or more distinct longer candidates as
   `AMBIGUOUS_VARIANT_CANDIDATE` (decline, a new tier) instead of selecting by
   length. Max cluster size fell to 16, with Holt and Transome confirmed apart.
4. **Two validation-script bugs, not resolution bugs.** `cluster_of` and the
   large-cluster report both treated `canonical_form=None` as a real, comparable
   value and reported false merges between unrelated ambiguous entries. Found
   serially: the second occurrence was not checked for when the first was fixed,
   which cost a repeat round.
5. **Shared-modifier false merges.** `young holt` / `young felix` / `young
   debarry` and `old man` / `old spot` / `old aunt` linked via the shared modifier
   surviving `core_tokens`. A hard suffix veto (jr, sr, roman numerals,
   young/old) was added for the *adjacent* case (a bare name versus its modified
   form); the *lateral* case (two different modified names matching each other)
   remains.

**Frozen at its real ceiling.** The lateral case, and the class it represents
(Jacob versus Jacob Jr.; `poor man` needing scene or addressee context; any case
where identity depends on discourse rather than string shape), is not solvable by
token overlap regardless of further rules. This was confirmed empirically and is
consistent with the literature (aliases can share zero overlap; book-scale
coreference never fully closes). Further patching would be minor fixes to a
strategy at its ceiling.

**Scope as built and validated:** honorific and article stripping; pairwise,
non-transitive token overlap; decline on ambiguity (two or more candidates); hard
veto on generational or age-distinguishing suffixes. Genuine merges exist (the
Lizio cluster); the Morel cluster declines safely rather than merging wrongly.
**Accepted limitations:** generic shared modifiers can still link two different
modified names; no narrative context of any kind; and per-book ambiguous-decline
counts are large (12–239 depending on book length and structure), expected given
the first two.

**Single-book expectation.** A curated single-book build should show cleaner
numbers than the six-book run, but for a narrower reason than assumed: it removes
cross-book collision risk (the Decameron's roughly 100 novellas sharing one
`book_id` was the largest single source of false positives) and reduces volume.
It does not close the within-book narrative-context problems.

---

## Wiring into live retrieval

Resolution maps are loaded and applied in retrieval (see
[`architecture.md`](architecture.md#resolution-layer) for the integration state).
A real-usage audit of the wired-in result found three distinct problems:

1. **Pronoun and generic terminal answers** (`"her son"`, `"you"`, `"the old man"`
   as chain answers) reached output. The diagnostic that exposed this built its map from Stage A only and discarded the Stage 0 entries, so the pronoun tier was absent from it; the saved map contains them (100 `excluded_pronoun_generic` entries in book 40882). Nothing checked a *computed answer* independently.
2. **A terminal-answer and pair-exclusion defect** reproduced on the Mrs.
   Transome case; see
   [`v2-retrieval-findings.md`](v2-retrieval-findings.md#terminal-answer-and-pair-exclusion-investigation).
3. **A diagnostic harness testing the wrong depth** (hardcoded `max_hops=1`
   against the pipeline's real effective depth), repaired by extracting the
   depth computation as an importable function.

Related but unresolved: a "Mrs. Holt's son's wife" question answered `mistress
holt` instead of the wife, flagged and not investigated (possibly the
vector/entity-linking mismatch recurring).

**End-to-end result.** On the correctness yardstick the layer currently *lowers*
accuracy; see [`benchmarks.md`](benchmarks.md#resolution-layer-ab). The frontier
diagnostic improved while the end-to-end score worsened.

---

## Status

- Stage 0 and Stage A: built, validated on the corpus, wired in. Stage A frozen.
- Entity resolution is **not complete**: the layer is wired in, measured negative
  on the yardstick, and the proposed fix (endpoint-gate removal) is unmeasured.
- Stage B and Stage C: deferred to a later checkpoint; windowing must exist first.
- Open: the roughly 14 unclassified "unrelated" functional-step cases remain
  unspot-checked; the pilot's 33% "unrelated" bucket is a mix of hard aliases and
  source relation-semantics conflation, and its split has not been quantified.
