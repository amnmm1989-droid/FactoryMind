# Part 1 — Market and Competitive Positioning

## Market map (2026)

| Segment | Tools | Who they serve |
|---|---|---|
| **Large enterprise** | SAP IBP, Kinaxis RapidResponse, o9 Solutions, Blue Yonder, Oracle Demantra | Complex global supply chains, thousands of SKUs, full financial integration |
| **Mid-market** | Logility, ToolsGroup, RELEX | Mid-sized manufacturers/distributors needing multi-echelon inventory optimisation |
| **Small & medium (SMB)** | Netstock, GMDH Streamline | Those who outgrew Excel but haven't reached an enterprise budget |
| **Open source** | frePPLe (planning & scheduling), Nixtla suite (forecast engine) | Those who want the code, not the subscription |

**FactoryMind belongs to no single row entirely.** Its philosophy is closest
to Netstock (SMB, no implementation expert required) but it is free and open
like frePPLe, and its forecast engine (9 models + demand classification) is
deeper than what any SMB tool publicly exposes.

## What each segment does excellently — that we don't yet

### 1. Large enterprise: concurrent planning and neuro-symbolic AI

Kinaxis allows scenario simulation across the whole supply chain at once.
o9 builds a Knowledge Graph instead of flat tables. Blue Yonder replaces the
single deterministic forecast with a probabilistic range of outcomes.

**The applicable lesson here (not all of it):** probability. FactoryMind
already has ETS confidence bounds
(`services/forecast_engine/statistical.py:65`), but they are a fixed margin
(`z × spread`), not a true model-specific probabilistic distribution. This
is a relatively simple difference to implement (Phase 2 in
`READINESS_3_PLAN.md`).

### 2. Mid-market / SMB: ready-made integration with every ERP

Netstock ships connectors for SAP Business One, Dynamics, NetSuite, Odoo,
and 12+ systems — **with no code change from the customer.** GMDH Streamline
likewise, with bi-directional integration to Excel, QuickBooks, and Shopify.

**The difference with us:** FactoryMind reads a manually-exported file
(CSV/Excel) and guesses its columns by name (`services/ingest.py:51` —
`PRODUCT_HINTS`). This works but is brittle: any column name outside the
list fails with a message describing a symptom, not a cause (discovered in
practice this week with the long-format SAP export). No direct API
connection — and this is a **conscious scope decision** (vision: analysis
only), not a technical shortfall.

### 3. Open source: transparency and zero cost

frePPLe does what no one else in this list does: **its code is fully open**,
and it integrates with Odoo as a direct add-on. But it plans production and
scheduling — a wider scope than "analysis and forecasting", carrying setup
complexity beyond what a production manager who wants to upload a file and
get an answer in a minute is looking for.

**The difference with us:** FactoryMind is deliberately simpler — and that
is correct for the target audience (the vision explicitly excludes order
creation). But simplicity has a cost: no alignment across aggregation levels
(product → category → total), and no handling of a new product with no
history — both of which frePPLe and o9 do excellently, and both implementable
within our current scope without widening it (Phase 2 in
`READINESS_3_PLAN.md`).

## FactoryMind's real advantages — not to be touched

These are not aspiration but measured reality today, and must remain the
core of any marketing message:

1. **Honesty over illusion.** The README shows real, rerunnable model-vs-
   model results on this catalogue (`scripts/measure_model_accuracy.py`) —
   and no commercial tool publishes such a number about itself, reproducible
   or not. This is the **Forecast Value Added (FVA)** discipline that
   the most mature planning teams practise: measuring every intervention
   against a naive baseline, not assuming complexity means accuracy.
   FactoryMind already practises it without naming it; naming it and turning
   it into a continuous metric (not a one-off report) is a cheap win
   (Phase 0 in the plan).

2. **Privacy by design, not by policy.** The user's file is never written to
   disk (`ui/data_source.py:9`), and hosted mode has no persistence at all.
   Large SaaS tools promise this in their contracts; this project makes it
   architecturally impossible.

3. **Genuinely free and open**, not a time-limited trial.

## A decision worth putting to the user, not assuming

This plan assumes no business model. But every improvement in
`READINESS_3_PLAN.md` implicitly assumes one question: **does the project
stay entirely free, or does a paid hosting layer get built later to cover
the cost of measurement and maintenance as usage grows?** No answer is
needed now — but a decision like "user accounts" (Phase 3) changes shape
depending on the answer.
