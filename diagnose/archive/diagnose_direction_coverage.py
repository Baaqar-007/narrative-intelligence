"""Diagnostic: direction-detection coverage across phrasing styles.

Run standalone, no corpus/ChromaDB/model needed - pure text functions.
Tests the specific gap found this session: detect_query_direction and
estimate_hop_depth were validated almost entirely against "of"-genitive
phrasing ("a friend of X"), which the benchmark generator itself always
produces - but real usage includes possessive ("X's friend"), relative
clause ("the person who..."), and yes/no phrasing that were never
checked. Replace REAL_ENTITY_NAMES below with actual names from your
corpus (short names, multi-word names, unusual names) for a more
representative test than testing "Taug" alone.

Output: prints a per-question table and an overall coverage summary,
and writes results to direction_coverage_log.csv for sharing back.
"""

import csv

from embedding.relation_text import MANUAL_TEMPLATES
from retrieval.direction_detection import detect_query_direction, estimate_hop_depth

# --- Fill in with real names from your corpus before running ---
REAL_ENTITY_NAMES = ["Taug", "Akut", "Teeka"]  # replace with real, varied names

# One relation per phrasing style, per entity - deliberately spans
# every style a real user might actually type, not just the one the
# benchmark generator produces.
QUESTION_TEMPLATES = [
    ("of-genitive (tested style)", "Who is {e} a companion of?", "companion_of"),
    ("of-genitive, verb form", "Who protects {e}?", "protector_of"),
    ("possessive 's (untested style)", "Who is {e}'s companion?", "companion_of"),
    ("possessive 's, verb form", "Who does {e}'s companion protect?", "protector_of"),
    ("relative clause (untested style)", "Who is the person that {e} protects?", "protector_of"),
    ("yes/no question (untested style)", "Is {e} a companion of Akut?", "companion_of"),
    ("nested of-genitive, 2-hop", "Who is the leader of the friend of {e}?", "friend_of"),
    ("nested possessive, 2-hop", "Who is {e}'s friend's leader?", "friend_of"),
]


def main():
    rows = []
    for style, template, relation in QUESTION_TEMPLATES:
        for entity in REAL_ENTITY_NAMES:
            query = template.format(e=entity)
            direction = detect_query_direction(query, entity, relation)
            hop_depth = estimate_hop_depth(query)
            rows.append({
                "style": style, "query": query, "entity": entity, "relation": relation,
                "detected_direction": direction, "estimated_hop_depth": hop_depth,
            })

    print(f"{'style':35} {'query':45} {'direction':10} {'hop_depth'}")
    for r in rows:
        print(f"{r['style']:35} {r['query']:45} {str(r['detected_direction']):10} {r['estimated_hop_depth']}")

    with open("direction_coverage_log.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    print(f"\n--- Coverage by phrasing style (fraction where direction was detected at all) ---")
    styles = {r["style"] for r in rows}
    for style in sorted(styles):
        style_rows = [r for r in rows if r["style"] == style]
        detected = sum(1 for r in style_rows if r["detected_direction"] is not None)
        print(f"  {style:35} {detected}/{len(style_rows)} detected")

    print(f"\nFull results written to direction_coverage_log.csv")


if __name__ == "__main__":
    main()
