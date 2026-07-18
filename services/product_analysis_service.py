# services/product_analysis_service.py
"""
Service Layer لتحليل منتج واحد.

هذا الملف يحل محل الاستدعاء المباشر لـ models.forecasting /
models.statistics / services.analytics من داخل ui/dashboard.py.

قبل Phase 1:
    ui/dashboard.py يستدعي forecast_ets, forecast_sarima, trend_analysis,
    detect_outliers_iqr, compute_basic_stats مباشرة ويتعامل مع قواميس خام.

بعد Phase 1:
    ui/dashboard.py يستدعي analyze_product() مرة واحدة ويحصل على
    ProductAnalysis (كائن domain واحد يحمل كل شيء)، والأخطاء تُسجَّل
    مركزياً عبر core.logging_config بدل st.warning المباشر داخل منطق
    الحساب.

⚠️ لم يتم تعديل أي دالة داخل models/ أو services/analytics.py — هذه
الطبقة تُغلّفها فقط (Wrapper)، حفاظاً على عقد الاختبارات الحالية
(tests/test_models.py) كما هو دون أي تغيير.
"""
from __future__ import annotations

from dataclasses import dataclass

from core.exceptions import InsufficientDataError
from core.logging_config import get_logger
from domain.entities import ForecastResult, OutlierReport, ProductStats, TrendAnalysis
from models.forecasting import forecast_ets, forecast_sarima
from models.statistics import detect_outliers_iqr, trend_analysis
from services.analytics import compute_basic_stats, prepare_forecast_months

logger = get_logger(__name__)


@dataclass
class ProductAnalysis:
    """نتيجة تحليل منتج واحد جاهزة للعرض مباشرة في أي واجهة (Streamlit
    الحالية أو أي واجهة مستقبلية)."""
    product_name: str
    selected_months: list
    series: list
    stats: ProductStats
    forecast_months: list
    ets: ForecastResult
    sarima_values: list | None = None
    trend: TrendAnalysis | None = None
    outliers: OutlierReport | None = None


def analyze_product(
    product_name: str,
    full_months: list,
    selected_months: list,
    series: list,
    to_idx: int,
    forecast_steps: int,
    *,
    include_sarima: bool = False,
    include_trend: bool = True,
    include_outliers: bool = True,
    granularity: str = "monthly",
) -> ProductAnalysis:
    """يُشغّل التحليل الكامل لمنتج واحد ضمن نطاق زمني محدد.

    Raises:
        InsufficientDataError: إذا كانت السلسلة فارغة (لا بيانات في
            النطاق المحدد). في هذه الحالة لا معنى لأي حساب لاحق.
    """
    if not series:
        raise InsufficientDataError(
            "لا توجد بيانات لهذا المنتج ضمن النطاق الزمني المحدد",
            context={"product": product_name, "to_idx": to_idx},
        )

    # ----- إحصائيات أساسية -----
    raw_stats = compute_basic_stats(series)
    stats = ProductStats(product_name=product_name, **raw_stats)

    # ----- التنبؤ ETS (دائماً) -----
    forecast_vals, lower_vals, upper_vals, metrics, ets_error = forecast_ets(
        series, steps=forecast_steps
    )
    if ets_error:
        logger.warning("ETS forecast warning | product=%s | %s", product_name, ets_error)

    ets_result = ForecastResult(
        product_name=product_name,
        model_name="ETS",
        forecast_values=list(forecast_vals),
        lower_bound=list(lower_vals),
        upper_bound=list(upper_vals),
        mae=metrics.get("MAE") if metrics else None,
        rmse=metrics.get("RMSE") if metrics else None,
        mape=metrics.get("MAPE") if metrics else None,
    )

    # ----- SARIMA (اختياري) -----
    sarima_values = None
    if include_sarima:
        sarima_forecast, sarima_error = forecast_sarima(series, steps=forecast_steps)
        if sarima_error:
            logger.warning("SARIMA forecast warning | product=%s | %s", product_name, sarima_error)
        sarima_values = list(sarima_forecast) if sarima_forecast is not None else None

    forecast_months = prepare_forecast_months(
        to_idx, full_months, forecast_steps, granularity
    )

    # ----- تحليل الاتجاه (اختياري) -----
    trend = None
    if include_trend:
        raw_trend = trend_analysis(series)
        trend = TrendAnalysis(product_name=product_name, **raw_trend)

    # ----- القيم الشاذة (اختياري) -----
    outliers = None
    if include_outliers:
        idx_list, lower_bound, upper_bound = detect_outliers_iqr(series)
        outliers = OutlierReport(
            product_name=product_name,
            outlier_indices=idx_list,
            lower_bound=lower_bound,
            upper_bound=upper_bound,
        )

    logger.info(
        "Product analyzed | product=%s | points=%d | forecast_steps=%d | sarima=%s",
        product_name, len(series), forecast_steps, include_sarima,
    )

    return ProductAnalysis(
        product_name=product_name,
        selected_months=selected_months,
        series=series,
        stats=stats,
        forecast_months=forecast_months,
        ets=ets_result,
        sarima_values=sarima_values,
        trend=trend,
        outliers=outliers,
    )
