"""Tests for graph/traversal.py.

Covers the direction-agnostic-but-scoped-to-symmetric-relations design
(Week 7): forward edges always followed, reverse edges only for
SYMMETRIC_RELATIONS, and the exact-vs-up-to-hops distinction that
caught a real bug during development (find_n_hop_paths silently
returning nothing when the real answer was closer than the requested
depth - see find_paths_up_to_hops).
"""

import networkx as nx
import pytest

from graph.traversal import (
    find_n_hop_paths,
    find_paths_up_to_hops,
    graph_n_hop_search,
)


@pytest.fixture
def mixed_graph() -> nx.MultiDiGraph:
    """A small graph with both a symmetric relation (companion_of,
    reverse-traversable) and an asymmetric one (child_of, forward-only)
    - mirrors the exact shape used to catch the original forward-only
    bug during development.
    """
    g = nx.MultiDiGraph()
    g.add_edge("taug", "akut", relation="companion_of")
    g.add_edge("teeka", "taug", relation="companion_of")   # reverse from taug
    g.add_edge("akut", "duro", relation="child_of")         # asymmetric, forward only
    return g


class TestGraphNHopSearch:
    def test_forward_edge_always_reachable(self, mixed_graph):
        assert "akut" in graph_n_hop_search(mixed_graph, "taug", hops=1)

    def test_symmetric_relation_reverse_reachable(self, mixed_graph):
        """The bug this whole feature exists to fix: teeka is only
        connected to taug via a reverse-stored companion_of edge."""
        assert "teeka" in graph_n_hop_search(mixed_graph, "taug", hops=1)

    def test_asymmetric_relation_not_reverse_reachable(self, mixed_graph):
        """child_of is NOT in SYMMETRIC_RELATIONS - duro must not be
        reverse-reachable from akut's perspective going the wrong way."""
        reachable_from_duro = graph_n_hop_search(mixed_graph, "duro", hops=1)
        assert "akut" not in reachable_from_duro

    def test_cumulative_across_hops(self, mixed_graph):
        """A node reachable in 1 hop must still appear in the 2-hop
        result (cumulative, not just the final BFS layer - this was a
        real bug in v1's original hop-count benchmark)."""
        one_hop = graph_n_hop_search(mixed_graph, "teeka", hops=1)
        two_hop = graph_n_hop_search(mixed_graph, "teeka", hops=2)
        assert one_hop.issubset(two_hop)

    def test_entity_a_excluded_from_own_result(self, mixed_graph):
        assert "taug" not in graph_n_hop_search(mixed_graph, "taug", hops=2)


class TestFindNHopPaths:
    def test_exact_depth_only(self, mixed_graph):
        """Every returned path must be EXACTLY `hops` long - this is
        the deliberate benchmark-sampling behavior, distinct from
        find_paths_up_to_hops()."""
        paths = find_n_hop_paths(mixed_graph, hops=2, max_samples=50)
        for p in paths:
            assert len(p["relations"]) == 2
            assert len(p["directions"]) == 2

    def test_direction_recorded_correctly(self, mixed_graph):
        paths = find_n_hop_paths(mixed_graph, hops=1, max_samples=50)
        taug_to_teeka = [p for p in paths if p["start"] == "taug" and p["end"] == "teeka"]
        assert len(taug_to_teeka) == 1
        assert taug_to_teeka[0]["directions"] == ["reverse"]

    def test_start_node_none_searches_whole_graph(self, mixed_graph):
        """Backward-compat check: default behavior (benchmark sampling)
        must be unaffected by adding the start_node parameter."""
        paths = find_n_hop_paths(mixed_graph, hops=1, max_samples=50, start_node=None)
        starts = {p["start"] for p in paths}
        assert len(starts) > 1  # multiple distinct starting points

    def test_start_node_restricts_to_one_entity(self, mixed_graph):
        paths = find_n_hop_paths(mixed_graph, hops=1, max_samples=50, start_node="taug")
        assert all(p["start"] == "taug" for p in paths)

    def test_no_exact_2hop_path_returns_empty(self, mixed_graph):
        """Regression test for the exact bug found during development:
        duro has no outgoing edges and no symmetric in-edges to
        continue from, so no 2-hop path from duro exists at all."""
        paths = find_n_hop_paths(mixed_graph, hops=2, max_samples=50, start_node="duro")
        assert paths == []


class TestFindPathsUpToHops:
    def test_recovers_shorter_paths_missed_by_exact_search(self, mixed_graph):
        """The actual bug this function exists to fix: a 1-hop answer
        must be found even when max_hops=2 is requested."""
        paths = find_paths_up_to_hops(mixed_graph, max_hops=2, start_node="akut")
        ends = {p["end"] for p in paths}
        assert "duro" in ends  # the real 1-hop fact, not silently dropped

    def test_all_paths_start_from_given_node(self, mixed_graph):
        paths = find_paths_up_to_hops(mixed_graph, max_hops=2, start_node="taug")
        assert all(p["start"] == "taug" for p in paths)

    def test_respects_max_samples(self, mixed_graph):
        paths = find_paths_up_to_hops(mixed_graph, max_hops=3, start_node="taug", max_samples=1)
        assert len(paths) <= 1
