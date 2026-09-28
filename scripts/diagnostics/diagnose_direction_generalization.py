"""Generalization test for direction_detection.py fixes (session
2, following the Felix Holt/40882 diagnosis).

Tests detect_query_direction/entity_to_expand_from/target_relation
DIRECTLY against real graph triples, bypassing hybrid_search's vector
retrieval - isolates the module under test from vector-recall
confounds (yesterday's Bug C: wrong-relation-type hits) so a failure
here means direction detection, not retrieval.

Pre-registered pass/fail criterion (not "does it break"):
- Resolution rate = fraction of generated questions where
  entity_to_expand_from returns non-None.
- Failures are bucketed as EXPECTED (same phrasing families already
  known to be gaps: coordinated possessors, un-synonymed relations,
  untemplated relations) vs NEW (anything else) - a new-family failure
  is the signal worth acting on, not the raw resolution rate alone,
  since different books will have different relation-type mixes.

Axes stressed per book (see session log for why each was picked):
  12753  - title/honorific-prefixed entities (Sir, King, Lord, Queen)
  47634  - modern English kinship density, different author/era
  52617  - translated work (distribution shift)
  73548  - translated work, mythological/compound names
  40882  - baseline (yesterday's book, fixes were built against it)
  106    - positive control (unrelated relation family: companion_of/
           enemy_of, not kinship - sanity check the fixes didn't
           regress anything outside kinship relations)
"""

import csv
import re
from collections import defaultdict
from pathlib import Path

from embedding.relation_text import MANUAL_TEMPLATES, get_anchor_phrase
from graph.corpus import load_corpus
from retrieval.direction_detection import (
    NOUN_SYNONYMS,
    detect_query_direction,
    entity_to_expand_from,
    target_relation,
)

DATA_DIR = Path("data")

BOOKS = {
    "12753": "King Arthur",
    "47634": "Sons and Lovers",
    "52617": "Decameron",
    "73548": "Rhinegold",
    "40882": "Felix Holt (baseline)",
    "106": "Tarzan (positive control)",
}

# Relation types this fix session actually touched - the ones worth
# stress-testing for generalization. companion_of/enemy_of included
# for 106 as a non-kinship sanity check (should already work, per
# yesterday's positive control - if IT regresses on a new book, the
# problem isn't kinship-specific).
KINSHIP_RELATIONS = {
    "parent_mother_of", "parent_father_of", "child_of",
    "sibling_of", "spouse_of", "relative_of", "adopted_by",
}
CONTROL_RELATIONS = {"companion_of", "enemy_of", "friend_of"}
TARGET_RELATIONS = KINSHIP_RELATIONS | CONTROL_RELATIONS

TITLE_PATTERN = re.compile(
    r"^(sir|king|queen|lord|lady|prince|princess|dr\.?|mr\.?|mrs\.?|miss)\s+", re.IGNORECASE
)
PARTICLE_PATTERN = re.compile(r"\b(van|von|de|di|du|der|le|la)\s+", re.IGNORECASE)


def classify_axis(entity: str) -> str:
    if TITLE_PATTERN.search(entity):
        return "title"
    if PARTICLE_PATTERN.search(entity):
        return "particle"
    if len(entity.split()) >= 3:
        return "multiword"
    return "plain"


def sample_kinship_edges(graph, max_per_relation: int = 8):
    """Real (e1, e2, relation) triples for TARGET_RELATIONS, capped
    per relation type so one dense relation doesn't dominate the
    sample - mirrors the corpus-wide sampling discipline used in
    Week 5's EVNT audit (cap, don't exhaustively enumerate)."""
    by_relation = defaultdict(list)
    for u, v, data in graph.edges(data=True):
        rel = data.get("relation")
        if rel in TARGET_RELATIONS and len(by_relation[rel]) < max_per_relation:
            by_relation[rel].append((u, v))
    return by_relation


def build_questions(e1: str, e2: str, relation: str):
    """Two possessive-style questions per edge, testing both known
    boundary/synonym fixes from yesterday:
      Q1 - anchor noun directly, asked from e2's side
           ("Who is {e2}'s {anchor_noun}?") - tests the possessive-
           boundary tolerance fix (title/particle-prefixed e2).
      Q2 - synonym noun, asked from e1's side
           ("Who is {e1}'s {synonym_noun}?") - tests the
           NOUN_SYNONYMS fix; skipped if no synonym exists for this
           relation (expected, not a failure - logged separately).
    Returns a list of (question_text, which_entity_is_test_subject).
    """
    questions = []
    anchor = get_anchor_phrase(relation)
    if anchor:
        words = anchor.split()
        anchor_noun = words[1] if words[0] in ("a", "an", "the") else words[0]
        questions.append((f"Who is {e2}'s {anchor_noun}?", e2, "anchor_noun"))
    synonyms = NOUN_SYNONYMS.get(relation, [])
    if synonyms:
        questions.append((f"Who is {e1}'s {synonyms[0]}?", e1, "synonym_noun"))
    return questions


def build_coordinated_possessor_question(graph, relation: str):
    """'X and Y's <noun>' - two entities sharing the same e2 (e.g. two
    children of the same parent) via the same relation. Tests the
    KNOWN, LOGGED limitation from yesterday's fix - expected to
    misattribute, not a new failure if it does. Returns None if no
    such pair exists in this book for this relation."""
    by_target = defaultdict(list)
    for u, v, data in graph.edges(data=True):
        if data.get("relation") == relation:
            by_target[v].append(u)
    for target, sources in by_target.items():
        if len(sources) >= 2:
            anchor = get_anchor_phrase(relation)
            if not anchor:
                continue
            words = anchor.split()
            anchor_noun = words[1] if words[0] in ("a", "an", "the") else words[0]
            q = f"Who is {sources[0]} and {sources[1]}'s {anchor_noun}?"
            return q, sources[0], sources[1], target
    return None


def bucket_failure(relation: str, question_kind: str, has_synonym: bool) -> str:
    """EXPECTED = matches a gap already known and logged from
    yesterday's session. NEW = anything else - the actual signal this
    script exists to find."""
    if question_kind == "synonym_noun" and not has_synonym:
        return "EXPECTED (no NOUN_SYNONYMS entry for this relation)"
    if relation not in MANUAL_TEMPLATES:
        return "EXPECTED (untemplated relation)"
    return "NEW"


def run_book(book_id: str, label: str, corpus, writer):
    graph = corpus.get(book_id)
    if graph is None:
        print(f"\n=== {label} ({book_id}): NOT IN CORPUS - skipping ===")
        return None

    by_relation = sample_kinship_edges(graph)
    total = resolved = 0
    new_failures = []

    print(f"\n=== {label} ({book_id}) ===")
    for relation, pairs in by_relation.items():
        for e1, e2 in pairs:
            for question, subject, kind in build_questions(e1, e2, relation):
                total += 1
                expand = entity_to_expand_from(question, e1, e2, relation)
                t_rel = target_relation(question)
                axis = classify_axis(subject)
                ok = expand is not None
                resolved += int(ok)
                row = {
                    "book": label, "book_id": book_id, "relation": relation,
                    "question": question, "axis": axis, "kind": kind,
                    "expand_from": expand, "target_relation": t_rel,
                    "resolved": ok,
                }
                if not ok:
                    has_syn = bool(NOUN_SYNONYMS.get(relation))
                    row["failure_bucket"] = bucket_failure(relation, kind, has_syn)
                    if row["failure_bucket"] == "NEW":
                        new_failures.append(row)
                writer.writerow(row)

        # Coordinated-possessor probe, once per relation present in this book
        coord = build_coordinated_possessor_question(graph, relation)
        if coord:
            q, a, b, target = coord
            total += 1
            expand = entity_to_expand_from(q, a, target, relation)
            ok = expand is not None
            resolved += int(ok)
            row = {
                "book": label, "book_id": book_id, "relation": relation,
                "question": q, "axis": "coordinated", "kind": "coordinated_possessor",
                "expand_from": expand, "target_relation": target_relation(q),
                "resolved": ok,
                "failure_bucket": "EXPECTED (known coordinated-possessor limitation)" if not ok else "",
            }
            writer.writerow(row)

    rate = resolved / total if total else float("nan")
    print(f"  resolution rate: {resolved}/{total} = {rate:.1%}")
    if new_failures:
        print(f"  {len(new_failures)} NEW-family failures:")
        for f in new_failures[:10]:
            print(f"    [{f['axis']}] {f['question']!r} (relation={f['relation']})")
    return {"book": label, "resolved": resolved, "total": total, "rate": rate,
            "new_failures": len(new_failures)}


def main():
    corpus = load_corpus(DATA_DIR / "graphs" / "corpus.pkl")
    with open("direction_generalization.csv", "w", newline="") as f:
        fieldnames = ["book", "book_id", "relation", "question", "axis", "kind",
                      "expand_from", "target_relation", "resolved", "failure_bucket"]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        summary = [run_book(bid, label, corpus, writer) for bid, label in BOOKS.items()]

    print("\n=== Summary ===")
    for s in summary:
        if s:
            print(f"  {s['book']}: {s['resolved']}/{s['total']} = {s['rate']:.1%}"
                  f"  ({s['new_failures']} new-family failures)")
    print("\nWritten to direction_generalization.csv")


if __name__ == "__main__":
    main()