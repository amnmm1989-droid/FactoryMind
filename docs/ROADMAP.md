# ROADMAP.md
Manufacturing analysis & forecasting — vision, history, and forward plan.

---

# Vision

**An analysis and forecasting layer on top of the factory's existing systems
— never a replacement for them.**

The factory runs Odoo, SAP, or similar. It exports reports; this project
reads them, analyses them, and forecasts. It does not write to those systems,
does not store what they store, and does not compete with them.

## Audience

| Manager | ERP report | Question answered |
|---|---|---|
| **Production** | Sales Analysis | How much of each product should I make? |
| **Procurement** | Inventory + Sales | When do I reorder? Which products can't be planned by forecast at all? |
| **Sales** | Sales by Customer | Which customer grows? Which bleeds? Where is my risk concentrated? |
| **Plant** | Manufacturing Orders | Are we executing what we plan? |

## Explicitly out of scope

| Item | Why |
|---|---|
| **Creating orders** | The tool analyses; it does not commit. A wrong analysis is a rejected suggestion; a wrong order is money spent |
| **OEE and downtime** | Needs a live machine stream, not a CSV export. A different product |
| **Bills of materials (BOM)** | Was only needed for purchase orders; fell with them |
| **MOQ / unit cost / supplier** | Same reason. `products_meta` keeps only `lead_time_days` — the stock-depletion factor needs it |
| **Writing to ERP via API** | Permissions + version drift + one mistake equals real damage |

## Governing principle

**The tool's value is that it knows when it does not know.**

Not a slogan — a measurement: on this catalogue, **84%** of products are
intermittent, naive models win **60%** of the richest series, and Prophet
won **zero of 43**. A tool claiming "95% accuracy" lies to its user; a tool
that says "this product cannot be forecast — don't plan on it" gives them
something they will not find elsewhere.

Every new screen honours this: uncomputed factors are shown, confidence is
stated, and a number without an accuracy measure says so.

## Expansion rule

**Every new file format must bring a new question — not a new tab with the
same numbers.**

A sales manager who sees the production manager's screen under a different
title will leave. Expansion happens in *file formats*, not in screens.

> **Competitive readiness:** the detailed plan for reaching parity with the
> world's best forecasting tools lives in
> [`READINESS_0_INDEX.md`](READINESS_0_INDEX.md) (market map, gap analysis,
> phased execution plan, formulas). This roadmap stays the capability map by
> user file format; the two cross-reference each other.

---

# Completed phases — history and lessons

## Phase 0 — Foundation ✅

**Goal:** a solid base nothing depends on yet, but everything will.

- [x] ~~`core/app_config.py`~~ — **deleted.** See below.
- [x] `core/logging_config.py` — central logging (console + rotating file)
- [x] `core/exceptions.py` — unified exception hierarchy
- [x] `domain/entities.py` — object structure (ForecastResult, RiskScore,
      ProductionRecommendation, InventoryStatus) — no business logic yet
- [x] Unit tests (`tests/test_phase0_foundation.py`)

> **`core/app_config.py` — a lesson worth keeping in writing.**
>
> A settings layer was written to fix three real flaws in `config.py`:
> `os.makedirs()` on mere import, no environment-variable support, and
> `DATA_SOURCE` hardcoded. Its header carried a three-step integration plan.
>
> **Step two was never executed.** 23 modules kept importing the old
> `config`; nothing imported the new module except its own tests. 264 lines
> (code + tests) guarded a fix that was never applied — the three flaws
> stayed alive, and the module's existence implied they were handled.
>
> One of its tests was `assert not os.path.exists(...) or True` — an
> expression that is always True. A test whose name promises to guard side
> effects, and guards nothing.
>
> **Deleted.** `core/runtime_mode.py` proved the alternative: one environment
> variable added when a real need appears, not a whole layer built in
> anticipation. **An unapplied fix is not an asset — it is debt disguised
> as one.**

## Phase 1 — Domain + Service Layer Refactor ✅

- Extracted the compute logic of `ui/dashboard.py` into
  `services/product_analysis_service.py`, returning `domain.entities`
  instead of raw dicts.
- `models/forecasting.py` now raises `InsufficientDataError` /
  `ModelTrainingError` instead of swallowing exceptions.
- `core.logging_config` wired to every failure point.
- **No visible change to the Streamlit UI.**

## Phase 2 — DB Schema Extension ✅

**Goal:** move schema ownership from Python code to explicit migrations, and
prepare the tables Phases 3–5 would need.

- [x] `migrations/001..007` — baseline (months/products/sales), products_meta,
      inventory, forecasts, model_performance, recommendations, production_plans
- [x] `migrate.py` — idempotent and atomic runner, checksum drift detection,
      `--status` command
- [x] `SQLiteRepository._init_db()` **removed** — replaced by
      `_verify_schema()`, which raises `MigrationError` with clear
      instructions instead of silently creating tables
- [x] `tests/conftest.py` — tests run on a temporary database, never on
      `data/app.db`

**Behavioural note (since updated):** this phase made `python migrate.py`
mandatory before first run. That mandate later turned out to be a bug — a
hosting platform runs `streamlit run app.py` and nothing else, so every
visitor saw an error telling them to run a terminal command on a server they
don't own. `app.py` now calls `migrate()` at boot (idempotent), and a clean
clone works with `streamlit run` alone. See `tests/test_cold_boot.py` and
[`MIGRATION_GUIDE_PHASE2.md`](MIGRATION_GUIDE_PHASE2.md).

## Phase 3 — Forecast Engine ✅

**Goal:** one interface that trains several models, evaluates them, and picks
the best by evidence.

- [x] `services/forecast_engine/` — `base.py` (Forecaster contract),
      `naive.py` (Naive + MovingAverage), `statistical.py` (ETS + SARIMA),
      `prophet_model.py`, `tree.py` (XGBoost + RandomForest via lag
      features), `evaluation.py` (backtesting + MAE/RMSE/MAPE),
      `cache.py`, `registry.py`, `engine.py`
- [x] `repositories/forecast_repository.py` + `migrations/008` (links
      model_performance to its evaluation round)

### Two additions to the original plan — and why

**1. Baseline models (Naive + MovingAverage).** The plan asked for five
models that all need ≥ 24 points. But the median product here has **9
non-zero months out of 44**, and 39% of the validation catalogue has only
1–5 months. Without baselines the engine fails on 39% of the catalogue —
and there is no reference to measure whether complex models earn their
complexity.

**2. Eligibility by non-zero points, not series length.** Every product has
exactly 44 points, so a length criterion says every product qualifies for
SARIMA. They don't.

### The measured result (43 products with ≥ 24 non-zero months)

| Model | Wins | Mean rank |
|---|---|---|
| MovingAverage | 10 | **2.47** |
| Naive | **16** | 3.05 |
| RandomForest | 6 | 3.65 |
| XGBoost | 8 | 4.16 |
| ETS | 1 | 4.63 |
| Prophet | **0** | 4.81 |
| SARIMA | 2 | 5.23 |

**Naive models win 60% of cases on the richest data available.** Prophet
never won. Not an implementation flaw — it is what the data says: 44 monthly
points cannot support learning complex patterns. The real value of this
phase is that the system now **knows and measures that**, instead of
assuming complex means better.

### Documented deviation

- **The cache stores results, not models.** The plan asked for pickled
  models (joblib). Pickled Prophet/statsmodels objects are bound to library
  versions — one upgrade turns every file into a time bomb that loads and
  silently behaves differently. Storing the result skips training *and*
  prediction, and weighs kilobytes instead of megabytes.

## Phase 4 — Decision Engine + Risk Scoring ✅

- [x] `services/risk_service/factors.py` — five factors, each 0–100
- [x] `services/risk_service/scoring.py` — weighted sum + re-normalisation
- [x] `services/decision_engine/recommender.py` — recommendation + reason
- [x] `repositories/recommendation_repository.py` — persistence + `highest_risk()`
- [x] `domain/entities.py` — `RiskScore` factors became `float | None`

### The central decision: `None` is not zero

`stock_depletion_risk` needs the `inventory` table — empty until the stock
file lands. The easy choice was zero. But:

| Value | Meaning |
|---|---|
| `0` | We measured stock, and it covers demand — **safe** |
| `None` | We don't know how much you have — **unknown** |

Conflating them makes a product with unknown stock top the "safest" list.
So: unknown factors are excluded from the score and the remaining weights
re-normalise to 1.0. `RiskScore` carries `missing_factors` and `confidence`
— the score states what it was built on instead of hiding it. Database
columns accept NULL, so the distinction survives storage round-trips.

### A bug found by real use, not by tests

The first run on real data produced: **"produce 192 units … due to an
expected demand increase of 0.0%"**. Zero is not an increase.

The number was right and the sentence was a lie: `as_message` read `>= 0`
as "rise". Fixed with an explicit *stable* state.

The structural cause runs deeper: the winning model on most products is
`MovingAverage(3)`, and the comparison baseline is also 3 months — so the
change is **necessarily zero**. That is not a flaw to hide by changing the
window; the model genuinely predicts that next month looks like recent
months.

### Still open

- **Weights are an initial calibration with no validation data.** They get
  tuned once `production_plans.actual_quantity` accumulates against
  `planned_quantity`.

## Intermittent demand — Croston / TSB ✅

**Motivation:** the Syntetos-Boylan-Croston classification of this catalogue:

| Class | Count | Share |
|---|---|---|
| Intermittent | 122 | 66% |
| Lumpy | 34 | 18% |
| Smooth | 26 | **14%** |
| Erratic | 3 | 2% |

**84% of products are intermittent or lumpy.** The previous seven models are
all built for smooth demand — i.e. for 14% of the catalogue.

- [x] `intermittent.py` — `classify_demand` (ADI/CV²) + Croston + TSB
- [x] Croston with the Syntetos-Boylan bias correction (default)
- [x] TSB — updates demand probability every period, so it notices obsolescence
- [x] `cumulative_error` in `ModelMetrics` + metric selection by demand class

### Results — no gloss

On 46 **live** intermittent products (sold within the last 6 months):

| Model | Wins | Mean rank |
|---|---|---|
| MovingAverage | 8 | **3.05** |
| Naive | 12 | 3.48 |
| **Croston** | 7 | 3.79 |
| **TSB** | 6 | 4.07 |
| XGBoost | 6 | 4.25 |
| RandomForest | 3 | 4.65 |
| SARIMA | 3 | 5.20 |
| ETS | 1 | 5.45 |
| Prophet | 0 | 5.65 |

Croston + TSB win 13 of 46 (28%) — **a real presence, not a revolution**.
Baselines still lead. The data is hard, and models do not create signal
that isn't there.

### A recorded correction — the original motivation was wrong

This work was built on a Phase 4 observation: "a product that sold in 22 of
44 months gets a 'produce 0' recommendation, because RMSE rewards
predicting zero on intermittent series."

**Both halves were wrong:**

1. **The product was not alive.** Its last 8 months were zeros — genuinely
   dormant, and "produce 0" was the right answer. The original reading saw
   "22/44" and assumed activity.
2. **RMSE does not reward zero.** Squared error is minimised by predicting
   *the mean*. Zero wins only when the mean is zero — i.e. when the product
   is dormant, where zero is correct. A test written to confirm the claim
   failed, exposing it.

`test_rmse_does_not_reward_predicting_zero` and
`test_zero_is_rmse_optimal_only_when_demand_really_is_zero` remain to keep
the misleading intuition from returning.

**What stayed true regardless:** 84% of the catalogue is intermittent,
intermittent-demand methods fit it, and they win 28% of cases. The work
earned its place — just not for the reason it started with.

### `cumulative_error` — weak evidence, limited effect

After the original motivation collapsed, a decision-driven one remained:
if you produce for a whole horizon, your surplus or shortfall is exactly
|sum(forecast) − sum(actual)|, not per-month accuracy.

Strict measurement (three-way split — selection on one window, judgment on
a window that never entered selection):
- The two metrics agree on **30 of 34** (88%)
- When they disagreed: cumulative was better **4 of 4**
- Mean final RMSE: 121.0 (selected by RMSE) vs **114.8** (by cumulative)

**n=4 is weak evidence** (~6% chance of coincidence). The change stays
because its decision rationale stands on its own and its effect is limited
— **not because the numbers settled it**. Re-measure as data accumulates.

⚠️ `cumulative_error` measures **bias, not accuracy**: opposite errors
cancel. It is therefore restricted to intermittent series; RMSE remains for
smooth ones.

## Phase 6 — Dashboard for the production manager ✅

**Goal:** wire the engines to the UI. Before this phase, Phases 3–4 were
code guarded by tests that no user ever saw.

- [x] `app.py` — an `st.navigation` shell with five pages, computing nothing
- [x] `ui/pages/executive.py` — "what needs my attention?"
- [x] `ui/pages/forecasting.py` — Phase 3 engine + model comparison
- [x] `ui/pages/production_planning.py` — system suggestion → human decision
- [x] `ui/pages/product_intelligence.py` — classification + risk breakdown
- [x] `ui/pages/advanced_analytics.py` — the original page, behaviour unchanged
- [x] `services/batch.py` — whole-catalogue computation and persistence

### Batch, not compute-on-load — a measurement settled the design

| Models | Full catalogue |
|---|---|
| Light (4) | **under a second** |
| Full (9) | **3.3 minutes** |

An executive page that runs all nine on every load is dead on arrival. This
is why `forecasts` and `recommendations` have existed since Phase 2:
`services/batch.py` fills them, pages read instantly. The full family stays
an explicit user choice.

### A decision the data forced: risk alone makes a useless screen

First run: the top-5 riskiest products **all recommended "produce 0"** —
dead products with volatile history. High risk, zero required action.

So the primary screen is **what needs production** (quantity > 0) ordered
by risk, and risky-but-dormant products sit in a separate collapsed
section. The number that proves the decision: **zero** of the 83 products
needing production were high-risk — mixing them would have buried what
needs a decision.

### Three bugs found by running, not by tests

1. **`st.Page` path collision.** Every closure `_page()` returns is named
   `run`, and Streamlit derives the URL from the function name →
   `StreamlitAPIException`. Fix: explicit `url_path` per page.
2. **"Produce 0" inside a table called "needs a decision".** Croston/TSB
   produce fractional *rates* (0.4 units/month) and `round()` displayed
   them as zero. Fix: `MIN_ACTIONABLE_UNITS = 0.5` threshold + one-decimal
   display for small values.
3. **An empty comparison table** on a product with 4 sales months: no model
   could be evaluated (the series is too short to split into train and
   test). Documented engine behaviour (no evidence → simplest wins), but it
   looked like a defect. Fix: an explicit notice instead of the empty table.

### The default page is served at the root

`st.Page(default=True)` is served at `/`, not at its own `url_path`.
Recorded in the run skill's driver.

### Later hardening (post-Phase 6, all shipped)

- **Cold boot**: `app.py` builds the database at startup; a clean clone
  works with `streamlit run` alone. Six tests in `tests/test_cold_boot.py`
  all fail on the pre-fix code.
- **Frozen paths**: repositories used `db_path: str = DATABASE_PATH` —
  a Python default evaluated once at import and frozen forever. That made
  the boot path untestable, which is exactly why the cold-boot bug survived.
  Now every repository resolves its path at call time
  (`repositories.base.resolve_db_path`), with structural guards.
- **Plan ↔ recommendation link**: `production_plans.source_recommendation_id`
  existed since migration 007 — with a foreign key and a comment explaining
  it is the *reason* the two tables are separate — and nothing ever wrote
  it. The planning page held its own SQL and omitted it, so the question
  the table was built to answer ("how often are our recommendations
  followed?") was unanswerable. `ProductionPlanRepository` now owns the
  table, writes the link, and `adherence()` answers the question.
  `test_the_page_holds_no_sql` keeps UI pages out of the SQL business.

---

# Forward plan

Ordered by leverage, not by forced sequence. Item 1 precedes the others
because everything after it is built on its assumption.

> The competitive dimension of each item (metrics, hierarchy, cold start,
> accounts, scale) is detailed in [`READINESS_3_PLAN.md`](READINESS_3_PLAN.md).

## 1. Time granularity

### The dangerous half — ✅ done: the gate

A weekly file used to be **accepted and treated as months**: 30 weeks read
as 30 months, and `SEASONAL_PERIODS = 12` hunting a cycle every **12
weeks** and calling it annual. No error — just confident, wrong analysis.

`services/ingest.detect_granularity` now detects and rejects anything
non-monthly, explaining why. The tool knows when it does not know again.

**Two rules learned through a failed first attempt:**

1. **A label without a day cannot be finer than a month.** "January 2024"
   is monthly by construction however far it sits from its neighbour. The
   first implementation classified gaps (mode) and rejected monthly data
   with holes (Jan/Jun/Dec → gaps of 152 and 183 days → "quarterly") — and
   84% of this catalogue is intermittent, i.e. exported with missing
   months. **A false rejection is also a defect — just a louder one.**
2. **With explicit days, the smallest gap is the granularity.** Gaps are
   its multiples, not another granularity: weekly with a hole gives gaps of
   7 and 14 — the smallest is the truth.

### The remaining half — actually supporting weekly/daily

Needed: derive the seasonal period from the granularity (7 / 52 / 12 / 4)
instead of the constant 12, and generalise horizons and lead times.

Month-anchored locations — **seven, counted not estimated**:

| File | Line |
|---|---|
| `config.py` | 28 — `SEASONAL_PERIODS = 12` |
| `services/forecast_engine/statistical.py` | 48 — `freq="MS"` |
| `services/forecast_engine/prophet_model.py` | 51, 70 — `freq="MS"` |
| `services/risk_service/factors.py` | 156 — `lead_time_days / 30.0` |
| `models/forecasting.py` | 27, 95 — `freq='MS'` |

**Why now:** it is structural, and every feature built on the month
assumption raises its cost. Without it, the claim "fits all manufacturing"
is **not honest**: food is weekly, aircraft are yearly.

## 2. Column mapping 🔴

**Measured defect:** hint lists in `services/ingest.py` are guesses — and a
guess fails at **the first customer, not at your desk** (it failed on a
long-format SAP export this very week; one missing word, misleading error).

Needed: a screen that shows the file's actual columns and asks "which is
the product? the date? the quantity?", pre-filled from the current hints.
Every new file format doubles the odds of rejection without it.

## 3. Stock file — for the procurement manager

Two ERP columns: `product, current stock`.

Unlocks:
- **Production**: "produce 240" → **"produce 190, you have 50"**
- **Procurement**: stock coverage and reorder timing
- **Confidence 80% → 100%**: stock depletion is the fifth, uncomputed factor

`inventory` has been ready since Phase 2; `stock_depletion_risk` is written
and waiting for its data.

## 4. Actual production file — for the plant manager

Same shape as the sales file: `product, month, produced quantity`
(manufacturing orders report from the ERP).

Unlocks:
- **Plant**: planned vs actual — plan adherence
- **The system calibrating itself**: `production_plans.actual_quantity` has
  existed since Phase 2, empty. Filling it lets us tune the risk weights
  documented as "initial calibration with no validation data".

**The system starts grading itself instead of claiming.**

> **Half of this became available early.** The first question — "how often
> are recommendations followed?" — needed `source_recommendation_id`, not a
> new file. The column existed since 007 and nothing wrote it (see the
> hardening notes above). `ProductionPlanRepository.adherence()` answers it
> now. **The second question** — "are outcomes better when they are
> followed?" — is the one that still waits for `actual_quantity` from this
> file.

## 5. Customer dimension — for the sales manager

`product, customer, month, quantity` (Sales by Customer). A third dimension
— `services/ingest.py` reads two today.

Unlocks analysis that exists on no other page: risk concentration ("40% of
your sales come from two customers"), bleeding customers, growth by
customer.

**Analysis only — no order creation.** The sales manager receives orders;
he does not place them.

---

## An architectural tension to resolve

**Monitoring needs storage; hosted mode stores nothing — deliberately.**

"What changed since last month?" requires saving last month. But one
instance serves all visitors and `app.db` is a shared file, so persistence
means one visitor's data leaking to the next (see `core/runtime_mode.py`).

**Current decision:** monitoring over time is **local-mode only**. Hosted
stays "analyse your file now". Acceptable — provided the UI says it
explicitly rather than letting users discover it.

If user accounts ever land (READINESS Phase 3), this decision must be
revisited *by re-scoping the promise, not breaking it*: a planner's account
and name are one thing; their sales file is another. Keeping those separate
is what preserves the privacy guarantee.

## Tests — continuous, not a phase

No phase is complete without a green suite; that is standing behaviour, not
a checkbox.

**The count is not written here.** It once said "354" while the truth was
369 — an external reviewer copied the wrong number because he trusted this
document. A number that describes the code without being derived from it
goes stale silently — the same defect class as a sidebar describing data
that had been replaced. The live count is in the
[CI log](https://github.com/amnmm1989-droid/FactoryMind/actions/workflows/ci.yml).

Since 2026-07-17 the suite runs automatically on every push to `main` and
every PR (`.github/workflows/ci.yml`, against `requirements.lock.txt`, not
the loose file). Before that it ran only by hand: a suite without a runner
equals zero tests.
