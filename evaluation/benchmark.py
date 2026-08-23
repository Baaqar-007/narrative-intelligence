# evaluation/benchmark.py
"""Benchmark: hybrid retrieval vs. vector-only baseline, using ARF's
ground-truth relations to auto-generate evaluation questions.

Methodology: for each sampled relation instance (entity1, relation,
entity2), generate the question "Who/what is <relation> of <entity1>?"
with entity2 as the known correct answer. Query both systems and check
whether the correct answer is surfaced.

Metrics:
- baseline_top1: does the #1 vector search hit mention the correct
  answer (as either entity1 or entity2)?
- baseline_topk: does the correct answer appear anywhere in the top-k
  vector hits?
- hybrid_topk: does the correct answer appear anywhere among the
  entities in the enriched relationship lists for the top-k hits?
  (Tests hybrid's actual value-add: graph enrichment surfacing facts
  vector similarity alone ranked lower or missed.)
"""

import random
from dataclasses import dataclass
import networkx as nx

import pandas as pd

from graph.canonicalization import normalize_entity_name
from graph.relation_ontology import is_canonical_relation
from retrieval.hybrid_search import hybrid_search
from embedding.vector_store import query_relations


@dataclass
class BenchmarkQuestion:
    """One auto-generated evaluation question with a known-correct answer."""

    query: str
    book_id: str
    correct_answer: str  # canonicalized entity name
    source_relation: str


def generate_questions(df: pd.DataFrame, n_samples: int = 200, seed: int = 42) -> list[BenchmarkQuestion]:
    rng = random.Random(seed)

    candidates = []
    for _, row in df.iterrows():
        for r in row["relations_parsed"]:
            if is_canonical_relation(r["relation"]):
                candidates.append((row["book_id"], r))

    sampled = rng.sample(candidates, min(n_samples, len(candidates)))

    questions = []
    for book_id, r in sampled:
        readable_relation = r["relation"].replace("_", " ")
        if readable_relation.endswith(" of"):
            query = f"Who is {readable_relation} {r['entity1']}?"
        else:
            query = f"Who is the {readable_relation} of {r['entity1']}?"
        questions.append(BenchmarkQuestion(
            query=query,
            book_id=book_id,
            correct_answer=normalize_entity_name(r["entity2"]),
            source_relation=r["relation"],
        ))

    return questions


def _entities_in_metadata(meta: dict) -> set[str]:
    return {meta["entity1"], meta["entity2"]}


def evaluate_baseline(collection, model, questions: list[BenchmarkQuestion], k: int = 5) -> dict:
    """Evaluate vector-search-only retrieval (no graph enrichment)."""
    top1_correct = 0
    topk_correct = 0

    for q in questions:
        result = query_relations(collection, q.query, model, n_results=k, book_id=q.book_id)
        metadatas = result["metadatas"][0]

        if not metadatas:
            continue

        if q.correct_answer in _entities_in_metadata(metadatas[0]):
            top1_correct += 1

        all_entities = set()
        for meta in metadatas:
            all_entities |= _entities_in_metadata(meta)
        if q.correct_answer in all_entities:
            topk_correct += 1

    n = len(questions)
    return {
        "n_questions": n,
        "top1_precision": top1_correct / n,
        "topk_precision": topk_correct / n,
    }


def evaluate_hybrid(collection, model, corpus: dict, questions: list[BenchmarkQuestion], k: int = 5) -> dict:
    """Evaluate hybrid retrieval (vector search + graph enrichment)."""
    topk_correct = 0

    for q in questions:
        hits = hybrid_search(collection, q.query, model, corpus, n_results=k, book_id=q.book_id)

        all_entities = set()
        for hit in hits:
            all_entities.add(hit.entity1)
            all_entities.add(hit.entity2)
            for r in hit.all_relationships:
                all_entities.add(r["entity1"])
                all_entities.add(r["entity2"])

        if q.correct_answer in all_entities:
            topk_correct += 1

    n = len(questions)
    return {
        "n_questions": n,
        "topk_precision": topk_correct / n,
    }
    
def evaluate_direction_aware(collection, model, corpus: dict, questions: list[BenchmarkQuestion], k: int = 5) -> dict:
    """Checks whether the CORRECTLY-DIRECTED fact is found, not just
    whether the right name appears anywhere. This is the metric that
    actually tests hybrid's value-add (see Week 3 Day 4/5 findings -
    topk_precision alone couldn't detect direction correctness).
    """
    baseline_correct = 0
    hybrid_correct = 0

    for q in questions:
        # Baseline: does the #1 vector hit state the fact in the right direction?
        result = query_relations(collection, q.query, model, n_results=1, book_id=q.book_id)
        if result["metadatas"][0]:
            meta = result["metadatas"][0][0]
            if meta["relation"] == q.source_relation and meta["entity2"] == q.correct_answer:
                baseline_correct += 1

        # Hybrid: among ALL enriched relationships, does the correctly-directed
        # fact (same relation type, same direction) exist anywhere?
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
    

# add to evaluation/benchmark.py

def find_two_hop_paths(graph: nx.MultiDiGraph, max_samples: int = 500) -> list[tuple]:
    """Find real 2-hop paths A -> B -> C in a graph, for multi-hop
    benchmark question generation.

    Returns:
        List of (a, rel1, b, rel2, c) tuples, distinct a/b/c only.
    """
    paths = []
    for a, b, data1 in graph.edges(data=True):
        for _, c, data2 in graph.edges(b, data=True):
            if c != a and c != b:
                paths.append((a, data1["relation"], b, data2["relation"], c))
            if len(paths) >= max_samples:
                return paths
    return paths


@dataclass
class MultiHopQuestion:
    query: str
    book_id: str
    entity_a: str
    entity_b: str  # the intermediate hop - NOT given in the query
    correct_answer: str  # entity_c
    rel1: str
    rel2: str


def generate_multihop_questions(corpus: dict[str, nx.MultiDiGraph], n_samples: int = 100, seed: int = 42) -> list[MultiHopQuestion]:
    rng = random.Random(seed)
    candidates = []

    for book_id, graph in corpus.items():
        for a, rel1, b, rel2, c in find_two_hop_paths(graph, max_samples=50):
            candidates.append((book_id, a, rel1, b, rel2, c))

    sampled = rng.sample(candidates, min(n_samples, len(candidates)))

    questions = []
    for book_id, a, rel1, b, rel2, c in sampled:
        r1 = rel1.replace("_", " ")
        r2 = rel2.replace("_", " ")
        query = f"Starting from {a}, who is {r2} the entity that is {r1} {a}?"
        questions.append(MultiHopQuestion(
            query=query, book_id=book_id, entity_a=a, entity_b=b,
            correct_answer=c, rel1=rel1, rel2=rel2,
        ))
    return questions

def evaluate_multihop_baseline(collection, model, questions: list[MultiHopQuestion], k: int = 10) -> float:
    """Single vector query per question - structurally cannot chain
    two facts, since no embedded sentence states a 2-hop relationship.
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

def graph_multihop_search(graph: nx.MultiDiGraph, entity_a: str) -> set[str]:
    """Real 2-hop BFS from entity_a - the capability vector search
    structurally cannot replicate in one query.
    """
    one_hop = set()
    for u, v, _ in graph.edges(nbunch=[entity_a], data=True):
        one_hop.add(v if u == entity_a else u)

    two_hop = set()
    for mid in one_hop:
        for u, v, _ in graph.edges(nbunch=[mid], data=True):
            two_hop.add(v if u == mid else u)

    return two_hop - {entity_a} - one_hop

def graph_n_hop_search(graph: nx.MultiDiGraph, entity_a: str, hops: int) -> set[str]:
    """Return all entities reachable from entity_a within `hops` steps
    (cumulative across all hop depths up to `hops`, not just the final
    layer - a node reachable via a shorter path than `hops` still
    counts, since shortest-path distance can differ from a specific
    sampled DFS path's length. See Week 3 findings.
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


def evaluate_multihop_graph(corpus: dict, questions: list[MultiHopQuestion]) -> float:
    correct = 0
    for q in questions:
        graph = corpus.get(q.book_id)
        if graph is None:
            continue
        two_hop_entities = graph_multihop_search(graph, q.entity_a)
        if q.correct_answer in two_hop_entities:
            correct += 1
    return correct / len(questions)

# add to evaluation/benchmark.py

def find_n_hop_paths(graph: nx.MultiDiGraph, hops: int, max_samples: int = 500) -> list[dict]:
    """Find real n-hop paths in a graph via DFS, for multi-hop question
    generation at arbitrary hop depth.

    Returns:
        List of dicts: {'start': entity, 'end': entity, 'path': [nodes]}.
        All nodes in a path are distinct (no revisits).
    """
    paths = []

    def dfs(current: str, visited: list[str], depth: int):
        if depth == hops:
            paths.append({"start": visited[0], "end": current, "path": list(visited) + [current]})
            return
        if len(paths) >= max_samples:
            return
        for u, v, _ in graph.edges(nbunch=[current], data=True):
            other = v if u == current else u
            if other not in visited:
                dfs(other, visited + [current], depth + 1)

    for node in graph.nodes:
        if len(paths) >= max_samples:
            break
        dfs(node, [], 0)

    return paths


def evaluate_graph_hop_accuracy(corpus: dict, hops: int, n_samples: int = 100, seed: int = 42) -> float:
    """For a given hop count, sample real n-hop paths and check whether
    graph_n_hop_search correctly finds the true endpoint from the start.
    """
    rng = random.Random(seed)
    candidates = []

    for book_id, graph in corpus.items():
        for path_info in find_n_hop_paths(graph, hops, max_samples=20):
            candidates.append((book_id, path_info["start"], path_info["end"]))

    if not candidates:
        return None

    sampled = rng.sample(candidates, min(n_samples, len(candidates)))

    correct = 0
    for book_id, start, end in sampled:
        graph = corpus[book_id]
        reached = graph_n_hop_search(graph, start, hops)
        if end in reached:
            correct += 1

    return correct / len(sampled)


# add to evaluation/benchmark.py

@dataclass
class NHopQuestion:
    query: str
    book_id: str
    start_entity: str
    correct_answer: str
    hops: int


def generate_nhop_questions(corpus: dict[str, nx.MultiDiGraph], hops: int, n_samples: int = 100, seed: int = 42) -> list[NHopQuestion]:
    """Generate questions with a specific, single correct answer at a
    given hop depth, using real sampled paths (not the full reachable
    set - one specific true endpoint per question).
    """
    rng = random.Random(seed)
    candidates = []

    for book_id, graph in corpus.items():
        for path_info in find_n_hop_paths(graph, hops, max_samples=20):
            candidates.append((book_id, path_info["start"], path_info["end"], path_info["path"]))

    sampled = rng.sample(candidates, min(n_samples, len(candidates)))

    questions = []
    for book_id, start, end, path in sampled:
        query = f"Starting from {start} and following {hops} connected relationships in the story, who do we reach?"
        questions.append(NHopQuestion(query=query, book_id=book_id, start_entity=start, correct_answer=end, hops=hops))

    return questions


def evaluate_nhop_baseline(collection, model, questions: list[NHopQuestion], k: int = 10) -> float:
    """Vector-only: one query per question, checks if the correct
    answer entity appears anywhere in top-k results.
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