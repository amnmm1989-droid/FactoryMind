# Database Migrations Guide

## What changed — and what it means in practice

Phase 2 moved schema ownership from Python code to explicit SQL files.

**Before:** `SQLiteRepository.__init__` created tables automatically on
first use.
**After:** `migrations/` owns the schema, and `migrate.py` applies it
explicitly.

---

## 1. A step that became optional

```bash
python migrate.py
```

Safe to repeat — run it ten times, same result.

> **Update:** this step used to be **mandatory before first run**, and no
> longer is. `app.py` calls `migrate()` at boot, so a clean clone works
> with `streamlit run app.py` alone.
>
> The mandate was never a decision — it was a bug: a hosting platform runs
> `streamlit run` and nothing else, so every visitor was told to run a
> terminal command on a server they don't own. And hosting is the
> project's first goal. See `tests/test_cold_boot.py`.
>
> Run it manually when you want the database built before boot
> (deployment, CI, a `--status` check).

**If the app fails to build the database**, you get no cryptic crash but a
`MigrationError` naming the missing tables and the command to run. Today
that message means the automatic build tried and failed — a read-only
disk, checksum drift, or a broken migration — not that you skipped a step.

**An existing database is never touched.** `001_baseline.sql` uses
`CREATE TABLE IF NOT EXISTS` and passes over existing tables without
modifying them; your data stays as it is.

---

## 2. Useful commands

```bash
python migrate.py             # apply everything pending
python migrate.py --status    # show state without changing anything
python migrate.py --db other.db
```

---

## 3. The schema tables

| Table | Maps to | Used by |
|---|---|---|
| `months`, `products`, `sales` | catalogue | everything |
| `products_meta` | — | metadata (category, unit, lead time) |
| `inventory` | `InventoryStatus` | stock file (roadmap item 3) |
| `forecasts` | `ForecastResult` | forecast engine |
| `model_performance` | — | model selection evidence |
| `recommendations` | `ProductionRecommendation` + `RiskScore` | decision engine |
| `production_plans` | — | planner decisions; `source_recommendation_id` links each plan to the recommendation the planner saw |

Tables mirror `domain/entities.py` column-for-column, so objects build
straight from rows with no mapping layer.

---

## 4. Rules for writing a new migration

**Never edit an applied migration.** The runner stores a SHA-256 checksum
of every file and refuses to run if one changed:

```
MigrationError: migration 003_inventory changed after being applied —
the database no longer reflects its content. Create a new migration
instead of editing an applied one.
```

The reason: your database will never re-run an applied migration, so an
edit creates a silent gap between what the files say and what the database
is — a gap that typically surfaces in production, late.

**To change something: create a new file** with the next number:

```
migrations/009_add_supplier_column.sql
```

The pattern is mandatory: `NNN_lowercase_name.sql`. The runner rejects
anything else.

**When adding a new table**, add its name to `REQUIRED_TABLES` in
`migrate.py` so `_verify_schema` covers it.

---

## 5. Tests

`tests/conftest.py` provides three fixtures:

| Fixture | What you get |
|---|---|
| `repo` | A ready repository on a temporary database filled from `data.json` |
| `migrated_db` | Path to a temporary database with all migrations applied |
| `empty_db` | Path to a database with no migrations — for failure cases |

```python
def test_something(repo):
    assert repo.get_products()
```

Tests never touch the real `data/app.db`.

⚠️ **`migrated_db` is session-scoped and derived tables accumulate.**
The catalogue (products/months) is never modified by tests, but
`forecasts` and `recommendations` are written across the session and
nothing cleans them globally. Existing tests survive because they only
assert on what they just wrote. Any test that asserts on a *global* state
(an aggregate, an empty table) must clean up what concerns it first, or
use its own isolated `tmp_path` database (see the `isolated_db` fixture
pattern in `tests/test_stock_upload_ui.py`).

---

## 6. Starting from scratch

```bash
rm data/app.db
streamlit run app.py     # the boot rebuilds and refills it automatically
```

The app repopulates from `data/data.json` on first boot
(`migrate_from_json` behaviour — unchanged).
