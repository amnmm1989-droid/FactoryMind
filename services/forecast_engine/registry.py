# services/forecast_engine/registry.py
"""
سجل النماذج المتاحة.

الترتيب هنا ليس تجميلياً — إنه ترتيب الأفضلية حين تتساوى الأدلة أو تنعدم:
من الأبسط إلى الأعقد. حين لا يمكن تقييم أي نموذج (سلسلة أقصر من أن تُقسَّم
إلى تدريب واختبار)، يختار المحرك الأول القادر على العمل. أي: بلا دليل على
أن التعقيد يفيد، لا نشتريه.
"""
from __future__ import annotations

from typing import Sequence

from .base import Forecaster
from .naive import MovingAverageForecaster, NaiveForecaster
from .prophet_model import ProphetForecaster
from .statistical import ETSForecaster, SARIMAForecaster
from .tree import RandomForestForecaster, XGBoostForecaster


def default_models() -> list[Forecaster]:
    """كل النماذج، مرتبة من الأبسط إلى الأعقد."""
    return [
        NaiveForecaster(),
        MovingAverageForecaster(),
        ETSForecaster(),
        SARIMAForecaster(),
        ProphetForecaster(),
        XGBoostForecaster(),
        RandomForestForecaster(),
    ]


def applicable_models(series: Sequence[float], models: list[Forecaster] | None = None) -> list[Forecaster]:
    """النماذج التي تكفيها هذه السلسلة."""
    candidates = models if models is not None else default_models()
    return [model for model in candidates if model.can_handle(series)]
