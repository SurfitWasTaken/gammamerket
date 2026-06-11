# TODO — living checklist

Keep this current as you work. Check items off; add discovered tasks under the
right phase. `[~]` = in progress. Detail for the current phase lives in
`PHASE_5_WORKPLAN.md` (Phase 4's plan is `PHASE_4_WORKPLAN.md`, completed).

## ✅ Done: Phase 4 — Options Pricing + Chain  (complete 2026-06-11, 217 tests)
**Step 0 — resolve & record design decisions (blocking; see workplan §Step 0)**
- [x] D1: sim-time → years convention; add `market.minutes_per_year` to config
- [x] D2: integer-tick spot → BS `S` (single conversion site)
- [x] D3: moneyness → integer strikes (single conversion site)
- [x] D4: option price units / rounding policy (float in Phase 4)
- [x] D5: Greeks set (delta, gamma, vega required)
- [x] Record D1–D5 as a "Phase 4 Implementation Contracts" section in CLAUDE.md
- [x] Normal CDF source: SciPy (`scipy.special.ndtr`); pinned `scipy>=1.10` in requirements.txt

**Step 1 — `sim/options/pricer.py`**
- [x] `Greeks` frozen dataclass
- [x] `bs_price(...)` with T≤0 / σ≤0 / invalid-input handling
- [x] `bs_greeks(...)` (delta, gamma, vega)
- [x] `tests/test_pricer.py`: known value, put-call parity, Greek sanity, expiry
- [x] commit: "Phase 4: pricer complete"

**Step 2 — `sim/options/surface.py`**
- [x] `FlatVolSurface` with `vol(strike, expiry)` interface
- [x] `tests/test_surface.py`
- [x] commit: "Phase 4: surface complete"

**Step 3 — `sim/options/chain.py`**
- [x] `OptionSeries` dataclass + `build_chain(...)`
- [x] `time_to_expiry_years(...)` (D1 site) + `spot_from_book(...)` (D2 site)
- [x] `tests/test_chain.py`
- [x] commit: "Phase 4: chain complete"

**Step 4 — config wiring**
- [x] add `options` + `agents.options_mm` + `market.minutes_per_year` to params.yaml
- [x] confirm `config/loader.py` reads them (no new read sites)

**Step 5 — integration**
- [x] `tests/test_e2e_phase4.py`: price a chain off a live `run()` book mid
- [x] full suite green

**Step 6 — close-out**
- [x] CLAUDE.md: Phase 4 → [x], modules [x], test count (217), contracts section
- [x] ROADMAP.md + this file updated
- [x] no debt accrued — module review surfaced no P0/P1; no Phase 4 Audit needed

## Now: Phase 5 — Options Dealer + Delta Hedging  (detail: `PHASE_5_WORKPLAN.md`)
**Step 0 — resolve & record design decisions (blocking; see workplan §Step 0)**
- [ ] E1: how option trades are generated (quote-driven flow vs seeded position)
- [ ] E2: delta units — contracts → share-equivalents → equity hedge **lots**
- [ ] E3: when to hedge (every fill + step, gated by `delta_hedge_threshold`)
- [ ] E4: option quote pricing (vol/spread_vols, option-quote rounding policy)
- [ ] E5: gamma-limit enforcement
- [ ] E6: chain lifecycle (fixed strikes in v1 vs re-strike)
- [ ] Record E1–E6 as a "Phase 5 Implementation Contracts" section in CLAUDE.md

**Step 1 — `sim/agents/options_mm.py`**
- [ ] `OptionsMMConfig` + `OptionsMarketMaker(Agent)` (chain + surface + position book)
- [ ] `_net_delta_lots` (E2 single site) + `_portfolio_gamma` (E5)
- [ ] `on_option_trade(...)` → `_hedge(...)` → equity market order
- [ ] `step(state)`: recompute delta off live mid, hedge past threshold (E3)
- [ ] `tests/test_options_mm.py`: net-delta math, post-hedge ≈ 0, hedge sign, gamma cap
- [ ] commit: "Phase 5: options_mm complete"

**Step 2 — options-demand flow (E1)**
- [ ] `sim/agents/options_flow.py` Poisson taker → `dealer.on_option_trade(...)`
- [ ] `agents.options_flow` config block; `tests/test_options_flow.py`
- [ ] commit: "Phase 5: options_flow complete"

**Step 3 — runner + e2e (close the loop)**
- [ ] wire dealer + flow into the runner alongside Phase 3 agents
- [ ] `tests/test_e2e_phase5.py`: option fills happen, equity book reacts,
      **net delta within threshold of zero after each hedge cycle**
- [ ] full suite green

**Step 4 — close-out**
- [ ] CLAUDE.md: Phase 5 → [x], modules [x], test count, contracts section
- [ ] ROADMAP.md + this file updated
- [ ] (if debt accrued) Phase 5 Audit backlog + dedicated cleanup commit

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
