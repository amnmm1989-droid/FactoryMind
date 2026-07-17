# tests/test_decision_engine.py
"""
اختبارات محرك القرار (Phase 4).

المحور: التوصية قرار لا وصف — يجب أن تخصم المخزون، وأن تحمل معها ما
يكفي لمراجعتها، وألا تدّعي تغيّراً لا يراه النموذج.
"""
from __future__ import annotations

import math

import pytest

from core.exceptions import DecisionEngineError
from domain.entities import ForecastResult, InventoryStatus, ProductionRecommendation
from services.decision_engine import recommend_production

STEADY = [100.0] * 30
RISING = [float(50 + i * 5) for i in range(30)]
SEASONAL = [100 + 60 * math.sin(i * math.pi / 6) for i in range(36)]


def _forecast(values=None, model="Naive", mape=10.0, rmse=5.0,
              wape=None, fva=None) -> ForecastResult:
    return ForecastResult(
        product_name="منتج",
        model_name=model,
        forecast_values=values if values is not None else [100.0] * 6,
        lower_bound=[90.0] * 6,
        upper_bound=[110.0] * 6,
        mae=4.0,
        rmse=rmse,
        mape=mape,
        wape=wape,
        fva=fva,
    )


def _inventory(current: float, safety: float = 20.0) -> InventoryStatus:
    return InventoryStatus(
        product_name="منتج",
        current_stock=current,
        minimum_stock=10.0,
        safety_stock=safety,
        reorder_point=50.0,
        lead_time_days=30,
    )


# ---------------------------------------------------------------------------
# الكمية
# ---------------------------------------------------------------------------
def test_without_inventory_quantity_equals_forecast_demand():
    rec = recommend_production("منتج", STEADY, _forecast(values=[240.0] * 6))

    assert rec.recommended_quantity == 240.0


def test_available_stock_is_deducted():
    """جوهر الفرق بين تنبؤ وتوصية: الطلب 240، لديك 100 -> أنتج 140."""
    rec = recommend_production(
        "منتج", STEADY, _forecast(values=[240.0] * 6), _inventory(current=120.0, safety=20.0)
    )

    assert rec.recommended_quantity == 140.0  # 240 - (120 - 20)


def test_safety_stock_is_not_treated_as_available():
    """مخزون الأمان موجود للصدمات — توصية تستهلكه تُبطل غرضه."""
    with_safety = recommend_production(
        "منتج", STEADY, _forecast(values=[240.0] * 6), _inventory(current=100.0, safety=40.0)
    )
    without_safety = recommend_production(
        "منتج", STEADY, _forecast(values=[240.0] * 6), _inventory(current=100.0, safety=0.0)
    )

    assert with_safety.recommended_quantity > without_safety.recommended_quantity


def test_surplus_stock_gives_zero_not_negative():
    """كمية إنتاج سالبة ليست توصية."""
    rec = recommend_production(
        "منتج", STEADY, _forecast(values=[50.0] * 6), _inventory(current=5000.0)
    )

    assert rec.recommended_quantity == 0.0


def test_horizon_sums_the_months_requested():
    rec = recommend_production(
        "منتج", STEADY, _forecast(values=[10.0, 20.0, 30.0, 40.0, 50.0, 60.0]), horizon_months=3
    )

    assert rec.recommended_quantity == 60.0  # 10 + 20 + 30


def test_longer_horizon_never_recommends_less():
    one = recommend_production("منتج", STEADY, _forecast(), horizon_months=1)
    three = recommend_production("منتج", STEADY, _forecast(), horizon_months=3)

    assert three.recommended_quantity >= one.recommended_quantity


# ---------------------------------------------------------------------------
# نسبة التغيّر
# ---------------------------------------------------------------------------
def test_rising_demand_shows_positive_change():
    rec = recommend_production("منتج", STEADY, _forecast(values=[150.0] * 6))

    assert rec.expected_demand_change_pct == pytest.approx(50.0)


def test_falling_demand_shows_negative_change():
    rec = recommend_production("منتج", STEADY, _forecast(values=[75.0] * 6))

    assert rec.expected_demand_change_pct == pytest.approx(-25.0)


def test_zero_baseline_does_not_produce_infinity():
    """منتج نائم ثم يُتوقع له طلب: القسمة على صفر تعطي inf.

    'ارتفاع بنسبة inf%' ليست معلومة لمدير إنتاج.
    """
    dormant = [50.0] * 10 + [0.0] * 20

    rec = recommend_production("نائم", dormant, _forecast(values=[80.0] * 6))

    assert math.isfinite(rec.expected_demand_change_pct)


def test_zero_recent_months_fall_back_to_the_overall_mean():
    """آخر 3 أشهر أصفار لا تعني أن المنتج بلا تاريخ — 39% من المنتجات متقطّعة.

    المرجع البديل هو متوسط السلسلة كاملة *بأصفارها*: منتج توقّف ثلاثة أشهر
    متوسطه التاريخي أقل ممّا كان يبيعه وهو نشط، وهذا هو الصدق. استبعاد
    الأصفار كان سيقول "يبيع 100 شهرياً" عن منتج لا يبيع شيئاً منذ ربع سنة.
    """
    intermittent = [100.0] * 20 + [0.0, 0.0, 0.0]
    overall_mean = sum(intermittent) / len(intermittent)  # 86.96 — الأصفار محسوبة

    rec = recommend_production("متقطّع", intermittent, _forecast(values=[100.0] * 6))

    expected = (100.0 - overall_mean) / overall_mean * 100.0
    assert rec.expected_demand_change_pct == pytest.approx(expected)


# ---------------------------------------------------------------------------
# الرسالة — الخطأ الذي كشفه التشغيل على بيانات حقيقية
# ---------------------------------------------------------------------------
def test_flat_demand_is_not_described_as_rising():
    """انحدار: MovingAverage(3) يفوز غالباً، ومرجعنا أيضاً 3 أشهر، فالتغيّر
    صفر بنيوياً. الصياغة القديمة كانت تُخرج 'بسبب ارتفاع الطلب بنسبة 0.0%'."""
    rec = recommend_production("منتج", STEADY, _forecast(values=[100.0] * 6))

    message = rec.as_message()
    assert "ارتفاع" not in message
    assert "انخفاض" not in message
    assert "مستقر" in message


def test_rising_demand_is_described_as_rising():
    rec = recommend_production("منتج", STEADY, _forecast(values=[150.0] * 6))

    assert "ارتفاع" in rec.as_message()


def test_falling_demand_is_described_as_falling():
    rec = recommend_production("منتج", STEADY, _forecast(values=[60.0] * 6))

    assert "انخفاض" in rec.as_message()


def test_message_carries_quantity_and_product():
    rec = recommend_production("منتج س", STEADY, _forecast(values=[1234.0] * 6))

    message = rec.as_message()
    assert "1,234" in message
    assert "منتج س" in message


# ---------------------------------------------------------------------------
# نص السبب — القرار يجب أن يكون قابلاً للمراجعة
# ---------------------------------------------------------------------------
def test_reason_names_the_model_behind_the_number():
    """التوصية لا تكون أدق من تنبؤها — والقارئ يستحق معرفة مصدرها."""
    rec = recommend_production("منتج", STEADY, _forecast(model="MovingAverage"))

    assert "MovingAverage" in rec.reason


def test_reason_reports_historical_error():
    rec = recommend_production("منتج", STEADY, _forecast(mape=37.0))

    assert "37%" in rec.reason


def test_reason_admits_when_the_model_was_never_evaluated():
    rec = recommend_production("منتج", STEADY, _forecast(mape=None, rmse=None))

    assert "لم يُقيَّم" in rec.reason


def test_reason_flags_uncomputed_risk_factors():
    rec = recommend_production("منتج", STEADY, _forecast(), inventory=None)

    assert "عوامل غير محسوبة" in rec.reason


def test_reason_mentions_deducted_stock():
    rec = recommend_production(
        "منتج", STEADY, _forecast(values=[240.0] * 6), _inventory(current=120.0)
    )

    assert "المخزون" in rec.reason


def test_reason_states_the_risk_level():
    rec = recommend_production("منتج", STEADY, _forecast())

    assert "خطورة" in rec.reason


# ---------------------------------------------------------------------------
# الخطورة مرفقة
# ---------------------------------------------------------------------------
def test_recommendation_carries_its_risk():
    rec = recommend_production("منتج", SEASONAL, _forecast())

    assert rec.risk is not None
    assert 0 <= rec.risk.score <= 100


def test_risk_uses_inventory_when_available():
    without = recommend_production("منتج", STEADY, _forecast())
    with_stock = recommend_production("منتج", STEADY, _forecast(), _inventory(current=50.0))

    assert without.risk.stock_depletion_risk is None
    assert with_stock.risk.stock_depletion_risk is not None


# ---------------------------------------------------------------------------
# WAPE وFVA — منقولان من التنبؤ، لا يُحسبان هنا
# ---------------------------------------------------------------------------
def test_forecast_wape_and_fva_are_carried_to_the_recommendation():
    """التوصية لا تحسب WAPE/FVA — تنقلهما كما هما من ForecastResult.

    نفس مبدأ risk: القرار يُبنى على ما يقيسه المحرك، لا على حساب موازٍ
    قد ينحرف عن مصدره.
    """
    rec = recommend_production("منتج", STEADY, _forecast(wape=12.5, fva=3.2))

    assert rec.forecast_wape == 12.5
    assert rec.forecast_fva == 3.2


def test_uncomputed_wape_and_fva_stay_none_not_zero():
    """تنبؤ لم يُقيَّم (وليس تنبؤاً دقيقاً 0%) يجب ألا يوهم التوصية بذلك."""
    rec = recommend_production("منتج", STEADY, _forecast(wape=None, fva=None))

    assert rec.forecast_wape is None
    assert rec.forecast_fva is None


# ---------------------------------------------------------------------------
# الرفض
# ---------------------------------------------------------------------------
def test_empty_forecast_is_rejected():
    with pytest.raises(DecisionEngineError, match="بلا قيم"):
        recommend_production("منتج", STEADY, _forecast(values=[]))


def test_non_positive_horizon_is_rejected():
    with pytest.raises(DecisionEngineError):
        recommend_production("منتج", STEADY, _forecast(), horizon_months=0)


def test_horizon_beyond_the_forecast_is_rejected():
    """طلب 12 شهراً من تنبؤ 6 أشهر: الصمت هنا يعني توصية بنصف الحقيقة."""
    with pytest.raises(DecisionEngineError, match="يتجاوز التنبؤ المتاح"):
        recommend_production("منتج", STEADY, _forecast(values=[100.0] * 6), horizon_months=12)


# ---------------------------------------------------------------------------
# تكامل مع محرك التنبؤ
# ---------------------------------------------------------------------------
def test_engine_output_feeds_the_recommender():
    """العقد بين Phase 3 و Phase 4: ForecastResult يدخل بلا تحويل."""
    from services.forecast_engine import forecast_product
    from services.forecast_engine.naive import NaiveForecaster

    result = forecast_product("منتج", RISING, steps=6, models=[NaiveForecaster()], use_cache=False)

    rec = recommend_production("منتج", RISING, result.best)

    assert isinstance(rec, ProductionRecommendation)
    assert rec.recommended_quantity > 0
    assert "Naive" in rec.reason
