"""ChromaDB storage and retrieval for relation embeddings."""

import chromadb

from embedding.embed_relations import EmbeddingRecord

COLLECTION_NAME = "arf_relations"
CHROMA_PATH = "../data/chroma"


def get_collection(path: str = CHROMA_PATH):
    """Connect to (or create) the persistent ChromaDB collection.

    Args:
        path: Filesystem path where ChromaDB persists its data.

    Returns:
        The ChromaDB collection handle.
    """
    client = chromadb.PersistentClient(path=path)
    return client.get_or_create_collection(name=COLLECTION_NAME)


def add_records(collection, records: list[EmbeddingRecord], embeddings: list[list[float]], batch_size: int = 5000) -> None:
    """Add records and their embeddings to the collection, in batches.

    Args:
        collection: A ChromaDB collection (see get_collection()).
        records: The EmbeddingRecords to store.
        embeddings: Parallel list of embedding vectors, same order/length as records.
        batch_size: ChromaDB has an internal max batch size; chunk large
            inserts to stay under it (128K records in one call may fail).
    """
    for start in range(0, len(records), batch_size):
        batch_records = records[start:start + batch_size]
        batch_embeddings = embeddings[start:start + batch_size]

        collection.add(
            ids=[r.id for r in batch_records],
            embeddings=batch_embeddings,
            documents=[r.text for r in batch_records],
            metadatas=[
                {
                    "book_id": r.book_id,
                    "chunk_id": r.chunk_id,
                    "entity1": r.entity1,
                    "entity2": r.entity2,
                    "relation": r.relation,
                }
                for r in batch_records
            ],
        )
        print(f"Added {min(start + batch_size, len(records)):,} / {len(records):,}")

def query_relations(collection, query_text: str, model, n_results: int = 5, book_id: str | None = None) -> dict:
    """Semantic search over stored relation embeddings.

    Args:
        collection: A ChromaDB collection (see get_collection()).
        query_text: Natural-language query, e.g. "who protected Taug".
        model: A pre-loaded SentenceTransformer, used to embed the query
            the same way relations were embedded (same model required
            for meaningful similarity comparison).
        n_results: How many top matches to return.
        book_id: If given, restrict results to this book only.

    Returns:
        Raw ChromaDB query result (ids, documents, metadatas, distances).
    """
    query_embedding = model.encode([query_text]).tolist()

    where_filter = {"book_id": book_id} if book_id else None

    return collection.query(
        query_embeddings=query_embedding,
        n_results=n_results,
        where=where_filter,
    )