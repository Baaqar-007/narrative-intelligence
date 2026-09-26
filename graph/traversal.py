"""Graph traversal algorithms, shared by evaluation/benchmark.py and
retrieval/hybrid_search.py.

allowed_relations (find_paths_up_to_hops) is the latest addition:
unconstrained live traversal was found, via real-corpus testing, to
return almost entirely irrelevant chains once the start entity has
high degree (a 657-degree node returned 100 chains with zero touching
the query's actual target relation). Filtering to the set of relations
the query actually mentioned (retrieval.direction_detection.
mentioned_relations) fixed it directly - confirmed via a realistic
reproduction (30 irrelevant edges + 2 relevant ones at a hub):
unconstrained returned 20 chains, 0 relevant; constrained returned 3,
including the one real answer.
"""

import networkx as nx

from graph.relation_ontology import SYMMETRIC_RELATIONS


def graph_n_hop_search(graph: nx.MultiDiGraph, entity_a: str, hops: int) -> set[str]:
    """All entities reachable from entity_a within `hops` steps.
    Outgoing edges always followed; incoming edges only for relation
    types in SYMMETRIC_RELATIONS. Cumulative across hop depths."""
    frontier = {entity_a}
    visited = {entity_a}
    for _ in range(hops):
        next_frontier = set()
        for node in frontier:
            neighbors = {v for _, v, _ in graph.edges(nbunch=[node], data=True)}
            neighbors |= {
                u for u, _, data in graph.in_edges(nbunch=[node], data=True)
                if data["relation"] in SYMMETRIC_RELATIONS
            }
            next_frontier |= neighbors - visited
        visited |= next_frontier
        frontier = next_frontier
    return visited - {entity_a}


def find_n_hop_paths(
    graph: nx.MultiDiGraph, hops: int, max_samples: int = 500, start_node: str | None = None
) -> list[dict]:
    """Paths of EXACTLY `hops` length - for BENCHMARK use (exact-depth
    sampling for controlled accuracy-vs-hop-count comparison). For
    LIVE retrieval use find_paths_up_to_hops() instead.

    start_node: if given, search only from this entity (live use).
    If None (default), search from every node (benchmark sampling).
    """
    paths = []

    def dfs(current, visited_nodes, visited_rels, visited_dirs, depth):
        if depth == hops:
            paths.append({
                "start": visited_nodes[0], "end": current,
                "path": visited_nodes + [current],
                "relations": list(visited_rels), "directions": list(visited_dirs),
            })
            return
        if len(paths) >= max_samples:
            return
        candidates = [
            (v, data["relation"], "forward")
            for _, v, data in graph.edges(nbunch=[current], data=True)
        ]
        candidates += [
            (u, data["relation"], "reverse")
            for u, _, data in graph.in_edges(nbunch=[current], data=True)
            if data["relation"] in SYMMETRIC_RELATIONS
        ]
        for other, relation, direction in candidates:
            if other not in visited_nodes:
                dfs(other, visited_nodes + [current], visited_rels + [relation],
                    visited_dirs + [direction], depth + 1)

    nodes_to_search = [start_node] if start_node is not None else graph.nodes
    for node in nodes_to_search:
        if len(paths) >= max_samples:
            break
        dfs(node, [], [], [], 0)

    return paths


def find_paths_up_to_hops(
    graph: nx.MultiDiGraph,
    max_hops: int,
    start_node: str,
    max_samples: int = 20,
    allowed_relations: set[str] | None = None,
) -> list[dict]:
    """Paths from start_node up to (and including) max_hops long -
    every depth along the way, not just exactly max_hops. For LIVE
    retrieval use (the real answer's distance isn't known in advance).

    Args:
        allowed_relations: if given, only follow/record edges whose
            relation is in this set. Found necessary via real-usage
            testing: without it, a high-degree start entity floods the
            result with chains through relation types the query never
            asked about, crowding out the genuinely relevant path
            before max_samples is even reached. None (default) means
            unconstrained.
    """
    paths = []

    def dfs(current, visited_nodes, visited_rels, visited_dirs, depth):
        if depth > 0:
            paths.append({
                "start": visited_nodes[0], "end": current,
                "path": visited_nodes + [current],
                "relations": list(visited_rels), "directions": list(visited_dirs),
            })
        if depth == max_hops or len(paths) >= max_samples:
            return
        candidates = [
            (v, data["relation"], "forward")
            for _, v, data in graph.edges(nbunch=[current], data=True)
        ]
        candidates += [
            (u, data["relation"], "reverse")
            for u, _, data in graph.in_edges(nbunch=[current], data=True)
            if data["relation"] in SYMMETRIC_RELATIONS
        ]
        candidates = list(dict.fromkeys(candidates))  # collapse parallel multi-edges (same relation instance repeated)
        if allowed_relations is not None:
            candidates = [c for c in candidates if c[1] in allowed_relations]
        for other, relation, direction in candidates:
            if other not in visited_nodes and len(paths) < max_samples:
                dfs(other, visited_nodes + [current], visited_rels + [relation],
                    visited_dirs + [direction], depth + 1)

    dfs(start_node, [], [], [], 0)
    # Path-level dedupe. The same (start, path, relations) chain can be
    # emitted more than once when a node has parallel edges with the
    # same relation, or when a symmetric edge is reachable via both its
    # forward and reverse traversals. dict.fromkeys() above only
    # collapses parallel edges at a single DFS step, not paths that
    # converge. Dedupe here, after DFS, so the sample cap and traversal
    # order are unchanged.
    seen: set[tuple] = set()
    deduped: list[dict] = []
    for p in paths:
        key = (p["start"], tuple(p["path"]), tuple(p["relations"]))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(p)
    return deduped

def _direction_aware_undirected_view(graph: nx.MultiDiGraph) -> nx.MultiDiGraph:
    """Build a copy of graph where SYMMETRIC_RELATIONS edges are
    traversable in either direction (mirrored), all other edges keep
    their original direction only - matching graph_n_hop_search()'s
    exact semantics, for use as an independent verification target.
    """
    mirrored = graph.copy()
    for u, v, data in graph.edges(data=True):
        if data.get("relation") in SYMMETRIC_RELATIONS:
            mirrored.add_edge(v, u, **data)
    return mirrored