# visualization/benchmark_plot.py
"""Plots for benchmark results comparing retrieval systems.

Kept deliberately minimal - two charts only, each answering one
specific comparison question from the Week 3 benchmark findings.
"""

import matplotlib.pyplot as plt


def plot_benchmark_comparison(
    labels: list[str],
    values: list[float],
    title: str,
    ylabel: str = "Accuracy",
) -> plt.Figure:
    """Bar chart comparing accuracy across systems/conditions.

    Args:
        labels: X-axis category labels (e.g. system names).
        values: Corresponding accuracy values (0-1 scale).
        title: Chart title.
        ylabel: Y-axis label.

    Returns:
        The matplotlib Figure.
    """
    fig, ax = plt.subplots(figsize=(6, 4))
    bars = ax.bar(labels, values, color=["#94a3b8", "#2563eb"])
    ax.set_ylim(0, 1)
    ax.set_ylabel(ylabel)
    ax.set_title(title)

    for bar, val in zip(bars, values):
        ax.text(bar.get_x() + bar.get_width() / 2, val + 0.02, f"{val:.1%}",
                ha="center", fontweight="bold")

    return fig

def plot_line_trend(x_values: list, y_values: list, title: str, xlabel: str, ylabel: str = "Accuracy") -> plt.Figure:
    """Line chart showing a metric trend across a swept parameter."""
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.plot(x_values, y_values, marker="o", color="#2563eb", linewidth=2)
    ax.set_ylim(0, 1)
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.grid(alpha=0.3)

    for x, y in zip(x_values, y_values):
        ax.annotate(f"{y:.0%}", (x, y), textcoords="offset points", xytext=(0, 8), ha="center")

    return fig