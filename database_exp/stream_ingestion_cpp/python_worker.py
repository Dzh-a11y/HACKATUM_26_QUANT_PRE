"""对照进程：直接调用现有 NumPy 模块，重放与 C++ 相同的 fixture。"""

import argparse
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys
from time import perf_counter

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "stream_ingestion"))
import duckdb
import numpy as np
import accounts
from accounts import mock as account_mock
from accounts.transform import apply_fills, value_accounts
import market
import news
import storage
import trades


def from_us(value):
    return datetime(1970, 1, 1, tzinfo=timezone.utc) + timedelta(microseconds=value)


def run(input_path, output, *, threads=1, memory_limit="8GB"):
    total_start = perf_counter()
    start = perf_counter()
    fixture = json.loads(Path(input_path).read_text())
    if fixture["format_version"] != 1:
        raise ValueError("unsupported fixture version")
    info = fixture["metadata"]
    p = info["parameters"]
    market_params, trade_params = market.MarketParams(**p["market"]), trades.TradeParams(**p["trades"])
    account_params, news_params = accounts.AccountParams(**p["accounts"]), news.NewsParams(**p["news"])
    for data in fixture["ticks"]:
        for key in ("market", "trades", "accounts"):
            for record in data[key]:
                record["event_time"] = from_us(record["event_time"])
        data["received_us"] = from_us(data["received_us"])
        data["ingested_us"] = from_us(data["ingested_us"])
        data["event_us"] = from_us(data["event_us"])
    state = account_mock.initial_state(info["instruments"], params=account_params)
    metrics = dict(input_decode_ms=(perf_counter() - start) * 1000, calculate_ms=0, write_ms=0,
                   news_ms=0, export_ms=0, wait_ms=0, write_samples_ms=[])
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    (output / "parquet").mkdir()
    (output / "news.jsonl").touch()
    info.update(status="running", mode="accelerated", implementation="python-numpy-existing-modules",
                committed_ticks=0, committed_seconds=0, batches=[], news_records=0,
                duckdb_version=duckdb.__version__, numpy_version=np.__version__,
                runtime=dict(threads=threads, memory_limit=memory_limit))
    storage.write_json(output / "run.json", info)
    print(f"RUN_DIR={output.resolve()}", flush=True)
    step, period = info["tick_seconds"], info["export_interval_seconds"]
    simulation_start = datetime.fromisoformat(info["simulation_start"])
    db = duckdb.connect(str(output / "market.duckdb"), config={"threads": threads, "memory_limit": memory_limit})
    try:
        db.execute("SET TimeZone='UTC'")
        storage.create_tables(db)
        info["source_id"] = db.execute("SELECT source_id FROM pragma_version()").fetchall()[0][0]
        next_export = 0
        for data in fixture["ticks"]:
            tick = data["tick"]
            context = dict(tick=tick, received_at=data["received_us"], ingested_at=data["ingested_us"])
            start = perf_counter()
            next_state = apply_fills(state, data["trades"])
            snapshots = value_accounts(data["event_us"], state=next_state, quotes=data["market"], params=account_params)
            metrics["calculate_ms"] += (perf_counter() - start) * 1000
            start = perf_counter()
            info["news_records"] += news.write_records(output / "news.jsonl", data["news"], params=news_params, **context)
            metrics["news_ms"] += (perf_counter() - start) * 1000
            start = perf_counter()
            db.execute("BEGIN TRANSACTION")
            try:
                market.write_records(db, data["market"], params=market_params, **context)
                trades.write_records(db, data["trades"], params=trade_params, **context)
                accounts.write_records(db, snapshots, params=account_params, **context)
                db.execute("COMMIT")
            except BaseException:
                db.execute("ROLLBACK")
                raise
            elapsed = (perf_counter() - start) * 1000
            metrics["write_ms"] += elapsed
            metrics["write_samples_ms"].append(elapsed)
            state = next_state
            info.update(committed_ticks=tick + 1, committed_seconds=(tick + 1) * step)
            if (tick + 1) * step % period == 0:
                start = perf_counter()
                info["batches"].append(storage.export_batch(db, output / "parquet", start_tick=next_export, end_tick=tick + 1,
                                      simulation_start=simulation_start, tick_seconds=step, export_seconds=period))
                metrics["export_ms"] += (perf_counter() - start) * 1000
                next_export = tick + 1
                storage.write_json(output / "run.json", info)
        if info["committed_ticks"] > next_export:
            start = perf_counter()
            info["batches"].append(storage.export_batch(db, output / "parquet", start_tick=next_export, end_tick=info["committed_ticks"],
                                  simulation_start=simulation_start, tick_seconds=step, export_seconds=period))
            metrics["export_ms"] += (perf_counter() - start) * 1000
        info["rows"] = {module.TABLE_NAME: db.execute(f"SELECT count(*) FROM {module.TABLE_NAME}").fetchall()[0][0]
                        for module in (market, trades, accounts)}
        info["status"] = "completed"
    except BaseException as error:
        info.update(status="failed", error=str(error), metrics=metrics)
        storage.write_json(output / "run.json", info)
        raise
    finally:
        start = perf_counter()
        db.close()
        metrics["close_ms"] = (perf_counter() - start) * 1000
    metrics["total_active_ms"] = (perf_counter() - total_start) * 1000
    info["metrics"] = metrics
    storage.write_json(output / "run.json", info)
    print(f"DONE {info['rows']}", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--threads", type=int, default=1)
    parser.add_argument("--memory-limit", default="8GB")
    args = parser.parse_args()
    run(args.input, args.output, threads=args.threads, memory_limit=args.memory_limit)
