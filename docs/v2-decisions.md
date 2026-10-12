# v2 Decision Log

The decisions made during v2, with their status and the evidence behind them.
Numbers are stable identifiers (other documents cite them) and follow the order
in which decisions were recorded, not their theme; the log is grouped by theme
below for readability. v1 design choices are in
[`architecture.md`](architecture.md) and are not repeated here.

**Status vocabulary:** *Resolved*, *Open*, *Rejected*, *Reverted*, *Frozen*
(deliberately stopped at a measured ceiling), *Correction* (a prior record was
wrong and is amended), *Rule* (a standing methodological rule).

Contents: [Policy and scope](#policy-and-scope) ·
[Entity resolution](#entity-resolution) · [Events](#events) ·
[Retrieval and traversal](#retrieval-and-traversal) ·
[Evaluation](#evaluation) · [Tooling and process](#tooling-and-process) ·
[Documentation corrections](#documentation-corrections-decision-56)

---

## Policy and scope

**1. Resolved: an LLM is permitted only as a bounded verifier.** It may judge
identity over existing candidate entities and must never create entities or
relations. Prompted by three independent sources reaching for an LLM as an
identity verifier rather than an extractor (see
[`research-notes.md`](research-notes.md#cross-source-patterns)).

**2. Resolved: coreference uses a pretrained, off-the-shelf model.** No
fine-tuning or in-house build unless a later evaluation shows it necessary.

**3. Open: which pretrained coreference model.** Empirical testing found neither
candidate safe for a single full-book call (see
[`v2-entity-resolution-findings.md`](v2-entity-resolution-findings.md#coreference-tooling-experiments)),
so the choice is secondary to building windowing first.

**9. Correction, later closed: Week 7 was not complete when first declared.**
Direction detection was built, tested (93 passing tests) and wired in, but a
real-usage audit found it near-inert on real questions (0 of 11 chains on real
multi-hop questions). Passing tests was necessary but not sufficient evidence of
completion, and the premature claim was corrected rather than left standing. The
audit's fixes were later completed (see items 11 and 12 to 14).

---

## Entity resolution

**26. Resolved: Stage 0 (pronoun/generic filter) before Stage A (alias
merging).** Based on the pilot's quantified breakdown (58% pronoun/generic against
9% surface variants of confirmed fragmentation). At full scale the mix is 47.1%
and 19.6%, which keeps the ordering and roughly doubles Stage A's expected payoff.

**28. Resolved: Stage 0 built and validated on the corpus.**
`resolution/pronoun_filter.py`. Pilot contamination fell from 43 to 31 after the
first pass (25.6% resolved) and to 23 after two real misses (`"daughter"` and
plural handling) were fixed. Non-destructive.

**29. Finding: the "unrelated" bucket is not one thing.** It contains genuine
zero-string-overlap hard aliases (confirmed corpus-wide, not only in the
literature) and known ARF relation-semantics conflation.

**30. Resolved: `is_nameable()` delegates to `is_pronoun_generic`.** It had
duplicated the logic through its own drifted `_GENERIC` set. Delegation removes
the second source of truth rather than resyncing it.

**33. Frozen: Stage A (surface-variant merge) stopped at its measured ceiling.**
Five debugging rounds, each a distinct bug (transitive over-merging,
longest-string-wins, two `None`-handling validation bugs, a young/old
shared-modifier false merge). The high-precision scope works (honorific and
article stripping, pairwise matching, decline on ambiguity). Narrative-dependent
identity (Jacob versus Jacob Jr., "poor man") is empirically not solvable by token
overlap; continuing to patch would be minor fixes to a strategy at its ceiling.

**36. Resolved: full 96-book frontier baseline.** 22.4% contamination (291 of
1,298 frontiers), confirming the pilot's 19.4%. Two real vocabulary gaps fixed
from hand inspection (informal kinship terms; standalone judicial and
professional titles), leaving 286 contaminated frontiers, of which 79.7% resolve
to at most one answer (up from 75.3%).

**37. Resolved as wiring only: `resolution_map` is wired into live retrieval.**
`find_paths_up_to_hops`, `hybrid_search`, `ChainFact.answer` in the API schema,
and a startup load in `api/main.py`. An over-broad first version (declining on an
unresolved alias status rather than only on failed direction detection) was
corrected. "Wired in" is not "complete": see item 50.

**38. Resolved: pronoun and generic terminal answers.**  A computed chain answer could be a pronoun (`"her son"`,`"you"`) because nothing checked computed answers independently. Fixed by checking them against `is_pronoun_generic` directly. **Correction:** the day-9 reading that the map never contains pronoun entries was a diagnostic artifact (that script built a Stage A-only map). The saved map has them (book 40882: 100 `excluded_pronoun_generic`). The check stays as the guard when maps are off.

**40. Open: Week 8 is not closed.** The original blocking item (a code fix for the
Mrs. Transome case) no longer applies as stated, since part of that failure is a
source-data contradiction (item 39). Closure is blocked on the remaining work in
item 45 and on measuring the endpoint-gate removal (item 52), after which the
yardstick result in item 50 must be re-checked.

**50. Open, negative result: the resolution layer lowers yardstick accuracy.**
First end-to-end score of the layer: HIT 38.0% to 29.1% (34.2% under
canonicalized scoring) and WRONG 13.4% to 24.4% (19.3%), on the traversal code
before the endpoint-gate removal. Week 8's earlier results were diagnostic-script
measurements only. The correct status line is: *wired in, measured negative, fix
unmeasured.* Week 8 stays open.

**52. Open: ambiguous-tier endpoint exclusion removes real answers.** 395 of 470
correct nodes in lost questions were in the ambiguous tier. The endpoint-gate
removal passes tests and is **unmeasured**. Whether the ambiguous tier should ever
be excluded as an endpoint is open and in tension with Stage A's
decline-on-ambiguity design (item 33).

Stages B and C are deferred to a later checkpoint; windowing must exist first.

---

## Events

**4. Resolved: events become graph nodes through a two-tier, non-destructive
design.** Edge reification for event-shaped relations, plus a tiered
`event_candidate` map for EVNT-typed entities, with per-relation-type gating
corrected against real data. No new extraction; Vrittanta-EN ruled out, not
deferred. See [`v2-events-findings.md`](v2-events-findings.md).

**5. Open: event-node edge semantics.** Generic `involved_in` versus
role-differentiated edges; whether the original binary relation edge stays; one
event versus two for a single captor with two captives.

**6. Open: re-scope the 1,119 multi-typed-string count per book.** Currently
global; do not use it to argue anything beyond the confirmed `Tristan and Isolde`
example until re-scoped.

---

## Retrieval and traversal

**7. Resolved: question-generation direction bug fixed; traversal made
direction-agnostic for seven symmetric relations only.** Questions derive from the
verified templates. Historical 72% / 26% multi-hop figures are void.

**8. Open, trigger pre-registered: hub skew.** Skew in recovered n-hop nodes is
measured but not shown harmful. Revisit only if accuracy is meaningfully worse for
low-degree-answer questions than for hub-answer questions; any mitigation must be
validated against that split, not its own degree distribution.

**10. Resolved: API layer reviewed and updated.** `answer_generation.py`,
`schemas.py` and `main.py` (`ChainFact` schema, dynamic `hop_depth`, chains wired
through to the prompt and response, UI updated). A real off-by-one in hop-budget
compensation was caught only by testing through the real endpoint with a
dynamically estimated depth.

**11. Resolved: all four audit follow-ups.**
(a) `temperature=0` set; LLM stability 1 of 11 to 10 of 11, remainder cosmetic.
(b) Gendered kinship synonyms implemented, later extended to
`parent_mother_of`/`parent_father_of`. (c) Possessive-genitive support in
`detect_query_direction()` itself, later loosened for trailing-word tolerance with
the coordinated-possessor limitation logged. (d) Canonicalization severity
quantified (19.4%, 43 of 222; 58% pronoun/generic) and fed to Week 8 scoping.
(The earlier record listed (b) and (c) as unstarted although both already existed
in code; see item 56.)

**12. Resolved: `entity_to_expand_from` returns `None` on undetermined
direction.** The silent `entity2` default was the root cause of the "Esther Lyon's
husband" wrong chain.

**13. Resolved: argument-order bug.** `hybrid_search` passed `query_target_relation`
where `matched_relation` was needed; fixed by reordering.

**14. Resolved: `target_relation()` tie-breaking and shape.** A silent 3-way tie
resolved by dict insertion order, and a leftmost-only heuristic invalid for
possessive chains. Of-genitive chains now read leftmost, possessive-only chains
rightmost, ties decline.

**15. Open, evidence only: three new findings.** The `'mrs.holt'` / `'mrs. holt'`
punctuation split (feeds entity resolution); vector recall returning the wrong
relation type (upstream of direction detection; not measured at scale); the
untemplated `owns` relation (31 of 48 types templated).

**17. Rejected: dual-entity expansion.** Five iterations, each fix surfacing a new
bug; one genuine win (recovered a correct answer) offset by a fundamental gap (no
relation-sequence enforcement). The starting side is determined by the matched
fact, so searching both sides risks answering a different question.

**18. Open: relation-sequence enforcement.** A chain must traverse the relation
the matched fact established before satisfying the query's outer relation. A
traversal-ordering problem, not a phrasing or regex-versus-LLM one.

**21. Open, live bug: role slot for `son`/`daughter`.** These nouns on
`parent_mother_of`/`parent_father_of` name entity2's slot, so both the fixed
possessive-reverse rule and the entity1-answer rule are wrong for them. An
explicit `{relation: {noun: role}}` table (`ROLE_NOUNS`) is drafted, not wired in.

**22. Open, gated: `relation_sequence(query)` extractor.** Ordered steps
(possessives left to right, then of-genitives right to left, an untested
hypothesis) replacing three separate heuristics. Gated on the first-step
measurement's decision rule (see
[`benchmarks.md`](benchmarks.md#pre-registered-decision-rule-for-the-first-step-metric)).

**24. Reverted, with two salvaged pieces.** Single expansion restored after item
17. Kept: the symmetric-aware role logic and the answer versus end field
distinction. A regression (the hop-budget bump dropped in the first revert pass)
was caught by the positive control and fixed.

**25. Open: overshoot in the terminal-relation filter.** No shortest-chain
preference; a precision bug. Minimal fix (keep only minimum-satisfying-hop
chains) identified, not applied.

**39. Reclassified, then qualified: the Mrs. Transome failure.** First attributed
to a `_terminal_answer`/pair-exclusion defect, then to a source contradiction
(the graph stores both `mrs. transome -> harold` and `harold -> mrs. transome` as
`parent_mother_of`). The reclassification was incomplete: the 92 corpus-wide
contradictions are real, but whether they explain Transome specifically is
unverified, and `_terminal_answer`'s behavior for non-symmetric edges is a
separate cause. No code fix exists for the data contradiction itself.

**41. Partly resolved: Esther's diagnostic harness.** The hardcoded `max_hops=1`
was repaired by extracting `_effective_hop_depth` (item 46), and the rerun showed only `spouse_of` chains; a later check found the answer edge is a non-symmetric in-edge from a pronoun node (untraversable), so the failure is not shown to be a recall problem. The "Mrs. Holt's son's wife" answering `mistress holt` is flagged, not investigated.

**42. Finding: 92 bidirectional parentage contradictions.** `parent_father_of` 41,
`parent_mother_of` 39, `child_of` 12, across 95 books. `spouse_of` (302) and `sibling_of` (317)
bidirectional pairs are expected. See
[`data-findings.md`](data-findings.md#bidirectional-parentage-contradictions).

**46. Resolved, structurally verified only: pair exclusion by chain length.** A
chain is excluded as a restatement only when `len(path) == 2`. `_effective_hop_depth`
extracted as an importable function. See item 49 for the verification caveat.

**49. Correction: item 46's verification was overstated.** It was recorded as
verified against three cases; only structure was checked. The direction follows from the `protector_of` template: `squire -protector_of-> lord` means squire protects lord, so the four `lord` tests expect the answer to "who does squire protect", not "who protects squire". With the edge flipped (`lord -protector_of-> squire`), no chain reaches lord (checked), because traversal does not follow non-symmetric in-edges.
**51. Open, suspected cause: `_terminal_answer` returns an already-passed node.**
For non-symmetric terminal edges it returns `path[-2]`. Of 118 newly wrong e1
answers, 83.9% sit in the anchor's own first-step frontier and 98.3% had the first
step retrieved; the mechanism is inferred, not traced chain by chain. A role-aware
terminal step is proposed. Probably the same family as item 21; the link is
unconfirmed.

**53. Open: answer-generation review findings.** `_chain_line` never reads
`chain["answer"]`; the prompt calls chains pre-verified and complete evidence
though retrieval guarantees only path existence and a correctly typed last edge;
no contradiction handling; no truncation for hub entities. A recommendation to
surface `answer` was withdrawn (item 51).

---

## Evaluation

**16. Resolved, scope corrected: direction-detection generalization.** 96.9–100%
across four new books plus baseline and control measures that detection *fires*
(`expand_from is not None`), not that it is correct. Question phrasing was
script-generated; a real-usage check on a non-Felix-Holt book is open (item 19).

**19. Open: real-usage check on a book other than Felix Holt.** Unscripted
phrasing, distinct from item 16.

**23. Built and baselined: the correctness yardstick.** 6 books, 6,181 questions.
The early figures (41.4% HIT, 6.5% WRONG) describe the
dual-expansion spike and **must not be quoted as a baseline or floor.** Five of
six pre-registered predictions were confirmed or borderline; the asymmetric
first-step prediction failed (47.9% versus about 0%), correcting a wrong model of
where hop 1 comes from. See [`benchmarks.md`](benchmarks.md#v2-correctness-yardstick).

**27. Rule: pair comparisons by question ID and by run type.** An unpaired
comparison reported a 5.8-point regression and a 54% RECALL jump, both artifacts
of different question populations; paired, both were noise.

**31. Resolved: the `is_nameable` A/B comparison.** Two tooling bugs (RNG-based
ordering; order-dependent capping) had to be fixed before `only_new = 0` validated
it. Tightening costs 301 previously-HIT questions, of which 13.6% were pure
(against 24.8% corpus-wide): a net-positive trade. The earlier "997 HITs lost" is
invalid and superseded.

**54. Correction: "WRONG doubled" was an artifact of comparing across run
types.** Paired against the single-expansion run: HIT 44.5% to 38.0%, WRONG 11.8%
to 13.4%, pure-HIT 10.3% to 22.3% of questions, median answers 5 to 2.

---

## Tooling and process

**20. Resolved: diagnostic scripts moved under `scripts/diagnostics/`** and
tracked in git.

**32. Pattern: measurement tooling needs the same rigor as retrieval code.** Two
sessions running (shuffle bug, then capping bug).

**34. Pattern: consolidation-avoidance cost recurred a third time.** An unhandled
`None` fixed in one function and not checked in its sibling.

**35. Resolved in part: consolidation of the diagnostics.** The listed scripts now
import shared primitives and write outputs through a common path helper
(`output_path()`, which fixed CSVs landing in the repository root), closing
the repeated-reconstruction pattern of items 32 and 34. (Item 27 is a standing
methodological rule, not a task, and is not closed by this.) Residual duplication
remains: `yardstick.py` and `common.py` both define `build_index`, `step`, `walk`
and the adapter with different signatures, which broke `compare_nameable.py`.

**43. Lesson: dependency order among assumptions.** The Transome root cause was
locatable in one five-line read-only query proposed a session earlier; six rounds
of careful reasoning about a synthetic fixture preceded the one check that
mattered (does the fixture match reality?).

**44. Decided, not actioned: scripts for reruns, a notebook for single-shot
lookups.** Scripts remain the default for anything rerun as a regression check; a
`notebooks/week8_adhoc.ipynb` is the agreed home for read-only one-offs. Not yet
created.

**45. Open: Week 8 remainder.** Other-exclusion re-verification (item 49),
housekeeping, the `answer_generation.py` review (done, item 53), and the
direction-detection ceiling measurement, likely the largest remaining unknown.

**47. Resolved: the last of the seven test failures.** Three distinct causes, all
in the test's own inputs; fixed by an inline matching collection.

**48. Lesson: check the test's internal consistency first.** When a traced-correct
fix still fails a test, compare fixture metadata, query text and graph content
before re-suspecting the code.

**55. Open at the last recorded checkpoint.** A `USE_RESOLUTION = False` toggle
(proposed, application unconfirmed); the `compare_nameable.py` fix (unconfirmed);
measuring the traversal change; deciding the e1 stop-gap; building the role-aware
terminal step; the unconfirmed "son ties three relations" explanation for e2's
100% decline.

---

## Documentation corrections (decision 56)

A set of corrections to figures and claims that earlier records stated too
strongly. The documents in this repository reflect them.

1. **Early yardstick figures** (41.4% HIT, 6.5% WRONG) came from the
   dual-expansion spike and are not a baseline. Single expansion ("10/1") was HIT
   44.5%, WRONG 11.8%. Current code with no resolution maps: HIT 38.0%, DECLINED
   48.6%, WRONG 13.4%, pure-HIT 22.3% of 5,115 questions.
2. **"96.9–100% generalizes"** measured that direction detection returned a
   non-`None` result, not that it was correct.
3. **"Verified against three cases"** (pair exclusion) was overstated: only
   structure was checked, and the direction follows from the `protector_of` template: `squire -protector_of-> lord` means squire protects lord, so the four `lord` tests expect the answer to "who does squire protect", not "who protects squire". With the edge flipped (`lord -protector_of-> squire`), no chain reaches lord (checked), because traversal does not follow non-symmetric in-edges.
4. **Resolution wiring** is "wired in, measured negative, fix unmeasured", not
   "complete". The frontier audit improved (79.7% of contaminated frontiers
   resolved, 40 of 286 unchanged), yet on the yardstick HIT fell from 38.0% to
   29.1% (34.2% canonicalized) and WRONG rose from 13.4% to 24.4% (19.3%). 395 of
   470 correct nodes in lost questions were in the ambiguous tier. The later
   endpoint-gate removal passes tests and is unmeasured. Whether `USE_RESOLUTION =
   False` is applied is unknown.
5. **e1 and e2.** e1-ending questions ran about 7% HIT against 23% WRONG, and 83.9%
   of the new wrong e1 answers sit in the anchor's first-step frontier. That
   supports `_terminal_answer` returning an already-reached node, but the mechanism
   is inferred, not traced. e2 questions were 100% declined with `target_relation`
   returning `None`; the "son ties three relations" explanation is unconfirmed.
6. **Mrs. Transome.** The reclassification as source noise was incomplete. The 92
   bidirectional contradictions are real (41 `parent_father_of`, 39
   `parent_mother_of`; 12 `child_of`), but whether they explain
   Transome specifically is unverified, and `_terminal_answer`'s behavior is a
   separate cause.
7. **`answer_generation.py`** never reads `chain["answer"]`, and its prompt calls
   chains pre-verified, complete evidence. Retrieval guarantees only that the path
   exists and the last edge has the right type.
8. **Stage A.** Stage 0 came before Stage A on the pilot (58% pronoun/generic, 9%
   surface). At full scale it is 47.1% and 19.6%. Contamination is 22.4% of 1,298
   frontiers, against 19.4% (43 of 222) on six books.
9. **Duplication and gaps.** `yardstick.py` and `common.py` both define
   `build_index`, `step`, `walk` and the adapter with different signatures, which
   broke `compare_nameable.py`. `graph/traversal.py` and `api/static/index.html`
   were never reviewed.
