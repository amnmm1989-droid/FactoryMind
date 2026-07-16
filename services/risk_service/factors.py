# services/risk_service/factors.py
"""
حساب عوامل الخطورة الخمسة، كلٌ على مقياس 0-100.

مبدأ حاكم لكل دالة هنا: تُرجع None حين لا تملك ما يكفي، ولا تخترع رقماً.
عامل مجهول يُعرَض كمجهول؛ الصفر محجوز لمعناه الحقيقي — "قِسنا، ولا خطورة".

التوحيد على 0-100 عبر دالة إشباع (saturation) لا قصّ (clipping):
القصّ يجعل كل تقلب فوق العتبة متساوياً (CV=2 و CV=10 كلاهما 100)، بينما
الإشباع يحفظ الترتيب مهما تطرّفت القيمة. وبيانات هذا المشروع متطرّفة فعلاً
(رأينا معامل اختلاف 336%).
"""
from __future__ import annotations

from typing import Sequence

import numpy as np

from domain.entities import ForecastResult, InventoryStatus

# نقاط المنتصف: القيمة التي تُترجم إلى خطورة 50. معايرة قابلة للضبط،
# وهي أهم أرقام هذا الملف — تغييرها يغيّر كل الدرجات.
CV_MIDPOINT = 1.0            # معامل اختلاف = 1 (الانحراف = المتوسط) -> 50
GROWTH_MIDPOINT = 0.5        # تغيّر سنوي = 50% من المتوسط -> 50
MAPE_MIDPOINT = 30.0         # خطأ تنبؤ 30% -> 50

MIN_POINTS_FOR_SEASONALITY = 24  # دورتان — أقل من ذلك لا يُميّز الموسمية من الضجيج
SEASONAL_PERIOD = 12


def _saturate(value: float, midpoint: float) -> float:
    """تحويل قيمة موجبة غير مسقوفة إلى 0-100، حيث midpoint -> 50.

    100 * v / (v + m): تقترب من 100 ولا تبلغها. لا فقدان ترتيب عند التطرّف.
    """
    if value <= 0:
        return 0.0
    return float(100.0 * value / (value + midpoint))


def demand_volatility(series: Sequence[float]) -> float | None:
    """تقلب الطلب من معامل الاختلاف (الانحراف المعياري / المتوسط).

    None حين تقلّ النقاط عن اثنتين — انحراف معياري لنقطة واحدة بلا معنى.
    0 لمنتج بلا مبيعات قط: لا طلب، فلا تقلب فيه. (وخطورته الحقيقية —
    منتج ميت — سؤال آخر لا يجيب عنه هذا العامل.)
    """
    values = np.asarray(series, dtype=float)
    if len(values) < 2:
        return None

    mean = float(np.mean(values))
    if mean == 0:
        return 0.0

    cv = float(np.std(values)) / abs(mean)
    return _saturate(cv, CV_MIDPOINT)


def growth_rate(series: Sequence[float]) -> float | None:
    """خطورة معدّل التغيّر — بالقيمة المطلقة.

    لماذا المطلقة؟ العامل يقيس *خطورة التخطيط* لا جودة الأعمال. نمو 40%
    وانكماش 40% كلاهما يجعل الشهر القادم مختلفاً عن أمس، وكلاهما يُغري
    بإنتاج خاطئ. الاتجاه (صعود أم هبوط) يحمله
    ProductionRecommendation.expected_demand_change_pct بإشارته.
    """
    values = np.asarray(series, dtype=float)
    if len(values) < 3:
        return None

    mean = float(np.mean(values))
    if mean == 0:
        return 0.0

    from models.statistics import trend_analysis

    slope = float(trend_analysis(list(values))["slope"])
    # الميل شهري -> نُسنِّته ونعبّر عنه كنسبة من المتوسط
    annual_relative_change = abs(slope) * 12.0 / abs(mean)
    return _saturate(annual_relative_change, GROWTH_MIDPOINT)


def seasonality_factor(series: Sequence[float]) -> float | None:
    """قوة النمط الموسمي: نسبة التباين الذي يفسّره الشهر من السنة.

    موسمية عالية = خطورة تخطيط أعلى: الطلب يقفز ويهوي بحسب الشهر، وخطأ
    التوقيت يعني مخزوناً راكداً أو نفاداً في الذروة.

    None تحت 24 نقطة: بدورة واحدة لا يمكن تمييز "موسمية" من "حدث لمرة".
    """
    values = np.asarray(series, dtype=float)
    if len(values) < MIN_POINTS_FOR_SEASONALITY:
        return None

    total_variance = float(np.var(values))
    if total_variance == 0:
        return 0.0  # سلسلة ثابتة تماماً: لا موسمية

    # متوسط كل شهر من السنة عبر كل الدورات
    month_means = [
        float(np.mean(values[month::SEASONAL_PERIOD]))
        for month in range(SEASONAL_PERIOD)
        if len(values[month::SEASONAL_PERIOD]) > 0
    ]
    seasonal_variance = float(np.var(month_means))

    # نسبة التباين الموسمي إلى الكلي (0-1) -> 0-100
    ratio = min(seasonal_variance / total_variance, 1.0)
    return float(ratio * 100.0)


def forecast_accuracy_penalty(
    forecast: ForecastResult, series: Sequence[float]
) -> float | None:
    """عقوبة عدم دقة التنبؤ.

    التنبؤ الذي أخطأ تاريخياً بـ 40% يجعل أي قرار مبني عليه أخطر — بغضّ
    النظر عن جودة المنتج نفسه.

    MAPE أولاً (نسبة، قابلة للمقارنة بين المنتجات). عند غيابه — وهو شائع
    هنا لأن MAPE يحتاج قيماً غير صفرية — نشتقّ بديلاً من RMSE منسوباً
    إلى المتوسط. عند غياب الاثنين: None، فالنموذج لم يُقيَّم أصلاً.
    """
    if forecast.mape is not None:
        return _saturate(float(forecast.mape), MAPE_MIDPOINT)

    if forecast.rmse is not None:
        values = np.asarray(series, dtype=float)
        mean = float(np.mean(values))
        if mean > 0:
            normalized_rmse = float(forecast.rmse) / mean * 100.0
            return _saturate(normalized_rmse, MAPE_MIDPOINT)

    return None


def stock_depletion_risk(
    inventory: InventoryStatus | None,
    forecast: ForecastResult,
) -> float | None:
    """خطورة نفاد المخزون قبل وصول الدفعة التالية.

    None حين لا نعرف المخزون — وهو الوضع الافتراضي حتى Phase 5 تملأ جدول
    inventory. هذا هو الفارق الذي يستحق التشدد: 0 يعني "المخزون يغطي
    الطلب"، وNone يعني "لا نعرف كم لديك". منتج مجهول المخزون ليس آمناً؛
    هو مجهول. وإعطاؤه 0 يجعله يبدو الأكثر أماناً في قائمة مرتّبة.
    """
    if inventory is None:
        return None

    if inventory.stockout_risk:
        return 100.0  # المخزون عند حد الأمان أو تحته

    # الطلب المتوقع خلال مهلة التوريد
    lead_time_months = max(inventory.lead_time_days / 30.0, 0.0)
    if lead_time_months == 0 or not forecast.forecast_values:
        # بلا مهلة توريد لا يوجد خطر نفاد أثناء الانتظار
        return 0.0 if inventory.current_stock > inventory.reorder_point else 100.0

    monthly_demand = float(np.mean(forecast.forecast_values))
    demand_during_lead_time = monthly_demand * lead_time_months
    if demand_during_lead_time <= 0:
        return 0.0  # لا طلب متوقع -> لا نفاد

    coverage = inventory.current_stock / demand_during_lead_time
    # تغطية >= 1 -> الطلب مغطّى -> 0. تغطية 0 -> 100.
    return float(max(0.0, (1.0 - min(coverage, 1.0)) * 100.0))
