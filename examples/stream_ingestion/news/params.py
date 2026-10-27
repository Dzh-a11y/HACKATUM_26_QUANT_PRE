"""新闻处理参数。"""

from dataclasses import dataclass


@dataclass(frozen=True)
class NewsParams:
    known_symbols: tuple = ("ALPHA", "BETA")
    symbols_field: str = "Symbols"
    source: str = "simulated_feed"
    fsync: bool = True
    every_n_ticks: int = 60  # 仅用于模拟新闻生成频率。
