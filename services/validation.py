# services/validation.py
"""
تقرير التحقّق — "لو استخدمتَ هذه الأداة على تاريخك، ماذا كانت ستقول؟"

## لماذا هذا الملف موجود

الادّعاء "أداتي صحيحة" لا يبيع ولا يُثبِت. ما يبيع ويُثبِت هو رقمٌ على
بيانات العميل نفسه: *على تاريخك أنت، هذه دقّة ما كانت الأداة ستوصي به*.
هذا الملف يُنتج ذلك الرقم.

## الفارق عن backtesting الموجود في evaluation.py

`evaluation.backtest` يقيّم **نموذجاً واحداً** على **نافذة واحدة** ليختار
المحرك فائزه. هذا الملف يقيّم **الأداة كلها** على **عدة نقاط زمنية**:

    لكل أصل (origin) في الماضي:
        درّب على ما قبله فقط  ->  دع المحرك يختار نموذجه بنفسه
        قارن توصيته بما حدث فعلاً بعده

فيحاكي ما كانت الأداة ستقوله لو شُغّلت في ذلك التاريخ — بما في ذلك
*اختيارها للنموذج*، لا نموذجاً مثبَّتاً سلفاً. نافذة واحدة قد تكون حظاً؛
عدة أصول تكشف الثبات.

⚠️ لا تسريب للمستقبل: كل أصل يرى `series[:origin]` فقط. لهذا نستدعي
`forecast_product` على الشريحة لا على السلسلة كاملة — المحرك يعيد اختيار
نموذجه من الشريحة وحدها، تماماً كما كان سيفعل حينها.

## المقاييس

- **WAPE**: `Σ|خطأ| / Σ|فعلي|` — نسبة مفهومة بلا شرح رياضي، ومقاومة
  للأصفار (خلافاً لـMAPE الذي ينهار عليها، و84% من هذا الكتالوج متقطّع).
- **MASE**: الخطأ مقسوماً على خطأ التنبؤ الساذج على بيانات التدريب.
  قيمة < 1 تعني "أفضل من الساذج"، و> 1 تعني "أسوأ منه". هو المقياس
  الوحيد هنا القابل للمقارنة **بين منتجات مختلفة الأحجام** — ولهذا يصلح
  لتلخيص كتالوج كامل برقم واحد.

## الأمانة أولاً

منتج لا يكفي تاريخه للتقييم **يُذكر باسمه وسببه**، لا يُحذف من المقام
فيبدو المتوسط أجمل. هذا ما يميّز التقرير عن دعاية: نسبة التغطية جزء من
النتيجة لا هامش عليها.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from core.exceptions import AppError
from core.logging_config import get_logger
from services.forecast_engine import forecast_product
from services.forecast_engine.intermittent import classify_demand

logger = get_logger(__name__)

# أقل تدريب مقبول قبل أول أصل: أقصر من ذلك والنتيجة ضجيج لا قياس.
MIN_TRAIN_POINTS = 8
DEFAULT_ORIGINS = 3
DEFAULT_HORIZON = 3


@dataclass(frozen=True)
class OriginResult:
    """نتيجة أصل واحد: ما توقّعته الأداة مقابل ما حدث — ومقابل الساذج.

    `naive` هو تكرار آخر قيمة تدريب على نفس الأفق ونفس النافذة. وجوده هنا
    ليس زينة: المقارنة العادلة الوحيدة هي **نفس الأفق على نفس البيانات**.
    """

    train_size: int
    model_name: str
    actual: list[float]
    predicted: list[float]
    naive: list[float]


@dataclass(frozen=True)
class ProductValidation:
    """حصيلة منتج واحد عبر كل أصوله."""

    product_name: str
    demand_class: str
    origins: list[OriginResult]
    wape: float | None
    mase: float | None
    mae: float | None = None        # خطأ الأداة، مجمَّعاً على الأصول
    naive_mae: float | None = None  # خطأ الساذج على نفس النوافذ والأفق

    @property
    def origins_tested(self) -> int:
        return len(self.origins)

    @property
    def beat_naive(self) -> bool | None:
        """هل تفوّقت الأداة على الساذج — **على نفس الأفق ونفس النافذة**؟

        المقارنة هنا لا تستخدم MASE عمداً. مقام MASE هو خطأ الساذج
        *بخطوة واحدة داخل التدريب*، ومقارنة تنبؤ بأفق ثلاث فترات به
        تحاسب الأداة على صعوبة الأفق لا على جودتها — فتبدو أسوأ مما هي
        لسبب حسابي. الادّعاء الذي يُعرَض على مصنع يجب أن يكون عادلاً:
        نفس النافذة، نفس الأفق، نموذجان.

        None حين لا طلب فعلي يُقاس عليه.
        """
        if self.mae is None or self.naive_mae is None:
            return None
        return self.mae < self.naive_mae

    @property
    def winning_models(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for origin in self.origins:
            counts[origin.model_name] = counts.get(origin.model_name, 0) + 1
        return counts


@dataclass
class ValidationReport:
    """التقرير الكامل — بما فيه ما تعذّر تقييمه."""

    products: list[ProductValidation] = field(default_factory=list)
    skipped: list[tuple[str, str]] = field(default_factory=list)
    horizon: int = DEFAULT_HORIZON
    origins_requested: int = DEFAULT_ORIGINS
    granularity: str = "monthly"

    @property
    def evaluated_count(self) -> int:
        """شُغِّلت عليها الأداة فعلاً (بصرف النظر عن قابلية القياس)."""
        return len(self.products)

    @property
    def measured_count(self) -> int:
        """قِيست دقّتها فعلاً — أي وقع فيها طلب تُقاس عليه.

        منفصلة عن evaluated_count عمداً: منتج نافذته صفرية بالكامل شُغِّلت
        عليه الأداة لكن لا دقّة تُقاس له. خلطهما كان سيرفع "التغطية"
        برقمٍ لا يسنده قياس.
        """
        return sum(1 for p in self.products if p.wape is not None)

    @property
    def no_demand_count(self) -> int:
        """قُيِّمت لكن لم يقع فيها طلب في نافذة الاختبار — لا دقّة تُقاس."""
        return self.evaluated_count - self.measured_count

    @property
    def total_count(self) -> int:
        return len(self.products) + len(self.skipped)

    @property
    def coverage(self) -> float:
        """نسبة المنتجات التي **قِيست** دقّتها — لا التي شُغِّلت عليها.

        جزء من النتيجة لا هامش عليها: المقام يشمل المتخطّى وعديم الطلب
        معاً، وإلا لجمّلنا المتوسط بحذف ما لم نستطع قياسه.
        """
        return self.measured_count / self.total_count if self.total_count else 0.0

    @property
    def median_wape(self) -> float | None:
        values = [p.wape for p in self.products if p.wape is not None]
        return float(np.median(values)) if values else None

    @property
    def median_mase(self) -> float | None:
        values = [p.mase for p in self.products if p.mase is not None]
        return float(np.median(values)) if values else None

    @property
    def beat_naive_share(self) -> float | None:
        """نسبة المنتجات التي تفوّقت فيها الأداة على الساذج."""
        judged = [p.beat_naive for p in self.products if p.beat_naive is not None]
        return sum(judged) / len(judged) if judged else None

    @property
    def model_usage(self) -> dict[str, int]:
        """كم مرة فاز كل نموذج عبر كل المنتجات والأصول."""
        counts: dict[str, int] = {}
        for product in self.products:
            for name, times in product.winning_models.items():
                counts[name] = counts.get(name, 0) + times
        return dict(sorted(counts.items(), key=lambda kv: -kv[1]))


def _wape(actual: np.ndarray, predicted: np.ndarray) -> float | None:
    denominator = float(np.sum(np.abs(actual)))
    if denominator == 0:
        return None
    return float(np.sum(np.abs(actual - predicted)) / denominator * 100)


def _mase(actual: np.ndarray, predicted: np.ndarray, scale: float) -> float | None:
    """MASE: الخطأ مقسوماً على خطأ الساذج ذي الخطوة الواحدة على التدريب.

    None في حالتين، وكلتاهما "لا أعرف" لا "ممتاز":

    1. **مقياس التدريب صفر** (سلسلة ثابتة تماماً) — القسمة على صفر تُنتج
       inf، وinf في وسيط الكتالوج يُفسده كله.
    2. **لا طلب فعلي في نافذة الاختبار** — وهذا الفخّ الحقيقي هنا. على
       بيانات 87% أصفار، نصف المنتجات تقريباً نافذتها صفرية بالكامل؛
       والنموذج يتنبّأ بصفر فيصير MASE = 0.00 أي "دقّة مثالية". قِيس
       فعلياً: 19 من 40 منتجاً أسبوعياً. عرض ذلك كدقّة يبيع ثقةً بلا
       أساس — وهو أسوأ من عدم عرض رقم إطلاقاً. WAPE محروس أصلاً بنفس
       الشرط (مقامه Σ|فعلي|)، وهذا يوحّدهما.
    """
    if scale <= 0:
        return None
    if float(np.sum(np.abs(actual))) == 0:
        return None
    return float(np.mean(np.abs(actual - predicted)) / scale)


def _origins_for(length: int, horizon: int, requested: int) -> list[int]:
    """مواضع الأصول — من الأحدث إلى الأقدم، بخطوة أفق واحد.

    الخطوة بأفق كامل (لا بفترة واحدة) تجعل نوافذ الاختبار غير متداخلة،
    فلا يُحتسب الخطأ نفسه مرتين ويبدو الثبات أعلى مما هو.
    """
    origins = []
    for index in range(requested):
        origin = length - horizon * (index + 1)
        if origin < MIN_TRAIN_POINTS:
            break
        origins.append(origin)
    return sorted(origins)


def validate_product(
    product_name: str,
    series: list[float],
    *,
    horizon: int = DEFAULT_HORIZON,
    origins: int = DEFAULT_ORIGINS,
    granularity: str = "monthly",
    models=None,
) -> ProductValidation:
    """تشغيل الأداة على ماضي منتج واحد، عدة مرات.

    Raises:
        ValueError: حين لا يكفي التاريخ لأصل واحد — الرافع يقرر ماذا
            يفعل، والتقرير يسجّله في skipped بدل أن يبتلعه.
    """
    values = np.asarray(series, dtype=float)
    positions = _origins_for(len(values), horizon, origins)
    if not positions:
        raise ValueError(
            f"{len(values)} نقطة لا تكفي لأصل واحد "
            f"(الحد الأدنى {MIN_TRAIN_POINTS + horizon})"
        )

    results: list[OriginResult] = []
    all_actual: list[float] = []
    all_predicted: list[float] = []
    all_naive: list[float] = []
    scales: list[float] = []

    for origin in positions:
        train = values[:origin]
        actual = values[origin:origin + horizon]
        if len(actual) == 0:
            continue
        try:
            outcome = forecast_product(
                product_name, train.tolist(), steps=len(actual),
                models=models, use_cache=False, granularity=granularity,
            )
        except AppError as exc:
            logger.debug("Origin skipped | product=%s | origin=%d | %s",
                         product_name, origin, exc)
            continue

        predicted = np.asarray(outcome.best.forecast_values[:len(actual)], dtype=float)
        # الساذج على نفس النافذة ونفس الأفق: تكرار آخر قيمة تدريب
        naive = np.full(len(actual), float(train[-1]))

        results.append(OriginResult(
            train_size=int(origin),
            model_name=outcome.best_model_name,
            actual=actual.tolist(),
            predicted=predicted.tolist(),
            naive=naive.tolist(),
        ))
        all_actual.extend(actual.tolist())
        all_predicted.extend(predicted.tolist())
        all_naive.extend(naive.tolist())
        if len(train) >= 2:
            scale = float(np.mean(np.abs(np.diff(train))))
            if scale > 0:
                scales.append(scale)

    if not results:
        raise ValueError("تعذّر تقييم أي أصل — كل النماذج فشلت على هذه السلسلة")

    actual_array = np.asarray(all_actual, dtype=float)
    predicted_array = np.asarray(all_predicted, dtype=float)
    naive_array = np.asarray(all_naive, dtype=float)

    # المقاييس مجمَّعة على كل الأصول لا متوسط نِسَبٍ فردية: أصلٌ بقيم صغيرة
    # لا يقلب النتيجة (نفس مبدأ WAPE في evaluation.py).
    measurable = float(np.sum(np.abs(actual_array))) > 0

    return ProductValidation(
        product_name=product_name,
        demand_class=classify_demand(series).demand_class.value,
        origins=results,
        wape=_wape(actual_array, predicted_array),
        mase=_mase(
            actual_array, predicted_array, float(np.mean(scales)) if scales else 0.0
        ),
        mae=float(np.mean(np.abs(actual_array - predicted_array))) if measurable else None,
        naive_mae=float(np.mean(np.abs(actual_array - naive_array))) if measurable else None,
    )


def build_validation_report(
    products: dict[str, list[float]],
    *,
    horizon: int = DEFAULT_HORIZON,
    origins: int = DEFAULT_ORIGINS,
    granularity: str = "monthly",
    models=None,
    on_progress=None,
) -> ValidationReport:
    """تقرير التحقّق للكتالوج كله.

    منتج يتعذّر تقييمه لا يُسقِط التقرير ولا يختفي — يُسجَّل في skipped
    بسببه، وتظهر نسبة التغطية في النتيجة.
    """
    report = ValidationReport(
        horizon=horizon, origins_requested=origins, granularity=granularity
    )
    total = len(products)

    for index, (name, series) in enumerate(products.items(), start=1):
        try:
            report.products.append(validate_product(
                name, list(series), horizon=horizon, origins=origins,
                granularity=granularity, models=models,
            ))
        except (ValueError, AppError) as exc:
            report.skipped.append((name, getattr(exc, "message", str(exc))))
        if on_progress is not None:
            on_progress(index, total, name)

    logger.info(
        "Validation report | evaluated=%d/%d | median_wape=%s | beat_naive=%s",
        report.evaluated_count, report.total_count,
        report.median_wape, report.beat_naive_share,
    )
    return report
