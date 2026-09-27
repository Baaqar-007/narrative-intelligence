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
        if hop_depth > 0 and query_target_relation is not None:
            allowed = mentioned_relations(query_text)
            e1, e2 = meta["entity1"], meta["entity2"]
            chains = (
                _expand_from_entity(graph, e1, e2, hop_depth, query_target_relation, allowed)
                + _expand_from_entity(graph, e2, e1, hop_depth, query_target_relation, allowed)
            )
            

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

# def _hop_bump(start_entity: str, matched_e1: str, matched_relation: str | None) -> int:
#     """Whether the first hop re-treads the matched pair's own edge -
#     always true starting from entity1 (that's the edge's direction),
#     true starting from entity2 only if the relation is symmetric
#     (same edge, reachable either way). Generalizes the original
#     single-expand_from bump condition to either starting entity."""
#     if start_entity == matched_e1:
#         return 1
#     return 1 if matched_relation in SYMMETRIC_RELATIONS else 0

def _terminal_answer(chain: dict) -> str:
    """The node the query is actually asking for, from the terminal
    edge of this chain.

    SYMMETRIC relations (see graph.relation_ontology.SYMMETRIC_RELATIONS)
    have no meaningful entity1/entity2 role distinction - "X's enemy"
    and "Y's enemy" where X enemy_of Y is the same real-world fact
    regardless of which was recorded as entity1. For these, the answer
    is simply the newly-reached node (chain["end"]) - NOT entity1's
    position. Confirmed as a real bug, not a hypothesis: this exact
    case zeroed the Taug/Tarzan positive control, because several
    real enemy_of edges happen to store tarzan as entity1 - the old
    entity1-based rule answered "tarzan" (the start node, already
    excluded) instead of the actual enemy.

    For non-symmetric relations, the entity1-based rule from before
    still holds (all MANUAL_TEMPLATES phrase entity1 as the wanted
    role for both phrasing shapes target_relation() recognizes) - not
    proven for a hypothetical future synonym naming entity2 instead.
    """
    if chain["relations"][-1] in SYMMETRIC_RELATIONS:
        return chain["end"]
    if chain["directions"][-1] == "forward":
        return chain["path"][-2]
    return chain["path"][-1]


def _expand_from_entity(graph, start, other, hop_depth, query_target_relation, allowed):
    raw_chains = find_paths_up_to_hops(
        graph, max_hops=hop_depth, start_node=start,
        max_samples=20, allowed_relations=allowed,
    )
    chains = []
    for c in raw_chains:
        if query_target_relation is None or c["relations"][-1] != query_target_relation:
            continue
        answer = _terminal_answer(c)
        if answer in (start, other):
            # answer == other: just restates the originally-matched
            # fact, already covered by all_relationships.
            # answer == start: the chain's terminal edge resolves back
            # to the anchor entity itself (e.g. a direct, possibly
            # contradictory taug-enemy_of->tarzan edge evaluated from
            # taug's own side) - not a real answer to a question about
            # that entity. Both cases are "not new information," for
            # different reasons - conflating them under one check
            # (checking only `answer == other`, or only `end`) is what
            # broke last turn; both need checking explicitly.
            continue
        chains.append({**c, "answer": answer})
    return chains
        