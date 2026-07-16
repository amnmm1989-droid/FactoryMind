# ui/sidebar.py
import streamlit as st
from config import DEFAULT_FORECAST_STEPS, MAX_FORECAST_STEPS

def render_sidebar(months, product_names):
    """عرض الشريط الجانبي وإرجاع الخيارات المختارة"""
    with st.sidebar:
        st.header("🎛️ لوحة التحكم")

        # اختيار المنتج (متعدد)
        selected_products = st.multiselect(
            "اختر المنتج (يمكن اختيار عدة)",
            product_names,
            default=st.session_state.selected_products if st.session_state.selected_products else [product_names[0]]
        )
        st.session_state.selected_products = selected_products

        if not selected_products:
            st.warning("الرجاء اختيار منتج واحد على الأقل")
            st.stop()

        # نطاق الأشهر
        month_indices = list(range(len(months)))
        from_idx = st.selectbox("من شهر", month_indices, format_func=lambda i: months[i], index=0)
        to_idx = st.selectbox("إلى شهر", month_indices, format_func=lambda i: months[i], index=len(months)-1)

        if from_idx > to_idx:
            st.error("تاريخ البداية يجب أن يكون قبل النهاية")
            st.stop()

        # إعدادات التنبؤ
        st.subheader("🔮 إعدادات التنبؤ")
        forecast_steps = st.slider("عدد الأشهر للتنبؤ", min_value=1, max_value=MAX_FORECAST_STEPS, value=DEFAULT_FORECAST_STEPS, step=1)
        show_confidence = st.checkbox("عرض فترات الثقة", value=True)
        forecast_model = st.selectbox("نموذج التنبؤ", ["ETS (التنعيم الأسي)", "SARIMA (إذا توفر)"])

        # تحليلات إضافية
        st.subheader("📊 تحليلات إضافية")
        show_trend = st.checkbox("تحليل الاتجاه", value=st.session_state.get('show_trend', True))
        st.session_state.show_trend = show_trend
        show_seasonal = st.checkbox("التحليل الموسمي", value=st.session_state.get('show_seasonal', True))
        st.session_state.show_seasonal = show_seasonal
        show_correlation = st.checkbox("مصفوفة الارتباط بين المنتجات", value=st.session_state.get('show_correlation', True))
        st.session_state.show_correlation = show_correlation
        show_distribution = st.checkbox("تحليل التوزيع الإحصائي", value=st.session_state.get('show_distribution', True))
        st.session_state.show_distribution = show_distribution
        show_outliers = st.checkbox("كشف النقاط الشاذة", value=True)

        st.markdown("---")
        run = st.button("🔄 تشغيل التحليل المتقدم", use_container_width=True)

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