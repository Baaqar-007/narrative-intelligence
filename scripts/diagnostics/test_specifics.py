import networkx as nx

from graph.traversal import find_paths_up_to_hops
from retrieval.hybrid_search import _is_redundant_continuation, _terminal_answer
from resolution.pronoun_filter import resolve_canonical, is_pronoun_generic
def test_mrs_transome_2hop_not_dropped_by_redundancy_or_other_exclusion():
    """Regression for the overshoot-fix session: a correct, terminal-
    relation-matching 2-hop chain was disappearing between raw_chains
    and the final filtered output, for reasons not resolved by tracing
    live diagnostic output. Isolates the exact chain-filtering block
    against a minimal synthetic graph reproducing the real shape."""
    g = nx.MultiDiGraph()
    g.add_edge("mrs. transome", "harold", relation="parent_mother_of")
    g.add_edge("harold", "jermyn", relation="parent_father_of")
    g.add_edge("jermyn", "daughters", relation="parent_father_of")

    raw_chains = find_paths_up_to_hops(
        g, max_hops=3, start_node="mrs. transome", max_samples=20,
        allowed_relations={"parent_mother_of", "parent_father_of"},
    )

    target_relation = "parent_father_of"
    other = "harold"  # whatever the real `other` binding should be - this is what I need to confirm
    expand_from = "mrs. transome"

    kept = []
    for c in raw_chains:
        if (c["relations"] and c["relations"][-1] == target_relation
                and not _is_redundant_continuation(c, raw_chains, target_relation)):
            answer = resolve_canonical(_terminal_answer(c), {})
            if answer not in (expand_from, other) and not is_pronoun_generic(answer):
                kept.append((c["path"], answer))
    print(len(raw_chains))
    for c in raw_chains:
        print(c["path"], c["relations"])
    print(f"kept={kept}")
    for c in raw_chains:
        print(c["path"], c["relations"], c["directions"], "-> terminal_answer:", _terminal_answer(c))
    # The 2-hop answer must survive; the 3-hop overshoot must not.
    assert (["mrs. transome", "harold", "jermyn"], "jermyn") in kept
    assert not any(path == ["mrs. transome", "harold", "jermyn", "daughters"] for path, _ in kept) 
    
def test_jermyn_graphs():
    from graph.corpus import load_corpus
    from pathlib import Path

    corpus = load_corpus(Path("data/graphs/corpus.pkl"))
    graph = corpus["40882"]
    for u, v, data in graph.edges(nbunch=["jermyn", "harold"], data=True):
        print(u, "->", v, data.get("relation"))

def test_bidirectional_edges():
        # scripts/diagnostics/bidirectional_edge_audit.py
    """Corpus-wide check for the pattern found manually on Felix Holt
    (day 9): the SAME (u, v, relation) pair stored as edges in BOTH
    directions - u->v AND v->u, same relation - which is a different,
    more concrete problem than general direction-inconsistency (used_by,
    married_to): those were "entity1 sometimes plays the wrong role,"
    this is "both roles asserted simultaneously for the same pair,"
    unresolvable by any traversal/direction-detection logic since it's a
    genuine logical contradiction at the data level, not a role-labeling
    error.

    Scoped to the FUNCTIONAL_STEPS relations (parent_father_of/
    parent_mother_of, e1 role) since those are the ones where a
    bidirectional contradiction is unambiguous - X cannot be both parent
    and child of Y under the same relation type, whereas a symmetric
    relation (companion_of, enemy_of) having both directions stored is
    expected and NOT a contradiction (that's exactly what
    SYMMETRIC_RELATIONS already assumes is normal).
    """

    from collections import defaultdict
    from pathlib import Path

    from graph.corpus import load_corpus

    DATA_DIR = Path("data")
    CONTRADICTION_CHECK_RELATIONS = {"parent_father_of", "parent_mother_of", "spouse_of",
                                    "sibling_of", "child_of"}
    # spouse_of/sibling_of included despite being in SYMMETRIC_RELATIONS
    # elsewhere in the codebase - included here deliberately to measure
    # whether genuinely CONTRADICTORY pairs (not just expected-symmetric
    # ones) show up even for those types; see note in report().


    def find_bidirectional_pairs(graph, relations):
        """Returns {(relation, frozenset({u, v})): [(u,v) edges found]}
        for every pair where BOTH u->v and v->u exist under the same
        relation."""
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


    def check():
        corpus = load_corpus(DATA_DIR / "graphs" / "corpus.pkl")
        all_contradictions = []

        for book_id, graph in corpus.items():
            if graph is None or graph.number_of_nodes() == 0:
                continue
            found = find_bidirectional_pairs(graph, CONTRADICTION_CHECK_RELATIONS)
            for (rel, pair), example in found.items():
                all_contradictions.append({"book_id": book_id, "relation": rel, "pair": pair, "example": example})

        print(f"Books checked: {sum(1 for g in corpus.values() if g and g.number_of_nodes() > 0)}")
        print(f"Total bidirectional-contradiction pairs found: {len(all_contradictions)}\n")

        by_relation = defaultdict(int)
        for c in all_contradictions:
            by_relation[c["relation"]] += 1
        print("-- by relation --")
        for rel, n in sorted(by_relation.items(), key=lambda kv: -kv[1]):
            note = " (symmetric relation - expected, not necessarily a real contradiction)" \
                if rel in ("spouse_of", "sibling_of") else ""
            print(f"  {rel:<20} {n}{note}")

        print("\n-- parent_father_of / parent_mother_of contradictions (genuinely unambiguous) --")
        strict = [c for c in all_contradictions if c["relation"] in ("parent_father_of", "parent_mother_of")]
        for c in strict[:20]:
            u, v = c["example"]
            print(f"  [{c['book_id']}] {u} <-> {v}  ({c['relation']}, both directions stored)")
        if len(strict) > 20:
            print(f"  ... and {len(strict) - 20} more")

        print(f"\nTotal strict (parent_father_of/parent_mother_of) contradictions: {len(strict)}")

    check()


if __name__ == "__main__":
    # test_mrs_transome_2hop_not_dropped_by_redundancy_or_other_exclusion()
    # test_jermyn_graphs()
    test_bidirectional_edges()