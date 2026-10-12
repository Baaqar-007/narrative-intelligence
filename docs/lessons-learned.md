# Lessons Learned

Methodology lessons from building NIE, each tied to the specific evidence that
produced it. These are recorded because most of them were learned more than once.

Contents: [Evidence and claims](#evidence-and-claims) ·
[Measurement](#measurement) · [Debugging](#debugging) ·
[Code and documentation hygiene](#code-and-documentation-hygiene) ·
[Scope and sequencing](#scope-and-sequencing)

---

## Evidence and claims

### Passing tests is not completion

Week 7 shipped with 93 passing tests and then failed on 11 of 11 real
multi-hop questions. The tests used synthetic graphs and questions from the
project's own generators; the detector was validated against the phrasing those
generators produce. **A real-usage audit against unscripted queries is required
before any build week is closed.** The same pattern recurred later: the Week 8
resolution layer improved its diagnostic (79.7% of contaminated frontiers
resolved) while lowering end-to-end accuracy (HIT 38.0% to 29.1%). See
[`v2-retrieval-findings.md`](v2-retrieval-findings.md#week-7--real-usage-audit)
and [`benchmarks.md`](benchmarks.md#resolution-layer-ab).

### Do not test a system against its own output

The benchmark and the direction detector were tested against each other's
phrasing, never independent human phrasing. A self-consistency benchmark
(`evaluate_nhop_graph`) asks whether traversal finds paths it just generated with
the same logic, so it cannot measure capability; the v1 multi-hop figures were
voided for this reason. Benchmark 1's metric had the same shape in miniature: it
could not see the improvement it was meant to detect.

### State what a "verified" claim verified

Three claims were later narrowed. "96.9–100% generalizes" measured only that
detection returned a non-`None` value. "Verified against three cases" meant the
structure was checked, not that three cases were run (The direction follows from the `protector_of` template: `squire -protector_of-> lord` means squire protects lord, so the four `lord` tests expect the answer to
"who does squire protect", not "who protects squire". With the edge flipped (`lord -protector_of-> squire`), no chain reaches lord (checked), because traversal does not follow non-symmetric in-edges). A reclassification of
the Mrs. Transome failure as pure source noise was incomplete. Write what was
checked, not just that checking occurred. See
[`v2-decisions.md`](v2-decisions.md#documentation-corrections-decision-56).

### Measure before mitigating, and decide the trigger first

Hub skew in recovered nodes was measured but never shown harmful, because
degree-distribution skew and retrieval-quality harm are different claims. A
revisit trigger was pre-registered (an accuracy split by answer degree) before
any mitigation was built. Pre-registered predictions also caught a wrong model of
the system: the asymmetric-first-step prediction failed (47.9% versus about 0%)
because hop 1 comes from the vector-matched pair, not from traversal.

### Scope claims to what the data supports

Direction-agnostic traversal was first applied to all 48 relations, then scoped to
the seven confirmed symmetric ones. The "event-shaped relations are always person
to person" claim was checked against all 33 rows and failed by relation type.
Neither fix would have been found by reasoning alone.

---

## Measurement

### Pair comparisons and validate the comparison

An unpaired comparison of two runs with different question populations reported a
5.8-point regression and a 54% RECALL jump; paired on the same question IDs, both
were noise. A valid comparison of a filtered population against its parent must
have `only_new = 0`; the first `is_nameable` comparison returned 1,993, which
exposed two bugs in the comparison itself (an RNG shuffle that cannot give
comparable permutations across lists of different length, and an order-dependent
cap).

### Measurement tooling needs the same rigor as the code it measures

The tooling bugs cost more iterations than the research question they were meant
to answer, in consecutive sessions. Diagnostic scripts were consolidated into
shared modules; residual duplication (`yardstick.py` against `common.py`) still
broke a script and remains open.

### Prefer a diagnostic that can fail

The event audit, the frontier audit and the generalization test each had a
pre-stated way to come out against the working hypothesis. Several did (the
sequencing rationale shifted from 58%/9% to 47.1%/19.6% at full scale; the
"always PER to PER" claim fell by relation type).

---

## Debugging

### Verify the premise before reasoning from it

The Mrs. Transome failure was chased through six rounds of careful reasoning about
a synthetic fixture before a five-line, read-only query checked whether the
fixture matched the real graph. The reasoning was sound; the premise was
unchecked. Check the foundation first, then reason.

### Isolate before tracing

Six rounds of tracing through the live pipeline failed to find a bug that a
standalone unit test against a minimal synthetic graph found in two iterations.
Reach for isolation first when live tracing stalls.

### When a traced-correct fix still fails a test, check the test

A failing test turned out to have three inconsistent inputs of its own (fixture
metadata said `friend_of`, the query said "companion", the graph held
`companion_of`). The code under test was never wrong.

### Work from the live file, not a remembered version

Several rounds were lost to scripts written against a remembered, not current,
version of a function whose signature had since changed. Read the real file
before writing code that calls it.

### Silent failures are the most expensive

- Raw entity names in embedding metadata versus canonical names in the graph
  returned empty results with no error.
- `LingMessCoref` returned an empty list rather than failing on over-long input.
- `entity_to_expand_from` silently defaulted to `entity2`.
- `chunk_id` loaded as a string and sorted lexicographically, producing a
  plausible but wrong range.
- A dict-insertion-order tie-break returned a confidently wrong relation.

The shared remedy is to fail loudly (return `None`, raise, or decline), and to
check for the empty result explicitly.

---

## Code and documentation hygiene

### One fact, one source of truth

The same defect appeared at least six times: `mentioned_relations` (extracted
after two consumers drifted), `NOUN_SYNONYMS` against the role table,
`is_nameable` against `is_pronoun_generic`, the question generator against the
verified templates, the inline chain filter (now `select_chains`), and the
yardstick against `common.py`. Extract the shared function the first time two
consumers need the same fact, and delegate rather than resync.

### Documentation drifts from code

A decision log listed two fixes as unstarted that already existed in code, and a
fresh status note repeatedly flagged corrections that had already been made on a
stale copy. When a record and the code disagree, check the code, then correct the
record and say so.

### Verify paper identity and what was read

Two cited papers were not what the project notes said they were (a survey cited
as the original method paper; annotation guidelines cited as an algorithm), and
one result was understated ("specialized resources solve it" versus models topping
out at 61–67 F1). Check identity against the document, and record whether a
source was read in full or only summarized.

---

## Scope and sequencing

### Do not chase an asymptote

Stage A (surface-variant merging) went through five rounds, each fixing the case
that motivated it, while the underlying class (identity that depends on narrative
discourse) was not solvable by token overlap. It was frozen at its measured
ceiling. The dual-expansion spike was likewise stopped after five iterations
with one new bug per fix. A pattern of one-fix-one-new-bug is itself the signal.

### Sequence by quantified payoff, then re-check at scale

The first measurement put pronoun/generic noise at 58% and surface variants at
9%; at full scale it was 47.1% and 19.6%. The ordering survived, but the expected
payoff of the second stage roughly doubled. Re-measure at scale before treating a
pilot's ratios as settled.

### Honest negative results are results

Benchmark 1's tie, the dual-expansion spike, the CatRAG non-transfer, the event
dataset being unusable, and the resolution layer lowering yardstick accuracy are
all recorded as findings, with the evidence, not discarded or smoothed.
