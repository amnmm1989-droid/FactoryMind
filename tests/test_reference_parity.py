# tests/test_reference_parity.py
"""
أمانة الجسر إلى `statsforecast` — لا نُشوّه ما تُرجعه المكتبة.

## كيف انقلب هذا الملف

كان يقارن تنفيذنا اليدوي لـ Croston/TSB/ADIDA بالمكتبة، ويوثّق أين
يختلفان. ثم حُذف التنفيذ اليدوي كلّه: الحساب صار في `statsforecast`،
فسؤال «هل نطابق المرجع؟» فقد معناه — **نحن نستدعيه**.

السؤال الباقي أدقّ وأخطر: **هل يمرّ الرقم كما هو؟** بين استدعاء المكتبة
وعرض الرقم على مصنع تقع طبقة `reference.point_forecast` وطبقة المحوّلات:
تحويل نوع، قصّ للسالب، حراسة NaN. أيٌّ منها قد يزيح الرقم بصمت. هذه
الاختبارات تقارن مخرَجنا بمخرَج المكتبة مباشرةً، بلا تسامح.

`statsforecast` اعتمادية إنتاج الآن (لا اختيارية)، فلا تخطّي هنا.
"""
from __future__ import annotations

import numpy as np
import pytest
from statsforecast.models import ADIDA, CrostonClassic, CrostonSBA, Naive
from statsforecast.models import TSB as ReferenceTSB
from statsforecast.models import WindowAverage

from services.forecast_engine.aggregation import ADIDAForecaster
from services.forecast_engine.intermittent import CrostonForecaster, TSBForecaster
from services.forecast_engine.naive import MovingAverageForecaster, NaiveForecaster

# سلاسل بأنماط فجوات مختلفة عمداً: منتظمة، عشوائية، وتبدأ بطلب
SERIES = [
    [0, 0, 10, 0, 0, 0, 14, 0, 8, 0, 0, 12, 0, 0, 0, 9, 0, 0, 11, 0,
     0, 7, 0, 0, 13, 0, 0, 0, 10, 0],
    [5, 0, 0, 8, 0, 12, 0, 0, 0, 3, 0, 0, 7, 0, 0, 0, 9, 0, 4, 0],
    [0, 0, 0, 0, 20, 0, 0, 0, 0, 25, 0, 0, 0, 0, 18, 0, 0, 0, 0, 22],
]
IDS = ["gappy", "starts-with-demand", "regular"]
HORIZON = 3


def _reference(model, series: list[float]) -> np.ndarray:
    return np.asarray(
        model.forecast(y=np.asarray(series, dtype=np.float32), h=HORIZON)["mean"],
        dtype=float,
    )


@pytest.mark.parametrize("series", SERIES, ids=IDS)
@pytest.mark.parametrize("ours,theirs", [
    (CrostonForecaster(use_sba=True), CrostonSBA()),
    (CrostonForecaster(use_sba=False), CrostonClassic()),
    (TSBForecaster(alpha_d=0.1, alpha_p=0.05), ReferenceTSB(alpha_d=0.1, alpha_p=0.05)),
    (NaiveForecaster(), Naive()),
], ids=["croston-sba", "croston-classic", "tsb", "naive"])
def test_our_output_is_the_reference_output_unchanged(ours, theirs, series):
    """بلا تسامح: أي إزاحة هنا تعني أن طبقتنا تعبث بالرقم."""
    assert ours.fit_predict(series, HORIZON).values == pytest.approx(
        _reference(theirs, series), abs=1e-9
    )


@pytest.mark.parametrize("series", SERIES, ids=IDS)
def test_adida_output_is_the_reference_output_unchanged(series):
    assert ADIDAForecaster().fit_predict(series, HORIZON).values == pytest.approx(
        _reference(ADIDA(), series), abs=1e-9
    )


def test_moving_average_passes_its_window_through():
    series = [0.0, 0.0, 3.0, 6.0, 9.0]

    ours = MovingAverageForecaster(window=3).fit_predict(series, HORIZON).values

    assert ours == pytest.approx(_reference(WindowAverage(window_size=3), series), abs=1e-9)


def test_a_window_longer_than_the_series_is_clamped_not_crashed():
    """39% من هذا الكتالوج أقصر من النافذة الافتراضية؛ المكتبة تفشل عليها
    والقصّ عندنا يُبقي النموذج منطبقاً."""
    short = [4.0, 8.0]

    output = MovingAverageForecaster(window=3).fit_predict(short, HORIZON)

    assert output.values == pytest.approx(
        _reference(WindowAverage(window_size=2), short), abs=1e-9
    )


# ---------------------------------------------------------------------------
# ما تضيفه طبقتنا عمداً — ولا تملكه المكتبة
# ---------------------------------------------------------------------------
def test_negative_forecasts_are_clipped_to_zero():
    """كمية منتَجة سالبة بلا معنى. المكتبة قد تُرجعها على حوافّ السلاسل."""
    from services.forecast_engine.reference import point_forecast

    class _Negative:
        def forecast(self, y, h):
            return {"mean": np.full(h, -5.0)}

    assert list(point_forecast(_Negative(), [1.0, 2.0], 2, name="x")) == [0.0, 0.0]


def test_non_finite_output_fails_loudly_instead_of_reaching_a_factory():
    from core.exceptions import ModelTrainingError
    from services.forecast_engine.reference import point_forecast

    class _NaN:
        def forecast(self, y, h):
            return {"mean": np.full(h, np.nan)}

    with pytest.raises(ModelTrainingError, match="غير منتهية"):
        point_forecast(_NaN(), [1.0, 2.0], 2, name="x")


def test_a_library_failure_becomes_the_projects_own_error():
    """المحرك يميّز فشل التدريب عن نتيجة سيئة — فيجب ألا يتسرّب
    استثناء المكتبة الخام إليه."""
    from core.exceptions import ModelTrainingError
    from services.forecast_engine.reference import point_forecast

    class _Broken:
        def forecast(self, y, h):
            raise RuntimeError("انهيار داخلي")

    with pytest.raises(ModelTrainingError, match="فشل تدريب"):
        point_forecast(_Broken(), [1.0, 2.0], 2, name="x")
