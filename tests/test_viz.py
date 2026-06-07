"""Tests for sim.viz rendering.

Uses the headless `Agg` backend so the suite runs in CI without a
display. Exercises both the empty-book message and the populated
chart paths.
"""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg", force=True)

import matplotlib.pyplot as plt  # noqa: E402

from sim.viz import _render  # noqa: E402


def _snap(**kw) -> dict:
    base = {
        "timestamp": 0.0,
        "best_bid": None,
        "best_ask": None,
        "spread": None,
        "mid": None,
        "n_orders": 0,
        "bids": {},
        "asks": {},
        "fills": [],
    }
    base.update(kw)
    return base


def test_empty_snapshot_shows_friendly_message():
    fig, (ax_d, ax_f) = plt.subplots(1, 2)
    try:
        _render(ax_d, ax_f, _snap())
        assert "empty" in ax_d.get_title().lower()
        assert len(ax_d.texts) >= 1
        msg = ax_d.texts[0].get_text()
        assert "sim.repl" in msg
        assert "sim.agents_repl" in msg
        assert "no orders or fills" in msg.lower()
        assert "(0)" in ax_f.get_title()
    finally:
        plt.close(fig)


def test_populated_snapshot_renders_depth_bars():
    fig, (ax_d, ax_f) = plt.subplots(1, 2)
    try:
        snap = _snap(
            best_bid=99,
            best_ask=101,
            spread=2,
            mid=100,
            n_orders=2,
            bids={"99": 5},
            asks={"101": 3},
        )
        _render(ax_d, ax_f, snap)
        assert len(ax_d.patches) >= 2
        title = ax_d.get_title()
        assert "Depth" in title
        assert "99" in title and "101" in title
    finally:
        plt.close(fig)


def test_populated_snapshot_with_fills_renders_scatter():
    fig, (ax_d, ax_f) = plt.subplots(1, 2)
    try:
        snap = _snap(
            best_bid=99,
            best_ask=101,
            spread=2,
            mid=100,
            bids={"99": 5},
            asks={"101": 3},
            fills=[
                {"ts": 1.0, "side": "BUY", "price": 100, "qty": 1},
                {"ts": 2.0, "side": "SELL", "price": 100, "qty": 1},
            ],
        )
        _render(ax_d, ax_f, snap)
        assert len(ax_f.lines) >= 1 or len(ax_f.collections) >= 1
        assert "(2)" in ax_f.get_title()
    finally:
        plt.close(fig)


def test_partial_book_renders_only_present_side():
    fig, (ax_d, ax_f) = plt.subplots(1, 2)
    try:
        snap = _snap(
            best_bid=99,
            best_ask=None,
            spread=None,
            mid=None,
            bids={"99": 5},
            asks={},
        )
        _render(ax_d, ax_f, snap)
        assert len(ax_d.patches) >= 1
        assert "99" in ax_d.get_title()
    finally:
        plt.close(fig)


def test_y_axis_uses_plain_integer_formatter_no_offset():
    """The price axis must not auto-emit a `+1e4` offset — that makes a
    2-tick range look like it spans -10000 to +10000."""
    from matplotlib.ticker import FuncFormatter

    fig, (ax_d, ax_f) = plt.subplots(1, 2)
    try:
        snap = _snap(
            best_bid=9999,
            best_ask=10001,
            spread=2,
            mid=10000,
            bids={"9999": 5},
            asks={"10001": 5},
            fills=[
                {"ts": 1.0, "side": "BUY", "price": 10001, "qty": 1},
                {"ts": 2.0, "side": "SELL", "price": 9999, "qty": 1},
            ],
        )
        _render(ax_d, ax_f, snap)
        # Both axes should have a FuncFormatter (plain integer labels)
        for ax in (ax_d, ax_f):
            formatter = ax.yaxis.get_major_formatter()
            assert isinstance(formatter, FuncFormatter), (
                f"expected FuncFormatter, got {type(formatter).__name__}"
            )
        # Spot-check the formatter renders 10001 as "10001" (no offset)
        fmt = ax_f.yaxis.get_major_formatter()
        assert fmt(10001, 0) == "10001"
        assert fmt(9999, 0) == "9999"
    finally:
        plt.close(fig)
