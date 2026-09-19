# NIE v2 — Phase 1 Research Summary (Weeks 1–5)

> Compiled reference covering GraphRAG-adjacent literature and the
> entity-resolution research thread. This document is the
> synthesized, cross-referenced version — what each source means for
> *this* project's decisions, not a restatement of each paper.
>
> Status markers: ✅ read in full · 🔶 read via secondhand summary
> (not independently verified from source) · 📋 decision/proposal
> pending sign-off.

---

## How to use this document

- **Design implications** sections are the load-bearing content and
  the fastest path back into this material after a gap.
- **Open decisions** are collected at the end — nothing here should
  be treated as settled until those are resolved.
- Paper identity was independently checked against the actual PDF for
  every source below (not assumed from filename/citation) — two
  mismatches were caught this way (Week 1, Week 3) and are noted
  explicitly where relevant, since they change what the source can
  and can't be used for.

---

## Week 1 — Graph RAG landscape ✅

**Source**: *Graph Retrieval-Augmented Generation: A Survey*, Peng et
al. 2024, arXiv:2408.08921 (41 pages, read in full).

**Identity note**: this is a broad survey of the GraphRAG methodology
space, *not* Edge et al.'s original Microsoft GraphRAG paper (which
`research_notes.md` originally pointed to). Edge et al.'s method is
described concretely within this survey (indexing, generation, and
industry sections) — sufficient secondhand grounding; the original
wasn't independently read.

**What validates v1's existing design** (no adoption needed — v1
already does this):
- NetworkX graph + templated-sentence embeddings + ChromaDB = the
  survey's "Hybrid Indexing" pattern — the field's practical default,
  not a project-specific improvisation.
- `relation_to_sentence()`'s templating = the survey's "Natural
  Language" graph-format category — the most common choice in the
  field.
- `hybrid_search()`'s single-pass design = "Once Retrieval" — a
  documented latency/accuracy tradeoff, not an omission.

**What does *not* transfer, and why**:
- Community-summary infrastructure (Edge et al.'s core mechanism)
  solves Query-Focused Summarization — "what are this corpus's
  themes." Every NIE query has a small, localized evidence set; there
  is no QFS-shaped question in this project. Confirmed no, not
  deferred maybe.
- LLM-based graph construction, used by every industrial system
  surveyed (Microsoft, NebulaGraph, AntGroup, Neo4j), conflicts
  directly with dataset-first — a deliberate minority choice, not an
  oversight.

**Most important finding for the whole v2 roadmap**: §10.1 states
nearly all GraphRAG methods assume a static graph; dynamic/adaptive
graph updating is named as a barely-explored open direction, with no
citations of a solved approach. **v2's Phase 3 (simulate node/event
removal, re-traverse) sits exactly in this gap** — there's no existing
recipe to adapt; the design work is closer to original graph-algorithms
work than "apply pattern X."

**Design input for Week 7 (live multi-hop wiring)**: implement as
non-parametric, fixed-depth, once retrieval — wire the existing
benchmarked BFS traversal directly in, not an LLM-agent iterative
loop. Real precedent for this in the field (Wang et al., GNN-RAG), not
just a complexity-avoidance default.

---

## Week 2 — CatRAG (Static Graph Fallacy) ✅

**Source**: *Breaking the Static Graph: Context-Aware Traversal for
Robust RAG*, Lau et al., arXiv:2602.01965, Feb 2026 (13 pages, read in
full). Identity confirmed against project notes — no mismatch.

**What it is**: builds on HippoRAG 2's Personalized PageRank (PPR)
retrieval. The "Static Graph Fallacy": PPR transition weights are
fixed at index time and don't discriminate by query, so probability
mass diffuses into high-degree "hub" nodes — high partial recall, but
broken multi-hop evidence chains. Fix: LLM-scored dynamic edge
reweighting per query, on top of weak-entity-anchor seeding and a
non-LLM key-fact passage boost.

**Does the critique transfer? Two different answers for two different
parts of v2**:

- **Week 7 (live multi-hop)**: not directly. CatRAG's failure is a
  *recall* loss — PPR is stochastic, probability mass genuinely gets
  lost to hubs. NIE's `graph_n_hop_search` is exhaustive BFS —
  deterministic; a hub node can't cause it to miss anything within the
  hop radius. A related but different risk is worth watching once
  Week 7 ships: hub entities flooding the neighborhood with irrelevant
  results is a *precision* problem, not this recall problem — not
  worth solving before it's measured.
- **Phase 3 (simulation traversal) — this is the genuine finding**:
  does not transfer, and it's a real negative result, not a stretch.
  CatRAG addresses graphs static *across queries* (fixed topology,
  query-adaptive weights). v2's simulation needs graphs static *across
  scenarios* (topology itself changes via real node removal, then
  exact reachability/centrality is recomputed — no stochastic
  weighting anywhere in that step). Orthogonal problems. CatRAG's
  actual fix mechanism (an LLM scoring edges to decide traversal
  weighting) is also exactly what Design Principle 3 already forbids
  for simulation, independent of whether the framing resonates.

**What genuinely transfers**: CatRAG's **Full Chain Retrieval (FCR)**
and **Joint Success Rate (JSR)** metrics — did retrieval return the
*entire* gold evidence chain, not just an overlapping subset — are the
multi-hop generalization of the exact lesson v1's own Benchmark 1→2
evolution already found independently. Concrete input for Phase 3's
Week 12 evaluation design, where no ARF-style ground truth exists.

**Secondary confirmation**: CatRAG explicitly rejects iterative/agentic
retrieval for latency reasons, independently reinforcing the same
"once retrieval, fixed-depth" call as Week 1's survey reading — two
unrelated papers, same conclusion.

**Status**: keep loaded. Role narrows from "traversal design input" to
"evaluation-metric input + a documented non-transfer finding."

---

## Week 3 — Entity Resolution: three facets

The unresolved v1 limitation (README, Known Limitation #1–2) is really
three distinct sub-problems the roadmap deliberately keeps separate
until Week 4 unifies them.

### Facet 1 — Alias/nickname resolution ✅

**Source**: Amalvy & Labatut, *Annotation Guidelines for Corpus
Novelties: Part 2 – Alias Resolution*, arXiv:2410.00522 (14 pages,
read in full).

**Correction**: this is human annotation guidelines for building a
gold corpus, not an automated clustering algorithm — an earlier
project note described a method that isn't actually present in the
document.

**Value**: a taxonomy of hard cases, not a method. Confirms with
concrete examples why v1's `difflib` fuzzy-match failed structurally,
not just numerically — true aliases can share **zero string overlap**
(`Milady` → `Anne de Breuil`; `D'Artagnan` → `Charles de Batz de
Castelmore, dit d'Artagnan`). Splits "alias resolution" into two real
tiers: surface variants (mechanically tractable — honorific-stripping,
name-part matching) vs. true aliases (not mechanically solvable at all
without external knowledge or narrative context).

### Facet 2 — Coreference resolution ✅

**Source**: Martinelli, Bonomo et al., *BOOKCOREF: Coreference
Resolution at Book Scale*, arXiv:2507.12075, July 2025 (19 pages, read
in full).

**Correction**: an earlier project note understated the finding as
"specialized resources solve it." Actual numbers: off-the-shelf models
score
40–51 CoNLL-F1 at book scale (vs. ~80+ on standard benchmarks); even
the best specialized systems, fine-tuned on book-scale data, only
reach 61–67 — the gap never fully closes. Genuinely open problem, by
the paper's own admission.

**Pipeline shape (the reusable part)**: precision-first, recall-later
funnel — link explicit named mentions first (high precision), verify,
*then* expand to pronouns/generic phrases via windowed-then-grouped
coreference passes. Same shape as CatRAG's coarse-to-fine pruning
(Week 2) — a recurring pattern wherever false positives are expensive
downstream and false negatives are cheap to recover later.

**Concrete implications for Week 8**: ARF's 5-sentence chunking is the
wrong granularity for this by the paper's own diagnosis — antecedents
several chunks back can't resolve under a per-chunk pass. Also: this
paper's PER-only annotation scope independently matches v1's own
"PER-only scoping" decision — a second point of convergence.

### Facet 3 — Generic/collective entities 🔶

**Source**: Bhattacharya, collective relational entity resolution.
Not independently read for this summary; analyzed from an internally
maintained summary of the source, since the PDF is not currently in
the project's reference set. Lower confidence than the other two
facets accordingly.

**What it describes**: disambiguating individual identity (e.g., is
`"W. Wang"` in two papers the same person?) using relational
co-occurrence (coauthorship) rather than string similarity alone,
resolved collectively rather than pair-by-pair.

**Scope-mismatch flag**: this resolves *individual* identity — there
is always exactly one true referent to converge on. NIE's actual
problem (`"apes"` vs `"the apes"` vs `"young apes"`) may have no single
true referent at all — different narrative subsets, not one entity
under different names. The *mechanism* (relational-neighborhood
overlap as evidence) may still transfer; the *semantics* of "correct
merge" don't, and the paper's own framework doesn't resolve that gap.

### Cross-facet finding: the recurring LLM-for-identity tension

Three independent sources this week (Vrittanta-EN's event extraction,
Amalvy & Labatut's note on generative models for historical lookups,
BookCoref's LLM-based mention verification) each reach for an LLM to
verify identity over entities *already extracted*, not to extract new
relations. This recurrence across unrelated sources suggests it
warrants one explicit project-wide decision (Week 4), rather than
three separate ad hoc calls.

---

## Week 4 — Unified Entity Resolution Proposal 📋

**Why one design, not three patches**: the facets aren't independent.
Coreference resolution needs alias merging done *first*, or pronouns
resolve to fragmented pre-merge name variants. Generic/collective
resolution can't reuse the alias/coref "merge into one node" logic at
all, because Week 3 established there's often no single ground-truth
referent to merge toward.

### Recommended architecture: non-destructive resolution layer

Same pattern v1 already used twice — `relation_ontology.py`'s opt-in
`is_canonical_relation()` filter, and the embedding dedup step —
neither touches the raw graph. Entity resolution should match: the
existing `(book_id, normalized_entity_name)` graph stays exactly as
built; a new `resolution/` module holds a `resolution_map` (raw name →
resolved ID, tagged with tier and confidence) that retrieval opts into
before graph lookup. A bad resolution decision becomes a metadata
edit, not a graph-corrupting one.

### Three-stage funnel, in dependency order

1. **Stage A — Extended mechanical alias resolution.** Extend Week 1's
   appositive-stripping with honorific/name-part rules from the Amalvy
   & Labatut taxonomy. Deterministic, no new dependencies. Runs first
   — everything downstream needs a stable name list.
2. **Stage B — Coreference expansion.** ARF already emits raw
   pronoun/descriptor entity strings (confirmed: README's Benchmark 3
   "his brother" caveat). Needs book-level, windowed-then-grouped
   context per BookCoref's pattern, not chunk-level. Requires a new
   coreference-model dependency (flagged below). Output stored with a
   confidence tier, never silently merged as ground truth.
3. **Stage C — Hard aliases and generic/collective entities —
   deliberately not auto-merged.** Hard aliases: flag as
   `flagged_candidate` via relational-neighborhood overlap, never
   auto-merged. Generic/collective entities: **reframed as a missing
   *relation* problem, not a resolution problem** — represent
   `"young apes" —instance_of→ "apes"` as an edge, not a node merge.
   Sidesteps the "what does correct even mean" question entirely. Hard
   line, not a gray area: this edge can only come from a mechanical
   heuristic (shared head noun/substring) — LLM-inferred relations here
   would be new relation extraction, squarely against Principle 2.

### Decisions — resolved (2026-09-05)

1. **LLM-for-identity-verification boundary**: **approved, scoped
   narrowly.** LLM may act only as a bounded verifier over existing
   candidate entities (Stage B mention-linking checks, Stage C hard-alias
   candidate confirmation) — never to create new entities or relations.
   Stage C's generic/collective `instance_of` edges remain
   mechanical-heuristic-only regardless (this was already a hard line,
   not a gray area — now doubly confirmed, not loosened by decision 1).
2. **Coreference dependency approach**: **approved as off-the-shelf,
   not fine-tuned.** Use a pretrained coreference model as-is; do not
   fine-tune or build one in-house unless a later evaluation
   (Benchmark 2/3 regression check, per the evaluation plan above)
   shows it's actually necessary. Specific model still unselected —
   to be picked once a feasibility smoke-test against real ARF text is
   run (see "Next concrete step" below). Note: the bounded-verifier
   LLM from decision 1 can reuse v1's existing Groq/gpt-oss-20b setup
   directly — no new API dependency for that narrower role. The
   coreference *engine* itself (finding and clustering mentions) still
   needs a dedicated model; the two roles are not interchangeable
   despite both being "an LLM could technically do this."

### Evaluation — a real gap, not an oversight

ARF has no ground truth for entity resolution (unlike relations).
Recommended order: **extrinsic first** — re-run v1's existing
Benchmark 2/3 pipeline before/after resolution and see if accuracy
moves (free, reuses existing infra). Fall back to small manual
annotation (scaled-down Amalvy & Labatut / BookCoref style) only if
the extrinsic signal is too noisy to read.

**Scope note**: PER-type entities remain the primary target, matching
v1's own PER-only scoping — other types deferred without a measured
need.

---

## Week 4 addendum — empirical validation in `notebooks/explore_entity_resolution.ipynb`

Real findings from testing the Week 4 proposal's assumptions against
actual v1 data, not from reading — recorded here so they don't need
rediscovering.

- **`chunk_id` loads as string dtype from the parquet**, not int.
  Sorting/`.min()`/`.max()` on it are lexicographic, not numeric,
  unless explicitly cast — silently produces a nonsense-looking range
  and a "gappy" passage reconstruction if not caught. Confirmed the
  underlying data itself is fine once cast (book 106: true range
  0–882, zero gaps) — this was a script bug, not a data bug, but a
  real one, and easy to reproduce accidentally again on other books.
- **New dependency conflict**: `fastcoref` requires `transformers`
  4.x; v1's stack is on 5.x. Resolved via a separate venv — and this
  should be the *permanent* answer, not a workaround. Entity
  resolution's `resolution_map` is offline-precomputed, consumed (not
  generated) by the live API — same shape as v1's existing
  `scripts/build_pipeline.py` vs. `api/` split. The dependency never
  needs to coexist with the serving environment at runtime.
- **Memory ceiling found empirically, not assumed**: `FCoref`
  (RoBERTa-backed, plain O(n²) self-attention) failed once with a raw
  allocation error at ~60 chunks / ~6,600 words on a single call, then
  succeeded on an identical rerun — confirmed not a PyTorch allocator
  warm-up artifact (reproduced fresh-kernel). Conclusion: a soft
  ceiling dependent on concurrent system load, not a deterministic
  hard limit — a single successful run at this size should not be
  read as confirmation of a safe threshold. Book 106 is 883 chunks total, ~15x
  this test size — **whole-book single-call processing is confirmed
  infeasible on this hardware**, not just discouraged by BookCoref's
  own architecture recommendation. Two independent justifications
  (BookCoref's accuracy argument, this memory-engineering finding) now
  point at the same windowed-processing requirement for Stage B.
- **`LingMessCoref` tested as the Longformer-backed alternative — found a different, more dangerous failure mode, not a fix.** At 60 chunks, `predict()` silently returned an empty list — no exception, no warning — rather than erroring. Confirmed working at 17 chunks. Ceiling bracketed between 17 (works) and 60 (silently fails), exact value not yet found. Also confirmed ~14x slower than `FCoref` in the range it does handle, matching the model's own published benchmark. **Silent truncation is worse than `FCoref`'s crash**: a crash is loud and debuggable; an empty return is indistinguishable from "nothing to resolve here" unless explicitly checked for, and would silently produce an incomplete `resolution_map` with no indication anything was skipped. Directly relevant to Principle 1 — this isn't the "invented facts" failure Principle 2 guards against, it's the mirror-image failure (silently omitted real ones), and arguably harder to catch.
- **Conclusion, independently reached**: neither model is safe for a single full-book call, for two unrelated reasons (memory instability vs. silent length-based dropping) — model choice is secondary to building windowing first; comparing models without windowing would be comparing both under conditions neither is meant to run in.
- **Real gap flagged, not yet closed**: nothing in this exploration has yet verified a *genuine cross-chunk* resolution (a pronoun correctly linked to an antecedent introduced several chunks earlier) — every successful run so far may only have needed local, within-window context. This is the actual capability Stage B exists for; it hasn't been tested even once yet. First concrete task for the next research session, once windowing exists.

---

## Week 5 — Events as first-class graph nodes 📋

**ROADMAP's required first step**: audit ARF's existing 414
`EVNT`-typed entity occurrences before assuming new extraction is
needed — done in `notebooks/explore_events.ipynb`, on real data, not
assumed.

### Audit findings (own data, not literature)

- 414 EVNT occurrences / 331 unique raw strings, across 74/96 books.
- Manual sampling: a genuine mix — real historical events
  (`Battle of Bull Run`), artistic-work titles (`Tristan and Isolde`),
  structural extraction artifacts (`'CHAPTER VI'` tagged as an event),
  and generic recurring concepts (`breakfast`, `arrest`), not mostly
  removable specific occurrences.
- **Confirmed mistagging, not just ambiguity**: `Tristan and Isolde`
  tagged both `EVNT` and `OBJ` within the same book, same person
  involved. Corpus-wide, 1,119 distinct strings carry more than one
  entity type — caveat: checked globally, not per-book like graph node
  identity; some fraction is legitimate cross-book homonymy, not all
  noise. Re-scoping per-book before trusting the number further is a
  flagged follow-up, not yet done.
- **EVNT-to-EVNT relations: 3 instances in the entire 96-book corpus.**
  No sequencing/causality signal exists in current relations to build
  simulation ordering on — decisive on its own, independent of the
  type-quality question.
- **Hidden-event check** (does event signal exist in relation *type*,
  independent of the unreliable EVNT tag?): top-30 relation types are
  almost entirely relationship *states* (`companion_of`, `friend_of`,
  `sibling_of`), not events. Full 48-type sweep for event-shaped verbs:
  `kills` (2), `married_to` (2), `attacks` (12), `captured_by` (15),
  `captures` (2) — 33 instances total, corpus-wide. Thin, and decisive.

### Vauth & Gius, *Event Annotations of Prose* (2022) ✅ — read in full, 6 pages

**Identity confirmed** against project notes — no mismatch.

**Dataset itself: not usable, decisively.** Six German-language prose
texts (Kleist, Kafka, Fontane, et al.) — ARF is entirely English. Also
a different representational level entirely: per-subclause
narratological typing (non_event / stative_event / process /
change_of_state), not named event entities linked to participants via
relations. Even ignoring language, this schema doesn't produce the
artifact v2 needs (a removable node with participants).

**But the taxonomy explains the audit's own findings, which is worth
more than the dataset would have been.** Their stative vs.
process/change_of_state distinction maps precisely onto what the audit
found: ARF's dominant relation types (`companion_of`, `friend_of`,
`sibling_of`, `spouse_of`) are all *stative* in Vauth & Gius's terms;
genuinely event-shaped, change-of-state relations are rare (33
corpus-wide) because **ARF's 48-type ontology was built to capture
character relationships, not events** — a structural blind spot in the
ontology's own design, not a GPT-4o extraction failure. Better
explanation than "extraction missed things," arrived at only because
the paper was read rather than skipped once the dataset was ruled out.

**IAA caution, applies regardless of path chosen**: core `event_type`
classification gets workable agreement (0.57–0.75 Krippendorff's α)
even among trained annotators with a published guideline and regular
resolution meetings — but several finer properties (`unpredictable`,
`persistent`) score **negative** α on multiple texts, i.e.
worse-than-chance agreement among human experts. Real evidence the
underlying task has genuine ambiguity at the property level, not just
an extraction-quality problem — temper expectations on any method's
ability to cleanly classify event *properties*, even where classifying
*that something is an event* works reasonably.

### Decision: two-tier design, then corrected after checking the data

Proposed design (mechanical-first, dataset-first, non-destructive —
same `resolution_map` shape as Week 4, sits alongside the raw graph,
never mutates it):

1. **Tier 1 — event-shaped relations, direct edge reification.**
2. **Tier 2 — EVNT-typed entities, tiered `event_candidate` map**:
   mechanical exclude (structural artifacts, bare pronouns) →
   flagged-not-excluded (creative-work-verb pattern, generalized to
   "raw string also tagged with a different type elsewhere in the same
   book" — the general version of what caught `Tristan and Isolde`) →
   `needs_review` (tractable at Phase 4's single-book scope — low
   dozens, not 331).

**Tier 1's "no filtering needed, always PER↔PER" claim was checked
against all 33 real rows and falsified — not uniformly, but by
relation type, which changes the design more usefully than a blanket
rejection would have**:

- `attacks` (12/12): **never** PER↔PER — always targets FAC/LOC/VEH
  (`Tyler's regiments → the wall`, `McDowell → Henry Hill`). Consistent
  pattern, not noise: means "military force assaults a place," a
  structurally different event shape (actor + target-location) than a
  person-harm schema. Real events, wrong schema if forced into
  victim/perpetrator roles.
- `captured_by`/`captures` (13/16 clean): mostly holds, but 3 real
  exceptions — `Regulus captured_by Carthaginians` (ORG, not PER, but
  still a sensible event — schema needs to tolerate non-PER
  participants), plus two genuinely odd non-person captures (`rope
  captures tiger`, `commander captures frigate`) that should not
  auto-promote.
- `kills` (n=2): surfaced a deeper problem than relation reliability —
  `tiger (PER) kills sheep (PER)`, both animals mistagged `PER`. The
  `PER` type tag itself can't be trusted as "this is a human
  character," which matters well beyond this one relation type.
- `married_to` (2/2): clean, unambiguous failure — both instances
  link a person to a *location* (`Arthur Rushton married_to London`),
  reading as GPT-4o conflating "married at this venue" with "married
  to this person." 2/2 wrong on an unambiguous relation type — a real
  negative finding, not a hedge, same shape as Week 1's `used_by`
  direction bug.
- No exact chunk-boundary duplicates found in this sample (the
  specific worry raised beforehand) — worth recording that the check
  disconfirmed its own hypothesis, not just that it ran.

**Corrected recommendation**: no blanket Tier 1 auto-promotion.
`captured_by`/`captures` stay in Tier 1 with a participant-type
tolerant schema and the 3 non-PER-PER exceptions routed to
`needs_review`; `attacks` stays but as a structurally distinct event
subtype, not forced into a person-harm role schema; `kills` and
`married_to` move to `needs_review` given 100% and 2/2 failure rates
respectively in the only evidence available.

**Genuinely open, not yet decided**: event node edge semantics —
generic `involved_in` for both participants, or role-differentiated
(`victim_of`/`perpetrator_of`, `actor_of`/`target_of` for the
`attacks` subtype)? Does the original binary relation edge get removed
once an event node exists, or stay as a non-destructive layer
alongside it (matching the pattern used everywhere else so far)? Also
open: whether `Cassandra captured_by Greeks` and `Andromache
captured_by Greeks` (same chunk, same captor) is one event with two
participants or two separate events — a real modeling choice, not
urgent, but not yet made either.

**Vrittanta-EN (LLM-prompt-based event extraction)**: not read. Ruled
out as the next step, not merely deferred — it would create graph
structure ARF never provided, which is categorically different from
Week 4's approved LLM-verifier carve-out (identity judgment over
existing entities) and would need its own separate exception to
Principle 2, not an extension of the one already granted.

---

## Week 7 — Multi-hop traversal + query-direction detection 📋

**Bug found and fixed first, before any traversal changes**:
`evaluation/benchmark.py`'s `generate_questions()`/`_chain_phrase()`
derived question phrasing from raw relation strings independently of
`embedding/relation_text.py`'s already-verified `MANUAL_TEMPLATES` —
two sources of truth for the same fact, and only one was correct.
Confirmed on real output: `child_of`, `protector_of`, `leader_of` all
produced questions asking the opposite of their own ground truth (e.g.
"Who is child of Will?" naturally asks who Will's child is; ground
truth was Will's *parent*). Fixed via `relation_to_question()` —
mechanically wh-fronts the verified statement templates rather than
re-deriving direction from the relation string — and
`relation_to_question(..., direction="reverse")` for the chain case
below. Question generation now scoped to the 31/48 relation types with
a verified template (previously all 48 canonical types); unverified
relations return `None` and are skipped rather than guessed at.

**`graph_n_hop_search()`/`find_n_hop_paths()` were forward-only**
(only followed outgoing edges) — confirmed via direct NetworkX testing
that `.edges(nbunch=[node])` never returns in-edges. Real consequence:
silently misses reachability for relation types README already
confirmed are stored inconsistently in direction (`companion_of` and
similar symmetric types). Demonstrated on a constructed graph before
fixing (same "prove it before assuming" discipline as v1's own
`MultiDiGraph`/GML decisions).

**Direction-agnostic traversal was tried broad (all 48 relation types)
first, then scoped down** — measured, not assumed, at each step:
- Broad version: 3.5–4x reachable-set growth at 2–3 hops (real, large
  effect — confirmed via degree-distribution and reachable-set-size
  diagnostics after the historical 72%/26% benchmark comparison turned
  out to be the wrong instrument to see it with, see below).
- Newly-recovered nodes skew toward high degree (median 2 vs. corpus
  median 1; mean 16.8 vs. corpus mean 9.7) — a real compositional
  shift, confirmed via direct measurement.
- Scoping reverse-traversal to only the 7 confirmed-inconsistent
  symmetric relation types (`companion_of`, `friend_of`, `enemy_of`,
  `rival_of`, `sibling_of`, `spouse_of`, `relative_of`) reduces
  absolute recovered-node volume (~31% less at 2 hops) but does **not**
  reduce the skew ratio — median/mean recovered degree essentially
  unchanged from the broad version. High-degree nodes in this corpus
  are protagonists connected via many relation types simultaneously;
  restricting which relation type triggers reverse-traversal doesn't
  change who's structurally most reachable.

**Decision**: ship the scoped (symmetric-relations-only) version —
matches what README's finding actually evidenced, not a broader claim
the data never made. Hub-skew logged as a real, measured property,
explicitly **not** logged as a confirmed problem — degree-distribution
skew and retrieval-quality harm are separate claims; only the first
was measured, and elevated protagonist-centrality in a narrative graph
may be structurally correct rather than a defect (a query about a
protagonist's companion *should* surface protagonist-adjacent, high-
degree territory). Consistent with, not a reversal of, Week 2's
original CatRAG-derived call to defer precision concerns until
measured — this is a second correct application of that same
discipline, not an exception to it.

**Pre-registered revisit trigger, defined now rather than left vague**:
compare direction-aware benchmark accuracy for questions whose correct
answer is a low-degree node vs. a hub node. A meaningful accuracy gap
disfavoring low-degree answers is the trigger to revisit, not "if it
seems worse." If a degree cap or similar mitigation is ever built in
response, it must be validated against this same accuracy split, not
against its own degree-distribution output — skew reduction alone
would not be evidence the fix helped, since skew was never the
measured harm.

**Methodological note, worth keeping**: the historical 72%/26%
multi-hop benchmark numbers are void, not comparable to any future
rerun — `evaluate_nhop_graph()` turned out to be a self-consistency
check once both question generation and traversal share the same
direction-agnostic logic (does traversal find paths it just generated
using itself), not a real capability measurement. The
reachable-set-size and degree-distribution diagnostics above were
necessary specifically because the existing benchmark metric couldn't
see this fix's effect at all — a second instance of the same lesson as
Benchmark 1 in v1 (naive metrics can fail to detect a real
improvement, not just fail to detect a real problem).

## Week 7, continued — direction-detection module, built and wired in ✅

**Design process, three approaches tried in order, each rejected for a
specific, testable reason** — not settled on the first idea:
- Cosine similarity between the query and each candidate phrasing:
  rejected. The two candidate phrasings for any relation share nearly
  identical word sets, and embedding similarity is fundamentally weak
  at distinguishing word-order differences when the words themselves
  overlap - confirmed empirically (a word-vector-averaging model
  produced IDENTICAL similarity scores for both directions on every
  test case) and independently reconfirmed by this project's own prior
  finding (the original "who protects Taug" vector-search failure).
- A general-purpose dependency parser: rejected. Not because subject/
  object role detection was the wrong idea, but because general-domain
  parsers misparse this corpus's invented proper nouns ("Taug" parsed
  as a noun compound instead of a subject) - the same weakness Week
  3's BookCoref paper predicted for general NLP tools on literary
  names, now confirmed a second time in a different task.
- What works: locating the known entity's position relative to the
  relation's own already-verified phrasing (embedding.relation_text's
  MANUAL_TEMPLATES), via two tiers - exact anchor phrase, falling back
  to a verb form for relations that have one. Deterministic, fails
  safe (returns None) rather than guessing wrong.

**Three real bugs caught by testing the module against its own design,
not just accepted on first pass:**
1. A naive mechanical -er/-or suffix-strip rule for deriving verb
   forms produced broken stems (mother -> "moth", mentor -> "ment",
   lover -> "lov") - "ment" collided with ordinary English words
   ("mentioned", "sentiment"), a silent false positive, not just a
   missed match. Fixed by hand-verifying the verb-form list instead of
   deriving it - same discipline MANUAL_TEMPLATES itself needed.
2. travel_to's anchor phrase is just "to" (2 characters) - matched
   inside any query containing the word "to" at all, confidently
   misclassifying unrelated queries. Every other template's anchor is
   7+ characters, a large natural gap; fixed with MIN_ANCHOR_LENGTH=5.
3. Short entity names matched as substrings of unrelated names via
   plain string search ("An" matching inside "Ann"), producing a
   confidently wrong direction for a sentence about a different
   person entirely. Fixed with word-boundary regex matching.
4. (Found while wiring into hybrid_search, not in isolated testing)
   15/31 templates use "a"/"an" as their anchor's article, but "the X
   of Y" is equally natural English and was being missed entirely -
   real, common gap, not an edge case. Fixed with article-variant
   matching (a/an <-> the).

**Integration into retrieval/hybrid_search.py, two uses:**
- `entity_to_expand_from()` replaces the previously-hardcoded "always
  expand chains from entity2" default (explicitly flagged as
  provisional when hop_depth/chains was first built) - chain expansion
  now continues from whichever entity the query is actually asking
  about. Falls back to entity2 (the original default) when direction
  can't be determined - strictly additive, not a regression.
- `direction_match()` annotates each fact in all_relationships with
  True/False/None - whether the query's detected direction aligns
  with that fact's stored direction. Deliberately additive-only, never
  filters: a direction mismatch means a fact doesn't directly answer
  what was asked in the direction asked, not that it's wrong or
  irrelevant. Whether to use, hide, or deprioritize a mismatched fact
  is left to whatever consumes this output (e.g. answer_generation.py)
  - kept out of retrieval's decision-making, consistent with keeping
  retrieval and presentation concerns separate.

**A genuinely informative integration test result**: for the exact
"protector of the friend of the knight" motivating example, the
single-hop fact gets correctly flagged `query_direction_match: False`
(the query's literal phrasing implies the opposite direction from how
the fact happens to be stored) - but `chains` still finds the complete
correct multi-hop answer anyway, because chain expansion explores the
whole neighborhood of the query-relevant entity rather than being
constrained by any one fact's specific direction. The system is
honestly uncertain about the single fact and correct about the full
answer at the same time - not a contradiction, a demonstration that
the two mechanisms serve genuinely different purposes.

**Verified against 72 passing tests** across `test_traversal.py`,
`test_direction_detection.py`, `test_relation_text.py` (additions),
`test_hybrid_search.py` (additions), `test_benchmark.py` (new),
`test_relation_ontology.py` (additions) - see `tests/`.

**Genuinely still open, not resolved from this session:**
- `api/answer_generation.py` and `api/schemas.py` were never seen -
  whether `EnrichedHit.chains`/`query_direction_match` need any
  handling there (e.g. strict schema validation choking on new keys)
  is unverified, not confirmed safe.
- Chain expansion currently checks direction using only the first
  relationship in a multi-relationship pair (`relationships[0]`) when
  choosing which entity to expand from - untested for pairs with
  multiple, differently-directed relation types between the same two
  entities.
- No live end-to-end test exists exercising a real ChromaDB collection
  and real SentenceTransformer together with this feature - all
  testing here uses fakes, by design, but real vector-search behavior
  (versus a fake returning fixed results) is unverified.

---

## Week 7, real-usage reality check — north star audit ⚠️

**Context**: after Week 7 was declared closed (traversal, direction
detection, wiring, API, UI all shipped and unit/integration tested),
real informal usage against the live system — not synthetic test
data — was checked against the project's own north star claim:
*"does making narrative state explicit give us causal traceability,
structural consistency, controllability, and reproducibility that
implicit LLM simulation doesn't naturally provide."* Three problems
were reported from that real usage; a `diagnose_direction_coverage.py`
(zero-dependency, text-only) and `diagnose_pipeline.py` (full
pipeline, real corpus/ChromaDB/model) were built to get evidence
rather than debug from memory, since no specific failing examples
were retained. **This is arguably the most important finding of the
whole project so far** — it's the first check against real,
unscripted usage rather than curated or auto-generated test data, and
it changes what "Week 7 complete" actually means.

**The core methodological lesson, stated once, applies to everything
below**: every test built during Week 7 (93+ passing tests) used
synthetic graphs or benchmark questions generated by
`generate_questions()`/`generate_nhop_questions()` — and
`direction_detection.py` was validated against exactly the phrasing
those generators produce (`"Who is X a Y of?"`). Benchmark and
detector were tested against each other's output, never against
independent human phrasing. Structurally the same trap as
`evaluate_nhop_graph()`'s self-consistency bug (fixed earlier in
Week 7) — recurring one level higher in the stack, where no unit test
could see it.

### 1. Direction-detection coverage — confirmed near-total failure on real phrasing

`diagnose_direction_coverage.py` run against 3 real corpus names
(Taug, Akut, Teeka) across 8 phrasing styles:

- **"of"-genitive (the tested style)**: 100% detected, as expected.
- **Possessive genitive** (`"Taug's companion"`, `"Taug's friend's
  leader"`): **0% detected**, consistently across all 3 names — not
  a one-name fluke. `detect_query_direction()` itself returns `None`
  here, not just `estimate_hop_depth()` — meaning `direction_match`
  and `entity_to_expand_from` are silently inert for this entire
  phrasing family, not just chains.
- **New, dangerous finding — false positive, not just missed
  coverage**: `"Who does Taug's companion protect?"` → confidently
  detected `forward`. This is wrong: the query is about Taug's
  *companion's* protectee (a 2-hop relationship), not Taug's own
  `protector_of` role. Plain substring verb-matching found "Taug"
  positioned before "protect" and fired, with no awareness that
  `"'s companion"` sits structurally between them. A confident wrong
  answer, not a safe decline — the one exception found so far to the
  "fails safe" property everything else in Week 7 held to.
- **New finding — unhandled question type**: yes/no questions
  (`"Is Taug a companion of Akut?"`) get treated as wh-questions
  seeking an unknown entity. Not a phrasing coverage gap so much as a
  missing question-type classification the system was never designed
  to have.

### 2. Chains — 0/11 on real, naturally-phrased multi-hop questions, for three compounding causes

`diagnose_pipeline.py` run against 11 real questions from an actual
book (Felix Holt), each checked twice for retrieval stability.
`hop_depth = 0` and `total_chains = 0` on **all 11**, no exceptions.
Three separate, compounding causes identified, not one:

1. **Possessive genitive** (known, confirmed above) — compounded
   further when it's layered under an "of"-genitive prefix (e.g.
   `"the mother of Esther Lyon's husband"` — the outer phrase would
   match, the inner one doesn't).
2. **Missing gendered kinship vocabulary, new finding**:
   `MANUAL_TEMPLATES` has `parent_father_of`/`parent_mother_of` but no
   entries at all for "husband," "wife," "son," or "daughter" — not a
   phrasing-style problem, a genuine ontology coverage gap dating to
   v1's original template set, invisible until real family-relation
   questions were tried.
3. **Modifier-breaks-exact-match, new finding**: `"the biological
   father of"` doesn't contain the literal substring `"the father
   of"` — anchor matching requires contiguity, and any inserted
   adjective defeats it silently.

### 3. Entity canonicalization — confirmed, and worse than any prior documented finding

Matched pairs from real retrieval included bare pronouns stored as
canonical entity names (`('rufus lyon', 'you')`, `('mr. lyon',
'her')`) **and full descriptive clauses**
(`('jermyn', "jermyn's third daughter")`,
`('jermyn', 'his third affectionate and expensive daughter')`). This
goes beyond every previously-documented entity-quality finding
(README's "apes"/"the apes" generic-entity gap, the "his brother"
pronoun caveat, Week 5's EVNT mistagging) — those were about
*ambiguous* canonical strings; this is *raw, uncleaned extraction
noise* with no canonicalization pass applied at all. Directly explains
why `query_direction_match` is `None` almost everywhere in the
pipeline diagnostic: these "entity names" could never appear in a
real user's query text, so direction detection has nothing to anchor
to regardless of phrasing coverage. Real, concrete input for scoping
Week 8's entity resolution work more aggressively than the original
Week 4 proposal assumed (mechanical pre-filtering of pronoun-only and
clause-length raw strings, before any of the alias/coreference work
begins).

### 4. Reproducibility — cleanly isolated to exactly one layer

`retrieval_stable_across_calls = True` on all 11 questions — graph
traversal and ChromaDB retrieval are deterministic here; ruled out as
a contributor, not just assumed clean.

`llm_stable_on_same_facts = False` on 10/11 — confirms `temperature=
0.2` (a v1-era default, never revisited before this check) as the
cause, not a guess. Most instances were cosmetic rewording of "cannot
be determined." **One was not cosmetic**: for *"Who is the lawyer
that manages the estate of Mrs. Transome's son?"*, the identical
retrieved facts produced "cannot be determined" on one call and an
unhedged *"The lawyer who manages the estate... is Lawyer Jermyn"* on
the other — inferring "owns the estate" implies "manages the estate,"
which no retrieved fact states. This is the prompt's own explicit
"say plainly it cannot be determined... rather than guessing"
instruction being violated on roughly half of identical trials, on a
question that isn't even multi-hop. A serious finding independent of
everything else here.

### Recommended order of fixes, not yet started

1. `temperature=0` — cheap, directly evidenced, no dependency on
   anything else here.
2. Gendered kinship synonyms (husband/wife/son/daughter) +
   modifier-tolerant anchor matching (allow 0–2 inserted words) — small
   and mechanical, but deserves its own careful build-and-test pass,
   not a rushed patch, given how much the possessive-genitive fix
   already grew once actually investigated.
3. Possessive-genitive support in `detect_query_direction()` itself
   (not just `estimate_hop_depth()`) — still the largest lift.
4. Entity-canonicalization severity — feed into Week 8's scoping as
   evidence, not patched ad hoc now.



These weren't designed to compare — they surfaced from reading
unrelated papers in sequence, which makes the convergence worth
recording:

- **Precision-first, recall-later funnels** — CatRAG's coarse-to-fine
  edge pruning, BookCoref's link-then-expand pipeline. Same shape
  wherever false positives are expensive downstream and false
  negatives are cheap to recover later.
- **"Once retrieval" over iterative/agentic retrieval** — independently
  argued for by both the GraphRAG survey (§6.2.4's tradeoff analysis)
  and CatRAG (explicit latency rejection of iterative refinement).
- **Static graphs as an open problem, not a solved one** — the
  GraphRAG survey names it directly (§10.1); CatRAG is the only source
  engaging with a version of it, but for a different axis (query-time
  weighting, not scenario-time topology change).
- **LLM-for-identity-verification, not extraction** — three
  independent entity-resolution sources reach for this pattern. Real
  enough to need one project-wide decision (Week 4), not three
  separate calls.

---

## Decision log

1. ✅ **Resolved** — LLM permitted only as a bounded verifier over
   existing candidate entities; never to create new entities or
   relations.
2. ✅ **Resolved** — pretrained, off-the-shelf coreference model;
   no fine-tuning/in-house build unless a later evaluation shows it's
   necessary.
3. 🔲 **Still open** — which specific pretrained coreference model.
   Next concrete step: a small feasibility smoke-test against real ARF
   book text (not a Week 8 build — just "does candidate model X
   produce sane output on our actual data at all"), same spirit as
   v1's pre-deploy platform verification (README, Week 4). Requires
   running against the real dataset, so this happens in the project's
   own notebook/environment, not this research-summary session.
4. ✅ **Resolved** — events become first-class graph nodes via a
   two-tier, non-destructive design (edge reification for event-shaped
   relations + tiered `event_candidate` map for EVNT-typed entities),
   per-relation-type gating corrected against real data, not blanket.
   No new extraction; Vrittanta-EN ruled out, not deferred.
5. 🔲 **Still open** — event node edge semantics (generic `involved_in`
   vs. role-differentiated per event subtype); whether the original
   binary relation edge is removed or kept alongside the new event
   node; single-event-multi-participant modeling (the `Cassandra`/
   `Andromache`/`Greeks` case). Flagged for Week 9, not yet decided.
6. 🔲 **Still open** — re-scope the 1,119 multi-typed-string count
   per-book (currently global) before it's used to argue anything
   beyond the one confirmed `Tristan and Isolde` example.
7. ✅ **Resolved** — `generate_questions()`/`_chain_phrase()` direction
   bug fixed (derive questions from `relation_text.py`'s verified
   templates, not ad hoc phrasing); n-hop traversal made
   direction-agnostic, scoped to the 7 confirmed symmetric relation
   types only, not all 48. Historical 72%/26% benchmark numbers void.
8. 🔲 **Still open, trigger pre-registered** — hub-skew in recovered
   n-hop nodes is measured (confirmed real) but not shown harmful to
   retrieval quality (separate, unproven claim). Revisit only if
   direction-aware benchmark accuracy is meaningfully worse for
   low-degree-answer questions vs. hub-answer questions. Any future
   degree-cap mitigation must be validated against that same accuracy
   split, not against its own degree-distribution output.
9. ⚠️ **Revised — Week 7 was NOT fully closed, despite the prior
   entry here.** Query-direction detection was built, unit/integration
   tested (93 passing tests), and wired into `hybrid_search.py` — but
   a real-usage audit against the north star (see "Week 7, real-usage
   reality check" section above) found the phrasing-coverage gap is
   severe enough that the feature is near-inert on real questions
   (0/11 chains found on real multi-hop questions). Tests passing was
   necessary but not sufficient evidence of "closed" — correcting the
   premature claim rather than leaving it standing.
10. ✅ **Resolved** — `api/answer_generation.py`/`api/schemas.py`/
    `api/main.py` all reviewed and updated (`ChainFact` schema,
    dynamic `hop_depth`, chains wired through to the LLM prompt and
    API response, UI updated). A real off-by-one bug in hop-budget
    compensation was caught only by testing through the actual API
    endpoint with a dynamically-estimated `hop_depth`, not a
    hand-picked test value — logged as its own methodological lesson.
11. 🔲 **Open, prioritized** — from the real-usage audit:
    (a) ✅ **Resolved and verified** — `temperature=0` set in
    `retrieval/answer_generation.py`. Re-ran `diagnose_pipeline.py`
    after the change: retrieval remained stable (as before), and LLM
    stability rose from 1/11 to 10/11. The one remaining unstable case
    ("Who is the mother of Esther Lyon's husband?") was checked
    directly, side by side — confirmed genuinely cosmetic wording
    only ("available data" vs. "given data"), not a second Jermyn-
    style over-inference. Real evidence, not assumed clean.
    (b) 🔲 add gendered kinship synonyms (husband/wife/son/daughter/
    brother/sister) + modifier-tolerant anchor matching - in progress;
    (c) possessive-genitive support in `detect_query_direction()`
    itself, not just `estimate_hop_depth()` - not started;
    (d) feed the entity-canonicalization severity findings (bare
    pronouns and full descriptive clauses stored as canonical entity
    names) into Week 8's scoping - not started.
