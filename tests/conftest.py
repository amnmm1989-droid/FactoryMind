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

    session-scoped: بناء الـ schema وتعبئة الكتالوج كاملاً من JSON عملية
    غير رخيصة، والكتالوج نفسه (products/months) لا يعدّله اختبار.

    ⚠️ لكن الجداول المشتقّة تُكتب: forecasts و recommendations و
    production_plans تتراكم عبر الجلسة ولا ينظّفها أحد. تنجو الاختبارات
    القائمة لأنها لا تؤكّد إلا على ما كتبته للتوّ — لا على مجموع ولا على
    جدول فارغ. نجاةٌ بالصدفة لا بالتصميم: أول اختبار يقيس حالة عامة يفشل
    بسبب صفٍّ كتبه اختبار آخر.

    من يحتاج بداية نظيفة يمسح ما يخصّه بنفسه — انظر _clean_slate في
    tests/test_production_plan_repository.py.
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
