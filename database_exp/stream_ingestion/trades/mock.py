"""仅用于本表的模拟数据；正式接入可以不复制此文件。"""

import numpy as np


def simulate(tick, event_time, *, quotes, positions, team_ids, symbols, seed, params):
    """纯函数：固定输入得到固定成交，不修改持仓或外部随机数状态。"""
    if tick % params.every_n_ticks:
        return []
    rng = np.random.default_rng(seed)
    team_lookup = {team: i for i, team in enumerate(team_ids)}
    symbol_lookup = {symbol: i for i, symbol in enumerate(symbols)}
    quote_indices = (tick // params.every_n_ticks + np.arange(len(params.teams))) % len(quotes)
    selected = [quotes[i] for i in quote_indices]
    team_indices = [team_lookup[team] for team in params.teams]
    symbol_indices = [symbol_lookup[quote["instrument_id"]] for quote in selected]
    quantities = rng.integers(1, params.max_quantity + 1, size=len(params.teams))
    sides = np.where(positions[team_indices, symbol_indices] >= quantities, "SELL", "BUY")
    prices = np.where(sides == "BUY", [q["ask_cents"] for q in selected], [q["bid_cents"] for q in selected])
    return [{
            "trade_id": f"sim-{tick:08d}-{team}", "event_time": event_time,
            "team_id": team, "instrument_id": quote["instrument_id"], "side": side,
            "quantity": quantity,
            "price_cents": price,
            "fee_cents": params.fee_cents,
        } for team, quote, quantity, side, price in zip(
            params.teams, selected, quantities.tolist(), sides.tolist(), prices.tolist())]
