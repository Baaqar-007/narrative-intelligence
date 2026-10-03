# scripts/diagnostics/full_corpus_resolution_followup.py
"""Two follow-ups to the full-corpus Module A baseline:
1. Manual spot-check dump for book 3322 (the one high-contamination
   book with a large enough sample - n=58 - to trust the rate itself,
   per the baseline run's own flag).
2. Full-corpus before/after: how much of the 291 contaminated
   functional-step frontiers actually clear once the CONSOLIDATED
   resolution.resolve.build_full_resolution_map() is applied - the
   natural next check once a baseline exists, per day-5's pattern
   (predict a resolution rate, then verify against real data, don't
   assume the module's effect without checking).
"""

from collections import defaultdict
from pathlib import Path

from graph.corpus import load_corpus
from resolution.resolve import build_full_resolution_map, is_nameable

DATA_DIR = Path("data")
FUNCTIONAL_STEPS = {("parent_father_of", "e1"), ("parent_mother_of", "e1")}
SPOT_CHECK_BOOK = "3322"


def build_index(graph):
    out_, in_ = defaultdict(lambda: defaultdict(set)), defaultdict(lambda: defaultdict(set))
    for u, v, d in graph.edges(data=True):
        rel = d.get("relation")
        if rel:
            out_[rel][u].add(v)
            in_[rel][v].add(u)
    return out_, in_


def step(index_out, index_in, node, relation, want):
    e1s = index_in[relation].get(node, set())
    e2s = index_out[relation].get(node, set())
    return set(e1s) if want == "e1" else set(e2s) if want == "e2" else e1s | e2s


def token_overlap(frontier):
    if len(frontier) <= 1:
        return True
    longest = max(frontier, key=len)
    long_tokens = set(longest.split())
    return all(set(s.split()) & long_tokens for s in frontier if s != longest)


def main():
    corpus = load_corpus(DATA_DIR / "graphs" / "corpus.pkl")

    # --- Part 1: spot-check book 3322 ---
    graph = corpus.get(SPOT_CHECK_BOOK)
    if graph is None:
        print(f"Book {SPOT_CHECK_BOOK} not found in corpus.")
    else:
        index_out, index_in = build_index(graph)
        print(f"-- Book {SPOT_CHECK_BOOK}: contaminated functional-step frontiers --")
        for anchor in graph.nodes:
            if not is_nameable(anchor):
                continue
            for relation, role in FUNCTIONAL_STEPS:
                frontier = step(index_out, index_in, anchor, relation, role)
                if len(frontier) > 1:
                    print(f"  {anchor} -{relation}:{role}-> {frontier}")

    # --- Part 2: full-corpus before/after resolution ---
    print("\n-- Full-corpus before/after resolution --")
    total_contaminated = resolved_to_single = still_multi = unchanged_or_worse = 0

    for book_id, g in corpus.items():
        if g is None or g.number_of_nodes() == 0:
            continue
        resolution_map = build_full_resolution_map(g)
        index_out, index_in = build_index(g)

        for anchor in g.nodes:
            if not is_nameable(anchor):
                continue
            for relation, role in FUNCTIONAL_STEPS:
                frontier = step(index_out, index_in, anchor, relation, role)
                if len(frontier) <= 1:
                    continue
                total_contaminated += 1

                resolved_frontier = set()
                for member in frontier:
                    entry = resolution_map.get(member)
                    if entry is None:
                        resolved_frontier.add(member)  # unresolved, kept as-is
                    elif entry.tier.value == "surface_variant":
                        resolved_frontier.add(entry.canonical_form)  # redirected
                    # pronoun_generic / ambiguous_variant_candidate: dropped entirely
                    # (excluded from composition, per is_excluded_from_composition's logic)

                if len(resolved_frontier) <= 1:
                    resolved_to_single += 1
                elif len(resolved_frontier) < len(frontier):
                    still_multi += 1  # improved, but not fully resolved
                else:
                    unchanged_or_worse += 1

    print(f"Total contaminated functional-step frontiers: {total_contaminated}")
    print(f"  fully resolved to <=1 answer:  {resolved_to_single} "
          f"({resolved_to_single/total_contaminated:.1%})")
    print(f"  improved but still >1 answer:  {still_multi} "
          f"({still_multi/total_contaminated:.1%})")
    print(f"  unchanged (no improvement):    {unchanged_or_worse} "
          f"({unchanged_or_worse/total_contaminated:.1%})")


if __name__ == "__main__":
    main()