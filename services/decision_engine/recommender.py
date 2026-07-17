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
    ReasonPart,
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
    متقطّعة (وسيط كتالوج التحقّق: 9 أشهر غير صفرية من 44)، فآخر 3 أشهر أصفار
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


def _build_reason_parts(
    forecast: ForecastResult,
    risk: RiskScore,
    change_pct: float,
    baseline: float,
    available: float | None,
) -> tuple[ReasonPart, ...]:
    """أجزاء السبب كبيانات — يجب أن تحمل ما يكفي لمراجعة القرار، لا لتزيينه.

    رموز لا نصوص: الواجهة تترجمها (ui/i18n.format_reason)، والنص العربي
    يُشتقّ منها في _reason_text للسجل والتخزين.
    """
    parts: list[ReasonPart] = []

    if baseline <= 0:
        parts.append(ReasonPart("no_baseline"))
    elif abs(change_pct) < ProductionRecommendation.STABLE_THRESHOLD_PCT:
        parts.append(ReasonPart("stable"))
    else:
        parts.append(ReasonPart(
            "rise" if change_pct > 0 else "fall", {"pct": abs(change_pct)}
        ))

    if available is not None and available > 0:
        parts.append(ReasonPart("stock_deducted", {"units": available}))

    parts.append(ReasonPart("model", {"name": forecast.model_name}))

    # الشفافية عن جودة الأساس: توصية مبنية على تنبؤ غير مُقيَّم أو ضعيف
    # الدقة يجب أن تقول ذلك عن نفسها.
    if forecast.mape is not None:
        parts.append(ReasonPart("historical_error", {"pct": forecast.mape}))
    elif forecast.rmse is None:
        parts.append(ReasonPart("unevaluated"))

    parts.append(ReasonPart(
        "risk_level", {"level": risk.level.value, "score": risk.score}
    ))

    if risk.missing_factors:
        parts.append(ReasonPart("missing_factors", {"count": len(risk.missing_factors)}))

    return tuple(parts)


_REASON_AR = {
    "no_baseline": "لا مبيعات في الفترة المرجعية — التوصية من التنبؤ وحده",
    "stable": "الطلب المتوقع مستقر",
    "rise": "ارتفاع الطلب المتوقع بنسبة {pct:.1f}%",
    "fall": "انخفاض الطلب المتوقع بنسبة {pct:.1f}%",
    "stock_deducted": "بعد خصم {units:,.0f} وحدة متاحة في المخزون",
    "model": "نموذج التنبؤ: {name}",
    "historical_error": "خطأ تاريخي {pct:.0f}%",
    "unevaluated": "لم يُقيَّم النموذج (بيانات غير كافية للاختبار)",
    "missing_factors": "عوامل غير محسوبة: {count} من 5",
}
_LEVEL_AR = {
    RiskLevel.LOW.value: "خطورة منخفضة",
    RiskLevel.MEDIUM.value: "خطورة متوسطة",
    RiskLevel.HIGH.value: "خطورة عالية",
}


def _reason_text(parts: tuple[ReasonPart, ...]) -> str:
    """النص العربي للسجل والتخزين.

    ثابت اللغة عمداً: سجل يتبدّل بلغة من صادف أن فتح الصفحة لا يصلح
    للمراجعة، وصفّ محفوظ في قاعدة البيانات يجب أن يعني الشيء نفسه بعد سنة.
    """
    rendered: list[str] = []
    for part in parts:
        if part.code == "risk_level":
            level = _LEVEL_AR[part.params["level"]]
            rendered.append(f"{level} ({part.params['score']:.0f}/100)")
        else:
            rendered.append(_REASON_AR[part.code].format(**part.params))
    return " | ".join(rendered)


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

    reason_parts = _build_reason_parts(forecast, risk, change_pct, baseline, available)
    recommendation = ProductionRecommendation(
        product_name=product_name,
        recommended_quantity=quantity,
        reason=_reason_text(reason_parts),
        expected_demand_change_pct=change_pct,
        risk=risk,
        reason_parts=reason_parts,
    )

    logger.info(
        "Recommendation | product=%s | qty=%.0f | change=%.1f%% | risk=%.0f (%s) | model=%s",
        product_name, quantity, change_pct, risk.score, risk.level.value, forecast.model_name,
    )
    return recommendation
