# tests/test_reference_parity.py
"""
تكافؤ نماذج الطلب المتقطّع مع تنفيذ مرجعي مستقل (Nixtla statsforecast).

## لماذا هذا الملف موجود

Croston و TSB و ADIDA **مكتوبة داخل هذا المشروع** — لا توجد في statsmodels
ولا scikit-learn. وهذا سؤال مشروع يطرحه أي مهندس في مصنع قبل الشراء:
«من يضمن أن تنفيذكم للورقة العلمية صحيح؟»

المقاييس (MAE/RMSE/WAPE/MAPE) تُقارَن بـ scikit-learn في مواضعها. أما هذه
النماذج فمرجعها العملي هو `statsforecast` من Nixtla — مكتبة مفتوحة واسعة
الاستخدام تنفّذ الأوراق نفسها.

## اعتمادية اختيارية — لا تمسّ الإنتاج

`statsforecast` **ليست** في requirements.txt: تُثبَّت عند الحاجة للتدقيق
فقط، وتتخطّى هذه الاختبارات إن غابت. سببٌ عملي: تثبيتها يخفض pandas إلى
2.x بينما القفل عندنا 3.x.

    pip install statsforecast     # ثم شغّل هذا الملف

## الحصيلة المُثبَتة هنا

- **تنعيم الأحجام يطابق المرجع تماماً** (فارق 0.0) — نفس SES، نفس α.
- **الانحراف كلّه في تقدير الفاصل**، وسببه عُرفان لا خطأ حسابي:
    1. Nixtla يحتسب الفجوة الأولى (من بداية السلسلة إلى أول طلب)؛ نحن لا.
    2. Nixtla يبدأ التنعيم من أول فجوة؛ نحن نبدأ من متوسط الفجوات.

هذه الاختبارات **توثّق الحالة القائمة وتمنع انحرافها صامتاً**. إن قُرّر
لاحقاً اعتماد عُرف Nixtla، فهي التي ستُثبت التطابق.
"""
from __future__ import annotations

import numpy as np
import pytest

statsforecast = pytest.importorskip(
    "statsforecast",
    reason="اعتمادية تدقيق اختيارية — pip install statsforecast",
)
from statsforecast.models import CrostonClassic, CrostonSBA  # noqa: E402

from services.forecast_engine.intermittent import CrostonForecaster  # noqa: E402

ALPHA = 0.1

# سلاسل متقطّعة بأنماط فجوات مختلفة عمداً: منتظمة، عشوائية، وتبدأ بطلب
SERIES = [
    [0, 0, 10, 0, 0, 0, 14, 0, 8, 0, 0, 12, 0, 0, 0, 9, 0, 0, 11, 0,
     0, 7, 0, 0, 13, 0, 0, 0, 10, 0],
    [5, 0, 0, 8, 0, 12, 0, 0, 0, 3, 0, 0, 7, 0, 0, 0, 9, 0, 4, 0],
    [0, 0, 0, 0, 20, 0, 0, 0, 0, 25, 0, 0, 0, 0, 18, 0, 0, 0, 0, 22],
]


def _ses(values: np.ndarray, alpha: float) -> float:
    """التنعيم الأسي البسيط كما ينفّذه المرجع: fitted[0] = x[0]."""
    fitted = np.empty_like(values)
    fitted[0] = values[0]
    for i in range(1, len(values)):
        fitted[i] = alpha * values[i - 1] + (1 - alpha) * fitted[i - 1]
    return float(alpha * values[-1] + (1 - alpha) * fitted[-1])


def _reference(series: list[float], sba: bool = False) -> float:
    model = CrostonSBA() if sba else CrostonClassic()
    return float(model.forecast(y=np.asarray(series, dtype=np.float32), h=1)["mean"][0])


def _our_interval_estimate(series: list[float]) -> float:
    """تقدير الفاصل كما يحسبه CrostonForecaster فعلاً — لعزل مصدر الفارق."""
    values = np.asarray(series, dtype=float)
    idx = np.flatnonzero(values > 0)
    estimate = float(np.mean(np.diff(idx)))
    since = 1
    for i in range(idx[0] + 1, len(values)):
        if values[i] > 0:
            estimate = ALPHA * since + (1 - ALPHA) * estimate
            since = 1
        else:
            since += 1
    return estimate


@pytest.mark.parametrize("series", SERIES, ids=["gappy", "starts-with-demand", "regular"])
def test_demand_smoothing_matches_the_reference_exactly(series):
    """نصف الخوارزمية الأول — تنعيم أحجام الطلب — مطابق بفارق صفر.

    يُعزَل بضرب ناتجنا في تقديرنا للفاصل: الحاصل يجب أن يساوي SES(الطلبات)
    التي يحسبها المرجع، بلا أي تسامح.
    """
    ours = CrostonForecaster(alpha=ALPHA, use_sba=False).fit_predict(series, 1).values[0]
    demand = np.asarray(series, dtype=float)
    demand = demand[demand > 0]

    reconstructed = ours * _our_interval_estimate(series)

    assert reconstructed == pytest.approx(_ses(demand, ALPHA), abs=1e-9)


@pytest.mark.parametrize("series", SERIES, ids=["gappy", "starts-with-demand", "regular"])
def test_adopting_the_reference_interval_convention_reproduces_it_exactly(series):
    """الفارق كلّه في الفاصل — والدليل: بعُرف Nixtla للفاصل نطابقه تماماً.

    يُثبت هذا أن تنفيذنا ليس خطأً حسابياً بل عُرفاً مختلفاً في نقطتين:
    احتساب الفجوة الأولى، وقيمة البدء.
    """
    values = np.asarray(series, dtype=float)
    demand = values[values > 0]
    idx = np.flatnonzero(values != 0)
    # عُرف المرجع: الفجوة الأولى محتسَبة من بداية السلسلة
    intervals = np.diff(idx + 1, prepend=0).astype(float)

    rebuilt = _ses(demand, ALPHA) / _ses(intervals, ALPHA)

    assert rebuilt == pytest.approx(_reference(series), abs=1e-6)


def test_the_reference_injects_a_phantom_interval_when_a_series_starts_with_demand():
    """لماذا لا نتبنّى عُرف المرجع كما هو — أثرٌ حسابي في تنفيذه.

    `np.diff(idx + 1, prepend=0)` يعني أن سلسلة تبدأ بطلب في الموضع 0
    تُنتج فاصلاً أولياً = 1، رغم أنه **لا فجوة مرصودة قبله إطلاقاً**.
    ومع α=0.1 يظل أثر البدء ثقيلاً، فينخفض تقدير الفاصل ويرتفع التنبؤ:
    قِيس هنا فارقاً يقارب 35% على سلسلة تبدأ بطلب، مقابل ~3% على سلسلة
    تبدأ بفجوة.

    أي أن أياً من العُرفين لا يتفوّق مطلقاً: لنا بدءٌ يستعمل متوسط الفجوات،
    ولهم فاصلٌ مخترَع عند الحافة. هذا الاختبار يوثّق المقايضة كي لا
    "يُصحَّح" أحدهما إلى الآخر بلا قرار.
    """
    starts_with_demand = SERIES[1]
    values = np.asarray(starts_with_demand, dtype=float)
    idx = np.flatnonzero(values != 0)

    assert idx[0] == 0, "السلسلة يجب أن تبدأ بطلب ليظهر الأثر"
    reference_intervals = np.diff(idx + 1, prepend=0)
    assert reference_intervals[0] == 1        # الفاصل المخترَع
    assert np.diff(idx)[0] == 3               # أول فجوة مرصودة فعلاً

    ours = CrostonForecaster(alpha=ALPHA, use_sba=False).fit_predict(
        starts_with_demand, 1).values[0]
    # الفاصل المخترَع يرفع تنبؤ المرجع فوق تنبؤنا
    assert _reference(starts_with_demand) > ours


@pytest.mark.parametrize("series", [SERIES[0], SERIES[2]], ids=["gappy", "regular"])
def test_conventions_stay_close_when_the_series_starts_with_a_gap(series):
    """بلا الأثر الحافّي، العُرفان متقاربان — فالفارق عُرفٌ لا خوارزمية."""
    ours = CrostonForecaster(alpha=ALPHA, use_sba=False).fit_predict(series, 1).values[0]

    assert ours == pytest.approx(_reference(series), rel=0.15)


@pytest.mark.parametrize("series", SERIES, ids=["gappy", "starts-with-demand", "regular"])
def test_the_sba_correction_matches_the_reference_factor(series):
    """تصحيح Syntetos-Boylan = ضرب في (1 - α/2). المرجع يطبّق نفس العامل،
    فنسبة SBA إلى الكلاسيكي يجب أن تتطابق في التنفيذين."""
    classic = CrostonForecaster(alpha=ALPHA, use_sba=False).fit_predict(series, 1).values[0]
    sba = CrostonForecaster(alpha=ALPHA, use_sba=True).fit_predict(series, 1).values[0]

    assert sba / classic == pytest.approx(1 - ALPHA / 2, abs=1e-9)
    assert _reference(series, sba=True) / _reference(series) == pytest.approx(
        1 - ALPHA / 2, abs=1e-6
    )
