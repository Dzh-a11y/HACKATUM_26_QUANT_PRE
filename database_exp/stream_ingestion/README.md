# NumPy + DuckDB + Parquet：按模块复制的写入示例

默认每秒写入持久化 `market.duckdb`，每五分钟把新增数据导出为一批 Parquet。只有行情、成交、账户三张表；新闻追加到 JSONL。全部为模拟数据，订单表以后再加。

数值计算使用 NumPy；三表写入采用 NumPy 列数组 → 单条 `INSERT … SELECT`。保留每表独立目录、显式参数和纯函数边界。

## 目录与改动入口

```text
stream_ingestion/
├── market/                  # 市场行情，可整包复制
│   ├── params.py            # 本表参数
│   ├── transform.py         # 纯函数：官方字段 → 本表字段
│   ├── columns.py           # 纯函数：记录 → NumPy 列数组
│   ├── storage.py           # 建表、写入、导出 Parquet
│   ├── mock.py              # 纯函数：模拟行情
│   └── __init__.py          # 对外函数入口
├── trades/                  # 团队成交；同样的六个文件
├── accounts/                # 账户快照；同样的六个文件
├── news/
│   ├── params.py            # Symbols 字段名、交易池、保存参数
│   ├── parser.py            # 纯函数：原文 → 新闻记录
│   ├── writer.py            # 追加 JSONL
│   ├── mock.py              # 纯函数：模拟新闻
│   └── __init__.py
├── settings.py              # 集中配置四个模块与运行参数
├── mock_source.py           # 纯函数：组合一秒的四类模拟输入
├── storage.py               # 跨表事务、整批 Parquet 发布
├── main.py                  # 时钟、调度、连接和退出处理
├── verify_run.py            # 停止写入后核查保存结果
├── benchmark.py             # 旧写入 / 批量写入与估值核心耗时对比
└── test_ingestion.py         # 纯函数、事务、复制与边界检查
```

| 要修改什么 | 修改哪里 |
| --- | --- |
| 写入 / 导出周期、运行时长、内存预算 | [settings.py](settings.py) 的 `RUNTIME` |
| 行情市场、币种、模拟初始价 | [market/params.py](market/params.py)；本例配置值在 `settings.MARKET` |
| 成交团队、模拟频率 / 数量 / 手续费 | [trades/params.py](trades/params.py)；配置值在 `settings.TRADES` |
| 账户团队、模拟初始资金 | [accounts/params.py](accounts/params.py)；配置值在 `settings.ACCOUNTS` |
| 官方字段名称和单位 | 对应目录的 `transform.py`；新闻使用 [news/parser.py](news/parser.py) |
| 数据库列定义、INSERT / COPY | 对应目录的 `storage.py` |
| 列名、记录转数组 | 对应目录的 `columns.py` |
| 新闻代码字段名称 / 标的白名单 | [news/params.py](news/params.py)；配置值在 `settings.NEWS` |
| 用真实 API 替换模拟输入 | [main.py](main.py) 中 `mock_source.read_tick(...)` 的调用位置 |

四个业务目录之间没有互相导入，也不依赖旧的 `news_jsonl` 示例或 awk。复制单个目录时，可以不带 `mock.py`。`__init__.py` 不加载模拟代码。

## 纯函数与 I/O 分开

`transform.py`、`columns.py`、`news/parser.py`、各模块的 `mock.py` 和 `mock_source.py` 不读时钟、不读写文件、不访问数据库，也不原地修改输入。

```python
batch, next_state = mock_source.read_tick(
    tick, event_time,
    state=old_state,
    seed=42,
    market_params=market_params,
    trade_params=trade_params,
    account_params=account_params,
    news_params=news_params,
)
```

同样的状态、时间、种子、参数得到相同结果。随机数生成器只在函数内部由显式种子创建；没有共享的可变 RNG 或有状态数据源对象。主程序在数据库事务提交成功后，才把运行状态推进到 `next_state`。

账户的两个计算函数可直接复用：

```python
from accounts.transform import apply_fills, value_accounts

new_state = apply_fills(old_state, fills)
snapshots = value_accounts(event_time, state=new_state, quotes=quotes, params=account_params)
```

`params.py` 中的 dataclass 是配置容器，函数不会修改它。记录仍使用普通字典 / 列表；持续数值状态使用 NumPy 数组。账户 `state` 的结构为：

```python
{
    "teams": ("TEAM_A", "TEAM_B"),  # 持仓矩阵的行顺序
    "symbols": ("ALPHA", "BETA"),  # 持仓矩阵的列顺序
    "cash": np.array([10_000_000, 10_000_000], dtype=np.int64),
    "positions": np.zeros((2, 2), dtype=np.int64),
}
```

行情状态为 `{"symbols": (...), "mid_cents": int64数组}`。函数返回新的价格 / 现金 / 持仓数组，不修改旧数组；生成的 JSON 快照也不与数组共享可变数据。`np.add.at` 正确累加同一团队同一股票的多笔成交，`cash + positions @ marks` 一次计算所有团队资产。

金额和数量使用 `int64`，不经 `float64` 中转。账户计算先检查保守溢出上界，超界会报错；这不是无限精度计算。随机数使用函数局部的 `np.random.default_rng(seed)`；固定依赖版本和相同输入可复现，数值序列与此前 Python `random` 版本不同，运行清单保存模拟器和 NumPy 版本。

实际副作用集中在每个模块的 `storage.py` / `news/writer.py`，以及外层连接、事务、时钟、信号与目录操作。这些函数显式接收连接或路径。

## 运行

当前项目已有前一个示例的环境，从**项目根目录**可直接运行：

```bash
# 首次使用此 NumPy 版本，更新示例环境的依赖
database_exp/duckdb_parquet/.venv/bin/python -m pip install -r database_exp/stream_ingestion/requirements.txt

# 真实每秒一轮、每 300 秒导出，默认十分钟后结束
database_exp/duckdb_parquet/.venv/bin/python database_exp/stream_ingestion/main.py

# 加速演示十分钟十秒；不等待，但保留完整的模拟秒序号和归档边界
database_exp/duckdb_parquet/.venv/bin/python database_exp/stream_ingestion/main.py --seconds 610 --fast

# 快速观察真实节拍；仅这条命令将导出周期临时改为五秒
database_exp/duckdb_parquet/.venv/bin/python database_exp/stream_ingestion/main.py --seconds 6 --export-every 5
```

复制到独立项目时，在 `stream_ingestion` 目录安装环境：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python main.py --seconds 610 --fast
```

参数：`--seconds` 运行时长、`--write-every` 写入间隔、`--export-every` 导出间隔、`--fast` 加速、`--output-dir` 输出父目录。单位为整数秒；导出间隔和运行时长必须是写入间隔的整数倍。每次建立独立 `run-*` 目录，避免覆盖已有数据。

默认模拟两只股票、两个团队；每秒两条行情和两条账户快照，每五轮每队一笔成交，每六十轮一条新闻。修改写入周期后，模拟事件的 `every_n_ticks` 仍表示轮数。

## 三张表的含义

| 表 | 一行表示什么 | 主要字段 |
| --- | --- | --- |
| `market_quotes` | 一轮采样里某个标的 / 市场的最新报价快照 | 标的、市场、币种、买卖价及量 |
| `team_trades` | 一笔实际成交，包含自己和其他团队 | 成交 ID、团队、标的、方向、数量、成交价、手续费 |
| `account_snapshots` | 一个团队当轮成交后的账户快照 | 团队、币种、现金、持仓、总资产、盈亏 |

三表共同包含 `tick`（本次运行的采集轮次）、`event_time`、`received_at`、`ingested_at`。时间列使用 `TIMESTAMPTZ`，连接时区为 UTC。模拟事件 / 接收时间由逻辑时钟生成；`ingested_at` 由主程序记录实际写入时刻。因此加速模式的模拟事件时间可能晚于实际执行时间。

所有 `_cents` 字段使用整数分，默认币种 EUR。账户 `positions` 是 JSON 对象，例如 `{"ALPHA": 5, "BETA": 2}`；同一团队的现金只存一次。初始资金和零持仓写入运行清单。模拟账户按本轮买卖中间价估值；本例报价价差为偶数分，无半分舍入问题。正式接口的价格精度、初始账户、估值规则和手续费需要据实际数据调整。

默认输出中 `TEAM_A` 代表自己，`TEAM_B` 代表其他团队；其他团队数据是否可取得要以正式接口为准。没有订单状态表。

## 如何复制单张表使用

仅把 `market/` 目录复制到自己的项目，即可这样调用：

```python
from datetime import datetime, timezone
import duckdb
from market import MarketParams, create_table, parse_record, write_records, export_parquet

params = MarketParams(venue="SIM", currency="EUR")
now = datetime.now(timezone.utc)  # 在调用层读取时钟
raw = {
    "event_time": now,
    "instrument_id": "ALPHA",
    "bid_cents": 10000, "ask_cents": 10002,
    "bid_size": 50, "ask_size": 60,
}
context = dict(tick=0, received_at=now, ingested_at=now, params=params)

row = parse_record(raw, **context)  # 纯转换，可以先单独检查 / 测试
with duckdb.connect("market.duckdb") as db:
    create_table(db)
    write_records(db, [raw], **context)
    export_parquet(db, "market_0_1.parquet", start_tick=0, end_tick=1)
```

这个独立小片段请在新目录 / 新数据库中运行一次；重复使用相同主键会报错。多个模块一起写时，由外层 `storage.write_tick()` 包在同一事务中，各模块不自行 `COMMIT`。时间参数传入带时区的 datetime；原始数据的字段约定可以直接从各模块的 `transform.py` 看到。

如果源数据已经是 NumPy 列数组，直接使用各表的 `write_columns(db, columns)`，避免先组装逐行字典。列名见对应 `columns.COLUMN_NAMES`；所有列必须是一维等长数组，数值列使用 `np.int64`，时间列使用带时区 datetime 的 `object` 数组，文本 / JSON 列使用 `object` 数组。空批次不执行 INSERT。

```python
from market import records_to_columns, write_columns

columns = records_to_columns([raw], **context)  # 纯函数，可独立检查
# 若接口直接给列数组，这一步可以省略。
with duckdb.connect() as db:  # 新的内存库，仅示范此接口
    create_table(db)
    write_columns(db, columns)  # 与 write_records 二选一，避免重复写同一主键
```

模拟器保留记录列表来示范真实 API 的字段适配，存在记录与数组转换成本；已有数组的调用方可走直接接口。新闻解析 / JSON 编码仍用标准库。依赖只有 DuckDB、NumPy、pytz，无需 pandas / PyArrow。

## 输出与归档规则

```text
output/run-…/
├── market.duckdb
├── news.jsonl
├── run.json
└── parquet/
    ├── batch_000000_000300/
    │   ├── market_quotes.parquet
    │   ├── team_trades.parquet
    │   ├── account_snapshots.parquet
    │   └── manifest.json
    ├── batch_000300_000600/
    └── batch_000600_000610/    # --seconds 610 的正常退出尾批
```

- 归档按采集轮次 `[start_tick, end_tick)` 分批；默认一轮一秒，彼此不重叠。某轮没有成交时也能生成带 schema 的空成交文件。
- 先把整批文件写到隐藏暂存目录，全部成功后才重命名为 `batch_*`；读者只扫描 `parquet/batch_*/*.parquet`，不会读到写了一半的批次。
- 导出不会删除 DuckDB 数据；查询也不会触发额外导出。三张表保持完整历史。
- 正常到期、Ctrl+C、SIGTERM 会把已提交的不足五分钟尾批导出，再关闭连接。
- 新闻直接追加 JSONL，保留原文；缺失、空、异常、未知 Symbols 分别标记。新闻使用独立文件，不与三表组成一个原子事务。

## 验证

写入进程停止后，使用输出的 `RUN_DIR`：

```bash
database_exp/duckdb_parquet/.venv/bin/python database_exp/stream_ingestion/verify_run.py database_exp/stream_ingestion/output/run-f_ludxgn
database_exp/duckdb_parquet/.venv/bin/python -m unittest discover -s database_exp/stream_ingestion -p test_ingestion.py -v
```

2026-10-26，Python 3.14.7 / DuckDB 2.0.0 / NumPy 2.5.4 已验证当前 NumPy 版本：

- 610 个模拟秒：行情 1,220 行、成交 244 行、账户 1,220 行、新闻 11 行；两个五分钟批次及十秒尾批逐值核对一致，账户现金、持仓、盈亏独立用 Python 整数重放核对通过。[记录](output/run-f_ludxgn/verification.txt)
- 真实一秒节拍运行六秒、临时五秒导出：六轮实际写入时间跨度约 5.003 秒，完整批次及尾批通过读回。[记录](output/run-ug9xyv9f/verification.txt)
- 十二项测试覆盖：纯函数重复性 / 输入不变、记录映射、四包独立复制、事务回滚、重复成交回滚、空成交归档 /他边界、导出失败、新闻边界，以及新增的重复数组索引累加 / 标的顺序、整数溢出拒绝、JSON / 时区 / 大整数精度、千行批量值一致性。
- 修改币种、标的、团队及其排列顺序、新闻标签、写入和导出周期后仍通过核对。[记录](output/run-0g5bi5zq/verification.txt)
- SIGTERM 后一轮尾批成功导出，关闭连接后可独立读回。[记录](output/run-e5yfeegh/signal_check.txt)

`output/` 是本地生成目录，不随代码共享。核查脚本面向本例模拟数据；正式接入后需要按实际数据契约调整。

## NumPy 优化的实测范围

运行 [benchmark.py](benchmark.py)：

```bash
database_exp/duckdb_parquet/.venv/bin/python database_exp/stream_ingestion/benchmark.py --repeats 5
```

本机 Apple Silicon / Python 3.14.7，5 次中位数；持久化 DuckDB 单表写入，保留主键与 CHECK 约束。两条记录路径都计入字段转换和事务提交，输入完全相同，所有行逐值核对。预热一次、轮换测试顺序；完整样本及环境保存在 [benchmarks/numpy-v1.json](benchmarks/numpy-v1.json)。

| 每批行情条数 | 原 `executemany` | 现 `write_records` | 本次加速 |
| ---: | ---: | ---: | ---: |
| 2 | 1.008 ms | 0.600 ms | 1.68 倍 |
| 1,000 | 183.212 ms | 2.280 ms | 80.35 倍 |
| 10,000 | 1,789.870 ms | 15.242 ms | 117.43 倍 |

性能提升主要来自整批插入，避免对每条记录执行一次 SQL；不只是数值计算换了 NumPy。预先准备好列数组时，`write_columns` 还可省掉记录转换；原始结果也保留了 Appender 路径对照。

256 个团队 × 512 只股票的**纯估值核心**，Python 循环约 3.125 ms，NumPy 约 0.056 ms，约 56 倍；NumPy 计入溢出上界检查，两侧输入都提前准备，不含 JSON / 记录序列化。这些结果不是整条采集链路的加速倍数，也不能推断其他机器或正式行情的吞吐。默认两只股票时，数值计算规模很小，收益主要在批量写入。

采用的 API 依据：[DuckDB 直接读取 NumPy 列数组](https://duckdb.org/docs/2.0/guides/python/import_numpy)、[NumPy 局部随机数 Generator](https://numpy.org/doc/stable/reference/random/generator.html)。本例直接扫描局部数组，不注册临时视图，批量失败时仍由外层事务回滚。

## 当前范围

这是单写入进程的教学实现：同步导出时采集循环会短暂等待，不提供硬实时保证；用单调时钟对齐下一轮，避免每轮固定 `sleep(1)` 的累计漂移。实际高频接口需要再评估队列和背压。

运行中的嵌入式 DuckDB 文件由写入进程持有。独立进程可读已发布的 Parquet；如要查看实时表，应在拥有连接的进程内提供查询接口，或停止写入后再打开数据库。

每次从新运行目录开始，未实现断点续跑、源事件重试去重、多进程写同库、断电恢复和保留策略。重复主键会报错回滚，不会静默跳过。导出失败不会删除已提交的数据；目录发布保证普通运行期间的完整批次可见性，不等于磁盘断电恢复承诺。`8GB` 是 DuckDB 内存预算参数，不是整个 Python 进程的绝对上限。
