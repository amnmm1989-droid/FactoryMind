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
from .reference import point_forecast

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
    """Croston (1972) — مفوَّضاً إلى `statsforecast`.

    كان منفَّذاً يدوياً هنا. أُزيل التنفيذ لأن المكتبة المرجعية تقدّمه:
    لا نُعيد بناء ما هو متاح وموثوق.

    ثلاث صيغ تختارها المكتبة عنّا:
      - `CrostonSBA` (الافتراضي): بتصحيح Syntetos-Boylan للتحيّز. التقدير
        الأصلي يبالغ في المعدّل، ومبالغة منهجية تعني مخزوناً راكداً منهجياً.
      - `CrostonClassic`: الصيغة الأصلية بلا تصحيح.
      - `CrostonOptimized`: تُلائم معامل التنعيم بدل تثبيته عند 0.1 — قدرة
        لم تكن في تنفيذنا اليدوي أصلاً.

    ⚠️ لا معامل `alpha` بعد الآن: الصيغتان الكلاسيكية وSBA تثبّتانه عند 0.1
    في المكتبة، وقبولُ معاملٍ لا أثر له كذبٌ في الواجهة. استخدم
    `optimized=True` إن أردت ملاءمته.
    """

    name = "Croston"
    min_points = 4
    min_non_zero = 2  # طلبان على الأقل — الفترة تحتاج فارقاً لتُقاس

    def __init__(self, *, use_sba: bool = True, optimized: bool = False) -> None:
        self.use_sba = use_sba
        self.optimized = optimized

    def _model(self):
        from statsforecast.models import (
            CrostonClassic, CrostonOptimized, CrostonSBA,
        )

        if self.optimized:
            return CrostonOptimized()
        return CrostonSBA() if self.use_sba else CrostonClassic()

    def fit_predict(self, series: Sequence[float], steps: int) -> ForecastOutput:
        values = np.asarray(series, dtype=float)
        non_zero = values[values > 0]
        # الحارس يبقى عندنا: المكتبة تُرجع صفراً صامتاً على سلسلة بلا طلبات
        # كافية، والمحرك يحتاج تمييز "لا ينطبق" عن "توقّع صفراً".
        if len(non_zero) < self.min_non_zero:
            raise ModelTrainingError(
                f"طلبات غير كافية لـ Croston: {len(non_zero)}",
                context={"model": self.name},
            )

        forecast = point_forecast(self._model(), series, steps, name=self.name)
        lower, upper = _rate_interval(float(forecast[0]), non_zero)
        return ForecastOutput(
            values=forecast.tolist(), lower=lower * steps, upper=upper * steps
        )


class TSBForecaster(Forecaster):
    """Teunter-Syntetos-Babai (2011) — مفوَّضاً إلى `statsforecast`.

    الفرق الحاسم عن Croston: يحدّث *احتمال* وقوع الطلب في **كل** فترة، لا
    عند وقوعه فقط. ولهذا يلاحظ منتجاً يموت: سلسلة تنتهي بعشرة أصفار تُبقي
    تقدير Croston عند آخر معدّل عرفه، بينما يُنزل TSB الاحتمال تدريجياً.
    وبيانات هذا المشروع مليئة بمنتجات تنتهي بأصفار (التقادم).

    أسماء المعاملات تتبع المكتبة: `alpha_d` لأحجام الطلب، و`alpha_p`
    لاحتمال وقوعه — وهو أبطأ عمداً كي لا يقفز الاحتمال بفترة واحدة.
    """

    name = "TSB"
    min_points = 4
    min_non_zero = 2

    def __init__(self, alpha_d: float = 0.1, alpha_p: float = 0.05) -> None:
        for label, value in (("alpha_d", alpha_d), ("alpha_p", alpha_p)):
            if not 0 < value <= 1:
                raise ValueError(f"{label} خارج المجال (0, 1]: {value}")
        self.alpha_d = alpha_d
        self.alpha_p = alpha_p

    def fit_predict(self, series: Sequence[float], steps: int) -> ForecastOutput:
        from statsforecast.models import TSB

        values = np.asarray(series, dtype=float)
        non_zero = values[values > 0]
        if len(non_zero) < self.min_non_zero:
            raise ModelTrainingError(
                f"طلبات غير كافية لـ TSB: {len(non_zero)}",
                context={"model": self.name},
            )

        forecast = point_forecast(
            TSB(alpha_d=self.alpha_d, alpha_p=self.alpha_p),
            series, steps, name=self.name,
        )
        lower, upper = _rate_interval(float(forecast[0]), non_zero)
        return ForecastOutput(
            values=forecast.tolist(), lower=lower * steps, upper=upper * steps
        )
