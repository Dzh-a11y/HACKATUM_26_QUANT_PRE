"""纯函数：只转换传入数据，不读时钟、不访问数据库、不修改输入。"""

def parse_record(raw, *, tick, received_at, ingested_at, params):
    """只接收实际成交；比赛时在这里改官方字段映射。成交 ID 需全局唯一。"""
    return (
        raw["trade_id"], tick, raw["event_time"], received_at, ingested_at,
        raw["team_id"], raw["instrument_id"], raw.get("venue", params.venue),
        raw.get("currency", params.currency), raw["side"], raw["quantity"],
        raw["price_cents"], raw["fee_cents"],
    )
