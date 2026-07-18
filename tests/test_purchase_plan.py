# tests/test_purchase_plan.py
"""
خطة الشراء (services/decision_engine/purchase_plan.py) — ميزة طلبها
مستخدم فعلي: "ملف Excel لأوامر الشراء لكل منتج، لتغطية عدد أشهر أحدده".
"""
from __future__ import annotations

from services.decision_engine.purchase_plan import (
    COLD_START_MAX_NON_ZERO,
    RECENT_DORMANCY_WINDOW,
    build_purchase_plan,
)


def _smooth_series(months: int = 24, base: float = 100.0) -> list[float]:
    return [base + i * 2 for i in range(months)]


def test_builds_a_line_per_evaluable_product_with_the_chosen_horizon():
    products = {"منتج أ": _smooth_series(), "منتج ب": _smooth_series(base=50.0)}

    plan = build_purchase_plan(products, horizon_months=3)

    assert plan.horizon_months == 3
    assert {line.product_name for line in plan.lines} == set(products)
    assert all(line.horizon_months == 3 for line in plan.lines)
    assert not plan.skipped


def test_quantity_is_non_negative_and_reflects_multi_month_demand():
    """أفق 6 أشهر يجب أن يعطي كمية أكبر تقريباً من أفق شهر واحد لنفس المنتج
    المستقر — التوصية تتراكم على الأفق، لا تكرّر شهراً واحداً."""
    series = _smooth_series()

    one_month = build_purchase_plan({"م": series}, horizon_months=1).lines[0]
    six_months = build_purchase_plan({"م": series}, horizon_months=6).lines[0]

    assert one_month.recommended_quantity >= 0
    assert six_months.recommended_quantity >= one_month.recommended_quantity


def test_insufficient_data_is_skipped_not_dropped_silently():
    products = {"سلسلة فارغة": []}

    plan = build_purchase_plan(products, horizon_months=3)

    assert plan.lines == []
    assert len(plan.skipped) == 1
    assert plan.skipped[0][0] == "سلسلة فارغة"


def test_invalid_horizon_raises():
    import pytest

    with pytest.raises(ValueError):
        build_purchase_plan({"م": _smooth_series()}, horizon_months=0)


def test_cold_start_product_is_flagged_not_treated_as_confident():
    """منتج بثلاث نقاط بيانات فعلية أو أقل — الكمية تُحسب، لكن يجب أن
    تحمل تحذيراً صريحاً بدل الظهور بثقة مطابقة لمنتج له تاريخ كامل."""
    series = [0.0] * 40 + [150.0, 140.0, 160.0]
    assert sum(1 for v in series if v != 0) <= COLD_START_MAX_NON_ZERO

    plan = build_purchase_plan({"منتج جديد": series}, horizon_months=3)

    assert plan.lines[0].confidence_note == "cold_start"


def test_recently_dormant_product_is_flagged():
    """منتج نشط تاريخياً لكن بلا بيع منذ نافذة الركود بالكامل — يُعامَل
    'متوقّفاً مؤخراً' لا 'جديداً' (له تاريخ كافٍ يفرّقه عن Cold Start)."""
    series = [100.0] * 12 + [0.0] * RECENT_DORMANCY_WINDOW

    plan = build_purchase_plan({"منتج متوقّف": series}, horizon_months=3)

    assert plan.lines[0].confidence_note == "recently_dormant"
    assert plan.lines[0].recommended_quantity == 0.0


def test_healthy_active_product_has_no_confidence_note():
    plan = build_purchase_plan({"منتج نشط": _smooth_series()}, horizon_months=3)

    assert plan.lines[0].confidence_note is None


def test_current_stock_is_recorded_and_deducted_when_inventory_known():
    from domain.entities import InventoryStatus

    series = _smooth_series()
    inventory = {
        "م": InventoryStatus(
            product_name="م", current_stock=1000.0, minimum_stock=0.0,
            safety_stock=0.0, reorder_point=0.0, lead_time_days=0,
        )
    }

    without_stock = build_purchase_plan({"م": series}, horizon_months=3).lines[0]
    with_stock = build_purchase_plan(
        {"م": series}, horizon_months=3, inventory=inventory
    ).lines[0]

    assert without_stock.current_stock is None
    assert with_stock.current_stock == 1000.0
    assert with_stock.recommended_quantity <= without_stock.recommended_quantity
