# services/risk_service/scoring.py
"""
تجميع العوامل في درجة خطورة واحدة 0-100.
"""
from __future__ import annotations

from typing import Sequence

from core.exceptions import InsufficientDataError
from core.logging_config import get_logger
from domain.entities import ForecastResult, InventoryStatus, RiskScore

from . import factors

logger = get_logger(__name__)

# أوزان العوامل. مجموعها 1.0 حين تُعرف كلها؛ وتُعاد الموازنة على المعروف فقط.
#
# المنطق: تقلب الطلب أقوى مؤشر على صعوبة التخطيط، ونفاد المخزون ودقة
# التنبؤ يليانه (الأول أثر مباشر، الثاني يقوّض الثقة بكل ما بُني عليه).
# الموسمية والنمو أنماط قابلة للتوقع نسبياً — تُضيف خطورة لكنها أقل حدّة.
#
# هذه معايرة أولية بلا بيانات تحقّق. تُضبط حين تتراكم نتائج فعلية
# (production_plans.actual_quantity مقابل planned_quantity يعطي إشارة).
FACTOR_WEIGHTS: dict[str, float] = {
    "demand_volatility": 0.30,
    "stock_depletion_risk": 0.25,
    "forecast_accuracy_penalty": 0.25,
    "seasonality_factor": 0.10,
    "growth_rate": 0.10,
}


def _weighted_score(known: dict[str, float]) -> float:
    """جمع موزون على العوامل المعروفة، بإعادة موازنة الأوزان.

    مثال: بلا بيانات مخزون (حالة كل المنتجات حتى Phase 5)، تُحذف
    stock_depletion_risk (0.25) ويُعاد توزيع أوزان الأربعة الباقية على
    0.75 لتجمع 1.0 من جديد.

    البديل — اعتبار المجهول صفراً — يخفض كل درجة بمقدار وزن العامل
    الغائب، فيبدو منتج مجهول المخزون أأمن من منتج نعرف أن مخزونه وفير.
    وهو عكس الحقيقة تماماً.
    """
    if not known:
        raise InsufficientDataError(
            "تعذّر حساب أي عامل خطورة",
            context={"known_factors": []},
        )

    total_weight = sum(FACTOR_WEIGHTS[name] for name in known)
    weighted_sum = sum(FACTOR_WEIGHTS[name] * value for name, value in known.items())
    return weighted_sum / total_weight


def compute_risk(
    product_name: str,
    series: Sequence[float],
    forecast: ForecastResult,
    inventory: InventoryStatus | None = None,
) -> RiskScore:
    """حساب درجة خطورة منتج من عوامله الخمسة.

    Args:
        inventory: حالة المخزون إن عُرفت. None (الافتراضي حتى Phase 5)
            يعني استبعاد عامل النفاد وإعادة موازنة الباقي — لا افتراض
            أن المخزون وفير.

    Raises:
        InsufficientDataError: تعذّر حساب أي عامل.
    """
    computed = {
        "demand_volatility": factors.demand_volatility(series),
        "stock_depletion_risk": factors.stock_depletion_risk(inventory, forecast),
        "forecast_accuracy_penalty": factors.forecast_accuracy_penalty(forecast, series),
        "seasonality_factor": factors.seasonality_factor(series),
        "growth_rate": factors.growth_rate(series),
    }
    known = {name: value for name, value in computed.items() if value is not None}
    score = _weighted_score(known)

    if len(known) < len(FACTOR_WEIGHTS):
        logger.debug(
            "Risk computed from partial factors | product=%s | known=%d/5 | missing=%s",
            product_name, len(known), sorted(set(computed) - set(known)),
        )

    return RiskScore(
        product_name=product_name,
        score=score,
        demand_volatility=computed["demand_volatility"],
        stock_depletion_risk=computed["stock_depletion_risk"],
        forecast_accuracy_penalty=computed["forecast_accuracy_penalty"],
        seasonality_factor=computed["seasonality_factor"],
        growth_rate=computed["growth_rate"],
    )
