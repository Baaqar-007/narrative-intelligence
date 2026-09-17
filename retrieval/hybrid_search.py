from dataclasses import dataclass, field

import networkx as nx

from graph.traversal import find_paths_up_to_hops
from retrieval.direction_detection import direction_match, entity_to_expand_from
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
    """Paths reachable from whichever entity the query is asking about
    (see entity_to_expand_from), up to `hop_depth` hops. Empty unless
    explicitly requested. Excludes any path leading back to the OTHER
    entity in the matched pair - that relationship is already fully
    covered by all_relationships, and there's always some path back to
    it by construction (that's why they were matched as a pair), so
    including it would only add redundant noise downstream.
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
        hop_depth: If > 0, also expand from whichever entity the query
            is asking about, up to this many hops, populating
            EnrichedHit.chains. Default 0 (disabled) - existing callers
            see identical behavior and cost unless they opt in.

    Returns:
        A list of EnrichedHit, one per vector hit, each carrying the
        full set of relationships between that hit's two entities
        (each annotated with whether it matches the query's detected
        direction), plus any requested multi-hop chains beyond that
        pair.
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
        for fact in relationships:
            fact["query_direction_match"] = direction_match(query_text, fact)

        chains = []
        if hop_depth > 0:
            expand_from = entity_to_expand_from(
                query_text, meta["entity1"], meta["entity2"],
                relationships[0]["relation"] if relationships else "",
            )
            other_entity = meta["entity2"] if expand_from == meta["entity1"] else meta["entity1"]

            effective_hop_depth = hop_depth
            if expand_from == meta["entity1"]:
                # entity_to_expand_from backtracked to entity1 because
                # the matched pair's own direction didn't satisfy the
                # query - that first hop re-traverses the same edge
                # that produced the mismatched pair, before reaching
                # any genuinely new ground. Confirmed as a real bug,
                # not a hypothetical: hop_depth=1 from "knight" only
                # reached "squire" (the already-covered entity), never
                # the actual answer, on the exact motivating query.
                effective_hop_depth = hop_depth + 1

            raw_chains = find_paths_up_to_hops(
                graph, max_hops=effective_hop_depth, start_node=expand_from, max_samples=20
            )
            chains = [c for c in raw_chains if c["end"] != other_entity]

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
