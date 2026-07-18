# tests/test_executive_glance.py
"""
إشارة Purchase Plan في Executive Overview — مدفوعة عبر AppTest.

بعد إزالة Production Planning وCustomer Intelligence من نطاق المشروع
(قرار منتج صريح)، Purchase Plan هي الصفحة المتبقية الوحيدة التي يمكن
لـ Executive أن يسحب منها إشارة عابرة للصفحات — إن كانت قد حُسبت فعلاً
هذه الجلسة. لا تُجبَر زيارتها أولاً، ولا يظهر شيء إن لم تُحسَب بعد.
"""
from __future__ import annotations

from streamlit.testing.v1 import AppTest


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


def test_purchase_plan_status_is_absent_when_no_plan_was_computed():
    at = _run_page()

    captions = " ".join(c.value for c in at.caption)
    assert "urgent order" not in captions and "طلباً عاجلاً" not in captions


def test_purchase_plan_status_appears_independent_of_production_recommendations():
    """الاستقلالية هي الشرط الحقيقي: الإشارة تظهر حتى لو لا توصيات إنتاج
    محسوبة بعد على هذه القاعدة (فارغة). كانت نسخة سابقة من هذه الميزة
    محشورة داخل `if stored:` فتختفي كلياً كلما لم تُحسب توصيات."""
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
    captions = " ".join(c.value for c in at.caption)
    assert "1 of 2 products" in captions
