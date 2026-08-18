# Narrative Intelligence Engine (NIE)

A temporal graph-augmented retrieval system for fictional narratives.

Version 1 builds a knowledge graph, a temporal (narrative-order) layer,
and a hybrid graph + vector retrieval pipeline over the **Artificial
Relationships in Fiction (ARF)** dataset. It does **not** perform
relation extraction — ARF already provides entities and relationships;
this project focuses on graph construction, retrieval, and grounded
question answering.

## Status

- **Week 1 (Knowledge Graph) — complete.**
- **Week 2 (Temporal Layer) — complete.**
- Weeks 3–4 (Hybrid Retrieval, Deployment) — not started.

## Architecture

Dataset -> Entity Canonicalization -> Knowledge Graph -> Temporal Layer
-> Vector Embeddings -> Hybrid Retrieval -> LLM -> Answer

Stack: Python, Pandas, NetworkX, NumPy, Sentence Transformers, ChromaDB,
FastAPI, Docker. No relation extraction, no model training/fine-tuning
anywhere in the pipeline.

## What's built so far

| Module | Purpose |
|---|---|
| `notebooks/explore_arf_dataset.ipynb` | Dataset exploration, cleaning, findings |
| `graph/canonicalization.py` | `normalize_entity_name()` — normalizes raw entity strings for use as node IDs |
| `graph/build_graph.py` | `build_book_graph()` — builds a `MultiDiGraph` for one book |
| `graph/corpus.py` | `build_corpus_graphs()`, `save_corpus()`, `load_corpus()` — builds and persists the full 96-book corpus |
| `data/arf_chunks_parsed.parquet` | Cleaned dataset (malformed rows removed) |
| `data/graphs/corpus.pkl` | Persisted graph corpus (96 books) |
| `temporal/binning.py` | `compute_num_bins()`, `assign_narrative_bin()` — narrative-position binning, adapted from Christou & Tsoumakas (2025), "Relational Arcs as Narrative Structure" |
| `temporal/trajectory.py` | `build_temporal_index()`, `relationship_trajectory()`, `most_active_pairs_in_bin()`, `book_trajectory()`, `weighted_mean_bin()` — query-time temporal queries over a book's graph |

### Corpus stats
- 96 books, 44,248 nodes, 128,331 edges
- Edge count matches the dataset-wide relation count exactly (verified)

## Design decisions

- **Node identity**: `(book_id, normalized_entity_name)` — entities are
  scoped per-book, not merged globally, since the same name (e.g.
  "Tarzan") can refer to unrelated characters across different books.
- **Graph type**: `MultiDiGraph`, not a simple `DiGraph` — confirmed
  necessary by data: some entity pairs (e.g. Tarzan–Taug) have 90+
  separate relation instances, which a simple `DiGraph` would silently
  collapse into one edge.
- **Persistence**: `pickle`, not GML/GraphML — GML/GraphML can't
  represent the `set`-typed `surface_forms` node attribute without a
  lossy custom encoding; confirmed empirically. Trade-off: pickle is
  Python-only and unsafe to load from untrusted sources, which is fine
  since we only load files we generate ourselves.
- **Temporal = narrative position, not real time.** ARF has no calendar
  dates; `chunk_id` (per-book, mostly contiguous — see Week 1 findings)
  is the only ordering signal. "Temporal layer" here means percent-of-book
  position, following the binning method from Christou & Tsoumakas (2025).
- **Deviation from the published binning formula:** uses
  `(chunk_id - min_chunk_id)` instead of raw `chunk_id`, since ARF's
  per-book chunk sampling means `chunk_id` doesn't always start at 0.
  Verified empirically this matters: a chunk 5 positions into an
  883-chunk span landed in bin 1 with the offset vs. bin 3 without it.
- **Query-time, not precomputed.** Trajectories and bin queries are
  computed on demand from the graph, not stored/cached. Revisit if
  retrieval latency becomes a measured problem (deferred to v2/deployment).
- **Relation filtering:** all temporal queries default to
  `canonical_only=True` (see `graph/relation_ontology.py`), excluding
  the ~2.5% of relation instances that deviate from ARF's 48-type
  ontology (free-text phrases like "screaming at", not typos —
  see Week 1 findings). Revisit only if this measurably affects output.
### Corpus-wide temporal finding

Computed a count-weighted mean narrative position (normalized 0–1)
for all canonical relations in each book, across 95/96 books (74763
excluded — zero relations). Result: activity is roughly evenly
distributed across the narrative for most books (mean = 0.531,
89/95 books within the 0.4–0.6 band), **not** front- or back-loaded.
Book 106 ("Jungle Tales of Tarzan"), used throughout early development,
is *not* representative — it shows unusually clustered early/late
activity with a sparse middle. This suggests narrative-position-based
retrieval queries should be meaningful across most of the corpus, not
just the one book used for development.

## Known limitations (open, tracked deliberately)

1. **Generic/collective entities are not resolved.** "apes" and "the
   apes" remain distinct nodes, even though they likely refer to the
   same collective reference. Different in kind from individual named
   characters; deferred until it's a measured retrieval problem.
2. **No cross-alias / nickname resolution.** E.g. "Tarzan" and "Lord
   Greystoke" are not merged. Only a narrow, verified appositive-strip
   rule is applied (`"Bolgani, the gorilla"` → `"bolgani"`).
3. **Relation directionality is inconsistent for symmetric relation
   types.** E.g. `companion_of` appears in both directions for the same
   entity pair, while types like `protector_of` are genuinely
   asymmetric. Whether/how to normalize this is deferred to retrieval
   work, where it can be evaluated against real query behavior.
4. **Book 74763 has zero relations** (8 chunks, none with extractable
   relations) — produces a valid but empty graph. Likely a very short
   work. Will be excluded from the retrieval-ready book list later.
5. **1 malformed row** in the raw ARF dataset (a parsing artifact,
   not our bug) — filtered out during cleaning.

6. **No distinction between "no relationship" and "unrecognized entity name."**          `relationship_trajectory()` returns an all-zero dense
   trajectory for both a real entity pair with no shared relations and
   a misspelled/nonexistent entity name — verified by test, not a bug,
   but worth guarding against once retrieval accepts free-text entity
   references from user queries (Week 3+).

## Setup

```bash
pip install -e .
python -m pytest tests/ -v
```

## Planned evaluation (not yet built)

ARF's ground-truth relations enable auto-generated eval questions
(e.g. `{Tarzan, companion_of, Taug}` -> "Who is Taug's companion?")
without hand-labeling. Planned comparison: this hybrid graph+vector
system vs. plain vector-only RAG, across single-fact, multi-hop, and
aggregation question types, on retrieval precision/recall, answer
accuracy, and latency. Scoped for Week 3–4.

## Roadmap

- [x] Week 1 — Knowledge Graph
- [x] Week 2 — Temporal Layer
- [ ] Week 3 — Hybrid Retrieval
- [ ] Week 4 — Deployment