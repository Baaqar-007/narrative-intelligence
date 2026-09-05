# NIE v2 — Phase 1 Research Summary (Weeks 1–4)

> Synthesized reference covering the GraphRAG-adjacent literature and the
> entity-resolution research thread reviewed during Phase 1.
> This document captures what each
> source implies for this project's design decisions, rather than
> restating each paper.

**Status legend**: ✅ read in full · 🔶 read via secondhand summary
(not independently verified against source) · 📋 decision or proposal
pending sign-off.

---

## Document structure

- **Design implications** subsections carry the load-bearing content
  and are the fastest path back into this material after a gap.
- **Open decisions** are collected at the end of each week and again in
  a consolidated list at the close of the document — nothing here
  should be treated as settled until those are resolved.
- Paper identity was verified against the source PDF for every entry
  below rather than assumed from filename or citation. Two mismatches
  were caught this way (Weeks 1 and 3) and are called out explicitly,
  since they affect what each source can and cannot support.

---

## Week 1 — Graph RAG landscape ✅

**Source**: *Graph Retrieval-Augmented Generation: A Survey*, Peng et
al. 2024, arXiv:2408.08921 (41 pages, read in full).

**Identity note**: this is a broad survey of the GraphRAG methodology
space, not Edge et al.'s original Microsoft GraphRAG paper (the
citation `research_notes.md` originally pointed to). Edge et al.'s
method is described concretely within the survey's indexing,
generation, and industry sections, which provides sufficient secondhand
grounding — the original paper was not independently read.

**What validates v1's existing design** (no adoption needed — v1
already implements this):
- NetworkX graph + templated-sentence embeddings + ChromaDB matches the
  survey's "Hybrid Indexing" pattern — the field's practical default,
  not a project-specific improvisation.
- `relation_to_sentence()`'s templating corresponds to the survey's
  "Natural Language" graph-format category, the most common choice in
  the field.
- `hybrid_search()`'s single-pass design matches "Once Retrieval," a
  documented latency/accuracy tradeoff rather than an omission.

**What does not transfer, and why**:
- Community-summary infrastructure (Edge et al.'s core mechanism)
  addresses Query-Focused Summarization — "what are this corpus's
  themes." NIE queries have a small, localized evidence set; there is
  no QFS-shaped question in this project. This is a confirmed non-fit,
  not a deferred maybe.
- LLM-based graph construction, used by every industrial system
  surveyed (Microsoft, NebulaGraph, AntGroup, Neo4j), conflicts
  directly with the project's dataset-first constraint — a deliberate
  minority choice, not an oversight.

**Most significant finding for the v2 roadmap**: Section 10.1 states
that nearly all GraphRAG methods assume a static graph, and names
dynamic/adaptive graph updating as a largely unexplored open direction
with no citations of a solved approach. **v2 Phase 3 (simulating
node/event removal and re-traversal) sits directly in this gap** —
there is no existing recipe to adapt, and the design work is closer to
original graph-algorithms work than an application of a known pattern.

**Design input for Week 7 (live multi-hop wiring)**: implement as
non-parametric, fixed-depth, single-pass retrieval — wire the existing,
benchmarked BFS traversal directly in rather than an LLM-agent
iterative loop. This has precedent in the field (Wang et al., GNN-RAG),
not just as a complexity-avoidance default.

---

## Week 2 — CatRAG (Static Graph Fallacy) ✅

**Source**: *Breaking the Static Graph: Context-Aware Traversal for
Robust RAG*, Lau et al., arXiv:2602.01965, Feb 2026 (13 pages, read in
full). Identity confirmed against project notes — no mismatch found.

**Summary**: builds on HippoRAG 2's Personalized PageRank (PPR)
retrieval. The paper's "Static Graph Fallacy": PPR transition weights
are fixed at index time and don't discriminate by query, so probability
mass diffuses into high-degree "hub" nodes — producing high partial
recall but broken multi-hop evidence chains. The proposed fix is
LLM-scored dynamic edge reweighting per query, combined with weak-entity-
anchor seeding and a non-LLM key-fact passage boost.

**Applicability differs across two parts of v2**:

- **Week 7 (live multi-hop)**: does not transfer directly. CatRAG's
  failure mode is a *recall* loss — PPR is stochastic, and probability
  mass genuinely gets lost to hub nodes. NIE's `graph_n_hop_search` is
  exhaustive BFS and deterministic; a hub node cannot cause it to miss
  results within the hop radius. A related but distinct risk is worth
  monitoring once Week 7 ships: hub entities flooding the neighborhood
  with irrelevant results is a *precision* problem, not this recall
  problem, and isn't worth addressing before it's measured.
- **Phase 3 (simulation traversal)** — the genuine finding: does not
  transfer, and this is a real negative result rather than a stretch.
  CatRAG addresses graphs that are static *across queries* (fixed
  topology, query-adaptive weights). v2's simulation requires graphs
  that are static *across scenarios* — topology itself changes via real
  node removal, and exact reachability/centrality is recomputed with no
  stochastic weighting anywhere in that step. These are orthogonal
  problems. CatRAG's fix mechanism (an LLM scoring edges to decide
  traversal weighting) is also exactly what Design Principle 3 already
  rules out for simulation, independent of whether the broader framing
  applies.

**What does transfer**: CatRAG's **Full Chain Retrieval (FCR)** and
**Joint Success Rate (JSR)** metrics — whether retrieval returned the
*entire* gold evidence chain, not just an overlapping subset — are the
multi-hop generalization of the exact lesson v1's own Benchmark 1→2
evolution found independently. This is concrete input for Phase 3's
Week 12 evaluation design, where no ARF-style ground truth exists.

**Secondary confirmation**: CatRAG explicitly rejects iterative/agentic
retrieval on latency grounds, independently reinforcing the same "once
retrieval, fixed-depth" conclusion as the Week 1 survey — two unrelated
sources, same conclusion.

**Status**: keep loaded. Role narrows from "traversal design input" to
"evaluation-metric input plus a documented non-transfer finding."

---

## Week 3 — Entity resolution: three facets

The unresolved v1 limitation (README, Known Limitations #1–2) is
actually three distinct sub-problems, kept deliberately separate until
Week 4 unifies them.

### Facet 1 — Alias/nickname resolution ✅

**Source**: Amalvy & Labatut, *Annotation Guidelines for Corpus
Novelties: Part 2 – Alias Resolution*, arXiv:2410.00522 (14 pages, read
in full).

**Correction**: this is a set of human annotation guidelines for
building a gold corpus, not an automated clustering algorithm — an
earlier project note described a method that isn't actually present in
the document.

**Value**: a taxonomy of hard cases rather than a method. It confirms,
with concrete examples, why v1's `difflib` fuzzy-match failed
structurally rather than just numerically — true aliases can share
**zero string overlap** (`Milady` → `Anne de Breuil`; `D'Artagnan` →
`Charles de Batz de Castelmore, dit d'Artagnan`). It splits "alias
resolution" into two real tiers: surface variants (mechanically
tractable — honorific-stripping, name-part matching) versus true
aliases (not mechanically solvable without external knowledge or
narrative context).

### Facet 2 — Coreference resolution ✅

**Source**: Martinelli, Bonomo et al., *BOOKCOREF: Coreference
Resolution at Book Scale*, arXiv:2507.12075, July 2025 (19 pages, read
in full).

**Correction**: an earlier project note understated the finding as
"specialized resources solve it." The actual reported numbers:
off-the-shelf models score 40–51 CoNLL-F1 at book scale (versus ~80+ on
standard benchmarks); even the best specialized systems, fine-tuned on
book-scale data, reach only 61–67. The gap never fully closes — this is
a genuinely open problem by the paper's own account.

**Reusable pipeline shape**: a precision-first, recall-later funnel —
link explicit named mentions first (high precision), verify, then
expand to pronouns/generic phrases via windowed-then-grouped
coreference passes. This matches CatRAG's coarse-to-fine pruning
(Week 2), suggesting a recurring pattern wherever false positives are
expensive downstream and false negatives are cheap to recover later.

**Implications for Week 8**: ARF's 5-sentence chunking is the wrong
granularity for this task by the paper's own diagnosis — antecedents
several chunks back cannot resolve under a per-chunk pass. Separately,
this paper's PER-only annotation scope independently matches v1's own
PER-only scoping decision, a second point of convergence.

### Facet 3 — Generic/collective entities 🔶

**Source**: Bhattacharya & Getoor, *Collective Entity Resolution in
Relational Data*. Not independently re-read for this summary; analyzed
from an internally maintained summary of the source, since the source
PDF is not currently in the project's reference set. Confidence is
lower here than for the other two facets accordingly.

**What it describes**: disambiguating individual identity (for
example, whether "W. Wang" in two papers is the same person) using
relational co-occurrence — such as coauthorship — rather than string
similarity alone, resolved collectively rather than pair-by-pair.

**Scope mismatch**: this method resolves *individual* identity, where
exactly one true referent always exists to converge on. NIE's actual
problem (`"apes"` vs. `"the apes"` vs. `"young apes"`) may have no
single true referent at all — these may denote different narrative
subsets rather than one entity under different names. The underlying
*mechanism* (relational-neighborhood overlap as evidence) may still be
useful; the *semantics* of what counts as a correct merge do not carry
over, and the source paper's own framework does not resolve that gap.

### Cross-facet finding: LLM-for-identity tension

Three independent sources reviewed this week — Vrittanta-EN's event
extraction, Amalvy & Labatut's note on generative models for historical
lookups, and BookCoref's LLM-based mention verification — each reach
for an LLM to verify identity over entities *already extracted*, rather
than to extract new relations. This pattern recurring three times
independently suggests it warrants one explicit project-wide decision
(Week 4) rather than three separate ad hoc calls.

---

## Week 4 — Unified entity resolution proposal 📋

**Why one design rather than three patches**: the facets are not
independent. Coreference resolution needs alias merging done first, or
pronouns resolve to fragmented, pre-merge name variants. Generic/
collective resolution cannot reuse the alias/coref "merge into one
node" logic at all, since Week 3 established that there is often no
single ground-truth referent to merge toward.

### Recommended architecture: non-destructive resolution layer

This follows a pattern v1 already uses twice — `relation_ontology.py`'s
opt-in `is_canonical_relation()` filter, and the embedding dedup step —
neither of which touches the raw graph. Entity resolution should follow
the same shape: the existing `(book_id, normalized_entity_name)` graph
stays exactly as built, and a new `resolution/` module holds a
`resolution_map` (raw name → resolved ID, tagged with tier and
confidence) that retrieval opts into before graph lookup. Under this
design, a bad resolution decision becomes a metadata edit rather than a
graph-corrupting one.

### Three-stage funnel, in dependency order

1. **Stage A — Extended mechanical alias resolution.** Extends Week 1's
   appositive-stripping with honorific/name-part rules drawn from the
   Amalvy & Labatut taxonomy. Deterministic, no new dependencies. Runs
   first, since everything downstream needs a stable name list.
2. **Stage B — Coreference expansion.** ARF already emits raw
   pronoun/descriptor entity strings (confirmed via the README's
   Benchmark 3 "his brother" caveat). Requires book-level,
   windowed-then-grouped context per BookCoref's pattern rather than
   chunk-level processing, and a new coreference-model dependency
   (flagged below). Output is stored with a confidence tier and never
   silently merged as ground truth.
3. **Stage C — Hard aliases and generic/collective entities, not
   auto-merged.** Hard aliases are flagged as `flagged_candidate` via
   relational-neighborhood overlap and never auto-merged.
   Generic/collective entities are **reframed as a missing *relation*
   problem rather than a resolution problem** — represented as
   `"young apes" —instance_of→ "apes"`, an edge rather than a node
   merge. This sidesteps the "what counts as correct" question
   entirely. This is a firm line rather than a gray area: the edge may
   only be produced by a mechanical heuristic (shared head noun or
   substring); an LLM-inferred relation here would constitute new
   relation extraction, which runs against Design Principle 2.

### Evaluation — a genuine gap, not an oversight

ARF has no ground truth for entity resolution, unlike relations.
Recommended order: **extrinsic evaluation first** — re-run v1's
existing Benchmark 2/3 pipeline before and after resolution and check
whether accuracy moves (no additional cost, reuses existing
infrastructure). Fall back to small-scale manual annotation (a
scaled-down Amalvy & Labatut / BookCoref style) only if the extrinsic
signal proves too noisy to read.

**Scope note**: PER-type entities remain the primary target, matching
v1's own PER-only scoping; other entity types are deferred pending a
measured need.

---

## Cross-cutting patterns across independent sources

These weren't designed for comparison — they surfaced from reading
unrelated papers in sequence, which is what makes the convergence worth
recording:

- **Precision-first, recall-later funnels** — CatRAG's coarse-to-fine
  edge pruning and BookCoref's link-then-expand pipeline share this
  shape, which recurs wherever false positives are expensive downstream
  and false negatives are cheap to recover later.
- **"Once retrieval" over iterative/agentic retrieval** — argued for
  independently by both the GraphRAG survey (§6.2.4's tradeoff
  analysis) and CatRAG (explicit latency-based rejection of iterative
  refinement).
- **Static graphs as an open problem, not a solved one** — the
  GraphRAG survey names this directly (§10.1); CatRAG is the only
  source engaging with a version of it, but along a different axis
  (query-time weighting rather than scenario-time topology change).
- **LLM-for-identity-verification, not extraction** — three independent
  entity-resolution sources reach for this same pattern, which is
  consistent enough to warrant one project-wide decision (Week 4)
  rather than three separate calls.

---

