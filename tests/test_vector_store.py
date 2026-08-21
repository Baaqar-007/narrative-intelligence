# tests/test_vector_store.py
"""Tests for embedding.vector_store.

Uses an in-memory (non-persistent) ChromaDB client so tests don't
touch disk or require the real corpus - fast, isolated.
"""

import chromadb
import pytest

from embedding.embed_relations import EmbeddingRecord
from embedding.vector_store import add_records

import uuid

@pytest.fixture
def empty_collection():
    client = chromadb.Client()
    collection_name = f"test_collection_{uuid.uuid4().hex[:8]}"
    return client.get_or_create_collection(name=collection_name)



def _make_record(i: int) -> EmbeddingRecord:
    return EmbeddingRecord(
        id=f"rec_{i}",
        text=f"entity{i} is a companion of entity{i+1}",
        book_id="test_book",
        chunk_id=i,
        entity1=f"entity{i}",
        entity2=f"entity{i+1}",
        relation="companion_of",
    )


def test_add_records_stores_correct_count(empty_collection) -> None:
    records = [_make_record(i) for i in range(10)]
    embeddings = [[0.1, 0.2, 0.3] for _ in records]  # fake, fixed-dim vectors

    add_records(empty_collection, records, embeddings, batch_size=5)

    assert empty_collection.count() == 10


def test_add_records_batches_correctly_at_boundary(empty_collection) -> None:
    records = [_make_record(i) for i in range(6)]
    embeddings = [[0.1, 0.2, 0.3] for _ in records]

    add_records(empty_collection, records, embeddings, batch_size=3)

    assert empty_collection.count() == 6


def test_add_records_preserves_metadata(empty_collection) -> None:
    records = [_make_record(0)]
    embeddings = [[0.1, 0.2, 0.3]]

    add_records(empty_collection, records, embeddings)

    result = empty_collection.get(ids=["rec_0"])
    assert result["metadatas"][0]["entity1"] == "entity0"
    assert result["metadatas"][0]["relation"] == "companion_of"