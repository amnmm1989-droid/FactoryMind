# ui/dashboard.py
import streamlit as st
import numpy as np
from core.exceptions import InsufficientDataError
from core.logging_config import get_logger
from services.analytics import prepare_seasonal_data
from services.product_analysis_service import analyze_product
from ui.charts import (
    create_main_chart,
    create_comparison_chart,
    create_correlation_matrix,
    create_seasonal_chart,
    create_distribution_charts
)
from ui.tables import render_details_table
from ui.export import render_export_buttons
from ui.i18n import format_month, format_months, t

logger = get_logger(__name__)

def render_dashboard(months, products, options):
    """
    عرض لوحة التحكم الكاملة
    options: dict يحتوي على الخيارات المختارة من الشريط الجانبي

    ملاحظة (Phase 1): منطق الحساب (إحصائيات، تنبؤ، اتجاه، قيم شاذة)
    انتقل بالكامل إلى services.product_analysis_service.analyze_product.
    هذا الملف أصبح مسؤولاً عن العرض (rendering) فقط، ولا يحسب شيئاً بنفسه.
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

    # ========== التحليل الكامل عبر Service Layer ==========
    try:
        analysis = analyze_product(
            product_name=main_product,
            full_months=months,
            selected_months=selected_months,
            series=selected_data_main,
            to_idx=to_idx,
            forecast_steps=forecast_steps,
            include_sarima=(forecast_model == "sarima"),
            include_trend=show_trend,
            include_outliers=show_outliers,
        )
    except InsufficientDataError as e:
        logger.warning("Dashboard render aborted: %s", e)
        st.error(e.message, icon=":material/error:")
        st.stop()

    forecast_vals = analysis.ets.forecast_values
    lower_vals = analysis.ets.lower_bound
    upper_vals = analysis.ets.upper_bound
    metrics = None
    if analysis.ets.mae is not None:
        metrics = {'MAE': analysis.ets.mae, 'RMSE': analysis.ets.rmse, 'MAPE': analysis.ets.mape}
    sarima_forecast = analysis.sarima_values
    forecast_months = analysis.forecast_months

    # ========== الإحصائيات الأساسية ==========
    stats = analysis.stats
    st.subheader(t("old.product_analysis", product=main_product))

    col1, col2, col3, col4, col5, col6 = st.columns(6)
    col1.metric(t("old.total"), f"{stats.total:,.0f}")
    col2.metric(t("old.average"), f"{stats.avg:,.1f}")
    col3.metric(t("old.max"), f"{stats.max:,.0f}")
    col4.metric(t("old.min_nonzero"), f"{stats.min:,.0f}")
    col5.metric(t("old.std"), f"{stats.std:,.1f}")
    col6.metric(t("old.median"), f"{stats.median:,.0f}")

    col7, col8, col9, col10 = st.columns(4)
    col7.metric(t("old.nonzero_months"), f"{stats.non_zero_count}")
    col8.metric(t("old.cv"), f"{stats.cv:.2%}")
    col9.metric(t("old.last_value"), f"{stats.last_val:,.0f}")
    col10.metric(t("old.first_forecast"), f"{forecast_vals[0]:,.0f}")

    if metrics:
        with st.expander(t("old.accuracy_metrics")):
            col_m1, col_m2, col_m3 = st.columns(3)
            col_m1.metric("MAE", f"{metrics['MAE']:.2f}")
            col_m2.metric("RMSE", f"{metrics['RMSE']:.2f}")
            col_m3.metric("MAPE", f"{metrics['MAPE']:.2f}%")

    # ========== تحليل الاتجاه ==========
    if show_trend and analysis.trend:
        trend = analysis.trend
        st.subheader(t("old.trend_analysis"))
        col_t1, col_t2, col_t3, col_t4 = st.columns(4)
        col_t1.metric(t("old.direction"), t(f"trend.{trend.direction}"))
        col_t2.metric(t("old.slope"), f"{trend.slope:.2f}")
        col_t3.metric(t("old.r_squared"), f"{trend.r_squared:.3f}")
        col_t4.metric(t("old.p_value"), f"{trend.p_value:.4f}")

    # ========== كشف النقاط الشاذة ==========
    outlier_indices = []
    if show_outliers and analysis.outliers:
        outlier_indices = analysis.outliers.outlier_indices
        if outlier_indices:
            st.warning(t("old.outliers_found",
                         count=len(outlier_indices),
                         months="، ".join(format_months(
                             [selected_months[i] for i in outlier_indices]))),
                       icon=":material/warning:")
        else:
            st.success(t("old.no_outliers"), icon=":material/check_circle:")

    # ========== الرسم البياني الرئيسي ==========
    st.subheader(t("old.main_chart"))
    fig = create_main_chart(
        selected_months, selected_data_main,
        forecast_months, forecast_vals, lower_vals, upper_vals,
        sarima_forecast, outlier_indices, main_product, show_confidence
    )
    st.plotly_chart(fig, use_container_width=True)

    # ========== مقارنة المنتجات ==========
    if len(selected_products) > 1:
        st.subheader(t("old.comparison_selected"))
        fig_compare = create_comparison_chart(selected_months, all_products_data)
        st.plotly_chart(fig_compare, use_container_width=True)

    # ========== مصفوفة الارتباط ==========
    if show_correlation and len(selected_products) > 1:
        st.subheader(t("old.correlation_products"))
        fig_corr = create_correlation_matrix(all_products_data)
        st.plotly_chart(fig_corr, use_container_width=True)

    # ========== التحليل الموسمي ==========
    if show_seasonal and len(selected_months) >= 4:
        st.subheader(t("old.seasonal_title"))
        seasonal_avg = prepare_seasonal_data(selected_months, selected_data_main)
        fig_season = create_seasonal_chart(seasonal_avg)
        st.plotly_chart(fig_season, use_container_width=True)
        st.dataframe(seasonal_avg, use_container_width=True)

    # ========== تحليل التوزيع الإحصائي ==========
    if show_distribution:
        st.subheader(t("old.distribution_title"))
        col_dist1, col_dist2 = st.columns(2)
        fig_hist, fig_box, fig_density = create_distribution_charts(selected_data_main)
        with col_dist1:
            st.plotly_chart(fig_hist, use_container_width=True)
            st.plotly_chart(fig_density, use_container_width=True)
        with col_dist2:
            st.plotly_chart(fig_box, use_container_width=True)

    # ========== جدول البيانات التفصيلية ==========
    st.subheader(t("old.details_table"))
    render_details_table(selected_months, selected_data_main, forecast_months, forecast_vals)

    # ========== تصدير البيانات ==========
    render_export_buttons(main_product, selected_months, selected_data_main,
                          forecast_months, forecast_vals, lower_vals, upper_vals)

    # ========== تذييل ==========
    st.markdown("---")
    st.caption(t("old.footer"))
    st.caption(t("old.analysed_range",
                 start=format_month(selected_months[0]),
                 end=format_month(selected_months[-1]),
                 count=len(selected_months)))
