# Detection reference

The file `expected-detection.json` contains the reference evidence from the completed `pattern-demo-lab` SQL recount.
It contains 1,221 unique `(rule_id, case_id)` evidence sets and their original CSV transaction row IDs.
It contains no raw account details or transaction labels.
Detection and the dashboard do not read this file.

The reference run used ruleset `historical-demo-6ed874e77b60`.
It used 71 cutoffs at six-hour intervals, from `2022-09-01 06:00:00` to `2022-09-18 18:00:00`.
Each cutoff used windows of 48, 96, and 216 hours.
The run calculated candidates from 5,078,345 source transactions.
The selected evidence contains 330 unique transactions across seven active pattern families.
The file `provenance.json` records source and output hashes.
Its paths identify historical files. They are not runtime dependencies.

To validate detection results:

1. Install the project dependencies.
2. Prepare the source data.
3. Run detection.
4. Run the reference comparison:

```sh
python scripts/verify_detection.py
```

This comparison does not need the old project, DuckDB, Parquet support, or the ignored artifacts directory.
Use `--database path/to/detection.sqlite` to select another result database.
Use `--reference` to select another export of the same reference evidence.
JSON spacing, record order, and member order can differ.
The verifier compares a canonical SHA-256 hash. It rejects missing, duplicate, or changed reference evidence.
If validation fails, the command returns a JSON report and exit status 1.

The reference export uses `results/sql_recount/selected_evidence.parquet`.
The source query is:

```sql
SELECT DISTINCT rule_id, family, case_id, transaction_ids
FROM selected_candidates
ORDER BY rule_id, case_id;
```

To establish a revised detector reference:

1. Run the separate reference implementation.
2. Export its selected evidence.
3. Review the changed transaction sets and source records.
4. Update the reference file and verifier expectations together.

Do not use the implementation under test to replace reference evidence only to obtain a passing result.

This reference validates historical reproduction. It does not establish prediction performance on unseen data.
Source distributions exclude raw CSV files and generated SQLite databases.
Obtain the matching inputs and rebuild the databases locally.
