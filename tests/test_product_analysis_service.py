# tests/test_product_analysis_service.py
"""
طبقة وصف المنتج — بلا تنبؤ.

أُزيلت اختبارات ETS/SARIMA/الاتجاه مع إزالة التنبؤ نفسه من هذه الطبقة
(راجع services/product_analysis_service.py): مسار التنبؤ الوحيد الآن هو
services/forecast_engine، وله اختباراته في tests/test_forecast_engine.py.
"""
import pytest

from core.exceptions import InsufficientDataError
from domain.entities import OutlierReport, ProductStats
from services.product_analysis_service import ProductAnalysis, analyze_product

SAMPLE_SERIES = [5, 82, 89, 74, 99, 77, 95, 93, 152, 178, 117, 147, 171, 162, 179,
                 172, 150, 165, 236, 229, 258, 333, 260, 234, 187, 332, 179, 348,
                 184, 283, 269, 228, 215, 182, 101, 237, 198, 114, 123, 292, 239,
                 199, 249, 127]
SELECTED_MONTHS = [f"شهر {i}" for i in range(len(SAMPLE_SERIES))]


def test_analyze_product_returns_product_analysis():
    result = analyze_product(
        product_name="منتج تجريبي",
        selected_months=SELECTED_MONTHS,
        series=SAMPLE_SERIES,
    )
    assert isinstance(result, ProductAnalysis)
    assert isinstance(result.stats, ProductStats)
    assert result.stats.product_name == "منتج تجريبي"
    assert result.series == SAMPLE_SERIES


def test_analyze_product_raises_on_empty_series():
    with pytest.raises(InsufficientDataError):
        analyze_product(
            product_name="منتج فارغ",
            selected_months=[],
            series=[],
        )


def test_analyze_product_includes_outliers_by_default():
    result = analyze_product(
        product_name="منتج تجريبي",
        selected_months=SELECTED_MONTHS,
        series=SAMPLE_SERIES,
    )
    assert isinstance(result.outliers, OutlierReport)


def test_analyze_product_skips_outliers_when_disabled():
    result = analyze_product(
        product_name="منتج تجريبي",
        selected_months=SELECTED_MONTHS,
        series=SAMPLE_SERIES,
        include_outliers=False,
    )
    assert result.outliers is None


def test_the_service_no_longer_forecasts():
    """حارس القرار: مسار تنبؤ ثانٍ هنا كان يعني رقمين مختلفين لنفس المنتج
    على صفحتين — راجع services/product_analysis_service.py."""
    result = analyze_product(
        product_name="منتج تجريبي",
        selected_months=SELECTED_MONTHS,
        series=SAMPLE_SERIES,
    )
    for gone in ("ets", "sarima_values", "trend", "forecast_months"):
        assert not hasattr(result, gone), f"{gone} عاد إلى طبقة وصفية"
