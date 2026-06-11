# TODO — living checklist

Keep this current as you work. Check items off; add discovered tasks under the
right phase. `[~]` = in progress. Detail for Phase 4 lives in
`PHASE_4_WORKPLAN.md`.

## Now: Phase 4 — Options Pricing + Chain
**Step 0 — resolve & record design decisions (blocking; see workplan §Step 0)**
- [ ] D1: sim-time → years convention; add `market.minutes_per_year` to config
- [ ] D2: integer-tick spot → BS `S` (single conversion site)
- [ ] D3: moneyness → integer strikes (single conversion site)
- [ ] D4: option price units / rounding policy (float in Phase 4)
- [ ] D5: Greeks set (delta, gamma, vega required)
- [ ] Record D1–D5 as a "Phase 4 Implementation Contracts" section in CLAUDE.md

**Step 1 — `sim/options/pricer.py`**
- [ ] `Greeks` frozen dataclass
- [ ] `bs_price(...)` with T≤0 / σ≤0 / invalid-input handling
- [ ] `bs_greeks(...)` (delta, gamma, vega)
- [ ] `tests/test_pricer.py`: known value, put-call parity, Greek sanity, expiry
- [ ] commit: "Phase 4: pricer complete"

**Step 2 — `sim/options/surface.py`**
- [ ] `FlatVolSurface` with `vol(strike, expiry)` interface
- [ ] `tests/test_surface.py`
- [ ] commit: "Phase 4: surface complete"

**Step 3 — `sim/options/chain.py`**
- [ ] `OptionSeries` dataclass + `build_chain(...)`
- [ ] `time_to_expiry_years(...)` (D1 site) + `spot_from_book(...)` (D2 site)
- [ ] `tests/test_chain.py`
- [ ] commit: "Phase 4: chain complete"

**Step 4 — config wiring**
- [ ] add `options` + `agents.options_mm` + `market.minutes_per_year` to params.yaml
- [ ] confirm `config/loader.py` reads them (no new read sites)

**Step 5 — integration**
- [ ] `tests/test_e2e_phase4.py`: price a chain off a live `run()` book mid
- [ ] full suite green

**Step 6 — close-out**
- [ ] CLAUDE.md: Phase 4 → [x], modules [x], test count, contracts section
- [ ] ROADMAP.md + this file updated
- [ ] (if debt accrued) Phase 4 Audit backlog + dedicated cleanup commit

## Next: Phase 5 — Options Dealer + Delta Hedging
- [ ] `sim/agents/options_mm.py`: quote options off pricer + surface
- [ ] on each options fill: recompute portfolio delta
- [ ] hedge: `hedge_qty = -net_delta * lot_size` → equity market order
- [ ] verify feedback loop: equity book reacts; re-quote on underlying move
- [ ] gamma limit + delta-hedge threshold from config
- [ ] Phase 5 test contract: **net delta within threshold of zero post-hedge**
- [ ] `tests/test_options_mm.py`, `tests/test_e2e_phase5.py`

## Later: Phase 6 — Calibration, Analytics, Full Run
- [ ] effective-spread / depth / realized-vol metrics in `analytics/`
- [ ] parameter calibration sweeps
- [ ] dynamic vol surface (replace FlatVolSurface behind the same interface)
- [ ] validate the stylised-facts checklist in GOALS.md end-to-end
- [ ] full-run report / plots

## Backlog (non-blocking, revisit when relevant)
- [ ] P2-2 carryover: drop the `equity_mm`/`equity_mms` singular shim **iff**
      `test_e2e_phase2.py` is ever unfrozen (currently intentionally retained).
- [ ] Consider whether the chain re-strikes as spot drifts (Phase 5/6 decision).
- [ ] Trading-calendar time convention vs continuous (revisit in calibration).
