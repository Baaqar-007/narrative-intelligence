
"""Paired comparison for the is_nameable() delegation change (day 5) -
without reverting the live file. Reconstructs what generate() would
have produced under the OLD is_nameable (pre-delegation, pre-plural/
archaic-form fixes) by re-implementing that old logic here as a
standalone function, and diffs against what the CURRENT generate()
actually produces - both scored through the real hybrid_search
adapter, compared only on the question-ID intersection (same
paired-by-question-ID discipline as day 4's run_paired_comparison.py,
which caught a false-alarm regression that an unpaired comparison
would have missed).

Requires: build_index, STEPS, STEP_KEYS, walk, generate, GENDERED,
make_hybrid_adapter, score, BOOKS, SEED, HOPS, CAP_PER_COMBO, step,
is_nameable all importable from the live yardstick script - adjust
the import path below to wherever that file actually lives on disk.
"""

import random
import string
from collections import Counter
from pathlib import Path

import pandas as pd

from embedding.embed_relations import load_embedding_model
from graph.corpus import load_corpus
from embedding.vector_store import get_collection
from scripts.diagnostics.generate_positive_controls import (
    generate, make_hybrid_adapter, score, build_index, STEPS, STEP_KEYS,
     walk, GENDERED, is_nameable, step, BOOKS, SEED, HOPS, CAP_PER_COMBO,
)

DATA_DIR = Path("data")

# Exact pre-day-5 is_nameable logic, frozen here for comparison only -
# NOT the live version, NOT imported from resolution/pronoun_filter.
# This is what anchors looked like before: (a) the delegation to
# is_pronoun_generic, (b) the plural/archaic-form additions, and
# (c) the _SOCIAL_ROLE_GENERIC additions ("gentlewoman", etc.).
_OLD_FUNCTION_WORDS = {"he", "she", "her", "his", "him", "you", "your", "my", "me", "i", "we",
                       "our", "us", "they", "them", "their", "it", "its", "the", "a", "an",
                       "this", "that", "these", "those", "some", "little", "young", "old"}
_OLD_GENERIC = {"husband", "wife", "son", "daughter", "brother", "sister"} | \
               {"party", "people", "man", "woman", "boy", "girl", "baby", "lady"}


def is_nameable_old(entity: str) -> bool:
    tokens = entity.split()
    return (1 <= len(tokens) <= 4 and tokens[0] not in _OLD_FUNCTION_WORDS
            and entity not in _OLD_GENERIC)


def generate_with_nameable(graph, book_id, hops, cap, nameable_fn, enforce_purity=True):
    """... same as before, but for A/B comparison purposes cap should
    be passed as None/unbounded - see run_comparison() below. A
    per-sequence-label cap is order-dependent (which anchors "use up"
    a combo slot first depends on where they sit in iteration order),
    so even deterministic sorted order doesn't make the tighter-
    filtered population a true subset when capping is active. Capping
    is correct for the main yardstick's diversity sampling; it's
    wrong for an A/B test whose entire point is "does this exact set
    of questions change.\""""
    index, degree = build_index(graph), dict(graph.degree())
    anchors = sorted(n for n in graph.nodes if nameable_fn(n))
    combo_counts, out, excluded = Counter(), [], [0]
    for anchor in anchors:
        for seq, gold in walk(index, anchor, [], {anchor}, hops, enforce_purity, excluded):
            label = " > ".join(f"{r}:{w}" for r, w in seq)
            if cap is not None and combo_counts[label] >= cap:
                continue
            combo_counts[label] += 1
            phrase = string.capwords(anchor)
            for key in seq:
                phrase = f"the {STEPS[key]} of {phrase}"
            out.append({
                "book_id": book_id, "question": f"Who is {phrase}?", "anchor": anchor,
                "sequence": label, "hops": hops, "gold_set": gold,
                "gold": ";".join(sorted(gold)), "gold_size": len(gold),
                "unique": len(gold) == 1,
                "gold_nameable_frac": round(sum(map(is_nameable, gold)) / len(gold), 2),
                "gold_max_degree": max(degree.get(g, 0) for g in gold),
                "anchor_degree": degree.get(anchor, 0),
                "first_step_symmetric": seq[0][1] == "sym",
                "first_rel": seq[0][0],
                "first_nodes": step(index, anchor, *seq[0]),
                "gendered": any(STEPS[k] in GENDERED for k in seq),
            })
    print(f"  [{book_id}] excluded by purity filter: {excluded[0]}")
    return out


def run_population(books, corpus, adapter, hops, cap, generate_fn, **generate_kwargs):
    rows = []
    for book_id, label in books.items():
        graph = corpus.get(book_id)
        if graph is None:
            continue
        for q in generate_fn(graph, book_id, hops=hops, cap=cap, **generate_kwargs):
            result = adapter(q["question"], book_id, q["anchor"], q["first_rel"], q["first_nodes"])
            rows.append({**q, "book": label, **score(q["gold_set"], result)})
    return pd.DataFrame(rows)


def main():
    corpus = load_corpus(DATA_DIR / "graphs" / "corpus.pkl")
    adapter = make_hybrid_adapter(get_collection(path=str(DATA_DIR / "chroma")),
                                  load_embedding_model(), corpus)

    print("Generating OLD-is_nameable population (deterministic order, uncapped)...")
    before = run_population(BOOKS, corpus, adapter, HOPS, None,
                             generate_with_nameable, nameable_fn=is_nameable_old)
    before.to_csv("yardstick_old_is_nameable.csv", index=False)

    print("Generating CURRENT-is_nameable population (deterministic order, uncapped)...")
    after = run_population(BOOKS, corpus, adapter, HOPS, None,
                            generate_with_nameable, nameable_fn=is_nameable)
    after.to_csv("yardstick_current_is_nameable.csv", index=False)

    b = before.set_index(["book_id", "question"])
    a = after.set_index(["book_id", "question"])
    common = b.index.intersection(a.index)
    only_old = b.index.difference(a.index)
    only_new = a.index.difference(b.index)

    print(f"\nOld population: {len(b)}, current population: {len(a)}, common: {len(common)}")
    print(f"Questions only in OLD (now excluded by tighter filter): {len(only_old)}")
    print(f"Questions only in NEW (should be exactly 0 now): {len(only_new)}")
    assert len(only_new) == 0, "only_new is non-empty - the comparison is STILL invalid, stop and investigate before reading further output"

    print(f"\n-- common questions, paired --")
    print(f"  old HIT: {b.loc[common].outcome.eq('HIT').mean():.1%}"
          f"   new HIT: {a.loc[common].outcome.eq('HIT').mean():.1%}")
    print(f"  old WRONG: {b.loc[common].outcome.eq('WRONG').mean():.1%}"
          f"   new WRONG: {a.loc[common].outcome.eq('WRONG').mean():.1%}")

    print(f"\n-- the actual question: were excluded-anchor questions correct before? --")
    excluded = b.loc[only_old]
    print(f"  {len(excluded)} questions lost. Outcome breakdown when they still existed:")
    print(excluded.outcome.value_counts(normalize=True).mul(100).round(1))
    print(f"  Of those, HIT count lost: {(excluded.outcome == 'HIT').sum()}")


if __name__ == "__main__":
    main()