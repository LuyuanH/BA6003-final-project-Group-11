SELECT c.family AS pattern,
       COUNT(DISTINCT m.transaction_id) AS transaction_count,
       COUNT(DISTINCT c.case_id) AS evidence_set_count
FROM selected_candidates s
JOIN candidate_features c USING (candidate_ordinal)
JOIN candidate_members m USING (candidate_ordinal)
GROUP BY c.family
ORDER BY c.family;
