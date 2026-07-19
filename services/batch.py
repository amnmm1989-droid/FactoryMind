# services/batch.py
"""
حساب التنبؤات والتوصيات لكل المنتجات دفعةً واحدة، وحفظها.

لماذا دفعة لا حساباً عند الطلب — قياس فعلي على هذه الآلة:

    النماذج الخفيفة (4):  أقل من ثانية لكتالوج كامل
    النماذج الكاملة (9):  3.3 دقيقة

صفحة تُشغّل كل النماذج لكل منتج عند كل تحميل غير قابلة للاستخدام.
ولهذا وُجد جدولا forecasts و recommendations منذ Phase 2: تُملأ هنا مرة،
وتقرأ منها الصفحات فوراً.

الاستدعاء من الواجهة يمرّر on_progress لعرض شريط تقدّم.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Sequence

from core.exceptions import AppError
from core.logging_config import get_logger
from domain.entities import InventoryStatus
from repositories.forecast_repository import ForecastRepository
from repositories.recommendation_repository import RecommendationRepository
from services.decision_engine import recommend_production
from services.forecast_engine import forecast_product
from services.forecast_engine.base import Forecaster

logger = get_logger(__name__)


def fast_models() -> list[Forecaster]:
    """النماذج الخفيفة: بلا تدريب تكراري، فتُنهي الكتالوج في أجزاء من الثانية.

    تكفي 84% من هذا الكتالوج (المتقطّع) حيث تفوز أصلاً — راجع
    docs/ROADMAP.md. العائلة الكاملة تبقى خياراً صريحاً للمستخدم.
    """
    from services.forecast_engine.intermittent import CrostonForecaster, TSBForecaster
    from services.forecast_engine.naive import MovingAverageForecaster, NaiveForecaster

    return [
        NaiveForecaster(),
        MovingAverageForecaster(),
        CrostonForecaster(),
        TSBForecaster(),
    ]


@dataclass
class BatchReport:
    """حصيلة الدفعة. الفشل يُعدّ ولا يُبتلع."""

    total: int = 0
    succeeded: int = 0
    failed: list[tuple[str, str]] = field(default_factory=list)
    elapsed_seconds: float = 0.0

    @property
    def failure_count(self) -> int:
        return len(self.failed)


def run_batch(
    products: dict[str, Sequence[float]],
    *,
    steps: int = 6,
    use_fast_models: bool = True,
    db_path: str | None = None,
    inventory: dict[str, InventoryStatus] | None = None,
    granularity: str = "monthly",
    on_progress: Callable[[int, int, str], None] | None = None,
) -> BatchReport:
    """حساب وحفظ تنبؤ + توصية لكل منتج.

    Args:
        on_progress: يُستدعى بـ (المُنجَز، الإجمالي، اسم المنتج) بعد كل منتج.
        use_fast_models: True (افتراضي) = 4 نماذج، ~لحظي. False = 9 نماذج،
            دقائق على كتالوج كامل.
        inventory: {اسم المنتج: InventoryStatus}، إن وُجد ملف مخزون مرفوع.
            منتج غائب عن القاموس (أو القاموس None كله) يمرّ بلا مخزون —
            نفس الوضع الافتراضي قبل هذه الميزة، لا خطأ.
        granularity: حبيبة الكتالوج الفعلية (dataset.granularity) — تُمرَّر
            إلى forecast_product/recommend_production فتشتقّان الدورة
            الموسمية وتحويل مهلة التوريد الصحيحين. لا تؤثر على
            use_fast_models=True (Naive/MovingAverage/Croston/TSB بلا
            مفهوم موسمي أصلاً).

    منتج يفشل لا يُسقط الدفعة — يُسجَّل في report.failed ويستمر الباقي.
    منتج بلا مبيعات قط يفشل بـ InsufficientDataError، وهذا متوقَّع لا عطل.
    """
    import time

    # db_path=None يمرّ كما هو: المستودعات تحلّ الافتراضي عند النداء
    # (repositories.base.resolve_db_path). لا داعي لقراءة config هنا.
    forecast_repo = ForecastRepository(db_path=db_path)
    recommendation_repo = RecommendationRepository(db_path=db_path)
    models = fast_models() if use_fast_models else None

    report = BatchReport(total=len(products))
    started = time.perf_counter()

    for index, (name, series) in enumerate(products.items(), start=1):
        try:
            result = forecast_product(
                name, series, steps=steps, models=models, use_cache=True,
                granularity=granularity,
            )
            forecast_id = forecast_repo.save_result(result)
            product_inventory = inventory.get(name) if inventory else None
            recommendation = recommend_production(
                name, list(series), result.best, product_inventory,
                granularity=granularity,
            )
            recommendation_repo.save(recommendation, forecast_id=forecast_id)
            report.succeeded += 1
        except AppError as exc:
            # متوقَّع: منتجات بلا بيانات كافية. يُعدّ ولا يُوقف الدفعة.
            report.failed.append((name, exc.message))
        except Exception as exc:  # noqa: BLE001
            logger.exception("Batch item failed | product=%s", name)
            report.failed.append((name, f"{type(exc).__name__}: {exc}"))

        if on_progress is not None:
            on_progress(index, report.total, name)

    report.elapsed_seconds = time.perf_counter() - started
    logger.info(
        "Batch done | ok=%d | failed=%d | %.1fs",
        report.succeeded, report.failure_count, report.elapsed_seconds,
    )
    return report
