# embedding/embed_relations.py
"""Generates sentence embeddings for ARF relation instances.

Deduplicates exact-repeat relation extractions within a chunk before
embedding (see Week 3 Day 2 findings - GPT-4o occasionally emits the
same relation dict multiple times for a single underlying fact, e.g.
35x repeats of one 'child_of' relation in a single chunk). The graph
itself remains untouched/faithful to raw ARF data; this dedup applies
only to the embedding pipeline's input.
"""

from dataclasses import dataclass

import pandas as pd
from sentence_transformers import SentenceTransformer

from embedding.relation_text import relation_to_sentence

MODEL_NAME = "all-MiniLM-L6-v2"


@dataclass
class EmbeddingRecord:
    """One relation instance, ready to embed and store."""

    id: str
    text: str
    book_id: str
    chunk_id: int
    entity1: str
    entity2: str
    relation: str


def deduplicate_chunk_relations(relations: list[dict]) -> list[dict]:
    """Drop exact-duplicate relation dicts within a single chunk.

    Args:
        relations: Parsed relations for one chunk (relations_parsed).

    Returns:
        The list with exact duplicates removed, order preserved.
    """
    seen: set[tuple[str, str, str]] = set()
    deduped = []
    for r in relations:
        key = (r["entity1"], r["entity2"], r["relation"])
        if key not in seen:
            seen.add(key)
            deduped.append(r)
    return deduped


def build_embedding_records(df: pd.DataFrame) -> list[EmbeddingRecord]:
    """Build one EmbeddingRecord per (deduplicated) relation instance.

    Handles the remaining rare cross-chunk duplicate case (same
    book_id/chunk_id/entity1/entity2/relation appearing more than once
    even after within-chunk dedup - not expected after dedup, but
    guarded via an occurrence suffix for safety) by appending an
    occurrence index to the ID if a base ID repeats.

    Args:
        df: Parsed ARF dataframe with 'book_id', 'chunk_id', and
            'relations_parsed' columns.

    Returns:
        A list of EmbeddingRecords, ready for embedding + storage.
    """
    records: list[EmbeddingRecord] = []
    id_occurrences: dict[str, int] = {}

    for _, row in df.iterrows():
        deduped = deduplicate_chunk_relations(row["relations_parsed"])

        for r in deduped:
            base_id = f"{row['book_id']}_{row['chunk_id']}_{r['entity1']}_{r['entity2']}_{r['relation']}"
            count = id_occurrences.get(base_id, 0)
            id_occurrences[base_id] = count + 1
            record_id = f"{base_id}_{count}" if count else base_id

            text = relation_to_sentence(r["entity1"], r["entity2"], r["relation"])

            records.append(EmbeddingRecord(
                id=record_id,
                text=text,
                book_id=row["book_id"],
                chunk_id=int(row["chunk_id"]),
                entity1=r["entity1"],
                entity2=r["entity2"],
                relation=r["relation"],
            ))

    return records


def load_embedding_model(model_name: str = MODEL_NAME) -> SentenceTransformer:
    """Load the sentence embedding model once, for reuse across calls.

    Args:
        model_name: Sentence Transformers model identifier.

    Returns:
        The loaded model, ready to pass into embed_records().
    """
    return SentenceTransformer(model_name)


def embed_records(records: list[EmbeddingRecord], model: SentenceTransformer) -> list[list[float]]:
    """Generate embedding vectors for a list of records.

    Args:
        records: Output of build_embedding_records().
        model: A pre-loaded SentenceTransformer (see load_embedding_model()).
            Caller-provided so the model is loaded once and reused across
            many calls, rather than reloaded (a ~3 minute cost) per call.

    Returns:
        A list of embedding vectors, one per record, same order.
    """
    texts = [r.text for r in records]
    embeddings = model.encode(texts, show_progress_bar=True)
    return embeddings.tolist()