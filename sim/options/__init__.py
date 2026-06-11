"""Options pricing library (Phase 4).

A pure, agent-free library the Phase 5 dealer will call:
- `pricer`  — Black-Scholes European price + Greeks (delta, gamma, vega).
- `surface` — implied-vol surface (flat to start, dynamic later).
- `chain`   — strikes × expiries grid anchored to the live underlying, plus
              the two frozen unit-conversion sites (D1 time→years, D2 spot).

See the "Phase 4 Implementation Contracts" section of CLAUDE.md for the
frozen D1–D5 unit decisions every function here obeys.
"""
