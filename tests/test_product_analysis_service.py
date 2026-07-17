# tests/test_product_analysis_service.py
import pytest

from core.exceptions import InsufficientDataError
from domain.entities import ForecastResult, OutlierReport, ProductStats, TrendAnalysis
from services.product_analysis_service import ProductAnalysis, analyze_product

SAMPLE_SERIES = [5, 82, 89, 74, 99, 77, 95, 93, 152, 178, 117, 147, 171, 162, 179,
                 172, 150, 165, 236, 229, 258, 333, 260, 234, 187, 332, 179, 348,
                 184, 283, 269, 228, 215, 182, 101, 237, 198, 114, 123, 292, 239,
                 199, 249, 127]
FULL_MONTHS = [f"شهر {i}" for i in range(len(SAMPLE_SERIES))]
SELECTED_MONTHS = FULL_MONTHS


def test_analyze_product_returns_product_analysis():
    result = analyze_product(
        product_name="منتج تجريبي",
        full_months=FULL_MONTHS,
        selected_months=SELECTED_MONTHS,
        series=SAMPLE_SERIES,
        to_idx=len(SAMPLE_SERIES) - 1,
        forecast_steps=6,
    )
    assert isinstance(result, ProductAnalysis)
    assert isinstance(result.stats, ProductStats)
    assert isinstance(result.ets, ForecastResult)
    assert result.ets.model_name == "ETS"
    assert len(result.ets.forecast_values) == 6
    assert len(result.forecast_months) == 6


def test_analyze_product_raises_on_empty_series():
    with pytest.raises(InsufficientDataError):
        analyze_product(
            product_name="منتج فارغ",
            full_months=FULL_MONTHS,
            selected_months=[],
            series=[],
            to_idx=0,
            forecast_steps=6,
        )


def test_analyze_product_includes_trend_by_default():
    result = analyze_product(
        product_name="منتج تجريبي",
        full_months=FULL_MONTHS,
        selected_months=SELECTED_MONTHS,
        series=SAMPLE_SERIES,
        to_idx=len(SAMPLE_SERIES) - 1,
        forecast_steps=6,
    )
    assert isinstance(result.trend, TrendAnalysis)
    assert result.trend.direction in ["up", "down", "flat"]


def test_analyze_product_skips_trend_when_disabled():
    result = analyze_product(
        product_name="منتج تجريبي",
        full_months=FULL_MONTHS,
        selected_months=SELECTED_MONTHS,
        series=SAMPLE_SERIES,
        to_idx=len(SAMPLE_SERIES) - 1,
        forecast_steps=6,
        include_trend=False,
    )
    assert result.trend is None


def test_analyze_product_includes_outliers_by_default():
    result = analyze_product(
        product_name="منتج تجريبي",
        full_months=FULL_MONTHS,
        selected_months=SELECTED_MONTHS,
        series=SAMPLE_SERIES,
        to_idx=len(SAMPLE_SERIES) - 1,
        forecast_steps=6,
    )
    assert isinstance(result.outliers, OutlierReport)


def test_analyze_product_sarima_disabled_by_default():
    result = analyze_product(
        product_name="منتج تجريبي",
        full_months=FULL_MONTHS,
        selected_months=SELECTED_MONTHS,
        series=SAMPLE_SERIES,
        to_idx=len(SAMPLE_SERIES) - 1,
        forecast_steps=6,
    )
    assert result.sarima_values is None


def test_analyze_product_sarima_enabled():
    result = analyze_product(
        product_name="منتج تجريبي",
        full_months=FULL_MONTHS,
        selected_months=SELECTED_MONTHS,
        series=SAMPLE_SERIES,
        to_idx=len(SAMPLE_SERIES) - 1,
        forecast_steps=6,
        include_sarima=True,
    )
    # قد تفشل SARIMA لأسباب رياضية بحتة (بيانات غير كافية للموسمية)، لكن
    # الحقل يجب أن يكون إما قائمة أو None (لا استثناء غير متوقع)
    assert result.sarima_values is None or isinstance(result.sarima_values, list)


def test_forecast_result_metrics_populated_for_long_series():
    result = analyze_product(
        product_name="منتج تجريبي",
        full_months=FULL_MONTHS,
        selected_months=SELECTED_MONTHS,
        series=SAMPLE_SERIES,  # 44 نقطة > 20، إذن metrics يجب أن تُحسب
        to_idx=len(SAMPLE_SERIES) - 1,
        forecast_steps=6,
    )
    assert result.ets.mae is not None
    assert result.ets.rmse is not None
    assert result.ets.mape is not None
