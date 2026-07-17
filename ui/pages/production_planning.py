# ui/pages/production_planning.py
"""
تخطيط الإنتاج — تحويل توصية النظام إلى قرار إنسان.

الفصل بين الجدولين متعمّد منذ Phase 2:
    recommendations   = اقتراح النظام
    production_plans  = ما قرّره المخطِّط فعلاً
قد يوافق أو يخالف. الفصل يسمح لاحقاً بقياس: كم مرة تُتَّبع التوصيات؟
وهل النتائج أفضل حين تُتَّبع؟ (planned_quantity مقابل actual_quantity).

⚠️ حدّ معروف: الكميات هنا لا تخصم المخزون، لأن جدول inventory فارغ حتى
Phase 5. محرك القرار يخصم المخزون المتاح حين يُمرَّر إليه — ولا شيء
يُمرَّر بعد. المعروض هو الطلب المتوقَّع كاملاً.
"""
from __future__ import annotations

import sqlite3

import pandas as pd
import streamlit as st

from config import DATABASE_PATH
from core.logging_config import get_logger
from repositories.recommendation_repository import RecommendationRepository

logger = get_logger(__name__)

STATUS_LABELS = {
    "draft": "مسودّة",
    "approved": "معتمدة",
    "in_progress": "قيد التنفيذ",
    "completed": "مكتملة",
    "cancelled": "ملغاة",
}


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DATABASE_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    return conn


def _months() -> list[tuple[int, str]]:
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT id, name FROM months ORDER BY sort_order DESC"
        ).fetchall()
        return [(row["id"], row["name"]) for row in rows]
    finally:
        conn.close()


def _save_plan(product: str, month_id: int, quantity: float, status: str,
               notes: str) -> None:
    """حفظ خطة. UNIQUE(product_id, month_id) -> خطة واحدة لكل منتج/شهر."""
    conn = _connect()
    try:
        product_id = conn.execute(
            "SELECT id FROM products WHERE name = ?", (product,)
        ).fetchone()["id"]
        conn.execute(
            """
            INSERT INTO production_plans
                (product_id, month_id, planned_quantity, status, notes)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(product_id, month_id) DO UPDATE SET
                planned_quantity = excluded.planned_quantity,
                status = excluded.status,
                notes = excluded.notes,
                updated_at = datetime('now')
            """,
            (product_id, month_id, quantity, status, notes or None),
        )
        conn.commit()
    finally:
        conn.close()


def _plans() -> pd.DataFrame:
    conn = _connect()
    try:
        rows = conn.execute(
            """
            SELECT p.name AS product, m.name AS month, pp.planned_quantity,
                   pp.actual_quantity, pp.status, pp.notes, pp.updated_at
            FROM production_plans pp
            JOIN products p ON pp.product_id = p.id
            JOIN months m ON pp.month_id = m.id
            ORDER BY pp.updated_at DESC
            """
        ).fetchall()
    finally:
        conn.close()

    if not rows:
        return pd.DataFrame()
    frame = pd.DataFrame([dict(row) for row in rows])
    frame["status"] = frame["status"].map(lambda s: STATUS_LABELS.get(s, s))
    return frame.rename(columns={
        "product": "المنتج", "month": "الشهر",
        "planned_quantity": "المخطَّط", "actual_quantity": "الفعلي",
        "status": "الحالة", "notes": "ملاحظات", "updated_at": "آخر تحديث",
    })


def render(months: list[str], products: dict[str, list[float]]) -> None:
    st.title("🏭 تخطيط الإنتاج")
    st.caption(
        "التوصية اقتراح النظام؛ الخطة قرارك. الفصل بينهما يسمح بقياس "
        "جودة التوصيات لاحقاً."
    )

    st.warning(
        "**الكميات لا تخصم المخزون** — جدول `inventory` فارغ حتى Phase 5. "
        "المعروض هو الطلب المتوقَّع كاملاً، لا الفجوة بينه وبين ما لديك.",
        icon="⚠️",
    )

    repository = RecommendationRepository(db_path=DATABASE_PATH)
    month_options = _months()

    st.subheader("إنشاء خطة")
    with st.form("new_plan"):
        columns = st.columns([3, 2])
        product = columns[0].selectbox("المنتج", sorted(products))
        month_label = columns[1].selectbox(
            "الشهر", [name for _, name in month_options]
        )

        recommendation = repository.latest_for_product(product)
        suggested = round(recommendation.recommended_quantity) if recommendation else 0
        if recommendation:
            st.caption(f"توصية النظام: **{suggested:,}** — {recommendation.reason}")
        else:
            st.caption(
                "لا توصية محفوظة لهذا المنتج. شغّل الحساب من **النظرة التنفيذية**."
            )

        columns = st.columns([2, 2, 4])
        quantity = columns[0].number_input(
            "الكمية المخطَّطة", min_value=0.0, value=float(suggested), step=10.0
        )
        status = columns[1].selectbox(
            "الحالة", list(STATUS_LABELS), format_func=lambda s: STATUS_LABELS[s]
        )
        notes = columns[2].text_input("ملاحظات (اختياري)")

        if st.form_submit_button("حفظ الخطة", use_container_width=True):
            month_id = next(mid for mid, name in month_options if name == month_label)
            _save_plan(product, month_id, quantity, status, notes)
            if recommendation and quantity != suggested:
                st.info(
                    f"خالفت التوصية ({suggested:,} → {quantity:,.0f}). "
                    "الفارق مسجَّل — وهو ما سيقيس جودة التوصيات لاحقاً."
                )
            st.success(f"حُفظت خطة {product[:40]} لشهر {month_label}.")

    st.subheader("الخطط المسجَّلة")
    frame = _plans()
    if frame.empty:
        st.info("لا خطط بعد.")
    else:
        st.dataframe(frame, use_container_width=True, hide_index=True)
