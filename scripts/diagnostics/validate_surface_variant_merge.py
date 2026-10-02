# scripts/diagnostics/validate_surface_variant_merge.py
"""Real-corpus validation for resolution/surface_variant_merge.py.
Per the standing rule, unit tests passing is not sufficient - this
checks two things unit tests can't: (1) do the specific day-4/5 known
cases still cluster correctly when run against the real, full node
set (not a constructed 3-4 node graph), and (2) does anything ELSE
in the corpus get merged that shouldn't - the Mrs. Holt/Mrs. Transome
risk, at scale, not just the one pair we already caught by hand.

Imports shared primitives rather than reconstructing them - first
step toward the scripts/diagnostics/ consolidation flagged at the
end of day 6, not another standalone reimplementation.
"""

from pathlib import Path

from graph.corpus import load_corpus
from resolution.pronoun_filter import build_resolution_map
from resolution.surface_variant_merge import build_surface_variant_map

DATA_DIR = Path("data")
BOOKS = {"40882": "Felix Holt", "106": "Tarzan", "12753": "King Arthur",
         "47634": "Sons and Lovers", "52617": "Decameron", "73548": "Rhinegold"}

# Known-correct clusters from days 4-5's manual inspection - each
# should appear as ONE cluster (same canonical_form) after this run.
EXPECTED_CLUSTERS = {
    "Sons and Lovers": [{"morel", "mr. morel", "walter morel"}],  # keep - but now expect AMBIGUOUS, not merged
    "Decameron": [{"messer lizio", "messer lizio da valbonna", "lizio"}],
}

# Known-should-NOT-merge pairs - the Mrs. Holt/Mrs. Transome catch,
# plus the cross-story title risk (different "count"s across
# different Decameron novellas sharing one book_id).
EXPECTED_NON_MERGES = {
    "Felix Holt": [("mrs. holt", "mrs. transome")],
}




def cluster_of(entity, resolution_map):
    entry = resolution_map.get(entity)
    if entry is None or entry.canonical_form is None:
        return entity  # unflagged, or ambiguous - treat as its own singleton, not interchangeable with other Nones
    return entry.canonical_form


def main():
    corpus = load_corpus(DATA_DIR / "graphs" / "corpus.pkl")
    all_maps = {}

    for book_id, label in BOOKS.items():
        graph = corpus.get(book_id)
        if graph is None:
            continue
        pronoun_map = build_resolution_map(graph)
        surface_map = build_surface_variant_map(graph, pronoun_generic_map=pronoun_map)
        all_maps[label] = surface_map
        print(f"{label}: {len(surface_map)} nodes merged into variant clusters")

    print("\n-- known-correct clusters: still correct? --")
    for label, clusters in EXPECTED_CLUSTERS.items():
        for expected in clusters:
            canon_forms = {cluster_of(n, all_maps[label]) for n in expected}
            ok = len(canon_forms) == 1
            print(f"  [{'OK' if ok else 'BROKEN'}] {label}: {expected} -> {canon_forms}")

    print("\n-- known-risk pairs: still correctly NOT merged? --")
    for label, pairs in EXPECTED_NON_MERGES.items():
        for a, b in pairs:
            merged = cluster_of(a, all_maps[label]) == cluster_of(b, all_maps[label])
            print(f"  [{'BROKEN' if merged else 'OK'}] {label}: {a!r} vs {b!r} "
                  f"-> {'MERGED (bad)' if merged else 'separate (good)'}")

    print("\n-- unexpected large clusters (manual spot-check candidates) --")
    c,m = 0,0
    for label, resolution_map in all_maps.items():
        by_canonical = {}
        for entry in resolution_map.values():
            if entry.canonical_form is None:
                continue  # ambiguous entries aren't a cluster with each other
            by_canonical.setdefault(entry.canonical_form, set()).add(entry.raw_name)
        for canon, members in by_canonical.items():
            if len(members) >= 4:
                c += 1
                m = max(m, len(members))
                print(f"  {label}: {canon!r} <- {members}")

    print("\n-- ambiguous entries, for separate review (NOT a cluster count) --")
    for label, resolution_map in all_maps.items():
        n = sum(1 for e in resolution_map.values() if e.canonical_form is None)
        print(f"  {label}: {n} nodes declined as ambiguous")
    print(f"\n{c} large clusters flagged for manual review (>=4 members)")
    print(f"Maximum cluster size: {m}")
    
    for name in ("mrs. holt", "mrs. transome"):
        entry = all_maps["Felix Holt"].get(name)
        print(name, "->", entry)


if __name__ == "__main__":
    main()