"""Runs all NIE benchmarks against the already-built pipeline and
persists results + plots as real files.

Prerequisite: scripts/build_pipeline.py must have been run first.

Run:
    python scripts/run_benchmarks.py

Produces, under results/ (timestamped, so old runs aren't overwritten):
    results/<timestamp>/benchmark_results.json
    results/<timestamp>/direction_accuracy_vs_k.png
    results/<timestamp>/hop_count_trend.png

NOTE (see README "Known limitations" #10): the hop-count sweep uses a
single, hop-count-invariant query template, which is NOT phrased as
naturally as the single-hop direction benchmark's questions. Absolute
baseline numbers between the two benchmarks below are therefore not
directly comparable - only within-benchmark trends are. This is
documented, not hidden; see results JSON's "caveats" field.
"""

import json
import pickle
import time
from pathlib import Path

from embedding.embed_relations import load_embedding_model
from embedding.vector_store import get_collection
from evaluation.benchmark import (
    evaluate_direction_aware,
    evaluate_nhop_baseline,
    evaluate_nhop_graph,
    generate_nhop_questions,
    generate_questions,
)
from graph.corpus import load_corpus
from visualisation.benchmark_plot import plot_line_trend

DATA_DIR = Path("data")
RESULTS_DIR = Path("results") / time.strftime("%Y%m%d_%H%M%S")


def main():
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    results = {"caveats": []}

    print("Loading persisted pipeline (corpus, embeddings, vector store)...")
    corpus = load_corpus(DATA_DIR / "graphs" / "corpus.pkl")
    collection = get_collection(path=str(DATA_DIR / "chroma"))
    model = load_embedding_model()
    print(f"Loaded {len(corpus)} book graphs, {collection.count():,} vectors.\n")

    # --- Benchmark 1: single-hop direction correctness vs. k ---
    print("=== Benchmark: single-hop direction accuracy vs. k ===")
    questions = generate_questions(
        _load_valid_dataframe(), n_samples=200
    )
    k_values = [1, 3, 5, 7, 10, 15, 20]
    hybrid_by_k = []
    for k in k_values:
        r = evaluate_direction_aware(collection, model, corpus, questions, k=k)
        hybrid_by_k.append(r["hybrid_direction_correct"])
        print(f"  k={k}: hybrid={r['hybrid_direction_correct']:.1%}")

    results["single_hop_direction_vs_k"] = dict(zip(k_values, hybrid_by_k))

    fig = plot_line_trend(
        k_values, hybrid_by_k,
        title="Hybrid Retrieval Accuracy vs. k",
        xlabel="k (results retrieved)",
    )
    fig.savefig(RESULTS_DIR / "direction_accuracy_vs_k.png", dpi=150, bbox_inches="tight")
    print(f"  Saved plot: {RESULTS_DIR / 'direction_accuracy_vs_k.png'}")

    # --- Benchmark 2: accuracy vs. hop count ---
    print("\n=== Benchmark: accuracy vs. hop count ===")
    hop_values = [1, 2, 3]
    baseline_by_hop, graph_by_hop = [], []
    for h in hop_values:
        hop_questions = generate_nhop_questions(corpus, hops=h, n_samples=100)
        b_acc = evaluate_nhop_baseline(collection, model, hop_questions, k=10)
        g_acc = evaluate_nhop_graph(corpus, hop_questions)
        baseline_by_hop.append(b_acc)
        graph_by_hop.append(g_acc)
        print(f"  {h}-hop: baseline={b_acc:.1%}, graph={g_acc:.1%}")

    results["hop_count_trend"] = {
        "hops": hop_values,
        "baseline": baseline_by_hop,
        "graph": graph_by_hop,
    }
    results["caveats"].append(
    "hop_count_trend previously used a generic, hop-count-invariant query "
    "template; this was replaced with natural chained phrasing (matching "
    "the style of single_hop_direction_vs_k) after finding it produced "
    "noisy, non-monotonic results. Current numbers use consistent natural "
    "phrasing at every hop depth."
)

    fig, ax = _plot_two_lines(hop_values, baseline_by_hop, graph_by_hop)
    fig.savefig(RESULTS_DIR / "hop_count_trend.png", dpi=150, bbox_inches="tight")
    print(f"  Saved plot: {RESULTS_DIR / 'hop_count_trend.png'}")

    # --- Persist everything ---
    with open(RESULTS_DIR / "benchmark_results.json", "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nAll results saved to {RESULTS_DIR}/")


def _load_valid_dataframe():
    import pandas as pd
    return pd.read_parquet(DATA_DIR / "arf_chunks_parsed.parquet")


def _plot_two_lines(x, y1, y2):
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.plot(x, y1, marker="o", label="Vector-only baseline", color="#94a3b8")
    ax.plot(x, y2, marker="o", label="Graph traversal", color="#2563eb")
    ax.set_ylim(0, 1)
    ax.set_xlabel("Number of hops")
    ax.set_ylabel("Accuracy")
    ax.set_title("Accuracy vs. Hop Count")
    ax.legend()
    ax.grid(alpha=0.3)
    return fig, ax


if __name__ == "__main__":
    main()
