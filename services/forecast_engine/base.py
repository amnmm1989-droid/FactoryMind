# services/forecast_engine/base.py
"""
العقد الذي تلتزم به كل النماذج.

الفكرة: المحرك لا يعرف شيئاً عن ETS أو Prophet أو XGBoost — يعرف فقط
كائنات تُجيب على سؤالين: "هل تستطيع التعامل مع هذه السلسلة؟" و"ما تنبؤك؟".
إضافة نموذج سادس لا تتطلب لمس المحرك.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Sequence


@dataclass(frozen=True)
class ForecastOutput:
    """مخرج نموذج واحد: القيم وحدود الثقة. بلا مقاييس — تلك مسؤولية
    evaluation.py، لأن النموذج لا يقيّم نفسه."""
    values: list[float]
    lower: list[float]
    upper: list[float]

    def __post_init__(self) -> None:
        if not (len(self.values) == len(self.lower) == len(self.upper)):
            raise ValueError(
                f"أطوال غير متطابقة: values={len(self.values)} "
                f"lower={len(self.lower)} upper={len(self.upper)}"
            )


class Forecaster(ABC):
    """نموذج تنبؤ واحد.

    min_points / min_non_zero: لماذا معياران لا واحد؟
    كل منتج في هذه البيانات له 44 نقطة شهرية بالضبط — لكن الوسيط 9 أشهر
    غير صفرية فقط. طول السلسلة وحده يقول إن كل المنتجات صالحة لـ SARIMA،
    وهذا خطأ: تدريب نموذج موسمي على 40 صفراً و4 قيم يُنتج رقماً بلا معنى،
    لكنه رقم — يبدو كإجابة ويُتَّخذ عليه قرار إنتاج.
    """

    name: str = "base"
    min_points: int = 1       # الحد الأدنى لطول السلسلة
    min_non_zero: int = 1     # الحد الأدنى للنقاط غير الصفرية

    def can_handle(self, series: Sequence[float]) -> bool:
        """هل تكفي هذه السلسلة لتدريب هذا النموذج؟

        المحرك يستدعيها قبل التدريب ويتخطّى ما لا ينطبق — التخطّي الصريح
        أفضل من نموذج يُدرَّب على بيانات لا تكفيه ثم يُرجع ضجيجاً.
        """
        if len(series) < self.min_points:
            return False
        non_zero = sum(1 for value in series if value != 0)
        return non_zero >= self.min_non_zero

    @abstractmethod
    def fit_predict(self, series: Sequence[float], steps: int) -> ForecastOutput:
        """تدريب وتنبؤ بخطوة واحدة.

        Raises:
            ModelTrainingError: إذا فشل التدريب. لا تبتلع الخطأ ولا تُرجع
                بديلاً صامتاً — المحرك يقرر ماذا يفعل بالفشل، لا النموذج.
        """

    def __repr__(self) -> str:
        return f"<{type(self).__name__} name={self.name}>"
