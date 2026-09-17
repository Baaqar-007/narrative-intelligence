

import pytest

from retrieval.direction_detection import (
    VERB_FORM_OVERRIDES,
    detect_query_direction,
    direction_match,
    entity_to_expand_from,
    estimate_hop_depth,
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

    def test_short_entity_substring_of_unrelated_name_does_not_false_positive(self):
        """Regression test for a second real bug: 'An' (a short entity
        name) matched as a substring of the unrelated name 'Ann' via
        plain .find(), producing a confidently wrong direction for a
        sentence actually about a different person. Fixed via
        word-boundary regex matching."""
        result = detect_query_direction(
            "Ann is a leader of the settlers.", "An", "leader_of",
        )
        assert result is None


class TestArticleVariants:
    """Regression coverage for a real gap found integrating this into
    hybrid_search: 15/31 templates use 'a'/'an' as their anchor's
    article, but 'the X of Y' is equally natural English and was
    being missed entirely."""

    def test_the_article_matches_where_a_article_template_exists(self):
        result = detect_query_direction(
            "who protects the friend of the knight?", "knight", "friend_of",
        )
        assert result is not None  # was None before the fix

    def test_a_article_still_works_as_before(self):
        result = detect_query_direction(
            "Who is a friend of Taug?", "Taug", "friend_of",
        )
        assert result == "reverse"


class TestDirectionMatch:
    def test_matching_direction_returns_true(self):
        fact = {"entity1": "Taug", "entity2": "Teeka", "relation": "protector_of"}
        assert direction_match("Who is Taug a protector of?", fact) is True

    def test_mismatched_direction_returns_false(self):
        """The exact scenario that motivated this whole feature: a
        query phrased in the opposite direction from how the fact
        happens to be stored."""
        fact = {"entity1": "knight", "entity2": "squire", "relation": "friend_of"}
        assert direction_match("who protects the friend of the knight?", fact) is False

    def test_undetermined_returns_none_not_a_guess(self):
        fact = {"entity1": "X", "entity2": "Y", "relation": "believes_in"}
        assert direction_match("Who does X believe in?", fact) is None


class TestEntityToExpandFrom:
    """Regression coverage for the previously-hardcoded 'always
    entity2' default in hybrid_search.py - these specifically check
    that REAL logic engaged, not that the fallback happened to produce
    the same answer (a real gap this exact test class exists to catch,
    found while integrating this into hybrid_search)."""

    def test_forward_query_expands_from_entity2(self):
        result = entity_to_expand_from("Who is Taug a protector of?", "Taug", "Teeka", "protector_of")
        assert result == "Teeka"

    def test_reverse_query_expands_from_entity1_not_the_old_default(self):
        """The actual behavior change this feature exists to make -
        must NOT just fall back to entity2."""
        result = entity_to_expand_from("Who protects Taug?", "Taug", "Teeka", "protector_of")
        assert result == "Taug"

    def test_undetermined_falls_back_to_entity2(self):
        """Preserves the original pre-Week-7 default when direction
        genuinely can't be determined - not a regression."""
        result = entity_to_expand_from("What is the weather?", "Taug", "Teeka", "protector_of")
        assert result == "Teeka"


class TestEstimateHopDepth:
    """UNVALIDATED against real free-text queries (see the function's
    own docstring) - these tests cover the reasoning it was built on,
    not a claim that the reasoning is correct in general."""

    def test_single_relation_needs_no_extra_hops(self):
        assert estimate_hop_depth("Who is Taug a companion of?") == 0

    def test_the_actual_motivating_two_hop_example(self):
        """Regression test for a real bug: verb-form matching originally
        used word-boundary regex (copied from entity matching by
        analogy without checking it applied), which broke on
        conjugated forms - 'protect' doesn't word-boundary-match inside
        'protects'. Fixed to match detect_query_direction's existing,
        already-correct plain substring approach."""
        assert estimate_hop_depth("who protects the friend of the knight?") == 1

    def test_three_distinct_relations_gives_two_hops(self):
        query = "Who is the leader of the protector of the friend of the knight?"
        assert estimate_hop_depth(query) == 2

    def test_no_relations_mentioned_gives_zero(self):
        assert estimate_hop_depth("What is the weather today?") == 0

    def test_known_limitation_same_relation_twice_undercounts(self):
        """Documented, not hidden: counting DISTINCT relation types
        means a genuine 2-hop same-relation chain ('the companion of
        the companion of X') is under-counted to 0. This test pins
        down the known limitation so it can't silently change without
        the change being noticed."""
        assert estimate_hop_depth("the companion of the companion of Taug") == 0

    def test_respects_max_hops_cap(self):
        many_relations = ("Who is the leader of the protector of the friend of the "
                           "companion of the enemy of the rival of the mentor of Taug?")
        assert estimate_hop_depth(many_relations, max_hops=3) == 3
