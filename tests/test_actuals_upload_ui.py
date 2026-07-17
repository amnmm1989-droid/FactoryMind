# tests/test_actuals_upload_ui.py
"""
رفع ملف الإنتاج الفعلي (Roadmap بند 4) — مدفوعة عبر AppTest.

نفس تقنية tests/test_adherence_dashboard_ui.py بالضبط ولنفس السبب:
production_planning.py صفحة مستقلة لا تعبر st.navigation في app.py
(AppTest.switch_page يحتاج ملف صفحة حقيقياً)، فتُشغَّل عبر
AppTest.from_function مباشرة.

⚠️ عزل القاعدة إلزامي: بلا monkeypatch على config.DATABASE_PATH، الرفع
يكتب في data/app.db الحقيقية.
"""
from __future__ import annotations

import pytest
from streamlit.testing.v1 import AppTest


@pytest.fixture(autouse=True)
def _isolate_streamlit_caches():
    import streamlit as st

    st.cache_data.clear()
    st.cache_resource.clear()
    yield
    st.cache_data.clear()
    st.cache_resource.clear()


@pytest.fixture
def isolated_db(tmp_path, monkeypatch):
    import config
    from migrate import migrate

    db_path = str(tmp_path / "test.db")
    migrate(db_path, verbose=False)
    monkeypatch.setattr(config, "DATABASE_PATH", db_path)
    return db_path


def _run_page() -> AppTest:
    def script() -> None:
        from repositories.sqlite_repository import SQLiteRepository
        from ui.pages.production_planning import render

        months, products = SQLiteRepository().load_data()
        render(months, products)

    at = AppTest.from_function(script, default_timeout=30)
    at.run()
    assert not at.exception
    return at


def _upload_actuals(at: AppTest, content: bytes, name: str = "actuals.csv") -> AppTest:
    uploader = next(f for f in at.file_uploader if f.key == "_actuals_uploader")
    uploader.set_value([(name, content, "text/csv")])
    at.run()
    assert not at.exception
    return at


def test_uploading_actuals_for_a_saved_plan_fills_the_gap(isolated_db):
    """المسار الجوهري: خطة محفوظة + ملف إنتاج فعلي لنفس المنتج/الشهر ->
    actual_quantity يُملأ، والصفحة تقول ذلك — لا صمتاً."""
    from repositories.production_plan_repository import ProductionPlanRepository
    from repositories.sqlite_repository import SQLiteRepository

    _, products = SQLiteRepository(db_path=isolated_db).load_data()
    product = next(iter(products))

    plans = ProductionPlanRepository(db_path=isolated_db)
    month_id, month_label = plans.month_options()[0]
    plans.save(product, month_id, 100.0)

    csv = f"Product,Month,Quantity\n{product},{month_label},95\n".encode("utf-8")

    at = _run_page()
    at = _upload_actuals(at, csv)

    successes = " ".join(s.value for s in at.success)
    assert "1" in successes

    stored = plans.all_plans()[0]
    assert stored["actual_quantity"] == 95.0


def test_a_plan_less_month_is_reported_as_no_plan_not_invented(isolated_db):
    """إنتاج فعلي لمنتج/شهر بلا خطة محفوظة — يُبلَّغ صراحةً، لا يُنشئ خطة."""
    from repositories.production_plan_repository import ProductionPlanRepository
    from repositories.sqlite_repository import SQLiteRepository

    _, products = SQLiteRepository(db_path=isolated_db).load_data()
    product = next(iter(products))
    plans = ProductionPlanRepository(db_path=isolated_db)
    _, month_label = plans.month_options()[0]

    csv = f"Product,Month,Quantity\n{product},{month_label},40\n".encode("utf-8")

    at = _run_page()
    at = _upload_actuals(at, csv)

    expander_labels = [e.label for e in at.expander]
    assert any("no saved plan" in label for label in expander_labels)
    assert plans.all_plans() == []
