# services/decision_engine/recommender.py
"""
تحويل تنبؤ إلى توصية إنتاج.

الفرق بين الاثنين ليس شكلياً: التنبؤ يقول "الطلب المتوقع 240 وحدة"،
والتوصية تقول "أنتج 190" — لأن لديك 50 في المخزون. التنبؤ وصف، التوصية قرار.
"""
from __future__ import annotations

from typing import Sequence

import numpy as np

from core.exceptions import DecisionEngineError
from core.logging_config import get_logger
from domain.entities import (
    ForecastResult,
    InventoryStatus,
    ProductionRecommendation,
    RiskLevel,
    RiskScore,
)
from services.risk_service import compute_risk

logger = get_logger(__name__)

# عدد الأشهر الأخيرة التي تُقارن بها التوقعات لقياس التغيّر.
#
# ملاحظة على اقتران بنيوي: النموذج الفائز على معظم منتجات هذا المشروع هو
# MovingAverage بنافذة 3 (انظر معيار Phase 3). حين يفوز، يكون التنبؤ =
# متوسط آخر 3 أشهر = المرجع بالضبط، فيصبح التغيّر صفراً حتماً.
#
# هذا ليس عيباً يُخفى بتغيير النافذة: النموذج *فعلاً* يتنبأ بأن الشهر
# القادم كالأشهر الماضية. صفر هو تنبؤه الصادق. المرجع الأطول (12 شهراً)
# كان سيُظهر رقماً غير صفري، لكنه يجيب سؤالاً آخر ("مقارنة بالسنة")
# ويوهم بأن النموذج يرى تغيّراً لا يراه.
BASELINE_MONTHS = 3


def _baseline_demand(series: Sequence[float]) -> float:
    """متوسط الطلب المرجعي الذي يُقاس عليه التغيّر.

    آخر 3 أشهر أولاً — الأقرب زمنياً أدلّ على الوضع الحالي. لكن هذه بيانات
    متقطّعة (وسيط 9 أشهر غير صفرية من 44)، فآخر 3 أشهر قد تكون أصفاراً
    لمنتج نشط. عندها نتراجع إلى متوسط السلسلة كاملة بدل إعلان "نمو لانهائي".
    """
    values = np.asarray(series, dtype=float)
    if len(values) == 0:
        return 0.0

    recent = values[-BASELINE_MONTHS:]
    recent_mean = float(np.mean(recent))
    if recent_mean > 0:
        return recent_mean

    overall_mean = float(np.mean(values))
    return overall_mean if overall_mean > 0 else 0.0


def _demand_change_pct(forecast_value: float, baseline: float) -> float:
    """نسبة تغيّر الطلب المتوقع عن المرجع.

    مرجع صفري: النسبة رياضياً غير معرّفة (قسمة على صفر). نُرجع 0.0 بدل
    inf — والسياق يُذكر في نص السبب. رقم لانهائي في رسالة لمدير إنتاج
    ليس معلومة.
    """
    if baseline <= 0:
        return 0.0
    return float((forecast_value - baseline) / baseline * 100.0)


def _available_stock(inventory: InventoryStatus | None) -> float | None:
    """المخزون القابل للاستهلاك = الحالي ناقص مخزون الأمان.

    مخزون الأمان ليس متاحاً للتخطيط — هذا معناه. خصمه من الحساب يمنع
    توصية تستهلكه، فيبقى لما وُجد لأجله: الصدمات.
    """
    if inventory is None:
        return None
    return max(0.0, inventory.current_stock - inventory.safety_stock)


def _build_reason(
    forecast: ForecastResult,
    risk: RiskScore,
    change_pct: float,
    baseline: float,
    available: float | None,
) -> str:
    """نص السبب — يجب أن يحمل ما يكفي لمراجعة القرار، لا لتزيينه."""
    parts: list[str] = []

    if baseline <= 0:
        parts.append("لا مبيعات في الفترة المرجعية — التوصية من التنبؤ وحده")
    elif abs(change_pct) < ProductionRecommendation.STABLE_THRESHOLD_PCT:
        parts.append("الطلب المتوقع مستقر")
    else:
        direction = "ارتفاع" if change_pct > 0 else "انخفاض"
        parts.append(f"{direction} الطلب المتوقع بنسبة {abs(change_pct):.1f}%")

    if available is not None and available > 0:
        parts.append(f"بعد خصم {available:,.0f} وحدة متاحة في المخزون")

    parts.append(f"نموذج التنبؤ: {forecast.model_name}")

    # الشفافية عن جودة الأساس: توصية مبنية على تنبؤ غير مُقيَّم أو ضعيف
    # الدقة يجب أن تقول ذلك عن نفسها.
    if forecast.mape is not None:
        parts.append(f"خطأ تاريخي {forecast.mape:.0f}%")
    elif forecast.rmse is None:
        parts.append("لم يُقيَّم النموذج (بيانات غير كافية للاختبار)")

    level_text = {
        RiskLevel.LOW: "خطورة منخفضة",
        RiskLevel.MEDIUM: "خطورة متوسطة",
        RiskLevel.HIGH: "خطورة عالية",
    }[risk.level]
    parts.append(f"{level_text} ({risk.score:.0f}/100)")

    if risk.missing_factors:
        parts.append(f"عوامل غير محسوبة: {len(risk.missing_factors)} من 5")

    return " | ".join(parts)


def recommend_production(
    product_name: str,
    series: Sequence[float],
    forecast: ForecastResult,
    inventory: InventoryStatus | None = None,
    *,
    horizon_months: int = 1,
) -> ProductionRecommendation:
    """توليد توصية إنتاج من تنبؤ.

    الكمية = الطلب المتوقع خلال الأفق، ناقص المخزون المتاح (إن عُرف).

    ⚠️ التوصية لا تكون أدق من التنبؤ خلفها. على هذه البيانات، الفائز غالباً
    متوسط متحرك — أي أن "الطلب المتوقع" في جوهره "مثل الأشهر الماضية".
    نص السبب يحمل اسم النموذج وخطأه التاريخي كي لا يُقرأ الرقم كنبوءة.

    Raises:
        DecisionEngineError: تنبؤ فارغ أو أفق غير صالح.
    """
    if not forecast.forecast_values:
        raise DecisionEngineError(
            "تنبؤ بلا قيم — لا أساس لتوصية",
            context={"product": product_name},
        )
    if horizon_months < 1:
        raise DecisionEngineError(
            f"أفق غير صالح: {horizon_months}",
            context={"product": product_name, "horizon": horizon_months},
        )
    if horizon_months > len(forecast.forecast_values):
        raise DecisionEngineError(
            f"الأفق المطلوب ({horizon_months}) يتجاوز التنبؤ المتاح "
            f"({len(forecast.forecast_values)} شهراً)",
            context={"product": product_name},
        )

    risk = compute_risk(product_name, series, forecast, inventory)

    expected_demand = float(sum(forecast.forecast_values[:horizon_months]))
    available = _available_stock(inventory)
    quantity = expected_demand if available is None else max(0.0, expected_demand - available)

    baseline = _baseline_demand(series)
    change_pct = _demand_change_pct(float(forecast.forecast_values[0]), baseline)

    recommendation = ProductionRecommendation(
        product_name=product_name,
        recommended_quantity=quantity,
        reason=_build_reason(forecast, risk, change_pct, baseline, available),
        expected_demand_change_pct=change_pct,
        risk=risk,
    )

    logger.info(
        "Recommendation | product=%s | qty=%.0f | change=%.1f%% | risk=%.0f (%s) | model=%s",
        product_name, quantity, change_pct, risk.score, risk.level.value, forecast.model_name,
    )
    return recommendation
