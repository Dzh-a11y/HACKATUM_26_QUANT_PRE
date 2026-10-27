"""写入程序停止后独立核查：归档边界、全部值、新闻和账户资金 / 仓位。"""

import argparse
from datetime import datetime, timedelta
import json
from pathlib import Path

import duckdb


TABLE_KEYS = {
    "market_quotes": "tick, instrument_id, venue",
    "team_trades": "tick, trade_id",
    "account_snapshots": "tick, team_id",
}


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def verify(directory):
    directory = Path(directory).resolve()
    info = json.loads((directory / "run.json").read_text(encoding="utf-8"))
    require(info["status"] in ("completed", "stopped"), "只核查已正常结束的运行")
    ticks = info["committed_ticks"]
    step = info["tick_seconds"]
    period = info["export_interval_seconds"]
    start_time = datetime.fromisoformat(info["simulation_start"])
    batches = sorted((directory / "parquet").glob("batch_*"))
    require([path.name for path in batches] == info["batches"], "批次清单与目录不符")
    boundary = 0
    reports = []
    with duckdb.connect(str(directory / "market.duckdb"), read_only=True) as connection:
        connection.execute("SET TimeZone = 'UTC'")
        require({row[0] for row in connection.execute("SHOW TABLES").fetchall()} == set(TABLE_KEYS), "必须正好三张表")
        for batch in batches:
            manifest = json.loads((batch / "manifest.json").read_text(encoding="utf-8"))
            end = manifest["end_tick_exclusive"]
            require(manifest["start_tick"] == boundary and boundary < end <= ticks, "批次重叠、缺口或越界")
            require((end - boundary) * step <= period, "单批超过配置间隔")
            require(manifest["complete_interval"] == ((end - boundary) * step == period), "尾批标记错误")
            require(datetime.fromisoformat(manifest["start_time"]) == start_time + timedelta(seconds=boundary * step), "批次起点时间错误")
            require(datetime.fromisoformat(manifest["end_time_exclusive"]) == start_time + timedelta(seconds=end * step), "批次终点时间错误")
            for table, keys in TABLE_KEYS.items():
                expected = connection.execute(
                    f"SELECT * FROM {table} WHERE tick >= ? AND tick < ? ORDER BY {keys}",
                    [boundary, end],
                ).fetchall()
                actual = connection.execute(
                    f"SELECT * FROM read_parquet(?) ORDER BY {keys}",
                    [str(batch / f"{table}.parquet")],
                ).fetchall()
                require(actual == expected, f"{batch.name}/{table} 内容不一致")
                require(len(actual) == manifest["rows"][table], "清单行数错误")
            boundary = end
        require(boundary == ticks, "末尾数据未归档")

        expected_counts = {
            "market_quotes": ticks * len(info["instruments"]),
            "team_trades": len(range(0, ticks, info["parameters"]["trades"]["every_n_ticks"])) * len(info["teams"]),
            "account_snapshots": ticks * len(info["teams"]),
        }
        for table, expected in expected_counts.items():
            count = connection.execute(f"SELECT count(*) FROM {table}").fetchall()[0][0]
            require(count == expected == info["rows"][table], f"{table} 丢失或重复记录")
            bad_time = connection.execute(
                f"SELECT count(*) FROM {table} WHERE event_time != ?::TIMESTAMPTZ + tick * ? * INTERVAL '1 second' "
                "OR received_at < event_time", [info["simulation_start"], step],
            ).fetchall()[0][0]
            require(bad_time == 0, "模拟事件时间或接收时间错误")
        reports.append(f"PASS: exactly three tables, counts={expected_counts}")
        reports.append(f"PASS: {len(batches)} non-overlapping batches cover ticks [0, {ticks}); every Parquet value matches DuckDB.")

        # 独立从初始账户和成交重放，不借用模拟器的账户计算函数。
        marks = {
            (tick, symbol): (bid + ask) // 2
            for tick, symbol, bid, ask in connection.execute(
                "SELECT tick, instrument_id, bid_cents, ask_cents FROM market_quotes"
            ).fetchall()
        }
        trades = {}
        for row in connection.execute(
            "SELECT tick, team_id, instrument_id, side, quantity, price_cents, fee_cents "
            "FROM team_trades ORDER BY tick, trade_id"
        ).fetchall():
            trades.setdefault(row[0], []).append(row[1:])
        cash = dict.fromkeys(info["teams"], info["initial_cash_cents_per_team"])
        positions = {team: info["initial_positions_per_team"].copy() for team in info["teams"]}
        last_tick = -1
        snapshots = connection.execute(
            "SELECT tick, team_id, cash_cents, positions, equity_cents, pnl_cents "
            "FROM account_snapshots ORDER BY tick, team_id"
        ).fetchall()
        for tick, team, stored_cash, stored_positions, equity, pnl in snapshots:
            if tick != last_tick:
                for trade_team, symbol, side, quantity, price, fee in trades.get(tick, []):
                    signed = quantity if side == "BUY" else -quantity
                    cash[trade_team] -= signed * price + fee
                    positions[trade_team][symbol] += signed
                last_tick = tick
            expected_equity = cash[team] + sum(quantity * marks[tick, symbol] for symbol, quantity in positions[team].items())
            require(stored_cash == cash[team], "现金与成交不一致")
            require(json.loads(stored_positions) == positions[team], "持仓与成交不一致")
            require(equity == expected_equity, "总资产与行情估值不一致")
            require(pnl == expected_equity - info["initial_cash_cents_per_team"], "盈亏与初始资产不一致")
        reports.append("PASS: all account snapshots independently reconcile with fills, fees and midpoint marks.")
        if ticks > 1 and info["mode"] == "realtime":
            span = connection.execute(
                "SELECT epoch(max(ingested_at) - min(ingested_at)) FROM market_quotes"
            ).fetchall()[0][0]
            require(span >= (ticks - 1) * step * 0.8, "实际运行没有按一秒节拍写入")
            reports.append(f"PASS: real ingestion timestamp span={span:.3f}s across {ticks} ticks.")

    lines = (directory / "news.jsonl").read_text(encoding="utf-8").splitlines()
    news = [json.loads(line) for line in lines]
    expected_ticks = list(range(0, ticks, info["parameters"]["news"]["every_n_ticks"]))
    require(len(news) == info["news_records"] == len(expected_ticks), "新闻行数错误")
    require([item["tick"] for item in news] == expected_ticks, "新闻缺失或重复")
    for index, item in enumerate(news):
        configured = info["parameters"]["news"]["known_symbols"]
        symbols, status = [([configured[0]], "ok"), (list(dict.fromkeys(configured)), "ok"), ([], "missing")][index % 3]
        require((item["symbols"], item["symbol_status"]) == (symbols, status), "Symbols 提取错误")
        require('\n' in item["body"] and '"下一期将公布更多信息。"' in item["body"], "正文换行或引号丢失")
        require("Body:" in item["raw_text"], "没有保留新闻原文")
    reports.append(f"PASS: {len(news)} valid JSONL lines; Symbols, original text, Chinese and newlines preserved.")
    report = "\n".join(reports) + "\n"
    (directory / "verification.txt").write_text(report, encoding="utf-8")
    print(report, end="")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path, help="已停止写入的 output/run-* 目录")
    verify(parser.parse_args().directory)
