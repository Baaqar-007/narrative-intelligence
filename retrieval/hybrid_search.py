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
from resolution.pronoun_filter import resolve_canonical, is_pronoun_generic

@dataclass
class EnrichedHit:

    query_match_text: str
    distance: float
    book_id: str
    entity1: str
    entity2: str
    all_relationships: list[dict]
    chains: list[dict] = field(default_factory=list)
    


def hybrid_search(
    collection,
    query_text: str,
    model,
    corpus: dict[str, nx.MultiDiGraph],
    n_results: int = 5,
    book_id: str | None = None,
    hop_depth: int = 0,
    resolution_maps: dict[str, dict] | None = None,

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
        resolution_map = (resolution_maps or {}).get(meta["book_id"], {})

        relationships = get_relationships_between(graph, meta["entity1"], meta["entity2"])
        for fact in relationships:
            fact["query_direction_match"] = direction_match(query_text, fact)

        chains = []
        if hop_depth > 0 and query_target_relation is not None:
            matched_relation = meta.get("relation")
            expand_from = entity_to_expand_from(
                query_text, meta["entity1"], meta["entity2"], matched_relation or "",
            )
            if expand_from is not None:
                other = meta["entity2"] if expand_from == meta["entity1"] else meta["entity1"]
                allowed = mentioned_relations(query_text)
                effective_hop_depth = _effective_hop_depth(
                    expand_from, meta["entity1"], matched_relation, hop_depth,
                )
                raw_chains = find_paths_up_to_hops(
                    graph, max_hops=effective_hop_depth, start_node=expand_from,
                    max_samples=20, allowed_relations=allowed, resolution_map=resolution_map,
                )
                chains = select_chains(raw_chains, query_target_relation, expand_from, other, resolution_map)

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

def select_chains(raw_chains, query_target_relation, expand_from, other, resolution_map):
    """Filter and resolve raw traversal chains into answer-bearing chains.
    Extracted from hybrid_search's inline loop (day 13) so tests call the
    real logic instead of hand-copying it."""
    chains = []
    for c in raw_chains:
        if not (c["relations"] and c["relations"][-1] == query_target_relation):
            continue
        if _is_redundant_continuation(c, raw_chains, query_target_relation):
            continue
        answer = resolve_canonical(_terminal_answer(c), resolution_map)
        if is_pronoun_generic(answer):
            continue
        if len(c["path"]) == 2 and answer in (expand_from, other):
            continue
        chains.append({**c, "answer": answer})
    return chains

def _is_redundant_continuation(chain: dict, all_chains: list[dict], target_relation: str) -> bool:
    """True if some OTHER, shorter chain's full path is a strict
    prefix of this chain's path, and that shorter chain already
    satisfies target_relation - this chain is a longer walk past an
    already-complete answer, not a second valid one."""
    for other in all_chains:
        if other is chain or len(other["path"]) >= len(chain["path"]):
            continue
        if (chain["path"][:len(other["path"])] == other["path"]
                and other["relations"] and other["relations"][-1] == target_relation):
            return True
    return False

def _effective_hop_depth(expand_from: str, matched_e1: str, matched_relation: str | None,
                          hop_depth: int) -> int:
    """Whether the first hop re-treads the matched pair's own edge -
    always true starting from entity1 (that's the edge's direction),
    true starting from entity2 only if the relation is symmetric
    (same edge, reachable either way). Extracted as a named function
    (day 12) specifically so diagnostic scripts can call the EXACT
    same logic hybrid_search uses, rather than reconstructing it
    separately and risking drift (the day-9 Esther harness bug: a
    diagnostic hardcoded max_hops=1 instead of this computation,
    silently testing a different depth than the live pipeline)."""
    if expand_from == matched_e1 or matched_relation in SYMMETRIC_RELATIONS:
        return hop_depth + 1
    return hop_depth

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
