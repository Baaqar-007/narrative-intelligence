"""Runs all NIE benchmarks against the already-built pipeline and
persists results + plots as real files.

Prerequisite: scripts/build_pipeline.py must have been run first.

Run:
    python scripts/run_benchmarks.py

Produces, under results/ (timestamped, so old runs aren't overwritten):
    results/<timestamp>/benchmark_results.json
    results/<timestamp>/direction_accuracy_vs_k.png
    results/<timestamp>/hop_count_baseline.png

NOTE (see README "Known limitations" #10): the hop-count sweep uses
natural chained phrasing matching the single-hop benchmark's style
(this was itself a fix, replacing an earlier hop-count-invariant
template that produced noisy, non-monotonic results) - see the
"caveats" field in the results JSON.

WEEK 7 UPDATE: evaluate_nhop_graph() no longer exists - replaced by
validate_graph_reachability() in evaluation.benchmark, which answers a
different question (is our hand-rolled traversal correct, verified
independently against networkx) rather than a comparable accuracy
score. Consequences for this script:
  - hop_count_trend.png now plots ONLY the vector-only baseline -
    plotting the old "graph accuracy" line alongside it would imply a
    comparison that isn't real anymore (a sanity-check pass rate,
    expected near 1.0 by construction, is not an accuracy metric).
  - Reachability diagnostics are still recorded in the JSON (a
    meaningful bug signal if agreement_with_independent_check ever
    drops below 1.0 in some future run) but never plotted.
  - generate_questions()/generate_nhop_questions() now only sample
    relations with a verified question template (31/48 canonical
    types) - n_questions_valid vs. n_questions_requested is recorded
    per hop count to make that scope narrowing visible, not silent.
  - Historical numbers from before this update are void, not
    comparable to any fresh run - both traversal and question
    generation logic changed.
"""

import json
import time
from pathlib import Path

from embedding.embed_relations import load_embedding_model
from embedding.vector_store import get_collection
from evaluation.benchmark import (
    evaluate_direction_aware,
    evaluate_nhop_baseline,
    generate_nhop_questions,
    generate_questions,
    validate_graph_reachability,
)
from graph.corpus import load_corpus
from visualisation.benchmark_plot import plot_line_trend

DATA_DIR = Path("data")
RESULTS_DIR = Path("results") / time.strftime("%Y%m%d_%H%M%S")


def main():
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    results = {"caveats": []}
    results["caveats"].append(
        "hop_count_trend previously used a generic, hop-count-invariant "
        "query template; this was replaced with natural chained phrasing "
        "(matching the style of single_hop_direction_vs_k) after finding "
        "it produced noisy, non-monotonic results. Current numbers use "
        "consistent natural phrasing at every hop depth."
    )
    results["caveats"].append(
        "Week 7 update: evaluate_nhop_graph() was replaced with "
        "validate_graph_reachability() (see evaluation/benchmark.py "
        "module docstring for the full reasoning). It is a correctness "
        "sanity check, not a capability score - the old 'graph' accuracy "
        "field is gone, replaced by graph_reachability_check below, which "
        "is diagnostic-only and intentionally not plotted. Multi-hop "
        "traversal is now direction-agnostic for symmetric relation types "
        "(companion_of, friend_of, enemy_of, rival_of, sibling_of, "
        "spouse_of, relative_of); question generation is scoped to "
        "relation types with a verified direction template (31/48 "
        "canonical types). Numbers from before this update are void, not "
        "comparable to any prior run."
    )

    print("Loading persisted pipeline (corpus, embeddings, vector store)...")
    corpus = load_corpus(DATA_DIR / "graphs" / "corpus.pkl")
    collection = get_collection(path=str(DATA_DIR / "chroma"))
    model = load_embedding_model()
    print(f"Loaded {len(corpus)} book graphs, {collection.count():,} vectors.\n")

    # --- Benchmark 1: single-hop direction correctness vs. k ---
    print("=== Benchmark: single-hop direction accuracy vs. k ===")
    questions = generate_questions(_load_valid_dataframe(), n_samples=200)
    print(f"  {len(questions)} questions generated (31/48 templated relation types)")

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

    # --- Benchmark 2: baseline accuracy vs. hop count, + reachability
    #     sanity check (diagnostic only, not a comparable accuracy line) ---
    print("\n=== Benchmark: vector-only baseline accuracy vs. hop count ===")
    hop_values = [1, 2, 3]
    n_requested = 100
    baseline_by_hop = []
    reachability_by_hop = []

    for h in hop_values:
        hop_questions = generate_nhop_questions(corpus, hops=h, n_samples=n_requested)
        n_valid = len(hop_questions)

        b_acc = evaluate_nhop_baseline(collection, model, hop_questions, k=10)
        reach = validate_graph_reachability(corpus, hop_questions)

        baseline_by_hop.append(b_acc)
        reachability_by_hop.append({"hops": h, **reach})

        print(f"  {h}-hop: baseline={b_acc:.1%}  "
              f"(questions: {n_valid}/{n_requested} valid)")
        print(f"           reachability_check={reach}  <- diagnostic only, not an accuracy score")

    results["hop_count_trend"] = {
        "hops": hop_values,
        "baseline": baseline_by_hop,
        "n_questions_requested": n_requested,
        "n_questions_valid": [r["n_questions"] for r in reachability_by_hop],
    }
    results["graph_reachability_check"] = reachability_by_hop

    fig = plot_line_trend(
        hop_values, baseline_by_hop,
        title="Vector-only Baseline Accuracy vs. Hop Count",
        xlabel="Number of hops",
    )
    fig.savefig(RESULTS_DIR / "hop_count_baseline.png", dpi=150, bbox_inches="tight")
    print(f"  Saved plot: {RESULTS_DIR / 'hop_count_baseline.png'}")

    # --- Persist everything ---
    with open(RESULTS_DIR / "benchmark_results.json", "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nAll results saved to {RESULTS_DIR}/")


def _load_valid_dataframe():
    import pandas as pd
    return pd.read_parquet(DATA_DIR / "arf_chunks_parsed.parquet")


if __name__ == "__main__":
    main()
