"""Correctness yardstick for multi-hop (2+ hop) question answering.

Ground truth: composed relation steps over the raw stored edges
(ARF = source of truth), one (relation, role) step per hop. Measures
fidelity to the graph as stored, NOT real-world truth - it cannot see
ARF direction noise. Single-hop is out of scope (Benchmark 2 covers it).

Outcomes: HIT (gold & answers non-empty), DECLINED (no answers),
WRONG (answers returned, none in gold). Headline metric: WRONG rate.
Misses are attributed RECALL (anchor never retrieved) vs LOGIC.

Anchors must be nameable (a question can't be asked about "her");
gold answers are only TAGGED (Week 8 entanglement), never filtered.
Systems under test plug in via an adapter:
    adapter(question, book_id, anchor) -> {"answers": set, "anchor_retrieved": bool}
"""

import csv
import random
import string
from collections import Counter, defaultdict
from pathlib import Path

from embedding.embed_relations import load_embedding_model
from embedding.vector_store import get_collection
from graph.corpus import load_corpus
from graph.relation_ontology import SYMMETRIC_RELATIONS

DATA_DIR = Path("data")
BOOKS = {"40882": "Felix Holt", "106": "Tarzan", "12753": "King Arthur",
         "47634": "Sons and Lovers", "52617": "Decameron", "73548": "Rhinegold"}
SEED, HOPS, CAP_PER_COMBO = 0, 2, 5

# noun -> the slot of the STORED triple that noun names (= the answer
# slot for "the <noun> of K"). "sym" = symmetric relation, role moot.
# Hand-verified against MANUAL_TEMPLATES. First noun per (relation, role)
# is the one used to phrase questions.
ROLE_NOUNS: dict[str, dict[str, str]] = {
    "parent_father_of": {"father": "e1", "son": "e2"},
    "parent_mother_of": {"mother": "e1", "son": "e2"},
    "child_of": {"child": "e1"},
    "spouse_of": {"spouse": "sym", "husband": "sym", "wife": "sym"},
    "sibling_of": {"sibling": "sym", "brother": "sym", "sister": "sym"},
    "companion_of": {"companion": "sym"},
    "friend_of": {"friend": "sym"},
    "enemy_of": {"enemy": "sym"},
    "rival_of": {"rival": "sym"},
    "relative_of": {"relative": "sym"},
    "employer_of": {"employer": "e1"}, "leader_of": {"leader": "e1"},
    "mentor_of": {"mentor": "e1"}, "teacher_of": {"teacher": "e1"},
    "protector_of": {"protector": "e1"},
}
assert all(r in SYMMETRIC_RELATIONS for r, m in ROLE_NOUNS.items() if "sym" in m.values()), \
    "ROLE_NOUNS marks a relation 'sym' that SYMMETRIC_RELATIONS doesn't contain"

STEPS: dict[tuple[str, str], str] = {}
for _rel, _nouns in ROLE_NOUNS.items():
    for _noun, _role in _nouns.items():
        STEPS.setdefault((_rel, _role), _noun)
STEP_KEYS = sorted(STEPS)
GENDERED = {"son", "daughter", "husband", "wife", "brother", "sister"}

from resolution.pronoun_filter import is_pronoun_generic

_FUNCTION_WORDS = {"he", "she", "her", "his", "him", "you", "your", "my", "me", "i", "we",
                   "our", "us", "they", "them", "their", "it", "its", "the", "a", "an",
                   "this", "that", "these", "those", "some", "little", "young", "old"}

# Social-role/title descriptors - NOT kinship or pronoun patterns, so
# deliberately NOT folded into resolution.pronoun_filter (a different
# category, unvalidated at that module's level). Day-5 audit found
# "gentlewoman" playing the same generic-anchor role as the kinship
# nouns; "the count"/"the king" (definite article + bare title) is a
# related but distinct pattern this set does not catch - flagged,
# not fixed here.
_SOCIAL_ROLE_GENERIC = {"party", "people", "man", "woman", "boy", "girl", "lady", "gentlewoman"}


def is_nameable(entity: str) -> bool:
    """Heuristic only: could a real query plausibly contain this
    string? The kinship/pronoun check now delegates to
    resolution.pronoun_filter.is_pronoun_generic (single source of
    truth, day-5 fix) - this function previously kept its own
    separate _GENERIC set, derived from ROLE_NOUNS, which had
    silently drifted out of sync with the live resolution module
    (missing "daughter" despite "son" being present in both)."""
    tokens = entity.split()
    return (1 <= len(tokens) <= 4
            and tokens[0].lower() not in _FUNCTION_WORDS
            and not is_pronoun_generic(entity)
            and entity.lower() not in _SOCIAL_ROLE_GENERIC)


def build_index(graph):
    out_, in_ = defaultdict(lambda: defaultdict(set)), defaultdict(lambda: defaultdict(set))
    for u, v, d in graph.edges(data=True):
        rel = d.get("relation")
        if rel in ROLE_NOUNS and u != v:
            out_[rel][u].add(v)
            in_[rel][v].add(u)
    return out_, in_


def step(index, node, relation, want):
    out_, in_ = index
    e1s = in_[relation].get(node, set())   # X with X -rel-> node
    e2s = out_[relation].get(node, set())  # Y with node -rel-> Y
    return set(e1s) if want == "e1" else set(e2s) if want == "e2" else set(e1s) | set(e2s)


def walk(index, anchor, seq, frontier, hops, enforce_purity=True, excluded=None):
    if len(seq) == hops:
        yield seq, frontier
        return
    if enforce_purity and len(frontier) > 1 and len(seq) > 0:
        if excluded is not None:
            excluded[0] += 1
        return
    for key in STEP_KEYS:
        nxt = set().union(*(step(index, n, *key) for n in frontier)) - {anchor}
        if nxt:
            yield from walk(index, anchor, seq + [key], nxt, hops, enforce_purity, excluded)


def generate(graph, book_id, rng, hops, cap, enforce_purity=True):
    index, degree = build_index(graph), dict(graph.degree())
    anchors = sorted(n for n in graph.nodes if is_nameable(n))
    rng.shuffle(anchors)
    combo_counts, out, excluded = Counter(), [], [0]
    for anchor in anchors:
        for seq, gold in walk(index, anchor, [], {anchor}, hops, enforce_purity, excluded):
            label = " > ".join(f"{r}:{w}" for r, w in seq)
            if combo_counts[label] >= cap:
                continue
            combo_counts[label] += 1
            phrase = string.capwords(anchor)
            for key in seq:
                phrase = f"the {STEPS[key]} of {phrase}"
            out.append({
                "book_id": book_id, "question": f"Who is {phrase}?", "anchor": anchor,
                "sequence": label, "hops": hops, "gold_set": gold,
                "gold": ";".join(sorted(gold)), "gold_size": len(gold),
                "unique": len(gold) == 1,
                "gold_nameable_frac": round(sum(map(is_nameable, gold)) / len(gold), 2),
                "gold_max_degree": max(degree.get(g, 0) for g in gold),
                "anchor_degree": degree.get(anchor, 0),
                "first_step_symmetric": seq[0][1] == "sym",
                "first_rel": seq[0][0],
                "first_nodes": step(index, anchor, *seq[0]),
                "gendered": any(STEPS[k] in GENDERED for k in seq)
            })
    print(f"  [{book_id}] excluded by purity filter: {excluded[0]}")
    return out


def make_hybrid_adapter(collection, model, corpus):
    """End-to-end adapter over the live hybrid_search (includes vector recall)."""
    from retrieval.direction_detection import estimate_hop_depth
    from retrieval.hybrid_search import hybrid_search

    def run(question, book_id, anchor, first_rel, first_nodes):
        hits = hybrid_search(collection, question, model, corpus, n_results=5,
                            book_id=book_id, hop_depth=estimate_hop_depth(question))
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
    answers = result["answers"]
    outcome = "DECLINED" if not answers else "HIT" if gold & answers else "WRONG"
    return {
        "outcome": outcome, "n_answers": len(answers),
        "precision": round(len(gold & answers) / len(answers), 2) if answers else "",
        "anchor_retrieved": result["anchor_retrieved"],
        "attribution": "" if outcome == "HIT" else
                       ("LOGIC" if result["anchor_retrieved"] else "RECALL"),
        "answers": ";".join(sorted(answers)),
        "first_step_retrieved": result["first_step_retrieved"]
    }


def summarize(rows, key_fn, label):
    groups = defaultdict(list)
    for r in rows:
        groups[key_fn(r)].append(r)
    print(f"\n-- by {label} --")
    for g, rs in sorted(groups.items(), key=lambda kv: str(kv[0])):
        c, n = Counter(r["outcome"] for r in rs), len(rs)
        print(f"  {g!s:<30} n={n:<5} HIT {c['HIT']/n:6.1%}  "
              f"DECLINED {c['DECLINED']/n:6.1%}  WRONG {c['WRONG']/n:6.1%}")


def main():
    corpus = load_corpus(DATA_DIR / "graphs" / "corpus.pkl")
    adapter = make_hybrid_adapter(get_collection(path=str(DATA_DIR / "chroma")),
                                  load_embedding_model(), corpus)
    rng, rows = random.Random(SEED), []
    for book_id, label in BOOKS.items():
        graph = corpus.get(book_id)
        if graph is None:
            continue
        for q in generate(graph, book_id, rng, HOPS, CAP_PER_COMBO):
            rows.append({**q, "book": label, **score(q["gold_set"], adapter(q["question"], book_id, q["anchor"], q["first_rel"], q["first_nodes"]))})
        print(f"{label}: {sum(r['book_id'] == book_id for r in rows)} questions")

    fields = ["book", "book_id", "question", "anchor", "sequence", "hops", "gold", "gold_size",
              "unique", "gold_nameable_frac", "gold_max_degree", "anchor_degree",
              "first_step_symmetric", "gendered", "outcome", "attribution", "n_answers",
              "precision", "anchor_retrieved", "first_step_retrieved", "answers"]
    with open("yardstick_results.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)

    summarize(rows, lambda r: "all", "overall")
    summarize(rows, lambda r: r["book"], "book")
    summarize(rows, lambda r: r["first_step_symmetric"], "first step symmetric")
    summarize(rows, lambda r: r["unique"], "unique gold answer")
    summarize(rows, lambda r: r["gendered"], "gendered noun")
    summarize(rows, lambda r: r["attribution"] or "HIT", "miss attribution")


if __name__ == "__main__":
    main()