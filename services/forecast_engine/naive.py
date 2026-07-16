# services/forecast_engine/naive.py
"""
نماذج الأساس.

ليست حشواً — لها وظيفتان لا يؤديهما غيرها:

1. **التغطية:** 72 من 185 منتجاً لها 1-5 أشهر غير صفرية. ETS/SARIMA/
   Prophet/الأشجار كلها ترفضها. بلا أساس، المحرك يفشل على 39% من كتالوجك.

2. **المرجع:** بلا رقم تقارن به، "MAE = 12.4" لا يعني شيئاً. هل هذا جيد؟
   الجواب الوحيد المفيد: "أفضل أم أسوأ من تكرار آخر قيمة؟". نموذج لا يهزم
   الساذج لا يستحق وقت تدريبه — ومع 32 صف تدريب لأفضل منتج لديك، هذه
   نتيجة واردة جداً.
"""
from __future__ import annotations

from typing import Sequence

import numpy as np

from config import CONFIDENCE_LEVEL
from core.exceptions import ModelTrainingError

from .base import Forecaster, ForecastOutput


def _interval(center: np.ndarray, spread: float) -> tuple[list[float], list[float]]:
    """حدود ثقة متماثلة حول التنبؤ، غير سالبة.

    الكميات المنتَجة لا تكون سالبة — حدّ أدنى سالب ليس متحفظاً، بل بلا معنى.
    """
    margin = CONFIDENCE_LEVEL * spread
    lower = np.maximum(center - margin, 0.0)
    upper = center + margin
    return lower.tolist(), upper.tolist()


class NaiveForecaster(Forecaster):
    """آخر قيمة، مكرّرة. الأساس المرجعي في أدبيات التنبؤ (naive/random walk)."""

    name = "Naive"
    min_points = 1
    min_non_zero = 1

    def fit_predict(self, series: Sequence[float], steps: int) -> ForecastOutput:
        if not series:
            raise ModelTrainingError(
                "سلسلة فارغة", context={"model": self.name}
            )

        values = np.asarray(series, dtype=float)
        forecast = np.full(steps, values[-1], dtype=float)

        # عدم اليقين = تقلب الفروق بين الأشهر المتتالية. سلسلة ثابتة -> حدود ضيقة،
        # سلسلة متذبذبة -> حدود واسعة. وهو ما نريده بالضبط.
        diffs = np.diff(values)
        spread = float(np.std(diffs)) if len(diffs) > 0 else abs(float(values[-1])) * 0.2

        lower, upper = _interval(forecast, spread)
        return ForecastOutput(values=forecast.tolist(), lower=lower, upper=upper)


class MovingAverageForecaster(Forecaster):
    """متوسط آخر k شهراً، مكرّر.

    أمتن من Naive حين تكون البيانات متذبذبة: قيمة أخيرة شاذة تُضلّل Naive
    تماماً، بينما يخفّف المتوسط أثرها.
    """

    name = "MovingAverage"
    min_points = 3
    min_non_zero = 2

    def __init__(self, window: int = 3) -> None:
        if window < 1:
            raise ValueError(f"نافذة غير صالحة: {window}")
        self.window = window

    def fit_predict(self, series: Sequence[float], steps: int) -> ForecastOutput:
        values = np.asarray(series, dtype=float)
        if len(values) < self.window:
            raise ModelTrainingError(
                f"السلسلة ({len(values)}) أقصر من النافذة ({self.window})",
                context={"model": self.name},
            )

        window_values = values[-self.window:]
        forecast = np.full(steps, float(np.mean(window_values)), dtype=float)

        spread = float(np.std(window_values)) if len(window_values) > 1 else 0.0
        if spread == 0.0:
            # نافذة ثابتة تماماً: لا تدّعِ يقيناً مطلقاً — اشتقّ العرض من السلسلة كلها
            spread = float(np.std(values)) if len(values) > 1 else abs(float(values[-1])) * 0.2

        lower, upper = _interval(forecast, spread)
        return ForecastOutput(values=forecast.tolist(), lower=lower, upper=upper)
