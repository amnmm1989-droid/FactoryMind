# ui/dashboard.py
import streamlit as st
import numpy as np
from services.analytics import compute_basic_stats, prepare_forecast_months, prepare_seasonal_data
from models.forecasting import forecast_ets, forecast_sarima
from models.statistics import trend_analysis, detect_outliers_iqr
from ui.charts import (
    create_main_chart,
    create_comparison_chart,
    create_correlation_matrix,
    create_seasonal_chart,
    create_distribution_charts
)
from ui.tables import render_details_table
from ui.export import render_export_buttons

def render_dashboard(months, products, options):
    """
    عرض لوحة التحكم الكاملة
    options: dict يحتوي على الخيارات المختارة من الشريط الجانبي
    """
    selected_products = options['selected_products']
    from_idx = options['from_idx']
    to_idx = options['to_idx']
    forecast_steps = options['forecast_steps']
    show_confidence = options['show_confidence']
    forecast_model = options['forecast_model']
    show_trend = options['show_trend']
    show_seasonal = options['show_seasonal']
    show_correlation = options['show_correlation']
    show_distribution = options['show_distribution']
    show_outliers = options['show_outliers']

    main_product = selected_products[0]
    data_main = products[main_product]
    selected_data_main = data_main[from_idx:to_idx+1]
    selected_months = months[from_idx:to_idx+1]

    all_products_data = {}
    for p in selected_products:
        all_products_data[p] = products[p][from_idx:to_idx+1]

    # ========== التنبؤ ==========
    forecast_vals, lower_vals, upper_vals, metrics, ets_error = forecast_ets(selected_data_main, steps=forecast_steps)
    if ets_error:
        st.warning(f"⚠️ تحذير ETS: {ets_error}")

    sarima_forecast = None
    if forecast_model == "SARIMA (إذا توفر)":
        sarima_forecast, sarima_error = forecast_sarima(selected_data_main, steps=forecast_steps)
        if sarima_error:
            st.warning(f"⚠️ تحذير SARIMA: {sarima_error}")

    forecast_months = prepare_forecast_months(to_idx, months, forecast_steps)

    # ========== الإحصائيات الأساسية ==========
    stats = compute_basic_stats(selected_data_main)
    st.subheader(f"📊 تحليل المنتج: {main_product}")

    col1, col2, col3, col4, col5, col6 = st.columns(6)
    col1.metric("📦 الإجمالي", f"{stats['total']:,.0f}")
    col2.metric("📈 المتوسط", f"{stats['avg']:,.1f}")
    col3.metric("⬆ الأعلى", f"{stats['max']:,.0f}")
    col4.metric("⬇ الأدنى (غير صفري)", f"{stats['min']:,.0f}")
    col5.metric("📊 الانحراف المعياري", f"{stats['std']:,.1f}")
    col6.metric("📌 الوسيط", f"{stats['median']:,.0f}")

    col7, col8, col9, col10 = st.columns(4)
    col7.metric("📅 أشهر (>0)", f"{stats['non_zero_count']}")
    col8.metric("📉 معامل الاختلاف", f"{stats['cv']:.2%}")
    col9.metric("🔮 آخر قيمة", f"{stats['last_val']:,.0f}")
    col10.metric("📈 قيمة التنبؤ (أول شهر)", f"{forecast_vals[0]:,.0f}")

    if metrics:
        with st.expander("📈 مقاييس دقة التنبؤ (ETS)"):
            col_m1, col_m2, col_m3 = st.columns(3)
            col_m1.metric("MAE", f"{metrics['MAE']:.2f}")
            col_m2.metric("RMSE", f"{metrics['RMSE']:.2f}")
            col_m3.metric("MAPE", f"{metrics['MAPE']:.2f}%")

    # ========== تحليل الاتجاه ==========
    if show_trend:
        trend = trend_analysis(selected_data_main)
        st.subheader("📈 تحليل الاتجاه")
        col_t1, col_t2, col_t3, col_t4 = st.columns(4)
        col_t1.metric("الاتجاه", trend['direction'])
        col_t2.metric("الميل (لكل شهر)", f"{trend['slope']:.2f}")
        col_t3.metric("R² (قوة النموذج)", f"{trend['r_squared']:.3f}")
        col_t4.metric("قيمة p (الدلالة)", f"{trend['p_value']:.4f}")

    # ========== كشف النقاط الشاذة ==========
    outliers = []
    if show_outliers:
        outliers, lower_bound, upper_bound = detect_outliers_iqr(selected_data_main)
        if outliers:
            st.warning(f"⚠️ تم اكتشاف {len(outliers)} نقطة شاذة (أشهر: {', '.join([selected_months[i] for i in outliers])})")
        else:
            st.success("✅ لم يتم اكتشاف نقاط شاذة")

    # ========== الرسم البياني الرئيسي ==========
    st.subheader("📈 الاتجاه الفعلي والتنبؤ")
    fig = create_main_chart(
        selected_months, selected_data_main,
        forecast_months, forecast_vals, lower_vals, upper_vals,
        sarima_forecast, outliers, main_product, show_confidence
    )
    st.plotly_chart(fig, use_container_width=True)

    # ========== مقارنة المنتجات ==========
    if len(selected_products) > 1:
        st.subheader("📊 مقارنة المنتجات المختارة")
        fig_compare = create_comparison_chart(selected_months, all_products_data)
        st.plotly_chart(fig_compare, use_container_width=True)

    # ========== مصفوفة الارتباط ==========
    if show_correlation and len(selected_products) > 1:
        st.subheader("📊 مصفوفة الارتباط بين المنتجات")
        fig_corr = create_correlation_matrix(all_products_data)
        st.plotly_chart(fig_corr, use_container_width=True)

    # ========== التحليل الموسمي ==========
    if show_seasonal and len(selected_months) >= 4:
        st.subheader("📅 التحليل الموسمي (حسب الربع)")
        seasonal_avg = prepare_seasonal_data(selected_months, selected_data_main)
        fig_season = create_seasonal_chart(seasonal_avg)
        st.plotly_chart(fig_season, use_container_width=True)
        st.dataframe(seasonal_avg, use_container_width=True)

    # ========== تحليل التوزيع الإحصائي ==========
    if show_distribution:
        st.subheader("📊 تحليل التوزيع الإحصائي")
        col_dist1, col_dist2 = st.columns(2)
        fig_hist, fig_box, fig_density = create_distribution_charts(selected_data_main)
        with col_dist1:
            st.plotly_chart(fig_hist, use_container_width=True)
            st.plotly_chart(fig_density, use_container_width=True)
        with col_dist2:
            st.plotly_chart(fig_box, use_container_width=True)

    # ========== جدول البيانات التفصيلية ==========
    st.subheader("📋 البيانات التفصيلية مع التغيرات")
    render_details_table(selected_months, selected_data_main, forecast_months, forecast_vals)

    # ========== تصدير البيانات ==========
    render_export_buttons(main_product, selected_months, selected_data_main,
                          forecast_months, forecast_vals, lower_vals, upper_vals)

    # ========== تذييل ==========
    st.markdown("---")
    st.caption("🔮 نظام تحليل وتنبؤ متقدم – يعمل بنماذج ETS، SARIMA، والانحدار الخطي")
    st.caption(f"📅 تم تحليل البيانات من {selected_months[0]} إلى {selected_months[-1]} (عدد الأشهر: {len(selected_months)})")