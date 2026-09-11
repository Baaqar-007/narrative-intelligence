from dataclasses import dataclass, field

import networkx as nx

from temporal.trajectory import get_relationships_between
from graph.traversal import find_n_hop_paths 

MULTI_HOP_DEPTH = 2  # design default


@dataclass
class EnrichedHit:
    query_match_text: str
    distance: float
    book_id: str
    entity1: str
    entity2: str
    all_relationships: list[dict]
    chains: list[dict] = field(default_factory=list)  # NEW: n-hop paths from entity2


def hybrid_search(collection, query_text, model, corpus, n_results=5, book_id=None) -> list[EnrichedHit]:
    query_embedding = model.encode([query_text]).tolist()
    where_filter = {"book_id": book_id} if book_id else None
    results = collection.query(query_embeddings=query_embedding, n_results=n_results, where=where_filter)

    enriched = []
    for doc, meta, dist in zip(results["documents"][0], results["metadatas"][0], results["distances"][0]):
        graph = corpus.get(meta["book_id"])
        if graph is None:
            continue

        relationships = get_relationships_between(graph, meta["entity1"], meta["entity2"])
        chains = find_n_hop_paths(graph, hops=MULTI_HOP_DEPTH, start_node=meta["entity2"], max_samples=20)

        enriched.append(EnrichedHit(
            query_match_text=doc, distance=dist, book_id=meta["book_id"],
            entity1=meta["entity1"], entity2=meta["entity2"],
            all_relationships=relationships, chains=chains,
        ))
    return enriched