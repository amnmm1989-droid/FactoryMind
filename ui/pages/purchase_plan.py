# ui/pages/purchase_plan.py
"""
خطة الشراء — لمدير المشتريات: "كم أشتري من كل منتج لتغطية N شهراً القادمة؟"

الفرق عن executive.py: تلك تجيب "ماذا يحتاج انتباهي الشهر القادم؟" بأفق
شهر واحد ثابت، محفوظاً في قاعدة البيانات لكل الكتالوج. هذه الصفحة تجيب
سؤالاً مختلفاً طرحه مستخدم فعلي على الأداة مباشرة: أفق يختاره هو (3، 6،
12 شهراً)، بلا حفظ، ومُصدَّر Excel جاهزاً لإرساله.

منتج بكمية محسوبة دون نصف وحدة (متوقّف أو راكد غالباً) لا يظهر في ورقة
"أوامر الشراء" الأساسية — أمر شراء بصفر وحدة ضجيج لا قرار — لكنه يبقى
ظاهراً في قسم مستبعد + ورقة Excel منفصلة، لا محذوفاً بصمت.
"""
from __future__ import annotations

from io import BytesIO

import pandas as pd
import streamlit as st

from config import MAX_FORECAST_STEPS
from services.decision_engine import PurchaseOrderLine, build_purchase_plan
from ui.data_source import active_granularity, active_inventory, active_prices
from ui.i18n import t

DEFAULT_HORIZON_MONTHS = 6

# نفس عتبة executive.py: كمية دون هذا لا تستحق أمر شراء (Croston/TSB
# يُنتجان معدّلات كسرية، وأمر شراء لـ"0.2 وحدة" ليس قراراً).
MIN_ACTIONABLE_UNITS = 0.5

RESULT_KEY = "_purchase_plan_result"
PARAMS_KEY = "_purchase_plan_params"

# ترتيب الجدول حسب الأولوية لا حسب ترتيب الملف الأصلي: "اطلب الآن" أولاً،
# فـ"يمكن الانتظار"، فما لا حكم له (لا مهلة توريد أُدخلت أصلاً) — بلا مهلة
# توريد، كل الأسطر تتساوى هنا وتُرتَّب بالكمية فقط، فلا تأثير عملي لغيابها.
_URGENCY_ORDER = {"urgent": 0, "can_wait": 1, None: 2}


def _sort_key(line: PurchaseOrderLine) -> tuple[int, float]:
    return (_URGENCY_ORDER[line.urgency], -line.recommended_quantity)


def _signature(products: dict[str, list[float]], inventory, prices: dict[str, float]) -> str:
    """بصمة البيانات — نفس مبدأ executive.py::_dataset_signature بالحرف:
    تتغيّر بتغيّر الأرقام لا الأسماء فقط، فرفع ملف محدَّث يُبطل الخطة
    القديمة بدل عرضها كأنها لا تزال صحيحة. الأسعار تدخل البصمة لنفس
    السبب: ملف مخزون جديد بأسعار محدَّثة يجب أن يُعيد حساب التكلفة."""
    import hashlib

    digest = hashlib.sha256()
    for name in sorted(products):
        digest.update(name.encode("utf-8"))
        digest.update(b"|")
        digest.update(",".join(f"{v:.4f}" for v in products[name]).encode("utf-8"))
        digest.update(b"\n")
    for name in sorted(inventory or {}):
        digest.update(b"inv:")
        digest.update(name.encode("utf-8"))
        digest.update(b"|")
        digest.update(f"{inventory[name].current_stock:.4f}".encode("utf-8"))
        digest.update(b"\n")
    for name in sorted(prices):
        digest.update(b"price:")
        digest.update(name.encode("utf-8"))
        digest.update(b"|")
        digest.update(f"{prices[name]:.4f}".encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


def _confidence_label(note: str | None) -> str:
    return t(f"note.{note}") if note else ""


def _to_frame(lines: list[PurchaseOrderLine]) -> pd.DataFrame:
    return pd.DataFrame([
        {
            t("common.product"): line.product_name,
            t("common.recommended_qty"): round(line.recommended_quantity, 1),
            t("pplan.col_stock"): (
                round(line.current_stock, 1) if line.current_stock is not None else "—"
            ),
            t("pplan.col_class"): t(f"class.{line.demand_class}"),
            t("common.model"): line.model_name,
            t("common.wape"): f"{line.wape:.0f}%" if line.wape is not None else "—",
            t("common.level"): t(f"risk.{line.risk_level}"),
            t("pplan.col_urgency"): t(f"urgency.{line.urgency}") if line.urgency else "—",
            t("pplan.col_price"): (
                f"{line.unit_price:,.2f}" if line.unit_price is not None else "—"
            ),
            t("pplan.col_cost"): (
                f"{line.total_cost:,.0f}" if line.total_cost is not None else "—"
            ),
            t("pplan.col_note"): _confidence_label(line.confidence_note),
        }
        for line in lines
    ])


def _excel_bytes(
    active_lines: list[PurchaseOrderLine],
    excluded_lines: list[PurchaseOrderLine],
    skipped: list[tuple[str, str]],
) -> bytes:
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        _to_frame(active_lines).to_excel(
            writer, sheet_name=t("pplan.sheet_orders")[:31], index=False
        )
        if excluded_lines:
            _to_frame(excluded_lines).to_excel(
                writer, sheet_name=t("pplan.sheet_excluded")[:31], index=False
            )
        if skipped:
            pd.DataFrame([
                {t("common.product"): name, t("pplan.col_reason"): reason}
                for name, reason in skipped
            ]).to_excel(writer, sheet_name=t("pplan.sheet_skipped")[:31], index=False)
    return buffer.getvalue()


def render(months: list[str], products: dict[str, list[float]]) -> None:
    st.title(t("pplan.title"))
    st.caption(t("pplan.subtitle"))

    inventory = active_inventory()
    prices = active_prices()
    granularity = active_granularity()

    with st.sidebar:
        st.header(t("pplan.header"))
        horizon = st.number_input(
            t("pplan.horizon_label"), min_value=1, max_value=MAX_FORECAST_STEPS,
            value=DEFAULT_HORIZON_MONTHS, step=1, help=t("pplan.horizon_help"),
        )
        lead_time_days = st.number_input(
            t("pplan.lead_time_label"), min_value=0, value=0, step=1,
            help=t("pplan.lead_time_help"),
        )
        full_family = st.checkbox(
            t("common.all_nine_models"), value=False, help=t("common.all_nine_help"),
        )
        compute = st.button(
            t("pplan.compute"), icon=":material/refresh:", use_container_width=True
        )

    current_signature = _signature(products, inventory, prices)
    current_params = (int(horizon), int(lead_time_days), full_family, granularity, current_signature)

    if compute:
        progress = st.progress(0.0, text=t("exec.computing"))

        def on_progress(done: int, total: int, name: str) -> None:
            progress.progress(done / total, text=f"{done}/{total} — {name[:40]}")

        plan = build_purchase_plan(
            products, horizon_months=int(horizon), inventory=inventory,
            prices=prices, lead_time_days=int(lead_time_days) or None,
            granularity=granularity, use_fast_models=not full_family,
            on_progress=on_progress,
        )
        progress.empty()
        st.session_state[RESULT_KEY] = plan
        st.session_state[PARAMS_KEY] = current_params

    plan = st.session_state.get(RESULT_KEY)
    if plan is None:
        st.info(t("pplan.empty"))
        return

    if st.session_state.get(PARAMS_KEY) != current_params:
        st.warning(t("pplan.stale_warning"), icon=":material/warning:")

    active_lines = sorted(
        (line for line in plan.lines if line.recommended_quantity >= MIN_ACTIONABLE_UNITS),
        key=_sort_key,
    )
    excluded_lines = [
        line for line in plan.lines if line.recommended_quantity < MIN_ACTIONABLE_UNITS
    ]
    low_confidence_count = sum(1 for line in plan.lines if line.confidence_note == "cold_start")

    columns = st.columns(4)
    columns[0].metric(t("pplan.kpi_assessed"), len(plan.lines))
    columns[1].metric(t("pplan.kpi_to_order"), len(active_lines))
    columns[2].metric(t("pplan.kpi_low_confidence"), low_confidence_count)
    columns[3].metric(
        t("pplan.kpi_total_qty"),
        f"{sum(line.recommended_quantity for line in active_lines):,.0f}",
    )

    priced_lines = [line for line in active_lines if line.total_cost is not None]
    if priced_lines:
        st.caption(t(
            "pplan.kpi_total_cost",
            total=sum(line.total_cost for line in priced_lines),
            priced=len(priced_lines), total_lines=len(active_lines),
        ))

    if not inventory:
        st.caption(t("pplan.no_stock_note"))

    st.subheader(t("pplan.orders_title"))
    if active_lines:
        st.dataframe(_to_frame(active_lines), use_container_width=True, hide_index=True)
    else:
        st.info(t("pplan.nothing_to_order"))

    st.download_button(
        t("pplan.download_excel"),
        data=_excel_bytes(active_lines, excluded_lines, plan.skipped),
        file_name=f"purchase_plan_{plan.horizon_months}m.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )

    if excluded_lines:
        with st.expander(t("pplan.excluded_title", count=len(excluded_lines))):
            st.caption(t("pplan.excluded_help"))
            st.dataframe(_to_frame(excluded_lines), use_container_width=True, hide_index=True)

    if plan.skipped:
        with st.expander(t("pplan.skipped_title", count=len(plan.skipped))):
            for name, reason in plan.skipped[:50]:
                st.write(f"- **{name}** — {reason}")
