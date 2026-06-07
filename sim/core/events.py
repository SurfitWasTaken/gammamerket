"""Event types for the limit order book and surrounding exchange.

All monetary values are integer ticks. Frozen dataclasses are used so that
immutable event records can be passed freely between modules without
defensive copies.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from enum import Enum


class Side(Enum):
    """Order side. BUY lifts the ask side; SELL hits the bid side."""

    BUY = "BUY"
    SELL = "SELL"

    @property
    def is_buy(self) -> bool:
        return self is Side.BUY

    @property
    def is_sell(self) -> bool:
        return self is Side.SELL


@dataclass(frozen=True)
class Order:
    """A request to trade. Frozen: never mutated after construction.

    Args:
        order_id: Unique identifier (uuid4).
        agent_id: Submitting agent's identifier.
        side: BUY or SELL.
        price: Limit price in integer ticks. Ignored for market orders
            that are later created internally from a market sweep; for
            submitted market orders the price field is unused.
        qty: Quantity in integer lots. Must be positive.
        timestamp: Caller-supplied event time (used for time priority).
    """

    order_id: uuid.UUID
    agent_id: str
    side: Side
    price: int
    qty: int
    timestamp: float


@dataclass(frozen=True)
class Fill:
    """A matched trade between a taker (aggressor) and a maker (resting).

    Args:
        taker_order_id: The aggressive (incoming) order.
        maker_order_id: The resting (passive) order.
        aggressor_side: Side of the taker.
        price: Execution price in ticks. Always equals the maker's price
            (price-time priority: the resting order sets the price).
        qty: Executed quantity in lots.
        timestamp: Time at which the fill was generated.
    """

    taker_order_id: uuid.UUID
    maker_order_id: uuid.UUID
    aggressor_side: Side
    price: int
    qty: int
    timestamp: float


@dataclass(frozen=True)
class Cancel:
    """A request to remove a resting order from the book.

    Args:
        order_id: Identifier of the order to cancel.
        agent_id: Agent issuing the cancel (for audit/routing).
        timestamp: Event time of the cancel request.
    """

    order_id: uuid.UUID
    agent_id: str
    timestamp: float
