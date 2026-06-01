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
    # High-water mark of account equity per mode — feeds the drawdown circuit breaker
    peak_equity: dict[str, float] = field(default_factory=lambda: {"paper": 0.0, "live": 0.0})
    watched_symbols: list[dict] = field(default_factory=list)
    # Hawkes OFI — updated by refit_hawkes_job; served by /hawkes/pressure
    hawkes_pressure: dict[str, float] = field(default_factory=dict)   # symbol → pressure
    hawkes_regime:   dict[str, str]   = field(default_factory=dict)   # symbol → 'stable'|'reflexive'
    paper_account: dict = field(default_factory=lambda: {
        "initial_capital": 10_000.0,
        "fee_rate": 0.001,      # 0.1% maker/taker (Binance standard)
        "slippage_bps": 5,      # 5 bps = 0.05%
    })


app_state = AppState()
