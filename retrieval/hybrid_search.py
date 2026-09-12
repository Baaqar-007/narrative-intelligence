# retrieval/hybrid_search.py
"""Hybrid graph + vector retrieval.

Vector search finds semantically relevant entity pairs from a free-text
query, but can't reliably resolve which direction a relation runs (see
Week 3 Day 3 findings - "who protects Taug" surfaced a protector_of
edge, but in the wrong direction). This module enriches each vector hit
with the true, graph-verified relationships between its entities, so a
downstream consumer (LLM or user) sees precise facts, not a single
possibly-misdirected sentence.

WEEK 7 UPDATE: optional multi-hop chain enrichment, for questions like
"who is the protector of the friend of the knight" that a single-hop
pair alone can't answer. Opt-in via `hop_depth` (default 0 = disabled)
- deliberately zero cost and zero behavior change for any existing
caller that doesn't ask for it, since nothing downstream consumes
`chains` yet and query-direction detection (which entity a chained
query actually intends to continue from) isn't built yet either. When
enabled, chains expand from entity2 only, not entity1 or both - a
provisional choice based on the single motivating example above, not
a measured one; likely to be revisited once direction detection can
inform which entity to expand from instead of assuming it.
"""

from dataclasses import dataclass, field

import networkx as nx

from graph.traversal import find_paths_up_to_hops
from temporal.trajectory import get_relationships_between


@dataclass
class EnrichedHit:
    """A vector search hit, enriched with the full graph-verified
    relationship picture for its entity pair, and optionally a set of
    further reachable facts beyond that pair (see `chains`).
    """

    query_match_text: str
    distance: float
    book_id: str
    entity1: str
    entity2: str
    all_relationships: list[dict]
    chains: list[dict] = field(default_factory=list)
    """Paths reachable from entity2, up to `hop_depth` hops (see
    hybrid_search()'s hop_depth parameter). Empty unless explicitly
    requested. Excludes any path leading back to entity1 - that
    relationship is already fully covered by all_relationships, and
    entity2 always has some path back to entity1 by construction
    (that's why they were matched as a pair), so including it would
    only add redundant noise to a downstream LLM's context.
    """


def hybrid_search(
    collection,
    query_text: str,
    model,
    corpus: dict[str, nx.MultiDiGraph],
    n_results: int = 5,
    book_id: str | None = None,
    hop_depth: int = 0,
) -> list[EnrichedHit]:
    """Run vector search, then enrich each hit with graph-verified facts.

    Args:
        collection: ChromaDB collection (see embedding.vector_store).
        query_text: Free-text query.
        model: Pre-loaded SentenceTransformer.
        corpus: book_id -> graph, as built by graph.corpus.build_corpus_graphs().
        n_results: How many vector hits to enrich.
        book_id: Optional, restrict search to one book.
        hop_depth: If > 0, also expand each hit's entity2 up to this
            many hops, populating EnrichedHit.chains for multi-hop
            questions. Default 0 (disabled) - existing callers see
            identical behavior and cost unless they opt in explicitly.

    Returns:
        A list of EnrichedHit, one per vector hit, each carrying the
        full set of relationships (both directions, all relation types)
        between that hit's two entities, plus any requested multi-hop
        chains beyond that pair.
    """
    query_embedding = model.encode([query_text]).tolist()
    where_filter = {"book_id": book_id} if book_id else None

    results = collection.query(
        query_embeddings=query_embedding,
        n_results=n_results,
        where=where_filter,
    )

    enriched = []
    for doc, meta, dist in zip(
        results["documents"][0], results["metadatas"][0], results["distances"][0]
    ):
        graph = corpus.get(meta["book_id"])
        if graph is None:
            continue

        relationships = get_relationships_between(graph, meta["entity1"], meta["entity2"])

        chains = []
        if hop_depth > 0:
            raw_chains = find_paths_up_to_hops(
                graph, max_hops=hop_depth, start_node=meta["entity2"], max_samples=20
            )
            chains = [c for c in raw_chains if c["end"] != meta["entity1"]]

        enriched.append(EnrichedHit(
            query_match_text=doc,
            distance=dist,
            book_id=meta["book_id"],
            entity1=meta["entity1"],
            entity2=meta["entity2"],
            all_relationships=relationships,
            chains=chains,
        ))

    return enriched