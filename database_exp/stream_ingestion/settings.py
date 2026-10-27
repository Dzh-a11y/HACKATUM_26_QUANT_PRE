"""比赛前集中调参数；每张表的参数定义仍在自己的文件里。"""

from dataclasses import dataclass
from pathlib import Path

from accounts import AccountParams
from market import MarketParams
from news import NewsParams
from trades import TradeParams


@dataclass(frozen=True)
class RuntimeParams:
    write_every_seconds: int = 1
    export_every_seconds: int = 300
    duration_seconds: int = 600
    memory_limit: str = "8GB"
    output_dir: Path = Path(__file__).resolve().parent / "output"
    fast: bool = False
    seed: int = 42
    simulated_receive_delay_ms: int = 20


RUNTIME = RuntimeParams()

MARKET = MarketParams(
    venue="SIM", currency="EUR",
    initial_prices_cents={"ALPHA": 10_000, "BETA": 5_000},
    max_move_cents=3, half_spread_cents=1,
)

TRADES = TradeParams(
    teams=("TEAM_A", "TEAM_B"), venue="SIM", currency="EUR",
    every_n_ticks=5, max_quantity=5, fee_cents=1,
)

ACCOUNTS = AccountParams(
    teams=("TEAM_A", "TEAM_B"), currency="EUR", initial_cash_cents=10_000_000,
)

NEWS = NewsParams(
    known_symbols=("ALPHA", "BETA"), symbols_field="Symbols",
    source="simulated_feed", every_n_ticks=60, fsync=True,
)
