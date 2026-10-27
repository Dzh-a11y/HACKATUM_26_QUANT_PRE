"""本表的建表、字段映射、写入和 Parquet 导出。"""

import numpy as np

from .columns import COLUMN_NAMES, INTEGER_COLUMNS, records_to_columns

TABLE_NAME = "market_quotes"


def create_table(db):
    db.execute("""
        CREATE TABLE IF NOT EXISTS market_quotes (
            tick BIGINT NOT NULL,
            event_time TIMESTAMPTZ NOT NULL,
            received_at TIMESTAMPTZ NOT NULL,
            ingested_at TIMESTAMPTZ NOT NULL,
            instrument_id VARCHAR NOT NULL,
            venue VARCHAR NOT NULL,
            currency VARCHAR NOT NULL,
            bid_cents BIGINT NOT NULL CHECK (bid_cents > 0),
            ask_cents BIGINT NOT NULL CHECK (ask_cents >= bid_cents),
            bid_size BIGINT NOT NULL CHECK (bid_size > 0),
            ask_size BIGINT NOT NULL CHECK (ask_size > 0),
            PRIMARY KEY (tick, instrument_id, venue)
        )
    """)


def write_records(db, records, *, tick, received_at, ingested_at, params):
    columns = records_to_columns(records, tick=tick, received_at=received_at, ingested_at=ingested_at, params=params)
    return write_columns(db, columns)


def write_columns(db, columns):
    """I/O：整批插入 NumPy 数组；调用方管理事务，不逐条执行 INSERT。"""
    if set(columns) != set(COLUMN_NAMES):
        raise ValueError("列名必须与本表 COLUMN_NAMES 完全一致")
    if any(not isinstance(column, np.ndarray) or column.ndim != 1 for column in columns.values()):
        raise ValueError("每列必须是一维 NumPy 数组")
    count = len(columns[COLUMN_NAMES[0]])
    if any(len(column) != count for column in columns.values()):
        raise ValueError("各列长度必须一致")
    if count:
        # DuckDB replacement scan 读取此局部变量，不创建需要清理的临时视图。
        # 文本统一为 object：避免 NumPy Unicode → ENUM → JSON 的语义变化。
        _stream_market_numpy = {name: columns[name] if name in INTEGER_COLUMNS
                                else np.asarray(columns[name], dtype=object) for name in COLUMN_NAMES}
        db.execute("INSERT INTO market_quotes BY NAME SELECT * FROM _stream_market_numpy")
    return count


def export_parquet(db, path, *, start_tick, end_tick):
    """只导出 [start_tick, end_tick)，不会删除源表。"""
    count = db.execute("SELECT count(*) FROM market_quotes WHERE tick >= ? AND tick < ?", [start_tick, end_tick]).fetchall()[0][0]
    db.execute("""
        COPY (SELECT * FROM market_quotes WHERE tick >= ? AND tick < ?)
        TO ? (FORMAT PARQUET, COMPRESSION ZSTD)
    """, [start_tick, end_tick, str(path)])
    return count
