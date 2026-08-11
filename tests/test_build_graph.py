# tests/test_build_graph.py
"""Tests for graph.build_graph."""

import pandas as pd

from graph.build_graph import build_book_graph


def test_repeated_relations_create_multiple_edges() -> None:
    """Tarzan-Taug should have multiple edges, not one overwritten edge."""
    rows = pd.DataFrame([
        {"chunk_id": "1", "relations_parsed": [
            {"entity1": "Tarzan", "entity2": "Taug", "entity1Type": "PER", "entity2Type": "PER", "relation": "companion_of"}
        ]},
        {"chunk_id": "2", "relations_parsed": [
            {"entity1": "Tarzan", "entity2": "Taug", "entity1Type": "PER", "entity2Type": "PER", "relation": "companion_of"}
        ]},
    ])
    graph, stats = build_book_graph(rows, book_id="106")

    assert stats.num_edges == 2
    assert graph.number_of_edges("tarzan", "taug") == 2


def test_surface_forms_accumulate_on_shared_node() -> None:
    """Bolgani and 'Bolgani, the gorilla' should merge into one node."""
    rows = pd.DataFrame([
        {"chunk_id": "1", "relations_parsed": [
            {"entity1": "Bolgani, the gorilla", "entity2": "Tarzan", "entity1Type": "PER", "entity2Type": "PER", "relation": "enemy_of"}
        ]},
        {"chunk_id": "2", "relations_parsed": [
            {"entity1": "Bolgani", "entity2": "Tarzan", "entity1Type": "PER", "entity2Type": "PER", "relation": "enemy_of"}
        ]},
    ])
    graph, stats = build_book_graph(rows, book_id="106")

    assert stats.num_nodes == 2
    assert graph.nodes["bolgani"]["surface_forms"] == {"Bolgani, the gorilla", "Bolgani"}