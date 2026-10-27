"""纯函数：只转换传入数据，不读时钟、不访问数据库、不修改输入。"""

import json

import numpy as np


def parse_record(raw, *, tick, received_at, ingested_at, params):
    """正式接口有账户快照时直接映射这里，不必使用下面的 simulate。"""
    return (
        tick, raw["event_time"], received_at, ingested_at, raw["team_id"],
        raw.get("currency", params.currency), raw["cash_cents"],
        json.dumps(raw["positions"], ensure_ascii=False), raw["equity_cents"], raw["pnl_cents"],
    )


def apply_fills(state, fills):
    """纯函数：(旧账户状态, 成交) → 新账户状态；旧状态及成交保持不变。"""
    updated = {**state, "cash": state["cash"].copy(), "positions": state["positions"].copy()}
    if not fills:
        return updated
    teams = {team: i for i, team in enumerate(state["teams"])}
    symbols = {symbol: i for i, symbol in enumerate(state["symbols"])}
    team_indices = np.array([teams[fill["team_id"]] for fill in fills], dtype=np.intp)
    symbol_indices = np.array([symbols[fill["instrument_id"]] for fill in fills], dtype=np.intp)
    sides = np.array([fill["side"] for fill in fills])
    if not np.all((sides == "BUY") | (sides == "SELL")):
        raise ValueError("成交方向必须为 BUY / SELL")
    quantities = np.array([fill["quantity"] for fill in fills], dtype=np.int64)
    prices = np.array([fill["price_cents"] for fill in fills], dtype=np.int64)
    fees = np.array([fill["fee_cents"] for fill in fills], dtype=np.int64)
    if np.any(quantities <= 0) or np.any(prices <= 0) or np.any(fees < 0):
        raise ValueError("成交数量 / 价格必须为正，手续费不能为负")
    # 保守上界先用 Python 整数计算，避免 int64 运算静默溢出。
    quantity_bound = len(fills) * int(quantities.max())
    cash_bound = quantity_bound * int(prices.max()) + len(fills) * int(fees.max())
    _check_bound(_max_abs(state["cash"]) + cash_bound)
    _check_bound(_max_abs(state["positions"]) + quantity_bound)
    signed = np.where(sides == "BUY", quantities, -quantities)
    # 重复的团队 / 股票索引也要逐笔累加，不能用 fancy indexing 的 +=。
    np.add.at(updated["positions"], (team_indices, symbol_indices), signed)
    np.add.at(updated["cash"], team_indices, -(signed * prices + fees))
    return updated


def value_accounts(event_time, *, state, quotes, params):
    """纯函数：按买卖中间价估值，输出独立快照，不修改输入账户。"""
    marks_by_symbol = {quote["instrument_id"]: (quote["bid_cents"] + quote["ask_cents"]) // 2 for quote in quotes}
    marks = np.array([marks_by_symbol[symbol] for symbol in state["symbols"]], dtype=np.int64)
    equity = mark_to_market(state["cash"], state["positions"], marks)
    _check_bound(_max_abs(equity) + abs(params.initial_cash_cents))
    pnl = equity - params.initial_cash_cents
    return [{
        "event_time": event_time, "team_id": team, "cash_cents": cash,
        "positions": dict(zip(state["symbols"], quantities)),
        "equity_cents": value, "pnl_cents": profit,
    } for team, cash, quantities, value, profit in zip(
        state["teams"], state["cash"].tolist(), state["positions"].tolist(), equity.tolist(), pnl.tolist())]


def mark_to_market(cash, positions, marks):
    """纯数值核心：(团队现金, 团队×股票持仓, 股票价格) → 各团队总资产。"""
    if any(values.dtype != np.dtype(np.int64) for values in (cash, positions, marks)):
        raise TypeError("现金、持仓、价格必须使用 int64 数组")
    if cash.ndim != 1 or marks.ndim != 1 or positions.shape != (len(cash), len(marks)):
        raise ValueError("要求现金[T]、持仓[T, S]、价格[S]，且轴顺序一致")
    _check_bound(_max_abs(cash) + positions.shape[1] * _max_abs(positions) * _max_abs(marks))
    return cash + positions @ marks


def _max_abs(values):
    return max(abs(int(values.min())), abs(int(values.max()))) if values.size else 0


def _check_bound(value):
    if value > np.iinfo(np.int64).max:
        raise OverflowError("账户运算可能超出 int64 范围，请缩小单位 / 数量或改用更宽数值类型")
