# ARCHITECTURE.md

## Current architecture

```
app.py                       Composition root: boots the DB, routes 5 pages,
                             computes nothing itself
 ├─ core/
 │   ├─ logging_config.py    Central logging (console + rotating file)
 │   ├─ exceptions.py        Unified exception hierarchy
 │   └─ runtime_mode.py      local (persists) | hosted (never persists)
 ├─ domain/
 │   └─ entities.py          ForecastResult, RiskScore,
 │                           ProductionRecommendation, InventoryStatus —
 │                           pure objects, the contract between layers
 ├─ migrations/
 │   └─ NNN_*.sql            Sole owner of the database schema; applied by
 │                           migrate.py (idempotent, atomic, checksum drift
 │                           detection). app.py applies them at boot.
 ├─ repositories/            Data access. Owns ALL SQL — no other layer
 │                           touches sqlite3. Paths resolve at call time
 │                           (resolve_db_path), never freeze at import.
 │   ├─ base.py              DataRepository ABC + resolve_db_path()
 │   ├─ sqlite_repository.py Catalogue (months/products/sales)
 │   ├─ forecast_repository.py       forecasts + model_performance
 │   ├─ recommendation_repository.py recommendations
 │   └─ production_plan_repository.py production_plans + adherence()
 ├─ services/
 │   ├─ ingest.py            Reads user files (CSV/Excel), wide & long
 │   │                       layouts, granularity gate (monthly only).
 │   │                       The single entry point for user data.
 │   ├─ forecast_engine/     9 models + evidence-based selection:
 │   │                       Naive/MovingAverage/Croston/TSB/ETS/SARIMA/
 │   │                       Prophet/XGBoost/RF. The engine knows no model
 │   │                       by name — registry.py only.
 │   │                       intermittent.py classifies each series
 │   │                       (ADI/CV²) and picks the selection metric:
 │   │                       84% of the catalogue is intermittent.
 │   ├─ risk_service/        RiskScore from 5 factors. A factor without
 │   │                       data = None, never 0; it is excluded and the
 │   │                       remaining weights re-normalise.
 │   ├─ decision_engine/     ForecastResult → ProductionRecommendation.
 │   │                       Quantity = expected demand minus available
 │   │                       stock (when a stock file exists).
 │   └─ batch.py             Whole-catalogue computation + persistence
 └─ ui/
     ├─ i18n.py              Translation (Arabic/English). Every user-visible
     │                       string passes through it. Services emit *codes*
     │                       (ReasonPart, Warning_, message_code) — the layer
     │                       that computes never chooses display language.
     ├─ data_source.py       Session data: user upload or bundled demo
     ├─ pages/               executive, forecasting, production_planning,
     │                       product_intelligence, advanced_analytics
     └─ dashboard.py + sidebar/charts/tables/export
                             The original analyst view — render-only since
                             Phase 1; serves correlation/distribution/
                             seasonality analyses the new pages don't have
```

## Layering rules — each learned the hard way

### 1. The layer that computes never chooses display language or wording

Broken in four places, exposed when English was added: `domain/entities`
built the recommendation sentence, `decision_engine` the reason text,
`models/statistics` returned `"📈 rising"` as a value, and `analytics` used
`'Q1'` as a sort key.

All of them emit **codes** now (`ReasonPart`, `message_code`, `q1..q4`),
and `ui/i18n.py` alone knows languages. Any layer writing user-facing text
outside `ui/` reintroduces the bug.

### 2. Repositories own all SQL — UI pages render only

Broken once: `ui/pages/production_planning.py` opened its own sqlite3
connection and hand-wrote `INSERT ... ON CONFLICT` — the only page of five
that did. The cost was concrete: the query omitted
`source_recommendation_id`, silently orphaning every plan from the
recommendation it was based on, and making the question the table was
designed to answer ("how often are recommendations followed?")
unanswerable. A query written by someone thinking about the screen, not
the table, with no contract and no test.

`ProductionPlanRepository` owns the table now;
`test_the_page_holds_no_sql` keeps SQL out of pages permanently.

### 3. Paths resolve at call time, never at import time

`def __init__(self, db_path: str = DATABASE_PATH)` looks harmless, but
Python evaluates the default once at definition and freezes it. However
the configuration is redirected later, every instance still writes to the
real `data/app.db`.

This was the root cause of the cold-boot failure reaching production: an
unredirectable path is an untestable path, so the boot path was never
tested, so its breakage shipped. `repositories.base.resolve_db_path()`
reads `config.DATABASE_PATH` as a module attribute at call time; `None`
means "the current default", not "no path". Structural guards in
`tests/test_cold_boot.py` fail on any non-None default.

### 4. Unknown is None, never zero

`stock_depletion_risk` returns `None` while the inventory table is empty —
because `0` means "measured, safe" and `None` means "we don't know".
Conflating them puts unknown-stock products at the top of the "safest"
list. The same principle appears in `adherence()` (plans without a linked
recommendation are `unlinked`, not "overridden") and in MAPE handling
(None when all actuals are zero, never a fake number).

## Integration principle: no big bang

Each phase lands as a **new** layer beside existing code; old modules are
modified only on real need. The project stays runnable and testable at
every step, instead of becoming a suspended rewrite. (`ui/dashboard.py`
still serves the analyst exactly as before — the five new pages grew
around it, not over it.)

---

## The project's position: an analysis layer, not a system of record

```
   ┌─────────────┐   export    ┌──────────────┐
   │  Odoo/SAP   │  ─────────► │  FactoryMind │
   │ (system of  │  CSV/XLSX   │ (analysis    │
   │  record)    │             │  only)       │
   └─────────────┘             └──────────────┘
         ▲                            │
         └───── the human decides ────┘
```

**One direction.** No writing to the ERP, no API, no order creation. The
reason is not technical: a wrong analysis is a rejected suggestion; a wrong
order is money spent. The tool has not earned that responsibility while —
by its own measurements — 84% of the catalogue resists forecasting.

`recommendations` (system suggestion) is separate from `production_plans`
(human decision) since Phase 2 for exactly this reason — and
`source_recommendation_id` links each decision to the suggestion the
planner saw, so the follow/override rate is measurable
(`ProductionPlanRepository.adherence()`).

## Two runtime modes

| | local (default) | hosted (`FACTORYMIND_MODE=hosted`) |
|---|---|---|
| Batch results | persisted to `data/app.db` | recomputed in session memory |
| Production plans | ✅ | ❌ (needs persistence) |
| User uploads | memory only | memory only |

Hosted persistence is impossible **by architecture**: one instance serves
every visitor and `app.db` is a shared file — saving means visitor A's
data greeting visitor B. See `core/runtime_mode.py` and
`ui/pages/executive.py:_compute_in_session`.
