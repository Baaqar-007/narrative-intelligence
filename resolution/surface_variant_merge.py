# resolution/surface_variant_merge.py
"""Stage A of entity resolution (Week 8): mechanical surface-variant
alias merging via honorific/article stripping + pairwise (non-
transitive) core-token matching. Runs AFTER Stage 0
(pronoun_filter.py) - a pronoun/generic node must never become a
merge candidate here.

SCOPE, deliberately narrow (per Amalvy & Labatut's alias-resolution
taxonomy; Week 1's own prior difflib-fuzzy-match finding): exact
core-token overlap only, after stripping honorifics/articles. Does
NOT do fuzzy/edit-distance matching, and does NOT resolve true hard
aliases with zero string overlap (Wotan/Wanderer, "the king"/Tancrede
- deferred, not this module's job, no mechanical fix exists for this
class of problem).

DESIGN HISTORY, each point a real, data-found correction, not a
hypothetical:
- Union-find clustering (first version) was wrong: transitivity lets
  two unrelated nodes merge through an intermediate shared token,
  producing a 707-member cluster on real data. Replaced with direct
  pairwise matching only.
- "Longest string wins" as the canonical-selection rule was wrong: a
  node matching MULTIPLE distinct longer candidates (e.g. a bare name
  matching both a fuller form AND an unrelated person's modified
  name) picked one arbitrarily. Replaced with AMBIGUOUS_VARIANT_
  CANDIDATE (decline, don't guess) whenever 2+ distinct matches exist.
- A single shared token is UNSAFE as sole evidence once a surname can
  be shared by distinct family members (spouses, parent/child) or
  distinct title-holders across unrelated stories (this corpus bundles
  ~100 Decameron novellas under one book_id) - see _is_variant_pair.
- Generational/age-distinguishing modifiers (Jr., Sr., young/old, a
  generation-marking suffix) are NOT variants of the unmarked form -
  they EXIST to mark a different person. Hard-blocked via
  _differs_only_by_distinguishing_suffix, not left to the general
  ambiguity check.
- KNOWN, NOT FIXED limitation: two DIFFERENT modified names sharing
  only the modifier itself ("young holt" / "young felix") can still
  false-merge - the suffix block only guards the adjacent case (bare
  name vs its modified form), not this lateral case. This is the
  module's confirmed mechanical ceiling, not a bug queue - see
  project log, Week 8 Stage A closure.
"""

from resolution.pronoun_filter import ResolutionEntry, ResolutionTier

HONORIFICS_AND_ARTICLES: frozenset[str] = frozenset({
    "mr", "mr.", "mrs", "mrs.", "miss", "ms", "ms.", "dr", "dr.",
    "sir", "lady", "lord", "madam", "madame", "messer", "signior", "signor",
    "king", "queen", "prince", "princess", "count", "countess",
    "duke", "duchess", "the", "a", "an",
    # In HONORIFICS_AND_ARTICLES (resolution/surface_variant_merge.py):
    # professional/judicial titles, found via book 3322 ("justice" as a
    # standalone referring to "mr. justice hare") - same category as
    # existing honorifics, just a vocabulary gap
    "justice", "judge", "doctor", "captain", "reverend", "rev", "rev.",
})

# Generational/age-distinguishing suffixes - a pair differing ONLY by
# one of these must never merge, regardless of other token overlap.
# See module docstring for why this is a hard veto, not a candidacy
# filter.
DISTINGUISHING_SUFFIXES: frozenset[str] = frozenset({
    "jr", "jr.", "junior", "sr", "sr.", "senior",
    "ii", "iii", "iv", "elder", "younger", "young", "old",
})


def core_tokens(entity: str) -> frozenset[str]:
    """Identifying tokens only - honorifics/titles/articles stripped
    from anywhere in the string. A bare title with nothing left after
    stripping ("the count") returns an empty set and is excluded from
    candidacy entirely - nothing mechanical to match it on."""
    return frozenset(
        t for t in entity.strip().lower().split()
        if t not in HONORIFICS_AND_ARTICLES
    )


def _is_variant_pair(a_tokens: frozenset[str], b_tokens: frozenset[str]) -> bool:
    """True only if the SMALLER token set is fully contained in the
    larger ("morel" subset-of "walter morel"), OR both sets share 2+
    tokens. A single shared token between two otherwise-disjoint
    multi-token sets is NOT sufficient - that pattern is exactly what
    produced real false merges (shared surname between distinct
    family members; shared title across distinct stories)."""
    if not a_tokens or not b_tokens:
        return False
    smaller, larger = (a_tokens, b_tokens) if len(a_tokens) <= len(b_tokens) else (b_tokens, a_tokens)
    shared = smaller & larger
    if not shared:
        return False
    if smaller <= larger:
        return True
    return len(shared) >= 2


def _differs_only_by_distinguishing_suffix(a: str, b: str) -> bool:
    """True if `a` and `b` differ only by tokens in
    DISTINGUISHING_SUFFIXES - these pairs must NEVER merge, since the
    differing token exists specifically to mark a different person
    (Jacob vs Jacob Jr.), not to add detail to one name."""
    a_tokens, b_tokens = set(a.lower().split()), set(b.lower().split())
    diff = a_tokens.symmetric_difference(b_tokens)
    return bool(diff) and diff <= DISTINGUISHING_SUFFIXES


def build_surface_variant_map(
    graph, pronoun_generic_map: dict[str, ResolutionEntry] | None = None,
) -> dict[str, ResolutionEntry]:
    """Direct pairwise (non-transitive) matching. A node matching
    exactly one distinct longer candidate is SURFACE_VARIANT; a node
    matching 2+ distinct longer candidates is AMBIGUOUS_VARIANT_
    CANDIDATE (decline, don't guess which one is canonical). Nodes
    already flagged by Stage 0 are excluded from candidacy entirely.
    Non-destructive: does not modify `graph`."""
    excluded = set(pronoun_generic_map) if pronoun_generic_map else set()
    candidates = [n for n in graph.nodes if n not in excluded and core_tokens(n)]
    tokens_by_node = {n: core_tokens(n) for n in candidates}

    resolution_map: dict[str, ResolutionEntry] = {}
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
                reason=f"shares core token(s) "
                       f"{tokens_by_node[node] & tokens_by_node[matches[0]]!r} "
                       f"with canonical form {matches[0]!r}",
                canonical_form=matches[0],
            )
        else:
            resolution_map[node] = ResolutionEntry(
                raw_name=node, tier=ResolutionTier.AMBIGUOUS_VARIANT_CANDIDATE,
                reason=f"matches {len(matches)} distinct longer candidates "
                       f"{sorted(matches)!r} - cannot determine canonical form mechanically",
                canonical_form=None,
            )
    return resolution_map