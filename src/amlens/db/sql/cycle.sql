-- Apply ruleset historical-demo-6ed874e77b60 to features of complete structures.
SELECT * FROM candidate_features
WHERE family = 'CYCLE'
  AND "span_hours" <= 168
  AND "min_role_ach_fraction" <= 0.3
  AND "min_background_incidence" >= 53
ORDER BY candidate_ordinal;
