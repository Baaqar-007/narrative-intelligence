"""Tests for retrieval/direction_detection.py.

Covers the anchor-phrase + verb-form design (Week 7) and specifically
pins down failures found while designing it, so they can't silently
reappear: the "ment" substring collision with ordinary English words
(mentioned, sentiment), and the general absence of a verb form for
relations that don't have one (member_of).
"""

import pytest

from retrieval.direction_detection import (
    VERB_FORM_OVERRIDES,
    detect_query_direction,
)


class TestAnchorPhraseMatching:
    """Cases where the query uses the relation's exact noun-phrase
    template wording."""

    @pytest.mark.parametrize("query,entity,relation,expected", [
        ("Who is Taug a protector of?", "Taug", "protector_of", "forward"),
        ("Who is a protector of Taug?", "Taug", "protector_of", "reverse"),
        ("Who is Taug a companion of?", "Taug", "companion_of", "forward"),
        ("Who is a companion of Taug?", "Taug", "companion_of", "reverse"),
        ("Who is Taug the mother of?", "Taug", "parent_mother_of", "forward"),
        ("Who is the mother of Taug?", "Taug", "parent_mother_of", "reverse"),
    ])
    def test_direction_from_anchor_position(self, query, entity, relation, expected):
        assert detect_query_direction(query, entity, relation) == expected


class TestVerbFormFallback:
    """Cases where the query uses a bare verb instead of the noun-phrase
    template - the original gap this fallback exists to close."""

    @pytest.mark.parametrize("query,entity,relation,expected", [
        ("Who does Taug protect?", "Taug", "protector_of", "forward"),
        ("Who protects Taug?", "Taug", "protector_of", "reverse"),
        ("Who does Taug lead?", "Taug", "leader_of", "forward"),
        ("Who leads Taug?", "Taug", "leader_of", "reverse"),
        ("Who mentors Taug?", "Taug", "mentor_of", "reverse"),
        ("Who does Taug mentor?", "Taug", "mentor_of", "forward"),
    ])
    def test_direction_from_verb_form(self, query, entity, relation, expected):
        assert detect_query_direction(query, entity, relation) == expected

    def test_every_override_is_a_real_verb_not_a_mechanical_stem(self):
        """Regression test for the rejected approach: a naive -er/-or
        suffix strip produced broken stems (mother->moth, mentor->ment,
        lover->lov). This just asserts the override dict wasn't
        silently reverted to that mechanical derivation - not a
        linguistic correctness check, just a tripwire."""
        broken_stems = {"moth", "ment", "lov", "fath", "memb"}
        assert not (set(VERB_FORM_OVERRIDES.values()) & broken_stems)


class TestSafeFailure:
    """Cases that must return None rather than guess - a wrong answer
    is worse than no answer."""

    def test_relation_with_no_template_returns_none(self):
        assert detect_query_direction("Who does Taug believe in?", "Taug", "believes_in") is None

    def test_relation_with_no_verb_form_and_no_anchor_match_returns_none(self):
        """member_of has a template (anchor phrase) but no verb form -
        a bare-verb-style query for it must decline, not guess."""
        assert "member_of" not in VERB_FORM_OVERRIDES
        assert detect_query_direction("Who does Taug belong with?", "Taug", "member_of") is None

    def test_entity_not_in_query_returns_none(self):
        assert detect_query_direction("What is the capital of France?", "Taug", "protector_of") is None

    def test_ment_substring_does_not_false_positive(self):
        """Regression test for the specific bug caught while designing
        this: the naive stem 'ment' matched inside 'mentioned' and
        'sentiment'. The real override is the full word 'mentor',
        which must NOT match as a substring of unrelated words."""
        result = detect_query_direction(
            "What did Taug think about the sentiment of the crowd?",
            "Taug", "mentor_of",
        )
        assert result is None

    def test_mentioned_does_not_false_positive(self):
        result = detect_query_direction(
            "Was Taug mentioned in the will?", "Taug", "mentor_of",
        )
        assert result is None

    def test_travel_to_generic_anchor_does_not_false_positive(self):
        """Regression test for a real bug caught during test-writing
        itself: travel_to's anchor phrase is just 'to' - a 2-character
        anchor that matched inside any query containing the word 'to'
        at all, confidently misclassifying completely unrelated
        queries. Fixed via MIN_ANCHOR_LENGTH."""
        result = detect_query_direction(
            "Who wants to know where Bob went?", "Bob", "travel_to",
        )
        assert result is None
