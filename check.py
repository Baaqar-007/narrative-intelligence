import pandas as pd

before = pd.read_csv("yardstick_old_is_nameable.csv").set_index(["book_id", "question"])
only_old = before.index.difference(
    pd.read_csv("yardstick_current_is_nameable.csv").set_index(["book_id", "question"]).index
)
lost_hits = before.loc[only_old].query("outcome == 'HIT'")
print(f"lost HITs: {len(lost_hits)}")
print(f"  of which pure (precision == 1): {(lost_hits.precision == 1).sum()}")
print(f"  of which unique gold answer:    {lost_hits.unique.sum()}")
print(f"  median gold_size:               {lost_hits.gold_size.median()}")
print(f"\nfor comparison, same stats on the FULL old population's HITs:")
all_hits = before.query("outcome == 'HIT'")
print(f"  pure: {(all_hits.precision == 1).mean():.1%}, unique gold: {all_hits.unique.mean():.1%}, "
      f"median gold_size: {all_hits.gold_size.median()}")