"""纯函数模拟数据入口：显式输入旧状态，返回当秒数据和新状态。"""

from dataclasses import dataclass

from accounts import mock as account_mock
from market import mock as market_mock
from news import mock as news_mock
from trades import mock as trade_mock


@dataclass(frozen=True)
class TickBatch:
    market_records: list
    trade_records: list
    account_records: list
    news_records: list


def initial_state(*, market_params, trade_params, account_params, news_params):
    if set(trade_params.teams) != set(account_params.teams):
        raise ValueError("模拟成交与账户参数中的团队必须一致")
    if not market_params.initial_prices_cents or not news_params.known_symbols:
        raise ValueError("模拟标的不能为空")
    if not account_params.teams or len(set(account_params.teams)) != len(account_params.teams) or len(set(trade_params.teams)) != len(trade_params.teams):
        raise ValueError("团队不能为空或重复")
    if min(market_params.initial_prices_cents.values()) <= 0:
        raise ValueError("模拟初始价格必须为正")
    if trade_params.every_n_ticks < 1 or news_params.every_n_ticks < 1:
        raise ValueError("模拟事件间隔必须大于零")
    if market_params.max_move_cents < 0 or market_params.half_spread_cents < 1:
        raise ValueError("模拟价格波动不能为负，半价差必须为正")
    if trade_params.max_quantity < 1 or trade_params.fee_cents < 0:
        raise ValueError("模拟成交数量必须为正，手续费不能为负")
    if not (market_params.currency == trade_params.currency == account_params.currency):
        raise ValueError("本例只支持单币种模拟")
    return {
        "prices": market_mock.initial_state(params=market_params),
        "accounts": account_mock.initial_state(market_params.initial_prices_cents, params=account_params),
    }


def read_tick(tick, event_time, *, state, seed, market_params, trade_params, account_params, news_params):
    """相同输入给出相同输出；时间、种子、配置、状态全部由调用方提供。"""
    quotes, prices = market_mock.simulate(event_time, prices=state["prices"], seed=seed + tick * 2, params=market_params)
    fills = trade_mock.simulate(tick, event_time, quotes=quotes, positions=state["accounts"]["positions"],
                               team_ids=state["accounts"]["teams"], symbols=state["accounts"]["symbols"],
                               seed=seed + tick * 2 + 1, params=trade_params)
    snapshots, updated_accounts = account_mock.simulate(event_time, fills=fills, quotes=quotes, state=state["accounts"], params=account_params)
    messages = news_mock.simulate(tick, event_time, params=news_params)
    return TickBatch(quotes, fills, snapshots, messages), {"prices": prices, "accounts": updated_accounts}
