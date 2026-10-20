-- Apply ruleset historical-demo-6ed874e77b60 to features of complete structures.
SELECT * FROM candidate_features
WHERE family = 'GATHER-SCATTER'
  AND "currencies" <= 6
  AND "span_hours" <= 90
  AND "currency_switches" >= 50
ORDER BY candidate_ordinal;
