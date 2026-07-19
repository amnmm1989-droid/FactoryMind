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

⚠️ **Scope decision, not history**: this project no longer tracks a sales
manager's customer dimension or a plant manager's plan-adherence — both were
built and shipped, then removed deliberately to keep the tool to two
questions it answers well, not four it answers thinly. See the "Removed by
scope decision" note at the end of this file for what that took with it.

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

Not a slogan — a measurement: on the demo catalogue shipped today, most
products are intermittent (see the classification breakdown further down —
⚠️ its exact split has drifted from what this file claims in places; see the
correction note under Phase 3), and no single model family dominates the
rest — Naive holds a slim plurality of individual wins, but Prophet,
XGBoost, and ETS are close behind (see Phase 3's "measured result" below,
rerunnable with `scripts/measure_model_accuracy.py`). A tool claiming "95%
accuracy" lies to its user; a tool that says "this product cannot be
forecast — don't plan on it" gives them something they will not find
elsewhere.

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
models that all need ≥ 24 points, but not every product in a real catalogue
has that much non-zero history. Without baselines the engine would fail
outright on the sparser part of any catalogue — and there'd be no reference
to measure whether complex models earn their complexity at all.

**2. Eligibility by non-zero points, not series length.** Every product in
this demo has exactly 44 points, so a length criterion alone says every
product qualifies for SARIMA. They don't — 44 mostly-zero points is not the
same as 44 points of signal.

### The measured result — corrected

> **A correction, stated plainly.** This section used to cite a table
> measured on "43 products with ≥ 24 non-zero months" from what it called
> "the validation catalogue." That catalogue no longer exists in this
> repository — `data/data.json` today has **29 products total**, so a
> 43-product subset of it is arithmetically impossible. The claim had
> quietly gone stale, undetected, until a direct question about the
> engine's accuracy prompted someone to actually re-run the measurement
> instead of re-reading the old prose. Replaced below with what
> [`scripts/measure_model_accuracy.py`](../scripts/measure_model_accuracy.py)
> measures on the catalogue that actually ships today — rerunnable any time
> the engine or the demo data changes, not hand-copied again.

**28 of 29 demo products are evaluable** (one is entirely dead — zero sales
in all 44 months, no model applies):

| Model | Wins | Mean rank |
|---|---|---|
| Naive | 6 (21%) | 5.69 |
| Prophet | 5 (18%) | **3.91** |
| XGBoost | 5 (18%) | 4.65 |
| ETS | 4 (14%) | **3.65** |
| Croston | 4 (14%) | 5.81 |
| TSB | 2 (7%) | 5.54 |
| SARIMA | 1 (4%) | 4.74 |
| MovingAverage | 1 (4%) | 5.15 |
| RandomForest | 0 (0%) | 4.26 |

**No model dominates.** Naive holds a slim plurality of individual wins, but
Prophet and XGBoost win nearly as often, and ETS/Prophet have the *best*
mean ranks of all nine — the opposite of "complex models never help" this
section used to claim. The winning model beats the naive baseline (FVA > 0)
on 85% of evaluable products. The honest reading isn't "simple wins" or
"complex wins" — it's that **no single family is right often enough to
justify skipping the other eight**, which is the actual argument for
running all nine and measuring, not assuming.

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
- [x] `ui/pages/product_intelligence.py` — classification + risk breakdown
- [x] `ui/pages/advanced_analytics.py` — the original page, behaviour unchanged
- [x] `services/batch.py` — whole-catalogue computation and persistence

(`ui/pages/production_planning.py` also shipped in this phase — "system
suggestion → human decision" — removed later by an explicit scope
decision; see the Audience section at the top of this file.)

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

---

# Forward plan

Ordered by leverage, not by forced sequence. Item 1 precedes the others
because everything after it is built on its assumption.

> The competitive dimension of each item (metrics, hierarchy, cold start,
> accounts, scale) is detailed in [`READINESS_3_PLAN.md`](READINESS_3_PLAN.md).

## 1. Time granularity ✅

### The dangerous half — ✅ done: the gate

A weekly file used to be **accepted and treated as months**: 30 weeks read
as 30 months, and `SEASONAL_PERIODS = 12` hunting a cycle every **12
weeks** and calling it annual. No error — just confident, wrong analysis.

`services/ingest.detect_granularity` detected this from the start; what
changed is what happens next (see below) — it no longer rejects, it tags.

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

### The remaining half — ✅ done: actually supporting weekly/daily

All five detected granularities (daily/weekly/monthly/quarterly/yearly) are
now accepted, not just tagged and rejected — `Dataset.granularity` carries
it forward, and `ui/data_source.py::active_granularity()` exposes the
session's real granularity to every page.

Every location in the table below now derives its number from
`config.SEASONAL_PERIODS_BY_GRANULARITY`/`PERIODS_PER_YEAR_BY_GRANULARITY`/
`PANDAS_FREQ_BY_GRANULARITY`/`GRANULARITY_DAYS` instead of a constant —
threaded from the uploaded file through `forecast_product`/`recommend_
production`/`compute_risk`/`run_batch` down to each model:

| File | What changed |
|---|---|
| `config.py` | `SEASONAL_PERIODS_BY_GRANULARITY` (7/52/12/4/1), `PERIODS_PER_YEAR_BY_GRANULARITY`, `PANDAS_FREQ_BY_GRANULARITY`, `GRANULARITY_DAYS` — the single source both `services/ingest.py` and `services/risk_service` read from |
| `services/forecast_engine/statistical.py` | `ETSForecaster`/`SARIMAForecaster` take `seasonal_periods`/`freq`; `min_points`/`min_non_zero` are now instance attributes derived from them, not class constants fixed at 12/24 |
| `services/forecast_engine/prophet_model.py` | Same pattern, plus `weekly_seasonality` enabled only for daily data (a real day-of-week pattern), never for coarser grains |
| `services/forecast_engine/registry.py` | `default_models(granularity)` builds each model with the right periods/freq |
| `services/forecast_engine/cache.py` | granularity is part of the cache key — the same series under two granularities is two different results, not one cached under whichever ran first |
| `services/risk_service/factors.py` | `stock_depletion_risk` converts lead-time days using the real period length (was a fixed 30 always); `seasonality_factor`/`growth_rate` take the real cycle length and periods-per-year (was a fixed 12 always) |
| `models/forecasting.py` | `freq` parametrised too, default unchanged — this file stays frozen for `ui/dashboard.py`/`tests/test_models.py` per its own docstring |

**A bug the day-truncation caught**: `_finalize()` collapsed every date to
the 1st of its month before sorting and gap-detection — harmless when only
monthly data existed (every date already fell on day 1), but silently wrong
for weekly/daily data: two weeks in the same month collapsed to the same
truncated date, corrupting both column ordering and the gap count. Fixed by
truncating only when `granularity == "monthly"`.

Verified live: a genuinely weekly file (`2025-01-06, 2025-01-13, ...`)
uploads, reads back "Your file: 2 products × **8 weeks**" (not "months"),
and the Executive page computes real recommendations from it end to end.

### The label-format gap — ✅ done: reading ERP period headers

The verification above used **ISO-date** headers (`2025-01-06`). Real ERP
exports don't label periods that way: Odoo writes `W1 2023` for weeks,
`Q1 2023` for quarters, and a bare `2023` for years. `pd.to_datetime`
understands none of the first two, so weekly and quarterly files were
**rejected wholesale** — every column unreadable → `no_months`. And a bare
`2023` parses to `2023-01-01`; with every period landing on the 1st,
`detect_granularity` called three years "monthly" — silently, the worst
kind. So "all five granularities supported" held for the *detector* but not
for the *files a factory actually uploads*.

Fixed at the two points that were format-blind:

| File | What changed |
|---|---|
| `services/ingest.py::parse_full_date` | Parses `W# YYYY` (→ ISO-week Monday) and `Q# YYYY` (→ first month of the quarter); an impossible week (`W53` in a 52-week year) returns `None` → dropped column with a warning, not a crash |
| `services/ingest.py::detect_granularity_from_labels` | New: reads granularity from the *label shape* (`W#`/`Q#`/bare year) and runs **before** the gap detector — because quarterly and yearly both fall on day 1, where the gap detector cannot tell them from monthly. Absent a uniform explicit marker it returns `None` and the gap detector takes over unchanged |

Verified against the five real export files (daily/weekly/monthly/quarterly/
yearly): each now reads with its true granularity, and the seasonal models
(SARIMA/ETS/Prophet) run on quarterly data with `seasonal_periods=4`,
`freq="QS"` end to end. Covered by
`tests/test_ingest.py::test_each_erp_export_format_is_read_with_its_true_granularity`.

### The display gap — ✅ done: pages name the file's real unit

Detecting the granularity is not the same as *showing* it. Two blind spots
survived into the page labels, and a third was introduced by the ERP-header
fix above:

- **Hardcoded unit words.** Forecasting showed "Forecast horizon (months)"
  and "Next month forecast"; Product Intelligence "Months with sales" — for
  every file, weekly or yearly. Now the horizon slider, the no-evaluation
  notice, and the selling-periods metric take `{unit}` from the session
  granularity, and the next-period metric is worded period-generic.
- **Chart-axis collapse (a regression from the ERP-header fix).** Once
  `parse_month_label` learned to read `W1 2023` (→ `2023-01-01`),
  `format_month` began translating it to "January 2023" — so `W1`, `W2`,
  `W5` all rendered as the same "January 2023" on the x-axis. `format_month`
  now reformats **only bare month labels** (month name + year, or `YYYY-MM`);
  weekly/quarterly/yearly/daily labels pass through untouched, since they
  carry no month name to translate. The axis title itself now uses
  `granularity.one.*` (Week/Quarter/Year…), not a fixed "Month".

Covered by `tests/test_granularity_display_ui.py` (each page × weekly/
quarterly/yearly) and `tests/test_i18n.py::test_non_monthly_labels_are_not_collapsed_into_a_month`.

**The legacy page too — ✅ done.** Advanced Analytics wraps the older
dashboard (`ui/dashboard.py` + `ui/sidebar.py` + `ui/charts.py` +
`ui/tables.py`), which said "Months (>0)", "per month" and a chart x-axis of
"Month" regardless of the file. `granularity` now threads from
`active_granularity()` through `render_sidebar`/`render_dashboard`, so metric,
slider, and footer labels name the file's unit (`granularity.many.*` for
"Weeks (>0)", `granularity.unit.*` for the counted "26 weeks"), and chart axes
and the details-table column use `granularity.one.*`.

Verified live across weekly/quarterly/yearly with zero "month" leakage;
covered by `tests/test_granularity_display_ui.py::test_advanced_analytics_labels_follow_the_granularity`.

## 1b. Trimming the analyst view ✅

Then the page was **cut down**, ahead of selling the tool to real factories.
Each removed section was removed for a measured reason, not for tidiness:

| Removed | Why it was worse than nothing |
|---|---|
| "Seasonal analysis" | Split the range into four equal chunks and averaged them. That is not seasonality (it has no relation to position-in-cycle) — it said nothing at any granularity |
| Product correlation matrix | On series that are 80–95% zeros (this catalogue), correlations are mostly spurious — and the danger is that a planner acts on one |
| Distribution charts | The "distribution" of an intermittent series is a spike at zero; a density curve over it is meaningless |
| Trend analysis (slope/R²/p) | Linear regression over lumpy zero-heavy data yields numbers that look scientific and are fragile — false precision |
| ETS/SARIMA forecast | **Two forecasting paths meant two different numbers for the same product on two pages** — fatal in front of a factory betting on the number. And ETS ranks 8th of 9 here |

What survives is what genuinely has no equivalent on the other four pages:
multi-product comparison, outlier detection, summary statistics, and a raw
exportable table. The page is now **descriptive only** — "what happened" —
while "what will happen" belongs to the evidence-based Forecasting page.

Dead code removed with it: `models/forecasting.py` (the second forecast
path), `services/analytics.prepare_seasonal_data` /
`prepare_forecast_months`, and 40 orphaned i18n keys. `models/statistics.py`
stays — `trend_analysis` still feeds the risk engine.

**Why now:** it was structural, and every feature built on the month
assumption raised its cost. Without it, the claim "fits all manufacturing"
was **not honest**: food is weekly, aircraft are yearly.

## 2. Column mapping ✅

**Measured defect:** hint lists in `services/ingest.py` are guesses — and a
guess fails at **the first customer, not at your desk** (it failed on a
long-format SAP export this very week; one missing word, misleading error).

**Done:** a screen that shows the file's actual columns and asks "which is
the product? the month? the quantity?", pre-filled from the current hints
where they match. Triggers specifically when parsing fails with
`code="no_months"` on a file with at least 3 columns — the signature of an
unrecognised long format, not a genuinely malformed file. Every new file
format no longer doubles the odds of rejection: it doubles the odds of a
three-click recovery instead. See `READINESS_3_PLAN.md` Phase 1 for the
implementation detail and its tests.

## 3. Stock file — for the procurement manager ✅

Two ERP columns: `product, current stock`.

Unlocked:
- **Production**: "produce 240" → **"produce 190, you have 50"**
- **Confidence 80% → 100%**: stock depletion is the fifth factor, now computed

`inventory` has been ready since Phase 2; `stock_depletion_risk` was
written and waiting for its data — now fed via `ui/data_source.py::
active_inventory` (session-only, same privacy pattern as the sales file;
never written to SQLite). See `docs/READINESS_3_PLAN.md` 2.c for the
implementation detail and its tests.

**Partially resolved since**: Purchase Plan now takes a manual "typical
lead time (days)" input and flags each line urgent/can-wait against it
(`services/decision_engine/purchase_plan.py::_urgency`) — a real, if
coarse, answer to "when do I reorder?" **Still open**: this is one number
for the whole catalogue, not per-supplier, and it isn't a true
reorder-point system — that needs lead-time *variability* (multiple
order→delivery date pairs), which no current upload supplies.
`reorder_point`/`safety_stock` on `InventoryStatus` still default to
`0.0`; the urgency flag lives beside them, not inside them.

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

## 1c. Cutting CPU cost ✅

Profiled on the real files (per-model `duration_ms`, full family, 25 products):

| | Monthly | Weekly |
|---|---|---|
| Before | 12.52s | **357.94s** |
| After | 7.05s | **5.20s** |
| | 44% faster | **98.5% faster (69×)** |

Extrapolated to the full 185-product catalogue, the weekly file went from
**~44 minutes to ~38 seconds** per run.

Two measured changes:

**1. SARIMA removed.** It was pathological, not merely slow: `SARIMA(1,1,1)(1,1,1,52)`
on weekly data cost **~32 seconds per product** — 97.7% of all CPU on that
file — against ~0.2s for every other model. It won 1 product of 25 weekly and
2 of 25 monthly. Nothing else in the engine is remotely comparable, so it was
deleted rather than gated.

**2. Seasonal models skip intermittent demand.** `Forecaster.handles_intermittent`
(False for ETS/Prophet) makes `can_handle` reject intermittent/lumpy series.
This is not a preference but their definition — they look for a seasonal cycle,
and the gaps in an intermittent series are not a cycle. `DemandClass.SMOOTH`
already documented itself as "the ETS/SARIMA/Prophet domain". 84% of this
catalogue is intermittent, so most of that work was being spent where those
models cannot win.

**Accuracy cost: 3 products out of 50 changed winner** — SARIMA's wins moved to
Naive, ETS, and TSB. The engine's own evidence-based selection absorbed the
loss, exactly as "no single family is right often enough" predicts.

Covered by `tests/test_forecast_engine.py::test_seasonal_models_skip_intermittent_demand`
and `::test_an_intermittent_series_still_gets_a_forecast` (the speed-up must
never become a failure — intermittent series keep their own models).

## 1d. ADIDA — temporal aggregation ✅

The daily export is **95% zeros**, the weekly 87%. At that density the question
"how much on this particular day?" has no answer — not because the model is
weak, but because the data does not carry it. ADIDA changes the question:
aggregate into buckets of `k` periods (so the zeros are absorbed and the signal
appears), forecast there, then disaggregate evenly back.

`services/forecast_engine/aggregation.py` wraps a base forecaster (Croston by
default). Bucket size is `round(ADI)` — a bucket the width of the average gap
holds roughly one demand — clamped so the aggregated series never gets shorter
than the base model needs. Aggregation is **end-aligned**: the incomplete
remainder is trimmed from the *oldest* data, so the most recent periods always
form complete buckets (trimming the other end would make the last bucket a
short sum, dropping the forecast for a purely arithmetic reason).

**Scope:** intermittent/lumpy only. On smooth demand aggregation blurs detail
that is already visible, so `can_handle` declines it.

### Measured cost — free, and structurally so

| Model | ms per product |
|---|---|
| SARIMA (removed) | ~32,000 |
| XGBoost / Prophet | ~200 |
| ETS | ~110 |
| Croston / TSB | ~0 |
| **ADIDA** | **0.00** |

Zero is not a rounding artefact: aggregation hands the base model a series
`n/k` long, so it does *less* work than forecasting the original, and the
bucket/unbucket steps are O(n) numpy. It is therefore in the **fast default
set**, not behind the "all models" toggle.

### Measured benefit — it earns its place exactly where predicted

On the fast default set, ADIDA wins **3 of 20 products on the daily file** —
the sparsest one, which is precisely the case it was added for. On weekly and
monthly it wins nothing and costs nothing. That asymmetry is the honest result:
temporal aggregation pays off where density collapses, and is inert elsewhere.

## 2b. Validation report ✅

**"My tool is accurate" neither sells nor proves.** What does both is a number
on the customer's own data: *on your history, this is how accurate its advice
would have been.* `services/validation.py` produces that number.

### Rolling-origin, not a single holdout

`evaluation.backtest` scores **one model** on **one window** so the engine can
pick a winner. This scores **the whole tool** at **several points in time**:
for each origin, train on what came before it only, let the engine choose its
own model, then compare against what actually happened. It simulates what the
tool would have said had it been run that day — including its model choice.
One window can be luck; several reveal consistency.

No leakage: each origin sees `series[:origin]` and nothing after.
`tests/test_validation.py::test_training_never_sees_the_window_it_is_judged_on`
spies on the engine and asserts the exact training slice.

### Two traps found by measuring, not by reasoning

**1. Zero-demand windows read as perfect accuracy.** On 87%-zero weekly data,
**19 of 40 products** had an entirely zero test window. The model predicts
zero, actual is zero, so MASE came out `0.00` — and the catalogue median
reported "perfect". WAPE was already guarded (its denominator is Σ|actual|);
MASE now carries the same guard, and such products are reported as
**`no_demand`** — run, but nothing to measure. Median MASE went from a
flattering `0.00` to an honest `1.66–1.82`.

**2. `beat_naive` was judged on a mismatched benchmark.** MASE's denominator is
the naive *one-step, in-sample* error; scoring a 3-step-ahead forecast against
it charges the tool for the difficulty of the horizon rather than its quality.
`beat_naive` now compares against a naive forecast on the **same window and
same horizon**. The measured share moved from 17–21% (unfair) to **46–63%**
(fair).

### Measured on the five real files (fast models, horizon 3, 3 origins)

| File | Measured | No demand | Median WAPE | Beat naive | Runtime |
|---|---|---|---|---|---|
| Monthly | 87/185 (47%) | 83 | 50% | 46% | 0.2s |
| Weekly | 89/185 (48%) | 96 | 76% | 63% | 0.3s |
| Daily | 64/185 (35%) | 121 | 129% | 62% | 1.1s |

**Coverage is part of the result, not a footnote.** Its denominator includes
both the skipped and the no-demand products; dropping them would flatter the
median. That a third to a half of an intermittent catalogue has no measurable
accuracy *is* the finding — and saying so is what separates this report from
marketing.

Surfaced in Executive Overview behind a button (it is real work, not something
to run on every page load), with an Excel export carrying a second sheet for
everything that could **not** be measured, named and reasoned.

## 2c. Reference parity for the in-house models ✅

Croston, TSB and ADIDA are written in this repository — they exist in neither
statsmodels nor scikit-learn. That invites the question any factory's engineer
should ask: *who says your implementation of the paper is right?*

The metrics were already checkable (they match scikit-learn exactly). For these
models the practical reference is **Nixtla's `statsforecast`**, an open library
implementing the same papers. `tests/test_reference_parity.py` compares against
it. The dependency is **optional and test-only** — it is not in
`requirements.txt` (installing it downgrades pandas to 2.x against our 3.x
lock), and the tests skip cleanly when it is absent.

### What the comparison established

| Part | Result |
|---|---|
| Demand-size smoothing | **Matches exactly** — difference `0.0000000000` |
| Interval estimate | Differs, by convention not arithmetic |

Substituting the reference's interval convention into our demand estimate
reproduces `statsforecast` to `1e-6` on every test series — proving the
divergence is entirely two convention choices:

1. The reference counts a leading interval from the series start to the first
   demand; we count only observed gaps between demands.
2. The reference seeds smoothing with the first interval; we seed with the mean
   of the observed gaps.

### Why we did **not** simply adopt the reference

The initial instinct was to align and claim exact parity. Measuring stopped
that. `np.diff(idx + 1, prepend=0)` means a series that **starts with a demand
at index 0** yields a first interval of `1` — though no gap was observed before
it at all. With α=0.1 the seed stays heavy, so the interval estimate falls and
the forecast rises: measured **~35% divergence on a series starting with a
demand, against ~3% on one starting with a gap.**

So neither convention dominates: ours seeds from a whole-sample mean, theirs
invents an interval at the edge. The tests pin the trade-off — including the
phantom-interval artefact — so that neither is "corrected" into the other
without a deliberate decision.

**What can honestly be said to a customer:** the demand-smoothing half is
identical to the reference implementation, and the remaining difference is a
documented, tested convention in the interval estimate — not an unverified
guess.
