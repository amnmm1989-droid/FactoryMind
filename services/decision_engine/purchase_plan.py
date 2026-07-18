# services/decision_engine/purchase_plan.py
"""
خطة شراء لكل الكتالوج — أفق أشهر يختاره مدير المشتريات، لا الشهر الواحد
الذي تفترضه recommend_production افتراضياً.

الفرق عن services/batch.py: batch.py يحفظ توصية أفقها شهر واحد لكل منتج
في قاعدة البيانات (لصفحة executive). هنا لا حفظ — تقرير مؤقت بأفق موحّد
يختاره المستخدم عند الطلب (3، 6، 12 شهراً)، تماماً كما طلب مدير مشتريات
فعلي: "كم أشتري لتغطية N شهراً القادمة" لا "كم أنتج الشهر القادم".
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Sequence

from config import GRANULARITY_DAYS
from core.exceptions import AppError
from core.logging_config import get_logger
from domain.entities import InventoryStatus
from services.forecast_engine import forecast_product

from .recommender import recommend_production

logger = get_logger(__name__)

# منتج بلا بيع في هذا العدد من آخر الفترات يُعامَل "متوقّفاً مؤخراً" في
# ملاحظة السطر — تنبؤه غالباً صفر بالفعل (Naive يكرر آخر قيمة صفرية)، لكن
# مدير المشتريات يحتاج أن يرى *لماذا* صراحة، لا رقماً صفرياً بلا سبب ظاهر.
RECENT_DORMANCY_WINDOW = 12

# أقل عدد فترات فعلية (غير صفرية) قبل اعتبار المنتج "بيانات قليلة جداً" —
# تنبؤ من نقطة أو نقطتين تخمين موسوم لا تنبؤ، ويجب أن يقول ذلك عن نفسه
# بدل أن يُعرض بثقة مطابقة لمنتج له تاريخ كامل.
COLD_START_MAX_NON_ZERO = 3


@dataclass(frozen=True)
class PurchaseOrderLine:
    """سطر واحد في خطة الشراء — منتج واحد على الأفق الموحّد للخطة كاملة."""

    product_name: str
    horizon_months: int
    recommended_quantity: float
    current_stock: float | None
    demand_class: str
    model_name: str
    wape: float | None
    risk_level: str
    confidence_note: str | None  # "cold_start" | "recently_dormant" | None
    reason: str
    urgency: str | None = None  # "urgent" | "can_wait" | None (بلا مهلة توريد معروفة)
    unit_price: float | None = None
    total_cost: float | None = None


@dataclass
class PurchasePlan:
    """حصيلة كاملة — أسطر مُقيَّمة + ما تعذّر تقييمه كلياً (بلا بيانات)."""

    horizon_months: int
    lines: list[PurchaseOrderLine] = field(default_factory=list)
    skipped: list[tuple[str, str]] = field(default_factory=list)


def _confidence_note(series: Sequence[float], profile) -> str | None:
    """سبب صريح لضعف الثقة في سطر، لا صمتاً حين يستحق تحذيراً.

    الترتيب مقصود: cold_start أولى — منتج بثلاث نقاط بيانات أو أقل غير
    قابل للحكم عليه بـ"توقّف مؤخراً" أصلاً (لا تاريخ كافٍ ليُقارَن).
    """
    if profile is not None and profile.non_zero_count <= COLD_START_MAX_NON_ZERO:
        return "cold_start"

    window = series[-RECENT_DORMANCY_WINDOW:] if len(series) >= RECENT_DORMANCY_WINDOW else series
    if window and all(v == 0 for v in window) and any(v != 0 for v in series):
        return "recently_dormant"
    return None


def _urgency(
    current_stock: float | None, forecast_values: Sequence[float],
    horizon_months: int, lead_time_days: int | None, granularity: str,
) -> str | None:
    """"اطلب الآن" أم "يمكن الانتظار"؟ — تقدير أولوية لا نظام نقطة إعادة
    طلب كامل: يقارن أيام تغطية المخزون الحالي بمهلة التوريد المُدخَلة
    يدوياً، دون افتراض تباين تلك المهلة (يحتاج سجل أوامر شراء حقيقي غير
    متوفر بعد — راجع docs/ROADMAP.md).

    طول الفترة بالأيام يُشتقّ من الحبيبة الفعلية (config.GRANULARITY_DAYS)
    لا يُفترَض شهرياً: ملف أسبوعي يعني period_demand طلباً أسبوعياً، وضربه
    بـ30 كان سيحسبه كأنه طلب شهري فيبالغ في أيام التغطية ~4 أضعاف — عاجل
    فعلاً يظهر "يمكن الانتظار".

    None حين تنقص مدخلاته (لا مخزون معروف، لا مهلة أُدخلت، أو لا طلب
    متوقَّع لتُقاس عليه أيام التغطية) — لا صفراً موهماً بعدم إلحاح.
    """
    if lead_time_days is None or current_stock is None:
        return None
    period_demand = sum(forecast_values[:horizon_months]) / horizon_months if horizon_months else 0
    if period_demand <= 0:
        return None
    period_days = GRANULARITY_DAYS.get(granularity, GRANULARITY_DAYS["monthly"])
    days_of_stock = (current_stock / period_demand) * period_days
    return "urgent" if days_of_stock <= lead_time_days else "can_wait"


def build_purchase_plan(
    products: dict[str, Sequence[float]],
    *,
    horizon_months: int,
    inventory: dict[str, InventoryStatus] | None = None,
    prices: dict[str, float] | None = None,
    lead_time_days: int | None = None,
    granularity: str = "monthly",
    use_fast_models: bool = True,
    on_progress: Callable[[int, int, str], None] | None = None,
) -> PurchasePlan:
    """خطة شراء لكل منتج في products، بأفق موحّد.

    الكمية لكل سطر = مجموع الطلب المتوقَّع خلال horizon_months، ناقص
    المخزون الحالي إن عُرف (نفس منطق recommend_production بالحرف — هذا
    غلاف يكرره على الكتالوج كاملاً بأفق قابل للاختيار).

    prices: {اسم المنتج: سعر الوحدة}، إن وُجد عمود سعر اختياري في ملف
        المخزون. منتج غائب عن القاموس (أو القاموس None كله) يمرّ بلا
        تكلفة محسوبة — نفس معاملة inventory تماماً، غياب لا صفر.
    lead_time_days: مهلة توريد نمطية واحدة تُطبَّق على كل الكتالوج (رقم
        يدخله المستخدم يدوياً، لا ملف) — تكفي لتصنيف كل سطر "اطلب الآن"
        أم "يمكن الانتظار"، راجع _urgency.

    منتج بلا بيانات كافية (AppError) يُسجَّل في plan.skipped ولا يُسقط
    الخطة كاملة — نفس مبدأ services/batch.py.

    Raises:
        ValueError: horizon_months < 1.
    """
    if horizon_months < 1:
        raise ValueError(f"أفق غير صالح: {horizon_months}")

    from services.batch import fast_models

    models = fast_models() if use_fast_models else None
    plan = PurchasePlan(horizon_months=horizon_months)
    total = len(products)

    for index, (name, series) in enumerate(products.items(), start=1):
        try:
            engine_result = forecast_product(
                name, series, steps=horizon_months, models=models,
                use_cache=False, granularity=granularity,
            )
            product_inventory = inventory.get(name) if inventory else None
            recommendation = recommend_production(
                name, list(series), engine_result.best, product_inventory,
                horizon_months=horizon_months, granularity=granularity,
            )
            current_stock = (
                product_inventory.current_stock if product_inventory else None
            )
            unit_price = prices.get(name) if prices else None
            total_cost = (
                recommendation.recommended_quantity * unit_price
                if unit_price is not None else None
            )
            plan.lines.append(PurchaseOrderLine(
                product_name=name,
                horizon_months=horizon_months,
                recommended_quantity=recommendation.recommended_quantity,
                current_stock=current_stock,
                demand_class=(
                    engine_result.profile.demand_class.value
                    if engine_result.profile else "unknown"
                ),
                model_name=engine_result.best_model_name,
                wape=engine_result.best.wape,
                risk_level=recommendation.risk.level.value,
                confidence_note=_confidence_note(series, engine_result.profile),
                reason=recommendation.reason,
                urgency=_urgency(
                    current_stock, engine_result.best.forecast_values,
                    horizon_months, lead_time_days, granularity,
                ),
                unit_price=unit_price,
                total_cost=total_cost,
            ))
        except AppError as exc:
            plan.skipped.append((name, exc.message))

        if on_progress is not None:
            on_progress(index, total, name)

    logger.info(
        "Purchase plan built | horizon=%d | lines=%d | skipped=%d",
        horizon_months, len(plan.lines), len(plan.skipped),
    )
    return plan
