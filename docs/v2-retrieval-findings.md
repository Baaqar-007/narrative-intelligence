# v2 Findings — Retrieval, Traversal and Direction Detection

Empirical findings from building and auditing temporal phrase parsing (Week 6)
and multi-hop retrieval with query-direction detection (Week 7 and the
post-audit rounds that followed). The resulting design is in
[`architecture.md`](architecture.md#retrieval); measurements are in
[`benchmarks.md`](benchmarks.md).

Contents: [Week 6](#week-6--temporal-phrase-parsing) ·
[Traversal](#week-7--traversal-findings) ·
[Direction detection](#week-7--direction-detection-module) ·
[Real-usage audit](#week-7--real-usage-audit) ·
[Post-audit round](#post-audit-fix-round) ·
[Dual-expansion spike](#dual-entity-expansion-spike) ·
[Terminal-answer investigation](#terminal-answer-and-pair-exclusion-investigation) ·
[Test-suite triage](#test-suite-triage) · [Status](#status)

---

## Week 6 — temporal phrase parsing

Built `temporal/phrase_parsing.py`: `parse_temporal_phrase()` (relative position
phrases to `{start_frac, end_frac}`) and `resolve_to_bins()` (fraction to bin
range for a book's bin count). No literature source; worked directly against the
real corpus. The existing exploration notebook was reused, since one module was
built rather than a new research thread (two cells added: real per-book bin
counts, and an automated sweep across every `N` occurring in the corpus).

Findings from real-corpus testing:
- **The corpus bin distribution is heavily capped**: 84 of 96 books hit N=20;
  only 12 adapt (7 at N=6, one each at 9–13). See
  [`known-limitations.md`](known-limitations.md) item 14.
- **`np.int64` leaked through `resolve_to_bins()`.** `min(num_bins, start_bin)`
  preserves the smaller argument's type, so a numpy type leaked when clamping
  landed on `num_bins`. Fixed at the module boundary.
- **All 96 books passed the sanity sweep** (`1 <= start <= end <= N` for every
  real N from 6 to 20). Interpretations were correct on the sparsest (N=6), mid
  (N=20) and densest (N=20) books; out-of-scope and gibberish phrases return no
  match.
- **Coverage confirmed** on standard phrasings (`"near the end of the book"`,
  `"in the first third"`, `"two-thirds of the way through"`, `"the second half"`).
  Non-temporal phrasing correctly declines.

Two findings (the leak and the cap) came from running against real edges rather
than trusting the design. Sweeping every N, not three sample books, was
deliberate, because an off-by-one at one specific N could hide between samples.

---

## Week 7 — traversal findings

- **Question generation was wrong for some relations** (the benchmark generator
  derived phrasing independently of the verified templates; `child_of`,
  `protector_of` and `leader_of` asked the opposite of their ground truth). Fixed
  with `relation_to_question()`, scoped to the 31 templated relation types. See
  [`benchmarks.md`](benchmarks.md#week-7-corrections-to-the-v1-benchmarks).
- **`graph_n_hop_search()` and `find_n_hop_paths()` were forward-only.**
  `.edges(nbunch=[node])` never returns in-edges (confirmed directly in
  NetworkX). The consequence is silently missed reachability for relation types
  stored inconsistently in direction (`companion_of` and other symmetric types).
  Demonstrated on a constructed graph before fixing.
- **Direction-agnostic traversal was tried broad (all 48 types), then scoped.**
  The broad version grew the reachable set 3.5–4 times at 2–3 hops, and newly
  recovered nodes skewed toward high degree (median 2 against corpus median 1;
  mean 16.8 against corpus mean 9.7). Scoping reverse traversal to the seven
  confirmed symmetric relations (`companion_of`, `friend_of`, `enemy_of`,
  `rival_of`, `sibling_of`, `spouse_of`, `relative_of`) cut absolute
  recovered-node volume by about 31% at 2 hops (32.2 versus 46.7 recovered) but
  left the skew ratio unchanged (median 2, mean 17.1). High-degree nodes here are
  protagonists connected through many relation types at once, so restricting the
  relation type that triggers reversal does not change who is structurally most
  reachable.
- **Decision.** Ship the scoped version, which matches what the data evidenced.
  Hub skew is logged as a measured property and explicitly *not* as a confirmed
  problem: degree-distribution skew and retrieval-quality harm are separate
  claims and only the first was measured. Elevated protagonist-centrality may be
  structurally correct for a narrative graph (a query about a protagonist's
  companion should surface protagonist-adjacent, high-degree territory). A
  revisit trigger was pre-registered (see
  [`benchmarks.md`](benchmarks.md#methodology-rules)); any degree cap must be
  validated against that accuracy split, not its own skew output.
- **The existing metric could not see the fix.** Reachable-set-size and
  degree-distribution diagnostics were needed because the benchmark was a
  self-consistency check by then. See the benchmark validity table.

---

## Week 7 — direction-detection module

Built `retrieval/direction_detection.py` after three approaches (cosine
similarity, a dependency parser, anchor-phrase matching) were tried in order;
the reasons each lost are in
[`architecture.md`](architecture.md#query-direction-detection-retrievaldirection_detectionpy).

**Four bugs caught by testing the module against its own design:**
1. A mechanical `-er`/`-or` suffix strip produced broken stems (`mother` to
   `moth`, `mentor` to `ment`, `lover` to `lov`), and `ment` collided with
   "mentioned" and "sentiment", a silent false positive. Fixed by hand-verifying
   the verb-form list.
2. `travel_to`'s anchor is `"to"`, which matched any query containing the word.
   Every other anchor is 7+ characters; fixed with `MIN_ANCHOR_LENGTH = 5`.
3. Short entity names matched as substrings of unrelated names (`"An"` inside
   `"Ann"`). Fixed with word-boundary matching.
4. (Found while wiring into `hybrid_search`.) 15 of 31 templates use `a`/`an` as
   the anchor article, but `the X of Y` is equally natural and was missed
   entirely. Fixed with article-variant matching.

**Integration.** `entity_to_expand_from()` replaced a hardcoded "always expand
from entity2" default (flagged as provisional when chains were first built), and
`direction_match()` annotates each fact with `True`, `False` or `None`. The
annotation is additive-only because a mismatch means a fact does not directly
answer the question in the direction asked, not that it is wrong; showing,
hiding or deprioritizing it is left to the consumer, keeping retrieval and
presentation separate.

**An informative integration result.** For the motivating "protector of the
friend of the knight" question, the single-hop fact is correctly flagged
`query_direction_match: False` (the literal phrasing implies the opposite of the
stored direction), yet `chains` still finds the complete correct multi-hop
answer, because chain expansion explores the neighborhood of the query-relevant
entity rather than being bound by one fact's direction. The system is honestly
uncertain about the single fact and correct about the answer: the two mechanisms
serve different purposes.

**Verification at the time:** 72 passing tests across the traversal, direction,
templating, hybrid-search, benchmark and ontology test modules. (A later check,
below, showed why tests alone were not enough.)

**Open items recorded at the time, and what became of them:**
- `answer_generation.py` and `schemas.py` had never been reviewed against the new
  chain fields. Later reviewed; `ChainFact` was found to be missing the `answer`
  field and answer generation never reads it (see
  [`architecture.md`](architecture.md#answer-generation)).
- Direction was checked against only the first relationship of a multi-relation
  pair (`relationships[0]`). Later replaced by using the retrieved fact's own
  relation.
- No end-to-end test with real ChromaDB and a real encoder existed. The
  real-usage audit below used exactly that.

---

## Week 7 — real-usage audit

After Week 7 was declared closed (traversal, direction detection, wiring, API and
UI shipped and tested), real, unscripted use of the live system was checked
against the project's north-star question: does making narrative state explicit
give causal traceability, structural consistency, controllability and
reproducibility that implicit LLM simulation does not? Two diagnostics were built
to get evidence rather than debug from memory: a text-only direction-coverage
script (`diagnose_direction_coverage.py`) and a full-pipeline script
(`diagnose_pipeline.py`) against the real corpus, ChromaDB and encoder.

**The core lesson.** All 93+ Week 7 tests used synthetic graphs or questions from
`generate_questions()`, and the detector was validated against exactly the
phrasing those generators produce (`"Who is X a Y of?"`). Benchmark and detector
were tested against each other's output, never against independent human
phrasing: the same trap as the self-consistency benchmark, one level higher in
the stack, where no unit test could see it. This is the most important finding of
the project so far, and it changes what "complete" means.

### 1. Direction coverage: near-total failure on real phrasing

Run on 3 real corpus names (Taug, Akut, Teeka) across 8 phrasing styles:
- `of`-genitive (the tested style): 100% detected.
- **Possessive genitive** (`"Taug's companion"`, `"Taug's friend's leader"`): 0%
  detected, consistently across all three names. `detect_query_direction()`
  itself returned `None`, so `direction_match` and `entity_to_expand_from` were
  silently inert for this whole family, not only for chains.
- **A confident false positive** (not just missed coverage): `"Who does Taug's
  companion protect?"` was detected as `forward`, which is wrong (the query is
  about the companion's protectee, a 2-hop relation). Substring verb matching
  found "Taug" before "protect" with no awareness that `"'s companion"` sits
  between them. Possessive handling was subsequently built; a re-test of this
  exact query is not recorded.
- **Yes/no questions** (`"Is Taug a companion of Akut?"`) are treated as
  wh-questions seeking an unknown entity: a missing question-type
  classification the system was never designed to have.

### 2. Chains: 0 of 11 on real multi-hop questions, three compounding causes

On 11 real questions from Felix Holt, each checked twice, `hop_depth = 0` and
`total_chains = 0` on **all 11**:
1. Possessive genitive, compounded under an of-genitive prefix (`"the mother of
   Esther Lyon's husband"`: the outer phrase matches, the inner one does not).
2. **Missing gendered kinship vocabulary:** templates had `parent_father_of` and
   `parent_mother_of` but nothing for husband, wife, son or daughter, a real
   ontology-coverage gap dating to v1.
3. **Modifier breaks the exact match:** `"the biological father of"` does not
   contain `"the father of"`; contiguity was required.

### 3. Entity canonicalization: worse than any prior finding

Matched pairs included bare pronouns as canonical names (`('rufus lyon', 'you')`,
`('mr. lyon', 'her')`) and full descriptive clauses (`('jermyn', "jermyn's third
daughter")`). Earlier findings concerned *ambiguous* strings; these are raw,
uncleaned noise that could never appear in a user's query. This explains why
`query_direction_match` was `None` almost everywhere: there was nothing to anchor
to regardless of phrasing coverage. It reshaped entity-resolution scoping
([`v2-entity-resolution-findings.md`](v2-entity-resolution-findings.md)).

### 4. Reproducibility: cleanly isolated to one layer

`retrieval_stable_across_calls = True` on all 11 questions, so traversal and
retrieval are deterministic. `llm_stable_on_same_facts = False` on 10 of 11,
traced to `temperature=0.2`, a v1 default never revisited. Most differences were
cosmetic; one was not. For "Who is the lawyer that manages the estate of Mrs.
Transome's son?", identical facts produced "cannot be determined" on one call and
an unhedged "...is Lawyer Jermyn" on another (inferring "owns" implies
"manages"), violating the prompt's own instruction on roughly half of identical
trials, on a question that is not even multi-hop. Setting `temperature=0` raised
stability to 10 of 11 (the remainder cosmetic wording only) with retrieval
unchanged.

**Fix order recommended after the audit:** `temperature=0`; gendered kinship
synonyms and modifier-tolerant anchors; possessive-genitive support in
`detect_query_direction()` itself; feed the canonicalization severity into Week 8
scoping. All four were subsequently done or scoped.

---

## Post-audit fix round

**Two root-cause bugs closed.**
- `entity_to_expand_from` silently defaulted to `entity2` when direction was
  undetermined, the root cause of the "Esther Lyon's husband" wrong-chain finding.
  It now returns `None`, and `hybrid_search` skips chain expansion cleanly on
  `None` instead of passing it through as a node name.
- `hybrid_search` passed `query_target_relation` where `matched_relation` (the
  retrieved fact's own relation) was needed; the correct value was computed one
  line later and never used for this call. Fixed by reordering.

**Smaller fixes.** Missing `parent_mother_of`/`parent_father_of` entries in
`NOUN_SYNONYMS`; possessive matching loosened to tolerate trailing words before
`'s` (with the coordinated-possessor limitation logged, not fixed);
`target_relation()` fixed for two compounding bugs (a silent 3-way tie resolved
by dict insertion order after the synonyms were added, and a leftmost-only
heuristic invalid for possessive chains); and the chain-diagnostics script
(`diagnose_chain_hubs.py`) deduplicated by `(path, relations)` per question, because it had inflated counts
about 5 times wherever one fact is retrieved through several chunks.

**Verified, not assumed.** The positive control (Taug/Tarzan `enemy_of` chains in
book 106) stayed clean across every fix: 9 unique chains, no leakage. On book
40882, `expand_from` resolution rose from 0 of 50 to 24 of 50 hits; the remaining
`None`s traced to separate, correctly declining causes.

**New findings, logged, not fixed:**
- A punctuation-variant node split: `'mrs.holt'` vs `'mrs. holt'`.
- Vector recall returning the wrong relation type (`"Felix Holt's wife"`
  retrieving `child_of` facts, 5 of 5 and 3 of 5 hits on two questions). Correctly
  declined downstream, but upstream of direction detection.
- 3 hits where neither entity string appears in the query (`'her'`, `'his
  daughters'`, `'party'`): bare pronoun and generic node names.
- 1 untemplated relation (`owns`); 31 of 48 relation types are templated.

**Later generalization test.** The single-expansion fixes were checked on four new
books plus the baseline and control at 96.9–100% resolution, but that measured
only that detection fires (see
[`benchmarks.md`](benchmarks.md#direction-detection-generalization-test)).

---

## Dual-entity expansion spike

Motivation: single-entity expansion is brittle to phrasing gaps found one query
at a time; dual expansion (traverse from both entities of the matched pair, rank
by whether either side's chains end on `target_relation`) was proposed as a cheap
hedge with no new architecture. It converged on a negative result after five
iterations, each fix surfacing a new bug:

1. First evidence of value: the Mrs. Transome question found the correct answer
   (`jermyn`) mid-chain for the first time.
2. Terminal-role assignment (treating `c["end"]` as the answer) breaks beyond 1
   hop; the answer is entity1 of the terminal edge. Fixed via the `directions`
   metadata.
3. That fix regressed the exclusion check (compared `answer == other` only, not
   `answer == start`), so a direct `taug -enemy_of-> tarzan` edge answered "taug"
   to a question about taug. Fixed by checking both.
4. The entity1-is-the-answer rule is wrong for `SYMMETRIC_RELATIONS`, where
   entity1/entity2 is an arbitrary storage choice, not a role. It zeroed the
   positive control for a round. Fixed by branching on symmetry.
5. **Fundamental gap, not patched:** 1-hop `taug -enemy_of-> X` chains satisfied
   the terminal filter, answering "who is taug's enemy" instead of "who is the
   enemy of taug's companion". Nothing enforces relation order across hops;
   `mentioned_relations()` tracks which types appear, never their sequence.

Final state: 33 candidate chains, 1 correct (`mrs. transome -> harold ->
jermyn`); the rest pronoun or clause node names, relationally wrong answers, or
the wrong-question chains of finding 5. The positive control was unstable across
iterations (10 clean, 40+ leaked, 0 over-strict, 10 wrong-shape). The spike was
**reverted** to single expansion. Dual expansion is architecturally cheap but not
cheap in correctness: its accuracy needs relation-sequence and role reasoning
that single expansion gets free from `detect_query_direction` on the matched
fact. One hop-budget bump was dropped by accident in the first revert pass
(caught when the positive control returned 1 hop instead of 2) and restored.

The gap found is a traversal-ordering problem, not a phrasing-coverage problem,
so it does not reopen the question of using an LLM for query parsing, which was
already parked by the clean single-expansion generalization result. A
relation-sequence extractor (ordered steps: possessives left to right, then
of-genitives right to left, an untested hypothesis) is proposed and gated on the
pre-registered first-step measurement.

---

## Terminal-answer and pair-exclusion investigation

The Mrs. Transome case ("the biological father of Mrs. Transome's son") took
four sessions to separate into distinct causes.

1. **Located.** A real-usage audit of the wired-in resolution layer found that a
   correct 2-hop answer was dropped and a 3-hop overshoot kept. Isolated against
   a synthetic graph (after six rounds of live-diagnostic tracing failed), the
   cause was in the answer-vs-`other` exclusion: `_terminal_answer` returns
   `path[-2]`, here `"harold"`, which equals the vector-matched pair's second
   entity `other`, so the correct 2-hop answer was excluded while the 3-hop
   overshoot (answer `"jermyn"`, not equal to `other`) survived. An earlier
   attempted fix, `_is_redundant_continuation` (prefer a chain whose shorter
   prefix already satisfies the terminal relation), traced correctly in isolation;
   the defect lay elsewhere.
2. **Reclassified, then qualified.** Verifying the synthetic fixture against the
   real graph found it stores both `mrs. transome -> harold` and `harold -> mrs.
   transome` as `parent_mother_of`, a genuine source contradiction, which led to
   the corpus-wide count of 92 (see
   [`data-findings.md`](data-findings.md#bidirectional-parentage-contradictions)).
   That reclassification was **incomplete**: the contradictions are real, but
   whether they explain Transome specifically is unverified, and
   `_terminal_answer`'s behavior for non-symmetric edges is a separate cause.
3. **Confirmed general.** The exclusion gap reproduced on a synthetic
   knight/squire/lord fixture independent of any contradictory graph.
4. **Fixed.** Exclusion now applies only to 2-node chains (`len(path) == 2`);
   a chain of depth two or more landing on `other` is a genuine answer. Dead code
   left over from the reverted dual-expansion spike (`_expand_from_entity`) was
   deleted. The check
   was **structural only**, not a run across the three known cases, and the direction follows from the `protector_of` template: `squire -protector_of-> lord` means squire protects lord, so the four `lord` tests expect the answer to "who does squire protect", not "who protects squire". With the edge flipped (`lord -protector_of-> squire`), no chain reaches lord (checked), because traversal does not follow non-symmetric in-edges.
5. **Esther's harness** (diagnostic depth mismatch) was repaired by extracting
   `_effective_hop_depth`; rerun, every reachable chain from the matched pair was a
   `spouse_of` chain,   every reachable chain was a `spouse_of` chain. A later check found the only `parent_mother_of` edge into Felix Holt is an in-edge from a pronoun node, which traversal cannot follow, so the question is unanswerable even from the correct start. A vector-recall contribution is possible and unmeasured.

**Overshoot (separate, open).** The terminal-relation filter keeps any chain
whose last edge matches `target_relation`, with no shortest-chain preference.
Where `estimate_hop_depth` returns a budget deeper than the true distance (the
`son`-matches-three-relations ambiguity, a third recurrence of that root cause),
DFS continues past the answer: "the biological father of Mrs. Transome's son"
returns the correct answer plus three variants ending on Jermyn's daughters. A
precision bug, consistent with the measured impurity of hits. The minimal fix
(keep only minimum-satisfying-hop chains per expansion) is identified, not
applied.

---

## Test-suite triage

Seven failures were carried from the Week 8 consolidation (first recorded as five;
the count was corrected on closer triage) and resolved to specific outcomes rather
than deferred as a batch:
- **`test_main.py` (3):** a real gap; the Week 8 `resolution_maps` addition to
  `api/main.py` was never reflected in the test fixture.
- **`test_direction_detection.py` (1):** genuinely stale; it asserted the exact
  fallback behavior (`entity2`) that was deliberately removed. Replaced with a test
  that asserts `None`.
- **`test_hybrid_search.py` (3):** *not* pre-existing drift as first assumed; the
  pair-exclusion gap above, reproduced on a synthetic fixture. The exclusion fix
  resolved two of them. The last,
  `test_redundant_path_back_to_entity1_is_filtered`, took three incorrect fix
  attempts, each tracing to a distinct cause once isolated: a placeholder query
  that `target_relation()` correctly returns `None` for; a query naming the wrong
  relation word relative to the test's graph (`mentioned_relations()` parses query
  text, not graph content); and a shared fixture whose collection metadata said
  `friend_of` (the shared `single_hit_collection` fixture) while the query said
  "companion" and the graph held `companion_of`,
  a three-way inconsistency that silently broke direction detection. Fixed by
  building a matching collection inline. Lesson: when a traced-correct fix still
  fails a test, check the test's own internal consistency before re-suspecting the
  code.

A structural replacement for the Mrs. Transome test was written because the old
one hand-copied the previous filter and passed only by asserting a failure; the
chain-filter sequence is now a named function (`select_chains`) shared with the
code under test.

---

## Status

- Direction detection and chain traversal: built and in the live path. Coverage
  and correctness gaps are listed in [`known-limitations.md`](known-limitations.md)
  (items 9, 12, 17, 19, 20, 21).
- Open: role-aware terminal step; overshoot fix; relation-sequence enforcement;
  measuring the endpoint-gate removal; real-usage check on a non-Felix-Holt book.
