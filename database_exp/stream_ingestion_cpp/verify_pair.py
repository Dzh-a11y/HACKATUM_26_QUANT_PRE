"""计时之外核对两版数据库、表约束、Parquet 和新闻；JSON 按结构值比较。"""

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "stream_ingestion"))
import duckdb
import accounts
import market
import news
import trades
from verify_run import TABLE_KEYS, verify


def normalize(rows, table):
    if table != "account_snapshots":
        return rows
    return [tuple(json.loads(value) if i == 7 else value for i, value in enumerate(row)) for row in rows]


def inspect(path):
    result = {}
    with duckdb.connect(str(Path(path) / "market.duckdb"), read_only=True) as db:
        db.execute("SET TimeZone='UTC'")
        for table, keys in TABLE_KEYS.items():
            result[table] = normalize(db.execute(f"SELECT * FROM {table} ORDER BY {keys}").fetchall(), table)
        result["columns"] = db.execute("SELECT table_name, column_name, data_type, is_nullable, column_default FROM information_schema.columns WHERE table_schema='main' ORDER BY table_name, ordinal_position").fetchall()
        result["constraints"] = db.execute("SELECT table_name, constraint_type, constraint_text FROM duckdb_constraints() WHERE schema_name='main' ORDER BY ALL").fetchall()
    result["news"] = [json.loads(line) for line in (Path(path) / "news.jsonl").read_text().splitlines()]
    return result


def verify_pair(fixture_path, numpy_dir, cpp_dir):
    verify(numpy_dir)
    verify(cpp_dir)
    numpy_data, cpp_data = inspect(numpy_dir), inspect(cpp_dir)
    for key in numpy_data:
        if numpy_data[key] != cpp_data[key]:
            raise AssertionError(f"C++/NumPy mismatch: {key}")
    fixture = json.loads(Path(fixture_path).read_text())
    parameters = fixture["metadata"]["parameters"]
    epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
    convert = lambda us: epoch + timedelta(microseconds=us)
    modules = [("market", market, market.MarketParams(**parameters["market"])),
               ("trades", trades, trades.TradeParams(**parameters["trades"])),
               ("accounts", accounts, accounts.AccountParams(**parameters["accounts"]))]
    for name, module, params in modules:
        expected = []
        for data in fixture["ticks"]:
            for raw in data[name]:
                raw = {**raw, "event_time": convert(raw["event_time"])}
                expected.append(module.parse_record(raw, tick=data["tick"], received_at=convert(data["received_us"]),
                                                    ingested_at=convert(data["ingested_us"]), params=params))
        indices = {"market": (0, 4, 5), "trades": (1, 0), "accounts": (0, 4)}[name]
        expected.sort(key=lambda row: tuple(row[i] for i in indices))
        if normalize(expected, module.TABLE_NAME) != cpp_data[module.TABLE_NAME]:
            raise AssertionError(f"fixture value mismatch: {name}")
    expected_news = [news.parse_record(raw, tick=data["tick"], received_at=convert(data["received_us"]),
                                      ingested_at=convert(data["ingested_us"]), params=news.NewsParams(**parameters["news"]))
                     for data in fixture["ticks"] for raw in data["news"]]
    if cpp_data["news"] != expected_news:
        raise AssertionError("news differs from fixture parser")
    report = "PASS: identical columns and all PK/NOT NULL/CHECK constraints; every table value and JSONL record matches the common fixture; each Parquet batch matches its database. JSON objects compare structurally.\n"
    for directory in (numpy_dir, cpp_dir):
        (Path(directory) / "pair_verification.txt").write_text(report)
    print(report, end="")


if __name__ == "__main__":
    if len(sys.argv) != 4:
        raise SystemExit("usage: verify_pair.py fixture.json numpy_run cpp_run")
    verify_pair(*sys.argv[1:])
