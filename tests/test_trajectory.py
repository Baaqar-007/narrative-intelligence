from temporal.trajectory import relationship_trajectory, BookTemporalIndex, most_active_pairs_in_bin, weighted_mean_bin, book_trajectory
from networkx import MultiDiGraph

def test_trajectory_returns_all_bins_including_zeros() -> None:
    """Every bin from 1..num_bins should be present, even with no matches."""
    graph = MultiDiGraph()
    graph.add_edge("a", "b", relation="companion_of", chunk_id=0)

    index = BookTemporalIndex(min_chunk_id=0, max_chunk_id=99, num_bins=10)
    trajectory = relationship_trajectory(graph, "a", "b", index)

    assert len(trajectory) == 10
    assert trajectory[1] == 1  # chunk_id=0 lands in bin 1
    assert trajectory[5] == 0  # bin with no matches should still be present, as 0

def test_most_active_pairs_ranks_correctly() -> None:
    """A pair with more edges in the target bin should rank above one with fewer."""
    graph = MultiDiGraph()
    # tarzan-teeka: 2 edges in bin 1 (chunk_id 0, 1)
    graph.add_edge("tarzan", "teeka", relation="companion_of", chunk_id=0)
    graph.add_edge("teeka", "tarzan", relation="friend_of", chunk_id=1)
    # tarzan-taug: 1 edge in bin 1
    graph.add_edge("tarzan", "taug", relation="companion_of", chunk_id=1)
    # an edge in a different bin entirely - should not be counted
    graph.add_edge("tarzan", "numa", relation="enemy_of", chunk_id=90)

    index = BookTemporalIndex(min_chunk_id=0, max_chunk_id=99, num_bins=10)
    result = most_active_pairs_in_bin(graph, bin_num=1, index=index, top_n=5)

    assert result[0] == (("tarzan", "teeka"), 2)
    assert result[1] == (("tarzan", "taug"), 1)
    assert len(result) == 2  # tarzan-numa's bin (10) shouldn't appear
    
# tests/test_trajectory_edge_cases.py
"""Edge case tests for temporal.trajectory — protects retrieval-critical
functions from silently misbehaving on invalid or sparse input.
"""

import pytest



@pytest.fixture
def sample_graph() -> MultiDiGraph:
    graph = MultiDiGraph()
    graph.add_edge("tarzan", "taug", relation="companion_of", chunk_id=0)
    graph.add_edge("tarzan", "teeka", relation="companion_of", chunk_id=1)
    return graph


@pytest.fixture
def sample_index() -> BookTemporalIndex:
    return BookTemporalIndex(min_chunk_id=0, max_chunk_id=9, num_bins=10)


def test_nonexistent_entity_behavior(sample_graph, sample_index):
    """What actually happens when one entity isn't a node in the graph?
    This test documents real behavior rather than an assumed one —
    run it and see whether it raises or returns empty.
    """
    trajectory = relationship_trajectory(sample_graph, "tarzan", "nonexistent", sample_index)
    # If this assertion fails with an exception instead, that tells us
    # NetworkX raises on unknown nbunch nodes — in which case the fix
    # is to catch that and either re-raise a clearer error or return
    # an all-zero trajectory. Report back what actually happens.
    assert trajectory == {b: 0 for b in range(1, sample_index.num_bins + 1)}


def test_entities_with_zero_shared_relations_returns_dense_zeros(sample_graph, sample_index):
    """Two real entities with no relationship between them should
    return an all-zero dense trajectory, not crash or return empty.
    """
    trajectory = relationship_trajectory(sample_graph, "taug", "teeka", sample_index)
    assert trajectory == {b: 0 for b in range(1, sample_index.num_bins + 1)}


def test_bin_with_no_matching_edges_returns_empty_list(sample_graph, sample_index):
    """A bin number with no relation instances should return an empty
    list, not crash.
    """
    result = most_active_pairs_in_bin(sample_graph, bin_num=9, index=sample_index)
    assert result == []
    
def test_book_trajectory_counts_all_canonical_edges() -> None:
    """book_trajectory should count every canonical edge in the graph,
    not just edges between one specific pair.
    """
    graph = MultiDiGraph()
    graph.add_edge("tarzan", "taug", relation="companion_of", chunk_id=0)
    graph.add_edge("tarzan", "teeka", relation="companion_of", chunk_id=0)
    graph.add_edge("taug", "teeka", relation="enemy_of", chunk_id=5)
    graph.add_edge("tarzan", "numa", relation="screaming at", chunk_id=1)  # non-canonical, excluded

    index = BookTemporalIndex(min_chunk_id=0, max_chunk_id=9, num_bins=10)
    trajectory = book_trajectory(graph, index)

    assert sum(trajectory.values()) == 3  # not 4 - the non-canonical edge is dropped
    assert len(trajectory) == 10  # dense, all bins present


def test_weighted_mean_bin_computes_correctly() -> None:
    """Hand-computable case: bin 1 has 1 count, bin 3 has 3 counts.
    Weighted mean = (1*1 + 3*3) / (1+3) = 10/4 = 2.5
    """
    trajectory = {1: 1, 2: 0, 3: 3, 4: 0}
    assert weighted_mean_bin(trajectory) == 2.5


def test_weighted_mean_bin_returns_none_for_empty_trajectory() -> None:
    """A trajectory with zero total count has no meaningful mean position."""
    trajectory = {1: 0, 2: 0, 3: 0}
    assert weighted_mean_bin(trajectory) is None