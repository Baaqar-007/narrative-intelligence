from temporal.trajectory import relationship_trajectory, BookTemporalIndex, most_active_pairs_in_bin
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