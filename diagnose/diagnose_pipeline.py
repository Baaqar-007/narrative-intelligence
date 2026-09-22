"""Diagnostic: chains and reproducibility, against the REAL pipeline.

Run this in your actual environment (needs corpus.pkl, ChromaDB,
embedding model - same loading as api/main.py). Adjust DATA_DIR/book_id
and TEST_QUESTIONS below to match a book and characters you know well,
so you can sanity-check the output yourself.

Logs, per question:
- estimated hop_depth
- matched entity1/entity2, and whether that matched pair is STABLE
  across two separate retrieval calls (isolates retrieval-layer
  reproducibility from the LLM layer)
- number of chains found, and their content
- direction_match values for each returned fact

Also runs generate_answer() twice on the SAME retrieved hits, to check
whether non-reproducibility is coming from the LLM's phrasing/judgment
(temperature=0.2) rather than from retrieval itself - if the SAME
facts sometimes produce "cannot be determined" and sometimes produce
an answer, that isolates the LLM as the cause, not retrieval.
"""

import csv
from pathlib import Path

from embedding.embed_relations import load_embedding_model
from embedding.vector_store import get_collection
from graph.corpus import load_corpus
from retrieval.answer_generation import generate_answer
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

def diagnose_question(question, collection, model, corpus):
    hop_depth = estimate_hop_depth(question)

    # Two independent retrieval calls - checks retrieval-layer
    # reproducibility specifically, separate from the LLM.
    hits_1 = hybrid_search(collection, question, model, corpus,
                            n_results=5, book_id=BOOK_ID, hop_depth=hop_depth)
    hits_2 = hybrid_search(collection, question, model, corpus,
                            n_results=5, book_id=BOOK_ID, hop_depth=hop_depth)

    pair_1 = [(h.entity1, h.entity2) for h in hits_1]
    pair_2 = [(h.entity1, h.entity2) for h in hits_2]
    retrieval_stable = pair_1 == pair_2

    total_chains = sum(len(h.chains) for h in hits_1)
    total_facts = sum(len(h.all_relationships) for h in hits_1)
    direction_matches = [
        r.get("query_direction_match") for h in hits_1 for r in h.all_relationships
    ]

    # Same hits, LLM called twice - isolates LLM-layer non-determinism.
    answer_1 = generate_answer(question, hits_1)
    answer_2 = generate_answer(question, hits_1)
    llm_stable = answer_1.strip() == answer_2.strip()

    return {
        "question": question,
        "hop_depth": hop_depth,
        "retrieval_stable_across_calls": retrieval_stable,
        "matched_pairs_run1": pair_1,
        "matched_pairs_run2": pair_2,
        "total_facts": total_facts,
        "total_chains": total_chains,
        "direction_matches": direction_matches,
        "llm_stable_on_same_facts": llm_stable,
        "answer_1": answer_1,
        "answer_2": answer_2,
    }


def main():
    print("Loading pipeline...")
    corpus = load_corpus(DATA_DIR / "graphs" / "corpus.pkl")
    collection = get_collection(path=str(DATA_DIR / "chroma"))
    model = load_embedding_model()
    print(f"Ready: {len(corpus)} books, {collection.count():,} vectors.\n")

    results = []
    for q in TEST_QUESTIONS:
        print(f"=== {q!r} ===")
        r = diagnose_question(q, collection, model, corpus)
        results.append(r)
        print(f"  hop_depth={r['hop_depth']}  facts={r['total_facts']}  chains={r['total_chains']}")
        print(f"  retrieval stable across 2 calls: {r['retrieval_stable_across_calls']}")
        if not r["retrieval_stable_across_calls"]:
            print(f"    run1 pairs: {r['matched_pairs_run1']}")
            print(f"    run2 pairs: {r['matched_pairs_run2']}")
        print(f"  direction_match values: {r['direction_matches']}")
        print(f"  LLM stable on identical facts: {r['llm_stable_on_same_facts']}")
        if not r["llm_stable_on_same_facts"]:
            print(f"    answer1: {r['answer_1'][:150]}")
            print(f"    answer2: {r['answer_2'][:150]}")
        print()

    with open("pipeline_diagnostic_log.csv", "w", newline="", encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=list(results[0].keys()))
        writer.writeheader()
        writer.writerows(results)
    print("Full results written to pipeline_diagnostic_log.csv")


if __name__ == "__main__":
    main()
