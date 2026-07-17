# models/forecasting.py
import numpy as np
import pandas as pd
from statsmodels.tsa.holtwinters import ExponentialSmoothing
from statsmodels.tsa.arima.model import ARIMA
import warnings
warnings.filterwarnings('ignore')

from config import SEASONAL_PERIODS, CONFIDENCE_LEVEL
from core.logging_config import get_logger

logger = get_logger(__name__)

def forecast_ets(series, steps=6, seasonal_periods=SEASONAL_PERIODS, freq='MS'):
    """
    توقع باستخدام نموذج Exponential Smoothing (ETS)
    إرجاع: (forecast, lower, upper, metrics, error_message)

    freq: تردد pandas المطابق للحبيبة الفعلية (راجع
    config.PANDAS_FREQ_BY_GRANULARITY). الافتراضي 'MS' يبقي هذه الدالة
    كما هي لمستهلكيها الحاليين (ui/dashboard.py وtests/test_models.py) —
    راجع services/forecast_engine/statistical.py للتنفيذ المُعمَّم فعلاً.
    """
    try:
        if len(series) < 2 * seasonal_periods:
            last_val = series[-1] if len(series) > 0 else 0
            forecast = np.full(steps, last_val)
            lower = forecast - abs(last_val * 0.2)
            upper = forecast + abs(last_val * 0.2)
            return forecast, lower, upper, None, None

        idx = pd.date_range(start='2022-12-01', periods=len(series), freq=freq)
        ts = pd.Series(series, index=idx)

        model = ExponentialSmoothing(
            ts,
            trend='add',
            seasonal='add',
            seasonal_periods=seasonal_periods,
            initialization_method='estimated'
        )
        fitted = model.fit()
        forecast_result = fitted.forecast(steps)
        forecast_values = forecast_result.values

        residuals = fitted.resid.dropna()
        if len(residuals) > 0:
            std_resid = residuals.std()
        else:
            std_resid = np.std(series) * 0.1
        z = CONFIDENCE_LEVEL
        lower = forecast_values - z * std_resid
        upper = forecast_values + z * std_resid

        # حساب مقاييس الدقة على بيانات التدريب (إن أمكن)
        metrics = None
        if len(series) > 20:
            train = ts[:-6]
            test = ts[-6:]
            try:
                model_train = ExponentialSmoothing(
                    train,
                    trend='add',
                    seasonal='add',
                    seasonal_periods=seasonal_periods,
                    initialization_method='estimated'
                ).fit()
                pred_train = model_train.forecast(len(test))
                mae = np.mean(np.abs(test - pred_train))
                rmse = np.sqrt(np.mean((test - pred_train)**2))
                mape = np.mean(np.abs((test - pred_train) / test)) * 100
                metrics = {'MAE': mae, 'RMSE': rmse, 'MAPE': mape}
            except Exception:
                logger.warning("ETS accuracy metrics computation failed | series_len=%d", len(series))

        return forecast_values, lower, upper, metrics, None

    except Exception as e:
        logger.exception("ETS forecast failed | series_len=%d | steps=%d", len(series), steps)
        # إرجاع رسالة الخطأ بدلاً من استدعاء st.warning
        if len(series) == 0:
            forecast = np.zeros(steps)
            lower = np.zeros(steps)
            upper = np.zeros(steps)
        else:
            window = min(6, len(series))
            last_vals = series[-window:] if window > 0 else [0]
            avg = np.mean(last_vals)
            forecast = np.full(steps, avg)
            std = np.std(last_vals) if len(last_vals) > 1 else avg * 0.1
            lower = forecast - CONFIDENCE_LEVEL * std
            upper = forecast + CONFIDENCE_LEVEL * std
        return forecast, lower, upper, None, str(e)


def forecast_sarima(series, steps=6, seasonal_periods=SEASONAL_PERIODS, freq='MS'):
    try:
        if len(series) < 2 * seasonal_periods:
            return None, None
        idx = pd.date_range(start='2022-12-01', periods=len(series), freq=freq)
        ts = pd.Series(series, index=idx)
        model = ARIMA(ts, order=(1,1,1), seasonal_order=(1,1,1,seasonal_periods))
        fitted = model.fit()
        forecast = fitted.forecast(steps).values
        return forecast, None
    except Exception as e:
        logger.exception("SARIMA forecast failed | series_len=%d | steps=%d", len(series), steps)
        return None, str(e)