# tests/test_binning.py
"""Tests for temporal.binning."""

from temporal.binning import BinningConfig, assign_narrative_bin, compute_num_bins


def test_compute_num_bins_clamps_to_max() -> None:
    """Dense books (many relations) should cap at max_bins."""
    assert compute_num_bins(total_relations=1280) == 20


def test_compute_num_bins_clamps_to_min() -> None:
    """Sparse books (few relations) should floor at min_bins."""
    assert compute_num_bins(total_relations=10) == 6


def test_compute_num_bins_scales_in_between() -> None:
    config = BinningConfig()
    # 150 relations / 15 per bin = 10 bins, within [6, 20]
    assert compute_num_bins(total_relations=150, config=config) == 10


def test_assign_bin_matches_book_106_manual_calculation() -> None:
    """Cross-checked by hand against the paper's original formula."""
    assert assign_narrative_bin(chunk_id=100, min_chunk_id=0, max_chunk_id=882, num_bins=20) == 3


def test_assign_bin_respects_min_chunk_id_offset() -> None:
    """A chunk near a book's true narrative start should land in an early
    bin, even if min_chunk_id isn't 0 (e.g. due to ARF's per-book chunk
    subsampling). This is a deliberate deviation from the published
    formula, which assumes chunk_id starts at 0 (see module docstring).
    """
    assert assign_narrative_bin(chunk_id=105, min_chunk_id=100, max_chunk_id=982, num_bins=20) == 1


def test_last_chunk_lands_in_final_bin_not_overflow() -> None:
    """Guard against floor() pushing the very last chunk past num_bins."""
    assert assign_narrative_bin(chunk_id=882, min_chunk_id=0, max_chunk_id=882, num_bins=20) == 20