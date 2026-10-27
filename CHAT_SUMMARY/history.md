# 聊天记录概括与协作交接

> 更新日期：2026-10-27（Europe/Berlin）
> 用途：为后续聊天或其他 agent 提供精简上下文；记录需求与状态，不替代原始对话或正式会议决议。

## 1. 当前目标

为可能在 2026-10-26 举行的小组会议准备 Markdown 材料，介绍 hackaTUM 往届相关赛道及作品，讨论协作模式，并建立项目文档框架。

## 2. 已确认的用户要求

- 同时覆盖 **Optiver 与 IMC**。
- 以 **2025 年**为“去年”的背景，并考虑 **2024、2023 年**的资料和作品链接。
- 作品与资料须提供可直接点击的链接。
- 协作模式先讨论 **共享 Google Drive**，其他方案可提出供讨论。
- 建立 **README.md、AGENTS.md**，先设置格式，具体项目内容后续再讨论。
- 增加**聊天记录概括**文件，并让文档支持**多 agent 协作与交接**。
- 2026-10-26 后续要求：用模拟行情制作 DuckDB + Parquet 的简单可运行例子，演示保存、查询并解释选型理由。
- 2026-10-26 后续要求：先实现新闻写入示例，从模拟新闻的 `Symbols:` 行提取股票代码，再保存为 JSONL。
- 2026-10-26 后续要求：采用行情、团队成交、账户状态三表加新闻 JSONL，每秒写 DuckDB、每五分钟导出 Parquet；暂不加订单表。每张表必须独立目录、函数与参数，方便比赛复制调整；尽量使用纯函数。
- 后续明确要求：采用 NumPy 优化；再提供独立 C++ 版本，用相同输入和约束与现有 NumPy 版本比较速度，保留按表分目录 / 函数 / 参数和纯函数边界。

## 3. 当前文件与进度

当前项目目录：`/Users/douzihao/tricky/HackTUM2627`。2026-10-26 按用户要求，将四份项目文档及 `docs/meetings` 目录迁移至此；后续以此目录为准。

| 文件 | 当前内容 | 状态 |
| --- | --- | --- |
| [会议材料](../docs/meetings/2026-10-26-kickoff.md) | 两赛道背景、2023–2025 年案例、协作选项、决议与行动表 | 讨论稿已建立 |
| [README.md](../README.md) | 项目导航与待填章节 | 框架已建立 |
| [AGENTS.md](../AGENTS.md) | 阅读入口、多 agent 分工与交接约定、待填技术规则 | 框架已建立 |
| [DuckDB + Parquet 示例](../database_exp/duckdb_parquet/README.md) | 2400 条模拟行情、分批保存、SQL 查询与选型说明 | 已本地运行并核查 |
| [新闻 JSONL 示例](../database_exp/news_jsonl/README.md) | 三条模拟新闻、awk 提取 Symbols、Python 追加写入与完整读回 | 已本地运行并核查 |
| [三表持续写入示例](../database_exp/stream_ingestion/README.md) | 按表分目录、纯函数核心、每秒事务写入、每五分钟归档 | 已本地运行并核查 |
| [C++ 三表版本与对照](../database_exp/stream_ingestion_cpp/README.md) | 同一 fixture、同一 DuckDB 引擎 / 约束、成对测速及纯函数 / I/O 分离 | 已构建、实测并逐值核查 |
| 本文件 | 需求概括、状态及交接模板 | 已建立 |

资料依据已在会议材料中就近链接。2023、2024 年官方赛道奖项列表未列出 IMC，本次未确认对应作品；不要把其他赛道或赛事的案例当成这两年的 IMC 作品。获奖与技术效果分别标注，尚未复现任何往届实现。

本轮验证：四个 Markdown 文件的本地链接目标存在，代码块闭合，未残留内部检索引用标记；会议材料所列赛事、作品与获奖标记已通过对应官方页面或 Devpost 核查。

## 4. 已确定与待讨论的边界

**已确定：** 文档范围、历史资料年份、可点击链接、先搭框架、支持多 agent 交接。

**待讨论：** 最终赛道、本届正式规则、团队成员与分工、技术栈、模型或策略、验收指标、Google Drive / GitHub 的采用方式、会议时间和下一步截止日期。

**尚未执行：** 创建或共享线上 Drive、创建远程代码仓库、邀请或联系组员、实现交易程序。本文件中的协作建议不代表团队已采纳。

## 5. 多 agent 任务登记模板

当前没有并行任务在执行。启动新的协作任务时，由协调 agent 填写具体负责人和文件范围。

| 任务 ID | 任务与交付物 | 负责人 | 允许修改的文件 | 依赖 / 验收依据 | 状态 |
| --- | --- | --- | --- | --- | --- |
| 待填写 | 待填写 | 待填写 | 待填写 | 待填写 | 未开始 |

建议状态：`未开始`、`进行中`、`待验证`、`已完成`、`受阻`。同一文件的写入负责人应唯一；共享文档由协调 agent 汇总。

## 6. 交接模板

```markdown
### 交接：<任务 ID / 标题>

- 日期 / agent：
- 原始目标与约束：
- 已完成：
- 修改文件：
- 来源 / 验证方法与结果：
- 尚未验证或存在的问题：
- 需要团队决定：
- 下一步与接手人：
```

## 7. 决议记录模板

| 日期 | 决议 | 依据 / 对话或会议位置 | 影响文件 | 后续动作 |
| --- | --- | --- | --- | --- |
| 待填写 | 待填写 | 待填写 | 待填写 | 待填写 |

## 8. 下一次继续时

先确认用户的新要求或会议结论，再补充相应章节。若尚无会议结论，保持技术与协作选项为待讨论；历史链接与材料不代表 2026 年正式规则。

## 9. 数据类型与数据库选型分析（讨论建议，2026-10-26）

### 交接：赛道数据与数据库准备

- 日期 / agent：2026-10-26 / 本轮主 agent；未启动并行 agent。
- 原始目标与约束：分析赛道可能涉及的数据类型，以及比赛时可采用的数据库；当前同时考虑 Optiver 与 IMC。
- 已完成：阅读项目入口及会议材料，核查往届官方赛题和数据库官方文档，形成下列候选方案。
- 修改文件：本文件；没有安装数据库或实现采集、交易程序。
- 来源 / 验证方法与结果：[2025 Optiver Slides](https://hack.tum.de/wp-content/uploads/2025/11/hackaTUM2025_optiver_challenge.pdf)确认模拟交易、消息情绪和双重上市；[官方赛道页](https://hack.tum.de/challenges/)的 IMCity 段落列举天气、空气质量和航班活动。以下字段与架构为据此提出的设计建议，不是已取得的本届数据 schema。
- 尚未验证或存在的问题：尚未取得 2026 年完整接口、数据样本、更新频率、数据规模、存储权限及部署限制；没有进行性能测试。
- 需要团队决定：最终赛道、单机还是多机实时共享、交易与研究模块分工；本轮建议未被确认为技术栈决议。
- 下一步与接手人：团队取得规则和样本后，先验证采集、持久化和历史重放，再按实测并发与查询需求确定数据库。

| 可能的数据 | 代表字段 / 处理特点 | 候选保存方式 |
| --- | --- | --- |
| 行情与订单簿 | 标的、市场、时间、买卖价格及数量；区分快照与增量 | 最新状态在内存；历史批量写入 Parquet，用 DuckDB 分析 |
| 公共成交、自己的订单与成交 | trade_id / order_id、方向、价格、数量、状态；公共成交与自己的成交分开 | 行情成交可归档 Parquet；本地订单事件可用 SQLite，需要共享时用 PostgreSQL |
| 新闻 / 模拟社交消息 | 原文、来源、发布时间、接收时间、相关标的 | 原始消息文件；结构化字段加 TEXT，使用 PostgreSQL 时可附加 JSONB |
| IMC 城市信号 | 指标、地点、观测时间、发布时间、接收时间、值、单位；不同频率及修订版本 | 原始响应保留，标准化数值历史用 Parquet / DuckDB；共享服务可用 PostgreSQL |
| 派生特征与实验结果 | 特征时间、模型版本、参数、run_id、PnL 等 | 特征历史用 Parquet / DuckDB；实验元信息可用 SQLite 或 PostgreSQL |

候选方案与边界：

1. 单机起步：内存维护策略状态，追加原始事件日志，批量生成 Parquet，由 DuckDB 做历史查询和特征分析。Parquet 是文件格式，DuckDB 是查询数据库；仅在需要本地事务性记录和小记录更新时增加 SQLite。
2. 多机共享：采用 PostgreSQL 作为共同访问的服务；原始历史仍可按批次导出 Parquet。PostgreSQL 支持客户端 / 服务端访问及 JSONB，文本和 API JSON 并不自动意味着需要另设文档数据库。依据：[架构](https://www.postgresql.org/docs/current/tutorial-arch.html)、[JSON 类型](https://www.postgresql.org/docs/current/datatype-json.html)。
3. DuckDB 的直接 Parquet 查询适合该候选分析流程；本方案采用嵌入式模式，数据库文件由单一写进程拥有。当前 DuckDB 也有服务化并发方案，不能笼统声称其不支持多进程写入。依据：[Parquet](https://duckdb.org/docs/stable/data/parquet/overview)、[并发](https://duckdb.org/docs/stable/connect/concurrency)。SQLite 可用于本地存储，但每个数据库同一时刻只有一个写者；多人网络访问通常更适合服务端数据库，参见[官方适用场景](https://www.sqlite.org/whentouse.html)。
4. Google Drive 可共享已经封口、不会再修改的数据批次或一致性备份；不要把持续写入的数据库文件当作多机同步数据库。交易循环读内存中的最新状态，行情日志通过队列交给写入模块；监测积压与丢失，订单关键记录的持久化策略另行明确。
5. 数据约定优先：保留原始数据；区分事件 / 观测时间与实际接收时间，并记录来源、时区、事件 ID / 序号及运行版本；历史特征只能使用决策时已收到的信息。价格可按 tick size 存整数，分析特征可用浮点；没有源端序号时，本地序号不能证明上游没有丢数据。订单重启恢复需与交易所状态核对。

## 10. DuckDB + Parquet 模拟行情示例

### 交接：可运行的数据保存与查询教学示例

- 日期 / agent：2026-10-26 / 本轮主 agent；未启动并行 agent。
- 原始目标与约束：用户要求用模拟行情演示 DuckDB + Parquet 的保存、查询，以及采用这套组合的原因；保持简单、可复现。
- 已完成：生成两只虚构股票、两个市场、十分钟共 2400 条报价；每五分钟保存一个 ZSTD Parquet 文件；新 DuckDB 连接读取文件，展示类型、样本、平均价差、跨市场 JOIN 和执行计划。每次运行输出到独立目录。
- 修改文件：[demo.py](../database_exp/duckdb_parquet/demo.py)、[queries.sql](../database_exp/duckdb_parquet/queries.sql)、[requirements.txt](../database_exp/duckdb_parquet/requirements.txt)、[示例说明](../database_exp/duckdb_parquet/README.md)、示例 `.gitignore`、项目 README 和本文件。依赖只安装在示例 `.venv` 中。
- 来源 / 验证方法与结果：Python 3.14.7、DuckDB 2.0.0、pytz 2026.5；逐值读回全部记录；独立 Python 进程核查行数、序号、时间、报价约束、压缩元数据，并用 Python 核对 SQL 分组均值及全部 200 条模拟正价差；`pip check` 通过。详情与官方来源见[验证记录](../database_exp/duckdb_parquet/README.md#验证记录)。
- 尚未验证或存在的问题：没有接入实际交易所，没有测试实时并发采集、故障恢复或性能排名。模拟事件时间刻意同步；跨市场价格差是生成器人为制造，不能当作交易收益。
- 需要团队决定：是否将该流程用于正式项目；本示例不代表技术栈决议。
- 下一步与接手人：用户先运行并查看保存 / 查询代码；取得官方样本后再讨论字段映射、采集频率和异步时间对齐。

### 交接：直接写 Parquet 的解释与文件查看入口

- 日期 / agent：2026-10-26 / 本轮主 agent。
- 原始目标与约束：用户先讨论写入端，询问内存表是否必需以及如何打开 Parquet。
- 已完成：澄清内存表是可选实现，PyArrow 可直接写文件；新增只读查看脚本，显示行数、类型和前十条记录。
- 修改文件：[view_parquet.py](../database_exp/duckdb_parquet/view_parquet.py)、[示例说明](../database_exp/duckdb_parquet/README.md)及本文件。
- 来源 / 验证方法与结果：核查 Apache Arrow 官方写入文档；查看脚本读取本次保留的 `run-hrx0d630/quotes_01.parquet` 成功，显示 1200 行、9 个字段和十条样本。DuckDB 2.0 标量统计结果用 `fetchall()` 消费完毕后再调用关系查询。
- 尚未验证或存在的问题：PyArrow 路径仅作解释，没有安装 PyArrow 或更换原写入实现。
- 需要团队决定：写入端后续是否需要 SQL 清洗，或改用专门的 Parquet writer。
- 下一步与接手人：用户先查看已有文件，再继续确定写入数据格式和批次约定。

## 11. 新闻到交易标的的映射（候选方案）

### 交接：symbols 字段与轻量识别模型

- 日期 / agent：2026-10-26 / 本轮主 agent。
- 原始目标与约束：用户询问如何从新闻得到 `symbols`，希望采用能快速落地的模型或分类器。
- 已完成：核查实体抽取和规则匹配的官方说明。建议先区分“新闻明确提及的标的”与“推测受到影响的标的”；前者采用来源自带标签（如有）、公司 / 代码别名匹配、必要时实体模型补充，再用正式标的表做实体链接和交易池校验。
- 候选模型与来源：[GLiNER small v2.1](https://huggingface.co/urchade/gliner_small-v2.1)支持指定实体类别，模型卡标注 166M 参数、英文、Apache 2.0；[spaCy EntityRuler](https://spacy.io/api/entityruler)支持词元规则、短语匹配和与模型组合；[spaCy 英文 small](https://spacy.io/models/en#en_core_web_sm)也是通用实体识别候选。它们不会自动提供本届模拟市场的公司到 instrument_id 映射。
- 修改文件：本文件；没有安装模型、执行推理或修改数据写入代码。
- 尚未验证或存在的问题：未获得本届新闻样本、语言、标的表或延迟要求，没有准确率与性能测试。模型分数不能直接视为已校准的正确概率；通用实体抽取不能证明新闻影响某只股票。
- 需要团队决定：`symbols` 的业务含义，以及正式公司名 / 品牌 / 别名到证券代码的映射；双重上市可能是一家公司对应多个 instrument_id。
- 用户最新补充：希望届时股票代码有专门一行提供，考虑用 GNU / 文本处理工具直接解析。这是对接口形式的期待，尚未确认官方格式；优先直接解析显式字段。
- 补充验证：用本机 `awk` 从假设的 `Symbols: ALPHA, BETA` 行成功提取两个代码，支持标签大小写、首尾空白与逗号分隔；只是模拟格式演示，未接入真实新闻接口。
- 下一步与接手人：优先核实官方数据是否自带股票代码字段或专门行。若有，直接解析并与交易标的列表核对；若没有，再评估别名表和实体模型。按字段标签而非固定行号定位，缺失 / 格式异常保留 unresolved 状态。先保存原文，再记录带方法 / 版本 / 证据的映射结果，不让识别阻塞原始新闻写入。

## 12. 模拟新闻提取 Symbols 并保存 JSONL

### 交接：可运行的新闻写入示例

- 日期 / agent：2026-10-26 / 本轮主 agent；未启动并行 agent。
- 原始目标与约束：用户要求从模拟新闻的 Symbols 专门行提取代码，再保存成 JSONL；继续聚焦写入端。
- 已完成：提供单代码、多代码和缺失字段三条样本；系统 awk 只解析 `Body:` 之前的 Symbols 头部，去除重复代码；Python 标准库核对模拟交易池，保留原文并逐条追加为一行 JSON。缺失、空字段、异常和未知代码分别标记，每次运行使用独立输出目录。
- 修改文件：[demo.py](../database_exp/news_jsonl/demo.py)、[extract_symbols.awk](../database_exp/news_jsonl/extract_symbols.awk)、[samples](../database_exp/news_jsonl/samples/)、[示例说明](../database_exp/news_jsonl/README.md)、示例 `.gitignore`、项目 README 和本文件。没有安装模型或额外 Python 包。
- 来源 / 验证方法与结果：Python 3.14.7、系统 `/usr/bin/awk`；三条样本生成三行 JSONL，原文、中文、引号与换行完整读回；额外验证 CRLF、标签大小写 / 空白、重复代码、正文伪字段、空字段、代码内空格、末尾逗号、重复头部、部分解析失败、未知代码、连续追加与时区转换。全部通过，证据见[验证与范围](../database_exp/news_jsonl/README.md#验证与范围)。
- 尚未验证或存在的问题：新闻、标的及头部格式全部为模拟；未接入官方数据。每条样本启动一次 awk 用于教学；未覆盖并发写入、重试去重、崩溃恢复及缺失必需元数据，不承诺高频性能。
- 需要团队决定：正式数据格式、交易标的列表与运行负载；本示例不代表正式存储方案已确定。
- 下一步与接手人：用户可先运行并打开生成的 JSONL；取得官方样本后调整字段和代码校验，实际采集时由接收程序记录接收时间。

## 13. 三表 + 新闻持续写入原型

### 交接：按表分目录、显式参数、尽量纯函数

- 日期 / agent：2026-10-26 / 本轮主 agent；未启动并行 agent。
- 原始目标与约束：行情、团队成交、账户状态三表加新闻 JSONL；默认每秒写入持久化 DuckDB，每五分钟导出新增数据，订单表后面再加。用户明确要求每张表分目录、分函数、分参数，便于比赛整包复制调整；尽量纯函数。
- 已完成：独立 [market](../database_exp/stream_ingestion/market/)、[trades](../database_exp/stream_ingestion/trades/)、[accounts](../database_exp/stream_ingestion/accounts/)、[news](../database_exp/stream_ingestion/news/) 四个包。前三者各有 `params.py`、`transform.py`、`storage.py`、`mock.py`；新闻分参数、parser、writer、mock。包之间无相互依赖；可不带 mock 独立复制使用。
- 函数边界：字段映射、Symbols 提取、模拟数据、账户更新与估值均显式接收参数和状态，不读时钟或修改输入。`mock_source.read_tick` 返回 `(batch, next_state)`；主程序在数据库提交成功后推进状态。I/O 仅放在各模块写入文件与外层调度 / 事务 / 归档函数。
- 写入与归档：三张表每轮同一事务；成交 ID 唯一，行情 / 账户按轮次与标的 / 团队唯一。金额用整数分，账户持仓存 JSON。五分钟按采集轮次排他区间归档，先隐藏暂存再发布整批目录；正常退出导出尾批；不删除 DuckDB 历史。新闻逐条追加并保留原文，单独落盘。
- 修改文件：[示例说明](../database_exp/stream_ingestion/README.md)、[main.py](../database_exp/stream_ingestion/main.py)、[settings.py](../database_exp/stream_ingestion/settings.py)、[mock_source.py](../database_exp/stream_ingestion/mock_source.py)、[跨表 I/O](../database_exp/stream_ingestion/storage.py)、四个包、[测试](../database_exp/stream_ingestion/test_ingestion.py)、[结果核查](../database_exp/stream_ingestion/verify_run.py)、依赖 / 忽略文件，以及项目 README 与本文件。
- 来源 / 验证方法与结果：Python 3.14.7、DuckDB 2.0.0；当前纯函数版本八项检查通过，包括纯函数重复性 / 不修改输入、四个包独立复制使用、事务回滚、重复成交回滚、归档边界 / 空表、导出失败不发布半批、新闻解析。610 模拟秒生成 1,220 行行情、244 笔成交、1,220 条账户、11 条新闻，两个五分钟批次与十秒尾批逐值一致，账户独立重放通过；真实一秒节拍、临时五秒导出也通过。另验证模块参数独立修改及 SIGTERM 尾批。证据见[验证](../database_exp/stream_ingestion/README.md#验证)。
- 尚未验证或存在的问题：全部是模拟数据；未接入官方 API。同步导出会短暂占用循环，不保证硬实时；未实现断点续跑、跨介质原子提交、断电恢复或多进程写同库。新闻 JSONL 与 DuckDB 事务独立。运行中的数据库由写入进程拥有，外部可读已发布 Parquet；实时查询接口尚未实现。
- 需要团队决定：正式字段、价格精度、估值规则、真实账户来源、团队数据可见性、部署与数据保留方案；不要把模拟接口当成本届 schema。
- 下一步与接手人：先查看各表目录与配置；比赛样本到手后，主要调整对应模块 `transform.py` / `parser.py` 的字段映射及主程序的数据源入口。

## 14. NumPy 数值计算与批量写入优化

### 交接：保留按表分目录和纯函数接口

- 日期 / agent：2026-10-26 / 本轮主 agent；未启动并行 agent。
- 原始目标与约束：用户追加要求使用 NumPy、提高效率；继续保留每表独立目录 / 参数 / 函数、纯函数和一秒写入 / 五分钟导出的流程。
- 已完成：三表新增独立 `columns.py`，`records_to_columns` 纯转换，`write_records` 整批 INSERT SELECT；新增 `write_columns` 接受源端已准备的 NumPy 数组。数值列使用整数，时间与文本保留 object；保留数据库主键、CHECK 和三表事务。未添加 pandas / PyArrow。
- 数值状态：价格与账户现金 / 团队×股票持仓保持 NumPy int64；局部 `default_rng(seed)` 生成随机批次，`np.add.at` 处理重复成交索引，矩阵乘法估值。函数不修改输入数组；金额计算检查保守溢出上界。输出快照仍独立转 JSON；模拟器版本与 NumPy 版本写入运行清单。
- 修改文件：三个表包的 `columns.py` / `storage.py` / `__init__.py`，数值 mock 和账户 transform，[mock_source.py](../database_exp/stream_ingestion/mock_source.py)、[main.py](../database_exp/stream_ingestion/main.py)、[requirements.txt](../database_exp/stream_ingestion/requirements.txt)、[benchmark.py](../database_exp/stream_ingestion/benchmark.py)、[原始性能结果](../database_exp/stream_ingestion/benchmarks/numpy-v1.json)、[测试](../database_exp/stream_ingestion/test_ingestion.py)、示例与项目 README、本文件。
- 来源 / 验证方法与结果：Python 3.14.7、DuckDB 2.0.0、NumPy 2.5.4，`pip check` 通过；12 项检查通过，覆盖纯函数、目录独立复制、事务 / 导出、重复索引、标的映射、时区、JSON 对象、大整数精度与溢出。610 秒加速运行三表行数 1,220 / 244 / 1,220，新闻 11 行，三个 Parquet 批次逐值核对且账户独立重放一致。真实一秒节拍、参数 / 团队顺序调整、SIGTERM 尾批均通过，链接见[验证](../database_exp/stream_ingestion/README.md#验证)。
- 性能证据：5 次中位数，本机单表持久化写入 10,000 条从旧 executemany 约 1,789.870 ms 降至现 write_records 15.242 ms，约 117 倍；两条记录 1.008 → 0.600 ms。均包括字段转换和事务提交，逐值相等；不是单靠 NumPy 算术的收益。256×512 纯估值核心约 56 倍，不含记录 / JSON 序列化。详细范围及官方 API 来源见[性能说明](../database_exp/stream_ingestion/README.md#numpy-优化的实测范围)。
- 尚未验证或存在的问题：未接真实 API，未做正式负载全链路测试；模拟器仍以记录列表演示字段适配，数组接口可避免调用方的逐行中转。随机序列与旧 Python random 版本不同。同步导出、单写者、新闻与数据库事务独立等已有边界不变；不能承诺全局最优效率。
- 需要团队决定：正式字段 / 单位与负载，输入是否能直接提供列数组；NumPy int64 的金额范围需适配比赛数据。
- 下一步与接手人：按实际 API 调整各表 transform；若源头已有数组，直接使用 write_columns。以 benchmark 脚本和最终样本测量后再决定额外性能改造。

## 15. C++ 三表版本与 NumPy 同条件对照

### 交接：可独立运行的 C++ 重放、持久化与验证

- 日期 / agent：2026-10-27 / 本轮主 agent；未启动并行 agent。
- 原始目标与约束：用户明确要求 C++ 版本，用相同数据和约束与现有 NumPy 比较速度；按表分目录、函数、参数，尽量纯函数。用户中途“继续”保持同一目标。
- 已完成：新增 [stream_ingestion_cpp](../database_exp/stream_ingestion_cpp/README.md)，C++20 / DuckDB C API + Appender/DataChunk；行情、成交、账户各自 params / transform / storage，账户另有 calculate，新闻独立 parser / writer。业务目录互不依赖，复制单表时带通用 support/；四个目录均已独立复制、编译和保存读回。
- 状态与 I/O：64 位整数价格 / 现金 / 持仓，账户更新返回新状态、128 位中间值检查溢出；提交后才推进状态。三表一秒一事务，300 秒按排他 tick 区间发布 ZSTD Parquet，SIGTERM / 正常退出导出尾批；新闻单独追加并 fsync。默认输入是固定模拟数据重放，C++ 不另外生成不同随机序列；随代码附带六轮 fixture，运行不依赖 Python。
- 修改文件：新增整个 C++ 示例及 [results/cpp-vs-numpy.json](../database_exp/stream_ingestion_cpp/results/cpp-vs-numpy.json)，项目 README 与本文件；现有 NumPy 业务源码未修改。源码 / 二进制哈希均与最终性能记录一致。
- 来源 / 验证方法与结果：官方 DuckDB 2.0.0 动态库与 JSON 3.12.0 头文件，固定下载 SHA-256；本机 macOS arm64、AppleClang 21、Release -O3。Python 和 C++ 引擎 source_id 同为 d54cbbe3df；均 1 线程、8GB、同主键 / NOT NULL / CHECK、同事务、同 JSONL fsync / ZSTD 归档。三种负载各预热一轮、正式五轮，串行交替顺序；18 对运行逐值对照、所有约束相同、各批 Parquet 与 DB 一致、账户独立 Python 整数重放一致。JSON 对象按结构值比较，持仓 JSON 分隔空白已统一。
- 性能结果：610 轮默认小批量累计三表写入 NumPy 361.57 ms、C++ 339.34 ms，约 1.07 倍；一轮 1,000 条行情加 2 笔成交 / 2 条账户为 3.28 → 2.94 ms；10,000 条为 17.32 → 10.07 ms，约 1.72 倍，含输入 / 计算 / 新闻 / 归档 / 关闭的活动总耗时 59.94 → 42.86 ms，约 1.40 倍。此轮不能与旧的单表 15.2 ms 基准直接对比。大场景的账户计算 / 快照构造 C++ 比 NumPy 慢，详情见[性能范围](../database_exp/stream_ingestion_cpp/README.md#本机实测结果2026-10-27)。
- 其他验证：C++ 契约测试通过，包括跨 chunk、NULL / 重复主键回滚、整数精度 / 溢出、时区、新闻、空表归档、失败不发布半批；真实 6 秒运行时间跨度 5.010 秒，5 秒归档覆盖尾批；SIGTERM 一轮尾批、参数独立修改 / 团队顺序和目录独立编译通过。现有 NumPy 12 项测试再次通过。[验收记录](../database_exp/stream_ingestion_cpp/output/validation-locy09hb/validation.txt)。
- 尚未验证或存在的问题：全部为模拟重放；无正式交易所采集、订单、断点恢复、多写者、硬实时或 JSONL 与 DB 跨介质原子性。只有 macOS arm64 实测；其他打包平台未验证，Windows 未实现。基准不含进程启动 / Python 导入，不是实际行情持续吞吐保证；小批量差距有波动。
- 需要团队决定：实际输入规模与延迟指标，是否将 C++ 用在正式写入端；不能把更换语言当作数量级提速承诺。
- 下一步与接手人：按 README 构建 / 复现，取得真实样本后调整对应表 transform 和数据源；优先用实测定位剩余数据库事务、字段转换和账户快照构造开销。
