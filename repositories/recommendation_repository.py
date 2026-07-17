# repositories/recommendation_repository.py
"""
حفظ التوصيات في جدول recommendations (Phase 2).

الأعمدة تقابل ProductionRecommendation + RiskScore المدمج عموداً بعمود،
فالبناء من الصف مباشر بلا طبقة تحويل.
"""
from __future__ import annotations

import sqlite3
from typing import Any

from core.exceptions import DataAccessError
from core.logging_config import get_logger
from domain.entities import ProductionRecommendation, RiskScore
from repositories.base import resolve_db_path

logger = get_logger(__name__)


class RecommendationRepository:
    """كتابة/قراءة جدول recommendations."""

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

    def save(
        self,
        recommendation: ProductionRecommendation,
        *,
        forecast_id: int | None = None,
    ) -> int:
        """حفظ توصية.

        Args:
            forecast_id: التنبؤ الذي وُلّدت منه — الأثر الذي يجيب لاحقاً
                "لماذا أوصى النظام بهذا الرقم؟". None مسموح (توصية يدوية
                أو استكشافية)، لكن تمريره هو الوضع الصحيح في المسار الآلي.

        Returns:
            id الصف في recommendations.
        """
        risk = recommendation.risk
        conn = self._get_connection()
        try:
            product_id = self._product_id(conn, recommendation.product_name)
            cursor = conn.execute(
                """
                INSERT INTO recommendations (
                    product_id, recommended_quantity, reason,
                    expected_demand_change_pct, risk_score, demand_volatility,
                    stock_depletion_risk, forecast_accuracy_penalty,
                    seasonality_factor, growth_rate, forecast_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    product_id,
                    recommendation.recommended_quantity,
                    recommendation.reason,
                    recommendation.expected_demand_change_pct,
                    risk.score if risk else None,
                    risk.demand_volatility if risk else None,
                    risk.stock_depletion_risk if risk else None,
                    risk.forecast_accuracy_penalty if risk else None,
                    risk.seasonality_factor if risk else None,
                    risk.growth_rate if risk else None,
                    forecast_id,
                ),
            )
            conn.commit()
            recommendation_id = cursor.lastrowid
            logger.info(
                "Recommendation saved | product=%s | qty=%.0f | id=%d",
                recommendation.product_name, recommendation.recommended_quantity,
                recommendation_id,
            )
            return recommendation_id
        except sqlite3.Error as exc:
            conn.rollback()
            raise DataAccessError(
                f"فشل حفظ التوصية: {exc}",
                cause=exc,
                context={"product": recommendation.product_name},
            ) from exc
        finally:
            conn.close()

    def _to_entity(self, row: sqlite3.Row) -> ProductionRecommendation:
        """بناء الكيان من الصف.

        risk يُعاد فقط إن كانت الدرجة محفوظة — توصية بلا خطورة محسوبة
        تُرجع risk=None لا RiskScore بأصفار كاذبة.
        """
        record = dict(row)
        risk = None
        if record["risk_score"] is not None:
            risk = RiskScore(
                product_name=record["product_name"],
                score=record["risk_score"],
                demand_volatility=record["demand_volatility"],
                stock_depletion_risk=record["stock_depletion_risk"],
                forecast_accuracy_penalty=record["forecast_accuracy_penalty"],
                seasonality_factor=record["seasonality_factor"],
                growth_rate=record["growth_rate"],
            )

        return ProductionRecommendation(
            product_name=record["product_name"],
            recommended_quantity=record["recommended_quantity"],
            reason=record["reason"],
            expected_demand_change_pct=record["expected_demand_change_pct"],
            risk=risk,
        )

    def latest_with_id_for_product(
        self, product_name: str
    ) -> tuple[int, ProductionRecommendation] | None:
        """أحدث توصية لمنتج مع معرّفها في الجدول، أو None.

        المعرّف مطلوب لأن production_plans.source_recommendation_id يربط
        قرار المخطِّط بالتوصية التي رآها. والكيان لا يحمله: كائنات domain
        نقية تُبنى قبل أن تُحفظ، فلا معرّف لها ساعة الحساب. فيُعاد بجانبه
        لا بداخله.
        """
        conn = self._get_connection()
        try:
            row = conn.execute(
                """
                SELECT r.*, p.name AS product_name
                FROM recommendations r
                JOIN products p ON r.product_id = p.id
                WHERE p.name = ?
                ORDER BY r.generated_at DESC, r.id DESC
                LIMIT 1
                """,
                (product_name,),
            ).fetchone()
            return (row["id"], self._to_entity(row)) if row else None
        finally:
            conn.close()

    def latest_for_product(self, product_name: str) -> ProductionRecommendation | None:
        """أحدث توصية لمنتج، أو None."""
        found = self.latest_with_id_for_product(product_name)
        return found[1] if found else None

    def highest_risk(self, limit: int = 10) -> list[ProductionRecommendation]:
        """أعلى المنتجات خطورة — أحدث توصية لكل منتج، مرتّبة تنازلياً.

        الاستعلام الذي تبنى عليه شاشة "ما الذي يحتاج انتباهي؟" في Phase 6.

        التوصيات بلا درجة خطورة تُستبعد لا تُعامَل كصفر: قائمة "الأعلى
        خطورة" التي يتذيّلها منتج لم تُحسب خطورته أصلاً تكذب على قارئها.
        """
        conn = self._get_connection()
        try:
            rows = conn.execute(
                """
                SELECT r.*, p.name AS product_name
                FROM recommendations r
                JOIN products p ON r.product_id = p.id
                WHERE r.risk_score IS NOT NULL
                  AND r.id = (
                      SELECT r2.id FROM recommendations r2
                      WHERE r2.product_id = r.product_id
                      ORDER BY r2.generated_at DESC, r2.id DESC
                      LIMIT 1
                  )
                ORDER BY r.risk_score DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
            return [self._to_entity(row) for row in rows]
        finally:
            conn.close()

    def history_for_product(self, product_name: str, limit: int = 20) -> list[dict[str, Any]]:
        """سجل التوصيات لمنتج — الأحدث أولاً."""
        conn = self._get_connection()
        try:
            rows = conn.execute(
                """
                SELECT r.*, p.name AS product_name
                FROM recommendations r
                JOIN products p ON r.product_id = p.id
                WHERE p.name = ?
                ORDER BY r.generated_at DESC, r.id DESC
                LIMIT ?
                """,
                (product_name, limit),
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()
