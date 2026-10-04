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
    
    

if __name__ == "__main__":
    test_mrs_transome_2hop_not_dropped_by_redundancy_or_other_exclusion()