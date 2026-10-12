# Benchmarks and Evaluation

Two generations of measurement exist, and they are not interchangeable.

- **v1 benchmarks** (Benchmarks 1–5) measured single-hop and multi-hop
  retrieval against ground truth derived from ARF triples. They are kept as a
  historical record. Several were later found invalid or of limited meaning; the
  [validity table](#validity-status-of-v1-benchmarks) says which.
- **The v2 correctness yardstick** is the current end-to-end measure of whether
  the retrieval pipeline returns the *right* answer to a structured question.
  Its construction, caveats and results are in
  [the second half](#v2-correctness-yardstick) of this document.

Contents: [v1 benchmarks](#v1-benchmarks) ·
[Validity status](#validity-status-of-v1-benchmarks) ·
[v2 yardstick](#v2-correctness-yardstick) ·
[Resolution A/B](#resolution-layer-ab) ·
[Methodology rules](#methodology-rules) · [Reproducing](#reproducing)

---

## v1 benchmarks

**Ground truth** comes directly from ARF's own relation triples (for example
`{Taug, protector_of, Teeka}` becomes "Who is protector of Taug?" with a known
answer), so no hand-labeling is needed. Each benchmark samples real relation or
path instances and checks whether a system recovers the known-correct answer.

### Benchmark 1 — single-hop, entity membership (superseded)

Metric: does the correct entity name appear anywhere in the top-k results.
**Baseline and hybrid tied exactly (55.0% at k=5).** A zero-mismatch check over
all 200 questions confirmed the metric cannot detect the hybrid system's value:
it does not check direction, and at k=5 the baseline already returns enough
candidate names that enrichment rarely adds a new one. This was a benchmark
design flaw, not a system failure, and it was replaced by Benchmark 2.

### Benchmark 2 — single-hop, direction-aware

Checks whether the result states the fact in the question's correct direction
(`entity1`/`entity2` order), not just whether the right name appears.

| System | Accuracy |
|---|---|
| Vector-only baseline (top-1) | 33.5% |
| Hybrid (k=5) | 55.0% |
| Hybrid (k=10) | 69.0% |

**Root-cause check.** Of the 90 hybrid failures at k=5, **0** were "entity found
but wrong direction" and **all 90** were "vector search never surfaced the
entity pair". Once vector search finds the right pair, graph enrichment
recovers the correctly directed fact every time; the remaining gap is vector
recall. Widening k from 5 to 10 recovered more than half of the misses.

### Benchmark 3 — multi-hop (historical; numbers void)

Real 2-hop graph paths (`A -rel1-> B -rel2-> C`); the question asks for `C`
given only `A`.

| System | Accuracy |
|---|---|
| Vector-only (single query, k=10) | 26.0% |
| Graph traversal (2-hop BFS) | 72.0% |

At the time this was read as the strongest result in v1: vector search has no
mechanism to chain facts, so the 26% was attributed mostly to coincidental
overlap, while traversal chains facts by construction. **These numbers are void
and must not be compared with any later run.** See
[the Week 7 corrections](#week-7-corrections-to-the-v1-benchmarks). A caveat was
already recorded when they were produced: some correct answers were
pronoun-like entities (`"his brother"`), and how much of the 72% relied on
named versus pronoun answers was never quantified.

### Benchmark 4 — accuracy versus hop count

The first sweep (hops 1–4, `evaluate_graph_hop_accuracy`) showed a steep drop
(99%, 74%, 31%, 4%) that was a **bug, not a finding**: the traversal returned only the final BFS layer, but a
DFS-sampled path of length N does not guarantee the shortest-path distance is
also N. Confirmed directly with `nx.shortest_path_length` (DFS path length 3,
true distance 2). Accumulating all visited nodes gave 99%, 100%, 100%, 100%, but
that tests only whether BFS rediscovers a path known to exist, a sanity check on
the traversal implementation rather than a retrieval-capability trend.

Rebuilt with single-answer n-hop questions (`generate_nhop_questions`) and one
fixed phrasing at every depth:

| Hops | Vector-only baseline | Graph traversal |
|---|---|---|
| 1 | 21.0% | 99.0% |
| 2 | 12.0% | 100.0% |
| 3 | 16.0% | 100.0% |

The generic, hop-invariant query template makes absolute baseline values
incomparable with Benchmark 2's better-phrased 33.5%. Only the within-run trend
is valid (21% to 12% from 1 to 2 hops). The 3-hop uptick to 16% is most likely
sampling noise at n=100 per hop and is reported as such.

### Benchmark 5 — reproduction via `scripts/run_benchmarks.py`

A fresh, from-scratch pipeline build reproduced the single-hop result.

| k | Hybrid direction accuracy |
|---|---|
| 1 | 34.0% |
| 3 | 47.5% |
| 5 | 55.5% |
| 7 | 62.0% |
| 10 | 69.0% |
| 15 | 75.0% |
| 20 | 80.0% |

This is consistent with the exploratory 33.5% / 55% / 69% at k = 1 / 5 / 10 and
shows no plateau through k=20, so there is headroom in retrieval breadth at a
latency cost.

| Hops | Vector-only baseline | Graph traversal |
|---|---|---|
| 1 | 41.0% | 99.0% |
| 2 | 21.0% | 100.0% |
| 3 | 14.0% | 100.0% |

Natural chained phrasing at every depth ("who is the enemy of the companion of
Taug") replaced the hop-invariant template, yielding a monotonically decreasing
baseline (41%, 21%, 14%). That confirmed the earlier non-monotonic 21% / 12% /
16% run was a phrasing artifact. The vector-only trend shows degradation as
chaining requirements grow. The traversal column is a self-consistency check
(see below), not a capability measurement.

### Latest run

* Date: [Insert Date]
* Results folder: [Insert folder path]

| k | Benchmark 5 | Latest run |
|---|---|---|
| 1 | 34.0% | 32.0% |
| 3 | 47.5% | 49.0% |
| 5 | 55.5% | 58.5% |
| 7 | 62.0% | 64.0% |
| 10 | 69.0% | 68.5% |
| 15 | 75.0% | 75.0% |
| 20 | 80.0% | 79.0% |

| Hops | Benchmark 5 baseline | Latest baseline | n valid |
|---|---|---|---|
| 1 | 41.0% | 39.2% | 97 |
| 2 | 21.0% | 25.3% | 91 |
| 3 | 14.0% | 23.1% | 91 |

Single-hop figures agree within 3 points. The 3-hop vector baseline moved most (14.0% to 23.1%, n=91), flattening the earlier trend (still decreasing). The cause is unverified: sampling noise, or the question generator now being scoped to the 31 templated relation types. `evaluate_nhop_graph()` has been replaced by `validate_graph_reachability()`, a diagnostic-only check (agreement 1.0 and reachable rate 1.0 at every depth) that is not a capability score and is not plotted.

---

## Validity status of v1 benchmarks

| Benchmark | Status | Reason |
|---|---|---|
| 1 | Superseded | Metric cannot see direction |
| 2 | Reproduced | Reproduced on the corrected generator within 3 points |
| 3 | **Void** | Traversal side is a self-consistency check; see below |
| 4 | Sanity check only (traversal); baseline phrasing confounded | Traversal rediscovers sampled paths; baseline template is phrasing-weak |
| 5 | Reproduced | Reproduced on the corrected generator within 3 points |

### Week 7 corrections to the v1 benchmarks

1. **The question generator mis-directed questions.**
   `generate_questions()` and `_chain_phrase()` in `evaluation/benchmark.py`
   derived phrasing from raw relation strings independently of the verified
   `MANUAL_TEMPLATES`: two sources of truth for one fact, only one correct.
   `child_of`, `protector_of` and `leader_of` produced questions asking the
   opposite of their own ground truth ("Who is child of Will?" naturally asks
   for Will's child; the ground truth was Will's parent). Fixed with
   `relation_to_question()`, which wh-fronts the verified statement templates
   (with `direction="reverse"` for chains). Generation is now scoped to the 31 of
   48 relation types with a verified template; unverified relations return
   `None` and are skipped.
2. **`evaluate_nhop_graph()` is a self-consistency check.** Once question
   generation and traversal share the same direction-agnostic logic, the
   benchmark asks whether traversal finds paths it just generated using
   itself. It cannot measure retrieval capability. The historical 72% / 26%
   figures are therefore void, and any traversal column from v1 should be read
   the same way.
3. **The instrument could not see the real change.** The effect of
   direction-agnostic traversal was found with reachable-set-size and
   degree-distribution diagnostics, because the benchmark metric could not
   register it (a second instance of the Benchmark 1 lesson: naive metrics can
   miss a real improvement as well as a real problem).

---

## v2 correctness yardstick

**Purpose.** Measure whether the live pipeline returns the *right* answer to
structured multi-step questions, including whether it declines honestly when it
cannot. Lives in `scripts/diagnostics/` (`yardstick.py`; shared primitives are
meant to live in `common.py`, but several are still duplicated with different
signatures, see [Known issues](#known-issues)).

**Construction.** Seed 0; cap of 5 questions per step-sequence; 6 books
(Felix Holt as baseline, *Jungle Tales of Tarzan* as control, King Arthur, Sons
and Lovers, Decameron, Rhinegold); 6,181 questions at 2 hops in the original
population. Gold answers are composed from stored ARF edges through a
hand-verified `(relation, role)` step table, so the yardstick measures **fidelity
to the graph as stored, not real-world truth**.

**Outcomes.** `HIT` (the gold answer is among those returned), `DECLINED` (no
answer returned), and `WRONG` (an answer returned, none correct). Misses are
attributed to `RECALL` (first fact never retrieved) or `LOGIC`. **`WRONG` is the
headline metric**, because a confident wrong answer is worse than a decline.
`pure-HIT` counts counts HITs where every returned answer is in the gold set (precision 1.0), reported as a share of all questions. A single correct answer to a multi-answer question counts.

**Known caveats.**
- Relation-typed gold undercounts wherever ARF stores redundant edges
  (`parent_father_of` versus `child_of` for one fact).
- The role table is shared by the generator and any future extractor, so a wrong
  entry would be invisible to both. An independent, human-written tier of 20–30
  natural-phrasing questions with gold looked up directly in the graph is **not
  yet built**.
- `HIT` is lenient: it credits a question whose returned set merely contains the
  right answer. Purity (below) is what exposes this.
- Questions are generated in a small number of phrasing shapes, so results show
  generalization across vocabulary and book, not across unscripted phrasing.

### Run history (read carefully: populations and code differ)

| Run | Code under test | HIT | DECLINED | WRONG | Notes |
|---|---|---|---|---|---|
| Early baseline (original 6,181-question population) | Dual-expansion spike | 41.4% | 52.2% | 6.5% | **Do not quote the 6.5% as a baseline or floor**: it describes the dual-expansion spike, which was later reverted. |
| Paired single-expansion run ("10/1") | Single expansion | 44.5% | n/r | 11.8% | pure-HIT 10.3%, median answers per question 5 |
| Current code, no resolution maps (5,115 questions) | Single expansion | 38.0% | 48.6% | 13.4% | pure-HIT 22.3% of all questions, median answers 2 |

`n/r` means not recorded. Paired against the 10/1 run, single expansion is much
purer (pure-HIT 10.3% to 22.3%, median answers 5 to 2), modestly lower on raw
HIT (44.5% to 38.0%), and WRONG rose from 11.8% to 13.4%. An earlier reading
that "WRONG doubled" compared across run types and was withdrawn.

### Early-baseline detail (dual-expansion code; for the decomposition, not as a baseline)

- **Parse gates.** G1 (`hop_depth == 0`) covers 337 questions and G2
  (`target_relation is None`) covers 697. All 1,034 are DECLINED, which is 32%
  of all declines. G3 (`target_relation` wrong) is 0.
- **Parse-passed subset (5,147 questions):** HIT 49.7%, DECLINED 42.5%,
  WRONG 7.8%.
- **Same relation named twice (485 questions):** 4.7% HIT even among those that
  parse, against 44.5% for the rest. Hypothesized structural cause (a cycle or
  an over-aggressive visited-node exclusion), not confirmed.
- **Clean subset** (unique gold, all nameable, parse-passed, n = 1,719): HIT
  31.0%, WRONG 8.7%. Pure HIT is 126 of 1,719 (7.3%); 215 of 1,719 (12.5%) are
  HITs with at most two answers; the median answered question returns 8
  answers. Roughly 79.8% of HITs were impure.

### Findings from the early baseline

- The parse layer is a **bounded lever**: at most about +8 percentage points of
  HIT, before discounting for downstream failures. The larger loss is
  post-parse (42.5% of parse-passed questions are DECLINED).
- **Purity** is the larger, separate problem. Unioning answers across 5 vector
  hits and both expansion sides produced large impure answer sets, which is most
  of the gap between lenient HIT (41.4%) and pure HIT (7.3%).
- `anchor_retrieved` (about 96%) is nearly uninformative: a query naming the
  anchor almost always retrieves some pair containing it. The real requirement
  is retrieving the *specific first-step fact* among the 5 hits (hypothesis).
- G1 (337) being smaller than the same-relation group (485) is unexplained; one
  unverified guess is that `son` matching three relations inflates the distinct
  relation count and lets some questions escape the `hop_depth == 0` gate.
- `WRONG` is higher on unique-gold questions (7.4% versus 5.9%); this does not
  fire the pre-registered hub-skew trigger, which concerns answer degree.

**Pre-registered predictions versus observed** (predictions made before the run):

| Prediction | Result |
|---|---|
| G2 about 10–12% | Confirmed: 11.3% |
| G1 at most about 5% | Borderline: 5.5% (the arithmetic going in was off) |
| G3 under 2% | Confirmed: 0 |
| Parse gates under 40% of DECLINED | Confirmed: 32% |
| Asymmetric first step about 0% HIT | **Failed:** 47.9% (symmetric was lower, 35.1%) |
| Hub flooding drives DECLINED | Weak: 49.3% to 55.0% across anchor-degree quartiles |

The asymmetric-step prediction failed because the system was modeled as pure
anchor-rooted traversal. In the live path hop 1 comes from the vector-matched
pair, so the in-edge restriction only affects the second hop onward.

### Breakdown by terminal-step role

- On an early run's CSV, **symmetric-relation questions produced about 98% of
  hits**; questions ending in the entity1 role produced almost none; questions
  ending in the entity2 role were **100% declined**, with `target_relation`
  returning `None` for all of them. The explanation that `son` ties across three
  relations is **unconfirmed**.
- A later breakdown put **e1-ending questions at about 7% HIT against 23%
  WRONG.** This is consistent with `_terminal_answer` returning an
  already-reached node for non-symmetric terminal edges, but that mechanism is
  inferred from the pattern, not traced chain by chain.

### Pre-registered decision rule for the first-step metric

A `first_step_retrieved` metric was added to the diagnostics, and its decision
rule was set in advance: if HIT given the first step was retrieved exceeds HIT
given it was not by more than 40 percentage points, and the not-retrieved group
is at least 80% DECLINED, then the loss is first-fact recall, which justifies
anchor-rooted traversal and a relation-sequence extractor. If HIT stays low even
when the first step was retrieved, the loss is in traversal or the filters and
those are debugged first. No result is recorded. A live (gold-free) abstention
version is proposed but not designed, since the diagnostic version needs gold.

### Direction-detection generalization test

The single-expansion direction fixes were tested on 4 new books (King Arthur,
Sons and Lovers, Decameron, Rhinegold) plus the Felix Holt baseline and the
Tarzan control: 96.9–100% resolution, 0 new-family failures on all 6. **This
measured only that `expand_from is not None`, i.e. that detection fires, not
that the direction returned is correct.** The questions were script-generated in
the same two phrasing shapes the fixes were built against. A real-usage check on
a non-Felix-Holt book with unscripted phrasing has not been run.

### `is_nameable` A/B

Tightening `is_nameable` (delegating to `resolution.pronoun_filter.is_pronoun_generic`)
excludes **818** previously askable questions (uncapped, full 6-book
population), of which **301** were previously HIT. Those lost HITs were less
likely to be clean: **13.6% pure (41 of 301)** versus 24.8% pure corpus-wide.
Unique-gold rate was roughly equal (26.9% versus 27.2%) and median `gold_size`
tied at 3.0 (comparison script: `compare_is_nameable_change.py`). Conclusion: the tightening is a net-positive trade (it removed
proportionally more low-precision matches than clean ones, at a cost of 41
genuinely clean answers) and stands.

Two bugs in the comparison tooling had to be fixed before this could be trusted,
and an earlier "997 HITs lost" figure is invalid and superseded:
1. **RNG bug.** Seeding `rng.shuffle()` identically for two lists of different
   length does not give comparable permutations (Fisher-Yates' swap sequence
   depends on length). Fixed by removing randomness: deterministic sorted anchor
   order. An invalid `only_new = 1993` fell to 262.
2. **Order-dependent capping.** `generate()`'s per-sequence-label cap depends on
   iteration position, so which anchors consume a shared combo slot shifts when
   a filter excludes some anchors, and the tighter population stops being a
   strict subset. Fixed by removing the cap for this comparison (correct for
   diversity sampling, wrong for an exact A/B). `only_new = 0` validated the
   method.

---

## Resolution layer A/B

The yardstick adapter had never passed `resolution_maps`, so the Week 8
resolution layer had been measured only by diagnostic scripts and never scored
end to end. An A/B edit now runs both arms on identical questions, with a
canonicalized scoring mode so an answer redirected to a canonical name is not
marked wrong against raw gold names. Measured on the traversal code *before*
the endpoint-gate removal:

| Arm | HIT | DECLINED | WRONG |
|---|---|---|---|
| No maps | 38.0% | 48.6% | 13.4% |
| Maps, strict scoring | 29.1% | 46.5% | 24.4% |
| Maps, canonicalized scoring | 34.2% | 46.5% | 19.3% |

**With the resolution layer on, HIT falls and WRONG rises, even under lenient
scoring.** Two effects were diagnosed:

- **Newly wrong e1 answers.** Of the 118 newly wrong e1 answers, 83.9% sit in the
  anchor's own first-step frontier, and 98.3% had the first step retrieved. This
  fits `_terminal_answer` returning an already-reached node, but the mechanism is
  inferred, not traced chain by chain.
- **Tier exclusion removes real answers.** Of 470 correct nodes in questions the
  maps arm lost, 395 were in the ambiguous tier.

The later traversal change (endpoint gate removed) passes tests and is **unmeasured**.
The accurate status is therefore: the layer is wired in, it measured negative on
the yardstick, and the fix is unmeasured. It is not complete.

**Diagnostics versus end to end.** These results coexist with an improvement on
the frontier-contamination diagnostic (79.7% of contaminated frontiers
resolved (This measure drops pronoun/generic and ambiguous-tier entries from each frontier, so "resolved to at most one answer" counts removing real names as success. That is the same removal that cost 395 of 470 correct nodes on the yardstick. Frontiers reduced to zero answers were not counted separately), 40 of 286 unchanged; see [`v2-entity-resolution-findings.md`](v2-entity-resolution-findings.md)). A diagnostic improving while the end-to-end score worsens is the reason a week is not closed on diagnostics alone.

---

## Methodology rules

- **Pair comparisons by question ID and by run type.** An unpaired comparison of
  two runs with different question populations (929 fewer questions after a
  purity filter) reported a 5.8-point gendered-HIT regression and a 54%
  RECALL-miss jump. Paired on the same question IDs, gendered HIT was 27.2% to
  26.3% and RECALL 7.5% to 7.7%: noise. Comparisons across run types (dual versus
  single expansion) are likewise invalid.
- **A comparison must pass a subset-validity check** before its result is read
  (`only_new` must be 0 when one population is a strict subset of the other).
- **State what a "verified" claim verified.** The length-based pair-exclusion
  fix was recorded as verified against three cases; it was only structurally
  verified, and the direction follows from the `protector_of` template: `squire -protector_of-> lord` means squire protects lord, so the four `lord` tests expect the answer to "who does squire protect", not "who protects squire". With the edge flipped (`lord -protector_of-> squire`), no chain reaches lord (checked), because traversal does not follow non-symmetric in-edges.
- **No week closes on diagnostics or unit tests alone.** A real-usage check
  against unscripted queries is required. See
  [`lessons-learned.md`](lessons-learned.md).
- **Hub-skew revisit trigger (pre-registered).** Compare direction-aware accuracy
  for questions whose correct answer is a low-degree node against those whose
  answer is a hub. A meaningful gap disfavoring low-degree answers is the
  trigger; any degree cap must be validated against that split, not against its
  own degree-distribution output.

---

## Reproducing

```bash
python -m scripts.run_benchmarks
```

Four timestamped runs are committed under `results/` (`20260824_112258`,
`20260911_135325`, `20260912_010212`, `20260912_131729`), each with
`benchmark_results.json` and plots. Re-run the v1 benchmarks before and after any
retrieval change to catch regressions, remembering the validity table above.
Diagnostic and yardstick scripts are in `scripts/diagnostics/`; one-off scripts
are archived in `scripts/diagnostics/archive/`.

### Known issues

- `yardstick.py` and `common.py` both define `build_index`, `step`, `walk` and
  the retrieval adapter (`make_hybrid_adapter`), with different signatures. The duplication broke
  `compare_nameable.py` (its `walk` call) and is unresolved. It is the same
  two-sources-of-truth failure seen elsewhere in the project.
- The proposed fixes for `compare_nameable.py` and for a `USE_RESOLUTION`
  toggle in `api/main.py` have an unconfirmed application status.
- The yardstick's independent human-written question tier does not exist yet.
