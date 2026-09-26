"""Decompose WHY each question returns 0 chains on 40882 - vector
recall miss, untemplated relation, target_relation() detection
failure, or genuine canonicalization mismatch. Same questions as
diagnose_chain_hubs.py; run after that script confirmed 0 across all
10, to avoid re-asserting the same conclusion without checking it."""

import re
from pathlib import Path

from embedding.embed_relations import load_embedding_model
from embedding.relation_text import MANUAL_TEMPLATES
from embedding.vector_store import get_collection
from graph.corpus import load_corpus
from retrieval.direction_detection import (
    detect_query_direction, entity_to_expand_from, target_relation,
)

DATA_DIR = Path("data")
BOOK_ID_MAIN = "40882"

TEST_QUESTIONS = [
    "Who is the mother of Esther Lyon's husband?",
    "Who is the father of Felix Holt's wife?",
    "Who is the biological father of Mrs. Transome's son?",
    "Who is the servant loyal to Harold Transome's mother?",
    "Who is the mother of Rufus Lyon's daughter's husband?",
    "Who is the father of Mrs. Holt's son's wife?",
    "Who is the lawyer that manages the estate of Mrs. Transome's son?",
    "Who is the mother of Matthew Jermyn's biological son?",
    "Who is the Conservative candidate against Mrs. Transome's son?",
    "Who is Mrs. Holt's son's wife?",
]


def _entity_in_query(query_lower: str, entity: str) -> bool:
    return re.search(r"\b" + re.escape(entity.lower()) + r"\b", query_lower) is not None


def diagnose(question, book_id, collection, model):
    q_lower = question.lower()
    q_target = target_relation(question)

    query_embedding = model.encode([question]).tolist()
    results = collection.query(
        query_embeddings=query_embedding, n_results=5,
        where={"book_id": book_id},
    )

    print(f"\n=== {question!r} ===")
    print(f"  target_relation(query) = {q_target!r}"
          f"{' <- FAIL: outer relation not detected' if q_target is None else ''}")

    if not results["metadatas"][0]:
        print("  ** No vector hits at all **")
        return

    for meta in results["metadatas"][0]:
        e1, e2, rel = meta["entity1"], meta["entity2"], meta.get("relation")
        templated = rel in MANUAL_TEMPLATES
        e1_present = _entity_in_query(q_lower, e1)
        e2_present = _entity_in_query(q_lower, e2)
        expand = entity_to_expand_from(question, e1, e2, rel or "") if templated else None

        bucket = "OK - resolved"
        if not templated:
            bucket = "UNTEMPLATED RELATION (not a canonicalization issue)"
        elif expand is None:
            if not e1_present and not e2_present:
                bucket = "NEITHER ENTITY STRING IN QUERY - check: recall miss, or genuine canonicalization gap?"
            else:
                bucket = "ENTITY PRESENT BUT DIRECTION UNDETECTED - phrasing gap (fix b/c), not canonicalization"

        print(f"  hit: ({e1!r}, {e2!r}, {rel!r})"
              f"  e1_in_query={e1_present} e2_in_query={e2_present}"
              f"  expand_from={expand!r}")
        print(f"    -> {bucket}")


def main():
    corpus = load_corpus(DATA_DIR / "graphs" / "corpus.pkl")  # unused here, kept for parity
    collection = get_collection(path=str(DATA_DIR / "chroma"))
    model = load_embedding_model()
    for q in TEST_QUESTIONS:
        diagnose(q, BOOK_ID_MAIN, collection, model)


if __name__ == "__main__":
    main()