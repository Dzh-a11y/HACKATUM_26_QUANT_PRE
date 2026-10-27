"""本模块的参数；复制后可以独立构造参数对象。"""

from dataclasses import dataclass


@dataclass(frozen=True)
class TradeParams:
    venue: str = "SIM"
    currency: str = "EUR"
    # 模拟参数；实盘 / 比赛中手续费和成交价格应由成交回报提供。
    teams: tuple = ("TEAM_A", "TEAM_B")
    every_n_ticks: int = 5
    max_quantity: int = 5
    fee_cents: int = 1
