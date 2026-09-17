

import networkx as nx
import numpy as np
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch

import api.main as main_module


class FakeModel:
    def encode(self, texts):
        return np.zeros((len(texts), 4))


class FakeCollection:
    def __init__(self, documents, metadatas, distances):
        self._d, self._m, self._dist = documents, metadatas, distances

    def count(self):
        return len(self._d)

    def query(self, query_embeddings, n_results, where=None):
        return {
            "documents": [self._d[:n_results]],
            "metadatas": [self._m[:n_results]],
            "distances": [self._dist[:n_results]],
        }


@pytest.fixture
def client():
    g = nx.MultiDiGraph()
    g.add_edge("knight", "squire", relation="friend_of", chunk_id=1)
    g.add_edge("squire", "lord", relation="protector_of", chunk_id=2)

    main_module.state["corpus"] = {"1": g}
    main_module.state["collection"] = FakeCollection(
        documents=["knight is a friend of squire"],
        metadatas=[{"book_id": "1", "entity1": "knight", "entity2": "squire"}],
        distances=[0.1],
    )
    main_module.state["model"] = FakeModel()
    main_module.state["titles"] = {"1": "Test Book"}
    return TestClient(main_module.app)


class TestQueryEndpoint:
    def test_unknown_book_id_returns_404(self, client):
        resp = client.post("/query", json={"book_id": "nope", "question": "who is Taug?"})
        assert resp.status_code == 404

    def test_motivating_two_hop_query_end_to_end(self, client):
        """The real regression test: this exact query, through the
        real endpoint, with a REAL (not hand-picked) hop_depth,
        used to return empty chains due to an off-by-one bug in how
        entity_to_expand_from's backtracking interacted with hop
        budget - only caught by testing at this level."""
        with patch("api.main.generate_answer", return_value="Lord protects squire."):
            resp = client.post("/query", json={
                "book_id": "1", "question": "who protects the friend of the knight?",
            })
        assert resp.status_code == 200
        data = resp.json()
        chain_ends = {c["path"][-1] for c in data["chains"]}
        assert "lord" in chain_ends

    def test_single_hop_query_needs_no_chains(self, client):
        with patch("api.main.generate_answer", return_value="Squire."):
            resp = client.post("/query", json={
                "book_id": "1", "question": "Who is knight a friend of?",
            })
        assert resp.status_code == 200
        assert resp.json()["chains"] == []

    def test_sources_include_direction_match_annotation(self, client):
        with patch("api.main.generate_answer", return_value="Squire."):
            resp = client.post("/query", json={
                "book_id": "1", "question": "Who is knight a friend of?",
            })
        sources = resp.json()["sources"]
        assert len(sources) == 1
        assert "query_direction_match" in sources[0]
