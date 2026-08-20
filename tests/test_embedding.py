# tests/test_embedding.py
"""Tests for embedding.embed_relations.

Deliberately does not test embed_records() itself - it's a thin wrapper
around SentenceTransformer.encode() with no branching logic, and loading
the real model would make the test suite slow (~3 min one-time cost).
"""

import pandas as pd

from embedding.embed_relations import (
    build_embedding_records,
    deduplicate_chunk_relations,
)


def test_deduplicate_removes_exact_repeats() -> None:
    """The 35x-repeat case from Week 3 Day 2 findings, simplified."""
    relations = [
        {"entity1": "his", "entity2": "his mother", "relation": "child_of"},
        {"entity1": "his", "entity2": "his mother", "relation": "child_of"},
        {"entity1": "his", "entity2": "his mother", "relation": "child_of"},
    ]
    deduped = deduplicate_chunk_relations(relations)
    assert len(deduped) == 1


def test_deduplicate_keeps_distinct_relations() -> None:
    """Different entity2 in the same chunk should NOT be deduplicated
    (this was the real risk with the original chunk_id+entity1+relation
    ID scheme - see Week 3 Day 2)."""
    relations = [
        {"entity1": "Tarzan", "entity2": "Taug", "relation": "companion_of"},
        {"entity1": "Tarzan", "entity2": "Teeka", "relation": "companion_of"},
    ]
    deduped = deduplicate_chunk_relations(relations)
    assert len(deduped) == 2


def test_build_embedding_records_generates_correct_text_and_ids() -> None:
    df = pd.DataFrame([
        {
            "book_id": "106",
            "chunk_id": "10",
            "relations_parsed": [
                {"entity1": "Taug", "entity2": "Tarzan", "relation": "companion_of"}
            ],
        }
    ])
    records = build_embedding_records(df)

    assert len(records) == 1
    assert records[0].id == "106_10_Taug_Tarzan_companion_of"
    assert records[0].text == "Taug is a companion of Tarzan"


def test_build_embedding_records_disambiguates_cross_chunk_duplicates() -> None:
    """Safety net for the rare case where the same base key appears in
    two different rows even after within-chunk dedup - should get
    distinct IDs via the occurrence suffix, not silently collide.
    """
    df = pd.DataFrame([
        {
            "book_id": "106",
            "chunk_id": "10",
            "relations_parsed": [
                {"entity1": "Taug", "entity2": "Tarzan", "relation": "companion_of"}
            ],
        },
        {
            "book_id": "106",
            "chunk_id": "10",  # duplicate row, same chunk_id, hypothetically
            "relations_parsed": [
                {"entity1": "Taug", "entity2": "Tarzan", "relation": "companion_of"}
            ],
        },
    ])
    records = build_embedding_records(df)

    ids = [r.id for r in records]
    assert len(ids) == len(set(ids)), "IDs must be unique even for repeated base keys"
    assert ids[0] == "106_10_Taug_Tarzan_companion_of"
    assert ids[1] == "106_10_Taug_Tarzan_companion_of_1"