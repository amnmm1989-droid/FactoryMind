# services/risk_service/__init__.py
"""
حساب درجة خطورة المنتج (Phase 4).

    from services.risk_service import compute_risk

    risk = compute_risk("منتج", series, forecast, inventory=None)
    risk.score            # 0-100
    risk.level            # RiskLevel.LOW / MEDIUM / HIGH
    risk.missing_factors  # ما تعذّر حسابه — يُعرَض مع الدرجة لا يُخفى
    risk.confidence       # نسبة العوامل المعروفة (0-1)

العوامل الخمسة: تقلب الطلب، نفاد المخزون، دقة التنبؤ، الموسمية، النمو.
عامل بلا بيانات = None (لا صفر)، يُستبعد من الحساب مع إعادة موازنة الباقي.
"""
from .factors import (
    demand_volatility,
    forecast_accuracy_penalty,
    growth_rate,
    seasonality_factor,
    stock_depletion_risk,
)
from .scoring import FACTOR_WEIGHTS, compute_risk

__all__ = [
    "compute_risk",
    "FACTOR_WEIGHTS",
    "demand_volatility",
    "stock_depletion_risk",
    "forecast_accuracy_penalty",
    "seasonality_factor",
    "growth_rate",
]
