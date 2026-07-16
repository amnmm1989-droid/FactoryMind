# services/forecast_engine/intermittent.py
"""
الطلب المتقطّع: التصنيف + Croston/SBA/TSB.

لماذا هذا الملف موجود: 84% من كتالوج هذا المشروع متقطّع أو متكتّل
(تصنيف Syntetos-Boylan-Croston). النماذج السبعة السابقة كلها مصمَّمة
للطلب المنتظم — أي لـ 14% منه.

الفكرة المركزية في Croston (1972): السلسلة المتقطّعة ليست سلسلة واحدة
بل سلسلتان متشابكتان —
  1. *أحجام* الطلب حين يحدث (50، 80، 60...)
  2. *الفترات* بين حدوثه (كل 3 أشهر، كل شهرين...)
تنبّأ بكلٍ على حدة، والمعدّل = الحجم ÷ الفترة.

التنبؤ الناتج معدّل ثابت (مثلاً 18 وحدة/شهر)، لا قيمة شهر بعينه. وهذا
مقصود: على طلب يظهر كل 3 أشهر، السؤال "كم في مارس تحديداً؟" لا جواب له،
والسؤال المفيد "كم إجمالاً في الربع القادم؟" له جواب.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Sequence

import numpy as np

from config import CONFIDENCE_LEVEL
from core.exceptions import ModelTrainingError

from .base import Forecaster, ForecastOutput

# عتبات تصنيف Syntetos-Boylan-Croston (2005) — مستقرّة في الأدبيات
ADI_CUTOFF = 1.32   # متوسط الفترة بين الطلبات
CV2_CUTOFF = 0.49   # مربع معامل اختلاف أحجام الطلب


class DemandClass(str, Enum):
    """تصنيف نمط الطلب — يحدد أي عائلة نماذج تناسبه."""

    SMOOTH = "smooth"              # منتظم: ETS/SARIMA/Prophet في مجالها
    ERRATIC = "erratic"            # متذبذب: يحدث غالباً، لكن بأحجام متقلبة
    INTERMITTENT = "intermittent"  # متقطّع: فجوات كثيرة، أحجام متماسكة -> Croston
    LUMPY = "lumpy"                # متكتّل: فجوات وأحجام متقلبة -> الأصعب
    DEAD = "dead"                  # بلا مبيعات قط

    @property
    def is_intermittent(self) -> bool:
        """هل يحتاج طرق الطلب المتقطّع (ومقياس تقييم مختلف)؟"""
        return self in (DemandClass.INTERMITTENT, DemandClass.LUMPY)


@dataclass(frozen=True)
class DemandProfile:
    """توصيف كمّي لنمط الطلب."""

    demand_class: DemandClass
    adi: float          # متوسط الفترة بين الطلبات (1.0 = كل شهر)
    cv_squared: float   # تقلب أحجام الطلب غير الصفري
    non_zero_count: int

    @property
    def is_intermittent(self) -> bool:
        return self.demand_class.is_intermittent


def classify_demand(series: Sequence[float]) -> DemandProfile:
    """تصنيف نمط الطلب بمعياري ADI و CV².

    ADI = عدد الفترات ÷ عدد الطلبات. قيمة 1.0 تعني طلباً كل شهر؛ 4.0
    تعني مرة كل أربعة أشهر.
    CV² = تقلب *أحجام* الطلب حين يحدث — يُحسب على القيم غير الصفرية وحدها.
    خلط الأصفار فيه كان سيقيس التقطّع مرتين بدل قياس التقلب.
    """
    values = np.asarray(series, dtype=float)
    non_zero = values[values > 0]

    if len(non_zero) == 0:
        return DemandProfile(
            demand_class=DemandClass.DEAD, adi=float("inf"), cv_squared=0.0, non_zero_count=0
        )

    adi = len(values) / len(non_zero)
    mean_size = float(np.mean(non_zero))
    cv_squared = float((np.std(non_zero) / mean_size) ** 2) if mean_size > 0 else 0.0

    if adi < ADI_CUTOFF:
        demand_class = DemandClass.SMOOTH if cv_squared < CV2_CUTOFF else DemandClass.ERRATIC
    else:
        demand_class = (
            DemandClass.INTERMITTENT if cv_squared < CV2_CUTOFF else DemandClass.LUMPY
        )

    return DemandProfile(
        demand_class=demand_class,
        adi=float(adi),
        cv_squared=cv_squared,
        non_zero_count=len(non_zero),
    )


def _rate_interval(rate: float, non_zero: np.ndarray) -> tuple[list[float], list[float]]:
    """حدود ثقة حول معدّل ثابت، مشتقّة من تقلب أحجام الطلب."""
    spread = float(np.std(non_zero)) if len(non_zero) > 1 else rate * 0.5
    margin = CONFIDENCE_LEVEL * spread
    return [max(rate - margin, 0.0)], [rate + margin]


class CrostonForecaster(Forecaster):
    """Croston (1972) مع تصحيح Syntetos-Boylan اختيارياً.

    التقدير الأصلي متحيّز إلى الأعلى — أثبت Syntetos و Boylan (2001) أن
    z/p يبالغ في المعدّل بعامل ~(1 - α/2). SBA يصحّحه، وهو الافتراضي هنا:
    مبالغة منهجية في تقدير الطلب تعني مخزوناً راكداً منهجياً.

    التحديث يحدث *فقط* عند وقوع طلب — هذا جوهر Croston. الأشهر الصفرية
    لا تُحدّث التقدير، بل تُطيل عدّاد الفترة فحسب.
    """

    name = "Croston"
    min_points = 4
    min_non_zero = 2  # طلبان على الأقل — الفترة تحتاج فارقاً لتُقاس

    def __init__(self, alpha: float = 0.1, use_sba: bool = True) -> None:
        if not 0 < alpha <= 1:
            raise ValueError(f"alpha خارج المجال (0, 1]: {alpha}")
        self.alpha = alpha
        self.use_sba = use_sba

    def fit_predict(self, series: Sequence[float], steps: int) -> ForecastOutput:
        values = np.asarray(series, dtype=float)
        non_zero_idx = np.flatnonzero(values > 0)

        if len(non_zero_idx) < self.min_non_zero:
            raise ModelTrainingError(
                f"طلبات غير كافية لـ Croston: {len(non_zero_idx)}",
                context={"model": self.name},
            )

        # التهيئة من أول طلب، والفترة من متوسط الفواصل الفعلية
        size_estimate = float(values[non_zero_idx[0]])
        intervals = np.diff(non_zero_idx)
        interval_estimate = float(np.mean(intervals)) if len(intervals) > 0 else 1.0

        periods_since_demand = 1
        for index in range(non_zero_idx[0] + 1, len(values)):
            if values[index] > 0:
                size_estimate = self.alpha * values[index] + (1 - self.alpha) * size_estimate
                interval_estimate = (
                    self.alpha * periods_since_demand + (1 - self.alpha) * interval_estimate
                )
                periods_since_demand = 1
            else:
                periods_since_demand += 1

        if interval_estimate <= 0:
            raise ModelTrainingError(
                "تقدير فترة غير صالح", context={"model": self.name}
            )

        rate = size_estimate / interval_estimate
        if self.use_sba:
            # تصحيح Syntetos-Boylan للتحيّز
            rate *= 1 - self.alpha / 2

        rate = max(rate, 0.0)
        if not np.isfinite(rate):
            raise ModelTrainingError(
                "Croston أنتج معدّلاً غير منتهٍ", context={"model": self.name}
            )

        lower, upper = _rate_interval(rate, values[non_zero_idx])
        return ForecastOutput(
            values=[rate] * steps, lower=lower * steps, upper=upper * steps
        )


class TSBForecaster(Forecaster):
    """Teunter-Syntetos-Babai (2011).

    الفرق الحاسم عن Croston: يحدّث *احتمال* وقوع الطلب في **كل** فترة، لا
    عند وقوع الطلب فقط.

    لماذا يهم هنا: Croston لا يلاحظ منتجاً يموت. سلسلة تنتهي بعشرة أصفار
    متتالية تُبقي تقدير Croston عند آخر معدّل عرفه — لأن الأصفار لا تُحدّث
    شيئاً. TSB يرى الأصفار ويُنزل الاحتمال تدريجياً. وبيانات هذا المشروع
    مليئة بمنتجات تنتهي بأصفار (مسألة التقادم/obsolescence).
    """

    name = "TSB"
    min_points = 4
    min_non_zero = 2

    def __init__(self, alpha: float = 0.1, beta: float = 0.05) -> None:
        if not 0 < alpha <= 1:
            raise ValueError(f"alpha خارج المجال (0, 1]: {alpha}")
        if not 0 < beta <= 1:
            raise ValueError(f"beta خارج المجال (0, 1]: {beta}")
        self.alpha = alpha
        self.beta = beta  # أبطأ من alpha عمداً: الاحتمال يجب ألا يقفز لشهر واحد

    def fit_predict(self, series: Sequence[float], steps: int) -> ForecastOutput:
        values = np.asarray(series, dtype=float)
        non_zero_idx = np.flatnonzero(values > 0)

        if len(non_zero_idx) < self.min_non_zero:
            raise ModelTrainingError(
                f"طلبات غير كافية لـ TSB: {len(non_zero_idx)}",
                context={"model": self.name},
            )

        size_estimate = float(values[non_zero_idx[0]])
        probability = len(non_zero_idx) / len(values)

        for index in range(non_zero_idx[0] + 1, len(values)):
            if values[index] > 0:
                size_estimate = self.alpha * values[index] + (1 - self.alpha) * size_estimate
                probability = self.beta * 1.0 + (1 - self.beta) * probability
            else:
                # الأصفار تُحدّث الاحتمال — هذا ما لا يفعله Croston
                probability = self.beta * 0.0 + (1 - self.beta) * probability

        rate = max(probability * size_estimate, 0.0)
        if not np.isfinite(rate):
            raise ModelTrainingError(
                "TSB أنتج معدّلاً غير منتهٍ", context={"model": self.name}
            )

        lower, upper = _rate_interval(rate, values[non_zero_idx])
        return ForecastOutput(
            values=[rate] * steps, lower=lower * steps, upper=upper * steps
        )
