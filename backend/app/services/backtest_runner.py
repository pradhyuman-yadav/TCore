from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import pandas as pd

from app.services.aggregator import classify_zone, compute_composite_score
from app.services.indicator_engine import IndicatorConfig, IndicatorDef, compute_indicators
from app.services.rule_engine import TradeSignal, evaluate_rules

_MIN_WARMUP_BARS = 30


@dataclass
class BacktestTrade:
    bar_index: int
    time: datetime
    side: str        # "buy" | "sell"
    price: float
    quantity: float
    pnl: float | None = None


@dataclass
class BacktestResult:
    symbol: str
    exchange: str
    total_bars: int
    trades: list[BacktestTrade] = field(default_factory=list)
    equity_curve: list[float] = field(default_factory=list)

    # Summary stats — populated by _compute_stats
    total_pnl: float = 0.0
    win_rate: float = 0.0
    num_trades: int = 0
    max_drawdown: float = 0.0
    sharpe_ratio: float | None = None

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "exchange": self.exchange,
            "total_bars": self.total_bars,
            "num_trades": self.num_trades,
            "total_pnl": round(self.total_pnl, 4),
            "win_rate": round(self.win_rate, 4),
            "max_drawdown": round(self.max_drawdown, 4),
            "sharpe_ratio": round(self.sharpe_ratio, 4) if self.sharpe_ratio is not None else None,
            "equity_curve": [round(v, 4) for v in self.equity_curve],
            "trades": [
                {
                    "bar_index": t.bar_index,
                    "time": t.time.isoformat(),
                    "side": t.side,
                    "price": t.price,
                    "quantity": t.quantity,
                    "pnl": round(t.pnl, 4) if t.pnl is not None else None,
                }
                for t in self.trades
            ],
        }


_SHORT_TO_FULL = {
    "macd":   "macd_hist",
    "bb":     "bb_position",
    "ema":    "ema_cross",
    "volume": "volume_surge",
}


def _build_indicator_config(strategy_config: dict) -> IndicatorConfig:
    tech_names = {"rsi", "macd_hist", "bb_position", "volume_surge", "ema_cross"}
    defs = []

    indicators_cfg = strategy_config.get("indicators")
    if indicators_cfg:
        # New format: {"indicators": {"rsi": {"weight": 0.5, ...}, ...}}
        for name, cfg in indicators_cfg.items():
            full_name = _SHORT_TO_FULL.get(name, name)
            if full_name not in tech_names:
                continue
            weight = float(cfg.get("weight", 0.0)) if isinstance(cfg, dict) else 0.0
            params = {
                k: v
                for k, v in (cfg.items() if isinstance(cfg, dict) else {})
                if k not in ("weight", "cache_ttl_minutes")
            }
            defs.append(IndicatorDef(name=full_name, weight=weight, params=params))
    else:
        # StrategyBuilder flat format: {"weights": {"rsi": 0.25, "macd": 0.20, ...}}
        weights_cfg = strategy_config.get("weights", {})
        for name, weight in weights_cfg.items():
            full_name = _SHORT_TO_FULL.get(name, name)
            if full_name not in tech_names:
                continue
            defs.append(IndicatorDef(name=full_name, weight=float(weight), params={}))

    return IndicatorConfig(indicators=defs)


def _compute_stats(result: BacktestResult, initial_capital: float) -> None:
    """Fills summary fields on result in-place."""
    sell_trades = [t for t in result.trades if t.side == "sell" and t.pnl is not None]
    result.num_trades = len(sell_trades)
    result.total_pnl = sum(t.pnl for t in sell_trades)  # type: ignore[arg-type]

    if sell_trades:
        wins = sum(1 for t in sell_trades if t.pnl and t.pnl > 0)
        result.win_rate = wins / len(sell_trades)

    # Max drawdown from equity curve
    if result.equity_curve:
        peak = result.equity_curve[0]
        max_dd = 0.0
        for v in result.equity_curve:
            if v > peak:
                peak = v
            dd = (peak - v) / peak if peak > 0 else 0.0
            max_dd = max(max_dd, dd)
        result.max_drawdown = max_dd

    # Simplified Sharpe: mean daily return / std
    if len(result.equity_curve) > 2:
        returns = pd.Series(result.equity_curve).pct_change().dropna()
        std = float(returns.std())
        if std > 1e-10:
            result.sharpe_ratio = float(returns.mean() / std * (252 ** 0.5))


def run_backtest(
    ohlcv: pd.DataFrame,
    strategy_config: dict,
    initial_capital: float = 10_000.0,
    fee_rate: float = 0.001,
    slippage_bps: float = 0.0,
) -> BacktestResult:
    """
    Walk-forward backtest over a pre-loaded OHLCV DataFrame.
    Uses only past bars at each step — no look-ahead.
    Sentiment indicators are skipped (no LLM calls during backtest).
    Never raises.
    """
    symbol: str = strategy_config.get("symbol", "UNKNOWN")
    exchange: str = strategy_config.get("exchange", "unknown")
    indicator_config = _build_indicator_config(strategy_config)

    weights: dict[str, float] = {ind.name: ind.weight for ind in indicator_config.indicators}
    # StrategyBuilder stores thresholds at root; legacy format uses "rules" sub-dict
    rules_cfg = strategy_config.get("rules", {})
    raw_buy  = strategy_config.get("buy_threshold")  or rules_cfg.get("buy_threshold",  0.45)
    raw_sell = strategy_config.get("sell_threshold") or rules_cfg.get("sell_threshold", 0.35)
    buy_threshold  = float(raw_buy)
    sell_threshold = -abs(float(raw_sell))  # always negative: sell when score < -X
    sizing = strategy_config.get("position_sizing", {})
    amount_usdt = float(sizing.get("amount", 100.0))
    max_open = int(sizing.get("max_open_positions", 1))
    risk_cfg = strategy_config.get("risk", {})
    max_daily_loss = float(risk_cfg.get("max_daily_loss_usdt", 200.0))

    result = BacktestResult(symbol=symbol, exchange=exchange, total_bars=len(ohlcv))

    capital = initial_capital
    daily_pnl = 0.0
    open_position: BacktestTrade | None = None
    equity = capital

    for i in range(_MIN_WARMUP_BARS, len(ohlcv)):
        window = ohlcv.iloc[: i + 1]
        price = float(window["close"].iloc[-1])
        bar_time = window.index[i] if isinstance(window.index[i], datetime) else datetime.utcfromtimestamp(0)
        try:
            bar_time = pd.Timestamp(ohlcv.index[i]).to_pydatetime()
        except Exception:
            bar_time = datetime.utcnow()

        # Indicator values
        try:
            ind_values = compute_indicators(window, indicator_config)
        except Exception:
            result.equity_curve.append(round(equity, 4))
            continue

        composite = compute_composite_score(ind_values, weights)
        if composite is None:
            result.equity_curve.append(round(equity, 4))
            continue

        zone = classify_zone(composite, buy_threshold, sell_threshold)
        open_positions_count = 1 if open_position is not None else 0

        signal: TradeSignal = evaluate_rules(
            zone=zone,
            kill_switch=False,
            open_positions=open_positions_count,
            daily_pnl=daily_pnl,
            strategy_config=strategy_config,
        )

        slip = slippage_bps / 10_000

        if signal.action == "buy" and open_position is None:
            fill_price = price * (1 + slip)
            qty = amount_usdt / fill_price
            buy_fee = fill_price * qty * fee_rate
            equity -= buy_fee          # fee paid immediately on entry
            open_position = BacktestTrade(
                bar_index=i, time=bar_time, side="buy", price=fill_price, quantity=qty
            )
            result.trades.append(open_position)

        elif signal.action == "sell" and open_position is not None:
            qty = open_position.quantity
            fill_price = price * (1 - slip)
            sell_fee = fill_price * qty * fee_rate
            gross_pnl = (fill_price - open_position.price) * qty
            net_pnl = gross_pnl - sell_fee
            sell_trade = BacktestTrade(
                bar_index=i, time=bar_time, side="sell", price=fill_price, quantity=qty, pnl=net_pnl
            )
            result.trades.append(sell_trade)
            daily_pnl += net_pnl
            equity += net_pnl
            open_position = None

        result.equity_curve.append(round(equity, 4))

    # Close any open position at last bar's price (mark-to-market, no fee)
    if open_position is not None and len(ohlcv) > 0:
        last_price = float(ohlcv["close"].iloc[-1])
        pnl = (last_price - open_position.price) * open_position.quantity
        open_position.pnl = pnl
        equity += pnl

    _compute_stats(result, initial_capital)
    return result
