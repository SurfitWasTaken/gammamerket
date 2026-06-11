"""Tests for sim/options/surface.py — implied-vol surface (Phase 4)."""

from __future__ import annotations

import pytest

from sim.options.surface import FlatVolSurface, VolSurface


def test_flat_surface_returns_constant_for_any_point():
    surf = FlatVolSurface(0.20)
    points = [
        (9500, 7 * 24 * 60),
        (10000, 14 * 24 * 60),
        (10500, 30 * 24 * 60),
        (1.0, 0.0),
        (1e9, 1e9),
    ]
    for strike, expiry in points:
        assert surf.vol(strike, expiry) == 0.20


def test_sigma_property_exposes_constant():
    assert FlatVolSurface(0.35).sigma == 0.35


@pytest.mark.parametrize("bad_sigma", [0.0, -0.1])
def test_nonpositive_sigma_raises(bad_sigma):
    with pytest.raises(ValueError):
        FlatVolSurface(bad_sigma)


def test_satisfies_volsurface_protocol():
    surf = FlatVolSurface(0.2)
    # runtime_checkable Protocol — callers can rely on the structural type.
    assert isinstance(surf, VolSurface)


def test_vol_feeds_pricer_unchanged():
    # The surface's output is a plain σ usable directly by the pricer.
    from sim.options.pricer import bs_price

    surf = FlatVolSurface(0.2)
    sigma = surf.vol(10000, 30 * 24 * 60)
    price = bs_price(10000.0, 10000.0, 1.0, 0.05, sigma, is_call=True)
    assert price > 0.0


def test_repr_is_informative():
    assert "0.2" in repr(FlatVolSurface(0.2))
