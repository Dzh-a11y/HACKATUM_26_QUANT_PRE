"""本模块的参数；复制后可以独立构造参数对象。"""

from dataclasses import dataclass


@dataclass(frozen=True)
class AccountParams:
    currency: str = "EUR"
    teams: tuple = ("TEAM_A", "TEAM_B")
    initial_cash_cents: int = 10_000_000  # 模拟每队 EUR 100,000，初始持仓零。
