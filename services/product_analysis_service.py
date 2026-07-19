# services/product_analysis_service.py
"""
Service Layer لاستكشاف تاريخ منتج واحد — لا تنبؤ.

## لماذا لا تنبؤ هنا (قرار نطاق صريح)

كانت هذه الطبقة تُشغّل ETS دائماً لتغذية صفحة
Advanced Analytics. أُزيل ذلك عمداً لسببين قِيسا لا خُمِّنا:

1. **ETS من أضعف النماذج ترتيباً** على هذا الكتالوج المتقطّع. تشغيل نموذج
   واحد ثابت بينما `services/forecast_engine` يختار من تسعة بالأدلة
   (backtesting) كان أسوأ بلا مبرّر.
2. **مساران للتنبؤ = رقمان مختلفان لنفس المنتج على صفحتين**. أمام مصنع
   يبني قراره على الرقم، هذا يقتل الثقة. الآن مسار واحد فقط:
   `services/forecast_engine` عبر صفحة التنبؤ.

فصارت هذه الطبقة **وصفية بحتة**: ماذا حدث فعلاً في التاريخ المحدّد.
والسؤال "ماذا سيحدث؟" له صفحته المبنية على الأدلة.
"""
from __future__ import annotations

from dataclasses import dataclass

from core.exceptions import InsufficientDataError
from core.logging_config import get_logger
from domain.entities import OutlierReport, ProductStats
from models.statistics import detect_outliers_iqr
from services.analytics import compute_basic_stats

logger = get_logger(__name__)


@dataclass
class ProductAnalysis:
    """وصف تاريخ منتج واحد ضمن نطاق زمني — جاهز للعرض مباشرة."""
    product_name: str
    selected_months: list
    series: list
    stats: ProductStats
    outliers: OutlierReport | None = None


def analyze_product(
    product_name: str,
    selected_months: list,
    series: list,
    *,
    include_outliers: bool = True,
) -> ProductAnalysis:
    """يصف تاريخ منتج واحد ضمن نطاق زمني محدد.

    Raises:
        InsufficientDataError: إذا كانت السلسلة فارغة (لا بيانات في
            النطاق المحدد). في هذه الحالة لا معنى لأي حساب لاحق.
    """
    if not series:
        raise InsufficientDataError(
            "لا توجد بيانات لهذا المنتج ضمن النطاق الزمني المحدد",
            context={"product": product_name},
        )

    raw_stats = compute_basic_stats(series)
    stats = ProductStats(product_name=product_name, **raw_stats)

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
        "Product described | product=%s | points=%d", product_name, len(series)
    )

    return ProductAnalysis(
        product_name=product_name,
        selected_months=selected_months,
        series=series,
        stats=stats,
        outliers=outliers,
    )
