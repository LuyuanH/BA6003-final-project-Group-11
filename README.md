# AMLens

AMLens 用于反洗钱交易结构分析。项目将交易数据存入 SQLite，使用 Python 图算法和七条固定 SQL 规则离线检测交易结构。Streamlit 仪表盘按历史时间回放检测证据，支持人工案件复核。

可选的人工智能（AI）分析提供案件证据评估和仪表盘摘要。

## 安装与启动

### 环境要求

- 安装 [Git](https://git-scm.com/downloads)。
- 安装 [uv](https://docs.astral.sh/uv/getting-started/installation/)。
- 预留至少 **5 GB** 可用磁盘空间，用于源文件、结果和临时数据库。

项目通过 `.python-version` 指定 Python **3.13.15**，uv 根据这个文件选择解释器。首次安装依赖和下载数据需要联网。以下命令适用于 Windows PowerShell、macOS 和 Linux。

默认数据来自 [Kaggle 数据集版本 8](https://www.kaggle.com/datasets/ealtman2019/ibm-transactions-for-anti-money-laundering-aml/versions/8)。下载器按[数据源清单](src/amlens/operations/reference_dataset.json)校验文件大小和 SHA-256 哈希值。源文件、数据库和结果保存在项目根目录的 `data/`，不纳入 Git。

### 首次安装

1. 克隆仓库：

   ```text
   git clone https://github.com/lunaticyang22-collab/BA6003-final-project-Group-11.git
   ```

2. 进入项目目录：

   ```text
   cd BA6003-final-project-Group-11
   ```

3. 安装锁定版本的依赖：

   ```text
   uv sync --frozen
   ```

4. 下载源数据并重建数据库：

   如果 Kaggle 要求认证，先按[官方认证说明](https://github.com/Kaggle/kagglehub#authenticate)在本机设置 `KAGGLE_API_TOKEN`，或创建 `~/.kaggle/kaggle.json`。凭据不得写入源代码、命令参数或 Git。

   ```text
   uv run --frozen python scripts/reproduce.py --download
   ```

   命令会校验源文件、导入交易、运行检测，并将检测结果与参考证据比较。数据准备完成后，命令退出。已有本地记录中的检测阶段耗时约 **14 分钟**；完整安装耗时取决于计算机性能和下载速度。

### 配置 AI 分析

此步骤可选。未配置 AI 时，仪表盘和人工复核仍可使用，分析卡片会显示配置说明。

选择支持 JSON Schema 结构化输出的准确 OpenRouter 模型 ID。应用要求提供方支持请求参数，不会自动选择其他模型。支持要求见 [OpenRouter 结构化输出说明](https://openrouter.ai/docs/guides/features/structured-outputs)。

API 密钥不得写入 Git、浏览器代码或共享日志。Git 和项目导出均排除本地 `.env` 文件，只保留不含凭据的示例文件。

1. 将 [`.env.example`](.env.example) 复制为项目根目录的 `.env`，与 `pyproject.toml` 放在同一目录。
2. 在 `.env` 中设置 API 密钥和模型 ID：

   ```dotenv
   OPENROUTER_API_KEY="your-local-key"
   AMLENS_AI_MODEL="provider/model-id"
   ```

3. 在本机替换两个占位值。

同一份 `.env` 格式适用于 Windows、macOS 和 Linux。完成配置后，按下一节启动仪表盘。

### 启动仪表盘

首次数据准备成功后，在项目根目录执行启动命令：

```text
uv run --frozen amlens --server.port=8513
```

在浏览器中打开 [http://127.0.0.1:8513](http://127.0.0.1:8513)。

后续启动仪表盘只需执行本节的启动命令。检测和回放可以离线运行，AI 分析需要联网。

### Deploy to Streamlit Community Cloud

The repository includes `deployment/replay.json.gz` for cloud deployment.
This snapshot contains all saved evidence, related transactions and accounts, and the complete transaction count timeline.
It represents 5,078,345 source transactions, 330 evidence transactions, 49 structure groups, and 1,221 evidence versions.
The compressed snapshot is approximately 183 KB.
Cloud deployment does not require the local data download or detection steps above.

1. Open [Streamlit Community Cloud](https://share.streamlit.io/).
2. Select **Create app**, then **Yup, I have an app**.
3. Enter these values:

   | Field | Value |
   | --- | --- |
   | Repository | `lunaticyang22-collab/BA6003-final-project-Group-11` |
   | Branch | `main` |
   | Main file path | `streamlit_app.py` |

4. Open **Advanced settings** and select Python **3.13**.
5. To enable AI, enter these root-level values in **Secrets**:

   ```toml
   OPENROUTER_API_KEY = "your-cloud-key"
   AMLENS_AI_MODEL = "provider/model-id"
   ```

   Replace the placeholders with your key and an exact model ID that supports JSON Schema structured outputs.
   Streamlit makes root-level secrets available as environment variables.
   Do not commit `.streamlit/secrets.toml` or `.env`.
   Without these values, replay and manual review remain available.

6. Select **Save**, then **Deploy**.
7. Check the application logs for startup errors.
8. Open a case and test AI analysis after replay reaches a detection time.

Community Cloud installs dependencies from `uv.lock`.
The cloud entry point reads only the committed snapshot.
It does not download source data or run detection.
Reviews and AI results stay in the current session; reconnection or restart can remove them.
See the official [deployment instructions](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy) and [dependency rules](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/app-dependencies).

To preview the cloud entry point locally, run:

```text
uv run --frozen streamlit run streamlit_app.py --server.address=127.0.0.1 --server.port=8514
```

To update cloud data after successful local detection:

1. Export the checked databases:

   ```text
   uv run --frozen python scripts/export_replay.py
   ```

   The exporter checks database compatibility and snapshot integrity before it replaces the previous snapshot.
   Export fails if detection is incomplete, source versions differ, or replay references are invalid.
   The reader accepts snapshot format version 1 and at most 64 MiB of uncompressed JSON.

2. Commit `deployment/replay.json.gz` and push the commit to the deployment branch.
3. Check the updated application in Community Cloud.

If the application reports unavailable replay data, export the snapshot again and commit it.
For AI authentication, credit, or model errors, correct the Secrets values or provider configuration, then retry the analysis.

## 文档目录

| 文档 | 内容 |
| --- | --- |
| [仪表盘使用](docs/dashboard.md) | 语言设置、回放、证据版本和人工复核 |
| [架构与检测流程](docs/architecture.md) | 模块职责、检测规则、数据流和项目术语 |
