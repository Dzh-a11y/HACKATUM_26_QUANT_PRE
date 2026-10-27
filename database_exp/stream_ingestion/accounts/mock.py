"""仅用于本表的模拟数据；正式接入可以不复制此文件。"""

import numpy as np

from .transform import apply_fills, value_accounts

def initial_state(symbols, *, params):
    return {
        "teams": tuple(params.teams), "symbols": tuple(symbols),
        "cash": np.full(len(params.teams), params.initial_cash_cents, dtype=np.int64),
        "positions": np.zeros((len(params.teams), len(symbols)), dtype=np.int64),
    }


def simulate(event_time, *, fills, quotes, state, params):
    """纯函数：返回 (账户快照, 新账户状态)，不原地修改传入状态。"""
    updated = apply_fills(state, fills)
    records = value_accounts(event_time, state=updated, quotes=quotes, params=params)
    return records, updated
