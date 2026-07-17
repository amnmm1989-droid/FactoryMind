# tests/test_risk_service.py
"""
اختبارات حساب الخطورة (Phase 4).

المحور: التمييز بين "قِسنا ولا خطورة" (0) و"لا نعرف" (None). خلطهما
يجعل منتجاً مجهول المخزون يتصدّر قائمة الآمنين.
"""
from __future__ import annotations

import math

import pytest

from core.exceptions import InsufficientDataError
from domain.entities import ForecastResult, InventoryStatus, RiskLevel
from services.risk_service import compute_risk, factors
from services.risk_service.scoring import FACTOR_WEIGHTS, _weighted_score

STEADY = [100.0] * 30
VOLATILE = [10.0, 200.0, 5.0, 180.0, 15.0, 190.0] * 5
SEASONAL = [100 + 60 * math.sin(i * math.pi / 6) for i in range(36)]


def _forecast(mape: float | None = 10.0, rmse: float | None = 5.0, values=None) -> ForecastResult:
    return ForecastResult(
        product_name="منتج",
        model_name="Naive",
        forecast_values=values if values is not None else [100.0] * 6,
        lower_bound=[90.0] * 6,
        upper_bound=[110.0] * 6,
        mae=4.0,
        rmse=rmse,
        mape=mape,
    )


def _inventory(current: float, safety: float = 20.0, lead_days: int = 30) -> InventoryStatus:
    return InventoryStatus(
        product_name="منتج",
        current_stock=current,
        minimum_stock=10.0,
        safety_stock=safety,
        reorder_point=50.0,
        lead_time_days=lead_days,
    )


# ---------------------------------------------------------------------------
# تقلب الطلب
# ---------------------------------------------------------------------------
def test_steady_demand_scores_no_volatility():
    assert factors.demand_volatility(STEADY) == 0.0


def test_volatile_demand_scores_higher_than_steady():
    assert factors.demand_volatility(VOLATILE) > factors.demand_volatility(STEADY)


def test_volatility_is_bounded_even_when_extreme():
    """معامل اختلاف 336% موجود فعلاً في هذه البيانات — يجب ألا يكسر المقياس."""
    extreme = [0.0] * 40 + [1000.0, 0.0, 2000.0, 0.0]

    value = factors.demand_volatility(extreme)

    assert 0 <= value <= 100


def test_volatility_needs_at_least_two_points():
    assert factors.demand_volatility([5.0]) is None


def test_volatility_of_a_dead_product_is_zero_not_none():
    """لا مبيعات = لا طلب = لا تقلب فيه. مقيس، لا مجهول."""
    assert factors.demand_volatility([0.0] * 20) == 0.0


# ---------------------------------------------------------------------------
# الموسمية
# ---------------------------------------------------------------------------
def test_seasonality_needs_two_full_cycles():
    """بدورة واحدة لا يُميَّز النمط الموسمي من حدث لمرة واحدة."""
    assert factors.seasonality_factor([100.0] * 23) is None
    assert factors.seasonality_factor([100.0] * 24) is not None


def test_seasonal_series_scores_above_flat_series():
    assert factors.seasonality_factor(SEASONAL) > factors.seasonality_factor([100.0] * 36)


def test_flat_series_has_no_seasonality():
    assert factors.seasonality_factor([100.0] * 36) == 0.0


# ---------------------------------------------------------------------------
# النمو
# ---------------------------------------------------------------------------
def test_growth_risk_ignores_direction():
    """نمو 40% وانكماش 40% خطورة تخطيط متساوية — كلاهما يغيّر الغد."""
    rising = [float(i) for i in range(10, 40)]
    falling = list(reversed(rising))

    assert factors.growth_rate(rising) == pytest.approx(factors.growth_rate(falling), rel=0.01)


def test_flat_series_has_no_growth_risk():
    assert factors.growth_rate(STEADY) == pytest.approx(0.0, abs=0.01)


def test_growth_needs_at_least_three_points():
    assert factors.growth_rate([1.0, 2.0]) is None


def test_growth_rate_uses_the_custom_periods_per_year():
    """الميل لكل فترة × فترات/سنة = التغيّر السنوي — 52 لا 12 لسلسلة أسبوعية.

    نفس الميل بوحدتي حبيبة مختلفتين يُنسَّى بمعامل مختلف تماماً: تجاهل
    ذلك (استخدام 12 دائماً) كان يُصغِّر خطورة النمو الحقيقية لبيانات
    أسبوعية بمعامل 52/12 ≈ 4.3.
    """
    rising = [float(i) for i in range(10, 40)]

    monthly = factors.growth_rate(rising, periods_per_year=12)
    weekly = factors.growth_rate(rising, periods_per_year=52)

    assert weekly > monthly


# ---------------------------------------------------------------------------
# الموسمية بحبيبة غير شهرية
# ---------------------------------------------------------------------------
def test_seasonality_with_a_custom_period_needs_two_cycles_of_that_period():
    """دورة أسبوعية طولها 7 (يوم الأسبوع) لا 12 — دورتان أي 14 نقطة."""
    assert factors.seasonality_factor([100.0] * 13, seasonal_period=7) is None
    assert factors.seasonality_factor([100.0] * 14, seasonal_period=7) is not None


def test_seasonality_detects_a_weekly_pattern_with_period_seven():
    import itertools

    weekday_pattern = [50.0, 60.0, 70.0, 80.0, 90.0, 30.0, 20.0]
    series = list(itertools.islice(itertools.cycle(weekday_pattern), 28))

    assert factors.seasonality_factor(series, seasonal_period=7) > \
        factors.seasonality_factor(series, seasonal_period=12)


# ---------------------------------------------------------------------------
# عقوبة دقة التنبؤ
# ---------------------------------------------------------------------------
def test_accurate_forecast_is_penalised_less():
    accurate = factors.forecast_accuracy_penalty(_forecast(mape=2.0), STEADY)
    sloppy = factors.forecast_accuracy_penalty(_forecast(mape=80.0), STEADY)

    assert accurate < sloppy


def test_penalty_falls_back_to_rmse_when_mape_is_missing():
    """MAPE غائب كثيراً هنا (يحتاج قيماً غير صفرية) — لا نستسلم فوراً."""
    penalty = factors.forecast_accuracy_penalty(_forecast(mape=None, rmse=30.0), STEADY)

    assert penalty is not None
    assert 0 <= penalty <= 100


def test_penalty_is_unknown_when_the_model_was_never_evaluated():
    assert factors.forecast_accuracy_penalty(_forecast(mape=None, rmse=None), STEADY) is None


# ---------------------------------------------------------------------------
# نفاد المخزون — جوهر التمييز بين 0 و None
# ---------------------------------------------------------------------------
def test_unknown_inventory_yields_none_not_zero():
    """الفخ الأساسي: 0 يعني 'مخزونك يغطي الطلب'، None يعني 'لا نعرف كم لديك'.

    إعطاء المجهول صفراً يجعله يبدو الأكثر أماناً في قائمة مرتّبة — وهو
    عكس الحقيقة. كل منتجات المشروع مجهولة المخزون حتى Phase 5.
    """
    assert factors.stock_depletion_risk(None, _forecast()) is None


def test_stock_at_or_below_safety_is_maximum_risk():
    assert factors.stock_depletion_risk(_inventory(current=15.0, safety=20.0), _forecast()) == 100.0


def test_ample_stock_scores_zero_risk():
    """صفر حقيقي: قِسنا، والمخزون يغطي الطلب خلال مهلة التوريد."""
    ample = _inventory(current=10_000.0, safety=20.0, lead_days=30)

    assert factors.stock_depletion_risk(ample, _forecast()) == 0.0


def test_partial_coverage_lands_between_the_extremes():
    # طلب 100/شهر، مهلة 30 يوماً -> يحتاج ~100. لديه 50 -> تغطية 50%
    partial = _inventory(current=50.0, safety=20.0, lead_days=30)

    risk = factors.stock_depletion_risk(partial, _forecast())

    assert 0 < risk < 100


def test_lead_time_conversion_uses_the_real_granularity_not_a_fixed_month():
    """30 يوم مهلة توريد لبيانات أسبوعية = ~4.3 فترة لا فترة واحدة.

    الخطأ الذي كان قائماً: lead_time_days / 30.0 دائماً، فمهلة 30 يوماً
    كانت تُحسب "شهراً واحداً" حتى لو forecast.forecast_values أسابيع —
    وحدتان مختلفتان تُضربان كأنهما واحدة.
    """
    ample = _inventory(current=300.0, safety=20.0, lead_days=30)
    weekly_forecast = _forecast(values=[100.0] * 6)  # 100 وحدة/أسبوع مفترضة

    monthly_risk = factors.stock_depletion_risk(ample, weekly_forecast, granularity="monthly")
    weekly_risk = factors.stock_depletion_risk(ample, weekly_forecast, granularity="weekly")

    # شهرياً: طلب خلال "شهر" واحد (lead_time_periods=1) = 100 -> تغطية 3x -> 0
    assert monthly_risk == 0.0
    # أسبوعياً: نفس 30 يوماً = ~4.3 أسبوع -> طلب ~430 -> تغطية 300/430 < 1 -> خطورة حقيقية
    assert weekly_risk > 0.0


def test_lead_time_conversion_defaults_to_monthly_for_old_callers():
    ample = _inventory(current=10_000.0, safety=20.0, lead_days=30)

    assert factors.stock_depletion_risk(ample, _forecast()) == \
        factors.stock_depletion_risk(ample, _forecast(), granularity="monthly")


def test_more_stock_never_means_more_risk():
    low = factors.stock_depletion_risk(_inventory(current=40.0), _forecast())
    high = factors.stock_depletion_risk(_inventory(current=90.0), _forecast())

    assert high <= low


# ---------------------------------------------------------------------------
# التجميع وإعادة الموازنة
# ---------------------------------------------------------------------------
def test_weights_sum_to_one():
    assert sum(FACTOR_WEIGHTS.values()) == pytest.approx(1.0)


def test_missing_factor_is_excluded_not_zeroed():
    """الاختبار الحاسم: عامل مجهول لا يسحب الدرجة نحو الصفر.

    لو عومل المجهول كصفر، لكانت درجة العاملين أقل من درجة نفس العاملين
    مع عامل ثالث معروف وعالٍ — أي أن الجهل يبدو أماناً.
    """
    all_high = _weighted_score({name: 80.0 for name in FACTOR_WEIGHTS})
    two_high = _weighted_score({"demand_volatility": 80.0, "growth_rate": 80.0})

    assert two_high == pytest.approx(all_high)


def test_renormalisation_keeps_relative_weights():
    known = {"demand_volatility": 100.0, "growth_rate": 0.0}

    score = _weighted_score(known)

    # 0.30 مقابل 0.10 -> النسبة 3:1 محفوظة بعد إعادة الموازنة
    assert score == pytest.approx(100.0 * 0.30 / 0.40)


def test_scoring_refuses_when_nothing_is_known():
    with pytest.raises(InsufficientDataError):
        _weighted_score({})


# ---------------------------------------------------------------------------
# compute_risk
# ---------------------------------------------------------------------------
def test_risk_score_stays_within_bounds():
    risk = compute_risk("منتج", VOLATILE, _forecast(mape=90.0))

    assert 0 <= risk.score <= 100


def test_risk_reports_what_it_could_not_compute():
    """درجة من عاملين ليست كدرجة من خمسة — والقارئ يستحق أن يعرف."""
    risk = compute_risk("منتج", STEADY, _forecast(), inventory=None)

    assert "stock_depletion_risk" in risk.missing_factors
    assert risk.stock_depletion_risk is None
    assert risk.confidence == pytest.approx(0.8)


def test_full_data_gives_full_confidence():
    risk = compute_risk("منتج", SEASONAL, _forecast(), inventory=_inventory(current=50.0))

    assert risk.missing_factors == []
    assert risk.confidence == 1.0
    assert len(risk.known_factors) == 5


def test_volatile_product_scores_riskier_than_steady_one():
    volatile = compute_risk("متذبذب", VOLATILE, _forecast(mape=60.0))
    steady = compute_risk("مستقر", STEADY, _forecast(mape=2.0))

    assert volatile.score > steady.score


def test_level_follows_score():
    risk = compute_risk("منتج", VOLATILE, _forecast(mape=95.0))

    assert risk.level == RiskLevel.from_score(risk.score)


def test_risk_carries_the_product_name():
    risk = compute_risk("منتج س", STEADY, _forecast())

    assert risk.product_name == "منتج س"


def test_short_series_still_scores_on_what_is_known():
    """39% من منتجات المشروع لها 1-5 أشهر — يجب أن تُقيَّم لا أن تُرفض."""
    risk = compute_risk("شحيح", [0.0, 5.0, 0.0, 8.0], _forecast(mape=None, rmse=None))

    assert 0 <= risk.score <= 100
    assert risk.confidence < 1.0


def test_compute_risk_threads_granularity_into_stock_depletion():
    """compute_risk يمرّر granularity إلى stock_depletion_risk فعلاً —
    نفس المخزون والتنبؤ ينتجان خطورة نفاد مختلفة بحبيبتين مختلفتين."""
    inventory = _inventory(current=300.0, safety=20.0, lead_days=30)
    forecast = _forecast(values=[100.0] * 6)

    monthly = compute_risk("منتج", STEADY, forecast, inventory, granularity="monthly")
    weekly = compute_risk("منتج", STEADY, forecast, inventory, granularity="weekly")

    assert monthly.stock_depletion_risk != weekly.stock_depletion_risk
