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