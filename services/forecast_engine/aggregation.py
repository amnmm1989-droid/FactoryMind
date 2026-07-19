# services/forecast_engine/aggregation.py
"""
ADIDA — Aggregate-Disaggregate Intermittent Demand Approach.

## الفكرة

السلسلة المتقطّعة فقيرة الإشارة عند حبيبتها الأصلية: ملف يومي في هذا
المشروع 95% أصفار، وأسبوعي 87%. السؤال "كم في هذا اليوم بعينه؟" لا جواب
له — ليس لضعف النموذج بل لأن البيانات لا تحمله.

ADIDA يغيّر السؤال بدل أن يجتهد في الإجابة الخاطئة:

    1. **تجميع**: اجمع السلسلة في دلاء بحجم k (يوميّ -> أسبوعيّ مثلاً).
       الأصفار تبتلعها الدلاء، فتظهر الإشارة.
    2. **تنبؤ**: درّب النموذج الأساسي على السلسلة المجمَّعة — حيث الإشارة.
    3. **تفكيك**: وزّع تنبؤ الدلو على فتراته الأصلية.

## الكلفة — رخيص بنيوياً، لا بالصدفة

السلسلة المجمَّعة **أقصر** من الأصلية (n/k نقطة)، فالنموذج الأساسي يعمل
على بيانات أقل لا أكثر. والتجميع/التفكيك عمليتان خطّيتان O(n) على مصفوفات
numpy. مع Croston أساساً (قِيس بـ~0 ms)، تبقى الكلفة الكلية ~0 ms.

## اختيار حجم الدلو

k = round(ADI) — متوسط الفترة بين الطلبات. المنطق: دلوٌ بحجم متوسط الفجوة
يحوي طلباً واحداً تقريباً، فتتحوّل السلسلة المتقطّعة إلى شبه متصلة. هذه
الاستدلالة القياسية في الأدبيات، ومقيَّدة هنا بحدّين:
  - k >= 2: التجميع بواحد ليس تجميعاً.
  - k بحيث تبقى للنموذج الأساسي نقاط تكفيه (len // base.min_points).

## نطاقه

للطلب المتقطّع/المتكتّل وحده. على الطلب المنتظم لا يضيف شيئاً — الإشارة
ظاهرة أصلاً، والتجميع يطمس تفاصيلها. `can_handle` يفرض ذلك صراحةً.
"""
from __future__ import annotations

import math
from typing import Sequence

import numpy as np

from core.exceptions import ModelTrainingError

from .base import Forecaster, ForecastOutput
from .intermittent import CrostonForecaster, classify_demand


def aggregate_series(values: np.ndarray, bucket: int) -> np.ndarray:
    """تجميع غير متداخل، محاذى إلى **النهاية**.

    المحاذاة للنهاية لا للبداية: البقية الناقصة تُقتطع من أقدم البيانات،
    فتبقى أحدث الفترات في دلاء كاملة. العكس كان سيجعل آخر دلو ناقصاً —
    أي مجموعاً أصغر من حقّه — فيهبط التنبؤ لسبب حسابي بحت.
    """
    usable = (len(values) // bucket) * bucket
    trimmed = values[len(values) - usable:]
    return trimmed.reshape(-1, bucket).sum(axis=1)


class ADIDAForecaster(Forecaster):
    """ADIDA فوق نموذج أساسي (Croston افتراضاً)."""

    name = "ADIDA"
    # يحتاج طولاً يكفي للتجميع *ثم* تدريب الأساس على الناتج
    min_points = 12
    min_non_zero = 3

    def __init__(self, base: Forecaster | None = None, bucket: int | None = None) -> None:
        self.base = base if base is not None else CrostonForecaster()
        self.bucket = bucket  # None = يُشتقّ من ADI

    def _bucket_for(self, values: np.ndarray) -> int:
        """حجم الدلو، أو 0 إن تعذّر تجميع مفيد."""
        if self.bucket is not None:
            candidate = self.bucket
        else:
            candidate = int(round(classify_demand(values).adi))

        # لا تُجمّع أكثر مما يترك للنموذج الأساسي نقاطاً تكفيه
        largest_useful = len(values) // max(self.base.min_points, 1)
        if largest_useful < 2:
            return 0
        return max(2, min(candidate, largest_useful))

    def can_handle(self, series: Sequence[float]) -> bool:
        if not super().can_handle(series):
            return False
        values = np.asarray(series, dtype=float)
        # ADIDA أداة الطلب المتقطّع: على المنتظم يطمس تفاصيل ظاهرة أصلاً
        if not classify_demand(values).is_intermittent:
            return False
        return self._bucket_for(values) >= 2

    def fit_predict(self, series: Sequence[float], steps: int) -> ForecastOutput:
        values = np.asarray(series, dtype=float)
        bucket = self._bucket_for(values)
        if bucket < 2:
            raise ModelTrainingError(
                f"لا حجم دلو مفيد لـ ADIDA ({len(values)} نقطة)",
                context={"model": self.name, "points": len(values)},
            )

        aggregated = aggregate_series(values, bucket)
        if not self.base.can_handle(aggregated.tolist()):
            raise ModelTrainingError(
                f"السلسلة المجمَّعة ({len(aggregated)} نقطة) لا تكفي "
                f"{self.base.name}",
                context={"model": self.name, "bucket": bucket},
            )

        aggregated_steps = math.ceil(steps / bucket)
        output = self.base.fit_predict(aggregated.tolist(), aggregated_steps)

        def disaggregate(sequence: list[float]) -> list[float]:
            """توزيع متساوٍ: قيمة الدلو ÷ حجمه لكل فترة داخله.

            التوزيع المتساوي هو صيغة ADIDA القياسية — وهو الصادق هنا: لا
            نعرف *أي* يوم داخل الأسبوع سيقع فيه الطلب، وادّعاء توزيع غير
            متساوٍ يخترع معلومة لا تحملها البيانات.
            """
            spread = [value / bucket for value in sequence for _ in range(bucket)]
            return spread[:steps]

        return ForecastOutput(
            values=disaggregate(output.values),
            lower=disaggregate(output.lower),
            upper=disaggregate(output.upper),
        )
