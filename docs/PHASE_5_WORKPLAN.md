# Phase 5 Workplan — Options Dealer + Delta Hedging

> Goal: the **core experiment**. An options dealer agent quotes vanilla European
> options off the Phase 4 library, takes fills, and after every fill recomputes
> its portfolio delta and submits an **equity hedge order into the existing LOB**
> — closing the feedback loop (option fill → hedge → underlying moves → option
> values change → re-quote). Done when **net delta is within threshold of zero
> after each hedge cycle** and the equity book visibly reacts.

Defer to `CLAUDE.md` for the canonical BS formulas, the delta-hedging loop, the
frozen Phase 4 unit contracts (D1–D5), coding standards, and scope boundaries.
This file is the build order, the open decisions, and the test plan.

**Prerequisite (met):** Phase 4 shipped a numerically-correct pricer + flat
surface + chain (217 tests green). Phase 5 consumes that library; it does not
modify it.

---

## What already exists for you (Phase 4 library API)
From `sim/options/`:
- `pricer.bs_price(S, K, T, r, sigma, *, is_call) -> float`
- `pricer.bs_greeks(S, K, T, r, sigma, *, is_call) -> Greeks(delta, gamma, vega)`
  — **delta/gamma/vega are per one unit of underlying** (per share, not per lot
  or per contract). Lot/contract scaling is a Phase 5 decision (E2 below).
- `surface.FlatVolSurface(sigma).vol(strike, expiry) -> float` (behind the
  `VolSurface` protocol).
- `chain.build_chain(anchor_spot, now_minutes, *, strikes_pct, expiries_days,
  tick_size) -> list[OptionSeries]`
- `chain.spot_from_book(mid, tick_size) -> float`  (D2 — the only tick→S site)
- `chain.time_to_expiry_years(series, now_minutes, minutes_per_year) -> float`
  (D1 — the only minutes→years site)
- `chain.find_series(chain, strike, expiry_minutes, is_call) -> OptionSeries`

Config already seeded (`agents.options_mm`, unused until now):
`vol_estimate: 0.20`, `spread_vols: 2.0`, `delta_hedge_threshold: 0.05`,
`gamma_limit: 500`. Plus `options.{strikes_pct, expiries_days, risk_free_rate}`
and `market.minutes_per_year`.

---

## Step 0 — Resolve the open design decisions FIRST (do not skip)

Same discipline as Phase 4 Step 0: resolve each, **record the choice in
`CLAUDE.md`** (a new "Phase 5 Implementation Contracts" section, mirroring the
Phase 2/3/4 ones), then code. Recommended defaults given — adopt unless you have
a reason not to. These are load-bearing for whether the hedge actually flattens
delta.

### E1 — How do option trades get generated? (quote-driven market shape)
GOALS.md fixes the scope: **no options LOB in Phase 5** — a *quote-driven* market
(dealer quotes on request). So something must take the dealer's option quotes or
there are no fills to hedge.
- **Recommended:** add a lightweight **options-demand flow** — a small taker
  process (Poisson arrivals, like retail) that, on each of its events, picks a
  series from the chain and "lifts" or "hits" the dealer's two-sided option
  quote for a random lot count. Model it as a direct dealer method
  (`dealer.on_option_trade(series, side, qty)`) invoked by a new
  `OptionsFlow` agent/driver, **not** as orders in a second LOB. This keeps the
  options market quote-driven and the equity LOB the only real book.
- Alternative (simpler, less realistic): seed the dealer with a fixed option
  position at t=0 and only test that it hedges as the *underlying* moves. Use
  this only if the flow process slips — it still exercises the hedge loop.
- Decision to record: the trigger surface for option fills and who owns it.

### E2 — Delta units: contracts → share-equivalents → equity hedge **lots**
This is the crux. The equity LOB trades in **integer lots**; `bs_greeks.delta`
is **per share**. CLAUDE.md's shorthand "hedge qty = −net_delta * lot_size" is
ambiguous about which unit `net_delta` is in — pin it down here.
- **Recommended convention:**
  - An option **contract is written on one lot** (`lot_size` shares) of the
    underlying. The dealer's option position is in **contracts**.
  - Per-contract delta in **lots** = `bs_delta` (per share) × `lot_size` shares
    ÷ `lot_size` shares/lot = **`bs_delta`**. So one contract contributes
    `position_contracts_i × bs_delta_i` lots of delta.
  - `net_delta_lots = Σ_i position_contracts_i × delta_i` (calls +, puts via
    their signed delta; include the equity hedge inventory as delta +1/lot).
  - `hedge_qty_lots = round(−net_delta_lots)` submitted as an equity **market**
    order (BUY if positive, SELL if negative; skip if 0).
- Record the rounding policy (`round` half-to-even is fine) and that the equity
  hedge inventory itself carries delta = +1 per long lot, so the loop converges.
- **Single conversion site:** a `dealer._net_delta_lots(spot, now)` method;
  never inline the contract→lot arithmetic elsewhere.

### E3 — When to hedge: after every fill, gated by threshold
CLAUDE.md: recompute portfolio delta after **every** options fill. Config gives
`delta_hedge_threshold`.
- **Recommended:** after every option fill (E1) **and** at each dealer step
  (underlying may have drifted), recompute `net_delta_lots`; submit a hedge only
  when `abs(net_delta_lots) > delta_hedge_threshold` (in lots). This avoids
  churning a 1-tick equity order every step while still flattening on real
  exposure. The **post-hedge** net delta is what the Phase 5 test asserts is
  within threshold of zero.

### E4 — Option quote pricing (vol, spread, rounding)
- **Recommended:** price the mid off `FlatVolSurface(vol_estimate)` and the
  Phase 4 pricer at the live spot (`spot_from_book(mid)`) and per-series `T`
  (`time_to_expiry_years`). Quote a two-sided option market by bumping vol by
  `± spread_vols` **vol points** (e.g. price the bid at σ−0.02·spread? — decide
  and record: vol-points vs vol-fraction) and re-pricing, so the option bid/ask
  straddle the theoretical value. This is the Phase 4 D4 carry-over: **Phase 5
  owns option-quote rounding** — round option prices to a tradable grid here
  (recommended: nearest tick, reusing the equity tick_size) and document it.

### E5 — Gamma limit
Config `gamma_limit`.
- **Recommended:** compute portfolio gamma (Σ contracts × gamma × lot scaling,
  same unit treatment as E2) and **stop quoting the side that would increase
  |gamma|** (or widen quotes) once `abs(portfolio_gamma) > gamma_limit`. Keep it
  simple in v1: refuse new option trades that push gamma past the limit; still
  hedge existing delta. Record the chosen enforcement.

### E6 — Chain lifecycle (re-strike or fixed?)
Phase 4 built the chain **once** at the anchor and kept strikes fixed (D3).
- **Recommended for Phase 5 v1:** keep the Phase 4 behaviour — build the chain
  once at dealer construction off the seeded BBO mid, strikes fixed. Re-striking
  as spot drifts is logged in `docs/TODO.md` backlog; defer to Phase 6 unless a
  run shows the spot leaving the strike grid materially.

---

## Step 1 — `sim/agents/options_mm.py`  (build + test first)
A new `Agent` subclass mirroring `equity_mm.py`'s shape (frozen
`OptionsMMConfig`, `__init__(agent_id, config, rng, ...)`, `step(state)`,
`on_fills(...)`). It holds: a `chain` (list[OptionSeries]), a `VolSurface`, the
`risk_free_rate`, `minutes_per_year`, `lot_size`, and an **option position book**
`dict[OptionSeries, int]` (contracts).

**Public surface (suggested):**
- `@dataclass(frozen=True) class OptionsMMConfig` — `arrival_rate`,
  `vol_estimate`, `spread_vols`, `delta_hedge_threshold`, `gamma_limit`,
  plus what E4 needs (e.g. `option_tick`).
- `class OptionsMarketMaker(Agent)`:
  - `quote(series, spot, now) -> (bid: float, ask: float)` (E4).
  - `on_option_trade(series, side, qty, spot, now) -> list[Order]` — the E1
    trigger: updates the option position book, then returns the equity hedge
    order(s) from `_hedge(spot, now)`.
  - `_net_delta_lots(spot, now) -> float` (E2 single site).
  - `_portfolio_gamma(spot, now) -> float` (E5).
  - `_hedge(spot, now) -> list[Order]` — builds the equity market order per E2/E3.
  - `step(state)` — recompute delta from the live mid and hedge if past
    threshold (E3); return equity orders. (Quoting option prices is for the
    flow process to read; the dealer's *equity* actions flow through `step`.)
- `net_delta_lots`, `option_positions`, `portfolio_gamma` read-only props for
  tests + diagnostics.

**Edge cases to handle explicitly (and test):**
- No reference price (mid and last_fill both None): emit no hedge (mirror
  equity_mm Audit P1-5).
- Expired series (`T <= 0`): delta is the step value from the pricer; ensure the
  position book either rolls/expires them or prices intrinsic without NaN.
- Hedge qty rounds to 0: emit nothing (no zero-qty orders — the LOB rejects).

**Tests (`tests/test_options_mm.py`):**
- After a single option fill, `_net_delta_lots` matches `pos × bs_delta`
  by hand for a known series.
- **The Phase 5 contract:** after `on_option_trade` + applying the returned
  hedge to a book, `abs(net_delta_lots) <= delta_hedge_threshold`.
- A long-call fill produces a **sell**-equity hedge (delta +), a long-put fill a
  **buy** hedge; signs are correct.
- Gamma-limit refusal: an option trade that would exceed `gamma_limit` is
  rejected/handled per E5.
- Threshold gating: a sub-threshold delta emits no hedge order.

## Step 2 — Wire the options-demand flow (E1)
`sim/agents/options_flow.py` (or a driver in the runner): a Poisson taker that,
on each event, selects a series + side + qty and calls
`dealer.on_option_trade(...)`. Register it on the Clock like any agent. Keep it
config-driven (`agents.options_flow: {arrival_rate, max_lots, ...}` — add to
`params.yaml`).

**Tests (`tests/test_options_flow.py`):** deterministic under a seeded rng;
generates trades only against existing series; respects `max_lots`.

## Step 3 — Runner + e2e: close the loop
- Extend `run_sim.py` (or a `run_sim_phase5` path) to build the dealer + flow
  alongside the Phase 3 agents, seeded BBO, and run.
- `tests/test_e2e_phase5.py`: run the full sim; assert (a) option fills occurred,
  (b) the dealer submitted equity hedge orders (equity book reacted — its mid or
  depth changed after hedges), and (c) **after each hedge cycle the dealer's net
  delta is within `delta_hedge_threshold` of zero** (the DoD assertion). Do not
  modify `test_e2e_phase2.py` (frozen).

## Step 4 — Config wiring
Add to `params.yaml` (single read site stays `config/loader.py`): the
`agents.options_flow` block and any new `agents.options_mm` keys E4/E5 need
(e.g. `option_tick`). Keep `options_mm` consumption to the dealer only.

## Step 5 — Close-out
- Update `CLAUDE.md`: flip Phase 5 → `[x]`, mark `agents/options_mm.py` (and any
  new modules) `[x]`, bump the test count, add the "Phase 5 Implementation
  Contracts" section capturing E1–E6 as frozen decisions.
- Update `ROADMAP.md` + `TODO.md` status.
- If you accumulated tech debt, add a "Phase 5 Audit" backlog and clear P0 in a
  dedicated cleanup commit before Phase 6 (same discipline as Phase 3/4).
- Check against the stylised facts: does the dealer's hedging visibly feed the
  equity book? That's the experiment Phase 6 will measure.

---

## Definition of done (Phase 5)
- `sim/agents/options_mm.py` (+ the options-flow driver) exist and are documented.
- `tests/test_options_mm.py`, `test_options_flow.py`, `test_e2e_phase5.py` pass;
  full suite green.
- **Net delta within `delta_hedge_threshold` of zero after each hedge cycle**
  (the Phase 5 test contract).
- The equity book demonstrably reacts to hedges (mid/depth moves).
- E1–E6 resolved and recorded in `CLAUDE.md`.
- No Phase 4 library behaviour changed; no frozen test modified; no new deps.

## House rules (unchanged, from CLAUDE.md / docs/README.md)
One module at a time; write the test with the module; commit a checkpoint after
each passing module (`Phase 5: <module> complete`); run the full suite before
every commit; `test_e2e_phase2.py` is frozen; no new dependencies beyond the
approved set; integer ticks for all LOB prices; log tech debt to a "Phase 5
Audit" backlog rather than fixing inline.
