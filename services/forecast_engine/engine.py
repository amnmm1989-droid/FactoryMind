# services/forecast_engine/engine.py
"""
المحرك: يُدرّب ما ينطبق، يقيّم، يختار الأفضل.

المحرك لا يعرف نموذجاً بعينه — يتعامل مع كائنات Forecaster. إضافة نموذج
ثامن = إضافة صف في registry.py، بلا لمس هذا الملف.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Sequence

from core.exceptions import InsufficientDataError, ModelSelectionError, ModelTrainingError
from core.logging_config import get_logger
from domain.entities import ForecastResult

from . import cache as forecast_cache
from .base import Forecaster, ForecastOutput
from .evaluation import ModelMetrics, backtest
from .intermittent import DemandProfile, classify_demand
from .registry import default_models

logger = get_logger(__name__)


def _metric_getter(metric_name: str):
    """دالة استخراج المقياس المستخدم للترتيب.

    مقياسان لا واحد، لأن السؤال يختلف:
      - rmse: "كم يخطئ في كل شهر؟" — صحيح للطلب المنتظم.
      - cumulative_error: "كم يخطئ في *إجمالي* الأفق؟" — الصحيح للمتقطّع،
        حيث الإصابة شهراً بشهر سؤال بلا جواب، وRMSE يكافئ التنبؤ بالصفر.
    """
    if metric_name == "cumulative_error":
        return lambda metrics: metrics.cumulative_error
    return lambda metrics: metrics.rmse


@dataclass(frozen=True)
class ModelEvaluation:
    """نتيجة نموذج واحد — نجح أو فشل. الفشل يُسجَّل ولا يُبتلع.

    metrics=None مع output موجود = دُرِّب لكن تعذّر تقييمه (سلسلة قصيرة).
    output=None = فشل التدريب، والسبب في error.
    """
    model_name: str
    output: ForecastOutput | None
    metrics: ModelMetrics | None
    duration_ms: int
    error: str | None = None
    from_cache: bool = False

    @property
    def succeeded(self) -> bool:
        return self.output is not None


@dataclass(frozen=True)
class EngineResult:
    """حصيلة المحرك: الفائز + سجل كامل لكل من جُرِّب."""
    product_name: str
    best: ForecastResult
    best_model_name: str
    evaluations: list[ModelEvaluation]
    data_hash: str
    profile: DemandProfile | None = None

    @property
    def evaluated_count(self) -> int:
        return sum(1 for e in self.evaluations if e.metrics is not None)

    @property
    def selection_metric(self) -> str:
        """المقياس الذي اختير به الفائز — يجب أن يُعرَض لا أن يُفترض."""
        if self.profile is not None and self.profile.is_intermittent:
            return "cumulative_error"
        return "rmse"

    def ranking(self) -> list[ModelEvaluation]:
        """المقيَّمة فقط، الأفضل أولاً — بالمقياس المناسب لهذه السلسلة."""
        scored = [e for e in self.evaluations if e.metrics is not None]
        key = _metric_getter(self.selection_metric)
        return sorted(scored, key=lambda e: key(e.metrics))


def _run_model(
    model: Forecaster,
    product_name: str,
    series: Sequence[float],
    steps: int,
    *,
    use_cache: bool,
) -> ModelEvaluation:
    """تشغيل نموذج واحد: cache -> تقييم -> تدريب نهائي."""
    started = time.perf_counter()
    key = forecast_cache.cache_key(product_name, series, model.name, steps)

    if use_cache:
        cached = forecast_cache.load(key)
        if cached is not None:
            return ModelEvaluation(
                model_name=model.name,
                output=cached.output,
                metrics=cached.metrics,
                duration_ms=int((time.perf_counter() - started) * 1000),
                from_cache=True,
            )

    # التقييم على بيانات مُخفاة أولاً — الرقم الذي سيُختار على أساسه
    metrics = backtest(model, series)

    # ثم التدريب النهائي على السلسلة كاملة (بما فيها ما أُخفي للتقييم):
    # التنبؤ الفعلي يستحق كل البيانات المتاحة، والتقييم أدى دوره.
    try:
        output = model.fit_predict(series, steps)
    except ModelTrainingError as exc:
        logger.info("Model failed | product=%s | model=%s | %s", product_name, model.name, exc.message)
        return ModelEvaluation(
            model_name=model.name,
            output=None,
            metrics=None,
            duration_ms=int((time.perf_counter() - started) * 1000),
            error=exc.message,
        )

    if use_cache:
        forecast_cache.save(key, output, metrics)

    return ModelEvaluation(
        model_name=model.name,
        output=output,
        metrics=metrics,
        duration_ms=int((time.perf_counter() - started) * 1000),
    )


def _forecast_value_added(
    evaluations: list[ModelEvaluation],
    winner: ModelEvaluation,
    metric_name: str,
) -> float | None:
    """Forecast Value Added: خطأ Naive ناقص خطأ الفائز، بمقياس الاختيار نفسه.

    موجب = الفائز أفضل من التكرار الساذج فعلاً — تعقيده اشترى شيئاً.
    صفر أو سالب = لم يشترِ شيئاً؛ الساذج كافٍ. القياس بنفس مقياس الاختيار
    (rmse للمنتظم، cumulative_error للمتقطّع) — مقارنة الفائز بمقياس
    والساذج بآخر بلا معنى.

    None حين لا يُقيَّم Naive (لم يُمرَّر ضمن النماذج المستدعاة، أو قصرت
    السلسلة عن تقييمه) — لا صفر مصطنع يوهم بمقارنة لم تحدث فعلاً. وهذا
    هو الفارق الذي يجعل الادّعاء الثابت في الـREADME ("النماذج الساذجة
    تفوز 60%") مقياساً حياً يتراكم مع بيانات كل مستخدم بدل تقرير واحد مجمَّد.
    """
    naive = next(
        (e for e in evaluations if e.model_name == "Naive" and e.metrics is not None),
        None,
    )
    if naive is None or winner.metrics is None:
        return None
    if naive.model_name == winner.model_name:
        return 0.0  # الساذج هو الفائز نفسه — لا قيمة مضافة تُقاس فوق نفسه

    metric = _metric_getter(metric_name)
    return float(metric(naive.metrics) - metric(winner.metrics))


def _select_best(
    evaluations: list[ModelEvaluation], metric_name: str = "rmse"
) -> ModelEvaluation:
    """اختيار الفائز.

    القاعدة الأولى: أقل قيمة للمقياس المناسب لهذه السلسلة بين المقيَّمة.
    القاعدة الثانية (حين لا يُقيَّم أي نموذج): الأول الناجح بترتيب السجل —
    أي الأبسط. مبدأ صريح: بلا دليل يثبت أن التعقيد يفيد، لا نشتريه.
    هذا ليس تنازلاً؛ على سلسلة من 5 نقاط، "آخر قيمة مكرّرة" إجابة أصدق
    من SARIMA لا يملك ما يكفي ليقول شيئاً.
    """
    successful = [e for e in evaluations if e.succeeded]
    if not successful:
        raise ModelSelectionError(
            "فشلت كل النماذج",
            context={"tried": [e.model_name for e in evaluations]},
        )

    scored = [e for e in successful if e.metrics is not None]
    if scored:
        key = _metric_getter(metric_name)
        return min(scored, key=lambda e: key(e.metrics))

    return successful[0]


def forecast_product(
    product_name: str,
    series: Sequence[float],
    steps: int = 6,
    *,
    models: list[Forecaster] | None = None,
    use_cache: bool = True,
) -> EngineResult:
    """تشغيل كل النماذج المنطبقة واختيار الأفضل.

    Raises:
        InsufficientDataError: سلسلة فارغة، أو لا نموذج ينطبق عليها.
        ModelSelectionError: انطبقت نماذج لكنها فشلت كلها.
    """
    if not series:
        raise InsufficientDataError(
            "سلسلة فارغة — لا يوجد ما يُتنبَّأ منه",
            context={"product": product_name},
        )
    if steps < 1:
        raise ValueError(f"عدد الخطوات يجب أن يكون >= 1، وصل: {steps}")

    candidates = models if models is not None else default_models()
    applicable = [m for m in candidates if m.can_handle(series)]

    if not applicable:
        raise InsufficientDataError(
            f"لا نموذج ينطبق على هذه السلسلة ({len(series)} نقطة، "
            f"{sum(1 for v in series if v != 0)} غير صفرية)",
            context={"product": product_name, "points": len(series)},
        )

    # تصنيف السلسلة يحدد المقياس الذي يُختار به الفائز. 84% من كتالوج هذا
    # المشروع متقطّع، وRMSE عليه يكافئ التنبؤ بالصفر — انظر evaluation.py.
    profile = classify_demand(series)
    metric_name = "cumulative_error" if profile.is_intermittent else "rmse"

    evaluations = [
        _run_model(model, product_name, series, steps, use_cache=use_cache)
        for model in applicable
    ]

    best = _select_best(evaluations, metric_name)
    metrics = best.metrics
    fva = _forecast_value_added(evaluations, best, metric_name)

    result = ForecastResult(
        product_name=product_name,
        model_name=best.model_name,
        forecast_values=best.output.values,
        lower_bound=best.output.lower,
        upper_bound=best.output.upper,
        mae=metrics.mae if metrics else None,
        rmse=metrics.rmse if metrics else None,
        mape=metrics.mape if metrics else None,
        wape=metrics.wape if metrics else None,
        fva=fva,
    )

    logger.info(
        "Forecast selected | product=%s | winner=%s | class=%s | metric=%s | evaluated=%d/%d",
        product_name,
        best.model_name,
        profile.demand_class.value,
        metric_name,
        sum(1 for e in evaluations if e.metrics is not None),
        len(evaluations),
    )

    return EngineResult(
        product_name=product_name,
        best=result,
        best_model_name=best.model_name,
        evaluations=evaluations,
        data_hash=forecast_cache.data_hash(product_name, series),
        profile=profile,
    )
