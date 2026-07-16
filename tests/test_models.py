# tests/test_models.py
import pytest
import numpy as np
from models.forecasting import forecast_ets, forecast_sarima
from models.statistics import trend_analysis, detect_outliers_iqr

# بيانات اختبار ثابتة (مأخوذة من عينة من data.json)
SAMPLE_SERIES = [5, 82, 89, 74, 99, 77, 95, 93, 152, 178, 117, 147, 171, 162, 179, 172, 150, 165, 236, 229, 258, 333, 260, 234, 187, 332, 179, 348, 184, 283, 269, 228, 215, 182, 101, 237, 198, 114, 123, 292, 239, 199, 249, 127]

def test_forecast_ets():
    forecast, lower, upper, metrics, error = forecast_ets(SAMPLE_SERIES, steps=6)
    assert error is None
    assert len(forecast) == 6
    assert len(lower) == 6
    assert len(upper) == 6
    assert metrics is not None  # لأنه يوجد أكثر من 20 نقطة
    assert 'MAE' in metrics
    assert 'RMSE' in metrics
    assert 'MAPE' in metrics

def test_forecast_sarima():
    forecast, error = forecast_sarima(SAMPLE_SERIES, steps=6)
    assert error is None
    assert len(forecast) == 6

def test_trend_analysis():
    trend = trend_analysis(SAMPLE_SERIES)
    assert 'slope' in trend
    assert 'r_squared' in trend
    assert trend['direction'] in ["📈 صاعد", "📉 هابط", "➡️ مستقر"]

def test_detect_outliers_iqr():
    outliers, lower, upper = detect_outliers_iqr(SAMPLE_SERIES)
    assert isinstance(outliers, list)
    assert len(outliers) >= 0