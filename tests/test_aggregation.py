# tests/test_aggregation.py
"""
ADIDA — التجميع الزمني للطلب المتقطّع.

المحور: التجميع يجب أن يكسب إشارة بلا أن يخترع كمية. أخطر ما يمكن أن يكذب
هنا بصمت هو التفكيك: قسمة خاطئة تضاعف أو تنصّف الطلب المتوقَّع كله.
"""
from __future__ import annotations

import numpy as np
import pytest

from core.exceptions import ModelTrainingError
from services.forecast_engine.aggregation import ADIDAForecaster, aggregate_series
from services.forecast_engine.intermittent import classify_demand

# طلب كل 4 فترات بحجم 80 — متقطّع بوضوح، ADI = 4
INTERMITTENT = [0.0, 0.0, 0.0, 80.0] * 20
SMOOTH = [100.0 + i * 2 for i in range(40)]


# ---------------------------------------------------------------------------
# التجميع
# ---------------------------------------------------------------------------
def test_aggregation_sums_each_bucket():
    result = aggregate_series(np.array([1.0, 2.0, 3.0, 4.0, 5.0, 6.0]), 3)

    assert result.tolist() == [6.0, 15.0]


def test_aggregation_is_aligned_to_the_end_not_the_start():
    """البقية تُقتطع من *أقدم* البيانات.

    لو قُصّت من النهاية لصار آخر دلو ناقصاً — مجموعاً أصغر من حقّه — فيهبط
    التنبؤ لسبب حسابي بحت لا لأن الطلب هبط.
    """
    values = np.array([99.0, 1.0, 2.0, 3.0, 4.0])  # 5 قيم، دلو 2 -> تُقتطع 99

    assert aggregate_series(values, 2).tolist() == [3.0, 7.0]


def test_aggregation_keeps_the_total_when_it_divides_evenly():
    values = np.arange(1.0, 13.0)

    assert aggregate_series(values, 4).sum() == pytest.approx(values.sum())


# ---------------------------------------------------------------------------
# النطاق: للمتقطّع وحده
# ---------------------------------------------------------------------------
def test_adida_accepts_intermittent_demand():
    assert classify_demand(INTERMITTENT).is_intermittent
    assert ADIDAForecaster().can_handle(INTERMITTENT)


def test_adida_declines_smooth_demand():
    """على الطلب المنتظم التجميع يطمس تفاصيل ظاهرة أصلاً — ولا يكسب شيئاً."""
    assert not classify_demand(SMOOTH).is_intermittent
    assert not ADIDAForecaster().can_handle(SMOOTH)


def test_adida_declines_a_series_too_short_to_aggregate():
    assert not ADIDAForecaster().can_handle([0.0, 5.0, 0.0, 7.0])


# ---------------------------------------------------------------------------
# حجم الدلو
# ---------------------------------------------------------------------------
def test_bucket_follows_the_demand_interval():
    """ADI = 4 (طلب كل أربع فترات) -> دلو من أربع، فيحوي طلباً واحداً."""
    assert ADIDAForecaster()._bucket_for(np.asarray(INTERMITTENT)) == 4


def test_bucket_never_starves_the_base_model():
    """دلو ضخم يترك سلسلة مجمَّعة أقصر من أن يتدرّب عليها الأساس."""
    sparse_wide_gaps = ([0.0] * 19 + [50.0]) * 3   # ADI = 20، لكن 60 نقطة فقط
    model = ADIDAForecaster()

    bucket = model._bucket_for(np.asarray(sparse_wide_gaps))

    assert bucket <= len(sparse_wide_gaps) // model.base.min_points


def test_an_explicit_bucket_overrides_the_heuristic():
    assert ADIDAForecaster(bucket=3)._bucket_for(np.asarray(INTERMITTENT)) == 3


# ---------------------------------------------------------------------------
# التفكيك — حيث يمكن أن يكذب بصمت
# ---------------------------------------------------------------------------
def test_forecast_has_the_requested_length():
    output = ADIDAForecaster().fit_predict(INTERMITTENT, steps=7)

    assert len(output.values) == 7
    assert len(output.lower) == 7
    assert len(output.upper) == 7


def test_disaggregation_divides_the_bucket_it_does_not_repeat_it():
    """الانحدار الأخطر: لو وُزّعت قيمة الدلو كما هي على كل فترة داخله،
    لتضاعف الطلب المتوقَّع بمقدار حجم الدلو — أربعة أضعاف هنا."""
    output = ADIDAForecaster().fit_predict(INTERMITTENT, steps=8)

    # المعدّل الحقيقي 80/4 = 20 وحدة للفترة (ناقصاً تصحيح SBA)
    assert np.mean(output.values) == pytest.approx(20.0, rel=0.15)


def test_the_forecast_is_finite_and_non_negative():
    output = ADIDAForecaster().fit_predict(INTERMITTENT, steps=6)

    assert all(np.isfinite(v) and v >= 0 for v in output.values)
    assert all(low <= value for low, value in zip(output.lower, output.values))


def test_a_series_that_cannot_be_bucketed_fails_loudly():
    with pytest.raises(ModelTrainingError):
        ADIDAForecaster().fit_predict([0.0, 3.0, 0.0, 4.0], steps=2)


# ---------------------------------------------------------------------------
# التسجيل في المحرك
# ---------------------------------------------------------------------------
def test_adida_is_registered_in_the_full_family():
    from services.forecast_engine.registry import default_models

    assert "ADIDA" in [m.name for m in default_models()]


def test_adida_is_in_the_fast_default_set():
    """الافتراضي هو ما تشغّله المصانع فعلاً — وADIDA رخيص (~0ms) ومصمَّم
    لـ84% من هذا الكتالوج، فمكانه هناك لا خلف خيار متقدّم."""
    from services.batch import fast_models

    assert "ADIDA" in [m.name for m in fast_models()]


def test_adida_ranks_after_the_model_it_wraps():
    """الترتيب من الأبسط إلى الأعقد: ADIDA غلاف فوق Croston، فيليه."""
    from services.forecast_engine.registry import default_models

    names = [m.name for m in default_models()]
    assert names.index("Croston") < names.index("ADIDA")
