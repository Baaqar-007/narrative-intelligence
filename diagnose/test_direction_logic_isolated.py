"""Isolated test: does detect_query_direction() work correctly when
fed a query that DOES contain the real canonical entity string
verbatim - even if that string is messy (a bare pronoun, a full
descriptive clause)?

This is the missing piece from diagnose_entities_and_chains.py: that
script showed entity strings don't match natural queries (the
canonicalization ceiling), but never tested whether the logic
underneath is sound once that specific barrier is removed. Separates
"the entity string can't be found" from "the direction logic is
broken" - two different bugs that would need two different fixes.

Fill in REAL_CASES below with actual (entity1, entity2, relation)
triples from your own fact rows (entity_and_chain_inspection.csv or
pipeline_diagnostic_log.csv) - using real canonical strings, however
messy, is the whole point.
"""

from retrieval.direction_detection import detect_query_direction

# Fill in with REAL rows from your own data - (canonical_entity1,
# canonical_entity2, relation). Include at least one with a messy
# canonical string (pronoun or descriptive clause) if you have one.
REAL_CASES = [
    # --- clean canonical strings (control) ---
    ("esther", "mr. lyon", "child_of"),              # chain: esther -> mr. lyon, child_of / adopted_by
    ("mr. lyon", "esther", "parent_father_of"),      # chain: mr. holt -> mr. lyon -> esther (parent_father_of)
    ("harold", "mrs. transome", "child_of"),         # chain: his mother -> harold -> mrs. transome (child_of)

    # --- messy canonical strings (the actual point of this test) ---
    ("his mother", "felix holt", "parent_mother_of"),        # fact: his mother -> felix holt (bare pronoun)
    ("her son", "mrs. transome", "child_of"),                # fact: her son -> her / mrs. transome (bare pronoun)
    ("jermyn's third daughter", "jermyn", "child_of"),       # fact: jermyn -> "jermyn's third daughter" (descriptive clause)
    ("lawyer jermyn", "transome estate", "member_of"),       # fact: lawyer jermyn -> transome estate (title + multiword)
]


def main():
    if not REAL_CASES:
        print("Fill in REAL_CASES with real (entity1, entity2, relation) "
              "triples from your own fact rows before running.")
        return

    for entity1, entity2, relation in REAL_CASES:
        # Synthetic query using the EXACT canonical string verbatim,
        # in the "of"-genitive form already confirmed working - this
        # isolates "does the logic work given the string" from
        # "can the string ever appear in a real question at all".
        query_forward = f"Who is {entity1} a {relation.replace('_of', '').replace('_', ' ')} of?"
        query_reverse = f"Who is a {relation.replace('_of', '').replace('_', ' ')} of {entity1}?"

        result_forward = detect_query_direction(query_forward, entity1, relation)
        result_reverse = detect_query_direction(query_reverse, entity1, relation)

        print(f"entity={entity1!r}  relation={relation!r}")
        print(f"  forward-phrased query: {query_forward!r} -> {result_forward!r} (expect 'forward')")
        print(f"  reverse-phrased query: {query_reverse!r} -> {result_reverse!r} (expect 'reverse')")
        if result_forward != "forward" or result_reverse != "reverse":
            print("  ** UNEXPECTED - logic issue independent of canonicalization, not just the known ceiling **")
        print()


if __name__ == "__main__":
    main()
