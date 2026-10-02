"""Stage A of entity resolution (Week 8): mechanical surface-variant
alias merging via honorific/article stripping + core-token overlap.
Runs AFTER Stage 0 (pronoun_filter.py) - a pronoun/generic node must
never become a merge candidate here.

SCOPE, deliberately narrow (Facet 1, Amalvy & Labatut; Week 1's own
prior finding): exact core-token overlap only, after stripping
honorifics/articles. Does NOT do fuzzy/edit-distance matching (Week 1
already tried difflib fuzzy matching and found it unreliable on short
strings - "Buto"/"Gunto" false positive) and does NOT resolve true
hard aliases with zero string overlap (Wotan/Wanderer, "the
king"/Tancrede - Stage C territory, not this module's job).

Design correction found BEFORE this module was written (day 6/7):
titles/honorifics must be stripped and excluded from comparison
entirely, not treated as identifying content. Module A's reporting-
only token_overlap heuristic flagged "mrs. holt"/"mrs. transome" as
variant-like purely on the shared honorific "mrs." - two different
people. A merge mechanism using raw tokens would have wrongly
clustered them. HONORIFICS_AND_ARTICLES includes noble titles (count,
king, queen...) specifically because stripping only "mr."/"mrs."
would leave "count" itself available as a false shared core token -
risking merging two unrelated title-holders across different stories
(the Decameron corpus here is ~100 novellas sharing one book_id, so
this risk is real, not hypothetical).

A bare title with an empty core-token set after stripping ("the
count", with no name) is excluded from candidacy - nothing to match
on. Structurally similar to Stage 0's pronoun/generic problem, a
different surface pattern; not folded into Stage 0, since only one
instance has been observed so far (not yet a measured, repeated
pattern).
"""

from collections import defaultdict
from typing import Callable

import networkx as nx
from enum import Enum

from resolution.pronoun_filter import ResolutionEntry, ResolutionTier

HONORIFICS_AND_ARTICLES: frozenset[str] = frozenset({
    "mr", "mr.", "mrs", "mrs.", "miss", "ms", "ms.", "dr", "dr.",
    "sir", "lady", "lord", "madam", "madame", "messer", "signior", "signor",
    "king", "queen", "prince", "princess", "count", "countess",
    "duke", "duchess", "the", "a", "an",
})

# Generational/age-distinguishing suffixes and modifiers - these are
# NOT variants of a shorter form, they're markers that TWO DIFFERENT
# people exist ("Jacob" vs "Jacob Jr.": the suffix exists specifically
# to distinguish them, not to add detail to one name). Token-overlap
# matching is adversarial here, not just insufficient - sharing fewer
# tokens with the modifier removed is NOT evidence of non-identity,
# it's near-certain evidence of identity with a DIFFERENT person. The
# existing "young"/"old" Morel false-merge (day 7) is a milder version
# of the same pattern. Hard block, not a candidacy filter - a pair
# differing only by one of these tokens must never merge, regardless
# of how many other tokens overlap.
DISTINGUISHING_SUFFIXES: frozenset[str] = frozenset({
    "jr", "jr.", "junior", "sr", "sr.", "senior",
    "ii", "iii", "iv", "elder", "younger",
    "young", "old",
})

def _differs_only_by_distinguishing_suffix(a: str, b: str) -> bool:
    a_tokens, b_tokens = set(a.lower().split()), set(b.lower().split())
    diff = a_tokens.symmetric_difference(b_tokens)
    return bool(diff) and diff <= DISTINGUISHING_SUFFIXES

def core_tokens(entity: str) -> frozenset[str]:
    """Identifying tokens only - honorifics/titles/articles stripped
    from anywhere in the string, not just the leading position
    ("the count" and "count d'angiers" both need "count" removed
    regardless of where it sits)."""
    return frozenset(
        t for t in entity.strip().lower().split()
        if t not in HONORIFICS_AND_ARTICLES
    )


def _is_variant_pair(a_tokens: frozenset[str], b_tokens: frozenset[str]) -> bool:
    """True only if the SMALLER token set is a (near-)subset of the
    larger - not just overlapping. "morel" subset-of "walter morel":
    yes. "transome" vs {"transome"} from an unrelated node: still
    risky on single-token names, so additionally require the smaller
    set be non-empty AND either an exact subset or share >=2 tokens
    (single shared token alone is the thing that caused the Decameron
    cross-story collisions and the Mrs. Holt/Mrs. Transome merge)."""
    if not a_tokens or not b_tokens:
        return False
    smaller, larger = (a_tokens, b_tokens) if len(a_tokens) <= len(b_tokens) else (b_tokens, a_tokens)
    shared = smaller & larger
    if not shared:
        return False
    if smaller <= larger:          # smaller is fully contained - "morel" in "walter morel"
        return True
    return len(shared) >= 2        # both multi-token, meaningful overlap, not just one coincidental token


class ResolutionTier(str, Enum):
    EXCLUDED_PRONOUN_GENERIC = "excluded_pronoun_generic"
    SURFACE_VARIANT = "surface_variant"
    AMBIGUOUS_VARIANT_CANDIDATE = "ambiguous_variant_candidate"  # new


def build_surface_variant_map(graph, pronoun_generic_map=None):
    """... same docstring intent, now also: a candidate matching MORE
    THAN ONE distinct longer string is flagged AMBIGUOUS_VARIANT_
    CANDIDATE rather than auto-merged to whichever sorts first. Found
    necessary via real data: "morel"/"mr. morel" matched both "walter
    morel" (a fuller name - correct) and "young mr. morel" (a
    distinguishing modifier, likely a different person - wrong), and
    length-based tie-breaking silently picked the wrong one. This
    project has no mechanical way to tell "fuller name" from
    "distinguishing modifier" apart - same shape as Week 1's
    appositive-vs-generic-collective distinction - so it declines
    rather than guesses, same discipline as pronoun_filter.py."""
    excluded = set(pronoun_generic_map) if pronoun_generic_map else set()
    candidates = [n for n in graph.nodes if n not in excluded and core_tokens(n)]
    tokens_by_node = {n: core_tokens(n) for n in candidates}

    resolution_map = {}
    for node in candidates:
        matches = [
        other for other in candidates
        if other != node and len(other) > len(node)
        and not _differs_only_by_distinguishing_suffix(node, other)
        and _is_variant_pair(tokens_by_node[node], tokens_by_node[other])
    ]
        if not matches:
            continue
        if len(matches) == 1:
            resolution_map[node] = ResolutionEntry(
                raw_name=node, tier=ResolutionTier.SURFACE_VARIANT,
                reason=f"shares core token(s) {tokens_by_node[node] & tokens_by_node[matches[0]]!r} "
                       f"with canonical form {matches[0]!r}",
                canonical_form=matches[0],
            )
        else:
            resolution_map[node] = ResolutionEntry(
                raw_name=node, tier=ResolutionTier.AMBIGUOUS_VARIANT_CANDIDATE,
                reason=f"matches {len(matches)} distinct longer candidates {sorted(matches)!r} "
                       f"- cannot determine canonical form mechanically",
                canonical_form=None,
            )
    return resolution_map