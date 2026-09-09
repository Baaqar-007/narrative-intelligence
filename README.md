# Narrative Intelligence Engine (NIE)

A temporal graph-augmented retrieval system for fictional narratives.

Version 1 builds a knowledge graph, a temporal (narrative-order) layer, and a
hybrid graph + vector retrieval pipeline over the **Artificial Relationships
in Fiction (ARF)** dataset. It does **not** perform relation extraction — ARF
already provides entities and relationships; this project focuses on graph
construction, retrieval, and grounded question answering.

Version 2 introduces narrative simulation and counterfactual
reasoning — "what if X happened differently" answered via graph
structure, not LLM inference. Phase 1 (research) is complete; Phase 2
(build) has not started. Research findings
and decisions: `docs/research-notes.md`.

## Status

**Version 1**
- Week 1 (Knowledge Graph) — complete.
- Week 2 (Temporal Layer) — complete.
- Week 3 (Hybrid Retrieval) — complete.
- Week 4 (Deployment) — complete.

**Version 2**
- Phase 1 (Research, Weeks 1–5) — complete. See
   `docs/research-notes.md.md` for findings and
   decisions.
- Phase 2 (Build, Weeks 6–9) — not started.

## Architecture

```
Dataset -> Entity Canonicalization -> Knowledge Graph -> Temporal Layer
        -> Vector Embeddings -> Hybrid Retrieval -> LLM -> Answer
```

Stack: Python 3.12, Pandas, NetworkX, NumPy, Sentence Transformers,
ChromaDB, FastAPI (Week 4), Docker (Week 4). No relation extraction, no
model training or fine-tuning anywhere in the pipeline — the LLM never
invents graph structure; the ARF dataset is the sole source of entities
and relationships.

## Setup

Create and activate a virtual environment, then install the package and its dependencies:

```bash
python -m venv .venv
source .venv/bin/activate        # macOS/Linux
# .venv\Scripts\activate         # Windows (CMD)
# .venv\Scripts\Activate.ps1     # Windows (PowerShell)

pip install -r requirements.txt
pip install -e .
```

Run tests (optional):

```bash
python -m pytest tests/ -v
```

## Scripts

- `scripts/build_pipeline.py` — main data construction pipeline; internally calls `load_data.py`.
- `scripts/run_benchmarks.py` — evaluation pipeline for models and vector embeddings.

Run from the repository root:

```bash
python -m scripts.build_pipeline
python -m scripts.run_benchmarks
```

---



# Week 1 — Knowledge Graph

## Dataset (ARF)

Source: `Despina/project_gutenberg`, `synthetic_relations_in_fiction_books`
config, via HuggingFace `datasets`. Cross-referenced against the dataset's
own paper: Christou & Tsoumakas, *"Artificial Relationships in Fiction: A
Dataset for Advancing NLP in Literary Domains"* (LaTeCH-CLfL 2025).

- 95,476 rows, chunk-level: each row is one 5-sentence rolling window
  (1-sentence overlap) from a book, with 0+ GPT-4o-extracted relations.
- 96 books total, 128,331 total relation instances.
- Schema per row: `book_id, title, author, author_gender, author_birth_year,
  author_death_year, release_date, pg_subjects, topics, chunk_id, chunk,
  relations`.
- `relations` is a **Python-literal string** (`ast.literal_eval`, not
  `json.loads` — single quotes, not valid JSON), containing a list of dicts:
  `{entity1, entity2, entity1Type, entity2Type, relation}`.
- Entity ontology: 11 types (PER, FAC, LOC, WTHR, VEH, ORG, EVNT, TIME, OBJ,
  SENT, CNCP). **PER dominates**: 231,313 of ~256,700 entity-slot
  occurrences (>90%) — see "PER-only scoping" decision below.
- Relation ontology: 48 canonical types (paper Appendix C).

### Data cleaning findings

- **1 malformed row** (`book_id` field contained a truncated fragment of
  another row's `relations` string — an upstream parsing artifact in ARF
  itself, not our bug). Filtered via a `safe_parse_relations()` helper that
  distinguishes "genuinely empty" (`[]`) from "unparseable" (`None`), rather
  than crashing or silently coercing.
- **`chunk_id` is contiguous within-book in 19/20 sampled books** —
  validated as a usable proxy for narrative position. The one exception
  (book 5111) had explainable gaps, not corruption.
- **Book 74763 has 0 relations** across all 8 of its sampled chunks — a
  short work with no extractable relations, confirmed against the real
  chunk text, not a bug. Produces a valid empty graph; excluded from
  retrieval-ready book lists.
- Cleaned dataset saved to `data/arf_chunks_parsed.parquet`.

## Entity canonicalization (`graph/canonicalization.py`)

**Problem found:** raw entity strings within one book include real
aliasing/formatting noise. Investigated by hand on book 106 (Jungle Tales
of Tarzan, 279 unique raw strings). Found two *distinct* phenomena, not one:

1. **Appositive descriptors** — mechanical, high-precision pattern:
   `"Bolgani, the gorilla"` → same entity as `"Bolgani"`. Fixed with a
   regex (`,\s*the\s+.+$` stripped, then lowercased).
2. **Generic/collective entities** — `"apes"` vs `"the apes"` vs `"young
   apes"`. NOT resolved — these are a different *kind* of problem
   (collective references, not individual-character aliasing) and are
   explicitly out of scope for v1. **Known limitation, not fixed.**

`normalize_entity_name()`: lowercase, strip whitespace, strip trailing
appositive clause. Verified against real data: exactly 5 matches on book
106, zero false-positive collisions (checked explicitly — no two distinct
raw names collapsed onto the same canonical form).

**Not attempted:** nickname/title resolution (e.g. "Tarzan" vs "Lord
Greystoke"). A `difflib.SequenceMatcher` fuzzy-match diagnostic produced
mostly false positives on short strings (e.g. `('Buto','Gunto')` flagged
as similar despite being different characters) — confirmed this approach
isn't reliable enough to build on. Deferred.

## Knowledge graph (`graph/build_graph.py`, `graph/corpus.py`)

### Node identity
`(book_id, normalized_entity_name)` — entities are scoped **per-book**, not
merged globally. Same name in different books (e.g. two unrelated
characters both named "Tarzan") must not collapse into one node.

### Graph type: `MultiDiGraph`, verified necessary with data
Checked whether the same entity pair could have multiple relation
instances before choosing a graph type. Result: `('Tarzan','Taug')` alone
has **90 separate relation instances** in book 106; 141/421 pairs in that
book repeat at least once. A simple `DiGraph` would silently collapse
these into one edge, destroying frequency/intensity signal. `MultiDiGraph`
was earned by measurement, not assumed.

### Node/edge attributes
- Node: `entity_type` (PER/LOC/etc.), `surface_forms` (a `set[str]` of every
  raw string that canonicalized to this node — useful for display).
- Edge: `relation` (raw string), `chunk_id` (provenance).

### Corpus build
`build_corpus_graphs()` loops over all 96 books. Verified: 44,248 total
nodes, 128,331 total edges — **matches the dataset-wide relation count
exactly**, confirming no data lost or duplicated across the full build.
One outlier found and explained (book 74763, 0 edges — see above).

### Persistence: `pickle`, not GML/GraphML
Checked empirically, not assumed: `nx.write_gml()` cannot represent the
`set`-typed `surface_forms` node attribute (GML/GraphML support only
scalar attribute types). `pickle` was chosen after confirming this
failure directly. Trade-off: pickle is Python-only and unsafe to load
from untrusted sources — acceptable since we only load files we generate
ourselves; noted in `load_corpus()`'s docstring.

## Relation ontology filtering (`graph/relation_ontology.py`)

Found **1,127 unique relation strings** in the corpus against a 48-type
closed ontology. Investigated whether this was typo/casing drift (like the
entity-aliasing problem) or something else: **it's something else**. Top
48 relation types account for **97.5%** of all instances (125,081 /
128,331); the remaining 850+ distinct strings are mostly singleton
free-text phrases (`"screaming at"`, `"spared the life of"`, `"wept
like"`) — GPT-4o occasionally ignored the closed ontology and wrote
descriptive verb phrases instead. This matches the ARF paper's own
reported 2.95% relation-level ontology deviation rate almost exactly.

**Decision:** did not attempt to normalize the long tail — there's no safe
mechanical mapping (unlike the appositive-stripping case), and inventing
one would mean injecting our own judgment into what's meant to be
ground-truth data. `is_canonical_relation()` provides an opt-in filter;
raw edges are untouched in the graph itself (non-destructive). Temporal
and embedding pipelines default to `canonical_only=True`.

### `used_by` — a known, unresolved direction inconsistency in ARF itself
The ARF ontology defines `used_by` **twice** with different type-pair
directions (id 36: FAC→ORG; id 47: OBJ→PER), and the paper's own prose
example for id 47 appears inconsistent with its stated type order.
Checked against **real corpus data**: `used_by` instances show entity1 as
sometimes the user, sometimes the used object, inconsistently — e.g.
`{'entity1':'the blacks','entity2':'fire','relation':'used_by'}` (PER→OBJ)
alongside `{'entity1':'Excalibur','entity2':'King Arthur',...}` (OBJ→PER).
This is genuine source-data noise, not fixable by a smarter template.
Accepted as-is (~small fraction of instances); documented rather than
engineered around.

---

# Week 2 — Temporal Layer

## What "temporal" means for this dataset

ARF has no calendar dates — only `chunk_id` (per-book, contiguous in
19/20 sampled books) as an ordering signal. "Temporal" here means
**narrative position** (percent-of-book), not real-world time.

## Narrative-position binning (`temporal/binning.py`)

Found and read the dataset authors' own follow-up paper — Christou &
Tsoumakas, *"Relational Arcs as Narrative Structure: Dynamics,
Distribution, and Diachronic Change in Fiction"* (2025, same 96-book
corpus) — rather than inventing a binning scheme from scratch. Adopted
their **percent-of-book binning method**:

- Adaptive bin count: `N = clamp(total_relations / 15, 6, 20)` — sparse
  books get fewer/wider bins so each bin still holds enough events to be
  meaningful; dense books get up to 20 bins.
- Bin assignment: `k = floor((position) * N / total_span) + 1`.

**Deliberate deviation from the published formula**, verified necessary
with a constructed test case: the paper's formula assumes `chunk_id`
starts at 0. Our implementation uses `(chunk_id - min_chunk_id)` instead
of raw `chunk_id`, because ARF's per-book chunk *sampling* means
`chunk_id` doesn't always start at 0 for a given book's row subset. Proved
this matters, not just theoretically: a chunk 5 positions into an
883-chunk span landed in **bin 1** with the offset correction vs. **bin 3**
without it — a real, would-have-been-silent misclassification.

Explicitly did NOT adopt from the arcs paper (scope discipline, not
missed capability): relation-family collapsing (48→7 families),
change-point/turning-point detection, k-means arc-shape clustering. These
are the paper's own research contributions for literary analysis, not
infrastructure this system's retrieval needs.

## Temporal queries (`temporal/trajectory.py`)

- `build_temporal_index()`: precomputes per-book `min_chunk_id`,
  `max_chunk_id`, `num_bins` once, reused per edge (not recomputed
  per-lookup).
- `relationship_trajectory()`: relation-instance counts between two
  entities, per bin. **Returns a dense dict** (every bin `1..N` present,
  zero-filled) — a deliberate design choice made after finding the sparse
  version (`Counter`-only, missing keys for zero-count bins) was a
  footgun for downstream consumers who might forget `.get(b, 0)`.
- `most_active_pairs_in_bin()`: ranks entity pairs by activity within one
  bin. Cross-validated against `relationship_trajectory()` on real data —
  independently computed, agreed exactly (17 instances for Tarzan-Taug in
  bin 1, both ways).
- `book_trajectory()` / `weighted_mean_bin()`: whole-book (not
  pairwise) binned counts and a count-weighted mean bin position,
  summarizing whether a book's relational activity skews early, late, or
  even.
- **Direction-agnostic edge lookup**: all pairwise queries use
  `tuple(sorted((u,v)))` / `{u,v} == {a,b}` style matching, because Week 1
  already established relation direction is inconsistent for symmetric
  relation types (e.g. `companion_of` appears both directions for the same
  pair — confirmed on real data, not assumed).
- **Query-time, not precomputed** — deliberate choice. No caching/storage
  of trajectories. Revisit only if retrieval latency becomes a measured
  problem (deferred explicitly to v2/deployment).

### Known limitation
`relationship_trajectory()` cannot distinguish "no relationship exists"
from "entity name not recognized" — both return an all-zero dense
trajectory, verified by test. Acceptable while entity names are
graph-controlled; will need explicit validation once retrieval accepts
free-text entity references from user queries.

## Corpus-wide finding: activity distribution

Computed `weighted_mean_bin()` (normalized 0–1) across all 95/96 books
with relations. **Result: 89/95 books (94%) fall in the 0.4–0.6 "roughly
even" band; corpus mean = 0.531.** This is a real, non-obvious finding:
book 106 (used throughout early development) is **not representative** —
it shows unusually clustered early/late activity with a sparse middle,
while most books distribute relational activity roughly evenly across
the narrative. This validates that narrative-position retrieval queries
should be meaningful across most of the corpus, not just the
development book.

## NetworkX bugs found and fixed this week
- `graph.edges(u, v, data=True)` is **not** valid syntax for "edges
  between u and v" — `.edges()`'s first positional arg is `nbunch` (a
  node filter), not a two-node pair. Correct pattern:
  `graph.edges(nbunch=[a,b], data=True)` filtered by `{u,v} == {a,b}`.
- A notebook loop variable named `graph` (`for book_id, graph in
  corpus.items()`) silently shadowed an earlier `graph = corpus["106"]`
  cell — a real, generalizable notebook footgun (loop variables persist
  and leak into global scope after the loop ends). Fixed by always
  indexing explicitly (`corpus["106"]`) rather than relying on a bare
  variable that might have been reassigned by any earlier-run cell.

---

# Week 3 — Hybrid Retrieval

## Embedding text generation (`embedding/relation_text.py`)

**Design question:** what to embed? Considered (1) raw text chunks, (2)
synthesized relation-level sentences, (3) both. Chose **(2) first**,
deliberately, reasoning that embedding raw chunks first would just
rebuild plain vector RAG — the baseline we intend to benchmark against —
before validating anything the graph actually informs. Move to (3) only
if (2) proves insufficient (not yet triggered).

**Templating:** `relation_to_sentence()` converts `(entity1, entity2,
relation)` into natural language.
- 32 hand-written grammatically-correct templates (`MANUAL_TEMPLATES`)
  for relation types needing irregular phrasing (father/mother/child,
  owns/owned_by, etc.) — cross-checked several against the ARF paper's
  own Appendix C example sentences to verify direction (e.g. `owned_by`:
  entity1 = thing owned, entity2 = owner, confirmed against the paper's
  "Thornfield Hall is owned_by Mr. Rochester" example).
- Generic fallback for everything else (remaining ontology types +
  non-canonical free-text relations).
- **Bug found and fixed during testing:** the fallback originally
  hardcoded `"is"` before the relation phrase, producing broken output
  for verb-style relations — e.g. `"travels_by"` → `"Goku is travels by
  Nimbus cloud"` (double-verb). Fixed by dropping the hardcoded `"is"`;
  verb-style relations now read correctly (`"Goku travels by Nimbus
  cloud"`), at the cost of noun-style fallbacks reading slightly stiffer
  without an article (acceptable — all noun-style ontology relations are
  already covered by `MANUAL_TEMPLATES`).
- `used_by` explicitly **not** specially handled (see Week 1 finding
  above) — accepted as known source-data noise.

## Embedding pipeline (`embedding/embed_relations.py`)

- Model: `all-MiniLM-L6-v2` (Sentence Transformers) — 384-dim, fast on
  CPU, standard choice for this scale of semantic search. Swappable later
  if retrieval quality proves insufficient (not yet needed).
- **Deduplication finding:** some chunks contain the *exact same* relation
  dict repeated many times (up to **35x** in one real case — a passage
  about "his mother" with no textual repetition, apparently a GPT-4o
  extraction artifact producing duplicate extractions of one underlying
  fact). Decided to deduplicate exact `(entity1, entity2, relation)`
  repeats **within a chunk** before embedding (graph itself stays
  untouched/faithful to raw ARF — this dedup applies only to the
  embedding pipeline's input).
- **ID scheme**, verified collision-free by direct check before use:
  `book_id_chunk_id_entity1_entity2_relation`, with an `occurrence` suffix
  for any residual duplicates (rare — checked 99 cases across the full
  corpus, nearly all explained by pronoun/generic-reference repeats like
  "my uncle" appearing verbatim twice in one chunk; the dedup step above
  eliminates the exact-repeat case, the occurrence suffix is a safety net
  for anything it doesn't catch).
- Full-corpus run: **128,190 records** after dedup (128,331 raw canonical
  instances minus duplicates) — cross-validated against an independently
  computed unique-key count from the same investigation, exact match.
- Model load (~3 min, one-time) split from encoding (~19 min for the full
  corpus, ~145 sentences/sec) via `load_embedding_model()` /
  `embed_records(records, model)` — refactored after discovering the
  original version reloaded the model on every call.
- Persisted to `data/embeddings/relation_embeddings.pkl` (not tracked in
  git — regenerable).

## Vector storage (`embedding/vector_store.py`)

ChromaDB, `PersistentClient`, one collection (`arf_relations`). Batched
inserts (`add_records`, default batch size 5,000) to stay under ChromaDB's
internal max-batch-size limits on a single `.add()` call.

**Critical bug found and fixed:** `build_embedding_records()` originally
stored **raw** (non-canonicalized) entity names in metadata (`"Taug"`),
while graph nodes are keyed by **canonicalized** names (`"taug"`) from
Week 1. Every hybrid-retrieval graph lookup silently returned an empty
relationship list — no error, just wrong (empty) results — because the
two pipelines (graph-building, embedding-building) independently read the
same source rows without sharing canonicalization, and this seam was
never exercised until hybrid search actually joined them. Fixed by
canonicalizing `entity1`/`entity2` before storing as metadata, while
keeping raw names in the *display text* (different purposes: metadata is
for machine lookup, text is for human reading). Required a full
re-embedding + re-ingestion. Added a regression **integration test**
(`tests/test_hybrid_integration.py`) that builds a graph and an embedding
record set from the same source rows and asserts every embedded entity
name resolves as a real graph node — the specific class of bug that unit
tests of either module alone couldn't catch.

**Retrieval validated against ground truth:** query `"who protects
Taug"` correctly surfaces `"Taug is a protector of Teeka"` as the closest
semantic match (distance 0.425) — despite different wording from the
stored sentence, confirming the embedding captures "protects ≈
protector of."

**Real limitation found via this same query:** the top match is
**direction-wrong** — it answers "who does Taug protect," not "who
protects Taug." Embeddings capture topical similarity, not precise
logical direction. This is the concrete, measured motivation for the
graph half of hybrid retrieval.

## Hybrid retrieval (`retrieval/hybrid_search.py`, `graph` query addition)

`get_relationships_between()` (pure graph-edge lookup, no temporal
logic — deliberately placed as a graph query, not folded into
`temporal/trajectory.py`) returns every edge between two entities, true
stored direction preserved, both directions included.

`hybrid_search()`: runs vector search, then enriches each hit with the
**complete** graph-verified relationship set for its entity pair — not
just the one relation that happened to match semantically. The vector
layer's job is narrowed to "find relevant entities"; the graph states the
facts.

### Deferred: query-side entity-role/direction detection
Determining which grammatical role a *free-text query* intends for an
entity (e.g. "who protects Taug" vs "who does Taug protect" — same
entities and relation type, opposite intended direction) is a real NLP
problem (dependency parsing or an LLM step), explicitly out of scope for
v1 per Principle 3 (no added complexity before it's proven necessary).
Current behavior: return facts in both directions, clearly labeled by
their stored `entity1`/`entity2` roles, and let the downstream LLM (final
pipeline stage) resolve intent from the original query text. Tracked in
`FUTURE_IDEAS.md` for revisiting before v2.

---

# Benchmarking

Ground truth for evaluation questions is generated directly from ARF's
own relation triples (e.g. `{Taug, protector_of, Teeka}` → "Who is
protector of Taug?" with a known correct answer) — no hand-labeling
needed. All three benchmarks below sample real relation/path instances
and check whether each system recovers the known-correct answer.

## Benchmark 1 — single-hop, entity-membership (initial, superseded)

First attempt: "does the correct entity name appear anywhere in the
top-k results." **Result: baseline and hybrid tied exactly (55.0% at
k=5).** Investigated rather than accepted at face value — confirmed via a
zero-mismatch check across all 200 questions that this metric genuinely
cannot detect hybrid's actual value-add (it doesn't check direction, and
with k=5 baseline already returns enough candidate names that enrichment
rarely adds a *new* name). This was a **benchmark design flaw**, not a
system failure — logged as a real, honest negative result, and replaced
with a sharper metric below rather than discarded.

## Benchmark 2 — single-hop, direction-aware (the real single-hop test)

Checks whether the result states the fact in the question's actually
correct direction (`entity1`/`entity2` order matches), not just whether
the right name appears somewhere.

| System | Accuracy |
|---|---|
| Vector-only baseline (top-1) | 33.5% |
| Hybrid (k=5) | 55.0% |
| Hybrid (k=10) | 69.0% |

**Root-cause check** (not assumed): of the 90 hybrid failures at k=5,
**0/90** were "entity found but wrong direction" — **all 90** were
"vector search never surfaced the entity pair at all." This means: **once
vector search finds the right entity pair, graph enrichment recovers the
correctly-directed fact 100% of the time.** The remaining gap is a pure
vector-search recall limitation, not a direction/enrichment failure.
Widening `k` from 5→10 recovered more than half of the original misses,
suggesting real, tunable headroom (at the cost of more entities to
enrich per query — a latency consideration for Week 4).

## Benchmark 3 — multi-hop reasoning (the strongest result)

Real 2-hop graph paths (`A --rel1--> B --rel2--> C`) sampled from the
corpus; question asks for `C` given only `A`. Tests whether each system
can **chain two facts**, which no single embedded sentence ever states.

| System | Accuracy |
|---|---|
| Vector-only (single query, k=10) | 26.0% |
| Graph traversal (2-hop BFS) | 72.0% |

This is a structural, not incremental, gap: vector search has no
mechanism to chain facts at all (the 26% is attributable mostly to
coincidental unrelated overlap, not real reasoning), while graph
traversal solves this by construction. This is the strongest evidence in
the project for why graph-augmented retrieval is worth the investment —
a capability plain vector RAG cannot replicate, not just does worse at.

**Known caveat, not yet quantified:** some correct answers are
pronoun/generic-reference entities (e.g. "his brother") rather than
canonicalized proper names — a byproduct of the Week 1 generic-entity
limitation resurfacing here. Unclear how much of the 72% relies on named
vs. pronoun-entity answers.

## Benchmark 4 — accuracy vs. hop count (methodological finding)

Attempted to sweep accuracy across hop depths 1–4. First version
(`evaluate_graph_hop_accuracy`) produced a suspicious, steep drop-off
(99%, 74%, 31%, 4%) that turned out to be a **real bug**, not a finding:
the traversal function returned only the *final BFS layer*, but a
DFS-sampled path of length N doesn't guarantee the true shortest-path
distance is also N — a node can be "3 hops away" via one path while
actually being reachable in 2 hops via another route, and the
final-layer-only check incorrectly treated that as unreachable. Confirmed
directly (`nx.shortest_path_length` on a real failing case: DFS path
length 3, true shortest-path distance 2). Fixed by accumulating all
visited nodes across hops, not just the final layer — corrected numbers
were 99%, 100%, 100%, 100%, but this version tests "does BFS rediscover a
path known to exist" (a correctness/sanity check on the traversal
implementation) rather than a real retrieval-capability trend.

**Rebuilt with proper single-answer n-hop questions** (one specific
correct endpoint per question, not "any node in the reachable set"):

| Hops | Vector-only baseline | Graph traversal |
|---|---|---|
| 1 | 21.0% | 99.0% |
| 2 | 12.0% | 100.0% |
| 3 | 16.0% | 100.0% |

**Honest methodological caveat:** the baseline query template used here
is generic and hop-count-invariant (not natural-language-optimized per
hop count), so absolute baseline values are **not directly comparable**
to Benchmark 2's better-phrased 33.5% figure — this is a confound
introduced by weaker question phrasing in this specific experiment, not
a real capability difference. What remains valid: the **within-experiment
trend**, using identical phrasing at every hop depth — baseline
accuracy drops from 21%→12% going 1-hop to 2-hop, consistent with
increasing difficulty of coincidental keyword/embedding overlap as chains
lengthen. The 3-hop uptick to 16% is most likely sampling noise at
n=100 questions per hop, not a genuine reversal, and is reported as such
rather than rationalized into a narrative.

## Benchmark 5 (reproduced via scripts/run_benchmarks.py)

### Single-hop direction-correctness vs. k
| k | Hybrid accuracy |
|---|---|
| 1 | 34.0% |
| 3 | 47.5% |
| 5 | 55.5% |
| 7 | 62.0% |
| 10 | 69.0% |
| 15 | 75.0% |
| 20 | 80.0% |

Consistent with the original exploratory finding (33.5%/55%/69% at
k=1/5/10) - confirms the result reproduces cleanly from a fresh,
from-scratch pipeline build, not an artifact of one development session's
state. Accuracy keeps climbing through k=20 with no sign of plateauing
yet, suggesting there's still real headroom in retrieval breadth beyond
what was explored earlier (latency tradeoff still applies).

### Accuracy vs. hop count
| Hops | Vector-only baseline | Graph traversal |
|---|---|---|
| 1 | 41.0% | 99.0% |
| 2 | 21.0% | 100.0% |
| 3 | 14.0% | 100.0% |

Rebuilt with natural chained phrasing at every hop depth (e.g. "who is
the enemy of the companion of Taug"), replacing the earlier generic,
hop-invariant template. This produces a clean, monotonically decreasing
baseline (41%->21%->14%) - confirming the earlier exploratory run's
noisy, non-monotonic numbers (21%/12%/16%, with an unexplained 3-hop
uptick) were a phrasing artifact, not a real property of the systems
being compared. The core finding holds and is now more cleanly evidenced:
vector search degrades sharply as fact-chaining requirements increase,
while graph traversal - which chains facts by construction - does not.

---

# Week 4 — Deployment

## The missing LLM step

Weeks 1-3 built retrieval up to structured facts (`EnrichedHit` objects) -
the pipeline's final step, `Hybrid Retrieval -> LLM -> Answer`, was never
built until this week. `retrieval/answer_generation.py` closes that gap:
retrieved facts are handed to an LLM with an explicit instruction not to
chain or infer beyond what's stated, and to say plainly when a question
can't be answered from the retrieved facts rather than guess. Verified
against a real failure case: a 2-hop question ("who is the protector of
the friend of the knight") initially produced a plausible-sounding but
unsupported answer, chaining two unrelated single-hop facts. Fixed by
making the prompt explicit that facts are isolated by default unless one
fact states the connection directly - re-verified against the same
question afterward.

**LLM provider**: Groq (`openai/gpt-oss-20b`), chosen for free-tier
capacity and speed on a low-complexity phrasing task. One real gotcha
found: gpt-oss models are reasoning-style models that spend output-token
budget on an internal reasoning trace by default: with a small
`max_tokens`, this can consume the entire budget before any visible
answer is produced, returning empty content with no error. Fixed via
`reasoning_effort="low"` and a larger token budget, with the raw response
logged as a fallback if content is ever empty again.

## API (`api/`)

FastAPI app, three endpoints: `GET /health`, `GET /books`, `POST /query`
(book_id + question -> answer + cited sources, including `chunk_id`
provenance per fact). A card-catalog-themed single-page frontend
(`api/static/index.html`) is served at `/` - deliberately simple (no
build step, no framework), styled around the project's actual
differentiator: cited, graph-verified facts rendered as ink-stamped
citation marks, not decoration for its own sake.

## Deployment: the actual path, including the dead ends

Worth documenting the real trail, not just the final answer, since most
of the effort here was in verifying platform claims rather than writing
code:

1. **Hugging Face Spaces** (originally planned, matches the project's
   original charter) - found, mid-build, that HF had recently locked
   both the Docker and Gradio SDKs behind a paid plan for new Spaces,
   with free accounts restricted to a GPU-burst tier (ZeroGPU) unsuited
   to an always-on, CPU-only service. Ruled out.
2. **Koyeb** - genuinely free, no card required, but a true (swap-
   disabled) memory test showed the stack does not fit in its 512MB
   free instance. Ruled out with a local test before attempting a real
   deploy.
3. **Modal** - no card required (OAuth-only signup), architecturally a
   good fit (usage-metered rather than a fixed memory ceiling) - but
   the actual free credit granted on signup was far smaller than
   multiple independent articles described, insufficient for
   meaningful uptime. Ruled out.
4. **Chosen approach: self-hosted Docker + Cloudflare Tunnel, on-
   demand.** Zero cost, no card, no platform dependency, and - the
   deciding factor over leaving it "always on" locally - no background
   resource cost between demos. The container and tunnel are started
   only when the project is being shown (e.g. for a review), and
   stopped after. Trade-off: the public URL is ephemeral (a fresh one
   generates each time via Cloudflare Quick Tunnels) rather than a
   fixed address - acceptable for a demo shown live, revisit with a
   named tunnel + domain if a permanent link is ever needed.

### Running the demo
```bash
docker build -t nie-api:local .
docker run -p 7860:7860 -e GROQ_API_KEY=your_key nie-api:local
# in a second terminal:
cloudflared tunnel --url http://localhost:7860
```
---

# Known limitations (full list)

1. **Generic/collective entities unresolved** — "apes" vs "the apes",
   "elephant" vs "the elephant" remain distinct nodes. Surfaced
   repeatedly: Week 1 canonicalization, Week 3's multi-hop benchmark
   caveat, hop-count bug investigation.
2. **No cross-alias/nickname resolution** — e.g. "Tarzan" vs "Lord
   Greystoke" not merged. A `difflib`-based fuzzy match was tried and
   confirmed unreliable on short strings (too many false positives).
3. **Relation directionality inconsistent for symmetric relation types**
   in the source data (e.g. `companion_of` appears both directions for
   the same pair) — handled via direction-agnostic queries in the
   temporal layer, but not "fixed" at the data level.
4. **Book 74763 has 0 relations** — real, explained, excluded from
   retrieval-ready book lists.
5. **1 malformed row** in raw ARF — filtered, source-side artifact.
6. **`relationship_trajectory()` can't distinguish "no relationship"
   from "unrecognized entity name"** — both return all-zero. Fine while
   entity names are graph-controlled; will need validation once
   free-text query entities are accepted.
7. **`used_by` relation direction is inconsistent in ARF's own generated
   data** (see Week 1) — accepted as source noise.
8. **Non-canonical (free-text) relation strings** (~2.5% of instances)
   are excluded from canonical-only queries by default, not normalized —
   no safe mechanical mapping exists.
9. **Query-side entity-role/direction detection** for free-text queries
   is not implemented — hybrid search returns both directions, labeled,
   rather than guessing user intent from grammar. Deferred to
   pre-v2 (see `FUTURE_IDEAS.md`).
10. **Benchmark 4's baseline uses a phrasing-weak query template** —
    absolute numbers aren't comparable across benchmarks; only the
    within-experiment trend is valid (documented above, not hidden).
11. **Memory footprint is driven mainly by PyTorch** (pulled in as
    `sentence-transformers`'s default backend), not the embedding model
    or vector data themselves. An ONNX Runtime backend would likely
    shrink this substantially, reopening tighter-memory free hosting
    options - not done, since it wasn't needed once self-hosting was
    chosen, and reshaping the runtime now wouldn't carry over cleanly
    to v2 anyway.
12. **No multi-hop query routing in the live API.** `hybrid_search()`
    only performs single-hop enrichment; the multi-hop graph traversal
    that scored 72% vs. 26% in Week 3's benchmarks is not wired into
    `/query`. Mitigated for now via the prompt fix above (the model
    admits it can't answer rather than guessing), not by adding real
    multi-hop retrieval - a legitimate v1.5/v2 item, not solved here.

14. **Adaptive temporal binning (`N = clamp(total_relations/15, 6,20)`) is only actually adaptive for ~12% of the corpus.** 84/96
    books exceed the 300-relation threshold that hits the N=20 cap,
    so the vast majority of books get the same flat bin count
    regardless of how much denser one is than another above that
    line (e.g. book 44 at 2,667 relations and book 106 at 1,280 both
    get N=20). Discovered incidentally while corpus-testing v2's
    phrase-parsing module (Week 6), not a bug in anything built this
    session — a previously undocumented property of v1's own binning
    formula. Not fixed; logged for awareness, revisit only if it
    proves to actually matter for something (e.g. temporal-query
    resolution feeling too coarse on dense books).

# Deferred to v2 (not implemented, not planned for v1)

- Arbitrary book upload (would require a real relation-extraction
  pipeline — explicitly excluded from v1's charter).
- Temporal slider UI.
- Counterfactual/"what if" narrative simulation.
- Local model fine-tuning on user corrections.
- Multiple embedding template variants per relation (retrieval
  diversity).
- Precomputed/cached temporal trajectories (if query-time latency
  becomes a measured problem).
- Efficient, principled query-side direction/role detection.
- Git branch-per-feature workflow (not needed for single-developer
  sequential work at v1's scale).
