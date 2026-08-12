# graph/corpus.py
"""Multi-book graph corpus assembly and persistence.

Builds one graph per book across the full ARF dataset and provides
pickle-based save/load so downstream retrieval work doesn't need to
rebuild from raw data every run.
"""

import pickle
from pathlib import Path

import networkx as nx
import pandas as pd

from graph.build_graph import GraphBuildStats, build_book_graph


def build_corpus_graphs(df: pd.DataFrame) -> dict[str, nx.MultiDiGraph]:
    """Build one graph per book_id present in the dataframe.

    Args:
        df: Parsed ARF dataframe with 'book_id' and 'relations_parsed'
            columns (see notebooks/explore_arf_dataset.ipynb).

    Returns:
        A dict mapping book_id -> that book's MultiDiGraph.
    """
    graphs: dict[str, nx.MultiDiGraph] = {}

    for book_id, book_rows in df.groupby("book_id"):
        graph, stats = build_book_graph(book_rows, book_id=book_id)
        _log_build(stats)
        graphs[book_id] = graph

    return graphs


def _log_build(stats: GraphBuildStats) -> None:
    """Print a one-line summary per book, so a 96-book build is inspectable."""
    print(
        f"book={stats.book_id:>8}  "
        f"chunks={stats.num_chunks_processed:>5}  "
        f"nodes={stats.num_nodes:>4}  "
        f"edges={stats.num_edges:>5}"
    )


def save_corpus(graphs: dict[str, nx.MultiDiGraph], path: str | Path) -> None:
    """Persist the full corpus of graphs to a single pickle file.

    Args:
        graphs: Output of build_corpus_graphs().
        path: Destination file path, e.g. "data/graphs/corpus.pkl".
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as f:
        pickle.dump(graphs, f)


def load_corpus(path: str | Path) -> dict[str, nx.MultiDiGraph]:
    """Load a previously saved corpus of graphs.

    Args:
        path: Path to a pickle file written by save_corpus().

    Returns:
        The dict of book_id -> MultiDiGraph.
    """
    with open(path, "rb") as f:
        return pickle.load(f)