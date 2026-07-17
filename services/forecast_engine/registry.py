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

import config

from .base import Forecaster
from .intermittent import CrostonForecaster, TSBForecaster
from .naive import MovingAverageForecaster, NaiveForecaster
from .prophet_model import ProphetForecaster
from .statistical import ETSForecaster, SARIMAForecaster
from .tree import RandomForestForecaster, XGBoostForecaster


def default_models(granularity: str = "monthly") -> list[Forecaster]:
    """كل النماذج، مرتبة من الأبسط إلى الأعقد.

    Croston و TSB بعد الأساس مباشرة: هما أبسط من العائلة الموسمية (معلَمان
    أو ثلاثة، بلا تدريب تكراري)، ويناسبان 84% من هذا الكتالوج. موقعهما
    المبكر يعني أنهما المرشّحان حين تنعدم الأدلة على سلسلة متقطّعة قصيرة.

    ETS/SARIMA/Prophet وحدها تحتاج granularity: دورتها الموسمية وfreq
    محورها الزمني يُشتقّان من حبيبة الملف الفعلية (config.
    SEASONAL_PERIODS_BY_GRANULARITY/PANDAS_FREQ_BY_GRANULARITY) لا من 12/
    "MS" ثابتتين. الباقي (Naive, MovingAverage, Croston, TSB, الأشجار)
    بلا مفهوم موسمي أصلاً — لا حاجة لتمرير الحبيبة إليها.
    """
    seasonal_periods = config.SEASONAL_PERIODS_BY_GRANULARITY[granularity]
    freq = config.PANDAS_FREQ_BY_GRANULARITY[granularity]
    return [
        NaiveForecaster(),
        MovingAverageForecaster(),
        CrostonForecaster(),
        TSBForecaster(),
        ETSForecaster(seasonal_periods=seasonal_periods, freq=freq),
        SARIMAForecaster(seasonal_periods=seasonal_periods, freq=freq),
        ProphetForecaster(
            freq=freq, seasonal_periods=seasonal_periods,
            daily=(granularity == "daily"),
        ),
        XGBoostForecaster(),
        RandomForestForecaster(),
    ]


def applicable_models(
    series: Sequence[float], models: list[Forecaster] | None = None,
    *, granularity: str = "monthly",
) -> list[Forecaster]:
    """النماذج التي تكفيها هذه السلسلة."""
    candidates = models if models is not None else default_models(granularity)
    return [model for model in candidates if model.can_handle(series)]
