import re

from embedding.relation_text import MANUAL_TEMPLATES, get_anchor_phrase

VERB_FORM_OVERRIDES: dict[str, str] = {
    "parent_father_of": "father",   # zero-derivation (noun = verb)
    "parent_mother_of": "mother",   # zero-derivation
    "mentor_of": "mentor",          # zero-derivation
    "lover_of": "love",             # real morphological change
    "teacher_of": "teach",
    "protector_of": "protect",
    "employer_of": "employ",
    "leader_of": "lead",
}

MIN_ANCHOR_LENGTH = 5
"""Anchors shorter than this are too generic to trust as a position
signal - found via testing, not assumed: travel_to's anchor ("to", 2
chars) matched inside unrelated queries. Every other template's anchor
is 7+ characters; 5 sits safely in the gap between them."""


def _anchor_variants(anchor: str) -> list[str]:
    """A canonical anchor phrase plus article variants ('a'/'an' <->
    'the') - both are equally natural English for the same
    relationship ("a friend of X" / "the friend of X"), and checking
    only the template's literal article missed a real, common case
    (15 of 31 templates use a/an; "the X of Y" is at least as natural
    a way to phrase a query - found by testing the actual motivating
    example, not assumed in advance)."""
    words = anchor.split()
    if words[0] in ("a", "an"):
        return [anchor, " ".join(["the"] + words[1:])]
    if words[0] == "the":
        return [anchor, " ".join(["a"] + words[1:]), " ".join(["an"] + words[1:])]
    return [anchor]


def detect_query_direction(query: str, entity: str, relation: str) -> str | None:
    """Determine whether `query` asks about `entity` as entity1 or
    entity2, for `relation`.

    Two tiers, both matched against already-verified phrasing rather
    than derived from the query in isolation: the relation's exact
    anchor phrase first (e.g. "a protector of"), falling back to its
    verb form if the anchor phrase isn't present verbatim (e.g. the
    query says "protects" instead of "a protector of"). Declines
    (returns None) rather than guesses if neither is found, or if the
    entity itself isn't present in the query text at all.

    Args:
        query: Free-text query.
        entity: The specific entity name to check the role of - e.g.
            a vector-matched hit's entity1 or entity2.
        relation: The relation type string.

    Returns:
        "forward" if entity plays entity1's role (query wants entity2),
        "reverse" if entity plays entity2's role (query wants entity1),
        or None if direction couldn't be determined.
    """
    if relation not in MANUAL_TEMPLATES:
        return None

    q_lower = query.lower()
    entity_match = re.search(r"\b" + re.escape(entity.lower()) + r"\b", q_lower)
    if entity_match is None:
        return None
    entity_idx = entity_match.start()

    anchor = get_anchor_phrase(relation)
    if anchor is not None and len(anchor) >= MIN_ANCHOR_LENGTH:
        for variant in _anchor_variants(anchor):
            anchor_idx = q_lower.find(variant.lower())
            if anchor_idx != -1:
                return "forward" if entity_idx < anchor_idx else "reverse"

    verb = VERB_FORM_OVERRIDES.get(relation)
    if verb is not None:
        verb_idx = q_lower.find(verb.lower())
        if verb_idx != -1:
            return "forward" if entity_idx < verb_idx else "reverse"

    return None


def direction_match(query: str, fact: dict) -> bool | None:
    """Does the query's detected direction align with this specific
    fact's stored direction?

    Used to annotate (not filter) retrieved facts - see
    retrieval.hybrid_search. A mismatch doesn't mean the fact is
    wrong or irrelevant, only that it doesn't directly answer what was
    asked in the direction asked; destructively dropping it isn't this
    function's call to make.

    Args:
        query: The original free-text query.
        fact: A relationship dict with 'entity1', 'entity2', 'relation'
            keys (e.g. from temporal.trajectory.get_relationships_between).

    Returns:
        True if the query's intent matches this fact's stored
        direction, False if it's the opposite, None if direction
        couldn't be determined for this fact's entities/relation.
    """
    detected = detect_query_direction(query, fact["entity1"], fact["relation"])
    if detected is not None:
        return detected == "forward"
    detected = detect_query_direction(query, fact["entity2"], fact["relation"])
    if detected is not None:
        return detected == "reverse"
    return None


def entity_to_expand_from(query: str, entity1: str, entity2: str, relation: str) -> str:
    """Decide which entity multi-hop chain expansion should continue
    from - the one the query is actually asking ABOUT, not the one
    it already names as known.

    Replaces retrieval.hybrid_search's previous hardcoded "always
    expand from entity2" default, which was explicitly flagged as
    provisional pending this module's existence.

    Falls back to entity2 (the original default) if direction can't be
    determined for either entity - strictly additive behavior, not a
    regression for cases this module can't resolve.
    """
    detected = detect_query_direction(query, entity1, relation)
    if detected == "forward":
        return entity2   # query already knows entity1, wants entity2
    if detected == "reverse":
        return entity1   # query wants entity1 - that's the fresh entity to expand from

    detected = detect_query_direction(query, entity2, relation)
    if detected == "reverse":
        return entity1
    if detected == "forward":
        return entity2

    return entity2  # undetermined - preserve original default behavior
