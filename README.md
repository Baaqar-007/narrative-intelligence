# Narrative Intelligence Engine (NIE)

A temporal graph-augmented retrieval system for fictional narratives.

Version 1 builds a knowledge graph, a temporal (narrative-order) layer,
and a hybrid graph + vector retrieval pipeline over the **Artificial
Relationships in Fiction (ARF)** dataset. It does **not** perform
relation extraction — ARF already provides entities and relationships;
this project focuses on graph construction, retrieval, and grounded
question answering.

## Status

**Week 1 (Knowledge Graph) — complete.**
Weeks 2–4 (Temporal Layer, Hybrid Retrieval, Deployment) — not started.

## Architecture

Dataset -> Entity Canonicalization -> Knowledge Graph -> Temporal Layer
-> Vector Embeddings -> Hybrid Retrieval -> LLM -> Answer

Stack: Python, Pandas, NetworkX, NumPy, Sentence Transformers, ChromaDB,
FastAPI, Docker. No relation extraction, no model training/fine-tuning
anywhere in the pipeline.

## What's built so far (Week 1)

| Module | Purpose |
|---|---|
| `notebooks/explore_arf_dataset.ipynb` | Dataset exploration, cleaning, findings |
| `graph/canonicalization.py` | `normalize_entity_name()` — normalizes raw entity strings for use as node IDs |
| `graph/build_graph.py` | `build_book_graph()` — builds a `MultiDiGraph` for one book |
| `graph/corpus.py` | `build_corpus_graphs()`, `save_corpus()`, `load_corpus()` — builds and persists the full 96-book corpus |
| `data/arf_chunks_parsed.parquet` | Cleaned dataset (malformed rows removed) |
| `data/graphs/corpus.pkl` | Persisted graph corpus (96 books) |

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
- [ ] Week 2 — Temporal Layer
- [ ] Week 3 — Hybrid Retrieval
- [ ] Week 4 — Deployment