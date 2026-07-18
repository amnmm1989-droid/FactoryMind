# ui/sidebar.py
import streamlit as st

from ui.i18n import format_month, t

# رموز مستقرة لا تتغيّر بتغيّر اللغة — انظر التعليق عند الاستخدام
MODEL_CODES = ("ets", "sarima")
ANALYSIS_CODES = ("trend", "seasonal", "correlation", "distribution", "outliers")
from config import DEFAULT_FORECAST_STEPS, MAX_FORECAST_STEPS

def render_sidebar(months, product_names):
    """عرض الشريط الجانبي وإرجاع الخيارات المختارة"""
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

        # نطاق الأشهر — شريط نطاق واحد بدل قائمتين منسدلتين. البداية لا
        # يمكن أن تتجاوز النهاية هنا بنيوياً (يمنعه المقبض نفسه)، فتحقّق
        # "old.bad_range" السابق صار مستحيل الحدوث لا مجرد نادر — حُذف معه.
        month_indices = list(range(len(months)))
        from_idx, to_idx = st.select_slider(
            t("old.month_range"), options=month_indices,
            value=(0, len(months) - 1), format_func=lambda i: format_month(months[i]),
        )

        # إعدادات التنبؤ
        st.subheader(t("old.forecast_settings"))
        forecast_steps = st.slider(t("old.forecast_months"), min_value=1, max_value=MAX_FORECAST_STEPS, value=DEFAULT_FORECAST_STEPS, step=1)
        show_confidence = st.toggle(t("old.show_confidence"), value=True)
        # رموز لا تسميات: dashboard.py يقارن بالقيمة، وترجمة التسمية كانت
        # ستكسر المقارنة بصمت فلا يعمل SARIMA أبداً بلا أي خطأ.
        forecast_model = st.selectbox(
            t("old.forecast_model"), MODEL_CODES,
            format_func=lambda code: t(f"model.{code}"),
        )

        # تحليلات إضافية — شرائح اختيار متعدد واحدة بدل خمسة مربعات اختيار
        # منفصلة؛ 2-5 خيارات مرئية كلها دفعة واحدة هي بالضبط ما صُمِّم له
        # st.pills. الرموز مستقرة لنفس سبب MODEL_CODES أعلاه.
        default_analyses = [
            code for code in ANALYSIS_CODES
            if st.session_state.get(f"show_{code}", True)
        ]
        selected_analyses = st.pills(
            t("old.extra_analyses"), ANALYSIS_CODES, selection_mode="multi",
            default=default_analyses, format_func=lambda code: t(f"old.{code}"),
        )
        show_trend = "trend" in selected_analyses
        show_seasonal = "seasonal" in selected_analyses
        show_correlation = "correlation" in selected_analyses
        show_distribution = "distribution" in selected_analyses
        show_outliers = "outliers" in selected_analyses
        st.session_state.show_trend = show_trend
        st.session_state.show_seasonal = show_seasonal
        st.session_state.show_correlation = show_correlation
        st.session_state.show_distribution = show_distribution

        st.markdown("---")
        run = st.button(
            t("old.run"), icon=":material/play_arrow:", use_container_width=True
        )

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