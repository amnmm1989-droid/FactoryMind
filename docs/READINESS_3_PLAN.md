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
   on the executive page, turning what used to be a static win/loss table
   in the README into a metric that shifts with each user's data.

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

## Phase 2 — Intelligence (brings the engine to enterprise level) — 2.a, 2.b done ✅, 2.c partly done (stock file ✅, safety-stock formula still blocked)

### 2.a — Level alignment (Hierarchical Reconciliation) ✅

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

**Delivered.** The category column turned out to already half-exist:
`products_meta.category` has been in the schema since Phase 2 (migration
002), indexed, and never once read or written by any code. `scripts/
generate_demo_data.py` already knows each product's family at generation
time (`f"{family} {variant}"`) — so recording it wasn't a guess, it's the
same fact the product name is built from. It's now written into `data/
data.json`'s new `"categories"` key and migrated into `products_meta` by
`SQLiteRepository.migrate_from_json()`; `SQLiteRepository.get_categories()`
reads it back.

For uploaded files: `services/ingest.py` gained `CATEGORY_HINTS` and an
optional 4th column in the long layout only — a category column is never
required and never guessed structurally into existence for wide files (no
natural place for one). Manual mapping (Phase 1's UI) does not offer a
category dropdown yet — auto-detection only, a scoping choice made
explicitly rather than silently, since Phase 1's screen wasn't reopened for
this.

`services/reconciliation.py::category_totals()` is the whole feature in one
function: it sums `recommended_quantity` per category. There is no
independent category-level forecast to reconcile against — Bottom-Up means
the total *is* the sum, so the acceptance criterion ("always,
arithmetically") holds by construction, not by later verification. A
product with no known category is excluded from every total, never folded
into an invented "other" bucket — same principle as `None ≠ 0` in
`risk_service` throughout this codebase.

Verified on the real demo catalogue (not a fixture): a "By category"
section renders with real numbers computed from real recommendations, and
`tests/test_cold_start_and_reconciliation_ui.py` proves the arithmetic
holds exactly even after a borrowed estimate (2.b) is added to a category
mid-session — the total moves by exactly the borrowed quantity, nothing
approximated.

### 2.b — New-product handling (Cold Start) ✅

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

**Delivered — but the actual mechanism turned out different from the
original diagnosis, and that difference matters.** `MIN_MONTHS` was never
the culprit — it gates the whole *file's* month count, not any single
product's history. The real mechanism: `services/forecast_engine/engine.py`
raises `InsufficientDataError` only when a product's series is entirely
zero (Naive itself needs just one non-zero point, so anything short of
"never sold a single unit" already gets a recommendation today). And
`ui/pages/executive.py:_compute_in_session` was catching that error with
`except AppError: pass` — silent, uncounted, with no trace anywhere.

A harder truth surfaced while building this: **an all-zero series cannot be
told apart from a genuinely dead product using the data alone** — a
brand-new, not-yet-launched item and one that's been discontinued for the
whole window look byte-for-byte identical. The fix does not pretend
otherwise; the "no sales history" section says exactly this ambiguity out
loud rather than labelling everything "new".

The visibility fix needed no change to the engine or to `batch.py` at all:
`ui/pages/executive.py` computes `no_history = set(products) -
{r.product_name for r in stored}` — a plain diff against whichever
products got zero recommendation, working identically whether `stored`
came from the ephemeral session path or `RecommendationRepository.
highest_risk()` (bumped from a hardcoded `limit=500` to `max(500,
len(products))`, since the diff needs the whole catalogue, not just the
top-500 riskiest).

The optional borrow tool is real, not a mock: `services/decision_engine/
recommender.py::borrow_recommendation()` runs the forecast engine on the
*source* product's series and returns a `ProductionRecommendation` for the
*target* name, with `borrowed_from` set and a `ReasonPart("borrowed", …)`
that renders in both languages ("⚠️ Entirely borrowed from…"). The borrowed
row carries a 🔗 prefix wherever its product name appears in any table
afterward — not just in a one-time confirmation toast that scrolls away.

Verified against the real demo catalogue's own dead product
("Coupling Flexible", category "Coupling") live in a running instance — the
section, its explanation, and the borrow tool all rendered exactly as
designed, not just in a fixture. `tests/test_cold_start_and_reconciliation_ui.py`
drives the full path through `AppTest`: upload a file with a zero-sales row,
confirm it's listed and absent from recommendations, select a source
product, click borrow, and confirm it moves into the recommendations table
with `borrowed_from` set — 5 of its 8 assertions checked to fail against the
pre-feature code before being called done.

### 2.c — True probability — stock file done ✅, safety-stock formula still blocked

**The problem**: the confidence margin is fixed (`1.96 × spread`), and
safety stock was uncomputed because stock data was absent entirely
(Roadmap item 3, not started at the time this item was written).

**What's actually blocking 2.c turned out to be two separate things, not
one** — the stock file (data availability) and the safety-stock formula
(a second kind of data this session's stock file still doesn't carry).
The first is done; the second remains genuinely out of reach, for a
reason worth stating precisely rather than re-deferring vaguely.

**Delivered — the stock file (Roadmap item 3)**: a two-column upload
(`product, current stock`), following the exact session-state-only
pattern the sales file already uses (`ui/data_source.py::active_inventory`)
— never written to SQLite, so this doesn't re-scope the privacy promise
the accounts decision (Phase 3, task 1) was held up on. `services/ingest.py`
gained `parse_stock_upload`/`parse_stock_upload_with_mapping`/
`stock_csv_template`, reusing the same hint-guessing and manual
column-mapping machinery Phase 1 built for the sales file — including a
fallback screen when column names aren't recognised.

This was wired through every place that was silently passing `inventory=
None` before: `services/batch.py::run_batch`, `ui/pages/executive.py`'s
ephemeral session path, and `ui/pages/product_intelligence.py`'s risk
computation. `recommend_production()`'s stock deduction
(`_available_stock`, `services/decision_engine/recommender.py`) and
`stock_depletion_risk()` (`services/risk_service/factors.py`) were already
built for this — they'd simply never received real data. The executive
page's recompute-cache signature now folds in the uploaded stock levels
too, for the identical reason it already folds in the sales data itself
(a stock upload after recommendations were computed must trigger a
recompute, not silently sit stale until the button is pressed again).

Verified against the real demo catalogue live: computed the catalogue
("Electric Motor 1.5kW" → 468.33 units), and confirmed via
`tests/test_stock_upload_ui.py::test_a_recomputed_recommendation_nets_off_the_uploaded_stock`
that uploading 5 units of stock and recomputing lands the recommendation
exactly 5 units lower — the same subtraction `recommend_production` has
always done, now actually reachable. All new tests confirmed to fail
against the pre-feature code (missing import at collection time), the
same check that caught the earlier adherence-dashboard false positive.

**Still blocked — the safety-stock formula itself**: the appendix formula
(`SS = z × √(σ²_d × L + μ²_d × σ²_L)`) needs lead-time *and its
variability* (`L`, `σ_L`), not stock level. The two-column stock file
doesn't carry either — and neither does anything else in the codebase
today: `products_meta.lead_time_days` exists as a column but has no
ingest path either, so it sits at its schema default (`0`) for every
product. Setting `safety_stock`/`reorder_point` from a formula that needs
data nobody has entered would be the exact "asked for 0, treated as
default" mistake the rest of this project explicitly refuses to make. So
`InventoryStatus.safety_stock`/`reorder_point` stay `0.0` — an honest
default documented in `ui/pages/production_planning.py`'s module
docstring, not a silent gap. Unblocking this for real needs a lead-time
(and ideally lead-time-variability) input somewhere — outside this
session's scope to invent without a real source for that data.

---

## Phase 3 — Collaboration (from individual tool to team tool) — task 2 done ✅, task 1 awaiting owner decision

**The problem**: no persistent accounts; `source_recommendation_id` (fixed
this session) links the plan to the recommendation but **within one
session**, not across planners.

**Tasks**:

1. [ ] **Accounts via `st.login()`** (OIDC, natively supported in Streamlit
   ≥ 1.32): no UI rebuild. Each planner saves plans under their name, not a
   transient session. **Not started — see the decision note below.**
2. [x] **Adherence dashboard**: `ProductionPlanRepository.adherence()` (added
   this session) actually answers "how many plans are followed?" now — but
   no screen shows it yet. This is the cheapest possible collaboration
   feature: the code is ready, only the display is missing.
3. [ ] **Comments and context on the decision**: a `notes` field exists in
   `production_plans` (`migrations/007`) and is already used — expanding it
   to a multi-comment log (who edited it and when) needs a small extra
   table, not a redesign. **Deliberately not started** — "who" is the whole
   point of a comment log, and there is no "who" without task 1. Building a
   timestamped-but-anonymous log now would be a lesser feature nobody asked
   for, not a step toward the real one.

**Acceptance criterion**: a production and a sales manager see the same plan,
under their names, and a dashboard saying "78% of this month's
recommendations were followed, and the average deviation when overridden was
X units".

**Task 2 delivered.** `ui/pages/production_planning.py` now renders the
adherence numbers `ProductionPlanRepository.adherence()` already computed —
no engine or repository change needed, exactly as sized. The percentage is
computed over `judged = total − unlinked`, not `total`: a plan with no
linked recommendation cannot be judged followed or overridden at all, and
dividing by the full total would understate the real follow rate — the same
`None ≠ 0` discipline `adherence()` itself already applies, now carried
through to the number a planner actually reads. The pure computation
(`_adherence_summary_params`) is separated from the `st.*` calls and unit
tested directly; `tests/test_adherence_dashboard_ui.py` drives the actual
page through `AppTest.from_function` (the page isn't reachable via
`AppTest.switch_page`, which needs a real file path and this app's pages are
dynamically registered closures in `app.py`) — seeding a real forecast and
recommendation first, since a freshly-migrated database has no
`recommendations` row to follow or override at all. All 3 of its tests
checked to fail against the pre-feature code; one assertion had to be
tightened after it passed *even without the feature* — `"0%" in captions`
matched the substring inside an unrelated `"18.0%"` elsewhere on the page,
a reminder that a loose text match can be worse than no test.

**Task 1 — accounts — needs your decision before I touch it, for two
reasons stated plainly:**

1. **I cannot configure the identity provider.** `st.login()` needs a real
   OIDC provider (Google, Microsoft, Okta, or similar) with a client ID and
   secret in `secrets.toml` — that requires you to create the provider-side
   app registration; no code change substitutes for it.
2. **It re-scopes a promise made throughout this project's own
   documentation** — "nothing is saved when hosted", "no accounts, ephemeral
   session" (`ARCHITECTURE.md`, `ROADMAP.md`'s architectural-tension note).
   A persistent account is persistent data, even if the sales file itself
   stays exactly as ephemeral as it is today. That re-scoping should be
   stated and agreed, not slipped in as a side effect of a feature.

Task 3 stays undelivered for the same reason — a comment log's value is
almost entirely in "who said this", which does not exist without task 1.

---

## Phase 4 — Scale and robustness — measurement done ✅

**The problem**: 29 products measured; 30,000 (the reference M5 competition
size) unmeasured. `services/batch.py` is sequential, with a fresh SQLite
connection per save.

**Tasks ordered by cost**:

1. [x] **Measure first, don't optimise blind**: create a synthetic catalogue
   of 1,000 then 10,000 products and run `run_batch` with the light models.
   Record the time before any change — this is the same principle the
   project applies everywhere else: measurement before claiming.
2. [ ] Parallelism at the product level — **not executed, see decision below**.
3. [ ] One SQLite connection per batch, not per row — **not executed, see
   decision below**.
4. [ ] DuckDB — **not executed, see decision below**.

**Acceptance criterion**: a real, published time figure for a 10,000-product
catalogue, not an assumption. If it is acceptable (seconds, not minutes),
**steps 2–4 are never executed** — this is exactly the same lesson as
`core/app_config.py`, deleted this session: a solution to a problem not yet
proven is debt, not an asset.

### Measured (`scripts/benchmark_catalogue_scale.py`, synthetic catalogue, 44 months, light models, ~15% dead products skipped exactly as `run_batch` does in production)

| Products | Engine only (no DB) | Full batch (forecast + persist) | DB share of batch time |
|---|---|---|---|
| 29 (sanity check) | 0.01s | 0.40s | 98% |
| 1,000 | 0.27s | 2.29s | 88% |
| 10,000 | 2.79s | 20.28s | 86% |

**Decision: steps 2–4 are not executed.** 20.28s for 10,000 products is
seconds, not minutes — the acceptance criterion is met as stated. Building
parallelism, a shared connection, or a DuckDB migration now would be solving
a problem the numbers say does not yet exist — the exact debt pattern this
project deleted once already this session.

**What the measurement actually found, and why it's worth keeping written
down even though no action follows:**

- **The engine was never the concern, and the numbers confirm it**: ~0.28ms
  per product, holding constant from 1,000 to 10,000 — perfectly linear, no
  surprise, nothing to fix.
- **The database *is* the dominant cost — 86–98% of batch time — exactly the
  hypothesis in `READINESS_2_GAPS.md` item 7** (a fresh SQLite connection per
  save in `ForecastRepository`/`RecommendationRepository`). The hypothesis
  was correct; it is simply not yet expensive enough in absolute terms to
  justify the fix. A future re-measurement at a catalogue size where it *is*
  expensive should start at step 3 (shared connection) — cheapest, and it
  targets the cost that's actually 86%+ of the total, not the 14% engine
  share step 2's parallelism would attack.
- **Honest extrapolation, not a new measurement**: linear scaling from the
  10,000-product data point puts a 30,490-product catalogue (M5's reference
  size) at roughly 62s of batch time — crossing from "seconds" into "about a
  minute". This is a projection, not evidence, and is recorded here so a
  future re-measurement at that size isn't surprised by a number this data
  already implied. It changes nothing today: the stated acceptance criterion
  was 10,000, and 10,000 measured at 20s.

`scripts/benchmark_catalogue_scale.py` is committed (not run in CI — it's a
measurement tool, like `scripts/generate_demo_data.py`, not a correctness
test) so this number can be reproduced or re-measured as the engine or
repositories change, rather than re-derived from memory.

---

## The suggested order if one number is requested

**0 → 1 → 4(measure only) → 2 → 3**

Metrics and connection raise credibility with the least code. Measuring
scale (not yet optimising it) must precede any investment in intelligence or
collaboration — there is no point aligning levels or building user accounts
on an engine not proven to handle the scale it will be used at.
