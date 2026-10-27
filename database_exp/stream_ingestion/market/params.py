"""本模块的参数；复制后可以独立构造参数对象。"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class MarketParams:
    venue: str = "SIM"
    currency: str = "EUR"


    # 以下三个参数只用于模拟；正式接口接入时直接替换数据源。
    initial_prices_cents: dict = field(default_factory=lambda: {"ALPHA": 10_000, "BETA": 5_000})
    max_move_cents: int = 3
    half_spread_cents: int = 1
