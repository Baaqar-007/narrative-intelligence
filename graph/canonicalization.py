# graph/canonicalization.py
"""Entity name canonicalization for ARF dataset relations.

Normalizes raw entity name strings into a consistent form usable as a
graph node identifier. Scope is intentionally narrow (see module-level
limitations below) — this is a Week 1, Day 2 deliverable, not a full
alias-resolution system.
"""

import re

# Matches a trailing appositive descriptor, e.g. ", the gorilla"
_APPOSITIVE_PATTERN = re.compile(r",\s*the\s+.+$")


def normalize_entity_name(name: str) -> str:
    """Normalize an entity name for use as a graph node identifier.

    Lowercases the name, strips surrounding whitespace, and removes a
    trailing appositive descriptor clause (e.g. "Bolgani, the gorilla"
    becomes "bolgani").

    Args:
        name: Raw entity name string as extracted from the ARF dataset.

    Returns:
        The normalized entity name.

    Known limitations:
        - Does not resolve generic/collective entities to a canonical
          form (e.g. "apes" and "the apes" remain distinct).
        - Does not perform cross-alias resolution for nicknames,
          titles, or honorifics (e.g. "Tarzan" vs "Lord Greystoke").
        - These are tracked as open issues, not silently handled.
    """
    normalized = name.strip().lower()
    normalized = _APPOSITIVE_PATTERN.sub("", normalized)
    return normalized.strip()