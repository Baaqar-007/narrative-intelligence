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
    entity_idx = q_lower.find(entity.lower())
    if entity_idx == -1:
        return None

    anchor = get_anchor_phrase(relation)
    if anchor is not None:
        anchor_idx = q_lower.find(anchor.lower())
        if anchor_idx != -1:
            return "forward" if entity_idx < anchor_idx else "reverse"

    verb = VERB_FORM_OVERRIDES.get(relation)
    if verb is not None:
        verb_idx = q_lower.find(verb.lower())
        if verb_idx != -1:
            return "forward" if entity_idx < verb_idx else "reverse"

    return None
