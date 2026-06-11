"""Tests for sim/options/pricer.py — Black-Scholes price + Greeks (Phase 4)."""

from __future__ import annotations

import math

import pytest

from sim.options.pricer import Greeks, bs_greeks, bs_price


# Canonical textbook parameter set (CLAUDE.md / workplan known-value check).
S0, K0, T0, R0, SIG0 = 100.0, 100.0, 1.0, 0.05, 0.20


# --- known values -----------------------------------------------------------


def test_known_call_value():
    # S=100, K=100, T=1, r=0.05, σ=0.2 → call ≈ 10.4506 (textbook).
    c = bs_price(S0, K0, T0, R0, SIG0, is_call=True)
    assert c == pytest.approx(10.4506, abs=1e-3)


def test_known_put_value():
    # From put-call parity at the same params: P = C - (S - K e^{-rT}).
    p = bs_price(S0, K0, T0, R0, SIG0, is_call=False)
    assert p == pytest.approx(5.5735, abs=1e-3)


# --- put-call parity --------------------------------------------------------


@pytest.mark.parametrize("S", [80.0, 95.0, 100.0, 110.0, 130.0])
@pytest.mark.parametrize("T", [0.1, 0.5, 1.0, 2.0])
def test_put_call_parity(S, T):
    # C - P == S - K e^{-rT}
    c = bs_price(S, K0, T, R0, SIG0, is_call=True)
    p = bs_price(S, K0, T, R0, SIG0, is_call=False)
    assert (c - p) == pytest.approx(S - K0 * math.exp(-R0 * T), abs=1e-9)


# --- delta ------------------------------------------------------------------


def test_atm_call_delta_in_expected_band():
    g = bs_greeks(S0, K0, T0, R0, SIG0, is_call=True)
    # ATM call delta sits a touch above 0.5 (drift term lifts d1).
    assert 0.5 < g.delta < 0.7


@pytest.mark.parametrize("S", [80.0, 100.0, 120.0])
def test_put_delta_equals_call_delta_minus_one(S):
    gc = bs_greeks(S, K0, T0, R0, SIG0, is_call=True)
    gp = bs_greeks(S, K0, T0, R0, SIG0, is_call=False)
    assert gp.delta == pytest.approx(gc.delta - 1.0, abs=1e-12)


def test_call_delta_bounds_and_monotonicity():
    deltas = [
        bs_greeks(S, K0, T0, R0, SIG0, is_call=True).delta
        for S in (60.0, 80.0, 100.0, 120.0, 140.0)
    ]
    assert all(0.0 <= d <= 1.0 for d in deltas)
    assert deltas == sorted(deltas)  # delta rises with spot


# --- gamma ------------------------------------------------------------------


def test_gamma_positive_and_call_put_symmetric():
    gc = bs_greeks(S0, K0, T0, R0, SIG0, is_call=True)
    gp = bs_greeks(S0, K0, T0, R0, SIG0, is_call=False)
    assert gc.gamma > 0.0
    assert gc.gamma == pytest.approx(gp.gamma, abs=1e-15)


def test_gamma_peaks_atm():
    # Gamma at the (forward-ish) money exceeds gamma deep ITM/OTM.
    g_atm = bs_greeks(100.0, K0, T0, R0, SIG0, is_call=True).gamma
    g_otm = bs_greeks(140.0, K0, T0, R0, SIG0, is_call=True).gamma
    g_itm = bs_greeks(60.0, K0, T0, R0, SIG0, is_call=True).gamma
    assert g_atm > g_otm
    assert g_atm > g_itm


# --- vega -------------------------------------------------------------------


def test_vega_positive_and_call_put_symmetric():
    gc = bs_greeks(S0, K0, T0, R0, SIG0, is_call=True)
    gp = bs_greeks(S0, K0, T0, R0, SIG0, is_call=False)
    assert gc.vega > 0.0
    assert gc.vega == pytest.approx(gp.vega, abs=1e-12)


def test_vega_decays_to_zero_as_T_shrinks():
    vegas = [
        bs_greeks(S0, K0, T, R0, SIG0, is_call=True).vega
        for T in (1.0, 0.25, 0.01, 1e-10)
    ]
    assert vegas == sorted(vegas, reverse=True)  # monotone down (vega ∝ √T)
    assert vegas[-1] == pytest.approx(0.0, abs=1e-2)


# --- expiry / degenerate edge cases -----------------------------------------


@pytest.mark.parametrize("is_call", [True, False])
@pytest.mark.parametrize("S", [80.0, 100.0, 120.0])
def test_expiry_price_is_intrinsic(S, is_call):
    intrinsic = max(S - K0, 0.0) if is_call else max(K0 - S, 0.0)
    assert bs_price(S, K0, 0.0, R0, SIG0, is_call=is_call) == pytest.approx(intrinsic)
    assert bs_price(S, K0, -1.0, R0, SIG0, is_call=is_call) == pytest.approx(intrinsic)


def test_expiry_greeks_are_step():
    # ITM call → delta 1, OTM → 0; gamma/vega vanish.
    itm = bs_greeks(120.0, K0, 0.0, R0, SIG0, is_call=True)
    otm = bs_greeks(80.0, K0, 0.0, R0, SIG0, is_call=True)
    assert itm == Greeks(delta=1.0, gamma=0.0, vega=0.0)
    assert otm == Greeks(delta=0.0, gamma=0.0, vega=0.0)
    # ITM put → delta -1.
    put_itm = bs_greeks(80.0, K0, 0.0, R0, SIG0, is_call=False)
    assert put_itm == Greeks(delta=-1.0, gamma=0.0, vega=0.0)


def test_zero_sigma_returns_discounted_intrinsic():
    # σ=0: deterministic; call worth max(S - K e^{-rT}, 0).
    disc_k = K0 * math.exp(-R0 * T0)
    assert bs_price(110.0, K0, T0, R0, 0.0, is_call=True) == pytest.approx(
        max(110.0 - disc_k, 0.0)
    )
    g = bs_greeks(110.0, K0, T0, R0, 0.0, is_call=True)
    assert g.gamma == 0.0 and g.vega == 0.0


def test_no_nan_or_inf_anywhere():
    for S in (50.0, 100.0, 150.0):
        for T in (0.0, 1e-8, 0.5, 2.0):
            for is_call in (True, False):
                price = bs_price(S, K0, T, R0, SIG0, is_call=is_call)
                g = bs_greeks(S, K0, T, R0, SIG0, is_call=is_call)
                assert math.isfinite(price)
                assert math.isfinite(g.delta)
                assert math.isfinite(g.gamma)
                assert math.isfinite(g.vega)


# --- invalid inputs ---------------------------------------------------------


@pytest.mark.parametrize("bad_S", [0.0, -1.0])
def test_nonpositive_spot_raises(bad_S):
    with pytest.raises(ValueError):
        bs_price(bad_S, K0, T0, R0, SIG0, is_call=True)
    with pytest.raises(ValueError):
        bs_greeks(bad_S, K0, T0, R0, SIG0, is_call=True)


@pytest.mark.parametrize("bad_K", [0.0, -5.0])
def test_nonpositive_strike_raises(bad_K):
    with pytest.raises(ValueError):
        bs_price(S0, bad_K, T0, R0, SIG0, is_call=True)
    with pytest.raises(ValueError):
        bs_greeks(S0, bad_K, T0, R0, SIG0, is_call=True)


def test_greeks_dataclass_is_frozen():
    g = bs_greeks(S0, K0, T0, R0, SIG0, is_call=True)
    with pytest.raises(Exception):
        g.delta = 0.0  # type: ignore[misc]
