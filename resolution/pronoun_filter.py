# resolution/pronoun_filter.py
"""Stage 0 of entity resolution (Week 8): mechanical pre-filter for
bare-pronoun and generic-noun strings that ARF/GPT-4o extraction
stored as if they were canonical entity names (e.g. "her son",
"mother", "his", "the child").

WHY THIS RUNS FIRST, ahead of Week 4's original Stage A (mechanical
alias merging): Day 4's corpus-wide audit (functional-step scope -
the e1 role of parent_father_of/parent_mother_of, the one relation
family where a single answer is structurally correct) found 58% of
confirmed entity fragmentation is this pronoun/generic pattern,
against 9% for surface-name variants (Stage A's target). Filtering
these out first is also a genuine dependency, not just a priority
call: a pronoun string must never become an alias-merge candidate
("her son" should not be clustered with "harold" - it isn't an alias
of Harold, it's a failure to resolve Harold at all).

NON-DESTRUCTIVE: never mutates the graph. Produces a resolution_map
entry per flagged node - raw facts stay retrievable, but multi-hop
composition (graph traversal chaining two or more hops) must refuse
to continue THROUGH an excluded node, mirroring the day-3 yardstick's
own walk()-purity fix (an intermediate frontier of unknown identity
must not be composed further). See Week 4's summary-doc entry for the
full resolution_map architecture.

DETECTION MECHANISM, deliberately simple for now: a hand-seeded list
of pronouns/determiners/generic-kinship-nouns, matched against an
entity string's FINAL token (catches "her son", "his mother", "your
daughter" - the possessive/determiner sits first, the generic noun
last). Same category of choice as MANUAL_TEMPLATES: correct until a
real case falls outside it, not a general solution. NOT YET measured
for miss rate (a real pronoun/generic string this list fails to
catch) or false-positive rate (a genuine character literally named
"Father" or "Son" - not observed in this corpus, not proven absent).
Escalating to a POS-tagging-based detector is deferred until a real
miss rate is measured against a full audit pass - not assumed
necessary in advance.
"""

from dataclasses import dataclass
from enum import Enum

import networkx as nx


class ResolutionTier(str, Enum):
    """Confidence tier for a resolution_map entry. Only one tier is
    populated by this module; later Week 8 stages will add more
    (surface_variant, hard_alias_candidate, coreference_*) - this
    module's scope stops at EXCLUDED_PRONOUN_GENERIC."""

    EXCLUDED_PRONOUN_GENERIC = "excluded_pronoun_generic"


@dataclass(frozen=True)
class ResolutionEntry:
    raw_name: str
    tier: ResolutionTier
    reason: str


# Hand-seeded, NOT exhaustive. Sourced from this project's own real
# findings: the Week 7 audit's "her"/"you" pronoun examples, and
# days 2-4's Harold-cluster diagnostics ("her son", "my son",
# "mother", "her own son"). Extend only from a real, observed miss -
# don't pre-guess additions "to be safe" (adds false-positive risk on
# real character names without a corresponding measured benefit).
PRONOUN_GENERIC_LAST_TOKEN: frozenset[str] = frozenset({
    "he", "she", "her", "his", "him", "you", "your", "yours",
    "me", "my", "mine", "i", "we", "our", "ours", "us",
    "they", "them", "their", "theirs", "it", "its",
    "mother", "father", "son", "daughter", "husband", "wife",
    "brother", "sister", "child", "baby", "parent",
})

# Irregular/archaic plural or spelling forms found in real corpus data
# (day-5 audit) - "sonnes" is an archaic spelling this project's
# specific Decameron translation uses; "children" is irregular (not
# caught by stripping a trailing "s"). NOT exhaustive - same
# discipline as the base list: extend from a real observed miss.
_IRREGULAR_PLURAL_FORMS: frozenset[str] = frozenset({"children", "sonnes"})
_ARCHAIC_PRONOUNS: frozenset[str] = frozenset({
    "thee", "thou", "thy", "thine", "ye", "hath", "doth",
})
_ARCHAIC_KINSHIP_SPELLINGS: frozenset[str] = frozenset({"sonne"})

def is_pronoun_generic(entity: str) -> bool:
    """True if `entity`'s final token matches a known bare-pronoun or
    generic-noun pattern (singular or plural) - the singular form of
    this pattern was found (day 4 audit) to explain 58% of confirmed
    functional-step entity fragmentation.

    Matches on the LAST token so "her son" / "his mother" / "your
    daughter" are all caught by one check, not a rule per phrasing. A
    single-token entity ("mother", "her") is caught the same way -
    the last token IS the whole string.

    Plural handling, added day 5 after real corpus data (Decameron,
    King Arthur, Sons and Lovers) showed plural forms ("daughters",
    "sonnes", "children") slipping through the original singular-only
    check: irregular/archaic forms are listed explicitly;
    regular plurals are caught by stripping a single trailing "s" and
    re-checking. Deliberately conservative (bare "-s" strip only, one
    pass, no deeper stemming) - can only false-positive on a real
    character name that happens to be the plural-looking form of one
    of these specific words (e.g. a character literally named "Sons")
    - not observed in this corpus, same accepted-risk shape as the
    base list itself.
    """
    tokens = entity.strip().lower().split()
    if not tokens:
        return False
    last = tokens[-1]
    if last in PRONOUN_GENERIC_LAST_TOKEN or last in _IRREGULAR_PLURAL_FORMS or last in _ARCHAIC_PRONOUNS or last in _ARCHAIC_KINSHIP_SPELLINGS:
        return True
    return last.endswith("s") and last[:-1] in PRONOUN_GENERIC_LAST_TOKEN


def build_resolution_map(graph: nx.MultiDiGraph) -> dict[str, ResolutionEntry]:
    """Scan every node in `graph` and return resolution_map entries
    for nodes matching is_pronoun_generic(). Does NOT modify `graph`.

    Returns:
        raw_node_name -> ResolutionEntry, for flagged nodes only. A
        node absent from the result is not flagged by THIS stage - it
        may still be flagged by a later Week 8 stage this module has
        no visibility into.
    """
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
    THROUGH `entity` as an intermediate node.

    Single-hop retrieval is NOT affected - a raw fact like ("her
    son", "parent_father_of", "jermyn") stays fully retrievable on its
    own (non-destructive: nothing is hidden from single-hop lookups).
    This check exists only for traversal/composition logic (e.g.
    graph.traversal.find_paths_up_to_hops, or the day-3 yardstick's
    walk()) deciding whether to extend a chain through this node.

    Not automatically wired into any existing traversal function yet
    - integration into retrieval.hybrid_search / graph.traversal is a
    separate, deliberate follow-up, not done by this module.
    """
    return entity in resolution_map