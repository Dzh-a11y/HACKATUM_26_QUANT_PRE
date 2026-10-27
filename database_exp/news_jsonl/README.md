# 模拟新闻：Symbols 行 → 股票代码 → JSONL

这是写入端的教学示例：系统 `awk` 解析明确的股票代码行，Python 标准库负责整理新闻和追加写入 JSONL。全部新闻、代码和格式均为模拟，不代表官方接口。

## 运行

从本目录执行，无需安装 Python 包：

```bash
python3 demo.py
```

脚本按顺序读取 [samples](samples/) 中的三条新闻，每次创建独立的 `output/run-…/news.jsonl`，避免覆盖旧结果。每收到一条样本就追加一行，然后读回核对。

| 输入文件 | 提取结果 | 状态 |
| --- | --- | --- |
| [001_single.txt](samples/001_single.txt) | `["ALPHA"]` | `ok` |
| [002_multiple.txt](samples/002_multiple.txt) | `["ALPHA", "BETA"]` | `ok`；去除重复代码 |
| [003_missing.txt](samples/003_missing.txt) | `[]` | `missing`；头部缺失，正文中的 Symbols 不参与提取 |

## 第一步：查看原始新闻

```text
News-ID: sim-001
Published-At: 2026-10-26T09:00:00Z
Received-At: 2026-10-26T09:00:02Z
Title: ALPHA 上调全年收入预期
Symbols: ALPHA

Body: ALPHA 公布新的收入指引。
管理层表示："我们预计需求会继续增长。"
```

本例约定：`Body:` 之前是头部，其后全部属于正文；标题为单行。`News-ID`、`Published-At`、`Received-At`、`Title` 是必需头部，两个时间都带时区。接收时间在本例中由模拟输入提供，实际采集时应由接收程序记录。

## 第二步：用 awk 提取 Symbols

```bash
awk -f extract_symbols.awk samples/002_multiple.txt
```

输出：

```text
ALPHA
BETA
```

[extract_symbols.awk](extract_symbols.awk) 按字段标签定位，不依赖行号；支持标签大小写、首尾空白、逗号分隔以及去重。它遇到 `Body:` 就停止读取头部，避免把正文中的类似文字误当代码。

假设的代码字符为英文字母、数字、点、下划线和短横线。代码内部不允许空格，大小写保持原样；实际字符范围和分隔符需要根据正式接口调整。重复的 Symbols 头部或非法格式会返回异常状态；缺失、显式空字段分别标记为 `missing`、`empty`。

Python 中再与教学交易池 `{ALPHA, BETA}` 核对。其他代码进入 `unrecognized_symbols`，并设置 `symbol_status = "unknown_symbols"`，不静默丢弃。原始文本一直保存在 `raw_text` 中。

## 第三步：Python 写入 JSONL

核心代码位于 [demo.py](demo.py) 的 `append_jsonl`：

```python
with destination.open("a", encoding="utf-8", newline="\n") as file:
    file.write(json.dumps(record, ensure_ascii=False) + "\n")
```

- `"a"` 表示追加；一条新闻对应一次写入。
- `ensure_ascii=False` 使中文保持可读。
- `json.dumps` 负责转义正文的换行和双引号，不手动拼 JSON。
- 不使用 `indent`，保证每条记录只有一个物理行。

一行中的 `body` 和 `raw_text` 可能出现 `\n`、`\"`；JSON 解析后会恢复原来的换行和引号。

输出字段为 `news_id`、`source`、`published_at`、`received_at`、`title`、`body`、`symbols`、`symbol_status`、`unrecognized_symbols`、`symbol_method`、`raw_text`。

## 打开结果

JSONL 是 UTF-8 文本，可用编辑器直接打开。也可以在本目录执行下面的代码，选择最近修改的运行目录，把每条记录展开显示：

```bash
python3 - <<'PY'
from pathlib import Path
import json

path = max(Path("output").glob("run-*/news.jsonl"), key=lambda p: p.stat().st_mtime_ns)
print(path)
for line in path.read_text(encoding="utf-8").splitlines():
    print(json.dumps(json.loads(line), ensure_ascii=False, indent=2))
PY
```

## 验证与范围

2026-10-26 已用 Python 3.14.7 和本机 `/usr/bin/awk` 验证：三条样本对应三行 JSONL，逐行读回后与写入前的完整记录一致；中文、引号、正文换行及原始文本均保留。

额外核查了 CRLF 换行、标签大小写与空白、重复代码、正文中的伪字段、空字段、代码内空格、末尾逗号、重复头部、未知代码，以及连续追加和时区转换。全部通过。

本次本地输出：[news.jsonl](output/run-l240tabc/news.jsonl)；核查记录：[verification.txt](output/run-l240tabc/verification.txt)。`output/` 是忽略的生成目录；重新运行会生成另一个独立目录。

这是单写进程、有限样本的示例。每条新闻启动一次 awk 是为了清楚展示工具分工；真实高频流可改为常驻解析器或直接在 Python 内解析。此处不处理并发写入、采集重试去重、崩溃恢复或缺失必需元数据的输入；JSONL 追加也没有额外的 `fsync` 持久化承诺。Symbols 缺失或格式异常不会阻止符合其他格式要求的新闻保存。
