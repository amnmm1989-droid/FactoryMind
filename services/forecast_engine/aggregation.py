# services/forecast_engine/aggregation.py
"""
ADIDA — Aggregate-Disaggregate Intermittent Demand Approach، مفوَّضاً إلى
`statsforecast`.

## الفكرة

السلسلة المتقطّعة فقيرة الإشارة عند حبيبتها الأصلية: الملف اليومي في هذا
المشروع 95% أصفار، والأسبوعي 87%. السؤال "كم في هذا اليوم بعينه؟" لا جواب
له — ليس لضعف النموذج بل لأن البيانات لا تحمله. ADIDA يغيّر السؤال: يجمّع
السلسلة في دلاء فتظهر الإشارة، يتنبّأ هناك، ثم يفكّك الناتج.

## لماذا لا تنفيذ يدوي هنا

كان مكتوباً في هذا الملف (اختيار حجم الدلو، التجميع المحاذى للنهاية،
التفكيك المتساوي). أُزيل كله: `statsforecast.ADIDA` ينفّذ الطريقة نفسها،
ولا نُعيد بناء ما هو متاح وموثوق. والمكتبة تقدّم معه `IMAPA` — تجميع على
عدة مستويات ومتوسطها — وهو ما لم يكن عندنا.

## ما بقي عندنا ولماذا

`can_handle` وحدها: **قصر ADIDA على الطلب المتقطّع/المتكتّل**. هذه سياسة
منتج لا خوارزمية — على الطلب المنتظم يطمس التجميع تفاصيل ظاهرة أصلاً،
وتشغيله هناك إنفاق حسابٍ حيث لا يفوز. المكتبة لا تعرف هذا القيد ولا يجب
أن تعرفه.
"""
from __future__ import annotations

from typing import Sequence

import numpy as np

from .base import Forecaster, ForecastOutput
from .intermittent import _rate_interval, classify_demand
from .reference import point_forecast


class ADIDAForecaster(Forecaster):
    """ADIDA للطلب المتقطّع — الحساب في `statsforecast`."""

    name = "ADIDA"
    # المكتبة تحتاج تاريخاً يكفي للتجميع ثم التنبؤ على الناتج
    min_points = 12
    min_non_zero = 3

    def can_handle(self, series: Sequence[float]) -> bool:
        if not super().can_handle(series):
            return False
        # سياسة المنتج لا الخوارزمية: التجميع يكسب إشارة حيث الفجوات كثيرة،
        # ولا يضيف شيئاً على طلب منتظم إشارتُه ظاهرة أصلاً.
        return classify_demand(series).is_intermittent

    def fit_predict(self, series: Sequence[float], steps: int) -> ForecastOutput:
        from statsforecast.models import ADIDA

        values = np.asarray(series, dtype=float)
        non_zero = values[values > 0]

        forecast = point_forecast(ADIDA(), series, steps, name=self.name)
        lower, upper = _rate_interval(float(forecast[0]), non_zero)
        return ForecastOutput(
            values=forecast.tolist(), lower=lower * steps, upper=upper * steps
        )
