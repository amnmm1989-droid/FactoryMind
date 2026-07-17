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
| **Sales** | Sales by customer | Which customers grow, which bleed |
| **Plant** | Manufacturing orders | Whether execution matches the plan |

Today **the production manager is fully served**; the rest need file formats
not yet supported — see [`docs/ROADMAP.md`](docs/ROADMAP.md) and the
competitive readiness plan in [`docs/READINESS_0_INDEX.md`](docs/READINESS_0_INDEX.md).

## What it explicitly does NOT do

- **It does not create orders.** It analyses and forecasts; decision and
  execution stay in your system.
- **It does not read from your ERP directly.** You export, it reads the file.
- **It does not monitor machines.** No OEE, no downtime — those need a live
  data stream, not a CSV export.

## What makes it different: honesty

Most forecasting tools promise "95% accuracy". This one tells you when
forecasting will **not** help you.

On this project's own validation catalogue, we ran nine models (ETS, SARIMA,
Prophet, XGBoost, RandomForest, Croston, TSB, and two naive baselines) across
43 data-rich series and measured the outcome:

| Model | Wins |
|---|---|
| Simple moving average | 10 |
| **Last value repeated (Naive)** | **16** |
| Prophet | **0** |
| ETS | 1 |

**Naive models win in 60% of cases.** That is not an implementation flaw —
44 monthly points simply do not carry enough signal for complex models. The
tool measures this and tells you, instead of selling an illusion.

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

- **Monthly data only.** A weekly or daily file is **explicitly rejected**
  with an explanation — never silently accepted and misread. Aggregate to
  months in your ERP, then export. (Weekly/daily support is the first item
  on the roadmap.)
- **Columns are guessed by name.** Odoo exports (`product_id`), SAP exports
  (`Material`), and common manufacturing names (`Part Number`) are read, in
  Arabic and English. The **wide** layout (name column + month columns)
  passes regardless of what its first column is called. But a **long** layout
  with a column name outside the known list is not understood — and the error
  message blames the months, not the column. **No hints are added by
  guesswork** — send a real export and its name gets added. A visual
  column-mapping screen remains the general fix (roadmap).
- **The stock-depletion factor is not computed** — there is no stock file
  yet. Every assessment therefore shows 80% confidence (4 factors of 5), and
  the tool says so on every screen.
- **Risk weights are an initial calibration** with no validation data. They
  get tuned once actual production is uploaded and compared with plans.

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
| Production planning | ✅ Available | ❌ Needs persistent storage |
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
  pages/               The five pages
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
