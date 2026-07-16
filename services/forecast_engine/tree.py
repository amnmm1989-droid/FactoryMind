# services/forecast_engine/tree.py
"""
النماذج الشجرية: XGBoost و RandomForest.

الأشجار لا تفهم الزمن — تحتاج تحويل السلسلة إلى مسألة انحدار جدولية عبر
lag features: "تنبّأ بقيمة الشهر من قيم الـ 12 شهراً السابقة".

⚠️ تحفّظ يجب أن يُقال بصراحة: هذا التحويل يكلّف صفوفاً. سلسلة من 44 نقطة
بـ 12 lag تُنتج 32 صف تدريب لـ 12 متغيراً — نسبة نحيفة لمجموعة أشجار،
ومَظِنّة overfitting. وهذه أفضل حالة في البيانات؛ الوسيط أسوأ بكثير.

لم نستبعدها لأجل ذلك: الحكم يُترك للأرقام، لا للحدس. جدول model_performance
سيقول بوضوح ما إذا كان XGBoost يهزم متوسطاً متحركاً من ثلاثة أشهر. إن لم
يفعل — وهو احتمال جدّي — فتلك نتيجة مفيدة لا فشل.
"""
from __future__ import annotations

from typing import Sequence

import numpy as np

from config import CONFIDENCE_LEVEL
from core.exceptions import ModelTrainingError

from .base import Forecaster, ForecastOutput

DEFAULT_LAGS = 12  # دورة سنوية كاملة — تسمح للنموذج بالتقاط الموسمية


def _build_supervised(values: np.ndarray, lags: int) -> tuple[np.ndarray, np.ndarray]:
    """تحويل سلسلة إلى (X, y): كل صف = نافذة الـ lags السابقة، الهدف = التالي."""
    windows = [values[i - lags : i] for i in range(lags, len(values))]
    targets = values[lags:]
    return np.asarray(windows, dtype=float), np.asarray(targets, dtype=float)


class _LagBasedForecaster(Forecaster):
    """المنطق المشترك: بناء lag features، تدريب، تنبؤ تكراري.

    XGBoost و RandomForest يختلفان في المُقدِّر فقط — لا في أي شيء آخر.
    """

    min_points = 2 * DEFAULT_LAGS  # 12 lag + 12 صف تدريب على الأقل
    min_non_zero = 12

    def __init__(self, lags: int = DEFAULT_LAGS) -> None:
        self.lags = lags

    def _make_estimator(self):
        raise NotImplementedError

    def fit_predict(self, series: Sequence[float], steps: int) -> ForecastOutput:
        values = np.asarray(series, dtype=float)
        if len(values) <= self.lags:
            raise ModelTrainingError(
                f"السلسلة ({len(values)}) لا تتجاوز عدد الـ lags ({self.lags})",
                context={"model": self.name},
            )

        features, targets = _build_supervised(values, self.lags)
        if len(features) < 2:
            raise ModelTrainingError(
                f"صفوف تدريب غير كافية: {len(features)}",
                context={"model": self.name, "points": len(values)},
            )

        try:
            estimator = self._make_estimator()
            estimator.fit(features, targets)
        except Exception as exc:
            raise ModelTrainingError(
                f"فشل تدريب {self.name}: {exc}",
                cause=exc,
                context={"model": self.name, "rows": len(features)},
            ) from exc

        # تنبؤ تكراري: كل قيمة متوقَّعة تصبح مُدخلاً للخطوة التالية.
        # الخطأ يتراكم مع الأفق — وهو قيد أصيل في هذا النهج، تعكسه
        # مقاييس التقييم على أفق كامل.
        history = list(values)
        forecast = []
        for _ in range(steps):
            window = np.asarray([history[-self.lags :]], dtype=float)
            predicted = float(estimator.predict(window)[0])
            predicted = max(predicted, 0.0)
            forecast.append(predicted)
            history.append(predicted)

        forecast_array = np.asarray(forecast, dtype=float)
        if not np.all(np.isfinite(forecast_array)):
            raise ModelTrainingError(
                f"{self.name} أنتج قيماً غير منتهية (NaN/inf)",
                context={"model": self.name},
            )

        # الأشجار لا تعطي فترات ثقة — نشتقّها من رواسب التدريب.
        # تحفّظ: رواسب التدريب متفائلة (النموذج رآها)، فالحدود أضيق من الحقيقة.
        residuals = targets - estimator.predict(features)
        spread = float(np.std(residuals)) if len(residuals) > 1 else 0.0
        margin = CONFIDENCE_LEVEL * spread
        lower = np.maximum(forecast_array - margin, 0.0)

        return ForecastOutput(
            values=forecast_array.tolist(),
            lower=lower.tolist(),
            upper=(forecast_array + margin).tolist(),
        )


class XGBoostForecaster(_LagBasedForecaster):
    """XGBoost بمعاملات محافظة عمداً.

    n_estimators=50 و max_depth=3: مع 32 صفاً، الإعدادات الافتراضية
    (100 شجرة، عمق 6) تحفظ بيانات التدريب حرفياً. الضحالة هنا قيد مقصود.
    """

    name = "XGBoost"

    def _make_estimator(self):
        try:
            from xgboost import XGBRegressor
        except ImportError as exc:
            raise ModelTrainingError(
                "XGBoost غير مثبّت — pip install -r requirements.lock.txt",
                cause=exc,
                context={"model": self.name},
            ) from exc

        return XGBRegressor(
            n_estimators=50,
            max_depth=3,
            learning_rate=0.1,
            subsample=0.8,
            random_state=42,  # نتائج قابلة للتكرار — مطلب للاختبارات وللمقارنة
            verbosity=0,
            n_jobs=1,
        )


class RandomForestForecaster(_LagBasedForecaster):
    """RandomForest.

    أقل ميلاً للـ overfitting من XGBoost على بيانات شحيحة (bagging لا
    boosting) — مرشّح معقول لأن يهزمه على هذه الأحجام.
    """

    name = "RandomForest"

    def _make_estimator(self):
        try:
            from sklearn.ensemble import RandomForestRegressor
        except ImportError as exc:
            raise ModelTrainingError(
                "scikit-learn غير مثبّت — pip install -r requirements.lock.txt",
                cause=exc,
                context={"model": self.name},
            ) from exc

        return RandomForestRegressor(
            n_estimators=100,
            max_depth=5,
            min_samples_leaf=2,
            random_state=42,
            n_jobs=1,
        )
