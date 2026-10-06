# scripts/diagnostics/full_corpus_resolution.py
"""Full 96-book functional-step contamination audit, through the
consolidated resolution package - plus the non-functional
classification, Stage C evidence dump, and worst-example report from
the earlier 6-book diagnose_hops.py (archived day 11; these three
pieces were NOT superseded by this script's original functional-only
scope, so merged in here rather than lost).

Uses resolution.resolve.is_nameable / resolution.pronoun_filter.
is_pronoun_generic directly - NOT a local re-derivation. This is the
exact fix for the bug class that made diagnose_hops.py stale in the
first place (its own local PRONOUN_GENERIC_LAST_TOKEN list never
received the day-5/8 mamma/papa/judicial-title extensions that the
live resolution module did).
"""

from collections import defaultdict
from pathlib import Path

import pandas as pd

from graph.corpus import load_corpus
from resolution.resolve import is_nameable
from resolution.pronoun_filter import is_pronoun_generic
from scripts.diagnostics.common import build_index, step, token_overlap, output_path
from scripts.diagnostics.yardstick import STEP_KEYS

DATA_DIR = Path("data")
FUNCTIONAL_STEPS = {("parent_father_of", "e1"), ("parent_mother_of", "e1")}


def classify_frontier(frontier: set[str]) -> str:
    if len(frontier) <= 1:
        return "pure"
    if any(is_pronoun_generic(f) for f in frontier):
        return "pronoun_generic"
    if token_overlap(frontier):
        return "surface_variant"
    return "unrelated"


def audit_book(graph, book_id):
    index = build_index(graph)
    rows = []
    for anchor in graph.nodes:
        if not is_nameable(anchor):
            continue
        for relation, role in STEP_KEYS:
            frontier = step(index, anchor, relation, role)
            if not frontier:
                continue
            rows.append({
                "book_id": book_id, "anchor": anchor, "relation": relation, "role": role,
                "functional": (relation, role) in FUNCTIONAL_STEPS,
                "frontier_size": len(frontier),
                "category": classify_frontier(frontier),
                "frontier": frontier,
            })
    return rows


def report(rows, title):
    total = len(rows)
    if total == 0:
        print(f"\n({title}: no rows)")
        return
    cats = defaultdict(int)
    for r in rows:
        cats[r["category"]] += 1
    print(f"\n-- {title} (n={total}) --")
    for cat in ("pure", "pronoun_generic", "surface_variant", "unrelated"):
        n = cats.get(cat, 0)
        print(f"  {cat:<18} {n:>5}  ({n/total:.1%})")


def main():
    corpus = load_corpus(DATA_DIR / "graphs" / "corpus.pkl")
    all_rows = []
    skipped = []
    for book_id, graph in corpus.items():
        if graph is None or graph.number_of_nodes() == 0:
            skipped.append(book_id)
            continue
        all_rows.extend(audit_book(graph, book_id))

    books_checked = len(corpus) - len(skipped)
    print(f"Books processed: {books_checked}, skipped (empty/None): {len(skipped)}")
    if skipped:
        print(f"  skipped book_ids: {skipped}")

    functional_rows = [r for r in all_rows if r["functional"]]
    nonfunctional_rows = [r for r in all_rows if not r["functional"]]

    report(functional_rows, "FUNCTIONAL steps (e1 of parent_father_of/parent_mother_of) - "
                              "frontier_size>1 is unambiguously a problem - full 96-book scale")
    report(nonfunctional_rows, "NON-FUNCTIONAL steps - multi-valued frontiers may be legitimate")

    print("\n-- functional-step contamination by book (top 10 highest, n>=5) --")
    by_book = defaultdict(list)
    for r in functional_rows:
        by_book[r["book_id"]].append(r)
    rates = []
    for book_id, rows in by_book.items():
        bad = sum(1 for r in rows if r["category"] != "pure")
        if len(rows) >= 5:
            rates.append((book_id, bad, len(rows), bad / len(rows)))
    for book_id, bad, n, rate in sorted(rates, key=lambda x: -x[3])[:10]:
        print(f"  {book_id:<10} {bad}/{n} = {rate:.1%}")

    print("\n-- worst functional-step examples by frontier size (manual spot-check) --")
    worst = sorted((r for r in functional_rows if r["category"] != "pure"),
                   key=lambda r: -r["frontier_size"])
    for r in worst[:10]:
        print(f"  [{r['book_id']}] {r['anchor']} -{r['relation']}:{r['role']}-> "
              f"[{r['category']}] {r['frontier']}")

    print("\n-- pronoun_generic examples, non-functional steps (Stage C / Week 8 evidence) --")
    pg = [r for r in nonfunctional_rows if r["category"] == "pronoun_generic"][:8]
    for r in pg:
        print(f"  [{r['book_id']}] {r['anchor']} -{r['relation']}:{r['role']}-> {r['frontier']}")

    pd.DataFrame(all_rows).to_csv(output_path("full_corpus_resolution_audit.csv"), index=False)
    print(f"\nWritten to {output_path('full_corpus_resolution_audit.csv')}")


if __name__ == "__main__":
    main()