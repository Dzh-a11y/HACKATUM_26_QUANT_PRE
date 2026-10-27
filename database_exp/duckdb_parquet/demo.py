"""模拟行情 → 两个 Parquet 文件 → 新 DuckDB 连接直接查询。

运行：.venv/bin/python demo.py
依赖 duckdb 和用于读取带时区时间的 pytz；所有行情均为教学模拟。
"""

from datetime import datetime, timedelta, timezone
from pathlib import Path
import random
import tempfile

import duckdb


HERE = Path(__file__).resolve().parent
START = datetime(2026, 10, 26, 9, 0, tzinfo=timezone.utc)
SECONDS = 600
SCHEMA = """
    event_time TIMESTAMPTZ,
    received_at TIMESTAMPTZ,
    symbol VARCHAR,
    venue VARCHAR,
    bid_ticks INTEGER,
    ask_ticks INTEGER,
    bid_size INTEGER,
    ask_size INTEGER,
    seq BIGINT
"""


def simulate_quotes():
    """固定种子；每秒为两只股票各生成 X、Y 两个市场的报价快照。"""
    rng = random.Random(42)
    mid_prices = {"ALPHA": 10000, "BETA": 5000}
    rows = []
    for second in range(SECONDS):
        event_time = START + timedelta(seconds=second)
        for symbol in mid_prices:
            mid_prices[symbol] += rng.randint(-2, 2)
            # 人为制造短暂的跨市场价格差，方便演示 JOIN；不是市场模型。
            offset_y = 6 if 10 <= second % 60 < 20 else rng.choice((-1, 0, 1))
            for venue, offset in (("X", 0), ("Y", offset_y)):
                mid = mid_prices[symbol] + offset
                half_spread = rng.choice((1, 2))
                received_at = event_time + timedelta(milliseconds=rng.randint(10, 40))
                rows.append((
                    event_time, received_at, symbol, venue,
                    mid - half_spread, mid + half_spread,
                    rng.randint(10, 100), rng.randint(10, 100), len(rows) + 1,
                ))
    return rows


def save_batches(rows, directory):
    """每五分钟写一个文件。DuckDB 临时表用于组织数据，持久化在 Parquet。"""
    with duckdb.connect(":memory:") as writer:
        writer.execute("SET TimeZone = 'UTC'")
        writer.execute(f"CREATE TABLE quotes_batch ({SCHEMA})")
        batch_size = 300 * 2 * 2
        for batch_no, start in enumerate(range(0, len(rows), batch_size), start=1):
            writer.execute("DELETE FROM quotes_batch")
            writer.executemany(
                "INSERT INTO quotes_batch VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                rows[start:start + batch_size],
            )
            destination = directory / f"quotes_{batch_no:02d}.parquet"
            writer.execute(
                "COPY quotes_batch TO ? (FORMAT PARQUET, COMPRESSION ZSTD)",
                [str(destination)],
            )


def render_query(connection, sql):
    """把 SQL 和实际结果一起展示，便于对照阅读；无需 pandas。"""
    cursor = connection.execute(sql)
    columns = [column[0] for column in cursor.description]
    rows = cursor.fetchall()
    # 解析器可能把下一条语句前的注释放入当前片段；展示时只保留 SQL。
    displayed_sql = "\n".join(
        line for line in sql.splitlines() if not line.lstrip().startswith("--")
    ).strip()
    # EXPLAIN 的结果包含多行查询计划，原样显示更易读。
    if columns == ["explain_key", "explain_value"]:
        return displayed_sql + "\n\n" + "\n".join(str(row[1]) for row in rows)
    cells = [[str(value) for value in row] for row in rows]
    widths = [max(len(name), *(len(row[i]) for row in cells))
              if cells else len(name) for i, name in enumerate(columns)]
    table = [" | ".join(name.ljust(widths[i]) for i, name in enumerate(columns))]
    table.append("-+-".join("-" * width for width in widths))
    table.extend(" | ".join(value.ljust(widths[i]) for i, value in enumerate(row))
                 for row in cells)
    return displayed_sql + "\n\n" + "\n".join(table)


def main():
    output = HERE / "output"
    output.mkdir(exist_ok=True)
    # 每次创建新目录，既不覆盖旧结果，也不会把不同运行的文件混在一起查。
    directory = Path(tempfile.mkdtemp(prefix="run-", dir=output))
    rows = simulate_quotes()
    save_batches(rows, directory)

    report = [
        f"DuckDB {duckdb.__version__} | synthetic quotes | seed=42",
        f"Output: {directory}",
        "2 symbols x 2 venues x 600 seconds = 2400 rows; 1 tick = EUR 0.01.",
        "Synchronized synthetic snapshots only; no executable-profit claim.",
    ]
    for path in sorted(directory.glob("quotes_*.parquet")):
        report.append(f"{path.name}: {path.stat().st_size:,} bytes")

    # 保存连接已经关闭；用全新的内存数据库从磁盘文件读取。
    with duckdb.connect(":memory:") as reader:
        reader.execute("SET TimeZone = 'UTC'")
        reader.read_parquet(str(directory / "quotes_*.parquet")).create_view("quotes")

        # 核查落盘再读取后，所有值及时间精度是否与输入一致。
        restored = reader.execute("SELECT * FROM quotes ORDER BY seq").fetchall()
        if restored != rows:
            raise AssertionError("Parquet round-trip did not preserve the input rows")
        report.append("PASS: all 2400 rows preserved after closing and reopening the connection.")

        # SQL 文件中的语句由 DuckDB 自己解析，支持注释和多个语句。
        statements = reader.extract_statements(
            (HERE / "queries.sql").read_text(encoding="utf-8")
        )
        for number, statement in enumerate(statements, start=1):
            report.append(f"Query {number}\n" + render_query(reader, statement.query))

    text = "\n\n".join(report) + "\n"
    (directory / "results.txt").write_text(text, encoding="utf-8")
    print(text)
    print(f"Saved query results: {directory / 'results.txt'}")


if __name__ == "__main__":
    main()
