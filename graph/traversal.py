"""Graph traversal algorithms, shared by evaluation/benchmark.py
(benchmark question generation) and retrieval/hybrid_search.py (live
multi-hop enrichment).

Extracted from evaluation/benchmark.py during Week 7's live wiring -
retrieval code importing from evaluation/ would have been a backward
dependency; this module is the shared base both import from instead.

Direction-agnostic traversal (following edges in either stored
direction) is scoped to SYMMETRIC_RELATIONS only - relation types
README confirmed are stored inconsistently in direction (e.g.
companion_of appears both directions for the same real pair).
Unscoped (all-relation-type) direction-agnostic traversal was tried
first and found to recover real reachability but skew heavily toward
high-degree "hub" nodes without the scoping actually reducing that
skew - see docs/ Week 7 findings for the full measurement. Scoping
here matches what the evidence actually supports.
"""

import networkx as nx

from graph.relation_ontology import SYMMETRIC_RELATIONS


def graph_n_hop_search(graph: nx.MultiDiGraph, entity_a: str, hops: int) -> set[str]:
    """Return all entities reachable from entity_a within `hops` steps.

    Follows outgoing edges always; follows incoming edges only for
    relation types in SYMMETRIC_RELATIONS. Cumulative across all hop
    depths up to `hops`, not just the final layer - a node reachable
    via a path shorter than `hops` still counts.
    """
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
    """Find real paths of EXACTLY `hops` length via DFS, recording
    relation type and direction at each hop.

    For BENCHMARK use (generate_nhop_questions) - deliberately exact-
    depth-only, for controlled accuracy-vs-hop-count comparison across
    a uniform sample. For LIVE retrieval, use find_paths_up_to_hops()
    instead - exact-depth search silently returns nothing whenever the
    real answer is closer than the requested depth, which is common,
    not an edge case, once you're searching from one specific entity
    instead of sampling broadly across a whole corpus.

    Args:
        graph: The book's graph.
        hops: Exact hop depth to search.
        max_samples: Cap on paths returned.
        start_node: If given, only search from this one entity. If
            None (default), search from every node (benchmark
            sampling use).

    Returns:
        List of dicts: {'start', 'end', 'path', 'relations',
        'directions'}. All nodes in a path are distinct.
    """
    paths = []

    def dfs(current, visited_nodes, visited_rels, visited_dirs, depth):
        if depth == hops:
            paths.append({
                "start": visited_nodes[0],
                "end": current,
                "path": visited_nodes + [current],
                "relations": list(visited_rels),
                "directions": list(visited_dirs),
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
    graph: nx.MultiDiGraph, max_hops: int, start_node: str, max_samples: int = 20
) -> list[dict]:
    """Find all paths from start_node up to (and including) max_hops
    long - every depth along the way, not just exactly max_hops.

    For LIVE retrieval use (retrieval.hybrid_search), where the real
    answer's distance from start_node isn't known in advance - see
    find_n_hop_paths()'s docstring for why that function's exact-depth
    behavior is wrong for this use case specifically.

    Returns:
        Same shape as find_n_hop_paths()'s entries, minus 'path'
        (start/end/relations/directions only).
    """
    paths = []

    def dfs(current, visited_nodes, visited_rels, visited_dirs, depth):
        if depth > 0:
            paths.append({
                "start": visited_nodes[0],
                "end": current,
                "relations": list(visited_rels),
                "directions": list(visited_dirs),
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
        for other, relation, direction in candidates:
            if other not in visited_nodes and len(paths) < max_samples:
                dfs(other, visited_nodes + [current], visited_rels + [relation],
                    visited_dirs + [direction], depth + 1)

    dfs(start_node, [], [], [], 0)
    return paths


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