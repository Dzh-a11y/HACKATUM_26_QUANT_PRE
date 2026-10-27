"""仅用于本表的模拟数据；正式接入可以不复制此文件。"""

import numpy as np


def initial_state(*, params):
    return {
        "symbols": tuple(params.initial_prices_cents),
        "mid_cents": np.array(list(params.initial_prices_cents.values()), dtype=np.int64),
    }


def simulate(event_time, *, prices, seed, params):
    """纯函数：给定价格、种子、时间，返回记录和新价格；不修改 prices。"""
    rng = np.random.default_rng(seed)
    symbols, previous = prices["symbols"], prices["mid_cents"]
    if int(previous.max()) + params.max_move_cents + params.half_spread_cents > np.iinfo(np.int64).max:
        raise OverflowError("模拟价格超出 int64 范围")
    mids = np.maximum(params.half_spread_cents + 1,
                      previous + rng.integers(-params.max_move_cents, params.max_move_cents + 1, size=len(symbols)))
    bids, asks = mids - params.half_spread_cents, mids + params.half_spread_cents
    sizes = rng.integers(10, 101, size=(2, len(symbols)))
    # 仅在记录接口边界转 Python 标量；计算过程保持连续 int64 数组。
    records = [{
            "event_time": event_time, "instrument_id": symbol,
            "bid_cents": bid, "ask_cents": ask,
            "bid_size": bid_size, "ask_size": ask_size,
        } for symbol, bid, ask, bid_size, ask_size in
        zip(symbols, bids.tolist(), asks.tolist(), sizes[0].tolist(), sizes[1].tolist())]
    return records, {"symbols": symbols, "mid_cents": mids}
