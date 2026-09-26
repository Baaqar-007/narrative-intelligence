# retrieval/direction_detection.py
"""Query-side entity-role/direction detection.

DESIGN HISTORY (fixes accumulated across Week 7 and the subsequent
real-usage audit - see docs/ for full detail):
- Cosine similarity: rejected, word-order blind.
- General dependency parser: rejected, misparses invented proper nouns.
- Anchor-phrase + verb-form matching against embedding.relation_text's
  verified templates: the working foundation.
- MIN_ANCHOR_LENGTH: travel_to's anchor ("to") caused false positives.
- Word-boundary entity matching: "An" matched inside "Ann".
- Article variants (a/an/the): "the friend of" was being missed.
- Gendered kinship synonyms (husband/wife/son/daughter/brother/sister).
- Modifier-tolerant matching ("the biological father of") - requires a
  trailing "of" after adversarial testing showed unconstrained
  modifier-gaps false-matched idioms ("mother ship", "father statue").
- father/mother removed from the verb-fallback entirely - zero-
  derivation collisions with idiomatic English.
- Possessive genitive ("Taug's companion") - FIXED direction (always
  "reverse"), not position-dependent - required its own function.
  Requires a real boundary after the noun for the same idiom-collision
  reason as the modifier fix ("Taug's mother tongue").
- mentioned_relations() extracted so live traversal (hybrid_search)
  can filter chains to relations the query actually asked about -
  unconstrained multi-hop traversal was found to return ~100%
  irrelevant chains from a high-degree start entity in real testing.
"""

import re

from embedding.relation_text import MANUAL_TEMPLATES, get_anchor_phrase

VERB_FORM_OVERRIDES: dict[str, str] = {
    "mentor_of": "mentor",
    "lover_of": "love",
    "teacher_of": "teach",
    "protector_of": "protect",
    "employer_of": "employ",
    "leader_of": "lead",
}
"""father/mother deliberately excluded - zero-derivation collisions
with idiomatic English ("founding father", "mother ship"), confirmed
via adversarial testing. Relies on noun-position matching (with
required trailing "of") instead."""

MIN_ANCHOR_LENGTH = 5
"""Anchors shorter than this are too generic to trust - travel_to's
anchor ("to") matched inside unrelated queries. Every other template's
anchor is 7+ characters."""

NOUN_SYNONYMS: dict[str, list[str]] = {
    "spouse_of": ["husband", "wife"],
    "child_of": ["son", "daughter"],
    "sibling_of": ["brother", "sister"],
}
"""Gendered alternatives for ungendered canonical nouns - found
missing entirely in real-usage testing ("the husband of Esther Lyon")."""


def _anchor_variants(anchor: str) -> list[str]:
    words = anchor.split()
    if words[0] in ("a", "an"):
        return [anchor, " ".join(["the"] + words[1:])]
    if words[0] == "the":
        return [anchor, " ".join(["a"] + words[1:]), " ".join(["an"] + words[1:])]
    return [anchor]


def _relation_nouns(relation: str) -> list[str]:
    nouns = []
    anchor = get_anchor_phrase(relation)
    if anchor is not None and len(anchor) >= MIN_ANCHOR_LENGTH:
        words = anchor.split()
        nouns.append(words[1] if words[0] in ("a", "an", "the") else words[0])
    nouns.extend(NOUN_SYNONYMS.get(relation, []))
    return nouns


def _noun_position_pattern(article: str, noun: str) -> str:
    """'<article> [0-2 modifier words] <noun> of' - requires trailing
    "of" to avoid idiom false-positives found via adversarial testing
    ("the old wooden mother ship", "the old stone father statue")."""
    return rf"\b{re.escape(article)}\s+(?:\w+\s+){{0,2}}{re.escape(noun)}\s+of\b"


def _possessive_noun_pattern(noun: str, possessor: str = r"\w+") -> str:
    """'<possessor>'s [0-2 modifiers] <noun>', requiring a real
    boundary after the noun (end of string, ?, comma, or a further
    possessive 's for chaining) - avoids compound-noun idiom false
    positives like "Taug's mother tongue"."""
    return (rf"\b{possessor}'s\s+(?:\w+\s+){{0,2}}{re.escape(noun)}"
            rf"(?:'s\b|[?,]|$)")


def _find_relation_mention(query_lower: str, relation: str) -> int | None:
    """Position of an "of"-genitive or verb-form mention. Possessive
    handled separately (fixed direction, not position-based)."""
    for noun in _relation_nouns(relation):
        for article in ("a", "an", "the"):
            m = re.search(_noun_position_pattern(article, noun), query_lower)
            if m is not None:
                return m.start()
    verb = VERB_FORM_OVERRIDES.get(relation)
    if verb is not None:
        idx = query_lower.find(verb.lower())
        if idx != -1:
            return idx
    return None


def _find_possessive_position(query_lower: str, relation: str) -> int | None:
    for noun in _relation_nouns(relation):
        m = re.search(_possessive_noun_pattern(noun), query_lower)
        if m is not None:
            return m.start()
    return None


def _find_possessive_mention(query_lower: str, relation: str) -> bool:
    return _find_possessive_position(query_lower, relation) is not None


def _find_possessive_direction(query_lower: str, entity_lower: str, relation: str) -> str | None:
    """"<entity>'s <noun>" always returns "reverse" - possessive
    direction is FIXED, not position-dependent. Proven by working
    through relation semantics: "X's employer" means X is the
    employee; "X's father" means X is the child. The possessor always
    ends up in the role the anchor noun does NOT name (entity2)."""
    for noun in _relation_nouns(relation):
        pattern = _possessive_noun_pattern(noun, re.escape(entity_lower))
        if re.search(pattern, query_lower):
            return "reverse"
    return None


def detect_query_direction(query: str, entity: str, relation: str) -> str | None:
    """Determine whether `query` asks about `entity` as entity1 or
    entity2, for `relation`. Checks possessive genitive first (fixed
    direction), then "of"-genitive/verb form (position-dependent).
    Declines (None) rather than guesses.

    Returns "forward" (entity plays entity1, query wants entity2),
    "reverse" (entity plays entity2, query wants entity1), or None.
    """
    if relation not in MANUAL_TEMPLATES:
        return None
    q_lower = query.lower()
    entity_lower = entity.lower()
    entity_match = re.search(r"\b" + re.escape(entity_lower) + r"\b", q_lower)
    if entity_match is None:
        return None
    entity_idx = entity_match.start()

    possessive_direction = _find_possessive_direction(q_lower, entity_lower, relation)
    if possessive_direction is not None:
        return possessive_direction

    mention_idx = _find_relation_mention(q_lower, relation)
    if mention_idx is None:
        return None
    return "forward" if entity_idx < mention_idx else "reverse"


def direction_match(query: str, fact: dict) -> bool | None:
    """Does the query's detected direction align with this fact's
    stored direction? Additive annotation only - never filters."""
    detected = detect_query_direction(query, fact["entity1"], fact["relation"])
    if detected is not None:
        return detected == "forward"
    detected = detect_query_direction(query, fact["entity2"], fact["relation"])
    if detected is not None:
        return detected == "reverse"
    return None


def entity_to_expand_from(query: str, entity1: str, entity2: str, relation: str) -> str:
    """Which entity chain expansion should continue from - the one the
    query asks ABOUT. Falls back to entity2 if undetermined."""
    detected = detect_query_direction(query, entity1, relation)
    if detected == "forward":
        return entity2
    if detected == "reverse":
        return entity1
    detected = detect_query_direction(query, entity2, relation)
    if detected == "reverse":
        return entity1
    if detected == "forward":
        return entity2
    return entity2

def target_relation(query: str) -> str | None:
    """The single relation this query is ultimately asking about - the
    outermost relation in a nested genitive chain (e.g. "the mother of
    Esther Lyon's husband" -> parent_mother_of, not spouse_of, even
    though spouse_of is also mentioned). Heuristic: the relation whose
    anchor phrase appears LEFTMOST in the query. Holds for both
    "X of Y's Z" and "the ... of X's Y's Z" phrasing (confirmed against
    real Week 7 audit examples) because English places the final-
    answer relation before its nested modifying clause in both cases -
    not proven for every possible phrasing. Distinct from
    mentioned_relations(), which returns the full unordered set (used
    for allowed_relations filtering, where all mentioned types should
    still be traversable as intermediate hops)."""
    q_lower = query.lower()
    positions: dict[str, int] = {}
    for relation in MANUAL_TEMPLATES:
        idx = _find_relation_mention(q_lower, relation)
        if idx is None:
            idx = _find_possessive_position(q_lower, relation)
        if idx is not None:
            positions[relation] = idx
    if not positions:
        return None
    return min(positions, key=positions.get)

def mentioned_relations(query: str) -> set[str]:
    """Set of relation types recognized anywhere in the query - any
    form (of-genitive, verb, possessive). Single source of truth for
    "what did this query ask about" - consumed by estimate_hop_depth()
    AND retrieval.hybrid_search's chain-filtering, so they can't drift
    out of sync (a real bug this session, at a smaller scale, already
    happened once)."""
    q_lower = query.lower()
    return {
        relation for relation in MANUAL_TEMPLATES
        if _find_relation_mention(q_lower, relation) is not None
        or _find_possessive_mention(q_lower, relation)
    }


def estimate_hop_depth(query: str, max_hops: int = 3) -> int:
    """Estimated additional hops needed beyond the vector-matched pair,
    from how many DISTINCT relation types are mentioned. Counts
    distinct types, not occurrences - known limitation, documented not
    hidden ("the companion of the companion of X" undercounts to 1).
    UNVALIDATED against the full diversity of real usage."""
    n = len(mentioned_relations(query))
    return max(0, min(n - 1, max_hops))
