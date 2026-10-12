# Architecture and Design Decisions

How NIE is built, why each choice was made, and which alternatives lost. For
measurements behind these choices see [`data-findings.md`](data-findings.md)
and [`benchmarks.md`](benchmarks.md). For the chronological decision record see
[`v2-decisions.md`](v2-decisions.md).

Contents: [Design constraints](#design-constraints) · [Pipeline](#pipeline) ·
[Graph layer](#graph-layer) · [Temporal layer](#temporal-layer) ·
[Embedding layer](#embedding-layer) · [Retrieval](#retrieval) ·
[Resolution layer](#resolution-layer) · [Event model](#event-model-planned) ·
[Answer generation](#answer-generation) · [API and frontend](#api-and-frontend) ·
[Simulation](#simulation-planned) · [Alternatives considered](#alternatives-considered)

---

## Design constraints

These constraints bind every design choice.

1. **Dataset-first.** For books in ARF, the dataset's entities and relations are
   the source of truth. There is no relation extraction, no model training or
   fine-tuning, and the LLM never invents graph structure.
2. **The LLM phrases and narrates; it does not reason.** The answer prompt
   forbids chaining two separate facts into an unsupported conclusion.
   Counterfactual simulation must be graph-algorithmic (node or event removal
   with reachability and centrality changes); the LLM only narrates computed
   results.
3. **Bounded LLM use for identity.** The one approved extension: an LLM may act
   as a verifier over *existing* candidate entities (identity judgments), never
   to create entities or relations.
4. **No added complexity before a measured need.** No new framework or library
   (including LangChain or LangGraph) is adopted before a measured bottleneck
   justifies it.
5. **Non-destructive layers.** The raw graph is never mutated. Filters and
   resolution decisions live in separate maps that retrieval opts into, so a
   wrong decision is a metadata edit rather than graph corruption.
6. **Decisions rest on data or papers, and are verified first.** Library
   behavior, platform terms and paper details are checked before building on
   them.

---

## Pipeline

```
ARF dataset
  -> entity canonicalization
  -> knowledge graph (per-book MultiDiGraph)
  -> temporal layer (narrative-position bins)
  -> relation-level embeddings (ChromaDB)
  -> hybrid retrieval
       vector search
         -> graph enrichment (all edges for each matched pair)
         -> query-direction detection (annotation only)
         -> chain expansion (typed, direction-aware traversal)
         -> resolution layer (exclude/redirect unreliable entity names)
  -> LLM phrasing -> cited answer
```

Stack: Python 3.12, pandas, NetworkX, NumPy, Sentence Transformers, ChromaDB,
FastAPI, Docker, Groq for the LLM step. Entity resolution adds an offline
dependency, `fastcoref`, only for exploration (see
[`v2-entity-resolution-findings.md`](v2-entity-resolution-findings.md)).

| Directory | Responsibility |
|---|---|
| `graph/` | Canonicalization, graph construction, corpus assembly, relation ontology filtering, traversal |
| `temporal/` | Narrative-position binning, trajectory queries, temporal phrase parsing |
| `embedding/` | Relation-to-text templating, embedding pipeline, ChromaDB vector store |
| `retrieval/` | Hybrid search, query-direction detection, answer generation |
| `resolution/` | Pronoun/generic filter, surface-variant merge, corpus resolution map |
| `evaluation/` | Benchmark question generation and evaluation |
| `api/` | FastAPI app, schemas, static frontend |
| `scripts/` | Build pipeline, benchmark runner, data loading, diagnostics |
| `visualisation/` | Benchmark plots |

Key modules: `graph/canonicalization.py` (`normalize_entity_name`),
`graph/build_graph.py`, `graph/corpus.py` (`build_corpus_graphs`, `load_corpus`),
`graph/relation_ontology.py`, `graph/traversal.py`, `embedding/relation_text.py`,
`embedding/embed_relations.py`, `embedding/vector_store.py`, `temporal/binning.py`,
`temporal/trajectory.py`, `temporal/phrase_parsing.py`,
`retrieval/hybrid_search.py`, `retrieval/direction_detection.py`,
`retrieval/answer_generation.py`, `resolution/pronoun_filter.py`,
`resolution/surface_variant_merge.py`, `resolution/corpus_resolution.py`,
`resolution/resolve.py`.

---

## Graph layer

| Decision | Choice | Why | Alternative rejected |
|---|---|---|---|
| Node identity | `(book_id, normalized_entity_name)`, scoped per book | The same name in different books (two unrelated "Tarzan"s) must not collapse | Global merge across books (cross-book merging stays out of scope) |
| Graph type | `MultiDiGraph` | Measured: one pair has 90 parallel relation instances; 141 of 421 pairs in book 106 repeat | `DiGraph`, which silently collapses instances and destroys frequency signal |
| Node attributes | `entity_type`, `surface_forms` (set of raw strings) | `surface_forms` supports display | none |
| Edge attributes | `relation` (raw string), `chunk_id` | Provenance for every fact | none |
| Persistence | `pickle` | GML and GraphML cannot hold the set-typed `surface_forms`; confirmed by failure. Trade-off: Python-only and unsafe on untrusted input, acceptable because only self-generated files are loaded | GML / GraphML |
| Canonicalization scope | Lowercase, strip whitespace, strip a trailing appositive clause | Mechanical and high-precision; zero collisions on book 106 | Fuzzy matching (`difflib`), rejected for false positives on short strings |
| Non-ontology relations | Not normalized; opt-in `is_canonical_relation()` filter; temporal and embedding pipelines default to `canonical_only=True` | No safe mechanical mapping for the 850+ free-text strings; inventing one injects judgment into ground truth | Mapping the long tail onto the 48 types |

`get_relationships_between()` is a pure graph-edge lookup returning every edge
between two entities in true stored direction, both directions included. It
sits with graph queries, not with the temporal code, because it has no temporal
logic.

---

## Temporal layer

- **Binning** adopts the dataset authors' percent-of-book method with one
  verified deviation (`chunk_id - min_chunk_id`); see
  [`research-notes.md`](research-notes.md#relational-arcs--christou--tsoumakas-2025).
- **`relationship_trajectory()` returns a dense dict** (every bin `1..N`
  present, zero-filled). The sparse `Counter` version was a footgun for callers
  who forget `.get(b, 0)`.
- **Direction-agnostic pairwise lookups** (`tuple(sorted((u, v)))` matching),
  because symmetric relations are stored inconsistently in the source.
- **Query-time, not precomputed.** No caching of trajectories. Revisit only if
  retrieval latency becomes a measured problem.
- **`build_temporal_index()`** precomputes per-book `min_chunk_id`,
  `max_chunk_id` and `num_bins` once.
- **`most_active_pairs_in_bin()`** was cross-validated against
  `relationship_trajectory()` on real data (17 instances for Tarzan–Taug in
  bin 1, both ways). `book_trajectory()` and `weighted_mean_bin()` summarize
  whole-book activity.
- **Phrase parsing** (`temporal/phrase_parsing.py`): `parse_temporal_phrase()`
  maps relative position phrases ("near the end of the book", "in the first
  third", "two-thirds of the way through", "the second half") to
  `{start_frac, end_frac}`, and `resolve_to_bins()` maps a fraction to a bin
  range for a book's bin count. Non-temporal phrasing ("what if the hero died
  in the second battle") deliberately returns no match rather than guessing.
  Type normalization is done at the module boundary: `resolve_to_bins()`'s
  `min(num_bins, start_bin)` preserves the smaller argument's type, so a numpy
  integer leaked out when clamping hit `num_bins`. It is fixed in the module,
  not the caller, because the function is public and a pandas caller would
  plausibly pass `np.int64` too.

---

## Embedding layer

**What to embed.** Options were raw text chunks, synthesized relation-level
sentences, or both. Relation sentences were chosen first: embedding raw chunks
would rebuild plain vector RAG, the baseline the project benchmarks against,
before validating anything the graph informs. Moving to "both" is conditional on
relation sentences proving insufficient (not triggered).

- **Templating.** `relation_to_sentence()` converts `(entity1, entity2,
  relation)` to natural language. Hand-written grammatical templates
  (`MANUAL_TEMPLATES`) cover relation types with irregular phrasing
  (father/mother/child, `owns`/`owned_by`), with directions cross-checked against
  the ARF paper's examples. A generic fallback covers the rest. A fallback bug
  (a hardcoded `"is"` produced `"Goku is travels by Nimbus cloud"`) was fixed by
  dropping the `"is"`; verb-style relations read correctly, noun-style fallbacks
  read slightly stiffer, which is acceptable because noun-style ontology
  relations are all templated. `used_by` is deliberately not specially handled
  (source noise).
- **Model.** `all-MiniLM-L6-v2`, 384 dimensions, fast on CPU, standard for this
  scale. Swappable if retrieval quality proves insufficient (not yet needed).
  Model load (about 3 minutes, once) is split from encoding (about 19 minutes
  for the corpus, about 145 sentences/second) via `load_embedding_model()` and
  `embed_records(records, model)`, after the first version reloaded the model on
  every call.
- **Deduplication** of exact repeats applies to embedding input only; the graph
  stays faithful to raw ARF. Embeddings are persisted to
  `data/embeddings/relation_embeddings.pkl` (git-ignored, regenerable).
- **Vector store.** ChromaDB `PersistentClient`, one collection
  (`arf_relations`). Inserts are batched (`add_records`, default 5,000) to stay
  under ChromaDB's maximum batch size.
- **The graph/embedding canonicalization seam.** `build_embedding_records()`
  originally stored *raw* entity names in metadata (`"Taug"`) while graph nodes
  use *canonicalized* names (`"taug"`). Every hybrid graph lookup silently
  returned an empty list, with no error, because two pipelines read the same
  source rows without sharing canonicalization and the seam was never exercised
  until hybrid search joined them. Fixed by canonicalizing entity names before
  storing metadata (metadata is for machine lookup; the display text keeps raw
  names). It required a full re-embed and re-ingest. A regression integration
  test was added at the time for this class of bug, which neither module's unit
  tests could catch (build the graph and the embedding records from the same
  source rows, then assert every embedded entity name resolves as a graph node).
- **Retrieval sanity check.** The query `"who protects Taug"` surfaces `"Taug is
  a protector of Teeka"` as the closest match (distance 0.425) despite different
  wording, showing the embedding captures "protects" ≈ "protector of". The top
  match is **direction-wrong**: it answers who Taug protects, not who protects
  Taug. Embeddings capture topical similarity, not logical direction, and this
  is the measured motivation for the graph half of hybrid retrieval.

---

## Retrieval

`hybrid_search()` runs vector search, then enriches each hit with the
**complete** graph-verified relationship set for its entity pair, not only the
relation that matched semantically. The vector layer's job is narrowed to "find
relevant entities"; the graph states the facts. Each fact is annotated, never
filtered, with `query_direction_match` (`True`, `False`, or `None`). Results are
returned as `EnrichedHit` objects carrying `all_relationships` and, when
multi-hop expansion is requested, `chains` (`EnrichedHit.chains`). A mismatch
means a fact does not directly answer the query in the asked direction, not that
it is wrong; whether to show, hide or deprioritize it is left to the consumer.

### Query-direction detection (`retrieval/direction_detection.py`)

Determining which role a free-text query intends for an entity ("who protects
Taug" vs "who does Taug protect") was deferred in v1 and built in v2 after three
approaches were tried in order.

| Approach | Outcome |
|---|---|
| Cosine similarity between query and candidate phrasings | Rejected. The two phrasings of a relation share nearly identical word sets and embeddings are weak on word order; a word-vector-averaging model gave identical scores for both directions on every test case. |
| General-purpose dependency parser | Rejected. General parsers misparse this corpus's invented proper nouns (`Taug` parsed as a noun compound), the weakness the coreference literature predicts for general NLP tools on literary names. |
| Locate the known entity relative to the relation's own verified phrasing (`MANUAL_TEMPLATES`), via an exact anchor phrase with a verb-form fallback | **Adopted.** Deterministic; returns `None` rather than guessing wrong. |

Rules and guards added from testing and real use (each closed a specific
failure):

- Verb forms are **hand-verified**, not derived. A mechanical `-er`/`-or` strip
  produced `moth`, `ment` and `lov`; `ment` collided with "mentioned" and
  "sentiment".
- `MIN_ANCHOR_LENGTH = 5`: `travel_to`'s anchor is `"to"` and matched any query
  containing that word. Every other anchor is 7+ characters.
- **Word-boundary entity matching**: `"An"` was matching inside `"Ann"`.
- **Article variants**: 15 of 31 templates use "a" or "an", but "the X of Y" is
  equally natural and was missed.
- **Gendered synonyms** (`NOUN_SYNONYMS`): husband/wife for `spouse_of`,
  son/daughter for `child_of` and later `parent_mother_of`/`parent_father_of`,
  brother/sister for `sibling_of`.
- **Modifier tolerance** (0–2 inserted words) requires a trailing `of`, because
  unconstrained gaps false-matched idioms ("mother ship", "father statue").
- `father` and `mother` are excluded from the verb fallback (collisions with
  idioms such as "founding father").
- **Possessives** ("Taug's companion"; `_possessive_noun_pattern` and
  `_find_possessive_direction`) have a *fixed* direction (the possessor
  ends up in the role the anchor noun does not name) and require a real boundary
  after the noun ("Taug's mother tongue"). The possessor match tolerates 0–2
  trailing words before `'s`, so `Harold Transome's` matches the node `harold`.
  Known and accepted: a coordinated possessor ("Taug and Akut's mother") would
  misattribute.
- `entity_to_expand_from()` returns `None` when direction is undetermined
  (it previously defaulted silently to `entity2`, the root cause of the "Esther
  Lyon's husband" wrong-chain finding).
- `target_relation(query)` returns the single relation the query ultimately asks
  about. Of-genitive chains read **leftmost** (the target is named first),
  possessive-only chains read **rightmost** (the target comes last), and any tie
  declines. A silent dict-insertion-order tie-break had produced a confidently
  wrong `parent_father_of` for questions that never mention a father.
- `mentioned_relations()` is the single source of truth for "what did this query
  ask about", consumed by both hop-depth estimation and chain filtering so they
  cannot drift apart.
- **Known design correction (not yet applied):** the assumption that the
  possessor is always the wanted role is false for `son`/`daughter` on
  `parent_mother_of`/`parent_father_of`, which name entity2's slot. The fix is an
  explicit `{relation: {noun: role}}` table (drafted as `ROLE_NOUNS`), not
  position inference; it is not yet wired into retrieval.

### Chain expansion (`graph/traversal.py`, `retrieval/hybrid_search.py`)

| Choice | Detail |
|---|---|
| Non-parametric, fixed-depth, single pass | Wires the BFS-style traversal directly in, not an LLM-agent loop (precedent: GNN-RAG; see research notes) |
| Direction-agnostic only for symmetric relations | Reverse traversal is enabled for exactly the seven confirmed symmetric relation types. Broad reverse traversal (all 48) was tried first and scoped down on measurement. |
| Typed traversal | `allowed_relations` restricts edges to relations the query mentioned. Unconstrained traversal from a hub (a 657-degree node) returned 100 chains with none touching the target relation. |
| Parallel-edge dedupe | Candidates are collapsed with `dict.fromkeys`; parallel multi-edges had spent most of `max_samples` on repeats. |
| Hop budget | `estimate_hop_depth()` counts *distinct* relation types mentioned (known undercount: "the companion of the companion of X" counts as 1). A one-hop bump applies when expansion starts from entity1 or the matched relation is symmetric, because the first hop would otherwise re-traverse the matched pair's own edge. `_effective_hop_depth` is an importable function so diagnostics reuse the exact computation. |
| `select_chains()` | The chain-filter sequence is a named function, not inline code. |
| Pair exclusion | A chain is excluded as a restatement only when it is a pure 2-node chain (`len(path) == 2`). Excluding by answer identity against the matched pair's second entity dropped correct multi-hop answers that happened to coincide with it. (Verified structurally, not by a run across multiple cases; see [`v2-decisions.md`](v2-decisions.md), decision 49.) |
| Terminal answer | `_terminal_answer` is role-aware for symmetric relations; for non-symmetric terminal edges it returns `path[-2]`, a node the walk has already passed. This is the suspected cause of a measured class of wrong answers (see findings) and has no fix yet. |
| Pronoun and generic answers | Computed chain answers are checked against `is_pronoun_generic` independently, as a second guard. The saved map does contain pronoun-tier entries (book 40882: 110 `surface_variant`, 100 `excluded_pronoun_generic`, 97 `ambiguous_variant_candidate`), but with maps off (the API default) nothing else blocks them. |
| Endpoint gate | The resolution-map filter on path endpoints was removed after measurement showed it excluded real answers. The change passes tests and is **not yet measured**. |

Alternatives that lost: a hub degree cap (hub skew was measured but never shown
harmful; see decision 8), CatRAG-style dynamic edge weighting (does not transfer
to exact BFS or to scenario-time topology change), and dual-entity expansion
(see below).

**Dual-entity expansion was built and rejected.** Traversing from both entities
of the matched pair and ranking by terminal relation looked like a cheap hedge
against single-entity brittleness. Five iterations, each fix surfacing a new
bug, ended at 1 correct chain of 33. The decisive gap: nothing enforces that a
chain traverses the *relation the matched fact already established* before
satisfying the query's outer relation, so 1-hop chains answered a different
question. Single expansion avoids this by construction, because direction
detection on the matched fact starts the search already past the established
relation. The starting side is determined, not unknown, so searching both sides
does not hedge, it risks answering a different question. Two pieces were kept:
the role-aware terminal-answer logic for symmetric relations and the answer
versus end field distinction.

---

## Resolution layer

A non-destructive layer in `resolution/` that holds a `resolution_map` (raw name
to resolved identity, tagged with tier). Retrieval opts into it; the graph is
never mutated. It was designed as one effort covering ambiguity, alias and
coreference, because the facets are not independent: coreference needs alias
merging first, or pronouns resolve to fragmented name variants, and
generic/collective entities cannot reuse the merge-into-one-node logic at all.

| Stage | Scope | Status |
|---|---|---|
| **Stage 0**: pronoun/generic filter (`pronoun_filter.py`) | Flags pronoun and generic-noun nodes (`is_pronoun_generic`, `build_resolution_map`, `is_excluded_from_composition`) so they cannot become answers or merge candidates | Built, wired in |
| **Stage A**: surface-variant merge (`surface_variant_merge.py`) | Honorific and article stripping, pairwise (non-transitive) token overlap, decline on ambiguity (2+ candidates), veto on generational or age suffixes | Built, wired in, **frozen** at its measured ceiling |
| **Stage B**: coreference expansion | Book-level windowed-then-grouped coreference with an off-the-shelf model; output tiered and never silently merged | Deferred |
| **Stage C**: hard aliases and generic/collective entities | Hard aliases flagged (`flagged_candidate`), never auto-merged; generic/collective entities represented as `instance_of` edges from a mechanical heuristic, not node merges | Deferred |

Why Stage 0 came before Stage A: the first measurement attributed 58% of
confirmed fragmentation to pronoun/generic names and 9% to surface variants.
At full corpus scale the mix is 47.1% and 19.6% (see
[`v2-entity-resolution-findings.md`](v2-entity-resolution-findings.md)); Stage 0
remains the larger share, so the ordering stands.

Stage A's design history is the reason for each rule: union-find transitivity
produced a 707-member cluster, so matching is pairwise; "longest string wins"
mis-selected a canonical form, so ambiguity declines; shared `young`/`old`
modifiers false-merged different people, so a suffix veto exists. The *lateral*
case (two different modified names matching on the shared modifier alone) is
not closed. Identity that depends on narrative discourse ("poor man", Jacob
versus Jacob Jr.) is not solvable by token overlap regardless of rule
refinement; further patching would be minor fixes to a strategy at its ceiling.

**Integration state.** `find_paths_up_to_hops` accepts an optional
`resolution_map`; `hybrid_search` takes per-book `resolution_maps`, applies
`resolve_canonical` to computed answers, and declines chain expansion only when
direction detection fails, not when the start entity merely has an unresolved
alias status (an over-broad first version discarded whole hits). `api/main.py`
loads `corpus_resolution.pkl` at startup with a graceful fallback if absent. A
`USE_RESOLUTION` toggle in `api/main.py` was proposed as a stop-gap; whether it
is applied is unconfirmed. On the correctness yardstick the layer currently
**lowers** accuracy; see [`benchmarks.md`](benchmarks.md#resolution-layer-ab).

The offline/online split: `resolution_map` is precomputed offline and consumed
(not generated) by the live API, the same shape as `scripts/build_pipeline.py`
versus `api/`. Heavy resolution dependencies therefore never need to coexist
with the serving environment.

**Approved decisions that govern this layer:**
- An LLM may be a bounded verifier over existing candidates, never a creator
  of entities or relations; the `instance_of` edges stay mechanical regardless.
- Coreference uses a pretrained off-the-shelf model, not fine-tuned or built
  in-house unless a later evaluation shows it is necessary. The specific model
  is not selected, and the choice is secondary to building windowing first.
- Evaluation is extrinsic first: ARF has no entity-resolution ground truth, so
  accuracy is compared before and after resolution on the existing benchmarks,
  falling back to small manual annotation only if that signal is too noisy.
- PER entities remain the primary target.

---

## Event model (planned)

Counterfactual questions ("what if the hero died in the second battle") need an
event to remove, and the graph has none: events exist only as edge labels.
Design (settled in principle, implementation pending), mechanical-first and
non-destructive like the resolution layer:

1. **Tier 1: event-shaped relations**, direct edge reification, gated *per
   relation type* after checking the data rather than blanket promotion.
   `captured_by`/`captures` stay with a participant-type-tolerant schema and
   three exceptions routed to review; `attacks` is a distinct event subtype
   (actor and target location), not a person-harm schema; `kills` and
   `married_to` go to review given their measured failure rates.
2. **Tier 2: EVNT-typed entities** in a tiered `event_candidate` map: mechanical
   exclude (structural artifacts, bare pronouns), then flagged but not excluded
   (creative-work verbs, strings tagged with a different type elsewhere in the
   same book), then `needs_review` (tractable at single-book scope).

Open: generic `involved_in` versus role-differentiated edges (`victim_of`,
`perpetrator_of`, `actor_of`, `target_of`); whether the original binary relation
edge is kept alongside an event node; whether one captor with two captives in
the same chunk is one event or two. Event-node implementation is planned after
entity resolution, because the EVNT tiering needs canonicalized names. No new
extraction is planned; see
[`v2-events-findings.md`](v2-events-findings.md).

---

## Answer generation

`retrieval/answer_generation.py` hands retrieved facts to an LLM with explicit
instructions not to chain or infer beyond what is stated, and to say plainly
when the question cannot be answered from them. Facts are treated as isolated
unless one states the connection. This was added after a real failure: the
2-hop question "who is the protector of the friend of the knight" first produced
a plausible but unsupported answer.

- **Provider:** Groq, `openai/gpt-oss-20b`, chosen for free-tier capacity and
  speed on a low-complexity phrasing task. gpt-oss models spend output tokens on
  an internal reasoning trace by default, so a small `max_tokens` can consume
  the whole budget and return empty content with no error. Fixed with
  `reasoning_effort="low"` and a larger budget; the raw response is logged if
  content is ever empty.
- **`temperature=0`.** The v1 default of 0.2 was never revisited. With identical
  retrieved facts, one question flipped between "cannot be determined" and an
  unhedged wrong inference ("the lawyer who manages the estate... is Lawyer
  Jermyn") on roughly half of trials. After the change, retrieval stayed stable
  and LLM stability on identical facts rose from 1 of 11 questions to 10 of 11;
  the remaining case differed only in cosmetic wording.
- **Open gaps** (from a review of the module): `_chain_line` rebuilds each chain
  from `path`, `relations` and `directions` and never reads `chain["answer"]`, so
  the computed answer never reaches the LLM. A recommendation to surface it was
  withdrawn because `_terminal_answer` can return an already-passed node. The
  prompt describes chains as pre-verified, complete evidence, but retrieval only
  guarantees that the path exists and the last edge has the right type. The
  prompt has no handling for contradictory facts, and fact sets for hub entities
  are never truncated. Source contradictions (see
  [`data-findings.md`](data-findings.md#bidirectional-parentage-contradictions))
  can therefore reach the LLM unflagged.

---

## API and frontend

FastAPI app with three endpoints: `GET /health`, `GET /books`, and
`POST /query` (book id and question in; answer and cited sources out, including
`chunk_id` provenance per fact). `ChainFact` carries the `answer` field (it was
computed by the backend but silently dropped before reaching the response until
it was added to the schema). The single-page frontend (`api/static/index.html`)
is a deliberately simple card-catalog-themed page with no build step or
framework, styled around the project's differentiator: cited, graph-verified
facts rendered as ink-stamped citation marks. Two files were never
covered by the consumer-review pass: `graph/traversal.py` and
`api/static/index.html`. Deployment is covered in
[`deployment.md`](deployment.md).

---

## Simulation (planned)

Counterfactual simulation is graph-algorithmic: remove a node or event,
recompute reachability and centrality changes, and let the LLM narrate the
result without deciding what changes. The survey's static-graph gap means there
is no existing recipe. Evaluation is itself a design problem because there is no
ARF-style ground truth for counterfactuals; chain-completeness metrics from the
CatRAG reading are the intended starting point. The design depends on the event
model and entity resolution landing first. See [`roadmap.md`](roadmap.md).

---

## Alternatives considered

| Area | Chosen | Rejected, and why |
|---|---|---|
| Graph type | `MultiDiGraph` | `DiGraph`: collapses 90 parallel instances |
| Serialization | `pickle` | GML/GraphML: cannot hold `set` attributes |
| Embedding target | Relation sentences | Raw chunks: rebuilds plain vector RAG |
| Alias merging | Mechanical, decline on ambiguity | Fuzzy matching: false positives on short strings; union-find: transitive over-merging |
| Direction detection | Anchor phrase + verb form | Cosine similarity (word-order blind); dependency parser (misparses invented names) |
| Reverse traversal | Seven symmetric relations | All 48 relations: 3.5–4× reachable-set growth and the same skew, with a broader claim than the data made |
| Chain expansion | Single expansion from the entity the query asks about | Dual expansion: no relation-sequence enforcement |
| Hub handling | None; skew logged, not treated as harm | Degree cap: harm never shown, and it would need its own accuracy validation |
| Event structure | Reify event-shaped relations + tiered candidate map | LLM-prompt event extraction: creates structure ARF never provided |
| Community summaries (GraphRAG) | Not used | Targets query-focused summarization; no such query shape here |
| Dynamic edge weighting (CatRAG) | Not used | Addresses static-across-queries graphs, not scenario-time topology |
| Hosting | Self-hosted Docker plus tunnel, on demand | See [`deployment.md`](deployment.md) |
| Frameworks | None added | LangChain/LangGraph: no measured bottleneck justifies them |
