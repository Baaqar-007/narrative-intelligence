"""Benchmark: hybrid retrieval vs. vector-only baseline, using ARF's
ground-truth relations to auto-generate evaluation questions.

Week 7 rewrite - what changed and why (kept in-module, not just in
chat history, per this project's own convention of documenting
hard-won findings next to the code they affect):

1. SINGLE-HOP PHRASING BUG (found and fixed first, before any
   traversal work). generate_questions() used to derive question
   phrasing ad hoc from the raw relation string, independently of
   embedding.relation_text.MANUAL_TEMPLATES - two sources of truth
   for the same direction fact, and only one was verified. Confirmed
   on real data: child_of, protector_of, and leader_of all produced
   questions asking the OPPOSITE of their own ground truth (e.g. "Who
   is child of Will?" naturally asks who Will's child is; ground
   truth was Will's parent). Fixed by deriving questions mechanically
   from the already-verified templates (relation_to_question()),
   rather than re-deriving direction from the relation string a
   second time. Scope is now 31/48 canonical relation types (those
   with a verified template) - a real, deliberate narrowing, not an
   oversight.

2. N-HOP TRAVERSAL WAS FORWARD-EDGE-ONLY. graph_n_hop_search() and
   find_n_hop_paths() only followed outgoing edges - confirmed via
   direct NetworkX testing that .edges(nbunch=[node]) never returns
   in-edges, so the `other = v if u == node else u` branch handling
   the reverse case was dead code. This silently missed real
   reachability for relation types ARF stores inconsistently in
   direction (README, Week 2: companion_of and other symmetric types
   appear both directions for the same pair). Fixed by also querying
   .in_edges(), but SCOPED to only the 7 confirmed-inconsistent
   symmetric relation types (SYMMETRIC_RELATIONS below), not all 48.
   Measured before scoping: unscoped direction-agnostic traversal
   recovers real reachability (3.5-4x growth at 2-3 hops on real
   data) but skews recovered nodes toward high degree; scoping to
   symmetric-only relations cuts absolute recovered volume (~31% less
   at 2 hops) but does NOT reduce the degree skew - high-degree nodes
   in this corpus are protagonists connected via many relation types
   at once, not an artifact of which relation type reaches them. Skew
   is MEASURED, not shown harmful - those are separate claims. See the
   pre-registered revisit trigger below.

3. evaluate_nhop_graph() (REMOVED, replaced by
   validate_graph_reachability()) was a self-consistency check
   wearing a capability-benchmark's clothes: once both question
   generation (find_n_hop_paths) and evaluation shared identical
   traversal logic, near-100% "accuracy" was close to guaranteed by
   construction, not evidence anything improved. Kept as a sanity
   check instead - independently verified via a graph deliberately
   mirrored to match our traversal's exact direction semantics, then
   checked with networkx's own (separately-implemented)
   shortest_path_length, not our own BFS compared against itself.
   This catches real implementation bugs in our hand-rolled BFS; it
   does not, and cannot, make "graph traversal finds paths that exist
   in the graph" an interesting capability claim - it was never one.
   evaluate_nhop_baseline() (vector-only) remains the genuinely
   meaningful, non-tautological signal in this suite: pure semantic
   search really does struggle to chain multi-hop facts, and that's
   worth tracking.

PRE-REGISTERED REVISIT TRIGGER for the symmetric-only scoping
decision (point 2): revisit only if evaluate_direction_aware()
accuracy is meaningfully worse for questions whose correct_answer is
a low-degree node vs. a hub node. Elevated protagonist-centrality in
a narrative graph may be structurally correct, not a defect - this
must be checked against actual retrieval accuracy, not against
degree-distribution statistics alone. Any future degree-cap
mitigation must be validated the same way, not against its own
distribution output.

HISTORICAL NUMBERS ARE VOID: the 72%/26% multi-hop figures from v1
are not comparable to any rerun of this module - both the traversal
and the question-generation logic changed.


"""

import random
from dataclasses import dataclass

import networkx as nx
import pandas as pd

from embedding.relation_text import relation_to_question
from embedding.vector_store import query_relations
from graph.canonicalization import normalize_entity_name
from retrieval.hybrid_search import hybrid_search
from graph.traversal import find_n_hop_paths, graph_n_hop_search, _direction_aware_undirected_view
# ---------------------------------------------------------------------
# Single-hop, direction-aware benchmark
# ---------------------------------------------------------------------

@dataclass
class BenchmarkQuestion:
    """One auto-generated single-hop evaluation question with a
    known-correct answer and the source relation type.
    """

    query: str
    book_id: str
    correct_answer: str  # canonicalized entity name
    source_relation: str


def generate_questions(df: pd.DataFrame, n_samples: int = 200, seed: int = 42) -> list[BenchmarkQuestion]:
    """Sample relation instances with a verified question template and
    generate single-hop benchmark questions.

    Only relations with a verified template (see
    embedding.relation_text.relation_to_question) are eligible -
    31/48 canonical types. An unverified direction would silently
    test the wrong thing in a direction-aware benchmark; see module
    docstring point 1.

    Args:
        df: Parsed ARF dataframe.
        n_samples: How many questions to generate.
        seed: Random seed, for reproducible sampling.

    Returns:
        A list of BenchmarkQuestions, sampled across multiple books.
    """
    rng = random.Random(seed)

    candidates = []
    for _, row in df.iterrows():
        for r in row["relations_parsed"]:
            if relation_to_question(r["entity1"], r["relation"]) is not None:
                candidates.append((row["book_id"], r))

    sampled = rng.sample(candidates, min(n_samples, len(candidates)))

    questions = []
    for book_id, r in sampled:
        questions.append(BenchmarkQuestion(
            query=relation_to_question(r["entity1"], r["relation"]),
            book_id=book_id,
            correct_answer=normalize_entity_name(r["entity2"]),
            source_relation=r["relation"],
        ))
    return questions


def evaluate_direction_aware(collection, model, corpus: dict, questions: list[BenchmarkQuestion], k: int = 5) -> dict:
    """Checks whether the CORRECTLY-DIRECTED fact is found, not just
    whether the right name appears anywhere among candidates.

    Unaffected by the Week 7 traversal changes (single-hop only) -
    unchanged from the original except for benefiting from
    generate_questions()'s corrected phrasing.
    """
    baseline_correct = 0
    hybrid_correct = 0

    for q in questions:
        result = query_relations(collection, q.query, model, n_results=1, book_id=q.book_id)
        if result["metadatas"][0]:
            meta = result["metadatas"][0][0]
            if meta["relation"] == q.source_relation and meta["entity2"] == q.correct_answer:
                baseline_correct += 1

        hits = hybrid_search(collection, q.query, model, corpus, n_results=k, book_id=q.book_id)
        found = False
        for hit in hits:
            for r in hit.all_relationships:
                if r["relation"] == q.source_relation and r["entity2"] == q.correct_answer:
                    found = True
                    break
        if found:
            hybrid_correct += 1

    n = len(questions)
    return {
        "n_questions": n,
        "baseline_direction_correct": baseline_correct / n,
        "hybrid_direction_correct": hybrid_correct / n,
    }




# ---------------------------------------------------------------------
# N-hop question generation and evaluation
# ---------------------------------------------------------------------

@dataclass
class NHopQuestion:
    query: str
    book_id: str
    start_entity: str
    correct_answer: str
    hops: int


def _chain_phrase(start: str, relations: list[str], directions: list[str]) -> str | None:
    """Build a step-by-step, direction-verified question from a chain
    of relations - not nested possessives ("the enemy of the
    companion of X"), which reproduces the single-hop direction bug,
    compounded once per hop.

    Each step reuses relation_to_question() directly - the first hop
    with the real start entity as subject, every subsequent hop with
    "that entity" as a placeholder subject for the previous step's
    (unknown) answer. direction picks which grammatical role the
    subject plays at that hop (see find_n_hop_paths).

    Returns:
        A multi-sentence question string, or None if ANY hop's
        relation lacks a verified template - one unverified hop
        anywhere invalidates the whole chain's ground truth.
    """
    steps = []
    subject = start
    for i, (rel, direction) in enumerate(zip(relations, directions)):
        question = relation_to_question(subject, rel, direction=direction)
        if question is None:
            return None
        if i == 0:
            steps.append(question)
        else:
            steps.append("Then, " + question[0].lower() + question[1:])
        subject = "that entity"
    return " ".join(steps)


def generate_nhop_questions(corpus: dict[str, nx.MultiDiGraph], hops: int, n_samples: int = 100, seed: int = 42) -> list[NHopQuestion]:
    """Generate natural-language n-hop questions with a specific,
    single correct answer, using real sampled paths and their true
    relation/direction chain for phrasing.
    """
    rng = random.Random(seed)
    candidates = []

    for book_id, graph in corpus.items():
        for path_info in find_n_hop_paths(graph, hops, max_samples=20):
            candidates.append((book_id, path_info))

    sampled = rng.sample(candidates, min(n_samples, len(candidates)))

    questions = []
    for book_id, path_info in sampled:
        phrase = _chain_phrase(path_info["start"], path_info["relations"], path_info["directions"])
        if phrase is None:
            continue
        questions.append(NHopQuestion(
            query=phrase,
            book_id=book_id,
            start_entity=path_info["start"],
            correct_answer=path_info["end"],
            hops=hops,
        ))
    return questions


def evaluate_nhop_baseline(collection, model, questions: list[NHopQuestion], k: int = 10) -> float:
    """Vector-only: one query per question, checks if the correct
    answer entity appears anywhere in top-k results. No mechanism to
    chain facts - this remains the genuinely meaningful,
    non-tautological signal in this benchmark suite (see module
    docstring point 3).
    """
    correct = 0
    for q in questions:
        result = query_relations(collection, q.query, model, n_results=k, book_id=q.book_id)
        entities = set()
        for meta in result["metadatas"][0]:
            entities |= {meta["entity1"], meta["entity2"]}
        if q.correct_answer in entities:
            correct += 1
    return correct / len(questions)


def validate_graph_reachability(corpus: dict, questions: list[NHopQuestion]) -> dict:
    """Sanity check, NOT a capability benchmark (see module docstring
    point 3 for why evaluate_nhop_graph() was replaced with this).

    Cross-validates our hand-rolled graph_n_hop_search() against
    networkx's own, independently-implemented shortest_path_length,
    run on a graph explicitly mirrored to match our traversal's exact
    direction semantics. This catches real bugs in our own BFS; it
    does not make "graph finds paths that exist in the graph" an
    interesting capability claim on its own.

    Returns:
        Dict with n_questions, agreement_rate (our check vs. nx's
        independent check - should be ~1.0; a mismatch is a real bug
        in our traversal, not a capability gap) and reachable_rate
        (fraction independently confirmed reachable - expected near
        1.0 by construction, NOT a metric to report as "graph
        accuracy" going forward).
    """
    agreement, reachable, n = 0, 0, len(questions)
    for q in questions:
        graph = corpus.get(q.book_id)
        if graph is None:
            n -= 1
            continue
        our_reachable = q.correct_answer in graph_n_hop_search(graph, q.start_entity, q.hops)
        mirrored = _direction_aware_undirected_view(graph)
        try:
            nx_reachable = nx.shortest_path_length(mirrored, q.start_entity, q.correct_answer) <= q.hops
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            nx_reachable = False
        if our_reachable == nx_reachable:
            agreement += 1
        if nx_reachable:
            reachable += 1
    return {
        "n_questions": n,
        "agreement_with_independent_check": agreement / n if n else 0.0,
        "reachable_rate": reachable / n if n else 0.0,
    }
