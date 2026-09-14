# tests/test_relation_text.py
"""Tests for embedding.relation_text."""

from embedding.relation_text import relation_to_sentence


def test_manual_template_used_when_available() -> None:
    sentence = relation_to_sentence("Taug", "Tarzan", "companion_of")
    assert sentence == "Taug is a companion of Tarzan"


def test_manual_template_preserves_direction() -> None:
    """owned_by: entity1=thing owned, entity2=owner (per ARF paper example
    'Thornfield Hall is owned_by Mr. Rochester')."""
    sentence = relation_to_sentence("Thornfield Hall", "Mr. Rochester", "owned_by")
    assert sentence == "Thornfield Hall is owned by Mr. Rochester"


def test_generic_fallback_for_untemplated_canonical_relation() -> None:
    sentence = relation_to_sentence("Goku", "Nimbus cloud", "travels_by")
    assert sentence == "Goku travels by Nimbus cloud"


def test_generic_fallback_for_non_canonical_relation() -> None:
    """Free-text deviations from the ontology should still produce
    readable (if imperfect) text, not crash."""
    sentence = relation_to_sentence("Tarzan", "Numa", "screaming at")
    assert sentence == "Tarzan screaming at Numa"
    
# --- Additions for Week 7's new functions in embedding/relation_text.py ---
# Append these to the existing test_relation_text.py - written without
# sight of that file's current imports/fixtures, so reconcile naming
# and style with whatever's already there before merging.

import pytest

from embedding.relation_text import (
    MANUAL_TEMPLATES,
    get_anchor_phrase,
    relation_to_question,
)


class TestGetAnchorPhrase:
    def test_extracts_predicate_between_entity_slots(self):
        assert get_anchor_phrase("protector_of") == "a protector of"
        assert get_anchor_phrase("parent_mother_of") == "the mother of"

    def test_unknown_relation_returns_none(self):
        assert get_anchor_phrase("not_a_real_relation") is None

    def test_travel_to_has_a_generic_short_anchor(self):
        """travel_to's anchor is 'to' - technically extracted fine by
        get_anchor_phrase, but too generic to safely use for position
        matching (see MIN_ANCHOR_LENGTH in direction_detection.py,
        added after this specific case caused false positives)."""
        assert get_anchor_phrase("travel_to") == "to"


class TestRelationToQuestionForward:
    """The bug this function exists to fix: generate_questions() used
    to derive phrasing independently of these templates, producing
    questions that asked the opposite of their own ground truth for
    several relation types. These are the exact confirmed-reversed
    cases from real corpus data."""

    def test_child_of_asks_for_parent_not_child(self):
        q = relation_to_question("Will", "child_of")
        assert q == "Who is Will a child of?"

    def test_protector_of_asks_who_is_protected(self):
        q = relation_to_question("Taug", "protector_of")
        assert q == "Who is Taug a protector of?"

    def test_leader_of_asks_what_is_led(self):
        q = relation_to_question("King Arthur", "leader_of")
        assert q == "Who is King Arthur a leader of?"

    def test_travel_to_uses_override_not_broken_wh_fronting(self):
        """travel_to has no copula - without the override, mechanical
        wh-fronting would produce broken English."""
        q = relation_to_question("Bob", "travel_to")
        assert q == "Where does Bob travel to?"

    def test_unverified_relation_returns_none(self):
        assert relation_to_question("X", "believes_in") is None


class TestRelationToQuestionReverse:
    def test_reverse_is_simple_subject_substitution(self):
        q = relation_to_question("taug", "protector_of", direction="reverse")
        assert q == "Who is a protector of taug?"

    def test_reverse_works_for_travel_to_without_special_casing(self):
        """Unlike forward, reverse needs no override - confirmed during
        development that plain template substitution works uniformly
        even for the one copula-less template."""
        q = relation_to_question("paris", "travel_to", direction="reverse")
        assert q == "Who travels to paris?"