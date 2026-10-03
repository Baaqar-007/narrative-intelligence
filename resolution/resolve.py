# resolution/resolve.py
"""Stage orchestration for Week 8's resolution stages, run in the
decided order: Stage 0 (pronoun/generic filter) before Stage A
(surface-variant merge).

NOT a standalone pipeline - meant to be called FROM
scripts/build_pipeline.py (the real end-to-end build), the same way
build_pipeline.py already calls load_data.py. Named resolve.py rather
than pipeline.py specifically to avoid implying a second, parallel
pipeline alongside the real one.
"""

from dataclasses import dataclass

import networkx as nx

from resolution.pronoun_filter import (
    ResolutionEntry,
    ResolutionTier,
    build_resolution_map as build_pronoun_generic_map,
    is_pronoun_generic,
)
from resolution.surface_variant_merge import build_surface_variant_map

# Leading function words / articles / pronouns - is_pronoun_generic
# checks only the FINAL token, so a leading "the"/"a" on an otherwise
# real-looking name needs a separate check here.
_LEADING_FUNCTION_WORDS: frozenset[str] = frozenset({
    "he", "she", "her", "his", "him", "you", "your", "my", "me", "i", "we",
    "our", "us", "they", "them", "their", "it", "its", "the", "a", "an",
    "this", "that", "these", "those", "some", "little", "young", "old",
})

# Social-role/title descriptors - not kinship/pronoun patterns
# (deliberately kept separate from pronoun_filter.py - a different
# category, not validated at that module's level).
_SOCIAL_ROLE_GENERIC: frozenset[str] = frozenset({
    "party", "people", "man", "woman", "boy", "girl", "lady", "gentlewoman",
})


def is_nameable(entity: str) -> bool:
    """Heuristic only: could a real query plausibly contain this
    string as a reference to one specific character? Single canonical
    copy - previously duplicated with an independently-maintained,
    drifted-out-of-sync set in diagnostic scripts; import from here."""
    tokens = entity.split()
    if not (1 <= len(tokens) <= 4):
        return False
    if tokens[0].lower() in _LEADING_FUNCTION_WORDS:
        return False
    if is_pronoun_generic(entity):
        return False
    if entity.lower() in _SOCIAL_ROLE_GENERIC:
        return False
    return True


def build_full_resolution_map(graph: nx.MultiDiGraph) -> dict[str, ResolutionEntry]:
    """Run Stage 0 then Stage A, in that order, for one book's graph.
    Non-destructive: never modifies `graph`. The two stages' outputs
    are guaranteed non-overlapping by construction (Stage A excludes
    Stage 0's flagged nodes from candidacy), so a plain dict merge is
    safe."""
    pronoun_map = build_pronoun_generic_map(graph)
    surface_map = build_surface_variant_map(graph, pronoun_generic_map=pronoun_map)
    return {**pronoun_map, **surface_map}


@dataclass(frozen=True)
class ResolutionSummary:
    total_nodes: int
    pronoun_generic: int
    surface_variant: int
    ambiguous_variant_candidate: int
    unresolved: int


def summarize(graph: nx.MultiDiGraph, resolution_map: dict[str, ResolutionEntry]) -> ResolutionSummary:
    counts = {tier: 0 for tier in ResolutionTier}
    for entry in resolution_map.values():
        counts[entry.tier] += 1
    total = graph.number_of_nodes()
    return ResolutionSummary(
        total_nodes=total,
        pronoun_generic=counts[ResolutionTier.EXCLUDED_PRONOUN_GENERIC],
        surface_variant=counts[ResolutionTier.SURFACE_VARIANT],
        ambiguous_variant_candidate=counts[ResolutionTier.AMBIGUOUS_VARIANT_CANDIDATE],
        unresolved=total - len(resolution_map),
    )