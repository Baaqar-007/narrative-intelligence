from temporal.trajectory import relationship_trajectory, BookTemporalIndex
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