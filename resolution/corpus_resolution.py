# resolution/corpus_resolution.py
"""Runs resolve.build_full_resolution_map() across every book in a
corpus dict (as produced by graph.corpus.build_corpus_graphs). One
resolution_map per book_id, persisted as a SEPARATE artifact from
corpus.pkl - resolution_map is derived FROM the graph, but the graph
itself stays untouched (non-destructive, per the Week 4 architecture).
"""

import pickle
from pathlib import Path

import networkx as nx

from resolution.pronoun_filter import ResolutionEntry
from resolution.resolve import build_full_resolution_map


def build_corpus_resolution_maps(
    corpus: dict[str, nx.MultiDiGraph],
) -> dict[str, dict[str, ResolutionEntry]]:
    """book_id -> (raw_node_name -> ResolutionEntry), for every book
    in `corpus`. Does not modify any graph in `corpus`."""
    return {
        book_id: build_full_resolution_map(graph)
        for book_id, graph in corpus.items()
    }


def save_corpus_resolution(
    resolution_maps: dict[str, dict[str, ResolutionEntry]], path: Path,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as f:
        pickle.dump(resolution_maps, f)


def load_corpus_resolution(path: Path) -> dict[str, dict[str, ResolutionEntry]]:
    with open(path, "rb") as f:
        return pickle.load(f)