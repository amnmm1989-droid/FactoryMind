# ui/pages/production_planning.py
"""
تخطيط الإنتاج — تحويل توصية النظام إلى قرار إنسان.

الفصل بين الجدولين متعمّد منذ Phase 2:
    recommendations   = اقتراح النظام
    production_plans  = ما قرّره المخطِّط فعلاً
قد يوافق أو يخالف. الفصل يسمح بقياس: كم مرة تُتَّبع التوصيات؟

وهو وعدٌ لم يكن يُنفَّذ: كانت هذه الصفحة تكتب SQL الخطط بنفسها — وحدها
بين الصفحات الخمس — وتُغفل source_recommendation_id، فيبقى NULL أبداً
ويصير السؤال بلا جواب رغم أن الجدول بُني لأجله. الآن يملك
ProductionPlanRepository الاستعلامات، ويكتب الرابط، ويُجيب عبر adherence().

"هل النتائج أفضل حين تُتَّبع؟" يحتاج actual_quantity — يُملأ الآن عبر رفع
ملف الإنتاج الفعلي (نفس شكل ملف المبيعات: منتج × شهر)، يطابق التاريخ لا
النص مع الخطط المحفوظة (ProductionPlanRepository.record_actuals). ⚠️ محلي
فقط: لا يظهر زر الرفع مع بيانات مرفوعة أو في الوضع المستضاف — نفس سبب حجب
نموذج إنشاء الخطة، وبنفس المفتاح الأجنبي بالضبط.

الكميات تخصم المخزون المتاح الآن حين يرفع المستخدم ملف مخزون (عمودان:
منتج + مخزون حالي، عبر ui/data_source.py::active_inventory) — قبل هذا
كانت تُعرض الطلب المتوقَّع كاملاً دوماً لأن لا شيء كان يُمرَّر لمحرك
القرار. ⚠️ حدّ باقٍ حتى الآن: الملف يحمل الرصيد فقط، لا مهلة التوريد أو
تذبذبها؛ فمخزون الأمان (safety_stock) ونقطة إعادة الطلب (reorder_point)
يبقيان صفراً افتراضياً، ولا حساب احتمالية حقيقية (appendix، Safety stock)
ممكناً بلا تلك البيانات.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from core.exceptions import DataValidationError
from core.logging_config import get_logger
from core.runtime_mode import is_hosted
from repositories.production_plan_repository import (
    STATUS_CODES,
    ProductionPlanRepository,
)
from repositories.recommendation_repository import RecommendationRepository
from services.ingest import (
    guess_column,
    parse_actuals_upload,
    parse_actuals_upload_with_mapping,
    read_columns,
    to_csv_template,
)
from ui.data_source import active_dataset, active_inventory
from ui.i18n import error as translate_error
from ui.i18n import format_month, format_reason, t

logger = get_logger(__name__)


def _status_label(code: str) -> str:
    return t(f"status.{code}")


def _adherence_summary_params(stats: dict[str, int]) -> dict[str, float | int] | None:
    """حساب بلا عرض — قابل للاختبار بمعزل عن Streamlit.

    None يعني: لا خطة يمكن الحكم عليها بعد (كل الخطط بلا توصية مرتبطة، أو
    لا خطط أصلاً). النسبة على judged = total - unlinked لا على total: خطة
    بلا توصية مرتبطة لا يمكن الحكم عليها متابعةً أو مخالفةً أصلاً، فقسمتها
    على الإجمالي تُصغِّر النسبة كذباً — نفس مبدأ adherence() نفسه.
    """
    judged = stats["total"] - stats["unlinked"]
    if judged <= 0:
        return None
    return {
        "judged": judged,
        "followed": stats["followed"],
        "overridden": stats["overridden"],
        "unlinked": stats["unlinked"],
        "pct": stats["followed"] / judged * 100,
    }


def _render_adherence(stats: dict[str, int]) -> None:
    """"كم مرة تُتَّبع توصياتنا؟" — السؤال الذي بُني الجدول لأجله في 007،
    وصار قابلاً للإجابة بعد أن صار source_recommendation_id يُكتب فعلاً.
    """
    params = _adherence_summary_params(stats)
    if params is None:
        st.caption(t("plan.adherence_none"))
        return

    st.subheader(t("plan.adherence_title"))
    st.caption(t("plan.adherence_summary", **params))


def _plans_frame(rows: list[dict]) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame()
    frame = pd.DataFrame(rows)
    frame["status"] = frame["status"].map(_status_label)
    frame["month"] = frame["month"].map(format_month)
    return frame.rename(columns={
        "product": t("common.product"), "month": t("common.month"),
        "planned_quantity": t("plan.planned"), "actual_quantity": t("plan.actual"),
        "status": t("plan.status"), "notes": t("plan.notes_column"),
        "updated_at": t("plan.updated"),
    })


def _render_actuals_report(report) -> None:
    if report.updated:
        st.success(t("plan.actuals_applied", count=report.updated))
    if report.no_plan:
        with st.expander(t("plan.actuals_no_plan", count=len(report.no_plan))):
            st.caption(t("plan.actuals_no_plan_help"))
            for product_name, month_label in report.no_plan[:30]:
                st.write(f"- {product_name} — {format_month(month_label)}")
    unmatched_products = len(report.unknown_products)
    unmatched_months = len(set(report.unknown_months))
    if unmatched_products or unmatched_months:
        st.caption(t(
            "plan.actuals_unmatched",
            products=unmatched_products, months=unmatched_months,
        ))
    if not report.updated and not report.no_plan and not unmatched_products \
            and not unmatched_months:
        st.info(t("plan.actuals_empty"))


def _render_actuals_mapping(uploaded) -> None:
    """نظير _render_column_mapping في ui/data_source.py — لكن التطبيق هنا
    يستدعي record_actuals مباشرة، لا يخزّن في session_state: لا معنى
    لبقاء ملف إنتاج فعلي "نشطاً" بين عمليات رفع، فهو حدث لا حالة جلسة.
    """
    try:
        columns = read_columns(uploaded.getvalue(), uploaded.name)
    except DataValidationError:
        return

    if len(columns) < 3:
        return

    with st.expander(t("data.map_columns"), expanded=True):
        st.caption(t("data.map_columns_help"))

        placeholder = t("data.map_choose")
        options = [placeholder] + columns

        def _index(role: str) -> int:
            guess = guess_column(columns, role)
            return options.index(guess) if guess in options else 0

        suffix = uploaded.file_id
        product_col = st.selectbox(
            t("data.map_product"), options, index=_index("product"),
            key=f"_actuals_map_product_{suffix}",
        )
        month_col = st.selectbox(
            t("data.map_month"), options, index=_index("month"),
            key=f"_actuals_map_month_{suffix}",
        )
        quantity_col = st.selectbox(
            t("data.map_quantity"), options, index=_index("quantity"),
            key=f"_actuals_map_quantity_{suffix}",
        )

        chosen = {product_col, month_col, quantity_col}
        none_chosen = placeholder in chosen
        ready = not none_chosen and len(chosen) == 3

        if st.button(t("data.map_apply"), disabled=not ready,
                     use_container_width=True, key=f"_actuals_map_apply_{suffix}"):
            try:
                actual_months, actual_products = parse_actuals_upload_with_mapping(
                    uploaded.getvalue(), uploaded.name,
                    product_column=product_col, month_column=month_col,
                    quantity_column=quantity_col,
                )
            except DataValidationError as exc:
                st.error(t("stock.read_failed", detail=translate_error(exc)))
                return

            report = ProductionPlanRepository().record_actuals(
                actual_months, actual_products
            )
            _render_actuals_report(report)

        if none_chosen:
            st.caption(t("data.map_incomplete"))
        elif not ready:
            st.caption(t("data.map_duplicate"))


def _render_actuals_upload() -> None:
    """رفع ملف الإنتاج الفعلي — نفس شكل ملف المبيعات تماماً (منتج × شهر)،
    فقط أن الكمية أُنتجت لا بيعت. Roadmap "بند 4" — النصف الثاني من
    السؤال الذي تركه adherence() بلا جواب: "هل النتائج أفضل حين تُتَّبع
    التوصية؟" يحتاج actual_quantity، لا planned_quantity وحدها.

    محلي فقط عمداً — لا زر رفع هنا في وضع البيانات المرفوعة أو المستضاف؛
    نفس سبب حجب نموذج إنشاء الخطة أعلاه بالضبط: production_plans يشير
    بمفتاح أجنبي إلى products المحلية، لا ملف المستخدم.
    """
    with st.expander(t("plan.actuals_header"), expanded=False):
        st.caption(t("plan.actuals_help"))
        uploaded = st.file_uploader(
            t("stock.uploader"), type=["csv", "xlsx", "xls"],
            key="_actuals_uploader",
        )
        st.download_button(
            t("plan.actuals_template"), data=to_csv_template(),
            file_name="factorymind-actuals-template.csv", mime="text/csv",
        )

        if uploaded is None:
            return

        try:
            actual_months, actual_products = parse_actuals_upload(
                uploaded.getvalue(), uploaded.name
            )
        except DataValidationError as exc:
            st.error(t("stock.read_failed", detail=translate_error(exc)))
            context = exc.context or {}
            if context.get("code") == "no_actuals_columns":
                _render_actuals_mapping(uploaded)
            return

        report = ProductionPlanRepository().record_actuals(
            actual_months, actual_products
        )
        _render_actuals_report(report)


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
        # تعليمات يتبعها زائر فعلاً، فتُختبَر لا تُكتب من الذاكرة:
        # كانت تقول `python migrate.py` — لم تعد لازمة بعد أن صار الإقلاع
        # يبني القاعدة — وتُغفل تثبيت الاعتماديات، فالاستنساخ يفشل بلا
        # streamlit أصلاً. سطرٌ ناقص هنا يعني زائراً عالقاً في طرفيته.
        st.code(
            "git clone https://github.com/amnmm1989-droid/FactoryMind\n"
            "cd FactoryMind\n"
            "pip install -r requirements.lock.txt\n"
            "streamlit run app.py",
            language="bash",
        )
        st.caption(t("plan.local_only_note"))
        return

    if active_inventory():
        st.caption(t("plan.inventory_active"))
    else:
        st.warning(t("plan.inventory_warning"), icon="⚠️")

    recommendations = RecommendationRepository()
    plans = ProductionPlanRepository()
    month_options = plans.month_options()

    st.subheader(t("plan.create"))
    with st.form("new_plan"):
        columns = st.columns([3, 2])
        product = columns[0].selectbox(t("common.product"), sorted(products))
        month_label = columns[1].selectbox(
            t("common.month"), [name for _, name in month_options],
            format_func=format_month,
        )

        # المعرّف لا الكيان وحده: هو ما يُكتب في source_recommendation_id
        # فيُسجَّل أي توصية رآها المخطِّط ساعة قراره.
        found = recommendations.latest_with_id_for_product(product)
        recommendation_id, recommendation = found if found else (None, None)
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
            plans.save(product, month_id, quantity, status, notes,
                       source_recommendation_id=recommendation_id)
            if recommendation and quantity != suggested:
                st.info(t("plan.overridden", suggested=suggested, actual=quantity))
            st.success(t("plan.saved", product=product[:40],
                         month=format_month(month_label)))

    _render_adherence(plans.adherence())
    _render_actuals_upload()

    st.subheader(t("plan.existing"))
    frame = _plans_frame(plans.all_plans())
    if frame.empty:
        st.info(t("plan.none_yet"))
    else:
        st.dataframe(frame, use_container_width=True, hide_index=True)
