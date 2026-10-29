# 函数热点采样

对原有 `accounts::value_accounts`、`accounts::records_to_columns`、`market::write_columns` 进行调用栈采样。macOS 使用 `/usr/bin/sample`，不是 Linux `perf record`，无需安装新工具或使用 sudo。

采样程序读取某次实验的同一份 fixture，第 0 轮先通过账户参考值检查，再分别重复三个阶段。为收集足够样本，每个阶段使用独立进程。代码调用原有函数，`profile_*` 非内联包装只用于在采样栈中定位阶段。编译使用 Release `-O3`、调试信息和 frame pointer，保留正常优化和内联；因此部分函数可能合并在调用者中，预编译 DuckDB 的内部源码位置可能缺失。

## 展示口径

- **自身样本占比**：目标阶段样本中，栈顶落在此函数的比例。
- **包含子调用的占比**：目标阶段样本中，调用栈包含此函数的比例；不同函数不能相加。递归同名函数在每条栈上只计一次。
- **调用树**：只保留经过该阶段 `profile_*` 包装的子树，排除初始化、准备输入、结果销毁、其他阶段、后台线程及标记外事务控制。
- `sample` 观察线程调用栈，也可能采到等待 / I/O；这些是栈样本占比，不能直接称为纯 CPU 时间、单次调用毫秒数或调用次数。
- 固定输入重复运行会改变缓存和分配器状态；这是定位阶段内部热点的实验，不是完整流水线时间分配或生产吞吐测试。
- 行情写入重复使用预先转换的列，保留原表约束。BEGIN / ROLLBACK 位于标记外，避免不断增长数据库；不包括 COMMIT、完整三表事务和真实归档。DuckDB 后台线程不在主线程标记栈里，因此报告不是该阶段全部线程的总 CPU 开销。
- 未采到目标标记时报告失败，不以全进程热点冒充阶段热点；原始样本、函数表、树和 folded stacks 一起保存。

## 输出与复现

输出位于 `../output/profiles/<id>/`，包含 `job.json`、各阶段 `*.sample.txt`、`*.sampler.log`、`*.json`、`*.folded`、worker 日志及临时数据库。来源清单保存 fixture、源码和二进制哈希以及编译参数。

实验台“函数热点”页可选择已完成的输入运行、采样秒数和阶段。一次仅运行一个实验或采样任务。服务启动在受限执行环境时，系统可能拒绝采样；在普通终端运行 `sh ../launch.sh` 使用正常用户进程权限。应用不会自动提权或修改系统设置。

官方说明：[Apple sample 采样工具](https://developer.apple.com/library/archive/documentation/Performance/Conceptual/CodeSpeed/Articles/DiagnosingSlowness.html)、[采样计数与执行时间的区别](https://developer.apple.com/tutorials/instruments/determining-execution-frequency)。本机 `man sample` 是具体命令参数和线程采样语义的直接依据。
