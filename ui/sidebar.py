# ui/sidebar.py
import streamlit as st

from ui.i18n import format_month, t

# رموز مستقرة لا تتغيّر بتغيّر اللغة — انظر التعليق عند الاستخدام
MODEL_CODES = ("ets", "sarima")
from config import DEFAULT_FORECAST_STEPS, MAX_FORECAST_STEPS

def render_sidebar(months, product_names):
    """عرض الشريط الجانبي وإرجاع الخيارات المختارة"""
    with st.sidebar:
        st.header(t("old.control_panel"))

        # اختيار المنتج (متعدد)
        selected_products = st.multiselect(
            t("old.select_products"),
            product_names,
            default=st.session_state.selected_products if st.session_state.selected_products else [product_names[0]]
        )
        st.session_state.selected_products = selected_products

        if not selected_products:
            st.warning(t("old.pick_one"))
            st.stop()

        # نطاق الأشهر
        month_indices = list(range(len(months)))
        from_idx = st.selectbox(t("old.from_month"), month_indices,
                                 format_func=lambda i: format_month(months[i]), index=0)
        to_idx = st.selectbox(t("old.to_month"), month_indices,
                               format_func=lambda i: format_month(months[i]),
                               index=len(months)-1)

        if from_idx > to_idx:
            st.error(t("old.bad_range"))
            st.stop()

        # إعدادات التنبؤ
        st.subheader(t("old.forecast_settings"))
        forecast_steps = st.slider(t("old.forecast_months"), min_value=1, max_value=MAX_FORECAST_STEPS, value=DEFAULT_FORECAST_STEPS, step=1)
        show_confidence = st.checkbox(t("old.show_confidence"), value=True)
        # رموز لا تسميات: dashboard.py يقارن بالقيمة، وترجمة التسمية كانت
        # ستكسر المقارنة بصمت فلا يعمل SARIMA أبداً بلا أي خطأ.
        forecast_model = st.selectbox(
            t("old.forecast_model"), MODEL_CODES,
            format_func=lambda code: t(f"model.{code}"),
        )

        # تحليلات إضافية
        st.subheader(t("old.extra_analyses"))
        show_trend = st.checkbox(t("old.trend"), value=st.session_state.get('show_trend', True))
        st.session_state.show_trend = show_trend
        show_seasonal = st.checkbox(t("old.seasonal"), value=st.session_state.get('show_seasonal', True))
        st.session_state.show_seasonal = show_seasonal
        show_correlation = st.checkbox(t("old.correlation"), value=st.session_state.get('show_correlation', True))
        st.session_state.show_correlation = show_correlation
        show_distribution = st.checkbox(t("old.distribution"), value=st.session_state.get('show_distribution', True))
        st.session_state.show_distribution = show_distribution
        show_outliers = st.checkbox(t("old.outliers"), value=True)

        st.markdown("---")
        run = st.button(t("old.run"), use_container_width=True)

        return {
            'selected_products': selected_products,
            'from_idx': from_idx,
            'to_idx': to_idx,
            'forecast_steps': forecast_steps,
            'show_confidence': show_confidence,
            'forecast_model': forecast_model,
            'show_trend': show_trend,
            'show_seasonal': show_seasonal,
            'show_correlation': show_correlation,
            'show_distribution': show_distribution,
            'show_outliers': show_outliers,
        }