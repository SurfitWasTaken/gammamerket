"""Pure snapshot serialization of LOB state for IPC / viz.

Kept as a standalone function so it can be unit-tested without a
display, and so the REPL and the viz subprocess agree on a single
schema.
"""

from __future__ import annotations

from typing import Any, Iterable

from sim.core.events import Side
from sim.core.lob import LimitOrderBook


def book_snapshot(
    book: LimitOrderBook,
    fills: Iterable[dict] = (),
    timestamp: float = 0.0,
) -> dict[str, Any]:
    """Return a JSON-serializable snapshot of `book` and recent fills.

    Args:
        book: The limit order book to serialize.
        fills: Iterable of fill dicts in the shape
            `{"ts": float, "side": "BUY"|"SELL", "price": int, "qty": int}`.
            Already-serialized or to be added by the caller.
        timestamp: A caller-supplied clock value to embed in the
            snapshot (typically the most recent event time).

    Returns:
        A plain dict ready for `json.dumps`. Price keys are stringified
        so the result is JSON-native.
    """
    bids = {str(p): book.depth(Side.BUY, p) for p in book.bids}
    asks = {str(p): book.depth(Side.SELL, p) for p in book.asks}
    return {
        "timestamp": timestamp,
        "best_bid": book.best_bid(),
        "best_ask": book.best_ask(),
        "spread": book.spread(),
        "mid": book.mid(),
        "n_orders": len(book),
        "bids": bids,
        "asks": asks,
        "fills": list(fills),
    }
