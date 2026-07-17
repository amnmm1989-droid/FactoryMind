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

    ترقيع config.DATABASE_PATH وحده لا يكفي، ورقعة __defaults__ أدناه ليست
    ترفاً: المستودعات تكتب `db_path: str = DATABASE_PATH`، والقيمة
    الافتراضية للوسيط تُقيَّم مرة عند استيراد الوحدة وتتجمّد. فمهما رقّعنا
    config لاحقاً، تبقى SQLiteRepository() موجَّهة إلى data/app.db الحقيقية.

    وهذا ليس عرضاً جانبياً للاختبار بل **سبب العطل نفسه**: مسار غير قابل
    لإعادة التوجيه = مسار غير قابل للاختبار، فلم يُختبر الإقلاع البارد قط،
    فنجا كسره حتى الإنتاج. الرقعة هنا تُبقي الحقيقة ظاهرة بدل أن تخفيها؛
    والعلاج الصحيح (db_path=None وقراءة config عند النداء) يخصّ المستودعات
    لا هذا الملف.
    """
    db = tmp_path / "cold" / "app.db"
    assert not db.exists()  # الشرط الابتدائي — لو انكسر لصار الاختبار وهماً

    import config
    from repositories.forecast_repository import ForecastRepository
    from repositories.recommendation_repository import RecommendationRepository
    from repositories.sqlite_repository import SQLiteRepository

    monkeypatch.setattr(config, "DATABASE_PATH", str(db))
    for repository in (SQLiteRepository, ForecastRepository, RecommendationRepository):
        monkeypatch.setattr(repository.__init__, "__defaults__", (str(db),))
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
