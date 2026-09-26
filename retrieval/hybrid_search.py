# retrieval/hybrid_search.py
"""Hybrid graph + vector retrieval.

WEEK 7 UPDATE, latest addition: chain traversal now filters to
mentioned_relations(query_text) - unconstrained traversal was found,
via real-corpus testing, to return almost entirely irrelevant chains
from a high-degree start entity (100 chains, 0 touching the query's
actual target relation, in a real case). See graph/traversal.py and
retrieval/direction_detection.py for the full fix history.
"""

from dataclasses import dataclass, field

import networkx as nx

from graph.relation_ontology import SYMMETRIC_RELATIONS
from graph.traversal import find_paths_up_to_hops
from retrieval.direction_detection import direction_match, entity_to_expand_from, mentioned_relations, target_relation
from temporal.trajectory import get_relationships_between
# from retrieval.direction_detection import target_relation
# print("Testing target_relation()")
# print(target_relation("Who is the mother of Esther Lyon's husband?"))
# print(target_relation("Who is the mother of Rufus Lyon's daughter's husband?"))
# print(target_relation("Who is the enemy of the companion of taug?"))

@dataclass
class EnrichedHit:
    """A vector search hit, enriched with the full graph-verified
    relationship picture for its entity pair, and optionally a set of
    further reachable facts beyond that pair (see `chains`)."""

    query_match_text: str
    distance: float
    book_id: str
    entity1: str
    entity2: str
    all_relationships: list[dict]
    chains: list[dict] = field(default_factory=list)
    """Paths reachable from whichever entity the query is asking
    about, up to `hop_depth` hops, filtered to relation types the
    query actually mentioned. Empty unless hop_depth > 0. Excludes
    any path leading back to the other entity in the matched pair -
    already covered by all_relationships."""


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
        collection: ChromaDB collection.
        query_text: Free-text query.
        model: Pre-loaded SentenceTransformer.
        corpus: book_id -> graph.
        n_results: How many vector hits to enrich.
        book_id: Optional, restrict search to one book.
        hop_depth: If > 0, also expand from whichever entity the query
            is asking about, up to this many hops, filtered to
            mentioned_relations(query_text). Default 0 (disabled) -
            existing callers see identical behavior unless they opt in.

    Returns:
        A list of EnrichedHit, each fact annotated with whether it
        matches the query's detected direction, plus any requested
        multi-hop chains beyond that pair.
    """
    query_embedding = model.encode([query_text]).tolist()
    where_filter = {"book_id": book_id} if book_id else None

    results = collection.query(
        query_embeddings=query_embedding,
        n_results=n_results,
        where=where_filter,
    )
    # graph = corpus.get("40882")
    # print("Test graph edges for 'esther' to 'felix':")
    # print([d for _, v, d in graph.edges(nbunch=["esther"], data=True) if v == "felix"])

    query_target_relation = target_relation(query_text)
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
            matched_relation = meta.get("relation")
            expand_from = entity_to_expand_from(
                query_text, meta["entity1"], meta["entity2"],
                matched_relation or "",
            )
            if expand_from is not None:
                other_entity = meta["entity2"] if expand_from == meta["entity1"] else meta["entity1"]
                effective_hop_depth = hop_depth
                if expand_from == meta["entity1"] or matched_relation in SYMMETRIC_RELATIONS:
                    effective_hop_depth = hop_depth + 1
                # ... (bump comment/condition unchanged - still uses matched_relation,
                # this check is about whether the FIRST hop re-treads the matched
                # pair's own edge, which is about that edge's symmetry, not about
                # what the query is ultimately asking for)

                allowed = mentioned_relations(query_text)
                raw_chains = find_paths_up_to_hops(
                    graph, max_hops=effective_hop_depth, start_node=expand_from,
                    max_samples=20, allowed_relations=allowed,
                )
                # Strict terminal equality against the query's single target
                # relation - computed once per query above, not per hit, so
                # it can't be diluted by a union across differently-matched
                # hits (Issue 1 from the previous round).
                chains = [
                    c for c in raw_chains
                    if c["end"] != other_entity
                    and query_target_relation is not None
                    and c["relations"][-1] == query_target_relation
                ]
            # expand_from is None: query couldn't be confidently anchored
            # to either entity in this pair - leave chains empty rather
            # than expand from a guessed node.

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
