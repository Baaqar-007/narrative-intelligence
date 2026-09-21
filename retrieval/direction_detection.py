# retrieval/direction_detection.py
"""Query-side entity-role/direction detection.

Determines whether a free-text query is asking "forward" (a known
entity plays entity1's role, the query wants entity2) or "reverse"
(the known entity plays entity2's role, the query wants entity1) for
a given relation type.

DESIGN HISTORY (see docs/ for full detail):
- Cosine similarity: rejected, tested, word-order blind.
- General dependency parser: rejected, misparses this corpus's
  invented proper nouns.
- Anchor-phrase + verb-form matching against embedding.relation_text's
  verified templates: what works, tested extensively.
- MIN_ANCHOR_LENGTH: travel_to's anchor ("to") caused false positives.
- Word-boundary entity matching: "An" matched inside "Ann".
- Article variants (a/an/the): "the friend of" was being missed.
- Real-usage audit (Week 7 reality check) found further gaps:
  possessive genitive ("Taug's companion") entirely unrecognized by
  this module as originally built; gendered kinship terms
  (husband/wife/son/daughter/brother/sister) missing from vocabulary
  entirely; modifier-inserted phrases ("the biological father of")
  defeat exact substring matching. Fixes for these are tracked
  separately as they're identified and tested.
"""

import re

from embedding.relation_text import MANUAL_TEMPLATES, get_anchor_phrase

_QUESTION_OVERRIDES: dict[str, str] = {}  # placeholder, not relevant here

VERB_FORM_OVERRIDES: dict[str, str] = {
    "mentor_of": "mentor",
    "lover_of": "love",
    "teacher_of": "teach",
    "protector_of": "protect",
    "employer_of": "employ",
    "leader_of": "lead",
}
"""parent_father_of/parent_mother_of deliberately excluded, even
though "father"/"mother" are valid zero-derivation verbs - found via
adversarial testing that they're too collision-prone as unconstrained
substring matches (idiomatic non-kinship uses: "founding father",
"mother ship", "mother tongue" all contain the bare word with no
kinship meaning at all). Relies on the noun-position matching (with
required trailing "of") instead, which is scoped tightly enough to
avoid this. "mentor" kept - no comparable common-idiom collision risk
identified."""

MIN_ANCHOR_LENGTH = 5
"""Anchors shorter than this are too generic to trust as a position
signal - found via testing: travel_to's anchor ("to", 2 chars)
matched inside unrelated queries. Every other template's anchor is 7+
characters; 5 sits safely in the gap between them."""

NOUN_SYNONYMS: dict[str, list[str]] = {
    "spouse_of": ["husband", "wife"],
    "child_of": ["son", "daughter"],
    "sibling_of": ["brother", "sister"],
}
"""Gendered alternatives for relations whose canonical template noun
is ungendered. Found via real-usage audit: "the husband of Esther
Lyon" didn't match spouse_of's anchor ("a spouse of") at all - not a
phrasing-style gap, a missing-vocabulary gap. Gender doesn't change
which stored direction (forward/reverse) is meant - "husband" and
"wife" both just mean "spouse" - so these use the exact same
forward/reverse position logic as the canonical noun, not a separate
direction rule."""


def _anchor_variants(anchor: str) -> list[str]:
    words = anchor.split()
    if words[0] in ("a", "an"):
        return [anchor, " ".join(["the"] + words[1:])]
    if words[0] == "the":
        return [anchor, " ".join(["a"] + words[1:]), " ".join(["an"] + words[1:])]
    return [anchor]


def _relation_nouns(relation: str) -> list[str]:
    """The canonical anchor noun plus any gendered synonyms - e.g.
    spouse_of -> ["spouse", "husband", "wife"]."""
    nouns = []
    anchor = get_anchor_phrase(relation)
    if anchor is not None and len(anchor) >= MIN_ANCHOR_LENGTH:
        words = anchor.split()
        nouns.append(words[1] if words[0] in ("a", "an", "the") else words[0])
    nouns.extend(NOUN_SYNONYMS.get(relation, []))
    return nouns


def _noun_position_pattern(article: str, noun: str) -> str:
    """'<article> [0-2 modifier words] <noun> of' - e.g. "the
    biological father of" still matches against "father". Requires
    the trailing "of" to complete the genitive structure - found via
    adversarial testing that omitting this caused real false
    positives on idiomatic English with no kinship meaning at all
    ("the old wooden mother ship", "the old stone father statue" both
    matched without this constraint, confidently and wrongly)."""
    return rf"\b{re.escape(article)}\s+(?:\w+\s+){{0,2}}{re.escape(noun)}\s+of\b"


def _find_relation_mention(query_lower: str, relation: str) -> int | None:
    """Find the position of any recognized mention of `relation` in
    the query - canonical noun, gendered synonym, tolerating inserted
    modifiers, or verb form - whichever matches first. Single place
    both detect_query_direction() and estimate_hop_depth() funnel
    through, so they can't drift out of sync the way two independent
    implementations already did once this week (see the verb-matching
    word-boundary regression in this module's own history).

    Returns the match's start index, or None if nothing matched.
    """
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


def _possessive_noun_pattern(noun: str, possessor: str = r"\w+") -> str:
    """Regex for '<possessor>'s [0-2 modifiers] <noun>', requiring a
    real boundary after the noun (end of string, ?, comma, or a
    further possessive 's for chaining like "friend's leader") - not
    just any following word, which would let compound-noun idioms
    through uncaught. Found via adversarial testing: without this,
    "Taug's mother tongue was English" confidently false-matched
    parent_mother_of.

    Default possessor is any word (for estimate_hop_depth, which only
    needs to know a relation was mentioned, not by whom); callers
    checking one specific known entity pass its escaped text instead.
    """
    return (rf"\b{possessor}'s\s+(?:\w+\s+){{0,2}}{re.escape(noun)}"
            rf"(?:'s\b|[?,]|$)")


def _find_possessive_mention(query_lower: str, relation: str) -> bool:
    """Is `relation` mentioned anywhere via possessive genitive,
    regardless of who the possessor is - used for hop-depth counting."""
    return any(
        re.search(_possessive_noun_pattern(noun), query_lower)
        for noun in _relation_nouns(relation)
    )


def _find_possessive_direction(query_lower: str, entity_lower: str, relation: str) -> str | None:
    """Does `entity` appear as the possessor immediately before one of
    `relation`'s nouns ("<entity>'s <noun>")?

    Always returns "reverse" when it matches - possessive direction is
    FIXED, not position-dependent like the "of"-genitive form. Proven
    by working through every relation's actual semantics, not assumed
    from surface word order: "X's employer" means X is the employee,
    never the employer; "X's father" means X is the child, never the
    father; "X's child" means X is the parent. The possessor always
    ends up in the role the anchor noun does NOT name - entity2,
    universally, across every relation checked. Symmetric relations
    (companion_of, friend_of, etc.) are direction-neutral in meaning,
    so returning "reverse" there is a harmless, consistent default,
    not a wrong answer.
    """
    for noun in _relation_nouns(relation):
        pattern = _possessive_noun_pattern(noun, re.escape(entity_lower))
        if re.search(pattern, query_lower):
            return "reverse"
    return None


def detect_query_direction(query: str, entity: str, relation: str) -> str | None:
    if relation not in MANUAL_TEMPLATES:
        return None

    q_lower = query.lower()
    entity_match = re.search(r"\b" + re.escape(entity.lower()) + r"\b", q_lower)
    if entity_match is None:
        return None
    entity_idx = entity_match.start()

    possessive_direction = _find_possessive_direction(q_lower, entity.lower(), relation)
    if possessive_direction is not None:
        return possessive_direction

    mention_idx = _find_relation_mention(q_lower, relation)
    if mention_idx is None:
        return None
    return "forward" if entity_idx < mention_idx else "reverse"


def direction_match(query: str, fact: dict) -> bool | None:
    detected = detect_query_direction(query, fact["entity1"], fact["relation"])
    if detected is not None:
        return detected == "forward"
    detected = detect_query_direction(query, fact["entity2"], fact["relation"])
    if detected is not None:
        return detected == "reverse"
    return None


def entity_to_expand_from(query: str, entity1: str, entity2: str, relation: str) -> str:
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


def estimate_hop_depth(query: str, max_hops: int = 3) -> int:
    q_lower = query.lower()
    relations_mentioned = {
        relation for relation in MANUAL_TEMPLATES
        if _find_relation_mention(q_lower, relation) is not None
        or _find_possessive_mention(q_lower, relation)
    }
    return max(0, min(len(relations_mentioned) - 1, max_hops))
