"""H2 diagnostic, corrected: full chain logging (no truncation) and a
quantified hub-degree measurement instead of eyeballing entity names,
plus a positive-control question with a known-answerable chain.

Prerequisite fix from the first pass: the earlier script capped chain
sampling at [:5] per hit, which could hide exactly the pattern being
investigated. This logs every chain.
"""

import csv
import statistics
from pathlib import Path

from embedding.embed_relations import load_embedding_model
from embedding.vector_store import get_collection
from graph.corpus import load_corpus
from retrieval.direction_detection import estimate_hop_depth
from retrieval.hybrid_search import hybrid_search

DATA_DIR = Path("data")
BOOK_ID_MAIN = "40882"  # adjust to a book you know well

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

# Positive control: book 106, real names already confirmed to exist
# this session (direction_coverage_log.csv). A genuine forward chain
# is expected to exist here - if THIS also drowns in noise, the
# problem is the traversal itself, not something specific to
# high-degree Felix Holt characters.
POSITIVE_CONTROL = ("Who is a companion of Taug?", "106")


def inspect_question(question, book_id, corpus, collection, model):
    hop_depth = estimate_hop_depth(question)
    hits = hybrid_search(collection, question, model, corpus,
                          n_results=5, book_id=book_id, hop_depth=hop_depth)

    graph = corpus.get(book_id)
    degrees = dict(graph.degree()) if graph is not None else {}
    corpus_median_degree = statistics.median(degrees.values()) if degrees else None

    rows = []
    for hit in hits:
        for c in hit.chains:  # ALL chains, not chains[:5]
            path_degrees = [degrees.get(node, None) for node in c["path"]]
            rows.append({
                "question": question, "hop_depth": hop_depth,
                "path": " -> ".join(c["path"]),
                "relations": ",".join(c["relations"]),
                "path_degrees": path_degrees,
                "max_degree_in_path": max((d for d in path_degrees if d is not None), default=None),
                "corpus_median_degree_for_reference": corpus_median_degree,
            })
    return rows


def main():
    corpus = load_corpus(DATA_DIR / "graphs" / "corpus.pkl")
    collection = get_collection(path=str(DATA_DIR / "chroma"))
    model = load_embedding_model()

    all_rows = []
    for q in TEST_QUESTIONS:
        rows = inspect_question(q, BOOK_ID_MAIN, corpus, collection, model)
        all_rows.extend(rows)
        print(f"\n=== {q!r}: {len(rows)} chains ===")
        for r in rows:
            ref = r["corpus_median_degree_for_reference"] or 1
            flag = " <- HIGH DEGREE" if (r["max_degree_in_path"] or 0) > 3 * ref else ""
            print(f"  {r['path']}  [{r['relations']}]  max_degree={r['max_degree_in_path']}{flag}")

    pc_question, pc_book = POSITIVE_CONTROL
    pc_rows = inspect_question(pc_question, pc_book, corpus, collection, model)
    all_rows.extend([{**r, "question": f"[POSITIVE CONTROL] {r['question']}"} for r in pc_rows])
    print(f"\n=== POSITIVE CONTROL {pc_question!r}: {len(pc_rows)} chains ===")
    for r in pc_rows:
        print(f"  {r['path']}  [{r['relations']}]  max_degree={r['max_degree_in_path']}")
    if not pc_rows:
        print("  ** No chains found even for the positive control - traversal "
              "itself may be the issue, not just hub-degree **")

    with open("chain_hub_inspection.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(all_rows[0].keys()))
        writer.writeheader()
        writer.writerows(all_rows)
    print("\nWritten to chain_hub_inspection.csv")


if __name__ == "__main__":
    main()
