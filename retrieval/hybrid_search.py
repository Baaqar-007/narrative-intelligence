# retrieval/hybrid_search.py
"""Hybrid graph + vector retrieval.

Vector search finds semantically relevant entity pairs from a free-text
query, but can't reliably resolve which direction a relation runs (see
Week 3 Day 3 findings - "who protects Taug" surfaced a protector_of
edge, but in the wrong direction). This module enriches each vector hit
with the true, graph-verified relationships between its entities, so a
downstream consumer (LLM or user) sees precise facts, not a single
possibly-misdirected sentence.
"""

from dataclasses import dataclass

import networkx as nx

from temporal.trajectory import get_relationships_between


@dataclass
class EnrichedHit:
    """A vector search hit, enriched with the full graph-verified
    relationship picture for its entity pair.
    """

    query_match_text: str
    distance: float
    book_id: str
    entity1: str
    entity2: str
    all_relationships: list[dict]


def hybrid_search(collection, query_text: str, model, corpus: dict[str, nx.MultiDiGraph], n_results: int = 5, book_id: str | None = None) -> list[EnrichedHit]:
    """Run vector search, then enrich each hit with graph-verified facts.

    Args:
        collection: ChromaDB collection (see embedding.vector_store).
        query_text: Free-text query.
        model: Pre-loaded SentenceTransformer.
        corpus: book_id -> graph, as built by graph.corpus.build_corpus_graphs().
        n_results: How many vector hits to enrich.
        book_id: Optional, restrict search to one book.

    Returns:
        A list of EnrichedHit, one per vector hit, each carrying the
        full set of relationships (both directions, all relation types)
        between that hit's two entities - not just the one relation
        that happened to match semantically.
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

        enriched.append(EnrichedHit(
            query_match_text=doc,
            distance=dist,
            book_id=meta["book_id"],
            entity1=meta["entity1"],
            entity2=meta["entity2"],
            all_relationships=relationships,
        ))

    return enriched