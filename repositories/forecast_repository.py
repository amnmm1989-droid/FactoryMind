# repositories/forecast_repository.py
"""
حفظ نتائج المحرك في الجداول التي أنشأتها Phase 2.

الفصل عن المحرك مقصود: المحرك يحسب ولا يعرف قاعدة بيانات؛ هذا الملف
يخزّن ولا يعرف نموذجاً. من أراد المحرك بلا تخزين (اختبار، سكربت) لا
يدفع ثمن قاعدة بيانات، ومن أراد التخزين لا يمسّ منطق التنبؤ.

## استيراد `EngineResult` من `services` — استثناء مقصود، لا سهو

فحصٌ آليّ لاتجاه الطبقات يُعلّم السطر أدناه مخالفةً: `repositories`
تستورد من `services`، وهي طبقة أعلى. الحكم صحيح بالقاعدة وخاطئ بالمعنى،
فيُوثَّق هنا كي لا "يُصلَح" لاحقاً إلى ما هو أسوأ:

**لماذا لا يُنقَل `EngineResult` إلى `domain`؟** لأنه يجرّ معه ثلاثة
أنواع من طبقة الخدمة: `ForecastOutput` (عقد `Forecaster` نفسه)،
و`ModelMetrics`، و`DemandProfile`. نقلها جميعاً إلى `domain` يجعل الطبقة
الأعمق تعرف تفاصيل المحرك — وهي المخالفة نفسها مقلوبةً ومضخَّمة.

**ولماذا لا يُخفى خلف `TYPE_CHECKING`؟** لأن ذلك يُسكت الفاحص ولا يغيّر
شيئاً: الاعتماد المفاهيمي باقٍ، وكلفته قِيست ~50ms فوق pandas التي
تُحمَّل هنا أصلاً — لا مكتبة ثقيلة تُجَرّ (قِيس: لا statsforecast ولا
sklearn ولا xgboost).

**الأصحّ أن القاعدة قاصرة هنا.** وظيفة هذا الملف المعلَنة هي حفظ حصيلة
المحرك؛ معرفةُ شكلِ ما يحفظه ليست تسرّباً بل تعريفه. البديل — أن يعرف
المحرك المستودع — هو الاقتران الحقيقي الذي يتجنّبه هذا الفصل أصلاً.
"""
from __future__ import annotations

import json
import sqlite3
from typing import Any

from core.exceptions import DataAccessError
from core.logging_config import get_logger
from repositories.base import connect, product_id, resolve_db_path
from services.forecast_engine.engine import EngineResult

logger = get_logger(__name__)


class ForecastRepository:
    """كتابة/قراءة جداول forecasts و model_performance."""

    def __init__(self, db_path: str | None = None) -> None:
        self.db_path = resolve_db_path(db_path)

    def _get_connection(self) -> sqlite3.Connection:
        return connect(self.db_path)

    def _product_id(self, conn: sqlite3.Connection, product_name: str) -> int:
        return product_id(conn, product_name)

    def save_result(self, result: EngineResult) -> int:
        """حفظ حصيلة المحرك: تنبؤ الفائز + تقييم كل نموذج جُرِّب.

        الاثنان في معاملة واحدة: تنبؤ محفوظ بلا سجل تقييم يعني توصية
        إنتاج لا نعرف على أي أساس اختيرت — وهو بالضبط ما يفترض
        model_performance أن يمنعه.

        Returns:
            id الصف في forecasts.
        """
        conn = self._get_connection()
        try:
            conn.execute("BEGIN")
            product_id = self._product_id(conn, result.product_name)
            best = result.best

            cursor = conn.execute(
                """
                INSERT INTO forecasts (
                    product_id, model_name, horizon, forecast_values,
                    lower_bound, upper_bound, mae, rmse, mape, wape, fva,
                    data_hash
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    product_id,
                    best.model_name,
                    len(best.forecast_values),
                    json.dumps(best.forecast_values),
                    json.dumps(best.lower_bound),
                    json.dumps(best.upper_bound),
                    best.mae,
                    best.rmse,
                    best.mape,
                    best.wape,
                    best.fva,
                    result.data_hash,
                ),
            )
            forecast_id = cursor.lastrowid

            # كل نموذج جُرِّب — بما فيه الخاسر. سجل القرار لا نتيجته فقط.
            # forecast_id يربطها بجولتها: بدونه، تقييمات جولات مختلفة
            # لنفس المنتج تختلط ويصبح "من فاز آخر مرة؟" بلا جواب.
            for evaluation in result.evaluations:
                metrics = evaluation.metrics
                conn.execute(
                    """
                    INSERT INTO model_performance (
                        product_id, model_name, mae, rmse, mape, wape,
                        training_duration_ms, is_best, data_hash, forecast_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        product_id,
                        evaluation.model_name,
                        metrics.mae if metrics else None,
                        metrics.rmse if metrics else None,
                        metrics.mape if metrics else None,
                        metrics.wape if metrics else None,
                        evaluation.duration_ms,
                        1 if evaluation.model_name == result.best_model_name else 0,
                        result.data_hash,
                        forecast_id,
                    ),
                )

            conn.execute("COMMIT")
            logger.info(
                "Forecast saved | product=%s | model=%s | id=%d",
                result.product_name, best.model_name, forecast_id,
            )
            return forecast_id
        except sqlite3.Error as exc:
            conn.execute("ROLLBACK")
            raise DataAccessError(
                f"فشل حفظ التنبؤ: {exc}",
                cause=exc,
                context={"product": result.product_name},
            ) from exc
        finally:
            conn.close()

    def latest_forecast(self, product_name: str) -> dict[str, Any] | None:
        """أحدث تنبؤ محفوظ لمنتج، أو None."""
        conn = self._get_connection()
        try:
            row = conn.execute(
                """
                SELECT f.*, p.name AS product_name
                FROM forecasts f
                JOIN products p ON f.product_id = p.id
                WHERE p.name = ?
                ORDER BY f.generated_at DESC, f.id DESC
                LIMIT 1
                """,
                (product_name,),
            ).fetchone()

            if row is None:
                return None

            record = dict(row)
            for column in ("forecast_values", "lower_bound", "upper_bound"):
                record[column] = json.loads(record[column])
            return record
        finally:
            conn.close()

    def find_cached(self, product_name: str, data_hash: str) -> dict[str, Any] | None:
        """تنبؤ محفوظ لنفس البيانات بالضبط — أي ما زال صالحاً.

        بصمة مختلفة = البيانات تغيّرت = التنبؤ القديم لا يعني شيئاً.
        """
        conn = self._get_connection()
        try:
            row = conn.execute(
                """
                SELECT f.id FROM forecasts f
                JOIN products p ON f.product_id = p.id
                WHERE p.name = ? AND f.data_hash = ?
                ORDER BY f.generated_at DESC, f.id DESC
                LIMIT 1
                """,
                (product_name, data_hash),
            ).fetchone()
            return self.latest_forecast(product_name) if row else None
        finally:
            conn.close()

    def model_ranking(self, product_name: str) -> list[dict[str, Any]]:
        """ترتيب نماذج *آخر جولة تقييم* لمنتج — الأدق أولاً.

        هذا هو الاستعلام الذي يجيب: "هل يستحق XGBoost وقته على هذا المنتج؟"

        النطاق هو forecast_id لا data_hash: model_performance تاريخي، ونفس
        البيانات قد تُقيَّم مراراً. الحصر بالبصمة كان يخلط الجولات ويُرجع
        عدة نماذج مُعلَّمة is_best=1 — كل واحد فائز جولته.
        """
        conn = self._get_connection()
        try:
            rows = conn.execute(
                """
                SELECT mp.model_name, mp.mae, mp.rmse, mp.mape, mp.wape,
                       mp.training_duration_ms, mp.is_best, mp.evaluated_at
                FROM model_performance mp
                WHERE mp.forecast_id = (
                    SELECT f.id FROM forecasts f
                    JOIN products p ON f.product_id = p.id
                    WHERE p.name = ?
                    ORDER BY f.generated_at DESC, f.id DESC
                    LIMIT 1
                )
                ORDER BY mp.rmse IS NULL, mp.rmse
                """,
                (product_name,),
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()
