# tests/test_intermittent.py
"""
اختبارات الطلب المتقطّع: التصنيف، Croston/TSB، ومقياس الاختيار.

المحور: على 84% من هذا الكتالوج، RMSE يكافئ التنبؤ بالصفر. الاختبارات
هنا تحرس التمييز بين "منتج نائم فالصفر صحيح" و"منتج حيّ متقطّع فالصفر
كارثة".
"""
from __future__ import annotations

import math

import numpy as np
import pytest

from core.exceptions import ModelTrainingError
from services.forecast_engine import classify_demand, forecast_product
from services.forecast_engine.engine import _select_best
from services.forecast_engine.evaluation import compute_metrics
from services.forecast_engine.intermittent import (
    CrostonForecaster,
    DemandClass,
    TSBForecaster,
)
from services.forecast_engine.registry import default_models

# طلب كل 3 أشهر بأحجام متماسكة -> متقطّع
INTERMITTENT = [0.0, 0.0, 50.0] * 12
# فجوات + أحجام شديدة التقلب -> متكتّل
LUMPY = ([0.0, 0.0, 5.0, 0.0, 0.0, 400.0] * 6)
# طلب كل شهر بأحجام متماسكة -> منتظم
SMOOTH = [100.0 + (i % 3) for i in range(36)]
# يبيع ثم يموت — مسألة التقادم
DYING = [50.0, 0.0, 45.0, 0.0, 55.0, 0.0] * 3 + [0.0] * 18


# ---------------------------------------------------------------------------
# التصنيف
# ---------------------------------------------------------------------------
def test_regular_demand_is_smooth():
    assert classify_demand(SMOOTH).demand_class == DemandClass.SMOOTH


def test_gapped_consistent_demand_is_intermittent():
    assert classify_demand(INTERMITTENT).demand_class == DemandClass.INTERMITTENT


def test_gapped_erratic_demand_is_lumpy():
    assert classify_demand(LUMPY).demand_class == DemandClass.LUMPY


def test_product_without_sales_is_dead():
    profile = classify_demand([0.0] * 20)

    assert profile.demand_class == DemandClass.DEAD
    assert profile.non_zero_count == 0


def test_adi_measures_the_gap_between_orders():
    """طلب كل 3 أشهر -> ADI = 3."""
    assert classify_demand(INTERMITTENT).adi == pytest.approx(3.0)


def test_cv_squared_ignores_the_zero_months():
    """CV² يقيس تقلب *الأحجام* حين يحدث الطلب.

    حشر الأصفار فيه كان سيقيس التقطّع مرتين بدل قياس التقلب — فتُصنَّف
    كل سلسلة متقطّعة كمتكتّلة.
    """
    steady_sizes = [0.0, 0.0, 50.0] * 12  # أحجام متطابقة تماماً

    assert classify_demand(steady_sizes).cv_squared == pytest.approx(0.0)


def test_only_gapped_classes_are_flagged_intermittent():
    assert classify_demand(INTERMITTENT).is_intermittent
    assert classify_demand(LUMPY).is_intermittent
    assert not classify_demand(SMOOTH).is_intermittent


# ---------------------------------------------------------------------------
# Croston
# ---------------------------------------------------------------------------
def test_croston_predicts_a_rate_not_the_next_month():
    """طلب 50 كل 3 أشهر -> ~16.7/شهر. السؤال 'كم في مارس؟' بلا جواب؛
    السؤال 'كم في الربع؟' له جواب."""
    output = CrostonForecaster(use_sba=False).fit_predict(INTERMITTENT, steps=6)

    assert output.values[0] == pytest.approx(50.0 / 3.0, rel=0.15)


def test_croston_rate_is_constant_across_the_horizon():
    output = CrostonForecaster().fit_predict(INTERMITTENT, steps=6)

    assert len(set(output.values)) == 1


def test_sba_correction_lowers_the_rate():
    """تقدير Croston متحيّز إلى الأعلى — ومبالغة منهجية = مخزون راكد منهجي."""
    plain = CrostonForecaster(use_sba=False).fit_predict(INTERMITTENT, steps=3)
    corrected = CrostonForecaster(use_sba=True).fit_predict(INTERMITTENT, steps=3)

    assert corrected.values[0] < plain.values[0]


def test_croston_never_predicts_negative_demand():
    output = CrostonForecaster().fit_predict(LUMPY, steps=6)

    assert all(v >= 0 for v in output.values)
    assert all(low >= 0 for low in output.lower)


def test_croston_needs_at_least_two_orders():
    """فترة واحدة تحتاج طلبين لتُقاس."""
    with pytest.raises(ModelTrainingError, match="طلبات غير كافية"):
        CrostonForecaster().fit_predict([0.0, 0.0, 40.0, 0.0], steps=3)


def test_croston_rejects_an_invalid_alpha():
    with pytest.raises(ValueError):
        CrostonForecaster(alpha=1.5)


def test_longer_gaps_mean_a_lower_rate():
    frequent = [0.0, 50.0] * 15
    rare = [0.0, 0.0, 0.0, 0.0, 50.0] * 6

    frequent_rate = CrostonForecaster().fit_predict(frequent, steps=1).values[0]
    rare_rate = CrostonForecaster().fit_predict(rare, steps=1).values[0]

    assert rare_rate < frequent_rate


# ---------------------------------------------------------------------------
# TSB — التقادم
# ---------------------------------------------------------------------------
def test_tsb_notices_a_dying_product():
    """الفارق الجوهري عن Croston: الأصفار تُحدّث الاحتمال.

    Croston لا يرى الأصفار إطلاقاً (يحدّث عند الطلب فقط)، فيُبقي تقديره
    عند آخر معدّل عرفه مهما طال الصمت. TSB يُنزله.
    """
    croston_rate = CrostonForecaster().fit_predict(DYING, steps=1).values[0]
    tsb_rate = TSBForecaster().fit_predict(DYING, steps=1).values[0]

    assert tsb_rate < croston_rate


def test_tsb_rate_stays_positive_for_a_live_product():
    output = TSBForecaster().fit_predict(INTERMITTENT, steps=6)

    assert output.values[0] > 0


def test_tsb_rejects_an_invalid_beta():
    with pytest.raises(ValueError):
        TSBForecaster(beta=0.0)


# ---------------------------------------------------------------------------
# المقياس — جوهر المشكلة
# ---------------------------------------------------------------------------
def test_rmse_does_not_reward_predicting_zero():
    """يحرس ضد ادّعاء خاطئ بُني عليه هذا الملف أولاً ثم صُحّح.

    الادّعاء كان: "على سلسلة نصفها أصفار، من يتنبأ بصفر يصيب نصف الأشهر
    مجاناً فيفوز بالـ RMSE". خاطئ: الخطأ التربيعي يُصغَّر بالتنبؤ
    بالمتوسط، لا بالصفر. الصفر يفوز فقط حين يكون المتوسط صفراً — أي حين
    يكون المنتج نائماً فعلاً، وعندها الصفر هو الجواب الصحيح.

    الاختبار باقٍ لأن الحدس المضلّل مقنع، وقد يعود.
    """
    actual = [0.0, 0.0, 40.0, 0.0, 0.0, 35.0]  # المتوسط 12.5
    all_zero = [0.0] * 6
    rate = [12.5] * 6

    zero_metrics = compute_metrics(actual, all_zero, holdout_size=6)
    rate_metrics = compute_metrics(actual, rate, holdout_size=6)

    assert rate_metrics.rmse < zero_metrics.rmse


def test_zero_is_rmse_optimal_only_when_demand_really_is_zero():
    """الوجه الآخر: حين تكون النافذة كلها أصفاراً، الصفر صحيح — لا منحاز."""
    dormant_actual = [0.0] * 6

    zero_metrics = compute_metrics(dormant_actual, [0.0] * 6, holdout_size=6)
    rate_metrics = compute_metrics(dormant_actual, [12.5] * 6, holdout_size=6)

    assert zero_metrics.rmse < rate_metrics.rmse
    assert zero_metrics.rmse == 0.0


def test_cumulative_error_measures_the_horizon_total():
    """المبرر القراري: من ينتج لستة أشهر، فائضه أو عجزه *هو* هذا الرقم."""
    actual = [0.0, 0.0, 40.0, 0.0, 0.0, 35.0]  # مجموع 75
    on_target = [12.5] * 6                      # مجموع 75 -> خطأ 0
    under = [5.0] * 6                           # مجموع 30 -> خطأ 45

    assert compute_metrics(actual, on_target, holdout_size=6).cumulative_error == pytest.approx(0.0)
    assert compute_metrics(actual, under, holdout_size=6).cumulative_error == pytest.approx(45.0)


def test_cumulative_error_is_a_bias_measure_not_an_accuracy_one():
    """قيد صريح: أخطاء متعاكسة تُلغي بعضها.

    لهذا لا يُستخدم للطلب المنتظم. توثيقه هنا يمنع تعميمه بحسن نيّة.
    """
    actual = [50.0, 50.0]
    swinging = [100.0, 0.0]  # يخطئ +50 ثم -50

    metrics = compute_metrics(actual, swinging, holdout_size=2)

    assert metrics.cumulative_error == pytest.approx(0.0)  # يبدو مثالياً
    assert metrics.rmse == pytest.approx(50.0)             # وليس كذلك


def test_cumulative_error_is_zero_for_a_perfect_total():
    metrics = compute_metrics([10.0, 0.0, 20.0], [10.0, 10.0, 10.0], holdout_size=3)

    assert metrics.cumulative_error == pytest.approx(0.0)  # 30 مقابل 30


def test_cumulative_error_is_always_computable():
    """بخلاف MAPE — لا قسمة على صفر هنا."""
    metrics = compute_metrics([0.0] * 5, [0.0] * 5, holdout_size=5)

    assert math.isfinite(metrics.cumulative_error)
    assert metrics.mape is None


# ---------------------------------------------------------------------------
# اختيار المقياس في المحرك
# ---------------------------------------------------------------------------
def test_engine_uses_rmse_for_smooth_demand():
    """RMSE صحيح تماماً للطلب المنتظم — لا نفرض المقياس الجديد على الجميع."""
    result = forecast_product("منتظم", SMOOTH, steps=6, use_cache=False)

    assert result.selection_metric == "rmse"


def test_engine_switches_metric_for_intermittent_demand():
    result = forecast_product("متقطّع", INTERMITTENT, steps=6, use_cache=False)

    assert result.selection_metric == "cumulative_error"


def test_engine_reports_the_demand_profile():
    """التصنيف يُعرَض لا يُفترض — من يقرأ التنبؤ يستحق معرفة أساس اختياره."""
    result = forecast_product("متقطّع", INTERMITTENT, steps=6, use_cache=False)

    assert result.profile is not None
    assert result.profile.demand_class == DemandClass.INTERMITTENT


def test_ranking_follows_the_chosen_metric():
    result = forecast_product("متقطّع", INTERMITTENT, steps=6, use_cache=False)

    ranking = result.ranking()
    errors = [e.metrics.cumulative_error for e in ranking]
    assert errors == sorted(errors)


def test_selection_can_differ_between_the_two_metrics():
    """لو كان المقياسان يختاران دائماً نفس النموذج، لكان التغيير تعقيداً بلا عائد.

    قياس فعلي: يختلفان في 17% من المنتجات المتقطّعة الحيّة.
    """
    result = forecast_product("متقطّع", LUMPY, steps=6, use_cache=False)

    by_rmse = _select_best(result.evaluations, "rmse")
    by_cumulative = _select_best(result.evaluations, "cumulative_error")

    # على الأقل: الاختيار بالتراكمي لا يكون أسوأ تراكمياً من اختيار RMSE
    assert by_cumulative.metrics.cumulative_error <= by_rmse.metrics.cumulative_error


# ---------------------------------------------------------------------------
# السجل والتكامل
# ---------------------------------------------------------------------------
def test_registry_includes_the_intermittent_models():
    names = {m.name for m in default_models()}

    assert {"Croston", "TSB"} <= names


def test_intermittent_models_rank_before_the_seasonal_family():
    """أبسط (معلَمان بلا تدريب تكراري) ويناسبان 84% من الكتالوج —
    فهما المرشّحان حين تنعدم الأدلة."""
    names = [m.name for m in default_models()]

    assert names.index("Croston") < names.index("ETS")
    assert names.index("TSB") < names.index("SARIMA")


def test_intermittent_models_apply_to_sparse_series():
    """السلاسل التي ترفضها العائلة الموسمية — هي بالضبط ما بُنيا له."""
    sparse = [0.0] * 38 + [12.0, 0.0, 0.0, 8.0, 0.0, 5.0]

    assert CrostonForecaster().can_handle(sparse)
    assert TSBForecaster().can_handle(sparse)


def test_a_dormant_product_still_gets_zero():
    """انحدار مهم: لا نُصلح مشكلة بخلق أخرى.

    منتج لم يبع منذ 8 أشهر يجب أن تبقى توصيته صفراً — الصفر هنا صحيح،
    والمبالغة في تصحيح مسألة المتقطّع كانت ستنتج مخزوناً راكداً.
    """
    dormant = [40.0, 0.0, 35.0, 0.0] * 5 + [0.0] * 12

    result = forecast_product("نائم", dormant, steps=6, use_cache=False)

    assert result.best.forecast_values[0] < 5.0
