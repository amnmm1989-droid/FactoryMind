"""
حفظ/قراءة جدول production_plans (Phase 2، migration 007).

وُجد هذا الملف متأخّراً: كان SQL الخطط يعيش في ui/pages/production_planning.py
— صفحةُ واجهة تفتح اتصالها بنفسها وتكتب INSERT ... ON CONFLICT بيدها،
وحدها بين الصفحات الخمس. وكان الثمن ملموساً لا نظرياً:

**source_recommendation_id لم يُكتب قط.** العمود معرَّف في 007 بمفتاح
أجنبي، وتعليق الـmigration يقول إن الفصل بين recommendations
و production_plans موجود ليقيس "كم مرة تُتَّبع توصياتنا؟ وهل النتائج أفضل
حين تُتَّبع؟". الصفحة كانت تعرض التوصية للمخطِّط، ثم تحفظ قراره بلا رابط
إليها — فيبقى العمود NULL أبداً، ويصير السؤالُ الذي بُني الجدول لأجله بلا
جواب. حفظ الفصل شكلاً ومحوُه معنى.

هذا ما تفعله الطبقة المفقودة: عقدٌ يُكتب مرة ويُختبَر، بدل استعلام يكتبه
من يفكّر في الشاشة لا في الجدول.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from typing import Any

from core.exceptions import DataAccessError
from core.logging_config import get_logger
from repositories.base import resolve_db_path

logger = get_logger(__name__)

# القيم المسموحة في العمود status — مطابِقة لقيد CHECK في 007.
# مكرَّرة هنا عمداً كي تُرفض القيمة الخاطئة برسالة مفهومة قبل أن ترتطم
# بقيد SQLite، وtest_migrations يحرس تطابق القائمتين.
STATUS_CODES = ("draft", "approved", "in_progress", "completed", "cancelled")


@dataclass
class ActualsReport:
    """حصيلة مطابقة ملف الإنتاج الفعلي — كل خلية (منتج × شهر) لها مصير.

    لا رقم إجمالي واحد يخفي التفاصيل: منتج غير معروف ليس نفس شهر غير
    مفهوم، وليس نفس خلية بلا خطة محفوظة أصلاً — كل حالة تعني شيئاً مختلفاً
    للمستخدم، فتُعدّ منفصلة لا تُطوى في "فشل" واحد.
    """

    updated: int = 0
    unknown_products: list[str] = field(default_factory=list)
    unknown_months: list[str] = field(default_factory=list)
    # (منتج، تسمية شهر) بلا خطة محفوظة لهما — إنتاج فعلي حدث فعلاً، لكن لا
    # planned_quantity يُقارَن به. لا تُخترَع له خطة بكمية مخطَّطة مجهولة.
    no_plan: list[tuple[str, str]] = field(default_factory=list)


class ProductionPlanRepository:
    """كتابة/قراءة جدول production_plans."""

    def __init__(self, db_path: str | None = None) -> None:
        self.db_path = resolve_db_path(db_path)

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA foreign_keys = ON")
        conn.row_factory = sqlite3.Row
        return conn

    def _product_id(self, conn: sqlite3.Connection, product_name: str) -> int:
        row = conn.execute(
            "SELECT id FROM products WHERE name = ?", (product_name,)
        ).fetchone()
        if row is None:
            raise DataAccessError(
                f"منتج غير موجود في قاعدة البيانات: {product_name}",
                context={"product": product_name},
            )
        return row["id"]

    def month_options(self) -> list[tuple[int, str]]:
        """(id, name) لكل شهر — الأحدث أولاً.

        هنا لا في SQLiteRepository.get_months() لأن تلك تُرجع الأسماء وحدها،
        والخطة مفتاحها month_id. والمحور الزمني نفسه الذي تُقاس عليه
        المبيعات — لا محور مستقل.
        """
        conn = self._get_connection()
        try:
            rows = conn.execute(
                "SELECT id, name FROM months ORDER BY sort_order DESC"
            ).fetchall()
            return [(row["id"], row["name"]) for row in rows]
        finally:
            conn.close()

    def save(
        self,
        product_name: str,
        month_id: int,
        planned_quantity: float,
        status: str = "draft",
        notes: str | None = None,
        *,
        source_recommendation_id: int | None = None,
    ) -> None:
        """حفظ خطة. UNIQUE(product_id, month_id) -> خطة واحدة لكل منتج/شهر.

        Args:
            source_recommendation_id: التوصية التي رآها المخطِّط ساعة القرار.
                تمريرها هو ما يجعل سؤال "كم مرة تُتَّبع توصياتنا؟" قابلاً
                للإجابة — وإغفالها هو ما جعله بلا جواب طوال وجود الجدول.
                None مسموح: خطة لمنتج بلا توصية محسوبة قرارٌ صحيح لا نقص.

        Raises:
            DataAccessError: منتج غير موجود، أو حالة غير مسموحة، أو فشل SQL.
        """
        if status not in STATUS_CODES:
            raise DataAccessError(
                f"حالة غير مسموحة: {status}",
                context={"status": status, "allowed": list(STATUS_CODES)},
            )

        conn = self._get_connection()
        try:
            product_id = self._product_id(conn, product_name)
            conn.execute(
                """
                INSERT INTO production_plans
                    (product_id, month_id, planned_quantity, status, notes,
                     source_recommendation_id)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(product_id, month_id) DO UPDATE SET
                    planned_quantity = excluded.planned_quantity,
                    status = excluded.status,
                    notes = excluded.notes,
                    source_recommendation_id = excluded.source_recommendation_id,
                    updated_at = datetime('now')
                """,
                (product_id, month_id, planned_quantity, status, notes or None,
                 source_recommendation_id),
            )
            conn.commit()
            logger.info(
                "Plan saved | product=%s | month_id=%d | qty=%.0f | source_rec=%s",
                product_name, month_id, planned_quantity, source_recommendation_id,
            )
        except DataAccessError:
            conn.rollback()
            raise
        except sqlite3.Error as exc:
            conn.rollback()
            raise DataAccessError(
                f"فشل حفظ الخطة: {exc}",
                cause=exc,
                context={"product": product_name, "month_id": month_id},
            ) from exc
        finally:
            conn.close()

    def all_plans(self) -> list[dict[str, Any]]:
        """كل الخطط — الأحدث تعديلاً أولاً.

        صفوف خام لا كيانات: لا يوجد كيان domain لخطة إنتاج بعد، واختراع
        واحد هنا لأجل جدول عرض يسبق الحاجة. حين يظهر منطق أعمال حول الخطط
        (قياس الالتزام، مقارنة planned بـactual) يُبنى الكيان حينها.
        """
        conn = self._get_connection()
        try:
            rows = conn.execute(
                """
                SELECT p.name AS product, m.name AS month, pp.planned_quantity,
                       pp.actual_quantity, pp.status, pp.notes, pp.updated_at
                FROM production_plans pp
                JOIN products p ON pp.product_id = p.id
                JOIN months m ON pp.month_id = m.id
                ORDER BY pp.updated_at DESC, pp.id DESC
                """
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    def adherence(self) -> dict[str, int]:
        """كم خطة تبع صاحبُها التوصية، وكم خالفها.

        السؤال الذي بُني الجدول لأجله (تعليق 007)، وصار قابلاً للإجابة الآن
        بعد أن صار source_recommendation_id يُكتب.

        `unlinked` ليست صفراً مقنّعاً: خطط حُفظت قبل ربط العمود، أو لمنتج
        بلا توصية محسوبة. عدّها "مخالِفة" يكذب، وإخفاؤها يجمّل النسبة.
        """
        conn = self._get_connection()
        try:
            row = conn.execute(
                """
                SELECT
                    COUNT(*) AS total,
                    SUM(CASE WHEN pp.source_recommendation_id IS NULL
                             THEN 1 ELSE 0 END) AS unlinked,
                    SUM(CASE WHEN pp.source_recommendation_id IS NOT NULL
                              AND ABS(pp.planned_quantity - r.recommended_quantity) < 0.5
                             THEN 1 ELSE 0 END) AS followed
                FROM production_plans pp
                LEFT JOIN recommendations r
                       ON r.id = pp.source_recommendation_id
                """
            ).fetchone()
        finally:
            conn.close()

        total = row["total"] or 0
        unlinked = row["unlinked"] or 0
        followed = row["followed"] or 0
        return {
            "total": total,
            "followed": followed,
            "overridden": total - unlinked - followed,
            "unlinked": unlinked,
        }

    def record_actuals(
        self, months: list[str], products: dict[str, list[float]]
    ) -> ActualsReport:
        """يطابق ملف الإنتاج الفعلي (نفس شكل ملف المبيعات: منتج × شهر) مع
        القاعدة، ويملأ actual_quantity لخطط محفوظة فعلاً.

        المطابقة بالتاريخ المفسَّر لا بنص التسمية: ملف المستخدم يسمّي
        الشهر بلغته وشكله ("Jan 2024")، بينما months.name تخزّن التسمية
        الخام كما وصلت من بيانات العرض ("يناير 2023") — نفس ما يفعله
        format_month في الاتجاه المعاكس.

        لا تُنشئ خطة جديدة: إنتاج فعلي لمنتج/شهر بلا صفّ production_plans
        محفوظ له أصلاً لا شيء يُقارَن به — planned_quantity غير معروفة،
        واختراع 0 كذبٌ (يعني قراراً واعياً بلا إنتاج، لا غياب خطة). تُعدّ
        في no_plan صراحةً بدل ذلك.

        Raises:
            DataAccessError: فشل SQL أثناء التحديث.
        """
        from services.ingest import parse_month_label

        conn = self._get_connection()
        try:
            month_rows = conn.execute("SELECT id, name FROM months").fetchall()
            month_id_by_date: dict[tuple[int, int], int] = {}
            for row in month_rows:
                parsed = parse_month_label(row["name"])
                if parsed is not None:
                    month_id_by_date[(parsed.year, parsed.month)] = row["id"]

            report = ActualsReport()
            for product_name, values in products.items():
                product_row = conn.execute(
                    "SELECT id FROM products WHERE name = ?", (product_name,)
                ).fetchone()
                if product_row is None:
                    report.unknown_products.append(product_name)
                    continue
                product_id = product_row["id"]

                for month_label, quantity in zip(months, values):
                    parsed = parse_month_label(month_label)
                    month_id = (
                        month_id_by_date.get((parsed.year, parsed.month))
                        if parsed is not None else None
                    )
                    if month_id is None:
                        report.unknown_months.append(month_label)
                        continue

                    cursor = conn.execute(
                        """
                        UPDATE production_plans
                        SET actual_quantity = ?, updated_at = datetime('now')
                        WHERE product_id = ? AND month_id = ?
                        """,
                        (quantity, product_id, month_id),
                    )
                    if cursor.rowcount == 0:
                        report.no_plan.append((product_name, month_label))
                    else:
                        report.updated += 1

            conn.commit()
            logger.info(
                "Actuals applied | updated=%d | no_plan=%d | unknown_products=%d "
                "| unknown_months=%d",
                report.updated, len(report.no_plan),
                len(report.unknown_products), len(report.unknown_months),
            )
            return report
        except sqlite3.Error as exc:
            conn.rollback()
            raise DataAccessError(
                f"فشل تسجيل الإنتاج الفعلي: {exc}", cause=exc
            ) from exc
        finally:
            conn.close()
