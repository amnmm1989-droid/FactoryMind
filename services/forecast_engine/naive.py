# services/forecast_engine/naive.py
"""
نماذج الأساس.

ليست حشواً — لها وظيفتان لا يؤديهما غيرها:

1. **التغطية:** 39% من كتالوج التحقّق له 1-5 أشهر غير صفرية. ETS/SARIMA/
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
from .reference import point_forecast


def _interval(center: np.ndarray, spread: float) -> tuple[list[float], list[float]]:
    """حدود ثقة متماثلة حول التنبؤ، غير سالبة.

    الكميات المنتَجة لا تكون سالبة — حدّ أدنى سالب ليس متحفظاً، بل بلا معنى.
    """
    margin = CONFIDENCE_LEVEL * spread
    lower = np.maximum(center - margin, 0.0)
    upper = center + margin
    return lower.tolist(), upper.tolist()


class NaiveForecaster(Forecaster):
    """آخر قيمة مكرّرة — `statsforecast.Naive`.

    الأساس المرجعي في أدبيات التنبؤ (random walk). بسيط بما يكفي لكتابته
    في سطرين، لكن القاعدة واحدة: ما توفّره المكتبة المرجعية يُستورَد، فلا
    يتفرّق مصدر الحقيقة بين نموذج ونموذج.
    """

    name = "Naive"
    min_points = 1
    min_non_zero = 1

    def fit_predict(self, series: Sequence[float], steps: int) -> ForecastOutput:
        from statsforecast.models import Naive

        if not len(series):
            raise ModelTrainingError("سلسلة فارغة", context={"model": self.name})

        forecast = point_forecast(Naive(), series, steps, name=self.name)
        spread = float(np.std(np.asarray(series, dtype=float)))
        lower, upper = _interval(forecast, spread)
        return ForecastOutput(values=forecast.tolist(), lower=lower, upper=upper)


class MovingAverageForecaster(Forecaster):
    """متوسط آخر k فترة، مكرّراً — `statsforecast.WindowAverage`."""

    name = "MovingAverage"
    min_points = 2
    min_non_zero = 1

    def __init__(self, window: int = 3) -> None:
        if window < 1:
            raise ValueError(f"نافذة غير صالحة: {window}")
        self.window = window

    def fit_predict(self, series: Sequence[float], steps: int) -> ForecastOutput:
        from statsforecast.models import WindowAverage

        values = np.asarray(series, dtype=float)
        if len(values) < self.min_points:
            raise ModelTrainingError(
                f"نقاط غير كافية: {len(values)}", context={"model": self.name},
            )
        # نافذة أطول من السلسلة تُفشل المكتبة؛ القصّ هنا يبقيها منطبقة على
        # السلاسل القصيرة — وهي 39% من هذا الكتالوج.
        window = min(self.window, len(values))

        forecast = point_forecast(
            WindowAverage(window_size=window), series, steps, name=self.name,
        )
        lower, upper = _interval(forecast, float(np.std(values)))
        return ForecastOutput(values=forecast.tolist(), lower=lower, upper=upper)
