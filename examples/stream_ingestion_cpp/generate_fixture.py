"""只生成一次模拟输入，两种实现读取同一文件；整数时间单位为 UTC 微秒。"""

import argparse
from dataclasses import asdict, replace
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import sys

PYTHON_ROOT = Path(__file__).resolve().parent.parent / "stream_ingestion"
sys.path.insert(0, str(PYTHON_ROOT))
import mock_source
import settings


def timestamp_us(value):
    delta = value - datetime(1970, 1, 1, tzinfo=timezone.utc)
    return (delta.days * 86400 + delta.seconds) * 1_000_000 + delta.microseconds


def generate(path, *, seconds=610, symbols=2, teams=2, step=1, export_every=300):
    if min(seconds, symbols, teams, step, export_every) < 1 or seconds % step or export_every % step:
        raise ValueError("positive counts and whole tick intervals required")
    instruments = ["ALPHA", "BETA"] if symbols == 2 else [f"S{i:05d}" for i in range(symbols)]
    team_names = ("TEAM_A", "TEAM_B") if teams == 2 else tuple(f"TEAM_{i:04d}" for i in range(teams))
    params = dict(
        market_params=replace(settings.MARKET, initial_prices_cents={symbol: 10000 + i * 10 for i, symbol in enumerate(instruments)}),
        trade_params=replace(settings.TRADES, teams=team_names),
        account_params=replace(settings.ACCOUNTS, teams=team_names),
        news_params=replace(settings.NEWS, known_symbols=tuple(instruments)),
    )
    start = datetime(2026, 10, 26, 9, tzinfo=timezone.utc)
    state = mock_source.initial_state(**params)
    ticks = []
    for tick in range(seconds // step):
        event = start + timedelta(seconds=tick * step)
        batch, state = mock_source.read_tick(tick, event, state=state, seed=42, **params)
        ticks.append(dict(tick=tick, event_us=timestamp_us(event), received_us=timestamp_us(event) + 20000,
                          ingested_us=timestamp_us(event) + 30000,
                          market=batch.market_records, trades=batch.trade_records,
                          accounts=batch.account_records, news=batch.news_records))
    metadata = dict(
        format_version=2, simulation_start=start.isoformat(), requested_seconds=seconds,
        tick_seconds=step, export_interval_seconds=export_every, seed=42,
        teams=list(team_names), instruments=instruments, currency=params["account_params"].currency,
        initial_cash_cents_per_team=params["account_params"].initial_cash_cents,
        initial_positions_per_team=dict.fromkeys(instruments, 0),
        parameters={name: asdict(params[key]) for name, key in
                    [("market", "market_params"), ("trades", "trade_params"), ("accounts", "account_params"), ("news", "news_params")]},
    )
    value = dict(format_version=1, metadata=metadata, ticks=ticks)
    content = json.dumps(value, default=timestamp_us, ensure_ascii=False, separators=(",", ":")) + "\n"
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as file:
        file.write(content)
    return hashlib.sha256(content.encode()).hexdigest()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--seconds", type=int, default=610)
    parser.add_argument("--symbols", type=int, default=2)
    parser.add_argument("--teams", type=int, default=2)
    parser.add_argument("--write-every", type=int, default=1)
    parser.add_argument("--export-every", type=int, default=300)
    args = parser.parse_args()
    print(generate(args.output, seconds=args.seconds, symbols=args.symbols, teams=args.teams,
                   step=args.write_every, export_every=args.export_every))
