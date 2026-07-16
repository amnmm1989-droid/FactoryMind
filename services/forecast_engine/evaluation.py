# services/forecast_engine/evaluation.py
"""
تقييم النماذج بالـ backtesting.

المبدأ: لا تثق بنموذج على بيانات رآها. نُخفي آخر h شهراً، ندرّب على ما
تبقّى، ونقارن التنبؤ بما أخفيناه. هذا هو الرقم الوحيد الذي يعني شيئاً
حين نختار "الأفضل".

⚠️ MAPE والأصفار — فخ حقيقي في هذه البيانات:
    mape = mean(|actual - pred| / actual)
قسمة على صفر حين actual = 0. ووسيط منتجاتك 9 أشهر غير صفرية من 44، أي
أن نافذة الاختبار مليئة بالأصفار غالباً. النتيجة inf أو nan — ولو قارنّا
النماذج بها، لفاز أول نموذج تصادف أن نافذته خلت من الأصفار، لا الأنسب.
الحل هنا: MAPE يُحسب على القيم غير الصفرية فقط، ويكون None إن لم توجد.
None صريح أفضل من رقم كاذب.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import numpy as np

from core.exceptions import ModelTrainingError
from core.logging_config import get_logger

from .base import Forecaster

logger = get_logger(__name__)

# أقصى أفق للتقييم — يوازن بين اختبار ذي معنى وإبقاء بيانات تدريب كافية
MAX_HOLDOUT = 6


@dataclass(frozen=True)
class ModelMetrics:
    """مقاييس دقة نموذج على بيانات لم يرَها."""
    mae: float
    rmse: float
    mape: float | None       # None حين تكون كل القيم الحقيقية أصفاراً
    holdout_size: int

    def is_better_than(self, other: "ModelMetrics | None") -> bool:
        """المقارنة بالـ RMSE.

        لماذا RMSE لا MAE؟ RMSE يعاقب الأخطاء الكبيرة أكثر — وفي التخطيط
        الإنتاجي، خطأ واحد فادح أسوأ من عدة أخطاء صغيرة بنفس المجموع.
        ولماذا لا MAPE؟ لأنه None على بيانات كثيرة هنا، فلا يصلح معياراً
        موحّداً للمقارنة.
        """
        if other is None:
            return True
        return self.rmse < other.rmse


def choose_holdout(length: int) -> int:
    """حجم نافذة الاختبار: خُمس السلسلة، بحد أقصى 6 وأدنى 1.

    ثابت (6 دائماً) كان سيلتهم ربع سلسلة من 24 نقطة ويترك تدريباً هزيلاً.
    """
    return max(1, min(MAX_HOLDOUT, length // 5))


def _mape(actual: np.ndarray, predicted: np.ndarray) -> float | None:
    """MAPE على القيم غير الصفرية فقط. None إن كانت كلها أصفاراً."""
    mask = actual != 0
    if not np.any(mask):
        return None
    return float(np.mean(np.abs((actual[mask] - predicted[mask]) / actual[mask])) * 100)


def compute_metrics(
    actual: Sequence[float], predicted: Sequence[float], holdout_size: int
) -> ModelMetrics:
    actual_array = np.asarray(actual, dtype=float)
    predicted_array = np.asarray(predicted, dtype=float)

    if len(actual_array) != len(predicted_array):
        raise ValueError(
            f"أطوال غير متطابقة: actual={len(actual_array)} predicted={len(predicted_array)}"
        )

    errors = actual_array - predicted_array
    return ModelMetrics(
        mae=float(np.mean(np.abs(errors))),
        rmse=float(np.sqrt(np.mean(errors**2))),
        mape=_mape(actual_array, predicted_array),
        holdout_size=holdout_size,
    )


def backtest(forecaster: Forecaster, series: Sequence[float]) -> ModelMetrics | None:
    """تقييم نموذج على آخر h شهراً من السلسلة.

    Returns:
        ModelMetrics، أو None إن تعذّر التقييم — وهذا ليس فشلاً بل واقع:
        سلسلة قصيرة لا يبقى منها تدريب كافٍ بعد اقتطاع نافذة الاختبار.
        المحرك يميّز "لم يُقيَّم" عن "قُيِّم وكان سيئاً".
    """
    holdout = choose_holdout(len(series))
    train = list(series[:-holdout])
    test = list(series[-holdout:])

    if not train or not forecaster.can_handle(train):
        logger.debug(
            "Backtest skipped | model=%s | train_points=%d", forecaster.name, len(train)
        )
        return None

    try:
        output = forecaster.fit_predict(train, holdout)
    except ModelTrainingError:
        logger.debug("Backtest failed | model=%s", forecaster.name)
        return None

    return compute_metrics(test, output.values, holdout)
