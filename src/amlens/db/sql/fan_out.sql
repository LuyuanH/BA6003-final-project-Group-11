-- Apply ruleset historical-demo-6ed874e77b60 to features of complete structures.
SELECT * FROM candidate_features
WHERE family = 'FAN-OUT'
  AND "nodes" >= 5
  AND "span_hours" <= 12
  AND "min_role_ach_fraction" >= 1
ORDER BY candidate_ordinal;
