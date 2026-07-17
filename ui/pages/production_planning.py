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
from core.runtime_mode import is_hosted
from repositories.recommendation_repository import RecommendationRepository
from ui.data_source import active_dataset
from ui.i18n import format_month, format_reason, t

logger = get_logger(__name__)

STATUS_CODES = ("draft", "approved", "in_progress", "completed", "cancelled")


def _status_label(code: str) -> str:
    return t(f"status.{code}")


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
    frame["status"] = frame["status"].map(_status_label)
    frame["month"] = frame["month"].map(format_month)
    return frame.rename(columns={
        "product": t("common.product"), "month": t("common.month"),
        "planned_quantity": t("plan.planned"), "actual_quantity": t("plan.actual"),
        "status": t("plan.status"), "notes": t("plan.notes_column"),
        "updated_at": t("plan.updated"),
    })


def render(months: list[str], products: dict[str, list[float]]) -> None:
    st.title(t("plan.title"))
    st.caption(t("plan.subtitle"))

    # الخطط تُكتب في production_plans، ومفتاحها الأجنبي يشير إلى جدول
    # products — الذي يحمل بيانات العرض لا ملف المستخدم. حفظ خطة لمنتج
    # مرفوع سيفشل بـ DataAccessError. الرفض هنا صريح ومُفسَّر بدل انهيار
    # عند الضغط على "حفظ".
    _, _, is_user_data = active_dataset()
    if is_user_data or is_hosted():
        reason = t("plan.reason_user_data" if is_user_data else "plan.reason_hosted")
        st.info(t("plan.local_only", reason=reason), icon="ℹ️")
        st.code("git clone https://github.com/amnmm1989-droid/FactoryMind\n"
                "cd FactoryMind && python migrate.py && streamlit run app.py",
                language="bash")
        st.caption(t("plan.local_only_note"))
        return

    st.warning(t("plan.inventory_warning"), icon="⚠️")

    repository = RecommendationRepository(db_path=DATABASE_PATH)
    month_options = _months()

    st.subheader(t("plan.create"))
    with st.form("new_plan"):
        columns = st.columns([3, 2])
        product = columns[0].selectbox(t("common.product"), sorted(products))
        month_label = columns[1].selectbox(
            t("common.month"), [name for _, name in month_options],
            format_func=format_month,
        )

        recommendation = repository.latest_for_product(product)
        suggested = round(recommendation.recommended_quantity) if recommendation else 0
        if recommendation:
            st.caption(t("plan.system_suggests", quantity=suggested,
                         reason=format_reason(recommendation)))
        else:
            st.caption(t("plan.no_recommendation"))

        columns = st.columns([2, 2, 4])
        quantity = columns[0].number_input(
            t("plan.planned_qty"), min_value=0.0, value=float(suggested), step=10.0
        )
        status = columns[1].selectbox(
            t("plan.status"), STATUS_CODES, format_func=_status_label
        )
        notes = columns[2].text_input(t("plan.notes"))

        if st.form_submit_button(t("plan.save"), use_container_width=True):
            month_id = next(mid for mid, name in month_options if name == month_label)
            _save_plan(product, month_id, quantity, status, notes)
            if recommendation and quantity != suggested:
                st.info(t("plan.overridden", suggested=suggested, actual=quantity))
            st.success(t("plan.saved", product=product[:40],
                         month=format_month(month_label)))

    st.subheader(t("plan.existing"))
    frame = _plans()
    if frame.empty:
        st.info(t("plan.none_yet"))
    else:
        st.dataframe(frame, use_container_width=True, hide_index=True)
