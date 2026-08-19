# embedding/relation_text.py
"""Converts ARF relation dicts into natural-language sentences for
embedding.

Uses hand-written templates for relation types whose generic phrasing
would read as grammatically broken (see MANUAL_TEMPLATES), and falls
back to a generic template for everything else - including the ~2.5%
of relation instances that deviate from ARF's 48-type ontology
(see graph/relation_ontology.py and Week 1/2 findings).

Known limitation: 'used_by' is templated as "{entity1} is used by
{entity2}", matching ARF's declared type order (id 36: FAC->ORG, id 47:
OBJ->PER per the ARF paper's Appendix C). Real corpus data shows
GPT-4o did not apply this consistently - some instances have the
"user" as entity1 instead (e.g. {'entity1': 'the blacks', 'entity2':
'fire', 'relation': 'used_by'}), which will read backwards under this
template. Accepted as a small, known source-data inconsistency rather
than engineering a special case - revisit only if it measurably hurts
retrieval quality.
"""

MANUAL_TEMPLATES: dict[str, str] = {
    "parent_father_of": "{entity1} is the father of {entity2}",
    "parent_mother_of": "{entity1} is the mother of {entity2}",
    "child_of":        "{entity1} is a child of {entity2}",
    "sibling_of":      "{entity1} is a sibling of {entity2}",
    "spouse_of":       "{entity1} is a spouse of {entity2}",
    "relative_of":     "{entity1} is a relative of {entity2}",
    "adopted_by":      "{entity1} was adopted by {entity2}",
    "companion_of":    "{entity1} is a companion of {entity2}",
    "friend_of":       "{entity1} is a friend of {entity2}",
    "lover_of":        "{entity1} is a lover of {entity2}",
    "rival_of":        "{entity1} is a rival of {entity2}",
    "enemy_of":        "{entity1} is an enemy of {entity2}",
    "mentor_of":       "{entity1} is a mentor of {entity2}",
    "teacher_of":      "{entity1} is a teacher of {entity2}",
    "protector_of":    "{entity1} is a protector of {entity2}",
    "employer_of":     "{entity1} is an employer of {entity2}",
    "leader_of":       "{entity1} is a leader of {entity2}",
    "member_of":       "{entity1} is a member of {entity2}",
    "travel_to":       "{entity1} travels to {entity2}",
    "born_in":         "{entity1} was born in {entity2}",
    "located_in":      "{entity1} is located in {entity2}",
    "part_of":         "{entity1} is part of {entity2}",
    "owned_by":        "{entity1} is owned by {entity2}",
    "occupied_by":     "{entity1} is occupied by {entity2}",
    "used_by":         "{entity1} is used by {entity2}",
    "experienced_by":  "{entity1} is experienced by {entity2}",
    "based_in":        "{entity1} is based in {entity2}",
    "attended_by":     "{entity1} was attended by {entity2}",
    "stored_in":       "{entity1} is stored in {entity2}",
    "expressed_by":    "{entity1} is expressed by {entity2}",
    "associated_with": "{entity1} is associated with {entity2}",
}


def relation_to_sentence(entity1: str, entity2: str, relation: str) -> str:
    """Convert a relation triple into a natural-language sentence.

    Uses a hand-written template if one exists for this relation type
    (grammatically correct, e.g. "X is the father of Y"). Otherwise
    falls back to a generic pattern that reads stiffly but remains
    understandable (e.g. "X is companion of Y"), covering both the
    remaining ontology relation types and any non-canonical, free-text
    relation strings present in the data.

    Args:
        entity1: The first entity's raw or normalized name.
        entity2: The second entity's raw or normalized name.
        relation: The relation type string from the ARF dataset.

    Returns:
        A natural-language sentence describing the relation.
    """
    template = MANUAL_TEMPLATES.get(relation)
    if template is not None:
        return template.format(entity1=entity1, entity2=entity2)

    readable_relation = relation.replace("_", " ")
    return f"{entity1} {readable_relation} {entity2}"