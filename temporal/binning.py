# temporal/binning.py
"""Narrative-position binning, based on the percent-of-book method from
Christou & Tsoumakas, "Relational Arcs as Narrative Structure" (2025).

Chunks are assigned to one of N narrative bins based on their position
within the book (not real-world time — ARF has no calendar dates, only
narrative/textual order via chunk_id; see Week 1 findings).
"""

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class BinningConfig:
    """Bin-count bounds for adaptive narrative binning."""

    min_bins: int = 6
    max_bins: int = 20
    relations_per_bin: int = 15


def compute_num_bins(total_relations: int, config: BinningConfig = BinningConfig()) -> int:
    """Compute the adaptive number of narrative bins for a book.

    Sparse books (few relations) get fewer, wider bins so each bin still
    contains enough events to be meaningful; dense books get up to
    max_bins for finer resolution.

    Args:
        total_relations: Total relation instances in the book.
        config: Bounds controlling the adaptive formula.

    Returns:
        Number of bins, clamped to [config.min_bins, config.max_bins].
    """
    raw = total_relations / config.relations_per_bin
    return int(min(config.max_bins, max(config.min_bins, raw)))


def assign_narrative_bin(chunk_id: int, min_chunk_id: int, max_chunk_id: int, num_bins: int) -> int:
    """Assign a chunk to a narrative-position bin (1-indexed).

    Args:
        chunk_id: The chunk's position identifier within its book.
        min_chunk_id: The book's minimum chunk_id (start of narrative).
        max_chunk_id: The book's maximum chunk_id (end of narrative).
        num_bins: Total number of bins for this book (see compute_num_bins).

    Returns:
        The 1-indexed bin number this chunk falls into.
    """
    total_span = max_chunk_id - min_chunk_id + 1
    position = chunk_id - min_chunk_id
    bin_index = math.floor(position * num_bins / total_span) + 1
    return min(bin_index, num_bins)  # guard against off-by-one at the final chunk