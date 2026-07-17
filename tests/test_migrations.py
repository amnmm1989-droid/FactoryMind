# tests/test_migrations.py
"""
اختبارات نظام الـ migrations (Phase 2).

التركيز على الضمانات التي تُبنى عليها بقية المراحل:
idempotency، الذرّية، كشف الانحراف، والتوافق مع قواعد بيانات أنشأها
الكود القديم قبل وجود الـ migrations.
"""
import sqlite3

import pytest

import migrate as migrate_module
from core.exceptions import MigrationError
from migrate import (
    REQUIRED_TABLES,
    applied_versions,
    discover_migrations,
    get_connection,
    migrate,
    missing_tables,
)
from repositories.sqlite_repository import SQLiteRepository


def _tables(db_path: str) -> set:
    conn = get_connection(db_path)
    try:
        rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        return {row["name"] for row in rows}
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# الاكتشاف
# ---------------------------------------------------------------------------
def test_discovers_migrations_in_numeric_order():
    found = discover_migrations()

    versions = [version for version, _, _ in found]

    assert versions == sorted(versions)
    assert versions[0] == "001"


def test_every_migration_has_unique_version():
    versions = [version for version, _, _ in discover_migrations()]

    assert len(versions) == len(set(versions))


# ---------------------------------------------------------------------------
# التطبيق
# ---------------------------------------------------------------------------
def test_migrate_creates_all_required_tables(empty_db):
    migrate(empty_db, verbose=False)

    tables = _tables(empty_db)

    for table in REQUIRED_TABLES:
        assert table in tables, f"الجدول {table} لم يُنشأ"


def test_migrate_records_applied_versions(empty_db):
    migrate(empty_db, verbose=False)

    conn = get_connection(empty_db)
    try:
        recorded = applied_versions(conn)
    finally:
        conn.close()

    expected = {version for version, _, _ in discover_migrations()}
    assert set(recorded) == expected


def test_migrate_returns_what_it_applied(empty_db):
    applied = migrate(empty_db, verbose=False)

    assert len(applied) == len(discover_migrations())


# ---------------------------------------------------------------------------
# Idempotency — المتطلب الصريح في خارطة الطريق
# ---------------------------------------------------------------------------
def test_second_run_applies_nothing(empty_db):
    migrate(empty_db, verbose=False)

    second = migrate(empty_db, verbose=False)

    assert second == []


def test_repeated_runs_leave_schema_identical(empty_db):
    migrate(empty_db, verbose=False)
    before = _tables(empty_db)

    migrate(empty_db, verbose=False)
    migrate(empty_db, verbose=False)

    assert _tables(empty_db) == before


def test_repeated_runs_do_not_duplicate_tracking_rows(empty_db):
    migrate(empty_db, verbose=False)
    migrate(empty_db, verbose=False)

    conn = get_connection(empty_db)
    try:
        count = conn.execute("SELECT COUNT(*) AS c FROM schema_migrations").fetchone()["c"]
    finally:
        conn.close()

    assert count == len(discover_migrations())


def test_migrate_preserves_existing_data(empty_db):
    """التشغيل المتكرر يجب ألا يمسّ البيانات — وإلا فالـ migration مدمّر."""
    migrate(empty_db, verbose=False)
    conn = get_connection(empty_db)
    try:
        conn.execute("INSERT INTO products (name) VALUES ('منتج تجريبي')")
    finally:
        conn.close()

    migrate(empty_db, verbose=False)

    conn = get_connection(empty_db)
    try:
        rows = conn.execute("SELECT name FROM products").fetchall()
    finally:
        conn.close()
    assert [row["name"] for row in rows] == ["منتج تجريبي"]


# ---------------------------------------------------------------------------
# التوافق مع القواعد القديمة (التي أنشأها _init_db قبل Phase 2)
# ---------------------------------------------------------------------------
def test_migrates_legacy_database_without_data_loss(tmp_path):
    """قاعدة أنشأها الكود القديم يجب أن تُرقّى دون فقدان صف واحد.

    هذا سيناريو المستخدم الحقيقي: data/app.db موجودة لديه أصلاً وفيها
    بيانات فعلية. لو أسقط الـ baseline الجداول أو فشل عليها، لضاعت.
    """
    db_path = str(tmp_path / "legacy.db")
    # محاكاة ما كان _init_db ينشئه بالضبط، مع صف بيانات
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        CREATE TABLE months (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            sort_order INTEGER NOT NULL
        );
        CREATE TABLE products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE
        );
        CREATE TABLE sales (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER NOT NULL,
            month_id INTEGER NOT NULL,
            quantity REAL NOT NULL,
            FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE,
            FOREIGN KEY (month_id) REFERENCES months(id) ON DELETE CASCADE,
            UNIQUE(product_id, month_id)
        );
        INSERT INTO months (name, sort_order) VALUES ('يناير 2024', 0);
        INSERT INTO products (name) VALUES ('منتج قديم');
        INSERT INTO sales (product_id, month_id, quantity) VALUES (1, 1, 42.0);
        """
    )
    conn.commit()
    conn.close()

    migrate(db_path, verbose=False)

    conn = get_connection(db_path)
    try:
        quantity = conn.execute("SELECT quantity FROM sales").fetchone()["quantity"]
        product = conn.execute("SELECT name FROM products").fetchone()["name"]
    finally:
        conn.close()

    assert quantity == 42.0
    assert product == "منتج قديم"
    assert not missing_tables(db_path)


# ---------------------------------------------------------------------------
# كشف الانحراف
# ---------------------------------------------------------------------------
def test_editing_an_applied_migration_is_rejected(empty_db, monkeypatch):
    migrate(empty_db, verbose=False)

    # محاكاة تعديل الملف بعد تطبيقه عبر تغيير بصمته
    real_checksum = migrate_module._checksum

    def fake_checksum(path):
        if path.endswith("001_baseline.sql"):
            return "0" * 64
        return real_checksum(path)

    monkeypatch.setattr(migrate_module, "_checksum", fake_checksum)

    with pytest.raises(MigrationError, match="تغيّر بعد تطبيقه"):
        migrate(empty_db, verbose=False)


# ---------------------------------------------------------------------------
# التحقق من الـ schema في المستودع
# ---------------------------------------------------------------------------
def test_missing_tables_lists_everything_on_empty_db(empty_db):
    assert set(missing_tables(empty_db)) == set(REQUIRED_TABLES)


def test_missing_tables_empty_after_migrate(empty_db):
    migrate(empty_db, verbose=False)

    assert missing_tables(empty_db) == []


def test_repository_refuses_unmigrated_database(empty_db):
    """الفشل يجب أن يكون صريحاً ومع تعليمات — لا 'no such table' غامضاً."""
    with pytest.raises(MigrationError, match="migrate.py"):
        SQLiteRepository(db_path=empty_db)


# ---------------------------------------------------------------------------
# القيود الفعلية على الجداول الجديدة
# ---------------------------------------------------------------------------
def test_foreign_keys_are_enforced(empty_db):
    migrate(empty_db, verbose=False)
    conn = get_connection(empty_db)
    try:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO inventory (product_id, current_stock) VALUES (999, 10)"
            )
    finally:
        conn.close()


def test_negative_stock_is_rejected(empty_db):
    migrate(empty_db, verbose=False)
    conn = get_connection(empty_db)
    try:
        conn.execute("INSERT INTO products (name) VALUES ('منتج')")
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO inventory (product_id, current_stock) VALUES (1, -5)"
            )
    finally:
        conn.close()


def test_invalid_production_plan_status_is_rejected(empty_db):
    migrate(empty_db, verbose=False)
    conn = get_connection(empty_db)
    try:
        conn.execute("INSERT INTO products (name) VALUES ('منتج')")
        conn.execute("INSERT INTO months (name, sort_order) VALUES ('يناير 2024', 0)")
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO production_plans (product_id, month_id, planned_quantity, status) "
                "VALUES (1, 1, 100, 'حالة_غير_موجودة')"
            )
    finally:
        conn.close()


def test_malformed_forecast_json_is_rejected(empty_db):
    migrate(empty_db, verbose=False)
    conn = get_connection(empty_db)
    try:
        conn.execute("INSERT INTO products (name) VALUES ('منتج')")
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO forecasts (product_id, model_name, horizon, "
                "forecast_values, lower_bound, upper_bound) "
                "VALUES (1, 'ETS', 3, 'هذا ليس JSON', '[1]', '[2]')"
            )
    finally:
        conn.close()


def test_risk_score_outside_range_is_rejected(empty_db):
    migrate(empty_db, verbose=False)
    conn = get_connection(empty_db)
    try:
        conn.execute("INSERT INTO products (name) VALUES ('منتج')")
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO recommendations (product_id, recommended_quantity, reason, "
                "expected_demand_change_pct, risk_score) VALUES (1, 50, 'سبب', 10, 150)"
            )
    finally:
        conn.close()
