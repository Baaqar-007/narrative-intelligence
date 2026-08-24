"""Loads and cleans the raw ARF dataset.

Extracted from notebook exploration (Week 1, Day 1) into a reusable
module - this logic previously only existed as notebook cells, which
is why it had to be re-run by hand every session. See
notebooks/explore_arf_dataset.ipynb for the original investigation
that produced these specific cleaning rules (malformed row detection,
etc.).
"""

import ast

import pandas as pd
from datasets import load_dataset


def safe_parse_relations(raw: object) -> list | None:
    """Parse a stringified relations list from the raw ARF dataset.

    Returns [] for genuinely empty relations, a list of dicts for valid
    data, or None if the string is malformed (can't be parsed at all).
    ARF's `relations` column is a Python-literal string, not JSON.

    Args:
        raw: The raw value of a 'relations' cell.

    Returns:
        Parsed list of relation dicts, or None if unparseable.
    """
    if not isinstance(raw, str):
        return None
    try:
        return ast.literal_eval(raw)
    except (ValueError, SyntaxError):
        return None


def load_and_clean_arf() -> pd.DataFrame:
    """Load the ARF dataset and produce a cleaned, ready-to-use dataframe.

    Filters the single known malformed row (see Week 1 Day 1 findings)
    and adds a `relations_parsed` column with `safe_parse_relations`
    already applied.

    Returns:
        A dataframe with all original ARF columns plus `relations_parsed`,
        malformed rows removed.
    """
    dataset = load_dataset("Despina/project_gutenberg", "synthetic_relations_in_fiction_books")
    df = dataset["train"].to_pandas()

    df["relations_parsed"] = df["relations"].apply(safe_parse_relations)
    valid = df[df["relations_parsed"].notnull()].copy()

    return valid
