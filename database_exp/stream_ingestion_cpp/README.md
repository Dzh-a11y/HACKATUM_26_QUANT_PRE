# C++ + DuckDB：三表写入与 NumPy 对照

C++20 版本保留行情、团队成交、账户快照三表，以及新闻 JSONL；默认每秒提交三表事务、每 300 秒导出 ZSTD Parquet，退出时导出已提交尾批。暂不包含订单表。

使用 DuckDB **C API + Appender/DataChunk**，数据库引擎固定为 2.0.0。对应 Python 版本是 [stream_ingestion](../stream_ingestion/README.md)，原有实现未替换。

## 按表分目录、分函数、分参数

```text
stream_ingestion_cpp/
├── market/
│   ├── params.hpp                 # 行情参数
│   ├── transform.hpp / .cpp       # 纯函数：输入记录 → 列缓冲区
│   └── storage.hpp / .cpp         # 建表、批量写入、Parquet 导出
├── trades/                       # 同样结构，团队实际成交
├── accounts/
│   ├── params.hpp
│   ├── transform.hpp / .cpp
│   ├── calculate.hpp / .cpp       # 纯函数：成交更新、持仓估值
│   └── storage.hpp / .cpp
├── news/
│   ├── params.hpp
│   ├── parser.hpp / .cpp          # 纯函数：Symbols 行及新闻字段
│   └── writer.hpp / .cpp          # JSONL、flush、fsync
├── support/                      # 通用列容器、C API 资源释放、时间和文件工具
├── settings.hpp                  # 参数容器与运行配置
├── pipeline.hpp / .cpp           # 三表事务、定时归档、状态推进
├── main.cpp                      # CLI、时钟、信号入口
├── setup_deps.py                 # 固定版本下载与 SHA-256 校验
├── generate_fixture.py           # 用现有 NumPy 模拟器生成公共输入
├── python_worker.py              # 调用现有 NumPy 模块的对照进程
├── benchmark.py                  # 串行交替测试与逐值验证
├── verify_pair.py
├── fixtures/sample.json          # 随代码提供的六轮示例，C++ 可独立读取
└── tests/
    ├── test.cpp                  # 纯函数、事务、精度与归档边界
    └── verify_io.py              # 真实节拍、SIGTERM、独立复制编译
```

四个业务目录不互相导入。**复制一张表时，复制该目录和 `support/`**，再链接 DuckDB 并提供 JSON 头文件；不需要其他表的代码。新闻只需要 JSON 头文件，不链接 DuckDB。已实际逐个复制到临时目录编译、写入并读回。

| 比赛时要改什么 | 位置 |
| --- | --- |
| 官方字段、价格单位、缺失字段规则 | 各表 `transform.cpp` |
| 表结构、主键与 CHECK 约束 | 各表 `storage.cpp` 的建表 SQL |
| 默认市场、币种、团队、初始资金 | 各表 `params.hpp` |
| 新闻头部标签、代码白名单 | `news/params.hpp` / `parser.cpp` |
| 写入、导出间隔与演示时长 | 公共输入 metadata；运行覆盖参数见下文 |
| 替换文件重放为正式数据源 | `pipeline.cpp` 中读取一轮输入的位置 |

重放程序从公共输入读取显式参数，因此修改 `params.hpp` 的默认值不会悄悄改变已有测试输入。接真实接口时可以直接构造参数传入各表函数。

## 纯函数边界

`records_to_columns(records, context, params)` 不访问数据库、不读取时钟、不修改输入，返回独立列缓冲区。金额 / 数量使用 `int64_t`；时间为 UTC Unix 微秒，写入 `TIMESTAMPTZ`。C API 资源管理使用 RAII，集中在 I/O 层。

账户计算可以独立使用：

```cpp
auto next = accounts::apply_fills(old_state, fills);
auto snapshots = accounts::value_accounts(event_us, next, quotes, account_params);
```

`State` 保存现金数组，以及按 `team * symbol_count + symbol` 排列的持仓数组。返回值不与旧状态共享可变缓冲区；只有外层事务提交成功后才推进状态。重复团队 / 股票的成交逐笔累加；用 128 位中间整数检查溢出，保存结果仍为 64 位整数。数值计算之外没有隐藏的共享 RNG 或全局账户。

每张表提供 `create_table`、`write_records`、`write_columns`、`export_parquet`。已有列数组可以直接调用 `write_columns`，跳过 JSON 字段转换。多个表一起写时使用 `pipeline::write_tick`；单独调用写入函数时，事务由调用方管理。

## 构建和运行

以下命令在项目根目录执行。本机已验证 macOS arm64 / AppleClang 21 / CMake Release（`-O3 -DNDEBUG`）。构建脚本也提供 macOS x86_64 和 Linux x86_64 / arm64 的固定下载，但未在这些平台执行验证；文件同步与信号处理使用 POSIX API，未实现 Windows 版本。

```bash
# Python 仅用于下载依赖；不向系统安装库
python3 database_exp/stream_ingestion_cpp/setup_deps.py
cmake -S database_exp/stream_ingestion_cpp -B database_exp/stream_ingestion_cpp/build -DCMAKE_BUILD_TYPE=Release
cmake --build database_exp/stream_ingestion_cpp/build -j 4

# 独立 C++ 示例：六轮真实一秒节拍，结束时输出一个尾批
database_exp/stream_ingestion_cpp/build/ingest_cpp \
  --input database_exp/stream_ingestion_cpp/fixtures/sample.json \
  --output database_exp/stream_ingestion_cpp/output/demo-realtime

# 生成一次 610 秒公共输入；原有环境已安装 NumPy / DuckDB
database_exp/duckdb_parquet/.venv/bin/python database_exp/stream_ingestion_cpp/generate_fixture.py \
  database_exp/stream_ingestion_cpp/output/shared-610.json

# 加速重放，输出两个 300 秒批次及 10 秒尾批
database_exp/stream_ingestion_cpp/build/ingest_cpp \
  --input database_exp/stream_ingestion_cpp/output/shared-610.json \
  --output database_exp/stream_ingestion_cpp/output/demo-fast --fast
```

输入和输出路径均拒绝覆盖已有结果；再次运行请换路径。依赖固定为 DuckDB 2.0.0 和 nlohmann/json 3.12.0，下载文件 SHA-256 写在 [setup_deps.py](setup_deps.py)。也可使用 `-DDUCKDB_DIR=/path/to/library` 指向自行安装的同版本库。C++ 程序运行时不依赖 Python / NumPy。

CLI 参数：`--input`、`--output`、`--fast`、`--seconds`、`--export-every`、`--threads`（默认 1）、`--memory-limit`（默认 8GB）。运行时长和归档间隔必须是输入写入周期的整数倍；不能超过输入已有轮数。

`--fast` 使用输入中固定的 `ingested_us`，保证两版数据可以逐值比较；真实节拍模式记录实际写入时间。行情事件时间和接收时间仍来自模拟输入，不是实时行情。C++ 默认不运行自有随机模拟器：两版读取**一次性生成的相同数据**，避免不同随机序列影响对照。

## 对照方法

```bash
database_exp/duckdb_parquet/.venv/bin/python database_exp/stream_ingestion_cpp/benchmark.py --repeats 5
```

每种负载预热一轮，再进行五轮成对测试；每轮交替 C++ / Python 执行顺序，绝不并行运行测速进程。每次使用新的持久化数据库和输出目录。两版均设置 1 个 DuckDB 线程和 8GB 内存预算；保留相同列类型、主键、NOT NULL、CHECK 约束、三表事务、新闻 fsync 和 Parquet ZSTD 压缩。

- **写入耗时 `write_ms`**：字段 / 列转换、三张表写入及 `BEGIN / COMMIT`；输入文件已读取。
- **账户计算 `calculate_ms`**：两版都从相同成交和行情重新计算现金、持仓与资产；fixture 中账户快照仅作核对依据。
- **活动总耗时 `total_active_ms`**：输入解码、数据库初始化、计算、新闻保存、三表写入、归档、运行清单和数据库关闭；排除睡眠、进程启动 / Python 导入，以及最后一份计时报告写入。
- 另记录输入解码、新闻、导出和关闭耗时。负载生成与正确性验证全部在计时之外。

对照脚本检查两版 DuckDB `source_id` 相同，核对输入 SHA-256，保存 C++ 二进制、两版源码哈希、编译器、依赖版本、每轮原始数据和中位数。每一对运行都会核对全部表值、全部约束、新闻字段与 Parquet 批次，账户另用 Python 整数独立重放。JSON 对象按结构值比较，不把键顺序当作数据差异；持仓 JSON 的分隔空白与 Python 保持一致。

## 本机实测结果（2026-10-27）

Apple Silicon / AppleClang 21，Release `-O3`；DuckDB 2.0.0，两版 source_id 均为 `d54cbbe3df`；NumPy 2.5.4。下表是五轮中位数，单位 ms；倍率为 NumPy 耗时 / C++ 耗时。

| 负载 | NumPy 三表写入 | C++ 三表写入 | 写入倍率 | NumPy 活动总耗时 | C++ 活动总耗时 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 610 轮；每轮 2 条行情、2 条账户；每 5 轮 2 笔成交（表内为累计耗时） | 361.57 | 339.34 | 1.07× | 404.45 | 365.25 |
| 1 轮；1,000 条行情 + 2 笔成交 + 2 条账户 | 3.28 | 2.94 | 1.12× | 22.44 | 19.42 |
| 1 轮；10,000 条行情 + 2 笔成交 + 2 条账户 | 17.32 | 10.07 | 1.72× | 59.94 | 42.86 |

默认小批量的三表写入，平均每轮约 0.593 ms → 0.556 ms，优势较小且样本有波动。单批一万条行情时优势更明显，写入约 1.72 倍，含读取 / 计算 / 新闻 / 归档 / 关闭的活动总耗时约 1.40 倍。

这份 C++ 实现并非每个阶段都更快：一万标的场景的账户更新与快照构造，NumPy 为 1.71 ms，C++ 为 2.93 ms。NumPy 已在底层执行数组计算，而当前 C++ 版本仍有 JSON 对象构造和逐项溢出检查。没有据此宣称 C++ 已达到最大性能，也没有把单表旧基准的 15.2 ms 与本次三表测试混为一谈。

[全部原始样本、哈希与环境](results/cpp-vs-numpy.json)保留在代码目录；[完整运行目录](output/comparison-qga5ato7/)包含 18 对运行（3 种负载 × 1 轮预热及 5 轮正式），每对都通过全部值和约束核对。`output/` 不随代码分享，原始计时 JSON 会保留。阶段各自取中位数，因此阶段中位数相加不一定等于活动总耗时中位数。

## 验证与限制

```bash
ctest --test-dir database_exp/stream_ingestion_cpp/build --output-on-failure
database_exp/duckdb_parquet/.venv/bin/python database_exp/stream_ingestion_cpp/tests/verify_io.py
database_exp/duckdb_parquet/.venv/bin/python -m unittest discover -s database_exp/stream_ingestion -p test_ingestion.py -v
```

C++ 契约测试覆盖输入不变与重复性、重复成交索引、整数溢出 / 大于 2^53 的精度、跨 DataChunk 的 5,000 行、列缓冲区类型、第三表失败回滚、重复主键回滚、JSON 对象、UTC 转换、新闻解析边界、排他归档区间、空成交文件、拒绝覆盖和失败导出不发布半批。

真实节拍测试运行六秒、临时五秒归档，六轮实际写入时间跨度 5.010 秒；另在第一次提交后发送 SIGTERM，检查一轮尾批。还独立修改标的、币种、团队排列顺序、新闻标签，并分别复制四个业务目录编译运行。[验收记录](output/validation-locy09hb/validation.txt)。C++ 契约测试和原 NumPy 的 12 项测试均通过。

这是单写者的模拟重放原型。同步导出仍会短暂占用循环；没有真实交易所接口、订单表、断点恢复、多写进程或跨 JSONL / DuckDB 的原子事务。行情、成交和账户三表处于同一事务；新闻独立落盘。目录暂存后重命名避免普通读者读到半批，不代表断电恢复保证。C++ 接口使用 C API 的收益需要按实际负载测量，不能把所有耗时都归因于 Python。

官方依据：[DuckDB C / C++ 接口边界](https://duckdb.org/docs/2.0/clients/cpp)、[C Appender](https://duckdb.org/docs/2.0/clients/c/appender)、[DataChunk](https://duckdb.org/docs/2.0/clients/c/data_chunk)、[Vectors](https://duckdb.org/docs/2.0/clients/c/vector)、[固定 DuckDB 发行版](https://github.com/duckdb/duckdb/releases/tag/v2.0.0)、[JSON 库](https://github.com/nlohmann/json/releases/tag/v3.12.0)。
