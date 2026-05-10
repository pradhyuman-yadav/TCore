import pytest

from app.services.rule_engine import TradeSignal, evaluate_rules


STRATEGY = {
    "position_sizing": {
        "mode": "fixed_usdt",
        "amount": 100,
        "max_open_positions": 1,
    },
    "risk": {
        "max_daily_loss_usdt": 200,
    },
}


def _eval(zone="buy", kill_switch=False, open_positions=0, daily_pnl=0.0, config=None):
    return evaluate_rules(
        zone=zone,
        kill_switch=kill_switch,
        open_positions=open_positions,
        daily_pnl=daily_pnl,
        strategy_config=config or STRATEGY,
    )


def test_kill_switch_returns_hold():
    sig = _eval(zone="buy", kill_switch=True)
    assert sig.action == "hold"
    assert "kill switch" in sig.reason


def test_neutral_zone_returns_hold():
    sig = _eval(zone="neutral")
    assert sig.action == "hold"
    assert "neutral" in sig.reason


def test_buy_zone_no_position_returns_buy():
    sig = _eval(zone="buy", open_positions=0)
    assert sig.action == "buy"
    assert sig.quantity_usdt == 100.0


def test_sell_zone_with_position_returns_sell():
    sig = _eval(zone="sell", open_positions=1)
    assert sig.action == "sell"
    assert sig.quantity_usdt == 0.0


def test_sell_zone_no_position_returns_hold():
    sig = _eval(zone="sell", open_positions=0)
    assert sig.action == "hold"
    assert "no position" in sig.reason


def test_max_daily_loss_blocks_trade():
    sig = _eval(zone="buy", daily_pnl=-200.0)
    assert sig.action == "hold"
    assert "daily loss" in sig.reason


def test_daily_loss_not_yet_hit_allows_trade():
    sig = _eval(zone="buy", daily_pnl=-199.99)
    assert sig.action == "buy"


def test_max_open_positions_blocks_buy():
    sig = _eval(zone="buy", open_positions=1)
    assert sig.action == "hold"
    assert "max open positions" in sig.reason


def test_buy_uses_amount_from_config():
    config = {**STRATEGY, "position_sizing": {**STRATEGY["position_sizing"], "amount": 250}}
    sig = _eval(zone="buy", config=config)
    assert sig.quantity_usdt == 250.0


def test_kill_switch_overrides_everything():
    # Even with valid zone and no risk violations, kill switch wins
    sig = _eval(zone="buy", kill_switch=True, open_positions=0, daily_pnl=100.0)
    assert sig.action == "hold"
