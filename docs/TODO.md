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

## ✅ Done: Phase 5 — Options Dealer + Delta Hedging  (complete 2026-06-12, 255 tests)
**Step 0 — resolve & record design decisions (blocking; see workplan §Step 0)**
- [x] E1: quote-driven flow — `OptionsFlow` taker calls `dealer.on_option_trade`;
      Clock owner-routes fills (`Order.agent_id`) so flow-carried hedges credit the dealer
- [x] E2: contract = one lot; per-contract delta in lots = `bs_delta` (lot_size
      cancels); `round(-net_delta)` half-to-even; **0.5-lot quantisation floor**
- [x] E3: hedge after every option fill + every dealer step, gated by threshold
- [x] E4: quotes at σ ± spread_vols **vol points** (1 pt = 0.01 σ); bid floored /
      ask ceiled to `option_tick`; spread ≥ 1 tick; trades execute at the quote
- [x] E5: gamma cap refuses |gamma|-increasing trades past `gamma_limit`
- [x] E6: chain built once at dealer construction (anchor = seeded BBO mid)
- [x] Recorded E1–E6 as "Phase 5 Implementation Contracts" in CLAUDE.md

**Step 1 — `sim/agents/options_mm.py`**
- [x] `OptionsMMConfig` + `OptionsMarketMaker(Agent)` (chain + surface + position book)
- [x] `net_delta_lots` (E2 single site) + `portfolio_gamma` (E5)
- [x] `on_option_trade(...)` → `_hedge(...)` → equity market order
- [x] `step(state)`: recompute delta off live mid, hedge past threshold (E3)
- [x] `tests/test_options_mm.py`: net-delta math, post-hedge bound, hedge signs,
      gamma cap, threshold gating, expired series, no-reference-price (23 tests)
- [x] commit: "Phase 5: options_mm complete"

**Step 2 — options-demand flow (E1)**
- [x] `sim/agents/options_flow.py` Poisson taker → `dealer.on_option_trade(...)`
- [x] Clock owner-routing extension (backward-compatible; pinned by tests)
- [x] `tests/test_options_flow.py` (9 tests, incl. owner-routing integration)
- [x] commit: "Phase 5: options_flow complete (+ clock owner-routing for E1)"

**Step 3+4 — config + runner + e2e (close the loop)**
- [x] `agents.options_flow` block + `options_mm.{arrival_rate, option_tick}` in params.yaml
- [x] dealer + flow wired into run_sim.py (switch on `agents.options_flow` presence)
- [x] `tests/test_e2e_phase5.py`: option fills happen, equity book reacts,
      **net delta within `max(threshold, 0.5)` lots of zero after each hedge cycle**
- [x] full suite green (255)

**Step 5 — close-out**
- [x] CLAUDE.md: Phase 5 → [x], modules [x], test count, contracts section
- [x] ROADMAP.md + this file updated
- [x] no P0/P1 debt — one latent pre-existing edge logged in Backlog below

## Now: Phase 6 — Calibration, Analytics, Full Run
- [ ] effective-spread / depth / realized-vol metrics in `analytics/`
- [ ] parameter calibration sweeps
- [ ] dynamic vol surface (replace FlatVolSurface behind the same interface)
- [ ] validate the stylised-facts checklist in GOALS.md end-to-end
- [ ] full-run report / plots

## Backlog (non-blocking, revisit when relevant)
- [ ] P2-2 carryover: drop the `equity_mm`/`equity_mms` singular shim **iff**
      `test_e2e_phase2.py` is ever unfrozen (currently intentionally retained).
- [ ] Consider whether the chain re-strikes as spot drifts (deferred to Phase 6
      per E6; revisit if a run shows spot leaving the strike grid materially).
- [ ] Trading-calendar time convention vs continuous (revisit in calibration).
- [ ] Self-trade position accounting (pre-existing, latent): `base.on_fills`
      applies one signed qty when an agent is both taker and maker of a fill,
      but a self-trade's net position change should be 0. Reachable in theory
      since LOB market-order surplus rests (a later opposite hedge/quote could
      cross it); not observed in any run — book depth (200-lot seeds, MM
      quotes) means hedges never leave surplus. Fix in `base.on_fills` (skip
      when `taker_agent_id == maker_agent_id`) with a regression test if Phase
      6 thins the book.
