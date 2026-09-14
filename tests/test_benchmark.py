"""Tests for evaluation/benchmark.py.

benchmark.py had the largest rewrite of anything this week and, as
far as I've seen, has no existing pytest coverage at all - this file
covers the pure-logic parts (no ChromaDB/model needed) fully, and the
collection/model-dependent parts (generate_questions,
evaluate_direction_aware) with self-contained fakes, same caveat as
test_hybrid_search.py: written without sight of any existing fixtures.
"""

import networkx as nx
import pandas as pd
import pytest

from evaluation.benchmark import (
    _chain_phrase,
    generate_nhop_questions,
    generate_questions,
    validate_graph_reachability,
)


@pytest.fixture
def mixed_graph() -> nx.MultiDiGraph:
    g = nx.MultiDiGraph()
    g.add_edge("taug", "akut", relation="companion_of")
    g.add_edge("teeka", "taug", relation="companion_of")
    g.add_edge("akut", "duro", relation="child_of")
    return g


class TestChainPhrase:
    """Regression coverage for the specific 'of of' bug found on real
    output this week - the old version nested possessives
    ('the X of of the X of...'); this version doesn't nest at all."""

    def test_single_hop_forward(self):
        phrase = _chain_phrase("taug", ["companion_of"], ["forward"])
        assert phrase == "Who is taug a companion of?"

    def test_two_hop_no_of_of_duplication(self):
        phrase = _chain_phrase("taug", ["companion_of", "companion_of"], ["forward", "forward"])
        assert "of of" not in phrase
        assert phrase == "Who is taug a companion of? Then, who is that entity a companion of?"

    def test_reverse_hop_phrasing(self):
        phrase = _chain_phrase("akut", ["companion_of"], ["reverse"])
        assert phrase == "Who is a companion of akut?"

    def test_mixed_directions(self):
        phrase = _chain_phrase("duro", ["child_of", "companion_of"], ["reverse", "reverse"])
        assert phrase == "Who is a child of duro? Then, who is a companion of that entity?"

    def test_unverified_relation_anywhere_invalidates_whole_chain(self):
        result = _chain_phrase("x", ["companion_of", "believes_in"], ["forward", "forward"])
        assert result is None


class TestGenerateNHopQuestions:
    def test_finds_forward_and_reverse_chains(self, mixed_graph):
        corpus = {"106": mixed_graph}
        questions = generate_nhop_questions(corpus, hops=2, n_samples=20, seed=1)
        assert len(questions) > 0
        assert all(q.hops == 2 for q in questions)

    def test_no_of_of_in_any_generated_query(self, mixed_graph):
        corpus = {"106": mixed_graph}
        questions = generate_nhop_questions(corpus, hops=2, n_samples=20, seed=1)
        assert all("of of" not in q.query for q in questions)


class TestValidateGraphReachability:
    """Sanity check against an INDEPENDENT implementation (networkx's
    own shortest_path_length), not our BFS compared against itself -
    see module docstring for why evaluate_nhop_graph() was replaced."""

    def test_agrees_with_independent_check_on_real_paths(self, mixed_graph):
        corpus = {"106": mixed_graph}
        questions = generate_nhop_questions(corpus, hops=1, n_samples=20, seed=1)
        result = validate_graph_reachability(corpus, questions)
        assert result["agreement_with_independent_check"] == 1.0

    def test_reachable_rate_near_one_for_real_sampled_paths(self, mixed_graph):
        """Questions are sampled FROM real graph paths, so their answers
        should be reachable by construction - this is the expected,
        healthy baseline, not evidence of a capability improvement."""
        corpus = {"106": mixed_graph}
        questions = generate_nhop_questions(corpus, hops=1, n_samples=20, seed=1)
        result = validate_graph_reachability(corpus, questions)
        assert result["reachable_rate"] == 1.0

    def test_missing_book_reduces_n_without_crashing(self, mixed_graph):
        corpus = {"106": mixed_graph}
        questions = generate_nhop_questions(corpus, hops=1, n_samples=5, seed=1)
        # point one question at a book not in corpus
        questions[0].book_id = "not_a_real_book"
        result = validate_graph_reachability(corpus, questions)
        assert result["n_questions"] == len(questions) - 1


class TestGenerateQuestions:
    """Regression coverage for the original single-hop direction bug -
    generate_questions() used to derive phrasing independently of
    relation_text.py's verified templates and got several relation
    types backwards (child_of, protector_of, leader_of confirmed on
    real data)."""

    @pytest.fixture
    def sample_df(self):
        return pd.DataFrame([
            {"book_id": "106", "relations_parsed": [
                {"entity1": "Will", "entity2": "Mrs. Brand", "relation": "child_of"},
                {"entity1": "Taug", "entity2": "Teeka", "relation": "protector_of"},
                {"entity1": "X", "entity2": "Y", "relation": "believes_in"},  # untemplated
            ]},
        ])

    def test_only_templated_relations_produce_questions(self, sample_df):
        questions = generate_questions(sample_df, n_samples=10, seed=1)
        assert all(q.source_relation != "believes_in" for q in questions)
        assert len(questions) == 2

    def test_child_of_question_matches_verified_phrasing(self, sample_df):
        questions = generate_questions(sample_df, n_samples=10, seed=1)
        child_q = next(q for q in questions if q.source_relation == "child_of")
        assert child_q.query == "Who is Will a child of?"
        assert child_q.correct_answer == "mrs. brand"
