"""End-to-end tests for the Phase 2 simulation."""

from __future__ import annotations

import numpy as np

from sim.agents.institution import Institution
from sim.agents.retail import Retail
from sim.analytics.metrics import (
    autocorrelation,
    fill_prices,
    simple_returns,
)
from run_sim import run


def _default_cfg(max_steps: int = 100) -> dict:
    return {
        "market": {
            "tick_size": 1,
            "lot_size": 100,
            "initial_price": 10000,
            "initial_bid_size": 200,
            "initial_ask_size": 200,
            "max_steps": max_steps,
            "seed": 42,
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
        },
    }


def test_phase2_100_step_run_produces_more_than_50_fills() -> None:
    result = run(_default_cfg(max_steps=100))
    n = len(result["tape"])
    assert n > 50, f"expected > 50 fills, got {n}"


def test_phase2_runs_to_max_steps() -> None:
    result = run(_default_cfg(max_steps=100))
    assert result["clock"].step_count == 100


def test_phase2_fill_prices_move_non_trivially() -> None:
    result = run(_default_cfg(max_steps=200))
    prices = fill_prices(result["tape"].fills)
    assert prices.max() - prices.min() > 0, "fill prices all identical"
    r = simple_returns(prices)
    assert r.std() > 0


def test_phase2_fill_prices_drift_beyond_seed_bbo() -> None:
    """The institution's signal-anchored quoting must let the price
    move beyond the ±1-tick seed BBO. The old behaviour pinned every
    fill to {9999, 10001}; this test guards against that regression."""
    result = run(_default_cfg(max_steps=300))
    prices = fill_prices(result["tape"].fills)
    seed_bbo = {9999, 10001}
    unique_prices = set(int(p) for p in prices)
    drifted = unique_prices - seed_bbo
    assert len(drifted) >= 2, (
        f"expected price to drift beyond seed BBO; "
        f"unique fills={sorted(unique_prices)}"
    )


def test_phase2_agents_all_instantiated() -> None:
    result = run(_default_cfg(max_steps=10))
    n_retail = sum(1 for a in result["agents"] if isinstance(a, Retail))
    n_inst = sum(1 for a in result["agents"] if isinstance(a, Institution))
    assert n_retail == 10
    assert n_inst == 1


def test_phase2_return_autocorr_lag_1_is_finite() -> None:
    result = run(_default_cfg(max_steps=200))
    prices = fill_prices(result["tape"].fills)
    r = simple_returns(prices)
    if len(r) > 10:
        acf = autocorrelation(r, max_lag=1)
        assert np.isfinite(acf[0])


def test_phase2_reproducible_with_same_seed() -> None:
    a = run(_default_cfg(max_steps=100))
    b = run(_default_cfg(max_steps=100))
    assert len(a["tape"]) == len(b["tape"])
    assert a["clock"].now == b["clock"].now


def test_phase2_different_seeds_yield_different_runs() -> None:
    cfg1 = _default_cfg(max_steps=100)
    cfg2 = _default_cfg(max_steps=100)
    cfg2["market"]["seed"] = 99
    a = run(cfg1)
    b = run(cfg2)
    pa = fill_prices(a["tape"].fills)
    pb = fill_prices(b["tape"].fills)
    assert not np.array_equal(pa, pb)
