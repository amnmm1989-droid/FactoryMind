# tests/test_aggregation.py
"""
ADIDA — التجميع الزمني للطلب المتقطّع.

الحساب في `statsforecast` الآن، فلا تُختبَر هنا خوارزمية التجميع
والتفكيك: تلك مسؤولية المكتبة واختباراتها. ما يُختبَر هو **ما بقي لنا**:
سياسة `can_handle` (متى يُشغَّل أصلاً) وعقد المخرجات الذي يعتمده المحرك.
"""
from __future__ import annotations

import numpy as np
import pytest

from services.forecast_engine.aggregation import ADIDAForecaster
from services.forecast_engine.intermittent import classify_demand

# طلب كل 4 فترات — متقطّع بوضوح
INTERMITTENT = [0.0, 0.0, 0.0, 80.0] * 20
SMOOTH = [100.0 + i * 2 for i in range(40)]


# ---------------------------------------------------------------------------
# السياسة: للمتقطّع وحده — وهي قرارنا لا قرار المكتبة
# ---------------------------------------------------------------------------
def test_adida_accepts_intermittent_demand():
    assert classify_demand(INTERMITTENT).is_intermittent
    assert ADIDAForecaster().can_handle(INTERMITTENT)


def test_adida_declines_smooth_demand():
    """المكتبة تقبل أي سلسلة؛ القيد قرارُ منتجٍ لا خوارزمية.

    على الطلب المنتظم يطمس التجميع تفاصيل ظاهرة أصلاً، فتشغيله هناك إنفاق
    حسابٍ حيث لا يفوز.
    """
    assert not classify_demand(SMOOTH).is_intermittent
    assert not ADIDAForecaster().can_handle(SMOOTH)


def test_adida_declines_a_series_too_short_to_aggregate():
    assert not ADIDAForecaster().can_handle([0.0, 5.0, 0.0, 7.0])


# ---------------------------------------------------------------------------
# عقد المخرجات الذي يعتمده المحرك
# ---------------------------------------------------------------------------
def test_forecast_has_the_requested_length():
    output = ADIDAForecaster().fit_predict(INTERMITTENT, steps=7)

    assert len(output.values) == 7
    assert len(output.lower) == 7
    assert len(output.upper) == 7


def test_the_forecast_is_finite_and_non_negative():
    """كمية منتَجة سالبة أو NaN ليست تنبؤاً متحفظاً — إنها بلا معنى."""
    output = ADIDAForecaster().fit_predict(INTERMITTENT, steps=6)

    assert all(np.isfinite(v) and v >= 0 for v in output.values)
    assert all(low <= value for low, value in zip(output.lower, output.values))


def test_the_rate_reflects_the_underlying_demand():
    """80 وحدة كل 4 فترات ≈ 20 للفترة — حارس ضد خطأ مقياس (×4 أو ÷4)."""
    output = ADIDAForecaster().fit_predict(INTERMITTENT, steps=8)

    assert np.mean(output.values) == pytest.approx(20.0, rel=0.35)


# ---------------------------------------------------------------------------
# التسجيل في المحرك
# ---------------------------------------------------------------------------
def test_adida_is_registered_in_the_full_family():
    from services.forecast_engine.registry import default_models

    assert "ADIDA" in [m.name for m in default_models()]


def test_adida_is_in_the_fast_default_set():
    """الافتراضي هو ما تشغّله المصانع فعلاً — وADIDA رخيص ومصمَّم لـ84%
    من هذا الكتالوج، فمكانه هناك لا خلف خيار متقدّم."""
    from services.batch import fast_models

    assert "ADIDA" in [m.name for m in fast_models()]


def test_adida_ranks_after_the_model_it_builds_on():
    """الترتيب من الأبسط إلى الأعقد: ADIDA يبني فوق منطق Croston، فيليه."""
    from services.forecast_engine.registry import default_models

    names = [m.name for m in default_models()]
    assert names.index("Croston") < names.index("ADIDA")
