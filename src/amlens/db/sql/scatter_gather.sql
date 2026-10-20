-- Apply ruleset historical-demo-6ed874e77b60 to features of complete structures.
SELECT * FROM candidate_features
WHERE family = 'SCATTER-GATHER'
  AND "edges" >= 12
  AND "mean_role_ach_fraction" >= 0.5
  AND "edge_node_ratio" <= 1.5
ORDER BY candidate_ordinal;
