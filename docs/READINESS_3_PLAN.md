# Part 3 — Execution Plan

Ordered by impact on credibility and competitive readiness, not by forced
chronology. Each phase is independent and executable on its own. Exact
formulas and references are in
[`READINESS_4_APPENDIX.md`](READINESS_4_APPENDIX.md).

---

## Phase 0 — Metrics (cheapest, highest credibility) ✅

**The problem**: `services/forecast_engine/evaluation.py` does not compute
WAPE, the actual standard for demand planning. And there is no continuous
Forecast Value Added tracking.

**Tasks**:

1. [x] Add `wape` to `ModelMetrics` (`evaluation.py`) — formula in the
   appendix. It does not replace RMSE (which stays the
   statistically-justified internal selection metric); it is shown to the
   user as a "practical accuracy" number understandable without a
   mathematical explanation.
2. [x] Show WAPE in `ui/pages/executive.py` alongside confidence — the
   current `RiskScore.confidence` shows 4/5 factors; WAPE answers "and do we
   trust the number itself?"
3. [x] **FVA panel**: after each batch, compare the winning model
   specifically against `NaiveForecaster` — not the best of the nine. Stored
   in `forecasts.fva` (migration 009) and surfaced as a live summary caption
   on the executive page, turning the README's static claim ("60% naive
   models win") into a metric that shifts with each user's data.

**Acceptance criterion**: an executive page showing "our actual accuracy
this month: WAPE X%, and complex models beat the moving average in Y% of
products" — a sentence no commercial competitor says about itself.

**Delivered.** `domain.entities.ForecastResult` carries `wape` and `fva`;
`services.forecast_engine.engine._forecast_value_added` computes FVA by the
same metric the winner was selected with (rmse or cumulative_error) — never
mixing metrics between the naive baseline and the winner. `None` when Naive
was never evaluated in that round (no fake zero implying a comparison that
never happened); `0.0` exactly when Naive itself is the winner (no value
added over itself, by definition, not by absence of measurement).

Verified live: a fresh catalogue run rendered
*"Across 26 products with a valid comparison: the chosen model beat the
naive baseline in 17 of them (65%)"* — a real, session-computed number, not
a static claim. 4 new tests confirm the FVA arithmetic matches a direct
recomputation from the underlying evaluations, including the case where
SARIMA beats Naive by a measured margin (rmse 6.6e-12 vs 33.3) on a
seasonal series.

`RecommendationRepository` reads `forecast_wape`/`forecast_fva` via a
`LEFT JOIN forecasts` on the existing `forecast_id` link — not a second copy
of the same numbers in two tables, which would drift.

**Size**: small. No architectural change — adding a field and a statistical
comparison on an existing structure.

---

## Phase 1 — Connection (opens every untested export) — task 1 done ✅

**The problem**: `PRODUCT_HINTS`/`MONTH_HINTS`/`QUANTITY_HINTS` in
`services/ingest.py` is a guess list that grows by accident, not by design.

**Tasks**:

1. [x] **Visible column-mapping screen**: when `_detect_layout` fails (finds
   no hint for a column), the file is not rejected — its actual columns are
   shown to the user with dropdowns: "which column is the product? the
   month? the quantity?" This turns every unknown export from a full
   rejection into a second of user work, with no code touched.
2. [ ] **Expanding hints by evidence, not by guessing**: any column name
   added from now on needs a real export to prove it (the same constraint
   placed this week after the German SAP column guessing error) — it stays,
   it is not relaxed.
3. [ ] **Downloadable template with customisable columns**: `to_csv_template()`
   currently shows fixed names; offering it downloadable with common source
   system columns (SAP/Odoo) as an option reduces the need for manual
   mapping in the first place.

**Acceptance criterion**: any CSV with Arabic or English or German columns,
long or wide, is read either automatically or by a three-click manual
mapping — no silent rejection.

**Task 1 delivered.** `services/ingest.py` gained `read_columns()` (exposes a
file's real headers, no analysis), `guess_column()` (the existing hint logic,
exposed to pre-fill the dropdowns — never forces a guess), and
`parse_upload_with_mapping()` (parses the long layout from user-chosen
columns instead of detected ones, sharing every downstream check — the
granularity gate, duplicate-row summing, warnings — via the same `_finalize`
helper `parse_upload()` now also calls, so a manually-mapped file is held to
exactly the same standard as an automatically-detected one).

The screen appears specifically when parsing fails with `code="no_months"`
and the file has at least 3 columns — the signature of a long-format file
whose column names weren't recognised (rather than a genuinely malformed
one, where showing a mapping screen would mislead). Widget keys are scoped
to the upload's `file_id`, so a second, different file never inherits stale
selections from the first.

Verified two ways: unit tests on the new `ingest.py` functions (including a
direct before/after pair — the same unrecognised-column file that
`parse_upload` rejects is accepted by `parse_upload_with_mapping` once the
user names its columns), and `tests/test_column_mapping_ui.py`, which drives
the actual running `app.py` through Streamlit's `AppTest` — uploading a real
file, reading the rendered dropdown options, selecting values, clicking the
button, and asserting the resulting session state — not a function called
in isolation. Confirmed the harder way too: 5 of 7 UI tests were checked to
actually fail against the pre-feature code before this was called done.

**Size**: medium. The visible screen needs extra session state in
`ui/data_source.py`, but the reading logic (`_from_long`/`_from_wide`) does
not change.

---

## Phase 2 — Intelligence (brings the engine to enterprise level)

### 2.a — Level alignment (Hierarchical Reconciliation)

**The problem**: `services/batch.py` forecasts each product independently;
no guarantee that the sum of a category's product forecasts matches the
directly-computed category forecast.

**The task**: after forecasting each product, aggregate by category (if a
product classification exists — currently absent, so this partly depends on
Phase 1 to introduce an optional category column), and compute Bottom-Up as
a first step (the simplest: aggregation from the bottom up with no
statistical adjustment) before moving to the more accurate MinT. Formulas in
the appendix.

**Acceptance criterion**: the sum of all a category's product forecasts =
the category forecast shown on a single executive panel, always,
arithmetically — not approximately.

### 2.b — New-product handling (Cold Start)

**The problem**: `MIN_MONTHS = 3` rejects any newer product — no estimate,
total absence.

**The task**: when a product's history falls below the floor, show it in a
separate section ("new products — no sufficient estimate yet") instead of
hiding it, with an optional choice: manually pick a "similar product" from
the existing catalogue and borrow its demand pattern
(Croston/ETS/smooth classification etc.) as an initial estimate, explicitly
labelled "borrowed, not computed". The explicit `None` here becomes a
labelled estimate — not an invented number without a warning.

**Acceptance criterion**: a product one month old is **visible** in every
report, clearly marked as lacking sufficient history, not silently absent.

### 2.c — True probability (depends on the stock file — outside this session)

**The problem**: the confidence margin is fixed (`1.96 × spread`), and
safety stock is uncomputed because stock data is absent (Phase 5 in
`docs/ROADMAP.md`, not started).

This item is **tied to something outside this plan's scope** — it needs the
stock file imported first (the first phase in the original roadmap). Once
available: the standard safety-stock formula in the appendix is ready to
apply directly on top of `risk_service/factors.py:stock_depletion_risk`,
which was built to receive it (`None` currently for exactly this reason, not
a defect).

---

## Phase 3 — Collaboration (from individual tool to team tool)

**The problem**: no persistent accounts; `source_recommendation_id` (fixed
this session) links the plan to the recommendation but **within one
session**, not across planners.

**Tasks**:

1. **Accounts via `st.login()`** (OIDC, natively supported in Streamlit
   ≥ 1.32): no UI rebuild. Each planner saves plans under their name, not a
   transient session.
2. **Adherence dashboard**: `ProductionPlanRepository.adherence()` (added
   this session) actually answers "how many plans are followed?" now — but
   no screen shows it yet. This is the cheapest possible collaboration
   feature: the code is ready, only the display is missing.
3. **Comments and context on the decision**: a `notes` field exists in
   `production_plans` (`migrations/007`) and is already used — expanding it
   to a multi-comment log (who edited it and when) needs a small extra
   table, not a redesign.

**Acceptance criterion**: a production and a sales manager see the same plan,
under their names, and a dashboard saying "78% of this month's
recommendations were followed, and the average deviation when overridden was
X units".

**Size**: relatively large — accounts change the "no persistent user state"
assumption the whole project was built on. It deserves an explicit decision
from the owner before starting (see the business-model note in
`READINESS_1_MARKET.md`) — because a persistent account means persistent
data, and this touches the current privacy promise ("nothing is saved when
hosted") and needs re-phrasing it, not breaking it: **a planner's account
and name are one thing, their sales file another entirely — separating them
is what preserves the promise.**

---

## Phase 4 — Scale and robustness (prerequisite for any real mid-sized customer)

**The problem**: 29 products measured; 30,000 (the reference M5 competition
size) unmeasured. `services/batch.py` is sequential, with a fresh SQLite
connection per save.

**Tasks ordered by cost**:

1. **Measure first, don't optimise blind**: create a synthetic catalogue of
   1,000 then 10,000 products (with the same `scripts/generate_demo_data.py`
   generator at larger size), and run `run_batch` with the light models.
   Record the time before any change — this is the same principle the
   project applies everywhere else: measurement before claiming.
2. **If the time is unacceptable**: parallelism at the product level
   (`concurrent.futures` or `multiprocessing`) — each product is entirely
   independent of the others in `batch.py:92`, so parallelism is safe with
   no coordination.
3. **One SQLite connection per batch, not per row**: `ForecastRepository`
   and `RecommendationRepository` open a connection per call — passing a
   shared connection across the whole batch (instead of row by row) reduces
   I/O overhead linearly with catalogue size.
4. **When SQLite is proven the real bottleneck** (not before): DuckDB is a
   close alternative with no major SQL change, suited to the heavy
   analytical read loads this project specifically does.

**Acceptance criterion**: a real, published time figure for a 10,000-product
catalogue, not an assumption. If it is acceptable (seconds, not minutes),
**steps 2–4 are never executed** — this is exactly the same lesson as
`core/app_config.py`, deleted this session: a solution to a problem not yet
proven is debt, not an asset.

---

## The suggested order if one number is requested

**0 → 1 → 4(measure only) → 2 → 3**

Metrics and connection raise credibility with the least code. Measuring
scale (not yet optimising it) must precede any investment in intelligence or
collaboration — there is no point aligning levels or building user accounts
on an engine not proven to handle the scale it will be used at.
