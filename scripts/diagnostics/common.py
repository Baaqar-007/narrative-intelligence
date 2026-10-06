# scripts/diagnostics/common.py
"""Shared primitives for diagnostic scripts - single source of truth
for logic that was independently reconstructed across multiple
scripts this week (build_index/step/walk/is_nameable all existed in
2+ places, drifting apart - the day-5 is_nameable gap and the day-9
diagnose_hops.py staleness are both direct instances of this). Import
from here; do not reimplement.

Also fixes the CSV-dumped-in-repo-root problem: OUTPUT_DIR is
absolute, derived from this file's own location, so it's correct
regardless of what directory a script is invoked from (python -m
scripts.diagnostics.whatever resolves relative paths against the
shell's cwd, not the script's location - this was the actual cause of
every CSV landing in repo root this week).
"""

from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd

from resolution.resolve import is_nameable  # single source of truth, per day-5/9 fix

OUTPUT_DIR = Path(__file__).parent / "output"
OUTPUT_DIR.mkdir(exist_ok=True)


def output_path(filename: str) -> Path:
    """Every diagnostic script should write CSVs via this, not a bare
    filename - e.g. df.to_csv(output_path('yardstick_results.csv'))."""
    return OUTPUT_DIR / filename


def build_index(graph):
    """Forward/reverse edge index by relation - book_id's graph, once
    per script run, reused across all step() calls rather than
    re-walking the graph per lookup."""
    out_, in_ = defaultdict(lambda: defaultdict(set)), defaultdict(lambda: defaultdict(set))
    for u, v, d in graph.edges(data=True):
        rel = d.get("relation")
        if rel:
            out_[rel][u].add(v)
            in_[rel][v].add(u)
    return out_, in_


def step(index, node, relation, want):
    """want: 'e1' (nodes with node as entity2, via in-edges), 'e2'
    (node as entity1, via out-edges), or 'sym' (union, for symmetric
    relations where the role distinction doesn't apply)."""
    out_, in_ = index
    e1s = in_[relation].get(node, set())
    e2s = out_[relation].get(node, set())
    if want == "e1":
        return set(e1s)
    if want == "e2":
        return set(e2s)
    return set(e1s) | set(e2s)


def walk(index, anchor, seq, frontier, hops, step_keys, steps_labels,
         enforce_purity=True, excluded=None):
    """Compose relation steps from `anchor`, yielding (sequence,
    gold_set) pairs at exactly `hops` depth. enforce_purity: an
    intermediate frontier (not yet at `hops`) must resolve to exactly
    one node before composing further - a multi-node intermediate
    frontier means gold would be a union across unrelated/variant
    entities (the Mrs. Transome bug, day 3). Terminal frontiers are
    NOT purity-checked - a real question can have many correct
    answers (Tarzan's 12 enemies).

    step_keys: ordered list of (relation, role) tuples to try at each
    hop. steps_labels: {(relation, role): display_noun}, used by
    callers for phrasing, not by walk() itself.
    """
    if len(seq) == hops:
        yield seq, frontier
        return
    if enforce_purity and len(frontier) > 1 and len(seq) > 0:
        if excluded is not None:
            excluded[0] += 1
        return
    for key in step_keys:
        nxt = set().union(*(step(index, n, *key) for n in frontier)) - {anchor}
        if nxt:
            yield from walk(index, anchor, seq + [key], nxt, hops, step_keys, steps_labels,
                             enforce_purity, excluded)


def token_overlap(frontier: set[str]) -> bool:
    """Heuristic: does every string in frontier share a token with
    the longest one - a candidate signal for 'surface-variant-like',
    NOT a merge decision (see resolution.surface_variant_merge for
    the actual, stricter merge logic - this is for diagnostic
    reporting only)."""
    if len(frontier) <= 1:
        return True
    longest = max(frontier, key=len)
    long_tokens = set(longest.split())
    return all(set(s.split()) & long_tokens for s in frontier if s != longest)


def make_hybrid_adapter(collection, model, corpus, resolution_maps=None):
    """End-to-end adapter over the live hybrid_search, including
    vector recall and (if resolution_maps given) entity resolution.
    Single definition - was reimplemented per-script, which is how
    the day-4 first_step_retrieved extension went unnoticed by later
    scripts built against an earlier remembered signature."""
    from retrieval.direction_detection import estimate_hop_depth
    from retrieval.hybrid_search import hybrid_search

    def run(question, book_id, anchor, first_rel, first_nodes):
        hits = hybrid_search(
            collection, question, model, corpus, n_results=5,
            book_id=book_id, hop_depth=estimate_hop_depth(question),
            resolution_maps=resolution_maps,
        )
        answers = {c.get("answer", c["end"]) for h in hits for c in h.chains}
        retrieved = {e for h in hits for e in (h.entity1, h.entity2)}
        first_ok = False
        for h in hits:
            if anchor not in (h.entity1, h.entity2):
                continue
            other = h.entity2 if h.entity1 == anchor else h.entity1
            if other in first_nodes and any(f["relation"] == first_rel for f in h.all_relationships):
                first_ok = True
                break
        return {"answers": answers, "anchor_retrieved": anchor in retrieved,
                "first_step_retrieved": first_ok}
    return run


def score(gold, result):
    """Single definition of the HIT/DECLINED/WRONG scoring contract -
    every script scoring yardstick-style output should use this, not
    reimplement the outcome logic."""
    answers = result["answers"]
    outcome = "DECLINED" if not answers else "HIT" if gold & answers else "WRONG"
    return {
        "outcome": outcome, "n_answers": len(answers),
        "precision": round(len(gold & answers) / len(answers), 2) if answers else "",
        "anchor_retrieved": result["anchor_retrieved"],
        "attribution": "" if outcome == "HIT" else
                       ("LOGIC" if result["anchor_retrieved"] else "RECALL"),
        "answers": ";".join(sorted(answers)),
        "first_step_retrieved": result["first_step_retrieved"],
    }