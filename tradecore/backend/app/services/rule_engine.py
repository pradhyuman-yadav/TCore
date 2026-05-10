from __future__ import annotations

from dataclasses import dataclass


@dataclass
class TradeSignal:
    action: str        # "buy" | "sell" | "hold"
    quantity_usdt: float  # USDT amount for buy; 0.0 for sell-all / hold
    reason: str


def evaluate_rules(
    zone: str,
    kill_switch: bool,
    open_positions: int,
    daily_pnl: float,
    strategy_config: dict,
) -> TradeSignal:
    """
    Pure function — no I/O. Returns a TradeSignal based on zone and risk checks.

    strategy_config keys used:
      position_sizing.mode        ("fixed_usdt")
      position_sizing.amount      (USDT per trade)
      position_sizing.max_open_positions
      risk.max_daily_loss_usdt
    """
    sizing = strategy_config.get("position_sizing", {})
    risk = strategy_config.get("risk", {})

    max_open = int(sizing.get("max_open_positions", 1))
    amount_usdt = float(sizing.get("amount", 100.0))
    max_daily_loss = float(risk.get("max_daily_loss_usdt", 200.0))

    if kill_switch:
        return TradeSignal(action="hold", quantity_usdt=0.0, reason="kill switch active")

    if zone == "neutral":
        return TradeSignal(action="hold", quantity_usdt=0.0, reason="zone is neutral")

    # Daily loss guard
    if daily_pnl <= -abs(max_daily_loss):
        return TradeSignal(
            action="hold",
            quantity_usdt=0.0,
            reason=f"daily loss limit reached ({daily_pnl:.2f} USD)",
        )

    if zone == "buy":
        if open_positions >= max_open:
            return TradeSignal(
                action="hold",
                quantity_usdt=0.0,
                reason=f"max open positions reached ({open_positions})",
            )
        return TradeSignal(action="buy", quantity_usdt=amount_usdt, reason="buy zone signal")

    if zone == "sell":
        if open_positions == 0:
            return TradeSignal(action="hold", quantity_usdt=0.0, reason="no position to sell")
        return TradeSignal(action="sell", quantity_usdt=0.0, reason="sell zone signal")

    return TradeSignal(action="hold", quantity_usdt=0.0, reason=f"unknown zone: {zone}")
