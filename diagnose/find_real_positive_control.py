"""Find a REAL, verified 2-hop chain in the actual graph, to use as a
proper positive control - not a guessed one.

Searches for entity1 -R1-> entity2 -R2-> entity3 where R1 and R2 both
have a verified direction template (so estimate_hop_depth will
recognize the resulting question as needing hop_depth=1), then prints
a ready-to-use question phrased in the confirmed-working style.

Fix vs. previous version:
  - no early cap at 10 before filtering (that hid most candidates)
  - dedupe identical (a, rel1, b, rel2, c) chains
  - surface hop_depth for each passing candidate so the filter is visible
"""

from pathlib import Path

from embedding.relation_text import MANUAL_TEMPLATES
from graph.corpus import load_corpus
from retrieval.direction_detection import estimate_hop_depth

DATA_DIR = Path("data")
BOOK_ID = "106"
MAX_TO_PRINT = 20


def main():
    corpus = load_corpus(DATA_DIR / "graphs" / "corpus.pkl")
    graph = corpus.get(BOOK_ID)
    if graph is None:
        print(f"No graph for book {BOOK_ID}")
        return

    seen = set()
    candidates = []
    for a in graph.nodes:
        for _, b, data1 in graph.edges(a, data=True):
            rel1 = data1.get("relation")
            if rel1 not in MANUAL_TEMPLATES:
                continue
            for _, c, data2 in graph.edges(b, data=True):
                rel2 = data2.get("relation")
                if rel2 not in MANUAL_TEMPLATES or c == a:
                    continue
                key = (a, rel1, b, rel2, c)
                if key in seen:
                    continue
                seen.add(key)
                candidates.append(key)

    print(f"Collected {len(candidates)} unique templated 2-hop chains "
          f"in book {BOOK_ID}\n")

    if not candidates:
        print("No 2-hop chain through two templated relations in this "
              "book's graph at all - worth knowing on its own.")
        return

    passed = []
    failed = []
    for a, rel1, b, rel2, c in candidates:
        noun2 = rel2.replace("_of", "").replace("_", " ")
        question = f"Who is the {noun2} of the " \
                   f"{rel1.replace('_of', '').replace('_', ' ')} of {a}?"
        h = estimate_hop_depth(question)
        if h < 1:
            failed.append((question, h))
            continue
        passed.append((a, rel1, b, rel2, c, question, h))

    print(f"Passing hop_depth >= 1: {len(passed)} / {len(candidates)}")
    if failed:
        print(f"Rejected (hop_depth < 1): {len(failed)}")
        for q, h in failed[:5]:
            print(f"   hop_depth={h}  {q!r}")
        if len(failed) > 5:
            print(f"   ... and {len(failed) - 5} more")
    print()

    if not passed:
        print("No candidate produced hop_depth >= 1 - the phrasing style "
              "generated here isn't recognized by estimate_hop_depth. "
              "The graph chains exist, but the question generator needs "
              "adjusting before this can serve as a positive control.")
        return

    print("Ready-to-use positive controls:\n")
    for a, rel1, b, rel2, c, question, h in passed[:MAX_TO_PRINT]:
        print(f"  {a} -{rel1}-> {b} -{rel2}-> {c}")
        print(f"  Suggested question: {question!r}  (hop_depth={h})")
        print(f"  Expected chain endpoint: {c!r}\n")


if __name__ == "__main__":
    main()