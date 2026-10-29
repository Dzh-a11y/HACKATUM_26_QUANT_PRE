# 数据库实验台

本机 Web 前端，观察 `database_exp/stream_ingestion_cpp` 的实际数据处理过程，并查看现有 Python / NumPy 数据源、表结构和技术实现证据。文档与界面使用中文。

实验分支：`codex/database-workbench`。本实验的代码、构建、输出均在本目录；原有实验的代码与配置不作修改。C++ 观测入口直接链接原有计算、字段转换、建表、批量写入和归档函数，没有新增 SIMD 或并行计算算法。

## 启动与使用

从仓库任意位置运行：

```bash
sh /Users/douzihao/CLionProjects/HACKATUM_26_QUANT_PRE/database_exp/workbench/launch.sh
```

打开 [本地实验台](http://127.0.0.1:8765)。默认使用已有 `../duckdb_parquet/.venv/bin/python`，依赖为现有 DuckDB、NumPy、pytz；C++ 使用已有 `../stream_ingestion_cpp/vendor`。不增加前端依赖，不下载库，不注册或发布云端站点。需要 macOS、CMake、C++20 编译器。

右上角“关闭实验台”会停止当前实验 / 采样并退出本地服务进程，释放监听端口；页面停止轮询，已有记录保留。先等待任务正常收尾，最多 15 秒，随后终止该任务独立进程组内的剩余子进程，必要时强制结束；不影响其他 Python 或数据库进程。再次使用时重新执行上述启动命令并刷新页面。“停止”按钮只停止当前任务，服务继续运行。

更换 Python 或端口：

```bash
WORKBENCH_PYTHON=/path/to/python sh launch.sh --port 8766
```

启动时检查构建，后续每次运行也核对 C++ 源码版本；仅页面变化不触发 C++ 重编译。若修改 Python 服务逻辑，需要重启服务。默认配置为 12 轮、32 个标的、2 个团队、1 个 DuckDB 线程预算、每 5 轮归档。

- **实验总览**：运行 / 停止、累计性能、处理行次 / 秒、逐阶段耗时和计数器、正确性校验。
- **数据处理流程**：输入解码、初始化、账户计算、新闻解析与写入、三表各自转列 / 写入、事务、状态推进、节拍等待、归档和关闭；查看逐次耗时和最近事件。归档内部三表导出与发布暂为一个观测阶段。
- **数据源与输出**：生成参数、固定种子 42、输入哈希、指定 tick 原始数据；结束后预览三张持久表和新闻 JSONL。
- **表结构与字段**：`market_quotes`（11 字段）、`team_trades`（13）、`account_snapshots`（10），及独立早期示例的 `quotes_batch`（9）。展示字段类型、主键、NOT NULL 和 CHECK。新闻 JSONL 的 13 个字段单列为文件格式，不能当作数据库表。
- **技术实现证据**：原始源码与行号、哈希、DataChunk 批量写入、线程预算、NumPy 数组计算、事务、归档及 Clang 向量化报告。
- **运行记录**：独立目录保留参数、结果、原始事件、校验日志与构建来源，可导出 JSON 报告。

“1 秒 / 轮”控制回放节拍，仍保留 fixture 的固定模拟写入时间，不把它当实际采集时间。运行清单使用 `paced-fixture` 标记。Python 生成器已有账户快照仅作参考，C++ 从相同行情和成交重新计算账户。

## macOS 性能采集口径

本机没有 Linux `perf stat`。使用公开 macOS SDK 的 `proc_pid_rusage(RUSAGE_INFO_V4)` 与 `getrusage(RUSAGE_SELF)`；本机已取得非零 instructions / cycles。

| 指标 | 数据来源及口径 |
| --- | --- |
| instructions、cycles | 同一进程的累计计数器前后做差；覆盖该阶段时间窗口内整个进程，包括内部线程 |
| IPC | 同一阶段 instructions / cycles；多次调用按计数器总和计算；零 cycles 时为缺失 |
| wall / user / system 时间 | 单调时钟及 getrusage；CPU 时间为所有进程线程之和，可能大于墙钟时间 |
| minor / major faults | getrusage 的 ru_minflt / ru_majflt 增量；不是 cache misses |
| voluntary / involuntary context switches | getrusage 的 ru_nvcsw / ru_nivcsw 增量 |
| RSS、线程数 | 阶段结束时的进程快照；总览只取已采样线程数最大值，不能作为持续并行工作的证明 |
| cache misses、branch misses、CPU migrations | 当前适配器不采集，保留 null / 未采集，不能填 0 |

计时边界包括采样调用的部分开销，短阶段尤其敏感；内核累计计数器有自己的统计粒度。日志写出在阶段计时外，但仍影响总体运行与缓存状态。各阶段相加也不等于完整进程耗时：准备、运行清单写入、采样间隙等没有全部作为阶段计数。生成阶段属于独立 Python 进程，不计入 C++ 汇总；等待单列排除。

数据表的“处理行次”是各阶段调用输入量，不能跨阶段相加当作唯一记录数。某些控制 / 归档阶段尚无行数口径，显示 0 行次，吞吐显示缺失。P95 使用 nearest-rank，小样本仅供观察。超过 JavaScript 安全整数范围的值在 API 中编码为十进制字符串。

当前机器只有 Command Line Tools，`xcrun xctrace list templates` 不可用。若后续接入 Instruments CPU Counters，需要另行实现事件和阶段对齐；本版本不宣称已完成该通道，也不要求 sudo 或改变系统安全设置。

依据：[Apple XNU Recount](https://github.com/apple-oss-distributions/xnu/blob/main/doc/observability/recount.md)、[Apple CPU Counters](https://developer.apple.com/documentation/xcode/addressing-cpu-bottlenecks)、[Xcode 命令行工具边界](https://developer.apple.com/documentation/xcode/installing-the-command-line-tools/)。

## 对照与证据

“函数热点”页对账户估值、账户转列、行情写入分别进行栈采样，展示函数自身 / 含子调用的样本占比、可展开调用树和原始报告。Mac 使用系统 `sample`，不是 Linux `perf record`。选择已完成运行作为数据源，每阶段采样 1–10 秒；使用优化构建、调试符号和原业务函数。详见 [函数采样的范围与使用说明](profiling/README.md)。采样结果存放在 `output/profiles/<id>/`，与正常运行互斥；已有报告可直接浏览，重新采样需要本机进程采样权限。

勾选“追加 C++ / Python 对照与逐值校验”后，观测运行结束，再串行运行原 C++ CLI 和原 Python worker。两版使用同一 fixture、线程预算、1 GB DuckDB 内存预算、事务、约束和归档配置；确认 DuckDB `source_id` 相同。

对照耗时来自原始、没有逐阶段观测的程序；不拿观测入口的计时与原 Python 比速度。当前是一轮探索性运行，没有预热与多轮统计，不作稳定加速结论。原验证器核对两版三表、全部约束、JSONL、输入 fixture 与所有 Parquet 值；也将观测版逐值对照到同一 Python 输出。

Clang 使用 `-Rpass=loop-vectorize -Rpass-missed=loop-vectorize` 输出具体循环的编译决定。本机报告同时出现已向量化和未向量化的循环，页面保留源码位置，不将它概括为整个程序已启用或未启用 SIMD。未测量运行时 SIMD 指令比例，也不推断预编译 DuckDB 内部路径。

证据页展示当前工作区源码和启动时读取的编译报告；每次运行自己的源码哈希和二进制哈希保存在报告中。历史结果须以该次报告为准，后续修改源码时不能把当前代码当作旧运行的精确版本。

## 文件与边界

```text
workbench/
├── app.py / job.py             # 本地 API、单次实验调度
├── catalog.py / probe.py       # 源码与 schema、Python 原生计数器
├── build.py / CMakeLists.txt   # 独立构建和来源清单
├── native/                    # C++ 观测入口及计数器
├── dist/                      # HTML / CSS / JS，无打包依赖
├── tests/                     # 真实进程与存储契约检查
├── build/                     # 忽略：二进制、编译日志与哈希
└── output/<run-id>/            # 忽略：每次独立输入与结果
    ├── config.json / job.json / provenance.json
    ├── fixture.json / generation.json
    ├── observed/              # trace.jsonl、run.json、DuckDB、JSONL、Parquet
    ├── baseline_cpp/          # 勾选对照时生成
    ├── baseline_python/
    ├── comparison.json
    └── worker.log
```

服务只监听 `127.0.0.1`，拒绝跨域写请求；命令、源码文件和表名通过固定参数 / 白名单处理，不提供任意 SQL、任意文件访问或 shell 执行接口。一次只管理一个实验。停止请求让 C++ 在轮次边界退出并导出已提交尾批；崩溃和强制终止不保证尾批发布。新闻独立落盘，三表事务失败不会回滚新闻。

运行中的 DuckDB 由写入进程持有；页面不另开连接抢读，结束或停止后才展示表数据。固定规模上限用于本机交互实验，大规模性能研究应使用原 benchmark 并控制环境。

## 验证

```bash
../duckdb_parquet/.venv/bin/python build.py
../duckdb_parquet/.venv/bin/python -m unittest discover -s tests -v
node --check dist/app.js
node --check dist/profile-ui.js
```

测试覆盖真实计数器返回或缺失、原 DDL 的字段与约束、参数与大整数、观测版对照 Python 全值及 Parquet、真实节拍停止与尾批、重复成交触发事务回滚及错误事件。不会修改原实验代码。

函数采样测试额外验证阶段外 / 后台线程样本排除、递归函数的 inclusive 去重、self 样本守恒、空样本和无效调用树拒绝，以及阶段白名单和采样时长边界。
