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
from services.ingest import Dataset, parse_upload, to_csv_template

logger = get_logger(__name__)

SESSION_KEY = "uploaded_dataset"


def _privacy_note() -> str:
    """ما يحدث لملف المستخدم فعلاً — لا وعد تسويقي.

    الصياغة تختلف بالوضع لأن الحقيقة تختلف: مستضافاً هناك خادم مشترك
    والطمأنة عنه؛ محلياً لا خادم أصلاً. لكن الجوهر واحد في الوضعين —
    الملف المرفوع لا يُكتب في قاعدة البيانات إطلاقاً.
    """
    if is_hosted():
        return (
            "🔒 ملفك يُحلَّل في الذاكرة ولا يُحفَظ على الخادم. "
            "يختفي بإغلاق التبويب، ولا يراه زائر آخر."
        )
    return (
        "🔒 ملفك في ذاكرة الجلسة ولا يُكتب في قاعدة البيانات. "
        "يختفي بإعادة التشغيل."
    )


@st.cache_data(show_spinner="تحميل بيانات العرض...")
def _demo_dataset() -> tuple[list[str], dict[str, list[float]]]:
    """بيانات العرض المرفقة — 185 صنف بنّ.

    cache_data يشاركها بين الجلسات، وهذا مقبول: إنها بيانات عامة في
    المستودع لا بيانات زائر.
    """
    from utils.data_loader import get_repository

    return get_repository().load_data()


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


def clear_upload() -> None:
    st.session_state.pop(SESSION_KEY, None)


def render_upload_widget() -> None:
    """أداة الرفع — تُعرض في الشريط الجانبي لكل صفحة.

    موضعها في الشريط لا في صفحة مستقلة: الرفع ليس خطوة تُنجَز مرة
    وتُنسى، بل تبديل للسياق يجب أن يكون في متناول اليد من كل صفحة.
    """
    dataset: Dataset | None = st.session_state.get(SESSION_KEY)

    with st.sidebar:
        st.header("📁 البيانات")

        if dataset is not None:
            st.success(
                f"ملفك: **{dataset.product_count}** منتج × "
                f"**{dataset.month_count}** شهر"
            )
            # الطمأنة تُعرَض هنا لا قبل الرفع فقط: بيانات المستخدم محمّلة
            # الآن، وهذه اللحظة بالضبط هي التي يحتاج فيها الجواب على
            # "أين ذهب ملفي؟". عرضها قبل الرفع وحده يجعلها تختفي عند
            # الحاجة إليها.
            st.caption(_privacy_note())
            if dataset.warnings:
                with st.expander(f"⚠️ ملاحظات على الملف ({len(dataset.warnings)})"):
                    for warning in dataset.warnings:
                        st.write(f"- {warning}")
            if st.button("العودة لبيانات العرض", use_container_width=True):
                clear_upload()
                st.rerun()
            return

        st.caption("بيانات العرض معروضة الآن (185 صنف بنّ). ارفع ملفك لتحليله.")
        uploaded = st.file_uploader(
            "CSV أو Excel", type=["csv", "xlsx", "xls"],
            help="عمود للمنتج + عمود لكل شهر. أو ثلاثة أعمدة: منتج/شهر/كمية.",
        )

        st.download_button(
            "⬇ نموذج CSV", data=to_csv_template(),
            file_name="factorymind-template.csv", mime="text/csv",
            use_container_width=True,
        )

        st.caption(_privacy_note())

        if uploaded is not None:
            try:
                parsed = parse_upload(uploaded.getvalue(), uploaded.name)
            except DataValidationError as exc:
                st.error(f"تعذّرت قراءة الملف: {exc.message}")
                context = exc.context or {}
                if context.get("columns"):
                    st.caption(f"الأعمدة التي وجدتها: {context['columns']}")
                return

            st.session_state[SESSION_KEY] = parsed
            logger.info(
                "Upload accepted | products=%d | months=%d | warnings=%d",
                parsed.product_count, parsed.month_count, len(parsed.warnings),
            )
            st.rerun()
