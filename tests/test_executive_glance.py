# tests/test_executive_glance.py
"""
قسم "نظرة سريعة عبر الأقسام الأخرى" في Executive Overview — مدفوعة عبر
AppTest، نفس تقنية tests/test_calibration_ui.py: عزل قاعدة بيانات مؤقتة،
وزرع بيانات مباشرة عبر المستودعات بدل عبور واجهة الرفع.

الصفحة قبل هذا القسم كانت بالكامل عن توصيات الإنتاج رغم اسمها "التنفيذية"
— هذا القسم يسحب سطراً من كل جانب آخر (التزام، عملاء، مشتريات) حين تتوفّر
بياناته في الجلسة، ولا يظهر إطلاقاً حين لا يتوفّر شيء.

ملاحظة فنية: عنوان القسم يُعرض عبر st.caption، لكن أسطره الفعلية عبر
st.write (فقرات markdown) — لذا at.caption يحمل العنوان وحده، وat.markdown
يحمل الأسطر. الخلط بينهما في محاولة أولى أخفى نجاح الميزة عن الاختبار.
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
        from ui.pages.executive import render

        months, products = SQLiteRepository().load_data()
        render(months, products)

    at = AppTest.from_function(script, default_timeout=30)
    at.run()
    assert not at.exception
    return at


def _seed_followed_plan(db_path: str) -> None:
    """خطة واحدة اتُّبعت فيها التوصية بالحرف — التزام 100% من خطة واحدة."""
    from domain.entities import ProductionRecommendation, RiskScore
    from repositories.production_plan_repository import ProductionPlanRepository
    from repositories.recommendation_repository import RecommendationRepository
    from repositories.sqlite_repository import SQLiteRepository

    _, products = SQLiteRepository(db_path=db_path).load_data()
    product = next(iter(products))
    plans = ProductionPlanRepository(db_path=db_path)
    recommendations = RecommendationRepository(db_path=db_path)
    month_id, _ = plans.month_options()[0]

    recommendation_id = recommendations.save(ProductionRecommendation(
        product_name=product, recommended_quantity=100.0, reason="اختبار",
        expected_demand_change_pct=5.0,
        risk=RiskScore(
            product_name=product, score=40, demand_volatility=0.3,
            stock_depletion_risk=None, forecast_accuracy_penalty=0.2,
            seasonality_factor=0.1, growth_rate=0.05,
        ),
    ))
    plans.save(product, month_id, 100.0, source_recommendation_id=recommendation_id)


def test_glance_section_is_absent_when_nothing_is_available(isolated_db):
    """لا خطط محكوم عليها، لا ملف عملاء، لا خطة شراء محسوبة — لا قسم فارغ."""
    at = _run_page()

    captions = " ".join(c.value for c in at.caption)
    assert "Quick glance" not in captions and "نظرة سريعة عبر" not in captions


def test_glance_appears_before_any_production_recommendation_exists(isolated_db):
    """الاستقلالية هي الشرط الحقيقي: القسم يظهر حتى لو "يحتاج قراراً" فارغة
    تماماً (لا توصيات إنتاج محسوبة بعد) — انحدار وجده أول تشغيل: كان
    القسم محشوراً داخل `if stored:` فيختفي كلياً كلما لم تُحسب توصيات."""
    from services.decision_engine.purchase_plan import PurchaseOrderLine, PurchasePlan
    from ui.pages.purchase_plan import RESULT_KEY as PPLAN_RESULT_KEY

    def script() -> None:
        from repositories.sqlite_repository import SQLiteRepository
        from ui.pages.executive import render

        months, products = SQLiteRepository().load_data()
        render(months, products)

    plan = PurchasePlan(horizon_months=3, lines=[
        PurchaseOrderLine(
            product_name="م", horizon_months=3, recommended_quantity=50.0,
            current_stock=None, demand_class="smooth", model_name="ETS",
            wape=10.0, risk_level="medium", confidence_note=None,
            reason="اختبار", urgency="urgent",
        ),
    ])

    at = AppTest.from_function(script, default_timeout=30)
    at.session_state[PPLAN_RESULT_KEY] = plan
    at.run()

    assert not at.exception
    # لا توصيات إنتاج في قاعدة معزولة فارغة تماماً — "يحتاج قراراً" غائبة
    assert not any("Need decision" in h.value for h in at.subheader)
    markdown_text = " ".join(m.value for m in at.markdown)
    assert "1 of 1 products" in markdown_text


def test_glance_shows_adherence_when_a_judged_plan_exists(isolated_db):
    _seed_followed_plan(isolated_db)

    at = _run_page()

    markdown_text = " ".join(m.value for m in at.markdown)
    assert "100% adherence" in markdown_text


def test_glance_shows_bleeding_customers_when_uploaded_this_session(isolated_db):
    from services.ingest import CustomerSalesDataset
    from ui.pages.customer_intelligence import SESSION_KEY as CUSTOMER_SESSION_KEY

    def script() -> None:
        from repositories.sqlite_repository import SQLiteRepository
        from ui.pages.executive import render

        months, products = SQLiteRepository().load_data()
        render(months, products)

    at = AppTest.from_function(script, default_timeout=30)
    at.session_state[CUSTOMER_SESSION_KEY] = CustomerSalesDataset(
        months=["m1", "m2", "m3", "m4"],
        rows={
            "عميل ينزف": {"منتج": [100.0, 100.0, 10.0, 5.0]},
            "عميل ينمو": {"منتج": [10.0, 10.0, 100.0, 100.0]},
        },
    )
    at.run()

    assert not at.exception
    markdown_text = " ".join(m.value for m in at.markdown)
    assert "1 of 2 customers" in markdown_text


def test_glance_shows_urgent_purchase_count_when_computed_this_session(isolated_db):
    from services.decision_engine.purchase_plan import PurchaseOrderLine, PurchasePlan
    from ui.pages.purchase_plan import RESULT_KEY as PPLAN_RESULT_KEY

    def script() -> None:
        from repositories.sqlite_repository import SQLiteRepository
        from ui.pages.executive import render

        months, products = SQLiteRepository().load_data()
        render(months, products)

    plan = PurchasePlan(horizon_months=3, lines=[
        PurchaseOrderLine(
            product_name="م1", horizon_months=3, recommended_quantity=50.0,
            current_stock=None, demand_class="smooth", model_name="ETS",
            wape=10.0, risk_level="medium", confidence_note=None,
            reason="اختبار", urgency="urgent",
        ),
        PurchaseOrderLine(
            product_name="م2", horizon_months=3, recommended_quantity=50.0,
            current_stock=None, demand_class="smooth", model_name="ETS",
            wape=10.0, risk_level="low", confidence_note=None,
            reason="اختبار", urgency="can_wait",
        ),
    ])

    at = AppTest.from_function(script, default_timeout=30)
    at.session_state[PPLAN_RESULT_KEY] = plan
    at.run()

    assert not at.exception
    markdown_text = " ".join(m.value for m in at.markdown)
    assert "1 of 2 products" in markdown_text
