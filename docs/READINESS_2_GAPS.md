# Part 2 — Gap Analysis (from the code, not from assumption)

Every line here is confirmed by an actual code reading in this session or
prior ones — not a guess. Where a gap exists, the nearest code location is
cited so implementation can start there directly rather than from scratch.

## 1. Metrics: RMSE/MAPE instead of the industry standard

`services/forecast_engine/evaluation.py` computes MAE, RMSE, MAPE (with
divide-by-zero protection), and cumulative_error — four metrics designed
with genuine care. But **none of them is WAPE**, which planning experts
describe as *"the default for demand planning, and the best for operational
decisions"* — because it weights the error by demand size, preventing a
small product from flipping the comparison, which is exactly what MAPE
suffers from here (hence the divide-by-zero protection was needed at all).

Also: no continuous tracking of **Forecast Value Added** — measuring each
model or human intervention against a naive baseline over time. The README
presents this as a one-off report ("naive models win 60%"), but it is not
stored as a live metric accumulating with every batch
(`services/batch.py`).

## 2. No alignment across aggregation levels (Hierarchical Reconciliation)

`services/batch.py:92` iterates over each product **entirely independently**:
```python
for index, (name, series) in enumerate(products.items(), start=1):
```
No category total, no grand total, and no guarantee that the forecast of 29
products sums to a figure consistent with a directly-computed total
forecast. For a plant manager who wants "how much will we produce this
month?" as a single answer, this is a fundamental difference — and it is
what every enterprise tool solves with the standard MinT (Minimum Trace)
technique, in use since 2019.

## 3. No special handling of the new product (Cold Start)

`services/ingest.py` sets `MIN_MONTHS = 3` as an absolute floor. Below that:
`InsufficientDataError` — a full rejection, no estimate. The industry uses
attribute matching (category, price, size) to borrow a demand pattern from
similar existing products. A new product in FactoryMind today is **invisible
in every report** — not "we don't know" but total absence, which is worse
than the explicit `None` that `risk_service` practises everywhere else
(`services/risk_service/factors.py:5`).

## 4. Probability is shallow

`services/forecast_engine/statistical.py:65`:
```python
margin = CONFIDENCE_LEVEL * spread
```
A fixed margin (`1.96 × spread`), not a probabilistic distribution derived
from each model's nature. Blue Yonder and o9 build a full outcome range, not
a single number with a margin. This ties directly to a deeper gap: **no
computed safety stock** — `services/risk_service/factors.py:149` returns
`None` for the stock-depletion factor because the `inventory` table
(`migrations/003_inventory.sql`) has existed structurally since Phase 2 and
was never filled. The standard safety-stock formula
(`z × √(σ²_d×L + μ²_d×σ²_L)`) needs exactly what is missing: a probabilistic
distribution + stock data.

## 5. System connection: guessing, not mapping

`services/ingest.py:51`:
```python
PRODUCT_HINTS = ("product", "item", "sku", "material", "part", "المنتج", "الصنف", "المادة")
```
A list that gets a word added every time a new export breaks it — as
happened in practice this week with the long-format SAP. Netstock and GMDH
ship connectors for every known system in advance; FactoryMind guesses a
column name. This is **not necessarily wrong** — the vision deliberately
excludes direct ERP connection — but a **visible column-mapping screen**
(the user picks which column is "the product" when the guess fails) is a
middle ground not yet built, and listed in `docs/ROADMAP.md` as the first
item from the start.

## 6. No accounts, no roles, no collaboration

`ui/data_source.py` — every session is isolated by Streamlit design, with no
persistent account. This is entirely correct for privacy (an advantage, not
a gap) but it prevents any form of team planning: a sales manager and a
production manager cannot see the same saved plan and comment on it, and
there is no continuous measurement over time of who follows recommendations
(which is exactly what we partly fixed by adding
`source_recommendation_id` — but it is session-local, with no account
tying it to a specific planner).

**The good news:** Streamlit natively supports `st.login()` and OIDC since
1.32 — no need to rebuild the UI on another framework to add accounts.

## 7. Scale: 29 products is not proof of 30,000

`services/batch.py` measures for real: 29 products with light models
< 1 second, with the full nine 3.3 minutes. This is a real number **on 29
only**. The reference M5 catalogue (the global forecasting competition) has
**30,490 series**. The loop in `batch.py:92` is sequential with no
parallelism, and every save (`ForecastRepository`,
`RecommendationRepository`) opens a fresh SQLite connection on its own.
There is no measurement and no test at that scale — the gap here is not in
the code but in the **absence of evidence**.

## What is not a gap — and deserves clarifying

- **No order creation**: a scope decision from the vision, not a shortfall.
- **No direct ERP connection**: a scope decision from the vision, not a
  shortfall.
- **Monthly data only**: a known, documented limit (`README.md`), the first
  roadmap item already, not a new discovery here.
- **The statistical family (Croston/TSB/ETS/SARIMA)**: entirely appropriate
  for the small-to-mid catalogue sizes targeted. No need to replace it with
  heavier models (LightGBM, foundation models like TimeGPT/Chronos) before
  real usage scale proves it the right phase — see Part 4 in
  `READINESS_3_PLAN.md` for the exact timing.
