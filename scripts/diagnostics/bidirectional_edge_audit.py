# scripts/diagnostics/bidirectional_edge_audit.py
"""Corpus-wide check for the SAME (u, v, relation) pair stored as
edges in BOTH directions - u->v AND v->u, same relation. Different,
more concrete problem than general direction-inconsistency (used_by,
married_to): those are "entity1 sometimes plays the wrong role," this
is "both roles asserted simultaneously," a genuine logical
contradiction at the data level - no traversal/direction-detection
logic can resolve it (day 9/10 finding: this, not a code bug, was the
actual cause of the Mrs. Transome overshoot investigation).

Scoped to parent_father_of/parent_mother_of/child_of for the "strict"
count (parent and child cannot be each other - unambiguous).
spouse_of/sibling_of are checked separately and reported with a note,
since those ARE in SYMMETRIC_RELATIONS elsewhere - a bidirectional
pair there is expected, not a contradiction.
"""

from collections import defaultdict
from pathlib import Path

from graph.corpus import load_corpus
from scripts.diagnostics.common import output_path

DATA_DIR = Path("data")
STRICT_RELATIONS = {"parent_father_of", "parent_mother_of", "child_of"}
SYMMETRIC_CHECK_RELATIONS = {"spouse_of", "sibling_of"}


def find_bidirectional_pairs(graph, relations):
    edges_by_relation = defaultdict(set)
    for u, v, data in graph.edges(data=True):
        rel = data.get("relation")
        if rel in relations:
            edges_by_relation[rel].add((u, v))

    contradictions = {}
    for rel, edge_set in edges_by_relation.items():
        for (u, v) in edge_set:
            if u != v and (v, u) in edge_set:
                key = (rel, frozenset({u, v}))
                if key not in contradictions:
                    contradictions[key] = (u, v)
    return contradictions


def main():
    corpus = load_corpus(DATA_DIR / "graphs" / "corpus.pkl")
    all_relations = STRICT_RELATIONS | SYMMETRIC_CHECK_RELATIONS
    all_contradictions = []

    for book_id, graph in corpus.items():
        if graph is None or graph.number_of_nodes() == 0:
            continue
        found = find_bidirectional_pairs(graph, all_relations)
        for (rel, pair), example in found.items():
            all_contradictions.append({"book_id": book_id, "relation": rel,
                                        "pair": sorted(pair), "example": example})

    books_checked = sum(1 for g in corpus.values() if g and g.number_of_nodes() > 0)
    print(f"Books checked: {books_checked}")
    print(f"Total bidirectional pairs found: {len(all_contradictions)}\n")

    by_relation = defaultdict(int)
    for c in all_contradictions:
        by_relation[c["relation"]] += 1
    print("-- by relation --")
    for rel, n in sorted(by_relation.items(), key=lambda kv: -kv[1]):
        note = " (symmetric - expected, not necessarily a contradiction)" \
            if rel in SYMMETRIC_CHECK_RELATIONS else ""
        print(f"  {rel:<20} {n}{note}")

    strict = [c for c in all_contradictions if c["relation"] in STRICT_RELATIONS]
    print(f"\n-- strict contradictions (parent_father_of/parent_mother_of/child_of) --")
    for c in strict[:20]:
        u, v = c["example"]
        print(f"  [{c['book_id']}] {u} <-> {v}  ({c['relation']}, both directions stored)")
    if len(strict) > 20:
        print(f"  ... and {len(strict) - 20} more")
    print(f"\nTotal strict contradictions: {len(strict)}")

    import pandas as pd
    pd.DataFrame(all_contradictions).to_csv(output_path("bidirectional_contradictions.csv"), index=False)
    print(f"\nWritten to {output_path('bidirectional_contradictions.csv')}")


if __name__ == "__main__":
    main()