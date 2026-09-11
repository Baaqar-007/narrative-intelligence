"""Benchmark: hybrid retrieval vs. vector-only baseline, using ARF's
ground-truth relations to auto-generate evaluation questions.

History note: earlier iterations of this module included a plain
entity-membership metric (evaluate_baseline/evaluate_hybrid) that
turned out unable to detect hybrid retrieval's actual improvement
(direction correctness) - both systems scored identically (55% at
k=5), which was itself a real, documented finding (see README), not a
bug. That metric and the multi-hop-specific predecessors of the
functions below (MultiHopQuestion, find_two_hop_paths,
graph_multihop_search, evaluate_multihop_baseline/graph) were removed
after being superseded by the general n-hop versions kept here. Full
history is in git log, not preserved as dead code.
"""

import random
from dataclasses import dataclass

import networkx as nx
import pandas as pd

from embedding.vector_store import query_relations
from embedding.relation_text import relation_to_question
from graph.canonicalization import normalize_entity_name
# from graph.relation_ontology import is_canonical_relation
from retrieval.hybrid_search import hybrid_search


# ---------------------------------------------------------------------
# Single-hop, direction-aware benchmark
# ---------------------------------------------------------------------

@dataclass
class BenchmarkQuestion:
    """One auto-generated single-hop evaluation question with a
    known-correct answer and the source relation type/direction.
    """

    query: str
    book_id: str
    correct_answer: str  # canonicalized entity name
    source_relation: str



def generate_questions(df: pd.DataFrame, n_samples: int = 200, seed: int = 42) -> list[BenchmarkQuestion]:
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
# Multi-hop benchmark (general, any hop count)
# ---------------------------------------------------------------------

def find_n_hop_paths(graph: nx.MultiDiGraph, hops: int, max_samples: int = 500) -> list[dict]:
    """... (docstring as before, plus:)

    Returns:
        List of dicts: {'start', 'end', 'path', 'relations',
        'directions'} - 'directions' is "forward"/"reverse" per hop,
        same order and length as 'relations'. Needed downstream because
        direction-agnostic traversal means a hop's current node isn't
        guaranteed to play entity1's role for that relation instance.
    """
    paths = []

    def dfs(current, visited_nodes, visited_rels, visited_dirs, depth):
        if depth == hops:
            paths.append({
                "start": visited_nodes[0],
                "end": current,
                "path": visited_nodes + [current],
                "relations": list(visited_rels),
                "directions": list(visited_dirs),
            })
            return
        if len(paths) >= max_samples:
            return
        candidates = (
            [(v, data["relation"], "forward") for _, v, data in graph.edges(nbunch=[current], data=True)]
            + [(u, data["relation"], "reverse") for u, _, data in graph.in_edges(nbunch=[current], data=True)]
        )
        for other, relation, direction in candidates:
            if other not in visited_nodes:
                dfs(other, visited_nodes + [current], visited_rels + [relation], visited_dirs + [direction], depth + 1)

    for node in graph.nodes:
        if len(paths) >= max_samples:
            break
        dfs(node, [], [], [], 0)

    return paths


def graph_n_hop_search(graph: nx.MultiDiGraph, entity_a: str, hops: int) -> set[str]:
    """Return all entities reachable from entity_a within `hops` steps.

    Direction-agnostic: follows edges in either stored direction, not
    just outgoing. ARF stores symmetric relation types (companion_of,
    friend_of, enemy_of, rival_of, sibling_of, spouse_of, relative_of)
    inconsistently in direction (README, Week 2), so a forward-only
    traversal silently drops real, reachable entities whenever an
    instance happened to be stored the "other" way. Matches
    get_relationships_between()'s existing direction-agnostic design
    for pairwise lookups (temporal/trajectory.py) - this brings n-hop
    traversal in line with a precedent already established elsewhere
    in the project, rather than introducing a new philosophy.

    Cumulative across all hop depths up to `hops`, not just the final
    BFS layer (unchanged from the prior version - a node reachable via
    a path shorter than `hops` still counts).
    """
    frontier = {entity_a}
    visited = {entity_a}
    for _ in range(hops):
        next_frontier = set()
        for node in frontier:
            neighbors = {v for _, v, _ in graph.edges(nbunch=[node], data=True)}
            neighbors |= {u for u, _, _ in graph.in_edges(nbunch=[node], data=True)}
            next_frontier |= neighbors - visited
        visited |= next_frontier
        frontier = next_frontier
    return visited - {entity_a}


@dataclass
class NHopQuestion:
    query: str
    book_id: str
    start_entity: str
    correct_answer: str
    hops: int



def _chain_phrase(start: str, relations: list[str], directions: list[str]) -> str | None:
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
    """Generate natural-language n-hop questions with a specific, single
    correct answer, using real sampled paths and their true relation
    chain for phrasing (same phrasing style at every hop depth, so
    accuracy trends across hop counts are fairly comparable).
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
    chain facts - included as the honest baseline this can't do well.
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


def evaluate_nhop_graph(corpus: dict, questions: list[NHopQuestion]) -> float:
    """Graph traversal: does the correct answer fall within the true
    n-hop reachable set from the start entity?
    """
    correct = 0
    for q in questions:
        graph = corpus.get(q.book_id)
        if graph is None:
            continue
        reached = graph_n_hop_search(graph, q.start_entity, q.hops)
        if q.correct_answer in reached:
            correct += 1
    return correct / len(questions)
