# services/forecast_engine/prophet_model.py
"""
Prophet.

معزول في ملفه لأنه الاعتماد الأثقل في المشروع: يجرّ cmdstanpy و matplotlib
و holidays، والاستيراد وحده يكلّف ثانيتين. الاستيراد كسول داخل fit_predict —
من لا يستخدم Prophet لا يدفع ثمنه عند تشغيل التطبيق.
"""
from __future__ import annotations

import logging
import warnings
from typing import Sequence

import numpy as np
import pandas as pd

from core.exceptions import ModelTrainingError

from .base import Forecaster, ForecastOutput
from .statistical import SERIES_START


class ProphetForecaster(Forecaster):
    """Prophet بموسمية سنوية.

    weekly/daily معطّلتان: البيانات شهرية، وتفعيلهما يجعل النموذج يلائم
    ضجيجاً لا وجود له في بيانات بهذا التردد.

    min_points = 24: Prophet يحذّر تحت دورتين ثم يُدرّب على أي حال —
    وهذا بالضبط النمط الذي نتجنّبه (رقم يبدو إجابة وليس كذلك).
    """

    name = "Prophet"
    min_points = 24
    min_non_zero = 12

    def fit_predict(self, series: Sequence[float], steps: int) -> ForecastOutput:
        try:
            from prophet import Prophet
        except ImportError as exc:
            raise ModelTrainingError(
                "Prophet غير مثبّت — pip install -r requirements.lock.txt",
                cause=exc,
                context={"model": self.name},
            ) from exc

        values = np.asarray(series, dtype=float)
        frame = pd.DataFrame(
            {
                "ds": pd.date_range(start=SERIES_START, periods=len(values), freq="MS"),
                "y": values,
            }
        )

        # Prophet يطبع تقدّم التحسين على stdout عبر cmdstanpy — ضجيج بحت
        # في سياقنا (كتالوج كامل × عدة نماذج).
        cmdstanpy_logger = logging.getLogger("cmdstanpy")
        previous_level = cmdstanpy_logger.level
        cmdstanpy_logger.setLevel(logging.CRITICAL)
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                model = Prophet(
                    yearly_seasonality=True,
                    weekly_seasonality=False,
                    daily_seasonality=False,
                )
                model.fit(frame)
                future = model.make_future_dataframe(periods=steps, freq="MS")
                prediction = model.predict(future).iloc[-steps:]
        except Exception as exc:
            raise ModelTrainingError(
                f"فشل تدريب Prophet: {exc}",
                cause=exc,
                context={"model": self.name, "points": len(series)},
            ) from exc
        finally:
            cmdstanpy_logger.setLevel(previous_level)

        forecast = np.maximum(
            np.asarray(prediction["yhat"], dtype=float), 0.0
        )
        lower = np.maximum(np.asarray(prediction["yhat_lower"], dtype=float), 0.0)
        upper = np.asarray(prediction["yhat_upper"], dtype=float)

        if not np.all(np.isfinite(forecast)):
            raise ModelTrainingError(
                "Prophet أنتج قيماً غير منتهية (NaN/inf)",
                context={"model": self.name, "points": len(series)},
            )

        return ForecastOutput(
            values=forecast.tolist(), lower=lower.tolist(), upper=upper.tolist()
        )
