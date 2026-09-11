from graph.relation_ontology import SYMMETRIC_RELATIONS
import networkx as nx

# ---------------------------------------------------------------------
# Multi-hop traversal (direction-agnostic for symmetric relation
# types only - see module docstring point 2)
# ---------------------------------------------------------------------

def graph_n_hop_search(graph: nx.MultiDiGraph, entity_a: str, hops: int) -> set[str]:
    """Return all entities reachable from entity_a within `hops` steps.

    Follows outgoing edges always; follows incoming edges only for
    relation types in SYMMETRIC_RELATIONS - the confirmed-direction-
    inconsistent subset, not all 48 canonical types (see module
    docstring point 2 for why the broader version was tried and
    scoped back).

    Cumulative across all hop depths up to `hops`, not just the final
    layer - a node reachable via a path shorter than `hops` still
    counts.
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


def find_n_hop_paths(graph: nx.MultiDiGraph, hops: int, max_samples: int = 500, start_node: str | None = None) -> list[dict]:
    """Find real n-hop paths via DFS, recording the relation type AND
    traversal direction at each hop.

    Direction-agnostic for symmetric relation types only, matching
    graph_n_hop_search(). 'directions' entries are "forward" (current
    node played entity1's role for that edge) or "reverse" (current
    node played entity2's role) - needed downstream because a
    reverse hop needs different question phrasing (see _chain_phrase).

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