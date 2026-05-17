from dataclasses import dataclass, field
from typing import Any


@dataclass
class AppState:
    indicator_values: dict[str, dict[str, float]] = field(default_factory=dict)
    composite_scores: dict[str, Any] = field(default_factory=dict)
    active_strategy: Any | None = None
    kill_switch: bool = False
    trading_mode: str = "paper"
    daily_pnl: dict[str, float] = field(default_factory=lambda: {"paper": 0.0, "live": 0.0})
    watched_symbols: list[dict] = field(default_factory=list)
    paper_account: dict = field(default_factory=lambda: {
        "initial_capital": 10_000.0,
        "fee_rate": 0.001,      # 0.1% maker/taker (Binance standard)
        "slippage_bps": 5,      # 5 bps = 0.05%
    })


app_state = AppState()
