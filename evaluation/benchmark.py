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
    """Find real n-hop paths in a graph via DFS, including the relation
    type traversed at each hop (used for natural-language question
    phrasing - see generate_nhop_questions).

    Returns:
        List of dicts: {'start', 'end', 'path': [nodes], 'relations':
        [relation types, in traversal order]}. All nodes in a path are
        distinct (no revisits).
    """
    paths = []

    def dfs(current: str, visited_nodes: list[str], visited_rels: list[str], depth: int):
        if depth == hops:
            paths.append({
                "start": visited_nodes[0],
                "end": current,
                "path": visited_nodes + [current],
                "relations": list(visited_rels),
            })
            return
        if len(paths) >= max_samples:
            return
        for u, v, data in graph.edges(nbunch=[current], data=True):
            other = v if u == current else u
            if other not in visited_nodes:
                dfs(other, visited_nodes + [current], visited_rels + [data["relation"]], depth + 1)

    for node in graph.nodes:
        if len(paths) >= max_samples:
            break
        dfs(node, [], [], 0)

    return paths


def graph_n_hop_search(graph: nx.MultiDiGraph, entity_a: str, hops: int) -> set[str]:
    """Return all entities reachable from entity_a within `hops` steps
    (cumulative across all hop depths up to `hops`, not just the final
    BFS layer - a node reachable via a path shorter than `hops` still
    counts, since a specific sampled DFS path's length can differ from
    the true shortest-path distance to the same node).
    """
    frontier = {entity_a}
    visited = {entity_a}
    for _ in range(hops):
        next_frontier = set()
        for node in frontier:
            for u, v, _ in graph.edges(nbunch=[node], data=True):
                other = v if u == node else u
                if other not in visited:
                    next_frontier.add(other)
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



def _chain_phrase(start: str, relations: list[str]) -> str | None:
    """Build a step-by-step, direction-verified question from a chain
    of relations - NOT nested possessives ("the enemy of the companion
    of X"), which reproduces the single-hop direction bug, compounded
    once per hop (confirmed on real corpus data - see Week 7 findings).

    Each step reuses relation_to_question() directly - the first hop
    with the real start entity as subject, every subsequent hop with
    "that entity" as a placeholder subject referring to the previous
    step's (unknown) answer. Correctness by construction: every
    individual step is independently verified, nothing new is derived
    by chaining.

    Returns:
        A multi-sentence question string, or None if ANY relation in
        the chain lacks a verified template - one unverified hop
        anywhere invalidates the whole chain's ground truth.
    """
    steps = []
    subject = start
    for i, rel in enumerate(relations):
        question = relation_to_question(subject, rel)
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
        phrase = _chain_phrase(path_info["start"], path_info["relations"])
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
