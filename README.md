# hackaTUM 2026 筹备：Optiver / IMC

> 状态：文档框架与数据存储教学示例阶段。具体赛道、目标、正式技术栈和协作模式待团队讨论。
> 更新日期：2026-10-27

## 文档导航

- [初次会议材料与讨论要求](docs/meetings/2026-10-26-kickoff.md)：2025 年赛道背景、2023–2025 年案例链接及协作议题。
- [AGENTS.md](AGENTS.md)：agent 工作与多 agent 协作框架。
- [CHAT_SUMMARY.md](CHAT_SUMMARY/CHAT_SUMMARY.md)：聊天概括、当前进度及任务交接。
- [DuckDB + Parquet 模拟行情示例](examples/duckdb_parquet/README.md)：生成行情、分批保存、SQL 查询与选型解释；已本地验证。
- [模拟新闻写入 JSONL](examples/news_jsonl/README.md)：用 awk 从 Symbols 头部提取代码，Python 追加保存新闻；已本地验证。
- [三表 + 新闻的持续写入示例](examples/stream_ingestion/README.md)：NumPy 计算与批量写入，每秒写 DuckDB、每五分钟导出；按表分目录，纯函数处理与 I/O 分离。
- [C++ 三表写入与 NumPy 对照](examples/stream_ingestion_cpp/README.md)：同输入、同约束、同事务的双实现；五轮实测与逐值验证。

## 1. 项目背景

TODO：填写本届赛事信息、最终选择的赛道和官方赛题链接。

## 2. 项目目标与范围

TODO：填写问题定义、预期成果、最小可行版本及范围边界。

## 3. 团队与协作

| 项目 | 内容 |
| --- | --- |
| 团队成员与职责 | TODO |
| Google Drive / 共享资料 | TODO |
| 代码仓库 | TODO |
| 沟通与任务管理 | TODO |
| 同步会议安排 | TODO |

## 4. 技术方案

TODO：填写数据来源、模块划分、模型 / 策略和技术栈。

已提供独立的 [DuckDB + Parquet 行情示例](examples/duckdb_parquet/README.md)和[新闻 JSONL 示例](examples/news_jsonl/README.md)，供验证数据保存与分析流程；不代表团队已确定正式技术栈。

当前写入原型按用户要求采用行情、团队成交、账户快照三张表和新闻 JSONL；实现见[持续写入示例](examples/stream_ingestion/README.md)。每张表有独立目录、函数与参数，业务计算尽量使用纯函数；NumPy 维护数值状态并整批写入 DuckDB；订单表留待后续。

另有独立 [C++20 版本](examples/stream_ingestion_cpp/README.md)，使用 DuckDB C API + Appender/DataChunk。保留相同表约束和归档流程；现有 NumPy 版本继续保留，性能结论来自共用 fixture 的成对测试。

## 5. 当前目录

```text
.
├── README.md
├── AGENTS.md
├── CHAT_SUMMARY/
│   └── CHAT_SUMMARY.md
├── examples/
│   ├── duckdb_parquet/
│   │   ├── README.md
│   │   ├── demo.py
│   │   ├── queries.sql
│   │   └── requirements.txt
│   ├── news_jsonl/
│   │   ├── README.md
│   │   ├── demo.py
│   │   ├── extract_symbols.awk
│   │   └── samples/
│   ├── stream_ingestion/
│   │   ├── README.md
│   │   ├── main.py
│   │   ├── settings.py
│   │   ├── market/
│   │   ├── trades/
│   │   ├── accounts/
│   │   └── news/
│   └── stream_ingestion_cpp/
│       ├── CMakeLists.txt
│       ├── main.cpp
│       ├── settings.hpp
│       ├── market/、trades/、accounts/、news/
│       ├── support/
│       └── results/cpp-vs-numpy.json
└── docs/
    └── meetings/
        └── 2026-10-26-kickoff.md
```

正式交易代码与实验目录在方案确定后补充。

## 6. 环境与运行

正式交易程序尚未实现。模拟行情示例的依赖、安装与运行命令见[示例说明](examples/duckdb_parquet/README.md#运行)。

新闻示例只需 Python 标准库和系统 awk，运行命令见[新闻写入说明](examples/news_jsonl/README.md#运行)。

三表持续写入示例可复用已有 DuckDB 环境，也可独立安装；真实时间与加速演示命令见[运行说明](examples/stream_ingestion/README.md#运行)。

C++ 依赖下载、Release 编译、独立运行与基准复现见[构建和运行](examples/stream_ingestion_cpp/README.md#构建和运行)。

## 7. 测试与评估

TODO：填写评价指标、实验方法、测试入口与结果记录方式。

模拟行情示例已验证 2400 条记录的保存 / 读回、独立进程读取、SQL 聚合与跨市场关联；证据见[验证记录](examples/duckdb_parquet/README.md#验证记录)。未进行交易收益或数据库性能评测。

新闻示例已验证三条新闻的 Symbols 提取、逐条追加和 JSONL 完整读回，以及缺失 / 格式异常等情况；见[验证与范围](examples/news_jsonl/README.md#验证与范围)。

持续写入示例已通过 12 项检查，并验证三表 / Parquet 逐值一致、账户重放、新闻解析、纯函数输入保持不变、四个模块独立复制使用、事务回滚和正常停止尾批；见[验证记录](examples/stream_ingestion/README.md#验证)。NumPy 批量写入和估值核心的本机对照测量见[性能记录](examples/stream_ingestion/README.md#numpy-优化的实测范围)，不是正式行情全链路吞吐测试。

C++ / NumPy 共用同一输入，18 对运行全部值、schema 与约束一致。五轮中位数：一轮 10,000 条行情加成交 / 账户，三表写入 17.32 → 10.07 ms，约 1.72 倍；默认少量每秒写入约 1.07 倍。C++ 真实节拍、SIGTERM、独立复制编译及错误边界已通过；见[实测结果](examples/stream_ingestion_cpp/README.md#本机实测结果2026-10-27)。

## 8. 里程碑与任务

| 里程碑 | 交付物 | 负责人 | 时间 | 状态 |
| --- | --- | --- | --- | --- |
| TODO | TODO | TODO | TODO | 待讨论 |

## 9. 展示与提交

TODO：填写 Demo、Slides、Devpost 和正式提交要求。

## 10. 参考资料

已核查的往届链接见[会议材料](docs/meetings/2026-10-26-kickoff.md)。本届正式资料与最终采用的参考方案待补充。
