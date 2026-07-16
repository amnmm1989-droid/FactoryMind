#!/usr/bin/env python3
# migrate.py
"""
مشغّل الـ migrations — المالك الوحيد لبنية قاعدة البيانات.

قبل Phase 2 كانت الجداول تُنشأ تلقائياً داخل SQLiteRepository.__init__،
ما جعل بنية القاعدة أثراً جانبياً لإنشاء كائن. الآن الـ schema تُبنى
هنا فقط، صراحةً، عبر ملفات SQL مرقّمة في migrations/.

الاستخدام:
    python migrate.py              # تطبيق كل ما هو معلّق
    python migrate.py --status     # عرض الحالة دون تغيير شيء
    python migrate.py --db path/to/other.db

خصائص مضمونة:
  - Idempotent: التشغيل مرة أو عشراً يعطي نفس النتيجة.
  - ذرّي: كل migration داخل معاملة — ينجح كاملاً أو لا يُطبَّق أصلاً.
  - قابل للاستيراد: conftest.py يستدعي migrate() على قاعدة مؤقتة.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import re
import sqlite3
import sys
from typing import List, Tuple

from config import BASE_DIR, DATABASE_PATH
from core.exceptions import MigrationError

MIGRATIONS_DIR = os.path.join(BASE_DIR, "migrations")

# 001_baseline.sql -> ("001", "baseline")
_MIGRATION_PATTERN = re.compile(r"^(\d{3})_([a-z0-9_]+)\.sql$")

# الجداول التي يجب أن توجد بعد تطبيق كل الـ migrations.
# يستخدمها SQLiteRepository للتحقق قبل العمل، بدل أن يفترض وجودها.
REQUIRED_TABLES = (
    "months",
    "products",
    "sales",
    "products_meta",
    "inventory",
    "forecasts",
    "model_performance",
    "recommendations",
    "production_plans",
)


def get_connection(db_path: str) -> sqlite3.Connection:
    """اتصال في وضع autocommit — المعاملات تُدار يدوياً هنا بـ BEGIN/COMMIT.

    isolation_level=None مقصود: الوضع الافتراضي لـ sqlite3 يبدأ معاملات
    ضمنية تتعارض مع إدارتنا الصريحة للمعاملات حول كل migration.
    """
    conn = sqlite3.connect(db_path, isolation_level=None)
    conn.row_factory = sqlite3.Row
    # خارج أي معاملة — PRAGMA foreign_keys يُتجاهَل بصمت داخل المعاملات
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _ensure_tracking_table(conn: sqlite3.Connection) -> None:
    """جدول تتبّع الـ migrations المطبَّقة. أول ما يُنشأ، وبنفسه idempotent."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version    TEXT PRIMARY KEY,
            name       TEXT NOT NULL,
            checksum   TEXT NOT NULL,
            applied_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """
    )


def discover_migrations() -> List[Tuple[str, str, str]]:
    """قراءة ملفات migrations/ مرتبة حسب الرقم -> [(version, name, path)]"""
    if not os.path.isdir(MIGRATIONS_DIR):
        raise MigrationError(
            f"مجلد الـ migrations غير موجود: {MIGRATIONS_DIR}",
            context={"dir": MIGRATIONS_DIR},
        )

    found = []
    for filename in sorted(os.listdir(MIGRATIONS_DIR)):
        if not filename.endswith(".sql"):
            continue
        match = _MIGRATION_PATTERN.match(filename)
        if not match:
            raise MigrationError(
                f"اسم migration مخالف للنمط المتوقع NNN_name.sql: {filename}",
                context={"filename": filename},
            )
        version, name = match.group(1), match.group(2)
        found.append((version, name, os.path.join(MIGRATIONS_DIR, filename)))

    versions = [v for v, _, _ in found]
    duplicates = {v for v in versions if versions.count(v) > 1}
    if duplicates:
        raise MigrationError(
            f"أرقام migration مكرّرة: {sorted(duplicates)}",
            context={"duplicates": sorted(duplicates)},
        )
    return found


def _checksum(path: str) -> str:
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def _split_statements(sql: str) -> List[str]:
    """تقسيم ملف SQL إلى تعليمات منفصلة.

    لا نستخدم executescript لأنه يُنهي أي معاملة معلّقة ضمنياً قبل
    التنفيذ — ما كان سيُفقد الذرّية التي نبنيها هنا. sqlite3.complete_statement
    يتولى التقسيم بشكل صحيح (يفهم الفواصل المنقوطة داخل النصوص).
    """
    statements: List[str] = []
    buffer = ""
    for line in sql.splitlines(keepends=True):
        buffer += line
        if sqlite3.complete_statement(buffer):
            statements.append(buffer.strip())
            buffer = ""
    # ما تبقّى بلا فاصلة منقوطة: تعليقات ختامية = مقبول، SQL ناقص = خطأ
    leftover = _strip_sql_comments(buffer).strip()
    if leftover:
        raise MigrationError(
            "تعليمة SQL غير مكتملة في نهاية الملف (فاصلة منقوطة ناقصة؟)",
            context={"leftover": leftover[:120]},
        )
    return statements


def _strip_sql_comments(sql: str) -> str:
    return "\n".join(line.split("--", 1)[0] for line in sql.splitlines())


def applied_versions(conn: sqlite3.Connection) -> dict:
    """{version: checksum} لما هو مطبَّق فعلاً على هذه القاعدة."""
    _ensure_tracking_table(conn)
    rows = conn.execute("SELECT version, checksum FROM schema_migrations").fetchall()
    return {row["version"]: row["checksum"] for row in rows}


def _verify_no_drift(version: str, name: str, path: str, recorded: str) -> None:
    """كشف تعديل ملف migration بعد تطبيقه.

    قاعدة بياناتك لن تعكس التعديل (فالـ migration لن يُعاد تشغيله)، فتنشأ
    فجوة صامتة بين ما في الملفات وما في القاعدة. الصمت هنا أسوأ من الخطأ.
    """
    current = _checksum(path)
    if current != recorded:
        raise MigrationError(
            f"الـ migration رقم {version}_{name} تغيّر بعد تطبيقه — "
            f"قاعدة البيانات لا تعكس محتواه الحالي. "
            f"أنشئ migration جديداً بدل تعديل المطبَّق.",
            context={"version": version, "expected": recorded[:12], "found": current[:12]},
        )


def apply_migration(conn: sqlite3.Connection, version: str, name: str, path: str) -> None:
    """تطبيق migration واحد ذرّياً: كل تعليماته + تسجيله، أو لا شيء."""
    with open(path, "r", encoding="utf-8") as f:
        sql = f.read()

    statements = _split_statements(sql)
    checksum = _checksum(path)

    conn.execute("BEGIN")
    try:
        for statement in statements:
            conn.execute(statement)
        conn.execute(
            "INSERT INTO schema_migrations (version, name, checksum) VALUES (?, ?, ?)",
            (version, name, checksum),
        )
        conn.execute("COMMIT")
    except Exception as exc:
        conn.execute("ROLLBACK")
        raise MigrationError(
            f"فشل تطبيق الـ migration {version}_{name}: {exc}",
            cause=exc,
            context={"version": version, "path": path},
        ) from exc


def migrate(db_path: str = DATABASE_PATH, *, verbose: bool = True) -> List[str]:
    """تطبيق كل الـ migrations المعلّقة. يُرجع قائمة ما طُبِّق في هذا التشغيل.

    idempotent: استدعاؤه على قاعدة محدَّثة بالكامل يُرجع [] ولا يغيّر شيئاً.
    """
    os.makedirs(os.path.dirname(os.path.abspath(db_path)) or ".", exist_ok=True)

    migrations = discover_migrations()
    conn = get_connection(db_path)
    try:
        already = applied_versions(conn)
        newly_applied: List[str] = []

        for version, name, path in migrations:
            if version in already:
                _verify_no_drift(version, name, path, already[version])
                continue
            apply_migration(conn, version, name, path)
            newly_applied.append(f"{version}_{name}")
            if verbose:
                print(f"  ✓ {version}_{name}")

        return newly_applied
    finally:
        conn.close()


def missing_tables(db_path: str) -> List[str]:
    """الجداول المطلوبة غير الموجودة. [] تعني القاعدة جاهزة."""
    if not os.path.exists(db_path):
        return list(REQUIRED_TABLES)
    conn = get_connection(db_path)
    try:
        rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        existing = {row["name"] for row in rows}
        return [t for t in REQUIRED_TABLES if t not in existing]
    finally:
        conn.close()


def print_status(db_path: str) -> None:
    migrations = discover_migrations()
    conn = get_connection(db_path)
    try:
        already = applied_versions(conn)
    finally:
        conn.close()

    print(f"قاعدة البيانات: {db_path}")
    print(f"الـ migrations: {len(migrations)} ملف | مطبَّق: {len(already)}\n")
    for version, name, _ in migrations:
        mark = "✓ مطبَّق" if version in already else "· معلّق"
        print(f"  {mark:12} {version}_{name}")

    pending = [v for v, _, _ in migrations if v not in already]
    print()
    if pending:
        print(f"معلّق: {len(pending)} — شغّل: python migrate.py")
    else:
        print("القاعدة محدَّثة بالكامل.")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="تطبيق migrations قاعدة البيانات (آمن للتشغيل المتكرر)"
    )
    parser.add_argument("--db", default=DATABASE_PATH, help="مسار قاعدة البيانات")
    parser.add_argument("--status", action="store_true", help="عرض الحالة دون تطبيق")
    args = parser.parse_args()

    try:
        if args.status:
            print_status(args.db)
            return 0

        print(f"قاعدة البيانات: {args.db}")
        applied = migrate(args.db)
        if applied:
            print(f"\nتم تطبيق {len(applied)} migration.")
        else:
            print("لا شيء معلّق — القاعدة محدَّثة بالكامل.")
        return 0
    except MigrationError as exc:
        print(f"\n✗ خطأ: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
