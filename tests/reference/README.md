# Detection reference evidence

[Go to README](../../README.md)

## Contents and source

`expected-detection.json` stores reference evidence from the completed SQL recount in `pattern-demo-lab`.
It contains 1,221 unique `(rule_id, case_id)` evidence sets and the source row IDs of CSV transactions.
The file contains no raw account data or transaction labels.
Detection and the dashboard do not read this file.

The reference run used ruleset `historical-demo-6ed874e77b60`.
It used 71 cutoffs at intervals of 6 hours, from `2022-09-01 06:00:00` to `2022-09-18 18:00:00`.
Each cutoff used windows of 48, 96, and 216 hours.
Candidates came from 5,078,345 source transactions.
The selected evidence contains 330 unique transactions across seven enabled patterns.

`provenance.json` records source and output hashes.
Its paths identify historical files.
These files are not runtime dependencies.

## Compare detection results

First, complete [First installation in the README](../../README.md#first-installation) to build the observation database and detection results.

Run the reference comparison from the project root directory:

```sh
python scripts/verify_detection.py
```

The previous project, DuckDB, Parquet support, and the artifacts directory that Git ignores are not necessary for the comparison.
Use `--database path/to/detection.sqlite` to select a different result database.
Use `--reference` to select a different export of the same reference evidence.

JSON whitespace, record order, and member order can be different.
The verifier compares normalized SHA-256 hashes.
It rejects missing, duplicate, or changed reference evidence.
If verification finds errors, the command gives a JSON report and exits with status 1.

## Reference evidence export

The reference export used `results/sql_recount/selected_evidence.parquet` and this source query:

```sql
SELECT DISTINCT rule_id, family, case_id, transaction_ids
FROM selected_candidates
ORDER BY rule_id, case_id;
```

## Update the detection reference

Do not replace reference evidence with results from the implementation under test only to stop test failures.
For a new reference, use this sequence:

1. Run a reference implementation that operates independently of the implementation under test.
2. Export the selected evidence.
3. Examine the changed transaction sets and source records.
4. Update the reference files and the verifier's specified values together.

The reference evidence shows historical reproduction only.
It does not show prediction performance on data that the reference run does not include.
Source distributions do not include raw CSV files or SQLite databases from data preparation.
Get the matching inputs.
Rebuild the databases locally.
