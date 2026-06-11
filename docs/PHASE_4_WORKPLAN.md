# Phase 4 Workplan — Options Pricing + Chain

> Goal: a correct, well-tested **options pricing library** (`sim/options/`) that
> the Phase 5 dealer will call. No agent uses it in Phase 4 — this phase ships a
> library + tests, not new market behaviour.

Defer to `CLAUDE.md` for the canonical BS formulas, coding standards, and scope
boundaries. This file is the build order, the open decisions, and the test plan.

---

## Step 0 — Resolve the open design decisions FIRST (do not skip)

These conversions are load-bearing: every Greek and every Phase 5 hedge depends
on them. Resolve each, **record the choice in `CLAUDE.md`** (a new "Phase 4
Implementation Contracts" section, mirroring the Phase 2/3 ones), then code.
Recommended defaults are given — adopt unless you have a reason not to.

### D1 — Simulation time → years (for `T` in Black-Scholes)
`MarketState.timestamp` is in **clock minutes**. BS needs `T` in **years**.
Pick one calendar and put the constant in `params.yaml` (e.g.
`market.minutes_per_year`).
- **Recommended:** continuous-time convention, `minutes_per_year = 525_600`
  (365 × 24 × 60). Simple, and the sim already treats time as continuous
  (Poisson arrivals, OU in minutes). A trading-calendar convention
  (390 min/day × 252 days = 98_280) is also defensible but couples vol scaling
  to a session model we don't otherwise have. Start continuous; revisit in
  calibration (Phase 6).
- `T_years = max(expiry_minutes - now_minutes, 0) / minutes_per_year`.

### D2 — Integer-tick underlying → BS spot `S`
Underlying prices are integer ticks (`tick_size: 1`, spot ≈ 10_000). BS is
scale-free in S/K, so:
- **Recommended:** use the tick price **directly** as `S` (and strikes as `K`),
  i.e. treat 1 tick = 1 price unit. With `tick_size: 1` this is exact and avoids
  a second unit. If `tick_size` ever ≠ 1, multiply by `tick_size` at the single
  conversion site. Keep the conversion in ONE function (e.g.
  `chain.spot_from_book(mid)`), never inline.

### D3 — Moneyness → integer strikes
The illustrative `[95, 97.5, 100, 102.5, 105]` in old docs is pre-integer-tick.
Generate strikes from **moneyness offsets** around the anchor spot.
- **Recommended:** `strikes_pct: [-0.05, -0.025, 0.0, 0.025, 0.05]` in config;
  `K = round(anchor_spot * (1 + pct))` snapped to a tick multiple. At spot
  10_000 → `[9500, 9750, 10000, 10250, 10500]`. Anchor = the mid at chain
  construction (document whether the chain re-strikes as spot drifts — for
  Phase 4, build once at the anchor and keep strikes fixed; re-striking is a
  Phase 5/6 decision).

### D4 — Option price units & rounding
The pricer returns a **float** option value in the same unit as `S` (ticks).
- **Recommended:** keep the pricer pure float; defer any tick-rounding of option
  *quotes* to Phase 5 where the options market is defined. Document that Phase 4
  pricing is float and Phase 5 owns the quote-rounding policy.

### D5 — Greeks set
`CLAUDE.md` gives delta, gamma, vega. Glossary also lists theta, rho.
- **Recommended:** implement **delta, gamma, vega** as required (Phase 5 hedging
  needs delta and gamma). Add theta/rho only if cheap and tested; otherwise
  leave a documented stub-free gap (don't ship untested Greeks).

---

## Step 1 — `sim/options/pricer.py`  (build + test first)
Pure functions; no state; SciPy norm CDF (`scipy.stats.norm.cdf` /
`norm.pdf`, or `scipy.special.ndtr`).

**Public surface (suggested):**
- `@dataclass(frozen=True) class Greeks: delta: float; gamma: float; vega: float`
  (+ `theta`, `rho` if D5 includes them).
- `bs_price(S, K, T, r, sigma, *, is_call: bool) -> float`
- `bs_greeks(S, K, T, r, sigma, *, is_call: bool) -> Greeks`
- A `d1`/`d2` helper (private).

**Edge cases to handle explicitly (and test):**
- `T <= 0` (at/after expiry): price = intrinsic `max(S-K, 0)` / `max(K-S, 0)`;
  delta = 0 or 1 (step), gamma/vega = 0. Don't divide by `sqrt(T)`.
- `sigma <= 0`: degenerate; return intrinsic (discounted) and zero gamma/vega.
- `S <= 0` or `K <= 0`: raise `ValueError` (invalid input).

**Tests (`tests/test_pricer.py`):**
- Known-value check vs a hand-computed/textbook BS price (pick a canonical set,
  e.g. S=100, K=100, T=1, r=0.05, σ=0.2 → call ≈ 10.4506).
- **Put-call parity:** `C - P == S - K*exp(-rT)` within tolerance.
- ATM call delta ≈ 0.5–0.6 region; put delta = call delta − 1.
- Gamma > 0 and symmetric for call/put at same strike; peaks ATM.
- Vega > 0; → 0 as `T → 0`.
- Expiry: `T=0` returns intrinsic; no NaN/inf.

## Step 2 — `sim/options/surface.py`
Implied-vol surface behind a small interface so a dynamic surface can drop in
later without touching callers.

**Public surface (suggested):**
- `class FlatVolSurface: def __init__(self, sigma: float); def vol(self, strike, expiry) -> float`
  (returns the constant `sigma` regardless of strike/expiry).
- Construct from config `agents.options_mm.vol_estimate` (or an `options.vol`).

**Tests (`tests/test_surface.py`):**
- Flat surface returns the same σ for any (strike, expiry).
- Interface is stable (a future `vol(K, T)` signature won't change for callers).

## Step 3 — `sim/options/chain.py`
Builds and manages the strikes × expiries grid, anchored to the underlying.

**Public surface (suggested):**
- `@dataclass(frozen=True) class OptionSeries: strike: int; expiry_minutes: float; is_call: bool`
- `def build_chain(anchor_spot, now_minutes, *, strikes_pct, expiries_days, minutes_per_year) -> list[OptionSeries]`
  (calls/puts at each strike × expiry).
- `def time_to_expiry_years(series, now_minutes, minutes_per_year) -> float`
  (the single D1 conversion site).
- `def spot_from_book(mid, tick_size) -> float` (the single D2 conversion site).

**Tests (`tests/test_chain.py`):**
- Correct number of series: `len(strikes) × len(expiries) × {call, put}`.
- Strikes match the D3 rule at a given anchor spot; snapped to tick multiples.
- `time_to_expiry_years` decreases as `now` advances; clamps at 0 past expiry.
- Lookups (by strike/expiry) return the right series.

## Step 4 — Config wiring
Add to `sim/config/params.yaml` (single read site stays `config/loader.py`):
```yaml
market:
  minutes_per_year: 525600          # D1
options:
  strikes_pct: [-0.05, -0.025, 0.0, 0.025, 0.05]   # D3
  expiries_days: [7, 14, 30]
  risk_free_rate: 0.05
agents:
  options_mm:                       # consumed in Phase 5; seed values now
    vol_estimate: 0.20
    spread_vols: 2.0
    delta_hedge_threshold: 0.05
    gamma_limit: 500
```
No agent reads `options_mm` yet — it's seeded so Phase 5 has it ready.

## Step 5 — Phase 4 e2e / integration test
`tests/test_e2e_phase4.py`: build a chain from a live `run()` result's book
mid, price every series off the flat surface, assert all prices finite and
parity holds across the chain. This proves the library composes with the
existing sim without wiring a new agent.

## Step 6 — Close-out
- Update `CLAUDE.md`: flip Phase 4 → `[x]`, mark `options/` modules `[x]`,
  bump the test count, add the "Phase 4 Implementation Contracts" section
  capturing D1–D5 as frozen decisions.
- Update `ROADMAP.md` + `TODO.md` status.
- If you accumulated tech debt, add a "Phase 4 Audit" backlog and clear P0 in a
  dedicated cleanup commit before Phase 5 (same discipline as Phase 3).

---

## Definition of done (Phase 4)
- `sim/options/{pricer,surface,chain}.py` exist and are documented.
- `tests/test_pricer.py`, `test_surface.py`, `test_chain.py`,
  `test_e2e_phase4.py` pass; full suite green.
- D1–D5 are resolved and recorded in `CLAUDE.md`.
- Greeks are numerically correct (known-value + parity tests pass).
- No agent behaviour changed; no frozen test modified; no new deps beyond SciPy.
