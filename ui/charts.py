# ui/charts.py
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
import numpy as np

def create_main_chart(selected_months, series, forecast_months, forecast_vals, lower_vals, upper_vals,
                      sarima_forecast, outliers, main_product, show_confidence):
    """إنشاء الرسم البياني الرئيسي (البيانات الفعلية + التنبؤ)"""
    df_actual = pd.DataFrame({
        'الشهر': selected_months,
        'الكمية': series,
        'النوع': 'فعلي'
    })

    df_forecast = pd.DataFrame({
        'الشهر': forecast_months,
        'الكمية': forecast_vals,
        'النوع': 'تنبؤ ETS'
    })

    df_all = pd.concat([df_actual, df_forecast])

    if sarima_forecast is not None:
        df_sarima = pd.DataFrame({
            'الشهر': forecast_months,
            'الكمية': sarima_forecast,
            'النوع': 'تنبؤ SARIMA'
        })
        df_all = pd.concat([df_all, df_sarima])

    fig = px.line(df_all, x='الشهر', y='الكمية', color='النوع',
                  title=f'الاتجاه والتنبؤ - {main_product}',
                  labels={'الكمية': 'الكمية', 'الشهر': 'الشهر'})

    if outliers:
        outlier_df = pd.DataFrame({
            'الشهر': [selected_months[i] for i in outliers],
            'الكمية': [series[i] for i in outliers]
        })
        fig.add_scatter(x=outlier_df['الشهر'], y=outlier_df['الكمية'],
                        mode='markers', marker=dict(color='red', size=10, symbol='x'),
                        name='نقاط شاذة')

    if show_confidence and len(forecast_months) > 0:
        df_upper = pd.DataFrame({'الشهر': forecast_months, 'الكمية': upper_vals})
        df_lower = pd.DataFrame({'الشهر': forecast_months, 'الكمية': lower_vals})
        fig.add_scatter(x=df_upper['الشهر'], y=df_upper['الكمية'],
                        mode='lines', line=dict(dash='dash', color='rgba(250,204,21,0.5)'),
                        name='حد أعلى 95%')
        fig.add_scatter(x=df_lower['الشهر'], y=df_lower['الكمية'],
                        mode='lines', line=dict(dash='dash', color='rgba(250,204,21,0.5)'),
                        name='حد أدنى 95%')
        fig.add_scatter(
            x=df_upper['الشهر'].tolist() + df_lower['الشهر'].tolist()[::-1],
            y=df_upper['الكمية'].tolist() + df_lower['الكمية'].tolist()[::-1],
            fill='toself',
            fillcolor='rgba(250,204,21,0.2)',
            line=dict(width=0),
            showlegend=False,
            name='فترة الثقة 95%'
        )

    fig.update_layout(height=450, margin=dict(l=0, r=0, t=40, b=0))
    return fig

def create_comparison_chart(selected_months, all_products_data):
    """إنشاء رسم بياني لمقارنة المنتجات"""
    df_compare = pd.DataFrame()
    for p, data in all_products_data.items():
        temp_df = pd.DataFrame({
            'الشهر': selected_months,
            'الكمية': data,
            'المنتج': p
        })
        df_compare = pd.concat([df_compare, temp_df])

    fig = px.line(df_compare, x='الشهر', y='الكمية', color='المنتج',
                  title='مقارنة الأداء الشهري',
                  labels={'الكمية': 'الكمية', 'الشهر': 'الشهر'})
    fig.update_layout(height=400)
    return fig

def create_correlation_matrix(all_products_data):
    """إنشاء مصفوفة الارتباط"""
    df_corr = pd.DataFrame(all_products_data)
    corr_matrix = df_corr.corr()
    fig = px.imshow(corr_matrix,
                    text_auto=True,
                    color_continuous_scale='RdBu_r',
                    title='مصفوفة الارتباط')
    fig.update_layout(height=500)
    return fig

def create_seasonal_chart(seasonal_avg):
    """إنشاء رسم بياني للتحليل الموسمي"""
    fig = px.bar(seasonal_avg, x='الربع', y='الكمية',
                 title='متوسط الكمية حسب الربع',
                 labels={'الكمية': 'المتوسط', 'الربع': 'الربع'},
                 color='الكمية', color_continuous_scale='Blues')
    fig.update_layout(height=350)
    return fig

def create_distribution_charts(series):
    """إنشاء رسوم التوزيع الإحصائي (هيستوجرام، Boxplot، كثافة)"""
    fig_hist = px.histogram(series, nbins=20, title='مدرج تكراري',
                            labels={'value': 'الكمية', 'count': 'التكرار'})
    fig_hist.update_layout(height=300)

    fig_box = px.box(y=series, title='صندوق الحظائر (Boxplot)',
                     labels={'y': 'الكمية'})
    fig_box.update_layout(height=300)

    fig_density = px.density_contour(x=series, title='منحنى الكثافة',
                                     labels={'x': 'الكمية'})
    fig_density.update_layout(height=300)

    return fig_hist, fig_box, fig_density