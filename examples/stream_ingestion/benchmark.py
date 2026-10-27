"""比较旧逐行写入与批量写入；每次独立建库，输出可复现的本机实测记录。"""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import platform
from statistics import median
import tempfile
from time import perf_counter

import duckdb
import numpy as np

from accounts.transform import mark_to_market
import market
import settings


def write_executemany(db, records, context):
    """优化前的路径，保留相同字段转换、约束和事务。"""
    rows = [market.parse_record(record, **context) for record in records]
    db.executemany("INSERT INTO market_quotes VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", rows)


def write_appender(db, records, context):
    rows = [market.parse_record(record, **context) for record in records]
    with db.appender("market_quotes") as appender:
        appender.append_rows(rows)


def benchmark_writes(directory, count, repeats):
    now = datetime(2026, 10, 26, 9, tzinfo=timezone.utc)
    context = dict(tick=0, received_at=now, ingested_at=now, params=settings.MARKET)
    records = [dict(event_time=now, instrument_id=f"S{i:08d}", bid_cents=10000 + i,
                    ask_cents=10002 + i, bid_size=50, ask_size=60) for i in range(count)]
    columns = market.records_to_columns(records, **context)
    expected = [market.parse_record(record, **context) for record in records]
    methods = {
        "old_executemany_records": lambda db: write_executemany(db, records, context),
        "new_write_records": lambda db: market.write_records(db, records, **context),
        "numpy_columns_ready": lambda db: market.write_columns(db, columns),
        "appender_records": lambda db: write_appender(db, records, context),
    }
    timings = {name: [] for name in methods}
    # 第一轮只预热；之后轮换顺序，减小固定执行顺序的影响。
    for repetition in range(repeats + 1):
        names = list(methods)
        offset = repetition % len(names)
        for name in names[offset:] + names[:offset]:
            path = directory / f"{count}-{repetition}-{name}.duckdb"
            with duckdb.connect(str(path)) as db:
                db.execute("SET TimeZone='UTC'")
                market.create_table(db)
                start = perf_counter()
                db.execute("BEGIN")
                methods[name](db)
                db.execute("COMMIT")
                elapsed = perf_counter() - start
                assert db.execute("SELECT * FROM market_quotes ORDER BY instrument_id").fetchall() == expected
                if repetition:
                    timings[name].append(elapsed * 1000)
    result = {"rows_per_transaction": count, "median_ms": {name: median(values) for name, values in timings.items()},
              "samples_ms": timings, "all_rows_equal": True}
    old, new = result["median_ms"]["old_executemany_records"], result["median_ms"]["new_write_records"]
    result["record_path_speedup"] = old / new
    print(f"rows={count}: old={old:.3f}ms new={new:.3f}ms speedup={old / new:.2f}x", flush=True)
    return result


def benchmark_valuation(repeats):
    rng = np.random.default_rng(42)
    cash = np.full(256, 10_000_000, dtype=np.int64)
    positions = rng.integers(-100, 101, size=(256, 512), dtype=np.int64)
    marks = rng.integers(100, 100_001, size=512, dtype=np.int64)
    cash_list, quantities, prices = cash.tolist(), positions.tolist(), marks.tolist()

    def python_loop():
        return [balance + sum(quantity * price for quantity, price in zip(row, prices))
                for balance, row in zip(cash_list, quantities)]

    expected = python_loop()
    np.testing.assert_array_equal(mark_to_market(cash, positions, marks), expected)
    timings = {}
    for name, function in (("python_loop", python_loop), ("numpy_int64", lambda: mark_to_market(cash, positions, marks))):
        function()
        values = []
        for _ in range(repeats):
            start = perf_counter()
            for _ in range(20):
                function()
            values.append((perf_counter() - start) * 1000 / 20)
        timings[name] = median(values)
    return {"teams": 256, "symbols": 512, "median_ms": timings,
            "speedup": timings["python_loop"] / timings["numpy_int64"], "values_equal": True,
            "scope": "仅估值数值核心，包含溢出上界检查；两侧输入均预先准备，不含记录 / JSON 序列化"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--sizes", type=int, nargs="+", default=[2, 1000, 10000])
    args = parser.parse_args()
    if args.repeats < 1 or min(args.sizes) < 1:
        parser.error("重复次数和批次大小必须为正")
    root = Path(__file__).parent / "output"
    root.mkdir(exist_ok=True)
    report_dir = Path(tempfile.mkdtemp(prefix="benchmark-", dir=root)).resolve()
    with tempfile.TemporaryDirectory() as temporary:
        writes = [benchmark_writes(Path(temporary), count, args.repeats) for count in args.sizes]
    result = {"measured_at": datetime.now(timezone.utc).isoformat(),
              "python": platform.python_version(), "platform": platform.platform(),
              "duckdb": duckdb.__version__, "numpy": np.__version__, "repeats": args.repeats,
              "writes": writes, "valuation": benchmark_valuation(args.repeats),
              "scope": "本机单表持久化写入，包含 BEGIN/COMMIT、字段转换和约束；不含建库、生成模拟数据、Parquet 或新闻。numpy_columns_ready 已在计时前转换。不能等同整条链路吞吐。"}
    (report_dir / "results.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(f"BENCHMARK_DIR={report_dir}", flush=True)
    print(json.dumps(result["valuation"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
