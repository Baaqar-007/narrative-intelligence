# tests/test_relation_ontology.py
"""Tests for graph.relation_ontology."""

from graph.relation_ontology import is_canonical_relation


def test_common_canonical_relations() -> None:
    assert is_canonical_relation("companion_of")
    assert is_canonical_relation("protector_of")
    assert is_canonical_relation("relative_of")


def test_free_text_deviations_are_not_canonical() -> None:
    """Real deviation examples found in our corpus (see Week 1 findings)."""
    assert not is_canonical_relation("screaming at")
    assert not is_canonical_relation("spared the life of")
    assert not is_canonical_relation("wept like")
    

from graph.relation_ontology import SYMMETRIC_RELATIONS

class TestSymmetricRelations:
    def test_contains_the_seven_confirmed_types(self):
        """These 7 are what README's Week 2 finding and this week's
        traversal work were based on - graph/traversal.py and
        retrieval/hybrid_search.py both depend on this exact set."""
        expected = {
            "companion_of", "friend_of", "enemy_of", "rival_of",
            "sibling_of", "spouse_of", "relative_of",
        }
        assert SYMMETRIC_RELATIONS == expected

    def test_is_a_set_not_a_list_or_tuple(self):
        """graph/traversal.py does membership checks (`in`) in a hot
        loop - a list would still work but degrade performance at
        scale; confirms the type contract other modules assume."""
        assert isinstance(SYMMETRIC_RELATIONS, set)

    def test_known_asymmetric_relations_are_not_included(self):
        """Sanity check on the boundary - relations known to be
        genuinely direction-sensitive must not accidentally be here."""
        asymmetric_examples = {"child_of", "leader_of", "employer_of", "owned_by"}
        assert not (SYMMETRIC_RELATIONS & asymmetric_examples)