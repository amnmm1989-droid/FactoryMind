# ui/data_source.py
"""
مصدر بيانات الجلسة: ملف المستخدم أو بيانات العرض المرفقة.

قبل هذا الملف كان `data/data.json` هو المصدر الوحيد، مثبَّتاً في
config.py. الآن كل جلسة تحمل بياناتها في `st.session_state` — وهو
معزول لكل زائر بحكم تصميم Streamlit، فلا يرى أحد بيانات أحد.

بيانات المستخدم **لا تُكتب في القرص أبداً** في الوضع المستضاف. راجع
core/runtime_mode.py.
"""
from __future__ import annotations

import streamlit as st

from core.exceptions import DataValidationError
from core.logging_config import get_logger
from core.runtime_mode import is_hosted
from services.ingest import (
    Dataset,
    guess_column,
    parse_upload,
    parse_upload_with_mapping,
    read_columns,
    to_csv_template,
)
from ui.i18n import error as translate_error
from ui.i18n import t

logger = get_logger(__name__)

SESSION_KEY = "uploaded_dataset"


def _privacy_note() -> str:
    """ما يحدث لملف المستخدم فعلاً — لا وعد تسويقي.

    الصياغة تختلف بالوضع لأن الحقيقة تختلف: مستضافاً هناك خادم مشترك
    والطمأنة عنه؛ محلياً لا خادم أصلاً. لكن الجوهر واحد في الوضعين —
    الملف المرفوع لا يُكتب في قاعدة البيانات إطلاقاً.
    """
    return t("data.privacy_hosted") if is_hosted() else t("data.privacy_local")


@st.cache_data(show_spinner=False)
def _demo_dataset() -> tuple[list[str], dict[str, list[float]]]:
    """بيانات العرض المرفقة — كتالوج اصطناعي (scripts/generate_demo_data.py).

    cache_data يشاركها بين الجلسات، وهذا مقبول: إنها بيانات عامة في
    المستودع لا بيانات زائر.
    """
    from utils.data_loader import get_repository

    return get_repository().load_data()  # spinner معطَّل: النص يُقيَّم قبل
    # أن تُعرف لغة الجلسة (cache_data يُزخرَف عند الاستيراد)، فيتجمّد
    # بلغة واحدة. التحميل لحظي على أي حال بعد أول مرة.


def active_dataset() -> tuple[list[str], dict[str, list[float]], bool]:
    """بيانات الجلسة الحالية.

    Returns:
        (months, products, is_user_data)
    """
    dataset: Dataset | None = st.session_state.get(SESSION_KEY)
    if dataset is not None:
        return dataset.months, dataset.products, True

    months, products = _demo_dataset()
    return months, products, False


def active_categories() -> dict[str, str]:
    """فئات المنتجات إن وُجدت — من ملف المستخدم (عمود فئة اختياري اكتُشف
    عند الرفع) أو من products_meta.category لبيانات العرض المرفقة.

    {} صريحة لا استثناء: أغلب الملفات لن تحمل فئات، وهذا متوقَّع لا نقص.
    التوفيق الهرمي (services/reconciliation.py) يتعامل مع {} بصمت — لا قسم
    "حسب الفئة" يظهر أصلاً حين لا توجد فئات.
    """
    dataset: Dataset | None = st.session_state.get(SESSION_KEY)
    if dataset is not None:
        return dataset.categories

    from utils.data_loader import get_repository

    return get_repository().get_categories()


def clear_upload() -> None:
    st.session_state.pop(SESSION_KEY, None)


def _render_column_mapping(uploaded) -> None:
    """شاشة ربط الأعمدة اليدوي — حين يفشل تخمين services.ingest.

    السيناريو الذي وُجدت لأجله: تصديرة SAP الطويلة بعمود Material لا
    Product — PRODUCT_HINTS لم تلتقطه، فسقط الملف إلى الشكل العريض وردّ
    "لم يُفهَم أي عمود كشهر": رسالة تصف عرَضاً (Period ليس تاريخاً) لا
    السبب الحقيقي (لم يُتعرَّف على عمود المنتج). بدل الرفض التام، تُعرض
    أعمدة الملف الفعلية ويختار المستخدم أدوارها — ثلاث نقرات بدل رفض.

    مفاتيح الودجت مربوطة بـ uploaded.file_id لا ثابتة: ملف جديد يحمل
    file_id جديداً، فتبدأ القوائم فارغة لا بقيم ملف سابق قد لا تكون من
    خياراته أصلاً.
    """
    try:
        columns = read_columns(uploaded.getvalue(), uploaded.name)
    except DataValidationError:
        return  # الملف نفسه غير مقروء — لا فائدة من عرض أعمدة لا وجود لها

    if len(columns) < 3:
        return  # لا يكفي عدد الأعمدة لثلاثة أدوار مختلفة

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
            key=f"_map_product_{suffix}",
        )
        month_col = st.selectbox(
            t("data.map_month"), options, index=_index("month"),
            key=f"_map_month_{suffix}",
        )
        quantity_col = st.selectbox(
            t("data.map_quantity"), options, index=_index("quantity"),
            key=f"_map_quantity_{suffix}",
        )

        chosen = {product_col, month_col, quantity_col}
        none_chosen = placeholder in chosen
        ready = not none_chosen and len(chosen) == 3

        if st.button(t("data.map_apply"), disabled=not ready, use_container_width=True):
            try:
                parsed = parse_upload_with_mapping(
                    uploaded.getvalue(), uploaded.name,
                    product_column=product_col, month_column=month_col,
                    quantity_column=quantity_col,
                )
            except DataValidationError as exc:
                st.error(t("data.read_failed", detail=translate_error(exc)))
                return

            st.session_state[SESSION_KEY] = parsed
            logger.info(
                "Upload accepted via manual column mapping | products=%d | months=%d",
                parsed.product_count, parsed.month_count,
            )
            st.rerun()

        if none_chosen:
            st.caption(t("data.map_incomplete"))
        elif not ready:
            st.caption(t("data.map_duplicate"))


def render_upload_widget() -> None:
    """أداة الرفع — تُعرض في الشريط الجانبي لكل صفحة.

    موضعها في الشريط لا في صفحة مستقلة: الرفع ليس خطوة تُنجَز مرة
    وتُنسى، بل تبديل للسياق يجب أن يكون في متناول اليد من كل صفحة.
    """
    dataset: Dataset | None = st.session_state.get(SESSION_KEY)

    with st.sidebar:
        st.header(t("data.header"))

        if dataset is not None:
            st.success(t("data.your_file", products=dataset.product_count,
                         months=dataset.month_count))
            # الطمأنة تُعرَض هنا لا قبل الرفع فقط: بيانات المستخدم محمّلة
            # الآن، وهذه اللحظة بالضبط هي التي يحتاج فيها الجواب على
            # "أين ذهب ملفي؟". عرضها قبل الرفع وحده يجعلها تختفي عند
            # الحاجة إليها.
            st.caption(_privacy_note())
            if dataset.warnings:
                with st.expander(t("data.notes", count=len(dataset.warnings))):
                    for warning in dataset.warnings:
                        st.write(f"- {t('warn.' + warning.code, **warning.params)}")
            if st.button(t("data.back_to_demo"), use_container_width=True):
                clear_upload()
                st.rerun()
            return

        st.caption(t("data.demo_active"))
        uploaded = st.file_uploader(
            t("data.uploader"), type=["csv", "xlsx", "xls"],
            help=t("data.uploader_help"),
        )

        st.download_button(
            t("data.template"), data=to_csv_template(),
            file_name="factorymind-template.csv", mime="text/csv",
            use_container_width=True,
        )

        st.caption(_privacy_note())

        if uploaded is not None:
            try:
                parsed = parse_upload(uploaded.getvalue(), uploaded.name)
            except DataValidationError as exc:
                st.error(t("data.read_failed", detail=translate_error(exc)))
                context = exc.context or {}
                if context.get("columns"):
                    st.caption(t("data.columns_found", columns=context["columns"]))
                # no_months تحديداً: قد يعني تخميناً فاشلاً على شكل طويل
                # (عمود المنتج/الشهر/الكمية بأسماء غير معروفة)، لا رفضاً
                # نهائياً. أخطاء أخرى (ملف فارغ، غير مقروء) لا يفيدها ربط
                # أعمدة لا وجود لها فعلياً.
                if context.get("code") == "no_months":
                    _render_column_mapping(uploaded)
                return

            st.session_state[SESSION_KEY] = parsed
            logger.info(
                "Upload accepted | products=%d | months=%d | warnings=%d",
                parsed.product_count, parsed.month_count, len(parsed.warnings),
            )
            st.rerun()
