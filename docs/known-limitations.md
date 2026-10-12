# Known Limitations

The complete list of known limitations, with the current status of each. Items
1–14 are the original v1 list; their numbers are kept stable because other
documents reference them. **There is no item 13** (the original list skipped
from 12 to 14, and the number has not been reused). Items 15 onward were
identified during v2.

**Status vocabulary:** *Open* (unresolved), *Mitigated* (reduced, not removed),
*Accepted* (source-data property; documented, not engineered around),
*Superseded* (replaced by later work), *Resolved*.

Where a v1 limitation has since changed, the **v1 statement** and the
**current status** are both given.

---

## Original list (v1)

### 1. Generic and collective entities unresolved

`"apes"` vs `"the apes"` vs `"young apes"`, and `"elephant"` vs `"the
elephant"`, remain distinct nodes. Surfaced repeatedly: entity canonicalization,
the multi-hop benchmark caveat, and the hop-count bug investigation.

**Status: Open.** Judged a different problem from alias resolution: these may
not share a single true referent, so a node merge could be wrong (a generic
statement versus a specific tracked group; `young apes` may be a genuine subset).
The planned approach is `instance_of` edges from a mechanical heuristic, not
merges. Deferred (see [`roadmap.md`](roadmap.md)). The pronoun/generic filter
excludes pronoun and generic-noun *nodes*; it does not resolve group nouns.

### 2. No cross-alias or nickname resolution

`Tarzan` versus `Lord Greystoke` is not merged. A `difflib` fuzzy match was
tried and found unreliable on short strings.

**Status: Open, partly mitigated.** Mechanical surface-variant merging is built
(honorifics, articles, name parts). True aliases with no string overlap
(`wotan` / `wanderer`, `the king` / `tancrede`) are not mechanically solvable;
this was confirmed on the corpus. Deferred to coreference and hard-alias work.

### 3. Relation direction inconsistent for symmetric relation types

`companion_of` appears in both directions for the same pair in the source data.

**Status: Accepted, handled.** Direction-agnostic queries in the temporal layer;
traversal reverses exactly the seven confirmed symmetric relation types. Not
fixed at the data level.

### 4. Book 74763 has 0 relations

**Status: Accepted.** Real and explained; excluded from retrieval-ready lists
and corpus-wide measurements.

### 5. One malformed row in raw ARF

**Status: Accepted.** Filtered; a source-side artifact.

### 6. `relationship_trajectory()` cannot distinguish "no relationship" from "unrecognized entity"

Both return an all-zero dense trajectory.

**Status: Open.** Acceptable while entity names are graph-controlled; needs
explicit validation once free-text entity references are accepted.

### 7. `used_by` direction inconsistent in ARF itself

**Status: Accepted.** See [`data-findings.md`](data-findings.md#used_by-direction-inconsistency).

### 8. Non-canonical (free-text) relation strings, about 2.5% of instances

Excluded from canonical-only queries by default; not normalized.

**Status: Accepted.** No safe mechanical mapping exists.

### 9. Query-side entity-role and direction detection

**v1 statement:** not implemented; hybrid search returned both directions,
labeled, and left intent resolution to the LLM.

**Current status: Implemented in v2; coverage incomplete.** The module exists
(see [`architecture.md`](architecture.md#query-direction-detection-retrievaldirection_detectionpy)).
Remaining gaps:
- Yes/no questions ("Is Taug a companion of Akut?") are treated as wh-questions;
  no question-type classification exists.
- The possessor-is-the-wanted-role assumption is wrong for `son`/`daughter` on
  `parent_mother_of`/`parent_father_of`; an explicit role table is drafted but not
  wired in.
- Some possessive-chain questions leave `target_relation` as `None` (a known,
  unchanged case from the real-usage audits).
- A coordinated possessor ("Taug and Akut's mother") would misattribute.
- Questions ending in the entity2 role were 100% declined in an early yardstick
  run, with `target_relation` returning `None`; the proposed cause (`son` tying
  three relations) is unconfirmed.
- Generalization was measured only as "detection fires", not "detection is
  correct".

### 10. Benchmark 4's baseline used a phrasing-weak template

**Status: Superseded.** Benchmark 5 replaced it with natural chained phrasing.
Both remain historical; see [`benchmarks.md`](benchmarks.md#validity-status-of-v1-benchmarks).

### 11. Memory footprint is driven mainly by PyTorch

An ONNX Runtime backend would likely shrink it, reopening tighter-memory free
hosting.

**Status: Open, not needed.** See [`deployment.md`](deployment.md#memory-footprint).

### 12. No multi-hop query routing in the live API

**v1 statement:** `hybrid_search()` performed only single-hop enrichment; the
multi-hop traversal from the benchmarks was not wired into `/query`. Mitigated
by a prompt that makes the model admit it cannot answer rather than guess.

**Current status: Wired in; accuracy limited.** Real n-hop traversal is in the
live path with direction detection and typed filtering. It was initially
near-inert on real phrasing (0 of 11 real multi-hop questions produced a chain
before the audit's fixes). Current end-to-end accuracy is measured on the
yardstick (HIT 38.0%, DECLINED 48.6%, WRONG 13.4% with no resolution maps; see
[`benchmarks.md`](benchmarks.md#run-history-read-carefully-populations-and-code-differ)).

### 14. Adaptive temporal binning is adaptive for only about 12% of the corpus

84 of 96 books exceed the 300-relation threshold that hits the N=20 cap, so most
books get the same bin count regardless of density above it (book 44 at 2,667
relations and book 106 at 1,280 both get N=20). A property of v1's own formula,
found incidentally.

**Status: Open, not urgent.** Revisit only if temporal-query resolution proves
too coarse on dense books.

---

## Identified during v2

### 15. Source contradictions can reach the LLM unflagged

The graph contains 92 unambiguous bidirectional parentage contradictions (41
`parent_father_of`, 39 `parent_mother_of`, 12 `child_of`). The answer prompt has no handling
for contradictory facts, so a contradiction can reach the phrasing step without
a flag.

**Status: Open.** See [`data-findings.md`](data-findings.md#bidirectional-parentage-contradictions).

### 16. Entity-name noise in the graph

Pronoun, clause-length, generic and surface-variant strings are stored as node
names. On the full corpus, 22.4% of 1,298 functional-step frontiers are
contaminated (19.4%, 43 of 222, on the six-book pilot).

**Status: Mitigated.** A pronoun/generic filter and a surface-variant merge are
built; 79.7% (This measure drops pronoun/generic and ambiguous-tier entries from each frontier, so "resolved to at most one answer" counts removing real names as success. That is the same removal that cost 395 of 470 correct nodes on the yardstick. Frontiers reduced to zero answers were not counted separately) of contaminated frontiers resolve to at most one answer, 40 of 286
are unchanged, and the remainder hits a narrative-context ceiling. The same layer
currently lowers yardstick accuracy (item 18).

### 17. Terminal-answer computation returns an already-passed node for non-symmetric edges

`_terminal_answer` returns `path[-2]` for a forward non-symmetric terminal edge.
Suspected cause of a class of wrong answers: 83.9% of 118 newly wrong e1 answers
sit in the anchor's own first-step frontier. The mechanism is inferred, not
traced chain by chain.

**Status: Open.** A role-aware terminal step is proposed, not built.

### 18. The resolution layer currently lowers end-to-end accuracy

On the yardstick (traversal code before the endpoint-gate removal), HIT fell
from 38.0% to 29.1% (34.2% under canonicalized scoring) and WRONG rose from
13.4% to 24.4% (19.3%). Tier exclusion removed real answers (395 of 470 correct
nodes in lost questions were in the ambiguous tier).

**Status: Open.** The endpoint-gate removal passes tests and is unmeasured. The
layer is wired in, measured negative, fix unmeasured.

### 19. Overshoot in the terminal-relation filter

When the hop budget exceeds the true answer distance (when a noun such as `son`
matches three relations), traversal continues past a correct answer and returns
further chains that also satisfy the terminal check. Confirmed on "the
biological father of Mrs. Transome's son?", which returns the correct answer
plus three overshoot variants. A precision bug, not a correctness bug.

**Status: Open.** A minimum-hop-depth preference is identified and not applied.

### 20. No relation-sequence enforcement

Nothing checks that a candidate chain traverses the relation the matched fact
established before satisfying the query's outer relation, so 1-hop chains can
answer a different question than asked.

**Status: Open.** A relation-sequence extractor is proposed and gated on a
pre-registered measurement; not built.

### 21. Vector search can match the wrong relationship type

Observed: "Felix Holt's wife" retrieved `child_of` facts about Felix's parents;
"Mother of Esther Lyon's husband" cannot be answered even from
the correct start node. In book 40882 the only `parent_mother_of` edge into
`felix holt` runs from the node `his mother`, with no out-edge. Traversal never
follows non-symmetric in-edges, and the one candidate is a pronoun string that
the answer filter rejects (see item 17). A vector-recall contribution is
possible and unmeasured.

**Status: Open.** Not measured at scale.

### 22. Answer-generation gaps

`_chain_line` never reads `chain["answer"]`; the prompt describes chains as
pre-verified, complete evidence although retrieval guarantees only that the
path exists and the last edge has the right type; no contradiction handling; no
truncation of hub fact sets.

**Status: Open.**

### 23. Coreference at book scale is unsolved

Neither tested model is safe for a single full-book call. `FCoref` is
memory-unstable near 60 chunks (about 6,600 words) and `LingMessCoref` silently
returns an empty result at 60 chunks (works at 17, ceiling between). A genuine
cross-chunk resolution has never been verified. Windowing is not built.

**Status: Open, deferred.** See
[`v2-entity-resolution-findings.md`](v2-entity-resolution-findings.md).

### 24. No event nodes; the ontology is stative

Events exist only as edge labels. Event-shaped relations number 33 corpus-wide
and EVNT-typed entities are heavily mistagged.

**Status: Open.** Design settled in principle; implementation pending.

### 25. Evaluation-tooling gaps

No independent human-written yardstick tier; the role table is shared by the
generator and any extractor; `yardstick.py` and `common.py` duplicate
`build_index`, `step`, `walk` and the adapter with different signatures (which
broke `compare_nameable.py`); the proposed fix for it has unconfirmed status.
`graph/traversal.py` and `api/static/index.html` were never covered by the
consumer-review pass.

**Status: Open.**

### 26. Template coverage is partial

31 of 48 relation types have a verified template; `owns` is a known untemplated
case. Benchmark question generation skips the rest.

**Status: Open.**

### 27. Hub skew is measured but not shown harmful

Newly recovered nodes skew toward high degree (median 2 versus corpus median 1;
mean 16.8 broad and 17.1 symmetric-only versus corpus mean 9.7). Scoping reverse
traversal to symmetric relations cut recovered-node volume by about 31% at 2 hops
but did not change the skew ratio.

**Status: Open, trigger pre-registered.** Revisit only if accuracy for
low-degree-answer questions is meaningfully worse than for hub-answer questions.

### 28. Stage A's accepted ceiling

Generic shared modifiers (`young`, `old`) can still link two different modified
names to each other; no narrative context exists to resolve "poor man" or to
tell an intentional suffix from a redundant one; per-book ambiguous-decline
counts are large (12–239 depending on book). These are within-book discourse
problems and do not shrink with a single-book scope.

**Status: Accepted.** Module frozen at this ceiling.

### 29. Pair-exclusion fix verified structurally only

The length-based exclusion was verified for structure only. The direction follows from the `protector_of` template: `squire -protector_of-> lord` means squire protects lord, so the four `lord` tests expect the answer to "who does squire protect", not "who protects squire". With the edge flipped (`lord -protector_of-> squire`), no chain reaches lord (checked), because traversal does not follow non-symmetric in-edges.

**Status: Open.**
