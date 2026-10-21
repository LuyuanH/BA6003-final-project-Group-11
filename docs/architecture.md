# Architecture and detection

[Go to README](../README.md)

AMLens runs data import, offline detection, and dashboard replay independently.
The dashboard reads stored results.
It does not start detection.

## Data flow and module boundaries

1. `operations` downloads the specified source files and examines them.
2. `ingestion` reads CSV batches and writes the observation database, `data/processed/amlens.sqlite`.
3. `detection` uses Python graph algorithms to create candidates and calculate features. It then uses fixed rules through SQLite.
4. `services` schedules detection and writes evidence and detection times to `data/processed/detection.sqlite`.
5. The replay service reads the two databases. `presenters` prepares interface data, and `components` shows the data.

`db` manages database connections, queries, and result storage.
The database and detection modules operate without Streamlit.
The browser does not execute SQL.

`analysis` reads evidence or an overview snapshot available at the replay time.
It calls OpenRouter and examines the report.
AI results stay only in the active Streamlit session.
The application does not write AI results to the detection database or change manual review decisions.

## Observation data

The import process keeps source row numbers.
`paid_raw` and `received_raw` keep the source precision of transaction amounts.
`paid` and `received` use DECIMAL(24,2) rounding and store integers in units of one hundredth of the currency unit.
Two source records with the same content stay two transactions.

The `nodes` table maps banks and accounts to node IDs.
The `edges` view gives transaction observations.
Source timestamps have no time zone.
The application uses the local time in the source file without time zone conversion.

The observation database contains no evaluation labels.
Detection does not read Patterns files.
The reference comparison shows historical reproduction only.
It does not show prediction performance on data that the reference run does not include.

## Detection rules and windows

The rule version is `historical-demo-6ed874e77b60`.
See the [fixed ruleset](../src/amlens/detection/frozen_ruleset.json) for the configuration.
The ruleset uses these rules:

- FAN-IN
- FAN-OUT
- CYCLE
- GATHER-SCATTER
- SCATTER-GATHER
- STACK
- RANDOM

The ruleset does not use BIPARTITE.

Detection runs at intervals of 6 hours with historical windows of 48, 96, and 216 hours.
Each window includes the start time but does not include the cutoff: `[window_start, cutoff)`.

Account background features use all payment methods.
Candidates use ACH transactions that meet the selection conditions.
Graph algorithms use limits for neighbor counts, path lengths, and search expansions.
Run statistics record these limits and the branches that the search does not examine.

## Evidence and database consistency

The result database stores structure groups, first detection times, evidence versions, and transaction members.
The application does not change stored evidence versions.
The database stores only one copy of each evidence set.
Replay shows only the last full version available at the replay time.
It does not put transaction members from different versions together.

Import and detection write temporary databases before they replace previous databases.
Previous detection results are not always compatible with an updated observation database.
The dashboard rejects results that are not compatible with the observation database.
If the dashboard rejects the results, run detection again.

See [Detection reference evidence](../tests/reference/README.md) for the source of the reference evidence and the comparison procedure.

## Project terms

| Term | Definition |
| --- | --- |
| Candidate | A full transaction structure before SQL rule selection |
| Cutoff | The end boundary of a detection batch, not part of that batch's window |
| Evidence set | All transaction members of one selected candidate |
| Evidence version | A stored evidence set with its first detection time |
| Structure group | A set of evidence versions with the same key accounts in the structure |
| Ruleset | A set of detection rules and search limits with a version ID |
