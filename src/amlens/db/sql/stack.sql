-- Apply ruleset historical-demo-6ed874e77b60 to features of complete structures.
SELECT * FROM candidate_features
WHERE family = 'STACK'
  AND "span_hours" <= 18
  AND "min_role_ach_fraction" <= 0.35
  AND "internal_max_background" <= 2
ORDER BY candidate_ordinal;
