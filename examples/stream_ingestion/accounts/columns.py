"""纯函数：把本表记录整理为 NumPy 列数组；不访问数据库。"""

import numpy as np

from .transform import parse_record

COLUMN_NAMES = ("tick","event_time","received_at","ingested_at","team_id","currency","cash_cents","positions","equity_cents","pnl_cents",)
INTEGER_COLUMNS = frozenset(["tick","cash_cents","equity_cents","pnl_cents"])


def records_to_columns(records, *, tick, received_at, ingested_at, params):
    rows = [parse_record(raw, tick=tick, received_at=received_at, ingested_at=ingested_at, params=params)
            for raw in records]
    if not rows:
        return {name: np.array([], dtype=np.int64 if name in INTEGER_COLUMNS else object)
                for name in COLUMN_NAMES}
    # 文本 / JSON / 带时区 datetime 保持 object；防止固定宽字符串截断或丢失时区。
    # 数字由 NumPy 推断；None 保持 NULL，交给数据库约束拒绝，不静默变成 0。
    return {name: np.asarray(values) if name in INTEGER_COLUMNS else np.asarray(values, dtype=object)
            for name, values in zip(COLUMN_NAMES, zip(*rows))}
