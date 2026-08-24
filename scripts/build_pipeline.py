"""Builds the full NIE data pipeline, start to finish, with no notebook
required.

Run once (or whenever source data / pipeline logic changes):
    python scripts/build_pipeline.py

Produces, all under data/ (gitignored, fully reproducible from this
script):
    data/arf_chunks_parsed.parquet   - cleaned dataset
    data/graphs/corpus.pkl           - per-book knowledge graphs
    data/embeddings/relation_embeddings.pkl - embedding records + vectors
    data/chroma/                     - persisted ChromaDB vector store

Each stage prints its own timing and summary stats, so a failure or
slowdown is immediately visible - no more guessing whether a notebook
cell hung, or scrolling for the source of a bug.
"""

import pickle
import time
from pathlib import Path
import chromadb
from embedding.embed_relations import build_embedding_records, embed_records, load_embedding_model
from embedding.vector_store import add_records, get_collection, COLLECTION_NAME
from graph.corpus import build_corpus_graphs, save_corpus
from .load_data import load_and_clean_arf

DATA_DIR = Path("data")


def _step(label: str):
    """Small timing context manager, so every stage reports its own cost."""
    class _Timer:
        def __enter__(self):
            print(f"\n=== {label} ===")
            self.start = time.time()
            return self

        def __exit__(self, *args):
            print(f"[{label}] done in {time.time() - self.start:.1f}s")

    return _Timer()


def main():
    DATA_DIR.mkdir(exist_ok=True)

    with _step("1/5 Load + clean ARF dataset"):
        valid = load_and_clean_arf()
        print(f"Rows: {len(valid):,}")
        valid.to_parquet(DATA_DIR / "arf_chunks_parsed.parquet", index=False)

    with _step("2/5 Build per-book knowledge graphs"):
        corpus = build_corpus_graphs(valid)
        total_nodes = sum(g.number_of_nodes() for g in corpus.values())
        total_edges = sum(g.number_of_edges() for g in corpus.values())
        print(f"Books: {len(corpus)}, nodes: {total_nodes:,}, edges: {total_edges:,}")
        save_corpus(corpus, DATA_DIR / "graphs" / "corpus.pkl")

    with _step("3/5 Build embedding records + generate embeddings"):
        records = build_embedding_records(valid)
        print(f"Records after dedup: {len(records):,}")

        model = load_embedding_model()
        embeddings = embed_records(records, model)

        (DATA_DIR / "embeddings").mkdir(exist_ok=True)
        with open(DATA_DIR / "embeddings" / "relation_embeddings.pkl", "wb") as f:
            pickle.dump({"records": records, "embeddings": embeddings}, f)

    with _step("4/5 Ingest into ChromaDB"):
        chroma_path = str(DATA_DIR / "chroma")
        client = chromadb.PersistentClient(path=chroma_path)
        try:
            client.delete_collection(name=COLLECTION_NAME)
        except Exception:
            pass  # nothing to delete on a first run
        collection = get_collection(path=chroma_path)
        add_records(collection, records, embeddings)
        print(f"Total in collection: {collection.count():,}")

    with _step("5/5 Sanity check"):
        assert collection.count() == len(records), "Collection count doesn't match records built"
        print("Pipeline built successfully. Ready for scripts/run_benchmarks.py or the API.")


if __name__ == "__main__":
    main()
