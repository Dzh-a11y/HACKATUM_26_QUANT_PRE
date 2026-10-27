"""纯函数：只转换传入数据，不读时钟、不访问数据库、不修改输入。"""

def parse_record(raw, *, tick, received_at, ingested_at, params):
    """比赛时主要改这里：把官方字段名 / 单位映射到本表。价格单位是分。"""
    return (
        tick, raw["event_time"], received_at, ingested_at,
        raw["instrument_id"], raw.get("venue", params.venue),
        raw.get("currency", params.currency), raw["bid_cents"], raw["ask_cents"],
        raw["bid_size"], raw["ask_size"],
    )
