import pandas as pd
from retrieval.direction_detection import estimate_hop_depth, target_relation
from ..diagnostics.generate_positive_controls import build_index, step
from pathlib import Path

df = pd.read_csv("yardstick_results.csv", encoding="cp1252")
seqs = df.sequence.str.split(" > ").apply(lambda s: [x.split(":")[0] for x in s])
targ = df.question.map(target_relation)

df["hop_depth"] = df.question.map(estimate_hop_depth)
df["target_none"] = targ.isna()
df["target_wrong"] = targ.notna() & (targ != seqs.str[-1])   # last step = outermost
df["same_relation"] = seqs.map(lambda s: len(set(s)) < len(s))

# Funnel order: G1 > G2 > G3, everything else "passed parse gates"
df["gate"] = "passed parse gates"
df.loc[df.target_wrong, "gate"] = "G3 target_relation wrong"
df.loc[df.target_none, "gate"] = "G2 target_relation None"
df.loc[df.hop_depth == 0, "gate"] = "G1 hop_depth 0"


def show(frame, key, title):
    t = pd.crosstab(key, frame.outcome, normalize="index").mul(100).round(1)
    t["n"] = key.value_counts()
    print(f"\n-- {title} --\n{t.to_string()}")


show(df, df.gate, "parse-stage gate")
show(df, df.same_relation, "same relation twice")
show(df, pd.qcut(df.anchor_degree, 4, duplicates="drop"), "anchor degree quartile")

answered = df[df.n_answers > 0]
hits = df[df.outcome == "HIT"]
print(f"\nHITs with precision < 1: {(hits.precision < 1).mean():.1%}")
print(f"median n_answers when answered: {answered.n_answers.median()}")

clean = df[df.unique & (df.gold_nameable_frac == 1)]
show(clean, clean.gate, "clean subset (unique gold, all nameable) by gate")
clean = df[df.unique & (df.gold_nameable_frac == 1) & (df.gate == "passed parse gates")]
h = clean[clean.outcome == "HIT"]
print(f"pure HIT: {(h.precision == 1).sum()}/{len(clean)}  "
      f"<=2 answers: {(h.n_answers <= 2).sum()}/{len(clean)}")

m = df[(df.anchor == "mrs. transome") & df.sequence.str.startswith("parent_mother_of:e2")]
print(m[["question", "gold", "answers", "outcome"]].to_string())  # may be empty: cap-sampled out

clean = df[(df.gate == "passed parse gates")]
t = clean.groupby("first_step_retrieved").outcome.value_counts(normalize=True).mul(100).round(1)
print(t)
print(clean.first_step_retrieved.value_counts()) 

from graph.corpus import load_corpus
corpus = load_corpus(Path("data/graphs/corpus.pkl"))
graph = corpus.get("40882")
index = build_index(graph)  # from the yardstick script
frontier = step(index, "mrs. transome", "parent_mother_of", "e2")
print(frontier)