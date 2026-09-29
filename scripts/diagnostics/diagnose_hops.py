"""Corpus-wide frontier-purity audit, v2 - corrects two flaws in the
v1 run:

1. v1 treated every multi-valued frontier as "contaminated," but most
   of STEP_KEYS covers non-functional relations (companion_of,
   enemy_of, siblings, a parent's own multiple children via the e2
   role, etc.) where a real character legitimately has many true
   relationships. Only the e1 role of parent_father_of/
   parent_mother_of is functional (one biological father, one
   biological mother) - that's the only case where frontier_size > 1
   is unambiguously wrong. Everything else needs to be read
   separately, not folded into one contamination rate.

2. v1's "unrelated" bucket (no shared token) silently absorbed the
   pronoun/generic-descriptor case documented since the Week 7 audit
   ("her son", "my son", "mother" as apparent entity strings) - which
   is a real, distinct, already-named problem (Week 8 Stage C), not
   generic ambiguity. Split out explicitly so it doesn't get
   miscounted as either "surface variant" (Stage A) or true noise.

Three-way category, checked in this order: pronoun_generic (Stage C) >
surface_variant (Stage A, token overlap) > unrelated (genuine ARF
noise, hard coreference, or real narrative multiplicity - this script
cannot tell those apart; flagged, not resolved).
"""

from collections import defaultdict
from pathlib import Path

from graph.corpus import load_corpus
from ..diagnostics.generate_positive_controls import (
    build_index, STEP_KEYS, step, is_nameable,
)

DATA_DIR = Path("data")
BOOKS = {"40882": "Felix Holt", "106": "Tarzan", "12753": "King Arthur",
         "47634": "Sons and Lovers", "52617": "Decameron", "73548": "Rhinegold"}

FUNCTIONAL_STEPS = {("parent_father_of", "e1"), ("parent_mother_of", "e1")}

# Seed list from findings so far (Harold's variants, Week 7 audit's
# bare-pronoun/generic examples) - not exhaustive. Matches on the
# LAST token so "her son"/"my son"/"his son" all hit "son", and on
# the full string for single-word generics.
PRONOUN_GENERIC_LAST_TOKEN = {
    "he", "she", "her", "his", "him", "you", "your", "my", "me",
    "mother", "father", "son", "daughter", "husband", "wife",
    "brother", "sister", "child",
}


def token_overlap(frontier: set[str]) -> bool:
    if len(frontier) <= 1:
        return True
    longest = max(frontier, key=len)
    long_tokens = set(longest.split())
    return all(set(s.split()) & long_tokens for s in frontier if s != longest)


def is_pronoun_generic(entity: str) -> bool:
    tokens = entity.split()
    return tokens[-1] in PRONOUN_GENERIC_LAST_TOKEN


def classify_frontier(frontier: set[str]) -> str:
    if len(frontier) <= 1:
        return "pure"
    if any(is_pronoun_generic(f) for f in frontier):
        return "pronoun_generic"
    if token_overlap(frontier):
        return "surface_variant"
    return "unrelated"


def audit_book(graph, label):
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
                "book": label, "anchor": anchor, "relation": relation, "role": role,
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
    for book_id, label in BOOKS.items():
        graph = corpus.get(book_id)
        if graph is not None:
            all_rows.extend(audit_book(graph, label))

    functional_rows = [r for r in all_rows if r["functional"]]
    nonfunctional_rows = [r for r in all_rows if not r["functional"]]

    report(functional_rows, "FUNCTIONAL steps (e1 of parent_father_of/parent_mother_of) - "
                              "frontier_size>1 here is unambiguously a problem")
    report(nonfunctional_rows, "NON-FUNCTIONAL steps - multi-valued frontiers may be legitimate")

    print("\n-- functional-step contamination by book (the real fragmentation rate) --")
    by_book = defaultdict(list)
    for r in functional_rows:
        by_book[r["book"]].append(r)
    for book, rs in sorted(by_book.items()):
        bad = sum(1 for r in rs if r["category"] != "pure")
        print(f"  {book:<20} {bad}/{len(rs)} = {bad/len(rs):.1%}" if rs else f"  {book}: n=0")

    print("\n-- worst functional-step examples (manual spot-check) --")
    worst = sorted((r for r in functional_rows if r["category"] != "pure"),
                   key=lambda r: -r["frontier_size"])
    for r in worst[:10]:
        print(f"  {r['book']}: {r['anchor']} -{r['relation']}:{r['role']}-> "
              f"[{r['category']}] {r['frontier']}")

    print("\n-- pronoun_generic examples, non-functional steps (Week 8 Stage C evidence) --")
    pg = [r for r in nonfunctional_rows if r["category"] == "pronoun_generic"][:8]
    for r in pg:
        print(f"  {r['book']}: {r['anchor']} -{r['relation']}:{r['role']}-> {r['frontier']}")


if __name__ == "__main__":
    main()