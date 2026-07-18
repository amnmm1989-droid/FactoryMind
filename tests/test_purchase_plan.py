# tests/test_purchase_plan.py
"""
خطة الشراء (services/decision_engine/purchase_plan.py) — ميزة طلبها
مستخدم فعلي: "ملف Excel لأوامر الشراء لكل منتج، لتغطية عدد أشهر أحدده".
"""
from __future__ import annotations

import pytest

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


def _inventory_with_stock(product: str, stock: float):
    from domain.entities import InventoryStatus

    return {
        product: InventoryStatus(
            product_name=product, current_stock=stock, minimum_stock=0.0,
            safety_stock=0.0, reorder_point=0.0, lead_time_days=0,
        )
    }


def test_urgency_is_none_without_lead_time_or_stock():
    """بلا مهلة توريد مُدخَلة أو بلا مخزون معروف — لا حكم أولوية، لا تخمين."""
    series = _smooth_series()

    no_lead_time = build_purchase_plan(
        {"م": series}, horizon_months=3, inventory=_inventory_with_stock("م", 100.0),
    ).lines[0]
    no_stock = build_purchase_plan(
        {"م": series}, horizon_months=3, lead_time_days=30,
    ).lines[0]

    assert no_lead_time.urgency is None
    assert no_stock.urgency is None


def test_urgency_flags_urgent_when_stock_covers_less_than_lead_time():
    """مخزون يكفي أياماً أقل من مهلة التوريد — اطلب الآن."""
    series = _smooth_series(base=300.0)  # طلب شهري مرتفع نسبياً

    plan = build_purchase_plan(
        {"م": series}, horizon_months=3,
        inventory=_inventory_with_stock("م", 10.0),  # مخزون ضئيل جداً
        lead_time_days=60,
    )

    assert plan.lines[0].urgency == "urgent"


def test_urgency_flags_can_wait_when_stock_covers_more_than_lead_time():
    """مخزون يغطي أياماً أكثر من مهلة التوريد بكثير — يمكن الانتظار."""
    series = _smooth_series(base=10.0)  # طلب شهري منخفض

    plan = build_purchase_plan(
        {"م": series}, horizon_months=3,
        inventory=_inventory_with_stock("م", 10000.0),  # مخزون ضخم
        lead_time_days=5,
    )

    assert plan.lines[0].urgency == "can_wait"


def test_unit_price_and_total_cost_computed_when_price_known():
    series = _smooth_series()
    plan = build_purchase_plan(
        {"م": series}, horizon_months=3, prices={"م": 12.5},
    )

    line = plan.lines[0]
    assert line.unit_price == 12.5
    assert line.total_cost == pytest.approx(line.recommended_quantity * 12.5)


def test_unit_price_is_none_when_price_unknown():
    plan = build_purchase_plan({"م": _smooth_series()}, horizon_months=3)

    line = plan.lines[0]
    assert line.unit_price is None
    assert line.total_cost is None


def test_urgency_uses_the_actual_granularity_not_a_hardcoded_month():
    """طلب أسبوعي 100 ومخزون 50 = تغطية 3.5 يوماً فعلياً (50/100 × 7).
    افتراض شهري خاطئ (× 30) كان سيحسبها 15 يوماً — عاجل فعلي يظهر
    "يمكن الانتظار" لو الحبيبة أُهملت."""
    series = _smooth_series(months=24, base=100.0)  # 100 وحدة/فترة تقريباً

    weekly = build_purchase_plan(
        {"م": series}, horizon_months=3,
        inventory=_inventory_with_stock("م", 50.0),
        lead_time_days=5, granularity="weekly",
    ).lines[0]

    assert weekly.urgency == "urgent"
