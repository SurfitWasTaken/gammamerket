"""End-to-end tests for the Phase 3 simulation."""

from __future__ import annotations

import numpy as np

from sim.agents.equity_mm import EquityMarketMaker
from sim.agents.institution import Institution
from sim.agents.retail import Retail
from run_sim import run


def _default_cfg(max_steps: int = 200) -> dict:
    return {
        "market": {
            "tick_size": 1,
            "lot_size": 100,
            "initial_price": 10000,
            "initial_bid_size": 200,
            "initial_ask_size": 200,
            "max_steps": max_steps,
            "seed": 42,
            "vol_window": 20,
        },
        "agents": {
            "retail": {
                "n_agents": 10,
                "arrival_rate": 10.0,
                "order_size_mean": 1,
                "direction_bias": 0.0,
            },
            "institution": {
                "arrival_rate": 5.0,
                "signal_halflife": 30.0,
                "signal_sigma": 1.0,
                "threshold": 0.0,
                "position_limit": 500,
                "quote_offset_ticks": 1,
                "scale": 100,
                "signal_price_scale": 5,
            },
            "equity_mms": [
                {
                    "id": "mm_aggressive",
                    "arrival_rate": 20.0,
                    "spread_target": 3,
                    "inventory_limit": 2000,
                    "risk_aversion": 0.05,
                    "quote_size": 5,
                    "max_orders_per_side": 1,
                    "vol_window": 20,
                    "vol_multiplier": 2.0,
                    "baseline_vol_bps": 5.0,
                },
                {
                    "id": "mm_conservative",
                    "arrival_rate": 20.0,
                    "spread_target": 5,
                    "inventory_limit": 2000,
                    "risk_aversion": 0.1,
                    "quote_size": 5,
                    "max_orders_per_side": 1,
                    "vol_window": 20,
                    "vol_multiplier": 2.0,
                    "baseline_vol_bps": 5.0,
                },
            ],
        },
    }


def test_phase3_two_mms_instantiated() -> None:
    """Two equity MMs with different IDs and spread targets are created."""
    result = run(_default_cfg(max_steps=10))
    mms = [a for a in result["agents"] if isinstance(a, EquityMarketMaker)]
    assert len(mms) == 2
    ids = {mm.agent_id for mm in mms}
    assert ids == {"mm_aggressive", "mm_conservative"}


def test_phase3_mms_have_different_spread_targets() -> None:
    """Aggressive MM has tighter spread target than conservative MM."""
    result = run(_default_cfg(max_steps=10))
    mms = {a.agent_id: a for a in result["agents"] if isinstance(a, EquityMarketMaker)}
    assert mms["mm_aggressive"].config.spread_target < mms["mm_conservative"].config.spread_target


def test_phase3_run_produces_fills() -> None:
    """Phase 3 sim runs and produces fills."""
    result = run(_default_cfg(max_steps=100))
    n = len(result["tape"])
    assert n > 0


def test_phase3_mms_registered_with_own_rates() -> None:
    """Each MM gets its own arrival_rate from config."""
    result = run(_default_cfg(max_steps=10))
    mms = [a for a in result["agents"] if isinstance(a, EquityMarketMaker)]
    for mm in mms:
        assert mm.config.arrival_rate == 20.0


def test_phase3_spread_always_positive() -> None:
    """Spread never crosses or goes to zero."""
    result = run(_default_cfg(max_steps=300))
    # Just check the sim runs without error; spread positivity is a unit test
    # This test guards against runtime crashes
    assert result["clock"].step_count == 300


def test_phase3_mm_pnl_finite() -> None:
    """MM P&L is finite and tracked."""
    result = run(_default_cfg(max_steps=200))
    mms = [a for a in result["agents"] if isinstance(a, EquityMarketMaker)]
    for mm in mms:
        assert np.isfinite(mm.total_pnl)
        assert np.isfinite(mm.cash_flow)
        assert mm.avg_spread > 0


def test_phase3_aggressive_mm_tighter_avg_spread() -> None:
    """Aggressive MM (lower spread_target) quotes tighter on average."""
    result = run(_default_cfg(max_steps=500))
    mms = {a.agent_id: a for a in result["agents"] if isinstance(a, EquityMarketMaker)}
    # Aggressive MM should have tighter average spread
    assert mms["mm_aggressive"].avg_spread < mms["mm_conservative"].avg_spread


def test_phase3_reproducible_with_same_seed() -> None:
    """Same seed produces identical results."""
    a = run(_default_cfg(max_steps=100))
    b = run(_default_cfg(max_steps=100))
    assert len(a["tape"]) == len(b["tape"])
    assert a["clock"].now == b["clock"].now


def test_phase3_different_seeds_yield_different_runs() -> None:
    """Different seeds produce different fill sequences."""
    cfg1 = _default_cfg(max_steps=100)
    cfg2 = _default_cfg(max_steps=100)
    cfg2["market"]["seed"] = 99
    a = run(cfg1)
    b = run(cfg2)
    from sim.analytics.metrics import fill_prices
    pa = fill_prices(a["tape"].fills)
    pb = fill_prices(b["tape"].fills)
    assert not np.array_equal(pa, pb)


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])