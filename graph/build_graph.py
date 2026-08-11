# graph/build_graph.py
"""Knowledge graph construction from the parsed ARF dataset.

Builds one NetworkX MultiDiGraph per book, where nodes are canonicalized
entities and edges are individual relation instances (preserving
repetition, since relation frequency is meaningful signal — see
notebooks/explore_arf_dataset.ipynb, Day 3 findings).
"""

from dataclasses import dataclass, field

import networkx as nx
import pandas as pd

from graph.canonicalization import normalize_entity_name


@dataclass
class GraphBuildStats:
    """Summary statistics from a graph build, for sanity-checking output."""

    book_id: str
    num_nodes: int = 0
    num_edges: int = 0
    num_chunks_processed: int = 0


def build_book_graph(book_rows: pd.DataFrame, book_id: str) -> tuple[nx.MultiDiGraph, GraphBuildStats]:
    """Build a knowledge graph for a single book from its relation chunks.

    Args:
        book_rows: Rows of the parsed ARF dataframe for one book_id,
            each with a 'relations_parsed' column of relation dicts.
        book_id: The book identifier, used to scope node identity.

    Returns:
        A tuple of (graph, stats). Nodes are keyed by normalized entity
        name (unique within this book's graph). Edges carry the raw
        relation type and the source chunk_id as provenance.
    """
    graph = nx.MultiDiGraph()
    stats = GraphBuildStats(book_id=book_id)

    for _, row in book_rows.iterrows():
        stats.num_chunks_processed += 1
        for relation in row["relations_parsed"]:
            source = _add_or_update_node(graph, relation["entity1"], relation["entity1Type"])
            target = _add_or_update_node(graph, relation["entity2"], relation["entity2Type"])
            graph.add_edge(
                source,
                target,
                relation=relation["relation"],
                chunk_id=int(row["chunk_id"]),
            )

    stats.num_nodes = graph.number_of_nodes()
    stats.num_edges = graph.number_of_edges()
    return graph, stats


def _add_or_update_node(graph: nx.MultiDiGraph, raw_name: str, entity_type: str) -> str:
    """Add a node if new, or record an additional surface form if it exists.

    Args:
        graph: The graph being built.
        raw_name: Raw entity name as it appeared in this relation.
        entity_type: Entity type from the dataset (e.g. "PER").

    Returns:
        The normalized node identifier used as the graph key.
    """
    node_id = normalize_entity_name(raw_name)

    if node_id not in graph:
        graph.add_node(node_id, entity_type=entity_type, surface_forms={raw_name})
    else:
        graph.nodes[node_id]["surface_forms"].add(raw_name)

    return node_id