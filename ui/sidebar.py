# ui/sidebar.py
"""
ضوابط عرض المحلّل: أي منتجات، وأي مدى، وهل تُبرَز الشواذّ.

ضوابط التنبؤ (عدد الفترات، حدود الثقة، اختيار النموذج) أُزيلت مع التنبؤ
نفسه — راجع ui/dashboard.py وservices/product_analysis_service.py.
"""
import streamlit as st

from ui.i18n import format_month, t


def render_sidebar(months, product_names, granularity="monthly"):
    """عرض الشريط الجانبي وإرجاع الخيارات المختارة.

    granularity: حبيبة الملف الفعلية — تُسمّى بها الوحدات ("أسابيع" لا
    "أشهر" ثابتة) في نطاق المدى.
    """
    many = t(f"granularity.many.{granularity}")

    with st.sidebar:
        st.header(t("old.control_panel"))

        # اختيار المنتج (متعدد) — session_state قد يحمل اختياراً من رفع
        # سابق بمنتجات مختلفة تماماً؛ التصفية هنا تمنع StreamlitAPIException
        # عند تمرير قيمة افتراضية لم تعد ضمن الخيارات الحالية.
        valid_previous = [p for p in st.session_state.selected_products if p in product_names]
        selected_products = st.multiselect(
            t("old.select_products"),
            product_names,
            default=valid_previous if valid_previous else [product_names[0]]
        )
        st.session_state.selected_products = selected_products

        if not selected_products:
            st.warning(t("old.pick_one"))
            st.stop()

        # نطاق المدى — شريط نطاق واحد بدل قائمتين منسدلتين. البداية لا
        # يمكن أن تتجاوز النهاية هنا بنيوياً (يمنعه المقبض نفسه)، فتحقّق
        # "old.bad_range" السابق صار مستحيل الحدوث لا مجرد نادر — حُذف معه.
        month_indices = list(range(len(months)))
        from_idx, to_idx = st.select_slider(
            t("old.month_range", many=many), options=month_indices,
            value=(0, len(months) - 1), format_func=lambda i: format_month(months[i]),
        )

        show_outliers = st.toggle(t("old.outliers"), value=True)
        st.session_state.show_outliers = show_outliers

        # لا زرّ "تشغيل" هنا عمداً: الصفحة وصفية وتُصيَّر عند كل تغيير في
        # الضوابط تلقائياً. كان الزرّ موجوداً ونتيجته تُهمَل — يضغطه
        # المستخدم وينتظر أثراً لا يأتي، وهو أسوأ من غيابه.
        return {
            'selected_products': selected_products,
            'from_idx': from_idx,
            'to_idx': to_idx,
            'show_outliers': show_outliers,
        }
