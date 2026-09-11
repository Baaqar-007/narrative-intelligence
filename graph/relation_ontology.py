# graph/relation_ontology.py
"""Canonical relation ontology from the ARF dataset paper.

Source: Christou & Tsoumakas, "Artificial Relationships in Fiction:
A Dataset for Advancing NLP in Literary Domains" (LaTeCH-CLfL 2025),
Appendix C. 48 relation types were the closed ontology given to GPT-4o
for annotation; ~2.5% of generated relation instances deviate from
this ontology (see paper Table 2, and our own corpus analysis which
found matching deviation rates).
"""

CANONICAL_RELATION_TYPES: frozenset[str] = frozenset({
    "parent_father_of", "parent_mother_of", "child_of", "sibling_of",
    "spouse_of", "relative_of", "adopted_by", "companion_of", "friend_of",
    "lover_of", "rival_of", "enemy_of", "inspires", "sacrifices_for",
    "mentor_of", "teacher_of", "protector_of", "employer_of", "leader_of",
    "member_of", "lives_in", "lived_in", "visits", "travel_to", "born_in",
    "travels_by", "participates_in", "causes", "owns", "believes_in",
    "embodies", "located_in", "part_of", "owned_by", "occupied_by",
    "used_by", "affects", "experienced_by", "travels_in", "based_in",
    "attended_by", "ends_in", "occurs_in", "features", "stored_in",
    "expressed_by", "associated_with",
})


def is_canonical_relation(relation: str) -> bool:
    """Check whether a relation string matches the ARF ontology's 48 types.

    Args:
        relation: The raw relation string from a parsed ARF relation dict.

    Returns:
        True if the relation is one of the 48 canonical ontology types.
    """
    return relation in CANONICAL_RELATION_TYPES

# graph/relation_ontology.py — add alongside is_canonical_relation()

SYMMETRIC_RELATIONS: set[str] = {
    "companion_of", "friend_of", "enemy_of", "rival_of",
    "sibling_of", "spouse_of", "relative_of",
}
"""Relation types confirmed (README, Week 2) to be stored
inconsistently in direction for the same real-world pair — e.g.
companion_of appears both directions across different instances.
Used by graph-traversal code to decide which relation types are safe
to treat as bidirectional for reachability purposes; NOT a claim that
these relations are semantically direction-free in every instance,
only that ARF's own extraction doesn't reliably preserve a consistent
direction for them."""