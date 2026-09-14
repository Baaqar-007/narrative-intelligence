# tests/test_hybrid_integration.py
"""Integration tests across graph + embedding modules - specifically
targets the kind of bug that unit tests of either module alone can't
catch (see Week 3 Day 4 findings).
"""

import networkx as nx
import pandas as pd
import numpy as np
import pytest

from embedding.embed_relations import build_embedding_records
from graph.build_graph import build_book_graph
from temporal.trajectory import get_relationships_between


def test_embedded_entity_names_resolve_in_graph() -> None:
    """The core invariant: any entity name stored in embedding metadata
    must be a real node in the corresponding graph, so hybrid retrieval
    can actually look it up.
    """
    rows = pd.DataFrame([
        {
            "book_id": "106",
            "chunk_id": "10",
            "relations_parsed": [
                {"entity1": "Taug", "entity2": "Bolgani, the gorilla",
                 "entity1Type": "PER", "entity2Type": "PER", "relation": "enemy_of"}
            ],
        }
    ])

    graph, _ = build_book_graph(rows, book_id="106")
    records = build_embedding_records(rows)

    for record in records:
        assert record.entity1 in graph.nodes, (
            f"{record.entity1!r} from embedding metadata not found in graph nodes"
        )
        assert record.entity2 in graph.nodes, (
            f"{record.entity2!r} from embedding metadata not found in graph nodes"
        )

    # and confirm the actual downstream lookup works end-to-end
    relationships = get_relationships_between(graph, records[0].entity1, records[0].entity2)
    assert len(relationships) == 1
    assert relationships[0]["relation"] == "enemy_of"


from retrieval.hybrid_search import hybrid_search


class FakeModel:
    """Stand-in for a SentenceTransformer - encode() just needs to
    return something with .tolist(), the actual vector values don't
    matter since FakeCollection ignores them and returns fixed results."""

    def encode(self, texts):
        return np.zeros((len(texts), 4))


class FakeCollection:
    """Stand-in for a ChromaDB collection - returns pre-configured
    results regardless of the query embedding, matching the real
    collection.query() return shape."""

    def __init__(self, documents, metadatas, distances):
        self._documents = documents
        self._metadatas = metadatas
        self._distances = distances

    def query(self, query_embeddings, n_results, where=None):
        return {
            "documents": [self._documents[:n_results]],
            "metadatas": [self._metadatas[:n_results]],
            "distances": [self._distances[:n_results]],
        }


@pytest.fixture
def knight_graph() -> nx.MultiDiGraph:
    """knight-friend_of->squire, squire-protector_of->lord - the exact
    shape of README's original motivating example ("protector of the
    friend of the knight")."""
    g = nx.MultiDiGraph()
    g.add_edge("knight", "squire", relation="friend_of", chunk_id="1")
    g.add_edge("squire", "lord", relation="protector_of", chunk_id="2")
    return g


@pytest.fixture
def single_hit_collection() -> FakeCollection:
    return FakeCollection(
        documents=["knight is a friend of squire"],
        metadatas=[{"book_id": "1", "entity1": "knight", "entity2": "squire"}],
        distances=[0.1],
    )


class TestHopDepthDefaultIsANoOp:
    """The core safety requirement from Week 7: hop_depth=0 (default)
    must be byte-for-byte identical to pre-Week-7 behavior."""

    def test_default_chains_is_empty(self, single_hit_collection, knight_graph):
        corpus = {"1": knight_graph}
        hits = hybrid_search(single_hit_collection, "who is squire's friend?",
                              FakeModel(), corpus, n_results=1)
        assert hits[0].chains == []

    def test_explicit_hop_depth_zero_also_empty(self, single_hit_collection, knight_graph):
        corpus = {"1": knight_graph}
        hits = hybrid_search(single_hit_collection, "who is squire's friend?",
                              FakeModel(), corpus, n_results=1, hop_depth=0)
        assert hits[0].chains == []

    def test_existing_fields_unaffected(self, single_hit_collection, knight_graph):
        corpus = {"1": knight_graph}
        hits = hybrid_search(single_hit_collection, "q", FakeModel(), corpus, n_results=1)
        assert hits[0].entity1 == "knight"
        assert hits[0].entity2 == "squire"
        assert hits[0].book_id == "1"


class TestHopDepthEnabled:
    def test_finds_the_motivating_two_hop_fact(self, single_hit_collection, knight_graph):
        """The actual feature this exists for: entity2 (squire) has a
        further fact (protector_of lord) the single-hop pair alone
        can't surface."""
        corpus = {"1": knight_graph}
        hits = hybrid_search(single_hit_collection, "who protects the friend of the knight?",
                              FakeModel(), corpus, n_results=1, hop_depth=2)
        ends = {c["end"] for c in hits[0].chains}
        assert "lord" in ends

    def test_redundant_path_back_to_entity1_is_filtered(self, single_hit_collection):
        """squire always has a path back to knight (that's why they were
        matched as a pair) - already covered by all_relationships, must
        not be duplicated in chains."""
        g = nx.MultiDiGraph()
        g.add_edge("knight", "squire", relation="companion_of", chunk_id="1")  # symmetric - reverse-reachable
        g.add_edge("squire", "lord", relation="protector_of", chunk_id="2")
        corpus = {"1": g}
        hits = hybrid_search(single_hit_collection, "q", FakeModel(), corpus,
                              n_results=1, hop_depth=2)
        ends = {c["end"] for c in hits[0].chains}
        assert "knight" not in ends
        assert "lord" in ends

    def test_missing_book_in_corpus_is_skipped_not_crashed(self, single_hit_collection):
        hits = hybrid_search(single_hit_collection, "q", FakeModel(), corpus={},
                              n_results=1, hop_depth=2)
        assert hits == []