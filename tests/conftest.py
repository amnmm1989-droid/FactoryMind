# tests/conftest.py
"""
تجهيزات pytest المشتركة.

قبل Phase 2 كانت اختبارات SQLite تعمل على قاعدة البيانات الحقيقية
(data/app.db) وتعتمد على أن __init__ ينشئ الجداول تلقائياً. الآن أن
الـ schema صارت مملوكة للـ migrations، صار التجهيز صريحاً — وجاء العزل
عن القاعدة الحقيقية كأثر جانبي مُرحَّب به: الاختبارات لم تعد تكتب في
بيانات المستخدم.
"""
import pytest

from migrate import migrate
from repositories.sqlite_repository import SQLiteRepository


@pytest.fixture(scope="session")
def migrated_db(tmp_path_factory) -> str:
    """قاعدة بيانات مؤقتة طُبِّقت عليها كل الـ migrations.

    session-scoped: بناء الـ schema وتعبئة 185 منتجاً × 44 شهراً من JSON
    عملية غير رخيصة، ولا اختبار هنا يعدّل البيانات — فمشاركتها آمنة.
    """
    db_path = tmp_path_factory.mktemp("db") / "test.db"
    migrate(str(db_path), verbose=False)
    return str(db_path)


@pytest.fixture
def repo(migrated_db: str) -> SQLiteRepository:
    """مستودع SQLite على القاعدة المؤقتة.

    أول بناء يملأ البيانات من data.json عبر migrate_from_json (سلوك
    __init__ القائم)؛ ما يليه يجدها موجودة فلا يعيد التعبئة.
    """
    return SQLiteRepository(db_path=migrated_db)


@pytest.fixture
def empty_db(tmp_path) -> str:
    """مسار قاعدة بيانات لم تُطبَّق عليها أي migration — لاختبار حالات الفشل."""
    return str(tmp_path / "empty.db")
