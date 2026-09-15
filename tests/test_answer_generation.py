"""Tests for retrieval/answer_generation.py.

Covers the fix for a real gap found this session: hit.chains and the
query_direction_match annotation were both computed correctly upstream
by hybrid_search() but never rendered into the LLM prompt at all -
meaning neither of Week 7's actual features reached an answer. These
tests cover the pure-logic rendering functions directly; generate_answer()
itself (the live Groq call) isn't tested here.
"""

import pytest

from retrieval.answer_generation import _chain_line, _fact_line, _facts_to_text
from retrieval.hybrid_search import EnrichedHit


class TestFactLine:
    def test_matching_direction_has_no_warning_note(self):
        fact = {"entity1": "Taug", "entity2": "Teeka", "relation": "protector_of",
                "chunk_id": 5, "query_direction_match": True}
        line = _fact_line(fact)
        assert "Note" not in line

    def test_mismatched_direction_includes_warning_note(self):
        fact = {"entity1": "knight", "entity2": "squire", "relation": "friend_of",
                "chunk_id": 1, "query_direction_match": False}
        line = _fact_line(fact)
        assert "OPPOSITE direction" in line

    def test_undetermined_direction_has_no_warning_note(self):
        """None means direction couldn't be determined, not that it's
        wrong - shouldn't be flagged as a mismatch."""
        fact = {"entity1": "X", "entity2": "Y", "relation": "believes_in",
                "chunk_id": 2, "query_direction_match": None}
        line = _fact_line(fact)
        assert "Note" not in line

    def test_missing_key_treated_as_no_warning(self):
        """Defensive: a fact dict without query_direction_match at all
        (e.g. constructed by older code) must not crash."""
        fact = {"entity1": "X", "entity2": "Y", "relation": "friend_of", "chunk_id": 1}
        line = _fact_line(fact)  # must not raise
        assert "Note" not in line


class TestChainLine:
    def test_forward_chain_renders_correct_entity_order(self):
        chain = {"start": "knight", "end": "lord", "path": ["knight", "squire", "lord"],
                  "relations": ["friend_of", "protector_of"], "directions": ["forward", "forward"]}
        line = _chain_line(chain)
        assert line == "- knight is a friend of squire. squire is a protector of lord."

    def test_reverse_hop_reconstructs_entity_order_correctly(self):
        """The harder case - a reverse-traversed hop must still
        produce a sentence with entities in the TRUE stored order,
        not the traversal order."""
        chain = {"start": "teeka", "end": "akut", "path": ["teeka", "taug", "akut"],
                  "relations": ["companion_of", "companion_of"], "directions": ["reverse", "forward"]}
        line = _chain_line(chain)
        assert line == "- taug is a companion of teeka. taug is a companion of akut."


class TestFactsToText:
    def test_chains_are_included_not_silently_dropped(self):
        """Regression test for the actual bug found this session:
        hit.chains was computed but never rendered at all."""
        hit = EnrichedHit(
            query_match_text="q", distance=0.1, book_id="1",
            entity1="knight", entity2="squire",
            all_relationships=[],
            chains=[{"start": "knight", "end": "lord", "path": ["knight", "squire", "lord"],
                     "relations": ["friend_of", "protector_of"], "directions": ["forward", "forward"]}],
        )
        _, chains_text = _facts_to_text([hit])
        assert chains_text != "(none)"
        assert "lord" in chains_text

    def test_empty_chains_render_as_none_placeholder(self):
        hit = EnrichedHit(query_match_text="q", distance=0.1, book_id="1",
                           entity1="a", entity2="b", all_relationships=[], chains=[])
        _, chains_text = _facts_to_text([hit])
        assert chains_text == "(none)"

    def test_duplicate_chains_across_hits_are_deduplicated(self):
        chain = {"start": "knight", "end": "lord", "path": ["knight", "squire", "lord"],
                  "relations": ["friend_of", "protector_of"], "directions": ["forward", "forward"]}
        hit1 = EnrichedHit(query_match_text="q1", distance=0.1, book_id="1",
                            entity1="knight", entity2="squire",
                            all_relationships=[], chains=[chain])
        hit2 = EnrichedHit(query_match_text="q2", distance=0.2, book_id="1",
                            entity1="knight", entity2="squire",
                            all_relationships=[], chains=[dict(chain)])
        _, chains_text = _facts_to_text([hit1, hit2])
        assert chains_text.count("knight is a friend of squire") == 1

    def test_facts_still_dedup_by_original_key_unaffected_by_new_field(self):
        """query_direction_match must not break the existing dedup
        logic (which keys on entity1/relation/entity2/chunk_id only)."""
        fact = {"entity1": "A", "entity2": "B", "relation": "friend_of",
                "chunk_id": 1, "query_direction_match": True}
        hit1 = EnrichedHit(query_match_text="q1", distance=0.1, book_id="1",
                            entity1="A", entity2="B", all_relationships=[dict(fact)], chains=[])
        hit2 = EnrichedHit(query_match_text="q2", distance=0.2, book_id="1",
                            entity1="A", entity2="B", all_relationships=[dict(fact)], chains=[])
        facts_text, _ = _facts_to_text([hit1, hit2])
        assert facts_text.count("friend of") == 1
