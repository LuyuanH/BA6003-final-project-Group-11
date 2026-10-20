# 检测参考证据

[返回 README](../../README.md)

## 内容与来源

`expected-detection.json` 保存已完成的 `pattern-demo-lab` SQL 重计数所导出的参考证据，包含 1,221 份唯一的 `(rule_id, case_id)` 证据集，以及原始 CSV 交易行 ID。文件不包含原始账户详情或交易标签，检测过程和仪表盘均不读取这个文件。

参考运行使用规则集 `historical-demo-6ed874e77b60`，从 `2022-09-01 06:00:00` 至 `2022-09-18 18:00:00`，每 6 小时设置一个截止时间，共 71 个。每个截止时间使用 48、96 和 216 小时的窗口。候选结构来自 5,078,345 笔源交易，选中证据包含七类启用模式中的 330 笔唯一交易。

`provenance.json` 记录源文件和输出哈希值。记录中的路径用于标识历史文件，不是运行依赖。

## 比较检测结果

执行比较前，先完成 [README 中的首次安装](../../README.md#首次安装)，生成观测数据库和检测结果。

在项目根目录执行参考比较：

```sh
python scripts/verify_detection.py
```

比较过程不需要旧项目、DuckDB、Parquet 支持或被 Git 忽略的 artifacts 目录。使用 `--database path/to/detection.sqlite` 可选择其他结果数据库，使用 `--reference` 可选择同一参考证据的其他导出文件。

JSON 空白、记录顺序和成员顺序可以不同。验证器比较规范化后的 SHA-256 哈希值，拒绝缺失、重复或变化的参考证据。校验失败时，命令返回 JSON 报告，退出状态为 1。

## 参考证据导出

参考导出使用 `results/sql_recount/selected_evidence.parquet`，源查询如下：

```sql
SELECT DISTINCT rule_id, family, case_id, transaction_ids
FROM selected_candidates
ORDER BY rule_id, case_id;
```

## 更新检测参考

不得只为使测试通过，就使用被测实现生成的结果替换参考证据。建立修订后的参考时，按以下顺序操作：

1. 运行独立参考实现。
2. 导出选中证据。
3. 审阅变化的交易集合和源记录。
4. 同步更新参考文件和验证器预期值。

参考证据只验证历史复现，不证明对未见数据的预测表现。源码分发包不包含原始 CSV 或生成的 SQLite 数据库，需要获取匹配输入并在本地重建。
