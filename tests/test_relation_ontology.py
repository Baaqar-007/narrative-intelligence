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