# AMLens

AMLens stores source transactions in SQLite. Python graph algorithms and seven fixed SQL rules detect transaction structures offline.
The Streamlit dashboard replays the saved detection results.

## Rebuild from a Git checkout

Git stores source code, locked dependencies, and the data source manifest.
The `data/` directory contains local inputs, databases, and results. Git ignores this directory.
The normal setup does not need Git LFS or a ZIP archive.

1. Install [uv](https://docs.astral.sh/uv/getting-started/installation/).
2. Clone the repository.
3. Open a terminal in the project root directory.
4. Run these commands in order:

```text
uv sync --frozen
uv run --frozen python scripts/reproduce.py --download
uv run --frozen amlens --server.port=8513
```

5. Open `http://127.0.0.1:8513` in a browser.

Use the same commands in Windows PowerShell, macOS, or Linux.
The rebuild command downloads missing HI files and validates their sizes and SHA-256 hashes.
It imports the CSV files, runs detection, and compares all 1,221 evidence sets with the reference.
It also validates these final dashboard counts:

| Item | Count |
|---|---:|
| Source transactions | 5,078,345 |
| Detected transactions | 330 |
| Structure groups | 49 |

The recorded local detection run took approximately 14 minutes. The duration can change on another computer.
After setup, use only the final command to start the dashboard again.

The project specifies Python **3.13.15** in `.python-version`. uv uses this file to select the interpreter.
The `uv.lock` file specifies dependency versions, including `kagglehub==1.0.2`.
The first installation and data download need network access. Detection and replay can then run offline.
Keep at least **5 GB** of free disk space for input files, results, and temporary databases.

## Data source and repeatable results

The downloader uses [Kaggle dataset version 8](https://www.kaggle.com/datasets/ealtman2019/ibm-transactions-for-anti-money-laundering-aml/versions/8).
It requests only these files:

- `HI-Small_Trans.csv`
- `HI-Small_accounts.csv`
- `HI-Small_Patterns.txt`

The file `src/amlens/operations/reference_dataset.json` specifies the version, file sizes, and SHA-256 hashes.
The downloader keeps the two CSV files unchanged.
The version 8 Patterns file has one additional final LF byte compared with the local reference file.
The downloader validates the source hash, removes that byte, and validates the local reference hash.
It makes no other text or line-ending changes. Detection does not read the Patterns file.

If a file fails validation, the downloader stops.
It does not select a newer dataset version or change the expected hashes.
It reuses valid local files without network access. It does not replace existing files with different contents.
It downloads missing files to a temporary directory. It publishes them only after all downloads pass validation.
If a download fails, run the same command again.

Repeatable results mean equal input transactions, rules, transaction IDs, and evidence sets.
Creation times and operation durations can differ. Thus, repeated builds can produce SQLite files with different binary hashes.
If the specified dataset version becomes unavailable, the downloader stops with an error.
Keep validated source files for later offline rebuilds.

If Kaggle requires authentication, use the [official authentication instructions](https://github.com/Kaggle/kagglehub#authenticate).
Configure `KAGGLE_API_TOKEN` or `~/.kaggle/kaggle.json` on the local computer. Then run the command again.
Keep credentials out of source code, command arguments, and Git.
The ignore rules include `.env`, `.kaggle/`, and `kaggle.json`.

## Run separate operations

To download and validate the source files, run:

```text
uv run --frozen python scripts/download_data.py
uv run --frozen python scripts/check_environment.py
```

To rebuild the observation database from the two CSV files, run:

```text
uv run --frozen python scripts/prepare_data.py
```

To generate and validate detection results, run:

```text
uv run --frozen python scripts/detect_patterns.py
uv run --frozen python scripts/reproduce.py --verify-only
```

If the original files are available locally, run `reproduce.py` without `--download` for an offline rebuild.
To copy inputs from another directory, run:

```text
uv run --frozen python scripts/reproduce.py --raw-dir "path/to/raw-files"
```

To place downloaded inputs and generated results in another data directory, run:

```text
uv run --frozen python scripts/reproduce.py --download --data-dir "path/to/data"
```

To download only the original files to another directory, run:

```text
uv run --frozen python scripts/download_data.py --raw-dir "path/to/raw-files"
```

The default data directory is `data` under the source project root.
The working directory does not change this location.
A wheel installation uses the operating system's user data directory.
Use a source distribution or portable archive for a complete rebuild.

To select a different data directory for the dashboard, set `AMLENS_DATA_DIR` to that directory's absolute path.

Windows PowerShell:

```powershell
$env:AMLENS_DATA_DIR="D:\AMLens data"
```

macOS or Linux:

```sh
export AMLENS_DATA_DIR="/path/to/AMLens data"
```

The observation database is `data/processed/amlens.sqlite`.
The result database is `data/processed/detection.sqlite`.
Each operation prepares a temporary database before it replaces the existing database.
If detection fails after an import, the dashboard rejects results that do not match the new observation database.
Run detection again to produce matching results.

A complete rebuild saves its report to `data/processed/reproduction-report.json`.
The `--verify-only` option reads existing data. It does not download files, rebuild databases, or write a report.

## Create a portable archive

Use Git and the download script for normal project transfer.
To save source files, original data, and existing results together, run:

```text
uv run --frozen python scripts/export_portable.py --output "dist/amlens-portable.zip"
```

If the output file already exists, select a different file name. The export command does not replace existing archives.
Use `--without-results` to exclude result databases. Rebuild results after transfer.
The exporter validates every file in the completed archive.

To use an archive that includes results:

1. Extract the ZIP file.
2. Open a terminal in the extracted `amlens-app` directory.
3. Run these commands in order:

```text
uv sync --frozen
uv run --frozen python scripts/verify_bundle.py
uv run --frozen python scripts/reproduce.py --verify-only
uv run --frozen amlens --server.port=8513
```

4. Open `http://127.0.0.1:8513` in a browser.

A Git checkout has no `bundle-manifest.json`. Do not run `verify_bundle.py` in that checkout.
The archive excludes the local virtual environment, browser replay position, and browser review state.

## Module responsibilities

| Module | Responsibility |
|---|---|
| `scripts` | Read command arguments and start operations. |
| `ingestion` | Read CSV batches, convert values, and validate imports. |
| `db` | Manage SQLite connections, indexes, queries, and stored results. |
| `detection` | Find structures, calculate features, and apply rule versions. |
| `services` | Run detection, prepare dashboard data, and manage replay state. |
| `operations` | Download specified inputs, validate files, and create portable archives. |
| `presenters` | Convert application records to dashboard fields. |
| `components` | Connect HTML, CSS, and JavaScript files to Streamlit. |

The database and detection modules do not depend on Streamlit. The browser does not execute SQL.
Use `snake_case` names for Python modules and functions. Give each file one clear responsibility.
Reuse common algorithms for the same structure type.

## Detection operation

The rule version is `historical-demo-6ed874e77b60`.
The file `src/amlens/detection/frozen_ruleset.json` contains the rule configuration.
Detection uses code and resources from this project.

The import preserves source row numbers in both source tables.
The `paid_raw` and `received_raw` fields preserve the original amount precision.
The `paid` and `received` fields use DECIMAL(24,2) rounding and store integer hundredths of each currency unit.
The `nodes` table maps banks and accounts to node IDs. The `edges` view supplies transaction observations.

Detection runs at six-hour intervals. Each run uses historical windows of 48, 96, and 216 hours.
Account background features use all payment methods. Candidate structures use eligible ACH transactions.
The graph algorithms limit neighbor counts, path lengths, and search expansions. Run statistics record these limits and excluded branches.

SQLite applies seven fixed selection rules to complete candidates.
Related tables store candidate features and transaction members.
The result database stores structure groups, first detection times, evidence versions, and transaction members.
It keeps each evidence version unchanged and does not store the same evidence twice.

Source timestamps have no time zone. The application uses the source local time without conversion.
Each time window includes its start and excludes its cutoff: `[window_start, cutoff)`.
Two identical source rows remain two separate transactions.
The observation database excludes evaluation labels. Detection does not read the Patterns file.

| Rule | Unique detected transactions across the full history |
|---|---:|
| FAN-IN | 27 |
| FAN-OUT | 47 |
| CYCLE | 76 |
| GATHER-SCATTER | 89 |
| SCATTER-GATHER | 60 |
| STACK | 25 |
| RANDOM | 21 |
| All rules, without duplicate transactions | 330 |

A transaction can match more than one rule. Do not add the rule counts to calculate the total.
BIPARTITE is inactive. The dashboard shows this state.
The 1,221 evidence sets belong to 49 structure groups.
These results support historical replay validation. The project has not established prediction performance on unseen data.

The recorded full SQLite detection run took **832.65 seconds** and generated **3,787,421 candidate snapshots**.
Its transaction IDs and evidence members matched the reference results.
The recorded load and final dashboard preparation took approximately **0.16 seconds**.

## Dashboard behavior

The dashboard keeps its Chinese and English text, page layout, fonts, and chart styles.
The file `docs/frontend-baseline.json` records frontend hashes and authorized changes.

Replay moves forward from start to end. The available speeds are 900×, 3,600×, 14,400×, and 28,800×.
Date changes, reverse replay, seeking, and position restoration are inactive.
Case inspection does not pause replay. Replay includes the final detection cutoff.

The queue includes every visible structure.
Each structure shows its latest complete evidence version at the current replay time.
The application does not combine members from different versions.
For versions from the same batch, it first selects the version with the latest evidence end time.
If end times are equal, it selects the version with more transactions. Case ID resolves any remaining tie.
The dashboard does not show evidence from a later cutoff.

New evidence returns a reviewed structure to the review queue.
Review state belongs to the current browser session.
The processed count uses the full transaction timeline. The review count counts each visible evidence transaction once.
The dashboard shows amounts separately for each currency.

## Validation

To run the project checks, execute:

```sh
uv sync --frozen --extra dev
uv run --frozen --extra dev python -m unittest discover -s tests -t . -v
uv run --frozen --extra dev ruff check .
uv run --frozen --extra dev ruff format --check .
node tests/frontend/review_queue.test.cjs
```

The final command needs Node.js and does tests for the frontend event queue.
Application operation does not need Node.js.

Import and detection summaries are in `data/processed`.
The file `docs/validation.json` records counts, transaction IDs, evidence comparisons, node mappings, and frontend checks.
If required data is absent or databases do not match, the dashboard shows data preparation instructions.

To compare existing detection results with the reference evidence, run:

```sh
uv run --frozen python scripts/verify_detection.py
```

The reference file is `tests/reference/expected-detection.json`.
Detection and the dashboard do not read this file. It serves only as a validation reference.
The file `tests/reference/README.md` explains the reference records and their use.
The files `docs/ingestion-validation.json` and `docs/query-validation.json` retain earlier migration comparisons.
Commands in those historical records are not setup requirements for a new computer.

Tests cover directory changes, paths with spaces or Chinese characters, environment data paths, damaged inputs, downloads, and archive contents.
The workflow in `.github/workflows/portable-checks.yml` defines checks for Windows, macOS, and Linux.
A local test pass does not establish a pass on all three remote systems.

## Project terms

| Term | Meaning |
|---|---|
| Candidate | A complete transaction structure before SQL rule selection. |
| Cutoff | The exclusive end time of one detection batch. |
| Evidence set | The complete transaction members of one selected candidate. |
| Evidence version | One saved evidence set and its first detection time. |
| Structure group | Related evidence versions with common structural accounts. |
| Ruleset | The versioned collection of detection rules and search limits. |
| Replay | Display of saved results in detection time order. |
| Reference | Fixed evidence records for result comparison. |
| Manifest | A file that lists expected files and their properties. |
