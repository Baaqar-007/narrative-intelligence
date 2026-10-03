# scripts/diagnostics/full_corpus_resolution_audit.py
"""Full 96-book run of Module A's functional-step contamination
measurement, through the CONSOLIDATED resolution package (not
hand-reconstructed per-script - the day-5/6/7 lesson). Reuses the
exact FUNCTIONAL_STEPS definition and category split (pronoun_generic
vs surface_variant vs unrelated) from the 6-book version, so results
are directly comparable to the day-4/7 numbers, not a new metric.

Answers the day-6 ponder directly: does the hand-seeded pronoun list
and the honorific-stripping logic, validated against 6 books, hold up
across the other 90 - or does contamination/category-mix look
meaningfully different at scale, signaling the hand list needs
another real-data-driven extension round (same spirit as the
plural/archaic-form fixes already made).
"""

from collections import defaultdict
from pathlib import Path

from graph.corpus import load_corpus
from resolution.resolve import build_full_resolution_map, is_nameable
from resolution.surface_variant_merge import core_tokens

DATA_DIR = Path("data")
FUNCTIONAL_STEPS = {("parent_father_of", "e1"), ("parent_mother_of", "e1")}


def token_overlap(frontier: set[str]) -> bool:
    if len(frontier) <= 1:
        return True
    longest = max(frontier, key=len)
    long_tokens = set(longest.split())
    return all(set(s.split()) & long_tokens for s in frontier if s != longest)


def is_pronoun_generic_frontier(frontier: set[str]) -> bool:
    from resolution.pronoun_filter import is_pronoun_generic
    return any(is_pronoun_generic(f) for f in frontier)


def classify_frontier(frontier: set[str]) -> str:
    if len(frontier) <= 1:
        return "pure"
    if is_pronoun_generic_frontier(frontier):
        return "pronoun_generic"
    if token_overlap(frontier):
        return "surface_variant"
    return "unrelated"


def step(index_out, index_in, node, relation, want):
    e1s = index_in[relation].get(node, set())
    e2s = index_out[relation].get(node, set())
    return set(e1s) if want == "e1" else set(e2s) if want == "e2" else e1s | e2s


def build_index(graph):
    out_, in_ = defaultdict(lambda: defaultdict(set)), defaultdict(lambda: defaultdict(set))
    for u, v, d in graph.edges(data=True):
        rel = d.get("relation")
        if rel:
            out_[rel][u].add(v)
            in_[rel][v].add(u)
    return out_, in_


def audit_book(graph, book_id):
    index_out, index_in = build_index(graph)
    rows = []
    for anchor in graph.nodes:
        if not is_nameable(anchor):
            continue
        for relation, role in FUNCTIONAL_STEPS:
            frontier = step(index_out, index_in, anchor, relation, role)
            if not frontier:
                continue
            rows.append({
                "book_id": book_id, "anchor": anchor, "relation": relation,
                "frontier_size": len(frontier), "category": classify_frontier(frontier),
            })
    return rows


def main():
    corpus = load_corpus(DATA_DIR / "graphs" / "corpus.pkl")
    all_rows = []
    skipped = []
    for book_id, graph in corpus.items():
        if graph is None or graph.number_of_nodes() == 0:
            skipped.append(book_id)
            continue
        all_rows.extend(audit_book(graph, book_id))

    print(f"Books processed: {len(corpus) - len(skipped)}, skipped (empty/None): {len(skipped)}")
    if skipped:
        print(f"  skipped book_ids: {skipped}")

    total = len(all_rows)
    contaminated = [r for r in all_rows if r["category"] != "pure"]
    print(f"\nTotal functional-step frontiers checked: {total}")
    print(f"Contaminated: {len(contaminated)} ({len(contaminated)/total:.1%})")

    cat_counts = defaultdict(int)
    for r in contaminated:
        cat_counts[r["category"]] += 1
    for cat in ("pronoun_generic", "surface_variant", "unrelated"):
        n = cat_counts.get(cat, 0)
        pct_of_contaminated = n / len(contaminated) if contaminated else 0
        print(f"  {cat:<18} {n:>5}  ({pct_of_contaminated:.1%} of contaminated)")

    print("\n-- per-book contamination rate (top 10 highest, for spot-check candidates) --")
    by_book = defaultdict(list)
    for r in all_rows:
        by_book[r["book_id"]].append(r)
    rates = []
    for book_id, rows in by_book.items():
        bad = sum(1 for r in rows if r["category"] != "pure")
        if len(rows) >= 5:  # skip tiny-sample books, not meaningful
            rates.append((book_id, bad, len(rows), bad / len(rows)))
    for book_id, bad, n, rate in sorted(rates, key=lambda x: -x[3])[:10]:
        print(f"  {book_id:<10} {bad}/{n} = {rate:.1%}")

    print(f"\nBooks with 0 functional-step frontiers at all (too sparse to measure): "
          f"{sum(1 for b, rows in by_book.items() if len(rows) == 0)}")


if __name__ == "__main__":
    main()