# tests/test_canonicalization.py
"""Tests for graph.canonicalization."""

from graph.canonicalization import normalize_entity_name


def test_strips_appositive_descriptor() -> None:
    assert normalize_entity_name("Bolgani, the gorilla") == "bolgani"
    assert normalize_entity_name("Numa, the lion") == "numa"


def test_lowercases_and_strips_whitespace() -> None:
    assert normalize_entity_name("  Tarzan  ") == "tarzan"


def test_leaves_plain_names_unchanged() -> None:
    assert normalize_entity_name("Bulabantu") == "bulabantu"


def test_idempotent() -> None:
    """Normalizing an already-normalized name should be a no-op."""
    once = normalize_entity_name("Bolgani, the gorilla")
    twice = normalize_entity_name(once)
    assert once == twice