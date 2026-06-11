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
4. **`PHASE_5_WORKPLAN.md`** — your immediate work: Options Dealer + Delta
   Hedging (the core experiment). Module-by-module specs, the open design
   decisions (E1–E6) you must resolve first, and the test plan.
   **`PHASE_4_WORKPLAN.md`** is the completed Options Pricing + Chain plan,
   kept for reference (its D1–D5 contracts are frozen in `CLAUDE.md`).
5. **`TODO.md`** — the living checklist. Keep it current as you work.

## Current state (Phase 5 kickoff — 2026-06-11)
- **Phases 1–4 complete.** LOB engine, equity agents (retail, institution, two
  competing market makers), discrete-event clock, central tape, metrics, and the
  `sim/options/` library (Black-Scholes price + Greeks, flat vol surface, chain).
- **All 217 tests pass:** `.venv/bin/python -m pytest tests/ -q`
- **No carried-over tech debt.** The Phase 3 Audit backlog was cleared (commit
  `5d5779e`); Phase 4 needed no audit backlog. The audit section in `CLAUDE.md`
  is a dated resolution log, not an open backlog.
- **Phase 4 shipped** the options library with the D1–D5 unit conversions frozen
  in `CLAUDE.md` (Phase 4 Implementation Contracts). `params.yaml` now carries
  `market.minutes_per_year`, an `options` block, and a seeded `agents.options_mm`
  block (unused until Phase 5). `scipy>=1.10` is pinned in `requirements.txt`.
- **Phase 5 is the immediate work** — Options Dealer + Delta Hedging, the core
  feedback-loop experiment. Start at `PHASE_5_WORKPLAN.md` Step 0 (E1–E6).

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
.venv/bin/python run_sim.py --no-plot       # run the Phase 3 sim, print summary
.venv/bin/python run_sim.py                 # + writes results/phase3.png
```
