# DuckDB + Parquet：模拟行情最小示例

这是可运行的教学示例：Python 生成行情，Parquet 文件保存行情，DuckDB 用 SQL 直接查询文件。数据全部虚构，项目最终技术栈仍待讨论。

## 运行

本示例使用独立虚拟环境，安装 `duckdb` 及其读取带时区时间所需的 `pytz`。已验证的版本与结果见下方“验证记录”。从本目录执行：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python demo.py
```

若本目录已存在本轮安装好的 `.venv`，直接执行最后一行即可。安装依赖需要联网，运行示例不需要网络、账号、交易所或数据库服务器。

每次运行创建独立的 `output/run-…/` 目录，终端会显示完整路径。目录中包含：

```text
quotes_01.parquet   # 前 5 分钟，共 1200 条
quotes_02.parquet   # 后 5 分钟，共 1200 条
results.txt        # 实际执行的 SQL、查询结果和执行计划
```

虚拟环境和生成结果已在本目录的 `.gitignore` 中排除。

## 阅读入口

- [demo.py](demo.py)：生成 → 分批保存 → 关闭写入连接 → 新连接读取 → 检查所有值 → 执行 SQL。
- [queries.sql](queries.sql)：查看类型、抽样行情、按组统计价差、关联两个市场、查看执行计划。
- [view_parquet.py](view_parquet.py)：只读查看一个 Parquet 文件的总行数、字段类型和前 10 条数据。

模拟范围是 2026-10-26 09:00:00–09:09:59 UTC，两只虚构股票 ALPHA、BETA，两个虚构市场 X、Y，每秒每个组合一条快照，共 2400 条。固定随机种子为 42。

| 字段 | 类型 | 含义 |
| --- | --- | --- |
| `event_time` | TIMESTAMPTZ | 报价发生时间，统一以 UTC 展示 |
| `received_at` | TIMESTAMPTZ | 模拟接收时间，比发生时间晚 10–40 毫秒 |
| `symbol` / `venue` | VARCHAR | 股票 / 市场 |
| `bid_ticks` / `ask_ticks` | INTEGER | 最优买价 / 卖价；本例约定 1 tick = 0.01 欧元 |
| `bid_size` / `ask_size` | INTEGER | 最优档数量 |
| `seq` | BIGINT | 本例生成器的全局顺序号，便于确定性重放 |

这里生成的是最优一档快照，不是完整订单簿、增量事件流或成交记录。价格用整数 tick 保存，避免价格比较依赖二进制浮点近似；金额展示时才除以 100。

## 保存和查询的核心

DuckDB 内存表是本示例选择的写入方式，属于可选步骤。这样可以用已有的 DuckDB 依赖和 SQL 定义字段类型、写入并导出；没有进行写入性能比较。若采集器只需要保存一批记录，也可以使用 PyArrow 把内存中的 Arrow Table 直接写成 Parquet，不需要建立 DuckDB 表。直接写仍需要内存缓冲、列式编码和压缩，参见 [PyArrow 写入接口](https://arrow.apache.org/docs/python/generated/pyarrow.parquet.write_table.html)。本例目前未安装 PyArrow，也未更换原写入实现。

写入阶段先在 DuckDB 内存表 `quotes_batch` 中组织好一批数据，再执行：

```sql
COPY quotes_batch TO 'quotes_01.parquet'
(FORMAT PARQUET, COMPRESSION ZSTD);
```

程序中使用参数绑定传入实际保存路径。内存表连接随后关闭，持久化的数据留在 Parquet 文件中。

读取阶段可以在一个新的 Python 进程中直接运行以下代码。将 `run_directory` 换成刚才终端显示的目录：

```python
from pathlib import Path
import duckdb

run_directory = Path("output/run-替换为实际目录")
with duckdb.connect(":memory:") as con:
    con.read_parquet(str(run_directory / "quotes_*.parquet")).create_view("quotes")
    con.sql("""
        SELECT symbol, venue, COUNT(*) AS quote_count,
               ROUND(AVG(ask_ticks - bid_ticks), 3) AS average_spread_ticks
        FROM quotes
        GROUP BY symbol, venue
        ORDER BY symbol, venue
    """).show()
```

`quotes` 是引用文件的视图。这一步没有把行情复制进持久化数据库；两个 Parquet 文件可以作为一张逻辑表查询。SQL 也支持直接写 `FROM read_parquet('output/run-实际目录/quotes_*.parquet')`。

## 打开已有的 Parquet 文件

Parquet 保存的是二进制数据，需要用兼容工具解码成表格。已有环境可以直接用 DuckDB 查看，无需再安装库。从本示例目录运行：

```bash
.venv/bin/python view_parquet.py output/run-hrx0d630/quotes_01.parquet
```

如果查看另一次运行，把路径换成对应的文件。脚本显示总行数、列类型和前 10 条记录，不会修改文件。预览没有按业务字段排序；需要按发生时间查看时，可另写 `ORDER BY event_time, symbol, venue`。

核心读取操作只有：

```python
with duckdb.connect(":memory:") as con:
    con.read_parquet("实际文件路径.parquet").limit(10).show()
```

这里 DuckDB 作为文件读取和查询工具使用，无需先执行 `CREATE TABLE` 或 `INSERT`。

## 为什么选择这套组合

| 本例的需求 | 组合提供的帮助 | 使用边界 |
| --- | --- | --- |
| 保存持续到达的行情批次 | 每批生成独立 Parquet 文件，旧批次保持不变 | Parquet 文件应写完再发布给读者；本例顺序执行保存与查询 |
| 保存时间、整数和字符串类型 | Parquet 带有 schema，可读回原有类型和值 | 不同采集程序仍须统一字段名、单位及时间语义 |
| 计算价差、分组统计、跨市场关联 | DuckDB 直接执行 SQL，不需要部署服务器或先复制全部文件到数据库 | 这是嵌入式分析示例，不是多人实时共同写一个库的演示 |
| 查询只涉及少数列 | 列式文件配合投影下推，减少读取无关列；过滤条件可下推至扫描 | 是否跳过行组还取决于文件统计信息和数据分布 |
| 在同学电脑上复现实验 | 分享已经写完的文件和代码即可，各自本地查询 | 不把持续修改的数据库文件交给云盘并发同步 |

本例使用 DuckDB 加一个小型时区依赖 pytz；无需同时安装 pandas、PyArrow、PostgreSQL 或 Redis。DuckDB 自己也能持久化表，Parquet 也能由其他兼容工具读取，这两者可以独立使用。

小数据用 CSV 加 Python 也完全可行。选择这个组合的价值在于保留类型、分批分享数据和方便地做 SQL 分析；2400 行示例不足以证明性能优于其他数据库。每条报价单独写一个文件会产生大量小文件，实际采集应采用适当批次。

## 如何理解跨市场查询

查询把 X 的卖价与 Y 的买价放在同一行。假设 X 卖价为 100.02，Y 买价为 100.05，纸面差值为 3 ticks，即每股 0.03 欧元。

生成器故意让 Y 市场每分钟有十秒偏高，目的是保证 JOIN 示例有结果。结果不表示可执行利润。两市场的事件时间在本例中同步；真实数据通常需要按当时已经收到的报价对齐，考虑数据陈旧程度、费用、延迟、数量与成交情况。

## 验证记录

2026-10-26 已在 Python 3.14.7、DuckDB 2.0.0、pytz 2026.5 下运行成功，`pip check` 通过。环境仅安装在本示例的 `.venv` 中。

- 两个文件分别为 13,296 和 12,102 字节，合计 25,398 字节；元数据确认使用 ZSTD 压缩。这是本次样本大小，不是与其他格式的性能比较。
- 写连接关闭后，新连接逐值核对全部 2400 条记录，时间和值均保持一致。
- 另开 Python 进程，不导入生成器，只读取文件：总行数、每文件行数、唯一序号、UTC 起止时间、买卖价格与数量约束均通过。
- 独立用 Python 加总、计数和按键匹配，核对四组 SQL 均值及全部 200 个模拟正价差，结果一致。
- 执行计划显示 Parquet 扫描投影 `bid_ticks`、`ask_ticks`，同时应用 `symbol = 'ALPHA'` 过滤。计划中的 `~480 rows` 是优化器估计，不是实测行数。

平均价差的实际输出如下；1 tick = 0.01 欧元：

| 股票 | 市场 | 报价条数 | 平均价差 / ticks |
| --- | --- | ---: | ---: |
| ALPHA | X | 600 | 3.010 |
| ALPHA | Y | 600 | 3.007 |
| BETA | X | 600 | 2.990 |
| BETA | Y | 600 | 2.970 |

本机留存：[完整查询结果](output/run-hrx0d630/results.txt)、[独立进程核查结果](output/run-hrx0d630/verification.txt)。`output/` 不随 Git 提交，其他电脑运行脚本即可生成自己的结果；这两条链接对应本次本地运行。

本次验收范围是数据保存、查询和重放，不涉及交易盈利或数据库性能排名。

## 官方参考

- [DuckDB Python API](https://duckdb.org/docs/stable/clients/python/overview)：在 Python 中创建连接和执行 SQL。
- [DuckDB COPY](https://duckdb.org/docs/stable/sql/statements/copy)：将表或查询结果导出为文件。
- [DuckDB Parquet 读写](https://duckdb.org/docs/stable/data/parquet/overview)：直接查询、通配符读取、压缩及投影 / 过滤下推。
- [Apache Parquet 概述](https://parquet.apache.org/docs/overview/)：列式文件格式与压缩。
