# Research Notes — Literature

This file records the papers and tools reviewed for NIE: what each says,
how reliable the reading was, and what does and does not transfer to this
project. It contains literature only. Findings from the project's own data
are in the findings documents listed in [`README.md`](../README.md#documentation).

**Reading-status markers**

| Marker | Meaning |
|---|---|
| Read in full | The source text was read directly. |
| Secondhand | Analyzed from a summary, not the source text. Lower confidence. |
| Not read | Identified or evaluated from metadata only. |

**Identity checks.** Paper identity was checked against the actual document
for every source below rather than assumed from a filename or citation. Two
mismatches were caught this way and are noted in the relevant entries
(GraphRAG survey, alias-resolution guidelines).

---

## Reading status at a glance

| Source | Used for | Status | Outcome |
|---|---|---|---|
| Christou & Tsoumakas 2025, *Artificial Relationships in Fiction* (ARF) | Dataset, ontology | Read | Dataset source |
| Christou & Tsoumakas 2025, *Relational Arcs as Narrative Structure* | Temporal binning | Read | Binning adopted with one deviation |
| Peng et al. 2024, *Graph RAG: A Survey* (arXiv:2408.08921) | Retrieval architecture | Read in full | Validates v1 design; names the static-graph gap |
| Lau et al. 2026, *Breaking the Static Graph* / CatRAG (arXiv:2602.01965) | Traversal, evaluation | Read in full | Non-transfer finding; metrics adopted |
| Amalvy & Labatut, *Alias Resolution* guidelines (arXiv:2410.00522) | Alias resolution | Read in full | Taxonomy of hard cases |
| Martinelli, Bonomo et al. 2025, *BookCoref* (arXiv:2507.12075) | Coreference | Read in full | Pipeline shape; book-scale ceiling |
| Bhattacharya & Getoor 2007, *Collective Entity Resolution in Relational Data* (ACM TKDD 1(1), Art. 5) | Generic/collective entities | Read in full | Judged out of scope for use in this project |
| Vauth & Gius 2022, *Event Annotations of Prose* | Events | Read in full | Dataset unusable; taxonomy explanatory |
| Vrittanta-EN (LLM-prompt event extraction) | Events | Not read | Ruled out |
| Edge et al., Microsoft GraphRAG | Retrieval architecture | Not read | Covered through the Peng et al. survey |
| Otmazgin et al., F-coref / `fastcoref` (arXiv:2209.04280) | Coreference tooling | Metadata and library behavior | Tested empirically |
| LingMess coreference model | Coreference tooling | Metadata and library behavior | Tested empirically |

---

## v1 sources

### ARF dataset paper — Christou & Tsoumakas (LaTeCH-CLfL 2025)

*Artificial Relationships in Fiction: A Dataset for Advancing NLP in Literary
Domains.* Source of the corpus and its closed relation ontology.

- Appendix C defines the 48-type relation ontology. Its example sentences were
  used to cross-check relation direction when writing templates (for example,
  `owned_by`: entity1 is the thing owned, entity2 the owner, matching the
  paper's "Thornfield Hall is owned_by Mr. Rochester").
- The paper reports a 2.95% relation-level ontology deviation rate (extraction
  producing free-text relations outside the closed ontology). The project
  measured 2.5% of instances outside the 48 types, consistent with this.
- The paper's own definition of `used_by` is internally inconsistent (see
  [`data-findings.md`](data-findings.md#used_by-direction-inconsistency)).

### Relational Arcs — Christou & Tsoumakas (2025)

*Relational Arcs as Narrative Structure: Dynamics, Distribution, and Diachronic
Change in Fiction.* Same authors, same 96-book corpus.

**Adopted:** percent-of-book binning. Bin count `N = clamp(total_relations / 15,
6, 20)`; bin assignment `k = floor(position * N / total_span) + 1`.

**Deviation (verified necessary):** the published formula assumes `chunk_id`
starts at 0. ARF's per-book chunk sampling means it does not always do so, so
the implementation uses `chunk_id - min_chunk_id`. On a constructed case, a
chunk 5 positions into an 883-chunk span landed in bin 1 with the correction
and bin 3 without it.

**Not adopted (scope, not oversight):** relation-family collapsing (48 → 7
families), change-point or turning-point detection, and k-means arc-shape
clustering. These are the paper's own literary-analysis contributions rather
than infrastructure that retrieval needs.

---

## v2 Phase 1 sources

### Graph Retrieval-Augmented Generation: A Survey — Peng et al. (2024)

arXiv:2408.08921, 41 pages. **Read in full.**

**Identity note.** This is a broad survey of the GraphRAG methodology space, not
Edge et al.'s original Microsoft GraphRAG paper, which an earlier project note
had cited. Edge et al.'s method is described concretely within the survey
(indexing, generation and industry sections), which is sufficient secondhand
grounding. The original paper was not read.

**Validates v1's existing design** (no adoption needed):
- NetworkX graph + templated-sentence embeddings + ChromaDB corresponds to the
  survey's "Hybrid Indexing" pattern, the field's practical default.
- `relation_to_sentence()` templating corresponds to the survey's "Natural
  Language" graph-format category, the most common choice.
- `hybrid_search()`'s single-pass design corresponds to "Once Retrieval", a
  documented latency/accuracy tradeoff.

**Does not transfer:**
- Community-summary infrastructure (Edge et al.'s core mechanism) targets
  Query-Focused Summarization ("what are this corpus's themes"). Every NIE query
  has a small, localized evidence set, so there is no summarization-shaped
  question in this project. A confirmed non-fit, not a deferred option.
- LLM-based graph construction, used by every industrial system surveyed
  (Microsoft, NebulaGraph, AntGroup, Neo4j), conflicts with the project's
  dataset-first constraint. A deliberate minority choice.

**Most important finding for v2.** Section 10.1 states that nearly all GraphRAG
methods assume a static graph, and names dynamic or adaptive graph updating as a
barely explored open direction with no solved approach cited. Counterfactual
simulation (remove a node or event, re-traverse) sits in exactly this gap, so
there is no recipe to adapt; the design work is closer to original
graph-algorithms work than to applying a known pattern.

**Design input for live multi-hop retrieval.** Non-parametric, fixed-depth,
single-pass traversal, wired in directly rather than an LLM-agent iterative
loop. The field has precedent for this (Wang et al., GNN-RAG).

### CatRAG — Lau et al. (2026)

*Breaking the Static Graph: Context-Aware Traversal for Robust RAG*,
arXiv:2602.01965, February 2026, 13 pages. **Read in full.** Identity matched
project notes.

**What it is.** Builds on HippoRAG 2's Personalized PageRank (PPR) retrieval.
The "Static Graph Fallacy": PPR transition weights are fixed at index time and
do not discriminate by query, so probability mass diffuses into high-degree hub
nodes, giving high partial recall but broken multi-hop evidence chains. The fix
is LLM-scored dynamic edge reweighting per query, combined with weak-entity-
anchor seeding and a non-LLM key-fact passage boost.

**Transfer assessment: two different answers for two parts of v2.**

- *Live multi-hop retrieval:* does not transfer directly. CatRAG's failure is a
  recall loss: PPR is stochastic and mass genuinely leaks to hubs. NIE's
  `graph_n_hop_search` is exhaustive BFS and deterministic, so a hub cannot
  cause it to miss anything inside the hop radius. A related but different
  risk is hub entities flooding the neighborhood with irrelevant results. That
  is a precision problem, not CatRAG's recall problem (later measured; see
  [`v2-retrieval-findings.md`](v2-retrieval-findings.md)).
- *Simulation traversal:* does not transfer, and this is a real negative
  result. CatRAG addresses graphs static *across queries* (fixed topology,
  query-adaptive weights). Simulation needs graphs static *across scenarios*:
  topology changes via real node removal and exact reachability or centrality
  is recomputed, with no stochastic weighting. The problems are orthogonal.
  CatRAG's fix mechanism (an LLM scoring edges to decide traversal weighting)
  is also exactly what the project's simulation constraint rules out.

**Transfers:** Full Chain Retrieval (FCR) and Joint Success Rate (JSR), which
ask whether retrieval returned the *entire* gold evidence chain rather than an
overlapping subset. These are the multi-hop generalization of the lesson the
project's own single-hop Benchmark 1 → 2 evolution found independently
([`benchmarks.md`](benchmarks.md)). Intended input for evaluating simulation,
where no ARF-style ground truth exists.

**Secondary confirmation.** CatRAG rejects iterative or agentic retrieval on
latency grounds, independently reinforcing the "once retrieval, fixed-depth"
conclusion from the survey.

### Alias Resolution guidelines — Amalvy & Labatut

*Annotation Guidelines for Corpus Novelties: Part 2 – Alias Resolution*,
arXiv:2410.00522, 14 pages. **Read in full.**

**Identity note.** The document is a set of human annotation guidelines for
building a gold corpus, not an automated clustering algorithm. An earlier
project note had described a method that is not present in it.

**Value: a taxonomy of hard cases, not a method.** True aliases can share zero
string overlap (`Milady` → `Anne de Breuil`; `D'Artagnan` → `Charles de Batz de
Castelmore, dit d'Artagnan`). This explains why v1's `difflib` fuzzy matching
failed structurally and not only numerically. It splits alias resolution into
two tiers:

1. *Surface variants*: mechanically tractable (honorific stripping, name-part
   matching).
2. *True aliases*: not mechanically solvable without external knowledge or
   narrative context.

The guidelines also note the use of generative models for historical lookups,
one of three sources reaching for an LLM as an identity verifier (see
[cross-source patterns](#cross-source-patterns)).

### BookCoref — Martinelli, Bonomo et al. (2025)

*BOOKCOREF: Coreference Resolution at Book Scale*, arXiv:2507.12075, July 2025,
19 pages. **Read in full.**

**Finding.** Off-the-shelf coreference models score 40–51 CoNLL-F1 at book scale
(against roughly 80+ on standard benchmarks). Even the best specialized systems,
fine-tuned on book-scale data, reach only 61–67. The gap never fully closes,
which the paper itself states. This corrects an earlier project note that had
understated the result as "specialized resources solve it".

**Reusable pipeline shape.** A precision-first, recall-later funnel: link
explicit named mentions first (high precision), verify, then expand to pronouns
and generic phrases through windowed-then-grouped coreference passes. It has
the same shape as CatRAG's coarse-to-fine pruning.

**Implications.**
- ARF's 5-sentence chunking is the wrong granularity for coreference by the
  paper's own diagnosis; antecedents several chunks back cannot resolve under a
  per-chunk pass.
- The paper's PER-only annotation scope independently matches the project's
  PER-focused scoping.
- Mentions LLM-based mention verification (one of the three LLM-as-verifier
  sources).

### Collective Entity Resolution in Relational Data — Bhattacharya & Getoor (2007)

*ACM Transactions on Knowledge Discovery from Data* 1(1), Article 5, March 2007.

**Status.** Initially analyzed from a secondhand summary; the full text was
later read directly. **Decision: out of scope for use in this project.** The
assessment below records why.

**What it describes.** Entity resolution as relational clustering. Instead of
resolving reference pairs independently from attribute similarity, references
that co-occur (for example, coauthors on a paper) are resolved jointly:
confident merges (an uncommon name such as `A. Ansari`) become evidence for
merging their neighbors. Cluster similarity is
`sim = (1 - α) · attribute_sim + α · relational_sim`, where relational
similarity compares the *current cluster labels* of each cluster's neighbors
and not their raw attributes. Neighborhood measures compared: common
neighbors, Jaccard, Adamic/Adar (with a name-ambiguity variant), and a
path-length-3 variant. Implementation uses blocking, bootstrapping with
high-precision exact matches, greedy agglomerative merging, and negative
constraints (two references in one hyperedge cannot be the same entity).

**Results reported.** On CiteSeer, arXiv and BioBase, collective resolution
beat attribute-only and naive-relational baselines, with the largest gain on the
most ambiguous dataset (BioBase F1 0.819 against 0.568 for the attribute
baseline). Synthetic experiments showed gains grow with hyperedge size and
ambiguity but peak and then decline as the entity graph gets denser.

**Scope mismatch (why it is out of scope here).** The method resolves
*individual* identity, where exactly one true referent exists to converge on.
NIE's generic or collective entities (`apes` vs `the apes` vs `young apes`) may
have no single true referent at all. They may denote different narrative
subsets rather than one entity under different names. The mechanism
(relational-neighborhood overlap as soft evidence) may still be useful. The
semantics of a "correct merge" do not transfer, and the paper's own framework
does not resolve that gap. For pure determiner or plural normalization
(`the apes` → `apes`), a normalization pass is the right tool, and collapsing
generic and specific references would introduce errors rather than fix them.

### Event Annotations of Prose — Vauth & Gius (2022)

**Read in full** (6 pages). Identity matched project notes.

**The dataset is unusable.** Six German-language prose texts (Kleist, Kafka,
Fontane and others) against an entirely English corpus. It also operates at a
different representational level: per-subclause narratological typing
(`non_event`, `stative_event`, `process`, `change_of_state`), not named event
entities linked to participants. Even setting language aside, the schema does
not produce the artifact the project needs (a removable node with participants).

**The taxonomy is the valuable part.** The stative versus process or
change-of-state distinction maps directly onto an audit finding: ARF's dominant
relation types (`companion_of`, `friend_of`, `sibling_of`, `spouse_of`) are all
*stative*, and genuinely event-shaped relations are rare. ARF's 48-type ontology
was built to capture character relationships, not events, a structural blind
spot in the ontology's design rather than an extraction failure. See
[`v2-events-findings.md`](v2-events-findings.md).

**Inter-annotator caution.** The core `event_type` classification reaches
workable agreement (Krippendorff's α 0.57–0.75) even among trained annotators
using a published guideline. Several finer properties (`unpredictable`,
`persistent`) score *negative* α on multiple texts, which is worse than chance
among human experts. Any method should be expected to classify *that something
is an event* more reliably than it classifies event *properties*.

### Vrittanta-EN — LLM-prompt-based event extraction

**Not read.** Ruled out as the next step, not merely deferred. It would create
graph structure that ARF never provided, which is categorically different from
the approved identity-verifier carve-out (an LLM judging identity over
*existing* entities) and would need its own explicit exception to the
dataset-first constraint rather than an extension of the existing one.

---

## Coreference tooling evaluated

Evaluated empirically rather than from the papers; results are in
[`v2-entity-resolution-findings.md`](v2-entity-resolution-findings.md).

- **`fastcoref` / F-coref** (Otmazgin et al., arXiv:2209.04280): RoBERTa-backed,
  designed to be fast on CPU.
- **LingMess coreference model** (available through `fastcoref`):
  Longformer-large backbone. The model's own published benchmark reports it as
  roughly 14× slower than F-coref (about 25 seconds versus 6 minutes per 2.8K
  OntoNotes documents), which the project's own timing agreed with.

---

## Cross-source patterns

These sources were not chosen for comparison; the convergence surfaced from
reading unrelated papers in sequence.

- **Precision-first, recall-later funnels.** CatRAG's coarse-to-fine edge
  pruning and BookCoref's link-then-expand pipeline share this shape, which
  recurs wherever false positives are expensive downstream and false negatives
  are cheap to recover later.
- **"Once retrieval" over iterative or agentic retrieval.** Argued
  independently by the GraphRAG survey (§6.2.4 tradeoff analysis) and CatRAG
  (explicit latency-based rejection of iterative refinement).
- **Static graphs as an open problem.** Named directly by the survey (§10.1).
  CatRAG engages with a version of it, but along a different axis (query-time
  weighting rather than scenario-time topology change).
- **LLM as identity verifier, not extractor.** Vrittanta-EN's event
  extraction, Amalvy & Labatut's note on generative models, and BookCoref's
  mention verification each reach for an LLM to verify identity over entities
  that were *already extracted*, not to extract new relations. The recurrence
  across unrelated sources led to one explicit project-wide decision rather
  than three ad hoc calls (see [`v2-decisions.md`](v2-decisions.md), decision 1).

---

## Identified but not read or unverified

Sources named in the project plan. Reading is not recorded for any of them, and
none should be treated as a real reference until verified.

| Source | Note |
|---|---|
| Visser Solissa, event-detection survey | Identified for the events thread. Reading not recorded. |
| PASTA | Identified as the most relevant grounding for modeling participant state change from a removed event (simulation design). Reading not recorded. |
| Coulet et al. (PHARE) | Likely a domain mismatch (biomedical ontology). Verify relevance before assigning any use. |
| "sentiment-fiction-seq" | Existence as a citable source not confirmed. |
| Tsutsui, *Resolving the Canon* | Cross-book entity merging is deliberately out of scope (entities are per-book scoped); reference only if a specific justified use arises. |
