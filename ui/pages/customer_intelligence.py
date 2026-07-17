# ui/pages/customer_intelligence.py
"""
البُعد الثالث: العميل (Roadmap بند 5) — من يُركِّز عليه الخطر، من ينزف،
ومن ينمو. لا سؤال من هذه الأسئلة تجيبه أي صفحة أخرى: كلّها تحتاج عموداً
لا يقرأه parse_upload (العميل).

**تحليل فقط، لا إنشاء طلبات** — مدير المبيعات يستقبل الطلبات، لا يُصدرها
(نفس تحفّظ الخارطة بالحرف).

لا اتصال بقاعدة بيانات هنا إطلاقاً، خلافاً لملف الإنتاج الفعلي: كل ما
يلزم التحليل موجود داخل الملف المرفوع نفسه (تاريخ كامل بشهوره)، لا لقطة
تُقارَن بأخرى محفوظة مسبقاً. فيُحلَّل في ذاكرة الجلسة ويختفي — نفس نمط
ملفي المبيعات والمخزون بالضبط.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from core.exceptions import DataValidationError
from services.customer_analysis import (
    BLEEDING_THRESHOLD_PCT,
    bleeding_customers,
    concentration,
    growth_by_customer,
)
from services.ingest import (
    CustomerSalesDataset,
    customer_csv_template,
    guess_column,
    parse_customer_upload,
    parse_customer_upload_with_mapping,
    read_columns,
)
from ui.i18n import error as translate_error
from ui.i18n import format_month, t

SESSION_KEY = "uploaded_customer_sales"


def _render_mapping(uploaded) -> None:
    """نظير _render_column_mapping في ui/data_source.py — أربعة أدوار لا
    ثلاثة، وتطبيقها يكتب مباشرة في session_state هنا لا هناك."""
    try:
        columns = read_columns(uploaded.getvalue(), uploaded.name)
    except DataValidationError:
        return

    if len(columns) < 4:
        return

    with st.expander(t("data.map_columns"), expanded=True):
        st.caption(t("cust.map_columns_help"))

        placeholder = t("data.map_choose")
        options = [placeholder] + columns

        def _index(role: str) -> int:
            guess = guess_column(columns, role)
            return options.index(guess) if guess in options else 0

        suffix = uploaded.file_id
        product_col = st.selectbox(
            t("data.map_product"), options, index=_index("product"),
            key=f"_cust_map_product_{suffix}",
        )
        customer_col = st.selectbox(
            t("cust.map_customer"), options, index=_index("customer"),
            key=f"_cust_map_customer_{suffix}",
        )
        month_col = st.selectbox(
            t("data.map_month"), options, index=_index("month"),
            key=f"_cust_map_month_{suffix}",
        )
        quantity_col = st.selectbox(
            t("data.map_quantity"), options, index=_index("quantity"),
            key=f"_cust_map_quantity_{suffix}",
        )

        chosen = {product_col, customer_col, month_col, quantity_col}
        none_chosen = placeholder in chosen
        ready = not none_chosen and len(chosen) == 4

        if st.button(t("data.map_apply"), disabled=not ready,
                     use_container_width=True, key=f"_cust_map_apply_{suffix}"):
            try:
                parsed = parse_customer_upload_with_mapping(
                    uploaded.getvalue(), uploaded.name,
                    product_column=product_col, customer_column=customer_col,
                    month_column=month_col, quantity_column=quantity_col,
                )
            except DataValidationError as exc:
                st.error(t("cust.read_failed", detail=translate_error(exc)))
                return

            st.session_state[SESSION_KEY] = parsed
            st.rerun()

        if none_chosen:
            st.caption(t("data.map_incomplete"))
        elif not ready:
            st.caption(t("data.map_duplicate"))


def _render_upload_widget() -> None:
    dataset: CustomerSalesDataset | None = st.session_state.get(SESSION_KEY)

    with st.sidebar:
        st.header(t("cust.header"))

        if dataset is not None:
            st.success(t("cust.loaded", count=dataset.customer_count,
                         months=len(dataset.months)))
            if dataset.warnings:
                with st.expander(t("data.notes", count=len(dataset.warnings))):
                    for warning in dataset.warnings:
                        st.write(f"- {t('warn.' + warning.code, **warning.params)}")
            if st.button(t("cust.clear"), use_container_width=True):
                st.session_state.pop(SESSION_KEY, None)
                st.rerun()
            return

        st.caption(t("cust.none_active"))
        uploaded = st.file_uploader(
            t("cust.uploader"), type=["csv", "xlsx", "xls"],
            help=t("cust.uploader_help"), key="_customer_uploader",
        )
        st.download_button(
            t("cust.template"), data=customer_csv_template(),
            file_name="factorymind-customer-template.csv", mime="text/csv",
            use_container_width=True,
        )
        st.caption(t("cust.privacy_note"))

        if uploaded is not None:
            try:
                parsed = parse_customer_upload(uploaded.getvalue(), uploaded.name)
            except DataValidationError as exc:
                st.error(t("cust.read_failed", detail=translate_error(exc)))
                context = exc.context or {}
                if context.get("columns"):
                    st.caption(t("data.columns_found", columns=context["columns"]))
                if context.get("code") == "no_customer_columns":
                    _render_mapping(uploaded)
                return

            st.session_state[SESSION_KEY] = parsed
            st.rerun()


def _render_concentration(dataset: CustomerSalesDataset) -> None:
    rows = concentration(dataset)
    if not rows:
        st.info(t("cust.concentration_none"))
        return

    st.subheader(t("cust.concentration_title"))
    top_n = min(2, len(rows))
    st.caption(t(
        "cust.concentration_summary",
        count=top_n, pct=rows[top_n - 1].cumulative_share_pct,
    ))
    st.dataframe(
        pd.DataFrame([
            {
                t("cust.customer"): row.customer,
                t("common.quantity"): f"{row.quantity:,.0f}",
                t("cust.share"): f"{row.share_pct:.0f}%",
                t("cust.cumulative_share"): f"{row.cumulative_share_pct:.0f}%",
            }
            for row in rows
        ]),
        use_container_width=True, hide_index=True,
    )


def _render_bleeding(dataset: CustomerSalesDataset) -> None:
    rows = bleeding_customers(dataset)
    st.subheader(t("cust.bleeding_title"))
    if not rows:
        st.info(t("cust.bleeding_none", threshold=abs(BLEEDING_THRESHOLD_PCT)))
        return

    st.caption(t("cust.bleeding_help", threshold=abs(BLEEDING_THRESHOLD_PCT)))
    st.dataframe(
        pd.DataFrame([
            {
                t("cust.customer"): row.customer,
                t("cust.first_half"): f"{row.first_half_avg:,.0f}",
                t("cust.second_half"): f"{row.second_half_avg:,.0f}",
                t("cust.growth"): f"{row.growth_pct:.0f}%",
            }
            for row in rows
        ]),
        use_container_width=True, hide_index=True,
    )


def _render_growth(dataset: CustomerSalesDataset) -> None:
    rows = sorted(
        growth_by_customer(dataset),
        key=lambda r: (r.growth_pct is None, r.growth_pct),
        reverse=True,
    )
    with st.expander(t("cust.growth_title")):
        st.caption(t("cust.growth_help"))
        st.dataframe(
            pd.DataFrame([
                {
                    t("cust.customer"): row.customer,
                    t("cust.first_half"): f"{row.first_half_avg:,.0f}",
                    t("cust.second_half"): f"{row.second_half_avg:,.0f}",
                    t("cust.growth"): (
                        f"{row.growth_pct:.0f}%" if row.growth_pct is not None else "—"
                    ),
                }
                for row in rows
            ]),
            use_container_width=True, hide_index=True,
        )


def render(months: list[str], products: dict[str, list[float]]) -> None:
    st.title(t("cust.title"))
    st.caption(t("cust.subtitle"))

    _render_upload_widget()

    dataset: CustomerSalesDataset | None = st.session_state.get(SESSION_KEY)
    if dataset is None:
        st.info(t("cust.upload_first"))
        return

    _render_concentration(dataset)
    _render_bleeding(dataset)
    _render_growth(dataset)
