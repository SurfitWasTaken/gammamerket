# gammarket — Operating Docs (Fable handoff)

Welcome, Fable. This folder is your operating layer: **what to build, in what
order, and how you'll know it's done.** It sits on top of — and defers to —
`CLAUDE.md`, which remains the single source of truth for architecture,
coding standards, and the per-phase implementation contracts.

## Read in this order
1. **`../CLAUDE.md`** — project identity, architecture tree, coding standards,
   domain concepts (LOB, BS Greeks, delta-hedging loop), and the frozen
   implementation contracts. **Authoritative.** If anything here disagrees with
   it, CLAUDE.md wins (or fix one to match the other in the same commit).
2. **`GOALS.md`** — the north star and the definition of done (stylised facts).
3. **`ROADMAP.md`** — the six-phase plan and where we are.
4. **`PHASE_5_WORKPLAN.md`** and **`PHASE_4_WORKPLAN.md`** — the completed
   Phase 5 (Options Dealer + Delta Hedging) and Phase 4 (Options Pricing +
   Chain) plans, kept for reference. Their decisions (E1–E6, D1–D5) are frozen
   in `CLAUDE.md` as per-phase Implementation Contracts.
5. **`TODO.md`** — the living checklist. Keep it current as you work.

## Current state (Phase 5 complete — 2026-06-12)
- **Phases 1–5 complete.** LOB engine, equity agents (retail, institution, two
  competing market makers), discrete-event clock, central tape, metrics, the
  `sim/options/` library (Black-Scholes price + Greeks, flat vol surface,
  chain), and now the **options dealer + delta-hedging loop**.
- **All 255 tests pass:** `.venv/bin/python -m pytest tests/ -q`
- **Phase 5 shipped** `sim/agents/options_mm.py` (dealer: BS quoting, gamma
  cap, delta hedging) and `sim/agents/options_flow.py` (Poisson taker driving
  the quote-driven options market). The Clock owner-routes fills so
  flow-carried dealer hedges credit the dealer. E1–E6 are frozen in `CLAUDE.md`
  (Phase 5 Implementation Contracts). The e2e contract holds: net delta within
  `max(delta_hedge_threshold, 0.5)` lots of zero after every hedge cycle.
- **No open P0/P1 debt.** One latent pre-existing self-trade accounting edge is
  logged in the `TODO.md` backlog (not observed in any run).
- **Phase 6 is the immediate work** — Calibration, Analytics, Full Run:
  effective-spread/depth/vol metrics, calibration sweeps, and validating the
  stylised-facts checklist in `GOALS.md` end-to-end.

## How to work here (house rules, from CLAUDE.md)
- **One module at a time.** Complete and test a file before starting the next.
- **Tests are the checkpoint system.** After each module:
  `.venv/bin/python -m pytest tests/test_<module>.py -v`
- **Commit checkpoints** after each passing module:
  `git add -A && git commit -m "Phase 4: <module> complete"`
- **No refactoring working modules during a feature session.** If you find
  tech debt, log it (a new "Phase 4 Audit" backlog section, same format as the
  Phase 3 one) and clear it in a dedicated cleanup commit — don't fix inline.
- **`test_e2e_phase2.py` is frozen.** Do not modify it. Add new e2e tests per
  phase (`test_e2e_phase4.py`, etc.).
- **No new libraries without flagging.** Allowed: NumPy, SciPy (norm CDF),
  PyYAML, matplotlib, pytest, sortedcontainers. No Pandas in the hot loop.
- **Integer ticks for all LOB prices.** Options pricing works in float; the
  tick/year/strike conversions are an explicit Phase 4 decision (see workplan).

## Quick commands
```bash
.venv/bin/python -m pytest tests/ -q        # full suite
.venv/bin/python run_sim.py --no-plot       # run the full sim (Phase 5 loop), print summary
.venv/bin/python run_sim.py                 # + writes results/phase3.png
```
