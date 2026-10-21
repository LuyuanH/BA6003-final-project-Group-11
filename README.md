# AMLens

AMLens is a tool for anti-money laundering analysis of transaction structures.
It stores transactions in SQLite.
Python graph algorithms and seven fixed SQL rules detect transaction structures without an internet connection.
A Streamlit dashboard replays detection evidence in historical time for manual case review.

Optional artificial intelligence (AI) examines case evidence and gives dashboard summaries.

## Setup

### Requirements

- Install [Git](https://git-scm.com/downloads).
- Install [uv](https://docs.astral.sh/uv/getting-started/installation/).
- Keep a minimum of **5 GB** of free disk space for source files, results, and temporary databases.

The specified Python version in `.python-version` is **3.13**.
The environment selects an available Python 3.13 patch release.
uv uses this file to select the interpreter.
An internet connection is necessary for the first dependency installation and data download.
Use the commands below with Windows PowerShell, macOS, or Linux.

The default data comes from [Kaggle dataset version 8](https://www.kaggle.com/datasets/ealtman2019/ibm-transactions-for-anti-money-laundering-aml/versions/8).
The downloader compares file sizes and SHA-256 hashes with the [source manifest](src/amlens/operations/reference_dataset.json).
Source files, databases, and results stay in `data/` in the project root directory.
Git does not track these files.

### First installation

1. Clone the repository:

   ```text
   git clone https://github.com/LuyuanH/BA6003-final-project-Group-11.git
   ```

2. Go to the project directory:

   ```text
   cd BA6003-final-project-Group-11
   ```

3. Install the dependencies at their locked versions:

   ```text
   uv sync --frozen
   ```

4. Prepare the data:

   If authentication is necessary for Kaggle, first use the [official authentication instructions](https://github.com/Kaggle/kagglehub#authenticate).
   Set `KAGGLE_API_TOKEN` locally, or make `~/.kaggle/kaggle.json`.
   Do not put credentials in source code, command arguments, or Git.

   ```text
   uv run --frozen python scripts/reproduce.py --download
   ```

   This command downloads the source files, verifies them, imports transactions, runs detection, and compares the results with reference evidence.
   The command stops after data preparation.
   A previous local record gives approximately **14 minutes** for detection.
   The full installation time changes with computer performance and download speed.

### Configure AI analysis

This procedure is optional.
The dashboard and manual review stay available without AI configuration.
If you do not configure AI, the analysis cards show configuration instructions.

Select the full ID of an OpenRouter model with support for JSON Schema structured outputs.
The application uses only providers with support for the request parameters.
It does not select a different model automatically.
See [OpenRouter structured outputs](https://openrouter.ai/docs/guides/features/structured-outputs) for the requirements.

Do not put API keys in Git, browser code, or logs that other persons can read.
Git and project exports do not include local `.env` files.
They keep only example files without credentials.

1. Copy [`.env.example`](.env.example) to `.env` in the project root directory, next to `pyproject.toml`.
2. Set the API key and model ID in `.env`:

   ```dotenv
   OPENROUTER_API_KEY="your-local-key"
   AMLENS_AI_MODEL="provider/model-id"
   ```

3. Replace the two placeholder values locally.

Use the same `.env` format on Windows, macOS, and Linux.
After configuration, start the dashboard with the command in the next section.

### Start the dashboard

If there are no errors from data preparation, run this command from the project root directory:

```text
uv run --frozen amlens --server.port=8513
```

Open [http://127.0.0.1:8513](http://127.0.0.1:8513) in a browser.

To start the dashboard again, run only the start command in this section.
No internet connection is necessary for detection or replay.
An internet connection is necessary for AI analysis.

### Deploy to Streamlit Community Cloud

The repository includes `deployment/replay.json.gz` for cloud deployment.
This snapshot contains all saved evidence, its transaction and account data, and the full timeline of transaction counts.
It represents 5,078,345 source transactions, 330 evidence transactions, 49 structure groups, and 1,221 evidence versions.
The compressed snapshot is approximately 183 KB.
The local data download and detection steps above are not necessary for cloud deployment.

Administrator access to the GitHub repository is necessary for deployment.
For a private repository, first connect private repository access in Streamlit under **Settings > Linked accounts**.
Examine the requested GitHub permissions before authorization.
See [GitHub connection requirements](https://docs.streamlit.io/deploy/streamlit-community-cloud/get-started/connect-your-github-account).

1. Open [Streamlit Community Cloud](https://share.streamlit.io/).
2. Select **Create app**. Then, select **Yup, I have an app**.
3. Enter these values:

   | Field | Value |
   | --- | --- |
   | Repository | `LuyuanH/BA6003-final-project-Group-11` |
   | Branch | `main` |
   | Main file path | `streamlit_app.py` |

4. Open **Advanced settings**. Select Python **3.13**.
5. For AI analysis, enter these root-level values in **Secrets**:

   ```toml
   OPENROUTER_API_KEY = "your-cloud-key"
   AMLENS_AI_MODEL = "provider/model-id"
   ```

   Replace the placeholders with your key and the model ID from [Configure AI analysis](#configure-ai-analysis).
   Streamlit makes root-level secrets available as environment variables.
   Do not commit `.streamlit/secrets.toml` or `.env`.
   Without these values, replay and manual review stay available.

6. Select **Save**. Then, select **Deploy**.
7. Examine the application logs for startup errors.
8. After replay reaches a detection time, open a case. Do a test of AI analysis.

Community Cloud installs dependencies from `uv.lock`.
The cloud entry point reads only the committed snapshot.
It does not download source data or run detection.
Reviews and AI results stay in the active session.
Reconnection or restart can remove these results.
See the official [deployment instructions](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy) and [dependency rules](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/app-dependencies).

To open the cloud entry point locally, run:

```text
uv run --frozen streamlit run streamlit_app.py --server.address=127.0.0.1 --server.port=8514
```

If local detection stops without errors, update cloud data with these steps:

1. Export the verified databases:

   ```text
   uv run --frozen python scripts/export_replay.py
   ```

   The exporter examines database compatibility and snapshot integrity before it replaces the previous snapshot.
   The exporter stops with an error if:

   - Detection is not completed.
   - Source versions are different.
   - Replay references contain errors.

   The reader accepts snapshot format version 1.
   The maximum size for uncompressed JSON is 64 MiB.

2. Commit `deployment/replay.json.gz`. Push the commit to the deployment branch.
3. Examine the updated application in Community Cloud.

If the application reports unavailable replay data, export the snapshot again.
Commit the snapshot.
For AI authentication, credit, or model errors, correct the Secrets values or provider configuration.
Run the analysis again.

## Documentation

| Document | Contents |
| --- | --- |
| [Dashboard use](docs/dashboard.md) | Language selection, replay, evidence versions, and manual review |
| [Architecture and detection](docs/architecture.md) | Module functions, detection rules, data flow, and project terms |
