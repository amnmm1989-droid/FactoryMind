# ui/charts.py
import pandas as pd
import plotly.express as px

from services.analytics import QUANTITY_KEY, QUARTER_KEY
from ui.i18n import format_months, t

# أسماء الأعمدة تُترجَم عند البناء: هذه DataFrames تُنشأ وتُستهلَك داخل
# الدالة نفسها، فلا حاجة لمفاتيح ثابتة. ما يحتاجها هو ما يعبر حدود
# الطبقات (services/analytics.py، ui/tables.py).


def create_main_chart(selected_months, series, forecast_months, forecast_vals,
                      lower_vals, upper_vals,
                      sarima_forecast, outliers, main_product, show_confidence):
    """إنشاء الرسم البياني الرئيسي (البيانات الفعلية + التنبؤ)"""
    month, quantity, kind = t("common.month"), t("common.quantity"), t("chart.series")
    display_months = format_months(list(selected_months))
    # أشهر التنبؤ تصل بصيغة ISO من services/analytics — تُصاغ هنا
    forecast_months = format_months(list(forecast_months))

    df_all = pd.concat([
        pd.DataFrame({month: display_months, quantity: series, kind: t("fc.actual")}),
        pd.DataFrame({month: forecast_months, quantity: forecast_vals,
                      kind: t("chart.ets_forecast")}),
    ])

    if sarima_forecast is not None:
        df_all = pd.concat([df_all, pd.DataFrame({
            month: forecast_months, quantity: sarima_forecast,
            kind: t("chart.sarima_forecast"),
        })])

    fig = px.line(df_all, x=month, y=quantity, color=kind,
                  title=t("chart.trend_and_forecast", product=main_product))

    if outliers:
        fig.add_scatter(
            x=[display_months[i] for i in outliers], y=[series[i] for i in outliers],
            mode='markers', marker=dict(color='red', size=10, symbol='x'),
            name=t("chart.outliers"),
        )

    if show_confidence and len(forecast_months) > 0:
        for values, label in ((upper_vals, t("fc.upper")), (lower_vals, t("chart.lower"))):
            fig.add_scatter(x=forecast_months, y=values, mode='lines',
                            line=dict(dash='dash', color='rgba(250,204,21,0.5)'),
                            name=label)
        fig.add_scatter(
            x=list(forecast_months) + list(forecast_months)[::-1],
            y=list(upper_vals) + list(lower_vals)[::-1],
            fill='toself', fillcolor='rgba(250,204,21,0.2)',
            line=dict(width=0), showlegend=False, name=t("fc.interval"),
        )

    fig.update_layout(height=450, margin=dict(l=0, r=0, t=40, b=0))
    return fig


def create_comparison_chart(selected_months, all_products_data):
    """إنشاء رسم بياني لمقارنة المنتجات"""
    month, quantity, product = t("common.month"), t("common.quantity"), t("common.product")
    display_months = format_months(list(selected_months))

    df_compare = pd.concat([
        pd.DataFrame({month: display_months, quantity: data, product: name})
        for name, data in all_products_data.items()
    ])

    fig = px.line(df_compare, x=month, y=quantity, color=product,
                  title=t("chart.monthly_comparison"))
    fig.update_layout(height=400)
    return fig


def create_correlation_matrix(all_products_data):
    """إنشاء مصفوفة الارتباط"""
    corr_matrix = pd.DataFrame(all_products_data).corr()
    fig = px.imshow(corr_matrix, text_auto=True, color_continuous_scale='RdBu_r',
                    title=t("old.correlation_title"))
    fig.update_layout(height=500)
    return fig


def create_seasonal_chart(seasonal_avg):
    """إنشاء رسم بياني للتحليل الموسمي.

    الأرباع تصل كرموز (q1..q4) من services/analytics — تُترجَم هنا فقط،
    بعد أن أدّت دورها في الفرز.
    """
    quarter, average = t("chart.quarter"), t("chart.average")
    frame = pd.DataFrame({
        quarter: [t(f"chart.{code}") for code in seasonal_avg[QUARTER_KEY]],
        average: seasonal_avg[QUANTITY_KEY].values,
    })

    fig = px.bar(frame, x=quarter, y=average, title=t("chart.quarterly_average"),
                 color=average, color_continuous_scale='Blues')
    fig.update_layout(height=350)
    return fig


def create_distribution_charts(series):
    """إنشاء رسوم التوزيع الإحصائي (هيستوجرام، Boxplot، كثافة)"""
    quantity = t("common.quantity")

    fig_hist = px.histogram(series, nbins=20, title=t("chart.histogram"),
                            labels={'value': quantity, 'count': t("chart.frequency")})
    fig_hist.update_layout(height=300)

    fig_box = px.box(y=series, title=t("chart.boxplot"), labels={'y': quantity})
    fig_box.update_layout(height=300)

    fig_density = px.density_contour(x=series, title=t("chart.density"),
                                     labels={'x': quantity})
    fig_density.update_layout(height=300)

    return fig_hist, fig_box, fig_density
