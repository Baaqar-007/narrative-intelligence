# temporal/trajectory.py
"""Binned relationship trajectories: how a relation between two entities
evolves in narrative-bin intensity across a book.
"""

from dataclasses import dataclass

import networkx as nx

from graph.relation_ontology import is_canonical_relation
from temporal.binning import assign_narrative_bin, compute_num_bins


@dataclass
class BookTemporalIndex:
    """Precomputed per-book values needed for binning any of its edges."""

    min_chunk_id: int
    max_chunk_id: int
    num_bins: int


def build_temporal_index(graph: nx.MultiDiGraph) -> BookTemporalIndex:
    """Compute the per-book values needed to bin this book's edges.

    Args:
        graph: A single book's relation graph (edges carry chunk_id).

    Returns:
        The book's min/max chunk_id and its adaptive bin count.
    """
    chunk_ids = [d["chunk_id"] for _, _, d in graph.edges(data=True)]
    total_relations = graph.number_of_edges()
    return BookTemporalIndex(
        min_chunk_id=min(chunk_ids),
        max_chunk_id=max(chunk_ids),
        num_bins=compute_num_bins(total_relations),
    )


def relationship_trajectory(
    graph: nx.MultiDiGraph,
    entity_a: str,
    entity_b: str,
    index: BookTemporalIndex,
    canonical_only: bool = True,
) -> dict[int, int]:
    """Count relation instances between two entities, per narrative bin.

    Returns a dense dict: every bin from 1 to index.num_bins is present,
    with 0 for bins containing no matching relation instances.
    """
    bin_counts: dict[int, int] = {b: 0 for b in range(1, index.num_bins + 1)}

    edges = [
        (u, v, data)
        for u, v, data in graph.edges(nbunch=[entity_a, entity_b], data=True)
        if {u, v} == {entity_a, entity_b}
    ]

    for _, _, data in edges:
        if canonical_only and not is_canonical_relation(data["relation"]):
            continue
        bin_num = assign_narrative_bin(
            chunk_id=data["chunk_id"],
            min_chunk_id=index.min_chunk_id,
            max_chunk_id=index.max_chunk_id,
            num_bins=index.num_bins,
        )
        bin_counts[bin_num] += 1

    return bin_counts