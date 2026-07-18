# 🔮 FactoryMind — Analysis & Forecasting for Manufacturing Data

[![CI](https://github.com/amnmm1989-droid/FactoryMind/actions/workflows/ci.yml/badge.svg)](https://github.com/amnmm1989-droid/FactoryMind/actions/workflows/ci.yml)

**A free, open tool that reads your ERP exports and analyses them.**

Your factory runs Odoo, SAP, or something like them. Export a report, upload
it here, and within a second know: **which of your products are forecastable
at all, and how much to produce of each.**

FactoryMind is **an analysis layer on top of your system — not a replacement
for it**. It never writes to your ERP, never stores what your ERP stores, and
never competes with it.

The interface is **bilingual (English / Arabic)** — the switcher sits at the
top of the sidebar, and the language persists in the URL (`?lang=ar`), so it
survives reloads and can be shared as-is.

## Who is it for?

| Manager | Uploads | Learns |
|---|---|---|
| **Production** | Sales report | How much to produce of each product |
| **Procurement** | Sales + stock | When to reorder, and which products can't be planned by forecast |

A deliberate scope decision, not a gap: FactoryMind analyses and forecasts
product demand — it does not track team adherence to plans or analyse
customers as their own dimension. See [`docs/ROADMAP.md`](docs/ROADMAP.md)
for what each upload unlocks, and the competitive readiness plan in
[`docs/READINESS_0_INDEX.md`](docs/READINESS_0_INDEX.md) for what's still
gated behind an owner decision (accounts).

## What it explicitly does NOT do

- **It does not create orders.** It analyses and forecasts; decision and
  execution stay in your system.
- **It does not read from your ERP directly.** You export, it reads the file.
- **It does not monitor machines.** No OEE, no downtime — those need a live
  data stream, not a CSV export.

## What makes it different: honesty

Most forecasting tools promise "95% accuracy". This one tells you when
forecasting will **not** help you.

We run nine models (ETS, SARIMA, Prophet, XGBoost, RandomForest, Croston,
TSB, and two naive baselines) on the bundled demo catalogue and measure the
outcome — reproducible any time with
[`scripts/measure_model_accuracy.py`](scripts/measure_model_accuracy.py),
not a number frozen in prose:

| Model | Wins (of 28 evaluable products) |
|---|---|
| **Last value repeated (Naive)** | **6** (21%) |
| Prophet | 5 (18%) |
| XGBoost | 5 (18%) |
| ETS | 4 (14%) |
| Croston | 4 (14%) |

**No single model dominates this catalogue** — Naive holds a slight
plurality, but Prophet and XGBoost win nearly as often, and ETS has the
*best* average rank overall. The honest finding isn't "simple always wins";
it's that **the winner genuinely depends on the product**, which is the
whole reason this engine tries all nine and measures instead of assuming
one family is always right. On products it does win, the winning model beat
the naive baseline 85% of the time (Forecast Value Added).

And the catalogue classification (using the standard ADI/CV² criteria)
answers the most important question:

> "These products are smooth — plan them by forecast.
> These are intermittent — stop trying to forecast them, hold safety stock.
> These are dead — drop them from planning."

**Excel does not offer this, and software vendors do not say it.**

This is the industry practice known as **Forecast Value Added (FVA)** —
measuring every model against a naive baseline instead of assuming complexity
buys accuracy. FactoryMind practices it by construction.

## ⚠️ Known limits

A tool that tells you when not to trust it should start with itself:

- **Reorder timing isn't real yet.** Stock depletion risk is computed once
  you upload a stock file, but `safety_stock`/`reorder_point` stay at zero —
  they need lead-time *and its variability* (multiple order→delivery date
  pairs per product), which no current upload supplies. A single "typical
  lead time" file is a scoped, not-yet-built next step; true variability
  needs a heavier purchase-order/receipt log most ERPs don't export as one
  flat file.
- **Risk weights are a documented initial estimate, not tuned against your
  own outcomes.** The five factors are weighted from general planning
  practice, not correlated against your specific plant's history — by
  scope decision, not oversight: FactoryMind analyses and forecasts, it
  does not track team decisions to learn from them.
- **Accounts don't exist.** Every session is independent; there's no login.
  This is a deliberate, not-yet-made decision — it needs an external
  identity provider (Google/Microsoft/Okta) and, more importantly, your
  explicit sign-off to re-scope the privacy promise below (an account is
  persistent by definition; your sales file still wouldn't be).
- **Forecasts see quantity history only.** No price, promotions, or
  macroeconomic signal — every model here is univariate by design. That's
  not a gap to be filled; it's what "reads a sales export" structurally
  means.

## 🔒 Your data

The file you upload is **analysed in memory and never written to the
database**. It disappears when the tab closes. Your sales data is a trade
secret, and the tool is built on that assumption.

---

## 🚀 Running it

```bash
# 1. Environment
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.lock.txt      # the exact tested versions

# 2. Run
streamlit run app.py
```

That's it. The app builds its database on first boot (`migrate()` is called
at startup — idempotent and atomic). Useful extras:

```bash
python migrate.py --status    # what's applied, what's pending
pytest                        # the full suite
```

The badge above runs on every push to `main` and every PR
([`.github/workflows/ci.yml`](.github/workflows/ci.yml)). The test count is
deliberately not written here: **a hand-written number goes stale silently** —
it once said "354" while the truth was 369, and an external reviewer copied
the wrong number because he trusted this file. The green badge is measured.

### Two modes

| | **Local** (default) | **Hosted** |
|---|---|---|
| Run | `streamlit run app.py` | `FACTORYMIND_MODE=hosted streamlit run app.py` |
| Results | Saved to `data/app.db` | **Nothing is ever saved** |
| Your uploaded file | Memory only | Memory only |

**Why no persistence when hosted?** One instance serves every visitor and
`app.db` is a shared file — the first visitor who uploads sales would write
them, and the second would read them. A leak by architecture, not by chance.

It works at all because the light models finish a full catalogue in **under
a second**: there is no need to store a result that recomputes faster than
it loads.

### Free hosting

Runs on [Streamlit Community Cloud](https://streamlit.io/cloud): connect the
repository and set `FACTORYMIND_MODE=hosted`. Measured footprint: **297 MB**
of memory — inside the free 1 GB limit.

---

## 📁 Project structure

```
app.py                 Entry point (composition root; boots the DB, routes 5 pages)
config.py              Settings — single source, read at call time not import time
migrate.py             Migration runner — idempotent and atomic, checksum drift detection

core/                  Foundation: logging, exceptions, runtime mode
domain/entities.py     Pure domain objects — the contract between layers
migrations/            NNN_*.sql — sole owner of the database schema
repositories/          Data access (products/sales, forecasts, recommendations, plans)
services/
  ingest.py            Reads and validates the user's file (CSV/Excel)
  forecast_engine/     9 models + demand classification + evidence-based selection
  risk_service/        0–100 risk from five factors (unknown = None, never 0)
  decision_engine/     Forecast → production recommendation
  batch.py             Whole-catalogue computation
models/                Original statistical models (ETS, SARIMA, trend)
ui/
  pages/               The six pages
  data_source.py       Session data: user upload or bundled demo
  i18n.py              Every user-visible string, in both languages
data/                  data.json (synthetic demo) + app.db (generated, untracked)
docs/                  ARCHITECTURE, ROADMAP, READINESS plan, migration guide
tests/                 pytest — run by CI on every push
```

See [`docs/ROADMAP.md`](docs/ROADMAP.md) for the development plan,
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the architecture, and
[`docs/READINESS_0_INDEX.md`](docs/READINESS_0_INDEX.md) for the plan to
compete with the world's best forecasting tools.
