-- Apply ruleset historical-demo-6ed874e77b60 to features of complete structures.
SELECT * FROM candidate_features
WHERE family = 'FAN-IN'
  AND "edges" >= 11
  AND "max_pair_repeats" <= 1
  AND "max_background_incidence" >= 159
ORDER BY candidate_ordinal;
