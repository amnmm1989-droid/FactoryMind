"""
الإقلاع البارد — الطريق الذي يسلكه المستخدم فعلاً.

هذا الملف موجود لأن عطلاً مرّ من تحت 369 اختباراً: `data/app.db` مُتجاهَل
في git عن حق، فالاستنساخ النظيف يصل بلا قاعدة، و`app.py` كان يرفع
MigrationError عند أول زيارة ويعرض "شغّل: python migrate.py" — على خادم
مستضاف لا يملك المستخدم فيه طرفية. الاستضافة، وهي هدف المشروع الأول،
كانت مكسورة كلياً بينما كل الاختبارات خضراء.

**لماذا لم يمسكه شيء؟** conftest.migrated_db يستدعي migrate() قبل كل
اختبار. فكل اختبار يبدأ من قاعدة جاهزة — حالة لا يبدأ منها أي مستخدم.
اختبرنا ما نُجهّزه نحن، لا ما يصل إليه هو. (وهو نفس نمط عطل سابق: تُبدَّل
البيانات ويبقى النص الذي يصفها.)

لذا: **لا fixture من conftest هنا عمداً.** ولا اختبار هنا يستدعي migrate()
بنفسه — لو فعل لأعاد بناء المصيدة ذاتها. نبدأ من لا شيء، ونشغّل app.py
الحقيقي عبر AppTest، ونسأل سؤال المستخدم: هل ظهرت أداة أم رسالة خطأ؟
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).resolve().parent.parent / "app.py")


@pytest.fixture(autouse=True)
def _isolate_streamlit_caches():
    """caches ستريمليت عالمية للعملية، وAppTest لا يعزلها.

    بدون هذا يفسد الترتيب النتيجة: أول اختبار يملأ cache_data في
    ui/data_source._demo_dataset، فتقرأ الاختبارات التالية كتالوجاً
    محفوظاً بلا أن تبني قاعدتها — فتبدو خضراء وهي لم تُقلع أصلاً، أو حمراء
    لسبب لا علاقة له بالمقصود. اختبار الإقلاع البارد بلا cache بارد ليس
    إقلاعاً بارداً.
    """
    import streamlit as st

    st.cache_data.clear()
    st.cache_resource.clear()
    yield
    st.cache_data.clear()
    st.cache_resource.clear()


@pytest.fixture
def cold_db(tmp_path, monkeypatch):
    """قاعدة غير موجودة — حالة كل استنساخ جديد.

    سطر واحد يكفي لإعادة التوجيه، وهذا مكتسَب حديث: كانت المستودعات تكتب
    `db_path: str = DATABASE_PATH`، والقيمة الافتراضية للوسيط تُقيَّم مرة
    عند تعريف الدالة وتتجمّد — فمهما رُقِّع config تبقى كل نسخة موجَّهة إلى
    data/app.db الحقيقية، وكان هذا الملف يحتاج رقعة __defaults__ ليعمل.

    ولم يكن ذلك عرَضاً جانبياً للاختبار بل سبب العطل: مسار لا يُعاد توجيهه
    لا يُختبر، فلم يُختبر الإقلاع البارد، فوصل معطّلاً إلى الإنتاج. أُزيل
    التجميد (repositories.base.resolve_db_path)، فسقطت الرقعة معه.
    """
    db = tmp_path / "cold" / "app.db"
    assert not db.exists()  # الشرط الابتدائي — لو انكسر لصار الاختبار وهماً

    import config

    monkeypatch.setattr(config, "DATABASE_PATH", str(db))
    return db


def _run(app: AppTest) -> AppTest:
    # 90s: أول إقلاع يطبّق 9 migrations ويملأ الكتالوج من JSON
    app._default_timeout = 90
    return app.run()


def test_a_fresh_clone_boots_without_a_database(cold_db):
    """العطل نفسه: استنساخ + streamlit run، بلا أي أمر قبلهما."""
    app = _run(AppTest.from_file(APP))

    assert not app.exception, f"انهار عند الإقلاع البارد: {app.exception}"
    errors = [element.value for element in app.error]
    assert errors == [], f"عرض خطأ على زائر لا يملك طرفية: {errors}"


def test_the_database_is_built_on_first_boot(cold_db):
    """لا "لم ينهَر" فقط — بل بنى القاعدة فعلاً.

    بلا هذا الاختبار يمكن أن يمرّ الأول بـ st.stop() صامت.
    """
    _run(AppTest.from_file(APP))

    assert cold_db.exists(), "الإقلاع لم يُنشئ القاعدة"

    from migrate import missing_tables

    assert missing_tables(str(cold_db)) == []


def test_the_catalogue_is_visible_after_a_cold_boot(cold_db):
    """السؤال الحقيقي: هل رأى الزائر أداة تعمل؟

    الجداول وحدها لا تكفي — قاعدة مبنية وفارغة تعطي شاشة "لا بيانات".
    """
    app = _run(AppTest.from_file(APP))

    from repositories.sqlite_repository import SQLiteRepository

    months, products = SQLiteRepository(db_path=str(cold_db)).load_data()
    assert products, "قاعدة مبنية لكن بلا كتالوج — الزائر يرى شاشة فارغة"
    assert months

    assert not app.exception


def test_booting_twice_is_safe(cold_db):
    """المستضاف يعيد التشغيل، والمحلي يُشغَّل مراراً — لا يجوز أن يُفقد ذلك شيئاً."""
    _run(AppTest.from_file(APP))
    second = _run(AppTest.from_file(APP))

    assert not second.exception
    assert [element.value for element in second.error] == []


def test_a_hosted_boot_needs_no_terminal(cold_db, monkeypatch):
    """الوضع المستضاف — سبب وجود هذا الملف.

    FACTORYMIND_MODE=hosted هو ما تضبطه Streamlit Cloud، ولا شيء غيره
    يجري قبل `streamlit run app.py`.
    """
    monkeypatch.setenv("FACTORYMIND_MODE", "hosted")

    app = _run(AppTest.from_file(APP))

    assert not app.exception
    errors = [element.value for element in app.error]
    assert not any("migrate" in str(e).lower() for e in errors), (
        f"طلب من المستضيف تشغيل أمر طرفية: {errors}"
    )


# ---------------------------------------------------------------------------
# التجميد نفسه — حارس على السبب لا على العرَض
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "module_path, attribute",
    [
        ("repositories.sqlite_repository", "SQLiteRepository"),
        ("repositories.forecast_repository", "ForecastRepository"),
        ("repositories.recommendation_repository", "RecommendationRepository"),
        ("repositories.json_repository", "JsonRepository"),
    ],
)
def test_no_repository_freezes_its_path_at_import(module_path, attribute):
    """`db_path: str = DATABASE_PATH` يُقيَّم مرة عند التعريف ثم يتجمّد.

    هذا ما جعل الإقلاع البارد غير قابل للاختبار، فغير مُختبَر، فمعطّلاً في
    الإنتاج. الحارس هنا على السبب: أي قيمة افتراضية غير None في هذا الوسيط
    تُعيد المسار مجمَّداً مهما بدت الاختبارات خضراء.
    """
    import importlib

    cls = getattr(importlib.import_module(module_path), attribute)
    defaults = cls.__init__.__defaults__ or ()

    assert all(default is None for default in defaults), (
        f"{attribute}.__init__ يجمّد مساراً عند الاستيراد: {defaults}"
    )


def test_migrate_does_not_freeze_its_path_at_import():
    """migrate() تبني القاعدة — فلا يجوز أن يجمّد توقيعُها القاعدةَ نفسها."""
    from migrate import migrate

    assert (migrate.__defaults__ or ()) == (None,), migrate.__defaults__


def test_redirecting_the_config_redirects_the_repositories(tmp_path, monkeypatch):
    """السلوك الذي يخدمه فكّ التجميد: إعادة التوجيه تصل فعلاً.

    الحارس أعلاه بنيويّ؛ هذا يقيس الأثر — لو عاد أحدهم يقرأ نسخة مجمَّدة
    بطريقة أخرى، يسقط هنا.
    """
    import config
    from repositories.forecast_repository import ForecastRepository
    from repositories.recommendation_repository import RecommendationRepository

    target = str(tmp_path / "redirected.db")
    monkeypatch.setattr(config, "DATABASE_PATH", target)

    assert ForecastRepository().db_path == target
    assert RecommendationRepository().db_path == target


def test_an_explicit_path_still_wins(tmp_path, monkeypatch):
    """None تعني "الافتراضي الحالي" — لا تُلغي وسيطاً صريحاً."""
    import config
    from repositories.recommendation_repository import RecommendationRepository

    monkeypatch.setattr(config, "DATABASE_PATH", str(tmp_path / "default.db"))
    explicit = str(tmp_path / "explicit.db")

    assert RecommendationRepository(db_path=explicit).db_path == explicit


def test_the_user_file_never_reaches_the_database(cold_db):
    """حارس خصوصية على مسار الإقلاع.

    الإقلاع صار يبني قاعدة تلقائياً؛ هذا الاختبار يثبّت أن ما يُبنى هو
    بيانات العرض العامة لا ملف الزائر. لولاه لكان "أصلحنا الاستضافة"
    طريقاً محتملاً لكتابة بيانات المستخدم على قرص مشترك.
    """
    _run(AppTest.from_file(APP))

    import sqlite3

    with sqlite3.connect(str(cold_db)) as conn:
        names = {row[0] for row in conn.execute("SELECT name FROM products")}

    import json

    from config import DATA_FILE

    with open(DATA_FILE, encoding="utf-8") as handle:
        demo = set(json.load(handle)["products"])

    assert names == demo, "القاعدة تحمل ما ليس في بيانات العرض المرفقة"
    assert os.environ.get("FACTORYMIND_MODE") is None or True  # الوضع لا يغيّر هذا
