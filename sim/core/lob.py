"""Price-time priority limit order book.

Internally backed by a `SortedDict` (from `sortedcontainers`) keyed by
price, with a FIFO `deque` of resting orders at each price level. All
monetary values are integer ticks. The book is the single source of
truth for every price agents observe.
"""

from __future__ import annotations

import uuid
from collections import deque
from dataclasses import dataclass
from typing import Callable, Optional

from sortedcontainers import SortedDict

from sim.core.events import Fill, Order, Side


@dataclass
class _RestingOrder:
    """Mutable in-book node. The public `Order` is frozen; this wrapper
    holds the remaining quantity that partial fills decrement in place."""

    order_id: uuid.UUID
    agent_id: str
    side: Side
    price: int
    remaining_qty: int
    timestamp: float


def _new_resting(order: Order) -> _RestingOrder:
    return _RestingOrder(
        order_id=order.order_id,
        agent_id=order.agent_id,
        side=order.side,
        price=order.price,
        remaining_qty=order.qty,
        timestamp=order.timestamp,
    )


class LimitOrderBook:
    """Two-sided limit order book with price-time priority.

    Args:
        tick_size: Minimum price increment in ticks. Limit order prices
            must be a positive multiple of this value.
        on_fill: Optional callback invoked once per generated fill
            (after the fill is appended to the return list of the
            `submit_*` method). Used by the runner to wire the central
            `Tape` without coupling the LOB to analytics. Defaults to
            None, in which case no callback is invoked.

    The book enforces:
        * Positive integer prices, positive integer quantities.
        * Tick-size alignment on limit orders (market orders ignore the
          price field of their `Order` and therefore cannot be rejected
          on tick grounds).
    """

    def __init__(
        self,
        tick_size: int = 1,
        on_fill: Optional[Callable[[Fill], None]] = None,
    ) -> None:
        if tick_size <= 0:
            raise ValueError(f"tick_size must be positive, got {tick_size}")
        self._tick_size: int = tick_size
        self.bids: SortedDict = SortedDict()
        self.asks: SortedDict = SortedDict()
        self._orders: dict[uuid.UUID, _RestingOrder] = {}
        self._on_fill: Optional[Callable[[Fill], None]] = on_fill

    @property
    def tick_size(self) -> int:
        return self._tick_size

    def __len__(self) -> int:
        return len(self._orders)

    def __call__(self) -> str:
        """One-line summary of book state. Returned (not printed) so the
        REPL and tests can echo or assert on it."""
        return (
            f"LOB<bid={self.best_bid()}  ask={self.best_ask()}  "
            f"spread={self.spread()}  mid={self.mid()}  "
            f"n_orders={len(self)}>"
        )

    def clear(self) -> None:
        """Remove all resting orders. The instance itself is preserved
        (callers holding a reference still see the same object)."""
        self.bids.clear()
        self.asks.clear()
        self._orders.clear()

    def best_bid(self) -> Optional[int]:
        if not self.bids:
            return None
        return self.bids.keys()[-1]

    def best_ask(self) -> Optional[int]:
        if not self.asks:
            return None
        return self.asks.keys()[0]

    def mid(self) -> Optional[float]:
        bb, ba = self.best_bid(), self.best_ask()
        if bb is None or ba is None:
            return None
        return (bb + ba) / 2.0

    def spread(self) -> Optional[int]:
        bb, ba = self.best_bid(), self.best_ask()
        if bb is None or ba is None:
            return None
        return ba - bb

    def depth(self, side: Side, price: int) -> int:
        """Total remaining quantity at a given price on a given side."""
        book = self.bids if side is Side.BUY else self.asks
        if price not in book:
            return 0
        return sum(r.remaining_qty for r in book[price])

    def submit_limit(self, order: Order) -> list[Fill]:
        """Insert a limit order, sweeping the opposite side if marketable.

        Args:
            order: The incoming limit order. Price must be a positive
                multiple of `tick_size`; qty must be positive.

        Returns:
            List of fills generated. Empty if the order rested without
            matching anything. If the order partially fills and the
            remainder is non-zero, the remainder is inserted into the
            book.
        """
        self._validate_limit(order)
        fills = self._sweep(order, is_limit=True)
        remaining = order.qty - sum(f.qty for f in fills)
        if remaining > 0:
            self._rest(_new_resting(_with_qty(order, remaining)))
        return fills

    def submit_market(self, order: Order) -> list[Fill]:
        """Sweep the opposite side. Surplus rests at the last-touched
        price when at least one fill was generated; surplus is dropped
        when the book was empty from the start (no last-touched price
        exists).

        Args:
            order: The incoming market order. The `price` field of the
                supplied `Order` is ignored. Qty must be positive.

        Returns:
            List of fills generated. May be empty if the book was empty.
        """
        if order.qty <= 0:
            raise ValueError(f"order qty must be positive, got {order.qty}")
        fills = self._sweep(order, is_limit=False)
        last_price = fills[-1].price if fills else None
        remaining = order.qty - sum(f.qty for f in fills)
        if remaining > 0 and last_price is not None:
            rested = _new_resting(_with_qty(order, remaining))
            rested.price = last_price
            self._rest(rested)
        return fills

    def cancel(self, order_id: uuid.UUID) -> bool:
        """Remove a resting order. Returns False if not present.

        Args:
            order_id: Identifier of the order to cancel.

        Returns:
            True if the order was found and removed; False if the order
            is unknown, already filled, or already cancelled.
        """
        node = self._orders.pop(order_id, None)
        if node is None:
            return False
        book = self.bids if node.side is Side.BUY else self.asks
        if node.price in book:
            level = book[node.price]
            try:
                level.remove(node)
            except ValueError:
                pass
            if not level:
                del book[node.price]
        return True

    def _validate_limit(self, order: Order) -> None:
        if order.qty <= 0:
            raise ValueError(f"order qty must be positive, got {order.qty}")
        if order.price <= 0:
            raise ValueError(f"order price must be positive, got {order.price}")
        if order.price % self._tick_size != 0:
            raise ValueError(
                f"order price {order.price} is not a multiple of tick_size {self._tick_size}"
            )

    def _sweep(self, taker: Order, *, is_limit: bool) -> list[Fill]:
        """Match `taker` against the opposite side. Returns the fills.

        A BUY taker sweeps the ask side; a SELL taker sweeps the bid
        side. Reads from `level[0]` (oldest) only and mutates the head
        node's `remaining_qty` in place, popping when zero. The deque
        itself is never mutated while iterating.
        """
        fills: list[Fill] = []
        remaining = taker.qty

        if taker.side is Side.BUY:
            book = self.asks
            best_price_fn = lambda b: b.keys()[0]
            crosses = (lambda p: True) if not is_limit else (lambda p: taker.price >= p)
        else:
            book = self.bids
            best_price_fn = lambda b: b.keys()[-1]
            crosses = (lambda p: True) if not is_limit else (lambda p: taker.price <= p)

        while remaining > 0 and book:
            best_price = best_price_fn(book)
            if not crosses(best_price):
                break
            level: deque = book[best_price]
            while remaining > 0 and level:
                maker = level[0]
                trade_qty = min(maker.remaining_qty, remaining)
                fill = Fill(
                    taker_order_id=taker.order_id,
                    maker_order_id=maker.order_id,
                    taker_agent_id=taker.agent_id,
                    maker_agent_id=maker.agent_id,
                    aggressor_side=taker.side,
                    price=maker.price,
                    qty=trade_qty,
                    timestamp=taker.timestamp,
                )
                fills.append(fill)
                if self._on_fill is not None:
                    self._on_fill(fill)
                maker.remaining_qty -= trade_qty
                remaining -= trade_qty
                if maker.remaining_qty == 0:
                    level.popleft()
                    self._orders.pop(maker.order_id, None)
            if not level:
                del book[best_price]

        return fills

    def _rest(self, node: _RestingOrder) -> None:
        book = self.bids if node.side is Side.BUY else self.asks
        if node.price not in book:
            book[node.price] = deque()
        book[node.price].append(node)
        self._orders[node.order_id] = node


def _with_qty(order: Order, qty: int) -> Order:
    """Return a copy of `order` with `qty` replaced.

    `Order` is frozen, so we cannot mutate. This is the only sanctioned
    place we build a derived `Order` for internal use.
    """
    return Order(
        order_id=order.order_id,
        agent_id=order.agent_id,
        side=order.side,
        price=order.price,
        qty=qty,
        timestamp=order.timestamp,
        is_market=order.is_market,
    )
