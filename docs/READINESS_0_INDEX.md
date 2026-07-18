# Global Readiness Plan — Index

**Goal:** move FactoryMind from a tool that works and tells its user the
truth, to a tool that competes with Netstock, GMDH Streamline, o9, and
Blue Yonder on function — while keeping what sets it apart from all of them:
**its honesty, its being free, and its being cloneable.**

This plan is built on two parallel research efforts: a survey of what the
world's best analysis and forecasting tools do today (2026), and a reading
of the actual code in this repository — not assumptions. Every gap named
here has a line of code that proves it.

## How to read these parts

| File | Answers | For |
|---|---|---|
| [`READINESS_1_MARKET.md`](READINESS_1_MARKET.md) | Who do we compete with, and how do we differ? | The decision-maker, before starting |
| [`READINESS_2_GAPS.md`](READINESS_2_GAPS.md) | Where is the code weaker than the global standard today? | Whoever wants to understand before implementing |
| [`READINESS_3_PLAN.md`](READINESS_3_PLAN.md) | What do we build, in what order? | Whoever wants to implement directly |
| [`READINESS_4_APPENDIX.md`](READINESS_4_APPENDIX.md) | The exact formulas and references | Whoever builds a specific phase |

**If you only want to execute:** go straight to `READINESS_3_PLAN.md` —
each phase there is independent, ordered by impact rather than forced
chronology.

## The governing stance — unchanged by this plan

From [`ROADMAP.md`](ROADMAP.md): the system is **analysis and forecasting
only**. No order creation, no direct ERP integration that writes back, no
live machine monitoring. This plan *deepens* readiness within that scope —
it does not widen it. Any item here that looks like it leaves the boundary
(such as a direct API connection) is **read-only**, and this is stated
explicitly where it appears.

## Executive summary — one line per phase

| Phase | What it solves | Why now |
|---|---|---|
| **0 — Metrics** | RMSE/MAPE aren't what professionals measure by; WAPE is the actual standard | Cheapest phase, highest immediate credibility |
| **1 — Connection** | Column guessing stays guessing; SAP/Odoo need visible mapping, not luck | Opens every export not yet tested |
| **2 — Intelligence** | No coherence between product, category, and total forecasts; nothing for a new product | Brings the engine closer to o9/Blue Yonder level |
| **3 — Collaboration** | ~~Removed~~ — built around Production Planning, which was removed by an explicit scope decision; see `ROADMAP.md`'s Audience section | N/A |
| **4 — Scale** | 29 products run in under a second; 30,000 (M5 size) never tested | A prerequisite for any real mid-sized customer |

Every number in the table above is backed by a source or a code reading —
the details are in the following parts.
