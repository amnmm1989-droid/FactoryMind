# services/risk_service/calibration.py
"""
معايرة FACTOR_WEIGHTS من نتائج فعلية — لا تخمين أبدي.

FACTOR_WEIGHTS في scoring.py معايرة أولية موثَّقة صراحة بأنها بلا بيانات
تحقّق (راجع تعليقها). هذا الملف يجيب: الآن بعد أن صار actual_quantity
قابلاً للتعبئة (Roadmap بند 4)، هل تتنبأ العوامل الخمسة فعلاً بصعوبة
التخطيط — أم أن أوزانها اليدوية مجرد حدس معقول؟

**تشخيص لا تطبيق تلقائي.** هذا الملف لا يكتب في FACTOR_WEIGHTS ولا
يُستدعى من compute_risk — إعادة توزيع خطورة كل منتج في التطبيق بناءً على
عيّنة قد تكون عشرات الصفوف فقط قرارٌ يستحق عرضاً على إنسان لا استبدالاً
صامتاً. الواجهة (ui/pages/production_planning.py) تعرض التقرير؛ تغيير
FACTOR_WEIGHTS نفسه قرار يدوي كما كان دائماً.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# أقل عدد أزواج (قيمة عامل، خطأ تخطيط) قبل أن يُحتسَب ارتباط لعامل ما.
# ليس ضماناً إحصائياً — عتبة تمنع أن تبدو نقطتان محظوظتان/سيّئتا الحظ
# كدليل قاطع، لا أكثر.
MIN_SAMPLE_PER_FACTOR = 10

FACTOR_NAMES = (
    "demand_volatility",
    "stock_depletion_risk",
    "forecast_accuracy_penalty",
    "seasonality_factor",
    "growth_rate",
)


def planning_error(planned: float, actual: float) -> float | None:
    """خطأ التخطيط النسبي لخطة واحدة: |الفعلي - المخطَّط| / الفعلي.

    None حين actual <= 0: النسبة قسمة على صفر — غير معرَّفة رياضياً، لا
    صفراً ولا خطأً أقصى. خطة لمنتج لم يُنتَج منه شيء فعلاً تُستبعد من
    المعايرة بدل أن تُشوَّه بقيمة مخترعة.
    """
    if actual <= 0:
        return None
    return abs(actual - planned) / actual


def _pearson(pairs: list[tuple[float, float]]) -> float | None:
    """معامل ارتباط بيرسون — بلا مكتبة خارجية، الصيغة القياسية مباشرة.

    None حين لا تباين في أحد المحورين (كل قيم العامل متطابقة مثلاً):
    الارتباط غير معرَّف رياضياً (قسمة على صفر) لا صفراً — صفر كان سيعني
    "لا علاقة"، بينما الحقيقة "لم يمكن اختبار علاقة أصلاً".
    """
    n = len(pairs)
    mean_x = sum(x for x, _ in pairs) / n
    mean_y = sum(y for _, y in pairs) / n
    covariance = sum((x - mean_x) * (y - mean_y) for x, y in pairs)
    variance_x = sum((x - mean_x) ** 2 for x, _ in pairs)
    variance_y = sum((y - mean_y) ** 2 for _, y in pairs)
    if variance_x == 0 or variance_y == 0:
        return None
    return covariance / (variance_x * variance_y) ** 0.5


@dataclass(frozen=True)
class FactorCorrelation:
    """ارتباط عامل واحد بخطأ التخطيط — عبر عيّنته الخاصة (لا كل الصفوف).

    عامل مثل stock_depletion_risk قد يكون None لمعظم الصفوف (لا ملف مخزون
    رُفع وقت كل توصية)، فعيّنته الصالحة أصغر من إجمالي الخطط المعتمَدة —
    وهذا مسجَّل صراحة في sample_size لا مطويّاً.
    """

    factor: str
    correlation: float | None
    sample_size: int


@dataclass(frozen=True)
class CalibrationReport:
    """حصيلة المعايرة الكاملة — ما يكفي لإنسان ليقرر، لا قراراً جاهزاً."""

    total_outcomes: int
    correlations: tuple[FactorCorrelation, ...] = field(default_factory=tuple)
    suggested_weights: dict[str, float] | None = None

    @property
    def validated_factors(self) -> list[str]:
        return [c.factor for c in self.correlations if c.correlation is not None]

    @property
    def unvalidated_factors(self) -> list[str]:
        return [c.factor for c in self.correlations if c.correlation is None]


def calibrate(outcomes: list[dict[str, float]]) -> CalibrationReport:
    """معايرة من صفوف ProductionPlanRepository.validated_outcomes().

    لكل عامل: يُجمَع (قيمته، خطأ التخطيط) عبر الصفوف التي حَسبته فعلاً
    (ليست None) ولها فعلي > 0 (planning_error معرَّف). دون MIN_SAMPLE_PER_FACTOR
    زوجاً، correlation=None — لا رقم من عيّنة لا تكفي لتبرير رقم.

    الوزن المقترح لعامل يتناسب مع ارتباطه الموجب بخطأ التخطيط: عامل
    يرتفع حين يصعب التخطيط يستحق وزناً أعلى؛ ارتباط سالب (العامل يرتفع
    حين *يسهل* التخطيط) يُصفَّر لا يُعكَس — عكسه في الوزن قرار مختلف كلياً
    (خفض الخطورة عند ارتفاع العامل)، وهذا الملف لا يعيد تصميم المعنى.

    suggested_weights=None كاملاً حين لا عامل واحد بلغ العتبة — لا فرضاً
    جزئياً موهماً بدقة لا تملكها العيّنة.
    """
    correlations: list[FactorCorrelation] = []
    positive_correlations: dict[str, float] = {}

    for factor in FACTOR_NAMES:
        pairs: list[tuple[float, float]] = []
        for row in outcomes:
            factor_value = row.get(factor)
            error = planning_error(row["planned_quantity"], row["actual_quantity"])
            if factor_value is not None and error is not None:
                pairs.append((factor_value, error))

        if len(pairs) < MIN_SAMPLE_PER_FACTOR:
            correlations.append(FactorCorrelation(factor, None, len(pairs)))
            continue

        correlation = _pearson(pairs)
        correlations.append(FactorCorrelation(factor, correlation, len(pairs)))
        if correlation is not None and correlation > 0:
            positive_correlations[factor] = correlation

    suggested_weights = None
    if positive_correlations:
        total = sum(positive_correlations.values())
        suggested_weights = {
            factor: value / total for factor, value in positive_correlations.items()
        }

    return CalibrationReport(
        total_outcomes=len(outcomes),
        correlations=tuple(correlations),
        suggested_weights=suggested_weights,
    )
