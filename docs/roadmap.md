# Roadmap

The plan for v2 and beyond, with current status. Weeks are sequence markers, not
deadlines, and any of them may stretch. Each is tagged **[Research]** (uncertain
output; the deliverable is a decision or proposal, not necessarily code) or
**[Build]** (a concrete implementation deliverable). Keeping the two modes
separate was a lesson from the v1 deployment stretch, where reasoning got crowded
out by task urgency.

**Standing rule: no week is complete on passing tests alone.** A real-usage audit
against unscripted queries is required before a build week is closed. Week 7
shipped with 93 passing tests and still failed on 11 of 11 real questions. See
[`lessons-learned.md`](lessons-learned.md).

---

## Status

| Phase | Weeks | Status |
|---|---|---|
| 1. Grounding (research) | 1–5 | Complete |
| 2. Foundational build | 6–9 | Weeks 6–7 complete; Week 8 in progress, not closed; Week 9 not started |
| 3. Simulation core | 10–13 | Not started |
| 4. Demo | 14+ | Not started |

---

## Phase 1 — Grounding (complete)

Findings are in [`research-notes.md`](research-notes.md) and the findings
documents.

- **Week 1 [Research]** — GraphRAG survey: what transfers given the project's
  constraints.
- **Week 2 [Research]** — CatRAG: whether its static-graph critique applies to
  simulation traversal (it does not transfer; its chain-completeness metrics do).
- **Week 3 [Research]** — Entity resolution, one facet per source: alias
  resolution, coreference, generic and collective entities.
- **Week 4 [Research]** — The unified entity-resolution proposal (ambiguity, alias
  and coreference as one design).
- **Week 5 [Research]** — Events as first-class graph objects; audit of the
  existing EVNT entities; a two-tier design. See
  [`v2-events-findings.md`](v2-events-findings.md).

## Phase 2 — Foundational build

- **Week 6 [Build], complete.** Temporal phrase parsing ("in the beginning" to a
  bin range). Small and well scoped; unlocks simulation's "at what point in the
  story" requirement.
- **Week 7 [Build], complete.** Real n-hop traversal wired into the live
  `hybrid_search()` path, closing the gap behind v1's "protector of the friend of
  the knight" failure. The scope grew well beyond its original one line: a full
  query-direction detection module, a real-usage audit (which produced the
  standing rule above), and a series of downstream fixes. See
  [`v2-retrieval-findings.md`](v2-retrieval-findings.md).
  The motivating example ("who protects the friend of the knight") is not
  answerable in the correct direction by the current traversal; see `known-limitations.md` item 17.
- **Week 8 [Build], in progress, not closed.** Entity resolution per the Week 4
  proposal. **Success criterion:** resolution must produce a *real, nameable
  form* that a genuine query could contain, not merely reduce ambiguity in the
  abstract. Isolated testing showed direction detection itself is sound; the
  ceiling was canonical strings like `"jermyn's third daughter"` and bare
  pronouns. Stage 0 (pronoun/generic filter) and Stage A (surface-variant merge)
  are built and wired in. On the correctness yardstick the layer currently lowers
  accuracy, and the proposed fix is unmeasured. Remaining: re-verify pair
  exclusion across the three known cases, the direction-detection ceiling
  measurement, and housekeeping. See
  [`v2-entity-resolution-findings.md`](v2-entity-resolution-findings.md) and
  [`v2-decisions.md`](v2-decisions.md) (items 40, 45, 50, 52).
- **Week 9 [Build], not started.** Event nodes in the graph schema per Week 5's
  design. Two sub-decisions are still open going in: event-edge semantics (generic
  versus role-differentiated) and whether the original binary relation edge is
  kept alongside the event node.

## Phase 3 — Simulation core

- **Week 10 [Research].** Design the counterfactual simulation algorithm: node or
  event removal, then reachability and centrality deltas. Depends on Weeks 8–9;
  no LLM in this step. PASTA is the most relevant grounding source for modeling
  participant state change from a removed event.
- **Week 11 [Build].** Implement node and event removal with reachability-change
  detection.
- **Week 12 [Build and Research].** Centrality-based "ripple effect" scoring. Also
  design what benchmarking means here: there is no ARF-style ground truth for
  counterfactuals, so evaluation methodology is part of the work.
- **Week 13 [Build].** LLM narration layer for simulation output, under the same
  "narrate, never decide" discipline as the answer step.

## Phase 4 — Demo, not before it is earned

- **Week 14 [Build].** A single curated-book v2 demo, end to end.
- **Week 15 and later [optional, evidence-gated].** A self-hosted arbitrary-book
  upload path and/or narration-style fine-tuning, only if Phase 3 surfaces a
  specific need. Neither is scheduled by default. Fine-tuning would require local
  model weights, reversing v1's API-only LLM decision, so it needs a deliberate,
  evidence-based trigger.

---

## Long-term goals

1. **Mastery of a single curated public-domain book** (checked by hand against that
   one book), as the depth target.
2. **Reproducibility by any user on a book of their choice.** This needs a
   relation-extraction pipeline, which v1 excluded by charter and which conflicts
   with the dataset-first constraint, so it would require its own explicit
   exception. Design considerations recorded so far (a sketch, not started):
   a swappable extraction backend (free API or local model); several candidate
   models plus evidence verification against retrieved sentences; ARF itself as
   the benchmark, by stripping `relations` from a few books and scoring the
   pipeline's output against ARF's ground truth. Goal 1 comes first and may use
   manual curation; Goal 2 cannot, so it is a harder bar than anything validated
   so far.

A hosted demo with usage limits is intended only once v2 meets its quality bar
(see [`deployment.md`](deployment.md#planned-hosted-demo)).

---

## Deferred from v1

Not implemented, and not planned for v1:

- Arbitrary book upload (needs a real relation-extraction pipeline; see Goal 2).
- Temporal slider UI.
- Counterfactual and "what if" narrative simulation (Phase 3).
- Local model fine-tuning on user corrections.
- Multiple embedding template variants per relation, for retrieval diversity.
- Precomputed or cached temporal trajectories, if query-time latency becomes a
  measured problem.
- Query-side direction and role detection. *Since built in Week 7; coverage gaps
  remain (see [`known-limitations.md`](known-limitations.md), item 9).*
- Git branch-per-feature workflow (not needed for single-developer sequential
  work at this scale).

## Reference sources not currently scheduled

Revisit only if a real need surfaces; see
[`research-notes.md`](research-notes.md#identified-but-not-read-or-unverified)
for their status: PHARE (likely a domain mismatch), "sentiment-fiction-seq"
(unverified), and Tsutsui's *Resolving the Canon* (cross-book entity merging stays
out of scope).
