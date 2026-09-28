"""Extended diagnostic: checks two specific hypotheses directly,
rather than inferring them from aggregate counts (hop_depth,
total_chains) alone.

1. Does direction_match=None trace to entity-canonicalization noise
   (fact entity1/entity2 never appearing verbatim in the question),
   as opposed to a remaining gap in direction-detection logic itself?
2. Is the large total_chains count (up to 85 seen) genuine relevant
   structure, or noise from a high-degree entity being expanded from -
   sampling a few real chain paths per question, not just counting
   them, to see what's actually in there.

Run in the same environment as diagnose_pipeline.py.
"""

import csv
from pathlib import Path

from embedding.embed_relations import load_embedding_model
from embedding.vector_store import get_collection
from graph.corpus import load_corpus
from retrieval.direction_detection import estimate_hop_depth
from retrieval.hybrid_search import hybrid_search

DATA_DIR = Path("data")
BOOK_ID = "40882"  # adjust to a book you know well

# Adjust to real characters from BOOK_ID - mix phrasing styles
# deliberately, matching Part A's finding that possessive/relative/
# yes-no phrasing is where coverage breaks down.
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
    "Who is Mrs. Holt's son's wife?"
]


def main():
    corpus = load_corpus(DATA_DIR / "graphs" / "corpus.pkl")
    collection = get_collection(path=str(DATA_DIR / "chroma"))
    model = load_embedding_model()

    rows = []
    for q in TEST_QUESTIONS:
        hop_depth = estimate_hop_depth(q)
        hits = hybrid_search(collection, q, model, corpus,
                              n_results=5, book_id=BOOK_ID, hop_depth=hop_depth)

        for hit in hits:
            q_lower = q.lower()
            for r in hit.all_relationships:
                e1_in_query = r["entity1"].lower() in q_lower
                e2_in_query = r["entity2"].lower() in q_lower
                rows.append({
                    "question": q, "hop_depth": hop_depth, "type": "fact",
                    "entity1": r["entity1"], "entity2": r["entity2"],
                    "entity1_appears_in_question": e1_in_query,
                    "entity2_appears_in_question": e2_in_query,
                    "query_direction_match": r.get("query_direction_match"),
                })

            # Sample up to 5 chains per hit, not just the count - to
            # actually see whether they look relevant or like noise.
            for c in hit.chains[:5]:
                rows.append({
                    "question": q, "hop_depth": hop_depth, "type": "chain_sample",
                    "path": " -> ".join(c["path"]),
                    "relations": ",".join(c["relations"]),
                })

    # Print rather than just log - this needs eyeballing, not just counting.
    for r in rows:
        print(r)

    with open("entity_and_chain_inspection.csv", "w", newline="") as f:
        all_keys = sorted({k for r in rows for k in r.keys()})
        writer = csv.DictWriter(f, fieldnames=all_keys)
        writer.writeheader()
        writer.writerows(rows)
    print("\nWritten to entity_and_chain_inspection.csv")


if __name__ == "__main__":
    main()
