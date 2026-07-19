# services/forecast_engine/reference.py
"""
الجسر الوحيد إلى `statsforecast` — الحساب هناك، وعقد Forecaster هنا.

## المبدأ

لا نُعيد بناء خوارزمية متاحة في مكتبة موثوقة مفتوحة المصدر. Croston و TSB
و ADIDA و ETS كلها منفَّذة في `statsforecast` (Nixtla) — مكتبة مرجعية واسعة
الاستخدام تنفّذ الأوراق نفسها التي كنّا ننفّذها يدوياً. فصار دورنا **الربط
لا الحساب**.

## ماذا يبقى عندنا ولماذا

الطبقة الرقيقة هنا ليست إعادة تنفيذ، بل ما لا تقدّمه المكتبة:

- **عقد `Forecaster`** الذي يعرفه المحرك (`can_handle` / `fit_predict`) —
  لولاه لعرف المحرك أسماء النماذج، وهو ما يتجنّبه `registry.py` عمداً.
- **تحويل الفشل** إلى `ModelTrainingError`: المحرك يميّز "فشل التدريب" عن
  "نتيجة سيئة"، والمكتبة ترفع استثناءاتها الخاصة.
- **حراسة القيم غير المنتهية**: NaN/inf يعبر بصمت وسط أرقام سليمة، ورقمٌ
  بلا معنى في توصية إنتاج أخطر من فشل صريح.
- **حدود الثقة**: `ConformalIntervals` في المكتبة تشترط 7 نقاط على الأقل
  (قِيس)، و39% من هذا الكتالوج أقصر من ذلك. فتبقى حدودنا المشتقّة من
  الرواسب — وهي اختيار عرضٍ لا خوارزمية.
"""
from __future__ import annotations

from typing import Sequence

import numpy as np

from core.exceptions import ModelTrainingError


def point_forecast(model, series: Sequence[float], steps: int, *, name: str) -> np.ndarray:
    """نقطة التنبؤ من نموذج statsforecast، بعقد أخطاء هذا المشروع.

    float32 لا float64: هو ما تتوقّعه واجهة statsforecast، وتمريره
    صراحةً يتجنّب تحويلاً ضمنياً يختلف بين إصداراتها.
    """
    values = np.asarray(series, dtype=np.float32)
    try:
        output = model.forecast(y=values, h=steps)
    except Exception as exc:  # noqa: BLE001 — المكتبة ترفع أنواعاً شتّى
        raise ModelTrainingError(
            f"فشل تدريب {name}: {exc}",
            cause=exc,
            context={"model": name, "points": len(values)},
        ) from exc

    forecast = np.asarray(output["mean"], dtype=float)
    if not np.all(np.isfinite(forecast)):
        raise ModelTrainingError(
            f"{name} أنتج قيماً غير منتهية (NaN/inf)",
            context={"model": name, "points": len(values)},
        )
    # كمية منتَجة سالبة بلا معنى — النماذج المتقطّعة قد تُنتجها على حوافّ
    return np.maximum(forecast, 0.0)
