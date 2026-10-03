# resolution/pronoun_filter.py
"""Stage 0 of entity resolution (Week 8): mechanical pre-filter for
bare-pronoun and generic-noun strings stored as if they were
canonical entity names (e.g. "her son", "mother", "his", "the child").

WHY THIS RUNS FIRST, ahead of Stage A (surface-variant merging): a
corpus-wide audit found 58% of confirmed functional-step entity
fragmentation is this pronoun/generic pattern, vs 9% for surface-name
variants. A pronoun string must also never become a Stage A merge
candidate - "her son" is not an alias of a real name, it's a failure
to resolve one. Non-destructive throughout: never mutates the graph.
"""

from dataclasses import dataclass
from enum import Enum

import networkx as nx


class ResolutionTier(str, Enum):
    """Confidence tier for a resolution_map entry. Defined once here
    (not duplicated per stage) since Stage A's entries share this
    enum - avoids two independently-maintained tier definitions
    drifting apart."""

    EXCLUDED_PRONOUN_GENERIC = "excluded_pronoun_generic"
    SURFACE_VARIANT = "surface_variant"
    AMBIGUOUS_VARIANT_CANDIDATE = "ambiguous_variant_candidate"


@dataclass(frozen=True)
class ResolutionEntry:
    raw_name: str
    tier: ResolutionTier
    reason: str
    canonical_form: str | None = None  # populated only for SURFACE_VARIANT


# Hand-seeded, NOT exhaustive. Sourced from real findings across this
# project: bare pronouns ("her", "you"), and the Harold-cluster
# diagnostics ("her son", "my son", "mother", "her own son"). Extend
# only from a real, observed miss.
PRONOUN_GENERIC_LAST_TOKEN: frozenset[str] = frozenset({
    "he", "she", "her", "his", "him", "you", "your", "yours",
    "me", "my", "mine", "i", "we", "our", "ours", "us",
    "they", "them", "their", "theirs", "it", "its",
    "mother", "father", "son", "daughter", "husband", "wife",
    "brother", "sister", "child", "baby", "parent",
    # In PRONOUN_GENERIC_LAST_TOKEN (resolution/pronoun_filter.py):
    # add "mamma", "papa" (and informal variants, found via book 3322,
    # East Lynne-era Victorian domestic fiction - not yet confirmed
    # elsewhere, extend further only on a real future miss)
    "mamma", "mama", "mom", "papa", "dad", "daddy",
})

# Irregular/archaic plural or spelling forms found in real corpus data
# - "sonne" (archaic singular spelling, this project's Decameron
# translation), "children" (irregular plural, not caught by a
# trailing-"s" strip).
_IRREGULAR_FORMS: frozenset[str] = frozenset({"children", "sonne", "sonnes"})

# Archaic second-person pronouns and verb forms found in real corpus
# data (Decameron/Rhinegold - period or translated texts) - the base
# list was seeded from modern-English examples and missed these.
_ARCHAIC_FORMS: frozenset[str] = frozenset({
    "thee", "thou", "thy", "thine", "ye", "hath", "doth",
})


def is_pronoun_generic(entity: str) -> bool:
    """True if `entity`'s final token matches a known bare-pronoun or
    generic-noun pattern (singular, plural, or archaic form).

    Matches on the LAST token so "her son" / "his mother" / "your
    daughter" are all caught by one check. Regular plurals are caught
    by stripping a single trailing "s" and re-checking against the
    base list; irregular/archaic forms are listed explicitly.

    Known, accepted false-positive risk: a real character literally
    named with one of these words (e.g. "Son") would be wrongly
    flagged. Not observed in this corpus.
    """
    tokens = entity.strip().lower().split()
    if not tokens:
        return False
    last = tokens[-1]
    if last in PRONOUN_GENERIC_LAST_TOKEN or last in _IRREGULAR_FORMS or last in _ARCHAIC_FORMS:
        return True
    return last.endswith("s") and last[:-1] in PRONOUN_GENERIC_LAST_TOKEN


def build_resolution_map(graph: nx.MultiDiGraph) -> dict[str, ResolutionEntry]:
    """Scan every node in `graph`, return ResolutionEntry for nodes
    matching is_pronoun_generic(). Does NOT modify `graph`. A node
    absent from the result is not flagged by THIS stage - it may
    still be flagged by Stage A."""
    return {
        node: ResolutionEntry(
            raw_name=node,
            tier=ResolutionTier.EXCLUDED_PRONOUN_GENERIC,
            reason=f"final token {node.strip().lower().split()[-1]!r} "
                   f"matches known pronoun/generic pattern",
        )
        for node in graph.nodes
        if is_pronoun_generic(node)
    }


def is_excluded_from_composition(
    entity: str, resolution_map: dict[str, ResolutionEntry]
) -> bool:
    """Whether multi-hop graph composition should refuse to continue
    THROUGH `entity` as an intermediate node. Covers BOTH tiers whose
    identity is genuinely unknown (pronoun/generic, and ambiguous
    surface-variant candidates matching 2+ distinct longer names) -
    SURFACE_VARIANT entries have a KNOWN identity and should be
    redirected via resolve_canonical() instead, not excluded.

    Single-hop retrieval is NOT affected - a raw fact stays fully
    retrievable on its own. This check exists only for traversal/
    composition logic deciding whether to extend a chain through this
    node. Not yet wired into graph.traversal / retrieval.hybrid_search
    - that integration is a separate, deliberate follow-up.
    """
    entry = resolution_map.get(entity)
    return entry is not None and entry.tier in (
        ResolutionTier.EXCLUDED_PRONOUN_GENERIC,
        ResolutionTier.AMBIGUOUS_VARIANT_CANDIDATE,
    )


def resolve_canonical(entity: str, resolution_map: dict[str, ResolutionEntry]) -> str:
    """Map a known surface-variant string to its canonical form.
    Returns `entity` unchanged if it's not a SURFACE_VARIANT entry
    (including pronoun/generic and ambiguous entries, which have no
    canonical form - use is_excluded_from_composition for those)."""
    entry = resolution_map.get(entity)
    if entry is not None and entry.tier == ResolutionTier.SURFACE_VARIANT and entry.canonical_form:
        return entry.canonical_form
    return entity