# scripts/diagnostics/verify_pronoun_filter_against_audit.py
"""Real-usage check for resolution/pronoun_filter.py - per the
standing rule, unit tests passing isn't sufficient. This reruns the
day-4 functional-step audit WITH the filter applied, to confirm the
predicted drop (58% of 19.4% fragmentation should become excluded,
not silently unify with real answers) actually happens on real data,
not just the hand-picked Harold cluster the unit tests checked.
"""

from pathlib import Path

from graph.corpus import load_corpus
from resolution.pronoun_filter import build_resolution_map
from scripts.diagnostics.generate_positive_controls import (
    build_index, STEP_KEYS, step, is_nameable
)
from scripts.diagnostics.diagnose_hops import FUNCTIONAL_STEPS, token_overlap

DATA_DIR = Path("data")
BOOKS = {"40882": "Felix Holt", "106": "Tarzan", "12753": "King Arthur",
         "47634": "Sons and Lovers", "52617": "Decameron", "73548": "Rhinegold"}


def audit_with_filter(graph, label):
    index = build_index(graph)
    resolution_map = build_resolution_map(graph)
    rows = []
    for anchor in graph.nodes:
        if not is_nameable(anchor):
            continue
        for relation, role in FUNCTIONAL_STEPS:
            frontier = step(index, anchor, relation, role)
            if len(frontier) <= 1:
                continue
            clean_frontier = frontier - set(resolution_map)
            if len(clean_frontier) <= 1:
                continue  # already resolved or emptied, not "still contaminated"
            rows.append({
                "book": label, "anchor": anchor, "relation": relation,
                "clean_frontier": clean_frontier,
                "clean_size": len(clean_frontier),
                "looks_like_surface_variant": token_overlap(clean_frontier),  # reuse from Module A
            })
    return rows


def main():
    corpus = load_corpus(DATA_DIR / "graphs" / "corpus.pkl")
    all_rows = []
    for book_id, label in BOOKS.items():
        graph = corpus.get(book_id)
        if graph is not None:
            all_rows.extend(audit_with_filter(graph, label))

    print(f"Still-contaminated functional-step frontiers: {len(all_rows)}\n")
    surface_like = [r for r in all_rows if r["looks_like_surface_variant"]]
    other = [r for r in all_rows if not r["looks_like_surface_variant"]]

    print(f"Look like surface-variant residue (Stage A territory): {len(surface_like)}")
    for r in surface_like:
        print(f"  {r['book']}: {r['anchor']} -{r['relation']}-> {r['clean_frontier']}")

    print(f"\nDo NOT look like surface variants (Stage B/C territory, or unexplained): {len(other)}")
    for r in other:
        print(f"  {r['book']}: {r['anchor']} -{r['relation']}-> {r['clean_frontier']}")


if __name__ == "__main__":
    main()