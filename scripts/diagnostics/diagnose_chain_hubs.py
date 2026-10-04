"""H2 diagnostic, corrected: full chain logging (no truncation) and a
quantified hub-degree measurement instead of eyeballing entity names,
plus a positive-control question with a known-answerable chain.

Prerequisite fix from the first pass: the earlier script capped chain
sampling at [:5] per hit, which could hide exactly the pattern being
investigated. This logs every chain.
"""

import csv
import statistics
from pathlib import Path

from embedding.embed_relations import load_embedding_model
from embedding.vector_store import get_collection
from graph.corpus import load_corpus
from retrieval.direction_detection import estimate_hop_depth
from retrieval.hybrid_search import hybrid_search
from resolution.pronoun_filter import build_resolution_map
from resolution.surface_variant_merge import build_surface_variant_map

DATA_DIR = Path("data")
BOOK_ID_MAIN = "40882"  # adjust to a book you know well

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

# Positive control: book 106, real names already confirmed to exist
# this session (direction_coverage_log.csv). A genuine forward chain
# is expected to exist here - if THIS also drowns in noise, the
# problem is the traversal itself, not something specific to
# high-degree Felix Holt characters.
POSITIVE_CONTROL = ("Who is the enemy of the companion of taug?", "106")


def inspect_question(question, book_id, corpus, collection, model, resolution_maps=None):
    hop_depth = estimate_hop_depth(question)
    hits = hybrid_search(collection, question, model, corpus,
                          n_results=5, book_id=book_id, hop_depth=hop_depth,
                          resolution_maps=resolution_maps)
    
    from graph.traversal import find_paths_up_to_hops
    from retrieval.direction_detection import mentioned_relations, target_relation

    if "Esther Lyon" in question or "Transome's son" in question:
        graph_local = corpus.get(book_id)
        q_target = target_relation(question)
        allowed = mentioned_relations(question)
        print(f"\n[{question}]")
        print(f"  target_relation={q_target}  allowed={allowed}")
        for h in hits:
            for start in (h.entity1, h.entity2):
                raw = find_paths_up_to_hops(
                    graph_local, max_hops=hop_depth, start_node=start,
                    max_samples=20, allowed_relations=allowed,
                )
                for c in raw:
                    is_terminal = c["relations"] and c["relations"][-1] == q_target
                    print(f"  hop={len(c['path'])-1}  {c['path']}  "
                        f"rels={c['relations']}  terminal_match={is_terminal}")
    graph = corpus.get(book_id)
    degrees = dict(graph.degree()) if graph is not None else {}
    corpus_median_degree = statistics.median(degrees.values()) if degrees else None

    rows = []
    seen_chains = set()  # dedupe across hits - same fact retrieved via
                          # multiple chunks legitimately produces the
                          # same graph chain more than once; that's
                          # correct enrichment, not something to fix in
                          # hybrid_search, just don't double-count it here
    for hit in hits:
        for c in hit.chains:  # ALL chains, not chains[:5]
            key = (tuple(c["path"]), tuple(c["relations"]))
            if key in seen_chains:
                continue
            seen_chains.add(key)
            path_degrees = [degrees.get(node, None) for node in c["path"]]
            rows.append({
                "question": question, "hop_depth": hop_depth,
                "path": " -> ".join(c["path"]),
                "relations": ",".join(c["relations"]),
                "path_degrees": path_degrees,
                "max_degree_in_path": max((d for d in path_degrees if d is not None), default=None),
                "corpus_median_degree_for_reference": corpus_median_degree,
            })
    
    return rows


def main():
    corpus = load_corpus(DATA_DIR / "graphs" / "corpus.pkl")
    collection = get_collection(path=str(DATA_DIR / "chroma"))
    model = load_embedding_model()
    
    # Build once, reuse across questions. Every book hit by this
    # diagnostic needs an entry, or hits on that book silently get
    # resolution_map = {} and today's work isn't exercised for it.
    book_ids = {BOOK_ID_MAIN, POSITIVE_CONTROL[1]}
    resolution_maps = {}
    for bid in book_ids:
        g = corpus.get(bid)
        if g is None:
            continue
        pm = build_resolution_map(g)
        resolution_maps[bid] = build_surface_variant_map(g, pronoun_generic_map=pm)

    print(f"resolution_maps built for: {list(resolution_maps)}")
    print(f"  40882 entries: {len(resolution_maps.get('40882', {}))}")
    print(f"  106 entries:   {len(resolution_maps.get('106', {}))}")
    for probe in ("her son", "my own son", "your son", "the child"):
        if probe in resolution_maps.get("40882", {}):
            print(f"  '{probe}' -> {resolution_maps['40882'][probe].canonical_form}")
    # --- diagnostic: what's actually in the map ---
    m40882 = resolution_maps.get("40882", {})
    m106   = resolution_maps.get("106", {})
    print(f"\n=== resolution_map sizes ===")
    print(f"  40882: {len(m40882)} entries")
    print(f"  106:   {len(m106)} entries")

    probes = ["her son", "my own son", "your son", "the child", "she", "her",
              "you", "father", "mother", "son", "mr. lyon", "esther",
              "mrs. transome", "harold", "jermyn"]
    print(f"\n=== which probes are in 40882 map ===")
    for p in probes:
        entry = m40882.get(p)
        if entry is None:
            print(f"  {p!r:<20} NOT IN MAP")
        else:
            print(f"  {p!r:<20} tier={entry.tier}  canonical={entry.canonical_form!r}")
    # --- end diagnostic ---
    
    from collections import Counter
    m = resolution_maps.get("40882", {})
    tiers = Counter(e.tier for e in m.values())
    print(f"\n=== tier breakdown 40882 ===")
    for tier, n in tiers.items():
        print(f"  {tier}: {n}")
    print(f"  total: {len(m)}")
    all_rows = []
    for q in TEST_QUESTIONS:
        rows = inspect_question(q, BOOK_ID_MAIN, corpus, collection, model, resolution_maps=resolution_maps)
        all_rows.extend(rows)
        print(f"\n=== {q!r}: {len(rows)} chains ===")
        for r in rows:
            ref = r["corpus_median_degree_for_reference"] or 1
            flag = " <- HIGH DEGREE" if (r["max_degree_in_path"] or 0) > 3 * ref else ""
            print(f"  {r['path']}  [{r['relations']}]  max_degree={r['max_degree_in_path']}{flag}")

    pc_question, pc_book = POSITIVE_CONTROL
    pc_rows = inspect_question(pc_question, pc_book, corpus, collection, model, resolution_maps=resolution_maps)
    all_rows.extend([{**r, "question": f"[POSITIVE CONTROL] {r['question']}"} for r in pc_rows])
    print(f"\n=== POSITIVE CONTROL {pc_question!r}: {len(pc_rows)} chains ===")
    for r in pc_rows:
        print(f"  {r['path']}  [{r['relations']}]  max_degree={r['max_degree_in_path']}")
    if not pc_rows:
        print("  ** No chains found even for the positive control - traversal "
              "itself may be the issue, not just hub-degree **")

    with open("chain_hub_inspection.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(all_rows[0].keys()))
        writer.writeheader()
        writer.writerows(all_rows)
    print("\nWritten to chain_hub_inspection.csv")


if __name__ == "__main__":
    main()
