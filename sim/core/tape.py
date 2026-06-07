"""Central chronological log of fills.

The Tape is the single source of truth for the post-run fill history. It
is injected into the LOB via the `on_fill` callback so the LOB never
imports analytics; analytics layers subscribe to (or replay) the tape
later.
"""

from __future__ import annotations

from typing import Iterator

import numpy as np

from sim.core.events import Fill


class Tape:
    """Chronological fill log.

    Append-only. The class is intentionally tiny: it owns a list of
    `Fill` records and exposes a few convenience accessors used by the
    metrics layer.
    """

    def __init__(self) -> None:
        self.fills: list[Fill] = []

    def append(self, fill: Fill) -> None:
        """Record a fill. Caller supplies the fill (typically the LOB's
        `on_fill` callback forwards into this method)."""
        self.fills.append(fill)

    def __len__(self) -> int:
        return len(self.fills)

    def __iter__(self) -> Iterator[Fill]:
        return iter(self.fills)

    def last_fill_price(self) -> int | None:
        """Price of the most recent fill, or None if no fills yet."""
        if not self.fills:
            return None
        return self.fills[-1].price

    def prices(self) -> np.ndarray:
        """Array of fill prices (in ticks), in chronological order."""
        if not self.fills:
            return np.empty(0, dtype=np.int64)
        return np.fromiter(
            (f.price for f in self.fills), dtype=np.int64, count=len(self.fills)
        )
