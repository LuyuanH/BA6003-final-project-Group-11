-- Apply ruleset historical-demo-6ed874e77b60 to features of complete structures.
SELECT * FROM candidate_features
WHERE family = 'RANDOM'
  AND "span_hours" <= 30
  AND "mean_role_ach_fraction" <= 0.35
  AND "compatible_pairs" >= 3
ORDER BY candidate_ordinal;
