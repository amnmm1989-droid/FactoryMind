# tests/test_metric_parity.py
"""
تطابق المقاييس مع مراجعها — بلا تسامح، كما النماذج في test_reference_parity.

## لماذا وُجد هذا الملف

سؤال «هل المقاييس مستوردة من المكاتب الأصلية؟» كشف فجوة توثيق: قيل سابقاً
إنها «مُتحقَّقة مقابل scikit-learn» ولم يكن في المستودع اختبار واحد يسند
الادّعاء. القياس أثبت التطابق (فرق صفري حرفياً) — وهذه الاختبارات تحوّل
القياس اللحظي إلى حارس دائم.

## سياسة «استورد ولا تَبنِ» — وأين حدّها هنا

النماذج استُوردت لأنها *خوارزميات* يطول تنفيذها ويسهل انحرافها. المقاييس
معادلات من سطر واحد فوق numpy؛ استيراد دالة sklearn مكانها لا يشتري
صحّةً إضافية — التطابق الصفري أدناه هو الضمانة نفسها بلا وسيط. ما يُمنع
هو الانحراف الصامت، وهذه الاختبارات تمنعه.

## الاستثناء الموثَّق: MAPE يختلف عن sklearn **عمداً**

sklearn يقسم على |actual| لكل النقاط (بحماية eps تُنتج أرقاماً فلكية على
الأصفار). سياستنا: القسمة على القيم غير الصفرية فقط، وNone حين لا توجد —
لأن 84% من هذا الكتالوج متقطّع، وMAPE فلكي على منتجٍ نصفُ شهوره أصفار
رقمٌ كاذب لا متحفّظ. الاختباران الأخيران يحرسان الاتفاق حيث يجب الاتفاق
والاختلاف حيث قُرِّر الاختلاف.
"""
from __future__ import annotations

import numpy as np
import pytest
import sklearn.metrics as sk

from services.forecast_engine.evaluation import compute_metrics
from services.validation import _mase

RNG = np.random.default_rng(7)
SMOOTH = (RNG.uniform(50, 150, 12), RNG.uniform(50, 150, 12))
INTERMITTENT = (
    np.array([0, 0, 30, 0, 0, 45, 0, 12, 0, 0, 60, 0], dtype=float),
    RNG.uniform(0, 40, 12),
)
ALL_ZERO = (np.zeros(6), RNG.uniform(0, 10, 6))

CASES = [SMOOTH, INTERMITTENT, ALL_ZERO]
IDS = ["smooth", "intermittent", "all-zero"]


def _ours(actual, predicted):
    return compute_metrics(actual.tolist(), predicted.tolist(), holdout_size=len(actual))


@pytest.mark.parametrize("actual,predicted", CASES, ids=IDS)
def test_mae_matches_sklearn_exactly(actual, predicted):
    assert _ours(actual, predicted).mae == pytest.approx(
        sk.mean_absolute_error(actual, predicted), abs=0
    )


@pytest.mark.parametrize("actual,predicted", CASES, ids=IDS)
def test_rmse_matches_sklearn_exactly(actual, predicted):
    assert _ours(actual, predicted).rmse == pytest.approx(
        sk.root_mean_squared_error(actual, predicted), abs=0
    )


@pytest.mark.parametrize("actual,predicted", CASES[:2], ids=IDS[:2])
def test_wape_matches_its_definition_through_sklearn(actual, predicted):
    """لا WAPE في sklearn — لكن wape = MAE·n / Σ|actual| هويةً، فيُشتق
    المرجع من MAE المستورد. انحرافنا عن التعريف ينكشف هنا."""
    reference = (
        sk.mean_absolute_error(actual, predicted) * len(actual)
        / np.abs(actual).sum() * 100
    )

    assert _ours(actual, predicted).wape == pytest.approx(reference, abs=1e-9)


def test_mase_matches_nixtlas_utilsforecast_exactly():
    """المرجع من نفس بيت statsforecast — اعتمادية موجودة أصلاً لا جديدة."""
    import pandas as pd
    from utilsforecast.losses import mase as reference_mase

    actual = np.array([12.0, 15.0, 9.0, 20.0, 14.0, 11.0, 18.0, 16.0])
    train = np.array([10.0, 13.0, 8.0, 15.0, 12.0, 9.0, 14.0, 11.0, 16.0, 12.0])
    predicted = np.array([13.0, 14.0, 10.0, 18.0, 15.0, 12.0, 17.0, 15.0])
    scale = float(np.mean(np.abs(np.diff(train))))

    frame = pd.DataFrame(
        {"unique_id": ["a"] * len(actual), "y": actual, "model": predicted}
    )
    train_frame = pd.DataFrame({"unique_id": ["a"] * len(train), "y": train})
    theirs = float(
        reference_mase(frame, models=["model"], seasonality=1, train_df=train_frame)
        ["model"].iloc[0]
    )

    assert _mase(actual, predicted, scale) == pytest.approx(theirs, abs=1e-12)


# ---------------------------------------------------------------------------
# MAPE — الاتفاق حيث يجب، والاختلاف حيث قُرِّر
# ---------------------------------------------------------------------------
def test_mape_matches_sklearn_when_no_zeros_exist():
    """حيث تتطابق التعريفات (لا أصفار) يجب التطابق الحرفي — أي فرق هنا
    خطأ تنفيذ لا سياسة."""
    actual, predicted = SMOOTH

    assert _ours(actual, predicted).mape == pytest.approx(
        sk.mean_absolute_percentage_error(actual, predicted) * 100, abs=1e-9
    )


def test_mape_is_none_on_all_zero_demand_not_an_astronomical_number():
    """الافتراق المتعمَّد: sklearn بحماية eps يُخرج رقماً فلكياً على
    الأصفار؛ سياستنا None صريحة. رقمٌ كاذب أخطر من غياب الرقم."""
    actual, predicted = ALL_ZERO

    assert _ours(actual, predicted).mape is None
