"""入口只调度：每秒接收 → 新闻 JSONL / 三表事务 → 每五分钟归档。"""

import argparse
from dataclasses import asdict, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
import signal
import tempfile
import threading
import time

import duckdb
import numpy as np

import mock_source
import news
import settings
import storage


def run(*, runtime=settings.RUNTIME, market_params=settings.MARKET,
        trade_params=settings.TRADES, account_params=settings.ACCOUNTS,
        news_params=settings.NEWS, stop=None):
    step = runtime.write_every_seconds
    period = runtime.export_every_seconds
    if min(step, period, runtime.duration_seconds) < 1:
        raise ValueError("写入间隔、归档间隔、运行时长必须为正整数秒")
    if period % step or runtime.duration_seconds % step:
        raise ValueError("归档间隔和运行时长必须是写入间隔的整数倍")
    total_ticks, export_ticks = runtime.duration_seconds // step, period // step
    stop = stop if stop is not None else threading.Event()
    source_params = dict(market_params=market_params, trade_params=trade_params,
                         account_params=account_params, news_params=news_params)
    state = mock_source.initial_state(**source_params)
    Path(runtime.output_dir).mkdir(parents=True, exist_ok=True)
    directory = Path(tempfile.mkdtemp(prefix="run-", dir=runtime.output_dir)).resolve()
    parquet_root = directory / "parquet"
    parquet_root.mkdir()
    news_path = directory / "news.jsonl"
    news_path.touch()
    start = datetime.now(timezone.utc).replace(microsecond=0)
    info = {
        "format_version": 2, "status": "running",
        "mode": "accelerated" if runtime.fast else "realtime",
        "simulation_start": start.isoformat(), "requested_seconds": runtime.duration_seconds,
        "tick_seconds": step, "committed_ticks": 0, "committed_seconds": 0,
        "export_interval_seconds": period, "seed": runtime.seed,
        "teams": list(account_params.teams), "instruments": list(market_params.initial_prices_cents),
        "currency": account_params.currency, "initial_cash_cents_per_team": account_params.initial_cash_cents,
        "initial_positions_per_team": dict.fromkeys(market_params.initial_prices_cents, 0),
        "parameters": {
            "market": asdict(market_params), "trades": asdict(trade_params),
            "accounts": asdict(account_params), "news": asdict(news_params),
        },
        "batches": [], "news_records": 0, "duckdb_version": duckdb.__version__,
        "numpy_version": np.__version__, "simulation_version": "numpy-v1",
    }
    storage.write_json(directory / "run.json", info)
    print(f"RUN_DIR={directory}", flush=True)
    print(f"MODE={info['mode']}; write={step}s; export={period}s; duration={runtime.duration_seconds}s", flush=True)
    next_export_start = 0
    try:
        with duckdb.connect(str(directory / "market.duckdb"), config={"memory_limit": runtime.memory_limit}) as db:
            db.execute("SET TimeZone = 'UTC'")
            storage.create_tables(db)
            timer_start = time.monotonic()
            for tick in range(total_ticks):
                if stop.is_set():
                    break
                event_time = start + timedelta(seconds=tick * step)
                batch, next_state = mock_source.read_tick(
                    tick, event_time, state=state, seed=runtime.seed, **source_params,
                )
                # 模拟接收时间。接入真实 API 时在实际收到消息时记录 received_at。
                received_at = event_time + timedelta(milliseconds=runtime.simulated_receive_delay_ms)
                ingested_at = datetime.now(timezone.utc)
                context = dict(tick=tick, received_at=received_at, ingested_at=ingested_at)
                info["news_records"] += news.write_records(news_path, batch.news_records, params=news_params, **context)
                counts = storage.write_tick(
                    db, batch, market_params=market_params, trade_params=trade_params,
                    account_params=account_params, **context,
                )
                state = next_state  # 提交成功后才推进内存中的模拟状态。
                info["committed_ticks"] = tick + 1
                info["committed_seconds"] = (tick + 1) * step
                if tick == 0 or info["committed_seconds"] % 60 == 0:
                    print(f"COMMIT seconds={info['committed_seconds']}: {counts}", flush=True)
                if not runtime.fast:
                    stop.wait(max(0, timer_start + (tick + 1) * step - time.monotonic()))
                if (tick + 1) % export_ticks == 0:
                    info["batches"].append(storage.export_batch(
                        db, parquet_root, start_tick=next_export_start, end_tick=tick + 1,
                        simulation_start=start, tick_seconds=step, export_seconds=period,
                    ))
                    next_export_start = tick + 1
                    storage.write_json(directory / "run.json", info)
            if info["committed_ticks"] > next_export_start:
                info["batches"].append(storage.export_batch(
                    db, parquet_root, start_tick=next_export_start, end_tick=info["committed_ticks"],
                    simulation_start=start, tick_seconds=step, export_seconds=period,
                ))
            info["rows"] = {
                module.TABLE_NAME: db.execute(f"SELECT count(*) FROM {module.TABLE_NAME}").fetchall()[0][0]
                for module in storage.TABLE_MODULES
            }
            info["status"] = "completed" if info["committed_ticks"] == total_ticks else "stopped"
            info["elapsed_wall_seconds"] = round(time.monotonic() - timer_start, 3)
    except BaseException as error:
        info.update(status="failed", error=f"{type(error).__name__}: {error}")
        storage.write_json(directory / "run.json", info)
        raise
    storage.write_json(directory / "run.json", info)
    print(f"DONE {info['status']}: {info['rows']}; news={info['news_records']}", flush=True)
    return directory


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seconds", type=int, default=settings.RUNTIME.duration_seconds)
    parser.add_argument("--fast", action="store_true", default=settings.RUNTIME.fast)
    parser.add_argument("--output-dir", type=Path, default=settings.RUNTIME.output_dir)
    parser.add_argument("--write-every", type=int, default=settings.RUNTIME.write_every_seconds)
    parser.add_argument("--export-every", type=int, default=settings.RUNTIME.export_every_seconds)
    args = parser.parse_args()
    runtime = replace(settings.RUNTIME, duration_seconds=args.seconds, fast=args.fast,
                      output_dir=args.output_dir, write_every_seconds=args.write_every,
                      export_every_seconds=args.export_every)
    if min(args.seconds, args.write_every, args.export_every) < 1 or args.seconds % args.write_every or args.export_every % args.write_every:
        parser.error("时间参数必须为正整数，时长和归档间隔必须是写入间隔的整数倍")
    stop = threading.Event()
    previous = {number: signal.signal(number, lambda *_: stop.set()) for number in (signal.SIGINT, signal.SIGTERM)}
    try:
        run(runtime=runtime, stop=stop)
    finally:
        for number, handler in previous.items():
            signal.signal(number, handler)


if __name__ == "__main__":
    main()
