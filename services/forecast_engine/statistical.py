# services/forecast_engine/statistical.py
"""
النماذج الإحصائية: ETS و SARIMA.

هذه إعادة تنفيذ لا تغليف لـ models/forecasting.py، والسبب جوهري:
`forecast_ets` القائمة تُرجع خطاً مسطّحاً عند نقص البيانات وتسمّيه "ETS"،
وتُرجع متوسطاً عند الفشل وتسمّيه "ETS" أيضاً. المستخدم يقرأ "نموذج: ETS"
ويظن أن نموذجاً موسمياً حلّل بياناته، بينما ما رآه هو آخر قيمة مكرّرة.

المحرك يحتاج العكس: نموذج يعلن حدوده صراحةً ويفشل بصوت مسموع، ليقرر
المحرك (لا النموذج) ما البديل — ويُسمّى البديل باسمه الحقيقي.

models/forecasting.py يبقى كما هو: ui/dashboard.py و tests/test_models.py
يعتمدان عليه، وتغييره خارج نطاق هذه المرحلة.
"""
from __future__ import annotations

import warnings
from typing import Sequence

import numpy as np
import pandas as pd

from config import CONFIDENCE_LEVEL, SEASONAL_PERIODS
from core.exceptions import ModelTrainingError

from .base import Forecaster, ForecastOutput

# محور زمني اصطناعي: النماذج تحتاج فهرساً منتظم الخطوة (freq يطابق حبيبة
# الملف الفعلية)، لا تاريخاً حقيقياً.
#
# التعليق السابق هنا ادّعى أن Prophet يعتمد على مطابقة هذا التاريخ للبيانات
# الفعلية (لأن موسميته السنوية تُحسب من اليوم في السنة). الادّعاء **خاطئ**،
# وقياس أثبته: ETS و SARIMA و Prophet تُنتج أرقاماً متطابقة حرفياً سواء
# بدأت السلسلة من 2022-12 أو 2019-03 أو 2000-07.
#
# السبب: النماذج ثابتة تحت الإزاحة (shift-invariant). إزاحة كل التواريخ
# بمقدار ثابت تُزيح النمط الموسمي المتعلَّم بنفس المقدار، وتُزيح معه أفق
# التنبؤ — فتُلغى الإزاحة. المهم هو *انتظام* الخطوة الشهرية لا موضعها
# على التقويم.
#
# لذا لا حاجة لتمرير تاريخ بداية المستخدم إلى المحرّكات، ولو بدا ذلك
# "أصحّ". يحرس هذه الحقيقةَ اختبارُ
# test_forecasts_are_invariant_to_the_synthetic_start_date.
SERIES_START = "2022-12-01"


def _period_index(length: int, freq: str) -> pd.DatetimeIndex:
    return pd.date_range(start=SERIES_START, periods=length, freq=freq)


def _as_timeseries(series: Sequence[float], freq: str) -> pd.Series:
    values = np.asarray(series, dtype=float)
    return pd.Series(values, index=_period_index(len(values), freq))


def _bounds_from_residuals(
    forecast: np.ndarray, residuals: np.ndarray, series: Sequence[float]
) -> tuple[list[float], list[float]]:
    residuals = residuals[~np.isnan(residuals)]
    if len(residuals) > 0:
        spread = float(np.std(residuals))
    else:
        spread = float(np.std(series)) * 0.1

    margin = CONFIDENCE_LEVEL * spread
    lower = np.maximum(forecast - margin, 0.0)
    return lower.tolist(), (forecast + margin).tolist()


class ETSForecaster(Forecaster):
    """Exponential Smoothing بمركّبتَي اتجاه وموسمية جمعيّتين.

    min_points = 2×seasonal_periods: النموذج الموسمي يحتاج دورتين كاملتين
    ليفصل النمط الموسمي عن الاتجاه. أقل من ذلك — statsmodels قد يُدرّب
    ويُرجع رقماً، لكنه رقم مُلائم للضجيج لا للموسمية.

    seasonal_periods/freq يُشتقّان من حبيبة الملف الفعلية (config.
    SEASONAL_PERIODS_BY_GRANULARITY/PANDAS_FREQ_BY_GRANULARITY عبر
    registry.default_models) — لا 12/"MS" مفروضتين على بيانات أسبوعية
    مثلاً. min_points/min_non_zero صفتا نسخة لا صنف: تُحسبان من
    seasonal_periods الممرَّر فعلاً، لا من الثابت الشهري دائماً.
    """

    name = "ETS"

    def __init__(
        self, seasonal_periods: int = SEASONAL_PERIODS, freq: str = "MS"
    ) -> None:
        self.seasonal_periods = seasonal_periods
        self.freq = freq
        self.min_points = 2 * seasonal_periods
        self.min_non_zero = seasonal_periods

    def fit_predict(self, series: Sequence[float], steps: int) -> ForecastOutput:
        from statsmodels.tsa.holtwinters import ExponentialSmoothing

        timeseries = _as_timeseries(series, self.freq)
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                fitted = ExponentialSmoothing(
                    timeseries,
                    trend="add",
                    seasonal="add",
                    seasonal_periods=self.seasonal_periods,
                    initialization_method="estimated",
                ).fit()
                forecast = np.asarray(fitted.forecast(steps), dtype=float)
        except Exception as exc:
            raise ModelTrainingError(
                f"فشل تدريب ETS: {exc}",
                cause=exc,
                context={"model": self.name, "points": len(series)},
            ) from exc

        if not np.all(np.isfinite(forecast)):
            raise ModelTrainingError(
                "ETS أنتج قيماً غير منتهية (NaN/inf)",
                context={"model": self.name, "points": len(series)},
            )

        forecast = np.maximum(forecast, 0.0)
        residuals = np.asarray(fitted.resid, dtype=float)
        lower, upper = _bounds_from_residuals(forecast, residuals, series)
        return ForecastOutput(values=forecast.tolist(), lower=lower, upper=upper)


class SARIMAForecaster(Forecaster):
    """SARIMA(1,1,1)(1,1,1,12).

    الرتب ثابتة كما في الكود القائم — البحث عن الرتب المثلى (auto-arima)
    خارج نطاق هذه المرحلة، وسيكون تحسيناً واضحاً لاحقاً.

    حدود الثقة هنا من النموذج نفسه (get_forecast) لا من الرواسب — أدق،
    لأنها تتسع مع أفق التنبؤ بدل أن تبقى ثابتة.
    """

    name = "SARIMA"

    def __init__(
        self, seasonal_periods: int = SEASONAL_PERIODS, freq: str = "MS"
    ) -> None:
        self.seasonal_periods = seasonal_periods
        self.freq = freq
        self.min_points = 2 * seasonal_periods
        self.min_non_zero = seasonal_periods

    def fit_predict(self, series: Sequence[float], steps: int) -> ForecastOutput:
        from statsmodels.tsa.arima.model import ARIMA

        timeseries = _as_timeseries(series, self.freq)
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                fitted = ARIMA(
                    timeseries,
                    order=(1, 1, 1),
                    seasonal_order=(1, 1, 1, self.seasonal_periods),
                ).fit()
                prediction = fitted.get_forecast(steps)
                forecast = np.asarray(prediction.predicted_mean, dtype=float)
                intervals = np.asarray(
                    prediction.conf_int(alpha=0.05), dtype=float
                )
        except Exception as exc:
            raise ModelTrainingError(
                f"فشل تدريب SARIMA: {exc}",
                cause=exc,
                context={"model": self.name, "points": len(series)},
            ) from exc

        if not np.all(np.isfinite(forecast)):
            raise ModelTrainingError(
                "SARIMA أنتج قيماً غير منتهية (NaN/inf)",
                context={"model": self.name, "points": len(series)},
            )

        forecast = np.maximum(forecast, 0.0)
        lower = np.maximum(intervals[:, 0], 0.0)
        upper = intervals[:, 1]

        # حدود غير منتهية تحدث حين لا يستقر النموذج — تراجَع إلى الرواسب
        if not (np.all(np.isfinite(lower)) and np.all(np.isfinite(upper))):
            residuals = np.asarray(fitted.resid, dtype=float)
            lower_list, upper_list = _bounds_from_residuals(forecast, residuals, series)
            return ForecastOutput(
                values=forecast.tolist(), lower=lower_list, upper=upper_list
            )

        return ForecastOutput(
            values=forecast.tolist(), lower=lower.tolist(), upper=upper.tolist()
        )
