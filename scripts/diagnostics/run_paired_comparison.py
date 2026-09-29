"""Regenerates the impure-frontier ('before') and pure-frontier
('after') yardstick runs from the same seed, scores both through the
live hybrid_search adapter, and compares ONLY the question set common
to both - so any rate difference reflects system behavior, not a
different population of questions. Answers the open day-4 question:
were the gendered-HIT drop and RECALL-miss jump from the last
same-seed diff real regressions, or artifacts of the purity filter
changing which questions got generated.
"""

import random
from pathlib import Path

import pandas as pd

from embedding.embed_relations import load_embedding_model
from graph.corpus import load_corpus
from embedding.vector_store import get_collection
from scripts.diagnostics.generate_positive_controls import SEED, HOPS, CAP_PER_COMBO, generate, make_hybrid_adapter, score, BOOKS

DATA_DIR = Path("data")


def run(enforce_purity, corpus, adapter):
    rng, rows = random.Random(SEED), []
    for book_id, label in BOOKS.items():
        graph = corpus.get(book_id)
        if graph is None:
            continue
        for q in generate(graph, book_id, rng, HOPS, CAP_PER_COMBO, enforce_purity):
            result = adapter(q["question"], book_id, q["anchor"],q["first_rel"], q["first_nodes"])
            rows.append({**q, "book": label, **score(q["gold_set"], result)})
    return pd.DataFrame(rows)


def main():
    corpus = load_corpus(DATA_DIR / "graphs" / "corpus.pkl")
    adapter = make_hybrid_adapter(get_collection(path=str(DATA_DIR / "chroma")),
                                  load_embedding_model(), corpus)

    print("Running WITHOUT purity filter (reconstructs the original day-3 run)...")
    before = run(enforce_purity=False, corpus=corpus, adapter=adapter)
    before.to_csv("yardstick_before_purity_fix.csv", index=False)

    print("Running WITH purity filter (day-4 corrected run)...")
    after = run(enforce_purity=True, corpus=corpus, adapter=adapter)
    after.to_csv("yardstick_after_purity_fix.csv", index=False)

    b = before.set_index(["book_id", "question"])
    a = after.set_index(["book_id", "question"])
    common = b.index.intersection(a.index)
    print(f"\nQuestions in 'before': {len(b)}, 'after': {len(a)}, common: {len(common)}")

    for label, mask_fn in [
        ("gendered", lambda df: df.gendered),
        ("all", lambda df: pd.Series(True, index=df.index)),
    ]:
        bm, am = mask_fn(b.loc[common]), mask_fn(a.loc[common])
        print(f"\n-- {label}, paired (n={bm.sum()}) --")
        print(f"  before HIT: {b.loc[common][bm].outcome.eq('HIT').mean():.1%}"
              f"   after HIT: {a.loc[common][am].outcome.eq('HIT').mean():.1%}")
        print(f"  before RECALL: {b.loc[common][bm].attribution.eq('RECALL').mean():.1%}"
              f"   after RECALL: {a.loc[common][am].attribution.eq('RECALL').mean():.1%}")


if __name__ == "__main__":
    main()