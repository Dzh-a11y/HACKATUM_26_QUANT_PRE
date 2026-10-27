"""从模拟新闻的 Symbols: 行提取股票代码，逐条追加保存为 JSONL。

只需 Python 标准库和系统 awk。运行：python3 demo.py
"""

from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import tempfile


HERE = Path(__file__).resolve().parent
KNOWN_SYMBOLS = {"ALPHA", "BETA"}  # 教学用交易池，正式接口到手后替换。


def extract_symbols(raw_text):
    result = subprocess.run(
        ["awk", "-f", str(HERE / "extract_symbols.awk")],
        input=raw_text, text=True, encoding="utf-8", capture_output=True,
        check=False,
    )
    if result.returncode in (2, 3):
        # 格式错误时可能已有部分 stdout；整条 Symbols 字段按未解析处理。
        status = "malformed" if result.returncode == 2 else "missing"
        return [], status, []
    if result.returncode != 0:
        raise RuntimeError(f"awk 执行失败：{result.stderr}")
    candidates = result.stdout.splitlines()
    known = [code for code in candidates if code in KNOWN_SYMBOLS]
    unknown = [code for code in candidates if code not in KNOWN_SYMBOLS]
    status = "unknown_symbols" if unknown else ("ok" if known else "empty")
    return known, status, unknown


def utc_time(value):
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("模拟时间必须带时区")
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_news(raw_text):
    headers = {}
    body = ""
    lines = raw_text.splitlines(keepends=True)
    for index, line in enumerate(lines):
        key, separator, value = line.partition(":")
        if not separator:
            continue
        key = key.strip().lower()
        if key == "body":
            body = value.lstrip(" \t") + "".join(lines[index + 1:])
            break
        headers[key] = value.strip()

    symbols, status, unknown = extract_symbols(raw_text)
    return {
        "news_id": headers["news-id"],
        "source": "simulated_feed",
        "published_at": utc_time(headers["published-at"]),
        "received_at": utc_time(headers["received-at"]),
        "title": headers["title"],
        "body": body,
        "symbols": symbols,
        "symbol_status": status,
        "unrecognized_symbols": unknown,
        "symbol_method": "symbols_header_v1",
        "raw_text": raw_text,
    }


def append_jsonl(record, destination):
    # json.dumps 会转义正文中的换行和引号；每条新闻始终只占一行。
    with destination.open("a", encoding="utf-8", newline="\n") as file:
        file.write(json.dumps(record, ensure_ascii=False) + "\n")


def main():
    output = HERE / "output"
    output.mkdir(exist_ok=True)
    run = Path(tempfile.mkdtemp(prefix="run-", dir=output))
    destination = run / "news.jsonl"
    records = []
    for sample in sorted((HERE / "samples").glob("*.txt")):
        # newline="" 保留样本原本的换行符，raw_text 可用于复核。
        with sample.open(encoding="utf-8", newline="") as file:
            record = parse_news(file.read())
        append_jsonl(record, destination)
        records.append(record)
        print(f"{sample.name}: symbols={record['symbols']}, status={record['symbol_status']}")

    physical_lines = destination.read_text(encoding="utf-8").splitlines()
    restored = [json.loads(line) for line in physical_lines]
    if restored != records:
        raise AssertionError("JSONL 读回后与原记录不同")
    print(f"PASS: {len(records)} 条新闻 = {len(physical_lines)} 行 JSONL，中文和正文换行完整读回。")
    print(f"Saved: {destination}")


if __name__ == "__main__":
    main()
